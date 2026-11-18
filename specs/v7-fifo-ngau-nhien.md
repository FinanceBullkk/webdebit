# Kiểm phân bổ thu bằng chuỗi lệnh ngẫu nhiên (FIFO-NGAU-NHIEN)

Trạng thái: ĐÃ CHỐT làm (người dùng chọn 18/11/2026, "Làm test FIFO"). Chỉ thêm test và công cụ kiểm; không đổi
hành vi, hàm SQL, schema, quyền hay quy tắc tiền. Không chạy trên `hao`, không chạm dữ liệu thật.

## Đầu ra

Một harness PostgreSQL mới, `cong-no-web-handoff/tools/test_pg_v7_fifo_ngau_nhien.py`, sinh ngẫu nhiên hàng trăm
chuỗi lệnh ghi tiền (dán chuyến, sửa giá, đổi ngày chuyến, xóa chuyến, điều chỉnh tháng, xóa điều chỉnh, ghi thu,
đổi ngày/hình thức phiếu, hủy phiếu, khóa/mở tháng, gửi lặp, trùng khóa lệnh, phiên bản cũ) và chạy từng lệnh qua
đúng hàm `sokhach.*` mà API gọi, trên container PostgreSQL 18.6 dùng một lần. Sau **mỗi** lệnh, toàn bộ sổ trong DB
được so với một mô hình tham chiếu viết độc lập bằng Python (`tools/v7_fifo_model.py`). Lệch ở bất kỳ đâu thì
Hypothesis rút gọn về chuỗi lệnh ngắn nhất còn gây lệch và in ra từng bước.

Lý do: test phân bổ hiện có đều là ví dụ viết tay (case 7.02, `RA-GHI-TIEN.01`, `XOA-DC-THANG.01`…); không test nào
sinh dữ liệu ngẫu nhiên. Phân bổ lại chạy ở 19 chỗ gọi `reallocate`, nên tổ hợp lệnh là chỗ lỗi dễ lọt nhất.

Bản JS `planReallocation` không nằm trong phạm vi so sánh: trang thật (`so-khach-v7-live.html`) để server phân bổ
(`book = null` ở chế độ live), bản JS chỉ chạy ở trang mẫu dữ liệu giả và đã có case 7.02 so với SQL.

## Nguồn quyết định

- Thu theo nợ cũ trước, phân bổ lại khi điều chỉnh, sửa giá, dán lô, đổi ngày phiếu; xếp theo ngày phiếu rồi mã
  phiếu; hủy phiếu không phân bổ lại phiếu khác: [`V7-SO`](../docs/decisions/v7-so.md), [quy tắc](../docs/business-rules.md).
- Phiếu mới cũng phân bổ lại mọi phiếu (V7-SO sửa 29/10/2026, ghi trong `record_receipt`).
- Dòng phân bổ bỏ qua tháng âm, phần dư là ứng trước ở tháng cuối; nợ còn lại từng tháng cấn khoản dư vào tháng nợ
  cũ nhất: [`V7-BE`](../docs/decisions/v7-be.md) (6), [`CAN-DU-01`](../docs/decisions/can-du-01.md).
- Đơn giá trống thì chuyến ngoài số dư (NULL không là 0); phụ phí trống của chuyến đã có đơn giá tính 0: `V7-BE`.
- Xóa điều chỉnh tháng bằng dòng đảo dấu, cả hai cùng ẩn: [`XOA-DC-THANG-01`](../docs/decisions/xoa-dc-thang-01.md).
- Ổ khóa tháng; dán chuyến không bị khóa chặn (case khóa tháng trong harness backend): `V7-SO`, `V7-CSM`.

## Mô hình tham chiếu (`tools/v7_fifo_model.py`)

Thuần Python, chỉ thư viện chuẩn, không đọc DB, không import `web/`. Giữ: opening theo tháng, chuyến (tháng, có
container hay chỉ phụ phí, đơn giá, phụ phí, đã xóa), điều chỉnh tháng, phiếu thu (mã, ngày, tiền, hình thức, đã hủy,
dòng phân bổ hiện hành), trạng thái khóa từng tháng, `version` của sổ. Tính:

| Hàm | Ứng với |
| --- | --- |
| Tiền chuyến | có đơn giá: đơn giá + phụ phí (trống = 0); không đơn giá, không container: phụ phí; còn lại: NULL |
| Tháng phát sinh | tháng có opening, chuyến còn hiệu lực (kể cả chưa giá) hoặc điều chỉnh còn hiệu lực |
| Phân bổ lại | `sokhach.reallocate`: phiếu chưa hủy theo (ngày, mã phiếu), trừ tháng còn nợ dương từ cũ tới mới, phần dư là ứng trước ở tháng phát sinh cuối |
| Kế hoạch phiếu mới | phần đầu `record_receipt` (trước khi phân bổ lại), để biết phiếu nào báo "đã phân bổ lại" |
| Nợ thô / nợ còn lại từng tháng | `v_outstanding_month_raw` / `v_outstanding_month` (CAN-DU-01) |
| Các tháng của `get_ledger` | tháng, nợ còn lại, phát sinh, đã thu theo ngày phiếu, số cuối tháng |

Mỗi lệnh có hàm dự đoán kết quả: thành công, hoặc mã lỗi theo đúng thứ tự kiểm của hàm SQL.

| Lệnh | Bị từ chối khi (theo thứ tự) | Phân bổ lại |
| --- | --- | --- |
| `paste_trips` | không (container luôn mới, ngày không ở tương lai) | có |
| `edit_trip_price` | chuyến đã xóa; tháng khóa; giá và phụ phí không đổi; dòng phụ phí không ngày mà thêm đơn giá hoặc bỏ phụ phí (`INVALID_FEE_ONLY_DATE`, ràng buộc hoãn báo lúc COMMIT) | có |
| `edit_trip_info` (`event_date`) | chuyến đã xóa; tháng cũ khóa; ngày không đổi; tháng mới khóa | có |
| `delete_trip` | chuyến đã xóa; tháng khóa | có |
| `adjust_month` | tháng chưa có phát sinh; tháng khóa | có |
| `delete_month_adjustment` | điều chỉnh đã xóa; tháng khóa | có |
| `record_receipt` | sổ chưa có tháng phát sinh nào | có |
| `edit_receipt_meta` | phiếu đã hủy; không đổi gì | chỉ khi đổi ngày |
| `void_receipt` | phiếu đã hủy | không |
| `set_month_lock` | không | không |
| Gửi lặp cùng khóa, cùng nội dung | không, trả đúng kết quả lần đầu | không |
| Cùng khóa, khác nội dung | `IDEMPOTENCY_CONFLICT` | không |
| Phiên bản cũ | `STALE_LEDGER` | không |

## Bất biến kiểm sau mỗi bước

1. Lệnh được nhận hay bị từ chối đúng như dự đoán, đúng mã lỗi.
2. `version` của sổ tăng đúng 1 khi lệnh được nhận; giữ nguyên khi bị từ chối hoặc gửi lặp.
3. Từng phiếu: còn/hủy, ngày, tiền, hình thức và dòng phân bổ hiện hành (tháng, nợ/ứng trước, tiền) đúng mô hình.
   Suy ra: tổng dòng của phiếu chưa hủy bằng tiền phiếu, phiếu hủy không còn dòng, hủy phiếu không đổi phiếu khác.
4. Danh sách `reallocated` trả về đúng các phiếu có dòng đổi, đúng thứ tự (ngày, mã phiếu).
5. `get_ledger`: tập tháng, nợ còn lại, phát sinh, đã thu, số cuối tháng của từng tháng và tổng còn phải thu đúng mô
   hình; đơn giá và phụ phí từng chuyến còn hiệu lực đúng mô hình.
6. Gửi lặp trả về từng byte kết quả đã lưu; bị từ chối thì sổ không đổi gì.

## Ngoài phạm vi

Cấn trừ hai sổ, điều chỉnh theo chuyến (`adjust_trip`), chuyến CHỜ KIỂM và kiểm trùng (container luôn mới), dòng sổ
gốc, phụ phí nhiều loại, phụ phí bằng 0 (hành vi giữ NULL hay 0 chưa ghi thành quyết định), bảng giá, đồng bộ Sheet,
chạy đồng thời hai phiên, số tiền gần giới hạn `bigint`. Mỗi mục có thể thêm vào mô hình ở đợt sau.

## Chạy

```text
uv run --python 3.13 --with-requirements requirements-dev.txt python cong-no-web-handoff/tools/test_pg_v7_fifo_ngau_nhien.py
```

Cần Docker. `--examples N` (số chuỗi, mặc định 100), `--steps N` (số lệnh tối đa mỗi chuỗi, mặc định 40), `--seed N`
(mặc định cố định để CI ổn định) hoặc `--seed random` (seed mới, in ra để chạy lại), `--report <file>.json`. Lệch thì
lệnh in "Chuỗi lệnh ngắn nhất còn gây lệch" (từng giá trị rút ra và từng bước) trước báo cáo JSON. Hypothesis ghim ở
`requirements-dev.txt`, chỉ dùng khi kiểm; mô hình và test đơn vị của nó không cần Hypothesis. CI chạy ở job
`postgres-v7-fifo` cho mọi PR không chỉ đổi tài liệu, gom vào `ci-ok`.

