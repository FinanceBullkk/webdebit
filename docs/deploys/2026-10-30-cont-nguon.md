# Đổi nguồn đồng bộ chuyến sang CONT_NGUON (30/10/2026)

**ĐÃ CHẠY trên `hao` 30/10/2026.** Không migration, không đổi DB, không ghi tiền, không ghi Sheet. Claude tự làm theo [runbook](../v7-deploy-runbook.md#đổi-nguồn-đồng-bộ-chuyến-sang-cont_nguon--đối-chiếu-rồi-đổi-mặc-định-giai-đoạn-2a-đã-chạy-trên-hao-30102026) sau khi phía giữ file CHAU_HAO báo đã dựng tab `CONT_NGUON` (0 lệch với `BOOKING_DATA` theo tab `DOI_CHIEU_NGUON` của họ) và nhờ web đổi nguồn rồi báo lại.

| Mục | Nội dung |
| --- | --- |
| Spec | [`v7-sheet-contract`](../../specs/v7-sheet-contract.md), mục "Giai đoạn 2a" |
| PR | FinanceBullkk/webdebit#204 (đường đọc mới, `--source`, công cụ so; release `c83cc58`, Deploy hao xanh), PR đổi mặc định đi kèm nhật ký này |
| Sheet | Không ghi gì. Các tab web đọc giữ nguyên; `BOOKING_DATA` và `CONT_BO` chờ phía Sheet bỏ sau nhật ký này |

## Đối chiếu (bước 1–2 runbook)

Bản chụp thử `--source cont_nguon` lúc 09:55 UTC so với `snapshot.json` đường cũ lúc 09:45 UTC, bằng `v7_sheet_source_diff.py`, chạy cùng user `v7app` và env của runner:

| Chỉ số | Đường cũ (`WEBDEBIT_EXPORT` + `BOOKING_DATA`) | `CONT_NGUON` |
| --- | --- | --- |
| Dòng | 5.404 | 5.576 |
| `READY` | 5.381 | 5.381 |
| `INVALID` | 23 | 195 (đều có Cờ lỗi) |
| `READY` chỉ có ở một bên | 0 | 0 |

`identical_ready: true`, mã thoát 0. Khác nhau còn lại: 92 khóa `INVALID` chỉ có ở bản mới (dòng thiếu số cont mà công thức `FILTER` của `WEBDEBIT_EXPORT` đã bỏ) và 23 dòng `INVALID` nay có booking, chủ hàng, shipper, 3 dòng có loại sầu riêng, vì không còn qua phép ghép 5 trường. Hai file tạm (có tên khách) đã xóa ngay sau khi lấy số.

## Đổi mặc định (bước 3)

PR đổi `DEFAULT_SOURCE = "cont_nguon"`; đường `export` giữ để quay lại.

## Kiểm sau deploy

(điền sau lượt timer đầu)

## Rollback

Drop-in cho `webdebit-sheet-sync.service`: `Environment=WEBDEBIT_SHEET_SOURCE=export`, `daemon-reload`, chạy một lượt. Chỉ còn tác dụng khi `BOOKING_DATA` và `WEBDEBIT_EXPORT` chưa bị xóa trên Sheet.

## CÒN MỞ

- Phía Sheet bỏ `BOOKING_DATA`, `CONT_BO`, `WEBDEBIT_EXPORT` (web đã báo được bỏ 30/10/2026 sau lượt timer đầu; API không đọc `WEBDEBIT_EXPORT`, runner chỉ còn đọc nó ở đường quay lại).
- Sau đó PR bỏ đường `export` trong `sheet_sync_runner.py` và `webdebit_export_connector.py`.
- Chuyến `Loại = BỘ` chưa đồng bộ; cần quyết định riêng và `WEB_GHEP_KHACH` đủ tên chủ hàng đường bộ.
