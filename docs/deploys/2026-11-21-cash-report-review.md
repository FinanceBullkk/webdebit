# Triển khai tay: xác nhận khoản thu chi Zalo (ZALO-THU-CHI-01 PR-3, 21/11/2026)

**ĐÃ CHẠY trên `hao` ngày 21/11/2026 (16:47 UTC).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và mục runbook "Xác nhận khoản thu chi Zalo (ZALO-THU-CHI-01 PR-3)". Đây là việc (5) trong chuỗi backend Zalo người dùng giao 21/11/2026 ("Làm tiếp" là lệnh chạy).

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#565, merge `4aca2e1` |
| Spec | [`zalo-thu-chi-real-time`](../../specs/zalo-thu-chi-real-time.md), mục B3 và "Khuôn đã code ở PR-3" |
| Migration | `2026-11-21-v7-cash-report-review.sql` (sha256 `83facd98…`): thêm bảng `cash_report_review` và 4 hàm. Chỉ THÊM, ngoài đường tiền: không đổi bảng tiền, view nợ, phân bổ, khóa tháng, `customer.version`, dữ liệu hay quyền cũ |
| Checker | `v7_post_deploy_check.sql` (sha256 `b18fe909…`): thêm `record_cash_review`, `get_cash_reviews` vào danh sách được phép của app, `get_cash_reviews` vào reader |
| Ghi tiền | Không ghi, không đổi |

## Kiểm trước

- `npm run check` xanh, `check-secrets` sạch.
- Harness PostgreSQL ở máy xanh: `test_pg_v7_backend.py`, `--migration-test`, `test_pg_v7_grants.py`, `v7_schema_snapshot.py --check`. Ca mới là `ZALO-THU-CHI.03`.
- CI của PR: 18/18 check xanh, gồm harness PostgreSQL.
- Review độc lập (subagent) bắt một lỗi chặn: gửi lại cùng `request_id` mà khác số vẫn trả "đã ghi". Kèm năm điểm nên sửa (thứ tự áp xác nhận và gộp ảnh, tin nhiều ảnh, danh mục xe đọc lỗi, khoản đã loại vẫn bị đếm, trần `before`). Thêm một lỗi tự tìm khi viết việc (6): ảnh bị loại làm trang Thu chi lỗi. Cả bảy đã sửa trong PR, mỗi lỗi có test.

## Bản sao thử (lượt cuối, bản migration sau review)

- Dump `webdebit_v7` (`-Fc`, 1.012 mục) kèm sha256; restore vào DB thử, thu hồi CONNECT của PUBLIC, cấp CONNECT như DB thật.
- Migration **hai lượt** (`psql -X -v ON_ERROR_STOP=1`): 160 ms rồi 114 ms; lượt hai chỉ báo "đã có, bỏ qua".
- Trước = sau: dấu vân tay tổng từng khách, 246 khách, 12.382 event, `customer.version` của mọi sổ, số dòng mọi bảng cũ. Bảng mới 0 dòng. `v7_post_deploy_check.sql` **9/9 OK**.
- Quyền:
  - app gọi được `record_cash_review`, `get_cash_reviews`;
  - reader chỉ gọi được `get_cash_reviews`;
  - PUBLIC không gọi được hàm ghi;
  - không role nào gọi được hàm phụ hay chạm thẳng bảng.
- Gọi thử dưới `v7_app` trong một transaction rồi ROLLBACK:
  - đọc rỗng trả `{"reviews": {}}`;
  - ghi một xác nhận thành công;
  - ghi lặp cùng `request_id` trả `replayed`;
  - đọc lại thấy `confirm`.

  Dấu vân tay không đổi, bảng còn 0 dòng. Đã xóa DB thử.

## Cửa sổ dừng ghi (16:47:36–16:47:48 UTC)

- Migration và checker lấy từ commit merge `4aca2e1` trùng bản đã thử (so sha256).
- Chờ lượt timer 15 phút (:45) xong. Chỉ còn API chạy; không phiên nào khác trong DB.
- Dừng `v7-ledger-api.service`, đo trước, dump lúc dừng (1.012 mục) kèm sha256.
- Áp migration một transaction: 125 ms.
- Trước = sau: dấu vân tay tổng từng khách, 246 khách, 12.382 event, version sổ, số dòng mọi bảng cũ.
- Checker 9/9 OK, không lỗi. Bật lại API: `active`. API gián đoạn 12 giây.

## Đổi release

- `Deploy hao` của commit merge dừng ở cổng SQL, đúng thiết kế.
- Chạy tay `git archive 4aca2e1 … | webdebit-release.sh deploy 4aca2e1…` dưới user `webdebit-deploy`, cùng gói workflow vẫn gửi: `.release-sha` = `4aca2e1`, trước đó là `4068903`.
- Script cảnh báo không dọn hết vài release cũ có từ trước (file của user khác), như các đợt trước.
- Sau đổi release:
  - unit `active`, `/healthz` loopback 200;
  - checker chạy từ file trong release 9/9 OK;
  - dưới `v7_app`, `get_cash_reviews('{"message_ids":[]}')` trả `{"reviews": {}}`;
  - journal API từ lúc áp không có dòng lỗi; bảng mới 0 dòng.

## Bằng chứng

Thư mục `backup-20261121-cash-review` trong `/srv/v7` trên `hao`, ngoài Git, quyền 700, chủ `postgres`. Gồm dump trước và dump lúc dừng kèm sha256, bản migration và checker đã chạy.

## Rollback

- DB: dưới `sokhach_owner`, `DROP TABLE sokhach.cash_report_review` và `DROP FUNCTION` các hàm `record_cash_review`, `get_cash_reviews`, `_cash_review_state`, `_cash_review_json`. Không gì tham chiếu tới. Hoặc restore dump lúc dừng.
- App: `webdebit-release.sh deploy 4068903a94fd691df00f3d46f560070a9f61a7df`. Release cũ không gọi bảng hay hàm mới.

## CÒN MỞ

- Nút xác nhận, sửa số, gắn đối tượng, loại trên trang Thu chi (PR giao diện). Lúc này route chỉ gọi được bằng API, chưa ai bấm, nên bảng còn trống.
- Người dùng tự đi Luồng 3 trên bản thử sau khi có giao diện.
