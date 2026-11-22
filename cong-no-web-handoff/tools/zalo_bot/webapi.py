"""Lớp gọi API web của bot (ZALO-BOT-01 Phần 5): chỉ GET, chỉ các tuyến trong bảng công cụ, gửi login của người hỏi.

API tin header `Tailscale-User-Login` khi yêu cầu đến từ loopback, và header đó mở được cả đường ghi. Vì vậy lớp này:
- không có hàm nào gửi phương thức khác GET;
- chỉ nhận `Route` có sẵn trong mã (model không tự ghép URL), tuyến admin chỉ cho người quyền admin;
- kiểm từng tham số theo khuôn của tuyến, tham số lạ thì từ chối;
- không theo chuyển hướng, không dùng proxy, giới hạn cỡ trả về và thời gian chờ.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .config import LOGIN, ROLES

BASE = "http://127.0.0.1:8780"
TIMEOUT = 15
MAX_BYTES = 4_000_000
HTTP_CODES = {400: "bad_request", 401: "forbidden", 403: "forbidden", 404: "not_found", 409: "conflict", 429: "rate_limited"}


class ApiError(Exception):
    """Lỗi gọi API, `code` là mã ngắn để trả lại model và ghi nhật ký (không có chữ của API)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Route:
    path: str
    params: dict[str, re.Pattern] = field(default_factory=dict)
    admin: bool = False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebApi:
    def __init__(self, base: str = BASE, *, opener: urllib.request.OpenerDirector | None = None, timeout: float = TIMEOUT):
        parts = urllib.parse.urlsplit(base)
        if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost") or not parts.port or parts.path not in ("", "/"):
            raise ValueError("API của bot chỉ được là http://127.0.0.1:<cổng>")
        self.base = f"http://{parts.hostname}:{parts.port}"
        self.host = f"{parts.hostname}:{parts.port}"
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        self.timeout = timeout

    def get(self, route: Route, params: dict[str, str] | None = None, *, login: str, role: str) -> object:
        if not LOGIN.fullmatch(login) or role not in ROLES:
            raise ApiError("bad_identity")
        if route.admin and role != "admin":
            raise ApiError("forbidden_role")
        clean: list[tuple[str, str]] = []
        for key, value in sorted((params or {}).items()):
            pattern = route.params.get(key)
            if pattern is None or not isinstance(value, str) or not pattern.fullmatch(value):
                raise ApiError("bad_param")
            clean.append((key, value))
        url = f"{self.base}{route.path}" + (f"?{urllib.parse.urlencode(clean)}" if clean else "")
        request = urllib.request.Request(url, method="GET", headers={
            "Host": self.host, "Tailscale-User-Login": login, "Accept": "application/json", "User-Agent": "webdebit-zalo-bot"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                status = getattr(response, "status", 200)
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise ApiError(HTTP_CODES.get(error.code, "server_error" if error.code >= 500 else "http_error")) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ApiError("unreachable") from None
        if status != 200:
            raise ApiError("http_error")     # gồm cả 3xx: không theo chuyển hướng
        if len(body) > MAX_BYTES:
            raise ApiError("too_large")
        try:
            return json.loads(body)
        except ValueError:
            raise ApiError("bad_json") from None
