# Lớp 2 — giao diện sổ công nợ V5 nối vào model

Trạng thái: **ĐÃ TRIỂN KHAI** ở mức bản thử chạy trong tab (merge `790fa1e`); giao diện **ĐÃ CHỐT** (người dùng, 18/10/2026 — mục `V5-GD` trong [docs/decisions.md](../docs/decisions.md)). Lớp 3 (backend thật) chưa tới; bốn điểm "Còn mở" bên dưới vẫn chưa chốt.

Lớp 2 của ba lớp: **lấy mockup đã duyệt, bỏ fixture cứng, nối vào model lớp 1**. Lớp 1 đã xong và đã kiểm chứng ([v5-model-tien.md](v5-model-tien.md)); lớp 3 (backend thật) là spec riêng, chưa tới.

Nguồn: [spec mockup đã duyệt](ux-v5-mockup-vong-2.md), [quyết định 17/10](ux-v5-quyet-dinh-2026-10-17.md), [brief](ux-brief-so-cong-no.md) mục 5 và 6.

**Không mở đường ghi tiền.** Trang chạy hoàn toàn trong tab, dữ liệu giả, không API, không lưu gì.

## Người dùng và luồng (bước 1)

Ba vai, trên 40 tuổi, quen bảng tính. Ba việc phải làm được **đúng số thao tác đã đặt**:

1. **Thêm một lô chuyến — 3 thao tác.** Chọn sổ ở cột trái → bấm vào dòng trống cuối bảng → dán. Hộp thoại `Dán từ bảng tính` là đường phụ.
2. **Ghi một khoản thu — gõ thẳng trên dòng.** Chọn dòng → gõ bốn ô ngay tại chỗ (ngày nhận tiền · cách thu · tham chiếu · số tiền) → Enter. Không mở màn khác.
3. **Chốt công nợ một tháng — 3 thao tác.** Chọn sổ → `Chốt công nợ tháng 04` → `Xác nhận chốt`.

Bị chặn khi: người chốt chính là người nhập, hoặc còn dòng chưa có giá. Chặn thì nêu **đủ mọi lý do** một lần.

Trang là bản thử nội bộ nên giữ ô chọn vai đăng nhập (người nhập / người thu tiền / người chốt) để đi hết ba luồng. Đây là tiện ích của bản thử, **không phải cơ chế phân quyền**.

## Đầu ra

`cong-no-web-handoff/preview/so-cong-no-v5.html` chạy được bằng cách mở trực tiếp trong trình duyệt: mọi con số trên màn do model lớp 1 tính ra, mọi thao tác trong ba luồng trên đi được từ đầu đến cuối.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Điểm xuất phát đã có sẵn trong repo:** `so-cong-no-v5.html` hiện là **bản sao nguyên văn của mockup đã duyệt** (commit `8a542fe`). Giữ nguyên HTML, CSS, câu chữ, cỡ chữ, bề rộng cột. Việc của lớp này là thay phần JavaScript dựng sẵn mười khung bằng một trạng thái thật chạy trên model.

**Model đã có, chỉ gọi, không viết lại:** `cong-no-web-handoff/preview/so-cong-no-v5-model.js` xuất năm hàm — `lineAmount`, `monthTotals`, `allocateReceipt`, `ledgerBalance`, `canClose`. (Từ 18/10/2026 model có thêm `allocateReceipts`; xem [v6-model-phan-bo-tung-khoan.md](v6-model-phan-bo-tung-khoan.md).) Chữ ký và hành vi mô tả tại [v5-model-tien.md](v5-model-tien.md). Tiền là `BigInt`; chuỗi chữ số vào, `BigInt` ra.

**Mockup gốc để đối chiếu:** `cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html` — **không được sửa**, nó là mốc đã duyệt.

**Số liệu giả** lấy nguyên từ [spec mockup](ux-v5-mockup-vong-2.md) mục "Đối chiếu dữ liệu": 5 sổ mẫu, bốn chuyến DEMO-105/106/107/103, chứng từ treo `CT-CHO-05` 5.000.000, khoản thu 120.000.000 và 200.000.000.

