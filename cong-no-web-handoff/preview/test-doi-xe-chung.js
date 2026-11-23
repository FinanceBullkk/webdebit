// Đội xe: phần dùng chung của hai màn (doi-xe-chung.js): địa chỉ giữa các mục, mã yêu cầu chống ghi trùng, khung ghi, thông báo.
// Không cần trình duyệt: fetch, đồng hồ và phần tử thông báo là đồ giả. Dữ liệu bịa.
const assert = require('node:assert/strict');
const test = require('node:test');
const C = require('./doi-xe-chung.js');

test('địa chỉ ba mục: mang tháng hợp lệ, bỏ tháng sai khuôn hoặc trống, Bảng giá giữ man=gia', () => {
  assert.equal(C.duongDanMuc('nguoi', '2026-10-01'), '/doi-xe.html?thang=2026-10');
  assert.equal(C.duongDanMuc('bangke', '2026-10-01'), '/doi-xe-bang-ke.html?thang=2026-10');
  assert.equal(C.duongDanMuc('gia', '2026-10-01'), '/doi-xe-bang-ke.html?man=gia&thang=2026-10');
  for (const thang of [null, undefined, '', '2026-10', '2026-13-01', '2026-00-01', '10/2026', 202610, '2026-10-01x']) {
    assert.equal(C.duongDanMuc('nguoi', thang), '/doi-xe.html', `tháng ${String(thang)} không mang`);
    assert.equal(C.duongDanMuc('gia', thang), '/doi-xe-bang-ke.html?man=gia');
  }
  assert.throws(() => C.duongDanMuc('lai-lo', '2026-10-01'), RangeError);
  assert.equal(C.thangUrl('2026-12-01'), '2026-12');
});

test('địa chỉ ba mục: biết hom_nay thì không mang tháng sau sang Người và xe (máy chủ không nhận), Bảng kê và Bảng giá vẫn mang', () => {
  const nay = '2026-11-18';
  assert.equal(C.duongDanMuc('nguoi', '2026-11-01', nay), '/doi-xe.html?thang=2026-11', 'tháng của hôm nay vẫn nhận');
  assert.equal(C.duongDanMuc('nguoi', '2026-10-01', nay), '/doi-xe.html?thang=2026-10');
  assert.equal(C.duongDanMuc('nguoi', '2026-12-01', nay), '/doi-xe.html', 'tháng sau thì bỏ');
  assert.equal(C.duongDanMuc('bangke', '2026-12-01', nay), '/doi-xe-bang-ke.html?thang=2026-12');
  assert.equal(C.duongDanMuc('gia', '2026-12-01', nay), '/doi-xe-bang-ke.html?man=gia&thang=2026-12');
  assert.equal(C.duongDanMuc('nguoi', '2026-12-01'), '/doi-xe.html?thang=2026-12', 'chưa biết hom_nay thì mang (trang đích tự bỏ khi bị từ chối)');
});

// Đồ giả cho `tao`: máy chủ trả lời theo kịch bản, ghi lại các lần gọi.
function dung(kichBan, opts = {}) {
  const calls = [], timers = [];
  const goc = { fetch: globalThis.fetch, setTimeout: globalThis.setTimeout };
  globalThis.fetch = async (url, init) => {
    calls.push({ url, body: init?.body ? JSON.parse(init.body) : null });
    const r = await kichBan(calls.length, url);
    return { ok: r.status < 400, status: r.status, json: async () => (r.body === undefined ? Promise.reject(Error('x')) : r.body) };
  };
  globalThis.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
  const S = { busy: false, toast: null, giuBao: null };
  const log = [];
  const toastBox = { hidden: true, className: '', innerHTML: '' };
  const api = C.tao({ S, draw: () => log.push('draw'), load: async () => { log.push('load'); if (opts.load) await opts.load(); }, toastBox,
    esc: t => String(t).replace(/</g, '&lt;'), tienTo: 'tx', matMang: 'MẤT MẠNG', chuaRo: 'CHƯA RÕ', toastMs: 7000, taiLai: ['CHANGED'] });
  return { api, S, log, calls, timers, toastBox, tra: () => Object.assign(globalThis, goc) };
}

