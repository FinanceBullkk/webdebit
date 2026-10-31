#!/usr/bin/env node
// Chạy bộ test JS theo quy ước tên file, thay cho danh sách chép tay trong package.json
// (trước đây PR nào thêm test cũng sửa cùng một dòng nên các phiên song song hay va nhau).
//
//   node scripts/run-tests.js unit      preview/test-*.js trừ *-browser.js, cộng test ở scripts/
//   node scripts/run-tests.js browser   preview/test-*-browser.js
//   node scripts/run-tests.js viewer    tests/test-viewer-browser.js
//
// Thêm test mới: đặt tên `test-<tên>.js` (hoặc `test-<tên>-browser.js` nếu cần Chromium)
// trong cong-no-web-handoff/preview/ là được chạy, không sửa file này.

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const PREVIEW = "cong-no-web-handoff/preview";

function previewTests(browser) {
  return fs
    .readdirSync(path.join(ROOT, PREVIEW))
    .filter((name) => /^test-.+\.js$/.test(name) && name.endsWith("-browser.js") === browser)
    .sort()
    .map((name) => `${PREVIEW}/${name}`);
}

const suites = {
  unit: () => [
    "scripts/test-business-rules.js",
    "scripts/test-check-secrets.js",
    "scripts/sheet-capture/test.js",
    ...previewTests(false),
  ],
  browser: () => previewTests(true),
  viewer: () => ["cong-no-web-handoff/tests/test-viewer-browser.js"],
};

const suite = suites[process.argv[2]];
if (!suite) {
  console.error(`Cách dùng: node scripts/run-tests.js <${Object.keys(suites).join("|")}>`);
  process.exit(2);
}
const files = suite();
if (process.argv.includes("--list")) {
  console.log(files.join("\n"));
  process.exit(0);
}
const run = spawnSync(process.execPath, ["--test", ...files], { cwd: ROOT, stdio: "inherit" });
process.exit(run.status ?? 1);
