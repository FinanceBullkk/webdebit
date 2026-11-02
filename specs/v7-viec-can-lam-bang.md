# Việc cần làm — bảng bốn cột (2/11/2026)

Người dùng yêu cầu code theo bản HTML đã chọn ngày 2/11: `ViecCanLamBang.dc.html`, tiêu đề “BẢN CHÍNH · bảng 4 cột có chữ”. File nguồn giữ ngoài Git trong Downloads; không nhập runtime React của bản thiết kế.

## Hợp đồng hoàn thành

- Người nhập nhìn số sổ còn việc, người đã ghi hôm nay, rồi bảng Khách / Phiếu thu / Giá chuyến / Chuyến cần xử lý / Thiết lập sổ. Một sổ một dòng; bấm mở chi tiết ngay bên dưới. Bộ lọc Tiền vào sổ, Chuyến, Thiết lập sổ đếm sổ, không đếm việc trùng.
- Hợp nhất `/api/v7/inbox`, `/dashboard`, `/dashboard/debt`, `/customers` bằng ID sổ. Không gộp khách theo tên. Chưa lấy được một nguồn phải báo thiếu, không kết luận hết việc.
- Giữ ghi phiếu qua `/sheet/receipts`, xem lại nợ trước/sau, phiên bản, hash Sheet, khóa chống trùng và kết quả riêng từng sổ. Giá đọc chi tiết `/ledger` trước khi xem lại và gọi `/sheet/prices`; không dựng số tiền từ bộ đếm.
- Chọn chung phiếu và giá: đọc mới từng sổ, xem tổng nợ cuối sau cả hai loại; ghi giá rồi phiếu, dùng phiên bản trả về của lệnh trước. Mất mạng giữ nguyên payload của lô chưa rõ, bỏ qua lô đã xong. Lô lỗi/một phần dừng và yêu cầu mở sổ kiểm tra, không gọi tiếp bằng phiên bản cũ.
- Chi tiết dùng lệnh có sẵn: đơn giá nhập theo triệu đồng (tối đa sáu số lẻ, quy đổi BigInt ra nguyên đồng), kết luận chờ kiểm có lý do bắt buộc, duyệt chuyến mới chưa giá, tách PS giữ tổng, xóa chuyến có xem lại. Tháng khóa giữ đường mở sổ; không tự mở khóa. “Giữ giá web” và “Giữ chuyến” lưu quyết định có người làm trên server theo nội dung dòng liên quan, theo [VCL-GIU-01](../docs/decisions/vcl-giu-01.md). Không thay đổi số dư.
- Việc cần đối chiếu sâu mở đúng sổ bằng đường đang có. Không ghi dữ liệu thật, sửa Sheet hoặc triển khai trong task. Năm hàm SQL mới (mục dưới), mỗi hàm một migration; hàm ghi tiền đi qua lệnh sẵn có (`edit_trip_price`, `edit_legacy_trip`, `record_receipt`, `void_receipt`, `paste_trips`).
- Kiểm: `npm run check`; browser với fixture ở 1280×560, thanh cuộn dọc, màn hẹp, chữ dài/Hán, dữ liệu trống/thiếu/lỗi, lọc, mở/gập, xem lại/hủy, ghi lỗi và thử lại cùng khóa. Xem ảnh render trước khi bàn giao.

## Map kiểm

| Thao tác | Entry point | Kiểm |
|---|---|---|
| Tải/lọc/mở sổ | `viec-can-lam.js`, `viec-can-lam-inbox.js` | browser bảng bốn cột |
| Ghi phiếu | `viec-can-lam.js` → `/sheet/receipts` | browser P2: lỗi từng sổ, mất mạng/chống trùng |
| Ghi giá | `viec-can-lam.js` → `/ledger` → `/sheet/prices` | browser: xem lại, phiên bản mới, thử lại |
| Chi tiết/soát máy | `viec-can-lam-inbox.js` | browser: đúng ID, không lộ fixture vào production |

