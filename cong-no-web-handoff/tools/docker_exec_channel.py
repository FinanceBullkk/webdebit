"""One reusable `docker exec` per container for the disposable-PostgreSQL harnesses.

Why: each `docker exec` costs ~0.1 s on a Linux runner but ~0.4-0.5 s through Docker
Desktop/WSL on Windows (measured 28/10/2026: 20 single-query execs 9.2 s, the same 20
queries in one exec 0.5 s). The V7 harness issues hundreds of single-statement psql
calls, so almost all local wall time was exec start-up, not PostgreSQL.

What stays the same: every request still starts a fresh process inside the container
with the same argv, environment and stdin, and returns its own exit code, stdout and
stderr. Only the host-side `docker exec` is reused, so one psql call is still one
connection and one transaction scope, exactly as before.

Callers keep their original subprocess path as the fallback: `run_docker_exec` returns
None for argv shapes it does not understand, while another thread holds the channel,
or when the channel cannot start, and the caller then runs `docker exec` directly.

`run_kept_psql` goes one step further for statements that must succeed: one psql
connection per argv runs them all (measured 3/11/2026 on Docker Desktop: fresh psql over
the channel 54 ms, kept connection 4 ms; the V7 backend harness makes ~5,800 calls).
After every request it runs ROLLBACK and DISCARD ALL before replying, so open
transactions, locks, SET, roles, temp tables and advisory locks never reach the next
request. An error still ends psql through ON_ERROR_STOP with the same exit code and
output; the next request starts a new connection. Expected errors (`check=False`) and
input with psql meta-commands (`\\set` would outlive the request) keep a fresh psql.
"""

from __future__ import annotations

import atexit
import queue
import re
import secrets
import shlex
import subprocess
import threading

# Length-prefixed frames both ways, so SQL bytes need no escaping. `head -c` reads
# exactly N bytes from the pipe (GNU head never reads past the count it was given).
_LOOP = r"""
d=$(mktemp -d) || exit 1
while IFS=' ' read -r clen ilen; do
  head -c "$clen" > "$d/c"
  head -c "$ilen" > "$d/i"
  bash "$d/c" < "$d/i" > "$d/o" 2> "$d/e"
  printf '%s %s %s\n' "$?" "$(wc -c < "$d/o")" "$(wc -c < "$d/e")"
  cat "$d/o" "$d/e"
done
"""


class _Channel:
    def __init__(self, container: str):
        self.container = container
        self.lock = threading.Lock()
        self.proc = subprocess.Popen(["docker", "exec", "-i", container, "bash", "-c", _LOOP],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)
        self.replies: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        out = self.proc.stdout
        try:
            while True:
                header = out.readline()
                if not header:
                    break
                rc, olen, elen = (int(x) for x in header.split())
                self.replies.put((rc, _read_exact(out, olen), _read_exact(out, elen)))
        except (OSError, ValueError):
            pass
        self.replies.put(None)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        if self.alive():
            self.proc.kill()
        self.proc.wait()

    def run(self, argv: list[str], env: dict[str, str], stdin: bytes, timeout: float):
        script = ("exec env " + " ".join(shlex.quote(f"{k}={v}") for k, v in env.items())
                  + " " + " ".join(shlex.quote(a) for a in argv) + "\n").encode("utf-8")
        try:
            self.proc.stdin.write(f"{len(script)} {len(stdin)}\n".encode() + script + stdin)
            self.proc.stdin.flush()
        except OSError:
            return None  # nothing reached the container; the direct path is safe
        try:
            reply = self.replies.get(timeout=timeout)
        except queue.Empty:
            self.close()  # same as subprocess.run: stop waiting, kill the exec client
            raise subprocess.TimeoutExpired(argv, timeout) from None
        if reply is None:
            # The command may have run; retrying it directly could repeat a write.
            raise OSError(f"docker exec channel to {self.container} closed mid-command")
        return reply


