# Khối "Sheet cần sửa": chỉ đúng ô lỗi trên Sheet, dựng lại vùng ô quanh nó

Trạng thái: ĐỀ XUẤT (Claude, 16/11/2026), đợt 3 của [KIEM-TAB-01](v7-kiem-tab-truoc-khi-ghi.md). Hướng (bản dựng lại vùng ô, khoanh ô lỗi) đã được người dùng duyệt qua phiên điều phối 16/11/2026; bố cục cụ thể dưới đây là ĐỀ XUẤT chờ xem bản dựng. Chưa code UI.

## 1. Bài toán

**Người dùng và bối cảnh.** Chủ sổ và người nhập liệu (phần lớn trên 40 tuổi), mở tab *Việc cần làm* vài lần mỗi ngày, màn thật 1280×560 hoặc iPhone 390px khi đang ở ngoài. Họ sửa Sheet bằng tay; web chỉ đọc Sheet (SONG-SONG-01).

**Câu hỏi họ mang tới, theo thứ tự:**
1. Tab của khách này có chỗ nào sai không, và sai ở ô nào?
2. Sửa thế nào cho đúng?
3. Sửa xong thì sao, bao giờ web đọc lại?

**Vấn đề hiện tại (bằng chứng 16/11/2026, đọc chỉ đọc trên `hao`).** Khi tab hỏng, máy chỉ ghi "Sheet có chỗ máy chưa đọc được" (khách `HELD`), hoặc từ đợt 1 bảng đối chiếu trả `blocked` mà màn chưa vẽ gì: người dùng không biết ô nào. Ca thật: sổ 79 ô tổng thu thiếu `=SUM(...)`, sổ 162 ô số dư bị gõ đè 0, sổ 239 tiền lệch một dòng. Mỗi ca phải mở Sheet dò tay, trong khi máy đã có đủ dữ liệu để chỉ đúng ô.

**Hành động chính:** xem ô sai và cách sửa, mở đúng ô trên Sheet. Phụ: đọc lại vùng ô sau khi sửa. Không có nút ghi nào trên khối này: web không ghi Sheet.

**Bước trong `UX-NEN-01`:** bước 3–4 (luồng thao tác, giao diện); mục tiêu M1 "hết ghi nhầm tiền" bằng cách chặn ghi khi tab hỏng và nói rõ vì sao.

**Điều đã biết:** `v7_tab_health` đã cho `findings` theo tab với ô (đợt 1); bản chụp 15 phút chỉ có giá trị đã tính, không có công thức, màu, ô gộp. **Giả định cần kiểm:** service account hiện có (`spreadsheets.readonly`) đọc được `includeGridData` của vùng nhỏ (đo trước khi code).

## 2. Cấu trúc thông tin: hai phương án

- **A. Nằm trong khách đang mở (đề xuất).** Dòng khách ở bảng "Khách lệch" có chip "Sheet cần sửa · 2 chỗ". Mở dòng thì khối này thay chỗ bảng đối chiếu (vì tab hỏng không có khoản để ghi): mỗi chỗ sai một thẻ gồm câu nói thường, ô, cách sửa, nút "Xem vùng ô" và "Mở ô này trên Sheet". Ưu: người dùng đã ở đúng khách, cùng chỗ với số lệch. Nhược: muốn thấy mọi tab hỏng một lượt phải lọc bảng.
- **B. Tab riêng "Sheet cần sửa".** Danh sách mọi tab hỏng, mỗi dòng một chỗ sai. Ưu: một danh sách việc phải sửa trên Sheet, đếm được. Nhược: thêm tab thứ tư, tách khỏi khách và số lệch, khó biết vì sao khách bị giữ.

Đề xuất **A**, kèm chip lọc "Sheet cần sửa (9)" đầu bảng (một chip như các chip hiện có, không tab mới): được cả hai, ít thêm chỗ mới. Hai bản dựng cho người dùng chọn trước khi làm kỹ.

