# Thu chi tự sinh: một nguồn tiền thật, bốn sổ (THU-CHI-02)

Trạng thái: **ĐỀ XUẤT** (Claude, 24/11/2026). Sếp chưa chốt, chưa trả lời [tám câu hỏi](#câu-hỏi-cho-sếp). Trang đề xuất gửi sếp (riêng tư): https://claude.ai/artifact/3z2DE74hHnSEs9M5BnfXF6. **Đợt 0** (bản bấm thử, số bịa, không backend) được người dùng giao code ngày 24/11/2026 để dễ hình dung; mọi đợt khác chờ sếp chốt và có quyết định `docs/decisions/thu-chi-02.md`.

Nguồn: sếp nhận xét (qua người dùng, chat 24/11/2026) phần thu chi và Zalo/WeChat "đang chỉ dựng lại 1 cái flow ko ổn của hiện tại", cần flow mới để thống kê thu chi hiệu quả nhất. Spec này thay hướng "đọc chat để đoán tiền" của [`ZALO-THU-CHI-01`](../docs/decisions/zalo-thu-chi-01.md) phần B, hấp thụ [`SAO-KE-01`](sao-ke-ngan-hang.md) và đi cùng đề xuất "Sổ nợ tự sinh" (23/11/2026): đây là nửa tiền của cùng một kiến trúc.

## Câu hỏi quản lý mà spec trả lời

1. Tiền đang có ở từng tài khoản và quỹ; hôm nay vào bao nhiêu, ra bao nhiêu.
2. Thu chi theo danh mục mỗi tháng: vào theo khách, ra theo loại chi, theo từng công ty trong nhóm.
3. Bắt sót và gian lận: tiền về chưa vào sổ, chi không có lý do hoặc không ai duyệt.
4. Đang ứng cho khách Trung Quốc bao nhiêu, của ai, bao lâu.
5. Lãi lỗ chuyến, xe, khách (đợt cuối).

## Vì sao thôi đọc chat để tính tiền

Đo chỉ đọc ngày 24/11/2026, chỉ số đếm:

- 30 ngày 25/10–23/11: sổ có 48 phiếu thu của 27 khách. Trang Thu chi bắt 50 khoản, tất cả từ ảnh của một nhóm Zalo gắn một sổ: khớp phiếu **0**. Ảnh mẫu là biên lai **khách tự trả hãng tàu, bảo hiểm** gửi làm bằng chứng, không phải tiền vào công ty; sổ đó có 0 phiếu thu trong tháng 10–11.
- Trang bắt 0 khoản chi. DB không có tài khoản ngân hàng, quỹ, danh mục chi, nhà cung cấp, ngoại tệ.
- Nhóm WeChat "THU-CHI" nội bộ (tin và ảnh 20–24/11): 19 ảnh xem được, 16 thuộc **tiền hàng khách Trung Quốc**: 8 chứng từ USD "payment for goods" vào tài khoản của công ty xuất khẩu trong nhóm (người dán nhãn tay tên khách), 4 bảng Excel số dư từng khách (USD nhận × tỷ giá → VND → các lần chi hộ → còn lại; có khách âm, tức công ty đang ứng), 2 lệnh chi hộ theo lô, 2 biên bản giao tiền mặt. Tin nhắn còn có: xin duyệt chi, xin ứng tiền mặt, "tiền mặt cty còn …", chốt tỷ giá bán USD, "khoản này vào chưa", "của ai vậy", bên thứ ba trả nợ hộ khách, khách trả lắt nhắt nhiều tháng, phần có hóa đơn và không hóa đơn.

Kết luận: chat là nơi người kể về tiền, không phải nơi tiền xảy ra; dòng tiền lớn nhất đang nằm ngoài mọi sổ.

## Người dùng và luồng (bước 1)

**Vai:** người cần chi (điện thoại); sếp, người duyệt (iPhone 390px); kế toán và thủ quỹ (máy tính 1280×720); người lo tiền hàng khách Trung Quốc (máy tính); team công nợ (máy tính, trang Việc cần làm); khách (chỉ chuyển tiền); bot (chỉ báo). Danh tính lấy từ Tailscale ([`V7-ID`](../docs/decisions/v7-id.md)); quyền theo [`QUYEN-01`](../docs/decisions/quyen-01.md).

1. **Đề nghị chi** (người cần chi): số tiền, tiền tệ, người nhận (chọn từ danh mục đối tác), loại chi, gắn chuyến/container/xe/khách, ảnh hóa đơn hoặc bảng kê. Loại: chi thường, chi hộ khách TQ, ứng tiền mặt. Gửi xong bot báo người duyệt. Thay tin xin duyệt trong WeChat, không làm hai lần.
2. **Duyệt** (sếp): mỗi đề nghị một thẻ, xem ảnh, bấm Duyệt hoặc Từ chối (bắt buộc lý do). Chi hộ hoặc ứng vượt số dư ví thì thẻ ghi rõ "vượt số dư ví …". Khóa thêm ngoài web: duyệt lệnh hai cấp trong internet banking doanh nghiệp.
3. **Chuyển và khớp** (kế toán): danh sách đã duyệt, mỗi dòng có nội dung chuyển khoản chứa mã đề nghị (`DC0456`) và nút chép. Sao kê về, máy đóng đề nghị; một đề nghị tách nhiều lệnh vẫn khớp.
4. **Tiền vào, thu cước**: debit note in mã thanh toán theo sổ (`HTH0123K`) và VietQR. Mỗi giao dịch vào thành **một phiếu thu điền sẵn** (`reference` = mã giao dịch), trừ nợ cũ trước như sổ đang làm, nên khách trả lắt nhắt không cần ghép hóa đơn. Trước ngày chuyển hẳn khỏi Sheet ([`CHUYEN-HAN-01`](../docs/decisions/chuyen-han-01.md)) chỉ đối chiếu, không ghi phiếu trên web.
5. **Ví khách TQ** (người lo tiền hàng): USD về tài khoản công ty xuất khẩu → máy nhận khách theo công ty chuyển tiền bên Trung Quốc (bảng ánh xạ học một lần) → bán USD (ghi tỷ giá ngân hàng và tỷ giá tính khách) → ví cộng VND → chi hộ nhà cung cấp hoặc giao tiền mặt → ví trừ. Ví âm là công ty đang ứng: phải duyệt, có hạn mức, có tuổi. Sao kê ví thay bảng Excel.
6. **Quỹ tiền mặt** (thủ quỹ): rút từ ngân hàng về quỹ (khớp giao dịch rút), giao tiền kèm ảnh biên bản bàn giao, kiểm quỹ (đếm, ghi số; lệch thì cờ).
7. **Tiền chờ về** (ai biết sắp có tiền): ghi số, tiền tệ, tài khoản, khách; sao kê có dòng khớp thì máy báo "Về rồi" và ghép luôn.
8. **Hộp ngoại lệ** (kế toán, team công nợ): khoản máy không chắc, xếp theo số tiền: tiền về chưa rõ của ai (gắn khách; máy hỏi có nhớ người chuyển không), chi chưa có đề nghị, lệch do phí, dòng TK cá nhân chưa phân loại (chỉ chủ tài khoản thấy).
9. **Dòng tiền** (sếp): tiền đang có theo tài khoản và quỹ kèm giờ cập nhật, tổng đang ứng cho khách, hôm nay vào/ra, "Cần sếp" (đề nghị chờ duyệt, chi chưa duyệt, tiền về chưa rõ của ai), tháng này theo danh mục.

**Bị chặn:** sao kê cũ quá 2 ngày làm việc hoặc thủng số dư thì Dòng tiền ghi rõ "chưa đủ", không giả là mới; người dùng thường gặp 403 như trang quản lý; dòng TK cá nhân chưa phân loại không hiện cho ai ngoài chủ tài khoản.

## Đầu ra

Một sổ tiền nhận mọi giao dịch thật; mỗi giao dịch ghép đúng một lần vào một trong bốn sổ; sếp có Dòng tiền trên iPhone; chi có duyệt trước; ví từng khách TQ thay Excel; cảnh báo bắt sót, gian lận chạy bằng luật cố định; bot viết vào nhóm, không đọc nhóm.

## Kiến trúc: một nguồn, bốn sổ

| Sổ đích | Gồm | Hiện có |
| --- | --- | --- |
| Thu cước | Khách trả cước, phụ phí (kể cả trả lắt nhắt, bên thứ ba trả hộ) | Sổ nợ `sokhach`, phân bổ nợ cũ trước |
| Ví khách TQ | USD tiền hàng vào, đổi sang VND, chi hộ (chuyển khoản, tiền mặt), ứng trước | Mới, thay Excel số dư |
| Chi có duyệt | Hãng tàu, cảng, cửa khẩu, xe thuê, Đội xe, văn phòng, lương, thuế; ứng tiền mặt | Mới (Đội xe đã có ứng, hoàn) |
| Nội bộ | Chuyển giữa tài khoản hoặc công ty, rút quỹ, bán USD, phí ngân hàng | Mới |

Dòng TK cá nhân không thuộc công ty là "việc riêng": bỏ nội dung, giữ số tiền và số dư để vẫn kiểm liền mạch, không vào thống kê.

**Luật ghép** (chỉ nhận khi có đúng một ứng viên, theo thứ tự): R1 mã đề nghị hoặc mã thanh toán trong nội dung · R2 mã ngân hàng trùng `reference` của phiếu · R3 người chuyển hoặc công ty chuyển đã biết · R4 số hóa đơn, số hợp đồng trong nội dung · R5 cùng số tiền trong cửa sổ ngày `MATCH_BEFORE/MATCH_AFTER` của `web/v7_cash_chat.py` · R6 tổng nhiều lệnh ra bằng một đề nghị · R7 một giao dịch bằng tổng ≤ 4 phiếu một sổ (chỉ gợi ý) · R8 cặp nội bộ và cặp đổi tiền · R9 người nhận định kỳ · còn lại người xử lý. **Phí ngân hàng:** số về hụt so với số chuyển trong ngưỡng theo tiền tệ thì vẫn khớp, phần hụt thành dòng "phí ngân hàng"; ngoài ngưỡng là ngoại lệ.

**Cảnh báo:** chi không có đề nghị duyệt · chuyển trước giờ duyệt · khác số hoặc khác người nhận · một đề nghị chi hai lần · tách nhỏ dưới ngưỡng · người nhận mới số lớn · tài khoản người nhận đổi · người nhận là người đề nghị · tiền về quá 3 ngày làm việc chưa vào sổ · phiếu không thấy tiền · khách báo chuyển mà không thấy tiền · tiền khách vào TK cá nhân bằng đúng một khoản nợ · ví âm quá hạn mức hoặc quá lâu · chi tiền mặt không có biên bản · kiểm quỹ lệch · sao kê thủng hoặc cũ · tài khoản chưa khai.

**Tách vai:** cờ "chi chưa duyệt" chỉ người duyệt gỡ bằng duyệt bù; người chuyển tiền và người phân loại không tự gỡ. Chống sửa file sao kê: kiểm số dư liền mạch, cuối tháng sếp tự tải bản PDF của ngân hàng để so tổng.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- Có: `sokhach.receipt` (`reference`, `record_receipt`, phân bổ nợ cũ trước); `contact_mark` ("khách báo đã chuyển"); Đội xe `doixe.ung`, `dot_hoan`, `tien_ve`, `dong_phi`; debit note v4 (`preview/debit-note-v4.js` in "Payment Ref." = số debit note, chưa lưu DB; tài khoản nhận lấy từ `web/v7_debit_note_config.py`); `web/v7_cash_chat.py` (`amount_vnd`, `Directory`, ghép một-một `_components`/`_saturate`/`pair_exact`/`pair_single`, hằng `MATCH_*`); `web/v7_telegram.py` (`Outbox`, cờ tắt); khuôn bảng chỉ thêm có `request_id`, trước → sau (`tools/migrations/2026-11-21-v7-cash-report-review.sql`); quyền `web/v7_role.py`; danh tính `web/v7_identity.py`.
- Thiếu: tài khoản và quỹ, giao dịch ngân hàng, đối tác và công ty chuyển tiền, danh mục thu chi, ví khách, đề nghị chi, tỷ giá, kiểm quỹ, tiền chờ về. Gói B4 của [`DOI-XE-MO-HINH-01`](../docs/decisions/doi-xe-mo-hinh-01.md) (`doixe.doi_tac`, `doixe.tien_chuyen`, chưa code) gộp vào schema mới, không dựng sổ tiền thứ hai.

## Dữ liệu (ĐỀ XUẤT, chưa migration)

Schema mới `tien`, ngoài đường tiền của sổ nợ (không vào `v_outstanding_month`, không đổi phân bổ, khóa tháng hay `customer.version`):

- `phap_nhan`; `tai_khoan` (ngân hàng hoặc quỹ, công ty hoặc cá nhân, tiền tệ, 4 số cuối, người giữ; không lưu số tài khoản đầy đủ).
- `lo_nhap` (nguồn file hoặc API, sha256 file, đếm đọc/nhập/trùng/lỗi, hủy lô bắt buộc lý do); `giao_dich` (chỉ thêm; khóa nguồn duy nhất theo tài khoản; số tiền đơn vị nhỏ nhất `bigint > 0` + tiền tệ; số dư sau; băm HMAC của tài khoản và tên đối ứng, khóa để ngoài repo).
- `ghep` (giao dịch ↔ phiếu thu, dòng ví, đề nghị, Đội xe hoặc giao dịch đối ứng; nhiều-nhiều có tổng; mã luật hoặc người làm).
- `doi_tac` (khách nối `sokhach.customer`, khách TQ, công ty chuyển tiền → khách, nhà cung cấp, người nối `doixe.nguoi`); `vi`, `vi_dong` (vào, đổi, chi hộ, ứng, phí; tỷ giá ngân hàng và tỷ giá tính khách kiểu `numeric` trong SQL).
- `de_nghi_chi`, `de_nghi_su_kien`; `quy_kiem`; `cho_ve`; `danh_muc`, `quy_tac`; `trao_doi`; `ty_gia`.

## Giao tiếp frontend–backend (ĐỀ XUẤT, sau đợt 0)

Mọi route chỉ quản lý, trừ tạo và xem đề nghị của chính mình: `GET /api/v7/tien/dong-tien`, `GET /api/v7/tien/giao-dich`, `POST /api/v7/tien/nhap` (xem trước rồi ghi, `request_id`), `POST /api/v7/tien/ghep`, `GET|POST /api/v7/tien/de-nghi`, `POST /api/v7/tien/de-nghi/duyet`, `GET /api/v7/tien/vi`, `POST /api/v7/tien/quy/kiem`, `POST /api/v7/tien/cho-ve`. Lỗi theo bảng `ERRORS` của `web/v7_api_tables.py`. Đợt 0 **không** có route nào.

## Đợt 0: bản bấm thử (giao code ngay)

**Mục đích:** người dùng và sếp bấm thử cả flow trên `hao` bằng số bịa, trước khi có schema, sao kê thật hay quyết định. Không ghi tiền, không gọi API, không đọc dữ liệu thật.

**Trang:** `preview/thu-chi-tu-sinh.html`, route `/thu-chi-tu-sinh.html` thêm một dòng vào `PAGES` của `web/v7_api_tables.py`; **không** thêm vào `USER_PAGES` (chỉ quản lý xem được), không thêm vào menu. JS/CSS nạp đúng khuôn `<script src="ten.js"></script>` và `<link rel="stylesheet" href="ten.css">` để server tự phục vụ (`PAGE_FILE`). Dùng đầu trang và CSS dùng chung như các trang quản lý hiện có. Dải cố định đầu trang: "Bản thử · số bịa · không nối ngân hàng".

**File:** `thu-chi-tu-sinh.html`, `thu-chi-tu-sinh.css`, `thu-chi-tu-sinh-fixture.js` (dữ liệu bịa), `thu-chi-tu-sinh-model.js` (hàm thuần: ghép, số dư, ví, cảnh báo, áp sự kiện), `thu-chi-tu-sinh-ui.js` (vẽ, bấm), `test-thu-chi-tu-sinh-model.js`, `test-thu-chi-tu-sinh-browser.js` (dùng `test` của `./shared-browser.js`).

**Bố cục:** thanh chọn vai "Xem như: Sếp · Kế toán · Tiền hàng · Nhân viên"; mỗi vai một màn:

- **Sếp (Dòng tiền, khung 390px):** tiền đang có theo tài khoản và quỹ; tổng đang ứng; hôm nay vào/ra; "Cần sếp" với thẻ đề nghị (Duyệt, Từ chối có lý do), cờ "chi chưa duyệt" (Duyệt bù); tháng này theo danh mục (thanh ngang).
- **Kế toán (Sổ tiền, 1280px):** giao dịch theo ngày và tài khoản, cột "ghép vào" (sổ, luật hoặc người); hộp ngoại lệ; đã duyệt chờ chuyển (nội dung có mã, nút chép); quỹ tiền mặt và kiểm quỹ; việc của team công nợ (tiền về chưa rõ của ai, phiếu chờ ghi).
- **Tiền hàng (Ví khách, 1280px):** danh sách ví (số dư, âm tô cảnh báo kèm chữ), sao kê một ví (USD vào, tỷ giá ngân hàng và tỷ giá tính khách, VND, chi hộ, tiền mặt, còn lại), tiền chờ về.
- **Nhân viên (Đề nghị chi, khung 390px):** form tạo đề nghị (kiểm nhập: số tiền nguyên dương, người nhận, loại; báo lỗi ngay dưới ô), danh sách đề nghị của mình, chi tiết một đề nghị với dòng thời gian (tạo → duyệt → chuyển → khớp ngân hàng) và mục Trao đổi.

**Kịch bản một ngày** (bảng bước có nút Trước/Tiếp, nhảy sang đúng vai; bước cần người thì chờ người bấm nút thật, Tiếp sẽ tự làm thay):

1. 08:05 sao kê sáng về: giao dịch mới vào sổ tiền; máy ghép phần lớn, vài khoản vào hộp ngoại lệ (tiền về chưa rõ của ai, chi chưa có đề nghị, lệch do phí).
2. 08:30 kế toán gắn khoản chưa rõ cho một khách (bên thứ ba trả hộ); máy hỏi có nhớ người chuyển không; phiếu thu điền sẵn hiện ở việc của team công nợ.
3. 09:00 nhân viên tạo đề nghị `DC0456` phí nâng hạ, gắn container `MAUU1000101`, ảnh hóa đơn giả; bot (mô phỏng) báo.
4. 09:31 sếp duyệt trên Dòng tiền.
5. 10:40 kế toán chép nội dung, chuyển (mô phỏng); 10:42 giao dịch ra về, máy đóng đề nghị.
6. 11:00 người lo tiền hàng ghi tiền chờ về USD của khách TQ 2.
7. 14:06 USD tiền hàng của khách TQ 1 về qua công ty chuyển đã biết → vào ví; bán USD → ví cộng VND; tiền chờ của khách TQ 2 báo "Về rồi" khi tới.
8. 14:30 đề nghị chi hộ khách TQ 1 cho nhà vườn, ba lệnh; sếp duyệt; ba giao dịch ra khớp một đề nghị; ví trừ.
9. 15:20 một khoản chi không có đề nghị → cờ đỏ; chỉ vai Sếp có nút Duyệt bù.
10. 16:00 ứng tiền mặt cho người của khách TQ 2 vượt số dư ví → cần sếp duyệt → thủ quỹ giao kèm ảnh biên bản giả → quỹ trừ, ví âm, tổng đang ứng tăng.
11. 17:30 kiểm quỹ: nhập số đếm; khớp hoặc lệch có cờ.

**Dữ liệu bịa:** 2–3 công ty trong nhóm, 5 tài khoản (2 VND công ty, 1 USD, 1 TK cá nhân, 1 quỹ tiền mặt), khách "Khách A/B/C" và "Khách TQ 1/2", công ty chuyển "Công ty chuyển TQ 1/2", nhà cung cấp "Nhà vườn 1/2", "Hãng tàu X", "Cảng Y"; số tiền tròn, rõ là giả; container chỉ dùng tiền tố bịa `MAUU`. Không tên người thật, không số tài khoản, không số tiền thật; số tiền dạng chấm nghìn trong tài liệu phải khai `<!-- du-lieu-gia: … -->` theo `scripts/check-secrets.js`.

**Trạng thái:** mỗi danh sách có trạng thái rỗng có chữ; lỗi nhập hiện dưới ô; nút "Đặt lại kịch bản" về đầu ngày. Trạng thái giữ trong bộ nhớ trang; được dùng `localStorage` có try/catch chỉ để nhớ vai và bước đang xem.

## Nguồn quyết định

- Sếp, chat 24/11/2026 (qua người dùng): flow hiện tại "chỉ dựng lại 1 cái flow ko ổn".
- Người dùng, chat 24/11/2026: nhóm WeChat dùng cả xin duyệt lẫn báo đã thu/chi; tiền đi qua TK công ty VND, TK cá nhân, RMB/USD; kế toán chuyển sau khi sếp duyệt; sếp cần cả bốn câu hỏi; chốt bản 2 và giao code đợt 0.
- [`ZALO-THU-CHI-01`](../docs/decisions/zalo-thu-chi-01.md) Q7, [`SAO-KE-01`](sao-ke-ngan-hang.md) (ĐỀ XUẤT): sao kê là nguồn tiền thật.
- [`UX-NEN-01`](../docs/decisions/ux-nen-01.md), [`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md), [`V7-CSM`](../docs/decisions/v7-csm.md) (sổ nợ chỉ ghi VND thực nhận), [`TELEGRAM-01`](../docs/decisions/telegram-01.md), [`QUYEN-01`](../docs/decisions/quyen-01.md), [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md), [`DOI-XE-MO-HINH-01`](../docs/decisions/doi-xe-mo-hinh-01.md).
- Duyệt chi trước khi chuyển khác phạm vi [`V6-THU`](../docs/decisions/v6-thu.md) (bỏ tách người nhập/duyệt của sổ nợ) nhưng vẫn phải ghi thành quyết định mới.
- CÒN MỞ: mọi [câu hỏi cho sếp](#câu-hỏi-cho-sếp).

## Hành vi và bất biến

- Giao dịch ngân hàng, ví và đề nghị **không** tự ghi tiền vào sổ nợ; phiếu thu vẫn qua `record_receipt`. Máy tự ghi khi khớp mã là quyết định riêng sau này.
- Số tiền là số nguyên ở đơn vị nhỏ nhất của từng tiền tệ (đồng, cent); không số thực (luật `VND-02`); ô trống là NULL, không phải 0, và dòng thiếu số bị từ chối.
- Một giao dịch chỉ ghép tổng không vượt số tiền của nó; không đoán khi có hơn một ứng viên.
- Mọi gắn, tách, loại, duyệt, hủy ghi người làm, trước → sau; từ chối, loại, hủy bắt buộc lý do; bấm lặp cùng `request_id` chỉ ghi một lần.
- Nội dung chuyển khoản và chữ trong chat không vào model nào; hiển thị dạng chữ thuần đã thoát HTML.
- Không lưu số tài khoản đầy đủ, mật khẩu hay khóa trong repo, log hay DB; không webhook, không cổng vào công khai.
- Web luôn hiện tuổi của sao kê; không kết luận "chưa thấy tiền" khi sao kê chưa phủ tới ngày đó.

## Lộ trình

| Bước | Nội dung | Cần sếp | Cổng |
| --- | --- | --- | --- |
| Đợt 0 | Bản bấm thử ở trên | — | Người dùng và sếp tự đi hết kịch bản trên `hao` |
| TC0 | Một tháng sao kê mọi tài khoản + một bảng Excel ví + sổ quỹ; đo phần trăm tự ghép, chênh do phí, liền mạch; kế toán dò 30 lần chi. File ngoài repo, chỉ báo số đếm | Chốt hướng, danh sách tài khoản, cho xuất sao kê | Có số đo |
| TC1 | Schema `tien`, nhập sao kê, quỹ, nội bộ, tiền chờ về, hộp ngoại lệ, Dòng tiền | — | Một tháng mọi tài khoản và quỹ đủ, mọi giao dịch có chỗ, tổng khớp sao kê |
| TC2 | Ví khách TQ | Hạn mức ứng, tỷ giá tính khách | Số dư ví khớp Excel cũ cuối tháng |
| TC3 | Đề nghị chi có duyệt; mã thanh toán và VietQR trên debit note; phiếu thu điền sẵn sau ngày chuyển hẳn | Ngưỡng duyệt, ngày áp dụng | ≥ 90% tiền ra có đề nghị duyệt; ≥ 80% tiền cước tự nhận ra khách |
| TC4 | Kéo giao dịch tự động (chỉ đọc, `hao` gọi ra), bot báo | Bên thứ ba, ngân sách | Dữ liệu không cũ quá 15 phút trong giờ làm việc, hai tuần |
| TC5 | Lãi lỗ chuyến/xe/khách; sao kê đối tác | — | Sếp dùng để quyết giá |
| Dọn | Tắt đọc ảnh tiền, bỏ khoản "từ ảnh", thay trang Thu chi bằng Dòng tiền | — | — |

## Tiêu chí nghiệm thu

Đợt 0:

- [x] `/thu-chi-tu-sinh.html` phục vụ cho quản lý; người dùng thường bị chặn như các trang quản lý khác.
- [x] Trang không gửi yêu cầu nào tới `/api/` (test browser chặn và đếm).
- [x] Dải "Bản thử · số bịa · không nối ngân hàng" luôn hiện ở mọi vai.
- [x] Bốn vai: Sếp và Nhân viên vừa 390×844 không cuộn ngang; Kế toán và Tiền hàng vừa 1280×720.
- [x] Kịch bản 11 bước chạy hết bằng nút Tiếp; sau mỗi bước, số trên Dòng tiền (tiền đang có, đang ứng, vào/ra hôm nay, Cần sếp) bằng bảng kỳ vọng trong test model.
- [x] Unit model: mỗi luật R1–R9 ít nhất một ca; phí trong và ngoài ngưỡng; ba lệnh ↔ một đề nghị; cặp đổi tiền; ví âm và hạn mức; chỉ vai người duyệt gỡ cờ; dòng việc riêng không vào tổng và chỉ chủ tài khoản thấy; số nguyên, không số thực.
- [x] Từ chối không lý do, số tiền không hợp lệ, thiếu người nhận bị chặn, báo dưới ô.
- [x] Bàn phím: mọi nút với tới bằng Tab, bấm bằng Enter/Space, focus thấy rõ; chữ thân ≥ 16px, vùng bấm ≥ 40px; trạng thái có chữ, không chỉ màu ([UX](../docs/ux-guidelines.md)).
- [ ] `npm run check` và `node scripts/check-secrets.js` xanh; Deploy hao xanh; mở được trên `hao` từ máy tính và iPhone.
- [ ] Người dùng tự đi hết kịch bản và xác nhận.

TC1–TC5: tiêu chí riêng viết khi sếp chốt (harness PostgreSQL cho mọi migration; tổng khách và phân bổ không đổi; bộ đọc sao kê bằng dữ liệu bịa; Playwright 390 và 1280).

## Phạm vi agent (đợt 0)

- Agent: claude ([`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md)).
- Review: sonnet medium (không ghi tiền, không DB).
- Được sửa: `cong-no-web-handoff/preview/thu-chi-tu-sinh*.{html,css,js}`, `cong-no-web-handoff/preview/test-thu-chi-tu-sinh-model.js`, `cong-no-web-handoff/preview/test-thu-chi-tu-sinh-browser.js`, một dòng `PAGES` trong `cong-no-web-handoff/web/v7_api_tables.py` (và test Python nếu có test liệt kê trang), mục Bằng chứng và ô tiêu chí của spec này.
- Ngân sách: khoảng 1.500 dòng (phần lớn là giao diện và dữ liệu bịa).
- Lệnh kiểm: `npm run check`; `node scripts/check-secrets.js`.
- Cấm: route API, bảng hay migration; gọi `/api/`; dữ liệu thật; thêm thư viện; sửa trang khác, agent Zalo, đường ghi tiền; thêm vào menu hay `USER_PAGES`.

