# V7 — sổ khách một bảng, cuộn liên tục theo lối Sheet

Trạng thái: **ĐỀ XUẤT** (Claude, 19/10/2026). Bố cục đã được **người dùng chốt trong chat ngày 19/10/2026** sau khi xem bản thử chạy trên dữ liệu thật; mã chưa vào repo. Dữ liệu mẫu ẩn danh đã có: `cong-no-web-handoff/preview/so-khach-v7-fixture.js`.

V7 **thay màn sổ khách của V6**, không thay model tiền. Nguồn bố cục: tab `Sổ khách` của Sheet đang dùng (đọc 19/10/2026). Nguồn luật tiền: [business-rules](../docs/business-rules.md), quyết định V6 (`ux-v6-quyet-dinh-2026-10-18.md`, hồ sơ nhánh nguồn, chưa nhập), lớp 1 V6 (`v6-model-tien.md`, hồ sơ nhánh nguồn, chưa nhập).

**Không mở đường ghi tiền.** Trang chạy hoàn toàn trong tab, fixture ẩn danh, không API, không lưu gì.

## Vì sao đổi bố cục

So bản V6 (`so-cong-no-v6.html`) với tab `Sổ khách` ngày 19/10/2026, bốn điểm lệch có hậu quả thật:

1. **Mất hai con số người dùng kiểm hằng ngày.** Sheet luôn hiện *Tổng còn nợ (mọi tháng)* và *Chờ xử lý* ở đầu sổ; V6 chỉ có chúng ở màn Tổng, vào sổ một khách là mất.
2. **Dòng phí lẻ bị loại khỏi tiền.** Sheet có dòng không container, không đơn giá, chỉ phụ phí, **vẫn cộng vào phát sinh tháng**. `lineAmount` của V6 trả `null` khi thiếu đơn giá nên dòng này rơi vào nhóm "chưa có giá" và không được cộng. Đây là điểm CÒN MỞ số 2 của v6-giao-dien.md (`v6-giao-dien.md`, hồ sơ nhánh nguồn, chưa nhập), nay chốt.
3. **Dán từ Sheet hỏng ở dấu phân nhóm.** Sheet hiện `46,000,000` (dấu phẩy); `fromText` của V6 chỉ nhận dấu chấm.
4. **Không thấy khoản thu rơi vào tháng nào.** Một khách thật có ~11 tháng, tháng lớn 37–43 chuyến; màn một-tháng-một-khối giấu mất việc "thu mới trừ nợ cũ trước" đang trừ vào đâu.

Bố cục cuộn liên tục của Sheet giải quyết cả bốn, và người dùng đã quen mắt với nó.

## Người dùng và luồng (bước 1)

Người dùng trên 40 tuổi, đang làm trên chính tab `Sổ khách`. Không có bước chốt tháng, không tách người nhập/người duyệt (V6-1, V6-2).

| Việc | Thao tác | Số thao tác |
| --- | --- | --- |
| Xem khách còn nợ bao nhiêu, còn việc gì | Mở sổ — đầu sổ dính, luôn thấy | **0** |
| Nhảy tới một tháng | Bấm tháng ở dải phải | **1** |
| Thêm một lô chuyến | Bấm ô dán cuối tháng đang mở → Ctrl+V | **2** |
| Sửa giá tháng đang mở | Bấm ô → gõ → Enter | **2** |
| Sửa số tháng đã khóa | Bấm ô → gõ **số đúng** → Enter → gõ lý do | **3**, không cần biết "dòng điều chỉnh" là gì |
| Ghi một khoản thu | Bấm ô ngày trong khối tiền → gõ ngày → gõ số → Enter | **3** |
| Xem khoản thu trừ vào tháng nào | Không thao tác — dòng thu hiện ngay ở tháng được trừ, kèm một dòng báo | **0** |
| Hủy một phiếu thu ghi sai | Bấm vào phiếu → gõ lý do → `Hủy phiếu` | **3** |

