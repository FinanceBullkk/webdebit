# Chi phí tài xế, ứng và hoàn tiền cho đội xe (CHI-PHI-XE-01, đợt 1)

Trạng thái: ĐỀ XUẤT (Claude, 18/11/2026). Các điểm người dùng đã trả lời trong chat 18/11/2026 ghi ở [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md); mọi chỗ ghi CÒN MỞ phải hỏi lại trước khi code phần đó.

## Bối cảnh

Công ty có **18 xe đầu kéo của mình** (nhóm VTP và NSX). Hiện có hai nơi ghi chi phí từng chuyến, mỗi nơi một người nhập:

- Google Sheet "TÀI XẾ T<tháng>" do một nhân viên nhập (10 xe), mỗi tài xế một tab.
- File Excel "BK TÍN PHÁT" do nhân viên còn lại nhập (8 xe), mỗi tháng một tab.

Từ tháng 5/2026 hai nơi dùng **cùng một mẫu cột** (xem mục Đối chiếu dữ liệu). Tài xế ứng tiền, tự chi các khoản trên đường (phí nâng, neo, vá vỏ…), gửi bill; văn phòng nhập, rồi chuyển khoản hoàn lại theo đợt. Ứng, hoàn và số dư từng tài xế hiện không có một nơi tính chung.

Ngoài phạm vi đợt 1 (đã chốt làm sau): công nợ cước với công ty hàng và nhà xe thuê ngoài, lương chuyến, lãi lỗ từng xe. Xem mục Phân kỳ.

## Người dùng và luồng (bước 1)

**Người thao tác:** hai nhân viên văn phòng nhập liệu trên máy tính (màn 1280×720), như hiện nay. Tài xế **không** dùng web ở đợt 1. Người quản lý xem số dư. Đăng nhập và quyền theo `ACCESS-01` như sổ khách.

**Luồng chính:**

1. **Mở Đội xe:** menu trái có mục "Đội xe". Mở ra là bảng tài xế: tên, biển số xe đang chạy, **số dư** (công ty còn nợ tài xế / tài xế còn giữ tiền ứng), số chuyến chưa hoàn, ngày ứng gần nhất. Bấm một dòng thì mở sổ tài xế đó.
2. **Nhập chi phí chuyến:** trong sổ tài xế, bảng chuyến kiểu Sheet (dùng lại cách nhập của `NHAP-SHEET-01`): dán khối dòng chép từ Sheet/Excel hiện tại, hoặc gõ tại ô. Mỗi dòng: ngày, container, cont kéo, tỉnh, kho, nơi lấy, nơi hạ, tên hàng, các khoản phí theo cột, ghi chú. Cột **"Tài xế chi"** tự cộng các khoản tài xế trả, **không** gồm cầu đường VETC (công ty trả).
3. **Ghi ứng:** nút "Ghi ứng" → số tiền, ngày chuyển, ghi chú → xem lại → ghi. Số dư giảm ngay.
4. **Hoàn tiền theo đợt:** nút "Hoàn tiền" → tích các chuyến chưa hoàn (mặc định tích tất cả) → thấy tổng → nhập ngày chuyển và số tiền thực chuyển → ghi. Các chuyến đã chọn đánh dấu "Đã hoàn ngày …", thay cho cột "da tt" / "14/10" đang ghi tay.
5. **Sửa, hủy:** sửa ô chuyến thì ghi Lịch sử trước → sau. Hủy một lần ứng hoặc một đợt hoàn **bắt buộc lý do**; hủy đợt hoàn thì các chuyến trở lại "chưa hoàn".

**Bị chặn khi:** ngày tương lai (giờ VN); số tiền không phải số nguyên VND; đợt hoàn không có chuyến nào; dòng có tiền nhưng thiếu cả ngày lẫn container (hiện Sheet có dòng như vậy vẫn được cộng, xem mục Chỗ dễ sai).

**Kết quả:** mỗi tài xế có một số dư đúng tới từng đồng, biết chuyến nào đã hoàn, đợt nào, ai ghi.

## Đầu ra

Mục "Đội xe" trên web hiện bảng 18 tài xế với số dư. Sổ từng tài xế nhập được chi phí chuyến bằng dán hoặc gõ, ghi được ứng và đợt hoàn. Số dư mỗi tài xế = tổng tài xế chi − tổng đã hoàn − tổng đã ứng, một số dư chung cho mỗi tài xế (người dùng chốt 18/11/2026). Mọi thao tác tiền có Lịch sử.

