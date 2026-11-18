const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// CHI-PHI-XE-01: màn Đội xe trên máy chủ giả cùng dạng /api/v7/doixe/* (dữ liệu bịa: tên, biển số, container).
// Máy chủ giả giữ luật chính của hàm SQL (khóa tháng → dòng điều chỉnh, mã yêu cầu, ngày tương lai) đủ để kiểm luồng màn;
// luật tiền thật được kiểm ở harness PostgreSQL (tools/test_pg_doixe.py).
const HOM_NAY = '2026-11-18';
const PHI = [['nang', 'Phí nâng', 12], ['nangha', 'Nâng hạ', 13], ['cau', 'Cầu đường', 14], ['neo', 'Neo', 15], ['xi', 'Xí cont', 16],
  ['dao', 'Đảo cont', 17], ['moi', 'Cont mới', 18], ['doi', 'Dời cont', 19], ['seal', 'Mua seal', 20], ['bai', 'Bãi chờ', 21],
  ['dieu', 'Điều độ', 22], ['dau', 'Đổ dầu', 23], ['ps', 'Phát sinh', 24], ['may', 'Nổ máy', 27], ['vetc', 'VETC', 26]]
  .map(([ma, ten, cot], i) => ({ ma, ten, ten_day_du: null, thu_tu: i + 1, cot_sheet: cot, cong_ty_tra: ma === 'vetc' }));

function world() {
  const w = {
    nguoi: [{ id: 1, ten: 'Tài xế Gia A', vai: 'tai_xe', so_du_dau: 0 }, { id: 2, ten: 'Tài xế Gia B', vai: 'tai_xe', so_du_dau: 1000000 },
      { id: 3, ten: 'Đi lệnh Gia', vai: 'di_lenh', so_du_dau: -3000000 }],
    xe: [{ id: 1, bien_so: '99Z-900.01', nhom: 'NHOM GIA', thue_ngoai: false, tai_xe_id: 1, dang_dung: true },
      { id: 2, bien_so: '99Z-900.02', nhom: 'NHOM GIA', thue_ngoai: false, tai_xe_id: 2, dang_dung: true },
      { id: 3, bien_so: '99Y-800.01', nhom: 'THUE GIA', thue_ngoai: true, tai_xe_id: null, dang_dung: true }],
    chang: [], ung: [], dot: [], events: [], khoa: { '2026-10-01': true }, keys: new Map(), seq: 100, calls: [], posts: [],
    delay: 0, failNext: 0, down: false,
  };
  const add = (ngay, cont, phi, o = {}) => {
    const id = ++w.seq;
    w.chang.push({ id, ngay, container: cont, loai: 'hang', xe_id: 1, tai_xe_id: 1, tra: 'nguoi', nguoi_tra_id: 1, noi_lay: 'KHO GIA', noi_ha: 'CANG GIA',
      kho: null, tinh: null, ten_hang: null, ghi_chu: null, sau_khoa: false, da_bo: false, da_xoa: false, actor: 'nv', luc: '01/11 08:00',
      chuyen: cont.endsWith('1') ? { khach: 'KHACH GIA', ngay, tu: 'KHO GIA', den: 'CANG GIA' } : null,
      dong: [{ id: ++w.seq, loai: 'goc', dot_hoan_id: null, dot_ngay: null, dc_phi: null, dc_truoc_vnd: null, dc_sau_vnd: null, actor: 'nv', luc: '01/11 08:00', phi }], ...o });
  };
  add('2026-10-08', 'MAUU1000001', { nang: '450000', nangha: '350000' });
  add('2026-11-05', 'MAUU1000011', { nangha: '300000', vetc: '120000', ps: '50000' });
  add('2026-11-06', 'MAUU1000002', {});
  add('2026-11-07', 'MAUU1000031', { nang: '500000' }, { xe_id: 2, tai_xe_id: 2, nguoi_tra_id: 3 });
  w.ung.push({ id: 1, nguoi_id: 1, ngay: '2026-11-01', so_tien_vnd: '500000', ghi_chu: 'ứng đầu tháng', actor: 'nv', luc: '01/11 08:10', huy: null });
  return w;
}