**Nhìn gì (khung 1280×560):** (1) dòng đầu của khối: "Tab <khách> cần sửa trước khi web ghi tiền" + số chỗ sai; (2) chỗ sai đầu tiên: câu thường + ô; (3) vùng ô dựng lại của chỗ sai đó, mở sẵn cho chỗ sai đầu, các chỗ sau đóng. **Luôn hiện:** câu thường, ô, cách sửa. **Chỉ mở khi cần:** vùng ô (đọc Sheet tốn một lượt gọi).

## 3. Nội dung mỗi chỗ sai (từ `findings`)

| Loại | Câu nói thường | Ô khoanh |
| --- | --- | --- |
| `row_shift` | "Dòng 15 có container mà không có tiền, dòng 16 có tiền mà không có container: tiền có thể nằm lệch một dòng." | cả cặp (hai ô), đỏ |
| `chain_break` | "Số cuối tháng 10 sai: ô N45 đang là 0 gõ tay, các tháng khác là `=N40+K45-M45`." | ô lỗi đỏ; ô cùng cột của khối khác (công thức mẫu) cạnh bên |
| `negative_receipt` | "Ô thu ở dòng 52 là số âm. Web chưa có loại chi trả khách (K5 chưa chốt)." | ô số âm, đỏ |
| `duplicate_container` | "Container X ở hai dòng 31 và 44, dòng 44 không có tiền." | hai ô container, cam |
| lỗi bộ quét (`issues`) | câu theo mã (đã có `REASON_TEXT`) | ô nếu biết, không thì cả dòng |
| `two_row_layout` (chú thích) | không hiện như lỗi; tab đã duyệt | — |

Ô nghi ngờ (viền cam nét đứt): ô ngày mà giá trị hiển thị và ngày lưu khác nhau kiểu đảo ngày/tháng (ví dụ hiện 11/10, lưu 10/11). Không đọc được ngày lưu thì bỏ cờ này, không đoán.

## 4. Vùng ô dựng lại

**Nguồn.** Một endpoint đọc `GET /api/v7/sheet/vung-o?customer=<id>&finding=<khóa>`. Server tự tính vùng từ `finding` (khoảng 10–15 dòng quanh ô, các cột của khối); **không nhận A1 tuỳ ý** từ client, để chỉ đọc được tab của khách đó. Chạy bằng service account có sẵn, `spreadsheets.get` với `includeGridData` và `fields` chỉ: `formattedValue`, `userEnteredValue.formulaValue`, `effectiveFormat` (nền, chữ đậm, căn lề), `merges`, `columnMetadata` và `rowMetadata.pixelSize`, `sheetId`. Đọc khi người dùng mở, không theo nhịp 15 phút. Cache ngắn (60 giây theo tab và vùng), trả kèm `read_at`. ID Sheet chỉ lấy từ cấu hình trên server, không đưa vào repo hay vào trang ngoài link mở ô.
Với `chain_break`: đọc thêm một dải cột (chỉ công thức) của ô tổng ở mọi khối để so với mẫu của các khối khác cùng tab: ô trống hoặc là số gõ tay thay công thức thì nêu thẳng ô; mẫu là công thức phổ biến nhất sau khi đổi sang tham chiếu tương đối.

**Hiển thị.**
- Lưới giống Sheet: chữ cột, số dòng, đúng giá trị hiển thị, màu nền, ô gộp.
- Cột trống liên tiếp gộp thành một cột hẹp ghi "…".
- Ô lỗi viền đỏ, kèm một câu giải thích; ô nghi ngờ viền cam nét đứt.
- `chain_break`: công thức mẫu của khối khác ghi cạnh giá trị hiện tại; `row_shift`: khoanh cả cặp ô.
- Dưới lưới: "đọc lúc 15:42" và nút "Đọc lại". Nút "Mở ô này trên Sheet" dùng `https://docs.google.com/spreadsheets/d/<id>/edit#gid=<sheetId>&range=<A1>`; ID lấy từ phản hồi server.
- Màu theo token `cong-no-theme.css`: đỏ lỗi và cam nghi ngờ lấy từ màu trạng thái hiện có; nền ô của Sheet giữ nguyên như Sheet (nội dung, không phải trang trí).

