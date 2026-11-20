# Sao kê ngân hàng làm nguồn tiền thật của trang Thu chi (SAO-KE-01)

Trạng thái: **ĐỀ XUẤT** (Claude, 20/11/2026). Chưa chốt, chưa code, chưa đăng ký dịch vụ nào, chưa đụng tài khoản ngân hàng nào. Chờ sếp và người dùng trả lời [câu hỏi cuối spec](#câu-hỏi-cho-sếp-và-người-dùng). Khi chốt sẽ có `docs/decisions/sao-ke-01.md`.

Nguồn: người dùng, chat 20/11/2026: đo thấy Zalo trên máy công ty gần như không nhận ảnh chuyển khoản của khách (chỉ một nhóm), nên chọn "tính sao kê ngân hàng" làm nguồn tiền thật. [`ZALO-THU-CHI-01`](zalo-thu-chi-real-time.md) Q7 đã chốt: nối ngân hàng để sau, spec riêng, sếp quyết vì cần cấp quyền đọc tài khoản và chưa kiểm chi phí. Spec này là spec riêng đó. `TELEGRAM-01` đã chốt: báo thu chi theo sự kiện vào nhóm Telegram.

Mọi số liệu về dịch vụ bên ngoài **tra ngày 20/11/2026**, chỉ đọc trang công khai; giá và điều khoản có thể đổi, phải tra lại trước khi quyết. Chỗ không tìm thấy thì ghi "không tìm thấy", không đoán.

## Câu hỏi mà spec trả lời

1. **Tiền khách chuyển vào đã thật sự về tài khoản chưa**, bao nhiêu, ngày nào, nội dung chuyển khoản ghi gì? (Zalo chỉ cho biết "khách báo đã chuyển".)
2. **Tiền về mà chưa có phiếu thu ở sổ khách** (chỗ hay sót nhất) và **phiếu thu mà ngân hàng chưa thấy tiền** (ghi nhầm, ghi sớm, hoặc tiền mặt).
3. **Tiền chi ra** (tài khoản công ty trả ra ngoài) có khớp sổ Đội xe không.
4. Có **giao dịch nào lọt** (sao kê thiếu dòng) không, để số "tiền thật" không im lặng sai.

Spec **không** thay đường ghi tiền. Giao dịch ngân hàng **không bao giờ tự ghi phiếu thu**; chỉ gợi ý, người nhập xác nhận bằng đúng nút "Ghi phiếu thu" đang có.

## Đã kiểm tra trong repo

- Phiếu thu `sokhach.receipt` đã có cột `reference` (tham chiếu, thêm ở migration `2026-10-21-v7-csm.sql`) và hình thức `THU TIỀN`, `CẤN TRỪ`, `ỨNG TRƯỚC`, `KHÁC`. Mã giao dịch ngân hàng ghi vào `reference` là cách ghép chắc nhất; `CẤN TRỪ` không phải tiền qua ngân hàng nên không đưa vào đối chiếu.
- `sokhach.contact_mark` (migration `2026-11-01-v7-zalo-group.sql`) là khuôn "bảng ngoài đường tiền": có `idempotency_key`, người làm, hủy bắt buộc lý do, trạng thái tính khi đọc, không VND vào số dư, không khóa tháng, không phân bổ. Bảng mới theo cùng khuôn.
- Trang Thu chi (PR-2 của `ZALO-THU-CHI-01`) đã có bảng trạng thái đối chiếu và hằng khoảng ngày `MATCH_BEFORE, MATCH_AFTER, MISSING_AFTER = 3, 7, 3` trong `web/v7_cash_chat.py`, khớp `sokhach._mark_json`. Spec này **dùng lại đúng các hằng đó** để ba chỗ không chấm khác nhau.
- Quyền: trang Thu chi chỉ cho quản lý ([`QUYEN-01`](../docs/decisions/quyen-01.md)); dữ liệu ngân hàng cũng chỉ cho quản lý.

## Tra cứu các cách lấy giao dịch (20/11/2026)

### A. Dịch vụ trung gian báo biến động số dư

**SePay** ([sepay.vn/bang-gia](https://sepay.vn/bang-gia.html), [developer.sepay.vn](https://developer.sepay.vn/en)):

- **Giá:** gói FREE 0 đồng, 50 giao dịch/tháng (vượt vẫn chạy, bị tính phí sau, mức phí không ghi); gói STARTUP từ 120 nghìn đồng/tháng, hạn mức từ 180 tới 986 nghìn giao dịch/tháng, trang không ghi giá từng bậc. "Giao dịch" là tiền **vào**; tiền ra không tính hạn mức (changelog). Gói SHOP theo cửa hàng không có API nên không dùng được. Số tài khoản ngân hàng: không giới hạn. Hoàn tiền trong 15 ngày đầu.
- **Ngân hàng:** kết nối trực tiếp 12 ngân hàng (Vietcombank, BIDV, VietinBank, MB, ACB, VPBank, TPBank, Sacombank, MSB, OCB, KienLongBank, Shinhan). Khác biệt theo loại tài khoản đáng chú ý: **Vietcombank doanh nghiệp và BIDV cá nhân/hộ kinh doanh chỉ nhận qua tài khoản ảo (VA), không có tiền ra**; BIDV doanh nghiệp, ACB, MB, TPBank có tiền ra. Trang giá nói ngân hàng còn lại qua SMS Banking, trang developer nói "chưa hỗ trợ": hai trang mâu thuẫn, phải hỏi SePay.
- **Lấy dữ liệu:** webhook (SePay gọi vào URL công khai của mình) **và** API kéo `GET /v2/transactions`, khóa API Bearer lấy trong cài đặt, 3 yêu cầu/giây mỗi IP, 100 bản ghi/trang, có `since_id` để kéo phần mới. Webhook yêu cầu URL công khai, địa chỉ nội bộ bị từ chối; thử lại 7 lần trong khoảng 33 phút, và tài liệu bảo mật **tự khuyên chạy cron 15–30 phút đối soát qua API** vì webhook có thể mất khi máy nhận ngừng quá 5 giờ.
- **Quyền cấp:** nhập thông tin internet banking hoặc kết nối OAuth tùy ngân hàng; trang không mô tả rõ quyền "chỉ xem" hay có thao tác được không. Không thấy tính năng chuyển tiền trong các trang đọc. **Không tìm thấy** nói SePay có lưu mật khẩu internet banking hay không.
- **Dữ liệu trả về:** mã giao dịch, thời điểm (giờ VN), số tài khoản, tiền vào/ra (số nguyên VND), số dư sau giao dịch (0 nếu ngân hàng không có), nội dung chuyển khoản gốc, mã tham chiếu ngân hàng. **Không thấy** tài khoản/tên người chuyển ở API kéo (webhook có thể có trong `description`).
- **Độ trễ:** "gần như tức thì" theo trang giá; không có con số giây.
- **Điều khoản dữ liệu:** có chứng nhận ISO 27001. Thời hạn lưu giao dịch "cấu hình được" nhưng chưa đọc con số; chính sách riêng tư và điều khoản sử dụng **chưa đọc**.

**Casso** ([casso.vn](https://casso.vn/), [flow.casso.vn/bang-gia](https://flow.casso.vn/bang-gia/), [tài liệu V2](https://flow.casso.vn/docs/v2/)):

- **Giá:** **không tìm thấy số tiền** (bảng giá tải bằng JavaScript). Cấu trúc: gói **năm** (không có gói tháng, không hoàn tiền sau khi thanh toán), tính theo số giao dịch (cả vào và ra) và số ngân hàng; gói Sponsor/Pioneer cho ngân hàng có API chính thức, gói Standard cho ngân hàng kết nối kiểu RPA. Dùng thử 14 ngày hoặc 100 giao dịch thật, không cần thẻ.
- **Ngân hàng:** "10+ ngân hàng", **không tìm thấy danh sách đầy đủ**. Official API cập nhật "realtime", RPA đồng bộ theo lịch (không ghi số phút). Một đường dẫn của Casso ghi ACB Biz cần ACB One Biz, số điện thoại duyệt lệnh, Safekey và OTP.
- **Lấy dữ liệu:** webhook (cần URL công khai HTTPS, trả 200 trong 5 giây, thử lại tới 17 lần/24 giờ rồi tạm dừng) **và** API kéo `GET /v2/transactions` (khóa API hoặc OAuth2; giới hạn theo gói: 2, 5 hoặc 20 yêu cầu/phút; sync tay 1 yêu cầu/phút mỗi tài khoản, MB Biz kiểu RPA 1 yêu cầu/15 phút).
- **Quyền cấp:** trang giá ghi "chỉ đọc dữ liệu ngân hàng". **Không tìm thấy** nói có lưu mật khẩu internet banking hay không, cũng không tìm thấy mô tả cơ chế RPA.
- **Dữ liệu trả về:** mã, tham chiếu, mô tả (nội dung chuyển khoản), số tiền, số dư, thời điểm, **tên và số tài khoản đối ứng**, ngân hàng đối ứng.
- **Lưu ý tài liệu:** tài liệu V2 ghi "dừng từ 31/12/2026", bản đang dùng là V3 (chưa đọc). Phải đọc V3 trước khi làm.
- **Điều khoản dữ liệu:** có ISO/IEC 27001:2022; chính sách bảo mật đã đọc chỉ nói về dữ liệu khách truy cập website; thỏa thuận sử dụng **chưa đọc**.

**Các dịch vụ khác** (MISA, JetPay BankHub, GPM Pay…) xuất hiện trong kết quả nhưng chưa đọc; không đánh giá ở đây.

### B. API trực tiếp của ngân hàng (open banking) cho tài khoản doanh nghiệp

- **Khung pháp lý:** Thông tư 64/2024/TT-NHNN (hiệu lực 1/3/2025) quy định Open API; danh mục cơ bản gồm lấy thông tin tài khoản và lịch sử giao dịch, với quy trình xin sự đồng ý của khách hàng và cấp/thu hồi mã truy cập. Bên thứ ba phải có hợp đồng với ngân hàng. Thông tư không cấm doanh nghiệp tự kết nối, nhưng thực tế kênh cho doanh nghiệp là sản phẩm ERP/H2H theo hợp đồng riêng.
- **VietinBank:** công khai nhất. Cổng openapi.vietinbank.vn có use case ERP "Sao kê", "Vấn tin chi tiết tài khoản" và "Notify biến động số dư nợ/có" ([danh sách](https://developer.vietinbank.vn/vtb/openbanking/system/files/2025-08/VietinBank_ERP_UseCase_Sao%20k%C3%AA_v1.0.pdf)). Điều kiện (theo hướng dẫn của MISA, không phải nguồn của ngân hàng): đăng ký với ngân hàng, user có vai trò chuyển tiền, khai báo IP, chứng thư số, tiền đề là dịch vụ eFAST và ERP. Tài liệu PDF của ngân hàng **chưa đọc được**.
- **BIDV:** portal [openapi.bidv.com.vn](https://openapi.bidv.com.vn/devportal/) có gói "Vấn tin thông tin tài khoản doanh nghiệp – kết nối iBank" (số dư, lịch sử giao dịch); đăng ký nhận API Key và Secret (hiện một lần), gọi qua user iBank và access token. Dữ liệu portal là sandbox.
- **TPBank:** có sandbox; báo chí nêu gói Biz Notify (biến động tức thời) và Biz Query (sao kê, số dư); không tìm thấy tài liệu kỹ thuật.
- **Vietcombank, MB, ACB, VPBank, Sacombank, Techcombank:** không tìm thấy tài liệu công khai về API sao kê/biến động cho doanh nghiệp nhỏ. Đường thực tế đi qua bên trung gian (mục A).
- **Phí, thời gian làm thủ tục, hợp đồng mẫu:** không tìm thấy ở ngân hàng nào, ngoài việc cổng thử của VietinBank miễn phí.
- **Chỉ quyền đọc:** **không tìm thấy** tài liệu nói doanh nghiệp được cấp quyền chỉ-đọc; VietinBank đòi user có vai trò chuyển tiền để đăng ký. Phải hỏi ngân hàng. Đây là điểm an toàn then chốt.
- **Kết luận:** doanh nghiệp logistics nhỏ tự kết nối trực tiếp hiếm khi thực tế (hợp đồng, IP cố định, chứng thư số, quy trình duyệt dành cho doanh nghiệp có ERP). Ngoại lệ có thể là VietinBank hoặc BIDV nếu công ty đã dùng eFAST hoặc iBank; hỏi chi nhánh trước.

### C. Không qua bên thứ ba

- **Tải sao kê từ internet banking doanh nghiệp (Excel/CSV, MT940):**
  - VietinBank có sao kê MT940 theo ngày, gửi qua SWIFT, email tới danh sách đã đăng ký, hoặc tải từ eFAST; cần ký hợp đồng dịch vụ MT940, phí không nêu; giao dịch sau giờ cắt vào sao kê ngày làm việc kế tiếp ([vietinbank.vn](https://vietinbank.vn/en/doanh-nghiep/san-pham-dich-vu/thanh-toan-quan-ly-dong-tien/sao-ke-dinh-dang-mt-940-31-html)). Eximbank cũng có MT940 ([eximbank.com.vn](https://eximbank.com.vn/en/corporate-other/mt-940-account-statement-service)).
  - VPBank NEOBiz có xuất sao kê/sổ phụ (nguồn mô tả ứng dụng); ACB ONE Biz xem sao kê trên app; VCB DigiBiz có cập nhật mẫu sao kê. **Không tìm thấy** nguồn chính thức về định dạng cột của file Excel ở ngân hàng nào, cũng không về sao kê tự động định kỳ. Phải tải một file mẫu thật (xóa dữ liệu trước khi đưa cho Claude xem) mới biết cột.
- **Email biến động số dư:** Techcombank nói email và thông báo trên app là kênh miễn phí, nhưng trang đó chỉ nói khách cá nhân. Với VCB, VietinBank, BIDV, MB, ACB, VPBank: **không tìm thấy** trang chính thức xác nhận email biến động cho tài khoản doanh nghiệp, **không tìm thấy** thông tin email có đủ nội dung chuyển khoản hay bị cắt, độ trễ, hay có DKIM. Tra DNS ngày 20/11/2026 cho chính sách DMARC của miền ngân hàng: Vietcombank `reject`; VietinBank và Techcombank `quarantine` (một phần thư); BIDV, MB, ACB, VPBank `none`. Chưa biết email biến động gửi từ miền nào, chỉ kiểm được trên một email thật.
- **Đọc hộp thư bằng Gmail API:** scope `gmail.readonly` là scope hạn chế của Google; ứng dụng chỉ dùng trong chính tổ chức Workspace của mình (loại Internal) không cần xác minh, ngoài tổ chức thì phải qua xác minh và đánh giá bảo mật ([Google](https://developers.google.com/workspace/gmail/api/auth/scopes), [production readiness](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)). `readonly` đọc **cả hộp thư**, nên nếu dùng phải là hộp thư riêng chỉ nhận email ngân hàng. IMAP bằng mật khẩu thường bị Google tắt với Workspace.
- **SMS Banking:** có bảng phí cho khách cá nhân (khoảng 10–15 nghìn đồng/tháng, 700 đồng/tin sau hạn mức, có ngưỡng số tiền); bảng phí doanh nghiệp không tìm thấy; **không tìm thấy** nói SMS có đủ nội dung chuyển khoản. Không đề xuất: không có API, và chuyển SMS về máy là thêm một mắt xích.

## So sánh

Cột "hao" = chạy được khi `hao` chỉ vào qua Tailscale, không mở cổng công khai (webhook cần cổng vào công khai, **không được đổi Tailscale nếu chưa hỏi**; kéo về là `hao` gọi ra ngoài, được).

| Cách | An toàn (ai giữ quyền gì, lộ gì) | Chi phí | Công sức cài | Độ đủ nội dung | Độ trễ | `hao` |
| --- | --- | --- | --- | --- | --- | --- |
| **1. Tải file sao kê, người nhập dán/tải lên web** | Không ai ngoài công ty giữ quyền; web chỉ nhận file đã tải. Không cấp quyền ngân hàng. Lộ: file nằm tạm ở máy người tải | 0 đồng (MT940 của VietinBank cần hợp đồng, phí không rõ) | Thấp: bộ đọc theo mẫu cột từng ngân hàng; cần một file mẫu | Đủ nếu file có cột nội dung và mã tham chiếu (chưa kiểm được) | Theo nhịp người tải (ngày, vài ngày) | Chạy, không cần mạng ra ngoài |
| **2. Đọc email biến động bằng Gmail API chỉ đọc** | Token chỉ đọc nhưng thấy cả hộp thư (dùng hộp thư riêng). Email có thể giả; phải kiểm DKIM | Email thường miễn phí (Techcombank cá nhân); doanh nghiệp chưa rõ | Trung bình: OAuth, lọc người gửi, kiểm DKIM, bộ đọc từng mẫu thư | **Chưa xác nhận** có đủ nội dung chuyển khoản | Gần tức thì nếu ngân hàng gửi ngay | Chạy (`hao` gọi ra Gmail) |
| **3. SePay, API kéo về từ `hao`** | Bên thứ ba giữ kết nối với ngân hàng (nhập thông tin internet banking hoặc OAuth; **chưa rõ có lưu mật khẩu, chưa rõ chỉ-đọc**). Lộ mọi giao dịch cho SePay. Khóa API đọc toàn bộ giao dịch, để ngoài repo | 0 đồng tới 50 giao dịch tiền vào/tháng; từ 120 nghìn đồng/tháng; hạn mức bậc cao chưa rõ giá | Thấp: một bộ kéo `since_id` | Đủ: nội dung gốc, mã tham chiếu, số tiền, giờ; thiếu tên/tài khoản người chuyển ở API kéo | Theo nhịp kéo (đề xuất 1–5 phút); dịch vụ nói gần tức thì | Chạy (kéo); **không dùng webhook** |
| **4. Casso, API kéo về từ `hao`** | Như SePay; ghi "chỉ đọc"; chưa rõ cơ chế RPA và lưu mật khẩu | **Chưa biết giá** (gói năm, không hoàn tiền); dùng thử 14 ngày | Thấp; **phải đọc V3** vì V2 dừng 31/12/2026 | Đủ, có thêm tên và số tài khoản đối ứng | Official API "realtime"; RPA theo lịch; giới hạn 2–20 yêu cầu/phút | Chạy (kéo) |
| **5. API ngân hàng trực tiếp** | Không qua bên thứ ba, nhưng thường đòi user có quyền chuyển tiền để đăng ký, chứng thư số, IP cố định | Chưa biết; VietinBank cổng thử miễn phí | Cao: hợp đồng, duyệt, chứng thư, tuần tới tháng | Đủ | Có kiểu đẩy (VietinBank, TPBank) và kéo | Kéo chạy; đẩy cần cổng vào |

## Đề xuất

**Đi hai bước, giữ phần lõi không phụ thuộc nguồn.**

1. **Bước đầu, không cần sếp cấp quyền gì: cách 1, tải sao kê.** Người nhập tải sao kê từ internet banking (mỗi ngày hoặc mỗi tuần) rồi đưa lên trang. Lý do: không cấp quyền ngân hàng cho ai, không gửi dữ liệu ra ngoài, không tốn tiền, và **chứng minh được giá trị của việc đối chiếu** (tiền về chưa vào sổ, phiếu chưa thấy tiền) trước khi sếp quyết chi tiền và quyền. Hạn chế: không tức thì; người dùng phải nhớ tải.
2. **Bước hai, khi sếp chấp nhận bên thứ ba: cách 3 hoặc 4, API kéo về từ `hao`.** Thêm một "nguồn" vào cùng bảng, không đổi phần đối chiếu. Chỉ kéo, không webhook, nên không đổi Tailscale. Dùng thử gói miễn phí/14 ngày trên **một** tài khoản trước, **chỉ sau khi sếp đồng ý** và người dùng tự cấp khóa. SePay có bảng giá công khai và API kéo rõ; Casso chưa lấy được giá. Chọn bên nào còn phụ thuộc ngân hàng của công ty ([câu hỏi 1](#câu-hỏi-cho-sếp-và-người-dùng)).

Không đề xuất: webhook (cần cổng công khai), SMS, và API ngân hàng trực tiếp (trừ khi sếp chọn VietinBank/BIDV và ngân hàng xác nhận quyền chỉ-đọc). Đọc email chỉ xét nếu ngân hàng xác nhận email biến động doanh nghiệp có đủ nội dung chuyển khoản.

## Người dùng và luồng (bước 1)

**Người thao tác:** sếp (xem, điện thoại 375–390px), người nhập và chủ sổ (xem, xác nhận, màn 1280×720). Danh tính lấy từ Tailscale ([`V7-ID`](../docs/decisions/v7-id.md)). Chỉ quản lý xem được dữ liệu ngân hàng.

### Luồng 1. Đưa sao kê lên (người nhập; bước đầu)

1. Mở trang **Thu chi**, bấm **Nhập sao kê**.
2. Chọn tài khoản (tên gọi tắt do quản lý khai, không số tài khoản đầy đủ) và file. Trang đọc thử và hiện **xem trước**: số dòng, khoảng ngày, tổng tiền vào, tổng tiền ra, bao nhiêu dòng mới, bao nhiêu dòng đã có (trùng), bao nhiêu dòng không đọc được.
3. Bấm **Nhập** thì dòng mới vào bảng giao dịch. Dòng trùng bị bỏ, không nhập hai lần. Dòng không đọc được số tiền hoặc ngày thì **không nhập** và được liệt kê; số trống không thành 0.
4. Nhập nhầm file thì **Hủy lô** (bắt buộc lý do), các dòng của lô ẩn khỏi đối chiếu, giữ vết.

### Luồng 2. Xem tiền thật (sếp, người nhập)

1. Trang Thu chi thêm khối **Ngân hàng**: tiền vào, tiền ra trong hôm nay và 7 ngày; **tiền về chưa vào sổ: K khoản**; **phiếu chưa thấy tiền: L khoản**; "Sao kê cập nhật lần cuối lúc …".
2. Mỗi dòng giao dịch: giờ, vào/ra, số tiền, nội dung chuyển khoản, trạng thái, nút liên quan (mở phiếu, mở sổ, Ghi phiếu thu).
3. Mỗi khoản thu/chi báo trong Zalo (khoản hiện có của trang) thêm cột **Ngân hàng**: "Tiền đã về lúc …" hoặc "Chưa thấy trên sao kê".
4. Lọc: Tiền về chưa vào sổ, Phiếu chưa thấy tiền, Lệch số, Chưa rõ của ai, Tất cả.

### Luồng 3. Từ tiền về tới phiếu thu (người nhập)

Ở dòng "Tiền về chưa vào sổ", **Ghi phiếu thu** mở đúng form ghi phiếu thu của sổ khách, **điền sẵn** ngày, số tiền, hình thức `THU TIỀN`, `reference` = mã giao dịch ngân hàng. Người nhập xem và bấm ghi như hôm nay; mọi luật tháng khóa, phân bổ, Lịch sử giữ nguyên. Spec **không** thêm đường ghi tiền thứ hai ([`UX-NEN-01`](../docs/decisions/ux-nen-01.md) M1). Nếu chưa chắc là của sổ nào thì chọn sổ ở hộp gợi ý; gợi ý không tự gắn khi có nhiều hơn một sổ.

### Luồng 4. Gắn hoặc loại một giao dịch (người nhập)

- **Gắn sổ** hoặc **gắn xe/tài xế** khi máy không đoán được.
- **Không phải thu chi của khách** (chuyển nội bộ giữa tài khoản công ty, vốn, lương, thuế…) kèm lý do, để dòng ra khỏi "chưa vào sổ".

Mọi lần bấm ghi người làm, trước → sau, như dấu tin của ZALO-GROUP-01. Các thao tác này **không ghi tiền**.

### Bị chặn

- **Sao kê cũ:** trang luôn ghi tuổi của giao dịch mới nhất; quá N ngày (đề xuất 3 ngày làm việc) thì cảnh báo vàng "tiền thật có thể chưa đủ". Web không giả là dữ liệu mới.
- **Sao kê thiếu dòng:** số dư sau giao dịch không liền mạch (số dư trước + vào − ra ≠ số dư sau) thì **chặn nhập lô đó** và chỉ ra chỗ hở. Ngân hàng không cung cấp số dư thì không kiểm được và ghi rõ "chưa kiểm liền mạch".
- **Không có quyền:** 403 như các trang quản lý.
- **Nguồn API kéo lỗi hoặc khóa hết hạn:** trang ghi "chưa kéo được từ lúc …" và máy canh báo email ([`CANH-BAO-01`](../docs/decisions/canh-bao-01.md)); không giả là đã đủ.

## Thiết kế dữ liệu (ĐỀ XUẤT)

Lưu ở PostgreSQL, **ngoài đường tiền**, theo khuôn `contact_mark`: không vào `v_outstanding_month`, không đổi phân bổ, không khóa tháng, không đổi `customer.version`, không VND nào vào số dư.

- `sokhach.bank_account`: tên gọi tắt, ngân hàng, 4 số cuối (để phân biệt), loại (thu/chi/cả hai), bật/tắt. **Không lưu số tài khoản đầy đủ.**
- `sokhach.bank_import_batch`: nguồn (`file`, `sepay`, `casso`), tài khoản, khoảng ngày, số dòng đọc/nhập/trùng/lỗi, người nhập, lúc nhập, `sha256` của file (chỉ băm, không lưu file), hủy (người, lúc, lý do).
- `sokhach.bank_txn`: `id`, `account_id`, `batch_id`, `source`, `source_txn_id` (mã ngân hàng/dịch vụ; duy nhất theo `account_id` + `source_txn_id` khi có, ngược lại băm của ngày + số tiền + số dư sau + nội dung + thứ tự dòng), `booked_at` (giờ giao dịch theo ngân hàng, giờ VN), `direction` (`in` | `out`), `amount_vnd bigint CHECK (> 0)`, `description` (nội dung chuyển khoản, ≤ 500 ký tự), `bank_ref`, `counterparty_name` (nếu nguồn có; xem câu hỏi dữ liệu), `balance_after bigint NULL`. Chỉ thêm dòng; không sửa, không xóa; hủy lô thì dòng ẩn khỏi đối chiếu.
- `sokhach.bank_txn_review`: gắn sổ/xe/người hoặc loại một giao dịch; `request_id` để bấm lặp không ghi hai lần; người làm, lý do, trước → sau; bản mới nhất có hiệu lực.

Mọi số tiền là VND `bigint` nguyên; đọc file từ chuỗi bằng bộ đọc chặt (dấu chấm hoặc dấu phẩy nghìn theo cấu hình từng ngân hàng, không qua số thực). Ô tiền trống là NULL và **dòng bị từ chối** (không thành 0). Hai cột ghi nợ và ghi có đều trống hoặc đều có số thì dòng lỗi. Ngày nghiệp vụ (ngày phiếu) và ngày giao dịch ngân hàng là hai thứ; chỉ so trong cửa sổ ngày, không đổi ngày phiếu.

Đọc DB chỉ qua hàm đọc theo khuôn hiện có; role app và role reader theo `DEPLOY-CLAUDE-01`. Chưa quyết định schema nằm trong `sokhach` hay schema riêng; PR-1 chốt.

## Đối chiếu (tính khi đọc, không lưu kết luận)

### Tiền vào với phiếu thu

| Mã | Khi nào | Câu hiện |
| --- | --- | --- |
| `BANK_RECEIPT_MATCH` | Có đúng một phiếu thu chưa hủy, đúng số, ngày phiếu từ `MATCH_BEFORE` ngày trước tới `MATCH_AFTER` ngày sau ngày giao dịch; hoặc `reference` của phiếu bằng mã ngân hàng | Đã có phiếu |
| `BANK_ONLY` | Không phiếu nào ứng, giao dịch đã quá `MISSING_AFTER` ngày | **Tiền về, chưa có phiếu** |
| `BANK_WAITING` | Như trên nhưng chưa quá `MISSING_AFTER` ngày | Chờ ghi phiếu |
| `AMOUNT_DIFF` | Có đúng một phiếu cùng sổ trong cửa sổ ngày nhưng khác số | Lệch: ngân hàng X, phiếu Y |
| `SUGGEST_BOOK` | Nội dung chuyển khoản chứa **đúng một** tên sổ (so không dấu, độ dài ≥ 3) | Có thể là sổ … (người xác nhận) |
| `SUGGEST_SUM` | Tổng ≤ 4 phiếu cùng sổ trong cửa sổ ngày bằng đúng số tiền | Một giao dịch, nhiều phiếu (người xác nhận) |
| `UNKNOWN` | Không đoán được | Chưa rõ của ai |
| `INTERNAL` | Hai giao dịch vào/ra khác tài khoản công ty, cùng số, trong 1 ngày; hoặc người dùng đánh dấu | Chuyển nội bộ |

### Phiếu thu với tiền thật

| Mã | Khi nào | Câu hiện |
| --- | --- | --- |
| `RECEIPT_BANKED` | Phiếu `THU TIỀN` có giao dịch vào ứng (một-một) | Tiền đã về |
| `RECEIPT_NOT_SEEN` | Phiếu `THU TIỀN` đã quá `MISSING_AFTER` ngày, sao kê đã cập nhật quá ngày phiếu, không giao dịch ứng | **Phiếu chưa thấy tiền trên sao kê** |
| `RECEIPT_CASH` | Người dùng đánh dấu phiếu là tiền mặt (hình thức `KHÁC` hoặc nút đánh dấu) | Tiền mặt, không qua ngân hàng |

Không xét phiếu `CẤN TRỪ` và `ỨNG TRƯỚC` (không phải tiền qua ngân hàng). Khi sao kê chưa phủ tới ngày phiếu thì **không kết luận** `RECEIPT_NOT_SEEN`: hiện "sao kê chưa tới ngày đó".

### Tiền ra với Đội xe

Tiền ra khớp một dòng chi (`doixe.dong_phi`) hoặc một lần ứng chưa hủy của Đội xe, đúng số, cửa sổ ngày như trên, thì `LEDGER_MATCH`. Chi không khớp là `BANK_ONLY_OUT` ("tiền ra chưa có trong sổ"); chi không thuộc Đội xe (văn phòng, lương, thuế) là `NO_LEDGER` chỉ liệt kê, như trang Thu chi hiện nay. Hoàn tiền cho khách là tiền ra của sổ khách, chỉ hiện và gợi ý, không ghi.

### Dùng chung với phần Zalo

Khoản báo trong Zalo (`ZALO-THU-CHI-01`) có thêm một chiều: khoản Zalo có giao dịch ngân hàng khớp (số, ngày, và tên hoặc `reference`) thì ghi "Ngân hàng xác nhận"; Zalo báo mà ngân hàng không thấy quá `MISSING_AFTER` ngày thì "Chưa thấy trên ngân hàng". Một giao dịch chỉ ứng với tối đa một khoản Zalo và tối đa một phiếu; hai ứng viên cho một giao dịch thì cả hai `shared`, người chọn.

Mọi chấm điểm bằng luật cố định, không đưa nội dung chuyển khoản vào model nào ([`MAY-CHAY-01`](../docs/decisions/may-chay-01.md) giữ nguyên tắc: chữ tự do của bên ngoài không tới model). Nội dung chuyển khoản là chữ do người ngoài viết, có thể chứa lệnh giả; web chỉ hiển thị dạng chữ thuần, thoát HTML.

## Telegram (`TELEGRAM-01`)

Dùng lại đường gửi và luật của TELEGRAM-01, thêm các sự kiện từ ngân hàng, vì đây mới là tiền thật:

- tiền về mà chưa có phiếu quá `MISSING_AFTER` ngày (`BANK_ONLY`);
- phiếu thu chưa thấy tiền quá hạn (`RECEIPT_NOT_SEEN`);
- tiền ra lớn bất thường: ngưỡng do sếp đặt, mặc định tắt;
- bản tổng cuối ngày: tổng vào, tổng ra, số khoản chưa vào sổ.

Nội dung tin: sổ hoặc tên gọi tắt tài khoản, số tiền, giờ, trạng thái, link mở khoản trên web. **Không gửi số tài khoản, tên người chuyển hay nội dung chuyển khoản gốc**, và không có tin nào kèm ảnh. Bot không nhận lệnh từ Telegram. Ai ở trong nhóm Telegram thì thấy số tiền ngân hàng của công ty; đó là rủi ro `TELEGRAM-01` đã chấp nhận cho thu chi, nhưng **số tiền ra và tổng cuối ngày là dữ liệu nhạy cảm hơn**, hỏi sếp ([câu hỏi 8](#câu-hỏi-cho-sếp-và-người-dùng)).

## Bí mật và quyền

- Khóa API (SePay, Casso) hoặc thông tin đăng nhập nếu có: **chỉ** trong `/etc/webdebit/sao-ke.env` trên `hao` (quyền đọc cho tài khoản chạy dịch vụ), không vào Git, nhật ký, ảnh chụp, tin Telegram hay đối số dòng lệnh. Có cờ tắt hẳn việc kéo. Người dùng tự tạo khóa trên trang của dịch vụ và đặt lên `hao`; Claude không tạo, không đọc khóa.
- **Mật khẩu internet banking không bao giờ đi qua web này, qua Claude hay qua repo.** Nếu dịch vụ trung gian đòi nhập mật khẩu internet banking thì người dùng nhập thẳng trên trang của họ, và đây là điểm sếp phải quyết ([câu hỏi 3](#câu-hỏi-cho-sếp-và-người-dùng)).
- Nên tạo user ngân hàng **riêng cho dịch vụ**, phân quyền xem sao kê, không có quyền lập hoặc duyệt lệnh chuyển tiền, nếu ngân hàng cho phép. Chưa tìm thấy nguồn xác nhận ngân hàng nào cho tách như vậy ở tài khoản doanh nghiệp.
- Chỉ quản lý đọc dữ liệu ngân hàng (route kiểu `ADMIN_ONLY` như `/api/v7/doixe`). Người dùng thường không thấy cả số tiền lẫn nội dung chuyển khoản.
- Dữ liệu ngân hàng không vào repo, fixture hay ảnh chụp bản xem; test dùng dữ liệu bịa. Tên người chuyển là thông tin của cá nhân bên ngoài: chỉ lưu nếu nguồn có và sếp đồng ý.

## Giao tiếp frontend–backend (ĐỀ XUẤT)

| Route (qua xác thực, chỉ quản lý) | Việc |
| --- | --- |
| `POST /api/v7/bank/import/preview` | nhận file, trả bản xem trước, **không ghi** |
| `POST /api/v7/bank/import` | ghi lô sau xem trước (cần `request_id`) |
| `POST /api/v7/bank/import/{id}/void` | hủy lô, bắt buộc lý do |
| `GET /api/v7/bank/txns?from=&to=&status=` | giao dịch kèm trạng thái, tổng, `bank_age`, số dòng chưa phủ ngày |
| `POST /api/v7/bank/review` | gắn hoặc loại một giao dịch |
| `GET /api/v7/cash-chat` | thêm cột `bank` cho mỗi khoản Zalo |

Tổng là VND `bigint`; giao dịch không có số tiền hợp lệ không cộng vào tổng và được đếm riêng.

## Đầu ra

1. Bảng giao dịch ngân hàng ngoài đường tiền, nhập được từ file sao kê, dòng trùng bị bỏ, lô hủy được.
2. Trang Thu chi có khối Ngân hàng và cột Ngân hàng cho khoản Zalo, với trạng thái ở trên.
3. "Ghi phiếu thu" điền sẵn từ giao dịch qua đường ghi phiếu hiện có, không đường mới.
4. Báo Telegram theo sự kiện ngân hàng (sau khi TELEGRAM-01 có code).
5. (Nếu sếp chọn bước hai) bộ kéo API chạy trên `hao`, cùng bảng, cùng đối chiếu.

## Hành vi và bất biến

- **Giao dịch ngân hàng không bao giờ ghi tiền.** Không tạo, sửa, hủy phiếu thu, dòng chi, ứng; không đổi phân bổ, khóa tháng, tổng khách.
- VND nguyên. Số tiền hoặc ngày không đọc được thì dòng bị từ chối, không thành 0, không vào tổng.
- Một giao dịch ứng với tối đa một phiếu (hoặc một khoản Zalo); không đoán khi có hơn một ứng viên.
- Mọi gắn, loại, hủy lô ghi người làm, trước → sau; hủy và loại bắt buộc lý do; bấm lặp cùng `request_id` chỉ ghi một lần.
- Không có đường nào để dịch vụ ngoài gọi vào `hao`. Không webhook; không đổi Tailscale, `pg_hba`, hay quyền ngoài runbook.
- Web luôn hiện tuổi của sao kê và không kết luận "chưa thấy" khi sao kê chưa phủ tới ngày đó.
- Khóa và mật khẩu ngoài repo; chữ tự do từ ngân hàng không đi vào model.

## Chia PR và cổng

| Bước | Nội dung | DB | Cổng hỏi |
| --- | --- | --- | --- |
| SK-0 | Trả lời [câu hỏi](#câu-hỏi-cho-sếp-và-người-dùng) và đưa một file sao kê mẫu (đã xóa dữ liệu thật, để ngoài repo) | Không | **Sếp và người dùng** |
| SK-1 | Bảng, hàm nhập có xem trước và hủy lô, harness PostgreSQL | Có, ngoài đường tiền | Migration tự triển khai theo `DEPLOY-CLAUDE-01`; **lần nạp dữ liệu thật đầu tiên hỏi người dùng** |
| SK-2 | Bộ đọc file theo mẫu ngân hàng, route đọc, đối chiếu thu/chi, khối Ngân hàng ở trang Thu chi | Không | — |
| SK-3 | "Ghi phiếu thu" điền sẵn, gắn/loại giao dịch, cột Ngân hàng cho khoản Zalo | Có (`bank_txn_review`) | — |
| SK-4 | Sự kiện Telegram từ ngân hàng | Không | Sau khi TELEGRAM-01 có code; **sếp chọn có gửi tiền ra và tổng cuối ngày không** |
| SK-5 | Bộ kéo API (SePay hoặc Casso), máy canh, cờ tắt | Không | **Sếp chấp nhận bên thứ ba; người dùng tự tạo khóa và đặt lên `hao`; đọc điều khoản dữ liệu của dịch vụ** |

- Agent: claude ([`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md)). Review: opus cho SK-1, SK-3 (DB, quyền) và SK-5 (bí mật); sonnet medium cho phần còn lại.
- Ngân sách: mỗi PR ≤ 600 dòng logic. Lệnh kiểm: `npm run check`; SK-1 và SK-3 thêm harness `tools/test_pg_*.py`.
- **Cấm:**
  - ghi tiền theo giao dịch ngân hàng;
  - webhook hoặc bất kỳ cổng vào công khai nào;
  - đăng ký dịch vụ, lấy khóa, đăng nhập ngân hàng, hoặc gửi dữ liệu ra ngoài trước khi sếp chốt;
  - lưu số tài khoản đầy đủ, mật khẩu hay khóa trong repo, nhật ký hay DB;
  - đưa nội dung chuyển khoản vào model;
  - đưa sao kê thật, tên khách, số tiền thật hay số tài khoản vào repo.

## Tiêu chí nghiệm thu

- [ ] Unit bộ đọc file (dữ liệu bịa): mỗi mẫu ngân hàng ra đúng ngày, vào/ra và VND nguyên; ô tiền trống hoặc sai khuôn thành dòng bị từ chối, không phải 0; cả hai cột nợ và có cùng trống hoặc cùng có số thì lỗi; mã hóa tiếng Việt (UTF-8 có và không BOM).
- [ ] Unit trùng lặp: nhập cùng file hai lần chỉ có một bộ dòng; file gối ngày một phần chỉ thêm dòng mới; hai giao dịch hợp lệ cùng ngày, cùng số, cùng nội dung nhưng khác số dư vẫn là hai dòng.
- [ ] Unit liền mạch số dư: số dư lệch một dòng thì chặn lô và chỉ đúng chỗ; ngân hàng không có số dư thì ghi "chưa kiểm liền mạch".
- [ ] Unit đối chiếu: mỗi mã trạng thái có ít nhất một ca; một phiếu không ứng với hai giao dịch; phiếu đã hủy, `CẤN TRỪ`, `ỨNG TRƯỚC` không tính; sao kê chưa phủ ngày thì không có `RECEIPT_NOT_SEEN`; đọc cùng hằng `MATCH_*` với `v7_cash_chat.py` (có test đọc hằng, như test SQL hiện có).
- [ ] Harness PostgreSQL: bảng không đổi dấu vân tay tổng khách, `v_outstanding_month`, phân bổ hay khóa tháng; bấm lặp chỉ ghi một lần; hủy lô và loại mà thiếu lý do bị từ chối; role app và role reader đúng quyền.
- [ ] Playwright, máy chủ giả, 1280×720 và 390×844: xem trước đúng số; nhập xong dòng hiện; lọc "Tiền về chưa vào sổ"; "Ghi phiếu thu" mở form điền sẵn; sao kê cũ hiện cảnh báo; người dùng thường nhận 403; dùng được bằng bàn phím.
- [ ] Không rò: nội dung chuyển khoản thoát HTML; Telegram không có số tài khoản, tên người chuyển hay nội dung gốc; `node scripts/check-secrets.js` sạch; không có khóa trong log.
- [ ] `npm run check` xanh.
- [ ] Trên `hao` (dữ liệu thật, sau khi được hỏi): nhập một sao kê một tuần, đối chiếu với phiếu thu, mọi khoản `BANK_ONLY` và `RECEIPT_NOT_SEEN` được người nhập xem và xác nhận là thật; tổng nợ khách không đổi sau khi nhập.
- [ ] Sếp và người dùng tự đi hết Luồng 1–3 trên bản thử và xác nhận.

## Hoàn tác

- **SK-1, SK-3:** revert app; bảng giữ lại hoặc `DROP` theo nhật ký triển khai, không gì trong đường tiền tham chiếu tới. Một lô nhập sai thì **hủy lô** (có lý do), không xóa tay.
- **SK-2, SK-4:** revert, không đụng dữ liệu; tắt gửi Telegram bằng cờ.
- **SK-5:** tắt cờ kéo; **thu hồi khóa API ở trang dịch vụ**, hủy liên kết ngân hàng ở trang dịch vụ, và yêu cầu dịch vụ xóa dữ liệu theo điều khoản; gỡ file `sao-ke.env`.

## Ngoài phạm vi

- Chuyển tiền, lập lệnh hay duyệt lệnh qua web. Web chỉ đọc.
- Tự ghi phiếu thu từ sao kê. Có thể xét **sau**, riêng, khi sao kê đã chạy ổn nhiều tháng và sếp muốn, nhưng cần quyết định mới.
- Ghi chi văn phòng, lương, thuế vào web (web chưa có sổ này).
- Đọc ảnh chuyển khoản (đã có `ANH-GEMINI-01`; ảnh vẫn là nguồn "khách báo", sao kê là nguồn "tiền thật").
- Webhook, SMS, API ngân hàng trực tiếp, các dịch vụ trung gian khác, ngoại tệ và tài khoản ngoài VND.

## Nguồn quyết định

- Người dùng, chat 20/11/2026: chọn "Tính sao kê ngân hàng" làm nguồn tiền thật (nêu ở đầu spec).
- [`ZALO-THU-CHI-01`](../docs/decisions/zalo-thu-chi-01.md) Q7: nối ngân hàng để sau, spec riêng, sếp quyết; sửa 20/11/2026: nguồn "đã chi thật" là sao kê.
- `TELEGRAM-01` (quyết định nằm ở PR FinanceBullkk/webdebit#554, chưa vào `main` lúc viết spec; đổi thành link khi đã merge): báo theo sự kiện, bí mật ngoài repo, chỉ báo.
- [`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md): ảnh không đọc thay số; đối chiếu sao kê ngân hàng CÒN MỞ, làm sau (spec này).
- [`UX-NEN-01`](../docs/decisions/ux-nen-01.md) M1: tiền chỉ vào sổ bằng phiếu thu.
- [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md), [`CANH-BAO-01`](../docs/decisions/canh-bao-01.md), [`QUYEN-01`](../docs/decisions/quyen-01.md), [`MAY-CHAY-01`](../docs/decisions/may-chay-01.md).
- CÒN MỞ: tất cả [câu hỏi dưới đây](#câu-hỏi-cho-sếp-và-người-dùng).

## Câu hỏi cho sếp và người dùng

Claude không có số liệu về ngân hàng của công ty nên các câu dưới đây **chưa trả lời được từ repo**.

1. **Ngân hàng nào, mấy tài khoản, loại gì?** Mỗi ngân hàng một tài khoản thu, một tài khoản chi hay dùng chung? Tài khoản doanh nghiệp, cá nhân hay hộ kinh doanh? Quyết định chọn SePay hay Casso, và việc có nhận được **tiền ra** hay không, tùy câu này (ví dụ Vietcombank doanh nghiệp chỉ qua tài khoản ảo ở SePay).
2. **Một tháng có khoảng bao nhiêu giao dịch tiền vào?** (Đếm trên sao kê, chỉ cần số đếm.) Để biết gói miễn phí 50 giao dịch có đủ không và ước chi phí.
3. **Chấp nhận bên thứ ba giữ kết nối tới tài khoản ngân hàng hay không?** Nếu có: dịch vụ nhập thông tin internet banking hay OAuth, có lưu mật khẩu không, có chỉ-đọc không, có tạo được user riêng không chuyển tiền được không? Claude **không tra được** các điểm này; phải hỏi dịch vụ hoặc ngân hàng, và đọc điều khoản dữ liệu.
4. **Ai được cấp quyền và ai giữ khóa?** Chủ tài khoản hoặc kế toán trưởng làm việc với ngân hàng; người dùng đặt khóa lên `hao`. Ai là người duyệt?
5. **Ngân sách mỗi tháng** cho dịch vụ này là bao nhiêu, hay chỉ làm bằng sao kê tải tay (0 đồng)?
6. **Ngân hàng của công ty có xuất sao kê Excel/CSV hoặc MT940 không, cột gồm gì?** Người dùng đưa một file mẫu đã xóa dữ liệu thật (để ngoài repo, chỉ cho Claude xem tên cột và vài dòng bịa). Nếu là VietinBank hoặc Eximbank thì hỏi về MT940 gửi email.
7. **Ngân hàng có gửi email biến động số dư cho tài khoản doanh nghiệp không, nội dung có đủ nội dung chuyển khoản không?** Nếu có và đủ thì cách 2 (đọc hộp thư riêng) thành phương án không qua bên thứ ba.
8. **Telegram có gửi tiền ra và tổng cuối ngày không**, và ai ở trong nhóm? Dữ liệu ngân hàng nhạy cảm hơn ảnh chuyển khoản của khách.
9. **Có lưu tên người chuyển (nếu dịch vụ trả về) không?** Mặc định đề xuất: không, chỉ nội dung chuyển khoản.
10. **Giữ dữ liệu ngân hàng bao lâu trên `hao`?** Mặc định đề xuất: như phiếu thu, không xóa; hủy lô khi nhập sai.
11. **Tiền mặt:** công ty còn thu tiền mặt không? Nếu có, đánh dấu phiếu tiền mặt thế nào cho khỏi báo "chưa thấy tiền".
12. **Một khách chuyển một lần cho nhiều sổ** hoặc nhiều lần cho một phiếu có thường xảy ra không? Quyết định có cần `SUGGEST_SUM` ngay hay để sau.

## Bằng chứng

**Tra cứu 20/11/2026**, chỉ đọc trang công khai bằng công cụ tìm kiếm và đọc trang, không đăng ký, không tạo tài khoản, không lấy khóa, không gửi dữ liệu của công ty ra ngoài (câu tìm chỉ chứa tên dịch vụ hoặc ngân hàng). Hạn chế phải biết:

- bảng giá Casso tải bằng JavaScript nên **không lấy được số tiền**;
- tài liệu PDF API của VietinBank và BIDV không đọc được; phần điều kiện đăng ký lấy từ hướng dẫn bên thứ ba;
- điều khoản sử dụng, chính sách riêng tư và thời hạn lưu dữ liệu của SePay và Casso **chưa đọc**;
- bảng DMARC lấy từ truy vấn DNS công khai, không phải tài liệu của ngân hàng;
- không có nguồn chính thức nào cho "email biến động doanh nghiệp đủ nội dung" hoặc "quyền chỉ-đọc cho doanh nghiệp".

Chưa chạy bộ kiểm nào, vì chưa có mã. Bằng chứng của repo: các file, bảng và hằng đã nêu ở [Đã kiểm tra trong repo](#đã-kiểm-tra-trong-repo).
