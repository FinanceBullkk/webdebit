// Luật nghiệp vụ đã chốt, viết dưới dạng check máy chạy được.
//
// Lý do tồn tại: luật nghiệp vụ của dự án nằm trong `docs/business-rules.md` và
// `docs/decisions.md`. Luật chỉ nằm trong tài liệu thì mỗi vòng review lại phải
// soi bằng mắt — dễ sót, tốn thời gian của cả người và agent. Luật nào máy kiểm
// được thì phải fail ngay ở máy, trước khi diff đến tay reviewer.
//
// Mỗi luật ở đây phải truy được về một dòng ĐÃ CHỐT trong sổ quyết định. Phần
// CÒN MỞ không biến thành check: một check sai còn tệ hơn không có check, vì nó
// biến lựa chọn kỹ thuật thành chính sách mà người dùng chưa duyệt.
//
// Module này chỉ thuần tính toán: `runRules(root)` nhận gốc repo, trả về danh
// sách vi phạm theo từng luật. Phần in ra và mã thoát nằm ở
// `check-business-rules.js`, để test gọi được trực tiếp trên thư mục fixture.

const fs = require("node:fs");
const path = require("node:path");

const SKIP_DIRS = new Set([
  "node_modules", ".venv", ".git", "__pycache__",
  ".playwright-browsers", "test-results", ".pytest_cache",
]);

// Duyệt cây file một lần, các luật cùng dùng lại kết quả này.
function collect(root) {
  const out = [];
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) walk(path.join(dir, entry.name));
        continue;
      }
      const ext = path.extname(entry.name);
      if (![".sql", ".py", ".js"].includes(ext)) continue;
      const abs = path.join(dir, entry.name);
      out.push({
        rel: path.relative(root, abs).split(path.sep).join("/"),
        ext,
        text: fs.readFileSync(abs, "utf-8"),
      });
    }
  };
  walk(root);
  return out;
}

// Test là nơi được phép dựng dữ liệu vi phạm để chứng minh guard hoạt động, nên
// luật tiền/ngày không áp vào test hay script công cụ. Việc guard có mặt hay
// không (FUTURE-01, TRIP-DATE-01) thì vẫn kiểm trên mọi file SQL.
const isTest = (f) =>
  /(^|\/)tests?\//.test(f.rel) ||
  /(^|\/)(test[-_][^/]*|[^/]*[-_]test)\.(py|js)$/.test(f.rel) ||
  /(^|\/)scripts\//.test(f.rel);

const lines = (text) => text.split(/\r?\n/);

function stripComment(line, ext) {
  if (ext === ".py") return line.replace(/#.*$/, "");
  if (ext === ".js") return line.replace(/\/\/.*$/, "");
  return line.replace(/--.*$/, "");
}

// ---------------------------------------------------------------------------
// VND-01 — cột tiền phải là số nguyên chính xác
//
// Nguồn: `docs/business-rules.md` ô "Tiền chưa rõ" — "VND nguyên chính xác,
// không làm tròn để ép khớp"; AGENTS.md nhắc lại. Số thập phân ở cột tiền mở
// đường cho sai số làm tròn mà không ai thấy, nên đây là lỗi, không phải style.
//
// Kiểm trong CREATE TABLE: mọi cột tên `*_vnd` phải là numeric/decimal với
// scale bằng 0, hoặc integer/bigint/smallint. Kiểu dấu phẩy động (real, double
// precision, float, money) và numeric không khai scale đều bị chặn.
// Chỉ lấy đúng phần kiểu: một từ, cộng `precision` cho `double precision`, cộng
// (p[,s]) nếu có. Không ăn luôn `NOT NULL`/`CHECK (...)` phía sau.
const VND_COLUMN = /^\s*([a-z_][a-z0-9_]*_vnd)\s+([a-z]+(?:\s+precision)?)\s*(\(\s*\d+\s*(?:,\s*\d+\s*)?\))?/i;

function ruleVndSqlColumns(files) {
  const found = [];
  for (const f of files.filter((file) => file.ext === ".sql")) {
    let inTable = false;
    lines(f.text).forEach((line, i) => {
      if (/^\s*CREATE\s+TABLE\b/i.test(line)) inTable = true;
      else if (inTable && /^\s*\)\s*;/.test(line)) inTable = false;
      if (!inTable) return;

      const m = line.match(VND_COLUMN);
      if (!m) return;
      const column = m[1];
      const type = (m[2] + (m[3] || "")).toLowerCase().replace(/\s+/g, " ").trim();

      if (/^(smallint|integer|int|bigint)$/.test(type)) return;
      const scaled = type.match(/^(numeric|decimal)\s*\(\s*\d+\s*,\s*(\d+)\s*\)$/);
      if (scaled) {
        if (Number(scaled[2]) === 0) return;
        found.push({
          file: f.rel, line: i + 1,
          detail: `cột tiền \`${column}\` khai báo \`${type}\` — scale ${scaled[2]} cho phép số thập phân; dùng \`numeric(20,0)\``,
        });
        return;
      }
      found.push({
        file: f.rel, line: i + 1,
        detail: `cột tiền \`${column}\` khai báo \`${type}\` — VND là số nguyên chính xác; dùng \`numeric(20,0)\``,
      });
    });
  }
  return found;
}

