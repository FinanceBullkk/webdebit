# CHI-PHI-XE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng trả lời trong chat ngày 18/11/2026 (ĐÃ CHỐT phạm vi):

1. 18 xe nhóm VTP và NSX là **xe của công ty**. 5 xe nhóm Trần Hùng là **nhà xe thuê ngoài**; người dùng chỉ ra đó là 5 xe cuối trong danh sách xe ở file điều xe (tab THONG TIN CHUNG).
2. Chiều nợ ở file "Công nợ cảng" tháng: **công ty hàng nợ đội xe** (bảng kê cước đội xe gửi công ty hàng).
3. Việc làm trước trên web: **chi phí tài xế + ứng**. Công nợ cước, lương chuyến và lãi lỗ từng xe làm sau.
4. Người nhập chi phí: **hai nhân viên văn phòng** như hiện nay. Tài xế không nhập ở đợt đầu.
5. Ứng tiền **cho từng tài xế**.
6. Công ty hoàn tiền tài xế đã chi **theo đợt, gộp vài chuyến một lần**.
7. Lương chuyến **chưa làm** ở đợt đầu.
8. Số dư mỗi tài xế = **tổng tài xế chi − tổng đã hoàn − tổng đã ứng**, một số dư chung cho mỗi tài xế. Dương: công ty còn nợ tài xế; âm: tài xế còn giữ tiền ứng.
9. **Mục tiêu:** web giúp công ty quản lý chi phí vận hành đội xe, có đủ dữ liệu để phân tích vì sao xe chạy không có lời. Phải phân biệt rõ khoản nào vào debit, khoản nào là chi phí.
10. **Nhập liệu đội xe trên web**, thay các Sheet rời; không làm đồng bộ từ các Sheet chi phí cũ.
11. **Bốn mặc định cho đợt 1** (mục "Mặc định cho đợt 1" của spec), người dùng đồng ý khi giao việc: "code và mockup lên canvas cho mình test trước":
    - Chặng tạo ra từ dòng chi phí.
    - Tiền theo người nhận ứng; chặng và chi phí theo phương tiện.
    - Khóa tháng như sổ khách.
    - Bản thử dùng dữ liệu sao chép tháng 10–11/2026.

    Trước khi code giao diện, dựng mockup bấm thử được trên canvas để người dùng test.

ĐỀ XUẤT (Claude, 18/11/2026; người dùng chưa phản đối):

- Làm trong repo và cơ sở dữ liệu hiện có, schema PostgreSQL riêng, không lập dự án mới. Lý do: chặng chở hàng nối được với chuyến khách theo container (đo tháng 10: 123/123 chặng hàng của Tín Phát có trong `CONT_NGUON`), và dùng chung đăng nhập, triển khai, backup.
- Chạy song song với Sheet một tháng để so số, rồi bỏ Sheet.
- Mô hình chặng – dòng thu – dòng chi – định phí xe theo [spec](../../specs/chi-phi-xe-01.md#mô-hình-dữ-liệu-đề-xuất).

Đính chính 18/11/2026: lúc đầu Claude nói ô `carrier` của chuyến trên web là nhà xe. Sai: ô đó là hãng tàu. Web hiện chưa biết xe nào chở container nào.

## Ngày / nguồn

18/11/2026, chat với người dùng sau khi Claude đọc 5 nguồn dữ liệu đội xe (chỉ đọc). Spec: [`specs/chi-phi-xe-01.md`](../../specs/chi-phi-xe-01.md).

## Hiệu lực và giới hạn

Chốt mục tiêu, phạm vi, nhập trên web, việc làm trước và công thức số dư. Chưa chốt khóa tháng, mốc bắt đầu, nguồn dầu, lương, định phí, thứ tự đợt 2–3: xem Câu hỏi mở trong spec. Không cấp quyền nạp dữ liệu thật, chạy DDL hay ghi Sheet.
