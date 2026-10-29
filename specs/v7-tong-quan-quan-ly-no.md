# V7 — Tổng quan quản lý công nợ (đổi nội dung DASH-01)

Trạng thái: **ĐÃ CHỐT** ([`DASH-03`](../docs/decisions/dash-03.md), người dùng 29/10/2026: "Duyệt, dùng mặc định" sau khi xem bản xem); **ĐÃ TRIỂN KHAI trên `hao` 30/10/2026** (release `5f04bc4`, [nhật ký](../docs/deploys/2026-10-30-tong-quan-quan-ly-no.md)); CÒN MỞ: người dùng tự đi hết luồng trên web thật. Nguồn: góp ý người dùng trong chat 29/10/2026 — Tổng quan phải nhất quán một mục tiêu là bức tranh công nợ (còn nợ, khách quá hạn hoặc rủi ro cao, tình hình thu); "Việc cần làm" không thuộc trang này; phân loại chỉ theo tháng và mặt hàng chưa đủ, trình bày còn đơn giản. Bản xem dữ liệu giả: [`preview/mockups/tong-quan-quan-ly-no/`](../cong-no-web-handoff/preview/mockups/tong-quan-quan-ly-no/index.html).

Spec này thay nội dung sáu khối của [DASH-01](v7-dashboard.md); giữ các điểm tương tác đã chốt 29/10/2026: bấm nhóm để lọc danh sách khách tại chỗ, bấm khách mở ngăn kéo, soi sâu ở Công nợ theo tháng, không so tháng trước, không đường 12 tháng.

## Người dùng và luồng (bước 1)

| Người xem | Lúc nào | Câu hỏi cần trả lời | Trang |
| --- | --- | --- | --- |
| Chủ nghiệp vụ | Cuối tuần/tháng, trước khi gọi đòi nợ | Khách nợ bao nhiêu? Bao nhiêu đã quá hạn, quá bao lâu? Ai cần đòi trước, vì sao? Thu tháng này có kịp nợ mới không? | Tổng quan |
| Người nhập | Cuối ngày | Còn chuyến thiếu giá/chờ kiểm nào? Hôm nay đã nhập/thu bao nhiêu? | Việc cần làm (tab mới) |

Luồng Tổng quan (trang đầu khi vào web, như DASH-01):

1. Đọc khối trên cùng: còn phải thu, đã thu/phát sinh tháng này, số khách rủi ro cao, thanh nợ theo hạn trả.
2. Bấm một nhóm hạn trả, ô "Khách rủi ro cao" hoặc một nhóm ở khối Phân loại → danh sách "Khách cần đòi trước" lọc tại chỗ (dải "Đang lọc", bỏ từng chip hoặc bỏ hết).
3. Bấm một khách → ngăn kéo: còn nợ, quá hạn, vì sao ở mức rủi ro đó, nợ theo tháng → "Mở sổ khách" hoặc "Xem ở ma trận".

Luồng người nhập: số trên mục "Việc cần làm" của thanh điều hướng → mở tab → bấm dòng → sổ khách tô đúng dòng (`?loc=thieu-gia|cho-kiem`, như hiện có).

## Đầu ra

- Tổng quan chỉ còn bốn khối về công nợ: A. Còn phải thu · B. Nợ theo hạn trả · C. Khách cần đòi trước · D. Phân loại khách đang nợ.
- Tab mới "Việc cần làm" nhận nguyên khối Việc cần làm và Hôm nay hiện có, thêm "Sổ đang dư tiền".
- Đọc được trên 1280×720: hàng trên (A, B) nằm trọn màn đầu; mọi số khớp server.

## Nội dung

