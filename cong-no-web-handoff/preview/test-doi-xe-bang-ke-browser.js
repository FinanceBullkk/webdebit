const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// DOI-XE-THU-01: màn Bảng kê gửi HTH + Bảng giá trên máy chủ giả cùng dạng /api/v7/doixe/* (dữ liệu bịa: container, tuyến,
// số tiền). Máy chủ giả giữ các luật chính của hàm SQL đủ để kiểm luồng màn (đã gửi thì chỉ điều chỉnh, đối chiếu xong mới
// ghi tiền về, trả thừa chặn, mã yêu cầu); luật tiền thật kiểm ở harness PostgreSQL (tools/test_pg_doixe_thu.py).
const HOM_NAY = '2026-11-18';
const item = (goc, ten, tien, o = {}) => ({ goc, ten, ma: 'x', so_tien_vnd: tien, chi_ho: false, cot: 'ps', ...o });
const nhap = (id, ngay, cont, o = {}) => ({ chang_id: id, ngay, container: cont, loai: 'hang', tinh: 'TỈNH A', kho: 'KHO GIẢ', tai_xe: 'Tài xế giả', so_xe: '99Z-900.01',
  noi_lay: 'CẢNG A', noi_ha: 'CẢNG B', ten_hang: 'HÀNG GIẢ', ghi_chu: null, tuyen_id: 1, tuyen: 'Hàng giả · Tỉnh A → Cảng A', tuyen_gan: false,
  khoa_tuyen: 'HANG GIA|TINH A', gia_bang_vnd: '1000000', cuoc_vnd: '1000000', cuoc_tay: false, ghep_vnd: null, ps_vnd: null, chi_ho_vnd: null, ps: [],
  chua_doc: 0, khoan_la: 0, chang_con: true, ...o });

function world() {
  const w = { calls: [], posts: [], keys: new Map(), seq: 1000, delay: 0, failNext: 0, down: false, events: [],
    ben: { ma: 'hth', ten: 'HTH', kinh_gui: 'HTH', tieu_de: 'DEBIT GIẢ' } };
  w.nhap = {
    '2026-11-01': [
      nhap(201, '2026-11-02', 'MAUU2000001', { ps: [item('Kiểm hoá 150k', 'Kiểm hoá', '150000', { chi_ho: true })], ps_vnd: '150000', chi_ho_vnd: '150000',
        ghi_chu: '_ Kiểm hoá 150k' }),
      nhap(202, '2026-11-03', 'MAUU2000002', { tuyen_id: null, tuyen: null, ten_hang: 'HÀNG GIẢ B', tinh: 'TỈNH B', khoa_tuyen: 'HANG GIA B|TINH B',
        gia_bang_vnd: null, cuoc_vnd: null }),
      nhap(203, '2026-11-04', 'MAUU2000003', { loai: 'rut_mooc', gia_bang_vnd: '700000', cuoc_vnd: '700000' }),
      nhap(204, '2026-11-05', 'MAUU2000004', { cuoc_tay: true, cuoc_vnd: '1200000', ps: [{ goc: 'Cân', loi: 'Thiếu số tiền (ví dụ 200k)' }], chua_doc: 1,
        ghi_chu: '_ Cân' }),
      nhap(205, '2026-11-06', 'MAUU2000005', { loai: 'chuyen_cang', tuyen_id: 2, tuyen: 'Chuyển cảng · Các cảng', gia_bang_vnd: '300000', cuoc_vnd: '300000',
        ghep_vnd: '500000', ps: [item('Đóng ghép 500k', 'Đóng ghép', '500000', { cot: 'ghep' })] }),
    ],
  };
  const sent = (id, stt, ngay, cont, o = {}) => ({ ...nhap(id - 200, ngay, cont, o), id, stt, dc_vnd: null, dieu_chinh: [] });
  w.bk = {
    '2026-09-01': { id: 9, so: 'HTH-2026-09', trang_thai: 'da_doi_chieu', gui_ngay: '2026-10-02', doi_chieu_luc: '10/10 10:12',
      dong: [sent(390, 1, '2026-09-05', 'MAUU0900001')], tien_ve: [{ id: 91, ngay: '2026-10-14', so_tien_vnd: '1000000', actor: 'nv@gia', actor_name: 'nv', luc: '14/10 15:05', huy: null }] },
    '2026-10-01': { id: 10, so: 'HTH-2026-10', trang_thai: 'da_gui', gui_ngay: '2026-11-03', doi_chieu_luc: null, tien_ve: [],
      dong: [sent(301, 1, '2026-10-03', 'MAUU1000001', { ps: [item('Hạ sớm 380k', 'Hạ sớm', '380000', { chi_ho: true })], ps_vnd: '380000', chi_ho_vnd: '380000' }),
        sent(302, 2, '2026-10-10', 'MAUU1000002'), sent(303, 3, '2026-10-20', 'MAUU1000003', { loai: 'chuyen_cang', tuyen: 'Chuyển cảng · Các cảng', cuoc_vnd: '300000', gia_bang_vnd: '300000' })] },
  };
  w.gia = { hom_nay: HOM_NAY, ben: { ma: 'hth', ten: 'HTH' },
    tuyen: [{ id: 1, loai: 'hang', hang: 'Hàng giả', di: 'Tỉnh A', den: 'Cảng A', ten: 'Hàng giả · Tỉnh A → Cảng A', dang_dung: true,
      gia: [{ tu_ngay: '2026-01-01', gia_vnd: '1000000' }], ten_goc: ['HANG GIA|TINH A'], cho_doi: ['2026-11-02', '2026-11-04'] },
    { id: 2, loai: 'chuyen_cang', hang: null, di: 'Các cảng', den: null, ten: 'Chuyển cảng · Các cảng', dang_dung: true,
      gia: [{ tu_ngay: '2026-01-01', gia_vnd: '300000' }], ten_goc: [], cho_doi: ['2026-11-06'] }],
    phat_sinh: [{ ma: 'kiem_hoa', ten: 'Kiểm hoá', cach: 'co_dinh', muc_vnd: null, muc_them_vnd: null, chi_ho: true, cot: 'ps', ten_goc: ['HA KIEM HOA', 'KIEM HOA'] },
      { ma: 'neo', ten: 'Neo', cach: 'theo_ngay', muc_vnd: null, muc_them_vnd: null, chi_ho: false, cot: 'ps', ten_goc: ['NEO'] }] };
  return w;
}

