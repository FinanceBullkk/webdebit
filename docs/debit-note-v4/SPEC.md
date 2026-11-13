# Debit note HTH – đặc tả mẫu xuất PDF (bản 4.0, chốt 10/11/2026)

Tài liệu này dành cho người dựng mẫu xuất debit note trong WebDebit. Nguồn sự thật về **giao diện** là các file HTML trong `reference/`; nguồn sự thật về **quy tắc** (dữ liệu, sang trang, kiểm tra) là tài liệu này. Nếu hai nguồn mâu thuẫn, dừng lại và hỏi, đừng tự chọn.

## 1. Mục tiêu

- Thay mẫu debit note đang xuất bằng mẫu mới: **một trang A4 ngang**. Thứ tự từ trên xuống: đầu trang, BILL TO và DOCUMENT, bảng container, rồi PAYMENT INFORMATION và ACCOUNT STATUS ở cuối trang.
- Không còn khối Amount due và Charge summary riêng. **Số phải trả là ô Amount của dòng Total** (chữ navy).
- Công nợ (ACCOUNT STATUS) chỉ để tham khảo. Không cộng nợ cũ vào số phải trả.
- PDF xuất ra phải giống `reference/*.png` khi chạy với `data/*.json`.

## 2. Tài liệu kèm theo

| File | Dùng để |
| --- | --- |
| `reference/1-trang-14-container.html` / `.png` / `.pdf` | Mẫu chuẩn 1 trang, dữ liệu `data/sample-14.json` |
| `reference/30-container-trang-1.html`, `-trang-2.html`, `.png`, `30-container-2-trang.pdf` | Ví dụ sang trang, dữ liệu `data/sample-30.json` (chia 20 + 10) |
| `reference/8-container-an-cot-HC-fee.html` / `.png` / `.pdf` | Ví dụ ẩn cột phí có tổng bằng 0, dữ liệu `data/sample-8-an-cot.json` |
| `reference/guideline-v4.0.pdf` | Design guideline (font, màu, lưới) |
| `data/*.json` | Dữ liệu mẫu và kết quả mong đợi (`expected`) để viết test |

Các file HTML là trang tĩnh, mở thẳng bằng Chrome là xem được, và đã đặt khổ A4 ngang thật (297 × 210 mm). CSS trong đó là kết quả đã đo: hãy chuyển gần như nguyên văn sang template của WebDebit, đừng viết lại bằng cảm quan.

## 3. Khổ giấy và xuất PDF

- A4 ngang 297 × 210 mm, `@page { size: A4 landscape; margin: 0 }`. Bản thiết kế vẽ ở 1123 × 794 px (96 dpi). Khung trang trong HTML là `width: 297mm; height: 210mm`.
- Nên xuất bằng Chromium headless (Puppeteer/Playwright), vì mẫu là HTML/CSS. Đặt `printBackground: true` (không có thì mất thanh navy và nền tiêu đề bảng) và `preferCSSPageSize: true`. Margin 0.
- Font: `'Times New Roman', 'Liberation Serif', Tinos, SimSun, 'Songti SC', 'Noto Serif CJK SC', 'Noto Serif SC', serif`.
  - Máy chủ Linux không có Times New Roman/SimSun thì dùng Liberation Serif (cùng số đo với Times New Roman) và Noto Serif CJK SC. Toàn bộ số đo trong mẫu được đo bằng chính hai font này.
  - Tuyệt đối không để rơi về font sans. Sau khi xuất, kiểm tra bằng `pdffonts`: chỉ có font serif nói trên và font phải được nhúng (emb = yes).
- Chỉ dùng hai độ đậm 400 và 700. Chữ Trung luôn 400, không giãn chữ.
- Số dùng `font-variant-numeric: tabular-nums`.

## 4. Cấu trúc và nội dung

Bốn khối, mỗi khối trả lời một câu hỏi:

| Khối | Câu hỏi | Nội dung |
| --- | --- | --- |
| A · Identity | Ai gửi cho ai, chứng từ nào? | Đầu trang; BILL TO (trái) và DOCUMENT (phải) |
| B · Details | Tính tiền những gì, phải trả bao nhiêu? | Bảng container + dòng Total |
| C · Action | Trả vào đâu? | PAYMENT INFORMATION (nửa trái, cuối trang) |
| D · Reference | Công nợ thế nào? | ACCOUNT STATUS (nửa phải, cuối trang), "For reference only · 仅供参考" |

### 4.1 Nhãn cố định (song ngữ, tiếng Anh trước)

