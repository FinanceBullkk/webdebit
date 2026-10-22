# MAP — bản đồ repo `webdebit`

Cập nhật file này mỗi khi cấu trúc hoặc thành phần Harness thay đổi. Workspace bao quanh (`D:\webdebit`: captures, release theo ngày, design, worktrees) nằm ngoài Git, xem `../README.md`.

| Vị trí | Vai trò |
| --- | --- |
| `AGENTS.md` | Lan can chung cho mọi agent (nghiệp vụ, an toàn, kiểm tra). `CLAUDE.md` nạp file này và thêm phần Harness |
| `SPEC.md`, `PLAN.md` | Mục tiêu/tiêu chí nghiệm thu và kế hoạch hiện tại |
| `contexte/` | Bối cảnh dự án và tóm tắt quyết định còn hiệu lực. Đọc theo nhiệm vụ |
| `livrables/` | Chỗ đặt sản phẩm bàn giao đã loại dữ liệu nhạy cảm |
| `.claude/settings.json` | Quyền tối thiểu: cho phép lệnh kiểm, hỏi trước push/commit/merge/xóa, cấm force push và đọc secrets |
| `.claude/agents/` | `planner` (chỉ đọc), `implementer` (sửa theo phạm vi), `reviewer` (review, không sửa) |
| `.claude/skills/kiem-tra-truoc-pr/` | Quy trình kiểm trước khi mở PR |
| `scripts/check-secrets.js` | Quét secrets nhẹ (stdlib Node) trên diff đã stage hoặc toàn bộ file đã theo dõi |
| `scripts/sheet-capture/` | Apps Script chỉ ghi vết sửa Sheet nguồn vào log riêng (`Code.gs`) và test giả lập (`test.js`); spec `specs/sheet-capture.md` |
| `scripts/` (còn lại) | `check.js` (`npm run check`), luật nghiệp vụ, `agent-run.ps1` chạy Codex/Gemini |
| `docs/` | Nghiệp vụ, quyết định (`decisions.md`), quy trình (`development.md`, `multi-agent.md`) |
| `specs/` | Spec từng thay đổi, theo `specs/_template.md` |
| `cong-no-web-handoff/` | Mã web/tools/tests (Python + JS) đang phát triển |
| `.github/workflows/test.yml` | CI chạy `npm run check` |

Không tạo, có chủ đích: `.mcp.json` (chưa cần MCP cho dự án), `.env.example` (mã chỉ đọc vài biến `WEBDEBIT_*`/`PG*`, không nạp `.env`), `sources/` (đã có `docs/source-register.md`), `.claude/rules/` (nội dung đã nằm trong `AGENTS.md`).
