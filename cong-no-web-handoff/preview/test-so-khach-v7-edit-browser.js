/* Trình duyệt (Playwright) cho sửa/xóa tại ô (NHAP-SHEET-01) trên sổ khách V7. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const shots = process.env.SHOTS_DIR;
const clock = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const todayMonth = `${clock.slice(0, 7)}-01`;
const monthOf = iso => `${iso.slice(0, 7)}-01`;

// Sổ giả: chuyến web và dòng sổ gốc tháng 9 đang mở; mỗi test có thể khóa riêng.
function makeWorld() {
  return {
    version: 1, reads: 0, refreshCalls: [], sheetRefresh: null, sheetSync: { snapshot_sha256: 'a'.repeat(64), new_count: 0, conflict_count: 0, items: [] }, receipts: [], requests: [], failNext: null, locks: [{ month: '2026-09-01', locked: false }], nextEvent: 1, events: [], adjustments: [],
    trips: [{ id: 11, month: '2026-09-01', container: 'DEMU1234567', carrier: 'Tàu thử', event_date: '2026-09-15', origin: 'Nơi A', destination: 'Nơi B',
      unit_price_vnd: '50000000', other_fee_vnd: null, amount_vnd: '50000000', status: 'confirmed', is_missing_price: false, is_fee_only: false,
      editable: true, info_editable: true, deleted: false }],
    legacy: [
      { id: 21, month: '2026-09-01', kind: 'trip', source_total_vnd: null, editable: true,
        display: { row: 5, stt: '1', container: 'OLDU0000001', carrier: 'Xe 1', date: '2026-09-02', from: 'Nơi C', to: 'Nơi D', unit_price: '', fee_vnd: '', flags: ['MISSING_PRICE'] },
        current: { container: 'OLDU0000001', carrier: 'Xe 1', shipper: 'Chủ hàng thử', event_date: '2026-09-02', origin: 'Nơi C', destination: 'Nơi D', unit_price_vnd: null, other_fee_vnd: null, counted_vnd: '0', month: '2026-09-01', deleted: false } },
      { id: 22, month: '2026-09-01', kind: 'trip', source_total_vnd: '93000000', editable: true,
        display: { row: 6, stt: '2', container: 'OLDU0000002', carrier: 'Xe 2', date: '2026-09-03', from: 'Nơi C', to: 'Nơi D', unit_price: '90000000', fee_vnd: '3000000', flags: [] },
        current: { container: 'OLDU0000002', carrier: 'Xe 2', event_date: '2026-09-03', origin: 'Nơi C', destination: 'Nơi D', unit_price_vnd: '90000000', other_fee_vnd: '3000000', counted_vnd: '93000000', month: '2026-09-01', deleted: false } },
    ],
  };
}

function ledger(world) {
  const trips = world.trips.filter(trip => !trip.deleted);
  const legacy = world.legacy.filter(row => !row.current.deleted);
  const keys = [...new Set([...trips, ...legacy].map(row => row.month).concat(todayMonth))].sort();
  return { status: 'active', customer_id: 1, version: world.version, demo: true, today_month: todayMonth,
    month_locks: world.locks,
    months: keys.map(month => ({ month, prior_months_vnd: '0', charges_vnd: '0', received_vnd: '0', end_of_month_vnd: '0', outstanding_vnd: '0' })),
    total_outstanding_vnd: '0', trips, adjustments: world.adjustments, opening: [], source_exceptions: [], receipts: world.receipts, outgoing_offsets: [],
    legacy_rows: legacy.map(row => ({ ...row, month: row.current.month })), events: world.events, sheet_sync: world.sheetSync,
    sheet_prices: world.sheetPrices ?? { ready: [], review: [], ready_count: 0, review_count: 0 } };
}

function apply(world, url, body) {
  const fail = world.failNext;
  if (fail) { world.failNext = null; return [422, fail]; }
  if (body.expected_version !== world.version) return [409, { error: 'STALE_LEDGER' }];
  if (url === '/api/v7/sheet/approve') {
    if (body.snapshot_sha256 !== world.sheetSync.snapshot_sha256) return [409, { error: 'STALE_SHEET' }];
    const row = world.sheetSync.items.find(item => item.sync_state === 'NEW');
    world.trips.push({ id: 200, month: monthOf(row.event_date), container: row.container, carrier: row.carrier,
      event_date: row.event_date, origin: row.origin, destination: row.destination, unit_price_vnd: null,
      other_fee_vnd: null, amount_vnd: null, note: 'Chuyến đồng bộ', status: 'confirmed', is_missing_price: true,
      is_fee_only: false, editable: true, info_editable: true, deleted: false });
    world.sheetSync = { ...world.sheetSync, items: [], new_count: 0, conflict_count: 0 };
    world.version += 1;
    return [200, { approved: 1, remaining: 0, complete: true }];
  }
  if (url === '/api/v7/sheet/prices') {
    if (world.priceStale || body.snapshot_sha256 !== world.sheetPrices.snapshot_sha256) return [409, { error: 'STALE_SHEET', message: 'Sheet đã đổi. Tải lại rồi ghi.' }];
    const written = world.sheetPrices.ready.length;
    for (const item of world.sheetPrices.ready) {
      const row = item.target_kind === 'trip' ? world.trips.find(trip => trip.id === item.target_id)
        : world.legacy.find(line => line.id === item.target_id).current;
      Object.assign(row, { unit_price_vnd: item.sheet_unit_price_vnd, other_fee_vnd: item.sheet_other_fee_vnd, is_missing_price: false });
    }
    world.sheetPrices = { ...world.sheetPrices, ready: [], ready_count: 0 };
    world.version += 1;
    return [200, { written, remaining: 0, complete: true, version: world.version }];
  }
  if (url === '/api/v7/sheet/resolve') {
    const item = world.sheetSync.items.find(row => row.source_row === body.source_row || row.existing_id === body.target_id);
    if (!item || !item.changed_fields.includes(body.field)) return [404, { message: 'Không còn trường lệch.' }];
    item.changed_fields = item.changed_fields.filter(field => field !== body.field);
    if (!item.changed_fields.length) world.sheetSync = { ...world.sheetSync, items: world.sheetSync.items.filter(row => row !== item), conflict_count: Math.max(0, world.sheetSync.conflict_count - 1) };
    world.version += 1;
    return [200, { resolved: true, version: world.version }];
  }
  const event = (kind, before, after) => world.events.unshift({ kind, actor: 'nguoi-thu', at: '2026-10-01T03:00:00Z', before, after });
  if (url === '/api/v7/trips/price') {
    const trip = world.trips.find(row => row.id === body.trip_id);
    Object.assign(trip, { unit_price_vnd: body.unit_price_vnd, other_fee_vnd: body.other_fee_vnd, is_missing_price: false });
    event('price_edit', { price: {} }, { price: {} });
  } else if (url === '/api/v7/months/lock') {
    world.locks = world.locks.map(row => row.month === body.month ? { ...row, locked: body.locked } : row);
  } else if (url === '/api/v7/trips/info') {
    const trip = world.trips.find(row => row.id === body.trip_id && !row.deleted);
    const before = { id: trip.id, field: body.field, value: trip[body.field], debt_month: trip.month, status: trip.status };
    trip[body.field] = body.value;
    if (body.field === 'event_date') trip.month = monthOf(body.value);
    const after = { trip: { ...before, value: body.value, debt_month: trip.month } };
    if (trip.month !== before.debt_month) Object.assign(after, { moved_from_month: before.debt_month, moved_to_month: trip.month });
    event('trip_edit', { trip: before }, after);
  } else if (url === '/api/v7/trips/delete') {
    const trip = world.trips.find(row => row.id === body.trip_id);
    event('trip_delete', { trip: { ...trip } }, { trip: { id: trip.id, deleted: true } });
    trip.deleted = true;
  } else if (url === '/api/v7/legacy/edit' || url === '/api/v7/legacy/delete') {
    const row = world.legacy.find(item => item.id === body.legacy_row_id);
    const old = { ...row.current };
    const next = { ...old };
    if (url.endsWith('delete')) Object.assign(next, { deleted: true, counted_vnd: '0' });
    else {
      next[body.field] = body.value === '' ? null : body.value;
      if (body.field === 'event_date') next.month = monthOf(body.value);
      if (body.field.endsWith('_vnd')) next.counted_vnd = next.unit_price_vnd == null ? '0' : String(BigInt(next.unit_price_vnd) + BigInt(next.other_fee_vnd ?? 0));
    }
    const delta = BigInt(next.counted_vnd) - BigInt(old.counted_vnd);
    if (delta !== 0n) world.adjustments.push({ id: world.adjustments.length + 1, month: old.month, trip_id: null, legacy_row_id: row.id, amount_vnd: delta.toString(), note: null });
    row.current = next;
    event(url.endsWith('delete') ? 'legacy_delete' : 'legacy_edit', { legacy: { ...old, field: body.field, value: old[body.field] } }, { legacy: { ...next, field: body.field, value: next[body.field] } });
  } else if (url === '/api/v7/trips/paste') {
    for (const trip of body.trips) {
      const [d, m, y] = trip.date.split('/');
      world.trips.push({ id: 100 + world.trips.length, month: `${y}-${m}-01`, container: trip.container, carrier: trip.carrier, event_date: `${y}-${m}-${d}`,
        origin: trip.from, destination: trip.to, unit_price_vnd: trip.unitPriceVnd, other_fee_vnd: trip.otherFeeVnd, amount_vnd: trip.unitPriceVnd,
        status: 'confirmed', is_missing_price: trip.unitPriceVnd === null, is_fee_only: false, editable: true, info_editable: true, deleted: false });
    }
    event('paste', {}, { trips: body.trips });
  } else return [404, { error: 'NOT_FOUND' }];
  world.version += 1;
  return [200, { ok: true }];
}

async function withPage(fn, setup = () => {}) {
  const world = makeWorld();
  setup(world);
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const send = (status, body) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (url.pathname === '/api/v7/customers') { send(200, { customers: [{ id: 1, name: 'Khách Thử Sửa', status: 'active' }], demo: true }); return; }
    if (url.pathname === '/api/v7/ledger') { world.reads++; send(200, ledger(world)); return; }
    if (url.pathname === '/api/v7/sheet/refresh') {   // nút Làm mới: mặc định server chưa bật
      world.refreshCalls.push(req.method);
      if (world.sheetRefresh) send(200, world.sheetRefresh(req.method)); else send(404, { error: 'NOT_FOUND' });
      return;
    }
    if (url.pathname.startsWith('/api/')) {
      const chunks = [];
      req.on('data', chunk => chunks.push(chunk));
      req.on('end', () => {
        const body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
        world.requests.push({ path: url.pathname, body });
        send(...apply(world, url.pathname, body));
      });
      return;
    }
    const file = path.join(__dirname, url.pathname.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html; charset=utf-8' : 'text/javascript; charset=utf-8' });
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/so-khach-v7-live.html?customer=1`);
    await page.waitForSelector('.book-head .history-toggle');
    const shot = async name => { if (shots) { fs.mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: true }); } };
    await fn({ page, world, shot });
    assert.deepEqual(errors, []);
  } finally { await browser.close(); server.close(); }
}

const tripCell = (page, field, id = 11) => page.locator(`td.info-edit[data-kind="trip"][data-id="${id}"][data-field="${field}"]`);
const legacyCell = (page, id, field) => page.locator(`td.info-edit[data-kind="legacy"][data-id="${id}"][data-field="${field}"]`);
const posts = world => world.requests.map(item => [item.path, item.body]);

test('Sổ khách làm mới thủ công nhưng giữ dữ liệu đang gõ', async () => withPage(async ({ page, world }) => {
  const amount = page.locator('.receipt-amount').first();
  await amount.fill('123');
  const before = world.reads;
  await page.locator('#refresh-data').click();
  assert.equal(world.reads, before);
  assert.equal(await amount.inputValue(), '123');
  await amount.fill('');
  await page.locator('#refresh-data').click();
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Cập nhật'));
  assert.equal(world.reads, before + 1);
}));

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


test('tháng khóa: cột chuyến chỉ đọc; phiếu thu vẫn nhập được', async () => withPage(async ({ page, world }) => {
  const sept = page.locator('#thang-2026-09');
  assert.equal(await sept.locator('td.info-edit,td.row-delete,td.editable,.draft-input').count(), 0);
  assert.equal(await sept.locator('.add-month-adjustment').isDisabled(), true);
  assert.equal(await sept.locator('.receipt-amount').count(), 1);
  assert.equal(world.requests.length, 0);
}, world => { world.locks = [{ month: '2026-09-01', locked: true }]; world.trips[0].editable = false; world.trips[0].info_editable = false; }));

test('chuyến web tháng mở: sửa ô bằng Enter, Esc trả lại, Tab lưu; ghi Lịch sử trước → sau', async () => withPage(async ({ page, world, shot }) => {
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu đổi');
  await page.keyboard.press('Escape');
  assert.equal(await tripCell(page, 'carrier').innerText(), 'Tàu thử');
  assert.equal(world.requests.length, 0);

  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu đổi');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="trip"][data-field="carrier"]')?.textContent === 'Tàu đổi');
  const sent = world.requests.at(-1);
  assert.equal(sent.path, '/api/v7/trips/info');
  assert.deepEqual({ ...sent.body, idempotency_key: 'k' }, { customer_id: 1, expected_version: 1, idempotency_key: 'k', trip_id: 11, field: 'carrier', value: 'Tàu đổi' });

  await tripCell(page, 'destination').click();
  await page.locator('.info-input').fill('Nơi mới');
  await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="trip"][data-field="destination"]')?.textContent === 'Nơi mới');
  assert.equal(world.requests.length, 2);

  // Bấm vào rồi rời ô không đổi gì: không gửi lệnh.
  await tripCell(page, 'origin').click();
  await page.locator('.book-head .head-item.total').click();
  assert.equal(world.requests.length, 2);

  await page.locator('.history-toggle').click();
  assert.match(await page.locator('#history-panel').innerText(), /Sửa ô chuyến[\s\S]*Chuyến DEMU1234567 · Hãng tàu: Tàu thử → Tàu đổi/);
  await shot('sua-o-chuyen-web');
}));

test('đổi ngày sang tháng khác: hỏi lại trước khi chuyển; Chuyển → dòng vàng ở tháng mới, dòng mờ Hoàn tác ở tháng cũ', async () => withPage(async ({ page, world, shot }) => {
  await tripCell(page, 'event_date').click();
  await page.locator('.info-input').fill('31/02/2026');
  await page.keyboard.press('Enter');
  assert.match(await tripCell(page, 'event_date').locator('.cell-error').innerText(), /dd\/mm\/yyyy/);
  assert.equal(world.requests.length, 0);

  // Ngày thuộc tháng khác: chưa gửi, hỏi lại ngay dưới dòng; Giữ ngày cũ trả lại ô.
  await page.locator('.info-input').fill('5/8/2026');
  await page.keyboard.press('Enter');
  const ask = page.locator('.move-ask');
  assert.match(await ask.innerText(), /Ngày 05\/08\/2026 thuộc tháng 8\/2026\. Chuyển chuyến DEMU1234567 sang tháng 8\/2026\?/);
  assert.equal(world.requests.length, 0);
  await ask.locator('.move-no').click();
  assert.equal(await page.locator('.move-ask').count(), 0);
  assert.equal(await tripCell(page, 'event_date').innerText(), '15/09/2026');
  assert.equal(world.requests.length, 0);

  await tripCell(page, 'event_date').click();
  await page.locator('.info-input').fill('5/8/2026');
  await page.keyboard.press('Enter');
  await page.locator('.move-ask .move-yes').click();
  await page.locator('#thang-2026-08 tr.moved').waitFor();
  assert.equal(world.requests.at(-1).body.value, '2026-08-05');
  assert.equal(await page.locator('#thang-2026-08 td.info-edit[data-field="event_date"]').innerText(), '05/08/2026');
  assert.match(await page.locator('#thang-2026-08 tr.moved .moved-tag').innerText(), /Vừa chuyển từ T9/);
  assert.equal(await page.locator('#thang-2026-09 td.info-edit[data-kind="trip"]').count(), 0);
  assert.match(await page.locator('#thang-2026-09 .ghost').innerText(), /DEMU1234567 \(ngày cũ 15\/09\/2026\) đã chuyển sang tháng 8\/2026/);
  assert.equal(await page.locator('.live-notice').isVisible(), false);
  await shot('chuyen-thang');

  // Hoàn tác: gửi lại ngày cũ, dòng về tháng 9, hết dòng mờ và màu vàng.
  await page.locator('#thang-2026-09 .ghost-undo').click();
  await page.locator('#thang-2026-09 td.info-edit[data-kind="trip"][data-field="event_date"]').waitFor();
  assert.equal(world.requests.at(-1).body.value, '2026-09-15');
  assert.equal(await page.locator('.ghost, tr.moved').count(), 0);
}, world => { world.locks.push({ month: '2026-08-01', locked: false }); }));

test('lỗi server hiện tại ô và giữ ô nhập', async () => withPage(async ({ page, world }) => {
  world.failNext = { error: 'INVALID_TRIP_INPUT', message: 'Thiếu thông tin chuyến.' };
  await tripCell(page, 'container').click();
  await page.locator('.info-input').fill('');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="trip"][data-field="container"] .cell-error')?.textContent === 'Thiếu thông tin chuyến.');
  assert.equal(await page.locator('.info-input').count(), 1);
}));

test('dòng sổ gốc: điền giá dòng thiếu giá, sửa giá; dòng điều chỉnh sổ gốc cộng phần chênh của tháng', async () => withPage(async ({ page, world, shot }) => {
  // 23/10/2026: không còn chú thích "Từ sổ gốc" và dòng chênh; dòng cũ trông và sửa như chuyến web.
  assert.equal(await page.locator('.legacy-caption, .source-total').count(), 0);
  const cells = page.locator('[data-row="legacy-21"] > td');
  assert.equal(await cells.count(), 14);
  assert.equal(await cells.nth(3).innerText(), 'Chủ hàng thử');
  assert.equal(await cells.nth(4).innerText(), '02/09/2026');
  const price = legacyCell(page, 21, 'unit_price_vnd');
  assert.equal(await price.innerText(), 'chưa có giá');
  assert.match(await price.getAttribute('class'), /missing/);
  await price.click();
  assert.equal(await page.locator('.info-input').inputValue(), '');
  await page.locator('.info-input').fill('70.000.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="legacy"][data-id="21"][data-field="unit_price_vnd"]')?.textContent === '70.000.000');
  assert.deepEqual(posts(world).at(-1), ['/api/v7/legacy/edit', { customer_id: 1, expected_version: 1, idempotency_key: world.requests.at(-1).body.idempotency_key,
    legacy_row_id: 21, field: 'unit_price_vnd', value: '70000000' }]);
  assert.equal(await legacyCell(page, 21, 'unit_price_vnd').innerText(), '70.000.000');

  await legacyCell(page, 22, 'unit_price_vnd').click();
  assert.equal(await page.locator('.info-input').inputValue(), '90.000.000');
  await page.locator('.info-input').fill('85.000.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="legacy"][data-id="22"][data-field="unit_price_vnd"]')?.textContent === '85.000.000');
  assert.equal(await page.locator('.legacy-adjustment').count(), 0);

  await page.locator('.history-toggle').click();
  assert.match(await page.locator('#history-panel').innerText(), /Sửa dòng sổ gốc[\s\S]*Dòng sổ gốc OLDU0000002 · Đơn giá: 90\.000\.000 → 85\.000\.000 · Số tính: 93\.000\.000 → 88\.000\.000/);
  await shot('sua-dong-so-goc');
}));

test('bấm STT để xóa hẳn: hỏi xác nhận có ngày và số tiền; Thôi giữ nguyên; Xóa hẳn gửi một lệnh', async () => withPage(async ({ page, world, shot }) => {
  const stt = page.locator('td.row-delete[data-kind="trip"][data-id="11"]');
  await stt.click();
  const prompt = page.locator('.delete-prompt');
  assert.match(await prompt.innerText(), /Xóa hẳn chuyến DEMU1234567 \(15\/09\/2026, thành tiền 50\.000\.000\)\?/);
  await shot('xoa-chuyen-xac-nhan');
  await prompt.locator('.cancel-delete').click();
  assert.equal(await page.locator('.delete-prompt').count(), 0);
  assert.equal(world.requests.length, 0);

  await stt.click();
  await page.locator('.confirm-delete').click();
  await page.waitForFunction(() => !document.querySelector('td.row-delete[data-kind="trip"]'));
  assert.deepEqual(posts(world).map(([url, body]) => [url, body.trip_id]), [['/api/v7/trips/delete', 11]]);

  await page.locator('td.row-delete[data-kind="legacy"][data-id="22"]').click();
  assert.match(await page.locator('.delete-prompt').innerText(), /Xóa hẳn dòng sổ gốc OLDU0000002 \(03\/09\/2026, đang tính 93\.000\.000\)\? Số dư đầu không đổi/);
  await page.locator('.confirm-delete').click();
  await page.waitForFunction(() => !document.querySelector('td.row-delete[data-id="22"]'));
  assert.equal(world.requests.at(-1).path, '/api/v7/legacy/delete');
  assert.equal(await page.locator('.legacy-adjustment').count(), 0);
}));

test('XOA-THU-GOC-01: tháng mở bấm số tiền khoản thu sổ gốc để xóa hẳn; tháng khóa không có nút', async () => withPage(async ({ page, world }) => {
  assert.equal(await page.locator('td.row-delete[data-kind="legacy"][data-id="25"]').count(), 0);
  const amount = page.locator('td.row-delete[data-kind="legacy"][data-id="24"]');
  assert.equal(await amount.innerText(), '1.234.567');
  await amount.click();
  assert.match(await page.locator('.delete-prompt').innerText(), /Xóa hẳn khoản thu sổ gốc 1\.234\.567 \(TTNU0000009\)\? Nợ tăng lại 1\.234\.567/);
  await page.locator('.confirm-delete').click();
  await page.waitForFunction(() => !document.querySelector('td.row-delete[data-id="24"]'));
  assert.deepEqual(posts(world).map(([url, body]) => [url, body.legacy_row_id]), [['/api/v7/legacy/delete', 24]]);
}, world => {
  world.locks = [{ month: '2026-09-01', locked: true }];
  world.legacy.push({ id: 24, month: todayMonth, kind: 'receipt', source_total_vnd: '1234567', editable: false,
    current: { month: todayMonth, deleted: false, counted_vnd: '1234567' }, display: { row: 9, container: 'TTNU0000009', raw_date: '', note: '' } },
  { id: 25, month: '2026-09-01', kind: 'receipt', source_total_vnd: '1000000', editable: false,
    current: { month: '2026-09-01', deleted: false, counted_vnd: '1000000' }, display: { row: 8, raw_date: '', note: '' } });
}));

test('bảng nhập kiểu Sheet: dán hàng từ tab khách vào hàng trống, ô lỗi chặn Lưu, Lưu gửi một lệnh dán lô', async () => withPage(async ({ page, world, shot }) => {
  assert.equal(await page.locator('.paste-input').count(), 0);
  const blank = page.locator(`#thang-${todayMonth.slice(0, 7)} .draft-input[data-draft="0"][data-field="carrier"]`);
  await blank.click();
  const day = `${clock.slice(8)}/${clock.slice(5, 7)}/${clock.slice(0, 4)}`;
  const rows = [['1', 'NEWU0000001', 'Tàu mới', day, 'Nơi A', 'Nơi B', '1,000,000', '', '', '90,000,000', '91,000,000', day, 'ck', '5,000,000'],
    ['2', 'NEWU0000002', 'Tàu mới', day, 'Nơi A', '', '', '', '', '', '0']].map(row => row.join('\t')).join('\n');
  await page.evaluate(text => {
    const data = new DataTransfer();
    data.setData('text/plain', text);
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  }, rows);
  await page.locator('.draft-row.draft').nth(1).waitFor();
  assert.equal(await page.locator('.draft-input[data-draft="0"][data-field="container"]').inputValue(), 'NEWU0000001');
  assert.equal(await page.locator('.draft-input[data-draft="0"][data-field="fee"]').inputValue(), '1.000.000');
  assert.match(await page.locator('.draft-note').innerText(), /Phần tiền khách trả trong vùng dán đã bỏ qua/);
  // Hàng 2 thiếu nơi đến: ô đỏ, nút Lưu tắt; thiếu giá chỉ tô cam, không chặn.
  assert.match(await page.locator('.draft-input[data-draft="1"][data-field="to"]').locator('..').getAttribute('class'), /bad/);
  assert.equal(await page.locator('.draft-save').isDisabled(), true);
  await page.locator('.draft-input[data-draft="1"][data-field="to"]').fill('Nơi C');
  await page.locator('.draft-input[data-draft="1"][data-field="from"]').click();
  await page.waitForFunction(() => !document.querySelector('.draft-save').disabled);
  assert.equal(world.requests.length, 0);
  await shot('bang-nhap-nhap');
  await page.locator('.draft-save').click();
  await page.waitForFunction(() => /Đã lưu 2 chuyến/.test(document.querySelector('.draft-note')?.textContent ?? ''));
  const sent = world.requests.at(-1);
  assert.equal(sent.path, '/api/v7/trips/paste');
  assert.deepEqual(sent.body.trips, [
    { container: 'NEWU0000001', carrier: 'Tàu mới', date: day, from: 'Nơi A', to: 'Nơi B', unitPriceVnd: '90000000', otherFeeVnd: '1000000', note: '', src: '' },
    { container: 'NEWU0000002', carrier: 'Tàu mới', date: day, from: 'Nơi A', to: 'Nơi C', unitPriceVnd: null, otherFeeVnd: null, note: '', src: '' }]);
  assert.equal(await page.locator('.draft-row.draft').count(), 0);
  assert.equal(await page.locator('td.info-edit[data-kind="trip"][data-field="container"]').filter({ hasText: 'NEWU0000002' }).count(), 1);
}, world => { world.locks = [{ month: '2026-09-01', locked: true }]; }));

test('tháng cũ đã mở khóa có hàng nhập phiếu và bảng nhập chuyến riêng; nháp không lẫn tháng, ô thu gõ dở không mất', async () => withPage(async ({ page, world, shot }) => {
  const sept = page.locator('#thang-2026-09');
  const current = page.locator(`#thang-${todayMonth.slice(0, 7)}`);
  await sept.locator('.draft-input[data-field="container"]').first().waitFor();
  for (const selector of ['.receipt-date:not(.saved-receipt-input)', '.receipt-method', '.receipt-amount', '.receipt-reference']) assert.equal(await sept.locator(selector).count(), 1);
  // Gõ nháp ở tháng 9 không làm hiện nháp ở tháng hiện tại.
  const entry = sept.locator('.draft-row').first();
  await entry.locator('.draft-input[data-field="container"]').fill('NEWU7654321');
  await sept.locator('.receipt-amount').fill('1.000.000');
  await entry.locator('.draft-input[data-field="carrier"]').click();
  await page.waitForFunction(() => document.querySelector('#thang-2026-09 .draft-bar strong')?.textContent === '1 chuyến nháp');
  assert.equal(await current.locator('.draft-bar strong').innerText(), '0 chuyến nháp');
  // Bảng nháp vẽ lại không làm mất ô thu đang gõ.
  assert.equal(await sept.locator('.receipt-amount').inputValue(), '1.000.000');
  await shot('nhap-thang-cu-mo-khoa');
  assert.equal(world.requests.length, 0);
}, world => { world.locks = [{ month: '2026-09-01', locked: false }]; }));

test('bàn phím: Enter trên ô mở sửa; 1280×720 không cuộn ngang', async () => withPage(async ({ page }) => {
  await tripCell(page, 'origin').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('.info-input').count(), 1);
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
}));

// Góp ý 23/10/2026: phiếu thu web ở hàng kế tiếp sau phiếu thu cuối cùng của tháng, như trên Sheet.
const webReceipt = (pid, month, date, amount, reference = null) => ({ id: pid, pid, reference, date, method: 'THU TIỀN', amount_vnd: amount, void_reason: null,
  offset_pair_id: null, counterparty_customer_id: null, counterparty_name: null, voided_on: null, voided_by_event: null,
  allocations: [{ month, amount_vnd: amount, kind: 'debt', superseded_by_event: null }] });
// Mỗi hàng dữ liệu của tháng → [ngày trả, hình thức, số tiền, STT/container để nhận hàng].
const payRows = (page, key) => page.evaluate(id => [...document.querySelectorAll(`#thang-${id} tr`)]
  .filter(tr => tr.querySelector('td.pay-start') && !tr.matches('.subtotal,.adjustment,.draft-row,.draft-caption,.draft-bar,.month,.void-trace,.spacer'))
  .map(tr => { const pay = [...tr.querySelectorAll('td.pay')]; const entry = tr.querySelector('.receipt-date');
    return { first: tr.cells[1]?.textContent.trim() ?? '', date: pay[0]?.textContent.trim() ?? '', method: pay[1]?.textContent.trim() ?? '', amount: pay[2]?.firstChild?.textContent?.trim?.() ?? '', entry: Boolean(entry) }; }), key);

test('phiếu web ở hàng kế tiếp: Sheet có phiếu hàng 1 → web hàng 2; nhiều phiếu hơn hàng thì thêm hàng; ô nhập ở hàng kế tiếp; ngày Sheet dd/mm/yyyy', async () => withPage(async ({ page, world, shot }) => {
  world.legacy.push({ id: 23, month: '2026-09-01', kind: 'receipt', source_total_vnd: '1000000', editable: false, current: { month: '2026-09-01', deleted: false },
    display: { row: 5, raw_date: '46032.0', note: '2026-01-10 00:00:00' } });
  world.receipts.push(webReceipt('PH-001', '2026-09-01', '2026-10-01', '2000000', 'REF-A'), webReceipt('PH-002', '2026-09-01', '2026-10-02', '3000000'),
    webReceipt('PH-003', '2026-09-01', '2026-10-03', '4000000'), webReceipt('PH-004', todayMonth, clock, '5000000'));
  await page.reload();
  await page.waitForSelector('#thang-2026-09');
  // Tháng 9: dòng Sheet 1 (phiếu Sheet), dòng Sheet 2, chuyến web, rồi hàng thêm.
  const sept = await payRows(page, '2026-09');
  assert.equal(sept.length, 5);
  assert.equal(sept[0].date, '10/01/2026');   // 46032 = 10/01/2026, ghi chú lặp cùng ngày bị bỏ
  assert.equal(sept[0].method, '');
  assert.deepEqual(sept.slice(1, 4).map(row => row.date), ['01/10/2026', '02/10/2026', '03/10/2026']);
  assert.equal(sept[4].entry, true);
  assert.equal(sept[3].first, '');            // hàng thêm chỉ có cột thu
  assert.equal(await page.locator('#thang-2026-09 [data-pid="PH-001"][data-field="date"]').count(), 1);
  // Tháng hiện tại: một phiếu ở hàng 1, ô nhập ở hàng 2 (cuối), tham chiếu nằm trong ô số tiền.
  const now = await payRows(page, todayMonth.slice(0, 7));
  assert.equal(now.length, 2);
  assert.equal(now[0].entry, false);
  assert.equal(now[1].entry, true);
  assert.equal(await page.locator(`#thang-${todayMonth.slice(0, 7)} .receipt-amount`).locator('xpath=ancestor::td').locator('.receipt-reference').count(), 1);
  // Tham chiếu là chữ nhỏ trong ô Số tiền trả, bấm để sửa; không còn hàng Tham chiếu riêng.
  assert.equal(await page.locator('tr.reference-row').count(), 0);
  const reference = page.locator('.receipt-ref[data-pid="PH-001"][data-field="reference"]');
  assert.equal(await reference.innerText(), 'Tham chiếu: REF-A');
  await reference.click();
  assert.equal(await reference.locator('input').inputValue(), 'REF-A');
  await reference.locator('input').press('Escape');
  assert.equal(await reference.innerText(), 'Tham chiếu: REF-A');
  // Bấm vào ô số tiền (không phải chữ tham chiếu) vẫn mở hỏi hủy phiếu.
  await page.locator('td.receipt[data-pid="PH-002"]:not([data-field])').click({ position: { x: 4, y: 4 } });
  assert.equal(await page.locator('.void-prompt[data-pid="PH-002"]').count(), 1);
  await page.locator('.cancel-void').click();
  await shot('phieu-thu-hang-ke-tiep');
  // Tháng chưa có phiếu: ô nhập ở hàng 1.
  world.receipts.length = 0; world.legacy.pop();
  await page.reload();
  await page.waitForSelector('#thang-2026-09');
  assert.equal((await payRows(page, '2026-09')).some(row => row.date !== ''), false);
  const empty = await payRows(page, todayMonth.slice(0, 7));
  assert.equal(empty.length, 1);
  assert.equal(empty[0].entry, true);
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
