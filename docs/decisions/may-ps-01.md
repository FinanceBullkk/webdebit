# MAY-PS-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **ô "Health+KĐ" của bảng PS không tách thành hai khoản, mà ghi nguyên số vào một loại phí gộp "Health + KĐ", và máy tự làm.** Lý do: mọi nguồn chỉ có một số gộp, nên chia ra là đoán, mà phiếu gửi khách hiện từng khoản ([`PHU-PHI-01`](phu-phi-01.md) (2)).

Máy (người làm trong Lịch sử là "Máy (theo Sheet)") tự làm ba việc, không đổi tổng còn nợ của khách:

1. **Tự tách theo PS:** mọi chuyến tách được, gồm cả chuyến chỉ vướng tháng khóa. Tháng khóa thì mở, ghi, khóa lại như [`MAY-KHOA-01`](may-khoa-01.md). Thay câu "Giữ khóa tháng" của người dùng ngày 29/10/2026 ở [spec](../../specs/v7-phu-phi-tu-ps.md).
2. **Bổ sung khoản còn thiếu ở dòng sổ gốc:** khi ô TOTAL trừ đơn giá bằng đúng tổng PS mà các khoản trên web chưa đủ, máy ghi đủ khoản theo PS. Ô TOTAL giữ nguyên.
3. **Tự chọn cột:** sau khi tách ở một sổ, máy đưa các loại nhiều tiền nhất của sổ đó lên cột riêng (tối đa 3). Cột đang không nằm trong nhóm này mới bị thay, thay từ cột cuối; thứ tự các cột còn lại giữ nguyên. Khoản không có cột vẫn nằm ở cột Khác. Chỉ chạy khi máy vừa tách ở sổ đó, nên không đè lại lựa chọn của người ở các lần sau.

Vẫn để người xem: tổng PS khác tổng web (`TOTAL_DIFF`), web đã phân loại khác PS (`TYPED_CONFLICT`), bộ lập bill báo lỗi, ô PS gõ sai, nhiều chuyến khớp. Máy cũng không tự tách khi việc thay khoản làm mất một ghi chú người đã gõ; dòng đó chờ người bấm nút Tách. Ghi chú do migration phụ phí tự sinh (`migration: legacy fee`, `migration: initial fee`) không tính, trước → sau vẫn nằm trong Lịch sử.

**Khác `MAY-GIA-01`:** không có mốc 10/2026, vì việc này chỉ phân loại, không đổi tiền. Bảng PS hiện có tiền ở các tháng từ 5/2026.

## Ngày / nguồn

4/11/2026, chat. Claude đọc chỉ đọc file PS gốc (tab `CHI PHÍ PS T6`), `PS_DATA`, `CONT_MASTER`, `DEBIT NOTE` và tab khách: cột `HEALH+KD` chỉ có một số, ghi chú chỉ có "XONG"; các cột Health/Kiểm định riêng chỉ là cờ. Có 6 cont 3.000.000đ và 1 cont 10.000.000đ, nên không có tỉ lệ cố định. Claude đề xuất loại gộp cùng cả ba việc trên, người dùng trả lời "Làm loại gộp".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thay vế "cần tách tay" của `PS_COMBINED` trong spec. [`PHU-PHI-01`](phu-phi-01.md) (10) vẫn giữ: loại riêng Health cert và Kiểm định vẫn dùng khi có giá riêng; cờ Health/KĐ vẫn chỉ nhắc, không tạo tiền, và không nhắc nữa khi chuyến đã có khoản gộp.

Đổi DB: thêm loại phí "Health + KĐ" và nới `_rewrite_trip_fees` cho việc 2, migration [`2026-11-04-v7-ps-gop.sql`](../../cong-no-web-handoff/tools/migrations/2026-11-04-v7-ps-gop.sql). Bật máy bằng `WEBDEBIT_AUTO_SHEET` có `ps`, mặc định tắt.

Khoản đã phân loại làm hàng chờ giá xếp dòng đó vào `MANUAL` khi Sheet đổi giá về sau, như mọi phụ phí đã phân loại: người sửa trong khung chi tiết phụ phí.

Hết hiệu lực khi chuyển hẳn khỏi Sheet.
