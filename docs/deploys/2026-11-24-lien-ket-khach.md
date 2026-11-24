# Liên kết khách: ghép tên chủ hàng, đọc khối không có cột đơn giá, gộp sổ 240 vào sổ 123 (24/11/2026)

**ĐÃ CHẠY trên `hao` và Sheet ngày 24/11/2026, 14:39–16:16 giờ VN.** Theo [`TU-LAM-01`](../decisions/tu-lam-01.md) (ghi Google Sheet, nạp dữ liệu không hỏi trước) và [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) (release tay). Người dùng chọn "Sửa dữ liệu trước" rồi "Máy đọc mẫu mới" trong chat cùng ngày, sau khi soát 13 dòng "Booking có, web chưa có" của Báo cáo tháng 11 ([`BAO-CAO-THANG-02`](../decisions/bao-cao-thang-02.md)). Quyết định mới: [`KHOI-KHONG-DON-GIA-01`](../decisions/khoi-khong-don-gia-01.md).

| Mục | Kết quả |
| --- | --- |
| Sheet CHAU_HAO, tab `WEB_GHEP_KHACH` | Điền cột F một dòng có sẵn, thêm hai dòng mới (ba tên chủ hàng → sổ 47, 157, 123) |
| PR / release | FinanceBullkk/webdebit#636, merge `be9b1c9d`; release tay `be9b1c9d` (trước đó `8891ab0e`) |
| DB | Đổi tên sổ 123 theo tên tab (một lệnh SQL có ghi Lịch sử); xóa 2 chuyến và 3 dòng sổ gốc chưa giá của sổ 240 bằng hàm app; còn lại do máy ghi theo Sheet |
| Cấu hình | `/srv/v7/customer-name-mapping.json`: mục sổ 123 đổi `v7_name`, thêm `display_name` là tên sổ cũ |
| Bằng chứng | `/srv/v7/backup-20261124-ghep-ten/` trên `hao` (thư mục 700) |

## 1. Hai tên chủ hàng mới (sổ 47, 157)

- Backup giờ `v7-20261124-143934` chạy ngay trước, thành công.
- Lý do chuyến chưa vào sổ: tên chủ hàng trên booking chưa ghép sổ (`NEEDS_CUSTOMER`). Tab khách đã ghi đủ chuyến kèm giá; máy đối soát thấy `sheet_row_missing` nhưng `NOTHING_TO_WRITE` vì sổ chưa có chuyến.
- Chạy thử `build_queue` của bản đang chạy trên bản chụp thật (chỉ đọc): thêm hai tên thì ba dòng về đúng sổ 47 và 157, `COMMODITY_OK`.
- Tài khoản máy trên `hao` chỉ đọc file (Drive `canEdit=false`), nên ghi bằng connector Google Sheets của người dùng. Đọc lại hai vùng ngay trước khi ghi (trống), ghi `F45:G45` và `A116:G116`, đọc lại qua API: tên khớp bản chụp từng ký tự, cột F khớp tên sổ, `parse_review_mapping` không báo trùng.
- Bản chụp 14:45 có hai tên; máy dán ba chuyến lúc 14:48–14:49 và ghi đơn giá, phụ phí theo Sheet. Đọc API: tổng hai sổ bằng đúng tổng Sheet.
- Lượt đối soát 15:05 (xong 15:15): sổ 47 và 157 `KHOP`, số sổ khớp 233 → 236. Tổng web mọi sổ tăng đúng bằng tiền ba chuyến mới; các sổ khác không đổi.

## 2. Đọc khối không có cột đơn giá (KHOI-KHONG-DON-GIA-01)

