# Khách mới và tên chủ hàng booking trên web (KHACH-WEB-01)

Trạng thái: ĐÃ CHỐT (người dùng, 24/11/2026): quản lý tạo sổ và gán tên trên web, lưu trong DB, thẻ Khách trong Quản trị. Phần cách làm là ĐỀ XUẤT của Claude ([quyết định](../docs/decisions/khach-web-01.md)).

## Người dùng và luồng

**Ai, khi nào:** quản lý, vài lần mỗi tháng, khi booking có chủ hàng mới hoặc tên viết khác. Hôm nay việc này do người nhập làm trên Sheet sổ nợ: mở tab khách, chép chuyến vào. Khi bỏ Sheet sổ nợ, không có tab thì chuyến biển của tên lạ không vào sổ nào.

**Câu hỏi theo thứ tự:**
1. Có chủ hàng nào trên booking mà chuyến chưa vào sổ nào không? Bao nhiêu chuyến, từ ngày nào?
2. Tên đó là khách nào: sổ nào đang có, hay khách mới?
3. Gán vào sổ đó hoặc tạo sổ mới. Chuyến có vào sổ chưa?

**Luồng:**
1. Quản trị → thẻ **Khách**. Khối đầu "Chủ hàng trên booking chưa có sổ · n tên · m chuyến". Mỗi tên một dòng gồm:
   - Biển/Bộ, số chuyến, ngày đầu–cuối, mặt hàng;
   - "Sheet ghi ở tab: …" khi tab khách trên Sheet đang ghi các chuyến đó (khi còn chạy song song);
   - ô chọn sổ và hai nút: "Gán vào sổ", "Tạo sổ mới".
2. **Gán vào sổ:** chọn sổ. Sổ gợi ý (tab Sheet ứng sổ đó) đã chọn sẵn và nút Gán là nút chính. Bấm Gán, dòng hỏi lại "Gán tên X vào sổ Y? Chuyến … sẽ tự vào sổ đó ở lượt máy sau, chưa có giá." Bấm Gán lần nữa: lệnh ghi có Lịch sử, tên rời danh sách và hiện ở sổ.
3. **Tạo sổ mới:** hộp thoại điền sẵn:
   - tên sổ: tab Sheet chưa có sổ nếu có, không thì tên chủ hàng;
   - biển/bộ;
   - mặt hàng hay gặp nhất;
   - tên trên booking.

   Bấm "Tạo sổ": sổ mới nợ 0, tên đã gán. Nút "Thêm khách mới" ở khối dưới mở cùng hộp thoại, để trống.
4. Khối dưới "Sổ và tên trên booking": mọi sổ đang hoạt động gồm tên sổ (link mở sổ), mặt hàng · biển/bộ, các tên booking. Mỗi tên có nút ✕ để bỏ, hỏi lại kiểu nguy hiểm. "+ Thêm tên" mở ô gõ ngay trong dòng. Ô tìm lọc theo tên sổ hoặc tên booking, không dấu.
5. Lượt máy sau (theo bản chụp booking, khoảng 15 phút): chuyến biển trùng mặt hàng tự vào sổ, chưa có giá. Chuyến khác mặt hàng hiện ở Việc cần làm của sổ để Duyệt. Chuyến bộ chưa ở tab nào vào sổ theo tên.

**Bị chặn:**
- người không phải quản lý: trang và API trả 403 (`v7_role`);
- tên đã gán cho sổ khác (`BOOKING_NAME_TAKEN`);
- tên sổ đã có, không phân biệt hoa thường (`BOOK_EXISTS`);
- sổ vừa đổi (`STALE_LEDGER`): trang đọc phiên bản ngay trước khi gửi;
- bản chụp booking đọc lỗi: khối đầu nói rõ, không hiện như "không có ai".

## Đầu ra

Quản lý thấy mọi chủ hàng booking chưa có sổ, gán vào sổ hoặc tạo sổ trong hai lần bấm. Từ lượt máy sau, chuyến của tên đó vào đúng sổ mà không cần tab trên Sheet.

## Đối chiếu dữ liệu và code hiện có

