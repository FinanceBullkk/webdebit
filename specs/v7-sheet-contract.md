# V7: hợp đồng đọc Sheet ↔ web (giai đoạn 1)

Trạng thái: giai đoạn 1 **ĐÃ TRIỂN KHAI trên `hao` và CHAU_HAO 29/10/2026** (người dùng cho làm cả A, B, C trong chat; [nhật ký](../docs/deploys/2026-10-29-sheet-contract.md)). Đề xuất ban đầu của Claude cùng ngày, theo yêu cầu đề xuất kiến trúc nối CHAU_HAO với web. Nguồn đơn giá đã chốt ở [`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md). Giai đoạn 2a (đọc `CONT_NGUON`) **ĐÃ CODE 30/10/2026**, chuyển nguồn trên `hao` sau khi đối chiếu 0 lệch (xem mục cuối). Giai đoạn 2b–3 chỉ là hướng.

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

## Giai đoạn 2a: đọc một bảng trung tâm `CONT_NGUON` (30/10/2026)

**Bối cảnh:** ngày 30/10/2026 phía giữ file CHAU_HAO (một phiên AI khác do người dùng giao, không phải bên thứ ba) đề xuất tái cấu trúc tầng nhập và dựng tab `CONT_NGUON`: một dòng một lần đóng cont, khóa `cont|ngày đóng`, tiêu đề ở dòng 1, có Booking, Chủ hàng (chuẩn/gốc), Shipper, Hãng tàu, Kho, Cảng đến, Tên hàng, Mặt hàng, Bảo hiểm, Loại (`BIỂN`/`BỘ`), Tab nguồn, Dòng nguồn, Cờ lỗi. Tab `DOI_CHIEU_NGUON` của họ đối chiếu với `BOOKING_DATA`: 5.576 dòng, 11 tab, 0 lệch. Web trả lời (trong chat, cùng ngày): giữ nguyên các tab đang đọc cho tới khi web đổi nguồn và báo lại; lỗi dữ liệu chỉ gắn cờ, sửa ở file booking gốc; không archive hay dọn chuỗi lập bill vì web đã có debit note ([`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md)).

**Vì sao đổi:** đường cũ ghép `WEBDEBIT_EXPORT` với `BOOKING_DATA` bằng đúng 5 trường (cont, ngày, hãng tàu, nơi đi, nơi đến); lệch một khoảng trắng hay một tên cảng là mất booking và chủ hàng. Một tab, đọc theo tên cột, bỏ được phép ghép đó và hai tab sẽ bị xóa.

**Thay đổi code (PR này):**
- `webdebit_export_connector.read_source` / `parse_source_values`: đọc `CONT_NGUON!A1:Z`, tìm 14 cột theo tên tiêu đề (thêm hoặc đảo cột không sao, đổi chữ tiêu đề thì dừng với `CONT_NGUON header mismatch`). Luật trạng thái **giữ y đường cũ**: `INVALID` khi thiếu cont/ngày/hãng/nơi đi/nơi đến, `DUPLICATE` khi trùng cont + ngày, `NO_CUSTOMER` khi trống chủ hàng chuẩn. Cờ lỗi của Sheet giữ nguyên văn ở `source_flag`, không đổi trạng thái. Chỉ lấy `Loại = BIỂN`; chuyến bộ vẫn dán tay cho tới khi có quyết định riêng.
- `sheet_sync_runner.py --source export|cont_nguon` (env `WEBDEBIT_SHEET_SOURCE`), **mặc định vẫn `export`** cho tới khi đối chiếu trên `hao` đạt; bản chụp ghi `runner.source`.
- `v7_sheet_source_diff.py OLD NEW [--detail]`: so hai bản chụp theo chuyến (cont, ngày, hãng, nơi đi, nơi đến), không theo số dòng; in số đếm, chi tiết (có tên khách) ghi ra file ngoài Git. Mã thoát 0 khi tập dòng `READY` và booking/chủ hàng/shipper/loại sầu riêng của chúng giống hệt.
- `v7_sheet_queue.project_customer`: quyết định "Giữ web" (`sheet_conflict_resolved`) khóa theo đích + trường, không theo số dòng Sheet, vì số dòng đổi khi đổi tab (trên `hao` có 69 quyết định như vậy tới 30/10). Mọi chỗ khác đã ghép theo cont + ngày từ trước (`get_ledger` không trả `source_ref` từ 22/10).

**Đã thử trên dữ liệu thật (PC, chỉ đọc, 30/10/2026):** `CONT_NGUON` 5.576 dòng → `READY` 5.381 (bằng bản chụp đường cũ trên `hao` cùng ngày), `INVALID` 195 (đường cũ 23: 172 dòng thiếu số cont bị công thức `FILTER` của `WEBDEBIT_EXPORT` bỏ từ trước, nay thấy được và đều có Cờ lỗi); sầu riêng 980 đông / 196 tươi.

**Chuyển nguồn trên `hao` (runbook, mục "Đổi nguồn đồng bộ chuyến sang CONT_NGUON"):** chạy runner một lượt với `--source cont_nguon` ra file tạm, so với `snapshot.json` bằng `v7_sheet_source_diff.py`; đạt khi `identical_ready: true`. Rồi PR nhỏ đổi `DEFAULT_SOURCE` sang `cont_nguon` và bỏ đường `export`; sau một lượt timer thành công, báo phía Sheet được bỏ `BOOKING_DATA` và `CONT_BO`. `WEBDEBIT_EXPORT` và `CONT_MASTER` vẫn giữ (PS đọc `CONT_MASTER`).

**Không đổi:** luật tiền, DB, nút duyệt, hợp đồng `WEB_GHEP_KHACH` (tiêu đề cột A vẫn "Chủ hàng từ BOOKING_DATA"), `CONT_MASTER` cho PS, nguồn đơn giá.

## Hướng sau (chưa làm)

- **Giai đoạn 2b:** runner đọc thẳng file booking THIEN THANH và file PS, bỏ phụ thuộc vào chuỗi `IMPORTRANGE` của CHAU_HAO. Khi đó CHAU_HAO hỏng thì web vẫn có chuyến. Cần quyền đọc hai file đó cho tài khoản dịch vụ và đối chiếu lại logic chuẩn hóa tên (`DANH_MUC_KHACH`) trong code.
- **Giai đoạn 3 (sau ngày chuyển hẳn):** web là sổ chính. CHAU_HAO thu về công cụ in bill đọc từ web, hoặc bỏ hẳn vì web đã có debit note ([`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md)). Các tab soát chuyển thành màn hình kiểm trên web. Xét lại [`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md) cùng lúc.
- **CÒN MỞ:** chưa đọc Apps Script của menu BILL (Sheets API không đọc được). Cần trước giai đoạn 3.