def _read_exact(stream, n: int) -> bytes:
    chunks = []
    while n:
        chunk = stream.read(n)
        if not chunk:
            raise OSError("short read from docker exec channel")
        chunks.append(chunk)
        n -= len(chunk)
    return b"".join(chunks)


_channels: dict[str, _Channel] = {}
_channels_lock = threading.Lock()


def _channel(container: str) -> _Channel | None:
    with _channels_lock:
        ch = _channels.get(container)
        if ch is not None and not ch.alive():
            ch = None
        if ch is None:
            try:
                ch = _channels[container] = _Channel(container)
            except OSError:
                return None
        return ch


@atexit.register
def close_all() -> None:
    with _channels_lock:
        for ch in _channels.values():
            ch.close()
        _channels.clear()
        for kept in _kept.values():
            kept.close()
        _kept.clear()


def _parse(args: list[str]):
    """Split `docker exec [-i] [--env K=V]... NAME CMD...`; None for anything else.

    >>> _parse(["docker", "exec", "-i", "--env", "A=1", "c", "pg_isready", "-q"])
    ('c', {'A': '1'}, ['pg_isready', '-q'])
    >>> _parse(["docker", "exec", "-u", "postgres", "c", "id"]) is None
    True
    """
    if args[:2] != ["docker", "exec"]:
        return None
    env: dict[str, str] = {}
    i = 2
    while i < len(args) and args[i].startswith("-"):
        if args[i] == "-i":
            i += 1
        elif args[i] == "--env" and i + 1 < len(args) and "=" in args[i + 1]:
            key, value = args[i + 1].split("=", 1)
            env[key] = value
            i += 2
        else:
            return None
    if len(args) - i < 2:
        return None
    return args[i], env, args[i + 1:]


def run_docker_exec(args: list[str], *, input_text: str | None,
                    timeout: float) -> subprocess.CompletedProcess[str] | None:
    """Run a `docker exec` argv over the container's channel, or None to fall back."""
    parsed = _parse(args)
    if parsed is None:
        return None
    container, env, argv = parsed
    ch = _channel(container)
    if ch is None or not ch.lock.acquire(blocking=False):
        return None  # concurrent callers (lock/contention checks) keep separate execs
    try:
        reply = ch.run(argv, env, (input_text or "").encode("utf-8"), timeout)
    finally:
        ch.lock.release()
    if reply is None:
        return None
    rc, out, err = reply
    return subprocess.CompletedProcess(args, rc, out.decode("utf-8", "replace"),
                                       err.decode("utf-8", "replace"))


# A psql meta-command anywhere at line start: `\set` and friends outlive the request.
_META = re.compile(rb"^[ \t]*\\", re.M)
# Statements PostgreSQL refuses while any other connection uses the database involved.
_DATABASE_DDL = re.compile(rb"\b(?:DROP|ALTER)\s+DATABASE\b|\bTEMPLATE\b", re.I)


