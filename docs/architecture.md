# Kiến trúc và phạm vi hiện có

Đường chạy thật là V7: `web/v7_ledger_api.py` phục vụ API và các trang trong `PAGES` của `web/v7_api_tables.py`; mọi lệnh psql đi qua `web/v7_psql.py`. Bố cục chi tiết: [Bố cục API V7](development.md#bố-cục-api-v7-web-từ-31102026). Query thật cần DB/role cấp riêng, ngoài test cơ sở. Code đời M1/V1/V2 (`pilot/reconcile.py`, viewer `web/app.py` + `web/db.py`, `web/ledger_app.py`, trang `so-cong-no*.html`, `customer-ledger-workbench`) đã xóa 18/11/2026; `web/ledger_db.py` còn vì harness `tools/test_pg_m1_queries.py`.

`preview/*-model.js` giữ số học tiền; `*-ui.js` vẽ và gọi model. `so-khach-v7.html` là bản fixture của Sổ khách cho test trình duyệt, không có API ghi. Python HTTP tests thay DB bằng fake, mở cổng loopback ngẫu nhiên; browser tests mở HTML fixture, không qua service thật.

SQL trong `tools/` kế thừa bản xuất có chọn lọc. Domain/ERD/DDL ngày 15/10 nằm trong hồ sơ gốc ngoài repo, chưa phải migration production. Nguyên tắc thiết kế: customer ID + alias, trip ID độc lập container, receipt tách allocation, posting bất biến, provenance và statement có phiên bản. Chưa chứng minh các module đó đã triển khai.

Máy chạy trên `hao` (từ 22/10/2026), mã trong repo, cấu hình ngoài repo:

- **API** `web/v7_ledger_api.py` có nhịp nền mỗi phút (`web/v7_inbox.py`): tính hộp việc theo bản chụp Sheet và, theo cờ `WEBDEBIT_AUTO_SHEET`, tự dán chuyến, ghi giá, phí PS. Đây là đường ghi tiền thứ nhất của máy.
- **Runner bản chụp Sheet** (`tools/sheet_sync_runner.py`, `v7_price_snapshot.py`, `v7_ps_snapshot.py`; timer 15 phút) chỉ đọc Google Sheet và ghi JSON vào `/var/lib/webdebit-sheet-sync`.
- **Máy đối soát** `tools/v7_reconcile_auto.py` (timer mỗi giờ, `--fix`): so tổng từng khách với Sheet, chỉ ghi khi đúng một tổ hợp việc khớp tới từng đồng. Đường ghi tiền thứ hai.
- **Sao lưu** `tools/v7_backup.py` (bản ghim ngoài release): dump mỗi giờ và hằng ngày, gói cấu hình, hộp chờ mã hóa `age` mà các PC kéo bằng `tools/v7_offsite_pull.py`.
- **Máy canh** `tools/v7_watchdog.py` (timer 15 phút): kiểm mọi thứ trên, gồm lưới an toàn `tools/v7_safety_net.py`, báo về healthchecks.io theo nhóm.
- **Ngoài `hao`:** agent Zalo (`tools/zalo_agent/`) trên PC `msi`; Apps Script log sửa Sheet (`scripts/sheet-capture/`).

Deploy: merge `main` → `Tests` → `Deploy hao` đẩy gói theo `scripts/deploy/release-paths.txt` qua SSH một lệnh (`scripts/deploy/hao-release.sh`); migration và SQL áp tay theo runbook. Bảng đầy đủ (nhịp, ai biết khi dừng, cách dừng): [van-hanh.md](van-hanh.md); dựng lại máy: [rebuild-hao.md](rebuild-hao.md).

Một số importer và test phụ thuộc nằm ngoài repo. Không copy cả workspace để thêm ngược. Thay schema/đường ghi cần hợp đồng riêng và test PostgreSQL thật trên bản sao (harness `tools/test_pg_*.py` dựng PostgreSQL 18 dùng một lần, chạy trong CI).

Xem [gate còn mở](decisions.md), [nguồn S15/S15R](source-register.md), [map thay đổi](../specs/pending-shipments/README.md).
