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

**Người dùng** (`/nguoi-dung.html`, chỉ quản lý), từ trên xuống:

1. **Vừa bị chặn** (chỉ hiện khi có): login Tailscale đã thử mở sổ mà không có quyền, kể từ lần khởi động gần nhất của
   máy chủ. Mỗi dòng có login, lần cuối, số lần, và hai nút "Cho vào (nhân viên)", "Bỏ qua". Bỏ qua chỉ ẩn trên trang.
2. **Ai được vào sổ**: bảng gồm Tên gọi, Login, Vai trò (Quản lý / Nhân viên), Thêm bởi. Mỗi dòng có nút đổi vai
   trò và nút "Bỏ quyền vào". Bấm "Bỏ quyền vào" thì hỏi lại ngay tại dòng: "Bỏ quyền vào của X? Họ sẽ không mở được
   sổ nữa", kèm nút Bỏ quyền và Thôi. Login đặt cố định trên máy chủ ghi "Cố định trên máy chủ" và không có nút. Dòng
   của chính mình ghi "Bạn" và không có nút.
3. **Thêm người**: Login Tailscale, Tên gọi (không bắt buộc), Vai trò (mặc định Nhân viên), nút Thêm.
4. **Lịch sử**: 30 dòng mới nhất, mỗi dòng gồm lúc, ai làm, việc gì, trước → sau.

Sau mỗi thao tác, trang hiện một dòng báo tại chỗ ("Đã cho X vào làm nhân viên") rồi đọc lại danh sách. Có thay đổi
có hiệu lực ngay ở yêu cầu tiếp theo, không cần restart.

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
sách cố định, khối Thêm người ẩn); ghi lỗi (câu theo mã: đã có, bản cũ thì đọc lại, cố định, chính mình); login dài
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
