# V5 — quyết định sau review mockup (17/10/2026)

Trạng thái: **ĐÃ CHỐT** bởi người dùng trong chat ngày 17/10/2026, sau review bộ mockup `mockup_v5_da_sua` (9 khung).

Phạm vi: **thiết kế màn hình và mô hình số liệu của sổ công nợ**. Đây **không** phải migration, **không** mở đường ghi tiền, **không** thay nghiệm thu backend. Dùng để: sửa mockup V5 vòng tiếp theo, và làm đầu vào cho spec code sau này.

Nguồn: [brief](ux-brief-so-cong-no.md), [bản ghép V5](ux-v5-ban-ghep.md), [business-rules](../docs/business-rules.md), [đường ghi tiền P0](p0-write-path/decisions-needed.md).

## 1. Chín quyết định

| # | Câu hỏi | Chốt |
| --- | --- | --- |
| 1 | Khoản thu thuộc chuyến hay thuộc sổ? | **Thuộc sổ (khách × loại hàng) + kỳ nợ.** Dòng chuyến chỉ là chỗ gõ, không phải chủ sở hữu khoản tiền |
| 2 | Có cột số lượng không? | **Không.** Giữ đúng 11 cột khi dán |
| 3 | Thành tiền dán hay tính? | **Hệ thống tự cộng**: thành tiền = đơn giá + phí khác + phí cắm điện cảng + phí áp tải |
| 4 | Ai xác nhận chứng từ, căn cứ gì? | **Hoãn.** Chưa xét phân quyền trong vòng này |
| 5 | Còn chứng từ chưa xác nhận thì có chốt tháng được không? | **Được.** Chứng từ vẫn treo, vẫn không vào số dư |
| 6 | Ô phí để trống nghĩa là gì? | **Không có phí.** Ô vẫn hiện `—`, không hiện `0`; khi cộng thành tiền thì coi như không phát sinh |
| 7 | Bỏ một dòng chuyến đã lưu có chứng từ? | **Bỏ cả dòng lẫn chứng từ** — xem giới hạn ở mục 3 |
| 8 | Khách trả dư thì hiện thế nào? | **Để số âm**, hiểu là tiền phải trả lại khách |
| 9 | Tiền dư nằm ở đâu? | Nằm lại **trong sổ đó**, không tự mang sang sổ khác của cùng khách. *Giả định của người dựng, người dùng chưa phản đối* |

## 2. Hệ quả của quyết định 1 — tiền thuộc sổ

- Khoản thu có danh tính riêng: khách · loại hàng · ngày nhận tiền · cách thu · tham chiếu · số tiền. **Không bắt buộc trỏ tới một chuyến.**
- Dòng chuyến nơi người dùng gõ chỉ còn là nhãn tham chiếu — "ghi tại dòng DEMO-105". Sửa, chuyển tháng hay bỏ dòng chuyến **không được làm đổi số tiền đã ghi**, trừ trường hợp mục 3.
- Phân bổ vẫn theo kỳ nợ, nợ cũ trước, và phải xem lại được từng kỳ nhận bao nhiêu (brief §3.7).
- Khớp với [business-rules](../docs/business-rules.md): *"Receipt/allocation: tiền thực nhận khác phân bổ theo kỳ"*, *"giữ số dư theo khách + kỳ"*, và brief quy tắc 9 *"không tự gắn tiền thu vào từng chuyến"*.
- Với Codex khi tới lượt schema: khoản thu là thực thể riêng gắn **khách + loại hàng**, không phải cột trên bảng chuyến. [verification.md](../docs/verification.md) ghi schema hiện **chưa có receipt entity/allocation ledger riêng**, nên đây là phần còn phải dựng, không phải phần đã có.

## 3. Giới hạn của quyết định 7 — bỏ dòng thì bỏ luôn chứng từ

Quyết định này chốt cho **chứng từ chưa xác nhận** (chưa có ngày nhận tiền, chưa vào số dư) — đúng tình huống 5.000.000 trên DEMO-103 trong mockup. Bỏ nó không làm đổi một con số nào trên sổ.

**Không áp dụng cho khoản thu đã xác nhận và đã phân bổ.** Xoá một khoản thu đã trừ nợ các tháng sẽ làm số dư nhảy ngược và sửa ngược lịch sử — trái brief quy tắc 6 và [AGENTS.md](../AGENTS.md) (*không sửa đè posting; đảo/điều chỉnh có audit*). Khoản đã xác nhận chỉ xử lý bằng **đảo khoản thu riêng, có lý do và lưu vết**, không đi theo đường bỏ dòng chuyến.

