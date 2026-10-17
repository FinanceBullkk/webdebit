# Lớp 2b — tách khoản thu thành bảng riêng

Trạng thái: **ĐỀ XUẤT** (Claude, 18/10/2026). Thực hiện sau khi [`v6-model-phan-bo-tung-khoan.md`](v6-model-phan-bo-tung-khoan.md) ĐẠT.

Đổi bố cục tháng đang mở của `so-cong-no-v5.html`: **bảng chuyến** và **bảng khoản thu** tách hẳn, thay cho cách gõ khoản thu ngay trên dòng chuyến. Quyết định `V6-THU` ngày 18/10/2026.

## Người dùng và luồng (bước 1)

Ba vai trên 40 tuổi, quen bảng tính, làm 10–50 container mỗi ngày, mỗi lô một khách.

1. **Xem sổ một khách.** Mở sổ → tháng đang mở hiện **hai bảng xếp dọc**: `Chuyến hàng` ở trên, `Các khoản thu` ở dưới, rồi `Tổng kết tháng`. Nhìn một lần thấy: tháng này chạy bao nhiêu chuyến, đã nhận bao nhiêu tiền, còn phải thu bao nhiêu.
2. **Ghi một khoản thu — gõ thẳng trên dòng trống đầu bảng thu.** Bốn ô: `Ngày thực nhận` · `Cách thu` · `Tham chiếu` · `Số tiền đã thu` → bấm `Lưu dòng`. Không mở màn khác, không hộp thoại. **Bỏ hẳn** các cột thu trên dòng chuyến (`Ngày nhận tiền`, `Cách thu`, `Tham chiếu`, `Đã thu`) và lối gõ thu trên dòng chuyến.
3. **Xem một khoản thu trừ cho nợ tháng nào.** Cột `Phân bổ` ghi dòng tóm tắt (`02/2026 · 20.000.000`) kèm `Xem phân bổ ›`; bấm thì **bung ngay dưới dòng thu đó**, liệt kê từng kỳ nợ bị trừ và số tiền từng kỳ. Bấm lại thì thu lại. Không hộp thoại, không rời màn.
4. **Thêm lô chuyến và chốt tháng:** giữ nguyên như hiện có.

Khoản thu nằm ở bảng thu của **tháng nhận tiền**, kể cả khi nó trừ nợ kỳ cũ; cột `Phân bổ` là chỗ nói ra điều đó. Không chuyển khoản thu sang tháng bị trừ, không sửa tháng đã chốt.

Khoản **chưa có ngày thực nhận**: cột `Ngày thực nhận` hiện `—`, `Trạng thái` ghi `Chờ ngày nhận`, cột `Phân bổ` ghi `Chưa ảnh hưởng số dư`; không vào tổng đã thu và không vào số dư.

CÒN MỞ — không tự quyết, không vẽ nút: ai được xác nhận chứng từ và căn cứ gì; sửa hoặc xóa một khoản thu **đã lưu**; tiền dư của khách.

## Đầu ra

`cong-no-web-handoff/preview/so-cong-no-v5.html` mở trực tiếp trong trình duyệt: tháng đang mở hiện hai bảng tách rời, ghi được khoản thu ở bảng dưới, bung được phân bổ từng khoản, mọi con số do model tính.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- Mốc hình đã duyệt: [`cong-no-web-handoff/preview/mockups/ux-v6-bang-thu-rieng-chatgpt.png`](../cong-no-web-handoff/preview/mockups/ux-v6-bang-thu-rieng-chatgpt.png). Lấy **bố cục, tên cột, thứ tự khối, cách báo lỗi dòng**. Không lấy: bảng chuyến 11 cột dàn ngang (giữ cách bung chi tiết theo dòng đang có), tên khách và mọi con số trong ảnh.
- `so-cong-no-v5-ui.js` (757 dòng) đã có sẵn: `data-action="allocation"`, `data-action="row-payment"`, các ô `data-pay="date|method|ref|amount"`, `data-action="payment-preview"`, `data-action="payment-cancel"`. Dùng lại các tên này cho bảng thu; phần gắn vào dòng chuyến thì bỏ.
- Model: `LedgerV5Model.allocateReceipts` (spec lớp 1b) cho cột `Phân bổ`; `ledgerBalance` vẫn là nguồn của `Tổng kết tháng`. **Không tự tính tiền trong mã giao diện.**
- Câu chữ đang có phải giữ nguyên: `Chờ ngày nhận`, `Chưa ảnh hưởng số dư`, `Thiếu giá`, `Dán từ bảng tính`, `Chốt công nợ tháng <mm>`, các nhãn ở `Tổng kết tháng`.

## Giao tiếp frontend–backend (bước 5)

Không có backend. Trạng thái trong tab, không `fetch`, không lưu trữ.

## Nguồn quyết định

- [`docs/decisions.md`](../docs/decisions.md): `V6-THU` (bố cục này), `V5-UX` (khoản thu thuộc sổ + kỳ nợ), `D03` (nợ cũ trước), `V5-GD` (phần còn hiệu lực).
- [`docs/ux-guidelines.md`](../docs/ux-guidelines.md) — chữ ≥ 16px, vùng bấm ≥ 40px, tiền VND nguyên, ô trống là `—`.

