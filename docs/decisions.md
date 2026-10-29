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
| <a id="v7-be"></a>[V7-BE](decisions/v7-be.md) | Quy tắc backend V7 (phụ phí trống, FIFO…) |  |
| <a id="v7-mh"></a>[V7-MH](decisions/v7-mh.md) | Mặt hàng gắn theo sổ khách |  |
| <a id="v7-tong"></a>[V7-TONG](decisions/v7-tong.md) | Loại tab không có tên trên TONG |  |
| <a id="moc-chuyen-moi"></a>[MOC-CHUYEN-MOI](decisions/moc-chuyen-moi.md) | Mốc chuyến mới |  |
| <a id="v7-copy"></a>[V7-COPY](decisions/v7-copy.md) | Bản sao dữ liệu thật V7 và cách hiện lịch sử |  |
| <a id="v7-csm"></a>[V7-CSM](decisions/v7-csm.md) | Chính sách V7 còn mở (D04–D07, Lịch sử) |  |
| <a id="song-song-01"></a>[SONG-SONG-01](decisions/song-song-01.md) | Chạy song song Sheet và web |  |
| <a id="song-song-02"></a>[SONG-SONG-02](decisions/song-song-02.md) | Mốc nạp clean-v2 và ngày song song |  |
| <a id="nhap-sheet-01"></a>[NHAP-SHEET-01](decisions/nhap-sheet-01.md) | Nhập và sửa chuyến kiểu Sheet | Vế (1) bảng nhập thay bởi [NHAP-SHEET-02](#nhap-sheet-02) |
| <a id="nhap-sheet-02"></a>[NHAP-SHEET-02](decisions/nhap-sheet-02.md) | Bỏ bảng nhập chuyến; chuyến lấy từ Sheet |  |
| <a id="dash-01"></a>[DASH-01](decisions/dash-01.md) | Trang tổng quan công nợ |  |
| <a id="mh-01"></a>[MH-01](decisions/mh-01.md) | Mặt hàng lấy từ cột LOAI HANG của TONG |  |
| <a id="so-gon-01"></a>[SO-GON-01](decisions/so-gon-01.md) | Sổ khách gọn |  |
| <a id="so-gon-02"></a>[SO-GON-02](decisions/so-gon-02.md) | Phiếu thu danh sách riêng, phiếu hủy gom gọn, bỏ cột cộng dồn | Mục (3) phần thanh tháng/dòng tổng sửa bởi [SO-GON-03](#so-gon-03) |
| <a id="so-gon-03"></a>[SO-GON-03](decisions/so-gon-03.md) | Mỗi số tiền của tháng hiện một lần |  |
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
