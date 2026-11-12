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

ĐÃ CHỐT. Spec: [`specs/v7-so-khach-dien-thoai.md`](../../specs/v7-so-khach-dien-thoai.md).

## Mở rộng 12/11/2026: bảng kê và phiếu thu

Người dùng giao "tối ưu cho điện thoại mọi tính năng và màn". Đo trên `hao` (chỉ đọc) thấy sổ có bảng kê ([`SO-CHI-TIET-01`](so-chi-tiet-01.md)) vỡ hẳn ở 390px (mỗi ô một dòng, chữ dọc) và danh sách phiếu thu đẩy số tiền ra ngoài màn. Claude áp cùng cách của ý 1–5, không dựng phương án mới:

6. Bảng kê dưới 760px luôn là bảng gọn, ba cột Số container · Ngày đóng · Tổng; nhãn tình trạng (Chưa có giá, Bảng kê hơn/kém, Chưa có trên bảng kê) nằm dưới số container; bấm dòng bung phép cộng tại chỗ như màn rộng. "Đủ cột" chỉ có trên máy tính; lựa chọn đã nhớ không bị xóa.
7. Mỗi phiếu thu hai dòng: ngày và số tiền ở trên, hình thức · tham chiếu · phân bổ ở dưới. Bấm ô vẫn như màn rộng.

Trạng thái: ĐỀ XUẤT đã triển khai theo giao việc chung, người dùng chưa xem trên điện thoại thật. Không đổi số, luật tiền hay API.
