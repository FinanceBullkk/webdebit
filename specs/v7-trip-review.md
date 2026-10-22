# V7 — Kết luận chuyến CHỜ KIỂM (NEWTRIP-01)

Trạng thái: phần backend/API đã code trên nhánh `claude/v7-pending-review` (Claude, 22/10/2026), **chưa triển khai** lên `hao`. Giao diện chờ người dùng duyệt luồng (mục cuối). Đóng mục E1 của [checklist chạy song song](../docs/song-song-checklist.md).

## Vấn đề

Từ M2-11 ([spec](v7-m2-11-dedup.md)), dán lô có dấu hiệu trùng thì chuyến vào `pending_review`, nằm ngoài số dư và không sửa được. [`NEWTRIP-01`](../docs/decisions.md#newtrip-01) yêu cầu chủ nghiệp vụ "xem và kết luận có lý do", nhưng chưa có hàm nào làm việc đó: chuyến kẹt ngoài số dư mãi và đối soát tổng khách lệch mà không sửa được.

## Hành vi (Claude chốt theo quyền người dùng trao 21/10/2026)

- Lệnh mới `review_trip(customer_id, expected_version, idempotency_key, trip_id, decision, reason)`, API `POST /api/v7/trips/review` với `trip_id`, `decision`, `reason`.
- Hai kết luận:
  - `confirm` → chuyến thành `confirmed`, tính vào sổ như chuyến dán bình thường, rồi phân bổ lại các phiếu thu chưa hủy theo nợ cũ trước.
  - `reject` → chuyến thành `rejected`: giữ nguyên dòng để có vết, **không** tính tiền, không sửa được, không phân bổ lại.
- Lý do bắt buộc cho cả hai (`REVIEW_REASON_REQUIRED`), lưu đã trim; giới hạn 500 ký tự như các ô ghi chú khác.
- `confirm` cần tháng nợ của chuyến đang mở (`MONTH_LOCKED`), giống dán lô: nhập muộn = mở tháng → kết luận → khóa lại. `reject` không đổi tiền nên làm được cả khi tháng khóa.
- Chỉ kết luận một lần: chuyến không còn `pending_review` thì `TRIP_NOT_PENDING`. Muốn đổi ý sau khi đã tính vào sổ thì dùng công cụ sẵn có (điều chỉnh chuyến về 0).
- Chuyến `rejected` vẫn được coi là "chuyến web đã ghi" khi kiểm trùng lần dán sau, nên dán lại cùng container vẫn vào CHỜ KIỂM.
- Ai mở được sổ thì kết luận được ([`V7-ID`](../docs/decisions.md#v7-id), không người duyệt thứ hai theo `V6-DB`); người làm lấy từ phiên máy chủ.
- Mỗi lần kết luận ghi một dòng Lịch sử `trip_review`: trước `{trip, container, status: pending_review}`, sau `{trip, container, status, review_reason}`.
- `get_ledger` trả thêm `review_reason` trên mỗi chuyến: lý do bị giữ lúc dán (`BASELINE_CODE_MATCH`, `BASELINE_DATE_WINDOW`, `WEB_DUPLICATE`, `BATCH_DUPLICATE`). Chuyến CHỜ KIỂM dán trước bản này không có lý do (NULL).

## Schema và migration

- `sokhach.trip.status` thêm giá trị `rejected`; cột mới `reviewed_by_event` (FK tới `event` cùng khách); CHECK: `pending_review` thì chưa có event kết luận, `rejected` thì phải có.
- Trigger `trip_immutable` đổi sang `guard_trip_change()`: dòng chuyến vẫn chỉ thêm, ngoại lệ duy nhất là đổi một lần `pending_review` → `confirmed`/`rejected` kèm `reviewed_by_event`, mọi cột khác giữ nguyên. Mọi UPDATE/DELETE khác vẫn báo `immutable row`.
- `event.kind` thêm `trip_review`, CHECK snapshot buộc trạng thái trước là `pending_review`, sau là `confirmed`/`rejected` và có lý do.
- `paste_trips` ghi thêm `review_reason` vào snapshot dán cho chuyến bị giữ; không đổi tiền hay luật kiểm trùng.
- Migration `cong-no-web-handoff/tools/migrations/2026-10-22-v7-trip-review.sql`: một transaction, chạy lặp được, chạy sau `2026-10-21-v7-csm.sql`. Không viết lại dòng tiền nào.

## Kiểm

| Thao tác | Module | Kiểm |
| --- | --- | --- |
| Kết luận tính vào sổ / loại | `review_trip`, `reallocate`, `get_ledger` | Harness PostgreSQL case `7.25`: số dư, phân bổ lại phiếu, lý do bắt buộc, quyết định sai, chuyến không tồn tại, retry cùng key, khóa khác payload, kết luận lần hai, tháng khóa, chuyến loại không sửa giá và vẫn chặn trùng, UPDATE/DELETE trực tiếp bị chặn |
| Nâng DB đang có | migration | Harness: chuỗi `001-m2-11` → CSM → bản này cho ra cùng catalog hàm, cột, view như schema mới; lỗi giữa chừng rollback; chạy lại an toàn |
| Quyền | grants | `review_trip` chỉ cấp cho `sokhach_app`, reader bị từ chối; checker sau triển khai đòi có hàm |
| API | `v7_ledger_api.py` | unittest: route, quyết định hợp lệ, lý do trống, mã lỗi |

Không chạy trên `hao`, Sheet hay dữ liệu thật. Triển khai theo runbook: backup, restore thử, chạy migration trên bản sao, rồi DB thật khi người dùng xác nhận; checker và đối soát tổng khách sau đó.

## Giao diện (ĐỀ XUẤT, chờ duyệt luồng trước khi code)

Theo quy trình frontend, luồng mới cần người dùng duyệt trước. Đề xuất dùng lại khuôn "hủy phiếu hỏi lý do ngay trong bảng":

1. Ô thành tiền của chuyến CHỜ KIỂM hiện nút **CHỜ KIỂM** (như hiện nay, thêm bấm được).
2. Bấm vào thì mở một dòng ngay dưới chuyến: lý do bị giữ bằng chữ dễ hiểu ("Trùng mã với dòng sổ gốc", "Cùng container, lệch ngày ≤3 ngày với dòng sổ gốc", "Trùng chuyến đã nhập trên web", "Trùng trong cùng lô dán"), ô **Lý do kết luận**, hai nút **Tính vào sổ** và **Loại, không tính**, nút **Thôi**.
3. Tính vào sổ khi tháng khóa: báo "Tháng đang khóa" như các thao tác khác.
4. Chuyến đã loại: ô thành tiền ghi **ĐÃ LOẠI**, chữ gạch ngang, không sửa được.

Đã làm sẵn trong nhánh này (chỉ hiển thị, không đổi luồng): Lịch sử hiện dòng "Kết luận CHỜ KIỂM", nội dung "Chuyến <container>: tính vào sổ/loại, không tính" và lý do ở ô "Ghi chú/lý do".
