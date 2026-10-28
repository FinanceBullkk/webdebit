# V7: nút "Làm mới" lấy ngay dữ liệu từ Sheet

Trạng thái: **ĐÃ CHỐT** luồng và mockup (người dùng yêu cầu và duyệt trong chat 28/10/2026: lấy ngay khi không muốn chờ lượt 15 phút, gắn vào nút "↻ Làm mới" đang có; "Duyệt, code tiếp"). **ĐÃ CODE** backend và giao diện, kiểm bằng máy chủ giả; **ĐÃ TRIỂN KHAI trên `hao` 28/10/2026** (release `5e0b184`, unit `.path`; bằng chứng ở [runbook](../docs/v7-deploy-runbook.md#nút-làm-mới-đọc-sheet-ngay--cài-unit-path-đã-chạy-trên-hao-28102026)). Không đổi luật tiền.

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (trên 40 tuổi, màn 1280×720) vừa gõ giá hoặc chuyến mới trên Sheet và muốn thấy ngay trên web để ghi.

**Bối cảnh:** trên `hao` hai runner chỉ đọc Sheet (chuyến: `webdebit-sheet-sync`, giá: `webdebit-sheet-prices`) chạy 15 phút một lần, ở phút 00/15/30/45 (kiểm 28/10/2026). Giá gõ trên Sheet có thể chờ tới khoảng 16 phút mới lên web. Nút "↻ Làm mới" hiện chỉ tải lại sổ từ DB, không đọc Sheet.

**Luồng:**
1. Người nhập bấm **"↻ Làm mới"** ở thanh trên cùng (sổ khách hoặc Tổng quan), đúng nút đang có.
2. Web tải lại sổ ngay như hiện nay, **đồng thời** yêu cầu `hao` đọc Sheet một lượt.
3. Cạnh nút hiện **"Đang lấy từ Sheet… (khoảng 1 phút)"**. Nút vẫn bấm được nhưng không gửi yêu cầu thứ hai.
4. Lấy xong, sổ tự tải lại. Dòng chữ cạnh nút đổi thành **"Sheet lúc 11:52 · tự tải mỗi 60 giây"**. Giá và chuyến mới hiện thành dòng vàng như đã chốt ở [`v7-price-queue`](v7-price-queue.md); vẫn phải bấm "Ghi N giá từ Sheet" hoặc "Duyệt … chuyến mới" mới vào sổ.
5. Không lấy được thì dòng chữ báo **"Chưa lấy được từ Sheet, đang dùng bản lúc 11:45"**. Sổ vẫn dùng được.

**Mockup (đã duyệt 28/10/2026):** [`preview/mockups/lam-moi-tu-sheet/index.html`](../cong-no-web-handoff/preview/mockups/lam-moi-tu-sheet/index.html), dữ liệu giả, năm trạng thái: bình thường, đang lấy, lấy xong, vừa lấy, không lấy được.

**Kết quả:** giá vừa gõ trên Sheet hiện trên web sau khoảng 1 phút, không phải chờ lượt 15 phút.

**Không thay đổi:**
- Tự tải mỗi 60 giây **không** đọc Sheet; chỉ bấm tay mới đọc.
- Lịch 15 phút giữ nguyên.
- Không có đường ghi Sheet. Runner vẫn chỉ đọc, dùng đúng tài khoản dịch vụ hiện có.
- Đang nhập nháp hoặc mở chi tiết thì nút giữ cách chặn hiện có ("Đóng chi tiết hoặc lưu/bỏ nháp trước khi làm mới.") và không gửi yêu cầu đọc Sheet.

**Trường hợp đặc biệt:**
| Trường hợp | Hiện cho người dùng | Hệ thống |
| --- | --- | --- |
| Đang có lượt chạy (bấm tay hoặc lịch 15 phút) | "Đang lấy từ Sheet…" | Không mở lượt thứ hai |
| Bản chụp vừa lấy dưới 60 giây | "Sheet vừa lấy lúc 11:52" | Không đọc lại; chỉ tải lại sổ |
| Quá 3 phút chưa xong | "Chưa lấy được từ Sheet, đang dùng bản lúc …" | Ghi log; lượt 15 phút sau vẫn chạy |
| Máy chủ chưa bật tính năng | Như hiện nay, không có chữ "Sheet lúc" | API trả `unavailable` |

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Có sẵn:**
- Nút `#refresh-data` và hàm `refresh(manual)` trong `so-khach-v7-ui.js`; `dashboard-v7.html` có nút cùng id.
- Runner: `sheet_sync_runner.py` ghi `snapshot.json`; `v7_price_snapshot.py` ghi `prices.json`. Cả hai có `runner.created_at` và ghi file nguyên tử, trong `/var/lib/webdebit-sheet-sync/` (chủ `v7app`, mode 700).
- API V7 chạy cùng user `v7app` (đọc được `prices.json` mode 600), nên ghi được file trong thư mục đó.

**Còn thiếu:** API báo trạng thái lấy Sheet, API yêu cầu lấy, cách để `hao` chạy runner khi có yêu cầu.

## Cách kích hoạt trên `hao`

API **không** chạy runner và **không** cần quyền `sudo`/`systemctl`:
- `POST` ghi file tín hiệu `/var/lib/webdebit-sheet-sync/refresh.request` (nội dung: thời điểm, người bấm theo `V7-ID`).
- Unit `webdebit-sheet-refresh.path` (`PathModified=` file đó) khởi động `webdebit-sheet-refresh.service`: oneshot, `Wants=` hai service runner hiện có. Drop-in cho `webdebit-sheet-prices.service` thêm `After=webdebit-sheet-sync.service`, để chụp giá sau chuyến (đúng thứ tự của lịch 15 phút).
- systemd không chạy song song cùng một service oneshot: bấm khi đang chạy thì gộp vào lượt đang chạy.

## Giao tiếp frontend–backend

- `GET /api/v7/sheet/refresh` → `{state: idle | running | failed | unavailable, sheet_at, requested_at}`. `sheet_at` là `runner.created_at` cũ hơn trong hai file (giờ của bản chụp đang dùng). `running` khi `requested_at` mới hơn `sheet_at` và chưa quá 3 phút; quá 3 phút thì `failed`.
- `POST /api/v7/sheet/refresh {}` → cùng dạng (thân rỗng: yêu cầu tự gộp nên không cần khóa lệnh). Không ghi tín hiệu khi đang `running` hoặc `sheet_at` dưới 60 giây; khi đó trả trạng thái hiện tại.
- Trình duyệt hỏi `GET` 5 giây một lần trong lúc `running`, dừng khi đổi trạng thái; xong thì gọi `refresh()` đọc lại sổ.
- Tắt được bằng biến môi trường: không đặt đường dẫn tín hiệu thì API trả `unavailable`, giao diện như hiện nay.

## Tiến độ (28/10/2026)

- `web/v7_sheet_refresh.py`: trạng thái theo giờ file (tín hiệu, `snapshot.json`, `prices.json`), ghi tín hiệu. `web/v7_ledger_api.py`: `GET`/`POST /api/v7/sheet/refresh`, biến `WEBDEBIT_SHEET_REFRESH_PATH`.
- `preview/sheet-refresh.js` dùng chung cho sổ khách và Tổng quan; nối vào nút `#refresh-data` có sẵn. Tự tải 60 giây chỉ `GET` trạng thái.
- Test: `tests/test_v7_sheet_refresh.py` (9 test); Playwright trong `test-so-khach-v7-edit-browser.js` (đang lấy → xong tải lại sổ, bấm lặp, đang nhập không gửi, lỗi).

## Tiêu chí nghiệm thu

- [x] Test API: `POST` ghi tín hiệu một lần; bấm lặp khi đang chạy hoặc vừa lấy dưới 60 giây không ghi thêm; trạng thái `running` → `idle` khi hai file mới hơn tín hiệu; quá 3 phút → `failed`; thiếu cấu hình → `unavailable`.
- [x] Playwright 1280×720, máy chủ giả: bấm "Làm mới" hiện "Đang lấy từ Sheet…", xong thì sổ tải lại và hiện "Sheet lúc …"; lỗi hiện câu báo, sổ vẫn dùng được; đang nhập thì không gửi. Tự tải 60 giây không gửi `POST`: chưa có test chờ 60 giây, kiểm bằng đọc code (nhánh tự động chỉ gọi `load()`).
- [ ] `npm run check` xanh.
- [x] Trên `hao` (người dùng cho phép 28/10/2026): cài unit `.path`, drop-in thứ tự, đổi release; bấm thử một lần, log hai runner có lượt ngoài lịch, số dư khách không đổi.
- [ ] Người dùng bấm thử và xác nhận.

## CÒN MỞ

- Trang "Công nợ theo tháng" chưa có nút "Làm mới"; không thêm trong phạm vi này.