## Đầu ra

- `cong-no-web-handoff/preview/so-khach-v7.html` (mới)
- `cong-no-web-handoff/preview/so-khach-v7-ui.js` (mới)
- `cong-no-web-handoff/preview/so-khach-v7-model.js` (mới, lớp tiền thuần, `module.exports`)
- `cong-no-web-handoff/preview/test-so-khach-v7-model.js` (mới, `node --test`, thêm vào `npm run test:unit`)
- `cong-no-web-handoff/preview/so-khach-v7-fixture.js` — **đã có trong commit này**

## Đối chiếu dữ liệu và code hiện có (bước 2)

- **Model V6** (`so-cong-no-v6-model.js`): `monthChain`, `allocate`, `isDirectEditable`, `validateAdjustment` dùng lại được **nguyên ý**. V7 **không sửa file này** — V6 còn chạy trên nó. Hai điểm V6 làm khác V7 nên viết trong model V7 mới, không vá vào V6:
  - `tripAmount` phải trả số khi **có phụ phí mà không có đơn giá** (dòng phí lẻ). `lineAmount` của V6 trả `null`.
  - Khoản thu có `voided` khác `null` bị loại khỏi mọi phép cộng.
- **Không sửa** `so-cong-no-v5*`, `so-cong-no-v6*`, mockup trong `preview/mockups/`.
- **Fixture**: `so-khach-v7-fixture.js`, sinh bằng script tất định, **không có một ký tự nào từ sổ thật**. Giữ hình dạng: 11 tháng, 250 dòng chuyến (tháng lớn nhất 43), một dòng phí lẻ, một phiếu trải hai tháng.

## Bố cục màn (đã chốt)

Một bảng duy nhất, một khách, cuộn liên tục từ tháng cũ nhất tới tháng đang mở.

**Bốn tầng dính, theo đúng thứ tự này** — đây là thứ Sheet không làm được và là lý do chính để lên web:

| Tầng | `top` | Nội dung |
| --- | --- | --- |
| Đầu sổ | `0` | Khách · Từ tháng · **Chờ xử lý** · **Tổng còn nợ (mọi tháng)** |
| Băng nhóm cột | `70px` | `CHUYẾN HÀNG · ô cam: chưa có giá, chưa tính vào nợ` \| `TIỀN KHÁCH TRẢ` \| `NỢ` \| `NGUỒN` |
| Header cột | `100px` | 14 cột dưới đây |
| Dòng `THÁNG x/yyyy` | `138px` | kèm nhãn khóa và *Nợ các tháng trước* |

**Cột, theo đúng thứ tự và tên tiếng Việt của Sheet** (bề rộng ở 1920):

`STT 52` · `Số container 148` · `Hãng tàu / số xe 104` · `Ngày chuyến 104` · `Nơi đi 118` · `Nơi đến 118` · `Đơn giá 128` · `Phụ phí 116` · `Thành tiền 148` ‖ `Ngày trả 112` · `Hình thức 112` · `Số tiền trả 150` ‖ `Còn nợ cộng dồn 158` · `Vết 96`. Tổng 1.700px.

- **Phụ phí là một cột**, không tách `OTHER / PLUG / ESCORT FEE` như V6.
- **Nhãn tiếng Việt**, không dùng `CONTAINER NO`, `UNIT PRICE`, `TOTAL (VND)`.
- Cột `Vết` giữ `CH:` / `TC:` / `SD:` như Sheet.
- **Dưới 1600px** (màn 1920 ở Windows 150% = 1280 CSS): ẩn cột `Vết`, bóp các cột còn lại xuống tổng **1.258px** — vẫn **không cuộn ngang**. Dải tháng bên phải ẩn theo.
- **Dải "DANH SÁCH THÁNG"** bên phải (150px, dính): mỗi tháng một dòng kèm nợ còn lại, bấm là nhảy tới tháng.

