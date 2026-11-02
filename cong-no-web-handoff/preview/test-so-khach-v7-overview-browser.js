/* Trình duyệt (Playwright) cho thẻ Tình hình của trang khách (TRANG-KHACH-01, specs/v7-trang-khach.md, PR A2): bốn số và mức
 * rủi ro bằng đúng sổ và Tổng quan, hình 12 tháng bằng months[] và bấm tháng sang thẻ Sổ, số chuyến 6 tháng, việc chờ mở thẻ Sổ
 * với loc=, khách chưa có số dư đầu, khách dư, Tổng quan và lần nhắc đọc lỗi. Máy chủ giả, dữ liệu giả, 1280×720, đồng hồ trang
 * ghim 15/11/2026 (giờ VN); không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage, viewMonth } = require('./so-khach-v7-browser-world');

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

const cards = page => page.locator('#the-tinh-hinh .ov-card').evaluateAll(nodes => nodes.map(node =>
  ['.ov-label', '.ov-value', '.ov-sub'].map(selector => node.querySelector(selector)?.innerText ?? null)));
const state = page => page.evaluate(() => [document.body.dataset.the, location.search]);
const ready = page => page.locator('#the-tinh-hinh .ov-risk').waitFor();

test('Bốn số bằng đúng sổ và Tổng quan, mức rủi ro kèm dữ kiện, lần nhắc gần nhất; bấm Quá hạn sang thẻ Sổ ở tháng quá hạn lâu nhất', async () => withPage(async ({ page, world, shot }) => {
  await ready(page);
  await shot('tinh-hinh');
  // Còn nợ = total_outstanding_vnd (đầu trang); Quá hạn = overdue_vnd của khách ở Tổng quan; Thu tháng này = received_vnd của today_month.
  assert.deepEqual(await cards(page), [
    ['Còn nợ', '491.000.000 đ', '5 tháng còn nợ: T7 → T11'],
    ['Quá hạn', '241.000.000 đ', 'T7, T8, T9 · lâu nhất 76 ngày'],
    ['Đến hạn 30/11', '200.000.000 đ', 'nợ T10 · kế tiếp 50 triệu hạn 31/12'],
    ['Thu tháng 11', '30.000.000 đ', 'phát sinh tháng 11: 50.000.000 đ']]);
  assert.equal(await page.locator('.book-head .head-item.total strong').textContent(), '491.000.000 đ');
  assert.deepEqual(await page.locator('#the-tinh-hinh .ov-facts span').allInnerTexts(),
    ['Rủi ro cao', 'Trả gần nhất 05/11/2026 · 10 ngày trước', 'Đi hàng gần nhất 12/11/2026 · 3 ngày trước']);
  assert.equal(await page.locator('#the-tinh-hinh .ov-talk').innerText(), 'Nhắc gần nhất 10/11/2026 · bấm Copy tin nhắc · đã nhắc 3 lần');
  assert.deepEqual(await page.locator('#the-tinh-hinh .ov-block h2').allInnerTexts(), ['Khách đang nợ mình bao nhiêu', 'Nợ đang tăng hay giảm?',
    'Khách còn đi hàng không?', 'Còn gì làm số chưa đúng?', 'Lần cuối nói chuyện với khách']);
  // 1280×720: không cuộn ngang; mọi nút của thẻ cao ≥ 40px, rộng ≥ 40px, nhãn đọc màn hình bắt đầu bằng chữ trên nút; chữ thân 16px.
  const layout = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    small: [...document.querySelectorAll('#the-tinh-hinh button')].map(node => [node.textContent, node.getBoundingClientRect()])
      .filter(([, box]) => box.height < 40 || box.width < 40).map(([text, box]) => `${text} ${box.width}×${box.height}`),
    named: [...document.querySelectorAll('#the-tinh-hinh button[aria-label]')].filter(node => !node.ariaLabel.startsWith(node.textContent))
      .map(node => node.textContent),
    font: getComputedStyle(document.querySelector('#the-tinh-hinh')).fontSize }));
  assert.deepEqual(layout, { overflow: 0, small: [], named: [], font: '16px' });
  assert.deepEqual([...new Set(world.sideReads)].sort(), ['/api/v7/dashboard/debt', '/api/v7/reminders']);
  await page.locator('#the-tinh-hinh .ov-link').click();
  assert.deepEqual(await state(page), ['so', '?customer=1&month=2026-07']);
  await page.locator('#thang-2026-07 .month-body').waitFor();
}, debtor));

test('Hình 12 tháng: cột và điểm bằng months[], tháng thiếu không có cột; bấm tháng sang thẻ Sổ với month= đúng, không tải lại', async () => withPage(async ({ page, world }) => {
  await ready(page);
  const drawn = await page.evaluate(() => {
    const read = selector => Object.fromEntries([...document.querySelectorAll(`#the-tinh-hinh ${selector}`)].map(node => [node.dataset.month, node.dataset.vnd]));
    return { ps: read('.ov-bar.ps'), thu: read('.ov-bar.thu'), end: read('.ov-point'),
      names: [...document.querySelector('#the-tinh-hinh .ov-months').children].map(node => [node.textContent, node.dataset.go ?? null]),
      labels: [...document.querySelectorAll('#the-tinh-hinh .ov-num[data-month]')].map(node => [node.dataset.month, node.textContent]) };
  });
  const shown = MONTHS.filter(row => row.month >= '2025-12-01').map(row => [row.month.slice(0, 7), row]);
  assert.deepEqual(drawn.ps, Object.fromEntries(shown.map(([key, row]) => [key, row.charges_vnd])));
  assert.deepEqual(drawn.thu, Object.fromEntries(shown.map(([key, row]) => [key, row.received_vnd])));
  assert.deepEqual(drawn.end, Object.fromEntries(shown.map(([key, row]) => [key, row.end_of_month_vnd])));
  assert.equal(drawn.ps['2026-05'], undefined, 'tháng không có trong months[] không có cột');
  assert.deepEqual(drawn.names.map(([text]) => text), ['T12/2025', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11']);
  assert.deepEqual(drawn.names.filter(([, go]) => !go).map(([text]) => text), ['T5']);
  assert.deepEqual(drawn.labels, [['2026-01', '60 triệu'], ['2026-11', '491 triệu']], 'số ở điểm thấp nhất và điểm cuối');
  const reads = world.reads;
  await page.locator('#the-tinh-hinh .ov-month[data-go="thang:2026-08"]').first().click();   // hàng tên tháng của hình 12 tháng (khối 2)
  assert.deepEqual(await state(page), ['so', '?customer=1&month=2026-08']);
  await page.locator('#thang-2026-08 .month-body').waitFor();
  const top = await page.locator('#thang-2026-08').evaluate(node => node.getBoundingClientRect().top);
  assert.ok(top > 0 && top < 360, `tháng 8 ở đầu vùng xem (${top}px)`);
  // Bấm thẳng vào cột tháng trên hình cũng vậy.
  await page.locator('#tab-tinh-hinh').click();
  assert.deepEqual(await state(page), ['tinh-hinh', '?customer=1&the=tinh-hinh']);
  await page.locator('#the-tinh-hinh .ov-col[data-go="thang:2026-07"] .ov-hit').first().click({ position: { x: 4, y: 4 } });
  assert.deepEqual(await state(page), ['so', '?customer=1&month=2026-07']);
  await page.locator('#thang-2026-07 .month-body').waitFor();
  assert.equal(world.reads, reads, 'đổi thẻ, mở tháng không đọc lại sổ');
}, debtor));

test('Đi hàng: số chuyến tháng bằng dòng chuyến web và sổ gốc, đã loại và phí lẻ không đếm; thẻ chỉ đọc Tổng quan khi mở', async () => withPage(async ({ page, world }) => {
  // Mở thẻ Sổ trước: chưa đọc Tổng quan hay lần nhắc. Đếm dòng chuyến của từng tháng trên sổ (bỏ dòng đã loại và phí lẻ không STT)
  // để so; sổ hiện mỗi tháng một màn (SO-GON-05) nên bấm chip từng tháng.
  assert.deepEqual(world.sideReads ?? [], []);
  const rowsOf = key => page.locator(`#thang-${key} .trip-list tr[data-row]`).evaluateAll(rows => rows.filter(row =>
    !row.querySelector('.trip-rejected') && row.cells[0].innerText.trim() !== '–').length);
  const shown = {};
  for (const key of ['2026-07', '2026-08', '2026-09', '2026-11']) {
    await viewMonth(page, key);
    shown[key] = await rowsOf(key);
  }
  await page.locator('#tab-tinh-hinh').click();
  await ready(page);
  assert.deepEqual([...new Set(world.sideReads)].sort(), ['/api/v7/dashboard/debt', '/api/v7/reminders']);
  const counts = Object.fromEntries(await page.locator('#the-tinh-hinh .ov-bar.trip').evaluateAll(nodes => nodes.map(node => [node.dataset.month, Number(node.dataset.count)])));
  assert.deepEqual(counts, { '2026-06': 0, '2026-07': 2, '2026-08': 1, '2026-09': 3, '2026-10': 3, '2026-11': 2 });
  // Tháng 11: 4 dòng chuyến web, bỏ dòng đã loại và dòng phí lẻ (không có STT) còn 2.
  for (const key of ['2026-07', '2026-08', '2026-09', '2026-11']) assert.equal(counts[key], shown[key], `tháng ${key}`);
  assert.equal(await page.locator('#the-tinh-hinh .ov-note').nth(1).innerText(), 'Số chuyến mỗi tháng · đi hàng gần nhất 12/11/2026');
}, world => { debtor(world); world.query = ''; }));

test('Còn gì làm số chưa đúng: số đếm khớp chip tháng; mỗi dòng mở thẻ Sổ với loc= đúng hoặc tới nút của lô, không tải lại', async () => withPage(async ({ page, world }) => {
  await ready(page);
  assert.deepEqual(await page.locator('#the-tinh-hinh .ov-task span').allInnerTexts(),
    ['1 chuyến chưa có giá', '1 chuyến chờ kiểm', '1 chuyến từ Sheet cần xem', 'Giá từ Sheet: 1 chờ ghi']);
  assert.equal(await page.locator('#the-tinh-hinh .ov-task + .ov-note').innerText(), 'Còn nợ ở trên chưa tính các dòng này.');
  const chips = (await page.locator('.month-chip .chip-work').allInnerTexts()).reduce((sum, text) => sum + Number(text), 0);
  assert.deepEqual([chips, await page.locator('#tab-so .tab-work').innerText()], [3, '3']);
  const reads = world.reads;
  const task = text => page.locator('#the-tinh-hinh .ov-task', { hasText: text }).locator('button');
  await task('chưa có giá').click();
  assert.deepEqual(await state(page), ['so', '?customer=1&loc=thieu-gia']);
  assert.match(await page.locator('.loc-bar').innerText(), /^1 chuyến thiếu đơn giá được tô vàng trong sổ\./);
  assert.equal(await page.locator('tr.loc-hit[data-row="trip-41"]').count(), 1);
  await page.locator('#tab-tinh-hinh').click();
  assert.deepEqual(await state(page), ['tinh-hinh', '?customer=1&the=tinh-hinh']);
  await task('chờ kiểm').click();
  assert.deepEqual(await state(page), ['so', '?customer=1&loc=cho-kiem']);
  assert.match(await page.locator('.loc-bar').innerText(), /^1 chuyến chờ kiểm được tô vàng/);
  assert.equal(await page.locator('tr.loc-hit[data-row="trip-42"]').count(), 1);
  for (const [text, button] of [['chuyến từ Sheet', 'sheet-approve'], ['Giá từ Sheet', 'price-approve']]) {
    await page.locator('#tab-tinh-hinh').click();
    await task(text).click();
    assert.deepEqual([(await state(page))[0], await page.evaluate(() => document.activeElement.className)], ['so', button], text);
  }
  assert.deepEqual([world.reads, world.requests.length], [reads, 0], 'không đọc lại sổ, không gửi lệnh');
}, debtor));

test('Khách chưa có số dư đầu: một câu thay số, không đọc Tổng quan; khách đang dư: "Khách đang dư …", không có quá hạn', async () => {
  const base = { clock: `${TODAY}T10:00:00+07:00`, todayMonth: '2026-11-01', month: null, query: '&the=tinh-hinh' };
  await withPage(async ({ page, world }) => {
    assert.match(await page.locator('#the-tinh-hinh').innerText(), /^Khách chưa có số dư đầu hiệu lực\. Chưa có số để xem\.\s+Mở thẻ Sổ$/);
    assert.deepEqual(world.sideReads ?? [], []);
    await page.locator('#the-tinh-hinh .tab-go').click();
    assert.deepEqual(await state(page), ['so', '?customer=1']);
  }, world => Object.assign(world, base, { status: 'NO_BASELINE', total: null, months: [] }));
  await withPage(async ({ page }) => {
    await page.locator('#the-tinh-hinh .ov-talk').filter({ hasText: 'Chưa nhắc lần nào.' }).waitFor();
    assert.deepEqual(await cards(page), [['Khách đang dư', '50.000.000 đ', 'trả trước'], ['Thu tháng 11', '0 đ', 'phát sinh tháng 11: 0 đ']]);
    assert.doesNotMatch(await page.locator('#the-tinh-hinh').innerText(), /[Qq]uá hạn/);
    assert.equal(await page.locator('#the-tinh-hinh .ov-risk').count(), 0);
  }, world => Object.assign(world, base, { total: '-50000000', months: [
    { month: '2026-10-01', charges_vnd: M(100), received_vnd: M(150), end_of_month_vnd: '-50000000', outstanding_vnd: '0' },
    { month: '2026-11-01', charges_vnd: '0', received_vnd: '0', end_of_month_vnd: '-50000000', outstanding_vnd: '-50000000' }] }));
});

test('Tổng quan đọc lỗi: Còn nợ vẫn từ sổ, phần quá hạn báo lỗi kèm Thử lại, khối khác vẫn hiện; lần nhắc lỗi chỉ khối đó báo', async () => withPage(async ({ page }) => {
  await ready(page);
  await page.route(/\/api\/v7\/dashboard\/debt$/, route => route.abort(), { times: 1 });
  await page.reload();
  const error = page.locator('#the-tinh-hinh .ov-error');
  await error.waitFor();
  assert.equal(await error.locator('span').innerText(), 'Không tải được số quá hạn. Kiểm tra mạng rồi bấm Thử lại.');
  assert.deepEqual((await cards(page)).filter(([label]) => label).map(([label, value]) => [label, value]),
    [['Còn nợ', '491.000.000 đ'], ['Thu tháng 11', '30.000.000 đ']]);
  assert.equal(await page.locator('#the-tinh-hinh .ov-risk').count(), 0);
  assert.equal(await page.locator('#the-tinh-hinh .ov-block').count(), 5, 'các khối khác vẫn hiện');
  assert.equal(await page.locator('#the-tinh-hinh .ov-bar.ps').count(), 11);
  assert.equal(await page.locator('#the-tinh-hinh .ov-talk').innerText(), 'Nhắc gần nhất 10/11/2026 · bấm Copy tin nhắc · đã nhắc 3 lần');
  await error.locator('button').click();
  await ready(page);
  assert.deepEqual((await cards(page))[1].slice(0, 2), ['Quá hạn', '241.000.000 đ']);
  await page.route(/\/api\/v7\/reminders$/, route => route.abort(), { times: 1 });
  await page.reload();
  const talk = page.locator('#the-tinh-hinh .ov-talk[role="alert"]');
  await talk.waitFor();
  assert.equal(await talk.innerText(), 'Không tải được lần nhắc nợ. Kiểm tra mạng rồi bấm Thử lại. Thử lại');
  await ready(page);
  assert.deepEqual((await cards(page))[1].slice(0, 2), ['Quá hạn', '241.000.000 đ'], 'lần nhắc lỗi không kéo khối 1 theo');
  await talk.locator('button').click();
  await page.locator('#the-tinh-hinh .ov-talk:not([role])').filter({ hasText: 'đã nhắc 3 lần' }).waitFor();
}, debtor));
