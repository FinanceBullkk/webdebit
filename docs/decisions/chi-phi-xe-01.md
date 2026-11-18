# CHI-PHI-XE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng trả lời trong chat ngày 18/11/2026 (ĐÃ CHỐT phạm vi):

1. 18 xe nhóm VTP và NSX là **xe của công ty**. 5 xe nhóm Trần Hùng là **nhà xe thuê ngoài**.
2. Chiều nợ ở file "Công nợ cảng" tháng: **công ty hàng nợ đội xe** (bảng kê cước đội xe gửi công ty hàng).
3. Việc làm trước trên web: **chi phí tài xế + ứng**. Công nợ cước, lương chuyến và lãi lỗ từng xe làm sau.
4. Người nhập chi phí: **hai nhân viên văn phòng** như hiện nay. Tài xế không nhập ở đợt đầu.
5. Ứng tiền **cho từng tài xế**.
6. Công ty hoàn tiền tài xế đã chi **theo đợt, gộp vài chuyến một lần**.
7. Lương chuyến **chưa làm** ở đợt đầu.

ĐỀ XUẤT (Claude, 18/11/2026; người dùng chưa phản đối): làm trong repo và cơ sở dữ liệu hiện có, schema PostgreSQL riêng, không lập dự án mới. Lý do: dùng chung chuyến/container, đăng nhập, triển khai, backup với sổ khách.

## Ngày / nguồn

18/11/2026, chat với người dùng sau khi Claude đọc 5 nguồn dữ liệu đội xe (chỉ đọc). Spec: [`specs/chi-phi-xe-01.md`](../../specs/chi-phi-xe-01.md).

## Hiệu lực và giới hạn

Chỉ chốt phạm vi và thứ tự. Chưa chốt công thức số dư, khóa tháng, sổ theo tài xế hay theo xe, mốc bắt đầu: xem Câu hỏi mở trong spec. Không cấp quyền nạp dữ liệu thật, chạy DDL hay ghi Sheet.