**Khối `TIỀN KHÁCH TRẢ` phải tách bạch về thị giác.** Trong Sheet, khoản thu nằm cùng hàng với một chuyến hoàn toàn không liên quan, rất dễ đọc nhầm thành "chuyến này đã trả". Giữ bố cục cột nhưng: nền riêng (`#f2f8ff`), viền trái đậm ở cột `Ngày trả`, và **không đánh số theo STT chuyến**.

**Mỗi tháng** có: dòng `THÁNG x/yyyy` → các dòng chuyến (xen dòng điều chỉnh nếu có) → dòng hỏi lý do hủy (khi đang hủy) → dòng vết phiếu đã hủy → ô dán (chỉ tháng đang mở) → dòng `Cộng tháng x/yyyy (n chuyến)` → một dòng trống.

## Quy tắc tiền (hợp đồng giữa giao diện và model)

1. **Giao diện không tự tính tiền.** Không `+`, `-`, `reduce` trên tiền trong `so-khach-v7-ui.js`. Mọi số đến từ `so-khach-v7-model.js`. VND là `BigInt`, vào từ chuỗi chữ số đã kiểm regex; hiển thị dấu **chấm** phân nhóm.
2. **Ô nhập nhận cả ba kiểu**: `46,000,000` (như Sheet hiện), `46.000.000` (như người Việt gõ) và `46000000`. Áp cho cả ô sửa, ô ghi thu và ô dán.
3. **Dòng phí lẻ**: không container, không đơn giá, có phụ phí → `Đơn giá` hiện `–`, `Thành tiền` bằng phụ phí, **vẫn cộng vào phát sinh tháng**, **không** tính là "chưa có giá".
4. **Chưa có đơn giá** → ô cam, chữ `chưa có giá`, không cộng vào phát sinh, và cộng vào đếm *Chờ xử lý* ở đầu sổ.
5. **Tháng đang mở** (`openMonth`, mặc định tháng của `today`): sửa đè thẳng vào ô. **ĐÃ CHỐT (người dùng, 19/10/2026): khóa tháng theo V6** — tháng trước vẫn sửa đè trực tiếp được đến hết ngày 5 của tháng sau (so theo `today`); từ ngày 6 là tháng khóa (điều 6). Dòng `THÁNG` của tháng trước còn trong đệm mang nhãn `Sửa đến hết 05/MM/YYYY`. Ô dán và ô ghi thu trống vẫn chỉ ở tháng của `today`. **THAY THẾ (người dùng, 19/10/2026): bỏ quy tắc ngày 5, dùng nút ổ khóa từng tháng** — mỗi tháng có một nút ổ khóa trên dòng `THÁNG`, ai cũng bấm được để mở/khóa lại. Mặc định lúc mở trang chỉ tháng của `today` mở, các tháng khác khóa. Mở/khóa **không** ghi vào Lịch sử. Ô dán lô có ở mọi tháng đang mở; ô ghi thu trống chỉ ở tháng của `today`.
6. **Tháng đã khóa**: ô **vẫn bấm được và vẫn gõ số mới được**, nhưng hệ thống **không sửa đè**. Nó lấy hiệu số rồi sinh một **dòng điều chỉnh** ngay dưới dòng chuyến, giữ nguyên giá gốc. Dòng điều chỉnh **chưa có lý do thì chưa tính vào tiền**, hiện chữ `chưa tính` màu đỏ, và cộng vào đếm *Chờ xử lý*. Nhập lý do xong tiền mới chạy. **ĐÃ CHỐT (người dùng, 19/10/2026): một chuyến được có nhiều dòng điều chỉnh** — mỗi lần gõ sinh một dòng mới với lý do riêng, không đè lên dòng đã có lý do. Hiệu số của dòng mới tính từ **giá hiện hành** (giá gốc cộng các điều chỉnh đã có lý do của chuyến đó), không từ giá gốc, để hai lần điều chỉnh không cộng trùng; dòng chưa có lý do không vào gốc tính. Mỗi chuyến chỉ giữ một dòng chờ lý do: gõ lại khi còn dòng chờ thì thay dòng chờ đó (hệ quả kỹ thuật, tránh cộng trùng). **THAY ĐỔI (người dùng, 19/10/2026): điều chỉnh KHÔNG cần lý do** — mọi câu trên về "chưa có lý do thì chưa tính", `chưa tính` và đếm "điều chỉnh chờ lý do" không còn hiệu lực: gõ số mới ở tháng khóa sinh dòng điều chỉnh **tính tiền ngay** và để lại lịch sử; ô ghi chú là tùy chọn. Hủy phiếu vẫn bắt buộc lý do.
7. **Ghi khoản thu**: gõ thẳng vào ba ô trống của khối `TIỀN KHÁCH TRẢ` (ngày trả · hình thức · số tiền). Lưu xong, tiền **trừ nợ cũ trước**: rải từ tháng còn nợ cũ nhất, mỗi tháng một dòng, phần dư thành `ỨNG TRƯỚC` ở tháng cuối. Hiện một dòng báo nêu rõ phiếu đã trừ vào tháng nào bao nhiêu.
8. **Hủy khoản thu**: không sửa đè, không xóa dòng. Bấm vào phiếu → **bắt buộc có lý do** → hủy **cả phiếu** (mọi dòng cùng `pid`, kể cả khi phiếu trải nhiều tháng). Dòng cũ ở nguyên chỗ, ngày và số tiền gạch ngang, cột `Hình thức` thành nhãn `ĐÃ HỦY`, và cuối khối tháng có một dòng vết: số tiền · ngày phiếu · ngày hủy · lý do. Ghi lại phiếu mới bằng chính ô trống đó.
9. **Hủy phiếu không phân bổ lại các phiếu khác.** Nợ trả về đúng (các) tháng phiếu đó đã trừ; không đẩy phiếu sau lùi về trả thay. Phân bổ lại lịch sử là việc [business-rules](../docs/business-rules.md) cấm. **Điều chỉnh thì phân bổ lại — ĐÃ CHỐT (người dùng, 19/10/2026, phương án A, theo V6-3d):** khi một điều chỉnh bắt đầu tính tiền, các phiếu chưa hủy được rải lại theo nợ cũ trước (xếp theo ngày phiếu rồi mã phiếu); phiếu đã hủy giữ nguyên; hủy phiếu vẫn không kích hoạt phân bổ lại. Dòng báo nêu các phiếu đổi tháng.
10. **Ngày hôm nay** lấy từ `?today=YYYY-MM-DD`, mặc định `2026-10-19` (khớp fixture). Không dùng đồng hồ máy cho quy tắc khóa.
11. **Điều chỉnh cả tháng — ĐÃ CHỐT (người dùng, 19/10/2026):** nút `+ Điều chỉnh cả tháng` ở dòng `Cộng tháng` (mọi tháng) mở một dòng nhập ở cuối các chuyến: số có dấu (nhận ba kiểu số), ghi chú tùy chọn. Số hiện ở cột `Thành tiền`, không nằm trong khối TIỀN KHÁCH TRẢ. Tính tiền ngay, cho phép tháng âm, chạy phân bổ lại thu. Dòng đã ghi không có nút sửa/xóa; sai thì thêm dòng ngược dấu.
12. **Ngăn Lịch sử — ĐÃ CHỐT (người dùng, 19/10/2026):** nút `Lịch sử` ở đầu sổ mở một ngăn riêng, mới nhất trên cùng; mỗi mục có thời điểm, người, loại thao tác, trước → sau, ghi chú/lý do. Ghi: sửa đè giá, điều chỉnh (theo chuyến và cả tháng), dán lô, ghi thu, hủy phiếu, sửa ngày/hình thức phiếu, phân bổ lại. Không ghi mở/khóa. Người thao tác hiện là nhãn cố định vì chưa có danh tính (xem spec backend).