const thangOf = iso => `${iso.slice(0, 7)}-01`;
const tienDong = d => Object.entries(d.phi).filter(([k]) => k !== 'vetc').reduce((s, [, v]) => s + Number(v), 0);
function soDu(w, id, truoc = null) {
  let s = w.nguoi.find(n => n.id === id).so_du_dau;
  for (const c of w.chang) if (!c.da_xoa && c.nguoi_tra_id === id && (!truoc || c.ngay < truoc)) for (const d of c.dong) s += tienDong(d);
  for (const h of w.dot) if (h.nguoi_id === id && !h.huy && (!truoc || h.ngay < truoc)) s -= Number(h.so_tien_vnd);
  for (const u of w.ung) if (u.nguoi_id === id && !u.huy && (!truoc || u.ngay < truoc)) s -= Number(u.so_tien_vnd);
  return s;
}
const khoa = (w, t) => w.khoa[t] ?? (t !== thangOf(HOM_NAY));
function chung(w) {
  const t = [...new Set([...w.chang.filter(c => !c.da_xoa).map(c => thangOf(c.ngay)), ...w.ung.map(u => thangOf(u.ngay)), thangOf(HOM_NAY)])].sort();
  return { hom_nay: HOM_NAY, loai_phi: PHI, thang_co: t, khoa: Object.fromEntries(t.map(m => [m, khoa(w, m)])),
    danh_muc: { nguoi: w.nguoi.map(n => ({ id: n.id, ten: n.ten, vai: n.vai, dang_dung: true })), xe: w.xe } };
}
function getTong(w, thang) {
  const m = thang ?? thangOf(HOM_NAY);
  return { ...chung(w), thang: m,
    nguoi: w.nguoi.map(n => ({ id: n.id, ten: n.ten, vai: n.vai, xe_id: w.xe.find(x => x.tai_xe_id === n.id)?.id ?? null, so_du_vnd: String(soDu(w, n.id)),
      chua_hoan: w.chang.filter(c => !c.da_xoa && c.nguoi_tra_id === n.id).flatMap(c => c.dong).filter(d => !d.dot_hoan_id && tienDong(d) !== 0).length })),
    xe: w.xe.map(x => { const ds = w.chang.filter(c => !c.da_xoa && !c.da_bo && c.xe_id === x.id && thangOf(c.ngay) === m);
      return { ...x, chang: ds.length, chua_phi: ds.filter(c => c.dong.every(d => !Object.keys(d.phi).length)).length }; }) };
}
function getSo(w, loai, id, thang) {
  const m = thang ?? thangOf(HOM_NAY);
  const view = c => { const { da_xoa: _x, ...rest } = c; return rest; };
  if (loai === 'xe') return { ...chung(w), thang: m, loai, xe: w.xe.find(x => x.id === id), chang: w.chang.filter(c => !c.da_xoa && c.xe_id === id && thangOf(c.ngay) === m).map(view) };
  const n = w.nguoi.find(x => x.id === id);
  const inM = d => thangOf(d) === m;
  let chi = 0;
  for (const c of w.chang) if (!c.da_xoa && c.nguoi_tra_id === id && inM(c.ngay)) for (const d of c.dong) chi += tienDong(d);
  const hoan = w.dot.filter(h => h.nguoi_id === id && !h.huy && inM(h.ngay)).reduce((s, h) => s + Number(h.so_tien_vnd), 0);
  const ung = w.ung.filter(u => u.nguoi_id === id && !u.huy && inM(u.ngay)).reduce((s, u) => s + Number(u.so_tien_vnd), 0);
  const dau = soDu(w, id, m);
  return { ...chung(w), thang: m, loai, nguoi: { id: n.id, ten: n.ten, vai: n.vai, xe_id: w.xe.find(x => x.tai_xe_id === id)?.id ?? null },
    so_du_vnd: String(soDu(w, id)), the: { dau_vnd: String(dau), chi_vnd: String(chi), hoan_vnd: String(hoan), ung_vnd: String(ung), cuoi_vnd: String(dau + chi - hoan - ung) },
    ung: w.ung.filter(u => u.nguoi_id === id && inM(u.ngay)), dot: w.dot.filter(h => h.nguoi_id === id && inM(h.ngay)),
    chang: w.chang.filter(c => !c.da_xoa && inM(c.ngay) && (c.tai_xe_id === id || c.nguoi_tra_id === id)).map(view),
    chua_hoan: w.chang.filter(c => !c.da_xoa && c.nguoi_tra_id === id && c.dong.some(d => !d.dot_hoan_id && tienDong(d) !== 0)).map(view) };
}
const loi = (status, error, message) => Object.assign(Error(message), { status, error });
function write(w, route, b) {
  const ev = (viec, o) => w.events.unshift({ id: w.events.length + 1, viec, actor: 'nv@gia', actor_name: 'nv', luc: '18/11 09:15', truoc: {}, sau: {}, ly_do: null, ...o });
  if (route === '/api/v7/doixe/chang') {
    const errs = [];
    b.rows.forEach((r, i) => {
      if (r.ngay > HOM_NAY) errs.push({ i, cot: 'ngay', ma: 'NGAY_TUONG_LAI' });
      if (w.chang.some(c => !c.da_xoa && c.ngay === r.ngay && c.container === r.container && c.loai === r.loai && c.xe_id === r.xe_id)) errs.push({ i, cot: 'container', ma: 'TRUNG_CHANG' });
    });
    if (errs.length) return { ok: false, loi: errs };
    for (const r of b.rows) {
      const id = ++w.seq;
      w.chang.push({ id, ...r, sau_khoa: khoa(w, thangOf(r.ngay)), da_bo: false, da_xoa: false, actor: 'nv@gia', luc: '18/11 09:15', chuyen: null,
        dong: [{ id: ++w.seq, loai: 'goc', dot_hoan_id: null, dot_ngay: null, dc_phi: null, dc_truoc_vnd: null, dc_sau_vnd: null, actor: 'nv@gia', luc: '18/11 09:15', phi: r.phi }] });
    }
    ev('them_chang', { nguoi_id: b.rows[0].nguoi_tra_id, sau: { so_dong: b.rows.length, tu: b.rows[0].ngay, den: b.rows[0].ngay, tien_vnd: '0' } });
    return { ok: true, so_dong: b.rows.length, chang_ids: [], sau_khoa: 0 };
  }
  if (route === '/api/v7/doixe/chang/sua') {
    const c = w.chang.find(x => x.id === b.chang_id);
    if (b.cot.startsWith('phi:')) {
      const ma = b.cot.slice(4);
      const hien = c.dong.reduce((s, d) => (d.phi[ma] === undefined ? s : (s ?? 0) + Number(d.phi[ma])), null);
      if ((hien === null ? null : String(hien)) !== b.truoc) throw loi(409, 'CHANGED', 'Ô này vừa đổi ở máy khác. Tải lại rồi sửa.');
      if (khoa(w, thangOf(c.ngay)) || c.dong[0].dot_hoan_id) {
        const chenh = Number(b.gia_tri ?? 0) - (hien ?? 0);
        c.dong.push({ id: ++w.seq, loai: 'dieu_chinh', dot_hoan_id: null, dot_ngay: null, dc_phi: ma, dc_truoc_vnd: b.truoc, dc_sau_vnd: b.gia_tri, actor: 'nv@gia', luc: '18/11 09:16', phi: { [ma]: String(chenh) } });
        return { ok: true, cach: 'dieu_chinh', ly_do_dc: khoa(w, thangOf(c.ngay)) ? 'thang_khoa' : 'da_hoan', chenh_vnd: String(chenh) };
      }
      if (b.gia_tri === null) delete c.dong[0].phi[ma]; else c.dong[0].phi[ma] = b.gia_tri;
      return { ok: true, cach: 'ghi_de' };
    }
    if (b.cot === 'ngay' && b.gia_tri > HOM_NAY) throw loi(422, 'NGAY_TUONG_LAI', 'Ngày không được sau hôm nay.');
    const col = b.cot === 'nguoi_tra' ? 'nguoi_tra_id' : b.cot;
    c[col] = b.cot === 'nguoi_tra' ? (b.gia_tri === 'cong_ty' ? null : Number(b.gia_tri)) : b.cot === 'xe_id' ? Number(b.gia_tri) : b.gia_tri;
    if (b.cot === 'nguoi_tra') c.tra = c.nguoi_tra_id ? 'nguoi' : 'cong_ty';
    return { ok: true, cach: 'ghi_de' };
  }
  if (route === '/api/v7/doixe/chang/xoa') {
    const c = w.chang.find(x => x.id === b.chang_id);
    if (khoa(w, thangOf(c.ngay))) { c.da_bo = true; return { ok: true, cach: 'bo' }; }
    c.da_xoa = true;
    return { ok: true, cach: 'xoa' };
  }
  if (route === '/api/v7/doixe/ung') {
    if (b.ngay > HOM_NAY) throw loi(422, 'NGAY_TUONG_LAI', 'Ngày không được sau hôm nay.');
    const truoc = soDu(w, b.nguoi_id);
    w.ung.push({ id: ++w.seq, nguoi_id: b.nguoi_id, ngay: b.ngay, so_tien_vnd: b.so_tien_vnd, ghi_chu: b.ghi_chu ?? null, actor: 'nv@gia', actor_name: 'nv', luc: '18/11 09:15', huy: null });
    ev('ghi_ung', { nguoi_id: b.nguoi_id, truoc: { so_du_vnd: String(truoc) }, sau: { ngay: b.ngay, so_tien_vnd: b.so_tien_vnd, so_du_vnd: String(soDu(w, b.nguoi_id)) } });
    return { ok: true, so_du_sau_vnd: String(soDu(w, b.nguoi_id)) };
  }
  if (route === '/api/v7/doixe/ung/huy') {
    const u = w.ung.find(x => x.id === b.ung_id);
    u.huy = { actor: 'nv@gia', actor_name: 'nv', luc: '18/11 09:20', ly_do: b.ly_do };
    ev('huy_ung', { nguoi_id: u.nguoi_id, ly_do: b.ly_do, truoc: { ngay: u.ngay, so_tien_vnd: u.so_tien_vnd, so_du_vnd: '0' }, sau: { so_du_vnd: String(soDu(w, u.nguoi_id)) } });
    return { ok: true, so_du_sau_vnd: String(soDu(w, u.nguoi_id)) };
  }
  if (route === '/api/v7/doixe/hoan') {
    const dongs = w.chang.flatMap(c => c.dong).filter(d => b.dong_ids.includes(d.id));
    const id = ++w.seq;
    const tong = dongs.reduce((s, d) => s + tienDong(d), 0);
    for (const d of dongs) { d.dot_hoan_id = id; d.dot_ngay = b.ngay; }
    w.dot.push({ id, nguoi_id: b.nguoi_id, ngay: b.ngay, so_tien_vnd: b.so_tien_vnd, tong_dong_vnd: String(tong), so_dong: dongs.length, actor: 'nv@gia', luc: '18/11 09:30', huy: null });
    return { ok: true, so_du_sau_vnd: String(soDu(w, b.nguoi_id)) };
  }
  if (route === '/api/v7/doixe/thang/khoa') {
    w.khoa[b.thang] = b.khoa;
    ev('khoa_thang', { truoc: { thang: b.thang, khoa: !b.khoa }, sau: { thang: b.thang, khoa: b.khoa } });
    return { ok: true, khoa: b.khoa };
  }
  throw loi(404, 'NOT_FOUND', 'x');
}

