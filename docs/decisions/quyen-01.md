# QUYEN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Web V7 có hai vai trò theo login Tailscale:

1. **Quản lý (admin)** thấy mọi trang như trước.
2. **Người dùng (user)**: mọi login được vào ([`ACCESS-01`](access-01.md)) mà không có trong danh sách quản lý. Menu chỉ
   có **Tìm khách, Tổng quan, Công nợ theo tháng, Sổ khách, Bảng thu, Báo cáo tháng**. Không có số Việc cần làm trên
   menu. Chat Zalo vẫn mở vì người dùng vào đó từ thẻ Liên hệ của Sổ khách.
3. **Máy chủ chặn, menu chỉ phản ánh.** Người dùng gõ địa chỉ trang quản lý (Việc cần làm, Máy chạy, Đội xe, Thông tin
   cty, Nhật ký công việc, cùng các trang ẩn Đòi nợ và Chuyến từ Sheet) thì nhận trang 403 "Mục này chỉ dành cho quản
   lý." và link về Tổng quan. API chỉ trang quản lý gọi (`/api/v7/machine…`, `/api/v7/doixe…`, `/api/v7/nhat-ky`) trả
   403 `ADMIN_ONLY` trước khi đụng DB.
4. **API mà trang người dùng cần vẫn mở**: `company-info` cho hộp xuất debit note, `inbox` cho việc Sheet trong Sổ
   khách, cùng mọi API đọc/ghi sổ.
5. **Quyền ghi tiền không đổi**: người dùng sửa, dán lô, ghi thu trong Sổ khách như trước. Vai trò chỉ chia màn hình.
6. Chỗ trên trang người dùng từng dẫn sang Việc cần làm (viên chuyến chưa giá ở Tổng quan, viên phiếu Sheet chưa ghi
   ở Bảng thu, lý do "người xử lý" ở Báo cáo tháng) vẫn hiện số nhưng không còn là link. Từ 25/11/2026 ([`WEB-CHINH-01`](web-chinh-01.md),
   người dùng tự gõ giá trên web từ 1/12): viên chuyến chưa giá của người dùng là nút bung danh sách sổ còn chuyến chưa giá
   ngay tại khối (số đếm có sẵn trong API Tổng quan), mỗi sổ mở Sổ khách tô chuyến thiếu giá (`?loc=thieu-gia`). Không mở
   Việc cần làm cho người dùng.

Danh sách quản lý là cấu hình vận hành trên máy chạy, **ngoài Git** vì chứa login: biến `WEBDEBIT_ADMIN_LOGINS`
(phân cách bằng dấu phẩy hoặc khoảng trắng) trong drop-in của unit API, hoặc cờ `--admin-login` lặp. Mỗi login quản lý
phải có trong danh sách ACCESS-01, và danh sách đã đặt thì không được rỗng; sai một trong hai thì API từ chối khởi động.
**Không đặt danh sách thì mọi login được vào đều là quản lý**, nên dev, test và bản cài cũ giữ nguyên.

### Sửa đổi 25/11/2026: Thu chi mở cho người dùng

Người dùng chốt ngày 25/11/2026, trong hộp câu hỏi của phiên kiểm toàn bộ website. Câu hỏi nói rõ trang có tin chat nhóm nội bộ và các khoản chi. Người dùng chọn **"Mở cả trang cho user"**. Lý do: từ 1/12/2026 người nhập ghi mọi phiếu thu trên web ([`WEB-CHINH-01`](web-chinh-01.md)), và nút "Ghi phiếu" ở Thu chi dẫn sang khung Ghi phiếu thu (`PHIEU-WEB-01` mục 4, PR #676).

| Đường | Đọc hay ghi | Ai được |
| --- | --- | --- |
| `/thu-chi.html` | trang | mọi login được vào |
| `GET /api/v7/cash-chat` | đọc các khoản thu, chi, ứng trong chat | mọi login được vào |
| `GET /api/v7/cash-chat/targets` | đọc danh sách sổ, xe, tài xế cho ô gắn | mọi login được vào |
| `GET /api/v7/zalo/media/…` | ảnh trong tin (đã mở từ trước cho Chat Zalo) | mọi login được vào |
| `POST /api/v7/cash-chat/review` | ghi kết luận xem xét: xác nhận, sửa số, gắn đối tượng, loại (không ghi tiền) | **chỉ quản lý** (`ADMIN_API_PATHS`, 403 `ADMIN_ONLY`) |

Trên trang, người dùng không có nút "Xử lý", vì nút đó gửi lệnh ghi. Người dùng cũng không có link "Mở Đội xe", vì Đội xe vẫn chỉ quản lý. Menu của người dùng thêm mục **Thu chi** ở cuối, cả ở menu viết sẵn của Sổ khách. Quản lý vẫn vào Thu chi từ dải thẻ Quản trị. Trước sửa đổi, trang Thu chi ([`ZALO-THU-CHI-01`](zalo-thu-chi-01.md)) và mọi API `/api/v7/cash-chat…` chỉ quản lý vào được (cùng quyền với Đội xe vì có số chi và ứng).

## Ngày / nguồn

20/11/2026, chat với người dùng (chủ sổ). Người dùng chỉ hai nhóm màn: nhóm quản lý (Việc cần làm, Máy chạy, Đội xe,
Thông tin cty, Nhật ký công việc) và nhóm người dùng (Tìm khách, Tổng quan, Công nợ theo tháng, Sổ khách, Bảng thu, Báo
cáo tháng), rồi duyệt cách làm hai lớp (máy chủ chặn, menu tự ẩn). Danh sách quản lý ban đầu: một login chủ sổ.

Thay điểm (4) "ai cũng thấy" của [`NHAT-KY-01`](nhat-ky-01.md): từ nay Nhật ký công việc chỉ quản lý thấy.

## Cách chạy

- Máy chủ: `web/v7_role.py` (`USER_PAGES`, `ADMIN_API_PREFIXES`, `ADMIN_API_PATHS`, `role`, `allowed`, `mark_html`); `web/v7_ledger_api.py`
  kiểm vai trò ngay sau khi giải danh tính, trước mọi route.
- Trang HTML trả cho người dùng có `<html lang="vi" data-role="user">`. Bản này giữ riêng trong bộ nhớ đệm, có ETag
  khác bản quản lý, nên trình duyệt không lấy nhầm bản của vai trò kia. Menu vẽ đúng ngay lần đầu, không phải hỏi
  thêm API.
- `preview/app-nav.js`: `AppNav.isAdmin()`; người dùng thì lọc menu, bỏ mục Nhật ký, không đếm Việc cần làm, và bỏ
  link quản lý có sẵn trong HTML (menu riêng của Sổ khách).
- Test: `tests/test_v7_ledger_api.py` (HTTP thật: 403 trang và API, 200 trang người dùng có dấu vai trò, CLI);
  `preview/test-bang-thu-browser.js`, `preview/test-v7-dashboard-browser.js` (menu năm mục, viên chỉ để đọc).

## Giới hạn

- Chặn theo bảng tra trong `v7_role.py`. Trang mới mặc định **chỉ quản lý** cho tới khi thêm vào `USER_PAGES`. API mới
  mặc định **mở** cho mọi login được vào, trừ khi thêm tiền tố vào `ADMIN_API_PREFIXES` hay đường đúng tên vào `ADMIN_API_PATHS`.
- Như ACCESS-01: đổi danh sách phải sửa drop-in trên `hao`, rồi `daemon-reload` và restart unit.
