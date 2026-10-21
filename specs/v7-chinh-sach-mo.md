# Chính sách V7 còn mở — phương án để chủ nghiệp vụ chọn

Trạng thái: **ĐỀ XUẤT** toàn bộ (Claude soạn 21/10/2026). Tài liệu chỉ bày phương án và khuyến nghị; **chưa điểm nào được chốt**. Chủ nghiệp vụ chọn xong thì quyết định mới ghi vào [`docs/decisions.md`](../docs/decisions.md) bằng một PR riêng, kèm người chốt, ngày, phạm vi. Không sửa code trong PR này.

## Người dùng và luồng

Người đọc là chủ nghiệp vụ. Mỗi điểm có bốn phần đọc theo thứ tự:

1. **Chuyện gì xảy ra** — tình huống thật, viết bằng lời thường.
2. **Các cách làm** — 2–3 phương án, mỗi cách có ví dụ số giả, điểm được, điểm mất.
3. **Khuyến nghị** — cách Claude đề nghị chọn và lý do.
4. **Ảnh hưởng tới mã** — phần dành cho người lập trình: hàm nào đổi, case test nào chuyển trạng thái.

Câu cần trả lời nằm ở [Câu hỏi mở](#câu-hỏi-mở), mỗi điểm một câu. Mọi tên khách, số tiền trong tài liệu là **giả**.

## Đầu ra

Một tài liệu đủ năm điểm còn mở chặn bước đầu (Phase 0) của kế hoạch tới v1: (1) D04 tiền dư, hoàn tiền, chuyển giữa sổ; (2) D05/D06 chứng từ phiếu thu, VND và tỷ giá; (3) D07 nhập muộn, mở lại tháng đã khóa; (4) ai xem Lịch sử; (5) case 7.11c chứng minh bản Sheet nguồn đã đóng băng và nạp đủ. Chủ nghiệp vụ trả lời năm câu ở cuối thì người lập trình có đủ căn cứ để viết spec triển khai và chuyển các case `SKIPPED_OPEN` sang `BEHAVIOR`.

## Đối chiếu dữ liệu và code hiện có

Trạng thái mã V7 trên `main` tại `af2091a` (thiết kế `specs/v7-backend/schema-draft.sql`, thân hàm `cong-no-web-handoff/tools/v7_backend_functions.sql`; cả hai vẫn là ĐỀ XUẤT, chưa chạy trên `hao`):

| Việc | Mã hiện làm gì |
| --- | --- |
| Khách trả dư | `record_receipt` trừ nợ cũ trước; phần dư thành dòng `receipt_line.kind = 'advance'` ở tháng cuối của sổ, trả về `overpayment_vnd`. Sổ hiện số âm. |
| Dư trừ dần vào chuyến sau | `paste_trips`, `edit_trip_price`, `adjust_*` gọi `reallocate`: rải lại mọi phiếu chưa hủy theo nợ cũ trước, nên phần dư tự trừ vào chuyến mới. |
| Cấn trừ hai sổ (CT-2SO) | `record_offset`: phiếu `CẤN TRỪ` ở sổ nhận + khoản "cấn trừ đi" ở sổ nguồn (`offset_pair`, view `v_offset_outgoing`), chặn khi vượt số dư (`OFFSET_EXCEEDS_CREDIT`). |
| Hoàn tiền | **Không có hàm.** |
| Chuyển nợ giữa hai sổ | **Không có hàm.** Chỉ làm được bằng hai lần `adjust_month` rời nhau. |
| Chứng từ phiếu thu | `receipt` có ngày, hình thức, số tiền; **không có ô tham chiếu, không có ảnh**. |
| Tiền tệ | Mọi cột tiền là `bigint` VND; không có cột ngoại tệ/tỷ giá. |
| Khóa tháng | `set_month_lock` ai cũng gọi được; `month_state` chỉ giữ người đổi **lần cuối**; không ghi `event`. `paste_trips`, `edit_trip_price` gặp tháng khóa thì báo `MONTH_LOCKED`. |
| Lịch sử | `get_ledger` trả `events` (người làm, lúc nào, trước → sau) cho cả `sokhach_app` và `sokhach_reader`. |
| Gate nguồn | `cutover.source_sha256` là SHA-256 của `manifest.json`; `cutover_customer.source_rows` đếm chính dữ liệu gửi vào. DB không biết có sót cả một khách hay sót dòng trước khi gửi. |

Ba case đang bỏ qua vì chính sách chưa chốt:

| Case | File | Lý do bỏ qua ghi trong mã |
| --- | --- | --- |
| `7.11c` | `cong-no-web-handoff/tools/test_pg_v7_backend.py` | Chưa chứng minh được bản nguồn đóng băng đủ dòng, đủ khách. |
| `7.15c` | `cong-no-web-handoff/tools/test_pg_v7_backend.py` | Chuyển âm giữa sổ và hoàn tiền chưa có chính sách. |
| `policy.refund_transfer` | `cong-no-web-handoff/tools/test_pg_v7_p0_harness.py` | D04 hoàn tiền/tiền dư chưa có chính sách; CT-2SO là hợp đồng riêng. |

## Nguồn quyết định

- [Gate chưa đóng](../docs/decisions.md#gate-chưa-đóng): D04, D05/D06, D07, ai xem lưu vết — CÒN MỞ.
- Đã chốt, các phương án dưới đây không được trái: `V6-DB` (không người duyệt thứ hai), [`V7-SO`](../docs/decisions.md#v7-so) (ổ khóa từng tháng, điều chỉnh không cần lý do, hủy phiếu bắt buộc lý do, dư ghi trong sổ hiện số âm, mở/khóa không ghi Lịch sử), [`V7-ID`](../docs/decisions.md#v7-id) (danh tính Tailscale, bản thử không phân quyền), [`V7-BE`](../docs/decisions.md#v7-be) (6) (thu mới bỏ qua tháng âm), `CT-2SO` (cấn trừ hai sổ), [`SONG-SONG-01`](../docs/decisions.md#song-song-01) (Sheet là sổ chính thức tới ngày chuyển hẳn), [`V7-TONG`](../docs/decisions.md#v7-tong) (tab không có tên trên `TONG` bị loại).
- Thiết kế: [`specs/v7-backend/thiet-ke.md`](v7-backend/thiet-ke.md) mục 7.11, 7.15 và mục 8; [`specs/m2-tieu-chi-v7.md`](m2-tieu-chi-v7.md) bảng "Gate còn mở"; [`specs/can-tru-hai-so.md`](can-tru-hai-so.md).

---

## Điểm 1 — Tiền dư, hoàn tiền, tiền chưa rõ của ai, tranh chấp, chuyển giữa hai sổ (D04)

### Chuyện gì xảy ra

Ví dụ chung cho cả điểm này: sổ **Khách A · sầu riêng** nợ tháng 9 là 30.000.000, tháng 10 là 20.000.000, tổng 50.000.000.

- **Trả dư.** Ngày 25/10 Khách A chuyển 70.000.000. Trừ hết nợ còn dư 20.000.000. Đã chốt: dư nằm trong sổ, sổ hiện **−20.000.000**. Phần còn mở là dư đó **đi đâu tiếp**.
- **Hoàn tiền.** Khách A xin trả lại 20.000.000 dư. Mình chuyển khoản trả lại. Trên web chưa có chỗ ghi việc này, nên sổ vẫn hiện −20.000.000 dù tiền đã trả.
- **Tiền chưa rõ của ai.** Sao kê có khoản 15.000.000 nội dung chỉ ghi "CK", chưa biết của khách nào.
- **Tranh chấp.** Khách A không nhận một chuyến 8.000.000 hoặc cãi giá, chưa ngã ngũ.
- **Chuyển giữa hai sổ mà không phải cấn trừ.** Ví dụ ghi nhầm khoản thu vào sổ khác; hoặc nợ của sổ cũ chuyển sang sổ mới vì khách đổi tên, gộp sổ, người khác nhận nợ thay. Cấn trừ (lấy tiền dư sổ này trả nợ sổ kia) đã chốt riêng ở `CT-2SO`, không bàn lại ở đây.

### Các cách làm

**1a. Dư đi đâu**

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | Như mã hiện nay: dư tự trừ vào chuyến sau. | Ngày 5/11 có chuyến 12.000.000 → sổ còn −8.000.000. | Giống Sheet: dư "ăn" dần vào nợ mới. Không thêm thao tác. Không đổi mã. | Không giữ dư riêng cho một mục đích (ví dụ khách dặn "để dành cho lô xoài"). |
| **B** | Dư đứng riêng; chỉ trừ khi người dùng bấm "dùng tiền dư". | Chuyến 12.000.000 vào → sổ nợ 12.000.000 và dư 20.000.000 cùng lúc, cho tới khi bấm. | Kiểm soát từng lần dùng dư. | Khác Sheet; số "còn phải thu" mất nghĩa một con số; thêm nút, thêm hàm. |

**1b. Hoàn tiền**

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | Dòng mới **"Trả lại khách"** trong khối TIỀN KHÁCH TRẢ, số âm, cùng tháng ngày trả. Chặn khi vượt số dư (như sổ nguồn của cấn trừ). Có mã phiếu `PH-` riêng, hủy bắt buộc lý do như phiếu thu. | Sổ −20.000.000, ghi "Trả lại khách 20.000.000" ngày 28/10 → sổ về 0. Gõ 25.000.000 thì báo "Sổ chỉ còn dư 20.000.000". | Đúng việc thật; không thể trả quá số dư; Lịch sử ghi rõ "trả lại". Dùng lại khuôn của cấn trừ, ít mã mới. | Thêm một loại dòng và một hàm ghi. |
| **B** | Dùng **dòng điều chỉnh tháng** +20.000.000, ghi chú "hoàn tiền". Làm được ngay hôm nay. | Điều chỉnh tháng 10 +20.000.000 → sổ về 0. | Không đổi mã. | Không chặn trả quá; lẫn với điều chỉnh giá; đối soát ngân hàng khó tìm. |
| **C** | Không ghi hoàn tiền trên web; Sheet ghi. | Sổ web vẫn −20.000.000. | Không làm gì. | Web lệch Sheet ở mỗi lần đối soát theo `SONG-SONG-01`; chuyển hẳn thì sai số. |

**1c. Tiền chưa rõ của ai**

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | Chưa rõ khách thì **chưa ghi lên web**; theo dõi ngoài (Sheet/sổ tay) tới khi rõ rồi ghi vào đúng sổ. | 15.000.000 "CK" nằm ngoài web; 30/10 biết là Khách B → ghi phiếu thu ở sổ B ngày tiền về. | Không có sổ "rác"; không đổi mã; hợp thời gian chạy song song (Sheet là sổ chính thức). | Web không nhắc khoản treo; phải nhớ ở chỗ khác. |
| **B** | Một **sổ "Tiền chờ xác định"** trên web, không thuộc khách nào, không tính vào nợ khách; rõ khách thì cấn trừ sang sổ đúng. | Ghi 15.000.000 vào sổ chờ → sổ chờ −15.000.000; sau dùng cấn trừ chuyển sang sổ B. | Thấy được mọi khoản treo trên web. | Thêm sổ đặc biệt, phải loại khỏi thống kê khách; đụng `V7-TONG` (sổ không có trên `TONG`). |

**1d. Tranh chấp**

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | Vẫn tính nợ; ghi chú trên chuyến. Ngã ngũ mà giảm thì sửa giá (tháng mở) hoặc điều chỉnh (tháng khóa) như `V7-SO`. | Chuyến 8.000.000 vẫn trong nợ; sau giảm còn 5.000.000 → điều chỉnh −3.000.000. | Giống Sheet; không đổi mã (chuyến đã có ô `note`). | Không lọc nhanh được "chuyến đang cãi". |
| **B** | Như A, thêm **cờ "đang tranh chấp"** chỉ để tô màu và lọc, không đổi tiền. | Chuyến 8.000.000 tô màu, vẫn trong nợ. | Thấy ngay chuyến đang cãi. | Thêm cột, thêm lệnh bật/tắt cờ. |
| **C** | Đưa chuyến tranh chấp **ra ngoài số dư** (như thiếu giá) tới khi xong. | Sổ còn 42.000.000 thay vì 50.000.000. | Số dư chỉ gồm nợ "chắc". | Lệch Sheet; dễ quên đưa lại vào; thêm trạng thái tiền mới. |

**1e. Chuyển giữa hai sổ mà không phải cấn trừ**

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | Dùng công cụ sẵn có. Ghi nhầm sổ: hủy phiếu (có lý do) rồi ghi lại đúng sổ. Chuyển nợ: điều chỉnh −X ở sổ cũ và +X ở sổ mới, ghi chú tên sổ bên kia. | Nợ 10.000.000 sổ A chuyển sang sổ C: A điều chỉnh −10.000.000, C điều chỉnh +10.000.000. | Không đổi mã. Đối soát theo tổng từng khách (`SONG-SONG-01`) sẽ lộ nếu quên một bên. | Hai thao tác rời nhau, có thể quên một bên. |
| **B** | Lệnh **"Chuyển nợ"** ghi cả hai sổ một lần (như cấn trừ), hủy thì hủy cả cặp. | Một lệnh: A −10.000.000, C +10.000.000. | Không thể lệch một bên. | Thêm hàm, bảng cặp, màn hình, mockup; việc này hiếm. |
| **C** | Không cho chuyển nợ trên web; gộp sổ hoặc đổi tên là việc **chuyển dữ liệu** làm ở mốc nạp. | Gộp sổ chờ lần nạp sau. | Không có đường ghi mới. | Phải chờ; giữa chừng hai sổ vẫn rời. |

### Khuyến nghị

**1a-A, 1b-A, 1c-A, 1d-A, 1e-A.**

- 1a-A: đúng cách Sheet đang làm, mã đã làm, test 7.02b đã kiểm.
- 1b-A: hoàn tiền là tiền ra thật, cần chặn trả quá như cấn trừ. Dùng điều chỉnh (B) thì không chặn được, lại lẫn với sửa giá. Dòng "Trả lại khách" là nửa bên nguồn của cấn trừ mà không có sổ nhận, nên mã mới ít.
- 1c-A: trong thời gian chạy song song Sheet vẫn là sổ chính thức, khoản treo nằm ở Sheet là đủ. Xem lại khi chuyển hẳn.
- 1d-A và 1e-A: hiếm, đã làm được bằng công cụ có sẵn, đối soát theo khách sẽ bắt lỗi quên một bên. Nếu một tháng gặp nhiều lần thì làm 1d-B hoặc 1e-B sau.

### Ảnh hưởng tới mã

Chỉ phương án được chọn mới làm; cần spec triển khai riêng trước khi viết DDL.

| Phương án | Thay đổi | Case test |
| --- | --- | --- |
| 1a-A | Không. | Giữ 7.02b, 7.15b. |
| 1b-A | `schema-draft.sql`: bảng `sokhach.refund` (khách, `pid`, ngày, `amount_vnd > 0`, lý do hủy, event tạo/hủy), view tiền ra gộp `v_offset_outgoing` + hoàn tiền; `v_outstanding_month` và `event.kind` thêm loại `refund`. `v7_backend_functions.sql`: hàm mới `record_refund`, `void_refund` (lý do bắt buộc); `reallocate`, `record_receipt` (tìm tháng cuối), `get_ledger` cộng thêm khoản hoàn; `GRANT EXECUTE` cho `sokhach_app`. | `7.15c` và `policy.refund_transfer`: `SKIPPED_OPEN` → `BEHAVIOR` (hoàn trong số dư đạt; vượt số dư bị chặn; hoàn ở tháng khóa; hủy hoàn trả sổ về số trước; tổng tiền ra = tổng hoàn; hai kết nối hoàn đồng thời không vượt dư; retry cùng khóa). |
| 1b-B | Không đổi hàm. | `7.15c`, `policy.refund_transfer` đổi lý do: "hoàn tiền ghi bằng điều chỉnh" và thêm case kiểm điều chỉnh mang ghi chú; **không** có chặn vượt dư để kiểm. |
| 1c-B | Cờ "sổ chờ xác định" trên `customer`, loại khỏi `list_customers`/thống kê, chặn chuyến trên sổ đó. | Case mới cho sổ chờ. |
| 1d-B | Cột cờ trên `trip` + lệnh bật/tắt có event. | Case mới. |
| 1e-B | Bảng cặp + `record_transfer`/`void_transfer` theo khuôn `record_offset`. | Phần "chuyển âm giữa sổ" của `7.15c`. |
| 1e-A, 1e-C | Không. | Phần "chuyển âm giữa sổ" của `7.15c` ghi là đã phủ bởi `CT-2SO` (cấn trừ) + công cụ sẵn có; bằng chứng là các case `CT-2SO.*` trong `test_pg_v7_backend.py`. |

---

## Điểm 2 — Phiếu thu cần chứng từ gì; VND và tỷ giá (D05/D06)

### Chuyện gì xảy ra

- **Chứng từ.** Ngày 15/11 ghi phiếu thu 50.000.000, hình thức `THU TIỀN`. Hai tháng sau khách nói chỉ chuyển 45.000.000, hoặc kế toán hỏi "tiền này vào tài khoản nào, giao dịch số mấy?". Hiện phiếu chỉ có ngày, hình thức, số tiền; không có gì để tra lại sao kê. Cũng không phát hiện được khi cùng một giao dịch bị ghi hai lần.
- **Ngoại tệ.** Có khách trả bằng USD hoặc nhân dân tệ (ví dụ 2.000 USD). Ngân hàng đổi ra VND theo tỷ giá ngày đó, số VND vào tài khoản có thể khác số mình tự nhân.

### Các cách làm

**2a. Chứng từ**

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | Không thêm gì, như Sheet. | Phiếu: 15/11 · THU TIỀN · 50.000.000. | Không đổi mã; dán lô từ Sheet không vướng. | Không tra được giao dịch; ghi trùng không ai báo. |
| **B** | Thêm ô **"Tham chiếu"** (số giao dịch ngân hàng, số phiếu…), **không bắt buộc**, sửa tại chỗ được như ngày và hình thức. Trùng tham chiếu trong cùng sổ thì **cảnh báo**, không chặn. | Phiếu: 15/11 · THU TIỀN · 50.000.000 · `GD-000123`. Ghi lần hai cùng `GD-000123` → "Tham chiếu này đã có ở PH-012". | Tra được sao kê; bắt được ghi trùng; không chặn khi Sheet không có số giao dịch. | Ô trống thì vẫn như A. |
| **C** | Tham chiếu **bắt buộc** với `THU TIỀN`, kèm **ảnh chứng từ** (ảnh chụp sao kê/ủy nhiệm chi) lưu trên máy chủ. | Không có số giao dịch hoặc ảnh → không ghi được phiếu. | Đủ chứng cứ nhất. | Dán lô từ Sheet bị chặn khi Sheet không có số giao dịch; ảnh chứng từ ngân hàng là dữ liệu nhạy cảm, phải lo chỗ lưu, sao lưu, quyền xem; nhiều việc. |

**2b. VND và tỷ giá**

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | **Chỉ ghi VND**, đúng số VND thực vào tài khoản. Ngoại tệ, tỷ giá ghi vào ô tham chiếu/ghi chú cho người đọc, không tính. | Khách trả 2.000 USD, ngân hàng báo có 50.600.000 → ghi 50.600.000; tham chiếu "2.000 USD @ 25.300". | Số trên sổ khớp sao kê VND; không đổi mã tiền; giữ VND nguyên chính xác. | Không thống kê được theo ngoại tệ. |
| **B** | Ghi thêm số ngoại tệ và tỷ giá thành ô riêng (chỉ xem); VND vẫn là số tính nợ, người ghi gõ. | 2.000 USD · 25.300 · 50.600.000. | Có số liệu ngoại tệ có cấu trúc. | Thêm ba cột; tỷ giá × ngoại tệ có thể lệch VND thực nhận (phí ngân hàng), phải quy định lệch thì tin số nào. |
| **C** | Sổ đa tiền tệ, hệ thống tự quy đổi theo tỷ giá ngày. | Hệ thống tự tính VND. | — | Trái quy tắc "VND nguyên, server không đoán"; nặng; không khuyến nghị. |

### Khuyến nghị

**2a-B và 2b-A.** Ô tham chiếu không bắt buộc cho tra cứu và bắt ghi trùng mà không làm vướng việc dán lô từ Sheet trong thời gian chạy song song. Không lưu ảnh ở v1 vì đó là chứng từ ngân hàng nhạy cảm; ảnh vẫn ở chỗ đang lưu hiện nay. Khi chuyển hẳn có thể xét lại việc bắt buộc tham chiếu cho `THU TIỀN`. Chỉ ghi VND thực nhận vì số đó khớp sao kê, và ngoại tệ đã có lối "Ngoài sổ" của cấn trừ cho khoản phải trả bằng USD.

### Ảnh hưởng tới mã

D05/D06 không có case `SKIPPED_OPEN`; phương án chọn tạo case mới.

| Phương án | Thay đổi | Case test |
| --- | --- | --- |
| 2a-A, 2b-A | Không. | Không. |
| 2a-B | `schema-draft.sql`: `receipt.ref text` (NULL hoặc không rỗng), chỉ mục không duy nhất `(customer_id, ref)`. `v7_backend_functions.sql`: `record_receipt` thêm tham số `ref` (vào payload idempotency và `event.after`), `edit_receipt_meta`/`_edit_receipt_meta` cho sửa `ref` có event trước → sau, `record_offset` truyền `ref`, `get_ledger` trả `ref` và cờ trùng; đổi chữ ký nên sửa dòng `GRANT EXECUTE`. API `web/v7_ledger_api.py` và model JS nối sau (đang có phiên khác sửa API, làm sau khi phiên đó xong). | Case mới `BEHAVIOR`: lưu và sửa tham chiếu có vết; trùng tham chiếu chỉ cảnh báo; retry cùng khóa khác tham chiếu bị từ chối (`7.04`). |
| 2a-C | Như 2a-B + chặn `ref` NULL khi `THU TIỀN`; bảng/kho file đính kèm, quyền xem, sao lưu. | Như trên + case chặn thiếu tham chiếu. |
| 2b-B | `receipt` thêm `currency`, `foreign_amount_minor bigint`, `rate`, quy định khi lệch. | Case mới. |

---

## Điểm 3 — Nhập muộn, mở lại tháng đã khóa (D07)

### Chuyện gì xảy ra

Đã chốt (`V7-SO`): mỗi tháng có ổ khóa; mặc định chỉ tháng hiện tại mở; ai cũng mở/khóa được; mở/khóa **không** ghi Lịch sử; tháng khóa muốn sửa số thì sinh dòng điều chỉnh.

- **Nhập muộn.** Ngày 3/11 mới có phiếu cân của chuyến xe nhập kho 30/10, 9.000.000, phải vào tháng 10. Từ 1/11 tháng 10 tự khóa, dán chuyến vào tháng 10 sẽ báo "tháng đã khóa". Muốn dán phải mở tháng 10, dán, rồi khóa lại.
- **Mở lại tháng cũ.** Ai đó mở tháng 3 (đã đối chiếu xong với khách), sửa đè giá, rồi khóa lại. Việc sửa giá có trong Lịch sử, nhưng việc **ai mở tháng 3, lúc nào** thì không; máy chỉ nhớ người đổi khóa lần cuối.
- **Ảnh hưởng số cuối tháng.** Thêm chuyến vào tháng 10 thì các phiếu thu được rải lại theo nợ cũ trước, nên "còn phải thu cuối tháng 10" đổi, kể cả khi đã báo số đó cho khách.

### Các cách làm

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | Giữ như đã chốt: ai cũng mở/khóa, không ghi Lịch sử. Nhập muộn = mở → dán → khóa. | 3/11 mở tháng 10, dán chuyến 9.000.000, khóa. Lịch sử chỉ có dòng "dán chuyến". | Không đổi mã; đơn giản nhất. | Không biết ai mở tháng cũ, mở lúc nào; quên khóa lại cũng không ai biết. |
| **B** | Ai cũng mở/khóa như cũ, nhưng **mỗi lần mở/khóa ghi một dòng Lịch sử** (người, lúc, tháng, mở hay khóa). Nhập muộn vẫn mở → dán → khóa. | Lịch sử: "3/11 09:02 · Người X · mở tháng 10", "09:03 · dán 1 chuyến 9.000.000", "09:04 · khóa tháng 10". | Có vết đầy đủ để đối soát; không cần phân quyền (chưa có danh tính tin cậy); ít mã. | Đổi một vế của `V7-SO` (mở/khóa không ghi Lịch sử) — vế này chính `V7-SO` đã ghi "cân nhắc lại khi có kiểm toán". Lịch sử dài thêm. |
| **C** | Như B, thêm **giới hạn người**: tháng liền trước ai cũng mở được; tháng cũ hơn chỉ chủ nghiệp vụ mở. | Người X mở tháng 3 → "Chỉ chủ nghiệp vụ mở được tháng này". | Chặn sửa nhầm tháng đã đối chiếu. | Cần danh sách người và vai trò, mà cách đọc danh tính Tailscale tin cậy còn mở (`V7-ID`); trái "bản thử không phân quyền". |

### Khuyến nghị

**B.** Không cần phân quyền mới, chỉ thêm vết, nên không vướng `V7-ID`. Trong thời gian chạy song song, mỗi lần web lệch Sheet phải tra được tháng nào đã bị mở lại. C để sau khi có danh tính tin cậy và có người ngoài nhóm dùng web. Tháng đã báo số cho khách mà phải thêm chuyến muộn thì vẫn làm được; Lịch sử cho biết vì sao số cuối tháng đổi.

### Ảnh hưởng tới mã

D07 không có case `SKIPPED_OPEN`; case 7.08 mở rộng.

| Phương án | Thay đổi | Case test |
| --- | --- | --- |
| A | Không. | Giữ 7.08. |
| B | `schema-draft.sql`: `event.kind` thêm `month_lock` (`before`/`after` có `month`, `locked`), sửa chú thích bảng `event` và `month_state` ("mở/khóa không ghi event" bỏ đi). `v7_backend_functions.sql`: `set_month_lock` ghi event trong cùng giao dịch, kể cả khi đổi về đúng mặc định; `get_ledger` hiện các event đó. Không đổi `_month_open`. Cập nhật luật `V7-SO` trong `docs/decisions.md` (PR riêng). | 7.08 thêm assert: mỗi lệnh mở/khóa có đúng một event, actor từ phiên; retry cùng khóa không nhân đôi event; mở → dán → khóa cho ba event theo thứ tự. |
| C | Như B + bảng vai trò, kiểm vai trò trong `set_month_lock`, nguồn danh tính tin cậy. | Như B + case từ chối người không có vai trò; phụ thuộc gate `V7-ID`. |

---

## Điểm 4 — Ai được xem Lịch sử ai sửa gì

### Chuyện gì xảy ra

Mỗi lần sửa giá, điều chỉnh, ghi hay hủy phiếu, web ghi: ai làm, lúc nào, số trước → số sau. Câu hỏi là **ai được xem** ngăn Lịch sử đó. Ví dụ: Người X sửa giá một chuyến từ 9.000.000 xuống 8.500.000. Người Y (cùng nhóm) mở sổ có thấy dòng "Người X sửa 9.000.000 → 8.500.000" không? Sau này nếu có người chỉ được xem sổ (kế toán ngoài, người kiểm toán), họ có thấy không?

Hiện tại: ai vào được app thì thao tác được (`V7-ID`), và mã đang trả Lịch sử cho mọi người mở sổ, kể cả vai trò chỉ đọc. Tài liệu tiêu chí M2 dặn không được tự suy "ai cũng thao tác" thành "ai cũng xem vết", nên cần chủ nghiệp vụ nói rõ.

### Các cách làm

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | **Ai mở được sổ thì xem được Lịch sử của sổ đó**, kể cả người chỉ xem. | Y và kế toán ngoài đều thấy "Người X sửa 9.000.000 → 8.500.000". | Minh bạch, ai sửa sai cũng thấy ngay; không đổi mã. | Người ngoài nhóm cũng thấy tên người sửa và mọi lần sửa. |
| **B** | Người **thao tác** xem được Lịch sử; người **chỉ xem** (nếu sau này có) chỉ thấy số. | Y thấy; kế toán ngoài chỉ thấy số dư và các dòng. | Giữ chuyện nội bộ trong nhóm. | Thêm một hàm đọc riêng; hiện chưa có người chỉ xem nên chưa thấy lợi ngay. |
| **C** | Chỉ **chủ nghiệp vụ** xem Lịch sử. | Y không thấy dòng của X. | Kín nhất. | Cần phân quyền theo người, vướng `V7-ID`; người sửa không tự kiểm lại được việc mình làm. |

### Khuyến nghị

**A cho tới ngày chuyển hẳn**, xét lại khi có người dùng chỉ xem. Nhóm hiện chỉ gồm người nội bộ vào qua Tailscale, và ai cũng thao tác được, nên giấu Lịch sử với nhau không bảo vệ thêm gì. Ngược lại, thấy được vết giúp mỗi người tự soát việc mình và việc người khác trong lúc chạy song song. Nếu sau này mở cho người ngoài chỉ xem, chuyển sang B; mã B nhỏ.

### Ảnh hưởng tới mã

Không có case `SKIPPED_OPEN`; đóng dòng "Ai xem lưu vết — CÒN MỞ" của `specs/m2-tieu-chi-v7.md` (M2-12).

| Phương án | Thay đổi | Case test |
| --- | --- | --- |
| A | Không đổi hàm (`get_ledger` đã trả `events` cho `sokhach_app` và `sokhach_reader`). | 7.09c thêm assert: phiên `sokhach_reader` đọc được `events` đầy đủ actor/trước/sau. |
| B | `get_ledger` bỏ `events`; hàm mới `get_history(customer_id)` chỉ `GRANT` cho `sokhach_app`. UI V7 đọc Lịch sử qua hàm mới. | `test_pg_v7_grants.py`: reader gọi `get_history` bị từ chối; app gọi được; `get_ledger` không còn `events`. |
| C | Như B + kiểm vai trò người trong `get_history`; phụ thuộc danh tính tin cậy. | Như B + case theo vai trò. |

---

## Điểm 5 — Chứng minh bản Sheet nguồn đã đóng băng và nạp đủ khách, đủ dòng (case 7.11c)

### Chuyện gì xảy ra

Ngày bắt đầu chạy song song, Sheet được xuất ra file, chạy công cụ làm sạch, rồi nạp lên web làm số dư đầu (`SONG-SONG-01`). Cần trả lời chắc hai câu:

1. **File nạp có đúng là Sheet lúc mốc không?** Sheet đổi hằng ngày. Nếu sau này có người hỏi "web lấy số từ bản nào", phải chỉ ra được đúng bản đó và chứng minh nó chưa bị sửa.
2. **Có sót khách hay sót dòng không?** Đã từng xảy ra (ghi ở `MOC-CHUYEN-MOI`, 20/10): bộ tách bỏ sót dòng chuyến ở những tab có thêm một cột nhãn đầu. **Số dư vẫn khớp** vì số dư lấy từ dòng tổng của tab, nhưng danh sách chuyến thiếu, nên kiểm trùng chuyến mới (`NEWTRIP-01`) có thể để lọt chuyến nhập hai lần.

Hiện tại: web nhận mã kiểm (SHA-256) của file `manifest.json`, giờ đóng băng, tổng tiền kiểm, và số dòng do chính công cụ nạp đếm. Web **không biết** được một khách bị bỏ hẳn, hay một dòng bị rơi trước khi gửi vào, vì mọi con số kiểm đều do cùng một công cụ đưa ra.

### Các cách làm

Ví dụ chung (số giả): bản mốc có 100 khách trên `TONG`, tab Khách A có 85 dòng chuyến và thu.

| | Cách | Ví dụ | Được | Mất |
| --- | --- | --- | --- | --- |
| **A** | Giữ như tổng duyệt 21/10: công cụ làm sạch tự kiểm tổng từng tab và tổng toàn bộ; báo cáo đối soát lưu ngoài Git; web chỉ kiểm tổng tiền gửi vào. | Tab Khách A rơi 1 dòng, tổng tab vẫn đúng → **không ai biết**. | Không đổi mã. | Đúng kiểu lỗi đã gặp ngày 20/10 lọt qua được. Case 7.11c vẫn bỏ qua, phải ghi là người dùng chấp nhận loại khỏi phạm vi. |
| **B** | **Niêm phong file + danh mục kiểm độc lập trong web.** (1) Giờ mốc: tải file xlsx từ Sheet, đặt tên phiên bản trong "Lịch sử phiên bản" của Google Sheet (ví dụ "MOC V7"). (2) Công cụ tính mã kiểm của chính file xlsx và ghi vào manifest. (3) Một bộ đếm **thứ hai**, quét mọi ô có dữ liệu, không dùng bộ tách, ra danh sách khách trên `TONG` và số dòng từng tab. (4) Web nhận danh mục này trước, khóa lại, rồi mới nhận từng khách. Khi kiểm, web so: mọi khách trên danh mục đều đã nạp (hoặc có lý do loại theo `V7-TONG`), không có khách lạ; số dòng nạp + cách ly + bỏ có lý do = số dòng danh mục. | Danh mục ghi tab Khách A 85 dòng; bộ tách chỉ ra 84 → web từ chối kiểm khách A, báo "thiếu 1 dòng". Thiếu khách thứ 100 → không kích hoạt được mốc. | Bắt được đúng lỗi 20/10; chỉ ra được bản nguồn bằng file + mã kiểm + tên phiên bản Google; người dùng tự làm bước (1) không cần kỹ thuật. Case 7.11c thành `BEHAVIOR`. | Thêm bảng, hàm và một bộ đếm thứ hai. Web vẫn **không tự đọc Sheet**: nó chứng minh hai công cụ độc lập khớp nhau trên một file đã niêm phong, không chứng minh thay Sheet. |
| **C** | Như B, thêm **cộng lại tiền từ từng dòng** trong web: tổng phát sinh, tổng thu mỗi tháng tính từ các dòng đã nạp, thay số tổng do công cụ gửi. | Dòng rơi làm tổng tháng lệch 9.000.000 → chặn. | Bắt cả lỗi rơi dòng lẫn lỗi tiền. | Các ngoại lệ đã chốt (chênh lịch sử 600đ, dòng thiếu giá giữ ô TOTAL, làm tròn được chia lại) làm tổng dòng có thể lệch hợp lệ; phải có danh sách ngoại lệ được phép, phức tạp. |

### Khuyến nghị

**B.** Đây là cách rẻ nhất bắt được đúng lỗi đã xảy ra. Phần "niêm phong" dựa vào file xlsx, mã kiểm và tên phiên bản trên Google Sheet, nên ai cũng kiểm lại được. C để sau khi đã có danh sách ngoại lệ được phép rõ ràng. Nói rõ giới hạn của B: web không chứng minh Sheet đúng; nó chỉ chứng minh hai bộ đếm độc lập cho cùng kết quả trên một file không đổi.

### Ảnh hưởng tới mã

| Phương án | Thay đổi | Case test |
| --- | --- | --- |
| A | Không. | `7.11c` giữ `SKIPPED_OPEN`, lý do đổi thành "người dùng chấp nhận loại khỏi phạm vi" kèm ngày chốt. |
| B | `schema-draft.sql`: `cutover.source_file_sha256` (mã kiểm file xlsx); bảng `sokhach.cutover_manifest_tab` (mốc, tab, tên trên `TONG`, `expected_rows`, `included`/`excluded` + lý do), khóa bằng `guard_cutover_evidence` khi mốc qua `draft`. `v7_backend_functions.sql`: hàm mới `import_cutover_manifest` (chỉ khi mốc `draft`, idempotent); `import_cutover` từ chối khách không có trong danh mục; `_check_cutover_customer` so `source_rows` với `expected_rows`; `_check_cutover` so tập khách đã verify với tập `included`. Công cụ: `v7_export_clean.py` ghi mã kiểm xlsx và chạy bộ đếm quét mọi ô; `v7_load_real_copy.py --from-clean` nạp danh mục trước. | `7.11c`: `SKIPPED_OPEN` → `BEHAVIOR`: thiếu khách → `verify_cutover` bị chặn; khách lạ → `import_cutover` bị chặn; thiếu/thừa dòng → `verify_cutover_customer` bị chặn; sửa danh mục sau verify bị trigger chặn; retry nạp danh mục cùng khóa trả kết quả cũ, khác nội dung bị từ chối. Thêm unittest cho bộ đếm trên file giả có cột nhãn đầu. |
| C | Như B + `_check_cutover_customer` cộng `legacy_row` theo tháng, so với `source_charge_vnd`/`source_receipt_vnd` trừ ngoại lệ trong danh sách được phép. | Như B + case rơi dòng có tiền; case ngoại lệ hợp lệ không chặn. |

---

## Hành vi và bất biến

Mọi phương án trên đều phải giữ:

- VND nguyên chính xác; NULL không phải 0 (ngoại lệ duy nhất đã chốt ở `V7-BE` (1)).
- Không phân bổ lại opening hay dòng lịch sử; thu mới trừ nợ cũ trước, bỏ qua tháng âm.
- Không người duyệt thứ hai (`V6-DB`); mọi thao tác tiền ghi người làm từ phiên phía server, trước → sau.
- Hủy bắt buộc lý do; điều chỉnh không cần lý do (`V7-SO`).
- Cấn trừ hai sổ theo đúng `CT-2SO`, không bàn lại.
- Sheet là sổ chính thức tới ngày chuyển hẳn (`SONG-SONG-01`); không phương án nào ghi ngược lên Sheet.
- Không đưa ảnh/chứng từ ngân hàng, tên khách, số tiền thật vào repo.

## Tiêu chí nghiệm thu

Cho tài liệu này:

- [x] Đủ năm điểm; mỗi điểm có tình huống bằng lời thường, 2–3 phương án, được/mất, ví dụ số giả, ảnh hưởng mã (hàm, case test), khuyến nghị kèm lý do.
- [x] Mọi mục ghi ĐỀ XUẤT; không sửa `docs/decisions.md`, không sửa code.
- [x] Không có tên khách, số tiền thật, đường dẫn hồ sơ nhạy cảm.
- [x] `npm run check` xanh trên nhánh của PR (máy Windows, 21/10/2026: 7/7 bước OK).

Cho bước sau (khi chủ nghiệp vụ đã chọn): mỗi phương án được chọn có quyết định trong `docs/decisions.md` và spec triển khai riêng; case `7.11c`, `7.15c`, `policy.refund_transfer` hoặc thành `BEHAVIOR` và đạt, hoặc giữ `SKIPPED_OPEN` với lý do "người dùng chấp nhận loại khỏi phạm vi" có ngày.

## Phạm vi agent

- Agent: claude
- Review: opus
- Được sửa:
  - `specs/v7-chinh-sach-mo.md`
  - `specs/README.md`
- Ngân sách diff: 400 dòng
- Lệnh kiểm:
  - `npm run check`
- Cấm:
  - Sửa `docs/decisions.md`, code, schema, test.
  - Chốt hộ chủ nghiệp vụ.
  - Chạm `hao`, DB thật, Sheet.

## Hoàn tác

Revert PR. Không có dữ liệu hay mã bị ảnh hưởng.

## Bằng chứng

Soạn trên `main` tại `af2091a`. Đối chiếu bằng cách đọc `v7_backend_functions.sql` (`record_receipt`, `reallocate`, `record_offset`, `set_month_lock`, `get_ledger`, `_check_cutover_customer`), `schema-draft.sql`, danh sách case trong `test_pg_v7_backend.py` và `test_pg_v7_p0_harness.py`. Không chạy harness PostgreSQL, không đọc dữ liệu thật. Kết quả `npm run check` ghi ở PR.

## Câu hỏi mở

Mỗi điểm một câu. Trả lời "đồng ý" là chọn phương án khuyến nghị; muốn khác thì ghi chữ cái phương án.

1. **Tiền dư, hoàn tiền (D04):** Dư tự trừ vào chuyến sau như hiện nay; hoàn tiền ghi bằng dòng "Trả lại khách" bị chặn khi vượt số dư; tiền chưa rõ của ai thì chưa ghi lên web; chuyến tranh chấp vẫn tính nợ kèm ghi chú; chuyển nợ giữa hai sổ bằng hai dòng điều chỉnh — đồng ý không? *(Khuyến nghị: 1a-A, 1b-A, 1c-A, 1d-A, 1e-A.)*
2. **Chứng từ, tỷ giá (D05/D06):** Phiếu thu có thêm ô "Tham chiếu" không bắt buộc, trùng thì cảnh báo, không lưu ảnh; mọi số tiền chỉ ghi VND thực nhận, ngoại tệ và tỷ giá ghi vào ô tham chiếu — đồng ý không? *(Khuyến nghị: 2a-B, 2b-A.)*
3. **Nhập muộn, mở tháng (D07):** Vẫn ai cũng mở/khóa tháng được, nhưng mỗi lần mở/khóa ghi một dòng Lịch sử (đổi vế "mở/khóa không ghi Lịch sử" của `V7-SO`) — đồng ý không? *(Khuyến nghị: B.)*
4. **Ai xem Lịch sử:** Ai mở được sổ thì xem được toàn bộ Lịch sử của sổ đó, xét lại khi có người chỉ xem — đồng ý không? *(Khuyến nghị: A.)*
5. **Niêm phong bản nguồn (7.11c):** Giờ mốc, người dùng tải file xlsx và đặt tên phiên bản trên Google Sheet; web nhận danh mục khách và số dòng từ một bộ đếm thứ hai, thiếu khách hay thiếu dòng thì không kích hoạt — đồng ý không? *(Khuyến nghị: B.)*
