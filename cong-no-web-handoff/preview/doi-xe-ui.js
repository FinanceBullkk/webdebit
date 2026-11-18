/* Màn Đội xe đợt 1 (CHI-PHI-XE-01, specs/chi-phi-xe-01.md), bám bản bấm thử người dùng chốt 18/11/2026: màn Đội xe (hai bảng),
 * sổ người (thẻ tiền, ứng, hoàn, bảng chi phí), sổ xe; nhập kiểu Sheet, dán khối từ tab tài xế, sửa tại ô, hoàn theo đợt, hủy có lý
 * do, khóa tháng, Lịch sử. Mọi phép tính tiền ở doi-xe-model.js (ARCH-03); luật ghi do hàm SQL `doixe.*` giữ. Mỗi lệnh ghi có mã
 * yêu cầu: bấm lặp hoặc gửi lại sau mất mạng với cùng nội dung dùng lại mã cũ, máy chủ trả kết quả cũ thay vì ghi lần hai. */
(() => {
  'use strict';
  const M = DoiXeModel;
  const { esc } = CongNoFormat;
  const $ = id => document.getElementById(id);
  const root = $('dx-root'), head = $('dx-head'), layer = $('dx-layer'), toastBox = $('dx-toast');

  const S = {
    view: 'tong', id: null, thang: null, data: null, loadError: '', loading: true, q: '', doiQ: '',
    cach: 'gon', loc: '', drafts: [], moi: null, danCau: '', hoan: null, hop: '', uf: null, huy: null,
    lichSu: null, busy: false, xoaHoi: null, toast: null, giuBao: null, seq: 0,
  };
  const keys = new Map();   // nội dung lệnh → mã yêu cầu, giữ tới khi máy chủ trả lời được

  const moiTrong = () => ({ ngay: '', container: '', loai: 'hang', xe: '', noi_lay: '', noi_ha: '', kho: '', ghi_chu: '', phi: {} });
  S.moi = moiTrong();

  // ---------- Địa chỉ ----------
  function readUrl() {
    const q = new URLSearchParams(location.search);
    const thang = q.get('thang');
    S.thang = thang && /^\d{4}-\d{2}$/.test(thang) ? `${thang}-01` : null;
    if (q.get('nguoi') && /^\d+$/.test(q.get('nguoi'))) { S.view = 'nguoi'; S.id = Number(q.get('nguoi')); }
    else if (q.get('xe') && /^\d+$/.test(q.get('xe'))) { S.view = 'xe'; S.id = Number(q.get('xe')); }
    else { S.view = 'tong'; S.id = null; }
  }
  function urlOf(view, id, thang) {
    const q = new URLSearchParams();
    if (view !== 'tong') q.set(view, String(id));
    if (thang) q.set('thang', thang.slice(0, 7));
    const s = q.toString();
    return location.pathname + (s ? `?${s}` : '');
  }
  function go(view, id, thang = S.thang, push = true) {
    const changed = view !== S.view || id !== S.id;
    if (changed) Object.assign(S, { drafts: [], moi: moiTrong(), danCau: '', hoan: null, loc: '', xoaHoi: null, hop: '', lichSu: null });
    Object.assign(S, { view, id, thang });
    history[push ? 'pushState' : 'replaceState'](null, '', urlOf(view, id, thang));
    load();
  }
  addEventListener('popstate', () => { readUrl(); Object.assign(S, { drafts: [], moi: moiTrong(), hoan: null, hop: '' }); load(); });

  // ---------- Mạng ----------
  async function getJson(url) {
    const r = await fetch(url, { cache: 'no-store' });
    const body = await r.json().catch(() => null);
    if (!r.ok) throw Object.assign(Error(body?.message || `Lỗi ${r.status}`), { code: body?.error, status: r.status });
    return body;
  }
  async function post(path, body) {
    const sig = `${path} ${JSON.stringify(body)}`;
    if (!keys.has(sig)) keys.set(sig, globalThis.crypto?.randomUUID?.() ?? `dx-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    let r;
    try {
      r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idempotency_key: keys.get(sig), ...body }) });
    } catch {
      throw Object.assign(Error('Mất kết nối, chưa rõ đã lưu chưa. Bấm lại: máy chủ không ghi lần hai.'), { code: 'NETWORK' });
    }
    const out = await r.json().catch(() => null);
    if (!r.ok) {
      if (r.status !== 503) keys.delete(sig);
      throw Object.assign(Error(out?.message || `Lỗi ${r.status}`), { code: out?.error, status: r.status });
    }
    keys.delete(sig);
    return out;
  }
  async function load() {
    const seq = ++S.seq;
    S.loading = true;
    if (!S.data) draw();
    const url = S.view === 'tong' ? `/api/v7/doixe${S.thang ? `?thang=${S.thang}` : ''}`
      : `/api/v7/doixe/so?loai=${S.view}&id=${S.id}${S.thang ? `&thang=${S.thang}` : ''}`;
    try {
      const data = await getJson(url);
      if (seq !== S.seq) return;
      Object.assign(S, { data, loadError: '', loading: false });
      if (!S.thang) S.thang = data.thang;
      document.body.dataset.loaded = '1';
    } catch (e) {
      if (seq !== S.seq) return;
      Object.assign(S, { loadError: e.status === 403 ? (e.message || 'Tài khoản này chưa được cấp quyền.') : `Không tải được ${S.view === 'tong' ? 'Đội xe' : 'sổ'}. Kiểm tra mạng rồi bấm Thử lại.`, loading: false });
      if (e.status === 422 || e.status === 404) S.data = null;
      document.body.dataset.loaded = '1';
    }
    draw();
    if (S.hop === 'lichsu') loadLichSu();
  }
  async function loadLichSu() {
    const q = S.view === 'nguoi' ? `?nguoi=${S.id}` : S.view === 'xe' ? `?xe=${S.id}` : '';
    try {
      S.lichSu = (await getJson(`/api/v7/doixe/lich-su${q}`)).events;
    } catch {
      S.lichSu = 'loi';
    }
    if (S.hop === 'lichsu') drawLayer();
  }

  function bao(text, loai = 'ok') {
    if (S.giuBao) { S.giuBao.push([text, loai]); return; }
    S.toast = { text, loai, n: (S.toast?.n ?? 0) + 1 };
    const n = S.toast.n;
    drawToast();
    setTimeout(() => { if (S.toast?.n === n) { S.toast = null; drawToast(); } }, 7000);
  }
  async function ghi(path, body, ok) {
    if (S.busy) return null;
    S.busy = true;
    draw();
    try {
      const out = await post(path, body);
      // Thông báo kết quả chỉ hiện sau khi sổ đọc lại xong: người dùng thấy câu báo cùng lúc với số mới.
      S.giuBao = [];
      if (ok) ok(out);
      await load();
      const giu = S.giuBao;
      S.giuBao = null;
      for (const [text, loai] of giu) bao(text, loai);
      return out;
    } catch (e) {
      S.giuBao = null;
      bao(e.message, 'err');
      if (e.code === 'CHANGED' || e.code === 'DONG_DA_DOI' || e.code === 'CHANG_NOT_FOUND') await load();
      return null;
    } finally {
      S.busy = false;
      draw();
    }
  }

  // ---------- Ngữ cảnh sổ ----------
  const dm = () => S.data.danh_muc;
  const loaiPhi = () => S.data.loai_phi;
  const xeById = id => dm().xe.find(x => x.id === id);
  const nguoiById = id => dm().nguoi.find(n => n.id === id);
  function ngCanh() {
    const d = S.data;
    if (S.view === 'xe') return { loai: 'xe', xe: d.xe.id, nguoiId: null, laSoXe: true, xemTx: true, xemXe: false, nhanChi: 'Đã chi', homNay: d.hom_nay };
    const dl = d.nguoi.vai === 'di_lenh';
    return { loai: dl ? 'di_lenh' : 'tai_xe', xe: d.nguoi.xe_id ?? null, nguoiId: d.nguoi.id, laSoXe: false, xemTx: dl, xemXe: dl,
      nhanChi: dl ? 'Đã chi' : 'Tài xế chi', homNay: d.hom_nay };
  }
  const daLuuKeys = () => new Set((S.data.chang ?? []).map(M.khoaDaLuu));
  const khoa = thang => Boolean(S.data.khoa?.[thang] ?? (thang !== `${S.data.hom_nay.slice(0, 7)}-01`));

  // ---------- Vẽ ----------
  function withFocus(fn) {
    const el = document.activeElement;
    const key = el?.dataset?.f;
    const pos = key && typeof el.selectionStart === 'number' ? [el.selectionStart, el.selectionEnd] : null;
    fn();
    if (key) {
      const again = document.querySelector(`[data-f="${CSS.escape(key)}"]`);
      if (again) { again.focus(); if (pos && typeof again.setSelectionRange === 'function') again.setSelectionRange(...pos); }
    }
  }
  function draw() { withFocus(() => { drawHead(); drawBody(); drawLayer(); }); }

  function drawHead() {
    if (S.view === 'tong') {
      head.innerHTML = `<h1>Đội xe</h1><label class="dx-find"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"></circle><path d="M16 16l4.5 4.5"></path></svg>`
        + `<input id="dx-q" data-f="q" value="${esc(S.q)}" placeholder="Tìm người hoặc biển số" aria-label="Tìm người hoặc biển số" autocomplete="off"></label>`;
      return;
    }
    const d = S.data;
    let ten = '…', phu = '';
    if (d && S.view === 'nguoi' && d.nguoi) {
      ten = d.nguoi.ten;
      phu = d.nguoi.vai === 'tai_xe' ? `Tài xế${d.nguoi.xe_id ? ` · xe ${esc(xeById(d.nguoi.xe_id)?.bien_so ?? '')}` : ''}` : 'Người đi lệnh · trả phí cảng cho nhiều xe';
    } else if (d && S.view === 'xe' && d.xe) {
      ten = d.xe.bien_so;
      const tx = d.xe.tai_xe_id ? nguoiById(d.xe.tai_xe_id)?.ten : null;
      phu = `${d.xe.thue_ngoai ? 'Xe thuê ngoài' : 'Xe công ty'} ${esc(d.xe.nhom)}${tx ? ` · tài xế ${esc(tx)}` : ' · chưa có tài xế'}`;
    }
    head.innerHTML = `<button type="button" class="dx-icon" data-act="ve-tong" aria-label="Về Đội xe" title="Về Đội xe"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"></path></svg></button>`
      + `<span class="dx-crumb">Đội xe /</span><div class="dx-doi"><button type="button" id="dx-doi" data-act="doi" aria-haspopup="listbox" aria-expanded="${S.hop === 'doi'}" title="Đổi người hoặc xe">${esc(ten)}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg></button>${S.hop === 'doi' ? doiBox() : ''}</div>`
      + `<span class="dx-sub">${phu}</span>`;
  }
  function doiBox() {
    const f = M.boDau(S.doiQ.trim());
    const items = dm().nguoi.filter(n => n.dang_dung).map(n => {
      const xe = dm().xe.find(x => x.tai_xe_id === n.id);
      return { loai: 'nguoi', id: n.id, ten: n.ten, phu: n.vai === 'tai_xe' ? `Tài xế${xe ? ` · ${xe.bien_so}` : ''}` : 'Đi lệnh', tim: M.boDau(`${n.ten} ${xe?.bien_so ?? ''} ${M.chuSo(xe?.bien_so)}`) };
    }).concat(dm().xe.filter(x => !x.thue_ngoai && x.dang_dung).map(x => ({ loai: 'xe', id: x.id, ten: x.bien_so,
      phu: `Xe · ${x.tai_xe_id ? nguoiById(x.tai_xe_id)?.ten ?? '' : 'chưa có tài xế'}`, tim: M.boDau(`${x.bien_so} ${M.chuSo(x.bien_so)} ${nguoiById(x.tai_xe_id)?.ten ?? ''}`) })))
      .filter(it => !f || it.tim.includes(f));
    return `<div class="dx-pop"><input id="dx-doi-q" data-f="doiq" value="${esc(S.doiQ)}" placeholder="Gõ tên hoặc biển số" aria-label="Tìm người hoặc xe" autocomplete="off">`
      + `<div role="listbox" aria-label="Người và xe">${items.map(it => `<button type="button" role="option" aria-selected="${it.loai === S.view && it.id === S.id}" data-act="mo" data-loai="${it.loai}" data-id="${it.id}"><b>${esc(it.ten)}</b><span>${esc(it.phu)}</span></button>`).join('')
      || '<p class="dx-empty">Không thấy ai khớp.</p>'}</div></div>`;
  }

  function drawBody() {
    if (S.loading && !S.data) { root.innerHTML = '<p class="dx-loading">Đang tải…</p>'; return; }
    if (S.loadError && !S.data) { root.innerHTML = `<div class="dx-err" role="alert">${esc(S.loadError)} <button type="button" class="dx-btn" data-act="thu-lai">Thử lại</button></div>`; return; }
    const stale = S.loadError ? `<div class="dx-err" role="alert">${esc(S.loadError)} Đang hiện số đọc lần trước. <button type="button" class="dx-btn" data-act="thu-lai">Thử lại</button></div>` : '';
    if (S.view === 'tong') root.innerHTML = stale + tongHtml();
    else root.innerHTML = stale + soHtml();
  }

  // ---------- Màn Đội xe ----------
  function tongHtml() {
    const d = S.data;
    const f = M.boDau(S.q.trim()), fd = M.chuSo(S.q);
    const xeOf = id => d.xe.find(x => x.id === id);
    const nguoi = M.xepNguoi(d.nguoi.filter(n => !f || M.boDau(n.ten).includes(f) || (fd && n.xe_id && M.chuSo(xeOf(n.xe_id)?.bien_so).includes(fd))));
    const tong = M.tongNguoi(nguoi);
    const rows = nguoi.map(n => {
      const v = M.so(n.so_du_vnd);
      const xe = n.xe_id ? xeOf(n.xe_id) : null;
      return `<button type="button" class="dx-row dx-g-nguoi" data-act="mo" data-loai="nguoi" data-id="${n.id}"><span class="dx-ten"><b>${esc(n.ten)}</b><span>${n.vai === 'tai_xe' ? esc(xe?.bien_so ?? '') : 'Đi lệnh'}</span></span>`
        + `<span class="r muted">${n.chua_hoan ? `${n.chua_hoan} dòng` : ''}</span><span class="r num b">${v > 0 ? M.fmt(v) : ''}</span><span class="r num b">${v < 0 ? M.fmt(-v) : ''}</span></button>`;
    }).join('');
    const xeLoc = d.xe.filter(x => !f || (fd && M.chuSo(x.bien_so).includes(fd)) || (x.tai_xe_id && M.boDau(d.nguoi.find(n => n.id === x.tai_xe_id)?.ten).includes(f)));
    const xeRow = x => {
      const tx = x.thue_ngoai ? 'Xe thuê' : x.tai_xe_id ? d.nguoi.find(n => n.id === x.tai_xe_id)?.ten ?? '' : 'Chưa có tài xế';
      const cells = `<b class="num">${esc(x.bien_so)}</b><span class="${x.tai_xe_id ? '' : 'muted'}">${esc(tx)}</span><span class="r num">${x.chang || '—'}</span><span class="r ${x.chua_phi ? 'warn b' : ''}">${x.chua_phi ? `${x.chua_phi} chặng` : ''}</span>`;
      return x.thue_ngoai ? `<div class="dx-row dx-g-xe muted" title="Chi phí xe thuê ngoài làm ở đợt 2">${cells}</div>`
        : `<button type="button" class="dx-row dx-g-xe" data-act="mo" data-loai="xe" data-id="${x.id}">${cells}</button>`;
    };
    const nhom = [['Xe công ty', xeLoc.filter(x => !x.thue_ngoai), ''], ['Xe thuê ngoài', xeLoc.filter(x => x.thue_ngoai), ' · chi phí xe thuê làm ở đợt 2']]
      .filter(([, ds]) => ds.length).map(([ten, ds, ghi]) => `<div class="dx-nhom"><b>${ten}</b><span>${ds.length} xe${ghi}</span></div>${ds.map(xeRow).join('')}`).join('');
    const thangs = M.cacThang(d.thang_co, d.hom_nay, d.thang);
    return `<div class="dx-grid2"><section class="dx-card" aria-labelledby="dx-nguoi-t"><div class="dx-card-h"><h2 id="dx-nguoi-t">Người nhận ứng</h2><span class="muted">${nguoi.length} người</span><span class="muted dx-right">Số dư hôm nay</span></div>`
      + '<div class="dx-th dx-g-nguoi"><span>Người</span><span class="r">Chưa hoàn</span><span class="r">Công ty còn nợ</span><span class="r">Đang giữ tiền ứng</span></div>'
      + (rows || '<p class="dx-empty">Không có người khớp chữ đang tìm.</p>')
      + `<div class="dx-tong dx-g-nguoi"><span>Tổng</span><span class="r muted">${tong.chuaHoan} dòng</span><span class="r num">${M.fmt(tong.no)}</span><span class="r num">${M.fmt(tong.giu)}</span></div></section>`
      + `<section class="dx-card" aria-labelledby="dx-xe-t"><div class="dx-card-h"><h2 id="dx-xe-t">Xe</h2><span class="muted">${xeLoc.length} xe</span><div class="dx-right dx-chips" role="group" aria-label="Đếm chặng theo tháng">`
      + thangs.map(t => `<button type="button" class="dx-chip${t === d.thang ? ' on' : ''}" aria-pressed="${t === d.thang}" data-act="thang" data-thang="${t}">Chặng tháng ${Number(t.slice(5, 7))}</button>`).join('')
      + '</div></div><div class="dx-th dx-g-xe"><span>Biển số</span><span>Tài xế đang chạy</span><span class="r">Chặng</span><span class="r">Chưa có phí</span></div>'
      + (nhom || '<p class="dx-empty">Không có xe khớp chữ đang tìm.</p>') + '</section></div>';
  }

  // ---------- Sổ người / sổ xe ----------
  function soHtml() {
    const d = S.data, ctx = ngCanh();
    const hoanMo = S.view === 'nguoi' && Boolean(S.hoan);
    let html = '';
    if (!hoanMo) {
      html += `<div class="dx-tabs" role="group" aria-label="Tháng">${M.cacThang(d.thang_co, d.hom_nay, d.thang).map(t => `<button type="button" class="dx-tab${t === d.thang ? ' on' : ''}" aria-pressed="${t === d.thang}" data-act="thang" data-thang="${t}">Tháng ${Number(t.slice(5, 7))}${khoa(t) ? '<svg viewBox="0 0 24 24" role="img" aria-label="đã khóa"><rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="M8 11V8a4 4 0 0 1 8 0v3"></path></svg>' : ''}</button>`).join('')}</div>`;
    }
    if (S.view === 'nguoi' && !hoanMo) html += theTienHtml(d);
    if (hoanMo) html += hoanHtml(d);
    if (S.view === 'xe') html += theXeHtml(d);
    return html + bangHtml(d, ctx, hoanMo);
  }

  function theTienHtml(d) {
    const ten = d.nguoi.ten, t = d.the, cuoi = M.cuoiThe(t);
    const item = (x, loai) => {
      const huy = x.huy;
      const ghiChu = huy ? `Đã hủy · ${x.huy.ly_do}` : loai === 'ung' ? (x.ghi_chu ?? '') : `${x.so_dong} dòng${M.chenhDot(x) > 0 ? ` · trừ ứng ${M.fmt(M.chenhDot(x))}` : M.chenhDot(x) < 0 ? ` · chuyển dư ${M.fmt(-M.chenhDot(x))}` : ''}`;
      return `<button type="button" class="dx-item${huy ? ' huy' : ''}" data-act="xem-huy" data-loai="${loai}" data-id="${x.id}" title="${huy ? esc(`Đã hủy ${huy.luc} · ${huy.actor_name ?? huy.actor} · lý do: ${huy.ly_do}`) : 'Bấm để xem hoặc hủy'}"><span class="num">${M.ddmm(x.ngay)}</span><span class="dx-gc">${esc(ghiChu)}</span><span class="num b">${M.fmt(M.so(x.so_tien_vnd))}</span></button>`;
    };
    const coChuaHoan = M.dongChuaHoan(d.chua_hoan, d.nguoi.id, loaiPhi()).length;
    const thangSo = Number(d.thang.slice(5, 7));
    return `<div class="dx-the"><div class="dx-the-so">`
      + `<div><span>Số dư đầu tháng</span><span class="num">${M.fmt(M.so(t.dau_vnd))}</span></div>`
      + `<div><span>+ ${d.nguoi.vai === 'di_lenh' ? 'Đã chi' : 'Tài xế chi'}</span><span class="num">${M.fmt(M.so(t.chi_vnd))}</span></div>`
      + `<div><span>− Công ty đã hoàn</span><span class="num">${M.fmt(M.so(t.hoan_vnd))}</span></div>`
      + `<div><span>− Công ty đã ứng</span><span class="num">${M.fmt(M.so(t.ung_vnd))}</span></div>`
      + `<div class="dx-cuoi"><strong>${esc(M.nhanCuoi(cuoi, ten))}</strong><strong class="num">${M.fmt(Math.abs(cuoi))}</strong></div></div>`
      + `<div class="dx-the-ds"><div class="dx-the-h"><strong>Ứng tháng ${thangSo}</strong><button type="button" class="dx-btn line" data-act="mo-ung">+ Ghi ứng</button></div>`
      + (d.ung.map(u => item(u, 'ung')).join('') || '<p class="dx-empty">Chưa ứng trong tháng.</p>') + '</div>'
      + `<div class="dx-the-ds"><div class="dx-the-h"><strong>Hoàn tháng ${thangSo}</strong><button type="button" class="dx-btn solid" data-act="mo-hoan" ${coChuaHoan ? '' : 'disabled'} title="${coChuaHoan ? `${coChuaHoan} dòng chưa hoàn` : 'Không còn dòng chưa hoàn'}">Hoàn tiền</button></div>`
      + (d.dot.map(x => item(x, 'dot')).join('') || '<p class="dx-empty">Chưa hoàn trong tháng.</p>') + '</div></div>';
  }

  function theXeHtml(d) {
    const t = M.theXe(d.chang, loaiPhi(), dm().nguoi);
    const tx = d.xe.tai_xe_id ? nguoiById(d.xe.tai_xe_id) : null;
    return `<div class="dx-the"><div class="dx-the-so">`
      + `<div><span>Số chặng</span><span class="num">${t.soChang} (${t.hang} hàng · ${t.phu} phụ)</span></div>`
      + `<div><span>Tài xế chi</span><span class="num">${M.fmt(t.tx)}</span></div><div><span>+ Người đi lệnh chi</span><span class="num">${M.fmt(t.dl)}</span></div>`
      + `<div><span>+ Công ty trả (VETC${t.cty ? ', phí khác' : ''})</span><span class="num">${M.fmt(t.vetc + t.cty)}</span></div>`
      + `<div class="dx-cuoi"><strong>Chi phí chặng trong tháng</strong><strong class="num">${M.fmt(t.tong)}</strong></div></div>`
      + `<div class="dx-the-ds muted"><p>Ứng và hoàn tiền tính theo người, không theo xe. Chặng do người đi lệnh trả phí vẫn tính vào chi phí xe.</p>`
      + (tx ? `<button type="button" class="dx-btn line" data-act="mo" data-loai="nguoi" data-id="${tx.id}">Mở sổ ${esc(tx.ten)}</button>` : '') + '</div></div>';
  }

  // Phần của hộp hoàn đổi theo số tiền và ngày gõ: chỉ thay các phần này khi gõ, ô nhập giữ nguyên (bộ chọn ngày không bị đóng).
  function hoanParts(d) {
    const ds = M.dongChuaHoan(d.chua_hoan, d.nguoi.id, loaiPhi());
    const h = S.hoan, tong = M.tongChon(ds, h.chon), nChon = ds.filter(x => h.chon.has(x.dong.id)).length;
    const t = M.docTien(h.tien), tv = t.loi || t.v === null ? null : t.v;
    const duNay = M.so(d.so_du_vnd), ten = d.nguoi.ten;
    let loi = '';
    if (!nChon) loi = 'Chọn ít nhất một dòng.';
    else if (t.loi) loi = `Số tiền: ${t.loi.toLowerCase()}. VND là số nguyên.`;
    else if (tv === null) loi = 'Nhập số tiền thực chuyển.';
    else if (!h.ngay) loi = 'Chọn ngày chuyển.';
    else if (h.ngay > d.hom_nay) loi = 'Ngày chuyển sau hôm nay.';
    const lech = tv === null ? 0 : M.lechHoan(tv, tong);
    return {
      ds, tong, nChon,
      doc: tv !== null ? `= ${M.docSo(tv)}` : '',
      tru: nChon && duNay < tong ? `<button type="button" class="dx-lk" data-act="tru-ung">Trừ tiền ứng đang giữ: chuyển ${M.fmt(M.truUngGiu(duNay))}</button>` : '',
      du: `<div class="muted">Số dư sau khi ghi</div><div class="num"><span class="muted">${esc(M.loiDu(duNay, ten))}</span> → <strong>${tv === null ? '…' : esc(M.loiDu(M.sauKhiGhi(duNay, tv), ten))}</strong></div>`
        + (lech && nChon ? `<div class="warn">${lech > 0 ? `Chuyển nhiều hơn tổng các dòng ${M.fmt(lech)}: phần dư tính như ứng thêm.` : `Chuyển ít hơn tổng các dòng ${M.fmt(-lech)}: phần thiếu trừ vào tiền ứng đang giữ.`}</div>` : ''),
      nut: `${loi ? `<span class="dx-loi" role="alert">${esc(loi)}</span>` : ''}<div><button type="button" class="dx-btn" data-act="bo-hoan">Bỏ</button>`
        + `<button type="button" class="dx-btn solid big" data-act="ghi-hoan" ${loi || S.busy ? 'disabled' : ''}>${S.busy ? 'Đang ghi…' : `Ghi đợt hoàn${tv !== null && !loi ? ` ${M.fmt(tv)}` : ''}`}</button></div>`,
    };
  }
  function hoanHtml(d) {
    const x = hoanParts(d), h = S.hoan;
    return `<div class="dx-hoan" role="region" aria-label="Hoàn tiền theo đợt"><div class="dx-hoan-a"><div class="dx-hoan-t">Hoàn tiền cho ${esc(d.nguoi.ten)}</div>`
      + `<div>Đã chọn <strong>${x.nChon}/${x.ds.length} dòng</strong> · tổng <strong class="num">${M.fmt(x.tong)}</strong></div>`
      + '<div class="dx-links"><button type="button" class="dx-lk" data-act="chon-het">Chọn hết</button><button type="button" class="dx-lk" data-act="bo-het">Bỏ chọn hết</button></div></div>'
      + `<label class="dx-f">Ngày chuyển<input type="date" id="dx-hoan-ngay" data-f="hoan-ngay" value="${esc(h.ngay)}" max="${d.hom_nay}"></label>`
      + `<div class="dx-f"><label for="dx-hoan-tien">Số tiền thực chuyển</label><input id="dx-hoan-tien" data-f="hoan-tien" class="dx-money" value="${esc(h.tien)}" aria-describedby="dx-hoan-doc" autocomplete="off">`
      + `<span id="dx-hoan-doc" class="dx-doc">${x.doc}</span><span id="dx-hoan-tru">${x.tru}</span></div>`
      + `<div class="dx-hoan-du" id="dx-hoan-du">${x.du}</div><div class="dx-hoan-nut" id="dx-hoan-nut">${x.nut}</div></div>`;
  }
  function fillHoan() {
    const x = hoanParts(S.data);
    $('dx-hoan-doc').textContent = x.doc;
    $('dx-hoan-tru').innerHTML = x.tru;
    $('dx-hoan-du').innerHTML = x.du;
    $('dx-hoan-nut').innerHTML = x.nut;
  }

  // ---------- Bảng chi phí ----------
  function cotBang(changs, drafts, ctx, hoanMo) {
    const du = S.cach === 'du';
    const cols = [];
    if (hoanMo) cols.push({ k: 'chk', t: 'Chọn', w: 52 });
    cols.push({ k: 'ngay', t: 'Ngày', w: 66 }, { k: 'cont', t: 'Container', w: 128 });
    if (ctx.xemTx) cols.push({ k: 'tx', t: 'Tài xế', w: 100 });
    if (du || ctx.xemXe) cols.push({ k: 'xe', t: 'Xe', w: 116 });
    cols.push({ k: 'loai', t: 'Loại chặng', w: 136 });
    if (du) cols.push({ k: 'noi_lay', t: 'Nơi lấy', w: 124 }, { k: 'noi_ha', t: 'Nơi hạ', w: 124 }, { k: 'kho', t: 'Kho', w: 110 });
    const wPhi = ctx.xemTx || ctx.xemXe ? 82 : 88;
    let khac = [];
    if (du) {
      for (const p of loaiPhi()) if (!p.cong_ty_tra) cols.push({ k: p.ma, t: p.ten, d: p.ten_day_du ?? '', w: wPhi, tien: true });
    } else {
      const g = M.cotPhiGon(changs.concat(drafts.map(x => ({ dong: [{ phi: x.phi }] }))), loaiPhi(), ctx.xemTx || ctx.xemXe ? 4 : 5);
      for (const p of g.hien) cols.push({ k: p.ma, t: p.ten, d: p.ten_day_du ?? '', w: wPhi, tien: true });
      khac = g.khac;
      if (khac.length) cols.push({ k: 'khac', t: 'Phí khác', d: khac.map(p => p.ten).join(', '), w: wPhi, tien: true });
    }
    for (const p of loaiPhi()) if (p.cong_ty_tra) cols.push({ k: p.ma, t: p.ten, d: 'Cầu đường VETC, công ty trả: không tính vào phần hoàn', w: 84, tien: true, cty: true });
    cols.push({ k: 'chi', t: ctx.nhanChi, d: ctx.laSoXe ? 'Tổng phí người nhận ứng đã trả (không gồm VETC)' : 'Tổng các cột phí người này trả (không gồm VETC)', w: 104, tien: true });
    if (du) cols.push({ k: 'tra', t: 'Người trả', w: 118 }, { k: 'khach', t: 'Chuyến khách', w: 124 }, { k: 'ghi_chu', t: 'Ghi chú', w: 170 });
    cols.push({ k: 'tt', t: 'Tình trạng', w: 124, flex: true });
    if (!hoanMo) cols.push({ k: 'del', t: '', w: 44 });
    return { cols, khac };
  }
  const tpl = cols => cols.map(c => (c.flex ? `minmax(${c.w}px,1fr)` : `${c.w}px`)).join(' ');

  function bangHtml(d, ctx, hoanMo) {
    let changs = d.chang;
    const dem = { chuahoan: 0, chuanoi: 0, chuaphi: 0 };
    const laCH = c => (ctx.laSoXe ? !c.da_bo && c.nguoi_tra_id !== null && c.dong.some(x => x.dot_hoan_id === null && (M.tienDong(x, loaiPhi()) ?? 0) !== 0)
      : M.laChuaHoan(c, ctx.nguoiId, loaiPhi()));
    const laCP = c => !c.da_bo && !M.coPhi(c);
    if (!hoanMo) {
      for (const c of changs) { if (laCH(c)) dem.chuahoan += 1; if (M.chuaNoi(c)) dem.chuanoi += 1; if (laCP(c)) dem.chuaphi += 1; }
      if (S.loc === 'chuahoan') changs = changs.filter(laCH);
      if (S.loc === 'chuanoi') changs = changs.filter(M.chuaNoi);
      if (S.loc === 'chuaphi') changs = changs.filter(laCP);
    }
    const dsHoan = hoanMo ? M.dongChuaHoan(d.chua_hoan, ctx.nguoiId, loaiPhi()) : [];
    const drafts = hoanMo ? [] : S.drafts;
    const { cols, khac } = cotBang(hoanMo ? dsHoan.map(x => x.chang) : changs, drafts, ctx, hoanMo);
    const g = tpl(cols), minW = cols.reduce((s, c) => s + c.w, 0);
    const du = S.cach === 'du';
    const sticky = new Set(du ? ['chk', 'ngay', 'cont'] : []);
    let left = 0;
    const stickyAt = cols.map(c => { if (!sticky.has(c.k)) return null; const at = left; left += c.w; return at; });
    const st = i => (stickyAt[i] !== null ? ` style="left:${stickyAt[i]}px"` : '');
    const cls = (c, i) => `${c.tien ? 'r num' : ''}${stickyAt[i] !== null ? ' dx-stick' : ''}${c.cty ? ' cty' : ''}`;
    const heads = cols.map((c, i) => `<span class="${cls(c, i)}"${st(i)} ${c.d ? `title="${esc(c.d)}"` : ''}>${esc(c.t)}</span>`).join('');
    const rows = [];
    if (hoanMo) {
      let thang = '';
      for (const x of dsHoan) {
        const t = M.thangCua(x.chang.ngay);
        if (t !== thang) {
          thang = t;
          const trongThang = dsHoan.filter(y => M.thangCua(y.chang.ngay) === t);
          rows.push(`<div class="dx-nhom-row">Tháng ${Number(t.slice(5, 7))} · ${trongThang.length} dòng chưa hoàn · ${M.fmt(M.tongTien(trongThang))}</div>`);
        }
        rows.push(dongHoanHtml(x, cols, g, st, cls));
      }
      if (!dsHoan.length) rows.push('<p class="dx-empty">Không còn dòng nào chưa hoàn.</p>');
    } else {
      for (const c of changs) rows.push(...changHtml(c, cols, khac, ctx, g, st, cls));
      rows.push(moiHtml(cols, ctx, g, st, cls));
      for (const x of drafts) rows.push(nhapHtml(x, cols, khac, ctx, g, st, cls));
    }
    const chips = hoanMo ? '' : [['chuahoan', 'Chưa hoàn'], ['chuanoi', 'Chưa nối chuyến khách'], ['chuaphi', 'Chưa có phí']]
      .filter(([k]) => dem[k] > 0 || S.loc === k)
      .map(([k, t]) => `<button type="button" class="dx-chip${S.loc === k ? ' on' : ''}" aria-pressed="${S.loc === k}" data-act="loc" data-loc="${k}">${t} · ${dem[k]}${S.loc === k ? '  ✕' : ''}</button>`).join('');
    const khoaT = khoa(d.thang);
    const nChang = changs.filter(c => !c.da_bo).length;
    const tieuDe = hoanMo ? 'Chọn các dòng sẽ hoàn (mọi tháng)' : `${ctx.laSoXe ? 'Chặng của xe tháng ' : 'Chi phí tháng '}${Number(d.thang.slice(5, 7))} · ${nChang} chặng`;
    let html = `<div class="dx-bang"><div class="dx-bang-h"><strong>${tieuDe}</strong><div class="dx-chips" role="group" aria-label="Lọc dòng">${chips}</div><span class="dx-sp"></span>`;
    if (!hoanMo) {
      html += `<div class="dx-seg" role="group" aria-label="Cách xem bảng"><button type="button" aria-pressed="${!du}" data-act="cach" data-cach="gon">Gọn</button><button type="button" aria-pressed="${du}" data-act="cach" data-cach="du">Đủ cột</button></div>`;
    }
    html += `<button type="button" class="dx-icon" data-act="lich-su" aria-label="Lịch sử" title="Lịch sử sửa, ứng, hoàn"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.3-5.7"></path><path d="M4 4v4h4"></path><path d="M12 8v4l3 2"></path></svg></button>`;
    if (!hoanMo) {
      const nhan = khoaT ? `Tháng ${Number(d.thang.slice(5, 7))} đã khóa · bấm để mở khóa` : `Tháng ${Number(d.thang.slice(5, 7))} đang mở · bấm để khóa`;
      html += `<button type="button" class="dx-icon" data-act="doi-khoa" aria-label="${nhan}" title="${nhan}"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="${khoaT ? 'M8 11V8a4 4 0 0 1 8 0v3' : 'M8 11V8a4 4 0 0 1 7.5-2'}"></path></svg></button>`;
    }
    html += '</div>';
    if (khoaT && !hoanMo) {
      html += `<div class="dx-khoa"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"></rect><path d="M8 11V8a4 4 0 0 1 8 0v3"></path></svg><span>Tháng ${Number(d.thang.slice(5, 7))} đã khóa. Sửa số tiền sẽ thêm dòng điều chỉnh, số cũ giữ nguyên.</span><button type="button" class="dx-btn" data-act="doi-khoa">Mở khóa</button></div>`;
    }
    html += `<div class="dx-scroll"><div class="dx-inner" style="min-width:${minW}px"><div class="dx-hd" style="grid-template-columns:${g}">${heads}</div>${rows.join('')}`;
    if (!hoanMo) html += nhapBarHtml(ctx);
    if (!hoanMo && changs.length) html += tongHtmlRow(changs, cols, ctx, g, st, khac);
    if (hoanMo && dsHoan.length) {
      const tongChon = M.tongChon(dsHoan, S.hoan.chon);
      html += `<div class="dx-tong" style="grid-template-columns:${g}">${cols.map((c, i) => `<span class="${cls(c, i)}${c.k === 'ngay' ? ' nhan' : ''}"${st(i)}>${c.k === 'ngay' ? 'Tổng đang chọn' : c.k === 'chi' ? M.fmt(tongChon) : ''}</span>`).join('')}</div>`;
    }
    return `${html}</div></div></div>`;
  }

  const cellIn = (f, v, opt = {}) => `<input class="dx-in${opt.tien ? ' r num' : ''}${opt.loi ? ' loi' : ''}${opt.cont ? ' mono' : ''}" data-f="${f}" value="${esc(v ?? '')}"${opt.ph ? ` placeholder="${esc(opt.ph)}"` : ''} aria-label="${esc(opt.aria ?? '')}"${opt.title ? ` title="${esc(opt.title)}"` : ''} autocomplete="off"${opt.dis ? ' disabled' : ''}>`;
  const tag = (text, tone, title) => `<span class="dx-tag ${tone}" title="${esc(title ?? text)}">${esc(text)}</span>`;
  const selLoai = (f, v, aria, dis) => `<select class="dx-sel" data-f="${f}" aria-label="${esc(aria)}"${dis ? ' disabled' : ''}>${M.LOAI.map(([k, t]) => `<option value="${k}"${k === v ? ' selected' : ''}>${t}</option>`).join('')}</select>`;
  const selXe = (f, v, aria, loi, dis) => `<select class="dx-sel${loi ? ' loi' : ''}" data-f="${f}" aria-label="${esc(aria)}"${loi ? ` title="${esc(loi)}"` : ''}${dis ? ' disabled' : ''}><option value="">Chọn xe</option>${dm().xe.filter(x => x.dang_dung || x.id === v).map(x => `<option value="${x.id}"${x.id === v ? ' selected' : ''}>${esc(x.bien_so)}</option>`).join('')}</select>`;
  function noiTag(c) {
    if (c.loai !== 'hang' || c.da_bo) return '';
    if (c.chuyen) return `<span class="dx-noi ok" title="${esc(`Đã nối chuyến khách ${c.chuyen.khach} · ${M.ddmm(c.chuyen.ngay)} · ${c.chuyen.tu ?? '?'} → ${c.chuyen.den ?? '?'}`)}">✓</span>`;
    return '<span class="dx-noi chua" title="Chưa nối chuyến khách: không thấy container này trong chuyến khách lệch tới 10 ngày. Kiểm số cont, ngày, hoặc đổi loại chặng.">chưa nối</span>';
  }

  function changHtml(c, cols, khac, ctx, g, st, cls) {
    const khoaT = khoa(M.thangCua(c.ngay));
    const tinh = ctx.laSoXe || c.nguoi_tra_id === ctx.nguoiId;
    const docOnly = c.da_bo;
    const out = [];
    const goc = c.dong.find(x => x.loai === 'goc') ?? c.dong[0];
    const aria = `${M.ddmm(c.ngay)} ${c.container}`;
    const tip = `${c.noi_lay || c.noi_ha ? `${c.noi_lay ?? '?'} → ${c.noi_ha ?? '?'}` : ''}${c.chuyen ? ` · chuyến ${c.chuyen.khach}` : ''}`;
    const dongHtml = (dong, phu) => cols.map((col, i) => {
      const k = col.k, wrap = html => `<span class="${cls(col, i)} dx-c"${st(i)}>${html}</span>`;
      if (k === 'ngay') {
        if (phu) return wrap(`<span class="muted sm" title="${esc(`${dong.loai === 'tru_lai' ? 'Dòng trừ lại' : 'Điều chỉnh'} lúc ${dong.luc} · ${dong.actor_name ?? dong.actor}`)}">↳ ${esc(dong.luc.slice(0, 5))}</span>`);
        return docOnly ? wrap(M.ddmm(c.ngay)) : wrap(cellIn(`luu:${c.id}:ngay`, M.ddmm(c.ngay), { ph: 'dd/mm', aria: `Ngày · ${aria}` }));
      }
      if (k === 'cont') {
        if (phu) return wrap(`<span class="muted sm" title="${dong.dc_phi ? esc(`${M.tenCot(`phi:${dong.dc_phi}`, loaiPhi())}: ${M.fmt(M.so(dong.dc_truoc_vnd)) || '—'} → ${M.fmt(M.so(dong.dc_sau_vnd)) || '—'}`) : 'Bỏ chặng'}">${dong.loai === 'tru_lai' ? 'Bỏ chặng' : 'Đ.chỉnh'} · ${esc(dong.actor_name ?? dong.actor)}</span>`);
        return docOnly ? wrap(`<span class="mono" title="${esc(tip)}">${esc(c.container)}</span>`) : wrap(cellIn(`luu:${c.id}:container`, c.container, { cont: true, aria: `Container · ${aria}`, title: tip }));
      }
      if (k === 'tx') return wrap(phu ? '' : esc(c.tai_xe_id ? M.tenNguoi(c.tai_xe_id, dm().nguoi) : 'Xe thuê'));
      if (k === 'xe') return wrap(phu ? '' : docOnly ? esc(xeById(c.xe_id)?.bien_so ?? '') : selXe(`luu:${c.id}:xe_id`, c.xe_id, `Xe · ${aria}`));
      if (k === 'loai') {
        if (phu) return wrap(esc(M.TEN_LOAI[c.loai]));
        return wrap(`${docOnly ? esc(M.TEN_LOAI[c.loai]) : selLoai(`luu:${c.id}:loai`, c.loai, `Loại chặng · ${aria}`)}${c.sau_khoa ? '<span class="dx-sk" title="Thêm vào tháng đã khóa">sau khóa</span>' : noiTag(c)}`);
      }
      if (k === 'noi_lay' || k === 'noi_ha' || k === 'kho' || k === 'ghi_chu') {
        if (phu) return wrap('');
        return docOnly ? wrap(esc(c[k] ?? '')) : wrap(cellIn(`luu:${c.id}:${k}`, c[k], { aria: `${col.t} · ${aria}` }));
      }
      if (k === 'khac') {
        const s = phu ? M.phiKhac({ dong: [dong] }, khac) : M.phiKhac({ dong: [dong] }, khac);
        if (s.tong === null) return wrap('');
        return wrap(`<button type="button" class="dx-khac" data-act="cach" data-cach="du" title="${esc(`${s.chiTiet} · bấm để xem đủ cột`)}">${phu ? M.fmtDau(s.tong) : M.fmt(s.tong)}</button>`);
      }
      if (col.tien && k !== 'chi') {
        const v = dong.phi[k] === undefined ? null : M.so(dong.phi[k]);
        const xam = col.cty || !tinh ? ' muted' : '';
        if (phu) return wrap(`<span class="sm${xam}">${v === null ? '' : M.fmtDau(v)}</span>`);
        if (docOnly) return wrap(`<span class="${xam}">${M.fmt(v)}</span>`);
        const hl = M.phiHieuLuc(c, k);
        return wrap(cellIn(`luu:${c.id}:phi:${k}`, M.fmt(v), { tien: true, aria: `${col.t} · ${aria}`, title: hl !== v ? `Đang tính ${M.fmt(hl) || '—'} (gồm điều chỉnh)` : '' }));
      }
      if (k === 'chi') {
        const v = M.tienDong(dong, loaiPhi());
        return wrap(`<span class="${tinh ? 'b' : 'muted'}" title="${tinh ? '' : esc(`Không tính vào ${ctx.nhanChi.toLowerCase()}: ${M.tenNguoi(c.nguoi_tra_id, dm().nguoi)} trả`)}">${v === null ? '' : phu ? M.fmtDau(v) : M.fmt(v)}</span>`);
      }
      if (k === 'tra') {
        if (phu) return wrap('');
        const val = c.nguoi_tra_id === null ? 'cong_ty' : String(c.nguoi_tra_id);
        const opts = [];
        if (c.tai_xe_id) opts.push([String(c.tai_xe_id), 'Tài xế']);
        for (const n of dm().nguoi) if (n.vai === 'di_lenh' && n.dang_dung) opts.push([String(n.id), n.ten]);
        if (!opts.some(([v]) => v === val) && val !== 'cong_ty') opts.push([val, M.tenNguoi(c.nguoi_tra_id, dm().nguoi)]);
        opts.push(['cong_ty', 'Công ty']);
        const dis = docOnly || khoaT || M.daHoan(c);
        return wrap(`<select class="dx-sel" data-f="luu:${c.id}:nguoi_tra" aria-label="Người trả · ${esc(aria)}"${dis ? ` disabled title="${khoaT ? 'Tháng đã khóa: không đổi người trả' : 'Dòng đã hoàn: hủy đợt hoàn trước rồi mới đổi người trả'}"` : ''}>${opts.map(([v, t]) => `<option value="${v}"${v === val ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`);
      }
      if (k === 'khach') {
        if (phu || c.loai !== 'hang') return wrap('');
        return wrap(c.chuyen ? `<span title="${esc(`Chuyến ${M.ddmm(c.chuyen.ngay)} · ${c.chuyen.tu ?? '?'} → ${c.chuyen.den ?? '?'}`)}">${esc(c.chuyen.khach)}</span>` : tag('Chưa nối', 'canh', 'Không thấy container này trong chuyến khách lệch tới 10 ngày'));
      }
      if (k === 'tt') return wrap(trangThai(c, dong, phu, tinh, ctx));
      if (k === 'del') {
        if (phu || docOnly) return wrap('');
        if (S.xoaHoi === c.id) return wrap(`<button type="button" class="dx-xoa-hoi" data-act="xoa" data-id="${c.id}" aria-label="Xác nhận xóa chặng ${esc(aria)}" title="${khoaT || M.daHoan(c) ? 'Tháng khóa hoặc dòng đã hoàn: sẽ gạch ngang và thêm dòng trừ lại' : 'Bấm lần nữa để xóa'}">Xóa?</button>`);
        return wrap(`<button type="button" class="dx-del" data-act="xoa-hoi" data-id="${c.id}" aria-label="Xóa chặng ${esc(aria)}" title="Xóa chặng ${esc(aria)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"></path></svg></button>`);
      }
      return wrap('');
    }).join('');
    const rowCls = `dx-r${c.da_bo ? ' bo' : ''}${c.sau_khoa ? ' sk' : ''}`;
    out.push(`<div class="${rowCls}" style="grid-template-columns:${g}" title="${c.sau_khoa ? 'Thêm vào tháng đã khóa' : ''}">${dongHtml(goc, false)}</div>`);
    for (const dong of c.dong) if (dong !== goc) out.push(`<div class="dx-r phu" style="grid-template-columns:${g}">${dongHtml(dong, true)}</div>`);
    return out;
  }

  function trangThai(c, dong, phu, tinh, ctx) {
    if (c.da_bo && !phu) return tag('Đã bỏ', 'xam', 'Chặng đã bỏ bằng dòng trừ lại');
    if (!tinh && !ctx.laSoXe) return tag(`${M.tenNguoi(c.nguoi_tra_id, dm().nguoi)} trả`, 'xam', `Người trả: ${M.tenNguoi(c.nguoi_tra_id, dm().nguoi)}`);
    if (c.nguoi_tra_id === null) return tag('Công ty trả', 'xam');
    if (!phu && !M.coPhi(c)) return tag('Chưa có phí', 'canh', 'Chặng chưa nhập khoản phí nào');
    const v = M.tienDong(dong, loaiPhi());
    if (v === null || v === 0) return tag('—', 'xam', 'Không có khoản người nhận ứng trả');
    if (dong.dot_hoan_id) return tag(`✓ Đã hoàn ${M.ddmm(dong.dot_ngay)}`, 'ok', `Đã hoàn ngày ${M.ddmm(dong.dot_ngay)}${ctx.laSoXe ? ` · ${M.tenNguoi(c.nguoi_tra_id, dm().nguoi)}` : ''}`);
    return tag('Chưa hoàn', 'cho', ctx.laSoXe ? `Chưa hoàn cho ${M.tenNguoi(c.nguoi_tra_id, dm().nguoi)}` : 'Chưa hoàn');
  }

  function dongHoanHtml(x, cols, g, st, cls) {
    const c = x.chang, dong = x.dong, phu = dong.loai !== 'goc';
    const on = S.hoan.chon.has(dong.id);
    const aria = `${M.ddmm(c.ngay)} ${c.container}`;
    return `<div class="dx-r${on ? ' chon' : ''}" style="grid-template-columns:${g}">${cols.map((col, i) => {
      const k = col.k, wrap = html => `<span class="${cls(col, i)} dx-c"${st(i)}>${html}</span>`;
      if (k === 'chk') return wrap(`<input type="checkbox" class="dx-chk" data-f="chk:${dong.id}" data-act="chon" data-id="${dong.id}"${on ? ' checked' : ''} aria-label="Chọn dòng ${esc(aria)}">`);
      if (k === 'ngay') return wrap(phu ? `<span class="muted sm">↳ ${esc(dong.luc.slice(0, 5))}</span>` : M.ddmm(c.ngay));
      if (k === 'cont') return wrap(`<span class="mono">${esc(c.container)}</span>`);
      if (k === 'xe') return wrap(esc(xeById(c.xe_id)?.bien_so ?? ''));
      if (k === 'tx') return wrap(esc(M.tenNguoi(c.tai_xe_id, dm().nguoi)));
      if (k === 'loai') return wrap(esc(M.TEN_LOAI[c.loai]) + (phu ? ` <span class="muted sm">· ${dong.loai === 'tru_lai' ? 'trừ lại' : 'đ.chỉnh'}</span>` : ''));
      if (k === 'khac') return wrap('');
      if (col.tien && k !== 'chi') { const v = dong.phi[k] === undefined ? null : M.so(dong.phi[k]); return wrap(`<span class="${col.cty ? 'muted' : ''}">${v === null ? '' : phu ? M.fmtDau(v) : M.fmt(v)}</span>`); }
      if (k === 'chi') return wrap(`<b>${phu ? M.fmtDau(x.tien) : M.fmt(x.tien)}</b>`);
      if (k === 'tt') return wrap(tag('Chưa hoàn', 'cho'));
      return wrap('');
    }).join('')}</div>`;
  }

  function moiHtml(cols, ctx, g, st, cls) {
    const m = S.moi, co = M.moiCo(m);
    return `<div class="dx-r moi" style="grid-template-columns:${g}">${cols.map((col, i) => {
      const k = col.k, wrap = html => `<span class="${cls(col, i)} dx-c"${st(i)}>${html}</span>`;
      if (k === 'ngay') return wrap(cellIn('moi:0:ngay', m.ngay, { ph: 'dd/mm', aria: 'Ngày · hàng trống' }));
      if (k === 'cont') return wrap(cellIn('moi:0:container', m.container, { ph: 'Gõ hoặc dán', cont: true, aria: 'Container · hàng trống', title: 'Gõ, hoặc chép nhiều dòng từ tab tài xế trên Sheet rồi dán vào đây' }));
      if (k === 'tx') { const x = xeById(Number(m.xe) || ctx.xe); return wrap(`<span class="muted">${esc(x?.tai_xe_id ? M.tenNguoi(x.tai_xe_id, dm().nguoi) : '')}</span>`); }
      if (k === 'xe') return wrap(selXe('moi:0:xe', Number(m.xe) || ctx.xe, 'Xe · hàng trống'));
      if (k === 'loai') return wrap(selLoai('moi:0:loai', m.loai, 'Loại chặng · hàng trống'));
      if (k === 'noi_lay' || k === 'noi_ha' || k === 'kho' || k === 'ghi_chu') return wrap(cellIn(`moi:0:${k}`, m[k], { aria: `${col.t} · hàng trống` }));
      if (col.tien && k !== 'chi' && k !== 'khac') return wrap(cellIn(`moi:0:phi:${k}`, m.phi[k] ?? '', { tien: true, aria: `${col.t} · hàng trống` }));
      if (k === 'tt') return wrap(co ? tag('Enter để thêm', 'xam', 'Bấm Enter để đưa dòng này vào nháp') : '');
      if (k === 'del') return wrap(co ? `<button type="button" class="dx-del" data-act="xoa-moi" aria-label="Xóa chữ đang gõ ở hàng trống" title="Xóa chữ đang gõ ở hàng trống"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg></button>` : '');
      return wrap('');
    }).join('')}</div>`;
  }

  function nhapHtml(x, cols, khac, ctx, g, st, cls) {
    const kq = M.kiemDong(x, daLuuKeys(), S.drafts, loaiPhi(), S.data.hom_nay);
    const lt = M.khoaChang(x);
    const aria = `dòng nháp ${M.ddmm(x.ngay)} ${x.container}`;
    const id = x.id;
    return `<div class="dx-r nhap${kq.loi ? ' coloi' : ''}" style="grid-template-columns:${g}" title="${esc(kq.loi ? `Dòng nháp có lỗi: ${kq.loi}` : 'Dòng nháp, chưa lưu')}" data-k="${esc(lt)}">${cols.map((col, i) => {
      const k = col.k, wrap = html => `<span class="${cls(col, i)} dx-c"${st(i)}>${html}</span>`;
      const loi = kq.loiCot[k === 'cont' ? 'container' : k] ?? '';
      if (k === 'ngay') return wrap(cellIn(`nhap:${id}:ngay`, x.ngay ? M.ddmm(x.ngay) : x.ngayTho ?? '', { ph: 'dd/mm', loi, title: loi, aria: `Ngày · ${aria}` }));
      if (k === 'cont') return wrap(cellIn(`nhap:${id}:container`, x.container, { ph: 'Số cont', cont: true, loi, title: loi, aria: `Container · ${aria}` }));
      if (k === 'tx') return wrap(esc(x.taiXe ? M.tenNguoi(x.taiXe, dm().nguoi) : '—'));
      if (k === 'xe') return wrap(selXe(`nhap:${id}:xe`, x.xe, `Xe · ${aria}`, kq.loiCot.xe));
      if (k === 'loai') return wrap(selLoai(`nhap:${id}:loai`, x.loai, `Loại chặng · ${aria}`));
      if (k === 'noi_lay' || k === 'noi_ha' || k === 'kho' || k === 'ghi_chu') return wrap(cellIn(`nhap:${id}:${k}`, x[k], { aria: `${col.t} · ${aria}` }));
      if (k === 'khac') {
        const loiK = khac.map(p => kq.loiCot[p.ma]).find(Boolean);
        if (loiK) return wrap(tag(loiK, 'loi', 'Ô phí khác có lỗi: xem Đủ cột'));
        const s = M.phiKhacNhap(x, khac);
        return wrap(s === null ? '' : `<button type="button" class="dx-khac" data-act="cach" data-cach="du" title="Bấm để xem đủ cột">${M.fmt(s)}</button>`);
      }
      if (col.tien && k !== 'chi') {
        // Ô lỗi giữ nguyên chữ đã dán (ví dụ 157500.5) để người nhập thấy và làm tròn tại chỗ.
        const v = loi ? x.tho[k] ?? '' : M.fmt(x.phi[k] ?? null);
        return wrap(cellIn(`nhap:${id}:phi:${k}`, v, { tien: true, loi, title: loi, aria: `${col.t} · ${aria}` }));
      }
      if (k === 'chi') return wrap(`<b>${M.fmt(M.chiNhap(x, loaiPhi()))}</b>`);
      if (k === 'tra') return wrap(esc(x.nguoiTra ? (x.nguoiTra === x.taiXe ? 'Tài xế' : M.tenNguoi(x.nguoiTra, dm().nguoi)) : 'Công ty'));
      if (k === 'tt') {
        if (kq.loi) return wrap(tag(kq.loi, 'loi'));
        if (kq.canhBao) return wrap(tag(kq.canhBao, 'canh', `${kq.canhBao}, web tính ${M.fmt(M.chiNhap(x, loaiPhi()) ?? 0)}. Kiểm lại cột nào lệch trước khi lưu.`));
        const sk = khoa(M.thangCua(x.ngay));
        return wrap(tag(sk ? 'Nháp · tháng khóa' : 'Nháp', 'nhap', sk ? `Tháng ${Number(x.ngay.slice(5, 7))} đã khóa: lưu sẽ ghi là thêm sau khóa` : 'Chưa lưu'));
      }
      if (k === 'del') return wrap(`<button type="button" class="dx-del" data-act="bo-nhap" data-id="${id}" aria-label="Bỏ dòng nháp ${esc(aria)}" title="Bỏ dòng nháp"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg></button>`);
      return wrap('');
    }).join('')}</div>`;
  }

  function thuLuu() {
    const ctx = ngCanh();
    const ds = S.drafts.concat(M.moiCo(S.moi) ? [nhapMoi(ctx)] : []);
    const keysSaved = daLuuKeys();
    const ok = [];
    for (const x of ds) if (!M.kiemDong(x, keysSaved, ds, loaiPhi(), S.data.hom_nay).loi) ok.push(x);
    return { ds, ok };
  }
  function nhapBarHtml() {
    const co = M.moiCo(S.moi);
    const n = S.drafts.length + (co ? 1 : 0);
    if (!n) return '';
    const { ds, ok } = thuLuu();
    const nLoi = ds.length - ok.length;
    const cau = `${S.danCau ? `${S.danCau} · ` : ''}${n} dòng nháp chưa lưu${nLoi ? ` · ${nLoi} dòng lỗi (ô đỏ)` : ''}`;
    return `<div class="dx-nhap-bar"><span>${esc(cau)}</span><button type="button" class="dx-btn" data-act="bo-nhap-het">Bỏ nháp</button>`
      + `<button type="button" class="dx-btn solid" data-act="luu" ${S.busy || !ok.length ? 'disabled' : ''}>${S.busy ? 'Đang lưu…' : ok.length ? `Lưu ${ok.length} dòng` : 'Sửa ô đỏ rồi lưu'}</button></div>`;
  }
  function tongHtmlRow(changs, cols, ctx, g, st, khac) {
    const n = changs.filter(c => !c.da_bo).length;
    let daNhan = false;
    return `<div class="dx-tong" style="grid-template-columns:${g}">${cols.map((c, i) => {
      let v = '';
      if (!daNhan && c.k === 'ngay') { v = `Tổng · ${n} chặng`; daNhan = true; }
      else if (c.k === 'chi') v = M.fmt(M.tongChi(changs, loaiPhi(), ctx.nguoiId, ctx.laSoXe));
      else if (c.k === 'khac') {
        let s = null;
        for (const x of changs) { if (!ctx.laSoXe && x.nguoi_tra_id !== ctx.nguoiId) continue; const t = M.phiKhac(x, khac).tong; if (t !== null) s = (s ?? 0) + t; }
        v = M.fmt(s);
      } else if (c.tien) v = M.fmt(M.tongCot(changs, c.k, ctx.nguoiId, ctx.laSoXe));
      return `<span class="${c.tien ? 'r num' : ''}${st(i) ? ' dx-stick' : ''}${c.cty ? ' muted' : ''}${c.k === 'ngay' ? ' nhan' : ''}"${st(i)}>${esc(v)}</span>`;
    }).join('')}</div>`;
  }

  // ---------- Hộp: ứng, hủy, Lịch sử ----------
  function drawLayer() {
    if (!S.data) { layer.innerHTML = ''; return; }
    layer.innerHTML = S.hop === 'ung' ? ungHtml() : S.hop === 'huy' ? huyHtml() : S.hop === 'lichsu' ? lichSuHtml() : '';
  }
  function ungParts() {
    const d = S.data, f = S.uf, ten = d.nguoi.ten, duNay = M.so(d.so_du_vnd);
    const t = M.docTien(f.tien);
    let loi = '';
    if (f.tien && t.loi) loi = `Số tiền: ${t.loi.toLowerCase()}. VND là số nguyên, ví dụ 3.000.000.`;
    else if (f.tien && t.v === 0) loi = 'Số tiền phải lớn hơn 0.';
    else if (f.ngay && f.ngay > d.hom_nay) loi = 'Ngày chuyển sau hôm nay.';
    else if (!f.ngay) loi = 'Chọn ngày chuyển.';
    const ok = !loi && t.v > 0;
    return {
      doc: ok ? `= ${M.docSo(t.v)}` : '',
      du: `<div class="muted sm">Số dư sau khi ghi</div><div class="num"><span class="muted">${esc(M.loiDu(duNay, ten))}</span> → <strong>${ok ? esc(M.loiDu(M.sauKhiGhi(duNay, t.v), ten)) : '…'}</strong></div>`,
      loi: loi ? `<div class="dx-loi" role="alert">${esc(loi)}</div>` : '',
      nut: `<button type="button" class="dx-btn" data-act="dong">Bỏ</button><button type="button" class="dx-btn solid big" data-act="ghi-ung" ${!ok || S.busy ? 'disabled' : ''}>${S.busy ? 'Đang ghi…' : `Ghi ứng${ok ? ` ${M.fmt(t.v)}` : ''}`}</button>`,
    };
  }
  function ungHtml() {
    const d = S.data, f = S.uf, x = ungParts();
    return `<div class="dx-mask" data-act="dong"></div><div role="dialog" aria-modal="true" aria-labelledby="dx-ung-t" class="dx-dlg"><h2 id="dx-ung-t">Ghi ứng cho ${esc(d.nguoi.ten)}</h2>`
      + `<label class="dx-f">Số tiền<input id="dx-ung-tien" data-f="uf-tien" class="dx-money big" value="${esc(f.tien)}" placeholder="Ví dụ 3.000.000" aria-describedby="dx-ung-doc" autocomplete="off"><span id="dx-ung-doc" class="dx-doc">${x.doc}</span></label>`
      + `<div class="dx-row2"><label class="dx-f">Ngày chuyển<input type="date" data-f="uf-ngay" id="dx-ung-ngay" value="${esc(f.ngay)}" max="${d.hom_nay}"></label>`
      + `<label class="dx-f grow">Ghi chú<input data-f="uf-ghichu" id="dx-ung-gc" value="${esc(f.ghichu)}" placeholder="Không bắt buộc" autocomplete="off" maxlength="500"></label></div>`
      + `<div class="dx-du" id="dx-ung-du">${x.du}</div><div id="dx-ung-loi">${x.loi}</div><div class="dx-dlg-nut" id="dx-ung-nut">${x.nut}</div></div>`;
  }
  function fillUng() {
    const x = ungParts();
    $('dx-ung-doc').textContent = x.doc;
    $('dx-ung-du').innerHTML = x.du;
    $('dx-ung-loi').innerHTML = x.loi;
    $('dx-ung-nut').innerHTML = x.nut;
  }
  function huyHtml() {
    const d = S.data, h = S.huy;
    const it = (h.loai === 'ung' ? d.ung : d.dot).find(x => x.id === h.id);
    if (!it) return '';
    const ten = d.nguoi.ten, duNay = M.so(d.so_du_vnd), tien = M.so(it.so_tien_vnd);
    const dong = [['Ngày chuyển', M.ddmmyyyy(it.ngay)]];
    if (h.loai === 'ung') dong.push(['Số tiền', M.fmt(tien)], ['Ghi chú', it.ghi_chu || '—']);
    else {
      const chenh = M.chenhDot(it);
      dong.push(['Các dòng đã hoàn', `${it.so_dong} dòng · ${M.fmt(M.so(it.tong_dong_vnd))}`]);
      if (chenh) dong.push([chenh > 0 ? 'Trừ vào tiền ứng' : 'Chuyển dư (như ứng thêm)', M.fmt(Math.abs(chenh))]);
      dong.push(['Số tiền thực chuyển', M.fmt(tien)]);
    }
    dong.push(['Người ghi', `${it.actor_name ?? it.actor} · ${it.luc}`]);
    if (it.huy) dong.push(['Đã hủy', `${it.huy.actor_name ?? it.huy.actor} · ${it.huy.luc}`], ['Lý do', it.huy.ly_do]);
    const coLyDo = Boolean(h.lydo.trim());
    let html = `<div class="dx-mask" data-act="dong"></div><div role="dialog" aria-modal="true" aria-labelledby="dx-huy-t" class="dx-dlg"><h2 id="dx-huy-t">${h.loai === 'ung' ? 'Lần ứng' : 'Đợt hoàn'} ${M.ddmm(it.ngay)}${it.huy ? ' (đã hủy)' : ''}</h2>`
      + dong.map(([k, v]) => `<div class="dx-kv"><span class="muted">${esc(k)}</span><span class="num">${esc(v)}</span></div>`).join('');
    if (!it.huy) {
      html += `<div class="dx-du"><div class="muted sm">Số dư sau khi hủy</div><div class="num"><span class="muted">${esc(M.loiDu(duNay, ten))}</span> → <strong>${esc(M.loiDu(M.sauKhiHuy(duNay, tien), ten))}</strong></div>`
        + (h.loai === 'dot' ? `<div class="sm">${it.so_dong} dòng sẽ trở lại Chưa hoàn.</div>` : '') + '</div>'
        + `<label class="dx-f">Lý do hủy (bắt buộc)<input data-f="huy-lydo" id="dx-huy-lydo" value="${esc(h.lydo)}" placeholder="Ví dụ: ghi trùng, chuyển nhầm số" autocomplete="off" maxlength="500"></label>`;
    }
    html += `<div class="dx-dlg-nut"><button type="button" class="dx-btn" data-act="dong">Đóng</button>${it.huy ? '' : `<button type="button" class="dx-btn danger big" data-act="huy" ${!coLyDo || S.busy ? 'disabled' : ''}>${S.busy ? 'Đang hủy…' : h.loai === 'ung' ? 'Hủy lần ứng' : 'Hủy đợt hoàn'}</button>`}</div></div>`;
    return html;
  }
  function lichSuHtml() {
    const ten = S.view === 'tong' ? 'cả đội xe' : S.view === 'nguoi' ? S.data?.nguoi?.ten : S.data?.xe?.bien_so;
    let body;
    if (S.lichSu === null) body = '<p class="dx-empty">Đang tải…</p>';
    else if (S.lichSu === 'loi') body = '<p class="dx-err">Không tải được Lịch sử. <button type="button" class="dx-btn" data-act="lich-su">Thử lại</button></p>';
    else if (!S.lichSu.length) body = '<p class="dx-empty">Chưa có thay đổi nào.</p>';
    else {
      body = S.lichSu.map(e => {
        const t = M.moTaSuKien(e, dm(), loaiPhi());
        return `<div class="dx-ev"><div class="muted sm">${esc(e.luc)} · ${esc(e.actor_name ?? e.actor)}</div><div class="b">${esc(t.viec)}</div><div class="sm">${esc(t.chi)}</div>`
          + (t.truoc || t.sau ? `<div class="sm num"><span class="muted">${esc(t.truoc)}</span> → <strong>${esc(t.sau)}</strong></div>` : '')
          + (t.lyDo ? `<div class="sm dx-lydo">Lý do: ${esc(t.lyDo)}</div>` : '') + '</div>';
      }).join('');
    }
    return `<div class="dx-mask nhe" data-act="dong"></div><aside role="dialog" aria-modal="true" aria-labelledby="dx-ls-t" class="dx-ls"><div class="dx-ls-h"><h2 id="dx-ls-t">Lịch sử · ${esc(ten ?? '')}</h2><button type="button" class="dx-icon" data-act="dong" aria-label="Đóng lịch sử"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg></button></div><div class="dx-ls-b">${body}</div></aside>`;
  }
  function drawToast() {
    toastBox.hidden = !S.toast;
    toastBox.className = `dx-toast ${S.toast?.loai ?? ''}`;
    toastBox.innerHTML = S.toast ? `<span>${esc(S.toast.text)}</span><button type="button" data-act="dong-toast" aria-label="Đóng thông báo">✕</button>` : '';
  }

  // ---------- Nhập ----------
  function nhapMoi(ctx) {
    const x = M.nhapTuGo(S.moi, ctx, loaiPhi(), dm().xe, S.data.hom_nay);
    x.id = `n${++S.seq}`;
    if (S.moi.ngay && x.ngayLoi) x.ngayTho = S.moi.ngay;
    return x;
  }
  function themMoi() {
    if (!M.moiCo(S.moi)) return;
    S.drafts.push(nhapMoi(ngCanh()));
    S.moi = moiTrong();
    S.danCau = '';
    draw();
  }
  function onPaste(e) {
    const text = e.clipboardData?.getData('text') ?? '';
    if (!/[\t\n]/.test(text.replace(/\n+$/, ''))) return;
    e.preventDefault();
    const ctx = { ...ngCanh() };
    const kq = M.danKhoi(text, ctx, loaiPhi(), dm().xe, daLuuKeys(), S.drafts);
    for (const x of kq.drafts) x.id = `n${++S.seq}`;
    S.drafts = S.drafts.concat(kq.drafts);
    S.danCau = kq.ghi;
    draw();
    bao(kq.cau, kq.loi ? 'warn' : 'ok');
  }
  async function luuNhap() {
    if (S.busy) return;
    const { ds, ok } = thuLuu();
    if (!ok.length) { bao('Chưa lưu được dòng nào: sửa các ô đỏ trước.', 'err'); return; }
    if (M.moiCo(S.moi)) { S.drafts = ds; S.moi = moiTrong(); }
    const out = await ghi('/api/v7/doixe/chang', { rows: ok.map(M.dongGui) });
    if (!out) return;
    if (out.ok === false) {
      for (const e of out.loi) { const x = ok[e.i]; if (x) x.loiMay = M.loiMay(e); }
      draw();
      bao(`Chưa lưu: ${out.loi.length} lỗi từ máy chủ, xem ô đỏ.`, 'err');
      return;
    }
    const daLuu = new Set(ok);
    const con = S.drafts.filter(x => !daLuu.has(x));
    S.drafts = con;
    S.danCau = '';
    draw();
    bao(`Đã lưu ${out.so_dong} dòng${out.sau_khoa ? ` (${out.sau_khoa} dòng vào tháng đã khóa, ghi là thêm sau khóa)` : ''}${con.length ? ` · còn ${con.length} dòng lỗi để sửa` : ''}.`, con.length ? 'warn' : 'ok');
  }

  function suaNhap(id, col, text) {
    const x = S.drafts.find(y => y.id === id);
    if (!x) return;
    delete x.loiMay;
    if (col === 'ngay') { const r = M.docNgayGo(text, S.data.hom_nay); x.ngay = r.v ?? ''; x.ngayLoi = r.loi ?? ''; x.ngayTho = r.loi ? text : ''; }
    else if (col === 'container') x.container = M.chuanCont(text);
    else if (col.startsWith('phi:')) {
      const ma = col.slice(4), r = M.docTien(text);
      if (r.loi) { x.loiO[ma] = r.loi; x.tho[ma] = text; delete x.phi[ma]; }
      else { delete x.loiO[ma]; delete x.tho[ma]; if (r.v === null) delete x.phi[ma]; else x.phi[ma] = r.v; }
      x.tongSheet = null;
    } else if (col === 'xe') { x.xe = text ? Number(text) : null; x.xeLoi = ''; M.hoanThien(x, ngCanh(), dm().xe); }
    else x[col] = text;
  }

  async function suaLuu(id, col, text) {
    const c = S.data.chang.find(y => y.id === id);
    if (!c) return;
    let truoc, giaTri;
    if (col.startsWith('phi:')) {
      const ma = col.slice(4), r = M.docTien(text);
      if (r.loi) { bao(`${r.loi} ở ô ${M.tenCot(col, loaiPhi())}: VND là số nguyên, làm tròn rồi nhập lại.`, 'err'); draw(); return; }
      const hl = M.phiHieuLuc(c, ma);
      if (r.v === hl) { draw(); return; }
      truoc = hl === null ? null : String(hl);
      giaTri = r.v === null ? null : String(r.v);
    } else if (col === 'ngay') {
      const r = M.docNgayGo(text, S.data.hom_nay);
      if (r.loi || !r.v) { bao('Ngày không đọc được. Gõ ngày/tháng, ví dụ 05/11.', 'err'); draw(); return; }
      if (r.v > S.data.hom_nay) { bao(`Không ghi ngày sau hôm nay (${M.ddmmyyyy(S.data.hom_nay)}).`, 'err'); draw(); return; }
      if (r.v === c.ngay) return;
      truoc = c.ngay; giaTri = r.v;
    } else if (col === 'container') {
      giaTri = M.chuanCont(text);
      if (!giaTri) { bao('Container không được trống.', 'err'); draw(); return; }
      if (giaTri === c.container) { draw(); return; }
      truoc = c.container;
    } else if (col === 'xe_id') {
      if (!text || Number(text) === c.xe_id) { draw(); return; }
      truoc = String(c.xe_id); giaTri = String(text);
    } else if (col === 'nguoi_tra') {
      truoc = c.nguoi_tra_id === null ? 'cong_ty' : String(c.nguoi_tra_id); giaTri = text;
      if (truoc === giaTri) return;
    } else {
      const moi = text.trim() || null;
      if (moi === (c[col] ?? null)) return;
      truoc = c[col] ?? null; giaTri = moi;
    }
    await ghi('/api/v7/doixe/chang/sua', { chang_id: id, cot: col, truoc, gia_tri: giaTri }, out => {
      if (out.cach === 'dieu_chinh') bao(`${out.ly_do_dc === 'thang_khoa' ? `Tháng ${Number(c.ngay.slice(5, 7))} đã khóa` : 'Dòng đã hoàn'}: số cũ giữ nguyên, thêm dòng điều chỉnh ${M.fmtDau(M.so(out.chenh_vnd))}.`, 'warn');
    });
  }

  // ---------- Sự kiện ----------
  function onAct(act, el) {
    const d = S.data;
    switch (act) {
      case 've-tong': go('tong', null); break;
      case 'mo': go(el.dataset.loai, Number(el.dataset.id)); break;
      case 'doi': S.hop = S.hop === 'doi' ? '' : 'doi'; S.doiQ = ''; drawHead(); $('dx-doi-q')?.focus(); break;
      case 'thu-lai': load(); break;
      case 'thang': go(S.view, S.id, el.dataset.thang); break;
      case 'loc': S.loc = S.loc === el.dataset.loc ? '' : el.dataset.loc; draw(); break;
      case 'cach': S.cach = el.dataset.cach; draw(); break;
      case 'lich-su': S.hop = 'lichsu'; S.lichSu = null; drawLayer(); loadLichSu(); layer.querySelector('[data-act="dong"].dx-icon')?.focus(); break;
      case 'dong': {
        const was = S.hop;
        S.hop = ''; S.huy = null; drawLayer(); drawHead();
        if (was === 'ung') document.querySelector('[data-act="mo-ung"]')?.focus();
        break;
      }
      case 'dong-toast': S.toast = null; drawToast(); break;
      case 'mo-ung': S.hop = 'ung'; S.uf = { tien: '', ngay: d.hom_nay, ghichu: '' }; drawLayer(); $('dx-ung-tien')?.focus(); break;
      case 'ghi-ung': {
        const t = M.docTien(S.uf.tien);
        if (t.loi || !(t.v > 0) || !S.uf.ngay || S.uf.ngay > d.hom_nay) return;
        const ten = d.nguoi.ten;
        ghi('/api/v7/doixe/ung', { nguoi_id: d.nguoi.id, ngay: S.uf.ngay, so_tien_vnd: String(t.v), ...(S.uf.ghichu.trim() ? { ghi_chu: S.uf.ghichu.trim() } : {}) },
          out => { S.hop = ''; S.thang = M.thangCua(S.uf.ngay); history.replaceState(null, '', urlOf(S.view, S.id, S.thang)); bao(`Đã ghi ứng ${M.fmt(t.v)} cho ${ten}.${out.lap_lai ? ' (Lần bấm trước đã ghi, không ghi thêm.)' : ''}`); });
        break;
      }
      case 'xem-huy': S.hop = 'huy'; S.huy = { loai: el.dataset.loai, id: Number(el.dataset.id), lydo: '' }; drawLayer(); $('dx-huy-lydo')?.focus(); break;
      case 'huy': {
        const h = S.huy;
        if (!h.lydo.trim()) return;
        ghi(h.loai === 'ung' ? '/api/v7/doixe/ung/huy' : '/api/v7/doixe/hoan/huy', { [h.loai === 'ung' ? 'ung_id' : 'dot_id']: h.id, ly_do: h.lydo.trim() },
          out => { S.hop = ''; S.huy = null; bao(`Đã hủy ${h.loai === 'ung' ? 'lần ứng' : 'đợt hoàn'}. Số dư: ${M.loiDu(M.so(out.so_du_sau_vnd), d.nguoi.ten)}.`, 'warn'); });
        break;
      }
      case 'mo-hoan': {
        const ds = M.dongChuaHoan(d.chua_hoan, d.nguoi.id, loaiPhi());
        if (!ds.length) return;
        const chon = new Set(ds.map(x => x.dong.id));
        S.hoan = { chon, ngay: d.hom_nay, tien: M.fmt(M.tongChon(ds, chon)), sua: false };
        Object.assign(S, { loc: '', drafts: [], moi: moiTrong(), danCau: '', xoaHoi: null });
        draw();
        $('dx-hoan-tien')?.focus();
        break;
      }
      case 'bo-hoan': S.hoan = null; draw(); break;
      case 'chon': case 'chon-het': case 'bo-het': {
        const ds = M.dongChuaHoan(d.chua_hoan, d.nguoi.id, loaiPhi());
        if (act === 'chon') { const id = Number(el.dataset.id); if (S.hoan.chon.has(id)) S.hoan.chon.delete(id); else S.hoan.chon.add(id); }
        else S.hoan.chon = new Set(act === 'chon-het' ? ds.map(x => x.dong.id) : []);
        if (!S.hoan.sua) S.hoan.tien = M.fmt(M.tongChon(ds, S.hoan.chon));
        draw();
        break;
      }
      case 'tru-ung': S.hoan.tien = M.fmt(M.truUngGiu(M.so(d.so_du_vnd))); S.hoan.sua = true; draw(); break;
      case 'ghi-hoan': {
        const ds = M.dongChuaHoan(d.chua_hoan, d.nguoi.id, loaiPhi());
        const ids = ds.filter(x => S.hoan.chon.has(x.dong.id)).map(x => x.dong.id);
        const t = M.docTien(S.hoan.tien);
        if (!ids.length || t.loi || t.v === null || !S.hoan.ngay || S.hoan.ngay > d.hom_nay) return;
        const ngay = S.hoan.ngay;
        ghi('/api/v7/doixe/hoan', { nguoi_id: d.nguoi.id, ngay, so_tien_vnd: String(t.v), dong_ids: ids },
          () => { S.hoan = null; S.thang = M.thangCua(ngay); history.replaceState(null, '', urlOf(S.view, S.id, S.thang)); bao(`Đã ghi đợt hoàn ${M.fmt(t.v)}: ${ids.length} dòng đánh dấu Đã hoàn ${M.ddmm(ngay)}.`); });
        break;
      }
      case 'doi-khoa': {
        const moi = !khoa(d.thang), thang = Number(d.thang.slice(5, 7));
        ghi('/api/v7/doixe/thang/khoa', { thang: d.thang, khoa: moi },
          () => bao(moi ? `Đã khóa tháng ${thang}: từ giờ sửa số tiền sẽ thêm dòng điều chỉnh.` : `Đã mở khóa tháng ${thang}: sửa thẳng, có ghi Lịch sử.`));
        break;
      }
      case 'xoa-hoi': S.xoaHoi = Number(el.dataset.id); draw(); document.querySelector('.dx-xoa-hoi')?.focus(); break;
      case 'xoa': {
        const id = Number(el.dataset.id);
        S.xoaHoi = null;
        ghi('/api/v7/doixe/chang/xoa', { chang_id: id }, out => bao(out.cach === 'bo' ? 'Tháng khóa hoặc dòng đã hoàn: chặng giữ lại, gạch ngang, thêm dòng trừ lại số tiền.' : 'Đã xóa chặng.', out.cach === 'bo' ? 'warn' : 'ok'));
        break;
      }
      case 'xoa-moi': S.moi = moiTrong(); draw(); break;
      case 'bo-nhap': S.drafts = S.drafts.filter(x => x.id !== el.dataset.id); draw(); break;
      case 'bo-nhap-het': Object.assign(S, { drafts: [], moi: moiTrong(), danCau: '' }); draw(); break;
      case 'luu': luuNhap(); break;
      default:
    }
  }

  document.addEventListener('click', e => {
    const el = e.target.closest('[data-act]');
    if (!el || el.disabled || el.type === 'checkbox' && el.dataset.act !== 'chon') return;
    if (el.closest('.dx-pop') === null && S.hop === 'doi' && el.dataset.act !== 'doi') { S.hop = ''; drawHead(); }
    if (S.xoaHoi !== null && !['xoa', 'xoa-hoi'].includes(el.dataset.act)) S.xoaHoi = null;
    onAct(el.dataset.act, el);
  });
  document.addEventListener('mousedown', e => {
    if (S.hop === 'doi' && !e.target.closest('.dx-doi')) { S.hop = ''; drawHead(); }
  });
  document.addEventListener('input', e => {
    const f = e.target.dataset?.f;
    if (!f) return;
    const v = e.target.value;
    if (f === 'q') { S.q = v; drawBody(); return; }
    if (f === 'doiq') { S.doiQ = v; withFocus(drawHead); return; }
    if (f === 'uf-tien' || f === 'uf-ngay' || f === 'uf-ghichu') { S.uf[f.slice(3)] = v; fillUng(); return; }
    if (f === 'huy-lydo') { S.huy.lydo = v; const b = layer.querySelector('[data-act="huy"]'); if (b) b.disabled = !v.trim() || S.busy; return; }
    if (f === 'hoan-tien') { S.hoan.tien = v; S.hoan.sua = true; fillHoan(); return; }
    if (f === 'hoan-ngay') { S.hoan.ngay = v; fillHoan(); return; }
    const [kind, , ...rest] = f.split(':');
    const col = rest.join(':');
    if (kind === 'moi') {
      if (col.startsWith('phi:')) S.moi.phi[col.slice(4)] = v;
      else S.moi[col] = v;
    }
  });
  document.addEventListener('change', e => {
    const f = e.target.dataset?.f;
    if (!f || !f.includes(':') || f.startsWith('chk:')) return;
    const [kind, id, ...rest] = f.split(':');
    const col = rest.join(':');
    const v = e.target.value;
    if (kind === 'moi') { if (e.target.tagName === 'SELECT') { S.moi[col] = v; setTimeout(draw, 0); } return; }
    if (kind === 'nhap') { suaNhap(id, col, v); setTimeout(draw, 0); return; }
    if (kind === 'luu') suaLuu(Number(id), col, v);
  });
  document.addEventListener('focusout', e => {
    const f = e.target.dataset?.f;
    if (f && f.startsWith('hoan-tien')) {
      const x = M.docTien(S.hoan?.tien);
      if (S.hoan && !x.loi && x.v !== null) { S.hoan.tien = M.fmt(x.v); e.target.value = S.hoan.tien; }
    }
    if (f === 'uf-tien') {
      const x = M.docTien(S.uf?.tien);
      if (S.uf && !x.loi && x.v !== null) { S.uf.tien = M.fmt(x.v); e.target.value = S.uf.tien; }
    }
  });
  document.addEventListener('keydown', e => {
    const t = e.target, f = t.dataset?.f ?? '';
    if (e.key === 'Escape') {
      if (S.hop) { onAct('dong', t); e.preventDefault(); return; }
      if (f.startsWith('moi:') || f.startsWith('nhap:') || f.startsWith('luu:')) { t.blur(); draw(); }
      return;
    }
    if (e.key !== 'Enter') return;
    if (f === 'q') { const first = root.querySelector('button[data-act="mo"]'); if (first) { e.preventDefault(); first.click(); } return; }
    if (f === 'doiq') { const first = head.querySelector('.dx-pop button[data-act="mo"]'); if (first) { e.preventDefault(); first.click(); } return; }
    if (f.startsWith('uf-')) { e.preventDefault(); onAct('ghi-ung', t); return; }
    if (f === 'huy-lydo') { e.preventDefault(); onAct('huy', t); return; }
    if (f.startsWith('moi:')) {
      e.preventDefault();
      themMoi();
      // Về ô Ngày của hàng trống để gõ dòng tiếp theo.
      root.querySelector('[data-f="moi:0:ngay"]')?.focus();
      return;
    }
    if (f.startsWith('nhap:') || f.startsWith('luu:')) { e.preventDefault(); t.blur(); }
  });
  document.addEventListener('paste', e => { if (e.target.dataset?.f?.startsWith('moi:')) onPaste(e); });
  addEventListener('beforeunload', e => { if (S.drafts.length || M.moiCo(S.moi)) { e.preventDefault(); e.returnValue = ''; } });

  readUrl();
  draw();
  load();
})();
