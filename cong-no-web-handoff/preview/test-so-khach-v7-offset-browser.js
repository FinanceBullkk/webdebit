/* Trình duyệt (Playwright) cho cấn trừ hai sổ trên sổ khách V7. Máy chủ giả tự dựng, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const shots = process.env.SHOTS_DIR;
const clock = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const monthStart = `${clock.slice(0, 7)}-01`;
const viDate = iso => `${iso.slice(8)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
const dayInMonth = '2026-10-20' <= clock && clock.startsWith('2026-10') ? '2026-10-20' : `${clock.slice(0, 7)}-01`;

function makeWorld() {
  const book = (id, name, commodity, base, charges) => ({ id, name, commodity, version: 1, base, charges, receipts: [], outgoing: [], events: [], locks: [], nextPid: 1 });
  const world = {
    books: { 1: book(1, 'Khách Thử Một', 'sầu riêng', 0n, 50000000n), 2: book(2, 'Khách Thử Hai', 'sầu riêng', -100000000n, 0n), 3: book(3, 'Khách Thử Ba', 'chuối', -30000000n, 0n) },
    pairs: [], nextPair: 1, requests: [], failNext: null, nextEvent: 10,
  };
  return world;
}

const received = book => book.receipts.filter(item => item.voided_by_event == null).reduce((sum, item) => sum + item.amount, 0n);
const outgoing = book => book.outgoing.filter(item => item.voided_by_event == null).reduce((sum, item) => sum + item.amount, 0n);
const outstanding = book => book.base + book.charges - received(book) + outgoing(book);

function ledger(world, id) {
  const out = ledgerBase(world, id);
  out.trips.push(...(world.books[id].review ?? []).map(item => ({ id: item.id, month: monthStart, container: item.container, carrier: '', event_date: dayInMonth, origin: '', destination: '',
    unit_price_vnd: '100', other_fee_vnd: null, amount_vnd: item.status === 'confirmed' ? '100' : null, status: item.status, review_reason: item.reason ?? null,
    is_missing_price: false, is_fee_only: false, editable: false, src: '' })));
  return out;
}

function ledgerBase(world, id) {
  const book = world.books[id];
  const total = outstanding(book);
  return { status: 'active', customer_id: id, version: book.version, demo: true, today_month: monthStart, month_locks: book.locks,
    months: [{ month: monthStart, prior_months_vnd: book.base.toString(), charges_vnd: book.charges.toString(), received_vnd: received(book).toString(),
      end_of_month_vnd: total.toString(), outstanding_vnd: total.toString() }],
    total_outstanding_vnd: total.toString(), pending_count: 0,
    trips: book.charges > 0n ? [{ id: 1, month: monthStart, container: 'DEMO-001', carrier: 'Tàu thử', event_date: dayInMonth, origin: 'Nơi A', destination: 'Nơi B',
      unit_price_vnd: book.charges.toString(), other_fee_vnd: '0', amount_vnd: book.charges.toString(), is_missing_price: false, is_fee_only: false, editable: true, src: '' }] : [],
    adjustments: [], opening: [], source_exceptions: [], legacy_rows: [], events: book.events,
    receipts: book.receipts.map(item => ({ id: item.pid, pid: item.pid, reference: item.reference ?? null, date: item.date, method: item.method, amount_vnd: item.amount.toString(),
      void_reason: item.void_reason ?? null, offset_pair_id: item.pair ?? null, counterparty_customer_id: item.other ?? null,
      counterparty_name: item.other ? world.books[item.other].name : null, voided_on: item.voided_on ?? null, voided_by_event: item.voided_by_event ?? null,
      allocations: [{ month: monthStart, amount_vnd: item.amount.toString(), kind: 'debt', superseded_by_event: item.voided_by_event == null ? null : item.voided_by_event }] })),
    outgoing_offsets: book.outgoing.map(item => ({ offset_pair_id: item.pair, pid: item.pid, date: item.date, method: 'CẤN TRỪ', amount_vnd: (-item.amount).toString(),
      void_reason: item.void_reason ?? null, voided_by_event: item.voided_by_event ?? null, counterparty_customer_id: item.other, counterparty_name: world.books[item.other].name })) };
}

function reply(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

test('CSM: optional reference, inline edit/clear, duplicate warns but saves, lock history has both actions', async () => withPage(async ({ page, world, open }) => {
  await open(1);
  assert.equal(await page.getByLabel('Tham chiếu', { exact: true }).count(), 1);
  async function pay(reference) {
    const expected = world.books[1].receipts.length + 1;
    await page.locator('.receipt-date:not(.saved-receipt-input)').fill(viDate(dayInMonth));
    await page.locator('.receipt-reference').fill(reference);
    await page.locator('.receipt-amount').fill('10');
    await page.locator('.receipt-amount').press('Enter');
    await page.waitForFunction(count => document.querySelectorAll('[data-field="reference"]').length === count, expected);
    await page.waitForFunction(() => /Đã lưu/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  }
  await pay('');
  assert.equal(world.books[1].receipts[0].reference, null);
  await pay('FAKE USD/rate text');
  const reference = page.locator('.receipt[data-pid="PH-021"][data-field="reference"]');
  await reference.click();
  await reference.locator('input').fill('FAKE USD/rate text');
  await reference.locator('input').press('Enter');
  await page.waitForFunction(() => /Tham chiếu trùng/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  assert.equal(world.books[1].receipts.length, 2);
  assert.equal(world.books[1].receipts[0].reference, 'FAKE USD/rate text');
  await reference.click();
  await reference.locator('input').fill('');
  await reference.locator('input').press('Enter');
  await page.waitForFunction(() => document.querySelector('[data-pid="PH-021"][data-field="reference"]')?.classList.contains('empty'));
  await pay('FAKE USD/rate text');
  assert.equal(world.books[1].receipts.length, 3);
  await page.waitForFunction(() => /Tham chiếu trùng/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  assert.match(await page.locator('.live-notice').innerText(), /Tham chiếu trùng/);
  const lock = page.locator('.month-lock');
  await lock.click();
  await page.waitForFunction(() => document.querySelector('.month-lock')?.getAttribute('aria-pressed') === 'false');
  await lock.click();
  await page.waitForFunction(() => document.querySelector('.month-lock')?.getAttribute('aria-pressed') === 'true');
  await page.locator('.history-toggle').click();
  const history = await page.locator('#history-panel').innerText();
  assert.match(history, /Khóa tháng/);
  assert.match(history, /Mở tháng/);
  assert.match(history, /fake-browser-actor/);
  assert.match(history, /02\/01\/2026 10:00/);
  assert.equal(await page.locator('#history-panel li').count(), 2);
  assert.equal(world.requests.at(-1).path, '/api/v7/months/lock');
}));

function handleApi(world, req, res, url, body) {
  if (req.method === 'GET' && url.pathname === '/api/v7/customers') {
    return reply(res, 200, { demo: true, customers: Object.values(world.books).map(item => ({ id: item.id, name: item.name, status: 'active',
      commodity: item.commodity, transport_mode: item.mode ?? null })) });
  }
  if (url.pathname.startsWith('/api/v7/presence')) return reply(res, 200, { people: [] });   // PRESENCE-01, không phải lệnh ghi sổ
  if (url.pathname.startsWith('/api/v7/price-table') && req.method === 'GET') return reply(res, 404, { error: 'NOT_FOUND' });   // BANG-GIA-01: sổ thử chưa có bảng giá
  if (url.pathname === '/api/v7/sheet/refresh') return reply(res, 404, { error: 'NOT_FOUND' });   // nút Làm mới: server chưa bật
  if (req.method === 'GET' && url.pathname === '/api/v7/fee-types') return reply(res, 200, { fee_types: [] });   // danh mục phụ phí (PHU-PHI-01)
  if (req.method === 'GET' && url.pathname === '/api/v7/ledger') return reply(res, 200, ledger(world, Number(url.searchParams.get('customer'))));
  if (req.method === 'GET' && url.pathname === '/api/v7/offset-sources') {
    const self = Number(url.searchParams.get('customer'));
    const sources = Object.values(world.books).filter(item => item.id !== self && outstanding(item) < 0n).map(item => ({
      customer_id: item.id, name: item.name, commodity: item.commodity, version: item.version,
      outstanding_vnd: outstanding(item).toString(), available_credit_vnd: (-outstanding(item)).toString() }));
    return reply(res, 200, { demo: true, sources: sources.reverse() });
  }
  // CHUNG-TU-01: trang đọc danh sách ảnh chứng từ sau mỗi lần đọc sổ; máy giả này chưa có ảnh, không tính là lệnh.
  if (req.method === 'GET' && url.pathname.startsWith('/api/v7/receipt-image')) return reply(res, 404, { error: 'NOT_FOUND' });
  world.requests.push({ path: url.pathname, body });
  if (world.failNext) { const failure = world.failNext; world.failNext = null; return reply(res, failure.status, failure.body); }
  const bump = (...books) => books.forEach(item => { item.version += 1; });
  if (url.pathname === '/api/v7/offsets') {
    const target = world.books[body.target_customer_id], source = world.books[body.source_customer_id];
    if (target.version !== body.target_version || source.version !== body.source_version) return reply(res, 409, { error: 'STALE_LEDGER', message: 'Sổ vừa đổi.' });
    const amount = BigInt(body.amount_vnd);
    if (amount > -outstanding(source)) return reply(res, 422, { error: 'OFFSET_EXCEEDS_CREDIT', message: 'x', available_credit_vnd: (-outstanding(source)).toString() });
    const pair = world.nextPair++;
    const targetPid = `PH-${String(21 + target.receipts.length).padStart(3, '0')}`, sourcePid = `PH-${String(13 + source.outgoing.length).padStart(3, '0')}`;
    target.receipts.push({ pid: targetPid, date: body.date, method: 'CẤN TRỪ', amount, pair, other: source.id });
    source.outgoing.push({ pid: sourcePid, date: body.date, amount, pair, other: target.id });
    bump(target, source);
    return reply(res, 200, { offset_pair_id: pair, source_customer_id: source.id, target_customer_id: target.id, source_version: source.version,
      target_version: target.version, source_pid: sourcePid, target_pid: targetPid, target_receipt: { overpayment_vnd: '0' } });
  }
  if (url.pathname === '/api/v7/offsets/void' || url.pathname === '/api/v7/offsets/date') {
    const self = world.books[body.customer_id];
    const mine = self.receipts.find(item => item.pair === body.offset_pair_id) ?? self.outgoing.find(item => item.pair === body.offset_pair_id);
    const other = world.books[mine.other];
    if (self.version !== body.expected_version || other.version !== body.other_version) return reply(res, 409, { error: 'STALE_LEDGER', message: 'Sổ vừa đổi.' });
    const both = [mine, [...other.receipts, ...other.outgoing].find(item => item.pair === body.offset_pair_id)];
    for (const item of both) {
      if (url.pathname.endsWith('/void')) Object.assign(item, { void_reason: body.reason, voided_by_event: world.nextEvent, voided_on: clock });
      else item.date = body.date;
    }
    world.nextEvent += 1;
    bump(self, other);
    return reply(res, 200, { offset_pair_id: body.offset_pair_id });
  }
  if (url.pathname === '/api/v7/trips/review') {
    const self = world.books[body.customer_id];
    const held = self.review.find(item => item.id === body.trip_id && item.status === 'pending_review');
    if (!held) return reply(res, 422, { error: 'TRIP_NOT_PENDING', message: 'Chuyến không còn chờ kiểm.' });
    held.status = body.decision === 'confirm' ? 'confirmed' : 'rejected';
    bump(self);
    return reply(res, 200, { status: held.status });
  }
  if (url.pathname === '/api/v7/receipts') {
    const self = world.books[body.customer_id];
    const reference = body.reference?.trim() || null;
    const duplicate = reference !== null && self.receipts.some(item => item.reference === reference);
    self.receipts.push({ pid: `PH-${String(21 + self.receipts.length).padStart(3, '0')}`, reference, date: body.date, method: body.method, amount: BigInt(body.amount_vnd) });
    bump(self);
    return reply(res, 200, { receipt: 'ok', duplicate_reference: duplicate });
  }
  if (url.pathname === '/api/v7/receipts/meta') {
    const self = world.books[body.customer_id], receipt = self.receipts.find(item => item.pid === body.pid);
    if (body.reference !== undefined) receipt.reference = body.reference.trim() || null;
    const duplicate = receipt.reference !== null && self.receipts.some(item => item !== receipt && item.reference === receipt.reference);
    bump(self);
    return reply(res, 200, { duplicate_reference: duplicate });
  }
  if (url.pathname === '/api/v7/months/lock') {
    const self = world.books[body.customer_id];
    self.events.unshift({ kind: 'month_lock', actor: 'fake-browser-actor', at: '2026-01-02T03:00:00Z', before: { month: body.month, locked: !body.locked }, after: { month: body.month, locked: body.locked } });
    self.locks = [{ month: body.month, locked: body.locked }];
    bump(self);
    return reply(res, 200, { locked: body.locked });
  }
  return reply(res, 404, { error: 'NOT_FOUND', message: 'Không có.' });
}

async function withPage(fn) {
  const world = makeWorld();
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname.startsWith('/api/')) {
      const chunks = [];
      req.on('data', chunk => chunks.push(chunk));
      req.on('end', () => {
        let body = {};
        try { body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}; } catch { /* body lạ */ }
        handleApi(world, req, res, url, body);
      });
      return;
    }
    const file = path.join(__dirname, url.pathname.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html; charset=utf-8' : 'text/javascript; charset=utf-8' });
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // Danh sách khách về sau sổ thì vẽ lại cả sổ, xóa ô đang gõ (CẤN TRỪ về THU TIỀN): chờ nó xong mới thao tác.
    const open = async id => {
      await page.goto(`${base}/so-khach-v7-live.html?customer=${id}`);
      await page.waitForSelector('.book-head .history-toggle');
      await page.waitForFunction(() => document.querySelector('#customer-count')?.textContent);
    };
    const shot = async name => { if (shots) { fs.mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, `${name}.png`) }); } };
    await fn({ page, world, open, shot, base });
    assert.deepEqual(errors, []);
  } finally { await browser.close(); server.close(); }
}

