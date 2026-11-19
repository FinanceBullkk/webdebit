# Đội xe: cấu trúc màn theo đối tượng (DOI-XE-CAU-TRUC-01)

Trạng thái: cấu trúc năm mục ĐÃ CHỐT (người dùng, 19/11/2026: "Chốt theo hướng A"; [`DOI-XE-CAU-TRUC-01`](../docs/decisions/doi-xe-cau-truc-01.md)). Bố cục từng mục, mô hình dữ liệu mới và thứ tự gói việc là ĐỀ XUẤT (Claude). Đây là tài liệu điều phối: mỗi gói việc có spec riêng khi tới lượt.

## Vì sao đổi

Audit ngày 19/11/2026 (chỉ đọc: spec, schema, code, năm màn trên `hao` với bản thử tháng 10–11/2026). Module đang chia màn theo file Sheet nguồn: sổ tài xế là tab tài xế, Bảng kê là file công nợ cảng, Điều độ sẽ là file điều xe. Cùng một chặng vì vậy hiện ở ba màn, sắp thành bốn.

| # | Trùng gì | Số đo |
| --- | --- | --- |
| 1 | Sổ xe trùng sổ tài xế | Tháng 10: 206 chặng ở cả hai phía; 14/16 cặp xe–tài xế có đúng cùng tập dòng; 0 chặng có người trả khác tài xế. Cả hai màn đều nhập và sửa được |
| 2 | Một chặng sửa ở nhiều nơi | Chữ và chi phí ở sổ; cước và tuyến ở Bảng kê; xe và tài xế sẽ ở Điều độ. Mỗi nơi một luật sửa |
| 3 | Hai kiểu chốt tháng | Ổ khóa tháng (chi) và trạng thái bảng kê (thu) không biết nhau: tháng 10 đã khóa trong khi bảng kê tháng 10 đang gom |
| 4 | Hai danh mục cho cùng khoản tiền | `loai_phi` có 16 khoản chi, `phat_sinh` có 14 khoản thu, nối được 10. Cờ chi hộ lưu ở cả hai. Một khoản chi hộ phía thu không có khoản chi tương ứng |
| 5 | Hai cách xác định người trả | Theo cả chặng (`chang.nguoi_tra_id`) và theo loại phí (`loai_phi.cong_ty_tra`). Thực tế là theo từng khoản |
| 6 | Việc dở nằm rải rác | "Chưa có phí" ở ba chỗ; "Chưa nối" ở sổ; "Chưa có giá", "Giá khác bảng", "Khoản lạ" ở Bảng kê |
| 7 | Lịch sử ba nơi; tab Bảng giá gộp giá với danh mục | Xe, người, loại phí không có màn sửa |

Luồng dùng:

- Sổ tài xế ở khung 1280×560 chỉ thấy 3 dòng chặng; thẻ tiền cao 180px.
- Đủ cột: 33 cột, rộng 3.106px trên khung 1.241px, 28 ô nhập mỗi dòng.
- Bảng kê tháng 10: 206 dòng phẳng, trang cao 9.823px.
- Bảng giá: 40 tuyến hàng, không tuyến nào có nơi đến, không tuyến nào có tên gốc; có cặp tên gần trùng cùng giá. 8/14 khoản phát sinh chưa có mức.
- Nhập theo người và tháng, trong khi phiếu chi về theo từng chuyến.
- Đổi giữa "Người và xe" và "Bảng kê" mất tháng đang chọn (hai trang riêng).

Mô hình và code:

- Tiền thu phát sinh đọc từ ô ghi chú chữ của chặng (`doixe._doc_ghi_chu`). Ghi chú được coi là chữ, sửa đè cả ở tháng khóa, nên sửa ghi chú làm đổi số sẽ đòi HTH khi bảng kê chưa gửi (đọc code, chưa thử).
- Mọi dòng chi buộc gắn chặng (`dong.chang_id`), chặng buộc có container: dầu, sửa chữa, định phí chưa có chỗ ghi.
- Mỗi đối tác một bộ bảng công nợ riêng: `ung`, `dot_hoan` cho người; `bang_ke`, `dieu_chinh_bk`, `tien_ve` cho HTH.
- Thu và chi của cùng chặng chưa hiện cạnh nhau ở màn nào.
- `doi-xe-ui.js` và `doi-xe-thu-ui.js` chép nguyên phần tải, ghi, thông báo.

