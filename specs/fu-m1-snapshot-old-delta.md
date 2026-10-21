# App ảnh chụp M1: không cộng chênh sổ cũ khi mốc không khớp hoặc dòng không xác nhận được

Trạng thái: ĐÃ CHỐT giao việc. Claude điều phối ngày 17/10/2026, theo cùng hướng PR #25 (người dùng đã duyệt merge) cho app ảnh chụp cũ. Không deploy; app này không nằm trong gói M1 (`tools/m1_release.py` chỉ chép `ledger_app.py`/`ledger_db.py`).

## Vấn đề

Claude đối chiếu trên `main` tại `7af67c2`:

- `cong-no-web-handoff/web/app.py` `render_overview()` (khoảng dòng 115) cộng `old_book_delta_vnd` của **mọi** dòng khách có giá trị khác NULL, rồi hiện "<số> chênh sổ cũ" ở khối "Các điểm còn mở" (khoảng dòng 132).
- Không xét trạng thái tổng: `db.provenance()` có `baseline_date`; chỉ khi đúng một dòng provenance và `baseline_date == as_of` của app thì mốc đối soát khớp ngày xem (giống `/health` và `main()` trong cùng file). Hiện `render_overview()` không nhận `as_of`.
- Không xét trạng thái từng dòng: cột `result` của `pilot.m1_customer_diff` có `NO_BASELINE`, `DUPLICATE_BASELINE` (chênh lấy `min()` của nhiều dòng mốc), `INVALID_BASELINE`, `NO_DB_EVENTS`. PR #25 ở `ledger_app.py` chỉ cộng dòng `MATCH`/`MISMATCH` có chênh khác NULL.

Hậu quả: chênh chưa xác nhận được trình bày như số đã biết; trái quy tắc giữ cờ `NO_BASELINE` (AGENTS.md).

## Nguồn quyết định

- PR #25 (merge `7af67c2`): `web/ledger_db.py` `customer_reconciliations()` và `web/ledger_app.py` `reconciliation_overview()` — chỉ cộng khi trạng thái tổng AVAILABLE, fail-closed, giữ số gốc.
- `specs/fu-m1-provenance-status.md`.

## Hành vi và bất biến

- `render_overview()` nhận thêm `as_of` (handler truyền `self.as_of`). Mốc khớp khi và chỉ khi `len(provenance) == 1` và `provenance[0]["baseline_date"] == as_of`; mọi trường hợp khác là chưa khớp (fail-closed). Ngoại lệ đã có sẵn giữ nguyên: provenance rỗng vẫn `raise DatabaseUnavailable("capture missing")` (503 cả trang, chặt hơn) — làm rõ 17/10/2026 sau khi review Claude và Codex hiểu khác nhau.
- Mốc chưa khớp: không cộng dòng nào; ô "chênh sổ cũ" thay số bằng câu nói rõ chưa có mốc đối soát khớp ngày xem nên chưa cộng (giọng câu hiện có, không thêm từ kỹ thuật như NO_BASELINE).
- Mốc khớp: chỉ cộng dòng có `result` thuộc {`MATCH`, `MISMATCH`} và `old_book_delta_vnd` khác NULL; ô ghi rõ đây là chênh đã biết và số khách được cộng. Dòng khác không được cộng.
- Không đổi dữ liệu dòng (`old_book_delta_vnd` gốc giữ nguyên, không thành 0/NULL); không đổi bảng khách, thẻ chỉ số, các trang khác, `db.py`, SQL view, `/health`, `main()`.
- VND nguyên (`int`), không float.

## Tiêu chí nghiệm thu

- [ ] Test tái hiện trước khi sửa trong `tests/test_web.py`, gọi `app.render_overview` với DB giả (số giả): (a) `baseline_date` khác `as_of`, có dòng `MATCH` chênh khác 0 → không hiện số đó; (b) mốc khớp, có thêm dòng `DUPLICATE_BASELINE`/`NO_BASELINE` có chênh → tổng chỉ gồm dòng `MATCH`/`MISMATCH`. FAIL trên code cũ, PASS sau sửa. Không tái hiện được thì dừng và báo, không sửa.
- [ ] Test: mốc khớp, chỉ dòng `MATCH`/`MISMATCH` → tổng như cũ.
- [ ] `cd cong-no-web-handoff && {python} -m unittest discover -s tests -v` PASS.

## Phạm vi agent

- Agent: codex
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/web/app.py`
  - `cong-no-web-handoff/tests/test_web.py`
- Ngân sách diff: 90 dòng
- Lệnh kiểm:
  - `cd cong-no-web-handoff && {python} -m unittest discover -s tests -v`
- Cấm:
  - Sửa `ledger_app.py`, `ledger_db.py`, `db.py`, SQL, gói release; deploy; kết nối DB hay `hao`.
  - Đổi hàm/trang khác ngoài `render_overview()` và một lời gọi trong handler; format lại file.
  - Ghi số liệu live vào test (dùng số giả).
- Khi cần vượt phạm vi: dừng, nêu câu hỏi trong báo cáo cuối.

## Hoàn tác

Revert commit. Không đụng dữ liệu.

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
