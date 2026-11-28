# SPEC — Web công nợ phải thu HTH

Spec từng thay đổi nằm ở `specs/`; file này chỉ giữ yêu cầu cấp dự án. Cập nhật 28/11/2026 theo
[`WEB-CHINH-01`](docs/decisions/web-chinh-01.md), [`CLAUDE-ALL-01`](docs/decisions/claude-all-01.md) và
[`DEPLOY-CLAUDE-01`](docs/decisions/deploy-claude-01.md); bản 21/10/2026 xem lịch sử Git.

## Yêu cầu
1. Web là sổ công nợ phải thu chính thức từ 25/11/2026. Từ 1/12/2026 mọi đầu vào của sổ nợ nhập trên web: khách mới, chuyến bộ
   chọn sổ, giá, phụ phí, phiếu thu. Không gõ Google Sheet sổ nợ nữa ([`WEB-CHINH-01`](docs/decisions/web-chinh-01.md)). File
   nguồn chuyến (booking) vẫn là đầu vào chuyến ([`NGUON-CHUYEN-01`](docs/decisions/nguon-chuyen-01.md)).
2. Tính đúng nợ theo `docs/business-rules.md`. Dữ liệu khách, chuyến, thu, kỳ, tháng nhất quán với nhau. Mọi thao tác tiền ghi
   người làm và giá trị trước → sau.
3. Người ít rành công nghệ dùng được trên laptop 1280×720.

Người dùng đã chốt thêm các mảng chạy trên cùng web, ngoài sổ nợ:
- Đội xe: [`CHI-PHI-XE-01`](docs/decisions/chi-phi-xe-01.md), [`DOI-XE-THU-01`](docs/decisions/doi-xe-thu-01.md),
  [`DOI-XE-DIEU-DO-01`](docs/decisions/doi-xe-dieu-do-01.md).
- Zalo và thu chi: [`ZALO-GROUP-01`](docs/decisions/zalo-group-01.md), [`ZALO-AGENT-01`](docs/decisions/zalo-agent-01.md),
  [`ZALO-THU-CHI-01`](docs/decisions/zalo-thu-chi-01.md).
- Nhật ký công việc: [`NHAT-KY-01`](docs/decisions/nhat-ky-01.md).
- Sổ tiền: [`SO-TIEN-01`](docs/decisions/so-tien-01.md), đang làm, chưa chạy trên `hao`.

## Ngoài phạm vi
- Duyệt hai người: đã bỏ theo [`V6-DB`](docs/decisions/v6-db.md).
- Claude ghi, nạp hay sửa dữ liệu nghiệp vụ của sổ tiền (schema `tien`), theo [`SO-TIEN-01`](docs/decisions/so-tien-01.md) mục (5).
- Mọi quyết định chưa có trong `docs/decisions.md`. Điều còn CÒN MỞ không thành chính sách chỉ vì đã có fixture, UI hay schema.

## Nghiệm thu
- `npm run check` xanh, không có SKIP ngoài ý muốn. `node scripts/check-secrets.js` sạch: không secrets hay dữ liệu thật trong Git.
- Mỗi quy tắc tiền có test. Đổi SQL, migration hay đường ghi tiền thì harness PostgreSQL xanh.
- Thay đổi chạm DB trên `hao` đi theo runbook: backup trước, kiểm sau triển khai, đối soát tổng khách, nhật ký trong
  `docs/deploys/` ([`DEPLOY-CLAUDE-01`](docs/decisions/deploy-claude-01.md)).
- Luồng frontend mới: spec có luồng người dùng và đối chiếu dữ liệu, kiểm trình duyệt, người dùng tự đi hết luồng trên môi
  trường thử ([quy trình frontend](docs/development.md#quy-trình-frontend)).
- Từ 1/12/2026 sổ web được kiểm theo booking mỗi giờ ([`DU-CHUYEN-01`](docs/decisions/du-chuyen-01.md)), lưới an toàn
  ([`LUOI-AN-TOAN-01`](docs/decisions/luoi-an-toan-01.md)) và đường lui xuất cả sổ ([`XUAT-SO-01`](docs/decisions/xuat-so-01.md)),
  không theo "khớp Sheet". Đây là ĐỀ XUẤT ở nguyên tắc 5 của `WEB-CHINH-01`; riêng ngày thôi gõ Sheet là ĐÃ CHỐT.
