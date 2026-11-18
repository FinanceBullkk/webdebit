# Triển khai: mở sổ lớn không JIT (18/11/2026)

**ĐÃ CHẠY trên `hao` lúc 08:55 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), spec [`mo-so-nhanh-03`](../../specs/mo-so-nhanh-03.md) và [runbook](../v7-deploy-runbook.md#mở-sổ-lớn-không-jit-mo-so-nhanh-03--nâng-db-đã-chạy-trên-hao-18112026). Không đổi quy tắc tiền nên không có quyết định mới.

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Phiên lưới an toàn giao việc 18/11/2026 (mục CÒN MỞ "Sổ 104 mở chậm"); triển khai tay theo `DEPLOY-CLAUDE-01` |
| PR / release | #464, merge `6b93a4e`; release tay `6b93a4e` thay cho `41b44c7` |
| CI | 17/17 check của #464 xanh trên head `7a832cc`, gồm `postgres-v7-backend` (`--migration-test`), `postgres-v7-luoi-an-toan`, grants, p0 |
| Migration | `2026-11-18-v7-mo-so-tat-jit.sql`, SHA-256 `57e24d56d422c3b565064ea6b9ab7c2b0aa91d4cd4bb3d10a1dbe39aba1d3aa6`, trùng bản trên `main` và bản đã thử |
| Ghi tiền | Không. Chỉ đổi cấu hình của một hàm đọc (`get_ledger`: `jit=off`) |

## Kết quả

Đo trên DB thật đúng như API gọi: mỗi lần một psql mới dưới `v7_app`, trong giao dịch chỉ đọc.

| Sổ | Trước (08:47) | Ngay sau khi API khởi động lại (08:56, hộp việc đang tính lại mọi sổ) | Lúc rảnh (08:57) |
| --- | ---: | ---: | ---: |
| 104 | 8.550 / 8.520 ms | 750 / 635 ms | 534 / 549 / 539 ms |
| 79 | 1.286 / 1.310 ms | 1.091 / 1.044 ms | 760 / 752 / 754 ms |
| 149 | 1.031 / 1.031 ms | 627 / 755 ms | 530 / 522 / 533 ms |

- Mỗi lần mở sổ 104, phần SQL nhanh khoảng 16 lần. Sáng nay, cũng lúc API vừa khởi động lại, sổ 104 mất 8,3 giây; nay dưới 1 giây.
- Lưới an toàn `--dry-run --full` (so `get_ledger` của cả 242 sổ, 8 câu SQL) chạy hết 33 giây và sạch. Sáng nay riêng phần chứa sổ 104 đã mất 11,7 giây.
- Phạm vi: trên bản sao ở PC chỉ 3 sổ đang chậm hơn 50 ms vì JIT (104, 79, 149). Các sổ khác có thể vượt ngưỡng khi dữ liệu lớn lên; cấu hình mới chặn trước cho mọi sổ.
- GET sổ trên trình duyệt chưa đo lại. Ngoài `get_ledger`, GET còn phần chiếu Sheet/PS (đo 13/11 ở sổ 79: khoảng 0,6 giây).

## Thử trên bản sao (08:36–08:39)

- Dump `webdebit_v7` (660 mục), khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC, `ANALYZE`.
- Migration hai lượt: 98 ms và 91 ms. Băm `get_ledger` 242/242 sổ trùng trước và sau, sau `RESET jit` và sau khi nâng lại.
- Dấu vân dữ liệu trùng (dấu vân của lưới an toàn, md5 nợ từng sổ từng tháng, số dòng mọi bảng). Catalog chỉ đổi cấu hình `get_ledger`; chủ và quyền giữ nguyên. Checker 9/9. Đã xóa DB thử.
- Mỗi sổ đo trong một phiên mới: sổ 104 từ 8.876 và 8.737 ms còn 431, 382 và 366 ms.

## DB thật, 08:55

- Không có kết nối nào khác vào `webdebit_v7`. Máy đối soát chạy lúc :05 nên không trùng.
- Backup toàn phần ngay trước khi áp; `pg_restore --list` đọc được (660 mục).
- Áp với `ON_ERROR_STOP`: 111 ms. Không cần cửa sổ dừng ghi vì chỉ đổi cấu hình của một hàm đọc.
- Dấu vân dữ liệu trùng; băm `get_ledger` 242/242 sổ trùng (0 sổ khác). Catalog sau bằng bản thử: chỉ `get_ledger` thêm `jit=off`. Checker 9/9.

## Release

- Release tay `6b93a4e` lúc 08:56 bằng đúng gói và script của `Deploy hao`: `/healthz` 200, unit active, `.release-sha` = `6b93a4e`. Script cảnh báo không dọn được vài release cũ có file của user khác (đã có từ trước).
- Lượt `Deploy hao` của `6b93a4e` (08:59) xanh, bỏ qua vì `hao` đã chạy đúng SHA đó.
- Journal API sau khởi động lại không có lỗi.
- Lưới an toàn `--dry-run`: `"ok": true`, không mục nào (so với lượt 08:47). Bản `--full` cũng sạch. Không cần `--accept`, vì dữ liệu không đổi.

## Rollback

`ALTER FUNCTION sokhach.get_ledger(bigint) RESET jit;` dưới `sokhach_owner` (đã thử trên bản sao: băm vẫn trùng). Release cũ chạy được với DB mới, release mới chạy được với DB cũ.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261118-mo-so-tat-jit/` trên `hao` (quyền 700). Gồm dump trước khi thử và trước khi nâng kèm sha256, SQL và script đã chạy, dấu vân, băm, catalog, checker và số đo.

## Còn mở

- `get_dashboard_debt` (Tổng quan, Việc cần làm, huy hiệu menu) cũng tốn thời gian chủ yếu cho JIT: trên bản sao ở PC 358 ms, tắt JIT còn 86 ms. Đã xử lý ở [HIEU-NANG-02](../../specs/hieu-nang-02.md), lên `hao` 10:19 cùng ngày ([nhật ký](2026-11-18-tong-quan-tat-jit.md)).
