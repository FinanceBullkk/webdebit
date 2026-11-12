# Thông tin cty: danh bạ khách và tài khoản nhận tiền từ Sheet

Trạng thái: ĐÃ CHỐT (người dùng, chat 12/11/2026: "tạo 1 tab thông tin cty trên web, lấy data trực tiếp từ sheet này", "Làm đi"; cách làm do Claude chọn theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md)). Quyết định: [`THONG-TIN-CTY-01`](../docs/decisions/thong-tin-cty-01.md).

## Người dùng và luồng

Người lập debit note (nhân viên kế toán, trên 40 tuổi, màn 1280×720) và người cần tra thông tin xuất hóa đơn của khách. Hôm nay thông tin này nằm trên một Google Sheet riêng (Sheet "thông tin khách hàng", tab `THÔNG TIN CTY` và tab `TÀI KHOẢN USD`); hộp debit note bắt người lập gõ lại tên pháp lý, địa chỉ, và ngân hàng thì in `[Beneficiary]`.

1. **Tra cứu.** Menu trái có mục *Thông tin cty*. Trang có hai khối: *Tài khoản nhận tiền* (mỗi tài khoản một thẻ: loại tiền, ngân hàng, các dòng nhãn → giá trị như trên Sheet) và *Khách hàng* (ô tìm theo tên shipper, mỗi khách một thẻ: tên shipper, khối thông tin xuất hóa đơn, khối ngân hàng của khách, giữ nguyên xuống dòng). Đầu trang ghi lúc web đọc Sheet lần cuối. Muốn sửa thì sửa trên Sheet; trang chỉ xem.
2. **Xuất debit note (mẫu v4).** Trong hộp, khối *Khách (BILL TO)* có ô *Chọn từ Thông tin cty*: gõ vài chữ tên shipper, chọn một dòng thì ô *Tên pháp lý và địa chỉ* được điền bằng khối thông tin xuất hóa đơn (vẫn sửa tay được). Khối mới *Tài khoản nhận tiền* là ô chọn một tài khoản; phần PAYMENT INFORMATION của chứng từ in theo tài khoản đó. Trình duyệt nhớ lựa chọn theo sổ, lần sau mở là có sẵn.
3. **Bị chặn / cảnh báo.** Chưa chọn tài khoản và cấu hình máy chủ cũng không có số tài khoản → cảnh báo "Chưa chọn tài khoản nhận tiền", phải tích xác nhận mới xuất (chứng từ in `[Account no.]`). Tài khoản đã nhớ không còn trên Sheet → coi như chưa chọn. Không đọc được danh bạ → hộp vẫn dùng được như cũ, ô chọn ghi "Chưa đọc được Thông tin cty".

## Đầu ra

Tab `/thong-tin-cty.html` hiện đúng dữ liệu hai tab Sheet theo bản đọc gần nhất trên `hao`; hộp debit note v4 chọn được khách và tài khoản từ đó. Dữ liệu thật không qua repo, không qua chat.

## Đối chiếu dữ liệu và code hiện có

- **Sheet** (chỉ đọc dòng tiêu đề khi viết spec): tab `THÔNG TIN CTY` có dòng tiêu đề ở dòng 2, cột C `SHIPPER`, D `THONG TIN XUAT HOA DON` (một ô nhiều dòng), E `THONG TIN NGAN HANG`. Tab `TÀI KHOẢN USD` không phải bảng: mỗi tài khoản là một khối, cột B gộp dọc là tên khối (ví dụ "收款人资料 / ACCOUNT NUMBER INFORMATION / (VND) / <tên ngân hàng>"), cột C là nhãn song ngữ (`公司全称 ACC NAME`, `公司地址 ADDRESS`, `银行名称 BANK NAME`, `银行地址 BANK ADDRESS`, `银行账户 ACCOUNT NUMBER`…), cột D là giá trị (gộp D:L).
- **Đọc Sheet trên `hao`**: tài khoản dịch vụ `spreadsheets.readonly` và hàm lấy token của [`sheet_sync_runner.py`](../cong-no-web-handoff/tools/sheet_sync_runner.py); ghi file nguyên tử mode 600 bằng `write_snapshot`. Sheet phải được chia sẻ quyền Viewer cho email tài khoản dịch vụ.
- **Hộp debit note v4**: [`so-khach-v7-debit-ui.js`](../cong-no-web-handoff/preview/so-khach-v7-debit-ui.js) `formV4`/`refreshV4`; [`debit-note-v4.js`](../cong-no-web-handoff/preview/debit-note-v4.js) in PAYMENT INFORMATION từ `config.payment` (`beneficiary`, `bank`, `account_label_en/cn`, `account`, `swift`). Mẫu v3 không đổi.
- **Trang**: khuôn như Bảng thu (`app-nav.js`, `cong-no-theme.css`, `presence.js`); đăng ký trang ở `PAGES` của [`v7_api_tables.py`](../cong-no-web-handoff/web/v7_api_tables.py). Menu riêng của Sổ khách (`so-khach-v7-live.html`) cũng thêm mục.

