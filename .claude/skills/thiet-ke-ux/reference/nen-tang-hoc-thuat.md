# Nền tảng học thuật UX/UI cho web công nợ

Đọc khi cần căn cứ cho một quyết định thiết kế ở bước 2–5 của [skill](../SKILL.md). Mỗi mục gồm: nguyên lý (diễn đạt lại), nguồn gốc để tra, và cách áp vào web này. Nguyên lý dùng để **lập luận và phản biện**; khi nguyên lý và số đo người dùng thật (M1–M5 của [`UX-NEN-01`](../../../../docs/decisions/ux-nen-01.md)) khác nhau thì số đo thắng.

Khi đề xuất phương án, nêu nguyên lý bằng tên (ví dụ "theo luật Hick, giảm lựa chọn ở bước ghi phiếu"). Như vậy người duyệt kiểm được lập luận, và lựa chọn không chỉ dựa vào "trông đẹp hơn".

## 1. Lỗi của người và cách thiết kế chặn lỗi

Mục tiêu số 1 của web là hết ghi nhầm tiền, nên đây là phần quan trọng nhất.

- **Trượt tay và nhầm hiểu (slips vs mistakes).** Trượt tay là định làm đúng mà thao tác sai: bấm nhầm dòng, gõ thừa số 0. Nhầm hiểu là hiểu sai tình huống nên chọn sai việc: tưởng phiếu thuộc tháng trước. Hai loại cần cách chặn khác nhau. Trượt tay chặn bằng ràng buộc và xác nhận trước → sau. Nhầm hiểu chặn bằng cách hiện đúng bối cảnh: khách nào, tháng nào, số dư hiện tại.
  Nguồn: J. Reason, *Human Error* (1990); D. Norman, *The Design of Everyday Things*, bản sửa 2013, chương 5.
- **Ràng buộc chống lỗi (poka-yoke, forcing function).** Làm cho thao tác sai không thể làm, thay vì cảnh báo sau khi đã làm. Ở web này: chặn ngày ghi sổ tương lai, chặn ghi vào tháng khóa (`MONTH_LOCKED`), chặn tên khách vào sổ khác.
  Nguồn: S. Shingo, *Zero Quality Control* (1986); Norman (2013).
- **Phản hồi và tầm nhìn trạng thái.** Sau mỗi thao tác, người dùng phải thấy hệ thống đã làm gì, trong khoảng 0,1 giây (cảm giác tức thì), 1 giây (không mất mạch), 10 giây (giới hạn chờ còn giữ được chú ý). Ghi phiếu xong hiện toast có số tiền và nút hoàn tác; lấy từ Sheet lâu thì có tiến trình.
  Nguồn: R. B. Miller, "Response time in man-computer conversational transactions" (1968); S. Card, G. Robertson, J. Mackinlay (1991); J. Nielsen, *Usability Engineering* (1993), chương 5.

## 2. Mười nguyên tắc heuristic và tám quy tắc vàng

Dùng như checklist review một màn:

- **Nielsen, 10 heuristic:** trạng thái hệ thống luôn thấy; khớp ngôn ngữ người dùng (từ điển giao diện mục 4.5 [audit UX](../../../../docs/ux-audit-2026-10-31.md)); người dùng làm chủ, có lối thoát và hoàn tác; nhất quán và theo chuẩn quen; phòng lỗi; **nhận ra hơn nhớ lại**; linh hoạt cho người dùng thạo (dán lô từ Sheet, phím tắt); tối giản, không thông tin thừa; giúp nhận ra và sửa lỗi; trợ giúp khi cần.
  Nguồn: J. Nielsen, R. Molich, "Heuristic evaluation of user interfaces", CHI 1990; J. Nielsen, CHI 1994; [nngroup.com/articles/ten-usability-heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/).
