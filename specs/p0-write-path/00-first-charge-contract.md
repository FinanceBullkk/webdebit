# T1 — Hợp đồng nghiệp vụ cho charge chuyến đầu tiên

Ngày chốt: 15/10/2026; cập nhật 17/10/2026 theo NEWTRIP-01, ALT-KEY-01, BOOKING-EDIT-01 và [OPENING-FINAL, LEGACY-A, PRICE-ZERO, PRICE-MAKER, SIMPLIFY](../../docs/decisions.md). Người quyết định: người dùng/chủ nghiệp vụ. Nguồn: xác nhận trong chat gốc, làm rõ trong phiên T3 ngày 15/10/2026 và xác nhận ngày 16/10/2026 sau review độc lập. Mã chuyến theo quyết định [TRIP-KEY](../../docs/decisions.md).

- **Chính sách trong phạm vi dưới đây: ĐÃ CHỐT**, trừ các mục ghi ĐỀ XUẤT hoặc CÒN MỞ.
- **Thiết kế triển khai: ĐỀ XUẤT, chưa được duyệt.** Cách lưu bảng resolution, tên trường và reason code trong fixture là ĐỀ XUẤT.
- **Triển khai/kiểm chứng: chỉ trên fixture CI dữ liệu giả.** Fixture PR #10 ([P0-02](07-identity-revision-implementation.md)) đã cài chính sách 16/10 và được review độc lập; xem [kiểm chứng](../../docs/verification.md). Chưa có app giao dịch, DB production hay bảng nối được duyệt. Tài liệu này không hoàn tất M2 và không mở đường ghi tiền.

## Phạm vi

Một charge mới gồm một chuyến, một khách, một dòng tăng nợ và một kỳ nợ đang mở. Chỉ nhận chuyến có ngày xe nhập kho từ 14/10/2026 trở đi. Ngày xe nhập kho là ngày nghiệp vụ chuyến (trong payload charge: `warehouse_in_date`); `debt_period` là trường độc lập. Kỳ phải được xác nhận đang mở tại lúc xử lý.

Chuyến có ngày xe nhập kho **trước 14/10/2026** là chuyến cũ, ngoài hợp đồng này (OPENING-FINAL, ĐÃ CHỐT 16/10/2026): nợ của chúng thuộc opening 13/10/2026 16:44 và **vẫn nằm trong số dư**, kể cả chuyến không có booking (LEGACY-A). Không nhập thêm, không đẩy ra khỏi số dư, không cộng lần nữa.

Không gồm receipt/Q09, nhập muộn, đảo, login thật, API ghi, migration, DB hoặc Google Sheet thật.

## Điều kiện hợp đồng

1. **Không cộng trùng opening.** Opening được chọn là replay ngày 13/10/2026 16:44 và đủ cho mọi chuyến trước 14/10 (OPENING-FINAL). Charge mới, ngày xe từ 14/10, chỉ được xử lý khi kết luận "chuyến chưa nằm trong opening" có **resolution theo mã chuyến (`trip_key`)** tự động theo NEWTRIP-01 khi có tập tham chiếu và không có dấu hiệu trùng; dấu hiệu trùng giữ CHỜ KIỂM để chủ nghiệp vụ kết luận. Chỉ ngày xe không thay được kiểm trùng.
   - Mã chuyến = số booking + số container, viết hoa và bỏ mọi khoảng trắng (TRIP-KEY, chốt 15/10/2026). Chuyến mới thiếu container ở CHỜ KIỂM, ngoài số dư; thiếu booking dùng mã thay thế theo ALT-KEY-01, định dạng chi tiết vẫn ĐỀ XUẤT. Không tự suy định danh ngoài chính sách đã chốt.
   - ĐỀ XUẤT: resolution là bảng theo `trip_key`, NEWTRIP-01 tự tạo khi có tập tham chiếu, người có thẩm quyền kết luận ngoại lệ; trạng thái `ABSENT_FROM_OPENING_APPROVED`, `IN_OPENING`, `UNRESOLVED`. Chỉ `ABSENT_FROM_OPENING_APPROVED` mới đủ điều kiện duyệt; mọi trạng thái khác và việc không có dòng đều là CHỜ KIỂM. Bảng rỗng mặc định chặn mọi charge. Tập tham chiếu và bảng resolution production vẫn CÒN MỞ.
   - Sổ opening không ghi booking: bảng nối dòng opening ↔ mã chuyến là ĐỀ XUẤT, lưu ngoài repo; bảng nối lịch sử 15/10 chỉ gồm chuyến cũ trước 14/10, không cần duyệt từng dòng theo quyết định 17/10. Container/ngày chỉ dùng để lập bảng nối, không là khóa.
2. **Kỳ nợ độc lập với ngày nghiệp vụ.** UI sau này gợi ý tháng xe nhập kho. Maker phải xác nhận `debt_period` theo nguồn. Nếu chọn kỳ khác tháng được gợi ý, phải có lý do và chứng cứ; checker duyệt đúng revision. Gợi ý không tự quyết kỳ.
3. **Xác nhận giá theo chuyến.** Mỗi chuyến có danh sách cấu phần và số tiền riêng; không dùng công thức chung. Chủ nghiệp vụ (vai trò xác nhận giá) duyệt danh sách và tổng tại đúng revision. Các cấu phần phải khớp nguồn và khớp chính xác tổng.
   - **Maker được phép đồng thời là người xác nhận giá** và tự xác nhận giá chuyến mình nhập, không cần xác nhận thứ hai (PRICE-MAKER, ĐÃ CHỐT 16/10/2026).
   - **Người xác nhận giá không được checker-approve cùng revision đó**, và maker ≠ checker theo D01. Xác nhận giá vẫn riêng với checker approval.
