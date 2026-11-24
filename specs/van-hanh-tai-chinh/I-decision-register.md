# I. Sổ quyết định cho chủ doanh nghiệp (Business Owner Decision Register)

Trạng thái: **11 câu chặn P0-a ĐÃ CHỐT** theo phương án A ngày 24/11/2026 ([`SO-TIEN-01`](../../docs/decisions/so-tien-01.md)); các câu khác **CÒN MỞ** (Claude lập 24/11/2026). Khuyến nghị không phải quyết định; code không dựa vào câu nào chưa có người chốt. Câu đã chốt chuyển thành file `docs/decisions/<id>.md`.

[← Mục lục](README.md) · Quy tắc liên quan: [D](D-business-rules.md) · Rollout: [H](H-migration-rollout.md)

Cột **Chặn**: P0-a, P0-b, P0-c, P1 = chưa chốt thì chưa làm bước đó; "Không" = cải tiến, làm được sau.

## 1. Tóm tắt

| ID | Quyết định | Khuyến nghị | Chặn | Người chốt |
| --- | --- | --- | --- | --- |
| QD-01 | Hướng v3 và cách chia P0 | Theo v3, chia P0-a/b/c có cổng | P0-a · **ĐÃ CHỐT A** | Chủ DN |
| QD-02 | Tài khoản thí điểm | TK VND công ty, không có tiền hàng, sau khi đo tỷ lệ cước về USD | P0-a · **ĐÃ CHỐT A** | Chủ DN, kế toán |
| QD-03 | Danh mục đủ pháp nhân/tài khoản/quỹ; tài khoản cá nhân | Lập danh mục ngay; không đưa TK cá nhân vào P0 | P1 | Chủ DN |
| QD-04 | Giờ cutoff, lịch, chồng kỳ, người tải | Tải 17h, kỳ từ ngày làm việc trước | P0-a · **ĐÃ CHỐT A** | Chủ DN, kế toán |
| QD-05 | Phạm vi V7-CSM (1) "không tiền chưa rõ chủ trên web" | Chỉ áp cho sổ nợ | P0-a · **ĐÃ CHỐT A** | Chủ DN |
| QD-06 | Tách nhiệm vụ, trùng vai, agent | Vai theo F1; trùng vai có cờ + tóm tắt tuần; agent không ghi dữ liệu tiền | P0-a · **ĐÃ CHỐT A** | Chủ DN |
| QD-07 | Định dạng file VCB và bộ đọc | File gốc `.xlsx`/CSV bằng thư viện chuẩn; `.xls` thì thêm thư viện ghim băm; không mở/lưu lại | P0-a · **ĐÃ CHỐT A** | Kế toán, kỹ thuật |
| QD-08 | Bảo vệ, lưu trữ dữ liệu ngân hàng | File gốc trong DB, quyền hẹp, mã hóa mọi bản sao lưu, log truy cập | P0-a · **ĐÃ CHỐT A** | Chủ DN, kế toán |
| QD-09 | Sổ kế toán chính thức | Sổ tiền là sổ quản trị + CSV | P0-a · **ĐÃ CHỐT A** | Kế toán |
| QD-10 | Số dư mở và bằng chứng | Đầu tháng, sao kê ngày trước, người khác đối chiếu | P0-a · **ĐÃ CHỐT A** | Kế toán |
| QD-11 | Danh mục phân loại | Danh sách đích P0 + 10–15 mục chi | P0-a · **ĐÃ CHỐT A** | Kế toán |
| QD-12 | Khoản nào phải duyệt, ngưỡng, duyệt thay, khẩn, hạn | Mọi khoản chi duyệt trước, trừ danh sách định kỳ; duyệt bù ≤ 1 ngày; hạn duyệt 7 ngày | P0-b | Chủ DN |
| QD-13 | Xác minh người nhận mới/đổi tài khoản | Gọi lại qua kênh đã biết, ghi kết quả | P0-b | Chủ DN |
| QD-14 | Ai duyệt đề nghị do chính sếp tạo | Người duyệt thay chỉ định; nếu không có: ngoại lệ ghi cờ + hậu kiểm tuần | P0-b | Chủ DN |
| QD-15 | Báo thu | Dùng lại "Khách báo đã chuyển" | P0-c | Chủ DN |
| QD-16 | Một nguồn ghi phiếu thu | Giữ máy theo Sheet tới quyết định chuyển hẳn; sau đó ghi từ ngân hàng từng sổ | P0-c (ghi) | Chủ DN |
| QD-17 | Sổ khách thuộc pháp nhân nào | Một pháp nhân mặc định + ngoại lệ; ánh xạ đủ trước P0-c | P0-c | Chủ DN |
| QD-18 | Khách trả cước bằng USD | Sổ nợ ghi VND thực nhận khi bán USD; đo tỷ lệ ở Discovery | P0-c | Kế toán |
| QD-19 | Chỉ định tháng, trả dư, bên thứ ba | Giữ luật hiện hành (nợ cũ trước, dư thành số âm) | Không | Chủ DN |
| QD-20 | Bản chất tiền khách Trung Quốc | Cổng pháp lý/kế toán trước P1 | P1 | Chủ DN, kế toán, pháp lý |
| QD-21 | Ngưỡng tự động; phí, chênh, xóa chênh | Không tự động tới khi shadow đạt ngưỡng; dòng phí do người tạo | P0-c | Kế toán |
| QD-22 | Cách tính số dư ước tính | Thận trọng: chỉ trừ chi đã báo; thu đã báo hiện riêng | P0-b | Chủ DN |
| QD-23 | Thông báo | P0-a không thông báo; từ P0-b chỉ số đếm + link | Không | Chủ DN |
| QD-24 | Ai ký review ngày, hạn ngoại lệ | Kế toán ký (có cờ) + sếp review tuần + người khác tự tải sao kê tháng | P0-a · **ĐÃ CHỐT A** | Chủ DN, kế toán |
| QD-25 | Đóng băng đọc chat/ảnh để tính tiền | Đóng băng phần tính tiền, giữ đọc chat để xem | Không (nên trước P0-b) | Chủ DN |
| QD-26 | Mã thanh toán trên debit note | Lưu bản phát hành + mã có chữ số kiểm; QR tùy chọn | Không | Chủ DN |

