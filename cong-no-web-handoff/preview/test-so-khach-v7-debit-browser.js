/* Trình duyệt (Playwright) cho debit note theo tháng công nợ (DEBIT-NOTE-01) trên sổ khách V7 bản live, theo
 * specs/v7-debit-note.md. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { withPage } = require('./so-khach-v7-browser-world');

// Chuyến web tháng 9 có một khoản Neo; dòng sổ gốc OLDU0000001 chưa có giá, OLDU0000002 có Phụ phí ban đầu 3.000.000.
const withNeo = world => {
  world.trips[0].fee_lines = [{ id: 700, fee_type_id: 1, amount_vnd: '2000000', note: null }];
  world.trips[0].amount_vnd = '52000000';
};

test('Debit note: xem trước đúng chuyến của tháng, thiếu giá để trống, tải Excel, Esc trả focus', async () => withPage(async ({ page, world, shot }) => {
  const open = page.locator('#thang-2026-09 .debit-open');
  await open.waitFor();
  assert.equal(await page.locator('.debit-open').count(), 1);   // tháng hiện tại chưa có chuyến: không có nút
  await open.click();
  const dialog = page.locator('.debit-dialog');
  await dialog.locator('.dn-sheet').waitFor();
  assert.equal(await page.evaluate(() => document.activeElement?.className), 'debit-excel');
  assert.match(await dialog.locator('h2').innerText(), /Debit note tháng 9\/2026\s*3 dòng · CHƯA CHỐT/);
  assert.match(await dialog.locator('.debit-notes').innerText(), /1 chuyến chưa có giá/);
  const rows = await dialog.locator('.dn-table tbody tr').evaluateAll(list => list.map(row => [...row.cells].map(cell => cell.textContent)));
  assert.deepEqual(rows[0].slice(0, 7), ['1', 'OLDU0000001', 'Xe 1', 'Chủ hàng thử', '02/09/2026', 'Nơi C', 'Nơi D']);
  assert.deepEqual(rows[0].slice(14), ['', '']);
  assert.deepEqual(rows[1].slice(7), ['', '', '', '3,000,000', '', '', '', '90,000,000', '93,000,000']);
  assert.deepEqual(rows[2].slice(7), ['2,000,000', '', '', '', '', '', '', '50,000,000', '52,000,000']);
  assert.equal(rows.length, 3);
  assert.deepEqual(await dialog.locator('.dn-total td').allTextContents(), ['TỔNG CỘNG · 总计 (VND)', '']);
  assert.equal(await dialog.locator('.dn-status').innerText(), 'CHƯA CHỐT');
  assert.match(await dialog.innerText(), /Khách Thử Sửa/);
  await shot('debit-note-xem-truoc');

  const [download] = await Promise.all([page.waitForEvent('download'), dialog.locator('.debit-excel').click()]);
  assert.equal(download.suggestedFilename(), 'debit-note-Khach-Thu-Sua-2026-09.xlsx');
  assert.equal(fs.readFileSync(await download.path()).subarray(0, 2).toString(), 'PK');

  await page.keyboard.press('Escape');
  assert.equal(await dialog.isHidden(), true);
  assert.equal(await page.evaluate(() => document.activeElement?.className), 'debit-open');
  assert.deepEqual(world.requests, []);   // chỉ đọc: không gửi lệnh nào
}, withNeo));

test('Debit note: đủ giá thì có tổng và ĐÃ CHỐT; chuyến CHỜ KIỂM không lên phiếu; In dựng bảng trong khung in', async () => withPage(async ({ page }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  await dialog.locator('.dn-sheet').waitFor();
  assert.match(await dialog.locator('h2').innerText(), /3 dòng · ĐÃ CHỐT/);
  assert.match(await dialog.locator('.debit-notes').innerText(), /1 chuyến đang CHỜ KIỂM không lên phiếu/);
  assert.equal(await dialog.locator('.dn-total .num').innerText(), '143,000,000');
  assert.equal(await dialog.locator('.dn-status').innerText(), 'ĐÃ CHỐT');
  await page.evaluate(() => { window.__printed = 0; HTMLIFrameElement.prototype.focus = () => {}; });
  await page.evaluate(() => {
    const original = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow').get;
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', { get() { const win = original.call(this); win.print = () => { window.__printed++; }; return win; } });
  });
  await dialog.locator('.debit-print').click();
  assert.equal(await page.evaluate(() => window.__printed), 1);
  assert.equal(await page.evaluate(() => document.querySelector('.debit-print-frame').contentDocument.querySelectorAll('.dn-table tbody tr').length), 3);
  await dialog.locator('.debit-close').click();
  assert.equal(await dialog.isHidden(), true);
}, world => {
  world.legacy[0].current = { ...world.legacy[0].current, unit_price_vnd: '0', counted_vnd: '0' };
  world.trips.push({ ...world.trips[0], id: 12, container: 'PEND0000001', status: 'pending_review', amount_vnd: null });
}));