test('post: cùng nội dung dùng lại mã khi 503 hoặc mất mạng, bỏ mã khi máy chủ đã trả lời được, mất mạng báo đúng câu của màn', async () => {
  const t = dung(n => {
    if (n === 1) throw Error('net');
    if (n === 2) return { status: 503, body: { error: 'DB_UNAVAILABLE', message: 'tạm dừng' } };
    if (n === 3) return { status: 422, body: { error: 'BAD', message: 'sai' } };
    return { status: 200, body: { ok: true } };
  });
  try {
    await assert.rejects(t.api.post('/p', { a: 1 }), e => e.code === 'NETWORK' && e.message === 'MẤT MẠNG');
    await assert.rejects(t.api.post('/p', { a: 1 }), e => e.status === 503 && e.code === 'DB_UNAVAILABLE');
    await assert.rejects(t.api.post('/p', { a: 1 }), e => e.status === 422 && e.message === 'sai');
    assert.deepEqual(await t.api.post('/p', { a: 1 }), { ok: true });
    const key = i => t.calls[i].body.idempotency_key;
    assert.equal(key(0), key(1));
    assert.equal(key(1), key(2));
    assert.notEqual(key(2), key(3), 'sau lỗi 422 máy chủ đã trả lời nên bỏ mã');
    await t.api.post('/p', { a: 1 });
    assert.notEqual(key(3), key(4), 'sau thành công bỏ mã');
    await t.api.post('/p', { a: 2 });
    assert.notEqual(key(4), key(5), 'nội dung khác thì mã khác');
    assert.equal(t.calls[0].body.a, 1);
  } finally { t.tra(); }
});

test('post: máy chủ trả 2xx mà thân không đọc được là chưa rõ kết quả: giữ mã, báo "chưa rõ", bấm lại dùng lại mã cũ (không ghi lần hai)', async () => {
  const t = dung(n => (n === 1 ? { status: 200 } : { status: 200, body: { ok: true, lap_lai: true } }));
  try {
    await assert.rejects(t.api.post('/p', { a: 1 }), e => e.code === 'BAD_RESPONSE' && e.status === 200 && e.message === 'CHƯA RÕ');
    assert.deepEqual(await t.api.post('/p', { a: 1 }), { ok: true, lap_lai: true });
    assert.equal(t.calls[0].body.idempotency_key, t.calls[1].body.idempotency_key, 'lần bấm lại dùng lại mã');
    await t.api.post('/p', { a: 1 });
    assert.notEqual(t.calls[1].body.idempotency_key, t.calls[2].body.idempotency_key, 'trả lời đọc được thì bỏ mã như cũ');
  } finally { t.tra(); }
});

test('ghi: thân 2xx không đọc được thì báo lỗi "chưa rõ", không chạy callback ghi, không đọc lại', async () => {
  const t = dung(() => ({ status: 200 }));
  try {
    let goi = false;
    assert.equal(await t.api.ghi('/p', { a: 1 }, () => { goi = true; }), null);
    assert.equal(goi, false, 'callback ghi đọc out.lap_lai nên không được chạy khi out hỏng');
    assert.equal(t.S.toast.text, 'CHƯA RÕ');
    assert.equal(t.S.toast.loai, 'err');
    assert.equal(t.S.busy, false);
  } finally { t.tra(); }
});

test('getJson: lỗi mang mã và trạng thái của máy chủ, thân không phải JSON thì câu tiếng Việt, không mã HTTP trần', async () => {
  const t = dung(n => (n === 1 ? { status: 403, body: { error: 'LOGIN_NOT_ALLOWED', message: 'chưa cấp quyền' } } : { status: 500 }));
  try {
    await assert.rejects(t.api.getJson('/g'), e => e.status === 403 && e.code === 'LOGIN_NOT_ALLOWED' && e.message === 'chưa cấp quyền');
    await assert.rejects(t.api.getJson('/g'), e => e.status === 500 && e.message === 'Máy chủ đang bận hoặc vừa khởi động lại. Chờ ít phút rồi bấm lại.');
  } finally { t.tra(); }
});

