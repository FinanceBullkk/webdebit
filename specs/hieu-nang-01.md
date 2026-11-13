# Web nhanh hơn khi dùng hằng ngày: giữ kết quả đọc nặng theo dấu dữ liệu, tính song song sổ vừa ghi (HIEU-NANG-01)

Trạng thái: ĐÃ CHỐT theo yêu cầu người dùng 13/11/2026 ("giờ đến giai đoạn dùng full trên web rồi, cần optimize performance"); cách làm do Claude chọn theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md). Phạm vi: tầng đọc của API (GET) và hộp thư Việc cần làm; không đổi luật tiền, không đổi thân hàm SQL có sẵn, không đổi giao diện.

Tiếp [MO-SO-NHANH-01](mo-so-nhanh-01.md) (ETag/gzip, đọc sổ song song với tải JS) và [MO-SO-NHANH-02](mo-so-nhanh-02.md) (Lịch sử nạp riêng). Bước 3 của MO-SO-NHANH ("cache `get_ledger` theo `version`") làm ở đây, mở rộng sang Tổng quan.

## Người dùng và luồng

Người nhập và chủ nghiệp vụ mở Tổng quan, Việc cần làm, Sổ khách nhiều lần trong ngày; mỗi trang tự đọc lại mỗi 60 giây, thanh menu đọc lại hộp thư mỗi 120 giây để đếm huy hiệu. Ghi thì thưa: 3 ngày gần nhất trên `hao` mỗi giờ 1–36 sự kiện, phần lớn của máy theo Sheet. Tức là gần như mọi lượt đọc trả đúng kết quả của lượt đọc trước, nhưng server tính lại từ đầu mỗi lần.

## Số đo trước khi làm

`hao` 13/11/2026, bản `61cd713`. Trình duyệt: `fetch` tuần tự từ máy làm việc qua Tailscale. Server: script chỉ đọc `sudo -u v7app python3 -B -I -` (đo `runner.run`, từng phép chiếu) và `psql` trong giao dịch `READ ONLY` (auto_explain).

| Đọc | Trình duyệt | SQL ở server | Ghi chú |
| --- | ---: | ---: | --- |
| `GET /api/v7/dashboard/debt` (Tổng quan, Việc cần làm, menu) | 830 ms | `get_dashboard_debt` 795–801 ms | Tổng quan gọi 2 lần lúc mở (trang + menu) |
| `GET /api/v7/dashboard` | 190–440 ms | `get_dashboard` 167–169 ms | cũng 2 lần |
| `GET /api/v7/inbox` sau khi có lệnh ghi | 3.605–3.913 ms | — | tính lại tuần tự tới 5 sổ "bẩn", mỗi sổ `get_ledger` + 6 phép chiếu |
| `GET /api/v7/inbox` không có sổ bẩn | 25–49 ms | — | |
| `GET /api/v7/ledger?customer=79` (sổ lớn nhất) | 1.804–2.753 ms | `get_ledger` 1.266 ms, chiếu 586–597 ms | 593 KB |
| `GET /api/v7/ledger?customer=14` | 420 ms | 231 ms, chiếu 140–164 ms | |
| `GET /api/v7/ledger?customer=176` (sổ thường) | 243–570 ms | 93 ms, chiếu 95–107 ms | 570 ms khi mở trang cùng lúc 5 lượt đọc khác |
| `GET /api/v7/sheet/doi-chieu?customer=79` | 1.852 ms | `statement` 1.383–1.395 ms | phần lớn là `get_ledger` |
| `list_customers` | 50–100 ms | 19–20 ms | |

## Đầu ra

