# Kiểm tab trước khi ghi, đợt 1: sức khỏe tab, `row_shift`, chặn ghi

Trạng thái: ĐÃ CODE (Claude, 16/11/2026), chờ merge và triển khai. Đợt 1 của đề xuất KIEM-TAB-01 ([`v7-kiem-tab-truoc-khi-ghi.md`](v7-kiem-tab-truoc-khi-ghi.md), mục K1 bước 1–3, phần `row_shift` và `HELD`). Mục này ghi chi tiết đợt 1: **luật miễn trừ bố cục hai dòng** (đã tóm ở K1 mục 5 của spec gốc) và **bằng chứng đo**.

## Đầu ra

- `tools/v7_tab_health.py` (nhận kết quả `scan_tabs` có sẵn và các dòng thô của tab, không sửa bộ quét) trả `health` cho từng tab: `{status: ok | broken, findings}`. Mỗi `finding` có `kind`, `level` (`error` hoặc `note`). `broken` khi có `finding` mức `error`: lỗi bộ quét đã đếm (`issues`, đúng các lỗi làm máy giữ khách) hoặc `row_shift`.
- `row_shift`: trong cùng khối tháng, hai dòng chuyến sát nhau (số dòng hơn kém 1): một dòng có container mà TỔNG trống hoặc 0, dòng kia có TỔNG khác 0 mà không container. Ưu tiên ghép "container trên, tiền dưới"; chỉ dòng container còn lại mới ghép với "tiền trên"; dòng tiền ngay dưới một chuyến đã có tiền là phí của chuyến đó, không ghép. `finding` nêu hai ô (`cells`, ví dụ `B15` và `L16`), `rows`, `order`, câu giải thích và cách sửa gợi ý.
- Bản chụp giá và phiếu có `tabs` (cùng lượt quét, cùng file với `rows`); hash vẫn tính trên `rows`.
- Tab `broken`: `v7_sheet_fix.plan` không trả nhóm nào; `apply_fix(health=…)` ném `409 TAB_BROKEN` trước mọi lệnh; bảng đối chiếu trả `groups` rỗng kèm `blocked`, `POST /api/v7/sheet/doi-chieu/ghi` trả `409 TAB_BROKEN` trước mọi kiểm khác; máy đối soát giữ khách (`reason = HELD`, `held_reasons` kiểu `ROW_SHIFT`). Khách đang `HELD` trong `reconcile.json` cũng bị bảng đối chiếu chặn. Duyệt chuyến không bị chặn.
- Chưa làm ở đợt này: giá Sheet và phiếu Sheet (`/sheet/prices`, `/sheet/tasks/price`, `/sheet/receipts`) vẫn chưa kiểm `health`; khối "Sheet cần sửa" trên màn (đợt 3); `chain_break` nêu ô, `negative_receipt`, `duplicate_container` (đợt 3).

## Miễn trừ bố cục hai dòng (Claude chốt 16/11/2026 theo quyền người dùng trao 21/10)

Bố cục "hai dòng mỗi container" (dòng container không tiền, tiền ở dòng không container ngay dưới) và "tiền lệch một dòng" nhìn như nhau trong dữ liệu; chỉ người biết tab mới phân được. Vì vậy:

1. Danh sách tab được duyệt bố cục hai dòng khai tay ở một chỗ: `TWO_ROW_LAYOUT_TABS` trong `tools/v7_tab_health.py`, kèm ghi chú nguồn. Không suy ra tự động, không dùng ngưỡng số cặp (ngưỡng sẽ miễn đúng ca nguy hiểm nhất: cả khối lệch một dòng ra nhiều cặp). Hiện chỉ có "KK - DỪA": audit 4/11/2026, tổng khớp tới từng đồng, nạp thành "Phí lẻ".
2. Miễn chỉ áp cho khối đều đặn: mọi cặp của khối đều "container trên, tiền ngay dưới". Khối có một cặp ngược (tiền trên, container dưới) thì mọi cặp của khối vẫn là `row_shift`, kể cả ở tab được miễn. Chuyến một dòng (container và tiền cùng dòng) xen giữa các cặp là thói quen của tab, không làm khối thành không đều.
3. Cặp được miễn vẫn nằm trong `findings` ở mức `note` (`two_row_layout`, "bố cục hai dòng đã duyệt"): không chặn, nhưng màn và lượt đo còn thấy. Lỗi `issues` ở tab được miễn vẫn chặn như mọi tab.

