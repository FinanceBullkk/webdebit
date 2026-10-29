# V7 — Công nợ theo tháng (ma trận khách × tháng) — hồ sơ thiết kế ĐỀ XUẤT

Trạng thái: **DUYỆT CÓ ĐIỀU KIỂN hướng A** (người dùng, 24/10/2026). Đã duyệt: hướng A, quy ước hiển thị ("Chưa phân loại" cuối, ô âm có dấu không tô heat, hai phạm vi tổng). API tổng hợp đã thêm vào SQL/API cục bộ và đã kiểm chứng harness + route test. Chưa duyệt: triển khai Phase 5 frontend.

> Nguồn duyệt: phản hồi người dùng 24/10/2026 — "Approve Design Direction A · Approve quy ước hiển thị · Conditional Backend API · Pending Phase 5".
Theo yêu cầu redesign "Customer Receivables Dashboard" v0.3 ngày 24/10/2026 của người dùng.
Mục đích chính: **quan sát** công nợ còn lại theo khách × tháng (BR-01), không phải quản lý đòi nợ (BR-08).

## 1. Audit hiện trạng

### 1.1 Trang đang chạy thật (`preview/dashboard-v7.html` + `dashboard-v7.js`)

6 thẻ tổng hợp từ `GET /api/v7/dashboard` (receivable/credit, aging 4 bucket, by_commodity, top_debtors, todo, today).
**Không có** ma trận khách × tháng, không chọn năm, không nhóm mặt hàng theo hàng, không drill-down theo tháng.
→ BR-02/03/06/07 hiện chưa tồn tại trong bản chạy thật; mọi ma trận mới nằm trong mockup chưa duyệt.

### 1.2 Dòng mockup đã thử (chưa vào code thật)

| Bản | Kết luận |
| --- | --- |
| Heat map bucket (4 cột nhóm tuổi) | Nhóm bucket méo độ rộng, không khớp mô hình tâm trí |
| Heat map theo tháng cụ thể (02–10/26 cuộn) | Gần mô hình tâm trí nhất; thiếu: năm lịch, chọn năm, tổng nhóm, kiểm soát màu/đỏ, số trong ô |
| Card ưu tiên đòi nợ | Trang dài, che khuất nợ theo tháng — bị loại làm dashboard chính (khớp kết luận của yêu cầu) |
| Compact table + expand | Dày nhưng nợ theo tháng khó đọc — bị loại làm dashboard chính |

### 1.3 Nguồn số liệu (truy vết code)

