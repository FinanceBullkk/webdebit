# Bản đồ feature cho AI và dev

Đọc [hướng dẫn chung](../README.md), [quy tắc nghiệp vụ](../business-rules.md) và [quyết định](../decisions.md), rồi mở đúng một trang dưới đây trước khi đọc mã. Các trang này là bản đồ entry point và phép kiểm, không sao chép spec hay dữ liệu nguồn.

| Công việc | Đọc tiếp | Mã chính | Kiểm tương ứng |
| --- | --- | --- | --- |
| Replay và ngoại lệ nguồn | [Replay](replay.md) | `cong-no-web-handoff/pilot/reconcile.py` | `tests/test_reconcile.py` |
| Trang đọc replay | [Web đọc](read-only-web.md) | `web/app.py`, `web/db.py` | `tests/test_web.py` |
| Sổ opening/posting đọc và SQL | [Sổ ledger](ledger.md) | `web/ledger_app.py`, `web/ledger_db.py`, `tools/pg_ledger_schema.sql` | `tests/test_ledger_web.py`, PostgreSQL characterization |
| Giao diện xem thử | [Preview](preview.md) | `preview/*model.js`, `preview/customer-ledger-workbench*.js` | Node và Chromium fixture tests |

Nếu task đi qua nhiều feature, mở từng trang liên quan. Dùng `rg` để tìm entry point rồi đọc vùng mã cần sửa; không nạp toàn repo, `package-lock.json`, raw capture hoặc toàn bộ log vào context mặc định. Đích vận hành là đa số task dưới 100k context; cần đo từ các task thật trước khi tuyên bố đạt.
