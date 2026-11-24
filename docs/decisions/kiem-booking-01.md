# KIEM-BOOKING-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ba điểm cho phép kiểm "Sheet sổ nợ so với booking", lưới an toàn thay "khớp Sheet" khi chuyển hẳn (mục A6, F5 của [checklist chuyển hẳn](../chuyen-han-checklist.md)):

1. **Chỗ hiện:** một khối trong tab Máy chạy, dưới bảng "Các job trên máy chủ". Không phải trang riêng, không phải cột ở Việc cần làm.
2. **Nhịp:** mỗi giờ, trong chính lượt đối soát máy ([`MAY-DOI-SOAT-01`](may-doi-soat-01.md), :05 từ 7 tới 22 giờ), trên cùng bản tải sổ gốc. Không tải Sheet thêm, không có timer mới.
3. **Phạm vi:** theo hai bản chụp nguồn đang có trên `hao`: `CONT_NGUON` (chuyến biển) và `CONT_BO` (chuyến bộ). Chưa làm bản chụp booking 2025 (GĐ2 của [spec](../../specs/v7-chuyen-theo-nguon.md)).

Claude chọn phần cách làm (ĐỀ XUẤT, áp dụng trong phạm vi trên):

- **Luật ghép và phân nhóm:** đúng công cụ GĐ1 `v7_trip_source_match` ([`NGUON-CHUYEN-01`](nguon-chuyen-01.md) (1)).
- **Khoảng kiểm:** chuyến biển từ 12/2025, chuyến bộ từ 08/2025, theo số đo dưới đây. Trước các tháng đó không báo "không có booking" hay "booking có, sổ chưa tính".
- **Bảy nhóm trên trang**, theo thứ tự chủ sổ hỏi.
  - Bốn nhóm đụng tiền:
    - nghi tính hai lần (cùng ngày, lệch 1–3 ngày, đảo ngày/tháng);
    - booking có, sổ chưa tính (kể cả chủ hàng chưa ứng sổ nào);
    - sổ khác khách booking, chỉ chuyến biển: chuyến bộ lấy khách theo sổ, theo `NGUON-CHUYEN-01` (2);
    - trên sổ, booking không có.
  - Ba nhóm chỉ để biết: lệch ngày, sổ thiếu ngày, chuyến tháng này chưa lên sổ.
- **Chỉ đếm, không lên trang:**
  - chuyến trước tháng đầu của tab khách: nằm trong số dư đầu kỳ, không cộng lại (`AGENTS.md`);
  - "giá khác booking": bản chụp `CONT_NGUON` không mang cột giá chữ nên không tính được.
- **Chạy ở tiến trình con song song với lượt đối soát:** lượt không dài thêm, và lỗi của phép kiểm không làm đổ lượt.
- **Khi không tin được số:** không kiểm, giữ kết quả lượt đạt trước và thêm `last_error`. Các trường hợp:
  - bản chụp nguồn thiếu, hỏng, rỗng, hoặc cũ quá 3 giờ;
  - không dòng sổ nào nằm trong khoảng kiểm;
  - lượt đối soát lỗi giữa chừng (`RUN_FAILED`);
  - phép kiểm chạy quá 15 phút tính từ lúc bắt đầu.

  API báo `stale` khi lượt đạt gần nhất cũ hơn lượt liền trước lượt theo lịch gần nhất. Trang chỉ ghi "không thấy chuyến nào…" khi lượt mới nhất đạt và còn mới.
- **Khác công cụ GĐ1 ở một điểm:** hai dòng cùng container, cùng ngày trong một bản chụp tính là một chuyến (công cụ GĐ1 giữ cả hai). Booking ghi lặp một chuyến thì không che mất dòng sổ tính hai lần.

### Lọc nhiễu khi ghép (16/11/2026)

16/11/2026, chat: người dùng hỏi "có thể xử lý những cái này không" với bốn nhóm đụng tiền, rồi chọn "Làm phần máy lọc". Claude chọn các luật dưới đây (ĐỀ XUẤT). Không luật nào đổi tiền hay điều kiện máy ghi; chúng chỉ đổi cách ghép và cách phân nhóm của công cụ GĐ1, nên phép kiểm và báo cáo tháng đổi theo.

