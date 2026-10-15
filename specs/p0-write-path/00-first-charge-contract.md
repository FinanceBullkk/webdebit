# T1 — Hợp đồng nghiệp vụ cho charge chuyến đầu tiên

Ngày chốt: 15/10/2026; cập nhật 16/10/2026 theo [OPENING-FINAL, LEGACY-A, PRICE-ZERO, PRICE-MAKER, SIMPLIFY](../../docs/decisions.md). Người quyết định: người dùng/chủ nghiệp vụ. Nguồn: xác nhận trong chat gốc, làm rõ trong phiên T3 ngày 15/10/2026 và xác nhận ngày 16/10/2026 sau review độc lập. Mã chuyến theo quyết định [TRIP-KEY](../../docs/decisions.md).

- **Chính sách trong phạm vi dưới đây: ĐÃ CHỐT**, trừ các mục ghi ĐỀ XUẤT hoặc CÒN MỞ.
- **Thiết kế triển khai: ĐỀ XUẤT, chưa được duyệt.** Cách lưu bảng resolution, tên trường và reason code trong fixture là ĐỀ XUẤT.
- **Triển khai/kiểm chứng: CHƯA THỰC HIỆN theo chính sách cập nhật 16/10.** Fixture tại `0e1330b` (CI, dữ liệu giả) kiểm một phiên bản cũ hơn của hợp đồng; xem điều 3–4 và [kiểm chứng](../../docs/verification.md). Tài liệu này không hoàn tất M2 và không mở đường ghi tiền.

## Phạm vi

Một charge mới gồm một chuyến, một khách, một dòng tăng nợ và một kỳ nợ đang mở. Chỉ nhận chuyến có ngày xe nhập kho từ 14/10/2026 trở đi. Ngày xe nhập kho là ngày nghiệp vụ chuyến (trong payload charge: `warehouse_in_date`); `debt_period` là trường độc lập. Kỳ phải được xác nhận đang mở tại lúc xử lý.

Chuyến có ngày xe nhập kho **trước 14/10/2026** là chuyến cũ, ngoài hợp đồng này (OPENING-FINAL, ĐÃ CHỐT 16/10/2026): nợ của chúng thuộc opening 13/10/2026 16:44 và **vẫn nằm trong số dư**, kể cả chuyến không có booking (LEGACY-A). Không nhập thêm, không đẩy ra khỏi số dư, không cộng lần nữa.

Không gồm receipt/Q09, nhập muộn, đảo, login thật, API ghi, migration, DB hoặc Google Sheet thật.

## Điều kiện hợp đồng

1. **Không cộng trùng opening.** Opening được chọn là replay ngày 13/10/2026 16:44 và đủ cho mọi chuyến trước 14/10 (OPENING-FINAL). Charge mới, ngày xe từ 14/10, chỉ được xử lý khi kết luận "chuyến chưa nằm trong opening" có **resolution theo mã chuyến (`trip_key`)** do chủ nghiệp vụ duyệt, kèm tham chiếu chứng cứ. Ngày xe từ 14/10 không tự chứng minh điều đó.
   - Mã chuyến = số booking + số container, viết hoa và bỏ mọi khoảng trắng (TRIP-KEY, chốt 15/10/2026). Chuyến mới thiếu booking hoặc container ở CHỜ KIỂM, ngoài số dư. Không suy định danh từ container, ngày, khách hoặc tổ hợp các trường này.
   - ĐỀ XUẤT: resolution là bảng theo `trip_key`, chỉ người có thẩm quyền do chủ nghiệp vụ duyệt mới ghi; trạng thái `ABSENT_FROM_OPENING_APPROVED`, `IN_OPENING`, `UNRESOLVED`. Chỉ `ABSENT_FROM_OPENING_APPROVED` mới đủ điều kiện duyệt; mọi trạng thái khác và việc không có dòng đều là CHỜ KIỂM. Bảng rỗng mặc định chặn mọi charge. Bảng production chỉ thiết kế sau khi chủ nghiệp vụ duyệt bảng nối (CÒN MỞ).
   - Sổ opening không ghi booking: bảng nối dòng opening ↔ mã chuyến là ĐỀ XUẤT, lưu ngoài repo, chỉ có hiệu lực khi chủ nghiệp vụ duyệt từng dòng. Container/ngày chỉ dùng để lập bảng nối, không là khóa.
