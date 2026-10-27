# Đối soát cuối ngày Sheet – web

Dành cho người nhập, chạy **mỗi cuối ngày** trong thời gian chạy song song ([`SONG-SONG-01`](decisions.md#song-song-01), [`SONG-SONG-02`](decisions.md#song-song-02)). Mục đích: biết tổng nợ từng khách trên web có bằng trên Sheet không. Sheet là sổ chính thức, nên lệch thì **sửa trên web**.

Chi tiết kỹ thuật của hai công cụ ở [runbook, mục đối soát cuối ngày](v7-deploy-runbook.md#đối-soát-tổng-khách-cuối-ngày--song-song-02). Trang này chỉ là các bước làm.

## Trước khi bắt đầu

- Cả Sheet và web đều **đã ngừng nhập** trong ngày. Nếu ai còn nhập sau khi chạy thì phải chạy lại.
- Máy chạy là máy có thư mục `D:\webdebit\repo` (đã cài theo README) và vào được web V7 qua Tailscale.
- Kết quả có tên khách và số tiền: lưu trong `D:\webdebit\captures\doi-soat\`, **không** đưa vào Git, không gửi qua kênh công khai.

Trong các lệnh dưới, thay `2026-11-03` bằng ngày hôm nay, `<dia-chi-web>` bằng địa chỉ web V7 (dạng `ten-may.ten-tailnet.ts.net:cong`, admin cung cấp).

## Bước 1. Tải Sheet

Trên Google Sheet: **Tệp → Tải xuống → Microsoft Excel (.xlsx)**. Lưu thành:

```text
D:\webdebit\captures\doi-soat\2026-11-03\sheet.xlsx
```

## Bước 2. Làm sạch bản tải

Mở PowerShell:

```powershell
cd D:\webdebit\repo
.venv\Scripts\python cong-no-web-handoff\tools\v7_export_clean.py --xlsx D:\webdebit\captures\doi-soat\2026-11-03\sheet.xlsx --out D:\webdebit\captures\doi-soat\2026-11-03\sach
```

| Màn hình in ra | Nghĩa | Làm gì |
| --- | --- | --- |
| `"ok": true` | Làm sạch xong | Sang bước 3 |
| `"held_customers": …` | Có khách bị giữ, **không tạo file nào** | Dừng. Báo admin/Claude số khách và `reason_counts` |
| `"ok": false, "reason": …` | Lỗi đọc file | Dừng. Báo lại nguyên dòng đó |

## Bước 3. So với web

```powershell
.venv\Scripts\python cong-no-web-handoff\tools\v7_reconcile_sheet.py --sheet-dir D:\webdebit\captures\doi-soat\2026-11-03\sach --api https://<dia-chi-web> --serve-host <dia-chi-web> --out D:\webdebit\captures\doi-soat\2026-11-03\ket-qua --totals-only --brief
```

Công cụ chỉ **đọc** web, không ghi gì. Thư mục `ket-qua` phải chưa tồn tại; chạy lại thì đặt tên mới (`ket-qua-2`, …).

## Bước 4. Đọc kết quả

Màn hình PowerShell in một dòng kết luận:

- `DOI SOAT: DAT`: mọi khách khớp. Xong, sang bước 6.
- `DOI SOAT: KHONG DAT`: có khách lệch. Sang bước 5.

Nếu không thấy dòng `DOI SOAT` mà thấy `reconciliation input/output error`, đó là lỗi đọc/ghi, **không** phải kết quả. Báo lại.

Để xem chi tiết, mở file `ket-quaeconcile_report.html` (bấm đúp, mở bằng trình duyệt). Đầu trang ghi **ĐỐI SOÁT: ĐẠT** hoặc **ĐỐI SOÁT: KHÔNG ĐẠT**. Bên dưới là bảng từng khách gồm tổng Sheet, tổng web, chênh lệch và trạng thái. Dòng xanh là khớp, dòng đỏ là cần xem.

| Trạng thái | Nghĩa |
| --- | --- |
| Khớp | Tổng web bằng tổng Sheet |
| Lệch tổng | Hai tổng khác nhau |
| Chỉ có Sheet | Khách có trên Sheet, không có trên web |
| Chỉ có web | Khách có trên web, không có trên Sheet |
| Thiếu số | Một bên chưa có tổng (ví dụ khách chưa có số dư đầu). Không coi là 0 |

## Bước 5. Khi lệch

Xem các **dòng đỏ** trong `reconcile_report.html`. **Chênh lệch = web − Sheet**. Nếu cần lọc hay sắp xếp, mở `ket-quaeconcile_customer.csv` bằng Excel; file này có cùng số liệu.

| Chênh lệch | Hay gặp do | Sửa trên web |
| --- | --- | --- |
| Âm (web ít hơn) | Chuyến đồng bộ từ Sheet còn **chưa điền giá**; chuyến mới chưa bấm duyệt; chuyến đang CHỜ KIỂM | Điền giá; bấm "Duyệt … chuyến mới"; kết luận CHỜ KIỂM |
| Dương (web nhiều hơn) | **Phiếu thu** trên Sheet chưa nhập lên web; Sheet đã sửa giá/xóa dòng mà web chưa theo | Nhập phiếu thu; sửa ô cho giống Sheet |

Tháng đã khóa thì mở khóa trước khi sửa chuyến (phiếu thu vẫn nhập được). Sửa xong, chạy lại **bước 3** với thư mục kết quả mới. Không sửa được hoặc không hiểu vì sao lệch: ghi lại tên khách và số chênh, báo chủ nghiệp vụ.

## Bước 6. Ghi sổ theo dõi

Mỗi ngày ghi một dòng vào sổ theo dõi (ngoài Git): ngày, `DAT`/`KHONG DAT`, số khách lệch, đã sửa gì. Chủ nghiệp vụ xem tổng kết cuối tuần và cuối tháng; cuối tháng khớp là điều kiện để chuyển hẳn sang web.

## Giới hạn

- Chỉ so **tổng từng khách**, không so từng dòng. Hai lỗi bù trừ nhau trong cùng khách sẽ không lộ ra.
- Bước 2 hiện **dừng** nếu bản tải Sheet có khách bị giữ (mục A3 của [checklist](song-song-checklist.md)). Chưa xử lý A3 thì chưa chạy được bước 3.
- Hướng dẫn này chưa được chạy thử trên dữ liệu thật (mục C4 của checklist).
