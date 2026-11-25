# Gán tên booking cho chủ hàng chuyến bộ máy đã học từ tab (25/11/2026)

**ĐÃ CHẠY trên `hao` ngày 25/11/2026, 13:20–13:30 giờ VN.** Theo [`TU-LAM-01`](../decisions/tu-lam-01.md) (ghi DB không hỏi trước: backup trước, đối soát tổng khách sau). Việc chuẩn bị tắt máy theo Sheet sổ nợ ngày 1/12 của [`WEB-CHINH-01`](../decisions/web-chinh-01.md), mục 5: hàng chờ chuyến bộ xếp chuyến vào sổ theo dòng tab Sheet, và khi không có dòng tab thì theo cặp CHỦ HÀNG → sổ học từ các chuyến tab đã xếp. Thôi đọc tab thì cả hai mất dần, nên ghi các cặp đó thành tên booking gán trên web ([`KHACH-WEB-01`](../decisions/khach-web-01.md)), là đường đã có sẵn.

| Mục | Kết quả |
| --- | --- |
| Code | Không đổi. Release đang chạy `f7424925` |
| DB | 24 lệnh `set_booking_name` (người làm `claude`), qua đúng hàm của nút Quản trị (`v7_api_khach.handle_booking_name`, có kiểm tên không đang đưa chuyến vào sổ khác) |
| Backup | `v7-20261125-132212` (backup giờ chạy tay ngay trước, thành công) |
| Bằng chứng | `/srv/v7/backup-20261125-ten-chu-hang/` trên `hao` (thư mục 700): kịch bản, danh sách cặp, nhật ký chạy thử và ghi, tổng nợ từng sổ trước/sau, phép so hàng chờ chuyến bộ |

## Chọn cặp (chỉ đọc)

Lặp đúng luật học của `build_road_queue` trên bản chụp `road.json` và `prices.json` lúc chạy: chuyến bộ có đúng một dòng tab gần ngày, dòng tab đó chỉ một chuyến nhận, tab thuộc một sổ.

| | Số |
| --- | ---: |
| Chủ hàng máy đã học | 38 |
| Đủ điều kiện (một sổ, ít nhất `OWNER_MIN_TRIPS` = 3 chuyến) | 25 |
| Trong đó đã có tên gán trên web | 0 |
| Chủ hàng học ra nhiều sổ (kho), không gán | 1 |
| Chưa đủ 3 chuyến, không gán | 12 |

Cả 25 cặp đều về sổ chuyến bộ (`BO`), tổng 15 sổ, không sổ nào lưu trữ.

## Ghi

Chạy thử (không ghi): 24 gán được, 1 bị chặn `ROUTED` vì bảng ghép tên `WEB_GHEP_KHACH` trên Sheet đang ghép tên đó vào một sổ khác (sổ 84 với sổ cùng chủ, đúng ca đã biết là hai tên của một khách). Để nguyên cho người, không ép.

Ghi thật: 24 tên, 0 lỗi, cùng 1 ca chặn như chạy thử. Tổng nợ cả 250 sổ đọc trước và sau giống hệt từng sổ (gán tên không đổi tiền).

Hôm nay không đổi chuyến nào: tên gán trùng đúng sổ máy đang học, và hàng chờ chỉ dùng tên khi lịch sử tab không chỉ sang sổ khác. Đo trên `hao` sau khi gán, hàng chờ chuyến bộ từ 10/2026 có và không có bản chụp giá: có tab 250 chuyến vào sổ; không tab 251 chuyến, 250 trùng đúng sổ cũ, 0 chuyến đổi sổ, 0 chuyến mất. Chuyến thêm là chuyến đang bị giữ vì tab có dòng cùng container lệch ngày (`TAB_FAR`); không tab thì nó vào sổ theo tên.

## Lùi lại

Bỏ từng tên ở thẻ Khách trong Quản trị (hoặc `set_booking_name` với `remove: true`). Danh sách tên và sổ trong thư mục bằng chứng.

## CÒN MỞ

- 12 chủ hàng chưa đủ 3 chuyến và chủ hàng mới sau 1/12: chuyến của họ chờ người chọn sổ (nút chọn sổ cho chuyến bộ, thuộc phiên kiểm đường nhập web).
- Ca bị chặn `ROUTED`: người xem bảng ghép tên.
