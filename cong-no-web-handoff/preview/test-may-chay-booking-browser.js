const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// KIEM-BOOKING-01 + DU-CHUYEN-01: khối "Kiểm sổ với booking" của tab Máy chạy. Dữ liệu giả; chỉ xem nên không có lệnh POST nào ngoài presence.
const NOW = '2026-11-13T10:30:00+07:00';
const machine = () => ({ now: NOW, run: null, jobs: [], office: { state: 'off', tasks: {} }, runs: [] });
const CUSTOMERS = [{ id: 7, name: 'KHACH BAY', status: 'active' }, { id: 9, name: 'KHACH CHIN', status: 'active' }];
const src = (date, kind = 'BIEN', owner = 'CHU HANG GIA') => ({ kind, date, owner, ref: 'BK1', tab: kind === 'BO' ? 'CONT_BO' : 'CONT_NGUON', line: 4 });
const ROWS = [
  { group: 'dup', code: 'TRUNG', tab: 'KHACH BAY', row: 12, month: '2026-03', date: '2026-03-10', container: 'DUPU1111111', amount_vnd: '40000000', source: src('2026-03-10'), pair: null, paired: true, near_trips: 1 },
  { group: 'dup', code: 'TRUNG', tab: 'KHACH CHIN', row: 5, month: '2026-03', date: '2026-03-10', container: 'DUPU1111111', amount_vnd: '40000000', source: null, pair: null, paired: false, near_trips: 1 },
  { group: 'dup', code: 'TRUNG_DAO_NGAY', tab: 'KHACH CHIN', row: 8, month: '2026-06', date: '2026-06-03', container: 'DAOU2222222', amount_vnd: '38500000', source: src('2026-03-06'), pair: { tab: 'KHACH BAY', row: 20, date: '2026-03-06' }, paired: false },
  { group: 'missing', code: 'CHUA_TINH', tab: null, row: null, month: '2026-04', date: null, container: 'MISU3333333', amount_vnd: null, source: src('2026-04-20', 'BO', 'KHO GIA'), suggest: { tab: 'KHACH BAY', from: '2025-06' }, pair: null, paired: false },
  { group: 'nosource', code: 'KHONG_NGUON', tab: 'SO CHUA CO TREN WEB', row: 3, month: '2026-05', date: '2026-05-02', container: 'NONU4444444', amount_vnd: '12000000', source: null, pair: null, paired: false },
  { group: 'nodate', code: 'NGAY_TU_NGUON', tab: 'KHACH BAY', row: 30, month: '2026-07', date: null, raw_date: 'ĐÃ TT', container: 'UNDU5555555', amount_vnd: '41000000', source: src('2026-07-12'), pair: null, paired: true },
];
const COUNTS = { dup: 3, missing: 1, other: 0, nosource: 1, date: 0, nodate: 1, recent: 0 };
const ok = (extra = {}) => ({ version: 1, state: 'ok', now: NOW, checked_at: '2026-11-13T10:14:02+07:00', window: { BIEN: '2025-12', BO: '2025-08', end: '2026-11' },
  sheet: { rows: 7641, paired: 7308 }, counts: COUNTS, rows: ROWS, ...extra });

