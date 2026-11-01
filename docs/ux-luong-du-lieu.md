# UX bước 02: đường đi của dữ liệu và các màn (1/11/2026)

Trạng thái: **ĐỀ XUẤT** (Claude). Phần số đo **ĐÃ KIỂM CHỨNG** trên `hao` ngày 1/11/2026. Bước 02 trong thứ tự của [`UX-NEN-01`](decisions/ux-nen-01.md), nối tiếp [Nền UX](ux-nen-nguoi-dung.md). Thước đo là năm chỉ số M1–M5 (độ đúng của dữ liệu vào). Chưa có thiết kế màn ở đây: tài liệu vẽ dữ liệu đi qua những chặng nào, máy kiểm gì, người phải làm gì, rồi mới xét màn nào cần.

## 1. Cách đo

- Script chỉ đọc chạy trên `hao`. Nó dùng đúng hàm chiếu hàng chờ của API (`ledger_projections` trong `web/v7_api_sheet.py`) cho cả 236 sổ, như khi người dùng mở từng sổ.
- Mọi lệnh DB chạy với `default_transaction_read_only=on`; script không gọi hàm ghi nào. Chỉ in số tổng hợp.
- Bản chụp Sheet và PS được runner trên `hao` lấy lại **15 phút một lần** (ba timer `webdebit-sheet-sync`, `webdebit-sheet-prices`, `webdebit-ps-snapshot`). Lần đo này dùng bản chụp lúc 06:00 UTC ngày 1/11.

## 2. Đường đi hôm nay

```
Booking sheet / Sheet công nợ / Bộ lập bill (PS)
        │  máy: runner chụp lại mỗi 15 phút            ← chặng này đã tự động
        ▼
Bốn hàng chờ, tính riêng cho TỪNG sổ khi mở sổ
        │  người: mở từng sổ, bấm Duyệt / Ghi / Tách / chọn "theo Sheet"
        ▼
Sổ web (chuyến, giá, phụ phí, phiếu thu) → nợ
        │  máy: tính nợ, phân bổ
        ▼
Người xem: Tổng quan, Công nợ theo tháng, Đòi nợ (tin nhắc)
```

Chặng lấy dữ liệu đã tự động và tươi. **Dữ liệu dừng lại ở chặng thứ hai**, vì mỗi dòng phải có người mở đúng sổ rồi bấm, mà hôm nay không ai làm (Nền UX mục 3). Đây là lý do của M5 "chậm khoảng 11 ngày".

## 3. Số đo từng hàng chờ, cả 236 sổ

| Hàng chờ | Số dòng | Ở bao nhiêu sổ | Có đụng tiền không |
| --- | ---: | ---: | --- |
| Chuyến mới (NEW) | 341 | 32 | Có: duyệt là cộng nợ |
| Lệch Sheet ↔ web (CONFLICT) | 975 | 72 | Phần lớn không (xem dưới) |
| Giá từ Sheet | 0 sẵn sàng, 45 cần xem | 10 | Có |
| Chuyến trên web chưa có giá | 22 | 4 | Có: chưa vào tổng nợ |
| Phụ phí PS | 0 sẵn sàng, 102 cần xem | 25 | Có |
| Phiếu thu từ Sheet | 6 sẵn sàng, 7 cần xem | 12 | Có |

Lý do "cần xem" gộp của ba hàng giá, phiếu thu, PS:
- WEB_NO_FEE 62
- AMBIGUOUS 41
- TOTAL_DIFF 16
- PS_BAD_AMOUNT 8
- MONTH_LOCKED 7
- PS_COMBINED 7
- CONFLICT 5
- NO_DATE 4
- SHEET_EDITED 3
- PS_TYPO 1

### 3.1 Lệch Sheet ↔ web: 975 dòng, gần như toàn chữ mô tả

- **951 dòng khác ở chữ:** nơi đi 550, nơi đến 537, shipper 241, ngày 7 (một dòng có thể khác nhiều cột).
- **24 dòng thật sự đáng lo cho M2:** 20 dòng container trùng hoặc đổi số, 3 dòng container đang thuộc sổ khách khác, 1 dòng khớp mơ hồ.
- Lịch sử người làm (Nền UX mục 3): 63 trên 69 lần chọn "theo Sheet".