## Đối chiếu dữ liệu và code hiện có (bước 2)

### Nguồn hiện tại (đã đọc 18/11/2026, bản sao ngoài Git ở `captures/nha-xe/`)

Mẫu cột chung của Sheet "TÀI XẾ T10" và các tab T5–T11 của "BK TÍN PHÁT" (dòng 2 là tiêu đề, dòng 1 là tổng từng cột):

| Cột Sheet | Trường web | Ghi chú |
| --- | --- | --- |
| STT | — | Đang bị dùng ghi ngày hoàn ("14/10") |
| TRÂN/GL | — | Đang ghi người nhập hoặc "da tt" |
| NGÀY | `event_date` | Chuỗi tháng/ngày/năm (`10/2/2026` = 2/10) |
| SỐ CONT, CONT KÉO | `container`, `container_keo` | Một container có thể đi nhiều chặng |
| TỈNH, KHO, NƠI LẤY, NƠI HẠ, TÊN HÀNG | thông tin chuyến | Chữ tự do |
| TÀI XẾ, Số xe | tài xế, xe | Biển số ghi không thống nhất giữa các file |
| PHÍ NÂNG, NÂNG HẠ, CẦU ĐƯỜNG, NEO, XÍ CONT/TRÁI TUYẾN/XE NÂNG, ĐẢO CONT, CONT MỚI, DỜI CONT, MUA SEAL, BÃI CHỜ, ĐIỀU ĐỘ, ĐỔ DẦU (tài xế trả), PHÁT SINH, NỔ MÁY PHÁT | dòng phí, người trả = tài xế | Danh mục phí, cách làm như `PHU-PHI-01` |
| GHI CHÚ | ghi chú | Diễn giải phát sinh (vá vỏ, tưới vỏ…) |
| CẦU ĐƯỜNG (VETC) CTY THANH TOÁN | dòng phí, người trả = công ty | Không cộng vào phần hoàn tài xế |
| Cột cuối không tiêu đề | "Tài xế chi" | Đã kiểm trên 3 dòng mẫu ở hai file: = tổng các phí tài xế trả, không gồm VETC |

Ứng hiện ghi trong file điều xe "XE TIN PHAT" thành khối "LẦN ỨNG / SỐ TIỀN / Q.TOÁN" theo tháng, không theo từng tài xế (CÒN MỞ (2)).

### Code dùng lại được

- Đăng nhập, danh tính người thao tác, Lịch sử dạng sự kiện (`sokhach.event`), khóa trùng lệnh ở `so-khach-v7-api.js`.
- Lưới nhập kiểu Sheet và dán khối (`NHAP-SHEET-01`), danh mục và dòng phụ phí (`PHU-PHI-01`).
- Triển khai, backup mỗi giờ, canh lỗi email trên `hao`.

### Còn thiếu

- Schema riêng (ĐỀ XUẤT tên `doixe`): tài xế, xe, chuyến chi phí, dòng phí, ứng, đợt hoàn, liên kết đợt hoàn ↔ chuyến. Không ghi vào bảng của `sokhach`.
- API `/api/v7/doixe/*`, màn Đội xe và sổ tài xế.

## Nguồn quyết định

- [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md): phạm vi và các câu người dùng đã trả lời 18/11/2026.
- Áp dụng nguyên các quy tắc tiền chung của `AGENTS.md`: VND nguyên, NULL không phải 0, mọi thao tác tiền ghi người làm và trước → sau, hủy bắt buộc lý do, cấm ngày ghi tương lai.
- Khóa tháng (`V7-SO`) có áp dụng cho sổ tài xế không: CÒN MỞ (4).

## Hành vi và bất biến

- Tiền là số nguyên VND. Số Sheet có phần lẻ (ví dụ `=11000000*70%`) bị chặn khi dán, người nhập tự làm tròn.
- Ô phí trống là NULL, không hiển thị 0, nhưng không cộng vào tổng.
- Chuyến chi phí độc lập với chuyến trong sổ khách. Ghép theo container + ngày chỉ để xem ở các đợt sau, không đổi số nợ khách.
- Một chuyến thuộc tối đa một đợt hoàn chưa hủy.
- Số dư tài xế tính lại được từ các dòng gốc. Không lưu số dư như một trường sửa tay.
- Số dư dương: công ty còn nợ tài xế. Số dư âm: tài xế còn giữ tiền ứng. Ứng không trừ riêng vào từng đợt hoàn; cả ba loại dòng cùng vào một số dư.

