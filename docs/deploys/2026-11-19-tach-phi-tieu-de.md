# Ghi dữ liệu một lần: tách phụ phí theo tên cột trên tab khách (19/11/2026)

**ĐÃ CHẠY trên `hao` ngày 19/11/2026 (12:33–12:36 giờ VN).** Người dùng chốt [`TACH-PHI-TIEU-DE-01`](../decisions/tach-phi-tieu-de-01.md) và bảo "Chạy thật" sau khi xem số đếm. Phiên giữ hàng merge cấp lượt `hao` sau khi #505 triển khai xong và #510 lên `hao`; trong cửa sổ không merge gì.

| Mục | Nội dung |
| --- | --- |
| Công cụ | `tools/v7_split_fee_by_header.py` trong release `3a193dd` (#506, #508, #510), mã băm trùng bản đã thử |
| Đổi schema, hàm, release | Không |
| Ghi tiền | Không đổi tiền: 1.372 dòng ở 80 sổ đổi loại phụ phí (`rewrite_trip_fees`), tổng phụ phí từng dòng giữ nguyên |

## Bản sao thử

Dump, restore vào DB tạm trên `hao`, chạy đúng `run()` của công cụ dưới role `v7_app`, xóa DB tạm sau khi thử. Chạy hai lần.

- **Lần 1 (release `0a2eaad`):** 1.342 dòng ghi, 13 lỗi `FEE_SIGN_INVALID`: dòng tab có ô phí âm (giảm trừ) bị xếp vào loại chỉ nhận số dương, và lỗi dừng phần còn lại của sổ đó. Sửa ở #510: dòng có ô âm để nguyên (`SHEET_NEGATIVE`).
- **Lần 2 (release `3a193dd`):** 1.372 dòng trong 287 giây, 0 lỗi. Chạy lại: 0 dòng còn phải ghi. Checker 9/9.
- Đo trước/sau giống hệt: số dư từng khách và từng tháng, Thành tiền và đơn giá mọi dòng sổ gốc, `legacy_row`, `adjustment`, `receipt`, `receipt_line`, `opening_balance`, `trip`, giá hiện hành từng chuyến, **tổng phụ phí từng chuyến và từng dòng sổ gốc**, tháng đang mở.

## Cửa sổ dừng ghi (12:33:15–12:36:12 giờ VN)

- Trước khi dừng: không event nào trong 5 phút, journal `sudo` chỉ có lần deploy #510 và máy canh chỉ đọc. Đợi qua lượt máy canh 12:32. Máy đối soát không chạy.
- Dừng timer `v7-reconcile-auto` và API, không còn kết nối khác. Đo, dump kèm hash, đọc lại được (57 bảng).
- Đếm lại trên DB đã dừng: khớp bản thử (1.372 dòng, 80 sổ).
- Ghi: 1.372 dòng trong 139 giây, 0 lỗi. 1.652 event: 1.372 `rewrite_trip_fees` (người làm `claude`), 280 `month_lock` (140 tháng mở rồi khóa lại theo [`MAY-KHOA-01`](../decisions/may-khoa-01.md)).
- Đo lại: mọi dòng ổn định giống hệt trước. Checker 9/9.
- Bật lại API và timer: `active`, `healthz` 200. API gián đoạn khoảng 3 phút.

Khoản phụ phí đang hiệu lực theo loại, trước → sau: Neo 25 → 1.207, Điện 2 → 287, Ghép 2 → 22, Health + KĐ 7 → 23, Bảo hiểm 0 → 9, Kiểm định 0 → 4, Khác 579 → 445, Phụ phí ban đầu 1.994 → 913, Giảm trừ 103 không đổi.

## Sau cửa sổ

- Đếm lại mọi sổ: 0 dòng còn phải ghi; 1.375 dòng đã đúng loại.
- Dòng trong ảnh người dùng gửi (một chuyến tháng 10 có bốn ô phí) nay là bốn khoản Neo, Ghép, Bảo hiểm, Health + KĐ, tổng bằng ô Khác cũ.
- Journal API không có lỗi mức `err`.

**Bằng chứng:** thư mục `backup-20261119-tach-phi` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700): dump trước và dump lúc dừng kèm sha256, script, phép đo, kết quả đếm và ghi, checker.

## Rollback

Mỗi dòng có event `rewrite_trip_fees` kèm `before`: sửa lại khoản phụ phí trong khung chi tiết, hoặc restore dump lúc dừng nếu cần cả đợt.

## CÒN MỞ

- Để nguyên, chờ người xem nếu cần: 128 dòng có ô phí âm, 175 dòng khớp nhiều chuyến, 32 dòng ô phí không cộng ra TOTAL − đơn giá, 10 dòng web đã phân loại khác, 20 dòng ô không đọc được, 127 dòng lệch cột.
- Máy đối soát chưa tự tách chuyến mới theo tên cột: chuyến về sau vẫn vào Khác cho tới khi chạy lại công cụ hoặc làm phần máy.
- Chưa thử xuất debit note ở một sổ vừa tách.
