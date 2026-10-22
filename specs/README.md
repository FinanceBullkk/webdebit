# Đặc tả thay đổi

Một spec cho một thay đổi: đầu ra, phạm vi, nguồn quyết định, hành vi/bất biến, entry point, tiêu chí nghiệm thu, hoàn tác và bằng chứng. Tách ĐỀ XUẤT/ĐÃ CHỐT/ĐÃ TRIỂN KHAI/ĐÃ KIỂM CHỨNG/CÒN MỞ; tài liệu không duyệt thay chủ nghiệp vụ.

- [Cảnh báo chuyến chờ duyệt](pending-shipments/README.md): thay đổi nhỏ trên fixture thử quy trình spec → test → browser → bằng chứng.

Yêu cầu nền ở [docs](../docs/README.md), không nhân bản vào từng spec.

- [Sổ khách V7](v7-so-khach-theo-sheet.md): prototype fixture; [backend đề xuất](v7-backend-so-khach.md), [API thử](v7-backend/ket-noi-giao-dien.md).
- [Nhập chuyến kiểu Sheet](v7-nhap-kieu-sheet.md): hàng trống, dán tự trải vào ô, nháp + Lưu; sửa đè/xóa tại ô mọi chuyến kể cả sổ gốc và tháng khóa, đổi ngày thì sang bảng tháng đó (`NHAP-SHEET-01`, 22/10/2026); có bản xem HTML, chưa code live. Backend: [sửa/xóa chuyến và dòng sổ gốc](v7-sua-xoa-chuyen.md).
- [Gắn mặt hàng và nhóm ô chọn khách](v7-mat-hang-chon-khach.md): đọc `LOAI HANG` của `TONG` khi nạp, SQL gán cho DB đang chạy, `list_customers` trả mặt hàng, ô chọn khách nhóm/tìm theo mặt hàng (`MH-01`, 23/10/2026); chưa triển khai.
- [Chuẩn bị gộp V7](../docs/v7-merge-prep.md): nguồn commit, phân loại, phần loại, kiểm và giới hạn.
- [Chính sách V7 còn mở](v7-chinh-sach-mo.md): phương án cho D04, D05/D06, D07, ai xem Lịch sử và case 7.11c, chờ chủ nghiệp vụ chọn (ĐỀ XUẤT).
- [Cấn trừ giữa hai sổ](can-tru-hai-so.md): ghi cả sổ lấy tiền và sổ được trả trong một lệnh, chốt 20/10/2026; [bản đặt mockup HTML](can-tru-hai-so-mockup-html.md), [bản sửa vòng 2](can-tru-hai-so-mockup-vong-2.md).
- [Kế hoạch triển khai V7 lên `hao`](v7-backend/ke-hoach-trien-khai-hao.md): thứ tự bước deploy, điều kiện an toàn, danh tính Tailscale tối thiểu, gate bắt buộc đóng vs để sau, thứ tự chạy `SONG-SONG-01`; ĐỀ XUẤT, không phải quyền chạy.
