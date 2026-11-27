# THAY-PHIEU-SHEET-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Sheet sửa hoặc xóa một phiếu thu mà web đã ghi từ Sheet thì máy đối soát theo Sheet: hủy phiếu cũ, ghi phiếu mới. Khách đã khớp tổng mà Sheet còn khoản web chưa theo thì máy vẫn xét: bù đủ thì ghi, không bù đủ thì báo người xem.

1. **Phiếu Sheet không còn.** Phiếu web chưa hủy, hình thức `THU TIỀN`, chứng từ do đường ghi từ Sheet đặt (`Sheet`, `Sheet: …`, `Sheet #…`), mà không dòng Sheet nào nhận nữa, là một nhóm việc riêng (`receipts_gone`). Ghi nhóm này là hủy phiếu với lý do cố định "Sheet không còn dòng thu này (máy theo Sheet)". Phiếu nhập tay, phiếu người đã sửa chứng từ, phiếu cấn trừ hai sổ thì không bao giờ bị máy hủy. Tab của sổ không có trong lượt quét, hoặc có tab lỗi, thì không nêu phiếu nào.
2. **Ghi hết khi mọi việc cộng lại khớp.** Chốt khớp tổng tới từng đồng của [`MAY-DOI-SOAT-01`](may-doi-soat-01.md) giữ nguyên. Thêm: mọi nhóm việc đang chờ cộng lại bằng đúng số lệch thì ghi hết, kể cả khi một phần nhỏ hơn cũng ra đúng số (trước đây là "nhiều tổ hợp, không ghi" hoặc ghi phần nhỏ hơn nếu chỉ phần đó khớp riêng).
3. **Khách đã khớp tổng cũng được xét.** Còn việc chờ mà mọi nhóm bù nhau về đúng 0 (hoặc đúng phần web đi trước) thì ghi hết. Không bù đủ thì không ghi, khách hiện ở "Số nợ lệch" với câu "khớp tổng nhưng Sheet đã đổi vài khoản mà web chưa theo", và việc chờ của sổ không bị ẩn.
4. **Phiếu nhập tay cho dòng không ngày.** Dòng Sheet không ghi ngày ghép với phiếu web cùng số tiền, ngày từ đầu tháng khối trở đi, khi không dòng có ngày nào đã lấy phiếu đó. Người nhập tay thay máy thì dòng không còn chờ.
5. Phiếu máy hủy theo điểm 1 không làm dòng Sheet thành "người đã gỡ" (`WEB_VOIDED` của [`MAY-DOI-SOAT-01`](may-doi-soat-01.md), 10/11/2026): Sheet trả lại dòng cũ thì máy ghi lại được. Phiếu người hủy vẫn như cũ.

## Ngày / nguồn

19/11/2026, chat. Người dùng hỏi Sheet đổi phiếu thu thì web có biết không, vì vừa thấy ở một sổ thật Sheet đổi mà web không theo, phải sửa tay. Claude đọc nhật ký sổ: Sheet đổi giá hai chuyến tháng 10 và thay một phiếu máy đã ghi (không ngày) bằng hai phiếu, hai thay đổi bù nhau đúng tới từng đồng; cùng lúc có một phiếu mới đúng bằng số lệch, máy chỉ ghi phiếu đó và báo khớp. Claude nêu hai hướng: báo và tự thay, hoặc chỉ báo. Người dùng chọn **"Báo và tự thay"**. Điểm 4 và 5 Claude thêm theo [`CLAUDE-ALL-01`](claude-all-01.md) khi làm: không có điểm 4 thì hai phiếu người dùng vừa nhập tay vẫn bị coi là chưa có trên web; không có điểm 5 thì phiếu máy hủy sẽ chặn chính dòng đó về sau.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Không đổi DB, hàm SQL, quyền hay luật phân bổ; hủy phiếu đi qua `void_receipt` có sẵn (bắt buộc lý do, không xét ổ khóa tháng, như người hủy). Mã: `web/v7_receipt_queue.py`, `web/v7_sheet_fix.py`, `tools/v7_reconcile_auto.py`; spec [hàng chờ phiếu](../../specs/v7-receipt-queue.md) và [máy đối soát](../../specs/v7-may-doi-soat.md). Áp dụng trong thời gian chạy song song ([`SONG-SONG-01`](song-song-01.md)), xét lại khi chuyển hẳn.

