---
name: thiet-ke-ux
description: Quy trình bắt buộc khi thiết kế, sửa hoặc review giao diện web công nợ (Sổ khách, Tổng quan, hộp ngoại lệ, mockup, bản bấm thử). Dùng trước khi đổi bố cục, luồng, chữ trên màn hay CSS, và khi người dùng chê "chưa ổn" một màn.
---

**Mục đích:** làm việc như một product designer chịu trách nhiệm cả tính hữu dụng, chất lượng thị giác và khả năng triển khai. Không bắt đầu từ chọn component hay viết code: hiểu mục đích màn, chốt cấu trúc thông tin, có hướng thiết kế rõ, rồi mới làm hình thức. Không coi code chạy, có component chuẩn hay "trông gọn hơn" là đủ để kết luận thiết kế tốt.

Skill này bổ sung cho [quy trình frontend](../../../docs/development.md#quy-trình-frontend) (nghiệp vụ, API, nghiệm thu). Nó không đổi luật tiền và không tự cấp quyền ghi hay triển khai.

## Nguồn phải đọc trước

- [`UX-NEN-01`](../../../docs/decisions/ux-nen-01.md): mục tiêu "bỏ được Sheet mà không mất độ đúng", chỉ số M1–M5 và thứ tự 5 bước. Không sửa giao diện khi chưa qua bước trước.
- Người dùng và số đo thật: [Nền UX](../../../docs/ux-nen-nguoi-dung.md), [luồng dữ liệu](../../../docs/ux-luong-du-lieu.md), [luồng thao tác](../../../docs/ux-buoc-03-luong-thao-tac.md).
- Hệ thị giác: [hướng dẫn UX](../../../docs/ux-guidelines.md), `cong-no-web-handoff/preview/mockups/DESIGN.md`, token ở `cong-no-web-handoff/preview/cong-no-theme.css`, mục 4.4–4.5 của [audit UX](../../../docs/ux-audit-2026-10-31.md). Repo chưa có design system đầy đủ: nói rõ chỗ nào đang theo token, chỗ nào tự đặt.
- Quyết định của màn đang sửa trong [`docs/decisions.md`](../../../docs/decisions.md) (ví dụ `SO-GON-*`, `TRANG-KHACH-01`, `HANG-CHO-01`, `DASH-03`).

## Ràng buộc riêng của dự án

- Người dùng chính trên 40 tuổi; ưu tiên đúng luồng, không thông tin thừa.
- Màn thật 1280×720 logic, Chrome chỉ thấy khoảng **1280×560**. Chrome trên Windows có thanh cuộn dọc 15px mà test headless không thấy: đổi bố cục thì đo lại ở 1280 có thanh cuộn.
- Giá trị số 1 là hết ghi nhầm tiền: mỗi thao tác đụng tiền phải cho thấy trước → sau, chặn sai ở máy trước khi hỏi người.
- Repo public: bản xem, ảnh chụp trong PR hay tài liệu chỉ dùng dữ liệu giả, không tên khách, không số dư thật.

## Các bước

**1. Hiểu bài toán.** Trước khi đổi giao diện, viết ngắn:
- người dùng chính, bối cảnh và tần suất dùng;
- mục đích màn và nó đang ở bước nào của `UX-NEN-01`;
- câu hỏi người dùng mang tới, theo thứ tự ưu tiên; khối nào trả lời câu nào;
- hành động chính và phụ;
- vấn đề hiện tại kèm bằng chứng quan sát được (ảnh render, số đo trên `hao` chỉ đọc, lời người dùng);
- ràng buộc nghiệp vụ, kỹ thuật, dữ liệu: dữ liệu đã có trong DB/API hay phải thêm (đọc schema thật).

Tách điều đã biết với giả định. Đọc tài liệu và code trước khi hỏi; chỉ hỏi khi câu trả lời đổi đáng kể phương án. Hỏi "có thật cần màn hay khối này không?".

**2. Cấu trúc trước hình thức.** Màn mới hoặc thay đổi lớn: đưa hai phương án khác nhau về cách tổ chức thông tin (không chỉ khác màu hay vị trí card), nêu ưu và nhược, đề xuất một theo tác vụ. Đưa cho người dùng chọn bằng AskUserQuestion kèm phác thảo. Chốt rõ:
- nhìn gì thứ nhất, thứ hai, thứ ba trong khung 1280×560;
- cái gì luôn hiện, cái gì chỉ mở khi cần;
- thông tin nào phải đặt cạnh nhau;
- thông tin hoặc hành động nào đang trùng.

Thay đổi nhỏ thì phân tích tương xứng, không cần hai phương án.

**3. Căn cứ cho quyết định thị giác.** Đọc token và component đang có. Xem reference nếu được cung cấp, nói học được gì và điều gì không hợp. Chốt cỡ chữ, mật độ, khoảng cách, màu trạng thái, cách nhóm; giữ nhất quán với các trang khác. Không mặc định mỗi nhóm một card; không thêm KPI, biểu đồ, gradient, icon hay hiệu ứng khi không có mục đích. Chưa có reference thì nói rõ, dựng phương án kiểm được; không giả vờ đã nghiên cứu.

**4. Hành vi và trạng thái.** Ngoài màn đủ dữ liệu, xét:
- đang tải, trống, thiếu dữ liệu (NULL hiện `—`, không như 0), lỗi, mất mạng;
- chữ dài, tên khách có chữ Hán, sổ nhiều dòng, màn hẹp;
- tháng mở và tháng khóa, quyền xem và sửa khác nhau;
- phản hồi sau thao tác, xác nhận hoặc hoàn tác khi đụng tiền.

Dùng từ nghiệp vụ người dùng quen; không để thuật ngữ kỹ thuật hay tên bảng DB quyết định cách trình bày.

**5. Kiểm sau khi làm.** Phải xem bản render thật trước khi kết luận. Kiểm:
- thứ tự chú ý có đúng mục đích màn không;
- tìm thông tin và hành động chính có nhanh không;
- chữ dễ đọc, tương phản đạt, trạng thái tương tác rõ;
- dữ liệu dài và thiếu dữ liệu có làm vỡ bố cục không;
- có theo token và hướng đã chọn không;
- có thông tin lặp hay trang trí gây nhiễu không.

Thấy lỗi thì sửa rồi kiểm lại. Không render được thì nói rõ phần chưa xác minh. Bước cuối của `UX-NEN-01` là người dùng thật đi hết luồng (xong việc, thời gian, số lỗi): Claude tự xem không thay bước đó.

## Báo cáo

Mỗi nhiệm vụ có bằng chứng ngắn cho ba giai đoạn:
1. Trước khi làm: bài toán, thứ tự ưu tiên, hướng thiết kế.
2. Sau khi làm: ảnh render (dữ liệu giả) và kết quả kiểm.
3. Bàn giao: thay đổi chính, lý do, giới hạn còn lại; ghi ĐỀ XUẤT / ĐÃ CHỐT / ĐÃ KIỂM CHỨNG theo `AGENTS.md`.

Không cần xin duyệt từng bước; làm tiếp trong phạm vi được giao. Khi được yêu cầu chỉ phân tích hoặc chờ duyệt phương án thì dừng đúng ở đó. Người dùng chê chung chung thì hỏi lại bằng các chỗ cụ thể kèm phác thảo, không đoán.

**Điều cấm:** dùng dữ liệu khách thật trong bản xem hay ảnh chia sẻ; biến lựa chọn trên UI thành chính sách khi quy tắc còn CÒN MỞ; nhảy vào sửa CSS khi chưa qua bước 1–2 với thay đổi lớn.