## Dữ liệu mẫu ẩn danh

`so-khach-v7-fixture.js` — khách `KHACH_MAU_A`, `today` `2026-10-19`, `openMonth` `2026-10`. Container `MAUU10000xx`, hãng tàu `HTA…HTK`, nơi đi `KHO TINH A/B/C`, nơi đến `CANG BAC 1`…`CANG NAM 6`. Bề rộng chuỗi giữ tương đương sổ thật để thử bề rộng cột.

| Tháng | Chuyến | Phát sinh | Đã thu | Còn nợ cộng dồn |
| --- | ---: | ---: | ---: | ---: |
| 12.2025 | 1 | 441.500.000 | 441.500.000 | – |
| 01.2026 | 18 | 913.900.000 | 913.900.000 | – |
| 02.2026 | 17 | 826.600.000 | 826.600.000 | – |
| 03.2026 | 37 | 1.779.900.000 | 1.779.900.000 | – |
| 04.2026 | 43 | 2.275.800.000 | 2.275.800.000 | – |
| 05.2026 | 31 | 1.625.800.000 | 1.625.800.000 | – |
| 06.2026 | 26 + 1 phí lẻ | 1.381.510.000 | 1.381.510.000 | – |
| 07.2026 | 18 | 946.500.000 | 946.500.000 | – |
| 08.2026 | 30 | 1.521.500.000 | 562.955.000 | 958.545.000 |
| 09.2026 | 25 | 1.332.100.000 | – | 2.290.645.000 |
| 10.2026 | 3 | 121.000.000 | – | **2.411.645.000** |

