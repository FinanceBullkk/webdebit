# Triển khai tay: thu tháng theo từng sổ, Tổng quan lọc chéo (9/11/2026)

**ĐÃ CHẠY trên `hao` ngày 9/11/2026 (13:13 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) sau khi người dùng nói "Merge khi xanh" trong chat. Quyết định: [`DASH-08`](../decisions/dash-08.md).

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#361 (`0b5b63e`, migration), FinanceBullkk/webdebit#360 (`4b22b12`, trang) |
| Migration | `2026-11-09-v7-thu-thang-theo-so.sql` (sha256 `6dabd12e…`): thay thân `get_dashboard_debt`, thêm `this_month.customers`. Không đổi bảng, view, hàm ghi, phân bổ, dữ liệu, quyền hay ngưỡng. |
| Release app | `72228d1` → `4b22b12` (`Deploy hao` dừng ở cổng SQL như dự kiến, đưa release tay) |
| Ghi tiền | Không. |

## Trước

- `hao` chạy `72228d1`. Journal `sudo` 30 phút trước bản thử và trước cửa sổ chỉ có lệnh của phiên này; phiên Claude khác đều nhàn rỗi.
- Máy đối soát `v7-reconcile-auto` chạy lượt 13:05 và xong 13:12:43 (`success`); cửa sổ mở sau đó.

## Bản sao thử (12:5x)

Dump (sha256 `0033fc8e…`), restore vào DB tạm trên `hao`, migration hai lượt (101 ms, 99 ms; một `COMMIT` mỗi lượt). Đã xóa DB tạm.

- Catalog ổn định giữa hai lượt; dấu vân tay (số dư từng khách từng tháng, số event, số dòng các bảng) không đổi; checker 9/9. Quyền: app và reader gọi được, `PUBLIC` không.
- `get_dashboard_debt` trước và sau: bỏ `this_month.customers` thì JSON trùng từng byte. 11 sổ có thu hoặc phát sinh tháng 11 (4 sổ đã hết nợ); cộng đúng tổng `this_month`; từng sổ bằng dòng tháng này của `get_ledger`; mặt hàng khớp `customers[]`.
- Rollback bằng `2026-11-06-v7-ngay-tra-that.sql`: Tổng quan trùng bản trước từng byte, dấu vân tay không đổi.
- Thời gian hàm (năm lần, trung vị): 718 ms → 794 ms.

## Cửa sổ dừng ghi (13:12:49–13:13:10 giờ VN)

- Dừng timer `v7-reconcile-auto` và API, không còn kết nối vào DB. Dấu vân tay, dump kèm hash (`b76b4ddb…`), đọc lại được (34 bảng).
- Áp migration với `ON_ERROR_STOP`: 91 ms, một `COMMIT`. Catalog sau áp trùng bản thử.
- **Đối soát tổng khách: dấu vân tay không đổi**; 239 sổ, tổng 63.301.848.356 đ, 10.052 event. Checker 9/9.
- Trên DB thật: mọi trường cũ trùng từng byte; 13 sổ có thu hoặc phát sinh tháng này (5 sổ đã hết nợ), cộng đúng tổng, từng sổ bằng `get_ledger`.
- Bật lại API và timer: `active`, loopback 403 (sống). API gián đoạn 21 giây.

## Đổi release

`git archive 4b22b12 …` (cùng các thư mục workflow dùng) `| webdebit-release.sh deploy 4b22b12…` dưới user `webdebit-deploy`. `.release-sha` = `4b22b12`, `healthz` 200, journal API không có lỗi mức `err`. Script báo không dọn hết vài release cũ vì có file của user khác, như các đợt trước.

## Kiểm sau

Đọc `GET /api/v7/dashboard/debt` qua Tailscale Serve và chạy `DashboardModel` của release mới, chỉ đọc: số từng khách khớp tổng server (lọc tại chỗ được bật); dải đầu chia theo từng mặt hàng hoặc từng mức rủi ro cộng đúng Còn phải thu; Thu tháng chia theo mặt hàng cộng đúng tổng `this_month`.

**Bằng chứng:** thư mục `backup-20261109-thu-thang-theo-so` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700): dump trước và lúc dừng kèm sha256, SQL kèm sha256, script, dấu vân tay, catalog, JSON Tổng quan và `get_ledger` trước và sau, log áp, checker, kết quả so.

## Rollback

- DB: chạy lại `2026-11-06-v7-ngay-tra-that.sql` (đã thử trên bản sao). Trang mới vẫn chạy với DB cũ: thẻ Thu tháng ghi "cả công ty" khi lọc.
- App: `webdebit-release.sh deploy 72228d11ec6d9a2f4a25d5c2acc040a7be3a25a2`.

## CÒN MỞ

- Người dùng tự đi hết luồng lọc trên `hao`.
- `get_dashboard_debt` chậm thêm khoảng 75 ms (đã chậm từ trước).
