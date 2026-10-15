# Gói deploy và rollback viewer M1

Trạng thái: **ĐỀ XUẤT**. Công cụ và test dùng thư mục tạm, repo git tạm và dữ liệu giả. **Chưa deploy**, chưa chạm máy chủ, DB hoặc Sheet nào. Gói không phải migration và không chứa DDL.

## Gate và thứ tự

1. **ACL trước**: cấp quyền đọc năm view của DB pilot cho role viewer, cùng `CONNECT` và `USAGE` ([đề xuất ACL](m1-acl-proposal.md)). Theo T07, viewer live thiếu `SELECT` trên ba view M1 summary; deploy trước khi cấp quyền thì `/health` trả 503 vì `exception_summary` và `customer_reconciliations` không đọc được. Hai view `web_*`, `CONNECT` và `USAGE` chưa có bằng chứng live, nên cũng nằm trong gate.
2. Build gói từ commit đã review.
3. Preflight chỉ đọc, gồm kiểm ACL bằng tài khoản viewer.
4. Người có quyền deploy cài gói; kiểm `/health` 200 và mở browser qua relay.
5. Không có bước nào trong tài liệu này tự chạy. Mỗi bước cần người dùng chạy hoặc duyệt riêng.

## Gói runtime

`cong-no-web-handoff/tools/m1_release.py` chỉ chép ba file trong allowlist từ **một commit git** (đọc bằng `git show`, không đọc working tree):

| File trong gói | Nguồn |
| --- | --- |
| `web/ledger_app.py` | `cong-no-web-handoff/web/ledger_app.py` |
| `web/ledger_db.py` | `cong-no-web-handoff/web/ledger_db.py` |
| `web/style.css` | `cong-no-web-handoff/web/style.css` |

Không đóng gói fixture SQL, schema, test, preview, `captures/`, docs, app cũ (`app.py`, `db.py`, `actor_assertion.py`) hay file cấu hình. Thêm file vào gói phải sửa allowlist trong code và review.

```powershell
.\.venv\Scripts\python.exe cong-no-web-handoff\tools\m1_release.py build <thu-muc-ngoai-repo> --commit <sha>
```

- Thư mục đích phải mới hoặc rỗng và nằm ngoài worktree (gói chứa mã chạy, không đưa vào Git).
- Build từ chối khi commit là HEAD mà ba file có thay đổi chưa commit (commit khác HEAD đọc thẳng từ git), thiếu trong commit hoặc lỗi cú pháp Python (chỉ `ast.parse`, không import).
- `MANIFEST.json` ghi `commit`, `tree`, đường dẫn, kích thước và SHA-256 từng file. Cùng commit cho cùng manifest từng byte.

Giữ `commit` và `tree` khớp với head PR đã qua CI: CI chỉ chứng minh test trên đúng tree đó.

## Preflight chỉ đọc

```powershell
.\.venv\Scripts\python.exe cong-no-web-handoff\tools\m1_release.py preflight <goi> [--installed <thu-muc-dang-cai>] [--check-db <ten-db-pilot>]
```

Không ghi file, không import code trong gói, không DDL/DML. Kiểm:

- manifest hợp lệ; danh sách file đúng allowlist; không file thừa, không symlink;
- SHA-256 và kích thước từng file, cú pháp Python;
- `--installed`: so từng file đang chạy với manifest (`identical`, `different`, `missing`) và in SHA-256 bản đang cài để làm hồ sơ rollback;
- `--check-db`: chạy thật `SELECT 1 FROM <view> LIMIT 0` trên từng view trong năm view mà viewer đọc (ba view M1 summary và `web_period_event`, `web_source_row`), cùng một `SELECT` kiểm `USAGE` trên schema `pilot`; kết nối được là bằng chứng `CONNECT`. Chạy bằng thông tin kết nối của **role viewer** (biến môi trường libpq, không đưa mật khẩu vào lệnh). Mỗi view báo `ok`, `denied` hoặc `error`.

Mã thoát: `0` sẵn sàng; `1` chưa sẵn sàng (kể cả khi chưa chạy `--check-db`, thiếu quyền hoặc lỗi kết nối); `2` gói hỏng hoặc tham số sai. `ready_for_deploy` chỉ là `true` khi gói đúng và ACL đạt. Kết quả này chưa chứng minh service chạy; sau deploy vẫn phải kiểm `/health` và browser.

## Rollback

Viewer chỉ đọc nên rollback là đưa lại bản mã trước; không có migration cần đảo.

Trước deploy (người deploy làm, ghi vào hồ sơ riêng ngoài Git):

1. Chạy preflight với `--installed` để lưu SHA-256 các file đang chạy. Lần deploy đầu, bản đang chạy (13/10) chỉ có `release.sha256`, chưa có `MANIFEST.json`; dùng SHA-256 này làm mốc, không đợi manifest.
2. Sao các file đang chạy sang thư mục sao lưu có tên theo thời điểm, tính SHA-256 từng file bản sao và so với SHA-256 bước 1 (và với `release.sha256` nếu có). Chưa khớp thì dừng, không deploy.
3. Ghi cách khởi động lại service hiện có (đặt tên service bằng placeholder `<viewer-service>` trong ghi chú chia sẻ; tên thật nằm trong hồ sơ riêng).

Khi cần quay lại (health 503, trang lỗi, số lạ):

1. Dừng ghi nhận deploy mới. Chép các file từ thư mục sao lưu về chỗ cài, khởi động lại `<viewer-service>`.
2. Tính lại SHA-256 các file đã chép về và so với giá trị đã ghi trước deploy (lần đầu: SHA-256 bản 13/10 hoặc `release.sha256`). Từ lần deploy thứ hai trở đi, có thể chạy preflight `--installed` với gói trước, mọi file phải `identical`.
3. Kiểm `/health` và một trang khách trên browser.

Hai điểm cần biết:

- **Rollback mã không hoàn tác ACL.** Bản mã trước vẫn chạy khi role viewer có thêm `SELECT` trên các view; không cần thu hồi để rollback. Thu hồi quyền chỉ khi chủ quyết định riêng.
- Nếu bản trước không có route `/exceptions` và `/health` mở rộng, `/health` của nó chỉ kiểm phần cũ. Dùng kiểm tay trang khách để xác nhận sau rollback.

## Giới hạn

ĐÃ KIỂM CHỨNG: build/preflight bằng repo tạm và dữ liệu giả (`tests/test_m1_release.py`); các câu kiểm ACL chỉ chứa `SELECT` (có test). CHƯA KIỂM CHỨNG: chạy với PostgreSQL, role hoặc máy thật; quy trình cài và khởi động lại thật; tương thích với bản đang chạy ngoài ba file này. CÒN MỞ: hồ sơ riêng ngoài Git cho tên service, đường dẫn cài và thông tin kết nối.
