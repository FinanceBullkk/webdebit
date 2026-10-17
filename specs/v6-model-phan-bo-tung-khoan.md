# Lớp 1b — phân bổ theo từng khoản thu

Trạng thái: **ĐỀ XUẤT** (Claude, 18/10/2026).

Bảng thu riêng ([`v6-bang-thu-rieng.md`](v6-bang-thu-rieng.md)) cần hiện **từng khoản thu trừ cho kỳ nợ nào**. Model V5 hiện chỉ cộng dồn mọi khoản rồi phân bổ một lần, nên không có số để điền vào cột Phân bổ. Spec này thêm đúng một hàm cho model, không đụng giao diện.

## Người dùng và luồng (bước 1)

Người thu tiền mở sổ của một khách, nhìn bảng khoản thu và hỏi: "khoản 20.000.000 nhận ngày 05/02 này trừ cho nợ tháng nào?". Màn phải trả lời được cho **từng dòng thu**, không phải cho cả tháng gộp lại. Đây là phần tính toán của câu trả lời đó; phần hiển thị ở spec giao diện.

## Đầu ra

`LedgerV5Model.allocateReceipts(receipts, buckets)` trả về danh sách phân bổ **của từng khoản thu**, cộng lại đúng bằng kết quả `ledgerBalance` hiện có.

## Đối chiếu dữ liệu và code hiện có (bước 2)

`cong-no-web-handoff/preview/so-cong-no-v5-model.js` (93 dòng) đang có:

- `allocateReceipt(receiptVnd, buckets)` — phân bổ **một** số tiền vào các kỳ nợ theo thứ tự truyền vào, trả `{allocations, overpaymentVnd}`. Dùng lại được nguyên.
- `ledgerBalance({closedVnd, openVnd, receipts, buckets})` — cộng mọi khoản có `receivedOn` khác null thành một số rồi gọi `allocateReceipt` một lần (comment trong code: "Same ordered buckets for all receipts"). Tổng đúng, nhưng **không biết khoản nào trừ kỳ nào**.
- Khoản có `receivedOn === null` bị bỏ qua — đúng quy tắc chứng từ chưa xác nhận không vào số dư; giữ nguyên.

Thiếu: hàm chạy lần lượt từng khoản trên số dư kỳ nợ **còn lại sau các khoản trước đó**.

## Giao tiếp frontend–backend (bước 5)

Chưa có backend. Hàm chạy trong tab, không API, không lưu trữ.

- Vào: `receipts` — mảng `{id, receivedOn, amountVnd}` theo **thứ tự ngày thực nhận tăng dần, cùng ngày thì theo thứ tự nhập**; `buckets` — mảng `{key, kind, balanceVnd}` như `ledgerBalance` đang dùng, cũ trước mới sau.
- Ra: `{perReceipt: [{id, allocations: [{key, kind, amountVnd}], overpaymentVnd}], overpaymentVnd}`.
- Lỗi: ném `Error` như các hàm hiện có (tiền không hợp lệ, `receivedOn` là chuỗi rỗng, `kind` lạ).

## Nguồn quyết định

- [`docs/decisions.md`](../docs/decisions.md): `V6-THU` (bảng thu riêng, cột Phân bổ), `D03` (thu mới trừ nợ cũ trước), `V5-UX` (khoản thu thuộc sổ + kỳ nợ).
- CÒN MỞ, không chốt trong spec này: tiền dư dùng cho sổ khác (`D04`), sửa/xóa khoản thu đã lưu.

## Hành vi và bất biến

- VND nguyên bằng `BigInt`; không `Number`, không làm tròn, không tự đổi đơn vị.
- Khoản `receivedOn === null` không được phân bổ và không vào tổng.
- Kỳ nợ cũ trừ trước; không phân bổ lại các khoản đã xử lý trước đó trong cùng lần chạy.
- `perReceipt` cộng lại theo từng `key` phải **bằng đúng** phân bổ mà `ledgerBalance` tính trên cùng dữ liệu; tiền dư cuối cùng cũng phải bằng.
- Không sửa `allocateReceipt`, `ledgerBalance`, `canClose`, `lineAmount`, `monthTotals`.

## Tiêu chí nghiệm thu

- [ ] `npm run test:unit` PASS, gồm các test mới trong `test-so-cong-no-v5-model.js`.
- [ ] Một khoản trừ gọn một kỳ.
- [ ] Một khoản trải qua nhiều kỳ (trừ hết kỳ cũ, phần còn lại sang kỳ sau).
- [ ] Hai khoản liên tiếp: khoản thứ hai trừ trên số dư **còn lại** sau khoản thứ nhất, không trừ lại kỳ đã hết.
- [ ] Khoản có `receivedOn: null` nằm giữa danh sách: bị bỏ qua, không đẩy lệch phân bổ của khoản sau.
- [ ] Thu nhiều hơn tổng nợ: `overpaymentVnd` đúng, không có phân bổ âm.
- [ ] Đối chiếu tổng với `ledgerBalance` trên cùng fixture.

## Phạm vi agent

- Agent: codex
- Review: opus — đường phân bổ tiền
- Được sửa:
  - `cong-no-web-handoff/preview/so-cong-no-v5-model.js`
  - `cong-no-web-handoff/preview/test-so-cong-no-v5-model.js`
- Ngân sách diff: 150 dòng
- Lệnh kiểm:
  - `npm run test:unit`
- Cấm:
  - Sửa giao diện (`so-cong-no-v5-ui.js`, `so-cong-no-v5.html`) hoặc bất kỳ màn/model cũ nào trong `preview/`.
  - Đổi chữ ký hoặc hành vi của năm hàm đang có; thêm hàm khác ngoài `allocateReceipts`.
  - Thêm dependency, framework, build step; dùng `fetch`, API, localStorage.
  - Tự quyết các điểm CÒN MỞ ở trên.
- Khi cần vượt phạm vi: dừng, ghi vào "Câu hỏi mở".

## Hoàn tác

Hai file sửa, revert commit; không đụng dữ liệu.

## Bằng chứng

<Agent ghi: lệnh đã chạy và kết quả. Fixture trong tab, không phải tích hợp hay live.>

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
