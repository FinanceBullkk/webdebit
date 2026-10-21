# Cấn trừ hai sổ — mockup vòng 2 (bản sửa cho ChatGPT)

Đây **không phải spec thứ hai**. Nguồn quy tắc là [`can-tru-hai-so.md`](can-tru-hai-so.md). File này ghi các chỗ phải sửa sau khi soát mockup vòng 1 (ChatGPT, 20/10/2026) và các quyết định người dùng chốt cùng ngày: mỗi sổ một mã phiếu, hủy ngay trong bảng, cho cấn quá số nợ của sổ nhận.

Cách dùng:
- **Nếu vẫn trong cuộc trò chuyện ChatGPT cũ:** dán phần dưới đường kẻ.
- **Nếu mở cuộc trò chuyện mới:** đính kèm file `index.html` vòng 1, dán phần dưới đường kẻ của [bản đặt vòng 1](can-tru-hai-so-mockup-html.md) trước, rồi dán phần dưới đây.

---

## Việc cần làm

Sửa tiếp file `index.html` vòng 1, **không làm lại từ đầu**. Giữ kiến trúc cũ: một file, HTML + CSS + JavaScript trong cùng file, không thư viện ngoài, dữ liệu giả trong trang.

## Giữ nguyên

Bố cục 1280×720 và 13 cột; danh sách Lấy từ sổ (hai nhóm, ô lọc, dòng Ngoài sổ); khung xác nhận; dòng "từ…" / "sang…" bấm được để mở sổ bên kia; dòng báo xanh; các số liệu đã có; khung 9 (không có sổ nào dư); thanh nút chuyển khung.

## Sáu chỗ phải sửa

1. **Mỗi sổ một mã phiếu, không dùng chung.** Sổ Khách B: phiếu cấn trừ là `PH-021`, phiếu Ngoài sổ ở khung 8 là `PH-022`. Sổ Khách A: dòng cấn trừ đi là `PH-013` (số tiếp theo sau `PH-012` của chính sổ A). Mọi câu dùng đúng mã của sổ đang xem; khi nhắc sổ bên kia thì ghi mã và tên sổ của bên đó. Dòng báo ở khung 6: "Đã ghi PH-013 ở sổ này, đi cùng PH-021 ở sổ Khách B · sầu riêng."
2. **Hủy ngay trong bảng, bỏ hộp thoại hủy.** Bấm vào ô **Số tiền trả** của dòng cấn trừ mới mở phần hủy (bấm ô Ngày trả là để sửa ngày, không cần vẽ phần sửa ngày). Phần hủy là **một dòng trải ngang cả bảng**, đặt ngay sau các dòng chuyến của tháng, gồm: câu "Hủy cấn trừ ở cả hai sổ: PH-021 ở sổ Khách B · sầu riêng và PH-013 ở sổ Khách A · sầu riêng — 50.000.000", ô `Lý do` (bắt buộc), nút `Hủy cả hai dòng` và nút `Bỏ qua`. Bấm hủy khi chưa có lý do thì hiện chữ đỏ "Nhập lý do hủy" ngay cạnh ô. Mở phần hủy từ sổ A thì câu viết PH-013 trước, PH-021 sau.
3. **Thứ tự dòng trong một tháng** (theo màn sổ đang có): dòng `THÁNG 10/2026` → các dòng chuyến → dòng hỏi lý do hủy (khi đang hủy) → dòng vết phiếu đã hủy → ô "Dán các dòng từ Sheet vào đây" → dòng `Cộng tháng`. Dòng vết **không** nằm dưới dòng Cộng tháng. Dòng vết viết gọn: "50.000.000 · 20/10/2026 · 20/10/2026 · Ghi nhầm sổ" (số tiền · ngày phiếu · ngày hủy · lý do). Cả hai sổ đều có dòng vết, mỗi sổ ở tháng của mình.
4. **Ghi xong vẫn còn ô ghi thu trống.** Ở khung 5, khung 8 và sổ B sau khi hủy: ba ô Ngày trả · Hình thức · Số tiền trả trống nằm ở hàng kế tiếp trong khối TIỀN KHÁCH TRẢ (hàng của chuyến số 2), để ghi phiếu sau.
5. **Câu lỗi ghi đủ tên sổ:** "Sổ Khách A · sầu riêng chỉ còn dư 100.000.000".
6. **Tên sổ ở đầu trang:** "Sổ khách · Khách B · sầu riêng" và "Sổ khách · Khách A · sầu riêng" (bỏ dạng `KHÁCH_B`, `KHÁCH_A`).

## Thêm khung 10 — Cấn quá số nợ

Quy tắc: cấn trừ lớn hơn số sổ nhận đang nợ thì **vẫn cho ghi**; phần thừa ở sổ nhận thành tiền khách ứng trước, số tổng còn nợ của sổ nhận thành số âm.

Vẽ: ở sổ Khách B, chọn Khách A · sầu riêng, gõ `70.000.000`, Enter. Khung xác nhận:

- câu "Cấn trừ 70.000.000 từ sổ Khách A · sầu riêng sang sổ Khách B · sầu riêng";
- Khách A · sầu riêng: `−100.000.000 → −30.000.000`;
- Khách B · sầu riêng: `50.000.000 → −20.000.000`;
- thêm một dòng ngay dưới hai ô: "Sổ Khách B · sầu riêng sẽ còn −20.000.000." Dòng này là thông tin, không phải lỗi: không tô đỏ, nút `Ghi cấn trừ` vẫn bấm được.

Thanh chuyển khung thêm nút 10.

## Không làm

- Không đổi phần nào khác của màn sổ, không thêm cột, không cuộn ngang.
- Không đổi số liệu ngoài các chỗ nêu trên; số trong mọi khung phải khớp nhau.
- Không vẽ phân quyền, nút duyệt, đính kèm chứng từ, tỷ giá.
- Không dùng tên khách thật.

## Bàn giao

- File `index.html` đủ 10 khung.
- Cuối câu trả lời, liệt kê những chỗ bạn phải tự đoán. Không tự chốt thay chủ nghiệp vụ.
