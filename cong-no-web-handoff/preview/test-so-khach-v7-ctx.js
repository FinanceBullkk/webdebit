// Hợp đồng ctx của sổ khách live (so-khach-v7-ctx.js): đối chiếu với mã từng file và thẻ script của trang,
// và kiểm install() dừng đúng chỗ khi phần đọc/ghi sai hợp đồng.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const contract = require('./so-khach-v7-ctx.js');

const { FIELDS, PARTS, KINDS, writer, setters, readers, install } = contract;
const partNames = PARTS.map(([name]) => name);
const read = name => fs.readFileSync(path.join(__dirname, name), 'utf8');
// Bỏ chú thích trước khi quét để chữ "ctx." trong câu chú thích không bị tính.
const strip = text => text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '$1');

// Trường một file đọc (destructure `const { … } = ctx;` lúc cài, hoặc `ctx.x`) và ghi (`ctx.x =`, `Object.assign(ctx, { … })`).
function usage(file) {
  const code = strip(read(file));
  const installed = [...code.matchAll(/const \{([^}]*)\} = ctx;/g)].flatMap(match => match[1].split(',').map(name => name.trim()).filter(Boolean));
  const writes = new Set([...code.matchAll(/\bctx\.(\w+)\s*=(?![=>])/g)].map(match => match[1]));
  for (const match of code.matchAll(/Object\.assign\(ctx, \{([^}]*)\}\)/g)) {
    for (const key of match[1].split(',')) writes.add(key.split(':')[0].trim());
  }
  const reads = new Set([...installed, ...[...code.matchAll(/\bctx\.(\w+)\b(?!\s*=(?![=>]))/g)].map(match => match[1])]);
  return { code, installed, reads, writes };
}
const sorted = set => [...set].sort();
const declaredReads = name => Object.keys(FIELDS).filter(field => readers(field).includes(name)).sort();

test('hợp đồng ctx: mỗi trường có một nơi ghi, kiểu hợp lệ, người đọc là phần đã khai', () => {
  assert.equal(new Set(partNames).size, partNames.length, 'tên phần trùng');
  for (const [field, [, kind, , meaning]] of Object.entries(FIELDS)) {
    assert.ok(['core', ...partNames].includes(writer(field)), `${field}: nơi ghi lạ`);
    assert.ok(setters(field).every(name => partNames.includes(name)), `${field}: phần gán lạ`);
    assert.equal(setters(field).length > 0, kind === 'đọc/ghi', `${field}: chỉ trường đọc/ghi mới có phần gán`);
    assert.ok(KINDS.includes(kind), `${field}: kiểu lạ ${kind}`);
    assert.ok(readers(field).length, `${field}: không ai đọc thì bỏ khỏi ctx`);
    assert.ok(readers(field).every(name => ['core', ...partNames].includes(name)), `${field}: người đọc lạ`);
    assert.ok(meaning, `${field}: thiếu ý nghĩa`);
  }
  // Phần đọc lúc cài trường của phần khác: phần đó phải đứng trước trong thứ tự cài.
  PARTS.forEach(([name, , needs], index) => {
    for (const field of needs) {
      assert.ok(Object.hasOwn(FIELDS, field) && writer(field) !== 'core', `${name}: ${field} không phải trường của phần`);
      assert.ok(partNames.indexOf(writer(field)) < index, `${name} cần ${field} lúc cài nhưng ${writer(field)} cài sau`);
      assert.ok(readers(field).includes(name), `${name} cần ${field} nhưng không khai là người đọc`);
    }
  });
});

