# Tự động đưa bản sửa lên hao — ĐỀ XUẤT

**ĐỀ XUẤT (người dùng chọn cách 2 ngày 23/10/2026), chưa cài, chưa bật, chưa chạy trên `hao`.**
Workflow và script chỉ nằm trong repo; không có gì chạy cho tới khi người dùng làm phần cài đặt dưới đây.

Luồng: merge vào `main` → `Tests` xanh trên đúng SHA → job `Deploy hao` chờ người duyệt (Environment `hao`)
→ runner GitHub vào Tailscale → SSH bằng khóa chỉ chạy được một lệnh → `scripts/deploy/hao-release.sh`
trên `hao` nhận gói mã, đổi symlink release, restart service, kiểm sống, lỗi thì tự quay lại bản trước.

## Phạm vi và những gì bị chặn

- Chỉ đổi release của app (`cong-no-web-handoff/{web,preview,tools}`), như mục "Giao diện sửa/xóa tại ô" trong
  [runbook](v7-deploy-runbook.md#giao-diện-sửaxóa-tại-ô--chỉ-đổi-release-app-đã-chạy-trên-hao-22102026).
- Diff so với bản đang chạy có `specs/v7-backend/`, `tools/migrations/`, file `.sql` hoặc loader `v7_load*`
  → job **dừng**, phải triển khai tay theo runbook (backup, bản sao, gate). Không DDL, không nạp dữ liệu.
- Không backup DB mỗi lượt vì không đụng DB. Đổi sang mã cần migration thì không đi đường này.
- Đạt (kỳ vọng): service active và cổng loopback trả 200/403 trong 30 giây; không thì quay lại release cũ, job đỏ.
  Chưa kiểm trên `hao` thật; kiểm sống chỉ chứng minh tiến trình sống, không chứng minh sổ đúng.

## Cài đặt một lần (người dùng/admin, ngoài repo)

1. **Hao:** tạo OS user `webdebit-deploy` không sudo chung; thư mục `RELEASES_DIR` thuộc user này.
   Chép `scripts/deploy/hao-release.sh` từ commit đã review vào đường dẫn root-owned, không sửa được bởi user deploy.
   `/etc/webdebit-deploy.conf` (root-owned): `RELEASES_DIR`, `CURRENT_LINK`, `UNIT`, `HEALTH_URL` (loopback, cổng API, một route thật như `/api/v7/customers`: trả 200 hoặc 403 là sống, 404 bị coi là lỗi).
2. **Unit hiện tại:** đổi một lần `WorkingDirectory`/`ExecStart` sang `CURRENT_LINK` (symlink) thay đường dẫn release
   cố định; `daemon-reload`. Tạo `.release-sha` trong release đang chạy bằng SHA thật của nó để lượt đầu có mốc diff.
   Làm tay theo quy trình runbook (lưu bản unit cũ để rollback).
3. **sudoers:** cho `webdebit-deploy` đúng một lệnh không mật khẩu: `systemctl restart <unit>`.
4. **Khóa SSH:** tạo cặp khóa riêng cho deploy; trong `authorized_keys` đặt
   `command="/đường/dẫn/hao-release.sh",restrict` trước khóa công khai. Khóa này không mở được shell.
5. **Tailscale:** tạo OAuth client giới hạn tag `tag:ci`; ACL chỉ cho `tag:ci` tới `hao` cổng SSH.
6. **GitHub:** Settings → Environments → `hao`, bật *Required reviewers* (người dùng). Đặt:
   secrets `HAO_SSH_USER`, `HAO_SSH_KEY_B64` (private key mã base64 một dòng: `sudo base64 -w0 /tmp/<khóa>`), `HAO_TS_OAUTH_CLIENT_ID`, `HAO_TS_OAUTH_SECRET`;
   variables `HAO_SSH_HOST` (tên Tailscale), `HAO_SSH_KNOWN_HOSTS` (host key đã ghim). Không ghi giá trị vào repo.

## Rủi ro còn lại

- GitHub giữ khóa SSH và OAuth Tailscale. Giảm bằng: khóa chỉ chạy một lệnh, ACL tag hẹp, bắt buộc người duyệt,
  workflow chỉ chạy từ `main` (PR từ fork không đọc được secret của Environment).
- Ai sửa được `main` thì sửa được thứ được deploy: giữ nhánh `main` bảo vệ (PR + CI xanh).
- Action dùng tag (`@v4`, `@v3`) như `test.yml`; nên ghim SHA khi bật thật.
- Script và workflow **chưa chạy thử** end-to-end. Lần bật đầu nên thử ở một thư mục release giả trên `hao`
  (HEALTH_URL trỏ service thử) trước khi trỏ vào unit thật.

## Rollback

Job tự quay lại bản trước khi kiểm sống lỗi. Quay tay: trỏ `CURRENT_LINK` về release cũ trong `RELEASES_DIR`
(giữ 5 bản gần nhất), `systemctl restart <unit>`. DB không cần restore.
