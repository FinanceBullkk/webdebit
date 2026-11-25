# PHIEU-WEB-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Từ 1/12/2026 mọi phiếu thu nhập trên web ([`WEB-CHINH-01`](web-chinh-01.md)), nên khung **Ghi phiếu thu** của Sổ khách phải ghi được mọi kiểu phiếu đang gặp trên Sheet, cho cả login người dùng ([`QUYEN-01`](quyen-01.md)). Phiên kiểm toàn bộ website giao 25/11/2026; Claude đặt cách làm dưới đây (ĐỀ XUẤT, không đổi luật tiền, không thêm hàm SQL).

1. **Phiếu không rõ ngày trả.** Khung có ô đánh dấu "Không rõ ngày trả". Đánh dấu thì ô ngày tắt, người chọn tháng khách trả (12 tháng tới tháng hiện tại, không chọn sẵn để không ghi nhầm tháng). Phiếu ghi:
   - **ngày** = ngày cuối tháng đó, không sau hôm nay (giờ VN) — đúng luật phiếu Sheet không ngày chủ sổ chốt 4/11/2026 (`month_end` ở `web/v7_sheet_fix.py`, xem [`MAY-DOI-SOAT-01`](may-doi-soat-01.md)). Hàm phía trang là `CongNoFormat.symbolicDate`; hai bên chạy chung bộ ca ở `cong-no-web-handoff/tests/golden/ngay-tuong-trung.json`, lệch luật là test đỏ;
   - **tham chiếu** = chữ người gõ + đuôi ` (ngày tượng trưng)`, đuôi mà Bảng thu, ngày trả thật và chữ tham chiếu trên sổ đã nhận ra ([`BANG-THU-01`](bang-thu-01.md)). Không gõ gì thì chữ là "Không rõ ngày" (server cắt khoảng trắng hai đầu, đuôi đứng một mình sẽ mất dấu cách và thôi khớp);
   - bước xem lại ghi rõ "(ngày tượng trưng)". Biết ngày thật sau thì sửa ngày ở dòng phiếu như phiếu thường.
   Cấn trừ cần ngày cụ thể: hình thức CẤN TRỪ không đi cùng "Không rõ ngày trả".

2. **Một lần chuyển cho nhiều sổ.** Nút "Chia cho nhiều sổ…" của khung mở khung riêng, mang sẵn chữ đang gõ. Người nhập ngày, hình thức (trừ CẤN TRỪ), tổng tiền khách chuyển, tham chiếu, rồi chia: sổ đang mở đứng đầu, thêm sổ đang hoạt động bằng ô tìm (sổ lưu trữ, sổ đã có trong danh sách không hiện).
   - **Chặn ở trang** khi tổng các phần khác tổng chuyển (nói rõ còn thiếu hay thừa bao nhiêu), phần trống hay 0 đ, một sổ hai lần, ít hơn hai sổ, ngày sau hôm nay.
   - **Mỗi phần là một phiếu riêng ở sổ đó**: một lệnh `record_receipt` mỗi sổ như phiếu thường (FIFO trong sổ đó, người làm, Lịch sử), cùng ngày, hình thức và tham chiếu. Khóa chống ghi trùng riêng từng sổ, đặt lúc xem lại.
   - **Không có giao dịch chung nhiều sổ** (không thêm hàm SQL, không đổi đường ghi tiền). Trang gửi lần lượt; lệnh lỗi thì dừng, bước xem lại ghi từng sổ "Đã ghi PH-…", "Không ghi được" kèm câu của máy chủ, "Chưa rõ đã lưu" hay "Chưa ghi". "Ghi tiếp" chỉ gửi phần chưa ghi, bằng đúng khóa cũ, nên phần máy chủ đã lưu mà trang chưa nhận được không thành hai phiếu. Sổ đổi từ lúc xem lại thì trang đọc phiên bản mới và gửi lại một lần cùng khóa.
   - Bước xem lại hiện còn nợ trước → sau của từng sổ, và **cảnh báo** (không chặn) khi tham chiếu đã có ở phiếu web khác trong tháng của ngày trả, đọc từ Bảng thu. Hai lần chuyển cùng chữ "CK" là thường, nên chỉ hỏi người.
   - **Đóng khi còn phiếu chưa ghi thì hỏi trước, không bỏ lần chia dở** (review độc lập 25/11/2026: bỏ rồi chia lại với khóa mới sẽ ghi lần hai các sổ đã lưu). "Đóng, ghi sau" giữ nguyên các khóa, bấm lại "Chia cho nhiều sổ…" là về đúng bước kết quả. Nút "Bỏ N phiếu chưa ghi" chỉ có khi không còn phiếu "chưa rõ đã lưu".
   - Phần bị từ chối hay chưa gửi sửa được số tiền ngay ở bước kết quả. Tổng mọi phần vẫn phải bằng tổng chuyển. Phần đổi số nhận khóa mới, phần đã ghi giữ nguyên. Phần "chưa rõ đã lưu" không sửa được, chỉ gửi lại đúng lệnh cũ.
   - Thiếu tham chiếu thì bước xem lại nhắc ghi mã giao dịch ngân hàng (không chặn).
   - Phiếu không rõ ngày không đi đường này: chia nhiều sổ cần ngày cụ thể.

Các mục sau (dán nhiều phiếu một lần, ghi phiếu từ ảnh Thu chi) thêm vào file này theo từng PR.

## Ngày / nguồn

25/11/2026, phiên kiểm toàn bộ website giao việc theo `WEB-CHINH-01`. Đo chỉ đọc trên `hao` cùng ngày: từ 1/10/2026 có 104 phiếu, đều từ login quản lý, trong đó 6 phiếu ngày tượng trưng; login người dùng chưa ghi phiếu nào.

## Hiệu lực và giới hạn

ĐỀ XUẤT của Claude trong phạm vi việc được giao; mục 1 và 2 không đổi DB, API hay quyền. ĐÃ KIỂM CHỨNG bằng test trang (`test-cong-no-format.js`, `test-so-khach-v7-model.js`, `test-so-khach-v7-entry-browser.js`, `test-so-khach-v7-split-browser.js`) và unittest `test_v7_sheet_fix.py`. Người nhập đi thử trên `hao` là bước còn lại.
