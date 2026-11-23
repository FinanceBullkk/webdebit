# Vận hành: cái gì chạy ở đâu

Trang một chỗ cho người lạ phải trông hệ thống (audit vận hành 23/11/2026, O11). Chi tiết cài từng phần ở
[runbook](v7-deploy-runbook.md); tự động deploy ở [hao-auto-deploy.md](hao-auto-deploy.md); dựng lại máy ở
[rebuild-hao.md](rebuild-hao.md). Trạng thái ghi theo 23/11/2026; báo cáo cũ không là trạng thái hôm nay, kiểm lại trên máy.

## Máy và việc

`hao` là laptop cũ một ổ HDD trong tailnet, chạy PostgreSQL 18 (DB V7 và hai DB legacy), API, các máy theo Sheet, sao lưu và máy
canh. Người dùng mở web qua Tailscale Serve (cổng 8443 → API `127.0.0.1:8780`). Mã chạy từ `/srv/v7/auto-releases/current`
(symlink tới release theo SHA của `main`), trừ sao lưu chạy bản ghim `/opt/webdebit-backup`.

| Việc | Ở đâu, nhịp | Ghi tiền? | Ai biết khi nó dừng (check healthchecks.io) | Dừng bằng |
| --- | --- | --- | --- | --- |
| API + web (`v7-ledger-api`) | `hao`, luôn chạy | qua nút bấm của người dùng | tiền (`/healthz` không 200) | `systemctl stop v7-ledger-api` (web tắt hẳn) |
| Máy 15 phút trong API (dán chuyến, ghi giá, phí PS, chữ, tách phí) | `hao`, nhịp nền mỗi phút, tính lại mỗi đợt bản chụp | **có** | tiền (hộp việc không tính được, cũ quá 90 phút, máy lỗi hai lượt liền, thiếu cờ) | bỏ cờ trong `WEBDEBIT_AUTO_SHEET` (drop-in `auto-sheet.conf` của API), `daemon-reload`, restart |
| Máy đối soát (`v7-reconcile-auto`) | `hao`, mỗi giờ :05 từ 7 tới 22 giờ | **có** (`--fix`) | tiền (cũ quá 3 giờ trong ngày, lỗi ghi, chạy không `--fix`, cầu dao 40 khách hai lượt) | `systemctl disable --now v7-reconcile-auto.timer` |
| Bản chụp Sheet (`webdebit-sheet-sync`, `-sheet-prices`, `-ps-snapshot`) | `hao`, 15 phút | không | tiền (file cũ quá 60 phút, nguồn booking trống 3 ngày) | `systemctl disable --now <tên>.timer` |
| Thông tin cty (`webdebit-company-info`), nút Làm mới (`.path`) | `hao`, mỗi giờ :20 / khi bấm | không | không ai (chỉ chữ trên trang) | `systemctl disable --now` |
| Sao lưu DB (`v7-backup-hourly`, `-daily`), gói cấu hình (`-config`), hộp chờ ngoài máy (`-offsite`) | `hao`, mỗi giờ / 02:40 / 02:50 / 03:00 | không | sao lưu (timer tắt, lỗi, quá 12/26 giờ; đĩa dưới 10%) | `systemctl disable --now <tên>.timer` |
| PC kéo bản sao (`Webdebit V7 Backup Pull`) | các PC, mỗi ngày 04:30/04:40 | không | sao lưu (không khóa kéo nào đăng nhập 48 giờ) và check riêng của từng PC (kéo không `PASS`) | `Disable-ScheduledTask` trên PC |
| Lưới an toàn (bốn phép kiểm chỉ đọc trên sổ thật) | trong máy canh, 15 phút | không | lưới an toàn | không cần dừng; chấp nhận một phát hiện bằng `v7_safety_net.py --accept` |
| Máy Zalo (agent đọc Zalo/WeChat, đẩy gói lên `hao`) | PC `msi`, mỗi phút | không | Zalo (7–20 giờ: im quá 15 phút, Zalo/WeChat chưa mở, lỗi xử lý) | task `ZaloAgent` trên `msi` |
| Bot Zalo hỏi đáp (`v7-zalo-bot`, `v7-zalo-kenh`) | `hao` | không | Zalo | CHƯA CÀI |
| Máy canh (`v7-watchdog`) | `hao`, 15 phút | không | **nhịp sống**: không ping 15 + 45 phút thì healthchecks.io gửi email | `systemctl disable --now v7-watchdog.timer`, rồi Pause mọi check |
| Log sửa Sheet (Apps Script) | Google | không | tiền (không dòng mới 26 giờ) | trong Apps Script |
| `Deploy hao`, `Tests`, `flaky-nightly`, Dependabot | GitHub | không | email GitHub khi job đỏ | tắt workflow trên GitHub |

