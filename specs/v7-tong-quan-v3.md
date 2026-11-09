# V7 — Tổng quan v3: bản ít chữ theo canvas (DASH-05)

> Khối khách (chip mức rủi ro, bảng) và thẻ Thu tháng sẽ thay theo [`v7-tong-quan-v4.md`](v7-tong-quan-v4.md) (`DASH-06`, 6/11/2026). Chưa code: trang đang chạy vẫn theo spec này.

Trạng thái: **ĐÃ CHỐT** ([`DASH-05`](../docs/decisions/dash-05.md), người dùng 2/11/2026 qua chat và canvas Claude Design, khung `TongQuanGon` là bản chính). Spec này **thay cách trình bày** của [`v7-tong-quan-v2.md`](v7-tong-quan-v2.md) (DASH-04) và **giữ nguyên** mọi quy tắc tính của [`v7-tong-quan-quan-ly-no.md`](v7-tong-quan-quan-ly-no.md) (DASH-03). Không đổi backend, không SQL mới.

## Bài toán (bước 1)

| Người xem | Lúc nào | Câu hỏi (theo thứ tự) | Khối trả lời |
| --- | --- | --- | --- |
| Chủ nghiệp vụ | Cuối tuần/tháng, trước khi gọi đòi nợ | 1. Khách nợ bao nhiêu, bao nhiêu đã quá hạn, quá bao lâu? | Dải đầu: Còn phải thu, ngoặc Trong hạn/Quá hạn, thanh + 5 ô hạn trả |
| | | 2. Thu tháng này có kịp phát sinh không? | Thẻ Thu tháng |
| | | 3. Ai cần đòi trước, nhóm rủi ro nào? | Chip mức rủi ro + bảng khách |
| | | 4. Khách này đang thế nào? | Bấm tên → trang khách, thẻ Tình hình |
| Người nhập | Cuối ngày | Còn việc gì? | Tab Việc cần làm (số trên menu), không đổi |

Vấn đề của bản DASH-04 (ghi chú canvas `tqhientai`, máy chủ giả 2/11/2026): thanh trên 56px chưa theo menu trái của các trang khác; hai thẻ ngang cùng nền nên không có thứ bậc; một nhóm hạn trả đọc ba kiểu (số trong đoạn, nhãn dưới đoạn, dòng "Đoạn hẹp"); số lặp ("8 khách" ở ngoặc, đầu bảng và ma trận); ghi chú chuyến thiếu giá ở thẻ Thu tháng nhưng nói về Còn phải thu; bảng tỷ làm khách nhỏ thành 0,03; ma trận 2×2 chiếm cả cột chỉ để lọc; ngăn kéo lặp trang Tình hình.

## Bố cục (bước 2) — thứ tự nhìn trong 1280×560

1. **Thanh tiêu đề** trắng 53px: "Tổng quan công nợ", giờ cập nhật (HH:MM; ngày số liệu và lịch tự tải ở chú thích), nút ↻ Làm mới 40×40.
2. **Dải đầu** nền xanh nhạt, hai phần:
   - Trái: "Còn phải thu" + **số 40px** (`get_dashboard().receivable.total_vnd`, rút gọn tỷ/tr) + ba nút nhỏ biểu tượng + số: hình người **N** (số khách đang nợ), thẻ giá **k** (chuyến chưa có đơn giá, nền cam, mở Việc cần làm; chỉ hiện khi k > 0), ví **X tr** (khách trả thừa, nền xanh ngọc; chỉ hiện khi có). Ngoặc "Trong hạn **X**" (xanh) | "Quá hạn **Y**" (đỏ), độ rộng theo tỉ lệ. Thanh 18px 5 đoạn chỉ là hình (không số). 5 ô dưới thanh, mỗi ô: chấm màu + tên ngắn (Chưa đến hạn · Hạn 30/11 · 1–2 tháng · 3–6 tháng · > 6 tháng) + số tiền; số nhóm quá hạn 1–2 tháng màu cam, 3–6 và > 6 tháng màu đỏ. Bấm đoạn hoặc ô = lọc bảng (bấm lại bỏ). Chú thích: tên đủ + tháng nợ + tiền + số khách + % còn phải thu.
   - Phải: thẻ trắng **Thu tháng M**: đã thu (30px, xanh lá) bên trái, phát sinh bên phải, thước 12px có vạch đen "hôm nay", đồng hồ "còn n ngày" (tới cuối tháng). % ở chú thích.
