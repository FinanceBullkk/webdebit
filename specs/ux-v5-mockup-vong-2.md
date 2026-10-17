# Sổ công nợ V5 — mockup vòng 2

Trạng thái: **ĐỀ XUẤT** (Claude, 17/10/2026) cho bước 3 quy trình frontend. Chín khung vòng 1 đã review xong; vòng này sửa theo chín quyết định người dùng chốt ngày 17/10/2026.

Nguồn: [bản ghép V5](ux-v5-ban-ghep.md) mục 8, [bản quyết định 17/10](ux-v5-quyet-dinh-2026-10-17.md), [brief](ux-brief-so-cong-no.md) mục 5 và 6.

## Người dùng và luồng (bước 1)

**Người thao tác.** Ba vai, có thể là ba người khác nhau, đều trên 40 tuổi, quen bảng tính, cần ít thao tác hơn là đẹp:
- *Người nhập* `Nguyễn Văn A` — gõ/dán chuyến vào tháng đang mở.
- *Người thu tiền* `Trần Thị B` — ghi tiền khách trả.
- *Người chốt* `Lê Văn C` — cuối tháng xem lại rồi chốt công nợ một tháng của một khách.

**Bối cảnh.** 240 sổ, mỗi sổ là một khách × một loại hàng; 10–50 container mỗi ngày; người nhập copy cả lô từ bảng tính rồi dán. Màn hình bàn/laptop, khung 1500×1000.

**Luồng 1 — thêm một lô chuyến (3 thao tác).** Mở app → chọn sổ ở cột trái → dán thẳng vào dòng trống cuối bảng của tháng đang mở. Hộp thoại "Dán từ bảng tính" là đường phụ (4 thao tác), giữ cho người muốn xem thứ tự 11 cột trước khi dán.

**Luồng 2 — ghi một khoản tiền khách trả (gõ thẳng trên dòng).** Chọn sổ → chọn dòng chuyến → gõ bốn ô ngay trên dòng: ngày nhận tiền, cách thu, tham chiếu, số tiền → Enter. **Không mở màn khác.** Một khoản thu phủ nhiều chuyến là bình thường; dòng chuyến chỉ là chỗ gõ, tiền thuộc về sổ và được phân bổ theo kỳ nợ, nợ cũ trước.

**Luồng 3 — chốt công nợ một tháng (3 thao tác).** Chọn sổ → `Chốt công nợ tháng 04` → hộp xem lại hiện số chuyến có giá, tổng tiền, dòng thiếu giá → `Xác nhận chốt`.

**Bị chặn khi:** người đang đăng nhập chính là người đã nhập các chuyến trong tháng; hoặc còn dòng chưa có giá. Chặn vì nhiều lý do thì **nêu hết trong một lần**.

**Việc chưa xong phải thấy ngay:** dòng thiếu giá, chứng từ chưa xác nhận, tháng chưa chốt — thấy được ở cột trái mà không phải mở từng sổ.

## Đầu ra

Một page Penpot tên `ux-v5-mockup-vong-2` gồm 10 board màn hình theo thứ tự thao tác, cộng đúng một board "Ghi chú" (tối đa 10 dòng, chỉ điểm CÒN MỞ và giả định).

## Đối chiếu dữ liệu và code hiện có (bước 2)

Toàn bộ là **dữ liệu giả**, lấy từ brief mục 6. Không bịa thêm số.

**Sổ đang xem:** `KHACH_MAU · thanh long`, tuyến `PHAN THIET → SHEKOU`. Ngày xem `17/10/2026`, tháng xem `04.2026`.

**Cột trái — 5 sổ mẫu trong 240 sổ**, nhóm theo loại hàng:

| Nhóm | Sổ | Đã chốt | Đang mở | Trạng thái |
| --- | --- | --- | --- | --- |
| Thanh long | KHACH_MAU | 95.000.000 | 90.000.000 | đang mở |
| Thanh long | KHACH_B | 100.000.000 | — | đã chốt |
| Thanh long | KHACH_C | 0 | — | chưa mở |
| Mít | KHACH_D | 70.000.000 | — | đã chốt |
| Mít | KHACH_E | 12.000.000 | 45.000.000 | đang mở |

