# V6 — sổ công nợ theo đúng sheet đang dùng, bỏ bước chốt tháng (18/10/2026)

Trạng thái: **ĐÃ CHỐT** bởi người dùng trong chat ngày 18/10/2026, sau khi đối chiếu mockup với sheet công nợ đang dùng. **Chưa triển khai** vào model, bản thử hay backend.

Phạm vi: **mô hình nghiệp vụ và bố cục màn sổ công nợ**. Không phải migration, không mở đường ghi tiền, không thay nghiệm thu backend.

Nguồn: chat 18/10/2026; sheet công nợ đang dùng, đọc **read-only** ngày 18/10/2026 (chỉ lấy cấu trúc, không chép tên khách, số tiền hay mã sheet); mockup canvas "Sổ công nợ V6 — mockup", các board C1, C2, A0.

## 1. Sheet đang dùng trông thế nào

Đọc trang tổng và 5 sổ thuộc ba loại (trái cây, đường bộ, bán cước); file có khoảng 250 tab.

- **Một tab = một khách × một loại hàng.** Các tháng xếp dọc trong tab, tháng mới nhất ở dưới cùng.
- **Mỗi khối tháng:** tiêu đề `SỔ CHI TIẾT THEO DÕI CÔNG NỢ PHẢI THU THÁNG x` → tên khách → hàng tiêu đề cột → `SỐ DƯ THÁNG CHUYỂN SANG` → các chuyến → dòng `TỔNG`.
- **11 cột chuyến đúng thứ tự** `Marks & Nos · CONTAINER NO · (hãng tàu, không có tiêu đề) · DATE · FROM · TO · OTHER FEE · OTHER FEE 码头插电费 · OTHER FEE 押车 · UNIT PRICE · TOTAL(VND)`. Giống nhau ở cả ba loại sổ đã xem, và khớp thứ tự brief §4.
- **Cột tiền bên phải:** `NGAY TT(STK)` · `SỐ ĐÃ ỨNG TRƯỚC/ĐÃ THU TRONG THÁNG` · `SỐ CÒN PHẢI THU CUỐI THÁNG` · `TỔNG THU`. Tiền thu ghi **một lần ở dòng đầu tháng**, số tiền có thể lớn hơn phát sinh vì trả cả nợ tháng trước.
- `NGAY TT(STK)` là **chữ tự do**: lúc là ngày, lúc là số tài khoản, lúc là "DA TT". Không có cột cách thu.
- **Không có trạng thái chốt, chờ duyệt hay người duyệt** ở đâu trong sheet.
- `SỐ CÒN PHẢI THU CUỐI THÁNG` = chuyển sang + phát sinh trong tháng − đã thu. **Gồm cả phát sinh của tháng.**
- Trang tổng có **số âm** ở nhiều khách (khách ứng trước).
- Lỗi chép tay: nhãn tháng sai so với khối, ghi chú nhét vào cột container hoặc cột nơi đi, dòng phí không có container.

## 2. Quyết định

| # | Câu hỏi | Chốt |
| --- | --- | --- |
| V6-1 | Có bước chốt công nợ tháng không? | **Không.** Nhập chuyến xong là tính vào nợ, giống sheet. Bỏ khái niệm đã chốt / đang mở, nút chốt, lý do chặn chốt |
| V6-2 | Có tách người nhập và người duyệt không? | **Không.** Thay quyết định `D01`; `Q02` (duyệt theo revision) không còn áp dụng cho chuyến và khoản thu của sổ |
| V6-3 | Sửa số của tháng trước thế nào? | **Không sửa đè.** Ghi một dòng điều chỉnh có lý do và lưu vết: ai, lúc nào, dòng nào, số cũ, số mới |
| V6-3b | "Tháng trước" tính từ đâu? | **Theo tháng lịch, cộng ngày đệm đầu tháng.** Trong ngày đệm, tháng vừa qua vẫn sửa thẳng được; hết ngày đệm thì chỉ sửa bằng dòng điều chỉnh. Không thêm thao tác nào cho người dùng. Số ngày đệm: **ĐỀ XUẤT hết ngày 5** của tháng sau, chờ người dùng xác nhận |
| V6-3c | Dòng điều chỉnh thuộc tháng nào? | **Thuộc đúng tháng gốc của chuyến.** Còn phải thu cuối tháng đó đổi, và số chuyển sang của mọi tháng sau tính lại theo. Màn hiện số cũ gạch ngang cạnh số mới. Số tiền điều chỉnh có thể dương hoặc âm; lý do bắt buộc |
| V6-3d | Điều chỉnh một tháng đã được trả bởi khoản thu trước đó thì sao? | **Phân bổ lại các khoản thu theo nợ cũ trước.** Ví dụ: thu 120.000.000 đã trừ 25.000.000 vào tháng 03; tháng 03 điều chỉnh +5.000.000 → tháng 03 nhận 30.000.000, tháng 04 còn 20.000.000. Câu trả lời "tiền trừ vào tháng nào" vì vậy có thể đổi sau điều chỉnh; lịch sử sửa phải ghi lại phân bổ trước và sau. Không áp dụng cho dữ liệu opening chuyển từ Sheet |
| V6-4 | Màn hiện mấy con số dư? | **Một số:** `Còn phải thu cuối tháng = chuyển sang + phát sinh − đã thu`, giống sheet. Bỏ tiêu chí "không chỗ nào in 185.000.000" |
| V6-5 | Số âm hiện thế nào? | **Hiện số âm trần, không kèm chữ.** Âm nghĩa là khách đã ứng trước: tiền đưa trước, trừ dần vào khoản phải thu sau. Thay quyết định 8 của `V5-UX` ("khách trả dư · phải trả lại") |
| V6-6 | Bố cục màn sổ? | **Khối tháng như sheet** (hướng C): các tháng trước gập thành nút; khối tháng gồm dòng chuyển sang → 11 cột đúng thứ tự sheet → dòng dán ở cuối → dòng `TỔNG`. Ô tiền bên phải gộp cả khối |
| V6-7 | Nhãn cột? | **11 cột chuyến dùng nhãn tiếng Anh như sheet**; cột tiền giữ nhãn tiếng Việt của sheet; phần còn lại của màn tiếng Việt |
| V6-8 | Ô nhập khoản thu? | Ngày nhận là **ô ngày riêng**; số tài khoản gộp vào ô tham chiếu; cách thu giữ bốn giá trị của brief |
| V6-9 | Màn mở đầu? | **Màn Tổng** theo trang tổng của sheet; lọc `Còn nợ` · `Ứng trước · số âm` · `Có dòng thiếu giá` |

