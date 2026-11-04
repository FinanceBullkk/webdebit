const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared } = require('./shared-browser.js');

// BANG-THU-01, BANG-THU-02: Bảng thu — tiền về theo ngày, gom mọi sổ, chỉ xem, năm cách xem. Dữ liệu giả; số không lọc lấy nguyên từ API.
const AS_OF = '2026-11-04';
const web = (id, customer, name, date, amount, note, allocations, extra) => ({ source: 'web', id, pid: `PH-${id}`, customer_id: customer, name, date,
  book_month: `${(date ?? '2026-11-01').slice(0, 7)}-01`, amount_vnd: amount, method: 'THU TIỀN', note, allocations, ...extra });
const sheet = (id, customer, name, date, amount, note, block) => ({ source: 'sheet', id, pid: null, customer_id: customer, name, date,
  book_month: block, amount_vnd: amount, method: null, note, allocations: [] });
const debt = (month, amount) => ({ month, kind: 'debt', amount_vnd: amount });
const months = [
  { month: '2026-11-01', total_vnd: '608500000', count: 3, undated_vnd: '0', undated_count: 0 },
  { month: '2026-10-01', total_vnd: '300000000', count: 1, undated_vnd: '0', undated_count: 0 },
  { month: '2026-07-01', total_vnd: '150000000', count: 1, undated_vnd: '40000000', undated_count: 2 },
];
const november = () => ({ month: '2026-11-01', as_of: AS_OF, today_month: '2026-11-01', months,
  summary: { total_vnd: '608500000', count: 3, customers: 3, undated_vnd: '0', undated_count: 0, today_vnd: '120000000', today_count: 1, has_sheet: false },
  days: [
    { date: '2026-11-04', total_vnd: '120000000', count: 1, rows: [web(1, 7, 'SỔ A', '2026-11-04', '120000000', 'CK VCB', [debt('2026-08-01', '70000000'), debt('2026-09-01', '50000000')])] },
    { date: '2026-11-03', total_vnd: '400000000', count: 1, rows: [web(2, 8, 'SỔ B', '2026-11-03', '400000000', '3/11/2026 da tt', [debt('2025-12-01', '400000000')])] },
    { date: '2026-11-01', total_vnd: '88500000', count: 1, rows: [web(3, 9, 'SỔ C', '2026-11-01', '88500000', null, [{ month: '2026-11-01', kind: 'advance', amount_vnd: '88500000' }], { method: 'KHÁC' })] },
  ],
  undated: [],
  customers: [
    { customer_id: 8, name: 'SỔ B', total_vnd: '400000000', count: 1, undated_vnd: '0', undated_count: 0, last_date: '2026-11-03', book_month: '2026-11-01' },
    { customer_id: 7, name: 'SỔ A', total_vnd: '120000000', count: 1, undated_vnd: '0', undated_count: 0, last_date: '2026-11-04', book_month: '2026-11-01' },
    { customer_id: 9, name: 'SỔ C', total_vnd: '88500000', count: 1, undated_vnd: '0', undated_count: 0, last_date: '2026-11-01', book_month: '2026-11-01' },
  ],
  offsets: [], voided: [] });
const july = () => ({ month: '2026-07-01', as_of: AS_OF, today_month: '2026-11-01', months,
  summary: { total_vnd: '150000000', count: 1, customers: 1, undated_vnd: '40000000', undated_count: 2, today_vnd: '0', today_count: 0, has_sheet: true },
  days: [{ date: '2026-07-15', total_vnd: '150000000', count: 1, rows: [sheet(21, 7, 'SỔ A', '2026-07-15', '150000000', '15/07/2026 tt', '2026-06-01')] }],
  undated: [sheet(22, 8, 'SỔ B', null, '30000000', 'da tt', '2026-07-01'), sheet(23, 9, 'SỔ C', null, '10000000', null, '2026-07-01')],
  customers: [
    { customer_id: 7, name: 'SỔ A', total_vnd: '150000000', count: 1, undated_vnd: '0', undated_count: 0, last_date: '2026-07-15', book_month: '2026-06-01' },
    { customer_id: 8, name: 'SỔ B', total_vnd: '0', count: 0, undated_vnd: '30000000', undated_count: 1, last_date: null, book_month: '2026-07-01' },
    { customer_id: 9, name: 'SỔ C', total_vnd: '0', count: 0, undated_vnd: '10000000', undated_count: 1, last_date: null, book_month: '2026-07-01' },
  ],
  offsets: [{ id: 1, date: '2026-07-20', amount_vnd: '5000000', source_customer_id: 7, source_name: 'SỔ A', target_customer_id: 8, target_name: 'SỔ B' }],
  voided: [{ pid: 'PH-9', customer_id: 9, name: 'SỔ C', date: '2026-07-02', amount_vnd: '77000000', voided_on: '2026-07-03', void_reason: 'nhập trùng' }] });
const empty = () => ({ month: '2026-10-01', as_of: AS_OF, today_month: '2026-11-01', months,
  summary: { total_vnd: '0', count: 0, customers: 0, undated_vnd: '0', undated_count: 0, today_vnd: '0', today_count: 0, has_sheet: false },
  days: [], undated: [], customers: [], offsets: [], voided: [] });
