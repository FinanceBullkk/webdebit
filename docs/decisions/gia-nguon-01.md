# GIA-NGUON-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Tới ngày chuyển hẳn sang web ([`SONG-SONG-01`](song-song-01.md)), **đơn giá và phụ phí mà web nhận từ Sheet lấy từ sổ gốc** (các tab khách trong file sổ gốc), qua runner giá và hàng chờ "Ghi N giá từ Sheet" ([spec](../../specs/v7-price-queue.md)). Web không lấy đơn giá từ `NHAP_GIA`/`GIA_WECHAT`/`CONT_MASTER` của bộ lập bill CHAU_HAO. Hai tab đó vẫn là nguồn giá để in bill trong CHAU_HAO.

Hệ quả: người nhập vẫn ghi giá vào sổ gốc như hiện nay. Giá có trong bộ lập bill mà chưa có trong sổ gốc thì web chưa có giá (chuyến hiện "chưa có giá"). Phần phụ phí theo từng loại (Neo, Điện, Ghép…) vẫn đọc từ `CONT_MASTER` theo [`v7-phu-phi-tu-ps`](../../specs/v7-phu-phi-tu-ps.md); quyết định này chỉ nói về đơn giá và tổng phụ phí ghi theo sổ gốc.

Phương án đã cân nhắc: lấy giá từ `CONT_MASTER` để bill và web cùng một số. Không chọn vì trong thời gian chạy song song, sổ gốc là sổ chính thức; xét lại khi chuyển hẳn.

## Ngày / nguồn

29/10/2026, người dùng trả lời "Sổ gốc" khi Claude hỏi nguồn đơn giá chuẩn cho web (CONT_MASTER hay sổ gốc), trong phần đề xuất kiến trúc nối Sheet ↔ web ([spec](../../specs/v7-sheet-contract.md)).

## Trạng thái

ĐÃ CHỐT. Đúng với cách web đang chạy (runner giá đọc sổ gốc từ 28/10/2026), không đổi code.
