# T1 — Hợp đồng nghiệp vụ cho charge chuyến đầu tiên

Ngày chốt: 15/10/2026. Người quyết định: người dùng/chủ nghiệp vụ. Nguồn: xác nhận trong chat gốc và làm rõ trực tiếp trong phiên T3 ngày 15/10/2026. Cập nhật cùng ngày: mã chuyến theo quyết định [TRIP-KEY](../../docs/decisions.md).

- **Chính sách trong phạm vi dưới đây: ĐÃ CHỐT.**
- **Thiết kế triển khai: ĐỀ XUẤT, chưa được duyệt.**
- **Triển khai/kiểm chứng: CHƯA THỰC HIỆN.** Tài liệu này không hoàn tất M2 và không mở đường ghi tiền.

## Phạm vi

Một charge mới gồm một chuyến, một khách, một dòng tăng nợ và một kỳ nợ đang mở. Ngày xe nhập kho từ 14/10/2026 trở đi. Ngày xe nhập kho là ngày nghiệp vụ; `debt_period` là trường độc lập. Kỳ phải được xác nhận đang mở tại lúc xử lý.

Không gồm receipt/Q09, nhập muộn, chuyến ngày 13/10/2026, đảo, login thật, API ghi, migration, DB hoặc Google Sheet thật.

## Điều kiện hợp đồng

1. **Không cộng trùng opening.** Opening được chọn là replay ngày 13/10/2026 16:44. Phải đối chiếu chuyến bằng định danh nguồn ổn định với chính snapshot này và lưu tham chiếu chứng cứ cho kết luận chuyến chưa nằm trong opening. Ngày xe nhập kho từ 14/10 trở đi không tự chứng minh điều đó. Định danh ổn định là **mã chuyến = số booking + số container**, viết hoa và bỏ mọi khoảng trắng (TRIP-KEY, chốt 15/10/2026). Chuyến không có booking hoặc không có container để tạo mã phải ở CHỜ KIỂM, ngoài số dư. Không suy định danh từ container, ngày, khách hoặc tổ hợp các trường này. Sổ opening không ghi booking: container/ngày chỉ được dùng để lập bảng nối ĐỀ XUẤT, và một dòng opening chỉ mang mã chuyến khi chủ nghiệp vụ đã duyệt dòng đó. Bảng nối chưa được duyệt và cách chứng minh chuyến vắng khỏi opening chưa chốt, nên chưa có charge đủ điều kiện để duyệt.
2. **Kỳ nợ độc lập với ngày nghiệp vụ.** UI sau này gợi ý tháng xe nhập kho. Maker phải xác nhận `debt_period` theo nguồn. Nếu chọn kỳ khác tháng được gợi ý, phải có lý do và chứng cứ; checker duyệt đúng revision. Gợi ý không tự quyết kỳ.
3. **Xác nhận giá theo chuyến.** Mỗi chuyến có danh sách cấu phần và số tiền riêng; không dùng công thức chung. Chủ nghiệp vụ (người dùng) duyệt danh sách và tổng tại đúng revision. Các cấu phần phải đủ, khớp nguồn và khớp chính xác tổng. Xác nhận này riêng với checker approval; cùng một người không được xác nhận giá rồi checker-approve revision đó. Maker và checker phải là hai người khác nhau theo D01.
4. **Giữ ngoại lệ chờ kiểm.** Thiếu hoặc lệch cấu phần, tổng blank/0, thiếu booking hoặc container để tạo mã chuyến, thiếu đối chiếu opening hoặc thiếu xác nhận giá của chủ nghiệp vụ đều giữ CHỜ KIỂM và ngoài số dư. Không tự điền, làm tròn, suy định danh hay suy giá.
5. **Tiền chính xác.** Dùng VND nguyên; tổng phải khớp chính xác với cấu phần. Blank/NULL không phải 0.
6. **Revision và duyệt lại.** Sửa tiền/cấu phần, kỳ, ngày xe nhập kho, nguồn hoặc chứng cứ tạo revision mới. Chủ nghiệp vụ xác nhận giá lại tại revision mới; checker duyệt lại revision mới. Approval cũ không áp dụng cho nội dung đã đổi. Áp dụng Q02 cho mọi trường nghiệp vụ còn lại.
7. **Số dư.** Chờ kiểm, chờ xác nhận hoặc chờ duyệt không làm đổi số dư. T1 không xác nhận rằng đường posting đã triển khai hay được phép dùng.

## Ma trận ví dụ

