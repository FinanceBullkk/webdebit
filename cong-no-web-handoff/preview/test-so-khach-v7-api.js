const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { create, stale, unknown } = require('./so-khach-v7-api.js');

const reply = (status, body) => ({ ok: status === 200, json: async () => body });
const ledger = version => ({ status: 'active', customer_id: 7, version, months: [], total_outstanding_vnd: '10' });
const receipt = { date: '2026-10-20', method: 'THU TIỀN', amount_vnd: '10', actor: 'forged', total_vnd: '999' };

async function livePage(data) {
  const listeners = {};
  const root = { innerHTML: '', addEventListener(name, handler) { listeners[name] = handler; }, querySelector() { return null; } };
  const context = vm.createContext({ document: { querySelector: () => root, addEventListener() {} },
    window: { scrollY: 0, scrollTo() {} }, location: { search: '?customer=7' },
    URLSearchParams, structuredClone, Date, BigInt, Intl, crypto: { randomUUID: () => 'key' },
    fetch: async (...args) => root.fetcher ? root.fetcher(...args) : reply(200, data) });
  for (const name of ['model', 'api', 'ui']) vm.runInContext(fs.readFileSync(require.resolve(`./so-khach-v7-${name}.js`), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  return { root, listeners, context };
}

test('paste history labels one trip date; receipt history keeps payment date', async () => {
  const { root } = await livePage({ ...ledger(1), events: [
    { kind: 'paste', before: {}, after: { trips: [
      { container: 'FAKE', date: '01/01/2026', event_date: '2026-01-01' },
      { container: 'FAKE-2', date: '02/01/2026' },
      { container: 'FAKE-3', event_date: '2026-01-03' }] } },
    { kind: 'receipt', before: {}, after: { pid: 'PH-001', date: '2026-10-20', amount_vnd: '100' } },
  ] });
  const paste = root.innerHTML.match(/<li>.*?<strong>Dán lô chuyến<\/strong>.*?<\/li>/s)[0];
  assert.doesNotMatch(paste, /Ngày trả/);
  assert.equal((paste.match(/Ngày chuyến:/g) || []).length, 3);
  assert.equal((paste.match(/01\/01\/2026/g) || []).length, 1);
  assert.match(root.innerHTML, /<strong>Ghi thu<\/strong><p>.*?Ngày trả: 20\/10\/2026/);
});

test('trip adjustment history pairs field and amount before to after with signed server delta', async () => {
  const changes = [
    ['unit_price_vnd', '300000', '350000', '300000', '350000', '50000',
      'Đơn giá: 300.000 → 350.000 · Thành tiền: 300.000 → 350.000 · Điều chỉnh: +50.000'],
    ['other_fee_vnd', '20000', '10000', '350000', '340000', '-10000',
      'Phụ phí: 20.000 → 10.000 · Thành tiền: 350.000 → 340.000 · Điều chỉnh: -10.000'],
    [null, null, null, '340000', '360000', '20000',
      'Thành tiền: 340.000 → 360.000 · Điều chỉnh: +20.000'],
    ['unit_price_vnd', '9007199254740993', '9007199254740994', '9007199254740993', '9007199254740994', '123',
      'Đơn giá: 9.007.199.254.740.993 → 9.007.199.254.740.994 · Thành tiền: 9.007.199.254.740.993 → 9.007.199.254.740.994 · Điều chỉnh: +123'],
    [null, null, null, null, null, null, 'Thành tiền: – → – · Điều chỉnh: –'],
  ];
  for (const [field, oldValue, newValue, oldAmount, newAmount, delta, expected] of changes) {
    const { root } = await livePage({ ...ledger(1), events: [{ kind: 'adjust_trip',
      before: { trip: 1, amount_vnd: oldAmount, field, new_value_vnd: oldValue },
      after: { adjustment: 1, new_amount_vnd: newAmount, old_amount_vnd: oldAmount,
        delta_vnd: delta, field, new_value_vnd: newValue } }] });
    assert.ok(root.innerHTML.includes(`<p>${expected}</p>`), expected);
  }
});

test('adjust_trip SQL stores field intent in adjustment; fee source is table not audit', () => {
  const sql = fs.readFileSync(require.resolve('../tools/v7_backend_functions.sql'), 'utf8');
  const adjust = sql.split('CREATE FUNCTION sokhach.adjust_trip(')[1].split('CREATE FUNCTION sokhach.adjust_month(')[0];
  assert.doesNotMatch(adjust, /FROM sokhach\.event/);
  assert.match(adjust, /SELECT a\.new_value_vnd INTO v_fee\s+FROM sokhach\.adjustment a/);
  assert.match(adjust, /a\.field='other_fee_vnd' AND a\.created_by_event>v_price\.created_by_event\s+ORDER BY a\.created_by_event DESC LIMIT 1/);
  assert.match(adjust, /INSERT INTO sokhach\.adjustment\([^)]*field,new_value_vnd\)[\s\S]*sokhach\._actor\(\),v_event,field,new_value_vnd\)/);
  const schema = fs.readFileSync(require.resolve('../../specs/v7-backend/schema-draft.sql'), 'utf8');
  const table = schema.split('CREATE TABLE sokhach.adjustment (')[1].split('COMMENT ON TABLE')[0];
  assert.match(table, /field text CHECK \(field IN \('unit_price_vnd','other_fee_vnd'\)\)/);
  assert.match(table, /new_value_vnd bigint CHECK \(new_value_vnd >= 0\)/);
  assert.match(table, /CHECK \(\(field IS NULL\) = \(new_value_vnd IS NULL\)\)/);
});

