# V7-MH

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt mặt hàng gắn theo sổ khách: một sổ (một dòng `TONG`) một mặt hàng, không gắn theo chuyến, không tách "công ty"; sầu riêng là một mặt hàng, cảng/bộ là phương thức vận chuyển riêng (áp cho sầu riêng, xoài, thanh long); "BAN CUOC" và "HANG NHAP" gán như mặt hàng; dùng để lọc danh sách khách và xác định sổ khi nhập, không đổi cách tính nợ. Sổ có dòng `TONG` là đang dùng; archive chỉ cho tab vừa không có dòng `TONG` vừa không có số dư mở; ~~khách có nợ ở tab không có dòng `TONG` vẫn tính vào thống kê, mặt hàng gán tạm `CHUA PHAN LOAI` để xem lại~~ (**thay 21/10/2026 bởi [`V7-TONG`](v7-tong.md):** tab không có tên trên `TONG` bị loại, kể cả còn số dư)

## Ngày / nguồn

20/10/2026, xác nhận trong chat; bảng đối chiếu ngoài Git ở `design/2026-10-20/`

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thiết kế (`customer.commodity_id`, `transport_mode`, cờ `archived`, lệnh gán/đổi) là ĐỀ XUẤT trên nhánh `codex/v7-opening-read`, chưa có thân hàm/harness. **Chốt 21/10/2026:** không chặn nhập chuyến/thu vào sổ khách archived, chỉ cảnh báo khi người dùng thao tác trên sổ đó (đề phòng archive nhầm). CÒN MỞ: mặt hàng thật của các khách đang `CHUA PHAN LOAI`.
