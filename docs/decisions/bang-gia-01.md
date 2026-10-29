# BANG-GIA-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chốt bảng giá theo ngày hiệu lực trên web ([`specs/v7-bang-gia-hieu-luc.md`](../../specs/v7-bang-gia-hieu-luc.md)): (1) **mọi người** vào được app đều sửa được bảng giá, mọi thay đổi ghi Lịch sử và người làm; (2) bảng giá **không dùng chung** nhiều sổ, mỗi sổ một bảng; (3) bảng giá có hai giá: **giá TT** cho shipper của TT, **giá khách** cho mọi shipper còn lại (kể cả shipper trống); (4) hiện giá **không khác theo cảng đích**; (5) **không** áp bảng giá cho dòng sổ gốc thiếu giá, vẫn nhập tay; (6) thêm đợt giá mới thì web hỏi và mặc định **đóng đợt cũ** vào ngày liền trước. Ngày tra giá là ngày xe nhập kho ([`DATE`](date.md)).

## Ngày / nguồn

29/10/2026, người dùng trả lời Q1–Q6 trong chat sau khi đọc spec

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách. Các nguyên tắc thiết kế trong spec (gõ tay thắng bảng giá, sửa bảng giá không tự đổi chuyến đã ghi mà mời áp lại, tra không ra thì NULL kèm lý do, cờ "khác bảng giá" chỉ tô màu) là ĐỀ XUẤT của Claude theo các quy tắc đã chốt `V7-BE`, khóa tháng 24/10 và `NHAP-SHEET-01`. Backend giai đoạn 1 ĐÃ CODE và kiểm bằng harness dữ liệu giả 29/10/2026 (migration `2026-10-29-v7-bang-gia.sql`); chưa triển khai `hao`, chưa có giao diện.

**Cập nhật 29/10/2026:** backend (migration + hàm + API) ĐÃ TRIỂN KHAI trên `hao` bằng đợt tay, xem [nhật ký](../deploys/2026-10-29-bang-gia-chung-tu.md); giao diện chưa có.

**Cập nhật 29/10/2026 (giao diện):** khung Bảng giá đầu tiên bị người dùng báo "không dùng được, không ai hiểu"; thay bằng giao diện lưới giống vùng bảng giá trên Sheet sau khi người dùng thử mockup v2 và chốt "Ổn, làm thật" (xem spec, giai đoạn 2). Không đổi quy tắc giá hay API.

**Cập nhật 29/10/2026 (rà đường ghi tiền):** server chặn bảng giá ghi đè đơn giá gõ tay (`PRICE_TYPED_PRICE`): `apply_price_table` chỉ ghi chuyến chưa có đơn giá hoặc đang mang đơn giá do bảng ghi (áp lại); trước đó chỉ giao diện lọc. Migration `2026-10-29-v7-ra-ghi-tien.sql`.
