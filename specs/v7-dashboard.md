# V7 — Trang tổng quan công nợ (DASH-01)

Trạng thái: **ĐÃ CHỐT nội dung** bởi người dùng 23/10/2026 (chọn trong chat); spec do Claude soạn. Đây là bước 1–2 của [quy trình frontend](../docs/development.md#quy-trình-frontend). Backend giao Codex theo mục "Phạm vi agent"; giao diện **chờ mockup Penpot** (Gemini) được người dùng duyệt, chưa code.

## Người dùng và luồng (bước 1)

Theo [UX](../docs/ux-guidelines.md): người dùng trên 40 tuổi, màn 1280×720, không thông tin thừa. Nhịp đối soát: người nhập xem cuối ngày, chủ nghiệp vụ xem cuối tuần/tháng.

| Người xem | Lúc nào | Cần biết để làm gì |
| --- | --- | --- |
| Người nhập | Cuối ngày | Còn việc gì dở (chuyến thiếu giá, CHỜ KIỂM…), hôm nay đã nhập/thu bao nhiêu → bấm là mở đúng sổ khách |
| Chủ nghiệp vụ | Cuối tuần/tháng | Tổng còn phải thu, theo mặt hàng, nợ cũ bao lâu, khách nào nợ nhiều → đòi nợ ai trước |

Luồng (ĐÃ CHỐT): **trang tổng quan là trang đầu khi vào web**. Từ đây chọn khách (ô chọn khách hiện có) hoặc bấm một dòng khách/việc cần làm → mở sổ khách (`so-khach-v7-live.html?customer=<id>`). Từ sổ khách có đường quay lại trang tổng quan. Trang **chỉ đọc**.

## Nội dung (ĐÃ CHỐT 23/10/2026)

| Khối | Hiện gì |
| --- | --- |
| A. Tổng còn phải thu | Tổng nợ các khách đang nợ và số khách; dòng phụ: tổng tiền khách đang dư (theo [V7-CSM](../docs/decisions.md#v7-csm) D04, dư là số âm) và số khách dư |
| B. Theo mặt hàng | Mặt hàng · phương thức → số khách đang nợ, còn phải thu; "Chưa phân loại" cuối |
| C. Nợ theo tháng phát sinh | Còn phải thu chia nhóm theo tháng nợ: tháng này · 1–2 tháng trước · 3–6 tháng trước · trên 6 tháng |
| D. Khách nợ nhiều nhất | 10 khách nợ lớn nhất: tên, mặt hàng, còn nợ, tháng nợ xa nhất còn mở |
| E. Việc cần làm | Theo khách: chuyến **web** thiếu đơn giá (dòng sổ gốc thiếu giá **không** tính — người dùng chọn); chuyến CHỜ KIỂM; khách chưa có số dư đầu; sổ đang dư tiền |
| F. Hôm nay | Theo **ngày ghi trên web** (giờ VN, người dùng chọn): số chuyến đã nhập, số phiếu thu và tổng tiền thu, số phiếu hủy; chia theo người làm |

Không làm: đối chiếu với Sheet (DB không giữ Sheet; vẫn dùng `tools/v7_reconcile_sheet.py` ngoài web).

## Đối chiếu dữ liệu và code hiện có (bước 2)

Lược đồ `sokhach` ([schema](v7-backend/schema-draft.sql), [hàm](../cong-no-web-handoff/tools/v7_backend_functions.sql)); API `cong-no-web-handoff/web/v7_ledger_api.py`.

- **Còn nợ khách × tháng nợ:** view `v_outstanding_month` (đã gồm số dư đầu, chuyến có giá, điều chỉnh, trừ dòng phân bổ của phiếu chưa hủy; chỉ khách/cutover `active`). Tổng một khách = tổng các tháng = `get_ledger.total_outstanding_vnd`.
- **Mặt hàng:** `customer.commodity_id` → `commodity.name`, `customer.transport_mode` — cột đã có trên `main`. Trên `hao` NULL hết cho tới khi chạy bước gán của [MH-01](v7-mat-hang-chon-khach.md) (PR FinanceBullkk/webdebit#77); khi đó khối B hiện toàn bộ là "Chưa phân loại".
- **Chuyến web thiếu giá:** chuyến `confirmed`, chưa xóa, bản giá mới nhất không có đơn giá — đúng điều kiện `is_missing_price` của `get_ledger` (phí lẻ không container có phụ phí thì không thiếu giá).
- **CHỜ KIỂM:** `trip.status = 'pending_review'`.
- **Chưa có số dư đầu:** khách không có `cutover_customer` và `cutover` cùng `active` (như `list_customers` trả `NO_BASELINE`).
- **Hôm nay:** `event.at` đổi sang ngày `Asia/Ho_Chi_Minh`; chuyến qua `trip.created_by_event`, phiếu qua `receipt.created_by_event`, hủy qua `receipt.voided_by_event`; người làm là `event.actor`.
- **Quyền:** schema cấm GRANT SELECT bảng/view toàn khách cho app/reader; số tổng hợp đi qua hàm `SECURITY DEFINER` chỉ đọc, như `list_customers`.
- **Thiếu (Codex làm):** hàm tổng hợp toàn khách và route API.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT cho Codex)

`GET /api/v7/dashboard` → `sokhach.get_dashboard()` (không tham số). Tiền là **chuỗi số nguyên VND** như `get_ledger`; ngày `YYYY-MM-DD`; tháng `YYYY-MM-01`.

```json
{
  "as_of": "2026-10-23",
  "receivable": {"total_vnd": "0", "customers": 0},
  "credit": {"total_vnd": "0", "customers": 0},
  "by_commodity": [{"commodity": "Sầu riêng", "transport_mode": "CANG", "customers": 0, "receivable_vnd": "0"}],
  "aging": [{"bucket": "current", "receivable_vnd": "0"}, {"bucket": "1-2", "receivable_vnd": "0"},
            {"bucket": "3-6", "receivable_vnd": "0"}, {"bucket": "over-6", "receivable_vnd": "0"}],
  "top_debtors": [{"customer_id": 1, "name": "…", "commodity": null, "transport_mode": null,
                   "outstanding_vnd": "0", "oldest_open_month": "2026-07-01"}],
  "todo": {
    "missing_price": [{"customer_id": 1, "name": "…", "count": 0}],
    "pending_review": [{"customer_id": 1, "name": "…", "count": 0}],
    "no_baseline": [{"customer_id": 1, "name": "…"}],
    "credit": [{"customer_id": 1, "name": "…", "credit_vnd": "-0"}]
  },
  "today": {"trips": 0, "receipts": 0, "received_vnd": "0", "voids": 0,
            "by_actor": [{"actor": "…", "trips": 0, "receipts": 0, "received_vnd": "0", "voids": 0}]}
}
```

Định nghĩa:

- `receivable`: khách `active` có tổng > 0; `credit`: khách `active` có tổng < 0 (`total_vnd` âm). Khách tổng = 0 không vào cả hai.
- `by_commodity`: chỉ khách trong `receivable`; nhóm theo (`commodity`, `transport_mode`), NULL là một nhóm; xếp theo tên mặt hàng, nhóm NULL cuối. Tổng các nhóm = `receivable.total_vnd`.
- `aging`: chỉ khách trong `receivable`, cộng `outstanding_vnd` từng tháng của họ (kể cả tháng âm) vào nhóm theo khoảng cách tháng nợ tới tháng hiện tại (giờ VN): `current` = tháng hiện tại hoặc sau; `1-2`; `3-6`; `over-6` = 7 tháng trở lên. Luôn đủ 4 nhóm, đúng thứ tự trên. **Tổng 4 nhóm = `receivable.total_vnd`.**
- `top_debtors`: 10 khách `receivable` lớn nhất, hòa thì theo tên rồi id; `oldest_open_month` = tháng nhỏ nhất có `outstanding_vnd > 0`.
- `todo.*`: danh sách theo tên (`COLLATE "C"`, rồi id); chỉ khách có ít nhất một mục. `missing_price`/`pending_review` đếm chuyến của khách `active`. `credit` = khách trong `credit`.
- `today`: event có `at` trong ngày `as_of` giờ VN. `trips` = số chuyến có `created_by_event` hôm nay (mọi trạng thái); `receipts`/`received_vnd` = phiếu có `created_by_event` hôm nay, **kể cả** đã hủy sau đó; `voids` = phiếu có `voided_by_event` hôm nay. `by_actor` theo actor của event tạo/hủy, xếp theo actor.
- Không có dữ liệu: danh sách rỗng, số 0 — không lỗi.

## Hành vi và bất biến

- VND nguyên, không làm tròn; frontend không cộng trừ tiền (`ARCH-03`).
- NULL không phải 0: chuyến thiếu giá, CHỜ KIỂM, đã loại không vào tổng (giữ đúng `v_outstanding_month`).
- Khách chưa có số dư đầu không vào tổng, chỉ ở `todo.no_baseline`.
- `receivable.total_vnd` = tổng `get_ledger.total_outstanding_vnd` của các khách dương; `credit` tương tự cho khách âm.
- "Hôm nay" theo giờ VN (`DATE-01`): không dùng `current_date`.

## Tiêu chí nghiệm thu (backend)

- [ ] Harness PostgreSQL (`tools/test_pg_v7_backend.py`, case mới `DASH.01`…): với khách giả gồm khách nợ nhiều tháng, khách dư, khách tổng 0, khách NO_BASELINE, chuyến thiếu giá, CHỜ KIỂM, chuyến đã loại, phiếu hủy, phí lẻ, khách có/không mặt hàng → mọi số khớp định nghĩa trên; `receivable`/`credit` khớp tổng `get_ledger`; tổng `aging` = tổng `by_commodity` = `receivable.total_vnd`.
- [ ] Ranh giới ngày VN: event lúc 23:30 và 00:30 giờ VN rơi đúng ngày (`today`); tháng nợ ranh giới `aging` đúng.
- [ ] Quyền: `sokhach_app` và `sokhach_reader` gọi được; thiếu actor bị từ chối `ACTOR_REQUIRED`; không cấp quyền bảng/view mới (`test_pg_v7_grants.py`, `v7_post_deploy_check.sql`).
- [ ] Migration nâng DB đang chạy: chuỗi migration cũ → bản này cho catalog hàm giống schema mới, chạy lặp được, lỗi giữa chừng rollback (`--migration-test`).
- [ ] API: `GET /api/v7/dashboard` gọi đúng hàm, có cờ `demo`/`real_copy` như `list_customers`; POST bị từ chối; unittest `tests/test_v7_ledger_api.py`.
- [ ] `npm run check` xanh.

## Phạm vi agent

- Agent: codex
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/tools/v7_backend_functions.sql` (thêm hàm `get_dashboard` và GRANT, không sửa hàm khác)
  - `cong-no-web-handoff/tools/migrations/2026-10-24-v7-dashboard.sql` (mới)
  - `cong-no-web-handoff/web/v7_ledger_api.py` (route GET mới)
  - `cong-no-web-handoff/tools/test_pg_v7_backend.py`, `cong-no-web-handoff/tools/test_pg_v7_grants.py`, `cong-no-web-handoff/tools/v7_post_deploy_check.sql`
  - `cong-no-web-handoff/tests/test_v7_ledger_api.py`
  - `specs/v7-dashboard.md` (chỉ mục "Bằng chứng" và "Câu hỏi mở")
- Ngân sách diff: 600 dòng
- Lệnh kiểm (script chạy từ gốc worktree bằng cmd.exe; `{python}` là venv của checkout chính):
  - `npm run check`
  - `{python} cong-no-web-handoff/tools/test_pg_v7_grants.py --strict`
  - `{python} cong-no-web-handoff/tools/test_pg_v7_backend.py --migration-test`
- Cấm:
  - Sửa bảng, view, hàm ghi tiền hoặc cách phân bổ; GRANT SELECT bảng/view; thêm dependency.
  - Code giao diện (chờ mockup Penpot được duyệt).
  - Chạy trên `hao`, Sheet hay dữ liệu thật; đưa tên khách/số tiền thật vào code, test, log.
- Ghi chú phối hợp: PR FinanceBullkk/webdebit#77 (mặt hàng) sửa `list_customers`, `test_pg_v7_backend.py` (chuỗi migration) và thêm migration `2026-10-23-v7-mat-hang.sql`. Migration của bản này chạy **sau** file đó; nếu #77 đã merge thì rebase lên `main` trước khi mở PR, nếu chưa thì chỉ thêm hàm mới, không đụng các chỗ #77 sửa.
- Khi cần vượt phạm vi: dừng, ghi câu hỏi ở "Câu hỏi mở".

## Hoàn tác

Revert PR; migration chỉ thêm một hàm chỉ đọc, gỡ bằng `DROP FUNCTION sokhach.get_dashboard()`. Không đụng dữ liệu.

## Bằng chứng

Chưa có.

## Câu hỏi mở

- Bố cục trang, thứ tự khối, cách hiện đường quay lại từ sổ khách: chốt ở mockup Penpot (Gemini), chưa vẽ.
