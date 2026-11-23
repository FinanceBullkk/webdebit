const test = require("node:test");
const assert = require("node:assert/strict");
const { findSmallFonts, cssDeclarations } = require("./check-font-size.js");

test("đọc font-size và font: theo px, rem; bỏ pt và chú thích", () => {
  const css = [
    ".a{font-size:12px}",
    ".b{color:red;font:600 12.5px/1.4 Segoe UI}",
    ".c{font-size:.75rem}",
    "/* .d{font-size:10px} */",
    ".e{font:9pt Arial}",
    ".f{font-size:14px}",
  ].join("\n");
  const got = cssDeclarations(css).map((d) => [d.line, d.selector, d.px]);
  assert.deepEqual(got, [
    [1, ".a", 12],
    [2, ".b", 12.5],
    [3, ".c", 12],
    [6, ".f", 14],
  ]);
});

test("báo chỗ dưới 13px, kể cả <style> và style= trong HTML", () => {
  const { violations } = findSmallFonts(
    [
      { name: "x.css", text: ".ok{font-size:13px}\n.nho{font-size:12px}" },
      { name: "p.html", text: '<style>\n.s{font-size:11px}\n</style>\n<b style="font-size:10px">x</b>' },
    ],
    new Set(),
  );
  assert.deepEqual(
    violations.map((v) => `${v.file}:${v.line} ${v.selector} ${v.px}`),
    ["x.css:2 .nho 12", "p.html:2 .s 11", 'p.html:4 style="…" 10'],
  );
});

test("chỗ còn nợ được bỏ qua; dòng nợ không còn khớp thì báo thừa", () => {
  const { violations, stalePending } = findSmallFonts(
    [{ name: "x.css", text: ".nho{font-size:12px}" }],
    new Set(["x.css|.nho", "x.css|.da-sua"]),
  );
  assert.deepEqual(violations, []);
  assert.deepEqual(stalePending, ["x.css|.da-sua"]);
});