**Khuôn mẫu tách tệp** theo cặp có sẵn `customer-ledger-workbench.js` / `customer-ledger-workbench-ui.js`: logic trạng thái tách khỏi dựng DOM.

## Giao tiếp frontend–backend (bước 5)

Chưa có backend. Trang `require`/nhúng model lớp 1 và chạy trên fixture trong bộ nhớ. Khi có backend, lớp 3 chỉ thay **nguồn dữ liệu**; chữ ký năm hàm giữ nguyên.

## Hợp đồng giữa giao diện và model

Đây là phần quan trọng nhất của lớp này.

**Giao diện không được tự tính tiền.** Không `+`, `-`, `reduce` trên tiền trong mã giao diện. Mọi con số hiện trên màn phải đến từ một trong năm hàm. Nếu cần một con số mà năm hàm không cho, **dừng lại và hỏi**, đừng tự cộng.

Ba ràng buộc review lớp 1 đã nêu, phải xử lý ở đây:

1. **`openVnd` phải lấy từ `monthTotals(lines).pricedTotalVnd`**, không bao giờ gõ cứng và không tự cộng. `ledgerBalance` không nhận `lines` nên nó không tự chặn được dòng thiếu giá lọt vào số dư — chặn nằm ở đây.
2. **`buckets` dựng từ số dư từng kỳ, không cộng dồn.** Năm bucket cho sổ mẫu: `before-T01 20tr`, `T01 20tr`, `T02 30tr`, `T03 25tr` (kind `closed`), `T04 90tr` (kind `open`). Tổng bốn bucket `closed` đúng bằng `closedVnd` 95tr — chính là ba thanh tháng `40 / 70 / 95` dưới dạng số phát sinh từng kỳ, **không phải** cộng lại số dư lũy kế.
3. **Bảng phân bổ gọi `allocateReceipt` cho từng khoản thu**, không dùng kết quả gộp của `ledgerBalance`. Người dùng hỏi "tiền tôi trả trừ vào tháng nào" là hỏi về một khoản thu cụ thể.

Và:

4. **`canClose` không phải cổng quyền.** Nó so tên hiển thị. Giao diện dùng nó để hiện lý do chặn, không được mô tả nó là kiểm quyền trên màn hình.
5. **Khoản thu chưa có ngày nhận tiền** truyền vào với `receivedOn: null` — model tự loại. Giao diện vẫn hiện số đó trên dòng kèm chữ `chưa xác nhận`.

## Hành vi và bất biến

- VND số nguyên, ghi đủ số. Định dạng hiển thị dùng dấu chấm phân nhóm; chuyển `BigInt` sang chuỗi, không qua `Number`.
- Ô chưa biết hiện `—`, không hiện `0`.
- Hai số `đã chốt` và `đang mở` luôn tách riêng; không chỗ nào in ra tổng gộp của hai số.
- Ba thanh tháng lịch sử `40.000.000 / 70.000.000 / 95.000.000` không đổi sau bất kỳ thao tác nào.
- Số âm chỉ xuất hiện ở `endOfMonthVnd` khi khách trả dư, luôn kèm chữ `khách trả dư · phải trả lại`.
- Dán tối đa 50 dòng mỗi lần, đúng 11 cột theo thứ tự; cột `Thành tiền` dán vào chỉ dùng **đối chiếu**: lệch với số model tính thì báo `lệch X, kiểm lại`, không tự sửa, không tự bỏ dòng.
- Giữ nguyên câu chữ và nhãn của mockup đã duyệt. Đổi chữ là đổi thiết kế đã duyệt, phải hỏi.
- Cỡ chữ tối thiểu 16px, vùng bấm tối thiểu 40px, tương phản tối thiểu 4.5:1 — mockup đã đạt, đừng làm hỏng.
- Bàn phím đi hết được luồng dán và luồng gõ tiền; phần tử đang focus phải thấy viền.

