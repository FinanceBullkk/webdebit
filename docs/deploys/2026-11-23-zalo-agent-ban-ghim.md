# Triển khai tay: agent Zalo chạy từ bản ghim theo SHA (ZALO-AGENT-01, 23/11/2026)

**ĐÃ THỬ trên task thử ở máy có Zalo (`msi`) ngày 23/11/2026; task thật `ZaloAgent` CHƯA chuyển** (chờ phiên điều phối nhắn "đã merge, chuyển đi"). Phần "Chuyển task thật" bên dưới ghi sau khi chuyển.

Bối cảnh: rà kỹ thuật Zalo/WeChat 23/11/2026 (chỉ đọc) thấy agent chạy thẳng từ checkout dev. Mục đích: mọi PR agent của đợt (đọc tiền ảnh, OCR engine, canh WeChat) triển khai bằng một lệnh, lùi bằng một lệnh, và `agent_version` nói đúng mã đang chạy.

| Mục | Nội dung |
| --- | --- |
| Code | `cong-no-web-handoff/tools/zalo_agent_release.ps1` (script mới); không sửa mã `zalo_agent/*.py` |
| SQL, DB | Không |
| Ghi tiền | Không |
| Đụng task thật | Chưa. Chỉ lệnh `Status` (chỉ đọc) chạy trên `ZaloAgent` |

## Vì sao

Task `ZaloAgent` chạy `pythonw -X utf8 -I "D:\webdebit\repo\cong-no-web-handoff\tools\zalo_agent" run …`, thư mục làm việc `D:\webdebit\repo`. Kéo `main` hay đổi nhánh ở checkout đó thì agent đang chạy nạp lười mã mới lẫn mã cũ (import muộn, tiến trình con `ocr_child.py` và tiến trình WeChat sinh lại), và lần chạy kế tiếp (lặp 15 phút, đăng nhập, tự chạy lại sau lỗi) chạy nhầm nhánh.

Đã thấy đúng chuyện này lúc đo: `status.json` (máy và `hao`) báo `agent_version` của một commit cũ trong khi HEAD của checkout dev đã là commit mới hơn.

## Cách làm

- Bản ghim là **một git repo riêng** ở `D:\zalo-agent\releases\<sha12>`, dựng bằng `git init` + `git fetch --depth 1 <checkout dev> <sha>` + `checkout --detach`, nên không dùng chung object hay worktree với checkout dev (xóa, gc, đổi nhánh ở đó không ảnh hưởng). Đầy đủ cây (không cắt thưa): agent còn nạp `tools/zalo_web_bundle.py` ngoài gói.
- `agent_version` đúng SHA mà **không sửa mã agent**: `status.agent_version` chạy `git -C REPO rev-parse --short=12 HEAD` với `REPO = parents[3]` của `zalo_agent/__main__.py`, tức gốc của bản ghim.
- Chỉ nhận SHA nằm trong `origin/main` (trừ `-AllowNonMain`).
- Trỏ task: chỉ đổi Action (đường dẫn gói trong tham số và thư mục làm việc); Python, mọi tham số khác, trigger, cài đặt pin, principal giữ nguyên. Script so XML trước/sau ngoài Action; lệch thì khôi phục XML cũ và dừng. XML cũ lưu ở `releases\task-<tên>-<giờ>.xml`.
- Trước khi đụng task: `python -I <gói> run --help` trong bản ghim (nạp mọi module mức đầu, bắt thiếu tệp hay lỗi cú pháp).
- Thứ tự khởi động lại: đổi Action → `Stop-ScheduledTask` → **chờ tới khi không còn tiến trình `zalo_agent … run` của đúng thư mục dữ liệu** (quá 30 giây thì giết; khóa `agent.lock` nhả khi tiến trình chết) → `Start-ScheduledTask`. Lý do: `schtasks /End` trả về khi tiến trình cũ chưa chết, `/Run` ngay sau đó gặp khóa còn giữ, in "đang có một agent khác chạy" rồi thoát mã 0 và không agent nào chạy tới lượt lặp 15 phút (gặp 22/11/2026). Đổi Action trước `Stop` để lượt lặp 15 phút không thể bật lại đường dẫn cũ giữa chừng. Tiến trình con của bản cũ (`ocr_child.py`, `wechat_export.py`) được chờ tối đa 30 giây trước `Start` để khỏi chồng hai OCR; còn sau đó thì chỉ báo, không giết.
- Kiểm: có tiến trình chạy từ bản ghim; `D:\zalo-agent\state\status.json` có `agent_version` = SHA và `at` sau lúc bấm Start; `hao:/srv/v7/zalo-agent/status.json` cũng vậy (đọc qua `ssh hao cat`). Agent chỉ ghi `status.json` sau khi xong cả lượt đầu, mà lượt đầu có thể dựng lại đầy đủ và đẩy cả gói, nên: hết `-TimeoutSec` (mặc định 240 giây) mà tiến trình còn sống và vẫn ghi file trong `logs`, `state`, `bundle`, `tmp` ở 60 giây gần nhất thì chờ tiếp, tối đa `-MaxWaitSec` (mặc định 1200 giây); tiến trình thoát hoặc im lặng thì hỏng ngay. Tăng `-MaxWaitSec` khi biết lượt đầu sẽ dựng lại cả gói trên đường truyền chậm. Máy lỗi thì **tự lùi** về bản trước, mã thoát 1; chỉ hao chưa thấy thì mã thoát 3, không tự lùi.
- Lỗi sau khi đã đổi task hoặc đã dừng agent cũ (kể cả khi chính lần lùi hỏng): script cố đưa task về trạng thái có agent chạy (trỏ về Action cũ, `Start` nếu không còn agent) và, nếu cũng hỏng, in "LÙI CŨNG HỎNG" kèm lệnh cứu tay `Register-ScheduledTask -Xml <XML cũ> -Force; Start-ScheduledTask`.
- Lùi: `Rollback` (bản trước theo `releases\history.jsonl`; gọi liên tiếp thì đi qua lại giữa hai bản) hoặc `Rollback -Sha <tiền tố ≥ 7 ký tự>`; giữ `-Keep` bản (mặc định 3) cộng bản đang chạy và bản để lùi. `Status` chỉ đọc.
- Phải chạy trong PowerShell **không nâng quyền**: thư mục dựng trong phiên nâng quyền thuộc nhóm Administrators, agent (không nâng quyền) gặp git "dubious ownership" và `agent_version` thành `unknown`. Script từ chối `Deploy`/`Rollback` trong phiên nâng quyền (trừ `-AllowElevated`).

