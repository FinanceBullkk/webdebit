# Checklist chuyển hẳn khỏi Sheet sổ nợ

Lập 11/11/2026 (Claude). **ĐỀ XUẤT**: danh mục do Claude đặt theo câu hỏi của người dùng ("cần audit những gì để nói web thay được Sheet"), chưa được duyệt từng mục. Phạm vi theo [`CHUYEN-HAN-01`](decisions/chuyen-han-01.md): thay Sheet sổ nợ (tab TONG và các tab khách); file nguồn chuyến CHAU_HAO vẫn dùng. Tiếp nối [checklist chạy song song](song-song-checklist.md) mục F4.

Trạng thái một mục chỉ đổi khi có bằng chứng đúng môi trường, ghi ngày. Tên khách và số tiền giữ ngoài Git; ở đây chỉ có số đếm.

## Việc phải làm thêm, không phải việc kiểm

Từ 4/11/2026 web chạy theo Sheet ([`MAY-DOI-SOAT-01`](decisions/may-doi-soat-01.md)). Bỏ Sheet sổ nợ thì các đầu vào sau mất nguồn; audit sạch cũng không thay được việc này. Phương án thay là ĐỀ XUẤT, CÒN MỞ tới khi người dùng chọn.

| Đầu vào | Hôm nay | Phương án thay (ĐỀ XUẤT) |
| --- | --- | --- |
| Chuyến mới | Chuyến biển đọc `CONT_NGUON`. Chuyến bộ vào sổ nào là theo tab khách trên Sheet sổ nợ ([`NGUON-CHUYEN-01`](decisions/nguon-chuyen-01.md)). Bảng nhập tay đã gỡ khỏi màn hình ([`NHAP-SHEET-02`](decisions/nhap-sheet-02.md)); lệnh `paste_trips` còn | Bật lại bảng nhập; chọn sổ cho chuyến bộ ngay trên web |
| Giá, phụ phí | Máy chép từ Sheet ([`MAY-GIA-01`](decisions/may-gia-01.md)) | Bảng giá trên web ([`BANG-GIA-02`](decisions/bang-gia-02.md)) và gõ tay |
| Phiếu thu | Máy chép từ Sheet ([`THU-SHEET-01`](decisions/thu-sheet-01.md)) | Người nhập gõ ở hàng phiếu thu, hàng này vẫn còn |
| Khách mới | Máy tạo sổ khi khách có trên TONG ([`MAY-TAO-SO-01`](decisions/may-tao-so-01.md)) | Tạo sổ từ nguồn booking hoặc từ màn hình |
| Lưới an toàn | Đối soát "khớp Sheet" mỗi giờ; hết hiệu lực khi chuyển hẳn | Phép kiểm định kỳ khác: so với booking, khách xác nhận debit note |

## Danh mục

Cột "Máy" ghi mục nào `v7_cutover_audit.py` đo được ([spec](../specs/v7-cutover-audit.md)).

### A. Số có đúng không

| # | Kiểm gì | Đạt khi | Máy | Trạng thái 11/11/2026 |
| --- | --- | --- | --- | --- |
| A1 | Tổng nợ từng khách web bằng Sheet lúc cuối tháng | Mọi khách khớp hoặc lệch đã giải thích; báo cả theo tiền | có | Chưa tới ngày xét. Lượt 17:12: 236/239 khớp, 3 khách web đi trước Sheet, lệch chưa giải thích bằng 0 |
| A2 | Tab TONG cộng đủ các tab khách | Mọi dòng TONG khớp sổ; không sổ nào còn số dư mà TONG để trống | có | **KHÔNG ĐẠT.** Khối tháng 10: 64 dòng có số đều khớp, nhưng 14 sổ còn số dư bị để trống (11 nợ, 3 dư). Chờ chủ sổ kết luận từng khách |
| A3 | Từng dòng và từng tháng, không chỉ tổng | Không còn dòng, tháng hay tổng thu nào `CHUA_GIAI_THICH` | có | ĐẠT cho lượt đo: 9.526/10.521 dòng khớp tuyệt đối, 0 dòng lệch giá; 7 tháng và 3 tổng thu khác nhau đều có lời giải; 17 dòng một bên có đều có lời giải |
| A4 | Các lời giải thích có người chốt | Mỗi nhóm có kết luận của chủ sổ | một phần | CÒN MỞ: 3 dòng bù số dư chuyển năm chưa ai xác nhận; 2 dòng lặp trên Sheet chưa xóa; 6 tab không có sổ chưa kết luận |
| A5 | Lệnh máy đã ghi | Không phiếu máy ghi nào bị hủy; không giá nào đè rồi phải quay lại; tháng máy mở đều đã khóa | có | ĐẠT cho 1–11/11: 2.883 lệnh; 20 phiếu, 0 bị hủy; 0 lần đè rồi quay lại; 17 dòng điều chỉnh máy ghi rồi tự xóa hết sau chưa đầy một ngày |
| A6 | Sheet tự nó có đúng không | So với booking, sao kê, xác nhận của khách lớn | không | CHƯA. Nguồn booking có 4 chuyến đã 4–9 ngày chưa nằm ở sổ nào (khách mới chưa có tab) và 13 chuyến đang chờ ở 9 sổ |