test('trang live nạp hợp đồng và mọi phần trước so-khach-v7-ui.js; không có file phần chưa khai', () => {
  const scripts = [...read('so-khach-v7-live.html').matchAll(/<script src="([^"]+)"><\/script>/g)].map(match => match[1]);
  const ui = scripts.indexOf('so-khach-v7-ui.js');
  assert.ok(ui > scripts.indexOf('so-khach-v7-ctx.js') && scripts.includes('so-khach-v7-ctx.js'), 'so-khach-v7-ctx.js phải nạp trước so-khach-v7-ui.js');
  for (const [name, file] of PARTS) {
    assert.equal(scripts.filter(src => src === file).length, 1, `${file} phải có đúng một thẻ script`);
    assert.ok(scripts.indexOf(file) < ui, `${file} phải nạp trước so-khach-v7-ui.js`);
    assert.equal(/SoKhachV7LiveParts[^.]*\.(\w+)\s*=\s*ctx\s*=>/.exec(strip(read(file)))?.[1], name, `${file} phải đăng ký phần "${name}"`);
  }
  const files = PARTS.map(([, file]) => file);
  for (const src of scripts.filter(name => /^so-khach-v7-.+-ui\.js$/.test(name))) assert.ok(files.includes(src), `${src} chưa khai trong PARTS`);
});

test('mỗi phần đọc và ghi đúng các trường hợp đồng khai cho nó', () => {
  for (const [name, file, needs] of PARTS) {
    const { installed, reads, writes } = usage(file);
    assert.deepEqual(sorted(reads), declaredReads(name), `${file}: trường đọc khác hợp đồng`);
    const own = Object.keys(FIELDS).filter(field => writer(field) === name || setters(field).includes(name)).sort();
    assert.deepEqual(sorted(writes), own, `${file}: trường ghi khác hợp đồng`);
    const early = installed.filter(field => writer(field) !== 'core').sort();
    assert.deepEqual(early, [...needs].sort(), `${file}: trường của phần khác đọc lúc cài phải khai ở PARTS`);
  }
});

test('lõi (so-khach-v7-ui.js) cài phần qua hợp đồng và chỉ đọc trường đã khai cho core', () => {
  const { code, reads, writes } = usage('so-khach-v7-ui.js');
  assert.match(code, /SoKhachV7Ctx\.install\(ctx, window\.SoKhachV7LiveParts \?\? \{\}\)/);
  assert.doesNotMatch(code, /Object\.values\(window\.SoKhachV7LiveParts/, 'không tự cài phần theo thứ tự thẻ script');
  assert.deepEqual(sorted(reads), declaredReads('core'));
  assert.deepEqual(sorted(writes), []);
});

test('install(): cài theo PARTS, dừng khi lõi/phần sai hợp đồng', () => {
  const coreCtx = () => Object.fromEntries(Object.keys(FIELDS).filter(field => writer(field) === 'core').map(field => [field, field]));
  const order = [];
  // Phần giả: ghi đủ trường hợp đồng khai cho nó và ghi lại thứ tự được cài.
  const fake = name => ctx => {
    order.push(name);
    for (const field of Object.keys(FIELDS).filter(item => writer(item) === name)) ctx[field] = `${name}:${field}`;
  };
  const parts = Object.fromEntries(partNames.map(name => [name, fake(name)]));
  const done = install(coreCtx(), Object.fromEntries(Object.entries(parts).reverse()));
  assert.deepEqual(order, partNames, 'cài theo PARTS, không theo thứ tự đăng ký');
  assert.equal(done.monthSections, 'month:monthSections');
  assert.equal(install(coreCtx(), { ...parts, presence: () => {} }).presenceStale, undefined, 'móc được phép thiếu');
  const fails = (core, registry, pattern) => assert.throws(() => install(core, registry), pattern);
  fails({ ...coreCtx(), stray: 1 }, parts, /lõi thiếu –; thừa stray/);
  const { root: _root, ...noRoot } = coreCtx();
  fails(noRoot, parts, /lõi thiếu root;/);
  const { pay: _pay, ...noPay } = parts;
  fails(coreCtx(), noPay, /thiếu phần "pay" \(thẻ <script src="so-khach-v7-pay-ui\.js">\)/);
  fails(coreCtx(), { ...parts, extra: () => {} }, /phần "extra" chưa khai trong PARTS/);
  fails(coreCtx(), { ...parts, history: ctx => { fake('history')(ctx); ctx.order = order; } }, /phần "history" ghi trường không khai: order/);
  fails(coreCtx(), { ...parts, trips: () => {} }, /phần "month" cần legacyTripRow, webTripRow, sheetPendingRows ngay lúc cài/);
  fails(coreCtx(), { ...parts, loc: () => {} }, /chưa phần nào ghi locAfterRender/);
});
