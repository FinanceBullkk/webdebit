# NEWTRIP-01 — kiểm trùng dán lô

Phạm vi: sửa luồng dán lô hiện có theo nhiệm vụ người dùng ngày 21/10/2026.
Không thêm bước thao tác, schema hoặc đường kết luận chuyến CHỜ KIỂM.
Không deploy, SSH, nạp nguồn hoặc ghi lên DB/Sheet thật.

## Tiêu chí

- Mã chuyến = booking chuẩn hóa + `|` + container chuẩn hóa; viết hoa, bỏ Unicode
  White_Space. Thiếu booking/chỉ ký hiệu dùng quy ước ALT hiện có của SQL:
  `ALT:<container>:<YYYYMMDD>|<container>`; ngày chưa biết là `UNKNOWN`.
- So mã chính xác hoặc cùng container lệch ngày tối đa 3 ngày (hai phía, gồm ngày thứ 3).
  So mốc đang active, chuyến web cùng sổ (mọi kỳ, kể cả đang chờ), rồi các dòng trước
  trong lô. Dòng nghi trùng lưu `pending_review`, không tính tiền, không sửa giá/điều chỉnh;
  dòng sạch còn lại ghi bình thường. Phí lẻ không container giữ hành vi hiện có.
- Mốc dùng `sokhach.baseline_trip_ref(cutover_id, booking_norm, container_norm,
  event_date)` đã có từ PR #50/#51. Không thêm bảng/cột. SQL kiểm dưới khóa khách
  của `_begin_command`, không tin trạng thái do client gửi. Thiếu tham chiếu vẫn
  fail-closed bằng `BASELINE_REF_MISSING`.

## Map kiểm

| Thao tác | Entry point | Kiểm |
|---|---|---|
| Dán fixture | `so-khach-v7-ui.js` → `parsePastedTrips` / `classifyPastedTrips` | node model: Unicode, ALT, ±3/±4, lô hỗn hợp, ngoài số dư |
| Dán web | UI → `/api/v7/trips/paste` → `sokhach.paste_trips` | API unit nhận booking, từ chối client status; harness `check_dedup`: đúng dòng chờ, đúng tổng, ±3/±4 cho web/lô |
| Xem dòng chờ | `get_ledger` → UI, cột Thành tiền | node renderer: phát sự kiện dán trên fixture và render GET giả; CHỜ KIỂM đúng dòng, không có ô sửa giá, dòng sạch vẫn hiện |

Kiểm chuẩn: `npm run check`; PostgreSQL: harness `test_pg_v7_backend.py --strict`
qua orchestrator ngoài sandbox; secrets: `node scripts/check-secrets.js` trước commit.
Kết quả thực chạy và giới hạn ghi trong PR; thêm test không đồng nghĩa đã chạy PostgreSQL.

## CÒN MỞ

- `decisions.md` NEWTRIP-01/SONG-SONG-02 ghi chưa cài, nhưng checkout đã có SQL
  cách ly và bảng mốc từ PR #50/#51. Tài liệu lịch sử không chứng minh runtime hiện tại;
  nhiệm vụ này không kiểm `hao` hay xác nhận tham chiếu thật đã nạp.
- Chi tiết ALT trong ALT-KEY-01 vẫn ghi ĐỀ XUẤT. Giữ quy ước đã có trong SQL/bộ nạp,
  không tự chốt chính sách mới. Không bổ sung booking thành cột thứ 8 của dữ liệu dán;
  UI giữ 7 cột, API nhận booking nếu caller cung cấp.
- Bộ nạp tham chiếu hiện có không lưu customer_id: so mốc theo cutover toàn bộ;
  web so trong cùng sổ. Không tự đổi phạm vi mốc/schema trong task này.
- Chưa có luồng chủ nghiệp vụ kết luận/giải phóng dòng chờ kèm lý do; không tự cho
  dòng chờ tính tiền. Fixture không có mốc thật; live SQL mới kiểm bảng mốc.
- Không nghiệm thu dữ liệu thật hoặc triển khai. Kiểm PostgreSQL/browser còn phụ
  thuộc môi trường được phép; không thay bằng kiểm tĩnh hoặc mock.
