# PHIEU-WEB-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Từ 1/12/2026 mọi phiếu thu nhập trên web ([`WEB-CHINH-01`](web-chinh-01.md)), nên khung **Ghi phiếu thu** của Sổ khách phải ghi được mọi kiểu phiếu đang gặp trên Sheet, cho cả login người dùng ([`QUYEN-01`](quyen-01.md)). Phiên kiểm toàn bộ website giao 25/11/2026; Claude đặt cách làm dưới đây (ĐỀ XUẤT, không đổi luật tiền, không thêm hàm SQL).

1. **Phiếu không rõ ngày trả.** Khung có ô đánh dấu "Không rõ ngày trả". Đánh dấu thì ô ngày tắt, người chọn tháng khách trả (12 tháng tới tháng hiện tại, không chọn sẵn để không ghi nhầm tháng). Phiếu ghi:
   - **ngày** = ngày cuối tháng đó, không sau hôm nay (giờ VN) — đúng luật phiếu Sheet không ngày chủ sổ chốt 4/11/2026 (`month_end` ở `web/v7_sheet_fix.py`, xem [`MAY-DOI-SOAT-01`](may-doi-soat-01.md)). Hàm phía trang là `CongNoFormat.symbolicDate`; hai bên chạy chung bộ ca ở `cong-no-web-handoff/tests/golden/ngay-tuong-trung.json`, lệch luật là test đỏ;
   - **tham chiếu** = chữ người gõ + đuôi ` (ngày tượng trưng)`, đuôi mà Bảng thu, ngày trả thật và chữ tham chiếu trên sổ đã nhận ra ([`BANG-THU-01`](bang-thu-01.md)). Không gõ gì thì chữ là "Không rõ ngày" (server cắt khoảng trắng hai đầu, đuôi đứng một mình sẽ mất dấu cách và thôi khớp);
   - bước xem lại ghi rõ "(ngày tượng trưng)". Biết ngày thật sau thì sửa ngày ở dòng phiếu như phiếu thường.
   Cấn trừ cần ngày cụ thể: hình thức CẤN TRỪ không đi cùng "Không rõ ngày trả".

