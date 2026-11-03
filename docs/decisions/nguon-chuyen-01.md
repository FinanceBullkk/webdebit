# NGUON-CHUYEN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **chuyến lấy theo bảng booking, tiền lấy theo sổ gốc.**

1. **Ghép chuyến.** Một dòng chuyến trên sổ (dòng sổ gốc hoặc chuyến web) và một dòng nguồn là cùng một chuyến khi cùng container và ngày lệch không quá 3 ngày; dòng sổ không có ngày thì cùng tháng nợ. Mỗi dòng nguồn ghép với nhiều nhất một dòng sổ, cặp lệch ít ngày nhất ghép trước. Đây là luật ±3 ngày mà chặn trùng (`BASELINE_DATE_WINDOW`) và hàng chờ đang dùng.
2. **Theo nguồn:**
   - ngày chuyến;
   - với chuyến biển, thêm khách (chủ hàng chuẩn, qua bảng ghép tên) và mặt hàng.

   Chuyến bộ lấy khách theo sổ trên Sheet, vì cột CHỦ HÀNG của bảng bộ có khi là kho đóng hàng chứ không phải khách. Ngày chuyến bộ là ngày xe nhập kho theo [`DATE`](date.md) khi bảng có ghi: cột "NGÀY ĐÓNG HÀNG", hoặc "NGÀY LÊN KHO" ở hai tab bộ sầu riêng của file 2025. Không có thì lấy ngày khởi hành ("NGÀY KHỞI HÀNH" / "NGÀY XUẤT PHÁT").
3. **Theo sổ gốc:** đơn giá, phụ phí, tổng tiền, như [`GIA-NGUON-01`](gia-nguon-01.md). Giá ghi bằng chữ trong booking (ví dụ "38TR+1") chỉ dùng để đối chiếu, không ghi vào sổ.
4. **Chỗ lệch do người quyết ở hộp ngoại lệ**, với "theo nguồn" là cách xử lý đề xuất sẵn. Các loại lệch:
   - ngày khác nguồn;
   - khách khác booking;
   - nghi tính trùng: hai dòng sổ trở lên có tiền cùng là một chuyến nguồn;
   - chuyến có trong nguồn mà không có trên sổ;
   - chuyến trên sổ không có trong nguồn.

   Máy chỉ tự làm phần [`HANG-CHO-01`](hang-cho-01.md) và `MAY-KHOA-01` ([PR FinanceBullkk/webdebit#282](https://github.com/FinanceBullkk/webdebit/pull/282), chưa merge lúc viết) đã cho, nay áp cho cả các nguồn dưới đây.
5. **Chuyến không có nguồn giữ như sổ gốc** ([`LEGACY-A`](legacy-a.md)): chuyến trước 2025, bán cước, và chuyến không có trong bảng nguồn.

**Nguồn:**
- `CONT_NGUON` của file CHAU_HAO: chuyến biển từ 11/2025. Web đang đọc tab này.
- `CONT_BO` của file CHAU_HAO: chuyến bộ từ 08/2025. **Giữ tab này**, thay cho lời báo phía Sheet ngày 30/10/2026 rằng được bỏ `CONT_BO`.
- File booking năm 2025 (bản người dùng chép, đưa 3/11/2026):
  - các tab tháng 01/2025–02/2026 (chuyến biển);
  - tab "CONT BỘ";
  - hai tab bộ sầu riêng. Hai tab này ghi ngày "dd/mm" không có năm, nên năm suy ra là 2025. Suy sai thì chuyến không ghép được, không ghép nhầm.

  Đây là lịch sử đã đóng, nên đọc một lần thành bản chụp.

## Ngày / nguồn

3/11/2026, chat. Người dùng hỏi có nên chuẩn hóa Sheet sổ nợ, rồi đề nghị lấy cont và ngày theo booking, ghép giá để có sổ nợ chính xác. Claude đo chỉ đọc: sổ gốc và hai tab CHAU_HAO tải trên `hao` cùng ngày, file 2025 đọc qua connector. Người dùng chốt ("Chốt, viết spec"), rồi đưa thêm file 2025 trong lúc viết spec.

Số đo (chỉ số đếm; danh sách có tên khách giữ ngoài Git):

- **Từ 01/2025 tới 10/2026:**
  - 9.416/9.710 dòng chuyến của sổ gốc khớp một dòng nguồn (97,0%), chiếm 98,6% tiền chuyến.
  - Khi ô ngày của sổ đọc được, ngày trùng đúng ngày nguồn ở 99,2% cặp biển và 97,1% cặp bộ.
- **Không có nguồn:** mọi chuyến năm 2024 (573 dòng, khoảng 5% tiền chuyến) và bán cước từ 2025 (dưới 1%).
- **Nguồn xác nhận bộ nạp đọc ngày đúng:** 1.870/1.877 ngày mà bộ nạp tự đảo ngày/tháng trùng đúng ngày booking.
- **Cần người xem:**
  - 28 nhóm có từ hai dòng có tiền cùng ghép một chuyến nguồn;
  - thêm 9 dòng nghi trùng lệch 1–3 ngày hoặc phải đảo ngày/tháng mới trùng (ca đảo ngày do phiên khác phát hiện cùng ngày);
  - 381 chuyến nguồn không thấy trên sổ dù khách đã có sổ;
  - 293 dòng sổ không đọc được ngày mà nguồn có ngày.

## Hiệu lực và giới hạn

ĐÃ CHỐT nguyên tắc (1)–(5) và danh sách nguồn. Cách làm theo giai đoạn ở [spec](../../specs/v7-chuyen-theo-nguon.md). Chưa triển khai: chưa đổi code hay dữ liệu.

Không đổi luật tiền, phân bổ, khóa tháng hay quyền. Mọi thay đổi trên sổ đi qua lệnh có sẵn và ghi Lịch sử.

CÒN MỞ, hỏi người dùng khi tới giai đoạn liên quan:
- Người bấm "lấy ngày theo nguồn" ở tháng khóa: theo [`KHOA-CHU-01`](khoa-chu-01.md), ngày vẫn khóa với người.
- Máy tự lấy ngày nguồn cho dòng **đã có ngày** mà lệch trong cùng tháng: `MAY-KHOA-01` hiện để người quyết.
- Một lệnh dời chuyến sang sổ khách theo booking. Hôm nay việc này làm bằng chuỗi lệnh tay ([nhật ký](../deploys/2026-11-03-doi-cont-sang-so-booking.md)).
- Chuyến bộ mới tự vào sổ: cần luật chọn sổ, vì CHỦ HÀNG của `CONT_BO` không luôn là khách.
