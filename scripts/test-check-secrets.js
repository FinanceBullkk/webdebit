// Test cho các mẫu trong `check-secrets.js` (audit DevOps 31/10/2026, mục 16).
//
// Mỗi mẫu có một chuỗi phải bắt và một chuỗi gần giống phải bỏ qua. Chuỗi giả ghép lúc
// chạy từ nhiều mảnh, để không dòng nào của file này khớp mẫu khi `--all` quét repo.

const test = require("node:test");
const assert = require("node:assert");

const { contentHits, pathHits } = require("./check-secrets");

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
