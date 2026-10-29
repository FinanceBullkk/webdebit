# Tự động đưa bản sửa lên hao

| Trạng thái | Phạm vi |
| --- | --- |
| ĐÃ CHỐT | Người dùng chọn cách 2 (GitHub Action đẩy qua Tailscale), 23/10/2026 |
| ĐÃ TRIỂN KHAI | `hao`, 23/10/2026: user deploy, script root-owned, sudoers, khóa SSH một lệnh, unit trỏ symlink release, Tailscale tag `tag:ci`, Environment `hao` có người duyệt. **28/10/2026:** người dùng bỏ *Required reviewers* (dự án chỉ một người làm), Environment chỉ còn luật nhánh `main`; kiểm bằng GitHub API cùng ngày |
| ĐÃ KIỂM CHỨNG | Lượt `Deploy hao` xanh trên GitHub cho commit `3608c9d` (từ đầu tới cuối: Tailscale, SSH, đẩy gói, restart, kiểm sống). Script thử trong Docker với `systemctl`/`curl` giả: deploy, tự quay lại khi kiểm sống lỗi, bỏ qua cùng SHA, từ chối SHA sai |
| CÒN MỞ | Tự quay lại khi kiểm sống lỗi chưa thử trên `hao` thật; kiểm sống chỉ chứng minh tiến trình sống, không chứng minh sổ đúng; giao diện sau deploy cần người dùng thử tay; action dùng tag (`@v4`, `@v3`), nên ghim SHA |

Luồng: merge vào `main` → `Tests` xanh trên đúng SHA → job `Deploy hao` tự chạy (Environment `hao`, không người duyệt từ 28/10/2026)
→ runner GitHub vào Tailscale → SSH bằng khóa chỉ chạy được một lệnh → `scripts/deploy/hao-release.sh`
trên `hao` nhận gói mã, đổi symlink release, restart service, kiểm sống, lỗi thì tự quay lại bản trước.
Chạy lại một SHA bất kỳ trên `main`: Actions → Deploy hao → Run workflow, nhập SHA đầy đủ.
Mỗi lượt ghi bảng *Tóm tắt triển khai* (kết quả, SHA trước/sau, commit trong đợt); đây là nhật ký triển khai app, không cần PR tài liệu riêng.

## Phạm vi và những gì bị chặn

