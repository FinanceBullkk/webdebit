/* DEBIT-NOTE-03: xuất PDF mẫu v4 bằng Chromium headless như máy thật (tools/debit-note-v4-pdf.js), theo SPEC mục 9:
 * chia trang đo thật cho dữ liệu mẫu, 16/17/30/60 container và ca tên dài; khổ A4 ngang; font serif đã nhúng; phép kiểm
 * sai thì không ra PDF. Dữ liệu mẫu, không chạm DB hay Sheet. */
const { test, launchShared } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { render, repeat, LONG } = require('../tools/debit-note-v4-pdf.js');

const ROOT = path.join(__dirname, '..', '..');
const config = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'web', 'debit-note-config.default.json'), 'utf8'));
const sample = name => JSON.parse(fs.readFileSync(path.join(ROOT, 'docs', 'debit-note-v4', 'data', `${name}.json`), 'utf8'));
const split = result => result.pages.map(page => `${page.kind}:${page.rows}`).join(' + ');

// Đọc PDF của Chromium (không nén bảng đối tượng): số trang, khổ, tên font và số font có nhúng.
function pdfInfo(bytes) {
  const text = Buffer.from(bytes).toString('latin1');
  return { pages: (text.match(/\/Type\s*\/Page[^s]/g) ?? []).length,
    boxes: [...new Set((text.match(/\/MediaBox\s*\[[^\]]*\]/g) ?? []).map(box => box.replace(/\s+/g, ' ')))],
    fonts: [...new Set((text.match(/\/BaseFont\s*\/[A-Za-z0-9+-]+/g) ?? []).map(name => name.replace(/.*\/(?:[A-Z]{6}\+)?/, '')))],
    embedded: (text.match(/\/FontFile[23]?\b/g) ?? []).length, descriptors: (text.match(/\/Type\s*\/FontDescriptor/g) ?? []).length };
}

// Font chữ Trung trong PDF: bỏ các font Latin serif. Số dòng mỗi trang của SPEC đo bằng Liberation Serif + Noto Serif CJK SC
// (máy chủ hao) hoặc Times New Roman + SimSun (Windows); máy thiếu font serif chữ Trung (runner Ubuntu của GitHub) thì dòng
// có chữ Trung dự phòng cao hơn chút, trang chứa ít dòng hơn: đó là đúng thiết kế (chia theo chiều cao đo thật), không phải lỗi.
const LATIN = /^(TimesNewRoman|LiberationSerif|Tinos)/;
const SERIF_CJK = /^(SimSun|NSimSun|STSong|Songti|NotoSerifCJK|NotoSerifSC)/;
const cjkOf = info => info.fonts.filter(name => !LATIN.test(name));
const hasSerifCjk = info => cjkOf(info).length > 0 && cjkOf(info).every(name => SERIF_CJK.test(name));
// Quy tắc không phụ thuộc font: đủ dòng theo thứ tự, trang đầu/giữa/cuối đúng loại, Total kèm ít nhất 3 dòng (khi có từ 4 dòng).
function assertSplitRules(result, count, label) {
  const pages = result.pages;
  assert.equal(pages.reduce((sum, page) => sum + page.rows, 0), count, label);
  if (pages.length === 1) { assert.equal(pages[0].kind, 'single', label); return; }
  assert.deepEqual(pages.map(page => page.kind), ['first', ...pages.slice(1, -1).map(() => 'middle'), 'last'], label);
  assert.ok(pages.at(-1).rows >= Math.min(3, count - 1), `${label}: trang cuối ${pages.at(-1).rows} dòng`);
}

async function withBrowser(run) {
  const browser = await launchShared();
  try { return await run(browser); } finally { await browser.close(); }
}

