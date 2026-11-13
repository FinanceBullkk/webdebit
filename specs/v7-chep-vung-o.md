# Chọn vùng ô và chép như Sheet ở bảng chuyến (CHEP-O-01)

Trạng thái: **ĐÃ TRIỂN KHAI khi PR merge** (Claude, 13/11/2026). Người dùng hỏi "chúng ta không copy được giống như Sheet hả?" kèm ảnh: kéo chuột trên bảng chuyến thì trình duyệt bôi chữ cả hàng, lẫn chữ nhỏ "theo bảng", và không dán được vào Sheet thành đúng ô. Chỉ đọc màn hình: không đổi API, DB, luật tiền.

## Người dùng và luồng

**Ai, khi nào:** người nhập hoặc chủ nghiệp vụ, ở thẻ Sổ, muốn chép vài chuyến (container, ngày, tuyến, giá…) sang Sheet, Excel hay tin nhắn.

1. Kéo chuột từ một ô tới ô khác trong bảng "Chuyến trong tháng": vùng chữ nhật tô xanh nhạt, viền xanh như Sheet. Không bôi chữ, không mở ô sửa.
2. Hoặc đứng ở một ô, Shift+bấm ô khác, hay Shift+mũi tên (lên/xuống/trái/phải) để mở rộng vùng.
3. Ctrl+C: chép vùng thành chữ cách bằng Tab, mỗi hàng một dòng; góc báo "Đã chép 3 hàng × 7 cột". Không có vùng thì Ctrl+C chép ô đang đứng.
4. Ctrl+V ở Sheet: ra đúng ô. Esc, hoặc bấm chỗ khác, bỏ vùng.

## Chữ chép

- Số tiền chép liền, không dấu chấm (`85.000.000` → `85000000`) để Sheet tiếng Anh hay tiếng Việt đều đọc ra số.
- Ô "–" và "chưa có giá" chép thành ô trống (trống không phải 0).
- Cột Tuyến chép thành hai cột Nơi đi, Nơi đến như Sheet.
- Không chép chữ nhỏ trong ô (theo bảng, bảng …, KHÁC, CHỜ DUYỆT), nút, ô tick; nhãn "chờ kiểm"/"đã loại" giữ.
- Ngày như trên màn (dd/mm/yyyy).

## Bất biến

- Chỉ đọc chữ đang hiện; không gửi lệnh, không đổi số.
- Đang gõ trong ô nhập thì Ctrl+C là của ô nhập; có chữ đang bôi ngoài bảng thì để trình duyệt chép.
- Bấm một ô (không kéo) vẫn mở ô sửa như cũ; kéo rồi quay về đúng ô đầu cũng như bấm.
- Sổ vẽ lại (sau khi lưu, đọc lại) thì vùng mất, như chọn lại từ đầu.

## Phạm vi và kiểm

- Mã: `cong-no-web-handoff/preview/so-khach-v7-copy-ui.js` (phần `copy` trong `so-khach-v7-ctx.js`), thẻ script ở `so-khach-v7-live.html`, CSS ở `so-khach-v7.css`.
- Test: `test-so-khach-v7-chep-browser.js` (kéo chuột, Shift+mũi tên, Shift+bấm, Esc, chép một ô, ô đang gõ).
- Ngoài phạm vi: bảng phiếu thu, bảng chi tiết (SO-CHI-TIET-01), điện thoại; dán vùng nhiều cột vào sổ (dán cột giá đã có ở GIA-O-01).
