# Quy trình phát triển chung

## Nguồn sửa chính

Theo lựa chọn người dùng 15/10/2026, GitHub là nơi dev/AI cùng phát triển. Trên PC hiện tại, checkout chính là `repo/` bên trong workspace; đường dẫn cụ thể ở hướng dẫn workspace, không là dependency code/test. Máy khác clone ở vị trí bất kỳ.

Handoff ngoài checkout giữ làm hồ sơ mốc trước chuyển đổi. Release/capture bất biến, không là working tree. Không sửa hai bản song song, không tự copy ngược preview/runtime. Hotfix bên ngoài phải so từng file và có spec/test/provenance trước khi nhập vào nhánh.

Mốc bàn giao `69a84a41382217265f745c1c9ae87cba9e557c16` có 34 file. Bản chia sẻ đổi nhãn fixture, bỏ submit/importer nội bộ và test phụ thuộc. Không lấy số test nội bộ làm số test repo. Chênh CRLF/LF tách khỏi nội dung; `.gitattributes` quy định LF.

## Một vòng thay đổi

1. Kiểm nhánh, HEAD, status/diff, bảo vệ thay đổi của người khác. Một phạm vi một người/agent ghi; khi cần dùng checkout/worktree riêng. Không tự discard/stash/absorb thay đổi chưa rõ chủ.
2. Đọc nghiệp vụ/quyết định, mở spec với tiêu chí quan sát được. Việc nhỏ mô tả trong PR; không cần framework specs.
3. Sửa hẹp, dùng runner hiện có. Regression có ý nghĩa chạy thất bại trước sửa và đạt sau sửa khi khả thi. Map thao tác → entry point → kiểm đúng tầng.
4. Chạy Python, bốn file JS và browser theo README. Nghiệm thu bằng clone sạch, venv mới không kế thừa site-packages, dependency/browser mới; không copy `node_modules` hay dùng cache Hermes/package Python toàn cục làm bằng chứng máy mới.
5. Review mọi diff định đưa lên, kiểm bí mật/nhạy cảm; không copy toàn docs/capture. Commit/PR chỉ gồm phần task khi được phép; review/CI đúng revision trước merge. Không tự push main hoặc mở ghi tiền vì test xanh.
6. Ghi revision/hash, môi trường, kết quả và giới hạn ở `docs/verification.md` hoặc PR. Phân biệt thêm workflow với CI đã chạy; fixture với DB/live.

Nghiệp vụ chia sẻ ở `docs/`, spec ở `specs/`. Hồ sơ ngoài repo là bằng chứng lịch sử theo hash trong [source register](source-register.md). Quyết định mới cập nhật repo, không duy trì hai bản sống. Nội dung nhạy cảm chỉ dẫn tới hồ sơ có quyền riêng, không dán vào issue/CI log/tài liệu.

## Quy trình frontend

ĐÃ CHỐT bởi người dùng/chủ nghiệp vụ ngày 16/10/2026 trong chat: áp dụng đủ các bước dưới đây cho luồng frontend mới hoặc thay đổi đáng kể trong repo. Penpot là nơi duyệt mockup trước khi code frontend. Quy trình không tự cấp quyền triển khai hoặc ghi tiền.

1. **Chốt kết quả nghiệp vụ:** xác định người thao tác, đầu vào, kết quả, điều kiện bị chặn và tiêu chí nghiệm thu. Quy tắc chưa chốt phải ghi CÒN MỞ, không biến lựa chọn trên UI thành chính sách.
2. **Đối chiếu dữ liệu/backend:** đọc nguồn, trường dữ liệu và entry point/API hiện có; ghi phần dùng được, phần thiếu, dữ liệu thật và fixture. Không dựng trường tiền từ giả định.
3. **Dựng luồng và mockup Penpot:** thể hiện màn hình nối nhau và trạng thái bình thường, thành công, trống, thiếu dữ liệu, lỗi, thiếu quyền, chờ duyệt khi áp dụng. Dùng dữ liệu giả trong mockup; không sao chép dữ liệu khách/chứng từ thật vào tài liệu chia sẻ.
4. **Người dùng duyệt mockup:** chốt tên trường, thứ tự thao tác, nguồn và thông báo trước khi code frontend. Ghi liên kết file/page/board, mốc phiên bản và người/ngày/phạm vi duyệt trong spec hoặc PR; không chỉ dẫn bản thiết kế đang thay đổi. Thay đổi luồng sau duyệt phải cập nhật mockup và duyệt lại phần bị ảnh hưởng. Nếu Penpot chưa kết nối hoặc chưa có duyệt, tiếp tục khảo sát/spec/check độc lập; chưa code frontend thuộc phạm vi đó.
5. **Chốt giao tiếp frontend–backend:** thống nhất request/response, validation, lỗi, quyền và trạng thái nghiệp vụ; bổ sung backend cần thiết cho luồng. Backend phải kiểm quyền và điều kiện ghi, không dựa vào nút bị ẩn trên UI.
6. **Code và nối backend:** tái sử dụng thành phần hiện có, đối chiếu mockup đã duyệt. Có thể dùng fixture trước khi API sẵn sàng nhưng phải ghi rõ; chưa coi luồng tích hợp hoàn thành khi vẫn dùng fixture.
7. **Kiểm trình duyệt và tích hợp:** chạy checks hiện có và kiểm bố cục, bàn phím/focus, nhập sai, tải chậm/mất mạng, bấm lặp, thiếu quyền theo phạm vi tác động. Kiểm luồng nối backend trên môi trường thử với dữ liệu giả; phân biệt bằng chứng fixture, tích hợp và live. Không thử ghi trên Sheet/DB thật từ quy trình này.
8. **Nghiệm thu và phát hành:** người dùng đi hết luồng trên môi trường thử, đối chiếu kết quả/nguồn. Ghi revision, môi trường, kết quả và khoảng trống; chỉ phát hành trong phạm vi được phép sau khi tiêu chí đạt. Duyệt mockup không thay nghiệm thu nghiệp vụ, chứng cứ hoặc quyền ghi tiền.

Giữ hồ sơ gọn trong spec/PR hiện có: thao tác → module/API → check → bằng chứng; kèm mockup đã duyệt và các gate còn mở. Không tạo thêm bộ tài liệu song song.

**Sửa nhỏ:** đổi chữ, khoảng cách hoặc sửa lỗi hiển thị mà không đổi luồng, ý nghĩa nghiệp vụ, dữ liệu, quyền hay hành vi không cần mockup/duyệt Penpot mới. Ghi lý do miễn trong PR và kiểm phù hợp phần sửa; không bỏ kiểm accessibility hoặc ranh giới tài chính. Quy trình không buộc làm lại toàn bộ màn hình cũ nếu chúng chưa thuộc phạm vi thay đổi.

**Giới hạn thực thi:** AGENTS.md và quy trình hướng dẫn dev/AI; review phải đối chiếu hồ sơ duyệt và bằng chứng. CI hiện có kiểm code/fixture, chưa tự xác nhận người dùng đã duyệt Penpot hoặc nghiệm thu luồng thật.

## Hoàn tác và ranh giới

Thay đổi hiện tại chỉ code/tài liệu/CI. Hoàn tác bằng diff/commit đã review, không xóa capture/release hay đụng DB. CI chỉ chạy fixture. Ghi tiền/deploy cần scope, policy, DB test và quyền riêng theo gate nghiệp vụ.
