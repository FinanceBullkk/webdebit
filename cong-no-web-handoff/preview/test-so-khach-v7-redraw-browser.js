/* Trình duyệt (Playwright): vẽ lại vì việc nền không xóa dòng hỏi hay chữ đang gõ (redrawWhenFree trong so-khach-v7-ui.js).
 * Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. Đồng hồ trang chạy tay nên không phụ thuộc máy nhanh hay chậm. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage } = require('./so-khach-v7-browser-world');

const LOCK = '.month-lock[data-month="2026-09-01"]';

// Đổi khổ xong (trình nghe resize của sổ đã nhận) mới cho đồng hồ chạy.
async function resize(page, width) {
  const resized = page.evaluate(() => new Promise(done => { addEventListener('resize', done, { once: true }); }));
  await page.setViewportSize({ width, height: 720 });
  await resized;
}
const isShown = node => node.evaluate(item => item.isConnected);

test('Đổi cỡ màn lúc đang hỏi khóa tháng: dòng hỏi còn nguyên; đóng rồi sổ mới vẽ theo khổ mới, tiêu điểm về nút', async () => withPage(async ({ page, world }) => {
  await page.clock.install();
  await page.locator(LOCK).click();
  const book = await page.locator('#the-so .ledger-book').elementHandle();
  await resize(page, 1200);
  await page.clock.runFor(2000);
  assert.equal(await page.locator('.lock-ask').count(), 1, 'dòng hỏi bị xóa khi đổi cỡ màn');
  assert.equal(await isShown(book), true, 'sổ vẽ lại trong lúc đang hỏi');
  await page.keyboard.press('Escape');
  await page.clock.runFor(1000);
  assert.equal(await isShown(book), false, 'đóng dòng hỏi rồi mà sổ không vẽ lại theo khổ mới');
  assert.equal(await page.evaluate(selector => document.activeElement === document.querySelector(selector), LOCK), true);
  assert.deepEqual(world.requests, [], 'Esc không gửi lệnh');
}));

test('Đổi cỡ màn lúc đang gõ lý do hủy phiếu: chữ đang gõ còn nguyên', async () => withPage(async ({ page }) => {
  await page.clock.install();
  await page.locator('td.receipt[data-pid="PH-001"] .receipt-sum').click();
  await page.locator('.void-reason').fill('ghi trùng');
  await resize(page, 1200);
  await page.clock.runFor(2000);
  assert.equal(await page.locator('.void-reason').inputValue(), 'ghi trùng');
}, world => {
  world.receipts.push({ id: 1, pid: 'PH-001', date: '2026-09-11', method: 'THU TIỀN', amount_vnd: '2000000', reference: null, voided_by_event: null, void_reason: null,
    allocations: [{ id: 1, month: '2026-09-01', kind: 'debt', amount_vnd: '2000000', superseded_by_event: null }] });
}));

// Giữ phản hồi của một đường API tới khi test cho về; trả về hàm cho về, chờ tới lúc trang đọc xong.
function holdResponse(world, pattern) {
  let open;
  const gate = new Promise(resolve => { open = resolve; });
  let page = null;
  world.beforeOpen = async opened => {
    page = opened;
    await opened.route(pattern, async route => { await gate; await route.continue(); });
  };
  return async () => {
    const answered = page.waitForResponse(pattern);
    open();
    await (await answered).finished();
    await page.evaluate(() => new Promise(done => { setTimeout(done, 100); }));
  };
}

function lateData(name, pattern, prepare, arrived) {
  let release;
  test(`${name} về muộn lúc đang hỏi khóa tháng: dòng hỏi còn nguyên; đóng rồi sổ mới hiện dữ liệu đó`, async () => withPage(async ({ page }) => {
    await page.locator(LOCK).click();
    await release();
    assert.equal(await page.locator('.lock-ask').count(), 1, 'dòng hỏi bị xóa khi dữ liệu về');
    await page.keyboard.press('Escape');
    await page.locator(arrived).first().waitFor({ state: 'attached' });
  }, world => {
    prepare(world);
    release = holdResponse(world, pattern);
  }));
}

lateData('Danh mục phụ phí', /\/api\/v7\/fee-types/, world => { world.feeColumns = [1]; }, '.ledger-head th:text-is("Neo")');
lateData('Trạng thái bảng giá', /\/api\/v7\/price-table\/status/, world => {
  world.priceStatus = { customer_id: 1, version: 1, has_table: true, ready_count: 0, ready_total_vnd: '0', ready_months: [], reapply_count: 0,
    trips: [{ trip_id: 11, ready: false, differs: true, from_table: false, unit_price_vnd: '50000000', lookup: { unit_price_vnd: '40000000', tier: 'tt' } }] };
}, '.price-diff');
