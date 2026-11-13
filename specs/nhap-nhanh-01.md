# Sổ khách: gõ xong hiện ngay như Sheet, ghi nền (NHAP-NHANH-01)

ĐỀ XUẤT của Claude theo yêu cầu người dùng ngày 13/11/2026: sổ khách đang chậm sau khi nhập hoặc xóa, người dùng muốn vùng này giống Sheet.

## Số đo trước khi làm

Đo trên `hao` ngày 13/11/2026, bản `1c2d1a2`, sổ LINSHUN (155) có 31 hàng bảng:

- `GET /api/v7/ledger`: khoảng 1,8 giây mỗi lần (đo 4 lần liên tiếp), 490 KB.
- Dựng lại `#app`: khoảng 20 ms.

Ngày nay, mỗi lần sửa một ô thì web gửi lệnh ghi, **đọc lại cả sổ**, vẽ lại cả trang, rồi ô mới hiện số. Lượt đọc ngay sau một lệnh ghi không dùng được bộ nhớ đọc của HIEU-NANG-01, vì dấu dữ liệu đã đổi. Gõ thêm một ô trong lúc chờ thì bị chặn với câu "Còn thao tác chưa rõ kết quả".

## Luồng người dùng

1. Người nhập sửa một ô rồi nhấn Enter, nhấn Tab hoặc bấm ra ngoài. Các ô áp dụng: chữ, ngày, Đơn giá, ô phụ phí cột riêng.
2. Ô hiện ngay giá trị mới. Thành tiền của dòng đó tạm hiện "…" (đang lưu). Tiêu điểm đi tiếp như hôm nay, và người nhập gõ tiếp được ngay.
3. Các lệnh ghi đi lần lượt ở nền, mỗi lệnh dùng số phiên bản mà lệnh trước trả về. Đầu sổ hiện dòng "Đang lưu…".
4. Khi mọi lệnh đã ghi xong, web đọc lại sổ **một lần**. Thành tiền, số tổng tháng và tổng còn nợ hiện số của máy chủ.
5. Xóa dòng: bấm "Xóa hẳn" thì dòng biến mất ngay, lệnh xóa đi theo cùng hàng đợi.

## Bất biến

- Trang **không cộng trừ tiền**. Thành tiền và số tổng luôn lấy từ máy chủ. Trong lúc chờ, ô Thành tiền của dòng vừa sửa hiện "…", không tính tạm.
- Một lệnh trong hàng đợi bị máy chủ từ chối (sổ vừa đổi, tháng khóa, sai dữ liệu…) thì hàng đợi dừng:
  - Web đọc lại sổ, nên các ô quay về số thật.
  - Web báo rõ ô nào chưa lưu và vì sao. Các ô gõ sau ô đó cũng chưa lưu, và web nói rõ bao nhiêu ô.
- Mất mạng hoặc chưa rõ kết quả: giữ nguyên lệnh đó với cùng khóa idempotency, đầu sổ hiện nút "Thử lại thao tác vừa gửi". Thử lại sẽ gửi lại lệnh đó rồi đi tiếp phần còn lại, như chuỗi dán giá (GIA-O-01 B).
- Trong lúc hàng đợi còn lệnh, sổ không tự đọc lại mỗi 60 giây. Nếu một lần đọc lại xen vào, các ô chưa ghi xong vẫn giữ giá trị vừa gõ, không nháy về số cũ.
- Thao tác khác (ghi phiếu thu, khóa tháng, dán giá…) chờ hàng đợi xong rồi mới gửi, không còn báo "Còn thao tác chưa rõ kết quả".
- Hộp Debit note chờ hàng đợi xong và sổ đọc lại rồi mới dựng chứng từ (nối với bản sửa #421).

## Ngoài phạm vi (giữ đường cũ: chờ máy chủ rồi mới hiện)

- Đổi ngày sang tháng khác (hỏi trước, dòng chuyển tháng).
- Sửa tiền ở tháng khóa (dòng điều chỉnh có ghi chú).
- Phụ phí cần xác nhận "Thành tiền sẽ đổi", sau khi người dùng bấm Ghi.
- Khung Chi tiết phụ phí, dán dòng mới, phiếu thu, cấn trừ.

## Đối chiếu dữ liệu và code hiện có

- Lệnh sổ đi qua `sokhach._finish_command`, nên trả `version` mới. `edit_trip_info` còn trả `pending_review` và `reason`.
- Lệnh trả lỗi `NO_CHANGE` (giá trị như cũ) thì coi như xong, giữ `version`.
- `api.submitSeries` (dán cột giá) đã ghi nối tiếp theo `version` trả về và đọc lại một lần ở cuối. Hàng đợi mới dùng cùng cách, cho nhiều loại lệnh.

## Tiêu chí nghiệm thu

- [x] Unit (`test-so-khach-v7-model.js`): các hàm vá bản sổ (`patchLedger`) cho từng loại lệnh. Không đổi bản gốc; đánh dấu dòng đang lưu.
- [x] Trình duyệt (`test-so-khach-v7-nhap-nhanh-browser.js`, máy chủ giả, lệnh ghi chậm 400 ms):
  - Gõ ba ô liên tiếp: cả ba hiện ngay, gửi ba lệnh theo thứ tự với `expected_version` nối tiếp, chỉ đọc lại sổ một lần sau cùng.
  - Thành tiền hiện "…" rồi ra số máy chủ.
- [x] Trình duyệt: xóa dòng thì dòng biến mất ngay, sổ đọc lại sau.
- [x] Trình duyệt: lệnh thứ hai bị từ chối thì ô quay về số cũ, báo ô nào chưa lưu và số ô sau đó chưa lưu.
- [x] Trình duyệt: mất mạng ở lệnh giữa thì có nút Thử lại; bấm thì ghi nốt, không trùng lệnh.
- [x] Trình duyệt: Debit note mở trong lúc đang lưu thì ra số sau khi lưu (`test-so-khach-v7-go-la-sua-browser.js`, từ #421, nay chạy qua hàng đợi).
- [x] Trình duyệt: ghi phiếu thu trong lúc hàng đợi còn lệnh thì chờ hàng đợi xong rồi gửi, không báo "chưa rõ kết quả".
- [ ] `npm run check` xanh. Đo lại trên `hao` sau triển khai: thời gian từ Enter tới khi ô hiện số mới.

## Phạm vi file

`cong-no-web-handoff/preview/`:

- Hàng đợi: `so-khach-v7-api.js`.
- Hàm vá thuần: `so-khach-v7-model.js`.
- Đường lưu ô: `so-khach-v7-edit-ui.js`, `so-khach-v7-fee-ui.js`.
- Ô "…": `so-khach-v7-trips-ui.js`.
- Dòng "Đang lưu…": `so-khach-v7-ui.js`.
- Máy chủ giả và test.

Không đổi máy chủ, SQL hay quy tắc tiền.

## Thay đổi đi kèm (tìm ra khi làm)

- `hasPending()` chỉ còn nghĩa "còn lệnh chưa rõ kết quả hoặc lệnh thường đang gửi". Hàng đợi đang ghi bình thường là `saving()`, nên Ghi phiếu thu, duyệt Sheet… không bị chặn. Tự làm mới 60 giây tạm dừng cả khi `saving()`.
- Menu "Cài đặt ▾" đang mở thì không vẽ lại nền. Lần vẽ lại sau khi đổi cỡ màn đóng mất menu giữa lúc chọn mục; test ma trận bảng giá 1280×560 lộ ra lỗi này.
- Câu "Sổ vừa thay đổi" vẫn kèm tên người cùng mở sổ khi đứng sau "Chưa lưu ô …:".