- Tiêu đề: `DEBIT NOTE` + `账单`.
- BILL TO `客户`: dòng 1 tên khách (đậm) + tên tiếng Trung (thường); dòng 2 tên pháp lý và địa chỉ. Dòng 3 `Attn 联系人` + người liên hệ **đã bỏ** (người dùng 12/11/2026): người liên hệ, nếu cần, nằm trong tên pháp lý và địa chỉ lấy từ Thông tin cty; các file trong `reference/` vẫn còn dòng này, không theo phần đó.
- DOCUMENT `单据信息` (từ 12/11/2026 sát lề phải, mép phải thẳng cột Amount và chữ DEBIT NOTE; nhãn và giá trị là hai cột rộng theo chữ, BILL TO lấy phần còn lại):
  - `Debit Note No. 账单号` (giá trị đậm)
  - `Issue Date 开单日期`
  - `Billing Period 账单期间`
  - `Currency 币种` (giá trị VND)
- PAYMENT INFORMATION `付款信息`:
  - `Beneficiary 收款人`
  - `Bank 开户银行`
  - `USD Account 美元账号` (giá trị đậm)
  - `SWIFT Code SWIFT代码`
  - `Payment Ref. 汇款附言` (= số debit note)
- ACCOUNT STATUS `账户情况` · `For reference only` `仅供参考`:
  - `Opening balance · 期初余额`
  - `This debit note · 本期账单`
  - `Payments received · 本期已收款`
  - `Outstanding balance · 未结余额` (dòng đậm)
- Dòng tổng: `Total, {n} containers · 合计`.
- Chân trang trái: `Debit Note {số} · Billing queries 账单查询: hth.logs@gmail.com`. Trang chưa phải trang cuối thì ghi `Debit Note {số} · Continued on next page · 续下页`. Chân trang phải: `Page {x} of {n}`.

### 4.2 Bảng container

| # | Cột | 中文 | Rộng | Căn | Hiện |
| --- | --- | --- | --- | --- | --- |
| 1 | No. | 序号 | 28px | phải | luôn |
| 2 | Container no. | 柜号 | 94px (lùi trái 10px) | trái | luôn |
| 3 | B/L no. | 提单号 | 106px | trái | luôn |
| 4 | Line | 船东 | 40px | trái | luôn |
| 5 | Shipper | 发货人 | **1fr** (cột co giãn) | trái | luôn |
| 6 | Loading date | 装柜日期 | 74px | trái | luôn |
| 7 | Loading place | 装柜地点 | 76px | trái | luôn |
| 8 | POD | 目的港 | 66px | trái | luôn |
| 9 | Lump-sum | 单价 | 78px | phải | luôn |
| 10 | Storage | 早装产生费用 | 76px | phải | khi tổng ≠ 0 |
| 11 | Generator / electricity fee | 发电机/电费 | 129px | phải | khi tổng ≠ 0 |
| 12 | Overstay | 押车 | 68px | phải | khi tổng ≠ 0 |
| 13 | HC fee | 卫生证 | 62px | phải | khi tổng ≠ 0 |
| 14 | Amount | 金额 | 84px | phải | luôn |

- Các cột số căn phải có `padding-left: 8px`. Mỗi hàng của bảng có `padding-right: 8px`.
- **Tự cân cột chữ (người dùng 12/11/2026)**: bề rộng px ở bảng trên chỉ là bản thiết kế. Khi xuất, Container no., Line, Loading date, Loading place, POD rộng theo chữ dài nhất của chứng từ (cả tiêu đề), đo thật bằng font của trang trước khi chia trang, cộng khoảng hở 12px bên phải mỗi cột chữ (kể cả Shipper); chỗ còn dư khi Shipper đã đủ một dòng chia đều cho các cột chữ (mỗi cột tối đa 48px), phần lẻ cho Shipper. Không đủ chỗ thì như trước: chữ nơi/cảng thu nhỏ (khi in tên tiếng Trung) và Shipper xuống dòng. Cột phí giữ bề rộng theo cấu hình.
- Thứ tự cột cố định, vì khách đối chiếu theo thứ tự này.
- Cột phí hiện hay ẩn tính theo **toàn bộ chứng từ**: mọi trang có cùng bộ cột. Ẩn cột nào thì cột Shipper rộng ra. Chứng từ xuất từ sổ (bản live) thì bảy cột Storage, Trucking, Generator / electricity fee, Overstay, HC fee, Cancellation fee, AMD fee **luôn hiện** kể cả tổng bằng 0 ([DEBIT-NOTE-04](../decisions/debit-note-04.md)); bảng trên chỉ còn đúng cho dữ liệu mẫu.
- Ô phí bằng 0 ghi `–` (gạch ngang ngắn, U+2013).
- Danh sách liền, không chia nhóm, không dòng cộng phụ. Xếp theo Loading date tăng dần, rồi B/L no., rồi Container no. Số thứ tự chạy liền qua các trang.
- Tiêu đề cột: nền `#E6EBF2`, chữ navy, tiếng Anh 700 (`white-space: nowrap`) ở trên, tiếng Trung 400 ở dưới. Hàng dữ liệu cao 25px (18 + 3 + 3 + kẻ 1px `#B8C0CB`); dòng cuối của mỗi trang không kẻ.
- Dòng Total chỉ có ở trang cuối, cộng **mọi** container của chứng từ. Kẻ đơn navy 1px ở trên, kẻ đôi navy 3px ở dưới, ô Amount chữ navy.
- ~~Các phí khác trong danh mục cũ (TRUCKING `拼柜`, CANCELLATION FEE `取消订柜费`, AMD FEE `改单费`) chưa có chỗ trong mẫu. Nếu dữ liệu thật có hơn 5 cột phí cần hiện, dừng lại hỏi. Đừng tự co chữ hay thu cột.~~ Thay bởi [DEBIT-NOTE-04](../decisions/debit-note-04.md) (13/11/2026): bảy cột luôn hiện; bảng không vừa thì lần lượt (1) cột phí hẹp theo số dài nhất, tiêu đề Anh tối đa hai dòng; (2) chữ cả bảng thu nhỏ đều, nhỏ nhất 80%; (3) tên Trung của nơi/cảng xuống dòng dưới tên Latin. Chứng từ ít cột vẫn in như bảng trên.

