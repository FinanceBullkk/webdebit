# Hộp ngoại lệ P3a: máy tự lấy chữ mô tả theo Sheet; tháng khóa sửa được bốn ô chữ

Trạng thái: ĐÃ TRIỂN KHAI trên `hao` 1/11/2026, máy đã bật 19:22 ([nhật ký](../docs/deploys/2026-11-01-khoa-chu.md)). Giai đoạn P3 của [UX bước 03](../docs/ux-buoc-03-luong-thao-tac.md), phần Q1 của [`HANG-CHO-01`](../docs/decisions/hang-cho-01.md), kèm [`KHOA-CHU-01`](../docs/decisions/khoa-chu-01.md). Người dùng bảo "Làm P3", rồi chọn "Cho sửa, ghi Lịch sử" (chat 1/11/2026). P3b (máy tự đưa chuyến mới vào sổ, Q2/Q5) làm sau.

## Người dùng và luồng (bước 1)

- **Máy:** sau mỗi lượt hộp ngoại lệ tính xong, với mỗi sổ có dòng lệch **toàn ô chữ** (hãng tàu, shipper, nơi đi, nơi đến), máy bấm thay "lấy theo Sheet". Đi đúng lệnh `resolve_sheet_conflict` mà người vẫn bấm; người làm trong Lịch sử là "Máy (theo Sheet)".
  - Dòng lệch ngày, container, booking, khách khác, thiếu shipper trên Sheet, hoặc Sheet để trống thì máy không đụng, để người quyết.
  - Công tắc `WEBDEBIT_AUTO_SHEET=text` trên `hao`, mặc định tắt.
- **Người nhập**, ở Việc cần làm: đầu hộp có dòng "Máy đã tự lấy theo Sheet hôm nay: n ô chữ ở m sổ". Bấm xem danh sách (sổ, container, ô, trước → sau, mở sổ). Sai thì mở sổ, sửa lại tại ô.
- **Người sửa tại sổ:** ở tháng khóa, bốn ô chữ của chuyến web và dòng sổ gốc giờ bấm sửa được (KHOA-CHU-01). Container, ngày, tiền, xóa vẫn khóa.

## Đầu ra

944 chỗ lệch chữ (đo trên `hao` 1/11/2026, đều ở tháng khóa, đều là dòng sổ gốc) được máy lấy theo Sheet khi bật công tắc. Hộp ngoại lệ chỉ còn lệch cần người.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Cần | Có sẵn | Thêm |
| --- | --- | --- |
| Dòng lệch, ô lệch, giá trị web và Sheet | `sheet_projection`: `sync_state`, `sync_reason`, `changed_fields`, `existing_kind/id`, `existing_values`, giá trị Sheet theo tên ô | Không |
| Lệnh ghi | `resolve_sheet_conflict` (SQL). DB kiểm giá trị web chưa đổi (`STALE_LEDGER`) và ghi event `sheet_conflict_resolved` | Migration `2026-11-01-v7-khoa-chu.sql`: không đòi tháng mở cho bốn ô chữ |
| Sửa tay ở tháng khóa | `edit_trip_info`, `edit_legacy_trip` đòi tháng mở cho mọi ô | Cùng migration: bốn ô chữ không đòi tháng mở |
| Tên người làm | `v7_presence.display_name` lấy phần trước `@` | `MACHINE_NAMES`: "Máy (theo Sheet)" |

## Hành vi và bất biến

- Không đổi tiền: bốn ô chữ không vào số tiền; giá đã lưu trên chuyến không tự tính lại khi đổi tuyến.
- Mỗi ô một khóa chống ghi trùng cố định theo (bản chụp, dòng Sheet, đích, ô, giá trị Sheet).
- Phiên bản sổ nối tiếp qua từng lệnh. Lỗi ở một sổ thì dừng sổ đó (đếm vào `auto.errors`); lượt sau thử lại.
- Danh sách "máy đã làm" giữ trong RAM của API (300 việc gần nhất), mất khi khởi động lại. Lịch sử từng sổ vẫn là nguồn đủ.

## Tiêu chí nghiệm thu

- [x] Harness `KHOA-CHU.01`: tháng khóa sửa được bốn ô chữ (chuyến web, sổ gốc, lấy theo Sheet) có Lịch sử; tiền, ngày, container, xóa vẫn `MONTH_LOCKED`; số dư không đổi; migration chạy hai lượt không đổi catalog.
- [x] Unit: máy tắt mặc định; khi bật chỉ lấy ô chữ, đúng phiên bản nối tiếp, đúng người làm, bỏ lệch ngày/thiếu shipper/giá trị trống.
- [x] Trình duyệt: dòng "Máy đã tự lấy theo Sheet hôm nay"; sổ khóa mở bốn ô chữ.
- [x] Trên `hao`: sau khi bật công tắc, số lệch chữ giảm về gần 0. Mỗi sổ có Lịch sử "Máy (theo Sheet)"; số dư 236 khách không đổi. (1/11/2026: 944 → 0, 1.316 ô ở 69 sổ, số dư bằng.)
