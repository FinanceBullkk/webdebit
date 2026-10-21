# V7 backend — đường ghi sổ khách (ĐỀ XUẤT)

Trạng thái: **ĐỀ XUẤT** (Claude, 19/10/2026). Chưa là chính sách đã duyệt, chưa là migration, **không cho phép ghi tiền**. Spec này chỉ nói backend phải làm gì và phải chứng minh gì **trước khi** nối giao diện V7; không chạy DDL, không đụng `hao`, Sheet hay dữ liệu thật. Giao diện: [v7-so-khach-theo-sheet.md](v7-so-khach-theo-sheet.md). Nền: [business-rules](../docs/business-rules.md), [decisions](../docs/decisions.md), [P0 đường ghi](p0-write-path/README.md).

## 1. Hiện trạng (để khỏi hiểu nhầm)

| Mục | Trạng thái |
| --- | --- |
| Giao diện V7 | ĐÃ KIỂM CHỨNG ở mức bản thử trong tab, dữ liệu mẫu ẩn danh: `npm run test:unit` 32/32 (19/10/2026); người dùng đã tự đi các luồng và thấy ổn (chat 19/10/2026). |
| Model tiền V7 (`so-khach-v7-model.js`) | Chạy trong trình duyệt. Là **bản mẫu hành vi** để đối chiếu, không phải nơi tính tiền thật. |
| Backend, DB, đường ghi | **Chưa có.** Không API, không lưu. Gate P0 còn mở (ghi nguyên tử, idempotency, đồng thời, đảo, khóa kỳ). |
| Dữ liệu thật | Chưa thử. Mọi số là fixture. |

## 2. Phải quyết trước khi viết backend (CÒN MỞ — không chốt hộ)

Mỗi điểm dưới đây là chỗ V7 đang lệch hoặc chưa phủ quyết định đã chốt. Backend không được tự chọn.

1. **Khóa tháng — ĐÃ CHỐT (người dùng, 19/10/2026): nút ổ khóa từng tháng, thay quy tắc ngày 5 của V6.** Mỗi tháng có cờ mở/khóa; ai trong nhóm cũng đổi được; mặc định chỉ tháng hiện tại mở; **mở/khóa không ghi vào Lịch sử** (quyết định của người dùng, cân nhắc lại khi có kiểm toán). Tháng mở sửa đè, tháng khóa chỉ điều chỉnh. Cờ phải lưu phía server và đọc theo ngày/ trạng thái của server, không theo client. ĐÃ TRIỂN KHAI ở bản thử trong tab; backend chưa có.
2. **Phân bổ lại khi điều chỉnh — ĐÃ CHỐT (người dùng, 19/10/2026): phương án A theo V6-3d.** Khi điều chỉnh bắt đầu tính tiền, các phiếu chưa hủy được rải lại theo nợ cũ trước, xếp theo (ngày phiếu, mã phiếu); phiếu đã hủy giữ nguyên; hủy phiếu không phân bổ lại phiếu khác. Backend phải ghi vết cho mọi phiếu đổi tháng (trước → sau). ĐÃ TRIỂN KHAI ở bản thử trong tab; backend chưa có. CÒN MỞ: có chạy khi sửa đè giá và dán lô không (bản thử đang chạy).
3. **D04 — tiền dư/ứng trước.** V7 ghi phần dư thành dòng `ỨNG TRƯỚC` ở tháng cuối và số âm hiện trần. D04 (ứng trước giữa các sổ, hoàn tiền, tiền chưa phân bổ ở mức ghi sổ) vẫn mở; backend chưa được coi dòng ỨNG TRƯỚC là sổ cái. **Một phần đã chốt (người dùng, 19/10/2026): khách trả dư thì ghi trong sổ và hiện số âm.** Hoàn tiền, ứng trước giữa các sổ vẫn CÒN MỞ.
4. **Danh tính người thao tác (Q01).** Tailscale là điều kiện mạng, chưa có account/ACL; "ai" thao tác chưa xác định. Không có bước duyệt (V6), nhưng **vết điều chỉnh/hủy cần biết người**. **Hướng đã chốt (người dùng, 19/10/2026): mỗi người một danh tính Tailscale riêng; dùng danh tính Tailscale làm người thao tác.** CÒN MỞ: cách app đọc danh tính một cách tin cậy (không tin header client tự khai), quản lý ai được vào, thu hồi. **Cách xác minh: người dùng để sau (19/10/2026).**
5. **P0-02 phê duyệt theo phiên bản.** Q02 ghi "không còn áp dụng cho chuyến và khoản thu theo V6". Các spec P0 02/06 còn viết theo maker-checker và khóa kỳ; phải sửa theo V6 trước khi dùng làm tiêu chí.
6. **"Khoản thu chưa chắc"** ở đầu sổ chưa có định nghĩa (đang cố định 0).
7. Sáu điểm CÒN MỞ ở cuối spec giao diện V7 (sửa phiếu đã lưu, điều chỉnh cả tháng, lịch sử sửa, nhiều khách, tháng âm, danh mục hình thức) và hai giả định đã ghi ở "Câu hỏi mở" (thứ tự 7 cột dán; một dòng chờ lý do mỗi chuyến).

