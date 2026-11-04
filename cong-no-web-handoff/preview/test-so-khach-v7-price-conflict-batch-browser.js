const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, posts } = require('./so-khach-v7-browser-world');

const conflict = (kind, id, sourceRow, container, web, sheet, fee = null) => ({
  status: 'CONFLICT', batchable: true, target_kind: kind, target_id: id, source_row: sourceRow,
  container, date: '2026-09-15', web_unit_price_vnd: web, sheet_unit_price_vnd: sheet,
  web_other_fee_vnd: fee, sheet_other_fee_vnd: fee,
  web_total_vnd: kind === 'legacy' ? String(BigInt(web) + BigInt(fee ?? '0')) : null,
});
const setup = world => {
  world.sheetPrices = { snapshot_sha256: 'b'.repeat(64), ready: [], ready_count: 0,
    review: [conflict('trip', 11, 51, 'DEMU1234567', '50000000', '52000000'),
      conflict('legacy', 22, 52, 'OLDU0000002', '90000000', '95000000', '3000000')], review_count: 2 };
};

test('giá lệch: chọn, xem trước, ghi một yêu cầu và đọc lại sổ một lần', async () => withPage(async ({ page, world }) => {
  await page.locator('.price-review-toggle').click();
  assert.equal(await page.locator('.price-conflict-select').count(), 2);
  assert.equal(await page.locator('.price-conflict-confirm').isDisabled(), true);
  await page.locator('.price-conflict-all').click();
  await page.locator('.price-conflict-confirm').click();
  const preview = await page.locator('.price-panel.confirm').innerText();
  assert.match(preview, /2 dòng đã chọn/);
  assert.match(preview, /50\.000\.000 đ → Sheet 52\.000\.000 đ/);
  assert.match(preview, /90\.000\.000 đ → Sheet 95\.000\.000 đ/);
  assert.match(preview, /chênh 7\.000\.000 đ/);
  assert.equal(posts(world).length, 0);
  await page.locator('.price-conflict-cancel').click();
  assert.equal(posts(world).length, 0);
  await page.locator('.price-conflict-confirm').click();
  const reads = world.reads;
  await page.locator('.price-conflict-write').click();
  await page.waitForFunction(() => !document.querySelector('.price-strip'));
  assert.equal(world.reads - reads, 1);
  assert.equal(posts(world).length, 1);
  const [path, body] = posts(world)[0];
  assert.equal(path, '/api/v7/sheet/prices/conflicts');
  assert.deepEqual(body.conflicts, [
    { target_kind: 'trip', target_id: 11, source_row: 51 },
    { target_kind: 'legacy', target_id: 22, source_row: 52 },
  ]);
  assert.equal(world.trips[0].unit_price_vnd, '52000000');
  assert.equal(world.legacy[1].current.unit_price_vnd, '95000000');
}, setup));

test('giá lệch: Sheet đổi trước lúc ghi thì không đổi sổ', async () => withPage(async ({ page, world }) => {
  await page.locator('.price-review-toggle').click();
  await page.locator('.price-conflict-all').click();
  await page.locator('.price-conflict-confirm').click();
  world.priceConflictStale = true;
  await page.locator('.price-conflict-write').click();
  assert.match(await page.locator('.price-panel.err').innerText(), /Sheet đã đổi/);
  assert.equal(world.trips[0].unit_price_vnd, '50000000');
  assert.equal(world.legacy[1].current.unit_price_vnd, '90000000');
}, setup));

test('giá lệch có phụ phí âm vẫn xem trước bằng số nguyên có dấu', async () => withPage(async ({ page, world }) => {
  await page.locator('.price-review-toggle').click();
  await page.locator('.price-conflict-select').check();
  await page.locator('.price-conflict-confirm').click();
  assert.match(await page.locator('.price-panel.confirm').innerText(), /Phụ phí Web 0 đ → Sheet -500\.000 đ/);
  assert.equal(posts(world).length, 0);
}, world => {
  setup(world);
  world.sheetPrices.review = [conflict('trip', 11, 51, 'DEMU1234567', '50000000', '52000000')];
  world.sheetPrices.review[0].sheet_other_fee_vnd = '-500000';
  world.sheetPrices.review_count = 1;
}));
