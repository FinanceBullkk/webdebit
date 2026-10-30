# DEBIT-NOTE-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Debit note xuất từ sổ khách theo **mẫu Debit Note v3** sếp duyệt ngày 30/10/2026 (đặc tả "Debit Note – đặc tả mẫu cho dev (v3)" do người dùng chuyển). Thay bố cục "COMMERCIAL INVOICE" của [DEBIT-NOTE-01](debit-note-01.md); giữ nguyên các điểm (1) theo tháng công nợ, (2) PDF + Excel, (4) Health cert là tiền, (5) chỉ chuyến của tháng. Spec: [`specs/v7-debit-note.md`](../../specs/v7-debit-note.md).

Theo đặc tả v3:

1. **Một chứng từ**: một bên phát hành, một bên mua, một kỳ, nhiều dòng container và có thể có dòng phí không gắn container; tiền gốc VND. Ngoài phạm vi: hóa đơn GTGT điện tử (chỉ ghi số để tham chiếu).
2. **PDF**: trang 1 tóm tắt A4 dọc luôn vừa một trang (thanh màu, header, BILL TO + DOCUMENT, khung AMOUNT DUE + DUE DATE, CHARGE SUMMARY theo cảng xếp theo số container giảm dần + dòng Additional charges + Subtotal + TOTAL DUE, số tiền bằng chữ, PAYMENT INFORMATION với Payment Ref = số debit note, khối ký, hai dòng ghi chú, chân trang "Page x of y"); các trang chi tiết A4 ngang, tiêu đề hai hàng lặp mỗi trang, chỉ hiện cột phí có phát sinh, nhóm ADDITIONAL CHARGES, dòng TOTAL không đứng một mình. Tiếng Anh chính, tiếng Trung kèm, không tiếng Việt; font, cỡ chữ, màu theo đặc tả.
3. **Danh mục 8 loại phí**, đúng thứ tự cột: LUMP-SUM 单价, STORAGE 早装产生费用, TRUCKING 拼柜, GENERATOR / ELECTRICITY FEE 发电机/电费, OVERSTAY 押车, HC FEE 卫生证, CANCELLATION FEE 取消订柜费, AMD FEE 改单费.
4. **Quy tắc tính**: mọi số trang 1 tính từ dòng chi tiết; thành tiền dòng = LUMP-SUM + phí; TOTAL DUE = container + dòng phí riêng; số container chỉ đếm dòng container; dòng phí riêng không đánh số; Subtotal = TOTAL DUE; hạn = ngày phát hành + số ngày; USD chia tổng một lần, làm tròn 2 số lẻ, một tỷ giá kèm nguồn và ngày; số bằng chữ "SAY VIETNAM DONG … ONLY".
5. **Excel đối chiếu**: một sheet, cột cố định NO., CONTAINER NO., SHIPPER, DATE, FROM, TO, đủ 8 cột phí, TOTAL (VND); số thật, không gộp ô, cố định hàng tiêu đề; USD chỉ ở dòng tổng. Tên file `<số>_<khách>_<yyyy-mm>`.
6. **Kiểm tra trước phát hành** (chặn/cảnh báo) theo bảng của đặc tả, phần làm được từ dữ liệu một chứng từ.

## Claude chọn (theo `CLAUDE-ALL-01`, người dùng sửa được khi xem bản thử)

- **Ánh xạ loại phụ phí sổ web → danh mục**: Neo → OVERSTAY (押车), Điện → GENSET, Ghép → TRUCKING (拼柜), Health cert → HC FEE, tên có "lưu kho/storage" → STORAGE, "hủy/cancel" → CANCELLATION, "amd/sửa bill" → AMENDMENT. Bốn loại sổ web có mà danh mục v3 chưa có in thành cột riêng **chỉ khi phát sinh**, sau 8 cột: Bảo hiểm → INSURANCE 保险, Kiểm định → INSPECTION (O+CD+VS) 检验费, Giảm trừ → DISCOUNT 折扣, Khác/Phụ phí ban đầu/loại tự thêm → OTHER FEES 其他费用.
- Cột phí hiện khi **có ô khác 0** (đặc tả ghi "tổng khác 0"; chọn vậy để khoản +x/−x không bị ẩn).
- **Thiếu giá** thì không coi là 0: ô trống, tổng in "—", chặn bản chính thức (thay điểm (3) "để trống, CHƯA CHỐT" của DEBIT-NOTE-01).
- Thành tiền dòng (LUMP-SUM + phí) **khác số trên sổ** thì chặn, như rule "Subtotal khác TOTAL DUE".
- Còn **Chặn** → chỉ xuất bản nháp có chữ DRAFT, tên file `_DRAFT`. Còn **Cảnh báo** → người lập tích xác nhận mới ra bản chính thức.
- **Thông tin chứng từ người lập điền ở form**, trình duyệt nhớ (công ty theo bên phát hành, khách theo sổ); không lưu máy chủ, không đưa thông tin ngân hàng, MST, tên pháp lý khách vào repo (repo public). Điền sẵn HTH (tên, địa chỉ, email đang in trên mẫu) và Nông Sản Xanh (tên, MST 0319147624 theo đặc tả).
- **Danh mục nơi đóng hàng/cảng** bản đầu (tỉnh Tây Nguyên, Đông/Tây Nam Bộ thường gặp; cảng Trung Quốc thường gặp). Ngoài danh mục thì cảnh báo; chính tả chuẩn "Dak Lak" (DAKLAK, DAK LAK cùng ra một tên).
- **Số debit note gợi ý** `<mã bên phát hành>-<yymm kỳ>-001` (HTH, NSX), người lập sửa được.
- Trang 1 nhiều cảng mà vượt một trang thì thu nhỏ cả trang cho vừa (đặc tả: "luôn vừa 1 trang").

## Ngày / nguồn

30/10/2026, chat: người dùng chuyển lời sếp (mẫu cũ xấu, làm theo mẫu chuyên nghiệp), rồi gửi file đặc tả v3 (ghi "Bố cục Debit Note v3 đã được sếp duyệt ngày 30/10/2026") kèm file tham chiếu v3 (Excel + PDF) và file Statement tháng 8/2026 khách đã đối chiếu. File khách không đưa vào repo.

## Hiệu lực và giới hạn

ĐÃ CHỐT bố cục và quy tắc v3 (sếp). ĐÃ CODE ở trang sổ khách; triển khai tự động khi merge qua `Deploy hao`.

CÒN MỞ theo đặc tả, đổi dữ liệu/nhãn chứ không đổi bố cục: tiêu đề DEBIT NOTE hay STATEMENT; quan hệ bên phát hành và chủ tài khoản nhận tiền (đang cảnh báo); pháp nhân nhận chứng từ của khách; thông tin pháp lý HTH (MST, tên trên giấy phép, địa chỉ mới); nguồn tỷ giá; số ngày thanh toán mặc định; tên TRUCKING/拼柜 và AMD FEE; phí ngân hàng (OUR); quy tắc đánh số; logo. Thêm: sếp gán bốn loại phí ngoài danh mục vào 8 loại hay giữ cột riêng.

CHƯA LÀM (cần lưu chứng từ đã phát hành vào DB, việc riêng): sổ số debit note và chặn một số dùng cho hai bên mua; chặn container đã nằm trong chứng từ khác cùng kỳ; cảnh báo đổi tỷ giá của chứng từ đã gửi; ngày phát hành cố định theo chứng từ đã lưu; lưu thông tin công ty/khách trên máy chủ thay cho trình duyệt; cột B/L NO. (sổ chưa có số B/L).
