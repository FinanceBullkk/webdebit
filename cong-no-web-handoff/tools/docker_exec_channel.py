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
"""

from __future__ import annotations

import atexit
import queue
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
