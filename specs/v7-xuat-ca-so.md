# Xuất cả sổ web ra bảng tính — đường lui F4 (XUAT-SO-01)

Trạng thái: ĐÃ CHỐT phần người dùng chọn trong chat 18/11/2026 ([`XUAT-SO-01`](../docs/decisions/xuat-so-01.md)): nút tải trên web, bảng gộp lọc theo khách, bản xuất giữ ở `D:\webdebit-du-phong\` trên PC. Phần kỹ thuật dưới đây là ĐỀ XUẤT của Claude. Mục F4 của [checklist chuyển hẳn](../docs/chuyen-han-checklist.md).

## Người dùng và luồng (bước 1, bắt buộc với frontend)

- **Ai:** chủ sổ và người nhập (các login trong danh sách cho phép của [`ACCESS-01`](../docs/decisions/access-01.md)), Chrome trên PC Windows, màn 1280×720.
- **Bối cảnh:** sau ngày chuyển hẳn khỏi Sheet sổ nợ, web là sổ duy nhất. Đường lui là luôn có trên PC một bản cả sổ mở được bằng Excel hoặc Google Sheets, không cần web. Người dùng tự tải định kỳ (gợi ý: cuối ngày làm việc; ít nhất cuối tuần và sau đối soát cuối tháng) rồi cất vào `D:\webdebit-du-phong\`. Web hỏng thì mở bản mới nhất và làm tiếp.
- **Luồng:**
  1. Mở Tổng quan. Thanh đầu trang có nút "Tải cả sổ" (biểu tượng tải xuống), trước đồng hồ và nút làm mới.
  2. Bấm. Nút đổi thành "Đang xuất…" và không bấm lặp được; dưới thanh đầu hiện "Đang xuất cả sổ… thường mất dưới một phút."
  3. Tự kiểm khớp: trình duyệt tải `so-web-YYYYMMDD-HHMM.xlsx` (giờ VN). Dòng trạng thái: "Đã tải `<tên file>`: `<N>` sổ, tự kiểm khớp (tổng các sổ bằng Còn phải thu trên Tổng quan). Cất file vào thư mục dự phòng."
  4. Tự kiểm lệch: file vẫn tải về, tên thêm đuôi `-CO-LECH`, tab KIỂM đứng đầu ghi từng phép kiểm không đạt. Dòng trạng thái màu đỏ nêu các phép kiểm lệch và "File vẫn tải về và đã đánh dấu CO-LECH; báo quản trị kiểm trước khi dùng."
  5. Lỗi: máy chủ không trả lời hoặc DB lỗi thì "Chưa xuất được cả sổ. Thử lại sau ít phút." Đang có lượt xuất khác thì "Đang có một lượt xuất khác. Chờ khoảng một phút rồi bấm lại."
- **Chặn:** như mọi `/api/v7/*`: chỉ login trong danh sách cho phép. Không có quyền riêng: ai mở được sổ thì tải được cả sổ (người dùng chấp nhận khi chọn phương án, 18/11/2026). Mỗi lần tải ghi một dòng vào journal của API: login, số sổ, kết quả kiểm, số byte.
- **Web hỏng mà API còn chạy:** mở thẳng `https://<máy chủ>/api/v7/xuat-so.xlsx` trong trình duyệt; tab KIỂM của file cho kết quả kiểm.

## Đầu ra

Trên Tổng quan có nút "Tải cả sổ". Bấm thì tải về một file xlsx gồm mọi sổ khách, đọc cùng một thời điểm, đã tự kiểm tổng; lệch thì file mang đuôi `-CO-LECH` và trang báo đỏ. Đã chạy thật một lần trên `hao`, tổng khớp, bản lưu ở `D:\webdebit-du-phong\`.

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

**Đọc:** một giao dịch `REPEATABLE READ READ ONLY` (như lưới an toàn) gọi lần lượt `get_dashboard`, `get_dashboard_debt`, `list_customers`, `get_fee_types`, rồi `get_ledger` từng sổ bỏ Lịch sử (`- 'events'`). Mọi con số trong file cùng một ảnh dữ liệu, nên tự kiểm lệch là lệch thật, không phải do có người ghi giữa chừng. Mã sổ lấy trước bằng một lần `list_customers`; trong giao dịch đọc lại, khác (vừa tạo sổ) thì đọc lại cả lượt một lần, vẫn khác thì báo lỗi. Tên hiển thị gắn như `GET /api/v7/customers` (bảng ánh xạ tên). Không thêm hàm SQL, không đổi DB.

| Tab | Một dòng là | Cột | Nguồn trong `get_ledger` |
| --- | --- | --- | --- |
| KIỂM | | Lúc xuất, người tải, số sổ, Còn phải thu và khách trả thừa theo Tổng quan, tổng các sổ, bảng phép kiểm (ĐẠT/LỆCH, chi tiết), cách đọc | `get_dashboard`, `get_dashboard_debt` |
| TỔNG | một sổ | Mã sổ, Tên sổ, Tên hiển thị, Trạng thái (đang dùng / chưa có số dư đầu), Mặt hàng, Biển/Bộ, Nợ còn lại, Tháng nợ cũ nhất còn nợ, Chuyến chưa giá hoặc chờ kiểm | `list_customers`, `total_outstanding_vnd`, `months`, `pending_count` |
| THÁNG | một tháng của một sổ | Mã sổ, Tên sổ, Tháng, Nợ các tháng trước, Phát sinh, Đã thu, Còn nợ cuối tháng, Nợ còn lại của tháng, Số dư đầu khi nạp sổ, Khóa | `months`, `opening`, `month_locks` |
| CHUYẾN | một chuyến web hoặc dòng chuyến sổ gốc | Mã sổ, Tên sổ, Nguồn, Mã dòng, Tháng, Ngày, Container, Booking, Hãng tàu, Shipper, Nơi đi, Nơi đến, Đơn giá, Phụ phí, Thành tiền, Chưa giá, Trạng thái, Các khoản phụ phí, Ghi chú | `trips`, `legacy_rows` loại `trip` (`current`), `fee_lines` + `get_fee_types` |
| PHIẾU THU | một phiếu web, khoản thu sổ gốc hoặc cấn trừ đi | Mã sổ, Tên sổ, Nguồn, Mã phiếu, Ngày, Hình thức, Tham chiếu / ghi chú, Số tiền, Đã hủy (lý do), Cấn trừ với, Trừ vào tháng | `receipts`, `legacy_rows` loại `receipt`, `outgoing_offsets` |
| PHÂN BỔ THU | một dòng chia của phiếu chưa hủy | Mã sổ, Tên sổ, Mã phiếu, Ngày phiếu, Trừ vào tháng, Loại (nợ / ứng trước), Số tiền | `receipts[].allocations` còn hiệu lực |
| ĐIỀU CHỈNH | một dòng điều chỉnh | Mã sổ, Tên sổ, Tháng, Số tiền, Ghi chú, Gắn với (chuyến / dòng sổ gốc / cả tháng), Lúc ghi | `adjustments` |

Thành tiền như web: chuyến web lấy `amount_vnd` (trống khi chưa giá hoặc chưa xác nhận); dòng sổ gốc lấy `counted_vnd`, trống khi chưa có đơn giá và `counted_vnd` là 0 (cùng luật debit note). Tiền là số nguyên VND định dạng `#,##0`; ngày là ô ngày `dd/mm/yyyy`, tháng là ô ngày `mm/yyyy`. Bảng nào cũng có hàng tiêu đề cố định và bộ lọc.

## Giao tiếp frontend–backend (bước 5, khi có)

- `GET /api/v7/xuat-so.xlsx`, không tham số. Sau xác thực danh tính như mọi route.
- 200: thân là file xlsx; `Content-Disposition: attachment; filename="so-web-YYYYMMDD-HHMM.xlsx"` (thêm `-CO-LECH` khi tự kiểm lệch); `Cache-Control: no-store`; `X-Xuat-So`: JSON chữ ASCII `{"ok":bool,"books":N,"problems":[{"code","count","books":[mã sổ ≤ 5]}]}`. Không tên khách, không số tiền trong header.
- 429 `EXPORT_BUSY`: đang có lượt xuất khác (một lượt mỗi lúc trong tiến trình API).
- 503 `DB_UNAVAILABLE`: không đọc được DB, hoặc danh sách sổ đổi cả hai lượt đọc.
- Trang dùng `fetch`, đọc `X-Xuat-So`, tải file bằng blob; mã lỗi kiểm đổi thành câu tiếng Việt ở trang.

## Nguồn quyết định

- [`XUAT-SO-01`](../docs/decisions/xuat-so-01.md): dạng, bố cục, nơi giữ (ĐÃ CHỐT 18/11/2026).
- [`CHUYEN-HAN-01`](../docs/decisions/chuyen-han-01.md), [`SONG-SONG-01`](../docs/decisions/song-song-01.md): F4 là điều kiện của checklist chuyển hẳn (ĐỀ XUẤT); Sheet vẫn là sổ chính thức tới lần xét sau đối soát cuối tháng 11.
- [`OPENING-SO-GOC`](../docs/decisions/opening-so-goc.md): số dư đầu lấy từ sổ gốc, dòng sổ gốc giữ nguyên trong file như trên web.
- [`LUOI-AN-TOAN-01`](../docs/decisions/luoi-an-toan-01.md): cùng cách đọc một ảnh dữ liệu và cùng phép so Tổng quan với tổng các sổ.

## Hành vi và bất biến

- Chỉ đọc: giao dịch `READ ONLY`, không ghi DB, không ghi Lịch sử. Không thêm hàm SQL.
- VND nguyên chính xác; ô trống là chưa có số, không bao giờ ghi 0 thay NULL (chuyến chưa giá để trống Thành tiền).
- Không xuất im lặng khi lệch. Phép tự kiểm, trên cùng ảnh dữ liệu và trên chính file đã ghi (đọc lại từ byte của file):
  1. **Tổng:** tổng các sổ dương bằng Còn phải thu của Tổng quan (`get_dashboard` và `get_dashboard_debt`), số sổ dương bằng số khách còn nợ; tổng và số sổ âm bằng khách trả thừa.
  2. **Từng sổ so Tổng quan:** `total_outstanding_vnd` của `get_ledger` bằng số Tổng quan dùng cho sổ đó (danh sách khách nợ, danh sách khách dư, còn lại là 0).
  3. **Trong một sổ:** cộng Nợ còn lại các tháng bằng nợ còn lại của sổ; Còn nợ cuối tháng của tháng cuối bằng nợ còn lại.
  4. **Phiếu thu:** mỗi phiếu chưa hủy có dòng chia và cộng các dòng chia bằng tiền phiếu; phiếu đã hủy không còn dòng chia (luật của `_check_allocations`).
  5. **File khớp `get_ledger`:** đọc lại file vừa ghi; từng sổ có đúng số tháng, chuyến, phiếu, dòng chia, điều chỉnh như `get_ledger`, các ô tiền cộng lại đúng như `get_ledger`, và mọi ô đọc lại bằng đúng giá trị đã ghi.
- Lệch thì vẫn trả file (đường lui có số còn hơn không) nhưng tên có `-CO-LECH`, tab KIỂM ghi phép kiểm lệch và mã sổ, header `X-Xuat-So` có `ok:false`, trang báo đỏ, journal ghi mã lệch.
- File chỉ sinh trong bộ nhớ và gửi thẳng cho trình duyệt; máy chủ không giữ bản nào. File có tên khách và số tiền nên không bao giờ vào Git; tài liệu chỉ ghi số đếm.

## Tiêu chí nghiệm thu

- [x] Test Python (`cong-no-web-handoff/tests/test_v7_xuat_so.py`, dữ liệu giả cùng hình dạng `get_ledger`): file đủ bảy tab, cột, ô trống giữ trống, số nguyên chính xác; đọc lại khớp.
- [x] Ca cố ý lệch, mỗi ca làm tự kiểm báo đỏ đúng mã: Tổng quan lệch tổng các sổ; một sổ lệch Tổng quan; tháng cộng không bằng nợ còn lại; phiếu chia thiếu; file ghi thiếu một dòng.
- [x] Test adapter (`tests/test_v7_psql_snapshot.py`): nhiều hàm trong một giao dịch, đọc từng dòng, lỗi psql thành `DB_UNAVAILABLE`.
- [x] Test API: route trả xlsx và header; lượt thứ hai khi đang xuất bị 429; lệch thì tên file có `-CO-LECH`.
- [x] Harness PostgreSQL (`tools/test_pg_v7_xuat_so.py`): xuất trên DB dùng một lần có sổ, chuyến, phiếu, điều chỉnh giả; tự kiểm khớp qua adapter thật.
- [x] Trình duyệt (`preview/test-xuat-so-browser.js`): nút có trên Tổng quan; bấm thì đang xuất, khóa bấm lặp, tải file, báo khớp; lệch thì báo đỏ; lỗi thì câu lỗi; bàn phím bấm được; điện thoại còn biểu tượng.
- [x] `npm run check` và `node scripts/check-secrets.js` xanh (máy Windows, ruff 0.17.3 ghim; quét diff đã stage sạch).
- [x] Chạy thật trên `hao`: tải một bản, tự kiểm khớp, bản lưu ở `D:\webdebit-du-phong\`; tài liệu chỉ ghi số đếm. Lượt qua nút sau deploy: chưa.
- [ ] Người dùng tự bấm nút trên `hao` và mở được file.

## Phạm vi agent

- Agent: claude (từ 29/10/2026 theo `CLAUDE-ALL-01`)
- Review: opus (đọc toàn bộ sổ, quyền tải)
- Được sửa:
  - `cong-no-web-handoff/web/v7_book_export.py`, `v7_book_export_rows.py`, `v7_book_export_check.py`, `v7_xlsx_writer.py` (mới)
  - `cong-no-web-handoff/web/v7_psql.py`, `cong-no-web-handoff/web/v7_api_tables.py`, `cong-no-web-handoff/web/v7_ledger_api.py`
  - `cong-no-web-handoff/preview/xuat-so.js`, `test-xuat-so-browser.js` (mới); `dashboard-v7.html`, `dashboard-v7.js`, `dashboard-v7.css`
  - `cong-no-web-handoff/tests/test_v7_xuat_so.py`, `test_v7_psql_snapshot.py`, `cong-no-web-handoff/tools/test_pg_v7_xuat_so.py` (mới); `.github/workflows/test.yml` (thêm harness)
  - `specs/v7-xuat-ca-so.md`, `docs/decisions/xuat-so-01.md`, `docs/decisions.md`, `docs/chuyen-han-checklist.md`, `docs/development.md`
- Cấm: đổi schema hoặc hàm SQL, ghi DB, quyền mới; chép file xuất thật vào repo.

## Hoàn tác

Revert PR: nút và route mất, không có dữ liệu nào phải dọn (route chỉ đọc, máy chủ không giữ file).

## Bằng chứng

18/11/2026, nhánh `claude/f4-duong-lui-xuat-so`.

- **Dữ liệu giả, máy Windows:** `tests/test_v7_xuat_so.py` 17 ca (gồm 7 ca cố ý lệch: Tổng quan khác tổng các sổ, khách dư khác, một sổ khác Tổng quan, tháng cộng không bằng nợ còn lại, phiếu chia thiếu, phiếu hủy còn dòng chia, file rơi một dòng; mỗi ca đỏ đúng mã, tên file `-CO-LECH`, tab KIỂM ghi LỆCH); `tests/test_v7_psql_snapshot.py` 5 ca (một giao dịch chỉ đọc, thứ tự lệnh, lỗi giữa chừng, hết giờ, chỉ hàm đọc); `preview/test-xuat-so-browser.js` 5 ca. File giả mở bằng openpyxl (khung cố định, bộ lọc, định dạng tiền và ngày) và bằng Excel trên PC (cửa sổ mang tên file, không phải bản sửa).
- **Harness PostgreSQL 18.6 dùng một lần:** `tools/test_pg_v7_xuat_so.py` đạt 3 ca: sổ qua nạp, dán chuyến, sửa giá, ghi thu, hủy phiếu, điều chỉnh xuất khớp và tổng bằng `get_ledger`; `get_dashboard`, `get_ledger` bị làm sai thì đỏ đúng mã; hàm đọc có lệnh ghi thì cả lượt lỗi (giao dịch đúng là READ ONLY).
- **Lượt thật trên `hao`, 11:04:** mã của nhánh chép vào thư mục tạm, chạy bằng `sudo -u v7app`, file đi thẳng qua SSH về `D:\webdebit-du-phong\`, thư mục tạm đã xóa. Kết quả: 242 sổ, tự kiểm khớp 6/6, 21,4 giây, 878 KB. Kiểm lại độc lập trên PC từ file: 946 dòng tháng, 10.696 chuyến, 1.310 phiếu thu, 101 dòng chia, 296 điều chỉnh; tổng 62 sổ còn nợ bằng Còn phải thu ghi trong tab KIỂM, sổ dư bằng Khách trả thừa, 0 sổ có cộng các tháng khác nợ còn lại. Tên khách và số tiền chỉ nằm trong file, không ở đây.
- **Chưa:** lượt qua nút trên `hao` sau deploy; người dùng tự bấm và mở file.

Lỗi sẵn có thấy khi làm (ngoài phạm vi): ở màn hẹp, khối "Quá hạn" của dải đầu Tổng quan có `min-width` nên tràn ngang với vài con số.

## Câu hỏi mở

- Nhắc tải định kỳ (ví dụ máy canh báo khi bản tải gần nhất quá N ngày) chưa làm: máy chủ không biết người dùng đã cất file chưa. Xét sau khi người dùng dùng thử.
