# UX bước 03: luồng thao tác, trạng thái và chỗ máy chặn sai (1/11/2026)

Trạng thái: **ĐỀ XUẤT** (Claude). Bước 03 trong thứ tự của [`UX-NEN-01`](decisions/ux-nen-01.md), dựng trên [`HANG-CHO-01`](decisions/hang-cho-01.md) (Q1–Q3 đã chốt) và [bước 02](ux-luong-du-lieu.md).

Tài liệu này mô tả **việc gì xảy ra, theo thứ tự nào, người thấy gì, máy chặn sai ở đâu**, ở từng trạng thái. Chưa có bố cục hay màu: đó là bước 04. Thước đo vẫn là M1–M5 (độ đúng của dữ liệu vào).

## 1. Ba luồng

| Luồng | Ai | Câu hỏi họ mang tới | Hôm nay | Sau |
| --- | --- | --- | --- | --- |
| **L1 · Xử lý ngoại lệ cuối ngày** | Người nhập | "Hôm nay còn gì máy không tự làm được, đụng tiền bao nhiêu?" | Mở từng sổ (32 sổ có chuyến chờ, 72 sổ có lệch), tìm nút ở mỗi sổ | Một trang: hộp ngoại lệ của cả công ty, xếp theo tiền |
| **L2 · Soát việc máy đã làm** | Người nhập | "Máy vừa tự ghi gì vào sổ, có gì sai không?" | Không có (máy chưa tự làm gì) | Một danh sách "Máy đã tự làm hôm nay" ngay đầu hộp ngoại lệ, mỗi dòng có đường sửa |
| **L3 · Đọc số tin được** | Sếp, người đòi nợ | "Khách này nợ bao nhiêu, có đúng tới hôm nay không?" | Số không nói tính tới bao giờ; sổ đang chậm khoảng 11 ngày mà không ai biết | Mỗi số có "tính tới …"; khách còn việc chờ đụng tiền thì có cảnh báo; tin nhắc nợ hỏi lại trước khi copy số có thể sai |

## 2. L1 · Hộp ngoại lệ (người nhập, cuối ngày)

### 2.1 Các bước

1. Mở "Việc cần làm". Trang này **đổi thành hộp ngoại lệ**; ba nhóm cũ (thiếu giá, chờ kiểm, sổ dư) gộp vào đây.
2. Đầu trang có ba thứ:
   - **độ tươi:** "Sheet lấy lúc 14:15 · lần tới 14:30" và nút "Lấy lại ngay";
   - **tổng việc:** "Còn 12 việc, đụng 380 triệu";
   - **dòng "Máy đã tự làm hôm nay"** (L2).
3. Bên dưới là danh sách việc, **xếp theo số tiền bị ảnh hưởng**, chia nhóm theo loại hành động (mục 2.2). Mỗi dòng có: khách (sổ), việc gì nói bằng câu, số tiền, **một hành động chính**.
4. Làm từng dòng tại chỗ. Việc cần nhìn cả sổ thì có nút "Mở trong sổ", mở đúng sổ, đúng tháng, tô đúng dòng, và có đường quay về hộp.
5. Hộp trống: "Hôm nay không còn việc. Sheet lấy lúc 14:15." Xong ngày.

So với hôm nay: từ "mở 32–72 sổ, tìm nút ở từng sổ" thành **một trang**. Số bước cho mỗi việc là 1 bấm (ghi) hoặc 2 bấm (mở sổ rồi sửa).

### 2.2 Các loại việc trong hộp (sau khi máy làm theo Q1, Q2)

