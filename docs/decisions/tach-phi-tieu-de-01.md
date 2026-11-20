# TACH-PHI-TIEU-DE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Ngoại lệ của [`PHU-PHI-01`](phu-phi-01.md) (8): **cột phí trên tab khách có tên nhận ra được thì tiền ở cột đó vào đúng loại phí, không vào Khác.** Cột không tên, tên lạ (DET, kiểm cadmium, 拖车, 重新贴标签...) hoặc tên chứa từ hai loại trở lên ("Neo / Phi dien / Dong ghep") vẫn là Khác như (8).

| Tên cột chứa | Loại phí trên web | Cột debit note |
|---|---|---|
| `NEO`, `押车`, `压车` (đồng âm), `OVERSTAY` | Neo | OVERSTAY 押车 |
| `GHÉP`, `拼柜`, `并柜`, `TRUCKING` | Ghép | TRUCKING 拼柜 |
| `ĐIỆN`, `发电`, `插电`, `电费`, `GENSET`, `GENERATOR` | Điện | GENSET 发电机/电费 |
| `卫生证`, `HEALTH`, `HC FEE` | Health + KĐ | HC FEE 卫生证 |
| `BẢO HIỂM`, `保险`, `INSURANCE`, `ÍNURANCE` (gõ sai) | Bảo hiểm | INSURANCE 保险 |
| `KIỂM ĐỊNH` | Kiểm định | INSPECTION 检验费 |
| `过磅`, `CÂN HÀNG`, `CÂN XE` | Cân hàng (loại mới) | cột riêng của sổ, sau bảy cột |
| `LOCAL`, `本地` | Local charge (loại mới) | cột riêng của sổ, sau bảy cột |
| `LƯU BÃI`, `LƯU KHO`, `STORAGE`, `早装产生` | Lưu bãi | STORAGE 早装产生费用 |
| `PHÍ HỦY`, `HỦY CONT`, `CANCEL`, `取消` | Phí hủy | CANCELLATION 取消订柜费 |
| `SỬA BILL`, `AMD FEE`, `AMEND`, `改单` | Sửa bill | AMD 改单费 |

- Năm dòng cuối bảng bổ sung 19/11/2026 (mục Ngày / nguồn). Không dùng chữ trần `CÂN`, `HỦY`, `WEIGH`, `AMD`: `CANCEL` chứa `CAN`, tên người có `HUY`, `OVERWEIGHT` là phí quá tải. Cân hàng và Local charge là loại mới trong danh mục (migration `2026-11-19-v7-tach-phi-loai-moi.sql`), không phải cột mặc định: sổ có cột riêng cho loại đó khi máy hoặc công cụ vừa tách được tiền vào loại đó (chỉ thêm cột, không đổi cột đang có). Debit note in loại có cột riêng sau bảy cột khi có số ([`DEBIT-NOTE-04`](debit-note-04.md) (2)).
- `卫生证` là Health cert (người dùng xác nhận). Ghi vào loại "Health + KĐ" vì đó là cột HC FEE mặc định của mọi sổ ([`COT-PHU-PHI-01`](cot-phu-phi-01.md)); loại "Health cert" không có cột nên sẽ hiện ở cột Khác. Debit note in hai loại như nhau.
- Cột `开发电器` (chữ gõ lệch, nhiều khả năng là `发电机`) là Điện, theo câu hỏi của người dùng ("phí điện hay máy phát"); cột này chưa thấy có tiền.
- **Chỉ tách khi số khớp:** tổng các ô phí giữa cột ngày/nơi đến và cột đơn giá bằng đúng TOTAL − đơn giá của dòng tab, tới từng đồng, và tổng khoản phí trên web bằng đúng số đó (hoặc dòng sổ gốc có TOTAL − đơn giá bằng số đó, như việc 2 của [`MAY-PS-01`](may-ps-01.md)). Dòng khác, dòng web đã phân loại khác, nhiều chuyến khớp, hay thay khoản làm mất ghi chú người gõ thì để nguyên.
- **Không đổi tiền:** ghi bằng `rewrite_trip_fees`, Thành tiền, số dư và phân bổ phiếu thu giữ nguyên, không sinh dòng điều chỉnh. Tháng khóa thì mở, ghi, khóa lại như [`MAY-KHOA-01`](may-khoa-01.md). Sheet không bị đụng tới.
- Phần trừ ở cột đã thu (phiếu nhãn KHÁC) không đổi; khoản trên chuyến ghi đủ như ô Sheet.

## Ngày / nguồn

19/11/2026, chat. Người dùng so một sổ trên Sheet (cột phí tách theo loại) với web (cả ô vào Khác) và hỏi cách tách cho đúng; Claude đề xuất ngoại lệ này, người dùng trả lời "ok", xác nhận `卫生证` là Health cert và `开发电器` là phí điện. Người dùng nêu thêm hướng định dạng lại tiêu đề các tab Sheet; Claude đề xuất làm sau, chỉ đổi chữ tiêu đề, không chèn/xóa cột.

Bổ sung cùng ngày, chat: người dùng gửi ảnh sổ có cột `过磅` (cân hàng) và `LOCAL CHARGE 本地费用` vẫn vào Khác, hỏi cách quét tên cột cho đủ. Claude đề xuất bốn bước (quét tên cột, thêm loại Cân hàng và Local charge cùng tên cột của Lưu bãi/Phí hủy/Sửa bill, chạy lại công cụ, máy tự tách chuyến mới); người dùng trả lời "Làm cả bốn bước". Quét chỉ đọc mọi tab trên `hao` 19/11/2026: ô có tiền mà tên cột chưa nhận ra là `LOCAL CHARGE 本地费用` 8 ô, `过磅` 2 ô, `CANCEL FEE 取消还空箱费` 2 ô (đều ở một tab), cùng `拖车` 10, `重新贴标签` 7, `DET FEE 滞箱费` 4 và một cột phí trả thêm cho tài xế 5 (chưa có loại, vẫn Khác); cột `OTHER FEE` chung 890 ô và cột không tên 206 ô vẫn Khác.

## Hiệu lực và giới hạn

ĐÃ CHỐT; ĐÃ CHẠY trên `hao` 19/11/2026: 1.372 dòng ở 80 sổ, số dư không đổi ([nhật ký](../deploys/2026-11-19-tach-phi-tieu-de.md)). Công cụ một lần [`tools/v7_split_fee_by_header.py`](../../cong-no-web-handoff/tools/v7_split_fee_by_header.py), mặc định chỉ đếm; dòng có ô phí âm để nguyên. Bổ sung 19/11/2026 ĐÃ TRIỂN KHAI trên `hao` ([nhật ký](../deploys/2026-11-19-tach-phi-loai-moi.md)): migration hai loại mới, 11 chuyến ở 3 sổ tách bằng công cụ (số dư không đổi), máy tự tách ĐÃ BẬT. Máy theo Sheet tự tách chuyến mới theo tên cột (bật bằng `WEBDEBIT_AUTO_SHEET=headers`): runner giá ghi tiền theo loại vào `prices.json` (`sheet_fees`), máy lập kế hoạch bằng cùng luật và ghi `rewrite_trip_fees`, mọi tháng vì không đổi tiền (tháng khóa mở, ghi, khóa lại). Dòng không tách được vẫn là Khác như trước, không thành việc của người. Hết hiệu lực khi chuyển hẳn khỏi Sheet.
