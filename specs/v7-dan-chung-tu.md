# Dán chứng từ vào phiếu thu

Trạng thái: ĐÃ CHỐT luồng ([`CHUNG-TU-01`](../docs/decisions.md#chung-tu-01), người dùng duyệt bản xem 29/10/2026); đề xuất kỹ thuật lưu ảnh còn chờ duyệt migration. Phạm vi chốt trong chat cùng ngày: người dùng chọn làm "dán chứng từ" trước, chưa tích hợp Zalo/WeChat. Bước này **chỉ đính ảnh**, web chưa đọc số trên ảnh. Bản xem HTML (dữ liệu giả): [`preview/mockups/dan-chung-tu`](../cong-no-web-handoff/preview/mockups/dan-chung-tu/index.html). Người dùng giao Claude làm bản xem, không qua Penpot (29/10/2026). Người dùng duyệt bản xem 29/10/2026 ("Duyệt, làm tiếp").

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập phiếu thu (danh tính Tailscale, `V7-ID`), trên 40 tuổi, màn 1280x720 ([UX](../docs/ux-guidelines.md)).

**Bối cảnh thật (người dùng trả lời 29/10/2026):**

- Khách báo đã trả tiền qua chat Zalo hoặc WeChat, gửi **ảnh chuyển khoản ngân hàng Việt Nam** (VND) hoặc **ảnh chuyển khoản tiền tệ** (RMB qua Alipay, WeChat Pay hoặc ngân hàng Trung Quốc).
- Mỗi ngày có khoảng **10–30 khoản thu**.
- Hiện người nhập nhìn ảnh trong chat rồi gõ tay vào Sheet. Ảnh chỉ nằm lại trong chat. Muốn tra lại "phiếu này căn cứ vào đâu" thì phải lục chat.

**Luồng dán khi ghi phiếu mới:**

1. Trong Zalo hoặc WeChat, người nhập bấm chuột phải vào ảnh rồi chọn **Sao chép** (hoặc lưu ảnh về máy).
2. Trên web, mở sổ khách rồi tới hàng nhập phiếu ở tháng đang mở (như hiện nay, `SO-GON-01`/`SO-GON-02`).
3. Người nhập bấm **Ctrl+V** ở bất kỳ đâu trên trang sổ khách, kéo thả file ảnh vào trang, hoặc bấm nút **"Chọn ảnh…"**. Ảnh vào phiếu đang nhập, trừ khi khung xem ảnh của một phiếu đã ghi đang mở thì vào phiếu đó. Dán chữ vào ô nhập vẫn như bình thường.
4. Ảnh hiện **phóng to cạnh ô nhập** để vừa nhìn vừa gõ. Không phải chuyển cửa sổ qua lại.
5. Người nhập gõ ngày trả, hình thức, số tiền, tham chiếu như hiện nay. Với ảnh RMB: **số tiền là VND thực nhận**, còn số RMB và tỷ giá ghi ở ô tham chiếu (`V7-CSM` (2)). Ảnh không thay cho việc ghi số.
6. Người nhập bấm Ghi. Phiếu được ghi trước, ảnh lưu ngay sau (một lần bấm). Phiếu đã ghi có biểu tượng 📎, bấm vào thì xem ảnh.

**Luồng đính ảnh vào phiếu đã ghi:** bấm nút 📎 của phiếu chưa hủy (phiếu chưa có ảnh hiện "＋📎") để mở khung xem, rồi Ctrl+V hoặc kéo thả. Dùng khi khách gửi ảnh sau, hoặc khi người nhập muốn bổ sung chứng từ cho phiếu cũ, kể cả phiếu ở tháng khóa: ảnh không đổi số tiền.

**Gỡ ảnh nhầm:** bấm "Gỡ" trên ảnh. Bắt buộc ghi lý do. Ảnh không bị xóa hẳn, chỉ ẩn khỏi phiếu và ghi Lịch sử (giống hủy phiếu).

**Cảnh báo (không chặn):**

- Ảnh này đã đính vào phiếu khác (cùng nội dung file) → "Ảnh này đã đính vào phiếu P… của khách … ngày …". Người nhập vẫn ghi được, vì có trường hợp một ảnh chuyển khoản trả cho hai sổ. Cách hiện giống cảnh báo trùng tham chiếu hiện có.
- Phiếu ghi không có ảnh: không cảnh báo. Ảnh là tùy chọn.

**Bị chặn:** file không phải ảnh (PNG, JPEG, WebP), ảnh quá lớn sau khi nén, mỗi phiếu tối đa 5 ảnh, phiếu đã hủy (chỉ xem ảnh, không đính thêm). Câu thông báo ngắn, nói cách làm tiếp.

**Ngoài phạm vi bước này:** web đọc số tiền và ngày từ ảnh; dán nhiều ảnh cho nhiều khách một lượt; Zalo OA, WeChat; đối chiếu sao kê ngân hàng. Các việc này làm sau khi bước này chạy ổn.

## Đầu ra

Trên sổ khách, người nhập dán ảnh chuyển khoản vào phiếu thu khi ghi hoặc sau khi ghi. Mọi người vào app đều xem được ảnh từ phiếu (người dùng chốt 29/10/2026). Số tiền, phân bổ và số dư không đổi gì so với hiện nay.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Phần | Hiện có | Còn thiếu |
|---|---|---|
| Phiếu thu | `sokhach.receipt` (`date`, `method`, `amount_vnd`, `reference`); `record_receipt`, `edit_receipt_meta`, `void_receipt` trong `tools/migrations/2026-10-21-v7-csm.sql` | Bảng ảnh gắn phiếu |
| API | `POST /api/v7/receipts`, `/receipts/meta`, `/receipts/void` trong `web/v7_ledger_api.py`. Thân request giới hạn `MAX_BODY` = 64 KB | Đường tải ảnh riêng có giới hạn lớn hơn và đường xem ảnh (GET) |
| Cảnh báo trùng | `record_receipt` trả `duplicate_reference` | `duplicate_attachment` theo SHA-256 của file |
| Giao diện | Hàng nhập phiếu và ô tham chiếu trong `preview/so-khach-v7-ui.js` (`referenceLine`, `renderLine`), danh sách phiếu bên phải (`SO-GON-02`) | Nhận Ctrl+V/kéo thả, khung xem ảnh cạnh ô nhập, biểu tượng 📎 trên phiếu |
| Lịch sử | Mọi thao tác ghi người làm, trước → sau (`V7-CSM`) | Sự kiện "đính ảnh" và "gỡ ảnh (lý do)" |
| Sao lưu | `tools/v7_backup.py` dùng `pg_dump` | Ảnh cần nằm trong phạm vi sao lưu |

**Thiết kế kỹ thuật** (ĐÃ CODE ở PR backend, chưa triển khai; migration hỏi người dùng trước khi merge và chạy):

- Bảng `sokhach.receipt_image` (mã, khách, phiếu, `sha256`, kiểu file, `data bytea` ≤ 2 MiB, event tạo, lý do và event gỡ) trong PostgreSQL, nên `v7_backup.py` sao lưu luôn ảnh. Trigger chặn xóa và chặn sửa, trừ một lần ghi lý do gỡ. App và reader không đọc bảng trực tiếp, chỉ qua hàm.
- Hàm: `attach_receipt_image` và `remove_receipt_image` (qua `_begin_command`/`_finish_command`: kiểm phiên bản sổ, chống gửi lặp, tăng phiên bản; mỗi lệnh một event `receipt_image`/`receipt_image_remove` trong Lịch sử); `list_receipt_images`, `get_receipt_image`, `find_receipt_image` (đọc, cấp cho cả reader). Không đụng `record_receipt` hay đường ghi tiền.
- Ghi phiếu kèm ảnh là **hai bước**: `record_receipt` như cũ, rồi đính từng ảnh vào mã phiếu vừa nhận. Mất mạng giữa chừng thì phiếu đã ghi đúng tiền, chỉ thiếu ảnh; giao diện báo "Phiếu đã ghi, ảnh chưa lưu" để dán lại. Chọn cách này để không sửa hàm ghi tiền.
- API: `POST /api/v7/receipts/images` (JSON có `data_base64`, thân tối đa 3 MiB chỉ ở đường này), `POST /api/v7/receipts/images/remove`, `GET /api/v7/receipt-images?customer=`, `GET /api/v7/receipt-image?customer=&id=` (trả JSON base64), `GET /api/v7/receipt-images/find?sha256=` (cảnh báo trùng trước khi ghi). Ảnh đi vào psql qua stdin (vượt giới hạn tham số dòng lệnh), chỉ sau khi kiểm là chữ base64.
- Kiểm hai lớp: API và DB đều kiểm kiểu file theo đầu file (PNG, JPEG, WebP), kích thước, tối đa 5 ảnh còn hiệu lực mỗi phiếu, cùng ảnh trong một phiếu (`IMAGE_DUPLICATE`). Cùng ảnh ở phiếu khác hoặc sổ khác trả `duplicates` để cảnh báo, không chặn.
- Trình duyệt nén ảnh trước khi tải (cạnh dài ≤ 2400 px, WebP 0,9). Giao diện cần thêm `img-src 'self' blob: data:` vào CSP của trang; việc này thuộc PR giao diện.

## Nguồn quyết định

- [`V7-CSM`](../docs/decisions.md#v7-csm) (2): ô tham chiếu không bắt buộc, chỉ ghi VND thực nhận.
- [`business-rules.md`](../docs/business-rules.md): chứng từ tiền không tự chứng minh thu đã xác minh.
- [`SO-GON-02`](../docs/decisions.md#so-gon-02): phiếu thu là danh sách riêng bên phải.
- [`SONG-SONG-01`](../docs/decisions.md#song-song-01): Sheet vẫn là sổ chính thức. Ảnh là phần thêm trên web, không thay đối soát.
- [`CHUNG-TU-01`](../docs/decisions.md#chung-tu-01): luồng và phạm vi đã chốt 29/10/2026.

## Hành vi và bất biến

- Ảnh **không** đổi số tiền, ngày, hình thức hay phân bổ của phiếu. Không có ảnh vẫn ghi được.
- Có ảnh không có nghĩa là tiền đã về. Không hiện chữ "đã xác minh".
- Không xóa hẳn ảnh qua giao diện. Gỡ ảnh bắt buộc lý do và ghi Lịch sử. Phiếu bị hủy vẫn giữ ảnh để tra.
- Ảnh là chứng từ ngân hàng của khách: **không** đưa vào Git, log, changelog, ảnh chụp test hay fixture. Fixture và test dùng ảnh giả do test tự tạo.
- Không gửi ảnh ra dịch vụ ngoài `hao`.

## Tiêu chí nghiệm thu

- [ ] Harness PostgreSQL: đính, gỡ (thiếu lý do thì bị chặn), cảnh báo trùng SHA-256, phiếu hủy không đính thêm, giới hạn 5 ảnh, dọn ảnh tạm. Số dư và phân bổ trước và sau khi đính ảnh như nhau.
- [ ] API: từ chối file không phải ảnh, file quá giới hạn, `Content-Type` giả. Ảnh trả về có header an toàn.
- [ ] Frontend: Ctrl+V, kéo thả và nút "Đính ảnh" đều chạy. Có bàn phím và focus, mất mạng giữa chừng thì báo rõ phiếu đã ghi nhưng ảnh chưa lưu, bấm Ghi hai lần không ra hai phiếu.
- [ ] Người dùng tự dán ảnh thật trên bản thử rồi xác nhận.
- [ ] Giao diện khớp bản xem HTML đã duyệt.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`). Mockup: bản xem HTML đã duyệt 29/10/2026. Review: opus (chạm đường ghi phiếu).
- PR 1 (backend): một migration mới trong `cong-no-web-handoff/tools/migrations/`, `cong-no-web-handoff/tools/v7_backend_functions.sql`, `specs/v7-backend/schema-draft.sql` nếu cần đồng bộ, `cong-no-web-handoff/web/v7_ledger_api.py`, test Python và harness PostgreSQL liên quan, runbook triển khai. Hỏi người dùng trước khi merge và trước khi chạy trên `hao`.
- PR 2 (giao diện): trang live sổ khách (`so-khach-v7-*.js`, `so-khach-v7-live.html`) theo bản xem, test browser.
- Cấm: đổi luật tiền, phân bổ, khóa tháng; gửi ảnh ra ngoài `hao`; ảnh thật trong repo; dependency mới.

## Hoàn tác

Revert PR. Nếu migration đã chạy thì bảng ảnh là bảng riêng: tắt giao diện là đủ, không đụng `sokhach.receipt` hay số tiền.

## Bằng chứng

Chưa có. Spec chỉ đọc code trên `main` ngày 29/10/2026.

## Câu hỏi mở

Người dùng trả lời ba câu hỏi ngày 29/10/2026:

- Một ảnh đính vào phiếu ở hai sổ (khách trả gộp): **cho phép, chỉ cảnh báo** (người dùng: "ok theo bạn").
- Ai được xem ảnh: **mọi người vào app**, như `V7-ID` hiện nay.
- Ảnh gốc hay ảnh nén: người dùng để Claude chọn. Claude chọn **chỉ giữ bản nén, nén nhẹ**: cạnh dài tối đa 2400 px (đủ độ phân giải gốc của ảnh chụp màn hình điện thoại, chữ số nhỏ vẫn rõ), WebP hoặc JPEG chất lượng 0,9, tối đa 2 MB mỗi ảnh. Không giữ bản gốc, vì sẽ gấp đôi dung lượng mà không đọc rõ hơn.
