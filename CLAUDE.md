@AGENTS.md

Vai trò của Claude: từ 29/10/2026 Claude làm hết — spec, backend, frontend, test, review ([`CLAUDE-ALL-01`](docs/decisions/claude-all-01.md)); không giao Codex/Gemini, không bắt buộc mockup Penpot. [docs/multi-agent.md](docs/multi-agent.md) chỉ còn là lịch sử.

## Harness cho Claude Code

- Trước nhiệm vụ lớn, đọc [MAP.md](MAP.md). Chỉ đọc file trong `contexte/` liên quan nhiệm vụ. Mục tiêu và tiêu chí xong: [SPEC.md](SPEC.md); kế hoạch hiện tại: [PLAN.md](PLAN.md).
- Đổi cấu trúc thư mục hoặc thành phần Harness thì cập nhật MAP.md cùng lúc.
- Quyết định nghiệp vụ ổn định ghi ở `docs/decisions/<id>.md`, mục lục ở `docs/decisions.md` (nguồn sống duy nhất); `contexte/` chỉ giữ bối cảnh và con trỏ, không chép lại quyết định.
- Không tạo file thừa, không sửa ngoài phạm vi nhiệm vụ, không tuyên bố xong khi chưa chạy kiểm tra phù hợp (`npm run check`; trước commit thêm `node scripts/check-secrets.js`).
- Agent chuyên biệt ở `.claude/agents/` (planner, implementer, reviewer); quy trình trước PR: skill `kiem-tra-truoc-pr`.
- Làm song song: mỗi phiên một nhánh và một worktree riêng, phạm vi file không chồng nhau. Checkout `repo/` luôn ở `main`; tạo worktree bằng `git -C repo worktree add ../worktrees/<ten> -b <nhanh>` rồi chạy `claude` trong đó (hoặc `claude --worktree <ten>`; `.claude/worktrees/` đã được ignore). Commit nhỏ, push nhánh, mở PR, `npm run check` xanh và review xong mới merge; chỉ dọn worktree sau khi merge và `git status` sạch. Từ 28/10/2026 (người dùng chốt): Claude tự push nhánh của nhiệm vụ, mở PR và merge (squash, repo chỉ cho kiểu này từ 29/10/2026) khi `npm run check`, `node scripts/check-secrets.js` xanh, diff đã tự review và mọi check bắt buộc trên GitHub xanh; merge vào `main` là tự deploy lên `hao` ([docs/hao-auto-deploy.md](docs/hao-auto-deploy.md)), nên sau merge theo dõi job `Deploy hao` tới khi xanh và báo lại; không mở PR tài liệu chỉ để ghi đã triển khai ([quy trình PR](docs/development.md#quy-trình-pr-và-triển-khai)). Sau đó tự dọn worktree và nhánh cục bộ đã merge. Vẫn hỏi người dùng trước: PR có `specs/v7-backend/`, `tools/migrations/`, file `.sql` hoặc loader `v7_load*` (phải triển khai tay theo runbook), PR đổi quy tắc tiền/quyết định chưa chốt, force push, xóa nhánh hoặc dữ liệu không phải của nhiệm vụ.