- **Chuyến bộ ghép theo cả ô "Số xe":** Sheet có lúc ghi biển số ở chỗ của container (một tab đường bộ), và `CONT_BO` có dòng đổi chỗ hai ô. Chỉ ghép khi đúng một chuyến hợp (±3 ngày, hoặc cùng tháng nợ với dòng không ngày), vì một xe chạy nhiều chuyến trong tháng.
- **Ô container không phải số container hay biển số** (`THUE`, `VAT`, `PHIKIEMDICHN`, `50`, ô trống sau khi bỏ dấu) là dòng phí, không phải chuyến. Những dòng này không lên nhóm "Trên sổ, booking không có", chỉ được đếm ở `hidden.KHONG_PHAI_CONT`. Số container gõ thừa một ký tự (dạng `MAUU12345670`, tám số) vẫn tính là chuyến.
- **Chủ hàng ghi ngay trong tên tab thì không là "khách khác".** Ví dụ: một tab mang tên chủ hàng A kèm mặt hàng, chủ yếu chở cho chủ hàng B nhưng cũng có chuyến của A.
- **Hòa khoảng cách thì ưu tiên dòng mang tiền rồi dòng nằm đúng khối tháng của chuyến.** Dòng thừa ra mới là dòng cần hỏi.
- **Dòng có ngày nằm ngoài khối tháng của nó, trong khi khối đó có một chuyến booking chưa dòng nào ghép:** ngày bị gõ nhầm, nên dòng này là chuyến đó, không phải tính hai lần. Kết quả hiện ở nhóm lệch ngày, ghi chú "ghi nhầm ngày?".
- **Dòng 0đ đã giữ chuyến (±3 ngày):** dòng mang tiền của chuyến đó thành lệch ngày, không thành nghi tính hai lần. Luật này chỉ áp khi dòng mang tiền là dòng chưa ghép duy nhất của container có tiền. Kiểu đảo ngày/tháng vẫn để người xem. Trong báo cáo tháng, dòng mang tiền là chuyến (`lech_ngay`), dòng 0đ là `chep`.

Đo trên bản tải và hai bản chụp lúc 17:00 ngày 16/11/2026, chạy ở máy dev:

| Nhóm | Trước | Sau |
| --- | ---: | ---: |
| Nghi tính hai lần | 62 | 56 |
| Booking có, sổ chưa tính | 111 | 106 |
| Sổ khác khách booking | 23 | 13 |
| Trên sổ, booking không có | 45 | 30 |
| Lệch ngày / sổ thiếu ngày | 69 / 240 | 71 / 243 |

11 dòng phí chuyển sang chỉ đếm. Còn lại để người dùng trả lời: hai cặp tab chép của nhau, và một cặp tên chưa rõ là một hay hai khách.

### Nhóm "tháng này" tách theo sổ web (24/11/2026)

24/11/2026, chat. Người dùng hỏi vì sao máy chưa xử lý các dòng "Tháng này chưa lên sổ". Đo chỉ đọc trên `hao` (lượt 08:05): 119/122 dòng máy đã đưa vào sổ web, đúng sổ, đúng ngày. Phép kiểm so tab khách trên Sheet, nên các dòng này vẫn hiện tới khi Sheet ghi. 3 dòng còn lại máy cố ý giữ: 2 dòng container dùng lại mà tab chưa có dòng riêng (`CONTAINER-DUNG-LAI-01`), 1 dòng chủ hàng chưa có sổ web. Người dùng chọn "Sửa ở đây".

Khi trang đọc kết quả, API gắn chuyến web cho mỗi dòng `THANG_CUOI`: cùng container, lệch không quá 3 ngày, sổ nào cũng được. Hàm đọc là `get_trip_month`, dùng chung bộ nhớ đọc với Báo cáo tháng. Một chuyến web chỉ ghép một dòng. Chuyến "chờ kiểm" tính là đã có. Nhóm tách hai:

- **"Tháng này, web chưa có"**: dòng cần xem. Mỗi dòng có link "xem lý do" sang danh sách web chưa có của Báo cáo tháng (BAO-CAO-THANG-02), nơi nêu lý do máy giữ.
- **"Web có, Sheet chưa ghi"**: link mở sổ web. Chuyến chưa có giá cho tới khi Sheet ghi (`MAY-GIA-01`).

