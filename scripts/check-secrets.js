#!/usr/bin/env node
// Quét secrets và dữ liệu nghiệp vụ thật trong tài liệu, chỉ dùng stdlib Node.
//
//   node scripts/check-secrets.js          quét các dòng thêm vào trong diff đã stage
//   node scripts/check-secrets.js --all    quét mọi file đã theo dõi (git ls-files); `npm run check` chạy lệnh này
//
// require() từ test chỉ lấy mẫu và hàm khớp, không quét (test: scripts/test-check-secrets.js).
//
// Chỉ in file, số dòng và tên mẫu; không bao giờ in giá trị khớp (repo public, log CI cũng public).
// Tên khách so theo danh sách ngoài repo (`customer-name` bên dưới); chưa có danh sách thì mẫu đó bỏ qua.
// Thoát 1 nếu có khớp. Đây là lưới thô, không thay review diff (AGENTS.md).

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");

const CONTENT_PATTERNS = [
  ["private-key", /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ["github-token", /\bgh[pousr]_[A-Za-z0-9]{30,}\b/],
  ["github-pat", /\bgithub_pat_[A-Za-z0-9_]{30,}\b/],
  ["anthropic-key", /\bsk-ant-[A-Za-z0-9_-]{20,}\b/],
  ["openai-style-key", /\bsk-[A-Za-z0-9]{32,}\b/],
  ["aws-access-key", /\bAKIA[0-9A-Z]{16}\b/],
  ["google-api-key", /\bAIza[0-9A-Za-z_-]{35}\b/],
  // Khóa Tailscale: tskey-auth-/api-/client-… và kiểu cũ tskey-<id>-<bí mật>.
  ["tailscale-key", /\btskey-(?:[a-z]+-)?[A-Za-z0-9]{6,}-[A-Za-z0-9]{6,}/],
  ["age-secret-key", /\bAGE-SECRET-KEY-1[0-9A-Z]{50,}/],
  ["gcp-service-account", /"private_key_id"\s*:\s*"[^"\s]{8,}"/],
  ["slack-token", /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/],
  ["db-url-with-password", /\b(?:postgres(?:ql)?|mysql|mongodb):\/\/[^\s:@/]+:[^\s@/]+@/i],
  ["secret-assignment", /\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*["'][^"'\s]{8,}["']/i],
];

const PATH_PATTERNS = [
  ["env-file", /(^|\/)\.env(\..+)?$/],
  ["key-file", /\.(pem|key|p12|pfx)$/i],
  ["age-file", /\.age$/i],
  ["db-or-dump", /\.(dump|backup|sqlite3?|db)$/i],
  ["captures-dir", /(^|\/)captures\//],
  // File danh sách tên khách (`NAMES_FILE`) chép nhầm vào cây làm việc.
  ["customer-name-list", /(^|\/)webdebit-ten-khach\.txt$/i],
];

// Dữ liệu nghiệp vụ thật trong tài liệu. Gỡ 18/11/2026: nhật ký triển khai đã chép tổng nợ cả công ty tới
// từng đồng, số tiền theo khách, tên khách và số container thật vào repo public. Chỉ áp cho tài liệu
// (`DOC_PATH`); test và fixture trong mã không qua lưới này. Không bắt được: số viết liền ("95000000"),
// nhóm phẩy ("1,070,000,000"), tiền rút gọn ("43,5 triệu"), số booking, tên khách ngoài danh sách hoặc dưới ngưỡng
// của `customer-name` — những thứ đó vẫn do review.
const DATA_PATTERNS = [
  // Số tiền nhóm chấm từ 7 chữ số (1.234.567 trở lên). Cỡ file ghi kèm "byte" không phải tiền.
  ["vnd-amount", /(?<![\d.])\d{1,3}(?:\.\d{3}){2,}(?!\d|\.\d)(?!\s*bytes?\b)/g],
  // Số container ISO 6346: 4 chữ hoa + 7 số, nhận cả kiểu viết "ABCU 123456 7" / "ABCU 123456-7".
  ["container-no", /(?<![A-Za-z0-9])[A-Z]{4} ?\d{6}[ -]?\d(?!\d)/g],
];

// Mã chủ container bịa của dữ liệu mẫu (không phải mã chủ của hãng thật): MAUU (bản xem, spec),
// HTHU (debit note mẫu v4), ALTU (ví dụ mã thay thế ALT-KEY-01).
const FAKE_CONTAINER_OWNERS = new Set(["MAUU", "HTHU", "ALTU"]);

// Tài liệu: mọi file dưới docs/, specs/, contexte/, livrables/ và mọi file .md.
const DOC_PATH = /^(?:docs|specs|contexte|livrables)\/|\.md$/i;

// Dữ liệu giả cố ý (ví dụ trong spec, fixture tổng hợp) khai ngay trong file đó, một hay nhiều dòng:
//   <!-- du-lieu-gia: 50.000.000 100.000.000 MAUU1000101 -->
// Chỉ đúng các giá trị đã khai, chỉ trong file đó; giá trị khác vẫn bị bắt. Không khai số thật vào đây.
const FAKE_MARKER = /<!--\s*du-lieu-gia:([^>]*?)-->/g;

// Như dòng khai trên, nhưng ghi ở đây cho file không nên sửa chỉ để thêm dòng khai: mọi thay đổi dưới
// `specs/v7-backend/` làm `Deploy hao` dừng ở cổng triển khai tay (`.github/workflows/deploy-hao.yml`).
const FAKE_VALUES_BY_FILE = {
  // Số của fixture vàng V7 (`so-khach-v7-fixture.js`, sinh bằng script, không lấy từ sổ thật).
  "specs/v7-backend/thiet-ke.md": ["600.694.000", "1.381.510.000", "2.411.645.000"],
};

// Tên khách thật trong tài liệu (từ 18/11/2026). Danh sách tên không nằm trong repo public: CI đọc biến
// `NAMES_ENV` (secret cùng tên của repo), ở máy đọc file `NAMES_FILE` trong thư mục git chung
// (`git rev-parse --git-common-dir`) — mọi worktree của một bản clone dùng chung file đó và Git không bao giờ theo
// dõi file trong thư mục này. Mỗi dòng một tên; dòng trống và dòng bắt đầu bằng `#` bỏ qua. Không có danh sách thì
// bỏ qua mẫu và in rõ đã bỏ qua. Báo khớp in `#n` (số dòng của tên trong danh sách), không bao giờ in tên.
const NAMES_ENV = "WEBDEBIT_TEN_KHACH";
const NAMES_FILE = "webdebit-ten-khach.txt";
// Bỏ dấu rồi thì tên ngắn trùng chữ thường gặp ("Cô Ba" ~ "có ba", "Tân" ~ "tận"): chỉ dùng tên từ 6 chữ/số, tên một
// từ thì từ 8 (âm tiết tiếng Việt dài nhất 7 chữ). Tên dài hơn mà vẫn trùng cụm từ hay gặp thì xóa khỏi danh sách.
const NAME_MIN_CHARS = 6;
const NAME_MIN_CHARS_ONE_WORD = 8;

// Các từ của một chuỗi để so tên như so tên tab (`fold` của cong-no-web-handoff/tools/v7_company_info_snapshot.py):
// bỏ dấu, đ → d, không phân biệt hoa thường; mọi ký tự không phải chữ/số (khoảng trắng, dấu câu, `-`, `_`) là ranh
// giới từ.
function nameWords(text) {
  return String(text).normalize("NFD").replace(/\p{M}+/gu, "").replace(/[đĐ]/g, "d").toLowerCase()
    .split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

// Chỉ mục danh sách tên: `keys` (các từ nối bằng một dấu cách → số dòng đầu tiên, từ 1), `starts` (từ đầu → các
// độ dài tên bắt đầu bằng từ đó), `skipped` (số tên dưới ngưỡng).
function nameIndex(lines) {
  const keys = new Map();
  const starts = new Map();
  let skipped = 0;
  lines.forEach((line, i) => {
    if (!line.trim() || line.trim().startsWith("#")) return;
    const words = nameWords(line);
    if (words.join("").length < (words.length > 1 ? NAME_MIN_CHARS : NAME_MIN_CHARS_ONE_WORD)) {
      skipped += 1;
      return;
    }
    const key = words.join(" ");
    if (keys.has(key)) return;
    keys.set(key, i + 1);
    if (!starts.has(words[0])) starts.set(words[0], new Set());
    starts.get(words[0]).add(words.length);
  });
  return { keys, starts, skipped };
}

// Số dòng (trong danh sách) của tên đầu tiên có trọn từ trong một dòng tài liệu; không có thì 0.
function nameHit(text, index) {
  const words = nameWords(text);
  for (let i = 0; i < words.length; i++) {
    for (const size of index.starts.get(words[i]) || []) {
      const lineNo = i + size <= words.length && index.keys.get(words.slice(i, i + size).join(" "));
      if (lineNo) return lineNo;
    }
  }
  return 0;
}

// Danh sách tên: biến `NAMES_ENV` nếu có chữ, nếu không thì file; không có cả hai thì null.
function readNameList(env, file) {
  const value = env[NAMES_ENV];
  if (value && value.trim()) return { lines: value.split(/\r?\n/), source: `biến ${NAMES_ENV}` };
  try {
    return { lines: fs.readFileSync(file, "utf8").split(/\r?\n/), source: file };
  } catch {
    return null;
  }
}

function git(args) {
  const r = spawnSync("git", args, { cwd: ROOT, encoding: "utf8", maxBuffer: 256 * 1024 * 1024 });
  if (r.status !== 0) {
    console.error(`git ${args.join(" ")} thất bại: ${(r.stderr || "").trim()}`);
    process.exit(2);
  }
  return r.stdout;
}

// Tên các mẫu khớp một dòng nội dung / một đường dẫn file.
function contentHits(text) {
  return CONTENT_PATTERNS.filter(([, re]) => re.test(text)).map(([name]) => name);
}

function pathHits(file) {
  const p = file.replace(/\\/g, "/");
  return PATH_PATTERNS.filter(([, re]) => re.test(p)).map(([name]) => name);
}

function isDocPath(file) {
  return DOC_PATH.test(file.replace(/\\/g, "/"));
}

// Tập giá trị đã khai là dữ liệu giả trong nội dung một file.
function fakeValues(text) {
  const out = new Set();
  for (const m of text.matchAll(FAKE_MARKER)) {
    for (const value of m[1].split(/[\s,;]+/)) if (value) out.add(value);
  }
  return out;
}

// Tập giá trị giả của một file tài liệu (dòng khai trong file + `FAKE_VALUES_BY_FILE`); file không phải
// tài liệu thì null: lưới dữ liệu thật không áp.
function allowedValues(file, text) {
  const p = file.replace(/\\/g, "/");
  if (!isDocPath(p)) return null;
  return new Set([...fakeValues(text), ...(FAKE_VALUES_BY_FILE[p] || [])]);
}

// Tên các mẫu dữ liệu thật khớp một dòng tài liệu; `allowed` là tập giá trị giả đã khai của file.
function dataHits(text, allowed = new Set()) {
  const line = text.replace(FAKE_MARKER, "");
  const names = [];
  for (const [name, re] of DATA_PATTERNS) {
    for (const m of line.matchAll(re)) {
      const value = m[0];
      if (allowed.has(value) || allowed.has(value.replace(/[ -]/g, ""))) continue;
      if (name === "container-no" && FAKE_CONTAINER_OWNERS.has(value.slice(0, 4))) continue;
      names.push(name);
      break;
    }
  }
  return names;
}

module.exports = {
  CONTENT_PATTERNS, PATH_PATTERNS, DATA_PATTERNS, FAKE_CONTAINER_OWNERS, FAKE_VALUES_BY_FILE, NAMES_ENV, NAMES_FILE,
  contentHits, pathHits, isDocPath, fakeValues, allowedValues, dataHits, nameWords, nameIndex, nameHit, readNameList,
};

const hits = [];
let dataFound = false;
let names = null; // chỉ mục tên khách (`nameIndex`); null khi chưa có danh sách

// Nạp danh sách tên khách, in nguồn và số tên dùng được (số đếm, không in tên).
function loadNames() {
  const file = path.resolve(ROOT, git(["rev-parse", "--git-common-dir"]).trim(), NAMES_FILE);
  const list = readNameList(process.env, file);
  const index = list && nameIndex(list.lines);
  if (!index || !index.keys.size) {
    console.log(`check-secrets: BỎ QUA customer-name — chưa có danh sách tên khách (biến ${NAMES_ENV} hoặc file ${file}).`);
    return null;
  }
  console.log(`check-secrets: customer-name dùng ${index.keys.size} tên từ ${list.source} (bỏ ${index.skipped} tên dưới ngưỡng).`);
  return index;
}

function scanLine(file, lineNo, text, allowed) {
  for (const name of contentHits(text)) hits.push(`${file}:${lineNo} [${name}]`);
  if (!allowed) return;
  const found = dataHits(text, allowed);
  const nameLine = names ? nameHit(text, names) : 0;
  if (nameLine) found.push(`customer-name #${nameLine}`);
  for (const name of found) {
    hits.push(`${file}:${lineNo} [${name}]`);
    dataFound = true;
  }
}

function scanPaths(files) {
  for (const f of files) {
    for (const name of pathHits(f)) hits.push(`${f} [${name}]`);
  }
}

function main() {
  const scanAll = process.argv.includes("--all");
  names = loadNames();
  if (scanAll) {
    const files = git(["ls-files", "-z"]).split("\0").filter(Boolean);
    scanPaths(files);
    for (const f of files) {
      if (f === "scripts/check-secrets.js") continue;
      let buf;
      try {
        buf = fs.readFileSync(path.join(ROOT, f));
      } catch {
        continue;
      }
      if (buf.includes(0)) continue;
      const text = buf.toString("utf8");
      const allowed = allowedValues(f, text);
      text.split(/\r?\n/).forEach((line, i) => scanLine(f, i + 1, line, allowed));
    }
  } else {
    scanPaths(git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]).split("\0").filter(Boolean));
    // Giá trị giả khai trong bản đã stage của chính file tài liệu đó.
    const allowedOf = new Map();
    const allowedFor = (file) => {
      if (!isDocPath(file)) return null;
      if (!allowedOf.has(file)) allowedOf.set(file, allowedValues(file, git(["show", `:${file}`])));
      return allowedOf.get(file);
    };
    let file = "";
    let lineNo = 0;
    for (const line of git(["diff", "--cached", "-U0", "--no-color"]).split("\n")) {
      if (line.startsWith("+++ b/")) {
        file = line.slice(6);
      } else if (line.startsWith("@@")) {
        const m = /\+(\d+)/.exec(line);
        lineNo = m ? Number(m[1]) : 0;
      } else if (line.startsWith("+") && !line.startsWith("+++")) {
        if (file !== "scripts/check-secrets.js") scanLine(file, lineNo, line.slice(1), allowedFor(file));
        lineNo += 1;
      }
    }
  }

  if (hits.length) {
    console.error("check-secrets: PHÁT HIỆN nghi ngờ (không in giá trị):");
    for (const h of hits) console.error("  " + h);
    if (dataFound) {
      console.error(
        "Dữ liệu thật trong tài liệu: ghi số đếm, mã sổ hoặc câu giữ ý (\"tổng nợ không đổi\") thay cho số tiền,"
        + " tên khách và số container; dữ liệu giả cố ý thì khai `<!-- du-lieu-gia: <giá trị> -->` trong chính file đó."
        + " `customer-name #n`: tên ở dòng n của danh sách tên khách; nếu dòng tài liệu chỉ là cụm từ thường gặp"
        + " trùng tên, xóa dòng n khỏi danh sách (file và secret), không khai tên trong tài liệu."
      );
    }
    process.exit(1);
  }
  console.log(`check-secrets: sạch (${scanAll ? "toàn bộ file đã theo dõi" : "diff đã stage"}).`);
}

if (require.main === module) main();
