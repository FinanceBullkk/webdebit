# Checklist bắt đầu chạy song song Sheet–web

Lập 22/10/2026 (Claude, phiên điều phối). Trạng thái từng mục lấy từ [`decisions.md`](decisions.md) trên `main` tại `71090b4`; không kiểm lại live trong lần lập này. Bằng chứng thật (báo cáo, hash, log) giữ ngoài Git như runbook quy định; ô "Bằng chứng" chỉ ghi loại bằng chứng cần có.

Ngày bắt đầu song song chính thức là ngày mọi mục **Chặn** dưới đây ĐẠT và chủ nghiệp vụ chốt ngày ([`SONG-SONG-02`](decisions.md#song-song-02) còn mở). Mục **Không chặn** làm trong lúc chạy song song, nhưng phải xong trước ngày chuyển hẳn.

Vai trò: **Chủ NV** = chủ nghiệp vụ (người dùng); **Admin** = người chạy lệnh trên `hao` (hiện cũng là người dùng); **Người nhập**; **Claude** = điều phối, spec, review; **Codex** = code backend ([vai trò](multi-agent.md)).

## A. Dữ liệu

| # | Điều kiện | Mức | Ai | Bằng chứng cần có | Trạng thái 22/10 |
| --- | --- | --- | --- | --- | --- |
| A1 | Mốc `clean-v2` nạp vào `webdebit_v7`, checker và đối soát với mốc đạt | Chặn | Admin | Checker OK, `DOI SOAT: DAT` 236 khách | **ĐẠT** 21/10, đọc lại sau đợt nâng 22/10 |
| A2 | Mọi thay đổi trên Sheet sau mốc (khoảng 9 giờ 21/10) đã dán bù lên web: chuyến mới, thu, sửa dòng cũ | Chặn | Người nhập | Đối soát `--totals-only` với bản xuất Sheet mới nhất ngày bắt đầu: mã thoát 0, tất cả `KHOP` | CHƯA |
| A3 | Hai khách bị giữ ở các bản xuất sau `clean-v2` (một tab trùng tên, một thiếu số dư đầu) có cách xử lý đã chốt | Chặn | Chủ NV quyết, Claude ghi `decisions.md` | Dòng quyết định; khách đó `KHOP` hoặc được ghi rõ là ngoài phạm vi đối soát | CHƯA chốt |
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
| C1 | Backup V7 tự động hằng ngày bằng `v7_backup.py`, giữ nhiều bản, ngoài repo | Chặn | Codex viết mẫu timer vào runbook, Admin cài | `MANIFEST.json` của hai ngày liên tiếp | CHƯA: chỉ có backup trước mỗi đợt nâng |
| C2 | Phục hồi thử một bản backup định kỳ ra DB mới, khớp số đếm | Chặn | Admin | Báo cáo restore khớp exact counts | CHƯA cho bản định kỳ (đã làm trước đợt nâng 22/10) |
| C3 | Rollback A/B/C có trong runbook | Chặn | — | [Runbook mục 7](v7-deploy-runbook.md), tổng duyệt Docker 21/10 | **ĐẠT** về tài liệu |
| C4 | Người chạy đối soát cuối ngày biết cách chạy và đọc kết quả | Chặn | Claude viết hướng dẫn ngắn, Người nhập chạy thử một lần | Một lần chạy thử có mã thoát và số đếm | CHƯA |

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
| E1 | Hàm kết luận CHỜ KIỂM → `confirmed` (hoặc loại bỏ) có lý do ([`NEWTRIP-01`](decisions.md#newtrip-01)) | Chặn | Claude spec, Codex code, Admin triển khai | Test PostgreSQL xanh trên CI, đợt nâng theo runbook | CHƯA có hàm. Không có nó, chuyến nghi trùng nằm ngoài số dư mãi và đối soát tổng khách lệch không sửa được |

## F. Chốt và khởi động

| # | Việc | Ai | Bằng chứng |
| --- | --- | --- | --- |
| F1 | Xác nhận mọi mục **Chặn** ở A–E đạt | Claude | Bảng này cập nhật, có link bằng chứng |
| F2 | Chốt ngày bắt đầu song song chính thức | Chủ NV | Dòng cập nhật `SONG-SONG-02` |
| F3 | Từ ngày đó: đối soát cuối mỗi ngày (Người nhập), xem tổng kết cuối tuần và cuối tháng (Chủ NV) | Người nhập, Chủ NV | Báo cáo đối soát ngoài Git |
| F4 | Chuyển hẳn: ít nhất một lần cuối tháng khớp, Chủ NV duyệt, khóa Sheet chỉ xem ([`SONG-SONG-01`](decisions.md#song-song-01)) | Chủ NV | Quyết định chuyển hẳn trong `decisions.md` |

## Cách cập nhật

Đổi trạng thái một mục chỉ khi có bằng chứng đúng môi trường; ghi ngày và nơi giữ bằng chứng. Quyết định mới (A3, A4, F2) ghi vào `decisions.md`, file này chỉ trỏ tới.
