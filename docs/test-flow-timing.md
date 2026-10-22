# Thời gian bộ kiểm và đề xuất chỉnh flow

Đo ngày 22/10/2026. Phần đo là số thật; phần "Đề xuất" là **ĐỀ XUẤT**, chưa phải ĐÃ CHỐT. Không đổi code nghiệp vụ, không chạy gì trên `hao`.

## 1. Đo cục bộ (máy dev, Docker Desktop 4 CPU / 6 GB, chạy tuần tự)

| Lệnh | Cục bộ | CI (trung vị) | Kết quả |
|---|---|---|---|
| `unittest discover` (`cong-no-web-handoff`) | 59 giây | 35 giây | xanh |
| `test_pg_v7_backend.py` | 921 giây | 252 giây | xanh (có 2 ca skipped; cờ `--strict` sẽ báo đỏ vì skipped, CI không bật cờ này) |
| `test_pg_v7_p0_harness.py --strict` | 447 giây | 128 giây | xanh |
| `test_pg_v7_grants.py --strict` | 255 giây | 72 giây | xanh |
| `test_pg_v7_direct.py --strict` | 43 giây | 13 giây | xanh |
| `rehearse_v7_deploy.py --strict` | 37 giây | 9 giây | xanh |
| `test_pg_versioned_approval.py` | 466 giây | 134 giây | xanh |
| `test_pg_ledger_schema.py` | 31 giây | 28 giây (2 bước) | xanh |
| `test_pg_m1_queries.py` | 25 giây | 16 giây | xanh |
| `npm ci` + `npm run check` | 7 + 82 giây | 43 giây (Ubuntu) / 61 giây (Windows) | xanh |

