// Việc cần làm: khối "Sheet cần sửa" (KIEM-TAB-01 3d). Dữ liệu giả; Sheets API thay bằng route giả /api/v7/sheet/vung-o.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

const sha = 'c'.repeat(64);
const customers = [['Mẫu Đông Á', 7], ['Mẫu An Phát', 1], ['Mẫu Phú Gia', 3], ['Mẫu Lộc Phát', 8], ['Mẫu Kim Long', 9]].map(([name, id]) => ({ id, name, commodity: 'Chuối', transport_mode: 'CANG' }));
const book = (id, extra = {}) => ({ customer_id: id, version: 3, outstanding_vnd: '100000000', receipts: { ready: 0, review: 0, amount_vnd: '0', items: [] }, prices: { ready: 0, review: 0 },
  removed: { count: 0, amount_vnd: '0' }, trips_new: 0, trips_check: { count: 0, reasons: {} }, ps: { ready: 0, review: 0 }, text_diff: 0, ...extra });
const dashboard = { as_of: '2026-11-06', todo: { missing_price: [{ customer_id: 7, count: 2 }], pending_review: [], no_baseline: [], credit: [] },
  today: { trips: 0, receipts: 0, voids: 0, received_vnd: '0', by_actor: [{ actor: 'Người nhập mẫu', trips: 2, receipts: 1, voids: 0, received_vnd: '5000000' }] } };
const lech = { customer: 'Mẫu Đông Á', customer_id: 7, status: 'LECH_TONG', reason: 'NO_EXACT_FIX', difference_vnd: '-64200000', web_total_vnd: '5210000000', sheet_total_vnd: '5274200000', web_ahead_vnd: '0',
  sheet_editing: true, sheet_last_edit_at: '2026-11-06T10:00:00+07:00', groups: [{ kind: 'prices', month: '2026-10', count: 18, delta_vnd: '58400000', chosen: false }] };
const reconcile = { version: 1, checked_at: '2026-11-06T10:12:00+07:00', mode: 'fix', counts: { KHOP: 238, LECH_TONG: 1 }, total: 239, matched_web_vnd: '88', all_web_vnd: '100', months_differ: [], outside_tabs: [], matched_ids: [1, 3], customers: [lech] };
const inbox = (extra = {}) => ({ state: 'ready', sheet_at: '2026-11-06T03:15:00Z', computed_at: '2026-11-06T03:16:00Z', failed: [], reconcile,
  auto: { today_count: 1, today_trips: 1, today_prices: 1, today_ps: 0,
    items: [{ customer_id: 1, field: 'origin', before: null, after: 'KHO MẪU', at: '2026-11-06T02:05:00+00:00' }],
    trip_items: [{ customer_id: 1, container: 'MAUU0000002', event_date: '2026-11-05', at: '2026-11-06T03:05:00+00:00' }],
    price_items: [{ customer_id: 3, container: 'MAUU0000003', date: '2026-11-04', before_unit_price_vnd: null, unit_price_vnd: '42000000', at: '2026-11-06T02:50:00+00:00' }] },
  books: [book(7, { prices: { ready: 0, review: 18 }, receipts: { ready: 0, review: 1, amount_vnd: '6100000', items: [] }, ps: { ready: 0, review: 1 } }), book(1, { sheet_matched: true, trips_check: { count: 3, reasons: {} } }), book(3, { sheet_matched: true, ps: { ready: 0, review: 6 } })], ...extra });
