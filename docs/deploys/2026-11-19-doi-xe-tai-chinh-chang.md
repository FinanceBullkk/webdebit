# Đội xe: hàm đọc thu, chi, lãi gộp của chặng lên `hao` (19/11/2026)

**ĐÃ CHẠY trên `hao` lúc 13:14 giờ VN**, sau khi merge. Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), [spec mục Chặng](../../specs/doi-xe-chang-01.md) (PR 2, gói B2 của [`DOI-XE-CAU-TRUC-01`](../decisions/doi-xe-cau-truc-01.md)), mô hình [`DOI-XE-MO-HINH-01`](../decisions/doi-xe-mo-hinh-01.md) và [runbook](../v7-deploy-runbook.md).

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Phiên điều phối Đội xe giao phiên giữ runbook `doixe` triển khai tay theo `DEPLOY-CLAUDE-01` (phiên viết PR không đụng `hao`) |
| PR / release | #509, merge `a022ac2`; release tay `a022ac2` |
| CI | 18/18 check của #509 xanh trên head `aecac09` |
| Migration | `2026-11-19-v7-doi-xe-tai-chinh-chang.sql`, SHA-256 `46f64010cc1a2c188c6a57208d8c0392b571354eb8db5fc50c7db54f858269ef` (trùng bản trên `main` và bản đã thử) |
| Ghi tiền | Không. Chỉ hai hàm đọc `STABLE`: `doixe._tai_chinh_chang` (không cấp ai) và `doixe.get_chang_tai_chinh` (cấp app). Không bảng, không ràng buộc, không đổi hàm cũ, không đổi `sokhach` |

## Thử trên bản sao (13:09)

- Backup toàn phần `webdebit_v7` (1008 mục), khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC.
- Migration hai lượt (102 ms, 104 ms); lượt hai chạy lại được.
- Dấu vân tiền trùng trước/sau (như các đợt đội xe trước: sổ `sokhach`, chặng, dòng phí, số dư, Lịch sử `doixe`).
- md5 định nghĩa và quyền của 83 hàm `doixe` có sẵn trùng trước/sau: migration không đổi hàm cũ.
- `v7_app` gọi được `get_chang_tai_chinh`, không gọi được `_tai_chinh_chang`; PUBLIC không gọi được hàm nào. `v7_post_deploy_check.sql` 9/9 OK.
- `get_chang_tai_chinh` dưới `v7_app` (giao dịch chỉ đọc): tháng 10 có 206 chặng, 203 chặng có lãi gộp, 1,07 s phần DB; tháng 11 tới hôm nay 13 chặng, 63 ms. Đã xóa DB thử.

## DB thật (13:14)

- Không kết nối nào khác vào `webdebit_v7`; máy đối soát giờ không chạy lúc áp.
- Backup lần nữa ngay trước khi áp (1008 mục).
- Áp với `ON_ERROR_STOP`: 122 ms. Không cần cửa sổ dừng ghi.
- Dấu vân tiền trùng, 83 hàm cũ trùng, `v7_post_deploy_check.sql` 9/9 OK, quyền như bản thử.
- `get_chang_tai_chinh` tháng 10: 206 chặng, 203 có lãi gộp, 0,99 s phần DB.

## Release

- Release tay `a022ac2` bằng đúng gói (`git archive`) và script của `Deploy hao` (trước đó `7ef1354`): `/healthz` 200, unit active, `.release-sha` = `a022ac2`. `Deploy hao` của commit này dừng ở gate vì diff có `tools/migrations/`; đó là chủ ý.
- Từ lúc merge tới lúc áp (vài chục giây), `GET /chang` trên release cũ chưa gọi hàm mới; không màn nào gọi route này lúc đó.

## Số đo `GET /api/v7/doixe/chang` cả route (qua Tailscale, sau release)

| Truy vấn | Thời gian | Kích thước |
| --- | --- | --- |
| `thang=2026-10-01` (ba lần) | 1,10 s; 0,93 s; 0,97 s | 276 KB |
| tháng hiện tại (không tham số) | 0,38 s | 34 KB |

Spec của #509 đo trên DB giả 0,3–0,65 s; trên dữ liệu thật một tháng đầy khoảng 1 s, phần lớn ở `get_chang_tai_chinh` (tính phần thu từng chặng qua `_tinh_chang`). Không chặn; ghi để màn mục Chặng (gói F2) tính tới.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261119-tai-chinh-chang/` trên `hao` (thư mục 700): `v7-truoc-thu.dump`, `v7-truoc-ap.dump`, dấu vân tiền và md5 hàm trước/sau, kịch bản `thu.sh`, `ap.sh`, `do.sql`.

## Rollback

Code: revert #509 (đường đọc Chặng bỏ lượt gọi hàm mới). DB không cần gỡ: hàm đọc mới không ai gọi thì vô hại. Muốn gỡ hẳn: `DROP FUNCTION doixe.get_chang_tai_chinh(jsonb), doixe._tai_chinh_chang(bigint);`.

## Còn mở

- Đọc một tháng đầy khoảng 1 s; nếu màn mục Chặng thấy chậm thì đo lại theo số chặng và cân nhắc gom `_tinh_chang` theo tháng.
