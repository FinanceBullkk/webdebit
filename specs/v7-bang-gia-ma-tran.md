# V7: khung Bảng giá dạng ma trận (phương án B)

Trạng thái: bố cục **ĐÃ CHỐT** ở [`BANG-GIA-05`](../docs/decisions/bang-gia-05.md) (người dùng chọn "Làm phương án B" trong chat 13/11/2026 sau khi xem 3 phương án trên canvas). Chi tiết hành vi dưới đây là **ĐỀ XUẤT** của Claude theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md). Không đổi luật tiền: [`BANG-GIA-01`](../docs/decisions/bang-gia-01.md) … [`BANG-GIA-04`](../docs/decisions/bang-gia-04.md) giữ nguyên, hợp đồng `GET/POST /api/v7/price-table` giữ nguyên ([spec gốc](v7-bang-gia-hieu-luc.md#giao-tiếp-frontendbackend-giai-đoạn-1-đã-code)).

## Bài toán (bước 1)

- **Người dùng:** người nhập trên 40 tuổi, màn 1280×720 nhưng Chrome chỉ thấy khoảng 1280×560 có thanh cuộn dọc 15px. Mở Bảng giá vài lần một tháng: khi khách báo giá mới (đổi đợt), khi nạp lần đầu từ Sheet, khi thấy chuyến "ngoài bảng giá".
- **Câu hỏi mang tới, theo thứ tự:** (1) giá đang dùng của nơi đi X là bao nhiêu; (2) đợt mới khác đợt cũ ở đâu; (3) lưu thì chuyến nào trong sổ đổi tiền; (4) shipper nào đang lấy giá TT, có tên viết lệch không.
- **Hành động chính:** đổi giá từ ngày (thêm đợt) và Lưu. Phụ: dán từ Sheet, sửa một ô, thêm nơi đi, khai shipper TT.
- **Vấn đề của lưới phẳng (bằng chứng):** mỗi dòng lặp Từ ngày/Đến ngày, dòng hết hạn trộn với dòng đang dùng; "Đổi giá từ ngày…" chép cả khối xuống cuối bảng nên không thấy giá mới khác giá cũ ở đâu; lỗi tô đỏ cả ô theo dòng, chữ lỗi ở cột Tình trạng tận bên phải; danh sách "shipper trong sổ đang lấy giá khách" (`book_shippers`) không còn trên màn dù spec gốc yêu cầu; lưu là tiền đổi ngay, chỉ báo sau khi đã ghi.
- **Hình dạng dữ liệu thật** (đo 13/11/2026 bằng `GET /api/v7/price-table` chỉ đọc trên `hao`, chỉ ghi số tổng hợp): 3 sổ có bảng giá; mỗi sổ 1–3 đợt, 1–14 cặp nơi đi/nơi đến; mỗi đợt có một cặp (Từ, Đến) chung cho mọi nơi đi trong đợt; phủ không đều (trong một sổ 10 cặp có ở cả 3 đợt, 2 cặp ở 2 đợt, 1–2 cặp chỉ ở 1 đợt); chưa sổ nào dùng Nơi đến; có đợt chỉ có giá TT cho một nơi đi; tên nơi đi dài nhất 20 ký tự, chưa có chữ Hán; tên khác (alias) chưa dùng.

## Bố cục (bước 2, ĐÃ CHỐT hướng)

Thứ tự nhìn trong khung 1280×560: (1) thanh trên — tên sổ, trạng thái lưu, nút chính; (2) lưới ma trận với đợt đang dùng tô xanh nhạt ở bên phải; (3) khối phải: shipper áp giá TT hoặc đợt đang sửa. Cảnh báo/lỗi nằm **trên** lưới, không ở cuối bảng.

- **Hàng** = một cặp Nơi đi · Nơi đến. Hai ô nhập cạnh nhau ở cột đầu (dính trái khi cuộn ngang); Nơi đến trống là giá chung của nơi đi (`BANG-GIA-04`), hàng có Nơi đến riêng nằm ngay dưới hàng giá chung của cùng nơi đi.
- **Cột** = một đợt `(valid_from, valid_to)` như server lưu; mỗi đợt một cặp cột **Giá khách | Giá TT**. Đầu cột hai tầng: tầng trên là nút đợt "15/09 – 09/10/2026" kèm trạng thái chữ (hết hạn / đang dùng / sắp áp dụng / lỗi), tầng dưới Giá khách | Giá TT. Đợt sắp theo Từ ngày tăng dần, mới nhất bên phải; đợt chồng ngày ở nơi đi khác nhau là hợp lệ và đứng cạnh nhau. Đợt đang dùng tô xanh nhạt; có thể có hai đợt đang dùng nếu phủ nơi đi khác nhau.
- **Mặc định hiện 3 đợt mới nhất**; nút "‹ Xem N đợt cũ hơn" mở hết (lưới cuộn ngang, cột nơi đi dính trái); đợt có lỗi luôn hiện.
- **Ô giá** gõ được trực tiếp (như Sheet). Ô trống hiện "—" khi không đứng ở đó (NULL không phải 0). Ô khác giá đợt liền trước của cùng hàng thì **đậm**; ô đã sửa mà chưa lưu thì **nền vàng**. Đợt hết hạn chữ xám.
- **Khối phải (256px)** — một trong ba:
  - *Shipper áp giá TT* (mặc định): danh sách tên kèm số chuyến trong sổ, nút × bỏ, ô thêm tên (gợi ý từ shipper trong sổ). Dưới: "Trong sổ đang lấy giá khách" — shipper của sổ không có trong danh sách TT, kèm số chuyến; tên gần giống một shipper TT (bỏ khoảng trắng/dấu chấm thì trùng, hoặc khác ≤ 2 ký tự) hiện "Gần giống …" và nút "Chuyển sang giá TT". Sổ chưa ghi shipper nào: một câu "Chuyến trong sổ chưa có tên shipper: mọi chuyến lấy giá khách."
  - *Đợt giá* (bấm đầu cột): Từ ngày, Đến ngày (trống = còn dùng), số giá trong đợt, nút "Bỏ đợt này". Đợt vừa thêm thì thêm dòng "Đợt … tự kết thúc ngày …" và "N dòng đổi giá, M dòng giữ giá đợt trước".
  - *Đợt giá mới* (nút "+ Đổi giá từ ngày…"): ô "Áp dụng từ ngày", nút "Thêm cột giá mới", "Thôi".
  - *Dán từ Sheet* (nút trên thanh trên): ô dán lớn, hình vùng Sheet cần chọn.

## Luồng người dùng

| Việc | Thao tác | Kết quả trên màn |
| --- | --- | --- |
| Mở | Cài đặt ▾ → **Bảng giá** | "Đang đọc bảng giá…" rồi lưới; lỗi đọc thì báo và không cho sửa |
| Nạp lần đầu | Bảng trống hiện hướng dẫn và hình vùng Sheet → bấm vào ô dán (hoặc **Dán từ Sheet**) → Ctrl+V | Dòng phẳng tự gộp: cùng (Từ, Đến) thành một đợt, cùng (Nơi đi, Nơi đến) thành một hàng. Báo "Đã dán N dòng giá vào M đợt[, K shipper áp giá TT]" |
| Dán lại vùng đã sửa trên Sheet | Như trên khi bảng đã có | Ô cùng đợt + cùng hàng bị thay giá mới (tô vàng); đợt/hàng mới thêm vào |
| Dán một cột giá | Đứng ở ô giá, Ctrl+V khối 1–2 cột nhiều dòng | Điền xuống từ hàng đang đứng (cột 1 → ô đó, cột 2 → ô bên phải) theo thứ tự hàng đang hiện |
| Đổi giá từ ngày | **+ Đổi giá từ ngày…** → gõ ngày → **Thêm cột giá mới** | Thêm cặp cột bên phải, chép giá từ các đợt còn dùng (Đến ngày trống); các đợt đó kết thúc ngày liền trước (Q6 của `BANG-GIA-01`). Con trỏ ở ô giá đầu tiên của cột mới. Sửa ngày ở khối phải thì ngày kết thúc đợt cũ đi theo |
| Sửa một giá | Bấm ô, gõ, Enter/mũi tên | Ô vàng; trạng thái "Chưa lưu · N ô đổi" |
| Sửa ngày một đợt | Bấm đầu cột → sửa Từ/Đến ở khối phải | Lỗi ngày hiện ngay ở đầu cột và khối phải |
| Bỏ một đợt | Bấm đầu cột → **Bỏ đợt này** | Cột biến mất; chưa ghi gì cho tới khi Lưu |
| Thêm/bỏ nơi đi | **+ Thêm nơi đi** (hàng trống cuối lưới, con trỏ ở ô Nơi đi) / nút × cuối hàng | |
| Tìm nơi đi | Ô **Tìm nơi đi** | Chỉ hiện hàng có chữ đó; không đổi dữ liệu |
| Shipper TT | Khối phải: thêm/bỏ tên, hoặc **Chuyển sang giá TT** | |
| Lưu | **Lưu bảng giá** | Như hiện nay (`BANG-GIA-02`): server đổi giá chuyến đang theo bảng ở tháng mở, khung đóng, thông báo trước → sau. PR (b) thay bằng bước **Xem lại trước khi lưu** |
| Đóng khi còn thay đổi | **Đóng**, Esc hoặc bấm ra ngoài | Hỏi "Bảng giá có thay đổi chưa lưu" — Lưu / Bỏ thay đổi / Ở lại |

## Đối chiếu dữ liệu

| Trên màn | Nguồn | Ghi chú |
| --- | --- | --- |
| Cột đợt | `price_table.periods[]` (`valid_from`, `valid_to`) | Một đợt server = một cột. Gửi lại: mỗi cột còn giá thành một `period`; cột không còn ô giá nào thì không gửi (bỏ đợt) |
| Hàng | cặp (`rates[].location`, `rates[].destination`) | Thứ tự hàng: theo `locations[]` như server trả, cùng nơi đi thì giá chung trước rồi nơi đến A→Z |
| Ô giá | `rates[]` với `tier` = `khach`/`tt` | Ô trống không gửi dòng (NULL ≠ 0); "60,000,000", "60.000.000", "60000000" đều đọc được |
| Tên khác của nơi đi | `locations[].aliases` | Không hiện, gửi lại nguyên như đã lưu theo tên nơi đi |
| Shipper áp giá TT | `tt_shippers` | Chuẩn hóa như server: hoa, gộp khoảng trắng |
| Shipper trong sổ | `book_shippers[]` (`name`, `trip_count`) | Lấy giá khách = không có trong danh sách TT đang sửa (tính tại trang, chỉ để soát tên; server vẫn quyết giá) |
| Trạng thái đợt | `valid_from`/`valid_to` so với hôm nay giờ VN | Chỉ để đọc, không phải luật tra giá |

Payload `POST /api/v7/price-table` giữ đúng hình dạng hiện có: `{tt_shippers, locations: [{name, aliases}], periods: [{valid_from, valid_to, rates: [{location, destination, tier, unit_price_vnd}]}]}`.

## Lỗi (hiện bằng chữ tại chỗ, không tô cả cột)

Kiểm ở trang như server để chặn trước khi gửi; server vẫn kiểm lại.

| Lỗi | Hiện ở đâu | Chữ |
| --- | --- | --- |
| Từ ngày trống/sai, Đến ngày sai, Đến trước Từ | Đầu cột (thay trạng thái) + khối Đợt giá | "Từ ngày sai", "Đến ngày sai", "Đến trước Từ ngày" |
| Giá không đọc được, âm, lẻ | Viền đỏ ở đúng ô + dòng lỗi trên lưới | "DAK LAK, đợt 10/10/2026: Giá khách sai" |
| Hàng có giá mà thiếu Nơi đi; hai hàng cùng Nơi đi + Nơi đến | Viền đỏ ô Nơi đi + dòng lỗi | "Hàng 4: thiếu Nơi đi", "DAK LAK có hai hàng" |
| Trùng ngày cùng nơi đi + nơi đến + nhóm giá (`BANG-GIA-04` mục 4) | Viền đỏ hai ô liên quan + chữ ở đầu hai cột + dòng lỗi | "DAK LAK: đợt 01/10/2026 trùng ngày đợt 15/09/2026 (giá khách)" |

Dòng lỗi nằm ngay trên lưới, mỗi lỗi một nút "Sửa" đưa con trỏ tới ô/đầu cột. Bấm Lưu khi còn lỗi: không gửi gì, báo "Chưa lưu: N lỗi".

## Trạng thái

- **Đang tải:** chỉ thanh trên và "Đang đọc bảng giá…"; chưa hiện lưới để không gõ vào bảng sắp bị thay.
- **Bảng trống:** hướng dẫn dán lần đầu + hình vùng Sheet + ô dán; vẫn có "+ Thêm nơi đi" để gõ tay.
- **Lỗi server khi lưu:** giữ nguyên bảng đang sửa, báo lỗi trên lưới; `NO_CHANGE` → "Bảng giá không có gì thay đổi"; `STALE_LEDGER` → "Sổ vừa thay đổi. Đóng khung, tải lại rồi lưu lại." (giữ bảng để người dùng còn chép lại); mất mạng → "Chưa rõ đã lưu chưa…".
- **Đóng khi chưa lưu, Esc:** Esc đóng khối/câu hỏi đang mở trước, rồi mới hỏi đóng khung.
- **Tên dài/chữ Hán:** ô Nơi đi rộng 150px, chữ dài cắt bằng "…" khi không đứng ở ô, đầy đủ trong `title`; hàng không cao lên.
- **Sổ không có cột Shipper / chưa có shipper:** khối Shipper TT vẫn hiện, có câu giải thích ở trên.

## Bước xem lại trước khi lưu (PR b)

Người dùng thấy trước khi ghi: bảng giá đổi gì, số chuyến tự đổi giá, tổng còn nợ tăng/giảm, số chuyến tháng khóa không đổi, số chuyến giữ giá gõ tay khác bảng, số chuyến bảng mới không còn giá, danh sách chuyến trước → sau; nút "Lưu và đổi giá N chuyến" (không có chuyến nào đổi thì "Lưu bảng giá").

**Cách lấy số liệu (ĐỀ XUẤT, chọn):** hàm SQL mới `sokhach.preview_price_table(customer_id, expected_version, price_table)` gọi **chính** `save_price_table` trong một khối con PL/pgSQL, đọc `get_price_status` sau khi lưu, rồi ném lỗi để PostgreSQL hoàn tác khối con và trả kết quả. Lý do:

- Một đường quy tắc: số xem trước là số của đúng hàm sẽ ghi (`_reprice_from_table`, `_lookup_price`), không viết lại quy tắc ở hàm thứ hai hay ở trang (trang không tự tính tiền).
- Không đổi tầng psql của API (`ARCH-01`: mọi lệnh bọc `BEGIN … COMMIT`); gọi `save_price_table` rồi `ROLLBACK` ở API sẽ phải thêm một kiểu chạy riêng chỉ cho một route.
- Kiểm được bằng harness PostgreSQL: gọi xem trước rồi so số dư, `version`, `event`, giá chuyến không đổi; rồi lưu thật và so kết quả trùng số xem trước.

Lưu thật vẫn gửi `expected_version` và đúng bảng của lúc xem; sổ đổi giữa chừng thì `STALE_LEDGER` như hiện nay. Cần migration nên triển khai tay theo [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md).

Đã làm (PR b): `POST /api/v7/price-table/preview` cùng thân lệnh với lưu, trả `{price_table, version (không đổi), repriced_trips (+tier), repriced_delta_vnd, locked_trips, no_price_trips, typed_trips, ready_count, ready_total_vnd}`; lỗi bảng trả như lệnh lưu và trang quay về lưới kèm câu báo. Máy chủ chưa có hàm (DB chưa nâng) hoặc lỗi khác: bước xem lại vẫn hiện bảng đổi gì, ghi "Chưa tính được trước chuyến nào đổi giá" và cho lưu như trước. Nút trên thanh trên đổi thành **Xem lại và lưu**; Esc hoặc **Quay lại sửa** trở về lưới, bảng giữ nguyên. Phần "Bảng giá thay đổi gì" so bảng đã lưu với bảng sắp gửi tại trang (dữ liệu bảng, không phải tiền); đợt mới so với đợt liền trước.

## Hai thứ Claude tự thêm trong mockup

Người dùng trả lời trong chat 13/11/2026 câu hỏi có làm hai thứ này không: "Chỉ dải nơi đi".

- **Dải nơi đi ngoài bảng — ĐÃ CHỐT, làm (PR c).** Ngay trên lưới (trong mép 560): "N chuyến chưa có giá vì nơi đi ngoài bảng: PHU YEN (2 chuyến), KON TUM (1 chuyến)." kèm nút **Thêm K nơi đi này**. Nguồn: chuyến có `lookup.reason = UNKNOWN_LOCATION` và chưa có đơn giá trong `GET /api/v7/price-table/status` (server tra), gom theo nơi đi đã chuẩn hóa (hoa, gộp khoảng trắng), bỏ nơi đi đã có hàng trên lưới; quá 5 nơi đi thì ghi "và M nơi đi khác". Nút chỉ thêm hàng trống (không tự điền giá, không ghi gì cho tới khi lưu), con trỏ ở ô Giá khách của đợt mới nhất; nơi đi đã có hàng thì dải tắt. Không có chuyến nào như vậy thì không hiện gì.
- **Nút "Cộng đều +N vào cột mới" — KHÔNG LÀM** (người dùng, cùng câu trả lời).

## Tiêu chí nghiệm thu

PR (a) — lưới ma trận, không đổi backend:
- [x] Mở bảng đã lưu: đợt thành cột, nơi đi thành hàng, đợt không đều để trống "—", tên khác giữ nguyên khi lưu; payload giữ hình dạng.
- [x] Dán vùng Sheet có tiêu đề, ô trống, số có dấu phẩy, ngày một chữ số, cột shipper sau một cột trống → gộp đúng đợt/hàng, báo số dòng và số đợt.
- [x] Dán một cột giá vào cột đợt mới điền xuống từ hàng đang đứng.
- [x] Đổi giá từ ngày: thêm cột, chép giá, đợt cũ kết thúc ngày liền trước; sửa ngày đợt mới thì ngày kết thúc đi theo; ô sửa tô vàng.
- [x] Lỗi ngày ở đầu cột, giá sai ở ô, trùng ngày ở hai cột, bằng chữ; Lưu bị chặn, không gửi gì.
- [x] Sửa ngày một đợt, bỏ một đợt, thêm/bỏ nơi đi; Tìm nơi đi lọc hàng.
- [x] Shipper TT: thêm/bỏ, "Trong sổ đang lấy giá khách" kèm gợi ý gần giống và nút chuyển.
- [x] Lỗi server giữ bảng đang sửa; `STALE_LEDGER`; đóng khi chưa lưu hỏi lại; Esc.
- [x] Test trình duyệt 1280×720 viết lại cho ma trận; ảnh render 1280×560 có thanh cuộn đã xem (dữ liệu giả).
- [ ] `npm run check`, `node scripts/check-secrets.js` xanh; Deploy hao xanh.

PR (c) — dải nơi đi ngoài bảng:
- [x] Đếm đúng chuyến chưa có giá vì nơi đi ngoài bảng, gộp cách viết khác hoa thường/khoảng trắng, bỏ chuyến đã có giá và nơi đi đã có hàng; dải nằm trên lưới trong mép 560 (test trình duyệt 1265×560).
- [x] Nút thêm hàng trống, không tự điền giá, không gửi lệnh nào; gõ giá rồi lưu thì nơi đi mới vào payload.

PR (b) — xem lại trước khi lưu:
- [x] Harness PostgreSQL: xem trước không đổi `version`, `event`, giá chuyến, số dư; số xem trước trùng kết quả lưu thật; lỗi bảng (trùng ngày…) trả đúng mã; quyền app/reader đúng.
- [x] Test trình duyệt: Lưu mở bước xem lại với số từ server, "Quay lại sửa" giữ bảng, "Lưu và đổi giá N chuyến" gửi đúng một lệnh lưu.
- [ ] Migration triển khai tay trên `hao` theo runbook, nhật ký trong `docs/deploys/`.
- [ ] Người dùng tự đi hết luồng trên bản thật: đổi giá từ ngày cho một sổ, xem lại, lưu.

## Phạm vi file

- PR (a): `cong-no-web-handoff/preview/so-khach-v7-price-ui.js`, phần `.price-*` của `so-khach-v7.css`, `test-so-khach-v7-price-browser.js`, máy chủ giả `so-khach-v7-browser-world.js` (nếu cần), spec này, `docs/decisions/bang-gia-05.md`, `docs/decisions.md`.
- PR (b): thêm `cong-no-web-handoff/web/v7_ledger_api.py` (và bảng route/SQL liên quan), `cong-no-web-handoff/tools/v7_backend_functions.sql`, migration mới, `cong-no-web-handoff/tools/test_pg_v7_backend_price.py`, `specs/v7-backend/schema-draft.sql` nếu cần.
- Cấm: đổi luật tra giá/đổi giá, ghi DB thật ngoài runbook, đưa tên khách/giá thật vào repo.

## Bằng chứng

PR (a), 13/11/2026, máy Windows, dữ liệu giả, không chạm DB:

- `test-so-khach-v7-price-browser.js` 12 test (7 test mới cho ma trận: dán vùng phẳng vào bảng trống và dán đè, đợt không đều + đợt cũ ẩn + đổi giá từ ngày + dán một cột + sửa ngày đợt mới, lỗi tại ô/đầu cột/trùng ngày/thiếu nơi đi + bỏ đợt/bỏ hàng, shipper TT và tên gần giống, sổ chưa có shipper, lỗi server/`STALE_LEDGER`/Esc, bố cục 1265×560); sửa theo ma trận một test phím mũi tên (`test-so-khach-v7-keys-browser.js`) và một test Hồ sơ → Xem bảng giá (`test-so-khach-v7-contact-browser.js`).
- Ảnh render 1280×720 và 1265×560 (giả lập thanh cuộn 15px) với 13 nơi đi giả, 4 đợt, một hàng có nơi đến riêng, tên dài có chữ Hán: 3 đợt vừa khung không cuộn ngang, khoảng 8 hàng thấy được, nút Lưu, đợt đang dùng và danh sách lỗi nằm trên mép 560. Đã sửa: cột rộng quá 10px ở 1265 (thu Nơi đến 104px, ô giá 108px); dải lỗi trùng lặp khi Lưu bị chặn.
- `npm run check` xanh; `node scripts/check-secrets.js` sạch.

PR (b), 13/11/2026, máy Windows, PostgreSQL 18.6 dùng một lần, dữ liệu giả:

- `test_pg_v7_backend.py --migration-test`: migration đạt (nâng từ schema cũ ra đúng catalog khởi tạo mới), 69 BEHAVIOR + 10 SCHEMA đạt, 2 SKIPPED_OPEN như trước. `BANG-GIA.01` thêm: xem trước không đổi version, event, revision giá, khóa lệnh, bảng giá, số dư tháng, dòng phân bổ; gọi lại cho cùng kết quả; `STALE_LEDGER`, `PRICE_PERIOD_OVERLAP`, `NO_CHANGE` trả đúng mã và không ghi; số xem trước trùng lệnh lưu thật (chuyến, tổng, tháng khóa, hết giá) và `typed_trips` trùng trạng thái giá sau lưu; tháng khóa xem trước báo đúng; chạy lại migration trên schema chuẩn không đổi gì.
- `test_pg_v7_grants.py --strict`: đạt (hàm mới chỉ `sokhach_app` gọi được).
- Test trình duyệt 14 test (thêm 2: bước xem lại đủ số từ server, bảng đổi gì, quay lại/Esc giữ bảng, lưu đúng bảng và phiên bản đã xem; máy chủ chưa tính được vẫn lưu được). Ảnh 1265×560 của bước xem lại đã xem và sửa (ô số xuống dòng, danh sách chuyến bị cắt).
