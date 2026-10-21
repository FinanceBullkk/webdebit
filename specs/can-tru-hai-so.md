# Cấn trừ giữa hai sổ

**Trạng thái:** sáu quyết định ĐÃ CHỐT (người dùng, 20/10/2026, chat). Các quy tắc còn lại là ĐỀ XUẤT, sẽ được duyệt cùng mockup. Mockup vòng 1 (ChatGPT, 20/10/2026) đã soát, **chưa duyệt**: người dùng yêu cầu làm vòng 2 theo [bản sửa vòng 2](can-tru-hai-so-mockup-vong-2.md). Chưa có code, chưa triển khai ở môi trường nào.

Spec này nối tiếp [V7 — sổ khách theo lối Sheet](v7-so-khach-theo-sheet.md) và [backend sổ khách V7](v7-backend-so-khach.md). Hai spec đó không đổi; spec này chỉ thêm một đường ghi.

## 1. Vấn đề

Ví dụ: sổ khách A đang dư 100.000.000 (số âm), sổ khách B đang nợ 50.000.000. Trên sổ tay ghi "cấn trừ 50 triệu từ A" ở phía B. Kết quả đúng: A còn dư 50.000.000, B hết nợ, tổng hai sổ không đổi.

Hiện tại V7 coi `CẤN TRỪ` chỉ là một trong bốn hình thức thu (`record_receipt`, nháp `tools/v7_backend_functions.sql` trên nhánh `codex/v7-opening-read`). Ghi ở B thì B giảm nợ; sổ A **không đổi**. Muốn đúng số phải ghi tay thêm một dòng điều chỉnh +50.000.000 ở A. Hai thao tác rời nhau, nên quên một bên hoặc hủy một bên là lệch, và không có gì báo.

| | Trước | Ghi đủ hai phía | Chỉ ghi ở B |
| --- | ---: | ---: | ---: |
| Sổ A | −100.000.000 | −50.000.000 | −100.000.000 |
| Sổ B | 50.000.000 | 0 | 0 |
| Tổng | −50.000.000 | −50.000.000 | −100.000.000 |

## 2. Quyết định

| # | Nội dung | Trạng thái |
| --- | --- | --- |
| 1 | Chọn `CẤN TRỪ` ở sổ được trả nợ thì phải chọn sổ lấy tiền. Danh sách gồm **mọi sổ đang dư tiền**; sổ khác của cùng khách lên đầu. Áp riêng cho cấn trừ; thay mặc định D04 "dư nằm lại trong sổ" ở đúng trường hợp này. | ĐÃ CHỐT (người dùng, 20/10/2026) |
| 2 | Số tiền lớn hơn số dư của sổ lấy tiền thì **chặn**, không cho sổ đó chuyển sang nợ. | ĐÃ CHỐT (người dùng, 20/10/2026) |
| 3 | Giữ lựa chọn **Ngoài sổ** cho cấn trừ không có sổ bên kia (khoản phải trả, USD…): chỉ trừ sổ đang ghi, đúng như V7 hiện nay. | ĐÃ CHỐT (người dùng, 20/10/2026) |
| 4 | Mockup tính năng này làm bằng HTML qua ChatGPT theo [bản đặt mockup](can-tru-hai-so-mockup-html.md), thay Penpot. Người dùng vẫn duyệt mockup trước khi code giao diện. | ĐÃ CHỐT (người dùng, 20/10/2026) |
| 5 | Sổ nhận bị trả quá nợ thì **cho phép**: phần thừa thành `ỨNG TRƯỚC` như ghi thu thường; khung xác nhận báo trước số âm của sổ nhận. | ĐÃ CHỐT (người dùng, 20/10/2026) |
| 6 | **Mỗi sổ một mã phiếu** theo dãy `PH-` riêng của sổ đó (ví dụ B `PH-021`, A `PH-013`); không dùng chung mã cho cặp. Dòng nào cũng ghi tên sổ bên kia để bấm sang. | ĐÃ CHỐT (người dùng, 20/10/2026) |
| 7 | Hủy cặp hỏi lý do **ngay trong bảng**, đúng cách hủy phiếu V7, không dùng hộp thoại. | ĐÃ CHỐT (người dùng, 20/10/2026) |
| 8 | Hai sổ ghi trong **một lệnh**: cả hai cùng ghi hoặc không ghi gì. | ĐỀ XUẤT |
| 9 | Hủy ở bên nào cũng **hủy cả cặp**, một lý do bắt buộc. | ĐỀ XUẤT |
| 10 | Phiếu `CẤN TRỪ` cũ (chuyển từ Sheet hoặc ghi trước khi có tính năng này) là **Ngoài sổ**. Không suy liên kết từ ghi chú, số tiền hay ngày trùng. | ĐỀ XUẤT, theo [business-rules](../docs/business-rules.md) |