## Giao tiếp frontend–backend

- **Job** `tools/v7_company_info_snapshot.py --output /var/lib/webdebit-sheet-sync/company-info.json`: đọc hai tab bằng `values:batchGet` (`FORMATTED_VALUE`, giữ số tài khoản như hiện trên Sheet), dựng `{accounts, customers, counts, runner}` rồi ghi đè nguyên tử. Không tìm thấy tiêu đề `SHIPPER` hoặc không có tài khoản nào có số tài khoản → thoát mã 1, **giữ file cũ**. Stdout chỉ có số đếm.
- **API** `GET /api/v7/company-info` (sau xác thực danh tính như mọi route, không nhận tham số): `200 {available: true, read_at, accounts: [{id, title, label, currency, beneficiary, address, bank, bank_address, account, swift, lines: [{label, value}]}], customers: [{shipper, invoice, bank}], counts}`; chưa có file → `200 {available: false}`; file hỏng → `503 COMPANY_INFO_UNAVAILABLE` "Không đọc được bản Thông tin cty của máy chủ."
- `id` tài khoản = băm ngắn của ngân hàng + số tài khoản, để trình duyệt nhớ lựa chọn qua các lần đọc lại.

## Nguồn quyết định

- [`THONG-TIN-CTY-01`](../docs/decisions/thong-tin-cty-01.md); [`DEBIT-NOTE-03`](../docs/decisions/debit-note-03.md) (cấu hình ngân hàng ngoài repo); repo public: không đưa mã Sheet, tên khách, số tài khoản vào repo.

## Hành vi và bất biến

- Chỉ đọc Sheet; không ghi DB, không đổi tiền. Không có dữ liệu thật trong repo, fixture là dữ liệu giả.
- File đầu ra mode 600, cùng thư mục và cùng user `v7app` với các bản chụp khác; nằm trong gói backup cấu hình như thư mục đó.
- Đọc lỗi thì web dùng bản cũ; trang ghi rõ giờ đọc.
- Tài khoản nhận tiền chọn ở hộp ghi đè `config.payment` cho riêng chứng từ đó; nhãn tài khoản theo loại tiền của khối (`USD Account 美元账号`, `VND Account 越南盾账号`, `CNY Account 人民币账号`).

## Tiêu chí nghiệm thu

- [ ] `tests/test_v7_company_info.py`: dò tiêu đề, bỏ dòng thiếu shipper, tách khối tài khoản theo cột B, nhận nhãn theo chữ Anh, loại tiền, bỏ dấu phẩy ở số tài khoản; lỗi cấu trúc thì không ghi đè file cũ; API trả `available: false` khi chưa có file, 503 khi file hỏng.
- [ ] `test-thong-tin-cty-browser.js`: trang hiện thẻ tài khoản và khách từ máy chủ giả, tìm bỏ dấu, chưa có bản đọc thì báo; menu bảy mục lọt khung 1280×560; 390px không cuộn ngang.
- [ ] `test-so-khach-v7-debit-v4-browser.js`: chọn khách điền ô pháp lý; chọn tài khoản thì PAYMENT INFORMATION in đúng; chưa chọn thì cảnh báo; nhớ theo sổ.
- [ ] `npm run check` xanh.
- [ ] Trên `hao`: chia sẻ Sheet cho tài khoản dịch vụ, chạy job một lần (chỉ đọc số đếm), bật timer; người dùng mở tab và xuất thử một debit note.

## Hoàn tác

Tắt timer `webdebit-company-info.timer`; revert PR. Không có dữ liệu DB.

## Bằng chứng

Ghi ở PR và mục triển khai của runbook.
