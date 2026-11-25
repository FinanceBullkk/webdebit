const { test } = require('node:test');
const assert = require('node:assert/strict');
const M = require('./bao-cao-thang-model.js');

// BAO-CAO-THANG-01: dữ liệu giả cùng dạng GET /api/v7/report/month.
const customer = (name, extra = {}) => ({ name, owner: null, book_id: 1, families: ['BIEN'], booking: 3, sheet: 3, web: 3, thieu: 0,
  khong_booking: 0, lech_ngay: 0, khong_ngay: 0, chep: 0, ngoai: 0, chi_web: 0, web_thieu: 0, issues: 0, ...extra });

test('chữ trạng thái theo nghiệp vụ, tháng đang chạy nói nhẹ hơn', () => {
  assert.deepEqual(M.statusOf({ status: 'khop', web: { date: '2026-10-03' } }), { text: 'Khớp', tone: 'ok' });
  assert.deepEqual(M.statusOf({ status: 'khop', web: null }), { text: 'Web chưa có', tone: 'warn' });
  const web = { date: '2026-10-29', source: 'web' };
  assert.deepEqual(M.statusOf({ status: 'thieu', web }), { text: 'Sheet chưa ghi', tone: 'bad' });
  assert.deepEqual(M.statusOf({ status: 'thieu', web }, true), { text: 'Chưa lên Sheet', tone: 'warn' });
  // BAO-CAO-THANG-02: web chưa có thì nói rõ, kể cả tháng đang chạy
  assert.deepEqual(M.statusOf({ status: 'thieu' }), { text: 'Sheet chưa ghi, web chưa có', tone: 'bad' });
  assert.deepEqual(M.statusOf({ status: 'thieu', web: null }, true), { text: 'Chưa lên Sheet, web chưa có', tone: 'bad' });
  assert.equal(M.statusOf({ status: 'lech_ngay', date: '2026-10-10', booking: { date: '2026-10-25' } }).text, 'Lệch ngày 15 ngày');
  assert.equal(M.statusOf({ status: 'chep' }).tone, 'muted');
  assert.equal(M.statusOf({ status: 'chi_web', web: { date: '2026-10-15' } }).text, 'Chỉ có trên web');
});

test('chip cần xem: chỉ loại có số, theo thứ tự đụng tiền', () => {
  const item = customer('A', { thieu: 2, web_thieu: 1, thieu_web: 1, chep: 11, issues: 3 });
  assert.deepEqual(M.chips(item).map(chip => chip.text), ['Sheet chưa ghi 2', 'Web chưa có 2', 'Chép 0đ 11'],
    'web chưa có gồm dòng Sheet và chuyến booking Sheet chưa ghi');
  assert.equal(M.chips(item, true)[0].text, 'Chưa lên Sheet 2');
  assert.deepEqual(M.chips(customer('B')), []);
});

test('lọc khách lệch và biển/bộ', () => {
  const list = [customer('A', { issues: 2 }), customer('B', { families: ['BO'] }), customer('C', { families: ['BIEN', 'BO'], issues: 1 })];
  assert.deepEqual(M.filter(list, { onlyIssues: true }).map(item => item.name), ['A', 'C']);
  assert.deepEqual(M.filter(list, { family: 'BO' }).map(item => item.name), ['B', 'C']);
  assert.deepEqual(M.filter(list).map(item => item.name), ['A', 'B', 'C']);
  assert.equal(M.familyText(['BIEN', 'BO']), 'Biển, Bộ');
  assert.equal(M.familyText([]), '—');
});

test('bảng tổng: null là chưa có số, không thành 0', () => {
  const rows = M.summaryRows({ BIEN: { booking: 262, sheet: 260, web: 255, thieu: 2, web_chua: 7, web_thieu: 5 },
    BO: { booking: 201, sheet: 201, web: 201, thieu: 0, web_chua: 0, web_thieu: 0 }, ALL: { booking: 463, sheet: 461, web: 456, thieu: 2, web_chua: 7, web_thieu: 5 } });
  assert.deepEqual(rows.map(row => row.values), [[262, 201, 463], [260, 201, 461], [255, 201, 456], [2, 0, 2], [7, 0, 7], [5, 0, 5]]);
  assert.deepEqual(rows.filter(row => row.list).map(row => row.label), ['Booking có, web chưa có'], 'chỉ hàng web chưa có mở được danh sách');
  assert.deepEqual(M.summaryRows({ ALL: { booking: null, web: 4 } })[0].values, [null, null, null]);
  assert.equal(M.summaryRows({}, true)[3].label, 'Booking có, chưa lên Sheet');
});

test('tháng chọn được từ tháng đầu tới tháng hiện tại, qua năm', () => {
  assert.deepEqual(M.months('2025-12', '2026-02'), ['2026-02', '2026-01', '2025-12']);
  assert.deepEqual(M.months(null, '2026-11'), ['2026-11']);
  assert.equal(M.shift('2026-01', -1), '2025-12');
  assert.equal(M.shift('2025-12', 1), '2026-01');
});

test('lý do máy chưa đưa chuyến booking vào web: câu nghiệp vụ và ai phải làm (BAO-CAO-THANG-02)', () => {
  assert.deepEqual(M.reasonOf('CONTAINER_REUSED_OR_CHANGED').whoText, 'Tự hết khi Sheet ghi');
  assert.match(M.reasonOf('NO_BOOK').text, /chưa gắn sổ web/);
  assert.equal(M.reasonOf('NO_BOOK').who, 'person');
  assert.equal(M.reasonOf('COMMODITY_MISMATCH').who, 'person');
  // WEB-CHINH-01: chuyến bộ không chờ Sheet nữa; người gán tên chủ hàng hoặc chọn sổ trên web.
  for (const code of ['ROAD_NO_TAB', 'ROAD_TAB_FAR', 'ROAD_AMBIGUOUS_TAB']) {
    assert.equal(M.reasonOf(code).who, 'person');
    assert.doesNotMatch(M.reasonOf(code).text, /sửa Sheet|chờ tab/);
  }
  assert.match(M.reasonOf('ROAD_NO_TAB').text, /thẻ Khách/);
  assert.match(M.reasonOf('ROAD_TAB_FAR').text, /chọn sổ ở Việc cần làm/);
  assert.equal(M.reasonOf('NEXT_RUN').whoText, 'Máy tự làm');
  assert.deepEqual(M.reasonOf('UNKNOWN'), { text: 'Chưa đọc được lý do', who: null, whoText: '—' }, 'mã lạ không đoán');
});
