# Audit chỉ đọc trước khi chuyển hẳn khỏi Sheet sổ nợ

Trạng thái: ĐỀ XUẤT (Claude, 11/11/2026). Người dùng yêu cầu trong chat 11/11/2026: hỏi "cần audit những gì" để nói web thay được Sheet, bấm "Chạy phần chỉ đọc", rồi "Đưa vào repo". Danh mục kiểm ở [checklist chuyển hẳn](../docs/chuyen-han-checklist.md) do Claude đặt, chưa được duyệt từng mục.

## Đầu ra

Một lệnh chỉ đọc, `cong-no-web-handoff/tools/v7_cutover_audit.py`, chạy lại được vào cuối mỗi tháng. Lệnh trả lời bốn câu mà đối soát tổng từng khách ([`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md)) không trả lời:

1. Trong một khách đã khớp tổng, từng dòng và từng tháng có khớp không.
2. Tab TONG của Sheet có cộng đủ các tab khách không.
3. Lệnh máy đã ghi có lệnh nào người phải sửa lại không.
4. Thao tác tiền nào trên web đã có người thật làm.

Báo cáo có tên khách và số tiền ghi vào thư mục `--out` ngoài mọi repo. Stdout chỉ có số đếm.

## Nguồn quyết định

- [`SONG-SONG-01`](../docs/decisions/song-song-01.md): điều kiện chuyển hẳn là mọi khách khớp hoặc chỗ lệch đã giải thích được.
- [`CHUYEN-HAN-01`](../docs/decisions/chuyen-han-01.md): xét lại sau đối soát cuối tháng 11/2026; phạm vi là Sheet sổ nợ.
- [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md): lưới an toàn là tổng từng khách, hai lỗi bù nhau trong một khách không lộ; phép so chỉ thấy khách đã có trong phép so.
- [`CAN-DU-01`](../docs/decisions/can-du-01.md): lệch theo tháng ở cột đã thu là có chủ đích, nên phép kiểm tháng chỉ so **phát sinh**, còn thu thì so tổng cả sổ.
- Lời giải thích nào được máy nhận là ĐỀ XUẤT của Claude (bảng dưới), không phải quyết định nghiệp vụ.

## Hành vi và bất biến

- **Không ghi gì.** Phía web chỉ GET (`/api/v7/customers`, `/ledger`, `/activity`) hoặc đọc thư mục JSON đã tải. Phía Sheet đọc một bản tải xlsx (dòng chuyến, dòng thu và tab TONG từ cùng một bản), hoặc bản chụp `prices.json`, `receipts.json` của runner giá.
- **Ghép dòng dùng đúng luật của web** (`v7_price_queue.classify`, `mark_shared`), nhưng giữ cả các trạng thái màn hình không hiện: `NOT_FOUND`, `AMBIGUOUS_PRICED`, `SHEET_NO_PRICE`, `NO_CONTAINER`. Soi thêm chiều ngược: dòng web có tiền mà không dòng Sheet nào trỏ tới.
- **Tiền của một dòng Sheet** là cột TỔNG; không có TỔNG thì đơn giá cộng phụ phí. Ô trống vẫn là trống khi so từng dòng; chỉ phép cộng của báo cáo coi trống là 0.
- **Mỗi lời giải thích là một đẳng thức đúng tới từng đồng.** Không khớp thì là `CHUA_GIAI_THICH`, không có "gần đúng".

| Mã | Áp cho | Điều kiện nhận |
| --- | --- | --- |
| `WEB_DI_TRUOC` | chuyến web có giá mà Sheet chưa có dòng hoặc dòng còn trống tiền; tháng của các chuyến đó | cộng các chuyến đó của sổ bằng đúng `web_ahead_vnd` mà lượt đối soát báo, và khách đó có lý do `WEB_AHEAD` với phần lệch còn lại bằng 0 |
| `DONG_LAP_TREN_SHEET` | tháng | nhiều dòng Sheet cùng trỏ một dòng web; phần Sheet ghi thừa bằng đúng phần lệch của tháng |
| `TONG_TRAI_DEU_LUC_NAP` | dòng, tháng | dòng sổ gốc mang cờ `TOTAL_SPREAD_OVER_TRIPS`; cộng lệch các dòng đó bằng lệch của tháng |
| `BU_SO_DU_CHUYEN_NAM` | tháng, tổng thu | dòng sổ gốc mang cờ `YEAR_END_CARRY_ADJUSTED`; số của dòng đó bằng đúng phần lệch |
| `LAM_TRON_DONG` | tổng thu | sổ có dòng mang cờ `ROUNDED_VND` và lệch không quá một đồng mỗi dòng thu trên Sheet |
| `DOI_SANG_SO_KHAC` | dòng chỉ một bên có | cùng container, cùng tháng, cùng tiền: Sheet có ở tab này, web có ở sổ khác |
| `KHAC_CHU_O_CONTAINER` | dòng chỉ một bên có | cùng sổ, cùng tháng, cùng tiền, chỉ khác chữ ở ô container |
| `DA_GHI_BANG_DIEU_CHINH` | dòng chỉ Sheet có | sổ có dòng điều chỉnh cả tháng đúng số tiền đó, cùng tháng; mỗi dòng điều chỉnh chỉ dùng một lần |

- **Phép kiểm TONG.** Với khối mới nhất (ngoài cùng bên phải) của tab TONG: `TONG cuối tháng = tổng nợ web hôm nay − web đi trước − phát sinh các tháng sau trên Sheet + thu ghi ở khối các tháng sau`. Tên trên TONG so bằng chữ và số đã bỏ dấu; tên không tự ghép được thì khai `--tong-alias`. Sổ còn số kỳ vọng khác 0 mà TONG để trống thì nêu ra. Máy đối soát mỗi giờ chạy đúng phép kiểm này ([`KIEM-TONG-01`](../docs/decisions/kiem-tong-01.md)): `read_tong`, `audit_tong`, `sheet_months` là mã dùng chung, sửa ở đây là sửa cả hai.
- **Nhật ký.** Người là actor có `@`; máy là `may-theo-sheet`. Danh sách thao tác (`OPERATIONS`) được test đối chiếu với mọi loại lệnh mà `tools/v7_backend_functions.sql` ghi vào `sokhach.event`. Ngày mà API trả ít dòng hơn `total` được báo là bị cắt bớt. Cấn trừ hai sổ đếm theo trạng thái sổ (`offset_pair_id`, `outgoing_offsets`), không dựa vào nhật ký.
- **Mã thoát.** 0: không còn mục tiền nào phải có người xem. 1: còn (dòng, tháng, tổng thu chưa giải thích; tab không có sổ; TONG lệch, tên lạ hoặc để trống; phiếu máy ghi bị hủy; giá máy đè rồi bị quay lại; tháng máy mở chưa khóa). 2: lỗi đầu vào, không ghi gì. Tháng cũ đang mở, chuyến chưa giá và thao tác chưa ai dùng chỉ được đếm, không đổi mã thoát.
- Login của người không ra stdout và không ra báo cáo; chỉ có số login.

## Tiêu chí nghiệm thu

- [x] `cong-no-web-handoff/tests/test_v7_cutover_audit.py` xanh trong `npm run check`: mỗi mã giải thích có ca nhận và ca từ chối, phép kiểm TONG, nhật ký, trạng thái sổ, dòng lệnh (mã thoát 0, 1, 2; tên khách không ra stdout; không ghi vào thư mục trong repo).
- [x] Phá từng luật trong bộ nhớ thì test đỏ: nhận bừa mọi lời giải thích, so tên TONG nguyên văn, tuổi thọ dòng điều chỉnh, bỏ cột TỔNG, ghép dòng bỏ qua ngày.
- [x] Chạy trên dữ liệu thật của `hao` ngày 11/11/2026 ra đúng các số đã đo tay cùng ngày (mục Bằng chứng).
- [ ] Chạy lại sau đối soát cuối tháng 11/2026 và ghi số đếm vào [checklist](../docs/chuyen-han-checklist.md).

## Phạm vi agent

- Agent: claude
- Review: sonnet medium (công cụ chỉ đọc, không chạm đường ghi tiền)
- Được sửa:
  - `cong-no-web-handoff/tools/v7_cutover_audit.py`
  - `cong-no-web-handoff/tests/test_v7_cutover_audit.py`
  - `specs/v7-cutover-audit.md`, `specs/README.md`
  - `docs/chuyen-han-checklist.md`, `docs/song-song-checklist.md`, `docs/v7-deploy-runbook.md`
  - `docs/decisions/chuyen-han-01.md`, `docs/decisions.md`, `PLAN.md`
- Cấm:
  - Lệnh ghi lên API, DB, Sheet; thêm dependency.
  - Đưa tên khách, số tiền, login, ID Sheet vào Git.

## Hoàn tác

Revert PR. Công cụ không chạy trong service nào và không ghi dữ liệu, nên không có gì để dọn trên `hao`.

## Bằng chứng

- Lượt đo tay 11/11/2026, 17:12–17:50 giờ VN, `hao` tại `35cba76`, chỉ đọc: số đếm ở [checklist](../docs/chuyen-han-checklist.md#lượt-đo-11112026); bản có tên khách và số tiền giữ ngoài Git.
- Công cụ chạy trên chính bộ dữ liệu đó (thư mục JSON đã tải, bản chụp của runner giá, khối TONG chép tay có kiểm bằng dòng tổng): cùng số trạng thái dòng, cùng 7 tháng và 3 tổng thu có lời giải, cùng 17 dòng một bên có, cùng 14 sổ TONG để trống, cùng số lệnh máy và người.
- Đường `--api` cùng `--xlsx`, chạy 11/11/2026 khoảng 18 giờ VN trên một bản tải mới (mã băm bản chép về khớp bản trên `hao`, bản trên `hao` đã xóa): 3 phút 21 giây cho 239 sổ, mã thoát 1, kết quả giống hệt lượt trên. Tab TONG do công cụ tự đọc từ xlsx cho đúng 64 dòng khớp và 14 sổ để trống như bản chép tay.
- `npm run check` cục bộ (Windows) trên bản cuối: 8 bước đều OK; unittest Python 954 ca, 8 ca bỏ qua có sẵn (chỉ chạy trên Linux, cần quyền symlink hoặc cần bật harness Docker). `node scripts/check-secrets.js` sạch.

## Câu hỏi mở

- Đưa phép kiểm TONG vào máy đối soát mỗi giờ: **đã trả lời** 11/11/2026. Người dùng chọn kiểm mỗi giờ, chỉ báo, kết quả hiện ở đầu tab Việc cần làm ([`KIEM-TONG-01`](../docs/decisions/kiem-tong-01.md)).
- Phép kiểm "Sheet tự nó có đúng không" (so với booking, sao kê, xác nhận của khách) nằm ngoài công cụ này.