Fixture cố ý chứa: **dòng nợ cũ chuyển sang sổ mới** (12.2025, không container), **một dòng phí lẻ** 1.310.000 ở 06.2026 (nên tháng này 27 dòng mà *Cộng tháng* ghi 26 chuyến), **một phiếu `PH-101` trải hai tháng** (524.974.000 ở 06.2026 + 75.720.000 ở 07.2026) để thử hủy cả phiếu, và **ba tháng cuối còn nợ** để cột cộng dồn có số.

## Tiêu chí nghiệm thu

- [ ] Mở trang: đầu sổ hiện `Tổng còn nợ (mọi tháng)` **2.411.645.000** và `Chờ xử lý` `0 chuyến chưa có giá · 0 khoản thu chưa chắc`.
- [ ] 11 dòng `Cộng tháng` khớp đúng bảng trên, cả cột `Còn nợ cộng dồn` (`–` khi hết nợ).
- [ ] Dòng phí lẻ 06.2026: `Đơn giá` là `–`, `Thành tiền` 1.310.000, *Cộng tháng* 06.2026 bằng **1.381.510.000** và **không** có cảnh báo thiếu giá.
- [ ] Xóa đơn giá một chuyến tháng 10: ô thành cam `chưa có giá`, đầu sổ đếm `1 chuyến chưa có giá`, tổng nợ giảm đúng bằng chuyến đó.
- [ ] Gõ số mới vào một ô giá tháng 03: **ô gốc không đổi**, sinh dòng điều chỉnh `chưa tính`, tổng nợ **không đổi**, đầu sổ đếm `1 điều chỉnh chờ lý do`. Nhập lý do → tiền chạy đúng bằng hiệu số. **[THAY BỞI 19/10/2026: nay điều chỉnh tính tiền ngay, không còn `chưa tính` hay đếm chờ lý do; tổng nợ đổi đúng bằng hiệu số.]**
- [ ] Ghi thu 1.000.000.000 ở tháng 09: trừ hết nợ 08.2026 trước rồi mới tới 09.2026; dòng báo nêu đúng hai số; tổng nợ giảm đúng 1.000.000.000.
- [ ] Ghi thu lớn hơn tổng nợ: phần dư thành dòng `ỨNG TRƯỚC`, tổng nợ âm, không kèm chữ giải thích thừa.
- [ ] Hủy phiếu `PH-101`: dải hỏi lý do nêu **600.694.000**; bỏ trống lý do thì không hủy được; hủy xong nợ trả lại **cả hai** tháng 06 và 07, hai dòng cũ gạch ngang mang nhãn `ĐÃ HỦY`, hai dòng vết hiện lý do.
- [ ] Ghi lại phiếu mới sau khi hủy: tổng nợ về đúng số trước khi hủy.
- [ ] Dán 7 cột từ Sheet với số kiểu `46,000,000`: vào đúng, không báo lỗi định dạng.
- [ ] 1920×1080: không cuộn ngang, dải tháng hiện. 1280×720: cột `Vết` ẩn, vẫn **không cuộn ngang**.
- [ ] Cuộn giữa sổ: đầu sổ, băng nhóm, header cột và dòng `THÁNG x` đều còn dính, không chồng nhau.
- [ ] Không phát hiện đo được nào: chữ ≥ 13px ở ô số, vùng bấm ≥ 28px, tương phản ≥ 4.5:1, không ô bị cắt chữ, không lỗi JS.
- [ ] Tìm trong `so-khach-v7-ui.js` không còn phép cộng/trừ nào trên tiền.
- [ ] Người dùng tự đi hết các việc ở bảng luồng và xác nhận (không agent nào thay được).

