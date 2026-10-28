# JOIN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chốt duyệt bảng nối opening ↔ mã chuyến (C03), áp dụng cho chuyến có ngày xe nhập kho từ 14/10/2026: (1) hệ thống chỉ gợi ý khi đúng một booking đạt tiêu chí ngày; nhiều ứng viên hoặc thiếu ngày là CHỜ KIỂM; mọi dòng vẫn phải được duyệt từng dòng. (2) Người duyệt là chủ nghiệp vụ bằng tài khoản cá nhân; không duyệt dòng nối cho charge do chính mình lập. (3) Chứng cứ tối thiểu: tham chiếu booking nguồn, thời điểm export/snapshot, người duyệt, thời điểm duyệt; ngày lệch ngưỡng hoặc booking đã sửa phải có lý do, thiếu lý do là CHỜ KIỂM. (4) Thu hồi dòng nối đang được proposal chờ dùng thì chặn ngay; proposal mất điều kiện và phải nộp lại; posting đã ghi không sửa, chỉ điều chỉnh có audit.

## Ngày / nguồn

16/10/2026, xác nhận trong chat; bổ sung 17/10/2026

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách; chưa triển khai bảng resolution production. Ngày 17/10/2026 người dùng chốt ngưỡng gợi ý: ngày đóng booking lệch ngày xe nhập kho **tối đa 3 ngày** (hai chiều); quá ngưỡng hoặc thiếu ngày là CHỜ KIỂM. Gợi ý vẫn phải được người dùng xác nhận khi nhập. **Sửa 21/10/2026:** vế (2) "không duyệt dòng nối cho charge do chính mình lập" **hết hiệu lực** — người dùng chốt bỏ, thống nhất với `V6-DB`/[`V7-ID`](v7-id.md): ai cũng duyệt được, kể cả dòng nối do chính mình lập. Phạm vi "chuyến từ 14/10/2026" của dòng này đọc theo [`MOC-CHUYEN-MOI`](moc-chuyen-moi.md): chuyến chưa có trong bản sổ gốc v2. Dấu `/` theo [ALT-KEY-01](alt-key-01.md), booking sửa theo [BOOKING-EDIT-01](booking-edit-01.md). Duyệt "không nằm trong opening" cho chuyến từ 14/10 theo [NEWTRIP-01](newtrip-01.md). Bảng nối lịch sử 15/10 (chỉ gồm chuyến trước 14/10) không cần duyệt từng dòng, vì thuộc opening theo OPENING-FINAL/LEGACY-A.