| Nhóm | Ví dụ | Hành động chính | Máy chặn sai thế nào |
| --- | --- | --- | --- |
| **Phiếu thu từ Sheet** (Q3) | "KHÁCH A · thu 50.000.000 ngày 30/10 · trừ vào nợ T8" | Chọn nhiều phiếu → "Ghi n phiếu (tổng …)" | Xem lại trước khi ghi: tổng nợ trước → sau của từng khách, tháng đang khóa, khách sẽ dư (như H5 của [`SO-GON-04`](decisions/so-gon-04.md)). Phiếu nghi trùng (cùng khách, cùng số tiền, cách ≤ 3 ngày với phiếu đã có) thì tách riêng, phải bấm từng phiếu (M4). |
| **Chuyến cần người quyết** | đã có ở sổ khác; container trùng ngày lệch xa; không có ở sổ nào; khách nhiều sổ chưa rõ mặt hàng; tháng khóa | Theo lý do: "Đúng là chuyến mới → vào sổ …", "Bỏ qua dòng này", "Mở trong sổ" | Nút ghi chỉ hiện khi lý do cho phép. "Đã có ở sổ khác" không có nút vào sổ; chỉ có "Mở sổ kia" và "Báo sai Sheet". Mọi lệnh vẫn qua `paste_trips` với lớp chặn trùng ở DB. |
| **Chuyến chưa có giá** | chuyến đã vào sổ, chưa có đơn giá (không cộng nợ) | "Ghi giá từ Sheet" khi hàng chờ giá có giá khớp; nếu không thì "Mở trong sổ" | Giá chỉ lấy từ dòng Sheet khớp duy nhất (luật [hàng chờ giá](../specs/v7-price-queue.md)). Ô trống không thành 0. |
| **Lệch cần người quyết** (phần Q1 không tự làm) | đổi ngày sang tháng khác, đổi container hoặc booking, đổi tuyến làm đổi giá | "Lấy theo Sheet" / "Giữ web" | Đổi ngày sang tháng khóa thì báo trước "Tháng 8 đang khóa: sửa sẽ thành dòng điều chỉnh". |
| **Phụ phí PS cần xem** | tổng PS khác tổng phụ phí web, PS ghi sai | "Mở trong sổ" | Như hiện nay: tách phụ phí không đổi tổng tiền. |
| **Sổ cần chú ý** | sổ dư, chờ kiểm | "Mở trong sổ" | Như hiện nay. |

### 2.3 Trạng thái của trang

| Trạng thái | Người thấy gì | Làm gì được |
| --- | --- | --- |
| Đang tải | "Đang tính việc của 236 sổ…" trong khung danh sách; đầu trang vẫn hiện độ tươi | Chờ; không có nút ghi |
| Trống | "Hôm nay không còn việc. Sheet lấy lúc …" | Không gì |
| Sheet cũ (bản chụp > 30 phút hoặc runner lỗi) | Băng vàng: "Chưa lấy được Sheet từ 13:00. Việc dưới đây có thể thiếu." | "Lấy lại ngay"; vẫn làm được các việc đang hiện |
| Lỗi tải | "Không tải được việc. Kiểm tra mạng rồi bấm Thử lại." (không hiện chữ tiếng Anh của trình duyệt) | "Thử lại" |
| Đang ghi | Dòng đang ghi mờ đi, nút đổi thành "Đang ghi…" | Không bấm lại được (chặn ghi hai lần) |
| Ghi xong | Dòng biến khỏi danh sách; băng: "Đã ghi 3 phiếu, tổng 120.000.000 đ" kèm "Hủy phiếu vừa ghi" (H3) | Hủy từng phiếu, có lý do điền sẵn |
| Ghi một phần | "Ghi được 2/3 phiếu. 1 phiếu không ghi: tháng 8 đang khóa." Dòng lỗi ở lại, lý do ngay tại dòng | Sửa rồi ghi lại dòng đó |
| Sổ vừa đổi (`STALE_LEDGER`) | "Sổ KHÁCH A vừa thay đổi; đã tải lại dòng này." Dòng tự tính lại | Ghi lại nếu vẫn đúng |
| Bị chặn (tháng khóa) | Ngay dòng: "Tháng 8 đang khóa. Muốn ghi phải mở khóa (có hỏi lại)" | "Mở trong sổ" để mở khóa |
| Chưa rõ lệnh đã lưu (mất mạng khi ghi) | "Chưa rõ đã ghi chưa." + "Kiểm tra lại" (gửi lại cùng mã idempotency, không ghi hai lần) | Kiểm tra lại |

