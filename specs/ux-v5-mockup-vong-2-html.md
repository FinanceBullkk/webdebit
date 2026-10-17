# V5 vòng 2 — bản chuyển thể để đặt làm mockup HTML

Đây **không phải spec thứ hai**. Nguồn quy tắc và số liệu vẫn là [`ux-v5-mockup-vong-2.md`](ux-v5-mockup-vong-2.md); file này chỉ chuyển nội dung đó sang dạng dán được cho công cụ viết HTML, bỏ phần Penpot và phần hợp đồng agent. Lệch nhau thì theo file gốc.

Cách dùng: dán toàn bộ phần dưới đường kẻ cho ChatGPT, **kèm file `index.html` đang có** để nó sửa tiếp chứ không làm lại từ đầu.

---

## Việc cần làm

Sửa tiếp bản mockup HTML hiện có của sổ công nợ V5. Giữ nguyên kiến trúc hiện tại: **một file `index.html` độc lập**, HTML + CSS + JavaScript trong cùng file, không thư viện ngoài, không backend, dữ liệu giả trong bộ nhớ trang.

Bản hiện tại có 9 khung và được làm theo một vòng góp ý cũ. Vòng này có **chín quyết định mới của chủ nghiệp vụ** và **thêm khung thứ 10**.

## Giữ nguyên, đừng làm lại

Những thứ bản hiện tại đã làm đúng: bố cục hai cột; thẻ sổ ở cột trái đổi số theo từng khung; cột `Đã thu` của DEMO-103 hiện `5.000.000 · Chưa xác nhận` kèm tham chiếu; tiền căn phải; menu `⋮` từng dòng; dòng dán trực tiếp cuối bảng; link xem bảng phân bổ; băng "Chỉ mô phỏng · không kết nối dữ liệu thật".

## Chín quyết định mới — bắt buộc

1. **Khoản thu thuộc sổ (khách × loại hàng) + kỳ nợ, không thuộc chuyến.** Dòng chuyến chỉ là chỗ gõ. Bỏ mọi cách diễn đạt kiểu "chứng từ gắn DEMO-103"; thay bằng "ghi tại dòng DEMO-105" hoặc tương đương.
2. **Không có cột số lượng.**
3. **Thành tiền = đơn giá + phí khác + phí cắm điện cảng + phí áp tải**, hệ thống tự cộng.
4. Chưa xét phân quyền xác nhận chứng từ — **không vẽ nút xác nhận**.
5. **Cho chốt tháng** kể cả khi còn chứng từ chưa xác nhận; chốt xong chứng từ vẫn treo, vẫn ngoài số dư.
6. **Ô phí để trống = không phát sinh phí.** Vẫn hiện `—`, không hiện `0`, và khi cộng thành tiền thì coi như không có.
7. **Bỏ dòng chuyến đã lưu thì bỏ luôn chứng từ chưa xác nhận trên đó**, có lưu vết. Khung hiện tại đang **chặn** — đổi thành **xác nhận**. Thêm một câu: khoản thu **đã xác nhận** không đi đường này, phải đảo riêng.
8. **Khách trả dư thì hiện số âm** kèm chữ `khách trả dư · phải trả lại`.
9. Tiền dư nằm lại **trong sổ đó**, không tự mang sang sổ khác của cùng khách.

Hệ quả trực tiếp của quyết định 2, 3 và 6: **đơn giá phải bằng thành tiền** ở ba dòng mẫu, vì cả ba ô phí đều trống. Hiện đang là `price 10.000.000 → amount 40.000.000`, sai. Sửa thành `40.000.000 / 30.000.000 / 20.000.000`.

## Số liệu — lấy đúng, không bịa

Sổ `KHACH_MAU · thanh long`, tuyến `PHAN THIET → SHEKOU`, ngày xem `17/10/2026`, tháng xem `04.2026`.

**Cột trái, 5 sổ mẫu trong khoảng 240 sổ:**

| Nhóm | Sổ | Đã chốt | Đang mở | Trạng thái |
| --- | --- | --- | --- | --- |
| Thanh long | KHACH_MAU | 95.000.000 | 90.000.000 | đang mở |
| Thanh long | KHACH_B | 100.000.000 | — | đã chốt |
| Thanh long | KHACH_C | 0 | — | chưa mở |
| Mít | KHACH_D | 70.000.000 | — | đã chốt |
| Mít | KHACH_E | 12.000.000 | 45.000.000 | đang mở |

**Các tháng:** `01.2026 đã chốt · 02/02/2026` → số dư cuối tháng `40.000.000`; `02.2026 đã chốt · 02/03/2026` → `70.000.000`; `03.2026 đã chốt · 02/04/2026` → `95.000.000`; `04.2026 đang mở · chưa chốt`.

**Bảng tháng 04:**

| STT | Container | Ngày | Đơn giá | Thành tiền | Tình trạng |
| --- | --- | --- | --- | --- | --- |
| 1 | DEMO-105 | 08/04/2026 | 40.000.000 | 40.000.000 | Chưa chốt |
| 2 | DEMO-106 | 12/04/2026 | 30.000.000 | 30.000.000 | Chưa chốt |
| 3 | DEMO-107 | 18/04/2026 | 20.000.000 | 20.000.000 | Chưa chốt |
| 4 | DEMO-103 | 22/04/2026 | — | Chưa có dữ liệu | Thiếu giá |

Ba ô phí của mọi dòng để trống. Chi tiết chuyến (bung dưới dòng, 7 trường): hãng tàu `WH`, nơi đi `PHAN THIET`, nơi đến `SHEKOU`, ba phí `—`, tham chiếu `—`.

