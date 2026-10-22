# Quyết định còn hiệu lực (tóm tắt từ bộ nhớ Claude, đã loại số liệu và tên khách)

Nguồn sống là `docs/decisions.md` và `docs/business-rules.md`; khi lệch thì các file đó thắng. Đây chỉ là bản định hướng.

**Nghiệp vụ**
- Opening lấy từ **sổ gốc** (Google Sheet), không dùng replay 13/10. Giao dịch lịch sử trong opening không cộng lại.
- Một người nhập và ghi sổ, không có người duyệt thứ hai (V6, V6-DB). Mọi thao tác ghi tiền ghi người làm.
- Mỗi tháng có ổ khóa; tháng khóa sửa bằng dòng điều chỉnh, hủy phiếu bắt buộc lý do (V7-SO). Thu mới trừ nợ cũ trước.
- NULL không phải 0, trừ phụ phí trống của chuyến đã có đơn giá (V7-BE). Cờ NO_BASELINE, thiếu giá, chênh 600đ chỉ tô màu.
- Cấm ghi phiếu có `posting_date` sau hôm nay (giờ VN), chặn ở hàm ghi sổ (luật FUTURE-01).
- Mặt hàng gắn theo sổ khách (một sổ một mặt hàng); sầu riêng cảng/bộ là phương thức vận chuyển, dùng để lọc.
- Cấn trừ giữa hai sổ: ghi cả hai sổ một lệnh, chặn khi sổ nguồn không đủ dư, vẫn có "Ngoài sổ".
- Chuyến cũ không có booking: giữ nợ, bỏ truy vết.

**Chuyển đổi**
- Chạy song song (SONG-SONG-01): Sheet là sổ chính thức tới ngày chuyển hẳn; thay đổi trên Sheet sau mốc phải dán lên web; đối soát theo tổng từng khách; chuyển hẳn sau ít nhất một lần cuối tháng khớp. Mốc là bản xuất Sheet mới nhất nạp vào V7 ngày bắt đầu song song.
- Nhập chuyến theo lô, một lô một khách (dán từ Sheet, 10–50 container/ngày); guardrail là trạng thái trên dòng, không thêm bước thao tác.

**Cách làm việc**
- Claude được trao quyền tự quyết điều phối (21/10/2026); mọi quyết định ghi vào `decisions.md` kèm người chốt. Thao tác khó đảo ngược trên `hao`/Sheet/dữ liệu thật vẫn cần backup, thử trên bản sao và báo người dùng.
- PR xếp chồng: retarget PR con sang nhánh đích trước khi merge cha, rồi kiểm `git merge-base --is-ancestor`.
- Mockup/UX: spec phải có "Người dùng và luồng" và "Đối chiếu dữ liệu" trước mockup.

**Trạng thái (22/10/2026):** V7 đã triển khai lên `hao` (mốc `clean-v2` 21/10, nâng 22/10), chưa bắt đầu chạy song song chính thức; điều kiện còn thiếu ở `docs/song-song-checklist.md`. Không suy trạng thái live từ tài liệu cũ.