## Trạng thái cần có trên mockup

Mockup đã duyệt rồi, không vẽ lại. Mười một trạng thái dưới đây là của **trang thật**, dùng cho mục "Ảnh chụp giao diện".

## Ảnh chụp giao diện

Trang thật, chụp bằng thao tác thật. Giữ các `data-action` sẵn có của mockup làm điểm bám; cần thêm thì đặt tên theo cùng lối.

```json
{
  "page": "cong-no-web-handoff/preview/so-cong-no-v5.html",
  "viewports": [[1500, 1000]],
  "states": [
    {"name": "mac-dinh", "board": "01 · Mặc định", "note": "So KHACH_MAU, thang 04 dang mo, DEMO-103 thieu gia",
     "shot": "", "fullPage": true, "steps": []},
    {"name": "bung-chi-tiet", "board": "02 · Bung chi tiết", "note": "Bung 7 truong cua DEMO-105",
     "shot": "", "fullPage": true, "steps": [{"click": "[data-action=\"expand-row\"][data-value=\"DEMO-105\"]"}]},
    {"name": "dan-bang-tinh", "board": "03 · Dán 11 cột", "note": "Hop thoai dan, liet ke 11 cot",
     "shot": "", "fullPage": true, "steps": [{"click": "[data-action=\"open-paste\"]"}]},
    {"name": "go-tien-tren-dong", "board": "04 · Gõ tiền trên dòng", "note": "Bon o nhap ngay tai dong DEMO-105",
     "shot": "", "fullPage": true, "steps": [{"click": "[data-action=\"row-payment\"][data-value=\"DEMO-105\"]"}]},
    {"name": "thu-120-trieu", "board": "05 · Thu 120 triệu", "note": "Da chot 0, dang mo 65 trieu",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"row-payment\"][data-value=\"DEMO-105\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]},
       {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]},
       {"fill": ["[data-pay=\"amount\"]", "120000000"]},
       {"press": "Enter"}]},
    {"name": "phan-bo-120-trieu", "board": "05 · Thu 120 triệu", "note": "Bang phan bo theo tung ky",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"row-payment\"][data-value=\"DEMO-105\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]},
       {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]},
       {"fill": ["[data-pay=\"amount\"]", "120000000"]},
       {"press": "Enter"},
       {"click": "[data-action=\"allocation\"]"}]},
    {"name": "chan-chot-hai-ly-do", "board": "06 · Chặn chốt", "note": "Dang nhap nguoi nhap, con dong thieu gia",
     "shot": "", "fullPage": true, "steps": [
       {"select": ["[data-action=\"actor\"]", "Nguyễn Văn A"]},
       {"click": "[data-action=\"open-close\"]"}]},
    {"name": "chot-hop-le", "board": "07 · Chốt hợp lệ", "note": "Nguoi chot khac nguoi nhap, DEMO-103 da co gia",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"row-edit\"][data-value=\"DEMO-103\"]"},
       {"fill": ["[data-edit-row=\"DEMO-103\"][data-col=\"price\"]", "15000000"]},
       {"press": "Enter"},
       {"select": ["[data-action=\"actor\"]", "Lê Văn C"]},
       {"click": "[data-action=\"open-close\"]"}]},
    {"name": "loc-chua-chot", "board": "08 · Lọc chưa chốt", "note": "2 tren 5 so mau",
     "shot": "", "fullPage": true, "steps": [{"click": "[data-action=\"filter\"][data-value=\"unclosed\"]"}]},
    {"name": "bo-dong-co-chung-tu", "board": "09 · Bỏ dòng có chứng từ", "note": "Xac nhan bo dong kem chung tu treo",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"row-menu\"][data-value=\"DEMO-103\"]"},
       {"click": "[data-action=\"row-remove\"][data-value=\"DEMO-103\"]"}]},
    {"name": "khach-tra-du", "board": "10 · Khách trả dư", "note": "Am 15 trieu kem chu phai tra lai",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"row-payment\"][data-value=\"DEMO-105\"]"},
       {"fill": ["[data-pay=\"date\"]", "22/04/2026"]},
       {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0422"]},
       {"fill": ["[data-pay=\"amount\"]", "200000000"]},
       {"press": "Enter"}]},
    {"name": "chot-da-xac-nhan", "board": "07 · Chốt hợp lệ", "note": "Bam het nut xac nhan chot, khong dung o hop thoai",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"row-edit\"][data-value=\"DEMO-103\"]"},
       {"fill": ["[data-edit-row=\"DEMO-103\"][data-col=\"price\"]", "15000000"]},
       {"press": "Enter"},
       {"select": ["[data-action=\"actor\"]", "Lê Văn C"]},
       {"click": "[data-action=\"open-close\"]"},
       {"click": "[data-action=\"close-sim\"]"}]},
    {"name": "phan-bo-sau-chot", "board": "07 · Chốt hợp lệ", "note": "Chot 105 trieu roi thu 120 trieu: con 80 trieu da chot",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"row-edit\"][data-value=\"DEMO-103\"]"},
       {"fill": ["[data-edit-row=\"DEMO-103\"][data-col=\"price\"]", "15000000"]},
       {"press": "Enter"},
       {"select": ["[data-action=\"actor\"]", "Lê Văn C"]},
       {"click": "[data-action=\"open-close\"]"},
       {"click": "[data-action=\"close-sim\"]"},
       {"click": "[data-action=\"row-payment\"][data-value=\"DEMO-105\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]},
       {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]},
       {"fill": ["[data-pay=\"amount\"]", "120000000"]},
       {"press": "Enter"},
       {"click": "[data-action=\"allocation\"]"}]},
    {"name": "dan-tsv-that", "board": "03 · Dán 11 cột", "note": "Dan that: o trong o hai dau va mot dong lech thanh tien",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"open-paste\"]"},
       {"fill": ["[data-action=\"paste-text\"]", "\tDEMO-108\tWH\t25/04/2026\tPHAN THIET\tSHEKOU\t\t\t\t12000000\t\n\tDEMO-109\tWH\t26/04/2026\tPHAN THIET\tSHEKOU\t\t\t\t10000000\t99000000"]},
       {"click": "[data-action=\"paste-submit\"]"}]},
    {"name": "dan-truc-tiep-cuoi-bang", "board": "03 · Dán 11 cột", "note": "Duong chinh: dan thang vao dong trong cuoi bang",
     "shot": "", "fullPage": true, "steps": [
       {"paste": ["[data-action=\"inline-paste\"]", "\tDEMO-110\tWH\t27/04/2026\tPHAN THIET\tSHEKOU\t\t\t\t8000000\t"]}]},
    {"name": "tien-sai-dinh-dang", "board": "04 · Gõ tiền trên dòng", "note": "Nhap -5000000: phai chan va giu nguyen noi dung da go",
     "shot": "", "steps": [
       {"click": "[data-action=\"row-payment\"][data-value=\"DEMO-105\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]},
       {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]},
       {"fill": ["[data-pay=\"amount\"]", "-5000000"]},
       {"press": "Enter"}]},
    {"name": "tien-sai-dinh-dang-1e6", "board": "04 · Gõ tiền trên dòng", "note": "Nhap 1e6: phai chan, giu nguyen bon o, so du khong doi",
     "shot": "", "steps": [
       {"click": "[data-action=\"row-payment\"][data-value=\"DEMO-105\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]},
       {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]},
       {"fill": ["[data-pay=\"amount\"]", "1e6"]},
       {"press": "Enter"}]},
    {"name": "khoa-khoan-thu-cu", "board": "05 · Thu 120 triệu", "note": "Sau khi ghi 120 trieu, dong DEMO-105 khong con nut mo lai khoan thu",
     "shot": "", "fullPage": true, "steps": [
       {"click": "[data-action=\"row-payment\"][data-value=\"DEMO-105\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]},
       {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]},
       {"fill": ["[data-pay=\"amount\"]", "120000000"]},
       {"press": "Enter"}]}
  ]
}
```