Giới hạn: số dư đầu và phụ phí PS dẫn về sổ hiện hành; không giả lập thao tác sửa Sheet hoặc tự đặt nguồn tiền. Giữ nhãn giá và trạng thái thật từ API. Nhập giá theo triệu như package; nhận dấu phẩy hoặc dấu chấm thập phân, không chấp nhận chuỗi có hai dấu. Giá gợi ý chỉ lấy từ `/price-table/status`, giữ đủ độ chính xác khi điền ô. Kiểm fixture không thay kiểm tích hợp hoặc người dùng đi hết luồng trên bản thử.

## Đối chiếu package sau góp ý ngày 2/11

Người dùng yêu cầu giống toàn bộ package, không chỉ dùng bố cục làm cảm hứng. Đã sửa biểu tượng, màu, khoảng cách, nhãn, người ghi dạng chip, bộ lọc có biểu tượng sổ, đếm mục thay cho sổ, tổng tiền phiếu theo triệu, gộp số cần xem, làm mờ cột ngoài nhóm lọc, bảng xem lại và xác nhận tại dòng. Nguồn HTML/runtime giữ ngoài Git; fixture cùng tám khách giả của package kiểm hình học và tổng độc lập. Không coi toàn bộ yêu cầu đã đạt chỉ vì các kiểm này xanh.

## Xử lý tại dòng (Codex làm 2/11, Claude rà và hoàn tất)

| Thao tác | API | Hàm SQL / migration | Ghi tiền |
|---|---|---|---|
| Giữ giá web, Giữ chuyến | `/sheet/tasks/keep` | `keep_sheet_task` · `2026-11-02-v7-giu-viec-sheet.sql` | Không ([VCL-GIU-01](../docs/decisions/vcl-giu-01.md)) |
| Lấy giá Sheet (một dòng) | `/sheet/tasks/price` | `apply_sheet_price` · `2026-11-02-v7-lay-gia-sheet.sql` | Có, qua lệnh sửa giá sẵn có |
| Ghi phiếu thiếu ngày | `/sheet/receipts/review` | `record_receipt` sẵn có; tham chiếu `Sheet #<hash>` nối phiếu với dòng nguồn | Có |
| Gán mặt hàng cho sổ chưa có | `/customers/commodity` | `set_customer_commodity` · `2026-11-02-v7-gan-mat-hang.sql` | Không |
| Chọn sổ cho một chuyến | `/sheet/trips/assign` | `assign_sheet_trip` · `2026-11-02-v7-chon-so-chuyen.sql` | Chuyến vào sổ đích chưa có giá, chưa cộng nợ |
| Hoàn tác lô giá/phiếu vừa ghi | `/sheet/batch/undo` | `undo_sheet_batch` · `2026-11-02-v7-hoan-tac-lo.sql` | Có: hủy phiếu, trả giá cũ; dòng sổ gốc trả cả TOTAL cũ bằng revision + điều chỉnh |

Kiểm: `npm run check`; harness `test_pg_v7_backend.py` (ca `VCL-GIU.01` phủ cả năm lệnh: gửi lại, khóa tháng, quyền chỉ xem, số dư từng tháng) và `test_pg_v7_backend_sheet_keep.py` chạy ở CI.

**CÒN MỞ — cần người dùng chốt trước khi merge:**

- Chọn sổ cho chuyến chỉ áp dụng riêng chuyến đó (đang làm theo cách này, như package tách hai thao tác) hay gán luôn mặt hàng mặc định của sổ.
- Hoàn tác lô là quy tắc tiền mới (hủy phiếu với lý do cố định "Hoàn tác lần ghi từ Việc cần làm", trả giá cũ, thêm dòng điều chỉnh cho TOTAL sổ gốc).

**Giới hạn đã biết:**

- Dấu nội dung nguồn so theo nội dung hiện tại: dòng Sheet đổi A → B → A thì quyết định Giữ cũ có hiệu lực lại.
- Lô ghi giá/phiếu mất phản hồi rồi gửi lại có thể nhận STALE_LEDGER thay vì kết quả cũ (`approve_request` kiểm phiên bản trước khi phát lại khóa con); không ghi trùng nhưng người dùng phải tải lại sổ.
- Danh sách mặt hàng chọn được cố định năm loại theo package (Sầu riêng, Thanh long, Chuối, Mít, Dừa).
- Phụ phí PS và số dư đầu vẫn mở sổ thật, chưa xử lý tại dòng.
