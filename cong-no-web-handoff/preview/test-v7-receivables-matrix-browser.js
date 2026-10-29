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
const ledger = { status: 'active', month: currentYear + '-01-01', outstanding_vnd: '100000', charges_vnd: '100000', received_vnd: '0', trips: [{ month: currentYear + '-01-01', event_date: currentYear + '-01-03', container: 'FAKE001', unit_price_vnd: '100000', other_fee_vnd: null, amount_vnd: '100000' }], opening: false };

function server({ matrixStatus = 200, matrixPayload = matrix } = {}) {
  return http.createServer((req, res) => {
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname === '/api/v7/receivables/matrix') return send(matrixStatus, 'application/json', JSON.stringify(matrixPayload(Number(url.searchParams.get('year')))));
    if (url.pathname === '/api/v7/receivables/detail') return send(200, 'application/json', JSON.stringify(ledger));
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
    assert.match(await page.locator('#scope-receivable').innerText(), /80\.000 đ/);
    assert.match(await page.locator('#recon').innerText(), /Khớp/);
    assert.equal(await page.locator('.neg[data-id="1"]').innerText(), 'dư 20.000 đ');
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
    assert.match(await page.locator('#drawer-body').innerText(), /FAKE001/);
    await page.locator('#drawer-close').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('#drawer a[href]').evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Escape');
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
test('matrix rejects missing money evidence from API', async () => {
  const app = server({ matrixPayload: year => ({ ...matrix(year), customers: [{ ...matrix(year).customers[0], months: {} }] }) });
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:' + app.address().port + '/cong-no-theo-thang.html');
    await page.locator('#error').waitFor({ state: 'visible' });
    assert.match(await page.locator('#error').innerText(), /Dữ liệu tiền từ API không hợp lệ/);
    assert.equal(await page.locator('#heat-body tr').count(), 0);
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
    await page.locator('#heat-foot').getByText('80.000 đ').first().waitFor();
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