const LONG_NAME = '陈氏贸易有限公司 RẤT DÀI TÊN KHÁCH ĐỂ THỬ BỐ CỤC';
const customers = [{ id: 7, name: 'SỔ A', commodity: 'Sầu riêng', transport_mode: 'CANG' }, { id: 8, name: 'SỔ B', commodity: 'Chuối', transport_mode: null },
  { id: 9, name: LONG_NAME, commodity: null, transport_mode: null }];
const box = (id, ready, review, amount, extra) => ({ customer_id: id, receipts: { ready, review, amount_vnd: amount }, ...extra });
const inboxReady = { state: 'ready', books: [box(7, 2, 0, '50000000'), box(8, 0, 1, '35000000'), box(9, 5, 0, '1000', { sheet_matched: true })] };

function makeServer({ book, inbox = inboxReady, bookStatus = () => 200, customersStatus = () => 200, calls = [], customerRows = customers }) {
  return http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const route = url.pathname;
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    if (route === '/api/v7/receipt-book') {
      calls.push(url.search);
      const status = bookStatus();
      return status === 200 ? out(book(url.searchParams.get('month'))) : out({ error: 'X' }, status);
    }
    if (route === '/api/v7/customers') return customersStatus() === 200 ? out({ customers: customerRows }) : out({}, 503);
    if (route === '/api/v7/inbox') return inbox ? out(inbox) : out({}, 503);
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 404);
    if (route === '/so-khach-v7-live.html') return send(200, 'text/html', '<!doctype html><title>Sổ</title><p id="so">sổ</p>');
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(options, fn) {
  const server = makeServer(options);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 560 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = `http://127.0.0.1:${server.address().port}`;
    await page.goto(`${base}/bang-thu.html${options.search ?? ''}`);
    await fn(page, base);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    server.close();
  }
}
const byMonth = month => (month === '2026-07-01' ? july() : month === '2026-10-01' ? empty() : november());
const clean = text => text.replace(/\s+/g, ' ').trim();
const cells = async row => (await row.locator('td').allInnerTexts()).map(clean);

test('Bảng thu: hôm nay, tháng này, gom theo ngày, mới nhất trên cùng, tổng từng ngày', () => withPage({ book: byMonth }, async page => {
  await page.locator('tr.pay').first().waitFor();
  assert.equal(await page.locator('nav a.active').innerText(), 'Bảng thu');
  const today = await page.locator('#fig-today').innerText();
  assert.match(today, /Hôm nay 04\/11/);
  assert.match(today, /120 tr/);
  assert.match(today, /1 phiếu/);
  assert.match(await page.locator('#fig-today b').getAttribute('data-tip'), /120\.000\.000 đ/);
  assert.match(await page.locator('#fig-month .lbl').innerText(), /^Thu tháng 11$/);
  assert.equal(await page.locator('.big-money').innerText(), '608,5 tr');
  assert.match(await page.locator('.big-money').getAttribute('data-tip'), /608\.500\.000 đ/);
  assert.match(clean(await page.locator('#pill-customers').innerText()), /^3/);
  assert.match(await page.locator('#pill-customers').getAttribute('data-tip'), /3 khách trả trong tháng/);
  assert.match(await page.locator('#pill-receipts').getAttribute('data-tip'), /3 phiếu có ngày thu/);
  assert.deepEqual((await page.locator('.group-head th').allInnerTexts()).map(clean), ['Hôm nay 04/11 1 phiếu', 'Hôm qua 03/11 1 phiếu', '01/11 1 phiếu']);
  assert.deepEqual(await page.locator('.group-head td.num').allInnerTexts(), ['120.000.000', '400.000.000', '88.500.000']);
  assert.deepEqual(await cells(page.locator('tr.pay').first()), ['SỔ A Sầu riêng · cảng', '120.000.000', 'CK VCB', 'T8, T9', '']);
  // Tháng khác năm ghi kèm năm; ứng trước ghi chữ; hình thức khác THU TIỀN ghi vào ghi chú.
  assert.equal(await page.locator('tr.pay').nth(1).locator('.debt').innerText(), 'T12/2025');
  const advance = page.locator('tr.pay').nth(2);
  assert.equal(await advance.locator('.debt').innerText(), 'ứng trước');
  assert.equal(await advance.locator('.note').innerText(), 'KHÁC');
  assert.equal(await page.locator('tr.pay').first().locator('.debt').getAttribute('title'), 'T8/2026 70.000.000 · T9/2026 50.000.000');
  assert.match(await page.locator('#as-of').getAttribute('data-tip'), /Số liệu đến 04\/11\/2026/);
  assert.match(await page.locator('#as-of').innerText(), /^\d{2}:\d{2}$/);
  assert.equal(await page.locator('#fig-undated').count(), 0);
  assert.equal(await page.locator('#sheet-note').count(), 0);
}));

test('Bảng thu: rê chuột vào số lớn thấy số đúng tới đồng; tab có chú thích', () => withPage({ book: byMonth }, async page => {
  await page.locator('tr.pay').first().waitFor();
  assert.equal(await page.locator('#tip').isHidden(), true);
  await page.locator('.big-money').hover();
  assert.match(clean(await page.locator('#tip').innerText()), /Thu tháng 11 608\.500\.000 đ/);
  await page.locator('#view-thang-no').hover();
  assert.match(clean(await page.locator('#tip').innerText()), /Tiền về tháng này trừ vào nợ tháng nào/);
  await page.locator('.list table').hover();
  assert.equal(await page.locator('#tip').isHidden(), true);
  await page.locator('#as-of').focus();
  assert.match(clean(await page.locator('#tip').innerText()), /Số liệu đến 04\/11\/2026/);
}));

