# webdebit

Repository phát triển chung cho dev và AI của sổ công nợ phải thu HTH, theo lựa chọn người dùng ngày 15/10/2026. Code và tài liệu nghiệp vụ đã lọc được quản lý phiên bản ở đây. Test chỉ dùng fixture giả; dữ liệu khách, capture, chứng từ và DB nằm ngoài repo.

Đọc [hướng dẫn](AGENTS.md), [hồ sơ nghiệp vụ](docs/README.md), [quyết định](docs/decisions.md), [quy trình phát triển](docs/development.md). Bản cơ sở `69a84a41382217265f745c1c9ae87cba9e557c16` là bản xuất mã có chọn lọc, không phải bản sao đầy đủ workspace hay runtime.

Theo dõi mốc và việc còn chặn tại [roadmap](docs/roadmap.md).

## Cài và kiểm trên máy mới

Yêu cầu Node.js 24, npm (kèm Node), Python 3.12 hoặc 3.13. Python cần gói dữ liệu múi giờ `tzdata` đã khóa phiên bản/hash, đặc biệt trên Windows; không cần PostgreSQL. Từ gốc repository trên Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci --ignore-scripts
npx playwright install chromium
npm run check
```

`requirements-dev.txt` chỉ có công cụ lint (ruff, ghim phiên bản, không ghim hash), không phải phụ thuộc chạy thật. `npm run check` ([scripts/check.js](scripts/check.js)) tự tìm Python và ruff trong `.venv`, rồi chạy tám bước: ruff, luật nghiệp vụ, link tài liệu, eslint, unittest của `cong-no-web-handoff/tests`, `test:unit`, `test:browser`, `test:viewer`; bước nào hỏng thì lệnh thoát khác 0. `npm run lint` chỉ chạy bốn bước lint.

Linux: tạo `.venv` bằng `python3 -m venv .venv`, cài requirements bằng `.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements.txt` và `.venv/bin/python -m pip install -r requirements-dev.txt`, rồi chạy `npm run check` từ gốc repo. Cài Chromium bằng `npx playwright install --with-deps chromium` để bổ sung thư viện hệ điều hành nếu cần. Python 3.12 trên Windows dùng `py -3.12` để tạo venv. Playwright khóa bằng `package-lock.json`, tự chọn browser khớp phiên bản. Có thể đặt `PLAYWRIGHT_BROWSERS_PATH` tới thư mục mới để kiểm không phụ thuộc cache browser trước đó.

`npm run test:unit` chạy sáu file JS không cần browser (gồm `scripts/test-business-rules.js`); `npm run test:browser` mở HTML fixture từ vị trí file test bằng Chromium headless; `npm run test:viewer` chạy test trình duyệt viewer dữ liệu giả. `npm test` chạy cả ba bộ JS nhưng không chạy lint hay unittest Python, nên lệnh chuẩn là `npm run check`. Chưa tải Chromium thì hai bước trình duyệt báo SKIP.

[Workflow](.github/workflows/test.yml) chạy mọi job trên máy của GitHub từ 21/10/2026 (repo public): unittest Python 3.12/3.13 và các harness PostgreSQL 18.6 dùng một lần trên `ubuntu-latest`; job `javascript` chạy `npm run check` (Python 3.13 qua `uv`, Node theo `.node-version`) trên `ubuntu-latest` và `windows-latest`. Repo này không dùng runner tự host trên `hao` (máy DB thật), xem [Quy trình phát triển](docs/development.md#ci-trên-runner-github). File workflow có mặt chưa chứng minh đã có lượt chạy GitHub: xem [bằng chứng](docs/verification.md).

## Phạm vi mã

- `cong-no-web-handoff/pilot/`: engine nhập/đối soát chỉ đọc từ file nguồn được cấp riêng.
- `cong-no-web-handoff/web/`: code đọc sổ và truy vấn; không cấu hình DB thật trong repo.
- `cong-no-web-handoff/tools/`: schema/export/verify phục vụ phát triển. SQL hiện có không phải migration mới đã duyệt.
- `cong-no-web-handoff/preview/`: prototype fixture giả trong bộ nhớ tab.
- `cong-no-web-handoff/tests/`: unit và HTTP tests dùng fake DB.
- `docs/`, `specs/`: yêu cầu, quyết định, kiểm chứng và thay đổi có phiên bản.

Tiện ích tách XLSX dùng `openpyxl` nằm ngoài cổng test cơ sở; chưa cung cấp môi trường import nguồn thật. Không kèm installer, SSH relay hoặc lệnh submit giao dịch thật. Test code/fixture không chứng minh số dư, quyền duyệt, service hay đường ghi tiền.
