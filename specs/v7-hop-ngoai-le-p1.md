# Hộp ngoại lệ P1: việc Sheet → web của cả công ty, chỉ đọc

Trạng thái: ĐỀ XUẤT (Claude, 1/11/2026). Giai đoạn P1 của [UX bước 03](../docs/ux-buoc-03-luong-thao-tac.md) mục 7, dựa trên [`HANG-CHO-01`](../docs/decisions/hang-cho-01.md) và [`UX-NEN-01`](../docs/decisions/ux-nen-01.md). Người dùng bảo "Bắt đầu P1" (chat 1/11/2026). P1 chỉ đọc: không đổi lệnh ghi, luật tiền hay DB.

## Người dùng và luồng (bước 1)

**Người nhập, cuối ngày** (luồng L1 của bước 03):
1. Mở "Việc cần làm".
2. Ngoài các nhóm cũ (thiếu giá, chờ kiểm, số dư đầu, mặt hàng, sổ dư, hôm nay), trang có thêm khối **"Từ Sheet chờ đưa vào sổ"**: việc của hàng chờ Sheet ở **cả 236 sổ**, gom theo loại, xếp theo tiền.
3. Mỗi dòng ghi khách, việc gì nói bằng câu, số tiền nếu có, và nút "Mở sổ" mở đúng sổ. Ở sổ, người nhập làm như hôm nay (các nút "Ghi n phiếu thu từ Sheet", "Duyệt n chuyến mới"…).
4. Quay lại "Việc cần làm": sổ vừa làm được tính lại ngay, dòng đã xong biến mất.

**Kết quả:** biết hôm nay còn gì ở sổ nào mà không phải mở 72 sổ.

**Bị chặn khi:**
- bản chụp Sheet không đọc được: khối ghi rõ "chưa tính được";
- đang tính lần đầu sau khi API khởi động: khối ghi "đang tính, khoảng 2 phút" (đo trên `hao` 1/11/2026: 90 giây cho 236 sổ, 4 luồng).

Sếp và người đòi nợ không đổi gì trong P1. Cảnh báo theo khách ở Tổng quan và Đòi nợ thuộc P2.

## Đầu ra

`GET /api/v7/inbox` trả việc chờ của mọi sổ, lấy từ bộ nhớ đệm do API tính nền. "Việc cần làm" có khối "Từ Sheet chờ đưa vào sổ" với đủ các trạng thái ở mục "Hành vi".

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Nhóm trong khối | Nguồn (đang có, `GET /api/v7/ledger` → hàm chiếu) | Số đo trên `hao` 1/11/2026 sau PR #240 |
| --- | --- | --- |
| Phiếu thu từ Sheet chờ ghi | `sheet_receipts.ready` / `.review` (`amount_vnd`) | 6 sẵn sàng + 7 cần xem, 12 sổ |
| Chuyến đang tính nợ nhưng không còn trên Sheet | `sheet_sync.removed_items` (`amount_vnd`) | 0 |
| Chuyến mới chờ duyệt | `sheet_sync.items` có `sync_state = NEW` | 100 |
| Chuyến cần người xem | `sheet_sync.items` có `CONFLICT`, lý do khác `DIFFERENT_FIELDS`, hoặc `DIFFERENT_FIELDS` có ngày/booking | khoảng 265 (241 `OTHER_BOOK_LEGACY`) |
| Giá từ Sheet | `sheet_prices.ready` / `.review` | 0 + 45, 10 sổ |
| Phụ phí PS cần xem | `ps_fees.ready` / `.review` | 0 + 102, 25 sổ |
| Lệch chữ mô tả (máy sẽ tự làm theo Q1, chưa bật) | `sheet_sync.items` có `DIFFERENT_FIELDS`, chỉ cột nơi đi/nơi đến/shipper/hãng tàu | khoảng 951 |

- Tên khách lấy từ `GET /api/v7/customers` mà trang đã tải sẵn.
- Độ tươi lấy từ `v7_sheet_refresh.status` (giờ bản chụp).
- Nhóm thiếu giá và chờ kiểm của trang vẫn lấy từ `GET /api/v7/dashboard` như cũ, khối mới không lặp lại hai nhóm này.

