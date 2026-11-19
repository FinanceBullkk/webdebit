# Khách mới: để ý thu sớm (KHACH-MOI-01)

Trạng thái: ĐỀ XUẤT (Claude, 19/11/2026). Mốc ngày lấy từ phép đo chỉ đọc trên `hao` ở mục Số đo. Chưa code, chưa có quyết định trong `docs/decisions.md`; khi người dùng chốt thì ghi `docs/decisions/khach-moi-01.md`.

## Vấn đề

Người dùng hỏi ngày 19/11/2026: khách mới sẽ có thêm, có cách nào cảnh báo để ý thu sớm không.

Luật hạn trả hiện tại ([`DASH-03`](../docs/decisions/dash-03.md) mục 1) cho nợ tháng M đến hạn vào cuối tháng M+1. Khách mới chạy chuyến đầu vào đầu tháng thì gần 60 ngày sau mới quá hạn. Suốt thời gian đó Tổng quan xếp khách vào "Không quá hạn", dù khách chưa trả đồng nào. Bảng khách cũng không cho biết khách nào mới bắt đầu, chưa có lịch sử trả.

## Số đo (chỉ đọc trên `hao`, 19/11/2026)

**Cách đo.** Đọc chuyến và lần trả của 242 sổ đang hoạt động, gồm dòng sổ gốc (`legacy_row`, ngày đọc như `get_dashboard_debt`) và chuyến, phiếu web. Dòng không có ngày lấy cuối tháng của dòng. Tiền chuyến là thành tiền sổ gốc hoặc giá mới nhất trên web; chuyến chưa có giá không tính. Ngày bắt đầu của sổ là ngày chuyến đầu tiên. Sổ có lần trả sớm hơn chuyến đầu quá 7 ngày bị bỏ (6 sổ), vì đó là dấu hiệu sổ có lịch sử trước đó. Kết quả là 209 sổ mới bắt đầu từ 01/2025, trong đó 165 sổ đã đủ 180 ngày để biết kết cục.

Sổ gốc giữ cả lịch sử đã trả: chuyến năm 2024 của các sổ cũ còn đủ trên tab, phần lớn đã trả xong. Vì vậy ngày chuyến đầu trên sổ đúng là ngày sổ bắt đầu, không phải ngày tab bị cắt bớt.

**"Kẹt"** = tới ngày thứ 180, khách trả chưa được 75% tiền chuyến của 90 ngày đầu. Có 12/165 sổ kẹt (7%), nhưng 12 sổ này giữ **72%** số tiền 90 ngày đầu còn chưa trả của cả nhóm. Ba sổ lớn nhất trong số đó giữ 55% phần ấy.

**Phần lớn khách mới trả nhanh, nhanh hơn khách lâu năm:**

| Tuổi sổ lúc chạy chuyến | Số ngày tới khi chuyến được trả đủ (theo nợ cũ trước): trung vị | p75 | p90 |
|---|---|---|---|
| 0–3 tháng | 32 | 48 | 68 |
| 3–6 tháng | 27 | 40 | 67 |
| 6–12 tháng | 47 | 92 | 152 |
| trên 12 tháng | 67 | 105 | 162 |

Chuyến trong 90 ngày đầu của sổ mới: 46% được trả đủ trong 30 ngày, 88% trong 60 ngày, 96% trong 90 ngày. Một chuyến của khách mới còn nợ sau 45 ngày là bất thường so với chính nhóm này.

**Luật hiện tại có bắt được nhưng muộn.** Cả 12 sổ kẹt đều có lúc quá hạn theo `DASH-03`: trung vị ở ngày 52 kể từ chuyến đầu. Chúng lên Rủi ro cao ở trung vị ngày 65.

**So các tín hiệu sớm trên 165 sổ đã đủ tuổi (xét trong 90 ngày đầu):**

| Tín hiệu | Sổ bị gắn | Bắt được sổ kẹt | Tỷ lệ trúng | Ngày gắn của sổ kẹt (trung vị) |
|---|---|---|---|---|
| S1: đủ 30 ngày từ chuyến đầu mà chưa trả lần nào | 60 | 7/12 | 12% | 30 |
| S2: có chuyến quá 45 ngày chưa trả đủ | 72 | 12/12 | 17% | 50 |
| S1 hoặc S2 | 86 | 12/12 | 14% | 30 |
| (đối chiếu) Quá hạn theo `DASH-03` | — | 12/12 | — | 52 |

Gộp S1 với S2 thì bắt đủ 12/12 sổ kẹt, sớm hơn luật hiện tại khoảng ba tuần. Đổi lại, khoảng 6/7 sổ bị gắn cuối cùng vẫn trả. Vì thế cảnh báo phải là **để ý / nhắc sớm**, không phải nhãn đỏ. Tính tại một thời điểm thì lượng việc nhỏ: hôm 19/11/2026 có 24 sổ chạy chuyến đầu trong 120 ngày qua, và 6 sổ trong đó dính S1 hoặc S2.

