"""TELEGRAM-01: `hao` gửi tin báo thu chi vào một nhóm Telegram theo sự kiện. Chỉ báo: không ghi tiền, bot không đọc nhóm, không nhận lệnh.

Sự kiện lấy từ trang Thu chi (`v7_cash_chat.build`, cùng đối chiếu người dùng thấy):

- có khoản thu, chi, ứng mới;
- khoản lệch số với sổ (`AMOUNT_DIFF`);
- khoản quá 3 ngày chưa vào sổ (`MISSING`);
- một bản tổng cuối ngày, sau `DAILY_HOUR` giờ VN.

Mỗi tin chỉ có nhóm hoặc khách, số tiền, giờ, trạng thái và link mở khoản trên web. Không có chữ gốc của tin chat. Ảnh chỉ gửi bản đã che
theo luật w1 do máy Zalo đẩy lên (`<thư mục kết quả đọc ảnh>/redacted-w1/<mã ảnh>.jpg`). Không có bản che thì chỉ gửi chữ; không bao giờ
đọc ảnh gốc.

**Cờ tắt mặc định.** Chỉ chạy khi `WEBDEBIT_TELEGRAM=1` và `/etc/webdebit/telegram.env` có `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
`TELEGRAM_LINK_BASE` là gốc link web, không bắt buộc. Token không vào Git, log hay nhật ký.

**Hộp gửi (outbox):** mỗi khóa sự kiện được gửi tối đa một lần.
- Ghi `sending` (đã `fsync`) trước khi gọi Telegram; gửi xong ghi `sent`.
- Chết giữa hai bước thì lần đọc sau khóa đó thành `uncertain` và không gửi lại: thiếu một tin còn hơn gửi trùng.
- Lỗi mạng trước khi Telegram nhận (không kết nối được) thì thử lại lượt sau, tối đa `MAX_TRIES`.
- Telegram từ chối (4xx) thì `failed`, không thử lại.
- Lần bật đầu tiên (chưa có file hộp gửi), mọi sự kiện đang có chỉ được ghi mốc (`baseline`), không gửi: nhóm chỉ nhận chuyện từ lúc bật.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import v7_cash_chat
import v7_machine

VN = v7_machine.VN
ENV_FILE = "/etc/webdebit/telegram.env"
OUTBOX_FILE = "/srv/v7/telegram/outbox.json"
INTERVAL = 60
DAILY_HOUR = 20
PER_RUN = 10                  # tin tối đa mỗi lượt: lần bật đầu hay sau khi máy Zalo đọc bù không xả cả trăm tin một lúc
MAX_TRIES = 5
LOOKBACK_DAYS = 3             # khoản mới chỉ trong chừng này ngày; khoản quá hạn thì theo đúng luật MISSING của trang
API = "https://api.telegram.org"
VERBS = {"thu": "Thu", "chi": "Chi", "ung": "Ứng"}
STATUS_TEXT = {"RECORDED": "đã vào sổ", "WAITING": "chờ vào sổ", "MISSING": "quá 3 ngày chưa vào sổ", "AMOUNT_DIFF": "lệch số với sổ",
               "SUGGEST": "có dòng sổ gần giống", "UNKNOWN_TARGET": "chưa rõ khách", "NO_LEDGER": "không cần đối chiếu",
               "NO_AMOUNT": "chưa đọc được số", "NOT_CASH": "đã loại"}


class SendError(Exception):
    def __init__(self, retry: bool):
        super().__init__("telegram")
        self.retry = retry


def config(path: str | None = None) -> dict | None:
    """Cấu hình khi cờ bật và đủ token, mã nhóm; ngược lại None (tắt). Không in, không log giá trị."""
    if os.getenv("WEBDEBIT_TELEGRAM") != "1":
        return None
    values: dict[str, str] = {}
    try:
        for line in Path(path or os.getenv("WEBDEBIT_TELEGRAM_ENV") or ENV_FILE).read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                values[key.strip()] = value.strip().strip('"')
    except OSError:
        return None
    if not values.get("TELEGRAM_BOT_TOKEN") or not values.get("TELEGRAM_CHAT_ID"):
        return None
    return {"token": values["TELEGRAM_BOT_TOKEN"], "chat": values["TELEGRAM_CHAT_ID"], "link": values.get("TELEGRAM_LINK_BASE", "").rstrip("/")}


def money(value: int | None) -> str:
    return "chưa rõ số" if value is None else f"{value:,}".replace(",", ".") + " đ"


def _who(item: dict) -> str:
    target = item.get("target") or {}
    return target.get("label") or item.get("conversation_name") or "chưa rõ nhóm"


def _when(item: dict) -> str:
    stamp = item.get("sent_at")
    return datetime.fromtimestamp(stamp / 1000, VN).strftime("%H:%M %d/%m") if isinstance(stamp, int) else item.get("day", "")


def _line(item: dict, link: str) -> str:
    amount = f"{item['amount_cny']:,} tệ".replace(",", ".") if item.get("currency") == "CNY" and item.get("amount_cny") else money(item.get("amount_vnd"))
    text = f"{VERBS.get(item.get('direction'), 'Khoản')} {amount} · {_who(item)} · {_when(item)} · {STATUS_TEXT.get(item.get('status'), item.get('status'))}"
    return text + (f"\n{link}/thu-chi.html?m={item['message_id']}" if link and item.get("message_id") else "")


def events(body: dict, now: float, link: str = "") -> list[dict]:
    """Sự kiện của một lượt dựng Thu chi, mỗi sự kiện có khóa ổn định (cùng sự kiện thì cùng khóa, gửi đúng một lần)."""
    if body.get("unavailable"):
        return []
    today = datetime.fromtimestamp(now, VN).date()
    out = []
    for item in body.get("items") or []:
        if item.get("status") == "NOT_CASH" or not isinstance(item.get("message_id"), str):
            continue
        day = date.fromisoformat(item["day"]) if isinstance(item.get("day"), str) else today
        media = [one.get("id") for one in item.get("media") or [] if isinstance(one, dict) and isinstance(one.get("id"), str)]
        base = {"photo": media[0] if media else None, "text": _line(item, link)}
        if (today - day).days <= LOOKBACK_DAYS:
            out.append({**base, "key": f"new:{item['message_id']}", "text": "Khoản mới: " + base["text"]})
        if item.get("status") == "AMOUNT_DIFF":
            out.append({**base, "key": f"diff:{item['message_id']}:{item.get('amount_vnd')}:{item.get('ledger_vnd')}",
                        "text": f"Lệch số: {base['text']}\nSổ ghi {money(item.get('ledger_vnd'))}"})
        if item.get("status") == "MISSING":
            out.append({**base, "key": f"missing:{item['message_id']}", "text": "Quá 3 ngày chưa vào sổ: " + base["text"]})
    if datetime.fromtimestamp(now, VN).hour >= DAILY_HOUR:
        totals = body.get("totals") or {}
        today_items = [item for item in body.get("items") or [] if item.get("day") == today.isoformat() and item.get("status") != "NOT_CASH"]
        lines = [f"Tổng ngày {today.strftime('%d/%m')}: thu {money(sum(i['amount_vnd'] or 0 for i in today_items if i.get('direction') == 'thu' and i.get('currency') != 'CNY'))}, "
                 f"chi {money(sum(i['amount_vnd'] or 0 for i in today_items if i.get('direction') == 'chi' and i.get('currency') != 'CNY'))}, "
                 f"ứng {money(sum(i['amount_vnd'] or 0 for i in today_items if i.get('direction') == 'ung' and i.get('currency') != 'CNY'))}",
                 f"{len(today_items)} khoản, {sum(i.get('status') == 'MISSING' for i in body.get('items') or [])} khoản quá 3 ngày chưa vào sổ, "
                 f"{totals.get('amount_diff', 0)} khoản lệch số"]
        out.append({"key": f"daily:{today.isoformat()}", "photo": None, "text": "\n".join(lines) + (f"\n{link}/thu-chi.html" if link else "")})
    return out


class Outbox:
    """`{khóa: {state, at, tries}}` trong một file JSON ghi nguyên tử. Đọc lên mà còn `sending` (lượt trước chết lúc đang gửi) thì thành
    `uncertain`: Telegram có thể đã nhận, nên không gửi lại."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.fresh = not self.path.exists()   # chưa từng chạy: lượt đầu chỉ ghi mốc
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.items: dict[str, dict] = {key: value for key, value in (data.get("items") or {}).items() if isinstance(value, dict)}
        changed = False
        for value in self.items.values():
            if value.get("state") == "sending":
                value["state"], changed = "uncertain", True
        if changed:
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        with tmp.open("w", encoding="utf-8") as stream:
            json.dump({"schema": 1, "items": self.items}, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, self.path)

    def ready(self, key: str) -> bool:
        item = self.items.get(key)
        return item is None or (item.get("state") == "retry" and item.get("tries", 0) < MAX_TRIES)

    def mark(self, key: str, state: str, now: float) -> None:
        tries = self.items.get(key, {}).get("tries", 0) + (state in ("retry", "failed"))
        self.items[key] = {"state": state, "at": datetime.fromtimestamp(now, VN).isoformat(timespec="seconds"), "tries": tries}
        self.save()

    def prune(self, now: float, keep_days: int = 30) -> None:
        cutoff = datetime.fromtimestamp(now - keep_days * 86400, VN).isoformat(timespec="seconds")
        self.items = {key: value for key, value in self.items.items() if str(value.get("at", "")) >= cutoff}


