"""V7 actor resolution from trusted Tailscale metadata; no client actor fallback.

Pass the actual socket peer IP/port, never a forwarded header. Serve mode must
only be enabled with a loopback-only listener behind tailscale serve, which
must strip/replace identity headers. Local processes then share that trust.
This module authenticates identity only; it does not grant roles or DB access.
"""

from __future__ import annotations

import http.client
import io
import ipaddress
import json
import math
import os
import socket
import time
import unicodedata
from collections.abc import Mapping
from contextlib import suppress
from typing import Protocol
from urllib.parse import urlencode

MAX_RESPONSE = 64 * 1024
UNIX_SOCKET = "/var/run/tailscale/tailscaled.sock"
WINDOWS_PIPE = r"\\.\pipe\ProtectedPrefix\Administrators\Tailscale\tailscaled"


class IdentityError(Exception):
    """Fail-closed identity error; code is safe to expose without peer metadata.

    `detail` (optional) is for the operator's log only, never for the response.
    """

    def __init__(self, code: str, detail: str | None = None):
        super().__init__(code)
        self.code = code
        self.detail = detail


class LocalAPI(Protocol):
    def whois(self, addr: str) -> Mapping[str, object]:
        """Return decoded whois JSON for IP:port (IPv6 bracketed).

        Raise IdentityError (NOT_TAILNET for HTTP 404), TimeoutError or OSError
        on failure. Implementations must bound their own I/O timeout.
        """
        ...


class _PipeSocket:
    """Raw HTTP over a Windows byte pipe, with bounded overlapped I/O."""

    def __init__(self, path: str, timeout: float):
        # ponytail: CPython 3.12/3.13 _winapi; replace transport for other runtimes.
        import _winapi

        self.api = _winapi
        self.deadline = time.monotonic() + timeout
        self.handle = self.api.CreateFile(path, 0xC0000000, 0, None, 3, 0x40000000, None)
        self._readers = 0
        self._closed = False

    def _finish(self, operation, error):
        try:
            if error == 997:  # ERROR_IO_PENDING
                remaining = max(0, math.ceil((self.deadline - time.monotonic()) * 1000))
                result = self.api.WaitForSingleObject(operation.event, remaining)
                if result == 258:  # WAIT_TIMEOUT
                    raise TimeoutError("LocalAPI pipe timeout")
                if result != 0:
                    raise OSError("LocalAPI pipe wait failed")
        except BaseException:
            # Drain cancellation before releasing buffers or closing the handle.
            operation.cancel()
            with suppress(OSError):
                operation.GetOverlappedResult(True)
            raise
        count, error = operation.GetOverlappedResult(True)
        if error:
            raise OSError(error, "LocalAPI pipe I/O failed")
        return count

    def sendall(self, data: bytes):
        while data:
            operation, error = self.api.WriteFile(self.handle, data, True)
            count = self._finish(operation, error)
            if not count:
                raise OSError("LocalAPI pipe closed during write")
            data = data[count:]

    def readinto(self, buffer):
        try:
            operation, error = self.api.ReadFile(self.handle, len(buffer), True)
            count = self._finish(operation, error)
        except OSError as exc:
            if getattr(exc, "winerror", None) in (109, 232) or exc.errno in (109, 232):
                return 0  # ERROR_BROKEN_PIPE / ERROR_NO_DATA
            raise
        buffer[:count] = operation.getbuffer()[:count]
        return count

    recv_into = readinto

    def makefile(self, mode):
        # HTTPConnection may close before HTTPResponse finishes reading.
        self._readers += 1
        return io.BufferedReader(socket.SocketIO(self, mode))

    def _decref_socketios(self):
        self._readers -= 1
        if self._closed:
            self.close()

    def close(self):
        self._closed = True
        if not self._readers and self.handle is not None:
            self.api.CloseHandle(self.handle)
            self.handle = None


class _LocalConnection(http.client.HTTPConnection):
    def __init__(self, endpoint: str | None, timeout: float):
        super().__init__("local-tailscaled.sock", timeout=timeout)
        self.endpoint = endpoint

    def connect(self):
        if os.name == "nt":
            self.sock = _PipeSocket(self.endpoint or WINDOWS_PIPE, self.timeout)
        else:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect(self.endpoint or UNIX_SOCKET)


