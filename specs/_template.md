# <Tên thay đổi>

Trạng thái: ĐỀ XUẤT | ĐÃ CHỐT (ai, ngày, phạm vi)

## Người dùng và luồng (bước 1, bắt buộc với frontend)

<Người thao tác (vai trò), bối cảnh thật, luồng sử dụng từng bước, kết quả, điều kiện bị chặn. Theo [UX](../docs/ux-guidelines.md); điều chưa biết ghi CÒN MỞ và hỏi người dùng, không tự giả định.>

## Đầu ra

<Kết quả quan sát được khi xong; một đoạn ngắn.>

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

<Trường dữ liệu, hàm/API có sẵn, câu thông báo hiện có, dữ liệu fixture/thật sẽ hiện trên màn hình, phần dùng được và phần còn thiếu. Mockup lấy số liệu từ đây.>

## Giao tiếp frontend–backend (bước 5, khi có)

<Hàm/API, tham số, giá trị trả về, lỗi và câu thông báo, quyền; nêu rõ fixture hay tích hợp.>

## Nguồn quyết định

- <Link `docs/decisions.md`/`docs/business-rules.md`; ghi CÒN MỞ nếu chưa chốt.>

## Hành vi và bất biến

- <Quy tắc phải giữ: VND nguyên, NULL khác 0, không cộng lại lịch sử trong opening...>

## Tiêu chí nghiệm thu

- [ ] <Test/lệnh cụ thể và kết quả mong đợi>
- [ ] <Frontend, bước 7: bàn phím/focus, nhập sai, bấm lặp, tải chậm/mất mạng, thiếu quyền — theo phạm vi tác động>
- [ ] <Frontend, bước 8: người dùng tự đi hết luồng trên bản thử và xác nhận>

## Ảnh chụp giao diện (tùy chọn, khi có giao diện)

Kịch bản để script chụp giao diện thật trước/sau thay đổi cho reviewer, theo [multi-agent](../docs/multi-agent.md#ảnh-chụp-giao-diện). Mỗi trạng thái ứng với một board mockup; thử bằng `-Step capture` trước khi giao agent.

```json
{
  "page": "cong-no-web-handoff/preview/customer-ledger-workbench.html",
  "viewports": [[1280, 720]],
  "states": [
    {"name": "1-ten-trang-thai", "board": "<tên board mockup>", "note": "<người dùng đang làm gì>",
     "shot": "#month-2026-03",
     "steps": [{"click": "#month-2026-03 [data-action=\"open-editor\"]"}]}
  ]
}
```

## Phạm vi agent

Mục này là hợp đồng với agent thực hiện; `scripts/agent-run.ps1` đọc nó để kiểm diff.

- Agent: claude (từ 29/10/2026 theo `CLAUDE-ALL-01`)
- Review (model Claude review chốt, effort tùy chọn; thiếu dòng = opus): opus | sonnet medium — opus cho ghi tiền/phân bổ/opening/quyền
- Được sửa:
  - `đường/dẫn/file.py`
  - `tests/test_file.py`
- Ngân sách diff: 200 dòng
- Lệnh kiểm (script chạy từ gốc worktree bằng cmd.exe; `{python}` là venv của checkout chính):
  - `npm run test:unit`
  - `cd cong-no-web-handoff && {python} -m unittest discover -s tests -v`
- Cấm:
  - Thêm dependency, framework, layer hoặc abstraction mới không có trong spec.
  - Refactor/đổi tên ngoài file được sửa; "dọn dẹp" ngoài yêu cầu.
  - Đổi schema, trường tiền, quyền, quy tắc nghiệp vụ; chạy DDL/import/deploy; chạm dữ liệu thật.
- Khi cần vượt phạm vi: dừng, không tự mở rộng; ghi câu hỏi ở mục "Câu hỏi mở" bên dưới.

## Hoàn tác

<Revert commit/PR; không đụng dữ liệu.>

## Bằng chứng

<Revision, lệnh đã chạy, kết quả; phân biệt fixture / tích hợp / live.>

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