Đo chỉ đọc trên `hao` 19/11/2026 lúc 16:51 (mã nhánh, chế độ báo, mọi lệnh ghi bị chặn, bản tải Sheet mới): 244 sổ, kết luận giống lượt thật 16:13 (236 khớp, 4 lệch tổng, 4 chỉ có trên web; các khách lệch giữ nguyên lý do). Xét chi tiết 236 khách khớp mất 35 giây: không khách nào còn việc chờ, nên khi lên `hao` máy không ghi gì thêm và không hủy phiếu nào. Sổ của ca 19/11 sau khi người dùng sửa tay cũng không còn việc chờ (hai phiếu nhập tay ghép với hai dòng không ngày theo điểm 4).

Giới hạn: máy chỉ nhận ra phiếu do đường ghi từ Sheet đặt chứng từ. Phiếu nhập tay rồi Sheet đổi thì máy không hủy, khách lệch và hiện ở "Số nợ lệch" như trước. Sheet đổi ngày một phiếu trong vòng 3 ngày thì vẫn coi là cùng phiếu, máy không sửa ngày.

**Cập nhật 25/11/2026 ([`WEB-CHINH-01`](web-chinh-01.md) (3)):** web là sổ chính thức nên vế "máy hủy phiếu cũ, ghi phiếu mới" thôi chạy. Phiếu Sheet không còn (`receipts_gone`) và tháng Sheet sửa phiếu cũ (`receipts_edited`) vẫn được nhận ra và vẫn giải thích số lệch trong tổ hợp, nhưng máy không hủy hay thay phiếu nào; phiếu Sheet mới đi cùng tổ hợp cũng không ghi riêng, vì có thể là chính phiếu bị sửa số. Khách hiện ở "Số nợ lệch" với kết luận `WEB_KEPT`, người hủy hay ghi ở bảng đối chiếu. Điểm 2 và 3 (ghi hết khi mọi nhóm khớp, xét cả khách đã khớp) giữ cho phần thêm.

**Bổ sung 27/11/2026 (sổ 141, [nhật ký](../deploys/2026-11-27-tach-sheet-141.md)):** "còn việc chờ" của điểm 3 trước đây lọc theo tổng nhóm. Nhóm giá gom theo tháng, nên Sheet sửa giá hai chuyến **cùng tháng** bù nhau (sổ thật: +10 và −10 triệu) thì nhóm tổng 0, máy coi như không có việc và bảng đối chiếu cũng ẩn nhóm: sổ khớp tổng mà web sai giá từng chuyến, debit note in sai giá từng dòng. Từ nay nhóm giá còn việc khi có dòng đổi tiền, dù cả tháng cộng lại bằng 0 (`has_work` trong `web/v7_sheet_fix.py`). Theo WEB-CHINH-01 máy vẫn không ghi giá đè web: khách thành `WEB_KEPT`, hiện ở "Số nợ lệch", nhóm ghi "Giá từng chuyến khác, tổng tháng bằng nhau", người xem từng chuyến rồi ghi hoặc giữ số web. Claude sửa theo [`CLAUDE-ALL-01`](claude-all-01.md) sau khi người dùng hỏi "do máy sai hay sao" rồi chọn "Sửa máy đối soát". Quét chỉ đọc 251 sổ cùng ngày: không sổ khớp tổng nào khác đang có kiểu lệch này, nên khi lên `hao` không khách nào đổi kết luận.
