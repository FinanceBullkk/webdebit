/* Trình duyệt (Playwright) cho thanh tháng và tháng thu gọn của sổ khách V7 (SO-GON-04, specs/v7-so-khach-ux-dot-2.md, PR 2a).
 * Sổ giả 9 tháng × 30 chuyến tính lùi từ tháng hiện tại (giờ VN), máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { todayMonth, withPage } = require('./so-khach-v7-browser-world');

const shift = (key, back) => {
  let year = Number(key.slice(0, 4)), month = Number(key.slice(5, 7)) - back;
  while (month < 1) { month += 12; year -= 1; }
  return `${year}-${String(month).padStart(2, '0')}`;
};
// Cũ → mới; tháng cuối là tháng hiện tại.
const MONTHS = Array.from({ length: 9 }, (_, index) => shift(todayMonth.slice(0, 7), 8 - index));
const endOf = index => String((index + 1) * 125000000);
const dots = value => value.replace(/\B(?=(\d{3})+(?!\d))/g, '.');

// Sổ 9 tháng, mỗi tháng 30 chuyến đã có giá; chỉ tháng hiện tại mở khóa; mặc định của trang (không ?month=).
function nineMonths(world) {
  world.month = null;
  world.locks = [];
  world.legacy = [];
  world.trips = MONTHS.flatMap((key, monthIndex) => Array.from({ length: 30 }, (_, index) => ({
    id: 1000 + monthIndex * 100 + index, month: `${key}-01`, container: `NINE${monthIndex}${String(index).padStart(6, '0')}`, carrier: 'Tàu thử',
    event_date: `${key}-${String(1 + (index % 28)).padStart(2, '0')}`, origin: 'Nơi A', destination: 'Nơi B', unit_price_vnd: '1000000',
    other_fee_vnd: null, amount_vnd: '1000000', status: 'confirmed', is_missing_price: false, is_fee_only: false, editable: true,
    info_editable: true, deleted: false })));
  world.monthValues = Object.fromEntries(MONTHS.map((key, index) => [`${key}-01`,
    { prior_months_vnd: '0', charges_vnd: '30000000', received_vnd: '0', end_of_month_vnd: endOf(index), outstanding_vnd: '30000000' }]));
}
const sections = page => page.$$eval('.ledger-book > section', list => list.map(section => ({ id: section.id,
  open: Boolean(section.querySelector('.month-body')), bar: section.querySelector('tr.month th').innerText })));
// Thanh của tháng nằm ngay dưới phần dính (cuộn tới tháng đó xong).
const atTop = (page, key) => page.waitForFunction(id => {
  const top = document.querySelector(`#thang-${id}`).getBoundingClientRect().top;
  return Math.abs(top - document.querySelector('.ledger-head').getBoundingClientRect().bottom) <= 2;
}, key);

test('Sổ 9 tháng: lúc mở chỉ tháng hiện tại và tháng liền trước hiện chi tiết; tháng cũ thu gọn còn số chuyến và còn nợ cuối tháng', async () => withPage(async ({ page }) => {
  const list = await sections(page);
  assert.deepEqual(list.map(item => item.id), MONTHS.map(key => `thang-${key}`));
  assert.deepEqual(list.filter(item => item.open).map(item => item.id), MONTHS.slice(-2).map(key => `thang-${key}`));
  for (const [index, item] of list.entries()) {
    assert.match(item.bar, new RegExp(`Còn nợ cuối tháng: ${dots(endOf(index))}`), item.id);
    assert.match(item.bar, item.open ? /Thu gọn/ : /30 chuyến[\s\S]*Xem chi tiết/, item.id);
  }
  // 9 tháng × 30 chuyến: lúc mở chỉ vẽ 60 dòng.
  assert.equal(await page.locator('.trip-list tr[data-row]').count(), 60);
  // Thanh chip thay danh sách tháng bên phải: 9 chip, còn nợ rút gọn, tháng khóa có dấu khóa.
  const chips = await page.locator('.month-chip').allInnerTexts();
  assert.equal(chips.length, 9);
  assert.match(chips[0], /125 triệu/);
  assert.match(chips[7], /1 tỷ/);
  assert.equal(await page.locator('.month-chip.locked').count(), 8);
  assert.equal(await page.locator('.months-nav').count(), 0);
}, nineMonths));

test('Phần dính đầu trang ≤ 180px khi cuộn (trừ băng dữ liệu giả); không cuộn ngang ở 1280', async () => withPage(async ({ page }) => {
  await page.evaluate(() => window.scrollTo({ top: 2400, behavior: 'instant' }));
  const geo = await page.evaluate(() => ({ banner: document.querySelector('#demo-banner').offsetHeight,
    chips: document.querySelector('.month-chips').getBoundingClientRect().top, bottom: document.querySelector('.ledger-head').getBoundingClientRect().bottom,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth }));
  assert.ok(geo.bottom - geo.banner <= 180, `phần dính ${geo.bottom - geo.banner}px`);
  assert.equal(geo.chips - geo.banner, 104, 'thanh chip dính ngay dưới đầu sổ');
  assert.equal(geo.overflow, 0);
}, nineMonths));

test('Bấm chip của tháng thu gọn: tháng hiện chi tiết, cuộn tới ngay dưới phần dính, chip được tô', async () => withPage(async ({ page, world }) => {
  const key = MONTHS[3];
  await page.locator(`.month-chip[data-month="${key}"]`).click();
  await page.locator(`#thang-${key} .month-body`).waitFor();
  await atTop(page, key);
  await page.waitForFunction(id => document.querySelector(`.month-chip[data-month="${id}"]`).getAttribute('aria-current') === 'true', key);
  assert.equal(await page.locator('.month-chip[aria-current="true"]').count(), 1);
  assert.equal(await page.locator(`#thang-${key} .trip-list tr[data-row]`).count(), 30);
  assert.equal(world.requests.length, 0);
}, nineMonths));

test('Thu gọn / Xem chi tiết; không thu gọn khi tháng đang có dòng hỏi; số tiền không đổi', async () => withPage(async ({ page, world }) => {
  const key = MONTHS[8];
  const total = await page.locator('.head-item.total strong').innerText();
  const toggle = page.locator(`#thang-${key} .month-toggle`);
  // Dòng hỏi "Xóa hẳn" đang mở trong tháng: thu gọn sẽ làm mất nó, nên chặn và báo.
  await page.locator(`#thang-${key} td.row-delete[data-kind="trip"]`).first().focus();
  await page.keyboard.press('Enter');
  await page.locator(`#thang-${key} .delete-prompt`).waitFor();
  await toggle.click();
  assert.match(await page.locator('.live-notice').innerText(), /còn ô đang sửa hoặc câu hỏi chưa trả lời/);
  assert.equal(await page.locator(`#thang-${key} .month-body`).count(), 1);
  await page.locator(`#thang-${key} .cancel-delete`).click();
  await toggle.click();
  await page.locator(`#thang-${key} table.month-collapsed`).waitFor();
  assert.equal(await toggle.innerText(), 'Xem chi tiết');
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  assert.ok(await toggle.evaluate(button => document.activeElement === button), 'tiêu điểm ở lại nút vừa bấm');
  assert.match(await page.locator(`#thang-${key} tr.month th`).innerText(), new RegExp(`Còn nợ cuối tháng: ${dots(endOf(8))}`));
  assert.equal(await page.locator('.head-item.total strong').innerText(), total);
  await toggle.click();
  await page.locator(`#thang-${key} .month-body`).waitFor();
  assert.equal(await toggle.innerText(), 'Thu gọn');
  assert.equal(world.requests.length, 0);
}, nineMonths));

test('?month= mở đúng tháng cũ và cuộn tới; các tháng cũ khác vẫn thu gọn', async () => withPage(async ({ page }) => {
  const key = MONTHS[2];
  await page.locator(`#thang-${key} .month-body`).waitFor();
  await atTop(page, key);
  const open = (await sections(page)).filter(item => item.open).map(item => item.id);
  assert.deepEqual(open, [MONTHS[2], MONTHS[7], MONTHS[8]].map(month => `thang-${month}`));
}, world => { nineMonths(world); world.month = MONTHS[2]; }));

test('?loc=thieu-gia: tháng cũ có chuyến thiếu giá tự hiện chi tiết; chip có chấm việc chờ', async () => withPage(async ({ page }) => {
  const key = MONTHS[1];
  await page.locator('.loc-bar').waitFor();
  assert.match(await page.locator('.loc-bar').innerText(), /1 chuyến thiếu đơn giá/);
  assert.equal(await page.locator(`#thang-${key} tr.loc-hit`).count(), 1);
  assert.equal(await page.locator(`.month-chip[data-month="${key}"] .chip-work`).innerText(), '1');
  assert.equal(await page.locator(`.month-chip[data-month="${key}"] .chip-work`).getAttribute('title'), '1 chưa có giá');
  const open = (await sections(page)).filter(item => item.open).map(item => item.id);
  assert.deepEqual(open, [MONTHS[1], MONTHS[7], MONTHS[8]].map(month => `thang-${month}`));
}, world => {
  nineMonths(world);
  world.query = '&loc=thieu-gia';
  Object.assign(world.trips.find(trip => trip.month === `${MONTHS[1]}-01`), { unit_price_vnd: null, amount_vnd: null, is_missing_price: true });
}));
