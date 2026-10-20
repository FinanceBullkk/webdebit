# Cấn trừ hai sổ — bản đặt mockup HTML cho ChatGPT

Đây **không phải spec thứ hai**. Quy tắc và trạng thái quyết định nằm ở [`can-tru-hai-so.md`](can-tru-hai-so.md); lệch nhau thì theo file đó. File này chỉ chuyển nội dung sang dạng dán được cho ChatGPT (quyết định CT-2SO, 20/10/2026: mockup tính năng này làm HTML qua ChatGPT thay Penpot).

Đây là bản vòng 1; các chỗ sửa sau khi soát nằm ở [bản sửa vòng 2](can-tru-hai-so-mockup-vong-2.md).

Cách dùng: dán toàn bộ phần dưới đường kẻ cho ChatGPT. Muốn nó vẽ giống màn đang có thì đính kèm ảnh chụp bản thử V7 ở 1280×720 (dữ liệu mẫu ẩn danh `KHACH_MAU_A`). **Không** đính kèm ảnh sổ thật, Sheet thật hay tên khách thật.

---

## Việc cần làm

Làm mockup HTML cho tính năng **"Cấn trừ giữa hai sổ"** của một phần mềm sổ công nợ phải thu (công ty vận chuyển container nông sản). Bàn giao **một file `index.html` độc lập**: HTML + CSS + JavaScript trong cùng file, không thư viện ngoài, không backend, dữ liệu giả nằm trong trang. Trên cùng có băng "Chỉ mô phỏng · không kết nối dữ liệu thật".

## Người dùng và màn hình

- Kế toán công nợ trên 40 tuổi, quen làm trên Google Sheet. Ưu tiên rõ ràng, ít chữ, chữ đủ lớn (thân 14px, ô bảng không dưới 13px). Thông tin quan trọng phải nhìn thấy ngay, không giấu sau rê chuột.
- Màn hình thật là **1280×720 (CSS px)**. Mỗi khung vẽ đúng 1280×720, **không cuộn ngang**.
- Toàn bộ chữ tiếng Việt có dấu. Tiền là VND ghi đủ số, dấu chấm phân nhóm (`50.000.000`), không viết tắt "tr", "k". Số âm hiện trần có dấu trừ (`−100.000.000`), trong ô sổ không kèm chữ "dư".

## Màn sổ đang có (giữ nguyên, chỉ thêm phần cấn trừ)

Mỗi sổ là một khách × một mặt hàng, cuộn liên tục như Sheet:

- **Đầu sổ (dính trên cùng):** Khách · Từ tháng · Chờ xử lý · Tổng còn nợ (mọi tháng).
- **Băng nhóm cột:** `CHUYẾN HÀNG` | `TIỀN KHÁCH TRẢ` | `NỢ`.
- **13 cột ở 1280px, đúng thứ tự:** STT · Số container · Hãng tàu / số xe · Ngày chuyến · Nơi đi · Nơi đến · Đơn giá · Phụ phí · Thành tiền ‖ Ngày trả · Hình thức · Số tiền trả ‖ Còn nợ cộng dồn. **Không thêm cột mới.**
- **Mỗi tháng:** dòng `THÁNG 10/2026` (nút ổ khóa, nhãn `Đang mở`/`Đã khóa`, bên phải "Nợ các tháng trước: …") → các dòng chuyến → ô "Dán các dòng từ Sheet vào đây" → dòng `Cộng tháng 10/2026 (n chuyến) · Phát sinh` có Thành tiền, Đã thu và **Còn nợ cộng dồn**. Còn nợ cộng dồn chỉ hiện ở dòng Cộng tháng, không hiện ở từng dòng chuyến.
- **Ô ghi thu trống** (tháng hiện tại): ba ô Ngày trả · Hình thức · Số tiền trả nằm trong khối TIỀN KHÁCH TRẢ, **cùng hàng với dòng chuyến đầu tiên** của tháng. Đó chỉ là chỗ gõ; phiếu thu không thuộc chuyến nào.
- **Khối TIỀN KHÁCH TRẢ** (ba cột giữa) có nền xanh nhạt riêng, viền trái đậm, để không đọc nhầm phiếu thu là của chuyến cùng hàng.
- Ô **Hình thức** chọn một trong bốn: `THU TIỀN` · `CẤN TRỪ` · `ỨNG TRƯỚC` · `KHÁC`.
- Tiền căn phải. Phiếu thu có mã dạng `PH-012`.

