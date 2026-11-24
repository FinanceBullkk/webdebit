# H. Kế hoạch migration và rollout

Trạng thái: **ĐỀ XUẤT** (Claude, 24/11/2026). Chưa chạy bước nào. Không DDL, không nạp dữ liệu, không bật cờ cho tới khi quyết định chặn ở [I](I-decision-register.md) có người chốt và PR migration được duyệt theo quy trình repo.

[← Mục lục](README.md) · PRD: [E](E-prd-p0.md) · UAT: [G](G-uat-test.md)

## 1. Nguyên tắc

1. **Thêm, không thay:** không đổi bảng, hàm, máy ghi, màn nào của sổ nợ ở P0-a/P0-b; không tắt quy trình đang chạy (Sheet, nhóm chat, Excel) cho tới khi phạm vi tương ứng qua cổng.
2. **Không di chuyển dữ liệu cũ vào sổ tiền:** đầu vào chỉ là danh mục pháp nhân/tài khoản, số dư mở có bằng chứng, file sao kê.
3. **Một tài khoản, một tháng trước;** mở rộng sau khi tài khoản trước qua cổng.
4. **Một nguồn ghi authoritative** cho mỗi loại dữ liệu ở mọi thời điểm; song song nghĩa là **so**, không phải **ghi hai nơi**.
5. **Lùi bằng tắt cờ**, không xóa lịch sử, không sửa số dư bằng tay.

## 2. Giai đoạn và cổng

