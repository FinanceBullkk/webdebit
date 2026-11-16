# CHUYEN-BO-CHU-HANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: chuyến bộ trên `CONT_BO` mà **chưa có ở tab khách nào** trên Sheet thì máy tự đưa vào sổ **theo CHỦ HÀNG**, không chờ tab khách nữa. Luật cũ của [`NGUON-CHUYEN-01`](nguon-chuyen-01.md) vẫn đứng trước: chuyến đã có ở đúng một tab thì sổ theo tab.

Máy chỉ xếp theo chủ hàng khi chắc chắn:

1. Chủ hàng đó (so tên bỏ khoảng trắng thừa, không phân biệt hoa thường, giữ số mã) đã có **ít nhất 3 chuyến** `CONT_BO` được tab xếp vào sổ, và **cả 3 cùng một sổ**. Chủ hàng từng vào hai sổ (thường là kho đóng hàng cho nhiều khách) hoặc chưa đủ 3 chuyến thì vẫn chờ tab, như trước.
2. Tab không còn dòng cùng container cách không quá 31 ngày (dòng không ngày: tháng nợ liền kề) mà chưa dòng `CONT_BO` nào nhận. Dòng như vậy thường là chính chuyến này với ngày gõ lệch, nên vẫn chờ tab, theo bài học của [`CONTAINER-DUNG-LAI-01`](container-dung-lai-01.md).

Hai dòng `CONT_BO` cùng container, cách không quá 3 ngày, cùng vào một sổ theo chủ hàng thì không đưa vào dòng nào (có thể là một chuyến ghi hai lần), chỉ đếm.

Sau đó chuyến đi tiếp đúng đường có sẵn của chuyến bộ: đã có trong sổ trong 3 ngày thì bỏ; vướng sổ hay khách khác thì để người; máy chỉ tự dán khi ngày không sau hôm nay và tháng từ 10/2026 (tháng khóa thì mở, dán, khóa lại theo `MAY-KHOA-01`). Chuyến vào sổ **chưa có giá**, nên chưa làm tăng nợ; giá vào khi tab khách có dòng, theo `MAY-GIA-01`. Đến lúc đó web hiện chuyến "thiếu giá" để người biết Sheet còn thiếu.

## Vì sao

Đối chiếu tháng 10/2026 với booking (16/11/2026) tìm ra chuyến `PCIU6051073` ngày 11/10 của CHANGHONG 379 có trên `CONT_BO` nhưng không có trên Sheet lẫn web. Chuyến này là chuyến thật: "XE 10" của lô (lô đánh số xe 1–11), số thùng 921 khác chuyến 20/9 (863), người phụ trách khác. Tab CHANG HONG chưa ghi tháng 10, nên luật cũ giữ nó ngoài sổ. Claude giải thích luật, người dùng chọn đổi: "đổi luật để chuyến bộ tự vào sổ theo chủ hàng".

Đo chỉ đọc trên bản chụp `road.json` và `prices.json` của `hao` sáng 16/11/2026:

| | Luật cũ | Luật mới |
|---|---|---|
| Chuyến từ 10/2026 xếp theo tab | 200 | 200 (y hệt từng dòng) |
| Chuyến chưa ở tab nào | 31 chờ | 31 theo chủ hàng, 0 chờ |

31 chuyến ở 6 sổ: DUONG BO HÂN HƯNG 324 (19), HTH352 (6), DUONG BO KPP (3), CHANG HONG (2), DUONG BO ALEX 368 (1). 30 chuyến tháng 11, 1 chuyến tháng 10. 38 chủ hàng từng ghép được; 37 chỉ vào một sổ, chủ hàng ít chuyến nhất có 4. Chủ hàng duy nhất vào hai sổ là HUYNH NUONG 289 (198 chuyến một sổ, 2 chuyến sổ khác): theo luật này nó vẫn chờ tab.

## Ngày / nguồn

16/11/2026, chat, sau bản đối chiếu tháng 10 Sheet ↔ booking ↔ web (hồ sơ ngoài Git, `captures/2026-11-16-thang-10-booking/`). Ngưỡng 3 chuyến và 31 ngày do Claude chọn khi code, theo số đo trên.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi code app (`v7_road_queue.py`), không có migration, không ghi Sheet. Không đổi quy tắc phân bổ.

Giới hạn:

- Chủ hàng đổi sang khách khác mà vẫn giữ tên thì chuyến vào sổ cũ; vì chưa có giá nên chưa đổi nợ, và vẫn vướng chặn sổ khác khi tab khách mới có dòng.
- `CONT_BO` ghi trùng một chuyến ở hai ngày xa nhau (quá 3 ngày) thì thành hai chuyến chưa giá; người thấy chuyến thiếu giá mà tab không có.
- Chủ hàng mới (chưa đủ 3 chuyến) vẫn chờ tab.
