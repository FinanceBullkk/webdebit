# Kiểm bất biến tiền bằng chuỗi lệnh ngẫu nhiên có seed (BAT-BIEN-TIEN)

Trạng thái: ĐÃ CHỐT làm (phiên điều phối giao 18/11/2026 theo quyền tự quyết của Claude). Chỉ thêm test và công cụ
kiểm; không đổi hành vi, hàm SQL, schema, quyền hay quy tắc tiền. Không chạy trên `hao`, không chạm dữ liệu thật.
Test tìm ra vi phạm thật trên `main` thì dừng và báo, không sửa SQL trong cùng việc.

## Đầu ra

Một harness PostgreSQL mới, `cong-no-web-handoff/tools/test_pg_v7_bat_bien.py`. Mỗi chuỗi dựng ba sổ giả (opening
một đến ba tháng, có số âm; mỗi sổ thêm một dòng chuyến và một dòng thu "lịch sử trong opening" chỉ để hiển thị) rồi
chạy 25 lệnh ghi tiền ngẫu nhiên qua đúng hàm `sokhach.*` mà API gọi. Sau **mỗi** lệnh kiểm các bất biến ở dưới.
Đỏ thì rút gọn chuỗi (bỏ dần từng khúc lệnh, giữ khi còn đỏ đúng bất biến đó) và in từng bước, chi tiết vi phạm và
lệnh chạy lại.

Khác `test_pg_v7_fifo_ngau_nhien.py` ([spec](v7-fifo-ngau-nhien.md)): bên đó so một sổ với mô hình phân bổ viết lại;
bên này không có mô hình phân bổ, chỉ giữ "bóng sổ" (những gì đã ghi) và kiểm **tính chất** trên nhiều sổ, gồm cả phần
bên kia để ngoài: cấn trừ hai sổ, điều chỉnh theo chuyến, chuyến chờ kiểm và duyệt, dòng lịch sử trong opening, Lịch
sử (người làm, trước → sau), ngày tương lai. Bộ sinh tự viết trên `random.Random(seed)`, chỉ thư viện chuẩn.

## Nguồn quyết định

- Số dư, VND nguyên, NULL không phải 0 (ngoại lệ phụ phí trống của chuyến đã có đơn giá), pending ngoài số dư, lịch
  sử trong opening không cộng lại: [quy tắc](../docs/business-rules.md), [`V7-BE`](../docs/decisions/v7-be.md).
- Thu theo nợ cũ trước; phân bổ lại khi điều chỉnh, sửa giá, dán lô, đổi ngày phiếu, ghi phiếu mới; hủy phiếu bắt buộc
  lý do và không phân bổ lại phiếu khác; ổ khóa tháng: [`V7-SO`](../docs/decisions/v7-so.md); mở/khóa ghi Lịch sử:
  [`V7-CSM`](../docs/decisions/v7-csm.md); tháng âm và ứng trước: [`CAN-DU-01`](../docs/decisions/can-du-01.md).
- Cấn trừ hai sổ một lệnh, chặn khi nguồn không đủ dư có: CT-2SO (`test_pg_v7_backend_offset.py`).
- Cấm ngày ghi sổ tương lai theo giờ VN: `FUTURE-01` (phiếu, ngày xe khi dán và khi sửa, ngày cấn trừ).

## Lệnh trong chuỗi

Dán lô (chuyến có/không đơn giá, phụ phí trống/âm/dương, dòng chỉ phụ phí có/không ngày, container trùng trong ba ngày
để vào CHỜ KIỂM), sửa giá, đổi ngày chuyến, xóa chuyến, điều chỉnh thành tiền chuyến, duyệt chờ kiểm (nhận/loại),
điều chỉnh tháng, xóa điều chỉnh tháng, ghi phiếu (bốn hình thức), sửa ngày/hình thức phiếu, hủy phiếu (có lúc lý do
trống), khóa/mở tháng (cả tháng ngoài sáu tháng mở sẵn), cấn trừ (thường lấy theo dư có của sổ nguồn, có lúc vượt),
đổi ngày cấn trừ, hủy cấn trừ (gọi từ sổ nguồn hoặc sổ đích), gửi lặp lệnh vừa được nhận. Ngày lấy lùi từ hôm nay giờ
VN, khoảng 4% rơi vào tương lai. Lệnh trỏ tới thứ đã xóa/đã hủy vẫn được gửi để kiểm mã từ chối.

