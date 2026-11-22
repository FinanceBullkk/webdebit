"""WECHAT-01: bộ đọc WeChat chỉ-đọc, chạy như TIẾN TRÌNH CON bằng Python của venv WeChat (không phải venv của repo).

    <venv WeChat>\\python.exe -X utf8 -I wechat_export.py --pilot D:\\deibt\\wechat-mcp-pilot groups
    <venv WeChat>\\python.exe -X utf8 -I wechat_export.py --pilot D:\\deibt\\wechat-mcp-pilot read  < yeu-cau.json
    <venv WeChat>\\python.exe -X utf8 -I wechat_export.py --pilot D:\\deibt\\wechat-mcp-pilot serve  (sống lâu, mỗi dòng stdin một yêu cầu)

`groups` in mỗi nhóm một dòng JSON (`username`, `name`, `members` là số đếm). `read` và `serve` nhận yêu cầu JSON
`{"groups": {"<username>": {"sort_seq": N, "tail": [local_id, …]}}, "first_limit": 5000, "images_dir": null, "window_hours": 6,
"deep_image_hours": 0, "known_fp": {}}` và in JSONL: mỗi tin mới hơn con trỏ (đọc tăng dần theo `sort_seq`, nhiều trang, không giới
hạn tổng: thiếu thì chỉ chậm), các tin trong cửa sổ `window_hours` giờ gần nhất (có cờ `window`, để bắt tin bị sửa tại chỗ như thu
hồi), thêm tối đa `DEEP_IMAGE_BUDGET` tin ẢNH mới nhất trong `deep_image_hours` giờ (cờ `deep`: lượt thử lại ảnh), rồi một dòng
`end` có số đếm. Tin ảnh trong cửa sổ mà bộ xử lý chưa có (`fp` không nằm trong `known_fp`) được giải ảnh lại khi có khóa.
`serve` giữ `WeChatDB` mở giữa các yêu cầu (lấy khóa một lần) và mở lại sau lỗi. Chỉ đọc các nhóm trong yêu cầu.

Nội dung được LÀM SẠCH ngay trong tiến trình con: tin tệp/liên kết/hệ thống chỉ ra phần chữ người đọc được (tiêu đề, mô tả,
chữ thông báo), không bao giờ ra XML, URL, khóa CDN hay mã; tiền tố `wxid…:` của tin nhóm bị bỏ. Không in khóa, không đọc
`private-state` trực tiếp: tin và ảnh qua `db_adapter.open_database()` của dự án pilot; riêng khóa ảnh suy từ TÊN file trong
thư mục `kvcomm` của WeChat và vài chục byte đầu/cuối của file `.dat` (xem `offline_image_key`). Lỗi chỉ in mã ngắn. Chỉ dùng stdlib.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from zalo_agent import wechat_dat as dat  # test và agent nạp như gói
except ImportError:   # tiến trình con chạy file này bằng `-I` (thư mục của script không vào sys.path): nạp file kề bên theo đường dẫn
    import importlib.util
    _spec = importlib.util.spec_from_file_location("zalo_agent_wechat_dat", Path(__file__).with_name("wechat_dat.py"))
    dat = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(dat)

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
KVCOMM = re.compile(r"key_(\d+)_.*\.statistic")
SAMPLES = 24        # số file `.dat` V2 dùng để thử khóa ảnh (mỗi file chỉ đọc 31 byte đầu và 16 byte cuối)
KEYS: dict = {}     # (tài khoản, wxid) → (mã kvcomm, khóa AES, byte XOR) đã kiểm đúng; chỉ trong bộ nhớ, `serve` sống lâu nên không kiểm lại
MISSES: dict = {}   # (tài khoản, wxid, tập mã) → giờ thử hụt (monotonic): không quét lại thư mục ảnh mỗi 10 giây khi chưa suy được khóa
MISS_RETRY = 600    # giây; có mã kvcomm mới thì thử ngay
DEEP_IMAGE_BUDGET = 200   # mỗi nhóm, mỗi yêu cầu: lượt ảnh 7 ngày giải tối đa chừng này ảnh mới nhất, để yêu cầu luôn xong trong timeout
IMAGE_SECONDS = 25        # mỗi yêu cầu chỉ giải ảnh trong chừng này giây (timeout của bộ xử lý là 60): sau đợt máy tắt lâu, tồn nhiều
                          # ảnh không làm yêu cầu quá giờ mãi rồi kẹt cả tin chữ; ảnh chưa giải quay lại ở lượt sau (dòng `end` báo)
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp")


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


def within(rows: list[dict], hours: float, now: float) -> set:
    """Khóa của các tin trong `hours` giờ gần nhất."""
    return {key(row) for row in rows if isinstance(row.get("create_time"), int) and row["create_time"] >= now - hours * 3600}


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
    """(MediaDownloader, aes, xor) khi khóa ảnh suy ra được ngoại tuyến, ngược lại None."""
    try:
        import importlib
        media = importlib.import_module("wechatauto.media")   # `db_adapter` đã đăng ký gói `wechatauto` trong sys.modules
        downloader = media.MediaDownloader(db)
    except Exception:   # noqa: BLE001  (thiếu thư viện…: không có ảnh, vẫn đọc chữ)
        return None
    try:
        derived = downloader._derive_cfg_key()
    except Exception:   # noqa: BLE001  (đường `cfg_dword` của upstream hỏng thì vẫn thử đường ngoại tuyến)
        derived = None
    try:
        derived = derived or offline_image_key(db)
    except Exception:   # noqa: BLE001
        return None
    return (downloader, derived[0], derived[1]) if derived else None


def offline_image_key(db) -> tuple[str, int] | None:
    """(khóa AES, byte XOR) của ảnh V2 suy hoàn toàn ngoại tuyến, hoặc None. Không quét bộ nhớ, không ghi khóa ra đâu.

    Khóa = 16 ký tự đầu của md5(mã trong tên `key_<mã>_….statistic` ở thư mục `kvcomm` của WeChat + wxid). wxid thử ba dạng (bỏ
    đuôi `_xxxx` của thư mục tài khoản…). Chỉ nhận khóa giải được khối đầu của file `.dat` V2 thật thành chữ ký ảnh (JPEG, PNG, GIF,
    WEBP, wxgf): bộ thử của upstream chỉ nhận JPEG trên MỘT file, mẫu là PNG thì loại cả khóa đúng. Byte XOR suy từ đuôi ảnh của các
    mẫu khi ít nhất hai mẫu cùng ra một byte (XOR sai thì ảnh vẫn qua kiểm đầu file nhưng hỏng đuôi), không thì mã & 0xFF.

    Khóa đã kiểm được nhớ trong tiến trình tới khi `kvcomm` có mã khác thay chỗ. Thư mục trống không làm mất khóa: WeChat thoát thì
    xóa rồi tạo lại các file này (đo trên máy Zalo 22/11/2026), một lượt đọc rơi vào giữa từng báo mất khóa ảnh vài giây."""
    appdata = os.environ.get("APPDATA")
    wxid = str(getattr(db, "wxid", "") or getattr(db, "account", "") or "")
    if not appdata or not wxid:
        return None
    codes = kvcomm_codes(Path(appdata))
    account = getattr(db, "account_dir", None)
    account = str(account) if isinstance(account, str | os.PathLike) else ""
    cached = KEYS.get((account, wxid))
    if cached and (cached[0] in codes or not codes):   # trống: WeChat đang ghi lại file, khóa chưa đổi
        return cached[1], cached[2]
    now = time.monotonic()
    for stale in [key for key, at in MISSES.items() if now - at >= MISS_RETRY]:
        del MISSES[stale]
    miss = (account, wxid, frozenset(codes))
    if not codes or not account or miss in MISSES:
        return None
    variants = list(dict.fromkeys(("_".join(wxid.split("_")[:2]), re.sub(r"_[0-9a-fA-F]{4}$", "", wxid), wxid)))
    probes = v2_probes(account)
    for code in codes if probes else []:
        for candidate in variants:
            aes = hashlib.md5((code + candidate).encode()).hexdigest()[:16]
            if opens(aes, probes):
                xor = tail_xor(aes, probes)
                KEYS[(account, wxid)] = (code, aes, int(code) & 0xFF if xor is None else xor)
                return KEYS[(account, wxid)][1:]
    MISSES[miss] = now
    return None


def kvcomm_codes(appdata: Path) -> list[str]:
    """Mã số trong tên `key_<mã>_….statistic` ở `kvcomm` (WeChat 4.x, `net` và `ilink`), file mới nhất trước, không trùng."""
    found = []
    for area in ("net", "ilink"):
        try:
            entries = list(os.scandir(appdata / "Tencent" / "xwechat" / area / "kvcomm"))
        except OSError:
            continue
        for entry in entries:
            match = KVCOMM.fullmatch(entry.name)
            if not match:
                continue
            with contextlib.suppress(OSError):   # file biến mất giữa lúc liệt kê: bỏ qua, đừng bỏ cả lượt
                found.append((entry.stat().st_mtime, match.group(1)))
    return list(dict.fromkeys(code for _, code in sorted(found, reverse=True)))


def v2_probes(account_dir: str, limit: int = SAMPLES) -> list[tuple[bytes, bytes]]:
    """(khối mã hóa đầu, 16 byte cuối của phần XOR hoặc b"") của tối đa `limit` file `.dat` V2 ở
    `msg/attach/<nhóm>/<tháng>/Img`, tháng mới trước. Mỗi file chỉ đọc 31 byte đầu và tối đa 16 byte cuối; không giải ảnh nào."""
    attach = Path(account_dir) / "msg" / "attach"
    months = []
    try:
        chats = [entry.path for entry in os.scandir(attach) if entry.is_dir()]
    except OSError:
        return []
    for chat in chats:
        with contextlib.suppress(OSError):
            months += [(entry.name, entry.path) for entry in os.scandir(chat) if entry.is_dir()]
    probes: list[tuple[bytes, bytes]] = []
    for _, month in sorted(months, reverse=True):
        try:
            names = sorted((entry.name for entry in os.scandir(Path(month) / "Img") if entry.name.endswith(".dat")), reverse=True)
        except OSError:
            continue
        for name in names:
            try:
                with open(Path(month) / "Img" / name, "rb") as stream:
                    head = stream.read(dat.V2_HEADER.size + 16)
                    if len(head) < dat.V2_HEADER.size + 16 or not head.startswith(dat.V2_MAGIC):
                        continue
                    xor_size = dat.V2_HEADER.unpack_from(head)[2]
                    tail = b""
                    if xor_size:
                        stream.seek(-min(16, xor_size), os.SEEK_END)
                        tail = stream.read(16)
            except OSError:
                continue
            probes.append((head[dat.V2_HEADER.size:], tail))
            if len(probes) >= limit:
                return probes
    return probes


def opens(aes: str, probes: list[tuple[bytes, bytes]]) -> bool:
    """Khóa giải được ít nhất hai mẫu (một, nếu chỉ có một) thành chữ ký ảnh: một khối 16 byte ngẫu nhiên tình cờ ra `FF D8 FF` là
    2⁻²⁴, đòi hai mẫu thì gần như không thể nhận nhầm khóa."""
    keys = dat.expand_key(aes.encode("ascii"))
    hits = 0
    for block, _ in probes:
        plain = dat.decrypt_block(keys, block)
        if dat.sniff(plain) or plain.startswith(b"wxgf"):
            hits += 1
            if hits >= min(2, len(probes)):
                return True
    return False


def tail_xor(aes: str, probes: list[tuple[bytes, bytes]]) -> int | None:
    """Byte XOR suy từ đuôi chắc chắn của ảnh (JPEG `FF D9`, PNG khối IEND) ở các mẫu giải được; chỉ trả khi ít nhất hai mẫu suy
    được và cùng một byte (một ảnh JPEG có thể có dữ liệu thừa sau `FF D9`). Không dùng GIF: đuôi chỉ một byte `3B`, GIF có đệm số
    0 thì mẫu nào cũng "khớp" một byte sai."""
    keys = dat.expand_key(aes.encode("ascii"))
    found = set()
    count = 0
    for block, tail in probes:
        mime = dat.sniff(dat.decrypt_block(keys, block))
        ending = dat.ENDINGS.get(mime) if mime in ("image/jpeg", "image/png") else None
        if not ending or len(tail) < len(ending):
            continue
        key = tail[-1] ^ ending[-1]
        if all(tail[-len(ending) + i] ^ key == byte for i, byte in enumerate(ending)):
            found.add(key)
            count += 1
    return found.pop() if count >= 2 and len(found) == 1 else None


def export_image(tools, username: str, local_id: int, sort_seq, directory: str) -> str | None:
    """Giải mã ảnh `.dat` của một tin ra `directory`; trả tên file hoặc None. Chỉ đọc file cục bộ, không đụng giao diện WeChat.

    `local_id` lặp giữa các mảnh DB và upstream tìm ảnh theo `local_id`, lấy tin ảnh có `sort_seq` lớn nhất: tin ảnh cũ trùng số
    với tin ảnh mới sẽ nhận NHẦM ảnh của tin mới. Nên chỉ giải khi tin upstream tìm ra đúng là tin này (cùng `sort_seq`)."""
    downloader, aes, xor = tools
    try:
        row = downloader.db.get_message_row(username, local_id, local_type=3)
        if not isinstance(row, dict) or row.get("sort_seq") != sort_seq:
            return None
        path = downloader.download_image(username, local_id, save_dir=directory, aes_key=aes, xor_key=xor, tier="best")
        if path and Path(path).suffix.lower() not in IMAGE_SUFFIXES:
            # Ảnh HEVC (`wxgf`) mà máy không có ffmpeg: upstream để nguyên `.wxgf`, web không hiện được. Thử ảnh thu nhỏ; vẫn không
            # được thì trả file cũ để bộ xử lý biết "giải ra mà không dùng được" và thôi thử.
            thumb = downloader.download_image(username, local_id, save_dir=directory, aes_key=aes, xor_key=xor, tier="thumb")
            if thumb and Path(thumb).suffix.lower() in IMAGE_SUFFIXES:
                with contextlib.suppress(OSError):
                    Path(path).unlink()
                path = thumb
    except Exception:   # noqa: BLE001
        return None
    return Path(path).name if path else None


def fingerprint(item: dict) -> str:
    """Dấu vân tay của một bản ghi đầu ra (loại, chữ đã làm sạch, người gửi và tên, cờ thu hồi): cửa sổ đọc lại chỉ cần so cái này;
    đổi biệt danh làm dòng được gửi lại để `users.json` cập nhật."""
    text = json.dumps([item.get("type"), item.get("content"), item.get("sender"), item.get("sender_name"), bool(item.get("revoked"))],
                      ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:16]


def sender_of(row: dict, nicks: dict) -> tuple[str, bool]:
    """(username người gửi, có phải tin của mình). Tin nhóm người khác gửi mở đầu bằng `<username>:\\n` do máy chủ WeChat ghi: đó
    là nguồn đúng. `SenderName2Id` chung mà upstream tra (`sender_username`) lệch với bản WeChat 4 trên máy Zalo — đo 22/11/2026
    trên một nhóm: 0/61 tin khớp tiền tố, 21 tin ra NGƯỜI KHÁC, 40 tin không ra ai; bảng `Name2Id` riêng của mảnh DB thì khớp 60/61.
    Nên tiền tố thắng, nhưng chỉ nhận tiền tố trông chắc là mã người (dạng `wxid_…`, có trong danh bạ, hoặc trùng kết quả tra), để
    dòng đầu "KH0001:" của một tin thường không bị lấy làm người gửi."""
    if row.get("sender_id") == 2:
        return "", True
    raw = row.get("content") if isinstance(row.get("content"), str) else ""
    looked_up = row.get("sender_username") or ""
    found = PREFIX.match(raw)
    if found:
        name = found.group(1)
        if (name.startswith("wxid_") and USERNAME.fullmatch(name)) or name in nicks or name == looked_up:
            return name, False
    return looked_up, False


def stale_key(row: dict, nicks: dict):
    """Khóa người gửi chưa tra được (thành viên mới vào sau khi tiến trình mở DB, bộ nhớ đệm của upstream cũ), hoặc None."""
    if row.get("type") == "系统消息":
        return None
    sender, own = sender_of(row, nicks)
    if own:
        return None
    if not sender:
        return ("id", row.get("sender_id"))
    return None if sender in nicks else ("name", sender)


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
    sender, is_self = sender_of(row, nicks)
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
        out["image"] = export_image(tools, username, row["local_id"], row.get("sort_seq"), images_dir)
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
    deep = request.get("deep_image_hours") if isinstance(request.get("deep_image_hours"), int | float) else 0
    # Một lần sau khi đổi cách tìm người gửi: đọc lại mọi tin trong chừng này giờ để sửa người gửi của tin đã lên web (chỉ tin đã có).
    resend = request.get("resend_hours") if isinstance(request.get("resend_hours"), int | float) else 0
    deep = 0 if resend > 0 else deep   # không chung một yêu cầu với lượt ảnh 7 ngày (bộ xử lý cũng không gửi chung)
    images_dir = request.get("images_dir") if isinstance(request.get("images_dir"), str) else None
    sent = request.get("known_fp") if isinstance(request.get("known_fp"), dict) else {}   # {username: {"local_id:sort_seq": fp}}
    nicks = db.nickname_map()
    tools = image_tools(db) if images_dir else None
    deep = deep if tools else 0   # không có khóa thì lượt thử lại ảnh cũ chẳng giải được gì: đừng đọc thêm
    started = time.monotonic()
    over: list[bool] = []   # có phần tử khi đã hết `IMAGE_SECONDS` của yêu cầu này (hết rồi thì hết hẳn tới cuối yêu cầu)

    def in_budget() -> bool:
        if not over and time.monotonic() - started >= IMAGE_SECONDS:
            over.append(True)
        return not over

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
            now = time.time()
            span = max(hours, deep, resend)
            late = [row for row in (read_window(db, username, span, now) if span > 0 and (have or {}).get("sort_seq") else [])
                    if key(row) not in seen]
            recent = within(late, hours, now)
            # Ngoài cửa sổ thường chỉ giữ tin ẢNH trong `deep` giờ, tối đa `DEEP_IMAGE_BUDGET` tin mới nhất: chỉ để thử lại/nâng ảnh.
            photos = {key(row) for row in late if row.get("type") == "图片"}
            older = {k for k in within(late, deep, now) if k not in recent and k in photos} if deep > 0 else set()
            older = set(sorted(older, key=lambda k: (k[1] if isinstance(k[1], int) else 0), reverse=True)[:DEEP_IMAGE_BUDGET])
            redo = {k for k in within(late, resend, now) if k not in recent} if resend > 0 else set()
            late = [row for row in late if key(row) in recent or key(row) in older or key(row) in redo]
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
            # Tin mới luôn được phát (con trỏ phải tiến); hết giờ giải ảnh thì phát không ảnh, lượt cửa sổ sau giải tiếp.
            item = record(nicks, username, row, tools if row.get("type") != "图片" or in_budget() else None, images_dir)
            counts["messages"] += 1
            counts["images"] += bool(item["image"])
            emit(item)
        for row in late:
            item = record(nicks, username, row, None, None, window=True)
            if key(row) not in recent:
                item["deep"] = True   # chỉ để thử lại/nâng ảnh hay sửa người gửi: bộ xử lý không nhập tin mới từ phần này
            if resend > 0:
                item["resend"] = True   # lượt sửa người gửi: bộ xử lý ghi lại cả tin ảnh đã có nếu người gửi đổi
            if (sent.get(username) or {}).get(f"{item['local_id']}:{item['sort_seq']}") == item["fp"]:
                counts["window_same"] += 1   # đã có đúng bản này: không gửi lại nội dung qua ống
                continue
            decode = key(row) in recent or key(row) in older   # tin chỉ đọc lại để sửa người gửi thì không giải ảnh
            if item["type"] == "图片" and tools and decode and not in_budget():
                if not resend:
                    continue   # hết giờ giải ảnh: tin ảnh cửa sổ/7 ngày không có ảnh thì phát cũng vô ích; bộ xử lý chưa nhớ nên lượt sau còn
                decode = False   # vẫn phát để sửa người gửi (lượt sửa chỉ chạy một lần)
            if tools and images_dir and decode and item["type"] == "图片" and isinstance(item["local_id"], int):
                # Bộ xử lý không giữ `fp` của tin ảnh còn thiếu ảnh (và giữ ngắn với ảnh thu nhỏ), nên tin đó về đây: thử giải lại
                # (file `.dat` tải chậm, khóa có muộn, bản nén có sau ảnh thu nhỏ). Ảnh đủ cỡ thì bộ xử lý giữ `fp`, tin dừng ở trên.
                item["image"] = export_image(tools, username, item["local_id"], item["sort_seq"], images_dir)
                counts["images"] += bool(item["image"])
            counts["window"] += 1
            emit(item)
    end = {"kind": "end", **counts, "image_keys": bool(tools)}
    if over:
        end["image_budget_hit"] = True   # còn ảnh chưa giải vì hết giờ: bộ xử lý giữ lượt 7 ngày để giải tiếp
    emit(end)
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
