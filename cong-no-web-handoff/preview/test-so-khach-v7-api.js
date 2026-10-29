const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { create, stale, unknown } = require('./so-khach-v7-api.js');
// File sổ khách nạp theo đúng thứ tự thẻ <script> của trang live (bỏ sheet-refresh.js: test không có ô Cập nhật).
const liveScripts = [...fs.readFileSync(require.resolve('./so-khach-v7-live.html'), 'utf8').matchAll(/<script src="(so-khach-v7-[a-z0-9-]+\.js)"><\/script>/g)].map(match => match[1]);

const reply = (status, body) => ({ ok: status === 200, json: async () => body });
const ledger = version => ({ status: 'active', customer_id: 7, version, months: [], total_outstanding_vnd: '10' });
const receipt = { date: '2026-10-20', method: 'THU TIỀN', amount_vnd: '10', actor: 'forged', total_vnd: '999' };

test('reference remains text; duplicate warning follows successful save and refresh', async () => {
  const sent = [], notices = [];
  const api = create({ customerId: 7, key: () => 'ref-key', onNotice: value => notices.push(value),
    fetcher: async (_url, options) => {
      if (options?.method === 'POST') { sent.push(JSON.parse(options.body)); return reply(200, { duplicate_reference: true }); }
      return reply(200, ledger(sent.length));
    } });
  await api.read();
  await api.submit('receipt', { ...receipt, reference: 'FAKE USD/rate text' });
  assert.equal(sent[0].reference, 'FAKE USD/rate text');
  assert.equal(sent[0].amount_vnd, '10');
  assert.match(notices.at(-1), /Đã lưu.*Tham chiếu trùng/);
  assert.equal(api.hasPending(), false);
  await api.submit('receiptMeta', { pid: 'PH-001', reference: '' });
  assert.equal(sent[1].reference, '');
});

test('month history shows separate open and close with actor, VN time and month', async () => {
  const { root } = await livePage({ ...ledger(1), events: [
    { kind: 'month_lock', actor: 'fake-opener', at: '2026-01-02T03:00:00Z', before: { month: '2026-01-01', locked: true }, after: { month: '2026-01-01', locked: false } },
    { kind: 'month_lock', actor: 'fake-closer', at: '2026-01-02T04:00:00Z', before: { month: '2026-01-01', locked: false }, after: { month: '2026-01-01', locked: true } },
  ] });
  assert.match(root.innerHTML, /fake-opener/);
  assert.match(root.innerHTML, /02\/01\/2026 10:00/);
  assert.match(root.innerHTML, /Mở tháng 1\/2026/);
  assert.match(root.innerHTML, /fake-closer/);
  assert.match(root.innerHTML, /Khóa tháng 1\/2026/);
});

async function livePage(data) {
  const listeners = {};
  const handlers = {};
  // Trang đăng ký nhiều trình nghe cùng loại: gọi lần lượt như trình duyệt.
  const root = { innerHTML: '', addEventListener(name, handler) { (handlers[name] ??= []).push(handler); listeners[name] = async event => { for (const item of handlers[name]) await item(event); }; }, querySelector() { return null; }, contains: () => false };
  const context = vm.createContext({ document: { querySelector: () => root, addEventListener() {} },
    window: { scrollY: 0, scrollTo() {} }, location: { search: '?customer=7' },
    URLSearchParams, structuredClone, Date, BigInt, Intl, setInterval: () => 0, crypto: { randomUUID: () => 'key' },
    fetch: async (...args) => root.fetcher ? root.fetcher(...args) : reply(200, data) });
  for (const name of liveScripts) vm.runInContext(fs.readFileSync(require.resolve(`./${name}`), 'utf8'), context);
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

test('adjust_trip keeps unit intent in adjustment and syncs fee intent through lines', () => {
  const sql = fs.readFileSync(require.resolve('../tools/v7_backend_functions.sql'), 'utf8');
  const adjust = sql.split('CREATE OR REPLACE FUNCTION sokhach.adjust_trip(')[1].split('CREATE FUNCTION sokhach.adjust_month(')[0];
  assert.doesNotMatch(adjust, /FROM sokhach\.event/);
  assert.match(adjust, /PERFORM sokhach\._compat_trip_fee\(customer_id,trip_id,new_value_vnd,v_event\)/);
  assert.doesNotMatch(adjust, /a\.created_by_event>v_price\.created_by_event/);
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
    receipts: [{ pid: 'PH-001', date: '2026-03-01', amount_vnd: '123456', voided_on: '2026-10-20', void_reason: 'nhập trùng', voided_by_event: 30,
      allocations: [{ month: '2026-01-01', amount_vnd: '999', superseded_by_event: 20 },
        { month: '2026-02-01', amount_vnd: '123456', superseded_by_event: 30 }] }] });
  // SO-GON-02: phiếu đã hủy không nằm trong danh sách phiếu; gom một dòng mờ, bấm Xem mới hiện số gạch, ngày, lý do.
  assert.doesNotMatch(root.innerHTML, /ĐÃ HỦY|data-pid="PH-001"/);
  assert.match(root.innerHTML, /<tr class="void-summary"><td colspan="3">1 phiếu đã hủy, không tính tiền<button type="button" class="void-toggle" data-month="2026-03" aria-expanded="false">Xem<\/button>/);
  assert.doesNotMatch(root.innerHTML, /nhập trùng/);
  root.querySelectorAll = () => [];
  await listeners.click({ target: { closest: selector => selector === '.void-toggle' ? { dataset: { month: '2026-03' } } : null } });
  assert.match(root.innerHTML, /<tr class="void-trace"><td colspan="3"><s>123\.456<\/s> · 01\/03\/2026 · hủy 20\/10\/2026 · nhập trùng<\/td><\/tr>/);
  assert.doesNotMatch(root.innerHTML, /999/);
  const deadCell = { classList: { contains: name => name === 'voided' }, querySelector() { throw Error('voided receipt edited'); } };
  await listeners.click({ target: { closest: selector => selector === 'td.receipt[data-pid]' ? deadCell : null } });
});

