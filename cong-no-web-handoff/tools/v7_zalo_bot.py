#!/usr/bin/env python3
"""Bot Zalo hỏi đáp công nợ, tiến trình bộ não (ZALO-BOT-01, specs/zalo-bot.md). Mã ở `zalo_bot/brain.py`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zalo_bot.brain import main

if __name__ == "__main__":
    raise SystemExit(main())
