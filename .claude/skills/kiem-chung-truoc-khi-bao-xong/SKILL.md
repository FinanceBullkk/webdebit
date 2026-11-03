---
name: kiem-chung-truoc-khi-bao-xong
description: Có bằng chứng mới chạy rồi mới báo xong, đã sửa, đã xanh hay đã triển khai trong repo webdebit. Dùng ngay trước khi nói việc đã xong, trước commit, mở/merge PR, báo Deploy hao, hoặc khi nhận báo cáo "thành công" của subagent hay phiên khác.
---

**Mục đích:** mọi câu báo trạng thái dựa trên output vừa chạy trong lượt này, không dựa vào lần chạy trước hay cảm giác "chắc ổn".

**Phạm vi file:** chỉ chạy lệnh kiểm và đọc; không sửa.

**Các bước (cổng trước mỗi câu báo trạng thái)**
1. Xác định lệnh nào chứng minh câu định nói (bảng dưới).
2. Chạy đủ lệnh đó, mới, trong lượt này.
3. Đọc hết output: mã thoát, số test hỏng, các bước SKIP.
4. Output khớp thì báo kèm bằng chứng; không khớp thì báo trạng thái thật kèm bằng chứng.

| Câu định nói | Bằng chứng cần | Chưa đủ |
| --- | --- | --- |
| Test/check xanh | `npm run check` thoát 0, ghi rõ bước SKIP | Lần chạy trước, `npm run lint`, chạy một file test |
| Sạch secrets | `node scripts/check-secrets.js` thoát 0 | Đã đọc lướt diff |
| Đã sửa lỗi | Chạy lại đúng triệu chứng ban đầu: hết; test hồi quy đỏ khi bỏ bản sửa, xanh khi có | Code đã đổi, "chắc đúng" |
| SQL/migration đúng | Harness `tools/test_pg_*.py` ở máy khi sửa SQL, schema, đường ghi tiền | Chỉ unittest |
| Giao diện đúng | Đã render và xem ở 1280×720 (hoặc màn thấy 1280×560) | Test DOM xanh |
| PR merge được | Mọi check bắt buộc trên GitHub xanh (`gh pr checks`) | CI local xanh |
| Đã triển khai `hao` | Job `Deploy hao` xanh; với migration: `v7_post_deploy_check.sql` và đối soát tổng khách | Đã merge |
| Subagent/phiên khác xong | Tự xem diff, nhánh hoặc file nó để lại | Báo cáo "thành công" của nó |
| Đạt yêu cầu | Đọc lại spec/tiêu chí, tick từng mục | Test xanh |

**Dấu hiệu phải dừng:** dùng chữ "chắc", "có lẽ", "hình như"; nói "xong rồi" trước khi chạy kiểm; sắp commit/push/PR mà chưa kiểm; tin báo cáo của agent khác.

**Hoàn thành khi:** câu báo trạng thái gắn với lệnh đã chạy và kết quả thật, dùng đúng nhãn `AGENTS.md`: ĐỀ XUẤT, ĐÃ CHỐT, ĐÃ TRIỂN KHAI (môi trường), ĐÃ KIỂM CHỨNG (bằng chứng), CÒN MỞ.

**Điều cấm:** báo xanh khi có bước đỏ hay SKIP mà không nói; gọi một phần kiểm là kiểm đủ; báo ĐÃ TRIỂN KHAI chỉ vì đã merge.

Phỏng theo skill `verification-before-completion` của [obra/superpowers](https://github.com/obra/superpowers) (MIT, © Jesse Vincent).
