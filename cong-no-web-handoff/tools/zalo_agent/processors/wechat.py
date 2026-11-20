"""WECHAT-01: nguồn WeChat của zalo-agent (hợp đồng dữ liệu trong specs/zalo-agent.md, mục "Nguồn WeChat").

Bộ xử lý `wechat` gọi bộ đọc chỉ-đọc `wechat_export.py` (tiến trình con, Python của venv WeChat) theo nhịp, đổi tin sang ĐÚNG
khuôn dòng tin của gói chat rồi nối vào kho cục bộ `<root>/wechat/log.jsonl`. Bộ xử lý `bundle` nhận kho đó làm "overlay":
dựng đầy đủ thì gộp nhóm, người gửi, tin và ảnh WeChat vào thư mục dữ liệu mới; giữa hai lần dựng thì nối tin mới vào
`messages-delta.jsonl` như tin Zalo. `hao` không phải sửa gì: nhóm WeChat là một hội thoại bình thường trong gói
(`conversation_id` = sha256 hex của `wechat:<username>`, nhãn "WeChat · <tên>").

Tiến trình con chạy trong luồng nền để chậm hay treo (timeout 60 giây) không giữ vòng lặp của `bundle`. Lỗi con lùi dần riêng
(`interval` nhân đôi tới 15 phút). Chỉ nhóm trong `wechat-groups.json` được đọc; không chữ tin nào đi vào model.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import zalo_web_bundle as wb

from .. import cursor as cursors
from ..source import read_json, retry_io

NAME = "wechat"
SCRIPT = Path(__file__).resolve().parents[1] / "wechat_export.py"
INTERVAL, MAX_BACKOFF, TIMEOUT = 10, 15 * 60, 60
SELF_NAME = "Tôi (WeChat)"
# local_type của WeChat 4.x (tên do upstream đặt) → message_type của gói Zalo (TYPE_NAMES trong web/v7_zalo_chat.py).
KINDS = {"文本": 1, "图片": 2, "文件/链接/卡片": 19, "系统消息": -4, "语音": 3, "视频": 18, "位置": 17, "动画表情": 4,
         "音视频通话": 6, "红包": 19}
LABELS = {"图片": "Ảnh WeChat (chưa đọc được)", "语音": "[Ghi âm WeChat]", "视频": "[Video WeChat]", "位置": "[Vị trí WeChat]",
          "动画表情": "[Biểu tượng WeChat]", "音视频通话": "[Cuộc gọi WeChat]", "红包": "[Lì xì WeChat]"}
UNKNOWN_LABEL = "[Tin WeChat loại lạ]"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def conversation_id(username: str) -> str:
    return sha("wechat:" + username)


def message_id(username: str, local_id: int, sort_seq: int) -> str:
    # `local_id` của WeChat 4.x lặp lại giữa các phân mảnh DB (upstream ghi rõ), nên thêm `sort_seq` để hai tin không trùng mã.
    return sha(f"wechat:{username}:{local_id}:{sort_seq}")


def sender_id(wxid: str) -> str:
    return sha("wechat:sender:" + wxid)[:32]


SELF_ID = sha("wechat:self")[:32]


def convert(item: dict, image: str | None = None) -> tuple[dict, tuple[str, str] | None] | None:
    """Một dòng JSON của bộ đọc → (dòng tin của gói, (mã người gửi, tên) hoặc None). Dòng sai khuôn thì None."""
    username, local_id, seq, stamp = item.get("username"), item.get("local_id"), item.get("sort_seq"), item.get("create_time")
    if not (isinstance(username, str) and all(isinstance(value, int) and not isinstance(value, bool) for value in (local_id, seq, stamp))):
        return None
    kind = item.get("type")
    content = item.get("content") if isinstance(item.get("content"), str) else ""
    mtype = KINDS.get(kind, 19) if isinstance(kind, str) else 19
    if kind == "图片":
        body = "Ảnh WeChat" if image else LABELS[kind]
    elif kind in ("文本", "文件/链接/卡片", "系统消息"):
        body = content.strip() or UNKNOWN_LABEL
    else:
        body = LABELS.get(kind, UNKNOWN_LABEL) if isinstance(kind, str) else UNKNOWN_LABEL
    own = bool(item.get("is_self"))
    wxid = item.get("sender") if isinstance(item.get("sender"), str) else ""
    sid = SELF_ID if own else sender_id(wxid) if wxid else None
    name = SELF_NAME if own else (item.get("sender_name") or wxid) if wxid else None
    millis = str(stamp * 1000)
    row = {"message_id": message_id(username, local_id, seq), "conversation_id": conversation_id(username), "sender_id": sid,
           "timestamp": millis, "server_time": millis, "message_type": mtype, "status": 2 if own else 4, "body_state": None,
           "body": body}
    return row, ((sid, str(name)) if sid and name else None)


class Selection:
    """`wechat-groups.json`: {"schema": 1, "groups": [{"username": "…@chatroom", "name": "…"}]}, ngoài repo, chỉ nhóm người dùng chọn."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def groups(self) -> dict[str, str]:
        document = read_json(self.path, {}) or {}
        return {g["username"]: g.get("name") or "" for g in document.get("groups", [])
                if isinstance(g, dict) and isinstance(g.get("username"), str) and g["username"].endswith("@chatroom")}

    def save(self, groups: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}")
        tmp.write_bytes(wb.dump({"schema": 1, "groups": [{"username": u, "name": n} for u, n in sorted(groups.items())]}))
        retry_io(lambda: os.replace(tmp, self.path))