const notice = page => page.locator('.live-notice');

async function fillEntry(page, date, amount) {
  await page.locator('.receipt-method').selectOption('CẤN TRỪ');
  await page.locator('.receipt-date').fill(viDate(date));
  await page.locator('.receipt-amount').fill(amount);
}

async function pickSource(page, name) {
  await page.locator('.offset-source-select').click();
  await page.locator('.offset-option', { hasText: name }).click();
}

test('MH-01: ô chọn khách nhóm theo mặt hàng, tìm không dấu theo mặt hàng, Enter mở khách đầu của kết quả', async () => withPage(async ({ page, world, open, shot }) => {
  world.books[1].mode = 'BO';
  await open(3);
  const search = page.locator('#customer-search');
  await search.click();
  await search.fill('');
  await page.locator('#customer-list .customer-group').first().waitFor();
  assert.deepEqual(await page.locator('#customer-list .customer-group').allInnerTexts(), ['chuối (1)', 'sầu riêng (1)', 'sầu riêng · bộ (1)']);
  assert.deepEqual(await page.locator('#customer-list a').allInnerTexts(), ['Khách Thử Ba · chuối', 'Khách Thử Hai · sầu riêng', 'Khách Thử Một · sầu riêng · bộ']);
  await shot('0-chon-khach-theo-mat-hang');
  await search.fill('sau rieng bo');
  assert.deepEqual(await page.locator('#customer-list a').allInnerTexts(), ['Khách Thử Một · sầu riêng · bộ']);
  await search.fill('SẦU RIÊNG');
  assert.deepEqual(await page.locator('#customer-list a').allInnerTexts(), ['Khách Thử Hai · sầu riêng', 'Khách Thử Một · sầu riêng · bộ']);
  await search.press('Enter');
  await page.waitForURL(/customer=2$/);
}));