3. **Khối "Công nợ theo mặt hàng"** ([`DASH-07`](../docs/decisions/dash-07.md), 9/11/2026), rộng cả trang, nền trắng, chỉ hiện khi số từng khách khớp tổng server: đầu khối tên + chú giải hai màu (Trong hạn xanh, Quá hạn đỏ); thân hai cột, mỗi nhóm mặt hàng một dòng cao 40px là nút lọc: tên (Khác, Chưa phân loại chữ xám) · thanh 12px dài theo còn phải thu, cùng thang = nhóm nhiều nhất, phần xanh trong hạn + phần đỏ quá hạn dương · **Còn phải thu** · **Quá hạn** (đỏ; "–" khi không có) · hình người + số khách. Tiền `F.short(…, 'tr')`. Nhóm và thứ tự theo `DashboardModel.commodities`. Chú thích dòng: tên, còn phải thu + % tổng, quá hạn, số khách, tên các mặt hàng gộp vào Khác, giải thích Chưa phân loại. Bấm dòng = lọc bảng (bấm lại bỏ), dòng khác mờ. Dưới 700px: một cột, bỏ thanh và chú giải, tên được xuống dòng.
4. **Bảng "Khách cần đòi trước"** rộng cả trang: góc phải có nút lịch 40×40 sang Công nợ theo tháng (phễu + select mặt hàng đã bỏ theo `DASH-07`). Hàng chip: **Tất cả** · **Rủi ro cao** (chấm đỏ, hình người n, tiền quá hạn) · **Theo dõi** (chấm cam, n, tiền quá hạn) · **Không quá hạn** (chấm xanh ngọc, n); đang lọc nhóm hạn trả thì thêm chip "■ tên nhóm ✕", đang lọc mặt hàng thì thêm chip "tên mặt hàng ✕" cùng hàng. Cột: Khách (chấm mức rủi ro + tên, là link) · Theo hạn trả (thanh 12px 5 màu, cùng thang = khách nợ nhiều nhất đang hiện) · Quá hạn `tr` (đỏ đậm; khi lọc nhóm hạn trả đổi thành "Nhóm này") · Còn nợ `tr` · Trả `ngày` · Đi hàng `ngày` · ›. Bấm đầu cột tiền/ngày để xếp. Hiện 10 dòng đầu, nút "Hiện cả N khách" mở hết tại chỗ.

Luôn hiện: dải đầu, khối mặt hàng, chip, 10 dòng. Chỉ mở khi cần: chú thích, dòng thứ 11 trở đi, trang khách. Không còn: ngăn kéo, ma trận 2×2, dòng chú giải chấm màu dưới bảng, dải "Đang lọc", câu "n/N khách có nợ quá hạn", ghi chú dưới thẻ Thu tháng.

### Mỗi số một chỗ (ghi chú canvas `tqdulieu`)

| Số | Chỗ duy nhất | Kiểm cộng |
| --- | --- | --- |
| Còn phải thu, số khách đang nợ | Dải đầu | — |
| Tiền từng nhóm hạn trả | 5 ô (số khách mỗi nhóm ở chú thích) | 5 ô = `receivable_vnd`; ngoặc là tổng phụ |
| Tiền quá hạn theo mức rủi ro | Chip | Chip Rủi ro cao + Theo dõi (+ phần quá hạn âm của khách Không quá hạn) = ngoặc Quá hạn |
| Số khách theo mức rủi ro | Chip | Ba chip = số dòng khách đang nợ |
| Còn phải thu, quá hạn, số khách theo mặt hàng | Khối Công nợ theo mặt hàng (`DASH-07`) | Các dòng cộng = Còn phải thu và số khách đang nợ (khối chỉ hiện khi đã khớp) |
| Từng khách | Một dòng bảng | Nợ theo tháng, lý do đầy đủ, hứa trả ở trang khách |

## Đối chiếu dữ liệu (bước 2)

| Thông tin trên màn | Nguồn | Tình trạng |
| --- | --- | --- |
| Còn phải thu, số khách, chuyến thiếu giá, khách trả thừa (số khách, tổng) | `GET /api/v7/dashboard` (`get_dashboard()`): `receivable`, `todo.missing_price[].count`, `credit` | Có, dùng nguyên |
| 5 nhóm hạn trả, ngoặc Quá hạn | `GET /api/v7/dashboard/debt` (`get_dashboard_debt()`): `due_tiers`, `summary.overdue_vnd` | Có |
| Thu tháng: đã thu, phát sinh, ngày hôm nay, số ngày còn lại | `.this_month`, `.as_of` (giờ VN) | Có; ngày còn lại = số ngày của tháng − ngày `as_of`, tính ở frontend |
| Từng khách: nhóm hạn trả, quá hạn, còn nợ, số ngày trả/đi hàng, mức rủi ro, mặt hàng | `.customers[]` (`tiers_vnd`, `overdue_vnd`, `outstanding_vnd`, `pay_days`, `trip_days`, `risk`, `commodity`, `transport_mode`) | Có |
| Chip: số khách và tiền quá hạn theo mức rủi ro | Gom `.customers[]` ở `dashboard-v7-model.js`; đối chiếu `summary.high_customers`, `high_overdue_vnd`, `overdue_customers`, `overdue_vnd` | Gom ở frontend, không SQL mới |
| Ngưỡng màu ô ngày | `.rule` (`no_pay_days`, `no_trip_days`, `active_trip_days`) | Có, không viết cứng |
| Tên khách | `GET /api/v7/customers` (tên Sheet `display_name`; trùng tên thêm mặt hàng/số sổ) | Có |

## Quy tắc (giữ DASH-03)