- Bộ V7 (backend + p0 + grants + direct + rehearse) cộng lại khoảng **28 phút** cục bộ, khoảng **8 phút** trên CI. Cục bộ chậm khoảng 3,5 lần ở mọi bộ dùng Postgres.
- Dựng database rất rẻ: chạy container 0,9 giây, chờ sẵn sàng 1,9 giây, tạo DB 0,6 giây, nạp schema 0,9 giây, nạp hàm 0,7 giây, `CREATE DATABASE … TEMPLATE` 0,9 giây (tổng khoảng 7 giây gồm cả xóa). Thời gian nằm ở các kịch bản, không ở bước dựng.
- Backend V7 theo ca (tổng ca 872 giây trên 921 giây): `csm_migration` 232, `snapshots` 71, `golden` 60, `dedup` 56, `model` 32, `cutover_gate` 30, `import_behavior` 22, `trip_review` 20. Riêng `csm_migration` chiếm 25%.
- Lưu ý nhiễu: một container V7 của phiên khác (PR #66) chạy chung máy trong lúc đo backend và khoảng 10 phút đầu của lần chạy này, nên số cục bộ có thể cao hơn máy rảnh.

## 2. Đo CI (20 lượt gần nhất của `Tests`, qua `gh api`)

Thời gian mỗi job (nhỏ nhất / trung vị / lớn nhất, giây):

| Job | min | trung vị | max | Ghi chú |
|---|---|---|---|---|
| `postgres-v7-backend` | 347 | 480 | 530 | backend 252, p0 128, grants 72, direct 13, rehearse 9 |
| `javascript` Windows | 199 | 292 | 626 | `playwright install` 192 (max 255), `npm ci` max 307, check 61 |
| `pg18-versioned-approval-fixture` | 106 | 140 | 153 | |
| `javascript` Ubuntu | 67 | 75 | 85 | playwright install 21, check 43 |
| `postgres-ledger` | 32 | 37 | 45 | |
| `python` 3.12 / 3.13 | 31–33 | 35 / 36 | 38 / 49 | |
| `postgres-m1-history-queries` | 22 | 24 | 33 | |

- Thời gian chờ của một lượt = job dài nhất: khoảng 8 phút (`postgres-v7-backend`), lúc xấu 10 phút. Tổng thời gian runner mỗi lượt khoảng 19 phút.
- `test.yml` **không có `paths`**: cả 8 job chạy mọi PR, kể cả PR chỉ đổi tài liệu.

## 3. Đánh giá từng bộ

Phân tích 200 lượt `Tests` gần nhất (từ 15/10), 55 lượt đỏ.

| Bộ | Bắt lỗi gì | Lần gần nhất bắt lỗi thật | Còn cần? |
|---|---|---|---|
| `postgres-v7-backend` | hợp đồng V7: hàm ghi sổ, khóa tháng, CSM, dedup, migration | 22/10 (`codex/v7-csm-code`, 2 lần đỏ ở backend contract); 21/10 đỏ ở grants (`claude/v7-m2-11-dedup`) | **Cần**, đang là bộ bắt lỗi thật nhiều nhất hiện nay |
| `javascript` (check: ruff, luật nghiệp vụ, eslint, unittest, JS, browser, viewer) | lint và luật nghiệp vụ code hóa | 22/10 (lint, Windows), 21/10 (nhiều lần) | **Cần** |
| `python` 3.12/3.13 | unittest không DB | trùng với `npm run check` (đã gồm unittest 3.13) | Bản 3.13 gần như trùng `javascript`; 3.12 là chỗ duy nhất kiểm bản cũ |
| `postgres-ledger` | schema sổ cũ trước V7, migration F2/F3 | thật: 15–16/10; các lần đỏ 18–19/10 là lỗi môi trường (runner `hao`, Postgres chưa sẵn sàng), đã sửa ở `b504cab` 20/10 | Ít cần: file kiểm không đổi từ 16/10 |
| `postgres-m1-history-queries` | truy vấn HistoryDB M1 | thật: 16/10 | Ít cần: không đổi từ 16/10 |
| `pg18-versioned-approval-fixture` | fixture duyệt có phiên bản (maker–checker, đã bị V6 thay) | thật: 16/10; sửa fixture lần cuối 18/10 | Ít cần: kiểm chính sách đã bỏ, chạy lâu nhất trong ba job cũ (140 giây) |

Ba job sổ cũ: từ khi chuyển sang runner của GitHub (21/10) chưa đỏ lần nào. Từ 17/10 chỉ có 3 commit chạm vào file của chúng (một sửa fixture, một sửa chờ khởi động, một sửa ruff). Chưa có bằng chứng chúng đang bảo vệ code V7 (V7 dùng lược đồ `sokhach`, không dùng các schema này). **Chưa đo** hết: chưa kiểm xem có code V7 nào import `ledger_db.py`/`pg_*.sql` cũ; nếu có thì `paths` phải gồm các file đó.

## 4. Đề xuất (ĐỀ XUẤT, xếp theo tiết kiệm / rủi ro)

1. **Vòng sửa của Codex chỉ chạy lệnh đang đỏ** (`codex-check-loop.ps1`: vòng ≥ 2 chỉ chạy lại lệnh vòng trước đỏ; chạy đủ bộ một lần ở vòng cuối). Tiết kiệm lớn nhất: cục bộ mỗi vòng đủ bộ khoảng 28 phút, 4 vòng ≈ 1,9 giờ; nếu chỉ chạy lệnh đỏ thường là vài phút. Rủi ro thấp nếu giữ lần chạy sạch đủ bộ trước merge.
2. **Phạm vi file Codex phải gồm cả test liên quan** (trong spec "Phạm vi agent": file hàm SQL cộng test tương ứng). Tránh vòng sửa đỏ vì Codex không được sửa test. Không tốn thời gian chạy, rủi ro thấp.
3. **Tách `postgres-v7-backend` thành các job song song** (backend / p0 / grants+direct+rehearse): CI chờ 480 → khoảng 250 giây, tiết kiệm khoảng 4 phút mỗi lượt. Không mất độ chắc, tổng phút runner không đổi.
4. **Lọc job theo file đổi**: PR chỉ đổi `docs/**`/`*.md` bỏ qua các job Postgres; ba job sổ cũ chỉ chạy khi đổi `tools/pg_*.sql`, `ledger_db.py`, file kiểm của chúng hoặc `test.yml`. Tiết kiệm khoảng 3,5 phút runner mỗi lượt cho ba job cũ, thêm khoảng 14 phút cho PR tài liệu; thời gian chờ không đổi (job dài nhất vẫn là V7). Rủi ro: nếu bảo vệ nhánh bắt buộc job nào đó thì job bị bỏ qua sẽ treo; dùng lọc ở mức bước (`if`) hoặc job tổng hợp. Chưa kiểm cấu hình bảo vệ nhánh.
5. **Cache trình duyệt Playwright trên Windows** (192 giây trong job `javascript`): tiết kiệm khoảng 3 phút cho job đó, chủ yếu giảm biến động (max 626 giây). Rủi ro thấp.
6. **Xem lại `csm_migration`** (232 giây, 25% backend): tìm lý do chậm (nhiều lần nạp, khóa, sleep?). Chưa rõ tiết kiệm bao nhiêu.
7. **Cân nhắc nghỉ hưu ba job sổ cũ** hoặc chỉ chạy theo lịch/`workflow_dispatch`: cần người dùng quyết vì xóa bằng chứng cho schema cũ.
8. **Không nên**: container Postgres chạy sẵn + `TEMPLATE` (dựng DB chỉ ~4 giây, không đáng); bỏ lần chạy đủ bộ trước merge.

## 5. Chưa đo được

- Máy rảnh hoàn toàn (số cục bộ có nhiễu từ phiên khác).
- Chạy song song các bộ V7 cục bộ (4 CPU / 6 GB có đủ không; mỗi bộ có container riêng).
- Vì sao cục bộ chậm 3,5 lần so với CI (Docker Desktop trên Windows, I/O volume, hay CPU).
- Thời gian từng ca của p0, grants, versioned (chỉ có theo ca cho backend).
- Có code V7 phụ thuộc file của ba job sổ cũ hay không.
- Cấu hình bảo vệ nhánh `main` (job nào bắt buộc).
- Lượt chạy `windows-latest` trước 21/10 không so sánh được (runner khác).
