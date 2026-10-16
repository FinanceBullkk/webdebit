# Fixture P0: cấm ngày ghi sổ tương lai (FUTURE-01)

Trạng thái: ĐÃ CHỐT giao việc. Người dùng duyệt ngày 16/10/2026 trong chat, sau khi đọc review PR #13. Chỉ sửa fixture CI PostgreSQL trên dữ liệu giả; chưa có app, không mở ghi tiền thật.

## Đầu ra

Fixture ghi tiền P0 `tools/pg_versioned_approval_fixture.sql` từ chối revision có `posting_date` sau ngày hiện tại theo giờ Việt Nam. Việc chặn áp dụng ở ba bước: nộp revision, duyệt và ghi sổ. Ngày ghi sổ bằng hôm nay vẫn hợp lệ.

## Nguồn quyết định

- FUTURE-01 trong [sổ quyết định](../docs/decisions.md), người dùng chốt 16/10/2026: chặn ở cả bước nhập và bước duyệt; "hôm nay" theo Asia/Ho_Chi_Minh.
- Ledger hiện hành đã cài cùng chính sách này ở PR #13 bằng `ledger.business_today()`.

## Hành vi và bất biến

- Thêm hàm `p0_fixture.assert_posting_date_not_future(p_payload jsonb, p_stage text)`, viết theo mẫu `p0_fixture.assert_periods_open`. Hàm RAISE P0001 `posting date is in the future (<stage>)` khi `posting_date > (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`.
- Gọi hàm này ở ba chỗ:
  - `submit_revision`, sau `canonicalize_payload`, trước mọi INSERT.
  - `approve_revision`, cạnh `assert_periods_open(..., 'approval')`.
  - `post_revision`, cạnh `assert_periods_open(..., 'posting')`.
- Bị từ chối thì không tạo revision, approval hay posting nào; trạng thái proposal giữ nguyên.
- Không đặt cận dưới cho `posting_date`. Fixture P0 chưa có cutover; mốc cận dưới là CÒN MỞ.
- Không đổi quy tắc `warehouse_in_date` (OPENING-FINAL), canonical payload, hash nội dung, quyền hay cách tính tiền.

## Tiêu chí nghiệm thu

Thêm các case sau vào `tools/test_pg_versioned_approval.py`, theo kiểu case hiện có:

- [ ] Revision có `posting_date` = hôm nay theo giờ VN được nộp thành công.
- [ ] Revision có `posting_date` = ngày mai bị từ chối ở bước nộp, kèm thông điệp trên và không có revision mới.
- [ ] Bị từ chối ở bước duyệt: dùng một revision có `posting_date` tương lai đã nằm trong DB, giả lập revision được nộp dưới hàm cũ. Tạo bằng quyền owner trong harness, ví dụ `SET session_replication_role = replica` trong phiên superuser rồi INSERT hoặc UPDATE trực tiếp. Không thêm đường tắt nào vào fixture. Sau khi bị từ chối, trạng thái giữ nguyên.
- [ ] Bị từ chối ở bước ghi sổ: revision đã duyệt nhưng `posting_date` tương lai. Không có posting nào được tạo.
- [ ] Toàn bộ harness exit 0. Các case cũ vẫn pass; chúng đang dùng `posting_date` 2026-10-15, là ngày quá khứ nên vẫn hợp lệ.

## Phạm vi agent

Mục này là hợp đồng với agent thực hiện; `scripts/agent-run.ps1` đọc nó để kiểm diff.

- Agent: codex
- Được sửa:
  - `cong-no-web-handoff/tools/pg_versioned_approval_fixture.sql`
  - `cong-no-web-handoff/tools/test_pg_versioned_approval.py`
- Ngân sách diff: 140 dòng
- Lệnh kiểm:
  - `{python} cong-no-web-handoff/tools/test_pg_versioned_approval.py --report %TEMP%\codex-p0-future-posting-date.json`
  - `cd cong-no-web-handoff && {python} -m unittest discover -s tests`
- Cấm:
  - Sửa `pg_ledger_schema.sql`, `web/`, spec P0 hoặc tài liệu. `specs/p0-write-path/*` đang có thay đổi chưa commit của người dùng.
  - Thêm cận dưới hay cutover vào fixture P0; đổi `warehouse_in_date`, canonical payload, hash hay quyền.
  - Thêm hàm "set ngày giả" hay tham số thời gian vào fixture chỉ để test.
  - Thêm dependency, framework hay file mới.
  - Chạy DDL ngoài harness container, chạm `hao`, Sheet hay DB thật.
- Khi cần vượt phạm vi: dừng, không tự mở rộng; ghi câu hỏi ở mục "Câu hỏi mở" bên dưới.

## Hoàn tác

Revert commit. Chỉ đổi fixture CI.

## Bằng chứng

<Agent ghi lệnh đã chạy và kết quả. Reviewer kiểm thêm: harness mới chạy với fixture cũ phải fail ở case ngày mai.>

## Câu hỏi mở

- (chưa có)