## Chỗ dễ sai thấy trong dữ liệu hiện tại

1. Dòng không có ngày, không có container nhưng vẫn có 100.000đ nâng hạ, và vẫn được cộng vào tổng tab.
2. Cột STT và TRÂN/GL bị dùng để ghi ngày hoàn và "da tt".
3. Ngày ở dạng chuỗi tháng/ngày, trong khi file điều xe ghi ngày/tháng.
4. Biển số ghi thiếu tỉnh ("44115") ở file này, đủ ("50H-44115") ở file khác.

## Phân kỳ

| Đợt | Nội dung | Trạng thái |
| --- | --- | --- |
| 1 | Chi phí chuyến, ứng, hoàn theo đợt, số dư tài xế (spec này) | ĐỀ XUẤT |
| 2 | Công nợ cước: công ty hàng nợ đội xe mình theo bảng kê; phải trả nhà xe thuê ngoài (Trần Hùng) | Chưa spec |
| 3 | Lương chuyến, lãi lỗ từng xe (doanh thu cước − chi phí − lương) | Chưa spec |

## Tiêu chí nghiệm thu

- [ ] Dán đúng 1 tab tài xế tháng 10/2026 vào bản thử: tổng "Tài xế chi" và tổng từng cột phí khớp dòng tổng của tab đó tới từng đồng, trừ các dòng bị chặn đã liệt kê.
- [ ] Ghi ứng, ghi đợt hoàn, hủy từng loại: số dư đổi đúng, Lịch sử có người làm, trước → sau, lý do hủy.
- [ ] Ghi lặp do bấm hai lần hoặc mất mạng giữa chừng không tạo hai lần ứng hay hai đợt hoàn.
- [ ] Harness PostgreSQL cho schema `doixe` chạy xanh; `npm run check` xanh.
- [ ] Kiểm trình duyệt 1280×720: bàn phím, nhập sai, tải chậm, thiếu quyền.
- [ ] Hai nhân viên nhập tự đi hết luồng trên bản thử với dữ liệu một tháng và xác nhận.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`)
- Review: opus (ghi tiền)
- Được sửa: PR này chỉ có tài liệu (`specs/chi-phi-xe-01.md`, `docs/decisions/chi-phi-xe-01.md`, `docs/decisions.md`). Các PR code sau sẽ ghi phạm vi file riêng.
- Cấm: chạy DDL, nạp dữ liệu thật, ghi Google Sheet.

## Hoàn tác

Revert PR. Không có dữ liệu.

## Bằng chứng

Đọc nguồn 18/11/2026 (chỉ đọc): 2 file công nợ cảng tháng 10/2026, Sheet "TÀI XẾ T10", file Drive "XE TIN PHAT" và "BK TÍN PHÁT - TRÂN". Kiểm công thức cột cuối trên 3 dòng mẫu. Chưa có code, chưa có bản thử.

## Câu hỏi mở

1. ~~Số dư = tài xế chi − đã hoàn − đã ứng, một số dư chung mỗi tài xế, đúng không?~~ ĐÃ TRẢ LỜI 18/11/2026: đúng.
2. Khối "LẦN ỨNG" trong file điều xe (ví dụ nhiều lần 20 triệu một tháng) là ứng cho từng tài xế hay cho người điều xe trả phí cảng? Nếu cho từng tài xế thì hiện ghi chi tiết theo người ở đâu?
3. Sổ theo **tài xế** hay theo **xe**? Đề xuất theo tài xế, vì ứng và hoàn là tiền của người, mỗi chuyến vẫn ghi biển số xe để đợt 3 tính lãi lỗ theo xe.
4. Có khóa tháng như sổ khách không, hay sửa lúc nào cũng được kèm Lịch sử?
5. Bắt đầu từ tháng nào, và số dư đầu của từng tài xế lấy ở đâu? Nạp dữ liệu thật cần người dùng duyệt riêng.
6. Cột "Nổ máy phát" có tính vào phần hoàn tài xế không? Trong dữ liệu đã đọc, cột này trống.
