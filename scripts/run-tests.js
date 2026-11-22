#!/usr/bin/env node
// Chạy bộ test JS theo quy ước tên file, thay cho danh sách chép tay trong package.json
// (trước đây PR nào thêm test cũng sửa cùng một dòng nên các phiên song song hay va nhau).
//
//   node scripts/run-tests.js unit      preview/test-*.js trừ *-browser.js, test-*.js dưới tools/, cộng test ở scripts/
//   node scripts/run-tests.js browser   preview/test-*-browser.js
//
// Thêm test mới: đặt tên `test-<tên>.js` (hoặc `test-<tên>-browser.js` nếu cần Chromium)
// trong cong-no-web-handoff/preview/ là được chạy, không sửa file này. File `-browser.js` lấy `test` từ
// ./shared-browser.js (thử lại khi Chromium báo ERR_NO_BUFFER_SPACE); test-shared-browser.js chặn file quên điều này.
// Mã Node chạy trên máy chủ (ví dụ kênh bot Zalo, tools/zalo_bot/kenh/) đặt test `test-<tên>.js` cạnh mã, cũng tự được chạy.

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const PREVIEW = "cong-no-web-handoff/preview";
const TOOLS = "cong-no-web-handoff/tools";

function previewTests(browser) {
  return fs
    .readdirSync(path.join(ROOT, PREVIEW))
    .filter((name) => /^test-.+\.js$/.test(name) && name.endsWith("-browser.js") === browser)
    .sort()
    .map((name) => `${PREVIEW}/${name}`);
}

// test-*.js dưới tools/ (bỏ node_modules); test Python ở tools/ tên test_*.py nên không lẫn.
function toolTests(folder = TOOLS) {
  return fs
    .readdirSync(path.join(ROOT, folder), { withFileTypes: true })
    .filter((entry) => entry.name !== "node_modules")
    .flatMap((entry) => {
      const child = `${folder}/${entry.name}`;
      if (entry.isDirectory()) return toolTests(child);
      return /^test-.+\.js$/.test(entry.name) ? [child] : [];
    })
    .sort();
}

const suites = {
  unit: () => [
    "scripts/test-business-rules.js",
    "scripts/test-check-gates.js",
    "scripts/test-check-secrets.js",
    "scripts/test-flaky-repeat.js",
    "scripts/sheet-capture/test.js",
    ...previewTests(false),
    ...toolTests(),
  ],
  browser: () => previewTests(true),
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