## Nghiệp vụ

Ví dụ: sổ Khách A đang dư 100.000.000 (tổng còn nợ −100.000.000), sổ Khách B đang nợ 50.000.000. Kế toán ghi "cấn trừ 50 triệu từ A" ở sổ B. Kết quả: A còn −50.000.000, B còn 0. Hệ thống ghi **cả hai sổ cùng lúc**.

Quy tắc:

1. Thao tác bắt đầu ở **sổ được trả nợ** (sổ B), trên dòng ghi thu trống.
2. Chọn hình thức `CẤN TRỪ` thì **ngay dưới ba ô ghi thu, trong khối TIỀN KHÁCH TRẢ**, hiện thêm ô **Lấy từ sổ**. Các hình thức khác không có ô này. Danh sách xổ ra được phép đè lên cột Còn nợ cộng dồn bên cạnh, nhưng không đẩy bảng rộng ra.
3. Danh sách Lấy từ sổ có ô gõ để lọc theo tên, gồm:
   - nhóm "Sổ khác của Khách B" (nếu đang dư) ở trên;
   - nhóm "Sổ khách khác đang dư", xếp theo tên A→Z;
   - dòng cuối, tách riêng: **Ngoài sổ (khoản phải trả, USD…) · chỉ trừ sổ này**.
   Mỗi dòng ghi: tên khách · mặt hàng · số âm hiện tại. Không có sổ đang mở, sổ đang nợ hay sổ bằng 0.
4. Số tiền **lớn hơn số dư** của sổ lấy tiền thì báo đỏ ngay tại ô và **không cho ghi**.
5. Hợp lệ thì Enter mở **khung xác nhận**: một câu nói rõ từ sổ nào sang sổ nào, hai ô "trước → sau" cho hai sổ, nút `Ghi cấn trừ` (nút chính) và `Quay lại`.
6. Ghi xong, **cả hai sổ có dòng**, tên sổ bên kia luôn hiện ngay dưới chữ `CẤN TRỪ` và bấm được để mở sổ đó:
   - sổ B: `CẤN TRỪ` · "từ Khách A · sầu riêng" · `50.000.000`;
   - sổ A: `CẤN TRỪ` · "sang Khách B · sầu riêng" · `−50.000.000`, trong khối TIỀN KHÁCH TRẢ, không ở cột Thành tiền.
7. Hủy ở bên nào cũng **hủy cả hai dòng**: bắt buộc nhập lý do, câu xác nhận nêu đủ hai sổ. Sau hủy, hai dòng gạch ngang ngày và số tiền, cột Hình thức thành nhãn `ĐÃ HỦY`, cuối khối tháng có một dòng vết: số tiền · ngày phiếu · ngày hủy · lý do.
8. Chọn **Ngoài sổ** thì không có khung xác nhận, ghi như phiếu thu thường, chỉ sổ đang mở thay đổi.

## Dữ liệu giả (dùng đúng các số này)

Hôm nay: **20/10/2026**.

**Sổ Khách B · sầu riêng** (sổ đang mở). Các tháng trước đã hết nợ. Tháng 10/2026 có ba chuyến:

| STT | Số container | Hãng tàu / số xe | Ngày chuyến | Nơi đi | Nơi đến | Đơn giá | Phụ phí | Thành tiền |
| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| 1 | MAUU1000101 | HTA | 03/10/2026 | KHO TINH A | CANG BAC 1 | 19.000.000 | 1.000.000 | 20.000.000 |
| 2 | MAUU1000102 | HTB | 09/10/2026 | KHO TINH A | CANG BAC 1 | 18.000.000 | — | 18.000.000 |
| 3 | MAUU1000103 | HTC | 15/10/2026 | KHO TINH B | CANG NAM 2 | 11.500.000 | 500.000 | 12.000.000 |

Dòng Cộng tháng 10/2026 (3 chuyến): Phát sinh 50.000.000, Đã thu –, Còn nợ cộng dồn 50.000.000. Nợ các tháng trước: 0. Tổng còn nợ ở đầu sổ: **50.000.000**.

