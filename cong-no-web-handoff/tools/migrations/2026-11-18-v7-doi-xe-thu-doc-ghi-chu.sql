-- DOI-XE-THU-01 (specs/doi-xe-thu-01.md): bộ đọc ghi chú phát sinh, bản sửa sau review độc lập (18/11/2026). Áp sau
-- 2026-11-18-v7-doi-xe-thu.sql (đã chạy trên hao); chỉ thay hai hàm phụ `doixe._doc_ghi_chu`, `doixe._ps_tu_o`, không đổi bảng,
-- quyền hay dữ liệu. Chạy lại được.
-- * Đơn vị phải hợp cách tính: khoản theo ngày chỉ nhận số ngày ("Neo 12 tiếng" gắn cờ), khoản theo giờ/lần không nhận số ngày.
-- * Khoản không ghi số tiền (cố định, theo ngày, theo đơn vị) không được có số nào khác trong tên ("Xí cont 2 cont" gắn cờ, không
--   lấy 1 × mức).
-- * Số âm ("Xí cont -150k") gắn cờ, không đổi thành số dương.
-- * "1tr5" chỉ khi chữ số lẻ dính liền sau tr ("Neo 3tr 2" không thành 3tr2); phần lẻ sau dấu chấm/phẩy chỉ 1–2 chữ số
--   ("1.200tr" là 1 200 triệu hay 1,2 triệu? không đoán).
-- * Tên danh mục một chữ khớp sau khi bỏ dấu nhưng ghi khác dấu ("Cần cẩu" với "Cân") không nhận là khoản đó: thành khoản lạ.
-- * Tiền lấy từ ô ngày neo, giờ máy phát quá lớn gắn cờ thay vì lỗi tràn số.
BEGIN;
SET LOCAL ROLE sokhach_owner;

