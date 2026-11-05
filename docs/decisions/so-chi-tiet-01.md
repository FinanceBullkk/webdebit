# SO-CHI-TIET-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Sổ mà Sheet ghi mỗi container hai dòng hiện theo đúng cột bảng kê gửi khách, mỗi container một dòng, tô màu thay cho tách dòng (spec [`v7-so-chi-tiet.md`](../../specs/v7-so-chi-tiet.md)):

1. **Nguồn là Sheet, tab riêng.** Bảng kê được chép sang tab `CHI TIET ...` trên Sheet sổ chính, không thêm cột vào tab sổ và không nạp file lên web.
2. **Chỉ để xem.** Số nợ vẫn theo tab sổ. Tab chi tiết không vào tiền; khác sổ thì web báo lệch, không tự sửa.
3. **Nghĩa của cước tàu.** Có trong Tổng thì mình thu (xanh); ngoài Tổng là khách tự trả (cam), không cộng vào nợ.
4. **Sửa ở bảng sổ.** Bảng chi tiết không có ô sửa; nút trên thanh chuyến đổi về bảng sổ.

## Ngày / nguồn

4–5/11/2026, chat. Chủ nghiệp vụ gửi bảng kê, giải thích hai dòng, xem mockup rồi chốt "build giống file excel, không tách 2 dòng mà tô màu", chọn nguồn là Sheet. Claude đề xuất và chủ nghiệp vụ cho chép tab riêng vì tab sổ đã kín cột và đang có công thức tổng trỏ vào.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Áp cho sổ có ít nhất một nửa container trong tab chi tiết. Không đổi `V7-COPY`, `PHU-PHI-01`, luật tiền hay đối soát. Tháng có tiền máy ghi thành điều chỉnh tháng chỉ so được ở mức tháng.