### 4.3 Định dạng

- Số tiền: VND, phẩy ngăn nghìn (`1,070,000,000`), không phần lẻ. Số trừ đặt trong ngoặc `(6,594,000,000)`; dấu ngoặc đóng treo ra ngoài cột (`margin-right: -0.333em`).
- Ngày: `04 Nov 2026`. Kỳ: `Nov 2026`.
- Trường chưa có dữ liệu ghi `[Tên trường]`, ví dụ `[Issue date]`, `[Tax ID]`, `[Contact]`.
- Bản gửi khách: chỉ tiếng Anh và tiếng Trung. Không tiếng Việt, không mã QR, không chữ ký, không dấu.
- Góc vuông, không bo tròn, không khung, không kẻ dọc. Màu nền duy nhất là `#E6EBF2` ở tiêu đề bảng; thanh navy 6px ở mép trên.

### 4.4 Màu

| Mã | Dùng cho |
| --- | --- |
| `#14304F` | Navy: tên công ty, tiêu đề, kẻ đầu trang, kẻ Total, ô Amount của Total, chữ tiêu đề bảng |
| `#1F2933` | Chữ chính |
| `#5F6B7A` | Nhãn, chú thích, chân trang, kẻ dòng Outstanding |
| `#B8C0CB` | Kẻ dòng, kẻ chân trang |
| `#E6EBF2` | Nền hàng tiêu đề bảng |

## 5. Khoảng trống dọc (giữ đúng như mẫu)

- Khung trang là flex dọc: thanh navy 6px, đầu trang (padding trên 24px), các khối, chân trang (padding dưới 24px). Lề trái/phải 40px.
- Giữa các khối là spacer `flex: 1 1 0; min-height: 10px; max-height: 20px`. Riêng spacer giữa bảng và khối PAYMENT | ACCOUNT STATUS không có max, nên phần dư dồn vào đó và khối thanh toán luôn nằm cuối trang.
- Các `margin` âm có sẵn trong mẫu là hằng số đo theo font, dùng để trừ phần đệm dòng, nhờ vậy khoảng trống nhìn thấy bằng nhau:
  - đầu trang `margin-bottom: -4.29px`;
  - khối BILL TO | DOCUMENT và khối PAYMENT | ACCOUNT STATUS `margin-top: -5.43px; margin-bottom: -4.95px`.

  Giữ nguyên, đừng "dọn" đi.

## 6. Sang trang

Bốn loại trang:

| Loại | Gồm |
| --- | --- |
| Đơn (`single`) | Đầu trang đầy đủ, BILL TO và DOCUMENT, cả bảng, Total, PAYMENT và ACCOUNT STATUS |
| Đầu (`first`) | Đầu trang đầy đủ, BILL TO và DOCUMENT, phần đầu bảng (không Total) |
| Giữa (`middle`) | Đầu trang rút gọn, tiếp bảng (lặp lại tiêu đề cột) |
| Cuối (`last`) | Đầu trang rút gọn, phần còn lại của bảng, Total, PAYMENT và ACCOUNT STATUS |

Đầu trang rút gọn: dòng 1 giống đầu trang đầy đủ; dòng 2 thay địa chỉ bằng `Debit Note No. 账单号 {số} · Bill to 客户 {tên khách} · Billing Period 账单期间 {kỳ} · Currency 币种 VND`.

Thuật toán: ngắt trang theo **chiều cao đo thật** trong trình duyệt, không theo số dòng cố định, vì tên dài xuống dòng sẽ làm dòng cao hơn.