## 3. L2 · Máy đã tự làm hôm nay

Dòng gọn ở đầu hộp ngoại lệ: "Máy đã tự làm hôm nay: 31 chuyến vào sổ · 120 chỗ sửa chữ theo Sheet · [Xem]". Bấm Xem thì mở danh sách theo sổ.

| Việc máy làm | Mỗi dòng ghi | Đường sửa |
| --- | --- | --- |
| Chuyến tự vào sổ (Q2) | sổ, container, ngày, tuyến, đơn giá, thành tiền | "Xóa chuyến này" (lệnh xóa đang có, ghi Lịch sử, tháng mở) |
| Sửa chữ theo Sheet (Q1) | sổ, container, cột, trước → sau | "Trả lại giá trị cũ" (lệnh sửa ô đang có) |

Người làm trong Lịch sử của sổ là "Máy (theo Sheet)". Không có chữ kỹ thuật. Dòng máy làm được ghi như mọi thao tác khác: người làm, trước → sau.

Máy **không** làm khi thiếu một điều kiện. Dòng đó vào hộp ngoại lệ kèm lý do, nên không có việc nào biến mất lặng lẽ.

## 4. L3 · Đọc số tin được (Tổng quan, trang khách, Đòi nợ)

1. **Độ tươi ở mọi số tiền.** Đầu Tổng quan và trang khách có: "Số tính tới 14:15 hôm nay (Sheet lấy lúc 14:15)". Khi bản chụp cũ hơn 30 phút hoặc runner lỗi, dòng này đổi màu kèm chữ "có thể cũ".
2. **Cảnh báo theo khách.** Khách còn việc chờ đụng tiền (phiếu thu chưa ghi, chuyến chưa vào sổ, chuyến chưa có giá) thì có nhãn chữ cạnh số nợ: "còn 1 phiếu thu chưa ghi (50 triệu)". Bấm vào thì đến đúng dòng trong hộp ngoại lệ.
3. **Tin nhắc nợ hỏi lại trước khi copy số có thể sai.** Ở Đòi nợ, bấm "Copy tin nhắc" cho khách còn phiếu thu chờ thì hỏi: "Khách còn 1 phiếu thu 50.000.000 đ trên Sheet chưa ghi vào web. Tin nhắc sẽ ghi nợ cao hơn thực tế." Hai nút: **"Ghi phiếu trước"** (nút chính, mở đúng dòng) và "Vẫn copy". Hỏi, không cấm, vì người đòi nợ có thể biết điều mình không biết.

Trạng thái: khi chưa tính được việc chờ (job lỗi), nhãn ghi "chưa kiểm được việc chờ", không giả là không có việc.

## 5. Đối chiếu dữ liệu: có sẵn và cần thêm