const n = v => (v === null || v === undefined ? 0 : Number(v));
function tong(dong, tienVe) {
  const s = k => dong.reduce((a, x) => a + n(x[k]), 0);
  const doi = s('cuoc_vnd') + s('ghep_vnd') + s('ps_vnd') + s('dc_vnd');
  const tra = (tienVe ?? []).filter(v => !v.huy).reduce((a, v) => a + n(v.so_tien_vnd), 0);
  return { cuoc_vnd: String(s('cuoc_vnd')), ghep_vnd: String(s('ghep_vnd')), ps_vnd: String(s('ps_vnd')), chi_ho_vnd: String(s('chi_ho_vnd')),
    dc_vnd: String(s('dc_vnd')), doi_vnd: String(doi), tra_vnd: String(tra), con_vnd: String(doi - tra), so_chang: dong.length,
    chua_gia: dong.filter(x => x.cuoc_vnd === null).length, khac_gia: dong.filter(x => x.cuoc_tay && x.gia_bang_vnd !== x.cuoc_vnd).length,
    chua_doc: dong.filter(x => x.chua_doc > 0).length, khoan_la: 0, trung: dong.filter(x => x.trung_gui).length,
    chang_bo: dong.filter(x => x.chang_con === false).length, cont_lap: dong.filter(x => Array.isArray(x.cont_lap)).length };
}
// Dấu các dòng đang gom (máy chủ thật: md5 của jsonb các dòng): gửi kèm, khác thì BANG_KE_DOI.
const dau = dong => crypto.createHash('md5').update(JSON.stringify(dong)).digest('hex');
const trangThai = bk => (!bk ? 'nhap' : bk.trang_thai === 'da_gui' ? 'gui' : n(tong(bk.dong, bk.tien_ve).con_vnd) === 0 ? 'du' : 'doi');
function getBangKe(w, thang) {
  const m = thang ?? '2026-11-01';
  const bk = w.bk[m];
  const dong = bk ? bk.dong : w.nhap[m] ?? [];
  const t = tong(dong, bk?.tien_ve);
  // Tháng sau chỉ hiện khi có chặng gom vào (ghi sau lúc gửi tháng này), như doixe._thang_bk.
  const months = ['2026-09-01', '2026-10-01', '2026-11-01', ...(w.nhap['2026-12-01'] ? ['2026-12-01'] : [])];
  const congNo = Object.values(w.bk).reduce((a, k) => a + n(tong(k.dong, k.tien_ve).con_vnd), 0);
  return { hom_nay: HOM_NAY, thang: m, ben: w.ben, cong_no_vnd: String(congNo),
    thang_ds: months.map(x => ({ thang: x, trang_thai: trangThai(w.bk[x]) })),
    bang_ke: bk ? { id: bk.id, so: bk.so, trang_thai: bk.trang_thai, gui_ngay: bk.gui_ngay, gui_actor: 'nv@gia', gui_luc: '03/11 09:20',
      doi_chieu_actor: bk.doi_chieu_luc ? 'nv@gia' : null, doi_chieu_luc: bk.doi_chieu_luc, thu_du: trangThai(bk) === 'du' } : null,
    dong, tong: t, dau: bk ? null : dau(dong), tien_ve: bk?.tien_ve ?? [] };
}
const loi = (status, error, message) => Object.assign(Error(message), { status, error });
function write(w, route, b) {
  const ev = (viec, truoc, sau, lyDo = null) => w.events.unshift({ id: ++w.seq, viec, actor: 'nv@gia', actor_name: 'nv', luc: '18/11 09:30', truoc, sau, ly_do: lyDo });
  if (route === '/api/v7/doixe/bang-ke/gui') {
    if (w.bk[b.thang]) throw loi(409, 'BANG_KE_DA_GUI', 'Bảng kê tháng này đã gửi. Tải lại.');
    const dong = w.nhap[b.thang];
    const t = tong(dong);
    if (t.doi_vnd !== b.doi_vnd || t.so_chang !== b.so_chang || dau(dong) !== b.dau) {
      throw loi(409, 'BANG_KE_DOI', 'Bảng kê vừa đổi ở máy khác. Tải lại, xem lại số rồi bấm lại.');
    }
    w.bk[b.thang] = { id: ++w.seq, so: `HTH-${b.thang.slice(0, 7)}`, trang_thai: 'da_gui', gui_ngay: HOM_NAY, doi_chieu_luc: null, tien_ve: [],
      dong: dong.map((x, i) => ({ ...x, id: 500 + i, stt: i + 1, dc_vnd: null, dieu_chinh: [] })) };
    delete w.nhap[b.thang];
    ev('gui_bang_ke', { thang: b.thang }, { thang: b.thang, so: w.bk[b.thang].so, so_chang: t.so_chang, doi_vnd: t.doi_vnd });
    return { ok: true, so: w.bk[b.thang].so, doi_vnd: t.doi_vnd, so_chang: t.so_chang };
  }
  if (route === '/api/v7/doixe/bang-ke/doi-chieu') {
    const bk = w.bk[b.thang];
    if (tong(bk.dong).doi_vnd !== b.doi_vnd) throw loi(409, 'BANG_KE_DOI', 'Bảng kê vừa đổi ở máy khác.');
    bk.trang_thai = 'da_doi_chieu'; bk.doi_chieu_luc = '18/11 09:31';
    ev('doi_chieu_xong', {}, { thang: b.thang, doi_vnd: b.doi_vnd });
    return { ok: true, doi_vnd: b.doi_vnd };
  }
  if (route === '/api/v7/doixe/bang-ke/dieu-chinh') {
    const bk = Object.values(w.bk).find(k => k.dong.some(x => x.id === b.dong_id));
    if (bk.trang_thai !== 'da_gui') throw loi(409, 'BANG_KE_DA_DOI_CHIEU', 'Bảng kê đã đối chiếu xong: không ghi điều chỉnh nữa.');
    const x = bk.dong.find(y => y.id === b.dong_id);
    const doi0 = n(tong(bk.dong).doi_vnd);
    if (b.doi_vnd !== String(doi0)) throw loi(409, 'BANG_KE_DOI', 'Bảng kê vừa đổi ở máy khác. Tải lại, xem lại số rồi bấm lại.');
    x.dc_vnd = String(n(x.dc_vnd) + Number(b.so_tien_vnd));
    x.dieu_chinh.push({ id: ++w.seq, so_tien_vnd: b.so_tien_vnd, ly_do: b.ly_do, actor: 'nv@gia', actor_name: 'nv', luc: '18/11 09:32' });
    ev('dieu_chinh_bk', { thang: '2026-10-01', container: x.container, doi_vnd: String(doi0) }, { so_tien_vnd: b.so_tien_vnd, doi_vnd: String(doi0 + Number(b.so_tien_vnd)) }, b.ly_do);
    return { ok: true, doi_truoc_vnd: String(doi0), doi_sau_vnd: String(doi0 + Number(b.so_tien_vnd)) };
  }
  if (route === '/api/v7/doixe/bang-ke/tien-ve') {
    const bk = w.bk[b.thang];
    if (bk.trang_thai !== 'da_doi_chieu') throw loi(409, 'BANG_KE_CHUA_DOI_CHIEU', 'Bảng kê chưa đối chiếu xong.');
    const con = n(tong(bk.dong, bk.tien_ve).con_vnd);
    // Như doixe.ghi_tien_ve (audit DX-03): số còn phải thu đang thấy khác thì BANG_KE_DOI.
    if (b.con_vnd !== String(con)) throw loi(409, 'BANG_KE_DOI', 'Bảng kê vừa đổi ở máy khác. Tải lại, xem lại số rồi bấm lại.');
    if (Number(b.so_tien_vnd) > con) throw loi(409, 'TIEN_VE_THUA', 'Số tiền lớn hơn số còn phải thu.');
    bk.tien_ve.push({ id: ++w.seq, ngay: b.ngay, so_tien_vnd: b.so_tien_vnd, actor: 'nv@gia', actor_name: 'nv', luc: '18/11 09:40', huy: null });
    ev('ghi_tien_ve', { con_vnd: String(con) }, { thang: b.thang, ngay: b.ngay, so_tien_vnd: b.so_tien_vnd, con_vnd: String(con - Number(b.so_tien_vnd)) });
    return { ok: true, con_truoc_vnd: String(con), con_sau_vnd: String(con - Number(b.so_tien_vnd)) };
  }
  if (route === '/api/v7/doixe/bang-ke/tien-ve/huy') {
    const v = Object.values(w.bk).flatMap(k => k.tien_ve).find(x => x.id === b.tien_ve_id);
    v.huy = { actor: 'nv@gia', actor_name: 'nv', luc: '18/11 09:45', ly_do: b.ly_do };
    return { ok: true };
  }
  if (route === '/api/v7/doixe/thu/cuoc') {
    const x = Object.values(w.nhap).flat().find(y => y.chang_id === b.chang_id);
    if ((x.cuoc_tay ? x.cuoc_vnd : null) !== b.truoc) throw loi(409, 'CHANGED', 'Ô này vừa đổi ở máy khác. Tải lại rồi sửa.');
    x.cuoc_tay = b.gia_tri !== null; x.cuoc_vnd = b.gia_tri ?? x.gia_bang_vnd;
    return { ok: true, cuoc_tay: x.cuoc_tay, cuoc_vnd: x.cuoc_vnd };
  }
  if (route === '/api/v7/doixe/thu/tuyen') {
    const x = Object.values(w.nhap).flat().find(y => y.chang_id === b.chang_id);
    const t = w.gia.tuyen.find(y => y.id === b.tuyen_id);
    Object.assign(x, { tuyen_id: t.id, tuyen: t.ten, gia_bang_vnd: t.gia[0].gia_vnd, cuoc_vnd: x.cuoc_tay ? x.cuoc_vnd : t.gia[0].gia_vnd });
    return { ok: true, so_chang: b.nho ? 1 : 1 };
  }
  if (route === '/api/v7/doixe/chang/sua') {
    const x = Object.values(w.nhap).flat().find(y => y.chang_id === b.chang_id);
    if (x.ghi_chu !== b.truoc) throw loi(409, 'CHANGED', 'Ô này vừa đổi ở máy khác. Tải lại rồi sửa.');
    x.ghi_chu = b.gia_tri;
    const m = /_ ?Cân (\d+)k/.exec(b.gia_tri ?? '');
    if (m) { x.ps = [item(`Cân ${m[1]}k`, 'Cân', String(Number(m[1]) * 1000), { chi_ho: true })]; x.ps_vnd = String(Number(m[1]) * 1000); x.chua_doc = 0; }
    return { ok: true, cach: 'ghi_de' };
  }
  if (route === '/api/v7/doixe/gia') {
    const t = w.gia.tuyen.find(y => y.id === b.tuyen_id);
    // Như doixe.luu_gia (audit DX-01): ngày trước tháng này phải kèm xác nhận.
    if (b.tu_ngay < `${w.gia.hom_nay.slice(0, 7)}-01` && b.xac_nhan_ngay_cu !== true) throw loi(409, 'NGAY_GIA_CU', 'Ngày áp dụng trước tháng này.');
    t.gia.push({ tu_ngay: b.tu_ngay, gia_vnd: b.gia_vnd });
    return { ok: true, so_chang: t.cho_doi.filter(d => d >= b.tu_ngay).length };
  }
  if (route === '/api/v7/doixe/phat-sinh') {
    const p = w.gia.phat_sinh.find(y => y.ma === b.ma);
    Object.assign(p, { cach: b.cach, muc_vnd: b.muc_vnd, muc_them_vnd: b.muc_them_vnd, chi_ho: b.chi_ho, ten_goc: b.ten_goc });
    return { ok: true };
  }
  if (route === '/api/v7/doixe/tuyen') {
    if (b.tuyen_id !== null) {
      // Như doixe.luu_tuyen (audit DX-06): bộ tên gốc đang thấy khác bộ hiện tại thì TUYEN_DOI.
      const t = w.gia.tuyen.find(y => y.id === b.tuyen_id);
      if (JSON.stringify([...b.ten_goc_truoc].sort()) !== JSON.stringify([...t.ten_goc].sort())) throw loi(409, 'TUYEN_DOI', 'Tên gốc của tuyến vừa đổi ở máy khác. Tải lại rồi sửa.');
      Object.assign(t, { dang_dung: b.dang_dung ?? true, ten_goc: b.ten_goc.map(x => `${x.hang ?? ''}|${x.tinh ?? ''}`) });
      return { ok: true, tuyen_id: t.id };
    }
    w.gia.tuyen.push({ id: ++w.seq, loai: b.loai, hang: b.hang, di: b.di, den: b.den, ten: `${b.hang} · ${b.di}`, dang_dung: true,
      gia: [{ tu_ngay: b.tu_ngay, gia_vnd: b.gia_vnd }], ten_goc: [], cho_doi: [] });
    return { ok: true, tuyen_id: w.seq };
  }
  throw loi(404, 'NOT_FOUND', 'x');
}