2. **Một lần chuyển cho nhiều sổ.** Nút "Chia cho nhiều sổ…" của khung mở khung riêng, mang sẵn chữ đang gõ. Người nhập ngày, hình thức (trừ CẤN TRỪ), tổng tiền khách chuyển, tham chiếu, rồi chia: sổ đang mở đứng đầu, thêm sổ đang hoạt động bằng ô tìm (sổ lưu trữ, sổ đã có trong danh sách không hiện).
   - **Chặn ở trang** khi tổng các phần khác tổng chuyển (nói rõ còn thiếu hay thừa bao nhiêu), phần trống hay 0 đ, một sổ hai lần, ít hơn hai sổ, ngày sau hôm nay.
   - **Mỗi phần là một phiếu riêng ở sổ đó**: một lệnh `record_receipt` mỗi sổ như phiếu thường (FIFO trong sổ đó, người làm, Lịch sử), cùng ngày, hình thức và tham chiếu. Khóa chống ghi trùng riêng từng sổ, đặt lúc xem lại.
   - **Không có giao dịch chung nhiều sổ** (không thêm hàm SQL, không đổi đường ghi tiền). Trang gửi lần lượt; lệnh lỗi thì dừng, bước xem lại ghi từng sổ "Đã ghi PH-…", "Không ghi được" kèm câu của máy chủ, "Chưa rõ đã lưu" hay "Chưa ghi". "Ghi tiếp" chỉ gửi phần chưa ghi, bằng đúng khóa cũ, nên phần máy chủ đã lưu mà trang chưa nhận được không thành hai phiếu. Sổ đổi từ lúc xem lại thì trang đọc phiên bản mới và gửi lại một lần cùng khóa.
   - Bước xem lại hiện còn nợ trước → sau của từng sổ, và **cảnh báo** (không chặn) khi tham chiếu đã có ở phiếu web khác trong tháng của ngày trả, đọc từ Bảng thu. Hai lần chuyển cùng chữ "CK" là thường, nên chỉ hỏi người.
   - **Đóng khi còn phiếu chưa ghi thì hỏi trước, không bỏ lần chia dở** (review độc lập 25/11/2026: bỏ rồi chia lại với khóa mới sẽ ghi lần hai các sổ đã lưu). "Đóng, ghi sau" giữ nguyên các khóa, bấm lại "Chia cho nhiều sổ…" là về đúng bước kết quả. Nút "Bỏ N phiếu chưa ghi" chỉ có khi không còn phiếu "chưa rõ đã lưu".
   - Phần bị từ chối hay chưa gửi sửa được số tiền ngay ở bước kết quả. Tổng mọi phần vẫn phải bằng tổng chuyển. Phần đổi số nhận khóa mới, phần đã ghi giữ nguyên. Phần "chưa rõ đã lưu" không sửa được, chỉ gửi lại đúng lệnh cũ.
   - Thiếu tham chiếu thì bước xem lại nhắc ghi mã giao dịch ngân hàng (không chặn).
   - **Lần chia dở lưu ở máy** (localStorage của trình duyệt, từ lúc gửi lệnh đầu tới khi mọi phần xong hay người bỏ). Tải lại trang hay sang sổ khác rồi mở lại "Chia cho nhiều sổ…" thì về đúng bước kết quả với các khóa cũ. Trước khi gửi mỗi lệnh, phần đó được lưu là "chưa rõ" cùng khóa của nó. Trang không biết login (danh tính chỉ ở máy chủ, qua Tailscale), nên trạng thái gắn với trình duyệt của máy. Còn phần chưa xong thì trình duyệt hỏi trước khi rời trang.
   - Sổ trong lần chia đã có phiếu web chưa hủy giống phần đó thì phần đó mặc định **không ghi**, người bấm "Vẫn ghi" mới ghi. "Giống" là cùng tham chiếu và số tiền (Bảng thu của tháng); lần chia không có tham chiếu thì cùng số tiền, ngày cách không quá 3 ngày (đọc cả tháng liền kề).
   - **Trạng thái chia dở lưu theo trình duyệt của máy, không theo login.** Hai người dùng chung một trình duyệt thì thấy chung lần chia dở. Bản lưu hỏng (sai kiểu, thiếu khóa) thì tự xóa và báo người kiểm Bảng thu trước khi chia lại.
   - **Khung chia chỉ mở để ghi ở một tab** (review #679): tab mở khung giữ khóa trình duyệt (`navigator.locks`) tới khi đóng khung hay đóng tab. Tab khác mở khung thì chỉ xem lần chia dở, mọi nút ghi và ô sửa đều tắt. Trình duyệt không có `navigator.locks` thì dùng dấu nhịp trong localStorage (dấu của tab khác còn mới dưới 15 giây thì chỉ xem).
   - Bản lưu gắn mã của lần chia. Trang chỉ ghi bản lưu khi bản trên máy trống hay cùng lần chia; lệch thì dừng, không gửi lệnh và không ghi đè. Còn một lần chia dở khác thì không bắt đầu lần chia mới. Bản lưu được kiểm đủ kiểu, tổng các phần bằng tổng chuyển, mỗi sổ một phần.
   - Kiểm trùng khi không tham chiếu so cả dòng thu sổ gốc lẫn phiếu web.
   - Phiếu không rõ ngày không đi đường này: chia nhiều sổ cần ngày cụ thể.

3. **Dán nhiều phiếu vào một sổ.** Nút "Dán nhiều phiếu…" của khung mở ô dán. Người chép từ Sheet các cột theo thứ tự **Ngày trả · Số tiền · Hình thức · Tham chiếu**, cột cố định theo Tab, ô trống giữ chỗ (Hình thức trống là THU TIỀN; ghi được THU TIỀN, ỨNG TRƯỚC, KHÁC; chữ khác là lỗi, không đoán). Dòng đầu không có chữ số ở ô ngày là dòng tiêu đề.
   - Trang đọc bảng ở model (`parseReceiptPaste`) và xem trước từng dòng, tổng tiền, tổng còn nợ trước → sau.
   - **Còn dòng lỗi thì không ghi phiếu nào**: ngày sai, ngày sau hôm nay, số tiền không đọc được, hình thức không hiểu. CẤN TRỪ phải ghi từng phiếu vì cần chọn sổ lấy tiền.
   - Theo review độc lập 25/11/2026:
     - **Số nghi nhầm đơn vị**: dưới 100.000 đ hay trên 1 tỷ đ. Khoản trả lẻ dưới 1 triệu là thật nên không hỏi (review lần 2 đổi ngưỡng từ luật ô giá sang luật riêng của phiếu thu, `receiptDoubt`). Số đọc bằng bộ đọc chung: "1,500" là 1.500 đ. Phải bấm "Đúng số này" từng dòng, hoặc "Đúng cả bảng" một lần, mới ghi được. **Khung một phiếu dùng cùng luật**: số ngoài khoảng đó phải bấm "Đúng số này" ở bước xem lại.
     - **Dòng có thể đã ghi** mặc định **không ghi**, người bấm "Vẫn ghi" mới ghi. Hai trường hợp:
       - sổ đã có phiếu chưa hủy cùng số tiền, ngày cách không quá 3 ngày (như hàng chờ phiếu Sheet);
       - một dòng trước trong cùng bảng cùng số tiền, cùng tham chiếu, ngày cách không quá 3 ngày.
     - Bản xem trước ghi ngày bằng chữ cạnh ngày số ("1 tháng 11"): bảng ghi tháng trước ngày mà cả hai phần ≤ 12 thì máy không nhận ra, người nhìn chữ thì thấy. Bản xem trước còn nhắc khi bảng có dòng kiểu tháng/ngày (phần sau lớn hơn 12), khi lô trải nhiều tháng, hay khi có dòng nằm ở tháng đang khóa. Các nhắc này không chặn.
     - **Ghi đúng bản đã xem trước**: lúc bấm Ghi, nếu danh sách dòng sẽ ghi hay phiên bản sổ khác lúc vẽ bản xem trước, trang dừng, vẽ lại bản xem trước, người bấm lại.
   - Ghi bằng chuỗi lệnh của sổ như dán cột giá (`submitSeries`): mỗi dòng một lệnh `record_receipt` theo thứ tự, lệnh sau dùng phiên bản lệnh trước. Máy chủ từ chối thì dừng: dòng đã ghi rời khỏi ô, dòng lỗi và các dòng sau ở lại để sửa. Mất mạng thì ô dán được xóa (bấm Ghi lần nữa sẽ thành hai phiếu). Nút Thử lại ngay trong khung gửi lại đúng lệnh đó rồi ghi nốt, không ghi hai lần; Thử lại vẫn mất kết nối thì nút vẫn còn.
4. **Ghi phiếu từ trang Thu chi.** Khoản thu "Chờ vào sổ" hay "Chưa vào sổ" đã gắn một sổ khách và có số tiền thì có nút **Ghi phiếu**. Nút mở Sổ khách của sổ đó với khung Ghi phiếu thu điền sẵn ngày của khoản, số tiền và tham chiếu: ảnh thì "CK <ngân hàng> <giờ> (ảnh Zalo)", tin thì "Zalo: <chữ tin>". Khung ghi rõ là điền sẵn từ Thu chi.
   - **Người vẫn xem lại và tự bấm ghi.** Tin hay ảnh không tự ghi tiền ([`ZALO-THU-CHI-01`](zalo-thu-chi-01.md)).
   - Phiếu nháp sang trang sổ qua `sessionStorage` (không đưa số tiền lên địa chỉ trang), dùng một lần, hết hạn sau 15 phút, chỉ nhận ở đúng sổ.
   - Ảnh ghi ngày quá cũ (`old_txn`) không có nút.
   - **Quyền:** người dùng chốt 25/11/2026 mở cả trang Thu chi cho login người dùng ([`QUYEN-01`](quyen-01.md) sửa đổi 25/11/2026), nên người nhập thấy nút Ghi phiếu. Lệnh ghi kết luận xem xét (`POST /api/v7/cash-chat/review`, nút "Xử lý") vẫn chỉ quản lý.

## Ngày / nguồn

25/11/2026, phiên kiểm toàn bộ website giao việc theo `WEB-CHINH-01`. Đo chỉ đọc trên `hao` cùng ngày: từ 1/10/2026 có 104 phiếu, đều từ login quản lý, trong đó 6 phiếu ngày tượng trưng; login người dùng chưa ghi phiếu nào.

## Hiệu lực và giới hạn

ĐỀ XUẤT của Claude trong phạm vi việc được giao; cả bốn mục không đổi DB, API hay quyền. ĐÃ KIỂM CHỨNG bằng test trang (`test-cong-no-format.js`, `test-so-khach-v7-model.js`, `test-thu-chi-model.js`, `test-so-khach-v7-entry-browser.js`, `test-so-khach-v7-split-browser.js`, `test-so-khach-v7-paste-receipts-browser.js`, `test-thu-chi-browser.js`) và unittest `test_v7_sheet_fix.py`. Người nhập đi thử trên `hao` là bước còn lại.

<!-- du-lieu-gia: 1.000.000 100.000 -->