Selector trên là **hợp đồng**: giữ đúng tên `data-action`/`data-pay`/`data-col` này, hoặc nếu phải đổi thì sửa luôn khối json trong spec và nói rõ trong báo cáo. Thử bằng `-Step capture` trước khi giao.

## Tiêu chí nghiệm thu

- [ ] `npm run test:unit` xanh — model lớp 1 và các test cũ không gãy.
- [ ] `-Step capture` chụp đủ 11 trạng thái, không bước nào lỗi selector.
- [ ] Không phát hiện đo được nào: cỡ chữ ≥ 16px, tương phản ≥ 4.5:1, vùng bấm ≥ 40px, không cuộn ngang, không lỗi JS, không từ kỹ thuật hay tiền viết tắt trên màn.
- [ ] Ảnh từng trạng thái khớp board mockup tương ứng: cùng bố cục, cùng câu chữ, cùng cột.
- [ ] `thu-120-trieu`: đã chốt `0 · đã thu đủ`, đang mở `65.000.000`, đã thu trong tháng `120.000.000`, còn phải thu cuối tháng `0`.
- [ ] `phan-bo-120-trieu`: bảng ra `20 / 20 / 30 / 25` rồi `hết phần đã chốt 95.000.000` rồi `tháng 04 · đang mở 25.000.000`, tổng `120.000.000`.
- [ ] `khach-tra-du`: đã chốt `0`, đang mở `0`, còn phải thu cuối tháng `−15.000.000` kèm chữ `khách trả dư · phải trả lại`.
- [ ] Ba thanh tháng `40 / 70 / 95` không đổi ở **mọi** trạng thái.
- [ ] Không màn nào in ra `185.000.000`.
- [ ] `chan-chot-hai-ly-do`: nêu **cả hai** lý do trong một lần.
- [ ] `chot-hop-le`: `4 chuyến có giá · 105.000.000`, và câu cho biết chứng từ 5.000.000 vẫn treo.
- [ ] Dán 11 cột vào dòng trống cuối bảng thêm được chuyến; `Thành tiền` lệch thì báo `lệch X, kiểm lại` chứ không tự sửa.
- [ ] Tìm trong mã giao diện không còn phép cộng/trừ nào trên tiền; mọi số đến từ năm hàm của model.
- [ ] Người dùng tự đi hết ba luồng trên bản thử và xác nhận (bước 8, không agent nào thay được).