test('DA-THU-01: phiếu nằm ở tháng của ngày thu, đủ số tiền, ghi chữ nhỏ phần trừ nợ từng tháng', async () => {
  const { root } = await livePage({ ...ledger(3), today_month: '2026-10-01',
    months: [
      { month: '2026-08-01', prior_months_vnd: '0', charges_vnd: '100', received_vnd: '0', end_of_month_vnd: '100', outstanding_vnd: '0' },
      { month: '2026-09-01', prior_months_vnd: '100', charges_vnd: '50', received_vnd: '30', end_of_month_vnd: '120', outstanding_vnd: '20' },
      { month: '2026-10-01', prior_months_vnd: '120', charges_vnd: '30', received_vnd: '100', end_of_month_vnd: '50', outstanding_vnd: '30' }],
    receipts: [
      { pid: 'PH-001', date: '2026-09-10', method: 'THU TIỀN', amount_vnd: '30', voided_on: null, voided_by_event: null,
        allocations: [{ month: '2026-08-01', kind: 'debt', amount_vnd: '30', superseded_by_event: null }] },
      { pid: 'PH-002', date: '2026-10-15', method: 'THU TIỀN', amount_vnd: '100', voided_on: null, voided_by_event: null,
        allocations: [{ month: '2026-08-01', kind: 'debt', amount_vnd: '70', superseded_by_event: null },
          { month: '2026-09-01', kind: 'debt', amount_vnd: '30', superseded_by_event: null }] },
      { pid: 'PH-003', date: '2026-10-20', method: 'THU TIỀN', amount_vnd: '5', voided_on: null, voided_by_event: null,
        allocations: [{ month: '2026-10-01', kind: 'debt', amount_vnd: '5', superseded_by_event: null }] }] });
  const block = key => root.innerHTML.match(new RegExp(`<section id="thang-${key}">.*?</section>`, 's'))[0];
  assert.doesNotMatch(block('2026-08'), /data-pid="PH-/);
  assert.match(block('2026-09'), /data-pid="PH-001"[^>]*>30<small class="[^"]*receipt-ref empty"[^>]*>\+<\/small><small class="receipt-allocation">Trừ nợ T8\/2026<\/small>/);
  assert.doesNotMatch(block('2026-09'), /PH-002/);
  assert.match(block('2026-10'), /data-pid="PH-002"[^>]*>100<small[^>]*>\+<\/small><small class="receipt-allocation">Trừ nợ T8\/2026 70 · T9\/2026 30<\/small>/);
  // Phiếu trừ đúng nợ tháng của mình: không ghi thêm chữ.
  assert.match(block('2026-10'), /data-pid="PH-003"[^>]*>5<small[^>]*>\+<\/small><\/td>/);
  // SO-GON-02: không còn cột "Còn nợ cộng dồn"; còn nợ cuối tháng ở dòng Tổng tháng (vùng phiếu thu) và thanh tháng.
  assert.match(block('2026-10'), /Đã thu<br>Còn nợ<\/td><td class="pay num subtotal-pay" colspan="2">100<br><span class="month-end-amount">50<\/span><\/td>/);
  assert.match(block('2026-10'), /Nợ các tháng trước: <b>120<\/b><\/span><span>Phát sinh: <b>30<\/b><\/span><span>Đã thu: <b>100<\/b><\/span><span class="month-end">Còn nợ cuối tháng: <b>50<\/b>/);
});

test('history formats every SQL event kind, snapshots and VN timestamp; hides unknown codes', async () => {
  // PHU-PHI-01: lệnh phụ phí có nhãn riêng và câu trước → sau (không lộ mã lệnh).
  const feeKinds = { add_trip_fees: 'Thêm phụ phí', set_trip_fee_type: 'Sửa phụ phí', replace_trip_fee: 'Sửa khoản phụ phí',
    void_trip_fee: 'Xóa khoản phụ phí', set_book_fee_columns: 'Đổi cột phụ phí riêng' };
  for (const [kind, label] of Object.entries(feeKinds)) {
    const fee = await livePage({ ...ledger(1), events: [{ id: 1, kind, actor: 'Người thử', at: '2026-10-20T01:02:00Z',
      before: { targets: [{ trip_id: 4, fee_lines: [{ id: 1, fee_type_id: 7, amount_vnd: '500' }] }], batch_count: 1, fee_columns: [] },
      after: { targets: [{ trip_id: 4, fee_lines: [{ id: 1, fee_type_id: 7, amount_vnd: '500' }, { fee_type_id: 7, amount_vnd: '1200', note: 'neo<1>' }] }], batch_count: 1, fee_columns: [7] } }] });
    assert.ok(fee.root.innerHTML.includes(label), kind);
    assert.ok(!fee.root.innerHTML.includes(kind), kind);
    assert.match(fee.root.innerHTML, kind === 'set_book_fee_columns' ? /Cột riêng: chỉ Khác → Loại #7/ : /#4: phụ phí 500 → 1\.700 \(Loại #7 1\.200 \(neo&lt;1&gt;\)\)/, kind);
  }
  // specs/v7-bang-gia-hieu-luc.md: nhãn bảng giá làm ở giai đoạn 2 (giao diện).
  const PENDING_UI_EVENT_KINDS = ['price_table_edit', 'price_table_apply'];
  for (const kind of PENDING_UI_EVENT_KINDS) {
    const pending = await livePage({ ...ledger(1), events: [{ id: 1, kind, actor: 'Người thử',
      at: '2026-10-20T01:02:00Z', before: { targets: [] }, after: { targets: [] } }] });
    assert.match(pending.root.innerHTML, /Thao tác khác/, kind);
    assert.ok(!pending.root.innerHTML.includes(kind), kind);
  }
  const kinds = { paste: 'Dán lô chuyến', price_edit: 'Sửa giá', adjust_trip: 'Điều chỉnh chuyến',
    adjust_month: 'Điều chỉnh cả tháng', receipt: 'Ghi thu', receipt_edit: 'Sửa thông tin phiếu', month_lock: 'Mở/khóa tháng',
    void: 'Hủy phiếu', reallocation: 'Phân bổ lại', import: 'Nhập số dư đầu', trip_review: 'Kết luận CHỜ KIỂM',
    receipt_image: 'Đính ảnh chứng từ', receipt_image_remove: 'Gỡ ảnh chứng từ' };
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
  const review = await livePage({ ...ledger(1), events: [{ id: 1, kind: 'trip_review', actor: 'Người thử', at: '2026-10-20T01:02:00Z',
    before: { trip: 3, container: 'FAKE<1>', status: 'pending_review' },
    after: { trip: 3, container: 'FAKE<1>', status: 'rejected', review_reason: 'trùng <sổ gốc>' } }] });
  assert.match(review.root.innerHTML, /Chuyến FAKE&lt;1&gt;: loại, không tính<\/p><small>Ghi chú\/lý do: trùng &lt;sổ gốc&gt;/);
  assert.doesNotMatch(root.innerHTML, /private_new_code|unknown_key|private_value|\[object Object\]|"amount_vnd"/);
  const image = await livePage({ ...ledger(1), events: [{ id: 1, kind: 'receipt_image_remove', actor: 'Người thử', at: '2026-10-20T01:02:00Z',
    before: { image: { id: 5, pid: 'PH-001' } }, after: { image: { id: 5, pid: 'PH-001', removed: true, reason: 'đính <nhầm>' } } }] });
  assert.match(image.root.innerHTML, /Phiếu PH-001 · gỡ 1 ảnh · Lý do: đính &lt;nhầm&gt;/);
  assert.doesNotMatch(image.root.innerHTML, /sha256|data_base64/);
  const sql = fs.readFileSync(require.resolve('../tools/v7_backend_functions.sql'), 'utf8');
  const written = [...sql.matchAll(/VALUES\s*\(\s*(?:customer_id|p_customer)\s*,\s*'([^']+)'/g)].map(match => match[1]);
  // Bốn loại NHAP-SHEET-01 chưa có nhãn trên giao diện (làm sau); tới lúc đó hiện "Thao tác khác".
  const pendingUi = ['trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete'];
  assert.deepEqual([...new Set(written)].filter(kind => !pendingUi.includes(kind) && !PENDING_UI_EVENT_KINDS.includes(kind) && !Object.hasOwn(feeKinds, kind)).sort(), Object.keys(kinds).sort());
});

test('locked month keeps trip cells read only and receipt entry usable', async () => {
  const { root } = await livePage({ ...ledger(1), today_month: '2026-10-01',
    months: [{ month: '2026-01-01', charges_vnd: '100', received_vnd: '0', outstanding_vnd: '100', end_of_month_vnd: '100' }],
    month_locks: [{ month: '2026-01-01', locked: true }],
    trips: [{ id: 1, month: '2026-01-01', status: 'confirmed', editable: false, info_editable: false,
      container: 'FAKE-LOCK', carrier: 'FAKE', event_date: '2026-01-10', origin: 'A', destination: 'B',
      unit_price_vnd: '100', other_fee_vnd: null, amount_vnd: '100' }], receipts: [], legacy_rows: [],
    adjustments: [], opening: [], source_exceptions: [], events: [] });
  const block = root.innerHTML.match(/<section id="thang-2026-01">.*?<\/section>/s)[0];
  assert.doesNotMatch(block, /data-trip="1"|data-kind="trip"|class="draft-input/);
  assert.match(block, /class="empty-entry receipt-amount"/);
  assert.match(block, /class="add-month-adjustment"[^>]*disabled/);
});

test('future receipt error appears beside date and releases pending command', async () => {
  const { root, listeners } = await livePage(ledger(1));
  root.fetcher = async () => reply(422, { error: 'FUTURE_RECEIPT_DATE', message: 'Ngày trả không được sau hôm nay.' });
  const error = { textContent: '' }, date = { value: '21/10/2026', focus() {} };
  const amount = { value: '10' };
  const row = { querySelector: selector => selector === '.receipt-date' ? date : selector === '.receipt-method' ? { value: 'THU TIỀN' } : selector === '.receipt-amount' ? amount : selector === '.receipt-reference' ? null : error };
  // Enter ở ô số tiền hay ô tham chiếu đều ghi hàng nhập phiếu chứa ô đó.
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
    booking: 'BK-FAKE', status: 'confirmed', trip_key: 'forged',
    unitPriceVnd: '10', actor: 'forged', total_vnd: '999', allocation: 'forged' }] });
  assert.deepEqual(posted.trips, [{ date: '20/10/2026', booking: 'BK-FAKE', container: 'FAKE', unitPriceVnd: '10' }]);
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
    const root = { innerHTML: '', listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; }, querySelector() { return null; } };
    const context = vm.createContext({ document: { querySelector: selector => selector === '#app' ? root : null, addEventListener() {} },
      window: { scrollY: 0, scrollTo() {} }, location: { search: live ? '?customer=7' : '' },
      URLSearchParams, structuredClone, Date, BigInt, setInterval: () => 0, crypto: { randomUUID: () => 'key' },
      fetch: async () => reply(200, data) });
    for (const name of live ? liveScripts : ['so-khach-v7-fixture.js', 'so-khach-v7-model.js', 'so-khach-v7-ui.js']) {
      vm.runInContext(fs.readFileSync(require.resolve(`./${name}`), 'utf8'), context, { filename: name });
    }
    return root;
  }
  const fixture = page(false);
  // Keep approved layout baseline; CSM adds only reference subrows, checked separately.
  // Baseline 22/10/2026: round-2 layout minus the Vết column (user test feedback).
  // 23/10/2026 (góp ý người dùng): bỏ hàng nhóm cột, "Từ tháng", "Chờ xử lý", nhãn Đã khóa/Đang mở; "Tổng tháng"; cột "Hãng tàu".
  assert.match(fixture.innerHTML, /class="reference-row"/);
  assert.match(fixture.innerHTML, /aria-label="Tham chiếu"/);
  assert.doesNotMatch(fixture.innerHTML, /Vết|NGUỒN|class="source"|colspan="14"|change-customer/);
  assert.equal(require('node:crypto').createHash('sha256').update(fixture.innerHTML.replace(/<tr class="reference-row">.*?<\/tr>/gs, '')).digest('hex'),
    '67d95ceb00e7bf1cf7cac022a8c6b00bfdac3150511586c4db9964dedd309408', 'fixture HTML must match the 23/10/2026 baseline');
  assert.match(fixture.innerHTML, /THÁNG 10\/2026/);
  assert.match(fixture.innerHTML, /Dán các dòng từ Sheet vào đây/);
  const paste = text => fixture.listeners.paste({ preventDefault() {},
    clipboardData: { getData: () => text }, target: { matches: selector => selector === '.paste-input',
      dataset: { month: '2026-10' }, closest: () => ({ querySelector: () => ({ textContent: '' }) }) } });
  paste('FAKE-NEW\tSHIP\t21/10/2026\tA\tB\t100\t\nFAKE-NEW\tSHIP\t24/10/2026\tA\tB\t100\t\nFAKE-SAFE\tSHIP\t21/10/2026\tA\tB\t200\t');
  const held = fixture.innerHTML.split('<tr>').find(row => row.includes('FAKE-NEW') && row.includes('24/10/2026'))?.split('</tr>')[0];
  assert.ok(held, 'duplicate row retained');
  assert.match(held, /CHỜ KIỂM/);
  assert.doesNotMatch(held, /class="num editable/);
  assert.match(fixture.innerHTML, /FAKE-SAFE/);
  const heldCount = () => fixture.innerHTML.split('<tr>').filter(row => row.split('</tr>')[0].includes('CHỜ KIỂM')).length;
  assert.equal(heldCount(), 1);
  paste('FAKE-NEW\tSHIP\t21/10/2026\tA\tB\t100\t');
  assert.equal(heldCount(), 2);
  assert.doesNotMatch(fixture.innerHTML, /Chờ xử lý|Từ tháng|class="badge|CHUYẾN HÀNG|Hãng tàu \/ số xe|Cộng tháng/);
  assert.match(fixture.innerHTML, /Tổng tháng 10\/2026/);
  const live = page(true, { ...ledger(1), months: [{ month: '2026-10-01', outstanding_vnd: '600', end_of_month_vnd: '600', charges_vnd: '1234567', received_vnd: '1233967' }],
    opening: [{ month: '2026-10-01', amount_vnd: '600' }], trips: [], receipts: [], adjustments: [],
    legacy_rows: [{ month: '2026-10-01', display: 'old', source_total_vnd: '600' }],
    source_exceptions: [{ month: '2026-10-01', exception_codes: ['HISTORICAL_DELTA_600'], source_charge_vnd: '1234567', source_receipt_vnd: '634567', source_cumulative_vnd: '600000' }], events: [] });
  await new Promise(resolve => setImmediate(resolve));
  // Import-quality flags stay in the DB/report, not on the ledger (user 20/10/2026).
  assert.doesNotMatch(live.innerHTML, /Chênh lịch sử 600đ|Cần kiểm tra nguồn|Thiếu mốc đối soát/);
  assert.match(live.innerHTML, /<tr class="legacy"/);
  // 23/10/2026: không còn chú thích "Từ sổ gốc", dòng "Theo sổ gốc" hay dòng số dư đầu. DA-THU-01 (28/10/2026): server
  // trả sẵn phát sinh/đã thu như Sheet; trang vẽ nguyên số, không dời số theo số dư đầu.
  assert.doesNotMatch(live.innerHTML, /Từ sổ gốc|Theo sổ gốc|source-total|legacy-caption|Nợ tháng này còn lại/);
  assert.match(live.innerHTML, /Tổng tháng 10\/2026 <button[^>]*>[^<]*<\/button><\/td><td class="num fee">[^<]*<\/td><td class="num ">1\.234\.567<\/td><td class="pay pay-start">Đã thu<br>Còn nợ<\/td><td class="pay num subtotal-pay" colspan="2">1\.233\.967<br>/);
  assert.doesNotMatch(live.innerHTML, /\[object Object\]/);
  assert.match(live.innerHTML, /Tổng còn nợ \(mọi tháng\)<\/span><strong>10<\/strong>/);
  // Tháng hiện tại chưa có dữ liệu vẫn có khối ghi thu và bảng nhập; tháng không có dòng Sheet vẽ thẳng từ GET;
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
  // Hàng nhập phiếu và bảng nhập chuyến ở mọi tháng đang mở: tháng hiện tại và tháng cũ đã mở khóa (8/2026);
  // tháng khóa (9/2026) không có. Không còn ô "Dán các dòng từ Sheet".
  const block = key => newMonth.innerHTML.match(new RegExp(`<section id="thang-${key}">.*?</section>`, 's'))[0];
  for (const key of ['2026-11', '2026-08']) {
    assert.match(block(key), new RegExp(`class="draft-input[^"]*" data-month="${key}"`));
    assert.match(block(key), /class="empty-entry receipt-date".*class="receipt-reference"/s);
  }
  assert.doesNotMatch(block('2026-09'), /class="draft-input/);
  assert.match(block('2026-09'), /class="empty-entry receipt-amount"/);
  assert.doesNotMatch(newMonth.innerHTML, /paste-input|Dán các dòng từ Sheet vào đây/);
  assert.match(newMonth.innerHTML, /<table class="ledger locked" aria-label="Sổ khách tháng 9\/2026">/);
  assert.match(newMonth.innerHTML, /<table class="ledger" aria-label="Sổ khách tháng 8\/2026">/);
  assert.match(newMonth.innerHTML, /<td class="num ">1\.234\.567<\/td><td class="pay pay-start">Đã thu<br>Còn nợ<\/td><td class="pay num subtotal-pay" colspan="2">1\.234\.067<br>/);
  assert.match(newMonth.innerHTML, /THÁNG 9\/2026.*Nợ các tháng trước: <b>0<\/b>/);
  assert.match(newMonth.innerHTML, /<div class="book-head"><div class="picker-slot"><\/div><button class="history-toggle"/);
  assert.doesNotMatch(newMonth.innerHTML, /change-customer|Chờ xử lý|Từ tháng|class="badge/);
  // Tháng chỉ có dòng Sheet: một dòng Tổng tháng như Sheet, không dòng trống, không dòng "nợ còn lại".
  const carried = page(true, { ...ledger(5), today_month: '2026-10-01',
    months: [
      { month: '2026-02-01', prior_months_vnd: '177', charges_vnd: '307', received_vnd: '484', end_of_month_vnd: '0', outstanding_vnd: '0' },
      { month: '2026-10-01', prior_months_vnd: '0', charges_vnd: '700', received_vnd: '0', end_of_month_vnd: '700', outstanding_vnd: '700' }],
    opening: [{ month: '2026-02-01', amount_vnd: '0' }, { month: '2026-10-01', amount_vnd: '700' }],
    legacy_rows: [{ month: '2026-02-01', kind: 'trip', display: { row: 3, container: 'FAKE-OLD' }, source_total_vnd: '307' }],
    source_exceptions: [{ month: '2026-02-01', source_charge_vnd: '307', source_receipt_vnd: '484', source_cumulative_vnd: '232' }],
    trips: [], receipts: [], adjustments: [], events: [] });
  await new Promise(resolve => setImmediate(resolve));
  const february = carried.innerHTML.match(/<section id="thang-2026-02">.*?<\/section>/s)[0];
  assert.doesNotMatch(february, /Cộng tháng|Nợ tháng này còn lại|<tr>\s*<td class=""><\/td>/);
  assert.match(february, /<tr class="subtotal"><td colspan="8">Tổng tháng 2\/2026 <button class="add-month-adjustment"[^>]*>[^<]*<\/button><\/td><td class="num fee">[^<]*<\/td><td class="num ">307<\/td><td class="pay pay-start">Đã thu<br>Còn nợ<\/td><td class="pay num subtotal-pay" colspan="2">484<br><span class="month-end-amount">0<\/span><\/td><\/tr><tr class="spacer">/);
  const october = carried.innerHTML.match(/<section id="thang-2026-10">.*?<\/section>/s)[0];
  assert.doesNotMatch(october, /Nợ tháng này còn lại/);
  assert.match(october, /Tổng tháng 10\/2026 <button[^>]*>[^<]*<\/button><\/td><td class="num fee">[^<]*<\/td><td class="num ">700<\/td>/);
  assert.match(october, /class="empty-entry receipt-amount"/);
  const pending = page(true, { ...ledger(1), today_month: '2026-10-01',
    months: [{ month: '2026-10-01', charges_vnd: '200', outstanding_vnd: '200', end_of_month_vnd: '200' }],
    trips: [{ id: 1, month: '2026-10-01', container: 'FAKE-HELD', status: 'pending_review', unit_price_vnd: '100', other_fee_vnd: null, amount_vnd: null },
      { id: 2, month: '2026-10-01', container: 'FAKE-CLEAN', status: 'confirmed', unit_price_vnd: '200', other_fee_vnd: null, amount_vnd: '200' }],
    receipts: [], adjustments: [], legacy_rows: [], source_exceptions: [], events: [] });
  await new Promise(resolve => setImmediate(resolve));
  const heldLive = pending.innerHTML.match(/<tr data-row="trip-1"><td[^>]*>1<\/td>\s*<td[^>]*>FAKE-HELD<\/td>.*?<\/tr>/s)?.[0];
  assert.ok(heldLive);
  assert.match(heldLive, /CHỜ KIỂM/);
  assert.doesNotMatch(heldLive, /class="num editable/);
  assert.match(pending.innerHTML, /data-trip="2"/);
  assert.doesNotMatch(pending.innerHTML, /chuyến chưa có giá/);
  const noBaseline = page(true, { ...ledger(0), status: 'NO_BASELINE', total_outstanding_vnd: null,
    source_exceptions: [{ month: '2026-10-01', exception_codes: ['NO_BASELINE'] }] });
  await new Promise(resolve => setImmediate(resolve));
  assert.match(noBaseline.innerHTML, /Khách chưa có số dư đầu hiệu lực/);
  assert.doesNotMatch(noBaseline.innerHTML, /Thiếu mốc đối soát nguồn|NO_BASELINE/);
  assert.doesNotMatch(noBaseline.innerHTML, /class="receipt-amount"/);
});

test('offset commands send numeric ids/versions of both books and one idempotency key per command', async () => {
  const calls = [];
  const fetcher = async (path, init) => {
    calls.push({ path, body: init?.body ? JSON.parse(init.body) : null });
    return path.startsWith('/api/v7/ledger') ? reply(200, ledger(4)) : reply(200, { offset_pair_id: 9 });
  };
  let n = 0;
  const api = create({ customerId: 7, fetcher, key: () => `k${++n}` });
  await api.read();
  const saved = await api.submitOffset('offset', { source_customer_id: '3', source_version: '12', date: '2026-10-20', amount_vnd: '50000000' });
  assert.equal(saved.status, 'saved');
  assert.deepEqual(calls.find(call => call.path === '/api/v7/offsets').body, { target_customer_id: 7, target_version: 4,
    idempotency_key: 'k1', source_customer_id: 3, source_version: 12, date: '2026-10-20', amount_vnd: '50000000' });
  await api.submitOffset('offsetVoid', { other_version: '2', offset_pair_id: '9', reason: 'nhập nhầm', customer_id: 99, amount_vnd: '1' });
  assert.deepEqual(calls.find(call => call.path === '/api/v7/offsets/void').body, { customer_id: 7, expected_version: 4,
    idempotency_key: 'k2', other_version: 2, offset_pair_id: 9, reason: 'nhập nhầm' });
  await api.submitOffset('offsetDate', { other_version: 2, offset_pair_id: 9, date: '2026-10-21' });
  assert.deepEqual(calls.find(call => call.path === '/api/v7/offsets/date').body, { customer_id: 7, expected_version: 4,
    idempotency_key: 'k3', other_version: 2, offset_pair_id: 9, date: '2026-10-21' });
});

test('offset command rejects missing/unsafe fields and non-string money before any request', async () => {
  const calls = [];
  const api = create({ customerId: 7, fetcher: async path => { calls.push(path); return reply(200, ledger(1)); } });
  await api.read();
  await assert.rejects(api.submitOffset('offset', { source_customer_id: 3, source_version: 1, date: '2026-10-20' }), /Thiếu thông tin/);
  await assert.rejects(api.submitOffset('offset', { source_customer_id: 3, source_version: 1, date: '2026-10-20', amount_vnd: 5 }), /chuỗi VND/);
  await assert.rejects(api.submitOffset('offset', { source_customer_id: '9007199254740993', source_version: 1, date: '2026-10-20', amount_vnd: '5' }), /không hợp lệ/);
  await assert.rejects(api.submitOffset('nope', {}), /không hợp lệ/);
  assert.deepEqual(calls, ['/api/v7/ledger?customer=7']);
});

test('offset STALE_LEDGER reloads the book and reports stale; server errors keep code and detail for the message table', async () => {
  const outcomes = [];
  let mode = 'stale';
  const fetcher = async path => {
    if (path.startsWith('/api/v7/ledger')) return reply(200, ledger(mode === 'stale' ? 5 : 1));
    return mode === 'stale' ? reply(409, { error: 'STALE_LEDGER' }) : reply(422, { error: 'OFFSET_EXCEEDS_CREDIT', message: 'x', available_credit_vnd: '4000' });
  };
  const notices = [];
  const api = create({ customerId: 7, fetcher, onNotice: text => notices.push(text) });
  await api.read();
  outcomes.push(await api.submitOffset('offset', { source_customer_id: 3, source_version: 1, date: '2026-10-20', amount_vnd: '5' }));
  assert.equal(outcomes[0].status, 'stale');
  assert.ok(notices.includes(stale));
  assert.equal(api.hasPending(), false);
  mode = 'error';
  outcomes.push(await api.submitOffset('offset', { source_customer_id: 3, source_version: 1, date: '2026-10-20', amount_vnd: '5' }));
  assert.equal(outcomes[1].status, 'error');
  assert.equal(outcomes[1].result.error, 'OFFSET_EXCEEDS_CREDIT');
  assert.equal(outcomes[1].result.available_credit_vnd, '4000');
});

test('offset unknown result keeps the same key for retry', async () => {
  const keys = [];
  let fail = true;
  const fetcher = async (path, init) => {
    if (path.startsWith('/api/v7/ledger')) return reply(200, ledger(1));
    keys.push(JSON.parse(init.body).idempotency_key);
    if (fail) throw Error('network');
    return reply(200, {});
  };
  let n = 0;
  const api = create({ customerId: 7, fetcher, key: () => `k${++n}` });
  await api.read();
  const first = await api.submitOffset('offset', { source_customer_id: 3, source_version: 1, date: '2026-10-20', amount_vnd: '5' });
  assert.equal(first.status, 'unknown');
  assert.equal(api.hasPending(), true);
  fail = false;
  await api.retry();
  assert.deepEqual(keys, ['k1', 'k1']);
});

test('loadOffsetSources and readOther read without touching the open book snapshot', async () => {
  const fetcher = async path => path.startsWith('/api/v7/offset-sources') ? reply(200, { sources: [{ customer_id: 3 }] })
    : path === '/api/v7/ledger?customer=3' ? reply(200, { ...ledger(8), customer_id: 3 }) : reply(200, ledger(2));
  const api = create({ customerId: 7, fetcher });
  await api.read();
  assert.deepEqual(await api.loadOffsetSources(), [{ customer_id: 3 }]);
  assert.equal((await api.readOther(3)).version, 8);
  assert.equal(api.snapshot().version, 2);
  await assert.rejects(api.readOther(4), /không hợp lệ/);
});

test('CHỜ KIỂM: nút bấm được, rejected ghi ĐÃ LOẠI và không sửa được', async () => {
  const trips = [
    { id: 1, month: '2026-10-01', container: 'FAKE-HELD', status: 'pending_review', review_reason: 'WEB_DUPLICATE', unit_price_vnd: '100', other_fee_vnd: null, amount_vnd: null },
    { id: 2, month: '2026-10-01', container: 'FAKE-GONE', status: 'rejected', unit_price_vnd: '100', other_fee_vnd: null, amount_vnd: null },
    { id: 3, month: '2026-10-01', container: 'FAKE-OK', status: 'confirmed', unit_price_vnd: '100', other_fee_vnd: '5', amount_vnd: '105' }];
  const { root } = await livePage({ ...ledger(1), months: [{ month: '2026-10-01', outstanding_vnd: '105' }], trips });
  assert.match(root.innerHTML, /<button type="button" class="review-open" data-trip="1"[^>]*>CHỜ KIỂM<\/button>/);
  assert.doesNotMatch(root.innerHTML, /review-open" data-trip="[23]"/);
  assert.match(root.innerHTML, /<td class="num trip-rejected">ĐÃ LOẠI<\/td>/);
  assert.doesNotMatch(root.innerHTML, /data-trip="2"/);
  // 23/10/2026: bỏ bộ đếm "Chờ xử lý" ở đầu sổ; chữ CHỜ KIỂM ngay trên dòng là đủ.
  assert.doesNotMatch(root.innerHTML, /chuyến CHỜ KIỂM|Chờ xử lý/);
});

test('CHỜ KIỂM: mở/đóng dòng kết luận, lý do trống không gửi, gửi đúng payload hai quyết định', async () => {
  const trips = [{ id: 1, month: '2026-10-01', container: 'FAKE-HELD', status: 'pending_review', review_reason: 'BASELINE_DATE_WINDOW', unit_price_vnd: '100', other_fee_vnd: null, amount_vnd: null }];
  const { root, listeners } = await livePage({ ...ledger(4), months: [{ month: '2026-10-01', outstanding_vnd: '0' }], trips });
  const sent = [];
  root.fetcher = async (path, options) => {
    if (options?.method === 'POST') { sent.push({ path, body: JSON.parse(options.body) }); return reply(200, {}); }
    return reply(200, { ...ledger(5), trips });
  };
  let prompts = [];const opens = [];
  const tripRow = { nextElementSibling: null, insertAdjacentHTML(_where, html) { this.nextElementSibling = promptRow(html); prompts = [this.nextElementSibling]; } };
  const input = { value: '', focus() {} };
  const error = { textContent: '' };
  const promptRow = html => ({ html, dataset: { trip: '1' }, classList: { contains: name => name === 'review-prompt' }, remove() { prompts = []; tripRow.nextElementSibling = null; },
    querySelector: selector => selector === '.review-reason' ? input : selector === '.review-error' ? error : null });
  const button = { dataset: { trip: '1' }, closest: () => tripRow, setAttribute(_n, value) { opens.push(value); } };
  root.querySelectorAll = selector => selector === '.review-prompt' ? prompts.slice() : [button];
  const click = target => listeners.click({ target: { closest: selector => target === selector ? (selector === '.review-open' ? button : prompts[0] ?? null) : (selector === '.review-prompt' && prompts[0] && target !== '.review-open' ? prompts[0] : null) } });

  await click('.review-open');
  assert.equal(prompts.length, 1);
  for (const text of ['Chuyến FAKE-HELD đang CHỜ KIỂM', 'Cùng container, lệch ngày ≤3 ngày với dòng sổ gốc', 'Lý do kết luận', 'Tính vào sổ', 'Loại, không tính', 'Thôi']) assert.ok(prompts[0].html.includes(text), text);
  assert.match(prompts[0].html, /maxlength="500"/);
  await click('.review-open');
  assert.equal(prompts.length, 0, 'bấm lần nữa thì đóng');
  await click('.review-open');
  await click('.review-cancel');
  assert.equal(prompts.length, 0, 'Thôi đóng dòng');
  await click('.review-open');

  await click('.review-confirm');
  assert.equal(error.textContent, 'Cần nhập lý do kết luận');
  assert.equal(sent.length, 0);
  input.value = '   ';
  await click('.review-reject');
  assert.equal(sent.length, 0);

  input.value = '  đúng là chuyến mới  ';
  await click('.review-confirm');
  input.value = 'trùng sổ gốc';
  await click('.review-reject');
  assert.deepEqual(sent.map(item => item.path), ['/api/v7/trips/review', '/api/v7/trips/review']);
  assert.deepEqual(sent.map(({ body }) => Object.fromEntries(Object.entries(body).filter(([name]) => name !== 'idempotency_key'))), [
    { customer_id: 7, expected_version: 4, trip_id: 1, decision: 'confirm', reason: 'đúng là chuyến mới' },
    { customer_id: 7, expected_version: 5, trip_id: 1, decision: 'reject', reason: 'trùng sổ gốc' }]);
  input.value = 'x'.repeat(501);
  await click('.review-confirm');
  assert.equal(error.textContent, 'Lý do tối đa 500 ký tự');
  assert.equal(sent.length, 2);
});

test('MH-01: nhóm khách theo mặt hàng + phương thức, Chưa phân loại cuối, tìm không dấu theo tên hoặc nhóm', () => {
  const { groupCustomers } = require('./so-khach-v7-api.js');
  const rows = [
    { id: 1, name: 'Khách A', commodity: 'Sầu riêng', transport_mode: 'CANG' },
    { id: 2, name: 'Khách B', commodity: null, transport_mode: null },
    { id: 3, name: 'Khách C', commodity: 'Chuối', transport_mode: null },
    { id: 4, name: 'Khách Đ', commodity: 'Sầu riêng', transport_mode: 'BO' },
    { id: 5, name: 'Khách E', commodity: 'Sầu riêng', transport_mode: 'CANG' },
  ];
  const all = groupCustomers(rows);
  assert.deepEqual(all.groups.map(g => [g.label, g.rows.map(r => r.id)]),
    [['Chuối', [3]], ['Sầu riêng · bộ', [4]], ['Sầu riêng · cảng', [1, 5]], ['Chưa phân loại', [2]]]);
  assert.deepEqual(all.found.map(r => r.id), [3, 4, 1, 5, 2]);
  assert.equal(all.labelled, true);
  assert.deepEqual(groupCustomers(rows, 'sau rieng').found.map(r => r.id), [4, 1, 5]);
  assert.deepEqual(groupCustomers(rows, 'SAU RIENG BO').found.map(r => r.id), [4]);
  assert.deepEqual(groupCustomers(rows, 'khach d').found.map(r => r.id), [4]);
  assert.deepEqual(groupCustomers(rows, 'chua phan').found.map(r => r.id), [2]);
  // DB chưa gán mặt hàng nào: danh sách phẳng, không có tiêu đề nhóm.
  const flat = groupCustomers(rows.map(r => ({ ...r, commodity: null })), '');
  assert.equal(flat.labelled, false);
  assert.deepEqual(flat.found.map(r => r.id), [1, 2, 3, 4, 5]);
});

test('tên Sheet và mặt hàng hiện trên sổ; tên V7 và alias vẫn tìm được', () => {
  const { groupCustomers, customerLabel, customerLabels } = require('./so-khach-v7-api.js');
  const rows = [
    { id: 7, name: 'OLD A', display_name: 'SHEET', aliases: ['TÊN PHỤ'], commodity: 'Chuối' },
    { id: 8, name: 'OLD B', display_name: 'SHEET', aliases: [], commodity: 'Dừa' },
    { id: 9, name: 'UNMAPPED', commodity: null },
  ];
  assert.equal(customerLabel(rows[0]), 'SHEET · Chuối');
  assert.equal(customerLabel(rows[1]), 'SHEET · Dừa');
  assert.equal(customerLabel(rows[2]), 'UNMAPPED');
  assert.deepEqual(groupCustomers(rows, 'ten phu').found.map(row => row.id), [7]);
  assert.deepEqual(groupCustomers(rows, 'old b').found.map(row => row.id), [8]);
  assert.deepEqual(groupCustomers(rows, 'sheet').found.map(row => row.id), [7, 8]);
  assert.deepEqual([...customerLabels([
    { id: 10, name: 'OLD A', display_name: 'SHEET', commodity: 'Chuối' },
    { id: 11, name: 'OLD B', display_name: 'SHEET', commodity: 'Chuối' },
  ])], [[10, 'SHEET · Chuối · sổ 10'], [11, 'SHEET · Chuối · sổ 11']]);
});
