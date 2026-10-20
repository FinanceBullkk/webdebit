#!/usr/bin/env node
// Một lệnh kiểm duy nhất cho cả Python và JavaScript: `npm run check`.
//
// Lý do tồn tại: trước đây lint không có, còn test thì phải nhớ hai lệnh ở hai
// thư mục khác nhau (`py -3.13 -m unittest` trong cong-no-web-handoff, `npm test`
// ở gốc). Agent và người đều dễ bỏ sót một nửa. CI gọi đúng lệnh này, nên thứ
// chạy xanh ở máy là thứ chạy xanh trên GitHub.
//
//   node scripts/check.js            chạy tất cả
//   node scripts/check.js --lint     chỉ lint (nhanh, dùng khi đang sửa)
//
// Mã thoát khác 0 nếu bất kỳ bước nào hỏng. Bước bị bỏ qua (SKIP) không làm hỏng.

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const HANDOFF = path.join(ROOT, "cong-no-web-handoff");
const lintOnly = process.argv.includes("--lint");

// Ruff nằm trong .venv của dự án khi chạy ở máy, nằm trên PATH khi chạy trong CI.
function ruffCommand() {
  const candidates = [
    path.join(ROOT, ".venv", "Scripts", "ruff.exe"),
    path.join(ROOT, ".venv", "bin", "ruff"),
  ];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return "ruff";
}

// Trình thông dịch Python: .venv của dự án khi có, nếu không thì cái nào trên
// PATH chạy được. Thử thật bằng `--version` thay vì đoán theo nền tảng, vì trên
// Windows `python` thường là stub của Microsoft Store (gọi là hỏng) còn trên
// runner CI thì `python` lại đúng là bản setup-python vừa cài.
function pythonCommand() {
  const venv = [
    path.join(ROOT, ".venv", "Scripts", "python.exe"),
    path.join(ROOT, ".venv", "bin", "python"),
  ];
  for (const c of venv) if (fs.existsSync(c)) return { cmd: c, args: [] };

  const fallbacks = [
    { cmd: "python3", args: [] },
    { cmd: "python", args: [] },
    { cmd: "py", args: ["-3.13"] },
  ];
  for (const f of fallbacks) {
    const probe = spawnSync(f.cmd, [...f.args, "-c", "import sys"], { encoding: "utf-8" });
    if (!probe.error && probe.status === 0) return f;
  }
  return null;
}

// eslint không khai báo bin/eslint.js trong "exports", nên require.resolve vào
// thẳng đường dẫn đó sẽ hỏng; lấy từ trường "bin" của package.json là cách được
// hỗ trợ.
function eslintBin() {
  const pkgPath = require.resolve("eslint/package.json");
  const bin = require(pkgPath).bin;
  const rel = typeof bin === "string" ? bin : bin.eslint;
  return path.join(path.dirname(pkgPath), rel);
}

const PYTHON = pythonCommand();

// Test trình duyệt cần bản Chromium đã tải. Ở máy chưa tải thì báo SKIP thay vì
// FAIL: một lỗi không liên quan tới thay đổi của người sửa sẽ khiến họ bỏ luôn
// thói quen chạy check.
function chromiumMissing() {
  try {
    const { chromium } = require("playwright");
    return !fs.existsSync(chromium.executablePath());
  } catch {
    return true;
  }
}

const steps = [
  {
    name: "lint:py   ruff",
    cmd: ruffCommand(),
    args: ["check", "."],
    cwd: ROOT,
  },
  {
    // Luật nghiệp vụ đã chốt, kiểm trên cả SQL/Python/JS. Chạy cùng nhóm lint
    // vì nó cũng chỉ đọc file: nhanh, không cần Python hay trình duyệt, và là
    // thứ phải fail trước khi diff tới reviewer. Lý do từng luật nằm trong
    // `scripts/business-rules.js`, cạnh chính luật đó.
    name: "lint:biz  business rules",
    cmd: process.execPath,
    args: [path.join(__dirname, "check-business-rules.js")],
    cwd: ROOT,
  },
  {
    // Gọi thẳng điểm vào của eslint bằng node: trên Windows, spawn một file
    // .cmd (npx.cmd) không qua shell bị Node chặn, nên bước này sẽ luôn hỏng
    // mà không in ra lỗi nào.
    name: "lint:js   eslint",
    cmd: process.execPath,
    args: [eslintBin(), "."],
    cwd: ROOT,
  },
  {
    name: "test:py   unittest",
    cmd: PYTHON && PYTHON.cmd,
    args: PYTHON ? [...PYTHON.args, "-m", "unittest", "discover", "-s", "tests"] : [],
    cwd: HANDOFF,
    lint: false,
    skip: () => !PYTHON && "không tìm thấy Python — tạo .venv theo README rồi chạy lại",
  },
  {
    name: "test:js   node --test",
    cmd: "npm",
    args: ["run", "test:unit"],
    cwd: ROOT,
    lint: false,
  },
  {
    name: "test:js   playwright",
    cmd: "npm",
    args: ["run", "test:browser"],
    cwd: ROOT,
    lint: false,
    skip: () =>
      chromiumMissing() &&
      "chưa có Chromium — chạy `npx playwright install chromium` nếu cần",
  },
  {
    // Bộ test viewer dữ liệu giả, cũng cần Chromium. Tách riêng vì nó nằm ở
    // `cong-no-web-handoff/tests/` chứ không phải `preview/`, và main thêm nó
    // sau khi bước playwright ở trên đã có.
    name: "test:js   viewer",
    cmd: "npm",
    args: ["run", "test:viewer"],
    cwd: ROOT,
    lint: false,
    skip: () =>
      chromiumMissing() &&
      "chưa có Chromium — chạy `npx playwright install chromium` nếu cần",
  },
];

const results = [];
for (const step of steps) {
  if (lintOnly && step.lint === false) continue;

  const reason = step.skip && step.skip();
  if (reason) {
    console.log(`\n=== SKIP ${step.name}: ${reason}\n`);
    results.push({ name: step.name, status: "SKIP" });
    continue;
  }

  console.log(`\n=== ${step.name}\n`);
  // `npm` là npm.cmd trên Windows; file .cmd chỉ chạy được qua shell.
  const r = spawnSync(step.cmd, step.args, {
    cwd: step.cwd,
    stdio: "inherit",
    shell: step.cmd === "npm" && process.platform === "win32",
  });
  if (r.error) {
    console.error(`không chạy được ${step.cmd}: ${r.error.message}`);
    results.push({ name: step.name, status: "FAIL" });
    continue;
  }
  results.push({ name: step.name, status: r.status === 0 ? "OK" : "FAIL" });
}

console.log("\n=== Tổng kết");
for (const r of results) console.log(`  ${r.status.padEnd(4)} ${r.name}`);
const failed = results.filter((r) => r.status === "FAIL");
process.exit(failed.length ? 1 : 0);