// HOAT-DONG-01: việc đã ghi theo ngày (GET /api/v7/activity), cùng hình dạng với Lịch sử của sổ.
const activityDays = {
  '2026-11-06': { day: '2026-11-06', today: '2026-11-06', prev_day: '2026-11-03', next_day: null, total: 3,
    events: [
      { id: 30, customer_id: 1, customer: 'Mẫu An Phát', kind: 'receipt', actor: 'thu.ke@example.test', actor_name: 'Thu', at: '2026-11-06T03:20:00+00:00', before: {},
        after: { pid: 'PH-007', date: '2026-11-05', method: 'CK', amount_vnd: '5000000', allocations: [] } },
      { id: 29, customer_id: 3, customer: 'Mẫu Phú Gia', kind: 'price_edit', actor: 'may-theo-sheet', actor_name: 'Máy (theo Sheet)', at: '2026-11-06T02:50:00+00:00',
        before: { price: { trip_id: 41, unit_price_vnd: null, other_fee_vnd: null } }, after: { price: { trip_id: 41, unit_price_vnd: '42000000', other_fee_vnd: null } } },
      { id: 28, customer_id: 1, customer: 'Mẫu An Phát', kind: 'paste', actor: 'may-theo-sheet', actor_name: 'Máy (theo Sheet)', at: '2026-11-06T02:05:00+00:00', before: {},
        after: { trips: [{ trip_id: 40, container: 'MAUU0000002', event_date: '2026-11-05', unitPriceVnd: null, status: 'confirmed', note: 'Chuyến đồng bộ' }, { trip_id: 42, container: 'MAUU0000004', event_date: '2026-11-05', unitPriceVnd: null, status: 'confirmed', note: 'Chuyến đồng bộ' }] } }],
    trips: [{ id: 40, container: 'MAUU0000002' }, { id: 42, container: 'MAUU0000004' }, { id: 41, container: 'MAUU0000003' }], receipts: [], legacy_rows: [], fee_types: [] },
  '2026-11-03': { day: '2026-11-03', today: '2026-11-06', prev_day: null, next_day: '2026-11-06', total: 1,
    events: [{ id: 5, customer_id: 7, customer: 'Mẫu Đông Á', kind: 'void', actor: 'ke.toan@example.test', actor_name: 'Kế toán', at: '2026-11-03T08:00:00+00:00',
      before: { pid: 'PH-002', amount_vnd: '1000000' }, after: { pid: 'PH-002', void_reason: 'ghi trùng' } }],
    trips: [], receipts: [], legacy_rows: [], fee_types: [] },
};
const fees = [[34, 95], [32, 20], [29, 135], [21, 60], [null, 40], [18, 32], [25, 10], [null, 24], [31, 8], [14, 15], [22, 21], [40, 12], [null, 26], [27, 14], [19, 19], [33, 9], [12, 20], [26, 24]];
const priceRows = fees.map(([web, delta], i) => ({ key: `legacy:${i + 1}`, status: 'CONFLICT', container: `MAUU ${100101 + i * 37}-${i % 9}`, date: `2026-10-${String(3 + i).padStart(2, '0')}`, source_row: 412 + i * 3,
  web_unit_price_vnd: '60000000', sheet_unit_price_vnd: '60000000', web_other_fee_vnd: web === null ? null : String(web * 100000), sheet_other_fee_vnd: String(((web ?? 0) + delta) * 100000), delta_vnd: String(delta * 100000), source_fingerprint: sha }));
const statement = (extra = {}) => ({ customer_id: 7, version: 12, web_vnd: '5210000000', sheet_total_vnd: '5274200000', checked_at: reconcile.checked_at, reason: 'NO_EXACT_FIX', sheet_editing: true, sheet_last_edit_at: lech.sheet_last_edit_at,
  web_ahead_vnd: '0', shuffled_months: [], prices_sha256: sha, receipts_sha256: 'd'.repeat(64),
  groups: [{ id: 'prices:2026-10', kind: 'prices', month: '2026-10', count: 18, delta_vnd: '58400000', locked: true, undoable: true, replaces: 0, rows: priceRows },
    { id: 'receipts_no_date:2026-09', kind: 'receipts_no_date', month: '2026-09', count: 1, delta_vnd: '-6100000', locked: false, undoable: true, replaces: 0, rows: [{ status: 'NO_DATE', source_row: 30, debt_month: '2026-09-01', amount_vnd: '6100000', note: 'trừ phí khác', date: null }] }], ...extra });

