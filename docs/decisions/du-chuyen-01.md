# DU-CHUYEN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **tiêu chí đầu tiên của web là đủ chuyến theo booking.** Thước đo này đứng trên "web khớp Sheet sổ nợ" (mục A1 của [checklist chuyển hẳn](../chuyen-han-checklist.md)). Lý do: web nạp và theo Sheet, nên Sheet sót chuyến thì web cũng sót. Khi bỏ Sheet, booking (`CONT_NGUON`, `CONT_BO`) là nguồn chuyến duy nhất.

Hướng đã chốt:

1. **Thước đo:** mỗi giờ so **sổ web ↔ booking**, cùng luật ghép và cùng các nhóm của [`KIEM-BOOKING-01`](kiem-booking-01.md). Phép so Sheet ↔ booking vẫn giữ trong lúc chạy song song ([`SONG-SONG-01`](song-song-01.md)).
2. **Chuyến vào sổ không cần Sheet có dòng.** Chuyến chưa giá không cộng nợ (NULL không phải 0), nên đưa chuyến booking vào sổ ở dạng chưa giá không đổi tổng nợ. Giá vẫn theo Sheet trong lúc song song ([`MAY-GIA-01`](may-gia-01.md)). Phần này là PR thứ hai (25/11/2026, mục "PR thứ hai" bên dưới).
3. **Tháng cũ không tự thêm.** Chuyến booking trước 10/2026 mà web chưa có thì liệt kê để chủ sổ quyết: sót tiền thật, booking ghi lặp, hay không phải tính. Lý do: các tháng đó đã khóa và đã tính tiền theo Sheet.
4. **Ngoài phạm vi:** chuyến không có booking (năm 2024, bán cước), giữ theo [`LEGACY-A`](legacy-a.md). Chuyến trước tháng đầu của sổ nằm trong số dư đầu kỳ, không cộng lại.

Phần cách làm của PR thứ nhất (Claude chọn, ĐỀ XUẤT):

- Lượt đối soát ([`MAY-DOI-SOAT-01`](may-doi-soat-01.md)) đã đọc `get_ledger` của mọi sổ. Phép so lấy chuyến từ chính lần đọc đó: chuyến web và dòng chuyến sổ gốc, bản hiện hành, chưa xóa, không bị từ chối. Không đọc DB thêm, không có timer mới.
- Ghép ngay trong lượt (vài giây, không đọc xlsx), sau khi đọc sổ xong. Ghi `booking-web.json` cạnh `booking-check.json`. Lỗi thành mã ở `last_error` và giữ kết quả lượt đạt trước; lỗi không làm đổ lượt.
- Biển hay bộ lấy theo `transport_mode` của sổ. Sổ chưa gán thì đoán theo tên, như phép kiểm Sheet. Dòng trang mang mã sổ web, nên trang mở đúng sổ mà không cần ghép tên.
- Số đầu dòng của khối là "X/Y chuyến booking đã có trên sổ web", trong đó Y không tính chuyến trước tháng đầu của sổ.
- Tab Máy chạy, khối "Kiểm sổ với booking" có nút chọn "Sổ web" (mặc định) và "Sheet sổ nợ". Ở phía sổ web, nhóm "Booking có, web chưa có" đứng đầu.

Phần cách làm của PR thứ hai (Claude chọn, ĐỀ XUẤT; người dùng bảo "Làm PR 2" ngày 25/11/2026):

- **Container dùng lại.** Dòng booking có container đã có trong cùng sổ, mà không dòng nào trong sổ cách nó quá 3 ngày, là **chuyến mới** khi booking có **nhiều dòng container đó hơn sổ**. Chỉ tính dòng booking của sổ đó, từ tháng đầu của sổ; dòng trước đó nằm trong số dư đầu kỳ. Một dòng booking là một chuyến. Đếm dòng, không so khoảng cách ngày, cùng lý do như [`CONTAINER-DUNG-LAI-01`](container-dung-lai-01.md): sổ có dòng ghi lệch ngày, sai năm. Luật này chỉ áp cho chuyến **từ tháng 10/2026**, đúng mốc máy tự đưa chuyến vào sổ ([`MAY-KHOA-01`](may-khoa-01.md)); tháng cũ theo (3). Luật tab của `CONTAINER-DUNG-LAI-01` vẫn giữ: có tab thì tab cũng quyết được, hết tab thì còn luật booking. Chuyến mới vẫn qua các chặn có sẵn (khách khác, sổ gốc của sổ khác, đúng mặt hàng, ngày không sau hôm nay), vào sổ chưa giá; `paste_trips` vẫn đẩy chuyến nghi trùng sang "chờ kiểm".
- **Chủ hàng chưa có sổ.** Cổng này đã gỡ bằng [`KHACH-WEB-01`](khach-web-01.md): thẻ Khách liệt kê chủ hàng booking chưa có sổ, quản lý tạo sổ hoặc gán tên trên web, lượt sau chuyến tự vào sổ mà không cần tab Sheet. Máy **không** tự tạo sổ chỉ từ booking. Lý do: tên chủ hàng có khi là tên khác của một khách đã có sổ, hoặc là kho đóng hàng cho nhiều khách; mặt hàng của sổ cũng phải có người chọn. Máy tạo sổ theo tab Sheet ([`MAY-TAO-SO-01`](may-tao-so-01.md)) vẫn chạy trong lúc song song.
- **Chuyến bộ ngoài phạm vi.** Hàng chờ `CONT_BO` vẫn xếp sổ theo tab khách, rồi theo chủ hàng ([`CHUYEN-BO-CHU-HANG-01`](chuyen-bo-chu-hang-01.md)). Phép so 24/11 không thấy chuyến bộ nào tháng mới bị thiếu.

