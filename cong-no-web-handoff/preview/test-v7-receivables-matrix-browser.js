const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const root = __dirname;
const currentYear = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric' }).format(new Date()));
const matrix = year => ({
  as_of: currentYear + '-10-26', year, years_available: [currentYear - 1, currentYear, currentYear + 1],
  customers: [{ customer_id: 1, name: 'Khách A', commodity: 'Sầu riêng', transport_mode: 'CẢNG',
    months: year === currentYear ? { '1': '100000', '2': '-20000', ...Object.fromEntries(Array.from({length:10}, (_, i) => [String(i + 3), '0'])) } : Object.fromEntries(Array.from({length:12}, (_, i) => [String(i + 1), '0'])),
    total_year_vnd: year === currentYear ? '80000' : '0', total_all_vnd: '80000', oldest_open_month: currentYear + '-01-01' },
  { customer_id: 2, name: 'Khách B', commodity: null, transport_mode: null,
    months: year === currentYear ? { '1': '100', '2': '-100', ...Object.fromEntries(Array.from({length:10}, (_, i) => [String(i + 3), '0'])) } : Object.fromEntries(Array.from({length:12}, (_, i) => [String(i + 1), '0'])),
    total_year_vnd: '0', total_all_vnd: '0', oldest_open_month: currentYear + '-01-01' }],
  grand_total_year_vnd: year === currentYear ? '80000' : '0', grand_total_all_vnd: '80000'
});
// Tháng có số dư đầu: dòng sổ gốc và chuyến web cùng hiện; phát sinh/đã thu như Sổ khách, thu phân bổ khác đã thu.
const ledger = { status: 'active', month: currentYear + '-01-01', outstanding_vnd: '100000', charges_vnd: '150000', received_vnd: '50000', allocated_vnd: '0',
  trips: [{ month: currentYear + '-01-01', event_date: currentYear + '-01-03', container: 'FAKE001', unit_price_vnd: '100000', other_fee_vnd: null, amount_vnd: '100000', historical: false },
    { month: currentYear + '-01-01', event_date: currentYear + '-01-02', container: 'FAKE-GOC', unit_price_vnd: '50000', other_fee_vnd: null, amount_vnd: '50000', historical: true }], opening: true, receipts: [] };
// Tháng web: phát sinh − thu đã trừ = còn lại; có phụ phí; chuyến thiếu giá và chờ kiểm không vào tổng.
const ledgerFeb = { status: 'active', month: currentYear + '-02-01', outstanding_vnd: '-20000', charges_vnd: '10000', received_vnd: '30000', allocated_vnd: '30000', opening: false,
  receipts: [{ pid: 'PH-001', date: currentYear + '-02-10', reference: 'FAKE-REF', amount_vnd: '30000', counterparty_name: null,
    allocations: [{ month: currentYear + '-01-01', kind: 'debt', amount_vnd: '20000' }, { month: currentYear + '-02-01', kind: 'advance', amount_vnd: '10000' }] }],
  trips: [{ event_date: currentYear + '-02-06', container: 'FAKE-D', status: 'pending_review', unit_price_vnd: '7000', other_fee_vnd: null, amount_vnd: '7000', historical: false },
    { event_date: currentYear + '-02-05', container: 'FAKE-B', status: 'confirmed', unit_price_vnd: '5000', other_fee_vnd: '5000', amount_vnd: '10000', historical: false },
    { event_date: currentYear + '-02-04', container: 'FAKE-C', status: 'confirmed', unit_price_vnd: null, other_fee_vnd: null, amount_vnd: null, historical: false }] };

