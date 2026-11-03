# Hộp ngoại lệ P3b: chuyến từ booking sheet vào đúng sổ theo mặt hàng; máy tự đưa chuyến mới vào sổ

Trạng thái: ĐỀ XUẤT (Claude, 1/11/2026). Giai đoạn P3 của [UX bước 03](../docs/ux-buoc-03-luong-thao-tac.md), phần Q2/Q5 của [`HANG-CHO-01`](../docs/decisions/hang-cho-01.md) kèm điều kiện an toàn cho khách nhiều sổ. Nối tiếp [P3a](v7-hop-ngoai-le-p3a.md). Người dùng bảo "Làm P3b" (chat 1/11/2026).

**Q4 (cột mặt hàng của booking sheet):** Claude tự trả lời từ dữ liệu, 1/11/2026. Tab `CONT_NGUON` có cột "Mặt hàng"; bộ đọc đã đọc cột này nhưng chỉ dùng để suy ra sầu riêng tươi/đông. Đo trên `hao` (dòng BIỂN từ 2026): CHUỐI 2.897, SẦU RIÊNG 1.135, THANH LONG 548, DỪA 272, XOÀI 24, MÍT 18, KHÁC 12, (CHƯA GHI) 4, NHÃN 3, KHOAI LANG 2. Có 9 tên khách trên Sheet có từ hai mặt hàng trở lên.

## Người dùng và luồng (bước 1)

- **Máy** (P3b-0, luôn chạy, không ghi gì): dòng booking chọn sổ theo **tên khách + mặt hàng**. Tên khách của một sổ là `display_name` trong bảng gán tên (ví dụ sổ "KK - DỪA" có tên khách "KK"), không có thì là tên sổ. Khách có nhiều sổ thì dòng dừa vào sổ dừa, dòng thanh long vào sổ thanh long. Hôm nay mọi dòng của khách đó đổ vào sổ trùng tên.
- **Máy** (P3b, công tắc `WEBDEBIT_AUTO_SHEET=trips`, mặc định tắt): sau mỗi lượt hộp ngoại lệ tính xong, với mỗi sổ có chuyến mới, máy bấm thay "Duyệt" cho những chuyến đủ điều kiện Q2:
  - (a) khớp đúng một sổ và **mặt hàng trên Sheet trùng mặt hàng của sổ**;
  - (b) chuyến đang ở trạng thái "chuyến mới", tức container chưa có ở chuyến web mọi sổ, sổ gốc mọi sổ, sổ này (luật ±3 ngày hoặc không ngày cùng tháng);
  - (d) tháng nợ đang mở;
  - (e) ngày không sau hôm nay (giờ VN).

  Máy đi đúng lệnh `paste_trips` mà nút "Duyệt" vẫn gọi, không kèm giá (Q5 = A). Người làm trong Lịch sử là "Máy (theo Sheet)". Lệnh vẫn tự chặn: chuyến trùng bản đối chiếu lúc nạp, sổ gốc hay chuyến web vào "chờ kiểm", không vào số dư.
- **Người nhập**, ở Việc cần làm: dòng "Máy đã tự làm hôm nay" ghi thêm "n chuyến mới vào sổ" (kèm số chuyến vào chờ kiểm). Bấm xem danh sách: sổ, container, ngày, mở sổ. Sai thì mở sổ, xóa chuyến như hiện nay.
- **Người duyệt tay** ở sổ: không đổi. Chuyến mới mà mặt hàng không khớp sổ vẫn hiện và vẫn duyệt tay được; máy không đụng.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Cần | Có sẵn | Thêm |
| --- | --- | --- |
| Mặt hàng từng dòng booking | `webdebit_export_connector.parse_source_values` đọc cột "Mặt hàng" (`cell["commodity"]`) | Ghi `commodity` vào dòng của bản chụp |
| Mặt hàng và tên khách của sổ | `list_customers` trả `commodity`, `transport_mode`; `with_display_names` gắn `display_name` và mặt hàng từ bảng gán tên | `sheet_projection` dùng danh sách đã gắn tên |
| Chọn sổ | `build_queue` khớp tên Sheet → đúng một tên sổ | Nhóm sổ theo tên khách, chọn theo mặt hàng; đánh dấu `book_match` |
| Lệnh ghi | `approve_sheet` → `paste_trips` theo tháng, 200 dòng một lệnh | Tách phần dựng lô để máy dùng chung, lọc theo điều kiện Q2 |
| Tháng mở | `_locked_months` (P2) đọc `month_locks`, `today_month` | Không |

