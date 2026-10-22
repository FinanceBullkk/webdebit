# V7 — Gắn mặt hàng cho sổ khách và nhóm ô chọn khách (MH-01)

Trạng thái: ĐỀ XUẤT, Claude chốt phạm vi theo quyền người dùng trao 21/10/2026; người dùng yêu cầu làm ngày 23/10/2026. Code trên nhánh `feat/v7-mat-hang`, **chưa triển khai** lên `hao`.

## Vấn đề

[`V7-MH`](../docs/decisions.md#v7-mh) (20/10) chốt: một sổ một mặt hàng, cảng/bộ là phương thức vận chuyển, dùng để **lọc danh sách khách và xác định sổ khi nhập**. Lược đồ đã có `customer.commodity_id`, `customer.transport_mode` và bảng `commodity`, nhưng:

1. Khâu xuất bản sạch (`v7_export_clean.py`) và khâu nạp (`v7_load_real_copy.py`, `v7_load_direct.py`) bỏ qua tab `TONG`, nên không đọc cột `LOAI HANG`; mọi khách nạp vào V7 đều có mặt hàng NULL.
2. `sokhach.list_customers()` chỉ trả `id`, `name`, `status`.
3. Ô chọn khách trên sổ live là một danh sách phẳng theo tên.

## Hành vi

### 1. Đọc `LOAI HANG` từ `TONG`

- Tab `TONG` có nhiều khối tháng đặt cạnh nhau; mỗi khối có cột tiêu đề `LOAI HANG` và cột `TÊN KHÁCH HÀNG` ngay bên phải. Với mỗi tên khách lấy nhãn ở **khối ngoài cùng bên phải** (tháng mới nhất) mà ô nhãn không trống.
- Khớp sổ theo tên đã chuẩn hóa (`normalized`, như khi đọc tiêu đề cột), không theo vị trí dòng.
- Nhãn chuẩn hóa thành (mặt hàng, phương thức):

| Nhãn trên `TONG` (đã chuẩn hóa) | Mặt hàng lưu | Phương thức |
| --- | --- | --- |
| `SAU RIENG CANG` / `SAU RIENG BO` / `SAU RIENG` | Sầu riêng | `CANG` / `BO` / NULL |
| `THANH LONG` / `TLONG BO` | Thanh long | NULL / `BO` |
| `XOAI` / `XOAI BO` | Xoài | NULL / `BO` |
| `CHUOI` | Chuối | NULL |
| `DUA COCONUT`, `DUA` / `DUA BO` | Dừa | NULL / `BO` |
| `BUOI`, `MIT`, `NHAN`, `GUNG TUOI`, `KHOAI LANG` | Bưởi, Mít, Nhãn, Gừng tươi, Khoai lang | NULL |
| `BAN CUOC`, `HANG NHAP` | Bán cước, Hàng nhập | NULL |

- Tên mặt hàng lưu bằng tiếng Việt có dấu, viết hoa chữ đầu cho người dùng dễ đọc; bảng trên là nguồn duy nhất, nằm trong code.
- Nhãn không có trong bảng, hoặc sổ không tìm thấy tên trên `TONG`, thì **để NULL** (hiện "Chưa phân loại"), không đoán. Bản sạch và báo cáo nạp đếm số sổ NULL và số nhãn lạ (không in tên khách ra stdout).
- Mặt hàng chỉ để phân loại/lọc; không đổi tiền, kỳ nợ, cờ hay cách kiểm của bản sạch.

### 2. Bản sạch và khâu nạp

- `clean_customers.csv`, cột `metadata` thêm hai khóa tùy chọn `commodity`, `transport_mode` (vắng = NULL). Không đổi `format_version`: bản v2 cũ vẫn nạp được (mặt hàng NULL); loader cũ gặp bản mới thì từ chối `CLEAN_METADATA` thay vì bỏ qua thầm lặng.
- `import_one` tạo dòng `commodity` nếu chưa có (`ON CONFLICT (name) DO NOTHING`) rồi ghi `commodity_id`, `transport_mode` ngay trong câu `INSERT` khách. Không thêm event, không tăng `version` (thuộc tính phân loại, không phải lệnh ghi tiền).

### 3. Gán cho DB đang chạy

`hao` đã nạp bản sạch v2 ngày 21/10 nên mọi khách đang NULL. Công cụ `tools/v7_commodity_sql.py --xlsx <bản xuất> --out <file .sql ngoài repo>` sinh một file SQL:

- Một transaction, `SET LOCAL ROLE sokhach_owner`, tạo `commodity` còn thiếu, `UPDATE customer ... WHERE name = <tên> AND commodity_id IS NULL AND transport_mode IS NULL` — không ghi đè khách đã gán; chạy lại vô hại.
- Tên khách mã hóa hex như loader; file chứa tên khách nên phải nằm ngoài repo (giống `captures/`). Stdout chỉ in số đếm.
- Công cụ **không** kết nối DB. Chạy file lên `hao` là bước riêng, cần backup và người dùng cho phép.

### 4. `list_customers`

Mỗi khách trả thêm `commodity` (tên, NULL được) và `transport_mode` (`CANG`/`BO`/NULL). Thứ tự giữ nguyên theo tên. Migration `tools/migrations/2026-10-23-v7-mat-hang.sql`: `CREATE OR REPLACE FUNCTION`, cùng chữ ký nên giữ quyền cũ; chạy lặp được, không đụng dòng tiền.

### 5. Ô chọn khách (sổ live)

- Danh sách chia nhóm theo mặt hàng + phương thức, mỗi nhóm có dòng tiêu đề không bấm được: "Sầu riêng · cảng (12)". Nhóm xếp theo tên tiếng Việt; "Chưa phân loại" cuối cùng. Trong nhóm giữ thứ tự tên.
- Khi chưa khách nào có mặt hàng (DB chưa chạy bước 3), danh sách giữ phẳng như cũ, không hiện một nhóm "Chưa phân loại" thừa.
- Ô tìm khớp cả tên khách lẫn tên nhóm, không phân biệt dấu: gõ "sau rieng" hiện mọi sổ sầu riêng, gõ "sau rieng bo" chỉ sổ đường bộ. Chữ gợi ý trong ô đổi thành "Gõ tên khách hoặc mặt hàng".
- Giữ nguyên các bước hiện có: gõ, bấm tên hoặc Enter mở khách đầu tiên; giới hạn 50 dòng và câu đếm.
- Danh sách nguồn cấn trừ đã hiện mặt hàng, không đổi.

**Miễn mockup Penpot:** ô chọn giữ nguyên luồng (cùng ô, cùng thao tác, cùng kết quả); thêm tiêu đề nhóm và mở rộng điều kiện tìm là đổi hiển thị, không đổi quyền, tiền hay bước. Nếu người dùng muốn thêm nút lọc riêng (ví dụ hàng nút "Tất cả · Sầu riêng · Chuối…"), đó là control mới, cần mockup và duyệt trước.

## Kiểm

| Thao tác | Module | Kiểm |
| --- | --- | --- |
| Đọc và chuẩn hóa nhãn `TONG` | `v7_load_real_copy.tong_commodities`, `commodity_of` | unittest: xlsx giả nhiều khối tháng, lấy khối phải nhất, nhãn có dấu/khoảng trắng, nhãn lạ → NULL, khách không có trên `TONG` → NULL |
| Bản sạch mang mặt hàng | `v7_export_clean.export`, `clean_data` | unittest: xuất rồi đọc lại giữ `commodity`/`transport_mode`; metadata lạ vẫn bị từ chối |
| Nạp gán mặt hàng | `import_one` | harness PostgreSQL: khách nạp có `commodity_id`/`transport_mode` đúng, khách NULL vẫn nạp |
| SQL gán cho DB đang chạy | `v7_commodity_sql.py` | unittest: file sinh ra không chứa tên rõ, chỉ ghi khách NULL; harness PostgreSQL: chạy hai lần, khách đã gán tay không bị đè |
| `list_customers` | SQL, migration | harness grants: JSON khớp truy vấn gốc có hai khóa mới; migration chạy lặp được |
| Ô chọn khách | `so-khach-v7-api.js` | Playwright: nhóm và tiêu đề, tìm theo mặt hàng không dấu, Enter mở khách đầu tiên của kết quả lọc |

Không chạy trên `hao`, Sheet hay dữ liệu thật. Triển khai: backup → chạy migration và SQL gán trên bản sao → đối chiếu số khách theo mặt hàng với `TONG` → chạy lên `hao` khi người dùng cho phép.

## Chạy thử trên dữ liệu thật (cục bộ, 23/10/2026)

`v7_commodity_sql.py` với bản sạch v2 (bản đã nạp lên `hao`) và bản xuất Sheet 21/10 19h; chỉ sinh file SQL vào thư mục tạm, không chạm DB. Trong 236 sổ: **212 có mặt hàng**, 22 không tìm thấy tên trên `TONG` (tên tab khác tên trên `TONG`; 4 trong số đó là dòng sửa tay của bản đối chiếu 20/10, 18 là sổ mới sau 20/10), 2 mang nhãn chưa có trong bảng: `DỪA- BỘ` (đã thêm vào bảng sau lần chạy này) và `CHUOI- DUONG SAT`. Khớp mờ (bỏ khoảng trắng, gần đúng ≥ 85%) chỉ thêm được 2–4 sổ nên không dùng: không đoán.

## CÒN MỞ

- 22 sổ "Chưa phân loại" do tên tab khác tên trên `TONG`: cần người dùng gán tay; lệnh gán/đổi trên web (`set_customer_attributes`) vẫn là ĐỀ XUẤT.
- Nhãn `CHUOI- DUONG SAT` (chuối đi đường sắt): lược đồ chỉ cho phương thức `CANG`/`BO`. Thêm `DUONG_SAT` hay gộp vào Chuối không phương thức cần người dùng chốt; tới lúc đó sổ này để "Chưa phân loại".
- Dashboard theo mặt hàng là spec riêng, làm sau phần này.
