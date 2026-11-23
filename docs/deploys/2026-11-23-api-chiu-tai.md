# Triển khai: API chịu tải và tin danh tính chặt hơn (audit API 23/11/2026, F1–F8, F11, F12)

Nguồn: `D:\webdebit\audits\2026-11-23-web-audit\api-findings.md` (ngoài repo). Mã đi qua `Deploy hao` khi merge; phần tay
trên `hao` chỉ là một drop-in giới hạn file descriptor ([`TU-LAM-01`](../decisions/tu-lam-01.md)).

| Mục | Nội dung |
| --- | --- |
| Code | `web/v7_ledger_api.py`, `v7_identity.py`, `v7_psql.py`, `v7_api_validate.py`, `v7_xlsx_writer.py`, `v7_book_export_rows.py` |
| SQL, DB | Không đổi schema hay hàm. Payload tới `psql` đi qua stdin (hằng dollar-quote) thay vì đối số `-v` |
| Ghi tiền | Không đổi quy tắc. Lệnh ghi nhận thêm 422 khi chữ tự do có ký tự điều khiển, 503 `DB_BUSY` khi 12 kết nối DB đều bận quá 10 giây (chưa chạy gì, gửi lại an toàn) |
| Tay trên `hao` | Drop-in `/etc/systemd/system/v7-ledger-api.service.d/limits.conf`: `LimitNOFILE=8192` |

## Đổi gì

- **F1** cổng HTTPS trực tiếp (8445): socket nghe không còn bọc TLS; mỗi kết nối bắt tay trong luồng xử lý, hạn 5 giây
  (`TailnetHTTPSServer`). Trước đây một kết nối TCP im làm treo cả cổng.
- **F2** thân trả lời (Excel, PDF, ảnh, JSON lớn) gửi từng lát 256 KiB, hạn 30 giây mỗi lát, trần tổng max(60 giây,
  cỡ / 32 KB/s). Lỗi sau khi đã gửi đầu trả lời thì đóng kết nối, không chèn JSON lỗi vào giữa file.
- **F3** tối đa 96 luồng xử lý mỗi cổng (hết chỗ thì kết nối chờ ở hàng đợi kernel); dòng đầu + header có hạn tuyệt đối
  10 giây; thân lệnh hạn theo cỡ (tối thiểu 16 KB/s); tối đa 12 tiến trình `psql` cùng lúc (`max_connections = 20`).
- **F4** header `Tailscale-User-Login` từ loopback chỉ được tin khi socket client thuộc uid 0 (`tailscaled`), tra
  `/proc/net/tcp*`. Đường riêng cho bot Zalo: uid khai trong `WEBDEBIT_READ_ONLY_PEER_UIDS`, chỉ GET. Bot chưa cài nên
  chưa khai uid nào ([ACCESS-01](../decisions/access-01.md), runbook mục ZALO-BOT-01).
- **F5** ký tự điều khiển C0/DEL trong lý do, ghi chú, tham chiếu bị từ chối 422; bản xuất cả sổ lọc mọi chữ qua
  `clean_text` (CR thành LF) nên không còn XML hỏng hay báo lệch giả.
- **F6** lỗi bất ngờ trả 500 `INTERNAL` và một dòng journal thay vì không trả lời. **F7** `/api/` chặn
  `Sec-Fetch-Site` khác `same-origin`/`none` (403 `CROSS_SITE`). **F8** dev actor chỉ bật bằng cờ, không đi cùng Serve.
- **F11** journal một dòng cho mỗi POST và mỗi trả lời không 2xx/304 (đường dẫn, mã, actor, ms; không query, không thân);
  lỗi `psql` lạ ghi SQLSTATE. **F12** payload không còn giới hạn 128 KiB của một đối số dòng lệnh.

## Trước khi merge (đã làm 23/11/2026)

- Kiểm trên `hao`: `tailscaled` chạy bằng root; socket client của nó tới `127.0.0.1:8780` hiện uid 0, ESTABLISHED, inode
  khác 0 trong `/proc/net/tcp`. Đọc `/proc/net/tcp` và `tcp6` được dưới `v7app` với `ProtectProc=invisible`, `ProcSubset=all`
  (khối hardening `50-hardening.conf`) bằng `systemd-run --uid=v7app`.
- Không công cụ nào khác trên `hao` gửi header danh tính tới 8780 (grep unit, script); bot Zalo chưa cài.
- Ghi danh sách drop-in trước khi thêm (`/tmp/v7-api-dropins-before-20261123.txt`, 15 file), tạo `limits.conf` mới (không
  ghi đè file nào), `daemon-reload`: `LimitNOFILESoft=8192`. Tiến trình đang chạy vẫn 1024 tới lượt restart của deploy.
- PostgreSQL 18.6 dùng một lần: payload 200 KB chứa `\!`, dấu huyền, `:'actor'`, `$$`, nháy đơn đi qua stdin về nguyên vẹn,
  không lệnh shell nào chạy; `\u0000` bị jsonb từ chối (SQLSTATE 22P05), nay validator chặn trước ở 422.

## Sau merge: kiểm

1. `Deploy hao` xanh; `cat /proc/<pid>/limits` của unit: `Max open files 8192`.
2. Mở một kết nối TCP im tới `:8445` rồi `curl https://<host>:8445/...` từ máy khác trong lúc đó: trả lời ngay.
3. Tải Excel cả sổ với `curl --limit-rate 200k` qua 8445: đủ byte bằng `Content-Length`.
4. Journal không có traceback; dòng `V7 API:` chỉ cho POST và mã không 2xx.

Gỡ: revert PR (deploy tự chạy); drop-in thì xóa `limits.conf`, `daemon-reload`, restart.
