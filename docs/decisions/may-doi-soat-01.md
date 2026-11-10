# MAY-DOI-SOAT-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt hướng: **web tự chạy theo Sheet, không cần người nhập thao tác trên web**, trong thời gian Sheet còn là sổ chính thức ([`SONG-SONG-01`](song-song-01.md)). Người nhập vẫn ghi trên Sheet. Chủ sổ chỉ xem một danh sách ngắn những gì máy không tự khớp được.

1. **Máy tự đối soát mỗi giờ, từ 7 tới 22 giờ VN**, đúng các bước của đối soát chính thức (tải xlsx, `v7_export_clean`, so tổng từng khách). Kết quả hiện ở đầu tab Việc cần làm. Thay vế "người nhập chạy cuối ngày" của [`SONG-SONG-02`](song-song-02.md); hướng dẫn chạy tay giữ làm dự phòng.
2. **Máy chỉ ghi tiền khi có đúng một tổ hợp việc đưa tổng khách về đúng tổng Sheet tới từng đồng.** Tổng Sheet và việc đang chờ lấy từ cùng một bản tải. Không có tổ hợp nào, hoặc có nhiều tổ hợp, thì không ghi gì và ghi lý do cho chủ sổ. Ghi xong đọc lại sổ để kiểm. Hơn 40 khách lệch cùng lúc thì chỉ báo, không ghi. **Đơn giá đổi chỗ vòng tròn trong một tháng** (giá web → giá Sheet tạo thành vòng, dấu hiệu Sheet xếp lại một phần cột) thì máy không ghi giá tháng đó dù tổng khớp, và báo chủ sổ (Claude thêm 4/11/2026: một sổ thật có 3 đơn giá đổi vòng, tổ hợp vẫn khớp đúng tổng, một phiên Claude khác phát hiện trước khi bật). **Đơn giá trượt qua một ô trống** cũng tính là đổi chỗ: một chuyến web có giá mà dòng Sheet của nó đang trống giá, và cùng tháng có dòng khác được Sheet ghi đúng giá web của chuyến đó (cập nhật 10/11/2026, dưới).
3. **Việc máy được ghi trong tổ hợp đó:**
   - phiếu thu Sheet sẵn sàng;
   - phiếu Sheet không ghi ngày: lấy **ngày cuối tháng của khối Sheet** chứa phiếu, không sau hôm nay;
   - tháng Sheet đã sửa phiếu cũ: thay khoản thu sổ gốc Sheet không còn bằng đúng các phiếu Sheet đang ghi;
   - giá Sheet: dòng sẵn sàng, dòng vướng tháng khóa, và **giá Sheet khác giá web, ở mọi tháng**, trừ dòng đã bấm "Giữ giá web" ([`VCL-GIU-01`](vcl-giu-01.md));
   - dòng Sheet có TỔNG mà đơn giá trống, chuyến web chưa có giá và chưa tính đồng nào: **lấy TỔNG làm đơn giá**;
   - dòng Sheet có tiền mà không có container: **ghi thành dòng điều chỉnh của tháng đó**, ghi rõ số dòng trên Sheet. Dòng như vậy có thể chỉ là chuyến chưa nhập xong, nên khi Sheet không còn dòng đó, dòng điều chỉnh của máy thành một việc hủy, cũng theo điều kiện khớp tổng (Claude thêm, sau khi đo trên `hao` 4/11/2026: một dòng có container sau vài giờ và máy đưa thành chuyến thật).
4. **Web đi trước Sheet tính riêng.** Chuyến web đã có giá mà Sheet chưa ghi (dòng Sheet chưa có giá lẫn TỔNG, hoặc chưa có dòng của container đó) là phần đã giải thích: cộng vào tổng Sheet khi xét khớp, và được liệt kê. Khách lệch đúng bằng phần này thì không có gì để làm. Tháng có dòng điều chỉnh trừ đúng bằng phần này thì tiền đã ra khỏi sổ, không tính là đi trước (Claude thêm 4/11/2026, sửa lỗi cách tính: một sổ thật có 4 chuyến dời sổ theo booking, trừ bằng một dòng điều chỉnh tay, nên máy bỏ qua một phiếu đúng). **Dòng Sheet có tiền mà mất container**, trùng tháng và trùng số với một chuyến web có giá mà tab không còn container đó, là cùng một khoản tiền: chuyến đó không tính là đi trước và dòng đó không thành dòng điều chỉnh mới (cập nhật 10/11/2026, dưới).
5. **Sổ đã khớp Sheet thì ẩn việc còn treo khỏi Việc cần làm**, khi tổng sổ chưa đổi từ lượt đối soát đó: việc từ Sheet và "chưa giá" ở đó không làm số đúng hơn. Chờ kiểm, số dư đầu, mặt hàng vẫn hiện. Sổ còn dòng giá khác giá Sheet thì không ẩn dù tổng khớp, vì đó là hai chỗ bù trừ nhau. Có nút hiện lại.

Tháng khóa làm như [`MAY-KHOA-01`](may-khoa-01.md): máy mở, ghi, khóa lại. Mọi lệnh đi qua các lệnh ghi có sẵn và vào Lịch sử với người làm "Máy (theo Sheet)".

Vẫn để người: nhiều chuyến khớp một dòng giá, phụ phí gõ tay, chuyến chờ kiểm, phiếu ngày tương lai, phiếu web đã xóa, phiếu ghi từ Sheet đã bị người hủy (từ 10/11/2026), Sheet xóa dòng chuyến, khách bị giữ vì số dư trên Sheet tự lệch.

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

