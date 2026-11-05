# SHEET-LOG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Log sửa Sheet do Apps Script ghi ([`sheet-capture`](../../specs/sheet-capture.md)) **chỉ dùng để giải thích, không dùng để ghi tiền.** Hai việc:

1. **Máy đối soát biết tab vừa được sửa.** Khách chưa khớp, kết luận thuộc loại "chưa rõ vì sao lệch", mà tab có lần sửa từ 15 phút trước lúc tải bản Sheet trở đi: không tính là "khách cần xem", không làm dải đối soát chuyển vàng. Dòng của khách vẫn hiện trong danh sách với giờ sửa và kết luận của máy. Lượt sau tab đã yên mà vẫn lệch thì thành "cần xem" như thường. Khách chưa khớp còn lại hiện thêm giờ Sheet sửa lần cuối.
2. **Có lệnh tra lịch sử sửa của một tab** (`tools/v7_sheet_log.py`), để khi lệch biết ô nào đổi lúc nào. Thay cho việc đọc tay cả log. Lệnh chạy trên `hao`, in tên khách và số tiền ra terminal của người chạy.

**Không làm:**

- **Không chặn máy ghi khi tab đang sửa.** Đo trên `hao` 3–5/11/2026: trong 90 đợt máy ghi tiền có 19 đợt ghi sau lần sửa tab không quá 30 phút, và không đợt nào trong 19 đợt đó có sửa tiếp trong 60 phút sau. Chốt khớp đúng tổng của [`MAY-DOI-SOAT-01`](may-doi-soat-01.md) đã chặn phần lớn trường hợp nhập dở, vì nhập dở thì hiếm khi có đúng một tổ hợp khớp tới từng đồng. Xét lại nếu có ca thật máy ghi theo số người đang nhập dở.
- **Không dựng lại sổ hay ghi tiền từ log.** Log thiếu lần sửa qua API hoặc script, thường không có giá trị cũ (chỉ khi sửa một ô đã có giá trị) và không biết ai sửa (cột người sửa trống ở mọi dòng đã xem).
- **Không dùng log để kết luận ai sửa.**
- **Không cảnh báo "sửa tháng cũ mà tổng không đổi" từ log.** Log không bắt lần sửa qua API. Nếu cần, nên để `hao` tự so các bản Sheet nó đã tải.

**Vì sao 15 phút.** Đo log 21/10–5/11/2026 (711 khoảng nghỉ giữa hai lần sửa cùng một tab, bỏ tab TONG): 93,5% không quá 15 phút, và tab đã yên quá 15 phút thì chỉ 7% có sửa tiếp trong 60 phút sau. Thử trên 69 giờ chạy giả định 1–5/11: 13 lượt có tab vừa sửa, không tab nào bị đánh dấu hai lượt liền, nên một khách lệch thật chỉ chậm báo một giờ.

## Ngày / nguồn

5/11/2026, chat. Người dùng hỏi có nên tận dụng file log này; Claude đo rồi đề xuất chỉ dùng tra cứu. Người dùng nói "tìm use case phù hợp và integrate cho phù hợp", giao Claude chọn. Claude đo thêm giả thuyết "chặn ghi khi tab đang sửa", số đo không ủng hộ nên bỏ, chọn hai việc trên. Lúc đo, khách duy nhất chưa khớp có lần sửa tab 4 phút trước lúc tải.

## Hiệu lực và giới hạn

ĐÃ CHỐT, Claude quyết theo ủy quyền trên; không đổi luật tiền, DB, quyền ứng dụng, đường ghi. Chi tiết ở [spec](../../specs/sheet-log-doi-soat.md), cách bật ở [runbook](../v7-deploy-runbook.md#log-sửa-sheet-sheet-log-01). Tắt bằng cách bỏ biến `WEBDEBIT_EDIT_LOG_ID`.

Không thấy lần sửa không có nghĩa là không ai sửa: khách lệch vì sửa qua API thì vẫn là "cần xem", đúng như trước khi có log. Log dừng thì máy báo `STALE` trong `reconcile.json` và journal, màn vẫn chạy như chưa có log.

Hết tác dụng khi chuyển hẳn khỏi Sheet.