class TailscaleLocalAPI:
    """Local daemon only: Unix socket or Windows named pipe; never TCP/proxies."""

    def __init__(self, *, endpoint: str | None = None, timeout: float = 2.0):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self.endpoint = endpoint
        self.timeout = timeout

    def whois(self, addr: str) -> Mapping[str, object]:
        connection = _LocalConnection(self.endpoint, self.timeout)
        try:
            connection.request("GET", "/localapi/v0/whois?" + urlencode({"addr": addr}),
                               headers={"Connection": "close", "Accept": "application/json"})
            with connection.getresponse() as response:
                if response.status == 404:
                    raise IdentityError("NOT_TAILNET")
                if response.status != 200:
                    raise IdentityError("LOCALAPI_ERROR")
                body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise IdentityError("LOCALAPI_INVALID_RESPONSE")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise IdentityError("LOCALAPI_INVALID_RESPONSE")
            return result
        except TimeoutError as exc:
            raise IdentityError("LOCALAPI_TIMEOUT") from exc
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise IdentityError("LOCALAPI_INVALID_RESPONSE") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise IdentityError("LOCALAPI_ERROR") from exc
        finally:
            connection.close()


def _login(value: object) -> str:
    if not isinstance(value, str) or any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in value):
        raise IdentityError("INVALID_LOGIN")
    login = value.strip()
    if not login:
        raise IdentityError("EMPTY_LOGIN")
    local, separator, domain = login.rpartition("@")
    return local + separator + domain.lower() if separator else login


def parse_allowed_logins(value: object) -> frozenset[str] | None:
    """Operator allowlist from WEBDEBIT_ALLOWED_LOGINS / --allowed-login (ACCESS-01).

    Logins are separated by commas or whitespace and normalized like actors
    (domain lower-cased). None means "not configured": resolve_actor then keeps
    every verified tailnet identity and the API decides whether that is allowed
    (Serve mode refuses to start). An empty set denies everyone.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise IdentityError("INVALID_CONFIG")
    return frozenset(_login(item) for item in value.replace(",", " ").split())


def _allowed(login: str, allowed_logins: frozenset[str] | None) -> str:
    if allowed_logins is not None and login not in allowed_logins:
        raise IdentityError("LOGIN_NOT_ALLOWED", login)
    return login


def resolve_actor(source_ip: str, headers: Mapping[str, str], localapi: LocalAPI | None = None,
                  *, source_port: int = 0, behind_tailscale_serve: bool = False,
                  allowed_logins: frozenset[str] | None = None) -> str:
    """Resolve one request; no default actor, forwarded IP, or cached fallback.

    source_port=0 supports IP-only callers; pass the socket peer port when known.
    The LocalAPI daemon, not an IP range guess, decides tailnet membership.
    Explicit Serve mode trusts only exact 127.0.0.1/::1 socket peers.
    allowed_logins (ACCESS-01): a verified login outside the set fails closed
    with LOGIN_NOT_ALLOWED (the login only in `detail`); None skips the check.
    """
    if type(behind_tailscale_serve) is not bool:
        raise IdentityError("INVALID_CONFIG")
    if allowed_logins is not None and not isinstance(allowed_logins, frozenset):
        raise IdentityError("INVALID_CONFIG")
    try:
        if not isinstance(source_ip, str) or "%" in source_ip:
            raise ValueError
        ip = ipaddress.ip_address(source_ip)
        if type(source_port) is not int or not 0 <= source_port <= 65535:
            raise ValueError
    except ValueError as exc:
        raise IdentityError("INVALID_SOURCE") from exc
    if behind_tailscale_serve and str(ip) in ("127.0.0.1", "::1"):
        values = [value for name, value in headers.items() if name.lower() == "tailscale-user-login"]
        if len(values) > 1:
            raise IdentityError("AMBIGUOUS_LOGIN")
        if values:
            return _allowed(_login(values[0]), allowed_logins)
    addr = f"[{ip}]:{source_port}" if ip.version == 6 else f"{ip}:{source_port}"
    try:
        result = (TailscaleLocalAPI() if localapi is None else localapi).whois(addr)
    except TimeoutError as exc:
        raise IdentityError("LOCALAPI_TIMEOUT") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise IdentityError("LOCALAPI_ERROR") from exc
    if not isinstance(result, Mapping):
        raise IdentityError("LOCALAPI_INVALID_RESPONSE")
    profile = result.get("UserProfile")
    if profile is None or profile == {}:
        raise IdentityError("NO_USER")
    if not isinstance(profile, Mapping):
        raise IdentityError("LOCALAPI_INVALID_RESPONSE")
    if "LoginName" not in profile:
        raise IdentityError("NO_USER")
    return _allowed(_login(profile["LoginName"]), allowed_logins)