Bóng sổ dự đoán từng lệnh được nhận hay bị từ chối với mã nào, theo đúng thứ tự kiểm của hàm SQL (ví dụ `edit_trip_price`:
chuyến đã xóa → chờ kiểm → tháng khóa → không đổi → dòng phụ phí không ngày). Cả chuỗi chạy trong một lượt psql
(`bat_bien.run` trong DB thử: mỗi lệnh một subtransaction với `sokhach.actor` riêng, ràng buộc hoãn kiểm ngay sau lệnh
như lúc COMMIT, rồi chụp ảnh các sổ); Python đi lại từng bước để kiểm. Cách này cần vì mỗi lượt `docker exec` trên
Windows mất khoảng 150 ms. Cứ 20 chuỗi, các sổ giả cũ bị xóa sạch bằng `TRUNCATE sokhach.customer, sokhach.cutover
CASCADE` (chỉ dọn DB thử; schema, hàm, danh mục phụ phí và lỗi cấy giữ nguyên) vì `get_ledger` chậm dần theo tổng số sổ của cả DB (xem Câu hỏi mở).

## Bất biến kiểm sau mỗi bước

| Mã | Bất biến | Kiểm thế nào |
| --- | --- | --- |
| `so-du` | Số dư = opening + phát sinh có giá − thu ± điều chỉnh ± cấn trừ, VND nguyên | `total_outstanding_vnd` của `get_ledger` bằng tổng tính từ bóng sổ; bằng tổng nợ thô; tháng: đầu + phát sinh − thu = cuối, tháng cuối bằng tổng; mọi số tiền là chuỗi số nguyên |
| `fifo` | Thu theo nợ cũ trước | Xếp phiếu chưa hủy theo (ngày, mã); mỗi phiếu: tổng dòng bằng tiền phiếu, không lặp dòng, chỉ trả tháng còn nợ dương và không quá số còn nợ, ứng trước chỉ ở tháng phát sinh cuối; từ lần phân bổ lại gần nhất: không trả tháng mới (hay ứng trước) khi tháng cũ hơn còn nợ |
| `opening` | Opening không đổi, không phân bổ lại, lịch sử trong opening không cộng lại | Dấu vân dòng `opening_balance` và `legacy_row` không đổi; dòng lịch sử có số tiền nhưng tổng sổ không tính |
| `huy-phieu` | Hủy phiếu bắt buộc lý do, không đổi phân bổ phiếu khác | Lý do trống bị chặn; phiếu khác giữ nguyên dòng; tới lệnh phân bổ lại kế tiếp mọi phiếu giữ đúng dòng lúc hủy |
| `pending` | Chuyến thiếu giá và chờ kiểm ngoài số dư | Thành tiền NULL, không vào tổng; đếm chờ đúng |
| `null` | NULL không thành 0 | Đơn giá, phụ phí trống giữ NULL; thành tiền đơn giá + phụ phí (trống tính 0); dòng chỉ phụ phí là phụ phí; cờ thiếu giá đúng |
| `thang-khoa` | Tháng khóa không bị sửa đè | Sửa/xóa/điều chỉnh/duyệt/đổi ngày vào tháng khóa bị `MONTH_LOCKED`; chuyến và điều chỉnh có sẵn của tháng khóa không đổi bản ghi; chỉ chuyến dán mới được vào; cờ khóa trong DB khớp |
| `lich-su` | Mỗi lệnh tiền có Lịch sử người làm và trước → sau | Lệnh được nhận: `version` từng sổ bị ghi +1 (cấn trừ: cả hai sổ), có đúng một dòng Lịch sử chính đúng loại, mọi dòng mới ghi đúng người của bước; trước → sau đúng (giá cũ → mới, ngày cũ → mới, khóa cũ → mới, tiền phiếu, lý do hủy); mỗi lần đổi dòng phân bổ có dòng phân bổ lại ghi đúng trước và sau; dòng Lịch sử cũ không bị sửa/xóa |
| `can-tru` | Cấn trừ không đổi tổng hai sổ | Ghi/đổi ngày/hủy: tổng hai sổ giữ nguyên, sổ nguồn đổi đúng ± số cấn trừ; vượt dư có bị `OFFSET_EXCEEDS_CREDIT` |
| `tuong-lai` | Ngày tương lai bị chặn | Phiếu, ngày xe khi dán và khi đổi, ngày cấn trừ ở tương lai bị chặn; không sổ nào có ngày sau hôm nay |
| `nguyen-tu` | Lệnh bị từ chối không để lại gì; gửi lặp không ghi thêm | Không đổi `version`, không Lịch sử mới, không đổi phiếu/chuyến/điều chỉnh/khóa/tổng; gửi lặp trả đúng kết quả lần đầu |
| `ket-qua` | Nhận/từ chối đúng luật | Mọi lệnh được nhận hay bị từ chối đúng mã bóng sổ dự đoán |