Nơi đi và nơi đến có thể ảnh hưởng giá vì bảng giá tính theo tuyến. Vì vậy "chỉ là chữ" chỉ đúng khi đổi tuyến không làm đổi giá.

### 3.2 Chuyến mới: 341 dòng

- Theo tháng: tháng 10–11 có 107 dòng, là chuyến mới thật sau mốc nạp. Tháng 1–9 có **234 dòng**.
- Trong 234 dòng tháng 1–9, **226 container đã có trong bản đối chiếu lúc nạp 21/10** (`baseline-refs.json`, 9.935 dòng), chỉ 8 container không có.
- Hàng chờ coi các dòng này là "mới" vì sổ web của khách đó không có dòng nào cùng container. Code ghi rõ bản đối chiếu lúc nạp chỉ để truy nguồn, không chặn dòng (`v7_sheet_queue.py`, `build_queue`).
### 3.3 Kết quả kiểm 234 dòng tháng 1–9 (ĐÃ KIỂM CHỨNG 1/11/2026, chỉ đọc)

**Cách kiểm:** đối chiếu từng container với dòng sổ gốc còn hiệu lực của **mọi** sổ. "Còn hiệu lực" nghĩa là lấy bản sửa mới nhất trong `legacy_trip_rev` (nếu có) và bỏ dòng đã xóa. Đối chiếu thêm với chuyến trên web, rồi đọc hàm ghi `sokhach.paste_trips`, là hàm mà nút "Duyệt n chuyến mới" gọi.

**Kết quả:** cả 226 container đều đang nằm trong sổ gốc của **một sổ khác**, chưa bị xóa.

| Nhóm | Dòng | Tiền ở sổ kia | Nếu bấm Duyệt hôm nay |
| --- | ---: | ---: | --- |
| Cùng container, lệch ngày ≤ 3 | 170 | 4,39 tỷ | DB **chặn được**: dòng vào trạng thái *chờ kiểm* (lý do `BASELINE_DATE_WINDOW`), không cộng nợ. Rủi ro dời sang bước kết luận chờ kiểm: người chọn "Đúng" thì thành tính trùng. |
| Dòng ở sổ kia **không có ngày** | 49 | 0,15 tỷ | DB **không chặn**: luật chặn so ngày, ngày trống thì không khớp. Chuyến vào sổ và cộng nợ; nhiều khả năng là tính trùng. |
| Lệch ngày > 3 (tới 365 ngày) | 7 | 0,29 tỷ | DB không chặn. Có thể là container dùng lại cho chuyến khác (đúng), có thể là cùng chuyến ghi sai ngày (trùng). Cần người xem. |
| Không có ở sổ nào | 8 | — | Chuyến thật sự mới, hoặc số container gõ khác nhau giữa booking sheet và Sheet công nợ. Nếu là chuyến chưa từng tính tiền thì đây là chỗ sót. Cần người xem. |

**Nguyên nhân chính: sổ tách theo mặt hàng.** 202 trong 226 dòng thuộc cùng một cặp sổ, là hai sổ của *cùng một khách*: sổ chính và sổ "– DỪA". Các cặp khác phần lớn cũng là cùng khách khác mặt hàng ("-SR", "– DỪA"). Chỉ một cặp 4 dòng có tên khác hẳn nhau, có thể là bí danh khách. Theo [`V7-MH`](decisions/v7-mh.md) và [`MH-01`](decisions/mh-01.md), mỗi sổ là một mặt hàng. Hàng chờ thì gán dòng booking theo **tên khách** nên rơi vào sổ chính. Sau đó nó chỉ so container trong sổ đó và với chuyến *web* của sổ khác, không so với sổ gốc của sổ khác (`project_customer` trong `v7_sheet_queue.py`; `list_sheet_trip_refs` chỉ trả chuyến web).

