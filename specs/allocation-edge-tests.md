# Test biên phân bổ thu theo nợ cũ trước (fixture)

Trạng thái: ĐỀ XUẤT ngày 16/10/2026 bởi Claude theo yêu cầu người dùng thử quy trình nhiều agent. Chỉ thêm test; không đổi hành vi, không thêm chính sách.

## Đầu ra

`test-so-cong-no-model.js` khóa thêm các trường hợp biên của `allocateOldestFirst` mà test hiện tại chưa phủ. Model giữ nguyên.

## Nguồn quyết định

- Thu mới trừ kỳ nợ cũ trước; NULL/blank không phải 0 ([AGENTS.md](../AGENTS.md), [quy tắc](../docs/business-rules.md)).

## Hành vi và bất biến

- Kỳ có số dư 0 hoặc âm (khách trả dư) bị bỏ qua, phần thu chuyển sang kỳ dương kế tiếp.
- Số thu `"0"`, `null`, `""` bị từ chối; số dư kỳ `null`, `""` hoặc thiếu bị từ chối (không coi là 0).
- `periodBalances` không phải mảng bị từ chối; kỳ sai định dạng (`"2026-13"`) bị từ chối.
- Kết quả là BigInt, không làm tròn.

## Tiêu chí nghiệm thu

- [ ] `node cong-no-web-handoff/preview/test-so-cong-no-model.js` đạt (chạy từ gốc repo).
- [ ] `npm run test:unit` đạt.
- [ ] `so-cong-no-model.js` không đổi.

## Phạm vi agent

Mục này là hợp đồng với agent thực hiện; `scripts/agent-run.ps1` đọc nó để kiểm diff.

- Agent: codex
- Được sửa:
  - `cong-no-web-handoff/preview/test-so-cong-no-model.js`
- Ngân sách diff: 40 dòng
- Lệnh kiểm:
  - `node cong-no-web-handoff/preview/test-so-cong-no-model.js`
  - `npm run test:unit`
  - `git diff --quiet 75d9ff9 -- cong-no-web-handoff/preview/so-cong-no-model.js`
- Cấm:
  - Sửa `so-cong-no-model.js` hoặc bất kỳ file nào khác; nếu test phát hiện model sai thì dừng và ghi vào "Câu hỏi mở".
  - Thêm dependency, framework test, helper/file mới; giữ phong cách `assert` hiện có.
  - Đổi schema, trường tiền, quyền, quy tắc nghiệp vụ; chạm dữ liệu thật.
- Khi cần vượt phạm vi: dừng, không tự mở rộng; ghi câu hỏi ở mục "Câu hỏi mở" bên dưới.

## Hoàn tác

Bỏ các dòng test vừa thêm.

## Bằng chứng

<Agent ghi lệnh đã chạy và kết quả.>

## Câu hỏi mở

- (chưa có)