-- Đọc ghi chú phát sinh. Mỗi khoản bắt đầu bằng "_" (đầu ghi chú hoặc sau khoảng trắng), tới "_" kế tiếp; chữ trước "_" đầu
-- tiên là ghi chú thường, không đọc. Một khoản: tên rồi số tiền ở cuối: 1250k · 1tr5 · 1,5tr · 1.250.000 · 1250000đ (dấu câu,
-- ngoặc đóng sau số tiền bỏ qua). Không có số tiền thì: khoản theo ngày lấy số ngày ở cuối ("Neo 2 ngày" = mức + 1 × mức thêm),
-- khoản theo đơn vị lấy số giờ/lần ở cuối ("Nổ máy phát 3 tiếng" = 3 × mức); số không đơn vị chỉ tới 10; khoản cố định lấy mức;
-- tên khi đó không được có số nào khác. Tên khớp tên dài nhất của danh mục ở đầu khoản (phần còn lại là mô tả, được có số lượng
-- kèm đơn vị như "Neo 2 ngày 3tr", "Đóng ghép 2 kho cách 70km 3100k" khi đã ghi số tiền); không khớp mà có số tiền: khoản lạ, vẫn
-- tính (không chi hộ) và gắn cờ. Không đoán: số âm, số ở cuối thiếu đơn vị, số tiền không ở cuối, hai số tiền, số lạ trong khoản,
-- số tiền dưới 10.000, đơn vị không hợp cách tính, chưa có mức: gắn lỗi, không tính.
-- Trả mảng: {goc, ten, ma, so_tien_vnd, chi_ho, cot, la?} hoặc {goc, loi, ma?}.
CREATE OR REPLACE FUNCTION doixe._doc_ghi_chu(p_ghi_chu text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v_out jsonb := '[]'::jsonb; v_goc text; v_x text; v_ten text; v_tien numeric; v_sl integer; v_dv text; m text[];
        ps doixe.phat_sinh; v_khop text; v_con text; v_loi text; v_ma text; v_goc_dm text; v_chu text; v_chu_dm text; v_n integer := 0;
        -- Trên chữ đã chuẩn hóa (_fold): một số tiền (150K, 1TR5, 2 TRIEU, 150000D) và một số lượng có đơn vị được phép nằm trong
        -- mô tả của khoản đã ghi số tiền (2 NGAY, 3H, 2 LAN, 3 KHO, 70KM, 2 CONT).
        c_tien CONSTANT text := '\m[0-9]+ ?(K|TRIEU|TR|DONG|D|VND)([0-9]{1,3})?\M';
        c_sl CONSTANT text := '\m[0-9]{1,4} ?(NGAY|N|DEM|TIENG|GIO|H|LAN|KHO|KM|CONT|CHUYEN|DIEM)\M';
        c_dau CONSTANT text := '[' || chr(768) || '-' || chr(879) || ']';   -- dấu thanh, dấu mũ (sau NFD)
BEGIN
    IF p_ghi_chu IS NULL OR p_ghi_chu !~ '(^|\s)_' THEN RETURN v_out; END IF;
    FOR v_goc IN SELECT btrim(x) FROM regexp_split_to_table(regexp_replace(p_ghi_chu, '\s+', ' ', 'g'), '(^|\s)_') WITH ORDINALITY AS s(x, n)
                  WHERE n > 1 ORDER BY n LOOP
        IF v_goc = '' THEN CONTINUE; END IF;
        v_n := v_n + 1;
        IF v_n > 20 THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'loi', 'Quá 20 khoản trong một ghi chú');
            CONTINUE;
        END IF;
        v_tien := NULL; v_sl := NULL; v_dv := NULL; v_ten := NULL; ps := NULL; v_loi := NULL;
        -- Dấu câu, ngoặc đóng ở cuối khoản không thuộc số tiền: "150k," "(1150k)".
        v_x := regexp_replace(v_goc, '[\s.,;:!?)\]]+$', '');
        -- 1,5tr · 1.25tr: phần lẻ 1–2 chữ số.
        m := regexp_match(v_x, '^(.*?)\s*([0-9]{1,9})[.,]([0-9]{1,2})\s*(tr|triệu|trieu)$', 'i');
        IF m IS NOT NULL THEN
            v_ten := m[1]; v_tien := m[2]::numeric * 1000000 + rpad(m[3], 3, '0')::numeric * 1000;
        ELSE
            -- 2tr · 1tr5: chữ số lẻ dính liền sau tr.
            m := regexp_match(v_x, '^(.*?)\s*([0-9]{1,9})\s*(tr|triệu|trieu)([0-9]{1,3})?$', 'i');
            IF m IS NOT NULL THEN
                v_ten := m[1]; v_tien := m[2]::numeric * 1000000 + coalesce(rpad(m[4], 3, '0')::numeric * 1000, 0);
            ELSE
                m := regexp_match(v_x, '^(.*?)\s*([0-9]{1,12})\s*k$', 'i');
                IF m IS NOT NULL THEN
                    v_ten := m[1]; v_tien := m[2]::numeric * 1000;
                ELSE
                    m := regexp_match(v_x, '^(.*?)\s*([0-9]{1,3}(?:[.,][0-9]{3})+)\s*(đ|đồng|d|dong|vnd)?$', 'i');
                    IF m IS NOT NULL THEN
                        v_ten := m[1]; v_tien := regexp_replace(m[2], '[.,]', '', 'g')::numeric;
                    ELSE
                        m := regexp_match(v_x, '^(.*?)\s*([0-9]{1,15})\s*(đ|đồng|d|dong|vnd)$', 'i');
                        IF m IS NOT NULL THEN
                            v_ten := m[1]; v_tien := m[2]::numeric;
                        ELSE
                            -- Số lượng ở cuối, đứng riêng (trước nó không phải chữ số: "Kiểm hoá 1171" không thành 71 đơn vị).
                            m := regexp_match(v_x, '^(|.*[^0-9.,])\s*([0-9]{1,2})\s*(ngày|ngay|đơn vị|don vi|lần|lan|tiếng|tieng|giờ|gio|h)?$', 'i');
                            IF m IS NOT NULL THEN
                                v_ten := m[1]; v_sl := m[2]::integer; v_dv := doixe._fold(m[3]);
                            ELSE
                                v_ten := v_x;
                            END IF;
                        END IF;
                    END IF;
                END IF;
            END IF;
        END IF;
        -- Phần còn lại (tên + mô tả) đã chuẩn hóa, bỏ các số lượng kèm đơn vị: còn số tiền hay số nào khác là dấu hiệu đọc sai.
        v_con := regexp_replace(coalesce(doixe._fold(v_ten), ''), c_sl, ' ', 'g');
        v_loi := CASE
            WHEN v_x ~ '[-−–][0-9]' THEN 'Số âm: ghi số tiền dương (bớt tiền thì ghi điều chỉnh khi đối chiếu)'
            WHEN v_tien IS NULL AND v_sl IS NULL AND v_x ~ '[0-9]$' THEN 'Số ở cuối thiếu đơn vị tiền (k, tr)'
            WHEN v_tien IS NULL AND v_sl IS NULL AND v_con ~ c_tien THEN 'Số tiền ghi ở cuối khoản, ví dụ «_ Xí cont 150k»'
            -- "1.250k", "1,5k", "1 200k", "1.200tr": số dính trước số tiền, dễ đọc sai.
            WHEN v_tien IS NOT NULL AND v_ten ~ '[0-9][.,]?\s*$' THEN 'Số tiền lạ: ghi kiểu 1250k, 1tr5 hoặc 1.250.000'
            -- "Xí cont 150k, nâng hạ 50k" khi quên dấu _: không đoán khoản nào.
            WHEN v_con ~ c_tien THEN 'Một khoản có hai số tiền: tách mỗi khoản bằng dấu _'
            WHEN v_con ~ '[0-9]' THEN 'Có số lạ trong khoản: ghi kiểu «_ Xí cont 150k» hoặc «_ Neo 2 ngày»'
            -- Không ghi số tiền thì tên không được có số nào ("Xí cont 2 cont", "Neo 2 ngày 3"): không biết lấy số nào.
            WHEN v_tien IS NULL AND coalesce(doixe._fold(v_ten), '') ~ '[0-9]' THEN 'Có số lạ trong khoản: ghi kiểu «_ Xí cont 150k» hoặc «_ Neo 2 ngày»'
            WHEN v_sl IS NOT NULL AND v_dv IS NULL AND v_sl > 10 THEN 'Số ở cuối thiếu đơn vị tiền (k, tr)'
            WHEN v_tien IS NOT NULL AND v_tien < 10000 THEN 'Số tiền lạ: ghi kiểu 1250k, 1tr5 hoặc 1.250.000' END;
        IF v_loi IS NOT NULL THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'loi', v_loi);
            CONTINUE;
        END IF;
        v_ten := btrim(v_ten, ' :-–=_.,;()[]');
        v_khop := doixe._fold(v_ten);
        IF v_khop IS NOT NULL THEN
            SELECT t.ma, t.ten INTO v_ma, v_goc_dm FROM doixe.phat_sinh_ten t
             WHERE v_khop = t.ten OR v_khop LIKE t.ten || ' %' ORDER BY char_length(t.ten) DESC LIMIT 1;
            IF FOUND THEN
                SELECT * INTO ps FROM doixe.phat_sinh WHERE ma = v_ma;
                -- Tên một chữ của danh mục ("CAN" của Cân) khớp sau khi bỏ dấu, mà chữ đầu khoản có dấu khác ("Cần cẩu"): khoản khác,
                -- không nhận. Gõ không dấu ("can") vẫn nhận.
                v_chu := lower(normalize(split_part(v_ten, ' ', 1), NFC));
                v_chu_dm := lower(normalize(split_part(ps.ten, ' ', 1), NFC));
                IF v_goc_dm !~ ' ' AND v_goc_dm = doixe._fold(v_chu_dm) AND v_chu <> v_chu_dm AND normalize(v_chu, NFD) ~ c_dau THEN
                    ps := NULL;
                END IF;
            END IF;
        END IF;
        IF v_tien IS NULL AND ps.ma IS NOT NULL THEN
            -- Đơn vị phải hợp cách tính: theo ngày nhận số ngày; theo đơn vị (giờ, lần) không nhận số ngày.
            IF v_sl IS NOT NULL AND ps.cach = 'theo_ngay' AND v_dv IS NOT NULL AND v_dv <> 'NGAY' THEN
                v_loi := 'Khoản này tính theo ngày: ghi số ngày, ví dụ «_ Neo 2 ngày»';
            ELSIF v_sl IS NOT NULL AND ps.cach = 'theo_don_vi' AND v_dv = 'NGAY' THEN
                v_loi := 'Khoản này tính theo giờ hoặc lần: ghi kiểu «_ Nổ máy phát 3 tiếng»';
            ELSIF v_sl IS NOT NULL AND ps.cach = 'theo_ngay' AND v_sl >= 1 AND ps.muc_vnd IS NOT NULL AND ps.muc_them_vnd IS NOT NULL THEN
                v_tien := ps.muc_vnd + (v_sl - 1)::numeric * ps.muc_them_vnd;
            ELSIF v_sl IS NOT NULL AND ps.cach = 'theo_don_vi' AND v_sl >= 1 AND ps.muc_vnd IS NOT NULL THEN
                v_tien := v_sl::numeric * ps.muc_vnd;
            ELSIF v_sl IS NULL AND ps.cach = 'co_dinh' AND ps.muc_vnd IS NOT NULL THEN
                v_tien := ps.muc_vnd;
            END IF;
            IF v_loi IS NOT NULL THEN
                v_out := v_out || jsonb_build_object('goc', v_goc, 'ma', ps.ma, 'loi', v_loi);
                CONTINUE;
            END IF;
        END IF;
        IF v_tien IS NULL THEN
            -- Khoản lỗi vẫn ghi mã danh mục khi nhận ra tên: ô số lượng của chặng không tính thêm khoản đó lần nữa.
            v_out := v_out || jsonb_build_object('goc', v_goc, 'ma', ps.ma, 'loi',
                CASE WHEN ps.ma IS NULL AND v_sl IS NULL THEN 'Thiếu số tiền (ví dụ 200k)'
                     WHEN ps.ma IS NULL THEN 'Chưa rõ khoản và số tiền'
                     WHEN ps.cach IN ('theo_ngay', 'theo_don_vi', 'co_dinh') AND ps.muc_vnd IS NULL THEN 'Khoản này chưa có mức: ghi số tiền'
                     WHEN v_sl IS NOT NULL AND ps.cach NOT IN ('theo_ngay', 'theo_don_vi') THEN 'Số ở cuối thiếu đơn vị tiền (k, tr)'
                     ELSE 'Thiếu số tiền (ví dụ 200k)' END);
        ELSIF v_tien <= 0 OR v_tien >= 10000000000000000 THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'ma', ps.ma, 'loi', 'Số tiền không hợp lệ');
        ELSIF ps.ma IS NULL THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'ten', coalesce(nullif(v_ten, ''), 'Khoản không tên'), 'ma', NULL,
                'so_tien_vnd', v_tien::bigint::text, 'chi_ho', false, 'cot', 'ps', 'la', true);
        ELSE
            v_out := v_out || jsonb_build_object('goc', v_goc, 'ten', coalesce(nullif(v_ten, ''), ps.ten), 'ma', ps.ma, 'ten_dm', ps.ten,
                'so_tien_vnd', v_tien::bigint::text, 'chi_ho', ps.chi_ho, 'cot', ps.cot);
        END IF;
    END LOOP;
    RETURN v_out;
