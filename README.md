# webdebit

Repository phát triển chung cho dev và AI của sổ công nợ phải thu HTH, theo lựa chọn người dùng ngày 15/10/2026. Code và tài liệu nghiệp vụ đã lọc được quản lý phiên bản ở đây. Test chỉ dùng fixture giả; dữ liệu khách, capture, chứng từ và DB nằm ngoài repo.

Đọc [hướng dẫn](AGENTS.md), [hồ sơ nghiệp vụ](docs/README.md), [quyết định](docs/decisions.md), [quy trình phát triển](docs/development.md). Bản cơ sở `69a84a41382217265f745c1c9ae87cba9e557c16` là bản xuất mã có chọn lọc, không phải bản sao đầy đủ workspace hay runtime.

Khi làm một feature, mở [bản đồ feature](docs/features/README.md) để chọn đúng mã và kiểm. OpenSpec đã được setup cho **thay đổi đáng kể mới**: `npm ci --ignore-scripts`, rồi `npx --no-install openspec doctor --json`; chọn `openspec-propose` trong Codex hoặc chạy CLI theo [quy trình](docs/development.md). Spec đang mở trong `specs/` tiếp tục ở đó, không tạo bản song song.

## Cài và kiểm trên máy mới

Yêu cầu Node.js 24, npm (kèm Node), Python 3.12 hoặc 3.13. Python cần gói dữ liệu múi giờ `tzdata` đã khóa phiên bản/hash, đặc biệt trên Windows; không cần PostgreSQL. Từ gốc repository trên Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements.txt
npm ci --ignore-scripts
npx playwright install chromium
npm test
cd cong-no-web-handoff
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Linux: tạo `.venv` bằng `python3 -m venv .venv`, cài requirements bằng `.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements.txt`, rồi chạy test từ `cong-no-web-handoff/` bằng `../.venv/bin/python -m unittest discover -s tests -v`. Cài Chromium bằng `npx playwright install --with-deps chromium` để bổ sung thư viện hệ điều hành nếu cần. Python 3.12 trên Windows dùng `py -3.12` để tạo venv. Playwright khóa bằng `package-lock.json`, tự chọn browser khớp phiên bản. Có thể đặt `PLAYWRIGHT_BROWSERS_PATH` tới thư mục mới để kiểm không phụ thuộc cache browser trước đó.

`npm run test:unit` chạy đủ bốn file JS không cần browser; `npm run test:browser` mở HTML fixture từ vị trí file test bằng Chromium headless. `npm test` chạy cả hai. [Workflow](.github/workflows/test.yml) kiểm Windows/Linux, Python 3.12/3.13 và Node 24/Chromium. File workflow có mặt chưa chứng minh đã có lượt chạy GitHub: xem [bằng chứng](docs/verification.md).

## Phạm vi mã

- `cong-no-web-handoff/pilot/`: engine nhập/đối soát chỉ đọc từ file nguồn được cấp riêng.
- `cong-no-web-handoff/web/`: code đọc sổ và truy vấn; không cấu hình DB thật trong repo.
- `cong-no-web-handoff/tools/`: schema/export/verify phục vụ phát triển. SQL hiện có không phải migration mới đã duyệt.
- `cong-no-web-handoff/preview/`: prototype fixture giả trong bộ nhớ tab.
- `cong-no-web-handoff/tests/`: unit và HTTP tests dùng fake DB.
- `docs/`, `specs/`, `openspec/`: yêu cầu, quyết định, kiểm chứng, spec hiện có và thay đổi mới có phiên bản.

Tiện ích tách XLSX dùng `openpyxl` nằm ngoài cổng test cơ sở; chưa cung cấp môi trường import nguồn thật. Không kèm installer, SSH relay hoặc lệnh submit giao dịch thật. Test code/fixture không chứng minh số dư, quyền duyệt, service hay đường ghi tiền.
