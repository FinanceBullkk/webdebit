# Lớp 1 — model tiền cho sổ công nợ V6

Trạng thái: **ĐỀ XUẤT** (Claude, 18/10/2026). Chưa triển khai.

Cập nhật 18/10/2026: bổ sung `lines` cho tháng opening (dòng chuyến đầy đủ, tiền **chỉ để hiển thị**) và `pricedCount` / `monthTotalVnd` cho mỗi tháng của `monthChain`. Opening vẫn **không** bị tính lại: số dư tháng opening vẫn lấy từ `endOfMonthVnd` và `remainingVnd`.

Lớp 1 của ba lớp dựng sổ công nợ V6: **model tiền thuần JavaScript, có test, không giao diện**. Lớp 2 (giao diện, [v6-giao-dien.md](v6-giao-dien.md)) chỉ gọi các hàm ở đây; lớp 3 (backend thật) là spec riêng, chưa tới.

Nguồn: [quyết định V6](ux-v6-quyet-dinh-2026-10-18.md) (V6-1 → V6-9), [business-rules](../docs/business-rules.md), brief [§6](ux-brief-so-cong-no.md) cho số mẫu.

**Không mở đường ghi tiền.** Hàm tính trong bộ nhớ, không API, không DB, không ghi sổ thật.

## Người dùng và luồng (bước 1)

Lớp này không có màn hình, nhưng quyết định mọi con số người dùng thấy:

- *Người nhập* dán chuyến → cần **thành tiền từng dòng**, **phát sinh trong tháng** (dòng thiếu giá không cộng) và **dòng nào lệch với cột thành tiền của sheet**.
- *Người thu tiền* ghi khoản thu → cần **còn phải thu cuối tháng** của từng tháng, và **khoản thu đó trừ vào tháng nào, mỗi tháng bao nhiêu**.
- *Bất kỳ ai sửa số* → cần biết **tháng này còn sửa thẳng được không**, hay phải ghi dòng điều chỉnh.

Không còn bước chốt, không còn người duyệt (V6-1, V6-2).

## Đầu ra

Module mới `cong-no-web-handoff/preview/so-cong-no-v6-model.js` xuất **sáu hàm thuần**, kèm `test-so-cong-no-v6-model.js` chạy bằng `node --test` và được thêm vào `npm run test:unit`.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Khuôn mẫu theo** `so-cong-no-v5-model.js`: tiền là `BigInt`; đầu vào là chuỗi chữ số kiểm bằng regex trước khi `BigInt(...)`; IIFE + `module.exports`; test bằng `node:assert/strict`.

**Bê nguyên, không viết lại:** `lineAmount` và `monthTotals` của V5 (thêm phần lệch thành tiền, xem dưới). Logic trừ lần lượt của `allocateReceipt` V5 dùng lại được.

**Không sửa** `so-cong-no-v5-model.js` và test của nó — bản thử V5 còn chạy trên đó cho tới khi lớp 2 V6 thay.

**Bỏ hẳn so với V5:** hai nhóm bucket `closed` / `open`, `ledgerBalance` tách hai số, `canClose`, tiêu chí "không trường nào bằng 185.000.000".

### Opening và tháng web là hai loại tháng khác nhau

Đây là điểm dễ làm sai nhất.

- **Tháng opening** là tháng chuyển từ Sheet sang (fixture: 01–03.2026). Model **không** tự tính lại chúng. Đầu vào cho mỗi tháng opening là: còn phải thu cuối tháng (để hiển thị) và **số còn nợ của riêng tháng đó** tại lúc chuyển (để phân bổ). Theo business-rules: *không phân bổ lại opening*.
- **Tháng web** là tháng nhập trên web (fixture: 04.2026 trở đi). Model tính lại toàn bộ từ chuyến, điều chỉnh và khoản thu.
- **Điều chỉnh** được phép ở cả hai loại tháng (V6-3c). Điều chỉnh tháng opening cộng vào số còn nợ của tháng đó và vào còn phải thu cuối tháng của nó, rồi lan sang mọi tháng sau.
- **Khoản thu web** được phân bổ lại mỗi lần tính (V6-3d), theo nợ cũ trước, qua cả số còn nợ opening lẫn tháng web.

Vì vậy với fixture, khoản thu 120.000.000 ra `20 / 20 / 30 / 25` cho opening rồi `25` cho tháng 04 — **không** phải tính lại từ đầu năm.

