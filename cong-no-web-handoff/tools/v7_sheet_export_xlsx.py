#!/usr/bin/env python3
"""Tải bản .xlsx của một Google Sheet bằng tài khoản dịch vụ, chỉ đọc (đối soát cuối tháng).

Chạy trên hao dưới user runner, cùng file biến môi trường với runner giá (WEBDEBIT_SHEET_ID là sổ gốc):

    v7_sheet_export_xlsx.py --output /var/lib/webdebit-sheet-sync/export/so-goc-YYYYMMDD.xlsx

Tải xlsx cần scope drive.readonly (vẫn chỉ đọc file đã chia sẻ cho tài khoản dịch vụ); các runner khác giữ
spreadsheets.readonly. File ra mode 600, không ghi đè file có sẵn. Stdout chỉ có số byte và sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import urllib.request
from collections.abc import Callable
from typing import Any

import sheet_sync_runner as runner

DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"


def export(spreadsheet_id: str, token: str, output: pathlib.Path,
           opener: Callable[..., Any] = urllib.request.urlopen) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", spreadsheet_id):
        raise ValueError("invalid spreadsheet ID")
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    digest, size = hashlib.sha256(), 0
    with opener(request, timeout=300) as response, output.open("xb") as stream:
        while chunk := response.read(1 << 20):
            stream.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    os.chmod(output, 0o600)
    with output.open("rb") as stream:
        is_zip = stream.read(2) == b"PK"
    if not is_zip:
        output.unlink()
        raise ValueError("response is not an xlsx file")
    return {"ok": True, "bytes": size, "sha256": digest.hexdigest()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_SHEET_ID"))
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    if not args.spreadsheet_id or not args.credentials:
        parser.error("cần --spreadsheet-id và --credentials (hoặc biến môi trường của runner)")
    try:
        token = runner.exchange_token(runner.load_credentials(args.credentials), scope=DRIVE_READONLY)
        result = export(args.spreadsheet_id, token, args.output)
    except Exception as exc:  # noqa: BLE001  (lỗi thành mã, không in dữ liệu)
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
