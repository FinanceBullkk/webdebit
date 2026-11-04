# TRANG-KHACH-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt trang khách V7 theo spec [`v7-trang-khach.md`](../../specs/v7-trang-khach.md). Kiến trúc như sau:
- Sổ khách mở rộng thành trang khách, không tạo trang thứ hai. Địa chỉ giữ là `so-khach-v7-live.html?customer=`, thêm tham số `the=`.
- Bốn thẻ: **Tình hình · Sổ · Trao đổi · Hồ sơ**.
- Đầu trang một dòng, cao ≤ 44px, thay đúng dòng đầu sổ của [`SO-GON-04`](so-gon-04.md) L7.
- Thẻ Sổ là SO-GON-04, không đổi.
- Ba giai đoạn: **A** dùng dữ liệu và API có sẵn; **B** thêm bảng ngoài đường tiền; **C** gộp sổ theo khách.

Người dùng lấy đúng phương án Claude đề xuất cho tám câu:

1. **K1 · Theo sổ hay theo khách:** trang khách theo **sổ** ở giai đoạn A và B. Gộp các sổ của cùng khách để giai đoạn C, sau khi chủ nghiệp vụ gán sổ vào khách. Không đoán theo tên.
2. **K2 · Thẻ mặc định:**
   - địa chỉ không ghi `the=` thì mở thẻ **Sổ**;
   - có `month=` hoặc `loc=` thì luôn mở thẻ Sổ;
   - mọi link hiện có giữ nguyên nghĩa.
3. **K3 · Tên mục trên thanh điều hướng:** giữ "Sổ khách" tới khi chốt từ điển giao diện (audit UX 4.5).
4. **K4 · Hứa trả:** có.
   - Người đòi nợ ghi tay số tiền (VND nguyên), hẹn ngày và ghi chú.
   - Máy tự chấm theo phiếu thu chưa hủy: **giữ lời**, **lỡ hẹn** (kèm số đã trả) hoặc **đang chờ**.
   - Hứa trả không cộng vào số nào, không đổi phân bổ, không khóa tháng. Nó là ghi chú ngoài đường tiền, như `reminder_log`.
   - Không đọc nội dung tin nhắn, không dự báo tiền về. Phạm vi v1 của [`NHAC-NO-01`](nhac-no-01.md) giữ nguyên.
5. **K5 · Đo trả chậm:** đếm số ngày từ hạn trả ([`DASH-03`](dash-03.md) (1)) tới ngày trả xong của từng tháng nợ, theo quy tắc ở spec.
   - Tháng còn nợ: đếm tới hôm nay (giờ VN).
   - Tháng trả xong trước mốc nạp, hoặc về 0 mà không qua dòng phân bổ: không đo.
6. **K6 · Hội thoại Zalo:** gắn tay một lần, ở thẻ Hồ sơ hoặc trang Chat Zalo. Đã gắn thì không cần tìm theo tên nữa.
7. **K7 · Debit note:** ghi lại mỗi lần bấm xuất: tháng, số debit note, tổng tiền, người làm.
8. **K8 · Quyền:** giữ [`V7-ID`](v7-id.md): ai vào app cũng thao tác như nhau. Phân quyền "chỉ xem" cho sếp là việc riêng, cần spec danh tính.

## Ngày / nguồn

31/10/2026, chat. Người dùng chuyển yêu cầu của sếp: cải thiện luồng người dùng, nhất là khi người quản lý mở một khách thì xem được gì. Claude đưa spec kèm tám câu K1–K8, mỗi câu một phương án "(đề xuất)", cùng bản xem dữ liệu giả ([PR FinanceBullkk/webdebit#229](https://github.com/FinanceBullkk/webdebit/pull/229)). Người dùng trả lời "Chốt theo đề xuất".

## Sửa đổi 4/11/2026: ẩn nhắc nợ

Người dùng chốt trong chat ("Ẩn luôn"): thẻ Tình hình và Trao đổi không còn nút hay dòng lịch sử nhắc nợ; chi tiết ở [`NHAC-NO-01`](nhac-no-01.md). Khi quá hạn, việc tiếp theo là "Liên hệ khách". Các mục dưới đây nói về Copy tin nhắc là lịch sử của bản trước.

## Hiệu lực và giới hạn

ĐÃ CHỐT. **PR A1 (vỏ trang khách) đã code** ngày 1/11/2026: đầu trang có thanh bốn thẻ, tham số `the=`, K2; ba thẻ ngoài Sổ hiện câu "đang làm" tới PR A2, A3. Kiểm trên máy chủ giả (spec, mục Bằng chứng); đã lên `hao` cùng ngày (FinanceBullkk/webdebit#235). **PR A2 (thẻ Tình hình) đã code** ngày 1/11/2026: khối 1, 2, 4, 5 và phần A của khối 6, chỉ đọc API có sẵn; kiểm trên máy chủ giả; đã lên `hao` cùng ngày (FinanceBullkk/webdebit#236). **PR A3 (thẻ Trao đổi và Hồ sơ) đã code** ngày 1/11/2026: dòng thời gian phiếu thu, cấn trừ, lần nhắc, hội thoại Zalo tìm theo tên; Copy tin nhắc cùng tin và cùng lệnh với Đòi nợ; giá đang áp, cột phụ phí, ảnh chứng từ, hạn trả; tin Zalo gần nhất ở khối 6 của thẻ Tình hình. Chỉ đọc API có sẵn, không đổi DB; kiểm trên máy chủ giả; đã lên `hao` cùng ngày (FinanceBullkk/webdebit#237). **PR A4 (đường vào) đã code** ngày 1/11/2026: ngăn kéo Tổng quan có nút "Trang khách" mở thẻ Tình hình; tên khách ở ma trận mở thẻ Tình hình, ở Đòi nợ mở thẻ Trao đổi; số quá hạn ở Đòi nợ mở Sổ ở tháng nợ cũ nhất, thay cho tên khách; các link khác giữ nguyên. Kiểm trên máy chủ giả. Giai đoạn A đã code xong; giai đoạn B và C chưa code.
- **Thời điểm:** code theo [PLAN](../../PLAN.md) (tạm dừng tính năng mới tới khi chạy song song) và sau PR 2c của SO-GON-04, vì cùng sửa đầu sổ.
- **Giai đoạn A:** chỉ đổi giao diện và đọc API có sẵn.
- **Giai đoạn B:** mỗi mục cần spec backend và migration riêng: B1 trả sau hạn, B2 hứa trả, B3 gắn Zalo, B4 ghi lần xuất debit note và ghi chú lần nhắc. Bảng mới nằm ngoài đường tiền, triển khai theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md).
- **Giai đoạn C:** chưa thiết kế, chờ dữ liệu gán sổ vào khách.

Không đổi luật tiền, phân bổ, khóa tháng hay các lựa chọn của SO-GON-04 (kể cả H5: không hiện phân bổ trước khi ghi phiếu).

Còn mở: ma trận "Công nợ theo tháng" nhóm nợ theo tuổi tháng, lệch một tháng so với nhóm hạn trả của Tổng quan và trang khách. Xét ở đợt 3 của audit UX.
