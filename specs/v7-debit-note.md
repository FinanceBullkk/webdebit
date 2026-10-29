# Debit note theo tháng công nợ

Trạng thái: ĐÃ CHỐT (người dùng, 29/10/2026, [`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md)); các điểm Claude chọn ghi trong file quyết định.

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Người nhập (trên 40 tuổi, màn 1280×720) cuối tháng gửi khách bảng kê chuyến theo mẫu "COMMERCIAL INVOICE" đang làm tay trên Excel.

1. Mở sổ khách, kéo tới tháng cần gửi, bấm **Debit note** ở dòng tiêu đề tháng.
2. Hộp xem trước hiện đúng bảng sẽ gửi: tên khách, ngày xuất, từng chuyến của tháng công nợ đó, dòng TỔNG và nhãn CHƯA CHỐT/ĐÃ CHỐT. Trên bảng có câu báo khi còn chuyến thiếu giá, chuyến CHỜ KIỂM chưa lên phiếu, hoặc tháng có dòng điều chỉnh không lên phiếu.
3. Bấm **Tải Excel** (file `.xlsx` giữ bố cục mẫu) hoặc **In / Lưu PDF** (hộp in của trình duyệt, khổ A4 ngang; chọn "Lưu dưới dạng PDF").
4. **Đóng** (hoặc Esc) về lại sổ, con trỏ trở về nút vừa bấm.

Không có gì bị chặn: tháng không có chuyến thì không hiện nút. Phiếu chỉ đọc dữ liệu sổ đang hiện, không ghi DB.

## Đầu ra

Nút Debit note ở mỗi tháng có chuyến; hộp xem trước; file Excel và bản in cùng nội dung, cột như mẫu.

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

Mọi trường đã có trong `GET /api/v7/ledger` mà trang sổ đang dùng; không cần API mới.

| Cột phiếu | Chuyến web (`trips[]`) | Dòng sổ gốc (`legacy_rows[]`, `kind='trip'`) |
| --- | --- | --- |
| Container No. | `container` (phí lẻ: chữ "Phí lẻ") | `current.container`, không có `current` thì `display.container` |
| Line | `carrier` | `current.carrier` / `display.carrier` |
| Shipper | `shipper` | `current.shipper` / `display.shipper` |
| Ngày | `event_date` | `current.event_date` / `display.date` |
| Kho | `origin` | `current.origin` / `display.from` |
| Cảng đến | `destination` | `current.destination` / `display.to` |
| Neo, Phí điện, Đóng ghép, Bảo hiểm, Kiểm định, Health cert | tổng `fee_lines` theo tên loại (danh mục `/api/v7/fee-types`) | như chuyến web |
| Other fee | tổng các khoản còn lại (Khác, Giảm trừ, Phụ phí ban đầu, loại tự thêm) | như chuyến web |
| Đơn giá | `unit_price_vnd`; `is_missing_price` → trống | `current.unit_price_vnd` / số trong `display.unit_price`; thiếu → trống |
| Tổng | `amount_vnd` của server; thiếu giá → trống | `current.counted_vnd` (thiếu giá và 0 → trống) / `source_total_vnd`, cờ `MISSING_PRICE` → trống |

Lấy chuyến web `status='confirmed'`, chưa xóa; dòng sổ gốc chưa xóa. Tháng = tháng công nợ (`month`) như khối tháng trên sổ. Thứ tự theo ngày, cùng ngày giữ thứ tự sổ (sổ gốc trước, web sau). Dòng TỔNG = tổng cột Tổng khi mọi dòng có Tổng; còn dòng trống thì TỔNG trống và nhãn CHƯA CHỐT.

FROM (tên, địa chỉ, email HTH) là chữ cố định trong `debit-note-xlsx.js`, giống mẫu. TO = tên khách của sổ. DATE = ngày xuất theo giờ Việt Nam.

## Giao tiếp frontend–backend (bước 5, khi có)

Không có lệnh mới. Phiếu dựng từ bản sổ trang đã tải (`ctx.snapshot`) và danh mục phụ phí (`ctx.feeTypes`).

## Nguồn quyết định

- [`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md), [`PHU-PHI-01`](../docs/decisions/phu-phi-01.md) (2): phiếu gửi khách hiện từng khoản phụ phí.

## Hành vi và bất biến

- VND nguyên (BigInt), cộng tổng ở model (ARCH-03); NULL không thành 0: ô không có khoản phụ phí để trống, thiếu giá để trống.
- Không cộng phiếu thu, nợ cũ, điều chỉnh cả tháng vào phiếu.
- Excel ghi số thật (định dạng `#,##0`) để người nhập sửa/điền tiếp được; ngày ghi dạng chữ `dd/mm/yyyy`.

## Module và kiểm

| Thao tác | Module | Kiểm |
| --- | --- | --- |
| Dựng dòng phiếu, tổng | `preview/so-khach-v7-model.js` `debitNote` | `test-so-khach-v7-model.js` |
| Ghi file `.xlsx` | `preview/debit-note-xlsx.js` | `test-debit-note-xlsx.js` (mở zip, CRC, XML) |
| Nút, hộp xem trước, in | `preview/so-khach-v7-debit-ui.js` | `test-so-khach-v7-debit-browser.js` |

## Tiêu chí nghiệm thu

- [ ] `npm run check` xanh.
- [ ] Hộp mở/đóng bằng bàn phím, Esc trả focus về nút; tải Excel ra file mở được.
- [ ] Người dùng xuất một tháng của sổ thật trên `hao`, đối chiếu với mẫu đang gửi khách (CÒN MỞ).

## Hoàn tác

Revert PR; không đụng dữ liệu.
