# Đội xe: mô hình dữ liệu mới theo hướng A (DOI-XE-MO-HINH-01)

Trạng thái: **ĐỀ XUẤT** (Claude, 19/11/2026), gói M1 của [spec điều phối](doi-xe-cau-truc-01.md). Hướng ĐÃ CHỐT (người dùng, 19/11/2026, "Chốt theo hướng A"; `DOI-XE-CAU-TRUC-01`): người trả theo từng khoản chi, khoản thu là dòng riêng, một cơ chế công nợ chung, chi gắn được vào xe. **Luật tiền chi tiết dưới đây chưa ai chốt**: người dùng chốt ở mục [Cần người dùng chốt](#cần-người-dùng-chốt) trước khi viết migration đầu tiên. Luật tiền hiện hành (công thức số dư, hoàn theo đợt, hủy bắt buộc lý do, khóa tháng, bảng kê gửi → đối chiếu → tiền về, chi hộ) **giữ nguyên** tới khi người dùng chốt khác; mọi bước chuyển dưới đây phải chứng minh được là không đổi số.

Phiên viết spec chỉ đọc code và tài liệu: không chạy DDL, không mở `hao`, chưa đo trên bản thử. Điều gì phải đo trước khi chạy ghi ở [Bằng chứng](#bằng-chứng).

## Đã biết và giả định

| ĐÃ BIẾT (đọc DDL tại `main` `3c8e4a0`, 19/11/2026) | Nguồn |
| --- | --- |
| `doixe.loai_phi` có 16 khoản chi: 15 từ đợt 1 (`nang`, `nangha`, `cau`, `neo`, `xi`, `dao`, `moi`, `doi`, `seal`, `bai`, `dieu`, `dau`, `ps`, `may`, `vetc`) và `hasom` từ migration phiếu chi. `cot_sheet` UNIQUE 0–28, `hasom` để NULL. `cong_ty_tra` chỉ `vetc` = true. `chi_ho` thêm ở đợt 2, mặc định true cho `xi`, `moi`, `hasom` | `2026-11-18-v7-doi-xe.sql`, `-phieu-chi.sql`, `-thu.sql` dòng 35–44 |
| `doixe.phat_sinh` có 14 khoản thu; 10 có `loai_phi`, 4 không (`can`, `dong_an`, `lay_xa`, `dong_ghep`); hai khoản (`kiem_hoa`, `ha_som`) cùng trỏ `hasom`; 9 khoản chi khác nhau được nối | `-thu.sql` dòng 119–137 |
| Số dư người nhận ứng `_so_du` = số dư đầu + tiền các dòng của chặng có `nguoi_tra_id` = người đó (bỏ loại `cong_ty_tra`, bỏ chặng `da_xoa`) − đợt hoàn chưa hủy − ứng chưa hủy | `doi-xe.sql` dòng 326–338 |
| Người trả là cột của **chặng** (`tra`, `nguoi_tra_id`, CHECK hai cột khớp nhau) cộng cờ của **loại phí** (`cong_ty_tra`); `ghi_hoan` chỉ nhận dòng của chặng có `nguoi_tra_id` = người nhận | `doi-xe.sql` dòng 97–110, 893–897 |
| Đơn vị chờ hoàn là `dong` (một dòng gốc mỗi chặng: `dong_mot_goc`), `dot_hoan.dong_ids` là mảng id `dong` | `doi-xe.sql` dòng 73–88, 132 |
| Phát sinh thu đọc từ `chang.ghi_chu` bằng `doixe._doc_ghi_chu` (và `_ps_tu_o` cho `neo_ngay`, `may_gio`) mỗi lần tính `_tinh_chang`. `sua_chang` ghi đè `ghi_chu` ở mọi tháng (chỉ cột `ngay` có chặn chuyển tháng khóa) | `-thu.sql` dòng 333–517; `-phieu-chi.sql` dòng 178–183 |
| `sua_chang`, `xoa_chang` của đợt 1 và phiếu chi **không** tham chiếu `bang_ke_dong`. Điều độ (bản nháp chưa commit) chỉ chặn `CHANG_DA_GUI` ở `doi_phan_cong`, `bo_phan_cong`, `nhan_booking`; thân `xoa_chang` chuyển nguyên sang `_xoa_chang_thuc` | grep `bang_ke_dong` trong `-phieu-chi.sql`: 0 kết quả |
| `bang_ke_dong` là bản chép lúc gửi (`bang_ke_dong_chi_them` chặn sửa, xóa); số đòi của bảng kê đã gửi = tổng cột `cuoc_vnd` + `ghep_vnd` + `ps_vnd` + `dieu_chinh_bk` − `tien_ve` chưa hủy, không đọc lại `chang` | `-thu.sql` dòng 173–192, 520–530 |
| `ben.xe_thue_ngoai boolean NOT NULL UNIQUE` chọn chặng vào bảng kê: `_chang_gom` lọc `x.thue_ngoai = ben.xe_thue_ngoai`. Hiện một dòng `ben` (HTH, xe không thuê ngoài); chặng của xe thuê ngoài không vào bảng kê nào | `-thu.sql` dòng 47–56, 477–484 |
| Khóa tháng chi là `thang_khoa` (không dòng: chỉ tháng hiện tại mở). Thu có vòng đời riêng: đang gom → `da_gui` → `da_doi_chieu` → thu đủ. `_thang_gom` có thể đẩy chặng sang tháng kế khi bảng kê tháng của nó đã gửi | `doi-xe.sql` dòng 145–151, 209–213; `-thu.sql` dòng 467–475 |
| Web sửa được danh mục thu: lệnh `luu_phat_sinh` (mức, cách tính, `chi_ho`, `cot`) | `-thu.sql` dòng 1085 |
| `doixe._chung()` trả `cot_sheet` cho web; đường dán 29 cột đọc `p.cot_sheet` | `doi-xe.sql` dòng 406–423; `preview/doi-xe-model.js` dòng 175 |

| GIẢ ĐỊNH (chưa kiểm trên dữ liệu thật; migration phải tự kiểm và dừng nếu sai) |
| --- |
| Hai cờ `chi_ho` của cặp khoản nối được (chi và thu) giống nhau. Theo giá trị mặc định thì giống ở cả 9 cặp, nhưng `luu_phat_sinh` cho sửa cờ phía thu, nên trên `hao` có thể đã lệch |
| Mỗi (chặng, loại phí) chỉ có một người trả. Chưa thấy dữ liệu nào cần chia; chưa ai xác nhận |
| Số chặng chưa gửi bảng kê có khoản trong ghi chú mà bộ đọc gắn lỗi (`loi`) chưa đếm |
| Bản thử trên `hao` chưa có lần ứng, đợt hoàn hay người đi lệnh nào (theo audit 19/11/2026), nên bất biến số dư mới chỉ chứng minh được trên dữ liệu giả của harness |

Chỗ DDL thật khác với mô tả ở bối cảnh: không có chỗ sai, chỉ thêm hai chi tiết. (1) `loai_phi.chi_ho` và `phat_sinh.chi_ho` đều tồn tại nhưng có thể không còn khớp vì chỉ phía thu có màn sửa. (2) `sua_chang` cũng không chặn sửa `ngay`, `container`, `loai`, `xe_id` của chặng đã gửi bảng kê: lỗ thứ hai rộng hơn chỉ `xoa_chang`.

## Người dùng và luồng

Spec này đổi **dữ liệu và luật ghi**, không đổi bố cục màn (bố cục thuộc bản bấm thử T1 và gói F). Người thao tác vẫn là điều xe, hai nhân viên nhập chi phí, kế toán, người quản lý (theo điều phối). Tác động nhìn thấy:

- Nhập chi: mỗi khoản chọn "ai trả" (mặc định theo chặng, VETC mặc định công ty).
- Nhập thu: phát sinh là từng dòng "khoản · số lượng · tiền" thay cho chữ `_ Tên khoản số`.
- Công nợ: một danh sách đối tác; nơi bán dầu, gara thêm vào mà không có bảng riêng.
- Chặng đã gửi bảng kê: sửa nhận dạng và xóa bị chặn đồng nhất ở mọi màn.

CÒN MỞ: chưa hỏi điều xe, nhân viên, kế toán về các luồng này.

## Đầu ra

Spec mô hình dữ liệu và thứ tự migration đủ để người dùng chốt luật tiền, rồi phiên thực thi viết từng migration (gói B3–B5 của điều phối) mà không phải đoán. Không có code, migration hay dữ liệu trong PR này.

## 1. Danh mục khoản chung

**Hiện có → đề xuất.** Hai danh mục (`loai_phi` chi, `phat_sinh` thu) thành một bảng `doixe.khoan`:

| Cột đề xuất | Nghĩa | Lấy từ |
| --- | --- | --- |
| `ma` (PK) | mã khoản; giữ nguyên mã `loai_phi` khi nối được, để `dong_phi.loai_phi` không phải đổi giá trị | `loai_phi.ma`, `phat_sinh.ma` |
| `ten`, `ten_day_du` | nhãn | cả hai |
| `huong` | `chi`, `thu` hoặc `ca_hai` | mới |
| `cach`, `muc_vnd`, `muc_them_vnd` | cách tính phía thu (`co_dinh`, `theo_ngay`, `theo_don_vi`, `nhap_tay`) và mức; NULL ở khoản chỉ chi | `phat_sinh` |
| `chi_ho` | **một** cờ chi hộ | `loai_phi.chi_ho`, `phat_sinh.chi_ho` |
| `cot_bang_ke` | `ps` hoặc `ghep` (khoản thu nằm cột nào của bảng kê) | `phat_sinh.cot` |
| `tra_mac_dinh` | `theo_chang` hoặc `cong_ty` (thay `cong_ty_tra`) | `loai_phi.cong_ty_tra` |
| `thu_tu_chi`, `thu_tu_thu` | thứ tự hiện trên từng màn (hai thứ tự khác nhau, VETC đứng cuối phía chi) | `thu_tu` của hai bảng |
| `dang_dung` | ngừng dùng thay xóa | mới |

`phat_sinh_ten` (tên đọc được trong ghi chú) đổi thành `khoan_ten(ten, khoan)`, chỉ đường dán còn dùng. `loai_phi.cot_sheet` **rời** danh mục: thành bảng `doixe.cot_sheet_dan(cot int PK CHECK 0..28, khoan text)` của đường dán chuyển dữ liệu cũ; `_chung()` vẫn trả `cot_sheet` (nối từ bảng này) nên web hiện tại không vỡ.

**Bảng ánh xạ đủ 30 khoản** (16 chi + 14 thu → 20 khoản mới = 16 + 14 − 10 mối nối, trong đó `hasom` hấp thụ hai khoản thu):

| Khoản mới | `huong` | Từ `loai_phi` (chi) | Từ `phat_sinh` (thu) | `chi_ho` | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| `nang` | chi | `nang` | — | không | |
| `nangha` | ca_hai | `nangha` | `nang_ha` | không | thu nhập tay |
| `cau` | chi | `cau` | — | không | |
| `neo` | ca_hai | `neo` | `neo` | không | thu theo ngày |
| `xi` | ca_hai | `xi` | `xi_cont` | có | |
| `dao` | chi | `dao` | — | không | |
| `moi` | ca_hai | `moi` | `cont_moi` | có | |
| `doi` | chi | `doi` | — | không | |
| `seal` | ca_hai | `seal` | `mua_seal` | không | |
| `bai` | ca_hai | `bai` | `bai_cho` | không | |
| `dieu` | ca_hai | `dieu` | `dieu_do` | không | |
| `dau` | chi | `dau` | — | không | còn ở dòng chặng; chi dầu theo xe xem mục 5 |
| `ps` | chi | `ps` | — | không | chi tổng hợp, giữ nguyên |
| `may` | ca_hai | `may` | `no_may` | không | thu theo đơn vị (giờ); tiền chi nổ máy còn mở ở [`CHI-PHI-XE-01`](chi-phi-xe-01.md) câu 6 |
| `vetc` | chi | `vetc` | — | không | `tra_mac_dinh` = `cong_ty` |
| `hasom` | ca_hai | `hasom` | `kiem_hoa`, `ha_som` | có | hai khoản thu thành một khoản; chữ "Kiểm hoá"/"Hạ sớm" giữ ở `dong_thu.nhan` (mục 3); ba tên trong `khoan_ten` |
| `can` | thu | — | `can` | có | chi hộ phía thu, không có khoản chi tương ứng (khớp hiện trạng) |
| `dong_an` | thu | — | `dong_an` | không | |
| `lay_xa` | thu | — | `lay_xa` | không | |
| `dong_ghep` | thu | — | `dong_ghep` | không | `cot_bang_ke` = `ghep` |

Thêm đúng một khoản `khac_thu` (thu, nhập tay, không chi hộ) cho "khoản lạ" mà bộ đọc ghi chú hiện vẫn tính; không có khoản này thì khoản lạ không có chỗ ở trong dòng thu. Danh mục thành 21 khoản.

**Cờ chi hộ còn một chỗ.** Migration kiểm từng cặp nối được: hai cờ cũ khác nhau thì **dừng và liệt kê** (không tự chọn), người dùng chốt cờ đúng. `luu_phat_sinh` đổi thành `luu_khoan` (cùng kiểm hình dạng, Lịch sử `luu_khoan`); `loai_phi` và `phat_sinh` còn lại là **view** cùng tên cột cũ trong các bước giữa để hàm cũ chưa viết lại vẫn chạy, view bỏ ở bước cuối.

**Tác động tới dữ liệu cũ:** `dong_phi.loai_phi`, `dong.dc_phi` đổi khóa ngoại sang `khoan(ma)`, giá trị giữ nguyên (mã `loai_phi` là mã chuẩn) nên không sửa dòng nào. `bang_ke_dong.ps` (jsonb, bản chép, không sửa được) còn mã `phat_sinh` cũ: giữ bảng `khoan_ma_cu(ma_cu, khoan)` cho ai đọc bản chép (xuất Excel, đối soát).

## 2. Người trả theo từng khoản chi

**Hiện có → đề xuất.**

| Hiện có | Đề xuất |
| --- | --- |
| `chang.tra`, `chang.nguoi_tra_id`: một người trả cả chặng | **Giữ** làm "người trả mặc định" khi thêm khoản mới (điều độ `phan_xe`, `doi_phan_cong` đang đọc và ghi hai cột này). Không còn cột nào của chặng được dùng để tính tiền |
| `loai_phi.cong_ty_tra` (chỉ `vetc`) làm `_so_du`, `_tien_dong` bỏ khoản này | `khoan.tra_mac_dinh = 'cong_ty'`; khoản VETC nằm ở dòng có `tra = 'cong_ty'` nên không cần cờ khi tính |
| `dong`: không có người trả; một dòng gốc mỗi chặng | thêm `tra`, `nguoi_tra_id` (CHECK `(tra = 'nguoi') = (nguoi_tra_id IS NOT NULL)`, như `chang`); đổi `dong_mot_goc` thành một dòng gốc mỗi **(chặng, người trả)** |
| `dong_phi (dong_id, loai_phi)` | PK giữ; một khoản của một chặng chỉ nằm ở một dòng gốc (hàm ghi bảo đảm, harness kiểm: giả định "không chia khoản cho hai người") |
| `dot_hoan.dong_ids`, `dong.dot_hoan_id` | **không đổi cấu trúc**; đơn vị chờ hoàn vẫn là `dong`, nhưng nay mỗi dòng có đúng một người trả nên chặng có hai người trả sinh hai dòng chờ hoàn, mỗi dòng ở danh sách của một người |
| `ghi_hoan` kiểm `c.nguoi_tra_id = v_nguoi` | kiểm `dd.nguoi_tra_id = v_nguoi`; `_tien_dong` không đổi vì VETC đã nằm ở dòng công ty |
| `dong.loai = 'dieu_chinh'` (tháng khóa, đã hoàn) | dòng điều chỉnh mang người trả **của khoản bị sửa** (tra cứu từ dòng khoản hiện có; khoản chưa có dòng thì lấy mặc định) |
| `dong.loai = 'tru_lai'` (bỏ chặng ở tháng khóa hoặc đã hoàn) | một dòng trừ lại **cho mỗi người trả** có tiền trong chặng, mỗi dòng trừ đúng tổng từng khoản của người đó |

**Cách chuyển một lần** (theo thứ tự, trong một giao dịch):

1. Thêm `dong.tra`, `dong.nguoi_tra_id`; điền: dòng của chặng `tra = 'nguoi'` lấy người trả của chặng; dòng của chặng `tra = 'cong_ty'` lấy công ty.
2. Dòng nào đang chứa khoản `vetc`: tạo dòng mới cùng `chang_id`, `loai`, `tra = 'cong_ty'`, chuyển các `dong_phi` VETC sang (đổi `dong_id`). Dòng mới `dot_hoan_id` NULL, đúng vì VETC chưa từng vào phần hoàn. `dot_hoan.tong_dong_vnd` đã lưu không đổi vì `_tien_dong` vốn không tính VETC.
3. Đổi `dong_mot_goc`; viết lại `_so_du`, `ghi_hoan`, `_chang_ds`, `get_so`, `get_tong`, `luu_chang`, `sua_chang`, `xoa_chang` (trong `luu_chang`, `phi` nhận thêm người trả từng khoản, mặc định như trên).

**Đổi người trả.** Cột `nguoi_tra` của `sua_chang` (cả chặng) giữ ý nghĩa cũ: đổi mặc định và chuyển các khoản **đang theo mặc định**, giống cách `doi_phan_cong` đang làm. Cột mới `nguoi_tra:<mã khoản>` đổi người trả một khoản. Cả hai chặn `KHONG_DOI_NGUOI_TRA` khi tháng khóa hoặc dòng chứa khoản đã hoàn (giữ luật hiện tại; có mở thêm "bút toán chuyển" hay không: câu 2).

**Bất biến phải chứng minh (B-1).** Với **mọi** người nhận ứng và mọi tháng `m`: `_so_du(người, m)` trước chuyển = sau chuyển, cùng số lượng dòng chờ hoàn (`dot_hoan_id IS NULL` và `_tien_dong ≠ 0`) và cùng tổng `tong_dong_vnd` các đợt. Cách làm: harness chụp (số dư, số dòng chờ hoàn, tổng đợt) của mọi người vào bảng tạm bằng **hàm cũ**, chạy migration, so với **hàm mới**; migration tự có khối `DO` so tổng chi theo (người, tháng) và `RAISE EXCEPTION` nếu lệch (giao dịch hoàn tác).

## 3. Khoản thu là dòng riêng

**Hiện có → đề xuất.** Cước giữ nguyên (`thu_chang.tuyen_id`, `cuoc_tay_vnd`, `tuyen`, `gia_tuyen`): chỉ **phát sinh và đóng ghép** thành dòng, vì chỉ chúng đang đọc từ chữ.

```
doixe.dong_thu (
  id bigint identity PK,
  chang_id bigint NOT NULL REFERENCES doixe.chang(id),
  khoan text NOT NULL REFERENCES doixe.khoan(ma),     -- huong IN ('thu','ca_hai')
  nhan text,                                          -- chữ người dùng ghi ("Kiểm hoá", khoản lạ), tối đa 100
  kieu text NOT NULL CHECK (kieu IN ('theo_muc','nhap_tay')),
  so_luong integer CHECK (so_luong > 0),              -- ngày, giờ, đơn vị; NULL với khoản cố định / nhập tay
  so_tien_vnd bigint CHECK (so_tien_vnd > 0),         -- chỉ khi kieu = 'nhap_tay'
  nguon text NOT NULL CHECK (nguon IN ('tay','dan','chuyen_ghi_chu','o_so_luong')),
  actor text NOT NULL, luc timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK ((kieu = 'nhap_tay') = (so_tien_vnd IS NOT NULL))
)
```

Tiền của dòng `theo_muc` **không lưu**, tính khi đọc từ (`khoan.cach`, `so_luong`, mức hiện hành) bằng đúng công thức đang dùng (`co_dinh`: mức; `theo_ngay`: mức + (số−1) × mức thêm; `theo_don_vi`: số × mức) và NULL khi khoản chưa có mức (NULL không phải 0, hiện là cờ "chưa có mức"). Nhờ vậy giữ hành vi hiện tại: đổi mức thì chặng chưa gửi đổi theo, bảng kê đã gửi không đổi (đã chép). Có giữ hành vi này hay đóng băng mức lúc ghi: câu 7.

**Lệnh.** `them_thu`, `sua_thu`, `bo_thu` (mã yêu cầu chống ghi trùng, khóa tư vấn chung, người làm, Lịch sử trước → sau, chặn `CHANG_DA_GUI` như `_chang_thu` hiện tại). Không bắt lý do: trước khi gửi, dòng thu là bản nháp như `thu_chang` hôm nay; đã gửi thì chỉ có `ghi_dieu_chinh_bk` (lý do bắt buộc). Ô `neo_ngay`, `may_gio` của chặng vẫn là số đo; `luu_chang`/`sua_chang` ghi kèm dòng `neo`/`may` (`nguon = 'o_so_luong'`, tối đa một dòng mỗi chặng và khoản) cho chặng chưa gửi, để **đọc thu không bao giờ lấy trực tiếp từ ô**.

**Bộ đọc ghi chú chỉ còn ở đường dán.** `_doc_ghi_chu` giữ để (a) chuyển một lần, (b) dán khối từ Sheet (`nguon = 'dan'`); `_tinh_chang` không gọi nữa, nên sửa `ghi_chu` ở bất kỳ tháng nào **không đổi tiền** (vá lỗ 1, mục 6). Sau chuyển `ghi_chu` là chữ thường; câu chữ "chưa đọc được" biến thành đếm dòng thu `theo_muc` có tiền NULL.

**Chuyển một lần từ ghi chú.** Chỉ với chặng **chưa** nằm trong `bang_ke_dong` (chặng đã gửi đã có bản chép, không chuyển):

1. Với mỗi chặng, lấy `_doc_ghi_chu(ghi_chu) || _ps_tu_o(...)`, đúng như `_tinh_chang` đang làm.
2. Mỗi khoản không có `loi`: ghi một `dong_thu` `kieu = 'nhap_tay'` với số tiền **đã tính** (đóng băng; kể cả khoản vốn tính từ mức); khoản từ ô (`o = true`) ghi `theo_muc` + `so_luong`; khoản lạ (`la = true`) ghi `khoan = 'khac_thu'` + `nhan`. Mã khoản cũ qua `khoan_ma_cu`.
3. Khoản có `loi`: **không** chuyển, ghi vào bảng báo cáo `doixe.chuyen_loi(chang_id, goc, loi)` và đếm. Hiện chúng không tính tiền, nên không tính cũng đúng số; nhưng cờ "chưa đọc được" mất, nên migration **dừng** nếu còn khoản lỗi chưa được xử lý (câu 6).

**Ảnh hưởng tới bảng kê.** `_tinh_chang` giữ **nguyên hình dạng jsonb** (`ghep_vnd`, `ps_vnd`, `chi_ho_vnd`, `ps[{goc, ten, ma, so_tien_vnd, chi_ho, cot, la, loi, o}]`), chỉ đổi nguồn: `goc` = `nhan`, `chi_ho` và `cot` đọc từ `khoan`. Vì vậy `gui_bang_ke`, `bang_ke_dong`, Excel 19 cột, `dieu_chinh_bk`, `tien_ve` không đổi. Bảng kê **đã gửi** không bị chạm: `bang_ke_dong` là bản chép, và `_doi_bk` chỉ đọc nó. Bảng kê **đang gom**: tổng không đổi, nhưng `dau` (md5 các dòng) đổi một lần vì `goc` đổi từ chữ ghi chú sang `nhan`; người đang mở màn gom sẽ gặp `BANG_KE_DOI` một lần (cần cửa sổ chuyển không ai gửi).

**Bất biến (B-2).** Với mọi (bên, tháng): bảng kê đang gom có `doi_vnd`, `cuoc_vnd`, `ghep_vnd`, `ps_vnd`, `chi_ho_vnd`, `chua_gia`, số chặng bằng nhau trước và sau; bảng kê đã gửi bằng nhau từng cột (bản chép không đổi). Harness chụp `_doc_bang_ke` mọi tháng bằng hàm cũ, so với hàm mới; migration có khối `DO` kiểm như mục 2.

## 4. Công nợ chung

Công nợ hiện là hai cơ chế: **người** (số dư = chi − hoàn − ứng, đơn vị hoàn là `dong`) và **bên trả cước** (đòi = bảng kê đã gửi + điều chỉnh − tiền về). Khối lượng thật để hợp nhất (đếm trong DDL): 6 bảng (`ung`, `dot_hoan`, `bang_ke`, `bang_ke_dong`, `dieu_chinh_bk`, `tien_ve`) và khoảng 19 hàm đụng tới tiền (`_so_du`, `_tien_dong`, `ghi_ung`, `huy_ung`, `ghi_hoan`, `huy_hoan`, `_doi_bk`, `_tra_bk`, `_cong_no`, `_thang_bk`, `_doc_bang_ke`, `gui_bang_ke`, `doi_chieu_xong`, `ghi_dieu_chinh_bk`, `ghi_tien_ve`, `huy_tien_ve`, `get_so`, `get_tong`, `get_bang_ke`).

| | (a) Giữ bảng hiện có, thêm lớp đọc chung; chỉ đối tác mới dùng bảng chung | (b) Chuyển hẳn mọi đối tác sang một bộ bảng | (c) Gộp nửa: một bảng tiền chuyển, nguồn nợ vẫn riêng |
| --- | --- | --- | --- |
| Bảng mới | `doi_tac`, `tien_chuyen` (nợ của đối tác mới đọc từ `chi_xe.doi_tac_id`, mục 5) | `doi_tac`, `no` (khoản phải thu/trả), `tien_chuyen`, `phan_bo` | `tien_chuyen` |
| Bảng cũ | giữ nguyên, thêm `doi_tac` nối ngược 1:1 (`doi_tac.nguoi_id`, `doi_tac.ben_ma`) | `ung`, `dot_hoan`, `tien_ve` thành bản chép rồi bỏ; bảng kê và dòng chi thành nguồn của `no` | `ung`, `dot_hoan`, `tien_ve` thành dòng `tien_chuyen`, nguồn nợ giữ |
| Đường ghi tiền đang chạy | **không đụng** (ứng, hoàn, tiền về, bảng kê chạy như cũ) | viết lại cả 19 hàm và đường ghi; phân bổ hoàn theo `dong_ids` thành bảng `phan_bo` | đụng `ghi_ung`, `ghi_hoan`, `ghi_tien_ve` và hai hàm hủy |
| Rủi ro | hai nơi lưu tiền, mọi luật mới viết hai lần cho tới khi hợp nhất | cao nhất: đổi đường ghi tiền khi bản thử đang nhập; cần chứng minh bằng nhau mọi số dư và mọi số đòi | vừa, nhưng không giải được "một cơ chế": vẫn hai nguồn nợ |
| Khối lượng | nhỏ nhất (3 bảng, 1 hàm đọc, 4–5 hàm ghi) | lớn nhất (phiên thực thi riêng, nhiều PR) | vừa |
| Kiểm chứng | số dư và số đòi cũ không đổi (không thể đổi: không chạm) + số dư đối tác mới = tổng nợ − tiền chuyển | phải chứng minh số dư từng người và số đòi từng bảng kê trước = sau trên dữ liệu thật | như (b) cho phần tiền chuyển |

**Đề xuất: (a), kèm cam kết hợp nhất sau.** Lý do chính: hướng A đòi "một cơ chế **trước khi thêm** dầu, gara", và (a) làm đúng điều đó (mục Công nợ một danh sách, đối tác mới dùng bảng chung) mà không động vào đường ghi tiền người dùng đã nghiệm thu và đang chạy thử; (b) bắt cả đợt chuyển dữ liệu cũ gánh rủi ro của một tính năng mới. Cái giá nói thẳng: (a) là **một giao diện đọc, hai nơi lưu** cho tới khi người dùng có lý do chuyển người và HTH sang bảng chung; khi đó làm như (b) từng đối tác một, mỗi lần có bất biến "số dư trước = sau". (c) bỏ: tốn như (b) ở đường ghi mà không bỏ được cơ chế nào.

Cấu trúc đề xuất cho (a):

- `doixe.doi_tac(id, loai CHECK IN ('nguoi','ben_thu','noi_ban','gara','nha_xe'), ten, dang_dung, nguoi_id UNIQUE NULL, ben_ma UNIQUE NULL)`. Điền ngược 1:1 từ `nguoi` và `ben`; đối tác mới chỉ có dòng ở đây.
- `doixe.tien_chuyen(id, doi_tac_id, chieu, ngay, so_tien_vnd > 0, ghi_chu, actor, luc, huy_actor, huy_luc, huy_ly_do)` theo khuôn `ung`: không xóa, hủy bắt buộc lý do, ngày không sau hôm nay (giờ VN). Chỉ dùng cho đối tác mới.
- `doixe.get_cong_no()` trả một danh sách: người (từ `_so_du`), bên (từ `_cong_no`), đối tác mới (Σ `chi_xe.so_tien_vnd` có `doi_tac_id` − Σ `tien_chuyen` chưa hủy).

**Bỏ ràng buộc tối đa hai bên của `ben`.** Thêm `chang.ben_thu text REFERENCES ben(ma)`, điền theo luật hiện tại (xe không thuê ngoài → `hth`; xe thuê ngoài → NULL, như hôm nay chúng không vào bảng kê nào), và một trigger `BEFORE INSERT` đặt giá trị theo luật đó khi NULL (để `luu_chang` và `phan_xe` của điều độ không phải sửa). `_chang_gom` lọc theo `c.ben_thu = p_ben.ma`; sau khi harness xanh, bỏ `ben.xe_thue_ngoai` và `UNIQUE` của nó. Bất biến: tập chặng đang gom của từng (bên, tháng) bằng nhau trước và sau.

## 5. Chi theo xe

**Hiện có → đề xuất.** Hiện không có chỗ ghi: dầu có lít và ODO, sửa chữa, định phí. Dòng chi chặng bắt buộc `chang_id`; `chang.container` bắt buộc không rỗng.

```
doixe.chi_xe (
  id bigint identity PK,
  xe_id bigint NOT NULL REFERENCES doixe.xe(id),
  khoan text NOT NULL REFERENCES doixe.khoan(ma),     -- huong IN ('chi','ca_hai')
  ngay date NOT NULL,                                 -- ngày phát sinh (đổ dầu, vào xưởng) hoặc ngày bắt đầu của định phí
  den_ngay date CHECK (den_ngay IS NULL OR den_ngay >= ngay),  -- định phí: chia theo ngày từ ngay tới den_ngay
  so_tien_vnd bigint NOT NULL CHECK (so_tien_vnd > 0),
  lit numeric(9,2) CHECK (lit > 0), odo integer CHECK (odo > 0),   -- dầu; NULL là trống
  chang_id bigint REFERENCES doixe.chang(id),         -- lần đổ phục vụ một chặng (không bắt buộc)
  doi_tac_id bigint REFERENCES doixe.doi_tac(id),     -- nợ nơi bán, gara; NULL = công ty trả ngay
  ghi_chu text, actor text NOT NULL, luc timestamptz NOT NULL DEFAULT clock_timestamp(),
  huy_actor text, huy_luc timestamptz, huy_ly_do text
)
```

Khoản mới dành cho chi theo xe (`dau_xe`, `sua_chua`, `dinh_phi`, `bao_hiem`…) là dòng của `khoan`, không phải bảng riêng. Định phí chia theo ngày: số của một tháng = tiền × số ngày giao với tháng / tổng số ngày; làm tròn VND nguyên (phần dư vào ngày cuối) là CÒN MỞ, chốt ở spec B5.

**Quan hệ với khoản "Đổ dầu" của chặng.** Khoản `dau` trong `dong_phi` là dầu **tài xế trả tiền mặt dọc đường**, nằm trong số dư và phần hoàn: giữ nguyên, không chuyển dòng nào. `chi_xe` là dầu đổ ở nơi bán (có lít, ODO, nợ nơi bán). Mỗi lần đổ chỉ ghi một nơi; báo cáo "dầu của xe" cộng cả hai. Để không chạm số dư người, **giai đoạn đầu `chi_xe` chỉ do công ty hoặc nơi bán/gara trả**: tài xế hay người đi lệnh ứng tiền trả dầu, sửa xe thì ghi như chi chặng (câu 4).

**Luật khóa tháng cho `chi_xe`:** đề xuất theo khuôn `ung` (không sửa, hủy bắt buộc lý do, ghi lại dòng mới) và tháng khóa theo `ngay`; chốt ở spec B5. Lịch sử: việc `them_chi_xe`, `huy_chi_xe` với trước → sau.

**Lịch sử tài xế chạy xe nào.** `xe.tai_xe_id` là tài xế hiện tại, `chang.tai_xe_id` là sự thật từng chặng (24/24 tài xế chỉ lái một xe trong 483 chuyến tháng 8–10/2026, theo [bản đồ dữ liệu](../docs/doi-xe-kien-truc-du-lieu.md)). Đề xuất `doixe.xe_tai_xe(xe_id, tai_xe_id, tu_ngay date NULL, den_ngay date NULL)` (`tu_ngay` NULL = từ trước khi có sổ; một dòng mở mỗi xe qua index riêng; không chồng ngày do hàm ghi kiểm, không dùng extension), điền một dòng mở từ `xe.tai_xe_id` hiện có. Dùng để gợi ý tài xế khi phân xe ở ngày quá khứ và để tính định phí, lương theo ngày. Chặng khác bảng này thì **chặng thắng**. Ưu tiên thấp: chỉ làm khi gói Lãi lỗ cần; `xe.tai_xe_id` giữ vì điều độ đọc.

## 6. Chốt tháng và hai lỗ

**Hiện có.** Hai thứ khác bản chất: `thang_khoa` là ổ khóa theo lịch (chặn sửa tiền chi tháng cũ), bảng kê là vòng đời chứng từ (gom → gửi → đối chiếu → thu đủ) và `_thang_gom` có thể gom chặng tháng M vào tháng M+1. Đây là hai thứ nên có hai trạng thái; **không đề xuất gộp thành một ổ khóa** vì khóa tháng chi tại một ngày cố định sẽ buộc bảng kê phải gửi đúng hạn đó, và chặng ghi muộn đã được `_thang_gom` xử lý.

**Đề xuất: một cách nói, ba trạng thái của chặng, một hàm.** Mọi lệnh và mọi màn hỏi cùng một hàm `doixe._trang_thai_chang(chang_id)` trả tập {`thang_khoa`, `da_hoan`, `da_gui`}. Đây là hàm mà `_ly_khoa_chang` của điều độ đã làm một phần (đã gửi, đã hoàn, đã có phí); B3 mở rộng cho `sua_chang`, `xoa_chang` dùng chung. Ở đầu màn Chặng, mỗi tháng hiện hai chip rời (**Chi**: mở/khóa; **Thu**: gom/gửi/đối chiếu/đủ), và hàng chờ có "tháng đã khóa còn chặng chưa lên bảng kê" (chỉ đọc, không chặn). Bảng quyền sửa:

| Thao tác trên chặng | Hiện nay | Đề xuất |
| --- | --- | --- |
| Sửa tiền chi | tháng khóa hoặc đã hoàn → dòng điều chỉnh; còn lại ghi đè | giữ |
| Sửa tiền thu (`dong_thu`) | chưa có (đọc từ ghi chú); `thu_chang` chặn `CHANG_DA_GUI` | chặn `CHANG_DA_GUI`; không theo khóa tháng chi |
| Sửa `ghi_chu`, nơi lấy/hạ, kho | ghi đè mọi tháng; **ghi chú sinh tiền** | giữ ghi đè; không còn sinh tiền (mục 3) |
| Sửa `ngay`, `container`, `loai`, `xe_id` | chặn chuyển tháng khóa; **đã gửi vẫn sửa được** | thêm chặn `CHANG_DA_GUI` (giống `doi_phan_cong` của điều độ) |
| Xóa/bỏ chặng (`xoa_chang`) | **không kiểm bảng kê đã gửi** | chặn `CHANG_DA_GUI`; đường sửa khi sai thật: câu 5 |
| Đổi người trả một khoản | chặn khi khóa hoặc đã hoàn | giữ |

**Vá lỗ 1 (ghi chú sinh tiền):** dòng thu thay ghi chú, nhờ mục 3. Bài kiểm trong harness: sửa `ghi_chu` của chặng đang gom và của chặng ở tháng khóa, `doi_vnd` không đổi. **Vá lỗ 2 (`xoa_chang` không kiểm bảng kê đã gửi):** `xoa_chang` và `sua_chang` (bốn cột nhận dạng) gọi `_trang_thai_chang` và chặn `CHANG_DA_GUI`. Hai điều này **thắt chặt** luật, nên phải chốt (câu 5); bản chép `bang_ke_dong` bảo đảm số đòi không đổi dù có lỗ, nhưng chặng và bảng kê lệch nhau không có cảnh báo nào ngoài cờ `chang_con` ở `_dong_bk`.

## 7. Thứ tự migration, harness, nghiệm thu

Mỗi migration một PR, theo đúng chuỗi tên file `2026-11-NN-v7-doi-xe-*.sql` (chuỗi chạy lại được **theo thứ tự**; chạy lại file cũ sau file mới sẽ viết đè hàm mới, nên harness chạy cả chuỗi hai lượt đúng thứ tự). Bắt đầu sau khi điều độ (B1) đã vào `main`, vì B1 viết lại thân `xoa_chang`, thêm `chang.ngay_dong`, `chang.nguon`, `phan_xe`.

| Bước | Migration (đề xuất) | Gói | Nội dung | Hoàn tác |
| --- | --- | --- | --- | --- |
| 1 | `-khoan.sql` | B3a | `khoan`, `cot_sheet_dan`, `khoan_ten`, `khoan_ma_cu`; điền từ hai danh mục; kiểm cờ chi hộ; đổi FK; `loai_phi`, `phat_sinh` thành view; `luu_khoan` | Khôi phục hai bảng từ view, trả FK. Không mất dữ liệu: chưa ai ghi khác |
| 2 | `-nguoi-tra-khoan.sql` | B3b | mục 2: `dong.tra`, `dong.nguoi_tra_id`, tách dòng VETC, viết lại hàm, khối kiểm B-1 | Chỉ đảo được **trước** khi có khoản nào mang người trả khác mặc định (gộp dòng lại theo chặng); sau đó chỉ tiến |
| 3 | `-dong-thu.sql` | B3c | mục 3 và `chang.ben_thu`: `dong_thu`, `chuyen_loi`, chuyển từ ghi chú, viết lại `_tinh_chang`, `them_thu`/`sua_thu`/`bo_thu`, khối kiểm B-2 | Đảo được trước khi có dòng thu `nguon = 'tay'` (đọc lại ghi chú, vì ghi chú không bị sửa); sau đó chỉ tiến |
| 4 | `-chan-sau-gui.sql` | B3d | mục 6: `_trang_thai_chang`, chặn `CHANG_DA_GUI` ở `xoa_chang`, `sua_chang` | Revert hàm về bản trước (đọc được từ file cũ) |
| 5 | `-doi-tac.sql` | B4 | `doi_tac`, `tien_chuyen`, `get_cong_no` | `DROP` ba đối tượng mới (chưa dùng) |
| 6 | `-chi-xe.sql` | B5 | `chi_xe`, `xe_tai_xe`, khoản chi theo xe | `DROP` (chưa dùng) |
| 7 | `-bo-view-cu.sql` | sau nghiệm thu | bỏ view `loai_phi`, `phat_sinh`, `ben.xe_thue_ngoai`; không bỏ `chang.tra`, `nguoi_tra_id` (điều độ dùng làm mặc định) | không (chỉ chạy sau khi người dùng nghiệm thu) |

Mỗi bước có file hoàn tác ghi cạnh (`...-hoan-tac.sql`) và nói rõ điều kiện đảo được. Bước 2 và 3 là hai bước đụng tiền: **không** gộp chung một PR.

**Harness cần thêm** (job `postgres-doixe` trong `.github/workflows/test.yml` chạy thêm script mới, cùng cách dựng DB dùng một lần của `test_pg_doixe.py`):

1. `test_pg_doixe_chuyen.py`: dựng dữ liệu giả bằng các migration cũ và kịch bản có sẵn (chặng nhiều người, ứng, hoàn, hủy hoàn, tháng khóa, dòng điều chỉnh, trừ lại, bảng kê gom/gửi/đối chiếu/tiền về, ghi chú đủ loại gồm khoản lạ và khoản lỗi); chụp số dư, dòng chờ hoàn, tổng đợt, `_doc_bang_ke` mọi tháng, tổng chi theo (người, tháng) bằng **hàm cũ**; chạy migration mới hai lượt; so từng chỉ số (B-1 đến B-3).
2. Kịch bản mới: chặng hai người trả (hoàn riêng từng người, hủy hoàn, bỏ chặng ở tháng khóa sinh hai dòng trừ lại); sửa `ghi_chu` không đổi `doi_vnd`; `xoa_chang` và sửa `ngay` của chặng đã gửi bị chặn; hai bên trả cước; `get_cong_no` cộng đúng người, bên, đối tác mới; quyền của `v7_app` (không quyền trên bảng, hàm phụ không cấp).
3. Kiểm "một khoản một người trả" và "mỗi mối nối `khoan` có một cờ chi hộ" bằng truy vấn trong khối `DO` của migration và trong harness.

**Tiêu chí nghiệm thu số** (đo được trên dữ liệu giả của harness **và** trên bản thử tháng 10/2026 sau khi triển khai theo `DEPLOY-CLAUDE-01`: sao lưu trước, `ON_ERROR_STOP`, kiểm sau):

| Bất biến | Phép đo | Dung sai |
| --- | --- | --- |
| B-1 số dư | `_so_du` của mọi người nhận ứng, mọi tháng; số dòng chờ hoàn; tổng `tong_dong_vnd` | 0 đ, 0 dòng |
| B-2 số đòi | `doi_vnd`, `cuoc_vnd`, `ghep_vnd`, `ps_vnd`, `chi_ho_vnd`, số chặng, `chua_gia` mọi (bên, tháng) cả đang gom và đã gửi; `_cong_no` | 0 đ |
| B-3 tổng chi | tổng `dong_phi.so_tien_vnd` theo (khoản, tháng của chặng) và số dòng `dong_phi` | 0 đ, 0 dòng |
| B-4 Lịch sử | số dòng `su_kien` cũ không đổi; mỗi bước thêm đúng một sự kiện đếm trước → sau | đúng |

## Nguồn quyết định

- [`DOI-XE-CAU-TRUC-01`](../docs/decisions/doi-xe-cau-truc-01.md) (người dùng, 19/11/2026): hướng đổi mô hình.
- [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md), [`DOI-XE-THU-01`](../docs/decisions/doi-xe-thu-01.md): luật tiền giữ nguyên; [`DOI-XE-DIEU-DO-01`](../docs/decisions/doi-xe-dieu-do-01.md): chặng sinh từ booking, `chang.ngay_dong`, `chang.nguon`.
- [Bản đồ dữ liệu](../docs/doi-xe-kien-truc-du-lieu.md); [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md) cho cách triển khai migration.
- Bản nháp migration điều độ (chưa commit, đọc để mô hình khớp): `2026-11-19-v7-doi-xe-dieu-do.sql`.

## Hành vi và bất biến

- VND nguyên (`bigint`); NULL là ô trống, không phải 0 (dòng `theo_muc` chưa có mức là NULL, hiện là "chưa có mức").
- Không đổi công thức số dư, hoàn theo đợt, hủy bắt buộc lý do, khóa tháng, bảng kê gửi → đối chiếu → tiền về, chi hộ; mọi bước chuyển giữ B-1 đến B-4.
- Mọi lệnh ghi mới: khóa tư vấn chung, mã yêu cầu chống ghi trùng, người làm từ `sokhach.actor`, ngày không sau hôm nay (giờ VN), Lịch sử chỉ thêm có trước → sau.
- Một khoản của một chặng có đúng một người trả (giả định, câu 1). `chang.tra`, `nguoi_tra_id` chỉ là mặc định.
- Số đòi của bảng kê đã gửi chỉ đọc `bang_ke_dong`; không có đường nào đọc lại `chang` hay `dong_thu` cho bảng kê đã gửi.
- Schema `doixe` chỉ đọc `sokhach`; web không ghi Google Sheet.

## Tiêu chí nghiệm thu

- [ ] Người dùng trả lời đủ các câu ở mục dưới; phiên điều phối ghi quyết định riêng (`docs/decisions/`) trước khi viết migration.
- [ ] Từng migration: harness chuyển (B-1 đến B-4) xanh với dữ liệu giả; `npm run check` xanh; harness PostgreSQL xanh ở máy và ở CI.
- [ ] Bản thử tháng 10/2026 trên `hao`: số đo bảng trên bằng 0 lệch trước và sau từng bước (nhật ký trong `docs/deploys/`, chỉ ghi số đếm).
- [ ] Sửa `ghi_chu` của chặng đang gom và chặng tháng khóa không đổi `doi_vnd`; `xoa_chang` chặng đã gửi trả `CHANG_DA_GUI`.
- [ ] Chặng có hai người trả: hoàn riêng từng người, số dư từng người đúng công thức.
- [ ] Không còn hàm nào của đường thu đọc `ghi_chu` ngoài đường dán (grep).
- [ ] Frontend (gói F, bước 7 và 8): thuộc spec của từng gói F; bản thử không thay nghiệm thu backend hoặc quyền ghi tiền.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`), phiên thực thi Sonnet 5.5 effort high.
- Review: opus (đụng luật tiền và schema).
- Được sửa: `specs/doi-xe-mo-hinh-01.md`, `specs/README.md` (một dòng).
- Cấm: migration, code, chạy DDL, ghi cơ sở dữ liệu hoặc Sheet, `ssh hao`, đổi `specs/doi-xe-cau-truc-01.md` hay `docs/decisions*`, chép tên người, biển số, container, số tiền thật.
- Lệnh kiểm: `npm run lint` (tài liệu, liên kết, dữ liệu nhạy cảm), `node scripts/check-secrets.js`.

## Hoàn tác

Revert PR. Không có dữ liệu.

## Bằng chứng

Đọc ngày 19/11/2026, chỉ đọc, `main` `3c8e4a0` và nhánh điều phối `origin/claude/doi-xe-cau-truc` (nay đã là `main` `62cbeaf`):

- `specs/chi-phi-xe-01.md`, `specs/doi-xe-thu-01.md`, `specs/doi-xe-dieu-do-01.md`, `docs/doi-xe-kien-truc-du-lieu.md`, `specs/doi-xe-cau-truc-01.md` và `docs/decisions/doi-xe-cau-truc-01.md` (đã vào `main` ở #497), ba quyết định Đội xe.
- DDL và thân hàm trong bốn migration `cong-no-web-handoff/tools/migrations/2026-11-18-v7-doi-xe*.sql`; `test_pg_doixe.py` (cấu trúc harness); bản nháp migration điều độ trong worktree riêng (chỉ đọc).
- Số đếm trong spec (16 khoản chi, 14 khoản thu, 10 mối nối, 9 khoản chi được nối, 4 khoản thu không nối, 20 + 1 khoản mới, 6 bảng và khoảng 19 hàm đụng tới tiền) đếm từ DDL, không từ dữ liệu.

Chưa làm và phải làm trước khi chạy migration ghi: (1) đo trên bản thử số chặng có khoản `loi` trong ghi chú; (2) so `loai_phi.chi_ho` với `phat_sinh.chi_ho` của từng cặp trên `hao`; (3) xác nhận không chặng nào cần chia một khoản cho hai người; (4) chạy thật mọi harness. Không kiểm gì trên `hao`, không chạy harness (spec thuần tài liệu).

## Cần người dùng chốt

Viết bằng từ nghiệp vụ; mỗi câu có **đề xuất** của Claude (chọn phương án đầu).

1. **Một khoản chi có thể do hai người cùng trả không?** (ví dụ phí cầu đường của một chặng, tài xế trả một nửa, người đi lệnh một nửa.) *Đề xuất: không*, mỗi khoản một người trả; cần chia thì ghi thành hai khoản. Đơn giản và đúng với dữ liệu thấy tới nay. Nếu có: phải thêm một cấp nữa ở dòng khoản, và đợt hoàn phức tạp hơn.
2. **Đổi người trả của một khoản khi tháng đã khóa hoặc khoản đã được hoàn?** *Đề xuất: vẫn chặn như hiện nay* (phải hủy đợt hoàn hoặc mở tháng, hoặc ghi điều chỉnh). Phương án hai: cho "chuyển khoản này từ người A sang người B" bằng một cặp dòng điều chỉnh có lý do; tiện hơn nhưng là luật mới về tiền.
3. **Công nợ chung: (a) hay (b)?** (mục 4) *Đề xuất (a)*: đối tác mới (nơi bán dầu, gara, nhà xe thuê) dùng bảng chung ngay, người và HTH giữ bảng cũ và hợp nhất sau khi người dùng muốn. Phương án (b) chuyển hết một lần: gọn hơn về sau nhưng rủi ro cao nhất cho phần tiền đang chạy thử.
4. **Tài xế hay người đi lệnh có ứng tiền trả dầu, sửa xe (khoản ghi theo xe, không theo chặng) không?** *Đề xuất: chưa*; giai đoạn đầu khoản theo xe do công ty hoặc nơi bán, gara trả; tiền tài xế tự trả dọc đường vẫn ghi như chi của chặng (khoản "Đổ dầu" hiện có). Nếu có: khoản theo xe phải vào số dư và phần hoàn của người, đụng đường hoàn.
5. **Chặng đã gửi bảng kê: không cho sửa ngày, container, loại chặng, xe và không cho xóa?** *Đề xuất: chặn*; sai thật thì điều chỉnh dòng bảng kê (lý do bắt buộc) trước khi đối chiếu xong. Hiện web không chặn, nên chặng và bảng kê đã gửi có thể lệch nhau mà không báo. Cần nói rõ: chặng gửi nhầm cần bỏ thì làm theo đường nào (đề xuất: điều chỉnh dòng bảng kê về 0, rồi mới được bỏ chặng).
6. **Khoản phát sinh viết trong ghi chú mà máy không đọc được, lúc chuyển sang dòng riêng thì ai xử lý?** *Đề xuất*: máy lập danh sách (chặng, chữ ghi chú, lý do lỗi); hai nhân viên sửa trên web thành dòng thu **trước** ngày chuyển; còn sót thì không chuyển và không tính tiền (đúng như hôm nay khoản lỗi không được tính). Số lượng khoản lỗi: chưa đo.
7. **Phát sinh tính theo mức (neo theo ngày, nổ máy theo giờ): đổi mức có đổi tiền của chặng chưa gửi không?** *Đề xuất: có* (như hiện nay, đến lúc gửi bảng kê thì chốt số). Phương án hai: đóng băng mức vào lúc ghi, đổi mức không ảnh hưởng chặng cũ; nhất quán hơn nhưng đổi hành vi người dùng đã quen.
8. **Hạ sớm và kiểm hoá: một khoản hay hai?** *Đề xuất: một khoản* `hasom` (chi hộ), nhãn "Hạ sớm" hay "Kiểm hoá" giữ ở từng dòng thu; Excel bảng kê không đổi. Phía chi vốn đã gộp một khoản, không tách lại được dữ liệu cũ.

Điều không hỏi vì giữ nguyên: danh sách khoản chi hộ (còn mở ở `DOI-XE-THU-01` câu 3 và `CHI-PHI-XE-01` câu 13; mô hình mới chỉ gom về một cờ, không đổi giá trị); tiền nổ máy phát (`CHI-PHI-XE-01` câu 6).

## Câu hỏi mở

- Định phí chia theo ngày làm tròn thế nào, `chi_xe` ở tháng khóa xử ra sao, lịch sử tài xế đổi xe có cần ngay không: để spec gói B5.
- Có đưa `cước` thành dòng thu của cùng bảng `dong_thu` về sau không (hiện giữ `thu_chang`).
- Người dùng muốn có lý do bắt buộc khi sửa hoặc bỏ dòng thu ở chặng chưa gửi không (đề xuất: không, như `thu_chang`).
