# Sổ khách: một tháng trên màn hình, bảng co giãn theo bề ngang (UX bước 04)

Trạng thái: ĐỀ XUẤT (Claude, 1/11/2026). Bước 04 (giao diện) của [khung UX](../docs/decisions/ux-nen-01.md) cho màn Sổ khách. Người dùng gửi hai ảnh màn sổ một khách và bảo "UI đang không ổn". Claude chỉ ra 7 lỗi và đề xuất đưa [bản bấm thử "Sổ một tháng"](../cong-no-web-handoff/preview/mockups/so-khach-mot-thang/index.html) vào màn thật; người dùng chọn "Làm theo hướng này" (chat 1/11/2026). Quyết định: [`SO-GON-05`](../docs/decisions/so-gon-05.md).

## Lỗi trên ảnh (1/11/2026)

1. Bảng có bề ngang cố định (1.258 hoặc 1.696 px), nằm giữa màn, hai bên trống; cột shipper, nơi đi, nơi đến bị cắt "…".
2. Có hai chỗ chọn tháng: hàng chip trên và các thanh tháng bên dưới. Có tháng mở, có tháng gập, nên không rõ đang xem tháng nào.
3. Ba cột phụ phí riêng gần như toàn "–". Ô Khác có dòng thứ hai "1 khoản", làm hàng cao thấp không đều.
4. Cột thu bên phải là một khối trống dọc theo 40+ dòng chuyến.
5. Ba thanh chồng nhau trước khi tới số liệu, có chữ kỹ thuật ("tự tải mỗi 60 giây").
6. Ổ khóa trên mọi chip, số đỏ trên chip không có lời giải thích.
7. Thanh tháng gập chỉ có "Còn nợ cuối tháng", không thấy số đó từ đâu ra.

## Người dùng và luồng (bước 1)

**Người nhập, người xem** mở sổ một khách:

1. Thấy **một tháng**: tháng đang làm. Nếu tháng hiện tại chưa có gì thì là tháng gần nhất có số liệu. Mở từ Công nợ theo tháng, Đòi nợ (`?month=`) hay từ một việc chờ (`?loc=`) thì là tháng đó.
2. Đầu tháng có một dòng tóm tắt: **Nợ đầu tháng + Phát sinh − Đã thu = Còn nợ cuối tháng**, cạnh đó là trạng thái khóa (bấm để khóa/mở, vẫn hỏi lại) và Debit note.
3. Muốn xem tháng khác thì bấm chip tháng ở hàng trên. Hàng chip là chỗ chọn tháng duy nhất. Sổ đổi sang tháng đó và cuộn về đầu sổ.
4. Đổi ngày một chuyến sang tháng khác (hỏi lại như cũ): sổ đi theo dòng sang tháng mới, dòng tô vàng "Vừa chuyển từ T…". Tháng cũ giữ dòng mờ "đã chuyển sang tháng …" có Xem (sang tháng mới, tới đúng dòng) và Hoàn tác.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Cần | Có sẵn | Đổi |
| --- | --- | --- |
| Nợ đầu tháng, phát sinh, đã thu, còn nợ cuối | GET sổ, `months[]`: `prior_months_vnd`, `charges_vnd`, `received_vnd`, `end_of_month_vnd` (đang ở chữ rê chuột của thanh tháng) | Hiện thành dòng tóm tắt; số lấy nguyên từ GET, trang không cộng trừ |
| Chọn tháng | `so-khach-v7-month-ui.js`: `shown` (nhiều tháng mở), `showMonth(key)` mọi phần đã gọi trước khi tìm dòng | Một tháng được chọn; `showMonth` chọn tháng đó |
| Bề ngang | `so-khach-v7.css`: `.ledger-book` 1.258/1.696 px cố định; cột có bề rộng px | `.ledger-book` co theo màn (tối thiểu như cũ); cột giữ tỉ lệ nên cột chữ rộng ra |
| Ô Khác | `so-khach-v7-trips-ui.js`: số + `<small>n khoản</small>` | Chỉ còn số; "n khoản" vào chữ rê chuột và nhãn đọc màn hình |

## Không làm trong đợt này

- **Ẩn cột phụ phí trống:** ô cột riêng là chỗ gõ phụ phí (`PHU-PHI-01`), ẩn thì mất chỗ nhập.
- **Gộp "Nơi đi → Nơi đến", ngày dd/mm:** mỗi ô đang sửa được tại chỗ, gõ ngày theo dd/mm/yyyy. Đổi cần làm lại ô sửa, để đợt sau.
- **Gộp ba thanh đầu sổ (lỗi 5), giải thích số trên chip (lỗi 6):** đợt sau, cùng phần dính đầu trang ≤ 110px còn mở của `SO-GON-04`.

## Tiêu chí nghiệm thu

- [x] Mở sổ: chỉ một bảng tháng; không còn nút "Xem chi tiết"/"Thu gọn"; chip của tháng đó được tô.
- [x] Tháng mặc định: `?month=` > tháng của `?loc=` > tháng hiện tại có số liệu > tháng gần nhất có số liệu.
- [x] Bấm chip: đổi tháng, cuộn về đầu sổ; dòng tóm tắt đúng bốn số của GET.
- [x] Đổi ngày sang tháng khác: sổ sang tháng mới, dòng vàng; tháng cũ có dòng mờ; Xem chuyển tháng tới đúng dòng; Hoàn tác như cũ.
- [x] Màn 1280×560 và màn rộng: bảng chiếm hết bề ngang vùng sổ, tiêu đề cột thẳng hàng với cột của bảng tháng.
- [x] Ô Khác một dòng.
- [ ] `npm run check` xanh; người dùng đi luồng 1–4 trên `hao`.

## Đợt 2 (1/11/2026, [`SO-GON-06`](../docs/decisions/so-gon-06.md))

Sau đợt 1, người dùng nói "thấy vẫn chưa ổn" và chọn hai chỗ: ba thanh đầu sổ rối, cột thu tiền trống. Người dùng chọn phương án đề xuất cho cả hai.

- **PR A · Phiếu thu lên đầu tháng:**
  - bỏ ba cột thu khỏi khung cột của sổ live; chỗ của chúng trả cho cột chuyến, nên ở màn 1280 cột chữ cũng đủ chỗ;
  - khối "Tiền khách trả tháng …" ngay dưới thanh tháng: cùng các hàng phiếu như trước (phiếu web, khoản thu sổ gốc, cấn trừ, phiếu hủy gom một dòng); sửa ngày, hình thức, tham chiếu, ảnh 📎 như cũ;
  - tháng không có phiếu: một dòng "… : chưa có phiếu thu".
- **PR B · Một thanh việc:** việc cần làm bên trái; giờ Sheet, Làm mới, "Cài đặt ▾" bên phải.

Tiêu chí đợt 2:

- [x] Thanh tháng → khối phiếu thu → bảng chuyến; bảng chuyến rộng bằng vùng sổ; tiêu đề cột kết thúc ở Thành tiền.
- [x] Tháng không phiếu: một dòng chữ, không bảng trống.
- [x] Đầu sổ còn một thanh dưới thanh tên khách; cài đặt trong "Cài đặt ▾".
- [ ] `npm run check` xanh; người dùng xem lại trên `hao`.