- **Ô tháng (BR-04)** = `sokhach.v_outstanding_month` (view, `tools/v7_backend_functions.sql:12`, schema `specs/v7-backend/schema-draft.sql:747`): `customer_id × debt_month → outstanding_vnd` = số dư đầu + charge hợp lệ + điều chỉnh − phân bổ phiếu thu chưa hủy; chỉ khách/cutover `active`. **Frontend không tự tính lại** (ràng buộc #6).
- **Chuỗi tháng & get_ledger**: `v_month_chain` (cộng dồn cho get_ledger); `get_ledger` trả mỗi khách `months:[{month, prior_months_vnd, charges_vnd, received_vnd, end_of_month_vnd, outstanding_vnd}]` + `total_outstanding_vnd` (bằng tổng các tháng — test `test-so-khach-v7-api.js:149`).
- **Thu phân bổ theo tháng**: `received_vnd` theo tháng đã có trong get_ledger; **không có phân bổ thu theo container** — khớp cảnh báo BR-06, không bịa.
- **Tổng hợp dashboard**: `get_dashboard` (dòng 1663–1707 trong v7_backend_functions.sql) tổng từ v_outstanding_month; aging theo bucket; **không có chiều năm**.
- **Năm/tháng**: `debt_month` là YYYY-MM tuyệt đối; không có cơ chế chuyển kết dư sang năm mới (phân bổ nợ cũ trước chạy trên tập tháng thật) → BR-02 khớp hành vi sẵn có; chọn năm = lọc theo năm của `debt_month`.
- **Hai phạm vi (BR-07)**: Năm chọn = Σ outstanding_vnd các tháng thuộc năm đó; mọi năm = `total_outstanding_vnd`. Số dư đầu cũng mang tháng thật (vd 2025-12) nên thuộc cột 2025, không trôi vào 2026.

### 1.4 Giới hạn UI vs nghiệp vụ

- UI: chưa có ma trận/năm/nhóm/drill — là thiếu hụt của frontend.
- Nghiệp vụ/data: đã đủ ở tầng DB cho ô tháng và drill-down **từng khách** (get_ledger). Còn thiếu **một hàm tổng hợp ma trận toàn khách** (250 khách × 12 tháng) — gọi get_ledger 250 lần là không chấp nhận → cần API mới (xem Vấn đề mở).

## 2. Kiến trúc thông tin

- **Chính (cấp 1)**: ma trận Khách × 12 tháng của năm đang chọn — mỗi ô = số tiền còn lại của đúng tháng đó; **số hiển thị ngay trong ô**, màu chỉ là lớp quét phụ (không truyền thông tin chỉ bằng màu).
- **Phụ (cấp 2)**: nhóm mặt hàng (header + tổng nhóm), 2 cột tổng ghim phải (Năm đang chọn | Mọi năm), tổng toàn bảng.
- **Chi tiết (cấp 3, theo yêu cầu)**: bấm ô → panel khách-tháng: container/chuyến, charge gốc, phụ phí, phát sinh, thu đã phân bổ vào tháng, còn lại; ghi rõ "thu phân bổ theo tháng".
- **Tương tác**: đổi năm (◀ 2026 ▶, không đổi số liệu — chỉ đổi khung nhìn); tìm khách; lọc mặt hàng; gập/mở nhóm; hover sáng hàng.
- **Trạng thái rỗng**: tháng không phát sinh hoặc đã trả hết → ô trống như nhau (BR-05).

## 3. Phương án A — Heat map tinh chỉnh (KHUYÊN DÙNG)

```
┌─ ◀ 2026 ▶   Tìm khách…   Mặt hàng: Tất cả ▾                    Đơn vị: đồng ──────────────┐
│ Dư nợ còn lại của năm 2026: 1.815.000.000 đ   Tổng dư nợ còn lại MỌI NĂM (đến 24/10/2026):    │
│                                                 2.480.000.000 đ (gồm 665.000.000 đ các năm cũ)│
├──────────────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬─────────┬────────┤
│ Khách        │ T1   │ T2   │ T3   │ T4   │ T5   │ T6   │ T7   │ T8   │ T9   │ T10  │ T11  │ T12  │ 2026▲  │ Mọi năm│
├──────────────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴─────────┴────────┤
│ ▾ SẦU RIÊNG (6 khách)                                                          tổng nhóm: 1.280.000.000 │ 1.280.000.000 │
│ Khách A      │      │      │180.0 │      │120.0 │ 80.0 │      │      │      │      │      │      │ 380.0M │ 380.0M │
│ Khách B      │      │      │      │      │130.0 │      │      │      │      │190.0 │      │      │ 320.0M │ 320.0M │
├──────────────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴─────────┴────────┤
│ ▸ THANH LONG (2) …                                                                          │    415M │    415M │
│ ▸ MÍT (3) …                                                                                 │    405M │    405M │
│ ▸ RAU CỦ (1) …                                                                              │    250M │    250M │
│ ▸ CHƯA PHÂN LOẠI (1)                                                                        │    130M │    130M │
├──────────────────────────────────────────────────────────────────────────────────────┬─────────┬────────┤
│ TỔNG 2026                                                                               │1.815.0M │2.480.0M │
└────────────────────────────────────────────────────────────────────────────────────────┴─────────┴────────┘
  Ô: số đầy đủ separators + nền navy đậm theo % của max toàn năm (lớp phụ); ô 0/trống = trắng.
  Cột "Khách" ghim trái; 2 cột tổng ghim phải; header ghim trên. Bấm ô → drawer chi tiết tháng.
```

Chi tiết ô (cell treatment): chữ 12px tabular phải-căn; nền `#1e4e8c` alpha 0.10→0.85 theo value/max(năm); ô âm (khách trả trước) hiển thị số âm mực đậm kèm dấu, không tô nền (chờ chốt — Vấn đề mở #2). Bấm ô bất kỳ → drawer BR-06 (từ get_ledger của khách, lọc tháng).

**Ưu**: đúng mô hình tâm trí; quét chéo khách×tháng trực tiếp; 12 cột cố định dễ đối chiếu; nhóm + tổng gom đúng cấp; mật độ 250 khách tốt (hàng ~34–40px vì chỉ 1 dòng số); số hiện sẵn không cần hover.
**Nhược**: bảng rộng (12+cột) cần cuộn ngang ở <1280 — đã có ghim 3 phía; đổi năm là chuyển khung nhìn, người dùng phải hiểu "mọi năm" luôn hiển thị cạnh (đã xử bằng 2 cột tổng + dòng đầu).

## 4. Phương án B — Ma trận + panel chi tiết cố định (master–detail)

```
┌─ ◀ 2026 ▶  Tìm…  Mặt hàng ▾ ────────────────────────────────────────────────────────────────┐
│ ┌─────────────────────────────────────── ma trận (≈62%) ───────┬───── panel chi tiết (≈38%) ─┐│
│ │ Khách      │ T1 │ T2 │ … │ T10│ T11│ T12│ 2026 │ Mọi năm │   │ Khách A · 05/2026          ││
│ │ ▾ SẦU RIÊNG                                                            │   │ ─ còn lại: 120.000.000 đ  ││
│ │ Khách A    │  · │  · │ … │  · │  · │  · │380.0M│ 380.0M │   │ Chuyến (container):        ││
│ │ Khách B    │  · │  · │ … │190 │  · │  · │320.0M│ 320.0M │   │  MAUU…301 · 58.000.000     ││
│ │ …           │    │    │   │    │    │    │       │        │   │  MAUU…302 · 62.000.000    ││
│ │ (ô chỉ số, màu nhạt hơn A)                                        │   │ Phát sinh: 120.000.000   ││
│ │                                                                  │   │ Thu đã phân bổ tháng: 0    ││
│ │                                                                  │   │ Còn lại: 120.000.000      ││
│ └──────────────────────────────────────────────────────────────────┴────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Ưu**: drill-down không cần lớp phủ — bấm ô là panel cập nhật ngay, giữ ngữ cảnh liên tục; phù hợp nếu thao tác tra chi tiết rất dày.
**Nhược**: ma trận bị ép hẹp còn ~62% bề rộng → 12 tháng + 2 tổng rất chật ở 1280; scannability giảm đúng nơi cần mật độ; panel trống rỗng khi chưa chọn (trạng thái rỗng phải xử lý); di chuột nhiều hơn giữa hai vùng.

## 5. So sánh & khuyến nghị

| Tiêu chí (từ yêu cầu) | A — heat map tinh chỉnh | B — master–detail |
| --- | --- | --- |
| Quét khách × tháng (UX-1/2) | ●●● | ●●○ |
| Số chính xác không mơ hồ (UX-3) | ●●● (số trong ô) | ●●● |
| So sánh ít di mắt (UX-4) | ●●● (đủ rộng) | ●○○ (hẹp) |
| Drill-down (UX-5) | ●●○ (drawer 1 bấm) | ●●● (panel liền) |
| 250 khách (UX-6) | ●●● | ●●○ |
| Vận hành tài chính chuyên nghiệp | ●●● | ●●○ |
| Rủi ro bố cục ở 1280 | thấp | cao |

**Khuyến nghị A**: mục đích chính là quan sát (BR-01) — ưu tiên quét ma trận full-width; drill-down là hành động phụ, drawer đã là pattern quen của app (history-panel). B chỉ thắng khi tra chi tiết chiếm >50% thời gian — không đúng định vị.

## 6. Vấn đề mở (chỉ blocker thật)

1. **API ma trận toàn khách**: cần hàm SQL mới (VD `sokhach.get_receivables_matrix(year)` trả rows: customer_id, name, commodity, transport_mode, 12 ô `outstanding_vnd`, `total_year_vnd`, `total_all_vnd` + danh sách năm có dữ liệu). Là thay đổi API — cần duyệt riêng (đề xuất gộp vào spec DASH-02).
2. **Ô âm (tháng khách trả trước)**: v_outstanding_month có thể âm theo tháng với khách trả thừa — hiển thị nguyên giá trị âm (không tô heat) đúng ràng buộc "không làm tròn/không đổi logic"; cần người dùng xác nhận cách trình bày.
3. **Nhóm "khác"**: khách `commodity NULL` → nhóm "Chưa phân loại" (đứng cuối) — xác nhận tên hiển thị.
4. **Nguồn danh sách năm**: đề xuất API trả min–max `debt_month` (năm 2025+ nếu có số dư đầu 2025) — xác nhận.

## 7. Kế hoạch implement (sau khi duyệt — Phase 5)

1. Backend: hàm `get_receivables_matrix` + route `GET /api/v7/receivables/matrix?year=` (xem hợp đồng §8). Spec riêng, review riêng.
2. Frontend: trang mới `cong-no-theo-thang.html` trong `preview/` theo visual proof §10, thuần CSS theo `preview/mockups/DESIGN.md`, drawer tái dùng get_ledger cho BR-06 (không API mới).
3. Test: Playwright — theo §9 + fixture 250 khách.
4. Rủi ro: hiệu năng payload 250×12 (~100KB); cuộn ngang 12 cột ở màn hẹp (ghim 3 phía đã chứng minh §10); không đụng logic tiền.
5. Hoàn tác: revert PR trang + hàm; không đụng dữ liệu.

## 8. Deliverable 1 — Hợp đồng API `get_receivables_matrix` (v0.1, chờ review backend)

> **Cập nhật 24/10 (SQL Review xong, 21/21 pass)**: bản SQL draft cuối cùng + bằng chứng đối chiếu/quyền/benchmark chạy thật trong container PostgreSQL 18.6 dùng một lần (`tools/test_pg_v7_matrix.py`, image pin như CI, network none, xả container sau chạy; **không đụng DB vận hành, chưa merge**). Kết quả: `specs/v7-cong-no-theo-thang-matrix-review.json`.

### 8.1. SQL đã kiểm chứng (nguyên văn, chạy thật 21/21 — `tools/test_pg_v7_matrix.py`)

```sql
CREATE FUNCTION sokhach.get_receivables_matrix(p_year int) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
  IF p_year IS NULL OR p_year < 2000 OR p_year > extract(year FROM d)::int + 1 THEN
    RAISE EXCEPTION 'INVALID_YEAR'; END IF;
  PERFORM sokhach._actor();
  RETURN (WITH base AS (
    SELECT c.id, c.name, c.commodity_id, c.transport_mode,
           coalesce(sum(v.outstanding_vnd),0)::bigint AS total_all,
           coalesce(sum(v.outstanding_vnd) FILTER (WHERE extract(year FROM v.debt_month)=p_year),0)::bigint AS total_year,
           min(v.debt_month) FILTER (WHERE v.outstanding_vnd>0) AS oldest
      FROM sokhach.customer c
      JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
      JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
      LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id
     WHERE NOT c.archived
     GROUP BY c.id, c.name, c.commodity_id, c.transport_mode
    HAVING coalesce(bool_or(v.outstanding_vnd <> 0), false)),
  cells AS (
    SELECT b.id, g.mm, coalesce(sum(v.outstanding_vnd),0)::bigint AS val
      FROM base b CROSS JOIN generate_series(1,12) AS g(mm)
      LEFT JOIN sokhach.v_outstanding_month v
        ON v.customer_id=b.id AND extract(year FROM v.debt_month)=p_year AND extract(month FROM v.debt_month)=g.mm
     GROUP BY b.id, g.mm),
  cust AS (
    SELECT jsonb_build_object('customer_id',b.id,'name',b.name,'commodity',m.name,
      'transport_mode',b.transport_mode,
      'months',(SELECT jsonb_object_agg(mm::text, val::text) FROM cells WHERE cells.id=b.id),
      'total_year_vnd',b.total_year::text,'total_all_vnd',b.total_all::text,
      'oldest_open_month',b.oldest::text) o
      FROM base b LEFT JOIN sokhach.commodity m ON m.id=b.commodity_id
     ORDER BY b.total_all DESC, b.name COLLATE "C", b.id)
  SELECT jsonb_build_object('as_of',d::text,'year',p_year,
    'years_available',(SELECT coalesce(jsonb_agg(DISTINCT y ORDER BY y),'[]'::jsonb) FROM
      (SELECT extract(year FROM debt_month)::int y FROM sokhach.v_outstanding_month
       UNION SELECT extract(year FROM d)::int) yy),
    'customers',(SELECT coalesce(jsonb_agg(o),'[]'::jsonb) FROM cust),
    'grand_total_year_vnd',(SELECT coalesce(sum(total_year),0)::bigint::text FROM base),
    'grand_total_all_vnd',(SELECT coalesce(sum(total_all),0)::bigint::text FROM base)));
END $$;

REVOKE ALL ON FUNCTION sokhach.get_receivables_matrix(int) FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_matrix(int) TO sokhach_app, sokhach_reader;
```

**Hai quy tắc chốt theo review 24/10 (P0):**
1. **Chọn khách**: `HAVING bool_or(outstanding_vnd <> 0)` — khách xuất hiện khi **có bất kỳ tháng nào còn số dư khác 0**, kể cả khi tổng ròng mọi năm = 0 (tháng +X/−X bù trừ). Khớp luật ledger: tháng âm giữ nguyên sign trong view (case 7.15a), thu mới bỏ qua tháng âm chỉ trừ tháng dương (V7-BE(6)) — không bù trừ liên kỳ ngoài quy tắc; tổng chỉ là tổng cộng các tháng. Test T13 chứng minh khách +100.000/−100.000 vẫn hiện đủ 2 tháng với `total_all_vnd = "0"`.
2. **Năm**: `years_available` là **danh sách gợi ý** (năm có dữ liệu ∪ năm hiện tại) cho UI; **mọi năm trong [2000, năm hiện tại + 1] đều truy vấn được** kể cả chưa phát sinh (giữ khách nợ năm cũ + 12 ô "0" — test T14 với năm 2027 ngoài danh sách); chỉ năm sai định dạng/phạm vi bị từ chối (`INVALID_YEAR`, 1999 và 2028 — test T12/T14b). Route Python validate cùng khoảng này, map `INVALID_YEAR` → 422.

**Ghi chú hiệu năng API**: 46,7ms/37,4ms là **SQL execution**; wall 572ms gồm chi phí `docker exec` + khởi tạo psql — không đại diện HTTP. Khi implement route, đo độ trễ HTTP thật (cold + warm) và lấy đó làm số duyệt, không thay bằng thời gian SQL.

### 8.2. Bằng chứng quyền (chạy thật)

- P1: `sokhach_reader` + `sokhach_app` có EXECUTE; ACL không cấp PUBLIC (aclexplode grantee=0 rỗng). ✓
- P2: hàm là SECURITY DEFINER, `search_path` khóa `pg_catalog, sokhach, pg_temp` (chống search_path hijack — cùng pattern mọi hàm hiện có). ✓
- P3: `sokhach_reader` SELECT trực tiếp `v_outstanding_month` **bị từ chối** — dữ liệu chỉ thoát qua hàm tổng hợp, không mở chiều nào mới. ✓
- P4: reader gọi hàm được qua SET ROLE (role NOLOGIN — đúng chính sách app server giữ mật khẩu). ✓
- Phân tích: schema V7 không dùng RLS (kiểm soát bằng grant; đã ghi chú xác nhận lại với DBA khi merge). Hàm chỉ đọc các view/bảng mà `get_ledger`/`get_dashboard` đã exposé cùng phạm vi — không mở rộng quyền truy cập dữ liệu.

### 8.3. Bằng chứng đối chiếu (chạy thật, fixture 4 sách + biên — 21/21)

T1 `total_all` từng khách = `get_ledger.total_outstanding_vnd` (4/4 sách, gồm sách tổng ròng 0) ✓ · T2 ô tháng = view đúng tháng (tháng thiếu "0") ✓ · T3 `total_year` = Σ 12 ô (mọi khách) ✓ · T4 khách chỉ nợ 2025: năm 2027 vẫn hiện, 12 ô "0", total_all giữ ✓ · T5 đổi năm không đổi grand_all ✓ · T6 tháng âm giữ dấu "-20000" ✓ · T7 khách chưa phân loại (commodity null) vẫn trong ma trận ✓ · T8 số dư đầu nằm đúng tháng gốc 2025-12 ✓ · T9 archived + NO_BASELINE bị loại ✓ · T10 grand_year(2026)+grand_year(2025)=grand_all (510000+500000=1010000) ✓ · T11 years_available=[2025,2026] (data ∪ năm hiện tại 2026) ✓ · T12 năm 1999 → INVALID_YEAR ✓ · **T13 khách tổng ròng 0 (+100.000/−100.000) vẫn hiện đủ 2 tháng, total_all "0"** ✓ · **T14 năm 2027 ngoài years_available vẫn truy vấn được, giữ khách nợ cũ** ✓ · **T14b năm 2028 (ngoài phạm vi) bị từ chối** ✓.

### 8.4. Benchmark thật 250 khách

Seed 250 khách active × ~9 tháng có số dư (2.250 dòng view): **payload 94KB (< 200KB), execution 37–47ms qua 2 lần chạy (< 500ms)**, tổng từng khách benchmark khớp view 0 lệch (B2). Container xả sạch sau đo.

**HTTP đo qua PostgreSQL disposable (26/10/2026):** API process gọi route thật, route gọi `docker exec psql` vào PostgreSQL 18.6 container dùng một lần. Cold request **379.88ms**, HTTP 200, payload 415 bytes; 10 warm requests trung bình **294.92ms** (min 274.04ms, max 309.66ms), tất cả HTTP 200. Không đụng DB vận hành; chưa phải benchmark `hao`.

**Route**: `GET /api/v7/receivables/matrix?year=YYYY` (không query khác; year bắt buộc, hợp lệ trong [2000, năm hiện tại + 1]).

**Phạm vi khách** (trả lời P0 "khách nợ năm cũ khi chuyển năm"): trả về **mọi khách có ít nhất một tháng `outstanding_vnd ≠ 0`** đến thời điểm truy vấn (từ `v_outstanding_month`, chỉ khách/cutover active) — không lọc theo năm đang chọn. Khách không phát sinh gì trong năm chọn vẫn nằm trong response với 12 ô rỗng/0 và `total_year_vnd = "0"`.

**Response** (tiền = chuỗi số nguyên VND, tháng key `"1".."12"`):

```json
{
  "as_of": "2026-10-24",
  "year": 2026,
  "years_available": [2025, 2026, 2027],
  "customers": [{
    "customer_id": 1, "name": "…", "commodity": "Sầu riêng" | null, "transport_mode": "CẢNG" | null,
    "months": {"1": "0", "2": "0", "3": "180000000", "…": "…", "12": "0"},
    "total_year_vnd": "380000000",
    "total_all_vnd":  "380000000",
    "oldest_open_month": "2026-03-01"
  }],
  "grand_total_year_vnd": "1815000000",
  "grand_total_all_vnd":  "2480000000"
}
```

**Bất biến**:
- Ô tháng = `v_outstanding_month.outstanding_vnd` (còn lại của đúng tháng) — **không phải** `end_of_month_vnd` lũy kế.
- `total_year_vnd` = Σ 12 ô của năm chọn; `total_all_vnd` = Σ `v_outstanding_month` mọi tháng của khách (bằng `get_ledger.total_outstanding_vnd`).
- Ô âm giữ nguyên dấu theo nguồn; **không** tự động gán nghĩa "trả trước" và không bù trừ khác quy tắc hiện hành khi tính tổng.
- Đổi `year` không làm thay đổi bất kỳ giá trị nào ngoài phạm vi năm (không phân bổ lại, không chuyển kỳ).

**Phân quyền**: theo pattern sẵn có của `get_dashboard`/`list_customers` — hàm đọc `SECURITY DEFINER`, REVOKE SELECT trực tiếp bảng/view khỏi role app/reader (schema đã cấm grant bảng toàn khách). **Lưu ý reviewer**: SECURITY DEFINER không tự động an toàn — hàm mới chỉ được đọc đúng các view/hàm tổng hợp mà app đã được phép thấy qua các route hiện có, không thêm chiều dữ liệu khách mới; sẽ review cùng DBA trên PR. Hiện schema V7 **không dùng RLS** (kiểm soát bằng grant), nên không có nguy cơ bypass RLS; ghi nhận để xác nhận lại khi review.

**Test cases (bắt buộc trước khi merge)**: (1) fixture 250 khách × 12 tháng — payload < ~200KB, thời gian hàm < 500ms trên harness; (2) `total_year + các năm khác = total_all` cho từng khách và tổng toàn bảng; (3) khách chỉ nợ năm cũ: 12 ô = "0", `total_all` ≠ 0; (4) tháng âm truyền nguyên dấu; (5) `year` ngoài `years_available` nhưng trong khoảng hợp lệ → 200; năm ngoài khoảng → 422; (6) so khớp chéo 10 khách ngẫu nhiên với `get_ledger` (Σ months theo năm và total_outstanding_vnd).

## 9. Deliverable 2 — Đối chiếu số liệu (quy tắc + bằng chứng fixture)

Quy tắc đối chiếu (sẽ thành test tự động khi nối API thật):
1. **Ô ↔ sổ**: với khách K, tháng M: `matrix[K].months[M]` = `get_ledger(K).months[M'].outstanding_vnd` (cùng debt_month).
2. **Cột năm ↔ hàng tháng**: Σ 12 ô của K trong năm Y = `matrix[K].total_year_vnd`; Σ tất cả các năm + tháng ngoài năm = `total_all_vnd` = `get_ledger(K).total_outstanding_vnd`.
3. **Nhóm**: tổng nhóm = Σ thành viên (mỗi khách đúng 1 nhóm theo `commodity` duy nhất — không đếm đôi).
4. **Toàn bảng**: Σ `total_all_vnd` = `grand_total_all_vnd` = tổng `v_outstanding_month` (khớp tổng sổ nguồn).
5. **Drill-down BR-06**: các trường lấy từ `get_ledger`: chuyến (container, ngày, đơn giá `unit_price_vnd`, phụ phí `other_fee_vnd` — **đã có sẵn**, xác nhận từ fixture `so-khach-v7-fixture.js` và test `test-so-khach-v7-api.js:149`); thu phân bổ theo tháng = `received_vnd`; còn lại = `outstanding_vnd`. Tháng **số dư đầu** (opening) không có chi tiết theo container — hiển thị là "khoản mục lịch sử", không bịa phân bổ.

Bằng chứng hiện có (fixture, chưa phải DB): bản visual proof §10 có dải đối chiếu tự tính — Σ ô 2026 = 1.815.000.000 đ ✓ khớp cột năm; Σ mọi năm = 2.480.000.000 đ ✓ khớp tổng khách (test `check-visual-proof.js` xác nhận 2 phép ✓, không LỆCH). **Số 1.815 tỷ / 665 triệu nợ cũ là fixture minh họa có chủ đích tình huống nợ năm cũ — không phải số đã đối chiếu DB thật** (trả lời P1 "đối chiếu số liệu trong wireframe").

## 10. Deliverable 3 — Visual Proof (đã chạy, chờ người dùng duyệt mắt)

File: `preview/mockups/cong-no-theo-thang/index.html` (serve `http://127.0.0.1:8123/cong-no-theo-thang/index.html`). Screenshot: `test-results/proof-1280.png`, `proof-1440.png`, `proof-250.png`.

Số đo thực tế (Playwright):
- **1280×800**: bảng 1512px trong khung 1218px → **cuộn ngang trong khung bảng** (trang không tràn); ô tháng **92px**, cột Mọi-năm 117px, số 12.5px tabular — đọc rõ "180.000.000".
- **1440×900**: bảng 1512px / khung 1378px → cuộn rất ít; mọi cột gần như vừa.
- **Ghim 3 phía**: Khách trái + Năm/Mọi-năm phải + header trên; nền đặc + z-index đúng — cuộn giữa bảng không lộ ô bên dưới (test tự động).
- **P0 năm 2027** (không phát sinh): 12 khách nợ cũ vẫn hiện, cột năm = 0 đ, Mọi-năm = 2.480.000.000 đ; năm 2025 tổng = 665.000.000 đ.
- **Ô âm**: "−20.000.000" không tô heat; drawer ghi rõ "không tự gán nghĩa, chờ xác nhận backend".
- **250 khách**: sinh 238 khách giả + 12 thật = 250 hàng, render 41–55ms, sticky/ghim ổn, trang không tràn.

### 10.1. Vòng 2 — sửa theo góp ý duyệt 24/10 (đã xong, test `check-visual-proof2.js` 15/15)

1. **P0 tổng nhóm bị che**: bỏ dòng tổng chạy dài sau cột sticky; tổng nhóm giờ nằm **đúng vị trí 2 cột tổng ghim phải** (ô riêng `gcol-year`/`gcol-all`, sticky, nền đặc) — test đo tọa độ khi cuộn giữa bảng: thẳng hàng cột Năm/Mọi-năm ±2px, luôn thấy được ở 1280 và 1440.
2. **P0 benchmark lệch**: dải "mọi năm" chuyển thành số **động** (trước hardcode 2,48 tỷ); benchmark 250 khách nay nhất quán — năm 15.945 tỷ ≤ mọi năm 16.610 tỷ = tổng cột; nút đổi tên "Benchmark 250 khách (số giả, riêng biệt)", dải đối chiếu tự chuyển **CHẾ ĐỘ BENCHMARK** ghi rõ không dùng đối chiếu tài chính; thoát benchmark về đúng 2,48 tỷ.
3. **Nhãn KPI**: "Còn nợ phát sinh 2026" → **"Dư nợ còn lại của năm 2026"**; kèm "Tổng dư nợ còn lại mọi năm".


## Phạm vi agent và bằng chứng triển khai

- **ĐÃ CHỐT:** hướng A, `HAVING bool_or(outstanding_vnd <> 0)`, giữ dấu tháng âm, `years_available` chỉ gợi ý; mọi năm hợp lệ trong `[2000, năm hiện tại + 1]` truy vấn được.
- **ĐÃ TRIỂN KHAI (PR #93, commit `0fd32fa`):** `cong-no-web-handoff/tools/v7_backend_functions.sql` và migration thêm `sokhach.get_receivables_matrix`; `web/v7_ledger_api.py` thêm `GET /api/v7/receivables/matrix?year=` và lỗi `INVALID_YEAR`; `tests/test_v7_ledger_api.py` thêm kiểm tra route. Không đổi view, schema hay logic phân bổ.
- **ĐÃ KIỂM CHỨNG:** `PYTHONIOENCODING=utf-8 py -3.13 cong-no-web-handoff/tools/test_pg_v7_matrix.py` — **21/21 PASS**, benchmark payload 94KB, SQL 54.893ms, container dùng một lần và đã xả; route test 31 test (1 skip có điều kiện). HTTP PostgreSQL disposable đã đo ở §8.4; benchmark `hao` còn mở.
- **CI trên commit `0fd32fa`:** 11/11 job PASS, gồm `npm run check` trên Ubuntu/Windows và harness PostgreSQL. Bằng chứng 21/21 cùng phép đo HTTP đã đăng trong PR #93.
- **Owner DBA sign-off:** người dùng xác nhận cả hai điểm §8.2 trong task; đã ghi nhận tại PR #93, comment `6404075124`. Chưa chạy DDL/triển khai trên `hao`.
- **ĐÃ MERGE:** backend PR #93 vào `main` tại `ed18f09` (26/10/2026, giờ Việt Nam). Gate Phase 5 frontend đã mở theo xác nhận của người dùng.

### Phase 5 — nối dashboard thật (đang triển khai)

- **ĐÃ TRIỂN KHAI (worktree `codex/phase5-receivables-matrix`):** thêm trang `/cong-no-theo-thang.html`, CSS/JS riêng; trang gọi `/api/v7/receivables/matrix?year=YYYY`, lọc khách/mặt hàng, đổi năm, hiển thị heatmap 12 tháng + 2 cột tổng, và drawer gọi `/api/v7/ledger?customer=...`.
- **Ranh giới:** không fixture, không benchmark giả trong trang thật; tiền định dạng từ chuỗi VND bằng `BigInt`; ô âm giữ dấu; khách tổng ròng 0 vẫn hiện; thu hiển thị theo tháng, không theo container.
- **ĐÃ KIỂM CHỨNG:** `node --test cong-no-web-handoff/preview/test-v7-receivables-matrix-browser.js` **2/2 PASS**; `npm run test:browser` **34/34 PASS**; `npm run check` **7/7 PASS**; screenshot 1280×800 và 390×844 đã kiểm tra.
- **CÒN MỞ:** review diff/PR Phase 5, chạy CI đầy đủ, kiểm tra tích hợp PostgreSQL disposable; chưa deploy `hao`.

### Ngăn kéo chi tiết tháng — audit UI 29/10/2026

- **ĐÃ CHỐT (người dùng chọn sửa nhóm P1 + P2 của audit trong chat, 29/10/2026):** chuyến xếp theo ngày, ngày `dd/mm`, số không kèm "đ" trong bảng, ẩn cột Phụ phí khi tháng không có phụ phí, dòng tổng chuyến ghim đáy; phần đầu (khách, "Mở sổ khách ›", đổi tháng ‹ ›, phép tính Phát sinh − Thu đã trừ = Còn lại) đứng yên, chỉ bảng chuyến cuộn. Ngăn kéo không có lớp phủ: màn ≥ 900px bảng thu hẹp, cuộn ngang tới ô đang mở và tô viền ô đó; bấm ô khác thì ngăn kéo đổi theo.
- Tháng có số dư đầu sổ gốc không ghi dấu −/= vì phát sinh/đã thu lấy theo Sheet; chuyến chờ kiểm hoặc chưa có giá hiện nhãn và không vào dòng tổng (như dòng Tổng tháng của Sổ khách).
- **ĐÃ CODE (29/10/2026):** ngăn kéo có bảng "Phiếu thu trong tháng" (ngày, phiếu/tham chiếu/cấn trừ từ, số tiền, kỳ đang được trừ hoặc trả trước, dòng tổng); tổng phiếu khác đã thu thì ghi phần chênh là số Sheet hoặc cấn trừ đi. Dữ liệu từ trường `receipts` của `get_receivables_detail` (migration `2026-10-29-v7-matrix-drawer-receipts.sql`).