## Việc còn lại — vòng sửa 1

Vòng đầu do gemini dựng, commit `a8112a0` trên `gemini/v5-giao-dien`. Bằng chứng đạt: `npm run test:unit` 17/17 PASS, 11 trạng thái chụp chạy hết, không lỗi selector, số tiền trên các màn đã xem khớp spec. Review hai tầng kết luận **CẦN SỬA**; vòng này sửa đúng những điểm dưới, **giữ nguyên phần đã đạt**.

**P1 — đường tiền:**

1. **Chốt chỉ đổi nhãn, không chuyển số dư** (`so-cong-no-v5-ui.js:667`). Sau khi xác nhận chốt 105 triệu, sổ mang nhãn "Đã chốt" nhưng tiền vẫn nằm ở phần "Đang mở". Dựng lại đầu vào model theo trạng thái đã chốt; **không tự cộng tiền trong UI**.
2. **Ghi đè khoản thu đã ghi nhận** (`so-cong-no-v5-ui.js:519`). Nhập 200 triệu sau khoản 120 triệu làm khoản cũ biến mất, phân bổ tính lại, không đảo, không lưu vết. Khóa sửa khoản đã ghi nhận; nếu đỡ nhiều khoản thu thì giữ từng khoản riêng và gọi `allocateReceipt` riêng cho từng khoản.
3. **Chuẩn hóa đầu vào làm đổi nghĩa số tiền** (`so-cong-no-v5-ui.js:24`). Đang xóa mọi ký tự ngoài chữ số, nên `-5000000` thành `5000000` và `1e6` thành `16`, rồi đưa vào model như tiền hợp lệ. Kiểm định dạng **trước**; chỉ bỏ dấu phân nhóm hợp lệ; đầu vào sai thì báo lỗi và giữ nguyên nội dung người dùng đã gõ.

