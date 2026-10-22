# Sheet capture-only

Người dùng chốt build ngày 21/10/2026. Chỉ ghi nhận nguồn để đối chiếu sau,
không tự ghi sổ, không replay giao dịch vào opening/Webdebit.

## Hợp đồng hoàn thành

- Apps Script standalone, log ở spreadsheet riêng tư khác nguồn; không sửa ô nguồn.
- Edit -> `captureEdit` -> EDIT và dirty tab; thay đổi cấu trúc -> `captureChange`
  -> STRUCTURE không đoán tab, xếp lịch toàn file.
- `captureDrain` -> snapshot đầy đủ giá trị/công thức của một tab mỗi lượt;
  ghi khi hash thay đổi; chỉ xóa pending sau ghi thành công.
- `captureFullSweep` -> inventory và xếp lịch quét bù mỗi ngày.
- Nhóm payload có part/parts và COMPLETE; không có COMPLETE hoặc thiếu part thì
  không được coi là dữ liệu đầy đủ. Thời gian là lúc handler đọc, không chứng minh
  thời điểm nhập; actor có thể trống. Dòng baseline không là giao dịch mới.
- Không dùng số hàng/container làm khóa replay. Bản sau có thể đã gộp nhiều sửa;
  không hứa phục hồi mọi trạng thái trung gian hoặc every edit.
- Khi lỗi quota, quyền, khóa hoặc dung lượng: fail, giữ pending nếu đã đánh dấu;
  xem Executions/trigger failure email. Không đổi lỗi đọc thành xóa dữ liệu.
  Tab lỗi được đánh dấu `fail_<id>` và xếp sau các tab khác, nên một tab lỗi mãi
  (ví dụ vượt 250.000 ô) không chặn cả hàng đợi; chỉ thử lại khi hết tab khác.
- Ngưỡng dung lượng log tính theo số cột đã cấp của tab EVENTS (tab mới mặc định
  26 cột), không chỉ 11 cột header.
- Test: `node scripts/sheet-capture/test.js` (fake Google services); không chứng minh
  trigger Google thật. Phải thử bản sao trước: sửa một ô, dán lô, xóa/chèn hàng,
  xóa tab, ghi bằng API rồi quét bù, lỗi log và retry.

## Cài đặt (chỉ sau kiểm thử trên bản sao)

1. Tạo spreadsheet log riêng tư cùng tài khoản có quyền đọc nguồn. Không chia sẻ
   rộng hơn nguồn. Tạo standalone Apps Script tại script.google.com, dán `Code.gs`.
2. Project Settings -> Script Properties: `SOURCE_ID` là ID nguồn thử,
   `LOG_ID` là ID file log thử, hai ID bắt buộc khác nhau. Không đưa ID vào repo.
3. Chạy `captureInstall`, cấp quyền Google cho script. Scope Spreadsheet của Apps
   Script không tự giới hạn read-only; code không gọi mutation trên nguồn.
4. Chạy `captureDrain` để kiểm snapshot; thực hiện các ca thử phía trên và kiểm
   EVENTS, Executions. Lặp drain cho tới hết baseline. Đừng nhập mốc nghiệp vụ
   từ snapshot như một batch atomic: mỗi tab đọc tại thời điểm riêng.
5. Khi đạt, dùng log riêng cho nguồn thật, đổi SOURCE_ID/LOG_ID rồi install bằng
   đúng một tài khoản chủ trigger. Cài lại xóa cache hash/queue để lấy baseline mới,
   không xóa event nhưng thay trigger
   của tài khoản hiện tại; không cài nhiều tài khoản cùng project.
6. Dừng bằng `captureUninstall`; giữ nguyên log. Không tự xóa/compact lịch sử.

## Hermes

Không cần LLM/PC cho trigger hoặc lịch quét: Apps Script có timer Google sẵn.
Hermes có thể cron kiểm `LAST_DRAIN_OK_UTC`, pending và Executions sau khi có
đường đọc được xác thực; chưa dựng endpoint công khai hoặc chép token Hermes.
Chưa tạo Hermes cron. Không coi heartbeat là bằng chứng đã bắt đủ dữ liệu.

## Giới hạn và nghiệm thu