test('chọn CẤN TRỪ hiện ô Lấy từ sổ; danh sách xếp A→Z, có Ngoài sổ, lọc theo tên', async () => withPage(async ({ page, open, shot }) => {
  await open(1);
  assert.equal(await page.locator('.offset-source-row').count(), 0);
  await page.locator('.receipt-method').selectOption('CẤN TRỪ');
  await page.locator('.offset-source-select').waitFor();
  assert.match(await page.locator('.offset-source-select').innerText(), /Chọn sổ đang dư tiền/);
  await page.locator('.offset-source-select').click();
  await page.locator('.offset-outside').waitFor();
  const names = await page.locator('.offset-option:not(.offset-outside) span').allInnerTexts();
  assert.deepEqual(names, ['Khách Thử Ba · chuối', 'Khách Thử Hai · sầu riêng']);
  assert.deepEqual(await page.locator('.offset-option:not(.offset-outside) strong').allInnerTexts(), ['-30.000.000', '-100.000.000']);
  assert.match(await page.locator('.offset-outside').innerText(), /Ngoài sổ/);
  await shot('1-chon-so-lay-tien');
  await page.locator('.offset-search').fill('sau rieng');
  assert.deepEqual(await page.locator('.offset-option:not(.offset-outside) span').allInnerTexts(), ['Khách Thử Hai · sầu riêng']);
  await page.locator('.offset-search').fill('zzz');
  assert.match(await page.locator('.offset-none').innerText(), /Không tìm thấy/);
  await page.locator('.receipt-method').selectOption('THU TIỀN');
  assert.equal(await page.locator('.offset-source-row').count(), 0);
}));