```
fits(kind, rows) = dựng trang loại kind với các dòng rows, đo, chiều cao nội dung <= chiều cao trang
if fits('single', all): một trang
else:
  pages = []; i = 0; kind = 'first'
  loop:
    rest = all[i:]
    if kind != 'first' and fits('last', rest): pages += ('last', rest); break
    cand = rest[: max(len(rest) - 3, 1)]          # chừa ít nhất 3 dòng đi cùng Total
    k = số dòng lớn nhất của cand vừa trang kind    # tìm nhị phân
    pages += (kind, rest[:k]); i += k; kind = 'middle'
```

Kết quả mong đợi với dữ liệu mẫu (dòng một hàng chữ):

| Số container | Chia trang |
| --- | --- |
| 1–16 | 1 trang |
| 17 | 14 + 3 |
| 30 | 20 + 10 |
| 60 | 20 + 23 + 17 |

Với tên và địa chỉ khách dài (xem `LONG` ở mục 9), một trang chỉ chứa 15 container (16 từ khi bỏ dòng Attn, 12/11/2026).

## 7. Sáu phép kiểm tra tự động (chặn xuất nếu sai)

Chạy trước khi dựng PDF. Phép nào sai thì không xuất, báo lỗi nêu rõ phép và các con số.

1. Mỗi dòng: Amount = Lump-sum + Storage + Generator + Overstay + HC fee (+ các phí khác nếu có).
2. Total Amount = tổng Amount của mọi dòng.
3. Tổng các cột phí = Total Amount.
4. Số dòng container = n trong `Total, n containers`.
5. `This debit note` ở ACCOUNT STATUS = Total Amount.
6. Opening balance + This debit note − Payments received = Outstanding balance.

## 8. Đang chờ team: không tự điền, không tự đổi

- Người thụ hưởng là công ty đang ghi trên mẫu (khác HTH) hay HTH.
- Tài khoản ghi `USD Account` trong khi số tiền là VND.
- Các ô đang để `[...]`: Issue date, Tax ID, Phone, tên pháp lý và địa chỉ khách, người liên hệ.
- Địa chỉ HTH (có thể đã đổi đơn vị hành chính sau 01/07/2025).
- Tên phí tiếng Trung (`单价`, `早装产生费用`, `拼柜` có thể đổi thành `包干价`, `堆存费`, `拖车费`). Giữ tên hiện tại.
- Chưa đưa vào mẫu: hạn thanh toán (Due date), số tiền bằng chữ, câu về VAT.

Đưa thông tin công ty, thông tin ngân hàng và nhãn phí (Anh/Trung) vào **cấu hình**, không viết cứng trong template, để team sửa được mà không cần sửa code.

## 9. Kiểm thử và nghiệm thu

- `data/sample-14.json` cho ra 1 trang, giống `reference/1-trang-14-container.png`. Total 1,070,000,000; Outstanding 19,882,128,759.
- `data/sample-30.json` cho ra 2 trang (20 + 10), giống hai ảnh `30-container-trang-*.png`; trang 1 có "Continued on next page".
- `data/sample-8-an-cot.json`: cột HC fee bị ẩn, Shipper rộng ra, giống `8-container-an-cot-HC-fee.png`.
- Chia trang đúng bảng ở mục 6 cho 16, 17, 30, 60 container (nhân dữ liệu mẫu lên).
- Dữ liệu dài (`LONG`): tên khách `FANYA INTERNATIONAL LOGISTICS (SHENZHEN) CO., LTD 泛亚国际物流（深圳）有限公司`; địa chỉ `Room 1203, Block B, Galaxy Century Building, No. 3069 Caitian Road, Futian District, Shenzhen, Guangdong, China`. Vẫn vừa trang, 15 container một trang (16 từ khi bỏ dòng Attn, 12/11/2026).
- Mỗi trang PDF đúng A4 ngang (≈ 841.9 × 595.3 pt), không có trang trắng thừa, font được nhúng, không có font sans.
- Cả 6 phép kiểm tra chạy và chặn được một ca cố tình sai (ví dụ sửa Amount một dòng).
- Mọi số tiền trong một cột thẳng mép phải; số tiền ở ACCOUNT STATUS thẳng mép với cột Amount của bảng.

## 10. Ngoài phạm vi

- Không đổi cấu trúc Google Sheet nguồn ("Bộ lập bill", các tab như BOOKING_DATA, CONT_BO). Đổi gì ở nguồn dữ liệu phải bàn với team trước.
- Không đổi các chứng từ khác ngoài debit note.
- Giữ mẫu cũ chạy được (bật/tắt bằng cấu hình) cho tới khi team duyệt mẫu mới trên dữ liệu thật.
