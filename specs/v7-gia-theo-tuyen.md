# Ghi giá theo tuyến ở Việc cần làm (GIA-TUYEN-01)

Trạng thái: **ĐỀ XUẤT** (Claude, 13/11/2026, vai chuyên gia UX theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md); người dùng chọn tối ưu luồng "người nhập cuối ngày" trước). Không đổi luật giá, API, DB hay quyền. Chưa có số mã quyết định trong `docs/decisions/` vì người dùng chưa đi thử.

## Người dùng và luồng (bước 1)

**Ai, khi nào:** người nhập, cuối ngày, ở tab Việc cần làm → Dọn chi tiết → mở một sổ → nhóm "Chưa giá". Sau khi bỏ Sheet sổ nợ, giá là đầu vào người nhập gõ hằng ngày ([checklist chuyển hẳn](../docs/chuyen-han-checklist.md) mục "Giá, phụ phí"; B2: máy chép giá Sheet 363 lần từ 1/11, khoảng 30 giá mỗi ngày).

**Vấn đề, đo trên `hao` 13/11/2026 (chỉ đọc):**

| Đo | Số |
| --- | ---: |
| Chuyến chưa giá ở Việc cần làm | 93 chuyến, 20 sổ |
| Số tuyến (nơi đi → nơi đến) khác nhau trong từng sổ, cộng lại | 40 |
| Thêm shipper vào khóa nhóm | 43 |
| Sổ có bảng giá (có giá gợi ý) | 3/20 |
| Chuyến chưa giá có chuyến đã có giá cùng tuyến trong sổ | 63/93 |
| Cặp chuyến liền nhau cùng tuyến có cùng đơn giá | 54/79 |
| Tuyến × tháng có hơn một đơn giá | 13/52 |
| Đọc lại một sổ 26 chuyến sau mỗi lần ghi | ≈ 2,2 giây |

Hôm nay mỗi chuyến là một lần gõ giá, một lần bấm "Ghi giá", một lần bấm "Xác nhận", rồi chờ đọc lại cả sổ. Một sổ 26 chuyến trên 9 tuyến là 26 vòng như vậy. Giá cùng tuyến thường giống nhau, nhưng không phải luôn luôn (một phần tư tuyến × tháng có hai giá), nên không được ghi mù cả nhóm.

**Luồng mới:**

1. Mở sổ ở Dọn chi tiết. Nhóm "Chưa giá" ghi "26 chuyến · 9 tuyến".
2. Tuyến có từ 2 chuyến sửa được trở lên có **một hàng tuyến** đứng đầu: số chuyến, tên tuyến (shipper khi cùng tuyến có nhiều shipper), khoảng ngày; ở vùng thao tác là nút giá gần nhất cùng tuyến nếu có ("Giá gần nhất 45 tr · 28/10"), một ô giá và nút "Ghi giá n chuyến". Các chuyến của tuyến nằm ngay dưới, mỗi chuyến vẫn có ô giá và nút "Ghi giá" riêng như cũ.
3. Gõ giá vào ô của hàng tuyến thì giá đó điền xuống ô của từng chuyến trong tuyến (như kéo giá xuống trên Sheet). Chuyến nào giá khác thì sửa ô của chuyến đó; chuyến nào chưa muốn ghi thì xóa trống ô. Ô chuyến người dùng đã tự sửa thì gõ lại ô tuyến không đè.
4. Bấm nút giá gần nhất thì giá đó vào ô tuyến (rồi điền xuống như bước 3). Máy không tự điền giá này: người phải bấm. Ô tuyến chỉ điền sẵn khi mọi chuyến của tuyến có cùng giá gợi ý của bảng giá.
5. Bấm "Ghi giá n chuyến" (n = số ô chuyến có giá hợp lệ): hàng tuyến đổi thành dòng xem lại "3 chuyến 45 tr · 1 chuyến 47 tr · nợ 679 → 861,5 tr" kèm "khác giá gần nhất 45 tr (28/10/2026)" khi có giá khác giá gần nhất, và hai nút Xác nhận / Thôi (tiêu điểm vào Thôi).
6. Xác nhận: máy ghi lần lượt từng chuyến bằng lệnh ghi giá đang có, lệnh sau dùng phiên bản sổ lệnh trước trả về; xong thì đọc lại sổ một lần. Chuyến đã ghi rời khỏi danh sách.

**Bị chặn:** chuyến tháng khóa (`editable` sai) không vào hàng tuyến, vẫn "Mở trong sổ". Dòng phí lẻ (không container, có phụ phí) không phải chuyến chưa giá (`is_missing_price` của server) nên không vào nhóm "Chưa giá": ghi đơn giá vào đó là cộng nợ sai. Ô có chữ sai định dạng có viền đỏ và lời nhắc tại ô; nút ghi nhóm tắt khi có ô sai hoặc không có ô hợp lệ. Trong lúc dòng xem lại đang hiện hay đang ghi, ô giá các chuyến của tuyến bị khóa: số trên dòng xem lại là số được ghi; muốn đổi thì bấm Thôi.

## Đầu ra

