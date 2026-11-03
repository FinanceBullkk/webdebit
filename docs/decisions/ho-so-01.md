# HO-SO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Thẻ **Hồ sơ** của trang khách ([`TRANG-KHACH-01`](trang-khach-01.md)) theo khung **HoSoV4** người dùng dựng trên canvas Claude Design. Spec: [`v7-trang-khach.md`](../../specs/v7-trang-khach.md#thẻ-hồ-sơ).

**Bố cục** (thay bố cục bốn khối 2×2 của PR A3):

1. Thứ tự: **Nhận diện** → **Thông tin doanh nghiệp và quan hệ** → **Thỏa thuận làm việc** → **Tài liệu**.
2. **Đầu hồ sơ:** chữ viết tắt, tên giao dịch lớn nhất trang, nhãn phụ (loại khách, hạng khách, tín dụng), mặt hàng · vận chuyển · khu vực, hợp tác từ, người phụ trách; nút **Chỉnh sửa hồ sơ** và **⋯**. Câu tóm tắt quan hệ chỉ hiện khi đã lưu.
3. **Không có dải cảnh báo ở đầu.** Cảnh báo gắn vào đúng mục: Gần/Vượt hạn mức nằm trong mục Hạn mức; hợp đồng sắp hết hạn nằm trong mục Hợp đồng; giá hết hạn nằm ở dòng giá đó.
4. **Hai cột 62/38**, phân cách bằng đường kẻ mảnh, không chia ô (card). Cột trái: Thông tin doanh nghiệp, Thỏa thuận làm việc (thanh toán, hạn mức, hợp đồng), Giá và phụ phí áp dụng. Cột phải: Người liên hệ, Nhóm trao đổi, Ghi chú khi làm việc, Tài liệu.
5. **Nhóm trao đổi** chỉ hiện khi sổ đã gắn group Zalo ([`ZALO-GROUP-01`](zalo-group-01.md)).
6. **Nút có chữ.** Nút của tính năng chưa có backend vẫn hiện nhưng bấm thì báo rõ "chưa lưu được" — không im lặng, không giả như đã lưu.
7. **Bỏ khối Ảnh chứng từ** khỏi Hồ sơ: ảnh xem ở phiếu thu của thẻ Sổ (CHUNG-TU-01). Nút "Xem bảng giá" và sửa phụ phí mở khung có sẵn ở thẻ Sổ.

**Bốn quy tắc** (khung QuyTac, "Đã duyệt 02/11/2026"), tính theo từng sổ, bám [`DASH-03`](dash-03.md) và K5 của TRANG-KHACH-01:

1. **Hạng khách — khách quan trọng cỡ nào.** Doanh thu 12 tháng đã kết thúc (phát sinh đã có giá, kể cả phụ phí); sắp sổ từ cao xuống, cộng dồn; tính lại ngày 1 hằng tháng.
   - **Khách lớn:** nhóm đầu, cộng dồn tới 80% tổng doanh thu.
   - **Khách vừa:** tiếp theo, tới 95%.
   - **Khách nhỏ:** phần còn lại.
   - **Khách mới:** chuyến đầu tiên chưa đủ 3 tháng.
   - **Ngừng đi hàng:** không có chuyến nào trong 12 tháng.
2. **Hạng tín dụng — khách có đáng tin không.** Số ngày trả trễ từng tháng nợ trong 12 tháng (K5), trung bình theo tiền; tháng còn nợ đếm tới hôm nay.
   - **Tín dụng tốt:** trễ trung bình ≤ 0 ngày.
   - **Tín dụng khá:** 1–30 ngày.
   - **Cần theo dõi:** 31–60 ngày, hoặc đang có nợ quá hạn.
   - **Tín dụng xấu:** trên 60 ngày, hoặc đang rủi ro cao ở Tổng quan.
   - **Chưa đủ dữ liệu:** đo được dưới 3 tháng nợ.
3. **Hạn mức nợ.** Đặt tay cho từng sổ, VND nguyên. **Chưa đặt** = chưa giới hạn, không cảnh báo (không phải hạn mức 0). Ai vào app cũng đặt được ([`V7-ID`](v7-id.md)); mỗi lần ghi người làm, ngày, trước → sau, **lý do bắt buộc**. Mức dùng = Còn nợ ÷ hạn mức; chuyến chưa giá, chờ kiểm không tính.
4. **Vượt hạn mức chỉ cảnh báo, không chặn.** Dưới 80% bình thường; 80–99% **Gần hạn mức** (cam); từ 100% **Vượt hạn mức** (đỏ). Hiện ở Hồ sơ, Tình hình, Đòi nợ; nhập chuyến thì nhắc một dòng, vẫn ghi được. Lý do không chặn: đang chạy song song với Sheet ([`SONG-SONG-01`](song-song-01.md)) và DASH-03 chỉ tô màu.

## Ngày / nguồn

2/11/2026, người dùng chốt qua chat và canvas Claude Design (trang "Hồ sơ": khung HoSoV4 với bốn khách giả, ghi chú `hosov4` và `hosobangiao`; khung QuyTac ghi "Đã duyệt 02/11/2026"). Claude ghi lại ngày 3/11/2026 theo giao việc của phiên điều phối, trước khi code.

## Hiệu lực và giới hạn

ĐÃ CHỐT bố cục và bốn quy tắc.

- **Giai đoạn A (code 3/11/2026):** chỉ hiện dữ liệu web đã có — mặt hàng · vận chuyển, bảng giá đang áp + giá sắp áp + nơi đi chưa có giá + giá TT (`GET /api/v7/price-table`), cột phụ phí riêng, quy tắc hạn trả chung, group Zalo đã gắn. Mục cần backend hiện trạng thái trống có hướng dẫn hoặc ẩn; **không bịa dữ liệu trên trang thật**.
- **Giai đoạn B (chưa làm, cần backend):** hạng khách, tín dụng, hạn mức (giá trị, người đặt, lịch sử), hợp đồng, người liên hệ, ghi chú khi làm việc, tài liệu, tên pháp lý/mã số thuế, khu vực, loại khách, chữ viết tắt riêng, người phụ trách, hợp tác từ, câu tóm tắt quan hệ, thỏa thuận riêng. Danh sách và nguồn dữ liệu ở spec.
- Quy tắc 1–4 chưa triển khai; khi làm phải đi đúng [quy trình frontend](../development.md#quy-trình-frontend) (spec dữ liệu, API, test). Hạn mức là thông tin ngoài đường tiền: không đổi số dư, phân bổ, khóa tháng.
- Nhãn tín dụng "Cần theo dõi" gần chữ với mức rủi ro "Theo dõi" của Tổng quan (canvas đã ghi); khi làm giai đoạn B cân nhắc đổi chữ, chưa chốt.