## Dữ liệu vào: một sổ

```js
{
  opening: {
    beforeKey: "before-2026-01",
    beforeBalanceVnd: "20000000",           // còn nợ trước tháng opening đầu tiên
    months: [                                // tăng dần, liên tục
      { key: "2026-01", endOfMonthVnd: "40000000", remainingVnd: "20000000",
        lines: [trip("DEMO-101", "20000000")] },
      { key: "2026-02", endOfMonthVnd: "70000000", remainingVnd: "30000000",
        lines: [trip("DEMO-102", "30000000")] },
      { key: "2026-03", endOfMonthVnd: "95000000", remainingVnd: "25000000",
        lines: [trip("DEMO-104", "25000000")] },
    ],
  },
  months: [                                  // tháng web, tăng dần, sau tháng opening cuối
    { key: "2026-04", lines: [ /* xem dưới */ ] },
  ],
  adjustments: [                             // V6-3, V6-3c
    { id: "ADJ-1", monthKey: "2026-03", lineId: "DEMO-104", amountVnd: "5000000", reason: "Thiếu phí áp tải chuyến DEMO-104" },
  ],
  receipts: [                                // khoản thu của sổ + kỳ (V5-UX quyết định 1)
    { id: "UNC-0420", monthKey: "2026-04", receivedOn: "2026-04-20", method: "Chuyển khoản", ref: "UNC-0420", amountVnd: "120000000" },
    { id: "CT-CHO-05", monthKey: "2026-04", receivedOn: null, method: null, ref: "CT-CHO-05", amountVnd: "5000000" },
  ],
}
```

Một dòng chuyến: `{ id, unitPriceVnd, otherFeeVnd, plugFeeVnd, escortFeeVnd, pastedAmountVnd }`, mỗi tiền là chuỗi chữ số hoặc `null`. `pastedAmountVnd` là cột thành tiền dán từ sheet, **chỉ để đối chiếu**. Trong khối trên, `trip(id, unitPriceVnd)` là lối viết tắt cho một dòng đủ trường với ba phí và `pastedAmountVnd` bằng `null`. Mọi trường đều bắt buộc có mặt — thiếu trường là ném lỗi, không coi là `null`.

### `lines` của tháng opening

Tháng opening mang **dòng chuyến đầy đủ**, cùng hình dạng với dòng tháng web (`trip(...)` ở trên là lối viết tắt cho một dòng đủ trường, phí `null`). Tiền trên dòng là **số đã chuyển từ Sheet sang, chỉ để hiển thị và để tra `lineId`**.

- Dùng cho hai việc: `validateAdjustment` kiểm `lineId`, và `monthChain` tính `pricedCount` / `monthTotalVnd` của dòng TỔNG.
- **Không** đụng tới số dư: `chargesVnd` của tháng opening vẫn là `null`, và `endOfMonthVnd` vẫn lấy từ `opening.endOfMonthVnd` cộng điều chỉnh — **không** cộng lại từ `lines`. Đây là ranh giới giữ "opening không tính lại".
- `missingPriceIds` và `mismatches` của tháng opening vẫn là `[]`: dòng opening không bị kiểm giá, không bị đối chiếu cột dán.
- Bắt buộc có mặt ở mọi tháng opening; `[]` hợp lệ, khi đó `monthTotalVnd` của tháng chỉ còn phần điều chỉnh và mọi `lineId !== null` trỏ vào tháng này đều bị từ chối.

Ràng buộc đầu vào, sai thì ném lỗi:

- `beforeBalanceVnd + Σ opening.months[].remainingVnd` = `endOfMonthVnd` của tháng opening cuối. Fixture: `20 + 20 + 30 + 25 = 95`.
- Khóa tháng dạng `YYYY-MM`, không trùng, tăng dần; tháng web đứng sau tháng opening cuối. Tháng web **được phép cách quãng** (sheet bỏ tháng không có hàng).
- `adjustments[].amountVnd` có dấu (`/^-?\d+$/`); `reason` không rỗng sau khi bỏ khoảng trắng; `monthKey` phải là tháng có trong sổ.
- `opening.months[].lines` là mảng (có thể rỗng) các dòng chuyến đủ trường, `id` là chuỗi không rỗng, không trùng trong cùng một tháng. Trùng `id` giữa các tháng không ném lỗi (model chỉ tra trong đúng tháng của `monthKey`), nhưng fixture tránh trùng: opening dùng `DEMO-101`, `DEMO-102`, `DEMO-104`; tháng 04 dùng `DEMO-105`, `DEMO-106`, `DEMO-107`, `DEMO-103`.
- Mọi tiền khác không âm.