test('Bảng thu: bấm một dòng mở sổ đúng khách, đúng tháng; Back về đúng tháng, tab và bộ lọc', () => withPage({ book: byMonth, search: `?month=2026-07&xem=khach&mh=${encodeURIComponent('Sầu riêng cảng')}` }, async (page, base) => {
  await page.locator('tr.pay').first().waitFor();
  assert.equal(await page.locator('#view-khach').getAttribute('aria-pressed'), 'true');
  // Bấm ô số tiền bằng chuột như người thật: cả dòng là vùng bấm của link tên khách.
  const cell = await page.locator('tr.pay').first().locator('td.num').first().boundingBox();
  await page.mouse.click(cell.x + cell.width / 2, cell.y + cell.height / 2);
  await page.waitForURL('**/so-khach-v7-live.html**');
  assert.equal(page.url(), `${base}/so-khach-v7-live.html?customer=7&month=2026-06`);
  await page.goBack();
  await page.locator('tr.pay').first().waitFor();
  assert.equal(new URL(page.url()).searchParams.get('xem'), 'khach');
  assert.equal(await page.locator('#view-khach').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('#month-pick').inputValue(), '2026-07');
  assert.equal(await page.locator('#com-filter').inputValue(), 'Sầu riêng cảng');
}));

test('Bảng thu: dòng Sheet mở sổ ở tháng của khối, không phải tháng tiền về; không rõ ngày nằm riêng, không cộng', () => withPage({ book: byMonth, search: '?month=2026-07' }, async page => {
  await page.locator('tr.pay').first().waitFor();
  assert.equal(await page.locator('#fig-today').count(), 0);
  const row = page.locator('tbody.day').first().locator('tr.pay').first();
  assert.deepEqual(await cells(row), ['SỔ A Sầu riêng · cảng', '150.000.000', '15/07/2026 tt', 'T6', '']);
  assert.equal(await row.locator('.debt').getAttribute('title'), 'Ghi ở khối 6/2026 trên Sheet');
  assert.match(await row.locator('a').getAttribute('href'), /customer=7&month=2026-06$/);
  assert.equal(await page.locator('.big-money').innerText(), '150 tr');
  const undated = page.locator('tbody.undated');
  assert.match(clean(await undated.locator('th').innerText()), /Không rõ ngày thu 2 phiếu/);
  assert.equal(await undated.locator('.group-head td.num').innerText(), '40.000.000');
  assert.equal(await undated.locator('.group-head .hint').innerText(), 'chưa cộng vào tổng tháng');
  assert.deepEqual(await undated.locator('tr.pay .note').allInnerTexts(), ['da tt', '']);
  assert.equal(clean(await page.locator('#fig-undated').innerText()), 'Không rõ ngày 40 tr');
  assert.match(await page.locator('#fig-undated').getAttribute('data-tip'), /2 phiếu không rõ ngày thu\n40\.000\.000 đ · chưa cộng vào tổng tháng/);
  assert.equal(await page.locator('a#fig-undated').getAttribute('href'), '#khong-ro-ngay');
  assert.match(await page.locator('#sheet-note').innerText(), /khác "Đã thu"/);
}));

test('Bảng thu: Theo khách xếp theo tiền, có thanh tỷ lệ; cột Không rõ ngày chỉ hiện khi có; NULL hiện —', () => withPage({ book: byMonth }, async page => {
  await page.locator('tr.pay').first().waitFor();
  await page.locator('#view-khach').click();
  assert.equal(new URL(page.url()).search, '?xem=khach');
  assert.deepEqual((await page.locator('.by-customer th').allInnerTexts()).map(clean).filter(Boolean), ['Khách', 'Phần trong tháng', 'Đã trả đ', 'Số lần', 'Trả gần nhất', 'Mở sổ']);
  assert.deepEqual((await page.locator('tr.pay .row-link').allInnerTexts()).map(clean), ['SỔ B Chuối', 'SỔ A Sầu riêng · cảng', LONG_NAME]);
  assert.deepEqual(await cells(page.locator('tr.pay').first()), ['SỔ B Chuối', '', '400.000.000', '1', '03/11/2026', '']);
  assert.equal(await page.locator('tr.pay').first().locator('.share').evaluate(node => node.style.width), '100%');
  assert.equal(await page.locator('tr.pay').nth(1).locator('.share').evaluate(node => node.style.width), '30%');
  await page.locator('#month-pick').selectOption('2026-07');
  await page.locator('.by-customer th', { hasText: 'Không rõ ngày' }).waitFor();
  assert.deepEqual(await cells(page.locator('tr.pay').nth(1)), ['SỔ B Chuối', '', '—', '—', '30.000.000', '—', '']);
  assert.equal(await page.locator('tr.pay').nth(1).locator('.share').count(), 0, 'sổ chỉ có khoản không rõ ngày thì không có thanh');
}));

test('Bảng thu: chip Không rõ ngày ở tab khác chuyển sang Theo ngày và tới đúng nhóm', () => withPage({ book: byMonth, search: '?month=2026-07&xem=khach' }, async page => {
  await page.locator('tr.pay').first().waitFor();
  await page.locator('#fig-undated').click();
  await page.locator('#khong-ro-ngay').waitFor();
  assert.equal(await page.locator('#view-ngay').getAttribute('aria-pressed'), 'true');
  assert.equal(new URL(page.url()).search, '?month=2026-07');
}));

