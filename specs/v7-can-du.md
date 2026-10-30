# Nợ từng tháng theo chuẩn tuổi nợ: cấn khoản dư vào tháng nợ cũ nhất (CAN-DU-01)

Trạng thái: ĐÃ CHỐT (người dùng, 30/10/2026, chat "ok làm theo chuẩn"; quyết định [`CAN-DU-01`](../docs/decisions/can-du-01.md))

## Người dùng và luồng

Người theo dõi công nợ mở sổ khách hoặc ma trận Công nợ theo tháng để biết khách còn nợ tháng nào. Trước thay đổi, khách có tháng âm (ví dụ số dư đầu âm vì khách trả trước) hiện "dư" ở tháng đó, trong khi các tháng sau vẫn hiện nợ đủ. Hai số đó nghe mâu thuẫn và làm tăng nợ quá hạn. Sau thay đổi: khoản dư cấn vào tháng còn nợ cũ nhất, tháng âm về 0 và tháng nợ cũ nhất giảm đúng bằng khoản dư. Bấm ô trong ma trận, ngăn kéo hiện phép tính có dòng khoản dư.

## Đầu ra

`v_outstanding_month.outstanding_vnd` là nợ còn lại của từng kỳ sau khi cấn khoản dư theo nợ cũ trước. Mọi chỗ đọc view (get_ledger `months[].outstanding_vnd`, ma trận, ngăn kéo, tổng quan/tuổi nợ, top nợ, tháng nợ cũ nhất) đổi theo mà không sửa từng hàm. Tổng mỗi khách và "Còn nợ cuối tháng" không đổi.

## Đối chiếu dữ liệu và code hiện có

- `v_outstanding_month` (file chuẩn `cong-no-web-handoff/tools/v7_backend_functions.sql`, bản live từ migration 22/10) = opening + chuyến đã có giá + điều chỉnh + cấn trừ đi − dòng phân bổ phiếu, theo kỳ. Kỳ âm giữ dấu.
- `reallocate` tự tính nợ kỳ từ các vế (không đọc view), phân bổ phiếu chỉ vào kỳ có nợ dương; dư thì `advance` ở kỳ cuối.
- `record_receipt` xếp tạm theo view rồi gọi `reallocate`.
- `get_ledger.end_of_month_vnd` tính lùi từ tổng còn nợ; tổng không đổi nên chuỗi không đổi.
- `record_offset`/`list_offset_sources` chỉ dùng tổng khách; không đổi.
- Ngăn kéo (`get_receivables_detail` + `cong-no-theo-thang.js`) hiện "Phát sinh − Thu đã trừ = Còn lại"; khi có cấn khoản dư phép trừ này không còn khớp nếu không có dòng mới.

## Nguồn quyết định

- [`CAN-DU-01`](../docs/decisions/can-du-01.md) thay vế số nợ từng tháng của [`V7-BE`](../docs/decisions/v7-be.md) (6).
- Giữ [`V7-SO`](../docs/decisions/v7-so.md) (phân bổ lại phiếu), [`DA-THU-01`](../docs/decisions/da-thu-01.md) (Còn nợ cuối tháng, đã thu theo ngày thu).

## Hành vi và bất biến