## 3. Luồng thao tác

Người dùng đang mở sổ B (sổ được trả nợ), tháng hiện tại, dòng ghi thu còn trống.

1. **Gõ ngày trả, chọn hình thức `CẤN TRỪ`.** Ngay dưới ba ô ghi thu, trong khối TIỀN KHÁCH TRẢ, hiện thêm ô **Lấy từ sổ**, chưa chọn gì. Không thêm cột. Các hình thức khác không hiện ô này.
2. **Bấm ô Lấy từ sổ, chọn sổ A.** Danh sách mở ra, có ô gõ để lọc theo tên:
   - nhóm trên: sổ khác của cùng khách B, nếu đang dư;
   - nhóm dưới: sổ của khách khác đang dư, xếp theo tên A→Z;
   - dòng cuối, tách riêng: **Ngoài sổ (khoản phải trả, USD…) · chỉ trừ sổ này**.
   Mỗi sổ hiện: tên khách · mặt hàng · số dư hiện tại (số âm trần, như V6-5). Không có sổ đang ghi, sổ nợ, sổ bằng 0 hay sổ lưu trữ. Danh sách trống thì hiện câu "Không có sổ nào đang dư tiền" và vẫn còn dòng Ngoài sổ.
3. **Gõ số tiền rồi Enter.** Vượt số dư thì báo đỏ ngay tại ô, ghi đủ tên sổ: "Sổ Khách A · sầu riêng chỉ còn dư 30.000.000", không mở bước sau. Chưa chọn sổ thì báo: "Chọn sổ lấy tiền, hoặc chọn Ngoài sổ".
4. **Khung xác nhận** (chỉ với cấn trừ hai sổ): một câu "Cấn trừ 50.000.000 từ sổ Khách A · sầu riêng sang sổ Khách B · sầu riêng", rồi hai ô trước → sau: A `−100.000.000 → −50.000.000`, B `50.000.000 → 0`. Nút `Ghi cấn trừ` và `Quay lại`. Số tiền lớn hơn số B đang nợ thì vẫn cho ghi; ô của B hiện số âm và thêm một dòng "Sổ Khách B · sầu riêng sẽ còn −20.000.000".
5. **Kết quả:** sổ B có phiếu `CẤN TRỪ` 50.000.000 mang mã trong dãy của sổ B, dưới chữ hình thức ghi "từ Khách A · sầu riêng" (bấm mở sổ A). Sổ A có dòng `CẤN TRỪ` −50.000.000 mang mã tiếp theo trong dãy của sổ A, nằm trong khối TIỀN KHÁCH TRẢ của tháng ứng với ngày trả, dưới chữ hình thức ghi "sang Khách B · sầu riêng". Tên sổ bên kia **luôn hiện**, không cần rê chuột; tên dài thì xuống tối đa hai dòng. Ô ghi thu trống vẫn còn ở hàng kế tiếp để ghi phiếu sau, như V7. Dòng báo như ghi thu thường, thêm một câu về sổ bên kia.
6. **Hủy:** bấm ô **Số tiền trả** của dòng cấn trừ ở bên nào cũng được (bấm Ngày trả là sửa ngày, như V7). Dòng hỏi lý do hiện **ngay trong bảng**, đúng vị trí của V7 (sau các dòng chuyến, trước dòng vết và ô dán), có câu "Hủy cấn trừ ở cả hai sổ: PH-021 ở sổ Khách B · sầu riêng và PH-013 ở sổ Khách A · sầu riêng", ô lý do bắt buộc, nút `Hủy cả hai dòng` và `Bỏ qua` (như dòng hủy phiếu V7). Sau hủy, ở cả hai sổ: dòng gạch ngang, nhãn `ĐÃ HỦY`, dòng vết đặt đúng chỗ như hủy phiếu V7.