Đọc sổ web lỗi thì giữ một nhóm như cũ. File job và cách job phân nhóm không đổi. ĐỀ XUẤT của Claude trong phạm vi "sửa ở đây". Không đổi luật tiền.

### Lọc nhiễu lần hai, dòng booking cần sửa (24/11/2026)

24/11/2026, chat: người dùng giao "xem hết 106 chuyến booking có mà Sheet không tính, và dọn 228 dòng booking lỗi", một mục trong danh sách việc để bỏ được Sheet sổ nợ. Claude rà từng chuyến trên lượt kiểm 08:05 cùng ngày (chỉ đọc; danh sách có tên khách giữ ngoài Git), rồi hỏi ai sửa dòng booking lỗi. Người dùng chọn **"Web liệt kê, người giữ booking sửa"**: dòng lỗi hiện ở khối này, Claude không ghi file booking.

Ba luật dưới đây là ĐỀ XUẤT của Claude. Như lần 16/11, chúng chỉ đổi cách ghép và phân nhóm của phép kiểm và báo cáo tháng, không đổi tiền hay điều kiện máy ghi.

- **Dòng sổ không ngày ghép được chuyến nửa cuối tháng trước.** Sheet ghi chuyến cuối tháng vào đầu khối tháng sau mà không ghi ngày. Nay dòng không ngày của khối tháng M ghép được chuyến booking từ ngày 16 của tháng M−1 (`LATE_DAY` trong công cụ GĐ1). Bậc này xét sau mọi cặp cùng tháng, nên chuyến cùng tháng vẫn thắng. Đo lượt 08:05: 57/106 chuyến "booking có, sổ chưa tính" là chuyến ngày 20–31/5, nằm không ngày ở khối tháng 6 của chính tab gợi ý (hai sổ đường bộ, một sổ biển). Cặp này hiện ở nhóm "Sổ thiếu ngày", ghi chú "ghi ở khối tháng sau".
- **Dòng booking không phải chuyến không còn đếm là lỗi** (`dong_khong_phai_chuyen`): ô container trống, hoặc không phải số container hay biển số. Đo: 190 dòng `CONT_NGUON`, là dòng cuối của từng tab tháng (container trống, ngày năm 1900) và dòng tiêu đề mặt hàng nằm ở cột container.
- **Chuyến thật thiếu ngày thành nhóm "Booking thiếu ngày"** (`dong_thieu_ngay`): có số container mà ô ngày trống, không đọc được hoặc trước năm 2000. Nhóm nằm ở hàng không đổi tiền, liệt kê container, ô ngày, tab nguồn và dòng nguồn, booking hoặc số xe, chủ hàng. Với chuyến biển, tab nguồn là tab tháng của file booking mà `CONT_NGUON` chép từ đó. Đo: 23 dòng biển, 14 dòng bộ. Số "228 dòng lỗi" trước đây là tổng của loại này và loại trên.
- **Chuyến "booking có, sổ chưa tính" kèm số đếm:** số chuyến booking và số dòng sổ (mọi tab) của cùng container trong 45 ngày quanh đó. Sổ có dòng mà ít hơn booking thì có thể sót một chuyến, hoặc booking ghi lặp. Sổ không có dòng nào thì chuyến chưa ở sổ nào. Chỉ là chữ giải thích, không đổi nhóm.

KẾT_QUẢ_ĐO

## Ngày / nguồn

13/11/2026, chat. Phiên điều phối giao việc A6/F5. Claude viết bài toán của màn (chủ sổ hỏi gì, theo thứ tự) rồi hỏi bằng ba câu chọn. Người dùng chọn:
- "Khối trong Máy chạy" (Claude đề xuất trang riêng);
- "Mỗi giờ, cùng lượt đối soát";
- "Theo hai bản chụp đang có".

Số đo chỉ đọc trên `hao` cùng ngày (bản tải 13/11, release `2cbbe02`):

