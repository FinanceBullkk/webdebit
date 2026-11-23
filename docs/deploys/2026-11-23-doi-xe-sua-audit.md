# Đội xe: sửa lỗi audit 23/11 lên hao (23/11/2026)

**ĐÃ CHẠY trên `hao` lúc 10:28 UTC (17:28 giờ VN)**, sau khi merge. Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [runbook](../v7-deploy-runbook.md). Việc do phiên "Kiểm toàn bộ website" giao (sửa các lỗi Đội xe của audit 23/11; DX-01 có hạn trước 01/12/2026).

| Mục | Kết quả |
| --- | --- |
| PR / release | FinanceBullkk/webdebit#609, merge `53c5870b`; release tay `53c5870b` (trước đó `9602b881`) |
| CI | 22/22 check của #609 xanh, gồm harness PostgreSQL mới `test_pg_doixe_audit.py` |
| Migration | `2026-11-23-v7-doi-xe-sua-audit.sql`, SHA-256 bắt đầu `61ef5e0f9839945b` (trùng bản trên `main` và bản đã thử) |
| Ghi tiền | Không đổi dữ liệu. Chỉ `CREATE OR REPLACE` 10 hàm `doixe` (thêm phép so "số đang thấy", cảnh báo container lặp, xác nhận áp giá ngược) và thêm hàm phụ `_cont_lap` (không cấp cho ai). Không đổi bảng, chỉ mục, quyền, `sokhach` |

## Thử trên bản sao

- Backup toàn phần `webdebit_v7`, khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC.
- Migration hai lượt (125 ms, 115 ms); lượt hai chạy lại được.
- Dấu vân tiền trùng trước/sau (14 dòng: sổ `sokhach`, chặng, dòng phí, số dư, ứng, đợt hoàn, bảng kê, giá, tuyến, tên gốc, Lịch sử, lệnh).
- 85 định nghĩa hàm `doixe` ngoài danh sách thay và quyền của mọi hàm trùng trước/sau. App gọi đúng 30 hàm như trước, không gọi được `_cont_lap`; PUBLIC không gọi được hàm nào. `v7_post_deploy_check.sql` 9/9 OK.
- Đọc dưới `v7_app`: `get_bang_ke` tháng này 49 → 53 ms, tháng trước 172 → 184 ms (chậm thêm khoảng 5% vì tính cờ container lặp từng dòng); `get_chang_tai_chinh` tháng 10 khoảng 0,31 s, như trước. Đã xóa DB thử.

## DB thật

- Không kết nối nào khác đang chạy vào `webdebit_v7`; máy đối soát giờ không chạy lúc áp. Không cần cửa sổ dừng ghi.
- Backup lần nữa ngay trước khi áp (1028 mục).
- Áp với `ON_ERROR_STOP`: 141 ms.
- Dấu vân tiền trùng, 85 hàm khác và quyền trùng, `v7_post_deploy_check.sql` 9/9 OK, app không gọi được `_cont_lap`.
- Bảng kê đang gom: tháng này 8/13 dòng, tháng trước 8/206 dòng có cờ container lặp. Chỉ là cảnh báo; một phần có thể là container dùng lại hợp lệ, người nhập xem ở mục "Trước khi gửi".

## Release

- `Deploy hao` của commit merge không tự triển khai được vì diff có `tools/migrations/` (cổng SQL), đúng thiết kế.
- Release tay `53c5870b` bằng đúng gói và script của `Deploy hao` (`git archive … | webdebit-release.sh deploy`, dưới user `webdebit-deploy`): unit `active`, `/healthz` 200, release có đúng file mới (`docNgayApGia`, hàng chờ `xep`, mã lỗi `SO_DU_DOI`). Journal API sau release không có dòng lỗi.
- Script cảnh báo không dọn hết vài release cũ (file của user khác), như các đợt trước.
- Từ lúc merge tới lúc áp (vài phút), release cũ vẫn chạy với hàm cũ; trường mới không bắt buộc ở SQL nên không lệnh nào gãy.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261123-doixe-audit/` trên `hao` (thư mục 700): `v7-truoc-thu.dump`, `v7-truoc-ap.dump`, dấu vân tiền và định nghĩa hàm trước/sau, kịch bản `thu.sh`, `ap.sh`, `fp.sql`, `ham.sql`, `do.sql`.

## Rollback

Code: `webdebit-release.sh deploy 9602b8811e3a8736aaa3963d07ea637b3039f03f`. Release cũ gửi lệnh không có trường mới, hàm mới vẫn nhận. Muốn gỡ hẳn hàm: chạy lại phần định nghĩa của 10 hàm từ các migration trước (`luu_chang` ở `2026-11-18-v7-doi-xe-phieu-chi.sql`, `xoa_chang` ở `2026-11-19-v7-doi-xe-dieu-do.sql`, `ghi_ung`/`ghi_hoan` ở `2026-11-18-v7-doi-xe.sql`, còn lại ở `2026-11-18-v7-doi-xe-thu.sql`), rồi `DROP FUNCTION doixe._cont_lap(doixe.chang);`. Hoặc khôi phục `v7-truoc-ap.dump`.

## Còn mở

- DX-05 (khóa tháng cho ứng, hoàn, hủy): chờ người dùng chọn chặn (`THANG_KHOA`) hay cho ghi nhưng gắn cờ "ghi sau khóa".
- Chưa người dùng nào đi lại các luồng mới trên màn thật (đổi giá, ghi ứng/tiền về trùng, ngưng/dùng lại tuyến).
