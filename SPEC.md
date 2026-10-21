# SPEC — Web công nợ phải thu HTH

Spec từng thay đổi nằm ở `specs/`; file này chỉ giữ yêu cầu cấp dự án.

## Yêu cầu
1. Thay Google Sheet bằng web: nhập chuyến theo lô, ghi thu, sửa/điều chỉnh, cấn trừ, xem sổ từng khách và tổng.
2. Tính đúng nợ theo `docs/business-rules.md`; dữ liệu khách, chuyến, thu, kỳ, tháng nhất quán với nhau.
3. Người ít rành công nghệ dùng được trên laptop 1280×720.

## Ngoài phạm vi
Ghi vào Sheet/DB thật, deploy lên `hao`, duyệt hai người (đã bỏ), mọi quyết định chưa có trong `docs/decisions.md`.

## Nghiệm thu
- `npm run check` xanh, không có SKIP ngoài ý muốn.
- Mỗi quy tắc tiền có test; số liệu mới đối soát với sổ gốc theo tổng từng khách.
- Luồng frontend mới có mockup đã duyệt và kiểm trình duyệt.
- Chạy song song tối thiểu một lần cuối tháng khớp thì mới chuyển hẳn (SONG-SONG-01).
- Không có secrets hoặc dữ liệu thật trong Git (`node scripts/check-secrets.js` sạch).
