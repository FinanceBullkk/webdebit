const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared } = require('./shared-browser.js');

// BANG-THU-01: Bảng thu — tiền về theo ngày, gom mọi sổ, chỉ xem. Dữ liệu giả, mọi số tiền lấy nguyên từ API.
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
const customers = [{ id: 7, name: 'SỔ A', commodity: 'SẦU RIÊNG', transport_mode: null }, { id: 8, name: 'SỔ B', commodity: 'CHUỐI', transport_mode: null },
  { id: 9, name: '陈氏贸易有限公司 RẤT DÀI TÊN KHÁCH ĐỂ THỬ BỐ CỤC', commodity: null, transport_mode: null }];
const box = (id, ready, review, amount, extra) => ({ customer_id: id, receipts: { ready, review, amount_vnd: amount }, ...extra });

function makeServer({ book, inbox = { state: 'ready', books: [box(7, 2, 0, '50000000'), box(8, 0, 1, '35000000'), box(9, 5, 0, '1000', { sheet_matched: true })] }, bookStatus = () => 200, calls = [] }) {
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
    if (route === '/api/v7/customers') return out({ customers });
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

test('Bảng thu: hôm nay, tháng này, gom theo ngày, mới nhất trên cùng, tổng từng ngày', () => withPage({ book: byMonth }, async page => {
  await page.locator('tr.pay').first().waitFor();
  assert.equal(await page.locator('nav a.active').innerText(), 'Bảng thu');
  const fig = await page.locator('#fig-today').innerText();
  assert.match(fig, /Hôm nay 04\/11/);
  assert.match(fig, /120\.000\.000 đ/);
  assert.match(fig, /1 phiếu/);
  const month = await page.locator('#fig-month').innerText();
  assert.match(month, /Tháng 11\/2026/);
  assert.match(month, /608\.500\.000 đ/);
  assert.match(month, /3 phiếu · 3 khách/);
  assert.deepEqual((await page.locator('.day-head th').allInnerTexts()).map(text => text.replace(/\s+/g, ' ')),
    ['Hôm nay 04/11 1 phiếu', 'Hôm qua 03/11 1 phiếu', '01/11 1 phiếu']);
  assert.deepEqual(await page.locator('.day-head td.num').allInnerTexts(), ['120.000.000', '400.000.000', '88.500.000']);
  const first = await page.locator('tr.pay').first().locator('td').allInnerTexts();
  assert.deepEqual(first, ['SỔ A · SẦU RIÊNG', '120.000.000', 'CK VCB', 'T8, T9']);
  // Tháng khác năm ghi kèm năm; ứng trước ghi chữ; hình thức khác THU TIỀN ghi vào ghi chú.
  assert.equal(await page.locator('tr.pay').nth(1).locator('.debt').innerText(), 'T12/2025');
  const advance = page.locator('tr.pay').nth(2);
  assert.equal(await advance.locator('.debt').innerText(), 'ứng trước');
  assert.equal(await advance.locator('.note').innerText(), 'KHÁC');
  assert.equal(await page.locator('tr.pay').first().locator('.debt').getAttribute('title'), 'T8/2026 70.000.000 · T9/2026 50.000.000');
  assert.equal(await page.locator('#as-of').innerText(), 'Số liệu đến 04/11/2026');
  assert.equal(await page.locator('#fig-undated').count(), 0);
  assert.equal(await page.locator('#sheet-note').count(), 0);
}));

test('Bảng thu: bấm một dòng mở sổ đúng khách, đúng tháng; Back về đúng tháng và cách xem', () => withPage({ book: byMonth, search: '?month=2026-07&xem=khach' }, async (page, base) => {
  await page.locator('tr.pay').first().waitFor();
  assert.equal(await page.locator('#view-khach').getAttribute('aria-pressed'), 'true');
  // Bấm ô số tiền bằng chuột như người thật: cả dòng là vùng bấm của link tên khách.
  const cell = await page.locator('tr.pay').first().locator('td.num').first().boundingBox();
  await page.mouse.click(cell.x + cell.width / 2, cell.y + cell.height / 2);
  await page.waitForURL('**/so-khach-v7-live.html**');
  assert.equal(page.url(), `${base}/so-khach-v7-live.html?customer=7&month=2026-06`);
  await page.goBack();
  await page.locator('tr.pay').first().waitFor();
  assert.equal(new URL(page.url()).search, '?month=2026-07&xem=khach');
  assert.equal(await page.locator('#view-khach').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('#month-pick').inputValue(), '2026-07');
}));

test('Bảng thu: dòng Sheet mở sổ ở tháng của khối, không phải tháng tiền về; không rõ ngày nằm riêng, không cộng', () => withPage({ book: byMonth, search: '?month=2026-07' }, async page => {
  await page.locator('tr.pay').first().waitFor();
  assert.equal(await page.locator('#fig-today').count(), 0);
  const row = page.locator('tbody.day').first().locator('tr.pay').first();
  assert.deepEqual(await row.locator('td').allInnerTexts(), ['SỔ A · SẦU RIÊNG', '150.000.000', '15/07/2026 tt', 'T6']);
  assert.equal(await row.locator('.debt').getAttribute('title'), 'Ghi ở khối 6/2026 trên Sheet');
  assert.match(await row.locator('a').getAttribute('href'), /customer=7&month=2026-06$/);
  assert.match(await page.locator('#fig-month').innerText(), /150\.000\.000 đ/);
  const undated = page.locator('#khong-ro-ngay');
  assert.match(await undated.locator('th').innerText(), /Không rõ ngày thu\s+2 phiếu, chưa cộng vào tổng tháng/);
  assert.equal(await undated.locator('.day-head td.num').innerText(), '40.000.000');
  assert.deepEqual(await undated.locator('tr.pay .note').allInnerTexts(), ['da tt', '']);
  assert.match(await page.locator('#fig-undated').innerText(), /40\.000\.000 đ\s*2 phiếu, chưa cộng/);
  assert.equal(await page.locator('a#fig-undated').getAttribute('href'), '#khong-ro-ngay');
  assert.match(await page.locator('#sheet-note').innerText(), /khác "Đã thu"/);
}));

test('Bảng thu: Theo khách xếp theo tiền; cột Không rõ ngày chỉ hiện khi có; NULL hiện —', () => withPage({ book: byMonth }, async page => {
  await page.locator('tr.pay').first().waitFor();
  await page.locator('#view-khach').click();
  assert.equal(new URL(page.url()).search, '?xem=khach');
  assert.deepEqual(await page.locator('.by-customer th').allInnerTexts(), ['Khách', 'Đã trả', 'Số lần', 'Trả gần nhất']);
  assert.deepEqual(await page.locator('tr.pay .row-link').allInnerTexts(), ['SỔ B · CHUỐI', 'SỔ A · SẦU RIÊNG', customers[2].name]);
  assert.deepEqual(await page.locator('tr.pay').first().locator('td').allInnerTexts(), ['SỔ B · CHUỐI', '400.000.000', '1', '03/11/2026']);
  await page.locator('#month-pick').selectOption('2026-07');
  await page.locator('.by-customer th', { hasText: 'Không rõ ngày' }).waitFor();
  assert.deepEqual(await page.locator('tr.pay').nth(1).locator('td').allInnerTexts(), ['SỔ B · CHUỐI', '—', '—', '30.000.000', '—']);
  assert.equal(await page.locator('a#fig-undated').count(), 0, 'không có nhóm để nhảy tới khi xem theo khách');
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
  const offsets = await page.locator('#offsets').innerText();
  assert.match(offsets, /Cấn trừ giữa hai sổ/);
  assert.match(offsets, /không phải tiền mới vào/);
  assert.match(offsets, /20\/07\/2026 · SỔ A · SẦU RIÊNG sang SỔ B · CHUỐI · 5\.000\.000/);
  assert.match(await page.locator('#voided').innerText(), /1 phiếu đã hủy, không tính tiền/);
  assert.doesNotMatch(await page.locator('#voided').innerText(), /77\.000\.000/);
  await page.locator('#void-toggle').click();
  const shown = await page.locator('#voided').innerText();
  assert.match(shown, /77\.000\.000/);
  assert.match(shown, /02\/07\/2026 · hủy 03\/07\/2026 · nhập trùng/);
  assert.equal(await page.locator('#void-toggle').getAttribute('aria-expanded'), 'true');
}));

test('Bảng thu: phiếu Sheet chưa ghi có một dòng dẫn sang Việc cần làm; sổ đã khớp Sheet không tính', () => withPage({ book: byMonth }, async page => {
  await page.locator('tr.pay').first().waitFor();
  const line = page.locator('a#pending');
  assert.equal((await line.innerText()).replace(/\s+/g, ' '), 'Còn 3 phiếu trên Sheet chưa ghi vào web · 85.000.000 đ ›');
  assert.equal(await line.getAttribute('href'), '/viec-can-lam.html');
}));

test('Bảng thu: không còn phiếu chờ thì không có dòng; không đọc được việc chờ thì nói rõ', async () => {
  await withPage({ book: byMonth, inbox: { state: 'ready', books: [box(7, 0, 0, '0')] } }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.equal(await page.locator('#pending').count(), 0);
  });
  await withPage({ book: byMonth, inbox: null }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.match(await page.locator('p#pending').innerText(), /Chưa kiểm được phiếu thu trên Sheet chờ ghi/);
  });
  await withPage({ book: byMonth, inbox: { state: 'unavailable' } }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.match(await page.locator('p#pending').innerText(), /Chưa kiểm được/);
  });
  // Vài phút đầu sau khi API khởi động lại: đang tính, không phải lỗi.
  await withPage({ book: byMonth, inbox: { state: 'computing', books: [] } }, async page => {
    await page.locator('tr.pay').first().waitFor();
    assert.match(await page.locator('p#pending').innerText(), /^Đang kiểm phiếu thu trên Sheet chờ ghi/);
  });
});

