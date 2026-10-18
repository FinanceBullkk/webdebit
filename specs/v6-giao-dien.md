# Lớp 2 — giao diện sổ công nợ V6 nối vào model

Trạng thái: **ĐỀ XUẤT** (Claude, 18/10/2026). Mockup đã được người dùng duyệt trong chat ngày 18/10/2026; chưa triển khai. **Làm sau khi lớp 1 ([v6-model-tien.md](v6-model-tien.md)) đã merge.**

Lấy mockup đã duyệt, nối vào model lớp 1. Lớp 3 (backend thật) là spec riêng, chưa tới.

Nguồn: [quyết định V6](ux-v6-quyet-dinh-2026-10-18.md), mockup `cong-no-web-handoff/preview/mockups/ux-v6/` (A0, C1–C8), [brief](ux-brief-so-cong-no.md) §2, §4.

**Không mở đường ghi tiền.** Trang chạy hoàn toàn trong tab, dữ liệu giả, không API, không lưu gì.

## Người dùng và luồng (bước 1)

Người dùng trên 40 tuổi, quen sheet công nợ hiện tại. Không còn vai người chốt hay người duyệt (V6-1, V6-2).

| Việc | Thao tác | Mockup |
| --- | --- | --- |
| Thêm một lô chuyến | Màn Tổng → bấm tên khách → bấm dòng dán cuối bảng → Ctrl+V. **3 thao tác** | A0 → C1 → C7 |
| Ghi một khoản thu | Mở sổ → gõ 4 ô trong cột tiền → Lưu. Không mở màn khác | C1 → C2 |
| Xem khoản thu trừ vào tháng nào | Bấm `Phân bổ` trên khoản thu | C2 |
| Sửa số tháng đang làm (kể cả tháng trước trong ngày đệm) | Bấm vào ô, sửa | C1, C5 |
| Sửa số tháng đã khóa | Bung tháng → `＋ Ghi điều chỉnh` → chọn chuyến, lý do, số ± → Lưu | C3 → C4 |
| Xem ai sửa gì | `Lịch sử sửa` | C6 |

## Đầu ra

`cong-no-web-handoff/preview/so-cong-no-v6.html` + `so-cong-no-v6-ui.js`, mở trực tiếp trong trình duyệt. Mọi con số do model lớp 1 tính; mọi việc ở bảng trên đi được từ đầu đến cuối.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- **Mockup đã duyệt:** `cong-no-web-handoff/preview/mockups/ux-v6/*.html` — HTML tĩnh, **không được sửa**. Giữ bố cục, câu chữ, bề rộng cột, cỡ chữ và màu của mockup.
- **Model:** `so-cong-no-v6-model.js` (lớp 1). Chỉ gọi, không viết lại, không tự cộng tiền.
- **Khuôn tách tệp:** như cặp `so-cong-no-v5.html` / `so-cong-no-v5-ui.js` — trạng thái tách khỏi dựng DOM.
- **Dữ liệu giả:** sổ mẫu ở mục "Dữ liệu vào" của spec model; bốn sổ khác cho màn Tổng lấy từ A0 (KHACH_B, KHACH_C, KHACH_D, KHACH_E), số hiển thị vẫn phải đi qua model.
- **Bản thử V5** (`so-cong-no-v5*`) không sửa; V6 là trang mới.

## Hợp đồng giữa giao diện và model

