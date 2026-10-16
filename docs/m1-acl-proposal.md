# Đề xuất ACL cho M1 (đã áp dụng; SQL giữ làm hồ sơ)

Trạng thái: **ĐÃ ÁP DỤNG trên `hao` ngày 16/10/2026 trong đợt M1**. Không có tên host, role, DB hay đường dẫn thật trong tài liệu này; SQL chi tiết và output live nằm trong hồ sơ riêng ngoài Git. Các câu lệnh dưới đây giữ nguyên dạng đề xuất/rollback để đối chiếu, không phải yêu cầu chạy lại.

Placeholder: `<pilot_db>` là DB lịch sử (HistoryDB), `<viewer_role>` là role của service viewer, `<maker_role>` là role maker của fixture/ghi sổ, `<normal_login>` là login thường của người dùng.

## Vì sao cần

Viewer bản mới đọc **năm view** trong `<pilot_db>` qua `HistoryDB`:

| View | Dùng cho |
| --- | --- |
| `pilot.m1_provenance`, `pilot.m1_exception_detail`, `pilot.m1_customer_diff` | `/health`, `/exceptions`, cảnh báo cạnh số dư |
| `pilot.web_period_event`, `pilot.web_source_row` | chi tiết sự kiện và dòng nguồn ở trang khách/kỳ |

Cùng với `CONNECT` trên `<pilot_db>` và `USAGE` trên schema `pilot`.

- **Bằng chứng trước áp dụng (T07):** viewer live thiếu `SELECT` trên ba view M1 summary; login thường là thành viên role maker.
- **Kết quả sau áp dụng:** viewer đọc đủ năm view, giữ `CONNECT`/`USAGE`; login thường bị gỡ membership maker và các đường `EXECUTE` ghi. Không gọi hàm ghi. Chi tiết hash, output và giới hạn ở [verification](verification.md) và hồ sơ live ngoài Git.

## Thứ tự bắt buộc: cấp quyền đi trước deploy

1. Cấp quyền cho viewer (mục A).
2. Kiểm bằng tài khoản viewer: `m1_release.py preflight <goi> --check-db <pilot_db>` trả `acl.status = ok`. Preflight chạy thật `SELECT 1 FROM <view> LIMIT 0` trên từng view trong năm view và kiểm `USAGE`; kết nối được là bằng chứng `CONNECT` ([gói và rollback](m1-deploy-rollback.md)).
3. Chỉ sau đó mới deploy gói M1.

**Nếu deploy trước khi cấp quyền, `/health` trả 503.** Service vẫn chạy nhưng báo lỗi thành phần `history_exception_summary`, `history_customer_reconciliation` và `history_provenance`. Đây là cảnh báo thiết kế trước áp dụng; lần M1 đã cấp ACL trước khi cài runtime.

## A. Cấp quyền đọc cho viewer (đề xuất)

Chạy trong `<pilot_db>` bằng role sở hữu schema `pilot`. Chỉ năm view, không cấp trên bảng gốc (`pilot.raw_row`, `pilot.source_exception`, `pilot.capture`):

```sql
-- SQL mẫu; không chạy lại chỉ từ tài liệu này. Placeholder, không phải tên thật.
BEGIN;
GRANT CONNECT ON DATABASE <pilot_db> TO <viewer_role>;
GRANT USAGE ON SCHEMA pilot TO <viewer_role>;
GRANT SELECT ON pilot.m1_provenance, pilot.m1_exception_detail, pilot.m1_customer_diff,
    pilot.web_period_event, pilot.web_source_row TO <viewer_role>;
COMMIT;
```

Kiểm trước và sau, chỉ đọc (chạy bằng role quản trị):

```sql
SELECT has_database_privilege('<viewer_role>', '<pilot_db>', 'CONNECT') AS can_connect,
       has_schema_privilege('<viewer_role>', 'pilot', 'USAGE') AS can_use_schema;

SELECT v, has_table_privilege('<viewer_role>', v, 'SELECT') AS can_select
FROM (VALUES ('pilot.m1_provenance'), ('pilot.m1_exception_detail'), ('pilot.m1_customer_diff'),
             ('pilot.web_period_event'), ('pilot.web_source_row')) t(v);
```

Sau: mọi giá trị `true`. Cờ catalog chưa đủ làm bằng chứng cuối: dùng thêm preflight bằng chính role viewer để chạy `SELECT` thật. Role viewer vẫn phải chỉ đọc (`default_transaction_read_only = on`); đừng cấp thêm quyền ghi.

Rollback của bước này (chỉ khi chủ quyết định): `REVOKE SELECT ON ... FROM <viewer_role>;` trên cùng các view. Không thu hồi `CONNECT`/`USAGE` nếu role viewer đang dùng chúng cho việc khác. Rollback mã viewer không cần thu hồi quyền.

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
-- SQL rollback mẫu; chỉ chạy theo quyết định vận hành riêng.
REVOKE <maker_role> FROM <normal_login>;
```

Kiểm sau: truy vấn trên không còn dòng của `<normal_login>`; và, từ kết nối của chính login đó, `SELECT pg_has_role(current_user, '<maker_role>', 'member')` trả `false`. Phiên đang mở có thể còn giữ quyền cũ đến khi kết nối lại.

Không thu hồi của role fixture/ứng dụng hợp lệ nếu chưa có quyết định riêng. Rollback (chỉ khi chủ quyết định): `GRANT <maker_role> TO <normal_login>;`, đồng thời chấp nhận rằng login thường lại đóng được vai maker.

## Phạm vi và còn mở

- Không đề xuất tạo role, đổi mật khẩu, DDL schema hay migration. Quyền ghi tiền vẫn đóng cho tới M3/M4.
- Trước M1, SQL chỉ được kiểm trên PostgreSQL fixture; sau M1, hồ sơ live ghi viewer/preflight đạt trên `hao`. Không chạy lại lệnh trên production chỉ vì đọc tài liệu này.
- Phần đọc sổ chính (`webdebit_ledger`) của viewer đang chạy live nên không nằm trong đề xuất này.
- CÒN MỞ: nghiệm thu đầy đủ source links `8765`/`8766`; ACL/membership đã áp dụng, rollback vẫn cần quyết định vận hành riêng.
