# ANH-GEMINI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 20/11/2026: **ảnh của các nhóm Zalo đã chọn lên web được đọc bằng OCR tại máy có Zalo; chỉ ảnh OCR đọc không chắc mới gửi ra Gemini.** Quyết định này sửa [`CHUNG-TU-01`](chung-tu-01.md) mục 4 và câu Q4 của [`ZALO-THU-CHI-01`](zalo-thu-chi-01.md), chỉ cho đường Zalo.

Bản chốt đầu cùng ngày gửi mọi ảnh ra Gemini. Sau khi P0 đo OCR tại máy đọc đúng 20/20 ảnh, người dùng đổi sang OCR làm chính ([mục sửa](#sửa-ngày-20112026-ocr-chính-gemini-khi-cần)).

1. **OCR tại máy đọc mọi ảnh** của nhóm đã chọn theo [`ZALO-GROUP-01`](zalo-group-01.md) (lệnh `add` ở máy có Zalo). OCR chạy nền, giới hạn luồng để không làm chậm máy. Ảnh của nhóm chưa chọn không được đọc.
2. **Khi nào gửi Gemini:** ảnh có dấu hiệu tiền (từ khóa ngân hàng, hoặc số kèm VND/đ) nhưng OCR không đọc ra số tiền, hoặc đọc ra mà độ tin cậy thấp. Ảnh không có dấu hiệu tiền (ảnh cont, seal, nhiệt độ…) **không rời máy**.
3. **Hai đường, mỗi ảnh cần gửi thì gửi cả hai:**
   - proxy 9router dùng Gemini OAuth của tài khoản Google cá nhân;
   - Gemini API trả phí.
4. **Thứ tự tin:**
   - OCR đọc chắc → dùng số của OCR;
   - không thì hai đường Gemini cùng ra một số → dùng số đó;
   - còn lại (lệch, hoặc một đường lỗi) → đưa người xem.

   Không đường Gemini nào tự quyết một mình.
5. **Kết quả chỉ đọc.** Số Gemini đọc được chỉ để hiện và đối chiếu, **không bao giờ ghi tiền**, không đổi phân bổ hay tháng khóa (giữ `ZALO-THU-CHI-01` mục 3).
6. **Ngoài phạm vi:** ảnh dán vào phiếu thu trên web (`CHUNG-TU-01` mục 1–3) vẫn không gửi ra ngoài `hao`. Chữ của tin nhắn không gửi ra Gemini; trang Thu chi vẫn đọc mẫu `thu|chi|ứng` tại chỗ.

## Ràng buộc kỹ thuật

- Khóa API và địa chỉ proxy chỉ nằm trên máy có Zalo, ngoài repo, ngoài nhật ký.
- Ảnh thu nhỏ trước khi gửi. Không gửi kèm tên nhóm, tên người gửi hay chữ của tin.
- Mỗi lần gửi ghi một dòng log tại máy có Zalo: mã ảnh (sha256), đường, giờ, kết quả hoặc mã lỗi. Không ghi nội dung ảnh hay chữ đọc được vào log.
- Một cờ cấu hình tắt hẳn việc gửi ra ngoài. Tắt thì trang vẫn chạy, chỉ thiếu số đọc từ ảnh.
- Đặt hạn mức chi tiêu cho khóa API trả phí ở phía Google.

## Rủi ro đã nêu, người dùng chấp nhận

Claude nêu trong chat trước khi người dùng chốt:

- Đường OAuth cá nhân đi theo điều khoản tài khoản cá nhân. Nội dung gửi lên có thể được Google dùng để cải thiện sản phẩm; API trả phí thì không.
- Proxy dùng token OAuth của công cụ khác có thể làm Google giới hạn hoặc khóa tài khoản. Đường này cũng dễ gãy khi token hết hạn.
- Proxy là thêm một bên nhìn thấy ảnh.
- Ảnh chuyển khoản có số tài khoản và tên người chuyển, người nhận.
- (Bản chốt đầu) Gửi mọi ảnh, không lọc trước, nghĩa là cả ảnh cont/seal và ảnh không liên quan tiền cũng ra ngoài. Nhóm nhiều ảnh nhất đo được khoảng 580 ảnh mỗi tuần (P0, 20/11/2026). Rủi ro này hết khi đổi sang OCR làm chính.

## Ngày / nguồn

20/11/2026, chat, trong lúc chạy P0 của `ZALO-THU-CHI-01`. Người dùng hỏi OCR có gọi model khác được không. Claude liệt kê các engine tại máy và AI ngoài, đề xuất đo OCR tại máy trước. Người dùng đề nghị gọi API Gemini, rồi đề nghị dùng proxy 9router (Gemini OAuth). Claude khuyên API trả phí làm đường chính, proxy chỉ để thử. Người dùng chọn "dùng cả 2", rồi trả lời hai câu hỏi: "Chạy cả hai rồi so" và "Mọi ảnh của nhóm đã chọn".

## Sửa ngày 20/11/2026: OCR chính, Gemini khi cần

P0 mục 3 đo trên máy có Zalo: easyocr đọc 20 ảnh chuyển khoản mới nhất, người dùng tự chấm trên trang soát tại máy, **đúng 20/20**. Máy (CPU 6 nhân, không GPU rời) đọc khoảng 7,5 giây mỗi ảnh khi dùng 6 luồng, 14 giây khi giới hạn 2 luồng. Lượng ảnh của nhóm đang lên web khoảng 1 ảnh mỗi ngày.

Người dùng hỏi máy có yếu quá để OCR tại chỗ không. Claude báo số đo trên và đề xuất OCR làm chính, Gemini chỉ cho ảnh OCR đọc không chắc. Người dùng chọn "OCR chính, Gemini khi cần". Mục 1–4 ở trên là bản đã sửa.

## Hiệu lực và giới hạn

ĐÃ CHỐT 20/11/2026 (bản sửa cùng ngày). Chưa code, chưa triển khai. Làm ở PR-4 của [spec Thu chi](../../specs/zalo-thu-chi-real-time.md#chia-pr-và-cổng).

CÒN MỞ:

- ngưỡng "độ tin cậy thấp" của OCR, chốt bằng dữ liệu khi code PR-4;
- model Gemini cụ thể và hạn mức chi tiêu;
- địa chỉ proxy 9router chạy ở máy nào;
- nếu hai đường Gemini thường xuyên lệch nhau thì xử lý thế nào.
