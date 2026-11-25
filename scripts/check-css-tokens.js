#!/usr/bin/env node
// Token CSS kiểu "chỉ được giảm": mỗi file giao diện có mức trần cho bốn loại giá trị tự đặt, không được vượt.
//
//   node scripts/check-css-tokens.js            kiểm
//   node scripts/check-css-tokens.js --update   hạ mức trần về số hiện tại (chỉ hạ, không nâng)
//
// Lý do tồn tại: ngày 25/11/2026 CSS giao diện có khoảng 90 khai báo cỡ chữ ngoài thang, vài trăm mã màu viết cứng
// và hơn mười kiểu bo góc, vì mỗi lần sửa một màn lại tự đặt giá trị mới. Từng màn không xấu, nhưng ghép lại thì
// không màn nào giống màn nào — người dùng gọi là "lộn xộn, trông như AI làm". Skill `thiet-ke-ux` nhắc chọn token;
// luật này giữ cho nhắc không trôi: PR thêm giá trị tự đặt thì đỏ, PR sửa màn cũ thì kéo mức trần xuống.
//
// Bốn loại (thang và màu theo mục 4.4 của `docs/ux-audit-2026-10-31.md`, token ở `preview/cong-no-theme.css`):
//   mau   màu viết thẳng (#hex, rgb(), hsl()) ngoài dòng khai báo biến `--ten: …`. Trắng, đen, transparent,
//         currentColor không tính. Khai biến cục bộ trong file vẫn được: đó là token, chỉ là token hẹp.
//   chu   cỡ chữ px/rem ngoài thang 13 / 14 / 15 / 16 / 18 / 22 / 28. 15 là thân chữ của theme hiện tại.
//   bo    bo góc bằng số ngoài `var(--radius)`. 0, 50%, 999px trở lên (viên thuốc) không tính.
//   vien  viền màu một bên dày từ 2px (border-left/right/inline-start/inline-end): kiểu đánh dấu trạng thái
//         dễ nhận ra là "AI làm". Dùng viền đủ bốn cạnh, nền nhạt hoặc chữ/biểu tượng đứng đầu.
//
// Phạm vi giống `check-font-size.js`: CSS trong `cong-no-web-handoff/preview/` (không đệ quy, `mockups/` là bản vẽ
// cũ), khối `<style>` và `style="…"` trong HTML ở đó. Style gán bằng JavaScript không xét.

const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const PREVIEW = path.join(ROOT, "cong-no-web-handoff", "preview");
const BASELINE = path.join(__dirname, "css-tokens-baseline.json");

const KINDS = {
  mau: "màu viết thẳng, không qua biến",
  chu: "cỡ chữ ngoài thang 13/14/15/16/18/22/28",
  bo: "bo góc bằng số, không qua var(--radius)",
  vien: "viền màu một bên dày từ 2px",
};
const TYPE_SCALE = new Set([13, 14, 15, 16, 18, 22, 28]);
const NEUTRAL_COLORS = new Set(["#fff", "#ffffff", "#000", "#000000"]);

// Thay chú thích bằng khoảng trắng cùng số dòng để số dòng báo lỗi đúng.
const blankComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));

// Mọi khai báo `thuộc-tính: giá-trị` trong một khối CSS: { line, selector, prop, value }.
function declarations(css, lineOffset = 0) {
  const text = blankComments(css);
  const out = [];
  const rule = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = rule.exec(text))) {
    const selector = m[1].trim().replace(/\s+/g, " ");
    const bodyStart = m.index + m[0].indexOf("{") + 1;
    const decl = /([-\w]+)\s*:\s*([^;]*)/g;
    let d;
    while ((d = decl.exec(m[2]))) {
      const line = lineOffset + text.slice(0, bodyStart + d.index).split("\n").length;
      out.push({ line, selector, prop: d[1].toLowerCase(), value: d[2].trim() });
    }
  }
  return out;
}

function htmlDeclarations(html) {
  const out = [];
  const style = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  let m;
  while ((m = style.exec(html))) {
    const offset = html.slice(0, m.index + m[0].indexOf(">") + 1).split("\n").length - 1;
    out.push(...declarations(m[1], offset));
  }
  const attr = /style\s*=\s*"([^"]*)"/gi;
  while ((m = attr.exec(html))) {
    const line = html.slice(0, m.index).split("\n").length;
    for (const d of declarations(`x{${m[1]}}`)) out.push({ ...d, line, selector: 'style="…"' });
  }
  return out;
}

