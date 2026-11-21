"""ZALO-AGENT-01 Phần 6: độ trễ từng chặng của tin mới (p50, p95) cho `status.json`. Chỉ có số giây và số mẫu, không chữ.

Chặng, tính bằng giây theo đồng hồ máy có Zalo:

- `zalo`: tin gửi (`timestamp` do Zalo cấp) → live-sync ghi revision có tin đó (`message_publish_epoch_ms`); mỗi tin MỚI thêm
  (không tính tin sửa, tin xóa) của nhóm đã chọn là một mẫu. Máy tắt qua đêm thì tin đọc bù buổi sáng có mẫu dài: đúng là tin đó
  lên web muộn, nhưng không do agent nên phép kiểm trên `hao` không dùng chặng này;
- `agent`: live-sync ghi revision → bộ xử lý `bundle` bắt đầu dựng phần thêm (nhịp 1 giây, gom 3 giây, chờ lùi sau lỗi);
- `build`: dựng phần thêm (đọc `changes-N`, quét `messages.jsonl`, ghi delta, ảnh mới);
- `push`: đẩy tới khi `hao` áp gói: ssh trả về sau khi `export-report.json` đã `mv` vào chỗ, nên trang Chat Zalo đọc được ngay;
- `total`: live-sync ghi revision → `hao` áp gói (= `agent` + `build` + `push`).

Mỗi lượt đẩy phần thêm có tin Zalo của nhóm đã chọn là một mẫu của bốn chặng sau, ghi lúc đẩy xong; lượt đẩy lỗi rồi gửi lại
thì mẫu tính tới lần gửi được (gồm cả thời gian chờ). Dựng đầy đủ không có mẫu. Hai cửa sổ: `hour` (60 phút, cho phép kiểm) và
`day` (24 giờ, cho tiêu chí "p95 30 giây trong một ngày làm việc"). Mẫu nhớ ở `<state>/latency.json` để chạy lại agent không mất;
`--dry-run` không ghi file.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from .source import read_json, retry_io

STAGES = ("zalo", "agent", "build", "push", "total")
WINDOWS = (("hour", 3600), ("day", 86400))
KEEP = 86400          # giây: mẫu cũ hơn thì bỏ
CAP = 2000            # mẫu tối đa mỗi chặng (lượt đọc bù sau một đêm có thể vài nghìn tin)
PER_STEP = 200        # mẫu `zalo` tối đa mỗi lượt
LIMIT = 10_000_000    # giây (khoảng 115 ngày): số lớn hơn là đồng hồ hỏng, không phải độ trễ
FILE = "latency.json"


def seconds(value: object) -> float | None:
    """Số giây hữu hạn, không âm (đồng hồ hai máy lệch vài giây thì về 0), không quá LIMIT; còn lại None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value > LIMIT:
        return None
    return round(max(0, value), 1)


def percentile(values: list[float], share: float) -> float:
    """Hạng gần nhất trên dãy đã xếp: p95 của 20 mẫu là mẫu thứ 19."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def stages(timing: dict, pushed: float) -> dict[str, list[float]]:
    """Mẫu của một lượt đẩy xong từ các mốc đã lưu trong `pending.timing`: `published` (live-sync ghi revision), `picked`
    (bắt đầu dựng), `built` (dựng xong), `zalo` (danh sách giây của chặng `zalo`). Thiếu mốc nào thì bỏ chặng cần mốc đó."""
    def stamp(key: str) -> float | None:
        value = timing.get(key)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

    published, picked, built = stamp("published"), stamp("picked"), stamp("built")
    out: dict[str, list[float]] = {"zalo": [value for value in timing.get("zalo") or [] if seconds(value) is not None][:PER_STEP]}
    if picked is not None and built is not None:
        out["build"], out["push"] = [built - picked], [pushed - built]
        if published is not None:
            out["agent"], out["total"] = [picked - published], [pushed - published]
    return out


class Latency:
    def __init__(self, state: Path, persist: bool = True):
        self.path = Path(state) / FILE
        self.persist = persist
        self.samples: dict[str, list[list[float]]] = {stage: [] for stage in STAGES}
        saved = read_json(self.path) if persist else None
        if isinstance(saved, dict):   # file hỏng hay sai khuôn thì bắt đầu lại từ rỗng: chỉ là số đo
            for stage in STAGES:
                rows = saved.get(stage) if isinstance(saved.get(stage), list) else []
                self.samples[stage] = [[row[0], value] for row in rows
                                       if isinstance(row, list) and len(row) == 2 and isinstance(row[0], (int, float))
                                       and not isinstance(row[0], bool) and math.isfinite(row[0])
                                       and (value := seconds(row[1])) is not None][-CAP:]

    def record(self, samples: dict[str, list[float]], now: float) -> None:
        added = False
        for stage, values in samples.items():
            for value in values if stage in self.samples else ():
                clean = seconds(value)
                if clean is not None:
                    self.samples[stage].append([round(now, 1), clean])
                    added = True
        for stage in STAGES:
            self.samples[stage] = [row for row in self.samples[stage] if now - row[0] <= KEEP][-CAP:]
        if added and self.persist:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}")
            tmp.write_text(json.dumps(self.samples, separators=(",", ":")), encoding="utf-8")
            retry_io(lambda: os.replace(tmp, self.path))

    def summary(self, now: float) -> dict[str, dict[str, dict]]:
        """`{"hour": {"zalo": {"n", "p50", "p95"}, …}, "day": {…}}`; chặng chưa có mẫu trong cửa sổ: `n` 0, p50 và p95 null."""
        out: dict[str, dict[str, dict]] = {}
        for window, span in WINDOWS:
            out[window] = {}
            for stage in STAGES:
                values = [value for at, value in self.samples[stage] if 0 <= now - at <= span]
                out[window][stage] = {"n": len(values), "p50": percentile(values, 0.5) if values else None,
                                      "p95": percentile(values, 0.95) if values else None}
        return out
