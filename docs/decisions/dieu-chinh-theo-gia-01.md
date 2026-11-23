# DIEU-CHINH-THEO-GIA-01

[← Sổ quyết định](../decisions.md)

**ĐÃ CHỐT** bởi người dùng trong chat ngày 23/11/2026 lúc 08:58 UTC: bấm "Cách A: bỏ điều chỉnh" trả lời câu hỏi mục F6 của audit SQL lõi tiền 23/11/2026.

## Quyết định

Điều chỉnh tiền của một chuyến (`adjust_trip`) chỉ tính vào số dư khi chuyến **còn số tiền gốc**: có đơn giá, hoặc là dòng chỉ phụ phí (không container) có phụ phí. Đây đúng là điều kiện để chính chuyến đó được cộng vào nợ.

- Xóa đơn giá của chuyến: cả chuyến lẫn điều chỉnh của nó ra khỏi số dư. Chuyến hiện "thiếu giá" như trước.
- Nhập lại đơn giá: điều chỉnh tính lại, không phải ghi lại.
- Dòng điều chỉnh không bị xóa hay sửa; chỉ không được tính và không hiện trong danh sách điều chỉnh của sổ khi chuyến không còn giá.
- Không đổi: điều chỉnh cả tháng (`adjust_month`), dòng sổ gốc, chuyến CHỜ KIỂM/đã loại (vẫn không tính như trước).

Cách B (chặn xóa đơn giá khi chuyến còn điều chỉnh) không chọn.

## Lý do

Trước đây chuyến không giá ra khỏi số dư (`V7-BE` (1): chuyến chưa có đơn giá nằm ngoài số dư) nhưng điều chỉnh của nó vẫn tính, nên sổ mang một khoản âm/dương lơ lửng cho chuyến đang "thiếu giá".

## Phạm vi và triển khai

- View `sokhach.v_adjustment_current`, migration `2026-11-23-v7-dieu-chinh-theo-gia.sql`; `schema_level()` = `2026112302`.
- Đo chỉ đọc trên `hao` 23/11/2026: không có điều chỉnh chuyến nào đang tính, nên số dư mọi sổ không đổi lúc nâng.
- Test: `AUDIT-SQL.01` (xóa giá → số dư bỏ cả chuyến và điều chỉnh; nhập lại → tính lại), mô hình bất biến tiền (`test_pg_v7_bat_bien.py`).