function makeServer(w) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body) => { response.writeHead(status, { 'Content-Type': type }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    w.calls.push(`${request.method} ${route}${url.search}`);
    if (route.startsWith('/api/v7/doixe')) {
      if (request.method === 'GET') {
        if (w.down) return out({ error: 'DB_UNAVAILABLE', message: 'x' }, 503);
        if (w.forbidden) return out({ error: 'LOGIN_NOT_ALLOWED', message: 'Tài khoản này chưa được cấp quyền dùng sổ. Báo quản trị thêm vào danh sách.' }, 403);
        const q = url.searchParams;
        if (route === '/api/v7/doixe') return out(getTong(w, q.get('thang')));
        if (route === '/api/v7/doixe/so') return out(getSo(w, q.get('loai'), Number(q.get('id')), q.get('thang')));
        if (route === '/api/v7/doixe/lich-su') return out({ events: w.events });
      }
      let raw = '';
      request.on('data', chunk => { raw += chunk; });
      request.on('end', () => setTimeout(() => {
        const b = JSON.parse(raw);
        w.posts.push({ route, body: b });
        if (w.failNext > 0) { w.failNext -= 1; request.socket.destroy(); return; }
        const sig = b.idempotency_key;
        try {
          if (w.keys.has(sig)) return out({ ...w.keys.get(sig), lap_lai: true });
          const result = write(w, route, b);
          if (result.ok !== false) w.keys.set(sig, result);
          return out(result);
        } catch (e) { return out({ error: e.error, message: e.message }, e.status ?? 500); }
      }, w.delay));
      return undefined;
    }
    if (route === '/api/v7/customers') return out({ customers: [] });
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 503);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(fn, { viewport = { width: 1280, height: 720 }, query = '', setup } = {}) {
  const w = world();
  setup?.(w);
  const server = makeServer(w);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await (await browser.newContext({ viewport })).newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = `http://127.0.0.1:${server.address().port}`;
    await page.goto(`${base}/doi-xe.html${query}`);
    await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
    await fn(page, w, base);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
// Ảnh để soát giao diện bằng mắt (dữ liệu giả): chạy với SHOTS_DIR=<thư mục ngoài repo>.
async function shot(page, name) {
  if (!process.env.SHOTS_DIR) return;
  fs.mkdirSync(process.env.SHOTS_DIR, { recursive: true });
  await page.screenshot({ path: path.join(process.env.SHOTS_DIR, `doi-xe-${name}.png`) });
}
const posts = (w, route) => w.posts.filter(p => p.route === route);

test('Đội xe: hai bảng, người công ty nợ nhiều lên đầu, hai cột thay số âm, tìm theo tên hoặc số biển, mở sổ', () => withPage(async (page, w) => {
  await shot(page, '1-tong');
  const rows = page.locator('.dx-g-nguoi.dx-row');
  assert.equal(await rows.count(), 3);
  assert.match(await rows.nth(0).innerText(), /Tài xế Gia B[\s\S]*99Z-900\.02[\s\S]*1\.000\.000/);
  assert.match(await rows.nth(1).innerText(), /Tài xế Gia A[\s\S]*99Z-900\.01[\s\S]*2 dòng[\s\S]*650\.000/);
  assert.match(await rows.nth(2).innerText(), /Đi lệnh Gia[\s\S]*Đi lệnh[\s\S]*2\.500\.000/, 'người giữ tiền ứng ở cột riêng, không số âm');
  assert.match(await page.locator('.dx-card').nth(1).innerText(), /Xe công ty\s+2 xe[\s\S]*99Z-900\.01\s+Tài xế Gia A\s+2\s+1 chặng[\s\S]*Xe thuê ngoài/);
  assert.equal(await page.locator('.dx-card').nth(1).locator('div.dx-row').count(), 1, 'xe thuê không mở sổ ở đợt 1');
  await page.locator('#dx-q').fill('90002');
  assert.equal(await page.locator('.dx-g-nguoi.dx-row').count(), 1);
  await page.locator('#dx-q').press('Enter');
  await page.locator('.dx-the').waitFor();
  assert.match(page.url(), /nguoi=2/);
  assert.match(await page.locator('#dx-head').innerText(), /Tài xế Gia B/);
  // Đổi người bằng ô gõ tìm ở tên.
  await page.locator('#dx-doi').click();
  await page.locator('#dx-doi-q').fill('di lenh');
  await page.locator('#dx-doi-q').press('Enter');
  await page.locator('#dx-head', { hasText: 'Người đi lệnh' }).waitFor();
  assert.ok(w.calls.some(call => call.startsWith('GET /api/v7/doixe/so?loai=nguoi&id=3')), 'đổi sang sổ người đi lệnh');
}));

test('Sổ tài xế: thẻ tiền như sổ, dòng người khác trả hiện xám không cộng, VETC xám, lọc nhanh, Đủ cột', () => withPage(async page => {
  await shot(page, '2-so-nguoi');
  const the = await page.locator('.dx-the-so').innerText();
  assert.match(the, /Số dư đầu tháng\s+800\.000\s+\+ Tài xế chi\s+350\.000\s+− Công ty đã hoàn\s+0\s+− Công ty đã ứng\s+500\.000\s+Công ty còn nợ Tài xế Gia A\s+650\.000/);
  assert.match(await page.locator('.dx-the-ds').first().innerText(), /01\/11\s+ứng đầu tháng\s+500\.000/);
  const rows = page.locator('.dx-r:not(.moi)');
  assert.equal(await rows.count(), 2);
  assert.match(await rows.nth(0).locator('.dx-c').last().innerText(), /^$/);
  assert.match(await page.locator('.dx-r').nth(0).innerText(), /Chưa hoàn/);
  assert.match(await page.locator('.dx-r').nth(1).innerText(), /Chưa có phí/);
  assert.match(await page.locator('.dx-tong').innerText(), /Tổng · 2 chặng[\s\S]*350\.000/);
  await page.locator('[data-loc="chuaphi"]').click();
  assert.equal(await page.locator('.dx-r:not(.moi)').count(), 1);
  await page.locator('[data-loc="chuaphi"]').click();
  await page.locator('[data-cach="du"]').first().click();
  assert.ok(await page.locator('.dx-hd span', { hasText: 'Nổ máy' }).count() === 1 && await page.locator('.dx-hd span', { hasText: 'Người trả' }).count() === 1);
}, { query: '?nguoi=1' }));

test('Nhập: Enter thành dòng nháp, con trỏ về ô Ngày; dán khối Sheet có ô đỏ; Lưu chỉ gửi dòng hết lỗi, dòng lỗi ở lại', () => withPage(async (page, w) => {
  await page.locator('[data-f="moi:0:ngay"]').fill('17/11');
  await page.locator('[data-f="moi:0:container"]').fill('mauu 2000001');
  await page.locator('[data-f="moi:0:phi:nangha"]').fill('300.000');
  await page.locator('[data-f="moi:0:phi:nangha"]').press('Enter');
  assert.equal(await page.locator('.dx-r.nhap').count(), 1);
  assert.equal(await page.evaluate(() => document.activeElement.dataset.f), 'moi:0:ngay');
  const cell = (c, n) => [...Array(29)].map((_, i) => c[i] ?? '').join('\t') + (n ?? '');
  const block = [cell({ 2: '11/16/2026', 3: 'MAUU2000002', 13: '300,000' }), cell({ 2: '11/16/2026', 3: 'MAUU2000003', 24: '157500.5', 25: 'vá vỏ 70%' }),
    cell({ 13: '300,000' }), cell({ 2: '11/19/2026', 3: 'MAUU2000004', 13: '100' })].join('\n');
  await page.locator('[data-f="moi:0:container"]').focus();
  await page.evaluate(text => {
    const data = new DataTransfer(); data.setData('text', text);
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  }, block);
  assert.equal(await page.locator('.dx-r.nhap').count(), 5);
  await shot(page, '3-dan');
  assert.equal(await page.locator('.dx-r.nhap.coloi').count(), 3);
  assert.equal(await page.locator('.dx-r.nhap.coloi .dx-in.loi').first().getAttribute('title'), 'Số lẻ');
  await page.locator('[data-cach="du"]').first().click();
  assert.equal(await page.locator('[data-f$=":phi:ps"].loi').inputValue(), '157500.5', 'ô lỗi giữ nguyên chữ đã dán');
  assert.match(await page.locator('.dx-nhap-bar').innerText(), /5 dòng nháp chưa lưu · 3 dòng lỗi[\s\S]*Lưu 2 dòng/);
  await page.locator('[data-act="luu"]').click();
  await page.locator('.dx-toast', { hasText: 'Đã lưu 2 dòng' }).waitFor();
  const sent = posts(w, '/api/v7/doixe/chang')[0].body.rows;
  assert.deepEqual(sent.map(r => [r.ngay, r.container, r.phi, r.tra, r.nguoi_tra_id, r.xe_id]),
    [['2026-11-17', 'MAUU2000001', { nangha: '300000' }, 'nguoi', 1, 1], ['2026-11-16', 'MAUU2000002', { nangha: '300000' }, 'nguoi', 1, 1]]);
  assert.equal(await page.locator('.dx-r.nhap').count(), 3, 'dòng lỗi ở lại để sửa');
  await page.locator('[data-f$=":phi:ps"].loi').fill('157500');
  await page.locator('[data-f$=":phi:ps"]').first().press('Tab');
  await page.waitForFunction(() => document.querySelectorAll('.dx-r.nhap.coloi').length === 2);
}, { query: '?nguoi=1' }));

test('Ghi ứng: đọc chữ, trước → sau, bấm hai lần chỉ một lệnh; mất mạng rồi bấm lại dùng lại mã cũ; ngày mai bị chặn', () => withPage(async (page, w) => {
  await page.locator('[data-act="mo-ung"]').click();
  await page.locator('#dx-ung-tien').fill('3000000');
  assert.match(await page.locator('#dx-ung-doc').innerText(), /= 3 triệu/);
  await shot(page, '4-ghi-ung');
  assert.match(await page.locator('.dx-dlg .dx-du').innerText(), /Công ty còn nợ 650\.000 → Tài xế Gia A đang giữ 2\.350\.000/);
  await page.locator('#dx-ung-ngay').fill('2026-11-19');
  await page.locator('.dx-dlg .dx-loi').waitFor();
  assert.equal(await page.locator('[data-act="ghi-ung"]').isDisabled(), true);
  assert.match(await page.locator('.dx-dlg .dx-loi').innerText(), /sau hôm nay/);
  await page.locator('#dx-ung-ngay').fill('2026-11-18');
  // Lệnh tới máy chủ và được ghi, nhưng trả lời mất trên đường về: trang không biết đã lưu chưa.
  await page.route('**/api/v7/doixe/ung', async route => { await route.fetch(); await route.abort('failed'); }, { times: 1 });
  await page.locator('[data-act="ghi-ung"]').click();
  await page.locator('.dx-toast.err', { hasText: 'Mất kết nối' }).waitFor();
  w.delay = 400;
  await page.locator('[data-act="ghi-ung"]').dblclick();
  await page.locator('.dx-toast', { hasText: 'Đã ghi ứng 3.000.000' }).waitFor();
  const sent = posts(w, '/api/v7/doixe/ung');
  assert.equal(sent.length, 2, 'một lần mất trả lời + một lần gửi lại; bấm đúp không gửi thêm');
  assert.equal(sent[0].body.idempotency_key, sent[1].body.idempotency_key, 'gửi lại dùng lại mã yêu cầu');
  assert.equal(w.ung.length, 2, 'máy chủ chỉ ghi một lần ứng mới');
  assert.match(await page.locator('.dx-cuoi').innerText(), /đang giữ tiền ứng\s+2\.350\.000/);
}, { query: '?nguoi=1' }));

test('Hoàn theo đợt: chỉ còn dòng chưa hoàn, tích sẵn, trừ tiền ứng đang giữ, ghi đợt; hủy ứng bắt buộc lý do', () => withPage(async (page, w) => {
  await page.locator('[data-act="mo-hoan"]').click();
  assert.equal(await page.locator('.dx-chk:checked').count(), 2, 'hai dòng chưa hoàn của mọi tháng');
  assert.match(await page.locator('.dx-hoan').innerText(), /Đã chọn 2\/2 dòng · tổng 1\.150\.000/);
  assert.equal(await page.locator('#dx-hoan-tien').inputValue(), '1.150.000');
  await page.locator('[data-act="tru-ung"]').click();
  assert.equal(await page.locator('#dx-hoan-tien').inputValue(), '650.000');
  await shot(page, '5-hoan');
  assert.match(await page.locator('.dx-hoan').innerText(), /Chuyển ít hơn tổng các dòng 500\.000: phần thiếu trừ vào tiền ứng đang giữ/);
  await page.locator('[data-act="ghi-hoan"]').click();
  await page.locator('.dx-toast', { hasText: 'Đã ghi đợt hoàn 650.000' }).waitFor();
  const body = posts(w, '/api/v7/doixe/hoan')[0].body;
  assert.deepEqual([body.so_tien_vnd, body.dong_ids.length, body.ngay], ['650000', 2, '2026-11-18']);
  assert.match(await page.locator('.dx-r').first().innerText(), /✓ Đã hoàn 18\/11/);
  assert.equal(await page.locator('[data-act="mo-hoan"]').isDisabled(), true);
  await page.locator('[data-act="xem-huy"][data-loai="ung"]').click();
  assert.equal(await page.locator('[data-act="huy"]').isDisabled(), true, 'chưa có lý do thì không hủy được');
  await page.locator('#dx-huy-lydo').fill('ghi trùng');
  await page.locator('[data-act="huy"]').click();
  await page.locator('.dx-item.huy').waitFor();
  assert.match(await page.locator('.dx-item.huy').innerText(), /Đã hủy · ghi trùng/);
}, { query: '?nguoi=1' }));

test('Tháng khóa: báo rõ, sửa tiền thành dòng điều chỉnh gửi kèm giá trị trước; xóa thành bỏ chặng; Lịch sử', () => withPage(async (page, w) => {
  assert.match(await page.locator('.dx-khoa').innerText(), /Tháng 10 đã khóa/);
  const neo = page.locator('[data-f$=":phi:nang"]').first();
  await neo.fill('400.000');
  await neo.press('Enter');
  await page.locator('.dx-toast', { hasText: 'thêm dòng điều chỉnh −50.000' }).waitFor();
  assert.deepEqual(posts(w, '/api/v7/doixe/chang/sua')[0].body, { idempotency_key: posts(w, '/api/v7/doixe/chang/sua')[0].body.idempotency_key, chang_id: 101, cot: 'phi:nang', truoc: '450000', gia_tri: '400000' });
  assert.equal(await page.locator('.dx-r.phu').count(), 1);
  await shot(page, '6-thang-khoa');
  assert.match(await page.locator('.dx-r.phu').innerText(), /Đ\.chỉnh · nv[\s\S]*−50\.000/);
  await page.locator('[data-act="xoa-hoi"]').first().click();
  await page.locator('[data-act="xoa"]').click();
  await page.locator('.dx-r.bo').waitFor();
  await page.locator('[data-act="doi-khoa"]').first().click();
  await page.locator('.dx-toast', { hasText: 'Đã mở khóa tháng 10' }).waitFor();
  await page.locator('[data-act="lich-su"]').click();
  await page.locator('.dx-ev').first().waitFor();
  assert.match(await page.locator('.dx-ls').innerText(), /Mở khóa tháng 10\/2026[\s\S]*Đã khóa → Đang mở/);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.dx-ls').count(), 0);
}, { query: '?nguoi=1&thang=2026-10' }));

test('Tải lỗi có Thử lại; thiếu quyền báo câu của máy chủ; 1265×560 không cuộn ngang, menu chín mục lọt khung', async () => {
  await withPage(async (page, w) => {
    assert.match(await page.locator('.dx-err').innerText(), /Không tải được Đội xe/);
    w.down = false;
    await page.locator('[data-act="thu-lai"]').click();
    await page.locator('.dx-card').first().waitFor();
  }, { setup: w => { w.down = true; } });
  await withPage(async page => {
    assert.match(await page.locator('.dx-err').innerText(), /chưa được cấp quyền/);
  }, { setup: w => { w.forbidden = true; } });
  await withPage(async page => {
    const size = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
    assert.ok(size.scroll <= size.client, `cuộn ngang: ${JSON.stringify(size)}`);
    const links = page.locator('.app-nav nav a');
    assert.equal(await links.count(), 9);
    const last = await links.last().boundingBox();
    assert.ok(last.y + last.height <= 560, `mục cuối menu ra ngoài khung: ${last.y + last.height}`);
    assert.equal(await page.locator('.app-nav nav a.active').innerText(), 'Đội xe');
    for (const sel of ['[data-act="mo-ung"]', '[data-act="mo-hoan"]', '[data-act="lich-su"]', '[data-act="doi-khoa"]']) {
      assert.ok((await page.locator(sel).first().boundingBox()).height >= 40, sel);
    }
  }, { viewport: { width: 1265, height: 560 }, query: '?nguoi=1' });
});