Chọn **Ngoài sổ** ở bước 2 thì bỏ bước 4, ghi như V7 hiện nay.

## 4. Quy tắc tiền và bất biến

- **Số dư sổ lấy tiền** = −(tổng còn nợ mọi tháng của sổ đó), chỉ tính khi tổng < 0. Cùng cách tính với số trên đầu sổ; giao diện không tự tính.
- **Chặn vượt dư** kiểm ở server, dưới khóa, tại lúc ghi. Sau đó sổ A thay đổi (thêm chuyến, sửa giá, hủy phiếu thu) mà chuyển sang nợ thì đó là nợ thật, hiện như thường.
- **Sổ nhận (B):** một phiếu thu hình thức `CẤN TRỪ`, trừ nợ cũ trước như mọi phiếu thu, có liên kết sang sổ nguồn. Cấn quá số nợ thì phần thừa thành `ỨNG TRƯỚC` ở tháng cuối, như `record_receipt`.
- **Mã phiếu:** mỗi bên lấy mã tiếp theo trong dãy `PH-` của chính sổ đó; mã không trùng trong một sổ (giữ ràng buộc hiện có). Hai dòng nối nhau bằng cặp, không bằng mã.
- **Sổ nguồn (A):** một khoản "cấn trừ đi" ở tháng của ngày trả. Khoản này **làm tăng** còn nợ của A đúng bằng số tiền, hiện ở khối TIỀN KHÁCH TRẢ với số âm, không hiện ở cột Thành tiền và không tính là phát sinh chuyến. Các phiếu thu của A được rải lại theo nợ cũ trước như khi có điều chỉnh (điều 9 của [V7](v7-so-khach-theo-sheet.md)), có ghi vết.
- **Tổng mọi sổ không đổi** sau khi ghi và sau khi hủy một cặp cấn trừ hai sổ.
- **Hủy cặp:** phía B theo quy tắc hủy phiếu V7 (không phân bổ lại phiếu khác). Phía A bỏ khoản "cấn trừ đi" rồi rải lại thu như khi điều chỉnh, nên tiền quay về thành dư. Sau hủy, cả hai sổ về đúng số trước khi cấn.
- **Sửa tại chỗ:** đổi ngày trả thì đổi cả hai bên. Không đổi hình thức hay sổ nguồn tại chỗ; muốn đổi thì hủy cặp rồi ghi lại. Số tiền không sửa, như phiếu thu V7.
- **Ngày trả** không được sau hôm nay (giờ Việt Nam). Hai bên cùng một ngày trả.
- **Lịch sử:** mỗi sổ một mục cho ghi, hủy, đổi ngày, nêu tên sổ bên kia; người thao tác như các lệnh V7 khác.

## 5. Hợp đồng backend (ĐỀ XUẤT cho Codex)

Codex chọn cách lưu, miễn đạt mục 4 và tiêu chí ở mục 6. Gợi ý theo nháp V7:

