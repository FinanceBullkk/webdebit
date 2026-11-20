# QUYEN-02

[← Sổ quyết định](../decisions.md)

## Quyết định

1. **Một mục Quản trị trên menu.** Quản lý thấy năm trang làm sổ như nhân viên, thêm một mục **Quản trị**. Bấm vào là tới
   thẳng Việc cần làm, vì đó là việc hằng ngày. Số "sổ còn việc" nằm trên mục này. Nhân viên không thấy mục này.
2. **Dải thẻ** ở đầu mọi màn quản lý để chuyển qua lại: Việc cần làm, Máy chạy, Đội xe, Thông tin cty, Nhật ký, Người dùng.
   Mục Nhật ký công việc dưới menu bỏ đi vì đã có trong dải thẻ.
3. **Trang Người dùng** (chỉ quản lý). Trên đó:
   - cho vào login vừa bị chặn;
   - thêm người, đặt tên gọi;
   - đổi giữa Quản lý và Nhân viên;
   - bỏ quyền vào. Bước này phải hỏi lại ngay tại dòng trước khi làm;
   - xem 30 thay đổi gần nhất, mỗi dòng ghi ai làm, lúc nào, trước → sau.

   Thay đổi có hiệu lực ngay ở yêu cầu kế tiếp, không cần restart.
4. **Hai nguồn danh sách.** Login cố định trong cấu hình unit (`WEBDEBIT_ALLOWED_LOGINS`, `WEBDEBIT_ADMIN_LOGINS`) không
   sửa được trên web. Đó là đường cứu khi lỡ tay. Login do trang quản lý nằm trong file `WEBDEBIT_ACCESS_FILE` trên máy chạy,
   ngoài Git. Được vào = cố định ∪ file. Quản lý = cố định ∪ file có vai trò quản lý.
5. **Chặn ở máy chủ**: sửa login cố định, tự sửa chính mình, bỏ quản lý cuối cùng, thêm trùng, ghi trên bản cũ. File hỏng
   thì chỉ dùng phần cố định (fail closed) và không cho ghi. Danh sách "vừa bị chặn" chỉ nằm trong bộ nhớ, tối đa 20 login.

Spec: [`specs/quyen-02.md`](../../specs/quyen-02.md).

## Ngày / nguồn

20/11/2026, chat với người dùng (chủ sổ). Người dùng chọn "trang gom các màn quản lý, trong đó có quản lý người dùng", rồi
chọn cách "bấm Quản trị là vào thẳng Việc cần làm, đổi màn bằng dải thẻ" thay vì một trang tổng có sáu ô.

Thay điểm "Nhật ký ở dưới khối chín mục" của [`NHAT-KY-01`](nhat-ky-01.md). Đóng điểm CÒN MỞ (3) của
[`ACCESS-01`](access-01.md): đã có cách tự phục vụ để thêm người.

## Cách chạy

- `web/v7_access.py` (`AccessStore`, `DeniedLog`). `v7_ledger_api.py` lấy danh sách có hiệu lực mỗi yêu cầu, đọc lại file
  khi file đổi. Route `GET/POST /api/v7/admin/users` nằm dưới tiền tố quản lý của QUYEN-01.
- `preview/app-nav.js` (mục Quản trị, `ADMIN_TABS`); `preview/nguoi-dung.html`, `nguoi-dung-ui.js`, `nguoi-dung.css`.
- Test: `tests/test_v7_access.py`, `tests/test_v7_ledger_api.py` (HTTP thật: cho vào rồi bỏ quyền có hiệu lực ngay),
  `preview/test-nguoi-dung-browser.js`.

## Giới hạn

- Tên gọi chỉ hiện trên trang Người dùng; ô "đang xem" (presence) vẫn hiện phần trước dấu @ của login.
- Login bị chặn chỉ hiện từ lần khởi động gần nhất của máy chủ; journal của unit vẫn là nguồn đầy đủ.
