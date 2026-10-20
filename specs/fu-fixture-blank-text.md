# Fixture duyệt theo phiên bản: chặn trường bắt buộc chỉ toàn khoảng trắng

Trạng thái: ĐÃ CHỐT giao việc. Người dùng đồng ý ngày 16/10/2026 trong chat sau review chuỗi PR #1–#7. Chỉ sửa fixture PostgreSQL thử nghiệm, không phải schema production.

## Vấn đề

Trong `cong-no-web-handoff/tools/pg_versioned_approval_fixture.sql` (trên `main` tại `53d02c7`), các kiểm "trường bắt buộc không rỗng" dùng `btrim(x)`, mà `btrim` một tham số chỉ bỏ dấu cách U+0020. Chuỗi chỉ gồm tab, xuống dòng (`\t`, `\n`, `\r`) hoặc khoảng trắng Unicode khác vẫn qua kiểm. Ví dụ: `source_ref`/`evidence_ref` của xác nhận giá, `period_override_reason`/`period_override_evidence_ref` của xác nhận kỳ, `customer_id`, `reason`, nhãn cấu phần giá, và các CHECK `evidence_ref`, `approved_by`. Hậu quả: xác nhận giá/kỳ có thể được ghi dù chứng cứ bắt buộc thực chất trống, trái hợp đồng "đủ chứng cứ" (CHARGE-01). Resolver hiện vẫn chặn approval charge nên chưa dẫn tới posting, nhưng fixture không bảo vệ đúng điều nó tuyên bố.

## Hành vi và bất biến

- Mọi chỗ kiểm "không rỗng" trong fixture coi chuỗi chỉ gồm khoảng trắng (mọi ký tự khoảng trắng: dấu cách, tab, xuống dòng, CR, NBSP U+00A0 và các khoảng trắng Unicode) là rỗng. Dùng một hàm nhỏ trong schema `p0_fixture` (ví dụ `p0_fixture.is_blank(text)`) và thay toàn bộ các chỗ `btrim(...)` dùng cho mục đích này, kể cả CHECK.
- Giá trị hợp lệ có chữ thật vẫn giữ nguyên, không bị cắt hay đổi nội dung (không đổi canonical payload/hash).
- Không đổi quy tắc khác: trip key, xác nhận kỳ/giá, duyệt, posting, khóa, ngày ghi sổ.

## Tiêu chí nghiệm thu

- [ ] Trong `cong-no-web-handoff/tools/test_pg_versioned_approval.py`, thêm case: với từng trường bắt buộc nêu trên, giá trị `"\t"`, `"\n"`, `" \t\r\n "`, `" "` bị từ chối (không tạo xác nhận/approval/posting), và giá trị `" A "` vẫn được chấp nhận như trước.
- [ ] Các case hiện có vẫn PASS (CI job `pg18-versioned-approval-fixture` trên PR; máy local không có Docker).
- [ ] `{python} -m py_compile cong-no-web-handoff/tools/test_pg_versioned_approval.py` PASS.

## Phạm vi agent

- Agent: codex
- Review: sonnet medium
- Được sửa:
  - `cong-no-web-handoff/tools/pg_versioned_approval_fixture.sql`
  - `cong-no-web-handoff/tools/test_pg_versioned_approval.py`
- Ngân sách diff: 90 dòng
- Lệnh kiểm:
  - `{python} -m py_compile cong-no-web-handoff/tools/test_pg_versioned_approval.py`
- Cấm:
  - Đổi trip key, canonical payload/hash version, quy tắc duyệt/posting/khóa, schema `pg_ledger_schema.sql`.
  - Chạy Docker/PostgreSQL/kết nối DB nào; thêm dependency hay file mới.
  - Format lại file.
- Khi cần vượt phạm vi: dừng, nêu câu hỏi trong báo cáo cuối.

## Hoàn tác

Revert commit; fixture chỉ chạy trong container CI.