- Lệnh mới `record_offset(target_customer_id, target_version, source_customer_id, source_version, idempotency_key, date, amount_vnd)`. Ngoài sổ vẫn dùng `record_receipt` với `CẤN TRỪ`, không đổi.
- Khóa **hai** sổ theo thứ tự id tăng dần, kiểm cả hai version: số trước → sau người dùng đã xem phải đúng số được ghi; lệch thì trả lỗi để giao diện tải lại số và xác nhận lại.
- Lỗi có mã riêng: `OFFSET_SAME_BOOK`, `OFFSET_EXCEEDS_CREDIT` (trả kèm số dư hiện tại), `NO_BASELINE` ở bất kỳ sổ nào, `FUTURE_DATE`, `INVALID_VND`, `STALE_LEDGER`.
- Một khóa idempotency cho cả cặp: gửi lại cùng nội dung trả cùng kết quả; cùng khóa khác nội dung thì từ chối.
- Một bảng cặp (ví dụ `offset_pair`) giữ nguồn, đích, ngày, số tiền, trạng thái hủy; phiếu thu phía B và khoản "cấn trừ đi" phía A cùng trỏ về cặp, mỗi bên có mã `PH-` theo dãy của sổ mình. `v_outstanding_month`, `reallocate` và `get_ledger` của sổ nguồn tính khoản "cấn trừ đi".
- `void_offset` và đổi ngày gọi được từ bất kỳ bên nào, luôn tác động cả cặp trong một giao dịch.
- Đọc danh sách sổ nguồn: một hàm trả các sổ đang dư (trừ sổ đang ghi, sổ lưu trữ, sổ chưa có mốc mở), kèm số dư và version, nhóm cùng khách lên đầu.

### Hợp đồng đã cài trong nhánh CT-2SO (chưa kiểm Docker)

- `record_offset(target_customer_id bigint, target_version bigint, source_customer_id bigint, source_version bigint, idempotency_key text, date date, amount_vnd bigint) → jsonb`.
- `void_offset(customer_id bigint, expected_version bigint, other_version bigint, idempotency_key text, offset_pair_id bigint, reason text) → jsonb`.
- `edit_offset_date(customer_id bigint, expected_version bigint, other_version bigint, idempotency_key text, offset_pair_id bigint, date date) → jsonb`.
- Hai lệnh sau gọi từ bất kỳ sổ trong cặp: `expected_version` của sổ gọi, `other_version` của sổ còn lại. Retry từ bên kia được phép; hai version không nằm trong payload idempotency. Khóa idempotency thuộc cặp ID không thứ tự; đổi hướng với cùng khóa là `IDEMPOTENCY_CONFLICT`.
- Kết quả lệnh có `offset_pair_id`, `source_customer_id`, `target_customer_id`, `source_version`, `target_version`, `source_pid`, `target_pid`, `target_receipt`, `source_reallocated`. `target_receipt` giữ kết quả lệnh thu/hủy/sửa ngày V7; khi ghi có `overpayment_vnd` và `allocations` (`advance` là phần ứng trước).
- `list_offset_sources(target_customer_id bigint) → jsonb`: mảng `{customer_id, name, commodity, version, outstanding_vnd, available_credit_vnd}`, tiền là chuỗi nguyên. Tạm xếp tên theo `COLLATE "C"`, rồi ID; chưa có khóa cùng khách nên không chia nhóm.
- Lưu mới: `offset_pair` giữ nguồn/đích, FK phiếu nhận, mã nguồn, ngày, tiền, event nguồn tạo/sửa/hủy và lý do; `offset_command` giữ payload/kết quả theo cặp và khóa; `v_offset_outgoing` chỉ lấy khoản nguồn chưa hủy. Không đổi bảng/cột của công cụ nạp. Không tự nối phiếu cũ.
- `get_ledger` giữ mọi trường cũ; thêm `outgoing_offsets` (mã, ngày, số tiền âm, cặp, sổ đối ứng, trạng thái hủy), liên kết đối ứng trong `receipts`, tên/ID đối ứng trong `events`. Khoản nguồn nằm ở tiền trả âm (`received_vnd`), không cộng `charges_vnd`. FIFO dùng khoản nguồn như nhu cầu phân bổ tại tháng ngày trả.
- Lỗi chính: `OFFSET_SAME_BOOK`, `OFFSET_EXCEEDS_CREDIT` (JSON `DETAIL.available_credit_vnd`), `NO_BASELINE`, `FUTURE_DATE`, `INVALID_VND`, `STALE_LEDGER`, `IDEMPOTENCY_CONFLICT`. Lỗi bổ sung: `INVALID_COMMAND`, `CUSTOMER_NOT_FOUND`, `INVALID_DATE`, `OFFSET_SOURCE_ARCHIVED`, `OFFSET_NOT_FOUND`, `OFFSET_ALREADY_VOID`, `VOID_REASON_REQUIRED`, `NO_CHANGE`. Gọi lệnh sửa/hủy phiếu đơn với phiếu nhận đã nối cặp trả `OFFSET_PAIR_REQUIRED`.