| Khối | Thay cho | Hiện gì | Cách vẽ |
| --- | --- | --- | --- |
| A. Còn phải thu | A + "Đã thu hôm nay" | Tổng còn phải thu, số khách; ô nhỏ "Đã thu tháng này" (kèm phát sinh tháng này) và "Khách rủi ro cao" (số khách, tiền quá hạn; bấm = lọc C); chú thích: chưa tính N chuyến thiếu đơn giá, khách đang dư tính riêng | Số lớn + 2 ô nhỏ |
| B. Nợ theo hạn trả | C (tháng phát sinh) | 5 nhóm: chưa đến hạn · đến hạn cuối tháng này · quá hạn 1–2 tháng · 3–6 tháng · trên 6 tháng; mỗi nhóm ghi rõ tháng nợ (vd "nợ T7–T8"); một câu kết luận | Một thanh chia đoạn, vạch "trong hạn \| quá hạn"; phần quá hạn màu cam → đỏ |
| C. Khách cần đòi trước | D (10 khách nợ nhiều nhất) | 10 khách xếp theo tiền quá hạn (bấm cột "Còn nợ" để xếp theo tổng); mỗi dòng: tên, nhãn Rủi ro cao/Theo dõi, một câu lý do ("7 tháng chưa trả · ngừng đi hàng"), thanh cơ cấu nợ theo nhóm hạn trả, quá hạn, còn nợ | Danh sách 2 dòng/khách |
| D. Phân loại khách đang nợ | B (mặt hàng) | Chọn một tiêu chí: Rủi ro · Lần trả gần nhất · Đi hàng gần nhất · Quy mô · Mặt hàng; mỗi nhóm: số khách, còn nợ; một câu kết luận | Thanh ngang; bấm = lọc C |
| Bỏ khỏi Tổng quan | E, F | Việc cần làm, Hôm nay → tab "Việc cần làm" | — |

## Quy tắc (ĐÃ CHỐT 29/10/2026, mặc định của đề xuất)

- **Hạn trả:** nợ tháng M đến hạn cuối tháng M+1 (gửi debit note đầu tháng sau, khách trả trong tháng đó). Một tham số chung cho mọi sổ; hạn riêng từng khách để sau.
- **Nhóm hạn trả** (theo tháng nợ, giờ VN): số tháng quá hạn = (tháng hiện tại − tháng nợ) − 1. Dưới 0: chưa đến hạn; 0: đến hạn cuối tháng này; 1–2; 3–6; từ 7: trên 6 tháng. Năm cũ không có tháng tính như tháng 12 năm đó.
- **Mức rủi ro** (chỉ khách đang nợ): *Rủi ro cao* = có nợ quá hạn **và** ít nhất một: quá hạn từ 3 tháng, hơn 60 ngày chưa trả (hoặc chưa trả lần nào), hơn 90 ngày không đi hàng. *Theo dõi* = có nợ quá hạn, không thuộc trên. *Trong hạn* = không có nợ quá hạn. Chỉ để tô màu và lọc, không chặn thao tác.
- **Lần trả gần nhất:** ngày của phiếu thu chưa hủy gần nhất; nhóm: trong 30 ngày · 31–60 · trên 60 · chưa trả lần nào.
- **Đi hàng gần nhất:** ngày xe nhập kho gần nhất (`DATE`); nhóm: trong 30 ngày · 31–90 · trên 90 (ngừng đi hàng).
- **Quy mô:** 5 khách nợ nhiều nhất · 5 tiếp theo · còn lại (cho biết mức tập trung nợ).
- **Thu tháng này:** đúng số "Đã thu"/"Phát sinh" dòng Tổng tháng của sổ khách (`DA-THU-01`) cộng qua mọi sổ đang hoạt động. Chỉ là số của tháng hiện tại, không so tháng trước.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Thông tin | Nguồn có sẵn | Tình trạng |
| --- | --- | --- |
| Còn phải thu, khách dư, mặt hàng, chuyến thiếu giá | `get_dashboard()` | Có, dùng nguyên |
| Nợ từng khách × tháng nợ | `v_outstanding_month` (qua `get_receivables_matrix`) | Có; nhóm hạn trả chỉ là cách gom khác của cùng số, tổng 5 nhóm = `receivable.total_vnd` |
| Đã thu / phát sinh tháng này | `get_ledger(...).months[]` `received_vnd`, `charges_vnd` (`DA-THU-01`) | Có từng sổ; **thiếu** hàm cộng toàn khách (gọi `get_ledger` 236 lần không chấp nhận) |
| Lần trả gần nhất | `receipt.date` (phiếu web chưa hủy); dòng thu sổ gốc `legacy_row` kind `receipt`, ô `display.date` (dạng YYYY-MM-DD hoặc DD/MM/YYYY, có thể trống) | Tính được; **cần kiểm** tỉ lệ dòng thu sổ gốc có ngày; trống thì dùng tháng của dòng, không bịa ngày. CÒN MỞ: phiếu CẤN TRỪ có tính là "trả" không |
| Đi hàng gần nhất | `v_trip_current.event_date` (chuyến chưa xóa, không tính đã loại); `legacy_row` kind `trip` `display.date` | Tính được; cùng lưu ý ô ngày sổ gốc |
| Hạn trả, mức rủi ro | — | Chưa có; quy tắc ở mục trên, tính ở server |
| Hạn trả riêng từng khách, hạn mức nợ, gộp nhiều sổ của một công ty, người phụ trách đòi | — | **Không có dữ liệu**; ngoài phạm vi bản này |