- Hạn trả: nợ tháng M đến hạn cuối tháng M+1; 5 nhóm do server tính.
- Mức rủi ro do server tính (`risk`): `ok` khi quá hạn ≤ 0 (nhãn **Không quá hạn**); `high` khi có quá hạn và (quá hạn từ 3 tháng, hoặc hơn 60 ngày chưa trả / chưa trả lần nào, hoặc hơn 90 ngày không đi hàng / chưa có chuyến); còn lại `watch`.
- Tiền là chuỗi VND nguyên, đổi BigInt; trang không tự cộng trừ ngoài gom/đối chiếu ở model. Bảng: `F.millions` (≥ 1 tỷ làm tròn triệu "1.410", ≥ 1 triệu một số lẻ "83,4"); dải đầu/chip/ô: `F.short(…, 'tr')`. Quá hạn 0 ghi "–" xám.
- Ô ngày: số ngày nguyên trong viên; null ghi "chưa" (không phải 0) và coi là lâu nhất khi xếp; vượt ngưỡng (`no_pay_days` / `no_trip_days`) nền đỏ nhạt chữ đỏ đậm; trên `active_trip_days` nền cam nhạt; còn lại chữ thường.
- Ngày theo `as_of` (giờ VN), không dùng đồng hồ máy cho nghiệp vụ.

## Hành vi

- **Lọc tại chỗ** kết hợp: nhóm hạn trả (`?han=0–4`), mức rủi ro (`?muc=cao|theo-doi|khong-qua-han`), mặt hàng (`?mh=`), xếp (`?xep=tong|chua-tra|di-hang`). Link cũ `?nhom=com:<mặt hàng>` vẫn mở lọc mặt hàng; `?nhom=mx:…`, `?khach=`, `?xem=` cũ bị bỏ qua và xóa khỏi địa chỉ khi đổi lọc. Lọc không đổi dải đầu.
- **Bấm tên khách** (hoặc dòng) mở `so-khach-v7-live.html?customer=<id>&the=tinh-hinh`. Ô tìm khách ở menu vẫn mở thẻ Sổ.
- **Không đối chiếu được** (`totalsMatch` sai: tổng từng khách ≠ `receivable_vnd` hoặc ≠ từng nhóm; hoặc `riskMatches` sai: chip ≠ `summary`): chip và select bị khóa, dưới chip một dòng "Số từng khách chưa khớp tổng; xem chi tiết ở Công nợ theo tháng."; bấm nhóm hạn trả mở Công nợ theo tháng.
- **Khách quá hạn âm** (dư ở nợ cũ, còn nợ mới; server trừ vào `summary.overdue_vnd`): khách ở chip Không quá hạn; chú thích ngoặc Quá hạn ghi "đã trừ k khách dư ở nợ cũ X".
- **API debt lỗi**: dải đầu chỉ còn số tổng và nút đếm, chỗ thanh ghi "Chưa tải được phần quá hạn. Bấm Làm mới để thử lại."; thẻ Thu tháng "Chưa tải được số thu tháng này."; bảng "Chưa tải được danh sách khách. Bấm Làm mới để thử lại.", ẩn chip và select. API tổng lỗi: một câu tiếng Việt + nút Thử lại (giữ audit P1-6).
- Không có khách nợ: "Chưa có khách đang nợ." ở chỗ thanh, bảng "Không có khách đang nợ."
- Tự tải mỗi 60 giây (không tải khi đang gõ tìm khách); PRESENCE-01 chấm người đang mở sổ cạnh tên khách; số trên mục Việc cần làm giữ.

## Tiêu chí nghiệm thu

- [ ] `test-dashboard-v7-model.js`: `risks` (đếm, tiền quá hạn, khách quá hạn âm vào Không quá hạn), `riskMatches`, `filterRows` theo mức rủi ro, `dayCell` mới, `tierLabels` tên ngắn, `monthProgress` số ngày còn lại.
- [ ] `test-v7-dashboard-browser.js` ở 1280×720: số trên trang bằng số API (tổng, 5 ô, ngoặc, chip, bảng triệu, ô ngày), lọc chip / hạn trả / mặt hàng kết hợp và địa chỉ trang, bấm tên mở đúng `the=tinh-hinh`, không cuộn ngang ở 1280 và 390, nút ≥ 40px, API debt lỗi, tổng lệch khóa lọc, link cũ.
- [ ] `npm run check` và `node scripts/check-secrets.js` xanh; ảnh 1280×720 dữ liệu giả trước/sau trong PR.
- [ ] Người dùng tự đi hết luồng trên `hao`.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`).
- Được sửa: `preview/dashboard-v7.{html,js,css}`, `preview/dashboard-v7-model.js`, hai test tương ứng, spec và quyết định.
- Cấm: `so-khach-v7-*` (phiên khác đang sửa), SQL, migration, `web/`, hàm ghi tiền, dependency mới. `DashboardModel.RISK.ok` đổi thành "Không quá hạn" theo điểm 4 của DASH-05; trang khách giữ bản chép nhãn riêng (`so-khach-v7-overview-ui.js`), phiên trang khách đổi theo.

## Hoàn tác

Revert PR frontend; không đụng dữ liệu, không có migration.
