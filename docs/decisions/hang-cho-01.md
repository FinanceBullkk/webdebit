# HANG-CHO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ba câu Q1–Q3 của [UX bước 02](../ux-luong-du-lieu.md) mục 7, theo đúng phương án Claude đề xuất: chia việc của hàng chờ Sheet → web theo "ai phải quyết". Máy tự làm phần đã có luật; người chỉ quyết ngoại lệ, ở **một hộp chung của cả công ty** thay vì mở từng sổ.

1. **Q1 · Lệch chữ mô tả.** Trong lúc chạy song song ([`SONG-SONG-01`](song-song-01.md)), khi Sheet đổi nơi đi, nơi đến hoặc shipper của một chuyến đã có trên web **mà số tiền chuyến đó không đổi**, web tự lấy theo Sheet. Mỗi lần ghi Lịch sử, người làm là máy. Không hỏi người.
   - Đổi ngày, container, booking, hoặc đổi tuyến làm đổi giá vẫn để người quyết.
2. **Q2 · Chuyến mới tự vào sổ** khi đủ các điều kiện:
   - (a) khớp đúng một sổ đang hoạt động;
   - (b) container chưa có ở đâu: chuyến web mọi sổ, sổ gốc mọi sổ theo luật ±3 ngày hoặc không ngày cùng tháng, bản đối chiếu lúc nạp;
   - (c) giá tính được từ bảng giá của sổ;
   - (d) tháng nợ đang mở;
   - (e) ngày không sau hôm nay.

   Chuyến tự vào được liệt kê ở mục "Máy đã tự làm hôm nay" để người nhập soát; sai thì xóa chuyến như hiện nay. Dòng thiếu một điều kiện vào hộp ngoại lệ. Thay vế "người nhập duyệt trên sổ" của [`NHAP-SHEET-02`](nhap-sheet-02.md) cho các dòng đủ điều kiện; [`NEWTRIP-01`](newtrip-01.md) giữ nguyên.
3. **Q3 · Phiếu thu từ Sheet** vẫn do người bấm xác nhận (tiền vào, chỉ số M4 của [`UX-NEN-01`](ux-nen-01.md)), nhưng ở hộp chung. Có thể chọn nhiều phiếu của nhiều sổ rồi ghi một lần; mỗi phiếu vẫn đi lệnh ghi phiếu thu có sẵn của sổ đó. Thay chỗ bấm của [`THU-SHEET-01`](thu-sheet-01.md), không đổi luật ghép phiếu.

**Điều kiện an toàn Claude thêm cho Q2 khi viết bước 03:** khách có nhiều sổ theo mặt hàng ([`V7-MH`](v7-mh.md)) chỉ được tự vào sổ khi dòng booking đã gán đúng sổ theo mặt hàng (Q4 của bước 02). Trước đó, dòng của khách nhiều sổ đi vào hộp ngoại lệ. Lý do: hàng chờ hôm nay gán theo tên khách, nên chuyến dừa thật sự mới của một khách có sổ dừa riêng sẽ rơi vào sổ chính. Lớp chặn trùng không bắt được trường hợp này, vì container chưa có ở đâu.

## Ngày / nguồn

1/11/2026, chat. Claude đưa Q1–Q3 kèm phương án "(đề xuất: có)" trong [UX bước 02](../ux-luong-du-lieu.md); người dùng chọn "Chốt Q1–Q3".

## Hiệu lực và giới hạn

ĐÃ CHỐT, chưa triển khai. Thiết kế luồng ở [UX bước 03](../ux-buoc-03-luong-thao-tac.md). Không đổi luật tiền, phân bổ, khóa tháng hay quyền ghi. Mọi việc máy làm đi qua đúng các lệnh ghi đang có và ghi Lịch sử như người làm.

Hết hiệu lực vế Q1 khi chuyển hẳn khỏi Sheet, vì lúc đó web là sổ chính, không còn "theo Sheet".

Đo 1/11/2026: chỉ 1/236 sổ có bảng giá, nên với điều kiện (c) Q2 hôm nay hầu như không tự đưa chuyến nào vào sổ. Xem câu Q5 ở bước 03.
