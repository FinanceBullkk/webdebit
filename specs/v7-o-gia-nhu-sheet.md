# Ô Đơn giá ở sổ khách như Sheet: gõ là sửa, dán cả cột giá (GIA-O-01)

Trạng thái: **ĐỀ XUẤT** (Claude, 13/11/2026). Người dùng chọn "Làm tiếp ở đây" cho đề xuất "ô Đơn giá ở sổ khách gõ là sửa và dán cả cột giá" sau [GIA-TUYEN-01](v7-gia-theo-tuyen.md). Hai phần, hai PR: **A** gõ là sửa, **B** dán cả cột giá. Không đổi API, DB, luật giá hay phân bổ.

## Người dùng và luồng (bước 1)

**Ai, khi nào:** người nhập, ở sổ khách (thẻ Sổ), tháng đang mở, khi ghi giá cho nhiều chuyến. Sau khi bỏ Sheet sổ nợ, giá là đầu vào gõ tay hằng ngày ([checklist chuyển hẳn](../docs/chuyen-han-checklist.md), dòng "Giá, phụ phí"). Thói quen trên Sheet: đứng ở ô là gõ, gõ xong Enter xuống ô dưới; giá nhiều chuyến thì dán cả cột.

**Hôm nay:** ô Đơn giá phải bấm Enter (hoặc bấm chuột) để mở ô nhập, gõ, rồi Enter để lưu. Mỗi chuyến cần ba phím, và gõ số ngay khi đang đứng ở ô thì không có gì xảy ra. Không có cách dán nhiều giá một lần.

### A · Gõ là sửa

1. Đứng ở ô Đơn giá (chuột hoặc mũi tên, Tab), gõ một chữ số: ô mở ra với đúng chữ số đó, thay giá cũ (như Sheet).
2. Gõ tiếp, Enter lưu rồi xuống ô Đơn giá hàng dưới (đã có từ SO-GON-04). Esc trả lại giá cũ.
3. Enter ở ô đang đứng vẫn mở ô với giá đang có, để sửa một phần.

Áp cho ô Đơn giá của chuyến web và dòng sổ gốc sửa được. Chỉ chữ số mở ô; chữ cái, dấu, phím có Ctrl/Alt không làm gì. Ô Đơn giá chỉ đọc (chờ kiểm, đã loại, tháng khóa) không mở. Ô chữ (container, ngày, nơi đi…) và ô phụ phí giữ như cũ: các ô này lưu khi rời ô, nên gõ nhầm một phím rồi bấm ra ngoài sẽ thành ghi.

### B · Dán cả cột giá

1. Đứng ở ô Đơn giá của một chuyến web, dán (Ctrl+V) một cột giá chép từ Sheet hay Excel. Mỗi dòng dán vào một chuyến, từ chuyến đang đứng trở xuống trong bảng tháng đó, như Sheet.
2. Chép kèm cột container (hai cột: container và giá, thứ tự cột nào cũng được): máy ghép theo **số container**, không theo thứ tự dòng. Đây là cách an toàn khi nguồn xếp khác sổ.
3. Chưa ghi gì. Hiện khung xem lại: từng chuyến (container, ngày, giá đang có → giá dán), dòng nào không ghi và vì sao, tổng nợ trước → sau. Giá dưới 1.000.000 đ được đánh dấu "nghi sai đơn vị"; ghi đè giá đang có được nêu riêng.
4. Xác nhận (tiêu điểm mặc định ở Thôi): ghi lần lượt bằng lệnh ghi giá đang có, lệnh sau dùng phiên bản lệnh trước trả về, đọc lại sổ một lần ở cuối, báo "Đã ghi n giá.". Lỗi giữa chừng (sổ vừa đổi, tháng vừa khóa…): dừng, đọc lại sổ, báo "Ghi được k/n giá rồi dừng: …". Mất mạng: băng "Thử lại thao tác vừa gửi" như mọi lệnh của sổ; Thử lại gửi đúng lệnh cũ (cùng khóa) rồi ghi tiếp. Sửa sai sau khi ghi: dán lại hoặc sửa từng ô; mỗi lần ghi có dòng Lịch sử trước → sau. Chưa có Hoàn tác ở sổ vì thông báo nổi chưa có chỗ đặt nút.

