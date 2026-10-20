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

// ---------------------------------------------------------------------------
// Ba luật ranh giới kiến trúc. Khác với luật tiền/ngày ở trên, ba luật này
// không bắt mã sai về nghiệp vụ — chúng giữ một ranh giới đang đúng khỏi bị
// lần refactor sau làm mất. Nên case âm ở đây quan trọng hơn case dương: mã
// hiện tại vốn đã sạch, một luật không bắt gì cũng in OK y hệt.

test("ARCH-01 bắt file ngoài tầng DB gọi psql", () => {
  const found = check("ARCH-01", {
    "cong-no-web-handoff/web/app.py":
      "import subprocess\n\ndef rows():\n    return subprocess.run(['psql', '-c', 'SELECT 1'])\n",
    // Đổi tên file không phải là cách ra khỏi luật: danh sách cho phép là tường minh.
    "cong-no-web-handoff/web/db_extra.py": "CMD = ['psql', '-X']\n",
    "cong-no-web-handoff/pilot/reconcile.py": "PSQL = 'psql'\n",
  });
  assert.strictEqual(found.length, 3, JSON.stringify(found, null, 2));
  assert.ok(found.some((v) => v.file === "cong-no-web-handoff/web/app.py"));
  assert.ok(found.some((v) => v.file === "cong-no-web-handoff/web/db_extra.py"));
  assert.ok(found.some((v) => v.file === "cong-no-web-handoff/pilot/reconcile.py"));
  assert.ok(found.every((v) => /ranh giới kiến trúc/.test(v.detail)), "detail phải nói rõ đây là ranh giới");
  assert.match(found[0].detail, /web\/db\.py/, "detail phải chỉ ra tầng DB đi qua đâu");
});

test("ARCH-01 cho qua đúng năm file tầng DB, và không tính chữ trong chú thích", () => {
  const found = check("ARCH-01", {
    "cong-no-web-handoff/web/db.py": "import subprocess\nCMD = ['psql', '-X']\n",
    "cong-no-web-handoff/web/ledger_db.py": "CMD = ['psql', '-X', '-w']\n",
    "cong-no-web-handoff/tools/pg_m1_report.py": "command = [psql, '-X']\n",
    "cong-no-web-handoff/tools/test_pg_ledger_schema.py": "run(['psql', '-qAt'])\n",
    "cong-no-web-handoff/tests/test_web.py": "def test_psql_quoting(self):\n    pass\n",
    "cong-no-web-handoff/web/ledger_app.py": "# Dữ liệu tới từ adapter, không gọi psql thẳng.\nfrom ledger_db import LedgerDB\n",
  });
  assert.deepStrictEqual(found, []);
});

// Luật cũ bắt mọi dòng có chữ `psql`, nên nó báo nhầm đúng chỗ đang tuân thủ:
// tầng web dựng adapter và truyền đường dẫn psql xuống cho adapter chạy. Đó là
// đi QUA tầng DB, không phải vòng qua nó. Case này giữ cho lần sửa sau không
// quay lại lối bắt theo chữ.
test("ARCH-01 không tính việc truyền tham số psql xuống adapter là vi phạm", () => {
  const found = check("ARCH-01", {
    // Y như `web/ledger_app.py` thật: dựng HistoryDB rồi đưa đường dẫn xuống.
    "cong-no-web-handoff/web/ledger_app.py":
      "def request_history(configured):\n    return HistoryDB(dbname=configured.dbname, psql=configured.psql)\n",
    // Tên tham số và thuộc tính cũng không phải lời gọi.
    "cong-no-web-handoff/web/report.py":
      "def rows(psql, dbname, sql):\n    return adapter.rows(sql)\n\nPATH = settings.psql\n",
    // Chữ trong docstring và tên hàm test cũng vậy.
    "cong-no-web-handoff/tests/test_ledger_web.py":
      '"""Mỗi màn đọc trong một câu lệnh psql."""\n\ndef test_rejected_before_psql():\n    pass\n',
  });
  assert.deepStrictEqual(found, [], "truyền tham số xuống adapter không phải là gọi psql");

  // Nhưng dựng lệnh thật thì vẫn phải bị bắt, kể cả khi cùng file ở trên.
  const still = check("ARCH-01", {
    "cong-no-web-handoff/web/ledger_app.py":
      "def rows(configured):\n    return subprocess.run([configured.psql, '-c', 'SELECT 1'])\n",
  });
  assert.strictEqual(still.length, 1, JSON.stringify(still, null, 2));
});

