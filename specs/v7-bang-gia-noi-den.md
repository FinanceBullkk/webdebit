# Bảng giá theo nơi đến

> 13/11/2026: [BANG-GIA-04](../docs/decisions/bang-gia-04.md) đổi dòng 8 — Nơi đến trống là giá chung của nơi đi, dòng đúng nơi đến thắng khi phủ ngày chuyến; Nơi đến không còn bắt buộc khi lưu.

Trạng thái: đề xuất triển khai 10/11/2026. Người dùng yêu cầu bảng giá có **Nơi đến** và chốt dòng giá cũ thiếu Nơi đến **chỉ áp khi bổ sung nơi đến**.

## Hợp đồng hoàn thành

- Lưới bảng giá có cột Nơi đến sau Nơi đi. Dán, gõ, mở lại, đổi đợt giá đều giữ nơi đến.
- Tra giá theo sổ, ngày, nơi đi, nơi đến, nhóm shipper. Nơi đến chuyến hoặc dòng bảng trống không sinh giá; không coi trống là mọi nơi đến.
- Một nơi đi có nhiều nơi đến trong cùng đợt và nhóm giá. Trùng cả cặp nơi đi/nơi đến, nhóm, khoảng ngày bị chặn.
- Giá gõ tay, giá từ Sheet, tháng khóa, opening và chuyến không còn giá giữ nguyên theo BANG-GIA-02. Lưu bảng có thể đổi tiền chuyến đang theo bảng trong tháng mở; phải giữ thông báo trước/sau.
- Kiểm bằng browser fixture và PostgreSQL dùng một lần. Không chạy migration, nạp giá hoặc sửa DB/Sheet thật trong việc này. Dừng nếu migration không bảo toàn dữ liệu cũ hay kiểm không đạt.

Đổi BANG-GIA-01 mục Q4: từ ngày này giá phân biệt theo nơi đến. Bảng giá cũ cần bổ sung nơi đến trước khi tra tiếp.