**Tốc độ:** tính một sổ khoảng 0,75 giây (đo 1/11/2026), nên không tính lúc mở trang.
- API tính nền bằng 2 luồng (4 luồng làm chậm việc mở sổ đang diễn ra; đo 1/11/2026): lúc khởi động, và một lần sau mỗi đợt bản chụp Sheet (chờ cả ba runner ghi xong, file mới nhất cũ hơn 90 giây).
- Sau một lệnh ghi (POST có `customer_id`), sổ đó được đánh dấu "cần tính lại" và tính lại ngay ở lần `GET /api/v7/inbox` sau.

## Giao tiếp frontend–backend (bước 5)

`GET /api/v7/inbox` (không tham số; tham số lạ trả 400; danh tính như mọi route):

```json
{"state": "ready", "computed_at": "2026-11-01T08:00:00+00:00", "sheet_at": "2026-11-01T07:45:00+00:00",
 "refreshing": false, "books_total": 236, "books_done": 236, "failed": [],
 "books": [{"customer_id": 7,
   "receipts": {"ready": 2, "review": 1, "amount_vnd": "150000000"},
   "removed": {"count": 0, "amount_vnd": "0"},
   "trips_new": 3, "trips_check": {"count": 2, "reasons": {"OTHER_BOOK_LEGACY": 2}},
   "text_diff": 5, "prices": {"ready": 0, "review": 1}, "ps": {"ready": 0, "review": 2}}]}
```

- `state`:
  - `computing`: chưa có lần tính nào xong, `books` rỗng;
  - `ready`: có kết quả; khi đang tính lại nền thì `refreshing: true` và `books` vẫn là kết quả cũ;
  - `unavailable`: không đọc được bản chụp.
- `failed`: id các sổ tính lỗi. Khối ghi "n sổ chưa tính được", không giả là không có việc.
- `books` chỉ có sổ có ít nhất một việc. Tiền là chuỗi số nguyên VND. `amount_vnd` của phiếu thu cộng cả phiếu sẵn sàng và phiếu cần xem; phiếu không có số tiền thì không cộng (không coi trống là 0).

## Nguồn quyết định

- [`HANG-CHO-01`](../docs/decisions/hang-cho-01.md): hộp chung, chia việc theo ai phải quyết. P1 chỉ là phần xem.
- [`THU-SHEET-01`](../docs/decisions/thu-sheet-01.md), [`NHAP-SHEET-02`](../docs/decisions/nhap-sheet-02.md): nút ghi vẫn ở sổ.
- [`DASH-03`](../docs/decisions/dash-03.md): Việc cần làm là tab của người nhập.

## Hành vi và bất biến

- Chỉ đọc. Không gọi hàm ghi. Không đổi số dư, phân bổ hay khóa tháng.
- Kết quả hộp bằng đúng kết quả hàm chiếu khi mở từng sổ: cùng hàm `ledger_projections`.
- Không coi trống là 0. Sổ tính lỗi được liệt kê.
- Trạng thái trên trang:
  - đang tính lần đầu;
  - sẵn sàng;
  - đang tính lại (vẫn hiện kết quả cũ, ghi "đang cập nhật");
  - không có việc ("Không còn việc từ Sheet");
  - không đọc được Sheet;
  - một số sổ lỗi;
  - lỗi tải (câu tiếng Việt và nút Thử lại; chỉ khối này lỗi, các nhóm cũ vẫn hiện).

## Tiêu chí nghiệm thu

- [ ] Unit Python: gom đúng bảy nhóm từ kết quả chiếu; sổ không có việc bị bỏ; sổ lỗi vào `failed`; đánh dấu sổ sau POST rồi tính lại ở GET sau; bản chụp đổi thì tính lại nền; tham số lạ trả 400.
- [ ] Trình duyệt (Playwright, máy chủ giả): khối hiện đủ nhóm, xếp theo tiền; các trạng thái đang tính, trống, một số sổ lỗi, lỗi tải; nút "Mở sổ" đúng địa chỉ; khung 1280×560 không cuộn ngang.
- [ ] `npm run check` xanh.
- [ ] Trên `hao` sau triển khai: `GET /api/v7/inbox` trả `ready` trong khoảng 1–2 phút sau khởi động, tổng đếm bằng phép đo chỉ đọc cùng giờ.
- [ ] Người dùng tự mở "Việc cần làm" trên `hao`, đi một vòng (mở một sổ từ khối, làm xong, quay lại thấy dòng biến mất) và xác nhận.
