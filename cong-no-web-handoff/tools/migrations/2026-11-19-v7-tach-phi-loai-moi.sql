-- TACH-PHI-TIEU-DE-01 (bổ sung 19/11/2026): hai loại phụ phí cho cột tab khách có tên rõ mà danh mục chưa có loại.
-- Cân hàng: cột `过磅`; Local charge: cột `LOCAL CHARGE 本地费用`. Không phải cột mặc định (default_position NULL): sổ chỉ có
-- cột riêng khi máy tách được tiền vào loại đó. Chỉ thêm danh mục: không đổi dòng phụ phí, tiền, số dư hay version sổ.
-- Chạy lại được; tên đã có (người thêm ở Cài đặt phụ phí) thì giữ nguyên.
BEGIN;
SET LOCAL ROLE sokhach_owner;
INSERT INTO sokhach.fee_type(name,kind,sign,system_key,sort) VALUES
 ('Cân hàng','service','positive',NULL,11),('Local charge','service','positive',NULL,12)
 ON CONFLICT(name_key) DO NOTHING;
COMMIT;