**Tín hiệu đã thử nhưng không dùng:** cỡ tiền 30 ngày đầu (ba nhóm bằng nhau có 5, 5, 2 sổ kẹt) và số chuyến 30 ngày đầu (sổ chạy từ 16 chuyến trở lên không có sổ kẹt nào, nhưng nhóm nhỏ). Mặt hàng dừa có 5/12 sổ kẹt trên 12 sổ dừa, cao bất thường. Một sổ dừa lớn có nhiều dòng phí lẻ không ngày nên phải kiểm lại trước khi dùng. Chưa dùng mặt hàng làm luật.

**Giới hạn của phép đo.** Một sổ không chắc là một khách: sổ tách từ khách cũ hoặc sổ mặt hàng mới của khách cũ cũng hiện như sổ mới ([`TRANG-KHACH-01`](../docs/decisions/trang-khach-01.md) K1, không đoán theo tên). 29% tiền sổ gốc không có ngày được đặt ở cuối tháng. Đây là tương quan; chưa có nhật ký lần đòi nên chưa biết nhắc sớm có làm khách trả nhanh hơn không. Số tuyệt đối đổi theo ngày nên đo lại trước khi chốt.

## Người dùng và luồng

- **Người dùng:** người theo dõi công nợ và sếp. Họ mở Tổng quan mỗi ngày, trên màn 1280×720 ở Windows 150% và trên iPhone ([`DIEN-THOAI-SEP-01`](../docs/decisions/dien-thoai-sep-01.md)).
- **Luồng:**
  1. Mở Tổng quan. Khách mới có nhãn **Mới** cạnh tên ở bảng khách.
  2. Có ô bấm **"Khách mới cần để ý · n"**. Bấm vào thì bảng khách chỉ còn các sổ mới dính S1 hoặc S2. Mỗi dòng có một câu dữ kiện: "Chưa trả lần nào · chuyến đầu 34 ngày trước" hoặc "Chuyến 02/10 chưa trả · 48 ngày".
  3. Bấm tên khách mở trang khách, thẻ Tình hình (như hiện nay). Thẻ có thêm một dòng: "Khách mới: chuyến đầu dd/mm/yyyy, chưa trả lần nào" hoặc "…, lần trả đầu dd/mm".
  4. Người dùng tự liên hệ khách. Web không gửi tin, không chặn ghi chuyến, không đổi số tiền.
- **Kết quả:** trong 90 ngày đầu của một sổ, người dùng thấy khách đang chậm khoảng ba tuần sớm hơn luật quá hạn hiện tại.
- **Không chặn gì:** như mức rủi ro của `DASH-03`, nhãn chỉ để tô màu và lọc.

## Hành vi

1. **Sổ mới:** sổ không lưu trữ, có chuyến đầu cách hôm nay (giờ VN) **≤ 90 ngày**, và không có lần trả nào sớm hơn chuyến đầu quá 7 ngày.
   - Chuyến đầu là ngày sớm nhất trong các chuyến web chưa xóa, không bị loại, và các dòng chuyến sổ gốc chưa xóa. Dòng không ngày lấy cuối tháng của dòng, theo cùng luật `trip_last` của `get_dashboard_debt`, chỉ đổi lấy muộn nhất thành lấy sớm nhất.
   - Mốc 90 ngày: S2 bắt đủ 12/12 sổ kẹt trước ngày 90, và tới 3–6 tháng khách vẫn trả nhanh như lúc mới.
2. **Lần trả** giống `pay_last` của `get_dashboard_debt`: phiếu chưa hủy (kể cả cấn trừ) và dòng thu sổ gốc khác 0, chưa xóa.
3. **S1 · Chưa trả lần nào:** sổ mới, đã đủ **30 ngày** từ chuyến đầu, chưa có lần trả nào từ 7 ngày trước chuyến đầu tới hôm nay.
4. **S2 · Chuyến chậm trả:** sổ mới có chuyến cũ nhất còn chưa trả đủ đã quá **45 ngày**. Tiền trả xếp vào chuyến theo nợ cũ trước, theo ngày chuyến.
   - Tiền chuyến sổ gốc lấy thành tiền sổ gốc. Ở đây chỉ dùng để xếp thứ tự, không cộng vào số nào: không phá quy tắc "`legacy_row` không tham gia công thức tiền".
   - Chuyến chưa có giá không tính là chưa trả.
5. Sổ dính cả S1 và S2 thì câu hiện S1.
6. Sau 90 ngày, nhãn **Mới** và S1, S2 tự hết. Sổ từ đó theo luật thường.
7. Hai tín hiệu **không đổi** nhóm hạn trả, mức rủi ro hay nhóm tình trạng của `DASH-03`, `DASH-05`, `DASH-06`, và không đổi tiền, phân bổ, khóa tháng hay quyền.
8. Ô "Khách mới cần để ý" là một chiều lọc theo [`DASH-08`](../docs/decisions/dash-08.md): các khối khác tính lại theo lọc này, còn ô tự nó vẫn hiện đủ số. Không có sổ nào thì ô hiện "0" và không bấm được.

## Đối chiếu dữ liệu và code hiện có