1. **Giao diện không tự tính tiền.** Không `+`, `-`, `reduce` trên tiền trong mã giao diện. Mọi số trên màn đến từ `monthChain`, `allocate`, `monthTotals` hoặc `lineAmount`. Thiếu số nào thì dừng và hỏi.
2. Sửa ô trực tiếp chỉ được khi `isDirectEditable(monthKey, today)` là `true`; ngược lại ô hiện chỉ đọc và tháng mang nhãn `Đã khóa ⓘ`.
3. Dòng điều chỉnh đi qua `validateAdjustment`; nêu **đủ mọi lý do** một lần.
4. Mỗi lần thêm chuyến, sửa ô, ghi khoản thu, ghi điều chỉnh: dựng lại `book` rồi gọi lại model — không vá số cũ.
5. **Lịch sử sửa** (C6) là nhật ký trong bộ nhớ tab do giao diện ghi: ai · lúc nào · tháng · dòng · số cũ → số mới · lý do. Với điều chỉnh có làm đổi phân bổ, ghi cả phân bổ trước và sau (V6-3d). Nhật ký này là tiện ích bản thử, **không phải lưu vết thật** — lưu vết thật thuộc lớp 3.

   **Hai bản ghi mẫu lúc mở trang**, không hơn — để thấy bộ lọc người và cột việc khi chưa thao tác gì:

   | Lúc | Người | Việc | Nội dung |
   | --- | --- | --- | --- |
   | `12/04/2026 08:05` | Nguyễn Văn A | Dán lô | Tháng 04 · 4 dòng · DEMO-105, DEMO-106, DEMO-107, DEMO-103 |
   | `18/04/2026 09:30` | Nguyễn Văn A | Sửa ô | Tháng 04 · DEMO-107 · UNIT PRICE 22.000.000 → 20.000.000 |

   Hai bản ghi này **khớp trạng thái mở đầu** của sổ: bốn dòng đó có thật, đơn giá DEMO-107 đang là 20.000.000. **Không** gieo bản ghi khoản thu 120.000.000 hay điều chỉnh +5.000.000 như mockup C6 vẽ — sổ lúc mở là `Đã thu —`, `Còn phải thu 185.000.000`, gieo hai bản ghi đó là nhật ký nói sai trạng thái sổ. Mockup C6 tự mâu thuẫn ở chỗ này; hai việc đó do thao tác thật trong C2 và C4 sinh ra.
6. **Ngày hôm nay** lấy từ tham số `?today=YYYY-MM-DD`, mặc định `2026-05-03`. Không dùng đồng hồ máy cho quy tắc khóa.

   Mặc định này nằm trong ngày đệm của tháng 04 — tháng làm việc của sổ mẫu — nên bản thử mở ra là sửa được ngay: dán chuyến, sửa ô, ghi thu đều đi được. Tháng 03 vẫn đã khóa (`isDirectEditable("2026-03", "2026-05-03")` là `false`), đúng như C3. Trạng thái khóa tháng 04 kiểm bằng `?today=2026-05-06`. (Sửa 18/10/2026: mặc định cũ `2026-10-18` làm mọi trạng thái rơi vào tháng đã khóa.)
7. **Người đang dùng** cố định `Trần Thị B`; không có ô chọn vai.

## Hành vi và bất biến

- VND số nguyên; hiển thị dấu chấm phân nhóm; chuyển `BigInt` sang chuỗi, không qua `Number`.
- Ô chưa biết hiện `—`, không hiện `0`.
- **Một số dư duy nhất:** `Còn phải thu` = `endOfMonthVnd` của tháng; được âm, **hiện số âm trần, không kèm chữ** (V6-5).
- Số `Chuyển sang` nằm ở ô tiền bên phải, **không** ở cột TOTAL.
- Dán: tối đa 50 dòng, đúng 11 cột theo thứ tự sheet; giữ tab đầu/cuối; cột thành tiền dán vào chỉ để đối chiếu — lệch thì đánh `!` ở cột No. và nêu số trong chú thích, không sửa, không bỏ dòng.
- Số tiền khoản thu: kiểm định dạng **trước** khi gọi model; sai thì giữ nguyên nội dung đã gõ và hiện `Chỉ nhập số dương, ví dụ 120.000.000`.
- **Ký hiệu thay chữ:** `!` cam ở cột No. cho dòng cần kiểm; `ⓘ` cho thông tin. Chú thích hiện khi **rê chuột hoặc khi focus bằng bàn phím**; ô nhập sai hiện chú thích ngay khi đang focus. Có `aria-describedby`.
- Sau điều chỉnh, số cũ hiện gạch ngang cạnh số mới ở dòng TỔNG của tháng đó và ở thanh các tháng sau.
- Cỡ chữ ≥ 16px, vùng bấm ≥ 40px, tương phản ≥ 4.5:1, không cuộn ngang ở 1280px, không ô nào bị cắt chữ.
- Bàn phím đi hết luồng dán, luồng ghi thu và luồng điều chỉnh; phần tử đang focus thấy viền.
- Không đưa lên màn: từ kỹ thuật, mã quyết định, câu giải thích quy trình.

## Ảnh chụp giao diện

Viewport `1280×720`. Selector dưới đây là **hợp đồng**; đổi thì sửa luôn khối này và nói trong báo cáo.