// ---------------------------------------------------------------------------
test("ARCH-02 bắt tầng web import ngược vào tools/ hay pilot/", () => {
  const found = check("ARCH-02", {
    "cong-no-web-handoff/web/app.py": "from tools.pg_m1_report import export\n",
    "cong-no-web-handoff/web/ledger_app.py": "import pilot.reconcile\n",
    "cong-no-web-handoff/web/report.py": [
      "import sys",
      "sys.path.insert(0, '../tools')",
      "mod = importlib.import_module('pilot.reconcile')",
    ].join("\n"),
  });
  assert.strictEqual(found.length, 4, JSON.stringify(found, null, 2));
  assert.ok(found.some((v) => v.file === "cong-no-web-handoff/web/app.py" && v.line === 1));
  assert.ok(found.some((v) => v.file === "cong-no-web-handoff/web/ledger_app.py" && v.line === 1));
  assert.ok(found.some((v) => v.file === "cong-no-web-handoff/web/report.py" && v.line === 2), "không bắt sys.path");
  assert.ok(found.some((v) => v.file === "cong-no-web-handoff/web/report.py" && v.line === 3), "không bắt import_module");
  assert.ok(found.every((v) => /ranh giới kiến trúc/.test(v.detail)));
});

test("ARCH-02 cho qua import trong tầng web và chiều ngược lại từ tools/", () => {
  const found = check("ARCH-02", {
    "cong-no-web-handoff/web/app.py": "from db import Database, DatabaseUnavailable\nimport json\n",
    "cong-no-web-handoff/web/ledger_app.py": "from ledger_db import HistoryDB, LedgerDB\n",
    // tools/ được phép dùng ngược lại: ranh giới chỉ một chiều.
    "cong-no-web-handoff/tools/pg_m1_report.py": "from pilot.reconcile import compare\n",
    // Tên biến có chữ tools không phải import.
    "cong-no-web-handoff/web/util.py": "tools = []\nprint('tools/pilot')\n",
  });
  assert.deepStrictEqual(found, []);
});

// ---------------------------------------------------------------------------
test("ARCH-03 bắt phép tính tiền trong file UI", () => {
  const found = check("ARCH-03", {
    "preview/so-khach-v7-ui.js": [
      "const totalVnd = closedVnd + openVnd;",
      "let remainingVnd = 0n;",
      "remainingVnd -= paidVnd;",
      "const twice = amountVnd * 2n;",
      "const left = balance - BigInt(paid);",
    ].join("\n"),
  });
  assert.strictEqual(found.length, 4, JSON.stringify(found, null, 2));
  assert.ok(atLine(found, 1), "không bắt phép cộng tiền");
  assert.ok(atLine(found, 3), "không bắt -= trên tiền");
  assert.ok(atLine(found, 4), "không bắt nhân với BigInt literal");
  assert.ok(atLine(found, 5), "không bắt trừ với BigInt()");
  assert.ok(found.every((v) => /ranh giới kiến trúc/.test(v.detail)));
  assert.match(found[0].detail, /-model\.js/, "detail phải chỉ ra chỗ đúng để tính tiền");
});

test("ARCH-03 cho qua so sánh, định dạng và phép tính nằm trong model", () => {
  const found = check("ARCH-03", {
    "preview/so-khach-v7-ui.js": [
      "const b = model.ledgerBalance({ closedVnd, openVnd, receipts, buckets });",
      "if (totals.pricedTotalVnd > 0n && b.openRemainingVnd === 0n) show('đã thu đủ');",
      "const txt = b.overpaymentVnd > 0n ? 'trả dư' : 'đủ';",
      "const cell = fmtVnd(r.unitPriceVnd);",
      // Tên hàm cũng kết thúc bằng Vnd; nối chuỗi quanh nó không phải cộng tiền.
      "const note = r.id + ' · ' + fmtVnd(r.amountVnd);",
      "const label = 'Tháng ' + m.name;",
      "const n = index + 1;",
      "const d = new Date(+m[3], +m[2] - 1, +m[1]);",
    ].join("\n"),
    // Phép tính tiền ở model là đúng chỗ, luật không được đụng tới.
    "preview/so-khach-v7-model.js": [
      "let remainingVnd = vnd(receiptVnd);",
      "remainingVnd -= amountVnd;",
      "return price + fees;",
    ].join("\n"),
  });
  assert.deepStrictEqual(found, []);
});
