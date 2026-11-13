// GIA-TUYEN-01 (specs/v7-gia-theo-tuyen.md): ghi giá theo tuyến ở Việc cần làm → Dọn chi tiết. Dữ liệu giả, máy chủ giả giữ
// phiên bản sổ như API thật: lệnh sai phiên bản bị trả STALE_LEDGER, lệnh đúng tăng phiên bản và trả phiên bản mới.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

const A = { origin: 'KHO MẪU A', destination: 'CẢNG MẪU 1' };
const B = { origin: 'KHO MẪU B - TRẠI ĐÓNG HÀNG SỐ 14 TÊN DÀI', destination: 'CẢNG MẪU 2 - BẾN XẾP DỠ PHÍA BẮC' };
const trip = (id, date, extra = {}) => ({ id, container: `MAUU${String(id).padStart(7, '0')}`, event_date: date, status: 'confirmed', unit_price_vnd: null,
  other_fee_vnd: null, editable: true, shipper: 'SHIP MẪU', ...A, ...extra });
function makeWorld() {
  return { version: 7, total: '679000000', keys: new Map(), trips: [
    trip(100, '2026-10-28', { unit_price_vnd: '45000000' }),   // đã có giá: "giá gần nhất" của tuyến A · SHIP MẪU
    trip(101, '2026-10-20', { unit_price_vnd: '44000000' }),
    trip(1, '2026-11-02'), trip(2, '2026-11-03'), trip(3, '2026-11-04', { other_fee_vnd: '500000' }), trip(4, '2026-11-05'),
    // Tuyến tên dài: hàng tuyến xuống dòng chứ không cắt (chữ trên Linux rộng hơn Segoe UI).
    ...[5, 6].map((id, i) => trip(id, `2026-11-0${3 + i * 3}`, { origin: B.origin, destination: B.destination })),
    trip(7, '2026-11-04', { origin: 'KHO MẪU C' }),
    trip(8, '2026-10-30', { editable: false }),                // tháng khóa: không vào hàng tuyến
    trip(9, '2026-11-07', { origin: null }),                    // thiếu nơi đi: không gom
    trip(10, '2026-11-08', { shipper: 'TT MẪU' }), trip(11, '2026-11-09', { shipper: 'TT MẪU' }),
  ] };
}
const ledgerOf = world => ({ version: world.version, total_outstanding_vnd: world.total, trips: world.trips, sheet_sync: { items: [], removed_items: [] }, sheet_prices: { ready: [], review: [] } });
const dashboard = { as_of: '2026-11-13', demo: true, todo: { missing_price: [{ customer_id: 2, count: 11 }], pending_review: [], no_baseline: [], credit: [] },
  today: { trips: 0, receipts: 0, voids: 0, received_vnd: '0', by_actor: [] } };
const inbox = { state: 'ready', sheet_at: '2026-11-13T02:00:00Z', computed_at: '2026-11-13T02:05:00Z', failed: [], books: [], auto: {} };
const customers = [{ id: 2, name: 'Công ty Mẫu Minh Châu 明珠', commodity: 'Chuối', transport_mode: 'CANG' }];