Chặn P0-a: 11 câu (QD-01, 02, 04–11, 24) — cả 11 đã chốt ngày 24/11/2026 theo [`SO-TIEN-01`](../../docs/decisions/so-tien-01.md). Chặn P0-b: 4. Chặn P0-c: 5. Chặn P1: 2. Không chặn: 4.

## 2. Chi tiết

### QD-01 — Hướng v3 và cách chia P0

- **Vì sao:** mọi phần sau phụ thuộc; v3 gom ba phase vào một P0 có một cổng.
- **Phương án:** (A) theo v3 + chia P0-a/b/c như [F2 ADR-TIEN-18](F2-adr.md#adr-tien-18--chia-p0-thành-ba-bước-có-cổng) — mỗi bước tự có giá trị, tự lùi; thêm cổng. (B) v3 nguyên văn — ít cổng, nhưng P0 phải chờ quyết định chuyển hẳn khỏi Sheet. (C) chỉ P0-a rồi xét — nhỏ nhất, chưa kiểm soát chi.
- **Khuyến nghị:** A.

### QD-02 — Tài khoản thí điểm

- **Vì sao:** cổng P0 đo trên tài khoản này; tài khoản có nghiệp vụ chưa hỗ trợ không được vào vận hành chính thức (v3 §3.3).
- **Phương án:** (A) TK VND công ty thu cước nhiều nhất — gần sổ nợ, nhưng có thể thiếu phần cước về USD. (B) TK USD — nhiều cước/tiền hàng, nhưng cần tỷ giá, tiền khách (P1). (C) TK VND chi nhiều nhất — tốt cho P0-b, ít thu.
- **Khuyến nghị:** A nếu Discovery cho thấy phần lớn cước về VND; nếu không, C cho P0-a/P0-b và đưa USD vào P1.

### QD-03 — Danh mục đủ; tài khoản cá nhân

- **Vì sao:** thiếu tài khoản thì "tiền đang có" sai; tài khoản cá nhân có rủi ro riêng tư, thuế.
- **Phương án:** (A) không đưa TK cá nhân, chuyển dần thu về TK công ty. (B) đưa vào phạm vi có căn cứ, dòng việc riêng chỉ giữ số. (C) đưa toàn bộ — rủi ro riêng tư cao.
- **Khuyến nghị:** lập danh mục ngay; A cho P0; B nếu buộc phải ở P1.

### QD-04 — Cutoff, lịch, chồng kỳ, người tải

- **Vì sao:** quyết định "số dư tới lúc nào" và cách bắt giao dịch sau giờ.
- **Phương án:** (A) tải 17h ngày làm việc, kỳ từ ngày làm việc trước — gần thời gian thực hơn, ngày cuối chưa trọn. (B) tải 8h sáng hôm sau — ngày trước đã trọn, dữ liệu trễ hơn. 
- **Khuyến nghị:** A (theo v3), xác nhận bằng file mẫu; người tải là kế toán, người tải đối chiếu định kỳ là người khác.

### QD-05 — Phạm vi V7-CSM (1)

- **Vì sao:** [`V7-CSM`](../../docs/decisions/v7-csm.md) (1) ghi "không có tiền chưa rõ chủ trên web"; P0 phải hiện tiền chưa rõ.
- **Phương án:** (A) câu đó chỉ áp cho sổ nợ; tiền chưa rõ chỉ ở sổ tiền, không vào sổ nợ. (B) giữ nghĩa rộng — P0 không hiện được giao dịch chưa rõ, trái mục tiêu.
- **Khuyến nghị:** A, ghi quyết định sửa phạm vi.

### QD-06 — Tách nhiệm vụ, trùng vai, agent

- **Vì sao:** chỉ 2 login người ghi sổ (đo 23/11/2026); [`V6-DB`](../../docs/decisions/v6-db.md) bỏ người duyệt thứ hai ở sổ nợ; [`TU-LAM-01`](../../docs/decisions/tu-lam-01.md) cho agent tự ghi dữ liệu, đổi quyền.
- **Phương án:** (A) bảy vai, cấm tự duyệt, trùng vai nhập/review có cờ + tóm tắt tuần, agent không ghi dữ liệu tiền, DB login riêng. (B) giữ QUYEN-01 cho sổ tiền — mọi login ghi được, không đạt kiểm soát. (C) giao thêm người review độc lập hằng ngày — tốt nhất, cần nhân sự.
- **Khuyến nghị:** A; C khi có người. COSO chấp nhận kiểm soát thay thế khi không tách được nhiệm vụ.

### QD-07 — Định dạng file VCB và bộ đọc

- **Vì sao:** không đoán cột (v3 §4.1); mở/lưu lại bằng Excel làm đổi file gốc; thư viện chuẩn Python không đọc được `.xls` cũ.
- **Phương án:** (A) `.xlsx` gốc, thư viện chuẩn. (B) chỉ có `.xls` → thêm một thư viện đọc `.xls`, ghim phiên bản + băm, cô lập trong bộ đọc. (C) CSV nếu ngân hàng có. (D) mở rồi lưu lại bằng Excel — **loại**.
- **Khuyến nghị:** A hoặc C; B nếu buộc; không D.

### QD-08 — Bảo vệ và lưu trữ dữ liệu ngân hàng

- **Vì sao:** file gốc chứa số tài khoản đầy đủ, tên đối tác; bản sao lưu trên `hao` hiện chưa mã hóa (`tools/v7_backup.py:364-365`).
- **Phương án:** (A) file gốc trong DB, chỉ vai nhập/review đọc, mã hóa mọi bản sao lưu (sửa công cụ sao lưu), log truy cập. (B) thêm mã hóa file gốc trong DB với khóa ngoài DB (cần kiểm extension trên `hao`; khóa đi qua phiên SQL). (C) không lưu file gốc, chỉ băm + ô đã che — bằng chứng yếu.
- **Khuyến nghị:** A (+B nếu khả thi). Thời hạn lưu theo chính sách lưu chứng từ của kế toán.

### QD-09 — Sổ kế toán chính thức

- **Phương án:** (A) sổ tiền là sổ quản trị + CSV. (B) dựng sổ cái quản trị — tốn, rủi ro hai sổ cái. (C) tích hợp trực tiếp phần mềm kế toán — cần biết phần mềm, giao diện.
- **Khuyến nghị:** A; kế toán cho biết phần mềm và định dạng muốn nhận.

### QD-10 — Số dư mở

- **Khuyến nghị:** ngày bắt đầu đầu tháng dương lịch, giờ VN; số dư từ sao kê ngày trước; người khác kế toán tự tải đối chiếu; nhập bằng lệnh có bằng chứng.

### QD-11 — Danh mục phân loại

- **Phương án:** (A) danh sách đích P0 ([F1 §3](F1-kien-truc-ky-thuat.md#3-mô-hình-dữ-liệu-logic)) + 10–15 mục chi. (B) hệ thống tài khoản kế toán ngay — chính xác hơn nhưng chậm, cần kế toán. (C) tự do — báo cáo vô dụng.
- **Khuyến nghị:** A, có ánh xạ sang tài khoản kế toán sau.

### QD-12 — Chính sách duyệt chi

- **Phương án:** (A) mọi khoản chi duyệt trước, trừ danh sách khoản định kỳ đã duyệt khung; khoản khẩn được chi trước và duyệt bù trong 1 ngày làm việc. (B) chỉ khoản trên ngưỡng — ít thao tác, lọt khoản nhỏ lặp lại. (C) hậu kiểm — không phòng ngừa.
- **Khuyến nghị:** A; hạn duyệt 7 ngày; người duyệt thay khi sếp vắng.

### QD-13 — Xác minh người nhận

- **Phương án:** (A) gọi lại qua số đã biết, ghi kết quả. (B) hai người xác nhận. (C) không xác minh.
- **Khuyến nghị:** A cho mọi người nhận mới hoặc đổi tài khoản.

### QD-14 — Đề nghị do chính sếp tạo

- **Phương án:** (A) người duyệt thay chỉ định duyệt — đúng maker–checker, có thể hình thức. (B) sếp tự duyệt như ngoại lệ ghi cờ, kế toán hậu kiểm tuần — thực tế, là ngoại lệ có kiểm soát bù. (C) miễn duyệt — không kiểm soát.
- **Khuyến nghị:** A nếu có người phù hợp; nếu không, B.

### QD-15 — Báo thu

- **Phương án:** (A) dùng lại "Khách báo đã chuyển" (`contact_mark`). (B) màn báo thu mới có tiền tệ, tài khoản, mục đích — thêm một lớp nhập. (C) không có báo thu.
- **Khuyến nghị:** A (ADR-TIEN-14).

### QD-16 — Một nguồn ghi phiếu thu

- **Vì sao:** máy đang ghi phiếu theo Sheet; ghi thêm từ ngân hàng là ghi công nợ hai lần.
- **Phương án:** (A) giữ máy theo Sheet, sổ tiền chỉ đối chiếu — an toàn, ít giảm nhập. (B) từng sổ chuyển sang ghi từ ngân hàng, tắt máy theo Sheet cho sổ đó — giảm nhập lặp, rủi ro chuyển đổi. (C) cả hai — **loại**.
- **Khuyến nghị:** A tới quyết định chuyển hẳn ([`CHUYEN-HAN-01`](../../docs/decisions/chuyen-han-01.md)); B từng sổ sau đó.

### QD-17 — Sổ khách thuộc pháp nhân nào

- **Phương án:** (A) một pháp nhân mặc định + ngoại lệ ghi rõ. (B) ánh xạ đủ từng sổ. (C) thêm pháp nhân vào schema sổ nợ — đổi `sokhach`, ngoài P0.
- **Khuyến nghị:** A cho P0-a, B trước P0-c.

### QD-18 — Khách trả cước bằng USD

- **Vì sao:** debit note mặc định in tài khoản USD ([`TAI-KHOAN-COT-E-01`](../../docs/decisions/tai-khoan-cot-e-01.md)); sổ nợ chỉ ghi VND thực nhận (V7-CSM (2)).
- **Phương án:** (A) ghi VND thực nhận khi bán USD; giao dịch USD chờ tới khi bán. (B) quy đổi theo tỷ giá ngày nhận — chênh lệch khi bán phải xử lý riêng. (C) sổ nợ theo USD — đổi động cơ sổ nợ.
- **Khuyến nghị:** A; đo tỷ lệ cước về USD ở Discovery.

### QD-19 — Chỉ định tháng, trả dư, bên thứ ba

- **Phương án:** (A) giữ luật hiện hành ([`V7-BE`](../../docs/decisions/v7-be.md), [`CAN-DU-01`](../../docs/decisions/can-du-01.md)). (B) cho chỉ định tháng — đổi `record_receipt`, phân bổ lại, test lại toàn bộ sổ nợ.
- **Khuyến nghị:** A; bên thứ ba trả hộ luôn qua review.

### QD-20 — Tiền khách Trung Quốc

- **Phương án:** (A) cổng pháp lý/kế toán trước P1; mô hình giữ hộ chỉ khi hợp đồng phù hợp. (B) coi là doanh thu bán hàng — không dùng mô hình ví. (C) dựng ví ngay — **loại**.
- **Khuyến nghị:** A; P0 chỉ gắn nhãn.

### QD-21 — Ngưỡng tự động; phí, chênh

- **Phương án:** (A) không tự động tới khi shadow ≥ 2 tháng, độ chính xác ≥ 99,5% theo giá trị, 0 sai nghiêm trọng; phí/chênh do người tạo dòng riêng. (B) tự áp mức A ngay. (C) dung sai tự xóa chênh — trái v3.
- **Khuyến nghị:** A.

### QD-22 — Số dư ước tính

- **Phương án:** (A) thận trọng (ADR-TIEN-16). (B) đối xứng như v3 §6 — đẹp hơn thực tế khi báo thu không về. (C) không hiện ước tính.
- **Khuyến nghị:** A.

### QD-23 — Thông báo

- **Phương án:** (A) không thông báo ở P0-a. (B) từ P0-b, chỉ số đếm + link nội bộ. (C) gửi chi tiết — **loại** (dữ liệu nhạy cảm).
- **Khuyến nghị:** A rồi B.

### QD-24 — Review ngày, hạn ngoại lệ

- **Phương án:** (A) kế toán ký ngày (trùng vai có cờ), sếp review tuần, người khác tự tải sao kê tháng; hạn ngoại lệ theo [B §7](B-quy-trinh-as-is-to-be.md#7-xử-lý-ngoại-lệ). (B) người review độc lập ký mỗi ngày. (C) chỉ review tháng — phát hiện muộn.
- **Khuyến nghị:** A; B khi có người.

### QD-25 — Đóng băng đọc chat/ảnh để tính tiền

- **Vì sao:** sửa phạm vi [`ZALO-THU-CHI-01`](../../docs/decisions/zalo-thu-chi-01.md) Q2 và [`ANH-GEMINI-01`](../../docs/decisions/anh-gemini-01.md); đo 24/11/2026 cho thấy chat không phải nguồn tiền tin được.
- **Phương án:** (A) đóng băng phần tính tiền, giữ đọc chat để xem và trao đổi. (B) giữ như hiện tại. (C) tắt hẳn đọc chat.
- **Khuyến nghị:** A.

### QD-26 — Mã thanh toán trên debit note

- **Phương án:** (A) lưu bản phát hành debit note + mã thanh toán có chữ số kiểm, in kèm; QR tùy chọn. (B) giữ như hiện tại (số sinh ở trình duyệt, không lưu).
- **Khuyến nghị:** A ở P0-c/P1 (v3 coi QR/mã là cải tiến tùy chọn).
