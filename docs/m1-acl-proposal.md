# Đề xuất ACL cho M1 (chưa chạy)

Trạng thái: **ĐỀ XUẤT, chưa chạy ở bất kỳ môi trường nào**. Không có tên host, role, DB hay đường dẫn thật trong tài liệu này; SQL chi tiết kèm tên thật nằm trong hồ sơ riêng ngoài Git. Mọi câu lệnh dưới đây cần người dùng có quyền chạy hoặc duyệt từng bước, trên bản sao trước nếu có.

Placeholder: `<pilot_db>` là DB lịch sử (HistoryDB), `<viewer_role>` là role của service viewer, `<maker_role>` là role maker của fixture/ghi sổ, `<normal_login>` là login thường của người dùng.

## Vì sao cần

- **Thiếu SELECT cho viewer (nghiệm thu M1).** Viewer mới đọc `pilot.m1_provenance`, `pilot.m1_exception_detail` và `pilot.m1_customer_diff` qua `HistoryDB`. Viewer live chưa có quyền này. Thiếu quyền thì `exception_summary` và `customer_reconciliations` lỗi, `/health` trả 503 và `/exceptions` hiện "Chưa kiểm được ngoại lệ nguồn".
- **Login thường đang là thành viên role maker (phát hiện M1-3 của T07).** Điều này cho phép một login thường đóng vai maker, trái với D01 (tách người nhập và người duyệt) và với việc định danh phải đến từ session phía server. Cần thu hồi membership đó trước khi có đường ghi tiền.

## Thứ tự bắt buộc: cấp quyền đi trước deploy

1. Cấp `SELECT` cho viewer.
2. Kiểm bằng tài khoản viewer: `m1_release.py preflight <goi> --check-db <pilot_db>` trả `acl.status = ok` ([gói và rollback](m1-deploy-rollback.md)).
3. Chỉ sau đó mới deploy gói M1.

**Nếu deploy trước khi cấp quyền, `/health` trả 503.** Service vẫn chạy nhưng báo lỗi thành phần `history_exception_summary`, `history_customer_reconciliation` và `history_provenance`; các trang đọc số dư không bị chặn. Cấp quyền sau đó tự khỏi, không cần khởi động lại.

## A. Cấp SELECT cho viewer (đề xuất)

Chạy trong `<pilot_db>` bằng role sở hữu schema `pilot`. Chỉ ba view, không cấp trên bảng gốc (`pilot.raw_row`, `pilot.source_exception`, `pilot.capture`):

```sql
-- ĐỀ XUẤT, chưa chạy. Placeholder, không phải tên thật.
BEGIN;
GRANT SELECT ON pilot.m1_provenance, pilot.m1_exception_detail, pilot.m1_customer_diff
    TO <viewer_role>;
COMMIT;
```

Kiểm trước và sau, chỉ đọc:

```sql
SELECT v, has_table_privilege('<viewer_role>', v, 'SELECT') AS can_select
FROM (VALUES ('pilot.m1_provenance'), ('pilot.m1_exception_detail'),
             ('pilot.m1_customer_diff')) t(v);
```

Trước: ít nhất một dòng `false`. Sau: cả ba `true`. Role viewer vẫn phải chỉ đọc (`default_transaction_read_only = on`); đừng cấp thêm quyền ghi.

Rollback của bước này (chỉ khi chủ quyết định): `REVOKE SELECT ON ... FROM <viewer_role>;` trên cùng ba view. Rollback mã viewer không cần thu hồi quyền này.

## B. Thu hồi membership maker của login thường (đề xuất)

Chạy bằng role có quyền quản trị membership của `<maker_role>`. Kiểm trước, chỉ đọc, để biết cấu hình hiện tại và ai thật sự cần giữ quyền:

```sql
SELECT r.rolname AS member, g.rolname AS granted_role, m.admin_option
FROM pg_auth_members m
JOIN pg_roles r ON r.oid = m.member
JOIN pg_roles g ON g.oid = m.roleid
WHERE g.rolname = '<maker_role>';
```

Nếu `<normal_login>` có mặt trong kết quả:

```sql
-- ĐỀ XUẤT, chưa chạy.
REVOKE <maker_role> FROM <normal_login>;
```

Kiểm sau: truy vấn trên không còn dòng của `<normal_login>`; và, từ kết nối của chính login đó, `SELECT pg_has_role(current_user, '<maker_role>', 'member')` trả `false`. Phiên đang mở có thể còn giữ quyền cũ đến khi kết nối lại.

Không thu hồi của role fixture/ứng dụng hợp lệ nếu chưa có quyết định riêng. Rollback (chỉ khi chủ quyết định): `GRANT <maker_role> TO <normal_login>;`, đồng thời chấp nhận rằng login thường lại đóng được vai maker.

## Phạm vi và còn mở

- Không đề xuất tạo role, đổi mật khẩu, DDL schema hay migration. Quyền ghi tiền vẫn đóng cho tới M3/M4.
- CHƯA KIỂM CHỨNG trên PostgreSQL nào; câu SQL ở đây dựa trên cách `HistoryDB` đọc view và trên phát hiện T07. Cần chạy thử trên bản sao và đọc lại bằng hai câu kiểm trước khi áp dụng.
- CÒN MỞ: tên role/DB thật, người chạy và thời điểm; bản ghi kết quả đặt ở hồ sơ riêng ngoài Git.
