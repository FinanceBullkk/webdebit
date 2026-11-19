# DOI-XE-CAU-TRUC-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 19/11/2026, trả lời "Chốt theo hướng A" sau khi đọc bản audit module Đội xe của Claude:

1. **Module Đội xe chia màn theo đối tượng nghiệp vụ, không theo file Sheet nguồn.** Mỗi đối tượng có một nhà; màn khác chỉ dẫn link tới, không có bản nhập và sửa thứ hai.
2. **Năm mục:**
   - **Chặng:** một danh sách chặng của cả đội, một phiếu chặng gồm phân công, chi, thu và lãi gộp; việc dở là hàng chờ ở đầu màn.
   - **Công nợ:** một sổ cùng cấu trúc cho mọi đối tác (tài xế, người đi lệnh, HTH; về sau nơi bán dầu, gara, nhà xe thuê).
   - **Xe:** hồ sơ, chi phí theo xe, hiệu suất.
   - **Lãi lỗ:** theo tuyến, xe, tháng.
   - **Thiết lập:** xe, người, tuyến và giá, một danh mục khoản dùng chung cho thu và chi.
3. **Màn bị thay:** màn Điều độ riêng, bảng chi phí trong sổ người, sổ xe, bảng chặng của trang Bảng kê, tab Bảng giá. Gỡ từng màn sau khi mục thay nó được nghiệm thu, không gỡ trước.
4. **Hướng đổi mô hình dữ liệu đi kèm:** người trả theo từng khoản chi; khoản thu phát sinh là dòng riêng, không đọc từ ghi chú chữ; một cơ chế công nợ chung trước khi thêm dầu, gara; chi phí gắn được vào xe, không chỉ vào chặng.
5. **Cách làm:** phiên audit làm điều phối; các phiên thực thi chạy Sonnet 5.5, effort high.

Cách chia gói việc, thứ tự và phạm vi file: [spec](../../specs/doi-xe-cau-truc-01.md).

## Quan hệ với quyết định trước

- [`DOI-XE-DIEU-DO-01`](doi-xe-dieu-do-01.md): giữ nguyên. Chặng vẫn sinh từ booking, điều xe vẫn phân công trên web. Chỉ đổi chỗ đặt: phân công là một phần của mục Chặng, không phải một màn riêng.
- [`CHI-PHI-XE-01`](chi-phi-xe-01.md) mục 12 (màn Đội xe hai bảng, sổ người, sổ xe) và [`DOI-XE-THU-01`](doi-xe-thu-01.md) mục 3 (trang Bảng kê theo tháng): bị thay về **cấu trúc màn**.
- **Luật tiền giữ nguyên** tới khi có quyết định riêng: công thức số dư, hoàn theo đợt, hủy bắt buộc lý do, khóa tháng, bảng kê gửi → đối chiếu → tiền về, chi hộ.

## Ngày / nguồn

19/11/2026, chat. Người dùng nêu module "có nhiều màn nhưng system design và luồng dùng chưa hiệu quả", "cóp nhặt y chang từ Google Sheet", "chưa MECE", và yêu cầu audit. Claude đọc spec, quyết định, schema, code và mở năm màn trên `hao` (bản thử tháng 10–11/2026, chỉ đọc), rồi trình hai hướng: A theo đối tượng, B theo vai người dùng. Người dùng chọn A.

Số đo làm căn cứ (bản thử tháng 10/2026 trên `hao`, chỉ đọc; chi tiết ở spec):

- Sổ xe và sổ tài xế cùng có 206 chặng; 14/16 cặp xe–tài xế có đúng cùng tập dòng; không chặng nào có người trả khác tài xế.
- Trang Bảng kê liệt kê lại đúng 206 chặng đó.
- Cách xem Đủ cột có 33 cột, rộng 3.106px trên khung 1.241px.
- Danh mục khoản chi có 16 khoản, danh mục khoản thu có 14 khoản, nối được 10.

## Hiệu lực và giới hạn

ĐÃ CHỐT cấu trúc năm mục, danh sách màn bị thay và hướng đổi mô hình (điểm 1–5). Chưa code.

Chưa chốt:

- luật tiền chi tiết của mô hình mới (người trả theo khoản, khoản thu dòng riêng, công nợ chung, chi theo xe): ĐỀ XUẤT sẽ viết ở spec riêng, người dùng chốt trước khi code;
- bố cục từng mục: chốt sau khi người dùng thử bản bấm thử;
- thứ tự làm Công nợ, Xe, Lãi lỗ, Thiết lập sau mục Chặng.

Chưa hỏi điều xe, hai nhân viên và kế toán. Không cấp quyền nạp dữ liệu, ghi Google Sheet hay chạy DDL trên `hao`: mỗi việc theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md) hoặc cần người dùng đồng ý riêng.
