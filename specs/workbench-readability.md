# Tăng độ dễ đọc bảng chuyến hàng cho người dùng trên 40 tuổi

Trạng thái: ĐỀ XUẤT ngày 16/10/2026, tách ra từ review mockup [remove-draft-rows](remove-draft-rows.md) theo yêu cầu người dùng. Bước 1–2 hoàn thiện ngày 16/10/2026 với câu trả lời của người dùng trong chat. ĐÃ CHỐT giao việc: người dùng duyệt spec ngày 16/10/2026 trong chat, cho chạy bước mockup. Ngày 17/10/2026, sau 3 lần mockup đều CẦN SỬA vì bảng nhập không vừa khung 1366 ở chữ 16/18px, người dùng chốt **thu hẹp**: lượt này chỉ làm bảng chuyến hàng và phần tóm tắt, theo hướng board 03 lần 3; bảng nhập chuyến làm ở spec sau, khi [remove-draft-rows](remove-draft-rows.md) đã code xong (hai spec sửa cùng bảng nhập). Mức chữ (16 hay 18px) và cách mở chi tiết vẫn chờ người dùng chọn trên mockup.

## Vấn đề

Người dùng chính trên 40 tuổi ([UX](../docs/ux-guidelines.md), ĐÃ CHỐT). `customer-ledger-workbench.css` hiện dùng chữ thân 14px, ô bảng 13px, tiêu đề cột 12px, nhãn trạng thái 11px; hướng dẫn UX đề xuất chữ thân tối thiểu 16px và vùng bấm tối thiểu 40px. Bảng chuyến hàng rất rộng (12 cột, `min-width:1550px`), tăng cỡ chữ sẽ làm bảng rộng thêm và phải cuộn ngang nhiều hơn.

## Người dùng và luồng (bước 1)

- **Người thao tác:** người kiểm chuyến hàng của một khách, trên 40 tuổi.
- **Thiết bị:** laptop 14–15 inch (người dùng trả lời 16/10/2026). ĐỀ XUẤT khung thiết kế 1366×768 điểm ảnh CSS (laptop 1366 ở 100%, hoặc 1920 ở khoảng 140%); kiểm thêm 1280×720 (1920 ở 150%). CÒN MỞ: tỉ lệ phóng Windows thực tế trên máy người dùng.
- **Luồng:** chọn khách và kỳ → bấm "Xem sổ" → đọc tổng còn nợ → mở tháng → đọc bảng "Chuyến hàng" và phần tóm tắt tháng để kiểm. Luồng không đổi; chỉ đổi cách hiển thị.
- **Cột bắt buộc thấy cùng lúc, không cuộn ngang** (người dùng chốt 16/10/2026): ngày chuyến, số container, khách; đơn giá và các phí (phí khác, phí đầu kéo / điện, bảo hiểm); thành tiền và trạng thái.
- **Cột có thể đưa vào chi tiết** (người dùng không chọn là bắt buộc): Hãng tàu / số xe, Shipper, Nơi đi, Nơi đến.
- **Cỡ chữ:** mockup so hai mức 16px và 18px để người dùng chọn (người dùng chốt 16/10/2026).
- **Ngoài phạm vi lượt này:** bảng nhập chuyến, bảng thanh toán, hộp chi tiết, phiếu thu. Giữ nguyên như hiện tại.
- **Kết quả:** người dùng đọc được bảng chuyến hàng ở khung laptop không phải phóng trình duyệt, không cuộn ngang để thấy các cột bắt buộc.

## Đầu ra

Phần đầu trang (bộ lọc, tổng còn nợ), tiêu đề tháng, bảng chuyến hàng và tóm tắt tháng hiển thị theo mức chữ người dùng chọn trên mockup; bảng chuyến hàng hiện đủ cột bắt buộc trong khung 1366px; dữ liệu, tiền và luồng không đổi.

## Đối chiếu dữ liệu và code hiện có (bước 2)

