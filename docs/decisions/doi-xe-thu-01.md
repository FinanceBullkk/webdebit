# DOI-XE-THU-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Đợt 2 của module Đội xe ([`CHI-PHI-XE-01`](chi-phi-xe-01.md)): thu cước, bảng kê và công nợ cước. Người dùng chốt ngày 18/11/2026:

1. Đội xe là **công ty con**; mỗi tháng xuất bảng kê cước cho **công ty mẹ HTH**. HTH trả theo tháng, đủ bảng kê.
2. **Phí nâng và phí hạ cảng do đội xe chịu** trong cước. Các khoản này là chi phí của chặng, không phải chi hộ, không lên bảng kê.
3. **Trang Bảng kê tổ chức theo tháng.** Ba số trên cùng là Đòi HTH, HTH đã trả, Còn phải thu. Nút chính đổi theo bước: Gửi bảng kê → Đối chiếu xong → Ghi tiền HTH trả. Người dùng chọn bố cục này, rồi "Chốt mockup" sau khi bấm thử bản trên canvas.
4. Theo bản bấm thử đã chốt:
   - Chặng chưa có giá vẫn gửi được bảng kê: ô cước để trống, chưa tính vào số đòi; trước khi gửi có cảnh báo.
   - Đã gửi thì không sửa thẳng số tiền. Mỗi điều chỉnh gắn với một dòng, bắt buộc lý do, cho thấy Đòi HTH trước → sau. Sau "Đối chiếu xong" thì thôi nhận điều chỉnh.
   - Tiền về gắn vào bảng kê của tháng đó. Trả thiếu vẫn ghi được; trả thừa bị chặn. Hủy một lần tiền về bắt buộc lý do.
   - Bảng giá tuyến có ngày áp dụng. Đổi giá không làm đổi tháng đã gửi; chặng của tháng đang gom từ ngày áp dụng thì đổi theo.
   - Rút mooc, thả mooc tính 70% giá tuyến, làm tròn tới nghìn đồng.
5. Danh mục phát sinh theo bản bấm thử là cách làm mặc định:
   - Chi hộ: kiểm hoá, hạ sớm, cân, xí cont, cont mới.
   - Neo tính theo ngày (mức ngày đầu, mỗi ngày thêm một mức); nổ máy phát tính theo đơn vị.
   - Cân và đóng ghép nhập tay.

   Danh sách chi hộ và cách tính nổ máy đang được hỏi lại ở phiên làm đợt 1; câu trả lời ở đó thay mặc định này. Mức tiền xác nhận lại khi nạp dữ liệu thật.

## Ngày / nguồn

18/11/2026: người dùng trả lời trong chat; chọn bố cục "Theo tháng"; bấm "Chốt mockup" sau khi thử 5 khung trên canvas thiết kế của dự án (trang "Đội xe: bảng kê HTH (đợt 2)"). Spec: [`specs/doi-xe-thu-01.md`](../../specs/doi-xe-thu-01.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT phạm vi và luồng của đợt 2; chưa code, chưa triển khai. Còn mở: bảng kê riêng cho xe Trần Hùng (tùy cước có đi qua đội xe không), ai ghi tiền về, đối chiếu với HTH đang làm ở đâu. Không cấp quyền nạp dữ liệu thật hay ghi Google Sheet.
