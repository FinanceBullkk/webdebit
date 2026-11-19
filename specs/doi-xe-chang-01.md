# Đội xe: API mục Chặng (DOI-XE-CHANG-01)

Trạng thái: ĐỀ XUẤT (Claude, 19/11/2026; PR 1 và PR 2 đã viết, chưa triển khai), gói B2 của [spec điều phối](doi-xe-cau-truc-01.md). Căn cứ đã chốt: cấu trúc năm mục ([`DOI-XE-CAU-TRUC-01`](../docs/decisions/doi-xe-cau-truc-01.md)), chặng sinh từ booking và điều xe phân công trên web ([`DOI-XE-DIEU-DO-01`](../docs/decisions/doi-xe-dieu-do-01.md)). Hợp đồng dưới đây là cái phiên frontend (gói F2) code theo; chỗ nào là lựa chọn của người viết ghi ở "Câu hỏi mở". Làm hai PR nối tiếp: **PR 1** (spec này, bộ đọc nguồn, đường đọc việc và chặng, bốn đường ghi phân công) và **PR 2** (hàm đọc thu, chi, lãi gộp của chặng, gộp vào đường đọc). PR 2 dựng trên PR 1 (cùng đường đọc, cùng spec). Mục nào do PR 2 thêm được đánh dấu **[PR 2]**.

Chạy trên mô hình dữ liệu HIỆN TẠI (`chang.tra`, `chang.nguoi_tra_id`, `loai_phi.cong_ty_tra`, ghi chú chữ cho phát sinh), nhưng JSON trả về theo hình dạng của mô hình mới (`DOI-XE-MO-HINH-01`: chi từng khoản có người trả, thu từng dòng) để mục Chặng không phải viết lại sau gói B3.

## Người dùng và luồng

Người thao tác, bối cảnh và luồng của mục Chặng đã ở [`DOI-XE-CAU-TRUC-01`](doi-xe-cau-truc-01.md) và [`DOI-XE-DIEU-DO-01`](doi-xe-dieu-do-01.md); spec này không đổi chúng. Phần API phục vụ các bước:

1. Điều xe mở mục Chặng: thấy việc hôm nay, hôm qua và mọi việc cũ còn chờ phân xe, kèm bộ đếm hàng chờ (`GET /chang?...&cu=60`).
2. Gõ vài số cuối biển số trên dòng, Enter: phân xe (`POST /chang/phan-xe`). Chọn xe thì tài xế đi theo xe, đổi được.
3. Đổi xe, tài xế, ngày chạy hoặc bỏ phân công khi chặng chưa có phí, chưa hoàn, chưa lên bảng kê đã gửi (`/chang/doi-phan-cong`, `/chang/bo-phan-cong`).
4. Booking đổi (ngày đóng, kho) hoặc việc biến mất khỏi booking: dòng mang nhãn, người quyết nhận, giữ ngoài booking hoặc bỏ (`/chang/nhan-booking`, `/chang/bo-phan-cong`). Máy không tự sửa, không tự xóa chặng.
5. Chặng đã có phí, đã hoàn hoặc đã gửi bảng kê: màn không đổi tại phân công, hiện lý do (`khoa`) và đổi theo luật điều chỉnh trong phiếu chặng.

