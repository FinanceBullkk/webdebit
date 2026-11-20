# Máy Zalo: một tiến trình nền, con trỏ theo revision (ZALO-AGENT-01)

Trạng thái: **ĐÃ CHỐT** (người dùng, chat 20/11/2026: "làm theo đề xuất" cho Q1–Q6 ở [cuối spec](#câu-hỏi-đã-chốt)). Chưa code. Quyết định đi kèm: [`ZALO-AGENT-01`](../docs/decisions/zalo-agent-01.md).

Spec này gom 6 cải tiến cho đường dữ liệu Zalo ở máy có Zalo (`msi`) và phía `hao`:

1. [Con trỏ theo revision](#phần-1-tiến-trình-nền-và-con-trỏ-theo-revision)
2. [Một kênh đẩy chung](#phần-2-một-kênh-đẩy-chung)
3. [Kết quả đọc ảnh có nguồn gốc](#phần-3-kết-quả-đọc-ảnh-có-nguồn-gốc)
4. [Che số tài khoản trước khi gửi ra ngoài](#phần-4-che-thông-tin-trước-khi-gửi-ra-ngoài)
5. [Vòng phản hồi cho đối chiếu](#phần-5-vòng-phản-hồi)
6. [Nhịp tim từng chặng](#phần-6-nhịp-tim-từng-chặng)

Spec này **thay A1 và A4** trong [Phần A của spec Thu chi](zalo-thu-chi-real-time.md#phần-a-gần-thời-gian-thực), mở rộng B4 và [`ANH-GEMINI-01`](../docs/decisions/anh-gemini-01.md). A2, A3 (phía `hao`) và Phần B còn lại của spec Thu chi giữ nguyên.

## Vì sao

Ngày 20/11/2026 có bốn sự cố, đều do cách các mảnh nối với nhau chứ không do một mảnh nào sai:

- **Lỗi quyền lặp hai lần.** Đường đẩy chat và đường đẩy bảo hiểm là hai bản cài khác nhau của cùng một việc (ssh + tar + quyền), nên cùng một lỗi setgid xảy ra ở cả hai ([nhật ký](../docs/deploys/2026-11-01-zalo-group.md#sửa-quyền-thư-mục-gói-20112026)).
- **Đứng im mà không ai biết.** Máy tắt 02:05–07:56. Sau khi bật, Zalo mở muộn, live-sync báo `waiting_for_zalo`. Web vẫn hiện "cập nhật 01:56" và không có cảnh báo nào.
- **Code chạy từ nơi khác `main`.** Task đẩy bảo hiểm chạy từ một worktree, và là task duy nhất dừng khi máy chạy pin.
- **Log phình to.** `heap-probe.log` lên khoảng 555 MB vì mỗi lần dò thành công lại in nguyên hai file JSON; không log nào được xoay vòng.

Lượng dữ liệu nhỏ: khoảng 126 nghìn tin, 54 nhóm, ảnh chuyển khoản khoảng 1 ảnh mỗi ngày ([P0](zalo-thu-chi-real-time.md#bằng-chứng)). Vì vậy spec **không** thêm DB, hàng đợi hay dịch vụ mới. Chỉ dùng file có sẵn và một con số nhớ chỗ.

## Hiện nay (đo 20/11/2026)

**Ở máy có Zalo:**

| Mảnh | Chạy thế nào | Đọc gì | Ghi gì |
| --- | --- | --- | --- |
| `watchdog.py` (repo `zalo-audit-viewer`) | Lối tắt trong Startup, 30 giây kiểm một lần | Danh sách tiến trình | Bật lại `live_sync.py` và `server.py` khi chết |
| `live_sync.py --interval 1` | Do watchdog bật | Bộ nhớ và SQLite của Zalo PC | Mỗi giây ghi `revision.json`. Mỗi lần có thay đổi: ghi lại cả `messages.jsonl` (khoảng 131 MB), thêm `changes-N.json` |
| `WebdebitZaloSync` | Task 15 phút, code ở checkout `main` của repo này | Cả `messages.jsonl` | Dựng lại cả gói, ssh + tar tới `hao:/srv/v7/zalo-bundle` |
| `ZaloInsuranceSync` | Task 15 phút (repo `zalo-audit-viewer`) | Cả `messages.jsonl` hai lần, mọi PDF | `insurance-snapshot.json`, cache OCR theo sha256 |
| `ZaloInsurancePush` | Task 15 phút, code ở **worktree** nhánh `claude/bao-hiem-web`, dừng khi chạy pin | Snapshot, băm lại mọi PDF mỗi lượt | ssh + tar tới `hao:/srv/v7/insurance`, cách cài khác đường chat |

**`changes-N.json`** chỉ có danh sách `message_id` (64 ký tự): `added`, `updated`, `deleted`, và `counts`. Không có nội dung tin, không có `conversation_id`. File chỉ ghi khi có thay đổi; số revision tăng một mỗi lần như vậy. Không bao giờ bị xóa: đo được 1.159 file, khoảng 1,1 MB.

**`revision.json`** ghi lại mỗi giây và ghi **sau cùng**, sau khi `messages.jsonl` đã thay. Từng file thay nguyên tử, nhưng cả bộ file thì không.

**Tin bị xóa** vẫn còn dòng: `body = null`, `deleted = true`. **Tin sửa** thay cả dòng.

Không mảnh nào nhớ "đã xử lý tới revision nào". Mỗi lượt đọc lại từ đầu.

## Thiết kế

```
Zalo PC ─► live-sync ─► revision.json + changes-N.json + messages.jsonl      (không đổi)
                                │
                       ┌────────▼─────────┐
                       │   zalo-agent     │  một tiến trình nền trên máy có Zalo
                       │  (thay 2 task)   │
                       └─┬───────┬──────┬─┘
        con trỏ riêng ►  │       │      │
                    Gói chat  Bảo hiểm  Đọc ảnh tiền (OCR → Gemini → người)
                         └───────┼──────┘
                       Kênh đẩy chung (ssh, umask 027, không chmod)
                                 │
            hao: /srv/v7/zalo-bundle, /srv/v7/insurance, /srv/v7/zalo-agent/status.json
                                 │
            Trang Chat Zalo, Thu chi, Máy chạy; máy canh email
```

### Phần 1: tiến trình nền và con trỏ theo revision

**Mã:** `cong-no-web-handoff/tools/zalo_agent/` trong repo này ([Q1](#câu-hỏi-đã-chốt)). Chỉ đọc thư mục live-sync, không ghi gì vào đó.

**Nguồn.** `Source` đọc `revision.json` trước, rồi đọc các `changes-(c+1) … changes-R`, với `c` là con trỏ và `R` là revision vừa đọc. Gom các `message_id` thêm, sửa, xóa. Sau đó quét `messages.jsonl` **một lượt**:

- lọc dòng bằng tìm chuỗi byte `message_id` trước, chỉ `json.loads` dòng trúng;
- chỉ giữ tin của nhóm đã chọn ([`ZALO-GROUP-01`](../docs/decisions/zalo-group-01.md)).

Mục tiêu dưới 2 giây cho 131 MB; đo ở PR-1. Gom các revision trong 3 giây rồi mới xử lý, như A1 cũ.

**Bộ xử lý.** Mỗi việc là một bộ xử lý có tên (`bundle`, `insurance`, `money_images`) và một con trỏ riêng ở `D:\zalo-agent\state\<tên>.json`:

```json
{"revision": 1129, "baseline_sha256": "…", "updated_at": "2026-11-20T08:03:51+07:00"}
```

Bộ xử lý nhận hai loại kích hoạt:

- **theo revision:** gói chat, đọc ảnh tiền;
- **theo file đổi** (so sha256): bảo hiểm, đọc `insurance-snapshot.json` do `insurance_sync.py` ghi.

**Quy tắc con trỏ:**

1. Con trỏ chỉ tiến **sau khi** đẩy lên `hao` thành công. Chết giữa chừng thì lượt sau làm lại từ con trỏ cũ: giao ít nhất một lần.
2. Mọi thứ đẩy đi phải **idempotent** theo `message_id` (tin) hoặc sha256 (ảnh, PDF). Gửi lại một revision không sinh dòng trùng.
3. **Dựng lại từ đầu** cho một bộ xử lý khi:
   - thiếu một `changes-N` ở giữa;
   - `revision.json` nhỏ hơn con trỏ (live-sync khởi tạo lại);
   - `baseline-manifest.json` đổi;
   - đổi danh sách nhóm đã chọn;
   - mỗi đêm một lần, như A1 cũ.
4. Đọc `revision.json` trước rồi mới đọc `messages.jsonl`. Có thể `messages.jsonl` đã mới hơn `R`; không sao, vì lượt sau xử lý lại theo quy tắc 2.

**Gói chat theo phần thêm.** Bộ xử lý `bundle` ghi tin thêm và tin sửa vào `messages-delta.jsonl`. Tin xóa ghi một dòng `deleted` (khuôn ở [hợp đồng dữ liệu](#hợp-đồng-dữ-liệu-giữa-máy-zalo-và-hao)). Vì vậy A2 trên `hao` đổi từ "tin trùng thì giữ một" thành **"bản mới nhất theo `message_id` thắng; tin xóa hiện giống bản dựng đầy đủ"**.

**Chạy nền.** Task Scheduler bật `zalo-agent` lúc đăng nhập và chạy lại khi chết, **kể cả khi chạy pin**, một bản duy nhất (`IgnoreNew`). Lệnh: `pythonw -X utf8 -I …\zalo_agent run`. Có `--once` để chạy tay và `--dry-run` để không đẩy.

**Dọn ở repo `zalo-audit-viewer`** (PR-0, ngoài repo này):

- `heap_probe_current.py` chỉ in số đếm, không in nguyên file JSON;
- xoay vòng các log ở `logs/`: 10 MB mỗi file, giữ 3 file;
- xóa `blocker.json` cũ mà không mảnh nào đọc.

### Phần 2: một kênh đẩy chung

**Mã:** `zalo_agent/push.py`, thay `push()` của `zalo_web_bundle.py` và `insurance_push.py`. Lấy phần tốt của mỗi bên:

| Từ | Giữ lại |
| --- | --- |
| Đường bảo hiểm | Máy chủ là nơi giữ trạng thái: hỏi danh sách file và sha256 trên máy chủ trước, chỉ gửi phần thiếu; không đổi gì thì không gửi tar |
| Đường bảo hiểm | Giải nén vào thư mục `.incoming-XXXXXX` tạo bằng `mktemp` trong thư mục đích, `trap` dọn khi lỗi |
| Đường chat | `umask 027` ở đầu, **không bao giờ `chmod`**; thư mục con kế thừa nhóm và setgid của gốc |
| Cả hai | File chốt (`export-report.json`, `insurance-web.json`, `status.json`) `mv` sau cùng; dọn file không còn trong danh sách giữ |

Gọi bằng một "kế hoạch đẩy": thư mục đích, các file (đường dẫn tương đối, sha256, nguồn), file chốt, luật dọn, và (từ PR-3) danh sách `keep`: tên mà máy chủ đang có thì giữ, không gửi. Bố cục thư mục trên `hao` **không đổi**, nên `v7_zalo_chat.py` và `v7_insurance_queue.py` đọc như cũ.

Sau PR-3, task `ZaloInsurancePush` và worktree `claude/bao-hiem-web` không còn cần. `insurance_web.build` (dựng bản gọn) chuyển vào bộ xử lý `insurance`.

**Bộ xử lý `insurance` (PR-3, `zalo_agent/processors/insurance.py`).**

- **Kích hoạt theo file đổi**, không theo revision: sha256 của `insurance-snapshot.json` đổi, hoặc kho PDF (`remote-media-store`) có file mới hoặc đổi (chữ ký tên + cỡ + mtime), hoặc đã 15 phút chưa hỏi `hao` (máy chủ mất file thì lượt sau tự gửi lại). Snapshot không đổi và chưa tới 15 phút thì không chạm máy chủ. Lượt hỏi mà `hao` đã đủ thì không gửi tar.
- **Bản gọn** `insurance-web.json` giữ **nguyên hợp đồng** của `insurance_web.build` ([`BAO-HIEM-ZALO-01`](v7-bao-hiem-zalo.md#nguồn-và-đường-đẩy-lên-hao)): `schema_version` 1, danh sách trắng 13 trường, các dòng xếp theo (`sha256`, `cert_no`, `container`), `sha256` tính trên các dòng, `row_count`, NULL vẫn NULL, giá trị riêng tư lọt vào `warnings` thành `[redacted]`. Các dòng không đổi thì giữ nguyên byte (kể cả `created_at`) nên máy chủ không thấy đổi vô cớ. Đã so bằng test với golden sinh từ code gốc, và trên snapshot thật bằng sha256 (không in nội dung).
- **Đẩy** tới `hao:/srv/v7/insurance`: `pdf/<sha256 nội dung>.pdf` (bất biến: cùng tên và cùng cỡ là đủ), `insurance-web.json` `mv` sau cùng, dọn `pdf/*` không dòng nào còn dùng. Giấy có dòng mà máy này tạm không có PDF thì PDF đang có trên `hao` được giữ (`keep`).
- **Không đẩy khi snapshot 0 dòng** (`empty_snapshot`): snapshot hỏng không được dọn sạch `hao`. Snapshot sai khuôn là `snapshot_invalid`; snapshot từng có rồi mất là `no_snapshot`; chưa từng có (chưa cài `insurance_sync`) thì im.
- **Không băm lại mọi PDF mỗi lượt:** kho đặt tên file theo băm URL nên phải băm nội dung; sha256 nhớ theo (tên, cỡ, mtime) trong `state/insurance.json` (chỉ có băm, số đếm và giờ). PDF đặt tên theo nội dung nên cache này an toàn.
- **`status.json`:** khóa `processors.insurance` cùng khuôn `bundle`, nhưng `revision` và `lag_revisions` luôn `null` (không theo revision). Không đổi `schema`.
- **Cấu hình:** `--insurance-target` / `ZALO_AGENT_INSURANCE_TARGET` (mặc định `hao:/srv/v7/insurance`, rỗng thì tắt), `--insurance-snapshot` / `ZALO_INSURANCE_SNAPSHOT`, `--insurance-store` / `ZALO_INSURANCE_STORE` (mặc định nằm trong thư mục live-sync).
- **`--dry-run`** (sửa kèm PR-3 cho mọi bộ xử lý): làm hết ở máy, không đẩy, **không lưu con trỏ, `status.json`, `identity.json`**; lượt thật sau đó vẫn đẩy.

### Phần 3: kết quả đọc ảnh có nguồn gốc

**Kho kết quả tại máy:** `D:\zalo-agent\reads\<sha256 ảnh>\<engine>@<phiên bản>.json`. Theo đúng mẫu `insurance-ocr-cache/<sha256>.json` đã chạy ổn.

```json
{"engine": "easyocr", "version": "1.7.2+p0", "is_money": true, "amount_vnd": 1500000,
 "txn_time": "2026-11-19T15:02:00+07:00", "bank": "…", "confidence": 0.93, "read_at": "…"}
```

Chữ OCR đầy đủ và vị trí các ô chữ nằm trong file này, **chỉ ở máy có Zalo**.

**Khóa theo nội dung.** Khóa là sha256 nội dung ảnh, không phải tên file trong `media-store` (tên đó là HMAC của mã ảnh Zalo). Cùng ảnh gửi ở hai tin chỉ đọc một lần.

**Tầng quyết định** (theo `ANH-GEMINI-01` mục 4):

1. `easyocr` đọc mọi ảnh của nhóm đã chọn, 2 luồng.
2. Ảnh có dấu hiệu tiền mà OCR đọc không chắc thì gửi `gemini-proxy` và `gemini-api`.
3. Kết luận ghi `decided_by`: `ocr`, `gemini-2` (hai đường khớp) hoặc `human` (cần xem).

"OCR chắc" là ba điều cùng đúng:

- ô số tiền có độ tin cậy ≥ T;
- có ít nhất 2 từ khóa ngân hàng;
- chỉ một ứng viên số tiền đứng đầu.

T chốt bằng dữ liệu ở PR-4 (CÒN MỞ).

**Đọc lại khi đổi engine.** `zalo_agent reread --engine <tên> --since <ngày>` đọc lại bằng engine hoặc phiên bản mới, giữ kết quả cũ cạnh bên để so. Cùng engine và phiên bản thì không đọc lại.

**Lên `hao`:** gói chỉ mang `{sha256, decided: {amount_vnd, txn_time, bank, by}, reads: [{engine, version, amount_vnd, confidence}]}`. Không mang chữ OCR, số tài khoản hay tên (giữ B4).

### Phần 4: che thông tin trước khi gửi ra ngoài

Áp cho mọi ảnh sắp gửi Gemini (cả hai đường), làm tại máy, dùng vị trí ô chữ của OCR ở Phần 3:

- **Tô đen** ô chữ có dãy từ 8 chữ số liền trở lên (số tài khoản, số thẻ), trừ ứng viên số tiền có dấu phân cách hàng nghìn.
- **Tô đen phần giá trị** của dòng có từ khóa tài khoản (`tài khoản`, `STK`, `số TK`, `account`) và tên (`người nhận`, `người chuyển`, `tên`) ([Q4](#câu-hỏi-đã-chốt)).
- Thu nhỏ cạnh dài ≤ 1600 px, bỏ EXIF, gửi JPEG.
- **Không che được thì không gửi.** OCR không tìm thấy ô chữ nào thì không biết che chỗ nào: ảnh đi thẳng sang "cần xem" ([Q3](#câu-hỏi-đã-chốt)).
- Lời nhắn gửi Gemini là câu cố định, chỉ kèm ảnh. Không kèm tên nhóm, người gửi hay chữ của tin.
- Kết quả Gemini phải đúng khuôn JSON `{is_transfer, amount_vnd, txn_time, bank}`, số tiền là số nguyên. Sai khuôn thì coi như lỗi. Kết quả là dữ liệu, không bao giờ là lệnh.
- Cờ `ZALO_AGENT_EXTERNAL=off` tắt hẳn việc gửi ra ngoài. Khóa API và địa chỉ proxy đọc từ biến môi trường ở máy có Zalo, không vào repo, không vào log.
- Mỗi lần gửi ghi một dòng `sent.jsonl`: sha256, đường, giờ, kết quả hoặc mã lỗi.

### Phần 5: vòng phản hồi

**Phụ thuộc** PR-3 của spec Thu chi (bảng `sokhach.cash_report_review`: người dùng xác nhận, sửa, loại). Không thêm bảng hay SQL nào.

`web/v7_cash_chat.py` ghép dòng xác nhận với kết quả đọc (Phần 3) rồi tính theo tuần, **chỉ số đếm**:

- số ảnh máy tự kết luận, theo `decided_by`;
- trong số người đã xác nhận: đúng, sai, theo từng engine và phiên bản;
- số ảnh "cần xem" người đã xử lý.

Hiện ở trang Thu chi (một dòng nhỏ dưới tiêu đề) và trong `summary()` của tab Máy chạy.

**Không tự chỉnh.** Ngưỡng T và khoảng ngày đối chiếu (Q6 của Thu chi) chỉ đổi bằng PR có số đo tuần đi kèm. Máy không tự đổi luật của chính nó.

### Phần 6: nhịp tim từng chặng

**Ở máy có Zalo.** Agent ghi `status.json` mỗi phút và mỗi khi có thay đổi, đẩy qua kênh chung tới `hao:/srv/v7/zalo-agent/status.json`:

```json
{"at": "…", "agent_version": "…",
 "live_sync": {"revision": 1129, "revision_at": "…", "identity": "attached"},
 "processors": {"bundle": {"revision": 1129, "lag": 0, "last_ok_at": "…", "error": null},
                "insurance": {"…": "…"}, "money_images": {"…": "…"}},
 "push": {"last_ok_at": "…", "error": null}}
```

Chỉ có mã và số đếm, không chữ tự do. `identity` lấy từ `poller-identity.json` của live-sync (`attached`, `waiting_for_zalo`, `reprobing`).

**Ở `hao`:**

- `v7_machine.py` thêm nhóm **"Máy Zalo"** vào tab Máy chạy, mỗi bộ xử lý một dòng, câu thường:
  - "Đang chạy, kịp tin mới";
  - "Zalo chưa mở trên máy Zalo";
  - "Chậm 12 phút";
  - "Không nghe máy Zalo từ 08:05".
- `tools/v7_watchdog.py` thêm phép kiểm `zalo`, chỉ trong 7:00–20:00 giờ VN, chỉ khi đã có `status.json` và đã chọn ít nhất một nhóm:
  - `status.json` cũ quá 15 phút → "máy Zalo im lặng";
  - `waiting_for_zalo` quá 15 phút (tính từ `identity_since`) → "Zalo chưa mở";
  - một bộ xử lý chậm quá 15 phút → "chậm";
  - một bộ xử lý hoặc `push` báo `error` liên tục quá 15 phút → "lỗi" kèm mã ngắn.
- Báo qua kênh email có sẵn ([`CANH-BAO-01`](../docs/decisions/canh-bao-01.md)). Hết lỗi thì có email "đã ổn".

Thay A4 của spec Thu chi: `pushed_at` trong `export-report.json` không cần nữa vì `status.json` mang đủ.

## Hợp đồng dữ liệu giữa máy Zalo và `hao`

PR-1 (máy Zalo ghi) và PR-2 (`hao` đọc) code song song theo đúng mục này. Đổi khuôn thì sửa mục này trước, trong cùng PR.

**Gói chat `/srv/v7/zalo-bundle`.** Bố cục giữ nguyên (`export-report.json`, `data-<dấu thời gian>/`, `media/<sha256>.<đuôi>`). Thêm:

- `data-<…>/messages-delta.jsonl`:
  - **chỉ nối thêm** trong một thư mục dữ liệu;
  - lần dựng lại đầy đủ tạo thư mục dữ liệu mới với `messages.jsonl` mới, chưa có `messages-delta.jsonl`.
- Mỗi dòng của delta:
  - tin thêm hoặc sửa: cùng khuôn với một dòng `messages.jsonl` của gói (đã làm sạch như `build`);
  - tin xóa: **dòng đã làm sạch như bản dựng đầy đủ, thêm `deleted: true`** (có đủ `message_id`, `conversation_id`, `timestamp` và các trường làm sạch khác như `sender_id`, `message_type`, `status`, `body: null`), không chỉ bốn khóa.
- **Bản cuối cùng theo `message_id` thắng**, xét theo thứ tự: `messages.jsonl` rồi tới delta từ trên xuống.
- Dòng `deleted` trong delta hiện **giống hệt** tin có `deleted: true` trong một bản dựng đầy đủ (cùng nhãn, cùng chỗ), để lần dựng lại mỗi đêm không đổi những gì người dùng thấy.
- `data-<…>/media.json` và `data-<…>/users.json` có thể được **thay tại chỗ** khi delta có ảnh hoặc người gửi mới. `hao` đọc lại hai file này mỗi khi `export-report.json` đổi.
- `export-report.json` thêm ba trường; các trường cũ giữ nguyên, kể cả `bundle_sha256` (băm của `messages.jsonl`):
  - `delta_bytes` (int): số byte hợp lệ của delta, 0 khi chưa có;
  - `delta_lines` (int);
  - `revision` (int): revision của live-sync đã gồm trong gói.
- `hao` đọc delta từ byte đã đọc tới đúng `delta_bytes`, không đọc quá. Nhờ vậy dòng đang ghi dở không bao giờ được đọc.
- `data_dir` hoặc `bundle_sha256` đổi thì lập chỉ mục lại từ đầu.
- Thứ tự đẩy: delta, `media.json`, `users.json` và ảnh mới trước; `export-report.json` `mv` sau cùng; dọn file không còn trong danh sách giữ **sau** khi `mv` file chốt, để file chốt cũ không bao giờ trỏ tới thư mục đã xóa.

**Nhịp tim `/srv/v7/zalo-agent/status.json`.** Đường dẫn đọc từ biến môi trường `WEBDEBIT_ZALO_AGENT_STATUS` (mặc định như trên).

```json
{"schema": 1, "at": "2026-11-20T08:04:00+07:00", "agent_version": "<sha commit>", "selected_groups": 1,
 "live_sync": {"revision": 1129, "revision_at": "2026-11-20T08:03:51+07:00", "identity": "attached",
               "identity_since": "2026-11-20T08:03:10+07:00"},
 "processors": {"bundle": {"revision": 1129, "lag_revisions": 0, "last_ok_at": "…", "error": null, "error_since": null}},
 "push": {"last_ok_at": "…", "error": null, "error_since": null}}
```

- `identity` ∈ `attached`, `waiting_for_zalo`, `reprobing`, `unknown`; lấy từ `poller-identity.json` của live-sync.
- `identity_since`: lúc `identity` đổi sang giá trị hiện tại (agent tự ghi nhận). `hao` đo "Zalo chưa mở quá 15 phút" bằng trường này; thiếu thì dùng `revision_at`.
- `live_sync.revision` và `revision_at` là `null` khi agent không đọc được `revision.json`.
- `error` là mã ngắn `[a-z_]{1,40}` hoặc `null`, không chữ tự do.
- `error_since` (có ở mỗi bộ xử lý và ở `push`): lúc `error` chuyển từ `null` sang có lỗi. Giữ nguyên mốc khi mã lỗi đổi sang mã khác mà vẫn lỗi; về `null` khi lần chạy kế thành công. Agent nhớ trong `status.json` ở thư mục trạng thái nên chạy lại không mất mốc. `hao` đo "lỗi liên tục quá 15 phút" bằng `now - error_since` (không dùng `last_ok_at`: lỗi ngay từ đầu thì không có `last_ok_at`, còn lỗi thoáng qua sau nhiều giờ im lặng thì báo ngay); thiếu thì coi như mới lỗi.
- Giờ là ISO 8601 có `+07:00`.
- **Thiếu file** (chưa bật agent): tab Máy chạy hiện "Chưa có máy Zalo báo về", máy canh im.
- **File đọc lỗi, `schema` khác 1, hoặc `at` cũ quá 15 phút**: "Không nghe máy Zalo từ …"; máy canh báo theo Phần 6. Không báo lỗi trang.
- Bộ xử lý chưa có thì không có khóa; `hao` chỉ hiện các khóa có mặt.

**Trang hỏi tin mới theo thứ tự đến** (thay `after=<timestamp>` của A3, chỉnh 20/11/2026 sau review PR-2): `GET /api/v7/zalo/messages?conversation=…&since=<token>` trả mọi dòng của hội thoại đến sau `token` (thêm, sửa, xóa) kèm `token` mới. `token` do server cấp (gắn với `bundle_sha256` và vị trí đã đọc trong delta); token của gói cũ thì trả `{reset: true}` và trang tải lại hội thoại. Lý do: khi máy Zalo mở lại sau một đêm, live-sync đọc bù hàng trăm tin có giờ gửi cũ hơn tin mới nhất trang đang hiện; lọc theo giờ gửi sẽ bỏ lỡ chúng.

Thư mục `/srv/v7/zalo-agent` trên `hao` (nhóm `v7app`, `drwxr-s---`) do Claude tạo bằng `sudo` ở bước Chuyển, theo đúng cách của `/srv/v7/zalo-bundle`.

## Người dùng và luồng

- **Luồng 1. Xem máy Zalo còn chạy không (sếp, người dùng).** Mở tab Máy chạy → nhóm "Máy Zalo" hiện trạng thái từng việc bằng câu thường. Không có dòng nào đỏ thì không phải làm gì.
- **Luồng 2. Nhận cảnh báo và tự sửa (người dùng).** Email "Zalo chưa mở trên máy Zalo từ 08:05" → mở Zalo PC → trong 1–2 phút agent tự đuổi kịp → email "đã ổn". Máy tắt thì email "máy Zalo im lặng" → bật máy.
- **Luồng 3. Xem số tiền máy đọc từ ảnh (người dùng, trang Thu chi).** Mỗi ảnh chuyển khoản hiện số tiền kèm nhãn nhỏ: "máy đọc", "hai lần đọc khớp", hoặc "cần xem". Bấm xác nhận hoặc sửa ở PR-3 của Thu chi; việc đó nuôi Phần 5.

## Hành vi và bất biến

- **Không ghi tiền.** Không đường nào trong spec này đổi số dư, phân bổ, tháng khóa hay `customer.version`.
- **Chỉ đọc live-sync.** Agent không ghi vào thư mục live-sync hay vào kho của Zalo PC.
- **Chỉ nhóm đã chọn rời máy.** Tin, ảnh và kết quả đọc của nhóm chưa chọn không lên `hao`, không ra Gemini.
- **Chữ của tin không đi vào model nào** (giữ B1 của Thu chi). Ra Gemini chỉ có ảnh đã che theo Phần 4.
- **Giao ít nhất một lần, không trùng:** con trỏ tiến sau khi đẩy thành công; `hao` gộp theo `message_id` và sha256.
- **Quyền:** `umask 027`, không `chmod`, file chốt `mv` sau cùng, cho mọi thư mục đích.
- **Không DB mới, không cổng ghi mới** trên `hao`, không đổi Tailscale; thêm đúng một thư mục `/srv/v7/zalo-agent`.
- **Bí mật ngoài repo:** khóa API, địa chỉ proxy, link ping.

## Đầu ra

1. `zalo-agent` chạy nền ở máy có Zalo, thay `WebdebitZaloSync` và `ZaloInsurancePush`.
2. Một module đẩy dùng chung cho mọi thư mục đích trên `hao`.
3. Kho kết quả đọc ảnh theo sha256 + engine + phiên bản, lệnh đọc lại.
4. Che thông tin trước khi gửi Gemini, cờ tắt gửi ra ngoài.
5. Số đo đúng/sai theo tuần, từng engine.
6. `status.json`, nhóm "Máy Zalo" ở tab Máy chạy, phép kiểm `zalo` của máy canh.

## Kế hoạch: chia PR và cổng

Thứ tự theo phụ thuộc. Mỗi PR ≤ 600 dòng logic, `npm run check` xanh. Không PR nào có SQL, nên harness PostgreSQL không bắt buộc.

| PR | Nội dung | Phần | Phụ thuộc | Cổng trước khi bật |
| --- | --- | --- | --- | --- |
| PR-0 | Repo `zalo-audit-viewer`: heap probe in số đếm, xoay vòng log, xóa `blocker.json` cũ | 1 | — | Không đụng dữ liệu Zalo; tự làm |
| PR-1 | `zalo_agent`: `Source` theo revision, con trỏ, bộ xử lý `bundle` theo phần thêm, `push.py` chung, `status.json` ghi tại máy | 1, 2, 6 | — | Chạy `--dry-run` song song task cũ một ngày, so gói |
| PR-2 | `hao`: A2 đọc phần thêm (bản mới nhất thắng, dòng xóa), A3 `after=` và trang tự cập nhật, đọc `status.json` ở tab Máy chạy, phép kiểm `zalo` | 1, 6 | PR-1 | Merge là deploy; phép kiểm chỉ bật khi có `status.json` |
| Chuyển | Bật task `zalo-agent`, tắt (không xóa) `WebdebitZaloSync` | 1 | PR-1, PR-2 | **Hỏi người dùng** (spec Thu chi đã ghi: thay task 15 phút phải hỏi) |
| PR-3 | Bộ xử lý `insurance` qua `push.py` chung; chuyển `insurance_web.build` vào | 2 | Chuyển | **Hỏi người dùng** trước khi tắt `ZaloInsurancePush` |
| PR-4 | Bộ xử lý `money_images`: OCR 2 luồng, kho kết quả, đọc lại, che thông tin, Gemini hai đường, kết luận | 3, 4 | Chuyển; PR-2 của Thu chi để có trang hiện | Người dùng đặt khóa API và địa chỉ proxy ở máy có Zalo; thử với `ZALO_AGENT_EXTERNAL=off` trước |
| PR-5 | Số đo tuần theo engine ở trang Thu chi và Máy chạy | 5 | PR-3 của Thu chi, PR-4 | Không |

Quan hệ với spec Thu chi: PR-1 của Thu chi (A1–A4) được thay bởi PR-1, PR-2 và bước Chuyển ở đây. PR-2, PR-3 của Thu chi giữ nguyên. PR-4 của Thu chi chính là PR-4 ở đây.

Review: sonnet medium cho PR-0, PR-2, PR-5; opus cho PR-1, PR-3, PR-4 (con trỏ, quyền trên máy chủ, dữ liệu ra ngoài).

## Tiêu chí nghiệm thu

- [ ] PR-0: sau một ngày chạy, `logs/` dưới 40 MB; heap probe vẫn dò được (watchdog ghi `exit=0`).
- [ ] PR-1, test với kho live-sync giả (fixture bịa, không dữ liệu thật):
  - thêm, sửa, xóa tin ra đúng `messages-delta.jsonl`;
  - chết giữa lượt đẩy thì lượt sau gửi lại, `hao` không có dòng trùng;
  - thiếu `changes-N` ở giữa, revision lùi hoặc baseline đổi thì dựng lại từ đầu;
  - nhóm chưa chọn không lọt vào gói;
  - quét 131 MB dưới 2 giây (đo trên máy có Zalo, ghi số).
- [ ] PR-1: test của `push.py`: kịch bản máy chủ có `umask 027`, không có `chmod`, file chốt `mv` sau cùng; không đổi gì thì không gửi tar.
- [ ] PR-1: thử trên `hao` ở thư mục tạm có setgid, đẩy hai lượt: mọi thư mục giữ `drwxr-s---` nhóm `v7app`, `v7app` đọc được; xóa thư mục tạm. Ghi nhật ký.
- [ ] PR-2: `tests/test_v7_zalo_chat.py`: phần thêm có bản sửa và dòng xóa thì hiện bản mới nhất, tin xóa hiện giống bản dựng đầy đủ; ảnh và người gửi mới trong `media.json`, `users.json` hiện được; `since=` trả cả tin tới muộn (giờ gửi cũ hơn), tin sửa, tin xóa; token gói cũ thì `reset`.
- [ ] PR-2: `tests/test_v7_watchdog.py`: `status.json` cũ 16 phút lúc 10:00 thì báo, lúc 22:00 thì không; `waiting_for_zalo` 16 phút thì báo; chưa chọn nhóm nào thì không kiểm.
- [ ] PR-2: test trình duyệt tab Máy chạy: nhóm "Máy Zalo" hiện bốn trạng thái bằng câu thường, ở 1280×720 và 390px.
- [ ] Chuyển: một ngày làm việc trên máy thật, tin mới lên web trong **30 giây** (p95, từ `revision_at` tới `status.json` trên `hao`); khởi động lại máy rồi mở Zalo thì agent tự đuổi kịp, không mất tin. Ghi số trong nhật ký.
- [x] PR-3, test với snapshot, PDF và máy chủ bịa (`tests/test_zalo_agent_insurance.py`): bản gọn trùng từng byte với golden của code gốc; PDF mới gửi, PDF cũ dọn, PDF mất ở máy thì giữ trên máy chủ; 0 dòng không đẩy; snapshot không đổi thì không gửi tar; lỗi đẩy thì `error_since` có mốc; băm PDF theo cache; `--dry-run` không lưu gì.
- [ ] PR-3, ở bước bật: task bảo hiểm không còn phụ thuộc worktree, chạy cả khi dùng pin; mọi giấy hiện như trước trên `hao` (hỏi người dùng trước khi tắt `ZaloInsurancePush`).
- [ ] PR-4, ảnh tổng hợp bằng PIL (số tài khoản giả):
  - ô có dãy ≥ 8 chữ số bị tô đen, số tiền không bị che;
  - OCR không thấy chữ thì không gửi;
  - `ZALO_AGENT_EXTERNAL=off` thì không có kết nối ra ngoài;
  - cùng engine và phiên bản thì không đọc lại;
  - kết quả Gemini sai khuôn bị loại.
- [ ] PR-4: trên 20 ảnh của P0, OCR với ngưỡng T vẫn đúng 20/20; số ảnh phải gửi Gemini được báo trong chat.
- [ ] PR-5: với dòng xác nhận giả, số đo tuần đúng theo engine; không chữ tự do nào vào `summary()`.
- [ ] Người dùng tự đi Luồng 1–2 (tắt Zalo 20 phút trong giờ làm, nhận email, mở lại, nhận email "đã ổn") và Luồng 3 trên trang Thu chi.

## Hoàn tác

- **Chuyển:** tắt task `zalo-agent`, bật lại `WebdebitZaloSync` (đã tắt chứ không xóa). Gói trên `hao` vẫn đọc được vì thiếu phần thêm thì chỉ đọc gói gốc.
- **PR-3:** bật lại `ZaloInsurancePush` từ worktree cũ; giữ worktree tới khi PR-3 chạy ổn hai tuần.
- **PR-4:** `ZALO_AGENT_EXTERNAL=off`, hoặc tắt bộ xử lý `money_images`. Trang Thu chi chỉ thiếu số đọc từ ảnh.
- **PR-2, PR-5:** revert. Phép kiểm `zalo` tự im khi không có `status.json`.
- Kho `D:\zalo-agent` xóa được bất cứ lúc nào; agent dựng lại từ đầu.

## Nguồn quyết định

- [`ZALO-GROUP-01`](../docs/decisions/zalo-group-01.md): chỉ nhóm đã chọn rời máy; đường ssh G5.
- [`ZALO-THU-CHI-01`](../docs/decisions/zalo-thu-chi-01.md): gần thời gian thực, không DB mới, hỏi trước khi thay task 15 phút.
- [`ANH-GEMINI-01`](../docs/decisions/anh-gemini-01.md): OCR chính, Gemini khi cần, hai đường; ràng buộc khóa và log.
- [`CANH-BAO-01`](../docs/decisions/canh-bao-01.md): kênh email của máy canh.
- [`MAY-CHAY-01`](../docs/decisions/may-chay-01.md): tab Máy chạy, `summary()` không mang chữ tự do.
- [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md): merge là deploy; không có migration.

## Ngoài phạm vi

- **Máy luôn bật.** Mọi thứ vẫn phụ thuộc một laptop có lúc tắt. Một máy mini luôn bật chỉ chạy Zalo PC (Q5 của Thu chi) là khuyến nghị, không thuộc spec này.
- DB, hàng đợi, dịch vụ mới; route ghi mới trên `hao`.
- Bot trả lời trong nhóm, WeChat, nối ngân hàng.
- Đổi cách `live_sync.py` ghi `messages.jsonl` (ghi lại cả file). Agent đọc được như hiện nay; tối ưu phía đó để sau nếu đo thấy chậm.

## Câu hỏi đã chốt

Người dùng chốt cả sáu câu theo đề xuất (chat 20/11/2026, "làm theo đề xuất").

- **Q1 — Mã agent đặt ở đâu?** **Chốt:** repo này (`tools/zalo_agent/`), vì có CI, review và test. Repo public nên không chứa dữ liệu hay bí mật; mọi cấu hình đọc từ biến môi trường. Phương án khác: repo `zalo-audit-viewer`.
- **Q2 — Bật agent bằng gì?** **Chốt:** Task Scheduler lúc đăng nhập, tự chạy lại khi chết, chạy cả khi dùng pin. Phương án khác: lối tắt Startup như `watchdog.py` (không tự chạy lại).
- **Q3 — Ảnh không che được thì sao?** **Chốt:** không gửi Gemini, đưa người xem. Phương án khác: vẫn gửi (đúng hơn nhưng lộ số tài khoản).
- **Q4 — Che cả tên người chuyển, người nhận?** **Chốt:** có. Gemini chỉ cần số tiền, giờ, ngân hàng.
- **Q5 — Giờ cảnh báo.** **Chốt:** 7:00–20:00 giờ VN, theo Q5 của Thu chi.
- **Q6 — Thứ tự làm.** **Chốt:** PR-0 → PR-1 → PR-2 → Chuyển → PR-3; PR-4 sau PR-2 của Thu chi; PR-5 cuối.

## Bằng chứng

Số đo ở mục [Hiện nay](#hiện-nay-đo-20112026) lấy ngày 20/11/2026 trên máy có Zalo, chỉ đọc: cấu trúc `changes-N.json` và `revision.json`, cách ghi `messages.jsonl`, các task và lối tắt khởi động, cách đẩy của hai đường, cỡ log. Không chép nội dung tin, tên hay số tài khoản.
