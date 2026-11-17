// Test cho các mẫu trong `check-secrets.js` (audit DevOps 31/10/2026, mục 16).
//
// Mỗi mẫu có một chuỗi phải bắt và một chuỗi gần giống phải bỏ qua. Chuỗi giả ghép lúc
// chạy từ nhiều mảnh, để không dòng nào của file này khớp mẫu khi `--all` quét repo.

const test = require("node:test");
const assert = require("node:assert");

const { contentHits, pathHits, isDocPath, fakeValues, dataHits } = require("./check-secrets");

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
