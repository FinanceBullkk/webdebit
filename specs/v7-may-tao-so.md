# Máy tự tạo sổ cho khách mới

Trạng thái: ĐÃ CHỐT (người dùng, 4/11/2026, [`MAY-TAO-SO-01`](../docs/decisions/may-tao-so-01.md))

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Người nhập không đổi cách làm: thêm tab khách mới trên Sheet, thêm tên vào TONG. Chủ sổ (trên 40 tuổi, laptop 1280×720) mở tab Việc cần làm, mang theo câu hỏi: khách mới đã vào web chưa, có gì mình phải quyết không.

1. Đủ điều kiện: lượt đối soát kế tiếp tạo sổ. Dải đầu tab ghi "hôm nay máy đã tạo N sổ mới"; bấm "Xem" thấy tên khách, câu "Máy đã tạo sổ mới theo TONG…" và đường mở sổ. Sổ mới xuất hiện ở Tìm khách, Tổng quan như mọi sổ khác.
2. Chưa đủ điều kiện: dải màu vàng, có một câu liệt kê tab, số còn nợ và lý do. Chủ sổ sửa trên Sheet hoặc nhờ xử lý; lượt sau máy kiểm lại.
3. Không có khách mới: không hiện thêm gì.

## Đầu ra

- `tools/v7_reconcile_auto.py`: đọc khối mới nhất của TONG thật (`live_tong`), nhận tab mới đủ điều kiện vào phép so (`admit_new_tabs`), tạo sổ cho khách có trên Sheet mà chưa có trên web (`create_new_books`), báo tab chưa nhận được (`outside_tabs`).
- Hàm SQL `sokhach.create_book_from_sheet`, migration `tools/migrations/2026-11-04-v7-tao-so.sql`.
- `reconcile.json` thêm `outside_tabs[].reason`; dòng khách thêm các lý do mới; `reconcile-log.jsonl` thêm `created`.
- Tab Việc cần làm hiện số sổ đã tạo, các lý do mới và lý do của tab chưa nhận được.

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

| Cần | Lấy từ | Ghi chú |
| --- | --- | --- |
| Danh sách khách trên TONG thật | Tab `TONG` trong bản tải, cột ngay sau `LOAI HANG` ở khối ngoài cùng bên phải | `in_summary` của bộ đọc sổ gốc so với CSV đóng băng 20/10, không dùng được cho việc này |
| Số cuối tháng trên TONG | Cột `SỐ CÒN PHẢI THU CUỐI THÁNG` cùng khối; tháng lấy từ tiêu đề `CÔNG NỢ PHÁT SINH TRONG THÁNG m.yyyy` | Đo 4/11/2026: khối T10/2026, 228 tên |
| Số cuối tháng đó trên tab | `checks[].source_cumulative_vnd` của sổ đọc được | Tab đã sang tháng mới vẫn so đúng tháng của TONG |
| Số dư đầu, dòng sổ gốc, kiểm từng tháng | `clean.build_books` như mọi khách | Cùng dữ liệu `import_cutover` đã nhận lúc nạp |
| Mặt hàng | Nhãn trên TONG qua `commodity_of` | Nhãn lạ để trống |
| Container đã ở sổ khác | `v7_price_queue.targets` của mọi sổ, đã đọc sẵn trong lượt | Cửa sổ ±3 ngày, như chặn trùng hàng chờ |
| Tạo khách, mốc, trạng thái | `import_cutover`, `verify_cutover_customer`, `verify_cutover`, `activate_cutover`, `activate_cutover_customer` | Mốc 21/10 đã khóa không cho thêm khách (`guard_cutover_customer_status`), nên mỗi sổ mới một mốc |
| Thêm chuyến sau khi tạo sổ | `paste_trips` đòi mốc có `baseline_trip_ref` | Hàm tạo sổ ghi tham chiếu từ dòng chuyến của tab; tab không có container thì ghi một dòng đánh dấu |

