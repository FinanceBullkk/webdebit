# SONG-SONG-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt trong chat 21/10/2026: (1) **Mốc nạp lên `hao` là bản làm sạch `clean-v2` (xuất khoảng 9 giờ sáng 21/10/2026, 236 khách, 877 kỳ số dư đầu), không phải bản xuất đúng ngày bắt đầu song song** — ngoại lệ có chủ đích so với vế (2) của [`SONG-SONG-01`](song-song-01.md) vì bản clean-v2 đã tổng duyệt không giữ khách nào, còn bản 7pm cùng ngày giữ lại hai khách chưa giải quyết (một tab trùng tên, một thiếu số dư đầu). Phần phát sinh trên Sheet sau mốc phải dán bù (vế (3)); hai khách bị giữ xử lý tay riêng. (2) **Đối soát định kỳ theo tổng từng khách (vế (4) của `SONG-SONG-01`): hằng ngày vào cuối ngày, do người nhập chạy; chủ nghiệp vụ xem tổng kết cuối tuần và cuối tháng** (cuối tháng là điều kiện chuyển hẳn).

## Ngày / nguồn

21/10/2026, xác nhận trong chat ("dùng clean-v2", "Chốt: đối soát hằng ngày cuối ngày do người nhập chạy, chủ nghiệp vụ xem tổng kết cuối tuần và cuối tháng")

## Hiệu lực và giới hạn

ĐÃ CHỐT. **ĐÃ TRIỂN KHAI trên `hao` 21/10/2026** (runbook bước 0–6 theo [PR #48](https://github.com/FinanceBullkk/webdebit/pull/48), chạy qua Tailscale Serve): DB `webdebit_v7` đã nạp mốc, checker 8/8 OK, đối soát với mốc `DOI SOAT: DAT`, số đếm `webdebit_ledger` không đổi. Chi tiết và bằng chứng nằm ngoài Git. **Chưa kiểm chứng:** hai người dùng khác nhau cho ra hai actor khác nhau (tailnet hiện một tài khoản). **Cập nhật 22/10/2026:** kiểm trùng khi dán lô ([`NEWTRIP-01`](newtrip-01.md)) và [`V7-CSM`](v7-csm.md) (D05/D06, D07) đã có trên `hao`; đợt nâng 22/10 đối soát lại `DOI SOAT: DAT` đủ 236 khách. Đợt này không chụp số đếm `webdebit_ledger` trước khi nâng, nên mục "số đếm `webdebit_ledger` không đổi" chưa kiểm chứng cho riêng đợt 22/10 (migration chỉ chạy trên `webdebit_v7`). CÒN MỞ: công cụ phát hiện sửa trên dòng đã có trong mốc (công cụ so tổng từng khách Sheet–web đã có từ PR #54, không thay việc này), ngày bắt đầu song song chính thức, backup định kỳ V7 (hiện chỉ có backup trước mỗi đợt nâng), kiểm hai người dùng khác nhau ra hai actor.
