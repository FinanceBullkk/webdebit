const assert = require('node:assert/strict');
const M = require('./may-chay-model.js');

// MAY-CHAY-01: lượt để vẽ suy đúng từ dữ liệu job; không có số nào do hình tự nghĩ ra.
const at = (h, m, s = 0) => `2026-11-06T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}+07:00`;
const trace = (over = {}) => ({
  state: 'done', mode: 'fix', started_at: at(9, 5), finished_at: at(9, 10), books: 10, counts: { KHOP: 10 }, fixed: 0, created: 0, unlinked: {}, customers: {},
  segments: [{ stage: 'tai', at: at(9, 5) }, { stage: 'sach', at: at(9, 5, 10) }, { stage: 'doc', at: at(9, 7) }, { stage: 'so', at: at(9, 9) }, { stage: 'luu', at: at(9, 9, 50) }], ...over,
});
const writing = () => trace({
  finished_at: at(9, 13), counts: { KHOP: 9 }, fixed: 1,
  segments: [{ stage: 'tai', at: at(9, 5) }, { stage: 'sach', at: at(9, 5, 10) }, { stage: 'doc', at: at(9, 7) }, { stage: 'so', at: at(9, 9) }, { stage: 'chot', at: at(9, 9, 10) }, { stage: 'tim', at: at(9, 9, 12) }, { stage: 'ghi', at: at(9, 12) }, { stage: 'tim', at: at(9, 12, 20) }, { stage: 'luu', at: at(9, 12, 50) }],
  customers: { 7: { customer_id: 7, reason: 'FIXED', decided_at: at(9, 11), done_at: at(9, 12, 15), before_vnd: '248300000', after_vnd: '260800000', target_vnd: '260800000' }, 9: { customer_id: 9, reason: 'NO_EXACT_FIX', decided_at: at(9, 12, 30), difference_vnd: '-8200000' } },
});

// Giây của lượt lấy từ mốc thật.
{
  const run = M.fromTrace(trace());
  assert.equal(run.sec, 300);
  assert.equal(run.stages.doc.from, 120);
  assert.equal(run.stages.tim.d, 0);
  assert.equal(M.stageNow(run, 130), 'doc');
  assert.equal(M.stageNow(run, 300), null);
}

// Trạm chạy nhiều đoạn (tìm, ghi, tìm tiếp) gom thành một khoảng; giữa chừng đúng trạm đang chạy.
{
  const run = M.fromTrace(writing());
  assert.equal(run.stages.tim.from, 252);
  assert.equal(M.stageNow(run, 430), 'ghi');
  assert.equal(M.stageNow(run, 445), 'tim');
  assert.equal(M.stationInfo(run, 480, 'tim', 'luu').text, '2/2 khách');
  assert.equal(M.stationInfo(run, 480, 'ghi', 'luu').text, '1/1 khách');
}

// Lượt không lệch: hai trạm sau hiện bỏ qua, không phải chưa tới.
{
  const run = M.fromTrace(trace());
  assert.equal(M.stationInfo(run, 200, 'tim', 'doc').state, '');
  assert.equal(M.stationInfo(run, 299, 'tim', 'luu').state, 'skip');
  assert.equal(M.stationInfo(run, 299, 'chot', 'luu').text, 'không cần');
  assert.equal(M.sentence(run, 300, null), 'Lượt xong lúc 09:10: 10/10 khớp, không ghi gì.');
}

// Chốt: qua, chặn, cả hai trong một lượt có dấu riêng; lỗi đọc lại là dấu ✕.
{
  const run = M.fromTrace(writing());
  const marks = M.gateMarks(run, 480);
  assert.deepEqual(marks.map(item => item.state), ['pass', 'held', 'pass']);
  assert.equal(marks[1].mark, '! ');
  assert.equal(M.gateMarks(run, 100)[0].state, '');
  const failed = M.drill('verify');
  assert.equal(M.gateMarks(failed, failed.sec)[2].mark, '✕ ');
  assert.equal(M.stationInfo(failed, failed.sec, 'ghi', null).state, 'stop');
  const many = M.drill('many');
  assert.equal(M.stationInfo(many, many.sec, 'chot', null).state, 'stop');
  assert.equal(M.stationInfo(many, many.sec, 'tim', null).text, 'không chạy');
  assert.ok(M.sentence(many, many.sec, null).includes('không ghi'));
}

// Lượt đang chạy: đếm theo job báo, không theo thời gian; chưa hết lượt thì không kết luận.
{
  const live = M.fromTrace(trace({ state: 'running', finished_at: null, books: null, counts: null, stage: 'doc', done: 4, total: 10, segments: [{ stage: 'tai', at: at(9, 5) }, { stage: 'doc', at: at(9, 7) }] }));
  live.sec = 130;
  live.stages.doc.to = 130;
  live.stages.doc.d = 10;
  assert.equal(M.stageNow(live, 130), 'doc');
  assert.equal(M.stationInfo(live, 130, 'doc', 'doc').text, '4/10');
  assert.ok(M.sentence(live, 130, 'doc').startsWith('Đang đọc'));
}