test('Dữ liệu mẫu: 14 → 1 trang, 30 → 20 + 10, 8 container ẩn cột HC fee; PDF A4 ngang, đủ trang, không trang trắng', () => withBrowser(async browser => {
  const cases = [['sample-14', 'single:14', 1], ['sample-30', 'first:20 + last:10', 2], ['sample-8-an-cot', 'single:8', 1]];
  for (const [name, pages, count] of cases) {
    const result = await render(sample(name), config, { browser });
    assert.equal(split(result), pages, name);
    const info = pdfInfo(result.pdf);
    assert.equal(info.pages, count, name);
    // 297 × 210 mm; Chromium làm tròn chiều cao xuống số px nguyên (793 px = 594.96 pt), như PDF chuẩn của gói thiết kế.
    assert.equal(info.boxes.length, 1, name);
    const [, , width, height] = info.boxes[0].match(/[\d.]+/g).map(Number);
    assert.ok(Math.abs(width - 841.89) < 0.5 && Math.abs(height - 595.28) < 0.5, `${name}: ${info.boxes[0]}`);
  }
  assert.deepEqual((await render(sample('sample-8-an-cot'), config, { browser })).columns, ['LUMP_SUM', 'STORAGE', 'GENSET', 'OVERSTAY']);
}));

test('Chia trang theo chiều cao đo thật: 16, 17, 30, 60 container và khách tên/địa chỉ dài (15 container một trang)', t => withBrowser(async browser => {
  const base = sample('sample-14');
  const exact = hasSerifCjk(pdfInfo((await render(base, config, { browser })).pdf));
  if (!exact) t.diagnostic('máy thiếu font serif chữ Trung: chỉ kiểm quy tắc chia trang, không so số dòng mỗi trang của SPEC');
  const long = data => ({ ...data, customer: { ...data.customer, ...LONG } });
  const cases = [[repeat(base, 16), 16, 'single:16'], [repeat(base, 17), 17, 'first:14 + last:3'], [repeat(base, 30), 30, 'first:20 + last:10'],
    [repeat(base, 60), 60, 'first:20 + middle:23 + last:17'], [long(repeat(base, 15)), 15, 'single:15'], [long(repeat(base, 16)), 16, 'first:13 + last:3']];
  for (const [data, count, pages] of cases) {
    const result = await render(data, config, { browser });
    const label = `${count} container${data.customer.name_en === LONG.name_en ? ', tên dài' : ''}`;
    assertSplitRules(result, count, label);
    if (exact) assert.equal(split(result), pages, label);
  }
}));

test('Font: chỉ serif (Times New Roman/Liberation Serif + SimSun/Noto Serif CJK), chỉ hai độ đậm, đều nhúng vào PDF', t => withBrowser(async browser => {
  const info = pdfInfo((await render(sample('sample-30'), config, { browser })).pdf);
  assert.equal(info.embedded, info.descriptors, `font không nhúng: ${info.fonts.join(', ')}`);
  const latin = info.fonts.filter(name => LATIN.test(name));
  assert.ok(latin.length >= 2, `font Latin: ${info.fonts.join(', ')}`);
  assert.ok(latin.every(name => /-Bold$|-BoldMT$|PSMT$|^LiberationSerif$|^Tinos$/.test(name) && !/Italic|Semi|Light|Black/.test(name)), `độ đậm: ${latin.join(', ')}`);
  // Máy chủ hao có Noto Serif CJK SC, Windows có SimSun; runner Ubuntu của GitHub không có font chữ Trung nào: chỉ báo.
  if (hasSerifCjk(info)) assert.ok(cjkOf(info).every(name => SERIF_CJK.test(name)));
  else if (process.platform === 'win32') assert.fail(`font chữ Trung không phải serif: ${cjkOf(info).join(', ') || '(không có)'}`);
  else t.diagnostic(`máy này thiếu font serif chữ Trung, đang dùng: ${cjkOf(info).join(', ') || '(không có)'}`);
  assert.ok(info.fonts.every(name => !/Arial|Helvetica|DejaVuSans|Segoe/i.test(name)), `có font sans: ${info.fonts.join(', ')}`);
}));

test('Phép kiểm sai thì không ra PDF: sửa Amount một dòng thì phép 1 (dòng) và phép 3 (tổng cột ≠ Total) chặn', () => withBrowser(async browser => {
  const data = sample('sample-14');
  data.containers[2].amount += 1;
  const result = await render(data, config, { browser });
  assert.equal(result.pdf, undefined);
  assert.deepEqual(result.problems, ['Phép 1: dòng 3 HTHU2611210: Amount 75,000,001 ≠ 70,000,000 + – + – + 5,000,000 + – = 75,000,000.',
    'Phép 3: tổng các cột phí 1,070,000,000 ≠ Total Amount 1,070,000,001.']);
}));
