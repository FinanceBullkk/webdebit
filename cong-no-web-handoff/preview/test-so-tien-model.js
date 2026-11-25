// SO-TIEN P0-a lát 2: phần không vẽ của Sổ tiền và Đối soát ngày (so-tien-model.js). Dữ liệu bịa; hình dạng lô chờ theo đúng
// tien._classify của lát 1 (dòng nghi trùng mềm F ≤ E có đúng một ứng viên mềm, giao dịch cùng tiền còn lại là UNMATCHED_EXISTING).
const assert = require('node:assert/strict');
const test = require('node:test');
const M = require('./so-tien-model.js');

test('chữ ngày, tiền: không qua múi giờ, null là —, chuỗi không phải số giữ nguyên văn', () => {
  assert.equal(M.vnDate('2026-11-24'), '24/11/2026');
  assert.equal(M.shortDate('2026-11-24'), '24/11');
  assert.equal(M.vnDate(null), '—');
  assert.equal(M.weekday('2026-11-24'), 'Thứ Ba');
  assert.equal(M.weekday('2026-11-22'), 'Chủ nhật');
  assert.equal(M.daysBetween('2026-11-20', '2026-11-25'), 5);
  assert.equal(M.addDays('2026-11-30', 1), '2026-12-01');
  assert.equal(M.addDays('2026-03-01', -1), '2026-02-28');
  assert.equal(M.money(null), '—');
  assert.equal(M.money('1234567'), '1.234.567 đ');
  assert.equal(M.money('-25000'), '−25.000 đ', 'dấu trừ chữ in của CongNoFormat.full');
  assert.equal(M.money('70.000'), '70.000', 'ô số tiền sai dạng của dòng lỗi hiện nguyên văn, không làm vỡ màn');
  assert.equal(M.stamp('2026-11-25T03:05:00+00:00'), '25/11 10:05');
  assert.equal(M.clean('  Sai file\n tải lại\tsau '), 'Sai file tải lại sau');
  assert.equal(M.refText({ customer_id: '12' }), 'sổ khách #12');
  assert.equal(M.refText({ transaction_id: '88' }), 'giao dịch #88');
});

test('đọc số tiền gõ tay: nhóm nghìn, dấu âm khi cho phép, không số lẻ', () => {
  assert.equal(M.readAmount('1.234.567'), '1234567');
  assert.equal(M.readAmount(' 1234567 '), '1234567');
  assert.equal(M.readAmount('2.000 đ'), '2000');
  assert.equal(M.readAmount('-25.000', { signed: true }), '-25000');
  assert.equal(M.readAmount('-0', { signed: true }), '0');
  for (const bad of ['-25.000', '12,5', '1.23', 'abc', '', '1234567890123456789']) assert.equal(M.readAmount(bad), null, bad);
});

test('phân bổ: còn lại, dòng thành thân lệnh (mã là chuỗi số như set_allocation đòi), đổi dòng cũ cần lý do', () => {
  assert.equal(M.remaining('100000', [{ amount: '30.000' }, { amount: 'chưa gõ' }]), '70000');
  assert.equal(M.remaining('100000', [{ amount: '60000' }, { amount: '50.000 đ' }]), '-10000');
  assert.deepEqual(M.allocationLines([{ kind: 'customer_unapplied', ref: '12', amount: '30.000', note: '  gia \n mot ' },
    { kind: 'bank_fee', ref: 'bo qua', amount: '5000', note: '' }, { kind: 'internal_transfer', ref: '88', amount: '1.000 đ' }]), { lines: [
    { target_kind: 'customer_unapplied', target_ref: { customer_id: '12' }, amount_minor: '30000', note: 'gia mot' },
    { target_kind: 'bank_fee', target_ref: {}, amount_minor: '5000' },
    { target_kind: 'internal_transfer', target_ref: { transaction_id: '88' }, amount_minor: '1000' }] });
  assert.equal(M.allocationLines([{ kind: 'expense_category', ref: ' ', amount: '5000' }]).error, 'Dòng 1: ghi mục chi.');
  assert.equal(M.allocationLines([{ kind: 'ar_book', ref: 'abc', amount: '5000' }]).error, 'Dòng 1: mã phải là số.');
  assert.equal(M.allocationLines([{ kind: 'bank_fee', amount: '0' }]).error, 'Dòng 1: số tiền phải là số nguyên lớn hơn 0.');
  assert.equal(M.allocationLines([{ kind: 'luong', amount: '5' }]).error, 'Dòng 1: chọn loại.');
  const old = [{ target_kind: 'bank_fee', target_ref: {}, amount_minor: '5000', note: null }];
  assert.equal(M.changesExisting(old, [{ target_kind: 'bank_fee', target_ref: {}, amount_minor: '5000' }]), false);
  assert.equal(M.changesExisting(old, [...old, { target_kind: 'other', target_ref: {}, amount_minor: '1' }]), false, 'chỉ thêm dòng không cần lý do');
  assert.equal(M.changesExisting(old, [{ target_kind: 'bank_fee', target_ref: {}, amount_minor: '6000' }]), true);
  assert.equal(M.changesExisting(old, []), true);
});

