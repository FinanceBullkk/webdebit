# DOI-XE-DIEU-DO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 19/11/2026, trả lời "Đồng ý" cho câu hỏi của Claude "Lấy chặng sinh từ booking, điều xe phân công trên web làm xương sống?":

1. **Chặng là xương sống của module Đội xe.** Thu, chi, ứng và hoàn, dầu, km, lương đều gắn vào chặng hoặc vào xe.
2. **Chặng hàng sinh từ booking của HTH.** Dòng booking giao cho đội xe là một việc phải chạy. Không ai gõ lại container, kho, ngày đóng.
3. **Điều xe phân công trên web:** chọn xe, tài xế cho từng việc và thêm chặng phụ (chuyển cảng, trả rỗng, rút mooc, thả mooc).
4. Thay mặc định 1 của đợt 1 ("chặng tạo ra từ dòng chi phí", [`CHI-PHI-XE-01`](chi-phi-xe-01.md) mục 11). Chi phí ghi vào chặng đã có; dán khối từ Sheet chỉ còn là đường chuyển dữ liệu cũ.

Định hướng chung người dùng nêu cùng ngày: không mang nguyên luồng và cách làm của Sheet lên web, vì như vậy thà dùng Sheet; phải hiểu toàn bộ dữ liệu nhà xe, mối liên hệ, cách quản lý và tác động. Phân tích theo định hướng này: [Đội xe: bản đồ dữ liệu và kiến trúc](../doi-xe-kien-truc-du-lieu.md).

ĐỀ XUẤT (Claude, 19/11/2026; chưa ai chốt): cách làm ở [spec](../../specs/doi-xe-dieu-do-01.md), gồm luồng màn Điều độ, cách nối việc với chặng, cột cần thêm vào nguồn và thứ tự các bước.

## Ngày / nguồn

19/11/2026, chat. Người dùng yêu cầu Claude phân tích và kiến trúc lại dữ liệu nhà xe. Claude đọc 10 nguồn (chỉ đọc), trình bản phân tích ([PR FinanceBullkk/webdebit#494](https://github.com/FinanceBullkk/webdebit/pull/494)) rồi hỏi câu trên. Người dùng trả lời "Đồng ý".

Số đo làm căn cứ, tháng 9–11/2026, chỉ đọc (chi tiết ở spec):

- Mọi container trong tab tháng 10 của file điều xe (203) đều là dòng booking mang mã nhà xe của đội xe. Chiều ngược lại: 166/166 container mang mã đội xe ở tab booking tháng 10 có trong file điều xe.
- Ngày ở tab tháng 10 của file điều xe trùng ngày đóng hàng của booking ở 180/190 dòng đọc được cả hai ngày; lệch một ngày ở 8 dòng.
- Tab `CONT_NGUON` web đang đọc ứng từng dòng với tab booking, chỉ thiếu cột nhà xe.

## Hiệu lực và giới hạn

ĐÃ CHỐT bốn điểm trên. Chưa code, chưa đổi schema.

Chưa chốt:

- thứ tự các khối còn lại (giấy tờ, dầu và số đo, lãi lỗ, sửa chữa và định phí);
- phạm vi có gồm công nợ phải trả các nhà xe ngoài hay không;
- tài xế có tự gửi số đo và phiếu chi không;
- hai nhân viên có nhập thử tiếp theo luồng đợt 1 trong lúc chờ không;
- các câu hỏi mở của spec.

Không cấp quyền ghi Google Sheet (kể cả thêm cột vào `CONT_NGUON`), nạp dữ liệu hay chạy DDL trên `hao`: mỗi việc cần người dùng đồng ý riêng hoặc đi theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md) khi tới bước code.
