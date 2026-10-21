@AGENTS.md

Vai trò của Claude trong cộng tác nhiều agent: điều phối, chốt spec và review cuối. Xem [docs/multi-agent.md](docs/multi-agent.md).

## Harness cho Claude Code

- Trước nhiệm vụ lớn, đọc [MAP.md](MAP.md). Chỉ đọc file trong `contexte/` liên quan nhiệm vụ. Mục tiêu và tiêu chí xong: [SPEC.md](SPEC.md); kế hoạch hiện tại: [PLAN.md](PLAN.md).
- Đổi cấu trúc thư mục hoặc thành phần Harness thì cập nhật MAP.md cùng lúc.
- Quyết định nghiệp vụ ổn định ghi ở `docs/decisions.md` (nguồn sống duy nhất); `contexte/` chỉ giữ bối cảnh và con trỏ, không chép lại quyết định.
- Không tạo file thừa, không sửa ngoài phạm vi nhiệm vụ, không tuyên bố xong khi chưa chạy kiểm tra phù hợp (`npm run check`; trước commit thêm `node scripts/check-secrets.js`).
- Agent chuyên biệt ở `.claude/agents/` (planner, implementer, reviewer); quy trình trước PR: skill `kiem-tra-truoc-pr`.
- Làm song song: mỗi phiên một nhánh và một worktree riêng, phạm vi file không chồng nhau. Checkout `repo/` luôn ở `main`; tạo worktree bằng `git -C repo worktree add ../worktrees/<ten> -b <nhanh>` rồi chạy `claude` trong đó (hoặc `claude --worktree <ten>`; `.claude/worktrees/` đã được ignore). Commit nhỏ, push nhánh, mở PR, `npm run check` xanh và review xong mới merge; chỉ dọn worktree sau khi merge và `git status` sạch. Push, merge, xóa và force push luôn hỏi người dùng trước.