// ---------------------------------------------------------------------------
// VND-02 — không dùng số thực ở đường tính tiền
//
// Cùng nguồn với VND-01. Python dùng Decimal, JS dùng BigInt; cả hai đã là cách
// làm hiện hành trong repo. Chặn các cấu trúc kéo tiền về float: `float()`,
// `parseFloat`, `toFixed`, và hằng số có dấu thập phân gán cho tên tiền.
const FLOAT_CALLS = [
  { ext: ".py", re: /\bfloat\s*\(/, what: "`float()`", fix: "dùng `Decimal` (xem `pilot/reconcile.py`)" },
  { ext: ".js", re: /\b(?:Number\.)?parseFloat\s*\(/, what: "`parseFloat`", fix: "dùng `BigInt` (xem `preview/so-khach-v7-model.js`)" },
  { ext: ".js", re: /\.toFixed\s*\(/, what: "`toFixed`", fix: "định dạng tiền từ BigInt, không qua số thực" },
];
const MONEY_DECIMAL_LITERAL = /\b([a-zA-Z_][a-zA-Z0-9_]*(?:_vnd|Vnd|VND))\s*(?:[-+*/]?=)\s*-?\d+\.\d/;

function ruleNoFloatMoney(files) {
  const found = [];
  for (const f of files) {
    if (isTest(f) || ![".py", ".js"].includes(f.ext)) continue;
    lines(f.text).forEach((line, i) => {
      const code = stripComment(line, f.ext);
      for (const probe of FLOAT_CALLS) {
        if (probe.ext === f.ext && probe.re.test(code)) {
          found.push({
            file: f.rel, line: i + 1,
            detail: `${probe.what} ở đường tính tiền — ${probe.fix}`,
          });
        }
      }
      const literal = code.match(MONEY_DECIMAL_LITERAL);
      if (literal) {
        found.push({
          file: f.rel, line: i + 1,
          detail: `gán số thập phân cho \`${literal[1]}\` — VND là số nguyên, không làm tròn để ép khớp`,
        });
      }
    });
  }
  return found;
}

// ---------------------------------------------------------------------------
// DATE-01 — "hôm nay" phải theo giờ Việt Nam
//
// Nguồn: FUTURE-01 trong `docs/decisions.md`, người dùng chốt 16/10/2026 —
// "hôm nay" theo Asia/Ho_Chi_Minh. Lấy ngày từ đồng hồ server (`current_date`,
// `date.today()`) làm ngày nghiệp vụ sẽ lệch một ngày mỗi khi server chạy ở múi
// giờ khác, và lệch đúng vào lúc giao ca cuối ngày.
//
// Dấu thời gian tuyệt đối không bị chặn: `now()` cho cột timestamptz và
// `datetime.now(UTC)` cho provenance không nhập nhằng múi giờ.
const VN_TZ = /Asia\/Ho_Chi_Minh|business_today\s*\(/;
const CLOCK_DATE = {
  ".sql": [
    /\bcurrent_date\b/i,
    /\blocaltimestamp\b/i,
    /\bnow\s*\(\s*\)\s*::\s*date\b/i,
    /\bcurrent_timestamp\s*::\s*date\b/i,
  ],
  ".py": [
    /\bdate(?:time)?\.today\s*\(/,
    /\bdatetime\.utcnow\s*\(/,
    /\bdatetime\.now\s*\(\s*\)/,
  ],
  ".js": [/\bnew Date\s*\(\s*\)/],
};

function ruleVnBusinessToday(files) {
  const found = [];
  for (const f of files) {
    if (isTest(f)) continue;
    const set = CLOCK_DATE[f.ext];
    if (!set) continue;
    lines(f.text).forEach((line, i) => {
      const code = stripComment(line, f.ext);
      if (VN_TZ.test(code)) return;
      for (const re of set) {
        if (re.test(code)) {
          found.push({
            file: f.rel, line: i + 1,
            detail: 'lấy ngày từ đồng hồ mà không khai múi giờ — "hôm nay" phải theo Asia/Ho_Chi_Minh (SQL: `ledger.business_today()`; Python: `datetime.now(VN_TZ).date()`)',
          });
          return;
        }
      }
    });
  }
  return found;
}

// ---------------------------------------------------------------------------
// Tách hàm trong file SQL, để hai luật dưới kiểm được từng hàm một thay vì cả
// file. Cắt thô theo `CREATE [OR REPLACE] FUNCTION` là đủ: thân hàm plpgsql
// trong repo luôn nằm giữa một cặp dollar-quote.
function sqlFunctions(text) {
  const re = /CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([a-z_][a-z0-9_.]*)/gi;
  const all = [...text.matchAll(re)];
  return all.map((m, idx) => ({
    name: m[1],
    body: text.slice(m.index, idx + 1 < all.length ? all[idx + 1].index : text.length),
    line: text.slice(0, m.index).split(/\r?\n/).length,
  }));
}

// Hàm ghi tiền: hàm có INSERT vào proposal hoặc posting.
const WRITES_LEDGER = /INSERT\s+INTO\s+[a-z_]*\.?(?:proposal|posting)\b/i;

// ---------------------------------------------------------------------------
// FUTURE-01 — không cho ngày ghi sổ ở tương lai
//
// Nguồn: FUTURE-01 trong `docs/decisions.md`, người dùng chốt 16/10/2026, và
// `specs/p0-fixture-future-posting-date.md`. Bản đã merge trên `main` cài bằng
// `ledger.business_today()`. Lúc chốt, luồng còn hai bước nhập/duyệt; theo
// `V6-DB` (19/10/2026) không còn bước duyệt. Luật quét từng hàm ghi sổ chứ
// không theo bước của luồng, nên vẫn đúng: hàm nào ghi sổ thì tự chặn.
//
// Kiểm: mỗi hàm ghi tiền có dính `posting_date` phải so posting_date với hôm
// nay theo giờ VN. Không đặt cận dưới ở đây — cận dưới là cutover, đã có guard
// riêng, và với fixture P0 thì mốc cutover vẫn CÒN MỞ.
const FUTURE_GUARD = /posting_date\s*>\s*(?:\(\s*now\s*\(\s*\)\s*AT TIME ZONE|[a-z_]*\.?business_today\s*\()/i;

function ruleFuturePostingDate(files) {
  const found = [];
  for (const f of files.filter((file) => file.ext === ".sql")) {
    for (const fn of sqlFunctions(f.text)) {
      if (!WRITES_LEDGER.test(fn.body)) continue;
      if (!/posting_date/i.test(fn.body)) continue;
      if (FUTURE_GUARD.test(fn.body)) continue;
      found.push({
        file: f.rel, line: fn.line,
        detail: `hàm ghi tiền \`${fn.name}\` không chặn \`posting_date\` ở tương lai — thêm so sánh \`posting_date > ledger.business_today()\` rồi RAISE ngay trong hàm này; mọi hàm ghi sổ tự chặn, không trông vào hàm khác`,
      });
    }
  }
  return found;
}

// ---------------------------------------------------------------------------
// TRIP-DATE-01 — ngày nghiệp vụ chuyến là bắt buộc
//
// Nguồn: DATE trong `docs/decisions.md` (người dùng làm rõ 14/10/2026) và ô
// "Ngày" trong `docs/business-rules.md`: ngày nghiệp vụ chuyến là ngày xe nhập
// kho, giữ riêng khỏi ngày nhập hệ thống / duyệt / ghi sổ / kỳ nợ.
//
// Giới hạn đã biết: trong schema hiện hành trường này tên là `event_date`, chưa
// có cột nào tên `warehouse_in_date`; sổ quyết định ghi rõ phần backend "chưa
// kiểm runtime đã đổi". Nên check chỉ khẳng định phần ĐÃ CHỐT và kiểm được: hàm
// ghi tiền không được nhận ngày nghiệp vụ rỗng. Việc đặt tên cột theo đúng
// nghiệp vụ vẫn CÒN MỞ, không ép qua check này.
const TRIP_DATE_GUARD = /p_event_date\s+IS\s+NULL/i;

function ruleTripDateRequired(files) {
  const found = [];
  for (const f of files.filter((file) => file.ext === ".sql")) {
    for (const fn of sqlFunctions(f.text)) {
      if (!WRITES_LEDGER.test(fn.body)) continue;
      if (!/\bp_event_date\b/i.test(fn.body)) continue;
      if (TRIP_DATE_GUARD.test(fn.body)) continue;
      found.push({
        file: f.rel, line: fn.line,
        detail: `hàm ghi tiền \`${fn.name}\` nhận \`p_event_date\` mà không chặn NULL — ngày nghiệp vụ chuyến (ngày xe nhập kho) là bắt buộc; blank/NULL giữ là chưa biết, không tự thay bằng hôm nay`,
      });
    }
  }
  return found;
}

// ---------------------------------------------------------------------------
// Ba luật ARCH-* dưới đây giữ ranh giới kiến trúc, không phải luật nghiệp vụ.
// Khác VND-*/DATE-*, chúng không truy về một dòng trong sổ quyết định: chúng
// mô tả cách mã nguồn đang được chia tầng, và tầng đó hôm nay đang đúng.
//
// Lý do code hóa: một ranh giới đúng mà không có gì giữ thì lần refactor sau
// làm mất, và mất êm — không test nào đỏ, chỉ có một `import` mới hoặc một
// phép cộng đặt nhầm chỗ. Ba luật này chốt lại hiện trạng đã kiểm, để việc đổi
// ranh giới phải là quyết định có chủ ý (sửa luật, ghi lý do) chứ không phải
// một diff lọt qua review.
//
// Giới hạn chung: `collect()` chỉ đọc .sql/.py/.js, nên script nhúng thẳng
// trong .html nằm ngoài tầm ba luật này.

// ---------------------------------------------------------------------------
// ARCH-01 — chỉ tầng DB được gọi psql
//
// Hiện trạng đã kiểm 19/10/2026 (`grep -rn psql`): các file dưới đây chạm
// tới psql, mọi truy vấn khác đi qua adapter trong `web/`. Giữ được điều này
// thì đổi cách nối DB (psql CLI → driver, đổi tham số kết nối, thêm timeout)
// là sửa hai file adapter chứ không phải lùng khắp repo; và không có đường nào
// gọi DB mà vòng qua chỗ trích dẫn/escape của adapter.
//
// Danh sách tường minh kèm lý do từng file — không dùng mẫu regex rộng rồi tự
// miễn trừ, vì mẫu rộng ("file nào tên *_db.py") chính là cách luật bị lách
// bằng cách đặt tên.
const PSQL_ALLOWED = {
  "cong-no-web-handoff/web/db.py":
    "adapter đọc capture — nơi duy nhất dựng lệnh psql cho đường đọc lịch sử",
  "cong-no-web-handoff/web/ledger_db.py":
    "adapter sổ cái — nơi duy nhất dựng lệnh psql cho đường sổ cái và pilot",
  "cong-no-web-handoff/tools/pg_m1_report.py":
    "công cụ vận hành xuất báo cáo M1, chạy tay ngoài tiến trình web",
  "cong-no-web-handoff/tools/test_pg_ledger_schema.py":
    "harness kiểm schema trong Docker, phải nói chuyện với psql để kiểm chính psql",
  "cong-no-web-handoff/tests/test_web.py":
    "test của adapter, kiểm đúng phần dựng lệnh và trích dẫn biến",
  // Bốn mục dưới đây thêm 19/10/2026 khi nhập `main`: chúng đã có từ trước trên
  // `main` và thật sự dựng lệnh psql, cùng loại với hai mục ngay trên.
  "cong-no-web-handoff/tools/test_pg_versioned_approval.py":
    "harness kiểm approval theo revision trong Docker, phải nói chuyện với psql để kiểm chính psql",
  "cong-no-web-handoff/tools/test_pg_m1_queries.py":
    "harness kiểm truy vấn M1 trong Docker, cùng lý do với harness schema",
  "cong-no-web-handoff/tools/m1_release.py":
    "công cụ vận hành phát hành M1, chạy tay ngoài tiến trình web như pg_m1_report.py",
  "cong-no-web-handoff/tests/test_m1_export_verify.py":
    "test của công cụ M1, truyền tên chương trình giả vào hàm đã được patch",
  // Sáu mục dưới đây thêm 21/10/2026 khi gom V7: tầng DB và công cụ của V7 thật sự
  // dựng lệnh psql (docker exec ... psql); cùng loại với adapter/harness ở trên.
  "cong-no-web-handoff/web/v7_ledger_api.py":
    "adapter DB của V7 — lớp Psql là nơi duy nhất dựng lệnh psql cho đường sổ khách V7",
  "cong-no-web-handoff/tools/test_pg_v7_backend.py":
    "harness kiểm backend V7 trong Docker, phải nói chuyện với psql để kiểm chính psql",
  "cong-no-web-handoff/tools/test_pg_v7_matrix.py":
    "harness review SQL get_receivables_matrix trong Docker dùng một lần, cùng loại harness V7 ở trên (thêm 24/10/2026, spec v7-cong-no-theo-thang)",
  "cong-no-web-handoff/tools/v7_load_real_copy.py":
    "công cụ nạp bản sao vào container cô lập, chạy tay ngoài tiến trình web",
  "cong-no-web-handoff/tools/v7_backup.py":
    "công cụ vận hành backup/restore lớp sokhach, phải gọi psql/pg_dump/pg_restore; chạy tay ngoài tiến trình web",
  "cong-no-web-handoff/tools/test_v7_backup.py":
    "harness kiểm backup/restore trong Docker, phải nói chuyện với psql để kiểm chính công cụ",
  "cong-no-web-handoff/tools/v7_live_demo.py":
    "công cụ dựng demo dữ liệu giả trong container cô lập, chạy tay ngoài tiến trình web",
  "cong-no-web-handoff/tests/test_v7_ledger_api.py":
    "test của adapter V7, kiểm dựng lệnh và ánh xạ lỗi psql bằng runner giả",
  "cong-no-web-handoff/tests/test_v7_load_real_copy.py":
    "test của công cụ nạp V7, truyền lệnh psql giả vào hàm đã được patch",
};

// `scripts/` là mã của chính bộ kiểm: luật và fixture ở đây buộc phải chứa
// chuỗi mẫu `psql` để chứng minh luật bắt được. Ngoại lệ duy nhất, và nó nằm
// ngoài ứng dụng.
const isCheckHarness = (f) => /^scripts\//.test(f.rel);

function ruleDbLayerOnlyPsql(files) {
  const found = [];
  for (const f of files) {
    if (![".py", ".js"].includes(f.ext)) continue;
    if (isCheckHarness(f) || PSQL_ALLOWED[f.rel]) continue;
    lines(f.text).forEach((line, i) => {
      const code = stripComment(line, f.ext);
      if (!/\bpsql\b/i.test(code)) return;
      // Chỉ tính là "gọi psql" khi dòng đó thật sự dựng lệnh: có chuỗi "psql"
      // làm tên chương trình, hoặc gọi subprocess ngay trên dòng. Truyền tham
      // số (`psql=configured.psql`), đọc thuộc tính (`self.psql`) hay đặt tên
      // tham số (`def rows(psql, ...)`) là đang ĐI QUA adapter — đúng ranh
      // giới, không phải vi phạm. Luật cũ bắt mọi dòng có chữ `psql`, nên nó
      // báo nhầm đúng chỗ đang tuân thủ: `web/ledger_app.py` dựng `HistoryDB`
      // bằng `psql=configured.psql` thì bị tính là gọi DB từ tầng web.
      const invokesPsql =
        /["']psql(\.exe)?["']/i.test(code) ||
        /\b(?:subprocess\.(?:run|Popen|call|check_output|check_call)|execFile|spawnSync|spawn)\s*\(/.test(code);
      if (!invokesPsql) return;
      found.push({
        file: f.rel, line: i + 1,
        detail: "gọi `psql` ngoài tầng DB — đây là ranh giới kiến trúc, không phải sở thích: mọi truy vấn đi qua adapter `cong-no-web-handoff/web/db.py` hoặc `cong-no-web-handoff/web/ledger_db.py`. Thêm hàm vào adapter rồi gọi hàm đó; nếu thật sự cần một tầng DB mới thì mở rộng `PSQL_ALLOWED` kèm lý do",
      });
    });
  }
  return found;
}

// ---------------------------------------------------------------------------
// ARCH-02 — tầng web không import ngược vào tools/ hay pilot/
//
// Hiện trạng đã kiểm 19/10/2026: `web/app.py` và `web/ledger_app.py` chỉ import
// stdlib cộng adapter cùng thư mục (`from db import ...`,
// `from ledger_db import ...`). Phụ thuộc chạy một chiều: `tools/` và `pilot/`
// được phép dùng tầng web, không có chiều ngược lại.
//
// Giữ chiều này vì `tools/` là công cụ vận hành chạy tay (đối số dòng lệnh,
// đường ghi file, `sudo`) và `pilot/` là đối soát một lần. Kéo chúng vào tiến
// trình phục vụ HTTP là kéo theo cả bề mặt đó vào chỗ nhận request.
//
// Kiểm ba dạng: câu import thẳng, `importlib.import_module`, và vá `sys.path`
// trỏ sang hai thư mục kia. Không kiểm được: import động dựng tên từ biến —
// giới hạn đã biết, ghi ra đây thay vì giả vờ luật phủ hết.
const WEB_LAYER = /(^|\/)web\/[^/]+\.py$/;
const CROSS_IMPORT = [
  { re: /^\s*(?:from|import)\s+(tools|pilot)\b/, how: "câu import" },
  { re: /import_module\s*\(\s*["'](tools|pilot)\b/, how: "`importlib.import_module`" },
  { re: /sys\.path\b.*\b(tools|pilot)\b/, how: "vá `sys.path`" },
];

function ruleWebNoToolsImport(files) {
  const found = [];
  for (const f of files) {
    if (f.ext !== ".py" || !WEB_LAYER.test(f.rel)) continue;
    lines(f.text).forEach((line, i) => {
      const code = stripComment(line, f.ext);
      for (const probe of CROSS_IMPORT) {
        const m = code.match(probe.re);
        if (!m) continue;
        found.push({
          file: f.rel, line: i + 1,
          detail: `tầng web với tới \`${m[1]}/\` qua ${probe.how} — đây là ranh giới kiến trúc, không phải sở thích: phụ thuộc chạy một chiều, \`tools/\` và \`pilot/\` dùng tầng web chứ không ngược lại. Phần dùng chung thì chuyển vào adapter trong \`web/\`, đừng kéo công cụ vận hành vào tiến trình nhận request`,
        });
        return;
      }
    });
  }
  return found;
}

// ---------------------------------------------------------------------------
// ARCH-03 — tính tiền chỉ ở model, không ở file UI
//
// Hiện trạng đã kiểm 19/10/2026: preview ghép từng cặp `X-model.js` +
// `X-ui.js`, nạp đúng thứ tự đó trong .html. Model giữ toàn bộ số học BigInt
// (`so-khach-v7-model.js`, `customer-ledger-workbench.js`); hai file UI
// (`so-khach-v7-*ui.js`, `customer-ledger-workbench-ui.js`) chỉ so sánh, định
// dạng và gọi model — kể cả chỗ tính lệch giữa số dán và số model cũng gọi
// `model.allocateReceipt` thay vì tự trừ.
//
// Giữ ranh giới này vì model là thứ có test (`test-*-model.js`). Một phép cộng
// tiền đặt trong file render thì không test nào chạm tới, và nó sẽ lệch khỏi
// model lúc nào không ai biết.
//
// Phạm vi: file `*-ui.js`, quy ước đặt tên repo đang dùng cho tầng render.
// Dấu hiệu tiền: tên kết thúc bằng `_vnd`/`Vnd`/`VND`, hằng BigInt (`0n`), và
// lời gọi `BigInt(...)`. Chỉ chặn số học `+ - *` và `+= -= *=`; so sánh với
// định dạng vẫn được phép, vì UI phải đọc được số để hiển thị.
//
// Giới hạn đã biết, ghi ra thay vì bắt bừa: ô tiền đặt tên không theo `*Vnd`
// (ví dụ `price`, `otherFee` ở workbench) nằm ngoài lưới này; và
// `web/ledger_app.py` thì cộng trừ tiền ngay trong đường render — tầng Python
// CHƯA tách model/UI như tầng JS. Luật chỉ khẳng định phần đang đúng và kiểm
// được; tách tầng Python là việc riêng, cần quyết định trước khi code hóa.
const UI_FILE = /-ui\.js$/;
const MONEY_NAME = String.raw`(?:[A-Za-z_$][A-Za-z0-9_$]*(?:_vnd|Vnd|VND)|\d+n)`;
// Tên kết thúc bằng Vnd mà đứng trước `(` là hàm, không phải giá trị tiền:
// `fmtVnd(x)` là bộ định dạng, và `'...' + fmtVnd(x)` là nối chuỗi chứ không
// phải cộng tiền. Lọc chỗ này ra, nếu không luật sẽ bắt nhầm đúng cái việc nó
// muốn khuyến khích — UI gọi hàm thay vì tự tính.
const MONEY_VALUE = MONEY_NAME + String.raw`(?!\s*\()`;
// Toán tử số học, viết sao cho không nuốt `==`/`===`/`=>`/`++`/`--`.
const MONEY_ARITHMETIC = [
  new RegExp(MONEY_NAME + String.raw`\s*(?:[-+*](?![-+=])|[-+*]=(?!=))`),
  new RegExp(String.raw`(?:[-+*](?![-+=*])|[-+*]=)\s*(?:` + MONEY_VALUE + String.raw`|BigInt\s*\()`),
];

function ruleMoneyMathInModel(files) {
  const found = [];
  for (const f of files) {
    if (f.ext !== ".js" || !UI_FILE.test(f.rel)) continue;
    const model = f.rel.replace(/-ui\.js$/, "-model.js");
    lines(f.text).forEach((line, i) => {
      const code = stripComment(line, f.ext);
      if (!MONEY_ARITHMETIC.some((re) => re.test(code))) return;
      found.push({
        file: f.rel, line: i + 1,
        detail: `cộng/trừ/nhân tiền trong file UI — đây là ranh giới kiến trúc, không phải sở thích: số học tiền nằm ở model (\`${model}\`), nơi có test riêng; file UI chỉ so sánh, định dạng và gọi model. Thêm hàm vào model rồi gọi hàm đó`,
      });
    });
  }
  return found;
}

const RULES = [
  { id: "VND-01", title: "cột tiền phải là số nguyên chính xác", run: ruleVndSqlColumns },
  { id: "VND-02", title: "không dùng số thực ở đường tính tiền", run: ruleNoFloatMoney },
  { id: "DATE-01", title: '"hôm nay" phải theo giờ Việt Nam', run: ruleVnBusinessToday },
  { id: "FUTURE-01", title: "không cho ngày ghi sổ ở tương lai", run: ruleFuturePostingDate },
  { id: "TRIP-DATE-01", title: "ngày nghiệp vụ chuyến là bắt buộc", run: ruleTripDateRequired },
  { id: "ARCH-01", title: "chỉ tầng DB được gọi psql", run: ruleDbLayerOnlyPsql },
  { id: "ARCH-02", title: "tầng web không import tools/ hay pilot/", run: ruleWebNoToolsImport },
  { id: "ARCH-03", title: "tính tiền chỉ ở model, không ở file UI", run: ruleMoneyMathInModel },
];

// Trả về [{ id, title, violations: [{ file, line, detail }] }] cho mọi luật, kể
// cả luật không có vi phạm, để người gọi in được bảng tổng kết.
function runRules(root, only = null) {
  const files = collect(root);
  return RULES.filter((rule) => !only || only.includes(rule.id)).map((rule) => ({
    id: rule.id,
    title: rule.title,
    violations: rule.run(files),
  }));
}

module.exports = { runRules, RULES, collect };
