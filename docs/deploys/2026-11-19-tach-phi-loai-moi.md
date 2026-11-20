# Triển khai: loại Cân hàng, Local charge và máy tách theo tên cột (19/11/2026)

**ĐÃ CHẠY trên `hao` 19/11/2026 (17:48–18:18 giờ VN).** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), quyết định [`TACH-PHI-TIEU-DE-01`](../decisions/tach-phi-tieu-de-01.md) (bổ sung cùng ngày) và [runbook](../v7-deploy-runbook.md#thêm-loại-cân-hàng-local-charge-và-máy-tách-theo-tên-cột-tach-phi-tieu-de-01-bổ-sung--nâng-db-release-bật-máy). Đợt trước của cùng quyết định: [tách 1.372 dòng](2026-11-19-tach-phi-tieu-de.md).

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Người dùng chọn "Làm cả bốn bước", rồi "Ghi và bật máy" sau khi xem số đếm (11 chuyến ở 3 sổ) |
| PR / release | #528, merge `d54ec44`; release tay `d54ec44` thay cho `119dc23` (giữa hai SHA chỉ có #528) |
| CI | 18/18 check xanh, gồm `postgres-v7-backend` (`--migration-test`, `v7_schema_snapshot.py --check`) |
| Review | Review độc lập (subagent): không đường nào đổi tiền; năm điểm nhẹ, bốn điểm đã sửa trong PR (bỏ `WEIGH` vì dính `OVERWEIGHT`, siết `AMD`/`早装`, `header_todo` chỉ sổ active, khóa lệnh gồm khoản cũ, lỗi lạ không làm kẹt lượt nền) |
| Migration | `2026-11-19-v7-tach-phi-loai-moi.sql`, SHA-256 `f9709d7ad73c08a629d6e70af41d9c457753d65e2a6846edcae85db142533049`, trùng bản trên `main` và bản đã thử |
| Ghi tiền | Không đổi tiền. 11 chuyến đổi loại phụ phí (`rewrite_trip_fees`), tổng phụ phí từng chuyến giữ nguyên |

## Quét tên cột (chỉ đọc, 16:5x)

Mọi tab khách qua Sheets API của `hao`. Ô có tiền mà tên cột chưa nhận ra: `LOCAL CHARGE 本地费用` 8, `过磅` 2, `CANCEL FEE 取消还空箱费` 2 (một tab); `拖车` 10, `重新贴标签` 7, `DET FEE 滞箱费` 4, một cột phí trả thêm cho tài xế 5 (chưa có loại, vẫn Khác). Cột `OTHER FEE` chung 890 ô, cột không tên 206 ô vẫn Khác.

## Thử migration trên bản sao (17:06)

Dump, khôi phục vào DB thử riêng, áp hai lượt (140 ms, 128 ms). Số dư, khoản phụ phí, cột, version sổ và số dòng mọi bảng (trừ `fee_type`) trùng trước/sau; catalog hàm không đổi; `fee_type` thêm đúng hai dòng; checker 9/9. Đã xóa DB thử.

## DB thật (17:48)

- Không có kết nối khác vào `webdebit_v7`; máy đối soát không chạy. Backup toàn phần, `pg_restore --list` đọc được (1027 dòng).
- Áp với `ON_ERROR_STOP`: 160 ms. Thêm `Cân hàng` (id 14) và `Local charge` (id 15). Dấu vân trùng trước/sau, catalog không đổi, checker 9/9.
- Release tay `d54ec44` bằng đúng gói của workflow (`git archive`) và `webdebit-release.sh` dưới `webdebit-deploy`: unit active, `/healthz` 200. Cảnh báo không dọn được vài release cũ có từ trước.
- Runner giá lượt 18:00 ghi `sheet_fees` cho 1.571 trên 10.745 dòng `prices.json`.

## Ghi một lần bằng công cụ (18:00)

- Đếm (không `--apply`): 11 chuyến tách được ở 3 sổ (10 ở tháng khóa, 1 ở tháng mở); 1.368 chuyến đã đúng từ đợt sáng (`DONE`).
- Ghi (`--apply`, user của API): 11 chuyến, cả lượt (đọc Sheet, ghi) 49 giây, 0 lỗi; thêm cột riêng ở 2 sổ. Tháng khóa đã mở, ghi, khóa lại.
- Trước/sau trùng: số dư từng khách và tháng, tổng phụ phí từng chuyến và dòng sổ gốc, `receipt_line`, số điều chỉnh, số phiếu thu, trạng thái khóa tháng.
- Khoản theo loại, trước → sau: Khác 447 → 437, Local charge 0 → 7, Cân hàng 0 → 2, Phí hủy 0 → 2, Neo 1.207 → 1.209, Ghép 22 → 23, Kiểm định 4 → 6.

## Thử máy `headers` trên bản sao (18:03)

Bản sao dựng từ dump trước khi nâng (17:48), áp migration, chạy hai lượt `Inbox.refresh_all` của release `d54ec44` chỉ với `WEBDEBIT_AUTO_SHEET=headers`, đọc đúng các bản chụp Sheet đang dùng. Vì `pg_hba` chỉ cho `v7_app` vào `webdebit_v7`, lệnh vào DB thử bằng `postgres` rồi `SET ROLE v7_app` đầu phiên (cùng quyền app); không đổi `pg_hba`.

- Lượt 1: máy tách đúng 11 chuyến như công cụ (cùng biến động từng loại), 2 lệnh chọn cột, 6 lệnh khóa tháng (3 tháng mở rồi khóa lại); 244 sổ, 0 sổ lỗi, 0 lỗi máy. Lượt 2 không ghi thêm.
- Số dư, tổng phụ phí, phiếu thu, điều chỉnh, khóa tháng trùng trước/sau; checker 9/9. Đã xóa DB thử.

## Bật máy (18:15)

- Chờ lượt máy đối soát 18:05 xong (18:15, `Result=success`). Lưu bản drop-in cũ, đo trước.
- `auto-sheet.conf`: `WEBDEBIT_AUTO_SHEET=text,trips,prices,road,ps,headers`, `daemon-reload`, restart API 18:15:21: unit active, `/healthz` 200.
- Lượt hộp việc đầu sau khởi động: `ready`, 244 sổ, 0 sổ lỗi, journal API không có lỗi. Không còn chuyến nào phải tách (công cụ đã làm hết lúc 18:00), nên số dư, tổng phụ phí, phiếu thu, điều chỉnh, khóa tháng và số khoản theo loại trùng trước/sau.
- Từ lượt runner giá kế tiếp, chuyến mới có cột tên rõ (`过磅`, `LOCAL CHARGE`...) và ô cộng đúng TOTAL − đơn giá được máy tách ngay sau khi ghi giá.

## Rollback

- Máy: bỏ `headers` khỏi `auto-sheet.conf`, `daemon-reload`, restart API.
- Khoản đã tách: mỗi chuyến có event `rewrite_trip_fees` kèm `before`; đổi lại loại trong khung chi tiết phụ phí, hoặc restore dump.
- Danh mục: loại chưa có khoản thì tắt bằng `set_fee_type_active`; release cũ chạy được với DB mới.

**Bằng chứng:** thư mục `backup-20261119-tach-phi-loai` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700): dump trước khi thử và trước khi nâng kèm sha256, SQL và script đã chạy, kết quả đếm và ghi, phép đo trước/sau, checker.
