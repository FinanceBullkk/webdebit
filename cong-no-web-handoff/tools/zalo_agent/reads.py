"""ZALO-AGENT-01 Phần 3: kho kết quả đọc ảnh tại máy, `<root>/<sha256 ảnh>/<engine>@<phiên bản>.json`.

Theo mẫu `insurance-ocr-cache/<sha256>.json`. Chữ OCR đầy đủ và ô chữ nằm trong file này và KHÔNG BAO GIỜ rời máy. Cùng engine và
phiên bản thì không đọc lại; engine hoặc phiên bản mới ghi file mới cạnh file cũ.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .source import read_json, retry_io

SHA = re.compile(r"[0-9a-f]{64}")
ENGINE = re.compile(r"[a-z0-9_-]{1,30}")
VERSION = re.compile(r"[A-Za-z0-9._+-]{1,40}")


def path(root: Path, sha: str, engine: str, version: str) -> Path:
    assert SHA.fullmatch(sha) and ENGINE.fullmatch(engine) and VERSION.fullmatch(version)
    return Path(root) / sha / f"{engine}@{version}.json"


def load(root: Path, sha: str, engine: str, version: str) -> dict | None:
    value = read_json(path(root, sha, engine, version))
    return value if isinstance(value, dict) else None


def save(root: Path, sha: str, result: dict) -> None:
    target = path(root, sha, result["engine"], result["version"])
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    retry_io(lambda: os.replace(tmp, target))


def for_image(root: Path, sha: str) -> list[dict]:
    """Mọi kết quả của một ảnh, theo (engine, phiên bản)."""
    folder = Path(root) / sha
    if not SHA.fullmatch(sha) or not folder.is_dir():
        return []
    reads = (read_json(file) for file in sorted(folder.glob("*@*.json")))
    return [value for value in reads if isinstance(value, dict)]
