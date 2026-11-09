# CHAN-DOAN-LECH-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Khi một khách lệch mà máy đối soát không tự sửa được, máy **đoán chỗ gây lệch và nói ra**, chỉ để người xem, **không ghi theo lời đoán**. Có bốn kiểu, cả bốn đều là ca thật ngày 9/11/2026:

1. **Phiếu thu ghi hai lần:** hai phiếu chưa hủy, cùng ngày, cùng số tiền. Ví dụ: phiếu ghi tay trước, sau đó Sheet dời ô, nên máy ghi thêm một phiếu mới cho cùng khoản.
2. **Dòng hàng giá cần người** (`MANUAL`, `CONFLICT`, `MONTH_LOCKED`) mà Sheet tính khác web, ví dụ dòng có phụ phí chia theo loại.
3. **Dòng Sheet có tiền mà web không có dòng nào**, ví dụ ô container ghi "… 取消".
4. **Khách bị giữ vì chuỗi số dư:** tháng đầu tiên có số cuối tháng trên Sheet khác với số tháng trước chuyển sang + phát sinh − thu. Thường do ô số dư chuyển sang đầu khối trống hoặc trỏ sai dòng.

Cột "Vì sao máy chưa tự sửa" ở Việc cần làm hiện tối đa hai lời đoán. Mở bảng đối chiếu thì thấy đủ. Nếu có tổ hợp lời đoán cộng lại đúng bằng số lệch tới từng đồng, máy nói rõ điều đó.

**Không làm:**

- Không tự hủy phiếu, không tự sửa phụ phí, không tự thêm dòng theo lời đoán. Chốt "đúng một tổ hợp việc đang chờ khớp tổng tới từng đồng" của [`MAY-DOI-SOAT-01`](may-doi-soat-01.md) giữ nguyên. Cả bốn kiểu trên đều cần người quyết: phiếu nào thừa, phí hủy cont có tính khách không, có ghi Sheet không.
- Chưa dùng AI để đoán. Các kiểu lặp lại thì code thành luật như thế này. AI chỉ xét sau, cho những ca máy vẫn chưa giải thích được.

## Ngày / nguồn

9/11/2026, chat. Ba khách lệch (hai khách lệch tổng, một khách bị giữ) đều hiện câu "không có việc nào giải thích được" hoặc "chưa đọc được". Claude soi tay mất khoảng một giờ thì ra cả ba nguyên nhân. Người dùng hỏi có nên thêm Claude chạy theo lịch. Claude đề xuất code các kiểu này trước, người dùng chọn "Làm luôn".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi phần giải thích trong `reconcile.json` và màn Việc cần làm; không đổi luật tiền, điều kiện ghi, DB hay quyền. Chi tiết ở [spec](../../specs/v7-may-doi-soat.md#máy-đoán-chỗ-lệch-chan-doan-lech-01).