test('Bảng thu: Theo mặt hàng gom sổ theo mặt hàng, nhóm nhiều tiền trước, tổng nhóm bằng tổng tháng', () => withPage({ book: byMonth, search: '?xem=mat-hang' }, async page => {
  await page.locator('.by-commodity tr.pay').first().waitFor();
  assert.equal(await page.locator('.by-commodity thead th').first().innerText(), 'Mặt hàng · khách');
  const heads = page.locator('.group-head');
  assert.deepEqual((await heads.locator('th').allInnerTexts()).map(clean), ['Chuối 1 khách', 'Sầu riêng cảng 1 khách', 'Chưa phân loại 1 khách']);
  assert.deepEqual(await heads.locator('td.num').allInnerTexts(), ['400.000.000', '1', '120.000.000', '1', '88.500.000', '1']);
  // Tên mặt hàng đã ở dòng nhóm, dòng sổ không lặp lại.
  assert.deepEqual((await page.locator('tr.pay .row-link').allInnerTexts()).map(clean), ['SỔ B', 'SỔ A', LONG_NAME]);
  assert.match(await page.locator('tr.pay').first().locator('a').getAttribute('href'), /customer=8&month=2026-11$/);
  // Nhóm và sổ chung một thước: sổ duy nhất của nhóm dài bằng thanh nhóm.
  const widths = await page.locator('.by-commodity .share').evaluateAll(nodes => nodes.map(node => node.style.width));
  assert.deepEqual(widths, ['100%', '100%', '30%', '30%', '22.1%', '22.1%']);
}));

test('Bảng thu: Theo mặt hàng, sổ trùng tên giữ số sổ; sầu riêng chưa ghi cảng/bộ nằm "Chưa phân loại" và giữ chữ để thấy vì sao', () => withPage({ book: byMonth, search: '?xem=mat-hang', customerRows: [
  { id: 7, name: 'SỔ A', commodity: 'Chuối', transport_mode: null }, { id: 8, name: 'SỔ A', commodity: 'Chuối', transport_mode: null }, { id: 9, name: 'SỔ C', commodity: 'Sầu riêng', transport_mode: null },
] }, async page => {
  await page.locator('.by-commodity tr.pay').first().waitFor();
  assert.deepEqual((await page.locator('.group-head th').allInnerTexts()).map(clean), ['Chuối 2 khách', 'Chưa phân loại 1 khách']);
  assert.deepEqual((await page.locator('tr.pay .row-link').allInnerTexts()).map(clean), ['SỔ A sổ 8', 'SỔ A sổ 7', 'SỔ C Sầu riêng']);
}));

test('Bảng thu: Theo tháng nợ tách đúng phần tiền, nợ cũ trước, ứng trước cuối; dòng mở sổ đúng tháng', () => withPage({ book: byMonth, search: '?xem=thang-no' }, async page => {
  await page.locator('.by-debt tr.pay').first().waitFor();
  assert.equal(await page.locator('.by-debt thead th').first().innerText(), 'Tháng nợ · khách');
  const heads = page.locator('.group-head');
  assert.deepEqual((await heads.locator('th').allInnerTexts()).map(clean), ['Nợ T12/2025 1 khách', 'Nợ T8 1 khách', 'Nợ T9 1 khách', 'Ứng trước 1 khách']);
  assert.deepEqual((await heads.locator('td.num').allInnerTexts()).filter((_, i) => i % 2 === 0), ['400.000.000', '70.000.000', '50.000.000', '88.500.000']);
  // Cùng phiếu 120 triệu của SỔ A tách vào hai tháng.
  assert.deepEqual(await cells(page.locator('tr.pay').nth(1)), ['SỔ A Sầu riêng · cảng', '', '70.000.000', '1', '04/11/2026', '']);
  assert.deepEqual(await cells(page.locator('tr.pay').nth(2)), ['SỔ A Sầu riêng · cảng', '', '50.000.000', '1', '04/11/2026', '']);
  assert.match(await page.locator('tr.pay').nth(2).locator('a').getAttribute('href'), /customer=7&month=2026-09$/);
  assert.match(await heads.last().getAttribute('title'), /vượt nợ/);
  assert.match(await page.locator('#realloc-note').innerText(), /phân bổ lại theo nợ cũ trước/);
  assert.equal(await page.locator('#view-thang-no').getAttribute('aria-pressed'), 'true');
}));

test('Bảng thu: Theo tháng nợ, dòng Sheet nằm ở tháng của khối, không rõ ngày tính riêng', () => withPage({ book: byMonth, search: '?month=2026-07&xem=thang-no' }, async page => {
  await page.locator('.by-debt tr.pay').first().waitFor();
  assert.deepEqual((await page.locator('.group-head th').allInnerTexts()).map(clean), ['Nợ T6 1 khách', 'Nợ T7 2 khách']);
  assert.deepEqual(await cells(page.locator('.group-head').first()), ['', '150.000.000', '1', '—', '']);
  assert.deepEqual(await cells(page.locator('.group-head').nth(1)), ['', '—', '—', '40.000.000', '']);
  assert.deepEqual(await cells(page.locator('tr.pay').nth(1)), ['SỔ B Chuối', '', '—', '—', '30.000.000', '—', '']);
}));

