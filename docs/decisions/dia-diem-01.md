# DIA-DIEM-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Debit note in **tên tiếng Trung** kèm tên chuẩn chữ Latin cho nơi đóng hàng (LOADING PLACE / FROM), cảng đến và cửa khẩu (POD / TO / DESTINATION PORT). Chỉ đổi phần hiển thị trên chứng từ: dữ liệu sổ, khóa nhận chuyến và tiền không đổi.

1. **Danh mục cố định trong code** (`DN_PLACES`, `DN_PORTS` ở `preview/so-khach-v7-model.js`): tỉnh, huyện/thị kho hay gặp, cảng đến, cửa khẩu chuyến bộ. Mỗi mục có tên chuẩn, tên Trung và các cách ghi khác trên Sheet (`HONGKONG`, `KAOHSIUNG - TAIWAN`, `N-PORT KLANG`, `TÀ LÙNG (水口)`…). Tỉnh theo ranh giới trước 7/2025 cho khớp Sheet.
2. **Tên Trung lấy theo nguồn bên Trung**: Bộ Thương mại TQ (hướng dẫn đầu tư Việt Nam 2025) cho tỉnh và cặp cửa khẩu lớn; Baidu Baike cho huyện; chính quyền Quảng Tây và báo TQ cho cửa khẩu nhỏ. Hai cách viết thì lấy tên mục chính của Baidu (Phan Thiết 潘切, không 藩切; Hóc Môn 福门). Huyện chưa có nguồn Trung (Hớn Quản, Buôn Hồ, Cao Lãnh, Tân Châu) hoặc chữ Nôm hiếm máy không hiện được (Chợ Gạo, Cái Bè) chỉ in tên tỉnh.
3. **Cửa khẩu** in theo cặp tên kiểu văn bản bên Trung, bên Trung trước: `Ta Lung  水口—驮隆口岸`, `Lao Cai  河口—老街口岸`.
4. **Tên kho** (ví dụ `KIM CƯƠNG TB`, `CỬU LONG - BẾN TRE`) vẫn giữ chữ gốc và vẫn cảnh báo "ngoài danh mục" như trước; nếu đầu hoặc cuối tên là địa danh (tên đủ hoặc viết tắt TB, ĐQ, BP, VT, TG, PT, BD, DN, TN, LA, DT) thì kèm tên Trung của địa danh đó. Địa danh nằm giữa tên công ty (`KHO BINH THUAN PHAT`) không tính; `BT` không đoán vì vừa là Bến Tre vừa là Bình Thuận.
5. **Cách in**: PDF trang 1 `Shanghai  上海港`, trang chi tiết tên Trung xuống dòng dưới chữ nhỏ màu xám; Excel ô FROM/TO là `Dak Lak  多乐省`.

## Ngày / nguồn

10/11/2026, chat: người dùng hỏi tên địa điểm trên Sheet booking có kèm tiếng Trung không, nhờ tra tên chuẩn Việt + Trung, kiểm lại bằng nguồn bên Trung, cho ghi tab tra cứu `DIA_DIEM` trên Sheet CHAU_HAO ("ok apply"), rồi chọn "Làm PR" đưa tên Trung vào debit note. Cách in và quy tắc đọc tên kho do Claude quyết theo [`CLAUDE-ALL-01`](claude-all-01.md).

Đo trên Sheet cùng ngày (5.506 dòng cont cảng, 2.709 dòng cont bộ): cảng đến 100% có tên Trung; cửa khẩu 2.627/2.709 dòng; kho cont cảng 5.377/5.506 dòng (còn lại là `/`, T&T, HƯNG THỊNH… chưa rõ nơi).

## Hiệu lực và giới hạn

ĐÃ CHỐT. Triển khai theo lượt `Deploy hao` khi merge. CÒN MỞ: `THIÊN BẢO` có phải cùng cửa khẩu Thanh Thủy (天保 là bên Trung của Thanh Thủy) và `ĐÔNG HƯNG` có phải Móng Cái không, nên hai tên này chưa vào danh mục; `DAK MIN` có phải Đắk Mil; nơi của kho T&T, HƯNG THỊNH, TAM HUONG, KHO BINH THUAN PHAT. Thêm cảng hoặc kho mới là sửa danh mục bằng PR nhỏ.
