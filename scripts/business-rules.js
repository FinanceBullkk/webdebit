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
  { ext: ".js", re: /\b(?:Number\.)?parseFloat\s*\(/, what: "`parseFloat`", fix: "dùng `BigInt` (xem `preview/so-cong-no-v5-model.js`)" },
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
// `specs/p0-fixture-future-posting-date.md`: chặn ở cả đường nhập và đường
// duyệt. Bản đã merge trên `main` cài bằng `ledger.business_today()`.
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
        detail: `hàm ghi tiền \`${fn.name}\` không chặn \`posting_date\` ở tương lai — thêm so sánh \`posting_date > ledger.business_today()\` rồi RAISE, ở cả đường nhập và đường duyệt`,
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

const RULES = [
  { id: "VND-01", title: "cột tiền phải là số nguyên chính xác", run: ruleVndSqlColumns },
  { id: "VND-02", title: "không dùng số thực ở đường tính tiền", run: ruleNoFloatMoney },
  { id: "DATE-01", title: '"hôm nay" phải theo giờ Việt Nam', run: ruleVnBusinessToday },
  { id: "FUTURE-01", title: "không cho ngày ghi sổ ở tương lai", run: ruleFuturePostingDate },
  { id: "TRIP-DATE-01", title: "ngày nghiệp vụ chuyến là bắt buộc", run: ruleTripDateRequired },
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