## Người dùng và luồng (bước 1)

Người thao tác: điều xe, hai nhân viên nhập chi phí, kế toán, người quản lý. Màn 1280×720 (Chrome thấy khoảng 1280×560). Đăng nhập và quyền theo `ACCESS-01`. Chưa hỏi trực tiếp các vai này: bố cục dưới đây là ĐỀ XUẤT tới khi người dùng thử bản bấm thử.

Nguyên tắc: mỗi đối tượng một nhà. Màn khác muốn sửa đối tượng đó thì mở nhà của nó.

| Mục | Câu hỏi người dùng mang tới | Đối tượng | Thay cho |
| --- | --- | --- | --- |
| **Chặng** | Hôm nay xe nào chạy gì? Chặng nào còn thiếu xe, thiếu phí, thiếu giá? | Chặng | Màn Điều độ riêng, bảng chi phí trong sổ người, sổ xe, bảng chặng của Bảng kê |
| **Công nợ** | Ai nợ ai bao nhiêu? Trả ai, thu ai? | Đối tác, khoản phải thu hoặc phải trả, tiền chuyển | Thẻ tiền, ứng, hoàn của sổ người; bảng kê, điều chỉnh, tiền về |
| **Xe** | Xe này tốn gì, chạy bao nhiêu, có lời không? | Phương tiện, chi theo xe | Sổ xe |
| **Lãi lỗ** | Tuyến nào, xe nào lỗ? | Góc nhìn, không nhập | Chưa có |
| **Thiết lập** | Sửa danh mục ở đâu? | Xe, người, tuyến và giá, danh mục khoản | Tab Bảng giá; danh mục nạp sẵn |

**Chặng** (ĐỀ XUẤT):

1. Một danh sách chặng của cả đội, lọc theo ngày, xe, tài xế, trạng thái. Hai cách xem: theo việc và theo xe.
2. Hàng chờ ở đầu màn, bấm là lọc: chờ phân xe, chưa có phí, chưa có giá, chưa nối chuyến khách, booking đã đổi.
3. Bấm một dòng mở phiếu chặng tại chỗ, ba phần: phân công (xe, tài xế, ngày chạy), chi (từng khoản, ai trả), thu (cước theo bảng giá, từng khoản phát sinh). Cuối phiếu là lãi gộp của chặng.
4. Mỗi vai có sẵn một bộ lọc mở đầu: điều xe thấy hôm nay và việc chờ phân xe; nhân viên thấy chặng chưa có phí; kế toán thấy chặng chưa có giá.
5. Hành vi phân công theo luồng đã chốt ở [`DOI-XE-DIEU-DO-01`](../docs/decisions/doi-xe-dieu-do-01.md). Chặng đã có phí, đã hoàn hoặc đã lên bảng kê đã gửi: sửa trong chính phiếu chặng theo luật điều chỉnh, không chỉ đường sang màn khác.
6. Dán khối từ Sheet chỉ còn là đường chuyển dữ liệu cũ.

**Công nợ** (ĐỀ XUẤT): danh sách đối tác kèm số dư; mỗi đối tác một sổ cùng cấu trúc (khoản làm tăng nợ, tiền chuyển, số dư). Sổ tài xế giữ ứng, hoàn theo đợt; chặng chưa hoàn là danh sách chỉ xem, bấm mở phiếu chặng. Sổ HTH giữ bảng kê tháng, đối chiếu, tiền về; Excel 19 cột giữ nguyên vì là chứng từ gửi đi.

**Xe, Lãi lỗ, Thiết lập:** phác ở bản bấm thử, spec riêng khi tới lượt.

## Đầu ra

Menu Đội xe còn năm mục. Một chặng chỉ nhập và sửa ở mục Chặng. Số dư mọi đối tác xem ở mục Công nợ. Các màn cũ bị gỡ sau khi mục thay nó được nghiệm thu.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Dùng lại:** bảng `chang`, `dong`, `dong_phi`, `ung`, `dot_hoan`, `thang_khoa`, `su_kien`, `lenh`; bảng giá `tuyen`, `gia_tuyen`; `bang_ke`, `bang_ke_dong`, `dieu_chinh_bk`, `tien_ve`; các lệnh `luu_chang`, `sua_chang`, `xoa_chang`, `ghi_ung`, `ghi_hoan`, `gui_bang_ke`, `ghi_tien_ve`; mã yêu cầu chống ghi trùng; Lịch sử.

