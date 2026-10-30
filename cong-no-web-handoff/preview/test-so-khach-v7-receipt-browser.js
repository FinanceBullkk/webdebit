/* Trình duyệt (Playwright) cho ghi phiếu thu từ Sheet (THU-SHEET-01, specs/v7-receipt-queue.md). Máy chủ giả, tiền giả, không chạm DB. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage, posts } = require('./so-khach-v7-browser-world');

const item = (date, amount, extra = {}) => ({ customer_tab: 'Khách Thử Sửa', source_row: 40, debt_month: '2026-09',
  amount_vnd: amount, note: date ? `${date.slice(8)}/${date.slice(5, 7)}/${date.slice(0, 4)} tt` : 'da tt', date, status: 'READY', ...extra });
const withReceipts = world => {
  world.sheetReceipts = { snapshot_sha256: 'e'.repeat(64), ready: [item('2026-09-20', '300000000'), item('2026-09-22', '20000000', { source_row: 41 })],
    review: [], ready_count: 2, review_count: 0 };
};

test('Ghi phiếu thu từ Sheet: khung xác nhận có từng phiếu và tổng, ghi một lệnh cho cả lô', async () => withPage(async ({ page, world, shot }) => {
  const button = page.locator('.receipt-approve');
  assert.equal(await button.innerText(), 'Ghi 2 phiếu thu từ Sheet');
  await shot('thu-sheet-1-cho-ghi');
  await button.click();
  const confirm = page.locator('.receipt-panel.confirm');
  assert.match(await confirm.innerText(), /Ghi 2 phiếu thu từ Sheet, tổng 320\.000\.000 đ\?/);
  assert.match(await confirm.innerText(), /giảm từ 0 xuống -320\.000\.000/);
  assert.match(await confirm.innerText(), /20\/09\/2026 · 300\.000\.000 đ · nợ tháng 9\/2026 trên Sheet · Sheet ghi "20\/09\/2026 tt"/);
  assert.equal(await page.evaluate(() => document.activeElement.className), 'receipt-write primary');
  await shot('thu-sheet-2-xac-nhan');
  await page.locator('.receipt-cancel').click();
  assert.equal(await page.locator('.receipt-panel').count(), 0);
  assert.equal(world.requests.length, 0);
  await button.click();
  await page.locator('.receipt-write').click();
  await page.waitForFunction(() => !document.querySelector('.receipt-approve'));
  const [path, body] = posts(world).at(-1);
  assert.equal(path, '/api/v7/sheet/receipts');
  assert.deepEqual(Object.keys(body).sort(), ['customer_id', 'expected_version', 'idempotency_key', 'snapshot_sha256']);
  assert.equal(body.snapshot_sha256, 'e'.repeat(64));
  assert.equal(world.requests.length, 1);
  assert.equal(world.receipts.length, 2);
  assert.match(await page.locator('.live-notice').innerText(), /Đã ghi 2 phiếu thu từ Sheet\./);
}, withReceipts));

test('Ghi phiếu thu từ Sheet: Sheet đổi giữa chừng thì không ghi gì và mời tải lại', async () => withPage(async ({ page, world }) => {
  world.receiptStale = true;
  await page.locator('.receipt-approve').click();
  await page.locator('.receipt-write').click();
  const error = page.locator('.receipt-panel.err');
  await error.waitFor();
  assert.match(await error.innerText(), /Chưa ghi phiếu thu nào\. Sheet đã đổi sau khi mở sổ\./);
  assert.equal(world.receipts.length, 0);
  world.receiptStale = false;
  world.sheetReceipts = { ...world.sheetReceipts, ready: [], ready_count: 0 };
  await page.locator('.receipt-reload').click();
  await page.waitForFunction(() => !document.querySelector('.receipt-panel'));
  assert.equal(await page.locator('.receipt-approve').count(), 0);
}, withReceipts));

test('Phiếu thu Sheet cần xem: không ngày, ngày tương lai, web đã xóa, Sheet sửa phiếu cũ có nút tới khoản cũ', async () => withPage(async ({ page, world, shot }) => {
  assert.equal(await page.locator('.receipt-approve').count(), 0);
  const strip = page.locator('.receipt-strip');
  assert.match(await strip.innerText(), /Phiếu thu Sheet cần xem:\s*4/);
  await strip.locator('.receipt-review-toggle').click();
  const panel = page.locator('.receipt-panel');
  const text = await panel.innerText();
  assert.match(text, /Sheet không ghi ngày thu\./);
  assert.match(text, /Ngày thu 05\/11\/2026 sau hôm nay\./);
  assert.match(text, /Web đã xóa khoản thu sổ gốc này/);
  assert.match(text, /Sheet đã sửa phiếu thu tháng 9\/2026: web còn khoản thu sổ gốc 48\.000\.000 đ không thấy trên Sheet\./);
  await shot('thu-sheet-3-can-xem');
  await panel.locator('.receipt-goto').click();
  assert.equal(await page.evaluate(() => document.activeElement.dataset.id), '31');
  assert.equal(world.requests.length, 0);
}, world => {
  world.legacy.push({ id: 31, month: '2026-09-01', kind: 'receipt', source_total_vnd: '48000000', editable: false,
    display: { row: 5, raw_date: '14/10/2026 tt' }, current: { month: '2026-09-01', deleted: false } });
  world.sheetReceipts = { snapshot_sha256: 'f'.repeat(64), ready: [], ready_count: 0, review_count: 4, review: [
    item(null, '65000000', { status: 'NO_DATE' }), item('2026-11-05', '1000000', { status: 'FUTURE_DATE' }),
    item('2026-09-03', '5000000', { status: 'WEB_DELETED' }),
    item('2026-10-14', '47000000', { status: 'SHEET_EDITED', web_legacy: [{ id: 31, amount_vnd: '48000000' }] })] };
}));