**Kết luận cho M2:**
- Đo hôm nay: **56 dòng (0,44 tỷ) có thể cộng nợ hai lần** nếu có người bấm Duyệt.
- 170 dòng nữa hiện sai là "chuyến mới" và sẽ thành việc chờ kiểm thừa.
- Chưa ai bấm, nên chưa có thiệt hại.

## 4. Điều rút ra về cấu trúc

1. **Web đang được dựng như một sổ thứ hai phải chép tay từ Sheet.** Có bốn hàng chờ, mỗi hàng nằm trong từng sổ, tổng cộng 236 sổ. Không có nơi nào gom việc của cả công ty. Trong lúc song song (Sheet là sổ chính thức), phần lớn thao tác duyệt chỉ là xác nhận điều Sheet đã nói.
2. **Công sức của người đổ vào chỗ không quyết định tiền:** 951 lệch chữ. Còn chỗ quyết định tiền thì bị lẫn trong đó: 24 container đáng ngờ, 56 dòng có thể tính trùng (mục 3.3), 45 giá, 102 phụ phí, 13 phiếu thu.
3. **Người xem đang đọc sổ chưa cập nhật mà không được báo.** Tổng quan và Đòi nợ không nói số tính tới bao giờ, cũng không nói còn bao nhiêu việc chờ có thể làm đổi số của khách đang xem.

## 5. Nguyên tắc cấu trúc đề xuất: chia theo "ai phải quyết"

| Loại | Ví dụ hôm nay | Đề xuất |
| --- | --- | --- |
| **Máy tự làm** (đã có luật, không đổi tiền) | 951 lệch chữ mô tả mà giá không đổi | Tự lấy theo Sheet trong lúc song song, ghi Lịch sử, người không phải bấm. **Cần người dùng chốt (Q1).** |
| **Máy tự làm có điều kiện** (đổi tiền nhưng luật rõ) | Chuyến mới khớp đúng một khách, container không có ở đâu khác, giá tính được từ bảng giá, tháng đang mở | Tự vào sổ, ghi Lịch sử, báo trong danh sách "đã tự vào hôm nay". **Cần người dùng chốt (Q2):** đổi cổng duyệt chuyến mới. |
| **Người quyết** (ngoại lệ) | Container trùng hoặc thuộc khách khác, 226 dòng booking đã có ở sổ khác, giá không tính được hoặc lệch bảng giá, PS lệch tổng, phiếu thu không rõ ngày | Gom vào **một hộp ngoại lệ của cả công ty**, xếp theo số tiền bị ảnh hưởng, mỗi dòng có một hành động. |
| **Người xác nhận** (tiền vào) | Phiếu thu từ Sheet sẵn sàng | Vẫn để người bấm (M4), nhưng làm ở hộp chung, không phải mở từng sổ. **Q3.** |
| **Người xem** | Sếp, người đòi nợ | Mỗi số có "tính tới lúc …" và cảnh báo khi khách đó còn việc chờ đụng tiền. |

## 6. Từng màn: giữ, gộp hay bỏ (ĐỀ XUẤT)

| Màn | Ai dùng | Việc | Đề xuất |
| --- | --- | --- | --- |
| **Việc cần làm** | Người nhập | Hôm nay: chỉ thiếu giá, chờ kiểm, sổ dư | **Đổi thành hộp ngoại lệ chung**, nơi làm việc chính của người nhập: bốn hàng chờ của cả 236 sổ, xếp theo tiền. Việc lớn nhất của bước 03. |
| **Sổ khách (thẻ Sổ)** | Người nhập, người tra cứu | Hôm nay: nơi duyệt từng sổ và soi chi tiết | **Giữ, đổi vai:** nơi tra cứu và sửa một ngoại lệ, không phải nơi duyệt hàng loạt. Bố cục (bản thử "một tháng") để tới bước 04. |
| **Tổng quan** | Sếp | Tổng nợ, khách lớn, quá hạn | **Giữ**, thêm độ tươi và cảnh báo việc chờ. |
| **Đòi nợ** | Người đòi nợ | Ai cần nhắc, copy tin nhắc | **Giữ**, chặn hoặc cảnh báo tin nhắc khi khách còn phiếu thu chờ duyệt (tránh nhắc theo số cũ). |
| **Chat Zalo** | Người đòi nợ | Đọc hội thoại | **Gộp** vào thẻ Trao đổi của trang khách; hai chỗ đang cùng một việc. |
| **Công nợ theo tháng** | Sếp? | Ma trận khách × tháng | **Chưa quyết:** không có nhật ký xem để biết ai dùng. Hỏi sếp; nếu Tổng quan đã trả lời đủ "ai nợ, nợ từ bao giờ" thì gộp. |
| **Trang khách: Tình hình, Hồ sơ** | Sếp, người đòi nợ | Bức tranh một khách | Giữ, xét lại ở bước 03 khi vẽ luồng của sếp. |

