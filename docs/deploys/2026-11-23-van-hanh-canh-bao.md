# Triển khai: nhiều check cảnh báo, máy kéo tự báo, ghim lại sao lưu (audit vận hành 23/11/2026, O2, O4, O5, O8)

Nguồn: `D:\webdebit\audits\2026-11-23-web-audit\ops-findings.md` (ngoài repo). Mã lên bằng `Deploy hao` của PR #607
(`3863befe`, run 45176997972 xanh). Phần tay trên `hao` và ba PC kéo làm theo [`TU-LAM-01`](../decisions/tu-lam-01.md):
chép bản cũ trước khi ghi. Link ping không ghi vào đây.

| Mục | Nội dung |
| --- | --- |
| Code | PR #607: máy canh chia nhóm (`tools/v7_watchdog.py`), PC kéo ping sau `PASS` (`v7_offsite_pull.py`), gói cấu hình thêm đường dẫn và bảng kê (`v7_backup.py`), gói release theo danh sách |
| SQL, DB, tiền | Không đổi |
| Tay trên `hao` | `/etc/webdebit/alert.env` thêm bốn biến link nhóm; ghim lại `v7_backup.py`; chạy một lượt gói cấu hình |
| Tay trên PC | Ba PC: script kéo mới, file link riêng, task thêm `--ping-url-file` |
| healthchecks.io | Check cũ đổi tên `webdebit nhịp sống`; thêm 4 check nhóm (15 phút / 45 phút) và 3 check kéo, mỗi PC một (1 ngày / 1 ngày); cả 8 bật email |

## Trên `hao` (giờ VN, 23/11/2026)

1. 19:34 — chép `alert.env` thành `alert.env.bak-20261123-123449` (cùng thư mục), thêm
   `WEBDEBIT_ALERT_PING_URL_TIEN`, `_LUOI`, `_SAOLUU`, `_ZALO`; giữ dòng check chính. Sau: `root:v7app 640`.
2. 19:44 — chép bản ghim cũ thành `v7_backup.py.bak-20261123`, cài `v7_backup.py` từ release `3863befe` vào
   `/opt/webdebit-backup/cong-no-web-handoff/tools/` (`root:root 644`). SHA-256 `be3b6a4b…2a2753` khớp `git show 3863befe:…`
   (bản trước `c5bf0897…`).
3. 19:45 — `systemctl start v7-backup-config.service`: `Result=success`, 118 file, 12 symlink, `missing` chỉ
   `command:inventory/lvm.txt` (máy không dùng LVM; [rebuild-hao.md](../rebuild-hao.md) bước 2 đã ghi là mẫu đã biết).
4. `systemctl start v7-watchdog.service`: `{"ok": true, "problems": [], "configured": true, "checks": 5}`.

## Trên ba PC kéo

Mỗi PC: so SHA-256 script mới với `git show 3863befe:cong-no-web-handoff/tools/v7_offsite_pull.py` (`37a690bb…020786`),
chép bản cũ thành `v7_offsite_pull.py.bak-20261123-1935xx`, ghi `ping-url.txt` trong thư mục bản kéo, thêm
`--ping-url-file "<thư mục bản kéo>\ping-url.txt"` vào task `Webdebit V7 Backup Pull`, chạy task một lần.

| PC | Kết quả 19:35 |
| --- | --- |
| `pc-cu` | `PASS pulled=2 … config_pulled=2 … \| pinged` |
| `desktop` | `PASS pulled=1 … config_pulled=1 … \| pinged` |
| `msi` | `PASS pulled=1 … config_pulled=1 … \| pinged` |

## Thử email (đóng E3)

- 19:47 — `v7_watchdog.py --test-fail` dưới `v7app` với `alert.env` (`systemd-run`): `"checks": 5`. healthchecks.io
  báo 5 check down; hộp thư chủ sổ nhận đủ 5 email `DOWN | webdebit …` (nhịp sống, tiền, lưới an toàn, sao lưu, Zalo).
- Chạy lại máy canh một lượt: `"ok": true`; 5 email `UP` tới; trang check không còn check down. Ba check kéo xanh từ 19:35.

## Rollback

`alert.env`: chép lại bản `.bak-20261123-123449`, mọi nhóm về check chính. Bản ghim: chép lại `.bak-20261123`. PC: chép lại
`.bak-…` và bỏ `--ping-url-file` khỏi task (script cũ không biết cờ này).

## Còn mở

- Phần hộp việc của O4 (lỗi máy 15 phút lặp hai lượt, thiếu cờ `WEBDEBIT_AUTO_SHEET`) đi cùng PR có nhật ký này, chỉ
  qua `Deploy hao`, không bước tay: cờ phải có mặc định đúng drop-in `auto-sheet.conf` hiện tại trên `hao`.
- Dừng thử máy canh quá thời gian chờ (spec [`v7-canh-bao`](../../specs/v7-canh-bao.md)) chưa làm.
- Diễn tập dựng lại máy (E1) chưa có máy.
