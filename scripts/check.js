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
//   node scripts/check.js --skip=test:py[,test:browser]
//                                    bỏ bước theo mã (chữ đầu tên bước). CI dùng: job JS trên ubuntu
//                                    bỏ test:py vì job `python` đã chạy unittest 3.12–3.14.
//
// Mã thoát khác 0 nếu bất kỳ bước nào hỏng. Thiếu công cụ bước cần (Python, Chromium) là hỏng, không
// phải bỏ qua (audit 19/11/2026, A11): trước đó máy thiếu công cụ vẫn thoát 0 dù không chạy tầng test.
// Chỉ bước bỏ bằng `--skip` là bỏ có chủ đích: không làm hỏng, nhưng tổng kết in "CHƯA ĐỦ" kèm mã bước.

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const HANDOFF = path.join(ROOT, "cong-no-web-handoff");

function parseSkipKeys(argv) {
  return argv
    .filter((a) => a.startsWith("--skip="))
    .flatMap((a) => a.slice("--skip=".length).split(","))
    .map((k) => k.trim())
    .filter(Boolean);
}

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

// Test trình duyệt cần bản Chromium đã tải. Trước 19/11/2026 thiếu thì báo SKIP để người sửa không bỏ thói quen
// chạy check; nhưng như vậy mã thoát 0 không còn nghĩa là đã chạy đủ, nên giờ là FAIL kèm cách cài.
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
    // Sàn cỡ chữ 13px trên CSS/HTML giao diện (audit 23/11/2026, F6): chữ nhỏ là lỗi đọc với người dùng trên 40
    // tuổi ở màn 1280×720, và một dòng chép từ CSS cũ là nó quay lại. Lý do và phạm vi ở đầu file script.
    name: "lint:css  cỡ chữ tối thiểu",
    cmd: process.execPath,
    args: [path.join(__dirname, "check-font-size.js")],
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
    // `missing()` trả câu báo thiếu gì và cách cài (theo README), hoặc false khi đủ công cụ.
    missing: () =>
      !PYTHON &&
      "Python — tạo .venv và cài requirements theo README (hoặc đặt VIRTUAL_ENV tới venv đã cài) rồi chạy lại",
  },
  {
    name: "test:js   node --test",
    cmd: "npm",
    args: ["run", "test:unit"],
    cwd: ROOT,
    lint: false,
  },
  {
    // Mã riêng `test:browser` (trước 19/11/2026 chung mã `test:js` với node --test) để bỏ có chủ đích
    // đúng bước này mà không bỏ luôn test JS không cần trình duyệt.
    name: "test:browser playwright",
    cmd: "npm",
    args: ["run", "test:browser"],
    cwd: ROOT,
    lint: false,
    missing: () =>
      chromiumMissing() && "Chromium của Playwright — chạy `npx playwright install chromium` theo README rồi chạy lại",
  },
];

// Mã bước là chữ đầu của tên ("test:py", "lint:js"...).
const stepKey = (step) => step.name.split(/\s+/)[0];

// Quyết định trước khi chạy một bước. Bỏ có chủ đích thắng thiếu công cụ, vì người gọi đã nói rõ không cần
// bước đó; còn thiếu công cụ mà không ai xin bỏ thì là FAIL.
function planStep(step, skipKeys) {
  if (skipKeys.includes(stepKey(step))) return { status: "SKIP", reason: "bỏ có chủ đích theo --skip" };
  const missing = step.missing && step.missing();
  if (missing) {
    return { status: "FAIL", reason: `thiếu ${missing}. Cố ý chạy thiếu bước này thì gọi --skip=${stepKey(step)}` };
  }
  return { status: "RUN" };
}

// Tổng kết và mã thoát từ kết quả các bước. Hàm thuần để test (scripts/test-check-gates.js).
function summarize(results) {
  const lines = results.map((r) => `  ${r.status.padEnd(4)} ${r.name}${r.reason ? `: ${r.reason}` : ""}`);
  const skipped = results.filter((r) => r.status === "SKIP");
  if (skipped.length) {
    lines.push(`CHƯA ĐỦ: lượt này bỏ có chủ đích ${skipped.map(stepKey).join(", ")}; xanh chỉ nói về các bước đã chạy.`);
  }
  const failed = results.filter((r) => r.status === "FAIL");
  return { exitCode: failed.length ? 1 : 0, lines };
}

function main(argv) {
  const lintOnly = argv.includes("--lint");
  const skipKeys = parseSkipKeys(argv);
  // Mã gõ sai thì dừng hẳn: bỏ nhầm một bước mà vẫn báo xanh là đúng kiểu lỗi lệnh này sinh ra để chặn.
  const unknownSkip = skipKeys.filter((k) => !steps.some((step) => stepKey(step) === k));
  if (unknownSkip.length) {
    console.error(`--skip có mã không tồn tại: ${unknownSkip.join(", ")}. Mã hợp lệ: ${[...new Set(steps.map(stepKey))].join(", ")}`);
    return 2;
  }

  const results = [];
  for (const step of steps) {
    if (lintOnly && step.lint === false) continue;

    const plan = planStep(step, skipKeys);
    if (plan.status !== "RUN") {
      console.log(`\n=== ${plan.status} ${step.name}: ${plan.reason}\n`);
      results.push({ name: step.name, status: plan.status, reason: plan.reason });
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
      results.push({ name: step.name, status: "FAIL", reason: `không chạy được ${step.cmd}` });
      continue;
    }
    results.push({ name: step.name, status: r.status === 0 ? "OK" : "FAIL" });
  }

  const { exitCode, lines } = summarize(results);
  console.log("\n=== Tổng kết");
  for (const line of lines) console.log(line);
  return exitCode;
}

if (require.main === module) process.exit(main(process.argv.slice(2)));

module.exports = { planStep, summarize, stepKey, parseSkipKeys };