test('ghi: bấm lặp bị bỏ; câu báo kết quả chỉ hiện sau khi đọc lại xong; lỗi có mã trong taiLai thì đọc lại, mã khác thì không', async () => {
  let thaLoad;
  const t = dung(n => (n === 1 ? { status: 200, body: { ok: 1 } }
    : n === 2 ? { status: 409, body: { error: 'CHANGED', message: 'đã đổi' } } : { status: 409, body: { error: 'KHAC', message: 'khác' } }),
  { load: () => new Promise(r => { thaLoad = r; }) });
  // Chờ `load` được gọi, có hạn: hỏng thì đỏ ở đây thay vì treo tới khi job hết giờ.
  const choTai = async () => {
    const han = Date.now() + 2000;
    while (!thaLoad) {
      if (Date.now() > han) throw Error('load không được gọi trong 2 giây');
      await new Promise(r => setImmediate(r));
    }
    const tha = thaLoad;
    thaLoad = null;
    return tha;
  };
  try {
    const dau = t.api.ghi('/p', { a: 1 }, () => t.api.bao('Đã ghi.'));
    assert.equal(await t.api.ghi('/p', { a: 2 }), null, 'đang ghi thì lệnh thứ hai bị bỏ');
    assert.equal(t.calls.length, 1);
    const tha = await choTai();
    assert.equal(t.S.toast, null, 'chưa đọc lại xong thì chưa hiện câu báo');
    tha();
    assert.deepEqual(await dau, { ok: 1 });
    assert.equal(t.S.toast.text, 'Đã ghi.');
    assert.equal(t.S.busy, false);
    assert.equal(t.S.giuBao, null);
    assert.equal(t.timers.at(-1).ms, 7000, 'câu báo tự tắt theo thời gian của màn');
    t.timers.at(-1).fn();
    assert.equal(t.S.toast, null);

    t.log.length = 0;
    const loi = t.api.ghi('/p', { a: 3 });
    (await choTai())();
    assert.equal(await loi, null);
    assert.equal(t.S.toast.loai, 'err');
    assert.ok(t.log.includes('load'), 'CHANGED thì đọc lại số liệu');

    t.log.length = 0;
    assert.equal(await t.api.ghi('/p', { a: 4 }), null);
    assert.ok(!t.log.includes('load'), 'mã lỗi khác không đọc lại');
    assert.equal(t.S.busy, false);
  } finally { t.tra(); }
});

test('drawToast: ẩn khi không có câu báo, thoát HTML khi có', () => {
  const t = dung(() => ({ status: 200, body: {} }));
  try {
    t.api.drawToast();
    assert.equal(t.toastBox.hidden, true);
    t.S.toast = { text: '<b>x</b>', loai: 'warn', n: 1 };
    t.api.drawToast();
    assert.equal(t.toastBox.hidden, false);
    assert.equal(t.toastBox.className, 'dx-toast warn');
    assert.match(t.toastBox.innerHTML, /^<span>&lt;b>x&lt;\/b><\/span><button[^>]*data-act="dong-toast"/);
  } finally { t.tra(); }
});

test('ghi: callback ok trả Promise thì được chờ xong trước khi đọc lại; ok ném lỗi thì báo lỗi, không đọc lại, mở khóa', async () => {
  const t = dung(() => ({ status: 200, body: { ok: 1 } }));
  try {
    t.api.ghi('/p', { a: 1 }, async () => { await new Promise(r => setImmediate(r)); t.log.push('ok xong'); });
    // load của đồ giả ghi 'load' vào cùng t.log: so thứ tự sau khi ghi xong.
    const han = Date.now() + 2000;
    while (t.S.busy || !t.log.includes('load')) {
      if (Date.now() > han) throw Error('ghi không xong trong 2 giây');
      await new Promise(r => setImmediate(r));
    }
    assert.ok(t.log.indexOf('ok xong') > -1 && t.log.indexOf('ok xong') < t.log.indexOf('load'), 'callback trả Promise được chờ xong rồi mới đọc lại');
    t.log.length = 0;
    assert.equal(await t.api.ghi('/p', { a: 2 }, () => { throw Error('callback hỏng'); }), null);
    assert.equal(t.S.toast.text, 'callback hỏng');
    assert.equal(t.S.toast.loai, 'err');
    assert.ok(!t.log.includes('load'));
    assert.equal(t.S.busy, false);
    assert.equal(t.S.giuBao, null);
  } finally { t.tra(); }
});

