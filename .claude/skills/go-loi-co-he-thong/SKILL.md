---
name: go-loi-co-he-thong
description: Quy trình gỡ lỗi trong repo webdebit: tìm nguyên nhân gốc trước khi sửa. Dùng khi gặp lỗi, test đỏ (local hoặc CI), số tiền/số dư lệch, Deploy hao đỏ hoặc hành vi lạ — trước khi đề xuất bất kỳ cách sửa nào.
---

**Mục đích:** sửa đúng gốc, không vá triệu chứng. Chưa xong bước 1 thì chưa đề xuất sửa.

**Phạm vi file:** bước 1–3 chỉ đọc và chạy lệnh chẩn đoán; bước 4 sửa trong phạm vi nhiệm vụ. Không chạy DDL, loader hay ghi DB thật để chẩn đoán.

**Các bước**
1. **Tìm nguyên nhân gốc.**
   - Đọc hết thông báo lỗi và stack trace, ghi file:dòng, mã lỗi.
   - Tái hiện được chắc chắn; không tái hiện được thì thu thêm dữ liệu, không đoán.
   - Xem thay đổi gần đây: `git log`, `git diff`, phụ thuộc, cấu hình, môi trường.
   - Hệ nhiều tầng (UI → API V7 → PostgreSQL, CI → `npm run check` → bộ test): ghi dữ liệu vào/ra ở mỗi ranh giới, chạy một lần để thấy tầng nào hỏng rồi mới đào tầng đó.
   - Giá trị sai nằm sâu: lần ngược ai truyền giá trị đó tới khi gặp nguồn; sửa ở nguồn.
2. **So mẫu.** Tìm đoạn code tương tự đang chạy đúng trong repo, liệt kê mọi khác biệt dù nhỏ, đọc hết mẫu tham chiếu chứ không đọc lướt.
3. **Giả thuyết.** Ghi một câu: "Gốc là X vì Y". Thử bằng thay đổi nhỏ nhất, một biến mỗi lần. Sai thì lập giả thuyết mới, không chồng thêm bản sửa. Không hiểu thì nói rõ chỗ chưa hiểu.
4. **Sửa.**
   - Viết test tái hiện lỗi trước (đỏ), rồi mới sửa (xanh).
   - Một bản sửa cho đúng gốc đã tìm; không kèm "tiện tay" refactor.
   - Kiểm lại theo skill `kiem-chung-truoc-khi-bao-xong`.
   - Đã thử 3 bản sửa mà không được: dừng, nghi thiết kế chứ không thử bản thứ 4; báo người dùng và bàn hướng khác.

**Bẫy đã biết của repo (kiểm trước khi kết luận là lỗi code)**
- Worktree thiếu `.venv`: unittest/viewer đỏ giả (thiếu `tzdata`), ruff FAIL giả. Đặt `VIRTUAL_ENV` và `WEBDEBIT_PYTHON`.
- Test đỏ quanh 17:00 UTC hoặc ngày 1 hằng tháng: ranh giới tháng giờ VN; truyền `today_month`, ghim `page.clock`.
- `ERR_NO_BUFFER_SPACE` trên runner Windows: lỗi mạng của runner, chạy lại job.
- Test mất mạng bằng Playwright: Chrome tự gửi lại GET khi socket bị cắt một lần; dùng `page.route` abort `{times: 1}`.
- Số tiền lệch: đối chiếu quy tắc ở `AGENTS.md` (NULL không phải 0, pending ngoài số dư, thu theo nợ cũ trước, opening không cộng lại lịch sử) trước khi nghi phép tính.

**Hoàn thành khi:** nêu được nguyên nhân gốc kèm bằng chứng (lệnh, output, dòng code); có test đỏ → xanh; `npm run check` xanh. Nếu kết luận là lỗi môi trường hoặc bên ngoài: ghi lại đã điều tra gì, xử lý phù hợp (thử lại, thông báo lỗi rõ) và nói thẳng là chưa sửa được gốc.

**Điều cấm:** đề xuất sửa trước bước 1; sửa nhiều chỗ cùng lúc rồi chạy test; tắt, skip hoặc nới test để cho xanh; tuyên bố đã sửa khi chưa chạy lại đúng triệu chứng ban đầu.

Phỏng theo skill `systematic-debugging` của [obra/superpowers](https://github.com/obra/superpowers) (MIT, © Jesse Vincent).
