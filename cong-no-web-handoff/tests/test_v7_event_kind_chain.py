"""Mọi migration dựng lại ràng buộc loại event phải lồng nhau thành một chuỗi.

Mỗi migration thêm loại event mới đều DROP rồi ADD lại `event_kind_check`/`event_snapshot_check`
với cả danh sách. Hai PR song song mỗi bên chỉ thêm loại của mình thì migration chạy sau trên
`hao` xóa mất loại của bên kia (suýt xảy ra giữa #160 và #161 ngày 29/10/2026). Test này không cần
DB: tập loại của các migration phải lồng nhau (bản nào cũng chứa trọn bản nhỏ hơn), và tập lớn
nhất phải đúng bằng `schema-draft.sql`. PR thứ hai thì gộp `main` và liệt kê đủ.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "cong-no-web-handoff/tools/migrations"
SCHEMA = ROOT / "specs/v7-backend/schema-draft.sql"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def kinds(source: str) -> frozenset | None:
    found = re.search(r"(?s)CONSTRAINT event_kind_check CHECK \(kind IN \((.*?)\)\)", source)
    return frozenset(re.findall(r"'([a-z_]+)'", found.group(1))) if found else None


def snapshot_kinds(source: str) -> frozenset | None:
    found = re.search(r"(?s)CONSTRAINT event_snapshot_check CHECK \(CASE kind(.*?)ELSE false END\)", source)
    return frozenset(re.findall(r"WHEN '([a-z_]+)' THEN", found.group(1))) if found else None


def rebuilt(parse) -> dict[str, frozenset]:
    out = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name.endswith(".rollback.sql"):
            continue
        found = parse(text(path))
        if found is not None:
            out[path.name] = found
    return out


class EventKindChain(unittest.TestCase):
    def check(self, parse):
        schema = parse(text(SCHEMA))
        self.assertIsNotNone(schema, "schema-draft.sql thiếu ràng buộc")
        found = rebuilt(parse)
        self.assertTrue(found, "không tìm thấy migration nào dựng lại ràng buộc")
        for a, sa in found.items():
            for b, sb in found.items():
                if a < b and not (sa <= sb or sb <= sa):
                    self.fail(f"{a} và {b} không lồng nhau: {a} thiếu {sorted(sb - sa)}, {b} thiếu {sorted(sa - sb)}. "
                              "Chạy cái nào sau trên hao cũng làm mất loại của cái kia; migration sau phải liệt kê đủ.")
        biggest = max(found.values(), key=len)
        self.assertEqual(sorted(biggest ^ schema), [], "tập lớn nhất trong migration khác schema-draft.sql")

    def test_event_kind_check(self):
        self.check(kinds)

    def test_event_snapshot_check(self):
        self.check(snapshot_kinds)

    def test_snapshot_covers_every_kind(self):
        self.assertEqual(sorted(kinds(text(SCHEMA)) ^ snapshot_kinds(text(SCHEMA))), [])


if __name__ == "__main__":
    unittest.main()
