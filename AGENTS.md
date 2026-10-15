# Hướng dẫn dev và AI

Repo là nơi phát triển chung code và tài liệu đã loại nhạy cảm. Đọc `README.md`, `docs/README.md`, `docs/business-rules.md`, `docs/decisions.md` và [bản đồ feature](docs/features/README.md), rồi mở đúng feature/spec liên quan trước khi sửa. Quy tắc cộng tác: `docs/development.md`; nguồn và phiên bản: `docs/source-register.md`.

- Một checkout/nhánh có một người hoặc agent ghi cùng phạm vi. Kiểm `git status`/diff trước khi sửa, giữ thay đổi của người khác. Không đồng bộ ngược từ release hoặc handoff cũ. Không stage/commit/push thay đổi ngoài nhiệm vụ.
- Tạo spec có đầu ra/tiêu chí cho thay đổi đáng kể. Map thao tác → module → kiểm → bằng chứng. Model, browser, DB test và live là các phạm vi riêng. Không cài framework/installer chỉ vì tài liệu gợi ý.
- Tạo venv/cài `requirements.txt` khóa hash theo README. Tại gốc: `npm ci --ignore-scripts`, `npx playwright install chromium`, `npm test`. Tại `cong-no-web-handoff/`: `..\.venv\Scripts\python.exe -m unittest discover -s tests -v` (Linux: `../.venv/bin/python`). CI kiểm Python 3.12/3.13 và Windows/Linux. Test không cần DB thật; không dựa vào package Python toàn cục.
- VND nguyên chính xác; NULL/blank không phải 0. Tách khách, kỳ nợ, ngày nghiệp vụ, ngày ghi sổ, ngày chốt. Container không là khóa duy nhất. Pending ngoài số dư; lịch sử trong opening không cộng lại. Thu mới theo nợ cũ trước, không phân bổ lại lịch sử.
- Không ghi tiền thiếu nguồn, chứng cứ, phê duyệt riêng và gate của task. Không sửa đè posting; đảo/điều chỉnh có audit. CÒN MỞ trong `docs/decisions.md` không thành chính sách đã duyệt qua fixture/UI/schema.
- Không thêm raw capture, export, dump, DB, chứng từ ngân hàng, ảnh khách, exact Sheet ID, SSH details, bí mật hoặc artifact chưa kiểm. Không chạy DDL/import/deploy/submit thật trong task test/tài liệu. Review toàn bộ diff định đưa lên và kiểm bí mật/nhạy cảm trước push; `.gitignore` không thay review.
- Quyết định mới ghi người chốt, thời điểm và phạm vi. Báo rõ ĐỀ XUẤT, ĐÃ CHỐT, ĐÃ TRIỂN KHAI (môi trường), ĐÃ KIỂM CHỨNG (bằng chứng), CÒN MỞ. Báo cáo cũ không là trạng thái live hôm nay.
- Với thay đổi mới đáng kể, dùng OpenSpec trong `openspec/`; spec đang mở ở `specs/` tiếp tục tại chỗ, không tạo hai bản sống. CLI/skill hỗ trợ lập và kiểm spec, không cấp quyền ghi DB/Sheet/deploy. Xem `docs/development.md`.
- Trước khi đọc mã, chọn feature và dùng `rg` tìm entry point; đọc file/vùng liên quan. Không nạp cả repo, lockfile, raw capture hoặc log dài vào context mặc định. Mục tiêu đa số task dưới 100k context cần đo trên task thật.
- Mã nguồn mới tối đa 300 dòng/file. Năm file lớn hiện có được cố định ngưỡng trong `scripts/loc-baseline.json`; không tăng ngưỡng chỉ để vượt CI. Khi cần tách file, giữ hành vi và chạy kiểm liên quan. `npm run check:loc` là gate thực thi.