Thẻ KHACH_MAU có thêm dòng cảnh báo `1 dòng thiếu giá · 1 chứng từ chưa xác nhận (5.000.000)`.

**Các tháng của sổ KHACH_MAU:** `01.2026 đã chốt · 02/02/2026` số dư cuối tháng `40.000.000`; `02.2026 đã chốt · 02/03/2026` → `70.000.000`; `03.2026 đã chốt · 02/04/2026` → `95.000.000`; `04.2026 đang mở · chưa chốt`.

**Bảng tháng 04.2026** — cột: STT · Số container · Ngày · Đơn giá · Thành tiền · Ngày nhận tiền · Cách thu · Đã thu · Tình trạng.

| STT | Container | Ngày | Đơn giá | Thành tiền | Tình trạng |
| --- | --- | --- | --- | --- | --- |
| 1 | DEMO-105 | 08/04/2026 | 40.000.000 | 40.000.000 | Chưa chốt |
| 2 | DEMO-106 | 12/04/2026 | 30.000.000 | 30.000.000 | Chưa chốt |
| 3 | DEMO-107 | 18/04/2026 | 20.000.000 | 20.000.000 | Chưa chốt |
| 4 | DEMO-103 | 22/04/2026 | — | Chưa có dữ liệu | Thiếu giá |

Ba ô phí của mọi dòng để trống (`—`): không phát sinh phí, nên thành tiền bằng đúng đơn giá. **Không có cột số lượng.** Dòng 5 là dòng trống để gõ hoặc dán: `Nhập container hoặc dán lô…`.

**Số tổng của tháng 04** (không điền vào từng dòng): số dư tháng chuyển sang `95.000.000`; phát sinh tháng 04 · 3 chuyến có giá `90.000.000`; đã thu trong tháng `—`; còn phải thu cuối tháng (phần đã chốt) `95.000.000`; đang mở · chưa chốt `90.000.000`.

**Chứng từ treo:** `5.000.000 trên DEMO-103 chưa có ngày nhận tiền · Chưa xác nhận, không vào số dư`. Tham chiếu `CT-CHO-05`. Hiện trong cột `Đã thu` của dòng đó dạng mờ `5.000.000 · chưa xác nhận`, và ở hộp góc trái `Chứng từ cần xác nhận · KHACH_MAU · 5.000.000`.

**Chi tiết một chuyến** (bung dưới dòng đang chọn, 7 trường): Hãng tàu `WH` · Nơi đi `PHAN THIET` · Nơi đến `SHEKOU` · Phí khác `—` · Phí cắm điện cảng `—` · Phí áp tải `—` · Tham chiếu `—`. Kèm một dòng: `Thành tiền = đơn giá + phí khác + phí cắm điện cảng + phí áp tải`.

**Khoản thu 120.000.000** (ngày nhận tiền `20/04/2026`, cách thu `Chuyển khoản`, tham chiếu `UNC-0420`, phủ ba chuyến DEMO-105/106/107) phân bổ:

| Phân bổ vào | Số tiền |
| --- | --- |
| Số dư trước tháng 01.2026 | 20.000.000 |
| Tháng 01.2026 | 20.000.000 |
| Tháng 02.2026 | 30.000.000 |
| Tháng 03.2026 | 25.000.000 |
| *hết phần đã chốt* | *95.000.000* |
| Tháng 04.2026 · đang mở | 25.000.000 |
| **Tổng khoản thu** | **120.000.000** |

Kết quả: đã chốt `0` kèm chữ `đã thu đủ`; đang mở `65.000.000`; đã thu trong tháng `120.000.000`; còn phải thu cuối tháng `0`.

**Khoản thu 200.000.000 — trường hợp trả dư** (ngày nhận tiền `22/04/2026`, cách thu `Chuyển khoản`, tham chiếu `UNC-0422`): trừ hết `95.000.000` đã chốt, rồi hết `90.000.000` đang mở, còn **dư 15.000.000**.

