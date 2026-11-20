"""WECHAT-01: bộ đọc WeChat chỉ-đọc, chạy như TIẾN TRÌNH CON bằng Python của venv WeChat (không phải venv của repo).

    <venv WeChat>\\python.exe -X utf8 -I wechat_export.py --pilot D:\\deibt\\wechat-mcp-pilot groups
    <venv WeChat>\\python.exe -X utf8 -I wechat_export.py --pilot D:\\deibt\\wechat-mcp-pilot read < yeu-cau.json

`groups` in mỗi nhóm một dòng JSON (`username`, `name`, `members` là số đếm). `read` đọc yêu cầu JSON từ stdin
`{"groups": {"<username>": {"sort_seq": N, "tail": [local_id, …]}}, "first_limit": 5000, "images_dir": null}` và in JSONL:
mỗi tin mới hơn con trỏ, rồi một dòng `end` có số đếm. Chỉ đọc các nhóm trong `groups`; nhóm nào không có trong yêu cầu thì không
đụng tới. Không in khóa, không đọc `private-state` trực tiếp: mọi thứ qua `db_adapter.open_database()` của dự án pilot.
Lỗi chỉ in mã ngắn (`error`), không in chữ lỗi hay đường dẫn. Module chỉ dùng stdlib để test import được ở venv của repo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PAGE = 100
CATCHUP = 2000        # mỗi lượt đọc tối đa số tin này cho một nhóm đã có con trỏ
MAX_BODY = 4000


def open_db(pilot: str):
    sys.path.insert(0, pilot)   # chỉ để import `db_adapter` của pilot; `-I` không tự thêm
    import db_adapter
    return db_adapter.open_database()


def is_new(row: dict, cursor: dict | None) -> bool:
    """Mới hơn con trỏ: sort_seq lớn hơn, hoặc bằng nhưng local_id chưa thấy (cùng sort_seq có thể đến muộn)."""
    seq = (cursor or {}).get("sort_seq")
    if not isinstance(seq, int):
        return True
    have = row.get("sort_seq")
    if not isinstance(have, int):
        return False
    return have > seq or (have == seq and row.get("local_id") not in ((cursor or {}).get("tail") or []))


def read_group(db, username: str, cursor: dict | None, first_limit: int) -> list[dict]:
    """Tin mới của một nhóm, cũ trước mới sau. `get_messages` trả mới trước cũ: đọc từng trang tới khi gặp tin không còn mới."""
    cap = first_limit if not (cursor or {}).get("sort_seq") else CATCHUP
    found: list[dict] = []
    offset = 0
    while offset < cap:
        take = min(PAGE, cap - offset)
        page = db.get_messages(username, limit=take, offset=offset)
        for row in page:
            if is_new(row, cursor):
                found.append(row)
            elif isinstance((cursor or {}).get("sort_seq"), int) and isinstance(row.get("sort_seq"), int) and row["sort_seq"] < cursor["sort_seq"]:
                return list(reversed(found))
        if len(page) < take:
            break
        offset += len(page)
    return list(reversed(found))


def image_tools(db):
    """(MediaDownloader, aes, xor) khi khóa ảnh suy ra được hoàn toàn ngoại tuyến từ cấu hình WeChat, ngược lại None.

    Cố ý KHÔNG gọi nhánh quét bộ nhớ tiến trình Weixin.exe của upstream (`detect_image_key`, `_scan_aes_key`) và không truyền khóa
    nào khác: không suy ra được thì ảnh để "chưa đọc được", không cố."""
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


def record(db, nicks: dict, username: str, row: dict, tools, images_dir: str | None) -> dict:
    sender = row.get("sender_username") or ""
    is_self = row.get("sender_id") == 2
    content = row.get("content")
    out = {"kind": "message", "username": username, "local_id": row.get("local_id"), "sort_seq": row.get("sort_seq"),
           "create_time": row.get("create_time"), "type": row.get("type"), "is_self": is_self,
           "sender": "" if is_self else sender, "sender_name": "" if is_self else (nicks.get(sender) or sender),
           "content": content[:MAX_BODY] if isinstance(content, str) else "", "image": None}
    if tools and images_dir and row.get("type") == "图片" and isinstance(row.get("local_id"), int):
        out["image"] = export_image(tools, username, row["local_id"], images_dir)
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
    images_dir = request.get("images_dir") if isinstance(request.get("images_dir"), str) else None
    nicks = db.nickname_map()
    tools = image_tools(db) if images_dir else None
    counts = {"messages": 0, "images": 0, "missing_groups": 0}
    for username, cursor in sorted(groups.items()):
        if username not in known:
            counts["missing_groups"] += 1
            continue
        for row in read_group(db, username, cursor if isinstance(cursor, dict) else None, first):
            item = record(db, nicks, username, row, tools, images_dir)
            counts["messages"] += 1
            counts["images"] += bool(item["image"])
            emit(item)
    emit({"kind": "end", **counts, "image_keys": bool(tools)})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wechat_export")
    parser.add_argument("--pilot", required=True, help="thư mục dự án wechat-mcp-pilot (có db_adapter.py)")
    parser.add_argument("command", choices=("groups", "read"))
    args = parser.parse_args(argv)
    try:
        request = json.loads(sys.stdin.read() or "{}") if args.command == "read" else {}
        db = open_db(args.pilot)
        return cmd_groups(db) if args.command == "groups" else cmd_read(db, request)
    except Exception as exc:   # noqa: BLE001  (chỉ mã ngắn ra ngoài: chữ lỗi có thể chứa đường dẫn hay nội dung)
        emit({"kind": "error", "code": type(exc).__name__[:40]})
        return 2


if __name__ == "__main__":
    sys.exit(main())
