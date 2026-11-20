"""ZALO-AGENT-01: `python -X utf8 -I …\\zalo_agent run [--once] [--dry-run]`, một tiến trình nền ở máy có Zalo.

Cấu hình đọc từ tham số hoặc biến môi trường (`ZALO_LIVE_SYNC`, `ZALO_AGENT_ROOT`, `ZALO_AGENT_TARGET`,
`ZALO_AGENT_STATUS_TARGET`, `ZALO_AGENT_WECHAT` (=1 bật nguồn WeChat), `ZALO_WECHAT_PYTHON`, `ZALO_WECHAT_PILOT`, `ZALO_WECHAT_GROUPS`, `ZALO_AGENT_INSURANCE_TARGET`, `ZALO_INSURANCE_SNAPSHOT`, `ZALO_INSURANCE_STORE`, `ZALO_AGENT_MONEY_IMAGES`), không có bí mật trong repo. Thư mục gốc `D:\\zalo-agent`: `state/` (con trỏ, status.json),
`bundle/` (gói chat dựng tại máy), `insurance/` (bản gọn bảo hiểm), `reads/` (kết quả OCR ảnh, chỉ ở máy), `logs/` (xoay vòng 10 MB x 3). Chỉ đọc thư mục live-sync.
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):   # chạy `python -I …\zalo_agent`: đưa thư mục cha vào sys.path rồi nạp như gói
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zalo_agent import cursor as cursors
from zalo_agent import ocr
from zalo_agent import push as pusher
from zalo_agent import status as status_file
from zalo_agent.processors import wechat as wechat_source
from zalo_agent.processors.bundle import BundleProcessor
from zalo_agent.processors.insurance import InsuranceProcessor
from zalo_agent.processors.money_images import MoneyImagesProcessor
from zalo_agent.source import VN, LiveSync

REPO = Path(__file__).resolve().parents[3]
STATUS_EVERY = 60     # giây: nhịp tim tối thiểu khi không có gì đổi
SETTLE = 3            # giây: gom các revision liên tiếp rồi mới xử lý
MAX_BACKOFF = 15 * 60  # giây
LOCAL_RETRY = 10      # giây: thử lại lỗi cục bộ


class Agent:
    def __init__(self, live: LiveSync, root: Path, bundle_target: str, status_target: str, *, run=pusher.ssh_run,
                 dry_run: bool = False, clock=time.time, sleep=time.sleep, log=None, insurance_target: str | None = None,
                 insurance_snapshot: Path | None = None, insurance_store: Path | None = None, money_images: bool = False, money_args: dict | None = None,
                 wechat: dict | None = None, **processor_args):
        self.live, self.root, self.status_target, self.run = live, Path(root), status_target, run
        self.dry_run, self.clock, self.sleep = dry_run, clock, sleep
        self.state = self.root / "state"
        self.log = log or logging.getLogger("zalo_agent")
        self.version = status_file.agent_version(REPO)
        # --dry-run dùng kho riêng (`wechat-dry`): không nối `log.jsonl` thật nên lượt thật sau đó không có dòng thừa
        overlay = wechat_source.Store(self.root / ("wechat-dry" if dry_run else "wechat"), wechat_source.Selection(Path(wechat["groups"]))) if wechat else None
        self.processors = [BundleProcessor(live, self.state, self.root / "bundle", bundle_target, run=run, dry_run=dry_run,
                                           clock=clock, overlay=overlay, **processor_args)]
        if overlay:   # WECHAT-01: nguồn thứ hai, chỉ khi bật `--wechat`; tiến trình con chạy ở luồng nền nên không làm chậm bundle
            self.processors.append(wechat_source.WeChatProcessor(
                overlay, self.state, python=wechat["python"], pilot=wechat["pilot"], interval=wechat.get("interval", wechat_source.INTERVAL),
                images=wechat.get("images", False), run=wechat.get("run") or wechat_source.Session(), dry_run=dry_run, clock=clock,
                background=wechat.get("background", True)))
        if insurance_target:   # không đích thì không có bộ xử lý (và không có khóa trong status.json)
            self.processors.append(InsuranceProcessor(live, self.state, self.root / "insurance", insurance_target,
                                                      snapshot=insurance_snapshot, store=insurance_store, run=run, dry_run=dry_run, clock=clock))
        if money_images:   # mặc định tắt: agent chạy code từ checkout `main`, bật sẵn thì merge là bắt đầu OCR trên máy thật
            self.processors.append(MoneyImagesProcessor(live, self.state, self.root / "reads", dry_run=dry_run, clock=clock, **(money_args or {})))
        self.last = {}
        self.last_status_at = 0.0
        # Lùi dần RIÊNG từng bộ xử lý: lỗi của bộ này không bao giờ làm bộ khác chạy chậm đi.
        self.retry_at = {processor.name: 0.0 for processor in self.processors}
        self.failures = {processor.name: 0 for processor in self.processors}
        self.ran: list[str] = []   # tên các bộ xử lý đã chạy ở lượt `cycle` gần nhất
        self.push_ok_at = None
        self.push_error = None
        self.lock_handle = None
        self.last_identity = None

    def lock(self) -> bool:
        """Khóa của hệ điều hành trên handle mở suốt đời tiến trình: tiến trình chết (kể cả bị giết, máy khởi động lại) thì
        hệ điều hành tự nhả. File `agent.lock` còn sót không chặn ai."""
        if self.lock_handle is not None:
            return True
        self.state.mkdir(parents=True, exist_ok=True)
        handle = open(self.state / "agent.lock", "a+b")  # noqa: SIM115  (giữ mở suốt đời tiến trình)
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.lock_handle = handle
        return True

    def release(self) -> None:
        if self.lock_handle is not None:
            self.lock_handle.close()
            self.lock_handle = None

    def cycle(self, force_status: bool = False, run_steps: bool = True) -> dict | None:
        """Một lượt: chạy từng bộ xử lý không đang lùi sau lỗi (`run_steps` False: không chạy bộ nào, chỉ nhịp tim), ghi
        `status.json` và đẩy khi có đổi hoặc đủ một phút. Bộ đang lùi giữ nguyên kết quả lượt trước trong `status.json`."""
        if not self.lock():
            return None
        results = dict(self.last)
        started = self.clock()
        due = [processor for processor in self.processors if run_steps and started >= self.retry_at[processor.name]]
        self.ran = [processor.name for processor in due]
        for processor in due:
            try:
                results[processor.name] = processor.step()
            except Exception as exc:  # noqa: BLE001  (một bộ xử lý lỗi không được làm chết cả agent)
                saved = cursors.load(self.state, processor.name)
                results[processor.name] = {"action": "idle", "revision": (saved or {}).get("revision"), "error": "unexpected"}
                self.log.error("%s: %s", processor.name, type(exc).__name__)
        now = self.clock()
        for name, result in results.items():
            if result["action"] != "idle" or result["error"] != (self.last.get(name) or {}).get("error"):
                self.log.info("%s: %s revision=%s bytes=%s error=%s", name, result["action"], result["revision"],
                              result.get("bytes_sent"), result["error"])
        changed = {name: (r["action"], r["revision"], r["error"]) for name, r in results.items()} != \
            {name: (r["action"], r["revision"], r["error"]) for name, r in self.last.items()}
        self.last = results
        identity = self.live.identity()
        moved = identity != self.last_identity   # identity đổi (Zalo mở/đóng): báo hao ngay, không chờ nhịp 60 giây
        self.last_identity = identity
        if not (force_status or changed or moved or now - self.last_status_at >= STATUS_EVERY):
            return None
        try:
            status = status_file.compose(status_file.load(self.state), now, self.version, len(self.live.selection()), self.live,
                                         results, self.push_ok_at, self.push_error,
                                         (identity, status_file.track_identity(self.state, identity, now, persist=not self.dry_run)))
            data = status_file.write(self.state, status, persist=not self.dry_run)
        except Exception as exc:  # noqa: BLE001  (file trạng thái bị giữ, ổ đĩa lỗi…: bỏ lượt này, không làm chết agent)
            self.log.error("status: %s", type(exc).__name__)
            return None
        self.last_status_at = now
        if not self.dry_run:
            try:
                status_file.push_status(self.status_target, data, self.run)
                self.push_ok_at, self.push_error = cursors.now_iso(now), None
            except pusher.PushError:
                self.push_error = "push_failed"
        return status

    def wants_work(self) -> bool:
        """Có bộ xử lý nào (không đang lùi) cần gom revision. Mỗi bộ bọc `try` riêng: một bộ hỏng không chặn bộ khác."""
        now = self.clock()
        wanted = False
        for processor in self.processors:
            if now < self.retry_at[processor.name]:
                continue
            try:
                wanted = processor.wants_work() or wanted
            except Exception as exc:  # noqa: BLE001
                self.log.error("%s: wants_work %s", processor.name, type(exc).__name__)
        return wanted

    def tick(self) -> None:
        if self.wants_work():
            self.sleep(SETTLE)
        self.cycle()
        for name in self.ran:
            error = self.last[name]["error"]
            if not error:
                self.failures[name], self.retry_at[name] = 0, 0.0
            elif error == "push_failed":   # máy chủ hoặc mạng: lùi dần bộ này để khỏi ssh liên tục
                self.failures[name] += 1
                delay = backoff(self.failures[name])
                self.retry_at[name] = self.clock() + delay
                self.log.warning("%s: lỗi đẩy lần %d liên tiếp: lùi %d giây", name, self.failures[name], delay)
            else:                           # lỗi cục bộ (thiếu file, dựng gói lỗi…): thử lại sớm để hết lỗi là mốc error_since về null
                self.failures[name], self.retry_at[name] = 0, self.clock() + LOCAL_RETRY

    def forever(self, interval: float = 1.0) -> None:
        while True:
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001  (không gì được làm chết vòng lặp: pythonw chết thì chết im lặng)
                self.log.error("vòng lặp: %s", type(exc).__name__)
                for name in self.retry_at:
                    self.retry_at[name] = self.clock() + LOCAL_RETRY
            self.sleep(interval)


def backoff(failures: int) -> int:
    """Giây chờ sau lần lỗi thứ `failures` liên tiếp: 60, 120, 240, … tối đa 15 phút."""
    return min(MAX_BACKOFF, 60 * 2 ** (failures - 1))


def configure_logging(root: Path) -> logging.Logger:
    logger = logging.getLogger("zalo_agent")
    logger.setLevel(logging.INFO)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(root / "logs" / "agent.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return logger


def run_reread(args, root: Path) -> int:
    """`zalo_agent reread`: in số đếm, không in chữ OCR, số tiền hay đường dẫn."""
    since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=VN)
    processor = MoneyImagesProcessor(LiveSync(Path(args.live_sync)), root / "state", root / "reads")
    try:
        counts = processor.reread(ocr.ENGINES[args.engine](), int(since.timestamp() * 1000))
    except ocr.OcrUnavailable:
        print("thiếu engine OCR ở máy này (ocr_unavailable)")
        return 1
    print(json.dumps(counts))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zalo_agent", description="Tiến trình nền ở máy có Zalo (ZALO-AGENT-01).")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="đọc live-sync theo revision, đẩy gói chat, giấy bảo hiểm và nhịp tim lên hao")
    run.add_argument("--once", action="store_true", help="chạy một lượt rồi thoát")
    run.add_argument("--dry-run", action="store_true", help="làm hết ở máy, không đẩy gì lên hao")
    run.add_argument("--live-sync", default=os.environ.get("ZALO_LIVE_SYNC", r"D:\zalo-audit-viewer\live-sync-20261030"))
    run.add_argument("--root", default=os.environ.get("ZALO_AGENT_ROOT", r"D:\zalo-agent"))
    run.add_argument("--target", default=os.environ.get("ZALO_AGENT_TARGET", "hao:/srv/v7/zalo-bundle"))
    run.add_argument("--status-target", default=os.environ.get("ZALO_AGENT_STATUS_TARGET", "hao:/srv/v7/zalo-agent"))
    run.add_argument("--insurance-target", default=os.environ.get("ZALO_AGENT_INSURANCE_TARGET", ""),
                     help="đích giấy bảo hiểm, ví dụ hao:/srv/v7/insurance; MẶC ĐỊNH RỖNG = tắt bộ xử lý insurance (chỉ bật ở bước "
                          "tắt ZaloInsurancePush, để hai đường không ghi song song)")
    run.add_argument("--insurance-snapshot", default=os.environ.get("ZALO_INSURANCE_SNAPSHOT"), help="mặc định: <live-sync>/insurance-snapshot.json")
    run.add_argument("--insurance-store", default=os.environ.get("ZALO_INSURANCE_STORE"), help="mặc định: <live-sync>/remote-media-store")
    run.add_argument("--money-images", choices=("on", "off"), default=os.environ.get("ZALO_AGENT_MONEY_IMAGES", "off"),
                     help="bật bộ xử lý money_images (OCR ảnh của nhóm đã chọn tại máy); MẶC ĐỊNH off")
    run.add_argument("--money-max-age-days", type=int, default=30, help="chỉ đọc ảnh gửi trong chừng này ngày khi dựng lại từ đầu")
    wechat_source.add_arguments(run)
    run.add_argument("--wechat", action="store_true", default=os.environ.get("ZALO_AGENT_WECHAT") == "1",
                     help="WECHAT-01: bật nguồn WeChat (nhóm trong wechat-groups.json); MẶC ĐỊNH TẮT")
    run.add_argument("--wechat-interval", type=float, default=wechat_source.INTERVAL, help="giây giữa hai lần đọc WeChat")
    run.add_argument("--wechat-images", action="store_true", help="giải mã ảnh WeChat khi khóa ảnh suy ra được ngoại tuyến (mặc định tắt)")
    for name in ("wechat-list", "wechat-add", "wechat-remove"):
        command = sub.add_parser(name, help="chọn nhóm WeChat lên web (đọc chỉ-đọc qua wechat-mcp-pilot)")
        wechat_source.add_arguments(command)
        if name != "wechat-list":
            command.add_argument("needles", nargs="+", help="tên nhóm hoặc 8 ký tự đầu mã")
    run.add_argument("--max-fetch", type=int, default=50, help="số ảnh tối đa tải từ Zalo mỗi lượt")
    run.add_argument("--max-age-days", type=int, default=30)
    reread = sub.add_parser("reread", help="đọc lại ảnh đã nhận bằng một engine OCR (hoặc phiên bản mới), giữ kết quả cũ cạnh bên")
    reread.add_argument("--engine", required=True, choices=sorted(ocr.ENGINES))
    reread.add_argument("--since", required=True, help="YYYY-MM-DD (giờ VN): chỉ ảnh gửi từ ngày này")
    reread.add_argument("--live-sync", default=os.environ.get("ZALO_LIVE_SYNC", r"D:\zalo-audit-viewer\live-sync-20261030"))
    reread.add_argument("--root", default=os.environ.get("ZALO_AGENT_ROOT", r"D:\zalo-agent"))
    args = parser.parse_args(argv)
    if args.command.startswith("wechat-"):
        return wechat_source.main_command(args)
    root = Path(args.root)
    if args.command == "reread":
        return run_reread(args, root)
    agent = Agent(LiveSync(Path(args.live_sync)), root, args.target, args.status_target, dry_run=args.dry_run,
                  insurance_target=args.insurance_target, insurance_snapshot=Path(args.insurance_snapshot) if args.insurance_snapshot else None,
                  insurance_store=Path(args.insurance_store) if args.insurance_store else None,
                  money_images=args.money_images == "on", money_args={"max_age_days": args.money_max_age_days},
                  wechat={"python": args.wechat_python, "pilot": args.wechat_pilot, "groups": args.wechat_groups,
                          "interval": args.wechat_interval, "images": args.wechat_images} if args.wechat else None,
                  max_fetch=args.max_fetch, max_age_days=args.max_age_days)
    if not agent.lock():   # trước khi mở agent.log: bản thứ hai giữ handle log sẽ làm bản chính không xoay vòng được log trên Windows
        print("đang có một agent khác chạy")
        return 0
    configure_logging(root)
    if args.once:
        status = agent.cycle(force_status=True)
        print(json.dumps(status, ensure_ascii=False, indent=2) if status else "không ghi được status (xem agent.log)")
        return 1 if status and any(item["error"] for item in status["processors"].values()) else 0
    agent.forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
