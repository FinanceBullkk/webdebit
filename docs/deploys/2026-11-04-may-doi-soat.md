# Triển khai tay: máy tự đối soát Sheet–web mỗi giờ (4/11/2026)

**ĐÃ CHẠY trên `hao` ngày 4/11/2026 (10:21–10:34 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Người dùng chốt hướng, từng quy tắc và việc thêm timer trong chat cùng ngày ([`MAY-DOI-SOAT-01`](../decisions/may-doi-soat-01.md)).

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#292 (khóa lại tháng máy bỏ mở, nạp lại "Máy đã tự làm hôm nay"), #293 (máy đối soát), #294 (chặn đơn giá đổi chỗ) |
| Migration | Không có. Mã lên bằng `Deploy hao` |
| Thêm trên `hao` | Unit `v7-reconcile-auto.service` có `--fix`, timer `v7-reconcile-auto.timer` (phút :05, 7–22 giờ VN), bộ 6 CSV mốc ở `/srv/v7/so-goc-20261020` (`root:v7app`, 750/640), kết quả `reconcile.json`, `reconcile-log.jsonl` |
| Ghi tiền | Có. Lượt đầu ghi một giá cho một khách, tổng nợ +95.000.000 đ; từ đó mỗi giờ theo quy tắc |
| Bằng chứng | Thư mục `backup-20261104-may-doi-soat` trong `/srv/v7` trên `hao`, ngoài Git, quyền 700 |

## Trước

- `hao` chạy `d8358c0`. Tổng nợ trên web 67.104.805.665 đ, event cuối 9.168. Dump `truoc.dump` kèm sha256.
- Một phiên Claude khác ghi tay theo trả lời của người dùng lúc 09:41 và 10:05 (phiếu không ngày, thay phiếu sổ gốc, giá từng container), người làm `claude`. Hai phiên báo cho nhau qua tin nhắn; job của phiên này chưa ghi gì trước 10:21.

## Chỉ báo trên DB thật (không ghi)

Chạy unit tạm không có `--fix`, ba lần trong sáng. Lần cuối bằng đúng mã của #294 (10:05–10:15): 234/236 khớp, 1 khách web đi trước Sheet, 1 khách bị giữ, không có khách lệch tháng ngoài khách vừa nhận phiếu. Một lượt khoảng 8–10 phút ở `Nice=10`, bộ nhớ đỉnh 170 MB.

## Bản sao thử

Dump, restore vào DB tạm, vào bằng `postgres` rồi `SET ROLE v7_app`, chạy bản release `4592a2d` với `--fix` trên một bản tải (09:38–09:59):

- 6 khách được sửa; tổng nợ đổi −2.538.850.010 đ, bằng đúng tổng các nhóm đã chọn; khách khác giữ nguyên số dư.
- Không có cặp mở/khóa lệch, không tháng nào máy bỏ mở. `v7_post_deploy_check.sql` đạt.
- Chạy lại lần hai trên cùng bản tải: không còn gì để ghi, tổng nợ không đổi.
- Đã xóa DB tạm.

## Phát hiện trong lúc làm

- **Chốt khớp tổng chặn được lỗi thật.** Một sổ có 78 dòng "chỉ có TỔNG" đã tính sẵn trong sổ gốc; ghi mù sẽ cộng sai 274 triệu. Máy không chọn nhóm đó, và điều kiện đã siết để các dòng này không còn là việc.
- **Dòng tiền không container có thể là chuyến chưa nhập xong.** Một dòng 43,5 triệu có container sau vài giờ, máy đưa thành chuyến thật. Nếu lúc đó đã ghi dòng điều chỉnh thì tính trùng, nên thêm nhóm tự hủy dòng điều chỉnh của máy.
- **Chỗ mù của khớp tổng.** Một tab Sheet bị xếp lại một phần cột: container đổi chỗ, giá giữ nguyên. Tổng vẫn đúng, tổ hợp vẫn khớp, máy sẽ ghi sai giá từng container. Một phiên Claude khác phát hiện trước khi bật; đã kiểm lại trên dữ liệu thật rồi thêm chốt `shuffled_months` (#294).
- **33 khách "lệch tháng" không phải lỗi ghi.** Sau khi áp `CAN-DU-01` lên số Sheet, cả 33 khớp từng tháng.

## Bật

1. Sao lưu; đặt hai unit, `systemd-analyze verify` không lỗi; `daemon-reload`.
2. `systemctl start v7-reconcile-auto.service` (10:21–10:30), `Result=success`, 554 giây.
3. Đọc kết quả, đối chiếu dòng Sheet của khách máy vừa sửa với giá đã ghi, rồi `systemctl enable --now v7-reconcile-auto.timer`.

## Sau

- 234 khớp, 1 khách web đi trước Sheet (lệch đúng bằng phần đó), 1 khách bị giữ vì 8 dòng tháng 11 trên Sheet có đơn giá mà chưa có cột TỔNG. Theo tiền, khách khớp chiếm 45% số nợ, vì hai khách còn lại là hai khách lớn nhất.
- Tổng nợ 67.199.805.665 đ, đổi +95.000.000 đ, đúng một khách. Giá máy ghi trùng dòng Sheet (đơn giá + phụ phí = TỔNG).
- Không có cặp mở/khóa lệch của máy, không tháng nào máy bỏ mở. `v7_post_deploy_check.sql` đạt.
- Trong cùng cửa sổ, các event `rewrite_trip_fees`, `set_book_fee_columns` của máy là `MAY-PS-01` (FinanceBullkk/webdebit#295, phiên khác, merge 10:26), giữ nguyên tổng, không phải của job này.
- Đối soát độc lập từ máy khác, qua API và đúng các bước của [hướng dẫn tay](../doi-soat-cuoi-ngay.md), trên bản tải sau lượt đầu: 234 khớp, 1 lệch tổng, 1 bị giữ, trùng kết quả của máy.
- Tab Việc cần làm trên `hao`: dải đối soát hiện đúng, còn 5 sổ có việc thay vì 50, 41 sổ đã khớp được ẩn, không lỗi JS.

## Rollback

- Dừng máy: `systemctl disable --now v7-reconcile-auto.timer`. Muốn đối soát mà không ghi thì bỏ `--fix` khỏi `ExecStart`, `daemon-reload`, bật lại timer.
- Việc máy đã ghi vẫn nằm trong sổ và Lịch sử, người làm `may-theo-sheet`; sửa tay nếu sai. Về hẳn lúc trước đợt: restore `truoc.dump` vào DB mới (quy trình M2-11).

## CÒN MỞ

- Cảnh báo khi máy lỗi: hiện chỉ thấy ở đầu tab Việc cần làm và journal; chưa có kênh đẩy (audit DevOps #2). Khi không còn người nhập thì đây là chỗ thiếu quan trọng nhất.
- Kiểu lệch cột ở chuyến web chưa có giá thì máy không bắt được; máy ghi theo Sheet vì Sheet là sổ chính thức.
- Chủ sổ chưa tự đi hết luồng trên `hao`.