test('ghi cấn trừ: khung xác nhận có số trước → sau, gửi version cả hai sổ, sổ nhận có liên kết sang sổ bên kia', async () => withPage(async ({ page, world, open, shot }) => {
  await open(1);
  await fillEntry(page, dayInMonth, '50.000.000');
  await pickSource(page, 'Khách Thử Hai');
  await shot('2-nhap-so-tien');
  await page.locator('.receipt-amount').press('Enter');
  const dialog = page.locator('.offset-dialog');
  await dialog.waitFor();
  const text = await dialog.innerText();
  assert.match(text, /Cấn trừ 50\.000\.000 từ sổ Khách Thử Hai · sầu riêng sang sổ Khách Thử Một/);
  assert.match(text, /-100\.000\.000\s*→\s*-50\.000\.000/);
  assert.match(text, /50\.000\.000\s*→\s*0/);
  assert.doesNotMatch(text, /sẽ còn/);
  assert.equal(world.requests.length, 0, 'chưa gửi gì trước khi xác nhận');
  await shot('3-xac-nhan');
  await page.locator('.offset-confirm').click();
  await page.waitForFunction(() => !document.querySelector('.offset-dialog'));
  assert.equal(world.requests.length, 1);
  const { path: sent, body } = world.requests[0];
  assert.equal(sent, '/api/v7/offsets');
  assert.deepEqual({ ...body, idempotency_key: typeof body.idempotency_key }, {
    target_customer_id: 1, target_version: 1, source_customer_id: 2, source_version: 1,
    idempotency_key: 'string', date: dayInMonth, amount_vnd: '50000000' });
  assert.match(await notice(page).innerText(), /Đã ghi PH-021: cấn trừ 50\.000\.000 từ sổ Khách Thử Hai · sầu riêng \(phiếu PH-013\)\. Sổ đó còn -50\.000\.000\./);
  const link = page.locator('.offset-link');
  assert.equal(await link.innerText(), 'từ Khách Thử Hai');
  assert.match(await link.getAttribute('href'), /customer=2$/);
  assert.equal(await page.locator('.head-item.total strong').innerText(), '0');
  await shot('4-ghi-xong-so-nhan');
  await open(2);
  assert.equal(await page.locator('.offset-link').innerText(), 'sang Khách Thử Một');
  assert.equal(await page.locator('td.receipt[data-pair]').last().innerText(), '-50.000.000');
  assert.equal(await page.locator('.head-item.total strong').innerText(), '-50.000.000');
  await shot('5-so-nguon-sau-khi-ghi');
}));

