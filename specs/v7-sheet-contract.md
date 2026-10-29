# V7: hợp đồng đọc Sheet ↔ web (giai đoạn 1)

Trạng thái: giai đoạn 1 **ĐÃ TRIỂN KHAI trên `hao` và CHAU_HAO 29/10/2026** (người dùng cho làm cả A, B, C trong chat; [nhật ký](../docs/deploys/2026-10-29-sheet-contract.md)). Đề xuất ban đầu của Claude cùng ngày, theo yêu cầu đề xuất kiến trúc nối CHAU_HAO với web. Nguồn đơn giá đã chốt ở [`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md). Giai đoạn 2–3 ở cuối file chỉ là hướng, chưa làm.

## Bối cảnh: CHAU_HAO đang chạy thế nào (đọc 29/10/2026, chỉ đọc)

Bộ lập bill CHAU_HAO là chuỗi công thức `LET`/`REDUCE`/`IMPORTRANGE`, không có bước lưu giữa:

```
File booking THIEN THANH (tab "THÁNG mm/yyyy") ─IMPORTRANGE─► BOOKING_DATA ─┐
DANH_MUC_KHACH (chuẩn hóa tên chủ hàng) ───────────────────────────────────┤
File PS (tab "CHI PHI PS THANG n", 3 kiểu cột) ─IMPORTRANGE─► PS_DATA ─────┼─► CONT_MASTER (1 dòng / cont|ngày đóng)
NHAP_GIA, GIA_WECHAT (đơn giá cho bill) ───────────────────────────────────┤      ├─► WEBDEBIT_EXPORT
BILL_DA_GUI (bill đã chốt, Apps Script ghi) ───────────────────────────────┘      └─► LOC_CONT → DEBIT NOTE, CI_DATA, các tab soát
```

`CAU_HINH` giữ ID hai file nguồn và danh sách tab theo tháng; thêm tháng mới thì thêm một dòng ở đó.

Web chỉ đọc, qua ba runner trên `hao` (mỗi 15 phút và khi bấm "↻ Làm mới"):

| Runner | File | Tab / dải | Kiểm cấu trúc |
|---|---|---|---|
| đồng bộ chuyến (`sheet_sync_runner.py`) | CHAU_HAO | `WEBDEBIT_EXPORT!A1:E`, `BOOKING_DATA!A1:O`, `WEB_GHEP_KHACH!A1:F` (trước 29/10: `REVIEW_KHACH_2026-10-24`) | So nguyên dòng tiêu đề, lệch thì dừng |
| bảng PS (`v7_ps_snapshot.py`) | CHAU_HAO | `CONT_MASTER!A2:AC`, tab ghép khách | Tìm cột theo tên |
| giá (`v7_price_snapshot.py`) | sổ gốc | mọi tab khách | Theo cấu trúc tab khách |

## Vấn đề giai đoạn 1 xử lý

1. **Runner đồng bộ chuyến trên `hao` chạy bản cài tay ở `/opt/webdebit-sheet-sync`**, không theo release. Bản `webdebit_export_connector.py` ở đó dừng ở 24/10. Nó thiếu phần phân loại sầu riêng cảng/bộ từ cột Tên hàng (#123) và chỉ đọc `BOOKING_DATA` tới cột K, nên tính năng đó chưa chạy thật. Sửa code đồng bộ trong repo cũng không tự lên `hao`.
2. **Tab ghép tên khách mang tên như tab tạm** (`REVIEW_KHACH_2026-10-24`). Người dọn Sheet dễ xóa hoặc đổi tên, làm cả đồng bộ chuyến lẫn bảng PS hỏng.
3. **Không có gì trên Sheet báo cho người sửa biết tab hoặc cột nào web đang đọc.** Chèn cột vào `WEBDEBIT_EXPORT`, đổi chữ tiêu đề `BOOKING_DATA` hay `CONT_MASTER` thì runner dừng (đúng thiết kế), nhưng người sửa Sheet không biết vì sao.

## Thay đổi

**A. Runner đồng bộ chạy từ release** (code + `hao`, không đụng Sheet)

- Đổi `webdebit-sheet-sync.service` sang `WorkingDirectory`/`ExecStart` trong `/srv/v7/auto-releases/current/cong-no-web-handoff/tools/`, như hai runner kia. Giữ `/opt/webdebit-sheet-sync` một tuần để quay lại, rồi xóa.
- Sau khi đổi, kiểm lượt đồng bộ đọc đủ 15 cột `BOOKING_DATA`. Đếm chuyến sầu riêng có `durian_type` ≠ NULL trong bản chụp, chỉ ghi số đếm vào nhật ký.
- Ghi bước này vào runbook mục đồng bộ Sheet, nhật ký trong `docs/deploys/`.

**B. Đổi tên tab ghép khách** (code + Sheet, cần người dùng cho phép ghi Sheet)

- Code đọc `WEB_GHEP_KHACH`; nếu không có thì đọc tên cũ `REVIEW_KHACH_2026-10-24` và ghi cảnh báo vào log runner. Merge và deploy code trước, rồi mới đổi tên trên Sheet, nên không có lúc nào runner hỏng.
- Đổi tên tab trên Sheet (giữ nguyên `sheetId`, dữ liệu, dòng tiêu đề). Sau một lượt đồng bộ đạt thì bỏ đường đọc tên cũ ở PR sau.

**C. Đánh dấu các chỗ web đọc trên Sheet** (Sheet, cần người dùng cho phép)

- Thêm vùng bảo vệ **chỉ cảnh báo** (`warningOnly`, không chặn ai) lên dòng tiêu đề của `WEBDEBIT_EXPORT`, `CONT_MASTER` (dòng 1–2) và `WEB_GHEP_KHACH`. Khi làm: `BOOKING_DATA` đã khóa cứng cả tab nên không thêm; `WEB_GHEP_KHACH` chỉ khóa dòng 1 vì người nhập điền cột F hằng ngày. Lời nhắn: "Web đọc dòng/tab này theo tên cột. Đổi tiêu đề hoặc chèn cột thì đồng bộ lên web dừng. Hỏi trước khi sửa."
- Không đổi công thức, không thêm tab khác.

## Ngoài phạm vi giai đoạn 1

- Không đổi nguồn đơn giá ([`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md)): web vẫn lấy giá từ sổ gốc.
- Không đụng chuỗi `IMPORTRANGE`, Apps Script menu BILL, các tab in bill và tab soát.
- Không đổi luật tiền, không migration.

