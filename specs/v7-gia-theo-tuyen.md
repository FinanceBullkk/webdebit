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
2. Tuyến có từ 2 chuyến sửa được trở lên có **một hàng tuyến** đứng đầu: tên tuyến, số chuyến, khoảng ngày, giá lần trước cùng tuyến nếu có ("lần trước 45 tr · 28/10"), một ô giá và nút "Ghi giá n chuyến". Các chuyến của tuyến nằm ngay dưới, mỗi chuyến vẫn có ô giá và nút "Ghi giá" riêng như cũ.
3. Gõ giá vào ô của hàng tuyến thì giá đó điền xuống ô của từng chuyến trong tuyến (như kéo giá xuống trên Sheet). Chuyến nào giá khác thì sửa ô của chuyến đó; chuyến nào chưa muốn ghi thì xóa trống ô. Ô chuyến người dùng đã tự sửa thì gõ lại ô tuyến không đè.
4. Nút "Dùng 45" cạnh giá lần trước điền giá đó vào ô tuyến. Máy không tự điền giá lần trước: người phải bấm.
5. Bấm "Ghi giá n chuyến" (n = số ô chuyến có giá hợp lệ): hàng tuyến đổi thành dòng xem lại "6 chuyến 45 tr · 1 chuyến 47 tr · nợ 679 → 994,0 tr" kèm "khác lần trước 45 tr" khi có giá khác giá lần trước, và hai nút Xác nhận / Thôi.
6. Xác nhận: máy ghi lần lượt từng chuyến bằng lệnh ghi giá đang có, lệnh sau dùng phiên bản sổ lệnh trước trả về; xong thì đọc lại sổ một lần. Chuyến đã ghi rời khỏi danh sách.

**Bị chặn:** chuyến tháng khóa (`editable` sai) không vào hàng tuyến, vẫn "Mở trong sổ". Ô có chữ sai định dạng thì báo ngay tại ô, không gửi gì. Nút ghi nhóm tắt khi không có ô hợp lệ.

## Đầu ra

Một sổ nhiều chuyến cùng tuyến ghi giá bằng một lần gõ và hai lần bấm cho cả tuyến; chuyến khác giá vẫn sửa riêng được trước khi ghi; người nhìn thấy nợ trước → sau và chỗ khác giá lần trước trước khi ghi.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- Chi tiết sổ: `GET /api/v7/ledger` → `trips[]` có `id`, `container`, `event_date`, `origin`, `destination`, `status`, `unit_price_vnd`, `other_fee_vnd`, `editable`. Chuyến chưa giá là `unit_price_vnd == null && status == 'confirmed'` (như hiện nay).
- Giá lần trước: chuyến `confirmed` cùng sổ, cùng `origin` và `destination`, có `unit_price_vnd`, ngày chuyến lớn nhất. Chỉ là chữ gợi ý và nút điền; không phải nguồn giá ([`BANG-GIA-01`](../docs/decisions/bang-gia-01.md) giữ: giá có nguồn là bảng giá, Sheet hoặc người gõ).
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

- [ ] `npm run check` xanh.
- [ ] Browser (fixture, 1280×560): hàng tuyến chỉ hiện khi tuyến có ≥ 2 chuyến sửa được; gõ ô tuyến điền xuống ô chuyến chưa tự sửa; ô đã sửa giữ; xóa trống một ô thì nút ghi đếm bớt; xem lại nêu nợ trước → sau và chỗ khác giá lần trước; xác nhận gửi đúng số lệnh, đúng giá từng chuyến, phiên bản nối tiếp; lỗi giữa chừng dừng và báo k/n; mất mạng thử lại cùng khóa; chuyến tháng khóa không vào nhóm; nút "Dùng" điền giá lần trước.
- [ ] Xem ảnh render (dữ liệu giả) ở 1280 có thanh cuộn.
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
- Ngân sách diff: 400 dòng