| Phân bổ vào | Số tiền |
| --- | --- |
| Số dư trước tháng 01.2026 | 20.000.000 |
| Tháng 01.2026 | 20.000.000 |
| Tháng 02.2026 | 30.000.000 |
| Tháng 03.2026 | 25.000.000 |
| Tháng 04.2026 · đang mở | 90.000.000 |
| **Không còn nợ để trừ · trả dư** | **15.000.000** |
| **Tổng khoản thu** | **200.000.000** |

Kết quả: đã chốt `0 · đã thu đủ`; đang mở `0 · đã thu đủ`; còn phải thu cuối tháng **`−15.000.000`** kèm chữ `khách trả dư · phải trả lại`.

**Câu chữ giữ nguyên, không đổi:** `Dán từ bảng tính` · `Dòng mới` · `Dán trực tiếp vào dòng trống cuối bảng` · `Chốt công nợ tháng 04` · `Tối đa 50 dòng mỗi lần dán` · `Không dán các cột tiền thu; STT sẽ được hệ thống đánh lại` · `Thứ tự 11 cột cần đối chiếu với bảng tính thật` · `Chưa xác nhận, không vào số dư` · `Giá của DEMO-103 chưa có · Dòng vẫn lưu, không tính vào tổng và chưa thể chốt` · `Nhấn Enter hoặc chuyển ô để lưu · Không mở trang nhập tiền khác` · `Nợ cũ trước, phần dư mới trừ vào tháng đang mở` · `Số dư lịch sử tháng 01 / 02 / 03 không bị sửa ngược`.

**Mười một cột khi dán, đúng thứ tự:** STT (hệ thống tự đánh số) · Số container · Hãng tàu · Ngày · Nơi đi · Nơi đến · Phí khác · Phí cắm điện cảng · Phí áp tải · Đơn giá · Thành tiền.

**Code hiện có:** chưa có trang V5 trong `cong-no-web-handoff/preview/`; bước này **chỉ vẽ Penpot, không sửa repo**. Trang và model sẽ dựng ở bước 6 theo mockup đã duyệt.

## Trạng thái cần có trên mockup

Mười board, đánh số theo thứ tự thao tác. Board 1–9 là bộ vòng 1 đã sửa; board 10 là khung mới.

| # | Board | Phải khác vòng 1 ở chỗ |
| --- | --- | --- |
| 1 | Mặc định — cột trái + tháng 04 đang mở, có dòng thiếu giá | Đơn giá về 40/30/20; cột `Đã thu` của DEMO-103 hiện `5.000.000 · chưa xác nhận` thay cho `—` |
| 2 | Bung chi tiết một chuyến | Thêm dòng công thức `thành tiền = đơn giá + 3 phí`; bỏ câu "cách tính thành tiền khi thiếu phí đang chờ xác nhận" |
| 3 | Dán từ bảng tính, 11 cột đánh số | Thêm: cột Thành tiền dán vào chỉ dùng **đối chiếu**, lệch thì báo `lệch X, kiểm lại`, không tự sửa và không tự bỏ dòng |
| 4 | Đang gõ khoản thu 120.000.000 ngay trên dòng DEMO-105 | Nhãn đổi thành `ghi tại dòng DEMO-105`; nói rõ khoản thu thuộc sổ, phủ ba chuyến |
| 5 | Kết quả thu 120.000.000 + bảng phân bổ | Giữ dấu "phủ ba chuyến" trên cả DEMO-106 và DEMO-107 sau khi lưu; hộp phân bổ không che bảng; cảnh báo cột trái vẫn còn `1 dòng thiếu giá` |
| 6 | Chặn chốt, nêu đủ hai lý do | Giữ nguyên |
| 7 | Người chốt hợp lệ, DEMO-103 đã bổ sung giá 15.000.000 | Thêm câu: chốt xong, chứng từ 5.000.000 vẫn treo, vẫn chưa vào số dư |
| 8 | Cột trái đang lọc `chưa chốt` (2 / 5 sổ mẫu) | Giữ nguyên |
| 9 | Bỏ dòng DEMO-103 đang có chứng từ | Từ **chặn** đổi thành **xác nhận**: bỏ dòng thì bỏ luôn chứng từ 5.000.000 chưa xác nhận, không đổi số dư, có lưu vết; thêm một câu: khoản **đã xác nhận** không đi đường này, phải đảo riêng |
| 10 | **Khách trả dư** — khoản thu 200.000.000 | Khung mới: số âm `−15.000.000` kèm chữ `khách trả dư · phải trả lại`, bảng phân bổ có dòng `Không còn nợ để trừ · trả dư` |