## Tiêu chí xong

- `webdebit-sheet-sync.service` chạy từ release; lượt đầu `success`, số dòng bằng lượt trước ±0 chuyến mới. `BOOKING_DATA` đọc tới cột O; có `durian_type` trên chuyến sầu riêng có Tên hàng nhận ra.
- Tab `WEB_GHEP_KHACH` tồn tại, tên cũ không còn. Hai runner CHAU_HAO đọc được, log không còn cảnh báo tên cũ.
- Bốn vùng cảnh báo có trên Sheet, đọc lại qua API thấy `warningOnly: true`.
- `npm run check` xanh, test mới cho đường đọc tên tab (tên mới, tên cũ, không có tab nào → lỗi rõ).

## Hướng sau (chưa làm)

- **Giai đoạn 2:** runner đọc thẳng file booking THIEN THANH và file PS, bỏ phụ thuộc vào chuỗi `IMPORTRANGE` của CHAU_HAO. Khi đó CHAU_HAO hỏng thì web vẫn có chuyến. Cần quyền đọc hai file đó cho tài khoản dịch vụ và đối chiếu lại logic chuẩn hóa tên (`DANH_MUC_KHACH`) trong code.
- **Giai đoạn 3 (sau ngày chuyển hẳn):** web là sổ chính. CHAU_HAO thu về công cụ in bill đọc từ web, hoặc bỏ hẳn vì web đã có debit note ([`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md)). Các tab soát chuyển thành màn hình kiểm trên web. Xét lại [`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md) cùng lúc.
- **CÒN MỞ:** chưa đọc Apps Script của menu BILL (Sheets API không đọc được). Cần trước giai đoạn 3.
