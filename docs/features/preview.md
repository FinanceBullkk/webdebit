# Giao diện xem thử

**Trạng thái:** model và workbench là fixture giả trong bộ nhớ tab, không có API ghi hay duyệt thật. Xem [kiến trúc](../architecture.md).

- Luồng: `preview/customer-ledger-workbench-ui.js` nối form/filter → `customer-ledger-workbench.js` và `*model.js` → DOM/HTML.
- Kiểm: `npm run test:unit` cho model; `npm run test:browser` cho hành vi trên Chromium fixture.
- Bất biến: trạng thái chờ phải nhìn thấy nhưng không tăng/giảm số dư đã ghi; hiển thị chuyến và thu cạnh nhau không hàm ý tất toán.
- Giới hạn: browser test không đi qua DB/service thật; số fixture không phải opening hay số dư khách.