Mockup dùng bộ khách hư cấu của `preview/mockups/dashboard-redesign/data.js`, thêm ngày thu/ngày đi hàng/thu-phát sinh tháng giả; mọi khối tính từ cùng một bộ nên cộng về cùng tổng.

## Giao tiếp frontend–backend (bước 5)

Một hàm đọc mới `sokhach.get_dashboard_debt()` (SECURITY DEFINER, chỉ đọc, như `get_dashboard`; helper `_legacy_date` đọc ô ngày dòng sổ gốc, không ai được EXECUTE) và route `GET /api/v7/dashboard/debt`; tiền là chuỗi VND nguyên, ngày `YYYY-MM-DD`; chỉ khách đang nợ, xếp theo tiền quá hạn rồi còn nợ:

```json
{
  "as_of": "2026-10-29",
  "rule": {"due_after_months": 1, "long_overdue_months": 3, "no_pay_days": 60, "no_trip_days": 90},
  "due_tiers": [{"tier": "not_due", "receivable_vnd": "0", "from_month": "2026-10-01", "to_month": "2026-10-01"}, "… 5 nhóm …"],
  "this_month": {"received_vnd": "0", "charges_vnd": "0"},
  "receivable_vnd": "0",
  "summary": {"overdue_vnd": "0", "long_overdue_vnd": "0", "overdue_customers": 0, "high_customers": 0, "high_overdue_vnd": "0"},
  "customers": [{"customer_id": 1, "name": "…", "commodity": null, "transport_mode": null,
                 "outstanding_vnd": "0", "tiers_vnd": ["0", "0", "0", "0", "0"], "overdue_vnd": "0", "long_overdue_vnd": "0",
                 "oldest_open_month": "2026-07-01", "last_receipt_date": null, "last_receipt_exact": null, "pay_days": null,
                 "last_trip_date": null, "last_trip_exact": null, "trip_days": null, "risk": "high",
                 "months": [{"month": "2026-07-01", "outstanding_vnd": "0"}]}]
}
```

`*_exact` = false khi ngày lấy cuối tháng của dòng sổ gốc không có ngày. `get_dashboard()` giữ nguyên cho số tổng và tab Việc cần làm. Frontend gom/lọc danh sách bằng BigInt (`cong-no-format.js`); nếu tổng khách hoặc tổng từng nhóm khác số server thì không lọc tại chỗ mà mở Công nợ theo tháng (như cách Tổng quan làm với ma trận). API debt lỗi (ví dụ chưa nâng DB) thì trang vẫn hiện số tổng, các khối kia báo chưa tải được.

## Hành vi và bất biến

