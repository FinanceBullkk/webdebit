// Test cho các mẫu trong `check-secrets.js` (audit DevOps 31/10/2026, mục 16).
//
// Mỗi mẫu có một chuỗi phải bắt và một chuỗi gần giống phải bỏ qua. Chuỗi giả ghép lúc
// chạy từ nhiều mảnh, để không dòng nào của file này khớp mẫu khi `--all` quét repo.

const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {
  contentHits, pathHits, isDocPath, fakeValues, dataHits, nameWords, nameIndex, nameHit, readNameList, NAMES_ENV,
} = require("./check-secrets");

const fake = (n, ch = "x") => ch.repeat(n);

test("tailscale-key: bắt khóa auth/client và kiểu cũ, bỏ qua chữ trong tài liệu", () => {
  const auth = "tskey-" + "auth-" + "kAbC123CNTRL" + "-" + fake(24, "Q");
  const client = "TS_OAUTH=" + "tskey-" + "client-" + "k9z8y7" + "-" + fake(30, "a");
  const legacy = "tskey-" + "kAbC123CNTRL" + "-" + fake(20, "7");
  for (const line of [auth, client, legacy]) assert.deepStrictEqual(contentHits(line), ["tailscale-key"]);
  assert.deepStrictEqual(contentHits("thiếu mẫu: `tskey-…` (Tailscale)"), []);
  assert.deepStrictEqual(contentHits("tskey-auth-<khóa>"), []);
});

test("age-secret-key: bắt khóa bí mật age, bỏ qua khóa công khai", () => {
  const ageKey = "AGE-SECRET-KEY-" + "1" + fake(58, "Q");
  assert.deepStrictEqual(contentHits(ageKey), ["age-secret-key"]);
  assert.deepStrictEqual(contentHits("# public key: age1" + fake(58, "q")), []);
  assert.deepStrictEqual(contentHits("AGE-SECRET-KEY-" + "1…"), []);
});

test("gcp-service-account: bắt private_key_id có giá trị trong JSON", () => {
  const json = '  "private_key_id"' + ': "' + fake(40, "a1") + '",';
  const compact = '{"type":"service_account","private_key_id"' + ':"' + fake(40, "f") + '"}';
  assert.deepStrictEqual(contentHits(json), ["gcp-service-account"]);
  assert.deepStrictEqual(contentHits(compact), ["gcp-service-account"]);
  assert.deepStrictEqual(contentHits('"private_key_id"' + ': ""'), []);
  assert.deepStrictEqual(contentHits("trường private_key_id của service account"), []);
});

test("age-file: bắt file .age, bỏ qua tên chỉ chứa chữ age", () => {
  assert.deepStrictEqual(pathHits("backups/webdebit.sql.age"), ["age-file"]);
  assert.deepStrictEqual(pathHits("secrets\\hao.AGE"), ["age-file"]);
  assert.deepStrictEqual(pathHits("docs/age.md"), []);
  assert.deepStrictEqual(pathHits("scripts/image.agent.js"), []);
  assert.deepStrictEqual(pathHits("cong-no-web-handoff/preview/page.js"), []);
});

// Dữ liệu nghiệp vụ thật trong tài liệu (gỡ 18/11/2026). Số và mã ghép lúc chạy như phần trên.
const grouped = (...parts) => parts.join(".");

test("vnd-amount: bắt số tiền nhóm chấm từ 7 chữ số, bỏ qua số đếm, ngày, phiên bản và cỡ file", () => {
  assert.deepStrictEqual(dataHits(`- 236 khách, tổng nợ ${grouped("66", "001", "162", "261")} đ.`), ["vnd-amount"]);
  assert.deepStrictEqual(dataHits(`dòng điều chỉnh **+${grouped("181", "000", "000")}** ghi rõ`), ["vnd-amount"]);
  assert.deepStrictEqual(dataHits(`| Sổ 228 | −${grouped("164", "833", "232")} |`), ["vnd-amount"]);
  assert.deepStrictEqual(dataHits(`tổng ${grouped("1", "234", "567")}đ`), ["vnd-amount"]);
  for (const ok of ["10.521 dòng ở 239 sổ", "100.000 ô mỗi tab", "ngày 16.11.2026", "age 1.3.1", "PostgreSQL 18.6",
    `dump ${grouped("1", "909", "164")} byte`, `gói ${grouped("400", "350", "834")} bytes`, "giá 45 tr, 1,25 tỷ"]) {
    assert.deepStrictEqual(dataHits(ok), [], ok);
  }
  // Chỉ miễn khi "byte" đi ngay sau trên cùng dòng: quét theo dòng, nên "byte" xuống dòng thì số vẫn bị bắt.
  assert.deepStrictEqual(dataHits(`${grouped("2", "366", "314")}\n  byte`.split("\n")[0]), ["vnd-amount"]);
});