function server({ matrixStatus = 200, matrixPayload = matrix, detail = month => month.endsWith('-02-01') ? ledgerFeb : ledger } = {}) {
  return http.createServer((req, res) => {
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname === '/api/v7/receivables/matrix') return send(matrixStatus, 'application/json', JSON.stringify(matrixPayload(Number(url.searchParams.get('year')))));
    if (url.pathname === '/api/v7/receivables/detail') return send(200, 'application/json', JSON.stringify(detail(url.searchParams.get('month'))));
    const file = path.join(root, url.pathname.replace(/^\//, ''));
    if (!file.startsWith(root) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    send(200, file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript', fs.readFileSync(file));
  });
}

test('real matrix page loads API data, validates totals, changes year, filters and opens ledger detail', async () => {
  const app = server();
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto('http://127.0.0.1:' + app.address().port + '/cong-no-theo-thang.html');
    await page.locator('#heat-body .khach').first().waitFor();
    const layout = await page.evaluate(() => {
      const months = [...document.querySelectorAll('#heat-head th.mh')].map(th => Math.round(th.getBoundingClientRect().width));
      const [year, all] = document.querySelectorAll('#heat-head th.tot');
      const wrap = document.querySelector('.table-wrap');
      return { months, equal: new Set(months).size === 1, innerScroll: wrap.scrollHeight > wrap.clientHeight + 1 || wrap.scrollWidth > wrap.clientWidth + 1,
        pageScrollX: document.documentElement.scrollWidth > innerWidth, separated: year.getBoundingClientRect().right <= all.getBoundingClientRect().left + 1 };
    });
    // Mockup v4.1 (duyệt 29/10/2026): 12 cột tháng rộng bằng nhau, bảng không có khung cuộn riêng ở 1280px.
    assert.equal(layout.months.length === 12 && layout.equal && !layout.innerScroll && !layout.pageScrollX && layout.separated, true, JSON.stringify(layout));
    assert.equal(await page.locator('#heat-head th.mh').first().innerText(), 'Tháng 1');
    // Audit UX 31/10/2026 (P0-6): ô và cột tổng ghi số triệu đồng không kèm đơn vị (không còn "tr"); đơn vị ghi một lần ở tiêu đề.
    assert.match(await page.locator('#heat-head th.khach').innerText(), /^Khách\s+Đơn vị: triệu đồng$/);
    assert.equal(await page.locator('.cell-btn[data-id="1"][data-month="1"]').innerText(), '0,1');
    assert.deepEqual(await page.locator('#heat-body tr[data-row="1"] td.tot').allInnerTexts(), ['0,08', '0,08']);
    assert.match(await page.locator('#scope-receivable').innerText(), /80\.000 đ/);
    assert.match(await page.locator('#recon').innerText(), /Khớp/);
    assert.equal(await page.locator('.neg[data-id="1"]').innerText(), 'dư 0,02');
    assert.equal(await page.locator('.neg[data-id="1"]').getAttribute('title'), '20.000 đ (dư)');
    assert.match(await page.locator('#heat-body .group').first().innerText(), /Sầu riêng · cảng/);
    assert.equal(await page.locator('#heat-body a[href="/so-khach-v7-live.html?customer=1"]').count(), 1);
    await page.locator('#only-open').check();
    assert.doesNotMatch(await page.locator('#heat-body').innerText(), /Khách B/);
    await page.locator('#only-open').uncheck();
    assert.match(await page.locator('#heat-body').innerText(), /Khách B/);
    if (process.env.SHOTS_DIR) {
      fs.mkdirSync(process.env.SHOTS_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'receivables-matrix-1280.png'), fullPage: true });
    }
    await page.locator('#year-next').click();
    await page.waitForFunction(y => document.querySelector('#year-cur').textContent === String(y), currentYear + 1);
    assert.equal(await page.locator('#year-cur').innerText(), String(currentYear + 1));
    await page.locator('#year-prev').click();
    await page.waitForFunction(y => document.querySelector('#year-cur').textContent === String(y), currentYear);
    await page.locator('#find').fill('Không tồn tại');
    assert.match(await page.locator('#heat-body').innerText(), /Không có khách phù hợp/);
    await page.locator('#find').fill('Khách A');
    await page.locator('.cell-btn[data-id="1"]').first().click();
    await page.locator('#drawer-body .mini-table').waitFor();
    // Tháng sổ gốc: chuyến xếp theo ngày dd/mm, không cột phụ phí khi tháng không có, dòng tổng khớp phát sinh.
    // Dòng sổ gốc lẫn dòng web: tách hai nhóm thay cho nhãn "sổ gốc" từng dòng (nhãn làm bảng tràn ngang).
    assert.deepEqual(await page.locator('#drawer-body tr.part').allInnerTexts(), ['Theo sổ gốc (đã nằm trong số dư đầu) · 1 chuyến', 'Nhập trên web · 1 chuyến']);
    const rows = await page.locator('#drawer-body table:not(.receipts) tbody tr:not(.part)').allInnerTexts();
    assert.match(rows[0], /^02\/01\s+FAKE-GOC\s+50\.000$/);
    assert.match(rows[1], /^03\/01\s+FAKE001\s+100\.000$/);
    assert.deepEqual(await page.locator('#drawer-body table:not(.receipts) thead th').allInnerTexts(), ['Ngày', 'Container', 'Thành tiền (đ)']);
    assert.match(await page.locator('#drawer-body table:not(.receipts) tfoot').innerText(), /Tổng 2 chuyến\s+150\.000/);
    const sum = await page.locator('#drawer-sum').innerText();
    assert.match(sum, /Phát sinh trong tháng\s+150\.000 đ/);
    // Tháng không thành phép tính: hiện thẳng đã thu, bỏ dòng "thu đã trừ 0 đ" dễ hiểu nhầm là khách chưa trả.
    assert.match(sum, /Đã thu trong tháng\s+50\.000 đ/);
    assert.doesNotMatch(sum, /Thu đã trừ vào nợ/);
    assert.match(sum, /Còn lại tháng này\s+100\.000 đ/);
    assert.match(sum, /số dư đầu theo sổ gốc/);
    assert.doesNotMatch(sum, /[−=]\s*\n/);
    assert.doesNotMatch(await page.locator('#drawer').innerText(), /không có dòng chuyến|không khớp|chênh/);
    assert.doesNotMatch(await page.locator('#drawer-body').innerText(), /Phiếu thu|Không có phiếu thu/);
    assert.equal(await page.locator('#drawer-ledger').getAttribute('href'), '/so-khach-v7-live.html?customer=1');
    assert.equal(await page.locator('#drawer-month').innerText(), 'Tháng 1/' + currentYear);
    assert.equal(await page.locator('.cell-btn.active').getAttribute('data-month'), '1');
    // Ngăn kéo không chặn bảng: bấm ô khác thì đổi tháng; tháng web hiện phép tính, phụ phí và chuyến chưa tính.
    await page.locator('.cell-btn[data-id="1"][data-month="2"]').click();
    await page.locator('#drawer-body').getByText('FAKE-B').waitFor();
    assert.equal(await page.locator('#drawer-month').innerText(), 'Tháng 2/' + currentYear);
    assert.equal(await page.locator('.cell-btn.active').getAttribute('data-month'), '2');
    const feb = await page.locator('#drawer-sum').innerText();
    assert.match(feb, /−\s+Thu đã trừ vào nợ tháng này\s+30\.000 đ/);
    assert.match(feb, /=\s+Còn lại tháng này\s+−20\.000 đ/);
    assert.deepEqual(await page.locator('#drawer-body table:not(.receipts) thead th').allInnerTexts(), ['Ngày', 'Container', 'Đơn giá', 'Phụ phí', 'Thành tiền (đ)']);
    // Màn 1280: bảng chuyến có phụ phí vừa ngăn kéo, không cuộn ngang.
    assert.equal(await page.locator('#drawer-body').evaluate(el => el.scrollWidth <= el.clientWidth), true);
    assert.equal(await page.locator('#drawer-body tr.part').count(), 0);
    const febRows = await page.locator('#drawer-body table:not(.receipts) tbody tr').allInnerTexts();
    assert.match(febRows[0], /^04\/02\s+FAKE-C\s+—\s+—\s+chưa có giá$/);
    assert.match(febRows[2], /FAKE-D\s+chờ kiểm/);
    assert.match(await page.locator('#drawer-body table:not(.receipts) tfoot').innerText(), /Tổng 1 chuyến có tính\s+10\.000/);
    assert.match(await page.locator('#drawer-body').innerText(), /2 chuyến chờ kiểm hoặc chưa có giá/);
    // Phiếu thu của tháng: kỳ được trừ theo nợ cũ trước, phần trả trước ghi rõ; tổng phiếu bằng đã thu nên không báo chênh.
    assert.deepEqual(await page.locator('#drawer-body table.receipts tbody tr').allInnerTexts(), ['10/02\tPH-001 · FAKE-REF\t30.000\tT1, trả trước']);
    assert.match(await page.locator('#drawer-body table.receipts tfoot').innerText(), /Tổng 1 phiếu\s+30\.000/);
    assert.doesNotMatch(await page.locator('#drawer-body').innerText(), /Chênh/);
    await page.locator('#drawer-prev').click();
    await page.locator('#drawer-body').getByText('FAKE001').waitFor();
    assert.equal(await page.locator('#drawer-prev').isDisabled(), true);
    assert.equal(await page.locator('.cell-btn.active').getAttribute('data-month'), '1');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#drawer').isHidden(), true);
    assert.equal(await page.locator('.cell-btn[data-id="1"][data-month="1"]').evaluate(el => el === document.activeElement && !el.classList.contains('active')), true);
    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      nodes: [...document.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > innerWidth + 1 && getComputedStyle(el).position !== 'sticky').slice(0, 8).map(el => [el.tagName, el.className, Math.round(el.getBoundingClientRect().right)]) }));
    assert.equal(overflow.scrollWidth <= overflow.width, true, JSON.stringify(overflow));
    if (process.env.SHOTS_DIR) await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'receivables-matrix-390.png'), fullPage: true });
    await page.locator('.table-wrap').evaluate(el => { el.scrollLeft = el.scrollWidth; });
    const mobileTotals = await page.evaluate(() => {
      const wrap = document.querySelector('.table-wrap').getBoundingClientRect();
      const [year, all] = [...document.querySelectorAll('#heat-head th.tot')].map(th => th.getBoundingClientRect());
      return { visible: year.left >= wrap.left && all.right <= wrap.right + 1, separated: year.right <= all.left + 1 };
    });
    assert.equal(mobileTotals.visible && mobileTotals.separated, true, JSON.stringify(mobileTotals));
  } finally {
    await browser.close();
    app.close();
  }
});
// CAN-DU-01: khoản dư tháng âm cấn vào tháng còn nợ cũ nhất; ngăn kéo cộng trừ đủ để ra đúng ô ma trận.
test('drawer explains credit applied from or to other months', async () => {
  const cells = { '1': '0', '2': '0', '3': '129000', ...Object.fromEntries(Array.from({length:9}, (_, i) => [String(i + 4), '0'])) };
  const zero = Object.fromEntries(Array.from({length:12}, (_, i) => [String(i + 1), '0']));
  const credited = year => ({ ...matrix(year), customers: [{ ...matrix(year).customers[0], months: year === currentYear ? cells : zero,
    total_year_vnd: year === currentYear ? '129000' : '0', total_all_vnd: '129000', oldest_open_month: currentYear + '-03-01' }],
    grand_total_year_vnd: year === currentYear ? '129000' : '0', grand_total_all_vnd: '129000' });
  const month = (key, extra) => ({ status: 'active', month: currentYear + key, received_vnd: '0', allocated_vnd: '0', opening: false, receipts: [], trips: [], ...extra });
  const app = server({ matrixPayload: credited, detail: key => key.endsWith('-02-01')
    ? month('-02-01', { outstanding_vnd: '0', charges_vnd: '-271000', credit_applied_vnd: '-271000' })
    : month('-03-01', { outstanding_vnd: '129000', charges_vnd: '300000', credit_applied_vnd: '171000' }) });
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:' + app.address().port + '/cong-no-theo-thang.html');
    await page.locator('.cell-btn[data-id="1"][data-month="3"]').click();
    await page.locator('#drawer-sum').getByText('Tiền khách dư tháng khác cấn vào').waitFor();
    const march = await page.locator('#drawer-sum').innerText();
    assert.match(march, /−\s+Tiền khách dư tháng khác cấn vào\s+171\.000 đ/);
    assert.match(march, /=\s+Còn lại tháng này\s+129\.000 đ/);
    assert.doesNotMatch(await page.locator('#drawer').innerText(), /không khớp|Còn lại khác/);
    await page.locator('#drawer-prev').click();
    await page.locator('#drawer-sum').getByText('Khoản dư đã cấn sang tháng còn nợ').waitFor();
    const feb = await page.locator('#drawer-sum').innerText();
    assert.match(feb, /\+\s+Khoản dư đã cấn sang tháng còn nợ\s+271\.000 đ/);
    assert.match(feb, /=\s+Còn lại tháng này\s+0 đ/);
  } finally { await browser.close(); app.close(); }
});
test('matrix rejects missing money evidence from API', async () => {
  const app = server({ matrixPayload: year => ({ ...matrix(year), customers: [{ ...matrix(year).customers[0], months: {} }] }) });
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:' + app.address().port + '/cong-no-theo-thang.html');
    await page.locator('#error').waitFor({ state: 'visible' });
    assert.match(await page.locator('#error').innerText(), /Số liệu ma trận không hợp lệ nên chưa hiện\. Báo người quản trị kiểm tra nguồn số liệu\./);
    assert.doesNotMatch(await page.locator('#error').innerText(), /API/);
    assert.equal(await page.locator('#heat-body tr').count(), 0);
  } finally { await browser.close(); app.close(); }
});
// Audit UX 31/10/2026 (P1-6): mất mạng khi tải chỉ hiện một câu tiếng Việt "chuyện gì · cần làm gì" và nút Thử lại tải lại.
test('matrix network error: Vietnamese sentence, never the browser string; Thử lại loads the table', async () => {
  const app = server();
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.route('**/api/v7/receivables/matrix*', route => route.abort('failed'));
    await page.goto('http://127.0.0.1:' + app.address().port + '/cong-no-theo-thang.html');
    await page.locator('#error').waitFor({ state: 'visible' });
    const text = await page.locator('#error').innerText();
    assert.match(text, /^Không tải được ma trận công nợ\. Kiểm tra mạng rồi bấm Thử lại\.\s*Thử lại$/);
    assert.doesNotMatch(text, /fetch|TypeError|HTTP/i);
    await page.unroute('**/api/v7/receivables/matrix*');
    await page.locator('#error').getByRole('button', { name: 'Thử lại' }).click();
    await page.locator('#heat-body .khach').first().waitFor();
    assert.equal(await page.locator('#error').isHidden(), true);
  } finally { await browser.close(); app.close(); }
});
test('matrix refresh reads new data while preserving selected year', async () => {
  let total = '80000';
  const app = server({ matrixPayload: year => {
    const data = matrix(year);
    if (year !== currentYear) return data;
    data.customers[0].months['1'] = String(Number(total) + 20000);
    data.customers[0].total_year_vnd = total;
    data.customers[0].total_all_vnd = total;
    data.grand_total_year_vnd = total;
    data.grand_total_all_vnd = total;
    return data;
  } });
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:' + app.address().port + '/cong-no-theo-thang.html');
    await page.locator('#heat-foot').getByText('0,08').first().waitFor();
    total = '80001';
    await page.locator('#refresh-data').click();
    await page.locator('#scope-receivable').getByText('80.001 đ').waitFor();
    assert.equal(await page.locator('#year-cur').innerText(), String(currentYear));
    assert.match(await page.locator('#updated-at').innerText(), /Cập nhật .* tự tải mỗi 60 giây/);
  } finally { await browser.close(); app.close(); }
});

