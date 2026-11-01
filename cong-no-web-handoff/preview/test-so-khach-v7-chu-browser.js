/* Trình duyệt (Playwright) cho cỡ chữ, "+ thêm", nhãn trạng thái dòng và đầu sổ của sổ khách V7 (SO-GON-04, PR 2c).
 * Máy chủ giả, dữ liệu giả, 1280×720; không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage } = require('./so-khach-v7-browser-world');

// Cỡ chữ nhỏ nhất của mọi chữ đang hiện trong ô sổ và danh sách phiếu; cỡ chữ số tiền của ô số.
const sizes = page => page.evaluate(() => {
  const shown = [...document.querySelectorAll('#app .ledger td, #app .ledger td *')].filter(node =>
    node.offsetParent !== null && [...node.childNodes].some(child => child.nodeType === 3 && child.textContent.trim()));
  const px = node => Number.parseFloat(getComputedStyle(node).fontSize);
  const small = shown.filter(node => px(node) < 14).map(node => `${node.className || node.tagName}: ${node.textContent.trim().slice(0, 20)} (${px(node)}px)`);
  const money = [...document.querySelectorAll('#app .ledger td.num')].filter(td => /\d\.\d{3}/.test(td.textContent)).map(px);
  return { small, money: [...new Set(money)], overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
});
// Sổ giả có phụ phí, phiếu thu có tham chiếu và phần trừ nợ, chuyến chờ kiểm, chuyến đã loại.
function rich(world) {
  world.trips.push({ id: 31, month: '2026-09-01', container: 'HOLD0000031', carrier: 'Tàu thử', event_date: '2026-09-20', origin: 'Nơi A',
    destination: 'Nơi B', unit_price_vnd: '40000000', other_fee_vnd: null, amount_vnd: null, status: 'pending_review', review_reason: 'WEB_DUPLICATE',
    is_missing_price: false, is_fee_only: false, editable: false, info_editable: true, deleted: false },
  { id: 32, month: '2026-09-01', container: 'GONE0000032', carrier: 'Tàu thử', event_date: '2026-09-21', origin: 'Nơi A', destination: 'Nơi B',
    unit_price_vnd: '40000000', other_fee_vnd: null, amount_vnd: null, status: 'rejected', is_missing_price: false, is_fee_only: false,
    editable: false, info_editable: false, deleted: false });
  world.receipts.push({ id: 1, pid: 'PH-001', date: '2026-09-25', method: 'THU TIỀN', amount_vnd: '93000000', reference: 'CK 0099', voided_by_event: null,
    void_reason: null, allocations: [{ id: 1, month: '2026-08-01', kind: 'debt', amount_vnd: '3000000', superseded_by_event: null },
      { id: 2, month: '2026-09-01', kind: 'debt', amount_vnd: '90000000', superseded_by_event: null }] });
}

test('Chữ trong sổ và danh sách phiếu ≥ 14px; số tiền 16px; không cuộn ngang ở 1280', async () => withPage(async ({ page }) => {
  const { small, money, overflow } = await sizes(page);
  assert.deepEqual(small, []);
  assert.deepEqual(money, [16]);
  assert.equal(overflow, 0);
}, rich));

test('Sổ có Shipper và 3 cột phụ phí riêng: không cần khổ chật (SO-GON-06 trả chỗ ba cột thu), số 16px, không cuộn ngang ở 1280', async () => withPage(async ({ page }) => {
  assert.equal(await page.locator('.ledger-book.tight').count(), 0);
  const { small, money, overflow } = await sizes(page);
  assert.deepEqual(small, []);
  assert.deepEqual(money, [16]);
  assert.equal(overflow, 0);
}, world => { rich(world); world.feeColumns = [1, 2, 3]; }));

test('"+ thêm" chỉ hiện khi rê chuột vào dòng, đứng ở ô, hoặc tick chọn dòng; ô trống ghi "–"', async () => withPage(async ({ page }) => {
  const row = page.locator('tr[data-row="trip-11"]');
  const plus = row.locator('.fee-plus');
  await page.mouse.move(5, 5);
  assert.equal(await page.locator('.fee-plus:visible').count(), 0);
  assert.equal(await row.locator('.fee-dash').isVisible(), true);
  await row.locator('td').nth(1).hover();
  assert.equal(await plus.isVisible(), true);
  await page.mouse.move(5, 5);
  assert.equal(await plus.isVisible(), false);
  await row.locator('td.fee-other').focus();
  assert.equal(await plus.isVisible(), true);
  await page.locator('#customer-search').focus();
  await page.mouse.move(5, 5);
  await row.locator('.fee-pick').check();
  await page.mouse.move(5, 5);
  assert.equal(await plus.isVisible(), true);
}));

test('Trạng thái dòng là nhãn chữ: "chờ kiểm" bấm mở dòng kết luận, "đã loại" gạch, "chưa có giá" có chữ', async () => withPage(async ({ page }) => {
  const review = page.locator('tr[data-row="trip-31"] .review-open');
  assert.equal(await review.innerText(), 'chờ kiểm');
  await review.click();
  await page.locator('.review-prompt').waitFor();
  const gone = page.locator('tr[data-row="trip-32"] .trip-rejected');
  assert.equal(await gone.innerText(), 'đã loại');
  assert.match(await gone.evaluate(node => getComputedStyle(node).textDecorationLine), /line-through/);
  assert.equal(await page.locator('td.missing').first().innerText(), 'chưa có giá');
}, rich));

test('Thanh xanh trên cùng chỉ còn tên trang và điều hướng; đầu sổ một nút chính; một thanh việc: Làm mới, menu Cài đặt', async () => withPage(async ({ page, world }) => {
  assert.equal(await page.locator('.topbar #refresh-data, .topbar .live-controls, .topbar .presence-toggle').count(), 0);
  const head = page.locator('.book-head');
  assert.equal(await head.locator('button.entry-open').count(), 1);
  assert.deepEqual(await head.locator('button:not([role="tab"])').allInnerTexts(), ['Ghi phiếu thu', 'Lịch sử']);
  assert.equal(await page.locator('.book-bar #refresh-data').innerText(), 'Làm mới');
  // SO-GON-06: cài đặt nằm trong menu "Cài đặt ▾" của thanh việc (ẩn tới khi mở); bấm ra ngoài thì đóng.
  assert.equal(await page.locator('.book-bar .settings-menu .fee-settings-open').count(), 1);
  assert.equal(await page.locator('.book-bar .settings-menu .price-table-open').count(), 1);
  assert.equal(await page.locator('.book-bar .settings-menu .presence-toggle').count(), 1);
  assert.equal(await page.locator('.fee-settings-open').isVisible(), false);
  await page.locator('.book-settings > summary').click();
  assert.equal(await page.locator('.fee-settings-open').isVisible(), true);
  await page.locator('.book-head').click({ position: { x: 5, y: 5 } });
  assert.equal(await page.locator('.fee-settings-open').isVisible(), false);
  // Không còn hàng riêng nào giữa thanh việc và chip tháng.
  assert.equal(await page.evaluate(() => document.querySelector('.book-bar').nextElementSibling?.matches('.price-strip')), false);
  assert.equal(await page.locator('.book-bar #updated-at').count(), 1);
  // Làm mới ở dải mới vẫn tải lại sổ như trước.
  const before = world.reads;
  await page.locator('#refresh-data').click();
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Cập nhật'));
  assert.equal(world.reads, before + 1);
}));
