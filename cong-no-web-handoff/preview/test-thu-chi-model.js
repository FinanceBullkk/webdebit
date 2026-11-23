const assert = require('node:assert/strict');
const test = require('node:test');
const M = require('./thu-chi-model.js');

// ZALO-THU-CHI-01 PR-2: phép tính của trang Thu chi. Dữ liệu giả.
const item = (day, direction, amount, status, extra = {}) => ({ source: 'chat', message_id: `m-${day}-${direction}-${amount}-${status}`, conversation_id: 'c', sent_at: 1, day, direction,
  amount_vnd: amount, status, shared: false, ledger_vnd: null, ledger_ref: null, target: { kind: null, id: null, label: null }, ambiguous: false, media: [], text: '', ...extra });

test('Tổng thu, chi, ứng cộng BigInt; khoản không có số chỉ đếm riêng, không vào tổng', () => {
  const sum = M.summarize([item('2026-11-20', 'thu', 50_000_000, 'RECORDED'), item('2026-11-20', 'thu', 1_200_000, 'MISSING'), item('2026-11-20', 'chi', 2_500_000, 'WAITING'),
    item('2026-11-20', 'ung', 3_000_000, 'AMOUNT_DIFF'), item('2026-11-20', 'thu', null, 'NO_AMOUNT')]);
  assert.deepEqual([sum.thu, sum.chi, sum.ung], [{ n: 2, img: 0, vnd: '51200000' }, { n: 1, img: 0, vnd: '2500000' }, { n: 1, img: 0, vnd: '3000000' }]);
  assert.deepEqual([sum.missing, sum.diff, sum.noAmount], [1, 1, 1]);
});

test('Tổng lớn không mất đồng nào (vượt 2^53)', () => {
  const big = [item('2026-11-20', 'thu', 9_007_199_254_740_991, 'RECORDED'), item('2026-11-20', 'thu', 2, 'RECORDED')];
  assert.equal(M.summarize(big).thu.vnd, '9007199254740993');
});

test('Bộ lọc: số đếm khớp danh sách sau khi lọc', () => {
  const items = [item('d', 'thu', 1, 'MISSING'), item('d', 'thu', 2, 'MISSING'), item('d', 'thu', 3, 'AMOUNT_DIFF'), item('d', 'thu', 4, 'SUGGEST'), item('d', 'chi', 5, 'UNKNOWN_TARGET'),
    item('d', 'thu', null, 'NO_AMOUNT'), item('d', 'thu', 6, 'RECORDED')];
  const counts = M.counts(items);
  assert.deepEqual(counts, { all: 7, missing: 2, diff: 1, unknown: 2, noamount: 1, notcash: 0 });
  for (const filter of M.FILTERS) assert.equal(M.filterItems(items, filter.id).length, counts[filter.id]);
  assert.equal(M.filterItems(items, 'khong-co').length, 7);
});

test('Gom theo ngày: ngày mới trên cùng, mỗi ngày có tổng riêng', () => {
  const groups = M.groupByDay([item('2026-11-19', 'thu', 5, 'RECORDED'), item('2026-11-20', 'chi', 7, 'WAITING'), item('2026-11-19', 'thu', 6, 'RECORDED')]);
  assert.deepEqual(groups.map(group => [group.day, group.rows.length, group.sum.thu.vnd, group.sum.chi.vnd]), [['2026-11-20', 1, '0', '7'], ['2026-11-19', 2, '11', '0']]);
});

test('Khoảng ngày đếm lùi theo lịch, qua tháng và năm', () => {
  assert.deepEqual(M.range('2026-11-20', 7), { from: '2026-11-14', to: '2026-11-20' });
  assert.deepEqual(M.range('2026-01-03', 7), { from: '2025-12-28', to: '2026-01-03' });
  assert.deepEqual(M.range('2026-03-01', 30), { from: '2026-01-31', to: '2026-03-01' });
});