### B. Bỏ Sheet thì nhập ở đâu

| # | Kiểm gì | Đạt khi | Máy | Trạng thái 11/11/2026 |
| --- | --- | --- | --- | --- |
| B1 | Mỗi kiểu sửa người nhập làm trên Sheet có thao tác tương ứng trên web | Bảng ánh xạ không còn dòng trống | không | CHƯA lập bảng. Khối lượng 1–11/11 theo log sửa Sheet: 988 lần sửa ở 46 tab; riêng tab TONG 114 lần, gõ từng ô |
| B2 | Mỗi phương án thay ở bảng trên có một lần ghi thật trên `hao` | Dòng Lịch sử của từng loại | có | CHƯA. Giá: máy chép từ Sheet 363 lần (từ 1/11); bảng giá web áp 8 lần, người gõ 46 lần (từ 22/10) |

### C. Người dùng tự làm được không

| # | Kiểm gì | Đạt khi | Máy | Trạng thái 11/11/2026 |
| --- | --- | --- | --- | --- |
| C1 | Người nhập làm trọn một ngày trên web, không mở Sheet | Hết việc trong ngày, không ghi nhầm | không | CHƯA từng làm |
| C2 | Mỗi thao tác tiền có lần ghi thật của người | Mọi dòng của bảng thao tác có số khác 0 | có | CHƯA đủ: chưa người nào làm điều chỉnh theo chuyến, sửa ngày phiếu, kết luận chuyến chờ kiểm; cấn trừ hai sổ chưa ai dùng |
| C3 | Mỗi người một tài khoản, Lịch sử ra đúng tên | Hai người, hai tên | đếm | CHƯA: mới 1 login từng ghi; danh sách cho phép có 3 login |
| C4 | Hai người cùng sửa một sổ | Không mất dữ liệu, người sau được báo | không | CHƯA thử bằng hai người thật ([`PRESENCE-01`](decisions/presence-01.md)) |
| C5 | Chủ sổ tự đi hết các màn đã lên `hao` | Xác nhận từng màn | không | CHƯA: Sổ gọn, Việc cần làm, xuất debit note đối chiếu mẫu, xóa dòng điều chỉnh |

### D. Thứ Sheet đang cho ra

| # | Kiểm gì | Đạt khi | Máy | Trạng thái 11/11/2026 |
| --- | --- | --- | --- | --- |
| D1 | Debit note gửi khách | Đúng mẫu, đúng số, có thông tin ngân hàng | không | CHƯA có thông tin ngân hàng |
| D2 | Số trên Tổng quan bằng số trong sổ | Khớp tới đồng tại cùng thời điểm | không | ĐẠT cho tổng: "còn phải thu" trừ phần khách dư bằng tổng 239 sổ |
| D3 | Tra chuyện cũ không cần mở Sheet | Lấy mẫu vài khách, vài tháng cũ | không | CHƯA |
| D4 | Ai và cái gì khác đang đọc Sheet sổ nợ | Danh sách rỗng hoặc đã chuyển sang web | không | CHƯA liệt kê |

### E. Hệ thống có trụ được khi là sổ duy nhất

| # | Kiểm gì | Đạt khi | Máy | Trạng thái 11/11/2026 |
| --- | --- | --- | --- | --- |
| E1 | `hao` hỏng thì mất bao nhiêu và bao lâu dựng lại | Diễn tập phục hồi trên máy khác, có số phút | không | CHƯA. Lần phục hồi thử có ghi lại là 29/10, trên chính `hao` |
| E2 | `hao` sập giữa ngày thì ghi tạm vào đâu | Có quy trình một trang | không | CHƯA |
| E3 | Cảnh báo email tới thật | Một lần thử tới hộp thư | không | Máy canh báo ổn lúc 17:32; chưa kiểm lại email |
| E4 | Bảo mật | Ba điểm còn mở của [`ACCESS-01`](decisions/access-01.md) đóng hoặc được chấp nhận | không | CÒN MỞ |
| E5 | Sang tháng | Ngày 1 máy chạy không kẹt | không | Chờ 1/12 |
| E6 | Lỗi mạng, bấm lặp, tốc độ khi dán nhiều chuyến | Đo trên `hao` | không | CHƯA |

### F. Quyết định và đường lui

| # | Kiểm gì | Đạt khi | Trạng thái 11/11/2026 |
| --- | --- | --- | --- |
| F1 | Câu chủ nghiệp vụ còn nợ | Mỗi câu có chốt | CÒN MỞ: khách không còn tab ([`SONG-SONG-03`](decisions/song-song-03.md)); các mục "Việc chủ sổ phải quyết" dưới đây |
| F2 | Quyết định còn chữ CÒN MỞ chạm đường tiền | Đã lọc và trả lời | CHƯA lọc |
| F3 | Kịch bản ngày chuyển | Diễn tập trên bản sao | CHƯA viết |
| F4 | Đường lui | Xuất được cả sổ web ra bảng tính, tổng khớp | CHƯA có lệnh xuất cả sổ |
| F5 | Lưới an toàn thay "khớp Sheet" | Có phép kiểm định kỳ khác | CHƯA |

