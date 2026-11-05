# Đối soát biết tab Sheet vừa sửa, tra lịch sử sửa

Trạng thái: ĐÃ CHỐT (Claude theo ủy quyền của người dùng, 5/11/2026, [`SHEET-LOG-01`](../docs/decisions/sheet-log-01.md))

## Người dùng và luồng (bước 1, bắt buộc với frontend)

**Chủ sổ** (trên 40 tuổi, laptop 1280×720) mở tab Việc cần làm, hỏi: web có đúng với Sheet không, còn gì mình phải quyết. Vấn đề hiện tại: người nhập đang gõ dở trên một tab thì lượt đối soát báo "1 khách cần xem" và dải chuyển vàng, chủ sổ mở ra chỉ thấy "chưa đọc được". Một giờ sau tự hết. Lúc đo 5/11/2026, khách duy nhất đang báo như vậy có lần sửa tab 4 phút trước lúc máy tải bản Sheet.

1. Không còn gì khác: dải không vàng, có thêm chữ "1 khách Sheet vừa sửa, chờ lượt sau". Chủ sổ không phải làm gì.
2. Bấm "Xem": dòng khách đó nói "Tab này vừa được sửa lúc 11:15, máy xem lại ở lượt sau." rồi tới kết luận của máy, xếp sau các khách cần xem thật.
3. Khách cần xem thật: kết luận như cũ, cuối câu thêm "Sheet sửa lần cuối lúc 14:20 ngày 03/11." để biết lệch có mới không.
4. Lượt sau tab đã yên mà vẫn lệch: thành "cần xem" như thường.

Thay đổi nhỏ trên một dải đã có: thêm chữ, không thêm khối, không đổi bố cục, nên không cần hai phương án (`thiet-ke-ux` bước 2).

**Admin hoặc Claude** điều tra một khách lệch: chạy `v7_sheet_log.py --tab "<tab>"` trên `hao`, thấy từng lần sửa với giờ, ô, cũ → mới.

## Đầu ra

- `tools/v7_sheet_log.py`: đọc đuôi log, bỏ cột nội dung; lệnh tra tay.
- `v7_reconcile_auto.py`: cuối mỗi lượt đọc log, ghi `sheet_last_edit_at` và `sheet_editing` vào khách chưa khớp, `edit_log` vào kết quả.
- Dải và danh sách đối soát ở Việc cần làm hiện theo hai trường đó.
- Biến `WEBDEBIT_EDIT_LOG_ID`; không đặt thì mọi thứ như cũ, `edit_log.status` là `OFF`.

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

| Cần | Lấy từ | Ghi chú |
| --- | --- | --- |
| Lần sửa cuối từng tab | Tab `EVENTS` của file log, cột A:J, dòng `EDIT` | Cột K là nội dung: dòng SNAPSHOT tới 20.000 ký tự/ô, 31 dòng cuối đo được khoảng 714 KB, nên không đọc |
| Giờ tải bản Sheet | `now_vn()` ngay đầu `run()` | Bản tải chỉ cũ hơn log, không mới hơn |
| Tên tab ↔ khách | `tab_key` so bằng `' '.join(split())`, cùng cách với `rec.name` | Tên tab đổi hoặc sổ tên khác tab thì không có giờ sửa, khách vẫn hiện như trước |
| Quyền đọc | Tài khoản dịch vụ, scope `spreadsheets.readonly` như runner | File log chỉ chia sẻ cho chủ file: phải chia sẻ quyền xem cho tài khoản dịch vụ |
| Log còn sống | Dòng `INVENTORY` quét bù hằng ngày | Quá 26 giờ không có dòng nào là `STALE` |
| Dải và danh sách | `reconcileHtml`, `reconcileRowText` ở `preview/viec-can-lam-inbox.js` | Dùng chữ và kiểu sẵn có của dải, không thêm CSS |

Đo từ log thật (chỉ đọc, số đếm): log có 5.109 dòng, 889 lần sửa trên 49 tab từ 21/10 tới 5/11. Ngày đông nhất khoảng 1.500 dòng cả loại, nên 3.000 dòng cuối đủ cho hơn một ngày.