test('Nhận ra khoản mới theo mã tin, dấu của sổ không có mã thì theo giờ và số tiền', () => {
  const old = [item('d', 'thu', 1, 'WAITING'), item('d', 'thu', 2, 'WAITING', { source: 'mark', message_id: null, sent_at: 5 })];
  const next = [...old, item('d', 'chi', 3, 'WAITING')];
  assert.deepEqual(M.newKeys(old, next), [M.keyOf(next[2])]);
  assert.deepEqual(M.newKeys(old, old), []);
});

test('Câu trạng thái đúng bảng của spec; lệch số ghi cả hai số, NULL không hiện 0', () => {
  assert.equal(M.statusText(item('d', 'thu', 1, 'RECORDED')).text, 'Đã vào sổ');
  assert.equal(M.statusText(item('d', 'thu', 1, 'WAITING')).text, 'Chờ vào sổ');
  assert.equal(M.statusText(item('d', 'thu', 1, 'MISSING')).tone, 'warn');
  assert.equal(M.statusText(item('d', 'thu', 5_000_000, 'AMOUNT_DIFF', { ledger_vnd: 4_500_000 })).text, 'Lệch: báo 5.000.000 đ, sổ 4.500.000 đ');
  assert.match(M.statusText(item('d', 'thu', 1, 'AMOUNT_DIFF', { shared: true, ledger_vnd: 1 })).note, /hai khoản báo/);
  assert.match(M.statusText(item('d', 'thu', 1, 'SUGGEST', { ledger_ref: { name: 'SỔ A' } })).text, /^Có thể là phiếu của sổ SỔ A$/);
  assert.equal(M.statusText(item('d', 'chi', 1, 'UNKNOWN_TARGET')).text, 'Chưa rõ của ai');
  assert.equal(M.statusText(item('d', 'chi', 1, 'NO_LEDGER')).text, 'Web chưa có sổ chi này');
  assert.equal(M.statusText(item('d', 'thu', null, 'NO_AMOUNT')).text, 'Không đọc được số');
  assert.equal(M.money(null), '—');
  // Ảnh ghi ngày giao dịch quá cũ: máy chủ không kết luận, trang không báo đỏ mà nói rõ ngày trên ảnh để người mở ảnh xem.
  const old = M.statusText(item('d', 'thu', 1, 'WAITING', { source: 'anh', old_txn: true, image: { txn_time: '2026-02-11' } }));
  assert.deepEqual([old.tone, old.text], ['info', 'Ảnh ghi ngày cũ']);
  assert.match(old.note, /ngày 11\/02\/2026, trước ngày gửi hơn 3 tháng/);
  assert.equal(M.statusText(item('d', 'thu', 1, 'RECORDED', { source: 'anh', old_txn: true })).text, 'Đã vào sổ');
});

test('Khoản chưa đối chiếu được (nguồn sổ lỗi) không bị ghi là chưa vào sổ', () => {
  const text = M.statusText(item('d', 'thu', 5, 'WAITING', { unchecked: true }));
  assert.deepEqual([text.tone, text.text], ['info', 'Chưa đối chiếu được']);
  assert.match(M.statusText(item('d', 'thu', 5, 'UNKNOWN_TARGET', { unchecked: true })).note, /danh sách khách và xe/);
  assert.equal(M.statusText(item('d', 'thu', 5, 'WAITING')).text, 'Chờ vào sổ');
});

// PR-4b: ảnh chuyển khoản máy đọc (source 'anh'). Số bịa.
const photo = (amount, status, extra = {}) => item('2026-11-19', 'thu', amount, status, { source: 'anh', message_id: 'img', amount_from: amount == null ? null : 'anh',
  image_vnd: amount, media: [{ id: 'a'.repeat(64) }], image: { by: amount == null ? 'human' : 'ocr', bank: 'VCB', txn_time: null, candidates: [] }, ...extra });