class Store:
    """Kho cục bộ `<root>/wechat/`: `log.jsonl` (chỉ nối thêm, bản cuối của mỗi mã tin thắng), `users.json`, `media.json`, `media/`."""

    def __init__(self, root: Path, selection: Selection):
        self.dir, self.selection = Path(root), selection
        self.log, self.users_path, self.media_path = self.dir / "log.jsonl", self.dir / "users.json", self.dir / "media.json"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "media").mkdir(exist_ok=True)
        if self.log.is_file():   # lượt chết giữa chừng có thể để dòng dở: cắt về dòng trọn cuối cùng
            data = self.log.read_bytes()
            if data and not data.endswith(b"\n"):
                with self.log.open("r+b") as stream:
                    stream.truncate(data.rfind(b"\n") + 1)

    def conversation_ids(self) -> list[str]:
        return sorted(conversation_id(username) for username in self.selection.groups())

    def size(self) -> int:
        return self.log.stat().st_size if self.log.is_file() else 0

    def append(self, rows: list[dict], users: dict[str, str], media: dict[str, dict]) -> None:
        if media:
            known = read_json(self.media_path, {}) or {}
            wb.write_atomic(self.media_path, wb.dump({**known, **media}))
        if users:
            known = read_json(self.users_path, {}) or {}
            wb.write_atomic(self.users_path, wb.dump({**known, **users}))
        if rows:
            with self.log.open("ab") as stream:
                stream.write(b"".join(wb.dump(row) + b"\n" for row in rows))
                stream.flush()
                os.fsync(stream.fileno())

    def store_image(self, data: bytes) -> tuple[str, dict] | None:
        mime = wb.sniff(data)
        if mime not in wb.EXTENSIONS:
            return None
        digest = hashlib.sha256(data).hexdigest()
        target = self.dir / "media" / (digest + wb.EXTENSIONS[mime])
        if not target.is_file():
            wb.write_atomic(target, data)
        return digest, {"mime": mime, "bytes": len(data), "width": None, "height": None}

    def rows_after(self, offset: int) -> tuple[list[dict], int]:
        """Tin của nhóm đang chọn nằm sau `offset` (bản cuối của mỗi mã tin thắng) và vị trí mới. Nhóm đã bỏ chọn không lọt."""
        if not self.log.is_file():
            return [], 0
        with self.log.open("rb") as stream:
            stream.seek(offset)
            data = stream.read()
        data = data[:data.rfind(b"\n") + 1]
        chosen = set(self.conversation_ids())
        latest: dict[str, dict] = {}
        for raw in data.splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("conversation_id") in chosen and isinstance(row.get("message_id"), str):
                latest[row["message_id"]] = row
        return list(latest.values()), offset + len(data)

    def users_for(self, rows: list[dict]) -> dict[str, str]:
        known = read_json(self.users_path, {}) or {}
        return {row["sender_id"]: known[row["sender_id"]] for row in rows if row.get("sender_id") in known}

    def media_for(self, rows: list[dict], out: Path) -> dict[str, dict]:
        """Chép ảnh của các dòng vào `out/media` (nếu thiếu) và trả mục `media.json` của chúng."""
        known = read_json(self.media_path, {}) or {}
        items = {}
        (out / "media").mkdir(parents=True, exist_ok=True)
        for row in rows:
            for digest in row.get("media") or []:
                item = known.get(digest)
                if not item:
                    continue
                name = digest + wb.EXTENSIONS[item["mime"]]
                if not (out / "media" / name).is_file() and (self.dir / "media" / name).is_file():
                    wb.write_atomic(out / "media" / name, (self.dir / "media" / name).read_bytes())
                items[digest] = item
        return items

    def merge_into(self, data_dir: Path, out: Path) -> dict:
        """Dựng đầy đủ xong: thêm nhóm, người gửi, tin và ảnh WeChat vào thư mục dữ liệu mới, tính lại `bundle_sha256`."""
        rows, offset = self.rows_after(0)
        groups = self.selection.groups()
        count = dict.fromkeys(self.conversation_ids(), 0)
        for row in rows:
            count[row["conversation_id"]] += 1
        conversations = read_json(data_dir / "conversations.json", []) or []
        have = {c.get("conversation_id") for c in conversations if isinstance(c, dict)}
        extra = [{"conversation_id": conversation_id(u), "display_name": f"WeChat · {name or u[:8]}", "name_status": "name_index",
                  "is_group": True, "participant_ids": [], "message_count": count[conversation_id(u)]}
                 for u, name in sorted(groups.items()) if conversation_id(u) not in have]
        users = read_json(data_dir / "users.json", {"self_user": None, "users": {}}) or {}
        users["users"] = {**(users.get("users") or {}), **self.users_for(rows)}
        media = read_json(data_dir / "media.json", {}) or {}
        media.update(self.media_for(rows, out))
        wb.write_atomic(data_dir / "conversations.json", wb.dump(conversations + extra))
        wb.write_atomic(data_dir / "users.json", wb.dump(users))
        wb.write_atomic(data_dir / "media.json", wb.dump(media))
        if rows:
            with (data_dir / "messages.jsonl").open("ab") as stream:
                stream.write(b"".join(wb.dump(row) + b"\n" for row in rows))
        digest = hashlib.sha256()
        for name in ("conversations.json", "users.json", "messages.jsonl", "media.json"):
            digest.update((data_dir / name).read_bytes())
        return {"bytes": offset, "messages": len(rows), "conversations": len(extra), "media": len(media), "sha256": digest.hexdigest()}


