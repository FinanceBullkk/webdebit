# V7 — Tổng quan v2: mỗi câu hỏi một hình (đổi cách trình bày DASH-03)

Trạng thái: **ĐÃ CHỐT** ([`DASH-04`](../docs/decisions/dash-04.md), người dùng 30/10/2026: "Theo v2, viết spec" sau khi xem layout thử). Nguồn: góp ý người dùng trong chat 30/10/2026 — Tổng quan "ghi nhiều thông tin quá, thay vì biểu diễn thì chọn ghi chữ, nhìn vào full of text"; yêu cầu thiết kế lại ở mức kiến trúc: nên biểu diễn dữ liệu gì, kiểu gì. Layout thử dữ liệu giả: [`preview/mockups/tong-quan-v2/`](../cong-no-web-handoff/preview/mockups/tong-quan-v2/index.html).

Spec này **thay cách trình bày** của [`v7-tong-quan-quan-ly-no.md`](v7-tong-quan-quan-ly-no.md) (DASH-03) và **giữ nguyên** mọi quy tắc tính ở đó: hạn trả, 5 nhóm, mức rủi ro, lần trả/đi hàng gần nhất, thu/phát sinh tháng này, API `get_dashboard_debt()`. Không đổi backend.

## Nguyên tắc (bước 0)

Audit 30/10/2026 trên màn 1280×720: khoảng 125 mẩu chữ, một số lặp tới 3 lần (ô "Khách rủi ro cao", câu dẫn và dòng đầu khối Phân loại), câu kết luận kể lại thứ thanh đã vẽ, % lặp lại độ rộng đoạn, lý do là câu chạy không quét mắt được. Nguyên nhân là DASH-03 yêu cầu "một câu kết luận" và "một câu lý do" cho mỗi khối. Nguyên tắc mới:

1. **Mỗi câu hỏi nghiệp vụ một hình; số nằm trong hình**, không ghi lại bên cạnh. Mỗi khối đúng một số headline.
2. **Không câu kết luận.** Kết luận là thứ hình phải tự nói; cần chữ là dấu hiệu hình chưa đúng. Chữ chỉ là nhãn, chú giải ghi một lần, tooltip và ngăn kéo.
3. **Thời gian = số + màu ngưỡng**, không viết thành câu.
4. **Một thang tiền** trên cả trang: dạng rút gọn `F.short` ("8,79 tỷ", "344,6 triệu"); bảng dùng tỷ với hai chữ số thập phân và ghi đơn vị một lần ở đầu cột.
5. **Màu có nghĩa, không trang trí**: xanh = trong hạn (hai bậc), cam → đỏ = quá hạn theo tuổi, xanh lá = tiền thu về, xám = chưa rõ. Đỏ chỉ cho quá hạn hoặc vượt ngưỡng.

## Người dùng và luồng (bước 1)

| Người xem | Lúc nào | Câu hỏi | Hình trả lời |
| --- | --- | --- | --- |
| Chủ nghiệp vụ | Cuối tuần/tháng, trước khi gọi đòi nợ | 1. Khách nợ bao nhiêu, bao nhiêu đã quá hạn, quá bao lâu? | Thanh hạn trả lớn (khối 1) |
| | | 2. Thu tháng này có kịp nợ mới không? | Thước đo tháng (khối 2) |
| | | 3. Ai cần đòi trước, vì sao? | Bảng khách có cột cơ cấu nợ cùng thang và hai cột số ngày (khối 3) |
| | | 4. Khách quá hạn đang ở đâu? | Ma trận 2×2 trả gần nhất × đi hàng gần nhất (khối 4) |
| Người nhập | Cuối ngày | Còn việc gì? | Tab Việc cần làm, không đổi |