function makeServer(state) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body) => { response.writeHead(status, { 'Content-Type': type }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    state.calls.push(`${request.method} ${route}`);
    if (route === '/api/v7/machine/booking') return state.booking === null ? out({ error: 'X' }, 503) : out(state.booking);
    if (route === '/api/v7/machine' || route === '/api/v7/machine/now') return out(machine());
    if (route === '/api/v7/customers') return out({ customers: CUSTOMERS });
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 503);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(booking, fn, viewport = { width: 1265, height: 560 }) {
  const shared = { calls: [], booking };
  const server = makeServer(shared);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await (await browser.newContext({ viewport })).newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/may-chay.html`);
    await page.waitForFunction(() => document.getElementById('bk-status').textContent !== 'Đang tải…');
    await fn(page, shared);
    assert.deepEqual(errors, []);
    assert.deepEqual(shared.calls.filter(call => call.startsWith('POST') && !call.includes('presence')), [], 'khối chỉ xem không gửi lệnh ghi');
  } finally {
    await browser.close();
    server.close();
  }
}
const status = page => page.locator('#bk-status').innerText();
const CLEAN = 'Không thấy chuyến nào';

test('Kiểm booking: lượt đạt hiện giờ, số dòng khớp, nhóm đụng tiền trước; nhóm 0 không bấm được', () => withPage(ok(), async page => {
  assert.equal(await status(page), 'Lượt 10:14 hôm nay · 7.308/7.641 dòng chuyến khớp booking');
  assert.ok((await page.locator('#bk-scope').innerText()).includes('chuyến biển từ 12/2025, chuyến bộ từ 8/2025'));
  const groups = await page.locator('.bk-group').allInnerTexts();
  assert.deepEqual(groups.map(text => text.replace(/\s+/g, ' ')), ['Nghi tính hai lần 3', 'Booking có, sổ chưa tính 1', 'Sổ khác khách booking 0', 'Trên sổ, booking không có 1',
    'Lệch ngày 0', 'Sổ thiếu ngày 1', 'Tháng này chưa lên sổ 0']);
  assert.equal(await page.locator('[data-group="fix"]').count(), 0, 'lượt chưa có booking_fix: không hiện nhóm như thể 0 dòng lỗi');
  assert.equal(await page.locator('[data-group="other"]').isDisabled(), true);
  assert.equal(await page.locator('#bk-list').isVisible(), false);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
}));

test('Kiểm booking: mở nhóm thấy từng dòng, link mở sổ đúng tháng, lọc theo sổ, bấm lại thì đóng', () => withPage(ok(), async page => {
  await page.locator('[data-group="dup"]').click();
  assert.equal(await page.locator('[data-group="dup"]').getAttribute('aria-expanded'), 'true');
  assert.equal(await page.locator('#bk-list-name').innerText(), 'Nghi tính hai lần · 3');
  const rows = await page.locator('#bk-body tr').allInnerTexts();
  assert.equal(rows.length, 3);
  assert.ok(rows[0].includes('DUPU1111111') && rows[0].includes('10/03/2026') && rows[0].includes('40.000.000đ') && rows[0].includes('KHACH BAY'), rows[0]);
  assert.ok(rows[0].includes('booking chỉ có 1 chuyến'), rows[0]);
  assert.ok(!rows[1].includes('không có'), 'dòng thứ hai của cặp: chuyến đã ghép dòng kia, không ghi "không có"');
  assert.ok(rows[2].includes('Đảo ngày/tháng thì trùng chuyến booking 06/03/2026, đã tính ở KHACH BAY dòng 20'), rows[2]);
  assert.equal(await page.locator('#bk-body tr').first().locator('a').getAttribute('href'), '/so-khach-v7-live.html?customer=7&month=2026-03');
  await page.locator('#bk-book').selectOption('KHACH CHIN');
  assert.equal(await page.locator('#bk-body tr').count(), 2);
  assert.equal(await page.locator('#bk-list-name').innerText(), 'Nghi tính hai lần · 2 / 3');
  await page.locator('[data-group="missing"]').click();
  const missing = await page.locator('#bk-body tr').innerText();
  assert.ok(missing.includes('gợi ý') && missing.includes('KHACH BAY') && missing.includes('Bộ') && missing.includes('KHO GIA') && missing.includes('—'), missing);
  await page.locator('[data-group="nosource"]').click();
  assert.equal(await page.locator('#bk-body a').count(), 0, 'sổ chưa có trên web thì không có link');
  assert.ok((await page.locator('#bk-body tr').innerText()).includes('không có'));
  await page.locator('[data-group="nodate"]').click();
  assert.ok((await page.locator('#bk-body tr').innerText()).includes('ĐÃ TT'));
  await page.locator('[data-group="nodate"]').click();
  assert.equal(await page.locator('#bk-list').isVisible(), false);
}));

// Nhóm "tháng này" đã so với sổ web (đo 24/11/2026: 119/122 dòng máy đã đưa vào web): tách dòng web chưa có ra để xem.
const RECENT = [
  { group: 'recent', code: 'THANG_CUOI', tab: null, row: null, month: '2026-11', date: null, container: 'WEBU1111111', amount_vnd: null,
    source: src('2026-11-10'), suggest: { tab: 'KHACH BAY', from: '2025-12' }, web: { customer_id: 9, name: 'KHACH CHIN', date: '2026-11-11' } },
  { group: 'recent', code: 'THANG_CUOI', tab: null, row: null, month: '2026-11', date: null, container: 'WEBU2222222', amount_vnd: null,
    source: src('2026-11-12', 'BO', 'KHO GIA'), suggest: null, web: { customer_id: 7, name: 'KHACH BAY', date: '2026-11-12' } },
  { group: 'recent', code: 'THANG_CUOI', tab: null, row: null, month: '2026-11', date: null, container: 'NEWU3333333', amount_vnd: null,
    source: src('2026-11-04'), suggest: { tab: 'KHACH BAY', from: '2025-12' } },
];
const RECENT_COUNTS = { ...COUNTS, recent: 3 };

test('Kiểm booking: tháng này tách "web chưa có" với "web có, Sheet chưa ghi"; dòng web có link tới sổ web', () => withPage(ok({
  counts: RECENT_COUNTS, rows: [...ROWS, ...RECENT], recent_web: 'checked',
}), async page => {
  const info = (await page.locator('.bk-info .bk-group').allInnerTexts()).map(text => text.replace(/\s+/g, ' '));
  assert.deepEqual(info, ['Lệch ngày 0', 'Sổ thiếu ngày 1', 'Tháng này, web chưa có 1', 'Web có, Sheet chưa ghi 2']);
  await page.locator('[data-group="recent"]').click();
  const row = await page.locator('#bk-body tr').innerText();
  assert.ok(row.includes('NEWU3333333') && row.includes('gợi ý') && row.includes('Web chưa có'), row);
  assert.equal(await page.locator('#bk-body tr a', { hasText: 'xem lý do' }).getAttribute('href'), '/bao-cao-thang.html?month=2026-11&webchua=1');
  await page.locator('[data-group="recent_web"]').click();
  assert.equal(await page.locator('#bk-list-name').innerText(), 'Web có, Sheet chưa ghi · 2');
  const rows = await page.locator('#bk-body tr').allInnerTexts();
  assert.ok(rows[0].includes('KHACH CHIN') && rows[0].includes('Đã vào sổ web ngày 11/11/2026, chờ Sheet ghi giá') && !rows[0].includes('gợi ý'), rows[0]);
  assert.equal(await page.locator('#bk-body tr').first().locator('a').getAttribute('href'), '/so-khach-v7-live.html?customer=9&month=2026-11');
  await page.locator('#bk-book').selectOption('KHACH BAY');
  assert.deepEqual((await page.locator('#bk-body tr').allInnerTexts()).map(text => text.includes('WEBU2222222')), [true]);
}));

test('Kiểm booking: đọc sổ web lỗi thì nhóm tháng này giữ một nút như trước', () => withPage(ok({
  counts: RECENT_COUNTS, rows: [...ROWS, ...RECENT.map(({ web: _web, ...row }) => row)], recent_web: 'unavailable',
}), async page => {
  const info = (await page.locator('.bk-info .bk-group').allInnerTexts()).map(text => text.replace(/\s+/g, ' '));
  assert.deepEqual(info, ['Lệch ngày 0', 'Sổ thiếu ngày 1', 'Tháng này chưa lên sổ 3']);
  await page.locator('[data-group="recent"]').click();
  assert.ok((await page.locator('#bk-body').innerText()).includes('Tháng này, sổ có thể chưa ghi'));
  assert.equal(await page.locator('#bk-body a', { hasText: 'xem lý do' }).count(), 0);
}));

// Lọc nhiễu 24/11/2026: dòng booking thiếu ngày liệt kê theo tab nguồn cho người giữ booking; chuyến chưa tính nói rõ sổ có mấy dòng.
const FIX = [
  { family: 'BIEN', tab: 'THÁNG 08/2026', line: '41', cont: 'OERU4400262', owner: 'CHU HANG GIA', ref: 'BK8', raw_date: '/' },
  { family: 'BIEN', tab: 'THÁNG 07/2026', line: '25', cont: 'OERU4111260', owner: '', ref: 'BK7', raw_date: 'in' },
  { family: 'BO', tab: 'CONT_BO', line: 91, cont: 'CRLU1220757', owner: 'KHO GIA', ref: '47C-23393', raw_date: '' },
];
const NEAR_ROWS = [
  { ...ROWS[3], near: { booking: 2, sheet: 1 } },
  { ...ROWS[3], container: 'ALOU7777777', near: { booking: 1, sheet: 0 } },
  { ...ROWS[5], month: '2026-06', source: src('2026-05-29', 'BO') },
];

test('Kiểm booking: nhóm Booking thiếu ngày lọc theo tab nguồn; chuyến chưa tính nói sổ có mấy dòng; sổ ghi ở khối tháng sau', () => withPage(ok({
  booking_fix: FIX, rows: [...ROWS.filter(row => row.group !== 'missing' && row.group !== 'nodate'), ...NEAR_ROWS],
  counts: { ...COUNTS, missing: 2 },
}), async page => {
  const fix = page.locator('[data-group="fix"]');
  assert.equal((await fix.innerText()).replace(/\s+/g, ' '), 'Booking thiếu ngày 3');
  assert.equal(await fix.evaluate(el => el.closest('.bk-row').classList.contains('bk-info')), true, 'không đụng tiền: nằm ở hàng để biết');
  await fix.click();
  assert.equal(await page.locator('#bk-headrow').innerText(), 'Container\tÔ ngày trong booking\tTab nguồn\tBooking / số xe\tChủ hàng\tViệc');
  const rows = await page.locator('#bk-body tr').allInnerTexts();
  assert.equal(rows.length, 3);
  assert.ok(rows[0].includes('OERU4400262') && rows[0].includes('THÁNG 08/2026 dòng 41') && rows[0].includes('BK8') && rows[0].includes('CHU HANG GIA'), rows[0]);
  assert.ok(rows[2].includes('trống') && rows[2].includes('CONT_BO dòng 91') && rows[2].includes('Bộ'), rows[2]);
  assert.equal(await page.locator('#bk-filter-name').innerText(), 'Tab nguồn');
  await page.locator('#bk-book').selectOption('CONT_BO');
  assert.equal(await page.locator('#bk-body tr').count(), 1);
  assert.equal(await page.locator('#bk-list-name').innerText(), 'Booking thiếu ngày · 1 / 3');
  await page.locator('[data-group="missing"]').click();
  assert.equal(await page.locator('#bk-filter-name').innerText(), 'Sổ');
  assert.ok((await page.locator('#bk-headrow').innerText()).startsWith('Container\tNgày trên sổ'));
  const missing = await page.locator('#bk-body tr').allInnerTexts();
  assert.ok(missing[0].includes('booking có 2 chuyến container này trong 45 ngày quanh đó, sổ có 1 dòng'), missing[0]);
  assert.ok(missing[1].includes('sổ không có dòng nào của container này trong 45 ngày quanh đó'), missing[1]);
  await page.locator('[data-group="nodate"]').click();
  assert.ok((await page.locator('#bk-body tr').innerText()).includes('Sổ không ghi ngày, ghi ở khối tháng sau'));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
}));

// DU-CHUYEN-01: phía sổ web (tiêu chí số 1) là mặc định khi API có `web_check`; dòng mang mã sổ web nên có link không cần ghép tên.
const WEB_ROWS = [
  { group: 'missing', code: 'CHUA_TINH', tab: null, row: null, month: '2026-05', date: null, container: 'MISU3333333', amount_vnd: null,
    source: src('2026-05-20', 'BO', 'KHO GIA'), suggest: { tab: 'SO WEB TEN KHAC', from: '2025-08' }, pair: null, paired: false, near: { booking: 1, sheet: 0 } },
  { group: 'nosource', code: 'KHONG_NGUON', tab: 'SO WEB TEN KHAC', row: 'legacy:5', customer_id: 42, month: '2026-03', date: '2026-03-02',
    container: 'NONU4444444', amount_vnd: '12000000', source: null, pair: null, paired: false },
  { group: 'recent', code: 'THANG_CUOI', tab: null, row: null, month: '2026-11', date: null, container: 'NEWU3333333', amount_vnd: null,
    source: src('2026-11-04'), suggest: null, pair: null, paired: false },
];
const WEB = {
  version: 1, state: 'ok', now: NOW, compare: 'web', checked_at: '2026-11-13T10:15:00+07:00', window: { BIEN: '2025-12', BO: '2025-08', end: '2026-11' },
  booking: { trips: 7692, on_web: 7621 }, web: { rows: 7749, paired: 7619 }, counts: { dup: 0, missing: 1, other: 0, nosource: 1, date: 0, nodate: 0, recent: 1 },
  rows: WEB_ROWS, booking_fix: [],
};

test('Kiểm booking: mặc định so sổ web; đếm chuyến booking đã có trên web; tên nhóm nói web; chuyển sang Sheet rồi về', () => withPage(ok({ web_check: WEB }), async page => {
  assert.equal(await page.locator('#bk-title').innerText(), 'Kiểm sổ với booking');
  assert.equal(await page.locator('#bk-sides').isVisible(), true);
  assert.equal(await page.locator('[data-side="web"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await status(page), 'Lượt 10:15 hôm nay · 7.621/7.692 chuyến booking đã có trên sổ web');
  assert.ok((await page.locator('#bk-scope').innerText()).includes('tiêu chí số 1'));
  const groups = (await page.locator('.bk-group').allInnerTexts()).map(text => text.replace(/\s+/g, ' '));
  assert.deepEqual(groups, ['Booking có, web chưa có 1', 'Nghi tính hai lần 0', 'Sổ khác khách booking 0', 'Trên web, booking không có 1',
    'Lệch ngày 0', 'Web thiếu ngày 0', 'Tháng này, web chưa có 1', 'Booking thiếu ngày 0']);
  await page.locator('[data-group="nosource"]').click();
  assert.equal(await page.locator('#bk-body tr a').getAttribute('href'), '/so-khach-v7-live.html?customer=42&month=2026-03', 'mã sổ có sẵn, không cần ghép tên');
  assert.ok(!(await page.locator('#bk-body tr').innerText()).includes('legacy:5'), 'không lộ mã dòng nội bộ');
  await page.locator('[data-group="recent"]').click();
  const recent = await page.locator('#bk-body tr').innerText();
  assert.ok(recent.includes('Web chưa có'), recent);
  assert.equal(await page.locator('#bk-body tr a', { hasText: 'xem lý do' }).getAttribute('href'), '/bao-cao-thang.html?month=2026-11&webchua=1');
  await page.locator('[data-side="sheet"]').click();
  assert.equal(await page.locator('[data-side="sheet"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('#bk-list').isVisible(), false, 'đổi phía thì đóng danh sách đang mở');
  assert.equal(await status(page), 'Lượt 10:14 hôm nay · 7.308/7.641 dòng chuyến khớp booking');
  assert.ok((await page.locator('.bk-group').allInnerTexts()).some(text => text.includes('Booking có, sổ chưa tính')));
  await page.locator('[data-side="web"]').click();
  assert.ok((await status(page)).includes('chuyến booking đã có trên sổ web'));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
}));

test('Kiểm booking: phía sổ web chưa có lượt nào thì nói rõ, không hiện như ổn; API cũ không có web_check thì không có nút chọn', async () => {
  await withPage(ok({ web_check: { state: 'none', now: NOW } }), async page => {
    assert.ok((await status(page)).startsWith('Chưa có lượt kiểm nào'));
    assert.equal(await page.locator('#bk-groups').isVisible(), false);
    await page.locator('[data-side="sheet"]').click();
    assert.ok((await status(page)).includes('dòng chuyến khớp booking'));
  });
  await withPage(ok({ web_check: { state: 'none', now: NOW, last_error: { at: '2026-11-13T10:15:00+07:00', reason: 'WEB_EMPTY' } } }), async page => {
    assert.ok((await status(page)).includes('đọc sổ web không thấy dòng chuyến nào'));
  });
  await withPage(ok(), async page => {
    assert.equal(await page.locator('#bk-sides').isVisible(), false);
  });
});

test('Kiểm booking: chưa có lượt, lượt lỗi, kết quả cũ, không tải được đều không hiện như "không có gì lệch"', async () => {
  await withPage({ state: 'none', now: NOW }, async page => {
    assert.ok((await status(page)).startsWith('Chưa có lượt kiểm nào'));
    assert.equal(await page.locator('#bk-status').getAttribute('class'), 'bk-status warn');
    assert.equal(await page.locator('#bk-groups').isVisible(), false);
  });
  await withPage({ state: 'none', now: NOW, last_error: { at: '2026-11-13T10:13:00+07:00', reason: 'ROAD_STALE' } }, async page => {
    assert.equal(await status(page), 'Lượt kiểm 10:13 hôm nay lỗi: bản chụp CONT_BO cũ quá 3 giờ. Chưa có kết quả nào.');
    assert.equal(await page.locator('#bk-status').getAttribute('class'), 'bk-status bad');
  });
  const zero = { ...COUNTS, dup: 0, missing: 0, nosource: 0 };
  await withPage(ok({ state: 'error', counts: zero, last_error: { at: '2026-11-13T11:13:00+07:00', reason: 'SEA_MISSING' } }), async page => {
    const text = await status(page);
    assert.ok(text.includes('lỗi: chưa có bản chụp CONT_NGUON') && text.includes('của lượt 10:14 hôm nay, có thể cũ'), text);
    assert.ok(!text.includes(CLEAN));
    assert.equal(await page.locator('#bk-groups').isVisible(), true);
  });
  await withPage(ok({ state: 'stale', counts: zero, checked_at: '2026-11-12T15:14:00+07:00' }), async page => {
    const text = await status(page);
    assert.ok(text.startsWith('Lượt kiểm gần nhất 15:14 ngày 12/11') && !text.includes(CLEAN), text);
  });
  await withPage(ok({ state: 'error', last_error: { at: '2026-11-13T11:13:00+07:00', reason: 'NEW_CODE' } }), async page => {
    assert.ok((await status(page)).includes('lỗi: mã NEW_CODE'));
  });
  await withPage(null, async page => {
    assert.ok((await status(page)).startsWith('Không tải được'));
    assert.equal(await page.locator('#bk-groups').isVisible(), false);
  });
  await withPage(ok({ counts: zero, rows: ROWS.filter(row => row.group === 'nodate') }), async page => {
    assert.ok((await status(page)).includes(CLEAN));
    assert.equal(await page.locator('#bk-status').getAttribute('class'), 'bk-status ok');
  });
});

test('Kiểm booking: chữ từ Sheet không chèn được HTML; tên dài và khổ điện thoại không tràn ngang, nút đủ to', () => withPage(ok({
  rows: [{ ...ROWS[0], tab: '<img src=x onerror=alert(1)>', source: src('2026-03-10', 'BIEN', '<b>CHU</b> RAT DAI '.repeat(8)) }, ROWS[1], ROWS[2]],
}), async page => {
  await page.locator('[data-group="dup"]').click();
  assert.equal(await page.locator('#bk-body img, #bk-body b').count(), 0);
  assert.ok((await page.locator('#bk-body').innerText()).includes('<img src=x'));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), 'không tràn ngang');
  const low = await page.evaluate(() => [...document.querySelectorAll('.bk-group')].filter(el => el.getBoundingClientRect().height < 40).length);
  assert.equal(low, 0);
}, { width: 420, height: 800 }));
