# Triển khai lưới an toàn (18/11/2026)

**ĐÃ CHẠY trên `hao` lúc 06:38 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), [`LUOI-AN-TOAN-01`](../decisions/luoi-an-toan-01.md) và [runbook](../v7-deploy-runbook.md#lưới-an-toàn-luoi-an-toan-01--nâng-db-và-drop-in-cho-máy-canh).

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Người dùng chọn làm lưới an toàn 18/11/2026 (phiên riêng); triển khai tay theo `DEPLOY-CLAUDE-01` |
| PR / release | #461, merge `4173ae4`; release tay `4173ae4` từ `30f3abe` |
| CI | 17/17 check của #461 xanh trên head `aad32bd` (gồm `postgres-v7-luoi-an-toan`, `--migration-test`, grants, p0) |
| Migration | `2026-11-18-v7-luoi-an-toan.sql`, SHA-256 `87793348a62116fa142979e82c61911a4440fd2790bafb1f25289350ac52bbbf` (trùng bản trên `main`) |
| Ghi tiền | Không. Chỉ thêm ba hàm đọc và quyền gọi hàm chính cho `sokhach_app` |
| systemd | Drop-in `/etc/systemd/system/v7-watchdog.service.d/luoi-an-toan.conf` (`StateDirectory=v7-watchdog`, mode 700), đúng như runbook |

## Thử trên bản sao (06:30–06:35)

- Backup toàn phần `webdebit_v7` kèm hash; `pg_restore --list` đọc được; khôi phục vào DB thử riêng, thu quyền `CONNECT` của PUBLIC như DB thật.
- Migration hai lượt, 112 ms mỗi lượt. Dấu vân dữ liệu trùng trước/sau: 242 sổ, md5 số dư từng sổ từng tháng, số dòng Lịch sử, chuyến, dòng chia phiếu. Catalog thêm đúng 3 hàm; app gọi được thêm đúng 1 hàm.
- Checker đạt 9/9.
- Gọi lưới an toàn bằng `v7_app` trong giao dịch chỉ đọc trên dữ liệu thật của bản sao: **sạch**. Không phiếu thu nào chia lệch; Tổng quan khớp tổng các sổ ở mọi mục; cả 242 sổ khớp tổng `get_ledger` (10,9 giây cho cả 242 sổ); Lịch sử 11 khối. Một lượt như máy canh (1/8 số sổ, 30 sổ) 3,1 giây.
- Đã xóa DB thử.

## DB thật, 06:38:58

- Không kết nối nào khác vào `webdebit_v7`; máy đối soát không chạy (lượt kế 07:05).
- Backup lần nữa ngay trước migration; `pg_restore --list` đọc được.
- Áp migration với `ON_ERROR_STOP`: 156 ms.
- Dấu vân trước và sau trùng nhau (242 sổ, md5 số dư, Lịch sử, chuyến, dòng chia); catalog sau trùng bản thử.
- Checker đạt 9/9. Quyền: `v7_app` gọi được `get_safety_net`; `sokhach_reader` không; hai hàm phụ không cấp ai.
- Chỉ thêm hàm đọc nên không cần cửa sổ dừng ghi.

## Release và máy canh

- Release tay `4173ae4` lúc 06:39 bằng đúng gói và script của `Deploy hao`: `/healthz` 200, unit active, `.release-sha` = `4173ae4`. Script cảnh báo không dọn được vài release cũ có file của user khác (đã có từ trước).
- Lượt máy canh chạy tay trước drop-in: mục lưới an toàn chạy được trong sandbox của unit (vào DB bằng `v7_app`), 242 sổ, phần 6/8 (30 sổ), không báo, `"ok": true`.
- Cài drop-in, `systemd-analyze verify`, `daemon-reload`, chạy lượt đầu: systemd tạo `/var/lib/v7-watchdog` (chủ `v7app`, 700); mốc `luoi-an-toan.json` 73 KB, mode 600; `"baseline": "lần đầu, lấy mốc"`, `"ok": true`.
- Lượt theo lịch 06:47 so với mốc: `"baseline": "so với lượt 06:39 ngày 18/11"`, phần 7/8, không mục chờ, `"ok": true`.

## Lệnh chạy tay `--full` lỗi một lần, đã sửa

Ngay sau release, lệnh `--dry-run --full` (so `get_ledger` của mọi sổ, 8 câu SQL) lỗi `DB_UNAVAILABLE` ở một câu; không ghi gì (`--dry-run`). Chạy lại từng phần thì cả 8 phần đều sạch, 3,6–4,8 giây mỗi phần, riêng phần 0 mất 11,7 giây. Đo từng sổ: sổ 104 mất 8,3 giây mở bằng `get_ledger` lúc API vừa khởi động lại và đang tính lại hộp việc (cả 242 sổ 22,6 giây, trên bản sao lúc máy rảnh 10,9 giây). Câu chạy quá 15 giây (giới hạn mỗi câu của adapter) thì bị dừng, nên lượt máy canh rơi vào phần đó lúc máy bận có thể báo nhầm "Không kiểm được".

Sửa ở PR kế tiếp: câu đọc nền (`read_only`) được chạy tới 60 giây, lệnh của người dùng vẫn 15 giây. Lên `hao` qua `Deploy hao` (không có SQL). Kiểm lại sau khi lên: ghi ở PR đó.

## Rollback

Tắt kiểm 3, 4: xóa drop-in, `daemon-reload`. Gỡ hàm: `DROP FUNCTION sokhach.get_safety_net(jsonb), sokhach._safety_fingerprints(), sokhach._safety_events(bigint,interval);` (đã thử trên bản sao: không gì phụ thuộc). Release cũ không gọi hàm này.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261118-luoi-an-toan/` trên `hao` (quyền 700).

## Còn mở

- Chưa có email thật nào của mục mới (chưa có lượt nào báo lỗi thật); email thử của máy canh (mục E3 của checklist) vẫn chưa ghi nhận.
- Sổ 104 mở chậm (8 giây khi máy bận): ảnh hưởng cả trang sổ đó, ngoài phạm vi đợt này. Nguyên nhân là JIT của PostgreSQL; xử lý ở [MO-SO-NHANH-03](../../specs/mo-so-nhanh-03.md), lên `hao` 08:55 cùng ngày ([nhật ký](2026-11-18-mo-so-tat-jit.md)).