| Cần | Hôm nay có ở đâu | Phải thêm |
| --- | --- | --- |
| Việc chờ từng sổ (chuyến, lệch, giá, phiếu thu, PS) | `GET /api/v7/ledger` → `sheet_sync`, `sheet_prices`, `sheet_receipts`, `ps_fees` (tính khi mở sổ) | **Job gom việc**: chiếu cả 236 sổ sau mỗi lượt chụp Sheet. Đo 1/11/2026: khoảng 0,75 giây/sổ, cả 236 sổ khoảng 3 phút, nên không tính lúc mở trang. Job ghi một file `inbox.json`; endpoint `GET /api/v7/inbox` chỉ đọc file đó. |
| Ghi phiếu thu, giá, chuyến, giải quyết lệch | `/api/v7/sheet/receipts`, `/sheet/prices`, `/sheet/approve`, `/sheet/resolve` (từng sổ) | Hộp gọi lần lượt từng sổ, giữ mã idempotency từng sổ. Không cần lệnh ghi mới. |
| Độ tươi | `v7_sheet_refresh` (giờ của bản chụp và tín hiệu "Làm mới") | Đưa vào `inbox.json` và đầu Tổng quan |
| Máy tự làm (Q1, Q2) | Chưa có | Bước chạy sau job gom việc, cùng tài khoản máy riêng (người làm "Máy (theo Sheet)"), gọi đúng lệnh ghi có sẵn. Có công tắc bật/tắt trên `hao`. |
| Cảnh báo theo khách ở Tổng quan/Đòi nợ | Chưa có | Đọc số việc chờ theo khách từ `inbox.json` |
| Gán sổ theo mặt hàng (Q4) | Runner đọc cột **"Mặt hàng"** của booking sheet (`webdebit_export_connector.py`), mỗi sổ có `commodity_id` (223/236 sổ đã gắn) | Gán dòng booking vào sổ theo cặp (tên khách, mặt hàng) khi khách có nhiều sổ |

## 6. Đo thế nào là xong

| Chỉ số | Đo bằng | Mức đạt |
| --- | --- | --- |
| Số trang phải mở cuối ngày | đếm | 1 (hôm nay: tới 72 sổ) |
| Độ tươi M5 | giờ bản chụp và giờ việc cuối được xử lý | ≤ 1 ngày |
| Việc treo quá 1 ngày | `inbox.json` | 0 việc đụng tiền treo quá 1 ngày |
| Trùng/sót M2 | phép đối chiếu booking sheet ↔ chuyến | 0 |
| Phiếu hủy vì nhầm M4 | event `void` có lý do "Ghi nhầm" | 0 |
| Người nhập tự làm L1 không cần hướng dẫn | bước 05, quan sát | xong cả ngày ≤ 15 phút |

## 7. Giai đoạn

1. **P1 · Hộp chỉ đọc + độ tươi.** Job gom việc, `GET /api/v7/inbox`, trang hộp ngoại lệ với nút "Mở trong sổ", độ tươi trên Tổng quan. Không đổi đường ghi. Làm được ngay.
2. **P2 · Ghi tại hộp (Q3).** Ghi phiếu thu, giá, giải quyết lệch ngay ở hộp; ghi một phần; cảnh báo ở Đòi nợ.
3. **P3 · Máy tự làm (Q1, Q2).** Bật từng luật bằng công tắc, có danh sách "Máy đã tự làm" (L2). Q2 chỉ bật cho khách nhiều sổ sau khi có Q4.
4. **Bước 04 (giao diện)** đi cùng P1: bản bấm thử hộp ngoại lệ ở khung 1280×560, dữ liệu giả lấy theo số đo thật.

## 8. Câu hỏi cần người dùng trả lời

- **Q4 (xác nhận):** cột "Mặt hàng" của booking sheet có ghi đúng tên mặt hàng như sổ không (sầu riêng, chuối, thanh long, dừa…)? Nếu đúng thì dòng booking của khách nhiều sổ vào sổ theo (tên khách, mặt hàng). Đây là gốc của 241 dòng rơi nhầm sổ.
- **Q5 (mới):** chỉ 1/236 sổ có bảng giá, nên điều kiện (c) của Q2 làm máy hầu như không tự đưa chuyến nào vào sổ. Có hai cách:
  - **(A, Claude đề xuất)** chuyến đủ điều kiện (a)(b)(d)(e) tự vào sổ dù chưa có giá. Chuyến hiện "chưa có giá", **không cộng vào nợ** cho tới khi có giá; giá vào sau qua hàng chờ giá. Danh sách chuyến luôn đủ và tươi (M2, M5), số nợ chỉ đổi khi có giá có nguồn (M3).
  - **(B)** giữ điều kiện giá, dựng bảng giá cho các sổ trước. Đây là việc cấu hình lớn; trong lúc đó mỗi ngày vẫn có 35–40 chuyến chờ người.
