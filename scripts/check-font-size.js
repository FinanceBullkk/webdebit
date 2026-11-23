#!/usr/bin/env node
// Sàn cỡ chữ của giao diện web: không `font-size` (hay `font:`) nào dưới 13px.
//
//   node scripts/check-font-size.js
//
// Lý do tồn tại: audit 23/11/2026 (F6) đếm 292/768 khai báo cỡ chữ dưới 14px, 104 dưới 13px, kể cả tiêu đề
// bảng tiền và nhãn menu 11,5px. Người dùng chính trên 40 tuổi, màn 1280×720 logic (`docs/ux-guidelines.md`
// nguyên tắc 3; thang chữ ở mục 4.4 của `docs/ux-audit-2026-10-31.md`: chú thích 13 là tối thiểu, trong bảng và
// cạnh số 14). Sửa một lần không giữ được: PR sau chép một dòng `font-size:12px` là chữ nhỏ quay lại. Máy chặn
// mức 13; mức 14 cho bảng là việc của người thiết kế, máy không phân biệt được ô nào "cạnh số".
//
// Phạm vi: CSS giao diện trong `cong-no-web-handoff/preview/` (không đệ quy: `mockups/` là bản vẽ cũ), khối
// `<style>` và thuộc tính `style="…"` trong các trang HTML ở đó. Đơn vị px và rem (1rem = 16px). Đơn vị pt chỉ có ở
// bản in debit note (giấy A4, đọc bằng mắt in ra) nên không xét.

const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const PREVIEW = path.join(ROOT, "cong-no-web-handoff", "preview");
const FLOOR_PX = 13;

// Chỗ còn nợ, sửa ở PR sau (file đang do phiên khác sửa). Mỗi dòng: "file|selector". Bỏ dòng khi đã sửa;
// dòng không còn khớp chỗ nào cũng là lỗi để danh sách không mục dần.
const PENDING = new Set([
  "doi-xe.css|.dx-noi.chua,.dx-sk",
  "doi-xe-thu.css|.dxt-thang span",
]);

// Thay chú thích bằng khoảng trắng cùng số dòng để số dòng báo lỗi đúng.
const blankComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));

function pxOf(value) {
  const m = value.match(/(?:^|[\s/])(\d*\.?\d+)(px|rem)\b/);
  if (!m) return null;
  return m[2] === "rem" ? Number(m[1]) * 16 : Number(m[1]);
}

// Trả các khai báo cỡ chữ trong một khối CSS: { line, selector, px }.
function cssDeclarations(css, lineOffset = 0) {
  const text = blankComments(css);
  const out = [];
  const rule = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = rule.exec(text))) {
    const selector = m[1].trim().replace(/\s+/g, " ");
    const bodyStart = m.index + m[0].indexOf("{") + 1;
    const decl = /(^|[;\s])font(-size)?\s*:\s*([^;]*)/g;
    let d;
    while ((d = decl.exec(m[2]))) {
      const px = pxOf(d[3]);
      if (px === null) continue;
      const line = lineOffset + text.slice(0, bodyStart + d.index).split("\n").length;
      out.push({ line, selector, px });
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
    out.push(...cssDeclarations(m[1], offset));
  }
  const attr = /style\s*=\s*"([^"]*)"/gi;
  while ((m = attr.exec(html))) {
    const line = html.slice(0, m.index).split("\n").length;
    for (const d of cssDeclarations(`x{${m[1]}}`)) out.push({ ...d, line, selector: "style=\"…\"" });
  }
  return out;
}

// Hàm thuần để test: nhận danh sách { name, text }, trả { violations, stalePending }.
function findSmallFonts(files, pending = PENDING) {
  const violations = [];
  const used = new Set();
  for (const file of files) {
    const decls = file.name.endsWith(".html") ? htmlDeclarations(file.text) : cssDeclarations(file.text);
    for (const d of decls) {
      if (d.px >= FLOOR_PX) continue;
      const key = `${file.name}|${d.selector}`;
      if (pending.has(key)) {
        used.add(key);
        continue;
      }
      violations.push({ file: file.name, ...d });
    }
  }
  const stalePending = [...pending].filter((key) => !used.has(key));
  return { violations, stalePending };
}

function shippedFiles() {
  return fs
    .readdirSync(PREVIEW)
    .filter((name) => name.endsWith(".css") || name.endsWith(".html"))
    .sort()
    .map((name) => ({ name, text: fs.readFileSync(path.join(PREVIEW, name), "utf-8") }));
}

if (require.main === module) {
  const { violations, stalePending } = findSmallFonts(shippedFiles());
  for (const v of violations) {
    console.error(`cong-no-web-handoff/preview/${v.file}:${v.line}  ${v.selector}  ${v.px}px < ${FLOOR_PX}px`);
  }
  for (const key of stalePending) {
    console.error(`PENDING thừa: "${key}" không còn chỗ nào dưới ${FLOOR_PX}px — bỏ dòng này khỏi scripts/check-font-size.js`);
  }
  if (violations.length || stalePending.length) {
    console.error(
      `\n${violations.length} chỗ cỡ chữ dưới ${FLOOR_PX}px. Chú thích tối thiểu 13px, trong bảng và cạnh số 14px ` +
        "(docs/ux-audit-2026-10-31.md mục 4.4).",
    );
    process.exit(1);
  }
  console.log(`cỡ chữ: không chỗ nào dưới ${FLOOR_PX}px`);
}

module.exports = { findSmallFonts, cssDeclarations, htmlDeclarations, FLOOR_PX };
