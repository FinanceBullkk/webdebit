# Chuyến theo nguồn booking: ghép sổ với `CONT_NGUON`, `CONT_BO` và booking 2025

Trạng thái: ĐÃ CHỐT hướng (người dùng, 3/11/2026, [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md)). Bốn giai đoạn dưới đây là ĐỀ XUẤT của Claude, làm theo thứ tự, mỗi giai đoạn một PR. Nối tiếp [P3b](v7-hop-ngoai-le-p3b.md) và `MAY-KHOA-01` ([PR FinanceBullkk/webdebit#282](https://github.com/FinanceBullkk/webdebit/pull/282)).

## Người dùng và luồng

- **Máy** (chạy theo nhịp hộp việc, không hỏi người):
  - ghép từng dòng chuyến của mỗi sổ với các bảng nguồn theo luật (1) của quyết định;
  - điền ngày cho dòng sổ gốc không có ngày như việc A của `MAY-KHOA-01` (cùng container, cùng tháng nợ, đúng một dòng). Khác ở chỗ: nay dòng nguồn có thể đến từ cả `CONT_BO` và booking 2025.
- **Người nhập**, ở Việc cần làm (bảng sổ × loại việc), mỗi sổ có thêm:
  - **"Nghi tính trùng"**: hai dòng trở lên có tiền cùng là một chuyến nguồn. Hiện các dòng, ngày, số tiền, kèm nút mở sổ tại dòng.
    - Dòng thừa thì xóa bằng thao tác xóa đang có.
    - "Giữ" khi đúng là hai khoản, ví dụ cước và phí tách dòng.
  - **"Có trong booking, chưa có trên sổ"**, cho tháng trước 10/2026: chỉ là danh sách để xem, máy không tự đưa vào sổ, vì trước tháng nạp V7 thì sổ gốc là chuẩn (`MAY-KHOA-01`). "Giữ" khi chuyến đã tính ở chỗ khác.
  - **"Ngày khác booking"**: loại này đã có (lệch trường `event_date`). Thêm ngày nguồn bên cạnh, và nút "Lấy theo booking" ở tháng mở.
  - **"Khách khác booking"** (chuyến biển): loại này đã có (`OTHER_CUSTOMER`, `OTHER_BOOK_LEGACY`). Thêm tên khách theo booking.
- **Chủ nghiệp vụ**, một lần: xem danh sách lịch sử 2025 (trùng, chưa có trên sổ) do công cụ GĐ1 xuất, rồi quyết từng nhóm.
- **Điều kiện chặn:**
  - Bản chụp nguồn đọc lỗi hoặc rỗng: không thêm, không bớt việc, giữ kết quả lượt trước.
  - Tháng mà nguồn không phủ: không báo "trên sổ, không có trong nguồn".

Giao diện GĐ4 làm theo skill `thiet-ke-ux` trên khung Việc cần làm đang có. Spec này chỉ chốt loại việc và dữ liệu.

## Đầu ra

Sau GĐ4, mỗi chuyến của sổ trong khoảng có nguồn ở một trong hai trạng thái: đã ghép với đúng một chuyến nguồn, hoặc nằm trong một việc ở hộp ngoại lệ. Ngày chuyến trên web trùng ngày nguồn, trừ chỗ người đã chọn giữ. Số dư mọi sổ không đổi vì luật này.

## Đối chiếu dữ liệu và code hiện có

| Cần | Có sẵn | Thêm |
| --- | --- | --- |
| Đọc `CONT_NGUON` | `webdebit_export_connector.read_source`; `sheet_sync_runner.py --source cont_nguon` ghi `snapshot.json` | Không |
| Đọc `CONT_BO` | Chưa đọc. Tab 24 cột, tiêu đề ở dòng 1: SỐ CONT, SỐ XE, CHỦ HÀNG, CỬA KHẨU, NGÀY ĐÓNG HÀNG, NGÀY KHỞI HÀNH… | Bộ đọc theo tên cột; bản chụp riêng `road.json` |
| Booking 2025 | Chưa có. Tab tháng có vị trí cột khác nhau giữa các tháng, nên phải đọc theo tên cột | Bản chụp một lần `booking-2025.json` |
| Ghép dòng sổ ↔ nguồn | `v7_sheet_queue.project_customer`: `CONT_NGUON` ↔ chuyến web và sổ gốc, ±3 ngày hoặc trùng booking; `MAY-KHOA-01` thêm dòng không ngày cùng tháng | Ghép một-một theo cặp lệch ít ngày nhất; thêm hai nguồn mới, chỉ để so với dòng đã có |
| Đọc sổ gốc từ file tải | `v7_load_real_copy.workbook_rows`, `scan_tabs` | Không |
| Điền ngày | Việc A của `MAY-KHOA-01`: mở khóa, `edit_legacy_trip`, khóa lại; người làm "Máy (theo Sheet)" | Áp thêm cho nguồn mới |
| Giữ việc | `keep_sheet_task` ([`VCL-GIU-01`](../docs/decisions/vcl-giu-01.md)) | Thêm loại việc mới |
| Lấy ngày Sheet khi lệch | `resolve_sheet_conflict` chỉ cho `keep_web` với `event_date`; muốn lấy ngày thì phải sửa tay ở tháng mở | Nút "Lấy theo booking" ở tháng mở (tháng khóa CÒN MỞ) |
| Gom nhóm theo sổ | `v7_inbox.summarize`: phiếu thu, chuyến bị xóa, chuyến mới, chuyến cần kiểm, lệch chữ, giá, PS | `trip_dup`, `source_only` |

## Giai đoạn

### GĐ1 — Công cụ đối soát nguồn (chỉ đọc)

`cong-no-web-handoff/tools/v7_trip_source_match.py`.
- **Đầu vào:** sổ gốc `.xlsx` (tải theo runbook "Đối soát cuối tháng", bước 1) và các bản chụp nguồn.
- **Đầu ra:** số đếm in ra màn hình (không tên khách), và ba file CSV ngoài Git: dòng sổ, dòng nguồn, danh sách cần xem.

Đây là bản sạch, có test, của script đo ngày 3/11. Script gốc và kết quả nằm ngoài Git.

- **Ghép theo luật (1).** Các bảng nguồn có dòng trùng nhau, ví dụ booking 2025 lặp lại tháng 12/2025–02/2026 của `CONT_NGUON`. Dòng cùng container, lệch ≤ 3 ngày thì gom thành một chuyến, bảng mới hơn thắng.
- **Đọc ngày nguồn** theo kiểu ngày trước tháng (đo 3/11: không ô nào có số thứ hai lớn hơn 12). Dạng "dd/mm" không năm chỉ có ở hai tab bộ của booking 2025, năm lấy là 2025.
- **So tên chủ hàng** sau khi bỏ dấu, chữ số và mã HTH/TTH. Ví dụ "NGUYỄN VĂN A" và "NGUYEN VAN A 123" là một chủ hàng.
- **Phân nhóm:**
  - trùng, gồm ba trường hợp:
    - cùng container và cùng ngày, có tiền ở hai dòng trở lên;
    - dòng không ghép được mà ngày của nó cách không quá 3 ngày một chuyến nguồn đã ghép dòng khác;
    - dòng không ghép được mà **đảo ngày/tháng** thì trùng (±3 ngày) một chuyến nguồn đã ghép dòng khác. Phiên khác phát hiện ca này ngày 3/11/2026: một chuyến booking 6/3 được tính ở hai sổ, một sổ ghi 6/3, sổ kia ghi 3/6.
    Dòng còn lại cùng container nhưng xa ngày là container dùng lại, không báo;
  - chưa có trên sổ, tách ba trường hợp: tháng hiện tại; trước khi khách có sổ; chủ hàng chưa ghép được sổ nào;
  - khách khác;
  - không có nguồn;
  - lệch ngày;
  - ngày lấy từ nguồn;
  - giá khác: chữ giá của booking đọc được mà khác tổng trên sổ.

### GĐ2 — Bản chụp nguồn trên `hao`

- **`CONT_BO`:** runner đọc theo tên cột như `CONT_NGUON`; thiếu cột thì dừng với lỗi rõ. Ghi `road.json` (mode 600, cùng thư mục, cùng timer). Dòng thiếu container hoặc ngày là `INVALID`.
- **Booking 2025:** công cụ đọc một lần bằng tài khoản dịch vụ chỉ đọc, ghi `booking-2025.json` kèm sha256. Theo phiên khác, tài khoản này đã đọc được file; nếu không thì người dùng chia sẻ thêm. Chỉ đọc lại khi người dùng báo file đổi.
- **Báo phía Sheet:** giữ `CONT_BO` và dòng tiêu đề hiện có.

### GĐ3 — Ghép trong hộp việc

- **Chiếu từng sổ:** thêm dòng nguồn từ `road.json` và `booking-2025.json` vào phép so với dòng đã có. Hai nguồn này không tạo chuyến mới.
- **Ghép một-một**, cặp lệch ít ngày nhất trước. Giữ các luật đang có (trùng booking thì ghép).
- **Điền ngày** (việc A của `MAY-KHOA-01`): áp cho cả hai nguồn mới.
- **Kết quả mới của mỗi sổ:**
  - `trip_dup`: nhóm dòng có tiền cùng một chuyến nguồn, theo ba trường hợp trùng của GĐ1, kể cả trường hợp đảo ngày/tháng;
  - `source_only`: chuyến nguồn trước 10/2026 không ghép dòng nào, kèm gợi ý sổ.
  - Lệch ngày giữ ở nhóm chuyến cần kiểm như hiện nay.
- **Gợi ý sổ cho chuyến bộ:** sổ mà các chuyến khác cùng CHỦ HÀNG đã ghép nhiều nhất. Chỉ để hiện, không dùng để ghi.

### GĐ4 — Hộp ngoại lệ: hiện và xử lý

- Việc cần làm thêm hai loại: "Nghi tính trùng" và "Có trong booking, chưa có trên sổ". Dòng lệch ngày hiện thêm ngày nguồn.
- "Lấy theo booking" cho lệch ngày ở tháng mở: gọi lệnh sửa ngày đang có (`edit_legacy_trip` hoặc sửa chuyến web), có Lịch sử.
- "Giữ" cho mọi loại mới, theo `VCL-GIU-01`.

### Sau GĐ4 (CÒN MỞ trong quyết định)

- Người bấm lấy ngày ở tháng khóa.
- Máy tự áp ngày nguồn cho dòng đã có ngày.
- Lệnh dời chuyến sang sổ theo booking.
- Chuyến bộ mới tự vào sổ.
- Lịch sử 2024 (chưa có nguồn).

## Nguồn quyết định

- [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md) (quyết định của spec này).
- [`HANG-CHO-01`](../docs/decisions/hang-cho-01.md), `MAY-KHOA-01` (PR FinanceBullkk/webdebit#282), [`KHOA-CHU-01`](../docs/decisions/khoa-chu-01.md): máy tự làm gì, tháng khóa.
- [`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md): tiền theo sổ gốc.
- [`DATE`](../docs/decisions/date.md): ngày xe nhập kho; [`FUTURE-01`](../docs/decisions/future-01.md): không có ngày tương lai.
- [`LEGACY-A`](../docs/decisions/legacy-a.md): chuyến cũ không có nguồn giữ nợ; [`ALT-KEY-01`](../docs/decisions/alt-key-01.md): chuyến bộ không có booking dùng mã container + ngày.
- [`SONG-SONG-01`](../docs/decisions/song-song-01.md): Sheet là sổ chính thức tới ngày chuyển hẳn.

## Hành vi và bất biến

- **Không đổi tiền.** Luật này không ghi đơn giá, phụ phí, phiếu thu hay điều chỉnh. Điền ngày chỉ khi cùng tháng nợ, nên không dời nợ sang tháng khác. Mỗi giai đoạn có ghi phải đo số dư mọi sổ trước và sau trên bản sao DB, hai số phải bằng nhau (như `MAY-KHOA-01`).
- **NULL không phải 0.** Chuyến nguồn chưa có giá không sinh tiền. Chữ giá của booking không ghi vào sổ.
- **Ghép:** một chuyến nguồn ghép nhiều nhất một dòng sổ. Dòng sổ không có ngày chỉ ghép khi cùng tháng và là dòng duy nhất.
- **Ngày nguồn sau hôm nay** (giờ VN) thì không điền ([`FUTURE-01`](../docs/decisions/future-01.md)).
- **Nguồn đọc lỗi hoặc rỗng:** giữ kết quả lượt trước, không báo "không có trong nguồn" hàng loạt.
- **Không ghi Sheet, không nạp lại sổ gốc** (`v7_load*`).
- **Tên khách và số tiền từng khách** chỉ nằm ngoài Git.

## Tiêu chí nghiệm thu

GĐ1:
- [ ] Unit `tests/test_v7_trip_source_match.py`:
  - ghép một-một: cặp lệch ít ngày thắng; container dùng lại lệch hơn 3 ngày không ghép;
  - dòng thứ hai của một chuyến nguồn vào nhóm trùng cả khi lệch 1–3 ngày và khi phải đảo ngày/tháng mới trùng;
  - dòng không ngày ghép khi cùng tháng;
  - gom dòng trùng giữa các bảng nguồn;
  - đọc ngày kiểu ngày trước tháng, và "dd/mm" khi có năm gợi ý;
  - tên chủ hàng bỏ dấu;
  - phân nhóm trùng, chưa có trên sổ, không có nguồn.
- [ ] Chạy trên bản tải ngày 3/11 (ngoài Git) ra lại số của quyết định: 9.416/9.710 dòng khớp từ 01/2025; 28 nhóm trùng cùng ngày; 381 chuyến chưa có trên sổ. Thêm 5 dòng trùng lệch 1–3 ngày và 4 dòng trùng khi đảo ngày/tháng, trong đó có ca phiên khác báo.
- [ ] `npm run check` xanh.

GĐ2:
- [ ] Test bộ đọc `CONT_BO` theo tên cột: đảo cột vẫn đọc được, thiếu cột thì dừng. `road.json` có `runner.created_at` và mode 600.
- [ ] Trên `hao`: bản chụp đầu có số dòng bằng số đo 3/11, cộng chuyến mới. Sha256 của `booking-2025.json` ghi vào nhật ký `docs/deploys/`.

GĐ3:
- [ ] Unit phần chiếu:
  - dòng nguồn bộ và 2025 không tạo chuyến mới;
  - điền ngày theo nguồn mới;
  - phát hiện nhóm trùng;
  - chuyến nguồn chưa có trên sổ chỉ báo cho tháng trước tháng nạp.
- [ ] Trên bản sao DB của `hao`: tổng nợ mọi sổ trước bằng sau; đếm số dòng được điền ngày; mọi tháng máy đã mở đều được khóa lại.

GĐ4:
- [ ] Test trình duyệt Việc cần làm: có hai loại mới; nút mở sổ đúng dòng; "Lấy theo booking" có ở tháng mở và không có ở tháng khóa.
- [ ] Người dùng tự đi hết luồng trên bản thử và xác nhận.

## Phạm vi agent

GĐ1 (các giai đoạn sau ghi phạm vi trong PR của từng giai đoạn):

- Agent: claude (từ 29/10/2026 theo `CLAUDE-ALL-01`)
- Review: opus (dữ liệu tiền, dù chỉ đọc)
- Được sửa:
  - `cong-no-web-handoff/tools/v7_trip_source_match.py`
  - `cong-no-web-handoff/tests/test_v7_trip_source_match.py`
  - `specs/v7-chuyen-theo-nguon.md` (mục Bằng chứng)
- Ngân sách diff: 500 dòng
- Lệnh kiểm: `npm run check`
- Cấm: ghi DB hay Sheet; đổi luật tiền; đưa dữ liệu thật hoặc tên khách vào repo.

## Hoàn tác

- GĐ1, GĐ2: revert PR; xóa `road.json` và `booking-2025.json` trên `hao`.
- GĐ3, GĐ4: revert PR. Ngày đã điền là lệnh `edit_legacy_trip` có Lịch sử: trả lại bằng sửa ngày, giá trị trước nằm trong event `legacy_edit`.

## Bằng chứng

**Đo 3/11/2026, chỉ đọc:**
- Sổ gốc tải trên `hao` (runbook "Đối soát cuối tháng", bước 1); `CONT_NGUON` 5.631 dòng, toàn chuyến BIỂN; `CONT_BO` 2.705 dòng. Hai tab CHAU_HAO đọc trên `hao` bằng tài khoản dịch vụ của runner.
- Booking 2025 đọc qua connector: 8.264 dòng có container, trong đó 8.015 dòng có ngày.
- File tạm trên `hao` đã xóa sau khi chép về và so sha256.

| Phần sổ (theo tháng khối của sổ gốc) | Dòng chuyến | Khớp nguồn: dòng | Khớp nguồn: tiền |
| --- | ---: | ---: | ---: |
| Biển 01–11/2025 | 2.041 | 98,6% | 98,7% |
| Bộ 01–11/2025 | 195 | 86,7% | 93,1% |
| Biển 12/2025–10/2026 | 5.390 | 96,6% | 99,3% |
| Bộ 12/2025–10/2026 | 2.084 | 97,3% | 95,0% |
| Năm 2024 (mọi loại) | 573 | gần 0 | gần 0 (không có nguồn) |

Cặp ghép được mà ô ngày của sổ đọc được: trùng đúng ngày ở 99,2% (biển) và 97,1% (bộ). Script đo, danh sách cần xem và các bản tải (có tên khách) nằm ở `captures/2026-11-03-khop-booking/`, ngoài Git.

## Câu hỏi mở

- File booking 2025: theo báo cáo của phiên khác ngày 3/11/2026, tài khoản dịch vụ của runner trên `hao` đã đọc được file. GĐ2 kiểm lại trước khi dựa vào.
- Có file booking năm 2024 không? Nếu có, phần lịch sử 2024 cũng ghép được.
- Các mục CÒN MỞ của quyết định: hỏi khi tới giai đoạn liên quan.
