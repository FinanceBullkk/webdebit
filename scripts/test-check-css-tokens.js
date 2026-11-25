const test = require("node:test");
const assert = require("node:assert/strict");
const { measure, compare, toBaseline, kindsOf } = require("./check-css-tokens.js");

const kinds = (prop, value) => kindsOf({ prop, value });

test("màu: tính hex/rgb/hsl ngoài biến; trắng, đen, khai báo biến không tính", () => {
  assert.deepEqual(kinds("color", "#1a1a19"), ["mau"]);
  assert.deepEqual(kinds("box-shadow", "0 1px 3px rgba(0,0,0,.1), 0 0 0 1px #d7dce3"), ["mau", "mau"]);
  assert.deepEqual(kinds("background", "hsl(210 40% 96%)"), ["mau"]);
  assert.deepEqual(kinds("color", "#fff"), []);
  assert.deepEqual(kinds("color", "var(--ink)"), []);
  assert.deepEqual(kinds("--brand", "#2a78d6"), []);
});

test("cỡ chữ: ngoài thang thì tính, kể cả rem và trong `font:`; số sau / là chiều cao dòng", () => {
  assert.deepEqual(kinds("font-size", "13.5px"), ["chu"]);
  assert.deepEqual(kinds("font-size", "1.0625rem"), ["chu"]);
  assert.deepEqual(kinds("font", '600 17px/1.4 "Segoe UI"'), ["chu"]);
  assert.deepEqual(kinds("font", '15px/22px "Segoe UI"'), []);
  assert.deepEqual(kinds("font-size", "14px"), []);
  assert.deepEqual(kinds("font-size", "inherit"), []);
});

test("bo góc: số tự đặt thì tính; var, 0, 50%, viên thuốc không tính", () => {
  assert.deepEqual(kinds("border-radius", "6px"), ["bo"]);
  assert.deepEqual(kinds("border-top-left-radius", "4px"), ["bo"]);
  assert.deepEqual(kinds("border-radius", "var(--radius)"), []);
  assert.deepEqual(kinds("border-radius", "0"), []);
  assert.deepEqual(kinds("border-radius", "50%"), []);
  assert.deepEqual(kinds("border-radius", "999px"), []);
});

test("viền một bên: từ 2px thì tính; 1px, 0, transparent không tính", () => {
  assert.deepEqual(kinds("border-left", "3px solid var(--accent)"), ["vien"]);
  assert.deepEqual(kinds("border-inline-start", "4px solid var(--critical)"), ["vien"]);
  assert.deepEqual(kinds("border-left", "1px solid var(--line)"), []);
  assert.deepEqual(kinds("border-right", "0"), []);
  assert.deepEqual(kinds("border-left", "3px solid transparent"), []);
});

test("đo cả <style>, style= trong HTML; chú thích không tính", () => {
  const got = measure([
    { name: "a.css", text: ".x{color:#123456;border-radius:6px}\n/* .y{color:#abcdef} */" },
    { name: "p.html", text: '<style>\n.s{font-size:17px}\n</style>\n<b style="color:#c00">x</b>' },
    { name: "sach.css", text: ".z{color:var(--ink);border-radius:var(--radius)}" },
  ]);
  assert.deepEqual(got["a.css"].counts, { mau: 1, bo: 1 });
  assert.deepEqual(got["p.html"].counts, { chu: 1, mau: 1 });
  assert.deepEqual(
    got["p.html"].places.map((p) => `${p.line} ${p.selector} ${p.kind}`),
    ["2 .s chu", '4 style="…" mau'],
  );
  assert.equal(got["sach.css"], undefined);
});

test("so mức trần: vượt là lỗi, giảm cũng báo để hạ mức, file mới có trần 0", () => {
  const measured = measure([
    { name: "cu.css", text: ".a{color:#111;color:#222}\n.b{border-radius:4px}" },
    { name: "moi.css", text: ".c{color:#333}" },
  ]);
  const { over, under } = compare(measured, { "cu.css": { mau: 1, bo: 3 }, "da-xoa.css": { chu: 2 } });
  assert.deepEqual(
    over.map((o) => `${o.file} ${o.kind} ${o.now}>${o.cap}`),
    ["cu.css mau 2>1", "moi.css mau 1>0"],
  );
  assert.deepEqual(
    under.map((u) => `${u.file} ${u.kind} ${u.now}<${u.cap}`),
    ["cu.css bo 1<3", "da-xoa.css chu 0<2"],
  );
});

test("mức trần chỉ ghi loại có số, theo thứ tự tên file", () => {
  const measured = measure([
    { name: "b.css", text: ".a{border-radius:4px}" },
    { name: "a.css", text: ".a{color:#111}" },
  ]);
  assert.deepEqual(toBaseline(measured), { "a.css": { mau: 1 }, "b.css": { bo: 1 } });
  assert.deepEqual(Object.keys(toBaseline(measured)), ["a.css", "b.css"]);
});