Luồng: đọc hàng trên (khối 1, 2) → bấm một đoạn/nhãn hạn trả hoặc một ô ma trận → bảng lọc tại chỗ (dải "Đang lọc" với chip, bỏ từng chip hoặc bỏ hết) → bấm một khách → ngăn kéo (còn nợ, quá hạn, vì sao, nợ theo tháng) → "Mở sổ khách" hoặc "Xem ở ma trận". Giữ nguyên tương tác đã chốt ở DASH-01/03: lọc tại chỗ, ngăn kéo, trạng thái trên địa chỉ trang, soi sâu ở Công nợ theo tháng, không so tháng trước.

## Đầu ra

- Tổng quan gồm bốn khối: 1. Nợ theo hạn trả (gộp "Còn phải thu") · 2. Thu tháng này · 3. Khách cần đòi trước · 4. Khách quá hạn đang ở đâu.
- Trên 1280×720: hàng trên (khối 1, 2) và đầu bảng nằm trọn màn đầu; không cuộn ngang; 390px không cuộn ngang.
- Mọi số khớp server; tổng 5 đoạn = `receivable_vnd`; tổng 4 ô ma trận = `summary.overdue_customers` và `summary.overdue_vnd`.

## Nội dung

| Khối | Hiện gì | Cách vẽ | Chữ còn lại |
| --- | --- | --- | --- |
| **1. Nợ theo hạn trả** (span 8) | Còn phải thu (số headline, số khách), 5 nhóm hạn trả, tổng trong hạn / quá hạn | Dòng tiêu đề: "Còn phải thu **67,89 tỷ** · 67 khách đang nợ", ⓘ tooltip quy tắc hạn trả. **Ngoặc** trên thanh chia hai phần: "Trong hạn X" (xanh) và "Quá hạn Y · p% · n khách" (đỏ). **Thanh 52px** 5 đoạn theo tỉ lệ, số tiền ghi *trong* đoạn khi đoạn ≥ 7% tổng; dưới mỗi đoạn đủ rộng: tên nhóm + tháng nợ ("1–2 tháng / nợ T7–T8"), thẳng hàng với đoạn. Đoạn hẹp (< 7%) không ghi trong thanh, liệt kê một dòng nhỏ "Đoạn hẹp: ■ trên 6 tháng 2,61 tỷ (nợ T2 về trước)". Bấm đoạn hoặc nhãn = lọc bảng; tooltip giữ như cũ (nhóm, tiền, %, số khách, tháng nợ, số đồng) | Tiêu đề, 2 nhãn ngoặc, tên nhóm + tháng nợ |
| **2. Thu tháng này** (span 4) | Đã thu, phát sinh, hôm nay là ngày mấy của tháng | **Thước đo** 30px: nền = phát sinh tháng này, phần xanh lá = đã thu (tỉ lệ đã thu / phát sinh, cắt ở 100%), vạch đứt "hôm nay d/m" tại vị trí ngày/số ngày của tháng (`as_of`, giờ VN). Dưới thước: "**344,6 triệu** đã thu · 3,8%" (trái) và "**9,04 tỷ** phát sinh tháng này" (phải). Phát sinh = 0: thước trống, ghi "chưa phát sinh"; đã thu > phát sinh: thước đầy, % vẫn ghi đúng. Chú thích một dòng nhỏ (giữ của DASH-03): "Chưa tính N chuyến thiếu đơn giá · k khách đang dư Z" | Tiêu đề, 2 số có nhãn, chú thích |
| **3. Khách cần đòi trước** (span 8) | 10 khách xếp theo tiền quá hạn (bấm đầu cột để xếp theo Còn nợ, Chưa trả, Đi hàng) | **Bảng** 6 cột: Khách (chấm màu mức rủi ro + tên Sheet) · Cơ cấu nợ (thanh 12px 5 màu nhóm hạn trả, **cùng thang**: dài nhất = khách nợ nhiều nhất đang hiện) · Quá hạn (đậm đỏ) · Còn nợ (xám) · Chưa trả (số ngày) · Đi hàng (số ngày). Số ngày: ≤ 90 ghi "92 ngày", lâu hơn ghi "7 tháng" (`ago`); chưa trả lần nào ghi "chưa trả", chưa có chuyến ghi "chưa có" — không ghi 0. Màu: vượt ngưỡng rủi ro (60 / 90 ngày, hoặc chưa có) đỏ đậm; 31 ngày tới ngưỡng vàng; còn lại thường. Chú giải một lần dưới bảng: "● Rủi ro cao ● Theo dõi · ngày đỏ: chưa trả > 60 · không đi hàng > 90". Mỗi dòng có `title` = tên mức rủi ro + lý do (chữ, cho máy đọc và rê chuột); ngăn kéo vẫn hiện câu lý do đầy đủ. Khi đang lọc theo nhóm hạn trả, cột "Quá hạn" đổi thành "Nợ nhóm này" như cũ | Tiêu đề, 6 đầu cột, tên khách, số, chú giải |
| **4. Khách quá hạn đang ở đâu** (span 4) | Chỉ khách **có nợ quá hạn**, chia theo hai yếu tố của quy tắc rủi ro | **Ma trận 2×2**: cột "Có trả trong 60 ngày" / "Trên 60 ngày chưa trả" (gồm chưa trả lần nào); hàng "Còn đi hàng" / "Ngừng đi hàng > 90 ngày" (gồm chưa có chuyến). Mỗi ô: "**n khách**" và "quá hạn X". Nền ô theo số yếu tố xấu: 0 xanh nhạt, 1 vàng nhạt, 2 đỏ nhạt (ô dưới-phải, số tiền đỏ). Ô trống ghi "0 khách". Bấm ô = lọc bảng (bấm lại bỏ). Tooltip: tên ô, tiền, % còn phải thu, số khách | Tiêu đề, 2 nhãn cột, 2 nhãn hàng, 4 ô |
| **Bộ lọc Mặt hàng** | Mặt hàng (như `com` của DASH-03: sầu riêng cảng/bộ, mặt hàng dưới 1% gom "Khác", "Chưa phân loại") | `<select>` ở góc phải tiêu đề bảng "Mặt hàng: tất cả ▾"; chọn = lọc bảng (chip như nhóm khác) | 1 select |
| **Bỏ** | Ô "Khách rủi ro cao" ở Còn phải thu, dòng số đồng đầy đủ, câu kết luận khối hạn trả, 5 ô chú giải và %, câu lý do từng dòng, nhãn "Rủi ro cao" lặp từng dòng, khối Phân loại 5 tab, tiêu chí Quy mô (thanh cùng thang đã cho thấy tập trung nợ) | — | — |