## 3. Hợp đồng đề xuất

**Nguyên tắc:** server là nơi duy nhất tính tiền. Client gửi **ý định + số người dùng gõ**; server kiểm, tính, ghi, trả kết quả. Client không gửi phân bổ, không gửi tổng, không gửi actor.

### 3.1 Dữ liệu
- **Chuyến**: mã cố định do server cấp (không dùng vị trí như `2026-03#0` của bản thử); khách, ngày nghiệp vụ (ngày xe nhập kho), container (không là khóa), hãng tàu, nơi đi/đến, đơn giá (`NULL` ≠ 0), phụ phí (`NULL` ≠ 0), nguồn. VND là số nguyên.
- **Điều chỉnh**: mã riêng, trỏ về chuyến, hiệu số có dấu, ghi chú tùy chọn, người, thời điểm. **Tính tiền ngay (người dùng, 19/10/2026: điều chỉnh không cần lý do).** Nhiều dòng cho một chuyến; hiệu số tính từ **giá hiện hành** (giá gốc + điều chỉnh đã có lý do).
- **Phiếu thu** `pid` + **dòng phân bổ** (một dòng mỗi tháng, tách dòng ỨNG TRƯỚC). Dòng chỉ-thêm; hủy = ghi nhãn hủy kèm lý do, ngày hủy, người, **không xóa, không sửa số**.
- **Vết** chỉ-thêm cho mọi thao tác: ai, lúc nào, trước → sau, lý do.

### 3.2 Lệnh
| Lệnh | Vào | Server làm |
| --- | --- | --- |
| Dán lô chuyến | khách, tháng mở, các dòng | Kiểm toàn lô (all-or-nothing), cấp mã, ghi |
| Sửa ô tháng mở | mã chuyến, trường, số mới | Sửa đè, ghi vết trước → sau |
| Điều chỉnh tháng khóa | mã chuyến, số đúng, ghi chú (tùy chọn) | Tính hiệu số từ giá hiện hành, ghi dòng điều chỉnh, tính tiền ngay, phân bổ lại thu, ghi lịch sử |
| Ghi thu | khách, ngày, hình thức, số tiền, khóa idempotency | Phân bổ nợ cũ trước, ghi phiếu + dòng phân bổ, trả bảng phân bổ để hiện dòng báo |
| Hủy phiếu | `pid`, lý do | Hủy cả phiếu mọi tháng; **không** phân bổ lại phiếu khác |

Mọi lệnh: một giao dịch nguyên tử (hoặc ghi đủ phiếu + dòng + vết, hoặc không gì cả); kiểm phiên bản sổ của khách (từ chối nếu client dựa trên bản đã cũ); khóa theo khách để hai lệnh ghi thu đồng thời không cùng tiêu thụ một khoản nợ; cùng khóa idempotency + cùng nội dung → trả kết quả cũ, cùng khóa + khác nội dung → từ chối.

### 3.3 Đọc
Một lệnh đọc trả sổ khách đã tính sẵn (từng dòng, từng tháng, tổng, đếm Chờ xử lý). Số trả ra là chuỗi chữ số, không số thực.

## 4. Quy tắc tiền backend phải tái lập

Lấy từ model V7 và bảng nghiệm thu giao diện; backend phải ra **cùng số** trên fixture, rồi ra số riêng trên dữ liệu bản sao.

