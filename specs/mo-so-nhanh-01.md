# Mở Sổ khách nhanh hơn, bước 1: giữ file ở trình duyệt, nén, đọc sổ song song (MO-SO-NHANH-01)

Trạng thái: ĐÃ CHỐT (người dùng, 4/11/2026, "Làm bước 1"; phạm vi tầng HTTP và thứ tự tải của trang Sổ khách, không đổi luật tiền, không đổi SQL)

## Người dùng và luồng

Người nhập mở Sổ khách (từ Tổng quan, Việc cần làm hoặc đổi khách ở tên) và đợi bảng hiện. Mỗi lần mở là một lần tải trang, nên mọi khoản cố định của trang cộng vào thời gian chờ.

Đo trên `hao` 4/11/2026 từ trình duyệt máy làm việc (qua Tailscale), bản `8946881` (sau #317):

| Khoản | Sổ thường (id 176, 54 KB) | Sổ lớn nhất (id 14, 397 KB) |
| --- | --- | --- |
| Tải 36 file JS/CSS (650 KB, `no-store`, không nén) | 330 ms | 500 ms |
| GET `/api/v7/ledger`, chỉ bắt đầu sau khi tải hết JS | 220 ms | 640 ms |
| Gọi thêm sau khi có sổ (ảnh chứng từ, trạng thái bảng giá) | 80 ms | 80 ms |

Với sổ thường, tải file lớn hơn cả GET sổ. Mạng chậm hơn (Tailscale qua relay, 4G) thì khoản tải file phình trước tiên.

## Đầu ra

- File JS/CSS/HTML trả `ETag` + `Cache-Control: private, no-cache`: lần mở sau trình duyệt chỉ hỏi "còn mới không" và nhận 304, không tải lại 650 KB; sau deploy lượt mở kế đã lấy bản mới (không dùng `max-age` để HTML và JS không lệch phiên bản).
- File ≥ 1 KB và JSON ≥ 1 KB nén gzip khi trình duyệt nhận (`Accept-Encoding`); bản gzip có ETag riêng, `Vary: Accept-Encoding`. JSON vẫn `no-store`.
- `so-khach-v7-prefetch.js` đứng đầu `<head>`: bắt đầu GET sổ của `?customer=` ngay khi trang mở; `create().read()` trong `so-khach-v7-api.js` dùng phản hồi đó đúng một lần cho lần đọc đầu cùng mã khách. Lỗi hoặc đổi khách thì fetch như thường. Số lần GET sổ khi mở trang không đổi (một).

## Giao tiếp frontend–backend

Không thêm route. `GET /api/v7/ledger` giữ nguyên tham số và thân; chỉ thêm header `Content-Encoding: gzip` khi được nhận. Static: thêm `ETag`, `Vary`, đổi `Cache-Control` từ `no-store` sang `private, no-cache`; `If-None-Match` khớp trả 304 không thân. CSP, `X-Frame-Options`, `nosniff` giữ nguyên ở 200.

## Nguồn quyết định

- Không đụng quyết định nghiệp vụ nào trong `docs/decisions.md`. Bước 2 (tách lịch sử/dòng sổ gốc ra endpoint riêng) và bước 3 (cache `get_ledger` theo `version`) CÒN MỞ, chưa làm.

## Hành vi và bất biến

- Không cache JSON ở trình duyệt (`no-store` giữ nguyên): số dư luôn đọc từ server.
- Bộ nhớ file trong tiến trình theo `(mtime_ns, size)`; deploy thay thư mục release và khởi động lại dịch vụ.
- Thẻ script mới đúng dạng `<script src="x.js"></script>` để `page_assets` (v7_api_tables.py) nhận ra và phục vụ.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_ledger_api.py::LedgerHttpTest::test_assets_revalidate_by_etag_and_gzip_when_accepted`: ETag, 304, gzip có ETag riêng, file đổi thì ETag đổi, JSON nhỏ không nén, JSON lớn nén khi nhận.
- [x] `preview/test-so-khach-v7-api.js`: lần đọc đầu dùng bản tải sớm một lần; khác mã khách thì không; tải sớm lỗi thì Thử lại fetch thường; trang live nạp prefetch trước api.
- [x] Test trình duyệt tải lại trang bằng `reload(page)` của `so-khach-v7-browser-world.js` (chờ danh sách khách về) thay vì `page.reload()` thẳng: CI windows 4/11/2026 đỏ vì `loadCustomers()` vẽ lại cả sổ đúng giữa lúc test lấy phần tử và đo (rect = 0); tái hiện tại máy 5/6 lần khi `/api/v7/customers` chậm 30 ms, có chờ 0/12.
- [ ] `npm run check` xanh; `node scripts/check-secrets.js` sạch.
- [ ] Sau deploy lên `hao`: đo lại cùng hai sổ, lần mở thứ hai tải file trả 304, GET sổ bắt đầu trước khi tải hết JS; ghi số vào PR.

## Phạm vi agent

- Agent: claude
- Review: sonnet medium
- Được sửa:
  - `cong-no-web-handoff/web/v7_ledger_api.py`
  - `cong-no-web-handoff/preview/so-khach-v7-prefetch.js` (mới)
  - `cong-no-web-handoff/preview/so-khach-v7-api.js`
  - `cong-no-web-handoff/preview/so-khach-v7-live.html`
  - `cong-no-web-handoff/tests/test_v7_ledger_api.py`
  - `cong-no-web-handoff/preview/test-so-khach-v7-api.js`
- Ngân sách diff: 250 dòng
