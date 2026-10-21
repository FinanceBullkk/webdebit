# Môi trường agent trên Windows

Tài liệu cục bộ của máy dev (đường dẫn D:/webdebit chỉ là ví dụ). Phạm vi: Claude điều phối Codex trong `D:/webdebit`; không thay `AGENTS.md` hay luật nghiệp vụ.

## Lệnh chuẩn

### Docker / WSL2

Kiểm Docker trước mọi harness:

```powershell
docker info
```

Kết quả kiểm gần nhất: Docker Server `29.7.2`, 4 CPU, `6214496256` byte RAM; các container Penpot và registry đã tự lên lại sau restart.

Cấu hình máy:

```text
%USERPROFILE%/.wslconfig
memory=6GB
processors=4
swap=4GB
```

Docker Desktop:

- `AutoStart=true`
- `UseResourceSaver=false`
- WSL2 backend

Nếu Docker lỗi `sailor-ingest.sock`:

1. Dừng toàn bộ `Docker Desktop` và `com.docker.backend`.
2. Xóa `%USERPROFILE%/AppData/Local/Docker/run/sailor-ingest.sock` sau khi process đã dừng.
3. Chạy lại `C:/Program Files/Docker/Docker/Docker Desktop.exe`.
4. Chờ `docker info` thành công rồi mới chạy test.

Không xóa container `penpot-*`, `webdebit-ledger-copy`, `webdebit-v7-read-20261020` khi dọn harness.

### Python / Node trong worktree

Dùng Python duy nhất:

```text
D:/webdebit/repo/.venv/Scripts/python.exe
```

Worktree dùng dependency của checkout chính:

```powershell
$env:NODE_PATH = 'D:/webdebit/repo/node_modules'
$env:PLAYWRIGHT_BROWSERS_PATH = 'D:/webdebit/repo/.playwright-browsers'
$env:PYTHONPATH = 'cong-no-web-handoff'
```

Quy ước đường dẫn: truyền `D:/...` cho Python/Node native; không truyền `/d/...`.

Lệnh đã kiểm:

```powershell
cd D:/webdebit/worktrees/codex-v7-opening-read
$env:NODE_PATH = 'D:/webdebit/repo/node_modules'
$env:PLAYWRIGHT_BROWSERS_PATH = 'D:/webdebit/repo/.playwright-browsers'
npm run test:unit
```

Kết quả: 40/40 pass.

```powershell
cd D:/webdebit/repo
$env:PYTHONPATH = 'cong-no-web-handoff'
D:/webdebit/repo/.venv/Scripts/python.exe -m unittest discover -s cong-no-web-handoff/tests
```

Kết quả: 95/95 pass.

### PostgreSQL harness

Harness ledger chính:

```powershell
D:/webdebit/repo/.venv/Scripts/python.exe D:/webdebit/repo/cong-no-web-handoff/tools/test_pg_ledger_schema.py --report D:/webdebit/worktrees/_logs/test_ledger_schema_report.json
```

Kết quả đã kiểm: exit 0; mọi case pass; `cleanup=verified_and_removed`.

V7 harness hiện nằm trong worktree:

```powershell
D:/webdebit/repo/.venv/Scripts/python.exe D:/webdebit/worktrees/codex-v7-opening-read/cong-no-web-handoff/tools/test_pg_v7_backend.py --list
D:/webdebit/repo/.venv/Scripts/python.exe D:/webdebit/worktrees/codex-v7-opening-read/cong-no-web-handoff/tools/test_pg_v7_backend.py --report D:/webdebit/worktrees/_logs/test_v7_report.json
```

Kết quả môi trường: PostgreSQL 18.6 khởi động được, chạy đủ case, dọn container và volume thành công. Kết quả nghiệp vụ hiện tại: SCHEMA 10 pass; BEHAVIOR 8 pass/5 fail; NEEDS_FUNCTION 3 fail; SKIPPED_OPEN 3. Đây là trạng thái red của nhánh, không phải lỗi Docker.

