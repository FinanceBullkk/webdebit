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

- **Kích hoạt theo file đổi**, không theo revision: sha256 của `insurance-snapshot.json` đổi, hoặc kho PDF (`remote-media-store`) có file mới hoặc đổi (chữ ký tên + cỡ + mtime), hoặc đã 15 phút chưa hỏi `hao` (máy chủ mất file thì lượt sau tự gửi lại). Snapshot không đổi và chưa tới 15 phút thì không chạm máy chủ. Lượt hỏi mà `hao` đã đủ thì không gửi tar. Vòng lặp chạy mỗi giây nên snapshot chỉ được đọc và băm lại khi (cỡ, mtime_ns) đổi hoặc đã quá 15 phút (mốc an toàn); đọc qua thử lại khi Windows từ chối (`insurance_sync` đang giữ file), vẫn lỗi thì `snapshot_unreadable`.
- **Bản gọn** `insurance-web.json` giữ **nguyên hợp đồng** của `insurance_web.build` ([`BAO-HIEM-ZALO-01`](v7-bao-hiem-zalo.md#nguồn-và-đường-đẩy-lên-hao)): `schema_version` 1, danh sách trắng 13 trường, các dòng xếp theo (`sha256`, `cert_no`, `container`), `sha256` tính trên các dòng, `row_count`, NULL vẫn NULL, giá trị riêng tư lọt vào `warnings` thành `[redacted]`. Các dòng không đổi thì giữ nguyên byte (kể cả `created_at`) nên máy chủ không thấy đổi vô cớ. Đã so bằng test với golden sinh từ code gốc, và trên snapshot thật bằng sha256 (không in nội dung).
- **Đẩy** tới `hao:/srv/v7/insurance`: `pdf/<sha256 nội dung>.pdf` (bất biến: cùng tên và cùng cỡ là đủ), `insurance-web.json` `mv` sau cùng, dọn `pdf/*` không dòng nào còn dùng. Giấy có dòng mà máy này tạm không có PDF thì PDF đang có trên `hao` được giữ (`keep`). Lúc đưa PDF vào tar, nội dung được băm lại và phải khớp tên `pdf/<sha256>.pdf`; lệch thì không gửi file đó, báo `pdf_changed` và băm lại lượt sau. PDF thiếu **cả ở máy lẫn trên `hao`** thì báo `pdf_missing` (giữ tới khi PDF về kho), bản gọn vẫn đẩy phần có.
- **Không đẩy khi snapshot 0 dòng** (`empty_snapshot`): snapshot hỏng không được dọn sạch `hao`. Snapshot sai khuôn, hoặc có dòng thiếu/sai `sha256`, là `snapshot_invalid` (bản gốc `insurance_web.build` vẫn ghi dòng hỏng, nhưng bộ đọc trên `hao` từ chối cả file và danh sách PDF cần giữ thiếu dòng đó sẽ làm dọn PDF, nên không đẩy: `hao` giữ bản tốt cuối cùng); snapshot từng có rồi mất là `no_snapshot`; chưa từng có (chưa cài `insurance_sync`) thì im.
- **Không băm lại mọi PDF mỗi lượt:** kho đặt tên file theo băm URL nên phải băm nội dung; sha256 nhớ theo (tên, cỡ, mtime) trong `state/insurance.json` (chỉ có băm, số đếm và giờ). PDF đặt tên theo nội dung nên cache này an toàn.
- **`status.json`:** khóa `processors.insurance` cùng khuôn `bundle`, nhưng `revision` và `lag_revisions` luôn `null` (không theo revision). Không đổi `schema`. Mã lỗi riêng: `no_snapshot`, `snapshot_unreadable`, `snapshot_invalid`, `empty_snapshot`, `pdf_changed`, `pdf_unreadable`, `pdf_missing`, `push_failed`, `build_failed`.
- **Lỗi cục bộ không giữ vòng lặp chờ:** `empty_snapshot`, `snapshot_invalid`, `build_failed`, `pdf_changed`, `pdf_unreadable` không lưu `snapshot_sha256`, nên bộ xử lý nhớ trong bộ nhớ (sha snapshot, chữ ký kho, giờ) và `wants_work` trả False cho tới khi snapshot (hoặc kho, với lỗi phụ thuộc kho) đổi hoặc tới lượt hỏi lại sau 15 phút; vòng lặp không còn gom 3 giây vì bảo hiểm mỗi lần thử lại 10 giây. `empty_snapshot` và `snapshot_invalid` còn bỏ qua việc dựng lại trong 15 phút đó.
- **PDF bị khóa:** băm PDF qua `retry_io`; vẫn lỗi thì tính vào `pdf_unreadable` (phần đọc được vẫn đẩy), **không lưu `store_sig`** để lượt sau quét lại, chờ 60 giây giữa hai lần quét (không ssh mỗi 10 giây).
- **Cấu hình:** `--insurance-target` / `ZALO_AGENT_INSURANCE_TARGET` (**mặc định rỗng = tắt** cho tới bước bật: agent chạy code từ checkout `main`, nên bật sẵn thì merge là ghi `/srv/v7/insurance` song song task cũ; bước tắt `ZaloInsurancePush` thêm `--insurance-target hao:/srv/v7/insurance` vào lệnh task cùng lúc), `--insurance-snapshot` / `ZALO_INSURANCE_SNAPSHOT`, `--insurance-store` / `ZALO_INSURANCE_STORE` (mặc định nằm trong thư mục live-sync).
- **`--dry-run`** (sửa kèm PR-3 cho mọi bộ xử lý): làm hết ở máy, không đẩy, **không lưu con trỏ, `status.json`, `identity.json`** ra đĩa; lượt thật sau đó vẫn đẩy. Con trỏ vẫn nhớ trong bộ nhớ của tiến trình, nên `run --dry-run` chạy liên tục (không `--once`) dựng gói một lần rồi chỉ xử lý phần thêm, không dựng lại mỗi nhịp.
- **Lùi dần riêng từng bộ xử lý:** `failures` và `retry_at` của mỗi bộ xử lý tách nhau (`push_failed`: 60 giây gấp đôi tới 15 phút; lỗi cục bộ: thử lại sau 10 giây). Lỗi của bộ này không bao giờ làm bộ khác chạy chậm đi hay chờ gom 3 giây; bộ đang lùi giữ kết quả lượt trước trong `status.json`. Mỗi `wants_work` bọc `try` riêng.

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

T mặc định **0,6** (`ocr.CONFIDENCE_T`, đổi bằng `ZALO_AGENT_OCR_CONFIDENCE`). Số đo ngày 20/11/2026 trên 20 ảnh chuyển khoản của P0 (người dùng đã chấm đúng 20/20), chạy qua bộ xử lý thật: **20/20 khớp**; độ tin cậy của ô số tiền thấp nhất 0,42, phân vị 10% là 0,62, trung vị 0,73; cả 20 ảnh đều có ≥ 2 từ khóa và một ứng viên đứng đầu. Số ảnh được coi là "chắc" (đúng cả ba điều) theo T: 0,5 → 19/20; **0,6 → 18/20**; 0,7 → 13/20; 0,8 → 6/20; 0,9 → 3/20, và không ảnh nào "chắc mà sai" ở mọi T. T = 0,6 để 2/20 ảnh sang Gemini; T cao hơn đẩy gần hết ảnh sang Gemini vì easyocr hiếm khi báo tin cậy trên 0,8 cho ô chữ lớn. Mẫu 20 ảnh toàn đúng nên không đo được tỉ lệ "chắc mà sai": T vẫn chỉ đổi bằng PR có số đo tuần đi kèm (Phần 5). Tốc độ: khoảng 19 giây mỗi ảnh (trung vị) khi máy đang chạy Zalo PC, live-sync và agent; lần đọc đầu 71 giây vì nạp model.

**Đọc lại khi đổi engine.** `zalo_agent reread --engine <tên> --since <ngày>` đọc lại bằng engine hoặc phiên bản mới, giữ kết quả cũ cạnh bên để so. Cùng engine và phiên bản thì không đọc lại. Đổi luật phân tích không cần `reread` (xem "Hai phiên bản tách nhau" dưới).

**Bộ xử lý `money_images` (PR-4a-1, `zalo_agent/processors/money_images.py`, `ocr.py`, `reads.py`).**

- **Nguồn ảnh:** tin `message_type` 2 và 7 của **mọi hội thoại trong danh sách đã chọn** (`web-groups.json`), nhóm hay chat riêng 1-1, không lọc theo `is_group` (20/11/2026: tiền thu đọc từ ảnh chuyển khoản ngay trong hội thoại của khách); file lấy ở `media-store` qua `media-index.json` (tên file là `id`, không phải sha256). Dựng lại từ đầu (lần đầu, baseline đổi, đổi nhóm, mất `changes-N`, revision lùi, mỗi đêm) quét ảnh trong `--money-max-age-days` ngày (mặc định 30); giữa hai lần chỉ xét tin thêm trong `changes-N`.
- **Khóa kho** là sha256 của **byte mà gói chat sẽ lưu** (JXL đã chuyển JPEG như `zalo_web_bundle.Media`), để `hao` nối kết quả với `media/<sha256>.<đuôi>`; băm file thô trong `media-store` không dùng được vì `hao` không thấy nó. Cùng ảnh ở hai tin chỉ đọc một lần.
- **OCR ở tiến trình con sống lâu, việc nộp từ một luồng nền (review 20/11/2026):** `step()` chỉ nộp việc, thu kết quả và ghi con trỏ nên 14 giây mỗi ảnh không chặn `bundle` và `insurance`; luồng nền là luồng **daemon**, thoát agent (`--once`) không chờ OCR đang đọc dở. easyocr chạy ở **tiến trình con** (`zalo_agent/ocr_child.py`, `python.exe -X utf8 -I`, 2 luồng torch, `download_enabled=False`) nên torch chết bằng lỗi native hay hết bộ nhớ thì agent vẫn sống và **agent không import torch hay easyocr**. Giao thức: mỗi dòng stdin một yêu cầu `{"path": "<PNG đã thu nhỏ>"}`, mỗi dòng stdout một trả lời `{"boxes": [{b, t, c, p}]}` (`p` = 4 góc [x, y] theo thứ tự trên-trái, trên-phải, dưới-phải, dưới-trái, số nguyên Python: easyocr trả số của numpy mà `json` không in được) hoặc `{"error": "unavailable" | "model_missing" | "failed"}`; nạp model một lần ở yêu cầu đầu; stdin đóng thì con thoát. Kênh trả lời là **bản sao của fd 1 lấy trước khi import torch**, rồi fd 1 và `sys.stdout` nối sang stderr: mã native hay thư viện in gì ra stdout cũng không chen vào giao thức. Ảnh PNG tạm nằm ở `<root>/tmp/` (tên `ocr-*.png`, dọn khi khởi động), không ở `%TEMP%`. Con chết hoặc quá 300 giây thì bị giết và lần đọc sau tạo lại; sau mỗi lần chết bộ xử lý nghỉ 60 giây × 2^(lần liên tiếp − 1), tối đa 1 giờ; `atexit` đăng ký đúng một lần. **Không tự tải model**: model phải có sẵn ở `~/.EasyOCR`, thiếu thì `ocr_unavailable`. Ảnh mới nhất đọc trước.
- **Con trỏ `state/money_images.json`:** `revision`, `baseline_sha256`, `selection_sha256`, `built_at` như `bundle`, cộng `todo` (hàng chờ, sống qua lần khởi động lại), `members` (ảnh của nhóm **đang chọn** đã có kết quả: tập duy nhất được phép xuất ra ngoài; bỏ chọn nhóm rồi dựng lại thì ảnh của nhóm đó rời tập), `canon` (băm file thô → khóa kho, để dựng lại không giải mã lại), `failed` (ảnh đã thử đủ 3 lần: `{file, ts, at}`, bị cấm 1 ngày rồi lần dựng lại thử lại). Con trỏ tiến ngay khi ảnh vào hàng chờ vì bước này không có gì phải đẩy.
- **Khuôn file kho** (`reads/<sha256>/<engine>@<phiên bản>.json`, **chỉ ở máy**): `engine`, `version` (`<phiên bản engine>+<PREPARE>`: phiên bản của ô chữ, xem dưới), `read_at`, `size` (rộng, cao của ảnh đã thu nhỏ ≤ 1600 px mà ô chữ dùng), `boxes` (`b` = [x0, y0, x1, y1], `t` chữ, `c` độ tin cậy, `p` = 4 góc của ô, dùng để biết ô có nghiêng không), và phần phân tích: `is_money`, `amount_vnd`, `confidence` (của ô số tiền), `hits` (số từ khóa), `unique` (một ứng viên đứng đầu), `txn_time` (ISO `+07:00`, hoặc `YYYY-MM-DD`, hoặc null), `bank` (null nếu không thấy), từ luật `a3` thêm `done` (có dấu hiệu giao dịch đã xong), `direction` (`in`/`out`/null), `txn_ref` (mã giao dịch hoặc null) và `currency` (đơn vị của số đứng đầu: `VND`, `USD`, `CNY`, `EUR` hoặc null khi không ghi), `analysis` (phiên bản luật phân tích đã cho các trường đó; file chưa có trường này là luật `a2`). Phân tích lưu rời từng trường nên đổi T không phải đọc lại ảnh.
- **Hai phiên bản tách nhau (A1, 23/11/2026):** ô chữ gắn với engine và tiền xử lý ảnh (`ocr.PREPARE`, nằm trong tên file); luật phân tích gắn với `ocr.ANALYSIS` (trường `analysis`). Đổi tiền xử lý hay engine thì đổi `PREPARE`: kho OCR lại và giữ file cũ cạnh bên (`reread`). Đổi luật phân tích thì đổi `ANALYSIS`: agent **không OCR lại** (15-19 giây mỗi ảnh) mà chạy lại phân tích trên ô chữ đã lưu (vài mili giây), ghi đè các trường phân tích trong cùng file, ô chữ giữ nguyên. Con trỏ nhớ `analysis`; lần đầu nạp con trỏ với luật mới thì kết luận lại cả `members` (ảnh đổi nhóm thì quyết lại `by`, có thể phải hỏi Gemini). Số tiền OCR đổi thì **chỉ ảnh có kết luận `ocr`** (hoặc chưa vào `members`) bị bỏ ảnh đã che để dựng lại theo số mới (luật che `w1` dán lại đúng `amount_vnd`); ảnh `gemini-2`/`human` giữ nguyên ảnh che và số đã có, vì ảnh che đó là ảnh đã gửi Gemini, dựng lại theo số OCR mới thì lệch với số Gemini mà không ai hỏi lại. Ảnh che bị xóa **trước** khi ghi kho; xóa không được thì ảnh đó giữ luật cũ tới lần nạp sau. `--dry-run` và `zalo_agent reread` (không lưu con trỏ) chỉ phân tích lại trong bộ nhớ, không ghi kho, không xóa ảnh che. Khi nạp con trỏ, ảnh ghi "đã có ảnh che" mà file đã mất (lượt trước chết giữa chừng) thì được dựng lại. Ảnh đã che đẩy lên `hao` được so bằng sha256 (không chỉ so cỡ) vì nội dung có thể đổi dưới cùng tên. CÒN MỞ (có từ trước A1): đổi `PREPARE` (OCR lại bằng tiền xử lý mới) chưa bỏ ảnh che cũ, `add_rows` và `hidden_bytes` vẫn dùng lại file `redacted-w1/<sha>.jpg` dựng theo ô chữ cũ; trước khi đổi `PREPARE` phải sửa chỗ này (hoặc đổi `redact.RULE`). `PREPARE` giữ `a2` (tên cũ của chuỗi gộp) nên 52 file `easyocr@1.7.2+a2.json` trên máy có Zalo dùng tiếp: kiểm trên bản sao kho thật 23/11/2026, đổi `ANALYSIS` thì 52/52 file phân tích lại tại chỗ, 0 lần gọi engine, kết luận và `money-reads.json` không đổi.
- **Phân loại:** `none` (không dấu hiệu tiền: không bao giờ rời máy), `ocr` (OCR chắc), `unsure` (có dấu hiệu tiền mà OCR không chắc: sang Gemini). Dấu hiệu tiền = có ít nhất một số ứng viên (luật `a3`) và ≥ 2 từ khóa ngân hàng, hoặc số kèm VND/đ, hoặc số kèm đơn vị tiền khác. OCR chắc = ô số tiền có `confidence` ≥ T, `hits` ≥ 2, `unique`, và (luật `a3`) `done`.
- **Luật phân tích `a3` (A3, 23/11/2026)**, rút từ 42 ảnh có dấu hiệu tiền trên máy có Zalo, không đổi quy tắc tiền:
  - **Giao dịch đã xong** (`done`): một trong các cụm `Thành công` (cả `Giao dịch/Chuyển khoản/Chuyển tiền/Thanh toán thành công`), `Successful` (cả `Transaction/Transfer/Payment successful`), `Transfer completed`, `Transaction completed`, `Transaction confirmed`, `Đã phê duyệt`, `Đã chuyển tiền`, tìm trên **dòng** (ô cùng hàng ghép theo hoành độ, vì OCR hay tách một nhãn thành vài ô lệch thứ tự). Thiếu thì ảnh không "chắc": bảng kê hóa đơn, đề nghị thanh toán, mã QR, màn nhập người hưởng có số tiền và tên ngân hàng mà tiền chưa đi. Ba cụm `Transaction successful`, `Transaction confirmed`, `Đã phê duyệt` có trên ảnh thật; các cụm khác thêm theo review #599.
  - **Giờ giao dịch** (`txn_time`): chỉ ghép ngày với giờ trên **cùng một dòng** (giờ ngay sau ngày nhận cả `12.30` và `10:.35`); ưu tiên dòng có nhãn `Thời gian giao dịch`, `Ngày giao dịch`, `Transaction time/date`, `Ngày phê duyệt` (tiền đi lúc duyệt, không phải lúc yêu cầu), `Thời gian`, `Ngày giờ`; rồi dòng đầu có cả ngày lẫn giờ; rồi ngày đầu tiên. Không còn ghép ngày đầu tiên với giờ đầu tiên của cả ảnh (đồng hồ thanh trạng thái, giờ yêu cầu).
  - **Chiều tiền** (`direction`, góc nhìn người chụp): dấu `+`/`−` dính ô số tiền đứng đầu thắng; không dấu thì theo từ (`nhận tiền`, `tiền vào`, `ghi có`, `received` → `in`; `chuyển tiền`, `chuyển khoản`, `người (thụ) hưởng`, `beneficiary`, `ghi nợ` → `out`); có cả hai phía hoặc không phía nào thì null.
  - **Không có số thì không phải ảnh tiền:** ảnh có từ khóa (`chuyển tiền`, `tài khoản`…) mà không có số ứng viên nào và **không có dấu hiệu giao dịch đã xong** là `none` (không chờ người xem, không rời máy). Trên máy thật đó là ảnh cắt phần "Thông tin người hưởng / Tài khoản người nhận". Ảnh có dấu hiệu đã xong và ≥ 2 từ khóa mà không có số ứng viên (biên lai thật OCR làm rơi dấu chấm: `5000000`, `VND` ô riêng) vẫn là ảnh tiền chờ người xem (review #599).
  - **Tiền khác VND:** số đứng đầu có `USD`/`US$`/`$`, `CNY`/`RMB`/`¥`/`￥`/`人民币`/`元` hoặc `EUR`/`€` trong ô số hay ô sát bên cùng hàng thì `amount_vnd` và `confidence` là null, `currency` ghi mã; ảnh vẫn là ảnh tiền (`unsure`, chờ người xem) chứ không "chắc mà sai". Phiên OCR thấy 5/16 ảnh WeChat có số USD; ảnh WeChat chưa vào hàng đọc (A2) nên chưa đo được trên máy thật.
  - **Mã giao dịch** (`txn_ref`, **chỉ lưu trong kho tại máy, không xuất**: review #599 thấy chuỗi sau nhãn có thể là số điện thoại hay tên trong lời nhắn): giá trị **ngay sau** nhãn `Mã giao dịch`, `Số giao dịch`, `Số/Mã tham chiếu`, `Reference number/no`, `Transaction ID`, `Transfer code`, `Mã GD`, `Số GD` trên cùng dòng; 6-30 ký tự chữ-số, ít nhất 6 chữ số và nhiều nhất 4 chữ cái, không có dạng số di động Việt Nam; dòng có tài khoản/account, nội dung, lời nhắn, diễn giải, ghi chú thì bỏ.
  - **Số đo trước/sau** (bản sao kho và con trỏ thật, chạy qua `reanalyse`, 0 lần gọi engine): 52 ảnh. `ocr` → `ocr` 24; `ocr` → `unsure` 2 (cả hai là bảng kê hóa đơn, không phải biên lai; gửi ra ngoài đang tắt nên thành `human`); `human` → `none` 12 (màn người hưởng không có số); `human` giữ 4 (2 biên lai tiếng Anh mà ô số tiền tin cậy 0,46-0,55 < T, 2 bảng kê hóa đơn); `none` giữ 10; không ảnh nào lên `ocr`. Hàng "cần người xem" (`review`) từ 16 còn 6; `money-reads.json` từ 42 mục còn 30. Giờ đủ phút trong file xuất: 23 ảnh (trước: 3). `txn_ref` (trong kho): 24/24 ảnh `ocr`, 0 ảnh không dấu hiệu tiền. Trên `hao` bảng xử lý khoản báo (`sokhach.cash_report_review`) có 0 dòng lúc 23/11/2026, nên 14 ảnh đổi nhóm không có khoản đã xác nhận, sửa số hay loại nào bị mất. `direction`: 24 `out`, 0 `in`. `currency`: 26 `VND`, 26 null, 0 tiền khác. Số cặp ảnh `ocr` cùng số tiền và cùng phút (khóa gộp của `hao`): 0 trước, 0 sau.
  - CÒN MỞ (review #599): giờ 12 tiếng có AM/PM chưa đổi sang 24 giờ (`03:15 PM` thành 03:15); OCR đọc nhầm chữ O thành số 0 trong số tiền (`5.000.0O0`) thì chỉ nhận phần đầu (5.000) và có thể ra "chắc mà sai" nếu đủ các điều khác; test giờ màn duyệt (`test_approval_screen_takes_the_approval_time...`) cũng xanh trên luật cũ vì giờ duyệt là giờ có dấu `:` đầu tiên của ảnh.
- **`status.json`:** khóa `processors.money_images` cùng khuôn `bundle` (revision, `lag_revisions`, …) cộng `counts` = `{read, pending, failed, review, asking}` (số nguyên): `review` = ảnh đã kết luận `human` (cần người xem), `asking` = ảnh có dấu hiệu tiền mà OCR không chắc, đang chờ Gemini. Mã lỗi: `ocr_unavailable` (máy thiếu easyocr, torch hoặc Pillow), `no_revision`, `scan_failed`, `push_failed` (đẩy `money-reads.json`). Ảnh hỏng, hoặc tiến trình OCR chết khi đọc ảnh đó, thử 3 lần rồi bỏ vào `failed` và chỉ tính vào `counts.failed`. Engine không dùng được (thiếu thư viện, lỗi nạp DLL, thiếu model) là `ocr_unavailable` chứ không phải lỗi của ảnh: **không tính lần thử, không vào `failed`**, bộ xử lý không hỏi lại và không đòi agent gom 3 giây: chờ 60 giây rồi lùi lũy thừa tới tối đa 1 giờ, về 60 giây sau một lần đọc thành công. `counts.failed` chỉ đếm ảnh còn trong hạn cấm 1 ngày.
- **Cấu hình:** `--money-images on|off` / `ZALO_AGENT_MONEY_IMAGES` (**mặc định off**: agent chạy code từ checkout `main`, bật sẵn thì merge là bắt đầu OCR trên máy thật), `--money-max-age-days`, `--reads-target` / `ZALO_AGENT_READS_TARGET` (**mặc định rỗng = không đẩy**; ví dụ `hao:/srv/v7/zalo-reads`, thư mục do bước bật tạo). `--dry-run` vẫn ghi kho kết quả (việc tại máy, idempotent) nhưng không lưu con trỏ, không đẩy và **không gửi ảnh ra ngoài**.
- **Gemini (PR-4a-2, `gemini.py`, `redact.py`):** biến môi trường ở máy có Zalo, không vào repo hay log: `ZALO_AGENT_EXTERNAL` (`on` mới bật; mặc định `off` thì không có kết nối ra ngoài nào), `ZALO_AGENT_GEMINI_MODEL`, đường proxy `ZALO_AGENT_GEMINI_PROXY` (địa chỉ gốc, kiểu tương thích OpenAI `…/chat/completions` mặc định, `ZALO_AGENT_GEMINI_PROXY_STYLE=gemini` cho kiểu `…/v1beta/models/<model>:generateContent`; khóa tùy chọn `ZALO_AGENT_GEMINI_PROXY_KEY`), đường API trả phí `GEMINI_API_KEY` (gửi qua header `x-goog-api-key`, không nằm trong URL). Thiếu một đường hoặc thiếu model thì coi như tắt: không đường nào được tự quyết một mình. Đoạn gọi mạng duy nhất là `gemini.post_json`, đổi nhà cung cấp thì đổi ở đó và ở `request_for`. Địa chỉ proxy phải là `https://`, hoặc `http://` chỉ khi chạy ngay trên máy này (`127.0.0.1`, `localhost`, `[::1]`); cuộc gọi **không đi theo chuyển hướng** (3xx thành lỗi `http_3xx`) và **không dùng proxy hệ thống** (biến môi trường, cài đặt Windows) trừ khi cấu hình rõ `ZALO_AGENT_EXTERNAL_PROXY` (chỉ `http(s)://`, sai khuôn thì tắt hẳn việc gửi ra ngoài; **không áp cho đường `127.0.0.1`/`localhost`/`[::1]`**, proxy 9router ở ngay máy này đi thẳng); khóa nằm trong `Route.headers`, không bao giờ vào `repr`, log hay traceback.
- **Kết luận từng ảnh** (`by`): `ocr` (OCR chắc); ảnh có dấu hiệu tiền mà OCR không chắc thì che rồi gửi **cả hai đường** (mỗi đường lưu vào kho như một lượt đọc `gemini-proxy@<model>`, `gemini-api@<model>`): cùng một số nguyên **dương** và cả hai nói là chuyển khoản → `gemini-2`; lệch, hoặc một đường nói không phải chuyển khoản → `human`; đường lỗi (kể cả lỗi lạ của thư viện), hoặc file media nguồn đã mất, đều tính một lần thử: thử lại sau 10 phút × số lần thử, đủ 3 lần thì `human` (không lặp mỗi giây); không che được (OCR không thấy ô chữ nào, hoặc ảnh không còn cùng kích thước với lúc đọc) → `human`, không gửi gì; gửi ra ngoài tắt → `human` ngay. Ảnh không dấu hiệu tiền không có kết luận và không bao giờ rời máy. Kết luận đã chốt `human` không đổi ý lặng lẽ; dựng lại mỗi đêm tính lại từ kho.
- **`sent.jsonl`** (`D:\zalo-agent\sent.jsonl`, chỉ ở máy): mỗi lần gửi một dòng `{"sha256", "route" ("gemini-proxy"|"gemini-api"), "at", "result" ("ok" hoặc mã lỗi như `http_429`, `timeout`, `network`, `bad_shape`)}`; không chữ OCR, không khóa, không địa chỉ.
- **Che ảnh** (`redact.py`): danh sách trắng như Phần 4 (tấm đen, dán lại ô số tiền, nhãn đã biết, ngày giờ); kiểm bằng ảnh PIL tổng hợp (tên xuống dòng, số tài khoản cách đôi, QR, nhãn `Tên người nhận`/`Tên tài khoản nhận`/`Số tài khoản nhận`/`Account name`, ô số tiền lẫn tên) và đọc từng marker của JPEG ra.
- **File cho `hao`** `money-reads.json` (đẩy bằng `push.py`, chỉ có file chốt nên luôn gửi, `mv` nguyên tử; gửi lại khi nội dung đổi hoặc mỗi giờ; chọn nhóm rỗng thì gửi `reads` rỗng; đang đổi nhóm chưa dựng lại thì chưa gửi):

  ```json
  {"schema": 1, "redact": "w1", "reads": {"<sha256 ảnh, cùng khóa với media/<sha256>.<đuôi> của gói chat>": {
      "by": "ocr", "amount_vnd": 1500000, "txn_time": "2026-11-19T15:02:00+07:00", "bank": "VIETCOMBANK", "direction": "out",
      "reads": [{"engine": "easyocr", "version": "1.7.2+a2", "amount_vnd": 1500000, "confidence": 0.93}]}}}
  ```

  Chỉ có ảnh có dấu hiệu tiền và đã có kết luận (`by` ∈ `ocr`, `gemini-2`, `human`). `human` thì `amount_vnd`, `txn_time`, `bank` là `null` (các số mỗi engine đọc nằm trong `reads`, kèm độ tin cậy, `null` với Gemini); `gemini-2` thì `txn_time` và `bank` chỉ có khi hai đường khớp nhau, không thì `null`. `direction` (luật `a3`) chỉ có khi `by` = `ocr`, còn lại `null`; **`hao` chưa dùng nó để đếm hay đổi chiều thu/chi**; `txn_ref` không xuất (đổi luật đếm phải hỏi người dùng: CÒN MỞ ở `specs/zalo-thu-chi-real-time.md`). Không có chữ OCR, số tài khoản, tên hay ô chữ; không có giờ tạo file nên không đổi dữ liệu thì không đổi byte; `amount_vnd` là số nguyên, `txn_time` là ISO `+07:00` hoặc `YYYY-MM-DD` hoặc `null`.

- **Ảnh đã che cho `hao`** `redacted-w1/<sha256 ảnh gốc>.jpg` (cùng đích `--reads-target`, để `hao` gửi tin báo thu chi kèm ảnh đã che; việc gửi đó không thuộc spec này): có một file cho mỗi ảnh trong `money-reads.json` mà che được, cùng luật che như trước khi gửi Gemini (số tài khoản/thẻ ≥ 8 chữ số, tên người chuyển/nhận, ≤ 1600 px, JPEG, không EXIF). **Ảnh không che được** (OCR không thấy ô chữ nào) **thì không có file** `redacted`, `hao` chỉ gửi chữ. Tên file là khóa của ảnh gốc nên không đổi; `redacted-w1/*` không còn trong kết quả (nhóm bị bỏ chọn, ảnh rời tập) thì bị dọn trên `hao`. Ảnh đã che nhớ ở `<root>/redacted/` (cạnh `reads/`); sửa luật che thì xóa thư mục này để dựng lại. Chỉ tạo khi bộ xử lý bật và có `--reads-target`. Ảnh đã che được dựng **ở luồng nền** (cùng luồng với OCR và Gemini, thứ tự: đọc OCR, hỏi Gemini, dựng ảnh che), không giải mã hay vẽ gì ở vòng chính; một ảnh chỉ vào `money-reads.json` khi đã có kết luận **và** đã quyết xong chuyện ảnh che (có file hoặc không che được), để `hao` không gửi chữ trước rồi mới có ảnh. `money-reads.json` và `redacted/*` chỉ được dựng và đẩy lại khi có đổi (cờ bẩn) hoặc mỗi giờ, không dựng lại mỗi giây. **Phiên bản luật che nằm trong tên thư mục** (`redacted-w1/`, `w1` = luật danh sách trắng ở Phần 4) **và trong trường `redact` của `money-reads.json`**: đổi luật che thì đổi mã (`redact.RULE`), ảnh đã che theo luật cũ không bao giờ được dùng lại (máy dựng lại theo luật mới ở thư mục mới, các thư mục `redacted-*` cũ trên `hao` bị dọn). `hao` chỉ nên dùng ảnh ở thư mục khớp `redact`.
- **`zalo_agent reread --engine <tên> --since <YYYY-MM-DD>`** đọc lại ảnh trong `members` **và `failed`** có giờ gửi từ ngày đó bằng engine hoặc phiên bản mới (giữ kết quả cũ cạnh bên; cùng engine và phiên bản thì bỏ qua) và chỉ in số đếm.

**Lên `hao`:** `money-reads.json` chỉ mang kết luận (`by`, số tiền, giờ, ngân hàng) và `reads: [{engine, version, amount_vnd, confidence}]` của từng ảnh, đẩy tới thư mục riêng (`--reads-target`) chứ không nhét vào gói chat, để không đụng luật dọn của `bundle`. Không mang chữ OCR, số tài khoản hay tên (giữ B4). Khuôn file ở mục "Bộ xử lý `money_images`" phía trên.

### Phần 4: che thông tin trước khi gửi ra ngoài

Áp cho mọi ảnh sắp gửi Gemini (cả hai đường) **và** cho ảnh đã che `hao` dùng để báo thu chi (xem hợp đồng dữ liệu), làm tại máy, dùng vị trí ô chữ của OCR ở Phần 3.

**Danh sách trắng, hỏng thì che** (sửa 20/11/2026 sau review; thay cách cũ "dò cái nhận ra là nhạy cảm rồi tô đen", vốn rò rỉ mỗi khi OCR bỏ sót hoặc đọc sai một ô: tên xuống dòng, số tài khoản cách đôi, mã QR, nhãn lạ):

- Ảnh ra là **một tấm đen cùng kích thước** với ảnh đã thu nhỏ, rồi chỉ **dán lại từ ảnh gốc** những ô chữ được chứng minh là an toàn. Mọi thứ còn lại (tên, nội dung chuyển khoản, số tài khoản, QR, logo, vùng OCR không thấy chữ, ô OCR đọc sai hay lẫn nhiều thứ) vẫn đen, nên lỗi của OCR chỉ làm ảnh **thiếu chữ**, không làm **lộ chữ**.
- Một ô chữ được dán lại khi **cả bốn điều** cùng đúng:
  1. **Toàn bộ chữ tách được** thành các thành phần trong danh sách trắng, không còn gì khác: (a) **số tiền** có từ 2 nhóm dấu phân cách hàng nghìn trở lên (tối đa 12 chữ số), hoặc 1 nhóm kèm VND/đ/₫ đứng ngay sau, không bắt đầu bằng 0; **số liền không dấu phân cách thì không bao giờ được nhận** (dễ là mã); (b) **nhãn nguyên cụm đã biết**, chỉ là nhãn không kèm giá trị: `Số tiền`, `Thời gian`, `Giao dịch thành công`, `Chuyển khoản thành công`, `Phí giao dịch`, `Mã giao dịch`, `Ngân hàng`, `VND` và tên ngân hàng trong danh sách. Nhãn một từ (`Phí`, `Giờ`, `Ngày`) chỉ nhận khi có dấu `:` ngay sau, vì đứng riêng nó có thể là một dòng của tên (`PHÍ THÀNH CÔNG`); (c) **ngày giờ hợp lệ** (ngày 1-31, tháng 1-12, năm 2000-2100, giờ 0-23, phút và giây 0-59); cùng dấu phân cách `: ; , - –`. Khi so, `Ð`/`ð` đọc là `d`.
  2. Nếu ô có số tiền thì **mọi số tiền trong ô phải bằng đúng số OCR đã đọc** (`amount_vnd`): phí, số dư, số tiền khác giá trị giữ đen; OCR không có `amount_vnd` thì ô số tiền nào cũng giữ đen và ảnh không được gửi. Hệ quả cần biết: Gemini chỉ nhìn thấy số mà OCR đã chọn, nên hai đường Gemini xác nhận hoặc bác số của OCR chứ không tìm ra số khác.
  3. Độ tin cậy của ô ≥ 0,5 và ô **không nghiêng quá 5°** theo 4 góc OCR gửi về (ô nghiêng thì khung chữ nhật lấn sang dòng trên dưới và có thể kéo theo nét chữ của dòng nhạy cảm).
  4. Không chạm (kể cả cách 3 điểm ảnh: `PAD + 1`) một ô không an toàn nào.
- Không dán lại: ô số tiền nằm chung ô với chữ khác (`TK … +<số tiền>VND … ND: <tên>`), nhãn tên/tài khoản (`Tên người nhận`, `Số tài khoản nhận`, `Account name`…) và mọi giá trị đi kèm.
- Thu nhỏ cạnh dài ≤ 1600 px; ảnh ra là JPEG **tạo mới từ điểm ảnh** (không EXIF, XMP, ICC hay chú thích của ảnh gốc).
- **Không che được thì không gửi** ([Q3](#câu-hỏi-đã-chốt)): không có ô chữ nào, ảnh đã đổi kích thước so với lúc đọc, hoặc **không dán lại được ô số tiền nào** thì ảnh đi thẳng sang "cần xem" và không có ảnh đã che.
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

Khuôn đã code (21/11/2026; API sẵn, dòng trên trang để PR giao diện):

- `GET /api/v7/cash-chat` thêm `feedback: {weeks: [...]}`, tuần mới trước. Mỗi tuần gồm:
  - `week` (ISO, ví dụ `2026-W47`), `from`, `to`: thứ Hai–Chủ nhật, giờ VN, theo ngày của khoản;
  - `decided`: số ảnh đã đọc theo `by`;
  - `reviewed`: ảnh người đã chốt số (xác nhận, sửa số) hay loại; chỉ gắn đối tượng thì chưa là chốt;
  - `human_handled`: trong số ảnh đã chốt, ảnh "cần xem";
  - `engines`: `{"<engine>@<phiên bản>": {"right", "wrong"}}`. Số engine đọc trùng số cuối cùng là đúng; ảnh bị loại thì mọi số đọc ra đều sai.
- Ảnh chứng gửi ngay sau tin gõ (trong 2 phút) không tính. Mã engine sai khuôn thì bỏ.
- `summary()` có `thu_chi_anh_tuan`: tuần hiện tại, kèm `at`. Trang Thu chi ghi giá trị này mỗi lần dựng một khoảng có hôm nay, vì tab Máy chạy không có kết nối DB. Giá trị là `null` khi chưa ai mở trang từ lần khởi động API. Chỉ số đếm và mã cố định.

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

**Độ trễ từng chặng** (21/11/2026, `zalo_agent/latency.py`), giây theo đồng hồ máy có Zalo:

| Chặng | Từ → tới | Mẫu |
| --- | --- | --- |
| `zalo` | tin gửi (`timestamp` của Zalo) → live-sync ghi revision có tin đó (`message_publish_epoch_ms`) | mỗi tin **mới thêm** của nhóm đã chọn (không tính tin sửa, tin xóa) |
| `agent` | live-sync ghi revision → bộ xử lý `bundle` bắt đầu dựng phần thêm (nhịp 1 giây, gom 3 giây, chờ lùi sau lỗi) | mỗi lượt đẩy phần thêm có tin Zalo |
| `build` | bắt đầu dựng → dựng xong (đọc `changes-N`, quét `messages.jsonl`, ghi delta, ảnh mới) | như trên |
| `push` | dựng xong → `hao` áp gói (ssh trả về sau khi `export-report.json` đã `mv` vào chỗ) | như trên |
| `total` | live-sync ghi revision → `hao` áp gói | như trên |

Mốc nằm trong `pending.timing` của con trỏ `bundle` nên lượt đẩy lỗi rồi gửi lại vẫn đo từ đúng mốc cũ (gồm cả thời gian chờ); dựng đầy đủ và `--dry-run` không có mẫu. Mẫu giữ 24 giờ (tối đa 2.000 mỗi chặng) ở `<state>/latency.json`, p50/p95 theo hạng gần nhất cho hai cửa sổ: `hour` (60 phút, cho phép kiểm) và `day` (24 giờ, cho tiêu chí bước Chuyển). Số âm do hai đồng hồ lệch thành 0.

**Tốc độ xả hàng chờ đọc ảnh:** `money_images` báo `drain` = số ảnh rời hàng chờ OCR (đọc xong hoặc bỏ sau 3 lần) trong 60 phút qua, lúc hàng chờ từ rỗng sang có ảnh, lúc ảnh gần nhất xong. Chỉ nhớ trong tiến trình: chạy lại agent thì đo lại từ lúc khởi động.

**Ở `hao`:**

- `v7_machine.py` thêm nhóm **"Máy Zalo"** vào tab Máy chạy, mỗi bộ xử lý một dòng, câu thường:
  - "Đang chạy, kịp tin mới";
  - "Zalo chưa mở trên máy Zalo";
  - "Zalo đã mở nhưng chưa đọc được tin, có thể đang chờ đăng nhập (N phút)": `reprobing` từ 5 phút (lúc Zalo vừa mở thì chỉ thoáng qua), như dòng đầu trang Chat và Thu chi;
  - "Chậm 12 phút";
  - "Không nghe máy Zalo từ 08:05";
  - dòng WeChat (WECHAT-01): "Chưa mở trên máy Zalo (12 phút)", "Đang chờ cập nhật, chưa mở lại trên máy Zalo", "Chờ đăng nhập trên máy Zalo, xác nhận trên điện thoại", "Đang chạy, không giải được ảnh".
- `tools/v7_watchdog.py` thêm phép kiểm `zalo`, chỉ trong 7:00–20:00 giờ VN, chỉ khi đã có `status.json` và đã chọn ít nhất một nhóm:
  - `status.json` cũ quá 15 phút → "máy Zalo im lặng";
  - `waiting_for_zalo` quá 15 phút (tính từ `identity_since`) → "Zalo chưa mở";
  - `reprobing` quá 15 phút (tính từ `identity_since`) → "Zalo đã mở nhưng máy chưa đọc được tin: xem Zalo có đang chờ đăng nhập lại không". Thêm 23/11/2026: ngày 22/11 Zalo mở lại 06:03 rồi kẹt như vậy hơn 18 giờ (cửa sổ Zalo ở cỡ màn đăng nhập), mà máy canh, tab Máy chạy và dòng đầu Chat đều coi là ổn;
  - `processors.wechat.app` là `closed`, `update` hay `login` quá 15 phút (tính từ `app_since`) → "WeChat chưa mở / đang chờ cập nhật / đang chờ đăng nhập trên máy Zalo"; `images` = `no_key` quá 15 phút → "WeChat không giải được ảnh". `unknown` không báo;
  - một bộ xử lý chậm quá 15 phút → "chậm";
  - một bộ xử lý hoặc `push` báo `error` liên tục quá 15 phút → "lỗi" kèm mã ngắn;
  - tin mới lên web chậm: `latency.hour.total` có ít nhất 3 lượt và p95 quá 5 phút (mục tiêu 30 giây) → "tin mới lên web chậm". Chặng `zalo` không xét: tin đọc bù sau khi máy tắt qua đêm luôn dài và không do agent;
  - hàng chờ đọc ảnh đứng: còn ảnh chờ, bộ xử lý không báo lỗi (lỗi đã có cảnh báo riêng), và quá 15 phút kể từ mốc muộn hơn trong (`pending_since`, `last_done_at`) không ảnh nào xong → "đọc ảnh chuyển khoản đứng". Bắt được tiến trình OCR chết lặp lại (bộ xử lý nghỉ tới 1 giờ mà không có mã lỗi).
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
- Trường thêm của dòng tin (21/11/2026; gói và delta như nhau; thiếu khóa nghĩa là không có):
  - `card`: mã thẻ suy từ `msgType` và `action` của Zalo: `link`, `missed_call`, `call`, `contact`, `poll`, `bank_card`, `system`. Là phần làm sạch nên dòng tin xóa cũng có;
  - `quote_id`: `message_id` của tin được trích dẫn, cùng hội thoại (từ `quote-index.json` của viewer);
  - `reactions`: `[{"emoji": "<chuỗi 1–16 ký tự>", "count": <số người>}]`, tối đa 20, nhiều người trước. Đếm người, không đếm lần bấm, không ghi ai thả. `emoji` là mã chữ của Zalo (`/-heart`, `/-strong`, `:>`…; trang Chat đổi ra hình). `reactions` của viewer là `{người thả: {loại cảm xúc: số lần bấm}}`, viewer băm cả khóa loại; bộ dựng học khóa → loại từ các tin chỉ có một loại (`last_react_icon` của tin đó), cần ít nhất 3 tin và 90% đồng ý, khóa không học được thì bỏ (đo 22/11/2026: 6 khóa = 6 cảm xúc mặc định của Zalo, đồng ý ≥ 99,8%; trước đó bộ dựng lấy nhầm số lần bấm làm loại nên mọi cảm xúc hiện thành `--b`);
  - `sticker`: sha256 của ảnh sticker trong `media/` (có trong `media.json`);
  - `media` của ghi âm (loại 3, `audio/aac` hoặc `audio/amr`) và video (loại 18, `video/mp4`): bản có trong máy Zalo hoặc bản CDN viewer đã tải sẵn. Bộ dựng không tự tải hai loại này từ CDN;
  - tin xóa không có `quote_id`, `reactions`, `sticker`.
- `users.json` thêm `avatars` (`{<sender_id>: <sha256 trong media/>}`); mỗi mục `conversations.json` thêm `avatar` (sha256 hoặc `null`). Sticker, avatar và bản tải sẵn chỉ được chép khi sha256 khớp chỉ mục của viewer.
- Trích dẫn hay cảm xúc tới sau khi tin đã vào delta (viewer dựng chỉ mục sau `revision.json`) hiện ở lần dựng lại đầy đủ kế tiếp. Con trỏ của agent ghi `format` (hiện 3: cảm xúc đọc đúng loại); agent gặp con trỏ khuôn cũ thì dựng lại đầy đủ ngay.
- `GET /api/v7/zalo/messages` trả thêm cho mỗi tin:
  - `card`;
  - `quote`: `{message_id, found, sender_id, sender_name, type_label, deleted, body_text}` với `body_text` tối đa 120 ký tự, `found: false` khi không đọc được tin gốc;
  - `reactions`;
  - `sticker`: `{id, mime, width, height}`;
  - `sender_avatar`: mã ảnh.

  `GET /api/v7/zalo/conversations` thêm `avatar`. `type_label` theo `card` trước (loại 6 phần lớn là liên kết), rồi theo loại tin (thêm tên cho 25, 26, 27, 52, -27, -1909). Giá trị sai khuôn thì bỏ.
- Trang Chat Zalo hiện các trường này (22/11/2026, `zalo-chat.js`; test ở `test-zalo-chat-browser.js`):
  - avatar tròn ở danh sách hội thoại và ở tin đầu cụm của người khác (tin của mình không có); không có ảnh hay ảnh hỏng (404) thì chữ cái đầu của tên;
  - tin trả lời có khung "↩ tên · đoạn trích" trên nội dung, tin gốc của mình ghi "Mình"; bấm thì cuộn tới tin gốc và tô sáng, tin gốc chưa tải thì mở đúng trang chứa nó (`message=`); `found: false` thì ghi "Trả lời một tin không còn trên web", không bấm được;
  - cảm xúc là chip "biểu tượng + số người" dưới nội dung (một người thì không ghi số);
  - sticker là ảnh tối đa 120px, không ghi "[Sticker]"; ghi âm AAC có nút nghe (`preload="none"`), AMR thì liên kết tải về vì trình duyệt không phát được.
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
- `identity_since`: lúc `identity` đổi sang giá trị hiện tại (agent tự ghi nhận). `hao` đo "Zalo chưa mở" và "Zalo mở mà chưa đọc được" bằng trường này; thiếu thì dùng `revision_at`.
- `live_sync.revision` và `revision_at` là `null` khi agent không đọc được `revision.json`.
- `error` là mã ngắn `[a-z_]{1,40}` hoặc `null`, không chữ tự do.
- `push` là **đường đẩy nhịp tim** (chính file này): `push.error` chỉ phản ánh việc đẩy `status.json`; lỗi đẩy của từng bộ xử lý nằm ở `processors.<tên>.error` (sửa 20/11/2026 sau review PR-3: trước đó mọi `push_failed` của bộ xử lý bị gom vào `push`).
- `error_since` (có ở mỗi bộ xử lý và ở `push`): lúc `error` chuyển từ `null` sang có lỗi. Giữ nguyên mốc khi mã lỗi đổi sang mã khác mà vẫn lỗi; về `null` khi lần chạy kế thành công. Agent nhớ trong `status.json` ở thư mục trạng thái nên chạy lại không mất mốc. `hao` đo "lỗi liên tục quá 15 phút" bằng `now - error_since` (không dùng `last_ok_at`: lỗi ngay từ đầu thì không có `last_ok_at`, còn lỗi thoáng qua sau nhiều giờ im lặng thì báo ngay); thiếu thì coi như mới lỗi.
- Giờ là ISO 8601 có `+07:00`.
- **Thiếu file** (chưa bật agent): tab Máy chạy hiện "Chưa có máy Zalo báo về", máy canh im.
- **File đọc lỗi, `schema` khác 1, hoặc `at` cũ quá 15 phút**: "Không nghe máy Zalo từ …"; máy canh báo theo Phần 6. Không báo lỗi trang.
- Bộ xử lý chưa có thì không có khóa; `hao` chỉ hiện các khóa có mặt.
- `latency` (21/11/2026): `{"hour": {<chặng>: {"n", "p50", "p95"}}, "day": {…}}`, đủ năm chặng `zalo`, `agent`, `build`, `push`, `total` ([định nghĩa](#phần-6-nhịp-tim-từng-chặng)); `n` là số nguyên, `p50` và `p95` là giây (một chữ số thập phân), chưa có mẫu trong cửa sổ thì `n` 0 và hai số kia `null`. `hao` chỉ nhận cửa sổ và chặng đã biết, số hữu hạn từ 0 tới 10⁷; agent cũ chưa có khóa thì phép kiểm độ trễ im.
- `processors.money_images.drain` (21/11/2026): `{"done_1h": <int>, "pending_since": <giờ hoặc null>, "last_done_at": <giờ hoặc null>}`; số ảnh chờ vẫn ở `counts.pending`. Thiếu `pending_since` (agent cũ) thì `hao` không tính hàng chờ đứng.

**Trang hỏi tin mới theo thứ tự đến** (thay `after=<timestamp>` của A3, chỉnh 20/11/2026 sau review PR-2): `GET /api/v7/zalo/messages?conversation=…&since=<token>` trả mọi dòng của hội thoại đến sau `token` (thêm, sửa, xóa) kèm `token` mới. `token` do server cấp (gắn với `bundle_sha256` và vị trí đã đọc trong delta); token của gói cũ thì trả `{reset: true}` và trang tải lại hội thoại. Lý do: khi máy Zalo mở lại sau một đêm, live-sync đọc bù hàng trăm tin có giờ gửi cũ hơn tin mới nhất trang đang hiện; lọc theo giờ gửi sẽ bỏ lỡ chúng.

Thư mục `/srv/v7/zalo-agent` trên `hao` (nhóm `v7app`, `drwxr-s---`) do Claude tạo bằng `sudo` ở bước Chuyển, theo đúng cách của `/srv/v7/zalo-bundle`.

## Nguồn WeChat (WECHAT-01)

Người dùng chốt 20/11/2026 ([`WECHAT-01`](../docs/decisions/wechat-01.md)): WeChat là nguồn thứ hai của agent, chỉ nhóm người dùng chọn (hiện nhóm nội bộ "HTH THU- CHI"). Bật bằng `--wechat` (hoặc `ZALO_AGENT_WECHAT=1`); **mặc định tắt**, nên merge không đổi gì trên máy thật.

**Lựa chọn thiết kế: cùng gói, `hao` không sửa.** Nhóm WeChat là một hội thoại của gói `/srv/v7/zalo-bundle` giống nhóm Zalo; hợp đồng dữ liệu ở trên không đổi một chữ. Bộ xử lý `bundle` có thêm một "overlay" (kho của bộ xử lý `wechat`): dựng đầy đủ xong thì gộp vào thư mục dữ liệu mới, giữa hai lần dựng thì nối vào `messages-delta.jsonl` cùng với tin Zalo, cùng luật "bản mới nhất theo `message_id` thắng". Không dùng gói thứ hai vì `hao` chỉ đọc một gói; không ghi `messages.jsonl` riêng vì hai bộ xử lý ghi chung một gói sẽ lệch con trỏ.

```
WeChat DB ─► wechat_export.py (tiến trình con, venv WeChat, chỉ đọc) ─► JSONL
                                │
        processors/wechat.py: đổi khuôn ─► <root>\wechat\log.jsonl (chỉ nối thêm), users.json, media.json, media\
                                │
        processors/bundle.py (overlay): rebuild ─► gộp vào data-<giờ>\;  delta ─► messages-delta.jsonl
                                │
                       kênh đẩy chung ─► hao:/srv/v7/zalo-bundle
```

**Tiến trình con** `zalo_agent/wechat_export.py`: chạy bằng Python của venv WeChat (`--wechat-python`, mặc định `D:\deibt\wechat-mcp-pilot\.venv\Scripts\python.exe`), nạp `db_adapter` của dự án pilot (`--wechat-pilot`), chỉ dùng `open_database()`; không đọc `private-state`, không in khóa. `groups` liệt kê nhóm (tên, số thành viên); `read` nhận con trỏ từng nhóm trên stdin và in JSONL tin mới hơn con trỏ rồi một dòng `end` có số đếm; `serve` là tiến trình **sống lâu** (mỗi dòng stdin một yêu cầu `read`, giữ `WeChatDB` mở, mở lại sau lỗi). Chỉ đọc nhóm có trong yêu cầu. Lỗi chỉ ra mã ngắn (tên lớp ngoại lệ), không chữ lỗi.

- **Một tiến trình sống lâu, không phải mỗi 10 giây một tiến trình.** Upstream quét bộ nhớ Weixin.exe mỗi lần tạo `WeChatDB` (`extract_master_key()` khi chưa có `cfg_dword`, `extract_keys()` khi có mảnh DB chưa có khóa; `db.py` khoảng dòng 715–728), nên bộ xử lý giữ MỘT tiến trình `serve` (`Session`) và lấy khóa một lần. Mỗi yêu cầu có timeout 60 giây; treo thì giết và tạo lại ở yêu cầu sau; chết giữa chừng thì tạo lại; `open_database()` lỗi thì tiến trình quên DB và mở lại ở yêu cầu sau. Đo 20/11/2026: yêu cầu đầu 2,1 giây (mở DB), các yêu cầu sau khoảng 0,01 giây. Khóa chỉ ở máy: không vào log, repo, `status.json` hay `hao`; stderr của con bị bỏ.
- **Đọc tăng dần, không mất tin.** Có con trỏ thì đọc bằng `get_new_messages(since_seq)` của upstream, nhiều trang (200 tin/trang). Mỗi yêu cầu có **ngân sách 2000 tin mới chia đều các nhóm** (sàn 100/nhóm), cắt đúng ngân sách: yêu cầu luôn xong trong timeout và con trỏ luôn tiến; tồn nhiều thì lượt sau đọc tiếp từ con trỏ (chỉ chậm, không mất). **Lần đầu (chưa có con trỏ) cũng nằm trong ngân sách**: mỗi nhóm chỉ lấy `min(first_limit, phần ngân sách của nhóm)` tin GẦN NHẤT (mặc định tối đa 2000 khi một nhóm; thêm nhiều nhóm cùng lúc thì chia nhỏ hơn). Phần cũ hơn **bỏ có chủ đích**, không đọc dần: lịch sử trước khi bật không cần cho Thu chi, và đọc 5000 tin mỗi nhóm có thể vượt timeout rồi kẹt mãi.
- **Người gửi lấy từ tiền tố của tin (22/11/2026).** Tin nhóm người khác gửi mở đầu bằng `<username>:` + xuống dòng do máy chủ WeChat ghi, cả tin ảnh. `SenderName2Id` chung mà upstream tra (`sender_username`) lệch với WeChat 4 trên máy Zalo: đo trên một nhóm 61 tin, 0 tin khớp tiền tố, 21 tin ra **người khác**, 40 tin không ra ai; bảng `Name2Id` riêng của mảnh DB khớp 60/61. Nên tiền tố thắng khi nó trông chắc là mã người (dạng `wxid_…`, có trong danh bạ, hoặc trùng kết quả tra); không có tiền tố như vậy thì dùng kết quả tra như cũ. Tin `sender_id = 2` vẫn là tin của mình. Kho ghi bằng cách cũ (trạng thái `wechat.json` chưa có `sender_rule` ≥ 2) được sửa một lần: yêu cầu đầu tiên sau khi agent chạy gửi `resend_hours` (400 ngày, tối đa `WINDOW_CAP` tin mỗi nhóm), **riêng, trước lượt ảnh 7 ngày** (không bao giờ chung một yêu cầu: hai lượt nặng chung ngân sách giải ảnh thì lượt 7 ngày bị cắt); tiến trình con phát lại các tin đó với cờ `deep` + `resend` (không giải ảnh); bộ xử lý chỉ ghi lại tin **đã có** mà người gửi đổi (tin ảnh giữ ảnh đang có), không nhập tin mới, và không nhớ `fp` của tin ngoài cửa sổ 6 giờ (để lượt 7 ngày ngay sau còn thử lại ảnh thiếu). Chỉ coi là xong khi lượt đọc thành công không thiếu nhóm nào; quá giờ hai lần thì thôi tới lần chạy agent sau. Tin cũ hơn 1000 tin gần nhất của nhóm và dòng đã xóa giữ người gửi cũ. Số "tin đã nhập" ở tab Máy chạy là số tin khác nhau trong kho, không đếm lần ghi lại một tin.
- **Người gửi luôn được tra lại.** Upstream giữ bộ nhớ đệm người gửi và biệt danh trong tiến trình sống lâu, nên thành viên mới vào nhóm sau khi mở DB chưa có trong đó. Gặp tin MỚI (không xét cửa sổ đọc lại) có người gửi chưa tra ra, tiến trình con đặt lại bộ nhớ đệm (`_sender_id_cache`, `nickname_map(refresh=True)`) một lần mỗi yêu cầu rồi đọc lại nhóm. Người gửi đã làm mới mà vẫn không ra (đã rời nhóm, không có trong `SenderName2Id`) được nhớ và không làm mới lại trong 6 giờ. Lỗi làm mới giữ bảng biệt danh cũ và **không bao giờ làm `serve` bỏ DB** (mở lại DB là upstream quét bộ nhớ Weixin.exe lần nữa). Tên chưa tra được là "Thành viên WeChat", **không bao giờ wxid thô**; tên theo bản MỚI NHẤT (biệt danh có sau cập nhật `users.json` của kho dù dòng không đổi, và "Thành viên WeChat" không đè tên thật đã biết); tên mã thô còn sót từ bản cũ bị làm sạch trước khi vào gói. Lưu ý: tên đổi mà không có dòng mới nào của người đó thì tới lần dựng đầy đủ kế tiếp (mỗi đêm) hao mới thấy. Chữ ký vết của dòng có người gửi, nên dòng gửi thiếu người tự được sửa ở cửa sổ đọc lại.
- **Cửa sổ chỉ gửi khác biệt.** Mỗi bản ghi có dấu vân tay `fp` (loại, chữ đã làm sạch, người gửi, cờ thu hồi); bộ xử lý gửi kèm yêu cầu các `fp` đã có (`known_fp`, nhớ trong bộ nhớ, quên sau cửa sổ + 1 giờ); tiến trình con không gửi lại dòng có `fp` trùng (đếm ở `window_same`). Tin ảnh đã có trong log không bị cửa sổ ghi đè (giữ `media`). Bộ xử lý chỉ báo `poll` khi **thật sự ghi dòng**.
- **Thử lại ảnh còn thiếu.** Mọi tin đều được nhớ `fp`; `retry_at` quyết định lúc quên để tiến trình con gửi lại và giải thử: tin ảnh chưa có ảnh nào (file `.dat` tải chậm, khóa có muộn, đọc file lỗi thoáng qua) sau 1 phút (không mỗi 10 giây, vì upstream duyệt cả cây ảnh của nhóm mỗi lần thử); ảnh thu nhỏ hay tải dở sau 10 phút. File giải ra mà không dùng được (`wxgf` khi máy không có ffmpeg và ảnh thu nhỏ cũng không được, HEIC, video) thì thôi thử. Xóa file `incoming/` lỗi (phần mềm diệt virus đang giữ) không làm mất ảnh đã đọc. Đọc lại mà không có ảnh (cửa sổ, hoặc con trỏ mất lúc không có khóa) không bao giờ đè dòng đã có `media`; con trỏ vẫn tiến.
- **Giữ ảnh tốt nhất.** `tier="best"` của upstream lấy ảnh gốc, rồi bản nén, rồi ảnh thu nhỏ, và không kiểm file đã tải trọn chưa, nên tin vừa tới có thể chỉ có ảnh thu nhỏ hoặc ảnh đang tải dở (đo 22/11: 4/12 ảnh của nhóm cạnh dài 157–210 điểm ảnh, không đọc được số). Hai bản của cùng một ảnh so theo (trọn, số điểm ảnh): ảnh trọn thắng ảnh dở (JPEG có `FF D9` trong 64 byte cuối, PNG có IEND, GIF kết thúc `3B`, WEBP đủ độ dài RIFF), rồi bản nhiều điểm ảnh hơn thắng (đọc từ đầu file JPEG/PNG/GIF/WEBP). Dòng chỉ đổi sang bản tốt hơn, không bao giờ lùi (ảnh gốc bị WeChat dọn thì giữ bản đang có); bản đang có không đọc được cỡ thì chỉ thay bằng ảnh trọn lớn hơn 240×240. Ảnh từ 240×240 trở xuống hoặc chưa trọn được thử lại sau 10 phút trong cửa sổ 6 giờ; lượt 7 ngày cũng thử. Ảnh bị bỏ không lưu vào `media/`. WeChat PC thường chỉ tải bản nén khi nhóm hay ảnh được mở, nên ảnh chưa ai mở có thể ở mãi bản thu nhỏ.
- **Giới hạn thời gian giải ảnh.** Mỗi yêu cầu chỉ giải ảnh trong 25 giây (timeout của bộ xử lý là 60): sau đợt máy tắt lâu, tồn nhiều ảnh không làm yêu cầu quá giờ mãi rồi kẹt cả tin chữ. Hết giờ thì tin mới vẫn được phát (không ảnh, con trỏ vẫn tiến, thử lại sau 1 phút), tin ảnh cửa sổ/7 ngày không phát, dòng `end` báo `image_budget_hit`.
- **Không gắn nhầm ảnh.** Upstream tìm ảnh theo `local_id`, mà `local_id` lặp giữa các mảnh DB; trùng số thì nó lấy tin có `sort_seq` lớn nhất. Tiến trình con chỉ giải khi tin upstream tìm ra có đúng `sort_seq` của tin đang xét; không thì để "chưa đọc được".
- **Lượt ảnh 7 ngày.** Lượt đọc thành công đầu tiên sau khi agent chạy gửi `deep_image_hours` = 168: tiến trình con đọc thêm tối đa 200 tin **ảnh** mới nhất mỗi nhóm trong 7 ngày (cờ `deep`, chung trần `WINDOW_CAP` dòng của cửa sổ) và giải lại; bộ xử lý chỉ dùng để bổ sung hay nâng ảnh cho tin đã có, không nhập tin lần đầu từ phần này. Tin chữ ngoài cửa sổ 6 giờ không đọc lại. Vì `fp` chỉ nằm trong bộ nhớ, lượt này giải lại cả ảnh đã có `media` (một lần mỗi lần agent chạy). Chưa có khóa thì tiến trình con bỏ qua phần này và bộ xử lý giữ lượt 7 ngày tới lượt đầu tiên có khóa (dòng `end` báo `image_keys`). Hết giờ giải ảnh mà vẫn giải được ảnh thì lượt 7 ngày làm tiếp ở lượt sau, và trong lúc đó `fp` được nhớ theo cả 7 ngày để phần đã xong không bị giải lại; không giải thêm được ảnh nào thì thôi. Quá giờ (`child_timeout`) hai lần thì bỏ, để tin chữ không bị kẹt; lỗi khác (mở DB…) không tính. Vậy khóa có muộn, bật ảnh muộn, máy tắt lâu hay sửa khóa rồi chạy lại agent, ảnh 7 ngày gần nhất đều tự bổ sung.
- **Làm sạch nội dung ngay trong tiến trình con**: tin chữ chỉ bỏ tiền tố `<username>:` + xuống dòng của tin nhóm NGƯỜI KHÁC gửi; tin tệp/liên kết/thẻ chỉ ra `<title> · <des>` (bỏ `refermsg`, URL mọi scheme kể cả `weixin://`, thẻ như `<_wc_custom_link_ …>` giữ chữ bên trong, `cdnattachurl`, `aeskey`, `md5`, mọi mã; không dùng bộ phân tích XML để khỏi bom thực thể); tin hệ thống chỉ ra chữ của `replacemsg` hoặc mẫu `template` (bỏ chỗ giữ `${…}`) hoặc văn bản thường, không có chữ thì "[Thông báo WeChat]". Tin chính chủ không bao giờ bị bỏ tiền tố (upstream không có tiền tố cho tin tự gửi; "KH01:" hay "T10:" ở dòng đầu là chữ thật). Biết người gửi: chỉ bỏ khi tiền tố đúng bằng username của họ. Chưa biết người gửi: bỏ khi tiền tố có dạng username WeChat hợp lệ (`wxid_…` hoặc id tùy chỉnh 6–20 ký tự, bắt đầu bằng chữ cái); ngắn hơn hoặc có khoảng trắng ("T10:", "Ghi chú:") thì giữ. Chỗ giữ của mẫu thông báo gồm `${…}` và `$username$`, `$names$`. XML và URL không bao giờ rời tiến trình con; bộ xử lý lọc thêm lần nữa phòng con cũ.
- **Thu hồi.** WeChat 4.x chưa kiểm chứng được cách ghi thu hồi trên máy này (nhóm hiện chưa có tin thu hồi nào), nên dùng cách an toàn cho cả hai khả năng: mỗi lượt con đọc lại **cửa sổ 6 giờ** gần nhất (`--wechat-interval` không đổi; cờ `window` trên dòng) và bộ xử lý so dấu vết (loại, chữ, đã xóa) với bản cuối trong log. Dòng đổi thì phát bản mới ("bản mới nhất thắng"); riêng dòng cũ **biến thành tin hệ thống có `revokemsg` hoặc "撤回"** thì phát dòng xóa đúng hợp đồng (đủ `message_id`, `conversation_id`, `timestamp`, người gửi và loại tin cũ, `body: null`, `deleted: true`) và không bao giờ bị tin hệ thống ghi đè lại. Tin hệ thống thu hồi là dòng mới thì hiện như thông báo thường. Tin đến muộn có `sort_seq` nhỏ hơn con trỏ cũng được lượm từ cửa sổ này. **Giới hạn:** cửa sổ đọc tối đa 1000 dòng mỗi nhóm (`WINDOW_CAP`); nhóm có hơn 1000 tin trong 6 giờ thì phần cũ của cửa sổ không bắt được thu hồi hay sửa.

**Chọn nhóm.** `D:\zalo-agent\wechat-groups.json` (`--wechat-groups`), ngoài repo: `{"schema": 1, "groups": [{"username": "…@chatroom", "name": "…"}]}`. Chỉ `@chatroom` được nhận (chat riêng không bao giờ đọc). Lệnh: `zalo_agent wechat-list`, `wechat-add <tên>` (khớp không phân biệt hoa thường, dấu; mơ hồ thì dừng, không đổi), `wechat-remove <tên>`. Thêm hoặc bỏ nhóm làm đổi băm danh sách chọn của `bundle` nên dựng lại (nhóm bỏ chọn rời gói ngay; kho cục bộ vẫn giữ tin, gói không mang).

**Khuôn dòng tin** (đúng khuôn một dòng `messages.jsonl` của gói, nên `hao` hiện không cần sửa):

| Trường | Giá trị |
| --- | --- |
| `conversation_id` | sha256 hex của `wechat:<username>` (64 hex) |
| `message_id` | sha256 hex của `wechat:<username>:<local_id>:<sort_seq>`. Thêm `sort_seq` so với đề xuất ban đầu vì `local_id` của WeChat 4.x lặp lại giữa các phân mảnh DB (upstream ghi rõ); hai tin không được trùng mã |
| `sender_id` | sha256 hex 32 ký tự của `wechat:sender:<wxid>` (mã WeChat không rời máy); tin của chính chủ: mã cố định, tên "Tôi (WeChat)"; tin hệ thống: `null` |
| `timestamp`, `server_time` | `create_time` × 1000, chuỗi số |
| `message_type` | chữ → 1, ảnh → 2, tệp/liên kết/thẻ → 19, hệ thống → -4; thêm ghi âm → 3, video → 18, vị trí → 17, biểu tượng → 4, cuộc gọi → 6, lì xì → 19, loại lạ → 19 |
| `status` | 2 tin chính chủ gửi, 4 tin nhận |
| `body` | chữ của tin; ghi âm, video, vị trí… chỉ nhãn tiếng Việt ("[Ghi âm WeChat]"); loại lạ "[Tin WeChat loại lạ]" |
| ảnh | giải mã được: `media: [sha256]` + `media/<sha256>.<đuôi>`, `body` "Ảnh WeChat"; chưa được: `body` "Ảnh WeChat (chưa đọc được)" |

`conversations.json`: `display_name` "WeChat · <tên>", `is_group` true. `users.json`: người gửi và tên (biệt danh hoặc ghi chú). `self_user` vẫn là chủ tài khoản Zalo. Tin chính chủ gửi từ WeChat mang `sender_id` = `self_user` lúc gộp vào gói (hao chỉ nhận ra chủ bằng `self_user`; cùng một người nên tên và căn lề đúng); kho cục bộ giữ mã cố định rồi đổi ở bước gộp.

**Con trỏ và idempotent.**

- Con trỏ đọc: `state/wechat.json` theo từng nhóm `{sort_seq, tail}`; `tail` là các `local_id` đã thấy ở đúng `sort_seq` đó (tin cùng `sort_seq` đến muộn vẫn được đọc, tin đã thấy không đọc lại). Con trỏ tiến sau khi tin đã vào kho cục bộ (`log.jsonl`, `fsync`).
- Con trỏ vào gói: `wechat_bytes` trong con trỏ `bundle` (byte của kho đã vào gói), tiến **sau khi đẩy thành công** như `revision`; lượt chết giữa chừng thì `pending` đẩy lại đúng phần đã chuẩn bị. Gửi lại không sinh dòng trùng vì `hao` gộp theo `message_id`.
- Lần đầu đọc tin gần nhất trong ngân sách của yêu cầu; về sau đọc hết phần tồn qua nhiều yêu cầu (xem "Đọc tăng dần").
- `--dry-run` dùng kho riêng `wechat-dry` (không nối `log.jsonl` thật, lượt thật sau đó không có dòng thừa) và không lưu con trỏ.
- Dựng đầy đủ giữ `KEEP_DATA_DIRS = 2` cả khi thư mục dữ liệu trước chỉ có thêm nhóm WeChat còn được chọn (`keep_conversations` của `zalo_web_bundle.build`); nhóm bỏ chọn thì rời ngay.
- Gói không dựng được vì chưa chọn nhóm Zalo nào mà đã chọn nhóm WeChat: `processors.bundle.error` = `no_zalo_group` (không im).

**Chạy nền và lỗi.** Mỗi 10 giây (`--wechat-interval`) bộ xử lý `wechat` gửi một yêu cầu cho tiến trình con sống lâu ở **luồng nền**, timeout 60 giây. Vòng lặp của `bundle` không bao giờ chờ nó. Tiến trình con lỗi thì lùi dần riêng (nhịp × 2 tới 15 phút) với mã `child_failed`, `child_timeout`, `child_missing`, `child_output`, `store_failed`; lỗi này không đụng `bundle`. `wants_work` của `wechat` luôn False; `bundle` tự thấy kho dài ra và xử lý sau lượt gom 3 giây.

**`status.json`.** Khóa `processors.wechat` cùng khuôn `bundle` (`revision` và `lag_revisions` luôn `null`), thêm `messages` (số tin đã nhập kho từ lúc có con trỏ). Chỉ mã và số đếm. Không đổi `schema`.

**App WeChat và khóa ảnh trong `status.json` (22/11/2026).** Đọc DB và khóa ảnh vẫn chạy khi WeChat đã tắt hay chờ đăng nhập (sáng 22/11 WeChat tắt từ khoảng 03:48 tới 06:10, chỉ còn `WeixinUpdate.exe`, mà `processors.wechat` vẫn ổn). Nên `processors.wechat` có thêm:

- `app` + `app_since`: `logged_in`, `login` (màn đăng nhập, "Confirm on Phone"), `closed`, `update` (chỉ còn trình cập nhật), `unknown` (không đọc được). `zalo_agent/wechat_app.py` xem mỗi 30 giây, chỉ đọc danh sách tiến trình (Toolhelp32) và lớp cửa sổ (EnumWindows), khoảng 25 ms; không đọc tiêu đề cửa sổ, không bật lớp trợ năng của WeChat như upstream. Đo trên máy thật: tiến trình chính là `Weixin.exe` có cha không phải `Weixin.exe`; đã đăng nhập thì nó có cửa sổ ẩn lớp `…WxTrayIconMessageWindowClass` và có tiến trình con `Weixin.exe` (wxutility, wxocr, wxpublic, xplayer), cả khi cửa sổ chính thu xuống khay; màn đăng nhập không có cả hai. Nhiều bản WeChat cùng chạy thì một bản đã đăng nhập là `logged_in`.
- `images` + `images_since` (chỉ khi bật ảnh): `ok` hay `no_key`, theo dòng `end` (`image_keys`) của lượt đọc thành công gần nhất. WeChat thoát thì xóa rồi tạo lại các file `kvcomm`, nên thư mục trống trong vài giây. Lúc đó tiến trình đọc vẫn giữ khóa đã kiểm, nên `images` không nháy `no_key`. Khóa chỉ bị suy lại khi trong thư mục có mã khác thay chỗ.
- Mốc `…_since` nhớ trong `<state>/wechat-app.json` và `wechat-images.json`, nên chạy lại agent không mất. `hao` (`v7_machine.zalo`) đổi ra số phút (`app_minutes`, `images_minutes`); mã lạ thành không rõ.

**ĐÃ KIỂM CHỨNG trên máy Zalo (22/11/2026, 16:30–16:39, người dùng thao tác qua phiên điều phối):**

| Người dùng làm | `status.json` | Tab Máy chạy trên `hao` |
| --- | --- | --- |
| Thoát WeChat ở khay | `closed` từ 16:30:51 | "WeChat: Chưa mở trên máy Zalo (1 phút)" |
| Mở lại, để nguyên màn đăng nhập | `login` từ 16:34:53 | "Chờ đăng nhập trên máy Zalo, xác nhận trên điện thoại" |
| Xác nhận trên điện thoại | `logged_in` từ 16:37:56 | "WeChat: Đang chạy, … tin đã nhập" |

- `status.json` đổi trong khoảng 30–60 giây sau mỗi bước, và `hao` đổi theo.
- Lúc đăng nhập lại, WeChat tạo thêm một file `kvcomm` nhưng `images` vẫn `ok`.
- Lúc thoát có một lượt đọc báo `no_key` vài giây. Bản sửa ở bullet `images` trên đã chặn chuyện này.

**Chưa làm (CÒN MỞ):**

- Ảnh còn thiếu cũ hơn 7 ngày (khóa hỏng lâu rồi mới sửa) không tự bổ sung: lượt tự động chỉ phủ cửa sổ 6 giờ và lượt 7 ngày lúc agent chạy; phần cũ hơn phải làm tay.
- Kiểm khóa cần ít nhất hai file `.dat` V2 mở được thành chữ ký ảnh (một, nếu máy chỉ có một file V2). Máy mới chưa có ảnh V2 nào thì chưa có khóa, tới khi có ảnh đầu tiên.
- Chưa thử thật email máy canh cho trạng thái app WeChat hay khóa ảnh. Muốn thử phải để một trạng thái không ổn kéo quá 15 phút trong 7:00–20:00. Máy canh chạy 15 phút một lần nên email tới sau 15–30 phút. Ngày 22/11/2026 người dùng chọn không chờ. Câu email đã có test. Đường gửi email (ping healthchecks.io) dùng chung cho mọi kiểm của máy canh và đã thử thật khi bật `CANH-BAO-01`.

**Đã làm (22/11/2026): đọc ảnh bằng khóa ngoại tuyến** (bản đầu viết ngoài phiên Claude bằng Codex; Claude rà, thêm review độc lập, rồi thêm phần thử lại, giữ ảnh lớn nhất, chặn gắn nhầm ảnh, bộ kiểm khóa nhiều mẫu, chặn đè ảnh khi đọc lại):

- **Khóa ảnh V2 không cần quét bộ nhớ** (`offline_image_key`): 16 ký tự đầu của md5(mã số trong tên `key_<mã>_….statistic` ở `%APPDATA%\Tencent\xwechat\{net,ilink}\kvcomm`, file mới nhất trước + wxid, thử ba dạng bỏ đuôi `_xxxx`). Byte XOR suy từ đuôi ảnh của các mẫu khi ít nhất hai mẫu cùng ra một byte (XOR sai thì ảnh vẫn qua kiểm đầu file nhưng hỏng đuôi), không thì mã & 0xFF. Đúng trên 12 ảnh thật của nhóm: 9 JPEG kết thúc `FF D9`, 3 PNG kết thúc khối `IEND`, nên cả phần AES lẫn phần XOR đều đúng.
- **Kiểm khóa trên nhiều mẫu, nhiều loại ảnh:** khóa chỉ được nhận khi giải khối đầu của ít nhất hai file `.dat` V2 thật thành chữ ký JPEG, PNG, GIF, WEBP hay wxgf (tối đa 24 file của các tháng mới nhất, mỗi file đọc 31 byte đầu và 16 byte cuối; bộ mã AES của repo `wechat_dat.py`, tiến trình con nạp theo đường dẫn vì chạy bằng `-I`). Bộ thử của upstream chỉ nhận JPEG trên một file, nên khi gặp mẫu PNG là loại cả khóa đúng. Khóa đã kiểm được nhớ trong tiến trình `serve` theo (tài khoản, wxid), dùng lại khi mã kvcomm còn hoặc thư mục kvcomm trống (WeChat thoát thì xóa rồi tạo lại file), suy lại khi có mã khác thay chỗ; không ghi ra file, log, `status.json` hay `hao`. Chưa suy được khóa thì 10 phút mới quét lại thư mục ảnh (có mã kvcomm mới thì thử ngay), không quét mỗi 10 giây. Đường `cfg_dword` của upstream lỗi cũng không chặn đường ngoại tuyến.
- **Bật trên `msi`:** task `ZaloAgent` có `--wechat-images` từ 22/11/2026 04:12 với bản đầu. 12 ảnh cũ của nhóm (đọc lúc chưa bật ảnh) được bổ sung bằng một lượt chạy tay ngay trước đó (log có 65 dòng cho 53 tin); từ bản này, lượt 7 ngày làm việc đó tự động.
- **Test** (`tests/test_zalo_agent_wechat.py`): khóa (có mẫu PNG, `ilink`, mã mới nhất trước, thiếu APPDATA, mẫu sai khóa, file khuôn cũ, một khối trùng may mắn không đủ, giữ khóa khi thư mục kvcomm trống nhưng suy lại khi mã khác thay chỗ, thử hụt không quét lại trong 10 phút kể cả khi thứ tự mã đổi, XOR suy từ đuôi ảnh JPEG/PNG và không dùng GIF có đệm, chỉ giải khi đúng tin, `wxgf` lùi về ảnh thu nhỏ); tiến trình con (giải lại ảnh trong cửa sổ, lượt sâu chỉ thêm ảnh, chỉ khi có khóa, có trần, hết giờ giải ảnh thì tin mới vẫn đi); bộ xử lý (tin thiếu ảnh thử lại sau 1 phút, đọc lỗi thì thử lại còn xóa lỗi vẫn giữ ảnh, file không dùng được hay HEIC thì thôi thử, ảnh thu nhỏ thử lại mỗi 10 phút và chỉ thay bằng bản tốt hơn, ảnh dở không thắng ảnh trọn, lượt `deep` không nhập tin mới, lượt 7 ngày giữ tới lượt đầu có khóa, làm tiếp khi hết giờ mà còn tiến, bỏ sau hai lần quá giờ, đọc lại không đè ảnh); đường thật qua `Session` với tiến trình con thật: khóa có muộn thì ảnh cũ được bổ sung không cần chạy lại, ảnh mới giải ngay, tiến trình con chết và được tạo lại vẫn giải được, hai mảnh DB trùng `local_id` không tráo ảnh. Các test của đợt đầu đều đỏ trên bản Codex.

**Đã làm PR-W2 (21/11/2026):**

- **Bộ giải mã `zalo_agent/wechat_dat.py`**, chỉ stdlib, AES-128 tự dựng có vector chuẩn FIPS-197:
  - khuôn cũ XOR một byte: byte suy từ chữ ký ảnh, không cần khóa;
  - khuôn V2 (`07 08 56 32 08 07`, độ dài phần AES và phần XOR, AES-128-ECB đệm PKCS7, giữa để nguyên, đuôi XOR): cần khóa ảnh của máy; byte XOR suy từ đuôi ảnh JPEG, PNG, GIF;
  - sai khóa, file cụt, khuôn lạ đều trả None, không ra ảnh hỏng.

  Test chỉ dùng ảnh và khóa giả (`tests/test_zalo_agent_wechat_dat.py`). `--wechat-images` vẫn mặc định tắt.
- **Tiền tệ ở trang Thu chi:**
  - nhận khoản có đơn vị tệ: tệ, nhân dân tệ, NDT, RMB, CNY, 元, 块, hoặc ¥ trước số;
  - mỗi khoản có `currency` (`CNY`/`VND`) và `amount_cny` (số nguyên tệ; số lẻ hay dạng lạ thì để trống);
  - không đổi ra VND, không lấy số từ ảnh chuyển khoản, `status` là `NO_LEDGER` (sổ khách và Đội xe tính VND);
  - `totals.cny = {thu, chi, ung, count, no_amount}`, tách khỏi mọi tổng VND.
- **Tab Máy chạy và máy canh** liệt kê `wechat`:
  - không theo revision nên chỉ ổn hay lỗi, kèm `messages`;
  - lỗi quá 15 phút thì máy canh báo như các bộ xử lý khác;
  - không có cảnh báo "chậm".
- Nhóm mới vào chỉ có tin từ lúc được thêm; độ phủ mẫu `thu|chi|ứng` chưa đo.

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
| PR-4 | Bộ xử lý `money_images`, chia hai PR xếp chồng: **4a-1** OCR nền 2 luồng, kho kết quả, `reread`, phân loại, `status.json`; **4a-2** che thông tin, Gemini hai đường, kết luận, đẩy kết quả lên `hao` | 3, 4 | Chuyển; PR-2 của Thu chi để có trang hiện | Người dùng đặt khóa API và địa chỉ proxy ở máy có Zalo; thử với `ZALO_AGENT_EXTERNAL=off` trước |
| PR-5 | Số đo tuần theo engine ở trang Thu chi và Máy chạy | 5 | PR-3 của Thu chi, PR-4 | Không |

Quan hệ với spec Thu chi: PR-1 của Thu chi (A1–A4) được thay bởi PR-1, PR-2 và bước Chuyển ở đây. PR-2, PR-3 của Thu chi giữ nguyên. PR-4 của Thu chi chính là PR-4 ở đây.

Review: sonnet medium cho PR-0, PR-2, PR-5; opus cho PR-1, PR-3, PR-4 (con trỏ, quyền trên máy chủ, dữ liệu ra ngoài).

## Tiêu chí nghiệm thu

- [ ] PR-0: sau một ngày chạy, `logs/` dưới 40 MB; heap probe vẫn dò được (watchdog ghi `exit=0`). 22/11/2026: `logs/` 25 MB sau hai ngày (đạt); heap probe chỉ chạy khi poller gắn lại: `exit=0` lúc áp PR-0, hai lần `exit=1` sau đó trùng lúc Zalo PC tắt; còn chờ một lần gắn lại khi Zalo mở ([nhật ký](../docs/deploys/2026-11-20-zalo-agent.md#đo-thêm-22112026)).
- [x] PR-1, test với kho live-sync giả (fixture bịa, không dữ liệu thật), `tests/test_zalo_agent.py` (đối chiếu 22/11/2026):
  - thêm, sửa, xóa tin ra đúng `messages-delta.jsonl` (`test_add_update_delete_become_delta_and_unselected_groups_stay_out`, `test_delta_row_has_exactly_the_shape_build_would_produce`);
  - chết giữa lượt đẩy thì lượt sau gửi lại, `hao` không có dòng trùng (`test_dropped_connection_resends_without_duplicate_lines`, `test_agent_killed_while_sending_resumes_from_pending_without_loss_or_repeat`);
  - thiếu `changes-N` ở giữa, revision lùi hoặc baseline đổi thì dựng lại từ đầu (`test_rebuild_from_scratch_when_cursor_cannot_be_trusted`, ca `missing_changes`, `revision_back`, `baseline_changed`);
  - nhóm chưa chọn không lọt vào gói (cùng ca đầu, `test_revision_without_selected_messages_moves_cursor_and_sends_nothing`);
  - quét 131 MB dưới 2 giây: đo lại 22/11/2026 trên máy có Zalo, `rows_for` với 446 mã không có (buộc quét hết) trên `messages.jsonl` 125,1 MiB: nhanh nhất **0,33 giây** / 3 lượt ([nhật ký](../docs/deploys/2026-11-20-zalo-agent.md#đo-thêm-22112026)).
- [x] PR-1: test của `push.py`: kịch bản máy chủ có `umask 027`, không có `chmod`, file chốt `mv` sau cùng; không đổi gì thì không gửi tar (`PushTest.test_script_has_umask_first_no_chmod_and_final_file_moved_last`, `test_nothing_changed_sends_no_tar_and_changes_send_only_difference`; cả lớp bỏ qua khi máy không có bash + tar).
- [x] PR-1: thử trên `hao` ở thư mục tạm có setgid, đẩy hai lượt: mọi thư mục giữ `drwxr-s---` nhóm `v7app`, `v7app` đọc được; xóa thư mục tạm. Ghi nhật ký (20/11/2026, ba lượt ở `/srv/v7/zalo-agent-test`: [nhật ký](../docs/deploys/2026-11-20-zalo-agent.md#trên-hao)).
- [x] PR-2: `tests/test_v7_zalo_chat.py`: phần thêm có bản sửa và dòng xóa thì hiện bản mới nhất, tin xóa hiện giống bản dựng đầy đủ; ảnh và người gửi mới trong `media.json`, `users.json` hiện được; `since=` trả cả tin tới muộn (giờ gửi cũ hơn), tin sửa, tin xóa; token gói cũ thì `reset` (`ZaloDeltaTest`: `test_edit_replaces_and_deleted_line_shows_like_a_full_build`, `test_media_and_users_replaced_in_place_reach_new_delta_messages`, `test_since_returns_everything_that_arrived_after_the_token_even_old_edits_and_late_messages`, `test_since_asks_for_a_reload_when_the_bundle_was_rebuilt`).
- [x] PR-2: `tests/test_v7_watchdog.py`: `status.json` cũ 16 phút lúc 10:00 thì báo, lúc 22:00 thì không; `waiting_for_zalo` 16 phút thì báo; chưa chọn nhóm nào thì không kiểm (`ZaloTests`: `test_silent_status_reports_during_work_hours_only`, `test_waiting_for_zalo_reports_after_15_minutes`, `test_no_selected_group_means_no_check`). Thêm 23/11/2026: `reprobing` 236 phút thì báo, 14 phút hay ngoài giờ thì không (`test_zalo_open_but_unreadable_reports_after_15_minutes`); tab Máy chạy và dòng đầu Chat/Thu chi có ca `reprobing` trong `test-may-chay-model.js`, `test-cong-no-format.js`, `test-zalo-chat-browser.js`.
- [x] PR-2: test trình duyệt tab Máy chạy: nhóm "Máy Zalo" hiện bốn trạng thái bằng câu thường, ở 1280×720 và 390px (`test-may-chay-browser.js`: ca "Máy chạy (1280×720)…" và "Máy chạy (390px)…", cùng tên "nhóm "Máy Zalo" hiện bốn trạng thái bằng câu thường").
- [x] Chịu lỗi, test với kho live-sync và máy chủ bịa (21/11/2026), mỗi ca kiểm không mất tin, không gói dở (file chốt luôn trỏ tới thư mục đủ file, delta dài ít nhất `delta_bytes`), con trỏ đuổi kịp:
  - agent bị giết lúc gửi tar và sau khi máy chủ đã áp: chạy lại thì đẩy nốt `pending`, không tin nào hai lần;
  - ssh đứt giữa tar (bash + tar thật): máy chủ giữ nguyên file chốt cũ, không sót thư mục tạm, lượt sau đẩy đủ;
  - ổ đĩa `hao` đầy: hai lượt `push_failed`, gói cũ nguyên, có chỗ thì đẩy đủ;
  - Zalo mở lại sau nhiều giờ: một lượt delta mang tin tới muộn (giờ gửi cũ hơn), tin sửa, tin xóa; `since=` của trang đang mở nhận đủ.

  Tên test: `test_agent_killed_while_sending_resumes_from_pending_without_loss_or_repeat`, `test_ssh_cut_in_the_middle_of_the_tar_leaves_the_old_bundle_whole`, `test_full_disk_on_hao_keeps_pending_and_the_old_bundle_until_space_returns`, `test_zalo_reopened_after_hours_delivers_late_messages_in_one_delta_and_since_sees_them`.
- [ ] Chuyển: một ngày làm việc trên máy thật, tin mới lên web trong **30 giây** (p95, từ `revision_at` tới `status.json` trên `hao`); khởi động lại máy rồi mở Zalo thì agent tự đuổi kịp, không mất tin. Ghi số trong nhật ký.
- [x] PR-3, test với snapshot, PDF và máy chủ bịa (`tests/test_zalo_agent_insurance.py`): bản gọn trùng từng byte với golden của code gốc; PDF mới gửi, PDF cũ dọn, PDF mất ở máy thì giữ trên máy chủ; 0 dòng không đẩy; snapshot không đổi thì không gửi tar; lỗi đẩy thì `error_since` có mốc; băm PDF theo cache; `--dry-run` không lưu gì.
- [x] PR-3, ở bước bật: task bảo hiểm không còn phụ thuộc worktree, chạy cả khi dùng pin; mọi giấy hiện như trước trên `hao` (hỏi người dùng trước khi tắt `ZaloInsurancePush`). 20/11/2026: người dùng bấm "Đồng ý bật"; bộ xử lý `insurance` chạy trong task `ZaloAgent` (code từ checkout `main`, chạy cả khi dùng pin), `ZaloInsurancePush` tắt không xóa; trên `hao` 22 dòng, 22 PDF, một giấy qua web 200 và băm khớp ([nhật ký](../docs/deploys/2026-11-20-zalo-agent.md#bật-đường-bảo-hiểm-trong-agent-1239)).
- [x] PR-4, ảnh tổng hợp bằng PIL (số tài khoản giả), đối chiếu 22/11/2026:
  - ô có dãy ≥ 8 chữ số bị tô đen, số tiền không bị che (`RedactPixelsTest.test_everything_sensitive_is_black_and_only_amount_labels_time_bank_survive`: luật thật chặt hơn, che mọi ô ngoài danh sách được giữ; dãy số liền chỉ kiểm ở mức chữ trong `RedactWhitelistTest`; cần Pillow nên chỉ chạy ở job Windows);
  - OCR không thấy chữ thì không gửi (`ExternalTest.test_image_where_ocr_finds_no_text_at_all_is_never_sent`, thêm 22/11/2026; `redact.redact` trả None khi không có ô chữ);
  - `ZALO_AGENT_EXTERNAL=off` thì không có kết nối ra ngoài (`test_external_off_sends_nothing_and_opens_no_connection_unsure_goes_to_human`, mức cấu hình ở `GeminiTest`);
  - cùng engine và phiên bản thì không đọc lại (`test_same_engine_and_version_is_not_read_again_new_version_reads_and_keeps_the_old_file`);
  - kết quả Gemini sai khuôn bị loại (`GeminiTest.test_answer_must_have_exactly_the_agreed_shape`).
- [x] PR-4: trên 20 ảnh của P0, OCR với ngưỡng T vẫn đúng 20/20; số ảnh phải gửi Gemini được báo trong chat (20/11/2026: 20/20 khớp, T = 0,6 để 2/20 ảnh sang Gemini; số đo ở [Phần 3](#phần-3-kết-quả-đọc-ảnh-có-nguồn-gốc)).
- [x] PR-5: với dòng xác nhận giả, số đo tuần đúng theo engine; không chữ tự do nào vào `summary()` (21/11/2026: `FeedbackTests` ở `tests/test_v7_cash_chat.py`, `test_summary_carries_this_weeks_image_feedback_as_codes_and_counts` ở `tests/test_v7_machine.py`).
- [x] Đo độ trễ từng chặng và tốc độ xả hàng chờ OCR (21/11/2026), test với dữ liệu bịa: `LatencyTest` (p50/p95 hạng gần nhất, hai cửa sổ, mẫu quá 24 giờ bị bỏ, sống qua lần chạy lại, số lạ bị bỏ, `--dry-run` không ghi file); `test_delta_push_measures_each_stage_and_a_retry_counts_the_wait` (năm chặng đúng từng mốc, tin sửa và nhóm chưa chọn không là mẫu `zalo`, đẩy lỗi chưa có mẫu, gửi lại tính cả thời gian chờ); `test_drain_counts_images_leaving_the_queue_and_when_the_queue_filled`; phía `hao`: `test_zalo_latency_and_ocr_drain_are_numbers_only`, `test_slow_delivery_p95_and_stalled_image_queue` (p95 quá 5 phút với ≥ 3 lượt thì báo, ít lượt hay đúng ngưỡng thì không; hàng chờ đứng 20 phút thì báo, đang lỗi thì chỉ báo lỗi).
- [x] Mở rộng hợp đồng gói chat (21/11/2026), test với kho viewer bịa:
  - `test_extras_quote_reactions_sticker_avatar_voice_and_cards`: trích dẫn; cảm xúc đếm theo người; sticker và avatar chép khi sha256 khớp; ghi âm lấy bản viewer tải sẵn, không tải CDN; mã thẻ; tin xóa không có ba trường; chỉ mục hỏng thì gói vẫn dựng; không lộ URL hay băm URL;
  - `test_delta_carries_quote_reactions_sticker_avatar_and_voice_like_a_full_build`: delta giống hệt bản dựng đầy đủ; người gửi mới mang avatar;
  - ca `format_changed`: con trỏ khuôn cũ thì dựng lại ngay;
  - phía `hao`: `test_extras_reach_the_api_and_bad_values_are_dropped`.
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
- [`WECHAT-01`](../docs/decisions/wechat-01.md): nguồn WeChat thứ hai, chỉ nhóm người dùng chọn.

## Ngoài phạm vi

- **Máy luôn bật.** Mọi thứ vẫn phụ thuộc một laptop có lúc tắt. Một máy mini luôn bật chỉ chạy Zalo PC (Q5 của Thu chi) là khuyến nghị, không thuộc spec này.
- DB, hàng đợi, dịch vụ mới; route ghi mới trên `hao`.
- Bot trả lời trong nhóm, nối ngân hàng. (WeChat: có, như nguồn thứ hai, xem [Nguồn WeChat](#nguồn-wechat-wechat-01).)
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