1. **Hàm SQL `sokhach.get_read_stamp()`**: trả `{"as_of": "YYYY-MM-DD" (giờ VN), "stamp": "<md5>"}`. `stamp` là md5 của `(tên bảng, số dòng, tổng xmin)` của **mọi** bảng trong schema `sokhach` (lấy danh sách bảng từ `pg_class` lúc gọi, bảng mới tự vào). Mọi INSERT, UPDATE, DELETE đã commit ở bất kỳ bảng nào đều đổi `stamp` (UPDATE tạo bản dòng mới với xmin mới; DELETE đổi số dòng); khóa dòng (`FOR UPDATE`) và đọc không đổi. Đo trên `hao`: 29–42 ms trong DB.
2. **Bộ nhớ đọc theo dấu (`web/v7_read_cache.py`)**: cho bốn hàm đọc nặng `get_ledger`, `get_dashboard`, `get_dashboard_debt`, `get_receivables_matrix`, ở đường GET: mỗi lượt đọc lấy dấu **mới** (một lần psql), khóa = `(as_of, stamp, hàm, tham số)`; có thì trả bản giữ, chưa có thì chạy hàm như nay rồi giữ. Hai lượt cùng khóa đến cùng lúc chỉ chạy hàm một lần. Giữ chữ JSON (không giữ dict), mỗi lượt trả một bản `json.loads` mới. Giới hạn 96 MB; đổi dấu thì bỏ hết bản của dấu cũ.
3. **Đối chiếu ở Việc cần làm** (`GET /api/v7/sheet/doi-chieu`) đọc `get_ledger` qua cùng bộ nhớ.
4. **Hộp thư**: các sổ vừa ghi (tối đa 5) tính lại **song song** thay vì lần lượt; hai lượt GET cùng lúc không tính trùng (lượt sau chờ lượt trước rồi dùng kết quả).

Dự kiến (khi không có lệnh ghi giữa hai lượt đọc): `dashboard/debt` ~800 → ~60 ms, `dashboard` ~170 → ~60 ms, sổ 79 ~1,8 → ~0,7 giây (còn phần chiếu Sheet), đối chiếu sổ 79 ~1,4 → ~0,2 giây, hộp thư sau lệnh ghi ~3,6 → ~1 giây. Lượt đọc đầu tiên sau một lệnh ghi chậm hơn hôm nay ~45 ms (thêm lần lấy dấu).

## Đối chiếu dữ liệu và code hiện có

- `get_ledger`, `get_dashboard`, `get_dashboard_debt`, `get_receivables_matrix` chỉ đọc bảng/view trong `sokhach` (search_path `pg_catalog, sokhach, pg_temp`) và chỉ phụ thuộc thời gian qua **ngày/tháng giờ VN** (`d`, `m`, `clock_timestamp()` lấy tháng trong `editable`). Kiểm trên `hao` 13/11/2026: không view nào trong `sokhach` gọi `now()`/`clock_timestamp()`, không có bảng phân vùng, materialized view hay foreign table. Kết quả không phụ thuộc người đọc: `_actor()` chỉ đòi có tên người làm.
- Không phải mọi lệnh ghi đều tăng `customer.version` (loại phí `_change_fee_type`, `create_book_from_sheet`, `link_zalo`, `record_mark`, `record_reminder`… không qua `_begin_command`), nên dấu không dựa vào `version` mà vào mọi bảng.
- WAL (`pg_current_wal_lsn`) không dùng được: đo 13/11 nó nhích cả khi không lệnh ghi nào (cluster có DB khác).
- Runner (`web/v7_psql.py`) chạy mỗi hàm một lần psql trong `BEGIN … COMMIT`; thêm `run_text()` trả chữ JSON thô để bộ nhớ khỏi `dumps` lại.
- `GET /api/v7/ledger` vẫn chạy `ledger_projections` (chiếu Sheet/PS) mỗi lượt như nay: phụ thuộc file bản chụp Sheet, không giữ ở bước này.
- Hộp thư nền (`Inbox.refresh_all`), máy theo Sheet, mọi lệnh ghi và đường POST **không** đi qua bộ nhớ: máy đọc `version` ngay sau khi ghi, phải luôn đọc DB.

## Nguồn quyết định

- Không đụng quyết định nghiệp vụ nào trong [`docs/decisions.md`](../docs/decisions.md). Số dư vẫn đọc từ server, không giữ JSON ở trình duyệt (`no-store` như MO-SO-NHANH-01).
- Migration chỉ thêm một hàm đọc; tự triển khai theo [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md).

## Hành vi và bất biến

