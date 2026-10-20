# Vùng bảng cuộn ngang dùng được bằng bàn phím (fixture)

Trạng thái: ĐỀ XUẤT ngày 16/10/2026 bởi Claude theo yêu cầu người dùng thử Gemini trong quy trình nhiều agent. Sửa nhỏ accessibility, không đổi luồng.

Miễn mockup Penpot theo mục "Sửa nhỏ" của [quy trình frontend](../docs/development.md#quy-trình-frontend): chỉ thêm thuộc tính truy cập cho vùng cuộn có sẵn; không đổi bố cục, chữ hiển thị, luồng, dữ liệu, quyền hay nghiệp vụ.

## Đầu ra

Trong workbench `cong-no-web-handoff/preview/customer-ledger-workbench.html`, mỗi tháng có 3 vùng `.table-scroll` (bảng chuyến hàng, bảng nhập chuyến, bảng thanh toán). Bảng rộng hơn màn hình nên phải cuộn ngang, nhưng hiện các vùng này không nhận focus bằng Tab, nên người dùng bàn phím không cuộn được.

## Hành vi và bất biến

- Mỗi phần tử `.table-scroll` do `customer-ledger-workbench-ui.js` sinh ra có `tabindex="0"`, `role="region"` và `aria-label` riêng theo bảng và tháng:
  - Bảng chuyến hàng: `Chuyến hàng · <nhãn tháng>`
  - Bảng nhập chuyến: `Bảng nhập chuyến · <nhãn tháng>`
  - Bảng thanh toán: `Thanh toán · <nhãn tháng>`
  - `<nhãn tháng>` dùng đúng hàm `label(p)` đã có trong file, như ở tiêu đề "Bảng nhập chuyến · ${label(p)}".
- Vùng cuộn khi được focus phải có viền focus nhìn thấy, cùng kiểu với các control khác (`outline:3px solid #e6a64a;outline-offset:2px`).
- Không đổi số liệu, chữ hiển thị, thứ tự cột, hành vi nút, model hay tổng nợ.

## Tiêu chí nghiệm thu

- [ ] Test browser mới khẳng định: mọi `.table-scroll` trong tháng đang mở có `tabindex="0"`, `role="region"` và `aria-label` không rỗng, và 3 nhãn trong một tháng khác nhau.
- [ ] `npm run test:unit` và `npm run test:browser` đạt.

## Ảnh chụp giao diện

Script chụp trước/sau thay đổi cho reviewer; xem [multi-agent](../docs/multi-agent.md#ảnh-chụp-giao-diện).

```json
{
  "page": "cong-no-web-handoff/preview/customer-ledger-workbench.html",
  "viewports": [[1500, 1000]],
  "states": [
    {"name": "1-tab-vao-bang-thanh-toan", "note": "Tháng 03/2026 (mở sẵn): từ nút + Thanh toán bấm Tab tới vùng cuộn bảng thanh toán, phải thấy viền focus",
     "shot": "#month-2026-03",
     "steps": [{"focus": "#month-2026-03 [data-action=\"open-receipt\"]"}, {"press": "Tab"}]},
    {"name": "2-bang-nhap-mo", "note": "Mở bảng nhập chuyến tháng 03/2026, thêm một dòng",
     "shot": "#month-2026-03",
     "steps": [{"click": "#month-2026-03 [data-action=\"open-editor\"]"}, {"click": "[data-editor=\"2026-03\"] [data-action=\"add\"]"}]}
  ]
}
```

## Phạm vi agent

Mục này là hợp đồng với agent thực hiện; `scripts/agent-run.ps1` đọc nó để kiểm diff.

- Agent: gemini
- Mockup: miễn: sửa nhỏ accessibility, không đổi bố cục/luồng (xem đầu spec)
- Review: sonnet medium
- Được sửa:
  - `cong-no-web-handoff/preview/customer-ledger-workbench-ui.js`
  - `cong-no-web-handoff/preview/customer-ledger-workbench.css`
  - `cong-no-web-handoff/preview/test-customer-ledger-browser.js`
- Ngân sách diff: 30 dòng
- Lệnh kiểm:
  - `npm run test:unit`
  - `npm run test:browser`
- Cấm:
  - Đổi bố cục, màu, chữ hiển thị, luồng, model (`customer-ledger-workbench.js`, `*-model.js`) hoặc HTML tĩnh.
  - Format lại hoặc tách dòng các file đang viết dạng nén: sửa tại chỗ, giữ nguyên kiểu viết hiện có.
  - Thêm dependency, framework, thư viện a11y, helper hoặc file mới.
  - Đổi trường tiền, quyền, quy tắc nghiệp vụ; chạm dữ liệu thật.
- Khi cần vượt phạm vi: dừng, không tự mở rộng; nêu câu hỏi trong báo cáo cuối.

## Hoàn tác

Bỏ các thuộc tính, quy tắc CSS và test vừa thêm.

## Bằng chứng

<Script ghi kết quả Lệnh kiểm vào log; reviewer ghi kết luận.>

## Câu hỏi mở

- (chưa có)