- VND nguyên; tổng 5 nhóm hạn trả = tổng các nhóm của mỗi tiêu chí phân loại = `receivable.total_vnd`.
- NULL không phải 0: thiếu ngày thu là "chưa trả lần nào"/"không rõ ngày", không tính như ngày 0; chuyến thiếu giá và CHỜ KIỂM không vào tổng nào (như `v_outstanding_month`).
- Ngày và tháng theo giờ VN (`DATE-01`), không dùng `current_date`.
- Trang chỉ đọc; không đổi đường ghi tiền, phân bổ hay `get_ledger`.
- Nhãn rủi ro luôn kèm chữ và lý do, không chỉ màu.

## Tiêu chí nghiệm thu

- [ ] Harness PostgreSQL: khách giả gồm nợ nhiều tháng, năm cũ, khách dư, phiếu hủy, cấn trừ, chuyến thiếu giá/chờ kiểm/đã loại, dòng sổ gốc có và không có ngày → nhóm hạn trả, mức rủi ro, ngày thu/đi hàng gần nhất đúng định nghĩa; tổng khớp `get_dashboard`; ranh giới tháng/ngày giờ VN.
- [ ] `npm run check` xanh, gồm test browser 1280×720: lọc theo nhóm hạn trả + phân loại kết hợp, đổi tiêu chí giữ lọc, xếp cột, ngăn kéo mở/ESC, không cuộn ngang ở 390px.
- [ ] Tab Việc cần làm giữ đúng số và đường mở sổ `?loc=` như trước.
- [ ] Người dùng tự đi hết luồng trên bản thử và xác nhận.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`)
- Review: opus
- Được sửa: `tools/v7_backend_functions.sql`, migration `tools/migrations/2026-10-29-v7-tong-quan-quan-ly-no.sql`, `tools/v7_post_deploy_check.sql`, harness (`test_pg_v7_backend.py`, `test_pg_v7_backend_dashboard_debt.py`, chuỗi migration trong `test_pg_v7_backend_locks.py`/`_price.py`, `test_pg_v7_grants.py`), `web/v7_ledger_api.py`, `web/v7_presence.py`, `tests/test_v7_ledger_api.py`, `preview/dashboard-v7.*`, `preview/dashboard-v7-model.js`, `preview/viec-can-lam.*`, thanh điều hướng của `cong-no-theo-thang.html`/`so-khach-v7-live.html`, `preview/presence.js` (tên trang), test JS tương ứng.
- Cấm: đổi bảng, view, hàm ghi tiền, phân bổ hay `get_ledger`; GRANT bảng/view; thêm dependency.

## Hoàn tác

Revert PR; migration chỉ thêm hai hàm đọc (`DROP FUNCTION sokhach.get_dashboard_debt(); DROP FUNCTION sokhach._legacy_date(text);`). Không đụng dữ liệu.

## Bằng chứng

- Bản xem: `preview/mockups/tong-quan-quan-ly-no/` (serve thư mục `cong-no-web-handoff/preview` rồi mở `/mockups/tong-quan-quan-ly-no/`), kiểm ở khung 1280×720 ngày 29/10/2026: không cuộn ngang, không lỗi console, lọc kết hợp và ngăn kéo chạy; eslint đạt. Chỉ là dữ liệu giả.
- Code: harness `DASH.03` (khách giả: nhóm hạn trả, mức rủi ro, ngày thu/đi hàng từ phiếu web, cấn trừ, dòng sổ gốc có/không/sai ngày và đã xóa, tháng có số Sheet; tổng khớp `get_dashboard`; đã thu/phát sinh tháng này khớp tổng `get_ledger` mọi sổ), chuỗi migration so catalog với khởi tạo mới, checker quyền; test model và trình duyệt 1280×720 + 390px cho Tổng quan và tab Việc cần làm. Kết quả lượt chạy ghi ở PR.

## Câu hỏi mở

- Hạn trả riêng từng khách, hạn mức nợ, gộp nhiều sổ của một công ty: chưa có dữ liệu, chưa làm.
