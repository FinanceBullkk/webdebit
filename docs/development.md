# Quy trình phát triển chung

## Nguồn sửa chính

Theo lựa chọn người dùng 15/10/2026, GitHub là nơi dev/AI cùng phát triển. Trên PC hiện tại, checkout chính là `repo/` bên trong workspace; đường dẫn cụ thể ở hướng dẫn workspace, không là dependency code/test. Máy khác clone ở vị trí bất kỳ.

Handoff ngoài checkout giữ làm hồ sơ mốc trước chuyển đổi. Release/capture bất biến, không là working tree. Không sửa hai bản song song, không tự copy ngược preview/runtime. Hotfix bên ngoài phải so từng file và có spec/test/provenance trước khi nhập vào nhánh.

Mốc bàn giao `69a84a41382217265f745c1c9ae87cba9e557c16` có 34 file. Bản chia sẻ đổi nhãn fixture, bỏ submit/importer nội bộ và test phụ thuộc. Không lấy số test nội bộ làm số test repo. Chênh CRLF/LF tách khỏi nội dung; `.gitattributes` quy định LF.

## Một vòng thay đổi

1. Kiểm nhánh, HEAD, status/diff, bảo vệ thay đổi của người khác. Một phạm vi một người/agent ghi; khi cần dùng checkout/worktree riêng. Không tự discard/stash/absorb thay đổi chưa rõ chủ.
2. Đọc nghiệp vụ/quyết định, mở spec với tiêu chí quan sát được. Việc nhỏ mô tả trong PR; không cần framework specs.
3. Sửa hẹp, dùng runner hiện có. Regression có ý nghĩa chạy thất bại trước sửa và đạt sau sửa khi khả thi. Map thao tác → entry point → kiểm đúng tầng.
4. Chạy Python, bốn file JS và browser theo README. Nghiệm thu bằng clone sạch có dependency/browser mới; không copy `node_modules` hay dùng cache Hermes làm bằng chứng máy mới.
5. Review mọi diff định đưa lên, kiểm bí mật/nhạy cảm; không copy toàn docs/capture. Commit/PR chỉ gồm phần task khi được phép; review/CI đúng revision trước merge. Không tự push main hoặc mở ghi tiền vì test xanh.
6. Ghi revision/hash, môi trường, kết quả và giới hạn ở `docs/verification.md` hoặc PR. Phân biệt thêm workflow với CI đã chạy; fixture với DB/live.

Nghiệp vụ chia sẻ ở `docs/`, spec ở `specs/`. Hồ sơ ngoài repo là bằng chứng lịch sử theo hash trong [source register](source-register.md). Quyết định mới cập nhật repo, không duy trì hai bản sống. Nội dung nhạy cảm chỉ dẫn tới hồ sơ có quyền riêng, không dán vào issue/CI log/tài liệu.

## Hoàn tác và ranh giới

Thay đổi hiện tại chỉ code/tài liệu/CI. Hoàn tác bằng diff/commit đã review, không xóa capture/release hay đụng DB. CI chỉ chạy fixture. Ghi tiền/deploy cần scope, policy, DB test và quyền riêng theo gate nghiệp vụ.
