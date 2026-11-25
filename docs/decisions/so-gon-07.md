# SO-GON-07

[← Sổ quyết định](../decisions.md)

## Quyết định

Bảng chuyến của Sổ khách (bản live), phương án A người dùng chọn:

1. **Ẩn cột phí riêng trống cả tháng đang xem.** Cột phụ phí riêng của sổ ([COT-PHU-PHI-01](cot-phu-phi-01.md)) không có khoản nào trong tháng đang xem thì không hiện; cấu hình cột của sổ giữ nguyên. Nút **"Hiện n cột phí trống"** ở thanh bảng chuyến mở lại mọi cột để gõ phí vào lưới như Sheet; trình duyệt nhớ lựa chọn (bấm "Ẩn cột phí trống" để về mặc định). Phí loại đó cũng vẫn nhập được qua ô Khác.
2. **Mỗi chuyến một dòng.** Ghi chú giá không xuống dòng dưới số nữa: giá ghi theo bảng là bình thường, không in chữ (rê chuột thấy); giá khác bảng có nhãn "≠ bảng" cùng dòng (ô vẫn tô vàng); chuyến chưa có giá mà bảng giá có thì ghi "chờ điền giá"; không tra được thì chữ "chưa có giá" thay bằng lý do ngắn ("ngoài bảng giá", "thiếu nơi đi"…). Số của bảng và câu đầy đủ ở chữ rê chuột.
3. **Thành tiền ghim phải.** Bảng vẫn rộng hơn khung (nhiều cột phí có khoản) thì chỉ phần giữa cuộn ngang, cột Thành tiền luôn thấy.

## Ngày / nguồn

23/11/2026, chat. Audit giao diện 23/11 đo trên `hao` ở 1366×599: bảng 1.412px trong khung 1.241px, Thành tiền ngoài màn, mỗi chuyến cao hai dòng vì chữ "theo bảng", một màn ~9 chuyến. Claude đưa hai phương án (A: ghim Thành tiền, ẩn cột phí trống, ghi chú cùng dòng; B: gộp phụ phí một cột); người dùng chọn **A**. Nút "Hiện cột phí trống" Claude thêm khi thấy ẩn cột làm mất chỗ gõ phí.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Sửa phần bố cục Claude chọn trong `COT-PHU-PHI-01` (cột riêng trống hẹp 60px): nay mặc định ẩn theo tháng, hẹp khi đã bấm Hiện. Chỉ đổi cách hiện: không đổi dòng phụ phí, tiền, số dư, phân bổ hay quyền ghi. Bảng chi tiết "Gọn | Đủ cột" ([SO-CHI-TIET-01](so-chi-tiet-01.md)) không đổi.

## Sửa đổi 25/11/2026: tháng mở hiện đủ cột phí (SK-G7)

Thay (1). Người dùng chọn phương án A (chat, 25/11/2026), vì từ 1/12/2026 gõ phí tại ô trên web là đường nhập duy nhất (người nhập thôi gõ Sheet sổ nợ) và audit Sổ khách 25/11/2026 (SK-G7) thấy hai máy mở cùng sổ hiện 8 cột và 1 cột phí do lựa chọn nhớ theo trình duyệt.

1. **Tháng đang mở** (sổ đang dùng, tháng không khóa) hiện đủ cột phụ phí riêng của sổ, kể cả cột trống, để gõ thẳng vào lưới như Sheet. Bảng rộng hơn khung thì cuộn ngang; tên cột và Thành tiền vẫn dính (SK-N1).
2. **Tháng khóa** ẩn cột riêng trống cả tháng như (1) cũ, cho gọn để đọc.
3. Nút ở thanh bảng chuyến ("Ẩn n cột phí trống" / "Hiện n cột phí trống") chỉ đổi tạm cho tháng đang xem; đổi tháng hay tải lại thì về mặc định. **Không nhớ theo trình duyệt** nữa: mọi máy thấy cùng một bảng.

ĐÃ CHỐT. Chỉ đổi cách hiện; (2), (3) và dòng phụ phí, tiền, số dư, phân bổ, quyền ghi không đổi.
