/* Trình duyệt (Playwright): ô Đơn giá gõ là sửa như Sheet (GIA-O-01 phần A, specs/v7-o-gia-nhu-sheet.md).
 * Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { withPage, legacyCell, posts } = require('./so-khach-v7-browser-world');

const DEBIT_V4 = { ...JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'web', 'debit-note-config.default.json'), 'utf8')), template: 'v4' };

// Tháng 9/2026: sổ gốc 21 (chưa giá), 22; chuyến web 11, 13; 14 đang CHỜ KIỂM (ô giá chỉ đọc).
function moreTrips(world) {
  const trip = (id, container, extra) => ({ id, month: '2026-09-01', container, carrier: `Tàu ${id}`, event_date: '2026-09-20', origin: 'Nơi E',
    destination: 'Nơi F', unit_price_vnd: '40000000', other_fee_vnd: null, amount_vnd: '40000000', status: 'confirmed', is_missing_price: false,
    is_fee_only: false, editable: true, info_editable: true, deleted: false, ...extra });
  world.trips.push(trip(13, 'DEMU0000013'), trip(14, 'DEMU0000014', { status: 'pending_review', review_reason: 'WEB_DUPLICATE' }));
}
const price = (page, id) => page.locator(`td.editable[data-trip="${id}"]`);
const pricePosts = world => posts(world).filter(([path]) => path === '/api/v7/trips/price' || path === '/api/v7/legacy/edit');

test('ô Đơn giá chuyến web: gõ số là mở ô với số đó, Enter lưu rồi xuống ô dưới', async () => withPage(async ({ page, world }) => {
  await price(page, 11).focus();
  await page.keyboard.press('4');
  assert.equal(await page.locator('td.editable[data-trip="11"] .money-input').inputValue(), '4', 'số vừa gõ thay giá cũ, không cộng vào sau');
  await page.keyboard.type('5000000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.editable[data-trip="11"]')?.textContent.startsWith('45.000.000'));
  assert.deepEqual(pricePosts(world).at(-1), ['/api/v7/trips/price', { ...pricePosts(world).at(-1)[1], trip_id: 11, unit_price_vnd: '45000000', other_fee_vnd: null }]);
  // Enter lưu thì tiêu điểm xuống ô Đơn giá hàng dưới; gõ tiếp là sửa luôn chuyến đó.
  assert.equal(await price(page, 13).evaluate(cell => cell === document.activeElement), true);
  await page.keyboard.type('41000000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.editable[data-trip="13"]')?.textContent.startsWith('41.000.000'));
  assert.deepEqual(pricePosts(world).map(([, body]) => [body.trip_id, body.unit_price_vnd]), [[11, '45000000'], [13, '41000000']]);
}, moreTrips));

test('ô Đơn giá dòng sổ gốc: gõ số là mở ô, Enter lưu', async () => withPage(async ({ page, world }) => {
  const cell = legacyCell(page, 21, 'unit_price_vnd');
  await cell.focus();
  await page.keyboard.press('7');
  assert.equal(await page.locator('.info-edit[data-kind="legacy"][data-id="21"] .money-input').inputValue(), '7');
  await page.keyboard.type('0.000.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.info-edit[data-kind="legacy"][data-id="21"][data-field="unit_price_vnd"]')?.textContent.startsWith('70.000.000'));
  assert.deepEqual(pricePosts(world).at(-1), ['/api/v7/legacy/edit', { ...pricePosts(world).at(-1)[1], legacy_row_id: 21, field: 'unit_price_vnd', value: '70000000' }]);
}, moreTrips));

// Sửa 13/11/2026 (NHAP-SHEET-01: rời ô là lưu): gõ giá rồi bấm chuột ra chỗ khác thì vẫn lưu như ô chữ; trước đây chỉ Enter/Tab mới lưu,
// số nằm lại trong ô nhập mà máy chủ không có — debit note xuất ra thiếu giá.
test('ô Đơn giá chuyến web: gõ giá rồi bấm chuột ra ngoài là lưu, một lệnh', async () => withPage(async ({ page, world }) => {
  await price(page, 11).focus();
  await page.keyboard.type('45000000');
  await page.locator('.book-head').click();
  await page.waitForFunction(() => document.querySelector('td.editable[data-trip="11"]')?.textContent.startsWith('45.000.000'));
  assert.equal(await page.locator('td.editable[data-trip="11"] input').count(), 0);
  assert.deepEqual(pricePosts(world).map(([, body]) => [body.trip_id, body.unit_price_vnd]), [[11, '45000000']]);
  // Esc rồi bấm ra ngoài: không lưu gì thêm.
  await price(page, 13).focus();
  await page.keyboard.type('9');
  await page.keyboard.press('Escape');
  await page.locator('.book-head').click();
  assert.equal(pricePosts(world).length, 1);
}, moreTrips));

test('ô Đơn giá chuyến web: gõ giá rồi bấm thẳng Debit note thì chứng từ có giá vừa gõ', async () => withPage(async ({ page, world }) => {
  // Máy chủ ghi chậm: hộp debit phải chờ lệnh ghi xong và sổ đọc lại rồi mới dựng chứng từ.
  await page.route('**/api/v7/trips/price', async route => { await new Promise(done => setTimeout(done, 400)); await route.continue(); });
  await price(page, 11).focus();
  await page.keyboard.type('45000000');
  await page.locator('#thang-2026-09 .debit-open').click();
  await page.frameLocator('.debit-preview').locator('[data-page]').first().waitFor();
  // Tháng 9: chuyến 11 (45.000.000 vừa gõ) + 13 (40.000.000) + sổ gốc 22 (93.000.000); sổ gốc 21 chưa giá; 14 chờ kiểm không lên.
  assert.equal(await page.locator('.debit-dialog .debit-status').innerText(), '4 container · 178.000.000 đ · 1 chuyến chưa có giá');
  assert.match(await page.frameLocator('.debit-preview').locator('[data-row]', { hasText: 'DEMU1234567' }).innerText(), /45,000,000/);
  assert.deepEqual(pricePosts(world).map(([, body]) => [body.trip_id, body.unit_price_vnd]), [[11, '45000000']]);
}, world => { moreTrips(world); world.debitConfig = DEBIT_V4; }));

test('không mở khi: Esc trả lại, chữ cái, phím Ctrl, ô chỉ đọc của chuyến chờ kiểm', async () => withPage(async ({ page, world }) => {
  await price(page, 11).focus();
  await page.keyboard.press('9');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('td.editable[data-trip="11"] input').count(), 0);
  assert.equal(await price(page, 11).evaluate(cell => cell === document.activeElement), true, 'Esc trả tiêu điểm về ô');
  assert.match(await price(page, 11).innerText(), /^50\.000\.000/);
  await page.keyboard.press('a');
  await page.keyboard.press('Control+1');
  assert.equal(await page.locator('td.editable[data-trip="11"] input').count(), 0);
  // Ô giá của chuyến chờ kiểm là ô chỉ đọc: đứng được (mũi tên) nhưng gõ số không mở gì.
  await price(page, 13).focus();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('5');
  assert.equal(await page.locator('tr[data-row="trip-14"] input').count(), 0);
  assert.equal(pricePosts(world).length, 0);
}, moreTrips));
