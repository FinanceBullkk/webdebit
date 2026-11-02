const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage } = require('./so-khach-v7-browser-world');

test('Ưu tiên: số API cạnh phiếu thu, trên cột chuyến; mỗi số tháng một chỗ; không ghi tiền khi mở sổ', async () => withPage(async ({ page, world, shot }) => {
  await page.setViewportSize({ width: 1280, height: 560 });
  const geometry = await page.evaluate(() => {
    const box = selector => document.querySelector(selector).getBoundingClientRect();
    const stats = box('.month-stats'), pays = box('.pay-block'), columns = box('.ledger-head');
    return { sideBySide: stats.right <= pays.left && pays.top < stats.bottom,
      below: columns.top >= Math.max(stats.bottom, pays.bottom), overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
  });
  assert.deepEqual(geometry, { sideBySide: true, below: true, overflow: 0 });
  assert.deepEqual(await page.locator('.month-stats b').allTextContents(), ['412.600.000', '58.750.000', '150.000.000', '321.350.000']);
  assert.equal(await page.locator('.month-chip .chip-end').count(), 0);
  assert.equal(await page.locator('.subtotal').innerText().then(text => text.includes('58.750.000')), false);
  assert.equal(await page.locator('.entry-open').count(), 1);
  assert.equal(world.requests.length, 0);
  await shot('uu-tien-1280');
}, world => {
  world.monthValues = { '2026-09-01': { prior_months_vnd: '412600000', charges_vnd: '58750000', received_vnd: '150000000', end_of_month_vnd: '321350000' } };
  world.receipts = [{ id: 1, pid: 'PH-001', date: '2026-09-15', method: 'THU TIỀN', amount_vnd: '150000000', reference: 'Chứng từ mẫu',
    voided_by_event: null, allocations: [{ month: '2026-09-01', amount_vnd: '150000000', superseded_by_event: null }] }];
}));

test('Ưu tiên: giữ NULL và số âm từ API; mở menu và đổi khách bằng bàn phím', async () => withPage(async ({ page, world }) => {
  assert.deepEqual(await page.locator('.month-stats b').allTextContents(), ['–', '–', '–', '-12.345']);
  await page.locator('.nav-toggle').first().click();
  assert.equal(await page.locator('.nav-toggle').first().getAttribute('aria-expanded'), 'true');
  await page.locator('.customer-switch').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#customer-search').isVisible(), true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#customer-search').isVisible(), false);
  assert.equal(await page.locator('.customer-switch').evaluate(node => node === document.activeElement), true);
  assert.equal(world.requests.length, 0);
  await page.goto(new URL('/so-khach-v7-live.html', page.url()).href);
  await page.locator('.nav-toggle').first().click();
  assert.equal(await page.locator('.nav-toggle').first().getAttribute('aria-expanded'), 'true', 'menu vẫn dùng được trước khi chọn khách');
}, world => { world.monthValues = { '2026-09-01': { prior_months_vnd: null, charges_vnd: null, received_vnd: null, end_of_month_vnd: '-12345' } }; }));

test('Ưu tiên: 1265px có ba cột phí; màn hẹp chỉ cuộn ngang trong vùng sổ', async () => withPage(async ({ page, shot }) => {
  for (const width of [1265, 700, 390]) {
    await page.setViewportSize({ width, height: 560 });
    await page.waitForFunction(() => document.documentElement.scrollWidth === document.documentElement.clientWidth);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, `${width}px`);
    assert.equal(await page.locator('.ledger-head .fee-h').count(), 4);
  }
  await shot('uu-tien-390');
}, world => { world.feeColumns = [1, 2, 3]; }));
