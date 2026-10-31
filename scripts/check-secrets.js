#!/usr/bin/env node
// Quét secrets nhẹ, chỉ dùng stdlib Node.
//
//   node scripts/check-secrets.js          quét các dòng thêm vào trong diff đã stage
//   node scripts/check-secrets.js --all    quét mọi file đã theo dõi (git ls-files)
//
// require() từ test chỉ lấy mẫu và hàm khớp, không quét (test: scripts/test-check-secrets.js).
//
// Chỉ in file, số dòng và tên mẫu; không bao giờ in giá trị khớp.
// Thoát 1 nếu có khớp. Đây là lưới thô, không thay review diff (AGENTS.md).

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");

const CONTENT_PATTERNS = [
  ["private-key", /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ["github-token", /\bgh[pousr]_[A-Za-z0-9]{30,}\b/],
  ["github-pat", /\bgithub_pat_[A-Za-z0-9_]{30,}\b/],
  ["anthropic-key", /\bsk-ant-[A-Za-z0-9_-]{20,}\b/],
  ["openai-style-key", /\bsk-[A-Za-z0-9]{32,}\b/],
  ["aws-access-key", /\bAKIA[0-9A-Z]{16}\b/],
  ["google-api-key", /\bAIza[0-9A-Za-z_-]{35}\b/],
  // Khóa Tailscale: tskey-auth-/api-/client-… và kiểu cũ tskey-<id>-<bí mật>.
  ["tailscale-key", /\btskey-(?:[a-z]+-)?[A-Za-z0-9]{6,}-[A-Za-z0-9]{6,}/],
  ["age-secret-key", /\bAGE-SECRET-KEY-1[0-9A-Z]{50,}/],
  ["gcp-service-account", /"private_key_id"\s*:\s*"[^"\s]{8,}"/],
  ["slack-token", /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/],
  ["db-url-with-password", /\b(?:postgres(?:ql)?|mysql|mongodb):\/\/[^\s:@/]+:[^\s@/]+@/i],
  ["secret-assignment", /\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*["'][^"'\s]{8,}["']/i],
];

const PATH_PATTERNS = [
  ["env-file", /(^|\/)\.env(\..+)?$/],
  ["key-file", /\.(pem|key|p12|pfx)$/i],
  ["age-file", /\.age$/i],
  ["db-or-dump", /\.(dump|backup|sqlite3?|db)$/i],
  ["captures-dir", /(^|\/)captures\//],
];

function git(args) {
  const r = spawnSync("git", args, { cwd: ROOT, encoding: "utf8", maxBuffer: 256 * 1024 * 1024 });
  if (r.status !== 0) {
    console.error(`git ${args.join(" ")} thất bại: ${(r.stderr || "").trim()}`);
    process.exit(2);
  }
  return r.stdout;
}

// Tên các mẫu khớp một dòng nội dung / một đường dẫn file.
function contentHits(text) {
  return CONTENT_PATTERNS.filter(([, re]) => re.test(text)).map(([name]) => name);
}

function pathHits(file) {
  const p = file.replace(/\\/g, "/");
  return PATH_PATTERNS.filter(([, re]) => re.test(p)).map(([name]) => name);
}

module.exports = { CONTENT_PATTERNS, PATH_PATTERNS, contentHits, pathHits };

const hits = [];

function scanLine(file, lineNo, text) {
  for (const name of contentHits(text)) hits.push(`${file}:${lineNo} [${name}]`);
}

function scanPaths(files) {
  for (const f of files) {
    for (const name of pathHits(f)) hits.push(`${f} [${name}]`);
  }
}

function main() {
  const scanAll = process.argv.includes("--all");
  if (scanAll) {
    const files = git(["ls-files", "-z"]).split("\0").filter(Boolean);
    scanPaths(files);
    for (const f of files) {
      if (f === "scripts/check-secrets.js") continue;
      let buf;
      try {
        buf = fs.readFileSync(path.join(ROOT, f));
      } catch {
        continue;
      }
      if (buf.includes(0)) continue;
      buf.toString("utf8").split(/\r?\n/).forEach((line, i) => scanLine(f, i + 1, line));
    }
  } else {
    scanPaths(git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]).split("\0").filter(Boolean));
    let file = "";
    let lineNo = 0;
    for (const line of git(["diff", "--cached", "-U0", "--no-color"]).split("\n")) {
      if (line.startsWith("+++ b/")) {
        file = line.slice(6);
      } else if (line.startsWith("@@")) {
        const m = /\+(\d+)/.exec(line);
        lineNo = m ? Number(m[1]) : 0;
      } else if (line.startsWith("+") && !line.startsWith("+++")) {
        if (file !== "scripts/check-secrets.js") scanLine(file, lineNo, line.slice(1));
        lineNo += 1;
      }
    }
  }

  if (hits.length) {
    console.error("check-secrets: PHÁT HIỆN nghi ngờ (không in giá trị):");
    for (const h of hits) console.error("  " + h);
    process.exit(1);
  }
  console.log(`check-secrets: sạch (${scanAll ? "toàn bộ file đã theo dõi" : "diff đã stage"}).`);
}

if (require.main === module) main();
