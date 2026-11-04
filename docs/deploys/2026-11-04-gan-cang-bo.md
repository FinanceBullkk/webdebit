# Triển khai tay: gán cảng/bộ tại Việc cần làm (4/11/2026)

**ĐÃ CHẠY trên `hao` ngày 4/11/2026 (13:44 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), sửa lỗi người dùng báo trong chat: gán mặt hàng xong việc vẫn còn, bấm lại báo "Sổ đã thay đổi".

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#302 (`66ee0a0`) |
| Căn cứ | [spec Việc cần làm](../../specs/v7-viec-can-lam-bang.md); [`DASH-01`](../decisions/dash-01.md) (nhóm "Cần gán mặt hàng / cảng-bộ"); [`V7-MH`](../decisions/v7-mh.md) (cảng/bộ là phương thức riêng của sổ) |
| Migration | `2026-11-04-v7-gan-cang-bo.sql` (sha256 `d7a0d284…`): chỉ THÊM hàm `set_customer_transport`, cấp cho `sokhach_app`, thu hồi từ `PUBLIC` và `sokhach_reader`. Không đổi bảng, ràng buộc, loại event, dữ liệu hay hàm cũ. Chạy lại được. |
| Release app | `023c51b` → `66ee0a0` |
| Ghi tiền | Không ghi, không đổi. |

## Nguyên nhân

Lần lưu đầu đã thành công (có sự kiện `customer_attr`). Tổng quan coi Sầu riêng thiếu cảng/bộ là "Chưa phân loại"; Việc cần làm đọc đó thành "chưa có mặt hàng" mà không có chỗ nhập cảng/bộ, nên việc không bao giờ hết. Bấm lại thì `set_customer_commodity` chặn vì sổ đã có mặt hàng.

## Trước

- `hao` chạy `023c51b`. 236 khách.
- Script cửa sổ đọc `ActiveState` của bốn job (đối soát, đồng bộ Sheet, giá Sheet, PS) và dừng lại nếu còn job chạy. Kiểm lệnh sudo 6 phút gần nhất: không có lệnh của phiên khác.

## Bản sao thử

- Dump, restore vào DB thử, migration hai lượt: 94 ms và 100 ms, mỗi lượt 1 `COMMIT`, catalog `0915425d…` ổn định giữa hai lượt.
- Dấu vân tay (tổng từng khách, số khách, event, phiếu, phân bổ, dòng sổ gốc, chuyến) không đổi. Checker 9/9 OK.
- `v7_app` gọi được hàm, `sokhach_reader` không.
- Gọi thật bằng role app trên một sổ Sầu riêng thiếu cảng/bộ: lưu đúng, version +1, số dư không đổi; gọi lần hai để ghi đè bị `STALE_LEDGER`.
- Đã xóa DB thử.
- Harness `--migration-test` đỏ, nhưng `main` trước PR cũng đỏ cùng lỗi: chuỗi của chế độ này đã cũ và CI không chạy. Các ca so catalog đang dùng (`CSM.03`, `BANG-GIA`) có migration mới và xanh.

## Cửa sổ dừng ghi (13:43:57–13:44:01 giờ VN)

- Mã băm migration và checker lấy từ commit merge.
- Dừng `v7-ledger-api.service`, không còn kết nối, ghi dấu vân tay, dump kèm hash, đọc lại dump (633 mục).
- Áp migration với `ON_ERROR_STOP`: 120 ms, 1 `COMMIT`. Catalog trùng bản thử.
- Dấu vân tay không đổi trong cửa sổ. Checker 9/9 OK.
- Bật lại API: `active`, `/healthz` 200. API gián đoạn 4 giây.

## Đổi release

`git archive 66ee0a0 … | webdebit-release.sh deploy 66ee0a0…` dưới user `webdebit-deploy`. `.release-sha` = `66ee0a0`, `/healthz` 200, không có file do root sở hữu, migration trong release trùng hash bản đã chạy, journal API không có lỗi.

## Sau

**Màn thật (chỉ đọc, không bấm ghi):** hai sổ từng báo "mặt hàng" giờ hiện `cảng/bộ`; dòng Cộng ghi "2 cảng/bộ"; mở dòng có ô Cảng/Bộ, không còn ô chọn mặt hàng.

**Bằng chứng:** thư mục `backup-20261104-gan-cang-bo` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700). Gồm dump trước và dump lúc dừng kèm sha256, bản sao các file SQL kèm sha256, script cửa sổ, dấu vân tay, log áp thử và áp thật, log checker.

## Rollback

- App: `webdebit-release.sh deploy 023c51ba56823d1ffce60b6c629e8f85814ae91d`. Release cũ không gọi hàm mới, chạy được với DB mới.
- DB: `DROP FUNCTION sokhach.set_customer_transport(bigint,bigint,text,text)` dưới `sokhach_owner`, gỡ hàm khỏi checker. Cảng/bộ đã gán giữ trong Lịch sử.

## CÒN MỞ

- Chưa ai bấm thử Lưu cảng/bộ trên bản thật: người dùng chọn cảng/bộ cho từng sổ. Mới có test trình duyệt, harness và lần gọi thử trên bản sao.
- Ô chọn mặt hàng chỉ có năm loại; web chưa có lệnh đổi mặt hàng đã gán.