test('cấn quá nợ của sổ nhận: khung báo trước số âm, vẫn cho ghi', async () => withPage(async ({ page, open }) => {
  await open(1);
  await fillEntry(page, dayInMonth, '70.000.000');
  await pickSource(page, 'Khách Thử Hai');
  await page.locator('.receipt-amount').press('Enter');
  const text = await page.locator('.offset-dialog').innerText();
  assert.match(text, /Sổ Khách Thử Một · sầu riêng sẽ còn -20\.000\.000\./);
  assert.equal(await page.locator('.offset-confirm').isEnabled(), true);
}));

test('chặn ngay tại ô: vượt số dư, chưa chọn sổ, ngày sai/tương lai; không gửi lệnh nào', async () => withPage(async ({ page, world, open, shot }) => {
  await open(1);
  await fillEntry(page, dayInMonth, '31.000.000');
  await page.locator('.receipt-amount').press('Enter');
  assert.match(await page.locator('.offset-source-error').innerText(), /Chọn sổ lấy tiền, hoặc chọn Ngoài sổ/);
  await pickSource(page, 'Khách Thử Ba');
  await page.locator('.receipt-amount').press('Enter');
  assert.match(await page.locator('.receipt-amount-error').innerText(), /Sổ Khách Thử Ba · chuối chỉ còn dư 30\.000\.000/);
  await shot('6-loi-vuot-so-du');
  await page.locator('.receipt-amount').fill('abc');
  await page.locator('.receipt-amount').press('Enter');
  assert.match(await page.locator('.receipt-amount-error').innerText(), /Số tiền không hợp lệ/);
  await page.locator('.receipt-amount').fill('1.000.000');
  await page.locator('.receipt-date').fill('01/01/2099');
  await page.locator('.receipt-amount').press('Enter');
  assert.match(await page.locator('.receipt-date-error').innerText(), /Ngày trả không được sau hôm nay/);
  await page.locator('.receipt-date').fill('32/13/2026');
  await page.locator('.receipt-amount').press('Enter');
  assert.match(await page.locator('.receipt-date-error').innerText(), /Ngày trả không hợp lệ/);
  assert.equal(world.requests.length, 0);
  assert.equal(await page.locator('.offset-dialog').count(), 0);
}));

