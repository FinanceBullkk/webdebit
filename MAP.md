# MAP — bản đồ repo `webdebit`

Cập nhật file này mỗi khi cấu trúc hoặc thành phần Harness thay đổi. Workspace bao quanh (`D:\webdebit`: captures, release theo ngày, design, worktrees) nằm ngoài Git, xem `../README.md`.

| Vị trí | Vai trò |
| --- | --- |
| `AGENTS.md` | Lan can chung cho mọi agent (nghiệp vụ, an toàn, kiểm tra). `CLAUDE.md` nạp file này và thêm phần Harness |
| `SPEC.md`, `PLAN.md` | Mục tiêu/tiêu chí nghiệm thu và kế hoạch hiện tại |
| `contexte/` | Bối cảnh dự án và con trỏ tới quyết định còn hiệu lực theo từng mảng (không chép nội dung quyết định). Đọc theo nhiệm vụ |
| `livrables/` | Chỗ đặt sản phẩm bàn giao đã loại dữ liệu nhạy cảm |
| `.claude/settings.json` | Quyền: cho phép lệnh kiểm, commit/push/mở và merge PR (Claude tự merge từ 28/10/2026), hỏi trước psql/xóa file (ssh không hỏi từ 30/10/2026, lệnh có psql vẫn hỏi), cấm force push và đọc secrets |
| `.claude/agents/` | `planner.md` (chỉ đọc), `implementer.md` (sửa theo phạm vi), `reviewer.md` (review, không sửa) |
| `.claude/skills/kiem-tra-truoc-pr/` | Quy trình kiểm trước khi mở PR |
| `.claude/skills/thiet-ke-ux/` | Quy trình thiết kế, sửa, review giao diện: bài toán → cấu trúc → thị giác → trạng thái → kiểm bản render; `reference/` có danh sách chống giao diện "AI" và nền tảng học thuật UX/UI kèm nguồn |
| `scripts/check-css-tokens.js` | Bước `lint:tok`: màu viết thẳng, cỡ chữ ngoài thang, bo góc tự đặt, viền một bên trong CSS giao diện không vượt mức trần từng file (`scripts/css-tokens-baseline.json`, chỉ được hạ bằng `--update`) |
| `.claude/skills/go-loi-co-he-thong/` | Gỡ lỗi: nguyên nhân gốc → so mẫu → giả thuyết → test đỏ rồi sửa; bẫy môi trường đã biết (phỏng theo obra/superpowers, MIT) |
| `.claude/skills/kiem-chung-truoc-khi-bao-xong/` | Cổng bằng chứng trước mỗi câu báo xong/xanh/đã triển khai (phỏng theo obra/superpowers, MIT) |
| `scripts/check-secrets.js` | Quét secrets và dữ liệu thật trong tài liệu (số tiền nhóm chấm từ 7 chữ số, số container; stdlib Node) trên diff đã stage hoặc toàn bộ file đã theo dõi; `npm run check` chạy bản `--all` |
| `scripts/hermes-office/` | Quản lý Hermes của tab Máy chạy (`MAY-CHAY-01`): cấu hình container khóa, cổng ra danh sách trắng, script kiểm cách ly, dữ liệu mẫu |
| `scripts/deploy/` | `hao-release.sh` (lệnh bắt buộc của khóa deploy trên `hao`: nhận gói, đổi symlink, kiểm sống, tự quay lại) và `release-paths.txt` (danh sách file được vào gói release; `cong-no-web-handoff/tests/test_release_paths.py` kiểm đủ module mà unit trên `hao` nạp) |
| `scripts/sheet-capture/` | Apps Script chỉ ghi vết sửa Sheet nguồn vào log riêng (`Code.gs`) và test giả lập (`test.js`); spec `specs/sheet-capture.md` |
| `scripts/` (còn lại) | `check.js` (`npm run check`), `run-tests.js` (bộ test JS theo tên file), `flaky-repeat.js` + `flaky-reporter.js` (chạy lặp, đếm test chập chờn), luật nghiệp vụ; `agent-run.ps1` (giao Codex/Gemini) chỉ còn là lịch sử từ 29/10/2026 theo `CLAUDE-ALL-01` |
| `cong-no-web-handoff/tools/zalo_agent_release.ps1` | Triển khai/lùi agent Zalo ở máy `msi`: dựng bản ghim theo SHA của `main` dưới `D:\zalo-agent\releases`, trỏ task `ZaloAgent` sang, chờ tiến trình cũ chết rồi mới khởi động lại, kiểm `agent_version` ở máy và `hao` ([spec](specs/zalo-agent.md#triển-khai-agent-từ-bản-ghim-23112026)) |
| `docs/` | Nghiệp vụ, quyết định (`decisions.md` mục lục + `decisions/<id>.md`), nhật ký triển khai tay (`deploys/`), quy trình (`development.md`; `multi-agent.md` chỉ còn là lịch sử), gói thiết kế debit note v4 (`debit-note-v4/`: SPEC, trang mẫu, dữ liệu mẫu) |
| `docs/van-hanh.md`, `docs/rebuild-hao.md` | Vận hành `hao`: cái gì chạy ở đâu, ai biết khi nó dừng, cách dừng mọi máy ghi; checklist dựng lại máy từ gói cấu hình + dump |
| `specs/` | Spec từng thay đổi, theo `specs/_template.md` |
| `cong-no-web-handoff/` | Mã web/tools/tests (Python + JS) đang phát triển |
| `cong-no-web-handoff/schema/v7_schema_current.pgsql` | SINH TỰ ĐỘNG bởi `tools/v7_schema_snapshot.py`: định nghĩa hiện hành của mọi hàm/view/bảng/quyền V7, mỗi thứ một lần. Đọc ở đây thay vì dò migration; không sửa tay, không chạy trên `hao`; CI so với SQL nguồn |
| `.github/workflows/test.yml` | CI chạy `npm run check` |
| `.github/workflows/flaky-nightly.yml` | Hằng đêm (và chạy tay) chạy bộ test browser 10 lượt trên ubuntu và windows bằng `scripts/flaky-repeat.js`, bảng ca nào đỏ mấy lần; đỏ thì job đỏ ([cách đọc](docs/development.md#job-đêm-tìm-test-chập-chờn)) |
| `.github/workflows/deploy-hao.yml` | Sau `Tests` xanh trên `main`: vào tailnet, kiểm diff (SQL/migration/loader thì dừng), đẩy gói theo `scripts/deploy/release-paths.txt` lên `hao` |
| `.github/dependabot.yml` | Nâng phụ thuộc hằng tuần, gom một PR mỗi hệ (actions ghim SHA, npm, pip; thêm kênh và venv bot Zalo) |

Không tạo, có chủ đích: `.mcp.json` (chưa cần MCP cho dự án), `.env.example` (mã chỉ đọc vài biến `WEBDEBIT_*`/`PG*`, không nạp `.env`), `sources/` (đã có `docs/source-register.md`), `.claude/rules/` (nội dung đã nằm trong `AGENTS.md`).
