// Việc cần làm (KIEM-TONG-01): dòng tab TONG dưới dòng đầu trang, danh sách mở tại chỗ. Dữ liệu giả, không tên hay số dư thật.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

const LONG = 'Mẫu 长城果业 Trường Thành tên khách rất dài để thử xuống dòng';
const customers = [['Mẫu Đông Á', 7], ['Mẫu An Phát', 1], ['Mẫu Phú Gia', 3], [LONG, 12]].map(([name, id]) => ({ id, name, commodity: 'Chuối', transport_mode: 'CANG' }));
const lech = { customer: 'Mẫu Đông Á', customer_id: 7, status: 'LECH_TONG', reason: 'NO_EXACT_FIX', difference_vnd: '-64200000', web_total_vnd: '5210000000',
  sheet_total_vnd: '5274200000', web_ahead_vnd: '0', groups: [] };
// Đông Á: TONG khác sổ (và sổ đang lệch Sheet). An Phát, tên dài: TONG để trống. Phú Gia: TONG ghi tên khác, số khớp tới đồng. Một tên lạ.
const problems = { month: '2026-10', matched: 64, tong_sum_vnd: '48000000000', expected_sum_vnd: '48326660000', gap_vnd: '-326660000',
  differs: [{ name: 'Mẫu Đông Á', book: 7, tong_vnd: '5200000000', expected_vnd: '5210000000' }],
  blank_on_tong: [{ book: 12, name: LONG, expected_vnd: '-95300000' }, { book: 1, name: 'Mẫu An Phát', expected_vnd: '412000000' }, { book: 3, name: 'Mẫu Phú Gia', expected_vnd: '123456789' }],
  unknown_names: [{ name: 'MẪU PHÚ GIA - DỪA', end_vnd: '123456789' }, { name: 'MẪU TÊN LẠ', end_vnd: '40000' }] };
const matchedAll = { month: '2026-10', matched: 78, differs: [], unknown_names: [], blank_on_tong: [], tong_sum_vnd: '48000000000', expected_sum_vnd: '48000000000', gap_vnd: '0' };
const reconcile = tong => ({ version: 1, checked_at: '2026-11-06T10:12:00+07:00', mode: 'fix', counts: { KHOP: 238, LECH_TONG: 1 }, total: 239, matched_web_vnd: '88',
  all_web_vnd: '100', months_differ: [], outside_tabs: [], matched_ids: [1, 3], customers: [lech], ...(tong === undefined ? {} : { tong }) });
const inbox = tong => ({ state: 'ready', sheet_at: '2026-11-06T03:15:00Z', computed_at: '2026-11-06T03:16:00Z', failed: [], reconcile: reconcile(tong), auto: {}, books: [] });
const statement = { customer_id: 7, version: 3, web_vnd: '5210000000', sheet_total_vnd: '5274200000', checked_at: '2026-11-06T10:12:00+07:00', reason: 'NO_EXACT_FIX',
  web_ahead_vnd: '0', shuffled_months: [], groups: [] };
const dashboard = { as_of: '2026-11-06', todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] },
  today: { trips: 0, receipts: 0, voids: 0, received_vnd: '0', by_actor: [] } };

function serverFor(tong) {
  return http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const send = (status, body) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (route.startsWith('/api/v7/presence')) return send(200, { people: [] });
    if (route === '/api/v7/inbox') return send(200, inbox(tong));
    if (route === '/api/v7/sheet/doi-chieu') return send(200, statement);
    if (route === '/api/v7/activity') return send(200, { day: '2026-11-06', today: '2026-11-06', prev_day: null, next_day: null, total: 0, events: [], trips: [], receipts: [], legacy_rows: [], fee_types: [] });
    if (route === '/api/v7/dashboard') return send(200, dashboard);
    if (route === '/api/v7/dashboard/debt') return send(200, { customers: [] });
    if (route === '/api/v7/customers') return send(200, { customers });
    if (route.startsWith('/api/')) return send(404, {});
    const file = path.join(__dirname, path.basename(route));
    if (!fs.existsSync(file)) return send(404, {});
    res.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.css') ? 'text/css' : 'text/javascript' });
    res.end(fs.readFileSync(file));
  });
}
async function withPage(tong, fn, { width = 1280, height = 560 } = {}) {
  const server = serverFor(tong);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.clock.setFixedTime(new Date('2026-11-06T10:15:00+07:00'));
    await page.goto(`http://127.0.0.1:${server.address().port}/viec-can-lam.html`);
    await page.locator('.viec-status').waitFor();
    await fn(page);
  } finally { await browser.close(); server.close(); }
}
const noSideScroll = page => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);