def run_child(python: str, pilot: str, command: str, request: dict, timeout: float = TIMEOUT, script: Path = SCRIPT) -> tuple[int, str]:
    done = subprocess.run([python, "-X", "utf8", "-I", str(script), "--pilot", pilot, command], input=json.dumps(request).encode(),
                          capture_output=True, timeout=timeout, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return done.returncode, done.stdout.decode("utf-8", "replace")


def parse(output: str) -> list[dict]:
    items = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


class WeChatProcessor:
    name = NAME

    def __init__(self, store: Store, state: Path, *, python: str, pilot: str, interval: float = INTERVAL, first_limit: int = 5000,
                 images: bool = False, run=run_child, clock=time.time, dry_run: bool = False, background: bool = True):
        self.store, self.state, self.python, self.pilot = store, Path(state), python, pilot
        self.interval, self.first_limit, self.images = interval, first_limit, images
        self.run, self.clock, self.dry_run, self.background = run, clock, dry_run, background
        saved = read_json(self.state / f"{NAME}.json", {}) or {}
        self.cursors: dict = saved.get("groups") if isinstance(saved.get("groups"), dict) else {}
        self.total = saved.get("messages") if isinstance(saved.get("messages"), int) else 0
        self.next_at = 0.0
        self.failures = 0
        self.thread: threading.Thread | None = None
        self.outcome: tuple[str | None, list[dict], dict] | None = None
        self.last = {"action": "idle", "revision": None, "error": None, "messages": self.total}

    def wants_work(self) -> bool:
        return False   # đọc theo nhịp riêng, không giữ vòng lặp gom 3 giây của bundle; `bundle` tự thấy log dài ra

    def request(self, groups: dict[str, str]) -> dict:
        images = str(self.store.dir / "incoming") if self.images else None
        if images:
            Path(images).mkdir(exist_ok=True)
        return {"groups": {u: self.cursors.get(u) or {} for u in groups}, "first_limit": self.first_limit, "images_dir": images}

    def poll(self, groups: dict[str, str]) -> tuple[str | None, list[dict], dict]:
        """Chạy tiến trình con (có thể ở luồng nền). Trả (mã lỗi, các dòng tin, dòng `end`)."""
        try:
            code, output = self.run(self.python, self.pilot, "read", self.request(groups))
        except subprocess.TimeoutExpired:
            return "child_timeout", [], {}
        except OSError:
            return "child_missing", [], {}
        items = parse(output)
        end = next((item for item in items if item.get("kind") == "end"), None)
        if code != 0 or end is None:
            return ("child_failed" if code != 0 else "child_output"), [], {}
        return None, [item for item in items if item.get("kind") == "message" and item.get("username") in groups], end

    def work(self, groups: dict[str, str]) -> None:
        self.outcome = self.poll(groups)

    def step(self) -> dict:
        groups = self.store.selection.groups()
        if self.outcome is not None:
            error, items, end = self.outcome
            self.outcome, self.thread = None, None
            self.apply(error, items, end, groups)
        elif self.thread is None and groups and self.clock() >= self.next_at:
            self.next_at = self.clock() + self.interval
            if self.background:
                self.thread = threading.Thread(target=self.work, args=(groups,), daemon=True, name="wechat-export")
                self.thread.start()
            else:
                self.work(groups)
                return self.step()
        result = self.last
        self.last = {**result, "action": "idle"}   # kết quả một lần: vòng lặp gọi step mỗi giây, đừng ghi log "poll" mãi
        return result

    def apply(self, error: str | None, items: list[dict], end: dict, groups: dict[str, str]) -> None:
        now = self.clock()
        if error is None:
            try:
                error = self.ingest(items, groups)
            except OSError:
                error = "store_failed"
        self.failures = self.failures + 1 if error else 0
        if error:
            self.next_at = now + min(MAX_BACKOFF, self.interval * 2 ** self.failures)
        self.last = {"action": "idle" if error or not items else "poll", "revision": None, "error": error, "messages": self.total}

    def ingest(self, items: list[dict], groups: dict[str, str]) -> str | None:
        rows, users, media, moved = [], {}, {}, {}
        for item in items:
            image = None
            if item.get("image") and self.images:
                image = self.read_image(item["image"])
                if image:
                    media[image[0]] = image[1]
            converted = convert(item, image[0] if image else None)
            if converted is None:
                continue
            row, user = converted
            if image:
                row["media"] = [image[0]]
            rows.append(row)
            if user:
                users[user[0]] = user[1]
            username, seq, local_id = item["username"], item["sort_seq"], item["local_id"]
            old = moved.get(username) or self.cursors.get(username) or {}
            tail = (old.get("tail") or []) if old.get("sort_seq") == seq else []
            if not isinstance(old.get("sort_seq"), int) or seq >= old["sort_seq"]:
                moved[username] = {"sort_seq": seq, "tail": [*tail, local_id]}
        self.store.append(rows, users, media)
        self.cursors = {**{u: c for u, c in self.cursors.items() if u in groups}, **moved}
        self.total += len(rows)
        if not self.dry_run:
            cursors.save(self.state, NAME, {"groups": self.cursors, "messages": self.total}, self.clock())
        return None

    def read_image(self, name: str) -> tuple[str, dict] | None:
        path = self.store.dir / "incoming" / Path(name).name
        try:
            data = path.read_bytes()
            path.unlink(missing_ok=True)
        except OSError:
            return None
        return self.store.store_image(data)


# ---- lệnh chọn nhóm: `zalo_agent wechat-list | wechat-add <tên> | wechat-remove <tên>` ----

def list_groups(python: str, pilot: str, run=run_child) -> list[dict]:
    code, output = run(python, pilot, "groups", {}, 120)
    if code != 0:
        raise RuntimeError("không đọc được danh sách nhóm WeChat (bộ đọc lỗi)")
    return [item for item in parse(output) if item.get("kind") == "group" and isinstance(item.get("username"), str)]


def find(groups: list[dict], needle: str) -> list[dict]:
    needle = needle.strip()
    fold = wb.fold
    exact = [g for g in groups if fold(g.get("name") or "") == fold(needle)]
    return exact or [g for g in groups if fold(needle) in fold(g.get("name") or "") or conversation_id(g["username"]).startswith(needle)]


def cmd_list(selection: Selection, python: str, pilot: str, run=run_child) -> int:
    chosen = selection.groups()
    for group in list_groups(python, pilot, run):
        mark = "[x]" if group["username"] in chosen else "[ ]"
        print(f"{mark} {conversation_id(group['username'])[:8]}  {group.get('members', 0):>4} người  {group.get('name') or 'chưa rõ tên'}")
    print(f"\n{len(chosen)} nhóm WeChat đang được lên web.")
    return 0


def cmd_change(selection: Selection, needles: list[str], add: bool, python: str, pilot: str, run=run_child) -> int:
    chosen = selection.groups()
    pool = list_groups(python, pilot, run) if add else [{"username": u, "name": n} for u, n in chosen.items()]
    for needle in needles:
        matches = find(pool, needle)
        if len(matches) != 1:
            print(f"“{needle}”: {'không thấy nhóm nào' if not matches else f'{len(matches)} nhóm khớp, ghi rõ hơn (8 ký tự đầu mã)'}")
            for group in matches[:10]:
                print(f"    {conversation_id(group['username'])[:8]}  {group.get('name') or 'chưa rõ tên'}")
            return 1
        group = matches[0]
        if add:
            chosen[group["username"]] = group.get("name") or ""
        else:
            chosen.pop(group["username"], None)
        print(f"{'Thêm' if add else 'Bỏ'}: {conversation_id(group['username'])[:8]}  {group.get('name') or 'chưa rõ tên'}")
    selection.save(chosen)
    return 0


def add_arguments(parser) -> None:
    parser.add_argument("--wechat-python", default=os.environ.get("ZALO_WECHAT_PYTHON", r"D:\deibt\wechat-mcp-pilot\.venv\Scripts\python.exe"))
    parser.add_argument("--wechat-pilot", default=os.environ.get("ZALO_WECHAT_PILOT", r"D:\deibt\wechat-mcp-pilot"))
    parser.add_argument("--wechat-groups", default=os.environ.get("ZALO_WECHAT_GROUPS", r"D:\zalo-agent\wechat-groups.json"))


def main_command(args) -> int:
    for stream in (sys.stdout, sys.stderr):   # tên nhóm có chữ Hán: đầu ra qua pipe Windows mặc định cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    selection = Selection(Path(args.wechat_groups))
    try:
        if args.command == "wechat-list":
            return cmd_list(selection, args.wechat_python, args.wechat_pilot)
        return cmd_change(selection, args.needles, args.command == "wechat-add", args.wechat_python, args.wechat_pilot)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