252 tab x 1 phút có thể mất hơn 4 giờ cho lượt baseline/quét bù; thay đổi mới
hiện dưới dạng EDIT, tab vừa được sửa ưu tiên trước tab chỉ quét bù.
Đọc tab không atomic với người đang sửa. Quét bù không bắt sửa rồi hoàn nguyên
giữa hai lần đọc. Thay đổi do API/script không kích hoạt edit trigger.
Snapshot giữ cả tab tổng hợp để không tự đoán cột nghiệp vụ; đây là capture thô,
không là đối soát tài chính. JSON giữ blank, zero và công thức; không tính tiền.
Log là spreadsheet thường có thể bị sửa/xóa, không phải audit bất biến.
Giới hạn 250.000 ô/tab, 20.000 ô/edit payload và 8 triệu ô log; vượt thì cần
chia vùng/tăng thông lượng hoặc archive có kiểm chứng. Apps Script quota có thể
khiến quét chậm hơn. Theo dõi lỗi và dung lượng, không tự xóa bằng chứng.

## Bằng chứng ngày 21/10/2026

- `npm run check` trong worktree trên nền `3f858f7`: exit 0; lint, Python,
  JS (gồm self-check capture), browser và viewer đạt. Dùng junction tới dependency
  repo đang có: không phải kiểm cài mới hoặc CI.
- Google thật, dữ liệu giả: dán A1:C3 -> EDIT + SNAPSHOT; sửa B2 từ 0 sang
  123456 có old/event value; thêm/xóa tab -> INSERT_GRID/REMOVE_GRID với
  affected_tab null, TAB_MISSING sau đó. Log giữ blank và zero riêng.
- Ghi C3 bằng Sheets API: không có EDIT; gọi full sweep, timer drain ghi snapshot
  có giá trị mới. Không suy ra bắt được sửa rồi hoàn nguyên giữa hai lần quét.
- Người dùng tự cấp quyền Google. Cài nguồn thật hoàn tất lúc 16:26:49 giờ VN;
  INSTALL có captured_at 09:26:42.292Z; timer ghi snapshot thật đầu tiên lúc
  09:27:31.818Z (16:27:31 giờ VN). Source không bị sửa ô để thử trigger.
- Log thật tách log thử, permissions đọc lại chỉ có owner. Chi tiết ID/URL nằm
  trong cấu hình Google và hồ sơ cục bộ ngoài Git; không chép raw vào repo.
- Baseline đang quét dần, chưa chứng minh đủ 252 tab; event thật của người dùng
  chưa được xác nhận trong lượt này. Có trigger không chứng minh bắt đủ mọi sửa.
- Chưa đồng bộ Webdebit, chưa tạo Hermes cron. Không dùng snapshot để tự replay tiền.

## Review ngày 22/10/2026 (Claude)

Bản cài trên Google ngày 21/10 là bản trước review. Sửa trong PR này:

- `captureDrain`: tab đọc lỗi trước đây luôn được chọn lại (nếu là tab ưu tiên
  hoặc đứng đầu danh sách), khiến mọi tab khác ngừng được chụp. Nay tab lỗi xếp
  sau, `fail_<id>` xóa khi chụp thành công, `captureInstall` xóa cả `fail_`.
- `captureAppend`: ngưỡng dung lượng tính theo `getMaxColumns()` của tab EVENTS.

Kiểm: `node scripts/sheet-capture/test.js` (case mới fail trên bản 21/10, pass trên
bản này) và `npm run check`. Chưa thử trên Google thật. Muốn bản sửa có hiệu lực:
dán `Code.gs` mới vào project, chạy lại các ca thử trên bản sao như mục Hợp đồng,
rồi mới thay cho bản đang chạy trên nguồn thật. Dán code không cần cài lại trigger;
`captureInstall` lại sẽ xóa hash và lấy baseline mới.

Còn mở, chưa sửa:

- Edit trigger chờ khóa tối đa 25 giây; nếu `captureDrain` đang giữ khóa lâu hơn
  (tab lớn), EDIT đó lỗi và tab không được đánh dấu, chỉ được quét bù ở lượt quét
  hằng ngày. Hiện ra ở Executions/trigger failure email.
- `setValues` để Sheets tự đổi chuỗi trông như số/ngày ở cột thường (ví dụ tên tab
  chỉ gồm chữ số); `sheet_id` và payload JSON vẫn giữ đúng giá trị.
- Snapshot chỉ là bản chụp thô. Chưa có công cụ so snapshot với bản mốc để tìm
  dòng cũ bị sửa (CÒN MỞ của `SONG-SONG-02`).