**P2:**

4. **Dán mất cột trống ở hai đầu** (`so-cong-no-v5-ui.js:449`). `.trim()` trước khi tách cột làm tab đầu/cuối biến mất, nên dòng đủ 11 cột có STT trống hoặc Thành tiền trống bị báo thiếu cột. Giữ tab, chỉ loại dòng cuối rỗng. Cần bằng chứng cho cả hai trường hợp.
5. **Bốn sổ còn dùng số dư dựng sẵn** (`so-cong-no-v5-ui.js:330` và `baseClients`). KHACH_B/C/D/E hiển thị tiền thẳng từ fixture, chỉ KHACH_MAU đi qua model. Giữ fixture làm đầu vào, nhưng số hiển thị phải là kết quả từ model.
6. **Bỏ giàn giáo của mockup.** Thanh "Khung đang xem" và link "Xem đủ 10 khung để chụp ảnh" vẫn còn ở đầu trang, lại hiển thị sai trạng thái; chính link đó là cảnh báo vùng bấm 21px. Mười trạng thái giờ tới được bằng thao tác thật nên không cần bộ chọn khung nữa.

**Chưa có bằng chứng, phải bổ sung trong vòng này:** thao tác xác nhận chốt chạy hết, dán dữ liệu thật, và nhập tiền sai định dạng bị chặn đúng cách.

**Bổ sung sau vòng sửa 1 (Claude, 17/10/2026).** Năm trạng thái chụp mới đã được thêm vào mục "Ảnh chụp giao diện" vì kịch bản cũ dừng ngay trước các nhánh vừa sửa: `chot-da-xac-nhan`, `phan-bo-sau-chot`, `dan-tsv-that`, `tien-sai-dinh-dang`, `khoa-khoan-thu-cu`. `specs/` không nằm trong "Được sửa" nên agent không thể tự thêm; đây là lỗi của kịch bản, không phải của bản dựng.

Riêng việc **khóa khoản thu đã ghi nhận** được xác minh bằng một phép thử có chủ ý: thêm bước bấm lại `[data-action="row-payment"]` sau khi đã ghi 120.000.000 thì `locator.click` hết giờ sau 5 giây — nút không còn tồn tại, đúng như yêu cầu. Bước đó đã bỏ khỏi kịch bản để khỏi báo thành lỗi; bằng chứng nằm ở `ui-after/checks.md` của lần chạy trước, mục `khoa-khoan-thu-cu`.

## Việc còn lại — vòng sửa 2

Review sau khi có đủ bằng chứng còn **một lỗi giao diện** và một lỗi kịch bản.

1. **[P1 theo đánh giá của Claude] Sau chốt, nhãn "đã thu đủ" nói sai trạng thái tiền** (`so-cong-no-v5-ui.js:103`, hiển thị ở dòng 200 và 317). Chốt chuyển phần đang mở về `0`, và nhãn lại suy ra "đã thu đủ" từ chính con số `0` đó. Ảnh `chot-da-xac-nhan` cho thấy còn phải thu **200.000.000**, chưa thu đồng nào, mà màn vẫn báo đã thu đủ. Chỉ hiện hậu tố này khi khoản nợ **thật sự được thu hết**, đừng suy từ `openRemaining === 0` sau khi đổi trạng thái chốt.

   Reviewer xếp P2; mình nâng lên P1 vì đây là câu chữ nói sai về tiền trên màn hình chính, đúng loại lỗi brief cấm.

