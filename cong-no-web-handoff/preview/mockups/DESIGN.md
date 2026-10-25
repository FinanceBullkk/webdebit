# DESIGN — token thiết kế dùng chung cho webdebit

Cập nhật 24/10/2026 sau vòng duyệt mockup (v3 chi tiết · v4 nhìn nhanh · danh sách đòi nợ heat map).
Trạng thái: **người dùng đã duyệt hướng qua mockup HTML** (dashboard-tong-quan-v3, dashboard-tong-quan-v4,
danh-sach-doi-no); chưa qua Penpot — nếu cần quy trình Penpot chuẩn thì chuyển sau, nội dung không đổi.
Mục tiêu: mọi trang web dùng chung một bộ token và một giọng văn, hết tình trạng mỗi trang một tông.

## Nguyên tắc

- Thuần CSS, không framework, không font ngoài (CSP app thật: `default-src 'none'`); font stack hệ thống đủ dấu tiếng Việt.
- Tiền là chuỗi VND nguyên; hiển thị `font-variant-numeric: tabular-nums`, nhóm nghìn `vi-VN`, đơn vị "đ".
- **Kỷ luật màu**: xám + MỘT xanh navy; đỏ chỉ dành cho cảnh báo thật (nợ quá hạn, số đếm việc). Không màu trang trí.
- **Ngôn ngữ thường ngày**: nhãn là câu nói tự nhiên ("Khách đang nợ mình", "Nợ bao lâu rồi?", "Thu có theo kịp nợ mới không?"); không thuật ngữ kế toán khi có cách nói thường ("trả thừa" thay "dư"/"ứng trước" trên nhãn; thuật ngữ nghiệp vụ giữ ở drawer/sổ chi tiết). Giải thích chỉ xuất hiện khi bấm vào (drawer), không rải chú thích trên màn hình.
- Hover/focus 120–150ms; tôn trọng `prefers-reduced-motion`; mọi hàng bấm được cao ≥44px; focus ring 2px navy.

## Màu (CSS custom properties)

| Token | Giá trị | Dùng cho |
| --- | --- | --- |
| `--bg` / `--card` | `#f6f7f9` / `#ffffff` | nền trang / bề mặt thẻ |
| `--ink` / `--ink2` / `--muted` | `#111827` / `#374151` / `#6b7280` | chữ chính/phụ/ghi chú (≥4.5:1 trên trắng) |
| `--line` / `--line2` | `#e5e7eb` / `#d1d5db` | viền trong / viền ngoài |
| `--brand` / `--link` / `--accent` | `#1e4e8c` / `#1d4ed8` | tiêu đề / liên kết / hành động chính |
| `--b-current` → `--b-over6` | `#9aa9bc` → `#71839c` → `#46587a` → `#b91c1c` | thang tuổi nợ: cùng sắc đậm dần theo độ già, chỉ nhóm trên 6 tháng được đỏ |
| `--bad` / `--bad-bg` | `#b91c1c` / `#fdecec` | cảnh báo: nợ quá hạn, số đếm việc |
| `--ok` / `--ok-bg` | `#15803d` / `#e7f0e9` | trạng thái tốt (khớp, tháng mở) |
| `--info-bg` | `#eef2f6` | hover, nền chip đếm |

## Typography

- Stack `"Segoe UI", system-ui, sans-serif`; body 14px/1.5; số tiền `.money` (tabular-nums, nowrap).
- Scale: 11 (th uppercase) · 12 · 13 (phụ) · 14 (body) · 15 (h2 thẻ) · 20 (h1 trang) · 27 (KPI) · 46 (số hero).
- Trọng số: 400 body · 600 nhãn/nút · 700 tiêu đề · 800 KPI/hero.

## Spacing & bề mặt

- Nhịp 4/8: 4 · 8 · 12 · 16 · 20; khe lưới thẻ 12px.
- Thẻ: nền trắng, viền `--line` 1px, bo 8px, bóng `0 1px 2px #1118270d`. Khối ĐỀ XUẤT/CẦN BACKEND: nét đứt vàng + nhãn.

## Biểu diễn dữ liệu (chốt theo research 24/10/2026)

| Dạng | Dùng cho | Trang |
| --- | --- | --- |
| Thanh ngang từng nhóm (scale theo nhóm lớn nhất, già nhất trên cùng) | Aging tại một thời điểm | v3, v4 |
| Cột xếp lớp theo tháng | Cơ cấu aging theo thời gian; tổng cột ghi trên đỉnh | v4 |
| Cột kép (xám vs navy) | Nợ mới vs đã thu từng tháng | v4 |
| Đường + vùng nhạt | Tổng nợ theo tháng (đặt cạnh số hero) | v4 |
| Hàng ưu tiên + dải tháng (sort mặc định theo tiền quá hạn; 1 mini-bar/tháng, đỏ = đã quá 3 tháng) | Danh sách đòi nợ — chọn trong 3 phương án ngày 24/10/2026 | danh-sach-doi-no |
| Heat map (khách × tháng) | Đã thử và thay bằng hướng trên sau feedback (mất hierarchy, phải đọc ô từng ô) | — |
| Không dùng | donut/pie cho aging; stacked bar cho so sánh một thời điểm | — |

## Thành phần dùng chung

Drawer chi tiết khách (mẫu history-panel của sổ V7: tổng nợ, nợ theo độ già, phiếu thu gần đây, việc phải xử lý, nút mở sổ) · chip "X tháng chưa trả" (đỏ ≥6, xám 3–5, nhạt <3) · KPI viền trái 3px màu semantic · bảng sort được (aria-sort khi code thật) · hàng bấm được min-height 44px.

## Cấu trúc 3 trang (đề xuất)

1. **Nhìn nhanh** (`dashboard-tong-quan-v4`): hero tổng nợ + đường 12 tháng → aging thanh ngang → nợ mới vs đã thu → cơ cấu aging theo tháng → khách nợ nhiều nhất (hàng thanh) → việc cần làm (đếm) → 2 khối đề xuất.
2. **Chi tiết** (`dashboard-tong-quan-v3`): dải 4 KPI → aging → khách nợ nhiều nhất → theo mặt hàng → hôm nay → việc cần làm → 2 khối đề xuất.
3. **Đòi nợ** (`danh-sach-doi-no`): heat map khách × nhóm tuổi + bảng khách cần chú ý.

## Áp dụng

Trang thật (`dashboard-v7`, `so-khach-v7`, `customer-ledger-workbench`) đưa token vào một stylesheet chung, thay dần màu hardcode. Mockup tham chiếu sống trong `preview/mockups/` (serve bằng `python -m http.server` từ thư mục mockups).
