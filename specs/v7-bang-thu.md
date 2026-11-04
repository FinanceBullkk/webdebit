# Bảng thu: tiền về theo ngày, gom mọi sổ

Trạng thái: ĐÃ CHỐT (người dùng, 4/11/2026, [`BANG-THU-01`](../docs/decisions/bang-thu-01.md), [`BANG-THU-02`](../docs/decisions/bang-thu-02.md))

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Người mở: sếp, chủ sổ, người đòi nợ (trên 40 tuổi, Chrome thấy khoảng 1280×560). Chỉ xem, không ghi. Câu hỏi mang tới, theo thứ tự:

1. Hôm nay thu được bao nhiêu, ai trả?
2. Tháng này thu được bao nhiêu, ai trả bao nhiêu?
3. Một khoản cụ thể trừ nợ tháng nào, xem ở đâu?
4. Tiền về tháng này trừ vào nợ những tháng nào?
5. Mặt hàng nào thu được bao nhiêu?
6. Tháng trước, tháng khác tiền về bao nhiêu?

Luồng:

1. Mở mục Bảng thu ở menu trái, hoặc bấm "Bảng thu" ở thẻ Thu tháng của Tổng quan. Mặc định là tháng hiện tại, xem theo ngày.
2. Nhìn thứ nhất: số tháng, số hôm nay và chip cảnh báo khi Sheet còn phiếu chưa ghi. Thứ hai: dải ngày, bấm một cột thì tới đúng ngày đó. Thứ ba: danh sách phiếu mới nhất trên cùng, gom theo ngày, mỗi ngày có tổng.
3. Bấm một dòng: mở sổ khách đúng tháng chứa khoản đó. Sửa hay hủy đều làm ở sổ.
4. Bấm tab ngay trên bảng để đổi cách xem (xem bảng dưới). Chọn mặt hàng ở bộ lọc thì số tháng, số hôm nay, dải ngày và bảng cùng lọc theo.
5. Đổi tháng bằng ‹ › hoặc ô chọn tháng ở thanh đầu. Quay lại từ sổ thì giữ đúng tháng, tab và bộ lọc. Gửi link cho người khác thì thấy đúng như vậy.

Không có điều kiện bị chặn vì trang không ghi gì.

## Đầu ra

Trang `/bang-thu.html`, mục thứ tư trên menu trái, đọc `GET /api/v7/receipt-book`. Tháng tính theo **ngày tiền về**. Khoản không rõ ngày nằm nhóm riêng, không cộng vào tổng tháng.

## Các cách xem (BANG-THU-02)

Địa chỉ trang: `?month=YYYY-MM&xem=<tab>&mh=<mặt hàng>`. Tab mặc định và bộ lọc trống không ghi lên địa chỉ.

| Tab (`xem`) | Trả lời | Gom từ | Một dòng là |
| --- | --- | --- | --- |
| Theo ngày (mặc định) | Ngày nào thu bao nhiêu, ai trả | `days[]`, `undated[]` | Một phiếu. Bấm mở sổ ở tháng chứa khoản đó |
| Theo khách (`khach`) | Cả tháng ai trả bao nhiêu | `customers[]`, giữ thứ tự server | Một sổ |
| Theo mặt hàng (`mat-hang`) | Mặt hàng nào thu được bao nhiêu | `customers[]` ghép mặt hàng của `GET /api/v7/customers` | Nhóm mặt hàng, trong đó từng sổ. Nhóm nhiều tiền trước |
| Theo tháng nợ (`thang-no`) | Tiền về tháng này trừ vào nợ tháng nào | `days[].rows[]`, `undated[]` | Nhóm tháng nợ, trong đó từng sổ. Tháng cũ trước, Ứng trước cuối |
| 12 tháng (`12-thang`) | Tiền về từng tháng | `months[]` của tháng đang xem, 12 tháng liền tới tháng hiện tại | Một tháng. Bấm mở Theo ngày của tháng đó |

Quy tắc gom:

1. **Mặt hàng** dùng `DashboardModel.commodityKey` như bộ lọc Tổng quan: chỉ sầu riêng tách cảng/bộ; thiếu mặt hàng, hoặc sầu riêng chưa ghi cảng/bộ, là "Chưa phân loại". Không đọc được `GET /api/v7/customers` thì ẩn bộ lọc, tab Theo mặt hàng báo rõ, các tab khác vẫn đúng số.
2. **Tháng nợ:** phiếu web đọc `allocations[]`, `kind = advance` vào nhóm Ứng trước. Dòng Sheet không có phân bổ riêng nên đọc `book_month`. Phiếu chia nhiều tháng tách đúng phần tiền vào từng nhóm và được đếm ở mỗi nhóm. Nếu phân bổ không đủ số tiền của phiếu, phần còn lại vào nhóm "Chưa phân bổ" để tổng vẫn khớp. Số của phiếu web có thể đổi khi sổ được điều chỉnh, vì phiếu được phân bổ lại theo nợ cũ trước.
3. **Đẳng thức:** ở mọi tab và mọi bộ lọc, tổng các nhóm bằng số tháng đang hiện; phần không rõ ngày tính riêng, không cộng vào.
4. **Bộ lọc** áp lên mọi tab trừ 12 tháng, vì `months[]` chỉ có tổng từng tháng. Chip phiếu Sheet chờ, phiếu đã hủy và cấn trừ cũng lọc theo sổ thuộc mặt hàng đó.
5. **Thanh "Phần trong tháng":** nhóm và sổ trong cùng bảng dùng chung một thước, nên thanh so được với nhau.

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

Đo trên `hao` 4/11/2026, phiên chỉ đọc, chỉ số tổng hợp.

| Cần | Có sẵn | Ghi chú |
| --- | --- | --- |
| Phiếu web | `sokhach.receipt` (một bảng chung, có `customer_id`) | Ngày, hình thức, tham chiếu, số tiền. 37 phiếu chưa hủy lúc đo, tăng dần vì máy và người đang ghi |
| Khoản thu trước mốc | `sokhach.legacy_row` kind `receipt`: 1.227 dòng, 354,64 tỷ | Tổng dòng bằng `source_receipt_vnd` ở 877/877 khách-tháng, kể cả sau khi trừ 2 khoản đã xóa |
| Ngày của khoản Sheet | `display.raw_date`, chữ tự do | 719 dòng đọc được ngày theo luật `pay_date` của hàng chờ phiếu; 497 dòng (103,56 tỷ, đo trên bản sao 4/11/2026) không đọc được hoặc ngày vô lý, thêm 15 dòng số tiền 0 |
| Trừ nợ tháng nào | `v_receipt_line_active` với phiếu web; `debt_month` với dòng Sheet | Dòng Sheet không có phân bổ riêng: hiện tháng của khối |
| Cấn trừ | `offset_pair`; phiếu đích nằm trong `receipt` | Không phải tiền mới vào. 0 khoản đang có hiệu lực lúc đo |
| Phiếu Sheet chưa ghi | `GET /api/v7/inbox`: `books[].receipts`, `sheet_matched` | Như tab Đòi nợ |
| Tên khách | `GET /api/v7/customers` + `customerLabels` | Tên trong hàm mới chỉ để dự phòng |

**Thiếu:** không có đường đọc phiếu qua nhiều sổ. `get_ledger` theo từng sổ tốn khoảng 0,75 giây mỗi sổ. Cần một hàm SQL đọc mới.

**Phát hiện quyết định thiết kế:** Sheet ghi khoản thu ở khối tháng nợ, còn ngày tiền về thường rơi vào tháng sau. Trong 719 dòng có ngày: 105 đúng tháng của khối, 587 ở tháng sau, 27 ở tháng trước. Ví dụ T9/2026: sổ ghi Đã thu 3,75 tỷ, tiền về trong T9 khoảng 24 tỷ. Vì vậy tổng tháng của Bảng thu **khác có chủ đích** với "Đã thu" của sổ ở các tháng có dòng Sheet.

Khối lượng: khoảng 3–4 phiếu mỗi ngày, nhiều nhất khoảng 100 phiếu một tháng, nên danh sách không cần phân trang hay thu gọn.

## Giao tiếp frontend–backend (bước 5, khi có)

`GET /api/v7/receipt-book` (tháng hiện tại giờ VN) hoặc `GET /api/v7/receipt-book?month=YYYY-MM-01`. Tham số khác hoặc không phải ngày đầu tháng: 400 `INVALID_MONTH`. Quyền: mọi người vào được app, hàm cấp cho `sokhach_app` và `sokhach_reader`. Tích hợp thật qua `sokhach.get_receipt_book(date)`.