## Hoàn tác

Đợt 0: revert PR (trang tĩnh, không dữ liệu). Các đợt sau: theo nhật ký triển khai từng migration.

## Ngoài phạm vi

Chuyển tiền hay duyệt lệnh qua web; tự ghi phiếu thu từ sao kê (quyết định sau); kế toán thuế, hóa đơn điện tử (chỉ là nguồn phụ, xét sau); chat riêng trên web.

## Câu hỏi cho sếp

1. Chốt hướng: tiền thật từ tài khoản và quỹ là gốc; nhóm chat chỉ để trao đổi và làm bằng chứng?
2. Danh sách tài khoản từng công ty, TK cá nhân dùng cho công ty, quỹ tiền mặt và người giữ; cho xuất một tháng sao kê để đo?
3. Ví khách TQ: bao nhiêu khách; tỷ giá tính khách là tỷ giá ngân hàng hay thỏa thuận (chênh lệch có tính là thu không); hạn mức ứng từng khách; ai duyệt ứng?
4. Duyệt chi: khoản nào, ngưỡng nào, ai duyệt thay; đã bật duyệt lệnh hai cấp ở ngân hàng chưa; từ ngày nào "không có đề nghị duyệt thì không chuyển"?
5. Tiền mặt: mọi lần giao tiền mặt đều cần đề nghị và ảnh biên bản; kiểm quỹ bao lâu một lần?
6. TK cá nhân: đưa vào hay ngưng dùng cho công ty từ ngày nào; ai thấy gì; công nợ có tách phần có và không hóa đơn không?
7. In mã thanh toán và VietQR trên debit note, nhờ khách lớn ghi mã khi chuyển?
8. Bot báo qua đâu; dùng dịch vụ đọc giao dịch tự động không, ngân sách; lãi lỗ cho một công ty hay cả nhóm?