if (process.argv.includes('--preview')) {
  const port = Number(process.env.UX_PREVIEW_PORT ?? 18769);
  serverFor(problems).listen(port, '127.0.0.1', () => process.stdout.write(`Fixture preview: http://127.0.0.1:${port}/viec-can-lam.html\n`));
} else {
  test('TONG chưa cộng đủ: một dòng dưới dòng đầu trang, bấm ra danh sách việc trên Sheet theo thứ tự', async () => withPage(problems, async page => {
    const line = page.locator('.tong-line');
    assert.match(await line.innerText(), /Tab TONG tháng 10 thiếu 326,7 tr so với các sổ[\s\S]*2 sổ để trống · 1 dòng khác sổ · 1 tên lạ · 1 tên khác tên tab[\s\S]*Xem 5 dòng/);
    const [title, button] = await Promise.all([line.locator('strong').boundingBox(), page.locator('[data-tong-toggle]').boundingBox()]);
    assert.ok(Math.abs(title.y - button.y) < 12, `dòng TONG vừa một dòng ở 1280: ${title.y} / ${button.y}`);
    assert.doesNotMatch(await page.locator('.status-line').first().innerText(), /TONG/, 'có dòng riêng thì dòng đầu không nói lại');
    const toggle = page.locator('[data-tong-toggle]');
    assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
    assert.equal(await page.locator('.tong-list').count(), 0);
    await toggle.click();
    assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
    assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute('data-tong-toggle')), true, 'vẽ lại vẫn giữ chỗ đang bấm');
    const rows = await page.locator('.tong-table tbody tr').allInnerTexts();
    assert.equal(rows.length, 5);
    assert.match(rows[0], /Mẫu Đông Á[\s\S]*5\.200[\s\S]*5\.210[\s\S]*Sổ này đang lệch Sheet/);
    assert.match(rows[1], /Mẫu An Phát[\s\S]*trống[\s\S]*412[\s\S]*Ô TONG trống: điền số theo sổ/);
    assert.match(rows[2], /长城果业[\s\S]*trống[\s\S]*−95,3/);
    assert.match(rows[3], /MẪU TÊN LẠ[\s\S]*40\.000 đ[\s\S]*—[\s\S]*không ứng sổ nào/);
    assert.match(rows[4], /Mẫu Phú Gia[\s\S]*Trên TONG: MẪU PHÚ GIA - DỪA[\s\S]*123,5[\s\S]*123,5[\s\S]*chỉ khác tên/);
    assert.equal(await page.locator('.tong-table a').count(), 4, 'mỗi dòng có sổ thì mở được sổ; tên lạ thì không');
    assert.match(await page.locator('.tong-list .inbox-note').innerText(), /Cộng TONG tháng 10: 48\.000 tr\. Cộng các sổ quy về cuối tháng 10: 48\.326,7 tr\. 64 dòng TONG khớp sổ/);
    assert.equal(await noSideScroll(page), true, 'không tràn ngang ở 1280 khi mở danh sách');
    if (process.env.UX_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.UX_SCREENSHOTS, 'viec-tong-mo-1280.png'), fullPage: true });
    await toggle.click();
    assert.equal(await page.locator('.tong-list').count(), 0);
    assert.match(await toggle.innerText(), /Xem 5 dòng/);
  }));

  test('màn thấy 1280×560: dòng đầu, dòng TONG, ba tab và khách lệch đều trong màn khi danh sách đóng', async () => withPage(problems, async page => {
    await page.locator('.dc-customer').first().waitFor();
    for (const selector of ['.viec-status', '.tong-line', '.viec-tabs', '.dc-customer >> nth=0']) {
      const box = await page.locator(selector).boundingBox();
      assert.ok(box && box.y + box.height <= 560, `${selector} nằm trong màn: ${box?.y}+${box?.height}`);
    }
    assert.equal(await noSideScroll(page), true);
    if (process.env.UX_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.UX_SCREENSHOTS, 'viec-tong-1280.png') });
  }));

  test('màn hẹp: trang không tràn ngang, bảng TONG cuộn trong khung', async () => withPage(problems, async page => {
    await page.locator('[data-tong-toggle]').click();
    assert.equal(await noSideScroll(page), true);
    assert.equal(await page.locator('.tong-list .work-scroll').evaluate(node => node.scrollWidth > node.clientWidth), true);
  }, { width: 390, height: 720 }));

  test('TONG khớp đủ, chưa đọc được, lỗi, quá nhiều khách lệch, chưa có kết quả: chỉ một ý trong dòng đầu hoặc không nói gì', async () => {
    const cases = [[matchedAll, /TONG tháng 10 khớp/], [{ ...matchedAll, unknown_names: [{ name: 'MẪU B - DỪA', end_vnd: '99' }], blank_on_tong: [{ book: 3, name: 'Mẫu Phú Gia', expected_vnd: '99' }] }, /TONG tháng 10 khớp, 1 tên khác tên tab/],
      [{ month: null, skipped: 'TONG_KHONG_DOC_DUOC' }, /chưa đọc được tab TONG/], [{ month: null, skipped: 'ERROR', error: 'KeyError' }, /lượt này chưa kiểm được tab TONG/],
      [{ month: null, skipped: 'TOO_MANY_DIFFERENT' }, null], [undefined, null]];
    for (const [tong, expected] of cases) {
      await withPage(tong, async page => {
        assert.equal(await page.locator('.tong-line').count(), 0, 'không có dòng riêng');
        const line = await page.locator('.status-line').first().innerText();
        if (expected) assert.match(line, expected);
        else assert.doesNotMatch(line, /TONG/);
        assert.doesNotMatch(line, /KeyError|TONG_KHONG_DOC_DUOC|TOO_MANY/, 'không lộ mã kỹ thuật');
      });
    }
  });
}