test('post: không có crypto.randomUUID thì mã dự phòng có tiền tố của màn', async () => {
  const goc = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  const t = dung(() => ({ status: 200, body: {} }));
  try {
    Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true, writable: true });
    await t.api.post('/p', { a: 1 });
    assert.match(t.calls[0].body.idempotency_key, /^tx-\d+-[0-9a-f]+$/);
  } finally {
    if (goc) Object.defineProperty(globalThis, 'crypto', goc); else delete globalThis.crypto;
    t.tra();
  }
});

test('xep (audit DX-02): lệnh sửa ô gõ liền tay khi lệnh trước chưa xong thì chờ tới lượt, không bị bỏ; chạy đúng thứ tự, sau lần tải lại', async () => {
  let thaLoad = null, soLoad = 0;
  const t = dung(() => ({ status: 200, body: { ok: 1 } }), { load: () => { soLoad += 1; return new Promise(r => { thaLoad = r; }); } });
  const cho = async () => {
    const han = Date.now() + 2000;
    while (!thaLoad) {
      if (Date.now() > han) throw Error('load không được gọi trong 2 giây');
      await new Promise(r => setImmediate(r));
    }
    const tha = thaLoad;
    thaLoad = null;
    tha();
  };
  try {
    const thay = [];
    const a = t.api.xep(() => { thay.push(`a@${soLoad}`); return t.api.ghi('/sua', { o: 'a' }); });
    const b = t.api.xep(() => { thay.push(`b@${soLoad}`); return t.api.ghi('/sua', { o: 'b' }); });
    await new Promise(r => setImmediate(r));
    assert.equal(t.S.busy, true);
    assert.equal(await t.api.ghi('/khac', {}), null, 'ghi thường vẫn bỏ khi đang bận');
    await cho();
    assert.deepEqual(await a, { ok: 1 });
    await cho();
    assert.deepEqual(await b, { ok: 1 });
    assert.deepEqual(thay, ['a@0', 'b@1'], 'b chạy sau khi a đã tải lại sổ');
    assert.deepEqual(t.calls.map(c => c.body.o), ['a', 'b']);
    // Việc trong hàng ném lỗi không chặn việc sau.
    await assert.rejects(t.api.xep(() => { throw Error('hỏng'); }), /hỏng/);
    assert.equal(await t.api.xep(() => 'xong'), 'xong');
    assert.equal(t.S.busy, false);
  } finally { t.tra(); }
});

test('getJson và post: mất mạng báo câu của màn, máy chủ lỗi không có câu thì câu tiếng Việt, không hiện mã HTTP trần (audit 23/11 F3)', async () => {
  const t = dung(n => {
    if (n === 1) throw new TypeError('Failed to fetch');
    if (n === 2) return { status: 502 };
    if (n === 3) return { status: 403 };
    return { status: 404 };
  });
  try {
    await assert.rejects(t.api.getJson('/g'), e => e.code === 'NETWORK' && e.message === 'MẤT MẠNG');
    await assert.rejects(t.api.getJson('/g'), e => e.status === 502 && e.message === 'Máy chủ đang bận hoặc vừa khởi động lại. Chờ ít phút rồi bấm lại.');
    await assert.rejects(t.api.getJson('/g'), e => e.message === 'Tài khoản này chưa được cấp quyền.');
    await assert.rejects(t.api.post('/p', { a: 1 }), e => e.status === 404 && !/Lỗi \d/.test(e.message));
  } finally { t.tra(); }
});