function serverFor(world, opts = {}) {
  return http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const send = (status, body, type = 'application/json') => { res.writeHead(status, { 'Content-Type': type }); res.end(type === 'application/json' ? JSON.stringify(body) : body); };
    if (route.startsWith('/api/v7/presence')) return send(200, { people: [] });   // nhịp "đang online" không phải lệnh ghi
    if (req.method === 'POST') {
      let raw = '';
      req.on('data', part => { raw += part; });
      req.on('end', () => {
        const body = JSON.parse(raw);
        opts.posted?.push({ route, body });
        const forced = opts.post?.(route, body, opts.posted.length);
        if (forced) return send(forced.status, forced.json);
        if (body.expected_version !== world.version) return send(409, { error: 'STALE_LEDGER', message: 'Sổ vừa thay đổi. Kiểm tra dữ liệu mới rồi thực hiện lại.' });
        if (route === '/api/v7/trips/price') {
          const row = world.trips.find(t => t.id === body.trip_id);
          world.keys.set(body.idempotency_key, { row, before: { unit_price_vnd: row.unit_price_vnd, other_fee_vnd: row.other_fee_vnd } });
          Object.assign(row, { unit_price_vnd: body.unit_price_vnd, other_fee_vnd: body.other_fee_vnd });
          world.version += 1;
          return send(200, { version: world.version });
        }
        if (route === '/api/v7/sheet/batch/undo') {
          for (const key of body.command_keys) { const saved = world.keys.get(key); Object.assign(saved.row, saved.before); }
          world.version += 1;
          return send(200, { complete: true, undone: body.command_keys.length, version: world.version });
        }
        return send(404, {});
      });
      return;
    }
    if (route.startsWith('/api/v7/presence')) return send(200, { people: [] });
    if (route === '/api/v7/inbox') return send(200, inbox);
    if (route === '/api/v7/dashboard') return send(200, dashboard);
    if (route === '/api/v7/dashboard/debt') return send(200, { customers: [] });
    if (route === '/api/v7/customers') return send(200, { customers });
    if (route === '/api/v7/price-table/status') return send(200, { trips: [] });
    if (route === '/api/v7/ledger') return send(200, ledgerOf(world));
    if (route.startsWith('/api/')) return send(404, {});
    const file = path.join(__dirname, path.basename(route));
    if (!fs.existsSync(file)) return send(404, {});
    send(200, fs.readFileSync(file), file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.css') ? 'text/css' : 'text/javascript');
  });
}
async function withPage(opts, fn) {
  const world = opts.world ?? makeWorld();
  const server = serverFor(world, opts);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await browser.newPage({ viewport: { width: 1265, height: 560 } });   // 1280 trừ thanh cuộn dọc của Chrome trên Windows
    await page.goto(`http://127.0.0.1:${server.address().port}/viec-can-lam.html`);
    await page.locator('.viec-status').waitFor();
    await page.locator('[data-tab="don"]').click();
    await page.locator('[data-book="2"] .book-name').click();
    await page.locator('[data-group-price]').first().waitFor();
    await fn(page, world);
  } finally { await browser.close(); server.close(); }
}
const keyA = JSON.stringify(['KHO MẪU A', 'CẢNG MẪU 1', 'SHIP MẪU']);
const groupInput = (page, key = keyA) => page.locator(`[data-group-price="${key.replace(/"/g, '\\"')}"]`);
const groupButton = (page, key = keyA) => page.locator(`[data-price-group="${key.replace(/"/g, '\\"')}"]`);
const values = page => page.evaluate(() => Object.fromEntries([...document.querySelectorAll('[data-manual-price]')].map(i => [i.dataset.manualPrice, i.value])));

