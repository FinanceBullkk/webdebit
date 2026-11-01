# Hộp ngoại lệ P2: ghi phiếu thu từ Sheet ngay tại hộp, Đòi nợ hỏi lại trước khi copy số có thể sai

Trạng thái: ĐỀ XUẤT (Claude, 1/11/2026). Giai đoạn P2 của [UX bước 03](../docs/ux-buoc-03-luong-thao-tac.md) mục 7, theo [`HANG-CHO-01`](../docs/decisions/hang-cho-01.md) Q3 (phiếu thu người xác nhận, ở hộp chung). Người dùng bảo "Làm P2" (chat 1/11/2026). Nối tiếp [P1](v7-hop-ngoai-le-p1.md).

**Phạm vi P2:** phiếu thu, và cảnh báo ở Đòi nợ. Giá từ Sheet hôm nay 0 dòng sẵn sàng, còn lệch chữ để máy tự làm ở P3, nên hai phần này chưa làm ở đây.

## Người dùng và luồng (bước 1)

**Người nhập** (luồng L1 của bước 03), ở Việc cần làm → khối "Từ Sheet chờ đưa vào sổ" → nhóm "Phiếu thu từ Sheet chờ ghi":

1. Mỗi sổ có phiếu sẵn sàng hiện một dòng có ô chọn:
   - tên khách;
   - "2 phiếu · 400 triệu";
   - bấm "Xem phiếu" thì mở danh sách: ngày, số tiền, ghi chú Sheet.

   Phiếu "cần xem" (không rõ ngày, ngày tương lai, Sheet sửa dòng sổ gốc, đã xóa trên web) không chọn được. Dòng đó có nút "Mở sổ".
2. Chọn một hay nhiều sổ (có "Chọn tất cả"), rồi bấm **"Xem lại n sổ (tổng …)"**.
3. Khung xem lại liệt kê từng sổ:
   - tổng còn nợ trước → sau;
   - "khách sẽ dư … đ" khi sau âm;
   - "có phiếu ngày trong tháng đang khóa: vẫn ghi được" khi có.

   Hai nút: **"Ghi n phiếu"** (chính) và "Thôi".
4. Ghi lần lượt từng sổ bằng lệnh đang có `POST /api/v7/sheet/receipts`. Mỗi sổ một mã chống ghi trùng, nên bấm lại hay mất mạng giữa chừng không bao giờ ghi hai lần.
5. Kết quả theo từng sổ:
   - sổ ghi xong biến khỏi danh sách;
   - băng "Đã ghi 5 phiếu ở 3 sổ, tổng 1,2 tỷ", kèm "Mở sổ" ở từng sổ để hủy phiếu vừa ghi nếu nhầm (hủy cần lý do, ở sổ, như [`SO-GON-04`](../docs/decisions/so-gon-04.md) H3);
   - sổ lỗi ở lại, kèm câu lỗi của server ngay tại dòng.

**Người đòi nợ**, ở Đòi nợ:
1. Khách còn phiếu thu từ Sheet chưa ghi thì có nhãn chữ cạnh số còn nợ: "còn 1 phiếu chưa ghi · 50 triệu".
2. Bấm "Copy tin nhắc" cho khách đó thì hỏi trước: "Khách còn 1 phiếu thu 50.000.000 đ trên Sheet chưa ghi vào web. Tin nhắc sẽ ghi nợ cao hơn thực tế." Hai nút:
   - **"Ghi phiếu trước"** (chính): mở Việc cần làm;
   - "Vẫn copy": copy và ghi mốc "đã nhắc" như cũ.
3. Không đọc được việc chờ thì không hỏi, và nhãn không hiện. Không giả là không có việc; dòng chú thích trang ghi "chưa kiểm được phiếu chờ".

**Bị chặn khi:** sổ vừa đổi (`STALE_LEDGER`) hoặc Sheet vừa đổi (`STALE_SHEET`). Dòng báo câu của server; hộp tự tải lại sổ đó ở lần đọc sau (P1 đánh dấu sổ sau lệnh ghi), người nhập chọn lại.