Cách đọc "không có dòng container vừa có container vừa có tiền xen giữa" của yêu cầu: không có dòng như vậy **giữa dòng container và dòng tiền của một cặp** (hai dòng sát nhau). Đo trên `hao` cho thấy khối T9 và T11/2026 của "KK - DỪA" có chuyến một dòng xen *giữa các cặp*; đọc theo nghĩa rộng (không có giữa bất kỳ cặp nào) thì tab này vẫn bị chặn, trái mục đích miễn trừ.

## Bằng chứng

Đo chỉ đọc trên `hao`, 16/11/2026 (chép release sang thư mục tạm, đè hai file mới, đọc Sheet qua Sheets API bằng cùng tài khoản đọc của runner, tính trong bộ nhớ, không ghi file nào, đã xóa thư mục tạm):

- Luật `row_shift` thuần theo đề xuất: 253 tab quét, 10 tab `broken` (8 chỉ vì `issues` sẵn có, 1 chỉ vì `row_shift`, 1 cả hai). `row_shift` ra ở 2 tab: tab sổ 239 (khối T10, 2 cặp, đúng ca thật) và "KK - DỪA" (48 cặp ở T8–T11/2026).
- Sau khi thêm miễn trừ: 253 tab, **9** `broken` (8 chỉ vì `issues`, 1 vừa `issues` vừa `row_shift` là tab sổ 239); "KK - DỪA" `ok` với các `note`. `reconcile.json` cùng lúc có 5 khách `HELD` trên 242.

## Phạm vi và kiểm

- Được sửa: `cong-no-web-handoff/tools/v7_tab_health.py` (mới), `tools/v7_price_snapshot.py`, `tools/v7_reconcile_auto.py`, `web/v7_sheet_fix.py`, `web/v7_api_doi_chieu.py`, test tương ứng, `specs/v7-viec-can-lam-doi-chieu.md`.
- Không đổi luật tiền, phân bổ, opening; không SQL, không migration.
- Test: `tests/test_v7_kiem_tab.py` (bộ quét, miễn trừ ba trường hợp, bản chụp, `plan`, `apply_fix`, máy đối soát), `tests/test_v7_api_doi_chieu.py` (bảng đối chiếu và khách `HELD`).
- Hoàn tác: revert PR; bản chụp cũ không có `tabs` được coi là chưa có kết luận (như `ok`).

## Vì sao phát hiện nằm ở `v7_tab_health.py`, không ở bộ quét (16/11/2026)

Bản đầu đặt phát hiện trong `v7_load_real_copy.py`. `Deploy hao` dừng ở cổng "diff có loader `v7_load*`" nên đợt 1 merge xong mà không lên `hao` được. Người dùng chọn "tách ra file riêng": phát hiện chuyển sang `tools/v7_tab_health.py`, bộ quét về đúng bản trước (diff rỗng so với `75cfb21`), và mọi luật kiểm mới của K1 (đợt 3) đặt ở đây. Chữ cột lấy từ dòng tiêu đề đang hiệu lực ở từng dòng (`columns_by_row`, cùng luật cột trái nhất và bảng phụ như bộ quét) rồi đổi qua `column_letter` (1 = A, 27 = AA). Web (`v7_sheet_fix.py`, `v7_api_doi_chieu.py`) không gọi module này (ARCH-02: web không nhập `tools/`); chúng đọc `tabs` trong bản chụp do `v7_price_snapshot.py` ghi.