```json
{
  "page": "cong-no-web-handoff/preview/so-cong-no-v6.html",
  "viewports": [[1280, 720]],
  "states": [
    {"name": "tong", "board": "A0", "note": "Man Tong thang 04, KHACH_MAU con phai thu 185 trieu", "steps": []},
    {"name": "mo-so", "board": "C1", "note": "So KHACH_MAU thang 04, con phai thu 185 trieu",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"}]},
    {"name": "thu-120-trieu", "board": "C2", "note": "Thu 120 trieu, phan bo 20/20/30/25/25, con phai thu 65 trieu",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]}, {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]}, {"fill": ["[data-pay=\"amount\"]", "120000000"]},
       {"click": "[data-action=\"pay-save\"]"}, {"click": "[data-action=\"allocation\"]"}]},
    {"name": "ghi-dieu-chinh", "board": "C3", "note": "Thang 03 da khoa, dang go dieu chinh +5 trieu",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"},
       {"click": "[data-action=\"expand-month\"][data-value=\"2026-03\"]"},
       {"click": "[data-action=\"open-adjust\"]"},
       {"select": ["[data-adj=\"line\"]", "DEMO-104"]},
       {"fill": ["[data-adj=\"reason\"]", "Thiếu phí áp tải chuyến DEMO-104"]},
       {"fill": ["[data-adj=\"amount\"]", "+5000000"]}]},
    {"name": "da-dieu-chinh", "board": "C4", "note": "Thang 03 con 100 trieu, thang 04 chuyen sang 100, con phai thu 190",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"},
       {"click": "[data-action=\"expand-month\"][data-value=\"2026-03\"]"},
       {"click": "[data-action=\"open-adjust\"]"},
       {"select": ["[data-adj=\"line\"]", "DEMO-104"]},
       {"fill": ["[data-adj=\"reason\"]", "Thiếu phí áp tải chuyến DEMO-104"]},
       {"fill": ["[data-adj=\"amount\"]", "+5000000"]},
       {"click": "[data-action=\"adjust-save\"]"}]},
    {"name": "ngay-dem", "board": "C5", "note": "today=2026-05-03 (mac dinh), thang 04 con sua thang duoc",
     "page": "cong-no-web-handoff/preview/so-cong-no-v6.html?today=2026-05-03",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"}]},
    {"name": "lich-su-sua", "board": "C6", "note": "Bon ban ghi: hai mau cua Nguyen Van A, hai do thao tac that sinh ra",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]}, {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]}, {"fill": ["[data-pay=\"amount\"]", "120000000"]},
       {"click": "[data-action=\"pay-save\"]"},
       {"click": "[data-action=\"expand-month\"][data-value=\"2026-03\"]"},
       {"click": "[data-action=\"open-adjust\"]"},
       {"select": ["[data-adj=\"line\"]", "DEMO-104"]},
       {"fill": ["[data-adj=\"reason\"]", "Thiếu phí áp tải chuyến DEMO-104"]},
       {"fill": ["[data-adj=\"amount\"]", "+5000000"]}, {"click": "[data-action=\"adjust-save\"]"},
       {"click": "[data-action=\"open-history\"]"}]},
    {"name": "dan-lech", "board": "C7", "note": "Dan 2 dong, DEMO-109 lech 89 trieu, con phai thu 207 trieu",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"},
       {"paste": ["[data-action=\"inline-paste\"]", "\tDEMO-108\tWH\t25/04/2026\tPHAN THIET\tSHEKOU\t\t\t\t12000000\t\n\tDEMO-109\tWH\t26/04/2026\tPHAN THIET\tSHEKOU\t\t\t\t10000000\t99000000"]},
       {"hover": "[data-warn=\"DEMO-109\"]"}]},
    {"name": "loi-so-tien", "board": "C8", "note": "Nhap -5000000: chan, giu noi dung, so du khong doi",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"},
       {"fill": ["[data-pay=\"date\"]", "20/04/2026"]}, {"fill": ["[data-pay=\"ref\"]", "UNC-0420"]},
       {"fill": ["[data-pay=\"amount\"]", "-5000000"]}, {"click": "[data-action=\"pay-save\"]"}]},
    {"name": "sua-gia-thang-khoa", "board": "C3", "note": "today=2026-05-06: o gia thang 04 chi doc, nhan Da khoa",
     "page": "cong-no-web-handoff/preview/so-cong-no-v6.html?today=2026-05-06",
     "steps": [{"click": "[data-action=\"open-book\"][data-value=\"KHACH_MAU\"]"}]}
  ]
}
```

## Tiêu chí nghiệm thu