## Hành vi và bất biến

- VND số nguyên, ghi đủ số, không viết tắt kiểu `95tr`.
- Ô chưa biết hiện `—`, **không** hiện `0` và không cộng như 0.
- Hai số `đã chốt` và `đang mở` để riêng. **Không nơi nào cộng thành 185.000.000**, kể cả trong bảng phân bổ của board 10.
- Ba thanh tháng đã chốt giữ nguyên `40.000.000 / 70.000.000 / 95.000.000` ở mọi board; khoản thu không sửa ngược số dư lịch sử.
- Tiền thu trừ nợ cũ trước, rồi mới tới tháng đang mở.
- Số âm chỉ xuất hiện ở board 10 và chỉ do khách trả dư, luôn kèm chữ `khách trả dư · phải trả lại`. Âm do phân bổ sai là lỗi.
- Dòng thiếu giá không được cộng vào tổng tháng; chứng từ chưa xác nhận không vào số dư.
- Người nhập khác người chốt; mỗi board chọn đúng người đang đăng nhập cho việc của board đó.
- Số của cả tháng không điền vào từng dòng.
- Không có từ kỹ thuật, mã quyết định hay ghi chú review bên trong khung màn hình.

## Tiêu chí nghiệm thu

- [ ] Đủ 10 board, đúng thứ tự thao tác, cộng một board "Ghi chú".
- [ ] Mọi con số khớp mục "Đối chiếu dữ liệu"; không có số nào bịa thêm.
- [ ] Board 10 ra đúng `−15.000.000` và không in ra con số `185.000.000`.
- [ ] Không board nào còn đơn giá khác thành tiền khi ba phí để trống.
- [ ] Không board nào hiện chữ `debit`.
- [ ] Cỡ chữ ≥ 12px, không tiền viết tắt, không từ kỹ thuật trên màn hình (script tự kiểm).
- [ ] Người dùng duyệt trên Penpot và lưu phiên bản có tên.

## Ảnh chụp giao diện

Trang được chụp là bản mockup HTML `cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html`: mỗi khung là một `section` id `khung-01`…`khung-10`, đổi khung bằng `#scene-select` (value là số khung). Hai khung có bảng phân bổ được chụp hai lần — một lần panel đang mở, một lần đã đóng để thấy trọn bảng chuyến.

