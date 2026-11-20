"""QUYEN-01: hai vai trò trên web V7 — quản lý (admin) thấy mọi trang, người dùng (user) chỉ các trang làm sổ.

Danh sách login quản lý là cấu hình vận hành trên máy chạy (`WEBDEBIT_ADMIN_LOGINS` / `--admin-login`), ngoài Git như
danh sách ACCESS-01. Chưa đặt danh sách (None) thì mọi login được vào đều là quản lý: dev, test và bản cài cũ giữ nguyên.
Vai trò chỉ chia màn hình: quyền ghi tiền trong Sổ khách của người dùng không đổi.
"""

from __future__ import annotations

ADMIN = "admin"
USER = "user"

# Trang người dùng mở được. Chat Zalo vào từ thẻ Liên hệ của Sổ khách nên cũng thuộc phần người dùng.
USER_PAGES = frozenset({
    "/", "/dashboard-v7.html", "/cong-no-theo-thang.html", "/so-khach-v7-live.html",
    "/bang-thu.html", "/bao-cao-thang.html", "/zalo-chat.html",
})
# API chỉ trang quản lý gọi: Máy chạy, Đội xe, Nhật ký công việc. API mà trang người dùng cần (company-info cho
# debit note, inbox cho việc Sheet trong Sổ khách…) vẫn mở cho mọi login được vào.
ADMIN_API_PREFIXES = ("/api/v7/machine", "/api/v7/doixe", "/api/v7/nhat-ky", "/api/v7/admin")   # admin: QUYEN-02

FORBIDDEN_MESSAGE = "Mục này chỉ dành cho quản lý."
_HTML_OPEN = b'<html lang="vi"'
_HTML_USER = b'<html lang="vi" data-role="user"'


def role(actor: str, admin_logins: frozenset[str] | None) -> str:
    return ADMIN if admin_logins is None or actor in admin_logins else USER


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def admin_api(path: str) -> bool:
    return any(_under(path, prefix) for prefix in ADMIN_API_PREFIXES)


def allowed(path: str, current: str, pages) -> bool:
    """Trang HTML ngoài USER_PAGES và API của ADMIN_API_PREFIXES chỉ cho quản lý; file .js/.css và API khác mở cho mọi login."""
    if current == ADMIN:
        return True
    if path in pages:
        return path in USER_PAGES
    return not admin_api(path)


def mark_html(data: bytes) -> bytes:
    """Gắn data-role="user" vào thẻ <html> để menu và link vẽ đúng ngay lần đầu, không cần hỏi API."""
    if _HTML_OPEN not in data:
        raise ValueError("page has no <html lang=\"vi\"")
    return data.replace(_HTML_OPEN, _HTML_USER, 1)


FORBIDDEN_PAGE = ("<!doctype html><html lang=\"vi\" data-role=\"user\"><head><meta charset=\"utf-8\">"
                  "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Công nợ HTH</title></head>"
                  "<body style=\"font:18px/1.5 system-ui,sans-serif;margin:48px auto;max-width:560px;padding:0 16px\">"
                  f"<h1 style=\"font-size:22px\">{FORBIDDEN_MESSAGE}</h1>"
                  "<p><a href=\"/dashboard-v7.html\">Về Tổng quan</a></p></body></html>").encode()
