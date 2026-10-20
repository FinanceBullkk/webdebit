# Sửa công cụ kiểm và CI sau review chuỗi PR #1–#7

Trạng thái: ĐÃ CHỐT giao việc. Người dùng đồng ý ngày 16/10/2026 trong chat ("xử lý giúp mình đi, có thể giao cho codex") sau review chuỗi PR trước khi merge vào main. Chỉ sửa công cụ kiểm/test/CI; không đổi schema, dữ liệu hay service thật.

## Đầu ra

Bốn khoảng trống do Codex review (đã được Claude đối chiếu trên `main` tại `53d02c7`) được khép, mỗi điểm có test chứng minh:

1. **Số liệu live hard-code.** `cong-no-web-handoff/tools/pg_ledger_verify.py` ghi cứng số kỳ, tổng opening và số kỳ `NO_BASELINE` của DB live; `tests/test_ledger_web.py` (dòng ~48 và ~547) dùng cùng số. Repo không được chứa số liệu live (PR #20). Đổi thành tham số dòng lệnh bắt buộc `--expect-periods`, `--expect-total-vnd`, `--expect-no-baseline` (giá trị lấy từ hồ sơ ngoài Git khi chạy thật); thiếu tham số thì lỗi, không có giá trị mặc định. Test dùng số giả nhỏ, khác số thật.
2. **`NO_DB_EVENTS` được chấp nhận sai.** `tools/pg_m1_verify.py` `check_reconciliation()` chấp nhận `NO_DB_EVENTS` kể cả khi khóa thuộc `required_keys` (đã có sự kiện replay). Từ chối `NO_DB_EVENTS` cho khóa thuộc `required_keys`; giữ chấp nhận cho khóa không có sự kiện. Thêm test trong `tests/test_m1_export_verify.py`.
3. **Harness PostgreSQL.** `tools/test_pg_ledger_schema.py`:
   - Dọn volume chỉ khi `volume_created`; nếu `docker volume create` đã tạo volume rồi CLI timeout/lỗi thì bỏ sót và báo `nothing_created`. Luôn dò volume đúng tên của run, kiểm name + labels + run-id rồi mới xóa, như cách đã làm với container; báo cleanup đúng thực tế.
   - `holder_pid_in_blocker_chain` dùng `str(holder_pid) in blocker_snapshot` (so chuỗi con). Parse `pg_blocking_pids` thành tập số nguyên và kiểm holder thuộc tập đó.
   - Thêm kiểm không cần Docker (unit test thuần Python, mock lệnh docker) cho: volume tạo xong rồi CLI lỗi → vẫn bị dọn; label lệch → từ chối xóa; PID trùng một phần (ví dụ 12 so với 123) → không tính là có.
4. **Migration F2/F3 chưa chạy trong CI.** `.github/workflows/test.yml` chỉ chạy harness không có `--base-schema`/`--migration`. Thêm bước chạy harness với `--base-schema` = `pg_ledger_schema.sql` tại commit `8c78c0f` (trước 74f5901/97c19d5, lấy bằng `git show` trong CI, cần `fetch-depth: 0` hoặc fetch commit đó) và `--migration cong-no-web-handoff/tools/migrations/2026-10-16-ledger-f2f3.sql`. Bước này chỉ chạy trong container của harness (`--network none`), không chạm DB thật.

## Hành vi và bất biến

- Không đổi `pg_ledger_schema.sql`, migration, dữ liệu fixture nghiệp vụ hay ngưỡng chấp nhận khác ngoài 4 điểm trên.
- Blank/NULL không thành 0; lỗi phải fail-closed.
- Không ghi số liệu live vào repo, kể cả trong test, comment, ví dụ.

## Tiêu chí nghiệm thu

- [ ] `git grep 65051673578` và `git grep "496"` trong hai file trên không còn số liệu live.
- [ ] Test mới cho điểm 1–3 chạy được không cần Docker và PASS.
- [ ] Workflow có bước migration; YAML hợp lệ (CI trên PR sẽ chứng minh chạy được; máy local không có Docker).
- [ ] `cd cong-no-web-handoff && {python} -m unittest discover -s tests -v` PASS.

## Phạm vi agent

- Agent: codex
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/tools/pg_ledger_verify.py`
  - `cong-no-web-handoff/tools/pg_m1_verify.py`
  - `cong-no-web-handoff/tools/test_pg_ledger_schema.py`
  - `cong-no-web-handoff/tests/test_ledger_web.py`
  - `cong-no-web-handoff/tests/test_m1_export_verify.py`
  - `cong-no-web-handoff/tests/test_pg_ledger_harness.py`
  - `.github/workflows/test.yml`
- Ngân sách diff: 260 dòng
- Lệnh kiểm:
  - `cd cong-no-web-handoff && {python} -m unittest discover -s tests -v`
  - `{python} -m py_compile cong-no-web-handoff/tools/test_pg_ledger_schema.py cong-no-web-handoff/tools/pg_ledger_verify.py cong-no-web-handoff/tools/pg_m1_verify.py`
- Cấm:
  - Đổi schema, migration, fixture nghiệp vụ, quy tắc tiền; chạy Docker/DDL/kết nối DB nào.
  - Thêm dependency, framework hay helper ngoài các file trên; refactor ngoài 4 điểm.
  - Ghi số liệu live hoặc hồ sơ ngoài Git vào repo.
- Khi cần vượt phạm vi: dừng, nêu câu hỏi trong báo cáo cuối.

## Hoàn tác

Revert commit; không đụng dữ liệu.

## Câu hỏi mở

- (chưa có)