- Chỉ đổi release của app (`cong-no-web-handoff/{web,preview,tools}`), như mục "Giao diện sửa/xóa tại ô" trong
  [runbook](v7-deploy-runbook.md#giao-diện-sửaxóa-tại-ô--chỉ-đổi-release-app-đã-chạy-trên-hao-22102026).
- Diff so với bản đang chạy có `specs/v7-backend/`, `tools/migrations/`, file `.sql` hoặc loader `v7_load*`
  → job **dừng**, phải triển khai tay theo runbook (backup, bản sao, gate). Job không chạy DDL, không nạp dữ liệu; Claude tự làm đợt tay cho SQL/migration theo [`DEPLOY-CLAUDE-01`](decisions/deploy-claude-01.md).
  Sau khi nâng DB tay, đặt `.release-sha` của release đang chạy bằng SHA `main` vừa triển khai để lượt sau có mốc diff đúng.
- Không backup DB mỗi lượt vì không đụng DB.
- Đạt: service active và cổng loopback trả 200/403 trong 30 giây; không thì quay lại release cũ, job đỏ.

## Cài đặt một lần (người dùng/admin, ngoài repo)

1. **Hao:** tạo OS user `webdebit-deploy`; thư mục release riêng thuộc user này (khác thư mục release cũ để
   script dọn dẹp không đụng bản cũ). Chép `scripts/deploy/hao-release.sh` từ commit đã review, **kiểm SHA-256**,
   rồi cài vào đường dẫn root-owned. `/etc/webdebit-deploy.conf` (root-owned): `RELEASES_DIR`, `CURRENT_LINK`,
   `UNIT`, `HEALTH_URL` (loopback, một route thật như `/api/v7/customers`: 200 hoặc 403 là sống, 404 bị coi là lỗi).
2. **Unit hiện tại:** đổi một lần `WorkingDirectory`/`ExecStart` sang `CURRENT_LINK` (symlink); chép release đang chạy
   làm bản đầu, ghi `.release-sha` bằng SHA thật của nó; lưu bản unit cũ để rollback; `daemon-reload`, restart.
3. **sudoers:** cho `webdebit-deploy` đúng một lệnh không mật khẩu: `systemctl restart <unit>`; kiểm `visudo -c`.
4. **Khóa SSH:** cặp khóa riêng cho deploy; trong `authorized_keys` đặt
   `command="/đường/dẫn/script",restrict` trước khóa công khai. Khóa này không mở được shell.
   Private key chỉ đi vào secret GitHub, không dán vào chat/ticket, rồi `shred` trên `hao`.
5. **sshd:** nếu `sshd -T` có `allowusers` thì user deploy bị từ chối ("not listed in AllowUsers"). Thêm bằng file riêng,
   chỉ cho đăng nhập từ dải Tailscale: `AllowUsers webdebit-deploy@100.64.0.0/10` trong
   `/etc/ssh/sshd_config.d/`; chạy `sshd -t` trước khi `reload`, giữ một phiên SSH đang mở phòng lỡ cấu hình sai.
6. **Tailscale:** `tagOwners` cho `tag:ci`; OAuth client scope Auth Keys → Write, tag `tag:ci`. Nếu chính sách mặc định
   "mọi thiết bị vào mọi thiết bị" (`"src": ["*"]`) thì quy tắc hẹp cho `tag:ci` vô tác dụng: thu hẹp quy tắc cũ về
   `autogroup:member` và thêm grant `tag:ci` → `hao` chỉ `tcp:22` (dùng `hosts` map cho `hao`).
   Máy nào gắn tag sẽ mất quyền ra ngoài sau khi thu hẹp: kiểm trước.
7. **GitHub:** Settings → Environments → `hao`, giới hạn *Deployment branches* về `main` (không bật *Required reviewers*: người dùng bỏ 28/10/2026). Secrets: `HAO_SSH_USER`,
   `HAO_SSH_KEY_B64` (private key base64 một dòng: `sudo base64 -w0 /tmp/<khóa>`; dán nhiều dòng từ terminal làm hỏng
   định dạng, lỗi `libcrypto`), `HAO_TS_OAUTH_CLIENT_ID`, `HAO_TS_OAUTH_SECRET`. Variables: `HAO_SSH_HOST` (tên Tailscale),
   `HAO_SSH_KNOWN_HOSTS` (một dòng `<tên> ssh-ed25519 <khóa>` lấy từ `/etc/ssh/ssh_host_ed25519_key.pub` trên `hao`;
   tên phải trùng `HAO_SSH_HOST`). Không ghi giá trị vào repo.

## Lỗi đã gặp khi cài (23/10/2026)

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `Load key ... error in libcrypto` | Private key dán nhiều dòng bị sai định dạng | Dùng `HAO_SSH_KEY_B64` |
| `Permission denied (publickey)` dù khóa đúng | `AllowUsers` của sshd chỉ liệt kê tài khoản khác | Bước 5; xem `journalctl -u ssh` |
| Test Postgres lỗi `the database system is starting up` | Container CI chưa sẵn sàng | Chạy lại job lỗi |
| `ssh-keyscan` Windows báo `unsupported KEX` | Bản OpenSSH Windows cũ | Lấy host key trực tiếp trên `hao` (bước 7) |
| `rm: cannot remove '…/<sha>/…/__pycache__/….pyc': Permission denied` sau dòng `đã chạy <sha>` (29/10/2026, `376a5bd`) | Service chạy Python ghi `__pycache__` vào release; user deploy không xóa được khi dọn bản cũ. Bản mới đã chạy và kiểm sống xong, chỉ bước dọn làm đỏ | Script trên `main` từ 29/10/2026 chỉ cảnh báo (cần cài lại trên `hao`); admin làm một lần các bước dưới |

### Dọn `__pycache__` của release cũ (admin, root, một lần)

**ĐÃ CHẠY trên `hao` 29/10/2026** (Claude, theo [`DEPLOY-CLAUDE-01`](decisions/deploy-claude-01.md)). Script cài đúng SHA-256 `fed3944b…`. Bước 2 làm bằng drop-in `no-bytecode.conf` thay cho `systemctl edit`; API sống lại (403). Đã xóa 1 thư mục `__pycache__`. Bản script và unit cũ lưu trong `/srv/backups/deploy-script-20261029-153500`. Chưa có lượt deploy code app nào chạy qua script mới.

1. Cài lại `scripts/deploy/hao-release.sh` từ `main` như bước 1 (kiểm SHA-256, giữ đường dẫn root-owned).
2. Tắt ghi bytecode: `systemctl edit <unit>`, thêm `[Service]` / `Environment=PYTHONDONTWRITEBYTECODE=1`, rồi
   `systemctl restart <unit>` và kiểm `HEALTH_URL` trả 200/403.
3. Xóa `__pycache__` còn trong các release (bản đang chạy cũng được, Python không cần nó):
   `find "$RELEASES_DIR" -mindepth 2 -type d -name __pycache__ -prune -exec rm -rf {} +` (lấy `RELEASES_DIR` từ
   `/etc/webdebit-deploy.conf`). Lượt deploy sau tự dọn bản cũ quá `KEEP`.

## Rủi ro còn lại

- GitHub giữ khóa SSH và OAuth Tailscale. Giảm bằng: khóa chỉ chạy một lệnh, ACL tag hẹp, `AllowUsers` giới hạn dải
  Tailscale, workflow chỉ chạy từ `main` sau `Tests` xanh. Không còn người duyệt (bỏ 28/10/2026): merge vào `main` là lên `hao`,
  trừ diff có migration/SQL/loader vẫn bị chặn và làm tay.
- Ai sửa được `main` thì sửa được thứ được deploy: giữ nhánh `main` bảo vệ (PR + CI xanh).

## Rollback

Job tự quay lại bản trước khi kiểm sống lỗi. Quay tay: trỏ `CURRENT_LINK` về release cũ trong `RELEASES_DIR`
(giữ 5 bản gần nhất), `systemctl restart <unit>`. Gỡ hẳn auto-deploy: tắt/xóa workflow, trả unit về bản đã lưu ở bước 2.
DB không cần restore.
