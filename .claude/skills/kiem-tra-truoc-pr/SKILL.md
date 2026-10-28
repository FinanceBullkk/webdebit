---
name: kiem-tra-truoc-pr
description: Kiểm tra bắt buộc trước khi commit hoặc mở PR trong repo webdebit: check, quét secrets, rà diff, đối chiếu phạm vi. Dùng khi người dùng nói "sẵn sàng PR", "kiểm trước commit" hoặc khi chuẩn bị mở PR.
allowed-tools: Bash(npm run check), Bash(node scripts/check-secrets.js*), Bash(git status*), Bash(git diff*), Bash(git log*), Read, Grep, Glob
---

**Mục đích:** bảo đảm nhánh chỉ chứa phần nhiệm vụ, sạch secrets/dữ liệu thật và `npm run check` xanh.

**Phạm vi file:** chỉ đọc; không sửa, không stage.

**Các bước**
1. `git status` và `git diff --stat`: mọi file đều thuộc nhiệm vụ; không có `captures/`, dump, `.env*`, export Sheet, ảnh khách.
2. `node scripts/check-secrets.js` (diff đã stage; thêm `--all` để quét mọi file đã theo dõi). Phải thoát 0.
3. `npm run check`. Ghi rõ bước nào SKIP (ví dụ chưa cài Chromium).
4. Đọc diff: tên khách, số dư thật, Sheet ID, chi tiết SSH, quy tắc tiền khớp `AGENTS.md`.
5. Nếu đổi cấu trúc hoặc thành phần Harness: `MAP.md` đã cập nhật.

**Hoàn thành khi:** có báo cáo gồm lệnh đã chạy, kết quả thật, các SKIP và việc còn lại.

**Điều cấm:** commit, push, mở hay merge PR trong skill này (skill chỉ kiểm; quyền merge của phiên chính theo `CLAUDE.md`); sửa code để cho kiểm xanh nếu không nằm trong nhiệm vụ; in giá trị secret ra báo cáo.