Bỏ dòng có chứng từ phải **lưu vết**: ai bỏ, lúc nào, dòng nào, số tiền bao nhiêu. Tiền biến khỏi màn hình nhưng không được biến khỏi lịch sử.

## 4. Hệ quả của quyết định 3 và 6 — thành tiền

- Ba dòng mẫu đưa về **đơn giá 40.000.000 / 30.000.000 / 20.000.000**, ba ô phí để trống. Trùng số trong brief §6.
- Bảng tính nguồn **đã có sẵn cột Thành tiền** và người nhập vẫn dán đủ 11 cột. Số dán vào **vẫn nhận, nhưng chỉ dùng để đối chiếu**: lệch với số tự cộng thì báo "lệch X, kiểm lại", **không tự sửa và không tự bỏ dòng**.
- Ô phí trống hiện `—`, không bao giờ hiện `0` (brief quy tắc 2 vẫn giữ nguyên ở phần trình bày).

## 5. Hệ quả của quyết định 8 — số âm

Brief quy tắc 4 trước đây ghi *"không số nào được âm"*. Quyết định này **không bãi bỏ** câu đó, mà tách làm hai loại:

- **Âm giả — vẫn cấm tuyệt đối.** Do phân bổ sai thứ tự, trừ nhầm kỳ, hoặc cộng nhầm phần chưa chốt vào phần đã chốt. Đây là lỗi bản dựng cũ từng mắc.
- **Âm thật — được phép, phải nói rõ.** Khách trả nhiều hơn toàn bộ nợ. Hiện số âm kèm chữ **"khách trả dư · phải trả lại"**, không để số âm trần.

ĐÃ SỬA trong [brief](ux-brief-so-cong-no.md) §5: quy tắc 4 bỏ câu "không số nào được âm", thêm quy tắc 4b tách hai loại. Sổ quyết định [`docs/decisions.md`](../docs/decisions.md) có dòng `V5-UX` trỏ về đây.

Hai bản đề xuất cũ vẫn giữ câu cũ và **không** được dùng làm nguồn cho phần này: [v4](ux-v4-so-khach.md) ("không số nào được âm", trả dư chưa chốt chính sách) và [v3](ux-v3-so-cong-no.md) (bắt chọn kỳ ghi âm khi trả dư). Chúng là hồ sơ lịch sử.

## 6. Mockup phải sửa gì

1. Khoản thu hiện như của **sổ**; dòng chuyến chỉ còn nhãn "ghi tại dòng DEMO-105". Bỏ chữ "gắn với chuyến này" ở khung 09.
2. Khung 09 đổi từ **chặn** sang **xác nhận bỏ dòng**: nói rõ bỏ luôn chứng từ 5.000.000 chưa xác nhận, không đổi số dư, có lưu vết. Thêm một câu cho biết khoản thu **đã xác nhận** thì không đi đường này.
3. Đơn giá về 40 / 30 / 20, phí để trống; bung chi tiết thì hiện rõ **thành tiền = đơn giá + 3 phí**.
4. Khung 03 ghi rõ cột Thành tiền dán vào chỉ dùng để đối chiếu.
5. Khung 07 thêm một câu: chốt xong, chứng từ 5.000.000 vẫn treo, vẫn chưa vào số dư.
6. Thêm khung **khách trả dư**: số âm kèm chữ "phải trả lại".
7. Ba điểm nhỏ còn lại từ vòng check: cột Đã thu của DEMO-103 đang hiện `—` trong khi dòng đó có chứng từ 5.000.000; mất dấu "phủ ba chuyến" sau khi lưu khoản thu (khung 05); sidebar khung 05 thiếu "1 dòng thiếu giá" trong khi bảng vẫn còn dòng đó.

## 7. Còn mở

1. **Thứ tự 11 cột thật** trong bảng tính — phải mở bảng tính đối chiếu một lần, chưa làm.
2. **Ai được xác nhận chứng từ và căn cứ gì** — hoãn theo quyết định 4; xem [Q09](p0-write-path/decisions-needed.md).
3. **Tiền dư có dùng được cho sổ khác của cùng khách không** — đang mặc định là không.
4. **Sổ "chưa mở" có tính là "chưa chốt" không** — mockup khung 08 đang tự quyết là không.
5. Mục 7 của brief còn lại giữ nguyên, chưa chốt hộ.

## 8. Hoàn tác

Tài liệu mới, chưa sửa code hay dữ liệu. Bỏ bằng cách xoá file này.
