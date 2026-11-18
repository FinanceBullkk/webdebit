# Kiến trúc và phạm vi hiện có

Đường chạy thật là V7: `web/v7_ledger_api.py` phục vụ API và các trang trong `PAGES` của `web/v7_api_tables.py`; mọi lệnh psql đi qua `web/v7_psql.py`. Bố cục chi tiết: [Bố cục API V7](development.md#bố-cục-api-v7-web-từ-31102026). Query thật cần DB/role cấp riêng, ngoài test cơ sở. Code đời M1/V1/V2 (`pilot/reconcile.py`, viewer `web/app.py` + `web/db.py`, `web/ledger_app.py`, trang `so-cong-no*.html`, `customer-ledger-workbench`) đã xóa 18/11/2026; `web/ledger_db.py` còn vì harness `tools/test_pg_m1_queries.py`.

`preview/*-model.js` giữ số học tiền; `*-ui.js` vẽ và gọi model. `so-khach-v7.html` là bản fixture của Sổ khách cho test trình duyệt, không có API ghi. Python HTTP tests thay DB bằng fake, mở cổng loopback ngẫu nhiên; browser tests mở HTML fixture, không qua service thật.

SQL trong `tools/` kế thừa bản xuất có chọn lọc. Domain/ERD/DDL ngày 15/10 nằm trong hồ sơ gốc ngoài repo, chưa phải migration production. Nguyên tắc thiết kế: customer ID + alias, trip ID độc lập container, receipt tách allocation, posting bất biến, provenance và statement có phiên bản. Chưa chứng minh các module đó đã triển khai.

Submit/deploy/SSH, một số importer và test phụ thuộc nằm ngoài repo. Không copy cả workspace để thêm ngược. Thay schema/đường ghi cần hợp đồng riêng và test PostgreSQL thật trên bản sao; repo chưa có môi trường DB integration tự dựng.

Xem [gate còn mở](decisions.md), [nguồn S15/S15R](source-register.md), [map thay đổi](../specs/pending-shipments/README.md).