test("container-no: bắt số container ISO, bỏ qua mã chủ giả, chuỗi năm chữ và chuỗi tám số", () => {
  const real = "ABC" + "U" + "1234567";
  assert.deepStrictEqual(dataHits(`ô \`${real}-mã chưa up\``), ["container-no"]);
  assert.deepStrictEqual(dataHits("chuyến " + "ABC" + "U 123456 7" + " trên tab"), ["container-no"]);
  assert.deepStrictEqual(dataHits("chuyến " + "ABC" + "U 123456-7"), ["container-no"]);
  for (const ok of ["MAUU" + "1000101", "HTHU" + "2611078", "ALTU" + "0000001", "FAKE" + "U0000001", "MAUU" + "12345670",
    "HCMQDG" + "2611001", "ISO 6346", "51C" + "18585"]) {
    assert.deepStrictEqual(dataHits(ok), [], ok);
  }
});

test("du-lieu-gia: chỉ các giá trị đã khai trong file được bỏ qua, dòng khai không tự bị bắt", () => {
  const ex = grouped("50", "000", "000");
  const other = grouped("51", "000", "000");
  const text = `# Spec\nVí dụ ${ex}\n<!-- du-lieu-gia: ${ex}, ${grouped("100", "000", "000")} -->\n<!-- du-lieu-gia: ABCU1234567 -->\n`;
  const allowed = fakeValues(text);
  assert.deepStrictEqual([...allowed].sort(), [grouped("100", "000", "000"), ex, "ABCU1234567"].sort());
  assert.deepStrictEqual(dataHits(`Khách trả ${ex}`, allowed), []);
  assert.deepStrictEqual(dataHits(`Khách trả ${ex} rồi ${other}`, allowed), ["vnd-amount"]);
  assert.deepStrictEqual(dataHits("mã ABCU 123456 7", allowed), []);
  assert.deepStrictEqual(dataHits(`<!-- du-lieu-gia: ${other} -->`), []);
  assert.deepStrictEqual(dataHits(`<!-- ghi chú: ${other} -->`), ["vnd-amount"]);
  assert.deepStrictEqual(fakeValues("<!-- du-lieu-gia: -->"), new Set());
});

test("phạm vi dữ liệu thật: tài liệu (docs, specs, contexte, livrables, mọi .md), không phải mã hay test", () => {
  for (const doc of ["docs/deploys/2026-11-16-kiem-tab.md", "specs/v7-bang-thu.md", "docs/debit-note-v4/data/sample-14.json",
    "docs/debit-note-v4/reference/1-trang-14-container.html", "README.md", "contexte/a.md", "livrables/b.md",
    "cong-no-web-handoff/README.md", "docs\\decisions\\may-khoa-01.md"]) {
    assert.ok(isDocPath(doc), doc);
  }
  for (const code of ["cong-no-web-handoff/preview/so-khach-v7-fixture.js", "scripts/test-check-secrets.js",
    "cong-no-web-handoff/tests/test_v7_normalize.py", "specsheet.js"]) {
    assert.ok(!isDocPath(code), code);
  }
});

test("FAKE_VALUES_BY_FILE: chỉ cho file dưới cổng triển khai tay, gộp với dòng khai trong file", () => {
  const { FAKE_VALUES_BY_FILE, allowedValues } = require("./check-secrets");
  for (const file of Object.keys(FAKE_VALUES_BY_FILE)) {
    assert.ok(file.startsWith("specs/v7-backend/") && isDocPath(file), file);
  }
  const ex = grouped("50", "000", "000");
  const allowed = allowedValues("specs/v7-backend/thiet-ke.md", `<!-- du-lieu-gia: ${ex} -->`);
  assert.ok(allowed.has(ex));
  for (const value of FAKE_VALUES_BY_FILE["specs/v7-backend/thiet-ke.md"]) assert.ok(allowed.has(value), value);
  assert.deepStrictEqual(dataHits(`tổng ${grouped("2", "411", "645", "000")}`, allowed), []);
  assert.deepStrictEqual(allowedValues("cong-no-web-handoff/preview/so-khach-v7-fixture.js", ""), null);
  assert.deepStrictEqual([...allowedValues("specs/khac.md", "")], []);
});

// Tên khách thật (từ 18/11/2026): danh sách thật chỉ ở secret/file ngoài repo; ở đây toàn tên bịa.
const NAME_LIST = [
  "# danh sách giả cho test", // 1: chú thích
  "", //                         2: trống
  "CÔNG TY MẪU THỬ", //          3
  "Lê Văn Giả", //               4
  "Cô Ba", //                    5: dưới 6 chữ
  "Xanh Lá", //                  6: đủ 6 chữ, hai từ
  "Bịa", //                      7: một từ dưới 8 chữ
  "GIẢLẬPVIỆT", //               8: một từ từ 8 chữ
  "lê   văn giả", //             9: trùng dòng 4 sau chuẩn hóa
];