## 7. Câu hỏi cần người dùng chốt

- **Q1:** Trong lúc song song, khi Sheet đổi nơi đi, nơi đến hoặc shipper mà giá không đổi, web có tự lấy theo Sheet (ghi Lịch sử, không hỏi) không? *Claude đề xuất: có.*
- **Q2:** Chuyến mới có được tự vào sổ khi đủ bốn điều kiện: khớp đúng một khách, container chưa có ở đâu (kể cả bản đối chiếu lúc nạp), giá tính được từ bảng giá, tháng đang mở? Đây là đổi cổng duyệt chuyến mới đang có. *Claude đề xuất: có, kèm danh sách "đã tự vào hôm nay" để người nhập soát.*
- **Q3:** Phiếu thu từ Sheet vẫn để người bấm xác nhận, nhưng ở hộp chung? *Claude đề xuất: có. Tiền vào là chỗ M4, giữ người.*
- **Q4:** Với khách có nhiều sổ theo mặt hàng, làm sao biết một dòng booking thuộc sổ nào? Booking sheet có cột mặt hàng (như LOAI HANG của TONG theo `MH-01`) không?

## 8. Chặn tính trùng ở hàng chờ chuyến mới (từ kết quả mục 3.3)

Việc 1 và 2 **ĐÃ TRIỂN KHAI** trên `hao` 1/11/2026 (PR FinanceBullkk/webdebit#240, [nhật ký](deploys/2026-11-01-chan-trung-hang-cho.md)). Đo lại sau triển khai: "chuyến mới" chờ duyệt từ 341 còn 100; 241 dòng hiện "đã có ở sổ gốc của sổ khác". Việc 3 còn chờ Q4.

1. **Hàng chờ:** trước khi gọi một dòng là "mới", so container với sổ gốc còn hiệu lực và chuyến web của **mọi** sổ.
   - Có ở sổ khác thì hiện "Đã có ở sổ …, ngày …", không có nút Duyệt, đưa vào hộp ngoại lệ.
   - Chỉ đổi phần chiếu (Python), không đổi DB.
2. **Lớp chặn ở DB:** `paste_trips` coi thêm dòng sổ gốc **không có ngày**, cùng container, là khớp với bản đối chiếu lúc nạp, để dòng vào *chờ kiểm* thay vì vào sổ thẳng.
   - Đây là migration SQL. Theo `DEPLOY-CLAUDE-01`, Claude tự làm được nhưng vẫn phải qua harness PostgreSQL.
3. **Gán sổ theo mặt hàng:** dòng booking của khách có nhiều sổ phải vào đúng sổ mặt hàng. Cần người dùng cho biết booking sheet có cột nào nói mặt hàng (dừa, sầu riêng, chuối…). Nếu không có thì quy tắc là gì. **Q4.**

Hai việc đầu không đổi quy tắc tiền, chỉ làm cho luật "mỗi container một chuyến" ([`DUP-01`](decisions/dup-01.md)) được áp ở cả hàng chờ. Việc 3 cần người dùng trả lời.

## 9. Bước tiếp (bước 03)

Vẽ luồng cho hai việc chính, đủ các trạng thái (đang tải, trống, lỗi, thành công, bị chặn, đã tự làm):
- người nhập xử lý hộp ngoại lệ cuối ngày;
- sếp hoặc người đòi nợ xem nợ có độ tươi.

Kèm số bước và chỗ máy chặn sai.