Đo trên `hao` 4/11/2026 (chỉ đọc): 13 tab ngoài danh sách mốc; 2 tab đủ điều kiện, số trên TONG khớp đúng số trên tab, tổng 334.601.234 đ. Bản giả và ảnh chụp không dùng số khách thật.

## Giao tiếp frontend–backend (bước 5, khi có)

Không thêm route. `GET /api/v7/inbox` trả nguyên `reconcile`:

```json
{"reconcile": {"outside_tabs": [{"customer": "…", "sheet_total_vnd": "…", "last_month": "2026-10", "reason": "TONG_DIFFERS"}],
  "customers": [{"customer": "…", "customer_id": 237, "status": "KHOP", "reason": "BOOK_CREATED", "fixed_at": "…",
                 "sheet_total_vnd": "…", "web_total_vnd": "…", "difference_vnd": "0"}]}}
```

- `outside_tabs[].reason`: `NOT_ON_TONG`, `TONG_DIFFERS`, `TAB_UNREADABLE`.
- `reason` của dòng khách thêm: `BOOK_CREATED`, `WOULD_CREATE_BOOK` (lượt chỉ báo), `BOOK_OVERLAP` (kèm `overlap_ids`), `TOO_MANY_NEW_BOOKS`. Sổ tạo trong ngày ở lại danh sách tới hết ngày như khách máy đã sửa.

## Nguồn quyết định

- [`MAY-TAO-SO-01`](../docs/decisions/may-tao-so-01.md), [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md), [`OPENING-SO-GOC`](../docs/decisions/opening-so-goc.md), [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md), [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md).

## Hành vi và bất biến

- Mọi điều kiện kiểm trên cùng một bản tải. Thiếu hay lạ thì ra "không biết" và không tạo: bố cục TONG khác, tên trùng trên TONG, ô không phải số.
- Hàm tạo sổ một giao dịch: một cổng kiểm từng tháng không đạt thì không còn khách, mốc hay event nào.
- Không tạo trùng: khóa theo giao dịch, tên đã có (không phân biệt hoa thường) thì `BOOK_EXISTS`.
- Tạo xong đọc lại sổ: tổng phải bằng tổng Sheet, không thì `VERIFY_FAILED` và dải đỏ.
- Sổ đã tạo về sau vẫn nằm trong phép so dù tab rời TONG; khi đó báo như mọi khách có vấn đề, không lờ đi.
- Tab lỗi không làm hỏng cả lượt: kiểm riêng từng tab trước khi nhận.
- Không đổi quy tắc tiền, phân bổ. Lịch sử trong số dư đầu không cộng lại. VND nguyên chính xác; NULL không phải 0.
- Thân lệnh đi qua một tham số dòng lệnh psql, giới hạn 128 KB. Tab mới quá lớn thì lệnh lỗi, máy báo, không ghi gì.

## Tiêu chí nghiệm thu

- [ ] `tools/test_pg_v7_backend_tao_so.py`: tạo sổ đủ trạng thái, Lịch sử, tham chiếu, dán chuyến được; tên trùng, đầu vào sai, cổng kiểm không đạt thì không để lại gì; quyền app và reader; migration chạy lại không đổi hàm.
- [ ] `tests/test_v7_reconcile_auto.py`: đọc TONG; tạo sổ khi đủ điều kiện rồi lượt sau khớp; chỉ báo không ghi; container ở sổ khác; TONG lệch tab; chưa có trên TONG; quá nhiều sổ mới; lỗi ghi.
- [ ] `preview/test-viec-can-lam-table-browser.js`: số sổ đã tạo, các lý do mới, lý do của tab chưa nhận được; không tràn ngang ở 1280.
- [ ] Thử trên bản sao DB của `hao`: đúng 2 sổ mới, tổng tăng đúng bằng tổng 2 tab, sổ khác giữ nguyên, lượt sau không ghi thêm, checker đạt, dán thử chuyến vào sổ mới được.
- [ ] Bật trên `hao`, đối soát cho kết quả như bản thử; sổ mới mở được trên web.
- [ ] Chủ sổ mở sổ mới đầu tiên và xác nhận đúng khách.