test('Ảnh: tổng đếm riêng số khoản từ ảnh; ảnh chưa đọc chắc không vào tổng', () => {
  const sum = M.summarize([photo(7_000_000, 'RECORDED'), photo(null, 'NO_AMOUNT'), item('2026-11-19', 'thu', 5_000_000, 'WAITING')]);
  assert.deepEqual([sum.thu, sum.noAmount], [{ n: 2, img: 1, vnd: '12000000' }, 1]);
});

test('Ảnh: câu trạng thái nói rõ lý do, không đoán', () => {
  const unsure = M.statusText(photo(null, 'NO_AMOUNT', { image: { by: 'human', candidates: [1_050_000, 1_500_000] } }));
  assert.deepEqual([unsure.text, unsure.note], ['Ảnh chưa đọc chắc', 'Máy đọc ra 1.050.000 đ và 1.500.000 đ. Mở ảnh để xem, không cộng vào tổng.']);
  assert.match(M.statusText(photo(null, 'NO_AMOUNT')).note, /^Máy không đọc ra số\./);
  assert.equal(M.statusText(photo(7, 'UNKNOWN_TARGET', { link: 'none' })).note, 'Hội thoại chưa gắn sổ.');
  assert.equal(M.statusText(photo(7, 'UNKNOWN_TARGET', { link: 'many', ambiguous: true })).note, 'Hội thoại gắn nhiều sổ.');
  assert.equal(M.statusText(photo(7, 'UNKNOWN_TARGET', { link: 'failed', unchecked: true })).note, 'Không đọc được danh sách nhóm gắn sổ lúc này.');
  // Danh sách khách hay phiếu đọc lỗi (không phải danh sách nhóm): giữ lý do thật, thêm câu chưa kiểm được.
  assert.equal(M.statusText(photo(7, 'UNKNOWN_TARGET', { link: 'none', unchecked: true })).note, 'Hội thoại chưa gắn sổ. Chưa kiểm được phiếu đúng số lúc này.');
  assert.equal(M.statusText(photo(7, 'RECORDED')).text, 'Đã vào sổ');
});

test('Ảnh chứng khác số gõ: "Lệch: mẫu X, ảnh Y", câu đối chiếu vẫn giữ ở ghi chú; đếm vào Lệch số', () => {
  const diff = item('d', 'thu', 5_000_000, 'RECORDED', { image_vnd: 5_500_000, image_diff: true, ledger_vnd: 5_000_000 });
  assert.deepEqual([M.statusText(diff).tone, M.statusText(diff).text, M.statusText(diff).note], ['warn', 'Lệch: mẫu 5.000.000 đ, ảnh 5.500.000 đ', 'Đã vào sổ.']);
  const suggest = item('d', 'thu', 5_000_000, 'SUGGEST', { image_vnd: 5_500_000, image_diff: true, ledger_ref: { name: 'SỔ D' } });
  assert.equal(M.statusText(suggest).note, 'Có thể là phiếu của sổ SỔ D. Người xác nhận.');   // gợi ý vẫn là gợi ý, không thành "sổ ghi"
  const missing = item('d', 'thu', 5_000_000, 'MISSING', { image_vnd: 5_500_000, image_diff: true });
  assert.equal(M.statusText(missing).note, 'Chưa vào sổ. Quá 3 ngày vẫn chưa thấy trong sổ.');
  assert.deepEqual([M.counts([diff, missing]).diff, M.counts([diff, missing]).missing, M.summarize([diff, missing]).diff], [2, 1, 2]);
  assert.equal(M.imageDiff(item('d', 'thu', 5_000_000, 'RECORDED', { image_vnd: 5_000_000, image_diff: false })), false);
  assert.equal(M.statusText(item('d', 'thu', 5, 'AMOUNT_DIFF', { ledger_vnd: 4 })).text, 'Lệch: báo 5 đ, sổ 4 đ');   // lệch với sổ như cũ
  const mark = item('d', 'thu', 8_000_000, 'WAITING', { source: 'mark', image_vnd: 7_000_000 });
  assert.deepEqual([M.statusText(mark).text, M.statusText(mark).note], ['Chờ vào sổ', 'Ảnh đọc ra 7.000.000 đ.']);   // dấu giữ số người nhập
});