## Chạy

```text
python cong-no-web-handoff/tools/test_pg_v7_bat_bien.py
```

Cần Docker. `--sequences N` (mặc định 200, bản CI), `--steps N` (lệnh mỗi chuỗi, mặc định 25), `--books N`
(mặc định 3), `--seed N` (mặc định cố định để CI ổn định), `--sequence I` (chỉ chạy chuỗi số I, để chạy lại chuỗi đỏ),
`--shrink-seconds`, `--report <file>.json`. Mỗi chuỗi có seed riêng `"<seed>:<số chuỗi>"`, nên `--seed S --sequence I
--steps M` dựng lại đúng chuỗi đó (ngày tính lùi từ hôm nay, nên chạy khác ngày thì ngày tuyệt đối dịch theo). Chuỗi
chạy qua nửa đêm giờ VN thì tự chạy lại một lần. CI chạy job `postgres-v7-bat-bien` cho mọi PR không chỉ đổi tài liệu,
gom vào `ci-ok`.

`--mutant <tên>` cố ý làm sai một hàm hoặc view trong container dùng một lần; lệnh đạt (mã 0) khi test đỏ vì vi phạm
bất biến: `fifo-dao` (phân bổ từ tháng mới về cũ), `huy-phan-bo-lai` (hủy phiếu phân bổ lại phiếu khác), `tuong-lai`
(nhận phiếu ngày tương lai), `khoa-thang` (bỏ ổ khóa tháng), `lich-su` (ghi sai người làm), `null-0` (đơn giá trống
lưu thành 0), `can-tru` (sổ nguồn tính gấp đôi số cấn trừ). Sửa harness thì chạy lại các mutant.

## Ngoài phạm vi

Phụ phí nhiều loại và cột phí riêng, bảng giá, đồng bộ/khớp Sheet, dòng sổ gốc sửa được, ảnh phiếu, nhiều phiên ghi
đồng thời, số tiền gần giới hạn `bigint`, xóa sổ hay lưu trữ sổ, khóa lệnh trùng nội dung khác (`IDEMPOTENCY_CONFLICT`,
`STALE_LEDGER` đã ở test FIFO).

## Tiêu chí nghiệm thu

