# Zalo gần thời gian thực và thu chi đọc từ nhóm chat (ZALO-THU-CHI-01)

Trạng thái: **ĐÃ CHỐT** (người dùng, chat 19/11/2026: "Chốt theo đề xuất" cho Q1–Q8 ở [cuối spec](#câu-hỏi-đã-chốt)). Chưa code. [P0](#p0-đo-trước-khi-code) xong 20/11/2026 ([Bằng chứng](#bằng-chứng)). Quyết định đi kèm: [`ZALO-THU-CHI-01`](../docs/decisions/zalo-thu-chi-01.md).

Nguồn: sếp hỏi trong chat 19/11/2026: cần "một cái WeChat hoặc Zalo" để gửi phiếu thanh toán, thu chi vào đó, "để biết được tình hình thu chi thực tế để con bot nó có thể đọc được". Sau đó sếp nói rõ thêm: muốn một con bot add vào các nhóm chat. Người dùng chọn "Spec real-time + thu chi".

<!-- du-lieu-gia: 1.200.000 2.500.000 50.000.000 -->

## Vì sao không dùng "con bot add vào nhóm"

Tra ngày 19/11/2026:

- **Zalo Bot chính thức** add được vào nhóm, nhưng tài liệu của Zalo ghi phần nhóm vẫn "thử nghiệm nội bộ". Bot chỉ nhận tin khi có người @nhắc nó hoặc trả lời tin nó gửi, không đọc mọi tin. Tài liệu không nói bot có nhận ảnh trong nhóm hay không.
- **Bot bằng nick cá nhân** qua thư viện không chính thức đọc được hết, nhưng trái điều khoản Zalo và dễ bị khóa nick.
- **WeChat cá nhân** không có bot chính thức cho nhóm. WeChat Work có bot nhận tin @ trong nhóm, nhưng công ty phải dùng WeChat Work và nhóm phải do WeChat Work tạo.

Vì vậy spec này **đọc** nhóm bằng đường của [`ZALO-GROUP-01`](../docs/decisions/zalo-group-01.md). Máy có Zalo đọc dữ liệu Zalo PC ngay trên máy, không tự động hóa tài khoản. Phần "bot trả lời trong nhóm" để sau, xem [Ngoài phạm vi](#ngoài-phạm-vi).

## Câu hỏi quản lý mà spec trả lời

1. **Hôm nay, tuần này tiền vào bao nhiêu, ra bao nhiêu** theo những gì mọi người báo trong nhóm, kèm tin và ảnh làm chứng?
2. **Khoản nào đã báo trong nhóm mà chưa vào sổ:** chưa có phiếu thu ở sổ khách, chưa có dòng chi hoặc ứng ở Đội xe? Đây là chỗ hay sót tiền nhất. Hôm nay muốn biết thì phải lục lại Zalo.
3. **Khoản nào báo một số mà sổ ghi số khác?**

Spec **không** trả lời "tiền đã thật sự về tài khoản chưa". Tin trong nhóm là lời người báo; ảnh chuyển khoản có thể gửi nhầm, gửi trùng hoặc chưa thành công. Sự thật về tiền nằm ở ngân hàng ([Q7](#câu-hỏi-đã-chốt)).

## Kiểm kê nguồn

| Nguồn | Chứa gì | Đã có trên web? |
| --- | --- | --- |
| Nhóm Zalo chung với khách | Khách hứa trả, báo đã chuyển, gửi ảnh chuyển khoản | Đường đọc có ([`ZALO-GROUP-01`](../docs/decisions/zalo-group-01.md) G1–G5), **chưa chọn nhóm nào** nên `hao` chưa có tin |
| Nhóm nội bộ hoặc nhóm tài xế | Ứng tiền, chi dầu, phí cảng, sửa xe | Chưa đọc |
| Nhóm "Thu chi" mới (sếp đề nghị) | Ai thu, ai chi thì gửi vào | Chưa có nhóm |
| WeChat với đối tác | Thanh toán RMB | Không đọc được, xem trên |
| Sổ khách | `sokhach.receipt`: phiếu thu (ngày, số tiền, sổ) | Có |
| Đội xe | `doixe.dong` và `doixe.dong_phi` (chi phí chặng), `doixe.ung` (ứng), `doixe.tien_ve` (tiền về từ công ty mẹ) | Có, lên `hao` 18/11/2026 |
| Chi khác (văn phòng, lương…) | Không có sổ trên web | Không |

Nguồn sống ở máy có Zalo (`live-sync`) cập nhật mỗi giây khi Zalo PC chạy. Đo ngày 1/11/2026: 51 nhóm. Chưa đo bao nhiêu nhóm có tin tiền, nên phải đo ở [P0](#p0-đo-trước-khi-code).

## Người dùng và luồng (bước 1)

**Người thao tác:** sếp (xem, thường trên điện thoại 375–390px), người nhập và chủ sổ (xem và xác nhận, màn 1280×720), mọi người trong nhóm Zalo (chỉ gửi tin như mọi ngày, không vào web). Ai thao tác trên web thì lấy danh tính Tailscale ([`V7-ID`](../docs/decisions/v7-id.md)).

### Luồng 1. Gửi thu chi vào nhóm (mọi người, trên Zalo)

1. Thu hoặc chi xong thì gửi vào nhóm "Thu chi" (hoặc nhóm đang dùng đã được chọn) một tin theo mẫu, kèm ảnh nếu có:
   - `thu 50tr Khách A ck VCB`
   - `chi 2tr5 dầu xe 12345`
   - `chi 800k phí cảng xe 67890`
   - `ứng 3tr tài xế B`
2. Không theo mẫu cũng được. Tin vẫn lên web như chat thường; nếu có ảnh chuyển khoản thì máy đọc ảnh ([Luồng 4](#luồng-4-ảnh-chuyển-khoản-không-kèm-mẫu-đợt-sau)).

**Mẫu tin** (chốt ở [Q2](#câu-hỏi-đã-chốt)):

- Từ đầu: `thu`, `chi` hoặc `ứng` (không phân biệt hoa thường, có dấu hay không).
- Số tiền: `50tr`, `50 triệu`, `2tr5`, `2,5tr`, `800k`, `1.200.000`, `1200000`. Mọi cách đều đổi ra VND nguyên. Không đọc được thì số để trống (NULL), không phải 0.
- Phần còn lại là đối tượng và ghi chú:
  - **Tên khách:** khớp **đúng một** sổ theo tên không dấu thì gắn sổ đó; khớp nhiều sổ hoặc không sổ nào thì để "chưa rõ".
  - **Biển số:** 4–5 số cuối khớp **đúng một** xe của Đội xe thì gắn xe đó.
  - **Tài xế:** tên khớp đúng một người.
  - Không đoán thêm.

### Luồng 2. Xem thu chi (sếp, người nhập)

1. Mở trang **Thu chi**.
2. Đầu trang cho hôm nay và 7 ngày:
   - thu đã báo (số khoản, tổng);
   - chi đã báo;
   - **chưa vào sổ: K khoản**;
   - **lệch số: L khoản**.
3. Dưới là danh sách theo ngày. Mỗi dòng gồm:
   - giờ, nhóm, người gửi;
   - thu/chi, số tiền, đối tượng;
   - **trạng thái đối chiếu**;
   - ảnh nhỏ và nút **Mở tin**, bấm vào thì sang Chat Zalo đúng tin.
4. Có lọc: Chưa vào sổ, Lệch số, Chưa rõ đối tượng, Tất cả.
5. Trang tự thêm khoản mới vài giây sau khi tin được gửi ([Phần A](#phần-a-gần-thời-gian-thực)), không cần tải lại.

**Trạng thái đối chiếu** (máy tự chấm, chỉ đọc sổ):

| Mã | Khi nào | Câu hiện |
| --- | --- | --- |
| `RECORDED` | Thu có sổ: có phiếu thu chưa hủy cùng sổ, đúng số, ngày phiếu từ 1 ngày trước tới 3 ngày sau ngày báo. Chi hoặc ứng có xe/tài xế: có dòng chi hoặc ứng đúng số, đúng xe/tài xế, cùng khoảng ngày | Đã vào sổ (có nút mở phiếu hoặc dòng) |
| `WAITING` | Chưa thấy trong sổ, chưa quá 3 ngày | Chờ vào sổ |
| `MISSING` | Quá 3 ngày vẫn chưa thấy | **Chưa vào sổ** |
| `AMOUNT_DIFF` | Có đúng một phiếu hoặc dòng cùng đối tượng trong khoảng ngày nhưng khác số | Lệch: báo X, sổ Y |
| `SUGGEST` | Thu chưa rõ sổ: có **đúng một** phiếu thu ở bất kỳ sổ nào đúng số trong khoảng ngày | Có thể là phiếu của sổ … (người xác nhận) |
| `UNKNOWN_TARGET` | Không rõ đối tượng, không có gợi ý | Chưa rõ của ai |
| `NO_LEDGER` | Chi không thuộc Đội xe (văn phòng, lương…) | Web chưa có sổ chi này, chỉ liệt kê |
| `NO_AMOUNT` | Không đọc được số tiền | Không đọc được số |

Một phiếu hoặc dòng chỉ ứng với một khoản báo. Hai khoản báo cùng ứng với một phiếu thì cả hai thành `AMOUNT_DIFF`/`SUGGEST` để người xem, không tự chọn.

### Luồng 3. Xác nhận hoặc sửa (người nhập, chủ sổ; [PR-3](#chia-pr-và-cổng))

Ở mỗi dòng, người dùng bấm:

- **Gắn sổ/xe** để chọn đối tượng;
- **Sửa số** khi mẫu gõ sai, mà tin gốc vẫn giữ nguyên;
- **Không phải thu chi** để loại khoản ra, bắt buộc lý do.

Mỗi lần bấm ghi người làm và giá trị trước → sau, như dấu tin của ZALO-GROUP-01. Các thao tác này **không ghi tiền**: muốn vào sổ thì vẫn ghi phiếu thu ở sổ khách hoặc dòng chi ở Đội xe như hôm nay.

### Luồng 4. Ảnh chuyển khoản không kèm mẫu (đợt sau)

1. Máy có Zalo đọc chữ trong ảnh (OCR) **ngay trên máy đó**, như đã đọc giấy bảo hiểm ([`BAO-HIEM-ZALO-01`](../docs/decisions/bao-hiem-zalo-01.md)). Kết quả gồm số tiền, giờ giao dịch, ngân hàng, mã giao dịch.
2. Khoản chỉ có OCR thì là "chờ xác nhận". Khi có cả mẫu tin và OCR:
   - hai số bằng nhau thì khoản chắc chắn;
   - hai số khác nhau thì là `AMOUNT_DIFF` "mẫu X, ảnh Y".
3. Cùng mã giao dịch xuất hiện hai lần (gửi lại ảnh, gửi hai nhóm) thì chỉ tính một khoản, kèm cảnh báo trùng. (22/11/2026: chưa đọc được mã giao dịch; làm theo [B4 luật 3](#b4-trên-hao-trang-thu-chi-hiện-số-đọc-từ-ảnh-pr-4b-21112026): cùng ảnh ở bất kỳ nhóm nào, hoặc ảnh khác cùng nhóm cùng số cùng phút giao dịch, thì một khoản, ghi "gửi lại thêm N lần".)
4. Ảnh không gửi ra dịch vụ ngoài `hao` và máy có Zalo ([`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md) mục 4). Đọc ảnh bằng AI ngoài là [Q4](#câu-hỏi-đã-chốt).

### Bị chặn

- **Máy có Zalo tắt:**
  - trang Thu chi và Chat Zalo ghi rõ "Zalo cập nhật lần cuối lúc …", không giả là đang mới (22/11/2026: hai trang dùng chung `CongNoFormat.zaloFreshness`; Chat Zalo hỏi lại dòng đầu mỗi phút khi tab hiện; Zalo chưa mở thì cảnh báo nói "tin Zalo", vì WeChat đọc kho riêng);
  - quá 15 phút trong giờ làm việc thì máy canh gửi email ([Phần A](#phần-a-gần-thời-gian-thực), A4).
- **Không có quyền (ngoài Tailscale):** 403 như mọi trang.
- **Nhóm chưa chọn lên web:** không có tin. Hội thoại riêng tư không rời máy (ZALO-GROUP-01).

## Đầu ra

1. Tin mới của các nhóm đã chọn hiện trên web trong vòng **30 giây** (p95) khi máy có Zalo bật, kể cả ảnh. Hôm nay là tới 15 phút.
2. Trang Máy chạy và máy canh biết khi đường Zalo ngừng.
3. Trang **Thu chi**: mọi khoản báo thu, chi, ứng theo mẫu trong các nhóm đã chọn, với trạng thái đối chiếu với phiếu thu và sổ Đội xe.
4. (PR-3) Người dùng xác nhận, gắn đối tượng hoặc loại khoản, có vết.
5. (Đợt sau, theo P0) Đọc số từ ảnh chuyển khoản trên máy có Zalo.

## Phần A: gần thời gian thực

### Hiện nay

- Task `WebdebitZaloSync` 15 phút một lần **dựng lại cả gói** của các nhóm đã chọn (đo 1/11/2026: 3 nhóm, 13 giây, 95 MB), rồi đẩy qua ssh + tar tới `hao:/srv/v7/zalo-bundle`. Ảnh đã có thì không gửi lại, nhưng `messages.jsonl` gửi lại cả file.
- `v7_zalo_chat.py` nạp lại khi `export-report.json` đổi (so `mtime`, cỡ file), lập chỉ mục cả gói.
- Trang Chat Zalo không tự hỏi tin mới.
- Không phép kiểm nào biết đường đẩy đã ngừng.

### Đề xuất: giữ gói file và kênh ssh, đổi bốn chỗ

> **Thay ngày 20/11/2026:** [`ZALO-AGENT-01`](zalo-agent.md) (ĐÃ CHỐT) thay A1 và A4 bằng một tiến trình nền có con trỏ theo revision, kênh đẩy chung và `status.json`; A2 đổi thành "bản mới nhất theo `message_id` thắng; tin xóa hiện giống bản dựng đầy đủ"; A3 hỏi bằng con trỏ `since` theo thứ tự đến thay cho `after=<timestamp>`. A1 và A4 dưới đây giữ làm lịch sử; A2, A3 vẫn hiện hành với sửa đổi trên.

Không thêm bảng DB, không mở cổng ghi mới trên `hao`, không đổi Tailscale. Cùng thư mục `/srv/v7/zalo-bundle` và cùng tài khoản ssh mà người dùng đã đồng ý ở G5.

**A1. Máy có Zalo: `zalo_web_bundle.py watch`.**

- Tiến trình chạy nền, do Task Scheduler bật lúc đăng nhập và tự chạy lại khi chết. Thay task 15 phút.
- Cứ 2 giây xem cỡ file `messages.jsonl` của `live-sync`. Có tin mới thuộc nhóm đã chọn thì làm ba việc:
  - ghi thêm các tin đó (đã làm sạch như `build`) vào `messages-delta.jsonl` của gói;
  - tải ảnh của các tin đó **ngay**, nên ảnh không còn bị CDN Zalo xóa sau 2–3 tuần;
  - đẩy `messages-delta.jsonl`, ảnh mới và `export-report.json`.
- Gom thay đổi trong 3 giây rồi mới đẩy, để một loạt tin chỉ đẩy một lần.
- Mỗi đêm (và khi đổi nhóm đã chọn) dựng lại gói đầy đủ như `build` hôm nay: `messages.jsonl` mới, `messages-delta.jsonl` rỗng.

**A2. `hao`: đọc gói gốc + phần thêm.**

- `ChatStore` lập chỉ mục `messages.jsonl` một lần. Khi `export-report.json` đổi mà gói gốc không đổi (`bundle_sha256` giữ nguyên), chỉ đọc phần mới của `messages-delta.jsonl` từ vị trí đã đọc.
- Tin trùng `message_id` (đẩy lại sau lỗi mạng) thì giữ một.

**A3. Trang Chat Zalo và Thu chi tự cập nhật.**

- `GET /api/v7/zalo/messages` thêm tham số `after=<timestamp_ms>` để chỉ trả tin mới hơn.
- Trang đang mở và đang hiện trên màn hỏi 5 giây một lần; tab ẩn thì ngừng hỏi.
- Người đang đọc tin cũ thì không bị kéo xuống cuối: hiện nút "N tin mới".
- Chọn hỏi định kỳ thay vì giữ kết nối mở, vì server dùng thư viện chuẩn và mỗi kết nối mở chiếm một luồng.

**A4. Theo dõi sống còn.**

- `export-report.json` thêm `pushed_at` và `last_message_at`. Không có tin mới thì `watch` vẫn đẩy riêng file report mỗi phút làm nhịp tim.
- `/healthz` thêm `zalo: {age_seconds}`, chỉ là số đếm.
- Trang Máy chạy hiện "Zalo cập nhật lúc …".
- `tools/v7_watchdog.py` thêm một phép kiểm: nhịp tim quá 15 phút trong giờ làm việc (7:00–20:00 giờ VN) thì báo lỗi qua kênh email có sẵn ([cảnh báo](v7-canh-bao.md)). Ngoài giờ không báo, như các phép kiểm đêm.
- Phép kiểm này chỉ bật khi đã chọn ít nhất một nhóm.

**Phương án không chọn:** máy có Zalo gửi từng tin qua HTTPS vào một route ghi trên `hao`, lưu tin vào PostgreSQL. Trễ thấp hơn vài giây nhưng phải mở đường ghi mới qua mạng, thêm bảng tin nhắn riêng tư vào DB và vào bản dump, đổi quyền Tailscale. Chỉ xét khi đo được A1–A3 không đạt 30 giây.

## Phần B: thu chi từ tin

### B1. Đọc mẫu tin (`web/v7_cash_chat.py`, chỉ đọc)

- **Đầu vào:** tin chữ của các nhóm đã chọn trong gói. Tin ảnh gửi ngay sau, cùng người gửi, trong vòng 2 phút thì gộp vào khoản như ảnh chứng.
- **Đầu ra:** danh sách khoản báo `{message_id, conversation_id, sent_at, sender_name, direction: thu|chi|ung, amount_vnd|null, text, target: {kind: so|xe|tai_xe|null, id, label}, media}`.
- **Tính lại** mỗi lần gói đổi, giống cách `v7_ps_queue.py` và `v7_insurance_queue.py` tính từ bản chụp. Không lưu gì ở PR-2.
- **Đọc bằng luật cố định** (biểu thức chính quy), **không đưa tin chat vào model nào**. Tin trong nhóm là dữ liệu do người ngoài viết, không được thành câu lệnh. Nguyên tắc này đã giữ ở `web/v7_machine.py` của [`MAY-CHAY-01`](../docs/decisions/may-chay-01.md): không chữ tự do nào lấy từ Sheet hay Zalo đi tới model.

### B2. Đối chiếu (chỉ đọc)

Đối chiếu theo bảng trạng thái ở [Luồng 2](#luồng-2-xem-thu-chi-sếp-người-nhập):

- Phiếu thu đọc từ `sokhach.receipt` (bỏ phiếu đã hủy).
- Chi và ứng đọc từ `doixe.dong`, `doixe.dong_phi`, `doixe.ung`.
- Khoảng ngày và luật "quá 3 ngày" lấy đúng như máy chấm dấu "Khách báo đã chuyển" của ZALO-GROUP-01, để hai chỗ không chấm khác nhau. **Sửa 20/11/2026 (PR-2):** spec ghi (−1, +3) nhưng `sokhach._mark_json` chấm phiếu từ báo−3 tới báo+7 và "chưa thấy" khi quá báo+3; code dùng đúng số của SQL (`MATCH_BEFORE`, `MATCH_AFTER`, `MISSING_AFTER` trong `web/v7_cash_chat.py`) và một test đọc file SQL để hai nơi không lệch. Bảng trạng thái và Q6 vì vậy đọc là "từ 3 ngày trước tới 7 ngày sau ngày báo".
- Dấu "Khách báo đã chuyển" đã có (`contact_mark`) cũng hiện trong trang Thu chi như một khoản thu, không chép sang bảng khác.

### B3. Xác nhận và sửa (PR-3, có DB)

- Bảng mới `sokhach.cash_report_review`, nằm ngoài đường tiền như `contact_mark`. Mỗi dòng gồm: `message_id`, việc (`target`, `amount`, `not_cash`), giá trị, lý do, người làm, lúc làm, `request_id` để bấm lặp không ghi hai lần. Chỉ thêm dòng, bản mới nhất có hiệu lực, giữ vết.
- Không vào `v_outstanding_month`, không đổi phân bổ, không khóa tháng, không đổi `customer.version`.
- Triển khai theo [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md): thử trên bản sao, `ON_ERROR_STOP`, `v7_post_deploy_check.sql`, đối soát tổng khách, viết nhật ký.

### B4. OCR ảnh chuyển khoản (đợt sau, theo P0)

- Chạy ở máy có Zalo, chỉ cho ảnh của nhóm đã chọn: bộ xử lý `money_images` của [`zalo-agent`](zalo-agent.md#phần-3-kết-quả-đọc-ảnh-có-nguồn-gốc) (PR-4a, đã merge 20/11/2026, mặc định tắt).
- **Sửa 20/11/2026:** kết quả không gói vào tin ảnh mà đi riêng trong `money-reads.json` (khóa là sha256 ảnh, trùng `media[].id` của gói chat). `hao` chỉ nhận kết luận (`by`, số tiền, giờ giao dịch, ngân hàng) và số mỗi engine đọc ra, không nhận chữ OCR, số tài khoản hay tên. Chưa có mã giao dịch.

### B4 trên `hao`: trang Thu chi hiện số đọc từ ảnh (PR-4b, 21/11/2026)

`web/v7_cash_chat.py` đọc `$WEBDEBIT_ZALO_READS_DIR/money-reads.json` (mặc định `/srv/v7/zalo-reads`, thư mục mà máy Zalo đẩy tới bằng `--reads-target`). Chỉ đọc, không ghi gì.

- **Thiếu file** (chưa bật `money_images`): trang như trước.
- **File hỏng, quá 8 MB hoặc sai khuôn** (`schema` khác 1): bỏ cả file. Trang có dòng cảnh báo "Không đọc được kết quả đọc ảnh lúc này", không báo lỗi trang.
- **Một mục sai khuôn bị bỏ, không đoán:** khóa không phải sha256; kết luận có số mà số không phải số nguyên dương; giờ giao dịch hay tên ngân hàng lạ thì để trống.

Luật:

1. **Ảnh chứng của khoản gõ theo mẫu** (cùng người gửi, trong 2 phút sau tin) giữ như B1, và thắng bất kể thứ tự đọc: ảnh đã làm ảnh chứng ở bất kỳ hội thoại nào thì không thành khoản riêng. Nếu các ảnh chứng đọc ra đúng một số (tính trước khi gộp ảnh khác vào):
   - mẫu không đọc được số: lấy số của ảnh, ghi "đọc từ ảnh";
   - mẫu và ảnh khác số: cảnh báo **Lệch: mẫu X, ảnh Y** (đếm vào Lệch số, như Luồng 4). Trạng thái đối chiếu giữ nguyên và hiện ở dòng dưới (đã vào sổ, gợi ý sổ, chưa vào sổ…).
2. **Ảnh còn lại có kết luận thành một khoản thu "từ ảnh"**, mỗi ảnh một khoản, khi người gửi không phải tài khoản Zalo của mình. Ảnh mình gửi đi thường là mình trả hoặc chuyển tiếp, không phải tiền vào.
   - **Đối tượng:** hội thoại gắn đúng một sổ (`get_zalo_links`, ZALO-GROUP-01) thì là sổ đó. Chưa gắn hoặc gắn nhiều sổ thì chưa rõ của ai, vẫn gợi ý phiếu đúng số như thu chưa rõ sổ.
   - **Số:** số của kết luận (`ocr`, hoặc hai đường ngoài khớp nhau). Kết luận "cần người xem" (`human`) thì không có số, không vào tổng, hiện "Ảnh chưa đọc chắc" kèm các số máy đọc ra.
   - **Ngày:** ngày tin. Ảnh cũ gửi lại (giao dịch trước ngày tin, trong 93 ngày) thì là ngày giao dịch, để đối chiếu đúng phiếu và cộng vào đúng ngày tiền vào. Giao dịch trước khoảng đang xem thì không cộng, trang chỉ ghi số ảnh như vậy. Ảnh ghi ngày giao dịch trước ngày tin từ 93 ngày trở lên (ảnh rất cũ gửi lại, hoặc máy đọc nhầm ngày; 22/11/2026) vẫn nằm ở ngày tin và vẫn cộng như trước, nhưng có cờ `old_txn` và **không bao giờ bị kết luận "chưa vào sổ"**: khớp đúng phiếu thì vẫn "Đã vào sổ"; không khớp thì giữ "chờ" và trang ghi "Ảnh ghi ngày cũ" kèm ngày trên ảnh để người mở ảnh xem.
   - **Đối chiếu sổ** như khoản thu gõ tay (B2), trừ một điều: khoản từ ảnh không ghép đoán (lệch số, gợi ý) vào phiếu mà một dấu "Khách báo đã chuyển" đang giữ. Ảnh khác số với phiếu đó thường là lần trả khác. Khoản gõ tay vẫn ghép như cũ vì gõ nhầm số là chuyện thường.
3. **Không đếm hai lần.** Mỗi khoản thu gõ theo mẫu và mỗi dấu "Khách báo đã chuyển" là một lần trả. Ảnh (theo thứ tự gửi) gắn vào:
   - cùng ảnh (cùng khóa) gửi nhiều lần, kể cả ở nhóm khác hay ảnh đã làm ảnh chứng của khoản gõ: một khoản, lần sớm nhất;
   - chỗ đang giữ một ảnh cùng hội thoại, cùng số, cùng giờ giao dịch (tới phút, theo giờ VN), không giới hạn ngày: cùng một giao dịch;
   - dấu đặt trên chính tin ảnh;
   - khoản thu gõ cùng hội thoại, cùng số (số gõ hoặc số ảnh chứng), cách không quá 24 giờ; rồi dấu cùng hội thoại, cùng số, ngày báo cách ngày giao dịch của ảnh không quá 1 ngày. Hai điều kiện: giờ giao dịch không vênh với ảnh chỗ đó đã có (giờ khác là lần trả khác), và chỗ đó chưa nhận ảnh nào theo luật này. Ảnh gắn vào dấu thì giữ số người nhập trên dấu; ảnh đọc ra số khác chỉ ghi chú "Ảnh đọc ra X".
4. **Trang:**
   - khoản từ ảnh có chữ "đọc từ ảnh" dưới số tiền;
   - cột nội dung ghi giờ giao dịch rồi ngân hàng máy đọc được ("Giao dịch 09:58 · VIETCOMBANK"; khác ngày tin thì thêm ngày). Giờ đứng trước vì ô hẹp bị cắt ở cuối dòng. Không đọc ra giờ thì ghi "Ảnh chuyển khoản · ngân hàng";
   - khoản nằm ở ngày khác ngày tin (ảnh cũ gửi lại, dấu) thì cột giờ ghi cả ngày tin;
   - khoản chưa rõ của ai ghi lý do: "Hội thoại chưa gắn sổ", "Hội thoại gắn nhiều sổ" hoặc "Không đọc được danh sách nhóm gắn sổ lúc này";
   - khối tổng ghi "N khoản, M từ ảnh".

**"Chờ xác nhận" của Luồng 4:** khoản từ ảnh là máy đọc. Khớp phiếu đúng số nghĩa là sổ đã xác nhận. Nút xác nhận bằng tay thuộc PR-3.

**Giờ giao dịch** lưu dạng ISO. Hao nhận thêm cách ghi của đường đọc ngoài (cách thay `T`, `Z`, `+0700`) rồi chuẩn hóa; ngày giờ không có thật thì để trống.

**API:** mỗi `item` thêm:

- `image_vnd`: số đọc từ ảnh của khoản (khoản gõ: chỉ ảnh chứng), hoặc `null`;
- `image_diff`: `true` khi mẫu và ảnh chứng khác số;
- `amount_from`: `anh` khi số tiền lấy từ ảnh, không thì `null`;
- `image`: chỉ có ở khoản từ ảnh, gồm `{by, bank, txn_time, candidates}`;
- `link`: chỉ có ở khoản từ ảnh, là `one`, `many`, `none` hoặc `failed`.

`source` thêm giá trị `anh`. `totals` thêm `from_image` (số khoản từ ảnh có số), và `amount_diff` đếm cả `image_diff`. Kết quả thêm `images_before` (số ảnh cũ gửi lại có giao dịch trước khoảng xem). `sources_failed` có thể có:

- `reads`: file đọc ảnh hỏng;
- `links`: không đọc được danh sách nhóm gắn sổ.

Review độc lập ngày 21/11/2026 (FinanceBullkk/webdebit#562) tìm ra 8 chỗ đếm hai lần, ẩn nhầm hoặc ghi sai lý do ở bản đầu. Luật trên là bản đã sửa; mỗi chỗ có một test trong `ImageReadTests`.

CÒN MỞ:

- Ảnh chuyển khoản do người không phải tài khoản Zalo của mình gửi vẫn tính là thu, kể cả nhân viên khác trong nhóm khách.
- File chưa có mã giao dịch. Hai ảnh khác nhau của cùng một giao dịch mà máy không đọc ra giờ giao dịch vẫn thành hai khoản; hai ảnh khác nhau của cùng giao dịch gửi ở **hai nhóm** cũng vậy (không gộp chéo nhóm chỉ bằng số và giờ: hai khách trả cùng số cùng phút là có thể).
- **Cảnh báo trùng (22/11/2026, Luồng 4 mục 3):** mỗi lần gửi lại bị gộp (cùng ảnh; hoặc gộp theo "cùng số, cùng giờ giao dịch") cộng một vào `resent` của khoản giữ lần trả; trang ghi "Ảnh chuyển khoản gửi lại thêm N lần (cùng giao dịch): chỉ tính một lần." ở ô trạng thái. Ảnh gắn làm ảnh chứng của khoản gõ hay của dấu khách báo không phải trùng. Tổng không đổi.

## P0: đo trước khi code

Chỉ đọc, chạy ở máy có Zalo, chỉ báo số đếm trong chat, không lưu nội dung vào repo:

1. 51 nhóm: mỗi nhóm có bao nhiêu tin ảnh mỗi tuần, bao nhiêu tin chữ có dạng số tiền (`\d+ ?(tr|triệu|k)`), trong 8 tuần gần nhất. Mục đích là biết nhóm nào thật sự mang tin tiền, rồi đề xuất danh sách nhóm cho người dùng chọn.
2. Ước lượng dung lượng gói và thời gian nạp lại trên `hao` cho danh sách đó (A2 có cần đọc thêm từng phần không).
3. Thử OCR trên 20 ảnh chuyển khoản gần nhất, chỉ tại máy có Zalo, đếm bao nhiêu ảnh đọc đúng số tiền. Từ 18/20 trở lên thì làm B4; thấp hơn thì dựa vào mẫu tin.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT)

| Route (qua xác thực như mọi `/api/v7/*`) | Trả về |
| --- | --- |
| `GET /api/v7/zalo/messages?…&after=<ms>` | như hiện có, chỉ tin có `timestamp_ms > after`; thêm `bundle_at` |
| `GET /api/v7/zalo/report` | thêm `zalo {state, at, silent_minutes, identity, quiet_minutes}` (nhịp tim máy Zalo, chỉ mã, giờ, số phút; cùng phần `zalo` của `/api/v7/cash-chat`). Sửa 22/11/2026: thay `pushed_at`, `last_message_at`, `age_seconds` của bản đề xuất |
| `GET /api/v7/cash-chat?from=YYYY-MM-DD&to=YYYY-MM-DD&status=` | `{items:[{…khoản B1, status, ledger_ref, ledger_vnd, message}], totals:{thu_vnd, chi_vnd, ung_vnd, missing, amount_diff}, zalo_age_seconds}`; thiếu gói → `{unavailable: true}` |
| `POST /api/v7/cash-chat/review` (PR-3) | `{message_id, action, value, reason, request_id}` → dòng đã ghi; lỗi `REASON_REQUIRED`, `MESSAGE_NOT_FOUND`, `TARGET_NOT_FOUND` |
| `GET /api/v7/cash-chat/targets` (PR-3b) | `{so, xe, tai_xe: [{id, label}], failed}`: danh sách cho ô "Gắn sổ/xe"; mọi sổ, xe và người còn dùng |

Các tổng là VND `bigint`. Khoản `NO_AMOUNT` không cộng vào tổng và được đếm riêng.

**Khuôn đã code ở PR-2** (`web/v7_cash_chat.py`; `/api/v7/cash-chat` chỉ cho quản lý như Đội xe, vì có số chi và ứng của Đội xe):

- Mặc định 7 ngày tới hôm nay (giờ VN), tối đa 93 ngày; `status=` nhận mã trạng thái cách nhau bằng dấu phẩy và chỉ lọc `items`, còn `totals` và `counts` tính trên cả khoảng.
- Mỗi `item`: `message_id`, `conversation_id`, `conversation_name`, `sent_at` (ms), `day`, `sender_name`, `direction`, `amount_vnd` (số nguyên hoặc `null`), `text` (≤ 300 ký tự), `media`, `target {kind, id, label}`, `ambiguous`, `status`, `shared`, `ledger_ref`, `ledger_vnd`, `source` (`chat` hoặc `mark`); từ 22/11/2026 thêm `resent` (số lần cùng giao dịch được gửi lại, 0 là không trùng).
- `zalo_age_seconds` được thay bằng `zalo {state, at, silent_minutes, identity, quiet_minutes}` lấy từ `status.json` của máy Zalo (`v7_machine.zalo()`), cộng `bundle_at` (giờ dựng gói) và `last_message_at`: đủ để phân biệt "máy im", "Zalo chưa mở" và "ít tin".
- `shared: true` khi một phiếu hoặc dòng sổ là ứng viên của hai khoản báo; cả hai hiện `AMOUNT_DIFF` (hoặc `SUGGEST`) cho người chọn.
- **Không đoán số và đối tượng (review 20/11/2026):** đơn vị rồi cách rồi chữ số ("1 triệu 2", "2 tr 5") và dấu trừ dính vào số ("chi -500k") là `NO_AMOUNT`, còn gạch có khoảng trắng ("chi - 500k") là dấu ngăn và vẫn đọc 500.000 (chủ ý). "Số rời" chỉ tính khi 1–3 chữ số đứng một mình và không dính chữ cái, không là ngày, không đứng trước danh từ đếm được: "1 triệu 2", "2 tr 5" là `NO_AMOUNT`, còn "5tr 30 cont", "2tr 51C-123.45", "800k 2 xe" đọc 5 triệu, 2 triệu, 800 nghìn; biển số chỉ nhận khi có chữ cái của dãy biển (51C-123.45) hoặc đứng ngay sau "xe", "bks", "bs", "biển số" ("15.11", "2026" không phải biển); tên sổ hoặc người ngắn hơn 3 ký tự (bỏ dấu) không tự khớp.
- **Ghép một-một cực đại:** trong mỗi nhóm khoản tranh chung dòng sổ, nếu có cách ghép đủ cho mọi khoản thì ghép (khoản sớm trước, dòng sớm trước); không đủ thì cả nhóm `shared`. Dấu "Khách báo đã chuyển" cùng tin hoặc cùng phiếu (`receipt_pid`) với một khoản chat bị ẩn (giữ khoản chat, tổng thu không cộng hai lần; `marks_hidden` đếm số dấu ẩn); cửa sổ ngày của dấu tính từ `on_date`, của khoản chat từ ngày tin.
- **Nguồn hỏng không làm sập trang:** dòng có giá trị null hoặc sai khuôn bị bỏ (NULL không thành 0); một hàm đọc lỗi thì `sources_failed` ghi mã (`receipt`, `fleet`, `directory`, `marks`) và các khoản liên quan là `WAITING` kèm `unchecked: true` ("chưa đối chiếu được"), không bao giờ kết luận `MISSING` từ một nguồn không đọc được. Giới hạn 20 nhóm áp cho cả tin chat và dấu (`conversations_skipped`); nhiều người hỏi cùng lúc chỉ dựng một lượt. Nhóm `shared` giữ các dòng của nó khỏi khoản khác; thu chưa rõ sổ mà nguồn phiếu lỗi cũng là `unchecked`; dữ liệu lạ (cột sai kiểu, giờ vô lý, tên khác không phải mảng) bị bỏ hoặc cho `{unavailable: true, reason: "UNREADABLE"}` chứ không 500, và người chờ lượt dựng của người khác quá 60 giây thì tự dựng.
- **Trang Thu chi (PR-2b, `thu-chi.html`):** thẻ "Thu chi" trong dải Quản trị, chỉ quản lý (cùng quyền route). Đầu trang hai khối Hôm nay và 7 ngày (thu, chi, ứng, chưa vào sổ, lệch số), chip lọc có số đếm, danh sách theo ngày với nút "Mở tin" (`/zalo-chat.html?c=&m=`) và ảnh chứng; chọn 7 hoặc 30 ngày. Hỏi lại 5 giây một lần khi tab hiện (lỗi liên tiếp thì giãn 10, 20, 30 giây), tab ẩn thì ngừng. Khoản mới nền vàng nhạt một lần; khi người dùng đang đọc (cuộn xuống hoặc tiêu điểm nằm trong danh sách) thì không vẽ lại mà hiện nút "Có N khoản mới, bấm để xem", bấm hoặc cuộn về đầu thì nhận. Nguồn sổ đọc lỗi thì có dòng cảnh báo và khoản liên quan ghi "Chưa đối chiếu được". Luôn hiện "Zalo cập nhật lúc …" ("lần cuối" khi máy im hoặc Zalo chưa mở quá 5 phút) kèm dòng cảnh báo.
- Đọc DB chỉ qua hàm đọc có sẵn: `list_customers`, `doixe_get_tong`, `get_receipt_book` (theo tháng, gồm phiếu web chưa hủy và dòng thu sổ gốc), `doixe_get_so` (theo xe hoặc người, chỉ cho đối tượng đã gắn), `get_marks` (theo nhóm). Kết quả giữ 8 giây trong bộ nhớ vì trang hỏi vài giây một lần.
- Chi hoặc ứng khớp một dòng phí (`dong_phi`) hoặc một lần ứng chưa hủy của Đội xe; chi không có xe/người mà có từ "lương", "văn phòng", "mặt bằng", "internet"… là `NO_LEDGER`, còn lại không rõ đối tượng là `UNKNOWN_TARGET`.

**Khuôn đã code ở PR-3** (21/11/2026; đợt này chỉ DB và API, nút trên trang làm ở PR-3b bên dưới):

- `POST /api/v7/cash-chat/review`, chỉ quản lý (cùng tiền tố `/api/v7/cash-chat`). Thân `{message_id, action, value, reason, request_id}`:
  - `confirm` xác nhận; `amount` sửa số (`value` là chuỗi VND số nguyên dương); `target` gắn đối tượng (`value` là `{kind: so|xe|tai_xe, id}`); `not_cash` loại, bắt buộc `reason`;
  - tin phải còn trong gói chat và chưa xóa (`MESSAGE_NOT_FOUND`); mã hội thoại lấy từ gói, không lấy từ trang;
  - lỗi khác: `INVALID_CASH_REVIEW`, `REASON_REQUIRED`, `TARGET_NOT_FOUND` (sổ, xe, người không có), `MULTIPLE_IMAGES` (một tin có nhiều ảnh chuyển khoản: xác nhận theo tin không biết là ảnh nào);
  - bấm lặp cùng `request_id` và đúng nội dung cũ thì trả dòng đã ghi (`replayed: true`); khác bất kỳ trường nào (số, đối tượng, lý do, tin) thì `IDEMPOTENCY_CONFLICT`, như `record_mark`.
- `sokhach.cash_report_review` chỉ thêm dòng. Trạng thái hiệu lực của một tin là các dòng gộp theo thứ tự: sửa số hay gắn đối tượng thì bỏ quyết định cũ (đã xác nhận số cũ), xác nhận và loại thay nhau. Mỗi dòng ghi `before` (trạng thái ngay trước; `{}` là giá trị đọc từ tin), người làm, lúc làm. Hai người bấm cùng một tin thì xếp hàng theo tin.
- `GET /api/v7/cash-chat`:
  - khoản đã có dòng thì có `review` (`decision`, `reason`, `reviews`, `last_action`, `last_by`, `last_at`);
  - số sửa thay số đọc từ tin (`amount_from: "sua"`), đối tượng gắn tay thay đối tượng tự khớp, đều trước khi gộp ảnh chứng và trước khi đối chiếu (số sửa có thể khớp đúng ảnh của khoản đó, nên không cộng hai lần);
  - khoản đã loại có `status: NOT_CASH`: không giữ ảnh chứng, không đối chiếu, không đếm và không cộng vào tổng, không hiện trong danh sách mặc định (hỏi `status=NOT_CASH` để xem); `counts.NOT_CASH` đếm số khoản đã loại;
  - đọc trạng thái lỗi thì `sources_failed` có `reviews`. Bấm xong thì bỏ kết quả đang giữ, lần hỏi kế tiếp thấy ngay.

**Khuôn đã code ở PR-3b** (22/11/2026; nút trên trang Thu chi, Luồng 3; không đổi DB):

- Mỗi khoản gõ hoặc ảnh có nút **Xử lý**; bấm thì mở khung ngay dưới dòng (không hộp nổi, khoản đang sửa vẫn thấy ngay trên), một khung một lúc. Dấu khách báo không có nút (sửa ở Chat Zalo); tin có hai ảnh chuyển khoản không có nút và ghi lý do (máy chủ không biết xác nhận ảnh nào, `MULTIPLE_IMAGES`).
- Bốn việc: **Đúng, xác nhận** (bấm thẳng; không hiện khi đã xác nhận hay khoản chưa có số), **Sửa số**, **Gắn sổ/xe**, **Không phải thu chi**. Khoản đã loại chỉ có **Đưa lại vào thu chi** (một lần xác nhận). Mỗi lúc một nút chính.
- **Trước → sau** hiện trước khi bấm Lưu: "Số: X → Y", "Đối tượng: A → B". Ô số chỉ nhận chữ số và dấu ngăn nghìn, không đọc "tr", "k" (không đoán số); bằng số đang có hay đúng đối tượng đang có thì nút Lưu tắt. Thu chỉ gắn sổ; chi và ứng chọn xe hoặc tài xế; tìm bỏ dấu, biển số không cần gạch, giữ chữ Hán. Danh sách lấy từ `GET /api/v7/cash-chat/targets` (chỉ quản lý, cùng tiền tố), hỏi lần đầu mở ô gắn.
- Loại bắt buộc lý do; xong thì có dòng báo kèm nút **Hoàn tác** (một lần xác nhận với mã yêu cầu mới). Khoản đã loại nằm ở chip "Đã loại" (chỉ hiện khi có), không đếm, không cộng; trang hỏi đủ mọi trạng thái (`status=` cả `NOT_CASH`) để chip không phải hỏi riêng.
- Dòng ghi lần xử lý gần nhất trong ô trạng thái ("Đã xác nhận · người · giờ · N lần"); số sửa ghi "đã sửa tay" dưới số, đối tượng gắn tay ghi "gắn tay" (`target_from: "sua"` trong `GET`).
- Mã yêu cầu tạo khi mở khung hay đổi việc, giữ qua lần bấm lại sau lỗi mạng ("Không chắc đã lưu… máy không ghi hai lần"); `IDEMPOTENCY_CONFLICT` thì đổi mã và tải lại. Lỗi khác hiện câu của máy chủ.
- Khung đang mở thì nhịp 5 giây không vẽ lại (chữ đang gõ giữ nguyên), bản mới chờ ở nút "Có N khoản mới"; Esc hay Đóng thì nhận. Cột nút cố định 236px ở màn rộng để số tiền các dòng thẳng cột; dưới 1000px cụm nút xuống hàng riêng.

## Nguồn quyết định

- Sếp và người dùng, chat 19/11/2026 (trích ở đầu spec).
- [`ZALO-GROUP-01`](../docs/decisions/zalo-group-01.md): chỉ nhóm đã chọn lên `hao`; "Khách báo đã chuyển" không ghi tiền, máy tự chấm theo phiếu thu.
- [`UX-NEN-01`](../docs/decisions/ux-nen-01.md) M1: tiền chỉ vào sổ bằng phiếu thu, không thêm chỗ ghi tiền thứ hai.
- [`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md): ảnh không ra dịch vụ ngoài `hao`; đọc số từ ảnh còn mở.
- [`BAO-HIEM-ZALO-01`](../docs/decisions/bao-hiem-zalo-01.md): mẫu đọc ở máy có Zalo, ghép trên `hao`, không cộng tiền.
- [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md), [`DOI-XE-THU-01`](../docs/decisions/doi-xe-thu-01.md): sổ chi, ứng, tiền về của Đội xe.
- [`CANH-BAO-01`](../docs/decisions/canh-bao-01.md): máy canh và email.
- Người dùng, chat 19/11/2026: "Chốt theo đề xuất" cho Q1–Q8 ([Câu hỏi đã chốt](#câu-hỏi-đã-chốt)).
- CÒN MỞ: engine OCR (B4), danh sách nhóm (sau P0), khoảng ngày cho chi Đội xe (Q6).

## Hành vi và bất biến

- **Tin trong nhóm không bao giờ ghi tiền.** Không tạo, sửa hay hủy phiếu thu, dòng chi hay ứng; không đổi phân bổ, khóa tháng, tổng khách.
- VND nguyên. Không đọc được số thì NULL, không phải 0, và không cộng vào tổng.
- Chỉ nhóm đã chọn rời máy có Zalo. Ảnh và kết quả OCR không gửi ra dịch vụ ngoài.
- Đối tượng chỉ gắn khi khớp **đúng một**; còn lại để người gắn.
- Một phiếu hoặc dòng sổ ứng với tối đa một khoản báo.
- Tin chat không đi vào model hay lệnh nào có quyền ghi.
- Mọi xác nhận, sửa, loại (PR-3) ghi người làm, trước → sau; loại thì bắt buộc lý do; bấm lặp cùng `request_id` chỉ ghi một lần.
- Web không giả là dữ liệu mới: luôn hiện tuổi của dữ liệu Zalo.

## Tiêu chí nghiệm thu

- [x] P0 xong, số đếm báo trong chat; người dùng chọn nhóm đưa lên web (20/11/2026: giữ nhóm đang lên web, các nhóm khác không liên quan; nhóm Thu chi chờ lập).
- [x] Unit `watch` (dữ liệu giả, đồng hồ giả). `watch` thành `zalo_agent run` ([`zalo-agent`](zalo-agent.md)); test ở `tests/test_zalo_agent.py` (đối chiếu 22/11/2026):
  - tin mới thuộc nhóm đã chọn vào `messages-delta.jsonl`, tin nhóm không chọn và chat riêng thì không (`test_add_update_delete_become_delta_and_unselected_groups_stay_out`, `test_revision_without_selected_messages_moves_cursor_and_sends_nothing`);
  - ảnh tải ngay (`test_delta_of_new_image_adds_media_and_is_sent`);
  - gom 3 giây thành một lần đẩy (`test_message_arriving_during_the_three_second_wait_goes_out_in_the_same_push`: tin thứ hai tới giữa lúc chờ đi cùng lượt);
  - không có tin thì vẫn có nhịp tim mỗi phút (`test_heartbeat_goes_out_every_minute_even_with_no_new_message`);
  - dựng đêm làm rỗng delta (`test_rebuild_from_scratch_when_cursor_cannot_be_trusted`, ca `nightly`).
- [x] Unit `ChatStore` (`tests/test_v7_zalo_chat.py`, lớp `ZaloDeltaTest`):
  - đọc thêm delta mà không lập lại chỉ mục gói gốc (`test_report_change_reads_only_new_delta`);
  - `message_id` trùng chỉ còn một, bản mới nhất thắng (`test_edit_replaces_and_deleted_line_shows_like_a_full_build`);
  - `after=` (thay bằng `since=` ở ZALO-AGENT-01) trả đúng tin mới hơn, kể cả tin tới muộn, tin sửa, tin xóa (`test_since_returns_everything_that_arrived_after_the_token_even_old_edits_and_late_messages`, `test_since_asks_for_a_reload_when_the_bundle_was_rebuilt`).
- [x] Unit `v7_cash_chat.py` (`tests/test_v7_cash_chat.py`):
  - mọi cách viết số ở [Luồng 1](#luồng-1-gửi-thu-chi-vào-nhóm-mọi-người-trên-zalo) ra đúng VND (`test_amount_forms`);
  - số không đọc được thành NULL (`test_unreadable_amount_is_none_not_zero`);
  - đối tượng khớp hai sổ thành "chưa rõ" (`test_two_books_is_unknown_but_longest_name_wins`);
  - mỗi trạng thái đối chiếu có ít nhất một ca (`test_every_status`; `NOT_CASH` ở `ReviewTests`);
  - một phiếu không ứng với hai khoản (`test_one_receipt_matches_one_report`, `test_matching_is_maximum_not_greedy_in_both_orders`);
  - phiếu đã hủy không tính (`test_voided_receipt_is_not_counted`).
- [x] Unit máy canh: Zalo quá 15 phút trong giờ làm việc thì báo, ngoài giờ không báo, chưa chọn nhóm thì không kiểm (`tests/test_v7_watchdog.py`: `test_silent_status_reports_during_work_hours_only`, `test_waiting_for_zalo_reports_after_15_minutes`, `test_no_selected_group_means_no_check`).
- [x] Playwright, máy chủ giả, 1280×720 và 390×844 (`test-thu-chi-browser.js`; 22/11/2026 thêm hai ca "Thu chi ở điện thoại 390×844" chạy hành vi, không chỉ bố cục):
  - khoản mới tự hiện sau một lượt hỏi (ca "khoản mới tự hiện sau một lượt hỏi"; 390×844);
  - đang đọc tin cũ thì hiện nút "N tin mới" (ca "đang đọc (cuộn xuống)…", "tiêu điểm đang ở trong danh sách…"; 390×844: nút ≥ 40px, trong màn);
  - lọc Chưa vào sổ đúng số (ca "lọc Chưa vào sổ, Lệch số, Chưa rõ đối tượng…"; 390×844);
  - Mở tin sang đúng tin (ca "Mở tin sang đúng tin của Chat Zalo…"; Chat Zalo: "?c=&m= mở đúng tin ở giữa hội thoại…");
  - Zalo cũ hiện câu "cập nhật lần cuối" (ca "Zalo cũ hiện "cập nhật lần cuối"…"; 390×844; trang Chat Zalo ở PR #574);
  - dùng được bằng bàn phím (chip lọc bằng Tab/Space/Enter; khung Xử lý: Enter lưu, Esc đóng; 390×844: Space trên chip).
- [x] PR-4b, test với gói chat, `money-reads.json` và sổ bịa (`tests/test_v7_cash_chat.py`, `test-thu-chi-*.js`):
  - ảnh có kết luận thành khoản thu, đối tượng theo hội thoại gắn đúng một sổ;
  - ảnh mình gửi không thành khoản;
  - `human` không vào tổng;
  - mẫu và ảnh khác số thì Lệch, mẫu không có số thì lấy số ảnh;
  - các luật không đếm hai lần, kể cả 8 tình huống của review #562 (ảnh chứng thắng bất kể thứ tự, giờ giao dịch khác là lần trả khác, ảnh cũ gửi lại, phiếu của dấu khách báo);
  - file thiếu, hỏng hoặc mục sai khuôn không làm hỏng trang;
  - trang hiện "đọc từ ảnh", "Ảnh chưa đọc chắc", "N khoản, M từ ảnh".
- [x] PR-3: harness PostgreSQL cho `cash_report_review`: không đổi dấu vân tay tổng khách, bấm lặp chỉ ghi một lần, loại mà thiếu lý do thì bị từ chối, quyền của role app và role reader (21/11/2026: ca `ZALO-THU-CHI.03` ở `tools/test_pg_v7_backend_cash_review.py`, danh mục quyền ở `tools/test_pg_v7_grants.py`; API: `ReviewTests` ở `tests/test_v7_cash_chat.py`).
- [ ] `npm run check` xanh; `node scripts/check-secrets.js` xanh.
- [ ] Trên `hao` (dữ liệu thật): gửi một tin thử vào nhóm thì tin lên web trong ≤ 30 giây; tắt Zalo 20 phút trong giờ làm việc thì có email.
- [x] PR-3b: test nút Luồng 3 (`test-thu-chi-model.js`, `test-thu-chi-browser.js` nhóm "Xử lý", `ReviewTests` cho `/targets`): xác nhận, sửa số chỉ nhận chữ số và hiện trước → sau, gắn theo hướng thu/chi, loại bắt buộc lý do + Hoàn tác, đã loại không đếm không cộng, mất mạng bấm lại cùng mã, mã trùng thì đổi mã, khung mở thì không vẽ lại, 1280×720 nút Lưu trong khung thấy, 390px không tràn và nút ≥ 40px (22/11/2026).
- [ ] Sếp và người dùng tự đi hết Luồng 1–2 (PR-3 thì thêm Luồng 3) trên bản thử và xác nhận.

## Chia PR và cổng

| Bước | Nội dung | DB | Cổng hỏi người dùng |
| --- | --- | --- | --- |
| P0 | Đo, chỉ đọc | Không | Người dùng chọn nhóm |
| PR-1 | A1–A4: `watch`, delta, `after=`, tự cập nhật trang Chat Zalo, nhịp tim, máy canh | Không | Thay task 15 phút bằng tiến trình chạy nền trên máy có Zalo |
| PR-2 | B1–B2: `v7_cash_chat.py`, route đọc, trang Thu chi chỉ xem | Không | — |
| PR-3 | B3: bảng `cash_report_review`, hàm, route ghi | Có, ngoài đường tiền | Tự triển khai theo `DEPLOY-CLAUDE-01` |
| PR-3b | B3 trên trang Thu chi: nút xác nhận/sửa số/gắn/loại, route danh sách đối tượng | Không | — |
| PR-4 | B4: OCR ở máy có Zalo (P0 đạt 20/20), Gemini cho ảnh OCR đọc không chắc theo [`ANH-GEMINI-01`](../docs/decisions/anh-gemini-01.md) | Không | Khóa API và địa chỉ proxy đặt trên máy có Zalo |
| PR-4b | B4 trên `hao`: trang Thu chi đọc `money-reads.json` | Không | — (số chỉ hiện khi máy Zalo bật `money_images` và `--reads-target`) |

- Agent: claude ([`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md)).
- Review: opus cho PR-3 (DB, quyền), sonnet medium cho các PR còn lại.
- Ngân sách: mỗi PR ≤ 600 dòng logic.
- Lệnh kiểm: `npm run check`; PR-3 thêm harness `tools/test_pg_*.py`.
- Cấm:
  - ghi tiền theo tin chat;
  - gắn đối tượng khi khớp nhiều hơn một;
  - đưa nội dung chat vào model;
  - gửi ảnh ra ngoài;
  - đổi Tailscale, pg_hba hay quyền ngoài runbook;
  - đưa tên khách, số tiền thật, biển số thật hay tin nhắn thật vào repo.

## Ngoài phạm vi

- **Bot trả lời trong nhóm** (ví dụ @bot "thu chi hôm nay"). Xét khi Zalo Bot chính thức mở hẳn phần nhóm; đọc vẫn qua đường này, bot chỉ để trả lời.
- **WeChat.** Tạm thời chuyển tiếp ảnh sang nhóm Zalo. Nếu đối tác Trung Quốc nhiều thì xét WeChat Work riêng.
- **Sao kê hoặc biến động ngân hàng** ([Q7](#câu-hỏi-đã-chốt)).
- **Sổ chi văn phòng, lương:** web chưa có sổ này. Phần B chỉ liệt kê các khoản đó (`NO_LEDGER`).

## Hoàn tác

- **PR-1:** gỡ tiến trình `watch`, bật lại task `WebdebitZaloSync` 15 phút; revert code. Gói vẫn đọc được vì thiếu delta thì chỉ đọc gói gốc.
- **PR-2:** revert, không đụng dữ liệu.
- **PR-3:** revert app; bảng giữ lại hoặc `DROP` theo nhật ký triển khai, không gì trong đường tiền tham chiếu tới.
- **PR-4:** tắt OCR trong `watch`.

## Bằng chứng

**P0 (20/11/2026, chỉ đọc, chạy ở máy có Zalo).** Chỉ ghi số đếm; nội dung tin, chữ OCR và ảnh nằm ngoài repo, ở máy có Zalo.

1. **Nhóm mang tin tiền (8 tuần):**
   - Kho live-sync có 54 nhóm; khoảng 20 nhóm là nhóm công việc, còn lại là nhóm riêng.
   - Ảnh chuyển khoản tập trung ở **nhóm kế toán đang lên web**: 21/22 ảnh dáng màn hình là ảnh chuyển khoản. Ngoài nhóm đó, mẫu chỉ thấy 5 ảnh chuyển khoản rải ở hai nhóm.
   - Các nhóm nhiều ảnh nhất (tới khoảng 580 ảnh mỗi tuần) là ảnh cont, seal, nhiệt độ: 0 ảnh chuyển khoản trong mẫu.
   - Tin chữ có số tiền (`\d+ ?(tr|triệu|k)`): chỉ một nhóm đáng kể, khoảng 15 tin mỗi tuần. Mẫu `thu|chi` mới có 4 tin.
   - Người dùng xem danh sách và trả lời các nhóm đó không liên quan; giữ nhóm đang lên web, nhóm Thu chi (Q1) chờ lập.
2. **Tải trên `hao` nếu đưa cả 20 nhóm công việc:**
   - 20.158 tin, khoảng 28 MB chữ;
   - `ChatStore` nạp lại 0,78 giây trên máy có Zalo (CPU `hao` nhanh hơn);
   - ảnh đã lưu ở máy khoảng 2 GB toàn lịch sử, `/srv` còn trống khoảng 370 GB.

   A2 không cần đọc gói từng phần.
3. **OCR tại máy (easyocr, CPU):**
   - Lọc theo dáng ảnh màn hình (cao ≥ 1,7 lần rộng), OCR 161 ảnh, nhận ra 26 ảnh chuyển khoản.
   - 20 ảnh mới nhất đều đọc ra một số; người dùng tự chấm trên trang soát tại máy: **đúng 20/20** (ngưỡng 18/20), nên làm B4.
   - Ảnh thường lấy ngẫu nhiên có 1 ảnh chuyển khoản, nên bộ lọc dáng ảnh có thể sót; PR-4 OCR mọi ảnh của nhóm đã chọn.
   - Tốc độ: khoảng 7,5 giây mỗi ảnh với 6 luồng, 14 giây với 2 luồng.
   - Người dùng đổi [`ANH-GEMINI-01`](../docs/decisions/anh-gemini-01.md) sang OCR làm chính, Gemini khi cần.

## Câu hỏi đã chốt

Người dùng chốt cả tám câu theo đề xuất của Claude (chat 19/11/2026, "Chốt theo đề xuất").

- **Q1 — Nhóm nào đưa lên web?** **Sửa 20/11/2026** ([`ZALO-THU-CHI-01`](../docs/decisions/zalo-thu-chi-01.md#sửa-ngày-20112026-không-lập-nhóm-thu-chi)): không lập nhóm Thu chi; nguồn là nhóm và chat riêng 1-1 của khách có ảnh chuyển khoản. Bản chốt đầu: lập **một nhóm Zalo nội bộ "Thu chi"** cho mọi khoản thu chi của công ty. Thêm các nhóm khách hay có ảnh chuyển khoản theo danh sách P0 đưa ra, mỗi nhóm người dùng tự `add`.
- **Q2 — Có bắt gõ theo mẫu không?** **Sửa 20/11/2026:** không bắt; mẫu vẫn được đọc nếu có. Bản chốt đầu: **có** trong nhóm Thu chi (`thu|chi|ứng <số> <đối tượng>`), vì đọc mẫu chắc chắn hơn đọc ảnh. Trong nhóm khách thì không bắt, chỉ đọc ảnh (B4) và dấu tay.
- **Q3 — Ai xem trang Thu chi?** **Chốt:** mọi người vào được web, như các trang khác (Tailscale). Nếu nhóm Thu chi có lương hay chi riêng của sếp thì cần tách quyền; đó là việc lớn hơn, chưa có trong spec.
- **Q4 — Đọc ảnh bằng gì?** **Chốt:** OCR ngay trên máy có Zalo, không gửi ảnh ra ngoài, giữ `CHUNG-TU-01`. Nếu P0 cho thấy OCR đọc kém mà sếp muốn dùng AI ngoài (ví dụ Claude đọc ảnh) thì phải sửa `CHUNG-TU-01` mục 4.
  **Thay ngày 20/11/2026** bởi [`ANH-GEMINI-01`](../docs/decisions/anh-gemini-01.md): OCR tại máy đọc mọi ảnh của nhóm đã chọn (P0: đúng 20/20); ảnh có dấu hiệu tiền mà OCR đọc không chắc mới gửi Gemini qua hai đường (proxy OAuth và API trả phí), hai kết quả khớp mới coi là máy đọc được.
- **Q5 — Máy có Zalo có bật suốt giờ làm việc không?** Real-time chỉ đúng khi máy đó bật. **Chốt:** bật 7:00–20:00. Nếu không bảo đảm được thì cân nhắc một máy riêng luôn bật chỉ chạy Zalo PC.
- **Q6 — Khoảng ngày đối chiếu.** **Chốt:** từ 1 ngày trước tới 3 ngày sau ngày báo, như dấu "Khách báo đã chuyển". Chi Đội xe có thể ghi muộn hơn (theo đợt hoàn), cần người nhập Đội xe xác nhận.
- **Q7 — Có nối ngân hàng không?** Đây mới là nguồn "tiền thật". **Chốt:** **để sau**, spec riêng. Các dịch vụ báo biến động số dư như SePay, Casso cần cấp quyền đọc tài khoản ngân hàng, và chi phí chưa kiểm. Nối ngân hàng cần sếp quyết trong spec riêng.
- **Q8 — Ứng tiền tài xế báo trong nhóm có tách loại riêng không?** **Chốt:** **có** (`ứng`), vì Đội xe tính số dư tài xế bằng chi − hoàn − ứng ([`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md)).

## Câu hỏi mở

- (Agent hoặc reviewer ghi vào đây.)
