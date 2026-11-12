const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// THONG-TIN-CTY-01: tab Thông tin cty, chỉ xem. Dữ liệu giả; trang không được gửi lệnh ghi nào ngoài presence.
const INFO = {
  available: true, read_at: '2026-11-12T07:05:00+00:00',
  accounts: [
    { id: 'a000000000001', title: 'ACCOUNT NUMBER INFORMATION\n(VND)\nNGAN HANG GIA', label: 'VND · NGAN HANG GIA', currency: 'VND', beneficiary: 'CONG TY GIA', address: '1 DUONG GIA',
      bank: 'TEST BANK', bank_address: '2 DUONG GIA', account: '1234567890', swift: null,
      lines: [{ label: '公司全称\nACC NAME', value: 'CONG TY GIA' }, { label: '银行名称\nBANK NAME', value: 'TEST BANK' }, { label: '银行账户\nACCOUNT NUMBER', value: '1234567890' }] },
    { id: 'a000000000002', title: '(USD) BANK B', label: 'USD · BANK B', currency: 'USD', beneficiary: 'TEST CO', address: null, bank: 'BANK B', bank_address: null,
      account: '000123', swift: 'TESTVNVX', lines: [{ label: 'ACCOUNT NUMBER', value: '000123' }, { label: 'SWIFT CODE', value: 'TESTVNVX' }] },
  ],
  customers: [
    { shipper: 'Công Ty Thử Một', invoice: 'CONG TY TNHH THU MOT\nMST: 0000000001\n' + 'Dia chi rat dai '.repeat(12), bank: 'NH Gia A\nSTK 111' },
    { shipper: '测试贸易', invoice: 'CE SHI TRADING CO.,LTD', bank: '' },
    ...Array.from({ length: 70 }, (_, index) => ({ shipper: `Khach Thu ${index + 3}`, invoice: `KHACH THU ${index + 3} CO.,LTD`, bank: '' })),
  ],
  counts: { accounts: 2, customers: 72 },
};

function makeServer(state) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body) => { response.writeHead(status, { 'Content-Type': type }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    state.calls.push(`${request.method} ${route}`);
    if (route === '/api/v7/company-info') return state.down ? out({ error: 'COMPANY_INFO_UNAVAILABLE', message: 'Không đọc được bản Thông tin cty của máy chủ.' }, 503) : out(state.info);
    if (route === '/api/v7/customers') return out({ customers: [] });
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 503);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(state, fn, { viewport = { width: 1265, height: 560 }, query = '' } = {}) {
  const shared = { calls: [], down: false, info: INFO, ...state };
  const server = makeServer(shared);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const context = await browser.newContext({ viewport });
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/thong-tin-cty.html${query}`);
    await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
    await fn(page, shared);
    assert.deepEqual(errors, []);
    assert.deepEqual(shared.calls.filter(call => call.startsWith('POST') && !call.includes('presence')), [], 'trang chỉ xem không gửi lệnh ghi');
  } finally {
    await browser.close();
    server.close();
  }
}

test('Thông tin cty: thẻ tài khoản, danh sách khách giới hạn 60, tìm bỏ dấu và chữ Hán, chép, giờ đọc Sheet', () => withPage({}, async page => {
  assert.equal(await page.locator('#read-at').innerText(), 'Theo Sheet lúc 14:05 12/11');
  assert.deepEqual(await page.locator('.ttc-account h3').allInnerTexts(), ['VND · NGAN HANG GIA', 'USD · BANK B']);
  assert.deepEqual(await page.locator('.ttc-account').first().locator('dt').allInnerTexts(), ['ACC NAME', 'BANK NAME', 'ACCOUNT NUMBER']);
  assert.equal(await page.locator('.ttc-customer').count(), 60);
  assert.equal(await page.locator('#customer-count').innerText(), '60 / 72 khách, gõ để tìm');
  assert.match(await page.locator('.ttc-customer').first().innerText(), /CONG TY TNHH THU MOT\nMST: 0000000001/);   // giữ xuống dòng

  await page.locator('#customer-filter').fill('cong ty thu mot');
  assert.equal(await page.locator('.ttc-customer').count(), 1);
  assert.equal(await page.locator('#customer-count').innerText(), '1 / 72 khách');
  assert.match(page.url(), /\?q=cong\+ty\+thu\+mot$/);
  await page.locator('#customer-filter').fill('0000000001');   // tìm cả trong khối hóa đơn (MST)
  assert.equal(await page.locator('.ttc-customer h3').innerText(), 'Công Ty Thử Một');
  await page.locator('#customer-filter').fill('测试');
  assert.equal(await page.locator('.ttc-customer h3').innerText(), '测试贸易');
  assert.match(await page.locator('.ttc-customer').first().locator('.ttc-block').last().innerText(), /^Ngân hàng của khách\s+—$/);
  await page.locator('#customer-filter').fill('khong ai ten nay');
  assert.match(await page.locator('#customers').innerText(), /Không có khách nào khớp/);

  await page.locator('.ttc-account .ttc-copy').first().click();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), '1234567890');
  assert.equal(await page.locator('.ttc-account .ttc-copy').first().innerText(), 'Đã chép');
  assert.equal(await page.locator('.app-nav a.active').innerText(), 'Thông tin cty');
}));

test('Thông tin cty: địa chỉ có ?q= thì tìm sẵn; chưa bật job thì báo; lỗi máy chủ thì báo và thử lại được', async () => {
  await withPage({}, async page => {
    assert.equal(await page.locator('#customer-filter').inputValue(), 'Khach Thu 10');
    assert.deepEqual(await page.locator('.ttc-customer h3').allInnerTexts(), ['Khach Thu 10']);
  }, { query: '?q=Khach%20Thu%2010' });
  await withPage({ info: { available: false } }, async page => {
    assert.match(await page.locator('#customers').innerText(), /Chưa có bản đọc từ Sheet/);
    assert.equal(await page.locator('.ttc-account').count(), 0);
  });
  await withPage({ down: true }, async (page, shared) => {
    assert.match(await page.locator('#error').innerText(), /Không đọc được bản Thông tin cty của máy chủ\. Bấm làm mới để thử lại\./);
    shared.down = false;
    await page.locator('#refresh-data').click();
    await page.locator('.ttc-account').first().waitFor();
    assert.equal(await page.locator('#error').isHidden(), true);
  });
});

test('Thông tin cty: khung 1265×560 có menu bảy mục lọt khung, không cuộn ngang; 390px xếp dọc, không cuộn ngang', async () => {
  await withPage({}, async page => {
    const last = await page.locator('.app-nav nav a').last().boundingBox();
    assert.ok(last.y + last.height <= 560, `mục cuối menu lọt khung: ${last.y + last.height}`);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    const search = await page.locator('.ttc-search').boundingBox(), account = await page.locator('.ttc-account').first().boundingBox();
    assert.ok(search.y < 140 && account.y < 140, `ô tìm và tài khoản thấy ngay: ${search.y}, ${account.y}`);
    assert.ok((await page.locator('#refresh-data').boundingBox()).height >= 40);
  });
  await withPage({}, async page => {
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    const customer = await page.locator('.ttc-customer').first().boundingBox(), account = await page.locator('.ttc-account').first().boundingBox();
    assert.ok(account.y > customer.y, 'tài khoản xuống dưới danh sách khách');
  }, { viewport: { width: 390, height: 844 } });
});