**Đang viết ở phiên khác (chưa lên `main`):** schema và lệnh phân xe của Điều độ.

**Còn thiếu:** hàm đọc danh sách chặng toàn đội kèm thu, chi, lãi gộp; người trả theo khoản; khoản thu có dòng riêng; danh mục khoản chung; công nợ chung; chi theo xe; màn sửa danh mục.

## Gói việc và thứ tự (ĐỀ XUẤT)

| Gói | Nội dung | File chính | Cần trước | Đụng luật tiền |
| --- | --- | --- | --- | --- |
| T1 | Bản bấm thử năm mục, dữ liệu giả, khung 1280×560 | Canvas thiết kế (ngoài Git) | — | Không |
| F1 | Vỏ chung: một module tải, ghi, thông báo dùng chung; đổi mục giữ tháng. Không đổi hành vi | `cong-no-web-handoff/preview/doi-xe*.js`, `doi-xe*.html`, `doi-xe*.css`, test trình duyệt | — | Không |
| M1 | Spec mô hình dữ liệu mới và đường chuyển từ bảng hiện có | `specs/doi-xe-mo-hinh-01.md` | — | ĐỀ XUẤT, người dùng chốt trước khi code |
| B1 | Điều độ: schema, lệnh phân xe, đổi, bỏ, nhận thay đổi booking | Migration điều độ, harness | — | Không đổi luật |
| B2 | Hàm đọc danh sách chặng toàn đội kèm phân công, chi, thu, lãi gộp; API | Migration chỉ có hàm đọc, `web/v7_api_doixe.py` | B1 | Chỉ đọc |
| F2 | Mục Chặng: danh sách, phiếu chặng, hàng chờ | File mới trong `preview/` | T1 được chốt, B2, F1 | Dùng lệnh ghi có sẵn |
| B3 | Người trả theo khoản, danh mục khoản chung, khoản thu dòng riêng | Migration, harness | M1 được chốt | Có |
| B4, F3 | Công nợ chung và mục Công nợ | Migration, `preview/` | M1 được chốt, B3 | Có |
| B5, F4 | Chi theo xe và mục Xe | Migration, `preview/` | M1 được chốt | Có |
| F5 | Mục Lãi lỗ | `preview/` | B2 cho bản đầu, B5 cho bản đủ | Chỉ đọc |
| F6 | Mục Thiết lập | `preview/`, lệnh sửa danh mục | B3 | Danh mục |
| X | Gỡ màn cũ | `preview/doi-xe-ui.js`, `doi-xe-thu-ui.js` | Mục thay nó đã nghiệm thu | Không |

Luật điều phối:

- Mỗi gói một phiên, một nhánh, một worktree; phạm vi file không chồng nhau.
- Gói backend (B1–B5) chạy **lần lượt**: chúng cùng sửa chuỗi migration, `schema/v7_schema_current.pgsql`, harness và job CI.
- Gói frontend chạy song song được khi file không chồng.
- `main` bắt buộc `ci-ok` với `strict`: merge từng PR, chỉ cập nhật nhánh PR kế tiếp.
- Gói đụng luật tiền chỉ code sau khi người dùng chốt spec của gói đó.
- Đợt 1 chạy song song: T1, F1, M1. B1 đang ở phiên khác.

## Nguồn quyết định

- [`DOI-XE-CAU-TRUC-01`](../docs/decisions/doi-xe-cau-truc-01.md): năm mục, màn bị thay, hướng đổi mô hình.
- [`DOI-XE-DIEU-DO-01`](../docs/decisions/doi-xe-dieu-do-01.md): chặng sinh từ booking, phân công trên web.
- [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md), [`DOI-XE-THU-01`](../docs/decisions/doi-xe-thu-01.md): luật tiền chi, ứng, hoàn, khóa tháng, bảng kê. Giữ nguyên tới khi có quyết định riêng.
- Bức tranh dữ liệu: [Đội xe: bản đồ dữ liệu và kiến trúc](../docs/doi-xe-kien-truc-du-lieu.md).

