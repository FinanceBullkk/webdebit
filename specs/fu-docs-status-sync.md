# Đồng bộ câu trạng thái trong ba tài liệu

Trạng thái: ĐÃ CHỐT giao việc. Claude điều phối ngày 17/10/2026 sau review chuỗi PR. Chỉ sửa câu trạng thái cho khớp sự thật đã ghi ở chỗ khác trong repo; không đổi quyết định, không thêm số liệu live.

## Vấn đề

Claude đối chiếu trên `main` tại `7af67c2`:

1. `docs/m1-deploy-rollback.md` dòng 3 ghi "Trạng thái: **ĐỀ XUẤT** … **Chưa deploy**, chưa chạm máy chủ…", trong khi mục bằng chứng cuối file (khoảng dòng 73) ghi đã triển khai live tại commit `c439d13…` (hồ sơ ngoài Git) và còn mục CÒN MỞ.
2. `specs/p0-write-path/07-identity-revision-implementation.md` khoảng dòng 23 ghi quy tắc trùng theo chuyến hay chuyến + loại phí và cách duyệt bảng nối opening ↔ mã chuyến vẫn **CÒN MỞ**, trong khi `docs/decisions.md` đã chốt DUP-01 (v1: mỗi `trip_key` một charge) và JOIN-01 (chính sách duyệt bảng nối) ngày 16/10/2026. Phần còn mở thật theo decisions.md: dấu "/" trong ô booking, booking bị sửa sau khi ghi, ngưỡng ngày cụ thể của JOIN-01, nâng khóa lên chuyến + loại phí khi có danh mục loại phí, bảng resolution production chưa triển khai.
3. `docs/decisions.md` dòng OPENING-FINAL ghi đổi tên trường sang `warehouse_in_date` và thông báo "chuyến cũ, nợ thuộc opening" là "ĐỀ XUẤT, chưa cài", trong khi fixture trên `main` (`cong-no-web-handoff/tools/pg_versioned_approval_fixture.sql`, đã merge qua PR #10) đã dùng `warehouse_in_date` và báo "chuyến cũ, nợ thuộc opening 13/10…", và spec 07 bảng "Quyết định áp dụng cho fixture" cũng mô tả vậy.

## Hành vi và bất biến

- (1) Đổi dòng trạng thái đầu file thành: ĐÃ TRIỂN KHAI live (viewer M1) tại commit `c439d13`, chi tiết/CÒN MỞ ở mục bằng chứng cuối file; phần gate/thứ tự/gói viết trước triển khai được đánh dấu là kế hoạch lúc đề xuất (lịch sử), không xóa nội dung. Không chép đường dẫn hồ sơ, tên máy hay số liệu mới ngoài những gì file đã có.
- (2) Tách câu: chính sách v1 ĐÃ CHỐT (DUP-01, JOIN-01, link `docs/decisions.md`) và fixture CI đã có `UNIQUE(posting.trip_key)`; liệt kê đúng các phần CÒN MỞ nêu trên. Không đổi bảng quyết định hay hành vi fixture mô tả trong spec.
- (3) Ghi đúng mốc: fixture CI đã cài `warehouse_in_date` và thông báo (PR #10); vẫn ĐÃ KIỂM CHỨNG chỉ ở mức fixture CI, chưa có app/DB production. Giữ câu "Ngày xe từ 14/10 vẫn không tự chứng minh…".
- Dùng nhãn trạng thái theo AGENTS.md (ĐỀ XUẤT, ĐÃ CHỐT, ĐÃ TRIỂN KHAI, ĐÃ KIỂM CHỨNG, CÒN MỞ). Không sửa câu khác, không format lại bảng.

## Tiêu chí nghiệm thu

- [ ] Ba chỗ trên khớp với nhau và với code fixture trên `main`; diff chỉ chạm câu trạng thái.
- [ ] `git diff --check` PASS; link tương đối trong câu sửa trỏ đúng file có trong repo.
- [ ] Không có Sheet ID, SSH, IP, số liệu khách mới trong diff.

## Phạm vi agent

- Agent: codex
- Review: sonnet medium
- Được sửa:
  - `docs/m1-deploy-rollback.md`
  - `specs/p0-write-path/07-identity-revision-implementation.md`
  - `docs/decisions.md`
- Ngân sách diff: 30 dòng
- Lệnh kiểm:
  - `git diff --check`
- Cấm:
  - Đổi quyết định, thêm quyết định mới, đổi nội dung kỹ thuật/fixture.
  - Sửa file ngoài danh sách; format lại bảng hay đoạn không liên quan.
  - Thêm số liệu live, Sheet ID, đường dẫn máy chủ, tên máy, SSH.
- Khi cần vượt phạm vi: dừng, nêu câu hỏi trong báo cáo cuối.

## Hoàn tác

Revert commit.

## Bằng chứng

Claude điều phối kiểm trong worktree sau sửa (reviewer Codex không đọc được file do lỗi sandbox):

- `docs/m1-deploy-rollback.md`: các tiêu đề là dòng 1 `# Gói deploy…`, 5 `## Gate và thứ tự`, 13 `## Gói runtime`, 35 `## Preflight chỉ đọc`, 50 `## Rollback`, 71 `## Giới hạn`. Dòng 73 (trong mục Giới hạn) bắt đầu "ĐÃ KIỂM CHỨNG: build/preflight bằng repo tạm…, sau đó triển khai live tại commit `c439d13…`" và có "CÒN MỞ: nghiệm thu đầy đủ liên kết nguồn/lịch sử…; rollback mã không hoàn tác ACL." Anchor `#giới-hạn` khớp tiêu đề dòng 71.
- `docs/decisions.md` trên `main`: DUP-01 "ĐÃ CHỐT chính sách. Fixture CI (PR #10) đã có `UNIQUE(posting.trip_key)`…; Có thể nâng lên khóa theo chuyến + loại phí khi danh mục loại phí được duyệt." JOIN-01 "ĐÃ CHỐT chính sách; chưa triển khai bảng resolution production. Ngưỡng ngày cụ thể, dấu `/` trong ô booking và xử lý booking sửa sau posting vẫn CÒN MỞ."
- Fixture `cong-no-web-handoff/tools/pg_versioned_approval_fixture.sql` trên `main` dòng 340–343 đọc `warehouse_in_date` và báo "chuyến cũ, nợ thuộc opening 13/10: ngày xe nhập kho trước 2026-10-14".

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