test('Bảng thu: 12 tháng đủ tháng liền, không có bộ lọc; bấm tháng mở Theo ngày của tháng đó, Back về lại', () => withPage({ book: byMonth, search: `?xem=12-thang&mh=${encodeURIComponent('Chuối')}` }, async (page, base) => {
  await page.locator('.by-year tbody tr').first().waitFor();
  assert.equal(await page.locator('.by-year tbody tr').count(), 12);
  assert.equal(await page.locator('#com-filter').count(), 0);
  const rows = page.locator('.by-year tbody tr');
  assert.deepEqual(await cells(rows.first()), ['T11/2026', '', '608.500.000', '—', '3', '']);
  assert.equal(await rows.first().getAttribute('aria-current'), 'true');
  assert.deepEqual(await cells(rows.nth(1)), ['T10/2026', '', '300.000.000', '—', '1', '']);
  assert.deepEqual(await cells(rows.nth(4)), ['T7/2026', '', '150.000.000', '40.000.000', '1', '']);
  // Tháng không có phiếu vẫn có dòng, không có link.
  assert.deepEqual(await cells(rows.nth(2)), ['T9/2026', '', '—', '—', '—', '']);
  assert.equal(await rows.nth(2).locator('a').count(), 0);
  // Số tháng và tháng đang chọn không lọc ở tab này.
  assert.equal(await page.locator('.big-money').innerText(), '608,5 tr');
  assert.match(await page.locator('#sheet-note').innerText(), /khác "Đã thu"/);
  await rows.nth(4).locator('a').click();
  await page.waitForURL(`${base}/bang-thu.html?month=2026-07&mh=**`);
  await page.locator('#view-ngay[aria-pressed="true"]').waitFor();
  assert.equal(await page.locator('#month-pick').inputValue(), '2026-07');
  assert.equal(await page.locator('#com-filter').inputValue(), 'Chuối', 'bộ lọc đi theo');
  await page.goBack();
  await page.locator('.by-year tbody tr').first().waitFor();
}));

test('Bảng thu: bộ lọc mặt hàng lọc cả số tháng, hôm nay, dải ngày, bảng, phiếu chờ; đổi tháng vẫn giữ; bỏ lọc về số server', () => withPage({ book: byMonth }, async page => {
  await page.locator('tr.pay').first().waitFor();
  assert.deepEqual(await page.locator('#com-filter option').allInnerTexts(), ['Mọi mặt hàng', 'Chuối', 'Sầu riêng cảng', 'Chưa phân loại']);
  // selectOption không tự đặt tiêu điểm như khi người dùng bấm vào ô.
  await page.locator('#com-filter').focus();
  await page.locator('#com-filter').selectOption('Sầu riêng cảng');
  await page.locator('#fig-month .lbl', { hasText: 'Sầu riêng cảng' }).waitFor();
  assert.equal(await page.locator('#fig-month .lbl').innerText(), 'Thu tháng 11 · Sầu riêng cảng');
  assert.equal(await page.locator('.big-money').innerText(), '120 tr');
  assert.match(await page.locator('#fig-today').innerText(), /120 tr/);
  assert.equal(await page.locator('tr.pay').count(), 1);
  assert.equal(await page.locator('#day-strip a').count(), 1);
  assert.equal(clean(await page.locator('a#pending').innerText()), '2 · 50 tr phiếu trên Sheet chưa ghi');
  assert.equal(new URL(page.url()).searchParams.get('mh'), 'Sầu riêng cảng');
  assert.equal(await page.locator('#com-filter').evaluate(node => node === document.activeElement), true, 'giữ tiêu điểm ở ô lọc');

  // Mặt hàng không có phiếu trong tháng thì nói rõ, không để trang trống.
  await page.locator('#month-pick').selectOption('2026-10');
  await page.locator('#empty').waitFor();
  assert.equal(await page.locator('#empty').innerText(), 'Không có phiếu Sầu riêng cảng trong tháng 10/2026.');
  assert.equal(await page.locator('.big-money').innerText(), '0 đ');
  await page.locator('#month-pick').selectOption('2026-07');
  await page.locator('#fig-month .lbl', { hasText: 'tháng 7' }).waitFor();
  assert.equal(await page.locator('.big-money').innerText(), '150 tr');
  assert.equal(await page.locator('#offsets').count(), 1, 'cấn trừ có một đầu thuộc mặt hàng này');
  assert.equal(await page.locator('#voided').count(), 0, 'phiếu hủy của sổ khác không hiện');

  await page.locator('#com-filter').selectOption('');
  await page.locator('#voided').waitFor();
  assert.equal(new URL(page.url()).searchParams.has('mh'), false);
}));

test('Bảng thu: link trỏ tới mặt hàng không còn thì bỏ lọc', () => withPage({ book: byMonth, search: '?mh=Khong-co' }, async page => {
  await page.locator('tr.pay').first().waitFor();
  assert.equal(await page.locator('#com-filter').inputValue(), '');
  assert.equal(await page.locator('.big-money').innerText(), '608,5 tr');
  assert.equal(new URL(page.url()).searchParams.has('mh'), false);
}));