**Điện thoại 390px (iPhone).** Lưới cuộn ngang trong khung riêng, ô lỗi tự cuộn vào giữa khung khi mở; cột chữ và số dòng cố định bên trái.

## 5. Trạng thái

- Đang tải: khung lưới giữ chỗ và chữ "Đang đọc Sheet…".
- Không đọc được Sheet (mạng, quyền, quá hạn): câu thường vẫn hiện, vùng ô thay bằng "Chưa đọc được Sheet lúc này" kèm "Thử lại"; nút mở ô vẫn dùng được nếu có `sheetId`.
- Ô trống của Sheet hiện trống; ô NULL của web (không phải của khối này) hiện `—`.
- Tab sửa xong: lượt quét 15 phút sau không còn chỗ sai, khối tự biến mất; trong lúc chờ, "Đọc lại" cho thấy vùng ô mới nhưng khối chỉ biến khi bản chụp mới không còn `finding`. Câu giải thích ghi rõ "web đọc lại Sheet mỗi 15 phút".
- Khách `HELD` do máy đối soát nhưng không có `finding` nào (lỗi tầng TONG, chuỗi số dư): hiện đúng câu cũ, không giả vờ biết ô.
- Tháng khóa/mở không liên quan khối này (không ghi). Tab được miễn bố cục hai dòng: không có khối.
- Chữ dài, tên khách chữ Hán: câu thường xuống dòng, không tràn; lưới cuộn trong khung.

## 6. Luồng người dùng

1. Mở *Việc cần làm*; thấy chip "Sheet cần sửa (9)" và, ở dòng khách, "Sheet cần sửa · 2 chỗ".
2. Bấm dòng khách: khối mở; chỗ sai đầu tiên hiện câu thường và vùng ô đang tải.
3. Nhìn ô đỏ, đọc cách sửa; bấm "Mở ô này trên Sheet", sửa trên Sheet.
4. Quay lại, bấm "Đọc lại" thấy ô đã đúng; chờ lượt quét kế tiếp, khối tự mất và bảng đối chiếu/ghi tiền của khách hiện lại.

## 7. Giao theo PR