const pxValues = (value) =>
  [...value.matchAll(/(?:^|[\s/(,])(\d*\.?\d+)(px|rem)\b/g)].map((m) => (m[2] === "rem" ? Number(m[1]) * 16 : Number(m[1])));

// Một khai báo vi phạm những loại nào (mảng mã loại, có thể lặp nếu một giá trị có nhiều màu).
function kindsOf({ prop, value }) {
  if (prop.startsWith("--")) return [];
  const found = [];
  const v = value.toLowerCase();

  for (const c of v.match(/#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?)\(/g) || []) {
    if (!NEUTRAL_COLORS.has(c)) found.push("mau");
  }

  if (prop === "font-size" || prop === "font") {
    // Với `font:` chỉ số đứng trước dấu `/` hoặc tên họ chữ là cỡ chữ; số sau `/` là chiều cao dòng.
    const sizePart = prop === "font" ? v.split("/")[0] : v;
    const size = pxValues(sizePart).at(-1);
    if (size !== undefined && !TYPE_SCALE.has(size)) found.push("chu");
  }

  if (/^border(-(top|bottom)-(left|right)|-(start|end)-(start|end))?-radius$/.test(prop) && !v.includes("var(")) {
    if (pxValues(v).some((px) => px > 0 && px < 999)) found.push("bo");
  }

  if (/^border-(left|right|inline-start|inline-end)(-width)?$/.test(prop)) {
    const width = pxValues(v)[0];
    if (width >= 2 && !/\b(none|hidden|transparent)\b/.test(v)) found.push("vien");
  }
  return found;
}

// Hàm thuần để test: nhận [{ name, text }], trả { [file]: { counts: {loại: n}, places: [{line, selector, kind}] } }.
function measure(files) {
  const result = {};
  for (const file of files) {
    const decls = file.name.endsWith(".html") ? htmlDeclarations(file.text) : declarations(file.text);
    const counts = {};
    const places = [];
    for (const d of decls) {
      for (const kind of kindsOf(d)) {
        counts[kind] = (counts[kind] || 0) + 1;
        places.push({ line: d.line, selector: d.selector, kind });
      }
    }
    if (places.length) result[file.name] = { counts, places };
  }
  return result;
}

// So số đo với mức trần. Trả { over: [{file, kind, now, cap, places}], under: [{file, kind, now, cap}] }.
// File chưa có trong mức trần có trần 0: file CSS mới phải dùng token ngay từ đầu.
function compare(measured, baseline) {
  const over = [];
  const under = [];
  const files = new Set([...Object.keys(measured), ...Object.keys(baseline)]);
  for (const file of [...files].sort()) {
    for (const kind of Object.keys(KINDS)) {
      const now = measured[file]?.counts[kind] || 0;
      const cap = baseline[file]?.[kind] || 0;
      if (now > cap) {
        const places = measured[file].places.filter((p) => p.kind === kind);
        over.push({ file, kind, now, cap, places });
      } else if (now < cap) {
        under.push({ file, kind, now, cap });
      }
    }
  }
  return { over, under };
}

function toBaseline(measured) {
  const out = {};
  for (const file of Object.keys(measured).sort()) {
    const row = {};
    for (const kind of Object.keys(KINDS)) if (measured[file].counts[kind]) row[kind] = measured[file].counts[kind];
    out[file] = row;
  }
  return out;
}

function shippedFiles() {
  return fs
    .readdirSync(PREVIEW)
    .filter((name) => name.endsWith(".css") || name.endsWith(".html"))
    .sort()
    .map((name) => ({ name, text: fs.readFileSync(path.join(PREVIEW, name), "utf-8") }));
}

const MAX_PLACES = 15;

function printOver(over) {
  for (const o of over) {
    console.error(`cong-no-web-handoff/preview/${o.file}: ${KINDS[o.kind]} ${o.now} > mức trần ${o.cap}`);
    for (const p of o.places.slice(0, MAX_PLACES)) console.error(`  dòng ${p.line}  ${p.selector}`);
    if (o.places.length > MAX_PLACES) console.error(`  … và ${o.places.length - MAX_PLACES} chỗ nữa`);
  }
}

if (require.main === module) {
  const baseline = fs.existsSync(BASELINE) ? JSON.parse(fs.readFileSync(BASELINE, "utf-8")) : {};
  const measured = measure(shippedFiles());
  const { over, under } = compare(measured, baseline);

  if (process.argv.includes("--update")) {
    // Chưa có file mức trần (lần đầu) thì ghi số hiện tại làm mức xuất phát.
    if (over.length && fs.existsSync(BASELINE)) {
      printOver(over);
      console.error("\nKhông hạ được mức trần khi còn file vượt: sửa các chỗ trên trước (--update không nâng mức).");
      process.exit(1);
    }
    fs.writeFileSync(BASELINE, `${JSON.stringify(toBaseline(measured), null, 2)}\n`);
    console.log(`token CSS: đã ghi mức trần mới vào scripts/css-tokens-baseline.json (${under.length} mục hạ)`);
    process.exit(0);
  }

  printOver(over);
  for (const u of under) {
    console.error(`cong-no-web-handoff/preview/${u.file}: ${KINDS[u.kind]} còn ${u.now}, mức trần ${u.cap} — tốt, hạ mức trần`);
  }
  if (over.length) {
    console.error(
      "\nGiá trị tự đặt mới trong CSS giao diện. Dùng token ở preview/cong-no-theme.css (màu var(--…), bo góc " +
        "var(--radius), cỡ chữ theo thang mục 4.4 docs/ux-audit-2026-10-31.md); cần màu mới thì khai biến `--ten:` " +
        "rồi dùng biến. Viền một bên: thay bằng viền đủ cạnh, nền nhạt hoặc chữ đứng đầu.",
    );
  }
  if (under.length) console.error("\nĐã giảm: chạy `node scripts/check-css-tokens.js --update` rồi commit file mức trần.");
  if (over.length || under.length) process.exit(1);

  const total = (kind) => Object.values(measured).reduce((s, f) => s + (f.counts[kind] || 0), 0);
  console.log(`token CSS: không vượt mức trần (${Object.keys(KINDS).map((k) => `${k} ${total(k)}`).join(", ")})`);
}

module.exports = { measure, compare, toBaseline, kindsOf, declarations, KINDS, TYPE_SCALE };
