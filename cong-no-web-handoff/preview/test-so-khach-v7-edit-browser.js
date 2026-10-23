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

// Sổ giả: một chuyến web tháng 9 (khóa), một dòng sổ gốc thiếu giá và một dòng có giá tháng 9.
function makeWorld() {
  return {
    version: 1, receipts: [], requests: [], failNext: null, nextEvent: 1, events: [], adjustments: [],
    trips: [{ id: 11, month: '2026-09-01', container: 'DEMU1234567', carrier: 'Tàu thử', event_date: '2026-09-15', origin: 'Nơi A', destination: 'Nơi B',
      unit_price_vnd: '50000000', other_fee_vnd: null, amount_vnd: '50000000', status: 'confirmed', is_missing_price: false, is_fee_only: false,
      editable: false, info_editable: true, deleted: false }],
    legacy: [
      { id: 21, month: '2026-09-01', kind: 'trip', source_total_vnd: null, editable: true,
        display: { row: 5, stt: '1', container: 'OLDU0000001', carrier: 'Xe 1', date: '2026-09-02', from: 'Nơi C', to: 'Nơi D', unit_price: '', fee_vnd: '', flags: ['MISSING_PRICE'] },
        current: { container: 'OLDU0000001', carrier: 'Xe 1', event_date: '2026-09-02', origin: 'Nơi C', destination: 'Nơi D', unit_price_vnd: null, other_fee_vnd: null, counted_vnd: '0', month: '2026-09-01', deleted: false } },
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
    month_locks: [{ month: '2026-09-01', locked: true }],
    months: keys.map(month => ({ month, prior_months_vnd: '0', charges_vnd: '0', received_vnd: '0', end_of_month_vnd: '0', outstanding_vnd: '0' })),
    total_outstanding_vnd: '0', trips, adjustments: world.adjustments, opening: [], source_exceptions: [], receipts: world.receipts, outgoing_offsets: [],
    legacy_rows: legacy.map(row => ({ ...row, month: row.current.month })), events: world.events };
}

function apply(world, url, body) {
  const fail = world.failNext;
  if (fail) { world.failNext = null; return [422, fail]; }
  if (body.expected_version !== world.version) return [409, { error: 'STALE_LEDGER' }];
  const event = (kind, before, after) => world.events.unshift({ kind, actor: 'nguoi-thu', at: '2026-10-01T03:00:00Z', before, after });
  if (url === '/api/v7/trips/info') {
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

async function withPage(fn) {
  const world = makeWorld();
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const send = (status, body) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (url.pathname === '/api/v7/customers') { send(200, { customers: [{ id: 1, name: 'Khách Thử Sửa', status: 'active' }], demo: true }); return; }
    if (url.pathname === '/api/v7/ledger') { send(200, ledger(world)); return; }
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

test('chuyến web tháng khóa: sửa ô bằng Enter, Esc trả lại, Tab lưu; ghi Lịch sử trước → sau', async () => withPage(async ({ page, world, shot }) => {
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
  assert.match(await ask.innerText(), /Ngày 05\/08\/2026 thuộc tháng 8\/2026 \(đã khóa\)\. Chuyển chuyến DEMU1234567 sang tháng 8\/2026\?/);
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
}));

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
}));

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
  assert.equal(sept.length, 4);
  assert.equal(sept[0].date, '10/01/2026');   // 46032 = 10/01/2026, ghi chú lặp cùng ngày bị bỏ
  assert.equal(sept[0].method, '');
  assert.deepEqual(sept.slice(1).map(row => row.date), ['01/10/2026', '02/10/2026', '03/10/2026']);
  assert.equal(sept[3].first, '');            // hàng thêm chỉ có cột thu
  assert.equal(await page.locator('#thang-2026-09 [data-pid="PH-001"][data-field="date"]').count(), 1);
  // Tháng hiện tại: một phiếu ở hàng 1, ô nhập ở hàng 2 (cuối), tham chiếu nằm trong ô số tiền.
  const now = await payRows(page, todayMonth.slice(0, 7));
  assert.equal(now.length, 2);
  assert.equal(now[0].entry, false);
  assert.equal(now[1].entry, true);
  assert.equal(await page.locator('.receipt-amount').locator('xpath=ancestor::td').locator('.receipt-reference').count(), 1);
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