test('Ngoài sổ ghi như thu thường, không hỏi sổ bên kia', async () => withPage(async ({ page, world, open }) => {
  await open(1);
  await fillEntry(page, dayInMonth, '5.000.000');
  await page.locator('.offset-source-select').click();
  await page.locator('.offset-outside').click();
  assert.match(await page.locator('.offset-source-select').innerText(), /Ngoài sổ/);
  await page.locator('.receipt-amount').press('Enter');
  await page.waitForFunction(() => document.querySelector('.live-notice')?.textContent === 'Đã lưu.');
  assert.equal(await page.locator('.offset-dialog').count(), 0);
  assert.deepEqual(world.requests.map(item => item.path), ['/api/v7/receipts']);
  assert.equal(world.requests[0].body.method, 'CẤN TRỪ');
  assert.equal(world.requests[0].body.amount_vnd, '5000000');
}));

test('server từ chối vượt dư: câu tiếng Việt hiện trong khung, dữ liệu giữ nguyên; sổ đổi thì báo tải lại', async () => withPage(async ({ page, world, open, shot }) => {
  await open(1);
  await fillEntry(page, dayInMonth, '10.000.000');
  await pickSource(page, 'Khách Thử Hai');
  await page.locator('.receipt-amount').press('Enter');
  world.failNext = { status: 422, body: { error: 'OFFSET_EXCEEDS_CREDIT', message: 'Số tiền vượt', available_credit_vnd: '4000000' } };
  await page.locator('.offset-confirm').click();
  await page.locator('.offset-dialog-error').filter({ hasText: 'chỉ còn dư 4.000.000' }).waitFor();
  assert.match(await page.locator('.offset-dialog-error').innerText(), /^Sổ lấy tiền chỉ còn dư 4\.000\.000$/);
  await shot('7-loi-tu-may-chu');
  await page.locator('.offset-back').click();
  assert.equal(await page.locator('.receipt-amount').inputValue(), '10.000.000');
  // Sổ bên kia đổi giữa chừng: lệnh bị từ chối vì version, giao diện tải lại và báo.
  await page.locator('.receipt-amount').press('Enter');
  world.books[2].version += 1;
  await page.locator('.offset-confirm').click();
  await page.waitForFunction(() => !document.querySelector('.offset-dialog'));
  assert.match(await notice(page).innerText(), /Sổ vừa thay đổi/);
  assert.equal(world.books[1].receipts.length, 0);
}));