## Lượt đo 11/11/2026

ĐÃ KIỂM CHỨNG trên `hao`, 17:12–17:50 giờ VN, bản đang chạy `35cba76`. Chỉ đọc: GET API, bản chụp Sheet của runner giá, tab TONG đọc qua Google Sheets. Không ghi `hao`, không ghi Sheet. Bản có tên khách và số tiền giữ ngoài Git.

- **Đối soát:** 239 sổ, 236 khớp, 3 web đi trước (6 chuyến). 125 lượt từ 4/11, không lượt nào thiếu so với lịch từ 5/11; 18 việc máy sửa, 3 sổ máy tạo.
- **Dòng:** 10.521 dòng chuyến ở 239 sổ. 9.526 khớp tuyệt đối; 494 không giá ở cả hai bên; 233 không container; 262 trỏ tới nhiều dòng web (container dùng lại hoặc dòng lặp) nên không soi riêng từng dòng; 6 chỉ Sheet có.
- **Tháng và thu:** 7 tháng khác phát sinh ở 7 sổ (3 web đi trước, 2 dòng lặp trên Sheet, 1 tổng trải đều lúc nạp, 1 dòng bù chuyển năm). 3 sổ khác tổng thu (2 dòng bù chuyển năm, 1 làm tròn 2 đồng).
- **Dòng một bên có:** 17 (8 dời sang sổ khác, 6 web đi trước, 2 khác chữ ở ô container, 1 đã ghi bằng dòng điều chỉnh).
- **TONG:** khối mới nhất là tháng 10/2026, chưa có khối tháng 11. 64 dòng có số, đều khớp. 14 sổ còn số dư để trống. Một dòng TONG tự không cân (số chuyển sang trống).
- **Máy:** 2.883 lệnh; 297 lần điền giá, 8 lần đè (6 lần chỉ thêm phụ phí); 346 chuyến dán, 1 bị xóa; mọi tháng máy mở đều đã khóa.
- **Người:** 1 login, 422 lệnh từ 22/10. Ngày 25/10 API nhật ký chỉ trả 2.000/3.107 dòng nên con số này là mức tối thiểu. 28 chuyến người dán đã phải xóa lại.
- **Sổ:** 15 tháng cũ đang mở ở 8 sổ; 73 chuyến chưa giá (69 của tháng 11); 0 chuyến chờ kiểm; 69 phiếu web, 7 đã hủy; 0 cấn trừ hai sổ.

## Việc chủ sổ phải quyết

1. 14 khách còn số dư mà TONG để trống: còn đòi thì điền lại ô TONG; đã xong thì ghi thu hoặc xóa nợ trên tab.
2. 3 con số chuyển năm không có dòng chứng minh: xác nhận từng số.
3. 4 chuyến trong booking chưa nằm ở sổ nào: tạo tab cho hai mã khách mới.
4. 13 chuyến booking đang chờ ở 9 sổ, 11 chuyến từ tháng 1–8/2026: tính hay loại.
5. 15 tháng cũ đang mở: khóa lại.
6. Một lần Sheet giảm giá lớn mà máy đã theo: xác nhận là đúng ý.

## Cách chạy lại

Sau [đối soát cuối tháng](v7-deploy-runbook.md#đối-soát-cuối-tháng--mốc-xét-chuyển-hẳn-song-song-01) (bước 1 tải xlsx, cùng một bản tải). Chép thêm `reconcile.json` của lượt đối soát gần nhất từ `hao`. Thư mục `--out` phải mới và nằm ngoài mọi Git.

```text
python cong-no-web-handoff/tools/v7_cutover_audit.py \
  --api https://<serve_fqdn>:<serve_port> --serve-host <serve_fqdn>:<serve_port> \
  --xlsx <source-google-export.xlsx> --reconcile <reconcile.json> \
  --since <ngày đầu tháng> --until <hôm nay> --out D:\doi-soat\audit-<ngày>
```

- Mã thoát 0: không còn mục tiền nào phải có người xem. 1: còn, đọc `bao-cao.txt`. 2: lỗi đầu vào.
- Tên trên TONG không tự ghép được với sổ: thêm `--tong-alias "TÊN TRÊN TONG=TÊN SỔ"`. Tab đã kết luận là bản sao hay tab cũ: thêm `--ignore-tab "TÊN TAB"`. Hai danh sách này có tên khách nên chỉ nằm trong lệnh chạy, không vào Git.
- Không có xlsx thì dùng `--prices`, `--receipts` (bản chụp ở `/var/lib/webdebit-sheet-sync/`) và `--tong <file JSON chép khối TONG>`.
- Ghi số đếm của mỗi lượt vào mục "Lượt đo" ở trên và cập nhật cột trạng thái.