## Hợp đồng hàm

Sáu hàm, không hơn. Tiền vào là chuỗi hoặc `BigInt`, tiền ra là `BigInt`; `null` là chưa biết, khác `0n`.

### 1. `lineAmount(line) -> BigInt | null`

Như V5: đơn giá `null` → `null`; ngược lại đơn giá + ba phí, phí `null` cộng như không phát sinh.

### 2. `monthTotals(lines) -> { pricedCount, pricedTotalVnd, missingPriceIds, mismatches }`

Như V5, thêm `mismatches`: với mỗi dòng có `pastedAmountVnd !== null` và `lineAmount !== null` mà hai số khác nhau → `{ id, pastedVnd, computedVnd, diffVnd }` với `diffVnd = |pasted − computed|`. **Không sửa dòng, không bỏ dòng**; số tính vào phát sinh luôn là `computedVnd`.

### 3. `isDirectEditable(monthKey, todayIso) -> boolean`

V6-3b. `todayIso` là chuỗi `YYYY-MM-DD` theo giờ Việt Nam do người gọi đưa vào; **không dùng `Date` bên trong** để khỏi lệch múi giờ.

- `true` khi `todayIso` ≤ ngày `05` của tháng liền sau `monthKey`, hoặc `monthKey` là tháng hiện tại / tương lai.
- Ngày lịch, không trừ ngày nghỉ.

### 4. `monthChain(book) -> Month[]`

Mọi tháng của sổ, theo thứ tự, mỗi tháng:

```js
{ key, source: "opening" | "web",
  carryVnd,            // = endOfMonthVnd của tháng liền trước (tháng đầu: beforeBalanceVnd)
  chargesVnd,          // tháng web: monthTotals(lines).pricedTotalVnd; tháng opening: null
  adjustmentsVnd,      // Σ điều chỉnh của tháng
  receivedVnd,         // Σ khoản thu đã có receivedOn, cùng monthKey; tháng opening: null
  endOfMonthVnd,       // có dấu
  lineCount,           // số dòng chuyến của tháng, cho nhãn "n cont"
  pricedCount,         // số dòng có giá (lineCount trừ số dòng thiếu giá)
  monthTotalVnd,       // số ở dòng TỔNG: monthTotals(lines).pricedTotalVnd + adjustmentsVnd
  missingPriceIds, mismatches }   // tháng opening: [] (dòng opening không bị kiểm giá)
```

- Tháng web: `endOfMonthVnd = carryVnd + chargesVnd + adjustmentsVnd − receivedVnd`.
- Tháng opening: `endOfMonthVnd = opening.endOfMonthVnd + Σ điều chỉnh của mọi tháng opening từ tháng đầu tới tháng này`.
- Nhãn `n cont` dùng `lineCount`, **không** dùng `pricedCount`: người dùng đếm container đã chạy, dòng chưa có giá vẫn là một container. Fixture tháng 04: `4 cont` với `pricedCount 3`.
- `lineCount`, `pricedCount` và `monthTotalVnd` tính như nhau ở cả hai loại tháng, từ `lines` của tháng đó cộng `adjustmentsVnd`. Đây là **số của dòng TỔNG**, không phải số dư; giao diện không được dùng nó thay `endOfMonthVnd`.
- `monthTotalVnd` của tháng opening **không** làm đổi `endOfMonthVnd` của tháng đó hay của tháng sau.
- `endOfMonthVnd` và `monthTotalVnd` là hai trường **duy nhất** được âm; `endOfMonthVnd` âm nghĩa là khách đã ứng trước (V6-5), `monthTotalVnd` âm nghĩa là điều chỉnh giảm lớn hơn phát sinh.
- Bất biến nối tháng (brief quy tắc 12): `carryVnd` của tháng sau luôn bằng `endOfMonthVnd` của tháng trước.

### 5. `allocate(book) -> { receipts: [{ id, allocations: [{ key, amountVnd }], overpaymentVnd }], remaining: [{ key, balanceVnd }], overpaymentVnd }`

V6-3d. Trả lời "khoản thu này trừ vào tháng nào".

