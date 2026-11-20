# ANH-GEMINI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 20/11/2026: **ảnh của các nhóm Zalo đã chọn lên web được gửi ra Gemini để đọc.** Quyết định này sửa [`CHUNG-TU-01`](chung-tu-01.md) mục 4 và câu Q4 của [`ZALO-THU-CHI-01`](zalo-thu-chi-01.md), chỉ cho đường Zalo.

1. **Phạm vi ảnh:** mọi ảnh của nhóm đã chọn theo [`ZALO-GROUP-01`](zalo-group-01.md) (lệnh `add` ở máy có Zalo). Không lọc trước tại máy. Ảnh của nhóm chưa chọn không bao giờ rời máy.
2. **Hai đường, mỗi ảnh gửi cả hai:**
   - proxy 9router dùng Gemini OAuth của tài khoản Google cá nhân;
   - Gemini API trả phí.
3. **So hai kết quả:** hai đường cùng đọc ra một số tiền thì coi là máy đọc được. Lệch, hoặc một đường lỗi, thì đưa người xem. Không đường nào tự quyết một mình.
4. **Kết quả chỉ đọc.** Số Gemini đọc được chỉ để hiện và đối chiếu, **không bao giờ ghi tiền**, không đổi phân bổ hay tháng khóa (giữ `ZALO-THU-CHI-01` mục 3).
5. **Ngoài phạm vi:** ảnh dán vào phiếu thu trên web (`CHUNG-TU-01` mục 1–3) vẫn không gửi ra ngoài `hao`. Chữ của tin nhắn không gửi ra Gemini; trang Thu chi vẫn đọc mẫu `thu|chi|ứng` tại chỗ.

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
- Gửi mọi ảnh, không lọc trước, nghĩa là cả ảnh cont/seal và ảnh không liên quan tiền cũng ra ngoài. Nhóm nhiều ảnh nhất đo được khoảng 580 ảnh mỗi tuần (P0, 20/11/2026).

## Ngày / nguồn

20/11/2026, chat, trong lúc chạy P0 của `ZALO-THU-CHI-01`. Người dùng hỏi OCR có gọi model khác được không. Claude liệt kê các engine tại máy và AI ngoài, đề xuất đo OCR tại máy trước. Người dùng đề nghị gọi API Gemini, rồi đề nghị dùng proxy 9router (Gemini OAuth). Claude khuyên API trả phí làm đường chính, proxy chỉ để thử. Người dùng chọn "dùng cả 2", rồi trả lời hai câu hỏi: "Chạy cả hai rồi so" và "Mọi ảnh của nhóm đã chọn".

## Hiệu lực và giới hạn

ĐÃ CHỐT 20/11/2026. Chưa code, chưa triển khai. Bước đầu là P0 mục 3: thử OCR tại máy và hai đường Gemini trên cùng 20 ảnh chuyển khoản. Người dùng chấm đúng/sai trên trang soát mở tại máy có Zalo.

CÒN MỞ:

- model Gemini cụ thể và hạn mức chi tiêu;
- địa chỉ proxy 9router chạy ở máy nào;
- nếu hai đường thường xuyên lệch nhau thì xử lý thế nào;
- có giữ OCR tại máy làm phiếu thứ ba hay không.