```jsonc
{
  "month": "2026-11-01", "as_of": "2026-11-04", "today_month": "2026-11-01",
  "months": [{"month": "2026-11-01", "total_vnd": "…", "count": 6, "undated_vnd": "0", "undated_count": 0}],  // mới trước
  "summary": {"total_vnd": "…", "count": 6, "customers": 5, "undated_vnd": "0", "undated_count": 0,
              "today_vnd": "…", "today_count": 2, "has_sheet": false},
  "days": [{"date": "2026-11-04", "total_vnd": "…", "count": 2, "rows": [ROW]}],                                // mới trước
  "undated": [ROW],
  "customers": [{"customer_id": 7, "name": "…", "total_vnd": "…", "count": 2, "undated_vnd": "0", "undated_count": 0,
                 "last_date": "2026-11-04", "book_month": "2026-11-01"}],                                        // nhiều tiền trước
  "offsets": [{"id": 1, "date": "…", "amount_vnd": "…", "source_customer_id": 1, "source_name": "…",
               "target_customer_id": 2, "target_name": "…"}],
  "voided": [{"pid": "PH-1", "customer_id": 7, "name": "…", "date": "…", "amount_vnd": "…", "voided_on": "…", "void_reason": "…"}]
}
// ROW: {"source": "web"|"sheet", "id": 1, "pid": "PH-1"|null, "customer_id": 7, "name": "…", "date": "2026-11-04"|null,
//       "book_month": "2026-11-01", "amount_vnd": "…", "method": "THU TIỀN"|null, "note": "…"|null,
//       "allocations": [{"month": "2026-09-01", "kind": "debt"|"advance", "amount_vnd": "…"}]}
```

Số tháng khi không lọc lấy nguyên từ SQL. Lọc, gom nhóm, tổng phiếu Sheet chưa ghi và thanh tỷ lệ tính ở `preview/bang-thu-model.js` bằng BigInt, có test riêng (ARCH-03); `preview/bang-thu-ui.js` chỉ định dạng. Năm cách xem không cần API mới.

## Nguồn quyết định

- [`BANG-THU-01`](../docs/decisions/bang-thu-01.md): bố cục và cách tính tháng.
- [`BANG-THU-02`](../docs/decisions/bang-thu-02.md): năm cách xem, bộ lọc mặt hàng, ngôn ngữ trình bày.
- [`DA-THU-01`](../docs/decisions/da-thu-01.md): Đã thu của sổ, không đổi.
- [`THU-SHEET-01`](../docs/decisions/thu-sheet-01.md), [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md): nguồn phiếu từ Sheet và phiếu máy đặt ngày cuối tháng khối.
- [`XOA-THU-GOC-01`](../docs/decisions/xoa-thu-goc-01.md): khoản thu sổ gốc đã xóa.
- [`UX-NEN-01`](../docs/decisions/ux-nen-01.md) L3: số phải nói rõ còn việc chờ nào có thể làm đổi số.

## Hành vi và bất biến

1. **Ngày của dòng:** phiếu web lấy `receipt.date`. Dòng Sheet đọc `display.date`, không có thì đọc `raw_date` bằng `_legacy_pay_date`, cùng luật với `pay_date` (số serial, ISO đầu chuỗi, dd/mm/yyyy ở đầu hoặc giữa ghi chú).
2. **Không rõ ngày** (`date` null), nằm ở tháng của khối, không cộng vào `total_vnd` tháng:
   - không đọc được ngày;
   - ngày sau lúc nạp sổ hoặc sau hôm nay (5 dòng, ví dụ năm 2028);
   - ngày trước tháng của khối hơn 12 tháng (ví dụ năm 2020);
   - phiếu đặt ngày cuối tháng khối vì Sheet không ghi ngày: tham chiếu kết thúc bằng ` · ngày theo cuối tháng khối Sheet` (máy) hoặc ` (ngày tượng trưng)` (ghi tay 4/11/2026, 6 phiếu, 2,39 tỷ).
3. **Không tính:** phiếu đã hủy (liệt kê riêng khi bấm Xem), khoản thu sổ gốc đã xóa, cấn trừ hai đầu (liệt kê riêng). Dòng Sheet số tiền 0 (15 dòng, ô công thức trống) không liệt kê.
4. **Đẳng thức cả đời:** tổng `total_vnd + undated_vnd` của mọi tháng, cộng mọi sổ, bằng tổng `received_vnd` của `get_ledger`. Dòng chỉ đổi tháng, không thêm bớt tiền.
5. **Đẳng thức tháng hiện tại:** khi tháng không có khối Sheet, `total_vnd + undated_vnd` bằng `this_month.received_vnd` của Tổng quan.
6. Không đổi luật tiền, phân bổ, số nợ hay dữ liệu. Migration chỉ thêm hai hàm đọc.
7. Ghi chú đã bỏ tiền tố kỹ thuật (`Sheet:`, `Sheet #<dấu dòng>:`) và đuôi của máy; ngày đứng một mình trùng ngày của dòng thì không lặp lại, số serial ngày của Sheet không hiện nguyên số. Không hiện dấu dòng lên màn.

## Tiêu chí nghiệm thu