### Codex chạy nền bền

Script:

```text
D:/webdebit/repo/scripts/codex-detached.ps1
```

Chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:/webdebit/repo/scripts/codex-detached.ps1 `
  -PromptFile D:/webdebit/worktrees/_logs/prompt.txt `
  -Worktree D:/webdebit/worktrees/codex-v7-opening-read `
  -LogDir D:/webdebit/worktrees/_logs/codex-run
```

Script trả ngay `PID` và `LOG_DIR`. Artifact:

```text
codex.pid       PID worker PowerShell
status.json     running/completed/failed, thời gian, exit code, lỗi launcher
exit-code.txt   mã thoát Codex
stdout.log      stdout
stderr.log      stderr + tiến trình Codex
report.md       câu trả lời cuối từ codex -o
```

Kiểm trạng thái:

```powershell
Get-Content D:/webdebit/worktrees/_logs/codex-run/status.json
Get-Process -Id (Get-Content D:/webdebit/worktrees/_logs/codex-run/codex.pid) -ErrorAction SilentlyContinue
Get-Content D:/webdebit/worktrees/_logs/codex-run/exit-code.txt
```

Test thật: process detached hoàn tất sau khi launcher đã thoát; `status=completed`, `exit_code=0`, `report.md=OK`; prompt UTF-8 tiếng Việt không mojibake.

Runner luôn gọi:

```text
codex exec -s workspace-write -c windows.sandbox=unelevated
```

Không dùng `danger-full-access` để cho Codex chạy Docker. Sandbox Windows không có quyền pipe `\\.\pipe\dockerDesktopLinuxEngine`; Claude/người gọi chạy harness Docker bên ngoài sandbox.

### UTF-8

Prompt phải là UTF-8 không BOM. Runner truyền file trực tiếp vào stdin của `node.exe`/Codex và đặt:

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

Không pipe prompt tiếng Việt qua Git Bash vào PowerShell.

## Codex CLI

Đã kiểm:

```text
codex-cli 0.162.1
model gpt-6-sol
provider <proxy tuy chinh>
<URL proxy noi bo, khong ghi vao repo>
```

Không đổi cấu hình `[windows] sandbox` toàn cục. Cờ dòng lệnh của runner là nguồn cấu hình cho lần chạy. Proxy không có lệnh quota chuẩn đã kiểm; xem lỗi quota/rate limit trong `stderr.log`, không đoán số dư.

## Trạng thái worktree

Checkout chính:

```text
D:/webdebit/repo
branch test/pg18-schema-characterization
origin: ahead 88
```

Checkout chính có nhiều file untracked, gồm tài liệu, spec và script điều phối. Không tự dọn, commit, merge hoặc push.

Liệt kê trạng thái thật:

```powershell
git -C D:/webdebit/repo status --short --branch
git -C D:/webdebit/repo worktree list
```

Không suy ra worktree đã merge chỉ từ tên. Dùng `git branch --merged` và lịch sử trước khi đề xuất xóa; mặc định không xóa worktree.

## Lỗi đã biết

- Docker `sailor-ingest.sock`: socket rác bị process cũ giữ; dừng process trước khi xóa.
- Docker tự pause: Resource Saver làm mất named pipe; đã tắt.
- WSL2 3GB gây áp lực RAM khi Penpot + PostgreSQL cùng chạy; đã nâng 6GB, swap 4GB.
- Codex sandbox không dùng được Docker pipe; giữ phân vai agent viết code, orchestrator chạy test.
- Codex chạy bằng `&` hoặc pipe gắn shell có thể chết khi shell đóng; dùng `codex-detached.ps1`.
- PowerShell/Git Bash dễ làm hỏng UTF-8 và biến `$`; dùng file prompt UTF-8 và đường dẫn `D:/...`.
- `python -m unittest discover` từ gốc không tìm đúng import; đặt `PYTHONPATH=cong-no-web-handoff` và `-s cong-no-web-handoff/tests`.
