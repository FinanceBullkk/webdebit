const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage } = require('./so-khach-v7-browser-world');
const handoff = require('./so-khach-v7-handoff-world');

test('Cảnh báo Sheet, ba cột phí và số dư lớn: hành động không vỡ chữ, không ép cột container', async () => withPage(async ({ page, world, shot }) => {
  for (const width of [1895, 1280, 390]) {
    await page.setViewportSize({ width, height: 848 });
    await page.reload();
    await page.locator('.sheet-removed-notice').first().waitFor();
    const geometry = await page.evaluate(() => {
      const line = document.querySelector('.sheet-removed-notice');
      const row = line.previousElementSibling;
      const controls = [...line.querySelectorAll('button')];
      const label = document.querySelector('.month-end');
      const range = document.createRange();
      range.selectNodeContents(label.firstChild);
      return { rowHeight: row.getBoundingClientRect().height,
        fullWidth: line.cells[0].colSpan === row.cells.length,
        labelLines: range.getClientRects().length,
        controlsFit: controls.every(button => button.scrollWidth <= button.clientWidth && getComputedStyle(button).whiteSpace === 'nowrap'),
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
    });
    assert.deepEqual(geometry, { rowHeight: 35, fullWidth: true, labelLines: 1, controlsFit: true, overflow: 0 });
    await shot(`sheet-warning-${width}`);
  }
  await page.locator('.sheet-removed-next').click();
  assert.equal(await page.locator('.sheet-removed-delete').first().evaluate(node => node === document.activeElement), true);
  await page.locator('.sheet-removed-delete').first().click();
  assert.equal(await page.locator('.delete-prompt .confirm-delete').count(), 1);
  await page.locator('.delete-prompt .cancel-delete').click();
  await page.locator('.sheet-removed-keep').first().click();
  await page.waitForFunction(() => document.querySelectorAll('.sheet-removed-notice').length === 5);
  assert.equal(world.requests.length, 1);
  assert.equal(world.requests[0].path, '/api/v7/sheet/tasks/keep');
}, world => {
  handoff(world);
  world.feeColumns = [1, 2, 3];
  for (const month of world.months) {
    month.prior_months_vnd = '28123456789';
    month.end_of_month_vnd = '28123456789';
  }
  world.sheetSync = { ...world.sheetSync, removed_count: 6, removed_items: world.trips.slice(0, 6).map(trip => ({
    source_fingerprint: 'c'.repeat(64), trip_id: trip.id, container: trip.container, month: trip.month, event_date: trip.event_date,
    status: trip.status, amount_vnd: trip.amount_vnd, month_locked: false,
  })) };
}));