- Sổ 123: kế toán đổi tên tab của khách và ghi khối tháng 11 theo mẫu hóa đơn dịch vụ, không có cột đơn giá; bộ đọc đánh dấu cả tab `broken`, máy không ghi tiền.
- Bộ đọc thôi bắt buộc cột đơn giá; ngày, cột đã thu, cột số dư vẫn bắt buộc. Test mới đỏ khi bỏ bản sửa, xanh khi có.
- Thử trên `hao`, chỉ đọc: chạy bộ quét cũ và mới trên mọi tab của Sheet sổ nợ. Đúng một tab đổi `broken` → `ok`, các tab khác giữ kết luận; dòng giá giống hệt (cùng mã băm), dòng phiếu thu thêm đúng các phiếu của tab đó.
- FinanceBullkk/webdebit#636: CI 19/19 xanh (3 job có điều kiện bỏ qua), merge squash `be9b1c9d` lúc 15:38; Tests của `main` xanh 15:48. `Deploy hao` dừng ở cổng file bộ đọc đúng thiết kế (lượt 45359297233).
- Release tay `be9b1c9d` lúc 15:49 bằng đúng gói của workflow (`git archive` theo `scripts/deploy/release-paths.txt`) và `webdebit-release.sh deploy` dưới `webdebit-deploy`: unit `active`, `/healthz` loopback 200, file bộ đọc của release có bản mới, journal API không lỗi. Máy bản chụp giá và máy đối soát chạy code của release hiện hành. Script báo không dọn được vài thư mục release cũ (file của user khác), có từ trước, không ảnh hưởng.

## 3. Gộp sổ 240 vào sổ 123

- Bối cảnh: tab cũ của sổ 123 đã đổi tên và nhận thêm một chủ hàng; một tab nháp riêng (không tiền) của chủ hàng đó làm máy tạo sổ 240 ngày đầu tháng. Hai sổ cùng 0 đ trên web trong khi tab thật có số nợ; Báo cáo tháng hiện 5 dòng.
- Backup giờ `v7-20261124-150134` chạy ngay trước, thành công. Chép file ánh xạ cũ và sổ 123, 240 (JSON API) vào thư mục bằng chứng.
- Chạy thử `build_queue` của release `8891ab0e` (vừa lên giữa chừng) với tên mới: mười dòng booking của hai chủ hàng đều về sổ 123, `COMMODITY_OK`.
- Đổi tên sổ 123 theo tên tab: một giao dịch `ON_ERROR_STOP`, chốt tên, version và chưa lưu trữ trước khi ghi, chặn trùng tên, ghi Lịch sử `customer_attr` (người làm `claude`), tăng version. Không có hàm app đổi tên sổ.
- File ánh xạ: chỉ mục sổ 123 đổi (`v7_name` mới, `display_name` là tên cũ để dòng booking mang tên cũ vẫn về sổ này, như lần tách sổ 239 ngày 4/11). Giữ chủ `v7app`, mode 600.
- Ngay sau khi đổi tên, máy tách phí theo tiêu đề ([`TACH-PHI-TIEU-DE-01`](../decisions/tach-phi-tieu-de-01.md)) nối được tab với sổ: mở tháng 3, phân loại phụ phí năm chuyến tháng 3 theo tên cột, khóa lại. Số dư và từng tháng của sổ 123 không đổi (so JSON API trước/sau).
- `WEB_GHEP_KHACH!A117:G117`: tên chủ hàng gộp → sổ 123. Đọc lại khớp; 104 tên ghép.
- Bản chụp 15:15 có tên ghép; trong hai giây sau đó xóa 2 chuyến và 3 dòng sổ gốc của sổ 240 bằng `delete_trip`, `delete_legacy_trip` (người làm `claude`, Lịch sử 12457–12461), không phân bổ lại phiếu nào; sổ 240 còn 0 chuyến.
- Lượt đối soát 15:05 đã nối tab với sổ 123 (không còn là tab ngoài danh sách; phép kiểm TONG ghép được tên trên TONG), sổ bị giữ đúng vì `LAYOUT_HEADER_MISSING_price`.
- Lượt nền của máy dán đủ năm chuyến tháng 11 vào sổ 123 lúc 15:18:56 (một lệnh dán, trạng thái `confirmed`, chưa giá); sổ 240 không còn chuyến nào. Báo cáo tháng hết năm dòng của khách này.