`--mutant <tên>` cố ý làm sai một hàm SQL ngay trong container dùng một lần rồi chạy như thường; lệnh đạt (mã 0) khi
harness đỏ. Ba lỗi có sẵn: `ngay-phieu` (phân bổ theo mã phiếu, quên ngày phiếu), `thang-am` (trừ cả tháng không còn
nợ dương), `huy-phan-bo-lai` (hủy phiếu thì phân bổ lại phiếu khác). Sửa harness hay mô hình thì chạy lại cả ba để chắc
nó vẫn bắt được lỗi; một bộ kiểm chỉ xanh trên mã đúng thì chưa chứng minh được gì.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_fifo_model.py` (trong `npm run check`) khóa mô hình bằng ví dụ tính tay: phân bổ theo ngày rồi
      mã phiếu, tháng âm bị bỏ qua, ứng trước ở tháng cuối, chuyến chưa giá giữ tháng nhưng không cộng tiền, hủy phiếu
      không phân bổ lại, CAN-DU-01, số cuối tháng của `get_ledger`, dòng phụ phí không ngày.
- [x] Harness xanh ở máy (Windows, Docker Desktop) với seed mặc định; CI: job `postgres-v7-fifo` của PR.
- [x] Cả ba `--mutant` làm harness đỏ và rút gọn được chuỗi.
- [x] `npm run check` và `node scripts/check-secrets.js` xanh.

## Phạm vi file

- Thêm: `cong-no-web-handoff/tools/v7_fifo_model.py` (mô hình), `cong-no-web-handoff/tools/v7_fifo_session.py` (chạy
  lệnh trên DB và so với mô hình), `cong-no-web-handoff/tools/test_pg_v7_fifo_ngau_nhien.py` (Hypothesis, dòng lệnh),
  `cong-no-web-handoff/tests/test_v7_fifo_model.py`, file spec này.
- Sửa: `cong-no-web-handoff/tools/pg_v7_harness.py` (thêm hàm dựng container dùng chung, không đổi hàm cũ),
  `requirements-dev.txt`, `.github/workflows/test.yml`, `docs/development.md`.

## Hoàn tác

Revert PR. Không có dữ liệu, migration hay triển khai nào để gỡ.

## Bằng chứng

ĐÃ KIỂM CHỨNG ở máy dev Windows (Docker Desktop, PostgreSQL 18.6 theo digest của harness), 18/11/2026, nhánh tách từ
`352d554`, Hypothesis 6.170.14, seed mặc định. Chỉ là fixture trong container dùng một lần; không chứng minh gì về
dữ liệu hay service trên `hao`.

- Mặc định (100 chuỗi, tối đa 40 lệnh): đạt; 120 chuỗi đã chạy, 1.040 lệnh, 208 lệnh bị từ chối đúng mã; 61 giây.
- `--mutant ngay-phieu`: đỏ đúng chỗ (`record_receipt` trả `reallocated` rỗng, mô hình chờ hai phiếu đổi dòng).
- `--mutant thang-am`: đỏ; ràng buộc CHECK của bảng dòng phân bổ chặn dòng không dương, lệnh lỗi ngoài dự đoán.
- `--mutant huy-phan-bo-lai`: đỏ, rút gọn còn 4 lệnh (hai phiếu 1 đồng, dán một chuyến chưa giá và một dòng phụ phí 1
  đồng, hủy phiếu đầu): DB dời phiếu thứ hai từ ứng trước sang trừ nợ; 212 giây gồm rút gọn.
- Lượt đầu tìm ra một luật mô hình còn thiếu, không phải lỗi SQL: dòng phụ phí không ngày phải giữ "không đơn giá, có
  phụ phí" (ràng buộc hoãn `check_trip_missing_date`, báo `INVALID_FEE_ONLY_DATE` lúc COMMIT); đã thêm vào mô hình
  và test tính tay.
- Không có lệch nào giữa SQL hiện hành và mô hình trong các lượt trên.

## Câu hỏi mở

- Thứ tự "mã phiếu" so như chuỗi (`pid COLLATE "C"` ở SQL, so chuỗi ở JS): từ phiếu thứ 1000 của một sổ, `PH-1000`
  đứng trước `PH-999` khi cùng ngày. Harness không sinh tới 1000 phiếu nên không kiểm; cần chủ nghiệp vụ xác nhận
  "theo mã phiếu" là theo chuỗi hay theo số trước khi có sổ chạm mốc đó.