function makeServer(w) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body, extra = {}) => { response.writeHead(status, { 'Content-Type': type, ...extra }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    w.calls.push(`${request.method} ${route}${url.search}`);
    if (route.startsWith('/api/v7/doixe')) {
      if (request.method === 'GET') {
        if (w.down) return out({ error: 'DB_UNAVAILABLE', message: 'x' }, 503);
        const q = url.searchParams;
        if (route === '/api/v7/doixe/bang-ke') return setTimeout(() => out(getBangKe(w, q.get('thang'))), w.delay);
        if (route === '/api/v7/doixe/bang-gia') return out(w.gia);
        if (route === '/api/v7/doixe/bang-ke/lich-su') return out({ events: w.events });
        if (route === '/api/v7/doixe/bang-ke.xlsx') return send(200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'PK-gia',
          { 'Content-Disposition': `attachment; filename="BangKe_HTH_T${q.get('thang').slice(5, 7)}_2026.xlsx"` });
      }
      let raw = '';
      request.on('data', chunk => { raw += chunk; });
      request.on('end', () => setTimeout(() => {
        const b = JSON.parse(raw);
        w.posts.push({ route, body: b });
        if (w.failNext > 0) { w.failNext -= 1; request.socket.destroy(); return; }
        try {
          if (w.keys.has(b.idempotency_key)) return out({ ...w.keys.get(b.idempotency_key), lap_lai: true });
          const result = write(w, route, b);
          w.keys.set(b.idempotency_key, result);
          return out(result);
        } catch (e) { return out({ error: e.error, message: e.message }, e.status ?? 500); }
      }, w.delay));
      return undefined;
    }
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
    const context = await browser.newContext({ viewport, acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = `http://127.0.0.1:${server.address().port}`;
    await page.goto(`${base}/doi-xe-bang-ke.html${query}`);
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
  await page.screenshot({ path: path.join(process.env.SHOTS_DIR, `doi-xe-bang-ke-${name}.png`), fullPage: true });
}
const posts = (w, route) => w.posts.filter(p => p.route === route);
const idle = page => page.locator('[data-act="nut-chinh"]:not([disabled]), .dxt-pill.tt-du').first().waitFor();

test('Bảng kê đang gom: ba số, thanh tháng có trạng thái, Trước khi gửi lọc đúng dòng, bấm container xem phát sinh', () => withPage(async page => {
  await shot(page, '1-dang-gom');
  assert.match(await page.locator('#dx-head').innerText(), /Người và xe[\s\S]*Bảng kê gửi HTH[\s\S]*Bảng giá/);
  assert.match(await page.locator('.dxt-thang-h').innerText(), /Tháng 9\s+thu đủ[\s\S]*Tháng 10\s+đang đối chiếu[\s\S]*Tháng 11\s+đang gom[\s\S]*HTH còn nợ \(các tháng đã gửi\)\s+2\.680\.000/);
  assert.match(await page.locator('.dxt-card').innerText(), /Bảng kê tháng 11\/2026 gửi HTH[\s\S]*Đang gom · chưa gửi[\s\S]*Đòi HTH\s+3\.850\.000[\s\S]*HTH đã trả\s+0[\s\S]*Còn phải thu\s+3\.850\.000/);
  assert.equal(await page.locator('.dxt-cocau').innerText(), 'Cước 3.200.000 · Đóng ghép 500.000 · Chi hộ 150.000 · 5 chặng');
  assert.equal(await page.locator('[data-act="nut-chinh"]').innerText(), 'Gửi bảng kê');
  const viec = page.locator('.dxt-viec');
  assert.match(await viec.innerText(), /Trước khi gửi:\s+1 chặng chưa có giá\s+1 chặng giá khác bảng giá\s+1 chặng có khoản phát sinh chưa tính được/);
  await viec.getByText('1 chặng chưa có giá').click();
  assert.equal(await page.locator('.dxt-dong').count(), 1);
  assert.match(await page.locator('.dxt-dong').innerText(), /MAUU2000002[\s\S]*HÀNG GIẢ B · TỈNH B[\s\S]*Chưa có giá/);
  assert.equal(await page.locator('.dxt-loc.on').innerText(), 'Chưa có giá (1)');
  await page.locator('[data-loc="all"]').click();
  assert.equal(await page.locator('.dxt-dong').count(), 5);
  assert.match(await page.locator('.dxt-dong').nth(2).innerText(), /Rút mooc/);
  assert.match(await page.locator('.dxt-tong').innerText(), /Tổng\s+5 chặng\s+3\.200\.000\s+500\.000\s+150\.000\s+3\.850\.000/);
  await page.locator('.dxt-cont', { hasText: 'MAUU2000001' }).click();
  assert.match(await page.locator('.dxt-ct').innerText(), /Bảng giá: Hàng giả · Tỉnh A → Cảng A · 1\.000\.000[\s\S]*Kiểm hoá: 150\.000 · chi hộ/);
  assert.equal(await page.locator('.dxt-cont', { hasText: 'MAUU2000001' }).getAttribute('aria-expanded'), 'true');
}));

test('Đang gom: giá tay cho chặng chưa có giá, dùng giá bảng, gắn tuyến nhớ tên gốc, sửa ghi chú phát sinh tại dòng', () => withPage(async (page, w) => {
  await page.locator('.dxt-cont', { hasText: 'MAUU2000002' }).click();
  await page.locator('#dxt-cuoc').fill('2,5');
  await page.locator('[data-act="luu-cuoc"]').click();
  assert.match(await page.locator('.dxt-ct .dx-loi').innerText(), /Giá cước: số lẻ/);
  assert.equal(posts(w, '/api/v7/doixe/thu/cuoc').length, 0, 'số lẻ chặn ở máy');
  await page.locator('#dxt-cuoc').fill('2.400.000');
  await page.locator('#dxt-cuoc').press('Enter');
  await page.locator('.dxt-dong', { hasText: 'MAUU2000002' }).filter({ hasText: '2.400.000' }).waitFor();
  assert.deepEqual(posts(w, '/api/v7/doixe/thu/cuoc')[0].body, { idempotency_key: posts(w, '/api/v7/doixe/thu/cuoc')[0].body.idempotency_key,
    chang_id: 202, truoc: null, gia_tri: '2400000' });
  assert.match(await page.locator('#dx-toast').innerText(), /Đã lưu giá cước dòng MAUU2000002/);
  // Dòng giá tay khác bảng: một bấm về giá bảng.
  await page.locator('.dxt-cont', { hasText: 'MAUU2000004' }).click();
  await page.locator('[data-act="dung-gia"]').click();
  await page.locator('.dxt-dong', { hasText: 'MAUU2000004' }).filter({ hasText: '1.000.000' }).waitFor();
  assert.deepEqual(posts(w, '/api/v7/doixe/thu/cuoc')[1].body.gia_tri, null);
  // Gắn tuyến, tick nhớ (mặc định bật).
  await page.locator('.dxt-cont', { hasText: 'MAUU2000004' }).click();
  await page.locator('.dxt-cont', { hasText: 'MAUU2000002' }).click();
  assert.match(await page.locator('.dxt-chk').innerText(), /Nhớ cho mọi chặng ghi «HANG GIA B · TINH B»/);
  await page.locator('#dxt-tuyen option[value="1"]').waitFor({ state: 'attached' });
  assert.deepEqual(await page.locator('#dxt-tuyen option').allInnerTexts(), ['Chưa gắn tuyến', 'Hàng giả · Tỉnh A → Cảng A'], 'chặng hàng chỉ chọn được tuyến hàng');
  await page.locator('#dxt-tuyen').selectOption('1');
  await page.locator('[data-act="gan-tuyen"]').click();
  await page.locator('#dx-toast', { hasText: 'Đã gắn tuyến' }).waitFor();
  assert.deepEqual(posts(w, '/api/v7/doixe/thu/tuyen')[0].body.nho, true);
  // Chặng chuyển cảng: chỉ tuyến chuyển cảng, không có ô Nhớ (tên gốc chỉ cho chặng hàng).
  await page.locator('.dxt-cont', { hasText: 'MAUU2000005' }).click();
  await page.locator('#dxt-tuyen option[value="2"]').waitFor({ state: 'attached' });
  assert.deepEqual(await page.locator('#dxt-tuyen option').allInnerTexts(), ['Chưa gắn tuyến', 'Chuyển cảng · Các cảng']);
  assert.equal(await page.locator('.dxt-chk').count(), 0);
  // Ghi chú phát sinh sửa tại dòng: đọc lại thành khoản.
  await page.locator('.dxt-cont', { hasText: 'MAUU2000004' }).click();
  await page.locator('#dxt-ghichu').fill('_ Cân 575k');
  await page.locator('#dxt-ghichu').press('Enter');
  await page.locator('#dx-toast', { hasText: 'Đã lưu ghi chú dòng MAUU2000004' }).waitFor();
  assert.deepEqual(posts(w, '/api/v7/doixe/chang/sua')[0].body.gia_tri, '_ Cân 575k');
  assert.match(await page.locator('.dxt-dong', { hasText: 'MAUU2000004' }).innerText(), /575\.000/);
}));

test('Gửi bảng kê: khung xác nhận có cảnh báo, gửi đúng số đang thấy, tải Excel, sang đang đối chiếu', () => withPage(async (page, w) => {
  await page.locator('[data-act="nut-chinh"]').click();
  const panel = page.locator('.dxt-panel');
  assert.match(await panel.innerText(), /Gửi bảng kê tháng 11\/2026 cho HTH[\s\S]*5 chặng · đòi HTH 3\.850\.000[\s\S]*1 chặng chưa có giá: ô cước để trống[\s\S]*Tháng 11 chưa hết/);
  assert.equal(await page.locator('.dxt-viec').count(), 0, 'khung mở thì ẩn ô Trước khi gửi');
  await shot(page, '2-gui');
  const download = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'Tải Excel và đánh dấu đã gửi' }).dblclick();
  assert.equal((await download).suggestedFilename(), 'BangKe_HTH_T11_2026.xlsx');
  await page.locator('.dxt-pill', { hasText: 'đang đối chiếu' }).waitFor();
  const sent = posts(w, '/api/v7/doixe/bang-ke/gui');
  assert.equal(sent.length, 1, 'bấm đúp chỉ gửi một lệnh');
  assert.match(sent[0].body.dau, /^[0-9a-f]{32}$/, 'gửi kèm dấu các dòng đang thấy');
  assert.deepEqual({ ...sent[0].body, idempotency_key: 'k', dau: 'd' }, { idempotency_key: 'k', thang: '2026-11-01', doi_vnd: '3850000', so_chang: 5, dau: 'd' });
  assert.match(await page.locator('#dx-toast').innerText(), /Đã đánh dấu gửi bảng kê tháng 11\/2026 \(đòi HTH 3\.850\.000\)\. Đã tải file BangKe_HTH_T11_2026\.xlsx/);
  assert.equal(await page.locator('[data-act="nut-chinh"]').innerText(), 'Đối chiếu xong');
  assert.match(await page.locator('.dxt-ghichu').innerText(), /bấm nút ± ở cuối dòng/);
}, { query: '?thang=2026-11' }));

test('Đã gửi: ô điều chỉnh mở ngay dưới dòng, lý do bắt buộc, Đòi HTH trước → sau; Đối chiếu xong thì thôi ±', () => withPage(async (page, w) => {
  await shot(page, '3-da-gui');
  assert.match(await page.locator('.dxt-card').innerText(), /Đã gửi 03\/11 · đang đối chiếu[\s\S]*Số HTH-2026-10[\s\S]*Đòi HTH\s+2\.680\.000/);
  assert.equal(await page.locator('[data-act="mo-dc"]').count(), 3);
  await page.locator('[data-act="mo-dc"]').first().click();
  const dc = page.locator('.dxt-dc');
  assert.equal(await page.locator('.dxt-dong').first().locator('.dxt-dc').count(), 1, 'ô điều chỉnh nằm ngay dưới dòng đó');
  await page.locator('#dxt-dc-tien').fill('390000');
  assert.equal(await page.locator('#dxt-dc-xem').innerText(), 'Đòi HTH: 2.680.000 → 2.290.000 · dòng này 1.380.000 → 990.000');
  await dc.getByRole('button', { name: 'Ghi điều chỉnh' }).click();
  assert.equal(await page.locator('#dxt-dc-loi').innerText(), 'Ghi lý do: HTH thắc mắc gì, ai báo.');
  assert.equal(posts(w, '/api/v7/doixe/bang-ke/dieu-chinh').length, 0);
  await page.locator('#dxt-dc-lydo').fill('HTH báo hạ sớm tính hai lần');
  await page.locator('#dxt-dc-lydo').press('Enter');
  await page.locator('.dxt-dong').first().filter({ hasText: '−390.000' }).waitFor();
  assert.deepEqual({ ...posts(w, '/api/v7/doixe/bang-ke/dieu-chinh')[0].body, idempotency_key: 'k' },
    { idempotency_key: 'k', dong_id: 301, so_tien_vnd: '-390000', ly_do: 'HTH báo hạ sớm tính hai lần', doi_vnd: '2680000' });
  assert.match(await page.locator('.dxt-so').innerText(), /Đòi HTH\s+2\.290\.000/);
  assert.match(await page.locator('.dxt-cocau').innerText(), /Điều chỉnh −390\.000/);
  // Ghi xong dòng vẫn mở: thấy ngay điều chỉnh vừa ghi, ô điều chỉnh đóng lại.
  assert.match(await page.locator('.dxt-ct').innerText(), /Điều chỉnh −390\.000 · HTH báo hạ sớm tính hai lần · nv 18\/11 09:32/);
  assert.equal(await page.locator('.dxt-dc').count(), 0);
  await page.locator('[data-act="nut-chinh"]').click();
  assert.match(await page.locator('.dxt-panel').innerText(), /HTH đồng ý đòi 2\.290\.000 sau 1 điều chỉnh \(−390\.000\)[\s\S]*không ghi điều chỉnh nữa/);
  await page.locator('[data-act="doi-chieu"]').click();
  await page.locator('.dxt-pill', { hasText: 'chờ HTH trả' }).waitFor();
  assert.equal(await page.locator('[data-act="mo-dc"]').count(), 0, 'đối chiếu xong thì không còn nút ±');
  assert.deepEqual(posts(w, '/api/v7/doixe/bang-ke/doi-chieu')[0].body.doi_vnd, '2290000');
}, { query: '?thang=2026-10' }));

test('Tiền về: ngày mặc định hôm nay, trả thừa chặn tại ô, trả thiếu ghi được, đủ thì thu đủ; hủy cần lý do', () => withPage(async (page, w) => {
  await page.locator('[data-act="nut-chinh"]').click();
  assert.equal(await page.locator('#dxt-tv-ngay').inputValue(), '18/11');
  assert.equal(await page.locator('#dxt-tv-tien').inputValue(), '2.680.000');
  await page.locator('#dxt-tv-tien').fill('2.680.001');
  await page.locator('[data-act="ghi-tv"]').click();
  assert.match(await page.locator('#dxt-tv-loi').innerText(), /Lớn hơn số còn phải thu \(2\.680\.000\)/);
  assert.equal(posts(w, '/api/v7/doixe/bang-ke/tien-ve').length, 0);
  await page.locator('#dxt-tv-tien').fill('2.000.000');
  assert.equal(await page.locator('#dxt-tv-xem').innerText(), 'Còn phải thu: 2.680.000 → 680.000');
  assert.match(await page.locator('#dxt-tv-canh').innerText(), /Trả thiếu 680\.000: tháng 10\/2026 vẫn chờ phần còn lại/);
  await shot(page, '4-tien-ve');
  await page.locator('#dxt-tv-tien').press('Enter');
  await page.locator('#dx-toast', { hasText: 'còn thiếu 680.000' }).waitFor();
  assert.match(await page.locator('.dxt-so').innerText(), /HTH đã trả\s+2\.000\.000[\s\S]*Còn phải thu\s+680\.000/);
  await page.locator('[data-act="nut-chinh"]').click();
  await page.locator('[data-act="ghi-tv"]').click();
  await page.locator('.dxt-pill', { hasText: 'HTH trả đủ 18/11' }).waitFor();
  assert.equal(await page.locator('[data-act="nut-chinh"]').count(), 0, 'thu đủ: không còn nút chính');
  assert.match(await page.locator('.dxt-thang.on').innerText(), /thu đủ/);
  // Hủy lần tiền về: lý do bắt buộc.
  await page.locator('[data-act="mo-huy"]').first().click();
  const huy = page.locator('[data-act="huy-tv"]');
  assert.equal(await huy.isDisabled(), true);
  assert.match(await page.locator('.dxt-panel').innerText(), /Còn phải thu: 0 → 2\.000\.000/);
  await page.locator('#dxt-huy-lydo').fill('ghi nhầm số tiền');
  await huy.click();
  await page.locator('.dxt-tv .huy').waitFor();
  assert.match(await page.locator('.dxt-tv').innerText(), /Đã hủy: 18\/11: 2\.000\.000 \(ghi nhầm số tiền\)/);
}, { setup: w => { w.bk['2026-10-01'].trang_thai = 'da_doi_chieu'; w.bk['2026-10-01'].doi_chieu_luc = '12/11 11:02'; }, query: '?thang=2026-10' }));

test('Mất mạng khi ghi: bấm lại dùng lại mã yêu cầu, máy chủ không ghi hai lần', () => withPage(async (page, w) => {
  await page.locator('[data-act="nut-chinh"]').click();
  // Máy chủ đã ghi nhưng câu trả lời mất giữa đường (cắt socket thì Chrome tự gửi lại, nên chặn ở phía trình duyệt).
  await page.route('**/api/v7/doixe/bang-ke/tien-ve', async route => { await route.fetch(); await route.abort('failed'); }, { times: 1 });
  await page.locator('[data-act="ghi-tv"]').click();
  await page.locator('.dx-toast.err', { hasText: 'Mất kết nối' }).waitFor();
  await page.locator('[data-act="ghi-tv"]').click();
  await page.locator('.dxt-pill', { hasText: 'HTH trả đủ' }).waitFor();
  const sent = posts(w, '/api/v7/doixe/bang-ke/tien-ve');
  assert.equal(sent.length, 2);
  assert.equal(sent[0].body.idempotency_key, sent[1].body.idempotency_key);
  assert.equal(w.bk['2026-10-01'].tien_ve.length, 1);
}, { setup: w => { w.bk['2026-10-01'].trang_thai = 'da_doi_chieu'; }, query: '?thang=2026-10' }));

test('Chặng trùng dòng đã gửi báo trước khi gửi; tháng sau (chặng ghi sau lúc gửi) xem được nhưng chưa gửi được', () => withPage(async page => {
  assert.match(await page.locator('.dxt-viec').innerText(), /1 chặng trùng dòng đã gửi \(cùng ngày, container\)/);
  await page.locator('.dxt-viec').getByText('1 chặng trùng dòng đã gửi (cùng ngày, container)').click();
  assert.equal(await page.locator('.dxt-dong').count(), 1);
  await page.locator('.dxt-cont', { hasText: 'MAUU2000003' }).click();
  assert.match(await page.locator('.dxt-ct').innerText(), /Cùng ngày, container với một dòng đã gửi ở bảng kê tháng 10\/2026/);
  await page.locator('[data-act="loc"][data-loc="all"]').click();
  await page.locator('[data-act="nut-chinh"]').click();
  assert.match(await page.locator('.dxt-panel').innerText(), /1 chặng cùng ngày, container với dòng đã gửi: xem có phải chặng đã gửi bị nhập lại/);
  await page.locator('[data-act="dong-panel"]').click();
  await page.locator('[data-act="thang"][data-thang="2026-12-01"]').click();
  await page.locator('.dxt-card', { hasText: 'Bảng kê tháng 12/2026' }).waitFor();
  assert.equal(await page.locator('[data-act="nut-chinh"]').count(), 0, 'tháng chưa tới: không có nút Gửi');
  assert.match(await page.locator('.dxt-ghichu').innerText(), /Tháng 12 chưa tới[\s\S]*Gửi được từ ngày 01\/12/);
}, { setup: w => {
  w.nhap['2026-11-01'][2].trung_gui = '2026-10-01';
  w.nhap['2026-12-01'] = [nhap(206, '2026-11-17', 'MAUU2000006')];
} }));

test('Đối chiếu xong nhắc dòng chưa có giá và chặng đã bỏ (sau bước này không điều chỉnh được nữa)', () => withPage(async page => {
  assert.match(await page.locator('.dxt-locs').innerText(), /Chặng đã bỏ \(1\)/);
  await page.locator('[data-act="nut-chinh"]').click();
  assert.match(await page.locator('.dxt-panel').innerText(),
    /1 dòng chưa có giá: đối chiếu xong thì không thêm tiền[\s\S]*1 dòng có chặng đã xóa hoặc bỏ ở sổ tài xế sau khi gửi/);
}, { setup: w => {
  Object.assign(w.bk['2026-10-01'].dong[1], { cuoc_vnd: null, gia_bang_vnd: null });
  w.bk['2026-10-01'].dong[2].chang_con = false;
}, query: '?thang=2026-10' }));

test('Bảng giá: giá hôm nay theo tuyến, đổi giá báo số chặng đổi theo, sửa khoản phát sinh (chi hộ), thêm tuyến', () => withPage(async (page, w) => {
  await page.locator('[data-man="gia"]').click();
  await page.locator('.dxt-gia').waitFor();
  await shot(page, '5-bang-gia');
  assert.match(page.url(), /man=gia/);
  assert.match(await page.locator('.dxt-g').first().innerText(), /Giá cước theo tuyến[\s\S]*Hàng giả\s+Tỉnh A → Cảng A\s+1\.000\.000\s+01\/01\/2026[\s\S]*70% giá tuyến/);
  assert.match(await page.locator('.dxt-g').nth(1).innerText(), /Kiểm hoá\s+Cố định\s+Chưa có mức\s+Chi hộ[\s\S]*Neo\s+Theo ngày \(chưa có mức\)/);
  await page.locator('[data-act="sua-gia"]').first().click();
  assert.equal(await page.locator('#dxt-gia-tu').inputValue(), '01/12/2026', 'mặc định có đủ năm (audit DX-01)');
  await page.locator('#dxt-gia-tu').fill('03/11');
  assert.match(await page.locator('#dxt-gia-note').innerText(), /từ 03\/11\/2026 đổi theo giá mới: 1 chặng/);
  await page.locator('#dxt-gia-val').fill('1.050.000');
  await page.locator('#dxt-gia-val').press('Enter');
  await page.locator('#dx-toast', { hasText: 'Đã lưu giá mới' }).waitFor();
  assert.deepEqual({ ...posts(w, '/api/v7/doixe/gia')[0].body, idempotency_key: 'k' }, { idempotency_key: 'k', tuyen_id: 1, tu_ngay: '2026-11-03', gia_vnd: '1050000' });
  await page.locator('[data-act="sua-ps"][data-ma="neo"]').click();
  await page.locator('#dxt-ps-muc').fill('1.300.000');
  await page.locator('#dxt-ps-them').fill('1.700.000');
  await page.locator('[data-act="luu-ps"]').click();
  await page.locator('#dx-toast', { hasText: 'Đã lưu khoản Neo' }).waitFor();
  assert.deepEqual(posts(w, '/api/v7/doixe/phat-sinh')[0].body.muc_them_vnd, '1700000');
  assert.match(await page.locator('.dxt-g').nth(1).innerText(), /Neo\s+Theo ngày: ngày đầu 1\.300\.000, mỗi ngày thêm 1\.700\.000/);
  await page.locator('[data-act="mo-tuyen-moi"]').click();
  await page.locator('#dxt-tm-hang').fill('Hàng giả C');
  await page.locator('[data-act="them-tuyen"]').click();
  assert.match(await page.locator('.dxt-g-sua.moi .dx-loi').innerText(), /Nhập nơi đi/);
  await page.locator('#dxt-tm-di').fill('Tỉnh C');
  await page.locator('#dxt-tm-gia').fill('900.000');
  await page.locator('[data-act="them-tuyen"]').click();
  await page.locator('#dx-toast', { hasText: 'Đã thêm tuyến' }).waitFor();
  assert.deepEqual(posts(w, '/api/v7/doixe/tuyen')[0].body.tu_ngay, '2026-01-01');
}));

test('1280×720 và 1265×560: không cuộn ngang trang, bảng chặng cuộn trong khung; thẻ Người và xe về màn đợt 1', () => withPage(async page => {
  for (const size of [{ width: 1280, height: 720 }, { width: 1265, height: 560 }]) {
    await page.setViewportSize(size);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, `cuộn ngang ở ${size.width}`);
    const box = await page.locator('[data-act="nut-chinh"]').boundingBox();
    assert.ok(box && box.y + box.height < size.height, 'nút chính trong khung đầu');
  }
  assert.equal(await page.locator('.dx-man a').first().getAttribute('href'), '/doi-xe.html');
}));