## Hành vi và bất biến

- Ô trống là `—`, không phải 0; khoản chờ không nằm trong tổng còn nợ.
- Tiền VND nguyên, phân cách hàng nghìn, căn phải.
- Trạng thái luôn có chữ, không chỉ dùng màu.
- Tháng đã chốt không đổi; không có đường sửa khoản thu đã lưu trong lần này.

## Tiêu chí nghiệm thu

- [ ] `npm run test:unit` PASS.
- [ ] Bàn phím: Tab đi hết bốn ô của dòng thu rồi tới `Lưu dòng`; Enter ở ô cuối lưu dòng; phần tử đang focus có viền thấy rõ.
- [ ] Nhập sai: thiếu số tiền, số tiền không phải số, ngày tương lai → báo ngay tại ô, giữ nguyên dữ liệu đã gõ.
- [ ] Bấm `Lưu dòng` hai lần liên tiếp không tạo hai khoản thu.
- [ ] Không còn ô nhập tiền nào trên dòng chuyến.
- [ ] Bước 8: người dùng tự đi hết ba luồng trên bản thử và xác nhận.

## Ảnh chụp giao diện

```json
{
  "page": "cong-no-web-handoff/preview/so-cong-no-v5.html",
  "viewports": [[1500, 1000]],
  "states": [
    {"name": "1-thang-dang-mo", "board": "ux-v6-bang-thu-rieng-chatgpt.png", "note": "Người dùng mở sổ, nhìn hai bảng tách rời",
     "shot": "#app", "steps": []},
    {"name": "2-go-khoan-thu", "board": "ux-v6-bang-thu-rieng-chatgpt.png", "note": "Đang gõ bốn ô ở dòng trống đầu bảng thu",
     "shot": "#app", "steps": [
       {"fill": ["[data-pay=\"date\"]", "05/02/2026"]},
       {"select": ["[data-pay=\"method\"]", "Chuyển khoản"]},
       {"fill": ["[data-pay=\"ref\"]", "CK123456"]},
       {"fill": ["[data-pay=\"amount\"]", "20000000"]}]},
    {"name": "3-da-luu-khoan-thu", "board": "ux-v6-bang-thu-rieng-chatgpt.png", "note": "Sau khi bấm Lưu dòng",
     "shot": "#app", "steps": [
       {"fill": ["[data-pay=\"date\"]", "05/02/2026"]},
       {"fill": ["[data-pay=\"ref\"]", "CK123456"]},
       {"fill": ["[data-pay=\"amount\"]", "20000000"]},
       {"click": "[data-action=\"payment-preview\"]"}]},
    {"name": "4-bung-phan-bo", "board": "ux-v6-bang-thu-rieng-chatgpt.png", "note": "Bấm Xem phân bổ, bung dưới dòng thu",
     "shot": "#app", "steps": [{"click": "[data-action=\"allocation\"]"}]},
    {"name": "5-cho-ngay-nhan", "board": "ux-v6-bang-thu-rieng-chatgpt.png", "note": "Khoản thu chưa có ngày thực nhận",
     "shot": "#app", "steps": [{"waitFor": "[data-state=\"pending-date\"]"}]}
  ]
}
```

Kịch bản này viết trước khi có giao diện mới; chạy `-Step capture` để chỉnh selector trước khi giao agent.

## Phạm vi agent

- Agent: gemini
- Mockup: miễn: người dùng duyệt trực tiếp wireframe ngày 18/10/2026 (quyết định `V6-THU`); mốc hình lưu tại `cong-no-web-handoff/preview/mockups/ux-v6-bang-thu-rieng-chatgpt.png`. Miễn trừ chỉ áp dụng cho thay đổi này.
- Review: opus — đụng hiển thị phân bổ tiền
- Được sửa:
  - `cong-no-web-handoff/preview/so-cong-no-v5.html`
  - `cong-no-web-handoff/preview/so-cong-no-v5-ui.js`
- Ngân sách diff: 450 dòng
- Lệnh kiểm:
  - `npm run test:unit`
- Cấm:
  - Sửa `so-cong-no-v5-model.js` và test của nó — model đã kiểm chứng; thiếu gì thì hỏi.
  - Sửa mockup hoặc bất kỳ màn/model cũ nào trong `preview/`.
  - Tự tính tiền trong mã giao diện.
  - Đổi câu chữ, nhãn, cỡ chữ của những phần không nằm trong thay đổi này.
  - Thêm dependency, framework, build step; `fetch`, API, localStorage.
  - Vẽ nút xác nhận chứng từ, sửa/xóa khoản thu đã lưu, xử lý tiền dư — các điểm CÒN MỞ.
- Khi cần vượt phạm vi: dừng, ghi vào "Câu hỏi mở".

## Hoàn tác

Hai file sửa, revert commit; không đụng dữ liệu.

## Bằng chứng

<Agent ghi: lệnh đã chạy, kết quả, đường dẫn ảnh chụp. Fixture trong tab, không phải tích hợp hay live.>

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