## Bằng chứng

Số đo ở đầu spec: lượt đọc chỉ đọc ngày 24/11/2026 (`GET /api/v7/receipt-book`, `GET /api/v7/cash-chat`, `GET /api/v7/doixe` trên `hao`; đếm gói chat `/srv/v7/zalo-bundle` và kết quả đọc ảnh tại máy đọc chat; tin và ảnh nhóm WeChat 20–24/11). Chỉ số đếm; nội dung tin, ảnh, tên và số tiền không vào repo. Đợt 0 (24/11/2026, chạy tại máy, chưa lên `hao`): `node --test test-thu-chi-tu-sinh-model.js` 38 ca xanh (mỗi luật R1–R9 một ca, phí trong và ngoài ngưỡng cả đồng lẫn USD, ba lệnh ↔ một đề nghị, cặp đổi tiền, ví âm và hạn mức, chỉ vai Sếp gỡ cờ, việc riêng không vào tổng, số lớn hơn 2^53, bảng kỳ vọng 12 dòng cho Dòng tiền sau từng bước kể cả khi người bấm tay trước và khi lùi bằng nút Trước); `test-thu-chi-tu-sinh-browser.js` 20 ca xanh (390×844 Sếp và Nhân viên, 1280×720 Kế toán và Tiền hàng mọi tab, không cuộn ngang, chữ không dưới 13px, vùng bấm không dưới 40px, không request nào tới `/api/`, đi hết 11 bước bằng nút Tiếp và bằng Enter/Space, danh sách rỗng có chữ, localStorage hỏng vẫn chạy); `test_v7_ledger_api` có thêm một dòng: `/thu-chi-tu-sinh.html` trả 403 cho người dùng thường, 200 cho quản lý (trang không nằm trong `USER_PAGES`). Kịch bản không có việc nào ghi vào sổ nợ: phiếu thu điền sẵn chỉ hiện trong trang. Một lượt review độc lập (agent `reviewer`) tìm ra chín điểm, đã sửa và thêm test: từ chối rồi Tiếp vẫn chuyển tiền; chi trước khi duyệt làm ví trừ sớm và đề nghị kẹt; "Cần sếp" lệch số thẻ; cửa sổ R5 khác `v7_cash_chat.py` (nay 3 ngày trước, 7 ngày sau); tiêu điểm bàn phím rơi về đầu trang; thiếu lối về; khối kịch bản chiếm màn điện thoại; cặp nội bộ về muộn không gỡ cờ; phiếu điền sẵn USD sai đơn vị.

## Câu hỏi mở

- Giới hạn đã biết của bản thử (không ảnh hưởng kịch bản, ghi để TC1 tính lại): luật R8 phụ thuộc thứ tự dòng khi một chân là tài khoản cá nhân; bán USD ít hơn số USD đang chờ của ví thì ví chưa đổi và không có cảnh báo; trang không có menu, chỉ có nút "Về Tổng quan".