Quy tắc đếm ngày của khối 3 và 4 dùng đúng ngưỡng `rule` của API (`no_pay_days`, `no_trip_days`, `active_trip_days`), không viết cứng.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Thông tin | Nguồn | Tình trạng |
| --- | --- | --- |
| Còn phải thu, số khách, chuyến thiếu giá, khách dư | `get_dashboard()` | Có, dùng nguyên |
| 5 nhóm hạn trả, tổng quá hạn, số khách quá hạn | `get_dashboard_debt().due_tiers`, `.summary` | Có |
| Đã thu / phát sinh tháng này | `.this_month` | Có; vị trí "hôm nay" tính từ `as_of` ở frontend |
| Từng khách: `tiers_vnd`, `overdue_vnd`, `pay_days`, `trip_days`, `risk` | `.customers[]` | Có; ma trận và hai cột ngày gom ở frontend (`dashboard-v7-model.js`), không cần hàm SQL mới |
| Mức rủi ro có yếu tố thứ ba (quá hạn ≥ 3 tháng) | `.customers[].risk` từ server | Giữ nguyên; ma trận chỉ chia theo hai yếu tố ngày, chấm màu trong bảng vẫn theo `risk` server nên một khách ở ô "tốt" vẫn có thể là Rủi ro cao vì nợ ≥ 3 tháng — ngăn kéo giải thích |

## Giao tiếp frontend–backend