**Không ghi** (nêu trong khung xem lại): dòng sổ gốc (sửa từng ô, vì Thành tiền dòng sổ gốc có luật riêng), chuyến chờ kiểm, đã loại, dòng phí lẻ, tháng khóa, container không có trong sổ hoặc có nhiều hơn một chuyến, dòng dán thừa (hết chuyến trong bảng tháng). Dòng dán trống là bỏ qua, không phải 0. Dòng dán không đọc được thành số tiền thì chặn cả lần dán, nêu số dòng.

## Đầu ra

A: ghi giá một chuyến bằng gõ số + Enter (hai phím thay vì ba lần thao tác). B: dán một cột giá chép từ Sheet/Excel, xem lại rồi ghi một lần.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- Ô Đơn giá chuyến web: `td.editable[data-field="unit_price_vnd"][data-trip]` (`so-khach-v7-trips-ui.js`), mở ô và lưu ở `so-khach-v7-edit-ui.js` (Enter/Tab lưu, không lưu khi rời ô). Ô Đơn giá dòng sổ gốc: `.info-edit[data-kind="legacy"][data-field="unit_price_vnd"]`, mở bằng `openInfoEdit`.
- Số tiền: `model.parseVnd` nhận số liền (`45000000`) hoặc có dấu nghìn (`45.000.000`, `45,000,000`), như ô hiện nay.
- Tiền chuyến sau khi có giá: `SoKhachV7Model.tripAmount` (đơn giá + phụ phí đang có). Chuyến chưa giá tính nợ cũ bằng 0.
- Ghi: `POST /api/v7/trips/price` `{trip_id, unit_price_vnd, other_fee_vnd}` qua `so-khach-v7-api.js`; lệnh trả `version` mới. Ghi nối tiếp: `api.submitSeries` (mới, `so-khach-v7-api.js`) giữ cơ chế `pending`/Thử lại của sổ; máy chủ giả của test trả `version` sau lệnh ghi như API thật.

## Hành vi và bất biến

- VND nguyên; ô trống không phải 0; giá phải là số tiền đọc được.
- Mỗi chuyến một lệnh, một dòng Lịch sử, phân bổ lại như ghi từng ô.
- Không có lệnh gộp: ghi được một phần là trạng thái thật, báo rõ đã ghi bao nhiêu.

## Tiêu chí nghiệm thu

- [x] A: `npm run check` xanh.
- [x] A, browser (`test-so-khach-v7-go-la-sua-browser.js`): gõ chữ số ở ô Đơn giá chuyến web và dòng sổ gốc mở ô với chữ số đó; Enter lưu và xuống hàng, gõ tiếp là sửa hàng dưới; Esc trả lại; chữ cái/Ctrl không mở; ô chỉ đọc không mở. Test bàn phím, sửa ô, phụ phí cũ vẫn xanh.
- [x] B, đơn vị (`test-so-khach-v7-dan-gia.js`): đọc một cột, hai cột theo container, dòng trống, dấu nghìn, chữ đ; chặn kèm số dòng; kế hoạch ghi và lý do không ghi; nợ trước → sau; container không có, trùng, dán hai lần.
- [x] B, browser (`test-so-khach-v7-dan-gia-browser.js`): khung xem lại đúng giá cũ → mới, lý do không ghi, nợ trước → sau; Thôi/Esc không gửi; Ghi gửi lần lượt, phiên bản nối tiếp; ghép container; chữ sai bị chặn; đang gõ trong ô thì dán như chữ thường; mất mạng thử lại cùng thân lệnh; lỗi giữa chừng dừng và báo k/n. Đã xem ảnh render ở 1280.
- [ ] Bước 8: người dùng thử trên `hao`.

## Phạm vi agent

- Agent: claude
- Review: opus (ghi tiền)
- Được sửa: `cong-no-web-handoff/preview/so-khach-v7-edit-ui.js`, `so-khach-v7-api.js` (B), `so-khach-v7*.css` (B), test mới `test-so-khach-v7-go-la-sua-browser.js` (A), `test-so-khach-v7-dan-gia-browser.js` (B), `specs/v7-o-gia-nhu-sheet.md`
- Ngân sách diff: A 150 dòng, B 600 dòng
