# V7 — Trang tổng quan "nhìn nhanh" + danh sách đòi nợ (DASH-02)

Trạng thái: **ĐỀ XUẤT** — mockup HTML đã người dùng xem và góp ý qua 24/10/2026 (dashboard-tong-quan-v3, dashboard-tong-quan-v4, danh-sach-doi-no trong `preview/mockups/`); chưa duyệt Penpot. Mở rộng [DASH-01](v7-dashboard.md) (ĐÃ CHỐT nội dung 23/10/2026), không thay thế.

## Người dùng và luồng (bước 1)

Theo DASH-01: người nhập xem cuối ngày, chủ nghiệp vụ xem cuối tuần/tháng, trang chỉ đọc. Người dùng chính 30–40+ tuổi (mockup vòng 24/10 người dùng yêu cầu: chuyên nghiệp, ít màu, không phụ thuộc chú thích).

| Trang | Lúc nào | Trả lời câu hỏi |
| --- | --- | --- |
| Nhìn nhanh (v4) | Mở web, 5 giây đầu | "Khách nợ mình bao nhiêu, đang tốt lên hay xấu đi, ai cần đòi trước?" |
| Chi tiết (v3 = DASH-01 nâng visual) | Cuối ngày/tuần | "Còn việc gì dở, hôm nay nhập/thu thế nào?" |
| Đòi nợ (heat map) | Khi ra đòi | "Khách nào nợ nhóm nào bao nhiêu?" |

Luồng giữ nguyên DASH-01: bấm khách → mở sổ khách; trang chỉ đọc. Topbar 3 mục: Nhìn nhanh · Chi tiết · Đòi nợ.

## Đầu ra

Ba trang tổng quan đọc được trên 1280×720 và 390px; mọi số tiền khớp `get_ledger`/`get_dashboard`; không thêm framework/dependency.

## Đối chiếu dữ liệu và code hiện có (bước 2)

Có sẵn từ `get_dashboard` (DASH-01): `receivable`, `credit`, `by_commodity`, `aging` (4 bucket), `top_debtors` (10 khách: tổng + tháng nợ cũ nhất), `todo`, `today`. Heat map và các chart theo tháng cần thêm:

- **Ma trận khách × bucket aging** (heat map): `get_dashboard` chỉ có tổng từng khách trong `top_debtors`. Cần bucket từng khách — tính được từ `v_outstanding_month` (đã có số dư đầu/chuyến/điều chỉnh theo tháng nợ).
- **Tổng nợ cuối từng tháng** (đường 12 tháng): chưa có — cần chuỗi theo tháng, tính từ trạng thái sổ tại cuối mỗi tháng hoặc lũy kế từ event. **Cách tính chuẩn xác cần chốt với backend** (replay theo event theo tháng, hay snapshot tháng đóng). CÒN MỞ.
- **Nợ mới vs đã thu từng tháng**: chưa có — tổng charge mới (chuyến có giá + điều chỉnh) và phiếu thu chưa hủy theo tháng ghi sổ; tính từ các bảng hiện có.
- **Cơ cấu aging theo từng tháng**: chưa có — phụ thuộc cách tính chuỗi ở trên. CÒN MỞ.
- **Trạng thái khóa tháng** (chip MỞ/KHÓA 10 tháng): chưa có API toàn khách; dữ liệu tồn tại trong sổ từng khách (`set_month_lock`).
- **"So web với Google Sheet"**: **mâu thuẫn quyết định đã chốt** — DASH-01 ghi rõ *không* đối chiếu Sheet trong web (DB không giữ Sheet; đối soát bằng `tools/v7_reconcile_sheet.py` ngoài web). Khối này trong mockup chỉ là gợi ý; nếu giữ trên UI thì phải chốt lại quyết định mới (hiển thị kết quả lần chạy gần nhất của tool, không chạy trong web), ngược lại bỏ khỏi UI. CÒN MỞ.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT cho Codex)

Giữ `GET /api/v7/dashboard` (DASH-01) nguyên vững cho trang Chi tiết. Thêm một hàm/field mới, tiền vẫn chuỗi nguyên VND, tháng dạng `YYYY-MM-01`:

