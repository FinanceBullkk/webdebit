#!/usr/bin/env python3
"""Bộ câu hỏi mẫu của bot Zalo hỏi đáp (ZALO-BOT-01): đo trước khi bật hay đổi model. Mã ở `zalo_bot/eval.py`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zalo_bot.eval import main

if __name__ == "__main__":
    raise SystemExit(main())
