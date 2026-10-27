# V7 — tên Sheet và mặt hàng

## Đã triển khai trong worktree

- API `/api/v7/customers` giữ `id` và `name` V7 để định tuyến, thêm `display_name` và `aliases` từ bảng ánh xạ.
- Picker hiển thị `display_name` (nếu có), tìm được bằng tên Sheet, tên V7 hoặc alias.
- Nhãn sổ hiển thị thêm mặt hàng/phương thức; các dòng có cùng khách nhưng khác mặt hàng vẫn là các sổ riêng.
- API `/api/v7/ledger` không đổi số dư, giao dịch, mã sổ hay dữ liệu lịch sử.

## Bảng ánh xạ

Đặt file JSON ngoài repo, rồi cấu hình `WEBDEBIT_CUSTOMER_NAME_MAPPING_PATH`:

```json
{
  "version": 1,
  "customers": {
    "123": {
      "v7_name": "Tên hiện có trong V7",
      "display_name": "Tên chuẩn từ Sheet",
      "aliases": ["Tên cũ", "Tên booking"]
    }
  }
}
```

Mã sổ là khóa chính. Nếu file thiếu, lỗi, hoặc tên V7 không khớp, web dùng tên V7 cũ và vẫn đọc sổ; không tự đổi tên hay gộp sổ.

## Còn mở

File ánh xạ dữ liệu thật nằm ngoài repo. Cần người có quyền vận hành đặt file lên máy chạy web, kiểm tra danh sách tên/mặt hàng với Sheet, rồi mới bật biến môi trường. Task này chưa deploy lên `hao`.