```json
GET /api/v7/dashboard/overview → sokhach.get_dashboard_overview()
{
  "as_of": "2026-10-24",
  "monthly_outstanding": [{"month": "2025-11-01", "total_vnd": "3100000000"}, "...12 tháng..."],
  "monthly_flow": [{"month": "2026-01-01", "new_debt_vnd": "400000000", "collected_vnd": "520000000"}],
  "monthly_aging": [{"month": "2026-05-01", "bucket": "current", "receivable_vnd": "700000000"}, "..."],
  "aging_matrix": [{"customer_id": 1, "name": "…", "commodity": null,
                    "buckets": {"current": "0", "1-2": "0", "3-6": "200000000", "over-6": "180000000"},
                    "total_vnd": "380000000", "oldest_open_month": "2026-03-01"}],
  "month_locks": [{"month": "2026-10-01", "locked": false}]
}
```

Lỗi/bộ đếm: `aging_matrix` có thể dài — trả toàn bộ khách đang nợ (đang ~18 khách thật, không cần phân trang).

## Nguồn quyết định

- [DASH-01](v7-dashboard.md) — nội dung dashboard gốc, ĐÃ CHỐT 23/10/2026.
- [V7-SO](../docs/decisions.md#v7-so), [V7-CSM](../docs/decisions.md#v7-csm) — khóa tháng, lịch sử mở/khóa.
- Quy tắc hiển thị aging/heat map: research 24/10/2026 (thanh ngang cho một thời điểm, stacked theo tháng cho chuỗi) — ghi tại `preview/mockups/DESIGN.md`.
- Đổi wording ("trả thừa" thay "dư tiền" trên nhãn): ĐỀ XUẤT từ vòng duyệt 24/10, chưa chốt chính thức.

## Hành vi và bất biến

- VND nguyên chuỗi; NULL/blank không là 0 (bucket trống hiển thị "–", không "0 đ").
- Aging theo **tháng nợ** (không phải ngày nhập); bucket giữ nguyên 4 nhóm DASH-01.
- Trang chỉ đọc; không đụng đường ghi tiền.
- Heat map/aging không tính chuyến thiếu giá và CHỜ KIỂM (đúng `get_dashboard` hiện có).

## Tiêu chí nghiệm thu

- [ ] `npm run check` xanh (bộ test browser mới cho 3 trang: aging lọc được, heat map sort được, drawer mở/ESC, 390px không cuộn ngang trang).
- [ ] Số trên 3 trang khớp nhau tại cùng `as_of` (tổng aging = `receivable.total_vnd` = tổng heat map = tổng `aging_matrix`).
- [ ] Chuỗi 12 tháng khớp đối chiếu một tháng bất kỳ với số liệu sổ thật (chọn 1 tháng, đối chiếu tay).
- [ ] Bàn phím/focus: tab qua mọi hàng bấm được, ESC đóng drawer, focus ring thấy được.
- [ ] Người dùng tự đi 3 trang trên bản thử và xác nhận.

## Phạm vi agent

- Agent: codex (backend overview) + claude (frontend 3 trang)
- Mockup: ĐÃ DUYỆT (HTML trong `preview/mockups/`, vòng 24/10/2026) — miễn Penpot nếu người duyệt chấp nhận mockup HTML là bản duyệt; CÒN MỎ nếu yêu cầu Penpot.
- Được sửa: `cong-no-web-handoff/web/v7_ledger_api.py`, `tools/v7_backend_functions.sql`, `preview/dashboard-v7.*`, mockup folders nêu trên, test browser tương ứng.
- Ngân sách diff: frontend ~600 dòng, backend ~250 dòng.
- Lệnh kiểm: `npm run check`.
- Cấm: thêm dependency; đổi schema/tiền/quyền; chạy DDL trên môi trường thật ngoài harness test.

## Hoàn tác

Revert PR; không đụng dữ liệu.

## Bằng chứng

Mockup chạy tại `preview/mockups/` (serve `python -m http.server 8123`); bộ test Playwright `test-results/check-v3b.js`, `check-v4b.js`, `check-heatmap.js` xanh 24/10/2026 (fixture, không tích hợp).

## Câu hỏi mở

- Cách tính chuỗi "tổng nợ cuối tháng": replay event theo tháng hay chỉ tính từ tháng có snapshot? (backend chốt)
- Khối "So web với Google Sheet": bỏ khỏi UI (theo DASH-01) hay hiển thị kết quả chạy `v7_reconcile_sheet.py` gần nhất (cần quyết định mới)?
- Có cần Penpot chính thức hay chấp nhận mockup HTML là bản duyệt?
