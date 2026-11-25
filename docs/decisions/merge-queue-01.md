# MERGE-QUEUE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Repo chuyển từ tài khoản cá nhân sang organization `ThienThanhLogs` (`ThienThanhLogs/webdebit`) để dùng **merge queue** của GitHub. Merge queue chỉ bật được cho repo thuộc organization. Nó thay luật "nhánh phải theo kịp `main` trước khi merge" (`strict`) của ruleset `main`.

- PR có `ci-ok` xanh thì vào hàng đợi (`gh pr merge <số>`, không thêm `--squash` vì hàng đợi tự squash; hoặc nút *Merge when ready*). PR chưa xanh thì `gh pr merge <số> --auto`. Không cần `gh pr update-branch` nữa.
- Hàng đợi ghép PR lên `main` mới nhất, chạy lại workflow `Tests` ở sự kiện `merge_group` rồi mới squash vào `main`. Nhiều PR có thể kiểm chung một lượt; nhóm đỏ thì hàng đợi tự tách PR hỏng ra.
- Required check vẫn chỉ là `ci-ok`. Workflow `Tests` lắng nghe `merge_group`; job `changes` lọc file theo `merge_group.base_sha...head_sha`, nên nhóm chỉ đổi tài liệu vẫn bỏ qua các job PostgreSQL.
- `Deploy hao` chạy ngay khi hàng đợi push vào `main`, nếu lượt `Tests` ở `merge_group` đã xanh trên đúng SHA đó. Không chờ lượt `Tests` chạy lại trên `main`; lượt đó vẫn chạy và là đường dự phòng (cùng SHA thì không deploy hai lần). SHA cũ hơn bản đang chạy thì bỏ qua, không deploy lùi.
- Xung đột văn bản vẫn phải tự gộp `origin/main` ở máy như trước. Hàng đợi chỉ bỏ vòng update-branch rồi chờ CI khi nhánh không xung đột.

Thiết lập kèm theo khi chuyển (người dùng duyệt "Làm hết 1–5", 25/11/2026):

- Hàng đợi: squash, nhóm ALLGREEN, tối đa 5 PR mỗi lượt, chờ gom 1 phút, quá 60 phút không có `ci-ok` thì PR bị đẩy ra.
- Bảo mật bật lại vì không theo repo sang org: CodeQL (default setup), secret scanning, chặn push có secret, Dependabot vá lỗi bảo mật.
- Org bắt buộc 2FA. Không bật "chỉ phương thức 2FA an toàn" để không khóa tài khoản đang dùng SMS.
- Bản nâng patch/minor của Dependabot tự vào hàng đợi khi `ci-ok` xanh (`dependabot-auto-merge.yml`); bản nâng major để người xem.

Tên cũ `FinanceBullkk/webdebit` được GitHub tự chuyển hướng (git và API). Link trong tài liệu cũ giữ nguyên; code đọc API (`v7_nhat_ky.py`) dùng tên mới.

## Ngày / nguồn

25/11/2026, chat. Người dùng hỏi cách chuẩn trong ngành để bớt vòng update-branch rồi chạy lại CI khi nhiều phiên cùng merge (#632 tụt sau `main` hai lần trong một buổi). Claude đưa ba hướng: merge queue, bỏ `strict` rồi dựa vào CI chạy lại trên `main`, hoặc bot tự update-branch. Người dùng chọn "Chuyển repo sang org", tự tạo org `ThienThanhLogs` và gửi link; Claude chuyển repo bằng API.

## Trạng thái

ĐÃ CHỐT (người dùng, 25/11/2026). ĐÃ TRIỂN KHAI trên GitHub 25/11/2026: repo đã chuyển; secrets, environment `hao` (4 secret, 2 biến, luật nhánh được bảo vệ), ruleset `main` và 6 PR đang mở đã sang repo mới. Merge queue bật trong ruleset `main` ngày 25/11/2026 sau khi #643 (trigger `merge_group`) vào `main`; `strict` đã tắt.

CÒN MỞ (kiểm ở lượt chạy thật):

- Commit hàng đợi đẩy lên `main` trùng SHA với lượt `merge_group` đã kiểm. Nếu không trùng, đường push của `Deploy hao` báo không qua hàng đợi và deploy đi đường `workflow_run` như cũ, chỉ chậm hơn.
- PR Dependabot được bật auto-merge bằng `GITHUB_TOKEN`: GitHub có thể không chạy workflow cho sự kiện do token này gây ra. Nếu vậy PR vẫn vào `main`, nhưng lên `hao` ở lượt merge sau.