- **Đọc ngay sau ghi thấy bản mới**: lượt GET đến sau khi lệnh ghi trả về luôn lấy dấu mới trong một giao dịch mới, nên dấu khác và đọc lại DB. Không dùng chung lần lấy dấu giữa các lượt.
- Dấu lấy **trước** khi đọc dữ liệu: bản giữ có thể mới hơn dấu của nó (lệnh ghi xen giữa), không bao giờ cũ hơn; lượt sau có dấu mới thì đọc lại.
- Đổi ngày VN là đổi khóa (kết quả phụ thuộc ngày/tháng).
- DB chưa có hàm dấu, hàm dấu lỗi hoặc trả sai dạng: đọc thẳng DB như hôm nay, không lỗi cho người dùng (release mới chạy được với DB cũ).
- Lỗi của hàm đọc (ví dụ `CUSTOMER_NOT_FOUND`) không được giữ; mọi lượt đang chờ cùng khóa nhận đúng lỗi đó.
- Bản giữ là chữ JSON; mỗi lượt trả dict mới, sửa dict (như `public_ledger`, `ledger_projections`) không đụng bản giữ.
- Không đổi số lần chạy, thứ tự hay kết quả của đường ghi tiền.

## Tiêu chí nghiệm thu

- [ ] `tools/test_pg_v7_backend_read_stamp.py` (harness máy): dấu không đổi khi chỉ đọc (cả `get_ledger`, `get_dashboard_debt`), đổi sau ghi phiếu thu, sau đổi tên loại phí (lệnh không tăng `version`), sau xóa dòng; `as_of` là ngày VN; thiếu người làm thì `ACTOR_REQUIRED`; `v7_app` và `v7_reader` gọi được. `--migration-test` chạy migration mới trên bản sao, chạy lại được.
- [ ] `tests/test_v7_read_cache.py`: trúng khi cùng dấu (hàm đọc chạy một lần), đổi dấu thì đọc lại và bỏ bản cũ, đổi ngày thì đọc lại, hàm không thuộc bốn hàm thì đi thẳng, dấu lỗi/sai dạng thì đi thẳng, lỗi hàm đọc không được giữ và truyền cho lượt chờ, hai lượt cùng khóa chạy hàm một lần, dict trả về sửa được mà không đổi bản giữ, vượt giới hạn byte thì bỏ bản cũ nhất.
- [ ] `tests/test_v7_ledger_api.py`: GET sổ, Tổng quan đi qua bộ nhớ; POST không; kết quả GET giống hệt khi không có bộ nhớ.
- [ ] `tests/test_v7_inbox*.py`: sổ bẩn tính song song (barrier), hai GET cùng lúc không tính trùng.
- [ ] `npm run check` xanh; `node scripts/check-secrets.js` sạch.
- [ ] Sau triển khai trên `hao`: đo lại bảng trên cùng cách; dấu trước/sau một lệnh ghi đổi; ghi số vào nhật ký triển khai.

## Phạm vi agent

- Agent: claude
- Review: opus (đường đọc số dư cho mọi màn)
- Được sửa:
  - `specs/hieu-nang-01.md`, `MAP.md` (nếu đổi cấu trúc)
  - `cong-no-web-handoff/tools/migrations/2026-11-13-v7-dau-doc.sql`, `cong-no-web-handoff/tools/v7_backend_functions.sql`, `cong-no-web-handoff/tools/v7_post_deploy_check.sql`, `cong-no-web-handoff/tools/pg_v7_harness.py`, `cong-no-web-handoff/tools/test_pg_v7_backend*.py`, `cong-no-web-handoff/tools/test_pg_v7_grants.py`
  - `cong-no-web-handoff/web/v7_read_cache.py` (mới), `v7_psql.py`, `v7_api_tables.py`, `v7_ledger_api.py`, `v7_api_doi_chieu.py`, `v7_inbox.py`
  - `cong-no-web-handoff/tests/test_v7_read_cache.py` (mới), `test_v7_ledger_api.py`, `test_v7_fee_sql_sync.py`, test hộp thư
  - `docs/v7-deploy-runbook.md`, `docs/deploys/2026-11-13-dau-doc.md`
- Ngân sách diff: 500 dòng
- Lệnh kiểm: `npm run check`; harness PostgreSQL ở máy (`tools/test_pg_v7_backend.py`, `--migration-test`)
- Cấm: đổi thân hàm SQL có sẵn; giữ kết quả ở đường ghi/máy; thêm dependency.

## Hoàn tác

Revert PR (release cũ không gọi hàm dấu). DB: `DROP FUNCTION sokhach.get_read_stamp();` — không dữ liệu nào phụ thuộc; release mới khi đó tự đọc thẳng DB.