class _KeptPsql:
    """One psql connection; each request ends with markers on stdout and stderr."""

    def __init__(self, container: str, env: dict[str, str], argv: list[str]):
        args = ["docker", "exec", "-i"]
        for key, value in env.items():
            args += ["--env", f"{key}={value}"]
        self.argv = argv
        self.proc = subprocess.Popen([*args, container, *argv], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.lock = threading.Lock()
        self.token = secrets.token_hex(8)
        self.count = 0
        self.out: queue.Queue = queue.Queue()
        self.err: queue.Queue = queue.Queue()
        for stream, lines in ((self.proc.stdout, self.out), (self.proc.stderr, self.err)):
            threading.Thread(target=_pump, args=(stream, lines), daemon=True).start()

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        if self.alive():
            self.proc.kill()
        self.proc.wait()

    def run(self, sql: bytes, timeout: float) -> tuple[int, bytes, bytes] | None:
        self.count += 1
        end = f"__webdebit_end_{self.token}_{self.count}__".encode()
        reset = f"__webdebit_reset_{self.token}_{self.count}__".encode()
        # The lone `;` sends a statement left open by a trailing comment, as EOF does for a fresh psql.
        # Query results are flushed at once; `\warn` goes to unbuffered stderr.
        script = (sql + b"\n;\nSELECT '" + end + b"';\n\\warn " + end + b"\n"
                  b"ROLLBACK;\nDISCARD ALL;\nSELECT '" + reset + b"';\n\\warn " + reset + b"\n")
        try:
            self.proc.stdin.write(script)
            self.proc.stdin.flush()
        except OSError:
            if self.count == 1:
                return None  # psql never started; nothing reached the database
            raise OSError("kept psql connection closed before the request") from None
        try:
            out, out_done = _until(self.out, end, timeout)
            err, err_done = _until(self.err, end, timeout)
        except queue.Empty:
            self.close()  # same as subprocess.run: stop waiting, kill the exec client
            raise subprocess.TimeoutExpired(self.argv, timeout) from None
        if not (out_done and err_done):
            # ON_ERROR_STOP ended psql: its exit code and output are the request's result.
            self.close()
            return self.proc.returncode, out, err
        try:
            _, reset_done = _until(self.out, reset, timeout)
            _, reset_err_done = _until(self.err, reset, timeout)
        except queue.Empty:
            reset_done = reset_err_done = False
        if not (reset_done and reset_err_done):
            self.close()  # never reuse a connection whose reset did not finish
        return 0, out, err


def _pump(stream, lines: queue.Queue) -> None:
    for line in stream:
        lines.put(line)
    lines.put(None)


def _until(lines: queue.Queue, marker: bytes, timeout: float) -> tuple[bytes, bool]:
    """Lines before `marker` and whether it came (False: the process ended first)."""
    chunks = []
    while True:
        line = lines.get(timeout=timeout)
        if line is None:
            lines.put(None)
            return b"".join(chunks), False
        if line.rstrip(b"\r\n") == marker:
            return b"".join(chunks), True
        chunks.append(line)


_kept: dict[tuple, _KeptPsql] = {}


def _close_kept(container: str) -> None:
    with _channels_lock:
        doomed = [key for key in _kept if key[0] == container]
        kept = [_kept.pop(key) for key in doomed]
    for one in kept:
        with one.lock:   # let a request in flight finish first
            one.close()


def run_kept_psql(args: list[str], *, input_text: str, timeout: float,
                  share: bool = True) -> subprocess.CompletedProcess[str] | None:
    """Run one psql request on a kept connection, or None to fall back.

    Called for every psql request, `share=False` included: DROP/ALTER DATABASE and
    CREATE DATABASE ... TEMPLATE fail while another connection is open on that
    database, so those first close the container's kept connections and then fall back.
    """
    parsed = _parse(args)
    # psql skips a UTF-8 BOM only at the start of its input; mid-stream it would be a syntax error.
    sql = input_text.encode("utf-8").removeprefix(b"\xef\xbb\xbf")
    if parsed is None or parsed[2][0] != "psql":
        return None
    container, env, argv = parsed
    if _DATABASE_DDL.search(sql):
        _close_kept(container)
        return None
    if not share or _META.search(sql):
        return None
    key = (container, tuple(env.items()), tuple(argv))
    with _channels_lock:
        kept = _kept.get(key)
        if kept is None or not kept.alive():
            try:
                kept = _kept[key] = _KeptPsql(container, env, argv)
            except OSError:
                return None
    if not kept.lock.acquire(blocking=False):
        return None  # concurrent callers keep their own connection
    try:
        reply = kept.run(sql, timeout)
    finally:
        kept.lock.release()
    if reply is None:
        return None
    rc, out, err = reply
    return subprocess.CompletedProcess(args, rc, out.decode("utf-8", "replace"),
                                       err.decode("utf-8", "replace"))