Bị chặn: xem [bảng mã lỗi](#mã-lỗi-và-câu-thông-báo). CÒN MỞ: điều xe dùng máy tính hay điện thoại, mấy người (câu 5 của `DOI-XE-DIEU-DO-01`), chưa hỏi trực tiếp.

## Đầu ra

- Bộ đọc nguồn đọc thêm bốn cột Nhà xe, Số seal, Nhiệt độ, Tên tàu của `CONT_NGUON`.
- `GET /api/v7/doixe/chang` trả việc của đội xe trong khoảng ngày, chặng đã nối, trạng thái, bộ đếm, danh mục xe và tài xế.
- Bốn `POST` phân công: phân xe, đổi phân công, bỏ phân công, nhận thay đổi của booking.
- **[PR 2]** Hàm đọc `doixe.get_chang_tai_chinh` (migration `2026-11-19-v7-doi-xe-tai-chinh-chang.sql`, chỉ có hàm đọc); trường `chi`, `thu`, `lai_gop`, `thang_khoa`, `bang_ke_thang` trong từng chặng của `GET /chang`; mảng `ngoai_booking`; đường phiếu một chặng `GET /chang/phieu?id=`.

## Đối chiếu dữ liệu và code hiện có

| Cần | Đã có | Thiếu / làm ở đây |
| --- | --- | --- |
| Bản chụp booking | `snapshot.json` (CONT_NGUON, 15 phút một lần) do `tools/sheet_sync_runner.py`; web đọc qua `v7_api_sheet.cached_load(load_snapshot, SHEET_SNAPSHOT_PATH)`; bộ đọc `parse_source_values` tìm cột theo TÊN tiêu đề | Bốn cột Nhà xe, Số seal, Nhiệt độ, Tên tàu chưa được đọc: thêm vào `tools/webdebit_export_connector.py` |
| Việc của đội xe | Danh mục `doixe.ma_nha_xe` (`dang_dung`), rỗng trên `hao` tới khi người dùng đồng ý nạp | API lọc bản chụp theo NGUYÊN mã, không chuỗi con |
| Chặng, cờ, xe, tài xế | `doixe.get_dieu_do(việc[])` (gói B1, đã triển khai 19/11/2026) | API tính trạng thái; `get_dieu_do` không liệt kê chặng ngoài booking: **[PR 2]** lấy từ hàm mới |
| Ghi phân công | `doixe.phan_xe`, `doi_phan_cong`, `bo_phan_cong`, `nhan_booking` đã cấp cho `sokhach_app` | Đường POST, kiểm đầu vào, câu cho năm mã lỗi mới |
| Thu, chi, lãi gộp | `doixe._tinh_chang`, `get_bang_ke`, `get_so` | **[PR 2]** `doixe.get_chang_tai_chinh`: gộp theo chặng, cộng lại bằng `get_bang_ke` và `get_so` |

Dữ liệu hiện trên màn lấy từ ba nguồn: bản chụp booking (việc, kho, hàng, cảng, hãng tàu, số booking, khách, seal, nhiệt độ, tên tàu; chỉ xem), `doixe.chang` (phân công, chữ của chặng), và **[PR 2]** phép tính thu chi của `get_chang_tai_chinh`. Bản bấm thử `preview/mockups/doi-xe-huong-a/index.html` dùng dữ liệu giả cùng hình dạng.

## Giao tiếp frontend–backend

Tích hợp thật (không fixture): đường đọc gọi hàm trong schema `doixe` qua đúng runner psql của sổ khách, cộng đọc file bản chụp booking ngoài DB. Mọi đường nằm sau xác thực danh tính ([`ACCESS-01`](../docs/decisions.md)): `handle` giải danh tính trước khi vào đây; người ngoài danh sách bị chặn `LOGIN_NOT_ALLOWED` (403) trước khi đọc bản chụp hay gọi DB. Người làm lấy từ phiên, không từ thân lệnh. Không có đường nào gọi `doixe.nap_nha_xe` (công cụ nạp mã nhà xe, không cấp cho app).

### Quy ước chung

- Ngày: chuỗi `YYYY-MM-DD`. Tháng: `YYYY-MM-01`. Id: số nguyên dương. Ô trống là `null`, không phải `0` hay `""`.
- Thân `POST` là JSON một đối tượng, không khóa lạ, không số thực. **Mọi lệnh ghi bắt buộc `idempotency_key`** (chuỗi 1–128 ký tự, không ký tự điều khiển): giao diện sinh một mã cho mỗi lần bấm, gửi lại đúng mã đó khi mất mạng hay bấm lặp. Cùng mã, cùng nội dung: trả kết quả cũ kèm `"lap_lai": true`, không ghi thêm. Cùng mã, nội dung khác: `IDEMPOTENCY_CONFLICT` (409).
- Lỗi: `{"error": "<MÃ>", "message": "<câu thường>"}` với status ở bảng mã lỗi. Lệnh quá 25 giây không rõ kết quả: `RESULT_UNKNOWN` (503), giao diện gửi lại với cùng mã.
- Mọi `actor` trong kết quả có thêm `actor_name` (tên ngắn theo bảng tên PRESENCE-01).
- Ngày chạy sau hôm nay (giờ VN) bị chặn, trừ khi bằng đúng ngày đóng của việc (xe lấy rỗng hôm nay, đóng hàng hôm sau).

### `GET /api/v7/doixe/chang`

Tham số (đúng một dạng, cộng `cu` tùy chọn; tham số lạ hoặc lặp là `INVALID_REQUEST`):

| Tham số | Nghĩa |
| --- | --- |
| `thang=YYYY-MM-01` | Cả tháng (ngày đóng trong tháng). Không có `thang`, `tu`, `den` thì lấy tháng hiện tại giờ VN |
| `tu=YYYY-MM-DD&den=YYYY-MM-DD` | Khoảng ngày đóng, gồm hai đầu, tối đa 93 ngày. Phải đủ cả hai tham số |
| `cu=N` (0–92, mặc định 0) | Lùi N ngày trước `tu`/đầu tháng để giữ thêm các việc cũ **còn chờ phân xe** (cờ `cu: true`). Việc cũ đã phân xe không hiện |

**Màn mặc định của điều xe** (hôm qua, hôm nay, việc cũ còn chờ, việc sắp tới): `tu=<hôm qua>&den=<hôm nay + 7>&cu=60`. Việc "sắp tới" (chưa có số cont, hoặc ngày đóng sau hôm nay) chỉ hiện khi ngày đóng của nó nằm trong `tu`–`den`, nên `den` phải lùi về sau hôm nay; frontend tự chọn số ngày (7 là đề xuất). Lấy `hom_nay` từ kết quả lần gọi trước, hoặc giờ VN của máy.

JSON trả về (`200`):

```json
{
  "hom_nay": "2026-11-19",
  "tu": "2026-11-01", "den": "2026-11-30", "cu": 0,
  "nguon": {"tao_luc": "2026-11-19T09:50:00+07:00", "qua_han": false, "so_dong": 812,
            "bo_qua": {"khong_nha_xe": 640, "khong_ngay": 2, "trung": 1}},
  "viec": [ <việc>, ... ],
  "khong_con_tren_booking": [ <chặng>, ... ],
  "ngoai_booking": [ <chặng>, ... ],
  "dem": {"viec": 41, "sap_toi": 3, "cho_phan_xe": 9, "da_phan_xe": 12, "da_co_phi": 10, "da_len_bang_ke": 7,
          "booking_doi": 2, "chua_co_phi": 14, "chua_co_gia": 5, "ngoai_khoang": 1, "khong_con_tren_booking": 1, "ngoai_booking": 2},
  "xe":    [{"id": 1, "bien_so": "…", "nhom": "…", "thue_ngoai": false, "tai_xe_id": 2}, ...],
  "tai_xe": [{"id": 2, "ten": "…"}, ...]
}
```

- `nguon.tao_luc`: giờ tạo bản chụp, **đã đổi sang giờ VN** (runner ghi UTC); `null` nếu không đọc được hoặc thiếu múi giờ. `nguon.qua_han`: bản chụp cũ hơn 60 phút (hoặc không đọc được giờ tạo): giao diện báo "Booking cập nhật lúc …". `bo_qua` là số đếm dòng bản chụp không vào danh sách, luôn tính kể cả khi bảng mã nhà xe rỗng (khi đó mọi dòng vào `khong_nha_xe`): `khong_nha_xe` (không có mã nhà xe đang dùng), `khong_ngay` (không có ngày đóng hợp lệ, hoặc trước 2020-01-01: `doixe._ngay` từ chối ngày đó nên một dòng gõ nhầm năm không được làm hỏng cả lượt gọi), `trung` (lặp cùng container và ngày).
- `xe`, `tai_xe`: chỉ xe và người đang dùng. Mảng `viec` sắp theo ngày đóng, container (tăng dần).
- `dem` đếm trên mảng `viec` trả về, **trừ việc `ngoai_khoang`** (chúng hiện trong `viec` nhưng không cộng vào bộ đếm nào, vì bấm bộ đếm là lọc trong khoảng đang xem; số của chúng ở `dem.ngoai_khoang`); việc cũ còn chờ (`cu`) có đếm: `sap_toi`, `cho_phan_xe`, `da_phan_xe`, `da_co_phi`, `da_len_bang_ke` là số việc theo trạng thái; `booking_doi` số việc có nhãn đổi; `chua_co_phi` số CHẶNG (mọi loại) chưa có phí; `khong_con_tren_booking` số chặng mồ côi; `ngoai_khoang` số việc không cộng vào; **[PR 2]** `chua_co_gia` số chặng của việc có đếm mà chưa có giá (`lai_gop.thieu` chứa `gia`), `ngoai_booking` số chặng ngoài booking. Hàng chờ ở đầu màn bấm là lọc phía giao diện trên các mảng này.

**`<việc>`:**

```json
{
  "id": "MAUU1000001|2026-11-19",
  "ngay_dong": "2026-11-19",
  "container": "MAUU1000001",
  "so_cont_la": false,
  "so_cont_goc": null,
  "trang_thai": "cho_phan_xe",
  "cu": false,
  "ngoai_khoang": false,
  "booking": {"kho": "…", "hang": "…", "cang": "…", "hang_tau": "…", "so_booking": "…", "khach": "…",
              "seal": "…", "nhiet_do": "…", "ten_tau": "…"},
  "hang_id": 12,
  "chang": [ <chặng>, ... ],
  "booking_doi": [{"chang_id": 12, "truong": "ngay_dong", "truoc": "2026-11-18", "sau": "2026-11-19"}],
  "ngay_dong_khac": ["2026-11-24"]
}
```

- `id`: `"<container>|<ngày đóng>"`; dòng chưa có số container: `"#<số dòng CONT_NGUON>|<ngày đóng>"`. Dùng làm khóa của dòng trên màn; không gửi lên máy chủ.
- `container`: số container chuẩn, viết hoa và bỏ khoảng trắng: bốn chữ cái rồi bảy chữ số (ĐÃ CHỐT ở `DOI-XE-DIEU-DO-01`: chưa có số container thì chưa phân xe được); hoặc `null` khi ô trống hoặc không đúng dạng đó. `null` thì chưa phân xe được, trạng thái `sap_toi`. Luật này chỉ cho đường đọc việc từ booking; chặng ngoài booking (`POST /chang`) giữ luật container của `luu_chang`.
- `so_cont_la`, `so_cont_goc`: ô Số cont không trống mà không đúng dạng chuẩn (chữ giữ chỗ như "chờ cont", "CHUA CO", số thiếu hoặc thừa ký tự) thì `so_cont_la` là `true` và `so_cont_goc` là chữ trong ô SAU KHI bộ đọc nguồn đã bỏ khoảng trắng và viết hoa ("chờ cont" thành `CHỜCONT`; không phải nguyên văn) để màn hiện cho điều xe thấy; việc vẫn `sap_toi`, không vào hàm nối, không phân xe được. Hai dòng cùng chữ giữ chỗ cùng ngày là hai việc riêng (`id` theo số dòng), không gộp. Ô trống: `so_cont_la` `false`, `so_cont_goc` `null`. Ý nghĩa dùng chung: cả hai ghi `ĐỀ XUẤT` tới khi người dùng xác nhận (Câu hỏi mở 8).
- `cu`: `true` khi việc có ngày đóng trước `tu` và còn chờ phân xe (chỉ có khi gọi với `cu` lớn hơn 0). `ngoai_khoang`: `true` khi việc nằm ngoài `tu`–`den` mà vẫn hiện vì giữ một chặng có ngày đóng trong khoảng (booking dời ngày đóng qua mép, kèm `booking_doi`); khác `cu` (việc `ngoai_khoang` có thể đã phân xe và có thể ở sau `den`).
- `booking.*`: chỉ xem, từ bản chụp, mỗi trường chuỗi hoặc `null`. Không có trường nào để ghi lại booking.
- `hang_id`: id chặng hàng gần nhất của việc; `null` khi chưa có.
- `chang`: các chặng đã nối, chặng hàng đứng đầu, rồi chặng phụ theo ngày chạy.
- `booking_doi`: `null` khi booking khớp chặng. Ngược lại là danh sách thay đổi trước → sau; `truong` là `ngay_dong` hoặc `kho`; so kho không phân biệt hoa thường và khoảng trắng thừa. Chỉ so chặng đã có ngày đóng. Cảng, hàng, hãng tàu không so được (chặng không lưu).
- `ngay_dong_khac`: ngày đóng của các việc khác CÙNG container trên booking (tối đa 20 ngày gần ngày đóng của việc nhất, xếp tăng dần). **Giao diện gửi nguyên mảng này vào `ngay_dong_khac` của `phan-xe`** để luật nối chọn đúng việc.

**`trang_thai` của việc** do API tính, không ai gõ, không lưu. Theo thứ tự thử:

| Giá trị | Điều kiện | Nhãn gợi ý |
| --- | --- | --- |
| `sap_toi` | Chưa có số container | Sắp tới (mờ, chưa phân xe được) |
| `cho_phan_xe` | Có số container, chưa có chặng hàng chưa bỏ | Chờ phân xe |
| `da_len_bang_ke` | Chặng hàng đã vào bảng kê đã gửi (`da_gui`) | Đã lên bảng kê |
| `da_co_phi` | Chặng hàng có phí (`co_phi`) hoặc đã hoàn (`da_hoan`) | Đã có phí |
| `da_phan_xe` | Chặng hàng có xe, chưa phí | Đã phân xe |

"Booking đã đổi" là nhãn kèm (`booking_doi` khác `null`), không thay trạng thái. "Chặng không còn trên booking" là mảng riêng `khong_con_tren_booking`. "Chặng ngoài booking" (chặng nhập tay hoặc có từ trước, ngày đóng `null`, không nối với việc nào, kể cả việc đã ẩn vì ngoài khoảng): **[PR 2]** mảng `ngoai_booking`, mỗi phần tử là một `<chặng>` kèm `"trang_thai": "ngoai_booking"`; gồm các chặng có ngày chạy trong khoảng đang xem (không áp `cu`). PR 1 chưa trả được vì `get_dieu_do` không liệt kê chúng.

**`<chặng>`** (một chặng, dùng trong `chang[]` và `khong_con_tren_booking[]`):

```json
{
  "id": 12, "loai": "hang", "ngay": "2026-11-19", "ngay_dong": "2026-11-19", "nguon": "dieu_do",
  "container": "MAUU1000001", "xe_id": 1, "tai_xe_id": 2, "tra": "nguoi", "nguoi_tra_id": 2,
  "noi_lay": null, "noi_ha": null, "kho": "…", "tinh": null, "ten_hang": null, "ghi_chu": null,
  "sau_khoa": false, "actor": "nv@gia", "actor_name": "nv", "luc": "2026-11-19T08:00:00+07:00",
  "co_phi": false, "da_hoan": false, "da_gui": false,
  "khoa": null,
  "cho_phep": {"doi_phan_cong": true, "bo_phan_cong": true}
}
```

- `loai`: `hang`, `chuyen_cang`, `tra_rong`, `rut_mooc`, `tha_mooc`, `khac`. `nguon`: `dieu_do`, `nhap`, `nap` hoặc `null` (chặng có trước điều độ). `ngay_dong` `null`: chặng chưa gắn ngày đóng.
- `khoa`: `null`, hoặc lý do điều độ không đổi, không bỏ được, theo thứ tự `CHANG_DA_GUI` → `CHANG_DA_HOAN` → `CHANG_CO_PHI` (cùng thứ tự máy chủ chặn). `cho_phep.doi_phan_cong` và `bo_phan_cong` đều bằng `khoa == null`. Chặng khóa thì giao diện hiện lý do bằng câu của mã đó và đổi theo luật điều chỉnh trong phiếu chặng.
- Mọi chặng của `khong_con_tren_booking` có thêm `"trang_thai": "khong_con_tren_booking"` và `cho_phep.chuyen_container` (`khoa == null`) cùng `cho_phep.giu_ngoai` (luôn `true`: giữ thành chặng ngoài booking không đụng tiền). Ba lựa chọn của người: chuyển sang container mới (`nhan-booking` `cap_nhat` kèm `container`), giữ ngoài booking (`giu_ngoai`), bỏ chặng (`bo-phan-cong`).
- **[PR 2]** thêm `thang_khoa`, `bang_ke_thang`, `chi`, `thu`, `lai_gop` (bản gọn), xem [dưới](#pr-2-thu-chi-lãi-gộp-của-chặng).

Giới hạn đã biết của đường đọc: (1) `get_dieu_do` tìm chặng mồ côi trong khoảng ngày đóng của các việc được gửi; khoảng không có việc nào thì không có mảng này. (2) Tối đa 1.500 việc có số cont mỗi lượt (kể cả việc láng giềng cùng container), quá thì `QUA_NHIEU_VIEC` (422): tham số `psql` có trần 128 KB. (3) Đường đọc tốn ba lượt psql (danh mục mã nhà xe; chặng nối việc, bỏ khi không việc nào có số cont; **[PR 2]** thu, chi, lãi gộp), mỗi lượt khoảng 50 ms trên `hao` cộng thời gian tính, chạy ở chế độ chỉ đọc (giao dịch `READ ONLY`, quá hạn báo `DB_UNAVAILABLE` chứ không phải `RESULT_UNKNOWN`); không có bộ nhớ đọc. (4) Việc trong ±10 ngày quanh khoảng xem cũng được gửi vào hàm nối (luật nối của SQL: chặng có ngày đóng nối việc lệch ≤ 3 ngày, `NGUON-CHUYEN-01`; chặng chưa có ngày đóng, như chặng nhập chi phí, nối theo ngày chạy lệch ≤ 10 ngày) nhưng chỉ hiện khi giữ một chặng có ngày đóng trong khoảng: booking dời ngày đóng qua mép khoảng (hoặc mép tháng) vẫn cho nhãn `booking_doi`, không biến chặng thành mồ côi; dời xa hơn 3 ngày thì SQL không nối nữa và chặng đúng là mồ côi. Chặng chưa có ngày đóng mà nối được một việc ẩn thì không hiện ở danh sách này (nó thuộc việc, nên hiện khi xem khoảng chứa việc đó) và không bị xếp `ngoai_booking`; việc đóng cách ngày chạy của nó hơn 10 ngày thì không nối, chặng đúng là ngoài booking. (5) Frontend phải chịu được khóa `chi`, `thu`, `lai_gop`, `thang_khoa`, `bang_ke_thang` VẮNG ở một chặng: ba lượt psql là ba ảnh chụp, một chặng bị bỏ giữa lượt nối và lượt thu chi thì còn trong `viec` mà không có phần tài chính (tải lại là hết). (6) Bản chụp chỉ giữ dòng `Loại = BIỂN` của `CONT_NGUON` (chuyến bộ ở `CONT_BO`, không phải việc của đội xe).

Lỗi riêng của đường đọc: `NGUON_THIEU_NHA_XE` (503: bản chụp chưa có cột Nhà xe; chờ lượt đồng bộ kế tiếp), `SHEET_SNAPSHOT_UNAVAILABLE` (503: không đọc được bản chụp), `QUA_NHIEU_VIEC` (422), `INVALID_MONTH`, `INVALID_DATE`, `INVALID_REQUEST` (422). Hai mã đầu, `QUA_NHIEU_VIEC` và `VIEC_KHONG_CON` có câu ngay trong code API, không đi qua DB.

### Bốn đường ghi

Cả bốn: `POST`, thân JSON, bắt buộc `idempotency_key`, kết quả `200` + JSON dưới đây (có thêm `lap_lai` khi gửi lại cùng mã). Sau khi ghi thành công giao diện tải lại `GET /chang` (kết quả ghi không đủ để dựng lại dòng).

**`POST /api/v7/doixe/chang/phan-xe`** — tạo chặng cho một việc (`nguon = dieu_do`). API kiểm trước khi ghi rằng cặp (`container`, `ngay_dong`) là một việc của đội xe trên bản chụp booking hiện tại (mã nhà xe đang dùng); không thì `VIEC_KHONG_CON` (409), không ghi gì, để gõ sai không tạo chặng mồ côi. Gửi lại cùng mã yêu cầu sau khi bản chụp đã đổi (ngày đóng hoặc số container khác) nhận `VIEC_KHONG_CON`: lần gửi đầu đã tạo đúng một chặng, lần sau không ghi gì; tải lại danh sách là thấy chặng đó (có thể kèm nhãn `booking_doi` hoặc nằm ở mồ côi). Lượt kiểm tốn thêm một lượt đọc danh mục mã nhà xe. Chặng ngoài booking (container nhà xe khác kéo, chuyển cảng...) không đi đường này mà đi `POST /api/v7/doixe/chang` (`luu_chang`) như hôm nay, với ngày đóng để trống.

| Trường | Bắt buộc | Kiểu và luật |
| --- | --- | --- |
| `container` | có | Chuỗi, ≤ 20 ký tự (như `chang.container`); rỗng hoặc `null` là `CONT_THIEU`. API so với booking bằng số container chuẩn (viết hoa, bỏ khoảng trắng, bốn chữ cái rồi bảy chữ số): chữ giữ chỗ không bao giờ khớp một việc nên bị `VIEC_KHONG_CON` |
| `ngay_dong` | có | Ngày đóng của việc (`viec.ngay_dong`) |
| `xe_id` | có | Id xe; `null` thì `XE_KHONG_RO` |
| `ngay` | không | Ngày chạy; mặc định ngày đóng |
| `loai` | không | Mặc định `hang`; loại khác thêm chặng phụ của việc (không giới hạn số chặng phụ, mỗi chặng một xe) |
| `tai_xe_id` | không | Mặc định tài xế của xe; xe không có tài xế thì người trả là công ty |
| `kho`, `noi_lay`, `noi_ha`, `tinh`, `ten_hang`, `ghi_chu` | không | Chuỗi ≤ 200 ký tự, không xuống dòng. Giao diện gửi `kho` = `booking.kho`, `ten_hang` = `booking.hang`; để trống `noi_lay` và `noi_ha` thì chặng hàng lấy tuyến của chuyến khách đã nối |
| `ngay_dong_khac` | không | Mảng ≤ 20 ngày: `viec.ngay_dong_khac` |

Kết quả: `{"ok": true, "chang_id": 12, "nguon": "dieu_do", "tra": "nguoi", "nguoi_tra_id": 2}`. Lỗi: `VIEC_KHONG_CON`, `CONT_THIEU`, `CHANG_HANG_DA_CO`, `XE_KHONG_RO`, `XE_NGUNG`, `NGUOI_NOT_FOUND`, `NGAY_TUONG_LAI`, `THANG_KHOA`, `TRUNG_CHANG`, `INVALID_DATE`.

**`POST /api/v7/doixe/chang/doi-phan-cong`** — đổi xe, tài xế, ngày chạy.

Thân: `chang_id`, `xe_id`, `tai_xe_id` (`null` được), `ngay`, và `truoc` = `{"xe_id", "tai_xe_id", "ngay"}` đúng cái màn đang thấy (khác hiện tại thì `CHANGED`). Người trả đang theo mặc định thì theo tài xế mới; người trả chỉnh tay giữ nguyên. Kết quả: `{"ok": true, "tra": "nguoi", "nguoi_tra_id": 3}` hoặc `{"ok": true, "khong_doi": true}`. Lỗi: `CHANGED`, `CHANG_NOT_FOUND`, `CHANG_DA_BO`, `CHANG_DA_GUI`, `CHANG_DA_HOAN`, `CHANG_CO_PHI`, `XE_KHONG_RO`, `XE_NGUNG`, `NGUOI_NOT_FOUND`, `NGAY_TUONG_LAI`, `THANG_KHOA_CHUYEN`, `TRUNG_CHANG`.

**`POST /api/v7/doixe/chang/bo-phan-cong`** — bỏ chặng. Thân: `chang_id`. Tháng mở: ẩn chặng (`"cach": "xoa"`); tháng khóa: gạch ngang kèm dòng trừ lại (`"cach": "bo"`). Kết quả: `{"ok": true, "cach": "xoa"}`. Lỗi: `CHANG_NOT_FOUND`, `CHANG_DA_BO`, `CHANG_DA_GUI`, `CHANG_DA_HOAN`, `CHANG_CO_PHI`.

**`POST /api/v7/doixe/chang/nhan-booking`** — người nhận thay đổi của booking cho một chặng. Hai kiểu:

- `{"chang_id", "kieu": "giu_ngoai"}`: giữ chặng thành chặng ngoài booking (ngày đóng về `null`). Không khóa khác.
- `{"chang_id", "kieu": "cap_nhat", "ngay_dong", ...}`: bắt buộc `ngay_dong`; tùy chọn `container` (chặng mồ côi sang container mới), `kho`, `noi_lay`, `noi_ha`, `ten_hang`, `tinh`. Khóa có mặt là đặt giá trị đó, `null` là xóa, khóa vắng là giữ nguyên. Không đổi tiền, xe, tài xế, ngày chạy. Chỉ ĐỔI CONTAINER bị chặn như đổi phân công (`CHANG_DA_GUI`, `CHANG_DA_HOAN`, `CHANG_CO_PHI`) và `THANG_KHOA` cho chặng ở tháng khóa. Giao diện nhận một thay đổi `booking_doi` thì gửi `ngay_dong` = `viec.ngay_dong` và `kho` = `viec.booking.kho` (khi có).

Kết quả `{"ok": true}` hoặc `{"ok": true, "khong_doi": true}`. Lỗi: `CHANG_NOT_FOUND`, `CHANG_DA_BO`, `CONT_THIEU`, `INVALID_DATE`, `CHANG_DA_GUI`, `CHANG_DA_HOAN`, `CHANG_CO_PHI`, `THANG_KHOA`, `TRUNG_CHANG`.

### Mã lỗi và câu thông báo

Năm mã mới của gói B1, cộng câu cho mã dùng lại. Câu nằm trong `web/v7_api_tables.py` (`ERRORS`), giao diện hiện đúng `message` trả về.

| Mã | Status | Câu |
| --- | --- | --- |
| `CHANG_HANG_DA_CO` | 409 | Việc này đã có chặng hàng. Tải lại để thấy xe đã phân. |
| `XE_NGUNG` | 422 | Xe này đã ngừng dùng. Chọn xe khác. |
| `THANG_KHOA` | 409 | Tháng này đã khóa: không phân thêm hay đổi chặng ở tháng khóa. |
| `CHANG_CO_PHI` | 409 | Chặng đã ghi phí: sửa xe hoặc tài xế bằng điều chỉnh ở phiếu chặng, không đổi ở phân công. |
| `CHANG_DA_HOAN` | 409 | Chặng đã được hoàn tiền cho tài xế: không đổi hay bỏ ở phân công. |
| `VIEC_KHONG_CON` (API, không qua DB) | 409 | Việc này không còn trên booking của đội xe (số container hoặc ngày đóng đã đổi). Tải lại danh sách. |
| `CHANG_DA_GUI` (đã có) | 409 | Chặng đã vào bảng kê đã gửi HTH: sửa bằng điều chỉnh ở bảng kê. |
| `CONT_THIEU`, `XE_KHONG_RO`, `XE_NOT_FOUND`, `NGUOI_NOT_FOUND`, `NGAY_TUONG_LAI`, `TRUNG_CHANG`, `THANG_KHOA_CHUYEN`, `CHANGED`, `CHANG_NOT_FOUND`, `CHANG_DA_BO`, `IDEMPOTENCY_CONFLICT` (đã có) | — | Câu hiện có |

### Quyền

Mọi đường đọc, ghi của mục Chặng cùng quyền với màn Đội xe hiện có: người dùng nằm trong danh sách cho phép (`ACCESS-01`); điều xe phải được thêm vào danh sách này trước khi dùng (việc cấu hình, ngoài gói này). `sokhach_app` chỉ gọi được năm hàm của gói B1 (`get_dieu_do`, `phan_xe`, `doi_phan_cong`, `bo_phan_cong`, `nhan_booking`) và **[PR 2]** `get_chang_tai_chinh`; không có quyền trên bảng; `nap_nha_xe` không cấp cho app và không có đường nào.

### [PR 2] Thu, chi, lãi gộp của chặng

Hàm SQL `doixe.get_chang_tai_chinh({"tu", "den", "ids"})` (chỉ đọc, cấp cho `sokhach_app`): `tu`, `den` cùng có hoặc cùng vắng (tối đa 400 ngày), `ids` là mảng id (tối đa 3.000); phải có khoảng hoặc `ids`; khóa lạ là `INVALID_COMMAND`. Trả `{"hom_nay", "chang": [...]}` các chặng chưa xóa, chưa bỏ có ngày chạy hoặc ngày đóng trong khoảng, hoặc có id trong `ids`; mỗi chặng là các trường của `<chặng>` ở trên cộng phần dưới. `GET /chang` gọi hàm một lượt sau `get_dieu_do`: `ids` là mọi chặng đang hiện (để chặng lệch ngày vẫn có số), khoảng là `tu`–`den` (để tìm chặng ngoài booking).

**Chọn đường đọc: bản gọn gộp vào `GET /chang`, bản đầy đủ ở `GET /chang/phieu?id=N`.** Cột Thu, Chi, Lãi gộp của mọi dòng cần có sẵn khi vẽ danh sách, nên bản gọn (mỗi chặng thêm khoảng 350 byte: tổng chi, cước, số đòi, lãi gộp) nằm trong `GET /chang`. Từng khoản chi và từng dòng thu (khoảng 150 byte mỗi khoản; một chặng có 3–8 khoản) chỉ cần khi mở phiếu, nên chỉ có ở `GET /chang/phieu?id=N`: danh sách một tháng (khoảng 200–400 chặng) không phình gấp đôi, và phiếu mở là một lượt đọc nhỏ cho đúng chặng đang xem nên số liệu phiếu luôn mới. Bản gọn bỏ `chi.dong`, `thu.dong`, `thu.loi`. (Kích thước là ước tính theo hình dạng JSON, chưa đo trên dữ liệu thật.)

**`GET /api/v7/doixe/chang/phieu?id=N`**: đúng một tham số `id`, số nguyên dương. Trả `{"hom_nay", "chang": <chặng đầy đủ>}`. Không còn chặng (đã xóa, đã bỏ): `CHANG_NOT_FOUND` (409, "Không còn chặng này. Tải lại."). Cùng quyền với mọi đường khác.

Phần tài chính của một chặng (trong `GET /chang` bỏ `dong` và `loi`):

```json
{
  "thang_khoa": false,
  "bang_ke_thang": "2026-11-01",
  "chi": {
    "dong": [{"khoan": "nang", "ten": "Nâng", "so_tien_vnd": "450000", "nguoi_tra": "nguoi", "nguoi_tra_id": 2, "chi_ho": false, "da_hoan": false},
             {"khoan": "vetc", "ten": "VETC", "so_tien_vnd": "80000", "nguoi_tra": "cong_ty", "nguoi_tra_id": null, "chi_ho": false, "da_hoan": null}],
    "tong_vnd": "530000", "chi_ho_vnd": "0", "ngoai_chi_ho_vnd": "530000"
  },
  "thu": {
    "cuoc": {"vnd": "9850500", "gia_bang_vnd": "9850500", "tay": false, "tuyen_id": 3, "tuyen": "…"},
    "ghep_vnd": "0", "ps_vnd": "1484000", "chi_ho_vnd": "1484000", "dc_vnd": null, "doi_vnd": "11334500",
    "dong": [{"khoan": "xi_cont", "ten": "Xí cont", "so_luong": null, "muc_vnd": null, "so_tien_vnd": "250000", "chi_ho": true, "cot": "ps", "la": false}],
    "loi": [{"goc": "_ Cân", "loi": "Thiếu số tiền (ví dụ 200k)"}],
    "chua_doc": 1
  },
  "lai_gop": {"thu_vnd": "9850500", "chi_vnd": "530000", "lai_vnd": "9320500", "thieu": []}
}
```

- **Chi** (`chi.dong`): từng khoản của chặng `{khoan, ten, so_tien_vnd, nguoi_tra, nguoi_tra_id, chi_ho, da_hoan}`; tiền là tổng mọi dòng của chặng (dòng gốc, điều chỉnh, trừ lại), nên cộng lại bằng `get_so`. `nguoi_tra`: `cong_ty` nếu loại phí do công ty trả (VETC) hoặc chặng do công ty trả, ngược lại `nguoi` kèm `nguoi_tra_id` của chặng. `chi_ho`: cờ chi hộ của loại phí. `da_hoan`: `true` khi mọi dòng chứa khoản đã nằm trong một đợt hoàn chưa hủy; `null` (không áp dụng) với khoản công ty trả. Sắp theo thứ tự danh mục. Chặng chưa có phí: `dong` rỗng và `tong_vnd`, `ngoai_chi_ho_vnd` là `null` (không phải `"0"`).
- **Thu** (`thu`): `null` khi chặng không vào bảng kê (chưa có xe, hoặc xe thuê ngoài). Chặng chưa gửi lấy từ `doixe._tinh_chang` (đúng hàm bảng kê dùng); chặng đã gửi lấy dòng bảng kê đã chép lúc gửi, nên đổi giá hay sửa ghi chú sau đó không đổi số. `cuoc.vnd` là `null` khi chưa có giá (không phải 0); `cuoc.tay` là giá nhập tay. `doi_vnd` là số đòi HTH của chặng, **cộng đúng như `get_bang_ke`**: cước + đóng ghép + phát sinh + điều chỉnh bảng kê (`dc_vnd`, `null` khi chưa có); cước trống góp 0. `chi_ho_vnd` là phần phát sinh chi hộ. Mỗi dòng phát sinh `{khoan, ten, so_luong, muc_vnd, so_tien_vnd, chi_ho, cot, la}`: `khoan` là mã danh mục phát sinh (`null` với khoản lạ, `la: true`); `cot` là `ps` hoặc `ghep`. Mô hình hiện tại chỉ lưu số tiền của khoản ghi chú, nên `so_luong` chỉ có với khoản lấy từ ô số lượng của chặng chưa gửi (neo, nổ máy) và `muc_vnd` luôn `null` cho tới gói B3. `loi` là các khoản ghi chú đọc không được `{goc, loi}`; `chua_doc` là số khoản đó.
- **Lãi gộp** (`lai_gop`): `thu_vnd` = số đòi − phát sinh chi hộ (cước + ghép + phát sinh không chi hộ + điều chỉnh), `chi_vnd` = tổng chi − chi hộ, `lai_vnd` = `thu_vnd − chi_vnd`. Mỗi số là `null` (không phải `"0"`) khi chưa tính được; `thieu` nói vì sao: `gia` (chưa có giá), `phi` (chưa có phí), `doc` (còn khoản ghi chú chưa đọc được, thu có thể thiếu), `khong_vao_bang_ke` (không có thu). `lai_vnd` chỉ có khi `thieu` rỗng.
- `thang_khoa`: ngày chạy của chặng ở tháng đã khóa. `bang_ke_thang`: tháng của bảng kê chứa chặng (đã gửi: tháng bảng kê đó; chưa gửi: tháng gom, có thể là tháng sau tháng chạy khi bảng kê tháng chạy đã gửi); `null` khi không vào bảng kê. `da_hoan`, `da_gui`, `co_phi` như `<chặng>`.

Bất biến cộng lại (kiểm ở harness PostgreSQL, dữ liệu giả): tổng `chi.dong[].so_tien_vnd` của khoản `nguoi_tra = nguoi` theo người và tháng chạy bằng đúng `get_so(...).the.chi_vnd`; tổng `thu.doi_vnd`, `thu.cuoc.vnd`, `thu.ghep_vnd`, `thu.ps_vnd`, `thu.chi_ho_vnd` của các chặng cùng `bang_ke_thang` bằng đúng `get_bang_ke(...).tong` (`doi_vnd`, `cuoc_vnd`, `ghep_vnd`, `ps_vnd`, `chi_ho_vnd`), cả lúc đang gom lẫn sau khi gửi. Ngoại lệ: dòng bảng kê đã gửi mà chặng sau đó bị xóa hoặc bỏ (`chang_con = false` ở `get_bang_ke`) còn trong tổng của bảng kê nhưng hàm này không liệt kê chặng đã bỏ, nên tổng thu của hàm thấp hơn đúng phần của chặng đó (harness có một ca cho việc này). `thu.muc_vnd` của từng dòng phát sinh luôn `null` cho tới gói B3.

## Nguồn quyết định

- [`DOI-XE-CAU-TRUC-01`](../docs/decisions/doi-xe-cau-truc-01.md): mục Chặng thay Điều độ, sổ người, sổ xe, bảng chặng của Bảng kê; phiếu chặng có phân công, chi, thu, lãi gộp.
- [`DOI-XE-DIEU-DO-01`](../docs/decisions/doi-xe-dieu-do-01.md): chặng sinh từ booking; hành vi phân công, đổi, bỏ, nhận thay đổi; so nguyên mã nhà xe; seal, nhiệt độ, tên tàu chỉ xem.
- [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md), [`DOI-XE-THU-01`](../docs/decisions/doi-xe-thu-01.md): luật tiền, khóa tháng, hoàn, bảng kê. Giữ nguyên.
- `DOI-XE-MO-HINH-01` (spec `doi-xe-mo-hinh-01.md`, PR riêng): hình dạng thu và chi theo mô hình mới. Các migration đổi mô hình (gói B3) chưa làm.
- [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md): luật nối ±3 ngày theo container.

## Hành vi và bất biến

- Web không ghi Google Sheet, không ghi vào schema `sokhach`. Máy không tự tạo, sửa, xóa chặng: mọi chặng do người bấm, có ghi người làm và Lịch sử trước → sau.
- Việc của đội xe là dòng booking có mã nhà xe nằm NGUYÊN trong `doixe.ma_nha_xe` đang dùng (cắt khoảng trắng hai đầu, phân biệt hoa thường, không so chuỗi con). Mã thật chỉ ở cơ sở dữ liệu trên `hao`; test dùng mã giả.
- Dòng booking chưa có số container hiện là "sắp tới", không bao giờ gửi vào hàm nối, không phân xe được.
- Bộ đọc nguồn: thiếu một trong bốn cột mới thì ô đó trống, luồng sổ khách đang chạy không đổi; `columns` trong bản chụp ghi cột nào có, để API phân biệt "chưa có cột" với "chưa điền".
- VND nguyên chính xác, ô trống là NULL, không phải 0. Luật tiền, khóa tháng, hoàn, bảng kê của đợt 1–2 không đổi; không đổi hàm ghi tiền hiện có.
- Chặng đã có phí, đã hoàn hoặc đã lên bảng kê đã gửi không đổi, không bỏ ở phân công (máy chủ chặn bằng mã riêng; `khoa` cho giao diện biết trước).
- Bấm lặp hoặc gửi lại sau mất mạng cùng mã yêu cầu chỉ tạo một chặng.
- Booking đổi không làm đổi tiền đã ghi và không đổi bảng kê đã gửi: chỉ hiện nhãn `booking_doi`.

## Tiêu chí nghiệm thu

- [ ] `npm run check` xanh; test đơn vị API (dữ liệu giả, mã nhà xe giả): mã trùng một phần chữ không bị bắt nhầm; dòng booking chưa có số container; bấm lặp cùng mã yêu cầu; thiếu quyền; thiếu cột nhà xe; khoảng ngày sai; kiểm đầu vào từng đường ghi.
- [ ] Test bộ đọc nguồn: bốn cột tìm theo tên; thiếu cột thì trống; `columns` đúng.
- [x] **[PR 2]** Harness PostgreSQL `tools/test_pg_doixe_chang.py` (19/11/2026, DB giả dùng một lần): tổng chi theo tháng từ hàm mới bằng đúng `get_so` từng người trả; tổng thu bằng đúng `get_bang_ke` (`doi_vnd`, `cuoc_vnd`, `ghep_vnd`, `ps_vnd`, `chi_ho_vnd`, số chặng) lúc đang gom và sau khi gửi; `v7_app` gọi được hàm mới, không có quyền trên bảng; chuỗi `--migration-test` có file mới.
- [ ] Chưa kiểm trên `hao` thật: bản chụp booking có bốn cột, bảng `ma_nha_xe` đã nạp, API đọc đúng việc (việc của phiên điều phối khi triển khai).
- [ ] Frontend (gói F2, không thuộc spec này): bàn phím, nhập sai, bấm lặp, tải chậm, mất mạng, thiếu quyền; điều xe tự đi hết luồng trên bản thử.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`); phiên thực thi Sonnet 5.5, effort high.
- Review: opus (đường ghi, nối với schema `doixe`).
- Được sửa: `specs/doi-xe-chang-01.md`, `specs/README.md` (một dòng), `cong-no-web-handoff/web/v7_api_doixe.py`, `web/v7_api_tables.py`, `web/v7_ledger_api.py` (định tuyến), `tools/webdebit_export_connector.py`, `tests/test_v7_api_doixe*.py`, `tests/test_webdebit_export_connector.py`. PR 2 thêm: migration `2026-11-19-v7-doi-xe-tai-chinh-chang.sql` (chỉ có hàm đọc), `tools/test_pg_doixe_chang.py`, chuỗi `check_migration` của `tools/test_pg_v7_backend.py`, `.github/workflows/test.yml`, `docs/development.md` (một dòng), `schema/v7_schema_current.pgsql` (sinh tự động; chỉ chụp `sokhach` nên không đổi).
- Cấm: sửa `preview/`, migration cũ, `docs/decisions*`; chạy DDL, nạp dữ liệu hay ssh `hao`; ghi Google Sheet; chép tên khách, biển số, container, mã nhà xe, số tiền thật vào repo; merge.

## Hoàn tác

Revert PR. Không có dữ liệu mới. Bản chụp booking đã có thêm khóa `columns` và bốn trường mỗi dòng: bản cũ của API bỏ qua chúng.

## Bằng chứng

PR 1, ngày 19/11/2026, ở máy dev, dữ liệu giả: `unittest` của `tests/test_v7_api_doixe.py`, `tests/test_v7_api_doixe_chang.py`, `tests/test_webdebit_export_connector.py`; `npm run check` (xem mô tả PR). PR 2, cùng ngày: `tools/test_pg_doixe_chang.py` (pass: thêm các ca hoàn rồi hủy, giá tay, khoản lạ, chặng đã gửi rồi bị bỏ, tổng chi công ty trả, định nghĩa các hàm cũ không đổi sau migration), `test_pg_doixe.py`, `test_pg_doixe_thu.py`, `test_pg_doixe_dieu_do.py` (pass, không hồi quy), `test_pg_v7_backend.py --migration-test` (pass), `v7_schema_snapshot.py` (không đổi file). Chưa chạy trên bản sao hay `hao`; chưa có bản chụp thật có bốn cột.

## Câu hỏi mở

1. **Chặng ngoài booking** (ngày đóng `null`) không có trong `get_dieu_do`: PR 2 lấy chúng từ hàm đọc mới (ngày chạy trong khoảng đang xem). Phiên điều phối xác nhận đó là chỗ đúng, hay muốn sửa `get_dieu_do` (migration riêng)?
2. **Tên hàng:** bản chụp chỉ giữ `Mặt hàng` (`commodity`) và loại sầu riêng, không giữ cột `Tên hàng` gốc. `booking.hang` dùng `Mặt hàng`. Cần tên hàng gốc thì thêm một trường vào bộ đọc (một PR riêng, đổi hình dạng bản chụp).
3. **Mã nhà xe phân biệt hoa thường** (chỉ cắt khoảng trắng hai đầu), theo "so nguyên mã". Nếu Sheet có thể gõ khác hoa thường cùng một mã thì phải đổi luật.
4. **Cảng, hàng, hãng tàu đổi sau khi phân xe** không báo được `booking_doi` vì chặng không lưu các trường đó. Chỉ ngày đóng và kho. Có cần mở rộng không?
5. **Ba lượt psql** cho một lần đọc `GET /chang` (danh mục mã nhà xe; chặng nối việc; thu, chi, lãi gộp), mỗi lượt khoảng 50 ms trên `hao` cộng thời gian tính (`get_bang_ke` tính sống cả tháng cũng làm đúng việc này). ĐÃ ĐO 19/11/2026 trong harness (DB giả dùng một lần, máy dev, 240 chặng một tháng, phiên psql mới mỗi lượt): `get_chang_tai_chinh` khoảng 0,5 giây trong DB; `get_dieu_do` với 240 việc khoảng 0,09 giây; cả `GET /chang` ba lượt cỡ 0,65 giây chưa kể Python. Dưới 1 giây nhưng thu, chi, lãi gộp chiếm gần hết: chưa đo trên dữ liệu thật của `hao`. Nếu chậm hơn, hướng tối ưu là tính phần chi và thu tách khỏi `_chang_dd`, hoặc tách hàm để danh sách chỉ tính tổng (bản gọn hiện chỉ bớt kích thước JSON, không bớt việc tính trong DB); giữ danh mục mã vài chục giây hoặc gộp ba lượt vào một là phần nhỏ.
6. **Việc cũ còn chờ** lấy bằng tham số `cu` (tối đa 92 ngày) thay vì "mọi việc cũ": việc chờ quá 92 ngày không hiện. Phù hợp thực tế (việc được giao trước một ngày) nhưng chưa đo trên dữ liệu thật.
7. Giao diện gửi `kho` và `ten_hang` từ booking lên `phan-xe` và để trống `noi_lay`, `noi_ha` (SQL lấy tuyến chuyến khách); là cách API hiểu "lấy từ booking" của `DOI-XE-DIEU-DO-01`. Đúng ý chưa?
8. **Số container giữ chỗ (ĐỀ XUẤT, quyết định của phiên điều phối 19/11/2026; chờ người dùng xác nhận):** ô Số cont chỉ được coi là có số khi đúng dạng chuẩn (bốn chữ cái rồi bảy chữ số sau khi bỏ khoảng trắng và viết hoa); ô không trống mà sai dạng thì việc `sap_toi` kèm `so_cont_la` và chữ nguyên văn, để điều xe thấy. Đổi lại, một số container gõ sai nhẹ (thiếu hoặc thừa một chữ số) cũng không phân xe được cho tới khi Sheet sửa. Bộ đọc sổ khách vẫn nhận mọi chuỗi không trống làm số container (luật riêng của sổ khách, không đổi ở đây); chưa đo trên bản chụp thật có bao nhiêu dòng sai dạng.
9. **"Chưa nối chuyến khách"** (hàng chờ trong bản bấm thử) cần `doixe._chuyen` cho từng chặng hàng; hàm PR 2 chưa trả cờ này vì ngoài phần thu, chi, lãi gộp đã giao. Cần cho F2 thì thêm trường `chuyen_khach` vào hàm (migration chỉ-đọc nhỏ).
10. **Tổng chi và công ty trả:** `chi.tong_vnd` tính cả khoản công ty trả (VETC) để lãi gộp đúng chi phí đội xe; chi của người trả khớp `get_so` chỉ gồm khoản `nguoi_tra = nguoi`. Giao diện cần hiện hai số này khác nhau ở đâu thì phiên F2 nói.
11. **Lãi gộp `null` khi còn khoản ghi chú chưa đọc được** (`thieu` có `doc`): chọn thận trọng vì thu có thể thiếu; nếu muốn tính tạm thì đổi luật, không phải lỗi dữ liệu.