function serverFor(opts = {}) {
  const value = x => typeof x === 'function' ? x() : x;
  return http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const send = (status, body) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (route.startsWith('/api/v7/presence')) return send(200, { people: [] });
    if (req.method === 'POST') {
      let raw = '';
      req.on('data', part => { raw += part; });
      req.on('end', () => {
        const body = JSON.parse(raw);
        opts.posted?.push({ route, body });
        const out = opts.post?.(route, body) ?? { status: 200, json: { complete: true, version: 20, before_vnd: '5210000000', after_vnd: '5268400000', undo: { command_keys: ['e'.repeat(64)], months: ['2026-10'] } } };
        send(out.status, out.json);
      });
      return;
    }
    if (route === '/api/v7/inbox') return send(200, value(opts.inbox ?? inbox()));
    if (route === '/api/v7/activity') {
      const day = new URL(req.url, 'http://x').searchParams.get('day') ?? '2026-11-06';
      opts.activityAsked?.push(day);
      return opts.activityStatus ? send(opts.activityStatus, {}) : send(200, activityDays[day] ?? { day, today: '2026-11-06', prev_day: '2026-11-03', next_day: '2026-11-06', total: 0, events: [], trips: [], receipts: [], legacy_rows: [], fee_types: [] });
    }
    if (route === '/api/v7/sheet/doi-chieu') return send(opts.statementStatus ?? 200, value(opts.statement ?? statement()));
    if (route === '/api/v7/sheet/vung-o') {
      opts.regionAsked?.push(req.url);
      return opts.regionStatus ? send(opts.regionStatus, {}) : send(200, value(opts.region ?? region()));
    }
    if (route === '/api/v7/ai/preview') return send(200, opts.aiPreview ?? { enabled: true, fingerprint: 'f'.repeat(64), packet: { customer_id: 7, customer: 'Mẫu Đông Á', checked_at: reconcile.checked_at, groups: [], partial: false } });
    if (route === '/api/v7/dashboard') return send(200, opts.dashboard ?? dashboard);
    if (route === '/api/v7/dashboard/debt') return send(200, { customers: [] });
    if (route === '/api/v7/customers') return send(200, { customers });
    if (route === '/api/v7/ledger') return send(200, { version: 12, total_outstanding_vnd: '100000000', trips: [], sheet_sync: { items: [], removed_items: [] }, sheet_prices: { ready: [], review: priceRows }, sheet_receipts: { review: [{ status: 'NO_DATE', amount_vnd: '6100000', note: 'x', source_fingerprint: sha, debt_month: '2026-09-01' }] } });
    if (route === '/api/v7/price-table/status') return send(200, { trips: [] });
    if (route.startsWith('/api/')) return send(404, {});
    const file = path.join(__dirname, path.basename(route));
    if (!fs.existsSync(file)) return send(404, {});
    res.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.css') ? 'text/css' : 'text/javascript' });
    res.end(fs.readFileSync(file));
  });
}
async function withPage(opts, fn, { width = 1280, height = 560 } = {}) {
  const server = serverFor(opts);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.clock.setFixedTime(new Date(opts.now ?? '2026-11-06T10:15:00+07:00'));
    await page.goto(`http://127.0.0.1:${server.address().port}/viec-can-lam.html`);
    await page.locator('.viec-status').waitFor();
    await fn(page);
  } finally { await browser.close(); server.close(); }
}
const letters = 'ABCDEFGHIJKLMNOPQR'.split('');
const cellOf = (v = '', extra = {}) => ({ v, f: null, bg: null, b: false, al: null, ...extra });
// Vùng 15 dòng × 18 cột từ dòng 8: container ở B15, tiền lệch xuống F16; cột K–R trống nên gộp thành "…".
function region(extra = {}, edit = () => {}) {
  const cells = Array.from({ length: 15 }, () => Array.from({ length: 18 }, () => cellOf()));
  cells[0][0] = cellOf('THÁNG 10/2026', { b: true, bg: '#e8f0fe' });
  ['STT', 'CONTAINER', 'NGÀY', 'ĐƠN GIÁ', 'PHÍ', 'TỔNG', 'GHI CHÚ', 'ĐÃ THU', 'CÒN LẠI', 'KẾ'].forEach((text, c) => { cells[1][c] = cellOf(text, { b: true, bg: '#f3f3f3', al: 'CENTER' }); });
  cells[7][1] = cellOf('MAUU0000001'); cells[7][2] = cellOf('03/10/2026');
  cells[8][5] = cellOf('44.710.920', { f: '=D16+E16', al: 'RIGHT' });
  edit(cells);
  const groups = [...Array.from({ length: 10 }, (_, c) => ({ cols: [c], collapsed: false })), { cols: [10, 11, 12, 13, 14, 15, 16, 17], collapsed: true }];
  return { customer_id: 7, finding: 0, kind: 'row_shift', level: 'error', message: 'Dòng 15 có container mà không có tiền.', fix: 'Đưa tiền về cùng dòng.',
    sample: null, read_at: '2026-11-06T10:14:00+07:00', open_url: 'https://docs.google.com/spreadsheets/d/FAKE/edit#gid=777&range=B15',
    region: { sheet_id: 777, first_row: 8, first_col: 1, col_letters: letters, widths: letters.map(() => 90), heights: Array(15).fill(21), cells,
      merges: [{ r1: 0, c1: 0, r2: 1, c2: 3 }], column_groups: groups,
      marks: [{ row: 7, col: 1, cell: 'B15', level: 'error', text: 'Container không có tiền.' }, { row: 8, col: 5, cell: 'F16', level: 'error', text: 'Tiền không có container.' },
        { row: 7, col: 2, cell: 'C15', level: 'suspect', text: 'Ô ngày hiện 03/10 nhưng lưu 10/03.' }] }, ...extra };
}
const rowShift = { tab: 'Mẫu Đông Á', kind: 'row_shift', level: 'error', month: '2026-10', rows: [15, 16], cells: ['B15', 'F16'],
  message: 'Dòng 15 có container mà không có tiền, dòng 16 có tiền mà không có container: tiền có thể nằm lệch một dòng.', fix: 'Đưa tiền về cùng dòng với container.' };
