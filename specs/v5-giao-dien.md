# Lớp 2 — giao diện sổ công nợ V5 nối vào model

Trạng thái: **ĐỀ XUẤT** (Claude, 17/10/2026).

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

**Model đã có, chỉ gọi, không viết lại:** `cong-no-web-handoff/preview/so-cong-no-v5-model.js` xuất năm hàm — `lineAmount`, `monthTotals`, `allocateReceipt`, `ledgerBalance`, `canClose`. Chữ ký và hành vi mô tả tại [v5-model-tien.md](v5-model-tien.md). Tiền là `BigInt`; chuỗi chữ số vào, `BigInt` ra.

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

## Phạm vi agent

- Agent: gemini
- Mockup: ĐÃ DUYỆT `cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html` · phiên bản "commit a7ea67b" · người dùng · 17/10/2026
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/preview/so-cong-no-v5.html`
  - `cong-no-web-handoff/preview/so-cong-no-v5-ui.js`
- Ngân sách diff: 900
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