test('Bảng thu: không đọc được danh sách khách thì số vẫn đúng, ẩn bộ lọc, Theo mặt hàng báo rõ; tải lại được thì hiện', () => {
  let status = 503;
  return withPage({ book: byMonth, customersStatus: () => status, search: `?xem=mat-hang&mh=${encodeURIComponent('Chuối')}` }, async page => {
    await page.locator('#no-commodity').waitFor();
    assert.match(await page.locator('#no-commodity').innerText(), /Chưa tải được danh sách mặt hàng/);
    assert.equal(await page.locator('#com-filter').count(), 0);
    assert.equal(await page.locator('.big-money').innerText(), '608,5 tr', 'không lọc khi chưa biết mặt hàng');
    await page.locator('#view-khach').click();
    assert.deepEqual((await page.locator('tr.pay .row-link').allInnerTexts()).map(clean), ['SỔ B', 'SỔ A', 'SỔ C'], 'tên lấy từ bảng thu');
    await page.locator('#view-mat-hang').click();
    status = 200;
    await page.locator('#refresh-data').click();
    await page.locator('.by-commodity').waitFor();
    assert.equal(await page.locator('#com-filter').inputValue(), 'Chuối', 'bộ lọc trên link có hiệu lực khi đã biết mặt hàng');
    assert.equal(await page.locator('.big-money').innerText(), '400 tr');
  });
});

test('Bảng thu: dải ngày chỉ ở Theo ngày; đủ ngày của tháng, bấm cột tới đúng ngày, không bị đầu bảng che', () => withPage({ book: () => {
  const book = july();
  const rows = Array.from({ length: 14 }, (_, i) => sheet(100 + i, 7, 'SỔ A', '2026-07-15', '1000000', `dòng ${i}`, '2026-06-01'));
  book.days = [{ date: '2026-07-20', total_vnd: '300000000', count: 1, rows: [sheet(99, 8, 'SỔ B', '2026-07-20', '300000000', '', '2026-06-01')] },
    { date: '2026-07-15', total_vnd: '14000000', count: 14, rows }, { date: '2026-07-02', total_vnd: '5000000', count: 1, rows: [sheet(98, 9, 'SỔ C', '2026-07-02', '5000000', '', '2026-06-01')] }];
  return book;
}, search: '?month=2026-07' }, async page => {
  await page.locator('tr.pay').first().waitFor();
  const strip = page.locator('#day-strip');
  assert.equal(await strip.locator('> *').count(), 31);
  assert.equal(await strip.locator('a').count(), 3);
  assert.equal(await strip.locator('a').nth(0).getAttribute('href'), '#ngay-2');
  assert.match(await strip.locator('a[href="#ngay-20"]').getAttribute('data-tip'), /300\.000\.000 đ · 1 phiếu/);
  assert.match(await strip.locator('a[href="#ngay-20"]').getAttribute('aria-label'), /^20\/07: 300\.000\.000 đ · 1 phiếu$/);
  // Cột cao theo ngày nhiều tiền nhất; ngày ít tiền vẫn thấy được.
  const heights = await strip.locator('a .bar').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().height));
  assert.equal(heights[0], 4);
  assert.equal(heights[2], 27);
  await strip.locator('a[href="#ngay-2"]').click();
  await page.waitForFunction(() => location.hash === '#ngay-2');
  const rows = await page.evaluate(() => {
    const row = document.getElementById('ngay-2').getBoundingClientRect();
    const head = document.querySelector('.thu thead th').getBoundingClientRect();
    return { rowTop: row.top, headBottom: head.bottom, viewport: innerHeight };
  });
  assert.ok(rows.rowTop >= rows.headBottom - 1, `đầu bảng che dòng ngày: ${JSON.stringify(rows)}`);
  assert.ok(rows.rowTop < rows.viewport);
  await page.locator('#view-khach').click();
  assert.equal(await page.locator('#day-strip').count(), 0);
}));

test('Bảng thu: dải ngày đánh dấu hôm nay, ngày chưa tới không bấm được', () => withPage({ book: byMonth }, async page => {
  await page.locator('#day-strip').waitFor();
  assert.equal(await page.locator('#day-strip > *').count(), 30);
  assert.equal(await page.locator('#day-strip .is-today').getAttribute('href'), '#ngay-4');
  assert.equal(await page.locator('#day-strip a.is-future').count(), 0);
  assert.match(await page.locator('#day-strip .is-future').first().getAttribute('data-tip'), /05\/11\nChưa tới/);
  assert.match(await page.locator('#day-strip > div').first().getAttribute('data-tip'), /02\/11\nKhông có phiếu/);
}));

test('Bảng thu: đổi tháng bằng ‹ › bỏ qua tháng không có phiếu, đầu và cuối thì khóa; tháng trống báo rõ', () => {
  const calls = [];
  return withPage({ book: byMonth, calls }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.equal(await page.locator('#month-newer').isDisabled(), true);
    assert.deepEqual(await page.locator('#month-pick option').allInnerTexts(), ['Tháng 11/2026', 'Tháng 10/2026', 'Tháng 07/2026']);
    assert.equal(calls[0], '');
    await page.locator('#month-older').click();
    await page.locator('#empty').waitFor();
    assert.equal(await page.locator('#empty').innerText(), 'Tháng 10/2026 chưa có phiếu thu.');
    assert.equal(calls.at(-1), '?month=2026-10-01');
    assert.equal(new URL(page.url()).search, '?month=2026-10');
    assert.equal(await page.locator('#month-older').evaluate(node => node === document.activeElement), true, 'giữ tiêu điểm sau khi vẽ lại');
    await page.locator('#month-older').click();
    await page.locator('#fig-undated').waitFor();
    assert.equal(await page.locator('#month-older').isDisabled(), true);
    assert.equal(await page.locator('#month-newer').evaluate(node => node === document.activeElement), true, 'nút vừa khóa thì tiêu điểm sang nút còn lại');
    await page.locator('#month-pick').selectOption('2026-11');
    await page.locator('#fig-today').waitFor();
  });
});