Đo chỉ đọc trên `hao` 25/11/2026: chạy hàng chờ của cả 204 sổ đi biển bằng bản đang chạy và bằng bản mới, cùng dữ liệu. Chỉ **2 dòng** đổi trạng thái, ở cùng một sổ, tháng 11/2026, từ "chờ tab Sheet" sang "chuyến mới, đúng mặt hàng". Đó là 2 chuyến (1) tìm ra ngày 24/11. Booking ghi container thứ nhất 3 lần (tháng 4, 7, 11), container thứ hai 2 lần (tháng 7, 11); mỗi lần có số booking riêng và nơi đóng hàng khác. 17 dòng chờ còn lại đều trước 10/2026 và giữ nguyên. Không sổ nào thêm hay bớt dòng lệch.

## Ngày / nguồn

24/11/2026, chat. Người dùng: "hiện tại chúng ta đang mâu thuẫn, mình nghĩ tiêu chí đầu tiên của web phải là đủ chuyến từ sheet booking đã". Claude chỉ ra chỗ mâu thuẫn: [`NGUON-CHUYEN-01`](nguon-chuyen-01.md) đã chốt "chuyến theo booking", nhưng máy đối soát theo Sheet, chuyến dùng lại container và khách mới phải chờ tab Sheet, còn phép kiểm booking lại so Sheet chứ không so web. Claude đề xuất bốn điểm trên. Người dùng chọn "Chốt, đo trước", rồi chọn "Làm PR 1".

Đo chỉ đọc trên `hao` 24/11/2026, khoảng 15:00 VN: chuyến web từ DB `webdebit_v7` lấy trong giao dịch `READ ONLY`, cộng hai bản chụp của lượt 15:15. Ghép bằng `v7_trip_source_match`. Chỉ ghi số đếm; danh sách có tên khách giữ ngoài Git.

| | Sổ web ↔ booking | Sheet ↔ booking (lượt 15:05) |
| --- | ---: | ---: |
| Chuyến booking trong khoảng kiểm (biển từ 12/2025, bộ từ 08/2025), trừ chuyến trước tháng đầu của sổ | 7.692 | |
| Đã có trên sổ | 7.621 | |
| Trước tháng đầu của sổ (chỉ đếm) | 547 | 547 |
| Thiếu, tháng 11/2026 | 4 | 127 |
| Thiếu, tháng cũ | 47 | 48 |
| Nghi tính hai lần | 50 | 57 |
| Trên sổ, booking không có | 29 (đều là dòng sổ gốc trước 10/2026) | 30 |

Về 4 chuyến tháng 11 web chưa có:
- 2 chuyến chờ tab Sheet theo `CONTAINER-DUNG-LAI-01` (container đã dùng ở cùng sổ vài tháng trước);
- 1 chuyến có chủ hàng chưa có sổ web;
- 1 chuyến ngày hôm đó, lượt sau mới tới.

Về 47 chuyến tháng cũ:
- 21 chuyến: web có cùng container trong 45 ngày quanh đó;
- 7 chuyến: web có container ở dòng không ngày;
- 19 chuyến: container không có ở sổ nào.

`evaluate_web` chạy trên cùng dữ liệu cho đúng các số này.

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng (1)–(4). Cách làm PR thứ nhất là ĐỀ XUẤT. PR thứ nhất chỉ đọc: không ghi sổ, không ghi DB, không ghi Sheet, không đổi luật tiền, luật ghép hay điều kiện máy ghi.

Mã:
- `v7_booking_check.web_rows`, `evaluate_web`, `run_web_safely`;
- lời gọi trong `tools/v7_reconcile_auto.py`, sau `read_web`;
- `web_check` trong `GET /api/v7/machine/booking` (`web/v7_booking_view.py`);
- khối `preview/may-chay-booking.js`.

Tắt cùng công tắc của phép kiểm Sheet: `WEBDEBIT_BOOKING_CHECK=off`.

Giới hạn:
- Chuyến lấy lúc lượt bắt đầu đọc sổ. Sổ máy tạo hay chuyến máy dán trong lượt đó thì tới lượt sau mới tính.
- Số đo trên dùng chuyến từ tháng nợ 06/2025. Lượt thật đọc mọi tháng, nên tháng đầu của vài sổ có thể sớm hơn và số "trước tháng đầu của sổ" có thể khác chút ít.
- PR thứ hai chỉ đổi code app, không migration, không ghi Sheet, không đổi luật tiền: chuyến máy thêm chưa có giá, giá vẫn theo `MAY-GIA-01`.
- CÒN MỞ: chủ sổ kết luận 47 chuyến tháng cũ, 50 dòng nghi tính hai lần và 29 dòng không có booking; người dùng tự đi khối trên `hao`.
