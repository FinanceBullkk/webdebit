# THEO-THANG-GON-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Trang Công nợ theo tháng, phương án A người dùng chọn ("Một dải tổng"):

1. Thẻ tổng (Còn phải thu, Khách trả trước, nợ ngoài năm, số khách) thành **một dải một dòng** trên bảng; cùng số, cùng nhãn.
2. Chân bảng **chỉ dòng "Còn phải thu ròng" dính đáy màn**, một dòng. Dòng này chỉ in nhãn; số khách ở chữ rê chuột và ở dải tổng (cột Khách không đủ chỗ cho cả hai khi font rộng). Hai dòng Phải thu và Trừ: trả trước theo tháng (chuẩn kế toán, không bù trừ) vẫn có, nằm cuối bảng và không dính.
3. Tiêu đề cột Khách một dòng "Khách (triệu đồng)".

## Ngày / nguồn

23/11/2026, chat. Audit giao diện 23/11 đo trên `hao`: thẻ tổng 84px và ba dòng chân dính 124px lặp cùng số; ở 1280×560 chỉ thấy 4–5 khách. Claude đưa hai phương án (A: một dải tổng; B: tổng lên đầu bảng, phần trên cuộn đi); người dùng chọn **A**.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi cách hiện; số, dòng chân và đối soát "Khớp" không đổi. Dữ liệu giả ở 1265×560: 7 khách và dòng nhóm trọn dòng (trước 5).