## Bằng chứng đã có

Bản thử cục bộ ngày 19/10/2026 (ngoài repo, chạy trên **dữ liệu thật** nên không đưa vào version control) đã dựng đủ bố cục trên và chứng minh:

- 11 dòng `Cộng tháng` và cột cộng dồn **khớp từng đồng** với tab `Sổ khách`, gồm cả dòng phí lẻ.
- Ghi thu tách tháng, hủy cả phiếu nhiều tháng, ghi lại phiếu mới: tổng nợ về đúng số ban đầu.
- Gõ số mới ở tháng khóa sinh dòng điều chỉnh, giá gốc không đổi, tiền chỉ chạy sau khi có lý do.
- 284 dòng DOM, vẽ xong ~50ms; 1.700px ở 1920, 1.258px ở 1280.

Đây là bằng chứng **bản thử**, không phải bằng chứng của mã trong repo. Mã trong repo phải tự chứng minh lại bằng các tiêu chí ở trên.

## Phạm vi agent

- Agent: codex
- Bố cục: **ĐÃ CHỐT** · người dùng · 19/10/2026
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/preview/so-khach-v7.html` (mới)
  - `cong-no-web-handoff/preview/so-khach-v7-ui.js` (mới)
  - `cong-no-web-handoff/preview/so-khach-v7-model.js` (mới)
  - `cong-no-web-handoff/preview/test-so-khach-v7-model.js` (mới)
  - `package.json` — chỉ thêm test mới vào `test:unit`
- Ngân sách diff: 1200 ban đầu; **nới theo phạm vi người dùng thêm ngày 19/10/2026** (khóa tháng V6, phân bổ lại, sửa ngày/hình thức phiếu, điều chỉnh không lý do; sắp tới: ngăn Lịch sử, nút ổ khóa, điều chỉnh cả tháng). Thực tế bốn file V7 mới ~980 dòng.
- Lệnh kiểm:
  - `npm run test:unit`
- Cấm:
  - Sửa `so-cong-no-v5*`, `so-cong-no-v6*`, mockup trong `preview/mockups/`.
  - Sửa `so-khach-v7-fixture.js` — thiếu gì thì hỏi.
  - Tự tính tiền trong mã giao diện.
  - Thêm dependency, framework, build step.
  - `fetch`, API, localStorage, lưu trữ bất kỳ.
  - Tự quyết các điểm CÒN MỞ bên dưới.
- Khi cần vượt phạm vi: dừng, ghi vào "Câu hỏi mở".

## Còn mở — không chốt hộ

1. **Sửa ngày hoặc hình thức của một phiếu đã lưu**: hiện phải hủy rồi ghi lại. Có cho sửa tại chỗ hai trường không-phải-tiền này không? **ĐÃ CHỐT (người dùng, 19/10/2026): cho sửa tại chỗ** ngày và hình thức của phiếu đã lưu (không sửa số tiền). CHƯA TRIỂN KHAI; cần vết trước → sau.
2. **Điều chỉnh cả tháng, không gắn chuyến** (V6 có): V7 chưa có lối vào. Đặt ở đâu — dòng `Cộng tháng`? **ĐÃ CHỐT (19/10/2026): xem điều 11.**
3. **Lịch sử sửa** (ai · lúc nào · trước → sau): V7 mới ghi ngày trong nhãn dòng. Để riêng một ngăn như V6, hay in thẳng vào sổ? **ĐÃ CHỐT (19/10/2026): ngăn riêng, xem điều 12.**
4. **Nhiều khách**: V7 là màn một khách. Màn Tổng của V6 giữ nguyên hay cũng đổi theo? **ĐÃ CHỐT (người dùng, 19/10/2026): V7 là màn một khách.** Màn Tổng của V6 chưa có quyết định.
5. **Điều chỉnh giảm làm một tháng âm**: xử lý thế nào, chặn hay cho âm? **ĐÃ CHỐT (người dùng, 19/10/2026): cho phép âm.**
6. Danh mục hình thức thu bốn giá trị (`THU TIỀN`, `CẤN TRỪ`, `ỨNG TRƯỚC`, `KHÁC`) đã đủ chưa. **ĐÃ CHỐT (người dùng, 19/10/2026): đủ bốn giá trị.**

## Hoàn tác

Bốn file mới cộng fixture. Revert commit; không đụng dữ liệu, không đụng V5/V6.

## Câu hỏi mở

- Gói 3 giả định ô dán nhận TSV 7 cột theo thứ tự: Số container · Hãng tàu / số xe · Ngày chuyến · Nơi đi · Nơi đến · Đơn giá · Phụ phí. Ô giá/phụ phí trống giữ `null`.

- Phân bổ lại cũng chạy khi sửa đè giá trực tiếp và khi dán lô (suy luận để tránh tháng âm; chưa ai chốt). ĐÃ CHỐT (người dùng, 19/10/2026): đúng như vậy, như công thức Excel.
- Fixture có 3 cặp phiếu mà thứ tự mã trái thứ tự ngày (PH-008/009, 011/012, 014/015), nên lần phân bổ lại đầu tiên báo các phiếu này đổi tháng dù tổng từng tháng không đổi. Đó là tính chất của dữ liệu mẫu, không phải lỗi; với dữ liệu thật cần kiểm lại.
- Gói sửa ngày/hình thức phiếu: bấm ô Ngày trả/Hình thức để sửa, bấm ô Số tiền trả để hủy. Đổi ngày làm chạy lại phân bổ theo (ngày, mã phiếu), nên một phiếu đổi ngày có thể làm nhiều phiếu khác đổi tháng (đo: đổi PH-020 về 01/01/2026 làm 13 phiếu đổi tháng). Đúng quy tắc A nhưng có thể gây bất ngờ; người dùng chưa xem.
- Phiếu cũ thiếu dữ liệu gốc về dòng dư (`ỨNG TRƯỚC`) cần quy tắc nhận diện trước khi áp dụng ngoài bản thử.
- Lịch sử ghi dòng điều chỉnh cả tháng thứ hai dạng `0 → -3.000.000` (số của dòng mới), không phải số lũy kế của tháng. Người dùng chưa xem.