- **Danh sách nợ theo thứ tự:** `beforeKey` (`beforeBalanceVnd`) → từng tháng opening (`remainingVnd` + điều chỉnh của tháng đó) → từng tháng web (`chargesVnd` + điều chỉnh).
- **Khoản thu dùng để phân bổ:** chỉ khoản có `receivedOn`, xếp theo `receivedOn` rồi `id`. Khoản `receivedOn === null` bị loại, không vào bất kỳ tổng nào.
- Mỗi khoản thu trừ lần lượt vào phần còn nợ của danh sách, cũ nhất trước, kể cả tháng **sau** tháng của khoản thu (ứng trước trừ vào nợ sau).
- Phần còn lại sau khi hết nợ → `overpaymentVnd` của khoản thu đó, cộng dồn vào `overpaymentVnd` cuối.
- Một mục nợ âm (điều chỉnh giảm nhiều hơn số nợ của tháng) → **ném lỗi**. CÒN MỞ: xử lý thế nào.
- **Bất biến 1:** với mỗi khoản thu, `Σ allocations + overpaymentVnd = amountVnd`.
- **Bất biến 2:** `Σ remaining.balanceVnd − overpaymentVnd` = `endOfMonthVnd` của tháng cuối trong `monthChain`.
- Không sửa `book`. Cùng `book` cho cùng kết quả.

### 6. `validateAdjustment(adjustment, book) -> { ok, reasons }`

Nêu **đủ mọi lý do** một lần (brief quy tắc 11b): thiếu lý do; số tiền sai định dạng hoặc bằng 0; tháng không có trong sổ; `lineId` không có trong tháng đó (khi khác `null`).

Cách kiểm `lineId` **giống nhau ở cả hai loại tháng**: so với `id` của các phần tử trong `lines` của tháng mang `monthKey` — tháng web là dòng chuyến, tháng opening là danh sách tra cứu ở trên. `lineId === null` nghĩa là điều chỉnh của cả tháng, không kiểm. Tháng không có trong sổ thì chỉ nêu lý do tháng, không nêu thêm lý do `lineId`.

## Hành vi và bất biến

- VND nguyên chính xác bằng `BigInt`. Không `Number`, không `parseFloat`, không làm tròn.
- `null` khác `0n`; chỉ ba loại phí trong `lineAmount` được coi `null` là không phát sinh.
- Dòng thiếu giá không vào `chargesVnd`.
- Khoản thu chưa có ngày nhận nằm ngoài mọi tổng.
- Opening không bị tính lại; chỉ điều chỉnh được cộng thêm vào opening.
- Mọi hàm thuần: không sửa đối số, không trạng thái dùng chung.

## Tiêu chí nghiệm thu

`npm run test:unit` xanh, test cũ không gãy, và file test mới phủ đúng các số dưới. Sổ mẫu là `book` ở mục "Dữ liệu vào" **bỏ** `adjustments` và khoản `UNC-0420`, trừ khi ca nói khác.

