# SO-TIEN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Chốt hướng nghiệp vụ cho **sổ tiền P0-a** của blueprint vận hành tài chính v3.0 (nhập Excel sao kê cuối ngày, không kết nối ngân hàng), theo phương án đề xuất A của cả 11 câu chặn P0-a ở [sổ quyết định của spec](../../specs/van-hanh-tai-chinh/I-decision-register.md):

1. **Hướng và cách chia (QD-01):** làm theo blueprint v3.0, chia P0 thành ba bước có cổng riêng: P0-a sổ tiền nền, P0-b kiểm soát chi, P0-c nối sổ nợ.
2. **Tài khoản thí điểm (QD-02):** tài khoản VND của công ty thu cước nhiều nhất và không có tiền hàng khách Trung Quốc; chọn tài khoản cụ thể sau khi Discovery đo tỷ lệ tiền cước khách trả bằng USD.
3. **Giờ chốt (QD-04):** kế toán tải sao kê lúc 17h mỗi ngày làm việc, kỳ từ ngày làm việc trước tới hôm nay; ngày cuối của mỗi file là ngày chưa trọn.
4. **Tiền chưa rõ (QD-05):** vế "không có tiền chưa rõ chủ trên web" của [`V7-CSM`](v7-csm.md) (1) chỉ áp cho **sổ nợ**. Sổ tiền được hiện giao dịch ngân hàng chưa rõ của ai hoặc chưa rõ mục đích; khoản đó không bao giờ tự vào sổ nợ.
5. **Chia vai, agent (QD-06):** kế toán nhập và phân loại; người khác ký đối chiếu, thiếu người thì cho trùng vai nhưng có đánh dấu và chủ doanh nghiệp xem tóm tắt hằng tuần; không ai tự duyệt khoản chi của mình; Claude chỉ triển khai phần mềm, **không ghi, nạp hay sửa dữ liệu nghiệp vụ của sổ tiền** — thu hẹp [`TU-LAM-01`](tu-lam-01.md) cho phần này.
6. **File sao kê (QD-07):** dùng đúng file tải từ ngân hàng (.xlsx hoặc CSV), không mở rồi lưu lại bằng Excel. Nếu ngân hàng chỉ xuất `.xls` cũ thì quay lại câu này để chọn bộ đọc riêng.
7. **Bảo vệ dữ liệu (QD-08):** lưu file gốc trong hệ thống; chỉ kế toán và người đối chiếu mở được dòng gốc, nội dung chuyển khoản; mã hóa mọi bản sao lưu, kể cả bản trên `hao`; ghi lại ai đã mở; thời hạn lưu theo quy định kế toán.
8. **Sổ chính thức (QD-09):** sổ tiền là sổ quản trị; sổ kế toán chính thức vẫn ở phần mềm kế toán hiện tại; kế toán nhận file CSV để đối chiếu.
9. **Số dư mở (QD-10):** bắt đầu từ ngày đầu một tháng dương lịch, giờ VN; số dư lấy từ sao kê ngày trước; người khác kế toán tự tải sao kê để đối chiếu.
10. **Danh mục (QD-11):** các loại có sẵn (cước khách, chuyển nội bộ, rút quỹ, phí ngân hàng, Đội xe, tiền hàng chờ sổ riêng…) cộng 10–15 mục chi do kế toán chọn.
11. **Ký đối chiếu (QD-24):** kế toán ký mỗi ngày (có đánh dấu vì là người nhập), chủ doanh nghiệp xem tóm tắt mỗi tuần, người khác kế toán tự tải sao kê đối chiếu mỗi tháng.

## Ngày / nguồn

24/11/2026, 13:50 giờ VN: người dùng lưu câu trả lời trên trang riêng tư "Chốt sổ tiền P0" với vai **Chủ doanh nghiệp**, chọn phương án A (đề xuất) cho cả 11 câu, không ghi chú; rồi báo trong chat "đã lưu câu trả lời". Vai Kế toán chưa lưu câu trả lời riêng. Phương án, lý do và đánh đổi của từng câu ở [I-decision-register](../../specs/van-hanh-tai-chinh/I-decision-register.md); thiết kế ở [bộ tài liệu vận hành tài chính](../../specs/van-hanh-tai-chinh/README.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng nghiệp vụ cho P0-a. **Chưa code, chưa migration, chưa có dữ liệu.** Thiết kế kỹ thuật (ADR-TIEN-01…18 ở [F2](../../specs/van-hanh-tai-chinh/F2-adr.md)) vẫn là ĐỀ XUẤT tới PR migration P0-a; các điểm trên chốt phần nghiệp vụ của ADR-TIEN-01 (8), 08 (5), 12 (3), 17 (6), 18 (1).

CÒN MỞ, chờ kế toán xác nhận ở bước Discovery: tài khoản cụ thể (2); định dạng file VCB thật, mã giao dịch có ổn định không (6); thời hạn lưu (7); tên phần mềm kế toán và định dạng CSV muốn nhận (8); ngày bắt đầu và số dư mở có bằng chứng (9); danh sách mục chi (10). Các câu chặn P0-b, P0-c, P1 (QD-03, QD-12…QD-23, QD-25, QD-26) chưa chốt.

Sửa phạm vi: [`V7-CSM`](v7-csm.md) (1) theo điểm 4; [`TU-LAM-01`](tu-lam-01.md) theo điểm 5. Không đổi luật tiền, dữ liệu hay quyền của sổ nợ.