test('hủy cấn trừ từ sổ nguồn: bắt buộc lý do, hủy cả hai sổ, hiện đúng mã phiếu hai bên', async () => withPage(async ({ page, world, open, shot }) => {
  await open(1);
  await fillEntry(page, dayInMonth, '50.000.000');
  await pickSource(page, 'Khách Thử Hai');
  await page.locator('.receipt-amount').press('Enter');
  await page.locator('.offset-confirm').click();
  await page.waitForFunction(() => !document.querySelector('.offset-dialog'));
  await open(2);
  await page.locator('td.receipt[data-pair]').last().click();
  const prompt = page.locator('.offset-void-prompt');
  await prompt.waitFor();
  const head = await prompt.locator('.offset-void-head').innerText();
  assert.match(head, /PH-013 ở sổ Khách Thử Hai · sầu riêng và PH-021 ở sổ Khách Thử Một/);
  await prompt.locator('.confirm-offset-void').click();
  assert.match(await prompt.locator('.offset-void-error').innerText(), /Nhập lý do hủy/);
  assert.equal(world.requests.length, 1, 'chưa lý do thì không gửi');
  await shot('8-huy-can-tru-hoi-ly-do');
  await prompt.locator('.offset-void-reason').fill('nhập nhầm');
  await prompt.locator('.offset-void-reason').press('Enter');
  await page.waitForFunction(() => document.querySelector('.live-notice')?.textContent === 'Đã hủy cấn trừ ở cả hai sổ.');
  const sent = world.requests[1];
  assert.equal(sent.path, '/api/v7/offsets/void');
  assert.deepEqual({ ...sent.body, idempotency_key: typeof sent.body.idempotency_key },
    { customer_id: 2, expected_version: 2, other_version: 2, idempotency_key: 'string', offset_pair_id: 1, reason: 'nhập nhầm' });
  // SO-GON-02: phiếu đã hủy rời danh sách phiếu, gom vào một dòng mờ; bấm Xem mới hiện số tiền và lý do.
  assert.equal(await page.locator('td.voided-method').count(), 0);
  assert.match(await page.locator('.void-summary').innerText(), /1 phiếu đã hủy, không tính tiền/);
  await page.locator('.void-toggle').click();
  assert.match(await page.locator('.pay-list .void-trace').innerText(), /nhập nhầm/);
  assert.equal(await page.locator('.void-toggle').getAttribute('aria-expanded'), 'true');
  assert.equal(await page.locator('.head-item.total strong').innerText(), '-100.000.000');
  await shot('9-sau-khi-huy-so-nguon');
  await open(1);
  assert.match(await page.locator('.void-summary').innerText(), /1 phiếu đã hủy/);
  assert.equal(await page.locator('.head-item.total strong').innerText(), '50.000.000');
}));