## Giao tiếp frontend–backend (bước 5, khi có)

`GET /api/v7/inbox` trả nguyên `reconcile.json`, thêm:

```json
{"reconcile": {"edit_log": {"status": "OK", "last_event_at": "2026-11-05T11:30:24+07:00"},
  "customers": [{"customer": "…", "status": "LECH_TONG", "reason": "NO_EXACT_FIX",
                 "sheet_last_edit_at": "2026-11-05T11:15:35+07:00", "sheet_editing": true}]}}
```

- `edit_log.status`: `OK`, `STALE`, `UNAVAILABLE` (kèm `reason` là mã lỗi), `OFF`. Màn không hiện trường này: chủ sổ không làm được gì với nó. Bản `reconcile.json` cũ không có trường nào ở trên thì màn hiện như trước.
- `sheet_last_edit_at`: chỉ có ở khách chưa khớp và tab có trong phần log đã đọc. Không có là chưa biết, không phải chưa từng sửa.
- `sheet_editing`: `true` hoặc không có.

## Nguồn quyết định

- [`SHEET-LOG-01`](../docs/decisions/sheet-log-01.md), [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md), [`sheet-capture`](sheet-capture.md).

## Hành vi và bất biến

- Log không ảnh hưởng tiền: không đổi nhóm việc, tổ hợp, lệnh ghi, `status`, `reason`, số lệch. Tab vừa sửa mà có đúng một tổ hợp khớp tổng thì máy vẫn ghi.
- Chỉ đánh dấu `sheet_editing` với `NO_EXACT_FIX`, `NOTHING_TO_WRITE`, `AMBIGUOUS_FIX`, `SHEET_SHUFFLED`, `TOO_MANY_GROUPS`, `HELD`. `VERIFY_FAILED`, `WRITE_ERROR`, `CHECK_ERROR`, `TOO_MANY_DIFFERENT`, `BOOK_OVERLAP` vẫn cần người dù tab đang sửa.
- Đọc log lỗi (quyền, hết giờ, tiêu đề đổi) không làm hỏng lượt: chỉ `edit_log.status = UNAVAILABLE` và một dòng journal có mã lỗi.
- Đọc cuối lượt, nên lần sửa trong lúc lượt chạy cũng tính.
- Tiêu đề cột khác `CAPTURE_HEADERS` thì báo `EDIT_LOG_FORMAT`, không đoán cột.
- Chỉ gọi `GET`. Không ghi file log, không ghi Sheet.
- Stdout và `reconcile-log.jsonl` chỉ có trạng thái và số đếm, không có tên khách hay số tiền.
- ID file log chỉ nằm trong biến môi trường, không vào repo.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_sheet_log.py`: đọc đúng đuôi, không đọc cột K; tiêu đề đổi, thiếu tab, ID lạ; lần sửa cuối từng tab; `STALE`; biên đúng 15 phút; lý do không được hạ mức; tra một tab chỉ tải nội dung dòng cần xem.
- [x] `tests/test_v7_reconcile_auto.py`: chưa cấu hình là `OFF`; tab vừa sửa được đánh dấu mà kết luận giữ nguyên; lần sửa cũ chỉ là thông tin; tab vừa sửa không chặn tổ hợp khớp đúng; log lỗi không hỏng lượt.
- [x] `preview/test-viec-can-lam-table-browser.js`: dải không vàng, không đếm "cần xem"; chữ dòng; thứ tự; web đi trước không thêm giờ sửa; không tràn ngang.
- [ ] Trên `hao`: sau khi chia sẻ log và đặt biến, một lượt có `edit_log.status = OK`, giờ sửa khớp log.
- [ ] Chủ sổ gặp một ca thật và thấy chữ hiểu được.

## Hoàn tác

Bỏ biến `WEBDEBIT_EDIT_LOG_ID`: lượt sau là `OFF`, màn như cũ. Revert PR nếu muốn gỡ mã. Không đụng dữ liệu.