- **Bản chụp:**
  - `CONT_NGUON`: 5.726 dòng. Tháng 11/2025 mới có 87 chuyến; từ 12/2025 mỗi tháng có 349–704. 175 dòng mang ngày năm 1899–1902 (ô rác).
  - `CONT_BO`: 2.719 dòng, từ 08/2025 (tháng 07/2025 chỉ có 2 chuyến).
- **Một lượt:**
  - 7.308/7.641 dòng chuyến trong khoảng kiểm khớp booking.
  - Nhóm đụng tiền: nghi tính hai lần 62 dòng, booking có mà sổ chưa tính 115, sổ khác khách booking 23, trên sổ mà booking không có 45.
  - Nhóm để biết: lệch ngày 67, sổ thiếu ngày 231, tháng này 125.
  - 550 chuyến trước tháng đầu của tab khách (toàn bộ 08–12/2025) chỉ đếm.
- **Chi phí:** 252 giây, bộ nhớ đỉnh 286 MB, chạy song song nên lượt không dài thêm. Đọc xlsx một lần cho cả tab TONG và tab khách thì còn 160 giây; bản đầu (PR FinanceBullkk/webdebit#428) làm vậy bằng cách đổi `v7_load_real_copy.tong_commodities`, nhưng cổng `Deploy hao` chặn mọi diff có loader `v7_load*`, nên đã trả file loader về như cũ.

## Hiệu lực và giới hạn

ĐÃ CHỐT ba điểm của người dùng. Phần cách làm là ĐỀ XUẤT. ĐÃ TRIỂN KHAI trên `hao` 16/11/2026, lượt theo lịch đầu tiên 10:05 đạt ([nhật ký](../deploys/2026-11-16-kiem-booking.md)). Chỉ đọc: không ghi sổ, không ghi DB, không ghi Sheet. Không đổi luật tiền, luật ghép hay điều kiện máy ghi.

Mã:
- job `tools/v7_booking_check.py`, gọi từ `tools/v7_reconcile_auto.py`;
- API `GET /api/v7/machine/booking` (`web/v7_booking_view.py`), sau xác thực danh tính;
- khối `preview/may-chay-booking.js`.

File `booking-check.json` (mode 600) có tên tab khách và số tiền, chỉ nằm trên `hao`. Stdout, journal và `reconcile-log.jsonl` chỉ có số đếm. Tắt nhanh: `WEBDEBIT_BOOKING_CHECK=off` trong env của unit đối soát.

Giới hạn:
- Chưa có nút xử lý. ĐỀ XUẤT cho bước sau: "Đã xem" hoặc "Giữ" theo từng dòng, để dòng đã kết luận không hiện lại mỗi giờ. Việc này cần nơi lưu và đường ghi riêng, nên chưa làm.
- Sửa ở đâu: Sheet sổ nợ vẫn là sổ chính thức ([`SONG-SONG-01`](song-song-01.md)), nên chỗ sai sửa trên Sheet; lượt sau tự cập nhật.
- Trang ghép tên tab với sổ web theo tên để có link mở sổ. Tab chưa có sổ web, hoặc hai sổ trùng tên, thì không có link.
- Ngày trong bản chụp chỉ đọc được dạng `dd/mm/yyyy` (bộ đọc của connector). Dòng booking ghi kiểu khác bị bỏ, và dòng sổ cùng chuyến có thể ra "booking không có". Đo 13/11/2026: 35 dòng `CONT_NGUON` và 14 dòng `CONT_BO` có container mà không có ngày đọc được.
- Ô tiền trống và 0 đều hiện "—": công cụ GĐ1 đã gộp tiền trống thành 0 khi đọc sổ.
- Một dòng sổ có thể nằm ở hai nhóm (ví dụ vừa nghi tính hai lần vừa không có booking), nên cộng số trên các nút có thể lớn hơn số dòng.
- Trước 12/2025 (biển) và 08/2025 (bộ) chưa kiểm. Mở rộng cần bản chụp booking 2025.
- Khi chuyển hẳn khỏi Sheet, phép kiểm phải đổi sang so sổ web với booking. Mã ghép dùng lại được, nhưng đầu vào là sổ web thay cho xlsx.
- CÒN MỞ: người dùng tự đi hết khối trên `hao`.