test('void keeps only allocations superseded by void event, with struck date/money and dated trace', async () => {
  const { root, listeners } = await livePage({ ...ledger(3), today_month: '2026-10-01',
    months: [{ month: '2026-01-01' }, { month: '2026-02-01' }],
    receipts: [{ pid: 'PH-001', date: '2026-03-01', voided_on: '2026-10-20', void_reason: 'nhập trùng', voided_by_event: 30,
      allocations: [{ month: '2026-01-01', amount_vnd: '999', superseded_by_event: 20 },
        { month: '2026-02-01', amount_vnd: '123456', superseded_by_event: 30 }] }] });
  assert.match(root.innerHTML, /class="pay pay-start receipt receipt-edit voided"[^>]*tabindex="-1">01\/03\/2026/);
  assert.match(root.innerHTML, /voided-method[^>]*>ĐÃ HỦY/);
  assert.match(root.innerHTML, /class="pay num receipt voided"[^>]*>123\.456/);
  assert.match(root.innerHTML, /123\.456 · 01\/03\/2026 · 20\/10\/2026 · nhập trùng/);
  assert.doesNotMatch(root.innerHTML, /999/);
  const deadCell = { classList: { contains: name => name === 'voided' }, querySelector() { throw Error('voided receipt edited'); } };
  await listeners.click({ target: { closest: selector => selector === 'td.receipt[data-pid]' ? deadCell : null } });
});