Nguồn: `cong-no-web-handoff/preview/customer-ledger-workbench.css` và `customer-ledger-workbench-ui.js` (giống nhau ở `HEAD` và `fix/m1-review-readiness`).

- **Cỡ chữ hiện tại:** gốc 14px; ô bảng 13px; tiêu đề cột 12px; nhãn trạng thái, nhãn tóm tắt tháng, badge 11px; tiêu đề tháng 16px; tổng còn nợ 29px; khung `.shell` tối đa 1500px.
- **Bảng "Chuyến hàng"** (`.shipment-table`, `min-width:1550px`), 12 cột theo thứ tự: STT, Số container, Hãng tàu / số xe, Shipper, Ngày chuyến, Nơi đi, Nơi đến, Phí khác, Phí đầu kéo / điện, Bảo hiểm, Đơn giá, Thành tiền.
- **Khách** không là cột: trang lọc theo một khách, tên khách ở tiêu đề trang. Giữ như vậy, không thêm cột khách.
- **Trạng thái chuyến** (đã ghi sổ / chờ giá / nháp chờ duyệt) hiện bằng nhãn `.status` trong dòng, không có cột riêng.
- **Xem chi tiết chuyến đã có sẵn:** số container là liên kết (`data-detail="shipment:…"`) mở hộp chi tiết của chuyến. Cột phụ đưa vào chi tiết có thể xem qua hộp này; nếu mockup thêm nút "Chi tiết" riêng thì phải mở cùng hộp đó, không làm hộp mới.
- **Nút có sẵn trong tháng:** "＋ Nhập chuyến" mở bảng nhập; giữ nguyên tên và chức năng.
- **Số liệu mockup** lấy từ fixture tháng 02/2026: `DEMO-102` 40,000,000 đã ghi sổ, `DEMO-103` chờ giá; thanh toán `PT-102` 10,000,000; còn nợ kỳ 30,000,000; tổng mọi kỳ 95,000,000.

## Giao tiếp frontend–backend

Không có. Fixture HTML tĩnh; chỉ đổi CSS và cách hiển thị cột.

## Nguồn quyết định

- Người dùng trên 40 tuổi, ưu tiên luồng nghiệp vụ, không thông tin thừa: [UX](../docs/ux-guidelines.md), ĐÃ CHỐT.
- Thiết bị, cột bắt buộc, hai mức chữ: người dùng trả lời trong chat 16/10/2026.
- Thu hẹp về bảng chuyến hàng + tóm tắt: người dùng chốt trong chat 17/10/2026.

## Hành vi và bất biến

- Không đổi dữ liệu, cách tính tiền, trạng thái, thứ tự dòng, câu thông báo, tên cột hay luồng thao tác.
- Không viết tắt tiền; luôn ghi đủ số. Ô trống hiện `—`, không thành 0.
- Không ẩn mất dữ liệu: cột đưa vào chi tiết vẫn xem được bằng một thao tác, đến được bằng bàn phím.
- Vùng bấm tối thiểu 40px, viền focus rõ, tương phản đạt WCAG AA.
- Không đổi giao diện bảng nhập chuyến trong lượt này.

## Trạng thái cần có trên mockup

Khung 1366×768, tỉ lệ 1:1, đúng 3 board:

- `A16 · Bảng chuyến hàng tháng 02`: đầu trang (tên khách, bộ lọc, tổng còn nợ, cảnh báo chờ giá), tháng 02/2026 đang mở, bảng chuyến hàng đủ cột bắt buộc với nhãn trạng thái, tóm tắt tháng; chữ nghiệp vụ 16px.
- `B18 · Bảng chuyến hàng tháng 02`: cùng nội dung, chữ nghiệp vụ 18px.
- Một board ghi chú ngắn ngoài khung màn hình: cột nào đưa vào chi tiết và cách mở; nhãn nào xin nhỏ hơn mức chữ (nếu có).

