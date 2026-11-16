# Triển khai kiểm Sheet sổ nợ so với booking (16/11/2026)

**ĐÃ TRIỂN KHAI trên `hao`** bằng `Deploy hao` (run 43794698495, xanh lúc 09:52 giờ VN). Theo [`KIEM-BOOKING-01`](../decisions/kiem-booking-01.md) và mục GĐ1b của [spec](../../specs/v7-chuyen-theo-nguon.md). Chỉ đọc: không SQL, không unit hay timer mới, không ghi tiền, không ghi Sheet.

| Mục | Kết quả |
| --- | --- |
| PR | FinanceBullkk/webdebit#428 (merge `894de1f`); FinanceBullkk/webdebit#430 (merge `7731f42`): đưa `v7_load_real_copy.py` về bản cũ để qua cổng loader |
| Release trên `hao` | `7731f42`, thay `ab1ffd2`. Cùng đợt có #426, #427, #429, #432 của các phiên khác |
| CI | Mọi check của #428 và #430 xanh. Tests trên `main` cho `894de1f` và `7731f42` đỏ ở hai test phím của Sổ khách có từ #426 (phiên khác sửa ở #429, #432). Job lỗi của `7731f42` chạy lại thì xanh, sau đó `Deploy hao` chạy |

## Vì sao có #430

`Deploy hao` của `70c97da` dừng ở cổng an toàn: diff từ bản đang chạy có `cong-no-web-handoff/tools/v7_load_real_copy.py`. #428 thêm tham số `tabs` cho `tong_commodities` để đọc xlsx một lần; hành vi mặc định không đổi, nhưng cổng chặn mọi diff có loader `v7_load*`. Người dùng chọn "Đưa loader về cũ" thay cho triển khai tay. #430 trả file về đúng `ab1ffd2`; phép kiểm đọc TONG bằng hàm cũ, chậm thêm khoảng 90 giây trong tiến trình con.

## Lượt theo lịch đầu tiên: 10:05 giờ VN

Đo chỉ đọc: journal, `reconcile-log.jsonl`, `booking-check.json` (đọc bằng `sudo -u v7app`, chỉ in số đếm), API qua Tailscale và trang Máy chạy trong Chrome (chỉ đọc chữ trạng thái và số, không chụp ảnh).

- **Lượt đối soát:** đạt, 487 giây (unit báo 8 phút 7 giây thời gian thật, bộ nhớ đỉnh 205,5 MB cả nhóm). Kết quả đối soát như thường: 235 khớp, 4 chỉ có web, 3 lệch tổng.
- **Phép kiểm booking:** 275 giây, chạy song song nên lượt không dài thêm. Không có `last_error`. File mode 600, chủ `v7app`, 280 KB.
- **Nguồn:** bản chụp lúc 10:01, `CONT_NGUON` 5.744 dòng, `CONT_BO` 2.719 dòng. Sau khi gom: 5.531 chuyến biển, 2.699 chuyến bộ. Bỏ:
  - 195 dòng thiếu container hoặc ngày đọc được;
  - 32 dòng ngày trước năm 2000;
  - 6 dòng trùng container cùng ngày.
- **Khớp:** 7.308/7.641 dòng chuyến của sổ trong khoảng kiểm (biển từ 12/2025, bộ từ 08/2025).

| Nhóm trên trang | Dòng | Ghi chú |
| --- | ---: | --- |
| Nghi tính hai lần | 62 | 55 cùng ngày (30 nhóm), 5 lệch 1–3 ngày, 2 đảo ngày/tháng. Ở 53/55 dòng cùng ngày, booking chỉ có 1 chuyến quanh ngày đó |
| Booking có, sổ chưa tính | 115 | 107 khách đã có sổ, 8 chủ hàng chưa ứng sổ nào |
| Sổ khác khách booking | 23 | Chỉ chuyến biển |
| Trên sổ, booking không có | 45 | |
| Lệch ngày | 67 | Không đổi tiền |
| Sổ thiếu ngày | 231 | Không đổi tiền |
| Tháng này chưa lên sổ | 147 | Tháng 11; 13/11 là 125 |

Chỉ đếm, không lên trang: 550 chuyến trước tháng đầu của tab khách, 8 dòng tính hai lần trước khoảng kiểm, 3 dòng khác khách của chuyến bộ.

So với lần chạy tay 13/11 (cùng mã, bản tải 13/11): sáu nhóm đầu ra đúng số cũ; chỉ nhóm tháng này tăng.

## API và trang

- `GET /api/v7/machine/booking` qua `https://<serve_fqdn>:<serve_port>` trả `state: ok`, `checked_at` 10:05:24, 690 dòng. `/may-chay-booking.js` trả 200.
- Trang Máy chạy:
  - dòng trạng thái "Lượt 10:05 hôm nay · 7.308/7.641 dòng chuyến khớp booking";
  - bảy nút đúng số;
  - nhóm "Nghi tính hai lần" mở ra 62 dòng ở 17 sổ, 56 dòng có link mở sổ (6 dòng ở tab chưa ứng tên một sổ web);
  - không tràn ngang.

## Còn lại

- Người dùng chưa tự đi hết khối trên `hao`.
- Chưa có nút "Đã xem"/"Giữ" theo từng dòng (ĐỀ XUẤT trong quyết định).
- Thư mục thử của lần chạy tay 13/11 (bản tải, bản sao mã, kết quả) đã xóa khỏi `/var/lib/webdebit-sheet-sync/export/` lúc 09:55.

## Rollback

- **Tắt phép kiểm, giữ release:** drop-in `Environment=WEBDEBIT_BOOKING_CHECK=off` cho `v7-reconcile-auto.service`, rồi `daemon-reload` ([runbook](../v7-deploy-runbook.md)).
- **Mã:** revert #428 và #430.
- **Trang báo "chưa có lượt kiểm":** xóa `booking-check.json`.