test('Bảng thu: hôm nay chưa có phiếu thì nói chữ, không hiện 0 đ', () => withPage({ book: () => {
  const book = november();
  book.summary = { ...book.summary, today_vnd: '0', today_count: 0 };
  return book;
} }, async page => {
  await page.locator('#fig-today').waitFor();
  assert.match(await page.locator('#fig-today').innerText(), /chưa có phiếu/);
  assert.doesNotMatch(await page.locator('#fig-today').innerText(), /0 đ/);
}));

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

test('Bảng thu: bố cục ở khung thấy thật 1280×560 có thanh cuộn: không cuộn ngang, chữ dài không vỡ, menu sáu mục nằm gọn', () => withPage({ book: () => {
  const book = november();
  const row = web(40, 9, 'SỔ C', '2026-11-04', '123456789012', 'GHI CHÚ RẤT DÀI '.repeat(12), Array.from({ length: 9 }, (_, n) => debt(`2026-0${n + 1}-01`, '1')));
  book.days[0].rows.push(row);
  return book;
} }, async page => {
  await page.locator('tr.pay').first().waitFor();
  // Headless không vẽ thanh cuộn 15px của Chrome Windows: thu khung lại đúng phần đó để đo.
  await page.setViewportSize({ width: 1265, height: 560 });
  const size = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  assert.ok(size.scroll <= size.client, `cuộn ngang: ${JSON.stringify(size)}`);
  const overflow = await page.locator('tr.pay .note').last().evaluate(node => ({ text: node.scrollWidth > node.clientWidth, height: node.closest('tr').getBoundingClientRect().height }));
  assert.ok(overflow.height <= 48, `dòng cao ${overflow.height}`);
  const links = page.locator('.app-nav nav a');
  assert.deepEqual((await links.allInnerTexts()).map(text => text.split('\n')[0]), ['Tổng quan', 'Công nợ theo tháng', 'Sổ khách', 'Bảng thu', 'Đòi nợ', 'Việc cần làm']);
  const last = await links.last().boundingBox();
  assert.ok(last.y + last.height <= 560, `mục cuối ra ngoài khung 560: ${last.y + last.height}`);
  // Vùng bấm của nút và dòng đủ lớn.
  for (const id of ['#month-older', '#month-pick', '#view-ngay', '#view-khach']) {
    assert.ok((await page.locator(id).boundingBox()).height >= 40, id);
  }
  assert.ok((await page.locator('tr.pay').first().boundingBox()).height >= 40);
  // Đầu trang gọn: dòng đầu danh sách nằm trong nửa trên khung.
  assert.ok((await page.locator('tr.pay').first().boundingBox()).y < 280);
}));

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
