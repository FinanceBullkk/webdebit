# Máy tự đối soát Sheet–web và tự sửa khi khớp

Trạng thái: ĐÃ CHỐT (người dùng, 4/11/2026, [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md))

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Chủ sổ (trên 40 tuổi, laptop 1280×720) mở tab Việc cần làm, mang theo ba câu hỏi: web có đúng với Sheet không; máy vừa tự sửa gì; còn gì mình phải quyết.

1. Đầu tab có một dòng: lần đối soát gần nhất lúc mấy giờ, bao nhiêu khách khớp và chiếm bao nhiêu phần trăm số nợ, máy vừa sửa bao nhiêu khách, bao nhiêu khách web đi trước Sheet, bao nhiêu khách cần xem. Xanh khi không còn gì phải xem; vàng khi có khách cần xem, lần chạy lỗi, hoặc kết quả đã cũ; đỏ khi máy ghi xong mà không khớp.
2. Bấm "Xem": danh sách các khách đó, khách cần xem trước, mỗi dòng có số lệch (web − Sheet, triệu), một câu kết luận và đường mở sổ.
3. Bảng việc bên dưới mặc định ẩn sổ đã khớp Sheet, có dòng báo đã ẩn bao nhiêu sổ và nút hiện lại. Chờ kiểm, số dư đầu, mặt hàng vẫn hiện.
4. Việc máy đã ghi hiện ở "Máy đã tự làm hôm nay" và trong Lịch sử từng sổ, người làm "Máy (theo Sheet)".

Không còn gì cần xem thì chủ sổ không phải làm gì.

## Đầu ra

- `tools/v7_reconcile_auto.py`: mỗi giờ từ 7 tới 22 giờ VN (timer `v7-reconcile-auto` trên `hao`) tải xlsx sổ gốc, làm sạch, so tổng từng khách, tự sửa khách lệch khi khớp đúng. Không có `--fix` thì chỉ báo sẽ ghi gì.
- `web/v7_sheet_fix.py`: gom việc thành nhóm, chọn tổ hợp, ghi bằng lệnh có sẵn.
- `reconcile.json` (mode 600, có tên khách và số tiền) và `reconcile-log.jsonl` (mỗi lượt một dòng, chỉ số đếm và tổng tiền) trong `/var/lib/webdebit-sheet-sync/`.
- `GET /api/v7/inbox` thêm `reconcile` và `sheet_matched` của từng sổ; tab Việc cần làm hiện kết quả.
- `v7_reconcile_sheet.py --can-du-months`: so từng tháng theo cách web tính ([`CAN-DU-01`](../docs/decisions/can-du-01.md)).

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

| Cần | Lấy từ | Ghi chú |
| --- | --- | --- |
| Tổng Sheet từng khách | `v7_export_clean.build_books` + `export`, rồi `v7_reconcile_sheet.read_sheet` | Đúng đường của đối soát chính thức; khách bị giữ như `--hold-out` |
| Tổng web từng khách | `get_ledger` qua `PsqlDirect`, `v7_reconcile_sheet.ledger` | Không đi qua HTTP nên không cần danh tính Tailscale |
| So tổng, so tháng | `v7_reconcile_sheet.reconcile` | So tháng dùng `can_du=True` |
| Hàng chờ phiếu, giá | `project_receipts`, `project_prices` trên bản chụp dựng từ **cùng bản tải** (`v7_price_snapshot.build_all`) | Tổng và việc cùng một trạng thái Sheet, nên phép khớp có nghĩa |
| Dòng chỉ có TỔNG, dòng không container, web đi trước | `v7_price_queue.classify` trả `SHEET_NO_PRICE`, `NO_CONTAINER` | Hàng chờ giá không hiện các loại này |
| Lệnh ghi | `record_receipt`, `delete_legacy_trip` (khoản thu sổ gốc, `XOA-THU-GOC-01`), `write_price_items`, `adjust_month`, `delete_month_adjustment`, `set_month_lock` | Không thêm hàm SQL |
| Phiếu không ngày đã ghi được nhận lại | Tham chiếu `Sheet #<dấu dòng>: …`, như `review_sheet_receipt` | Hàng chờ ghép bằng tiền tố này |
| Dòng không container đã ghi được nhận lại | Dòng điều chỉnh có ghi chú bắt đầu bằng `FEE_NOTE`, cùng tháng, cùng số | Dòng sổ gốc không container cùng tháng, cùng số cũng là đã có. Dòng điều chỉnh của máy mà Sheet không còn dòng tương ứng thành nhóm hủy (`delete_month_adjustment`) |
| Biết trước tổng đổi bao nhiêu | Chuyến: `đơn giá + phụ phí` trừ số đang tính (chưa có giá là 0). Dòng sổ gốc: `_change_legacy` tính lại `counted_vnd = đơn giá + phụ phí`, xóa khoản thu cộng lại đúng `counted_vnd` | Khoản thu có `counted_differs` thì không tính trước được, không vào nhóm |

Đo trên `hao` lúc thiết kế (chỉ đọc): một lượt khoảng 9 phút ở `Nice=10` (làm sạch 4 phút, đọc giá và phiếu 2,5 phút, đọc 236 sổ 1,5 phút), bộ nhớ khoảng 125 MB. Bản giả và ảnh chụp không dùng số khách thật.

## Giao tiếp frontend–backend (bước 5, khi có)

`GET /api/v7/inbox` thêm:

```json
{"reconcile": {"version": 1, "checked_at": "2026-11-04T08:05:00+07:00", "mode": "fix", "counts": {"KHOP": 233, "LECH_TONG": 3},
  "total": 236, "matched_web_vnd": "…", "all_web_vnd": "…", "matched_ids": [1, 3],
  "customers": [{"customer": "…", "customer_id": 2, "status": "LECH_TONG", "reason": "NO_EXACT_FIX", "sheet_total_vnd": "…",
                 "web_total_vnd": "…", "difference_vnd": "…", "web_ahead_vnd": "0",
                 "groups": [{"kind": "receipts_edited", "month": "2026-07", "count": 8, "delta_vnd": "-117", "chosen": false}]}],
  "months_differ": [], "last_error": {"at": "…", "reason": "HTTPError"}},
 "books": [{"customer_id": 1, "sheet_matched": true}]}
```

- `reconcile` là `null` khi chưa có lượt nào hoặc file hỏng; hộp việc vẫn chạy.
- `customers` gồm khách chưa khớp và khách máy vừa sửa. Tiền là chuỗi số nguyên; chưa biết là `null`, không phải 0.
- `reason`: `FIXED`, `WOULD_FIX`, `WEB_AHEAD`, `NO_EXACT_FIX`, `SHEET_SHUFFLED`, `AMBIGUOUS_FIX`, `NOTHING_TO_WRITE`, `TOO_MANY_GROUPS`, `TOO_MANY_DIFFERENT`, `WRITE_ERROR`, `CHECK_ERROR`, `VERIFY_FAILED`, `HELD`, `CHI_CO_SHEET`, `CHI_CO_WEB`, `THIEU_SO`. `FIXED` với `status` `LECH_TONG` là đã sửa, phần còn lại là web đi trước Sheet.
- `last_error`: lần chạy mới nhất hỏng, phần còn lại là kết quả lần đạt trước.
- `sheet_matched`: sổ có trong `matched` của lượt gần nhất, tổng hiện tại bằng tổng lúc đó, và không còn dòng giá khác giá Sheet (`prices_conflict`).

## Nguồn quyết định

- [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md), [`SONG-SONG-01`](../docs/decisions/song-song-01.md), [`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md), [`MAY-KHOA-01`](../docs/decisions/may-khoa-01.md), [`VCL-GIU-01`](../docs/decisions/vcl-giu-01.md), [`XOA-THU-GOC-01`](../docs/decisions/xoa-thu-goc-01.md), [`CAN-DU-01`](../docs/decisions/can-du-01.md).
- CÒN MỞ: cách chuyển hẳn khi Sheet vẫn là nơi nhập (mục F4 của [checklist](../docs/song-song-checklist.md)).

## Hành vi và bất biến

- Chỉ ghi khi đúng một tổ hợp nhóm có tổng đổi bằng đúng `tổng Sheet + web đi trước − tổng web`. Lệch 1 đồng là không ghi. Nhóm không đổi tiền không ghi.
- Tháng có đơn giá đổi chỗ vòng tròn (`shuffled_months`) không có nhóm giá: khớp tổng không phân biệt được giá của container nào, nên không ghi và báo `SHEET_SHUFFLED`. Kiểu này chỉ bắt được khi web đã có giá để so.
- Không ghi Sheet. Không đổi hàm SQL, quyền, luật phân bổ. Mọi lệnh có `expected_version`: người vừa sửa sổ thì lệnh lỗi `STALE_LEDGER`, lượt sau tính lại.
- Khóa chống ghi trùng gắn phiên bản sổ lúc bắt đầu lượt; phiếu đã ghi thì hàng chờ đã ghép, không chọn lại.
- Tháng khóa: mở, ghi, khóa lại; lệnh lỗi vẫn khóa lại; API tắt giữa chừng thì lượt nền của API khóa lại sau 10 phút (`machine_left_open`).
- Stdout không có tên khách hay số tiền. Bản tải và bản làm sạch nằm trong thư mục tạm, xóa ngay sau lượt.
- Lần chạy lỗi không xóa kết quả cũ, chỉ thêm `last_error`; unit thoát khác 0.
- VND nguyên chính xác; NULL không phải 0.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_sheet_fix.py`: nhóm việc, số tổng đổi, chọn tổ hợp (lệch 1 đồng, nhiều tổ hợp, nhóm không đổi tiền), đơn giá đổi chỗ, thứ tự ghi, tháng khóa, phiếu không ngày ghi xong rời hàng chờ.
- [x] `tests/test_v7_reconcile_auto.py`: cả lượt từ xlsx giả: khớp, chỉ báo, sửa rồi khớp, không khớp thì không ghi, lỗi ghi, web đi trước, khách bị giữ, quá nhiều khách lệch, lần chạy lỗi giữ kết quả cũ.
- [x] `tests/test_v7_reconcile_sheet.py`: `--can-du-months`.
- [x] `tests/test_v7_inbox.py`: `reconcile`, `sheet_matched`, file hỏng.
- [x] `preview/test-viec-can-lam-table-browser.js`: dải kết quả, thứ tự danh sách, ẩn và hiện sổ đã khớp, sổ ẩn không bị chọn ngầm, các trạng thái xanh, vàng, đỏ, lỗi, cũ, chưa có lượt nào; không tràn ngang ở 1280.
- [ ] Thử trên bản sao DB của `hao`: tổng khách sửa khớp đúng, khách khác không đổi, mọi tháng máy mở đã khóa lại, chạy lại không ghi thêm, checker đạt.
- [ ] Bật trên `hao`, đối soát chính thức sau lượt đầu cho kết quả như dự kiến.
- [ ] Chủ sổ tự đi hết luồng trên `hao`: đọc dải, mở danh sách, mở sổ, soát phiếu máy ghi.