test('Ảnh: hai ảnh trong một tin là hai khoản khác nhau khi nhận khoản mới', () => {
  const one = photo(1, 'WAITING', { media: [{ id: '1'.repeat(64) }] });
  const two = photo(2, 'WAITING', { media: [{ id: '2'.repeat(64) }] });
  assert.notEqual(M.keyOf(one), M.keyOf(two));
  assert.deepEqual(M.newKeys([one], [one, two]), [M.keyOf(two)]);
});

// Luồng 3: xác nhận, sửa số, gắn đối tượng, loại. Số và tên bịa.
const loai = (extra = {}) => item('2026-11-19', 'thu', 5_000_000, 'NOT_CASH', { review: { decision: 'not_cash', reason: 'tin hỏi giá', reviews: 1, last_action: 'not_cash', last_by: 'lan' }, ...extra });

test('Khoản đã loại: chỉ ở bộ lọc Đã loại, không đếm, không cộng tổng', () => {
  const items = [item('d', 'thu', 1_000_000, 'MISSING'), loai()];
  const counts = M.counts(items);
  assert.deepEqual([counts.all, counts.missing, counts.notcash], [1, 1, 1]);
  assert.deepEqual(M.filterItems(items, 'all').map(one => one.status), ['MISSING']);
  assert.deepEqual(M.filterItems(items, 'notcash').map(one => one.status), ['NOT_CASH']);
  assert.deepEqual(M.summarize(items).thu, { n: 1, img: 0, vnd: '1000000' });
  assert.deepEqual([M.statusText(loai()).text, M.statusText(loai()).note], ['Đã loại: không phải thu chi', 'Lý do: tin hỏi giá']);
  assert.ok(M.STATUSES.includes('NOT_CASH'));
});

test('Xử lý được: không cho dấu khách báo và tin có hai ảnh chuyển khoản, nói lý do', () => {
  const chat = item('d', 'thu', 1, 'WAITING');
  assert.deepEqual(M.reviewable(chat, [chat]), { ok: true, why: '' });
  assert.equal(M.reviewable(item('d', 'thu', 1, 'WAITING', { source: 'mark' }), []).ok, false);
  const one = photo(1, 'WAITING', { media: [{ id: '1'.repeat(64) }] });
  const two = photo(2, 'WAITING', { media: [{ id: '2'.repeat(64) }] });
  assert.match(M.reviewable(one, [one, two]).why, /nhiều ảnh/);
});

test('Nút theo trạng thái: đã xác nhận thì không còn nút xác nhận; không có số thì chưa xác nhận được; đã loại thì đưa lại', () => {
  assert.deepEqual(M.actions(item('d', 'thu', 1, 'WAITING')), ['confirm', 'amount', 'target', 'not_cash']);
  assert.deepEqual(M.actions(item('d', 'thu', 1, 'WAITING', { review: { decision: 'confirm' } })), ['amount', 'target', 'not_cash']);
  assert.deepEqual(M.actions(item('d', 'thu', null, 'NO_AMOUNT')), ['amount', 'target', 'not_cash']);
  assert.deepEqual(M.actions(loai()), ['restore']);
  assert.deepEqual([M.targetKinds('thu'), M.targetKinds('chi'), M.targetKinds('ung')], [['so'], ['xe', 'tai_xe'], ['xe', 'tai_xe']]);
});

test('Ô số đúng: chỉ chữ số và dấu ngăn nghìn; không đoán "tr", "k", số lẻ, số 0 hay số quá lớn', () => {
  assert.equal(M.parseAmount('4.500.000'), '4500000');
  assert.equal(M.parseAmount(' 4 500 000 '), '4500000');
  assert.equal(M.parseAmount('4,500,000'), '4500000');
  assert.equal(M.parseAmount('1000000000000'), '1000000000000');
  for (const bad of ['', '0', '000', '4,5tr', '500k', '-500000', '1000000000001', 'abc', '4.5e6', null]) assert.equal(M.parseAmount(bad), null, String(bad));
  // Audit 23/11: số lẻ hay nhóm sai không được bỏ dấu rồi đọc thành số khác 10–100 lần ("1,5" → 15, "45.000.000,50" → 4,5 tỷ).
  for (const bad of ['1,5', '45,5', '45.000.000,50', '1.234.56', '4.500,000', '4 500.000', '45,000,000.50', '1..500', '12.34']) assert.equal(M.parseAmount(bad), null, bad);
});

