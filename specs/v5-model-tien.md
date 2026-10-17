# Lớp 1 — model tiền cho sổ công nợ V5

Trạng thái: **ĐÃ TRIỂN KHAI** — commit `2f13063` trên `codex/v5-model-tien`, merge vào `test/pg18-schema-characterization` tại `a2baea4` ngày 17/10/2026. **Chưa push.** **ĐÃ KIỂM CHỨNG** bằng `npm run test:unit`: 17/17 pass, 0 fail — chạy hai lần, một lần trong worktree ngoài sandbox agent, một lần trong checkout chính sau khi merge. Review hai tầng Codex → Claude opus đều ĐẠT ở vòng 0. Log: `D:\webdebit\worktrees\_logs\codex-v5-model-tien`.

Đây là kiểm trên model trong bộ nhớ với dữ liệu giả. **Không phải nghiệm thu nghiệp vụ, không mở đường ghi tiền.**

Lớp 1 của ba lớp dựng frontend V5: **model tiền thuần JavaScript, có test, không giao diện**. Lớp 2 (giao diện nối vào model) và lớp 3 (backend thật) là spec riêng.

Nguồn: [quyết định 17/10](ux-v5-quyet-dinh-2026-10-17.md), [spec mockup đã duyệt](ux-v5-mockup-vong-2.md), [brief](ux-brief-so-cong-no.md) mục 5 và 6, [business-rules](../docs/business-rules.md).

**Không mở đường ghi tiền.** Đây là hàm tính trong bộ nhớ, không API, không DB, không ghi sổ thật.

## Người dùng và luồng (bước 1)

Lớp này không có màn hình, nhưng nó quyết định con số mà ba vai nhìn thấy:

- *Người nhập* dán hoặc gõ chuyến → cần biết **thành tiền từng dòng** và **tổng phát sinh trong tháng**, trong đó dòng chưa có giá không được cộng.
- *Người thu tiền* ghi một khoản thu phủ nhiều chuyến → cần biết khoản đó **trừ vào kỳ nào, mỗi kỳ bao nhiêu**, và còn dư bao nhiêu.
- *Người chốt* bấm chốt tháng → cần biết **được chốt hay không, và nếu không thì vì đủ những lý do gì**.

Sai ở lớp này thì cả ba vai đều thấy số sai mà không ai biết. Vì vậy lớp này phải kiểm được bằng test, không bằng mắt.

## Đầu ra

Một module `cong-no-web-handoff/preview/so-cong-no-v5-model.js` xuất năm hàm thuần, kèm file test chạy bằng `node --test`. Không DOM, không trạng thái toàn cục, không đọc/ghi gì bên ngoài.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Khuôn mẫu bắt buộc theo** `cong-no-web-handoff/preview/so-cong-no-model.js`:

- Tiền là **`BigInt`**, không bao giờ là `Number`. Đầu vào là chuỗi chữ số thập phân, kiểm bằng regex trước khi `BigInt(...)`; sai định dạng thì ném lỗi.
- Module viết theo IIFE rồi `if (typeof module !== "undefined") module.exports = ...` để dùng được cả trong trình duyệt lẫn node.
- Test viết bằng `node:assert/strict`, assert ở mức tệp, không framework ngoài.

**Đã có, dùng lại chứ đừng viết lại:** `allocateOldestFirst(receiptVnd, periodBalances)` trong model cũ đã làm đúng phần nợ cũ trước và trả `unallocatedVnd`. Hàm `allocateReceipt` dưới đây là bản mở rộng cho hai loại kỳ (đã chốt / đang mở) và cho tiền trả dư; được phép bê logic sang nhưng **không sửa file model cũ** vì màn cũ đang dùng.

**Số liệu mẫu** lấy từ [spec mockup](ux-v5-mockup-vong-2.md) mục "Đối chiếu dữ liệu", không bịa thêm.

## Giao tiếp frontend–backend (bước 5)

Chưa có. Lớp 1 chạy hoàn toàn trong tiến trình gọi nó. Lớp 2 sẽ `require`/nhúng module này và truyền dữ liệu fixture vào. Khi nào có backend thì lớp 3 thay nguồn dữ liệu, **chữ ký hàm giữ nguyên**.

## Hợp đồng hàm

Năm hàm, không hơn. Mọi tiền vào/ra là `BigInt`; `null` nghĩa là chưa biết, khác `0n`.

### 1. `lineAmount(line) -> BigInt | null`

`line`: `{unitPriceVnd, otherFeeVnd, plugFeeVnd, escortFeeVnd}`, mỗi trường là chuỗi chữ số hoặc `null`.

- `unitPriceVnd === null` → trả `null` (chưa có giá, không tính được).
- Ngược lại trả `unitPrice + other + plug + escort`, trong đó **phí `null` được cộng như không phát sinh**.
- Không làm tròn, không ước lượng.