test('Lịch sử bảng kê và lỗi tải: Thử lại', () => withPage(async (page, w) => {
  await page.locator('[data-act="lich-su"]').click();
  // Panel mở ngay với "Đang tải…", Lịch sử về sau: chờ chữ của bản đã tải, không đọc lúc còn tải.
  await page.locator('.dxt-panel.ls', { hasText: 'Chưa có thay đổi nào' }).waitFor();
  assert.match(await page.locator('.dxt-panel.ls').innerText(), /Lịch sử bảng kê[\s\S]*Chưa có thay đổi nào/);
  await page.locator('.dxt-panel.ls [data-act="dong-panel"]').click();
  w.down = true;
  await page.locator('[data-act="thang"][data-thang="2026-10-01"]').click();
  await page.locator('.dx-err').waitFor();
  assert.match(await page.locator('.dx-err').innerText(), /Đang hiện số đọc lần trước/);
  w.down = false;
  await page.locator('[data-act="thu-lai"]').click();
  await page.locator('.dxt-pill', { hasText: 'đang đối chiếu' }).waitFor();
  await idle(page);
}));

// DOI-XE-CAU-TRUC-01 (F1): đổi mục giữ tháng người dùng đã chọn; chiều ngược lại (từ Người và xe sang đây) kiểm ở test-doi-xe-browser.js.
test('Đổi mục giữ tháng: mở thẳng thì "Người và xe" như cũ; bấm chip tháng, sang Bảng giá rồi về Bảng kê thì tháng vẫn giữ', () => withPage(async page => {
  const nguoi = page.locator('.dx-man a').first();
  assert.equal(await nguoi.getAttribute('href'), '/doi-xe.html', 'tháng mặc định do máy chủ chọn thì không mang');
  await page.locator('[data-act="thang"][data-thang="2026-10-01"]').click();
  await page.locator('.dxt-pill', { hasText: 'đã gửi' }).waitFor();
  assert.equal(await nguoi.getAttribute('href'), '/doi-xe.html?thang=2026-10');
  await page.locator('[data-man="gia"]').click();
  await page.locator('.dxt-gia').waitFor();
  assert.match(page.url(), /man=gia&thang=2026-10$/, 'Bảng giá giữ tháng trong địa chỉ');
  assert.equal(await nguoi.getAttribute('href'), '/doi-xe.html?thang=2026-10');
  await page.locator('[data-man="bangke"]').click();
  await page.locator('.dxt-card-h h2', { hasText: 'tháng 10' }).waitFor();
  assert.equal(await nguoi.getAttribute('href'), '/doi-xe.html?thang=2026-10');
}));