## Đầu ra

Người nhập ghi được phiếu thu từ Sheet của nhiều sổ trên một trang, có bước xem lại. Người đòi nợ được hỏi trước khi gửi tin nhắc có số sai.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Cần | Có sẵn | Thêm |
| --- | --- | --- |
| Danh sách phiếu từng sổ | `sheet_receipts.ready` / `.review`: `date`, `amount_vnd`, `debt_month`, `note`, `status` (`v7_receipt_queue.project_receipts`) | Đưa vào `GET /api/v7/inbox`: `receipts.items`, `receipts.snapshot_sha256` |
| Phiên bản sổ, tổng còn nợ | `get_ledger`: `version`, `total_outstanding_vnd` | `version`, `outstanding_vnd` của sổ trong inbox |
| Tháng khóa | `get_ledger`: `month_locks`, `today_month` (tháng không có hàng thì chỉ `today_month` mở) | `receipts.locked_months`: tháng của các phiếu sẵn sàng đang khóa |
| Ghi | `POST /api/v7/sheet/receipts` {`customer_id`, `expected_version`, `snapshot_sha256`, `idempotency_key`} → {`written`, `remaining`, `complete`, `error`?}; ghi mọi phiếu sẵn sàng của sổ, mỗi phiếu một khóa riêng | Không có lệnh mới |
| Phiếu trùng (M4) | Hàng chờ đã loại phiếu trùng phiếu web (cùng số tiền, ±3 ngày) và dòng sổ gốc (cùng tháng, số tiền, chữ ngày); phiếu lệch sổ gốc thành "cần xem" | Không thêm luật |
| Đòi nợ | `doi-no.js` đọc `dashboard/debt`, `reminders`, `customers` | Đọc thêm `GET /api/v7/inbox` |

Số đo trên `hao` 1/11/2026: 13 phiếu (6 sẵn sàng, 7 cần xem) ở 12 sổ, tổng 3,19 tỷ.

## Nguồn quyết định

[`HANG-CHO-01`](../docs/decisions/hang-cho-01.md) Q3, [`THU-SHEET-01`](../docs/decisions/thu-sheet-01.md) (luật ghép phiếu không đổi), [`SO-GON-04`](../docs/decisions/so-gon-04.md) H3, H5, [`NHAC-NO-01`](../docs/decisions/nhac-no-01.md).

## Hành vi và bất biến

- Mọi phiếu đi đúng `record_receipt` qua lệnh duyệt đang có. Không thêm đường ghi tiền.
- Mỗi lần bấm Ghi có một khóa cho từng sổ; bấm lại hoặc "Thử lại" dùng đúng khóa đó.
- Không ghi sổ nào chưa qua khung xem lại.
- Nợ "sau" chỉ là tạm tính bằng nợ trước trừ tổng phiếu. Số thật lấy lại từ server sau khi ghi.
- Trống không thành 0: phiếu không có số tiền không có trong danh sách sẵn sàng (hàng chờ đã loại).

## Tiêu chí nghiệm thu

- [ ] Unit Python: inbox có `version`, `outstanding_vnd`, `receipts.items`, `snapshot_sha256`, `locked_months` đúng (tháng không có hàng khóa, trừ tháng hiện tại).
- [ ] Unit JS cho phần dựng câu: nợ sau, khách dư, tháng khóa.
- [ ] Trình duyệt (máy chủ giả):
  - chọn hai sổ → xem lại → ghi → cả hai biến mất, băng tổng đúng;
  - một sổ `STALE_LEDGER` thì ở lại với câu lỗi, sổ kia ghi xong;
  - mất mạng khi ghi thì "Thử lại" gửi đúng khóa cũ;
  - phiếu cần xem không chọn được;
  - Đòi nợ hỏi lại trước khi copy, hai nhánh nút đều đúng;
  - khung 1280×560.
- [ ] `npm run check` xanh.
- [ ] Trên `hao`: người dùng ghi các phiếu sẵn sàng qua hộp; số phiếu chờ giảm đúng; Lịch sử của sổ có dòng ghi phiếu với tên người làm.