2. **Kỳ nợ độc lập với ngày nghiệp vụ.** UI sau này gợi ý tháng xe nhập kho. Maker phải xác nhận `debt_period` theo nguồn. Nếu chọn kỳ khác tháng được gợi ý, phải có lý do và chứng cứ; checker duyệt đúng revision. Gợi ý không tự quyết kỳ.
3. **Xác nhận giá theo chuyến.** Mỗi chuyến có danh sách cấu phần và số tiền riêng; không dùng công thức chung. Chủ nghiệp vụ duyệt danh sách và tổng tại đúng revision. Các cấu phần phải khớp nguồn và khớp chính xác tổng.
   - **Maker được tự xác nhận giá** của chuyến mình nhập (PRICE-MAKER, ĐÃ CHỐT 16/10/2026).
   - **Người xác nhận giá không được checker-approve cùng revision đó**, và maker ≠ checker theo D01. Xác nhận giá vẫn riêng với checker approval.
4. **Giữ ngoại lệ chờ kiểm.** Thiếu hoặc lệch cấu phần, tổng trống hoặc 0, cấu phần trống (NULL), thiếu booking hoặc container để tạo mã chuyến, thiếu resolution theo mã chuyến hoặc resolution không phải `ABSENT_FROM_OPENING_APPROVED`, và thiếu xác nhận giá đều giữ CHỜ KIỂM và ngoài số dư. Không tự điền, làm tròn, suy định danh hay suy giá.
   - **Cấu phần 0đ chỉ là cảnh báo** (PRICE-ZERO, ĐÃ CHỐT 16/10/2026): khi tổng > 0 và các cấu phần khớp tổng, một cấu phần 0đ (ví dụ phí được miễn) không chặn xác nhận giá; hiển thị cảnh báo cho người xác nhận. Tổng 0 hoặc trống vẫn CHỜ KIỂM. Cấu phần trống/NULL không phải 0đ.
5. **Tiền chính xác.** Dùng VND nguyên; tổng phải khớp chính xác với cấu phần. Blank/NULL không phải 0.
6. **Revision và duyệt lại.** Sửa tiền/cấu phần, kỳ, ngày xe nhập kho, nguồn hoặc chứng cứ tạo revision mới. Xác nhận giá lại tại revision mới; checker duyệt lại revision mới. Approval cũ không áp dụng cho nội dung đã đổi. Áp dụng Q02 cho mọi trường nghiệp vụ còn lại.
7. **Số dư.** Chờ kiểm, chờ xác nhận hoặc chờ duyệt không làm đổi số dư. T1 không xác nhận rằng đường posting đã triển khai hay được phép dùng.

## Ma trận ví dụ

