# BANG-GIA-05

[← Sổ quyết định](../decisions.md)

## Quyết định

Khung **Bảng giá** của sổ khách dựng lại dạng **ma trận** (phương án B): mỗi cặp nơi đi · nơi đến một hàng, mỗi đợt giá một cặp cột Giá khách | Giá TT; đợt đang dùng tô nhạt, ô khác đợt trước in đậm, thêm đợt mới là thêm cặp cột bên phải chép giá đợt đang dùng; khối phải là shipper áp giá TT (kèm shipper trong sổ đang lấy giá khách) hoặc đợt đang sửa; có bước xem lại trước khi lưu do server tính. Thay lưới phẳng "giống vùng Sheet" của [`BANG-GIA-01`](bang-gia-01.md) (29/10/2026).

Chỉ đổi bố cục và luồng thao tác. Luật tiền giữ nguyên: [`BANG-GIA-01`](bang-gia-01.md) … [`BANG-GIA-04`](bang-gia-04.md), hợp đồng `GET/POST /api/v7/price-table` không đổi.

## Ngày / nguồn

13/11/2026, người dùng chê khung cũ "UI sơ khai, flow không hiệu quả", xem 3 phương án trên canvas và trả lời trong chat "Làm phương án B".

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng bố cục. Lưới ma trận ĐÃ TRIỂN KHAI trên `hao` 13/11/2026 (PR #407, `Deploy hao` xanh). Bước xem lại trước khi lưu cần migration `2026-11-13-v7-xem-truoc-bang-gia.sql` (hàm `preview_price_table`, không đổi dữ liệu). Chi tiết hành vi (lỗi tại ô, khối phải, dán gộp, số đợt hiện mặc định, cách server tính bước xem lại) là ĐỀ XUẤT của Claude theo `CLAUDE-ALL-01`, ghi ở [spec](../../specs/v7-bang-gia-ma-tran.md). Hai thứ Claude tự thêm trong mockup: người dùng trả lời trong chat 13/11/2026 "Chỉ dải nơi đi" — dải "N chuyến chưa có giá vì nơi đi ngoài bảng … [Thêm nơi đi]" ĐÃ CHỐT, làm; nút "Cộng đều +N vào cột mới" KHÔNG LÀM. Trạng thái triển khai ghi trong spec và `docs/deploys/`.
