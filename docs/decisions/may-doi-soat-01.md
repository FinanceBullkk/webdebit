# MAY-DOI-SOAT-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt hướng: **web tự chạy theo Sheet, không cần người nhập thao tác trên web**, trong thời gian Sheet còn là sổ chính thức ([`SONG-SONG-01`](song-song-01.md)). Người nhập vẫn ghi trên Sheet. Chủ sổ chỉ xem một danh sách ngắn những gì máy không tự khớp được.

1. **Máy tự đối soát mỗi giờ, từ 7 tới 22 giờ VN**, đúng các bước của đối soát chính thức (tải xlsx, `v7_export_clean`, so tổng từng khách). Kết quả hiện ở đầu tab Việc cần làm. Thay vế "người nhập chạy cuối ngày" của [`SONG-SONG-02`](song-song-02.md); hướng dẫn chạy tay giữ làm dự phòng.
2. **Máy chỉ ghi tiền khi có đúng một tổ hợp việc đưa tổng khách về đúng tổng Sheet tới từng đồng.** Tổng Sheet và việc đang chờ lấy từ cùng một bản tải. Không có tổ hợp nào, hoặc có nhiều tổ hợp, thì không ghi gì và ghi lý do cho chủ sổ. Ghi xong đọc lại sổ để kiểm. Hơn 40 khách lệch cùng lúc thì chỉ báo, không ghi. **Đơn giá đổi chỗ vòng tròn trong một tháng** (giá web → giá Sheet tạo thành vòng, dấu hiệu Sheet xếp lại một phần cột) thì máy không ghi giá tháng đó dù tổng khớp, và báo chủ sổ (Claude thêm 4/11/2026: một sổ thật có 3 đơn giá đổi vòng, tổ hợp vẫn khớp đúng tổng, một phiên Claude khác phát hiện trước khi bật).
3. **Việc máy được ghi trong tổ hợp đó:**
   - phiếu thu Sheet sẵn sàng;
   - phiếu Sheet không ghi ngày: lấy **ngày cuối tháng của khối Sheet** chứa phiếu, không sau hôm nay;
   - tháng Sheet đã sửa phiếu cũ: thay khoản thu sổ gốc Sheet không còn bằng đúng các phiếu Sheet đang ghi;
   - giá Sheet: dòng sẵn sàng, dòng vướng tháng khóa, và **giá Sheet khác giá web, ở mọi tháng**, trừ dòng đã bấm "Giữ giá web" ([`VCL-GIU-01`](vcl-giu-01.md));
   - dòng Sheet có TỔNG mà đơn giá trống, chuyến web chưa có giá và chưa tính đồng nào: **lấy TỔNG làm đơn giá**;
   - dòng Sheet có tiền mà không có container: **ghi thành dòng điều chỉnh của tháng đó**, ghi rõ số dòng trên Sheet. Dòng như vậy có thể chỉ là chuyến chưa nhập xong, nên khi Sheet không còn dòng đó, dòng điều chỉnh của máy thành một việc hủy, cũng theo điều kiện khớp tổng (Claude thêm, sau khi đo trên `hao` 4/11/2026: một dòng có container sau vài giờ và máy đưa thành chuyến thật).
4. **Web đi trước Sheet tính riêng.** Chuyến web đã có giá mà Sheet chưa ghi (dòng Sheet chưa có giá lẫn TỔNG, hoặc chưa có dòng của container đó) là phần đã giải thích: cộng vào tổng Sheet khi xét khớp, và được liệt kê. Khách lệch đúng bằng phần này thì không có gì để làm.
5. **Sổ đã khớp Sheet thì ẩn việc còn treo khỏi Việc cần làm**, khi tổng sổ chưa đổi từ lượt đối soát đó: việc từ Sheet và "chưa giá" ở đó không làm số đúng hơn. Chờ kiểm, số dư đầu, mặt hàng vẫn hiện. Sổ còn dòng giá khác giá Sheet thì không ẩn dù tổng khớp, vì đó là hai chỗ bù trừ nhau. Có nút hiện lại.

Tháng khóa làm như [`MAY-KHOA-01`](may-khoa-01.md): máy mở, ghi, khóa lại. Mọi lệnh đi qua các lệnh ghi có sẵn và vào Lịch sử với người làm "Máy (theo Sheet)".

Vẫn để người: nhiều chuyến khớp một dòng giá, phụ phí gõ tay, chuyến chờ kiểm, phiếu ngày tương lai, phiếu web đã xóa, Sheet xóa dòng chuyến, khách bị giữ vì số dư trên Sheet tự lệch.

## Thay thế

- Vế "phiếu thu từ Sheet do người bấm" của [`HANG-CHO-01`](hang-cho-01.md) Q3.
- Vế "giá Sheet khác giá web để người quyết" và mốc 10/2026 của [`MAY-GIA-01`](may-gia-01.md), **chỉ trong tổ hợp khớp tổng ở trên**. Máy ghi giá 15 phút một lần của `MAY-GIA-01` giữ nguyên phạm vi cũ.
- Vế "phiếu không chắc vào Cần xem" của [`THU-SHEET-01`](thu-sheet-01.md), cùng điều kiện.

## Ngày / nguồn

4/11/2026, chat. Sếp hỏi "dùng được và tin được chưa"; Claude rà máy tự ghi và đo hàng chờ. Người dùng nói "rà và xử lý luôn giúp mình. Hướng đến máy có thể tự động hoàn toàn ko cần người nhập nữa". Claude hỏi từng vế, người dùng chọn đúng phương án đề xuất:

- phiếu thu: "Tự ghi, phải khớp tổng";
- giá khác: "Lấy giá Sheet, phải khớp tổng";
- đối soát: "Mỗi giờ, 7–22 giờ";
- dòng chỉ có TỔNG: "Lấy TỔNG làm giá";
- dòng tiền không container: "Ghi dòng điều chỉnh";
- web đi trước Sheet: "Được, tính riêng phần đi trước".

Vế 5 (ẩn sổ đã khớp) do Claude đề xuất trong cùng hướng, không đổi tiền.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chi tiết ở [spec](../../specs/v7-may-doi-soat.md), cách cài ở [runbook](../v7-deploy-runbook.md#máy-tự-đối-soát-may-doi-soat-01--timer-v7-reconcile-auto). Không đổi DB, quyền, luật phân bổ. Không ghi Sheet.

Lưới an toàn là đúng tổng từng khách: hai lỗi bù trừ nhau trong cùng khách thì không lộ, như đối soát chính thức. Máy chỉ bắt được kiểu đổi chỗ khi web đã có giá để so; Sheet xếp lệch cột ở chuyến web chưa có giá thì máy ghi theo Sheet, vì Sheet là sổ chính thức. So từng tháng theo [`CAN-DU-01`](can-du-01.md) chạy kèm ở mỗi lượt để báo khách lệch tháng.

Hết hiệu lực khi chuyển hẳn khỏi Sheet, vì lúc đó web là sổ chính, không còn "theo Sheet". Câu hỏi "chuyển hẳn thế nào khi không còn người nhập trên web" CÒN MỞ: hướng này giữ Sheet làm nơi nhập, nên mục chuyển hẳn F4 của [checklist](../song-song-checklist.md) cần chủ sổ xem lại.