## 3. Giữ nguyên

- VND số nguyên chính xác; ô trống khác 0, hiện `—`.
- Dòng chưa có giá **không cộng** vào phát sinh, và được nêu tên.
- Tiền thu trừ tháng cũ nhất trước (`D03`); xem lại được một khoản thu trừ vào tháng nào, mỗi tháng bao nhiêu (brief §3.7).
- Khoản thu thuộc sổ (khách × loại hàng) + kỳ, không thuộc chuyến (`V5-UX` quyết định 1).
- Chứng từ chưa có ngày nhận tiền không tính vào số dư.
- Container không phải khóa duy nhất.
- Thành tiền = đơn giá + ba loại phí; cột thành tiền dán vào chỉ dùng đối chiếu.

## 4. Số mẫu theo V6

Dữ liệu giả của brief §6, tháng 04.2026 sổ `KHACH_MAU · thanh long`:

- Chuyển sang `95.000.000`, phát sinh 3 chuyến có giá `90.000.000`, đã thu `—` → **còn phải thu cuối tháng `185.000.000`**. DEMO-103 thiếu giá, không cộng.
- Thu `120.000.000` ngày 20/04/2026 → trừ `20 / 20 / 30 / 25` vào trước tháng 01 và các tháng 01–03, rồi `25.000.000` vào tháng 04 → **còn phải thu cuối tháng `65.000.000`**.
- Thu `200.000.000` thay cho khoản trên → **còn phải thu cuối tháng `−15.000.000`**, hiện số âm trần.
- Màn Tổng: `KHACH_E` còn phải thu cuối tháng `57.000.000` (12 + 45).

## 5. Hệ quả — phải sửa, chưa sửa

Mỗi mục dưới đây là việc riêng, cần spec riêng trước khi code.

1. **Model** `so-cong-no-v5-model.js`: `ledgerBalance` đang tách `closedRemainingVnd` / `openRemainingVnd`; `allocateReceipt` dùng hai loại bucket `closed` / `open`; `canClose` không còn dùng. Test `test-so-cong-no-v5-model.js` có tiêu chí "không trường nào bằng 185.000.000".
2. **Spec** `v5-giao-dien.md`: tiêu chí `thu-120-trieu`, `khach-tra-du`, `chan-chot-hai-ly-do`, `chot-hop-le`, "không màn nào in 185.000.000", và luồng chốt 3 thao tác.
3. **Brief** `ux-brief-so-cong-no.md`: §2 vai *người chốt*, §3.3, §3.6 ("khách nào chưa chốt"), §3.8, §5 quy tắc 3, 4b, 5, 6, ngưỡng thao tác chốt ở §8.
4. **Bản thử V5** `so-cong-no-v5.html` + `so-cong-no-v5-ui.js`: mốc `V5-GD` không còn là giao diện đích.
5. **Đường ghi tiền P0**: `02-versioned-approval-identity.md`, `06-period-posting-lock.md`, và `Q01`, `Q08` trong `decisions-needed.md`.
6. **`AGENTS.md`**: câu "không ghi tiền thiếu … phê duyệt riêng" cần đọc lại theo V6-2; câu "không phân bổ lại lịch sử" cần ghi rõ chỉ áp dụng cho opening, theo V6-3d.

## 6. Còn mở — không chốt hộ

1. **Số ngày đệm của V6-3b:** đang đề xuất hết ngày 5 của tháng sau. Ngày đệm tính theo ngày lịch hay ngày làm việc cũng chưa quyết.
2. Tiền ứng trước ở một sổ có trừ được cho sổ khác của cùng khách không (`D04`) — đang mặc định là không.
3. Dòng phí không có container trong sheet nhập vào web thế nào.
4. Danh mục cách thu bốn giá trị đã đủ chưa.
5. Nhãn tiếng Anh tự đặt vì sheet không có: `CARRIER` (cột hãng tàu không có tiêu đề), `PLUG FEE`, `ESCORT FEE` (dịch từ nhãn tiếng Trung).
6. Không còn duyệt thì "ai sửa gì" chỉ dựa vào lưu vết; ai được xem lưu vết chưa quyết.

## 7. Hoàn tác

Tài liệu mới, một dòng trong `docs/decisions.md`, một dòng trong `docs/business-rules.md`. Không đụng code hay dữ liệu. Revert commit.
