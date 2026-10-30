# Checklist bắt đầu chạy song song Sheet–web

Lập 22/10/2026 (Claude, phiên điều phối). Trạng thái từng mục lấy từ [`decisions.md`](decisions.md) trên `main` tại `71090b4`; không kiểm lại live trong lần lập này. Bằng chứng thật (báo cáo, hash, log) giữ ngoài Git như runbook quy định; ô "Bằng chứng" chỉ ghi loại bằng chứng cần có.

**Cập nhật 27/10/2026** (Claude, đọc code trên `main` tại `b58f470` và chạy `npm run check` cục bộ; không kiểm live): ghi chú 27/10 ở A2, A3, C4, E1. Người dùng báo trong chat 27/10 rằng `hao` đã nhận code mới và đang chạy; chưa có bằng chứng revision trong repo.

**Cập nhật 29/10/2026** (Claude, cài và kiểm live trên `hao`): C1, C2.

**Cập nhật 30/10/2026** (Claude, kiểm live trên `hao` sau lượt timer 02:40): C1. Cùng ngày (Claude, đọc Sheet nguồn qua Google Sheets, người dùng chốt trong chat): A3, C4.

**Cập nhật 31/10/2026** (Claude, chỉ đọc: bản xuất Sheet lúc 23:58 ngày 30/10 tải bằng `v7_sheet_export_xlsx.py` trên `hao` và GET API `hao`; không ghi gì): A2, C4, E1. Kết quả có tên khách và số tiền giữ ngoài Git.

