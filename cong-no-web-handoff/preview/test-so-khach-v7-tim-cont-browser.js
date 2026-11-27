/* Trình duyệt (Playwright) cho tìm số cont trên Sổ khách (TIM-CONT-01): ?cont= tô dòng, hộp đổi khách có khối Số cont.
 * Máy chủ giả, dữ liệu giả, không chạm DB. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage } = require('./so-khach-v7-browser-world');

test('mở từ kết quả tìm cont (?cont=): tô đúng chuyến web và dòng sổ gốc có số đó, bỏ đánh dấu xóa cả ?cont=', async () => withPage(async ({ page }) => {
  await page.locator('.loc-bar').waitFor();
  assert.match(await page.locator('.loc-bar').innerText(), /2 chuyến số cont DEMU1234567/);
  assert.deepEqual(await page.locator('tr.loc-hit').evaluateAll(rows => rows.map(row => row.dataset.row).sort()), ['legacy-21', 'trip-11']);
  await page.locator('.loc-next').click();
  await page.locator('.loc-clear').click();
  assert.equal(await page.locator('tr.loc-hit').count(), 0);
  assert.doesNotMatch(await page.evaluate(() => location.search), /cont=/);
}, world => {
  // Số cont gõ có khoảng trắng, chữ thường vẫn khớp; dòng sổ gốc 21 được sửa sang cùng số cont.
  world.query = '&cont=demu%201234567';
  world.legacy[0].current.container = 'DEMU 1234567';
}));

test('?cont= không còn chuyến nào khớp: thanh báo "không còn", không tô dòng nào', async () => withPage(async ({ page }) => {
  await page.locator('.loc-bar').waitFor();
  assert.match(await page.locator('.loc-bar').innerText(), /Sổ này không còn chuyến số cont NONE9999999/);
  assert.equal(await page.locator('tr.loc-hit').count(), 0);
}, world => { world.query = '&cont=NONE9999999'; }));

test('hộp đổi khách: gõ số cont thì có khối Số cont dưới các khách khớp, mỗi dòng mở sổ đúng tháng', async () => withPage(async ({ page, world }) => {
  world.containers = { query: 'DEMU12', more: false, items: [
    { customer_id: 1, debt_month: '2026-09-01', date: '2026-09-15', container: 'DEMU1234567', origin: 'Nơi A', destination: 'Nơi B', source: 'web' }] };
  const search = page.locator('#customer-search');
  await page.locator('.customer-switch').click();
  await search.click();
  await search.fill('demu12');
  const hit = page.locator('#customer-list a.cont-hit');
  await hit.waitFor();
  assert.equal(await hit.innerText(), 'DEMU1234567 · Khách Thử Sửa · 15/09/2026');
  assert.equal(await hit.getAttribute('href'), '/so-khach-v7-live.html?customer=1&month=2026-09&cont=DEMU1234567');
  assert.deepEqual(world.contReads, ['demu12']);
  assert.equal(await page.locator('#customer-list .customer-group').filter({ hasText: 'Số cont (1)' }).count(), 1);
}));
