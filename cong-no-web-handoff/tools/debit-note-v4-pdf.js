#!/usr/bin/env node
/* DEBIT-NOTE-03: xuất PDF debit note mẫu v4 bằng Chromium headless (Playwright), theo docs/debit-note-v4/SPEC.md mục 3.
 *
 *   node cong-no-web-handoff/tools/debit-note-v4-pdf.js <dữ liệu.json> <ra.pdf> [--png <ra-trang>] [--config <cấu hình.json>]
 *       [--repeat <n>] [--long]
 *
 * <dữ liệu.json> là dữ liệu dạng docs/debit-note-v4/data/*.json. Cấu hình mặc định là web/debit-note-config.default.json
 * (ngân hàng để trống, in [Tên trường]); --config ghi đè như file riêng trên máy chủ. --repeat nhân dữ liệu lên n container
 * (thử chia trang 16/17/30/60), --long đổi tên và địa chỉ khách sang ca dài của SPEC mục 9. Chạy 6 phép kiểm trước; phép
 * nào sai thì không ghi PDF, in lỗi và thoát mã 3. --png ghi ảnh từng trang (<ra-trang>-1.png, -2.png...) ở 2× để so ảnh chuẩn.
 * In ra JSON: số trang, số dòng mỗi trang, tổng. */
/* global DebitNoteV4 -- hàm truyền vào page.evaluate chạy trong trang, nơi debit-note-v4.js đã nạp. */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const PREVIEW = path.join(__dirname, '..', 'preview');
const DEFAULT_CONFIG = path.join(__dirname, '..', 'web', 'debit-note-config.default.json');
const LONG = { name_en: 'FANYA INTERNATIONAL LOGISTICS (SHENZHEN) CO., LTD', name_zh: '泛亚国际物流（深圳）有限公司',
  legal_name_address: 'Room 1203, Block B, Galaxy Century Building, No. 3069 Caitian Road, Futian District, Shenzhen, Guangdong, China' };

function merge(base, extra) {
  const out = { ...base, ...Object.fromEntries(Object.entries(extra).filter(([key]) => !['company', 'payment', 'fees'].includes(key))) };
  for (const key of ['company', 'payment', 'fees']) if (extra[key]) out[key] = { ...base[key], ...extra[key] };
  return out;
}

// Nhân dữ liệu mẫu lên n container: lặp lại các dòng, số container đổi theo thứ tự để không trùng.
function repeat(data, count) {
  const list = Array.from({ length: count }, (_, index) => {
    const item = data.containers[index % data.containers.length];
    return { ...item, no: index + 1, container_no: `${item.container_no.slice(0, 4)}${String(index).padStart(7, '0')}` };
  });
  return { ...data, containers: list };
}

// browser: trình duyệt có sẵn (test dùng chung một Chromium); không truyền thì tự mở rồi đóng. Trả thêm pdf (Buffer) khi xuất được.
async function render(data, config, { pdfPath, pngPrefix, browser: shared } = {}) {
  const browser = shared ?? await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1123, height: 794 }, deviceScaleFactor: 2 });
    await page.setContent('<!doctype html><html lang="en"><head><meta charset="utf-8"></head><body></body></html>');
    for (const file of ['cong-no-format.js', 'debit-note-v4.js']) await page.addScriptTag({ path: path.join(PREVIEW, file) });
    const result = await page.evaluate(({ data, config }) => {
      const doc = DebitNoteV4.fromSample(data, config);
      const problems = DebitNoteV4.checks(doc).filter(item => item.level === 'block');
      if (problems.length) return { problems: problems.map(item => item.text) };
      const pages = DebitNoteV4.split(doc, document);
      document.open();
      document.write(DebitNoteV4.documentHtml(doc, pages, doc.number));
      document.close();
      return { pages: pages.map(item => ({ kind: item.kind, rows: item.rows.length })), total: doc.total.amount.toString(),
        outstanding: doc.account.outstanding.toString(), columns: doc.columns.map(column => column.code) };
    }, { data, config });
    if (result.problems) return result;
    await page.evaluate(() => document.fonts.ready);
    // SPEC mục 3: printBackground (thanh navy, nền tiêu đề bảng), khổ theo CSS (A4 ngang), lề 0.
    result.pdf = await page.pdf({ path: pdfPath ?? undefined, printBackground: true, preferCSSPageSize: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
    if (pngPrefix) {
      const handles = await page.$$('[data-page]');
      for (const [index, handle] of handles.entries()) await handle.screenshot({ path: `${pngPrefix}-${index + 1}.png` });
    }
    return result;
  } finally {
    if (!shared) await browser.close();
  }
}

async function main(argv) {
  const args = [...argv];
  const take = flag => { const at = args.indexOf(flag); if (at < 0) return null; const [, value] = args.splice(at, 2); return value ?? null; };
  const flag = name => { const at = args.indexOf(name); if (at < 0) return false; args.splice(at, 1); return true; };
  const png = take('--png'), configPath = take('--config'), count = take('--repeat'), long = flag('--long');
  const [input, output] = args;
  if (!input || !output) {
    console.error('Cách dùng: debit-note-v4-pdf.js <dữ liệu.json> <ra.pdf> [--png <ra-trang>] [--config <cấu hình.json>] [--repeat <n>] [--long]');
    return 2;
  }
  let data = JSON.parse(fs.readFileSync(input, 'utf8'));
  if (count) data = repeat(data, Number(count));
  if (long) data = { ...data, customer: { ...data.customer, ...LONG } };
  const base = JSON.parse(fs.readFileSync(DEFAULT_CONFIG, 'utf8'));
  const config = configPath ? merge(base, JSON.parse(fs.readFileSync(configPath, 'utf8'))) : base;
  const result = await render(data, config, { pdfPath: output, pngPrefix: png });
  if (result.problems) {
    console.error(`Không xuất PDF vì phép kiểm sai:\n- ${result.problems.join('\n- ')}`);
    return 3;
  }
  delete result.pdf;
  console.log(JSON.stringify(result));
  return 0;
}

if (require.main === module) main(process.argv.slice(2)).then(code => process.exit(code), error => { console.error(error); process.exit(1); });
module.exports = { render, repeat, merge, LONG };
