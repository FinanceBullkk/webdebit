# MERGE-QUEUE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Repo chuyển từ tài khoản cá nhân sang organization `ThienThanhLogs` (`ThienThanhLogs/webdebit`) để dùng **merge queue** của GitHub. Merge queue chỉ bật được cho repo thuộc organization. Nó thay luật "nhánh phải theo kịp `main` trước khi merge" (`strict`) của ruleset `main`.

- PR có `ci-ok` xanh thì vào hàng đợi (`gh pr merge <số> --squash`, hoặc nút *Merge when ready*). Không cần `gh pr update-branch` nữa.
- Hàng đợi ghép PR lên `main` mới nhất, chạy lại workflow `Tests` ở sự kiện `merge_group` rồi mới squash vào `main`. Nhiều PR có thể kiểm chung một lượt; nhóm đỏ thì hàng đợi tự tách PR hỏng ra.
- Required check vẫn chỉ là `ci-ok`. Workflow `Tests` lắng nghe `merge_group`; job `changes` lọc file theo `merge_group.base_sha...head_sha`, nên nhóm chỉ đổi tài liệu vẫn bỏ qua các job PostgreSQL.
- `Deploy hao` giữ nguyên: chỉ chạy sau `Tests` xanh trên lượt push vào `main`.
- Xung đột văn bản vẫn phải tự gộp `origin/main` ở máy như trước. Hàng đợi chỉ bỏ vòng update-branch rồi chờ CI khi nhánh không xung đột.

Tên cũ `FinanceBullkk/webdebit` được GitHub tự chuyển hướng (git và API). Link trong tài liệu cũ giữ nguyên; code đọc API (`v7_nhat_ky.py`) dùng tên mới.

## Ngày / nguồn

25/11/2026, chat. Người dùng hỏi cách chuẩn trong ngành để bớt vòng update-branch rồi chạy lại CI khi nhiều phiên cùng merge (#632 tụt sau `main` hai lần trong một buổi). Claude đưa ba hướng: merge queue, bỏ `strict` rồi dựa vào CI chạy lại trên `main`, hoặc bot tự update-branch. Người dùng chọn "Chuyển repo sang org", tự tạo org `ThienThanhLogs` và gửi link; Claude chuyển repo bằng API.

## Trạng thái

ĐÃ CHỐT (người dùng, 25/11/2026). ĐÃ TRIỂN KHAI trên GitHub 25/11/2026: repo đã chuyển; secrets, environment `hao` (4 secret, 2 biến, luật nhánh được bảo vệ), ruleset `main` và 6 PR đang mở đã sang repo mới. Bật merge queue trong ruleset làm sau khi PR có trigger `merge_group` vào `main`, vì lượt hàng đợi cần `ci-ok` báo kết quả.