test('mở từ Tổng quan (?tuoi=&con-no=1): tô cột tháng của nhóm tuổi, chỉ khách còn nợ, bỏ chọn nhóm', async () => {
  const month = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', month: 'numeric' }).format(new Date()));
  const diff = month - 1;
  const age = diff <= 0 ? 0 : diff <= 2 ? 1 : diff <= 6 ? 2 : 3;
  const app = server();
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto('http://127.0.0.1:' + app.address().port + '/cong-no-theo-thang.html?tuoi=' + age + '&con-no=1');
    await page.locator('#heat-body .khach').first().waitFor();
    assert.equal(await page.locator('#age-pick').isVisible(), true);
    assert.equal(await page.locator('#only-open').isChecked(), true);
    assert.ok((await page.locator('#heat-head th.mh.pick').allInnerTexts()).includes('Tháng 1'));
    assert.doesNotMatch(await page.locator('#heat-body').innerText(), /Khách B/);
    assert.match(await page.locator('#heat-body').innerText(), /Khách A/);
    await page.locator('#age-clear').click();
    assert.equal(await page.locator('#age-pick').isHidden(), true);
    assert.equal(await page.locator('#heat-head th.mh.pick').count(), 0);
    assert.doesNotMatch(await page.evaluate(() => location.search), /tuoi=/);
  } finally {
    await browser.close();
    app.close();
  }
});