test("nameWords: bỏ dấu, đ thành d, chữ thường, dấu câu và khoảng trắng là ranh giới từ, NFC/NFD như nhau", () => {
  assert.deepStrictEqual(nameWords("  CÔNG-TY   Mẫu_thử. "), ["cong", "ty", "mau", "thu"]);
  assert.deepStrictEqual(nameWords("Đặng Đức"), ["dang", "duc"]);
  assert.deepStrictEqual(nameWords("Lê Văn Giả".normalize("NFD")), nameWords("Lê Văn Giả".normalize("NFC")));
  assert.deepStrictEqual(nameWords("Ưng Ơn"), ["ung", "on"]);
  assert.deepStrictEqual(nameWords("— · —"), []);
});

test("nameIndex: bỏ chú thích, dòng trống, tên dưới ngưỡng; giữ số dòng đầu tiên của tên trùng", () => {
  const index = nameIndex(NAME_LIST);
  assert.deepStrictEqual([...index.keys], [["cong ty mau thu", 3], ["le van gia", 4], ["xanh la", 6], ["gialapviet", 8]]);
  assert.strictEqual(index.skipped, 2);
  assert.deepStrictEqual([...index.starts.get("le")], [3]);
});

test("nameHit: khớp trọn từ, không phân biệt dấu/hoa thường/dấu câu; trả số dòng trong danh sách", () => {
  const index = nameIndex(NAME_LIST);
  assert.strictEqual(nameHit("Khách Công ty Mẫu Thử trả tiền tháng 10", index), 3);
  assert.strictEqual(nameHit("| LÊ VĂN GIẢ | 2 chuyến |", index), 4);
  assert.strictEqual(nameHit("docs/deploys/2026-11-01-le-van-gia.md", index), 4);
  assert.strictEqual(nameHit("Lê  Văn\tGiả".normalize("NFD"), index), 4);
  assert.strictEqual(nameHit("khách giảlậpviệt", index), 8);
  for (const ok of ["Lê Văn Giản", "XLê Văn Giả", "Lê Văn", "có ba bước", "chữ bịa", "Công ty Mẫu", ""]) {
    assert.strictEqual(nameHit(ok, index), 0, ok);
  }
  assert.strictEqual(nameHit("Lê Văn Giả", nameIndex([])), 0);
});

test("readNameList: biến môi trường trước file; biến rỗng thì đọc file; không có cả hai thì null", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "check-secrets-"));
  try {
    const file = path.join(dir, "webdebit-ten-khach.txt");
    const missing = path.join(dir, "khong-co.txt");
    fs.writeFileSync(file, "\uFEFF# chú thích\r\nLê Văn Giả\r\n");
    assert.deepStrictEqual(readNameList({ [NAMES_ENV]: "Xanh Lá\nCô Ba" }, file).lines, ["Xanh Lá", "Cô Ba"]);
    assert.match(readNameList({ [NAMES_ENV]: "Xanh Lá" }, file).source, new RegExp(NAMES_ENV));
    const fromFile = readNameList({ [NAMES_ENV]: " \n" }, file);
    assert.strictEqual(fromFile.source, file);
    assert.deepStrictEqual([...nameIndex(fromFile.lines).keys], [["le van gia", 2]]);
    assert.strictEqual(readNameList({}, missing), null);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("customer-name-list: chặn file danh sách tên chép nhầm vào repo", () => {
  assert.deepStrictEqual(pathHits("webdebit-ten-khach.txt"), ["customer-name-list"]);
  assert.deepStrictEqual(pathHits("docs\\webdebit-ten-khach.txt"), ["customer-name-list"]);
  assert.deepStrictEqual(pathHits("docs/ten-khach.md"), []);
});

test("quét --all: báo file:dòng và #n, không in tên; danh sách lấy từ biến, không từ file", () => {
  // Dùng dòng đầu của một tài liệu có thật làm "tên", để biết chắc có một chỗ khớp.
  const doc = "docs/development.md";
  const title = fs.readFileSync(path.join(__dirname, "..", doc), "utf8").split(/\r?\n/)[0].replace(/^#+\s*/, "");
  assert.ok(nameWords(title).join("").length >= 8, title);
  const run = spawnSync(process.execPath, [path.join(__dirname, "check-secrets.js"), "--all"], {
    cwd: path.join(__dirname, ".."), encoding: "utf8", env: { ...process.env, [NAMES_ENV]: `# test\n${title}` },
  });
  const out = run.stdout + run.stderr;
  assert.strictEqual(run.status, 1, out);
  assert.match(out, new RegExp(`customer-name dùng 1 tên từ biến ${NAMES_ENV}`));
  assert.ok(out.includes(`${doc}:1 [customer-name #2]`), out);
  for (const leaked of [title, nameWords(title).join(" ")]) assert.ok(!out.toLowerCase().includes(leaked.toLowerCase()), out);
});