END $$;

-- Phát sinh lấy từ ô số lượng của chặng (phiếu chi mới): ngày neo → khoản 'neo', giờ máy phát → khoản 'no_may', tính theo cách tính
-- và mức của danh mục. Chỉ khi ghi chú chưa có khoản đó (ghi chú có thì ghi chú quyết định, không cộng hai lần). Danh mục chưa có
-- mức, là khoản nhập tay, hoặc tiền ra quá lớn: gắn lỗi, không tính. Mỗi khoản có 'o' = true (lấy từ ô).
CREATE OR REPLACE FUNCTION doixe._ps_tu_o(c doixe.chang, p_ps jsonb) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v_out jsonb := '[]'::jsonb; r record; ps doixe.phat_sinh; v_tien numeric; v_ten text;
BEGIN
    FOR r IN SELECT * FROM (VALUES ('neo', c.neo_ngay, ' ngày'), ('no_may', c.may_gio, ' giờ')) v(ma, sl, dv) LOOP
        CONTINUE WHEN r.sl IS NULL OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_ps) e WHERE e ->> 'ma' = r.ma);
        SELECT * INTO ps FROM doixe.phat_sinh WHERE ma = r.ma;
        CONTINUE WHEN NOT FOUND;
        v_ten := ps.ten || ' ' || r.sl || r.dv;
        v_tien := CASE WHEN ps.cach = 'theo_ngay' AND ps.muc_vnd IS NOT NULL AND ps.muc_them_vnd IS NOT NULL
                            THEN ps.muc_vnd + (r.sl - 1)::numeric * ps.muc_them_vnd
                       WHEN ps.cach = 'theo_don_vi' AND ps.muc_vnd IS NOT NULL THEN r.sl::numeric * ps.muc_vnd END;
        IF v_tien IS NULL OR v_tien <= 0 OR v_tien >= 10000000000000000 THEN
            v_out := v_out || jsonb_build_object('goc', v_ten, 'ma', ps.ma, 'o', true, 'loi',
                CASE WHEN v_tien IS NOT NULL THEN 'Số tiền không hợp lệ: xem lại mức ở Bảng giá hoặc số ở ô'
                     WHEN ps.cach IN ('theo_ngay', 'theo_don_vi') THEN 'Khoản này chưa có mức: ghi mức ở Bảng giá hoặc ghi số tiền vào ghi chú'
                     ELSE 'Khoản này không tính theo số lượng: ghi số tiền vào ghi chú' END);
        ELSE
            v_out := v_out || jsonb_build_object('goc', v_ten, 'ten', v_ten, 'ma', ps.ma, 'ten_dm', ps.ten, 'so_tien_vnd', v_tien::bigint::text,
                'chi_ho', ps.chi_ho, 'cot', ps.cot, 'o', true);
        END IF;
    END LOOP;
    RETURN v_out;
END $$;

REVOKE ALL ON FUNCTION doixe._doc_ghi_chu(text), doixe._ps_tu_o(doixe.chang, jsonb) FROM PUBLIC;
COMMIT;
