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

test('Chia trang theo chiều cao đo thật: 16, 17, 30, 60 container và khách tên/địa chỉ dài (15 container một trang)', () => withBrowser(async browser => {
  const base = sample('sample-14');
  const want = { 16: 'single:16', 17: 'first:14 + last:3', 30: 'first:20 + last:10', 60: 'first:20 + middle:23 + last:17' };
  for (const [count, pages] of Object.entries(want)) assert.equal(split(await render(repeat(base, Number(count)), config, { browser })), pages, `${count} container`);
  const long = data => ({ ...data, customer: { ...data.customer, ...LONG } });
  assert.equal(split(await render(long(repeat(base, 15)), config, { browser })), 'single:15');
  assert.equal(split(await render(long(repeat(base, 16)), config, { browser })), 'first:13 + last:3');
}));

test('Font: chỉ serif (Times New Roman/Liberation Serif + SimSun/Noto Serif CJK), chỉ hai độ đậm, đều nhúng vào PDF', t => withBrowser(async browser => {
  const info = pdfInfo((await render(sample('sample-30'), config, { browser })).pdf);
  assert.equal(info.embedded, info.descriptors, `font không nhúng: ${info.fonts.join(', ')}`);
  const latin = info.fonts.filter(name => !/SimSun|Song|CJK|SC\b|Han/i.test(name));
  assert.ok(latin.length >= 2 && latin.every(name => /^(TimesNewRoman|LiberationSerif|Tinos)/.test(name)), `font Latin: ${latin.join(', ')}`);
  assert.ok(latin.every(name => /-Bold$|-BoldMT$|PSMT$|^LiberationSerif$|^Tinos$/.test(name) && !/Italic|Semi|Light|Black/.test(name)), `độ đậm: ${latin.join(', ')}`);
  const cjk = info.fonts.filter(name => !latin.includes(name));
  const serifCjk = name => /^(SimSun|NSimSun|STSong|Songti|NotoSerifCJK|NotoSerifSC)/.test(name);
  if (cjk.every(serifCjk)) assert.ok(cjk.length >= 1, 'có font chữ Trung');
  // Máy CI (Ubuntu) có thể không cài font serif chữ Trung: chỉ báo, không đỏ. Máy chủ hao có Noto Serif CJK SC.
  else if (process.platform === 'win32') assert.fail(`font chữ Trung không phải serif: ${cjk.join(', ')}`);
  else t.diagnostic(`máy này thiếu font serif chữ Trung, đang dùng: ${cjk.join(', ')}`);
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