## Tiêu chí nghiệm thu (cho bước code sau khi duyệt)

- [ ] Ở 1366×768 và 1280×720: bảng chuyến hàng thấy đủ cột bắt buộc không cuộn ngang; chữ trong vùng `#month-2026-02` không nhỏ hơn mức đã chọn, trừ nhãn phụ đã duyệt trên mockup.
- [ ] Cột phụ xem được qua chi tiết bằng chuột và bàn phím (Tab, Enter/Space), có viền focus.
- [ ] Đo tự động trong `ui-after/checks.md` không có phát hiện MỚI về cỡ chữ, tương phản, vùng bấm, focus. Mốc trước thay đổi (`-Step capture` ngày 16/10/2026, cả hai khung): bảng chuyến hàng 14 phát hiện có sẵn (cỡ chữ, tương phản, vùng bấm, focus). Reviewer so `report.json` trước/sau: con số này phải giảm.
- [ ] Bảng nhập chuyến không đổi giao diện (so ảnh trước/sau nếu mở).
- [ ] `npm run test:unit` và `npm run test:browser` đạt; số liệu tháng 02 không đổi.
- [ ] Giao diện khớp đúng phiên bản mockup Penpot đã duyệt.
- [ ] Người dùng tự đi hết luồng trên laptop của mình và xác nhận (bước 8).

## Ảnh chụp giao diện

Một trạng thái ứng với board của mức chữ được chọn (ghi tạm board A16; đổi sang B18 nếu người dùng chọn 18px).

```json
{
  "page": "cong-no-web-handoff/preview/customer-ledger-workbench.html",
  "viewports": [[1366, 768], [1280, 720]],
  "states": [
    {"name": "01-bang-chuyen-hang", "board": "A16 · Bảng chuyến hàng tháng 02", "note": "Mở tháng 02/2026 để kiểm chuyến hàng", "shot": "#month-2026-02",
     "steps": [{"select": ["#period", "2026-02"]}, {"click": "#filters button"}, {"click": "#month-2026-02 > summary"}]}
  ]
}
```

## Phạm vi agent

Mục này là hợp đồng với agent thực hiện; `scripts/agent-run.ps1` đọc nó để kiểm diff.

- Agent: gemini
- Mockup: CHỜ DUYỆT (khi duyệt ghi: ĐÃ DUYỆT <link page> · phiên bản "<tên version Penpot>" · <người> · <ngày>)
- Review: sonnet medium
- Được sửa:
  - `cong-no-web-handoff/preview/customer-ledger-workbench.css`
  - `cong-no-web-handoff/preview/customer-ledger-workbench-ui.js`
  - `cong-no-web-handoff/preview/test-customer-ledger-browser.js`
- Ngân sách diff: 60 dòng
- Lệnh kiểm:
  - `npm run test:unit`
  - `npm run test:browser`
- Cấm:
  - Đổi `customer-ledger-workbench.js` (model), cách tính tiền, trạng thái, câu thông báo hoặc luồng thao tác.
  - Đổi giao diện bảng nhập chuyến, bảng thanh toán, hộp chi tiết, phiếu thu.
  - Format lại hoặc tách dòng các file đang viết dạng nén; thêm dependency, framework, font ngoài hoặc file mới.
  - Chạm dữ liệu thật; tự quyết mức chữ khi người dùng chưa chọn trên mockup.
- Khi cần vượt phạm vi: dừng, không tự mở rộng; nêu câu hỏi trong báo cáo cuối.

## Hoàn tác

Revert commit CSS/UI; xóa page mockup trong Penpot nếu không dùng.

## Bằng chứng

<Link mockup đã duyệt; kết quả Lệnh kiểm; ui-after/checks.md; kết luận review.>

## Câu hỏi mở

- Tỉ lệ phóng Windows trên laptop người dùng (để chốt khung 1366 hay 1280).
- Bảng nhập chuyến: spec riêng sau khi remove-draft-rows code xong.