## Luật chọn sổ (P3b-0)

Với tên Sheet `N` (sau bảng ghép tên `customer_aliases`):

1. Nhóm sổ = sổ có tên sổ là `N`, cộng sổ có tên khách (`display_name`) là `N`.
2. Nhóm có một sổ: giữ như hôm nay (sổ đó).
3. Nhóm có nhiều sổ: lấy sổ có mặt hàng trùng cột "Mặt hàng", chỉ trong các sổ không phải đường bộ (dòng booking chỉ là BIỂN). Đúng một sổ thì dòng vào sổ đó.
   - Không chọn được một sổ (Sheet để trống, KHÁC, (CHƯA GHI), không sổ nào trùng hay nhiều sổ trùng): giữ sổ trùng tên như hôm nay.
4. `book_match` của dòng:
   - `COMMODITY_OK`: mặt hàng Sheet trùng mặt hàng sổ;
   - `COMMODITY_UNKNOWN`: Sheet hoặc sổ không có mặt hàng;
   - `COMMODITY_MISMATCH`: hai bên khác nhau;
   - `ROAD_BOOK`: dòng rơi vào sổ đường bộ (nhóm chỉ có sổ đó).

   Chỉ `COMMODITY_OK` cho máy tự vào sổ.

## Hành vi và bất biến

- Không đổi tiền: chuyến vào sổ chưa có giá, không cộng nợ (NULL không phải 0). Số dư 236 khách phải bằng trước khi máy chạy.
- Mỗi lô một khóa chống ghi trùng cố định theo (bản chụp, sổ, tháng, dòng Sheet đầu lô). Phiên bản sổ nối tiếp qua từng lô. Lỗi ở một sổ thì dừng sổ đó (đếm vào `auto.errors`); lượt sau thử lại.
- Máy chỉ chạy khi bản chụp Sheet đọc được (`key` khác `None`) và đã yên `SETTLE_SECONDS`.
- Nhịp nền của API (`Inbox.keep_fresh`, mỗi 60 giây) tự tính lại hộp khi bản chụp đổi, nên máy chạy theo từng đợt Sheet kể cả khi không ai mở Việc cần làm. Trước bản sửa 1/11/2026, hộp chỉ tính lại lúc API khởi động hoặc khi có người mở trang.
- Danh sách "máy đã làm" giữ trong RAM của API như P3a; Lịch sử từng sổ là nguồn đủ.

## Tiêu chí nghiệm thu

- [x] Unit `build_queue`: khách nhiều sổ chọn đúng sổ theo mặt hàng; khách một sổ giữ nguyên; Sheet trống/KHÁC/không sổ nào trùng giữ sổ trùng tên với `book_match` đúng; không chọn sổ đường bộ cho dòng BIỂN (`ROAD_BOOK` khi đó là sổ duy nhất).
- [x] Unit máy: tắt mặc định; khi bật chỉ dán chuyến `NEW` + `COMMODITY_OK` + tháng mở + không ngày tương lai; đúng người làm, phiên bản nối tiếp, khóa cố định; lỗi dừng sổ.
- [x] Trình duyệt: dòng "Máy đã tự làm hôm nay" có chuyến mới.
- [ ] Trên `hao`, đo trước/sau P3b-0 (chỉ đọc): số "chuyến mới", số `OTHER_BOOK_LEGACY`, số chuyến web bị báo "Sheet không còn dòng".
  - Đo 3/11/2026: còn 28 `OTHER_BOOK_LEGACY`; bổ sung hai luật chọn/ẩn và sửa bảng gán tên, còn 4 ([nhật ký](../docs/deploys/2026-11-03-trung-so-anh-em.md)).
- [ ] Trên `hao`, sau khi bật máy: số chuyến máy đưa vào khớp số đủ điều kiện; số dư 236 khách không đổi.
