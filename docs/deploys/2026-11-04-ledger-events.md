# Triển khai tay: Lịch sử đọc riêng, GET sổ nhẹ hơn (4/11/2026)

**ĐÃ CHẠY trên `hao` ngày 4/11/2026 (22:40 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Spec [`mo-so-nhanh-02`](../../specs/mo-so-nhanh-02.md), người dùng chốt 4/11/2026. Không đổi quy tắc tiền nên không có quyết định mới.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#320 (`943d8f2`) |
| Migration | `2026-11-04-v7-ledger-events.sql` (sha256 `80b098f0…`): tách biểu thức `events` của `get_ledger` thành `_ledger_events`, thêm `get_ledger_events`. Không đổi bảng, view, loại event, hàm ghi, dữ liệu hay quyền cũ. |
| Release app | `473bb0a` → `943d8f2` |
| Ghi tiền | Không. |

## Kết quả

Đo từ trình duyệt máy làm việc qua Tailscale, trung vị `fetch` lặp lại, sau khi hết tải khởi động.

| Sổ | Thân JSON | gzip trên dây | GET trước | GET sau | Mở Lịch sử (route mới) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 176 | 54,7 → 23,2 KB | 8,1 → 4,6 KB | 227 ms | 216–236 ms | 84 ms, 3,1 KB |
| 14 | 406,6 → 163,3 KB | 33,4 → 17,7 KB | 426 ms | 408–458 ms | 101 ms, 10,7 KB |
| 79 (lớn nhất) | 1.397 → 607 KB | 91,5 → 47,0 KB | 1.964 ms | 1.854–1.889 ms | 198 ms, 34,3 KB |

- **Thân giảm khoảng 2,5 lần**, đúng dự kiến trong spec (người dùng đã chấp nhận thay vì mục tiêu 3 lần).
- **Thời gian GET gần như không đổi**: sổ 14 nằm trong sai số, sổ 79 nhanh hơn khoảng 5%. Bước này không đụng phần tốn thời gian (SQL dòng sổ gốc, chiếu Sheet).
- **Đánh đổi:** trước đây bấm Lịch sử là có ngay vì đã tải sẵn; nay chờ một lượt mạng. Sổ 79 từ lúc bấm tới khi hiện danh sách: 225 ms.

**Kết quả `get_ledger` giữ nguyên:** băm JSON kèm `version` trùng 238/238 sổ giữa lần đọc ngay trước cửa sổ và lần đọc ngay sau. Khung Lịch sử sổ 79 trên `hao`: 658 dòng, khớp số sự kiện; mở sổ không gọi route Lịch sử; mở khung gọi một lần; đóng mở lại không gọi thêm; không có lỗi console.

## Trước

- `hao` chạy `473bb0a`. DB `webdebit_v7`: 238 sổ, 9.373 event. Không có kết nối khác.
- Có DB `webdebit_v7_try_split` và một tiến trình `reconcile-try` chiếm một lõi CPU trong lúc đo, không thuộc đợt này, không đụng. Tiến trình đã tự kết thúc lúc đo chốt. DB tạm đó vẫn còn.

## Bản sao thử

Dump, restore vào DB tạm trên `hao`, xóa sau khi thử.

- Băm `get_ledger` 238/238 sổ trùng sau migration hai lượt, sau rollback và sau nâng lại. Sau rollback không còn hai hàm mới.
- `get_ledger_events` khớp `events` và `version` của `get_ledger` ở mọi sổ.
- Checker 9 mục OK. Số event và tổng nợ không đổi.
- Diễn tập nguyên kịch bản cửa sổ trên bản sao, thay lệnh dừng dịch vụ bằng lệnh rỗng: đạt.

## Cửa sổ dừng ghi (22:40:34–22:40:36 giờ VN)

- Băm mọi sổ trước khi dừng. Dừng timer `v7-reconcile-auto` (không có lượt đang chạy) và API, không còn kết nối khác. Ghi dấu vân tay, dump kèm hash, đọc lại được (624 mục).
- Áp migration với `ON_ERROR_STOP`, một `COMMIT`.
- Dấu vân tay (số dòng các bảng, số dư từng khách từng tháng, 908 dòng) không đổi. Checker 9 mục OK.
- Bật lại API và timer. API gián đoạn 2 giây; `healthz` 200.
- Quyền sau migration: `sokhach_app` gọi được `get_ledger_events`, `sokhach_reader` không; `_ledger_events` không ai gọi thẳng được.

## Đổi release

`git archive 943d8f2 … | webdebit-release.sh deploy 943d8f2…` dưới user `webdebit-deploy`. `.release-sha` = `943d8f2`, `/healthz` 200, không có file do root sở hữu, migration trong release trùng hash bản đã chạy, journal API không có lỗi.

Script báo không dọn hết hai release cũ (`4592a2d`, `e4f3a56`) vì có file của user khác, như các đợt trước.

**Ngay sau khởi động GET chậm tạm thời:** khoảng một phút đầu sổ 176 đo được 628 ms, sổ 79 khoảng 3 giây, do lượt nền của API sau restart cộng với tiến trình nói trên. Hết tải thì về mức ở bảng trên. Đo so sánh sau deploy phải chờ qua khoảng này.

**Bằng chứng:** thư mục `backup-20261104-ledger-events` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700). Gồm dump kèm sha256, file SQL, dấu vân tay trước và sau, băm từng sổ trước và sau, log áp thật, checker.

## Rollback

- App: `webdebit-release.sh deploy 473bb0a4b0214d57a6796fe710b9196f8833d5d3`. Release cũ chạy được với DB mới.
- DB: xem [runbook](../v7-deploy-runbook.md#lịch-sử-đọc-riêng-mo-so-nhanh-02--nâng-db-đã-chạy-trên-hao-4112026).

## CÒN MỞ

- Người dùng chưa tự thử khung Lịch sử trên `hao` (lọc, làm một lệnh rồi thấy dòng mới). Đường "làm một lệnh" mới kiểm bằng test trình duyệt với máy chủ giả, không ghi thử lên sổ thật.
- Bước 3: thời gian `get_ledger` sổ lớn và chiếu hàng chờ, chưa làm.
