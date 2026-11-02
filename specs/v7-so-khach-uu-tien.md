# Sổ khách: mỗi số một chỗ, xếp theo ưu tiên

Ngày 2/11/2026. Người dùng yêu cầu đổi UX/UI theo bản HTML “Mỗi số một chỗ, xếp theo ưu tiên”. Chỉ trang sổ live; chưa phát hành.

Người nhập thường xuyên cần biết đang xem tháng nào, số nợ hình thành thế nào, khách đã trả gì, rồi soát chuyến. Hướng đã chọn từ mẫu: thanh tháng → phép đối chiếu bốn số bên trái và phiếu thu bên phải → bảng chuyến. So với hướng cũ (tóm tắt ngang, phiếu thu bên dưới), hướng này đặt số và bằng chứng cạnh nhau; màn hẹp xếp dọc. Không cần chọn lại phương án vì người dùng đã cung cấp hướng cụ thể.

Phạm vi: điều hướng bên trái, đầu khách/thẻ, thanh tháng, tóm tắt tháng, vị trí ghi phiếu và tiêu đề bảng chuyến. Giữ danh sách phụ phí động, mọi hành động hiện có, phân bổ, khóa tháng, xác nhận và dữ liệu đang nhập. Không sao chép runtime React của mẫu. Không sửa API, SQL, Sheet, DB hay deploy.

Nguồn số: `months[].prior_months_vnd`, `charges_vnd`, `received_vnd`, `end_of_month_vnd`; phiếu từ `receipts`, `legacy_rows`, `outgoing_offsets`. Tổng toàn sổ khác số cuối tháng: giữ ở đầu trang với nhãn “Tổng còn nợ”. NULL hiện dấu chưa biết, không chuyển thành 0. Tổng phát sinh chỉ hiện trong đối chiếu, cuối bảng chỉ cộng cột phụ phí.

| Thao tác | Entry point | Kiểm |
| --- | --- | --- |
| Đổi tháng, đọc số | month-ui, ui, CSS | month-browser; kiểm số nguyên từ API, NULL, âm |
| Ghi/hủy/sửa phiếu | entry-ui, pay-ui giữ luồng | entry/edit/offset/receipt browser |
| Soát chuyến, khóa, debit | month-ui + các phần hiện có | edit/debit/fee browser |
| Điều hướng, đổi khách, thẻ | HTML, tabs-ui | tabs browser, bàn phím, tên dài |

Nghiệm thu cục bộ: `npm run check`; bản render dữ liệu giả ở 1280×560, 1265px (trừ thanh cuộn Windows), tên dài và màn hẹp; không tràn ngang toàn trang, bảng rộng cuộn trong vùng riêng. Kiểm diff sau cùng. Dừng nếu cần đổi luật tiền hoặc dữ liệu thật. Người dùng đi hết luồng trên bản thử và CI/live là các bằng chứng riêng, chưa được thay bằng fixture.

ĐÃ KIỂM CHỨNG cục bộ 2/11/2026, Windows, nhánh `codex/so-khach-uu-tien` từ `origin/main` `11d2d7e`: `npm run check` đạt cả tám bước (ruff, luật nghiệp vụ, link tài liệu, eslint, unittest Python, unit JS, Chromium, viewer). Ba ca riêng `test-so-khach-v7-priority-browser.js` đạt: thứ tự/vị trí khối và số nguyên từ API; NULL/âm và bàn phím; 1265px với ba cột phụ phí, 700px, 390px. Đã xem ảnh render desktop/mobile dữ liệu giả, sửa phần dính che nội dung trên mobile; `git diff --check` sạch. Dùng venv mới và `npm ci --ignore-scripts`; browser từ cache Playwright sẵn có, không tuyên bố kiểm máy mới. Chưa CI, chưa tích hợp DB thật, chưa người dùng nghiệm thu, chưa deploy.
