/* TUONG-TAC-01, TINH-HINH-01: thẻ Tình hình — mở tại chỗ, ghim tháng, dòng tiền về. Máy chủ giả, dữ liệu giả, đồng hồ trang ghim 15/11/2026;
 * không chạm DB hay Sheet. Bố cục và số gốc đã có ở test-so-khach-v7-overview-browser.js. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, reload } = require('./so-khach-v7-browser-world');

const TODAY = '2026-11-15';
const M = millions => String(millions * 1000000);
const FLOW = [['2026-01', 60, 50], ['2026-02', 110, 0], ['2026-03', 95, 100], ['2026-04', 70, 70], ['2026-06', 130, 50], ['2026-07', 100, 0],
  ['2026-08', 140, 100], ['2026-09', 93, 50], ['2026-10', 200, 157], ['2026-11', 50, 30]];
const OPEN = { '2026-07': 8, '2026-08': 140, '2026-09': 93, '2026-10': 200, '2026-11': 50 };
let running = 0;
const MONTHS = FLOW.map(([key, charges, received]) => ({ month: `${key}-01`, prior_months_vnd: '0', charges_vnd: M(charges), received_vnd: M(received),
  end_of_month_vnd: M(running += charges - received), outstanding_vnd: M(OPEN[key] ?? 0) }));
const RULE = { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 };
const trip = (id, month, day, destination, extra = {}) => ({ id, month: `${month}-01`, container: `TINH${String(id).padStart(7, '0')}`, carrier: 'Tàu thử',
  event_date: `${month}-${day}`, origin: 'Nơi A', destination, unit_price_vnd: '1000000', other_fee_vnd: null, amount_vnd: '1000000',
  status: 'confirmed', is_missing_price: false, is_fee_only: false, editable: true, info_editable: true, deleted: false, ...extra });
const legacy = (id, kind, month, current, display = {}) => ({ id, kind, month: `${month}-01`, display: { row: id, flags: [], ...display },
  current: { month: `${month}-01`, deleted: false, counted_vnd: '0', ...current } });

function world(state) {
  Object.assign(state, { clock: `${TODAY}T10:00:00+07:00`, todayMonth: '2026-11-01', month: null, query: '&the=tinh-hinh', months: MONTHS, total: M(491) });
  // Bỏ dòng mặc định của máy chủ giả để đếm chuyến và tiền về chỉ theo dữ liệu dưới đây.
  for (const list of [state.trips, state.legacy, state.receipts]) list.length = 0;
  state.trips.push(trip(31, '2026-07', '10', 'Nơi B'), trip(32, '2026-07', '10', 'Nơi B'), trip(33, '2026-08', '12', 'Nơi C'),
    trip(34, '2026-10', '05', 'Nơi B'), trip(35, '2026-10', '20', 'Nơi C'),
    trip(41, '2026-11', '12', 'Nơi B', { unit_price_vnd: null, amount_vnd: null, is_missing_price: true }), trip(42, '2026-11', '13', 'Nơi B'));
  // Khoản thu sổ gốc chưa sửa đúng dạng API thật: current null, số ở source_total_vnd.
  state.legacy.push({ id: 51, kind: 'receipt', month: '2026-02-01', source_total_vnd: M(40), display: { row: 51, flags: [], date: null }, current: null }, legacy(52, 'trip', '2026-03', { event_date: '2026-03-09', container: 'OLDU0000052', destination: 'Nơi Cũ', unit_price_vnd: M(9), counted_vnd: M(9) }, { date: '2026-03-09' }));
  state.receipts.push({ id: 61, pid: 'PH-61', date: '2026-10-18', amount_vnd: M(157), method: 'CK', voided_by_event: null, allocations: [{ month: '2026-07-01', kind: 'debt', amount_vnd: M(92) }, { month: '2026-06-01', kind: 'debt', amount_vnd: M(65) }] });
  state.debt = { as_of: TODAY, month: '2026-11-01', rule: RULE, receivable_vnd: M(491), customers: [{ customer_id: 1, name: 'Khách Thử Sửa',
    commodity: null, transport_mode: null, outstanding_vnd: M(491), tiers_vnd: [M(50), M(200), M(233), M(8), '0'], overdue_vnd: M(241),
    long_overdue_vnd: M(8), oldest_open_month: '2026-07-01', last_receipt_date: '2026-10-18', last_receipt_exact: true, pay_days: 28,
    last_trip_date: '2026-10-31', last_trip_exact: false, trip_days: 15, risk: 'high',
    months: Object.entries(OPEN).map(([key, value]) => ({ month: `${key}-01`, outstanding_vnd: M(value) })) }] };
}
const ready = page => page.locator('#the-tinh-hinh .ov-risk.r-high').waitFor();
const the = page => page.evaluate(() => document.body.dataset.the);
const pinned = page => page.locator('#ov-pin strong').first();
const clean = text => text.replace(/\s+/g, ' ').trim();

test('Bấm số nợ mở từng tháng tại chỗ, cộng bằng số trên thanh; một lúc một khung; Đóng trả tiêu điểm; không gọi API', () => withPage(async ({ page, world: server }) => {
  await ready(page);
  const reads = server.reads;
  await page.locator('.ov-part[data-tier="late"]').click();
  const panel = page.locator('#ov-panel');
  await panel.waitFor();
  assert.equal(await the(page), 'tinh-hinh');
  assert.equal(await page.locator('.ov-part[data-tier="late"]').getAttribute('aria-expanded'), 'true');
  assert.deepEqual((await panel.locator('.ov-row').allInnerTexts()).map(clean), ['T7 8 triệu quá hạn 76 ngày', 'T8 140 triệu quá hạn 46 ngày', 'T9 93 triệu quá hạn 15 ngày']);
  assert.equal(await page.locator('#ov-segments').getAttribute('data-hot'), 'late');
  await page.locator('.ov-part[data-tier="due"]').click();
  assert.deepEqual((await panel.locator('.ov-row').allInnerTexts()).map(clean), ['T10 200 triệu còn 15 ngày · hạn 30/11']);
  assert.equal(await page.locator('.ov-part[data-tier="late"]').getAttribute('aria-expanded'), 'false');
  await page.locator('.ov-segment.future').click();
  assert.deepEqual((await panel.locator('.ov-row').allInnerTexts()).map(clean), ['T11 50 triệu hạn 31/12']);
  await panel.locator('.ov-close').click();
  await panel.waitFor({ state: 'detached' });
  assert.equal(await page.locator('.ov-part[data-tier="future"]').evaluate(node => node === document.activeElement), true);
  assert.equal(server.reads, reads);
}, world));

test('Nhãn rủi ro là chữ; dữ kiện luôn hiện, ngày không chắc nói rõ; số tiền của lần trả cộng đúng ngày', () => withPage(async ({ page }) => {
  await ready(page);
  assert.equal(await page.locator('.ov-hero button.ov-risk, .ov-risk-btn').count(), 0);
  assert.deepEqual((await page.locator('.ov-keyfact').allInnerTexts()).map(clean), [
    'Trả gần nhất 18/10/2026 157 triệu · 28 ngày trước', 'Thu T11 30 triệu phát sinh 50 triệu',
    'Đi hàng gần nhất trong tháng 10/2026 T11: 2 chuyến · T10: 2', 'Quá hạn lâu nhất T7 · 76 ngày còn 8 triệu']);
}, world));

test('Số từng tháng lệch Tổng quan thì không hiện từng tháng, chỉ cho mở ở Sổ', () => withPage(async ({ page }) => {
  await ready(page);
  await page.locator('.ov-part[data-tier="late"]').click();
  assert.match(await page.locator('#ov-panel').innerText(), /chưa tách được theo tháng/);
  assert.equal(await page.locator('#ov-panel .ov-row').count(), 0);
  await page.locator('#ov-panel .ov-link-btn').click();
  assert.equal(await the(page), 'so');
}, state => { world(state); state.debt.customers[0].tiers_vnd[2] = M(234); }));

test('Rê một tháng hiện bốn số, không đổi trang; Tab tới cũng vậy; tháng không có dòng không bấm được', () => withPage(async ({ page, world: server }) => {
  await ready(page);
  const reads = server.reads;
  const tip = page.locator('#ov-tip');
  assert.equal(await tip.isHidden(), true);
  await page.locator('.ov-month[data-key="2026-09"]').hover();
  assert.equal(clean(await tip.innerText()), 'T9 Phát sinh 93.000.000 đ Đã thu 50.000.000 đ Còn nợ cuối tháng 491.000.000 đ Chuyến 0'.replace('491.000.000', String(MONTHS.find(row => row.month === '2026-09-01').end_of_month_vnd).replace(/\B(?=(\d{3})+(?!\d))/g, '.')));
  assert.equal(await page.locator('.ov-month.hot').getAttribute('data-key'), '2026-09');
  await page.locator('.ov-total').hover();
  assert.equal(await tip.isHidden(), true);
  assert.equal(await page.locator('.ov-month.hot').count(), 0);
  await page.locator('.ov-month[data-key="2026-10"]').focus();
  assert.match(await tip.innerText(), /^T10/);
  assert.equal(await page.locator('.ov-month.off[title*="T5"] ').count(), 1);
  assert.equal(await page.locator('span.ov-month.off').evaluateAll(nodes => nodes.every(node => !node.dataset.ui)), true);
  assert.equal(server.reads, reads);
  assert.equal(server.requests.length, 0);
}, world));

test('Ghim tháng: dải số, Tiền về chỉ còn tháng đó, chip bỏ; bấm lại hoặc ✕ để bỏ; Mở sổ đúng tháng', () => withPage(async ({ page }) => {
  await ready(page);
  const column = page.locator('.ov-month[data-key="2026-10"]');
  await column.click();
  await pinned(page).waitFor();
  assert.equal(await pinned(page).innerText(), 'T10');
  assert.equal(await page.locator('.ov-month[data-key="2026-10"]').getAttribute('aria-pressed'), 'true');
  assert.deepEqual((await page.locator('#ov-pin span').allInnerTexts()).map(clean).slice(0, 2), ['Phát sinh 200 triệu', 'Đã thu 157 triệu']);
  assert.equal(await page.locator('.ov-month[data-key="2026-10"]').evaluate(node => node === document.activeElement), true, 'giữ tiêu điểm');
  assert.deepEqual(await page.locator('.ov-event-row time').allInnerTexts(), ['18/10/2026']);
  // Bỏ bằng chip ở Tiền về: tiêu điểm về cột của tháng đó.
  await page.locator('.ov-activity .ov-chip').click();
  await page.locator('#ov-pin').waitFor({ state: 'detached' });
  assert.equal(await page.locator('.ov-month[data-key="2026-10"]').evaluate(node => node === document.activeElement), true);
  assert.equal(await page.locator('.ov-event-row').count(), 2);
  // Tháng không có khoản thu thì nói rõ.
  await page.locator('.ov-month[data-key="2026-08"]').click();
  await pinned(page).waitFor();
  assert.equal(await page.locator('.ov-none').innerText(), 'Không có khoản thu trong T8.');
  // Bấm lại đúng cột là bỏ.
  await page.locator('.ov-month[data-key="2026-08"]').click();
  await page.locator('#ov-pin').waitFor({ state: 'detached' });
  await page.locator('.ov-month[data-key="2026-08"]').click();
  await page.locator('.ov-pin-open').click();
  assert.equal(await the(page), 'so');
  assert.equal(new URL(page.url()).searchParams.get('month'), '2026-08');
}, world));

test('Tiền về chỉ có tiền, không có chuyến; mở chi tiết tại dòng; khoản không ngày ghi tháng; Xem ở Sổ', () => withPage(async ({ page }) => {
  await ready(page);
  assert.deepEqual((await page.locator('.ov-event-row').allInnerTexts()).map(clean), ['18/10/2026 157.000.000 đ', 'T2/2026 40.000.000 đ']);
  assert.equal(await page.locator('.ov-more').count(), 0);
  await page.locator('.ov-event-row').nth(1).click();
  assert.match(clean(await page.locator('.ov-event-detail').innerText()), /Theo sổ gốc, ghi ở khối T2\/2026/);
  await page.locator('.ov-event-row').first().click();
  assert.match(clean(await page.locator('.ov-event-detail').innerText()), /Trừ nợ T7\/2026 92\.000\.000 đ Trừ nợ T6\/2026 65\.000\.000 đ/);
  assert.equal(await page.locator('.ov-event-detail').count(), 1, 'một lúc một dòng');
  await page.locator('.ov-event-go').click();
  assert.equal(await the(page), 'so');
}, world));

test('Nhiều khoản thu: 4 dòng rồi Xem thêm ngay trong khối', () => withPage(async ({ page }) => {
  await ready(page);
  assert.equal(await page.locator('.ov-event-row').count(), 4);
  await page.locator('.ov-more').click();
  assert.equal(await page.locator('.ov-event-row').count(), 6);
  assert.equal(await page.locator('.ov-more').count(), 0);
}, state => {
  world(state);
  for (let id = 71; id <= 74; id += 1) state.receipts.push({ id, pid: `PH-${id}`, date: `2026-09-${id - 60}`, amount_vnd: M(1), method: 'CK', voided_by_event: null, allocations: [] });
}));

test('Rê dòng tiền về: tháng của dòng sáng trên hình', () => withPage(async ({ page }) => {
  await ready(page);
  await page.locator('.ov-event-row').first().hover();
  assert.equal(await page.locator('.ov-month.hot').getAttribute('data-key'), '2026-10');
}, world));

test('Nguồn phụ về sau không làm mất tháng đang ghim, khung đang mở hay tiêu điểm', () => withPage(async ({ page }) => {
  await ready(page);
  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route(/\/api\/v7\/marks\?/, async route => { await held; await route.continue(); }, { times: 1 });
  await reload(page);
  await ready(page);
  await page.locator('.ov-month[data-key="2026-09"]').click();
  await page.locator('.ov-part[data-tier="due"]').click();
  await page.locator('.ov-part[data-tier="due"]').focus();
  const old = await page.locator('.ov-part[data-tier="due"]').elementHandle();
  release();
  await page.waitForFunction(node => !node.isConnected, old);
  assert.equal(await pinned(page).innerText(), 'T9');
  assert.equal(await page.locator('#ov-panel').count(), 1);
  assert.equal(await page.evaluate(() => document.activeElement.dataset.tier), 'due');
}, world));

test('Khách trả trước không có nhãn, không có khung; tháng ghim biến mất thì tự bỏ', () => withPage(async ({ page }) => {
  await page.locator('.ov-total').waitFor();
  assert.equal(await page.locator('.ov-risk-btn').count(), 0);
  assert.equal(await page.locator('.ov-part').count(), 0);
}, state => Object.assign(state, { clock: `${TODAY}T10:00:00+07:00`, todayMonth: '2026-11-01', month: null, query: '&the=tinh-hinh', total: '-50000000', months: [
  { month: '2026-10-01', charges_vnd: M(100), received_vnd: M(150), end_of_month_vnd: '-50000000', outstanding_vnd: '0' },
  { month: '2026-11-01', charges_vnd: '0', received_vnd: '0', end_of_month_vnd: '-50000000', outstanding_vnd: '-50000000' }] })));

test('Bố cục khi mở hết ở 1265×560 và màn hẹp: không cuộn ngang, nút đủ vùng bấm, cả font rộng hơn', () => withPage(async ({ page }) => {
  await ready(page);
  await page.locator('.ov-part[data-tier="late"]').click();
  await page.locator('.ov-month[data-key="2026-10"]').click();
  await page.locator('.ov-event-row').first().click();
  await page.setViewportSize({ width: 1265, height: 560 });
  for (const font of [null, 'Verdana, "DejaVu Sans", sans-serif']) {
    if (font) await page.addStyleTag({ content: `#the-tinh-hinh, #the-tinh-hinh * { font-family: ${font} !important; }` });
    const layout = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      small: [...document.querySelectorAll('#the-tinh-hinh button')].filter(node => node.getBoundingClientRect().height < 40).map(node => node.className),
      cut: [...document.querySelectorAll('.ov-keyfact b, .ov-keyfact small, .ov-part b')].filter(node => node.getBoundingClientRect().right > node.closest('.ov-keyfact, .ov-hero').getBoundingClientRect().right).map(node => node.innerText),
    }));
    assert.deepEqual(layout, { overflow: 0, small: [], cut: [] }, `font ${font ?? 'mặc định'}`);
  }
  await page.setViewportSize({ width: 390, height: 720 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0);
  assert.equal(await page.locator('#ov-pin .ov-pin-open').isVisible(), true);
}, world));

// Lỗi thấy khi xem ảnh render: luật cũ .ov-chart svg ép chiều cao hình nên đường Còn nợ lệch khỏi cột và chấm tháng.
test('Đường Còn nợ khớp đúng chấm từng tháng, chấm đủ lớn để thấy', () => withPage(async ({ page }) => {
  await ready(page);
  const fit = await page.evaluate(() => {
    const line = document.querySelector('.ov-lines');
    const box = line.getBoundingClientRect();
    const plot = document.querySelector('.ov-plot').getBoundingClientRect();
    const scaleY = box.height / line.viewBox.baseVal.height;
    const scaleX = box.width / line.viewBox.baseVal.width;
    const points = [...document.querySelector('.ov-line').points].map(point => [box.left + point.x * scaleX, box.top + point.y * scaleY]);
    const dots = [...document.querySelectorAll('.ov-point')].map(node => { const r = node.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, r.width]; });
    return { height: box.height, plot: plot.height, points, dots };
  });
  assert.equal(fit.height, fit.plot, 'hình cao bằng vùng vẽ');
  // Tháng không có dòng giữ số tháng trước nên đường có điểm mà không có chấm: so từng chấm với điểm gần nhất theo chiều ngang.
  assert.ok(fit.dots.length >= 8);
  for (const [x, y, width] of fit.dots) {
    const near = fit.points.reduce((best, point) => (Math.abs(point[0] - x) < Math.abs(best[0] - x) ? point : best));
    assert.ok(Math.abs(near[0] - x) < 1.5 && Math.abs(near[1] - y) < 1.5, `chấm ${[x, y]} lệch đường ${near}`);
    assert.ok(width >= 8, `chấm rộng ${width}`);
  }
}, world));