Không đổi. Vẫn `GET /api/v7/dashboard` và `GET /api/v7/dashboard/debt` như [`v7-tong-quan-quan-ly-no.md`](v7-tong-quan-quan-ly-no.md). API debt lỗi: khối 1 chỉ hiện số headline, khối 2–4 báo "Chưa tải được…" như cũ. Danh sách khách không khớp tổng server (`totalsMatch` sai): không lọc tại chỗ, bấm đoạn/ô mở Công nợ theo tháng như cũ.

Trạng thái trên địa chỉ trang giữ: `?han=` (0–4), `?nhom=mx:<pay><trip>` (ví dụ `mx:p1t1`) hoặc `?nhom=com:<mặt hàng>`, `?xep=tong|chua-tra|di-hang`, `?khach=`. Giá trị `nhom` của tiêu chí đã bỏ (`risk`, `pay`, `trip`, `size`) bị bỏ qua.

## Hành vi và bất biến

- VND nguyên (BigInt ở frontend); tổng 5 đoạn = `receivable_vnd`; tổng 4 ô = `summary.overdue_vnd` và `summary.overdue_customers`.
- NULL không phải 0: `pay_days`/`trip_days` null ghi "chưa trả"/"chưa có" và coi là lâu nhất (xếp đầu khi xếp theo cột ngày); phát sinh tháng 0 không chia.
- Ngày theo giờ VN từ `as_of`, không `new Date()` cho nghiệp vụ.
- Trang chỉ đọc. Không đổi `get_dashboard_debt`, `get_ledger`, đường ghi tiền, phân bổ.
- Mức rủi ro vẫn có chữ: chú giải một lần + `title` từng dòng + ngăn kéo (không chỉ màu).
- Tab Việc cần làm, số trên thanh điều hướng, PRESENCE-01 không đổi.

## Tiêu chí nghiệm thu

- [ ] `test-dashboard-v7-model.js`: ma trận 2×2 (4 ô, khách chưa trả lần nào / chưa có chuyến vào ô xấu, tổng = overdue), xếp theo cột ngày với null cuối, tiến độ tháng (phát sinh 0, thu vượt phát sinh, ngày cuối tháng).
- [ ] `test-v7-dashboard-browser.js` 1280×720 và 390px: bốn khối, số trong đoạn, đoạn hẹp liệt kê, thước tháng có vạch hôm nay, bảng 6 cột với số ngày và màu, ma trận bấm = lọc kết hợp với nhóm hạn trả, select mặt hàng, chip bỏ lọc, URL, ngăn kéo/ESC, API debt lỗi, tổng lệch → mở ma trận.
- [ ] `npm run check` xanh.
- [ ] Người dùng tự đi hết luồng trên bản thử (dữ liệu giả) và trên `hao` sau deploy, xác nhận ma trận 2×2 đọc hiểu được; nếu không, phương án lùi là 4 thanh ngang cùng nhãn (không đổi dữ liệu).

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`).
- Được sửa: `preview/dashboard-v7.js`, `preview/dashboard-v7.css`, `preview/dashboard-v7-model.js`, hai test tương ứng, `preview/mockups/tong-quan-v2/`, spec và quyết định.
- Cấm: SQL, migration, `web/`, `viec-can-lam.*`, hàm ghi tiền, dependency mới.

## Hoàn tác

Revert PR frontend; không đụng dữ liệu, không có migration.

## Bằng chứng

- Audit 30/10/2026 và layout thử: ảnh 1280×720 trong PR; mockup `preview/mockups/tong-quan-v2/index.html` (255 từ so với 352 của bản DASH-03 cùng dữ liệu giả).
- Kết quả `npm run check` và test browser ghi ở PR.

## Câu hỏi mở

- Ma trận 2×2 với người dùng trên 40 tuổi: chờ người dùng tự nhìn trên `hao`; phương án lùi ghi ở nghiệm thu.
- Hạn trả riêng từng khách, hạn mức nợ, gộp nhiều sổ một công ty: vẫn chưa có dữ liệu (như DASH-03).
