# Sổ khách: mỗi số một chỗ, xếp theo ưu tiên

Ngày 2/11/2026. Người dùng yêu cầu đổi UX/UI theo bản HTML “Mỗi số một chỗ, xếp theo ưu tiên”. Chỉ trang sổ live; chưa phát hành.

Người nhập thường xuyên cần biết đang xem tháng nào, số nợ hình thành thế nào, khách đã trả gì, rồi soát chuyến. Hướng đã chọn từ mẫu: thanh tháng → phép đối chiếu bốn số bên trái và phiếu thu bên phải → bảng chuyến. So với hướng cũ (tóm tắt ngang, phiếu thu bên dưới), hướng này đặt số và bằng chứng cạnh nhau; màn hẹp xếp dọc. Không cần chọn lại phương án vì người dùng đã cung cấp hướng cụ thể.

Phạm vi: điều hướng bên trái, đầu khách/thẻ, thanh tháng, tóm tắt tháng, vị trí ghi phiếu và tiêu đề bảng chuyến. Giữ danh sách phụ phí động, mọi hành động hiện có, phân bổ, khóa tháng, xác nhận và dữ liệu đang nhập. Không sao chép runtime React của mẫu. Không sửa API, SQL, Sheet, DB hay deploy.

Nguồn số: `months[].prior_months_vnd`, `charges_vnd`, `received_vnd`, `end_of_month_vnd`; phiếu từ `receipts`, `legacy_rows`, `outgoing_offsets`. Tổng toàn sổ khác số cuối tháng: giữ trong menu ⋯ với nhãn “Tổng còn nợ (mọi tháng)”. NULL hiện dấu chưa biết, không chuyển thành 0. Footer cộng cột phụ phí và Thành tiền theo handoff.

| Thao tác | Entry point | Kiểm |
| --- | --- | --- |
| Đổi tháng, đọc số | month-ui, ui, CSS | month-browser; kiểm số nguyên từ API, NULL, âm |
| Ghi/hủy/sửa phiếu | entry-ui, pay-ui giữ luồng | entry/edit/offset/receipt browser |
| Soát chuyến, khóa, debit | month-ui + các phần hiện có | edit/debit/fee browser |
| Điều hướng, đổi khách, thẻ | HTML, tabs-ui | tabs browser, bàn phím, tên dài |

Nghiệm thu cục bộ: `npm run check`; bản render dữ liệu giả ở 1280×560, 1265px (trừ thanh cuộn Windows), tên dài và màn hẹp; không tràn ngang toàn trang, bảng rộng cuộn trong vùng riêng. Kiểm diff sau cùng. Dừng nếu cần đổi luật tiền hoặc dữ liệu thật. Người dùng đi hết luồng trên bản thử và CI/live là các bằng chứng riêng, chưa được thay bằng fixture.

Bằng chứng bản đầu `ca5ca7e` (đã bị người dùng bác về thị giác): ĐÃ KIỂM CHỨNG cục bộ 2/11/2026, Windows, nhánh `codex/so-khach-uu-tien` từ `origin/main` `11d2d7e`: `npm run check` đạt cả tám bước (ruff, luật nghiệp vụ, link tài liệu, eslint, unittest Python, unit JS, Chromium, viewer). Ba ca riêng `test-so-khach-v7-priority-browser.js` đạt: thứ tự/vị trí khối và số nguyên từ API; NULL/âm và bàn phím; 1265px với ba cột phụ phí, 700px, 390px. Đã xem ảnh render desktop/mobile dữ liệu giả, sửa phần dính che nội dung trên mobile; `git diff --check` sạch. Dùng venv mới và `npm ci --ignore-scripts`; browser từ cache Playwright sẵn có, không tuyên bố kiểm máy mới. Chưa CI, chưa tích hợp DB thật, chưa người dùng nghiệm thu, chưa deploy.


## Sửa theo handoff, 2/11/2026

Người dùng bác bản đầu vì chỉ giống thứ tự khối, chưa giống thiết kế. Tiêu chí mới: dùng đúng HTML handoff làm chuẩn (menu 76px có nhãn, header khách và bốn thẻ + menu ⋯, chip tháng active ghi đủ tháng/năm, khối số/phiếu thu riêng, khối chuyến riêng, tuyến chung một cột vẫn sửa được hai đầu, phiếu thu năm cột). Giá trị, tên, số dòng thay theo API; không tự thêm phí Nâng hạ nếu sổ chưa chọn cột đó. Footer phục hồi Thành tiền như handoff (tổng cột). Thao tác phụ ở menu ⋯; trạng thái Sheet trong tooltip nút làm mới, lỗi vẫn hiện chữ. Băng dữ liệu thử vẫn phải hiện. Kiểm với cùng dữ liệu mẫu và cùng viewport 1280×760, 1895×848; kiểm các tọa độ/mật độ và xem hai ảnh cạnh nhau. Chưa có bằng chứng mới thì không nhận “giống handoff”.


ĐÃ KIỂM CHỨNG bản sửa handoff cục bộ 2/11/2026, Windows: `npm run check` đạt đủ tám bước; log ngoài repo `D:/webdebit/worktrees/_logs/handoff-check-final.log`. Sau chỉnh cách xếp trên màn hẹp, chạy lại năm ca `test-so-khach-v7-priority-browser.js` đều đạt (`handoff-priority-final.log`). Hai ca mới kiểm kích thước/vị trí tại 1280 và 1895px, năm ô phiếu, một cột tuyến, ba nút công cụ, không ghi khi xem; sửa hai đầu tuyến riêng và Enter/mũi tên giữ đúng trường ở hàng kế. Các bộ sửa/xóa, phụ phí, ảnh, phiếu, khóa tháng, Sheet, bàn phím và các thẻ đều đạt trên máy chủ giả. Đã xem ảnh HTML gốc và bản sửa cùng khổ 1895×848, bản sửa 1280×760 và 390px. Ảnh ngoài repo: `handoff-original.png`, `handoff-match3.png`, `handoff-1280.png`, `handoff-390-fixed.png` trong thư mục log trên.

Giới hạn đối chiếu: không tuyên bố trùng từng pixel. Bản thử có băng DỮ LIỆU GIẢ; nhãn phân bổ giữ năm để không lẫn kỳ; badge việc sidebar và dữ liệu theo trạng thái thật, không gán cứng số 3 của mẫu. Cột phụ phí phụ thuộc cấu hình sổ. Khi có việc chờ/lỗi, hiện thêm thông báo và hành động cần thiết. Chưa CI, chưa DB thật, chưa người dùng nghiệm thu, chưa deploy.
