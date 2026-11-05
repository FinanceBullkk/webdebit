# Sổ quyết định v1

Nguồn chuẩn bị gộp 21/10/2026: bản đã commit `test/pg18-schema-characterization` tại `cfa10f1`; riêng `V7-COPY` trích dòng đang sửa trong file quyết định ở checkout chính (chưa commit), đã loại số liệu nguồn. Đây là ghi nhận nguồn, không chốt thêm chính sách hay kiểm lại live. Các mô tả chưa triển khai/báo cáo chạy là trạng thái ở ngày ghi; bằng chứng phiên này ở [báo cáo chuẩn bị V7](v7-merge-prep.md).

Mỗi quyết định là một file trong [`decisions/`](decisions/); bảng dưới chỉ để tìm. Nội dung, nguồn và trạng thái (ĐỀ XUẤT/ĐÃ CHỐT/ĐÃ TRIỂN KHAI/ĐÃ KIỂM CHỨNG/CÒN MỞ) đầy đủ nằm trong từng file: đọc file của ID liên quan, không suy quy tắc từ cột tóm tắt.

**Thêm hoặc sửa quyết định:** sửa đúng file của ID đó. Quyết định mới tạo file `decisions/<id-viết-thường>.md` theo mẫu các file có sẵn và thêm một dòng vào bảng; không ghi nội dung quyết định vào bảng. Trạng thái triển khai app ghi theo lượt `Deploy hao` (xem [quy trình](development.md#quy-trình-pr-và-triển-khai)), không mở PR tài liệu riêng chỉ để ghi đã triển khai.

| ID | Chủ đề (không thay nội dung file) | Lưu ý |
| --- | --- | --- |
| <a id="w01"></a>[W01](decisions/w01.md) | GitHub là nơi dev/AI phát triển chung |  |
| <a id="opening"></a>[OPENING](decisions/opening.md) | Replay 13/10 làm opening | Thay bởi [OPENING-SO-GOC](#opening-so-goc) |
| <a id="d01"></a>[D01](decisions/d01.md) | Tách người nhập/duyệt | Thay bởi [V6](#v6) |
| <a id="q01"></a>[Q01](decisions/q01.md) | Self-host, Tailscale, danh tính người thao tác |  |
| <a id="q02"></a>[Q02](decisions/q02.md) | Duyệt gắn với revision bất biến | Không còn áp dụng theo V6 |
| <a id="charge-01"></a>[CHARGE-01](decisions/charge-01.md) | Hợp đồng ghi một charge chuyến mới |  |
| <a id="trip-key"></a>[TRIP-KEY](decisions/trip-key.md) | Mã chuyến = booking + container |  |
| <a id="legacy-a"></a>[LEGACY-A](decisions/legacy-a.md) | Chuyến cũ không booking: giữ nợ, bỏ truy vết |  |
| <a id="opening-final"></a>[OPENING-FINAL](decisions/opening-final.md) | Opening 13/10 đủ cho chuyến trước 14/10 | Thay bởi [MOC-CHUYEN-MOI](#moc-chuyen-moi) |
| <a id="price-zero"></a>[PRICE-ZERO](decisions/price-zero.md) | Cấu phần giá 0đ chỉ cảnh báo |  |
| <a id="price-maker"></a>[PRICE-MAKER](decisions/price-maker.md) | Người nhập được tự xác nhận giá |  |
| <a id="simplify"></a>[SIMPLIFY](decisions/simplify.md) | Đơn giản hóa fixture ghi ngay |  |
| <a id="dup-01"></a>[DUP-01](decisions/dup-01.md) | Mỗi mã chuyến một charge |  |
| <a id="join-01"></a>[JOIN-01](decisions/join-01.md) | Duyệt bảng nối opening ↔ mã chuyến |  |
| <a id="newtrip-01"></a>[NEWTRIP-01](decisions/newtrip-01.md) | Chuyến mới tự coi là ngoài opening, trừ khi kiểm trùng |  |
| <a id="alt-key-01"></a>[ALT-KEY-01](decisions/alt-key-01.md) | Mã thay thế khi thiếu booking |  |
| <a id="booking-edit-01"></a>[BOOKING-EDIT-01](decisions/booking-edit-01.md) | Booking sửa sau khi ghi nợ |  |
| <a id="frontend"></a>[FRONTEND](decisions/frontend.md) | Quy trình frontend: duyệt mockup trước | Thay bởi [CLAUDE-ALL-01](#claude-all-01) |
| <a id="date"></a>[DATE](decisions/date.md) | Ngày xe nhập kho là ngày nghiệp vụ chuyến |  |
| <a id="d03"></a>[D03](decisions/d03.md) | Thu mới trừ kỳ nợ cũ trước |  |
| <a id="future-01"></a>[FUTURE-01](decisions/future-01.md) | Cấm ngày ghi sổ trong tương lai (giờ VN) |  |
| <a id="v5-ux"></a>[V5-UX](decisions/v5-ux.md) | Chín điểm thiết kế sổ công nợ V5 |  |
| <a id="v5-gd"></a>[V5-GD](decisions/v5-gd.md) | Mốc giao diện V5 đã duyệt |  |
| <a id="v6-thu"></a>[V6-THU](decisions/v6-thu.md) | Bảng thu riêng | Hết hiệu lực 19/10/2026 |
| <a id="v6"></a>[V6](decisions/v6.md) | Sổ công nợ theo Sheet đang dùng |  |
| <a id="v6-db"></a>[V6-DB](decisions/v6-db.md) | Bỏ người duyệt thứ hai ở đường ghi tiền DB |  |
| <a id="opening-so-goc"></a>[OPENING-SO-GOC](decisions/opening-so-goc.md) | Sổ gốc là chuẩn số dư đầu |  |
| <a id="v7-so"></a>[V7-SO](decisions/v7-so.md) | Màn sổ khách V7, ổ khóa từng tháng |  |
| <a id="v7-id"></a>[V7-ID](decisions/v7-id.md) | Người thao tác là danh tính Tailscale |  |
| <a id="v7-mig"></a>[V7-MIG](decisions/v7-mig.md) | Chuyển dữ liệu từ Sheet theo phương án lai |  |
| <a id="v7-be"></a>[V7-BE](decisions/v7-be.md) | Quy tắc backend V7 (phụ phí trống, FIFO…) | (6) số nợ từng tháng thay bởi [CAN-DU-01](#can-du-01) |
| <a id="v7-mh"></a>[V7-MH](decisions/v7-mh.md) | Mặt hàng gắn theo sổ khách |  |
| <a id="v7-tong"></a>[V7-TONG](decisions/v7-tong.md) | Loại tab không có tên trên TONG |  |
| <a id="moc-chuyen-moi"></a>[MOC-CHUYEN-MOI](decisions/moc-chuyen-moi.md) | Mốc chuyến mới |  |
| <a id="v7-copy"></a>[V7-COPY](decisions/v7-copy.md) | Bản sao dữ liệu thật V7 và cách hiện lịch sử |  |
| <a id="v7-csm"></a>[V7-CSM](decisions/v7-csm.md) | Chính sách V7 còn mở (D04–D07, Lịch sử) |  |
| <a id="song-song-01"></a>[SONG-SONG-01](decisions/song-song-01.md) | Chạy song song Sheet và web |  |
| <a id="song-song-02"></a>[SONG-SONG-02](decisions/song-song-02.md) | Mốc nạp clean-v2 và ngày song song |  |
| <a id="song-song-03"></a>[SONG-SONG-03](decisions/song-song-03.md) | Hai khách bị giữ sau mốc (A3) |  |
| <a id="chuyen-han-01"></a>[CHUYEN-HAN-01](decisions/chuyen-han-01.md) | Chưa chuyển hẳn khỏi Sheet: người nhập vẫn ghi Sheet, chưa khóa; xét lại sau đối soát cuối tháng 11/2026 | Chốt 5/11/2026; không đổi code |
| <a id="nhap-sheet-01"></a>[NHAP-SHEET-01](decisions/nhap-sheet-01.md) | Nhập và sửa chuyến kiểu Sheet | Vế (1) bảng nhập thay bởi [NHAP-SHEET-02](#nhap-sheet-02) |
| <a id="nhap-sheet-02"></a>[NHAP-SHEET-02](decisions/nhap-sheet-02.md) | Bỏ bảng nhập chuyến; chuyến lấy từ Sheet |  |
| <a id="thu-sheet-01"></a>[THU-SHEET-01](decisions/thu-sheet-01.md) | Phiếu thu từ Sheet lên web bằng hàng chờ |  |
| <a id="dash-01"></a>[DASH-01](decisions/dash-01.md) | Trang tổng quan công nợ | Nội dung khối thay bởi [DASH-03](#dash-03) |
| <a id="mh-01"></a>[MH-01](decisions/mh-01.md) | Mặt hàng lấy từ cột LOAI HANG của TONG |  |
| <a id="so-gon-01"></a>[SO-GON-01](decisions/so-gon-01.md) | Sổ khách gọn | Hàng nhập phiếu từng tháng và danh sách tháng bên phải thay bởi [SO-GON-04](#so-gon-04) |
| <a id="so-gon-02"></a>[SO-GON-02](decisions/so-gon-02.md) | Phiếu thu danh sách riêng, phiếu hủy gom gọn, bỏ cột cộng dồn | Mục (3) phần thanh tháng/dòng tổng sửa bởi [SO-GON-03](#so-gon-03) |
| <a id="so-gon-03"></a>[SO-GON-03](decisions/so-gon-03.md) | Mỗi số tiền của tháng hiện một lần | Vế "dính đầu khi cuộn" của thanh tháng thay bởi chip tháng của [SO-GON-04](#so-gon-04) |
| <a id="so-gon-04"></a>[SO-GON-04](decisions/so-gon-04.md) | Sổ khách một tháng đang làm: thanh tháng, gập tháng cũ, một nút Ghi phiếu thu có xem lại, hỏi khi khóa/mở tháng | Đầu sổ sửa 31/10/2026 khi code PR 2c (người dùng đồng ý); PR 2d (Lịch sử, bàn phím) thêm trường đọc `actor_name` vào GET sổ; H1 thay bởi [SO-GON-05](#so-gon-05) |
| <a id="so-gon-05"></a>[SO-GON-05](decisions/so-gon-05.md) | Sổ khách một tháng trên màn hình, chip tháng là chỗ chọn tháng duy nhất, dòng tóm tắt tháng, bảng co giãn | Thay H1 của [SO-GON-04](#so-gon-04) |
| <a id="so-gon-06"></a>[SO-GON-06](decisions/so-gon-06.md) | Sổ khách: phiếu thu thành khối ở đầu tháng, một thanh việc ở đầu sổ | Thay vế phiếu thu bên phải của [SO-GON-02](#so-gon-02)/[SO-GON-04](#so-gon-04) và sửa (a) của SO-GON-04 |
| <a id="so-chi-tiet-01"></a>[SO-CHI-TIET-01](decisions/so-chi-tiet-01.md) | Sổ hai dòng hiện theo cột bảng kê, tô màu, chỉ xem; nguồn là tab `CHI TIET ...` trên Sheet |  |
| <a id="ct-2so"></a>[CT-2SO](decisions/ct-2so.md) | Cấn trừ giữa hai sổ |  |
| <a id="phu-phi-01"></a>[PHU-PHI-01](decisions/phu-phi-01.md) | Phụ phí nhiều loại |  |
| <a id="xoa-thu-goc-01"></a>[XOA-THU-GOC-01](decisions/xoa-thu-goc-01.md) | Xóa khoản thu sổ gốc |  |
| <a id="da-thu-01"></a>[DA-THU-01](decisions/da-thu-01.md) | Đã thu theo ngày thu, như Sheet |  |
| <a id="claude-all-01"></a>[CLAUDE-ALL-01](decisions/claude-all-01.md) | Claude làm hết, bỏ bắt buộc mockup Penpot |  |
| <a id="bang-gia-01"></a>[BANG-GIA-01](decisions/bang-gia-01.md) | Bảng giá theo ngày hiệu lực, giá TT/giá khách |  |
| <a id="chung-tu-01"></a>[CHUNG-TU-01](decisions/chung-tu-01.md) | Dán chứng từ vào phiếu thu |  |
| <a id="presence-01"></a>[PRESENCE-01](decisions/presence-01.md) | Thấy ai đang online, ô đang chọn, con trỏ chuột |  |
| <a id="debit-note-01"></a>[DEBIT-NOTE-01](decisions/debit-note-01.md) | Xuất debit note theo tháng công nợ (Excel + PDF) |  |
| <a id="xoa-dc-thang-01"></a>[XOA-DC-THANG-01](decisions/xoa-dc-thang-01.md) | Xóa dòng điều chỉnh cả tháng |  |
| <a id="deploy-claude-01"></a>[DEPLOY-CLAUDE-01](decisions/deploy-claude-01.md) | Claude tự triển khai SQL/migration lên hao |  |
| <a id="gia-nguon-01"></a>[GIA-NGUON-01](decisions/gia-nguon-01.md) | Đơn giá web lấy từ sổ gốc tới ngày chuyển hẳn |  |
| <a id="dash-03"></a>[DASH-03](decisions/dash-03.md) | Tổng quan quản lý công nợ: hạn trả, rủi ro, tab Việc cần làm | Cách trình bày thay bởi [DASH-04](#dash-04) rồi [DASH-05](#dash-05); quy tắc giữ |
| <a id="dash-04"></a>[DASH-04](decisions/dash-04.md) | Tổng quan v2: mỗi câu hỏi một hình, không câu kết luận | Cách trình bày thay bởi [DASH-05](#dash-05) |
| <a id="dash-05"></a>[DASH-05](decisions/dash-05.md) | Tổng quan ít chữ theo canvas: chip mức rủi ro thay ma trận, bấm tên mở Tình hình, bảng triệu, nhãn "Không quá hạn" |  |
| <a id="can-du-01"></a>[CAN-DU-01](decisions/can-du-01.md) | Nợ từng tháng theo chuẩn tuổi nợ: khoản dư cấn vào tháng nợ cũ nhất | Thay vế số nợ từng tháng của [V7-BE](#v7-be) (6) |
| <a id="debit-note-02"></a>[DEBIT-NOTE-02](decisions/debit-note-02.md) | Mẫu Debit Note v3 sếp duyệt: bố cục, 8 loại phí, quy tắc tính, kiểm tra trước phát hành | Thay bố cục và điểm (3) thiếu giá của [DEBIT-NOTE-01](#debit-note-01) |
| <a id="nhac-no-01"></a>[NHAC-NO-01](decisions/nhac-no-01.md) | Theo dõi đòi nợ: tab Đòi nợ + nút Copy tin nhắc; sửa đổi 30/10/2026: trang Chat Zalo đọc nội dung từ bản xuất (ZALO-CHAT-01); sửa đổi 4/11/2026: ẩn tab Đòi nợ khỏi menu và nhắc nợ ở trang khách, API và dữ liệu vẫn còn | Đã code; bản xuất chat chưa đặt lên `hao` |
| <a id="access-01"></a>[ACCESS-01](decisions/access-01.md) | Chỉ login Tailscale trong danh sách mới dùng được web V7; login lạ nhận 403 `LOGIN_NOT_ALLOWED`; chế độ Serve không có danh sách thì API không khởi động | Danh sách đặt trên `hao` (drop-in), ngoài Git |
| <a id="trang-khach-01"></a>[TRANG-KHACH-01](decisions/trang-khach-01.md) | Trang khách: sổ khách mở rộng thành bốn thẻ Tình hình, Sổ, Trao đổi, Hồ sơ; hứa trả, gắn hội thoại Zalo, ghi lần xuất debit note | PR A1 (vỏ, thanh thẻ), A2 (thẻ Tình hình), A3 (Trao đổi, Hồ sơ) đã lên `hao`; A4 (đường vào) đã code, xong giai đoạn A; B, C chưa |
| <a id="ux-nen-01"></a>[UX-NEN-01](decisions/ux-nen-01.md) | Mục tiêu sản phẩm: bỏ Sheet mà không mất độ đúng; năm chỉ số M1–M5; UX làm theo thứ tự người dùng → luồng → dễ dùng → giao diện → kiểm | Chưa có phép kiểm nào chạy |
| <a id="hang-cho-01"></a>[HANG-CHO-01](decisions/hang-cho-01.md) | Hàng chờ Sheet → web: máy tự lấy chữ mô tả theo Sheet khi tiền không đổi (Q1), chuyến mới đủ điều kiện tự vào sổ kể cả chưa có giá, chưa giá thì không cộng nợ (Q2, Q5), phiếu thu và giá từ Sheet người xác nhận ở hộp chung (Q3) | Chưa triển khai; Q2 cho khách nhiều sổ chờ Q4 |
| <a id="khoa-chu-01"></a>[KHOA-CHU-01](decisions/khoa-chu-01.md) | Tháng khóa vẫn sửa được bốn ô chữ (nơi đi, nơi đến, shipper, hãng tàu), có Lịch sử; tiền, ngày, container, xóa vẫn khóa | Migration 2026-11-01-v7-khoa-chu.sql |
| <a id="zalo-group-01"></a>[ZALO-GROUP-01](decisions/zalo-group-01.md) | Theo dõi nợ trong group Zalo: dựng lại tin có ảnh, đánh dấu tin (hứa trả, khách báo đã chuyển, ghi chú), nối vào thẻ Trao đổi; chỉ group được chọn lên `hao` | G1–G3 đã lên `hao` 1/11/2026 (bảng và API có, `hao` chưa có gói chat); G4 giao diện đánh dấu; G5 đường đẩy gói có trên `hao`, chờ người dùng chọn group |
| <a id="ho-so-01"></a>[HO-SO-01](decisions/ho-so-01.md) | Thẻ Hồ sơ theo khung HoSoV4 (nhận diện → doanh nghiệp và quan hệ → thỏa thuận → tài liệu, hai cột 62/38, cảnh báo gắn vào mục); bốn quy tắc hạng khách, tín dụng, hạn mức, vượt hạn mức chỉ cảnh báo | Giai đoạn A chỉ dữ liệu đã có; quy tắc và mục khác cần backend (giai đoạn B) |
| <a id="vcl-giu-01"></a>[VCL-GIU-01](decisions/vcl-giu-01.md) | Giữ giá web và giữ chuyến tới khi dòng Sheet liên quan đổi; lưu server và Lịch sử | Chốt 2/11/2026; lên `hao` 3/11/2026 ([nhật ký](deploys/2026-11-03-viec-can-lam.md)) |
| <a id="may-khoa-01"></a>[MAY-KHOA-01](decisions/may-khoa-01.md) | Khóa tháng chỉ chặn người: máy (theo Sheet) mở, ghi, khóa lại để điền ngày cho dòng sổ gốc không ngày cùng tháng, và đưa chuyến mới vào tháng khóa từ 10/2026 | Chốt 3/11/2026; chỉ đổi code app |
| <a id="may-gia-01"></a>[MAY-GIA-01](decisions/may-gia-01.md) | Máy tự ghi giá Sheet đã chắc chắn ở mọi tháng từ 10/2026, tháng khóa thì mở, ghi, khóa lại; thay vế "người bấm ghi giá" của HANG-CHO-01 Q5 | Chốt 3/11/2026; chỉ đổi code app, bật bằng `WEBDEBIT_AUTO_SHEET=prices` |
| <a id="may-ps-01"></a>[MAY-PS-01](decisions/may-ps-01.md) | Ô Health+KĐ của PS ghi vào một loại gộp "Health + KĐ", không tách; máy tự tách theo PS ở mọi tháng, bổ sung khoản thiếu ở dòng sổ gốc mà ô TOTAL giữ nguyên, và tự chọn cột riêng | Chốt 4/11/2026; có migration, bật bằng `WEBDEBIT_AUTO_SHEET=ps` |
| <a id="phu-phi-bu-01"></a>[PHU-PHI-BU-01](decisions/phu-phi-bu-01.md) | Dòng sổ gốc lệch vì cột không tiêu đề trên tab Sheet: bù phần thiếu thành khoản Khác/Giảm trừ khi TOTAL = đơn giá + mọi ô tiền bên trái cột giá; Thành tiền, số dư, phân bổ không đổi | Chốt 4/11/2026; chạy một lần bằng `v7_fill_fee_gap.py` |
| <a id="may-doi-soat-01"></a>[MAY-DOI-SOAT-01](decisions/may-doi-soat-01.md) | Web tự chạy theo Sheet, không cần người nhập trên web: máy đối soát mỗi giờ 7–22 giờ, chỉ ghi khi đúng một tổ hợp việc đưa tổng khách về đúng tổng Sheet tới từng đồng; thêm phiếu không ngày, phiếu Sheet đã sửa, giá khác, dòng chỉ có TỔNG, dòng tiền không container; ẩn việc của sổ đã khớp | Chốt 4/11/2026; thay vế người bấm của HANG-CHO-01 Q3 và THU-SHEET-01; cách chuyển hẳn CÒN MỞ |
| <a id="may-tao-so-01"></a>[MAY-TAO-SO-01](decisions/may-tao-so-01.md) | Máy tự tạo sổ cho khách mới khi tab đã có trên TONG thật, số trên TONG khớp tab, container không nằm ở sổ khác; làm đúng đường nạp mốc, mỗi sổ một mốc riêng | Chốt 4/11/2026; thêm một hàm SQL, lên `hao` 4/11/2026 ([nhật ký](deploys/2026-11-04-may-tao-so.md)) |
| <a id="sheet-log-01"></a>[SHEET-LOG-01](decisions/sheet-log-01.md) | Log sửa Sheet chỉ để giải thích, không để ghi tiền: khách chưa khớp mà tab vừa sửa (15 phút trước lúc tải trở đi) không tính "cần xem", lượt sau xem lại; có lệnh tra lịch sử sửa một tab; không chặn máy ghi vì số đo không cho thấy cần | Chốt 5/11/2026 (Claude theo ủy quyền); chỉ đổi code app, bật bằng `WEBDEBIT_EDIT_LOG_ID` |
| <a id="container-dung-lai-01"></a>[CONTAINER-DUNG-LAI-01](decisions/container-dung-lai-01.md) | Container đã có trong cùng sổ là chuyến mới khi tab khách ghi riêng chuyến đó: có dòng đúng ngày và nhiều dòng hơn trong sổ; không xét theo khoảng cách ngày | Chốt 4/11/2026; chỉ đổi code app |
| <a id="canh-bao-01"></a>[CANH-BAO-01](decisions/canh-bao-01.md) | Máy công nợ lỗi hoặc dừng thì báo email: máy canh trên `hao` 15 phút một lần, báo về healthchecks.io để `hao` tắt vẫn có email; không gửi tên khách, số tiền | Chốt 4/11/2026; chưa bật |
| <a id="nguon-chuyen-01"></a>[NGUON-CHUYEN-01](decisions/nguon-chuyen-01.md) | Chuyến theo booking (ngày; khách, mặt hàng với chuyến biển), tiền theo sổ gốc; lệch vào hộp ngoại lệ; nguồn `CONT_NGUON`, `CONT_BO` (giữ tab), booking 2025; chuyến bộ mới tự vào sổ theo tab khách trên Sheet | Chốt 3/11/2026; GĐ1, GĐ2 `CONT_BO` và chuyến bộ mới (bật bằng `road`) đã code, phần khác chưa, giai đoạn ở [spec](../specs/v7-chuyen-theo-nguon.md) |
| <a id="bang-thu-01"></a>[BANG-THU-01](decisions/bang-thu-01.md) | Bảng thu gom phiếu mọi sổ, chỉ xem: danh sách theo ngày, tháng tính theo ngày tiền về, khoản không rõ ngày nằm riêng và không cộng vào tháng | Chốt 4/11/2026; thêm hai hàm đọc, không đổi luật tiền |
| <a id="bang-thu-02"></a>[BANG-THU-02](decisions/bang-thu-02.md) | Bảng thu có năm cách xem dạng tab (theo ngày, khách, mặt hàng, tháng nợ, 12 tháng) và bộ lọc mặt hàng; trang theo ngôn ngữ Tổng quan bản ít chữ | Chốt 4/11/2026; chỉ đổi trình bày, không có migration |
| <a id="tuong-tac-01"></a>[TUONG-TAC-01](decisions/tuong-tac-01.md) | Bảng thu và Tình hình: bấm là lọc hoặc mở tại chỗ rồi mới Mở sổ; ghim tháng trên hình, mở phiếu tại dòng khách, dải ngày ở mọi tab trừ 12 tháng | Chốt 5/11/2026; chỉ đổi trang, không có migration |

## Cập nhật khóa tháng 24/10/2026

Đã chuyển sang [`decisions/khoa-thang-2026-10-24.md`](decisions/khoa-thang-2026-10-24.md).

## Gate chưa đóng

Nguồn S15R ghi thiết kế `NOT_ACCEPTED_FOR_FINANCIAL_WRITES`. Tóm tắt này không thay hợp đồng chi tiết để xây đường ghi tiền.

- D04: tiền dư, số âm, tiền chưa phân bổ, tín dụng/ứng trước, tranh chấp và hoàn tiền. (**Chốt 21/10/2026** theo [`V7-CSM`](#v7-csm) (1): dư hiện âm và trừ vào chuyến sau; không hoàn tiền, không tiền chưa rõ chủ, không trạng thái tranh chấp trên web; chưa triển khai.)
- D05/D06: chứng cứ xác minh receipt/cấn trừ, chính sách VND/tỷ giá được duyệt. (**Chốt 21/10/2026** theo `V7-CSM` (2): ô tham chiếu không bắt buộc, chỉ VND thực nhận; chưa triển khai.)
- D07: nhập muộn, kỳ khóa, mở lại và phiếu điều chỉnh; ảnh hưởng ngày chốt. (Một phần đã chốt theo [`V7-SO`](#v7-so): ổ khóa từng tháng, tháng khóa sửa bằng dòng điều chỉnh. Mở lại tháng chốt 21/10/2026 theo `V7-CSM` (3): ai cũng mở, mỗi lần mở/khóa ghi Lịch sử; chưa triển khai.)
- P0: procedure ghi tiền atomic; approval đúng phiên bản/nội dung/danh tính; cap allocation/FIFO dưới ghi đồng thời; idempotency cùng key khác payload; đảo chính xác, khóa kỳ, snapshot phiếu. (Phần approval hết hiệu lực theo `V6-DB`; vẫn giữ danh tính người thao tác và vết theo [`V7-ID`](#v7-id).)
- Vận hành: role/auth, DB integration, nghiệm thu và quyền deploy riêng. (**Người duyệt riêng hết hiệu lực 19/10/2026** theo `V6-DB`; chỗ của nó là lưu vết ai sửa gì, ai được xem lưu vết chốt 21/10/2026 theo `V7-CSM` (4): ai mở được sổ thì xem được Lịch sử sổ đó.)

Probe DDL đơn phiên đã tái hiện thiếu guard. Không coi fixture, CHECK/FK, command thành công hoặc báo cáo cũ là nghiệm thu các mục trên. Quyết định mới ghi người chốt, ngày, phạm vi, ví dụ cạnh biên, code/test tác động và liên kết bằng chứng có quyền riêng.