```json
{
  "page": "cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html",
  "viewports": [[1500, 1000]],
  "states": [
    {"name": "khung-01-mac-dinh", "board": "01 · Mặc định", "note": "So mac dinh, co dong thieu gia",
     "shot": "#khung-01", "steps": [{"select": ["#scene-select", "1"]}]},
    {"name": "khung-02-bung-chi-tiet", "board": "02 · Bung chi tiết", "note": "Bung chi tiet va cong thuc thanh tien",
     "shot": "#khung-02", "steps": [{"select": ["#scene-select", "2"]}]},
    {"name": "khung-03-dan-11-cot", "board": "03 · Dán 11 cột", "note": "Dan bang tinh 11 cot",
     "shot": "#khung-03", "steps": [{"select": ["#scene-select", "3"]}]},
    {"name": "khung-04-go-tien", "board": "04 · Gõ tiền trên dòng", "note": "Go bon o khoan thu tai dong DEMO-105",
     "shot": "#khung-04", "steps": [{"select": ["#scene-select", "4"]}]},
    {"name": "khung-05-thu-120", "board": "05 · Thu 120 triệu", "note": "Panel phan bo dang mo",
     "shot": "#khung-05", "steps": [{"select": ["#scene-select", "5"]}]},
    {"name": "khung-05-thu-120-dong-panel", "board": "05 · Thu 120 triệu", "note": "Da dong panel de thay tron bang chuyen",
     "shot": "#khung-05", "steps": [{"select": ["#scene-select", "5"]}, {"click": "button[data-action=\"drawer-close\"]"}]},
    {"name": "khung-06-chan-chot", "board": "06 · Chặn chốt", "note": "Neu du hai ly do trong mot lan",
     "shot": "#khung-06", "steps": [{"select": ["#scene-select", "6"]}]},
    {"name": "khung-07-chot-hop-le", "board": "07 · Chốt hợp lệ", "note": "Chung tu 5.000.000 van treo sau khi chot",
     "shot": "#khung-07", "steps": [{"select": ["#scene-select", "7"]}]},
    {"name": "khung-08-loc-chua-chot", "board": "08 · Lọc chưa chốt", "note": "2 tren 5 so mau",
     "shot": "#khung-08", "steps": [{"select": ["#scene-select", "8"]}]},
    {"name": "khung-09-bo-dong", "board": "09 · Bỏ dòng có chứng từ", "note": "Xac nhan bo dong kem chung tu chua xac nhan",
     "shot": "#khung-09", "steps": [{"select": ["#scene-select", "9"]}]},
    {"name": "khung-10-tra-du", "board": "10 · Khách trả dư", "note": "Am 15.000.000 kem chu phai tra lai",
     "shot": "#khung-10", "steps": [{"select": ["#scene-select", "10"]}]},
    {"name": "khung-10-tra-du-dong-panel", "board": "10 · Khách trả dư", "note": "Da dong panel de thay tron bang chuyen",
     "shot": "#khung-10", "steps": [{"select": ["#scene-select", "10"]}, {"click": "button[data-action=\"drawer-close\"]"}]}
  ]
}
```

Lưu ý khi chạy qua `agent-run.ps1`: bản "TRƯỚC thay đổi" lấy bằng `git archive` tại điểm rẽ nhánh. Trang mockup là file mới nên chưa tồn tại ở đó, `git archive` báo `pathspec ... did not match any files` và bước chụp dừng. Chạy thẳng công cụ thì không vướng:

```
node scripts/ui-capture.js --spec specs/ux-v5-mockup-vong-2.md --root . --out <thư mục> --label after
```

## Phạm vi agent

- Agent: gemini
- Mockup: ĐÃ DUYỆT `cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html` tại commit `a7ea67b9e4cd0ebd74c02a9651e2b917b121618f` · người dùng · 17/10/2026
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/preview/so-cong-no-v5.html`
  - `cong-no-web-handoff/preview/so-cong-no-v5-model.js`
- Ngân sách diff: 400
- Lệnh kiểm:
  - `npm run test:unit`

  Lệnh kiểm chỉ chạy ở bước 6; bước mockup không chạy lệnh nào.
- Cấm:
  - Bước 3 **không sửa file nào trong repo** và không chạy lệnh terminal.
  - Thêm tính năng, cột, chính sách hoặc lựa chọn thiết kế ngoài spec.
  - Quyết định hộ bốn điểm CÒN MỞ bên dưới.
  - Vẽ nút xác nhận chứng từ, vẽ phân quyền, vẽ hoàn tiền hay tranh chấp.
- Khi cần vượt phạm vi: dừng, ghi vào "Câu hỏi mở".

## Còn mở — không chốt hộ

1. Thứ tự 11 cột thật trong bảng tính: chưa đối chiếu.
2. Ai được xác nhận chứng từ và căn cứ gì: hoãn.
3. Tiền dư có dùng được cho sổ khác của cùng khách không: đang mặc định là không.
4. Sổ "chưa mở" có tính là "chưa chốt" không: board 8 đang coi là không.

## Hoàn tác

Chỉ là mockup Penpot và tài liệu; chưa sửa code hay dữ liệu. Bỏ bằng cách xoá page Penpot và file này.

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
