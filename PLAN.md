# PLAN — hiện tại (31/10/2026)

Mục tiêu gần nhất: **bắt đầu chạy song song Sheet–web chính thức** theo [`SONG-SONG-01`](docs/decisions/song-song-01.md)/[`SONG-SONG-02`](docs/decisions/song-song-02.md). ĐỀ XUẤT (Claude, 31/10/2026): ngày bắt đầu **1/11/2026** để trọn tháng 11 là tháng song song; chuyển hẳn sau khi đối soát cuối tháng 11 khớp (mục F4 của [checklist](docs/song-song-checklist.md)). Ngày bắt đầu do chủ nghiệp vụ chốt (F2, CÒN MỞ).

So với bản 22/10: Harness, V7 trên `hao` (tự deploy khi merge `main`), capture-only Sheet, backup hằng ngày + phục hồi thử (C1, C2 ĐẠT), hai khách bị giữ sau mốc (A3 ĐẠT, [`SONG-SONG-03`](docs/decisions/song-song-03.md)), đường Sheet → web cho chuyến (`CONT_NGUON`), giá, phiếu thu ([`THU-SHEET-01`](docs/decisions/thu-sheet-01.md)) và phụ phí PS, nút kết luận CHỜ KIỂM, tab Đòi nợ, Debit Note v3 đều đã trên `main`. Việc chặn còn lại là **vận hành**, không phải tính năng.

## Việc chặn ngày bắt đầu (theo checklist)

| # | Việc | Ai | Trạng thái 31/10 | Bằng chứng cần |
| --- | --- | --- | --- | --- |
| A2 | Web khớp tổng từng khách với Sheet (dán bù sau mốc) | Người nhập bấm các nút ghi từ Sheet; Claude đối soát | Đối soát chỉ đọc trên bản xuất cuối ngày 30/10: 223/236 khách khớp, 13 lệch; phần lớn chờ bấm "Ghi phiếu thu từ Sheet", điền ngày cho phiếu thu Sheet thiếu ngày, duyệt chuyến mới + giá; chi tiết ở checklist A2 | `DOI SOAT: DAT` trên bản xuất ngày bắt đầu |
| B1, B2 | Mỗi người nhập một tài khoản Tailscale; hai người mở/khóa một tháng ra hai tên trong Lịch sử | Admin (người dùng) mời vào tailnet; người nhập thao tác | CHƯA (tailnet một tài khoản) | Danh sách tailnet ngoài Git; hai cặp dòng Lịch sử |
| E1 | Một lần kết luận CHỜ KIỂM thật trên `hao` | Người nhập | Nút "Tính vào sổ"/"Loại" đã trên `hao`; hiện không có chuyến CHỜ KIỂM nên chờ lần phát sinh đầu | Dòng Lịch sử của lần kết luận |
| C4 | Người nhập tự chạy đối soát cuối ngày một lần theo [hướng dẫn](docs/doi-soat-cuoi-ngay.md) | Người nhập | CHƯA; Claude đã chạy 29, 30 và 31/10 | Một lần chạy có mã thoát và số đếm |
| F2 | Chốt ngày bắt đầu song song | Chủ nghiệp vụ | ĐỀ XUẤT 1/11/2026 | Dòng cập nhật `SONG-SONG-02` |

## Không chặn — làm trong lúc chạy song song, xong trước ngày chuyển hẳn

- Người dùng tự đi hết luồng trên web thật: tab Đòi nợ (`NHAC-NO-01`), xuất Debit Note đối chiếu mẫu (`DEBIT-NOTE-02`), xóa một dòng điều chỉnh (`XOA-DC-THANG-01`).
- Khách còn mở của `SONG-SONG-03` (2): chủ nghiệp vụ xác định số phải thu trước F4.
- Chép bản xuất chat Zalo lên `hao` để trang Chat Zalo có dữ liệu (`NHAC-NO-01`, sửa đổi ZALO-CHAT-01).
- Bỏ đường export cũ khi Sheet xóa ba tab (sau khi đồng bộ chuyến đã đọc `CONT_NGUON` ổn định).
- Tạm dừng thêm tính năng mới cho tới khi song song đã chạy.

Cập nhật bảng khi trạng thái đổi; lộ trình ở `docs/roadmap.md`, điều kiện khởi động ở `docs/song-song-checklist.md`.
