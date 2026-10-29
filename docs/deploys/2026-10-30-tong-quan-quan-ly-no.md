# Triển khai tay: Tổng quan quản lý công nợ (30/10/2026)

**ĐÃ CHẠY trên `hao` ngày 30/10/2026 (bản thử 06:08, cửa sổ dừng ghi 06:17:01–06:17:08 giờ VN)**. Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md); người dùng bảo "Tiếp tục triển khai" trong chat. Lượt `Deploy hao` của `5f04bc4` đỏ ở cổng SQL là chủ ý.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#186 (`5f04bc4`) |
| Quyết định | [`DASH-03`](../decisions/dash-03.md); spec [`v7-tong-quan-quan-ly-no`](../../specs/v7-tong-quan-quan-ly-no.md) |
| Migration | `2026-10-29-v7-tong-quan-quan-ly-no.sql`: thêm hàm đọc `get_dashboard_debt()` (cấp cho `sokhach_app`, `sokhach_reader`) và hàm phụ `_legacy_date(text)` (thu hồi quyền). Không đổi bảng, view hay hàm cũ |
| Release app | `bdf581d` → `5f04bc4` (Tests `main` xanh đúng SHA) |
| Ghi tiền | Không. Hai hàm chỉ đọc; không đổi dữ liệu |

## Bản sao thử

- Tối 29/10 đã chạy một lượt. Sáng 30/10 chạy lại trên dữ liệu mới nhất, sau đợt sửa shipper sổ gốc lúc 06:04–06:05 của một phiên khác (không thuộc đợt này).
- Dump `webdebit_v7` đang chạy rồi kiểm đọc lại được (`pg_restore --list`). Restore vào DB thử, thu hồi CONNECT của PUBLIC. Chạy migration hai lượt.
- Dấu vân tay số dư (`md5` của `v_outstanding_month`), số dư 236 khách và số dòng khách/sự kiện/phiếu/chuyến/điều chỉnh/dòng sổ gốc/số dư đầu đều giữ nguyên. `v7_post_deploy_check.sql` 9/9 OK.
- Hàm mới chạy 109 ms. Tổng còn phải thu bằng `get_dashboard`; năm nhóm hạn trả cộng lại bằng tổng; cộng từng khách bằng tổng; số khách bằng `get_dashboard`; đã thu/phát sinh tháng này bằng tổng dòng tháng của `get_ledger` qua mọi sổ.
- Đã xóa DB thử.

## Cửa sổ dừng ghi

- Trước khi dừng: Tests `main` xanh đúng `5f04bc4`; lượt `Deploy hao` đỏ ở bước kiểm diff (có migration); 10 phút trước đó không có sự kiện ghi nào. Ba timer 15 phút trên `hao` (bản chụp Sheet, PS, giá) chỉ ghi file JSON, không ghi DB, nên dừng API là dừng mọi đường ghi.
- Dừng `v7-ledger-api.service`. Đo lại dấu vân tay, số dư và số dòng. Dump lần hai, ghi hash, kiểm đọc lại được (`pg_restore --list`) trước khi áp.
- Áp migration (một transaction, `psql -X -v ON_ERROR_STOP=1`). Dấu vân tay, số dư 236/236 khách và số dòng không đổi.
- Đổi release bằng `webdebit-release.sh deploy 5f04bc4` dưới user deploy; script restart API và kiểm sống đạt. API dừng khoảng 7 giây. Dòng `find: Failed to restore initial working directory: /home/aohanh` là do lệnh SSH chạy từ thư mục home mà user deploy không vào được; script vẫn thoát 0. Lần sau chạy tay thì `cd /` trước.

## Sau

- `.release-sha` = `5f04bc4`; API active, log sau restart không có lỗi.
- Trên DB thật: `v7_post_deploy_check.sql` 9/9 OK; dấu vân tay, số dư và số dòng sau khi đổi release vẫn như trước; hàm mới chạy 135 ms, đạt đủ các phép so tổng như ở bản sao thử.
- Mở trang thật qua Tailscale ở khung 1280×720:
  - Tổng quan đủ bốn khối, danh sách 10 khách, năm nhóm hạn trả; các nút lọc bật (số từng khách khớp tổng); không lỗi, không cuộn ngang;
  - lọc theo nhóm hạn trả, lọc khách rủi ro cao, bỏ lọc, mở ngăn kéo khách và đóng bằng Esc đều chạy, địa chỉ trang đổi theo;
  - tab Việc cần làm đủ ba khối; dòng thiếu giá mở sổ kèm `?loc=thieu-gia`; số đếm trên thanh điều hướng khớp giữa hai trang;
  - Sổ khách và Công nợ theo tháng có mục Việc cần làm, thanh trên không tràn.
- **Bằng chứng:** thư mục backup `v7-tong-quan-20261030-060852` trên `hao`, ngoài Git. Gồm:
  - dump trước và dump lúc dừng, kèm hash và mục lục `pg_restore --list`;
  - hash migration, checker và script chạy;
  - dấu vân tay, số dư, số dòng ở từng mốc;
  - log áp migration, kết quả checker và kiểm hàm mới ở bản thử và DB thật.

  Lượt thử tối 29/10 nằm ở `v7-tong-quan-20261029-225653`.

## Rollback

- App: trỏ `CURRENT_LINK` về release `bdf581d` rồi restart. Release cũ không gọi `/api/v7/dashboard/debt`.
- DB: hai hàm chỉ đọc, để nguyên được. Muốn bỏ hẳn: `DROP FUNCTION sokhach.get_dashboard_debt(); DROP FUNCTION sokhach._legacy_date(text);` (khi đó checker của `main` sẽ báo thiếu hàm), hoặc restore `stopped.dump` vào DB mới.

## CÒN MỞ

- Người dùng chưa tự đi hết luồng trên web thật: Tổng quan (lọc theo nhóm, ngăn kéo khách, xếp cột) và tab Việc cần làm.
- Theo quy tắc mặc định đã chốt, dữ liệu thật hôm nay có 67 khách đang nợ, 49 khách có nợ quá hạn, 43 khách rủi ro cao. 1.218/1.227 dòng thu sổ gốc không có ngày, nên với phần lớn khách "lần trả gần nhất" là cuối tháng của dòng thu (ngăn kéo ghi "trong tháng …"). Web mới có 5 phiếu thu; nếu khoản thu sau mốc chưa dán lên web thì khách trông lâu chưa trả hơn thực tế. Ngưỡng 3 tháng / 60 ngày / 90 ngày chỉnh được nếu người dùng thấy quá nhiều khách rủi ro cao.
