# Bỏ dòng nháp đã chọn trong bảng nhập chuyến (fixture)

Trạng thái: ĐỀ XUẤT ngày 16/10/2026 bởi Claude theo yêu cầu người dùng thử bước mockup Penpot với Gemini. Luồng frontend mới, cần mockup được duyệt trước khi code ([quy trình frontend](../docs/development.md#quy-trình-frontend)).

## Vấn đề

Trong workbench `cong-no-web-handoff/preview/customer-ledger-workbench.html`, mỗi tháng có "Bảng nhập chuyến". Người nhập thêm/dán dòng, rồi bấm "Lưu nháp trong tab". `saveShipments` lưu theo kiểu tất cả hoặc không: chỉ một dòng sai (sai ngày, thiếu container, lệch tổng) là cả lô bị giữ lại. Hiện không có cách bỏ dòng thừa hoặc dán nhầm ra khỏi bảng nhập, nên người nhập phải tải lại trang và mất hết các dòng khác.

## Người dùng và luồng (bước 1)

- **Người thao tác:** người nhập chuyến (maker) của một khách, trên 40 tuổi ([UX](../docs/ux-guidelines.md)). Không phải người duyệt; luồng này không có bước duyệt.
- **Bối cảnh:** người nhập dán một lô dòng từ bảng tính vào "Bảng nhập chuyến" của một tháng, bấm "Lưu nháp trong tab"; một vài dòng sai hoặc dán thừa làm cả lô bị giữ lại.
- **Luồng sử dụng:** dán/thêm dòng → bấm lưu → thấy dòng lỗi → tick ô "Chọn" của dòng thừa/sai → bấm `✕ Bỏ dòng đã chọn` → bấm lưu lại → lô còn lại được giữ.
- **Kết quả:** các dòng còn lại lưu được mà không phải tải lại trang hay nhập lại.
- **Bị chặn khi:** chưa chọn dòng nào (báo, không bỏ gì).
- CÒN MỞ (UX chung, không chặn luồng này): thiết bị/kích thước màn hình, số dòng thường gặp mỗi lô.

## Đầu ra

Người nhập chọn một hoặc nhiều dòng trong bảng nhập (đã có ô "Chọn" từng dòng), bấm một thao tác để bỏ các dòng đó khỏi bảng nhập, rồi tiếp tục sửa hoặc lưu các dòng còn lại.

## Đối chiếu dữ liệu và code hiện có (bước 2)

Nguồn: `cong-no-web-handoff/preview/customer-ledger-workbench.js` và `customer-ledger-workbench-ui.js` tại base của nhánh. Toàn bộ là fixture trong bộ nhớ tab.

- **Dòng nháp:** `drafts[period]`, mỗi dòng có `id` dạng `NH-n`, `status:'draft'`, `errors`, `warnings` và 11 trường theo thứ tự cột: Ngày chuyến · xe nhập kho, Số container, Hãng tàu / số xe, Shipper, Nơi đi, Nơi đến, Đơn giá, Phí khác, Phí đầu kéo / điện, Bảo hiểm, Thành tiền dự kiến. Cột cuối "Kiểm tra" hiện lỗi/cảnh báo hoặc nhãn "Nháp".
- **Đã có:** `addDraft`, `paste` (tối đa 50 dòng/lần), `updateDraft`, `fillSelected(period, ids, values)`, `saveShipments(period)`; ô "Chọn" mỗi dòng (`data-select`); vùng phản hồi `data-feedback` của từng tháng.
- **`saveShipments`:** kiểm toàn bộ dòng; có lỗi thì không lưu dòng nào và báo "Còn lỗi kiểm tra. Dữ liệu và lỗi vẫn ở từng dòng; sửa rồi thử lại."; không lỗi thì chuyển tất cả sang danh sách chuyến (đơn giá trống → chờ giá, còn lại → nháp chờ duyệt), xóa bảng nhập và báo "Đã giữ N dòng nháp/chờ giá trong tab. Chưa ghi sổ, chưa thay đổi số dư."
- **Quy tắc tiền liên quan:** "Thành tiền dự kiến" chỉ tính khi đủ đơn giá và cả 3 phí (`estimate` trả null nếu thiếu); có thành tiền + một phần phí mà thiếu phí khác → lỗi; có đơn giá mà thiếu phí → cảnh báo.
- **Fixture tháng 02/2026:** chuyến `DEMO-102` 40,000,000 đã ghi sổ, `DEMO-103` chờ giá; thanh toán `PT-102` 10,000,000; còn nợ kỳ 30,000,000; tổng mọi kỳ 95,000,000.
- **Còn thiếu:** hàm bỏ dòng nháp trong model và nút/xử lý trên UI. Không cần trường dữ liệu mới.
- **Mẫu báo lỗi có sẵn:** "Điền dòng đã chọn" khi chưa chọn dòng ném lỗi "Chọn ít nhất một dòng và nhập giá/phí cần điền." và UI hiện vào vùng phản hồi; luồng mới dùng cùng cách.

## Giao tiếp model–UI (bước 5)

- **Model:** `removeDrafts(period, ids)` trong `createWorkbench`. Kỳ không hợp lệ → ném lỗi như `addDraft`. Chỉ xóa các dòng trong `drafts[period]` có `id` thuộc `ids`; id không có thì bỏ qua. Trả về số dòng đã bỏ. Không đụng `shipments`, `payments`, `openings`, `credits`.
- **UI:** nút `data-action="remove"` cạnh "Điền dòng đã chọn". Lấy id các ô "Chọn" đã tick của đúng tháng; không có id → ném lỗi "Chọn ít nhất một dòng cần bỏ." (hiện ở vùng phản hồi, không bỏ gì). Có id → gọi `removeDrafts`, render lại, phản hồi "Đã bỏ N dòng nháp chưa lưu."
- Không có API/backend; đây vẫn là fixture, chưa là tích hợp.

## Hành vi và bất biến

- Chỉ bỏ **dòng nháp chưa lưu** trong bảng nhập của đúng tháng đó. Không đụng chuyến đã lưu (nháp/chờ giá/chờ duyệt), chuyến đã ghi sổ, thanh toán hay tổng còn nợ.
- Không có dòng nào được chọn thì không bỏ gì và cho người dùng biết cần chọn dòng.
- Bỏ hết dòng thì bảng nhập về trạng thái trống hiện có ("Chưa có dòng nhập.").
- Dòng nháp có ô "Chọn" được tick tô nền vàng nhạt (đủ tương phản để chữ vẫn đọc rõ) để người dùng thấy rõ dòng nào sẽ bị bỏ; bỏ tick thì hết tô. ĐÃ CHỐT bởi người dùng 16/10/2026 sau review mockup lần 4. Ưu tiên làm bằng CSS (ví dụ `tr:has([data-select]:checked)`).
- Lỗi/cảnh báo đang hiện trên các dòng còn lại không bị xóa âm thầm; nếu thông điệp phản hồi đang nói về dòng đã bỏ thì cập nhật cho đúng.
- Fixture, chỉ trong bộ nhớ tab; không API, không localStorage.

## Trạng thái cần có trên mockup

- Bảng nhập có vài dòng, chưa chọn dòng nào.
- Đã chọn 1–2 dòng (trong đó có dòng đang báo lỗi khiến lưu bị chặn).
- Bấm bỏ khi chưa chọn dòng nào.
- Sau khi bỏ: các dòng còn lại, phản hồi số dòng đã bỏ, lưu được lô còn lại.
- Bỏ hết: bảng trống.
- Tổng còn nợ và bảng chuyến đã lưu không đổi trong mọi trạng thái trên.

## Lựa chọn thiết kế

ĐÃ CHỐT bởi người dùng ngày 16/10/2026 trong chat, sau review mockup lần 1:

- **Xác nhận:** bỏ ngay khi bấm, không có hộp xác nhận (1A).
- **Hoàn tác:** không có nút Hoàn tác (2B); dòng nháp chưa lưu, người dùng dán lại nếu cần.
- **Nút:** tên cố định `✕ Bỏ dòng đã chọn` (không hiện số đếm), đặt ngay cạnh "Điền dòng đã chọn", viền và chữ đỏ `#b91c1c`, không đổi màu theo số dòng chọn.
- **Phím tắt Delete / ô "Chọn tất cả":** chưa làm ở bản này.

## Tiêu chí nghiệm thu (cho bước code sau khi duyệt)

- [ ] Test model: bỏ dòng theo id chỉ xóa dòng nháp đúng tháng; id không có hoặc danh sách rỗng không đổi gì; chuyến đã lưu và tổng nợ không đổi.
- [ ] Test browser: chọn dòng lỗi → bỏ → lưu được các dòng còn lại; bỏ khi chưa chọn hiện thông báo; tổng còn nợ không đổi.
- [ ] Test browser (bước 7): nút đến được bằng Tab và bấm được bằng Enter/Space, có viền focus; bấm bỏ hai lần liên tiếp không bỏ thêm dòng nào ở lần hai (đã hết dòng được chọn) và báo cần chọn dòng.
- [ ] Giao diện khớp mockup đã duyệt (đúng phiên bản Penpot ghi ở dòng Mockup).
- [ ] `npm run test:unit` và `npm run test:browser` đạt.
- [ ] Người dùng tự đi hết luồng trên bản thử và xác nhận (bước 8); review của agent không thay bước này.

## Ảnh chụp giao diện

Kịch bản theo "Trạng thái cần có trên mockup", dùng đúng 3 dòng mẫu của mockup lần 6 (tháng 02/2026: DEMO-201, DEMO-202 hợp lệ, DEMO-ERR sai ngày). Mỗi trạng thái bắt đầu lại từ trang mới. Xem [multi-agent](../docs/multi-agent.md#ảnh-chụp-giao-diện).

```json
{
  "page": "cong-no-web-handoff/preview/customer-ledger-workbench.html",
  "viewports": [[1500, 1000]],
  "states": [
    {"name": "01-ba-dong-chua-chon", "board": "01 · Bình thường (3 dòng nháp, chưa chọn)", "note": "Dán 3 dòng vào bảng nhập tháng 02/2026", "shot": "#month-2026-02",
     "steps": [{"select": ["#period", "2026-02"]}, {"click": "#filters button"}, {"click": "#month-2026-02 > summary"},
       {"click": "#month-2026-02 [data-action=\"open-editor\"]"},
       {"fill": ["[data-paste=\"2026-02\"]", "2026-02-10\tDEMO-201\tMAERSK\tSHIPPER_A\tHải Phòng\tSài Gòn\t1500000\t50000\t0\t0\t1550000\n2026-02-11\tDEMO-202\tONE_LINE\tSHIPPER_B\tĐà Nẵng\tHải Phòng\t2100000\t0\t100000\t0\t2200000\nsai-dinh-dang\tDEMO-ERR\tSITC\tSHIPPER_C\tSài Gòn\tBình Dương\t1800000\t0\t0\t0\t1800000"]},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"paste\"]"}]},
    {"name": "02-luu-bi-chan-chon-dong-loi", "board": "02 · Lỗi chặn lưu & Chọn dòng lỗi", "note": "Bấm lưu bị chặn vì DEMO-ERR, rồi tick dòng DEMO-ERR", "shot": "#month-2026-02",
     "steps": [{"select": ["#period", "2026-02"]}, {"click": "#filters button"}, {"click": "#month-2026-02 > summary"},
       {"click": "#month-2026-02 [data-action=\"open-editor\"]"},
       {"fill": ["[data-paste=\"2026-02\"]", "2026-02-10\tDEMO-201\tMAERSK\tSHIPPER_A\tHải Phòng\tSài Gòn\t1500000\t50000\t0\t0\t1550000\n2026-02-11\tDEMO-202\tONE_LINE\tSHIPPER_B\tĐà Nẵng\tHải Phòng\t2100000\t0\t100000\t0\t2200000\nsai-dinh-dang\tDEMO-ERR\tSITC\tSHIPPER_C\tSài Gòn\tBình Dương\t1800000\t0\t0\t0\t1800000"]},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"paste\"]"},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"save\"]"},
       {"check": "[data-editor=\"2026-02\"] tbody tr:nth-child(3) [data-select]"}]},
    {"name": "03-bo-khi-chua-chon", "board": "03 · Thiếu dữ liệu (Bấm bỏ khi chưa chọn)", "note": "Bấm Bỏ dòng đã chọn khi chưa tick dòng nào", "shot": "#month-2026-02",
     "steps": [{"select": ["#period", "2026-02"]}, {"click": "#filters button"}, {"click": "#month-2026-02 > summary"},
       {"click": "#month-2026-02 [data-action=\"open-editor\"]"},
       {"fill": ["[data-paste=\"2026-02\"]", "2026-02-10\tDEMO-201\tMAERSK\tSHIPPER_A\tHải Phòng\tSài Gòn\t1500000\t50000\t0\t0\t1550000\n2026-02-11\tDEMO-202\tONE_LINE\tSHIPPER_B\tĐà Nẵng\tHải Phòng\t2100000\t0\t100000\t0\t2200000\nsai-dinh-dang\tDEMO-ERR\tSITC\tSHIPPER_C\tSài Gòn\tBình Dương\t1800000\t0\t0\t0\t1800000"]},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"paste\"]"},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"remove\"]"}]},
    {"name": "05-sau-khi-bo-dong-loi", "board": "05 · Thành công 1 (Sau khi bỏ dòng lỗi)", "note": "Tick DEMO-ERR rồi bấm Bỏ dòng đã chọn; nút vẫn đang focus", "shot": "#month-2026-02",
     "steps": [{"select": ["#period", "2026-02"]}, {"click": "#filters button"}, {"click": "#month-2026-02 > summary"},
       {"click": "#month-2026-02 [data-action=\"open-editor\"]"},
       {"fill": ["[data-paste=\"2026-02\"]", "2026-02-10\tDEMO-201\tMAERSK\tSHIPPER_A\tHải Phòng\tSài Gòn\t1500000\t50000\t0\t0\t1550000\n2026-02-11\tDEMO-202\tONE_LINE\tSHIPPER_B\tĐà Nẵng\tHải Phòng\t2100000\t0\t100000\t0\t2200000\nsai-dinh-dang\tDEMO-ERR\tSITC\tSHIPPER_C\tSài Gòn\tBình Dương\t1800000\t0\t0\t0\t1800000"]},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"paste\"]"},
       {"check": "[data-editor=\"2026-02\"] tbody tr:nth-child(3) [data-select]"},
       {"focus": "[data-editor=\"2026-02\"] [data-action=\"remove\"]"}, {"press": "Enter"}]},
    {"name": "06-luu-lo-con-lai", "board": "06 · Thành công 2 (Lưu lô còn lại thành công)", "note": "Sau khi bỏ DEMO-ERR, bấm Lưu nháp trong tab", "shot": "#month-2026-02",
     "steps": [{"select": ["#period", "2026-02"]}, {"click": "#filters button"}, {"click": "#month-2026-02 > summary"},
       {"click": "#month-2026-02 [data-action=\"open-editor\"]"},
       {"fill": ["[data-paste=\"2026-02\"]", "2026-02-10\tDEMO-201\tMAERSK\tSHIPPER_A\tHải Phòng\tSài Gòn\t1500000\t50000\t0\t0\t1550000\n2026-02-11\tDEMO-202\tONE_LINE\tSHIPPER_B\tĐà Nẵng\tHải Phòng\t2100000\t0\t100000\t0\t2200000\nsai-dinh-dang\tDEMO-ERR\tSITC\tSHIPPER_C\tSài Gòn\tBình Dương\t1800000\t0\t0\t0\t1800000"]},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"paste\"]"},
       {"check": "[data-editor=\"2026-02\"] tbody tr:nth-child(3) [data-select]"},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"remove\"]"},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"save\"]"}]},
    {"name": "07-bo-het-bang-trong", "board": "07 · Trạng thái trống (Bỏ hết dòng nháp)", "note": "Tick cả 3 dòng rồi bấm Bỏ dòng đã chọn", "shot": "#month-2026-02",
     "steps": [{"select": ["#period", "2026-02"]}, {"click": "#filters button"}, {"click": "#month-2026-02 > summary"},
       {"click": "#month-2026-02 [data-action=\"open-editor\"]"},
       {"fill": ["[data-paste=\"2026-02\"]", "2026-02-10\tDEMO-201\tMAERSK\tSHIPPER_A\tHải Phòng\tSài Gòn\t1500000\t50000\t0\t0\t1550000\n2026-02-11\tDEMO-202\tONE_LINE\tSHIPPER_B\tĐà Nẵng\tHải Phòng\t2100000\t0\t100000\t0\t2200000\nsai-dinh-dang\tDEMO-ERR\tSITC\tSHIPPER_C\tSài Gòn\tBình Dương\t1800000\t0\t0\t0\t1800000"]},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"paste\"]"},
       {"check": "[data-editor=\"2026-02\"] tbody tr:nth-child(1) [data-select]"},
       {"check": "[data-editor=\"2026-02\"] tbody tr:nth-child(2) [data-select]"},
       {"check": "[data-editor=\"2026-02\"] tbody tr:nth-child(3) [data-select]"},
       {"click": "[data-editor=\"2026-02\"] [data-action=\"remove\"]"}]}
  ]
}
```

## Phạm vi agent

Mục này là hợp đồng với agent thực hiện; `scripts/agent-run.ps1` đọc nó để kiểm diff.

- Agent: gemini
- Mockup: CHỜ DUYỆT (khi duyệt ghi: ĐÃ DUYỆT <link page> · phiên bản "<tên version Penpot>" · <người> · <ngày>)
- Được sửa:
  - `cong-no-web-handoff/preview/customer-ledger-workbench.js`
  - `cong-no-web-handoff/preview/customer-ledger-workbench-ui.js`
  - `cong-no-web-handoff/preview/customer-ledger-workbench.css`
  - `cong-no-web-handoff/preview/test-customer-ledger-workbench.js`
  - `cong-no-web-handoff/preview/test-customer-ledger-browser.js`
- Ngân sách diff: 60 dòng
- Lệnh kiểm:
  - `npm run test:unit`
  - `npm run test:browser`
- Cấm:
  - Đổi `saveShipments`, cách tính tiền, trạng thái chuyến, tổng nợ hoặc bất kỳ luồng nào khác ngoài bảng nhập.
  - Format lại hoặc tách dòng các file đang viết dạng nén; thêm dependency, framework, helper hoặc file mới.
  - Đổi trường tiền, quyền, quy tắc nghiệp vụ; chạm dữ liệu thật.
- Khi cần vượt phạm vi: dừng, không tự mở rộng; nêu câu hỏi trong báo cáo cuối.

## Hoàn tác

Bỏ thao tác, hàm model và test vừa thêm; xóa page mockup trong Penpot nếu không dùng.

## Bằng chứng

<Link mockup đã duyệt; kết quả Lệnh kiểm; kết luận review.>

## Yêu cầu mockup

- Vẽ tỉ lệ 1:1, khung màn hình rộng 1500px như app; cỡ chữ đúng `customer-ledger-workbench.css` hiện có (thân/nút/ô nhập 14px, ô bảng 13px, tiêu đề cột 12px, tiêu đề tháng 16px, tổng còn nợ 29px). Tăng cỡ chữ là spec riêng [workbench-readability](workbench-readability.md).
- Số liệu, nhãn cột, nhãn tóm tắt tháng ("DƯ ĐẦU KỲ", "PHÁT SINH", "THANH TOÁN & CẤN TRỪ", "CÒN NỢ"), câu lỗi ("Sai ngày hoặc ngày không thuộc kỳ") và câu thông báo lấy đúng từ code/fixture ở mục "Đối chiếu dữ liệu"; tiền ghi đủ số, không viết tắt; không thêm câu ngoài UI hiện có và spec.
- Page chỉ gồm board màn hình và một board ghi chú ngắn.

Lịch sử góp ý từng lần nằm ở `feedback.md` trong thư mục log của nhánh (`worktrees/_logs/gemini-remove-draft-rows/`), ngoài repo.