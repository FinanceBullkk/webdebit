# PRICE-MAKER

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: người xác nhận giá là chủ nghiệp vụ (vai trò xác nhận giá); maker được phép đồng thời là người đó và tự xác nhận giá chuyến mình nhập, không cần xác nhận thứ hai. Người xác nhận giá không được checker-approve cùng revision; maker ≠ checker theo D01.

## Ngày / nguồn

16/10/2026, xác nhận trong chat

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách. Fixture CI (PR #10) yêu cầu vai trò `price_owner` để xác nhận giá, cho maker có vai trò đó tự xác nhận, và cấm người xác nhận giá checker-approve cùng revision; chưa có app. **Sửa 19/10/2026:** vế "người xác nhận giá không được checker-approve cùng revision; maker ≠ checker theo D01" **hết hiệu lực** theo `V6-DB` — không còn bước duyệt thứ hai. Vế còn hiệu lực: người xác nhận giá là chủ nghiệp vụ, và maker được tự xác nhận giá chuyến mình nhập.
