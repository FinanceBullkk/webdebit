# DIEN-THOAI-CHUYEN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Trên điện thoại (màn rộng dưới 760px), bảng chuyến của Sổ khách là **bảng ba cột Ngày chuyến · Số container · Thành tiền** (phương án B trên canvas, trang "Chuyến trên điện thoại"):

1. Số tiền thẳng cột như sổ. Chuyến chưa có giá, chuyến Sheet chờ duyệt, chuyến Sheet chưa nối được hiện chữ ở cột Thành tiền, không ghi 0.
2. Bấm một hàng: khung chi tiết trượt lên từ dưới, có Hãng tàu, Shipper, Tuyến, phép cộng Đơn giá + các khoản phụ phí = Thành tiền, câu vì sao chuyến chưa tính vào nợ, nút Chuyến trước / Chuyến sau.
3. Trên điện thoại bảng chuyến **chỉ để xem**: bấm hàng không mở sửa ô, không xóa, không duyệt. Sửa giá, phụ phí, duyệt chuyến làm trên máy tính.
4. Dòng cộng tháng giữ cuối bảng, bằng Phát sinh.
5. Màn rộng từ 760px trở lên không đổi.

## Ngày / nguồn

12/11/2026, chat: người dùng hỏi web có dùng được trên điện thoại không; đo trên `hao` ở 390×844 thấy bảng chuyến rộng 1008px, chỉ hiện STT, container, hãng tàu. Claude dựng hai phương án lên canvas (A mỗi chuyến một thẻ, B bảng ba cột); người dùng chọn B. Ý 3 là giả định Claude nêu trên canvas, người dùng không phản đối.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Spec: [`specs/v7-so-khach-dien-thoai.md`](../../specs/v7-so-khach-dien-thoai.md). Ngoài phạm vi: sổ có bảng chi tiết theo bảng kê ([`SO-CHI-TIET-01`](so-chi-tiet-01.md)) vẫn là bảng cuộn ngang trên điện thoại; khối tổng tháng và phiếu thu không đổi.