## Lệnh

```powershell
# triển khai SHA mới nhất của main (hoặc -Sha <sha>); PowerShell thường, không nâng quyền
powershell -NoProfile -ExecutionPolicy Bypass -File D:\webdebit\repo\cong-no-web-handoff\tools\zalo_agent_release.ps1 Deploy
# lùi một bản
powershell -NoProfile -ExecutionPolicy Bypass -File D:\webdebit\repo\cong-no-web-handoff\tools\zalo_agent_release.ps1 Rollback
# xem tình hình (không đổi gì)
powershell -NoProfile -ExecutionPolicy Bypass -File D:\webdebit\repo\cong-no-web-handoff\tools\zalo_agent_release.ps1 Status
```

Lệnh `Deploy` chạy từ checkout `main` hoặc worktree đều được: script chỉ `git fetch origin main` (không đổi nhánh hay cây làm việc). Mã thoát: 0 xong; 1 hỏng ở máy (đã tự lùi); 3 máy chạy bản mới nhưng hao chưa thấy.

## Kiểm trên task thử (không đụng task thật)

Task thử `ZaloAgentTest` đăng ký từ XML của `ZaloAgent` (cùng trigger, cài đặt pin, principal), `--root` riêng ở thư mục thử, `--target`/`--status-target` trỏ host không tồn tại (không đẩy gì lên `hao`; `--dry-run` không dùng được vì không ghi `status.json`). Đã xóa task thử và nội dung thư mục thử sau khi kiểm.

| Phép thử | Kết quả |
| --- | --- |
| Deploy `main` khi agent cũ (chạy từ checkout dev) đang chạy | Tiến trình cũ dừng, tiến trình mới chạy từ bản ghim, `status.json` báo đúng SHA, mã thoát 0 |
| Deploy SHA cũ hơn 6 commit rồi `Rollback` | Mỗi lần `agent_version` đổi đúng SHA; `Rollback` đi đúng bản trước |
| XML task ngoài Action sau mỗi lần đổi | Không đổi (script tự so; không lần nào phải khôi phục) |
| Ép kiểm máy hỏng (`-TimeoutSec 1`) | Tự lùi về bản trước; lần thử đầu lộ lỗi: đặt giờ thư mục bản ghim khi tiến trình đang giữ nó làm cwd bị Windows từ chối và làm đứt đường lùi — đã sửa thành không bắt buộc, thử lại thì lùi đạt |
| Sau review (23/11): chờ dấu hiệu sống, `Rollback -Sha` tiền tố 7 ký tự, tiền tố sai | Thấy dòng "agent còn ghi file: chờ tiếp"; tiền tố 7 ký tự tìm đúng bản; tiền tố 3 ký tự bị từ chối |
| Sau review: ép hỏng `-MaxWaitSec 1` (cả lần deploy lẫn lần tự lùi) | Deploy hỏng → tự lùi về bản trước; lần lùi cũng "hỏng" thì dừng với mã 1, task vẫn có agent đang chạy (nhánh `Restore-Task` lúc agent còn sống). Nhánh khởi động lại khi không còn agent và nhánh in lệnh cứu tay CHƯA thử được trực tiếp |
| `Prune -Keep 1` | Giữ bản đang chạy và bản để lùi, xóa bản còn lại |
| `Status` trên task thật (chỉ đọc) | Đọc được task, tiến trình, `status.json` máy và `hao`; báo lệch giữa mã ở đường dẫn task và bản agent đang chạy |
| Bẫy `End` rồi `Run` ngay | Một lượt thử không tái hiện (hai lệnh liền nhau vẫn cho một tiến trình chạy); bẫy phụ thuộc thời điểm tiến trình chết nên script chờ theo điều kiện chứ không theo giờ |

## Chuyển task thật

CHƯA làm. Sau khi phiên điều phối nhắn "đã merge, chuyển đi": chạy `Deploy` trên task `ZaloAgent`, ghi vào đây SHA đang chạy, kết quả kiểm máy và `hao`, và cách lùi.

## CÒN MỞ

- Chưa thử tới tận lúc agent thật chuyển bản (xem mục trên).
- Chưa có bước dọn `D:\zalo-agent-test` (thư mục gốc rỗng còn lại: hệ thống chặn xóa chính thư mục đó, nội dung đã xóa).

## Rollback của việc này

`Rollback` đưa task về bản trước; bản đầu tiên (trước khi có bản ghim) là checkout dev `D:\webdebit\repo`, nên một lần lùi sau lần `Deploy` đầu tiên là trở về cách chạy cũ. Muốn bỏ hẳn bản ghim: sửa Action của task `ZaloAgent` về đường dẫn cũ (XML cũ lưu ở `releases\task-ZaloAgent-<giờ>.xml`, nhập lại bằng `Register-ScheduledTask -Xml`). Thư mục `D:\zalo-agent\releases` xóa được khi task không còn trỏ vào đó.