## Hành vi và bất biến

- Luật tiền chung của `AGENTS.md`: VND nguyên, ô trống là NULL, mọi thao tác tiền ghi người làm và trước → sau, hủy bắt buộc lý do, cấm ngày ghi sau hôm nay (giờ VN).
- Đổi cấu trúc màn không làm đổi số dư người nhận ứng, số đòi HTH hay công nợ cước đã ghi.
- Trong lúc chuyển, màn cũ vẫn chạy; không có lúc nào một việc không còn chỗ làm.
- Schema `doixe` chỉ đọc `sokhach`. Web không ghi Sheet.
- Bản bấm thử và ảnh chụp chỉ dùng dữ liệu giả.

## Tiêu chí nghiệm thu

- [ ] Mỗi gói: `npm run check` xanh; gói backend thêm harness PostgreSQL xanh.
- [ ] F1: bộ test trình duyệt Đội xe hiện có xanh, không sửa kỳ vọng; đổi mục giữ tháng.
- [ ] B2: tổng thu, tổng chi theo tháng từ hàm đọc mới bằng đúng tổng của `get_bang_ke` và `get_so` trên dữ liệu giả của harness.
- [ ] F2: phân xe, nhập chi, sửa cước một chặng mà không rời mục Chặng; kiểm 1280×720 và 1265×560: bàn phím, nhập sai, bấm lặp, tải chậm, mất mạng, thiếu quyền.
- [ ] Sau gói X: không còn hai màn cùng sửa một chặng.
- [ ] Điều xe, hai nhân viên và kế toán tự đi hết luồng của mình trên bản thử và xác nhận.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`); phiên thực thi Sonnet 5.5, effort high; phiên audit điều phối.
- Review: opus cho gói đụng luật tiền hoặc schema; sonnet medium cho gói còn lại.
- PR này chỉ có tài liệu: spec này, `docs/decisions/doi-xe-cau-truc-01.md`, một dòng trong `docs/decisions.md` và `specs/README.md`.
- Cấm: chạy DDL, nạp dữ liệu, ghi Google Sheet; chép tên khách, số tiền thật, số container, biển số vào repo; gỡ màn cũ trước khi mục thay nó được nghiệm thu.

## Hoàn tác

Revert PR. Không có dữ liệu.

## Bằng chứng

Đọc ngày 19/11/2026, chỉ đọc, không ghi cơ sở dữ liệu, Sheet hay `hao`:

- `specs/chi-phi-xe-01.md`, `specs/doi-xe-thu-01.md`, `specs/doi-xe-dieu-do-01.md`, `docs/doi-xe-kien-truc-du-lieu.md` và ba quyết định Đội xe tại `main` `3c8e4a0`.
- Bốn migration `cong-no-web-handoff/tools/migrations/2026-11-18-v7-doi-xe*.sql`, `web/v7_api_doixe.py`, `preview/doi-xe-ui.js`, `preview/doi-xe-thu-ui.js`.
- Năm màn trên `hao` (màn tổng, sổ tài xế, sổ xe, Bảng kê, Bảng giá) ở cửa sổ 1296×720; số đếm lấy bằng các đường đọc `GET /api/v7/doixe*`.

Giới hạn: bản thử chưa có lần ứng, đợt hoàn hay người đi lệnh nào, nên chưa quan sát được các luồng đó với dữ liệu. Chưa hỏi điều xe, hai nhân viên, kế toán.

## Câu hỏi mở

1. Gói B1 đang viết dở ở một phiên khác: phiên đó tự đưa PR lên, hay chuyển cho phiên thực thi mới?
2. Hai nhân viên có nhập thử tiếp trên màn cũ trong lúc chuyển không (trùng câu 6 của tài liệu kiến trúc)?
3. Công ty hoàn tiền từng tài xế riêng, hay một đợt trả cho nhiều tài xế cùng lúc? Câu trả lời đổi bố cục mục Công nợ.
4. Sau mục Chặng, làm Công nợ, Xe hay Lãi lỗ trước?
