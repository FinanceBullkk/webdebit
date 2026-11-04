/* Trình duyệt (Playwright) cho thanh chip tháng và tháng đang xem của sổ khách V7 (SO-GON-05: một tháng trên màn hình,
 * specs/v7-so-khach-mot-thang.md; thay phần thu gọn tháng của SO-GON-04).
 * Sổ giả 9 tháng × 30 chuyến tính lùi từ tháng hiện tại (giờ VN), máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
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
  open: Boolean(section.querySelector('.month-body')), bar: section.querySelector('.month-card').innerText.replace(/\s+/g, ' ') })));
// Thanh của tháng nằm ngay dưới phần dính (cuộn tới tháng đó xong).
const atTop = (page, key) => page.waitForFunction(id => {
  const top = document.querySelector(`#thang-${id}`).getBoundingClientRect().top;
  return Math.abs(top - document.querySelector('.month-chips').getBoundingClientRect().bottom) <= 2;
}, key);

test('Sổ 9 tháng: lúc mở chỉ một tháng (tháng hiện tại) với dòng tóm tắt; không còn thanh tháng gập hay nút Xem chi tiết', async () => withPage(async ({ page }) => {
  const list = await sections(page);
  assert.deepEqual(list.map(item => item.id), [`thang-${MONTHS[8]}`]);
  assert.ok(list[0].open);
  // Dòng tóm tắt: Nợ đầu tháng + Phát sinh − Khách trả = Còn nợ cuối tháng, số lấy nguyên từ GET.
  assert.match(list[0].bar, new RegExp(`Nợ đầu tháng 0\\s*\\+\\s*Phát sinh 30\\.000\\.000\\s*−\\s*Khách trả 0\\s*=\\s*Còn nợ cuối tháng ${dots(endOf(8))}`));
  assert.equal(await page.locator('.month-lock').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('.month-toggle, table.month-collapsed').count(), 0);
  // 9 tháng × 30 chuyến: lúc mở chỉ vẽ 30 dòng.
  assert.equal(await page.locator('.trip-list tr[data-row]').count(), 30);
  assert.equal(await page.locator('.month-chip.on[aria-current="true"]').getAttribute('data-month'), MONTHS[8]);
  // Thanh chip thay danh sách tháng bên phải: 9 chip, còn nợ rút gọn, tháng khóa có dấu khóa.
  const chips = await page.locator('.month-chip').allInnerTexts();
  assert.equal(chips.length, 9);
  assert.doesNotMatch(chips[0], /125 triệu/);
  assert.doesNotMatch(chips[7], /1 tỷ/);
  assert.equal(await page.locator('.month-chip.locked').count(), 8);
  assert.equal(await page.locator('.months-nav').count(), 0);
}, nineMonths));

test('Phần dính đầu trang ≤ 180px khi cuộn (trừ băng dữ liệu giả); không cuộn ngang ở 1280', async () => withPage(async ({ page }) => {
  await page.evaluate(() => window.scrollTo({ top: 2400, behavior: 'instant' }));
  const geo = await page.evaluate(() => ({ banner: document.querySelector('#demo-banner').offsetHeight,
    chips: document.querySelector('.month-chips').getBoundingClientRect().top, bottom: document.querySelector('.ledger-head').getBoundingClientRect().bottom,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth }));
  assert.ok(geo.bottom - geo.banner <= 180, `phần dính ${geo.bottom - geo.banner}px`);
  assert.ok(Math.abs(geo.chips - geo.banner - 52) <= 2, 'thanh chip dính ngay dưới đầu trang 52px (canvas UuTien 3/11/2026)');
  assert.equal(geo.overflow, 0);
}, nineMonths));

test('Màn 1280 trên Chrome Windows (thanh cuộn dọc 15px, khung nhìn 1265): không cuộn ngang; cột tiền giữ khổ 1280', async () => withPage(async ({ page }) => {
  await page.setViewportSize({ width: 1265, height: 720 });
  await page.reload();
  await page.locator('.ledger-book > section .month-body').waitFor({ state: 'attached' });
  await page.waitForFunction(() => {
    const book = document.querySelector('#the-so .ledger-book').clientWidth;
    return [...document.querySelectorAll('#the-so table.ledger')].every(table => table.scrollWidth <= book);
  });
  const geo = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    money: [...document.querySelectorAll('.ledger-head col')].slice(-3).map(col => parseInt(col.style.width, 10)) }));
  assert.equal(geo.overflow, 0);
  assert.deepEqual(geo.money, [108, 82, 120]);   // Đơn giá, Khác, Thành tiền giữ khổ 1280 (SO-GON-06: không còn cột thu)
}, nineMonths));

test('Bấm chip: sổ đổi sang tháng đó, cuộn tới ngay dưới phần dính, chip được tô; không gọi API', async () => withPage(async ({ page, world }) => {
  const key = MONTHS[3];
  await page.evaluate(() => window.scrollTo({ top: 800, behavior: 'instant' }));
  await page.locator(`.month-chip[data-month="${key}"]`).click();
  await page.locator(`#thang-${key} .month-body`).waitFor();
  await atTop(page, key);
  assert.deepEqual((await sections(page)).map(item => item.id), [`thang-${key}`]);
  await page.waitForFunction(id => document.querySelector(`.month-chip[data-month="${id}"]`).getAttribute('aria-current') === 'true', key);
  assert.equal(await page.locator('.month-chip[aria-current="true"]').count(), 1);
  assert.equal(await page.locator(`#thang-${key} .trip-list tr[data-row]`).count(), 30);
  assert.match((await page.locator(`#thang-${key} .month-card`).innerText()).replace(/\s+/g, ' '), new RegExp(`Còn nợ cuối tháng ${dots(endOf(3))}`));
  assert.equal(world.requests.length, 0);
}, nineMonths));

test('Không sang tháng khác khi tháng đang xem có dòng hỏi; số tiền không đổi', async () => withPage(async ({ page, world }) => {
  const key = MONTHS[8];
  const total = await page.locator('.head-item.total strong').textContent();
  const chip = page.locator(`.month-chip[data-month="${MONTHS[7]}"]`);
  // Dòng hỏi "Xóa hẳn" đang mở trong tháng: sang tháng khác sẽ làm mất nó, nên chặn và báo.
  await page.locator(`#thang-${key} td.row-delete[data-kind="trip"]`).first().focus();
  await page.keyboard.press('Enter');
  await page.locator(`#thang-${key} .delete-prompt`).waitFor();
  await chip.click();
  assert.match(await page.locator('.live-notice').innerText(), /còn ô đang sửa hoặc câu hỏi chưa trả lời/);
  assert.equal(await page.locator(`#thang-${key} .month-body`).count(), 1);
  await page.locator(`#thang-${key} .cancel-delete`).click();
  await chip.click();
  await page.locator(`#thang-${MONTHS[7]} .month-body`).waitFor();
  assert.ok(await chip.evaluate(link => document.activeElement === link), 'tiêu điểm ở lại chip vừa bấm');
  assert.equal(await page.locator('.head-item.total strong').textContent(), total);
  assert.equal(world.requests.length, 0);
}, nineMonths));

test('?month= mở đúng tháng cũ và cuộn tới; chỉ tháng đó hiện', async () => withPage(async ({ page }) => {
  const key = MONTHS[2];
  await page.locator(`#thang-${key} .month-body`).waitFor();
  await atTop(page, key);
  assert.deepEqual((await sections(page)).map(item => item.id), [`thang-${key}`]);
}, world => { nineMonths(world); world.month = MONTHS[2]; }));

test('Tháng hiện tại chưa có số liệu: mở tháng gần nhất có số liệu; chip tháng hiện tại vẫn có', async () => withPage(async ({ page }) => {
  await page.locator(`#thang-${MONTHS[7]} .month-body`).waitFor();
  assert.deepEqual((await sections(page)).map(item => item.id), [`thang-${MONTHS[7]}`]);
  assert.equal(await page.locator(`.month-chip[data-month="${MONTHS[8]}"]`).count(), 1);
}, world => {
  nineMonths(world);
  world.trips = world.trips.filter(trip => trip.month !== `${MONTHS[8]}-01`);
  delete world.monthValues[`${MONTHS[8]}-01`];
}));

test('?loc=thieu-gia: mở tháng cũ có chuyến thiếu giá; chip có chấm việc chờ', async () => withPage(async ({ page }) => {
  const key = MONTHS[1];
  await page.locator('.loc-bar').waitFor();
  assert.match(await page.locator('.loc-bar').innerText(), /1 chuyến thiếu đơn giá/);
  assert.equal(await page.locator(`#thang-${key} tr.loc-hit`).count(), 1);
  assert.equal(await page.locator(`.month-chip[data-month="${key}"] .chip-work`).innerText(), '1');
  assert.equal(await page.locator(`.month-chip[data-month="${key}"] .chip-work`).getAttribute('title'), '1 chưa có giá');
  assert.deepEqual((await sections(page)).map(item => item.id), [`thang-${key}`]);
}, world => {
  nineMonths(world);
  world.query = '&loc=thieu-gia';
  Object.assign(world.trips.find(trip => trip.month === `${MONTHS[1]}-01`), { unit_price_vnd: null, amount_vnd: null, is_missing_price: true });
}));