| Cần | Có sẵn | Thêm |
| --- | --- | --- |
| Chọn sổ cho chuyến biển | `v7_sheet_queue.build_queue` → `_pick_book`; tên khác lấy từ `WEB_GHEP_KHACH` (bản chụp `customer_aliases`) | `web_aliases(customers)` từ `booking_names` của sổ đang hoạt động, thắng bảng của file booking |
| Chọn sổ cho chuyến bộ chưa ở tab | `v7_road_queue.build_road_queue`: tab, rồi chủ hàng đã vào một sổ ≥ 3 chuyến | Tên booking gán trên web → sổ đó (`book_basis: "booking_name"`), trước luật chủ hàng |
| Tạo sổ | `create_book_from_sheet` (MAY-TAO-SO-01, chỉ máy, cần dữ liệu tab) | `create_customer`: mốc riêng, một số dư đầu 0 ở tháng tạo, cùng chuỗi cổng và cùng khóa tư vấn |
| Lưu tên booking | Không có (chỉ file `customer-name-mapping.json` cho tên tab, sửa tay trên máy chủ) | Bảng `booking_name` (tên PK, sổ), lệnh `set_booking_name` có Lịch sử `customer_attr` |
| Danh sách sổ | `list_customers` (id, tên, trạng thái, mặt hàng, phương thức) | thêm `booking_names` |
| Chủ hàng chưa có sổ | Hàng chờ có `NEEDS_CUSTOMER`; hàng chờ bộ có `skipped` `NO_TAB` | `v7_api_khach.unmapped`: gom theo tên từ 10/2026, kèm tab Sheet cùng container ±3 ngày (`prices.json`) |
| Lịch sử | `so-khach-v7-lich-su-cau.js` có câu cho `customer_attr` (mặt hàng, cảng/bộ) | "Tên trên booking thêm/bỏ X · nợ không đổi" |

Số đo 24/11/2026 (chỉ đọc, báo cáo tháng 11 trên `hao`): booking 220 chuyến biển, web 214; 11 chuyến chưa vào web, đều do tên chủ hàng (4 tên chưa ứng sổ, 1 khách có tab Sheet mà chưa có sổ web).

## Giao tiếp frontend–backend

- `GET /api/v7/admin/customers` → `{customers: [...list_customers...], unmapped: {state, road_state, snapshot_created_at, owners: [{name, family, trips, first, last, commodities, containers, sheet_tabs: [{tab, trips, customer_id}], suggest_customer_id}]}}`. `state: "unavailable"` khi bản chụp `CONT_NGUON`/giá đọc lỗi, `road_state` riêng cho `CONT_BO`.
- `POST /api/v7/admin/customers` `{book_name, commodity, transport_mode: CANG|BO, booking_names: [≤20], idempotency_key}` → `{customer_id, cutover_id, booking_names, version}`. Lỗi: `INVALID_BOOK_NAME`, `INVALID_BOOKING_NAME`, `BOOK_EXISTS`, `BOOKING_NAME_TAKEN`, `IDEMPOTENCY_CONFLICT`.
- `POST /api/v7/admin/booking-names` `{customer_id, expected_version, idempotency_key, name, remove}` → `{booking_names, version}`. Lỗi thêm: `NO_CHANGE`, `STALE_LEDGER`. Trang đọc `version` bằng `GET /api/v7/ledger/events?customer=` ngay trước khi gửi.
- Tên chuẩn hóa ở API (NFC, viết hoa, gộp khoảng trắng), DB kiểm lại bằng ràng buộc bảng. Mất mạng: trang giữ khóa và bấm lại cùng khóa; máy chủ trả kết quả lần đầu, không ghi hai lần.

## Nguồn quyết định

- [`KHACH-WEB-01`](../docs/decisions/khach-web-01.md) (quyết định của spec này).
- [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md): chuyến biển lấy khách theo booking; [`CHUYEN-BO-CHU-HANG-01`](../docs/decisions/chuyen-bo-chu-hang-01.md): chuyến bộ theo chủ hàng.
- [`MAY-TAO-SO-01`](../docs/decisions/may-tao-so-01.md): đường tạo sổ qua mốc; [`QUYEN-01`](../docs/decisions/quyen-01.md): chỉ quản lý.
- [`SONG-SONG-01`](../docs/decisions/song-song-01.md): Sheet vẫn là sổ chính thức, máy đối soát vẫn theo Sheet.

## Hành vi và bất biến

- Không ghi tiền: sổ mới nợ 0 (một số dư đầu 0 ở tháng tạo); tên booking không đổi số dư sổ nào.
- Một tên chỉ một sổ (khóa chính của bảng, khóa tư vấn theo tên khi gán).
- Lệnh tạo sổ trong một giao dịch: lỗi ở bước nào thì không còn khách, mốc, Lịch sử hay tên nào của lần đó.
- Bấm lại cùng khóa: kết quả lần đầu; cùng khóa khác nội dung bị từ chối.
- Máy vẫn chỉ tự dán chuyến biển khi mặt hàng booking trùng mặt hàng sổ.