**Danh sách sổ đang dư** (khi mở ô Lấy từ sổ ở sổ Khách B):

| Nhóm | Sổ | Số hiện tại |
| --- | --- | ---: |
| Sổ khác của Khách B | Khách B · thanh long | −20.000.000 |
| Sổ khách khác đang dư | Khách A · sầu riêng | −100.000.000 |
| Sổ khách khác đang dư | Khách C · xoài | −8.500.000 |
| Sổ khách khác đang dư | Khách D · sầu riêng | −3.000.000 |

**Sổ Khách A · sầu riêng.** Các tháng trước đã hết nợ. Tháng 10/2026 không có chuyến; một phiếu `PH-012` ngày 05/10/2026, `THU TIỀN`, 100.000.000. Dòng Cộng tháng 10/2026 (0 chuyến): Phát sinh 0, Đã thu 100.000.000, Còn nợ cộng dồn −100.000.000. Tổng còn nợ ở đầu sổ: −100.000.000.

## Các khung cần vẽ

Mỗi khung 1280×720, có tiêu đề ngắn. Trên cùng trang có các nút 1–9 để chuyển khung.

1. **Chọn CẤN TRỪ** — sổ B, dòng ghi thu: Ngày trả `20/10/2026`, Hình thức `CẤN TRỪ`; ngay dưới hiện ô Lấy từ sổ còn trống; ô số tiền trống.
2. **Danh sách sổ mở** — đủ hai nhóm và dòng Ngoài sổ, ô lọc ở trên cùng.
3. **Vượt số dư** — đã chọn Khách A, gõ `120.000.000`; báo đỏ "Sổ Khách A chỉ còn dư 100.000.000"; không có nút ghi.
4. **Xác nhận** — gõ `50.000.000`, Enter: "Cấn trừ 50.000.000 từ sổ Khách A · sầu riêng sang sổ Khách B · sầu riêng"; Khách A `−100.000.000 → −50.000.000`; Khách B `50.000.000 → 0`.
5. **Sổ B sau khi ghi** — phiếu `PH-021` `CẤN TRỪ` "từ Khách A · sầu riêng" 50.000.000; dòng Cộng tháng: Đã thu 50.000.000, Còn nợ cộng dồn 0; tổng còn nợ 0; dòng báo "Đã ghi cấn trừ 50.000.000 từ sổ Khách A · sầu riêng. Sổ đó còn −50.000.000."
6. **Sổ A sau khi ghi** — dòng `CẤN TRỪ` "sang Khách B · sầu riêng" −50.000.000 ngày 20/10/2026 dưới phiếu PH-012; dòng Cộng tháng: Đã thu 50.000.000, Còn nợ cộng dồn −50.000.000; tổng còn nợ ở đầu sổ −50.000.000.
7. **Hủy cặp** — bấm phiếu PH-021 ở sổ B: dòng hỏi lý do (bắt buộc) và câu "Hủy cấn trừ ở cả hai sổ: Khách A · sầu riêng và Khách B · sầu riêng"; vẽ thêm trạng thái sau hủy (gạch ngang, `ĐÃ HỦY`, dòng vết, tổng còn nợ về 50.000.000).
8. **Ngoài sổ** — chọn dòng Ngoài sổ, gõ 50.000.000: ghi như phiếu thường, không có khung xác nhận, không có tên sổ bên kia.
9. **Không có sổ nào dư** — danh sách chỉ có câu "Không có sổ nào đang dư tiền" và dòng Ngoài sổ.

## Không làm

- Không thêm cột, không cuộn ngang, không đổi phần nào của màn sổ ngoài phần cấn trừ.
- Không vẽ phân quyền, nút duyệt, đính kèm chứng từ, tỷ giá hay ngoại tệ.
- Không dùng tên khách thật; chỉ Khách A, B, C, D.
- Không đổi các số ở trên; số trong mọi khung phải khớp nhau.

## Bàn giao

- File `index.html` như trên.
- Cuối câu trả lời, liệt kê những chỗ bạn phải tự đoán vì đề bài chưa nói rõ. Không tự chốt thay chủ nghiệp vụ.