4. **Giữ ngoại lệ chờ kiểm.** Thiếu hoặc lệch cấu phần, tổng trống hoặc 0, cấu phần trống (NULL), thiếu container hoặc thiếu mã chuyến hợp lệ theo TRIP-KEY/ALT-KEY-01, thiếu resolution theo mã chuyến hoặc resolution không phải `ABSENT_FROM_OPENING_APPROVED`, và thiếu xác nhận giá đều giữ CHỜ KIỂM và ngoài số dư. Không tự điền, làm tròn, suy định danh hay suy giá.
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
| Chuyến mới thiếu container hoặc mã chuyến hợp lệ | **Chờ kiểm, ngoài số dư** | Thiếu booking dùng mã thay thế theo ALT-KEY-01; dấu hiệu trùng vẫn chặn. |
| Mã chuyến đã có chuyến/khoản khác (đã nhập hoặc có posting), thêm một khoản (ví dụ phí thêm) | **Chờ kiểm, ngoài số dư** | DUP-01: mỗi mã chuyến chỉ một charge ở v1; khoản thứ hai, kể cả phí bổ sung, chờ chính sách riêng. |
| Thiếu/lệch cấu phần, tổng trống/0, hoặc tổng không khớp cấu phần | **Chờ kiểm, ngoài số dư** | Giá chưa được xác nhận đầy đủ và chính xác. |
| Tổng > 0, cấu phần khớp tổng, có một cấu phần 0đ | **Cảnh báo; vẫn được xác nhận giá** | PRICE-ZERO. Các điều kiện khác vẫn áp dụng. |
| Maker tự xác nhận giá chuyến mình nhập; checker khác duyệt | **Đủ điều kiện theo hợp đồng** | PRICE-MAKER; maker ≠ checker. |
| Người xác nhận giá checker-approve cùng revision đó (kể cả maker) | **Từ chối duyệt** | Xác nhận giá riêng với checker approval; cần checker khác cho revision đó. |
| Maker xác nhận kỳ khác tháng được UI gợi ý; nguồn và lý do/chứng cứ hỗ trợ; kỳ còn mở; checker khác duyệt cùng revision | **Đủ điều kiện theo hợp đồng** | Kỳ độc lập; lệch gợi ý có căn cứ và được checker duyệt. |
| Đổi tiền, kỳ, ngày, nguồn hoặc chứng cứ sau xác nhận/approval | **Từ chối dùng revision cũ; chờ revision mới** | Phải xác nhận giá và checker approval lại trên revision mới. |

## Còn mở trước triển khai

- Cách duyệt bảng nối opening ↔ mã chuyến đã chốt ở [JOIN-01](../../docs/decisions.md) (gợi ý khi đúng một ứng viên, chủ nghiệp vụ duyệt từng dòng, chứng cứ tối thiểu, thu hồi chặn ngay). Ngưỡng 3 ngày hai chiều đã chốt 17/10/2026; chuyến từ 14/10 không còn cần duyệt từng dòng nối mà theo [NEWTRIP-01](../../docs/decisions.md) (tự động khi không có dấu hiệu trùng, đã cài trong fixture P0-02). Ngoài fixture dữ liệu giả vẫn chưa có charge nào đủ điều kiện.
- Booking trống hoặc chỉ ký hiệu ("/") dùng mã thay thế theo [ALT-KEY-01](../../docs/decisions.md) (17/10/2026); định dạng mã thay thế trong fixture P0-02 là ĐỀ XUẤT.
- Chặn trùng đã chốt theo chuyến ([DUP-01](../../docs/decisions.md)); chính sách phí bổ sung CÒN MỞ. Booking bị sửa sau khi ghi theo BOOKING-EDIT-01 (giữ phiếu, điều chỉnh/đảo thuộc P0-05); định dạng lưu mã (ĐỀ XUẤT: `trip_key` do DB tính từ booking + container thô, chưa chốt).
- Nhãn hiển thị "chuyến cũ, không truy vết được" và cách app báo chuyến trước 14/10 bị từ chối.
- Danh sách cấu phần và giá được duyệt riêng cho từng chuyến; không dùng danh mục/công thức chung. Fixture đề xuất lưu danh sách trong revision và attestation bất biến theo revision/hash; đây chưa là thiết kế production được duyệt.
- Cách kiểm chứng nguồn, tham chiếu opening, account/role chủ nghiệp vụ và trạng thái CHỜ KIỂM trong app.
- Login thật, API ghi, migration và DB/Sheet thật vẫn ngoài T1; các gate P0 liên quan vẫn áp dụng.

## Cách kiểm và giới hạn

Review tài liệu theo từng điều kiện và ma trận trên; xác nhận mọi nhánh chờ kiểm ở ngoài số dư, chuyến cũ nằm trong opening (không bị đẩy ra), và phân biệt xác nhận kỳ/giá với checker approval. Fixture PostgreSQL chạy trong CI với dữ liệu giả; nó không chứng minh mã chuyến, nguồn hoặc opening thật. Bản `0e1330b` là fixture cũ; PR #10 đã sửa theo SIMPLIFY và được kiểm riêng tại head `a15c7bf` ([38808180498](https://github.com/FinanceBullkk/webdebit/actions/runs/38808180498)). Không có kiểm app giao dịch, DB production, Sheet hoặc nghiệp vụ live.