## Tiêu chí nghiệm thu

- [x] Harness PG `KHACH-WEB.01` (`test_pg_v7_backend.py --khach-web-only --strict`):
  - tạo sổ nợ 0, mốc web, cột phụ phí mặc định, tên booking có Lịch sử dưới tên người làm;
  - bấm lại cùng khóa thì không tạo gì thêm; cùng khóa khác nội dung bị từ chối;
  - các lỗi `BOOK_EXISTS`, `BOOKING_NAME_TAKEN`, dữ liệu sai không để lại dòng nào;
  - dán chuyến vào sổ mới được;
  - gán, bỏ tên ở sổ cũ: Lịch sử trước → sau, phiên bản tăng, số dư không đổi;
  - quyền app, reader, public;
  - chạy lại migration thì định nghĩa và dữ liệu không đổi.
- [x] `test_pg_v7_backend.py --migration-test`: chuỗi migration lên `hao` bằng bản cài mới, checker sau triển khai đạt với bảng băm mới. `test_pg_v7_grants.py`: hình dạng `list_customers` mới.
- [x] Unit:
  - `test_sheet_queue`: tên web thắng `WEB_GHEP_KHACH`, sổ chưa hoạt động không nhận, khóa chuẩn hóa;
  - `test_v7_road_queue`: tên web xếp chuyến bộ chưa ở tab, `TAB_FAR` vẫn chờ, hai dòng cách 2 ngày không thành hai chuyến;
  - `test_v7_api_khach`: kiểm thân lệnh, chuẩn hóa, chủ hàng chưa có sổ kèm tab Sheet, bản chụp lỗi; route chỉ quản lý.
- [x] Trình duyệt `test-khach-browser.js`:
  - thẻ sáng, gợi ý chọn sẵn, nút chính đổi theo gợi ý;
  - gán phải chọn sổ, hỏi lại, gửi phiên bản vừa đọc;
  - tạo sổ điền sẵn, mất phản hồi bấm lại cùng khóa thì một sổ;
  - máy chủ từ chối thì bỏ khóa;
  - bỏ tên hỏi lại, thêm tên chữ hoa, tìm không dấu;
  - bản chụp lỗi, không chèn HTML, khổ 390 không tràn ngang.

  `test-so-khach-v7-api.js`: câu Lịch sử "Tên trên booking". `test-nguoi-dung-browser.js`: dải thẻ tám thẻ.
- [x] Xem ảnh render (dữ liệu giả) ở 1265×1400, hộp thoại và 390.
- [ ] Sau triển khai trên `hao`: chạy migration theo runbook; checker đạt; tổng nợ mọi sổ trước = sau; trang Khách liệt kê đúng các tên đo được.
- [ ] Người dùng tự gán một tên và tạo một sổ trên `hao`, thấy chuyến vào sổ ở lượt máy sau.

## Phạm vi agent

- Agent: claude
- Review: opus (lệnh ghi mới, DB, quyền)
- Được sửa: migration, `v7_backend_functions.sql`, `schema-draft.sql`, checker sau triển khai, bảng băm và bản chụp lược đồ, các harness liên quan, `web/v7_api_khach.py`, `web/v7_api_tables.py`, `web/v7_ledger_api.py`, `web/v7_sheet_queue.py`, `web/v7_road_queue.py`, trang `khach.*`, `app-nav.js`, `so-khach-v7-lich-su-cau.js`, test và tài liệu của các file đó.
- Cấm: đổi quy tắc tiền, phân bổ, khóa tháng; ghi Sheet hay file booking; dữ liệu khách thật trong repo.

## Hoàn tác

- Mã: revert PR.
- DB: bảng `booking_name` và hai lệnh không đụng dữ liệu tiền. Rollback là bỏ hai route (revert); bảng có thể để lại.
- Sổ đã tạo nhầm: chưa có lệnh xóa. Sổ nợ 0 không ảnh hưởng tổng; lưu trữ bằng `set_customer_archived`.

## Bằng chứng

Ở máy 24/11/2026, nhánh `claude/khach-web`:

- PostgreSQL 18.6 dùng một lần:
  - `--khach-web-only --strict`: 1/1;
  - `--migration-test`: SCHEMA 10/10, BEHAVIOR 78/78, 2 `SKIPPED_OPEN` như cũ;
  - `test_pg_v7_grants.py`: 3/3.
- Unit và trình duyệt: như tiêu chí trên. `npm run check` ghi ở PR.