- [ ] `npm run test:unit` xanh — model V6, model V5 và test cũ không gãy.
- [ ] Chụp đủ 10 trạng thái, không bước nào lỗi selector.
- [ ] Ảnh từng trạng thái khớp mockup tương ứng: bố cục, câu chữ, cột, màu.
- [ ] `tong`: KHACH_MAU `185.000.000`, KHACH_E `57.000.000`.
- [ ] `mo-so`: TỔNG `4 cont`, phát sinh `90.000.000`, `Còn phải thu 185.000.000`; dòng 4 có `!`.
- [ ] `thu-120-trieu`: phân bổ `20 / 20 / 30 / 25 / 25`; `Đã thu 120.000.000`, `Còn phải thu 65.000.000`.
- [ ] `da-dieu-chinh`: tháng 03 `Còn phải thu 100.000.000` kèm `95.000.000` gạch ngang; thanh tháng 04 `100.000.000` / `190.000.000` kèm số cũ gạch ngang.
- [ ] Sau `da-dieu-chinh` mà ghi thêm thu `120000000`: phân bổ `20 / 20 / 30 / 30 / 20`; Lịch sử sửa ghi phân bổ trước và sau.
- [ ] `lich-su-sua`: đúng bốn bản ghi, đủ bốn loại việc (Dán lô, Sửa ô, Ghi khoản thu, Điều chỉnh) và hai người; hai bản ghi mẫu đứng cuối, hai bản ghi mới đứng đầu. Bộ lọc tháng và bộ lọc người đều lọc đúng. Số sổ trên nền là trạng thái đã thu và đã điều chỉnh, **khác mockup C6** — ghi rõ khác biệt này trong báo cáo.
- [ ] Mở trang rồi mở ngay Lịch sử sửa mà không thao tác gì: đúng hai bản ghi mẫu, không có bản ghi khoản thu hay điều chỉnh.
- [ ] `ngay-dem`: tháng 04 sửa thẳng được, nhãn `Sửa được đến 05/05`; `sua-gia-thang-khoa` (`?today=2026-05-06`): ô giá tháng 04 chỉ đọc, nhãn `Đã khóa ⓘ`, dòng dán không bấm được.
- [ ] Ở `today` mặc định, tháng 04 sửa thẳng được và tháng 03 đã khóa — mọi trạng thái còn lại chụp ở mặc định đều thao tác được.
- [ ] `dan-lech`: phát sinh `112.000.000`, `Còn phải thu 207.000.000`, chú thích DEMO-109 nêu `99.000.000` / `10.000.000` / `89.000.000`.
- [ ] `loi-so-tien`: các ô giữ nguyên, câu lỗi hiện, số dư không đổi.
- [ ] Thu `200000000` thay cho 120: `Còn phải thu -15.000.000`, không kèm chữ.
- [ ] Không phát hiện đo được nào: chữ ≥ 16px, vùng bấm ≥ 40px, tương phản ≥ 4.5:1, không cuộn ngang, không ô bị cắt chữ, không lỗi JS.
- [ ] Tìm trong mã giao diện không còn phép cộng/trừ nào trên tiền.
- [ ] Người dùng tự đi hết các việc ở bảng luồng trên bản thử và xác nhận (không agent nào thay được).

## Phạm vi agent

- Agent: codex
- Mockup: ĐÃ DUYỆT `cong-no-web-handoff/preview/mockups/ux-v6/` · người dùng · 18/10/2026
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/preview/so-cong-no-v6.html` (mới)
  - `cong-no-web-handoff/preview/so-cong-no-v6-ui.js` (mới)
- Ngân sách diff: 900
- Lệnh kiểm:
  - `npm run test:unit`
- Cấm:
  - Sửa `so-cong-no-v6-model.js` — thiếu gì thì hỏi.
  - Sửa mockup trong `preview/mockups/`, bản thử V5 hay màn cũ trong `preview/`.
  - Tự tính tiền trong mã giao diện.
  - Đổi câu chữ, nhãn, cỡ chữ, bề rộng cột của mockup.
  - Thêm dependency, framework, build step.
  - `fetch`, API, localStorage, lưu trữ bất kỳ.
  - Tự quyết các điểm CÒN MỞ bên dưới.
- Khi cần vượt phạm vi: dừng, ghi vào "Câu hỏi mở".

## Còn mở — không chốt hộ

1. Nhãn tự đặt `CARRIER`, `PLUG FEE`, `ESCORT FEE`.
2. Dòng phí không có container trong sheet.
3. Ai được xem Lịch sử sửa.
4. Điều chỉnh giảm làm một tháng âm: model hiện ném lỗi; giao diện hiện lý do, không lưu.
5. Danh mục cách thu bốn giá trị đã đủ chưa.

## Hoàn tác

Hai file mới. Revert commit; không đụng dữ liệu.

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
