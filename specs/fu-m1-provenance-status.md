# M1: không cộng chênh sổ cũ khi mốc đối soát không khớp ngày xem

Trạng thái: ĐÃ CHỐT giao việc. Người dùng đồng ý ngày 16/10/2026 trong chat sau review chuỗi PR #1–#7. Sửa code web xem sổ M1 (đang chạy chỉ đọc trên `hao`); PR này **không** deploy, deploy là gate riêng của người dùng.

## Vấn đề

Claude đối chiếu trên `main` tại `53d02c7`:

- `cong-no-web-handoff/web/ledger_db.py` `customer_reconciliations()`: khi provenance có `baseline_date` thiếu hoặc khác `as_of`, kết quả tổng `reconciliation_status` = `NO_BASELINE`, nhưng từng dòng vẫn có `old_book_delta_status` = `AVAILABLE` và `reconciliation_status` = `MATCH`/`MISMATCH` theo bảng `pilot.m1_customer_diff`.
- `cong-no-web-handoff/web/ledger_app.py` `reconciliation_overview()` chỉ xét từng dòng, nên vẫn hiện "Tổng chênh sổ cũ đã biết: … từ N khách." như số đã xác nhận.

Hậu quả: chênh lệch chưa có mốc khớp ngày xem được trình bày như đã biết; trái quy tắc giữ cờ `NO_BASELINE` (AGENTS.md).

## Hành vi và bất biến

- Khi trạng thái tổng là `NO_BASELINE`, mỗi dòng trả về `old_book_delta_status` = `NO_BASELINE` (giữ nguyên `old_book_delta_vnd` gốc để truy vết, không đổi thành 0 hay NULL).
- `reconciliation_overview()` không cộng dòng nào khi trạng thái tổng là `NO_BASELINE`; câu hiển thị nói rõ chưa có mốc đối soát khớp ngày xem, dùng đúng giọng các câu hiện có, không thêm từ kỹ thuật.
- Khi `baseline_date == as_of`: hành vi và câu chữ giữ nguyên như hiện tại.
- Mở rộng 17/10/2026 (Claude điều phối, sau review Codex lần 8; người dùng xem lại khi duyệt PR): danh sách khách rỗng không cho biết mốc có khớp hay không, nên `reconciliation_overview()` nhận thêm trạng thái tổng (`baseline_available`). Được sửa thêm đúng ba chỗ để truyền trạng thái này: chữ ký `source_warning()` (tham số tùy chọn, mặc định giữ hành vi cũ), lời gọi ở trang tổng quan và trang ngoại lệ. Không đổi gì khác trong các hàm đó.
- Không đổi SQL view, schema, ACL, số liệu hay các trang khác.

## Tiêu chí nghiệm thu

- [ ] Test tái hiện trước khi sửa (provenance `baseline_date` khác `as_of`, có dòng `AVAILABLE` với chênh khác 0) — FAIL trên code cũ, PASS sau sửa. Nếu không tái hiện được thì dừng và báo, không sửa.
- [ ] Test: `baseline_date == as_of` vẫn cộng như cũ.
- [ ] `cd cong-no-web-handoff && {python} -m unittest discover -s tests -v` PASS.

## Phạm vi agent

- Agent: codex
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/web/ledger_db.py`
  - `cong-no-web-handoff/web/ledger_app.py`
  - `cong-no-web-handoff/tests/test_ledger_web.py`
- Ngân sách diff: 80 dòng
- Lệnh kiểm:
  - `cd cong-no-web-handoff && {python} -m unittest discover -s tests -v`
- Cấm:
  - Đổi schema/view/ACL, gói release, deploy; kết nối DB hay `hao`.
  - Đổi trang/hàm khác ngoài hai hàm trên, ba chỗ truyền trạng thái tổng nêu ở "Hành vi và bất biến", và test; format lại file.
  - Ghi số liệu live vào test (dùng số giả).
- Khi cần vượt phạm vi: dừng, nêu câu hỏi trong báo cáo cuối.

## Hoàn tác

Revert commit. Bản đang chạy trên `hao` không đổi cho tới khi người dùng deploy.