- [x] Xanh ở máy với ít nhất 1.000 chuỗi.
- [x] `--mutant fifo-dao` đỏ và rút gọn được chuỗi; các mutant khác đỏ đúng bất biến.
- [x] CI: job `postgres-v7-bat-bien` xanh, dưới khoảng 90 giây phần chạy test.
- [x] `npm run check` và `node scripts/check-secrets.js` xanh.

## Phạm vi file

- Thêm: `cong-no-web-handoff/tools/test_pg_v7_bat_bien.py`, file spec này.
- Sửa: `.github/workflows/test.yml` (job mới, `needs` của `ci-ok`), `docs/development.md` (bảng CI, bảng phạm vi harness).

## Hoàn tác

Revert PR. Không có dữ liệu, migration hay triển khai nào để gỡ.

## Bằng chứng

ĐÃ KIỂM CHỨNG 18/11/2026, nhánh tách từ `445713e`, PostgreSQL 18.6 theo digest của harness, seed mặc định `20261118`.
Chỉ là sổ giả trong container dùng một lần; không chứng minh gì về dữ liệu hay service trên `hao`.

- Máy dev Windows (Docker Desktop, máy đang tải nặng): 1.000 chuỗi × 25 lệnh xanh; 24.959 lệnh, 20.075 được nhận,
  4.884 bị từ chối đúng mã (nhiều nhất `MONTH_NOT_FOUND` 1.055, `OFFSET_EXCEEDS_CREDIT` 747, `TRIP_NOT_PENDING` 505,
  `FUTURE_DATE` 489, `MONTH_LOCKED` 402); 2.024 giây.
- CI (`ubuntu-latest`), 120 chuỗi: 2.992 lệnh, phần test 37,5 giây, cả job 51 giây; nâng mặc định lên 200 chuỗi.
- `--mutant`, mỗi lỗi đỏ đúng bất biến và rút gọn còn:
  - `fifo-dao` → `fifo`, 1 lệnh: ghi một phiếu vào sổ có ba tháng nợ, phiếu trả tháng mới khi tháng cũ còn nợ.
  - `huy-phan-bo-lai` → `huy-phieu`, 3 lệnh: hai phiếu, hủy phiếu đầu, phiếu sau bị dời phân bổ.
  - `tuong-lai` → `tuong-lai`, 1 lệnh: phiếu ngày tương lai được nhận.
  - `khoa-thang` → `thang-khoa`, 3 lệnh: khóa tháng, dán chuyến, đổi ngày chuyến vào tháng khóa được nhận.
  - `lich-su` → `lich-su`, 1 lệnh: điều chỉnh tháng ghi Lịch sử sai người làm.
  - `null-0` → `null`, 1 lệnh: dán chuyến chưa giá, DB lưu đơn giá 0.
  - `can-tru` → `can-tru`, 1 lệnh: một lần cấn trừ làm đổi tổng hai sổ.
- Không có vi phạm nào trên mã `main`. Hai lượt đầu chỉ lộ lỗi của chính test (đường dẫn `psql` phạm ARCH-01 — đổi
  sang `Pg.value`; dựng lại DB bằng chép mẫu vượt 30 giây trên Docker Windows — đổi sang `TRUNCATE`).

## Câu hỏi mở

- Hiệu năng, ngoài phạm vi test này: trong DB thử có khoảng 600 sổ nhỏ, `get_ledger` của một sổ gần trống mất khoảng
  340 ms. Đo 18/11/2026: `SELECT count(*) FROM sokhach.v_outstanding_month WHERE customer_id=$1` với plan chung (như
  khi chạy trong hàm plpgsql) mất khoảng 16 ms vì cửa sổ được tính trên mọi sổ, còn với hằng số chỉ 0,2 ms; `get_ledger`
  gọi view này một lần cho mỗi tháng của sổ. Trên `hao` (242 sổ) mở cả 242 sổ mất 23 giây ([lưới an toàn](v7-luoi-an-toan.md)),
  khớp hướng này. Chưa kiểm trên `hao`; cần một việc riêng để đo và sửa.
