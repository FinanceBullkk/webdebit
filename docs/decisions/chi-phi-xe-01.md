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
    - Chặng tạo ra từ dòng chi phí. (**Thay 19/11/2026** bởi [`DOI-XE-DIEU-DO-01`](doi-xe-dieu-do-01.md): chặng hàng sinh từ booking, điều xe phân công trên web. Bản đang chạy trên `hao` vẫn theo mặc định cũ tới khi code bước mới.)
    - Tiền theo người nhận ứng; chặng và chi phí theo phương tiện.
    - Khóa tháng như sổ khách.
    - Bản thử dùng dữ liệu sao chép tháng 10–11/2026.

    Trước khi code giao diện, dựng mockup bấm thử được trên canvas để người dùng test.

12. **Màn Đội xe đợt 1 theo bản bấm thử** (canvas Claude Design, trang "Đội xe"): người dùng thử rồi bấm "Chốt, code đi" trong chat ngày 18/11/2026. Bảy câu ở ô tím của canvas chốt theo đúng cách bản thử đang làm. Chi tiết luồng ở spec, mục [Người dùng và luồng đợt 1](../../specs/chi-phi-xe-01.md#người-dùng-và-luồng-đợt-1-bước-1):
    1. Màn Đội xe có hai bảng. **Người nhận ứng:** số dòng chưa hoàn, hai cột "Công ty còn nợ" và "Đang giữ tiền ứng" thay cho số âm, người công ty nợ nhiều xếp đầu. **Xe:** biển số, tài xế đang chạy, số chặng và số chặng chưa có phí theo tháng chọn; chia nhóm xe công ty và xe thuê ngoài (xe thuê chưa có sổ ở đợt 1). Một ô tìm theo tên hoặc số biển.
    2. Hai loại sổ: **sổ người** (ứng, hoàn, số dư) và **sổ xe** (mọi chặng của xe, ai trả cũng hiện, không có ứng/hoàn). Đổi người hoặc xe bằng ô gõ tìm ngay ở tên.
    3. Thẻ tiền của sổ người viết như sổ: số dư đầu tháng + tài xế chi − đã hoàn − đã ứng = số dư; dòng cuối ghi bằng chữ ("Công ty còn nợ …" hoặc "… đang giữ tiền ứng"). Liệt kê các lần ứng và đợt hoàn trong tháng; khoản đã hủy vẫn hiện, gạch ngang, kèm lý do.
    4. Bảng chi phí kiểu Sheet, mỗi dòng một chặng. Cách xem **Gọn**: 5 loại phí dùng nhiều nhất + "Phí khác". **Đủ cột**: 14 cột phí như Sheet, nơi lấy, nơi hạ, kho, người trả, chuyến khách, ghi chú. VETC tô xám, không vào phần hoàn. Có cột Tình trạng và ba lọc nhanh: Chưa hoàn, Chưa nối chuyến khách, Chưa có phí.
    5. **Nhập:** luôn có một hàng trống; gõ rồi Enter thành dòng nháp, con trỏ về ô Ngày. **Dán** khối chép từ tab tài xế: đủ 29 cột hoặc bắt đầu từ cột NGÀY, thứ tự cột như spec. Loại chặng đoán từ ghi chú, mặc định Hàng. Lưu chỉ lưu dòng hết lỗi; ô lỗi giữ nguyên chữ đã dán. **Chặn:** ngày sau hôm nay (giờ VN); tiền lẻ, âm hoặc không phải số; có tiền mà thiếu ngày hoặc container; chưa rõ xe; trùng chặng (ngày + container + loại + xe; dán lại cùng khối không tạo trùng). Cột tổng của Sheet khác tổng web tính thì chỉ cảnh báo.
    6. Chặng hàng tự nối chuyến khách theo container, lệch không quá 10 ngày: dấu ✓ (rê chuột thấy khách, ngày, tuyến) hoặc cờ "chưa nối". Tuyến trống thì lấy từ chuyến khách.
    7. **Ghi ứng:** số tiền (kèm đọc chữ), ngày chuyển không sau hôm nay, ghi chú; thấy số dư trước → sau; nút ghi kèm số tiền; bấm hai lần chỉ ghi một.
    8. **Hoàn theo đợt:** bảng chỉ còn dòng chưa hoàn của mọi tháng, tích sẵn; số tiền thực chuyển mặc định bằng tổng, sửa được. Khác tổng thì báo: chuyển ít hơn là trừ vào tiền ứng đang giữ, nhiều hơn là như ứng thêm. Có nút nhanh "Trừ tiền ứng đang giữ: chuyển …"; cho chuyển 0 (quyết toán trừ hết vào ứng, cách người đi lệnh đang làm). Dòng đã hoàn ghi "Đã hoàn dd/mm". Số dư vẫn theo công thức ở mục 8.
    9. Hủy lần ứng hoặc đợt hoàn **bắt buộc lý do**; hủy đợt hoàn thì các dòng trở lại chưa hoàn.
    10. **Khóa tháng chung cả đội xe**, mặc định chỉ tháng hiện tại (giờ VN) mở; mở hay khóa đều ghi Lịch sử. Tháng khóa hoặc dòng đã hoàn: sửa tiền không ghi đè mà thêm dòng điều chỉnh (dòng mới, chờ hoàn); xóa chặng thì gạch ngang và thêm dòng trừ lại. Sửa chữ (ngày, container, loại, xe, nơi) ghi đè, có Lịch sử; không chuyển chặng vào hay ra tháng khóa; không đổi người trả khi tháng khóa hoặc dòng đã hoàn.
    11. Người trả theo dòng: tài xế (mặc định), công ty, người đi lệnh. Dòng người khác trả hiện xám trong sổ tài xế, không cộng vào "Tài xế chi".
    12. Nổ máy phát tính vào phần hoàn tài xế. "Chưa có phí" là chặng chưa có khoản nào, kể cả VETC.

ĐỀ XUẤT (Claude, 18/11/2026; người dùng chưa phản đối):

- Làm trong repo và cơ sở dữ liệu hiện có, schema PostgreSQL riêng, không lập dự án mới. Lý do: chặng chở hàng nối được với chuyến khách theo container (đo tháng 10: 123/123 chặng hàng của Tín Phát có trong `CONT_NGUON`), và dùng chung đăng nhập, triển khai, backup.
- Chạy song song với Sheet một tháng để so số, rồi bỏ Sheet.
- Mô hình chặng – dòng thu – dòng chi – định phí xe theo [spec](../../specs/chi-phi-xe-01.md#mô-hình-dữ-liệu-đề-xuất).

Đính chính 18/11/2026: lúc đầu Claude nói ô `carrier` của chuyến trên web là nhà xe. Sai: ô đó là hãng tàu. Web hiện chưa biết xe nào chở container nào.

## Ngày / nguồn

18/11/2026, chat với người dùng sau khi Claude đọc 5 nguồn dữ liệu đội xe (chỉ đọc). Mục 12: cùng ngày, người dùng bấm thử bản trên canvas rồi trả lời "Chốt, code đi". Spec: [`specs/chi-phi-xe-01.md`](../../specs/chi-phi-xe-01.md).

## Hiệu lực và giới hạn

Chốt mục tiêu, phạm vi, nhập trên web, việc làm trước, công thức số dư và luồng màn Đội xe đợt 1 (mục 12, gồm khóa tháng chung cả đội xe). Chưa chốt mốc bắt đầu chạy thật, số dư đầu từng người, nguồn dầu, lương, định phí, thứ tự đợt 2–3: xem Câu hỏi mở trong spec. Không cấp quyền nạp dữ liệu thật hay bản sao lên `hao`, ghi Sheet: mỗi lần cần người dùng đồng ý riêng. Migration của schema `doixe` triển khai tay theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md).

Phiếu chi xe mới của nhà xe (từ 11/2026): 18/11/2026 người dùng chốt làm phần chắc chắn: loại phí Hạ sớm/KH (tài xế chi), ba ô số lượng của chặng (km, ngày neo, giờ máy phát; không phải tiền), dán ô Nổ máy ghi giờ thành số giờ. Dòng Hoá đơn, đổi cột Sheet, cont cắt + cont kéo CÒN MỞ: xem [spec](../../specs/chi-phi-xe-01.md#phiếu-chi-xe-mới-từ-112026).

Triển khai: schema `doixe` ĐÃ TRIỂN KHAI trên `hao` 18/11/2026 lúc 12:17 ([nhật ký](../deploys/2026-11-18-doi-xe.md)), bảng rỗng, chưa nạp danh mục. API `/api/v7/doixe/*` triển khai tự động khi merge qua `Deploy hao`.
