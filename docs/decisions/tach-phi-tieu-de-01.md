# TACH-PHI-TIEU-DE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Ngoại lệ của [`PHU-PHI-01`](phu-phi-01.md) (8): **cột phí trên tab khách có tên nhận ra được thì tiền ở cột đó vào đúng loại phí, không vào Khác.** Cột không tên, tên lạ (phí hủy, DET, kiểm cadmium, cân xe, 拖车...) hoặc tên chứa từ hai loại trở lên ("Neo / Phi dien / Dong ghep") vẫn là Khác như (8).

| Tên cột chứa | Loại phí trên web | Cột debit note |
|---|---|---|
| `NEO`, `押车`, `压车` (đồng âm), `OVERSTAY` | Neo | OVERSTAY 押车 |
| `GHÉP`, `拼柜`, `并柜`, `TRUCKING` | Ghép | TRUCKING 拼柜 |
| `ĐIỆN`, `发电`, `插电`, `电费`, `GENSET`, `GENERATOR` | Điện | GENSET 发电机/电费 |
| `卫生证`, `HEALTH`, `HC FEE` | Health + KĐ | HC FEE 卫生证 |
| `BẢO HIỂM`, `保险`, `INSURANCE`, `ÍNURANCE` (gõ sai) | Bảo hiểm | INSURANCE 保险 |
| `KIỂM ĐỊNH` | Kiểm định | INSPECTION 检验费 |

- `卫生证` là Health cert (người dùng xác nhận). Ghi vào loại "Health + KĐ" vì đó là cột HC FEE mặc định của mọi sổ ([`COT-PHU-PHI-01`](cot-phu-phi-01.md)); loại "Health cert" không có cột nên sẽ hiện ở cột Khác. Debit note in hai loại như nhau.
- Cột `开发电器` (chữ gõ lệch, nhiều khả năng là `发电机`) là Điện, theo câu hỏi của người dùng ("phí điện hay máy phát"); cột này chưa thấy có tiền.
- **Chỉ tách khi số khớp:** tổng các ô phí giữa cột ngày/nơi đến và cột đơn giá bằng đúng TOTAL − đơn giá của dòng tab, tới từng đồng, và tổng khoản phí trên web bằng đúng số đó (hoặc dòng sổ gốc có TOTAL − đơn giá bằng số đó, như việc 2 của [`MAY-PS-01`](may-ps-01.md)). Dòng khác, dòng web đã phân loại khác, nhiều chuyến khớp, hay thay khoản làm mất ghi chú người gõ thì để nguyên.
- **Không đổi tiền:** ghi bằng `rewrite_trip_fees`, Thành tiền, số dư và phân bổ phiếu thu giữ nguyên, không sinh dòng điều chỉnh. Tháng khóa thì mở, ghi, khóa lại như [`MAY-KHOA-01`](may-khoa-01.md). Sheet không bị đụng tới.
- Phần trừ ở cột đã thu (phiếu nhãn KHÁC) không đổi; khoản trên chuyến ghi đủ như ô Sheet.

## Ngày / nguồn

19/11/2026, chat. Người dùng so một sổ trên Sheet (cột phí tách theo loại) với web (cả ô vào Khác) và hỏi cách tách cho đúng; Claude đề xuất ngoại lệ này, người dùng trả lời "ok", xác nhận `卫生证` là Health cert và `开发电器` là phí điện. Người dùng nêu thêm hướng định dạng lại tiêu đề các tab Sheet; Claude đề xuất làm sau, chỉ đổi chữ tiêu đề, không chèn/xóa cột.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Công cụ một lần [`tools/v7_split_fee_by_header.py`](../../cong-no-web-handoff/tools/v7_split_fee_by_header.py), mặc định chỉ đếm; `--apply` chỉ chạy sau khi người dùng xem số đếm. Máy đối soát chưa tự tách chuyến mới theo tên cột: CÒN MỞ, làm khi số đếm cho thấy đáng làm. Hết hiệu lực khi chuyển hẳn khỏi Sheet.
