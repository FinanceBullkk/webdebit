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
//   node scripts/check.js --skip=test:py[,lint:js]
//                                    bỏ bước theo mã (chữ đầu tên bước). Chỉ CI dùng: job JS trên
//                                    ubuntu bỏ test:py vì job `python` đã chạy unittest 3.12–3.14.
//
// Mã thoát khác 0 nếu bất kỳ bước nào hỏng. Bước bị bỏ qua (SKIP) không làm hỏng.

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const HANDOFF = path.join(ROOT, "cong-no-web-handoff");
const lintOnly = process.argv.includes("--lint");
const skipKeys = process.argv
  .filter((a) => a.startsWith("--skip="))
  .flatMap((a) => a.slice("--skip=".length).split(","))
  .map((k) => k.trim())
  .filter(Boolean);

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

  // Môi trường đang kích hoạt (CI chạy qua `uv run`, nó đặt VIRTUAL_ENV). Phải
  // đứng trước `python3`: venv trên Windows không có python3.exe, nên `python3`
  // sẽ rơi vào Python của máy, thiếu tzdata.
  const active = process.env.VIRTUAL_ENV;
  if (active) {
    for (const c of [path.join(active, "Scripts", "python.exe"), path.join(active, "bin", "python")]) {
      if (fs.existsSync(c)) return { cmd: c, args: [] };
    }
  }

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

// Danh sách tên khách (secret `WEBDEBIT_TEN_KHACH` trên CI, xem check-secrets.js) chỉ đưa cho bước `lint:sec`;
// bước khác không cần, và test nào in biến môi trường ra log cũng không làm lộ tên.
const NAMES_ENV = "WEBDEBIT_TEN_KHACH";
const envWithoutNames = { ...process.env };
// Tên biến môi trường trên Windows không phân biệt hoa thường.
for (const key of Object.keys(envWithoutNames)) if (key.toUpperCase() === NAMES_ENV) delete envWithoutNames[key];

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
    // Link tương đối trong mọi file .md phải trỏ tới file và mục có thật.
    // Sổ quyết định tách thành từng file nên link `decisions.md#<id>` dễ gãy.
    name: "lint:doc  doc links",
    cmd: process.execPath,
    args: [path.join(__dirname, "check-doc-links.js")],
    cwd: ROOT,
  },
  {
    // Secrets và dữ liệu nghiệp vụ thật trong tài liệu (số tiền nhóm chấm từ 7 chữ số, số
    // container, tên khách theo danh sách ngoài repo) trên mọi file đã theo dõi. Trước 18/11/2026 lệnh
    // này chỉ chạy tay trước commit, và nhật ký triển khai đã lọt tổng nợ thật vào repo public; chạy ở
    // đây để CI chặn.
    name: "lint:sec  secrets + dữ liệu thật",
    cmd: process.execPath,
    args: [path.join(__dirname, "check-secrets.js"), "--all"],
    cwd: ROOT,
    names: true,
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
];

// Mã bước là chữ đầu của tên ("test:py", "lint:js"...). Mã gõ sai thì dừng hẳn: bỏ nhầm một bước
// mà vẫn báo xanh là đúng kiểu lỗi lệnh này sinh ra để chặn.
const stepKey = (step) => step.name.split(/\s+/)[0];
const unknownSkip = skipKeys.filter((k) => !steps.some((step) => stepKey(step) === k));
if (unknownSkip.length) {
  console.error(`--skip có mã không tồn tại: ${unknownSkip.join(", ")}. Mã hợp lệ: ${[...new Set(steps.map(stepKey))].join(", ")}`);
  process.exit(2);
}

const results = [];
for (const step of steps) {
  if (lintOnly && step.lint === false) continue;

  const reason = skipKeys.includes(stepKey(step))
    ? "bỏ theo --skip"
    : step.skip && step.skip();
  if (reason) {
    console.log(`\n=== SKIP ${step.name}: ${reason}\n`);
    results.push({ name: step.name, status: "SKIP" });
    continue;
  }

  console.log(`\n=== ${step.name}\n`);
  // `npm` là npm.cmd trên Windows; file .cmd chỉ chạy được qua shell.
  const r = spawnSync(step.cmd, step.args, {
    cwd: step.cwd,
    env: step.names ? process.env : envWithoutNames,
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