| Trường hợp | Kết quả | Điều kiện/lý do |
|---|---|---|
| Tương lai: chuyến nhập kho 14/10/2026 trở đi; có mã chuyến booking + container; đối chiếu đúng opening 13/10 16:44 qua bảng nối đã duyệt chứng minh chuyến chưa có; cấu phần riêng của chuyến đủ, khớp nguồn và tổng; chủ nghiệp vụ xác nhận giá tại revision; maker xác nhận kỳ đang mở; checker khác duyệt cùng revision | **Chỉ đủ điều kiện sau khi hoàn tất các gate còn mở** | Fixture hiện tại cố ý không tạo kết quả thành công cho charge. |
| Ngày xe nhập kho 14/10/2026 trở đi nhưng không có đối chiếu với opening | **Chờ kiểm, ngoài số dư** | Ngày không chứng minh chuyến vắng mặt trong snapshot. |
| Chuyến không có booking hoặc container để tạo mã; hoặc mã chưa đối chiếu được với opening qua bảng nối đã duyệt | **Chờ kiểm, ngoài số dư** | Không xác định được chuyến chưa được tính trong opening; không dùng container/ngày/khách để thay thế. |
| Mã chuyến đã có trong opening theo bảng nối đã duyệt, nhưng phát sinh thêm một khoản (ví dụ phí thêm) | **Chờ kiểm, ngoài số dư** | Chưa chốt chặn trùng theo chuyến hay theo chuyến + loại phí; không tự kết luận là trùng hay là khoản mới. |
| Thiếu/lệch cấu phần, tổng blank/0, hoặc tổng không khớp cấu phần | **Chờ kiểm, ngoài số dư** | Giá chưa được xác nhận đầy đủ và chính xác. |
| Maker xác nhận kỳ khác tháng được UI gợi ý; nguồn và lý do/chứng cứ hỗ trợ; kỳ còn mở; checker khác duyệt cùng revision | **Đủ điều kiện theo hợp đồng** | Kỳ độc lập; lệch gợi ý có căn cứ và được checker duyệt. |
| Người duyệt giá và checker là cùng một người | **Từ chối duyệt** | Xác nhận giá riêng với checker approval; cần checker khác cho revision đó. |
| Đổi tiền, kỳ, ngày, nguồn hoặc chứng cứ sau xác nhận/approval | **Từ chối dùng revision cũ; chờ revision mới** | Phải xác nhận giá và checker approval lại trên revision mới. |

## Còn mở trước triển khai

- Mã chuyến đã chốt (TRIP-KEY). Bảng nối dòng opening ↔ mã chuyến đã lập ở dạng ĐỀ XUẤT, lưu ngoài repo, chờ chủ nghiệp vụ duyệt. Quy tắc chọn booking theo ngày khi một container có nhiều booking chưa được duyệt.
- Chuyến không có booking: chưa quyết cách định danh; giữ CHỜ KIỂM.
- Chặn trùng theo chuyến hay theo chuyến + loại phí khi một chuyến có nhiều khoản; xử lý booking bị sửa sau khi ghi; định dạng lưu mã.
- ĐỀ XUẤT, chưa chốt: chỉ coi một chuyến là vắng khỏi opening khi mã không thuộc bảng nối đã duyệt **và** không còn dòng opening chưa nối (CHỜ KIỂM) cùng số container. Nếu còn dòng như vậy, giữ CHỜ KIỂM để tránh cộng trùng.
- Danh sách cấu phần và giá được duyệt riêng cho từng chuyến; không dùng danh mục/công thức chung. Fixture đề xuất lưu danh sách trong revision và attestation bất biến theo revision/hash; đây chưa là thiết kế production được duyệt.
- Cách kiểm chứng nguồn, tham chiếu opening, account/role chủ nghiệp vụ và trạng thái CHỜ KIỂM trong app còn mở.
- Login thật, API ghi, migration và DB/Sheet thật vẫn ngoài T1; các gate P0 liên quan vẫn áp dụng.

## Cách kiểm và giới hạn

Review tài liệu theo từng điều kiện và ma trận trên; xác nhận mọi nhánh chờ kiểm ở ngoài số dư, đồng thời phân biệt xác nhận kỳ/giá của maker/chủ nghiệp vụ với checker approval. Fixture T3 kiểm guard kỹ thuật riêng; fixture không chứng minh mã chuyến, nguồn hoặc opening thật và vẫn cố ý chặn mọi charge ở approval. Fixture chưa cài mã chuyến TRIP-KEY hay bảng nối opening. Không có kiểm app, DB, Sheet hoặc nghiệp vụ live.
