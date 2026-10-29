#!/usr/bin/env node
// Kiểm link tương đối trong tài liệu Markdown đã theo dõi (git ls-files '*.md').
//
//   node scripts/check-doc-links.js
//
// Link tới file phải trỏ tới file có thật; link có `#mục` phải khớp một
// `<a id="...">` hoặc một tiêu đề của file đích (cách GitHub tạo anchor).
// Lý do tồn tại: sổ quyết định tách thành `docs/decisions/<id>.md` (29/10/2026)
// và hàng chục tài liệu trỏ vào `decisions.md#<id>`; đổi tên hay xóa một mục
// thì link gãy âm thầm. Link http(s), mailto và link trong khối code bỏ qua.

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");

const listed = spawnSync("git", ["ls-files", "-z", "*.md"], { cwd: ROOT, encoding: "utf-8" });
if (listed.status !== 0) {
  console.error("không chạy được git ls-files");
  process.exit(2);
}
const files = listed.stdout.split("\0").filter(Boolean);

// Tiêu đề → anchor như GitHub: chữ thường, bỏ ký tự không phải chữ/số/dấu cách/gạch,
// dấu cách thành gạch; tiêu đề trùng thêm -1, -2…
function slugify(heading) {
  return heading
    .trim()
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/[^\p{L}\p{M}\p{N}\s_-]/gu, "")
    .replace(/\s/g, "-");
}

function stripFences(text) {
  return text.replace(/^(```|~~~)[\s\S]*?^\1/gm, "");
}

// Tiêu đề giữ chữ trong `code` (GitHub cũng giữ); chỉ khi tìm link mới bỏ code.
function stripCode(text) {
  return stripFences(text).replace(/`[^`\n]*`/g, "``");
}

const anchorCache = new Map();
function anchorsOf(abs) {
  if (anchorCache.has(abs)) return anchorCache.get(abs);
  const ids = new Set();
  const text = fs.readFileSync(abs, "utf-8");
  for (const m of text.matchAll(/<a\s+(?:id|name)="([^"]+)"/g)) ids.add(m[1]);
  const seen = new Map();
  for (const m of stripFences(text).matchAll(/^#{1,6}\s+(.+?)\s*#*\s*$/gm)) {
    const base = slugify(m[1].replace(/\[([^\]]*)\]\([^)]*\)/g, "$1"));
    const n = seen.get(base) || 0;
    ids.add(n ? `${base}-${n}` : base);
    seen.set(base, n + 1);
  }
  anchorCache.set(abs, ids);
  return ids;
}

const problems = [];
for (const rel of files) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) continue;
  const text = stripCode(fs.readFileSync(abs, "utf-8"));
  for (const m of text.matchAll(/\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) {
    const url = m[1];
    if (/^[a-z][a-z0-9+.-]*:/i.test(url) || url.startsWith("/")) continue;
    const [rawPath, frag] = url.split("#", 2);
    const target = rawPath ? path.resolve(path.dirname(abs), decodeURIComponent(rawPath)) : abs;
    if (!fs.existsSync(target)) {
      problems.push(`${rel}: không có file ${url}`);
      continue;
    }
    if (frag && target.endsWith(".md") && !anchorsOf(target).has(decodeURIComponent(frag))) {
      problems.push(`${rel}: không có mục #${frag} trong ${path.relative(ROOT, target)}`);
    }
  }
}

// Mục lục `docs/decisions.md` gộp theo kiểu union (.gitattributes) để hai PR cùng thêm dòng
// cuối bảng không va nhau; đổi lại phải chặn dòng trùng (hai bên cùng sửa một dòng thì union
// giữ cả hai) và file quyết định không được link từ mục lục.
const INDEX = "docs/decisions.md";
if (files.includes(INDEX)) {
  const index = fs.readFileSync(path.join(ROOT, INDEX), "utf-8");
  const seen = new Set();
  for (const m of index.matchAll(/^\| <a id="([^"]+)"><\/a>/gm)) {
    if (seen.has(m[1])) problems.push(`${INDEX}: dòng #${m[1]} lặp lại (gộp union giữ cả hai bản, chọn lấy một)`);
    seen.add(m[1]);
  }
  for (const rel of files.filter((f) => /^docs\/decisions\/[^/]+\.md$/.test(f))) {
    if (!index.includes(`(decisions/${path.basename(rel)})`)) problems.push(`${INDEX}: chưa có dòng link tới ${rel}`);
  }
}

for (const p of problems) console.log(p);
console.log(`${files.length} file Markdown, ${problems.length} link gãy.`);
process.exit(problems.length ? 1 : 0);