| PR | Nội dung | Đổi schema | Triển khai |
| --- | --- | --- | --- |
| 3a | Cặp hai dòng: tiền là giá chuyến web (đã lên `hao`, #442) | Không | Tự động |
| 3b | `negative_receipt` (mức `error`, chặn ghi) và `duplicate_container` (mức `warning`, không chặn: dòng không tiền cộng 0) trong `v7_tab_health.py`, ô nêu rõ. ĐÃ CODE 16/11/2026; đo trên `hao`: 9 tab `broken` như cũ, 1 tab có `negative_receipt` (ô M238, đúng ca số âm 164.833.232 đ ở cột thu), 11 cảnh báo `duplicate_container` ở 2 tab | Không | Tự động |
| 3c | Endpoint `GET /api/v7/sheet/vung-o` đọc vùng ô (`web/v7_sheet_region.py`, cache 60 giây, API tự xin token chỉ đọc) và `chain_break` nêu ô (ô số cuối tháng của khối, so công thức mẫu các khối khác). ĐÃ CODE 16/11/2026; đo trên `hao` với tab sổ 239: 1,1 giây, 20 KB, đọc đủ công thức, nền, ô gộp, chỉ đúng cặp ô `row_shift` và một ô ngày nghi đảo | Không; cần drop-in `sheet-region.conf` cho `v7-ledger-api` (phiên điều phối duyệt 16/11/2026 theo quyền người dùng trao 21/10) | Release tự động, drop-in tay |
| 3d | Khối "Sheet cần sửa" ở bảng đối chiếu của khách (`preview/viec-can-lam-sheet-can-sua.js`, CSS, nút Xem vùng ô / Đọc lại / Mở ô này trên Sheet, 1280×560 và 390px). ĐÃ CODE 16/11/2026 (test đơn vị, test trình duyệt hai cỡ, ảnh render dữ liệu giả). **Chưa làm:** bước cuối của `UX-NEN-01` (người dùng thật đi hết luồng) | Không | Tự động |
| 3e | Chip lọc "Sheet cần sửa (n)" đầu bảng khách lệch (n = số khách máy giữ) và nhãn "Sheet cần sửa · k chỗ" ở dòng. Máy đối soát ghi `sheet_fix_count` cho khách `HELD` bằng `sheet_findings` (`web/v7_sheet_fix.py`), cùng hàm bảng đối chiếu dùng, nên k bằng số thẻ khi mở; chưa đếm được thì nhãn không nêu số. ĐÃ CODE 17/11/2026 (test đơn vị, test trình duyệt 1280 và 390px) | Không (`reconcile.json` thêm một trường) | Tự động |

Mọi luật kiểm ở `v7_tab_health.py`, không đụng `v7_load*`. Không ghi Google Sheet.

## 8. Ca thật làm fixture giả (đổi tên và số)

- Sổ có ô số dư gõ đè 0, mẫu đúng `=N40+K45-M45`.
- Sổ có ô tổng thu trống, mẫu đúng `=SUM(M692:M847)`.
- Sổ lệch dòng ở khối tháng 10 (hai cặp).
- Ô ngày hiện 11/10 mà lưu 10/11.

## 9. Tiêu chí nghiệm thu

- [x] Mỗi loại ở mục 3 có fixture giả và test; ô đúng theo A1 (3b, 3c, 3d).
- [x] Endpoint không nhận A1 từ client; vùng tính từ chỗ sai của tab thuộc sổ; không ghi gì; có `read_at`; cache 60 giây, `fresh=1` bỏ cache; lỗi Sheet trả 503 rõ.
- [x] Bản dựng đúng giá trị hiển thị, nền, ô gộp; cột trống liên tiếp gộp thành "…".
- [x] Ô lỗi viền đỏ và ô nghi ngờ viền cam nét đứt, có câu giải thích; `chain_break` hiện công thức mẫu; `row_shift` khoanh cả cặp.
- [x] 1280×560: không cuộn ngang trang, ô lỗi trong khung lưới; 390px: lưới cuộn ngang trong khung, ô lỗi đầu tiên ở giữa (cả cặp ô nếu vừa khung).
- [x] Chip "Sheet cần sửa (n)" đếm đúng, lọc đúng (3e); tab sửa xong thì khối biến sau lượt quét (khối tự mất khi bản chụp mới không còn chỗ sai).
- [ ] Người dùng thật đi hết luồng mục 6 trên bản thử (bước cuối `UX-NEN-01`): chưa làm.

## 10. Đợt sau (chưa làm)

**Loại việc "TOTAL Sheet khác giá web".** Tab chỉ có cột TOTAL (không có đơn giá), chuyến web đã có giá khác: máy không có việc nào để đổi (ô đơn giá trống không phải 0, TOTAL chỉ thành giá khi chuyến chưa có giá) nên khách `NO_EXACT_FIX` mãi. Ca thật 16/11/2026, sổ 149: 11 chuyến web giá bảng 42 tr, TOTAL Sheet 15–26 tr; người dùng chốt "Sheet đúng". Đề xuất loại việc riêng liệt kê từng chuyến (giá web, TOTAL Sheet, chênh) cho người bấm "Lấy theo Sheet" từng chuyến hoặc cả nhóm, dùng lệnh sửa giá chuyến thường, có trước → sau. Chờ người dùng chốt.

## 11. Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`). Review: opus (đụng đường đọc Sheet và màn dùng hằng ngày).
- Được sửa: `cong-no-web-handoff/tools/v7_tab_health.py`, `web/` (endpoint đọc vùng ô, `v7_api_doi_chieu.py` nếu cần), `preview/` (khối, model, CSS), test tương ứng.
- Cấm: ghi Google Sheet, đổi luật tiền, đổi `v7_load*`, đưa ID Sheet vào repo, dữ liệu khách thật trong bản xem.