**Số tổng tháng 04:** chuyển sang `95.000.000`; phát sinh · 3 chuyến có giá `90.000.000`; đã thu `—`; còn phải thu cuối tháng (phần đã chốt) `95.000.000`; đang mở · chưa chốt `90.000.000`.

**Chứng từ treo:** `5.000.000`, tham chiếu `CT-CHO-05`, chưa có ngày nhận tiền → chưa xác nhận, không vào số dư.

**Khoản thu 120.000.000** — ngày `20/04/2026`, chuyển khoản, `UNC-0420`, phủ ba chuyến DEMO-105/106/107:

| Phân bổ vào | Số tiền |
| --- | --- |
| Số dư trước tháng 01.2026 | 20.000.000 |
| Tháng 01.2026 | 20.000.000 |
| Tháng 02.2026 | 30.000.000 |
| Tháng 03.2026 | 25.000.000 |
| *hết phần đã chốt* | *95.000.000* |
| Tháng 04.2026 · đang mở | 25.000.000 |
| **Tổng khoản thu** | **120.000.000** |

Kết quả: đã chốt `0 · đã thu đủ`; đang mở `65.000.000`; đã thu trong tháng `120.000.000`; còn phải thu cuối tháng `0`.

**Khoản thu 200.000.000 — khung mới, khách trả dư** — ngày `22/04/2026`, chuyển khoản, `UNC-0422`:

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

## Mười khung

| # | Khung | Ghi chú |
| --- | --- | --- |
| 1 | Sổ mặc định, có dòng thiếu giá | sửa đơn giá về 40/30/20 |
| 2 | Bung chi tiết một chuyến | thêm dòng công thức thành tiền = đơn giá + 3 phí |
| 3 | Dán 11 cột | nói rõ cột Thành tiền dán vào chỉ để **đối chiếu**: lệch với số tự cộng thì báo `lệch X, kiểm lại`, không tự sửa, không tự bỏ dòng |
| 4 | Đang gõ khoản thu 120.000.000 trên dòng DEMO-105 | đủ bốn ô: ngày nhận tiền · cách thu · tham chiếu `UNC-0420` · số tiền. Nhãn `ghi tại dòng DEMO-105` |
| 5 | Kết quả thu 120.000.000 + bảng phân bổ | giữ dấu phủ ba chuyến ở DEMO-106 và DEMO-107 |
| 6 | Chặn chốt, nêu **đủ hai lý do** trong một lần | người nhập trùng người chốt; DEMO-103 thiếu giá |
| 7 | Người chốt hợp lệ, DEMO-103 bổ sung giá giả định 15.000.000 → 4 chuyến `105.000.000` | thêm câu: chốt xong chứng từ 5.000.000 vẫn treo |
| 8 | Lọc `chưa chốt` → `2 / 5 sổ mẫu` | KHACH_C "chưa mở" không tính là chưa chốt |
| 9 | **Xác nhận** bỏ dòng DEMO-103 có chứng từ | đổi từ chặn sang xác nhận, theo quyết định 7 |
| 10 | **Khách trả dư** — khoản thu 200.000.000 | khung mới |

Ba vai đăng nhập: người nhập `Nguyễn Văn A`, người thu tiền `Trần Thị B`, người chốt `Lê Văn C`. Mỗi khung chọn đúng vai của việc đó.

## Bất biến — sai là hỏng

- VND số nguyên, ghi đủ số, không viết tắt kiểu `95tr`, không rút gọn `chưa x.nhận`.
- Ô chưa biết hiện `—`, không hiện `0`, không cộng như 0.
- Hai số `đã chốt` và `đang mở` luôn tách riêng. **Không chỗ nào in ra 185.000.000**, kể cả bảng phân bổ của khung 10.
- Ba thanh tháng lịch sử `40.000.000 / 70.000.000 / 95.000.000` giữ nguyên ở **mọi** khung, kể cả sau khi ghi tiền thu.
- Tiền thu trừ nợ cũ trước, rồi mới tới tháng đang mở.
- Số âm chỉ xuất hiện ở khung 10 và chỉ do khách trả dư, luôn kèm chữ. Âm do phân bổ sai là lỗi.
- Dòng thiếu giá không vào tổng tháng; chứng từ chưa xác nhận không vào số dư.
- Số của cả tháng không điền vào từng dòng.

## Yêu cầu kỹ thuật

- Một file `index.html`, không phụ thuộc mạng.
- Mỗi khung là một section có `id="khung-01"` … `id="khung-10"` để công cụ chụp ảnh tự động chụp được từng khung.
- Chữ thân **tối thiểu 16px**; vùng bấm tối thiểu 40px; tương phản chữ tối thiểu 4.5:1; không để chữ tràn hay bị cắt.
- Cột tiền căn phải.
- Người dùng trên 40 tuổi: không từ kỹ thuật, không mã nội bộ, không chữ phục vụ người review bên trong khung màn hình. Ghi chú để **ngoài** khung.

## Bốn điểm CÒN MỞ — không được tự quyết

1. Thứ tự 11 cột thật trong bảng tính: chưa đối chiếu.
2. Ai được xác nhận chứng từ và căn cứ gì: hoãn.
3. Tiền dư có dùng cho sổ khác của cùng khách không: mặc định là không.
4. Sổ "chưa mở" có tính là "chưa chốt" không: khung 8 đang coi là không.

Ghi bốn điểm này ở phần ghi chú ngoài khung màn hình, không tự thêm chính sách nào khác.