- [ ] `monthTotals` tháng 04: `pricedCount 3`, `pricedTotalVnd 90000000n`, `missingPriceIds ["DEMO-103"]`, `mismatches []`.
- [ ] `monthChain`: cuối tháng `40 / 70 / 95` triệu cho 01–03; tháng 04 `carryVnd 95000000n`, `chargesVnd 90000000n`, `receivedVnd 0n`, **`endOfMonthVnd 185000000n`**.
- [ ] Khoản `CT-CHO-05` (5.000.000, `receivedOn null`) không làm đổi bất kỳ số nào.
- [ ] Thêm thu `120000000` ngày `2026-04-20`: tháng 04 `endOfMonthVnd 65000000n`; `allocate` cho khoản đó `20 / 20 / 30 / 25` triệu (before-01, 01, 02, 03) rồi `25` triệu (04), `overpaymentVnd 0n`.
- [ ] Thay bằng thu `200000000`: tháng 04 `endOfMonthVnd -15000000n`; allocations `20 / 20 / 30 / 25 / 90` triệu, `overpaymentVnd 15000000n`.
- [ ] Thêm điều chỉnh `+5000000` vào `2026-03` (không có khoản thu): tháng 03 `endOfMonthVnd 100000000n`; tháng 04 `carryVnd 100000000n`, **`endOfMonthVnd 190000000n`**; tháng 01, 02 không đổi.
- [ ] Điều chỉnh `+5000000` tháng 03 **và** thu `120000000`: allocations `20 / 20 / 30 / 30 / 20` triệu — tháng 03 nhận 30, tháng 04 còn 20 (V6-3d); tháng 04 `endOfMonthVnd 70000000n`.
- [ ] Dán thêm `DEMO-108` đơn giá `12000000` và `DEMO-109` đơn giá `10000000` với `pastedAmountVnd "99000000"`: `chargesVnd 112000000n`, `endOfMonthVnd 207000000n`, `mismatches` có đúng một mục `{ id: "DEMO-109", pastedVnd 99000000n, computedVnd 10000000n, diffVnd 89000000n }`.
- [ ] `isDirectEditable("2026-04", "2026-05-05") === true`; `isDirectEditable("2026-04", "2026-05-06") === false`; `isDirectEditable("2026-12", "2027-01-05") === true`; `("2026-12", "2027-01-06") === false`; tháng hiện tại luôn `true`.
- [ ] `validateAdjustment` thiếu lý do **và** số tiền `0` → `ok false`, `reasons.length === 2`.
- [ ] `validateAdjustment` với `monthKey "2026-03"`, `lineId "DEMO-104"`, số tiền và lý do hợp lệ → `ok true`, `reasons` rỗng (dòng opening tra được).
- [ ] Cùng ca trên nhưng `lineId "DEMO-999"` → `ok false`, đúng một lý do về `lineId`; với `lineId null` → `ok true`.
- [ ] `lineId "DEMO-105"` của tháng web `2026-04` → `ok true`; `monthKey "2026-09"` (không có trong sổ) → `ok false`, lý do chỉ nói về tháng.
- [ ] Dòng TỔNG: tháng 03 `lineCount 1`, `pricedCount 1`, `monthTotalVnd 25000000n`; tháng 04 `lineCount 4`, `pricedCount 3`, `monthTotalVnd 90000000n`.
- [ ] Sau khi dán thêm `DEMO-108`, `DEMO-109`: tháng 04 `lineCount 6`, `pricedCount 5`.
- [ ] Với điều chỉnh `+5000000` tháng 03: tháng 03 `monthTotalVnd 30000000n`, `pricedCount` vẫn `1`; `endOfMonthVnd` của tháng 01, 02 và `carryVnd` tháng 03 không đổi.
- [ ] Thêm dòng vào `lines` của tháng opening làm đổi `pricedCount` và `monthTotalVnd` của tháng đó nhưng **không** đổi `endOfMonthVnd` của bất kỳ tháng nào, cũng không đổi kết quả `allocate`.
- [ ] Hai bất biến của `allocate` đúng ở mọi ca trên.
- [ ] Đầu vào sai (`'40.000.000'`, `'abc'`, `12.5`, số âm ở chỗ không cho âm, opening không cộng khớp) → ném lỗi.
- [ ] Gọi hai lần cùng đầu vào cho cùng kết quả; đầu vào đóng băng (`Object.freeze`) không gây lỗi.

## Phạm vi agent

- Agent: codex
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/preview/so-cong-no-v6-model.js` (mới)
  - `cong-no-web-handoff/preview/test-so-cong-no-v6-model.js` (mới)
  - `package.json` — chỉ thêm file test mới vào `test:unit`
- Ngân sách diff: 450
- Lệnh kiểm:
  - `npm run test:unit`
- Cấm:
  - Sửa `so-cong-no-v5-model.js`, các model cũ hay test cũ.
  - Dùng `Number`, `parseFloat`, `toFixed`, `Date` cho tiền hoặc cho phép so ngày.
  - DOM, `fetch`, API, file, DB, biến toàn cục.
  - Thêm dependency, framework, build step.
  - Tự quyết các điểm CÒN MỞ bên dưới.
- Khi cần vượt phạm vi: dừng, ghi vào "Câu hỏi mở".

## Còn mở — không chốt hộ

1. Điều chỉnh giảm làm một tháng âm: hiện ném lỗi.
2. Tiền ứng trước có trừ được cho sổ khác của cùng khách không (`D04`): mặc định không; `overpaymentVnd` nằm lại trong sổ.
3. Dòng phí không có container trong sheet: chưa có kiểu dòng riêng.
4. Lưu vết sửa (ai, lúc nào, số cũ → số mới) thuộc lớp 3; model không giữ lịch sử.

## Hoàn tác

Hai file mới và một dòng trong `package.json`. Revert commit; không đụng dữ liệu.

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
