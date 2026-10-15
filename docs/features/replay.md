# Replay và ngoại lệ nguồn

**Trạng thái:** engine đọc capture có manifest/hash do môi trường riêng cấp; repo chia sẻ không chứa capture và không tự gọi Sheet. Xem [kiến trúc](../architecture.md) và [nguồn](../source-register.md).

- Luồng: capture được cấp → `pilot/reconcile.py:load_capture` kiểm provenance → `build` tính replay/ngoại lệ → `save` ghi output cục bộ.
- Kiểm: `cong-no-web-handoff/tests/test_reconcile.py`; với dữ liệu thật cần đối chiếu nguồn và hash trong môi trường được cấp riêng.
- Bất biến: opening đã chứa lịch sử được chọn; không cộng lại lịch sử, không biến blank/NULL thành 0, giữ ngoại lệ và ngày/kỳ riêng.
- Giới hạn: fixture test không chứng minh Sheet hiện tại, tính đầy đủ của capture hoặc số dư live.
