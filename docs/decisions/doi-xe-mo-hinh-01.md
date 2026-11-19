# DOI-XE-MO-HINH-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 19/11/2026 cả tám câu luật tiền của mô hình dữ liệu mới của Đội xe, theo đúng đề xuất của Claude trong [spec](../../specs/doi-xe-mo-hinh-01.md):

1. **Mỗi khoản chi có đúng một người trả.** Không chia một khoản cho hai người; cần chia thì ghi thành hai khoản. Người trả của chặng chỉ là mặc định khi thêm khoản mới (VETC mặc định công ty trả).
2. **Tháng đã khóa hoặc khoản đã được hoàn thì không đổi người trả của khoản đó** (giữ luật hiện nay); muốn đổi thì hủy đợt hoàn, mở tháng hoặc ghi điều chỉnh. Không thêm "bút toán chuyển" giữa hai người.
3. **Công nợ chung theo phương án (a).** Đối tác mới (nơi bán dầu, gara, nhà xe thuê) dùng bảng chung ngay; tài xế, người đi lệnh và HTH giữ đường ghi tiền hiện có (ứng, hoàn, bảng kê, tiền về), chỉ thêm lớp đọc chung. Nếu định hợp nhất hẳn người và HTH vào bảng chung thì quyết trước ngày chạy thật.
4. **Khoản chi theo xe (dầu mua ở nơi bán, sửa chữa, định phí) giai đoạn đầu do công ty hoặc nơi bán, gara trả.** Tài xế, người đi lệnh tự trả dọc đường vẫn ghi như chi của chặng (khoản "Đổ dầu" hiện có).
5. **Chặng đã gửi bảng kê không được sửa ngày, container, loại chặng, xe và không được xóa.** Sai thật thì điều chỉnh dòng bảng kê (lý do bắt buộc) trước khi đối chiếu xong.
6. **Khoản phát sinh trong ghi chú mà máy không đọc được:** hai nhân viên sửa thành dòng thu trên web **trước** ngày chuyển; còn sót thì không chuyển và không tính tiền, như hiện nay.
7. **Phát sinh tính theo mức (neo theo ngày, nổ máy theo giờ): đổi mức thì chặng chưa gửi bảng kê đổi theo**; gửi bảng kê thì chốt số.
8. **Hạ sớm và kiểm hoá: phương án X.** Giữ hai khoản thu (mỗi khoản một mức) nối với một khoản chi "Hạ sớm/KH"; cờ chi hộ nằm ở một chỗ (khoản chi), hai khoản thu đọc theo.

Mô hình, bảng đối chiếu hiện có → đề xuất, thứ tự migration và bất biến số dư, số đòi: [spec](../../specs/doi-xe-mo-hinh-01.md). Luật tiền hiện hành (công thức số dư, hoàn theo đợt, hủy bắt buộc lý do, khóa tháng, bảng kê gửi → đối chiếu → tiền về, chi hộ) giữ nguyên; mọi bước chuyển phải chứng minh không đổi số.

## Quan hệ với quyết định trước

- [`DOI-XE-CAU-TRUC-01`](doi-xe-cau-truc-01.md): thực hiện điểm 4 của quyết định đó (hướng đổi mô hình); luật tiền chi tiết mà quyết định đó để ngỏ nay chốt ở đây.
- [`CHI-PHI-XE-01`](chi-phi-xe-01.md), [`DOI-XE-THU-01`](doi-xe-thu-01.md): giữ nguyên luật tiền; điểm 5 thắt chặt thêm một chỗ (chặng đã gửi bảng kê), điểm 8 chỉ gom cờ chi hộ về một chỗ, không đổi giá trị.
- [`DOI-XE-DIEU-DO-01`](doi-xe-dieu-do-01.md): giữ nguyên; `chang.tra`, `chang.nguoi_tra_id` còn làm người trả mặc định.

## Ngày / nguồn

19/11/2026, chat. Phiên điều phối (audit và thiết kế lại) trình người dùng bảng tóm tắt tám câu kèm đề xuất của spec (câu 3 chọn (a), câu 8 chọn X) và hỏi "Chốt 8 câu luật tiền theo đề xuất chứ?". Người dùng trả lời nguyên văn: "Chốt theo đề xuất". Người dùng chốt theo bảng tóm tắt đó, không đọc toàn bộ spec; chi tiết kỹ thuật ở spec là ĐỀ XUẤT cho tới khi từng gói migration có spec và review riêng.

## Hiệu lực và giới hạn

ĐÃ CHỐT tám điểm trên. Chưa code, chưa migration, chưa chạy gì trên `hao`.

Phải làm trước khi chạy migration ghi:

- đo trên bản thử số khoản ghi chú mà bộ đọc gắn lỗi (câu 6 chỉ định cách xử lý);
- kiểm hai cờ chi hộ của danh mục chi và danh mục thu có lệch nhau trên `hao` không (web có sửa được cờ phía thu); lệch thì dừng và người dùng chọn cờ đúng, không tự chọn.

Đã đo một lần (số đo của phiên điều phối ngày 19/11/2026 trên bản thử ở `hao`, chỉ đọc qua các đường `GET /api/v7/doixe`, `/bang-gia`, `/bang-ke`: tháng 10 có 206 chặng với 225 khoản phát sinh, 0 khoản lỗi, 1 khoản lạ; tháng 11 có 13 chặng, 0 khoản phát sinh; 10 cặp danh mục nối được, 0 cặp lệch cờ chi hộ. Đây là số của ngày đo; bản thử còn được nhập tiếp, nên vẫn phải đo lại ngay trước khi chạy migration).

Giả định nghiệp vụ người dùng chấp nhận theo đề xuất, chưa hỏi điều xe, hai nhân viên, kế toán: câu 1 (không chia một khoản cho hai người) và câu 4 (tài xế chưa ứng tiền trả dầu, sửa xe theo xe).

Còn mở, để spec từng gói: làm tròn định phí chia theo ngày, luật khóa tháng của chi theo xe, lịch sử tài xế đổi xe, có đưa cước thành dòng thu về sau không, có bắt lý do khi sửa dòng thu chưa gửi không.

Không cấp quyền nạp dữ liệu, ghi Google Sheet hay chạy DDL: mỗi việc theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md) hoặc cần người dùng đồng ý riêng.