- [x] `test_pg_v7_backend.py` case `BANG-THU.01`: mọi quy tắc ngày, loại trừ và hai đẳng thức; `_legacy_pay_date` cho cùng kết quả với `pay_date` trên bộ ví dụ.
- [x] Case `CSM.03` và `test_pg_v7_grants.py`: migration chạy hai lượt, catalog bằng khởi tạo mới; app và reader gọi được `get_receipt_book`, không gọi được `_legacy_pay_date`.
- [x] `test_v7_bang_thu.py`: route, tháng sai bị từ chối, trang và tài nguyên được phục vụ, chuỗi đuôi của máy khớp `v7_sheet_fix`.
- [x] `test-bang-thu-browser.js`: đủ trạng thái tải, trống, lỗi, thử lại; gom theo ngày, tổng ngày; Theo khách; đổi tháng và giữ qua Back; bấm dòng mở đúng sổ, đúng tháng; nhóm không rõ ngày; cảnh báo phiếu chờ; menu sáu mục không tràn ở 1280×560; không cuộn ngang ở 1280.
- [x] `test-bang-thu-model.js` (BANG-THU-02): lọc mặt hàng, gom mặt hàng, gom tháng nợ, 12 tháng, dải ngày, phiếu chờ; tổng các nhóm bằng tổng tháng ở mọi cách gom.
- [x] `test-bang-thu-browser.js` (BANG-THU-02): năm tab và địa chỉ trang; bộ lọc lọc cả số tháng, hôm nay, dải ngày, bảng; không đọc được mặt hàng; bấm dải ngày tới đúng ngày; chip không rõ ngày từ tab khác; bấm tháng ở 12 tháng; số lớn rút gọn và số đúng ở chú thích.
- [x] Trên `hao`: tổng T11 của trang bằng "Thu tháng" ở Tổng quan; đẳng thức cả đời đúng trên dữ liệu thật ([nhật ký](../docs/deploys/2026-11-04-bang-thu.md)).
- [ ] Sau khi merge, trên `hao`, chỉ đọc: năm tab chạy không lỗi; tổng các nhóm ở Theo mặt hàng và Theo tháng nợ bằng tổng tháng trên dữ liệu thật.
- [ ] Người dùng tự mở trang trên `hao` và xác nhận.

## Phạm vi

- BANG-THU-01 được sửa: `tools/v7_backend_functions.sql`, migration mới `2026-11-04-v7-bang-thu.sql`, `tools/v7_post_deploy_check.sql`, harness và grants trong `tools/`, `web/v7_api_tables.py`, `web/v7_api_validate.py`, `web/v7_ledger_api.py`, `web/v7_presence.py`, `preview/bang-thu.*`, `preview/app-nav.*`, `preview/presence.js`, menu của `so-khach-v7-live.html` và `so-khach-v7-priority.css`, thẻ Thu tháng của `dashboard-v7.js`, tài liệu quyết định và runbook.
- BANG-THU-02 được sửa: `preview/bang-thu*`, `preview/test-bang-thu-*`, `preview/data-tip.js` mới cùng chỗ gọi trong `dashboard-v7.{html,js}`, chú thích trong `cong-no-theme.css` và `dashboard-v7.css`, `tests/test_v7_bang_thu.py`, spec và quyết định.
- Cấm: đổi hàm ghi, view nợ, bảng tiền; nạp dữ liệu; ghi Sheet.

## Hoàn tác

Revert PR. BANG-THU-02 không có migration. BANG-THU-01 thêm DB: `DROP FUNCTION sokhach.get_receipt_book(date), sokhach._legacy_pay_date(text);` dưới `sokhach_owner`. Không có dữ liệu mới.

## Bằng chứng

FinanceBullkk/webdebit#296, FinanceBullkk/webdebit#299; nhật ký [đợt 1](../docs/deploys/2026-11-04-bang-thu.md), [đợt 2](../docs/deploys/2026-11-04-bang-thu-2.md). BANG-THU-02: PR của nhánh `feat/bang-thu-view` và lượt `Deploy hao` sau khi merge.

## Câu hỏi mở

- CÒN MỞ: gần 500 dòng Sheet không rõ ngày có đáng cho người bổ sung ngày không. Hiện để nguyên, không đoán.
- CÒN MỞ: đối chiếu sao kê ngân hàng ([`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md)) có thể dựng trên bảng này sau.
- CÒN MỞ: phiếu nhãn `KHÁC` có thể không phải tiền thật (ví dụ khoản giảm bảo hiểm ghi ngày 4/11/2026). Hiện vẫn cộng để khớp "Đã thu" và Tổng quan, nhãn hiện ở cột Ghi chú. Dòng Sheet cũ loại này không phân biệt được.
