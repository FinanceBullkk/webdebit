/* Trình duyệt (Playwright) cho thẻ Tình hình của trang khách (TRANG-KHACH-01, specs/v7-trang-khach.md, PR A2): bốn số và mức
 * rủi ro bằng đúng sổ và Tổng quan, hình 12 tháng bằng months[] và bấm tháng sang thẻ Sổ, số chuyến 6 tháng, việc chờ mở thẻ Sổ
 * với loc=, khách chưa có số dư đầu, khách dư, Tổng quan và lần nhắc đọc lỗi. Máy chủ giả, dữ liệu giả, 1280×720, đồng hồ trang
 * ghim 15/11/2026 (giờ VN); không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage } = require('./so-khach-v7-browser-world');

const TODAY = '2026-11-15';
const M = millions => String(millions * 1000000);
// Sổ giả 16 tháng (8/2025–11/2026), không có dòng nào tháng 5/2026; còn nợ cuối tháng cộng dồn phát sinh − đã thu, nợ còn ở T7–T11.
const FLOW = [['2025-08', 100, 0], ['2025-09', 120, 100], ['2025-10', 90, 120], ['2025-11', 80, 90], ['2025-12', 150, 80], ['2026-01', 60, 150],
  ['2026-02', 110, 0], ['2026-03', 95, 100], ['2026-04', 70, 70], ['2026-06', 130, 50], ['2026-07', 100, 0], ['2026-08', 140, 100],
  ['2026-09', 93, 50], ['2026-10', 200, 157], ['2026-11', 50, 30]];
const OPEN = { '2026-07': 8, '2026-08': 140, '2026-09': 93, '2026-10': 200, '2026-11': 50 };
let running = 0;
const MONTHS = FLOW.map(([key, charges, received]) => ({ month: `${key}-01`, prior_months_vnd: '0', charges_vnd: M(charges), received_vnd: M(received),
  end_of_month_vnd: M(running += charges - received), outstanding_vnd: M(OPEN[key] ?? 0) }));
const RULE = { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 };
const trip = (id, month, extra = {}) => ({ id, month: `${month}-01`, container: `TINH${String(id).padStart(7, '0')}`, carrier: 'Tàu thử',
  event_date: `${month}-10`, origin: 'Nơi A', destination: 'Nơi B', unit_price_vnd: '1000000', other_fee_vnd: null, amount_vnd: '1000000',
  status: 'confirmed', is_missing_price: false, is_fee_only: false, editable: true, info_editable: true, deleted: false, ...extra });

// Khách đang nợ: chuyến thiếu giá, chờ kiểm, đã loại, phí lẻ ở tháng 11; một chuyến Sheet chờ duyệt, một giá Sheet chờ ghi.
function debtor(world) {
  Object.assign(world, { clock: `${TODAY}T10:00:00+07:00`, todayMonth: '2026-11-01', month: null, query: '&the=tinh-hinh', months: MONTHS, total: M(491) });
  world.trips.push(trip(31, '2026-07'), trip(32, '2026-07'), trip(33, '2026-08'), trip(34, '2026-10'), trip(35, '2026-10'), trip(36, '2026-10'),
    trip(41, '2026-11', { unit_price_vnd: null, amount_vnd: null, is_missing_price: true, event_date: '2026-11-12' }),
    trip(42, '2026-11', { status: 'pending_review', review_reason: 'WEB_DUPLICATE', amount_vnd: null, editable: false }),
    trip(43, '2026-11', { status: 'rejected', amount_vnd: null, editable: false }),
    trip(44, '2026-11', { container: null, unit_price_vnd: null, other_fee_vnd: '500000', amount_vnd: '500000', is_fee_only: true }));
  world.sheetSync = { snapshot_sha256: 'a'.repeat(64), new_count: 1, conflict_count: 0, items: [
    { sync_state: 'NEW', event_date: '2026-11-13', container: 'NEWU7654321', carrier: 'WH', origin: 'A', destination: 'B' }] };
  world.sheetPrices = { snapshot_sha256: 'c'.repeat(64), review: [], ready_count: 1, review_count: 0, ready: [{ target_kind: 'trip', target_id: 41,
    sheet_unit_price_vnd: '1200000', sheet_other_fee_vnd: null, web_unit_price_vnd: null, web_other_fee_vnd: null, status: 'READY',
    container: 'TINH0000041', date: '2026-11-12', source_tab: 'Khách Thử Sửa', source_row: 41 }] };
  world.debt = { as_of: TODAY, month: '2026-11-01', rule: RULE, receivable_vnd: M(491), customers: [{ customer_id: 1, name: 'Khách Thử Sửa',
    commodity: null, transport_mode: null, outstanding_vnd: M(491), tiers_vnd: [M(50), M(200), M(233), M(8), '0'], overdue_vnd: M(241),
    long_overdue_vnd: M(8), oldest_open_month: '2026-07-01', last_receipt_date: '2026-11-05', last_receipt_exact: true, pay_days: 10,
    last_trip_date: '2026-11-12', last_trip_exact: true, trip_days: 3, risk: 'high',
    months: Object.entries(OPEN).map(([key, value]) => ({ month: `${key}-01`, outstanding_vnd: M(value) })) }] };
  world.reminders = [{ customer_id: 1, last_reminded: '2026-11-10', reminder_count: 3, last_source: 'copy-button' }];
}

const state = page => page.evaluate(() => [document.body.dataset.the, location.search]);
const ready = page => page.locator('#the-tinh-hinh .ov-risk.r-high').waitFor();

test('Bố cục và số của Tình hình lấy từ sổ, Tổng quan; mở tháng không đọc lại sổ', async () => withPage(async ({ page, world, shot }) => {
  await ready(page);
  await shot('tinh-hinh');
  assert.equal(await page.locator('.ov-total').innerText(), '491.000.000 đ');
  assert.deepEqual(await page.locator('.ov-part').evaluateAll(nodes => nodes.map(node => node.innerText)),
    ['Quá hạn\n241 triệu', 'Đến hạn 30/11\n200 triệu', 'Chưa đến hạn\n50 triệu']);
  assert.equal(await page.locator('.ov-risk').innerText(), 'Rủi ro cao');
  assert.equal(await page.locator('.ov-stat').nth(0).locator('strong').innerText(), '—');
  assert.match(await page.locator('.ov-stat').nth(1).innerText(), /Phát sinh đã ghi sổ trong 12 tháng/);
  assert.match(await page.locator('.ov-stat').nth(2).innerText(), /2 chuyến tháng này/);
  assert.equal(await page.locator('.ov-next-main strong').innerText(), 'Nhắc nợ ngay');
  assert.equal(await page.locator('.ov-activity li').count(), 4);
  const layout = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    small: [...document.querySelectorAll('#the-tinh-hinh button')].filter(node => node.getBoundingClientRect().height < 40).map(node => node.textContent),
    font: getComputedStyle(document.querySelector('#the-tinh-hinh')).fontSize
  }));
  assert.deepEqual(layout, { overflow: 0, small: [], font: '16px' });
  assert.deepEqual([...new Set(world.sideReads)].sort(), ['/api/v7/dashboard/debt', '/api/v7/reminders']);
  const reads = world.reads;
  await page.locator('.ov-part-link').first().click();
  assert.deepEqual(await state(page), ['so', '?customer=1&month=2026-07']);
  assert.equal(world.reads, reads);
}, debtor));

test('Hình 12 tháng dùng months[]; tháng thiếu không thành 0; mở đúng tháng', async () => withPage(async ({ page, world }) => {
  await ready(page);
  const chart = await page.evaluate(() => {
    const read = selector => Object.fromEntries([...document.querySelectorAll('#the-tinh-hinh ' + selector)].map(node => [node.dataset.month, node.dataset.vnd]));
    return { ps: read('.ov-bar.ps'), thu: read('.ov-bar.thu'), end: read('.ov-point'),
      names: [...document.querySelector('.ov-months').children].map(node => [node.textContent, node.dataset.go ?? null]) };
  });
  const shown = MONTHS.filter(row => row.month >= '2025-12-01').map(row => [row.month.slice(0, 7), row]);
  assert.deepEqual(chart.ps, Object.fromEntries(shown.map(([key, row]) => [key, row.charges_vnd])));
  assert.deepEqual(chart.thu, Object.fromEntries(shown.map(([key, row]) => [key, row.received_vnd])));
  assert.deepEqual(chart.end, Object.fromEntries(shown.map(([key, row]) => [key, row.end_of_month_vnd])));
  assert.equal(chart.ps['2026-05'], undefined);
  assert.deepEqual(chart.names.filter(([, go]) => !go).map(([text]) => text), ['T5']);
  assert.deepEqual(chart.names.at(-1), ['T11đến 15/11', 'thang:2026-11'], 'tháng đang chạy ghi tới hôm nay');
  await page.locator('.ov-month[data-go="thang:2026-08"]').first().click();
  assert.deepEqual(await state(page), ['so', '?customer=1&month=2026-08']);
  await page.locator('#thang-2026-08 .month-body').waitFor();
  assert.equal(world.requests.length, 0);
}, debtor));

test('Việc chờ không tính vào nợ; mở thẻ Sổ để xử lý', async () => withPage(async ({ page, world }) => {
  await ready(page);
  assert.equal(await page.locator('.ov-pending').innerText(), '+3 việc cần xem');
  assert.equal(await page.locator('.ov-total').innerText(), '491.000.000 đ');
  await page.locator('.ov-pending').click();
  assert.deepEqual(await state(page), ['so', '?customer=1']);
  assert.equal(world.requests.length, 0);
}, debtor));
const actions = page => page.locator('.ov-next-actions button').evaluateAll(nodes => nodes.map(node => [node.innerText, node.classList.contains('primary')]));
test('Nhắc nợ ngay: nút chính Copy tin nhắc nợ (lệnh của thẻ Trao đổi) và Xem Trao đổi', async () => withPage(async ({ page, world }) => {
  await ready(page);
  await page.locator('.ov-next-main strong', { hasText: 'Nhắc nợ ngay' }).waitFor();
  assert.deepEqual(await actions(page), [['Copy tin nhắc nợ', true], ['Xem Trao đổi', false]]);
  assert.equal(world.requests.length, 0);
  await page.locator('.ov-copy').click();
  await page.locator('#the-trao-doi .ct-note', { hasText: 'đã nhắc' }).waitFor();
  assert.equal(world.reminderLog.length, 1, 'Copy tin nhắc nợ dùng lệnh của thẻ Trao đổi');
}, debtor));

test('Không có nợ quá hạn: không nút nhắc, chỉ Xem Trao đổi', async () => withPage(async ({ page }) => {
  await page.locator('.ov-next-main strong', { hasText: 'Chưa cần làm gì' }).waitFor();
  assert.deepEqual(await actions(page), [['Xem Trao đổi', false]]);
}, world => {
  debtor(world);
  Object.assign(world.debt.customers[0], { overdue_vnd: '0', long_overdue_vnd: '0', tiers_vnd: [M(50), M(200), '0', '0', '0'], risk: 'ok' });
}));

test('Hứa trả đang chờ hiện việc tiếp theo, không ghi tiền', async () => withPage(async ({ page, world }) => {
  await page.locator('.ov-next-main strong', { hasText: 'Chờ hứa trả' }).waitFor();
  assert.deepEqual(await actions(page), [['Vẫn nhắc nợ', false], ['Xem Trao đổi', false]], 'chờ hứa trả: Vẫn nhắc nợ là nút phụ');
  assert.match(await page.locator('.ov-next').innerText(), /44.400.000 đ · hẹn 20\/11\/2026/);
  await page.locator('.ov-next-actions .tab-go').first().click();
  assert.equal((await state(page))[0], 'trao-doi');
  assert.equal(world.requests.length, 0);
  await page.locator('#tab-tinh-hinh').click();
  await page.locator('.ov-copy').click();
  await page.locator('#the-trao-doi .ct-note', { hasText: 'đã nhắc' }).waitFor();
  assert.equal(world.reminderLog.length, 1, 'Vẫn nhắc nợ dùng lệnh của thẻ Trao đổi');
}, world => {
  debtor(world);
  world.marks = [{ id: 1, kind: 'promise', amount_vnd: '44400000', on_date: '2026-11-20',
    created_on: '2026-10-30', status: 'pending' }];
}));

test('Thiếu opening giữ trạng thái chưa biết; khách trả trước không hiện quá hạn', async () => {
  const base = { clock: TODAY + 'T10:00:00+07:00', todayMonth: '2026-11-01', month: null, query: '&the=tinh-hinh' };
  await withPage(async ({ page, world }) => {
    assert.match(await page.locator('#the-tinh-hinh').innerText(), /^Khách chưa có số dư đầu hiệu lực/);
    assert.deepEqual(world.sideReads ?? [], []);
  }, world => Object.assign(world, base, { status: 'NO_BASELINE', total: null, months: [] }));
  await withPage(async ({ page }) => {
    await page.locator('.ov-total').waitFor();
    assert.equal(await page.locator('.ov-total').innerText(), '50.000.000 đ');
    assert.equal(await page.locator('.ov-parts').innerText(), 'Khách trả trước');
    assert.equal(await page.locator('.ov-risk').count(), 0);
  }, world => Object.assign(world, base, { total: '-50000000', months: [
    { month: '2026-10-01', charges_vnd: M(100), received_vnd: M(150), end_of_month_vnd: '-50000000', outstanding_vnd: '0' },
    { month: '2026-11-01', charges_vnd: '0', received_vnd: '0', end_of_month_vnd: '-50000000', outstanding_vnd: '-50000000' }] }));
});

test('Lỗi Tổng quan không đổi số sổ; thử lại đọc được cơ cấu nợ', async () => withPage(async ({ page }) => {
  await ready(page);
  await page.route(/\/api\/v7\/dashboard\/debt$/, route => route.abort(), { times: 1 });
  await page.reload();
  const error = page.locator('.ov-error');
  await error.waitFor();
  assert.equal(await page.locator('.ov-total').innerText(), '491.000.000 đ');
  assert.match(await error.innerText(), /Không tải được số quá hạn/);
  await error.locator('button').click();
  await page.locator('.ov-part-link').first().waitFor();
}, debtor));

test('Không đọc được hứa trả thì không tự quyết định nhắc nợ', async () => withPage(async ({ page }) => {
  await ready(page);
  await page.route(/\/api\/v7\/marks\?/, route => route.abort(), { times: 1 });
  await page.reload();
  const error = page.locator('.ov-next .ov-error');
  await error.waitFor();
  assert.equal(await page.locator('.ov-next-main strong').innerText(), 'Chưa xác định việc tiếp theo');
  assert.match(await error.innerText(), /Không tải được hứa trả/);
  await error.locator('button').click();
  await page.locator('.ov-next-main strong', { hasText: 'Nhắc nợ ngay' }).waitFor();
}, debtor));

test('Tình hình trên màn hẹp không cuộn ngang', async () => withPage(async ({ page }) => {
  await ready(page);
  await page.setViewportSize({ width: 390, height: 720 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0);
  assert.equal(await page.locator('.ov-total').isVisible(), true);
  assert.equal(await page.locator('.ov-activity').isVisible(), true);
}, debtor));

test('Đổi khách trên Tình hình mở ô tìm khách', async () => withPage(async ({ page }) => {
  await ready(page);
  await page.locator('.customer-switch').click();
  assert.equal(await page.locator('#customer-picker').evaluate(node => node.matches(':popover-open')), true);
  assert.equal(await page.locator('#customer-search').isVisible(), true);
}, debtor));