Lý do cụ thể hóa: hợp đồng đề xuất chưa có chữ ký hủy/đổi ngày, version bên đối ứng, namespace idempotency và JSON đọc khoản nguồn. Đây là hợp đồng backend để kiểm; không duyệt giao diện, không cấp quyền ghi thật. Tất cả hàm nội bộ vẫn bị thu hồi quyền `EXECUTE` như V7 hiện có.

## 6. Tiêu chí nghiệm thu

DB test trên bản sao, không chạm `hao`:

1. A −100.000.000, B 50.000.000, cấn 50.000.000 → A −50.000.000, B 0, tổng không đổi; mỗi sổ một mục Lịch sử.
2. Cấn 120.000.000 khi A dư 100.000.000 → `OFFSET_EXCEEDS_CREDIT`, không sổ nào đổi, version không tăng.
3. Gây lỗi sau khi đã ghi phía B → rollback, không sổ nào đổi.
4. Hai lệnh đồng thời cùng lấy từ A (dư 100.000.000, mỗi lệnh 60.000.000) → đúng một lệnh thành công.
5. Hai lệnh chéo nhau (A→B và B→A) chạy cùng lúc → không deadlock.
6. Lặp lại cùng khóa → cùng kết quả, không ghi thêm; cùng khóa khác số tiền → từ chối.
7. Hủy từ phía A, rồi làm lại và hủy từ phía B → mỗi lần cả hai sổ về đúng số trước khi cấn; phiếu thu khác của B không đổi phân bổ.
8. Đổi ngày từ một bên → cả hai bên cùng ngày mới, phân bổ hai sổ ghi vết.
9. Đổi hình thức phiếu cấn trừ hai sổ tại chỗ → bị từ chối.
10. Ngoài sổ → chỉ B đổi, như `record_receipt` hiện nay.
11. Danh sách sổ nguồn: không có sổ đang ghi, sổ nợ, sổ bằng 0, sổ lưu trữ; sổ cùng khách đứng trước.
12. Ngày trả sau hôm nay (giờ Việt Nam) → `FUTURE_DATE`.
13. Phiếu `CẤN TRỪ` cũ không có liên kết sau migration.
14. Mã phiếu: sổ A đang có `PH-012` thì dòng cấn trừ đi nhận `PH-013`; sổ B nhận mã tiếp theo của sổ B; không trùng mã trong mỗi sổ.
15. B nợ 50.000.000, cấn 70.000.000 từ A dư 100.000.000 → A −30.000.000, B −20.000.000 với dòng `ỨNG TRƯỚC` 20.000.000; tổng không đổi.

Giao diện (sau khi mockup được duyệt): kiểm trình duyệt ở 1280×720, đi đủ sáu bước của mục 3 và trạng thái lỗi; giao diện không tự cộng trừ tiền. Đọc số tiền theo bộ đọc ba kiểu số đã có của V7; **không** chép cách đọc số của file mockup (bỏ mọi ký tự không phải chữ số, nên `−5.000.000` thành `5.000.000`). Mockup được duyệt lưu vào `cong-no-web-handoff/preview/mockups/can-tru-hai-so/index.html` làm mốc.

## 7. Ngoài phạm vi, CÒN MỞ

- **Cách nhận "cùng khách"** giữa các sổ: V7 hiện một dòng TONG = một sổ, chưa có khóa nhóm khách. CÒN MỞ: dùng khóa nào. Chưa có khóa thì tạm xếp mọi sổ theo tên A→Z, không đoán cùng khách.
- Hoàn tiền và chuyển dư không qua cấn trừ (D04).
- Một lần cấn từ một sổ sang nhiều sổ: ngoài phạm vi, làm nhiều lần.
- Chứng cứ, tham chiếu chứng từ cho cấn trừ (D05/D06), ngoại tệ, tỷ giá.
- Danh tính người thao tác (Q01).
- Trang tổng các sổ: không đổi bố cục.
