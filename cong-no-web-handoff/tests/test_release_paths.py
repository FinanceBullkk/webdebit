"""Gói release lên hao chỉ gồm file chạy thật (audit vận hành 23/11/2026, O9; scripts/deploy/release-paths.txt).

Mọi module mà các unit trên hao nạp phải có trong gói: điểm chạy đọc từ ExecStart trong runbook, rồi lần theo import (cả import
nằm trong hàm). Gói không được có migration, file .sql hay test trình duyệt. Cần git (đọc danh sách file đã commit), không cần DB.
"""

import ast
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "cong-no-web-handoff" / "tools"
WEB = REPO / "cong-no-web-handoff" / "web"
PATHS_FILE = REPO / "scripts" / "deploy" / "release-paths.txt"
RUNBOOK = REPO / "docs" / "v7-deploy-runbook.md"
DEPLOY = REPO / ".github" / "workflows" / "deploy-hao.yml"
ENTRY = re.compile(r"(?:auto-releases/current|<current_link>|<release>)/(cong-no-web-handoff/(?:tools|web)/[\w/.-]+?\.py)\b")


def release_paths() -> list[str]:
    lines = PATHS_FILE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def entry_points() -> set[Path]:
    found = {REPO / match for match in ENTRY.findall(RUNBOOK.read_text(encoding="utf-8"))}
    # API (ExecStart dùng <release>/... với tham số) và runner bản chụp CONT_NGUON (runbook ghi thư mục rồi tên file riêng).
    return found | {WEB / "v7_ledger_api.py", TOOLS / "sheet_sync_runner.py"}


def resolve(name: str, here: Path, level: int) -> list[Path]:
    """File của module `name` (tools/web trên sys.path như lúc chạy; gói tools/zalo_bot; import tương đối trong gói)."""
    if level:
        base = here.parent
        for _ in range(level - 1):
            base = base.parent
        parts = name.split(".") if name else []
        return [base.joinpath(*parts).with_suffix(".py"), base.joinpath(*parts, "__init__.py")]
    parts = name.split(".")
    found = []
    for root in (TOOLS, WEB):
        for depth in range(len(parts), 0, -1):
            found += [root.joinpath(*parts[:depth]).with_suffix(".py"), root.joinpath(*parts[:depth], "__init__.py")]
    return found


def closure(starts: set[Path]) -> set[Path]:
    seen: set[Path] = set()
    stack = list(starts)
    while stack:
        path = stack.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        if path.parent.name == "zalo_bot" or (path.parent / "__init__.py").is_file():
            stack.append(path.parent / "__init__.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                targets = [(alias.name, 0) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                targets = [(module, node.level)] + [(f"{module}.{alias.name}" if module else alias.name, node.level) for alias in node.names]
            else:
                continue
            for name, level in targets:
                stack += [candidate for candidate in resolve(name, path, level) if candidate.is_file()]
    return seen


@unittest.skipUnless(shutil.which("git") and (REPO / ".git").exists(), "cần git và checkout của repo")
class ReleasePathsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        listed = subprocess.run(["git", "ls-files", "-z", "--", *release_paths()], cwd=REPO, capture_output=True, check=True).stdout
        cls.files = {name for name in listed.decode("utf-8").split("\0") if name}

    def test_every_module_a_unit_on_hao_loads_is_shipped(self):
        starts = entry_points()
        names = {path.name for path in starts}
        # Các máy đang chạy từ release (runbook): đọc được thì danh sách điểm chạy không rỗng một cách âm thầm.
        for expected in ("v7_ledger_api.py", "v7_reconcile_auto.py", "v7_watchdog.py", "v7_price_snapshot.py", "sheet_sync_runner.py",
                         "v7_ps_snapshot.py", "v7_zalo_bot.py", "v7_company_info_snapshot.py"):
            self.assertIn(expected, names)
        needed = {path.relative_to(REPO).as_posix() for path in closure(starts)}
        self.assertGreater(len(needed), len(starts))
        self.assertEqual(sorted(needed - self.files), [], "module chạy trên hao mà không có trong release-paths.txt")

    def test_data_files_the_running_code_reads_are_shipped(self):
        for name in ("cong-no-web-handoff/web/debit-note-config.default.json", "cong-no-web-handoff/tools/zalo_bot/requirements.txt",
                     "cong-no-web-handoff/preview/so-khach-v7-live.html", "docs/decisions.md", "docs/business-rules.md"):
            self.assertIn(name, self.files)
        self.assertTrue(any(name.startswith("cong-no-web-handoff/tools/zalo_bot/kenh/") for name in self.files))
        self.assertTrue(any(name.startswith("specs/") and name.endswith(".md") for name in self.files))

    def test_no_migration_sql_browser_test_or_pc_tool_is_shipped(self):
        bad = sorted(name for name in self.files if "/migrations/" in name or name.endswith(".sql")
                     or re.search(r"/preview/test-|/tools/zalo_agent/|/tools/rehearse_|/tools/test_pg_(?!v7_backend|v7_grants)", name))
        self.assertEqual(bad, [])
        self.assertLess(len(self.files), 700)

    def test_deploy_job_archives_exactly_this_list(self):
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("scripts/deploy/release-paths.txt", text)
        self.assertIn('git archive "$SHA" "${paths[@]}"', text)
        self.assertEqual(len(re.findall(r"git archive", text)), 1)


if __name__ == "__main__":
    unittest.main()
