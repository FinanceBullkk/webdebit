// Test cho hai cổng "xanh là đã kiểm" (audit kiến trúc 19/11/2026):
// - A11: `scripts/check.js` thiếu Python/Chromium là FAIL; chỉ `--skip` là bỏ có chủ đích và tổng kết in "CHƯA ĐỦ".
// - A09: mọi job trong `.github/workflows/test.yml` phải nằm trong `needs` của `ci-ok` — required check duy nhất của
//   `main`; job quên khai thì đỏ mà PR vẫn merge được.

const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { planStep, summarize, parseSkipKeys } = require("./check.js");

const ROOT = path.resolve(__dirname, "..");
const python = { name: "test:py   unittest", missing: () => "Python — tạo .venv" };
const lint = { name: "lint:js   eslint" };

test("A11: thiếu công cụ là FAIL kèm cách cài và mã bỏ; --skip đúng mã thì là bỏ có chủ đích", () => {
  const missing = planStep(python, []);
  assert.equal(missing.status, "FAIL");
  assert.match(missing.reason, /thiếu Python — tạo \.venv/);
  assert.match(missing.reason, /--skip=test:py/);
  assert.deepEqual(planStep(python, ["test:py"]), { status: "SKIP", reason: "bỏ có chủ đích theo --skip" });
  assert.deepEqual(planStep({ ...python, missing: () => false }, []), { status: "RUN" });
  assert.deepEqual(planStep(lint, ["test:py"]), { status: "RUN" });
  assert.deepEqual(parseSkipKeys(["--lint", "--skip=test:py, test:browser", "--skip=lint:js"]), ["test:py", "test:browser", "lint:js"]);
});

test("A11: mã thoát chỉ 0 khi không bước nào FAIL; bước bỏ có chủ đích in CHƯA ĐỦ", () => {
  const ok = { name: "lint:py   ruff", status: "OK" };
  const all = summarize([ok, { name: "test:js   node --test", status: "OK" }]);
  assert.equal(all.exitCode, 0);
  assert.ok(!all.lines.some((line) => line.includes("CHƯA ĐỦ")));

  const lacking = summarize([ok, { name: "test:py   unittest", status: "FAIL", reason: "thiếu Python" }]);
  assert.equal(lacking.exitCode, 1);
  assert.ok(lacking.lines.includes("  FAIL test:py   unittest: thiếu Python"));

  const partial = summarize([ok, { name: "test:py   unittest", status: "SKIP", reason: "bỏ có chủ đích theo --skip" }]);
  assert.equal(partial.exitCode, 0);
  assert.match(partial.lines.at(-1), /^CHƯA ĐỦ: lượt này bỏ có chủ đích test:py;/);
});

test("A11: chạy thật check.js khi thiếu Chromium thì thoát 1, không SKIP", () => {
  const browsers = fs.mkdtempSync(path.join(os.tmpdir(), "check-no-chromium-"));
  try {
    const run = (skip) =>
      spawnSync(process.execPath, [path.join(__dirname, "check.js"), `--skip=${skip}`], {
        cwd: ROOT,
        encoding: "utf-8",
        env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: browsers },
      });
    const others = "lint:py,lint:biz,lint:doc,lint:sec,lint:js,test:py,test:js";
    const lacking = run(others);
    assert.equal(lacking.status, 1, lacking.stdout + lacking.stderr);
    assert.match(lacking.stdout, /FAIL test:browser playwright: thiếu Chromium.*npx playwright install chromium/);

    const partial = run(`${others},test:browser`);
    assert.equal(partial.status, 0, partial.stdout + partial.stderr);
    assert.match(partial.stdout, /CHƯA ĐỦ: lượt này bỏ có chủ đích .*test:browser/);
  } finally {
    fs.rmSync(browsers, { recursive: true, force: true });
  }
});

// Parser tối thiểu theo thụt lề (repo không có thư viện YAML): đủ cho cấu trúc của test.yml — tên job thụt 2 dấu
// cách dưới `jobs:`, khóa của job thụt 4, phần tử danh sách `needs` thụt 6 hoặc viết `[a, b]` trên một dòng.
function workflowJobs(text) {
  const jobs = new Map();
  let inJobs = false;
  let current = null;
  let inNeeds = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+#.*$/, "");
    if (!line.trim() || /^\s*#/.test(raw)) continue;
    if (/^\S/.test(line)) {
      inJobs = /^jobs:\s*$/.test(line);
      current = null;
      continue;
    }
    if (!inJobs) continue;
    const job = /^ {2}([\w-]+):\s*$/.exec(line);
    if (job) {
      current = { needs: [], keys: {} };
      jobs.set(job[1], current);
      inNeeds = false;
      continue;
    }
    if (!current) continue;
    const key = /^ {4}([\w-]+):\s*(.*)$/.exec(line);
    if (key) {
      current.keys[key[1]] = key[2].trim();
      inNeeds = key[1] === "needs";
      if (inNeeds && key[2].trim()) {
        current.needs.push(...key[2].replace(/^\[|\]$/g, "").split(",").map((s) => s.trim()).filter(Boolean));
      }
      continue;
    }
    const item = /^ {6}- ([\w-]+)\s*$/.exec(line);
    if (inNeeds && item) current.needs.push(item[1]);
    else if (/^ {0,4}\S/.test(line)) inNeeds = false;
  }
  return jobs;
}

test("A09: parser đọc đúng needs dạng khối và dạng một dòng", () => {
  const jobs = workflowJobs(
    "on: push\njobs:\n  a:\n    runs-on: x\n  b:\n    needs: a\n  c:\n    needs: [a, b]\n" +
      "  ci-ok:\n    if: always()   # chú thích\n    needs:\n      - a\n      # chú thích\n      - c\n    steps:\n      - run: x\n",
  );
  assert.deepEqual([...jobs.keys()], ["a", "b", "c", "ci-ok"]);
  assert.deepEqual(jobs.get("b").needs, ["a"]);
  assert.deepEqual(jobs.get("c").needs, ["a", "b"]);
  assert.deepEqual(jobs.get("ci-ok").needs, ["a", "c"]);
  assert.equal(jobs.get("ci-ok").keys.if, "always()");
});

test("A09: ci-ok chạy cả khi job trước đỏ và gom mọi job của test.yml", () => {
  const jobs = workflowJobs(fs.readFileSync(path.join(ROOT, ".github", "workflows", "test.yml"), "utf-8"));
  const gate = jobs.get("ci-ok");
  assert.ok(gate, "test.yml phải có job ci-ok");
  assert.ok(jobs.size > 5, `parser chỉ thấy ${jobs.size} job, cấu trúc test.yml đổi?`);
  // Không có `if: always()` thì job trước đỏ làm ci-ok bị skipped, mà required check skipped vẫn tính là qua.
  assert.equal(gate.keys.if, "always()");
  const missing = [...jobs.keys()].filter((name) => name !== "ci-ok" && !gate.needs.includes(name));
  assert.deepEqual(missing, [], `thêm vào needs của ci-ok: ${missing.join(", ")}`);
  const unknown = gate.needs.filter((name) => !jobs.has(name));
  assert.deepEqual(unknown, [], `needs của ci-ok có job không tồn tại: ${unknown.join(", ")}`);
});
