# Gói triển khai tay: bảng giá + ảnh chứng từ (29/10/2026)

**ĐỀ XUẤT, CHƯA CHẠY.** Chỉ chạy khi người dùng ra lệnh chạy; không bước nào tự chạy. Lượt `Deploy hao` đỏ ở cổng SQL
là chủ ý, không phải lỗi.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#147 (BANG-GIA-01, `5ae1c84`), FinanceBullkk/webdebit#148 (CHUNG-TU-01, `639c1d7`) |
| Quyết định | [`BANG-GIA-01`](../decisions/bang-gia-01.md), [`CHUNG-TU-01`](../decisions/chung-tu-01.md) |
| Migration, **đúng thứ tự** | 1. `2026-10-29-v7-bang-gia.sql` 2. `2026-10-29-v7-chung-tu.sql` |
| Release app | SHA `main` lúc chạy (lấy lại bằng `git rev-parse origin/main`; `639c1d7` hoặc mới hơn, CI xanh đúng SHA) |
| Trạng thái `hao` (theo log `Deploy hao`) | release `a7987dd`; diff `a7987dd..639c1d7` ở thư mục migration chỉ gồm 3 file: hai migration trên và `chung-tu.rollback.sql` |
| Ghi tiền | Không. Chỉ thêm bảng cấu hình giá, bảng ảnh, hàm và loại sự kiện; không đổi tiền, phân bổ, dữ liệu có sẵn |

## ĐÃ KIỂM CHỨNG (máy dev, dữ liệu giả, ngày 29/10/2026)

- Harness backend PostgreSQL 18 dùng một lần trên nhánh #148 (`5ecd290`, đã gồm #147; main sau đó chỉ thêm #149 giao diện): 67 case, 65 đạt, 2 `skipped` cũ (7.11c, 7.15c); `test_pg_v7_grants.py` và `test_pg_v7_p0_harness.py` thoát 0; `npm run check` đạt; CI GitHub xanh đủ job.
- Hai migration chạy hai lượt, theo cả hai thứ tự, không làm mất loại sự kiện nào: mỗi migration giờ mang đủ `event_kind_check`/`event_snapshot_check` của cả hai (sửa trong #148, gồm thêm hai loại ảnh vào `2026-10-29-v7-bang-gia.sql`).
- **CÒN MỞ:** chưa thử trên bản sao dữ liệu thật của `hao`; chưa thử tay trên web sau nâng.

## Trước khi bắt đầu (CHỈ ĐỌC, trên `hao`)

Xác nhận `hao` đúng như giả định, vì bản này không nhìn thấy `hao`:

```sql
SELECT to_regclass('sokhach.price_rate') IS NOT NULL AS co_bang_gia,
       to_regclass('sokhach.receipt_image') IS NOT NULL AS co_anh_chung_tu;
```

Kỳ vọng `f|f`. Nếu một trong hai là `t` thì migration đó đã áp: dừng, báo lại, không chạy đè. Kiểm tiếp: đĩa trống
đủ cho dump (ảnh lưu `bytea` trong DB: khoảng 1–5 GB/năm), API ghi không có phiên nhập dở, CI xanh đúng SHA release.

## Các bước (cùng trình tự các đợt 28/10, xem [runbook](../v7-deploy-runbook.md#phụ-phí-pr-a--nâng-db-đang-có-đã-chạy-trên-hao-28102026))

1. **Bản sao trước.** Dump `webdebit_v7` đang chạy, restore vào DB thử (thu hồi CONNECT của PUBLIC). Trên DB thử chạy
   lần lượt `bang-gia.sql` hai lượt, rồi `chung-tu.sql` hai lượt. Đạt khi: số dư từng khách/tháng
   (`v_outstanding_month`) và số dòng mọi bảng cũ không đổi; `v7_post_deploy_check.sql` OK; xóa DB thử.
2. **Cửa sổ dừng ghi** (dự kiến vài chục giây, chưa đo): dừng `v7-ledger-api.service`; dump + hash; restore thử khớp số dư
   và số dòng; chạy `bang-gia.sql` rồi `chung-tu.sql` (mỗi file một transaction, dừng ngay khi lỗi, không sửa SQL để né);
   kiểm số dư/số dòng không đổi.
3. **Đổi release app:** `webdebit-release.sh deploy <sha>` dưới user deploy (script tự restart và kiểm sống). Đặt
   `.release-sha` = SHA vừa triển khai để lượt `Deploy hao` sau có mốc diff đúng.
4. **Kiểm sau:** `v7_post_deploy_check.sql` (app thêm `save_price_table`, `apply_price_table`, `attach_receipt_image`,
   `remove_receipt_image`; app + reader thêm `get_price_table`, `get_price_status`, `list_receipt_images`,
   `get_receipt_image`, `find_receipt_image`; mọi helper `_price_*`, `_guard_receipt_image`, `_receipt_image_matches`
   không được EXECUTE). Số dư 236/236 khách không đổi. Bảng giá của mọi sổ trống (chưa nhập) và 0 ảnh.
5. **Ghi nhật ký** vào file này: người cho chạy và lúc nào, SHA, kết quả từng kiểm, tên thư mục evidence/backup trên
   `hao` (dump, hash, log nằm ngoài Git). Cập nhật trạng thái "ĐÃ TRIỂN KHAI" trong hai file quyết định ở cùng PR.

## Rollback

- Trước khi có dữ liệu mới: `2026-10-29-v7-chung-tu.rollback.sql` (dừng `RECEIPT_IMAGE_EVENTS_PRESENT`/`RECEIPT_IMAGES_PRESENT`
  nếu đã có ảnh; trả ràng buộc event về trạng thái có loại bảng giá). Bảng giá không có file `.rollback.sql`.
- Đã commit và cần quay lại: restore dump chụp ngay trước nâng vào DB mới (quy trình M2-11), không viết SQL "down" tay.
- App: trỏ `CURRENT_LINK` về release cũ trong `RELEASES_DIR` rồi restart; DB mới tương thích release cũ vì chỉ thêm.

## Rủi ro cần biết

- Chạy `chung-tu.sql` **trước** `bang-gia.sql` vẫn an toàn sau sửa này, nhưng giữ thứ tự trên để khớp harness.
- Ảnh làm dump lớn dần: kiểm timer `v7_backup.py` và chỗ trống đĩa trước khi bật nhập ảnh cho người dùng.
- Kiểm sống chỉ chứng minh tiến trình sống, không chứng minh sổ đúng; cần người dùng thử tay bảng giá và dán một ảnh vào phiếu thử trên bản sao.