def _request(url: str, data: bytes, content_type: str) -> None:
    request = urllib.request.Request(url, data=data, headers={"Content-Type": content_type}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            ok = json.loads(response.read(65536) or b"{}").get("ok")
    except urllib.error.HTTPError as exc:
        raise SendError(retry=exc.code >= 500 or exc.code == 429) from None   # 4xx (token sai, nhóm sai): không thử lại
    except (urllib.error.URLError, OSError, ValueError):
        raise SendError(retry=True) from None
    if not ok:
        raise SendError(retry=False)


def send(cfg: dict, text: str, photo: Path | None = None, request=_request) -> None:
    """Gửi một tin; có ảnh đã che thì `sendPhoto` với chú thích, không thì `sendMessage`. Không bao giờ log token hay nội dung."""
    base = f"{API}/bot{cfg['token']}"
    if photo is None:
        body = json.dumps({"chat_id": cfg["chat"], "text": text[:4000], "disable_web_page_preview": True}).encode("utf-8")
        request(f"{base}/sendMessage", body, "application/json")
        return
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
             for name, value in (("chat_id", cfg["chat"]), ("caption", text[:1000]))]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="anh.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
                 + photo.read_bytes() + b"\r\n")
    request(f"{base}/sendPhoto", b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}")


def redacted(media_id: str | None) -> Path | None:
    """Bản đã che theo luật w1 do máy Zalo đẩy lên; không có thì None (chỉ gửi chữ)."""
    if not media_id or not v7_cash_chat.SHA256.fullmatch(media_id):
        return None
    path = Path(os.getenv("WEBDEBIT_ZALO_READS_DIR") or v7_cash_chat.READS_DIR) / "redacted-w1" / f"{media_id}.jpg"
    return path if path.is_file() and not path.is_symlink() else None