test('Tìm đối tượng bỏ dấu, biển số không cần gạch và chấm, giữ chữ Hán', () => {
  const rows = [{ id: 1, label: 'KHÁCH ĐÔNG' }, { id: 2, label: '51C-123.45' }, { id: 3, label: '陈氏贸易 SỔ' }, { id: 4, label: 'Bình' }];
  assert.deepEqual(M.searchTargets(rows, 'dong').map(row => row.id), [1]);
  assert.deepEqual(M.searchTargets(rows, '51c12345').map(row => row.id), [2]);
  assert.deepEqual(M.searchTargets(rows, '123.45').map(row => row.id), [2]);
  assert.deepEqual(M.searchTargets(rows, '陈氏').map(row => row.id), [3]);
  assert.deepEqual(M.searchTargets(rows, 'binh').map(row => row.id), [4]);
  assert.equal(M.searchTargets(rows, '').length, 4);
  assert.equal(M.searchTargets(rows, '', 2).length, 2);
});

test('Câu lần xử lý gần nhất', () => {
  assert.equal(M.reviewSummary(item('d', 'thu', 1, 'WAITING')), null);
  assert.deepEqual(M.reviewSummary(item('d', 'thu', 1, 'WAITING', { review: { decision: 'confirm', reviews: 2, last_action: 'confirm', last_by: 'lan', last_at: 'x' } })),
    { what: 'Đã xác nhận', by: 'lan', at: 'x', times: 2 });
  assert.equal(M.reviewSummary(item('d', 'thu', 1, 'WAITING', { review: { decision: null, reviews: 1, last_action: 'amount' } })).what, 'Đã sửa số');
  assert.equal(M.reviewSummary(item('d', 'thu', 1, 'WAITING', { review: { decision: null, reviews: 1, last_action: 'target' } })).what, 'Đã gắn đối tượng');
  assert.equal(M.reviewSummary(loai()).what, 'Đã loại');
});

test('Luồng 4: cùng giao dịch gửi lại thì ghi chú "gửi lại thêm N lần … chỉ tính một lần", giữ câu đối chiếu và cảnh báo lệch', () => {
  const twice = item('d', 'thu', 7_000_000, 'RECORDED', { resent: 2 });
  assert.deepEqual([M.statusText(twice).text, M.statusText(twice).note], ['Đã vào sổ', 'Ảnh chuyển khoản gửi lại thêm 2 lần (cùng giao dịch): chỉ tính một lần.']);
  const missing = item('d', 'thu', 7_000_000, 'MISSING', { resent: 1 });
  assert.equal(M.statusText(missing).note, 'Quá 3 ngày vẫn chưa thấy trong sổ. Ảnh chuyển khoản gửi lại thêm 1 lần (cùng giao dịch): chỉ tính một lần.');
  const diff = item('d', 'thu', 5_000_000, 'RECORDED', { image_vnd: 5_500_000, image_diff: true, resent: 1 });
  assert.equal(M.statusText(diff).text, 'Lệch: mẫu 5.000.000 đ, ảnh 5.500.000 đ');
  assert.match(M.statusText(diff).note, /^Đã vào sổ\. Ảnh chuyển khoản gửi lại thêm 1 lần/);
  for (const none of [0, undefined, null, '2']) assert.equal(M.statusText(item('d', 'thu', 1, 'RECORDED', { resent: none })).note, '', String(none));
  assert.deepEqual(M.summarize([twice]).thu, { n: 1, img: 0, vnd: '7000000' });   // tổng không đổi: một khoản
});
