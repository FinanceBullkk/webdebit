# Triển khai tay: ngày trả gần nhất là ngày tiền về (6/11/2026)

**ĐÃ CHẠY trên `hao` ngày 6/11/2026 (09:55 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Sửa cách đọc ngày của [`DASH-03`](../decisions/dash-03.md) mục 3, không đổi quy tắc tiền nên không có quyết định mới.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#344 (`28b8fcb`) |
| Migration | `2026-11-06-v7-ngay-tra-that.sql` (sha256 `0aa583ad…`): thay thân `get_dashboard_debt`. Không đổi bảng, view, hàm ghi, phân bổ, dữ liệu, quyền hay ngưỡng 60/90 ngày. |
| Release app | `6639377` → `28b8fcb` |
| Ghi tiền | Không. |

## Kết quả

| | Trước | Sau |
| --- | ---: | ---: |
| Rủi ro cao | 44 sổ, 24,48 tỷ quá hạn | 40 sổ, 23,36 tỷ quá hạn |
| Theo dõi | 8 sổ | 12 sổ |
| Không quá hạn | 17 sổ | 17 sổ |
| Sổ có quá hạn mà quá 60 ngày chưa trả | 36/52 | 26/52 |
| Sổ có ngày trả rõ | 20/63 | 43/63 |

- Đổi nhãn: 4 sổ từ Rủi ro cao sang Theo dõi (1,124 tỷ quá hạn), không sổ nào đổi chiều ngược lại.
- Ngày trả đổi ở 27 sổ, 23 sổ lệch từ 15 ngày, 5 sổ có ngày trả sớm hơn bản cũ.
- 20 sổ còn ngày trả không rõ: màn vẫn hiện "trong tháng", và ngày đó vẫn dùng để tính số ngày chưa trả.

## Trước

- `hao` chạy `6639377`. DB `webdebit_v7`: 239 sổ, 9.965 event. Không có event nào trong 10 phút trước cửa sổ, DB không có kết nối khác.
- `ListAgents`: một phiên khác đang chạy; journal `sudo` 10 phút gần nhất chỉ có lệnh của phiên này.

## Bản sao thử

Dump, restore vào DB tạm trên `hao`, chạy hai lần: lúc soạn PR và ngay trước cửa sổ, kết quả như nhau. Đã xóa DB tạm sau khi thử.

- Migration hai lượt: 126 ms và 111 ms, catalog ổn định, dấu vân tay không đổi, checker 9/9. Quyền: app và reader gọi được, `PUBLIC` không.
- So `get_dashboard_debt` từng sổ: tiền, nhóm hạn trả, tổng quá hạn, số khách có quá hạn, chuyến và thu/phát sinh tháng này trùng ở 69 sổ.
- Đối chiếu `get_receipt_book`: cả 43 sổ rõ ngày trùng ngày muộn nhất của sổ đó trên Bảng thu.
- Rollback bằng migration cũ: Tổng quan trùng bản trước từng byte, dấu vân tay không đổi.
- Thời gian hàm chậm hơn khoảng 95 ms: trung vị 625 ms → 721 ms, do đọc thêm `raw_date` ở mỗi dòng thu.

## Cửa sổ dừng ghi (09:54:59–09:55:15 giờ VN)

- Dừng timer `v7-reconcile-auto` (không có lượt đang chạy) và API, không còn kết nối khác. Ghi dấu vân tay, dump kèm hash, đọc lại được (34 bảng).
- Áp migration với `ON_ERROR_STOP`: 121 ms, một `COMMIT`.
- Catalog sau áp trùng bản thử. **Đối soát tổng khách: dấu vân tay (số dư từng khách từng tháng, số event, số dòng các bảng) không đổi**; 239 sổ, tổng 64.078.597.024 đ. Checker 9/9.
- Trên DB thật, so Tổng quan từng sổ và đối chiếu Bảng thu cho cùng số với bản thử.
- Bật lại API và timer: `active`, loopback 403 (sống). API gián đoạn 16 giây, phần lớn do chạy các phép so ngay trong cửa sổ.

## Đổi release

`git archive 28b8fcb … | webdebit-release.sh deploy 28b8fcb…` dưới user `webdebit-deploy`. `.release-sha` = `28b8fcb`, `healthz` 200, không có file do root sở hữu, migration trong release trùng hash bản đã chạy, journal API không có lỗi mức `err`.

Script báo không dọn hết một số release cũ vì có file của user khác, như các đợt trước.

## Kiểm trên trình duyệt

Mở `dashboard-v7.html` trên `hao`, chỉ đọc: chip hiện "Rủi ro cao 40". Cả 10 dòng của bảng khách hiện đúng cột Trả và Đi hàng theo `GET /api/v7/dashboard/debt`, đúng thứ tự. API trả 40 sổ Rủi ro cao, 12 Theo dõi, 17 Không quá hạn, 43/63 sổ rõ ngày.

**Bằng chứng:** thư mục `backup-20261106-ngay-tra-that` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700). Gồm dump trước và dump lúc dừng kèm sha256, file SQL kèm sha256, script, dấu vân tay, catalog, JSON Tổng quan trước và sau, log áp thật, checker, kết quả so.

## Rollback

- DB: chạy lại `2026-10-29-v7-tong-quan-quan-ly-no.sql`, xem [runbook](../v7-deploy-runbook.md#ngày-trả-gần-nhất-là-ngày-tiền-về-dash-03--nâng-db-đang-có-đã-chạy-trên-hao-6112026).
- App: `webdebit-release.sh deploy 66393771910c9628bd61798e910058a1e202b73a`. App không đọc trường mới nên release nào cũng chạy được với DB nào.

## CÒN MỞ

- Nhãn Rủi ro cao vẫn gần như không phân biệt được: 40/52 sổ có quá hạn. Ngưỡng do người dùng quyết, đợt này không đổi.
- Dòng thu có ngày sau lúc nạp sổ (1 dòng thật, nhiều khả năng Sheet đảo ngày tháng) được coi là không rõ ngày ở cả Tổng quan và Bảng thu. Muốn có ngày đúng thì phải sửa ô trên Sheet.
- `get_dashboard_debt` đã chậm từ trước, nay thêm khoảng 95 ms.
