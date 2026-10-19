#!/usr/bin/env node
// Chạy bộ luật nghiệp vụ trong `business-rules.js` trên gốc repo và in kết quả.
//
//   node scripts/check-business-rules.js              kiểm cả repo
//   node scripts/check-business-rules.js <đường dẫn>  kiểm một thư mục khác
//
// Mã thoát 1 nếu có vi phạm. `npm run check` gọi bước này; CI gọi `npm run
// check`, nên luật ở đây chặn được diff trước khi tới reviewer.

const path = require("node:path");
const { runRules } = require("./business-rules");

function report(results) {
  let total = 0;
  for (const rule of results) {
    if (!rule.violations.length) {
      console.log(`  OK   ${rule.id.padEnd(13)} ${rule.title}`);
      continue;
    }
    total += rule.violations.length;
    console.log(`  VI PHẠM ${rule.id} — ${rule.title}`);
    for (const v of rule.violations) {
      console.log(`         ${v.file}:${v.line}`);
      console.log(`           ${v.detail}`);
    }
  }
  return total;
}

function main() {
  const root = path.resolve(process.argv[2] || path.join(__dirname, ".."));
  const results = runRules(root);
  console.log(`Luật nghiệp vụ máy kiểm được — ${root}`);
  const total = report(results);
  if (total) {
    console.log(
      `\n${total} vi phạm. Mỗi luật truy về một dòng ĐÃ CHỐT trong docs/decisions.md;` +
      " sửa mã cho khớp luật, đừng tắt luật. Nếu luật sai thì cần quyết định mới của" +
      " người dùng trước khi đổi, ghi lại ở sổ quyết định."
    );
  }
  process.exit(total ? 1 : 0);
}

if (require.main === module) main();

module.exports = { report };
