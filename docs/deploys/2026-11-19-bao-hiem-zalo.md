# Triển khai tay: đường đẩy giấy bảo hiểm Zalo lên `hao` (19/11/2026)

**ĐÃ CHẠY trên `hao` và máy có Zalo ngày 19/11/2026.** Cổng B của [`BAO-HIEM-ZALO-01`](../decisions/bao-hiem-zalo-01.md); người dùng bấm "Install Gate B" trong chat. Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và mẫu G5 của [Group Zalo trên web](../../specs/v7-zalo-group-web.md#g5-đẩy-gói-lên-hao).

| Mục | Nội dung |
| --- | --- |
| Phía web | FinanceBullkk/webdebit#531 (PR-1 chỉ đọc), release `ad35c6b`, `Deploy hao` xanh trước đợt này |
| Phía máy Zalo | repo `zalo-audit-viewer`, nhánh `claude/bao-hiem-web` (`b909a2c`, `3d79d93`, `f25f077`), worktree `D:\zalo-audit-viewer-wt\bao-hiem-web`; chưa gộp vào `main` của repo đó |
| SQL, DB | Không. Không đổi bảng, hàm, quyền DB hay dữ liệu tiền |
| Ghi tiền | Không. Giấy chỉ hiện và mở PDF |

## Trên `hao`

- `install -d -o aohanh -g v7app -m 2750 /srv/v7/insurance`: chủ là tài khoản ssh đẩy, nhóm `v7app` (user của API) chỉ đọc, setgid để file mới tự thuộc nhóm `v7app`.
- Không thêm drop-in: API đọc đường mặc định `WEBDEBIT_INSURANCE_SNAPSHOT_PATH=/srv/v7/insurance/insurance-web.json`, PDF ở `pdf/` cạnh đó. Không restart API.

## Lượt đẩy đầu và lỗi quyền đã sửa

- Lượt tay đầu tiên gửi 16 dòng và 16 PDF.
- Phát hiện: dòng cuối script phía đích chạy `chmod -R` trên thư mục. `aohanh` không thuộc nhóm `v7app`, nên kernel xóa bit setgid của thư mục; từ lượt sau file mới sẽ thuộc nhóm `aohanh` và API không đọc được.
- Sửa ở `f25f077`: không bao giờ `chmod` thư mục, chỉ `chmod 0640` từng file vừa đến trước khi `mv`. Trả setgid và nhóm cho `/srv/v7/insurance` bằng `sudo`.
- Thử bản sửa ở thư mục tạm `/srv/v7/insurance-test` cùng cách dựng: hai lượt, mọi file nhóm `v7app` quyền 0640, gốc giữ setgid, lượt hai không gửi gì. Đã xóa thư mục tạm.
- Cùng lỗi đang có ở `/srv/v7/zalo-bundle` của G5 (file nhóm `aohanh`, `v7app` không đọc được). Ngoài phạm vi đợt này, CÒN MỞ.

## Trên máy có Zalo

- Task Scheduler `ZaloInsurancePush`, 15 phút một lần, cùng tài khoản chạy với `WebdebitZaloSync`, `pythonw -X utf8 insurance_push.py --target hao:/srv/v7/insurance`, đọc `insurance-snapshot.json` và kho PDF của thư mục live `live-sync-20261030`, chạy code từ worktree nhánh `claude/bao-hiem-web`. Không chạy chồng (`IgnoreNew`), giới hạn 10 phút.
- Lượt đầu của task: thoát 0, "target already current".
- Log `logs/insurance-push.log` trong worktree, chỉ số đếm.

## Kiểm

- `insurance-web.json` trên `hao`: 16 dòng, `row_count` 16, hash tính lại trên các dòng khớp `sha256` của file; chỉ 13 trường của hợp đồng.
- Không có tên, mã số thuế, số vận đơn, tàu, seal, tên file hay `sent_at` trên `hao`: dò 83 giá trị riêng tư của file gốc trong file trên `hao`, 0 lần có.
- `GET /api/v7/insurance/cert/<sha256>` qua Tailscale: 200 `application/pdf`, PDF tải về băm đúng `sha256`. Sha lạ: 404.
- `get_ledger` và Việc cần làm (sau lượt nền đọc đủ 244/244 sổ): 16 giấy chia đủ: sổ 107 có 5 cần xem và 6 `DONE` (1 theo booking, 5 theo container); sổ 149 có 3 cần xem; Việc cần làm có 2 `NO_BOOKING`. Khớp kết quả P0 sau ba điều chỉnh.

## Rollback

- Máy có Zalo: `Unregister-ScheduledTask ZaloInsurancePush`.
- `hao`: `rm -rf /srv/v7/insurance`. API thấy thiếu file thì `insurance: {unavailable: true}`, sổ vẫn mở.

## CÒN MỞ

- Gộp nhánh `claude/bao-hiem-web` vào `main` của `zalo-audit-viewer` rồi cho task chạy từ thư mục live; hiện task phụ thuộc worktree.
- Quyền `/srv/v7/zalo-bundle` của G5 (xem trên).
- Cổng D: người dùng tự đi hết luồng sau khi có giao diện (PR-2).