2. **Lỗi kịch bản, đã sửa — không phải việc của agent.** Trạng thái `dan-tsv-that` dùng bước `paste`, mà bước đó chỉ phát một `ClipboardEvent` tổng hợp nên không đặt giá trị vào `textarea`; textarea rỗng và màn báo "Chưa có dữ liệu để dán". Đã đổi sang `fill` cho hộp thoại, và thêm trạng thái `dan-truc-tiep-cuoi-bang` dùng `paste` cho dòng trống cuối bảng — chỗ đó app có nghe sự kiện dán thật.

**Còn thiếu bằng chứng:** thông báo chặn khi nhập `-5000000` (ảnh mới chứng minh giữ nguyên nội dung, chưa thấy câu báo lỗi), và trường hợp `1e6`.

## Việc còn lại — vòng sửa 3

Một việc duy nhất, kèm một sửa kịch bản của người viết spec.

1. **Đặt khối báo lỗi tiền ngay cạnh dòng đang nhập, không phải dưới cả bảng** (`so-cong-no-v5-ui.js:313` đặt khối, `:505-508` focus và cuộn).

   Hiện khối `validation` nằm dưới bảng chuyến. Vòng trước thêm `scrollIntoView` để kéo nó vào tầm nhìn, nhưng đó là sửa triệu chứng: bảng dài ra sau khi dán nhiều dòng thì cuộn xuống cuối bảng lại **đẩy chính ô đang focus ra khỏi màn hình**, vi phạm yêu cầu thấy viền focus và làm người dùng bàn phím mất dấu.

   Việc cần làm: chuyển khối lỗi lên ngay dưới dòng đang nhập tiền — cùng chỗ với thanh `Ghi tại dòng DEMO-105 · khoản thu thuộc sổ…`, nơi mockup đã dành cho thông tin của dòng đó. Giữ focus tại ô `Đã thu`. **Bỏ `scrollIntoView`.** Không đổi câu chữ của thông báo.

2. **Đã sửa trong kịch bản, không phải việc của agent:** hai trạng thái `tien-sai-dinh-dang` và `tien-sai-dinh-dang-1e6` trước đây chụp `fullPage`, nên ảnh luôn chứa khối lỗi dù người dùng thật có nhìn thấy hay không — reviewer phải suy từ toạ độ tài liệu. Hai trạng thái đó nay chụp đúng khung `1500×1000` để ảnh cho thấy **cái người dùng thật sự thấy**.

## Phạm vi agent

- Agent: codex
- Mockup: ĐÃ DUYỆT `cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html` · phiên bản "commit a7ea67b" · người dùng · 17/10/2026
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/preview/so-cong-no-v5.html`
  - `cong-no-web-handoff/preview/so-cong-no-v5-ui.js`
- Ngân sách diff: 400
- Lệnh kiểm:
  - `npm run test:unit`
- Cấm:
  - Sửa `so-cong-no-v5-model.js` — model đã kiểm chứng; thiếu gì thì hỏi, không tự thêm hàm.
  - Sửa `cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html` — mốc đã duyệt.
  - Sửa bất kỳ màn hoặc model cũ nào trong `preview/`.
  - Tự tính tiền trong mã giao diện.
  - Đổi câu chữ, nhãn, cỡ chữ, bề rộng cột của mockup đã duyệt.
  - Thêm dependency, framework, build step.
  - `fetch`, API, localStorage, lưu trữ bất kỳ.
  - Tự quyết bốn điểm CÒN MỞ bên dưới.
- Khi cần vượt phạm vi: dừng, ghi vào "Câu hỏi mở".

## Còn mở — không chốt hộ

1. Thứ tự 11 cột thật trong bảng tính: chưa đối chiếu.
2. Ai được xác nhận chứng từ và căn cứ gì: hoãn. Không vẽ nút xác nhận.
3. Tiền dư có dùng cho sổ khác của cùng khách không: mặc định là không.
4. Sổ "chưa mở" có tính là "chưa chốt" không: bộ lọc đang coi là không.

## Hoàn tác

Một file sửa, một file mới. Revert commit; không đụng dữ liệu.

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