- **Shneiderman, 8 quy tắc vàng:** nhất quán; phục vụ cả người mới và người thạo; phản hồi có ích; hộp thoại có điểm kết rõ; phòng lỗi; hoàn tác dễ; người dùng cảm thấy mình điều khiển; giảm tải trí nhớ ngắn hạn.
  Nguồn: B. Shneiderman và cộng sự, *Designing the User Interface*, bản 6 (2016); [cs.umd.edu/~ben/goldenrules.html](https://www.cs.umd.edu/~ben/goldenrules.html).
- **ISO 9241-110 (2020), nguyên tắc tương tác:** phù hợp nhiệm vụ, tự mô tả, đúng kỳ vọng người dùng, dễ học, người dùng điều khiển, chịu được lỗi, phù hợp từng người. Dùng khi cần ngôn ngữ chuẩn để viết tiêu chí nghiệm thu trong spec.

## 3. Nhận thức: chú ý, trí nhớ, quyết định

- **Tải nhận thức.** Trí nhớ làm việc chỉ giữ được khoảng 4 mục cùng lúc (không phải 7). Tải "thừa" do cách trình bày gây ra (phải nhớ số ở màn này để so với màn khác, đọc mã thay vì tên) phải bỏ trước. Thông tin cần so sánh thì đặt cạnh nhau, trên cùng một màn.
  Nguồn: J. Sweller, "Cognitive load during problem solving", *Cognitive Science* (1988); N. Cowan, "The magical number 4 in short-term memory", *Behavioral and Brain Sciences* (2001).
- **Luật Hick–Hyman.** Thời gian quyết định tăng theo logarit của số lựa chọn ngang hàng. Màn có hành động chính thì một vùng chỉ một nút chính; lựa chọn hiếm dùng đưa vào "Thêm".
  Nguồn: W. E. Hick (1952); R. Hyman (1953).
- **Luật Fitts.** Thời gian trỏ tới mục tiêu tăng khi mục tiêu nhỏ và xa. Nút hay dùng phải to và gần chỗ mắt và chuột đang ở; nút phá hủy đặt xa nút chính. Đây là căn cứ cho vùng bấm 40×40.
  Nguồn: P. M. Fitts, *Journal of Experimental Psychology* (1954); I. S. MacKenzie, *Human-Computer Interaction* (1992).
- **Xử lý tiền chú ý (preattentive).** Màu, kích thước, hướng, vị trí được mắt bắt trong dưới khoảng 250 ms, trước khi đọc. Chỉ dùng chúng cho điều cần thấy ngay (nợ quá hạn, chuyến chờ kiểm). Dùng cho trang trí thì chúng mất tác dụng báo hiệu.
  Nguồn: A. Treisman, G. Gelade, *Cognitive Psychology* (1980); C. Ware, *Information Visualization: Perception for Design*, bản 4 (2020).
- **Mù banner và thói quen.** Người dùng bỏ qua vùng trông giống quảng cáo hay thông báo lặp lại. Cảnh báo thật không nên dùng cùng kiểu với thông báo thường ngày.
  Nguồn: J. P. Benway, D. M. Lane (1998); NN/g.

## 4. Thị giác và bố cục

- **Gestalt.** Gần nhau thì được hiểu là cùng nhóm (gần), giống nhau thì cùng loại (tương đồng), cùng khung thì cùng nhóm (vùng chung), thẳng hàng thì liên quan (liên tục). Phần lớn việc nhóm thông tin nên làm bằng **khoảng cách**, không bằng card và viền.
  Nguồn: M. Wertheimer (1923); S. Palmer, I. Rock (1994) về vùng chung; tổng hợp ở Ware (2020).
- **Thứ bậc thị giác.** Mỗi màn có một thứ nhìn đầu tiên, rồi thứ hai, thứ ba (bước 2 của skill). Phân cấp bằng cỡ, đậm, vị trí; không bằng nhiều màu.
- **Chữ.** Độ dài dòng chữ thân khoảng 45–75 ký tự; thang chữ có bước rõ ràng; chữ số cùng độ rộng trong bảng.
  Nguồn: R. Bringhurst, *The Elements of Typographic Style* (bản 4, 2012); M. Butterick, *Practical Typography*.
- **Bảng số liệu.** Số căn phải, chữ căn trái, tiêu đề cột căn theo nội dung cột. Giảm kẻ dọc. Hàng xen màu nhạt hoặc kẻ ngang mảnh để mắt không lạc dòng.
  Nguồn: S. Few, *Show Me the Numbers*, bản 2 (2012), chương về thiết kế bảng.

## 5. Biểu đồ và trang tổng quan

- **Thứ hạng chính xác khi đọc.** Mắt so vị trí trên cùng trục chính xác nhất, rồi đến độ dài, góc và độ dốc, diện tích, sau cùng là màu và độ đậm. Nên so số tiền bằng cột hay thanh chung trục. Tránh bánh tròn, tránh so bằng diện tích.
  Nguồn: W. S. Cleveland, R. McGill, "Graphical perception", *JASA* (1984); J. Heer, M. Bostock, CHI 2010 (lặp lại thí nghiệm).
- **Tỷ lệ mực-dữ liệu.** Bỏ phần mực không mang dữ liệu: khung, nền, lưới đậm, 3D.
  Nguồn: E. Tufte, *The Visual Display of Quantitative Information*, bản 2 (2001).
- **Biến thị giác.** Mỗi biến (vị trí, kích thước, độ đậm, sắc màu, hình dạng) hợp với một loại dữ liệu. Ví dụ, thang tuổi nợ là dữ liệu có thứ tự nên dùng một màu đậm nhạt dần, không dùng nhiều sắc màu.
  Nguồn: J. Bertin, *Sémiologie graphique* (1967).
- **Câu thần chú tìm thông tin:** xem tổng thể trước, rồi phóng to và lọc, chi tiết khi cần. Đây là căn cứ cho Tổng quan → bấm khách → Sổ khách.
  Nguồn: B. Shneiderman, "The eyes have it", IEEE VL 1996.
- **Trang tổng quan** nhìn một lượt phải trả lời được câu hỏi chính. Không trang trí, không đồng hồ đo.
  Nguồn: S. Few, *Information Dashboard Design*, bản 2 (2013).

## 6. Người dùng trên 40 tuổi

- Từ khoảng 40 tuổi mắt cần nhiều sáng hơn và nhìn gần kém hơn (lão thị). Độ nhạy tương phản giảm. Tốc độ xử lý và trí nhớ làm việc giảm dần, nhưng kiến thức chuyên môn và vốn từ nghiệp vụ giữ vững hoặc tăng. Hệ quả cho thiết kế:
  - chữ to và tương phản cao: thang bắt đầu từ 13, chữ thân 15–16, nền và chữ đạt WCAG AA;
  - ít mục cùng lúc, luồng từng bước rõ, không bắt nhớ giữa các màn;
  - dùng đúng từ nghiệp vụ người dùng đã quen, vì đó là điểm mạnh của họ;
  - mục tiêu bấm to, khoảng cách giữa nút đủ rộng, không phụ thuộc rê chuột;
  - không đổi chỗ thứ quen chỉ để "làm mới".
  Nguồn: A. D. Fisk, S. J. Czaja, W. A. Rogers, N. Charness, J. Sharit, *Designing for Older Adults*, bản 3 (2020); T. Salthouse, "The processing-speed theory of adult age differences in cognition", *Psychological Review* (1996); [W3C WAI — Older Users and Web Accessibility](https://www.w3.org/WAI/older-users/).

## 7. Khả năng tiếp cận

- **WCAG 2.2 mức AA** là sàn: tương phản 4,5:1 cho chữ thường, 3:1 cho chữ lớn và thành phần giao diện; focus luôn thấy và không bị che (2.4.11); mục tiêu bấm tối thiểu 24×24 (2.5.8); không chỉ dùng màu để truyền nghĩa (1.4.1).
  Nguồn: [W3C, WCAG 2.2](https://www.w3.org/TR/WCAG22/) (2023).
- Skill `design:accessibility-review` có sẵn trong phiên để audit một màn theo WCAG.

## 8. Phương pháp kiểm với người dùng

- **5 người thử tìm được phần lớn lỗi dùng của một luồng.** Thử nhỏ, lặp nhiều vòng hiệu quả hơn một lần thử lớn. Phù hợp bước cuối của `UX-NEN-01`: người dùng thật đi hết luồng.
  Nguồn: J. Nielsen, T. Landauer, INTERACT/CHI 1993; lưu ý giới hạn ở J. Lewis (1994).
- **Đo, không đoán:** tỷ lệ xong việc, thời gian, số lỗi, mức hài lòng (ISO 9241-11:2018 định nghĩa usability bằng hiệu quả, hiệu suất, hài lòng). Đây chính là M1–M5.
- **Nghĩ to (think-aloud):** cho người dùng vừa làm vừa nói mình đang nghĩ gì. Cách này phát hiện chỗ họ hiểu sai, tức lỗi loại nhầm hiểu ở mục 1.
  Nguồn: K. A. Ericsson, H. A. Simon, *Protocol Analysis* (1993).

## Đọc thêm theo thứ tự ưu tiên

1. Norman, *The Design of Everyday Things* (2013): phản hồi, ánh xạ, lỗi.
2. Krug, *Don't Make Me Think*, bản 3 (2014): thực hành nhanh, kiểm với người dùng.
3. Few, *Show Me the Numbers* và *Information Dashboard Design*: bảng và tổng quan.
4. Fisk và cộng sự, *Designing for Older Adults* (2020).
5. Ware, *Information Visualization* (2020): nhận thức thị giác.
6. Yablonski, *Laws of UX*, bản 2 (2024), và [lawsofux.com](https://lawsofux.com/): tóm tắt các luật tâm lý kèm nguồn gốc.