- `tripAmount`: dòng phí lẻ (không container, không đơn giá, có phụ phí) = phụ phí và vẫn cộng; thiếu đơn giá = không cộng, không phải 0.
- Chuỗi tháng: nợ đầu kỳ + phát sinh + điều chỉnh đã có lý do − đã thu (không tính phiếu đã hủy).
- Ghi thu theo nợ cũ trước; phần dư thành ỨNG TRƯỚC; không phân bổ lại phiếu cũ.
- Hủy cả phiếu theo `pid`; hủy rồi ghi lại cùng số thì tổng nợ về như trước.
- Giữ cờ NO_BASELINE, chênh lịch sử 600đ và khoản thiếu giá (AGENTS.md); không dùng khớp tổng làm bằng chứng đủ nguồn.

## 5. Tiêu chí nghiệm thu (đều phải có bằng chứng riêng)

Chạy trên PostgreSQL thật **cô lập** theo harness của [next-task](p0-write-path/next-task.md) (container riêng, `--network none`, dữ liệu giả), không trên `hao`.

- [ ] **Golden:** fixture V7 qua backend cho tổng nợ 2.411.645.000; 11 dòng Cộng tháng khớp bảng spec giao diện; tháng 06.2026 là 1.381.510.000 và không thiếu giá; PH-101 gom 600.694.000 trải tháng 06 và 07.
- [ ] **Nguyên tử:** gây lỗi giữa chừng (sau khi ghi một dòng phân bổ) → không còn phiếu, dòng hay vết dở dang.
- [ ] **Idempotency:** gửi lại ghi thu cùng khóa → một phiếu; cùng khóa khác số tiền → bị từ chối.
- [ ] **Đồng thời:** hai ghi thu cùng khách chạy song song (hai kết nối, quan sát bằng `pg_blocking_pids`, không dùng `sleep`) → tổng đã trừ không vượt nợ; phần dư đúng một lần.
- [ ] **Sổ cũ:** lệnh dựa trên phiên bản cũ bị từ chối.
- [ ] **Hủy:** hủy cả phiếu nhiều tháng; không đổi phiếu khác; hủy hai lần bị từ chối; lý do rỗng bị từ chối.
- [ ] **Điều chỉnh:** hai lần liên tiếp cùng chuyến → hai dòng, tổng phát sinh = giá cuối, không cộng trùng; tính tiền ngay.
- [ ] **Không sửa đè:** không có đường nào làm đổi số tiền của dòng đã ghi (kể cả bằng quyền DB của ứng dụng).
- [ ] **Danh tính:** actor lấy từ phiên đăng nhập phía server; header/field tự khai bị bỏ qua (chỉ kiểm được sau khi Q01 chốt).
- [ ] **Số liệu:** VND nguyên, không `float`; `NULL` giữ nguyên là chưa biết.
- [ ] Người dùng tự đi lại các luồng trên bản nối backend **trên bản sao** và xác nhận.

## 6. Thứ tự đề xuất

1. Người dùng chốt mục 2.3–2.4 (ứng trước, danh tính); mục 2.1 và 2.2 đã chốt.
2. Sửa P0-02/P0-06 theo V6 — ĐÃ ghi chú "thay đổi theo V6/V7" ở đầu hai file (19/10/2026); viết lại tiêu chí chi tiết khi cài đặt.
3. Thiết kế lược đồ + lệnh trên bản nháp; review độc lập (không phải người viết) — bản nháp 1 tại [v7-backend/thiet-ke.md](v7-backend/thiet-ke.md) và `v7-backend/schema-draft.sql` (ĐỀ XUẤT, chưa review).
4. Harness PostgreSQL cô lập: test đặc tả (mục 5) viết **trước** mã.
5. Cài đặt đường ghi; chạy test; đối chiếu số với model V7 trên fixture.
6. Thử trên **bản sao** dữ liệu thật đã loại nhạy cảm, có quyền/gate riêng; không `hao` cho tới khi có gate triển khai riêng.

## 7. Phạm vi agent (khi được duyệt)

- Bố cục giao diện: ĐÃ CHỐT (người dùng, 19/10/2026). Spec backend này: **ĐỀ XUẤT**, chưa giao việc cài đặt.
- Cấm cho tới khi có gate riêng: DDL/import/deploy/submit lên `hao`, chạm Google Sheet, đưa dữ liệu thật hay capture vào repo, thêm bí mật, tự chọn các điểm ở mục 2.
- Review: người khác với người viết.

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
