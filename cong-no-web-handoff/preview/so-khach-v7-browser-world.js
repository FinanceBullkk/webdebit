/* Máy chủ giả và trình duyệt dùng chung cho test-so-khach-v7-*-browser.js (sửa tại ô, đối chiếu Sheet).
 * Tách từ test-so-khach-v7-edit-browser.js (29/10/2026). Dữ liệu giả, không chạm DB hay Sheet. */
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
    await page.goto(`http://127.0.0.1:${server.address().port}/so-khach-v7-live.html?customer=1${world.query ?? ''}`);
    await page.waitForSelector('.book-head .history-toggle');
    const shot = async name => { if (shots) { fs.mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: true }); } };
    await fn({ page, world, shot });
    assert.deepEqual(errors, []);
  } finally { await browser.close(); server.close(); }
}

const tripCell = (page, field, id = 11) => page.locator(`td.info-edit[data-kind="trip"][data-id="${id}"][data-field="${field}"]`);
const legacyCell = (page, id, field) => page.locator(`td.info-edit[data-kind="legacy"][data-id="${id}"][data-field="${field}"]`);
const posts = world => world.requests.map(item => [item.path, item.body]);

module.exports = { clock, todayMonth, withPage, tripCell, legacyCell, posts };