test('Đổi mục giữ tháng: mở thẳng Bảng giá kèm tháng thì "Người và xe" mang tháng, về Bảng kê đúng tháng đó', () => withPage(async page => {
  await page.locator('.dxt-gia').waitFor();
  assert.equal(await page.locator('.dx-man a').first().getAttribute('href'), '/doi-xe.html?thang=2026-10');
  await page.locator('[data-man="bangke"]').click();
  await page.locator('.dxt-card-h h2', { hasText: 'tháng 10' }).waitFor();
}, { query: '?man=gia&thang=2026-10' }));

test('Đổi mục giữ tháng: tháng sau (Bảng kê cho xem) không mang sang Người và xe; bấm sang thì trang đích đọc tháng mặc định', () => withPage(async page => {
  const yeuCau = [];
  await page.route(/\/api\/v7\/doixe(\?.*)?$/, route => { yeuCau.push(new URL(route.request().url()).search); return route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"DB_UNAVAILABLE","message":"x"}' }); });
  await page.locator('[data-act="thang"][data-thang="2026-12-01"]').click();
  await page.locator('.dxt-card-h h2', { hasText: 'tháng 12' }).waitFor();
  const nguoi = page.locator('.dx-man a').first();
  assert.equal(await nguoi.getAttribute('href'), '/doi-xe.html', 'tháng sau hôm nay không mang sang trang không nhận');
  await page.locator('[data-man="gia"]').click();
  await page.locator('.dxt-gia').waitFor();
  assert.equal(await nguoi.getAttribute('href'), '/doi-xe.html', 'Bảng giá cũng vậy');
  await Promise.all([page.waitForURL(/\/doi-xe\.html$/), nguoi.click()]);
  await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
  assert.deepEqual(yeuCau, [''], 'trang đích đọc không kèm tháng');
}, { setup: w => { w.nhap['2026-12-01'] = [nhap(401, '2026-12-02', 'MAUU3000001')]; } }));

test('Đổi mục giữ tháng: tháng mặc định không thành "đã chọn" sau khi sang Bảng giá rồi tải lại (F5)', () => withPage(async page => {
  await page.locator('[data-man="gia"]').click();
  await page.locator('.dxt-gia').waitFor();
  assert.doesNotMatch(page.url(), /thang=/, 'địa chỉ không ghi tháng mặc định');
  await page.reload();
  await page.locator('.dxt-gia').waitFor();
  assert.equal(await page.locator('.dx-man a').first().getAttribute('href'), '/doi-xe.html');
}));

test('Đổi giá tháng 12 (audit DX-01): ô ngày mặc định 01/01 năm sau; gõ 01/01 thiếu năm vẫn là năm sau; áp ngược phải gõ đủ năm và nút nói rõ', () => withPage(async (page, w) => {
  await page.locator('[data-act="sua-gia"]').first().click();
  assert.equal(await page.locator('#dxt-gia-tu').inputValue(), '01/01/2027');
  assert.match(await page.locator('#dxt-gia-note').innerText(), /^Áp dụng từ 01\/01\/2027\./);
  await page.locator('#dxt-gia-tu').fill('01/01');
  assert.match(await page.locator('#dxt-gia-note').innerText(), /^Áp dụng từ 01\/01\/2027\..*: 0 chặng\.$/);
  assert.equal(await page.locator('[data-act="luu-gia"]').innerText(), 'Lưu giá mới');
  await page.locator('#dxt-gia-tu').fill('01/01/2026');
  assert.match(await page.locator('#dxt-gia-note').innerText(), /Áp dụng từ 01\/01\/2026\..*: 2 chặng\. Ngày này trước tháng 12\/2026: giá áp ngược\./);
  assert.equal(await page.locator('[data-act="luu-gia"]').innerText(), 'Lưu, áp ngược từ 01/01/2026');
  await page.locator('#dxt-gia-val').fill('1.100.000');
  await page.locator('[data-act="luu-gia"]').click();
  await page.locator('#dx-toast', { hasText: 'Đã lưu giá mới' }).waitFor();
  assert.deepEqual({ ...posts(w, '/api/v7/doixe/gia')[0].body, idempotency_key: 'k' },
    { idempotency_key: 'k', tuyen_id: 1, tu_ngay: '2026-01-01', gia_vnd: '1100000', xac_nhan_ngay_cu: true });
}, { setup: w => { w.gia.hom_nay = '2026-12-05'; }, query: '?man=gia' }));

test('Đổi giá tháng 1 (audit DX-01): mặc định 01/02 năm nay; 28/12 thiếu năm là tháng 12 năm nay, không phải năm trước', () => withPage(async page => {
  await page.locator('[data-act="sua-gia"]').first().click();
  assert.equal(await page.locator('#dxt-gia-tu').inputValue(), '01/02/2027');
  await page.locator('#dxt-gia-tu').fill('28/12');
  assert.match(await page.locator('#dxt-gia-note').innerText(), /^Áp dụng từ 28\/12\/2027\./);
  await page.locator('#dxt-gia-tu').fill('28/12/2026');
  assert.equal(await page.locator('[data-act="luu-gia"]').innerText(), 'Lưu, áp ngược từ 28/12/2026');
}, { setup: w => { w.gia.hom_nay = '2027-01-10'; }, query: '?man=gia' }));

test('Ngưng tuyến (audit DX-07): hỏi trước, nói số chặng mất giá; giữ tên gốc; tuyến đã ngưng có Dùng lại', () => withPage(async (page, w) => {
  await page.locator('[data-act="sua-gia"]').first().click();
  await page.locator('[data-act="hoi-ngung"]').click();
  assert.match(await page.locator('.dxt-hoi').innerText(), /Ngưng dùng tuyến Hàng giả · Tỉnh A → Cảng A\? 2 chặng đang gom theo tuyến này sẽ thành «Chưa có giá»/);
  await page.locator('[data-act="thoi-ngung"]').click();
  assert.equal(await page.locator('.dxt-hoi').count(), 0);
  assert.equal(posts(w, '/api/v7/doixe/tuyen').length, 0, 'bấm Ngưng lần đầu chỉ hỏi');
  await page.locator('[data-act="hoi-ngung"]').click();
  await page.locator('.dxt-hoi [data-act="ngung-tuyen"]').click();
  await page.locator('#dx-toast', { hasText: 'Đã ngưng dùng tuyến' }).waitFor();
  const ngung = posts(w, '/api/v7/doixe/tuyen')[0].body;
  assert.deepEqual([ngung.tuyen_id, ngung.dang_dung, ngung.ten_goc, ngung.ten_goc_truoc],
    [1, false, [{ hang: 'HANG GIA', tinh: 'TINH A' }], ['HANG GIA|TINH A']], 'ngưng dùng giữ tên gốc, kèm bộ tên gốc đang thấy');
  const ds = page.locator('.dxt-ngung-ds');
  assert.match(await ds.innerText(), /Tuyến đã ngưng \(1\)/);
  await ds.locator('summary').click();
  await ds.locator('[data-act="dung-lai-tuyen"]').click();
  await page.locator('#dx-toast', { hasText: 'Đã dùng lại tuyến' }).waitFor();
  assert.equal(posts(w, '/api/v7/doixe/tuyen')[1].body.dang_dung, true);
  assert.equal(await page.locator('.dxt-ngung-ds').count(), 0);
}, { query: '?man=gia' }));

test('Bỏ tên gốc từ màn cũ (audit DX-06): máy khác vừa nhớ tên gốc mới thì máy chủ chặn, tải lại thấy cả hai, không xóa mất', () => withPage(async (page, w) => {
  await page.locator('[data-act="sua-gia"]').first().click();
  w.gia.tuyen[0].ten_goc.push('HANG GIA|TINH C');   // máy khác vừa gắn tuyến + Nhớ
  await page.locator('[data-act="bo-goc"]').first().click();
  await page.locator('.dx-toast.err', { hasText: 'Tên gốc của tuyến vừa đổi ở máy khác' }).waitFor();
  assert.deepEqual(w.gia.tuyen[0].ten_goc, ['HANG GIA|TINH A', 'HANG GIA|TINH C']);
  await page.locator('.dxt-goc-i', { hasText: 'TINH C' }).waitFor();
  assert.equal(await page.locator('.dxt-goc-i').count(), 2, 'màn đã tải lại bộ tên gốc mới, ô đổi giá vẫn mở');
}, { query: '?man=gia' }));

test('Tiền về (audit DX-03): lần cùng ngày cùng số thì báo, nút thành "Vẫn ghi thêm"; số còn phải thu đã cũ thì máy chủ chặn, tải lại', () => withPage(async (page, w) => {
  await page.locator('[data-act="nut-chinh"]').click();
  await page.locator('#dxt-tv-tien').fill('1.000.000');
  assert.equal(await page.locator('#dxt-tv-trung').innerText(), '');
  // Máy khác vừa ghi một lần tiền về 1.000.000 hôm nay.
  w.bk['2026-10-01'].tien_ve.push({ id: 77, ngay: HOM_NAY, so_tien_vnd: '1000000', actor: 'nv2@gia', actor_name: 'nv2', luc: '18/11 09:00', huy: null });
  await page.locator('[data-act="ghi-tv"]').click();
  await page.locator('.dx-toast.err', { hasText: 'Bảng kê vừa đổi ở máy khác' }).waitFor();
  assert.equal(posts(w, '/api/v7/doixe/bang-ke/tien-ve')[0].body.con_vnd, '2680000');
  assert.equal(w.bk['2026-10-01'].tien_ve.length, 1, 'không ghi thêm');
  await page.locator('.dxt-so', { hasText: '1.680.000' }).waitFor();
  await page.locator('[data-act="nut-chinh"]').click();
  await page.locator('#dxt-tv-tien').fill('1.000.000');
  assert.match(await page.locator('#dxt-tv-trung').innerText(), /^Đã có lần tiền về 18\/11 đúng 1\.000\.000 \(nv2 ghi 18\/11 09:00\)/);
  assert.equal(await page.locator('[data-act="ghi-tv"]').innerText(), 'Vẫn ghi thêm lần này');
  await page.locator('#dxt-tv-tien').fill('680.000');
  assert.equal(await page.locator('[data-act="ghi-tv"]').innerText(), 'Ghi tiền về');
}, { setup: w => { w.bk['2026-10-01'].trang_thai = 'da_doi_chieu'; }, query: '?thang=2026-10' }));

test('Container lặp (audit DX-04): Trước khi gửi có mục riêng, dòng có cờ, chi tiết nói ngày chặng kia, khung gửi cảnh báo', () => withPage(async page => {
  assert.match(await page.locator('.dxt-viec').innerText(), /1 chặng có container đã có chặng hàng khác trong 10 ngày/);
  const dong = page.locator('.dxt-dong').first();
  assert.equal(await dong.locator('.dxt-lap').count(), 1);
  await page.locator('.dxt-viec').getByText('1 chặng có container đã có chặng hàng khác trong 10 ngày').click();
  assert.equal(await page.locator('.dxt-dong').count(), 1);
  await page.locator('.dxt-cont', { hasText: 'MAUU2000001' }).click();
  assert.match(await page.locator('.dxt-ct').innerText(), /Container này còn chặng hàng ngày 05\/11 \(lệch tới 10 ngày\)/);
  await page.locator('[data-act="loc"][data-loc="all"]').click();
  await page.locator('[data-act="nut-chinh"]').click();
  assert.match(await page.locator('.dxt-panel').innerText(), /1 chặng có container đã có chặng hàng khác trong 10 ngày: xem có phải một chuyến bị dán hai lần không/);
}, { setup: w => { w.nhap['2026-11-01'][0].cont_lap = ['2026-11-05']; } }));