test('Bảng thu: cấn trừ liệt kê riêng; phiếu hủy gom một dòng, bấm Xem mới hiện lý do', () => withPage({ book: byMonth, search: '?month=2026-07' }, async page => {
  await page.locator('tr.pay').first().waitFor();
  const offsets = clean(await page.locator('#offsets').innerText());
  assert.match(offsets, /Cấn trừ giữa hai sổ, không cộng vào bảng/);
  assert.match(offsets, /20\/07\/2026 · SỔ A · Sầu riêng · cảng sang SỔ B · Chuối · 5\.000\.000/);
  assert.match(await page.locator('#voided').innerText(), /1 phiếu đã hủy, không tính tiền/);
  assert.doesNotMatch(await page.locator('#voided').innerText(), /77\.000\.000/);
  await page.locator('#void-toggle').click();
  const shown = clean(await page.locator('#voided').innerText());
  assert.match(shown, /77\.000\.000/);
  assert.match(shown, /02\/07\/2026 · hủy 03\/07\/2026 · nhập trùng/);
  assert.equal(await page.locator('#void-toggle').getAttribute('aria-expanded'), 'true');
}));

test('Bảng thu: phiếu Sheet chưa ghi là một chip dẫn sang Việc cần làm; sổ đã khớp Sheet không tính', () => withPage({ book: byMonth }, async page => {
  await page.locator('tr.pay').first().waitFor();
  const line = page.locator('a#pending');
  assert.equal(clean(await line.innerText()), '3 · 85 tr phiếu trên Sheet chưa ghi');
  assert.equal(await line.getAttribute('href'), '/viec-can-lam.html');
  assert.match(await line.getAttribute('data-tip'), /Còn 3 phiếu trên Sheet chưa ghi vào web\n85\.000\.000 đ · số ở đây có thể còn thiếu/);
}));

test('Bảng thu: không còn phiếu chờ thì không có chip; không đọc được việc chờ thì nói rõ', async () => {
  await withPage({ book: byMonth, inbox: { state: 'ready', books: [box(7, 0, 0, '0')] } }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.equal(await page.locator('#pending').count(), 0);
  });
  await withPage({ book: byMonth, inbox: null }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.equal(clean(await page.locator('span#pending').innerText()), 'Chưa kiểm được Sheet');
    assert.match(await page.locator('span#pending').getAttribute('data-tip'), /Số ở đây có thể còn thiếu/);
  });
  await withPage({ book: byMonth, inbox: { state: 'unavailable' } }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.equal(clean(await page.locator('span#pending').innerText()), 'Chưa kiểm được Sheet');
  });
  // Vài phút đầu sau khi API khởi động lại: đang tính, không phải lỗi.
  await withPage({ book: byMonth, inbox: { state: 'computing', books: [] } }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.equal(clean(await page.locator('span#pending').innerText()), 'Đang kiểm Sheet');
  });
});

test('Bảng thu: hôm nay chưa có phiếu thì nói chữ, không hiện 0 đ; tháng năm khác ghi kèm năm', async () => {
  await withPage({ book: () => {
    const book = november();
    book.summary = { ...book.summary, today_vnd: '0', today_count: 0 };
    return book;
  } }, async page => {
    await page.locator('#fig-today').waitFor();
    assert.match(await page.locator('#fig-today').innerText(), /Chưa có phiếu/);
    assert.doesNotMatch(await page.locator('#fig-today').innerText(), /0 đ/);
  });
  await withPage({ book: () => ({ ...empty(), month: '2025-12-01' }), search: '?month=2025-12' }, async page => {
    await page.locator('#empty').waitFor();
    assert.equal(await page.locator('#fig-month .lbl').innerText(), 'Thu tháng 12/2025');
    assert.equal(await page.locator('.big-money').evaluate(node => node.classList.contains('zero')), true);
  });
});

test('Bảng thu: tải lỗi thì báo và có Thử lại, không có chữ của trình duyệt; lỗi lúc tự tải vẫn giữ số cũ', () => {
  let status = 500;
  return withPage({ book: byMonth, bookStatus: () => status }, async page => {
    await page.locator('#error:not([hidden])').waitFor();
    assert.match(await page.locator('#error').innerText(), /Không tải được bảng thu\. Kiểm tra mạng rồi bấm Thử lại\./);
    assert.equal(await page.locator('#bang-thu tr.pay').count(), 0);
    status = 200;
    await page.locator('#retry').click();
    await page.locator('tr.pay').first().waitFor();
    assert.equal(await page.locator('#error').isHidden(), true);
    status = 500;
    await page.locator('#refresh-data').click();
    await page.locator('#error:not([hidden])').waitFor();
    assert.equal(await page.locator('#bang-thu tr.pay').count(), 3);
  });
});