## Kiểm sau cùng

- Lượt đối soát 16:05 (xong 16:16), code mới: sổ 123 `KHOP` (`FIXED`). Máy ghi lúc 16:15: đơn giá năm chuyến bằng TỔNG của từng dòng tab (luật `total_only_rows`), một phiếu thu đúng ngày tiền về trên tab (ô ngày dạng số của Sheet đọc ra đúng ngày), phân bổ lại theo nợ cũ trước. Tháng 11 của sổ: phát sinh, đã thu, còn nợ bằng đúng khối tháng 11 trên tab; tháng 3 không đổi.
- Số sổ khớp 233 (lượt 14:05) → 236 (15:05) → 237 (16:05); "chỉ có web" 5 → 3.
- So tổng web từng sổ giữa lượt 14:05 và 16:05: trong 246 sổ chỉ ba sổ 47, 123, 157 đổi, cả ba về đúng tổng Sheet; tổng mọi sổ tăng đúng bằng phần ba sổ đó.
- Phép kiểm TONG không còn báo sổ 123. Tab ngoài danh sách chỉ còn một (mục CÒN MỞ).
- Báo cáo tháng 11, "Booking có, web chưa có": 13 → 5 dòng, năm dòng còn lại đều đúng lý do (container dùng lại chờ tab ghi, container ở hai tab chờ kế toán, hai chủ hàng chưa có sổ).
- Dọn: thư mục tạm trên `hao` (bản chụp chạy thử bộ quét, kịch bản đọc) đã xóa; worktree code đã gỡ.

## Rollback

- Sheet: xóa ô `F45:G45`, dòng 116 và 117 của `WEB_GHEP_KHACH`.
- Release: `webdebit-release.sh deploy 8891ab0eec84fcb42eb90bb9caf893ae865c1db4` (bản trước).
- Sổ 123: đổi tên về tên cũ bằng cùng kịch bản (`doi_ten_123.sql` trong thư mục bằng chứng, đảo hai tên); file ánh xạ chép lại từ `customer-name-mapping.truoc.json`.
- Chuyến: xóa các chuyến máy đã dán ở sổ 47, 157, 123 (Lịch sử ghi người làm là máy); chuyến và dòng sổ gốc đã xóa ở sổ 240 còn trong Lịch sử. Backup `v7-20261124-143934` và `v7-20261124-150134` là bản trước.

## CÒN MỞ

- Tab nháp của chủ hàng đã gộp (3 dòng, 0 đ) vẫn còn trên Sheet sổ nợ nên sổ 240 (0 chuyến, 0 đ) vẫn khớp với nó. Kế toán hoặc người dùng xóa tab đó thì lưu trữ sổ 240 (`set_customer_archived`, số dư 0). Claude không sửa Sheet sổ nợ vì env dặn không đưa ID của file đó vào chat.
- Ô tên khách trên TONG của sổ 123 khác tên tab một dấu cách. Phép kiểm TONG vẫn ghép được nên không chặn gì; sửa thì cho gọn.
- Sổ 85: một container ghi ở hai tab khách (cùng xe, lệch một ngày), máy không chọn được sổ. Chờ kế toán xác nhận.
- Hai chủ hàng mới chưa có sổ web (Sheet chưa có tab).
- Cùng gốc, ngoài 13 dòng ban đầu: một chuyến đã gán tay vào sổ 148 ngày 4/11, nay kế toán tách sang tab riêng chưa có sổ (TONG lệch nên máy không tự tạo). Sổ 148 đi trước Sheet đúng bằng chuyến đó, máy đã gợi ý `ahead_other_book`. Chờ người dùng chọn cách xử lý.
- `WEB_GHEP_KHACH` là bảng tĩnh lập 24/10: tên chủ hàng mới không tự thêm dòng nên chuyến của tên mới cứ chờ mà không ai được báo. Thuộc đề xuất kiến trúc liên kết khách (ĐỀ XUẤT, chưa có spec).