const LINE3 = { line_no: 3, class: 'suspect', booking_date: '2026-11-21', direction: 'in', amount_minor: '30000', candidate: 43, soft_candidates: [43] };
const VIEW = {
  import: { id: 10 }, preview_hash: 'f'.repeat(64), stale: false, counts: { rows: 3, error: 0 }, signed_days: [],
  lines: [{ line_no: 1, class: 'duplicate', candidate: 42 }, { line_no: 2, class: 'new' }, LINE3],
  breaks: [{ code: 'UNMATCHED_EXISTING', transaction_id: 44, booking_date: '2026-11-21', direction: 'in', amount_minor: '30000' },
    { code: 'UNMATCHED_EXISTING', transaction_id: 45, booking_date: '2026-11-22', direction: 'out', amount_minor: '15000' }],
};

test('câu cần quyết: ứng viên gồm ứng viên mềm và giao dịch file chưa nhận cùng ngày/chiều/tiền; mọi giao dịch của U phải trùng hoặc giữ', () => {
  const q = M.questions(VIEW);
  assert.deepEqual(q.suspects.map(s => [s.line.line_no, s.candidates]), [[3, [43, 44]]]);
  assert.deepEqual(q.pool, [44, 45, 43], 'U = giao dịch file không nhận + ứng viên mềm');
  assert.equal(M.commitRole(VIEW), 'tien_review');
  assert.equal(M.commitRole({ ...VIEW, lines: [{ line_no: 1, class: 'new' }], breaks: [] }), 'tien_nhap');
  assert.deepEqual(M.keepAsks(VIEW, { lines: {}, keep: {} }), [45], 'lựa chọn của dòng chưa quyết chưa hỏi lý do giữ');
  assert.deepEqual(M.keepAsks(VIEW, { lines: { 3: 43 }, keep: {} }), [44, 45]);
  assert.deepEqual(M.keepAsks(VIEW, { lines: { 3: 'new' }, keep: {} }), [44, 45, 43], 'chọn "mới" thì ứng viên mềm cũng phải giữ có lý do');
  assert.equal(M.commitBody(VIEW, { lines: {}, keep: {} }).error, 'Dòng 3: chọn giao dịch mới hay trùng.');
  assert.equal(M.commitBody(VIEW, { lines: { 3: 43 }, keep: {} }).error, 'Giao dịch đã có ngày 21/11/2026, 30.000 đ chưa được file nhận: ghi lý do giữ.');
  assert.deepEqual(M.commitBody(VIEW, { lines: { 3: 43 }, keep: { 44: ' giu\nlai ', 45: 'ngan hang chua tra' } }), { needsReview: true, body: {
    import_id: 10, expected_preview_hash: 'f'.repeat(64), suspect_decisions: [{ line_no: 3, decision: 'duplicate_of', transaction_id: 43 }],
    keep_existing: [{ transaction_id: 44, reason: 'giu lai' }, { transaction_id: 45, reason: 'ngan hang chua tra' }] } });
  assert.deepEqual(M.commitBody(VIEW, { lines: { 3: 'new' }, keep: { 43: 'a', 44: 'b', 45: 'c' } }).body.keep_existing.map(k => k.transaction_id), [44, 45, 43]);
  const twice = { ...VIEW, lines: [LINE3, { ...LINE3, line_no: 4 }] };
  assert.equal(M.commitBody(twice, { lines: { 3: 43, 4: 43 }, keep: {} }).error, 'Dòng 4: hai dòng không thể cùng trùng một giao dịch đã có.');
  assert.deepEqual(M.commitBody({ ...VIEW, lines: [], breaks: [] }, { lines: {}, keep: {} }),
    { needsReview: false, body: { import_id: 10, expected_preview_hash: 'f'.repeat(64) } });
});

