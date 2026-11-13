-- HIEU-NANG-01 (13/11/2026): dấu dữ liệu cho bộ nhớ đọc của API. Chỉ thêm hàm get_read_stamp; không đổi bảng, hàm có sẵn,
-- quyền khác hay dữ liệu. Chạy sau 2026-11-13-v7-cot-phu-phi-mac-dinh.sql; chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;
-- HIEU-NANG-01: dấu của toàn bộ dữ liệu sokhach để API giữ kết quả đọc nặng (get_ledger, Tổng quan) tới khi có lệnh ghi.
-- stamp = md5 của (bảng, số dòng, tổng xmin) mọi bảng trong schema, lấy danh sách bảng lúc gọi: INSERT/UPDATE/DELETE đã commit
-- ở bất kỳ bảng nào đều đổi dấu (UPDATE tạo bản dòng với xmin mới, DELETE đổi số dòng); đọc và khóa dòng không đổi.
-- Không dựa vào customer.version vì vài lệnh dùng chung (loại phí, tạo sổ, Zalo) không tăng version.
-- Cộng thêm dòng catalog của hàm, view và bảng trong schema: migration thay thân get_ledger hay v_outstanding_month
-- (CREATE OR REPLACE) không đổi dòng dữ liệu nào nhưng đổi kết quả, nên cũng phải đổi dấu.
-- as_of là ngày giờ VN: kết quả các hàm được giữ phụ thuộc ngày/tháng hiện tại.
CREATE OR REPLACE FUNCTION sokhach.get_read_stamp() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_sql text; v_stamp text;
BEGIN
  PERFORM sokhach._actor();
  SELECT 'SELECT md5(string_agg(t||'':''||n||'':''||s,'','' ORDER BY t)) FROM ('
         ||string_agg(format('SELECT %L AS t,count(*) AS n,coalesce(sum(xmin::text::bigint),0) AS s FROM sokhach.%I',
                             c.relname,c.relname),' UNION ALL ' ORDER BY c.relname)||') z'
    INTO v_sql FROM pg_class c WHERE c.relnamespace='sokhach'::regnamespace AND c.relkind='r';
  EXECUTE v_sql INTO v_stamp;
  SELECT md5(v_stamp
    ||'|'||(SELECT count(*)||':'||coalesce(sum(p.xmin::text::bigint),0) FROM pg_proc p WHERE p.pronamespace='sokhach'::regnamespace)
    ||'|'||(SELECT count(*)||':'||coalesce(sum(r.xmin::text::bigint),0) FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
            WHERE c.relnamespace='sokhach'::regnamespace)
    ||'|'||(SELECT count(*)||':'||coalesce(sum(c.xmin::text::bigint),0) FROM pg_class c WHERE c.relnamespace='sokhach'::regnamespace))
    INTO v_stamp;
  RETURN jsonb_build_object('as_of',(now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date::text,'stamp',v_stamp);
END $$;

REVOKE ALL ON FUNCTION sokhach.get_read_stamp() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_read_stamp() TO sokhach_app, sokhach_reader;
RESET ROLE;
COMMIT;