if (process.argv.includes('--preview')) {
  const port = Number(process.env.UX_PREVIEW_PORT ?? 18768);
  serverFor(makeWorld(), { posted: [] }).listen(port, '127.0.0.1', () => process.stdout.write(`Fixture preview: http://127.0.0.1:${port}/viec-can-lam.html\n`));
} else {
  test('hàng tuyến: chỉ tuyến ≥ 2 chuyến sửa được, tách theo shipper, giá gần nhất, không cuộn ngang', async () => withPage({}, async page => {
    assert.match(await page.locator('.detail-group.warn h3').first().innerText(), /Chưa giá\s*11 chuyến · 6 tuyến/);
    const heads = await page.locator('li.price-group').evaluateAll(rows => rows.map(r => [r.querySelector('b').textContent, r.querySelector('.detail-description').textContent]));
    assert.deepEqual(heads, [
      ['4 chuyến', 'KHO MẪU A → CẢNG MẪU 1 · SHIP MẪU · 02/11–05/11'],
      ['2 chuyến', `${B.origin} → ${B.destination} · 03/11–06/11`],
      ['2 chuyến', 'KHO MẪU A → CẢNG MẪU 1 · TT MẪU · 08/11–09/11'],
    ]);
    assert.equal(await page.locator('.use-last').count(), 1);
    assert.equal(await page.locator('.use-last').innerText(), 'Giá gần nhất 45 tr · 28/10');
    // Tháng khóa và thiếu nơi đi: dòng riêng như cũ, không có ô của hàng tuyến.
    assert.equal(await page.locator('[data-manual-price="8"]').count(), 0);
    assert.equal(await page.locator('[data-manual-price="9"]').getAttribute('data-price-route'), null);
    assert.equal(await page.locator('[data-manual-price="7"]').getAttribute('data-price-route'), null);
    assert.equal(await groupButton(page).isDisabled(), true);
    const fit = await page.evaluate(() => {
      const row = document.querySelector('li.price-group'), button = row.querySelector('.use-last').getBoundingClientRect(), box = row.getBoundingClientRect();
      const rows = [...document.querySelectorAll('li.price-group')];
      // Tên tuyến không bị cắt ở hàng nào (tuyến B dài thì xuống dòng); hàng xuống dòng vẫn gọn, ô giá vẫn thẳng mép phải với chuyến.
      const whole = rows.every(r => { const d = r.querySelector('.detail-description'); return d.scrollWidth <= d.clientWidth && d.scrollHeight <= d.clientHeight + 1; });
      const input = sel => document.querySelector(sel).getBoundingClientRect().right;
      return { noScroll: document.scrollingElement.scrollWidth <= innerWidth, buttonInside: button.right <= box.right && button.left >= box.left, routeWhole: whole,
        tallest: Math.max(...rows.map(r => r.getBoundingClientRect().height)) <= 90, aligned: Math.abs(input('[data-group-price]') - input('[data-manual-price="1"]')) < 1 };
    });
    assert.deepEqual(fit, { noScroll: true, buttonInside: true, routeWhole: true, tallest: true, aligned: true });
  }));

  test('gõ ở hàng tuyến điền xuống; ô đã tự sửa giữ nguyên; ô trống bỏ qua; nút đếm chuyến', async () => withPage({}, async page => {
    await groupInput(page).fill('45');
    assert.deepEqual(await values(page), { 1: '45', 2: '45', 3: '45', 4: '45', 5: '', 6: '', 7: '', 9: '', 10: '', 11: '' });
    assert.equal(await groupButton(page).innerText(), 'Ghi giá 4 chuyến');
    await page.locator('[data-manual-price="2"]').fill('47');
    await page.locator('[data-manual-price="4"]').fill('');
    assert.equal(await groupButton(page).innerText(), 'Ghi giá 3 chuyến');
    await groupInput(page).fill('46');
    assert.deepEqual(Object.values(await values(page)).slice(0, 4), ['46', '47', '46', '']);
    await page.locator('[data-manual-price="3"]').fill('4x');
    assert.equal(await groupButton(page).isDisabled(), true);
    await page.locator('[data-manual-price="3"]').fill('45,5');
    assert.equal(await groupButton(page).isDisabled(), false);
    // Nút giá gần nhất điền vào ô tuyến, rồi xuống các ô chưa tự sửa.
    await page.locator('.use-last').click();
    assert.equal(await groupInput(page).inputValue(), '45');
    assert.deepEqual(Object.values(await values(page)).slice(0, 4), ['45', '47', '45,5', '']);
  }));

  test('xem lại một lần, ghi lần lượt với phiên bản nối tiếp, rồi Hoàn tác cả tuyến', async () => {
    const posted = [];
    await withPage({ posted }, async (page, world) => {
      await groupInput(page).fill('45');
      await page.locator('[data-manual-price="2"]').fill('47');
      await groupButton(page).click();
      const pending = page.locator('.pending-action');
      assert.match(await pending.innerText(), /Ghi 3 chuyến 45 tr · 1 chuyến 47 tr · nợ 679 → 861,5 tr · khác giá gần nhất 45 tr \(28\/10\/2026\)/);
      assert.equal(await page.evaluate(() => document.activeElement.hasAttribute('data-action-cancel')), true, 'tiêu điểm vào Thôi, không vào Xác nhận');
      assert.equal(posted.length, 0);
      await pending.locator('[data-action-write]').click();
      await page.locator('[data-undo-batch]').waitFor();
      assert.deepEqual(posted.map(p => [p.route, p.body.trip_id, p.body.unit_price_vnd, p.body.other_fee_vnd, p.body.expected_version]), [
        ['/api/v7/trips/price', 1, '45000000', null, 7], ['/api/v7/trips/price', 2, '47000000', null, 8],
        ['/api/v7/trips/price', 3, '45000000', '500000', 9], ['/api/v7/trips/price', 4, '45000000', null, 10]]);
      const keys = posted.map(p => p.body.idempotency_key);
      assert.ok(keys.every(k => /^[0-9a-f]{64}$/.test(k)) && new Set(keys).size === 4);
      assert.match(await page.locator('.inbox-result').innerText(), /Đã ghi giá 4 chuyến KHO MẪU A → CẢNG MẪU 1 · SHIP MẪU\./);
      // Sổ đọc lại: bốn chuyến đã có giá rời danh sách; hai chuyến TT MẪU còn hàng tuyến riêng.
      await page.waitForFunction(() => !document.querySelector('[data-manual-price="1"]'));
      assert.equal(await page.locator('li.price-group').count(), 2);
      await page.locator('[data-undo-batch]').click();
      await page.locator('.receipt-review [data-action-write]').click();
      await page.locator('.receipt-review h3', { hasText: 'Đã hoàn tác' }).waitFor();
      await page.locator('.receipt-review [data-action-cancel]').click();
      await page.waitForFunction(n => document.querySelectorAll('[data-manual-price]').length === n, 10);
      const undo = posted.at(-1);
      assert.equal(undo.route, '/api/v7/sheet/batch/undo');
      assert.deepEqual(undo.body.command_keys, keys);
      assert.equal(undo.body.expected_version, 11);
      assert.equal(world.version, 12);
    });
  });

  test('lỗi giữa chừng: dừng, báo đã ghi bao nhiêu, không đưa Hoàn tác', async () => {
    const posted = [];
    const post = (route, body, n) => (n === 2 ? { status: 422, json: { error: 'MONTH_LOCKED', message: 'Tháng 11/2026 đã khóa.' } } : null);
    await withPage({ posted, post }, async page => {
      await groupInput(page).fill('45');
      await groupButton(page).click();
      await page.locator('.pending-action [data-action-write]').click();
      await page.locator('.inbox-result.warn[role=alert]').waitFor();
      assert.equal(posted.length, 2);
      assert.match(await page.locator('.inbox-result.warn').innerText(), /Ghi được 1\/4 chuyến KHO MẪU A → CẢNG MẪU 1 · SHIP MẪU rồi dừng: Tháng 11\/2026 đã khóa\./);
      assert.equal(await page.locator('[data-undo-batch]').count(), 0);
      // Chuyến chưa ghi vẫn giữ giá đã gõ để ghi tiếp.
      await page.locator('[data-manual-price="2"]').waitFor();
      assert.equal(await page.locator('[data-manual-price="2"]').inputValue(), '45');
    });
  });

  test('mất mạng giữa chừng: Thử lại gửi đúng lệnh cũ (cùng khóa, cùng phiên bản), không ghi trùng', async () => {
    const posted = [];
    await withPage({ posted }, async page => {
      const lost = [];
      await page.route('**/api/v7/trips/price', async route => {
        if (posted.length === 1 && !lost.length) { lost.push(route.request().postDataJSON()); return route.abort(); }
        return route.continue();
      });
      await groupInput(page).fill('45');
      await groupButton(page).click();
      await page.locator('.pending-action [data-action-write]').click();
      await page.locator('.pending-action [role=alert]').waitFor();
      assert.match(await page.locator('.pending-action').innerText(), /Mất kết nối khi ghi: đã ghi 1\/4 chuyến/);
      assert.equal(await page.locator('.pending-action [data-action-cancel]').count(), 0);
      await page.locator('.pending-action [data-action-write]').click();
      await page.locator('[data-undo-batch]').waitFor();
      assert.deepEqual(posted[1].body, lost[0]);
      assert.deepEqual(posted.map(p => p.body.trip_id), [1, 2, 3, 4]);
    });
  });

  test('bàn phím: Enter ở ô tuyến mở xem lại, Esc bỏ không gửi', async () => {
    const posted = [];
    await withPage({ posted }, async page => {
      await groupInput(page).fill('45');
      await groupInput(page).press('Enter');
      await page.locator('.pending-action').waitFor();
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('.pending-action'));
      assert.equal(posted.length, 0);
      assert.equal(await groupInput(page).inputValue(), '45');
    });
  });
}
