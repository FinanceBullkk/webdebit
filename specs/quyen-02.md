# QUYEN-02: mục Quản trị và trang Người dùng

Quyết định: [`docs/decisions/quyen-02.md`](../docs/decisions/quyen-02.md). Nối tiếp [`QUYEN-01`](../docs/decisions/quyen-01.md).

## Người dùng và mục tiêu

Chỉ quản lý (chủ sổ) dùng, vài lần một tuần. Hai việc:

1. **Ít mục trên menu.** Năm màn quản lý (Việc cần làm, Máy chạy, Đội xe, Thông tin cty, Nhật ký công việc) gom vào một
   mục **Quản trị**. Việc cần làm là việc hằng ngày nên bấm Quản trị là vào thẳng đó.
2. **Tự thêm, bớt người dùng sổ trên web**, không phải sửa file trên `hao`. Thấy ngay ai vừa bị chặn để cho vào.

## Luồng

**Menu.** Quản lý thấy: Tìm khách, Tổng quan, Công nợ theo tháng, Sổ khách, Bảng thu, Báo cáo tháng, **Quản trị**. Số
"sổ còn việc" chuyển từ mục Việc cần làm sang mục Quản trị. Mục Quản trị sáng khi đang ở bất kỳ màn quản lý nào. Nhân
viên vẫn thấy sáu mục như QUYEN-01, không có Quản trị.

**Dải thẻ.** Đầu mỗi màn quản lý, ngay trên thanh đầu trang, có một dải cao 40px: Việc cần làm (số) · Máy chạy · Đội
xe · Thông tin cty · Nhật ký · Người dùng. Thẻ của màn đang mở được tô. Bấm thẻ là sang màn đó.

**Người dùng** (`/nguoi-dung.html`, chỉ quản lý). Bố cục làm lại 20/11/2026 theo trang canvas "Người dùng (Quản trị)"
(người dùng chê bản đầu lộn xộn, chọn qua bốn vòng trên canvas): một trục căn trái theo dải thẻ, rộng tối đa 920px, hai
thẻ cùng khuôn, từ trên xuống:

1. **Thành viên** (đầu thẻ: số người · số quản lý, nút "Thêm người"). Cột cố định: Người | Vai trò 168px | ⋯ 44px.
   - **Dòng xin vào** ở đầu thẻ (chỉ hiện khi có): login Tailscale đã thử mở sổ mà không có quyền, kể từ lần khởi động
     gần nhất của máy chủ, kèm số lần và lần cuối; hai nút "Bỏ qua" (chỉ ẩn trên trang) và "Cho vào" (làm Nhân viên).
   - **Mỗi người một dòng**: chữ cái đầu, tên gọi (không có thì phần trước @), login bên dưới. Vai trò đổi ngay ở ô
     chọn. Nút ⋯ mở "Sửa tên gọi" (sửa tại dòng, Enter để lưu) và "Bỏ quyền vào"; bỏ quyền hỏi lại ngay tại dòng: "Bỏ
     quyền vào của X? Họ sẽ không mở được sổ nữa", kèm Thôi và Bỏ quyền. Login cố định trên máy chủ và dòng của chính
     mình (ghi "Bạn") hiện vai trò trong ô mờ cùng cỡ, không đổi được, không có ⋯; ô cố định có ổ khóa.
2. **Lịch sử thay đổi**: câu ngắn "Bạn đổi vai trò Lan: Nhân viên → Quản lý" và giờ bên phải; 5 dòng mới nhất, "Xem
   thêm" ra đủ 30. Người làm là chính mình ghi "Bạn"; người làm không có @ (lúc chuyển từ cấu hình máy chủ) ghi "Hệ
   thống". Login còn trong danh sách hiện tên gọi, rê chuột thấy login đủ.

**Thêm người** là hộp thoại: Login Tailscale, Tên gọi (không bắt buộc), Vai trò (hai ô chọn có mô tả, mặc định Nhân
viên), Thôi và Thêm người. Login sai dạng hoặc máy chủ từ chối thì câu lỗi hiện ngay dưới ô login, hộp vẫn mở.

Sau mỗi thao tác, trang đọc lại danh sách rồi hiện câu báo nhỏ ở đáy màn ("Đã cho X vào làm Nhân viên."), tự tắt sau 4
giây. Thay đổi có hiệu lực ngay ở yêu cầu tiếp theo, không cần restart.

## Dữ liệu và an toàn

- **Hai nguồn.** Cố định: `WEBDEBIT_ALLOWED_LOGINS` / `WEBDEBIT_ADMIN_LOGINS` như ACCESS-01, QUYEN-01, là đường cứu khi
  lỡ tay. Quản lý trên web: file `WEBDEBIT_ACCESS_FILE` (JSON, ghi tạm rồi đổi tên, mode 600), do API ghi. Được vào =
  cố định ∪ file. Quản lý = cố định ∪ file có vai trò quản lý.
- Chặn: sửa login cố định (409), sửa chính mình (409), bỏ quản lý cuối cùng (409), thêm login đã có (409), bản cũ
  (`version` lệch, 409), login sai dạng (422).
- File hỏng hoặc không đọc được: chỉ dùng danh sách cố định (fail closed), lệnh ghi trả 503, journal ghi một dòng.
- Danh sách "Vừa bị chặn" chỉ giữ trong bộ nhớ (tối đa 20 login), mất khi restart. Journal vẫn là nguồn đầy đủ.
- API `GET/POST /api/v7/admin/users` nằm dưới tiền tố quản lý của QUYEN-01, nên nhân viên nhận 403 trước khi tới route.

## Trạng thái

Đang tải; lỗi đọc (câu ngắn và nút Thử lại); máy chủ chưa bật quản lý trên web (`configured: false`, chỉ xem danh
sách cố định, nút Thêm người ẩn); ghi lỗi (câu theo mã: đã có, bản cũ thì đọc lại, cố định, chính mình); login dài
thì xuống dòng, không tràn ngang ở 1280 và 390.

## Kiểm

- `tests/test_v7_access.py`: gộp hai nguồn, các lệnh và mọi mã chặn, file hỏng thì chỉ dùng danh sách cố định, ghi
  nguyên tử, lịch sử, danh sách bị chặn có giới hạn.
- `tests/test_v7_ledger_api.py`: HTTP thật, thêm nhân viên trên web thì login đó vào được ngay, bỏ quyền thì 403 ngay;
  nhân viên gọi `/api/v7/admin/users` thì 403; login bị chặn hiện trong danh sách Vừa bị chặn.
- Trình duyệt: menu bảy mục của quản lý (Quản trị có số), dải thẻ trên năm màn và trang Người dùng, các luồng cho vào,
  đổi vai trò, bỏ quyền có hỏi lại, lỗi, không cuộn ngang ở 1280 và 390.
- Trên `hao`: chuyển ba login nhân viên từ cấu hình cố định sang file, chỉ để login chủ sổ cố định; kiểm cùng các phép
  thử của QUYEN-01.
