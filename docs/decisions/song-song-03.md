# SONG-SONG-03

[← Sổ quyết định](../decisions.md)

## Quyết định

Cách xử lý hai khách bị giữ ở các bản xuất Sheet sau mốc `clean-v2` ([`SONG-SONG-02`](song-song-02.md), mục A3 của [checklist song song](../song-song-checklist.md)). Tên khách, số tiền và tên tab giữ ngoài Git.

1. **Khách có hai tab chỉ khác khoảng trắng đầu tên.** Hai tab cùng ba chuyến nhưng ra số khác nhau. Tab có khoảng trắng là sổ đúng: bản ghi tháng sau, đã ghi phần cấn trừ, khớp số còn phải thu trên `TONG`. Tab kia là bản cũ còn sót. **Đã sửa trên Sheet nguồn 30/10/2026** (Claude đổi tên qua Google Sheets theo yêu cầu người dùng, chỉ đổi tên tab, không sửa ô): tab cũ đổi tên thêm hậu tố "(cũ)", tab đúng đổi về tên không khoảng trắng. Từ bản xuất sau lần sửa này, không cần `--raw-tab` cho khách này. Không đổi số tiền nào trên Sheet hay web.
2. **Khách có trong sổ gốc và trên `TONG` (còn số phải thu) nhưng Sheet không còn tab nào.** Không dựng được tháng và số dư đầu từ Sheet (`MISSING_SOURCE_TAB`, kéo theo `MISSING_MONTH_ANCHOR`, `NO_ANCHOR`, `MISSING_OPENING_ANCHOR`). Chưa rõ khách đã trả, cần xóa nợ hay tab bị xóa nhầm, nên **tạm để ngoài phạm vi đối soát hằng ngày**: không bỏ dòng `TONG`, không ghi phiếu thu hay điều chỉnh nào trên web cho khách này. Việc xác định khách này đúng là khách bị giữ ở bản xuất 21/10 dựa trên đối chiếu tab với `TONG` ngày 30/10, chưa chạy lại `v7_export_clean.py` với bộ CSV sổ gốc.

Hệ quả cho [đối soát cuối ngày](../doi-soat-cuoi-ngay.md): khi bước làm sạch chỉ giữ đúng một khách với bộ mã ở (2), chạy lại với `--hold-out`. Đối soát sau đó báo khách này `CHI_CO_WEB` nếu sổ của khách còn trên web. Nếu đó là chỗ lệch duy nhất thì coi như đạt cho đối soát hằng ngày. Khác đi (thêm khách bị giữ, mã lý do khác, khách khác lệch) thì dừng và báo như cũ.

## Ngày / nguồn

30/10/2026, người dùng chọn trong chat sau khi Claude đọc tab và `TONG` của Sheet nguồn: (1) "chọn a" (giữ tab có khoảng trắng, đổi tên), "Claude đổi tên giúp"; (2) "Chưa rõ, để ngoài".

## Hiệu lực và giới hạn

ĐÃ CHỐT. (1) ĐÃ TRIỂN KHAI trên Sheet nguồn 30/10/2026; chưa kiểm chứng bằng một lần chạy `v7_export_clean.py` trên bản xuất mới. (2) CÒN MỞ: chủ nghiệp vụ xác định số phải thu của khách này (đã trả, xóa nợ hay khôi phục tab). Khách này phải xử lý xong trước ngày chuyển hẳn ([`SONG-SONG-01`](song-song-01.md), mục F4), vì đối soát cuối tháng không được còn khách ngoài phạm vi.
