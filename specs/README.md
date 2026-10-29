# Đặc tả thay đổi

Một spec cho một thay đổi: đầu ra, phạm vi, nguồn quyết định, hành vi/bất biến, entry point, tiêu chí nghiệm thu, hoàn tác và bằng chứng. Tách ĐỀ XUẤT/ĐÃ CHỐT/ĐÃ TRIỂN KHAI/ĐÃ KIỂM CHỨNG/CÒN MỞ; tài liệu không duyệt thay chủ nghiệp vụ.

- [Cảnh báo chuyến chờ duyệt](pending-shipments/README.md): thay đổi nhỏ trên fixture thử quy trình spec → test → browser → bằng chứng.

Yêu cầu nền ở [docs](../docs/README.md), không nhân bản vào từng spec.

- [Sổ khách V7](v7-so-khach-theo-sheet.md): prototype fixture; [backend đề xuất](v7-backend-so-khach.md), [API thử](v7-backend/ket-noi-giao-dien.md).
- [Nhập chuyến kiểu Sheet](v7-nhap-kieu-sheet.md): hàng trống, dán tự trải vào ô, nháp + Lưu; sửa đè/xóa tại ô mọi chuyến kể cả sổ gốc và tháng khóa, đổi ngày thì sang bảng tháng đó (`NHAP-SHEET-01`, 22/10/2026); có bản xem HTML, chưa code live. Backend: [sửa/xóa chuyến và dòng sổ gốc](v7-sua-xoa-chuyen.md).
- [Phụ phí nhiều loại](v7-phu-phi-nhieu-loai.md): danh mục loại phụ phí, nhiều dòng phụ phí mỗi chuyến, mỗi sổ chọn tối đa 3 cột riêng + cột Khác, áp một khoản cho cả lô (`PHU-PHI-01`, 28/10/2026; thiết kế ĐỀ XUẤT, chưa Penpot, chưa code). Spec con: [tách phụ phí theo bảng PS](v7-phu-phi-tu-ps.md) — đọc `CONT_MASTER` của bộ lập bill, tách Khác/Phụ phí ban đầu thành Neo/Điện/Ghép, giữ nguyên tổng tiền (ĐỀ XUẤT 29/10/2026, chưa code).
- [Bảng giá theo ngày hiệu lực](v7-bang-gia-hieu-luc.md): mỗi sổ một bảng giá (đợt giá × kho đi × giá khách/giá TT), tự điền đơn giá trống theo ngày xe nhập kho, không tự sửa chuyến đã ghi, cờ "khác bảng giá" (`BANG-GIA-01`, 29/10/2026; thiết kế ĐỀ XUẤT, Claude làm, chưa code).
- [Gắn mặt hàng và nhóm ô chọn khách](v7-mat-hang-chon-khach.md): đọc `LOAI HANG` của `TONG` khi nạp, SQL gán cho DB đang chạy, `list_customers` trả mặt hàng, ô chọn khách nhóm/tìm theo mặt hàng (`MH-01`, 23/10/2026); chưa triển khai.
- [Trang tổng quan công nợ](v7-dashboard.md): trang đầu, chỉ đọc; tổng nợ, theo mặt hàng, theo tháng, top khách, việc cần làm, hôm nay (`DASH-01`, 23/10/2026); backend giao Codex, giao diện chờ mockup.
- [Chuẩn bị gộp V7](../docs/v7-merge-prep.md): nguồn commit, phân loại, phần loại, kiểm và giới hạn.
- [Chính sách V7 còn mở](v7-chinh-sach-mo.md): phương án cho D04, D05/D06, D07, ai xem Lịch sử và case 7.11c, chờ chủ nghiệp vụ chọn (ĐỀ XUẤT).
- [Dán chứng từ vào phiếu thu](v7-dan-chung-tu.md): dán ảnh chuyển khoản từ Zalo/WeChat vào phiếu thu, chỉ đính ảnh, chưa đọc số (`CHUNG-TU-01`, 29/10/2026; [bản xem HTML](../cong-no-web-handoff/preview/mockups/dan-chung-tu/index.html) đã duyệt; backend đã triển khai trên `hao`, giao diện đã code).
- [Cấn trừ giữa hai sổ](can-tru-hai-so.md): ghi cả sổ lấy tiền và sổ được trả trong một lệnh, chốt 20/10/2026; [bản đặt mockup HTML](can-tru-hai-so-mockup-html.md), [bản sửa vòng 2](can-tru-hai-so-mockup-vong-2.md).
- [Kế hoạch triển khai V7 lên `hao`](v7-backend/ke-hoach-trien-khai-hao.md): thứ tự bước deploy, điều kiện an toàn, danh tính Tailscale tối thiểu, gate bắt buộc đóng vs để sau, thứ tự chạy `SONG-SONG-01`; ĐỀ XUẤT, không phải quyền chạy.