Ngày bắt đầu song song chính thức là ngày mọi mục **Chặn** dưới đây ĐẠT và chủ nghiệp vụ chốt ngày ([`SONG-SONG-02`](decisions.md#song-song-02) còn mở). Mục **Không chặn** làm trong lúc chạy song song, nhưng phải xong trước ngày chuyển hẳn.

Vai trò: **Chủ NV** = chủ nghiệp vụ (người dùng); **Admin** = người chạy lệnh trên `hao` (hiện cũng là người dùng); **Người nhập**; **Claude** = điều phối, spec, review; **Codex** = code backend ([vai trò](multi-agent.md)).

## A. Dữ liệu

| # | Điều kiện | Mức | Ai | Bằng chứng cần có | Trạng thái 22/10 |
| --- | --- | --- | --- | --- | --- |
| A1 | Mốc `clean-v2` nạp vào `webdebit_v7`, checker và đối soát với mốc đạt | Chặn | Admin | Checker OK, `DOI SOAT: DAT` 236 khách | **ĐẠT** 21/10, đọc lại sau đợt nâng 22/10 |
| A2 | Mọi thay đổi trên Sheet sau mốc (khoảng 9 giờ 21/10) đã dán bù lên web: chuyến mới, thu, sửa dòng cũ | Chặn | Người nhập | Đối soát `--totals-only` với bản xuất Sheet mới nhất ngày bắt đầu: mã thoát 0, tất cả `KHOP` | CHƯA. **27/10:** đã có đồng bộ chuyến Sheet → web (`sheet_sync_runner.py`, hàng chờ trong sổ khách, nút "Duyệt … chuyến mới", đối chiếu lệch từng trường), nên chuyến mới không phải dán tay. Đồng bộ chuyến **không** mang đơn giá/phụ phí và **không** có phiếu thu. **28/10:** giá đã có đường riêng, nút "Ghi N giá từ Sheet" (runner đọc tab khách 15 phút một lần, triển khai `hao` 27/10, [spec](../specs/v7-price-queue.md)); người nhập vẫn phải bấm ghi. Phiếu thu vẫn nhập tay. **30/10:** đối soát chỉ đọc trên bản tải mới (không cần bộ CSV 20/10): 223/238 khách khớp tổng, 12 lệch; 9/12 do phiếu thu Sheet chưa có trên web. Thêm đường phiếu thu ([`THU-SHEET-01`](decisions/thu-sheet-01.md), [spec](../specs/v7-receipt-queue.md)): nút "Ghi N phiếu thu từ Sheet", phiếu không chắc (không ngày, Sheet sửa phiếu cũ) vào "Cần xem". **31/10 (bản xuất cuối ngày 30/10, chỉ đọc):** 236/236 sổ web có tab Sheet cùng tên; 223 khớp tổng, 13 lệch. Nguyên nhân (một khách có thể nhiều): 6 phiếu thu READY chờ bấm "Ghi phiếu thu từ Sheet"; 4 phiếu thu Sheet không có ngày (ở "Cần xem", điền ngày trên Sheet rồi ghi); 2 Sheet sửa phiếu cũ; 3 chuyến mới chưa duyệt hoặc chưa giá; 2 giá lệch Sheet–web ("Cần xem"); 1 phiếu thu ghi trên dòng chuyến với ngày ngoài khối tháng nên không vào hàng chờ (nhập tay). 12 tab Sheet không có sổ web: 9 ngoài TONG (bản sao, tab cũ, nháp), 3 trên TONG (1 bố cục không đọc được, 1 khách mới sau mốc đang chờ tạo sổ ở hàng chờ chuyến `NEEDS_CUSTOMER`, 1 số dư 0). Lần này tính tổng Sheet bằng hàm quét của loader và so với GET API vì bộ CSV mốc 20/10 nằm ngoài thư mục phiên; bằng chứng chính thức vẫn phải là `v7_export_clean` + `v7_reconcile_sheet --totals-only` |
| A3 | Hai khách bị giữ ở các bản xuất sau `clean-v2` (một tab trùng tên, một thiếu số dư đầu) có cách xử lý đã chốt | Chặn | Chủ NV quyết, Claude ghi `decisions.md` | Dòng quyết định; khách đó `KHOP` hoặc được ghi rõ là ngoài phạm vi đối soát | **ĐẠT 30/10** về quyết định ([`SONG-SONG-03`](decisions/song-song-03.md)): khách tab trùng tên đã sửa trên Sheet (đổi tên tab); khách không còn tab tạm ngoài phạm vi đối soát hằng ngày, CÒN MỞ tới trước F4. Chưa kiểm chứng bằng một lần chạy `v7_export_clean.py` trên bản xuất mới. (27/10: mục này chặn C4 vì `v7_export_clean.py` thoát mã 2 khi có khách bị giữ.) |
| A4 | Cách tìm dòng cũ trong mốc bị sửa trên Sheet | Không chặn | Claude chốt, Codex code nếu cần | Capture-only đã chạy trên Sheet thật từ 21/10 16:26 ([spec](../specs/sheet-capture.md)); còn thiếu bước đọc log ra danh sách dòng cần dán | ĐỀ XUẤT: đối soát tổng khách bắt lệch tiền, log capture dùng để truy dòng |
| A5 | Đóng băng nguồn bằng hash xlsx ([`V7-CSM`](decisions.md#v7-csm) (5), case `7.11c`) | Không chặn | Claude spec, Codex code | Spec riêng, test `7.11c` thành BEHAVIOR | CHƯA cài; chỉ cần nếu nạp lại mốc |

## B. Danh tính và quyền vào

| # | Điều kiện | Mức | Ai | Bằng chứng cần có | Trạng thái 22/10 |
| --- | --- | --- | --- | --- | --- |
| B1 | Mỗi người nhập có tài khoản Tailscale riêng, vào được URL Serve của V7 | Chặn | Admin | Danh sách người dùng tailnet (ngoài Git) | CHƯA: tailnet một tài khoản |
| B2 | Hai người khác nhau ghi ra hai tên khác nhau trong Lịch sử ([`V7-ID`](decisions.md#v7-id)) | Chặn | Người nhập + Claude đọc lại | Mỗi người mở rồi khóa lại một tháng đã khóa: Lịch sử có hai cặp dòng với hai tên; số dư không đổi | CHƯA |
| B3 | Gỡ một người khỏi tailnet thì người đó không vào được | Không chặn | Admin | Thử gỡ một thiết bị thử, ghi kết quả | CHƯA |

B2 dùng mở/khóa tháng vì thao tác này ghi Lịch sử mà không đổi tiền, không cần phiếu thử trên dữ liệu thật. Đồng thời là bằng chứng D07 trên `hao` (mục D3).

## C. Vận hành

| # | Điều kiện | Mức | Ai | Bằng chứng cần có | Trạng thái 22/10 |
| --- | --- | --- | --- | --- | --- |
| C1 | Backup V7 tự động hằng ngày bằng `v7_backup.py`, giữ nhiều bản, ngoài repo | Chặn | Claude viết mẫu timer vào runbook và cài sau khi người dùng duyệt | `MANIFEST.json` của hai ngày liên tiếp | **ĐẠT 30/10:** timer `v7-backup-daily` cài trên `hao` 29/10 (02:40 giờ VN, giữ 30 bản, [runbook](v7-deploy-runbook.md#backup-hằng-ngày--timer-v7-backup-daily), [nhật ký](deploys/2026-10-29-v7-backup-daily.md)). Hai ngày liên tiếp có bản do unit `v7-backup-daily` tạo: `v7-20261029-194852` (chạy tay qua unit) và `v7-20261030-024010` (lượt timer 02:40 giờ VN 30/10, `Result=success`), cả hai `verify` MATCH. Bằng chứng `day2-*.txt` ở thư mục `v7-backup-daily-install-20261029-194749` trên `hao`, ngoài Git |
| C2 | Phục hồi thử một bản backup định kỳ ra DB mới, khớp số đếm | Chặn | Claude, theo runbook B4 | Báo cáo restore khớp exact counts | **ĐẠT 29/10:** bản `v7-20261029-194852` phục hồi ra DB tạm mới trên `hao`: `MATCH`, số dòng 31 bảng và tổng nợ 236 khách khớp `MANIFEST.json`; đã xóa DB tạm. Báo cáo ở thư mục `v7-backup-daily-install-20261029-194749` trên `hao`, ngoài Git ([nhật ký](deploys/2026-10-29-v7-backup-daily.md)) |
| C3 | Rollback A/B/C có trong runbook | Chặn | — | [Runbook mục 7](v7-deploy-runbook.md), tổng duyệt Docker 21/10 | **ĐẠT** về tài liệu |
| C4 | Người chạy đối soát cuối ngày biết cách chạy và đọc kết quả | Chặn | Claude viết hướng dẫn ngắn, Người nhập chạy thử một lần | Một lần chạy thử có mã thoát và số đếm | **27/10:** hướng dẫn đã viết ([đối soát cuối ngày](doi-soat-cuoi-ngay.md)). CHƯA chạy thử. **30/10:** A3 đã chốt, hướng dẫn thêm cách chạy `--hold-out` khi chỉ còn khách ngoài phạm vi; hết phụ thuộc A3. **31/10:** Claude chạy lần ba (chỉ đọc, kết quả ở A2); người nhập vẫn chưa tự chạy |

## D. Hành vi ghi trên `hao`

Runbook cấm ghi phiếu thử trên dữ liệu thật, nên mục D nghiệm thu bằng **thao tác thật đầu tiên** của từng loại sau ngày bắt đầu (Sheet vẫn là sổ chính thức nên sai sót sửa được bằng hủy/điều chỉnh). Không chặn ngày bắt đầu; mục nào hỏng thì dừng dùng loại thao tác đó trên web và báo Claude.

| # | Hành vi | Ai | Bằng chứng | Trạng thái 22/10 |
| --- | --- | --- | --- | --- |
| D1 | Dán lô chuyến mới ghi `confirmed`, chuyến nghi trùng ghi CHỜ KIỂM, ngoài số dư | Người nhập, Claude đọc lại | Lần dán đầu; lần trùng đầu tiên nếu có | Chưa có lần dán thật |
| D2 | Phiếu thu có ô Tham chiếu; trùng tham chiếu cùng sổ thì cảnh báo, không chặn | Người nhập | Phiếu thu thật đầu tiên có tham chiếu | Chưa thử |
| D3 | Mở/khóa tháng ghi Lịch sử | Người nhập | Từ B2 | Chưa thử |
| D4 | Hủy phiếu bắt buộc lý do; cấn trừ hai sổ ([`CT-2SO`](decisions.md)) | Người nhập | Lần hủy/cấn trừ thật đầu tiên | Chưa thử trên `hao` |

## E. Chức năng còn thiếu

| # | Việc | Mức | Ai | Bằng chứng cần có | Trạng thái 22/10 |
| --- | --- | --- | --- | --- | --- |
| E1 | Kết luận chuyến CHỜ KIỂM: tính vào sổ hoặc loại, có lý do ([`NEWTRIP-01`](decisions.md#newtrip-01), [spec](../specs/v7-trip-review.md)) | Chặn | Claude spec + code, Người dùng duyệt luồng giao diện, Admin triển khai | Test PostgreSQL xanh trên CI; đợt nâng theo runbook (migration `2026-10-22-v7-trip-review.sql`); một lần kết luận thật trên `hao` có dòng Lịch sử | **Backend/API ĐÃ CODE** trên `main` (PR #63, #64, CI xanh). CHƯA: nút trên giao diện (chờ duyệt luồng), triển khai `hao`. **27/10:** nút "Tính vào sổ"/"Loại" đã có trên `main` (Playwright xanh với máy chủ giả); chưa có lần kết luận thật trên `hao`. Chưa xong thì chuyến nghi trùng vẫn nằm ngoài số dư và đối soát tổng khách lệch không sửa được. **31/10:** nút đã có trên `hao` (release theo `main`); GET API cho thấy không có chuyến CHỜ KIỂM nào đang chờ, nên lần kết luận thật chờ lần phát sinh đầu |

## F. Chốt và khởi động

| # | Việc | Ai | Bằng chứng |
| --- | --- | --- | --- |
| F1 | Xác nhận mọi mục **Chặn** ở A–E đạt | Claude | Bảng này cập nhật, có link bằng chứng |
| F2 | Chốt ngày bắt đầu song song chính thức | Chủ NV | Dòng cập nhật `SONG-SONG-02` |
| F3 | Từ ngày đó: đối soát cuối mỗi ngày (Người nhập), xem tổng kết cuối tuần và cuối tháng (Chủ NV) | Người nhập, Chủ NV | Báo cáo đối soát ngoài Git |
| F4 | Chuyển hẳn: ít nhất một lần cuối tháng khớp, Chủ NV duyệt, khóa Sheet chỉ xem ([`SONG-SONG-01`](decisions.md#song-song-01)) | Chủ NV | Quyết định chuyển hẳn trong `decisions.md` |

## Cách cập nhật

Đổi trạng thái một mục chỉ khi có bằng chứng đúng môi trường; ghi ngày và nơi giữ bằng chứng. Quyết định mới (A3, A4, F2) ghi vào `decisions.md`, file này chỉ trỏ tới.
