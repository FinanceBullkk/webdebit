# V7: đối chiếu phí Bảo hiểm với giấy chứng nhận trong group Zalo

Trạng thái: **ĐỀ XUẤT** (Claude, 19/11/2026), chưa code, chưa đụng `hao`. Quyết định đi kèm: [`BAO-HIEM-ZALO-01`](../docs/decisions/bao-hiem-zalo-01.md); các câu Q1–Q4 ở cuối cần người dùng chọn trước khi code.

<!-- du-lieu-gia: MAUU1234567 -->

## Vì sao không "tự điền" tiền

Người dùng hỏi (chat 19/11/2026) web đã tự điền phí bảo hiểm từ giấy chứng nhận trong group Zalo chưa. Câu trả lời của spec này là **web không cộng tiền theo giấy**, giống cách web xử lý bảng PS. Có ba lý do, đều từ quyết định đã chốt:

- [`SONG-SONG-01`](../docs/decisions/song-song-01.md) và [`CHUYEN-HAN-01`](../docs/decisions/chuyen-han-01.md): Sheet vẫn là sổ chính thức; người nhập vẫn ghi Sheet.
- [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md): máy đưa tổng từng khách trên web về đúng tổng Sheet mỗi giờ. Một khoản web tự cộng mà Sheet không có sẽ thành lệch, hoặc thành "web đi trước" mà không ai giải thích.
- [`MAY-PS-01`](../docs/decisions/may-ps-01.md): "PS có tiền mà web chưa có" là câu hỏi có thu thêm hay không, nên để người xem. Giấy chứng nhận cũng là một nguồn phụ như PS.

Giấy chứng nhận vẫn có ích theo ba cách, không đổi tổng tiền:

1. **Nhắc:** chuyến có giấy mà Sheet/web chưa có phí bảo hiểm thì hiện "cần ghi Bảo hiểm vào Sheet".
2. **Phân loại:** chuyến có đúng một khoản chưa phân loại bằng đúng số trên giấy thì đổi loại khoản đó thành Bảo hiểm, tổng giữ nguyên.
3. **Chứng cứ:** khoản Bảo hiểm khớp giấy được gắn số giấy, bấm vào thì mở giấy.

