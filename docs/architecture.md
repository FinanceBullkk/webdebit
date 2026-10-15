# Kiến trúc và phạm vi hiện có

`pilot/reconcile.py` đọc capture có manifest/hash, kiểm provenance rồi tính replay/ngoại lệ; không tự gọi Sheet. Repo không có capture. `web/app.py` + `web/db.py` đọc replay; `web/ledger_app.py` + `web/ledger_db.py` đọc opening/posting và chi tiết. Query thật cần DB/role cấp riêng, ngoài test cơ sở.

`preview/*model.js` và `customer-ledger-workbench.js` là fixture. `customer-ledger-workbench-ui.js` nối form/filter với bộ nhớ tab. Trang không có API ghi, localStorage hay duyệt thật. Python HTTP tests thay DB bằng fake, mở cổng loopback ngẫu nhiên; browser tests mở HTML fixture, không qua service thật.

SQL trong `tools/` kế thừa bản xuất có chọn lọc. Domain/ERD/DDL ngày 15/10 nằm trong hồ sơ gốc ngoài repo, chưa phải migration production. Nguyên tắc thiết kế: customer ID + alias, trip ID độc lập container, receipt tách allocation, posting bất biến, provenance và statement có phiên bản. Chưa chứng minh các module đó đã triển khai.

Submit/deploy/SSH, một số importer và test phụ thuộc nằm ngoài repo. Không copy cả workspace để thêm ngược. Thay schema/đường ghi cần hợp đồng riêng và test PostgreSQL thật trên bản sao; repo chưa có môi trường DB integration tự dựng.

Xem [gate còn mở](decisions.md), [nguồn S15/S15R](source-register.md), [map thay đổi](../specs/pending-shipments/README.md).