test('history formats every SQL event kind, snapshots and VN timestamp; hides unknown codes', async () => {
  const kinds = { paste: 'Dán lô chuyến', price_edit: 'Sửa giá', adjust_trip: 'Điều chỉnh chuyến',
    adjust_month: 'Điều chỉnh cả tháng', receipt: 'Ghi thu', receipt_edit: 'Sửa ngày/hình thức phiếu',
    void: 'Hủy phiếu', reallocation: 'Phân bổ lại', import: 'Nhập số dư đầu' };
  const events = Object.keys(kinds).map((kind, i) => ({ id: i, kind, actor: 'Người thử', at: '2026-10-20T01:02:00Z',
    before: { amount_vnd: '9007199254740993', date: '2026-01-02', month: '2026-01-01' },
    after: { amount_vnd: '9007199254740994', note: 'giá đúng', allocations: [{ month: '2026-02-01', kind: 'debt', amount_vnd: '100' }] } }));
  events.push({ kind: 'private_new_code', at: '2026-10-20T01:01:00Z', before: { unknown_key: 'private_value' }, after: {} });
  const { root } = await livePage({ ...ledger(1), events });
  for (const label of Object.values(kinds)) assert.ok(root.innerHTML.includes(label), label);
  assert.match(root.innerHTML, /20\/10\/2026 08:02/);
  assert.match(root.innerHTML, /9\.007\.199\.254\.740\.993.*→.*9\.007\.199\.254\.740\.994/);
  assert.match(root.innerHTML, /02\/01\/2026/);
  assert.match(root.innerHTML, /tháng 2\/2026/);
  assert.match(root.innerHTML, /Ghi chú\/lý do: giá đúng/);
  assert.match(root.innerHTML, /Thao tác khác/);
  assert.doesNotMatch(root.innerHTML, /private_new_code|unknown_key|private_value|\[object Object\]|"amount_vnd"/);
  const sql = fs.readFileSync(require.resolve('../tools/v7_backend_functions.sql'), 'utf8');
  const written = [...sql.matchAll(/VALUES\s*\(\s*(?:customer_id|p_customer)\s*,\s*'([^']+)'/g)].map(match => match[1]);
  assert.deepEqual([...new Set(written)].sort(), Object.keys(kinds).sort());
});

test('locked edit asks clicked field, sends note and field intent only', async () => {
  const { root, listeners } = await livePage({ ...ledger(1), trips: [{ id: 1, editable: false,
    month: '2026-01-01', unit_price_vnd: '100', other_fee_vnd: null }] });
  const sent = [];
  root.fetcher = async (path, options) => { if (options?.method === 'POST') sent.push(JSON.parse(options.body)); return reply(422, { message: 'Chuyến chưa có giá.' }); };
  for (const [field, label] of [['unit_price_vnd', 'Đơn giá mới'], ['other_fee_vnd', 'Phụ phí mới']]) {
    let onKey;
    const input = { value: '200', focus() {}, select() {}, addEventListener(name, fn) { onKey = fn; } };
    const note = { value: 'ghi chú thử', addEventListener() {} };
    const error = { textContent: '' };
    const cell = { dataset: { trip: '1', field }, innerHTML: '', querySelector(selector) {
      if (selector === 'input' && !this.innerHTML) return null;
      return selector === '.adjustment-note' ? note : selector === '.cell-error' ? error : input;
    } };
    await listeners.click({ target: { closest: selector => selector === 'td.editable' ? cell : null } });
    assert.ok(cell.innerHTML.includes(`aria-label="${label}"`));
    assert.match(cell.innerHTML, /Ghi chú/);
    await onKey({ key: 'Enter', preventDefault() {} });
    assert.deepEqual(sent.at(-1), { customer_id: 7, expected_version: 1, idempotency_key: 'key',
      trip_id: 1, field, new_value_vnd: '200', note: 'ghi chú thử' });
  }
});

test('future receipt error appears beside date and releases pending command', async () => {
  const { root, listeners } = await livePage(ledger(1));
  root.fetcher = async () => reply(422, { error: 'FUTURE_RECEIPT_DATE', message: 'Ngày trả không được sau hôm nay.' });
  const error = { textContent: '' }, date = { value: '21/10/2026', focus() {} };
  const row = { querySelector: selector => selector === '.receipt-date' ? date : selector === '.receipt-method' ? { value: 'THU TIỀN' } : error };
  const target = { value: '10', matches: selector => selector === '.receipt-amount', closest: () => row };
  await listeners.keydown({ key: 'Enter', target, preventDefault() {} });
  assert.equal(error.textContent, 'Ngày trả không được sau hôm nay.');
  assert.match(root.innerHTML, /receipt-date-error/);
});

test('saved receipt date shows future-date error in clicked cell', async () => {
  const { root, listeners } = await livePage(ledger(1));
  let onKey;
  const input = { value: '21/10/2026', focus() {}, addEventListener(name, fn) { onKey = fn; } };
  const error = { textContent: '' };
  const cell = { dataset: { field: 'date', pid: 'PH-001' }, textContent: '20/10/2026', innerHTML: '',
    classList: { contains: () => false }, querySelector(selector) {
      if (selector === 'input,select') return null;
      return selector === '.receipt-date-error' ? error : input;
    } };
  root.fetcher = async () => reply(422, { error: 'FUTURE_RECEIPT_DATE', message: 'Ngày trả không được sau hôm nay.' });
  await listeners.click({ target: { closest: selector => selector === 'td.receipt[data-pid]' ? cell : null } });
  await onKey({ key: 'Enter', preventDefault() {} });
  assert.equal(error.textContent, 'Ngày trả không được sau hôm nay.');
});

test('real copy banner uses exact warning from GET', async () => {
  const { root } = await livePage({ ...ledger(1), real_copy: true });
  assert.equal(root.textContent, 'Dữ liệu thật · bản sao cô lập, chưa phải prod');
  assert.equal(root.hidden, false);
});

test('history presents actual nested price/paste/void snapshots and escapes notes', async () => {
  const { root } = await livePage({ ...ledger(1), events: [
    { kind: 'price_edit', before: { price: { unit_price_vnd: '9007199254740993', other_fee_vnd: null } },
      after: { price: { unit_price_vnd: '9007199254740994', other_fee_vnd: '10' } } },
    { kind: 'paste', before: {}, after: { trips: [{ container: 'FAKE', date: '01/01/2026',
      unitPriceVnd: '100', otherFeeVnd: null, note: '<script>bad</script>' }] } },
    { kind: 'void', before: { pid: 'PH-001', amount_vnd: '100' }, after: { pid: 'PH-001', void_reason: 'nhập trùng', allocations: [] } },
  ] });
  assert.match(root.innerHTML, /Đơn giá: 9\.007\.199\.254\.740\.993 · Phụ phí: – → Đơn giá: 9\.007\.199\.254\.740\.994 · Phụ phí: 10/);
  assert.match(root.innerHTML, /Chuyến: Container: FAKE/);
  assert.match(root.innerHTML, /Ghi chú\/lý do: &lt;script&gt;bad&lt;\/script&gt;/);
  assert.match(root.innerHTML, /Ghi chú\/lý do: nhập trùng/);
  assert.doesNotMatch(root.innerHTML, /<script>|price_edit|void_reason|unitPriceVnd/);
});

test('POST sends intent only; redraw follows successful GET', async () => {
  const calls = [], drawn = [];
  const responses = [reply(200, ledger(2)), reply(200, { version: 3 }), reply(200, ledger(3))];
  const api = create({ customerId: 7, fetcher: async (...args) => { calls.push(args); return responses.shift(); },
    key: () => 'one-key', onSnapshot: row => drawn.push(row.version) });
  await api.read();
  await api.submit('receipt', receipt);
  const sent = JSON.parse(calls[1][1].body);
  assert.deepEqual(sent, { customer_id: 7, expected_version: 2, idempotency_key: 'one-key',
    date: '2026-10-20', method: 'THU TIỀN', amount_vnd: '10' });
  assert.deepEqual(drawn, [2, 3]);
  assert.equal(api.hasPending(), false);
  assert.equal(calls[2][0], '/api/v7/ledger?customer=7');
});

test('STALE_LEDGER refreshes once and never resends old intent', async () => {
  const calls = [], notices = [], drawn = [];
  const responses = [reply(200, ledger(1)), reply(409, { error: 'STALE_LEDGER' }), reply(200, ledger(2))];
  const api = create({ customerId: 7, fetcher: async (...args) => { calls.push(args); return responses.shift(); },
    key: () => 'stale-key', onNotice: text => notices.push(text), onSnapshot: row => drawn.push(row.version) });
  await api.read(); await api.submit('receipt', receipt);
  assert.deepEqual(calls.map(call => call[0]), ['/api/v7/ledger?customer=7', '/api/v7/receipts', '/api/v7/ledger?customer=7']);
  assert.deepEqual(drawn, [1, 2]);
  assert.equal(notices.at(-1), stale);
  assert.equal(api.hasPending(), false);
});

test('paste strips nested actor and computed totals', async () => {
  let posted;
  const api = create({ customerId: 7, key: () => 'paste-key', fetcher: async (path, options) => {
    if (options?.method === 'POST') posted = JSON.parse(options.body);
    return reply(200, path.includes('/ledger?') ? ledger(posted ? 2 : 1) : { version: 2 });
  } });
  await api.read();
  await api.submit('paste', { debt_month: '2026-10-01', trips: [{ date: '20/10/2026', container: 'FAKE',
    unitPriceVnd: '10', actor: 'forged', total_vnd: '999', allocation: 'forged' }] });
  assert.deepEqual(posted.trips, [{ date: '20/10/2026', container: 'FAKE', unitPriceVnd: '10' }]);
});

for (const failure of ['network', 'unknown']) test(`${failure} keeps same payload and key on retry`, async () => {
  const calls = [], notices = [], drawn = [];
  let count = 0;
  const api = create({ customerId: 7, key: () => 'retry-key',
    fetcher: async (...args) => {
      calls.push(args);
      if (args[1]?.method === 'POST' && count++ === 0) {
        if (failure === 'network') throw Error('offline');
        return reply(503, { error: 'RESULT_UNKNOWN' });
      }
      return args[1]?.method === 'POST' ? reply(200, { version: 2 }) : reply(200, ledger(count ? 2 : 1));
    }, onNotice: text => notices.push(text), onSnapshot: row => drawn.push(row.version) });
  await api.read(); await api.submit('receipt', receipt);
  assert.equal(notices.at(-1), unknown);
  assert.equal(api.hasPending(), true);
  assert.deepEqual(drawn, [1]);
  await api.retry();
  assert.equal(calls[1][1].body, calls[2][1].body);
  assert.equal(api.hasPending(), false);
  assert.deepEqual(drawn, [1, 2]);
});

test('NO_BASELINE blocks writes and money must be string', async () => {
  const calls = [];
  const api = create({ customerId: 7, fetcher: async (...args) => { calls.push(args); return reply(200, { ...ledger(0), status: 'NO_BASELINE' }); } });
  await api.read();
  await assert.rejects(api.submit('receipt', receipt), /số dư đầu/);
  assert.equal(calls.length, 1);
  const active = create({ customerId: 7, fetcher: async () => reply(200, ledger(0)) });
  await active.read();
  await assert.rejects(active.submit('receipt', { ...receipt, amount_vnd: 10 }), /chuỗi VND/);
});

test('fixture renderer stays in tab; live renderer uses GET values and flags', async () => {
  function page(live, data) {
    const root = { innerHTML: '', addEventListener() {}, querySelector() { return null; } };
    const context = vm.createContext({ document: { querySelector: () => root, addEventListener() {} },
      window: { scrollY: 0, scrollTo() {} }, location: { search: live ? '?customer=7' : '' },
      URLSearchParams, structuredClone, Date, BigInt, crypto: { randomUUID: () => 'key' },
      fetch: async () => reply(200, data) });
    for (const name of [...(live ? [] : ['so-khach-v7-fixture.js']), 'so-khach-v7-model.js',
      ...(live ? ['so-khach-v7-api.js'] : []), 'so-khach-v7-ui.js']) {
      vm.runInContext(fs.readFileSync(require.resolve(`./${name}`), 'utf8'), context, { filename: name });
    }
    return root;
  }
  const fixture = page(false);
  assert.equal(require('node:crypto').createHash('sha256').update(fixture.innerHTML).digest('hex'),
    '58265f6d23ad38c4bc7654d8ff9295e5d35bbf78e0318b7c153e362b053e19c4', 'fixture HTML must match round-2 baseline');
  assert.match(fixture.innerHTML, /THÁNG 10\/2026/);
  assert.match(fixture.innerHTML, /Dán các dòng từ Sheet vào đây/);
  const live = page(true, { ...ledger(1), months: [{ month: '2026-10-01', outstanding_vnd: '600', end_of_month_vnd: '600' }],
    opening: [{ month: '2026-10-01', amount_vnd: '600' }], trips: [], receipts: [], adjustments: [],
    legacy_rows: [{ month: '2026-10-01', display: 'old', source_total_vnd: '600' }],
    source_exceptions: [{ month: '2026-10-01', exception_codes: ['HISTORICAL_DELTA_600'], source_charge_vnd: '1234567', source_receipt_vnd: '634567', source_cumulative_vnd: '600000' }], events: [] });
  await new Promise(resolve => setImmediate(resolve));
  // Import-quality flags stay in the DB/report, not on the ledger (user 20/10/2026).
  assert.doesNotMatch(live.innerHTML, /Chênh lịch sử 600đ|Cần kiểm tra nguồn|Thiếu mốc đối soát/);
  assert.match(live.innerHTML, /đã nằm trong số dư đầu, chỉ để đối chiếu, không cộng lại/);
  assert.match(live.innerHTML, /<tr class="legacy"/);
  // Option (b): Sheet figures shown beside the subtotal, straight from GET.
  assert.match(live.innerHTML, /<tr class="source-total"><td colspan="8">Theo sổ gốc[^<]*<\/td><td class="num ">1\.234\.567<\/td><td class="pay pay-start" colspan="2">Đã thu<\/td><td class="num pay">634\.567<\/td><td class="num ">600\.000<\/td>/);
  assert.doesNotMatch(live.innerHTML, /\[object Object\]/);
  assert.match(live.innerHTML, /Tổng còn nợ \(mọi tháng\)<\/span><strong>10<\/strong>/);
  // Tháng hiện tại chưa có dữ liệu vẫn có khối ghi thu và ô dán; tổng tháng vẽ thẳng từ GET;
  // cờ khóa lấy từ month_locks kể cả tháng không chuyến.
  const newMonth = page(true, { ...ledger(4), today_month: '2026-11-01',
    months: [
      { month: '2026-08-01', outstanding_vnd: '0', end_of_month_vnd: '0', prior_months_vnd: '0', charges_vnd: '0', received_vnd: '0' },
      { month: '2026-09-01', outstanding_vnd: '500', end_of_month_vnd: '500', prior_months_vnd: '0', charges_vnd: '1234567', received_vnd: '1234067' }],
    month_locks: [{ month: '2026-08-01', locked: false }],
    opening: [], trips: [], receipts: [], adjustments: [], legacy_rows: [], source_exceptions: [], events: [] });
  await new Promise(resolve => setImmediate(resolve));
  assert.match(newMonth.innerHTML, /id="thang-2026-11"/);
  assert.match(newMonth.innerHTML, /class="empty-entry receipt-amount"/);
  assert.match(newMonth.innerHTML, /data-month="2026-11" rows="2"/);
  assert.match(newMonth.innerHTML, /data-month="2026-08" rows="2"/);
  assert.doesNotMatch(newMonth.innerHTML, /data-month="2026-09" rows="2"/);
  assert.match(newMonth.innerHTML, /<td class="num ">1\.234\.567<\/td><td class="pay pay-start" colspan="2">Đã thu<\/td><td class="num pay">1\.234\.067<\/td>/);
  assert.match(newMonth.innerHTML, /THÁNG 9\/2026.*Nợ các tháng trước: 0<\/em>/);
  const noBaseline = page(true, { ...ledger(0), status: 'NO_BASELINE', total_outstanding_vnd: null,
    source_exceptions: [{ month: '2026-10-01', exception_codes: ['NO_BASELINE'] }] });
  await new Promise(resolve => setImmediate(resolve));
  assert.match(noBaseline.innerHTML, /Khách chưa có số dư đầu hiệu lực/);
  assert.doesNotMatch(noBaseline.innerHTML, /Thiếu mốc đối soát nguồn|NO_BASELINE/);
  assert.doesNotMatch(noBaseline.innerHTML, /class="receipt-amount"/);
});