test('đổi ngày cấn trừ từ sổ nhận: gửi version cả hai sổ, báo đã đổi cả hai sổ; ngày tương lai bị chặn tại ô', async () => withPage(async ({ page, world, open, shot }) => {
  await open(1);
  await fillEntry(page, dayInMonth, '20.000.000');
  await pickSource(page, 'Khách Thử Hai');
  await page.locator('.receipt-amount').press('Enter');
  await page.locator('.offset-confirm').click();
  await page.waitForFunction(() => !document.querySelector('.offset-dialog'));
  const dateCell = page.locator('td.receipt[data-field="date"][data-pair]');
  await dateCell.click();
  const input = dateCell.locator('input');
  await input.fill('01/01/2099');
  await input.press('Enter');
  assert.match(await dateCell.locator('.cell-error').innerText(), /Ngày trả không được sau hôm nay/);
  const newDate = `${clock.slice(0, 7)}-02`;
  await input.fill(viDate(newDate));
  await shot('10-doi-ngay');
  await input.press('Enter');
  await page.waitForFunction(() => /Đã đổi ngày cấn trừ/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const sent = world.requests.at(-1);
  assert.equal(sent.path, '/api/v7/offsets/date');
  assert.deepEqual({ ...sent.body, idempotency_key: typeof sent.body.idempotency_key },
    { customer_id: 1, expected_version: 2, other_version: 2, idempotency_key: 'string', offset_pair_id: 1, date: newDate });
  assert.equal(await page.locator('td.receipt[data-field="date"][data-pair]').innerText(), viDate(newDate));
  assert.equal(world.books[2].outgoing[0].date, newDate);
}));

test('không có sổ nào đang dư: báo rõ và vẫn còn Ngoài sổ', async () => withPage(async ({ page, world, open }) => {
  world.books[2].base = 0n; world.books[3].base = 0n;
  await open(1);
  await page.locator('.receipt-method').selectOption('CẤN TRỪ');
  await page.locator('.offset-source-select').click();
  assert.match(await page.locator('.offset-none').innerText(), /Không có sổ nào đang dư tiền/);
  assert.equal(await page.locator('.offset-outside').count(), 1);
}));

test('CHỜ KIỂM: bấm nút mở dòng kết luận, lý do trống không gửi, Loại → ĐÃ LOẠI gạch ngang, Tính vào sổ gửi đúng lệnh', async () => withPage(async ({ page, world, open, shot }) => {
  world.books[1].review = [{ id: 11, container: 'DEMO-HELD-1', status: 'pending_review', reason: 'BASELINE_CODE_MATCH' },
    { id: 12, container: 'DEMO-HELD-2', status: 'pending_review', reason: null }];
  await open(1);
  assert.equal(await page.locator('.review-open').count(), 2);
  await page.locator('.review-open[data-trip="11"]').click();
  assert.match(await page.locator('.review-prompt').innerText(), /Trùng mã với dòng sổ gốc/);
  await shot('11-cho-kiem');
  await page.locator('.review-reject').click();
  assert.equal(await page.locator('.review-error').innerText(), 'Cần nhập lý do kết luận');
  assert.equal(world.requests.length, 0);
  await page.locator('.review-reason').fill('trùng dòng sổ gốc');
  await page.locator('.review-reject').click();
  await page.waitForFunction(() => document.querySelectorAll('.trip-rejected').length === 1);
  assert.deepEqual({ ...world.requests[0].body, idempotency_key: typeof world.requests[0].body.idempotency_key },
    { customer_id: 1, expected_version: 1, idempotency_key: 'string', trip_id: 11, decision: 'reject', reason: 'trùng dòng sổ gốc' });
  assert.equal(await page.locator('.trip-rejected').innerText(), 'ĐÃ LOẠI');
  assert.match(await page.locator('.trip-rejected').evaluate(el => getComputedStyle(el).textDecorationLine), /line-through/);
  assert.equal(await page.locator('.review-open').count(), 1);
  await page.locator('.review-open[data-trip="12"]').click();
  assert.match(await page.locator('.review-prompt').innerText(), /Nghi trùng/);
  await page.locator('.review-reason').fill('chuyến mới thật');
  await page.locator('.review-confirm').click();
  await page.waitForFunction(() => document.querySelectorAll('.review-open').length === 0);
  assert.equal(world.requests[1].body.decision, 'confirm');
  assert.equal(world.requests[1].body.trip_id, 12);
}));
