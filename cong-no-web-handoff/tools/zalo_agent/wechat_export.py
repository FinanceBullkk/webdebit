"""WECHAT-01: bộ đọc WeChat chỉ-đọc, chạy như TIẾN TRÌNH CON bằng Python của venv WeChat (không phải venv của repo).

    <venv WeChat>\\python.exe -X utf8 -I wechat_export.py --pilot D:\\deibt\\wechat-mcp-pilot groups
    <venv WeChat>\\python.exe -X utf8 -I wechat_export.py --pilot D:\\deibt\\wechat-mcp-pilot read  < yeu-cau.json
    <venv WeChat>\\python.exe -X utf8 -I wechat_export.py --pilot D:\\deibt\\wechat-mcp-pilot serve  (sống lâu, mỗi dòng stdin một yêu cầu)

`groups` in mỗi nhóm một dòng JSON (`username`, `name`, `members` là số đếm). `read` và `serve` nhận yêu cầu JSON
`{"groups": {"<username>": {"sort_seq": N, "tail": [local_id, …]}}, "first_limit": 5000, "images_dir": null, "window_hours": 6}`
và in JSONL: mỗi tin mới hơn con trỏ (đọc tăng dần theo `sort_seq`, nhiều trang, không giới hạn tổng: thiếu thì chỉ chậm), các
tin trong cửa sổ `window_hours` giờ gần nhất (có cờ `window`, để bắt tin bị sửa tại chỗ như thu hồi), rồi một dòng `end` có số đếm.
`serve` giữ `WeChatDB` mở giữa các yêu cầu (lấy khóa một lần) và mở lại sau lỗi. Chỉ đọc các nhóm trong yêu cầu.

Nội dung được LÀM SẠCH ngay trong tiến trình con: tin tệp/liên kết/hệ thống chỉ ra phần chữ người đọc được (tiêu đề, mô tả,
chữ thông báo), không bao giờ ra XML, URL, khóa CDN hay mã; tiền tố `wxid…:` của tin nhóm bị bỏ. Không in khóa, không đọc
`private-state` trực tiếp: mọi thứ qua `db_adapter.open_database()` của dự án pilot. Lỗi chỉ in mã ngắn. Chỉ dùng stdlib.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path

PAGE = 200
REQUEST_BUDGET = 2000  # tổng số tin MỚI tối đa mỗi yêu cầu, chia đều các nhóm (sàn 100/nhóm): yêu cầu luôn xong trong timeout và
                       # con trỏ luôn tiến; tồn nhiều thì lượt sau đọc tiếp từ con trỏ (chậm, không mất)
WINDOW_CAP = 1000
MAX_BODY = 4000
MAX_CARD = 500
URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.\-]{1,19}://\S*")   # mọi scheme: http, weixin, wxp…
TAG = re.compile(r"<[^>]{0,400}>")
PLACEHOLDER = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_]\w*\$")   # `${name}` và mẫu thật của WeChat `$username$`, `$names$`
PREFIX = re.compile(r"^([A-Za-z0-9][\w@.\-]{2,63}):\n")
USERNAME = re.compile(r"(?:wxid_[A-Za-z0-9]{4,32}|[A-Za-z][A-Za-z0-9_\-]{5,19})")   # dạng username WeChat hợp lệ (id tùy chỉnh 6–20 ký tự)
TRIED: dict = {}                 # người gửi đã làm mới bộ nhớ đệm mà vẫn không tra ra → giờ thử gần nhất (không làm mới lại liền)
RETRY_AFTER = 6 * 3600           # giây
XMLISH = re.compile(r"<\s*/?\s*(?:msg|sysmsg|appmsg|revokemsg)\b", re.IGNORECASE)
REFER = re.compile(r"<refermsg>.*?</refermsg>", re.DOTALL)
REVOKE = re.compile(r"revokemsg|撤回|recalled a message|recalled", re.IGNORECASE)


def open_db(pilot: str):
    sys.path.insert(0, pilot)   # chỉ để import `db_adapter` của pilot; `-I` không tự thêm
    import db_adapter
    return db_adapter.open_database()


def tag(xml: str, name: str) -> str:
    """Chữ trong thẻ `<name>` đầu tiên (hỗ trợ CDATA); chuỗi rỗng nếu không có. Không dùng bộ phân tích XML (tránh bom thực thể)."""
    found = re.search(rf"<{name}>\s*(?:<!\[CDATA\[(.*?)\]\]>|(.*?))\s*</{name}>", xml, re.DOTALL)
    return (found.group(1) if found and found.group(1) is not None else found.group(2) if found else "") or ""


def scrub(text: str) -> str:
    """Bỏ thẻ (kể cả `<_wc_custom_link_ href=…>`, giữ chữ bên trong), URL mọi scheme và chỗ giữ `${…}`; gọn khoảng trắng."""
    text = PLACEHOLDER.sub(" ", URL.sub(" ", TAG.sub(" ", html.unescape(text))))
    return " ".join(text.split())[:MAX_CARD]


def strip_prefix(text: str, sender: str = "", is_self: bool = False) -> str:
    """Bỏ tiền tố `<username>:\n` của tin nhóm NGƯỜI KHÁC gửi. Tin chính chủ không có tiền tố nên không bao giờ bị bỏ (một dòng
    đầu như "KH01:" là chữ thật). Biết người gửi: chỉ bỏ khi tiền tố đúng bằng username đó. Chưa biết người gửi: bỏ khi tiền tố có
    dạng username WeChat hợp lệ (`wxid_…` hay id tùy chỉnh 6–20 ký tự), còn "T10:" hay "Ghi chú:" thì giữ."""
    found = None if is_self else PREFIX.match(text)
    if found and (found.group(1) == sender if sender else USERNAME.fullmatch(found.group(1))):
        return text[found.end():]
    return text


def clean_content(kind, content: str, sender: str = "", is_self: bool = False) -> str:
    """Chỉ phần chữ người đọc được. Loại tin khác ngoài chữ/tệp/hệ thống trả rỗng (bộ xử lý dùng nhãn tiếng Việt)."""
    text = content or ""
    if kind == "文本":
        return strip_prefix(text, sender, is_self)[:MAX_BODY]
    if kind == "文件/链接/卡片":
        xml = REFER.sub("", text)
        parts = [scrub(tag(xml, name)) for name in ("title", "des")]
        return " · ".join(part for part in parts if part)
    if kind == "系统消息":
        if XMLISH.search(text):   # thông báo vào nhóm, "vỗ"…: chữ nằm ở replacemsg hoặc mẫu `template` (bỏ chỗ giữ ${…})
            return scrub(tag(text, "replacemsg") or tag(text, "template"))
        return scrub(text)
    return ""


def is_new(row: dict, cursor: dict | None) -> bool:
    """Mới hơn con trỏ: sort_seq lớn hơn, hoặc bằng nhưng local_id chưa thấy (cùng sort_seq có thể đến muộn)."""
    seq = (cursor or {}).get("sort_seq")
    if not isinstance(seq, int):
        return True
    have = row.get("sort_seq")
    if not isinstance(have, int):
        return False
    return have > seq or (have == seq and row.get("local_id") not in ((cursor or {}).get("tail") or []))


def key(row: dict) -> tuple:
    return (row.get("local_id"), row.get("sort_seq"))


def read_group(db, username: str, cursor: dict | None, first_limit: int, limit: int = REQUEST_BUDGET) -> list[dict]:
    """Tin mới của một nhóm, cũ trước mới sau.

    Có con trỏ: đọc TĂNG DẦN bằng `get_new_messages(since_seq)` của upstream, nhiều trang, tới hết hoặc tới `limit` (lượt sau đọc
    tiếp từ con trỏ), nên tồn bao nhiêu cũng không mất. `since_seq` lùi một để thấy tin cùng `sort_seq` đến muộn; `is_new` lọc phần đã thấy.
    Lần đầu (chưa có con trỏ): `first_limit` tin gần nhất."""
    seq = (cursor or {}).get("sort_seq")
    if not isinstance(seq, int):
        found: list[dict] = []
        offset = 0
        while offset < first_limit:
            take = min(PAGE, first_limit - offset)
            page = db.get_messages(username, limit=take, offset=offset)
            found += page
            if len(page) < take:
                break
            offset += len(page)
        return list(reversed(found))
    out: list[dict] = []
    seen: set = set()
    since = seq - 1
    while len(out) < limit:
        page = db.get_new_messages(username, since_seq=since, limit=PAGE)
        for row in page:
            if is_new(row, cursor) and key(row) not in seen:
                seen.add(key(row))
                out.append(row)
        if len(page) < PAGE:
            break
        last = page[-1].get("sort_seq")
        if not isinstance(last, int):
            break
        since = last - 1 if last - 1 > since else last   # tiến ít nhất một; cả trang cùng sort_seq thì bỏ phần dư đồng seq
    return out[:limit]   # cắt đúng ngân sách: con trỏ theo tin cuối đã phát, phần còn lại (kể cả cùng sort_seq) là "mới" ở lượt sau


def read_window(db, username: str, hours: float, now: float) -> list[dict]:
    """Tin trong `hours` giờ gần nhất (cũ trước mới sau): để thấy tin bị sửa tại chỗ (thu hồi biến dòng cũ thành tin hệ thống)."""
    cutoff, rows, offset = now - hours * 3600, [], 0
    while offset < WINDOW_CAP:
        page = db.get_messages(username, limit=PAGE, offset=offset)
        rows += [row for row in page if isinstance(row.get("create_time"), int) and row["create_time"] >= cutoff]
        if len(page) < PAGE or all(isinstance(row.get("create_time"), int) and row["create_time"] < cutoff for row in page):
            break
        offset += len(page)
    return list(reversed(rows))


def image_tools(db):
    """(MediaDownloader, aes, xor) khi khóa ảnh suy ra được hoàn toàn ngoại tuyến từ cấu hình WeChat, ngược lại None.

    PR này chưa giải mã ảnh (PR-W2 sẽ dùng khóa lấy từ bộ nhớ Weixin.exe, người dùng đã cho phép 20/11/2026): chỉ chạy khi yêu cầu
    có `images_dir`, mặc định tắt."""
    try:
        import importlib
        media = importlib.import_module("wechatauto.media")   # `db_adapter` đã đăng ký gói `wechatauto` trong sys.modules
        downloader = media.MediaDownloader(db)
        derived = downloader._derive_cfg_key()
    except Exception:   # noqa: BLE001  (thiếu thư viện, thiếu khóa…: không có ảnh, vẫn đọc chữ)
        return None
    return (downloader, derived[0], derived[1]) if derived else None


def export_image(tools, username: str, local_id: int, directory: str) -> str | None:
    """Giải mã ảnh `.dat` của một tin ra `directory`; trả tên file hoặc None. Chỉ đọc file cục bộ, không đụng giao diện WeChat."""
    downloader, aes, xor = tools
    try:
        path = downloader.download_image(username, local_id, save_dir=directory, aes_key=aes, xor_key=xor, tier="best")
    except Exception:   # noqa: BLE001
        return None
    return Path(path).name if path else None


def fingerprint(item: dict) -> str:
    """Dấu vân tay của một bản ghi đầu ra (loại, chữ đã làm sạch, người gửi và tên, cờ thu hồi): cửa sổ đọc lại chỉ cần so cái này;
    đổi biệt danh làm dòng được gửi lại để `users.json` cập nhật."""
    text = json.dumps([item.get("type"), item.get("content"), item.get("sender"), item.get("sender_name"), bool(item.get("revoked"))],
                      ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:16]


def stale_key(row: dict, nicks: dict):
    """Khóa người gửi chưa tra được (thành viên mới vào sau khi tiến trình mở DB, bộ nhớ đệm của upstream cũ), hoặc None."""
    if row.get("sender_id") == 2 or row.get("type") == "系统消息":
        return None
    if not row.get("sender_username"):
        return ("id", row.get("sender_id"))
    return None if row["sender_username"] in nicks else ("name", row["sender_username"])


def refresh(db, current: dict) -> dict:
    """Đặt lại bộ nhớ đệm người gửi và biệt danh của upstream rồi trả bảng biệt danh mới. Lỗi làm mới thì giữ bảng cũ: tuyệt đối
    không để lỗi này làm `serve` bỏ DB (mở lại DB là upstream quét bộ nhớ Weixin.exe lần nữa)."""
    with contextlib.suppress(Exception):
        db._sender_id_cache = None
    try:
        return db.nickname_map(refresh=True)
    except TypeError:
        with contextlib.suppress(Exception):
            return db.nickname_map()
    except Exception:   # noqa: BLE001
        pass
    return current


def record(nicks: dict, username: str, row: dict, tools, images_dir: str | None, window: bool = False) -> dict:
    sender = row.get("sender_username") or ""
    is_self = row.get("sender_id") == 2
    kind = row.get("type")
    raw = row.get("content") if isinstance(row.get("content"), str) else ""
    out = {"kind": "message", "username": username, "local_id": row.get("local_id"), "sort_seq": row.get("sort_seq"),
           "create_time": row.get("create_time"), "type": kind, "is_self": is_self,
           "sender": "" if is_self else sender, "sender_name": "" if is_self else (nicks.get(sender) or ""),   # không bao giờ wxid thô
           "content": clean_content(kind, raw, sender, is_self), "image": None}
    if window:
        out["window"] = True
    if kind == "系统消息" and REVOKE.search(raw):
        out["revoked"] = True   # chỉ cờ; chữ gốc không ra ngoài
    if tools and images_dir and kind == "图片" and isinstance(row.get("local_id"), int):
        out["image"] = export_image(tools, username, row["local_id"], images_dir)
    out["fp"] = fingerprint(out)
    return out


def emit(value: dict) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def cmd_groups(db) -> int:
    for group in db.get_groups():
        emit({"kind": "group", "username": group["username"], "name": group["name"], "members": len(group.get("members") or [])})
    return 0


def cmd_read(db, request: dict) -> int:
    groups = request.get("groups") if isinstance(request.get("groups"), dict) else {}
    known = {group["username"] for group in db.get_groups()}
    first = request.get("first_limit") if isinstance(request.get("first_limit"), int) else 5000
    hours = request.get("window_hours") if isinstance(request.get("window_hours"), int | float) else 0
    images_dir = request.get("images_dir") if isinstance(request.get("images_dir"), str) else None
    sent = request.get("known_fp") if isinstance(request.get("known_fp"), dict) else {}   # {username: {"local_id:sort_seq": fp}}
    nicks = db.nickname_map()
    tools = image_tools(db) if images_dir else None
    counts = {"messages": 0, "images": 0, "missing_groups": 0, "window": 0, "window_same": 0}
    present = [username for username, _ in sorted(groups.items()) if username in known]
    counts["missing_groups"] = len(groups) - len(present)
    quota = max(100, REQUEST_BUDGET // max(1, len(present)))   # chia ngân sách tin mới cho các nhóm: mọi yêu cầu đều tiến
    refreshed = False
    for username in present:
        have = groups[username] if isinstance(groups[username], dict) else None
        # Lần đầu cũng nằm trong ngân sách: chỉ lấy tin gần nhất (tối đa min(first_limit, quota)); phần cũ hơn BỎ có chủ đích, không đọc dần.
        limit = quota if (have or {}).get("sort_seq") else min(first, quota)
        for attempt in (0, 1):
            fresh = read_group(db, username, have, limit, quota)
            seen = {key(row) for row in fresh}
            late = read_window(db, username, hours, time.time()) if hours > 0 and (have or {}).get("sort_seq") else []
            late = [row for row in late if key(row) not in seen]
            # Chỉ tin MỚI mới đáng làm mới bộ nhớ đệm; người gửi đã thử mà vẫn không ra (đã rời nhóm…) thì không thử lại trong 6 giờ.
            missing = {k for k in (stale_key(row, nicks) for row in fresh) if k is not None and time.time() - TRIED.get(k, 0) > RETRY_AFTER}
            if attempt == 0 and not refreshed and missing:
                nicks, refreshed = refresh(db, nicks), True   # người mới vào nhóm: đọc lại với bộ nhớ đệm người gửi mới
                continue
            if refreshed:
                for row in fresh:
                    k = stale_key(row, nicks)
                    if k is not None:
                        TRIED[k] = time.time()
            break
        for row in fresh:
            item = record(nicks, username, row, tools, images_dir)
            counts["messages"] += 1
            counts["images"] += bool(item["image"])
            emit(item)
        for row in late:
            item = record(nicks, username, row, None, None, window=True)
            if (sent.get(username) or {}).get(f"{item['local_id']}:{item['sort_seq']}") == item["fp"]:
                counts["window_same"] += 1   # đã có đúng bản này: không gửi lại nội dung qua ống
                continue
            counts["window"] += 1
            emit(item)
    emit({"kind": "end", **counts, "image_keys": bool(tools)})
    return 0


def serve(pilot: str) -> int:
    """Tiến trình sống lâu: mỗi dòng stdin là một yêu cầu `read`; thoát khi stdin đóng. Lỗi thì quên DB để lượt sau mở lại."""
    db = None
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            db = db or open_db(pilot)
            cmd_read(db, request if isinstance(request, dict) else {})
        except Exception as exc:   # noqa: BLE001  (chỉ mã ngắn ra ngoài)
            db = None
            emit({"kind": "error", "code": type(exc).__name__[:40]})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wechat_export")
    parser.add_argument("--pilot", required=True, help="thư mục dự án wechat-mcp-pilot (có db_adapter.py)")
    parser.add_argument("command", choices=("groups", "read", "serve"))
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args.pilot)
    try:
        request = json.loads(sys.stdin.read() or "{}") if args.command == "read" else {}
        db = open_db(args.pilot)
        return cmd_groups(db) if args.command == "groups" else cmd_read(db, request)
    except Exception as exc:   # noqa: BLE001  (chỉ mã ngắn ra ngoài: chữ lỗi có thể chứa đường dẫn hay nội dung)
        emit({"kind": "error", "code": type(exc).__name__[:40]})
        return 2


if __name__ == "__main__":
    sys.exit(main())