test('mở từ Tổng quan (?xep=con-no&khach=): bỏ nhóm mặt hàng, nợ nhiều nhất trước, tô dòng khách; đổi lại nhóm', async () => {
  const zero = Object.fromEntries(Array.from({ length: 12 }, (_, i) => [String(i + 1), '0']));
  const one = (id, name, commodity, value) => ({ customer_id: id, name, commodity, transport_mode: commodity ? 'CẢNG' : null,
    months: { ...zero, '1': value }, total_year_vnd: value, total_all_vnd: value, oldest_open_month: currentYear + '-01-01' });
  // Nhóm Sầu riêng · cảng (A 80.000 + D 30.000) đứng trước Chuối (C 50.000); xếp theo nợ thì C lên giữa A và D.
  const payload = year => ({ as_of: currentYear + '-10-26', year, years_available: [currentYear],
    customers: year === currentYear ? [one(1, 'Khách A', 'Sầu riêng', '80000'), one(3, 'Khách C', 'Chuối', '50000'), one(4, 'Khách D', 'Sầu riêng', '30000')] : [],
    grand_total_year_vnd: year === currentYear ? '160000' : '0', grand_total_all_vnd: year === currentYear ? '160000' : '0' });
  const app = server({ matrixPayload: payload });
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto('http://127.0.0.1:' + app.address().port + '/cong-no-theo-thang.html?con-no=1&xep=con-no&khach=3');
    await page.locator('#heat-body .khach').first().waitFor();
    assert.equal(await page.locator('#sort').inputValue(), 'debt');
    assert.equal(await page.locator('#heat-body tr.group').count(), 0);
    assert.deepEqual(await page.locator('#heat-body td.khach a').allInnerTexts(), ['Khách A', 'Khách C', 'Khách D']);
    assert.equal(await page.locator('#heat-body tr.focus').getAttribute('data-row'), '3');
    assert.match(await page.locator('#heat-foot').innerText(), /Tổng 3 khách/);
    await page.locator('#sort').selectOption('group');
    assert.equal(await page.locator('#heat-body tr.group').count(), 2);
    assert.deepEqual(await page.locator('#heat-body td.khach a').allInnerTexts(), ['Khách A', 'Khách D', 'Khách C']);
    assert.doesNotMatch(await page.evaluate(() => location.search), /xep=/);
    await page.locator('#sort').selectOption('debt');
    assert.match(await page.evaluate(() => location.search), /xep=con-no/);
  } finally {
    await browser.close();
    app.close();
  }
});
