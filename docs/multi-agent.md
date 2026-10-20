# Cộng tác nhiều agent

ĐỀ XUẤT ngày 16/10/2026, người dùng đồng ý dựng khung trong chat. Đã chạy thử hai spec nhỏ trên fixture: Codex ([allocation-edge-tests](../specs/allocation-edge-tests.md), chỉ test) và Gemini ([table-scroll-keyboard](../specs/table-scroll-keyboard.md), sửa a11y); cả hai ĐẠT ở vòng đầu. Agy đã kết nối Penpot MCP và gọi được công cụ đọc. Chưa thử task backend, vòng sửa CẦN SỬA, hay một lần Gemini dựng mockup thật. Bổ sung cho [quy trình phát triển](development.md), không thay lan can ở [AGENTS.md](../AGENTS.md).

## Vai trò

| Agent | Vai trò | Gọi bằng |
|---|---|---|
| Claude | Điều phối, chốt spec, review chốt (chỉ sau khi Codex ĐẠT). Chỉ có Read/Grep/Glob, không chạy lệnh hay sửa file; script hủy kết quả nếu worktree bị đổi | `claude -p --model <Review> --tools Read,Grep,Glob --output-format json` |
| Codex | Backend/test theo spec hẹp; hay làm quá tay → spec bắt buộc có "Phạm vi agent". Review sơ bộ mọi thay đổi và mockup | `codex exec` (sandbox `workspace-write`; review: `read-only --json`) |
| Gemini | Phụ trách chính mockup Penpot (qua MCP `penpot`) và frontend/preview theo [quy trình frontend](development.md#quy-trình-frontend). Headless chỉ được dùng MCP Penpot, không lệnh terminal; test do script chạy | `agy -p --mode accept-edits --sandbox` (đọc prompt từ file log) |
| Người dùng | Duyệt spec và mockup Penpot, commit/merge/push, deploy, mọi thao tác dữ liệu thật | — |

Tất cả đọc chung `AGENTS.md`: Codex trực tiếp, Claude qua `CLAUDE.md`, Gemini qua `GEMINI.md` và prompt của script.

## Kênh giao tiếp

Không dùng kênh riêng; trao đổi qua Git và log:

1. **Spec** (`specs/…`, từ [mẫu](../specs/_template.md)) là đầu vào. Mục "Phạm vi agent" ghi agent, file được sửa, ngân sách diff, lệnh kiểm, điều cấm.
2. **Nhánh/worktree riêng** `<agent>/<tên-spec>` cạnh repo; một phạm vi một agent ghi.
3. **Lệnh kiểm do script chạy** ngoài sandbox agent; mã thoát là bằng chứng, báo cáo agent chỉ là lời tự khai.
4. **Review hai tầng** (người dùng chọn 16/10/2026 để giảm token Claude): Codex review sơ bộ; chỉ khi Codex ĐẠT thì Claude review chốt. Mỗi review kết thúc bằng `Kết luận: ĐẠT | CẦN SỬA | CHẶN`. CẦN SỬA (của bất kỳ ai) → phát hiện quay lại agent, tối đa 2 vòng; CHẶN → dừng chờ người. Hết vòng mà Codex vẫn CẦN SỬA thì dừng, Claude không chạy.
   - Script chép sẵn diff (gồm file chưa track), kết quả Lệnh kiểm, spec, báo cáo agent vào prompt; reviewer không chạy lại test, không duyệt toàn repo.
   - Từ lần thứ hai, mỗi reviewer chỉ nhận phần đổi từ lần review trước của chính nó cùng review đó.
   - Model Claude theo dòng `- Review: <model> [effort]` trong "Phạm vi agent" (ví dụ `sonnet medium`); thiếu dòng thì dùng `opus`. Dùng `opus` cho đường ghi tiền, phân bổ, opening, quyền; `sonnet` cho test, tài liệu, a11y, UI nhỏ.
   - Token từng lần review (Codex và Claude, kèm chi phí ước tính của Claude) ghi vào `usage.tsv` trong thư mục log.
5. **Diff/PR** là đầu ra; người dùng commit/mở PR.

## Luồng frontend với Gemini

Theo đủ 8 bước [quy trình frontend](development.md#quy-trình-frontend) và [hướng dẫn UX](ux-guidelines.md):

1. **Bước 1–2, 5 (Claude cùng người dùng):** viết spec `Agent: gemini`, `Mockup: CHỜ DUYỆT` với mục "Người dùng và luồng" (hỏi người dùng điều chưa biết, không giả định), "Đối chiếu dữ liệu và code hiện có", "Giao tiếp frontend–backend". Script từ chối bước mockup khi spec thiếu hai mục đầu.
2. **Bước 3:** `-Step mockup` tự chạy cả vòng:
   - kiểm Penpot sẵn sàng (agy đọc tên file đang mở; tab bị tạm dừng thì dừng sau vài giây thay vì 20 phút);
   - Gemini vẽ trên Penpot theo luồng, số liệu của spec, hướng dẫn UX, góp ý và review trước; page chỉ có board màn hình và một board ghi chú; không sửa repo;
   - agy xuất `boards.json` (chữ, cỡ chữ, trong/ngoài màn hình) và ảnh PNG từng board;
   - script kiểm luật đo được (cỡ chữ, tiền viết tắt, từ kỹ thuật trên màn hình);
   - Codex review sơ bộ với ảnh đính kèm + chữ theo checklist UX; Codex ĐẠT thì Claude review chốt, đọc chữ trước và chỉ mở ảnh khi cần. Kết luận ĐẠT / CẦN SỬA / CHẶN; CẦN SỬA thì Gemini sửa lại, tối đa 2 vòng.
3. **Bước 4 (người dùng):** chỉ duyệt khi review ĐẠT. Cần chỉnh thì ghi góp ý vào `feedback.md` trong thư mục log của nhánh, chạy lại `-Step mockup`; điều đã chốt thì ghi vào spec. Đạt thì lưu phiên bản có tên trong Penpot (History) và ghi `Mockup: ĐÃ DUYỆT <link page> · phiên bản "<tên>" · <người> · <ngày>`. Script không cho vẽ đè sau khi đã duyệt.
4. **Bước 6–7:** chạy không `-Step` — Gemini code theo đúng phiên bản đã duyệt → script chạy test và chụp giao diện thật theo mục "Ảnh chụp giao diện" → Codex so ảnh với mockup và bản trước → Claude review chốt. Script từ chối code khi chưa có dòng `ĐÃ DUYỆT … phiên bản "…"` hoặc `miễn: <lý do>` (sửa nhỏ không đổi luồng).
5. **Bước 8 (người dùng):** tự đi hết luồng trên bản thử và xác nhận trước khi commit/merge; review của agent không thay bước này.

## Ảnh chụp giao diện

ĐỀ XUẤT ngày 16/10/2026 theo yêu cầu người dùng: reviewer phải thấy giao diện thật đã render, không chỉ đọc diff. Bắt buộc với spec `Agent: gemini` (script từ chối bước code/review khi thiếu); spec khác khai báo nếu có giao diện.

- **Khai báo:** mục `## Ảnh chụp giao diện` trong spec, một khối ```` ```json ```` gồm `page` (đường dẫn từ gốc repo), `viewports` (mặc định `[[1280, 720]]`, khớp màn hình thật của người dùng đã chốt ở [ux-guidelines](ux-guidelines.md) ngày 18/10/2026; spec cũ đã ghi `[[1500, 1000]]` trong kịch bản riêng giữ nguyên) và `states`. Mỗi trạng thái có `name` (a-z, 0-9, -), `board` (tên board mockup tương ứng), `note`, `shot` (selector vùng chụp; bỏ trống = cả khung, thêm `"fullPage": true` nếu cần cả trang) và `steps`.
- **Bước:** `click`, `focus`, `hover`, `check`, `uncheck`, `waitFor` (selector); `fill`, `select`, `paste` (`[selector, giá trị]`, `paste` dán TSV như test browser); `press` (phím, kèm `"times"`). Selector chạy strict: khớp 0 hoặc nhiều phần tử là lỗi. Trạng thái nên trùng danh sách "Trạng thái cần có trên mockup"; Claude viết cùng spec ở bước 5 và thử bằng `-Step capture`.
- **Chụp:** `scripts/ui-capture.js` luôn chạy từ checkout chính (agent không sửa được công cụ), bằng Playwright của repo. Bản TRƯỚC lấy thư mục trang tại điểm rẽ nhánh (`git archive`); bản SAU là worktree. Ảnh và kết quả ở `ui-before/`, `ui-after/` trong thư mục log (`checks.md`, `report.json`).
- **Đo tự động** trên giao diện đã render, trong vùng `shot`: lỗi JS, bước không bấm được, cỡ chữ < 12px, tương phản dưới WCAG AA (ước tính trên nền đặc gần nhất), vùng bấm < 40px, từ kỹ thuật/tiền viết tắt, cuộn ngang, phần tử đang focus không có viền. Bản SAU so với TRƯỚC: chỉ phát hiện MỚI được nêu chi tiết; lỗi có sẵn được gom một dòng để không đổ cho lần sửa này.
- **Review:** Codex nhận đính kèm ảnh theo thứ tự mockup → SAU → TRƯỚC (chỉ trạng thái đạt được trước thay đổi) cùng kết quả đo, so từng trạng thái với board mockup và với bản trước. Claude nhận kết quả đo và đường dẫn ảnh, chỉ mở ảnh khi có phát hiện MỚI hoặc cần chốt. Bước mockup cũng chụp app hiện tại để Codex/Claude kiểm mockup giữ đúng tên cột, nút, cỡ chữ, tỉ lệ; Gemini được chỉ đường dẫn ảnh này khi vẽ.
- **Giới hạn:** chạy trên fixture HTML tĩnh, chưa là kiểm tích hợp hay bước 8 của người dùng. Đo tương phản bỏ qua ảnh nền/gradient; vùng bấm đo theo hộp phần tử, không tính nhãn bao quanh. Ảnh mockup lấy từ lần xuất mới nhất trong log; khớp phiên bản đã duyệt vì sau duyệt script không cho vẽ đè, nhưng sửa tay trên Penpot sau đó thì script không biết.

## Chạy

```powershell
.\scripts\agent-run.ps1 -Spec specs\<x>.md -Step mockup   # Gemini vẽ mockup Penpot, dừng chờ duyệt
.\scripts\agent-run.ps1 -Spec specs\<x>.md -DryRun        # xem agent, phạm vi, lệnh kiểm, nhánh
.\scripts\agent-run.ps1 -Spec specs\<x>.md                # agent → kiểm → review → sửa (≤2 vòng)
.\scripts\agent-run.ps1 -Spec specs\<x>.md -Step check    # chỉ kiểm phạm vi + lệnh kiểm + chụp UI
.\scripts\agent-run.ps1 -Spec specs\<x>.md -Step capture  # thử kịch bản chụp khi viết spec (không gọi agent/reviewer)
.\scripts\agent-run.ps1 -Spec specs\<x>.md -Step review   # kiểm + review một lần, không vòng sửa
```

Mã thoát: 0 ĐẠT (cả Codex và Claude), 2 CẦN SỬA/không rõ, 3 CHẶN. Worktree ở `../worktrees/`, log (prompt từng vòng, báo cáo agent, `scope-check.txt`, `checks.md`, `review-codex-N.md`, `review-claude-N.md`, `review.md` = lần cuối, `usage.tsv`, `ui-before/`, `ui-after/`) ở `../worktrees/_logs/`, ngoài repo. Script không commit, push hay merge.

## Giới hạn

- Kiểm phạm vi là cảnh báo, không chặn; reviewer và người dùng vẫn đọc toàn bộ diff.
- Worktree dùng `.venv`, `node_modules`, browser Playwright của checkout chính qua `{python}`, `NODE_PATH`, `PLAYWRIGHT_BROWSERS_PATH`; không tạo junction. Trước merge vẫn chạy lại ở clone sạch/CI theo [quy trình](development.md).
- Vòng sửa gọi agent mới với prompt gồm phát hiện review, không nối phiên cũ.
- Agent không trả báo cáo (bị chặn quyền, hết 20 phút với agy) thì script dừng báo lỗi, không đi tiếp sang review.
- Penpot MCP chạy qua plugin trong tab trình duyệt, cần heartbeat liên tục. Mở Penpot bằng `.\scripts\open-penpot.ps1` (Chrome hồ sơ riêng, tắt tạm dừng tab khi cửa sổ bị che/chạy nền), mở đúng file và plugin MCP; chỉ để một tab Penpot có plugin kết nối. Cửa sổ Chrome thường hoặc browser pane của Claude bị tạm dừng sau khoảng 30 giây khi bị che. Cấu hình máy (ngoài repo): server `penpot` trong `~/.gemini/config/mcp_config.json`, quyền `mcp(penpot)` và `read_url(localhost:9001)` (xuất PNG, người dùng cho phép 16/10/2026) trong `~/.gemini/antigravity-cli/settings.json`; URL chứa token, không chép vào repo. Codex vẫn còn cấu hình Penpot riêng nhưng không là agent phụ trách.
- Cổng mockup chỉ kiểm dòng chữ trong spec, không xác minh được người dùng đã thật sự duyệt trên Penpot.
- Toàn quyền của reviewer chỉ trong worktree tạm; không thay lan can `AGENTS.md` (không push, deploy, DDL, chạm Sheet/DB thật).
- Review của agent không là ĐÃ KIỂM CHỨNG nghiệp vụ, không cấp quyền ghi tiền hoặc deploy.
- Sandbox Codex trên Windows: cấu hình chung `[windows] sandbox = "elevated"` làm mọi lệnh shell lỗi `helper_unknown_error: setup refresh had errors` (bước setup phải đổi ACL trên `node_repl.exe` của runtime `cua_node`, file đang chạy nên os error 32). Script gọi Codex với `-c windows.sandbox=unelevated`; kiểm 17/10/2026: read-only vẫn từ chối ghi, workspace-write ghi được trong worktree, chạy được Python `.venv`. Cấu hình chung của Codex desktop không đổi. Chạy `codex exec` tay thì thêm cùng cờ.
- Codex ĐẠT không thay review chốt của Claude. Khi Agent: codex, Codex review chính code mình viết (dễ thiên vị), nên tầng Claude vẫn bắt buộc. Claude không chạy lệnh; nghi ngờ cần chạy thử thì ghi vào phát hiện để người dùng hoặc vòng sau kiểm.