def run_once(runner, cfg: dict, now: float | None = None, outbox: Outbox | None = None, sender=send, build=v7_cash_chat.build) -> dict:
    """Một lượt: dựng Thu chi mấy ngày gần nhất, gửi các sự kiện chưa gửi (tối đa PER_RUN). Trả số đếm, không chữ của tin."""
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, VN).date()
    outbox = outbox or Outbox(os.getenv("WEBDEBIT_TELEGRAM_OUTBOX") or OUTBOX_FILE)
    body = build(today - timedelta(days=LOOKBACK_DAYS + 7), today, runner, "telegram", now)
    counts = dict.fromkeys(("sent", "retry", "failed", "skipped", "left", "baseline"), 0)
    found = events(body, now, cfg.get("link", ""))
    if outbox.fresh and not body.get("unavailable"):
        stamp = datetime.fromtimestamp(now, VN).isoformat(timespec="seconds")
        for event in found:
            outbox.items[event["key"]] = {"state": "baseline", "at": stamp, "tries": 0}
        counts["baseline"] = len(found)
        outbox.fresh = False
        outbox.save()
        return counts
    for event in found:
        if not outbox.ready(event["key"]):
            counts["skipped"] += 1
            continue
        if counts["sent"] + counts["retry"] + counts["failed"] >= PER_RUN:
            counts["left"] += 1
            continue
        outbox.mark(event["key"], "sending", now)
        try:
            sender(cfg, event["text"], redacted(event["photo"]))
        except SendError as exc:
            outbox.mark(event["key"], "retry" if exc.retry else "failed", now)
            counts["retry" if exc.retry else "failed"] += 1
            continue
        outbox.mark(event["key"], "sent", now)
        counts["sent"] += 1
    outbox.prune(now)
    outbox.save()
    return counts


def start(runner, cfg: dict | None = None, interval: int = INTERVAL) -> threading.Thread | None:
    """Gọi lúc API khởi động. Cờ tắt hay thiếu cấu hình thì không làm gì (mặc định)."""
    cfg = cfg if cfg is not None else config()
    if cfg is None:
        return None

    def loop() -> None:
        while True:
            try:
                counts = run_once(runner, cfg)
                if counts["sent"] or counts["failed"]:
                    print(f"V7 telegram: {json.dumps(counts)}", file=sys.stderr, flush=True)   # chỉ số đếm
            except Exception as exc:   # noqa: BLE001  (một lượt lỗi không làm chết luồng; lượt sau thử lại)
                print(f"V7 telegram: lượt lỗi ({type(exc).__name__})", file=sys.stderr, flush=True)
            time.sleep(interval)

    thread = threading.Thread(target=loop, name="telegram-sender", daemon=True)
    thread.start()
    return thread