test('chặn ghi lô: hết hạn, dòng lỗi, gãy số dư (câu rõ, tối đa 5); ngày đã ký chỉ là cảnh báo', () => {
  assert.deepEqual(M.blockers(VIEW), []);
  const view = { ...VIEW, stale: true, counts: { error: 2 }, signed_days: ['2026-11-21'], breaks: [
    { code: 'OPENING_MISMATCH', expected_minor: '1000000', actual_minor: '990000' },
    { code: 'RUNNING_BALANCE', line_no: 7, expected_minor: '5000', actual_minor: '6000' },
    { code: 'CLOSING_MISMATCH', expected_minor: '1000', actual_minor: '2000' },
    ...Array.from({ length: 4 }, (_, i) => ({ code: 'RUNNING_BALANCE', line_no: 10 + i, expected_minor: '1', actual_minor: '2' }))] };
  const blocked = M.blockers(view);
  assert.equal(blocked.length, 8);
  assert.match(blocked[0], /Bỏ lô này rồi nhập lại file/);
  assert.match(blocked[1], /2 dòng lỗi/);
  assert.equal(blocked[2], 'Số dư đầu của file 990.000 đ khác số dư sổ đầu kỳ 1.000.000 đ.');
  assert.equal(blocked[3], 'Dòng 7: số dư sau trong file 6.000 đ, tính theo các dòng trước là 5.000 đ.');
  assert.equal(blocked[4], 'Số dư cuối của file 2.000 đ khác số dư đầu cộng các dòng 1.000 đ.');
  assert.equal(blocked[7], 'Và 2 chỗ gãy số dư khác.');
  assert.ok(!blocked.some(b => b.includes('đã ký')), 'ngày đã ký không chặn: dòng chọn "trùng" không tạo giao dịch');
  assert.match(M.warnings(view)[0], /Ngày 21\/11\/2026 đã ký số dư[\s\S]*mở lại ngày 21\/11\/2026 ở Đối soát ngày/);
});

test('ngày mở đầu tiên: ngày cũ nhất đủ sao kê còn việc; hết việc thì ngày mới nhất', () => {
  const days = [
    { date: '2026-11-25', coverage: 'partial', coverage_status: 'unconfirmed', business_status: 'open' },
    { date: '2026-11-24', coverage: 'full', coverage_status: 'unconfirmed', business_status: 'open' },
    { date: '2026-11-23', coverage: 'full', coverage_status: 'signed', business_status: 'open' },
    { date: '2026-11-22', coverage: 'full', coverage_status: 'signed', business_status: 'signed' },
  ];
  assert.equal(M.nextDay(days), '2026-11-23');
  assert.equal(M.nextDay(days.map(d => ({ ...d, coverage_status: 'signed', business_status: 'signed' }))), '2026-11-25');
  assert.equal(M.nextDay([]), null);
  assert.deepEqual(days.map(M.dayCoverageText), ['Chưa trọn', 'Chưa ký', 'Đã ký', 'Đã ký']);
  assert.equal(M.dayCoverageText({ coverage: 'missing', coverage_status: 'unconfirmed' }), 'Thiếu sao kê');
  assert.equal(M.dayCoverageText({ coverage: 'full', coverage_status: 'reopened' }), 'Mở lại');
});

test('khoảng tháng tới hôm nay, chênh thành câu', () => {
  assert.deepEqual(M.monthRange('2026-02', '2026-11-25'), ['2026-02-01', '2026-02-28']);
  assert.deepEqual(M.monthRange('2028-02', '2028-12-01'), ['2028-02-01', '2028-02-29']);
  assert.deepEqual(M.monthRange('2026-11', '2026-11-25'), ['2026-11-01', '2026-11-25']);
  assert.equal(M.diffText('0'), 'Khớp');
  assert.equal(M.diffText('9000'), 'Sổ cao hơn ngân hàng 9.000 đ');
  assert.equal(M.diffText('-1000'), 'Sổ thấp hơn ngân hàng 1.000 đ');
  assert.equal(M.diffText(null), '—');
  assert.ok(M.REASON.NO_EVIDENCE && M.REASON.COVERAGE_NOT_SIGNED && M.TARGET.customer_unapplied.ref === 'customer_id');
  assert.equal(M.has(['tien_xem'], 'tien_review'), false);
});
