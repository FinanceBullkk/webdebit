/* DEBIT-NOTE-03: mẫu debit note v4 (docs/debit-note-v4/SPEC.md) — số của dữ liệu mẫu, chia trang, 6 phép kiểm, dựng từ sổ V7. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const model = require('./so-khach-v7-model.js');
const v4 = require('./debit-note-v4.js');

const ROOT = path.join(__dirname, '..', '..');
const config = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'web', 'debit-note-config.default.json'), 'utf8'));
const sample = name => JSON.parse(fs.readFileSync(path.join(ROOT, 'docs', 'debit-note-v4', 'data', `${name}.json`), 'utf8'));
const KEYS = { lump_sum: 'LUMP_SUM', storage: 'STORAGE', generator_electricity: 'GENSET', overstay: 'OVERSTAY', hc_fee: 'HC_FEE' };
const blocks = doc => v4.checks(doc).filter(item => item.level === 'block');

test('Dữ liệu mẫu ra đúng mục "expected": số container, tổng từng cột, Total, Outstanding, cột hiện', () => {
  for (const name of ['sample-14', 'sample-30', 'sample-8-an-cot']) {
    const data = sample(name), doc = v4.fromSample(data, config), want = data.expected;
    assert.equal(doc.total.count, want.container_count, name);
    for (const [key, value] of Object.entries(want.column_totals)) assert.equal(doc.total.cells[KEYS[key]] ?? 0n, BigInt(value), `${name} ${key}`);
    assert.equal(doc.total.amount, BigInt(want.total_amount), name);
    assert.equal(doc.account.thisNote, BigInt(want.this_debit_note), name);
    assert.equal(doc.account.outstanding, BigInt(want.outstanding_balance), name);
    if (want.visible_fee_columns) assert.deepEqual(doc.columns.map(column => column.code), want.visible_fee_columns.map(key => KEYS[key]), name);
    assert.deepEqual(blocks(doc), [], name);
  }
});

test('Định dạng: phẩy ngăn nghìn, 0 là "–", số âm trong ngoặc, ngày "04 Nov 2026", bỏ dấu tiếng Việt, tách tên Hán', () => {
  assert.equal(v4.money(1070000000n), '1,070,000,000');
  assert.equal(v4.money(0n), '–');
  assert.equal(v4.money(-6594000000n), '(6,594,000,000)');
  assert.equal(v4.money(null), '');
  assert.equal(v4.dateText('2026-11-04'), '04 Nov 2026');
  assert.equal(v4.periodText('2026-11'), 'Nov 2026');
  assert.equal(v4.latin('Công ty Đồng Tháp'), 'Cong ty Dong Thap');
  assert.deepEqual(v4.splitName('FANYA 泛亚'), { en: 'FANYA', zh: '泛亚' });
});

test('Chia trang (SPEC mục 6): Total luôn kèm ít nhất 3 dòng; 16 → 1, 17 → 14 + 3, 30 → 20 + 10, 60 → 20 + 23 + 17', () => {
  // Sức chứa một hàng chữ đo trên trang mẫu: đơn 16, đầu 20, giữa 23, cuối 17.
  const cap = { single: 16, first: 20, middle: 23, last: 17 };
  const split = count => v4.paginate(Array.from({ length: count }, (_, index) => index), (kind, rows) => rows.length <= cap[kind])
    .map(page => `${page.kind}:${page.rows.length}`).join(' + ');
  assert.equal(split(16), 'single:16');
  assert.equal(split(17), 'first:14 + last:3');
  assert.equal(split(30), 'first:20 + last:10');
  assert.equal(split(60), 'first:20 + middle:23 + last:17');
  assert.equal(split(1), 'single:1');
  // Dòng nào cũng không vừa (chữ quá dài) vẫn ra trang, không lặp mãi.
  assert.equal(v4.paginate([1, 2], () => false).map(page => page.rows.length).join('+'), '1+1');
});

test('Sáu phép kiểm (SPEC mục 7) chặn từng ca cố tình sai, câu báo nêu phép và các con số', () => {
  const fresh = () => v4.fromSample(sample('sample-14'), config);
  const cases = [
    [1, doc => { doc.rows[2].amount += 1n; }, /Phép 1: dòng 3 HTHU2611210: Amount 75,000,001 ≠ 70,000,000 \+ – \+ – \+ 5,000,000 \+ – = 75,000,000\./],
    [2, doc => { doc.total.amount += 1000n; }, /Phép 2: Total Amount 1,070,001,000 ≠ tổng Amount các dòng 1,070,000,000\./],
    [3, doc => { doc.total.cells.STORAGE = 0n; }, /Phép 3: tổng cột STORAGE in – ≠ cộng các dòng 5,000,000\./],
    [4, doc => { doc.total.count = 15; }, /Phép 4: có 14 dòng container nhưng dòng Total ghi 15 containers\./],
    [5, doc => { doc.account.thisNote = 1n; }, /Phép 5: This debit note 1 ≠ Total Amount 1,070,000,000\./],
    [6, doc => { doc.account.outstanding += 1n; }, /Phép 6: Opening 25,406,128,759 \+ This debit note 1,070,000,000 − Payments 6,594,000,000 ≠ Outstanding 19,882,128,760\./],
  ];
  for (const [rule, tamper, message] of cases) {
    const doc = fresh();
    tamper(doc);
    const found = blocks(doc);
    assert.ok(found.some(item => item.rule === rule && message.test(item.text)), `phép ${rule}: ${found.map(item => item.text).join(' | ')}`);
  }
  // Phí nằm ở cột bị ẩn cũng là sai phép 1 (in ra không cộng được).
  const hidden = v4.fromSample(sample('sample-8-an-cot'), config);
  hidden.rows[0].cells.HC_FEE = 1000n;
  assert.ok(blocks(hidden).some(item => item.rule === 1 && /cột không hiện \(HC_FEE\)/.test(item.text)));
});

// Sổ V7 (bản GET) có cột phụ phí riêng Điện, Neo; loại khác rơi vào Khác; tháng có điều chỉnh 1.000.000.
function ledger() {
  const trip = (id, extra) => ({ id, month: '2026-11-01', status: 'confirmed', deleted: false, carrier: 'IAL', shipper: 'Công ty Ánh', origin: 'TIEN GIANG',
    destination: 'QINGDAO', is_missing_price: false, is_fee_only: false, fee_lines: [], ...extra });
  return {
    trips: [
      trip(1, { container: 'TGHU1111111', event_date: '2026-11-09', unit_price_vnd: '70000000', amount_vnd: '75000000', fee_lines: [{ fee_type_id: 1, amount_vnd: '5000000' }] }),
      trip(2, { container: 'TGHU2222222', event_date: '2026-11-02', unit_price_vnd: '80000000', amount_vnd: '82000000',
        fee_lines: [{ fee_type_id: 4, amount_vnd: '1500000' }, { fee_type_id: 5, amount_vnd: '500000' }] }),
      trip(3, { container: 'TGHU3333333', event_date: '2026-11-03', status: 'pending_review', unit_price_vnd: '1', amount_vnd: '1' }),
      trip(4, { container: '', event_date: '2026-11-20', unit_price_vnd: null, amount_vnd: '300000', is_fee_only: true, fee_lines: [{ fee_type_id: 3, amount_vnd: '300000' }] }),
      trip(5, { container: 'TGHU5555555', month: '2026-10-01', event_date: '2026-10-30', unit_price_vnd: '9', amount_vnd: '9' }),
    ],
    legacy_rows: [{ kind: 'trip', month: '2026-11-01', editable: false, source_total_vnd: '60000000', fee_lines: [],
      display: { container: 'ABCU1234560', carrier: 'SITC', shipper: 'B', date: '2026-11-02', from: 'Dak Lak', to: 'Nansha', unit_price: '60000000' } }],
    months: [{ month: '2026-11-01', prior_months_vnd: '1000000000', charges_vnd: '218300000', received_vnd: '500000000', end_of_month_vnd: '718300000' }],
    receipts: [{ date: '2026-11-04', voided_by_event: null }, { date: '2026-11-15', voided_by_event: 9 }],
    outgoing_offsets: [{ date: '2026-11-10', voided_by_event: null }],
  };
}
const feeTypes = [{ id: 1, name: 'Neo' }, { id: 2, name: 'Điện' }, { id: 3, name: 'Khác' }, { id: 4, name: 'Phụ phí ban đầu' }, { id: 5, name: 'Health cert' }];
const build = (data = ledger()) => v4.fromLedger(data, '2026-11', { model, feeTypes, feeColumnIds: [2, 1], config,
  form: { number: 'HTH-2611-001', issueDate: '', customer: { nameEn: 'FANYA', nameZh: '泛亚' } } });

test('Từ sổ V7: cột theo cột phụ phí của sổ + Khác, ẩn cột cả chứng từ bằng 0, xếp theo ngày rồi số container, phí lẻ cuối bảng', () => {
  const doc = build();
  assert.deepEqual(doc.columns.map(column => `${column.en} ${column.cn}`), ['Unit price 单价', 'Overstay 押车', 'Other fees 其他费用']);
  assert.deepEqual(doc.rows.map(row => [row.no, row.container, row.date]), [[1, 'ABCU1234560', '2026-11-02'], [2, 'TGHU2222222', '2026-11-02'],
    [3, 'TGHU1111111', '2026-11-09'], [null, '', '2026-11-20']]);
  assert.deepEqual(doc.rows[1].cells, { LUMP_SUM: 80000000n, OTHER: 2000000n });   // Phụ phí ban đầu + Health cert không phải cột riêng → Khác
  assert.equal(doc.rows[1].shipper, 'Cong ty Anh');   // không in tiếng Việt
  assert.deepEqual([doc.rows[1].place.text, doc.rows[1].pod.text], ['Tien Giang', 'Qingdao']);
  assert.deepEqual(doc.rows[3].cells, { LUMP_SUM: null, OTHER: 300000n });
  assert.equal(doc.total.count, 3);
  assert.equal(doc.total.amount, 217300000n);
  assert.deepEqual(doc.total.cells, { LUMP_SUM: 210000000n, OVERSTAY: 5000000n, OTHER: 2300000n });
  assert.deepEqual(blocks(doc), []);
  assert.ok(v4.checks(doc).some(item => item.level === 'info' && /1 chuyến đang CHỜ KIỂM/.test(item.text)));
});

test('ACCOUNT STATUS từ months[] của máy chủ: Opening = nợ trước tháng; Payments = thu + cấn trừ + điều chỉnh; Outstanding = cuối tháng', () => {
  const doc = build();
  assert.deepEqual(doc.account, { opening: 1000000000n, openingDate: '2026-11-01', thisNote: 217300000n, payments: 499000000n, paymentsDate: '2026-11-10',
    outstanding: 718300000n, received: 500000000n, adjustments: 1000000n });
  assert.ok(v4.checks(doc).some(item => item.level === 'info' && /điều chỉnh 1,000,000 đ.*Payments received/.test(item.text)));
  // Máy chủ trả số cuối tháng không khớp: phép 6 chặn.
  const data = ledger();
  data.months[0].end_of_month_vnd = '718300001';
  assert.ok(blocks(build(data)).some(item => item.rule === 6));
  // Thành tiền của sổ khác đơn giá + phí: phép 1 chặn; thiếu giá: chặn, không coi là 0.
  const off = ledger();
  off.trips[0].amount_vnd = '76000000';
  assert.ok(blocks(build(off)).some(item => item.rule === 1 && /TGHU1111111: Amount 76,000,000/.test(item.text)));
  const missing = ledger();
  Object.assign(missing.trips[0], { is_missing_price: true, unit_price_vnd: null });
  assert.ok(blocks(build(missing)).some(item => /1 dòng chưa có giá/.test(item.text)));
  // Không có số tháng của máy chủ: chặn.
  assert.ok(blocks(build({ ...ledger(), months: [] })).some(item => /ACCOUNT STATUS/.test(item.text)));
});

test('HTML trang: đủ 4 khối ở trang đơn, ô trống in [Tên trường], không cột B/L, dòng cuối trang không kẻ, Total chữ navy', () => {
  const doc = build();
  const html = v4.pageHtml(doc, 'single', doc.rows, 1, 1);
  for (const block of ['LH', 'INFO', 'TABLE', 'BOTTOM']) assert.match(html, new RegExp(`data-blk="${block}"`));
  for (const label of ['[Issue date]', '[Tax ID]', '[Phone]', '[Customer legal name &amp; address]', '[Contact]', '[Beneficiary]', '[Bank]', '[Account no.]', '[SWIFT code]'])
    assert.ok(html.includes(label), label);
  assert.doesNotMatch(html, /B\/L no\./);
  assert.match(html, /Total, 3 containers<span style="font-weight: 400"> · 合计<\/span>/);
  assert.match(html, /color: #14304F">217,300,000<\/span><\/div><\/div>/);
  const rows = html.match(/<div data-row [^>]*>/g);
  assert.equal(rows.length, 4);
  assert.ok(rows.slice(0, -1).every(row => row.includes('border-bottom: 1px solid #B8C0CB')) && !rows.at(-1).includes('border-bottom'));
  assert.match(html, /Payments received · 本期已收款<\/span><span>10 Nov 2026<\/span><span style="text-align: right; padding-left: 0; margin-right: -0.333em">\(499,000,000\)/);
  assert.match(html, /Page 1 of 1/);
  assert.doesNotMatch(html, /[À-ỹ]/u);   // không chữ tiếng Việt có dấu
  // Trang đầu: không Total, không khối thanh toán, chân trang "Continued"; trang giữa: đầu trang rút gọn.
  const first = v4.pageHtml(doc, 'first', doc.rows.slice(0, 2), 1, 2);
  assert.doesNotMatch(first, /data-total|data-blk="BOTTOM"/);
  assert.match(first, /Continued on next page · 续下页<\/span><span>Page 1 of 2/);
  assert.match(v4.pageHtml(doc, 'middle', doc.rows.slice(2, 3), 2, 3), /Debit Note No\. 账单号 HTH-2611-001 · Bill to 客户 FANYA 泛亚 · Billing Period 账单期间 Nov 2026 · Currency 币种 VND/);
});