Một sổ nhiều chuyến cùng tuyến ghi giá bằng một lần gõ và hai lần bấm cho cả tuyến; chuyến khác giá vẫn sửa riêng được trước khi ghi; người nhìn thấy nợ trước → sau và chỗ khác giá gần nhất trước khi ghi; ghi xong có Hoàn tác cả tuyến.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- Chi tiết sổ: `GET /api/v7/ledger` → `trips[]` có `id`, `container`, `event_date`, `origin`, `destination`, `status`, `unit_price_vnd`, `other_fee_vnd`, `editable`. Chuyến chưa giá là `unit_price_vnd == null && status == 'confirmed'` (như hiện nay).
- Giá gần nhất: chuyến `confirmed` cùng sổ, cùng `origin`, `destination` và shipper, có `unit_price_vnd` lớn hơn 0, ngày chuyến lớn nhất (chỉ chuyến web, chưa đọc dòng sổ gốc). Chỉ là chữ gợi ý và nút điền; không phải nguồn giá ([`BANG-GIA-01`](../docs/decisions/bang-gia-01.md) giữ: giá có nguồn là bảng giá, Sheet hoặc người gõ).
- Giá gợi ý của bảng giá: `/api/v7/price-table/status` như cũ, vẫn điền sẵn ô từng chuyến. Ô tuyến điền sẵn khi mọi chuyến của tuyến có cùng giá gợi ý.
- Tiền chuyến sau khi có giá: `SoKhachV7Model.tripAmount` (như nút ghi một chuyến).
- Nhập giá: `InboxTable.parseMillions` (triệu đồng, tối đa sáu số lẻ, BigInt ra nguyên đồng).

## Giao tiếp frontend–backend (bước 5)

Không thêm API. Mỗi chuyến một lệnh `POST /api/v7/trips/price` `{customer_id, expected_version, idempotency_key, trip_id, unit_price_vnd, other_fee_vnd}` (giữ `other_fee_vnd` đang có của chuyến). Lệnh trả `version` mới (`_finish_command`); lệnh sau dùng số đó. Lệnh lỗi (ví dụ `STALE_LEDGER` khi máy hay người khác vừa ghi sổ) thì dừng, báo "Ghi được k/n chuyến rồi dừng" kèm câu lỗi, đọc lại sổ. Mất mạng: giữ nguyên thân lệnh và khóa của chuyến chưa rõ; "Thử lại" gửi đúng lệnh đó, server trả lại kết quả đã lưu nếu lệnh đã chạy (`_begin_command`), nên không ghi trùng.

## Hành vi và bất biến

- VND nguyên; ô trống là bỏ qua chuyến đó, không phải 0. Giá phải lớn hơn 0.
- Không ghi chuyến tháng khóa, chuyến chờ kiểm, dòng sổ gốc.
- Mỗi chuyến một dòng Lịch sử với người làm (lệnh đang có), phân bổ lại phiếu thu theo nợ cũ trước như khi ghi từng chuyến.
- Không có lệnh gộp: ghi được một phần là trạng thái thật, báo rõ phần đã ghi.

## Tiêu chí nghiệm thu

- [x] `npm run check` xanh.
- [x] Browser (`test-viec-can-lam-gia-tuyen-browser.js`, fixture, 1265×560 = 1280 trừ thanh cuộn): hàng tuyến chỉ hiện khi tuyến có ≥ 2 chuyến sửa được, tách shipper, tên tuyến dài xuống dòng chứ không cắt; gõ ô tuyến điền xuống ô chuyến chưa tự sửa; ô đã sửa giữ; xóa trống một ô thì nút ghi đếm bớt; xóa ô tuyến thì ô chuyến trống cả sau khi vẽ lại; ô sai viền đỏ; xem lại nêu nợ trước → sau và chỗ khác giá gần nhất; đang xem lại thì ô của tuyến khóa; xác nhận gửi đúng số lệnh, đúng giá và phụ phí từng chuyến, phiên bản nối tiếp; Hoàn tác đúng khóa và phiên bản; lỗi giữa chừng dừng và báo k/n; mất mạng (lệnh chưa tới server, hoặc server đã ghi mà mất phản hồi) thử lại cùng khóa, mỗi chuyến ghi một lần; chuyến tháng khóa, dòng phí lẻ không vào nhóm; nút giá gần nhất điền ô tuyến; Enter/Esc.
- [x] Xem ảnh render (dữ liệu giả) ở 1280 có thanh cuộn, chữ rộng kiểu Linux và 390.
- [ ] Bước 8: người nhập (hoặc chủ dự án) ghi giá một tuyến thật trên `hao`, kiểm Lịch sử và tổng nợ.

## Phạm vi agent

- Agent: claude
- Review: opus (ghi tiền)
- Được sửa:
  - `cong-no-web-handoff/preview/viec-can-lam.js`
  - `cong-no-web-handoff/preview/viec-can-lam-table.js`
  - `cong-no-web-handoff/preview/viec-can-lam.css`
  - `cong-no-web-handoff/preview/test-viec-can-lam-gia-tuyen-browser.js`
  - `specs/v7-gia-theo-tuyen.md`
- Ngân sách diff: 700 dòng (nâng từ 400 sau review: phần lớn là test)