Phép so chỉ thấy khách đã có trong phép so: tab mới mà chưa vào thì tổng Sheet lẫn tổng web đều chưa tính, hai bên vẫn khớp. Từ 4/11/2026 tab mới đủ điều kiện được máy tạo sổ ([`MAY-TAO-SO-01`](may-tao-so-01.md)); tab chưa đủ điều kiện, còn nợ, có phát sinh từ tháng 10/2026 thì mỗi lượt báo kèm lý do.

Hết hiệu lực khi chuyển hẳn khỏi Sheet, vì lúc đó web là sổ chính, không còn "theo Sheet". Câu hỏi "chuyển hẳn thế nào khi không còn người nhập trên web": từ 5/11/2026 chưa chuyển, giữ Sheet làm nơi nhập, xét lại sau đối soát cuối tháng 11 ([`CHUYEN-HAN-01`](chuyen-han-01.md)).

**Cập nhật 6/11/2026:** [`VIEC-DOI-CHIEU-01`](viec-doi-chieu-01.md) thay cách hiện của mục 5: việc của sổ đã khớp nằm ở tab Dọn chi tiết thay vì ẩn sau nút; luật máy không đổi.

**Cập nhật 10/11/2026 (thu hẹp điều kiện ghi):** người dùng giao review chỉ đọc máy đối soát, đọc kết quả rồi nói "Mở PR". Review tái hiện bằng dữ liệu giả hai ca máy ghi sai mà tổng vẫn "khớp", vì phần hở được tính là web đi trước, nên khách hiện là đã sửa và không ai phải xem:

- Sheet xếp lại container mà cột giá đứng yên, trong vòng đổi chỗ có một ô giá trống. Vòng không khép kín nên luật đổi chỗ vòng tròn không thấy; máy ghi đè giá một chuyến đang đúng và web dư đúng bằng giá chuyến bị trống. Máy giá 15 phút ghi dòng sẵn sàng trước là đủ, không cần lệch nào khác. Từ nay tháng như vậy không có nhóm giá và báo đổi chỗ.
- Ô container của một dòng Sheet bị xóa trong khi web đã có chuyến đó. Chuyến web thành "đi trước", dòng Sheet thành "dòng tiền không container"; cùng lượt có một việc khớp đúng khác thì máy ghi thêm dòng điều chỉnh, tính trùng. Từ nay hai thứ đó ghép thành một cặp, không phải việc; dòng điều chỉnh máy đã lỡ ghi cho dòng đó thành việc hủy.

Giới hạn: hai ca ghi sai mới tái hiện trên dữ liệu giả. Đo chỉ đọc trên `hao` 10/11/2026 (một lượt không `--fix` bằng code mới, rồi so cách tính cũ với mới trên cùng bản tải và cùng lần đọc sổ): cả 239 sổ cho kết quả giống hệt, 3 khách web đi trước giữ nguyên kết luận, không lệnh ghi nào được gọi. Lúc đo không sổ nào có nhóm giá hay dòng tiền không container đang chờ, nên số đo chỉ cho biết luật mới không đổi gì ở trạng thái hôm đó, chưa cho biết tỷ lệ báo nhầm về lâu dài. Luật thứ nhất có thể báo đổi chỗ nhầm khi người sửa giá một chuyến về đúng bằng giá một chuyến web đi trước cùng tháng; báo nhầm thì máy chỉ không ghi giá tháng đó. Bản hai dòng (một chuyến bị trống giá, một chuyến chưa giá nhận đúng giá đó) không phân biệt được với ca bình thường nên vẫn không bắt. Không đổi DB, quyền, hàm SQL, luật phân bổ.

CÒN MỞ từ lượt review này, chưa đổi: web đi trước không có giới hạn thời gian, nên chuyến Sheet đã xóa hoặc đổi container vẫn hiện là "không cần làm gì".

**Cập nhật 10/11/2026 (phiếu người đã hủy):** cùng lượt review thấy phiếu máy ghi bị người hủy mà Sheet còn dòng thu thì lượt sau tổng lại khớp và máy ghi lại đúng phiếu đó, mỗi giờ một lần. Claude hỏi "phiếu người đã hủy thì máy không tự ghi lại?", người dùng chọn "Sửa F4". Từ nay dòng Sheet mà phiếu ghi từ chính nó đã bị hủy trên web là việc của người: máy đối soát và nút "Ghi N phiếu thu từ Sheet" đều không ghi lại, dòng hiện ở "Phiếu thu Sheet cần xem". Luật nhận ra ở [spec hàng chờ phiếu](../../specs/v7-receipt-queue.md). Hệ quả: khách đó lệch đúng bằng số tiền phiếu cho tới khi người xóa dòng thu trên Sheet hoặc nhập lại phiếu tay, và trong lúc đó máy không tự sửa việc khác của khách này, vì không còn tổ hợp nào đưa tổng về đúng Sheet. Hoàn tác ở tab đối chiếu ([`VIEC-DOI-CHIEU-01`](viec-doi-chieu-01.md)) hủy phiếu bằng đúng lệnh đó, nên phiếu đã hoàn tác không bị máy ghi lại; giá đã hoàn tác thì máy vẫn có thể ghi lại khi tổng khớp. Không đổi DB, quyền, hàm SQL. Đo chỉ đọc trên `hao` 10/11/2026 (so hàng chờ phiếu cũ với mới trên cùng bản tải và cùng lần đọc sổ): 239 sổ, 1.264 dòng thu trên Sheet, không dòng nào đổi trạng thái; cả hệ thống có 7 phiếu đã hủy, 2 trong đó ghi từ Sheet và dòng Sheet của chúng không còn chờ.
