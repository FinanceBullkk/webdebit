# Harness P0 truyền SQL qua stdin

Trạng thái: ĐỀ XUẤT ngày 16/10/2026 bởi Claude, sau khi review nhánh `codex/p0-fixture-future-posting-date`. Chỉ sửa cách harness gọi `psql` trên dữ liệu giả; không đổi fixture, schema hay hành vi nghiệp vụ.

## Đầu ra

`test_pg_versioned_approval.py` chạy hết mọi nhóm trên Windows, không còn `group_errors`. Hiện nhóm `canonical_v3` dừng giữa chừng vì `FileNotFoundError: [WinError 206] The filename or extension is too long`: `Fixture.psql()` đưa SQL vào argv bằng `psql -c`, payload lớn vượt giới hạn dòng lệnh ~32K ký tự của Windows. CI Linux không gặp nên lỗi bị che.

## Nguồn quyết định

- Không có quyết định nghiệp vụ mới. Lan can harness ở [next-task P0](p0-write-path/next-task.md): `ON_ERROR_STOP`, `--network none`, cleanup theo label/run-id.

## Hành vi và bất biến

- `Fixture.psql()` gửi SQL qua stdin (`docker exec -i … psql … -f -`, `input=sql`), giữ nguyên `-X -qAt`, `ON_ERROR_STOP=1`, `VERBOSITY=verbose`, user, database, `PGAPPNAME`, `PGOPTIONS`, `check`, `timeout`.
- Mỗi lời gọi vẫn là một phiên psql riêng, SQL chạy như trước (cùng transaction semantics; nếu chuyển `-c` sang stdin làm đổi việc gói nhiều câu trong một transaction thì dùng `-1`/`--single-transaction` chỉ khi kết quả assertion cũ giữ nguyên và ghi lý do).
- Stdout/stderr, mã lỗi và thông báo `P0001` mà các assertion `rejected(...)` đọc phải giữ nguyên định dạng.
- Lệnh `-c` ngắn cố định trong `main()` (kiểm version, tạo DB, marker) và các `Popen` cho concurrency giữ nguyên.

## Tiêu chí nghiệm thu

- [ ] Trên Windows: `{python} cong-no-web-handoff/tools/test_pg_versioned_approval.py --report %TEMP%\harness-psql-stdin.json` thoát 0, report có `group_errors: []`, `canonical_v3` đủ case, `cleanup: verified_and_removed`.
- [ ] Số case và số failed của mọi nhóm khác bằng lượt trước trên nhánh gốc (không mất case nào).
- [ ] Unit test Python vẫn xanh.

## Phạm vi agent

- Agent: codex
- Được sửa:
  - `cong-no-web-handoff/tools/test_pg_versioned_approval.py`
- Ngân sách diff: 40 dòng
- Lệnh kiểm:
  - `{python} cong-no-web-handoff/tools/test_pg_versioned_approval.py --report %TEMP%\harness-psql-stdin.json`
  - `cd cong-no-web-handoff && {python} -m unittest discover -s tests`
- Cấm:
  - Sửa `pg_versioned_approval_fixture.sql`, `pg_ledger_schema.sql`, `test_pg_ledger_schema.py`, `web/`, `m1_release.py`, `pg_m1_report.py`.
  - Đổi, xóa hoặc nới assertion; đổi thứ tự nhóm; thêm dependency.
  - Đổi cô lập container (network, label, cleanup); trỏ tới DB thật hoặc `hao`.
- Khi cần vượt phạm vi: dừng, ghi câu hỏi ở mục "Câu hỏi mở".

## Hoàn tác

Revert commit; không có dữ liệu bền vững.

## Bằng chứng

<Revision, report JSON, so số case trước/sau.>

## Câu hỏi mở

- `test_pg_ledger_schema.py` cũng dùng `-c` nhưng SQL ngắn; chưa gặp lỗi nên ngoài phạm vi.