| Trường hợp | Kết quả | Điều kiện/lý do |
|---|---|---|
| Ngày xe nhập kho **trước 14/10/2026** (kể cả không có booking) | **Từ chối nhập charge; nợ thuộc opening, vẫn nằm trong số dư** | OPENING-FINAL, LEGACY-A. Không cộng lần nữa, không đẩy ra khỏi số dư; nhãn "chuyến cũ, không truy vết được" là việc hiển thị, chưa triển khai. |
| Chuyến nhập kho 14/10/2026 trở đi; có mã chuyến booking + container; resolution theo `trip_key` là `ABSENT_FROM_OPENING_APPROVED` do chủ nghiệp vụ duyệt; cấu phần riêng đủ, khớp nguồn và tổng; giá đã xác nhận tại revision; maker xác nhận kỳ đang mở; checker khác duyệt cùng revision | **Đủ điều kiện sau khi hoàn tất các gate còn mở** | Trên fixture dữ liệu giả có thể seed resolution để kiểm đường thành công; ngoài test, bảng rỗng nên mặc định chặn. |
| Ngày xe nhập kho 14/10 trở đi nhưng không có resolution theo mã chuyến | **Chờ kiểm, ngoài số dư** | Ngày không chứng minh chuyến vắng mặt trong snapshot. |
| Resolution là `IN_OPENING` hoặc `UNRESOLVED` | **Chờ kiểm, ngoài số dư** | Chuyến đã nằm trong opening hoặc chưa phân giải; không cộng lần nữa. |
| Chuyến mới thiếu booking hoặc container để tạo mã | **Chờ kiểm, ngoài số dư** | Không xác định được chuyến; không dùng container/ngày/khách thay thế. |
| Mã chuyến đã có chuyến/khoản khác (đã nhập hoặc có posting), thêm một khoản (ví dụ phí thêm) | **Chờ kiểm, ngoài số dư** | CÒN MỞ: chặn trùng theo chuyến hay theo chuyến + loại phí; không tự kết luận trùng hay khoản mới. |
| Thiếu/lệch cấu phần, tổng trống/0, hoặc tổng không khớp cấu phần | **Chờ kiểm, ngoài số dư** | Giá chưa được xác nhận đầy đủ và chính xác. |
| Tổng > 0, cấu phần khớp tổng, có một cấu phần 0đ | **Cảnh báo; vẫn được xác nhận giá** | PRICE-ZERO. Các điều kiện khác vẫn áp dụng. |
| Maker tự xác nhận giá chuyến mình nhập; checker khác duyệt | **Đủ điều kiện theo hợp đồng** | PRICE-MAKER; maker ≠ checker. |
| Người xác nhận giá checker-approve cùng revision đó (kể cả maker) | **Từ chối duyệt** | Xác nhận giá riêng với checker approval; cần checker khác cho revision đó. |
| Maker xác nhận kỳ khác tháng được UI gợi ý; nguồn và lý do/chứng cứ hỗ trợ; kỳ còn mở; checker khác duyệt cùng revision | **Đủ điều kiện theo hợp đồng** | Kỳ độc lập; lệch gợi ý có căn cứ và được checker duyệt. |
| Đổi tiền, kỳ, ngày, nguồn hoặc chứng cứ sau xác nhận/approval | **Từ chối dùng revision cũ; chờ revision mới** | Phải xác nhận giá và checker approval lại trên revision mới. |

## Còn mở trước triển khai

- Chủ nghiệp vụ duyệt bảng nối opening ↔ mã chuyến, gồm quy tắc chọn booking theo ngày khi một container có nhiều booking, và cách duyệt (ai, chứng cứ gì). Cho đến khi duyệt, không có charge nào đủ điều kiện ngoài fixture dữ liệu giả.
- Dấu "/" trong ô booking: ĐỀ XUẤT coi là thiếu booking (CHỜ KIỂM); chưa chốt.
- Chặn trùng theo chuyến hay theo chuyến + loại phí khi một chuyến có nhiều khoản; xử lý booking bị sửa sau khi ghi; định dạng lưu mã.
- Nhãn hiển thị "chuyến cũ, không truy vết được" và cách app báo chuyến trước 14/10 bị từ chối.
- Danh sách cấu phần và giá được duyệt riêng cho từng chuyến; không dùng danh mục/công thức chung. Fixture đề xuất lưu danh sách trong revision và attestation bất biến theo revision/hash; đây chưa là thiết kế production được duyệt.
- Cách kiểm chứng nguồn, tham chiếu opening, account/role chủ nghiệp vụ và trạng thái CHỜ KIỂM trong app.
- Login thật, API ghi, migration và DB/Sheet thật vẫn ngoài T1; các gate P0 liên quan vẫn áp dụng.

## Cách kiểm và giới hạn

Review tài liệu theo từng điều kiện và ma trận trên; xác nhận mọi nhánh chờ kiểm ở ngoài số dư, chuyến cũ nằm trong opening (không bị đẩy ra), và phân biệt xác nhận kỳ/giá với checker approval. Fixture PostgreSQL chạy trong CI với dữ liệu giả; nó không chứng minh mã chuyến, nguồn hoặc opening thật. Tại `0e1330b` fixture chưa cài đúng hợp đồng cập nhật này (còn dùng `trip_code` mờ đục, resolver cố định chặn mọi charge, chặn cấu phần 0đ, xác nhận giá bằng vai trò riêng); việc sửa fixture theo SIMPLIFY thuộc PR code riêng và chưa chạy. Không có kiểm app, DB, Sheet hoặc nghiệp vụ live.