- Mỗi khách: `credit` = tổng phần âm của các kỳ thô; nợ của kỳ dương k = `min(thô_k, max(0, Σ nợ dương tới k − credit))`; kỳ âm và kỳ 0 thành 0; nếu `credit` > tổng nợ dương thì phần dư (số âm) cộng vào kỳ cuối của khách.
- Tổng mỗi khách bằng tổng thô (migration kiểm, lệch thì hủy cả lượt: `CAN_DU_TOTAL_MISMATCH`). Không khách nào vừa có kỳ dương vừa có kỳ âm (`CAN_DU_CREDIT_LEFT`).
- Dòng phân bổ phiếu thu và event giữ nguyên: `record_receipt` xếp tạm theo view thô `v_outstanding_month_raw`, cùng cách `reallocate`, nên không sinh event phân bổ lại thừa.
- `get_receivables_detail.credit_applied_vnd` = số thô − ô ma trận (dương: nhận khoản dư tháng khác; âm: khoản dư của tháng đã cấn đi). Ngăn kéo: Phát sinh − Thu đã trừ − khoản dư nhận vào (+ khoản dư chuyển đi) = Còn lại.
- Hiệu năng: hàm đọc nhiều khách (ma trận, tổng quan) nối view cấn dư; thiếu thống kê bảng thì planner tính lại view cho từng khách (đo 250 khách: ma trận 45ms có thống kê, 750ms không có; bản cũ 62ms). Migration chạy `ANALYZE` các bảng `sokhach`; benchmark `test_pg_v7_matrix.py` đo sau `ANALYZE` như DB thật.
- VND nguyên, không làm tròn. View thô và view mới không cấp quyền đọc trực tiếp cho `sokhach_app`/`sokhach_reader`.
- Không đổi bảng, ràng buộc, dữ liệu, loại event hay quyền.

## Tiêu chí nghiệm thu

- [ ] Harness `test_pg_v7_backend.py --strict`: case mới `CAN-DU.01` (cấn cũ trước, phần dư ở kỳ cuối, `credit_applied_vnd`, ma trận, phiếu không sinh event phân bổ lại, migration chạy hai lượt không đổi catalog/view); 7.15b sửa kỳ vọng số nợ từng tháng theo luật mới, dòng phân bổ giữ nguyên; các chuỗi nâng DB kết thúc bằng migration mới và khớp file chuẩn.
- [ ] `test_pg_v7_matrix.py` cập nhật kỳ vọng tháng âm theo luật mới.
- [ ] `test-v7-receivables-matrix-browser.js`: ngăn kéo hiện dòng khoản dư nhận vào/chuyển đi, phép tính khớp ô.
- [ ] `npm run check`, `node scripts/check-secrets.js` xanh.
- [ ] Triển khai `hao` theo runbook: backup, `ON_ERROR_STOP`, `v7_post_deploy_check.sql`, tổng khách trước = sau, số khách có kỳ dương và kỳ âm cùng lúc sau = 0; nhật ký `docs/deploys/`.
- [ ] Người dùng mở lại sổ khách đã báo lệch (trong chat 30/10/2026) và ma trận năm 2025, xác nhận tháng âm về 0 và tháng nợ cũ nhất giảm đúng bằng khoản dư.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`)
- Được sửa: `cong-no-web-handoff/tools/v7_backend_functions.sql`, `cong-no-web-handoff/tools/migrations/2026-10-30-v7-can-du.sql`, `cong-no-web-handoff/tools/test_pg_v7_*.py`, `cong-no-web-handoff/tools/pg_v7_harness.py`, `cong-no-web-handoff/tools/v7_reconcile_real_copy.py`, `cong-no-web-handoff/tests/test_v7_fee_sql_sync.py`, `docs/v7-deploy-runbook.md`, `cong-no-web-handoff/preview/cong-no-theo-thang.js`, `cong-no-web-handoff/preview/test-v7-receivables-matrix-browser.js`, tài liệu quyết định/luật/spec.
- Cấm: đổi bảng, dữ liệu, dòng phân bổ đã lưu, quyền; loader `v7_load*`.

## Hoàn tác

Chạy lại hai view và hai hàm bản cũ: `CREATE OR REPLACE VIEW sokhach.v_outstanding_month` bằng thân của `v_outstanding_month_raw`, rồi các migration `2026-10-29-v7-matrix-drawer-receipts.sql` và `2026-10-29-v7-ra-ghi-tien.sql` (trả `get_receivables_detail` và `record_receipt` bản 29/10). View thô thừa lại không ảnh hưởng. Không đụng dữ liệu.

## Bằng chứng

Ghi ở PR và nhật ký triển khai.
