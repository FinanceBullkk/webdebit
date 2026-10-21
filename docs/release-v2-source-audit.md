# Đối chiếu mã release v2 — 21/10/2026

Phạm vi ĐÃ CHỐT bởi người dùng trong nhiệm vụ ngày 21/10: chỉ đối chiếu gói `ledger-web-release-2026-10-20-v2` với worktree `codex/release-v2-to-git`; đưa mã hợp lệ vào Git, giữ nguyên logic, loại dữ liệu opening nhạy cảm. Tiêu chí: phân loại đủ từng file, kiểm hash/nội dung, chạy checks khả dụng, không sửa release/captures hoặc tác động DB/Sheet/service. Đây là hồ sơ nguồn, không phải thay đổi luồng frontend nên không phát sinh mockup mới.

Baseline sạch: `ae8f8f7b9cab6679bd00fa8730e6357671921709` (đã có PR #30 và `a8aa769`). Không đọc trạng thái checkout khác. Dependency dùng chỉ đọc từ checkout chính theo quyền người dùng.

## Kết quả từng file

Đường dẫn web trong Git đều dưới `cong-no-web-handoff/web/`. “Giống” nghĩa là SHA-256 bytes gốc giống, không chỉ bỏ qua CRLF/LF.

| File trong gói | So với Git baseline | Phân loại và xử lý |
| --- | --- | --- |
| `web/ledger_app.py` | Khác đúng hai dòng gán so với baseline `ae8f8f7` | Mã nguồn đã có. Chỉ khác `CAPTURE` (`2026-10-20-so-goc-v2`) và tổng `opening_vnd` trong `OPENING_INVARIANTS`. **Người dùng chốt 21/10/2026 cập nhật hai hằng lên giá trị v2** (cùng loại tên bản/tổng gộp đã có sẵn trong Git); cập nhật cùng lúc để không ghép snapshot mới với tổng cũ. Sau cập nhật file khớp từng byte với gói v2. Test `test_ledger_web.py` dòng 571 đổi theo. Không đổi logic. |
| `web/ledger_db.py` | Giống từng byte | Mã nguồn đã có; không cần chép. |
| `web/style.css` | Giống từng byte | Mã nguồn đã có; không cần chép. |
| `release.sha256` | Chỉ có ở release | Manifest của artifact, không phải mã nguồn. Cả 3 mục khớp file trong gói; giữ ngoài Git, ghi hash ở source register. |
| `installed.sha256` | Chỉ có ở release | Manifest đích cài đặt, cùng 3 digest với `release.sha256`, khác tiền tố đường dẫn. Cả 3 mục khớp file trong gói; không chứng minh file trên máy chủ. Giữ ngoài Git. |
| `previous.sha256` | Chỉ có ở release | Manifest điều kiện phiên bản trước; cả 3 mục khớp web ở Git baseline. Giữ ngoài Git. |
| `install.sh` | Chỉ có ở release | Script vận hành: kiểm manifest, sao lưu, cài file, restart, health/rollback. Không phải mã web; giữ ngoài Git theo phạm vi repo không kèm installer. Chỉ đọc, không chạy. |

Không có mã nguồn web mới hoặc khác logic cần chuyển. Không sao chép số tiền thật, danh sách khách, Sheet ID, dữ liệu opening, cấu hình máy chủ hoặc artifact sinh ra vào Git. Không xóa/sửa các hằng opening đã tồn tại trong baseline; tách cấu hình khỏi mã là việc khác, chưa làm trong task giữ nguyên logic.

## Bằng chứng nguồn

| File web | SHA-256 release | SHA-256 Git baseline |
| --- | --- | --- |
| `ledger_app.py` | `ead33042710e0d57321d5c7b0a1d7e1ab998d0b9b74d4ec3a7e70b49cc8b44ca` | Sau cập nhật 21/10: như release. Baseline `ae8f8f7` là `ead6cc22673772f8fd37c926333b6d560ff6390aa6f89086986f856210779c9a` |
| `ledger_db.py` | `b876338bf9fb3f06e41da8a45c53e09aebe4f1ca81c18343d6fdb8476369760e` | Như release |
| `style.css` | `0a009535fdcf51e899ee45a6731868d977cae9097be39f1656e23a5147b791db` | Như release |

ĐÃ KIỂM CHỨNG cục bộ: `Get-FileHash`, `git diff --no-index`, và Python stdlib `hashlib` kiểm từng mục trong ba manifest (3/3 mỗi file). Python `ast.parse` so tất cả statement: chỉ hai phép gán trên khác; AST còn lại giống hoàn toàn. Không xuất giá trị tổng opening vào báo cáo. Hash metadata ở [source register](source-register.md#release-v2-20102026).

Map kiểm: trang xem sổ/health → `ledger_app.py` + `ledger_db.py` → `tests/test_ledger_web.py`; prototype → bốn file JS unit; trình duyệt → hai bộ browser hiện có. Đối chiếu nguồn không thay kiểm runtime.

## Kiểm cục bộ và giới hạn

Windows, Node `v24.16.0`, Python `3.13.6`. Không cài dependency. Dùng `NODE_PATH=D:\webdebit\repo\node_modules` và `WEBDEBIT_PYTHON=D:\webdebit\repo\.venv\Scripts\python.exe` cho Node; gọi trực tiếp Python venv đó cho unittest. Không sửa checkout chính.

| Lệnh / kiểm | Kết quả thật |
| --- | --- |
| `npm run check` | Exit 1: `Missing script: "check"`; package.json baseline không định nghĩa script này. |
| `npm test` | Exit 1: Node runner không spawn được process test (`spawn EPERM`), dừng ở unit; chưa chạy hai bước browser trong chuỗi này. |
| `node --test --test-isolation=none cong-no-web-handoff/preview/test-so-cong-no-model.js cong-no-web-handoff/preview/test-monthly-ledger-model.js cong-no-web-handoff/preview/test-customer-ledger-workbench.js cong-no-web-handoff/preview/test-customer-ledger-requirements.js` | Đạt 16/16, exit 0. Dùng cùng file test, chạy trong process hiện tại, không sửa runner repo. |
| `node --test --test-isolation=none cong-no-web-handoff/preview/test-customer-ledger-browser.js` | Exit 1: 6/6 bị lỗi khởi động Chromium `spawn EPERM`; chưa kiểm được UI. |
| `node --test --test-isolation=none cong-no-web-handoff/tests/test-viewer-browser.js` | Exit 1: 11/11 bị hook lỗi spawn Python fixture server `EPERM`; chưa kiểm được viewer qua browser. |
| Từ `cong-no-web-handoff/`: `D:\webdebit\repo\.venv\Scripts\python.exe -m unittest discover -s tests -v` | Exit 1. Thử TEMP mặc định rồi TEMP/TMP trong `test-results/release-v2/`: lần sau chạy 99 test, 42 errors; gặp `PermissionError: [WinError 5] Access is denied` khi thao tác thư mục tạm. Không coi toàn bộ Python đạt. |

Log fixture cục bộ trong `test-results/release-v2/` bị Git ignore, không commit. Không chạy SQL/DDL/import, installer, deploy, submit, hoặc kết nối DB/Sheet/hao thật.

## Trạng thái và việc còn mở

- ĐÃ KIỂM CHỨNG: logic ba file web của gói v2 đã có ở baseline Git; chênh lệch là hai hằng gắn opening. Nhận định “mã của gói v2 chưa có trong Git” không còn chính xác với baseline này.
- ĐÃ TRIỂN KHAI: chỉ tài liệu đối chiếu trong worktree; không triển khai phần mềm/service trong nhiệm vụ này. Thông tin gói đang chạy trên `hao` là bối cảnh người dùng cung cấp, chưa kiểm live.
- ĐỀ XUẤT: nếu cần dựng lại runtime v2 từ Git, làm task riêng tách cấu hình opening nhạy cảm khỏi mã, giữ guard fail-closed và kiểm đủ provenance. Chưa đổi hợp đồng cấu hình hoặc duyệt cách cài.
- CÒN MỞ: chạy đủ browser/Python trong môi trường cho phép spawn và thao tác temp; chưa nghiệm thu runtime v2, chưa xác minh số liệu hoặc quyền ghi tiền. M1 và các gate nghiệp vụ giữ nguyên.
