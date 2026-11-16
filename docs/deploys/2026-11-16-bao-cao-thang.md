# Triển khai Báo cáo tháng (16/11/2026)

**ĐÃ CHẠY trên `hao` lúc 12:32 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), [`BAO-CAO-THANG-01`](../decisions/bao-cao-thang-01.md) và [runbook](../v7-deploy-runbook.md).

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Người dùng trong chat 16/11/2026 ("CI xanh, merge"); triển khai tay theo `DEPLOY-CLAUDE-01` |
| PR / release | #435, merge `dbd07ec`; release tay `dbd07ec` từ `c63bd41` |
| CI | 15/15 check của #435 xanh trên head `c5e4083` (gồm PostgreSQL `--migration-test`, grants, p0) |
| Migration | `2026-11-16-v7-bao-cao-thang.sql`, SHA-256 `1775ff3f2e1afe90004137a247d5f8f0697dd39c95b397b983e4304e8e574d2c` (trùng bản trên `main`) |
| Ghi tiền | Không. Chỉ thêm hàm đọc `get_trip_month` và quyền gọi cho `sokhach_app`, `sokhach_reader` |

## Gate và kết quả

**Trước khi làm:**
- Không có kết nối DB nào khác.
- `v7-reconcile-auto` không chạy.
- Không có lệnh sudo ghi của phiên khác; một phiên chỉ đọc file lúc 11:42.

**Thử trên bản sao:**
- Backup toàn phần `webdebit_v7` kèm hash; `pg_restore --list` đọc được 34 bảng; restore vào DB thử riêng. DB thử thu quyền `CONNECT` của PUBLIC như DB thật.
- Migration hai lượt (101 ms, 112 ms). Catalog ổn định giữa hai lượt và khác bản trước đúng một hàm.
- Dấu vân tay không đổi: 242 khách, md5 số dư từng khách, tổng nợ, số event, số chuyến.
- Checker đạt. Quyền: `sokhach_app` và `sokhach_reader` gọi được, PUBLIC không.
- `get_trip_month('2026-10-01')` khoảng 1,2 giây: 242 sổ, 521 chuyến, trong đó 163 chuyến sổ gốc và 463 chuyến trong tháng 10. `get_trip_month('2026-10-15')` báo `INVALID_MONTH`.
- Đã xóa DB thử.

**DB thật, 12:32:03:**
- Backup lần nữa ngay trước migration (34 bảng).
- Áp migration với `ON_ERROR_STOP`: 1 `COMMIT`, 163 ms.
- Catalog sau trùng bản thử.
- Dấu vân tay trước và sau trùng nhau: 242 khách, tổng nợ 57.755.939.064đ. Con số này khác lần thử vì lượt máy 12:05 đã ghi 6 event.
- Checker đạt, quyền đúng.
- Migration chỉ thêm hàm đọc, nên không cần cửa sổ dừng ghi.

**Release tay `dbd07ec` lúc 12:33:**
- Dùng đúng gói và script của `Deploy hao`.
- `/healthz` 200, unit active.
- Script cảnh báo không dọn được vài release cũ có file của user khác (đã có từ trước).

**Lần kiểm đầu tiên:**
- Chạy riêng phép kiểm booking một lần bằng mã release mới, như phần con của lượt máy. Phép kiểm chỉ đọc Sheet và bản chụp, không chạy lượt đối soát nên không ghi sổ.
- Ghi được `booking-report.json` (1,9 MB, mode 600) sau 246 giây.

## Kiểm trên trang thật

Trình duyệt máy làm việc qua Tailscale, `GET /api/v7/report/month?month=2026-10` trả trong 695 ms:

| Tháng 10/2026 | Biển | Bộ | Tổng |
| --- | ---: | ---: | ---: |
| Booking | 262 | 201 | 463 |
| Sheet sổ nợ | 262 | 201 | 463 |
| Web | 262 | 201 | 463 |

Ngoài ra:
- 13 dòng chép 0đ, 2 dòng Sheet không ngày.
- Hai cont booking có mà Sheet chưa ghi lúc đối chiếu tay sáng nay đã có trên Sheet.
- Trang báo một chuyến "Web chưa có" ở một sổ, nhưng web thật ra có chuyến đó. Lỗi do thứ tự ghép: dòng Sheet không ngày cùng container giành mất chuyến web. Đã sửa ở PR kế tiếp: dòng có ngày ghép trước.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261116-bao-cao-thang/` trên `hao` (quyền 700).

## Rollback

`DROP FUNCTION sokhach.get_trip_month(date);` (đã thử trên bản sao, không gì phụ thuộc). Release cũ không đọc file báo cáo.

## Còn mở

- Người dùng tự đi hết trang Báo cáo tháng trên `hao`.