const second = { tab: 'Mẫu Đông Á', kind: 'negative_receipt', level: 'error', month: '2026-10', rows: [52], cells: ['M52'], message: 'Ô thu ở dòng 52 là số âm.', fix: 'Sửa dấu.' };
const codeOnly = { tab: 'Mẫu Đông Á', kind: 'MISSING_MONTH', level: 'error', count: 1 };
const blockedStatement = (findings = [rowShift, second, codeOnly], extra = {}) => statement({ groups: [], blocked: { code: 'TAB_BROKEN', findings, held: false, held_reasons: {} }, ...extra });
const sheetFix = page => page.locator('.sheet-fix');
const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

if (process.argv.includes('--preview')) {
  const port = Number(process.env.UX_PREVIEW_PORT ?? 18769);
  serverFor({ statement: blockedStatement() }).listen(port, '127.0.0.1', () => process.stdout.write(`Fixture preview: http://127.0.0.1:${port}/viec-can-lam.html\n`));
} else {
  test('tab hỏng: khối Sheet cần sửa thay các khoản, không có nút ghi, vùng ô của chỗ sai đầu mở sẵn và khoanh đúng ô', async () => {
    const asked = [];
    await withPage({ statement: blockedStatement(), regionAsked: asked }, async page => {
      await sheetFix(page).waitFor();
      assert.match(await sheetFix(page).innerText(), /Tab Sheet của khách này cần sửa trước khi web ghi tiền/);
      assert.equal(await page.locator('.dc-table').count(), 0);
      assert.equal(await page.locator('[data-dc-ghi]').count(), 0);
      await page.locator('.sf-scroll').waitFor();
      assert.deepEqual(asked, ['/api/v7/sheet/vung-o?customer=7&finding=0']);
      const marks = await page.locator('[data-sc-mark]').evaluateAll(list => list.map(el => [el.dataset.scMark, el.className.match(/sf-(error|suspect|warning)/)[1]]));
      assert.deepEqual(marks, [['B15', 'error'], ['C15', 'suspect'], ['F16', 'error']]);
      assert.match(await page.locator('.sf-meta').innerText(), /Đọc lúc 10:14/);
      const link = page.locator('.sf-meta a');
      assert.match(await link.getAttribute('href'), /#gid=777&range=B15$/);
      assert.equal(await link.getAttribute('target'), '_blank');
      assert.match(await link.getAttribute('rel'), /noopener/);
      assert.equal(await page.locator('.sf-grid tbody tr').first().locator('.sf-gap').innerText(), '…');   // cột trống K–R gộp thành một cột "…"
      assert.equal(await page.locator('.sf-grid thead th.sf-gap').count(), 1);
      assert.equal(await page.locator('.sf-grid td[colspan="3"]').count(), 1);   // ô tiêu đề gộp ba cột
    });
  });

  test('1280×560: không tràn ngang, ô lỗi nằm trong khung nhìn của lưới', async () => withPage({ statement: blockedStatement(), region: region() }, async page => {
    await page.locator('.sf-scroll').waitFor();
    assert.ok(await noOverflow(page), 'trang tràn ngang');
    const inside = await page.evaluate(() => {
      const mark = document.querySelector('[data-sc-mark="B15"]').getBoundingClientRect(), wrap = document.querySelector('.sf-scroll').getBoundingClientRect();
      return mark.left >= wrap.left && mark.right <= wrap.right;
    });
    assert.ok(inside);
  }));

  test('các chỗ sau đóng sẵn, bấm Xem vùng ô thì đọc đúng chỗ đó; chỗ chỉ có mã lỗi không có nút', async () => {
    const asked = [];
    await withPage({ statement: blockedStatement(), regionAsked: asked }, async page => {
      await page.locator('.sf-scroll').waitFor();
      assert.equal(await page.locator('.sf-card').count(), 3);
      assert.equal(await page.locator('.sf-card').nth(2).locator('[data-sc-view]').count(), 0);
      assert.match(await page.locator('.sf-card').nth(2).innerText(), /Không thấy khối tháng/);
      const button = page.locator('.sf-card').nth(1).locator('[data-sc-view]');
      assert.equal(await button.getAttribute('aria-expanded'), 'false');
      await button.click();
      await page.locator('.sf-card').nth(1).locator('.sf-scroll').waitFor();
      assert.deepEqual(asked, ['/api/v7/sheet/vung-o?customer=7&finding=0', '/api/v7/sheet/vung-o?customer=7&finding=1']);
      await page.locator('.sf-card').nth(1).locator('[data-sc-view]').click();   // ẩn lại
      assert.equal(await page.locator('.sf-card').nth(1).locator('.sf-scroll').count(), 0);
    });
  });

  test('Đọc lại bỏ cache; Sheet không đọc được thì câu thường vẫn hiện, có Thử lại', async () => {
    const asked = [];
    await withPage({ statement: blockedStatement(), regionAsked: asked }, async page => {
      await page.locator('.sf-scroll').waitFor();
      await page.locator('[data-sc-refresh]').click();
      await page.waitForFunction(() => document.querySelector('.sf-scroll'));
      assert.equal(asked.at(-1), '/api/v7/sheet/vung-o?customer=7&finding=0&fresh=1');
    });
    await withPage({ statement: blockedStatement(), regionStatus: 503 }, async page => {
      await page.locator('.sf-failed').waitFor();
      assert.match(await page.locator('.sf-failed').innerText(), /Chưa tải được hình Sheet/);
      assert.match(await sheetFix(page).innerText(), /tiền có thể nằm lệch một dòng/);   // câu thường không phụ thuộc Sheet
      assert.equal(await page.locator('.sf-failed [data-sc-refresh]').count(), 1);
    });
  });

  test('chain_break: nói ô và công thức mẫu của các khối khác', async () => {
    const chain = { tab: 'Mẫu Đông Á', kind: 'chain_break', level: 'error', month: '2026-10', rows: [45], cells: ['N45'], message: 'Số cuối tháng 10 trên Sheet lệch -500 đ.', fix: 'Điền lại công thức.' };
    await withPage({ statement: blockedStatement([chain]), region: region({ kind: 'chain_break', sample: { sample: '=N40+K45-M45', current: '0', has_formula: false } }) }, async page => {
      await page.locator('.sf-sample').waitFor();
      assert.match(await page.locator('.sf-sample').innerText(), /=N40\+K45-M45.*số gõ tay 0, không phải công thức/);
    });
  });

  test('máy giữ khách mà chưa chỉ ra được ô: nói thật, kèm mã lỗi, không giả vờ biết ô', async () => {
    const held = statement({ groups: [], blocked: { code: 'TAB_BROKEN', findings: [], held: true, held_reasons: { ANCHOR_CHAIN_MISMATCH: 2 } } });
    await withPage({ statement: held }, async page => {
      await sheetFix(page).waitFor();
      const text = await sheetFix(page).innerText();
      assert.match(text, /Máy đang giữ khách này/);
      assert.match(text, /ANCHOR_CHAIN_MISMATCH ×2/);
      assert.equal(await page.locator('.sf-card').count(), 0);
    });
  });

  test('chữ từ Sheet và từ server không chạy thành mã', async () => {
    const evil = { ...rowShift, message: '<img src=x onerror="window.pwned=1"> lệch', cells: ['B15'] };
    const shown = region({}, cells => { cells[7][1] = cellOf('<b onclick=1>X</b>'); });
    await withPage({ statement: blockedStatement([evil]), region: shown }, async page => {
      await page.locator('.sf-scroll').waitFor();
      assert.equal(await page.locator('.sheet-fix img').count(), 0);
      assert.equal(await page.evaluate(() => window.pwned), undefined);
      assert.match(await page.locator('[data-sc-mark="B15"]').innerText(), /<b onclick=1>X<\/b>/);
    });
  });

  // Chip lọc đầu bảng khách lệch và nhãn ở dòng (specs/v7-sheet-can-sua.md mục 2, phương án A).
  const heldRow = (name, id, extra = {}) => ({ customer: name, customer_id: id, status: 'CHI_CO_WEB', reason: 'HELD', difference_vnd: null, web_total_vnd: '100000000', sheet_total_vnd: null, held_reasons: { ROW_SHIFT: 2 }, ...extra });
  const withHeld = inbox({ reconcile: { ...reconcile, counts: { KHOP: 236, LECH_TONG: 1, CHI_CO_WEB: 2 }, customers: [lech, heldRow('Mẫu Lộc Phát', 8, { sheet_fix_count: 2 }), heldRow('Mẫu Kim Long', 9)] } });
  const rowNames = page => page.locator('.dc-customer th').allInnerTexts();

  test('chip Sheet cần sửa (n): đếm khách máy giữ, lọc còn đúng các khách đó, nhãn ở dòng nêu số chỗ', async () => {
    await withPage({ inbox: withHeld }, async page => {
      await page.locator('.dc-filter').waitFor();
      const chips = page.locator('.dc-filter .filter-chip');
      assert.deepEqual((await chips.allInnerTexts()).map(text => text.replace(/\s+/g, ' ').trim()), ['Tất cả 3', 'Sheet cần sửa 2']);
      assert.equal(await chips.nth(0).getAttribute('aria-pressed'), 'true');
      assert.deepEqual(await page.locator('.dc-tag').allInnerTexts(), ['Sheet cần sửa · 2 chỗ', 'Sheet cần sửa']);
      assert.equal(await rowNames(page).then(list => list.length), 3);
      await chips.nth(1).click();
      assert.equal(await page.locator('.dc-filter .filter-chip').nth(1).getAttribute('aria-pressed'), 'true');
      assert.deepEqual(await rowNames(page), ['Mẫu Lộc Phát', 'Mẫu Kim Long']);
      await page.locator('.dc-filter .filter-chip').nth(0).click();
      assert.equal(await rowNames(page).then(list => list.length), 3);
    });
  });

  test('không có khách máy giữ thì không có chip, bảng như cũ', async () => withPage({}, async page => {
    await page.locator('.dc-customer').first().waitFor();
    assert.equal(await page.locator('.dc-filter').count(), 0);
    assert.equal(await page.locator('.dc-tag').count(), 0);
  }));

  test('chip và nhãn ở 390px: trang không cuộn ngang', async () => withPage({ inbox: withHeld }, async page => {
    await page.locator('.dc-filter').waitFor();
    assert.ok(await noOverflow(page), 'trang tràn ngang');
    const box = await page.locator('.dc-filter').boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= 390);
  }, { width: 390, height: 780 }));

  test('điện thoại 390px: trang không cuộn ngang, lưới cuộn ngang trong khung và ô lỗi đầu tiên nằm trong khung nhìn', async () => withPage({ statement: blockedStatement(), region: region() }, async page => {
    await page.locator('.sf-scroll').waitFor();
    assert.ok(await noOverflow(page), 'trang tràn ngang');
    const grid = await page.evaluate(() => {
      const wrap = document.querySelector('.sf-scroll'), mark = document.querySelector('[data-sc-mark="B15"]').getBoundingClientRect(), box = wrap.getBoundingClientRect();
      return { scrolls: wrap.scrollWidth > wrap.clientWidth, visible: mark.left >= box.left && mark.right <= box.right, wide: box.width };
    });
    assert.ok(grid.scrolls, 'lưới phải cuộn ngang trong khung');
    assert.ok(grid.visible, 'ô lỗi phải nằm trong khung nhìn');
    assert.ok(grid.wide <= 390);
  }, { width: 390, height: 780 }));
}