## Ai biết khi có chuyện

Máy canh trên `hao` (15 phút) gom phép kiểm thành nhóm, mỗi nhóm một check trên healthchecks.io: **tiền**, **lưới an toàn**,
**sao lưu**, **Zalo**, cộng check chính là **nhịp sống**; mỗi PC kéo một check riêng ([`CANH-BAO-01`](decisions/canh-bao-01.md)).
healthchecks.io chỉ gửi email khi check đổi trạng thái: check đang đỏ thì lỗi mới cùng nhóm không có email mới, xem trang của
check hoặc `journalctl -u v7-watchdog.service -n 5 -o cat`. Nghỉ dài muốn yên thì Pause check của nhóm ồn, không Pause nhịp sống.

Không có email cho: khách cần xem, web đi trước Sheet, tab chưa tạo được sổ (đầu tab Việc cần làm); thông tin cty; Hermes ở PC
(tab Máy chạy). Tab **Máy chạy** trên web hiện trạng thái từng job trực tiếp.

## Dừng mọi máy ghi tiền

Theo thứ tự, trên `hao` (sudo); nhớ ghi nhật ký vào `docs/deploys/`:

1. `systemctl disable --now v7-reconcile-auto.timer` — máy đối soát.
2. Sửa `/etc/systemd/system/v7-ledger-api.service.d/auto-sheet.conf` thành `Environment=WEBDEBIT_AUTO_SHEET=` (chép bản cũ ra
   trước), `systemctl daemon-reload`, `systemctl restart v7-ledger-api` — máy 15 phút trong API. Web vẫn mở, người vẫn bấm được.
   Máy canh sẽ báo nhóm tiền vì thiếu cờ: đúng ý. Dừng lâu thì thêm `WEBDEBIT_ALERT_AUTO_FLAGS=` (trống) vào `alert.env`,
   bật lại thì bỏ dòng đó.
3. Muốn chặn cả người bấm: `systemctl stop v7-ledger-api` (web tắt). Máy canh sẽ báo nhóm tiền: là đúng.

Bản chụp Sheet, sao lưu, máy canh, Zalo không ghi tiền, để chạy. Bật lại theo thứ tự ngược, đối soát tổng khách trước khi bật
máy đối soát. Máy chỉ báo không ghi: bỏ `--fix` khỏi `ExecStart` của `v7-reconcile-auto` (máy canh sẽ báo chế độ `report`).

## Đưa mã lên

Merge vào `main` → `Tests` xanh → `Deploy hao` đẩy gói theo [`scripts/deploy/release-paths.txt`](../scripts/deploy/release-paths.txt)
(chỉ file chạy thật, không migration/SQL/test). Diff có migration, `.sql` hay loader thì job dừng: áp tay theo runbook, file SQL
chép riêng bằng `git show <sha>:<đường dẫn>` và so SHA-256, rồi release tay bằng cùng danh sách. Sao lưu chạy bản ghim: đổi
`v7_backup.py` thì ghim lại (B1 của runbook). Mọi việc tay trên `hao` có nhật ký trong [`deploys/`](deploys/).

## Khi `hao` chết

Dữ liệu: bản ngày (02:40) mà các PC đã kéo, mã hóa `age`; bản mỗi giờ không rời ổ `hao`. Dựng lại theo
[rebuild-hao.md](rebuild-hao.md) (CÒN MỞ: chưa diễn tập trên máy khác). Trong lúc chưa dựng xong, Sheet vẫn là sổ chính thức
([`SONG-SONG-01`](decisions/song-song-01.md)): người nhập tiếp tục trên Sheet, máy sẽ theo lại sau khi `hao` chạy.

## Nhìn ở đâu

| Cần | Lệnh hoặc chỗ |
| --- | --- |
| Máy canh thấy gì | `journalctl -u v7-watchdog.service -n 5 -o cat` |
| Lượt đối soát | tab Việc cần làm; `/var/lib/webdebit-sheet-sync/reconcile.json`, `reconcile-log.jsonl` |
| Máy 15 phút | `journalctl -u v7-ledger-api --since -1h \| grep "V7 máy"`; `/healthz` phần `inbox` |
| Sao lưu | `journalctl -u v7-backup-daily -n 1 -o cat`; `pull.log` trên PC |
| Release đang chạy | `cat /srv/v7/auto-releases/current/.release-sha`; tab Environments → hao trên GitHub |
