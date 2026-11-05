# SO-CHI-TIET-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Sổ mà Sheet ghi mỗi container hai dòng hiện theo bảng kê gửi khách, mỗi container một dòng (spec [`v7-so-chi-tiet.md`](../../specs/v7-so-chi-tiet.md)):

1. **Nguồn là Sheet, tab riêng.** Bảng kê được chép sang tab `CHI TIET ...` trên Sheet sổ chính, không thêm cột vào tab sổ và không nạp file lên web.
2. **Chỉ để xem.** Số nợ vẫn theo tab sổ. Tab chi tiết không vào tiền; khác sổ thì web báo lệch, không tự sửa. Cột Tổng và dòng cộng luôn hiện số của sổ; ô khác bảng kê có viền cam, rê chuột thấy số của bảng kê (chủ nghiệp vụ chốt 5/11/2026 sau khi xem một tháng thật có dòng cộng theo bảng kê cũ cao hơn sổ).
3. **Nghĩa của cước tàu.** Có trong Tổng thì mình thu; ngoài Tổng là khách tự trả, không cộng vào nợ và đứng ngoài phép cộng.
4. **Sửa ở bảng sổ.** Bảng chi tiết không có ô sửa; nút trên thanh chuyến đổi về bảng sổ.
5. **Màn mặc định là bảng gọn, không còn giống hệt Excel.** Phí mình thu + cước tàu mình thu = Tổng, cước khách tự trả ở cột riêng, bấm dòng để bung từng khoản. Vẫn có chế độ "Đủ cột" theo thứ tự file. Thay phần "build giống file excel" của lần chốt 4–5/11 về cách trình bày; các điểm 1–4 giữ nguyên.
6. **Nhãn trung tính khi bảng kê không cộng ra Tổng.** Ghi "Bảng kê không cộng ra Tổng", không viết "cộng thừa" hay kết luận bên nào sai: Tổng có thể cố ý chỉ tính một phần cước, chủ nghiệp vụ chưa xác nhận.

## Ngày / nguồn

4–5/11/2026, chat. Chủ nghiệp vụ gửi bảng kê, giải thích hai dòng, xem mockup rồi chốt "build giống file excel, không tách 2 dòng mà tô màu", chọn nguồn là Sheet. Claude đề xuất và chủ nghiệp vụ cho chép tab riêng vì tab sổ đã kín cột và đang có công thức tổng trỏ vào.

Điểm 5–6: 5/11/2026, chat. Chủ nghiệp vụ thấy bản 15 cột khó hiểu; Claude dựng hai phương án trên canvas và audit bằng dữ liệu thật: khoảng một nửa số tháng có cả cước mình thu lẫn khách tự trả, cột chữ hẹp làm cắt tên kho. Chủ nghiệp vụ xem bản gọn đã sửa theo audit rồi chốt "code trước".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Áp cho sổ có ít nhất một nửa container trong tab chi tiết. Không đổi `V7-COPY`, `PHU-PHI-01`, luật tiền hay đối soát. Tháng có tiền máy ghi thành điều chỉnh tháng chỉ so được ở mức tháng.