- `get_dashboard_debt` đã có đủ nguyên liệu: lần trả, chuyến web, dòng sổ gốc, sổ đang nợ (`debtor`). Hàm chỉ trả về sổ đang nợ. Khách mới đã trả hết thì không cần cảnh báo, nên không thiếu gì.
- Khối `rule` đã có các mốc (`no_pay_days`, `active_trip_days`…). Thêm `new_days: 90`, `new_no_pay_days: 30`, `new_unpaid_days: 45` vào đó để frontend không tự chép số.
- Bảng khách và chip ở `preview/dashboard-v7.js` và `dashboard-v7-model.js` đang dùng ba chip rủi ro của `DASH-05`; `DASH-06` (ô tình trạng) chưa code. Ô "Khách mới cần để ý" nằm cạnh hàng chip, đi theo hàng ô khi `DASH-06` được code.
- Thẻ Tình hình đã đọc `dashboard/debt` (`so-khach-v7-api.js`, [spec trang khách](v7-trang-khach.md)), nên dòng "Khách mới" dùng chính các trường mới dưới đây, không cần API mới. Sổ không còn nợ không có trong `dashboard/debt`, nên không hiện dòng; chấp nhận được vì đã trả hết.

## Giao tiếp frontend–backend

Mỗi khách trong `customers` của `get_dashboard_debt` có thêm:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `first_trip_day` | `date` hoặc `null` | ngày chuyến đầu theo Hành vi 1 |
| `first_trip_exact` | `bool` | `false` khi lấy cuối tháng của dòng không ngày |
| `is_new` | `bool` | theo Hành vi 1 |
| `new_flag` | `"no_pay"`, `"slow"` hoặc `null` | S1, S2 (S1 trước); `null` khi không mới |
| `oldest_unpaid_trip_day` | `date` hoặc `null` | chuyến cũ nhất còn chưa trả đủ, chỉ khi `is_new` |

Thay đổi chỉ nằm trong hàm đọc (`CREATE OR REPLACE`, migration riêng), không đổi bảng, view, hàm ghi hay quyền. Triển khai tay theo [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md). Frontend chạy trên DB cũ (thiếu trường) thì không hiện nhãn và ô, không báo lỗi.

## Nguồn quyết định

- [`DASH-03`](../docs/decisions/dash-03.md): hạn trả, cách tính lần trả và đi hàng. Giữ nguyên.
- [`DASH-06`](../docs/decisions/dash-06.md): Tổng quan cho C-level, màn chỉ ghi dữ kiện. Câu ở mỗi dòng là dữ kiện, không gợi ý việc.
- [`DASH-08`](../docs/decisions/dash-08.md): lọc chéo.
- [`MAY-TAO-SO-01`](../docs/decisions/may-tao-so-01.md): khách mới vào web bằng sổ máy tự tạo.
- CÒN MỞ, cần người dùng chốt: (a) ba mốc 90 / 30 / 45 ngày; (b) chỗ hiện: ô lọc ở Tổng quan và dòng ở Tình hình, hay thêm nơi khác; (c) có cần nút "Không phải khách mới" cho sổ tách từ khách cũ không. Phương án đề xuất là chưa làm nút, chờ xem có sổ nào bị gắn nhầm. Nút này cần bảng ngoài đường tiền như `contact_mark`.

## Tiêu chí nghiệm thu

- [ ] Harness PostgreSQL: sổ chuyến đầu 89 và 91 ngày (ranh giới `is_new`); đủ 29 và 30 ngày chưa trả (S1); chuyến chưa trả 45 và 46 ngày (S2); trả một phần làm chuyến cũ nhất đổi; dòng sổ gốc không ngày; phiếu đã hủy không tính là đã trả; phiếu trả trước chuyến đầu quá 7 ngày thì không phải sổ mới; giờ VN qua nửa đêm.
- [ ] Tổng tiền, nhóm hạn trả và mức rủi ro của `get_dashboard_debt` không đổi trước và sau migration trên bản sao DB (so JSON trừ các trường mới).
- [ ] Unit JS: model gắn nhãn, câu dữ kiện và lọc chéo; DB cũ thiếu trường thì không hiện gì.
- [ ] Trình duyệt 1280×720 và 390px: nhãn không làm bảng tràn ngang; ô bấm được bằng bàn phím; ô bằng 0 không bấm được.
- [ ] `npm run check` xanh.
- [ ] Người dùng tự mở Tổng quan trên `hao`, bấm ô, thấy đúng các sổ mới và xác nhận.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`)
- Review: opus (đọc đường tiền, dù không ghi)
- Được sửa (PR backend): `cong-no-web-handoff/tools/migrations/<ngày>-v7-khach-moi.sql`, `cong-no-web-handoff/tools/v7_backend_functions.sql`, `cong-no-web-handoff/tools/test_pg_v7_backend*.py`, `docs/v7-deploy-runbook.md`, `docs/deploys/`
- Được sửa (PR frontend): `cong-no-web-handoff/preview/dashboard-v7*.js`, `cong-no-web-handoff/preview/so-khach-v7*.js` (dòng ở Tình hình), test tương ứng
- Ngân sách diff: khoảng 300 dòng mỗi PR