// Giữa lượt có khách lệch mà chưa xét xong: không được nói khớp hết, trạm sau chưa phải bỏ qua, mẫu số theo job báo.
{
  const live = M.fromTrace(trace({ state: 'running', finished_at: null, books: 10, counts: null, stage: 'tim', done: 0, total: 1, different: 1, too_many: false, customers: {},
    segments: [{ stage: 'tai', at: at(9, 5) }, { stage: 'doc', at: at(9, 7) }, { stage: 'so', at: at(9, 9) }, { stage: 'chot', at: at(9, 9) }, { stage: 'tim', at: at(9, 9) }] }));
  live.sec = 245;
  live.stages.tim.to = 260;
  live.stages.tim.d = 20;
  const text = M.logLines(live, 245).map(item => item.text).join(' ');
  assert.ok(text.includes('1 khách cần xét'), text);
  assert.ok(!text.includes('khớp hết'), text);
  assert.equal(M.stationInfo(live, 245, 'ghi', 'tim').state, '');
  assert.equal(M.stationInfo(live, 245, 'luu', 'tim').state, '');
  assert.equal(M.stationInfo(live, 245, 'tim', 'tim').text, '0/1 khách');
}

// Lượt lỗi nói rõ mã lỗi.
{
  const run = M.fromTrace(trace({ state: 'failed', reason: 'HTTP_503', counts: null }));
  assert.ok(M.sentence(run, run.sec, null).includes('HTTP_503'));
  assert.equal(M.slotKind(run), 'bad');
}

// Dòng log cũ: chỉ có số đếm, không có thẻ khách, ghi nhận là ước tính; giờ xong đúng log.
{
  const row = { finished_at: at(13, 12, 38), counts: { KHOP: 9 }, total: 10, fixed: 1, created: 0, detail: null };
  const run = M.fromRow(row);
  assert.equal(run.countsOnly, true);
  assert.equal(run.estimated, true);
  assert.equal(run.customers.length, 0);
  assert.equal(run.sec, 458);
  assert.equal(M.clockOf(run.start).slice(0, 5), '13:05');
  assert.equal(M.slotKind(run), 'wrote');
  assert.equal(M.slotKind({ ...run, fixed: 0 }), 'left');
  assert.equal(M.slotKind({ ...run, fixed: 0, khop: 10 }), 'quiet');
  assert.equal(M.fromRow({ finished_at: at(14, 45, 6), counts: { KHOP: 5 }, total: 5, fixed: 0, created: 2, detail: null }).onSchedule, false);
  assert.equal(M.fromRow({ finished_at: at(23, 9, 58), counts: {}, total: null, detail: null }).sec >= 30, true);
}

// Ngày mới nhất lên trên, tổng ngày đúng.
{
  const days = M.byDay([{ finished_at: '2026-11-05T09:09:00+07:00', counts: { KHOP: 2 }, total: 2, fixed: 1, created: 0, detail: null }, { finished_at: at(9, 9), counts: { KHOP: 2 }, total: 2, fixed: 0, created: 3, detail: null }]);
  assert.deepEqual(days.map(day => [day.label, day.fixed, day.created]), [['6/11', 0, 3], ['5/11', 1, 0]]);
}

// Tiền chính xác từ chuỗi, kể cả số rất lớn; NULL là gạch, không phải 0.
{
  assert.equal(M.money('260800000'), '260.800.000đ');
  assert.equal(M.money('-8200000'), '-8.200.000đ');
  assert.equal(M.money('123456789012345678901'), '123.456.789.012.345.678.901đ');
  assert.equal(M.money(null), '—');
  assert.equal(M.millions('248300000'), '248,3 tr');
  assert.equal(M.millions('260000000'), '260 tr');
  assert.equal(M.millions('-8250000'), '-8,3 tr');
  assert.equal(M.millions(null), '—');
}

// Lý do lạ không vỡ, vẫn là không ghi; lý do có ghi được đánh dấu đúng.
{
  assert.equal(M.resultOf('LY_DO_MOI').tag, 'Cần xem');
  assert.equal(M.resultOf('LY_DO_MOI').wrote, undefined);
  assert.equal(M.resultOf('FIXED').wrote, true);
  assert.equal(M.resultOf('NO_EXACT_FIX').wrote, undefined);
}

// Web đổi mã khách thành tên; mã không có trong danh sách giữ nguyên.
{
  const label = id => ({ 7: 'KHÁCH BẢY' })[id];
  assert.equal(M.withNames('kh-7 còn lệch, kh-8 chưa rõ, KH-7 lặp', label), 'KHÁCH BẢY còn lệch, kh-8 chưa rõ, KHÁCH BẢY lặp');
  assert.equal(M.taskCustomer('kh-7-lech'), '7');
  assert.equal(M.taskCustomer('sao-luu-tre'), null);
}
console.log('may-chay-model: OK');