test('Bảng thu: bố cục ở khung thấy thật 1280×560 có thanh cuộn: không cuộn ngang ở mọi tab, chữ dài không vỡ, menu sáu mục nằm gọn', () => withPage({ book: () => {
  const book = november();
  const row = web(40, 9, 'SỔ C', '2026-11-04', '123456789012', 'GHI CHÚ RẤT DÀI '.repeat(12), Array.from({ length: 9 }, (_, n) => debt(`2026-0${n + 1}-01`, '1')));
  book.days[0].rows.push(row);
  return book;
} }, async page => {
  await page.locator('tr.pay').first().waitFor();
  // Headless không vẽ thanh cuộn 15px của Chrome Windows: thu khung lại đúng phần đó để đo.
  await page.setViewportSize({ width: 1265, height: 560 });
  for (const view of ['ngay', 'khach', 'mat-hang', 'thang-no', '12-thang']) {
    await page.locator(`#view-${view}`).click();
    const size = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    assert.ok(size.scroll <= size.client, `cuộn ngang ở ${view}: ${JSON.stringify(size)}`);
    // Tiêu đề cột không bị cắt chữ.
    const cut = await page.locator('.thu thead th').evaluateAll(nodes => nodes.filter(node => node.scrollWidth > node.clientWidth).map(node => node.innerText));
    assert.deepEqual(cut, [], `cắt chữ tiêu đề ở ${view}`);
  }
  await page.locator('#view-ngay').click();
  const overflow = await page.locator('tr.pay .note').last().evaluate(node => ({ height: node.closest('tr').getBoundingClientRect().height }));
  assert.ok(overflow.height <= 48, `dòng cao ${overflow.height}`);
  const links = page.locator('.app-nav nav a');
  assert.deepEqual((await links.allInnerTexts()).map(text => text.split('\n')[0]), ['Tổng quan', 'Công nợ theo tháng', 'Sổ khách', 'Bảng thu', 'Đòi nợ', 'Việc cần làm']);
  const last = await links.last().boundingBox();
  assert.ok(last.y + last.height <= 560, `mục cuối ra ngoài khung 560: ${last.y + last.height}`);
  // Vùng bấm của nút và dòng đủ lớn.
  for (const id of ['#month-older', '#month-pick', '#refresh-data', '#view-ngay', '#view-khach', '#view-mat-hang', '#view-thang-no', '#view-12-thang', '#com-pick']) {
    assert.ok((await page.locator(id).boundingBox()).height >= 40, id);
  }
  assert.ok((await page.locator('tr.pay').first().boundingBox()).height >= 40);
  // Trong khung thấy thật, sau khối tiền về còn thấy được các dòng đầu của danh sách.
  assert.ok((await page.locator('tr.pay').first().boundingBox()).y < 360);
  assert.ok((await page.locator('tr.pay').nth(2).boundingBox()).y + 44 <= 560, 'thấy ít nhất ba dòng đầu');
}));

test('Bảng thu: màn hẹp không cuộn cả trang', () => withPage({ book: byMonth, search: '?month=2026-07' }, async page => {
  await page.locator('tr.pay').first().waitFor();
  await page.setViewportSize({ width: 420, height: 800 });
  for (const view of ['ngay', 'khach', 'mat-hang', 'thang-no', '12-thang']) {
    await page.locator(`#view-${view}`).click();
    const size = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    assert.ok(size.scroll <= size.client, `cuộn ngang ở ${view}: ${JSON.stringify(size)}`);
  }
}));

test('Bảng thu: đổi tab không tải lại dữ liệu; tải lại khi đổi tháng', () => {
  const calls = [];
  return withPage({ book: byMonth, calls }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.equal(calls.length, 1);
    for (const view of ['khach', 'mat-hang', 'thang-no', '12-thang', 'ngay']) await page.locator(`#view-${view}`).click();
    assert.equal(calls.length, 1);
    await page.locator('#month-pick').selectOption('2026-07');
    await page.locator('#fig-undated').waitFor();
    assert.equal(calls.length, 2);
  });
});

test('Bảng thu: dữ liệu thử có băng báo', () => withPage({ book: () => ({ ...november(), demo: true }) }, async page => {
  await page.locator('tr.pay').first().waitFor();
  assert.match(await page.locator('#demo-banner').innerText(), /Dữ liệu thử/);
}));

test('Menu riêng của Sổ khách cũng có Bảng thu và sáu mục lọt khung 1280×560', () => withPage({ book: byMonth }, async (page, base) => {
  const html = fs.readFileSync(path.join(__dirname, 'so-khach-v7-live.html'), 'utf8');
  const order = [...html.match(/<nav aria-label="Điều hướng chính">.*?<\/nav>/s)[0].matchAll(/<span>([^<]+)<\/span>/g)].map(match => match[1]);
  assert.deepEqual(order, ['Tổng quan', 'Công nợ theo tháng', 'Sổ khách', 'Bảng thu', 'Đòi nợ', 'Việc cần làm']);
  await page.goto(`${base}/test-fixture-none`);
  await page.setContent(`<!doctype html><link rel="stylesheet" href="${base}/so-khach-v7.css"><link rel="stylesheet" href="${base}/so-khach-v7-priority.css">${html.match(/<header class="topbar">.*?<\/header>/s)[0]}`);
  await page.waitForLoadState('load');
  const last = await page.locator('.topbar > nav a').last().boundingBox();
  assert.ok(last.y + last.height <= 560, `mục cuối ra ngoài khung 560: ${last.y + last.height}`);
}));
