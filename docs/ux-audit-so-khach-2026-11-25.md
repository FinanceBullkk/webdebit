# Audit màn Sổ khách và danh sách việc sửa (25/11/2026)

Trạng thái: **ĐỀ XUẤT** (Claude, theo skill [`thiet-ke-ux`](../.claude/skills/thiet-ke-ux/SKILL.md) và [`CLAUDE-ALL-01`](decisions/claude-all-01.md)). Người dùng chưa duyệt hướng sửa nào. Các quan sát ghi "đã thấy trên `hao`" là **ĐÃ KIỂM CHỨNG** theo cách ở mục 1. Tài liệu không đổi luật tiền, API hay DB; mục nào cần đổi API ghi rõ.

Mỗi mục có mã `SK-…` để PR trỏ tới. Mức theo [cách review một màn](../.claude/skills/thiet-ke-ux/reference/chong-giao-dien-ai.md#cách-review-một-màn-theo-design-review): **Chặn** (sai tiền, mất dữ liệu, không làm xong việc), **Nên sửa** (chậm, khó tìm, trái token), **Gợi ý**. Căn cứ học thuật lấy theo [nền tảng học thuật](../.claude/skills/thiet-ke-ux/reference/nen-tang-hoc-thuat.md).

## 1. Phạm vi và cách làm

- Màn: trang `so-khach-v7-live.html`, thẻ **Sổ** (chọn khách, đổi khách, thẻ tháng, phiếu thu, bảng chuyến). Không xét thẻ Tình hình, Trao đổi, Hồ sơ.
- Đi luồng trên `hao`, chỉ đọc: tìm khách → đọc sổ → mở Ghi phiếu thu tới bước Xem lại → sửa ô Đơn giá tới câu hỏi giá. Thoát bằng Esc, **không ghi phiếu, không lưu giá**. Sổ đã xem (mã sổ): 10, 52, 68, 104.
- Khung: Chrome trên Windows có thanh cuộn, 1351×543 và 1568×744. Chưa đo đúng 1280 vì cửa sổ đang phóng to trên màn 1366 và trang chặn nhúng khung. CSS của màn không có breakpoint nào trong khoảng 1100–1877px, nên ở 1280 bố cục theo cùng luật, chỉ hẹp hơn khoảng 70px (bảng tràn ngang thường hơn, xem SK-N1).
- Sau đó đọc CSS/JS của màn và chạy `node scripts/check-css-tokens.js`.
- **Chưa kiểm:** đúng 1280 rộng; 390px điện thoại; mất mạng; ghi phiếu trọn vẹn vào tháng khóa; người dùng thật đi hết luồng (bước cuối của [`UX-NEN-01`](decisions/ux-nen-01.md)). Một lần trang treo khi mở sổ 10 ở một trình duyệt; mở lại ở trình duyệt khác thì bình thường, chưa tái hiện được nên chưa xếp mức.

## 2. Tóm tắt

| Mã | Mức | Vấn đề một dòng | Đụng tiền |
| --- | --- | --- | --- |
| SK-C1 | Chặn | Tháng hiện tại chưa có số liệu thì Nợ đầu tháng và Còn nợ cuối tháng hiện "–" dù sổ còn nợ | có (hiển thị) |
| SK-C2 | Chặn | Enter ở ô Số tiền rồi Enter lần nữa là ghi phiếu: bước Xem lại bị trôi | có (ghi) |
| SK-N1 | Nên sửa | Tiêu đề cột bảng chuyến không dính khi bảng tràn ngang | |
| SK-N2 | Nên sửa | Đầu sổ có bốn tín hiệu về giá; màn đầu chỉ thấy 1–3 chuyến | |
| SK-N3 | Nên sửa | Hai nút chính tranh nhau ("Điền giá theo bảng" đậm hơn "Ghi phiếu thu") | |
| SK-N4 | Nên sửa | Nút "+ Ghi phiếu thu" đổi chỗ theo nội dung | |
| SK-N5 | Nên sửa | Tuyến, Shipper bị cắt chữ, không có chữ rê chuột; cột "Hãng tàu" chứa biển số ở sổ bộ | |
| SK-N6 | Nên sửa | Phím mũi tên không chạy ở ô tìm khách và bộ đổi khách | |
| SK-N7 | Nên sửa | Danh sách khách có nhãn trùng ở hai nhóm; bộ đổi khách thiếu "khách gần đây" | |
| SK-N8 | Nên sửa | Chip tháng thiếu năm, nhảy cóc; sổ mở sẵn tháng có thể cũ hơn một năm | |
| SK-N9 | Nên sửa | Bảng phiếu thu không có tiêu đề cột; phiếu từ Sheet có hai ô "–" không tên | |
| SK-N10 | Nên sửa | Ô Số tiền: lỗi không nói cách sửa, không nhóm nghìn khi gõ, lỗi cũ không tự xóa | có (nhập) |
| SK-N11 | Nên sửa | Nút tắt ở tháng khóa không nói lý do; ổ khóa có `aria-label` và `title` nói ngược nhau | |
| SK-N12 | Nên sửa | Chữ thân 14px, chi tiết 13px; nhiều nút dưới 40px | |
| SK-N13 | Nên sửa | Màn không nạp token chung; hai lớp CSS với hai bảng màu | |
| SK-G1…G8 | Gợi ý | Xem mục 5 | |

## 3. Chặn

### SK-C1. Tháng hiện tại chưa có số liệu: số nợ hiện "–"

- **Chỗ nào:** sổ 10 (API trả `total_outstanding_vnd` > 0), chip Tháng 11/2026: "Nợ đầu tháng –", "Còn nợ cuối tháng –". Sổ 68 cũng vậy (cuối tháng trước là 0). Code: [`so-khach-v7-month-ui.js:117-118`](../cong-no-web-handoff/preview/so-khach-v7-month-ui.js) in `item.prior_months_vnd` và `item.end_of_month_vnd`, hai trường này null với tháng không có trong `months` của GET sổ.
- **Vấn đề:** số đã biết hiện như chưa biết. Thiết kế 2/11 đã bỏ dòng "Khách còn nợ" ở đầu sổ (số nợ chỉ ở dòng cuối thẻ tháng), nên khi tháng hiện tại chưa có chuyến, cả thẻ Sổ không còn chỗ nào cho thấy nợ hôm nay. Nút "+ Ghi phiếu thu" nằm ngay cạnh.
- **Tác động:** người dùng đọc "–" thành "hết nợ" hoặc "chưa có số" ngay lúc ghi tiền. Bước Xem lại có in tổng còn nợ trước → sau nên đỡ một phần, nhưng lúc đó đã gõ xong số.
- **Căn cứ:** Nielsen #1 (trạng thái hệ thống); Reason, Norman (nhầm hiểu: chặn bằng cách hiện đúng bối cảnh); luật NULL không phải 0 của `AGENTS.md` bị dùng ngược.
- **Hướng sửa (ĐỀ XUẤT):** GET sổ luôn trả dòng của tháng hiện tại trong `months` (Nợ đầu tháng = cuối tháng trước, Phát sinh 0, Khách trả 0, Còn nợ = Nợ đầu tháng). Giữ đúng điểm (3) của [`SO-GON-05`](decisions/so-gon-05.md): số lấy nguyên từ GET, trang không tự tính. Đây là đổi API đọc (`specs/v7-backend/`, theo runbook), không đổi luật tiền.
- **Tiêu chí xong:** sổ còn nợ, tháng hiện tại không có dòng → thẻ tháng hiện tại có Nợ đầu tháng bằng Còn nợ cuối tháng của tháng gần nhất và bằng `total_outstanding_vnd`; không còn "–" ở hai ô này. Harness PostgreSQL có ca này. Đối soát tổng khách không đổi sau deploy.

### SK-C2. Enter, Enter là ghi phiếu thu

- **Chỗ nào:** [`so-khach-v7-entry-ui.js:99`](../cong-no-web-handoff/preview/so-khach-v7-entry-ui.js) (và dòng 60 khi mở lại khung ở bước xem lại): sang bước Xem lại thì tiêu điểm vào nút **Ghi phiếu**. Đã thấy trên `hao`: `document.activeElement` là `button.receipt-save`.
- **Không nhất quán trong cùng màn:** câu hỏi giá nghi sai ở ô Đơn giá đặt tiêu điểm vào nút an toàn **Sửa lại** ([`so-khach-v7-edit-ui.js:54`](../cong-no-web-handoff/preview/so-khach-v7-edit-ui.js)).
- **Tác động:** người gõ theo thói quen Sheet (Enter, Enter) ghi tiền mà không đọc dòng trước → sau. Đây là trượt tay, đúng loại mục tiêu số 1 của web muốn chặn.
- **Căn cứ:** Reason, Norman (trượt tay); Shneiderman #5 (phòng lỗi); xác nhận theo thói quen mất tác dụng.
- **Hướng sửa (ĐỀ XUẤT):** sang bước Xem lại thì tiêu điểm vào câu tóm tắt (`tabindex="-1"`, đọc được bằng trình đọc màn hình), không vào nút Ghi phiếu; Enter ngay sau khi đổi bước, hoặc phím giữ lặp (`event.repeat`), không ghi. Một luật chung cho mọi hộp xác nhận đụng tiền của màn: tiêu điểm mặc định không nằm trên nút ghi.
- **Tiêu chí xong:** test trình duyệt: gõ ngày, số tiền, Enter, Enter → không có lệnh ghi nào gửi đi, bước Xem lại vẫn mở; Tab tới Ghi phiếu rồi Enter → ghi đúng một lệnh. Test cũ của luồng ghi phiếu vẫn xanh.

## 4. Nên sửa

### SK-N1. Tiêu đề cột không dính khi bảng tràn ngang

- **Chỗ nào:** `.ledger-book.fee-over .ledger-head{position:static}` ở [`so-khach-v7-priority.css:74`](../cong-no-web-handoff/preview/so-khach-v7-priority.css). Sổ 52 và 104: cuộn xuống thì mất tên các cột phí. Lý do kỹ thuật: bảng nằm trong `.trip-card{overflow-x:auto}` để ghim Thành tiền bên phải ([`SO-GON-07`](decisions/so-gon-07.md) (3)); `sticky` chỉ dính theo vùng cuộn gần nhất nên không dính theo trang được nữa.
- **Tác động:** tám cột phí toàn "–" sát nhau, người dùng phải nhớ cột nào là phí gì.
- **Căn cứ:** Nielsen #6 (nhận ra hơn nhớ lại); Cowan (trí nhớ làm việc khoảng 4 mục).
- **Hướng sửa (ĐỀ XUẤT):** một trong hai: bảng có vùng cuộn riêng (cao cố định theo màn, cuộn cả hai chiều, tiêu đề và Thành tiền cùng dính); hoặc hàng tiêu đề tách ra, cuộn ngang đồng bộ bằng JS với thân bảng. Chọn sau khi đo ở 1280×560.
- **Tiêu chí xong:** ở 1280 có thanh cuộn, sổ có ≥ 6 cột phí đang hiện: cuộn tới chuyến cuối vẫn thấy hàng tiêu đề và cột Thành tiền.

### SK-N2. Đầu sổ có bốn tín hiệu về giá; màn đầu chỉ thấy 1–3 chuyến

- **Chỗ nào:** sổ 104 có cùng lúc nút "Điền giá theo bảng (1 chuyến)", ô "Giá từ Sheet cần xem: 24", dải "1 chuyến thiếu đơn giá được tô vàng" (khi có `?loc=`), chip "1 chưa giá". Dòng chuyến đầu bắt đầu ở 499px trong khung cao 543px.
- **Vấn đề:** [`SO-GON-06`](decisions/so-gon-06.md) (2) đã chốt một thanh việc ở đầu sổ; nay lại thành nhiều dải. Hai con số (24 và 1) nói về cùng chuyện giá mà không giải thích khác nhau thế nào.
- **Căn cứ:** Hick–Hyman; mù banner (Benway, Lane); Few.
- **Hướng sửa (ĐỀ XUẤT):** gom về một thanh việc theo `SO-GON-06`, mỗi loại việc một mục có số và một động từ; dải `?loc=` thành trạng thái của mục tương ứng, không thành dải riêng.
- **Tiêu chí xong:** ở 1280×560, sổ có việc giá: phần trên thẻ tháng cao ≤ một thanh; thấy ít nhất 5 dòng chuyến khi cuộn tới đầu bảng.

### SK-N3. Hai nút chính tranh nhau

- **Chỗ nào:** "Điền giá theo bảng" có nền đậm nhất màn, đặt trên "+ Ghi phiếu thu".
- **Căn cứ:** Hick; thứ bậc thị giác (một vùng một nút chính).
- **Hướng sửa (ĐỀ XUẤT):** việc trong thanh việc dùng kiểu nút phụ; chỉ "+ Ghi phiếu thu" là nút chính của thẻ Sổ. Gộp vào SK-N2.

### SK-N4. Nút "+ Ghi phiếu thu" đổi chỗ theo nội dung

- **Chỗ nào:** `.pay-block{width:fit-content;min-width:min(640px,100%)}` ở [`so-khach-v7-priority.css:147`](../cong-no-web-handoff/preview/so-khach-v7-priority.css). Đã thấy nút ở x≈1034–1168 (sổ 104, tháng trống của sổ 68) và x≈1191–1327 (tháng có phiếu tham chiếu dài của sổ 68).
- **Tác động:** người lớn tuổi dựa vào trí nhớ vị trí; nút chạy chỗ thì phải tìm lại.
- **Căn cứ:** Fitts; Shneiderman #1 (nhất quán).
- **Tiêu chí xong:** mọi sổ, mọi tháng: nút cùng một vị trí ngang (đo `getBoundingClientRect().right` bằng nhau).

### SK-N5. Chữ bị cắt mà không có chữ rê chuột

- **Chỗ nào:** cột Tuyến (`td.route-cell`) và Shipper (`.info-edit`). Sổ 104: 55 ô bị cắt, 0 ô có `title`; phần "nơi đến" thường mất hẳn. Ở sổ chuyến bộ (sổ 68), cột "Hãng tàu" chứa biển số xe.
- **Căn cứ:** Nielsen #2 (khớp ngôn ngữ), #6.
- **Hướng sửa (ĐỀ XUẤT):** ô bị cắt có `title` đủ chữ; Tuyến ưu tiên giữ nơi đến (cắt nơi đi trước, hoặc hai dòng nhỏ); nhãn cột theo loại sổ ("Xe" cho sổ bộ) nếu dữ liệu xác nhận được.
- **Tiêu chí xong:** rê chuột ô bị cắt thấy đủ chữ; test kiểm `title` cho ô có `scrollWidth > clientWidth`.

### SK-N6. Phím mũi tên không chạy ở ô tìm khách

- **Chỗ nào:** ô "Tìm khách" của trang chọn khách và ô trong bộ đổi khách. Chỉ ô tìm ở menu trái có xử lý mũi tên ([`app-nav.js:94-100`](../cong-no-web-handoff/preview/app-nav.js)). Ở trang chọn khách, mục đầu được tô như đang chọn nhưng mũi tên không dời; Tab tới mục khác thì hai ô cùng được tô.
- **Căn cứ:** Nielsen #4 (nhất quán), #7 (linh hoạt cho người thạo).
- **Hướng sửa (ĐỀ XUẤT):** dùng chung một cách xử lý với `app-nav.js` (mũi tên dời mục, Enter mở, Esc đóng), một mục được tô tại một lúc.
- **Tiêu chí xong:** test trình duyệt: gõ, ↓ ↓, Enter → mở khách thứ hai của kết quả.
- **Đã làm (đợt 5, 25/11/2026; chưa merge/triển khai khi viết dòng này):** `so-khach-v7-api.js` — con trỏ ở lại ô tìm; gõ xong dòng đầu được tô (là dòng Enter mở), ↓ ↑ dời dòng tô (dừng ở hai đầu), Enter mở dòng tô, Tab/rê chuột tới dòng nào thì chỉ dòng đó được tô (`.is-active`, thay luật `:first-of-type` và `:hover` trong CSS), Esc xóa chữ ở trang chọn khách (trong hộp đổi khách Esc đóng hộp như cũ). Vì dòng đầu đã tô sẵn nên một ↓ tới khách thứ hai. Ô tìm ở menu trái (`app-nav.js`) giữ cách cũ, không đổi.

### SK-N7. Dễ mở nhầm sổ từ danh sách khách

- **Chỗ nào:** cùng một nhãn tên xuất hiện ở hai nhóm mặt hàng ("Bán cước" và "Chuối"), không có gì cho biết là một sổ hay hai sổ. Bộ đổi khách không có "khách gần đây" như thiết kế đã chốt 2/11 trên canvas.
- **Căn cứ:** trượt tay (Reason); Nielsen #6.
- **Hướng sửa (ĐỀ XUẤT):** nhãn trùng thì thêm dấu phân biệt (mặt hàng hoặc mã sổ); bộ đổi khách có 5 khách mở gần nhất ở đầu.
- **Đã làm (đợt 5, 25/11/2026; chưa merge/triển khai khi viết dòng này):** `so-khach-v7-api.js` — tên rút gọn trùng ở hai nhóm thì dòng giữ nhãn đủ "Tên · Mặt hàng" (tên không trùng vẫn gọn như `SO-GON-…`); chưa gõ thì nhóm "Gần đây" (≤ 5 khách mở gần nhất, mới nhất trước, bỏ khách đang mở, nhãn đủ mặt hàng) nằm đầu danh sách, cả ở hộp đổi khách lẫn trang chọn khách. Danh sách nhớ trong `localStorage` của trình duyệt (`webdebit.recentCustomers.v1`, chỉ id số, tối đa 10), không gửi lên máy chủ; chế độ riêng tư thì không có "Gần đây". Không đổi `customerLabels` (sổ cùng nhãn đủ vẫn có " · sổ <id>").

### SK-N8. Chip tháng thiếu năm, nhảy cóc

- **Chỗ nào:** dãy chip dạng "T7/2025 · Tháng 8/2025 · T11", trong đó T11 là 11/2026. `monthTag` ([`cong-no-format.js:129`](../cong-no-web-handoff/preview/cong-no-format.js)) chỉ bỏ năm khi trùng năm hiện tại, nên chip ngay sau "Tháng 8/2025" không có năm và dễ bị đọc thành 11/2025. Tháng không có số liệu bị ẩn, không có dấu báo khoảng trống 15 tháng. Sổ mở sẵn tháng gần nhất có số liệu ([`SO-GON-05`](decisions/so-gon-05.md) (2)), có khi cũ hơn một năm, trong khi phiếu bấm từ đó rơi vào tháng của ngày trả.
- **Căn cứ:** nhầm hiểu bối cảnh tháng (Reason); Nielsen #1; Gestalt (liên tục: chip đứng cạnh nhau được đọc như một dãy liền).
- **Hướng sửa (ĐỀ XUẤT):** chip đầu tiên của mỗi năm có năm (theo chip đứng trước, không theo năm hiện tại); khoảng trống nhiều tháng có dấu "…" kèm số tháng. Đi cùng SK-C1 (tháng hiện tại luôn có chip có số).

### SK-N9. Bảng phiếu thu không có tiêu đề cột

- **Chỗ nào:** khối "Khách trả trong tháng". Phiếu từ Sheet in hai ô "–" không tên ([`so-khach-v7-pay-ui.js:67`](../cong-no-web-handoff/preview/so-khach-v7-pay-ui.js)).
- **Căn cứ:** Nielsen #2, #6.
- **Tiêu chí xong:** có hàng tiêu đề (Ngày trả, Hình thức, Tham chiếu, Số tiền) hoặc ô trống của phiếu Sheet ghi rõ ("Sheet không ghi ngày").

### SK-N10. Ô Số tiền không giúp người gõ

- **Chỗ nào:** lỗi "Số tiền không hợp lệ." ([`so-khach-v7-model.js:209`](../cong-no-web-handoff/preview/so-khach-v7-model.js)). Gõ `1234567` không hiện dấu chấm ngăn nghìn. Lỗi cũ còn trên màn sau khi đã gõ lại đúng, tới lần bấm Xem lại sau.
- **Tác động:** thừa hay thiếu một số 0 khó thấy; câu lỗi không chỉ cách sửa.
- **Căn cứ:** Nielsen #9; phòng trượt tay.
- **Hướng sửa (ĐỀ XUẤT):** câu lỗi nói dạng đúng ("Chỉ gõ chữ số, có hoặc không có dấu chấm ngăn nghìn; không gõ chữ như tr, k"); nhóm nghìn khi rời ô hoặc hiện số đã hiểu ngay dưới ô; xóa lỗi khi người dùng sửa ô.

### SK-N11. Trạng thái khóa nói không rõ

- **Chỗ nào:** "+ Điều chỉnh cả tháng" ở tháng khóa bị tắt, không có chữ lý do. Nút ổ khóa: `aria-label` "Mở khóa tháng …" nhưng `title` "Đã khóa" ([`so-khach-v7-month-ui.js:112-113`](../cong-no-web-handoff/preview/so-khach-v7-month-ui.js)).
- **Căn cứ:** Nielsen #1, #9.
- **Tiêu chí xong:** nút tắt có chữ rê chuột "Tháng đang khóa, mở khóa trước"; `title` và `aria-label` nói cùng một ý (hành động kèm trạng thái).

### SK-N12. Chữ nhỏ, vùng bấm nhỏ

- **Chỗ nào:** `body` 14px ([`so-khach-v7-priority.css:3`](../cong-no-web-handoff/preview/so-khach-v7-priority.css)), bảng 14px, chi tiết phân bổ phiếu 13px. Nút dưới chuẩn 40px của dự án (mục 4.4 [audit UX](ux-audit-2026-10-31.md)): nút công cụ bảng 36×36, "Xem" 38×30, "+ Điều chỉnh cả tháng" 149×30, chip "chưa giá" 94×26, nút đính ảnh 28×24.
- **Căn cứ:** Fisk và cộng sự (người dùng lớn tuổi: chữ thân 15–16); Fitts; WCAG 2.5.8.
- **Hướng sửa (ĐỀ XUẤT):** đổi cùng SK-N13 (một thang chữ), không thu nhỏ để nhét thêm.

### SK-N13. Màn không dùng token chung

- **Chỗ nào:** `so-khach-v7-live.html` không nạp [`cong-no-theme.css`](../cong-no-web-handoff/preview/cong-no-theme.css). `so-khach-v7.css` và `so-khach-v7-priority.css` cùng khai lại 45 bộ chọn, kể cả `:root` và `body`, với hai bảng màu (một bộ xám ngả xanh, một bộ xám trung tính).
- **Số đo `lint:tok`** (11 file CSS của màn và trang HTML, gồm `cong-no-theme.css`):

  | Loại | Màn Sổ khách | Cả `preview/` |
  | --- | --- | --- |
  | Màu viết thẳng | 1108 | 1798 |
  | Cỡ chữ ngoài thang | 31 | 92 |
  | Bo góc tự đặt | 188 | 418 |
  | Viền màu một bên | 13 | 23 |

  Riêng các file `so-khach-v7*.css`: 304 mã màu hex khác nhau, 14 cỡ chữ khác nhau (thang chuẩn có 7).
- **Hướng sửa (ĐỀ XUẤT):** nạp `cong-no-theme.css`, chuyển dần từng khối sang `var(--…)` khi đụng tới, chạy `node scripts/check-css-tokens.js --update` để hạ mức trần. Không làm một PR "đổi màu cả màn".

## 5. Gợi ý

- **SK-G1.** Chỗ ghi "0", chỗ ghi "0 đ", chỗ ghi "–": đơn vị "đ" chỉ có ở dòng Còn nợ cuối tháng ([`so-khach-v7-month-ui.js:117`](../cong-no-web-handoff/preview/so-khach-v7-month-ui.js)).
- **SK-G2.** Dấu "–" ở ô phí tương phản 3,0:1, dưới 4,5:1 của WCAG 1.4.3.
- **SK-G3.** Câu hỏi giá nghi sai hiện ở mép trái hàng, cách ô đang sửa khoảng 600px (Gestalt: gần nhau).
- **SK-G4.** Ô Đơn giá đang sửa cao gấp đôi vì chữ "đồng, không phải triệu" xuống dòng, cả bảng nhảy.
- **SK-G5.** Tháng chưa có phiếu nói hai lần: "· 0 phiếu" và "Chưa có phiếu thu".
- **SK-G6.** Thẻ "Sổ" có "2 việc chờ" chỉ trong `aria`, mắt không thấy.
- **SK-G7.** Lựa chọn hiện/ẩn cột phí trống nhớ theo trình duyệt mà màn không báo; hai máy đã thấy cùng sổ hiện 8 cột và 1 cột phí.
- **SK-G8.** Chuyến xếp theo dòng Sheet, không theo ngày: đúng chủ đích giữ giống Sheet, chỉ ghi để biết.

## 6. Dấu hiệu "trông như AI"

Theo danh sách bỏ trong [chống giao diện AI](../.claude/skills/thiet-ke-ux/reference/chong-giao-dien-ai.md):

- Viền màu một bên: 13 chỗ, ví dụ viền trái dày của khung Ghi phiếu thu (`.entry-drawer`), `.saved-strip`, `.price-panel.confirm`, `.price-panel.err`.
- Hai bảng màu chồng nhau (SK-N13): dấu vết mỗi lần sửa thêm giá trị mới thay vì dùng lại.
- Bo góc khoảng 10 giá trị khác nhau (2, 3, 4, 6, 8, 9, 10, 12, 13, 20px) không qua `var(--radius)`.
- Cỡ chữ ngoài thang: 17, 19, 20, 24, 26, 30, 32, 34px.
- Chữ IN HOA trong ô chọn Hình thức ("THU TIỀN", "CẤN TRỪ").
- Dải nền ba màu cho nhóm cột: có mang thông tin nhóm, nhưng khi tám cột phí toàn "–" thì thành mảng trang trí.
- Không thấy: gradient, kính mờ, lưới card giống nhau, hiệu ứng trượt khi khối xuất hiện.

## 7. Chỗ đang làm tốt (giữ khi sửa)

- Ngày trả tương lai bị chặn; lỗi hiện cạnh ô, tiêu điểm về ô sai đầu tiên.
- Bước Xem lại phiếu thu cho thấy tổng còn nợ trước → sau và cảnh báo khách dư.
- Chip "chưa giá" nhảy tới đúng dòng và ghi `?loc=` lên địa chỉ.
- Đơn giá ngoài khoảng 1 triệu – 1 tỷ thì hỏi lại; tiêu điểm vào Sửa lại.
- Esc lùi từng bước; viền focus thấy rõ; menu "⋯" đóng thì không bắt tiêu điểm.

## 8. Đợt sửa đề xuất

Chia để mỗi PR một vùng file, chạy song song được:

| Đợt | Mục | File chính | Cần gì trước |
| --- | --- | --- | --- |
| 1 | SK-C2, SK-N10 | `so-khach-v7-entry-ui.js`, `so-khach-v7-model.js` | Không; test trình duyệt luồng ghi phiếu |
| 2 | SK-C1, SK-N8 | API sổ (`specs/v7-backend/`), `so-khach-v7-month-ui.js`, `cong-no-format.js` | Spec trước; deploy theo [runbook](v7-deploy-runbook.md), đối soát tổng khách |
| 3 | SK-N2, SK-N3, SK-N4, SK-N9, SK-N11 | `so-khach-v7-priority.css`, `so-khach-v7-pay-ui.js`, `so-khach-v7-ui.js` | Phác thảo thanh việc cho người dùng chọn (bước 2 của skill) |
| 4 | SK-N1, SK-N5 | `so-khach-v7-trips-ui.js`, `so-khach-v7-priority.css` | Đo hai phương án ở 1280×560; sau đợt 3 nếu cùng sửa `priority.css` |
| 5 | SK-N6, SK-N7 | `so-khach-v7-api.js`, `so-khach-v7-tabs-ui.js`, `app-nav.js` | Không |
| dần | SK-N12, SK-N13, SK-G… | CSS của màn | Làm kèm khi đụng tới, hạ mức trần `lint:tok` |

Mỗi PR: ảnh render dữ liệu giả ở 1280×720 có thanh cuộn, mở `hao` chỉ đọc trước khi báo xong, ghi mã `SK-…` đã đóng. Mục nào đổi một quyết định đã chốt (`SO-GON-05`, `SO-GON-06`, `SO-GON-07`) thì ghi quyết định mới trước khi code.
