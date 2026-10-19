// Test cho bộ luật nghiệp vụ trong `business-rules.js`.
//
// Một check chỉ chạy xanh trên mã sạch hiện tại thì không chứng minh được gì:
// nó có thể xanh vì luật không bắt gì cả. Nên mỗi luật ở đây có hai nửa — một
// fixture vi phạm phải bị bắt, và một fixture sạch phải đi qua. Fixture dựng
// trong thư mục tạm, không để lại vi phạm trong repo.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { runRules, RULES } = require("./business-rules");

// Dựng một cây file tạm từ map { 'đường/dẫn': 'nội dung' } rồi chạy một luật.
function check(ruleId, files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "webdebit-rule-"));
  try {
    for (const [rel, text] of Object.entries(files)) {
      const abs = path.join(root, rel);
      fs.mkdirSync(path.dirname(abs), { recursive: true });
      fs.writeFileSync(abs, text, "utf-8");
    }
    const [result] = runRules(root, [ruleId]);
    assert.ok(result, `không có luật ${ruleId}`);
    return result.violations;
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

const atLine = (violations, line) => violations.some((v) => v.line === line);

test("mọi luật đều có id và tiêu đề", () => {
  for (const rule of RULES) {
    assert.match(rule.id, /^[A-Z][A-Z0-9-]+$/);
    assert.ok(rule.title.length > 5, `luật ${rule.id} thiếu tiêu đề`);
  }
});

// ---------------------------------------------------------------------------
test("VND-01 bắt cột tiền có số thập phân hoặc dấu phẩy động", () => {
  const found = check("VND-01", {
    "schema.sql": [
      "CREATE TABLE ledger.posting (",
      "    amount_vnd numeric(20,2) NOT NULL,",
      "    fee_vnd double precision NOT NULL,",
      "    bonus_vnd numeric NOT NULL,",
      "    tip_vnd money NOT NULL,",
      ");",
    ].join("\n"),
  });
  assert.strictEqual(found.length, 4, JSON.stringify(found, null, 2));
  assert.ok(atLine(found, 2), "không bắt numeric(20,2)");
  assert.ok(atLine(found, 3), "không bắt double precision");
  assert.ok(atLine(found, 4), "không bắt numeric không khai scale");
  assert.ok(atLine(found, 5), "không bắt money");
  assert.match(found[0].detail, /amount_vnd/);
});

test("VND-01 cho qua cột tiền số nguyên chính xác", () => {
  const found = check("VND-01", {
    "schema.sql": [
      "CREATE TABLE ledger.posting (",
      "    amount_vnd numeric(20,0) NOT NULL CHECK (amount_vnd > 0),",
      "    fee_vnd bigint NOT NULL,",
      "    note text NOT NULL",
      ");",
      "-- Tham số hàm và cast ngoài CREATE TABLE không thuộc phạm vi luật này.",
      "CREATE FUNCTION f(p_total_vnd numeric) RETURNS void LANGUAGE sql AS $$ SELECT 1 $$;",
    ].join("\n"),
  });
  assert.deepStrictEqual(found, []);
});

// ---------------------------------------------------------------------------
test("VND-02 bắt số thực ở đường tính tiền", () => {
  const found = check("VND-02", {
    "web/money.py": "def total(raw):\n    return float(raw)\n",
    "preview/model.js": [
      "const a = parseFloat(raw);",
      "const b = total.toFixed(2);",
      "let amountVnd = 1.5;",
    ].join("\n"),
  });
  assert.strictEqual(found.length, 4, JSON.stringify(found, null, 2));
  assert.ok(found.some((v) => v.file === "web/money.py" && /float\(\)/.test(v.detail)));
  assert.ok(found.some((v) => /parseFloat/.test(v.detail)));
  assert.ok(found.some((v) => /toFixed/.test(v.detail)));
  assert.ok(found.some((v) => /amountVnd/.test(v.detail)));
});

test("VND-02 cho qua Decimal, BigInt và không áp vào test", () => {
  const found = check("VND-02", {
    "web/money.py": "from decimal import Decimal\n\ndef total(raw):\n    return Decimal(str(raw))\n",
    "preview/model.js": "const amountVnd = BigInt(raw);\nconst shown = amountVnd.toString();\n",
    // Test được phép dựng dữ liệu vi phạm để chứng minh guard chạy.
    "preview/test-model.js": "const amountVnd = 1.5;\nconst x = parseFloat('1.5');\n",
    "tests/test_money.py": "assert float('1.5') == 1.5\n",
  });
  assert.deepStrictEqual(found, []);
});

// ---------------------------------------------------------------------------
test('DATE-01 bắt "hôm nay" lấy từ đồng hồ không khai múi giờ', () => {
  const found = check("DATE-01", {
    "tools/schema.sql": [
      "CREATE FUNCTION f() RETURNS date LANGUAGE sql AS $$ SELECT current_date $$;",
      "CREATE FUNCTION g() RETURNS date LANGUAGE sql AS $$ SELECT now()::date $$;",
      "CREATE FUNCTION h() RETURNS date LANGUAGE sql AS $$ SELECT localtimestamp::date $$;",
    ].join("\n"),
    "web/clock.py": "import datetime\n\ndef today():\n    return datetime.date.today()\n",
    "web/clock2.py": "from datetime import datetime\n\ndef stamp():\n    return datetime.now()\n",
  });
  assert.strictEqual(found.length, 5, JSON.stringify(found, null, 2));
  assert.ok(found.every((v) => /Asia\/Ho_Chi_Minh/.test(v.detail)));
});

test("DATE-01 cho qua ngày theo giờ VN và dấu thời gian tuyệt đối", () => {
  const found = check("DATE-01", {
    "tools/schema.sql": [
      "CREATE FUNCTION ledger.business_today() RETURNS date LANGUAGE sql STABLE AS $$",
      "    SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date",
      "$$;",
      "CREATE TABLE t (at timestamptz NOT NULL DEFAULT now());",
      "CREATE FUNCTION f() RETURNS date LANGUAGE sql AS $$ SELECT ledger.business_today() $$;",
    ].join("\n"),
    "web/clock.py": [
      "from datetime import UTC, datetime",
      "from zoneinfo import ZoneInfo",
      "",
      "VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')",
      "",
      "def today():",
      "    return datetime.now(VN_TZ).date()",
      "",
      "def generated_at():",
      "    return datetime.now(UTC).isoformat()",
    ].join("\n"),
  });
  assert.deepStrictEqual(found, []);
});

// ---------------------------------------------------------------------------
// Thân hàm ghi tiền tối thiểu, dùng cho hai luật guard dưới đây.
const writeFn = (name, body) => [
  `CREATE FUNCTION ledger.${name}(p_event_date date, p_posting_date date)`,
  "RETURNS bigint LANGUAGE plpgsql AS $$",
  "BEGIN",
  body,
  "    INSERT INTO ledger.proposal(event_date, posting_date)",
  "    VALUES (p_event_date, p_posting_date);",
  "    RETURN 1;",
  "END $$;",
].join("\n");

const FUTURE_RAISE = [
  "    IF p_posting_date > ledger.business_today() THEN",
  "        RAISE EXCEPTION 'posting date is in the future';",
  "    END IF;",
].join("\n");

const NULL_RAISE = [
  "    IF p_event_date IS NULL THEN",
  "        RAISE EXCEPTION 'missing business date';",
  "    END IF;",
].join("\n");

test("FUTURE-01 bắt hàm ghi tiền thiếu guard ngày tương lai", () => {
  const found = check("FUTURE-01", {
    "tools/schema.sql": [
      writeFn("submit_entry", NULL_RAISE),
      writeFn("approve_entry", NULL_RAISE),
    ].join("\n\n"),
  });
  assert.strictEqual(found.length, 2, JSON.stringify(found, null, 2));
  assert.ok(found.some((v) => /submit_entry/.test(v.detail)), "thiếu đường nhập");
  assert.ok(found.some((v) => /approve_entry/.test(v.detail)), "thiếu đường duyệt");
});

test("FUTURE-01 bắt khi chỉ có guard ở đường nhập mà thiếu ở đường duyệt", () => {
  const found = check("FUTURE-01", {
    "tools/schema.sql": [
      writeFn("submit_entry", FUTURE_RAISE),
      writeFn("approve_entry", NULL_RAISE),
    ].join("\n\n"),
  });
  assert.strictEqual(found.length, 1, JSON.stringify(found, null, 2));
  assert.match(found[0].detail, /approve_entry/);
});

test("FUTURE-01 cho qua khi cả hai đường đều có guard, kể cả viết trực tiếp giờ VN", () => {
  const found = check("FUTURE-01", {
    "tools/schema.sql": [
      writeFn("submit_entry", FUTURE_RAISE),
      writeFn(
        "approve_entry",
        "    IF p_posting_date > (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date THEN\n" +
        "        RAISE EXCEPTION 'posting date is in the future';\n" +
        "    END IF;"
      ),
      // Hàm chỉ đọc không ghi sổ, không thuộc phạm vi luật.
      "CREATE FUNCTION ledger.balance_as_of(p_date date) RETURNS numeric LANGUAGE sql AS $$",
      "    SELECT sum(signed_amount_vnd) FROM ledger.posting WHERE posting_date <= p_date",
      "$$;",
    ].join("\n\n"),
  });
  assert.deepStrictEqual(found, []);
});

// ---------------------------------------------------------------------------
test("TRIP-DATE-01 bắt hàm ghi tiền nhận ngày nghiệp vụ rỗng", () => {
  const found = check("TRIP-DATE-01", {
    "tools/schema.sql": writeFn("submit_entry", FUTURE_RAISE),
  });
  assert.strictEqual(found.length, 1, JSON.stringify(found, null, 2));
  assert.match(found[0].detail, /xe nhập kho/);
});

test("TRIP-DATE-01 cho qua khi hàm chặn ngày nghiệp vụ NULL", () => {
  const found = check("TRIP-DATE-01", {
    "tools/schema.sql": writeFn("submit_entry", `${NULL_RAISE}\n${FUTURE_RAISE}`),
  });
  assert.deepStrictEqual(found, []);
});

test("TRIP-DATE-01 cho qua khi guard nằm trong một điều kiện gộp", () => {
  const found = check("TRIP-DATE-01", {
    "tools/schema.sql": writeFn(
      "submit_entry",
      "    IF p_event_date IS NULL OR p_posting_date IS NULL THEN\n" +
      "        RAISE EXCEPTION 'missing or invalid posting evidence/date/lines';\n" +
      "    END IF;"
    ),
  });
  assert.deepStrictEqual(found, []);
});
