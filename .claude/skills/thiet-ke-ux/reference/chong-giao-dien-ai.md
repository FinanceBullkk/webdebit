# Chống giao diện "trông như AI làm"

Đọc ở bước 3 (trước khi chốt thị giác) và bước 5 (khi xem bản render) của [skill](../SKILL.md). Đây là bản tóm tắt, viết lại theo bối cảnh web công nợ, từ bốn nguồn thực hành công khai (đọc ngày 25/11/2026):

- [pbakaus/impeccable](https://github.com/pbakaus/impeccable) (Apache-2.0): chế độ "Operate" cho màn làm việc, danh sách những gì nên bỏ, các bước kiểm sau khi dựng.
- [anthropics/skills — frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) (Apache-2.0): các dấu hiệu khiến người xem nhận ra trang do mô hình sinh ra.
- [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines) (MIT): checklist tương tác, focus, form, số liệu.
- [OneRedOak/claude-code-workflows — design-review](https://github.com/OneRedOak/claude-code-workflows/tree/main/design-review) (MIT): review trên bản đang chạy trước, đọc code sau.

Không cài các bộ này vào repo. Impeccable có trình chạy tự tải file thực thi, không dùng. Bộ kho mẫu `ui-ux-pro-max` đã xem và loại: nó gợi ý phong cách mới, còn web này đã có hướng và token.

## Vì sao giao diện do mô hình làm trông "AI"

Mô hình chọn giá trị phổ biến nhất ở mỗi chỗ. Từng chỗ đều hợp lý, nhưng ghép lại thành một bộ mặc định ai cũng nhận ra, và mỗi lần sửa một màn lại sinh thêm vài giá trị mới. Ngày 25/11/2026 CSS giao diện có khoảng 1.800 chỗ màu viết thẳng, 92 cỡ chữ ngoài thang, hơn 400 chỗ bo góc tự đặt (xem `scripts/css-tokens-baseline.json`). Vì vậy:

1. Đừng hỏi "chỗ này trông ổn không" mà hỏi "chỗ này đã có token hay mẫu ở màn khác chưa". Có rồi thì dùng lại, kể cả khi mình nghĩ ra cái đẹp hơn.
2. Mỗi quyết định thị giác phải nói được nó mang thông tin gì. Viền, nền, số thứ tự, nhãn, màu đều là thông tin; thêm vào chỉ để "cho có" là nhiễu.

## Web công nợ là màn "làm việc", không phải trang giới thiệu

Người dùng mở web để làm xong việc: tìm khách, đọc sổ, ghi phiếu, kiểm chuyến. Theo tinh thần chế độ Operate:

- Bố cục, điều hướng và nút là loại người dùng đã quen (bảng, tab, nút, ô nhập, menu chọn). Không chế điều khiển "độc đáo".
- Sự chăm chút thể hiện ở độ chính xác: lưới thẳng, khoảng cách đều, thang chữ rõ, số căn phải cùng độ rộng chữ số. Không thể hiện bằng hiệu ứng.
- Màu có việc thật: trạng thái (cảnh báo, cần làm, khách dư), chọn, chuỗi số liệu. Một màn xám chỉ có một màu nhấn chưa phải là tiết chế mà là chưa xong.
- Trang giới thiệu hay landing page mới cần "cá tính". Màn sổ thì không.

## Những thứ bỏ, trừ khi nói được lý do nghiệp vụ

Bố cục:
- Chia trang thành các card giống hệt nhau (biểu tượng + tiêu đề + đoạn chữ). Card là thùng chứa lười; card lồng card luôn sai.
- Khối "số lớn + nhãn nhỏ + vài số phụ + màu nhấn" đặt ở đầu mọi trang. Tổng quan cần trả lời câu hỏi của người dùng, không cần trưng số.
- Nhãn chữ nhỏ (thường IN HOA, giãn chữ) đặt phía trên tiêu đề. Tiêu đề tự đủ nghĩa.
- Số thứ tự 01 / 02 / 03 khi nội dung không thật sự là các bước.
- Hộp thoại chặn màn cho việc không cần chặn. Ở web này hộp thoại dành cho thao tác đụng tiền cần xác nhận trước → sau.

Bề mặt:
- Viền màu một bên hộp (border-left dày) để đánh dấu trạng thái. Thay bằng viền đủ bốn cạnh, nền nhạt hoặc chữ/biểu tượng đứng đầu dòng. `lint:tok` đếm loại này.
- Chữ gradient, kính mờ, bóng màu không lệch (quầng sáng), bóng khối không mờ.
- Một bóng mờ xám giống nhau dưới mọi khối và một bán kính bo cho mọi thứ bất kể cấp bậc.
- Hiệu ứng trượt hoặc mờ dần khi mỗi khối xuất hiện, hover đổi dáng trên mọi card. Chuyển động chỉ dùng để trả lời thao tác của người dùng (mở, bung, xác nhận) và cho thấy cái gì vừa đổi.
- Nhấn một từ trong tiêu đề bằng màu hay nghiêng khác.

Chữ:
- Chữ IN HOA cho nhãn, tiêu đề cột. Người trên 40 tuổi đọc chữ thường nhanh hơn.
- Chữ mô tả dài giải thích giao diện ("Bảng này cho thấy…"). Nếu cần giải thích thì giao diện chưa rõ.
- Lời máy móc hoặc tên kỹ thuật. Dùng từ trong từ điển giao diện (mục 4.5 [audit UX](../../../../docs/ux-audit-2026-10-31.md)).

## Kiểm trên bản render (bước 5)

Gom các mục dưới đây vào một lần xem, sửa hết những gì thấy rồi mới xem lại:

- **Token:** `node scripts/check-css-tokens.js` xanh. Nếu PR có sửa màn cũ thì mức trần phải giảm (`--update`).
- **Tương phản:** chữ thân và placeholder từ 4,5:1, chữ lớn từ 3:1. Chữ phụ trên nền màu lấy sắc của nền đó, không dùng xám chung.
- **Khoảng cách:** nhóm chặt bên trong, cách xa giữa các nhóm. Phía trên tiêu đề rộng hơn phía dưới. Đọc giá trị tính ra trong DevTools, đừng đoán bằng mắt.
- **Chữ:** thang 13 / 14 / 15 / 16 / 18 / 22 / 28. Dòng chữ thân không quá khoảng 75 ký tự. Số tiền `tabular-nums`, căn phải.
- **Trạng thái:** hover, focus bàn phím, disabled, đang tải, trống, lỗi, mất mạng, chữ dài, tên có chữ Hán.
- **Phần trình duyệt tự vẽ:** viền focus, màu bôi chọn chữ, thanh cuộn, chữ số trong bảng vẫn mang mặc định của trình duyệt nếu không chỉnh. Đây là dấu hiệu rẻ nhất cho thấy màn được dựng có chủ ý.
- **Chữ trên nút:** động từ + đối tượng ("Ghi phiếu thu"). Câu lỗi nói rõ sai gì và cách sửa.
- **Tìm thấy trong vài giây:** mọi yêu cầu của nhiệm vụ có mặt và thấy được ở khung 1280×560.

## Checklist tương tác (rút từ Vercel, chỉ giữ phần hợp web này)

- Mọi luồng làm được bằng bàn phím. Viền focus luôn thấy, dùng `:focus-visible`. Thanh dính trên đầu không che phần tử đang focus.
- Vùng bấm tối thiểu 24px; web này đặt 40×40 cho nút chính (mục 4.4 audit UX). Trên điện thoại 44px, ô nhập cỡ chữ từ 16px để iPhone không tự phóng to.
- Không chặn dán vào ô nhập. Không tắt phóng to của trình duyệt.
- Nút đang gửi hiện trạng thái đang làm và chặn bấm lặp. Giữ nguyên nhãn cũ, thêm chỉ báo.
- Lỗi form hiện cạnh ô sai, focus vào ô sai đầu tiên. Không xóa dữ liệu người dùng đã nhập khi báo lỗi.
- Trạng thái lọc, tab, tháng đang xem nằm trên URL để tải lại hay gửi link vẫn đúng chỗ.
- Thao tác phá hủy cần xác nhận hoặc hoàn tác. Thao tác tiền luôn cho thấy trước → sau.
- Số liệu dùng `tabular-nums`. Ngày `dd/mm/yyyy`. Không làm tròn tiền trong bảng chi tiết.
- Tôn trọng `prefers-reduced-motion`.

## Cách review một màn (theo design-review)

1. Mở bản chạy thật (bản thử trên máy hoặc `hao` chỉ đọc), ở khung 1280×720 có thanh cuộn. Đi hết luồng chính như người dùng, trước khi đọc code.
2. Đi lại bằng bàn phím. Thử dữ liệu dài, trống, lỗi.
3. Thu hẹp còn 390px nếu màn đó dùng trên điện thoại.
4. Mới đọc diff: token, cấu trúc, trùng lặp.
5. Báo theo mức: **Chặn** (sai tiền, mất dữ liệu, không làm xong việc), **Nên sửa** (chậm, khó tìm, trái token), **Gợi ý**. Mỗi mục kèm ảnh hoặc dòng code, mô tả vấn đề và tác động, không ra lệnh cách sửa.