Khi chuyển hẳn khỏi Sheet, câu "web tự ghi tiền theo giấy" sẽ được xét lại trong một quyết định riêng ([Q4](#câu-hỏi-mở)).

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (màn 1280×720) và chủ sổ. Người nhập ghi Sheet hằng ngày; chủ sổ xem Việc cần làm. Mỗi lần ghi mang tên người bấm hoặc "Máy (theo Sheet)" ([`V7-ID`](../docs/decisions/v7-id.md)).

**Bối cảnh:** công ty bảo hiểm gửi giấy chứng nhận bảo hiểm hàng xuất (PDF, phần lớn là bản scan) vào một group Zalo. Mỗi giấy ghi số giấy, container, số vận đơn, ngày tàu chạy, phí, VAT và tổng có VAT. Người dùng chốt ngày 19/11/2026 rằng số thu khách là **tổng có VAT**, không cộng thêm. Hiện người nhập phải mở từng PDF và gõ tay vào cột `BẢO HIỂM` của tab khách.

**Luồng:**

1. Ở máy có Zalo, job `insurance_sync.py` của dự án `zalo-audit-viewer` đã chạy 15 phút một lần (đọc group, tải PDF, OCR, kiểm phép cộng) và ghi `insurance-snapshot.json`. Spec này thêm một bước đẩy bản gọn của file đó lên `hao` (mục [Nguồn](#nguồn-và-đường-đẩy-lên-hao)).
2. Mở sổ khách. Đầu sổ, cạnh "PS cần xem", có **"Bảo hiểm cần xem: K"** khi sổ có giấy cần người xem.
3. Bấm vào thì mở danh sách ngay dưới đầu sổ. Mỗi dòng gồm container, booking, số giấy, ngày tàu chạy, "Giấy X · Web Y", lý do, việc cần làm và nút **Mở giấy**.
4. Giấy chưa gắn được vào sổ nào (không có booking, chưa có chuyến) nằm trong tab **Việc cần làm**, nhóm "Giấy bảo hiểm chưa có chuyến".
5. Khoản đổi loại do máy làm vào Lịch sử: "Đổi loại theo giấy bảo hiểm số …: Khác → Bảo hiểm, tổng không đổi".

**Trạng thái của một giấy:**

| Mã | Khi nào | Hiện ở | Ai làm gì |
| --- | --- | --- | --- |
| `DONE` | Chuyến có khoản Bảo hiểm bằng đúng số giấy | Không hiện; khoản có số giấy và nút Mở giấy | — |
| `CLASSIFY` | Chuyến có đúng một khoản Khác/Phụ phí ban đầu bằng đúng số giấy, chưa có khoản Bảo hiểm | Không hiện | Máy đổi loại ([Q2](#câu-hỏi-mở)); tổng không đổi |
| `SHEET_MISSING` | Chuyến tìm được, web không có khoản nào bằng số giấy | Bảo hiểm cần xem | Người nhập ghi số vào cột `BẢO HIỂM` của tab khách; máy đối soát đưa lên, lượt sau thành `CLASSIFY` hoặc `DONE` |
| `AMOUNT_DIFF` | Chuyến đã có khoản Bảo hiểm khác số giấy | Bảo hiểm cần xem | Xem lại Sheet hoặc giấy; không tự sửa |
| `NO_BOOKING` | Giấy không có booking trong tin Zalo | Việc cần làm | Người xem; container và ngày chỉ là gợi ý, không gắn tự động |
| `AMBIGUOUS` | Booking + container khớp hơn một chuyến | Bảo hiểm cần xem của từng sổ | Người xem |
| `NOT_FOUND` | Có booking + container mà chưa có chuyến web nào | Việc cần làm | Thường là chuyến chưa lên Sheet; lượt sau tự xét lại |
| `CERT_REVIEW` | Giấy chưa qua kiểm phép cộng, có nhiều container (số NULL) hoặc có cảnh báo khi đọc | Việc cần làm | Người xem giấy; không dùng số |
| `MONTH_LOCKED` | Như `CLASSIFY` nhưng tháng khóa | Như `CLASSIFY` | Máy mở, ghi, khóa lại như [`MAY-KHOA-01`](../docs/decisions/may-khoa-01.md) ([Q2](#câu-hỏi-mở)) |

**Không bao giờ:** cộng hay trừ tiền, sửa đơn giá, gắn giấy vào chuyến chỉ theo container và ngày, ghi Sheet.

## Đầu ra

Sổ khách và Việc cần làm cho biết chuyến nào có giấy bảo hiểm mà chưa thu, chuyến nào lệch giấy. Khoản Khác bằng đúng số giấy được đổi loại thành Bảo hiểm mà tổng còn nợ không đổi. Mỗi khoản Bảo hiểm khớp giấy mở được giấy gốc.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Nguồn: `insurance-snapshot.json` của `zalo-audit-viewer`** (đo 19/11/2026 ở máy có Zalo; chỉ ghi số đếm, dữ liệu ngoài Git):

- `schema_version` 1, `amount_basis` "certificate total incl. VAT". Mỗi dòng một giấy: `sha256` (của PDF), `cert_no`, `container`, `amount_vnd`, `cert_premium_vnd`, `cert_vat_vnd`, `cert_total_vnd`, `containers_on_cert`, `bl_no`, `vessel`, `depart_date`, `issue_date`, `sent_at`, `status`, `warnings`, `chat_bookings`, `seals`, cùng tên và mã số thuế người mua bảo hiểm và người được bảo hiểm.
- `amount_vnd` chỉ có số khi giấy qua mọi phép kiểm (phí + VAT = tổng, mã container đúng ISO 6346) và có đúng một container. Còn lại là NULL, không phải 0.
- 16 giấy, cả 16 `ok`, mỗi giấy một container; tàu chạy tháng 10 (6 giấy) và 11/2026 (10 giấy). 10 giấy có đúng một booking lấy từ tin điều xe trong Zalo, 6 giấy không có. 3 giấy có cảnh báo khi đọc. Người mua bảo hiểm có 3 tên khác nhau, người được bảo hiểm có 4; 5 giấy hai tên trùng nhau.
- Tổng tiền 16 giấy và từng số không ghi ở đây.

**Có sẵn, dùng lại:**

- Mẫu bản chụp → kế hoạch → cần xem của PS: `web/v7_ps_queue.py` (`load_ps_snapshot`, `pool`, `match`, `project_ps`), bản chụp có `sha256`, thiếu bản chụp thì `{unavailable: true}`.
- Lệnh `rewrite_trip_fees` (đổi các khoản của một chuyến, **tổng phải bằng tổng cũ**, lệch → `FEE_TOTAL_CHANGED`; `expected_line_ids` lệch → `FEE_LINES_CHANGED`). `source` là object tự do ≤ 2.000 ký tự, nên `{kind: 'insurance', cert_no, sha256, snapshot_sha256}` dùng được **không cần sửa SQL**.
- Loại phí "Bảo hiểm" và cột debit note `INSURANCE 保险` đã có ([`COT-PHU-PHI-01`](../docs/decisions/cot-phu-phi-01.md)). Cột `BẢO HIỂM` của tab khách đã vào đúng loại theo [`TACH-PHI-TIEU-DE-01`](../docs/decisions/tach-phi-tieu-de-01.md), nhưng đó là công cụ chạy một lần; phí Sheet mới vẫn có thể vào Khác.
- Đường đẩy dữ liệu từ máy có Zalo lên `hao`: kênh ssh + Task Scheduler của [Group Zalo trên web](v7-zalo-group-web.md) mục G5.
- Mã chuyến = booking + container ([TRIP-KEY](../docs/decisions.md)); container không là khóa duy nhất ([`NEWTRIP-01`](../docs/decisions/newtrip-01.md)).

**Còn thiếu:** bản gọn của snapshot trên `hao`, module ghép `web/v7_insurance_queue.py`, trường mới trong `get_ledger`, nhóm mới trong Việc cần làm, máy đổi loại, route mở PDF.

## Nguồn và đường đẩy lên `hao`

**Bản gọn.** Trên máy có Zalo, một bước mới sau `insurance_sync.py` ghi `insurance-web.json` chỉ gồm các trường ghép và kiểm cần: `cert_no`, `sha256`, `container`, `bookings` (từ `chat_bookings`), `amount_vnd`, `cert_premium_vnd`, `cert_vat_vnd`, `cert_total_vnd`, `containers_on_cert`, `depart_date`, `issue_date`, `status`, `warnings`. **Không** gửi tên, mã số thuế, số vận đơn hay tin nhắn ([Q1](#câu-hỏi-mở) có thể đổi điều này). File có `created_at`, `sha256` tính trên các dòng, `row_count`.

**Đẩy.** Dùng lại kênh G5: Task Scheduler 15 phút, `pythonw`, một tar qua ssh tới `hao:/srv/v7/insurance/`, ghi file tạm rồi `mv` để server không đọc file dở. PDF (để Mở giấy) chỉ gửi giấy chưa có trên `hao`, tên file là `sha256`. **Mở đường ghi mới trên `hao` phải hỏi người dùng trước** ([Q3](#câu-hỏi-mở)).

**Đọc.** `WEBDEBIT_INSURANCE_SNAPSHOT_PATH` (mặc định `/srv/v7/insurance/insurance-web.json`). Đọc lỗi, sai `schema_version` hoặc sai hash → `{unavailable: true}`, sổ vẫn mở bình thường.

## Ghép và kế hoạch

1. Giấy có `status` khác `ok`, `amount_vnd` NULL hoặc có `warnings` → `CERT_REVIEW`.
2. Không có booking → `NO_BOOKING`. Chỉ có booking mà không có container thì cũng là `NO_BOOKING`.
3. Tìm chuyến theo mã chuyến (booking + container, viết hoa, bỏ khoảng trắng) trong mọi sổ, gồm chuyến web và dòng sổ gốc có booking. Không có → `NOT_FOUND`; hơn một → `AMBIGUOUS`. Không dùng cửa sổ ngày để chọn giữa nhiều chuyến.
4. Một chuyến: so `amount_vnd` với các khoản hiệu lực của chuyến.
   - Có khoản loại Bảo hiểm: bằng → `DONE`; khác → `AMOUNT_DIFF`. Nhiều khoản Bảo hiểm thì so tổng của chúng.
   - Không có Bảo hiểm, có **đúng một** khoản Khác hoặc Phụ phí ban đầu bằng đúng số giấy → `CLASSIFY` (hoặc `MONTH_LOCKED`). Hai khoản cùng bằng → `SHEET_MISSING` kèm câu "hai khoản cùng số, chọn tay".
   - Còn lại → `SHEET_MISSING`.
5. Kế hoạch `CLASSIFY`: giữ mọi khoản khác, thay đúng khoản đó bằng một khoản Bảo hiểm cùng số, giữ ghi chú. Dòng sổ gốc: ô TOTAL không đổi vì tổng phụ phí không đổi (giống `MAY-PS-01`).
6. Một chuyến không nhận hai giấy: hai giấy cùng ghép một chuyến → cả hai `AMBIGUOUS`.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT)

- `get_ledger` trả thêm `insurance: {snapshot_sha256, review: [...], done: [...], review_count}`. Mỗi mục: `cert_no`, `sha256`, `container`, `booking`, `depart_date`, `target_kind`, `target_id`, `month`, `cert_vnd`, `web_vnd`, `status`, `message`. Thiếu bản chụp thì `{unavailable: true}`.
- Việc cần làm thêm nhóm "Giấy bảo hiểm chưa có chuyến" (`NO_BOOKING`, `NOT_FOUND`, `CERT_REVIEW`), không gắn sổ.
- `GET /api/v7/insurance/cert/<sha256>`: trả PDF (`application/pdf`, `X-Content-Type-Options: nosniff`), chỉ khi `sha256` có trong bản chụp hiện tại và file trên đĩa băm ra đúng giá trị đó; quyền như mọi route V7 (Tailscale).
- Máy đổi loại: chạy trong lượt của máy theo Sheet (cùng chỗ máy PS), bật bằng `WEBDEBIT_AUTO_SHEET` có `insurance`, mặc định tắt. Mỗi chuyến một lệnh `rewrite_trip_fees` với `source: {kind: 'insurance', cert_no, sha256, snapshot_sha256}`; server tính lại kế hoạch từ bản chụp đúng hash. Lỗi giữ câu có sẵn (`FEE_LINES_CHANGED`, `FEE_TOTAL_CHANGED`, `MONTH_LOCKED`, `VERSION_CONFLICT`).
- Câu thông báo (ví dụ, dữ liệu giả): "MAUU1234567 · giấy bảo hiểm có, Sheet chưa ghi Bảo hiểm. Ghi tổng có VAT trên giấy vào cột BẢO HIỂM của tab khách."

## Nguồn quyết định

- Người dùng, chat 19/11/2026: số thu khách là tổng có VAT trên giấy; hỏi "đã tự điền bảo hiểm vô được chưa", rồi "Viết spec".
- [`SONG-SONG-01`](../docs/decisions/song-song-01.md), [`CHUYEN-HAN-01`](../docs/decisions/chuyen-han-01.md), [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md): Sheet là sổ chính thức, web theo Sheet.
- [`MAY-PS-01`](../docs/decisions/may-ps-01.md), [`PHU-PHI-01`](../docs/decisions/phu-phi-01.md): nguồn phụ chỉ phân loại, không cộng tiền.
- [`TACH-PHI-TIEU-DE-01`](../docs/decisions/tach-phi-tieu-de-01.md), [`COT-PHU-PHI-01`](../docs/decisions/cot-phu-phi-01.md): loại và cột Bảo hiểm.
- [`MAY-KHOA-01`](../docs/decisions/may-khoa-01.md): máy mở, ghi, khóa lại tháng.
- CÒN MỞ: Q1–Q4 dưới đây.

## Hành vi và bất biến

- **Giấy không bao giờ đổi tiền.** Tổng phụ phí từng chuyến, tổng tháng, tổng khách và ô TOTAL dòng sổ gốc giữ nguyên tới từng đồng; không phân bổ lại phiếu thu.
- Không gắn giấy vào chuyến chỉ theo container, ngày hay tên. Thiếu booking là việc của người.
- `amount_vnd` NULL không phải 0; giấy nhiều container không chia đều.
- VND `bigint`; không làm tròn.
- `hao` không nhận tên, mã số thuế hay tin nhắn Zalo trong phạm vi spec này.
- Không ghi Sheet, không ghi vào kho `zalo-audit-viewer`.

## Tiêu chí nghiệm thu

- [ ] P0 (chỉ đọc, trước khi code giao diện): đếm trạng thái của 16 giấy hiện có trên dữ liệu `hao` bằng một lệnh đọc; báo người dùng số `DONE` / `CLASSIFY` / `SHEET_MISSING` / `AMOUNT_DIFF` / còn lại. Không ghi gì.
- [ ] Unit ghép (dữ liệu giả): mỗi trạng thái của bảng bước 1 có ít nhất một ca; booking viết thường/có khoảng trắng vẫn khớp; hai khoản Khác cùng số → `SHEET_MISSING`; hai giấy một chuyến → `AMBIGUOUS`; `amount_vnd` NULL → `CERT_REVIEW`; dòng sổ gốc giữ `counted_vnd`.
- [ ] Unit bản gọn: không chứa tên, mã số thuế, số vận đơn; hash ổn định khi đọc lại; sai `schema_version` → `unavailable`.
- [ ] API: chỉ `CLASSIFY`/`MONTH_LOCKED` được ghi; hash đổi → tính lại, không ghi theo kế hoạch cũ; Mở giấy từ chối `sha256` không có trong bản chụp hoặc file băm sai.
- [ ] Playwright 1280×720, máy chủ giả: "Bảo hiểm cần xem: K" đúng số; danh sách đủ trạng thái; Mở giấy mở tab mới; bàn phím; thiếu bản chụp thì sổ vẫn mở.
- [ ] `npm run check` xanh.
- [ ] Trên `hao` (sau Q2, Q3): số dư từng khách trước = sau một lượt máy đổi loại.
- [ ] Người dùng tự đi hết luồng trên bản thử và xác nhận.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`). Review: opus (đường ghi phụ phí, dòng sổ gốc).
- Tách PR:
  - **PR-0 (P0, không code trong repo):** lệnh đọc một lần, kết quả báo trong chat; không lưu số thật vào repo.
  - **PR-1 (đọc):** `web/v7_insurance_queue.py`, trường `insurance` trong `get_ledger`, nhóm Việc cần làm, route Mở giấy, test. Không SQL.
  - **PR-2 (giao diện):** "Bảo hiểm cần xem" trong sổ khách, Mở giấy, test Playwright.
  - **PR-3 (máy đổi loại, sau Q2):** bước `insurance` trong máy theo Sheet, gọi `rewrite_trip_fees` có sẵn; không SQL mới.
  - Phía máy có Zalo (bản gọn + đẩy ssh) nằm ở repo `zalo-audit-viewer`, làm sau Q3.
- Ngân sách diff: mỗi PR ≤ 600 dòng logic.
- Lệnh kiểm: `npm run check`.
- Cấm: cộng hoặc đổi tiền theo giấy; gắn giấy theo container/ngày; đổi quy tắc khóa tháng, phân bổ, opening; ghi Sheet; mở đường ghi trên `hao` trước Q3; đưa số giấy, container, tên, mã số thuế hay PDF thật vào repo.

## Hoàn tác

PR-1/PR-2: revert, không đụng dữ liệu. PR-3: tắt `insurance` trong `WEBDEBIT_AUTO_SHEET`; khoản đã đổi loại đổi lại bằng nút sửa loại phí có sẵn, tổng không đổi nên không cần dòng điều chỉnh. Đường đẩy: tắt task trên máy có Zalo, xóa `/srv/v7/insurance`.

## Bằng chứng

Chưa có: spec ĐỀ XUẤT. Số đếm ở bước 2 đo trên `insurance-snapshot.json` ở máy có Zalo ngày 19/11/2026, không phải dữ liệu `hao`.

## Câu hỏi mở

- **Q1 — Khách trả là ai?** Giấy ghi người mua bảo hiểm và người được bảo hiểm (5/16 giấy hai tên trùng nhau). Đề xuất: chuyến thuộc sổ nào thì sổ đó trả, không so tên, nên `hao` không cần nhận tên. Nếu cần kiểm tên với sổ khách thì phải gửi thêm tên và thêm bảng tên phụ.
- **Q2 — Máy có được tự đổi loại Khác → Bảo hiểm khi bằng đúng số giấy, kể cả tháng khóa?** Đề xuất: có, như `MAY-PS-01`. Số trên giấy là tổng có VAT, lẻ tới từng đồng, nên trùng ngẫu nhiên rất khó.
- **Q3 — Mở đường đẩy bản gọn và PDF từ máy có Zalo lên `hao`?** Cần người dùng đồng ý trước, như G5.
- **Q4 — Sau khi chuyển hẳn khỏi Sheet, web có tự ghi tiền theo giấy không?** Ngoài phạm vi; ghi lại để xét cùng `CHUYEN-HAN-01`.