### 2. `monthTotals(lines) -> {pricedCount, pricedTotalVnd, missingPriceIds}`

- Chỉ cộng dòng có `lineAmount !== null`.
- `missingPriceIds`: mảng id của các dòng chưa có giá, giữ đúng thứ tự đầu vào.
- Không sửa mảng đầu vào.

### 3. `allocateReceipt(receiptVnd, buckets) -> {allocations, overpaymentVnd}`

`buckets`: mảng **đã sắp theo thứ tự ưu tiên trả nợ**, mỗi phần tử `{key, kind, balanceVnd}` với `kind` là `'closed'` hoặc `'open'`. Hàm **không tự sắp xếp lại** — thứ tự là của người gọi, vì nó là quy tắc nghiệp vụ, không phải chi tiết kỹ thuật.

- Lần lượt trừ vào từng bucket, mỗi bucket nhận tối đa `balanceVnd`.
- Bucket có `balanceVnd <= 0n` thì bỏ qua, **không tạo entry**.
- `allocations`: chỉ gồm bucket thực sự nhận tiền, dạng `{key, kind, amountVnd}`.
- `overpaymentVnd`: phần còn lại sau khi hết bucket. Luôn `>= 0n`.
- **Bất biến:** `tổng allocations + overpaymentVnd === receiptVnd`.
- Không sửa `buckets`.

### 4. `ledgerBalance({closedVnd, openVnd, receipts, buckets}) -> {closedRemainingVnd, openRemainingVnd, overpaymentVnd, receivedVnd, endOfMonthVnd}`

- Chỉ tính các khoản thu **đã xác nhận**: `receipt.receivedOn` khác `null`. Khoản chưa có ngày nhận tiền bị bỏ qua hoàn toàn, không vào `receivedVnd`.
- `receivedVnd`: tổng các khoản đã xác nhận.
- Phân bổ qua `allocateReceipt`; `closedRemainingVnd` và `openRemainingVnd` là phần còn lại của hai nhóm bucket.
- **`closedRemainingVnd >= 0n` và `openRemainingVnd >= 0n` luôn đúng.** Không có đường nào cho ra số âm ở hai trường này.
- `endOfMonthVnd = closedRemainingVnd - overpaymentVnd`. Đây là trường **duy nhất** được phép âm, và chỉ âm khi khách trả dư.
- **Không trả về trường nào gộp `closedRemaining` với `openRemaining`.**

### 5. `canClose({lines, enteredBy, closedBy}) -> {ok, reasons}`

- `reasons` là mảng chuỗi. Khi không chốt được, phải liệt kê **đủ mọi lý do**, không dừng ở lý do đầu tiên.
- Lý do 1 — `closedBy === enteredBy`: người nhập không được tự chốt.
- Lý do 2 — còn dòng chưa có giá: nêu kèm id các dòng đó.
- `ok === true` chỉ khi `reasons` rỗng.

## Hành vi và bất biến

- VND số nguyên chính xác bằng `BigInt`. Không `Number`, không làm tròn, không `parseFloat`.
- `null` là chưa biết, khác `0n`. Không hàm nào được coi `null` là 0 **trừ** ba loại phí trong `lineAmount`, theo quyết định 6 ngày 17/10 (ô phí trống nghĩa là không phát sinh phí).
- Số đã chốt và số đang mở luôn là hai trường riêng.
- Tiền thu trừ nợ cũ trước, rồi mới tới kỳ đang mở.
- Phân bổ không sửa ngược số dư lịch sử: hàm không nhận và không trả bất kỳ thứ gì làm đổi số dư cuối tháng của kỳ đã chốt.
- Khoản thu chưa xác nhận nằm ngoài mọi tổng.
- Mọi hàm thuần: không sửa đối số, không trạng thái dùng chung, cùng đầu vào cho cùng đầu ra.

## Tiêu chí nghiệm thu

Test phải phủ đúng các số của spec mockup. `npm run test:unit` xanh, và trong đó:

- [x] `lineAmount`: đơn giá `40000000` với ba phí `null` → `40000000n`; đơn giá `null` → `null`; đơn giá `40000000` + phí khác `1000000` → `41000000n`.
- [x] `monthTotals` trên bốn dòng DEMO-105/106/107/103 → `pricedCount 3`, `pricedTotalVnd 90000000n`, `missingPriceIds ['DEMO-103']`.
- [x] `allocateReceipt('120000000', buckets)` với buckets `[trước T01 20tr, T01 20tr, T02 30tr, T03 25tr, T04 open 90tr]` → allocations `20/20/30/25/25` triệu, `overpaymentVnd 0n`.
- [x] Cùng buckets, `allocateReceipt('200000000', ...)` → allocations `20/20/30/25/90` triệu, `overpaymentVnd 15000000n`.
- [x] Bucket có `balanceVnd 0n` không sinh entry nào.
- [x] Với mọi ca trên: `tổng allocations + overpaymentVnd === receiptVnd`.
- [x] `ledgerBalance` với thu 120 triệu → `closedRemainingVnd 0n`, `openRemainingVnd 65000000n`, `receivedVnd 120000000n`, `endOfMonthVnd 0n`.
- [x] `ledgerBalance` với thu 200 triệu → `closedRemainingVnd 0n`, `openRemainingVnd 0n`, `overpaymentVnd 15000000n`, `endOfMonthVnd -15000000n`.
- [x] Khoản thu `receivedOn === null` trị giá 5 triệu không làm đổi bất kỳ trường nào.
- [x] Không có ca nào cho ra `closedRemainingVnd` hoặc `openRemainingVnd` âm.
- [x] Kết quả `ledgerBalance` không chứa trường nào bằng `185000000n`.
- [x] `canClose` với cùng người và còn dòng thiếu giá → `ok false`, `reasons.length === 2`.
- [x] `canClose` khác người và hết dòng thiếu giá → `ok true`, `reasons` rỗng.
- [x] Đầu vào sai định dạng tiền (`'40.000.000'`, `'abc'`, số âm, `12.5`) → ném lỗi, không trả kết quả sai.
- [x] Gọi hàm hai lần với cùng đối số cho cùng kết quả; đối số không bị sửa.

## Phạm vi agent

- Agent: codex
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/preview/so-cong-no-v5-model.js`
  - `cong-no-web-handoff/preview/test-so-cong-no-v5-model.js`
  - `package.json`
- Ngân sách diff: 400
- Lệnh kiểm:
  - `npm run test:unit`
- Cấm:
  - Sửa `so-cong-no-model.js`, `monthly-ledger-model.js`, `customer-ledger-workbench*` hay bất kỳ test cũ nào — màn cũ đang dùng.
  - Sửa `cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html`; mockup đã duyệt, lớp này không đụng tới.
  - Dùng `Number`, `parseFloat`, `toFixed` cho tiền.
  - Thêm dependency, framework, build step hoặc lớp trừu tượng ngoài spec.
  - DOM, `fetch`, API, file, DB, biến toàn cục.
  - Tự quyết chính sách cho bốn điểm CÒN MỞ bên dưới.
- Khi cần vượt phạm vi: dừng, ghi vào "Câu hỏi mở".

`package.json` chỉ được thêm file test mới vào `test:unit`, không sửa script khác.

## Còn mở — không chốt hộ

1. Thứ tự 11 cột thật trong bảng tính: chưa đối chiếu. Không ảnh hưởng lớp này.
2. Ai được xác nhận khoản thu và căn cứ gì: hoãn. Lớp này chỉ đọc cờ `receivedOn`, không tự xác nhận.
3. Tiền dư có dùng cho sổ khác của cùng khách không: mặc định là không. `overpaymentVnd` chỉ là một con số trả về, không tự chảy đi đâu.
4. Sổ "chưa mở" có tính là "chưa chốt" không: thuộc lớp 2, không thuộc lớp này.

## Hoàn tác

Hai file mới và một dòng trong `package.json`. Bỏ bằng cách revert commit; không có dữ liệu nào bị đụng.

## Câu hỏi mở

Từ review chốt ngày 17/10/2026. Không cái nào là lỗi tiền trong phạm vi lớp 1; đều là việc của lớp sau hoặc gia cố.

1. **Bucket số dư âm bị loại im lặng.** `if (balance > 0n)` khiến một bucket dạng credit (ví dụ tiền dư kỳ trước mang sang) không vào tổng mà cũng không báo. Nên ném lỗi thay vì nuốt — trừ khi chính sách tiền dư liên kỳ cho phép, mà điều đó còn mở (D04).
2. **Guard `closedVnd`/`openVnd` không bắt được lỗi cộng lại lịch sử**, vì cả buckets lẫn hai số tổng đều do người gọi đưa vào. Lớp 2 phải tự bảo đảm buckets dựng từ số dư từng kỳ, không cộng dồn lại.
3. **`ledgerBalance` không nhận `lines`** nên không chặn được dòng thiếu giá lọt vào `openVnd`. Ràng buộc `openVnd === monthTotals(lines).pricedTotalVnd` thuộc lớp 2.
4. **Không chặn `key` trùng hoặc thiếu** trong buckets, khác tiền lệ `allocateOldestFirst` cũ vốn có `Set` chống trùng kỳ.
5. **`canClose` không phải kiểm quyền.** `enteredBy`/`closedBy` là tên hiển thị dạng chuỗi; hai người trùng tên sẽ qua được cổng. Danh tính thật thuộc lớp 3 và Q01.
6. **`canClose` không xét chứng từ chưa xác nhận.** Đúng spec, và đúng quyết định 5 ngày 17/10 (cho chốt dù còn chứng từ treo) — ghi lại ở đây để lớp sau không tưởng là sót.
