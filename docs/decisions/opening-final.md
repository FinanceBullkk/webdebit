# OPENING-FINAL

[← Sổ quyết định](../decisions.md)

## Quyết định

(**THAY BỞI [`MOC-CHUYEN-MOI`](moc-chuyen-moi.md)** ngày 20/10/2026: opening đổi sang sổ gốc và mốc chuyến mới là bản sổ gốc v2, không còn là ngày xe nhập kho 14/10. Phần "21 chuyến 01–13/10 coi như đã xử lý" được đo theo replay 13/10; đối chiếu 20/10 cho thấy cả 21 chuyến có trong sổ gốc — xem (c) ở dòng mới.) Người dùng/chủ nghiệp vụ chốt: opening 13/10/2026 16:44 là đủ cho mọi chuyến có ngày xe nhập kho **trước 14/10/2026**. Chuyến 01–13/10 đã nằm trong opening giữ nguyên (44 dòng); chuyến 01–13/10 chưa nằm trong opening (21 chuyến) coi như đã xử lý, không nhập thêm. Dữ liệu chi tiết nằm ngoài repo. Hệ thống mới chỉ nhận charge có ngày xe nhập kho từ 14/10/2026.

## Ngày / nguồn

16/10/2026, xác nhận trong chat ("opening là đủ, chốt luôn"); thay mốc 01/10 nêu ngày 15/10

## Hiệu lực và giới hạn

ĐÃ CHỐT. ĐÃ KIỂM CHỨNG chỉ ở mức fixture CI: fixture tại `0e1330b` đã từ chối charge có ngày xe trước 14/10 (trường `event_date`); fixture CI (PR #10) đã đổi tên trường sang `warehouse_in_date` và cài thông báo "chuyến cũ, nợ thuộc opening 13/10"; chưa có app/DB production. Ngày xe từ 14/10 tự nó chưa đủ chứng minh chuyến vắng khỏi opening; quy tắc kiểm trùng ở [NEWTRIP-01](newtrip-01.md). Từ 19/10/2026 opening hiện hành là sổ gốc ([`OPENING-SO-GOC`](opening-so-goc.md)), có cả khối tháng 10/2026; mốc được chốt lại ngày 20/10/2026 bằng [`MOC-CHUYEN-MOI`](moc-chuyen-moi.md).
