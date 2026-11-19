# DOI-XE-DIEU-DO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 19/11/2026, trả lời "Đồng ý" cho câu hỏi của Claude "Lấy chặng sinh từ booking, điều xe phân công trên web làm xương sống?":

1. **Chặng là xương sống của module Đội xe.** Thu, chi, ứng và hoàn, dầu, km, lương đều gắn vào chặng hoặc vào xe.
2. **Chặng hàng sinh từ booking của HTH.** Dòng booking giao cho đội xe là một việc phải chạy. Không ai gõ lại container, kho, ngày đóng.
3. **Điều xe phân công trên web:** chọn xe, tài xế cho từng việc và thêm chặng phụ (chuyển cảng, trả rỗng, rút mooc, thả mooc).
4. Thay mặc định 1 của đợt 1 ("chặng tạo ra từ dòng chi phí", [`CHI-PHI-XE-01`](chi-phi-xe-01.md) mục 11). Chi phí ghi vào chặng đã có; dán khối từ Sheet chỉ còn là đường chuyển dữ liệu cũ.

Định hướng chung người dùng nêu cùng ngày: không mang nguyên luồng và cách làm của Sheet lên web, vì như vậy thà dùng Sheet; phải hiểu toàn bộ dữ liệu nhà xe, mối liên hệ, cách quản lý và tác động. Phân tích theo định hướng này: [Đội xe: bản đồ dữ liệu và kiến trúc](../doi-xe-kien-truc-du-lieu.md).

Người dùng chốt thêm ngày 19/11/2026, trong chat, chọn theo đề xuất của bản bấm thử màn Điều độ (bước 2) mà chưa bấm thử:

5. **Luồng màn Điều độ theo đề xuất của bản thử:** chưa có số container thì chưa phân xe được; seal, nhiệt độ, tên tàu chỉ xem; việc bị giao nhà xe khác thì người dùng chọn Giữ (thành chặng ngoài booking) hoặc Bỏ chặng; chặng đã có phí, đã hoàn hoặc đã lên bảng kê đã gửi thì màn Điều độ không đổi, không bỏ, chỉ chỉ đường sang sổ tài xế hoặc Bảng kê; việc cũ còn chờ nằm trên cùng.
6. **Bố cục:** A (theo việc) là mặc định; thêm chế độ B (theo xe) chỉ để xem.
7. **Cột nhà xe vào nguồn theo cách A:** thêm cột vào tab `CONT_NGUON`. Claude đã sửa tab ngày 19/11/2026 (thêm bốn cột cuối: Nhà xe, Số seal, Nhiệt độ, Tên tàu); bộ đọc của web chưa đọc bốn cột này.
8. **Mã nhà xe:** dùng hai mã đã đo. Mã thật chỉ nạp vào cơ sở dữ liệu trên `hao`, không có trong repo; test dùng mã giả.

Cùng ngày người dùng chốt [`DOI-XE-CAU-TRUC-01`](doi-xe-cau-truc-01.md): Đội xe chia màn theo đối tượng, không còn màn Điều độ riêng. Phân công là một phần của mục Chặng; chỗ "chỉ đường sang sổ tài xế hoặc Bảng kê" ở điểm 5 được thay bằng mục Chặng và phiếu chặng, bố cục ở điểm 6 do mục Chặng quyết lại. Hành vi phân công đã chốt (luật ở điểm 5, điểm 7, điểm 8) giữ nguyên.

Mô hình dữ liệu và thứ tự các bước (Claude, theo định hướng đã chốt): ở [spec](../../specs/doi-xe-dieu-do-01.md). Cách làm của bước 3 phần 1 (schema, lệnh ghi, harness) ĐÃ VIẾT, chưa triển khai.

## Ngày / nguồn

19/11/2026, chat. Người dùng yêu cầu Claude phân tích và kiến trúc lại dữ liệu nhà xe. Claude đọc 10 nguồn (chỉ đọc), trình bản phân tích ([PR FinanceBullkk/webdebit#494](https://github.com/FinanceBullkk/webdebit/pull/494)) rồi hỏi câu trên. Người dùng trả lời "Đồng ý".

Số đo làm căn cứ, tháng 9–11/2026, chỉ đọc (chi tiết ở spec):

- Mọi container trong tab tháng 10 của file điều xe (203) đều là dòng booking mang mã nhà xe của đội xe. Chiều ngược lại: 166/166 container mang mã đội xe ở tab booking tháng 10 có trong file điều xe.
- Ngày ở tab tháng 10 của file điều xe trùng ngày đóng hàng của booking ở 180/190 dòng đọc được cả hai ngày; lệch một ngày ở 8 dòng.
- Tab `CONT_NGUON` web đang đọc ứng từng dòng với tab booking, chỉ thiếu cột nhà xe.

## Hiệu lực và giới hạn

ĐÃ CHỐT tám điểm trên. ĐÃ VIẾT (chưa triển khai trên `hao`, chưa ai nghiệm thu): migration `2026-11-19-v7-doi-xe-dieu-do.sql` (schema `doixe`), harness `test_pg_doixe_dieu_do.py`. Chưa có API, phần phân công trong mục Chặng, mã nhà xe nào trong cơ sở dữ liệu; bộ đọc của web chưa đọc bốn cột mới của `CONT_NGUON`.

Chưa chốt:

- thứ tự các khối còn lại (giấy tờ, dầu và số đo, lãi lỗ, sửa chữa và định phí);
- phạm vi có gồm công nợ phải trả các nhà xe ngoài hay không;
- tài xế có tự gửi số đo và phiếu chi không;
- hai nhân viên có nhập thử tiếp theo luồng đợt 1 trong lúc chờ không;
- chuyển cảng phát sinh khi nào và ai quyết (câu 4 của spec), thiết bị và số người dùng (câu 5), "người trả theo từng khoản chi" (câu 7).

Không cấp quyền ghi Google Sheet (kể cả thêm cột vào `CONT_NGUON`), nạp dữ liệu hay chạy DDL trên `hao`: mỗi việc cần người dùng đồng ý riêng hoặc đi theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md) khi tới bước code.