| Bước | Việc | Cổng (đo được) | Ký |
| --- | --- | --- | --- |
| **0 — Discovery** (không code) | Chốt quyết định chặn P0-a; nhận 1 tháng sao kê thật của tài khoản thí điểm (ngoài repo); tải cùng kỳ hai lần để biết mã giao dịch có ổn định không; khảo sát cột, định dạng (`.xlsx`/`.xls`/CSV), số dư từng dòng, dòng tổng, ngày giá trị; đếm loại giao dịch; đo thời gian thao tác hiện tại (xin duyệt, báo chuyển, hỏi số dư) | Hồ sơ Discovery chỉ có số đếm; hợp đồng bộ đọc `vcb-…@1`; quyết định B2/B3 của ADR-TIEN-03 | Chủ DN, kế toán |
| **P0-a xây** | Migration `tien`, bộ đọc, API, 3 màn (Sổ tiền, Đối soát cuối ngày, Tổng quan tiền), máy canh, harness; cờ `off` | `npm run check`, harness mới, các `AT` của P0-a xanh; review | Kỹ thuật |
| **P0-a shadow** | Cờ `shadow` trên `hao`; nhập lại tháng lịch sử; chạy song song với cách cũ | AC-a1…AC-a4 ([E §8](E-prd-p0.md#8-tiêu-chí-nghiệm-thu)) | Kế toán, người review |
| **P0-a bật** | Cờ `on`; nhập mỗi ngày làm việc; ký ngày; sếp đọc thẻ số dư | AC-a5: 4 tuần; sau đó **ngưng hỏi số dư trong nhóm** cho tài khoản này | Chủ DN |
| **P0-b** | Đề nghị chi, duyệt, báo thực hiện, ghép chi; 2 màn (Việc của tôi, Duyệt chi); cờ `WEBDEBIT_TIEN_CHI` | AC-b1, AC-b2; sau đó **ngưng xin duyệt bằng tin nhắn** cho phạm vi chi đã chốt, từ ngày chủ DN công bố | Chủ DN |
| **P0-c shadow** | Báo thu bằng "khách báo đã chuyển"; đối chiếu chỉ đọc tiền về ↔ phiếu; luật gợi ý | AC-c1 (1 tháng) | Kế toán, team công nợ |
| **P0-c ghi** (chỉ khi QD-16 = B) | Sổ thí điểm: bật ghi phiếu từ ngân hàng, tắt máy ghi phiếu theo Sheet cho đúng sổ đó, cùng một lần đổi cấu hình | AC-c2; đối soát tổng khách với Sheet không lệch | Chủ DN |
| P1 | Thêm tài khoản (kể cả USD), quỹ + kiểm quỹ, tiền khách (sau cổng pháp lý), phải trả, liên công ty | Mỗi tài khoản lặp cổng P0-a shadow | — |
| P2 | Dự báo 7/30 ngày, lãi lỗ | Nguồn doanh thu/chi phí đủ; không suy lãi lỗ chỉ từ sao kê (v3 §9) | — |

## 3. Chọn tài khoản thí điểm (QD-02)

Tiêu chí, theo thứ tự:

1. Tài khoản **công ty**, VND, một pháp nhân, có quyền tải Excel từ ngân hàng.
2. **Không** có dòng tiền hàng khách Trung Quốc (P0 chưa hỗ trợ; v3 §3.3 không cho đưa tài khoản có nghiệp vụ chưa hỗ trợ vào vận hành chính thức).
3. Có đủ giao dịch thu cước và chi thường để đo (đề xuất: ≥ 100 dòng/tháng — *suy luận*, xác nhận ở Discovery).
4. Ưu tiên tài khoản mà kế toán đang tự chuyển tiền sau khi sếp duyệt (để P0-b đo được ngay).

**Lưu ý (QD-18):** debit note mặc định in tài khoản USD; nếu phần lớn tiền cước về tài khoản USD thì tài khoản VND thí điểm sẽ không thấy phần đó — Discovery phải đếm tỷ lệ này trước khi chọn.

## 4. Số dư mở

1. Kế toán chọn ngày bắt đầu = đầu một tháng dương lịch, giờ VN (QD-10).
2. Số dư mở lấy từ sao kê ngân hàng của ngày trước đó; người review **khác** kế toán tự tải để đối chiếu.
3. Nhập bằng lệnh `opening_set` (không SQL tay), kèm ghi chú bằng chứng; sai thì không sửa — tạo tài khoản mới hoặc điều chỉnh có quyết định.
4. Kiểm: số dư mở + giao dịch tháng lịch sử = số dư cuối tháng trên sao kê (AC-a1).

## 5. Thử một tháng lịch sử và shadow

- Nhập lại tháng lịch sử theo đúng SOP cuối ngày ([B §5](B-quy-trinh-as-is-to-be.md#5-to-be-cuối-ngày-eod)), mỗi ngày một lần, có cố ý chồng kỳ và nhập lặp để thử chống trùng.
- Kế toán dựng **tập chuẩn** bằng tay cho tháng đó (mỗi giao dịch thuộc loại gì, của ai) ngoài repo; so kết quả phân bổ với tập chuẩn bằng số đếm.
- Trong shadow, luật gợi ý chạy và lưu gợi ý; đo độ chính xác theo dòng và theo giá trị (G §4).
- Song song: quy trình cũ chạy như cũ; sổ tiền không thay quy trình nào, không ghi sổ nợ.

## 6. Song song không ghi hai lần

| Dữ liệu | Nguồn ghi trong song song | Sổ tiền làm gì |
| --- | --- | --- |
| Phiếu thu sổ nợ | Sheet → máy (như hiện tại) | Chỉ đọc, đối chiếu (P0-c shadow) |
| Phiếu thu sổ nợ sau QD-16 = B, cho sổ thí điểm | Phân bổ ngân hàng → `record_receipt` | Ghi; máy theo Sheet **tắt** cho sổ đó (I-14) |
| Duyệt chi | Tin nhắn → đề nghị trên web từ ngày công bố | Một nơi duyệt duy nhất sau ngày công bố |
| Ứng/hoàn Đội xe | Màn Đội xe (như hiện tại) | Chỉ phân bổ giao dịch vào dòng có sẵn |
| Số dư khách Trung Quốc | Excel (tới P1) | Chỉ gắn nhãn `customer_funds_pending` |

## 7. Cờ tính năng

| Cờ | Giá trị | Tác dụng |
| --- | --- | --- |
| `WEBDEBIT_TIEN` | `off` / `shadow` / `on` | `off`: không route `tien`; `shadow`: chỉ vai review/quản trị thấy; `on`: theo vai |
| `WEBDEBIT_TIEN_CHI` | `off` / `on` | Đề nghị chi, duyệt, báo thực hiện |
| `WEBDEBIT_TIEN_AR_POST` | danh sách mã sổ | Sổ được ghi phiếu từ ngân hàng; máy theo Sheet bỏ qua phiếu của các sổ này; khởi động từ chối nếu cấu hình mâu thuẫn |

Cờ đọc lúc khởi động như các cờ `WEBDEBIT_*` hiện có; đổi cờ ghi vào nhật ký vận hành.

## 8. UAT và cutover

1. UAT theo [G §2](G-uat-test.md#2-uat) trên `hao` ở chế độ `shadow`; mỗi ca có người chạy và người ký; ghi số đếm vào `docs/deploys/`.
2. **Cutover theo phạm vi**, không theo "ngày lớn": tài khoản thí điểm `on` (P0-a) → ngày công bố duyệt chi trên web (P0-b) → sổ thí điểm ghi phiếu từ ngân hàng (P0-c, nếu chọn).
3. Mỗi cutover có biên bản: phạm vi, ngày, số dư mở/cuối đã đối chiếu, người ký, thao tác cũ được ngưng.
4. Triển khai SQL theo [`DEPLOY-CLAUDE-01`](../../docs/decisions/deploy-claude-01.md): sao lưu trước, `ON_ERROR_STOP`, kiểm sau triển khai, so tổng từng khách chứng minh sổ nợ không đổi, nhật ký; vai quản trị đầu tiên tạo bằng bước runbook có chủ doanh nghiệp xác nhận.

## 9. Lùi (rollback)

| Tình huống | Cách lùi | Không làm |
| --- | --- | --- |
| Lỗi giao diện/API | Cờ `off` hoặc revert PR app | Không xóa dữ liệu `tien` |
| Lô nhập sai | Hủy lô có lý do, nhập lại | Không sửa dòng trong DB |
| Phân bổ sai | Thay bộ hoặc gỡ có lý do | Không xóa dòng phân bổ |
| Ghi phiếu sổ nợ từ ngân hàng sai (P0-c) | Bỏ sổ khỏi `WEBDEBIT_TIEN_AR_POST`, bật lại máy theo Sheet cho sổ đó; hủy phiếu sai có lý do theo luật hiện có; đối soát tổng với Sheet | Không xóa phiếu, không sửa phân bổ tay |
| Migration lỗi giữa chừng | Transaction + `ON_ERROR_STOP` nên không áp gì; khôi phục từ bản sao lưu ngay trước nếu cần | Không chạy tay từng câu |
| Bỏ hẳn module | Cờ `off`, giữ schema để tra; chỉ `DROP SCHEMA` sau khi xuất CSV đủ kỳ và có quyết định | Không `DROP` trong đường lùi thường |

Vì `tien` không ghi `sokhach` ở P0-a/P0-b và không có khóa ngoại sang `sokhach`, mọi đường lùi trên không chạm sổ nợ (AT-01.1, AT-18.1).

## 10. Rủi ro của kế hoạch

| Rủi ro | Dấu hiệu sớm | Chặn |
| --- | --- | --- |
| Sao kê không có mã ổn định, không có số dư từng dòng | Discovery: hai lần tải cùng kỳ ra mã khác | Dấu vân + bội số; ký coverage cần bằng chứng số dư của người khác |
| VCB chỉ xuất `.xls` | Discovery | QD-07 (thư viện ghim băm hoặc định dạng khác); cấm mở/lưu lại |
| Kế toán không kịp nhập mỗi ngày | Sao kê cũ > 2 ngày làm việc | Cổng P0-a bật đo đúng chỉ số này; chỉnh lịch (QD-04), không thêm kết nối ngân hàng |
| Phân loại tùy tiện | Tỷ lệ `other` cao | Danh mục QD-11; báo cáo tuần |
| Trùng vai thành thói quen | Cờ `role_overlap` mỗi ngày | Tóm tắt tuần cho chủ DN; chủ DN tự tải sao kê đối chiếu |
| Lấn sang ERP | Đòi bút toán, hóa đơn trong P0 | Phạm vi [E §2](E-prd-p0.md#2-phạm-vi); mở rộng qua quyết định mới |
