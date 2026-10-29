/* Trình duyệt (Playwright) cho đối chiếu Sheet, ghi giá từ Sheet và Làm mới trên sổ khách V7. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { clock, withPage, posts } = require('./so-khach-v7-browser-world');
test('chuyến mới hiện vàng; dòng khác hiện đỏ; duyệt lô giữ giá trống ngoài công nợ', async () => withPage(async ({ page, world, shot }) => {
  assert.equal(await page.locator('tr.sheet-new').count(), 1);
  assert.equal(await page.locator('[data-row="legacy-21"].sheet-conflict').count(), 1);
  await page.locator('[data-row="legacy-21"] .sheet-diff').click();
  assert.match(await page.locator('.sheet-detail').innerText(), /Xe 2/);
  assert.match(await page.locator('.sheet-detail').innerText(), /Web: Xe 1/);
  assert.match(await page.locator('.sheet-detail').innerText(), /Giữ web/);
  assert.match(await page.locator('.sheet-detail').innerText(), /Lấy Sheet/);
  await shot('doi-chieu-sheet');
  await page.locator('.sheet-choice-actions button[data-sheet-decision="use_sheet"]').first().click();
  await page.waitForFunction(() => document.querySelector('.sheet-detail')?.textContent.includes('Điểm đi'));
  assert.equal(await page.locator('.sheet-detail').count(), 1);
  assert.equal(await page.locator('[data-row="legacy-21"] .sheet-diff').innerText(), 'Đóng');
  await page.locator('[data-row="legacy-21"] .sheet-diff').click();
  assert.equal(await page.locator('.sheet-detail').count(), 0);
  assert.equal(await page.locator('[data-row="legacy-21"] .sheet-diff').innerText(), 'Xem');
  await page.locator('[data-row="legacy-21"] .sheet-diff').click();
  await page.locator('.sheet-detail [data-sheet-decision="keep_web"]').click();
  await page.waitForFunction(() => !document.querySelector('[data-row="legacy-21"].sheet-conflict'));
  assert.equal(world.requests.at(-1).path, '/api/v7/sheet/resolve');
  assert.equal(world.requests.at(-1).body.field, 'origin');
  assert.equal(world.requests.at(-1).body.source_row, 8);
  assert.equal(world.requests.at(-1).body.target_id, 21);
  assert.equal(world.requests.at(-1).body.decision, 'keep_web');
  assert.equal(await page.locator('.info-input').count(), 0);
  assert.match(await page.locator('.sheet-approve').innerText(), /Duyệt 1 chuyến mới/);
  await page.locator('.sheet-approve').click();
  await page.waitForFunction(() => !document.querySelector('.sheet-approve'));
  assert.equal(world.requests.at(-1).path, '/api/v7/sheet/approve');
  assert.equal(world.requests.at(-1).body.snapshot_sha256, 'a'.repeat(64));
  assert.equal(world.trips.at(-1).unit_price_vnd, null);
  assert.equal(await page.locator('td[data-trip="200"][data-field="unit_price_vnd"]').innerText(), '');
  assert.equal(await page.locator('.book-head .head-item.total strong').innerText(), '0');
}, world => {
  world.sheetSync = { snapshot_sha256: 'a'.repeat(64), new_count: 1, conflict_count: 1, items: [
    { sync_state: 'NEW', event_date: clock, container: 'NEWU1234567', carrier: 'WH', origin: 'A', destination: 'B' },
    { sync_state: 'CONFLICT', source_row: 8, event_date: '2026-09-02', container: 'OLDU0000001', carrier: 'WH', shipper: 'Xe 2', origin: 'Nơi C',
      destination: 'Nơi D', existing_kind: 'legacy', existing_id: 21, changed_fields: ['shipper', 'origin'], existing_values: { shipper: 'Xe 1', origin: 'Nơi Cũ' } },
  ] };
}));

const dateBookingConflict = world => {
  world.trips[0].booking = 'BK-OLD';
  world.sheetSync = { snapshot_sha256: 'a'.repeat(64), new_count: 0, conflict_count: 1, items: [
    { sync_state: 'CONFLICT', source_row: 9, event_date: '2026-09-20', container: 'DEMU1234567', carrier: 'Tàu thử', origin: 'Nơi A',
      destination: 'Nơi B', booking: 'BK-NEW', existing_kind: 'trip', existing_id: 11, changed_fields: ['event_date', 'booking'],
      existing_values: { event_date: '2026-09-15', booking: 'BK-OLD' } },
  ] };
};

test('lệch ngày/booking: booking chỉ giữ bản đã ghi; Lấy Sheet đổi ngày qua ô ngày', async () => withPage(async ({ page, world }) => {
  await page.locator('[data-row="trip-11"] .sheet-diff').click();
  const detail = page.locator('.sheet-detail');
  assert.match(await detail.innerText(), /Web: 15\/09\/2026/);
  assert.match(await detail.innerText(), /Sheet: BK-NEW/);
  assert.equal(await detail.locator('[data-sheet-field="booking"][data-sheet-decision="use_sheet"]').count(), 0);
  await detail.locator('[data-sheet-field="booking"][data-sheet-decision="keep_web"]').click();
  await page.waitForFunction(() => document.querySelector('.sheet-detail [data-sheet-field="event_date"]')
    && !document.querySelector('.sheet-detail [data-sheet-field="booking"]'));
  const resolved = world.requests.at(-1);
  assert.equal(resolved.path, '/api/v7/sheet/resolve');
  assert.deepEqual([resolved.body.field, resolved.body.decision, resolved.body.target_kind, resolved.body.target_id], ['booking', 'keep_web', 'trip', 11]);
  await page.locator('.sheet-detail [data-sheet-field="event_date"][data-sheet-decision="use_sheet"]').click();
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="trip"][data-id="11"][data-field="event_date"]')?.textContent.includes('20/09/2026'));
  const [route, body] = posts(world).at(-1);
  assert.equal(route, '/api/v7/trips/info');
  assert.equal(body.field, 'event_date');
  assert.equal(body.trip_id, 11);
  assert.equal(world.requests.filter(item => item.path === '/api/v7/sheet/resolve' && item.body.field === 'event_date').length, 0);
}, dateBookingConflict));

test('lệch ngày ở tháng khóa: Lấy Sheet không gửi lệnh, báo mở khóa', async () => withPage(async ({ page, world }) => {
  await page.locator('[data-row="trip-11"] .sheet-diff').click();
  await page.locator('.sheet-detail [data-sheet-field="event_date"][data-sheet-decision="use_sheet"]').click();
  assert.match(await page.locator('.live-notice').innerText(), /Mở khóa tháng/);
  assert.equal(world.requests.length, 0);
}, world => { dateBookingConflict(world); world.locks = [{ month: '2026-09-01', locked: true }]; world.trips[0].editable = false; world.trips[0].info_editable = false; }));

test('lệch shipper ở tháng khóa: Lấy Sheet báo ngay trong khung, Giữ web vẫn gửi', async () => withPage(async ({ page, world }) => {
  await page.locator('[data-row="trip-11"] .sheet-diff').click();
  await page.locator('.sheet-detail [data-sheet-field="shipper"][data-sheet-decision="use_sheet"]').click();
  assert.match(await page.locator('.sheet-detail .sheet-detail-status').innerText(), /Mở khóa tháng/);
  assert.equal(world.requests.length, 0);
  await page.locator('.sheet-detail [data-sheet-field="shipper"][data-sheet-decision="keep_web"]').click();
  await page.waitForFunction(() => !document.querySelector('[data-row="trip-11"].sheet-conflict'));
  assert.deepEqual([world.requests.at(-1).path, world.requests.at(-1).body.decision], ['/api/v7/sheet/resolve', 'keep_web']);
}, world => {
  world.locks = [{ month: '2026-09-01', locked: true }]; world.trips[0].editable = false; world.trips[0].info_editable = false;
  world.sheetSync = { snapshot_sha256: 'a'.repeat(64), new_count: 0, conflict_count: 1, items: [
    { sync_state: 'CONFLICT', source_row: 9, event_date: '2026-09-15', container: 'DEMU1234567', carrier: 'Tàu thử', shipper: 'Xe Sheet',
      origin: 'Nơi A', destination: 'Nơi B', existing_kind: 'trip', existing_id: 11, changed_fields: ['shipper'], existing_values: { shipper: null } },
  ] };
}));
// ---- Ghi giá từ Sheet (specs/v7-price-queue.md, mockup ghi-gia-tu-sheet đã duyệt 27/10/2026) ----
const priceItem = (kind, id, price, fee, extra = {}) => ({ target_kind: kind, target_id: id, sheet_unit_price_vnd: price,
  sheet_other_fee_vnd: fee, web_unit_price_vnd: null, web_other_fee_vnd: null, status: 'READY', container: 'FAKEU0000000',
  date: '2026-09-16', source_tab: 'Khách Thử Sửa', source_row: 40, ...extra });
const withPrices = world => {
  world.trips.push({ ...world.trips[0], id: 12, container: 'DEMU7654321', event_date: '2026-09-16', unit_price_vnd: null,
    other_fee_vnd: null, amount_vnd: null, is_missing_price: true });
  world.sheetPrices = { snapshot_sha256: 'c'.repeat(64), ready: [priceItem('trip', 12, '12500000', '300000'),
    priceItem('legacy', 21, '13000000', null)], review: [], ready_count: 2, review_count: 0 };
};

test('Ghi giá từ Sheet: dòng vàng chưa tính, khung xác nhận có số tăng, ghi một lệnh cho cả lô', async () => withPage(async ({ page, world, shot }) => {
  const button = page.locator('.price-approve');
  assert.equal(await button.innerText(), 'Ghi 2 giá từ Sheet');
  assert.equal(await page.locator('tr.from-sheet').count(), 2);
  const tripRow = page.locator('[data-row="trip-12"]');
  assert.match(await tripRow.locator('[data-field="unit_price_vnd"]').innerText(), /12\.500\.000\s*giá Sheet/);
  assert.match(await tripRow.innerText(), /12\.800\.000\s*chưa tính/);
  assert.equal(await page.locator('.book-head .head-item.total strong').innerText(), '0');
  await shot('gia-sheet-1-cho-ghi');
  await button.click();
  const confirm = page.locator('.price-panel.confirm');
  assert.match(await confirm.innerText(), /Ghi giá Sheet cho 2 chuyến tháng 9\/2026\?/);
  assert.match(await confirm.innerText(), /tăng 25\.800\.000 đ/);
  assert.equal(await page.evaluate(() => document.activeElement.className), 'price-write primary');
  await shot('gia-sheet-2-xac-nhan');
  await page.locator('.price-cancel').click();
  assert.equal(await page.locator('.price-panel').count(), 0);
  assert.equal(world.requests.length, 0);
  await button.click();
  await page.locator('.price-write').click();
  await page.waitForFunction(() => !document.querySelector('tr.from-sheet'));
  const [path, body] = posts(world).at(-1);
  assert.equal(path, '/api/v7/sheet/prices');
  assert.deepEqual(Object.keys(body).sort(), ['customer_id', 'expected_version', 'idempotency_key', 'snapshot_sha256']);
  assert.equal(body.snapshot_sha256, 'c'.repeat(64));
  assert.equal(world.requests.length, 1);
  assert.match(await page.locator('.live-notice').innerText(), /Đã ghi 2 giá từ Sheet\./);
  assert.equal(await page.locator('.price-approve').count(), 0);
  assert.equal(await tripRow.locator('[data-field="unit_price_vnd"]').innerText(), '12.500.000');
}, withPrices));

test('Ghi giá từ Sheet: Sheet đổi giữa chừng thì không ghi gì và mời tải lại', async () => withPage(async ({ page, world }) => {
  await page.locator('.price-approve').click();
  await page.locator('.price-write').click();
  const error = page.locator('.price-panel.err');
  await error.waitFor();
  assert.match(await error.innerText(), /Chưa ghi giá nào\. Sheet đã đổi sau khi mở sổ\./);
  assert.equal(await page.locator('tr.from-sheet').count(), 2);
  world.priceStale = false;
  await page.locator('.price-reload').click();
  await page.waitForFunction(() => !document.querySelector('.price-panel'));
}, world => { withPrices(world); world.priceStale = true; }));

test('Giá từ Sheet cần xem: tháng khóa mở khóa, lệch giá lấy Sheet, khớp nhiều chuyến chỉ báo', async () => withPage(async ({ page, world, shot }) => {
  assert.equal(await page.locator('.price-approve').count(), 0);
  assert.match(await page.locator('.price-strip').innerText(), /Giá từ Sheet cần xem:\s*4/);
  await page.locator('.price-review-toggle').click();
  const items = page.locator('.price-panel li');
  assert.equal(await items.count(), 4);
  assert.match(await items.nth(0).innerText(), /Tháng 8\/2026 đang khóa/);
  assert.match(await items.nth(1).innerText(), /Web 50\.000\.000 đ · Sheet 52\.000\.000 đ/);
  assert.match(await items.nth(2).innerText(), /Khớp nhiều chuyến/);
  assert.match(await items.nth(3).innerText(), /số âm/);
  assert.equal(await items.nth(2).locator('button').count(), 0);
  await shot('gia-sheet-3-can-xem');
  await items.nth(1).locator('.price-use-sheet').click();
  await page.waitForFunction(() => document.querySelector('[data-row="trip-11"] [data-field="unit_price_vnd"]')?.textContent.includes('52.000.000'));
  assert.deepEqual(posts(world).at(-1)[1].unit_price_vnd, '52000000');
  assert.equal(posts(world).at(-1)[0], '/api/v7/trips/price');
  // Khung "Cần xem" vẫn mở sau khi ghi một dòng, để xử lý tiếp dòng khác.
  await page.locator('.price-unlock').click();
  for (let i = 0; i < 100 && posts(world).at(-1)[0] !== '/api/v7/months/lock'; i++) await page.waitForTimeout(50);
  const [lockPath, lockBody] = posts(world).at(-1);
  assert.deepEqual([lockPath, lockBody.month, lockBody.locked], ['/api/v7/months/lock', '2026-08-01', false]);
}, world => {
  world.locks.push({ month: '2026-08-01', locked: true });
  world.trips.push({ ...world.trips[0], id: 13, month: '2026-08-01', container: 'DEMU0800001', event_date: '2026-08-20',
    unit_price_vnd: null, amount_vnd: null, is_missing_price: true, editable: false, info_editable: false });
  world.sheetPrices = { snapshot_sha256: 'd'.repeat(64), ready: [], ready_count: 0, review_count: 4, review: [
    priceItem('trip', 13, '11000000', null, { status: 'MONTH_LOCKED', container: 'DEMU0800001', date: '2026-08-20' }),
    priceItem('trip', 11, '52000000', null, { status: 'CONFLICT', web_unit_price_vnd: '50000000', container: 'DEMU1234567' }),
    priceItem('', '', '12500000', null, { status: 'AMBIGUOUS', container: 'DEMU0000009' }),
    priceItem('trip', 11, '50000000', '-500000', { status: 'MANUAL' })] };
}));

test('Làm mới đọc Sheet ngay: đang lấy → xong thì tải lại sổ; đang nhập thì không gửi; lỗi báo chưa lấy được', async () => withPage(async ({ page, world, shot }) => {
  const old = '2026-10-28T04:45:00Z', fresh = '2026-10-28T04:52:00Z';
  let state = 'idle';
  world.sheetRefresh = method => {
    if (method === 'POST') state = state === 'broken' ? 'failed' : 'running';
    else if (state === 'running') state = 'done';
    if (state === 'done') return { state: 'idle', sheet_at: fresh, requested_at: old };
    return { state, sheet_at: old, requested_at: state === 'idle' ? null : old };
  };
  await page.locator('#refresh-data').click();   // lần đầu: chưa bật lúc mở trang, giờ bật
  const status = page.locator('#updated-at');
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Đang lấy từ Sheet'));
  assert.equal(await page.locator('#refresh-data').getAttribute('aria-busy'), 'true');
  await shot('lam-moi-dang-lay');
  const reads = world.reads;
  await page.locator('#refresh-data').click();   // bấm lặp khi đang chạy: không gửi thêm
  assert.deepEqual(world.refreshCalls.filter(method => method === 'POST').length, 1);
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Sheet vừa lấy lúc 11:52'), null, { timeout: 15000 });
  assert.ok(world.reads > reads, 'lấy xong thì tải lại sổ');
  assert.equal(await page.locator('#refresh-data').getAttribute('aria-busy'), 'false');
  await shot('lam-moi-xong');
  await page.locator('#refresh-data').click();   // bấm lại ngay sau khi xong: chạy lượt mới
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Đang lấy từ Sheet'));
  assert.equal(world.refreshCalls.filter(method => method === 'POST').length, 2);
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Sheet vừa lấy lúc 11:52'), null, { timeout: 15000 });

  const amount = page.locator('.receipt-amount').first();
  await amount.fill('123');
  const posts = world.refreshCalls.length;
  await page.locator('#refresh-data').click();
  assert.equal(world.refreshCalls.slice(posts).includes('POST'), false);
  await amount.fill('');

  state = 'broken';
  await page.locator('#refresh-data').click();
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Chưa lấy được từ Sheet, đang dùng bản lúc 11:45'));
  assert.equal(await status.evaluate(node => node.classList.contains('sheet-error')), true);
}));
