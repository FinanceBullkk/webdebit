/* Đội xe đợt 2 (DOI-XE-THU-01, specs/doi-xe-thu-01.md): màn Bảng kê gửi HTH và Bảng giá, bám bản bấm thử người dùng chốt
 * 18/11/2026 (canvas "Đội xe: bảng kê HTH (đợt 2)"). Bố cục theo tháng: ba số Đòi HTH / HTH đã trả / Còn phải thu, nút chính đổi
 * theo bước Gửi bảng kê → Đối chiếu xong → Ghi tiền HTH trả; ô điều chỉnh mở ngay dưới dòng; ô vàng "Trước khi gửi" lọc đúng dòng
 * thiếu; Bảng giá có giá tuyến theo ngày áp dụng và danh mục phát sinh có cột Chi hộ. Số đòi, tổng do máy chủ tính; phép cộng
 * trước → sau ở doi-xe-thu-model.js. Mỗi lệnh ghi có mã yêu cầu: bấm lặp hoặc gửi lại sau mất mạng thì máy chủ trả kết quả cũ. */
(() => {
  'use strict';
  const M = DoiXeModel, T = DoiXeThuModel;
  const { esc } = CongNoFormat;
  const $ = id => document.getElementById(id);
  const root = $('dx-root'), head = $('dx-head'), toastBox = $('dx-toast');

  const S = {
    man: 'bangke', thang: null, data: null, gia: null, loading: true, loadError: '', loc: 'all', mo: null, panel: null,
    f: null, giaSua: null, psSua: null, tuyenMoi: null, busy: false, toast: null, giuBao: null, seq: 0, lichSu: null,
  };
  const keys = new Map();   // nội dung lệnh → mã yêu cầu, giữ tới khi máy chủ trả lời được

  // ---------- Địa chỉ ----------
  function readUrl() {
    const q = new URLSearchParams(location.search);
    S.man = q.get('man') === 'gia' ? 'gia' : 'bangke';
    const t = q.get('thang');
    S.thang = t && /^\d{4}-\d{2}$/.test(t) ? `${t}-01` : null;
  }
  function urlOf(man, thang) {
    const q = new URLSearchParams();
    if (man === 'gia') q.set('man', 'gia');
    else if (thang) q.set('thang', thang.slice(0, 7));
    const s = q.toString();
    return location.pathname + (s ? `?${s}` : '');
  }
  function go(man, thang = S.thang) {
    Object.assign(S, { man, thang, mo: null, panel: null, f: null, loc: 'all', giaSua: null, psSua: null, tuyenMoi: null });
    history.pushState(null, '', urlOf(man, thang));
    load();
  }
  addEventListener('popstate', () => { readUrl(); Object.assign(S, { mo: null, panel: null, f: null }); load(); });

  // ---------- Mạng ----------
  async function getJson(url) {
    const r = await fetch(url, { cache: 'no-store' });
    const body = await r.json().catch(() => null);
    if (!r.ok) throw Object.assign(Error(body?.message || `Lỗi ${r.status}`), { code: body?.error, status: r.status });
    return body;
  }
  async function post(path, body) {
    const sig = `${path} ${JSON.stringify(body)}`;
    if (!keys.has(sig)) keys.set(sig, globalThis.crypto?.randomUUID?.() ?? `dxt-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    let r;
    try {
      r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idempotency_key: keys.get(sig), ...body }) });
    } catch {
      throw Object.assign(Error('Mất kết nối, chưa rõ đã ghi chưa. Bấm lại: máy chủ không ghi lần hai.'), { code: 'NETWORK' });
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
    if (!(S.man === 'gia' ? S.gia : S.data)) draw();
    try {
      if (S.man === 'gia') {
        const gia = await getJson('/api/v7/doixe/bang-gia');
        if (seq !== S.seq) return;
        S.gia = gia;
      } else {
        const data = await getJson(`/api/v7/doixe/bang-ke${S.thang ? `?thang=${S.thang}` : ''}`);
        if (seq !== S.seq) return;
        S.data = data;
        if (!S.thang) S.thang = data.thang;
        if (T.trangThai(data) === 'nhap' && !S.gia) loadGia();
      }
      Object.assign(S, { loadError: '', loading: false });
    } catch (e) {
      if (seq !== S.seq) return;
      Object.assign(S, { loading: false, loadError: e.status === 403 ? (e.message || 'Tài khoản này chưa được cấp quyền.') : 'Không tải được bảng kê. Kiểm tra mạng rồi bấm Thử lại.' });
      if (e.status === 422) { S.data = null; }
    }
    document.body.dataset.loaded = '1';
    draw();
    if (S.panel?.k === 'ls') loadLichSu();
  }
  // Danh sách tuyến cho ô "Gắn tuyến" ở tháng đang gom (đọc ngầm, không chặn màn).
  async function loadGia() {
    try { S.gia = await getJson('/api/v7/doixe/bang-gia'); if (S.mo !== null) draw(); } catch { /* ô gắn tuyến chờ lần tải sau */ }
  }
  async function loadLichSu() {
    try { S.lichSu = (await getJson('/api/v7/doixe/bang-ke/lich-su')).events; } catch { S.lichSu = 'loi'; }
    if (S.panel?.k === 'ls') draw();
  }
  async function taiExcel(thang) {
    const r = await fetch(`/api/v7/doixe/bang-ke.xlsx?thang=${thang}`, { cache: 'no-store' });
    if (!r.ok) {
      const body = await r.json().catch(() => null);
      throw Error(body?.message || `Lỗi ${r.status}`);
    }
    const name = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') ?? '')?.[1] ?? `BangKe_HTH_${thang.slice(0, 7)}.xlsx`;
    const url = URL.createObjectURL(await r.blob());
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    return name;
  }

  function bao(text, loai = 'ok') {
    if (S.giuBao) { S.giuBao.push([text, loai]); return; }
    S.toast = { text, loai, n: (S.toast?.n ?? 0) + 1 };
    const n = S.toast.n;
    drawToast();
    setTimeout(() => { if (S.toast?.n === n) { S.toast = null; drawToast(); } }, 8000);
  }
  async function ghi(path, body, ok) {
    if (S.busy) return null;
    S.busy = true;
    draw();
    try {
      const out = await post(path, body);
      // Câu báo hiện sau khi đọc lại xong: người dùng thấy câu báo cùng lúc với số mới.
      S.giuBao = [];
      if (ok) await ok(out);
      await load();
      const giu = S.giuBao;
      S.giuBao = null;
      for (const [text, loai] of giu) bao(text, loai);
      return out;
    } catch (e) {
      S.giuBao = null;
      bao(e.message, 'err');
      if (['CHANGED', 'BANG_KE_DOI', 'BANG_KE_DA_GUI', 'CHANG_DA_GUI', 'BANG_KE_DA_DOI_CHIEU'].includes(e.code)) await load();
      return null;
    } finally {
      S.busy = false;
      draw();
    }
  }

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
  function draw() { withFocus(() => { drawHead(); drawBody(); }); }
  function drawToast() {
    toastBox.hidden = !S.toast;
    toastBox.className = `dx-toast ${S.toast?.loai ?? ''}`;
    toastBox.innerHTML = S.toast ? `<span>${esc(S.toast.text)}</span><button type="button" data-act="dong-toast" aria-label="Đóng thông báo">✕</button>` : '';
  }
  function drawHead() {
    const tab = (man, text) => `<button type="button" class="dx-man-tab" data-act="man" data-man="${man}" aria-pressed="${S.man === man}">${text}</button>`;
    head.innerHTML = '<h1>Đội xe</h1><nav class="dx-man" aria-label="Phần của đội xe"><a class="dx-man-tab" href="/doi-xe.html">Người và xe</a>'
      + `${tab('bangke', 'Bảng kê gửi HTH')}${tab('gia', 'Bảng giá')}</nav>`;
  }
  function drawBody() {
    const have = S.man === 'gia' ? S.gia : S.data;
    if (S.loading && !have) { root.innerHTML = '<p class="dx-loading">Đang tải…</p>'; return; }
    if (S.loadError && !have) { root.innerHTML = `<div class="dx-err" role="alert">${esc(S.loadError)} <button type="button" class="dx-btn" data-act="thu-lai">Thử lại</button></div>`; return; }
    const stale = S.loadError ? `<div class="dx-err" role="alert">${esc(S.loadError)} Đang hiện số đọc lần trước. <button type="button" class="dx-btn" data-act="thu-lai">Thử lại</button></div>` : '';
    root.innerHTML = stale + (S.man === 'gia' ? giaHtml() : bangKeHtml());
  }

  const svg = path => `<svg viewBox="0 0 24 24" aria-hidden="true">${path}</svg>`;
  const ICON = {
    tai: svg('<path d="M12 4v11M7 10l5 5 5-5M5 20h14"></path>'),
    ls: svg('<circle cx="12" cy="12" r="8.5"></circle><path d="M12 7.5V12l3 2"></path>'),
    pm: svg('<path d="M12 4v8M8 8h8M8 18h8"></path>'),
    sua: svg('<path d="M4 20h4l10-10-4-4L4 16z"></path><path d="M13 7l4 4"></path>'),
  };
  const so = v => (v === null || v === undefined ? null : M.so(v));
  const fmt = v => (v === null || v === undefined ? '' : M.fmt(v));

  // ---------- Bảng kê ----------
  function bangKeHtml() {
    const d = S.data, tt = T.trangThai(d), t = d.tong;
    const m = T.tenThang(d.thang);
    const chips = T.cacThang(d.thang_ds, d.thang).map(x => {
      const on = x.thang === d.thang;
      return `<button type="button" class="dxt-thang${on ? ' on' : ''}" aria-pressed="${on}" data-act="thang" data-thang="${x.thang}"><b>Tháng ${T.thangSo(x.thang)}</b><span class="tt-${x.trang_thai}">${T.CHIP[x.trang_thai]}</span></button>`;
    }).join('');
    const congNo = so(d.cong_no_vnd);
    let html = `<div class="dxt-thang-h" role="group" aria-label="Chọn tháng"><span class="muted">Tháng</span>${chips}`
      + `<span class="dxt-congno" title="Công nợ cước = bảng kê đã gửi + điều chỉnh − tiền HTH đã trả, mọi tháng">HTH còn nợ (các tháng đã gửi) <b class="num">${M.fmt(congNo)}</b></span></div>`;
    const nut = T.NUT[tt] ? `<button type="button" class="dx-btn solid big" data-act="nut-chinh" ${S.busy ? 'disabled' : ''}>${T.NUT[tt]}</button>` : '';
    html += `<section class="dxt-card" aria-labelledby="dxt-tieude"><div class="dxt-card-h"><h2 id="dxt-tieude">Bảng kê tháng ${m} gửi ${esc(d.ben.ten)}</h2>`
      + `<span class="dxt-pill tt-${tt}">${esc(T.nhanTrangThai(d))}</span>${d.bang_ke ? `<span class="muted sm">Số ${esc(d.bang_ke.so)}</span>` : ''}`
      + `<div class="dxt-nut"><button type="button" class="dx-icon big" data-act="excel" aria-label="Tải Excel bảng kê" title="Tải Excel bảng kê${tt === 'nhap' ? ' (bản nháp)' : ''}">${ICON.tai}</button>`
      + `<button type="button" class="dx-icon big" data-act="lich-su" aria-label="Lịch sử bảng kê" title="Lịch sử">${ICON.ls}</button>${nut}</div></div>`
      + `<div class="dxt-so"><div><span>Đòi ${esc(d.ben.ten)}</span><strong class="num" id="dxt-doi">${M.fmt(so(t.doi_vnd))}</strong></div>`
      + `<div><span>${esc(d.ben.ten)} đã trả</span><strong class="num">${M.fmt(so(t.tra_vnd))}</strong></div>`
      + `<div><span>Còn phải thu</span><strong class="num${so(t.con_vnd) === 0 ? ' du' : ''}">${M.fmt(so(t.con_vnd))}</strong></div></div>`
      + `<div class="dxt-cocau num">${esc(T.coCau(t))}</div>`;
    if (d.tien_ve.length) {
      html += `<div class="dxt-tv">${d.tien_ve.map(v => `<div${v.huy ? ' class="huy"' : ''}><span class="num">${v.huy ? 'Đã hủy: ' : 'Tiền về '}${M.ddmm(v.ngay)}: ${M.fmt(so(v.so_tien_vnd))}${v.huy ? ` (${esc(v.huy.ly_do)})` : ''}</span>`
        + `<span class="muted sm">${esc(v.actor_name ?? v.actor)} ${esc(v.luc)}</span>${v.huy ? '' : `<button type="button" class="dx-lk" data-act="mo-huy" data-id="${v.id}">Hủy lần này</button>`}</div>`).join('')}</div>`;
    }
    html += '</section>';
    const viec = tt === 'nhap' ? T.viecTruocGui(d.dong) : [];
    if (viec.length && !S.panel) {
      html += `<section class="dxt-viec" aria-label="Việc còn thiếu trước khi gửi"><strong>Trước khi gửi:</strong>${viec.map(v => `<button type="button" class="dx-lk" data-act="loc" data-loc="${v.loc}">${esc(v.text)}</button>`).join('')}</section>`;
    }
    const ghiChu = { gui: 'Đã gửi HTH nên không sửa thẳng số tiền. HTH thắc mắc dòng nào thì bấm nút ± ở cuối dòng đó để ghi điều chỉnh có lý do.',
      doi: 'HTH đã đồng ý số đòi. Tiền về thì bấm Ghi tiền HTH trả.' }[tt];
    if (ghiChu && !S.panel) html += `<p class="dxt-ghichu">${esc(ghiChu)}</p>`;
    if (S.panel) html += panelHtml(d);
    return html + bangHtml(d, tt);
  }

  function panelHtml(d) {
    const p = S.panel, m = T.tenThang(d.thang);
    const nut = (act, text, cls = 'solid') => `<button type="button" class="dx-btn ${cls} big" data-act="${act}" ${S.busy ? 'disabled' : ''}>${S.busy ? 'Đang ghi…' : text}</button>`;
    const thoi = '<button type="button" class="dx-btn big" data-act="dong-panel">Thôi</button>';
    if (p.k === 'gui') {
      const x = T.guiXem(d);
      return `<section class="dxt-panel" aria-labelledby="dxt-p"><h3 id="dxt-p">Gửi bảng kê tháng ${m} cho ${esc(d.ben.ten)}</h3><div class="num">${esc(x.tom)}</div>`
        + x.canh.map(c => `<div class="dxt-canh">${esc(c)}</div>`).join('')
        + `<div class="dxt-p-nut">${nut('gui', 'Tải Excel và đánh dấu đã gửi')}${thoi}</div></section>`;
    }
    if (p.k === 'doi') {
      const n = d.dong.reduce((s, x) => s + (x.dieu_chinh?.length ?? 0), 0), dc = so(d.tong.dc_vnd);
      return `<section class="dxt-panel" aria-labelledby="dxt-p"><h3 id="dxt-p">Đối chiếu xong tháng ${m}</h3>`
        + `<div class="num">${esc(d.ben.ten)} đồng ý đòi ${M.fmt(so(d.tong.doi_vnd))}${n ? ` sau ${n} điều chỉnh (${M.fmtDau(dc)})` : ', không điều chỉnh dòng nào'}.</div>`
        + '<div class="muted">Sau bước này không ghi điều chỉnh nữa; chỉ còn chờ HTH trả tiền.</div>'
        + `<div class="dxt-p-nut">${nut('doi-chieu', 'Ghi đối chiếu xong')}${thoi}</div></section>`;
    }
    if (p.k === 'tv') {
      const x = T.tvXem(d, p.ngay, p.tien);
      return `<section class="dxt-panel" aria-labelledby="dxt-p"><h3 id="dxt-p">Ghi tiền ${esc(d.ben.ten)} trả · tháng ${m}</h3><div class="dxt-p-o">`
        + `<label class="dx-f">Ngày tiền về<input id="dxt-tv-ngay" data-f="tv-ngay" value="${esc(p.ngay)}" placeholder="ngày/tháng" autocomplete="off" class="w130"></label>`
        + `<label class="dx-f">Số tiền về<input id="dxt-tv-tien" data-f="tv-tien" value="${esc(p.tien)}" class="dx-money" autocomplete="off"></label></div>`
        + `<div class="num" id="dxt-tv-xem">${esc(x.xem)}</div><div id="dxt-tv-canh" class="dxt-canh">${esc(x.canh)}</div>`
        + `<div id="dxt-tv-loi" class="dx-loi" role="alert">${S.panel.daBam ? esc(x.loi) : ''}</div>`
        + `<div class="dxt-p-nut">${nut('ghi-tv', 'Ghi tiền về')}${thoi}</div></section>`;
    }
    if (p.k === 'huy') {
      const v = d.tien_ve.find(x => x.id === p.id);
      if (!v) return '';
      return `<section class="dxt-panel huy" aria-labelledby="dxt-p"><h3 id="dxt-p">Hủy lần tiền về ${M.ddmm(v.ngay)}: ${M.fmt(so(v.so_tien_vnd))}</h3>`
        + `<label class="dx-f">Lý do hủy (bắt buộc)<input id="dxt-huy-lydo" data-f="huy-lydo" value="${esc(p.lydo)}" placeholder="ví dụ: ghi nhầm số tiền" autocomplete="off" maxlength="500"></label>`
        + `<div class="num">${esc(T.huyXem(so(d.tong.con_vnd), v))}</div>`
        + `<div class="dxt-p-nut"><button type="button" class="dx-btn danger big" data-act="huy-tv" ${!p.lydo.trim() || S.busy ? 'disabled' : ''}>${S.busy ? 'Đang hủy…' : 'Hủy lần tiền về này'}</button>${thoi}</div></section>`;
    }
    if (p.k === 'ls') {
      let body;
      if (S.lichSu === null) body = '<p class="dx-empty">Đang tải…</p>';
      else if (S.lichSu === 'loi') body = '<p class="dx-err">Không tải được Lịch sử. <button type="button" class="dx-btn" data-act="lich-su">Thử lại</button></p>';
      else if (!S.lichSu.length) body = '<p class="dx-empty">Chưa có thay đổi nào.</p>';
      else body = S.lichSu.map(e => `<div class="dxt-ev"><span class="num muted">${esc(e.luc)}</span><span>${esc(e.actor_name ?? e.actor)}</span>`
        + `<span class="num">${esc(T.moTa(e))}${e.ly_do ? ` <span class="dx-lydo">(lý do: ${esc(e.ly_do)})</span>` : ''}</span></div>`).join('');
      return `<section class="dxt-panel ls" aria-labelledby="dxt-p"><div class="dxt-ls-h"><h3 id="dxt-p">Lịch sử bảng kê</h3><button type="button" class="dx-lk" data-act="dong-panel">Đóng</button></div>${body}</section>`;
    }
    return '';
  }

  const COLS = '54px 120px 152px minmax(180px,1fr) 108px 88px 104px 116px 100px 48px';
  function bangHtml(d, tt) {
    const loc = T.LOC.some(x => x[0] === S.loc) ? S.loc : 'all';
    const rows = d.dong.filter(T.locFn(loc));
    const chips = T.locChips(d.dong, loc).map(x => `<button type="button" class="dxt-loc${x.k === loc ? ' on' : ''}" aria-pressed="${x.k === loc}" data-act="loc" data-loc="${x.k}">${esc(x.ten)} (${x.n})</button>`).join('');
    const coDc = tt === 'gui';
    let html = `<section class="dxt-bang" aria-labelledby="dxt-bang-t"><div class="dxt-bang-h"><h2 id="dxt-bang-t">Các chặng</h2><div class="dxt-locs" role="group" aria-label="Lọc chặng">${chips}</div>`
      + '<span class="dxt-goi muted">Bấm số container để xem phát sinh, giá bảng</span></div>'
      + `<div class="dxt-scroll"><div class="dxt-inner"><div class="dxt-hd" style="grid-template-columns:${COLS}"><span>Ngày</span><span>Container</span><span>Xe · tài xế</span><span>Tuyến</span>`
      + '<span class="r">Cước</span><span class="r">Đóng ghép</span><span class="r">Phát sinh</span><span class="r">Tổng dòng</span><span class="r">Điều chỉnh</span><span></span></div>';
    for (const x of rows) html += dongHtml(x, d, tt, coDc);
    if (!rows.length) html += `<p class="dx-empty">${d.dong.length ? 'Không có chặng nào khớp bộ lọc.' : `Tháng ${T.tenThang(d.thang)} chưa có chặng nào của xe công ty.`}</p>`;
    // Cột không dòng nào có số thì ô tổng để trống (ô trống không phải 0).
    const sum = k => (rows.some(x => x[k] !== null && x[k] !== undefined) ? M.fmt(rows.reduce((s, x) => s + (so(x[k]) ?? 0), 0)) : '');
    const dcSum = rows.reduce((s, x) => s + (so(x.dc_vnd) ?? 0), 0);
    const tongSum = rows.reduce((s, x) => s + (T.tongDong(x) ?? 0), 0);
    html += `<div class="dxt-tong" style="grid-template-columns:${COLS}"><span></span><span>Tổng</span><span class="muted">${rows.length} chặng</span><span></span>`
      + `<span class="r num">${sum('cuoc_vnd')}</span><span class="r num">${sum('ghep_vnd')}</span><span class="r num">${sum('ps_vnd')}</span>`
      + `<span class="r num">${M.fmt(tongSum)}</span><span class="r num">${dcSum ? M.fmtDau(dcSum) : ''}</span><span></span></div>`;
    return `${html}</div></div></section>`;
  }

  function dongHtml(x, d, tt, coDc) {
    const id = tt === 'nhap' ? x.chang_id : x.id;
    const mo = S.mo === id;
    const nhap = tt === 'nhap';
    const canh = nhap && (x.cuoc_vnd === null || T.khacGia(x) || x.chua_doc > 0 || x.khoan_la > 0);
    const tong = T.tongDong(x), dc = so(x.dc_vnd);
    const ps = so(x.ps_vnd);
    const psTip = (x.ps ?? []).filter(i => !i.loi).map(i => `${i.ten} ${M.fmt(M.so(i.so_tien_vnd))}${i.chi_ho ? ' (chi hộ)' : ''}`).join(' · ');
    const loai = x.loai !== 'hang' ? `<span class="dxt-loai">${esc(T.LOAI_PHU[x.loai] ?? x.loai)}</span>` : '';
    // Chặng phụ đã có nhãn loại: tên tuyến bỏ phần "Chuyển cảng · " lặp lại.
    const tuyenText = T.tenTuyen(x).replace(/^(Chuyển cảng|Trả rỗng) · /, x.loai !== 'hang' ? '' : '$&');
    const cuoc = x.cuoc_vnd === null ? '<span class="dxt-chua">Chưa có giá</span>'
      : `<span class="${T.khacGia(x) ? 'dxt-khac' : ''}" title="${T.khacGia(x) ? `Bảng giá ${M.fmt(so(x.gia_bang_vnd))}` : ''}">${M.fmt(so(x.cuoc_vnd))}</span>`;
    const psCell = x.chua_doc > 0 ? '<span class="dxt-chua" title="Có khoản ghi chú chưa đọc được">Chưa đọc</span>' : ps === null ? '' : `<span title="${esc(psTip)}">${M.fmt(ps)}</span>`;
    const xe = `${esc(x.so_xe ?? '')} <span class="muted sm">${esc(x.tai_xe ?? '')}</span>`;
    let html = `<div class="dxt-dong${canh ? ' canh' : ''}${mo ? ' mo' : ''}${x.chang_con === false ? ' bo' : ''}"><div class="dxt-r" style="grid-template-columns:${COLS}">`
      + `<span class="num">${M.ddmm(x.ngay)}</span>`
      + `<button type="button" class="dxt-cont" data-act="mo-dong" data-id="${id}" aria-expanded="${mo}">${esc(x.container)}</button>`
      + `<span class="dxt-cut" title="${esc(`${x.so_xe ?? ''} ${x.tai_xe ?? ''}`)}">${xe}</span>`
      + `<span class="dxt-cut" title="${esc(T.tenTuyen(x))}">${loai}${esc(tuyenText)}</span>`
      + `<span class="r num">${cuoc}</span><span class="r num">${fmt(so(x.ghep_vnd))}</span><span class="r num">${psCell}</span>`
      + `<strong class="r num">${tong === null ? '' : M.fmt(tong)}</strong><span class="r num b">${dc ? M.fmtDau(dc) : ''}</span>`
      + `<span>${coDc ? `<button type="button" class="dx-icon" data-act="mo-dc" data-id="${id}" aria-label="Ghi điều chỉnh dòng ${esc(x.container)}" title="Ghi điều chỉnh dòng này">${ICON.pm}</button>` : ''}</span></div>`;
    if (mo) html += chiTietHtml(x, d, tt, id);
    return `${html}</div>`;
  }

  function chiTietHtml(x, d, tt, id) {
    let html = `<div class="dxt-ct">${T.chiTiet(x).map(c => `<div class="${c.tone ? `ct-${c.tone}` : ''}">${esc(c.text)}</div>`).join('')}`;
    const f = S.f ?? {};
    if (tt === 'nhap') {
      if (T.khacGia(x)) html += `<button type="button" class="dx-lk" data-act="dung-gia" data-id="${id}">Dùng giá bảng ${M.fmt(so(x.gia_bang_vnd))}</button>`;
      html += `<div class="dxt-o"><label class="dx-f">Giá cước cho chặng này<input data-f="ct-cuoc" id="dxt-cuoc" value="${esc(f.cuoc ?? '')}" placeholder="${x.gia_bang_vnd ? M.fmt(so(x.gia_bang_vnd)) : 'ví dụ 24.000.000'}" class="dx-money" autocomplete="off"></label>`
        + `<button type="button" class="dx-btn solid" data-act="luu-cuoc" data-id="${id}" ${S.busy ? 'disabled' : ''}>Lưu giá</button>`
        + `<span class="muted sm">Chỉ cho chặng này${x.cuoc_tay ? '. Xóa trống rồi Lưu giá là theo bảng giá' : ''}. Thêm tuyến vào bảng giá ở mục Bảng giá.</span></div>`;
      if (f.loiCuoc) html += `<div class="dx-loi" role="alert">${esc(f.loiCuoc)}</div>`;
      const tuyen = (S.gia?.tuyen ?? []).filter(t => t.dang_dung);
      const nho = x.khoa_tuyen && x.khoa_tuyen !== '|';
      html += `<div class="dxt-o"><label class="dx-f">Tuyến tính giá<select data-f="ct-tuyen" id="dxt-tuyen" class="dxt-sel"><option value="">Chưa gắn tuyến</option>`
        + tuyen.map(t => `<option value="${t.id}"${String(t.id) === String(f.tuyen ?? x.tuyen_id ?? '') ? ' selected' : ''}>${esc(t.ten)}</option>`).join('') + '</select></label>'
        + (nho ? `<label class="dxt-chk"><input type="checkbox" data-f="ct-nho" ${f.nho !== false ? 'checked' : ''}> Nhớ cho mọi chặng ghi «${esc(T.tenGoc(x.khoa_tuyen))}»</label>` : '')
        + `<button type="button" class="dx-btn" data-act="gan-tuyen" data-id="${id}" ${S.busy || !S.gia ? 'disabled' : ''}>Gắn tuyến</button></div>`;
      html += `<div class="dxt-o grow"><label class="dx-f grow">Ghi chú của chặng (phát sinh ghi «_ Tên khoản số k», ví dụ «_ Kiểm hoá 1150k _ Neo 2 ngày»)`
        + `<input data-f="ct-ghichu" id="dxt-ghichu" value="${esc(f.ghiChu ?? x.ghi_chu ?? '')}" maxlength="200" autocomplete="off"></label>`
        + `<button type="button" class="dx-btn" data-act="luu-ghichu" data-id="${id}" ${S.busy ? 'disabled' : ''}>Lưu ghi chú</button></div>`;
    }
    if (tt === 'gui' && f.dc) html += dcHtml(x, d, id);
    return `${html}</div>`;
  }

  function dcHtml(x, d, id) {
    const g = S.f.dc;
    const v = T.dcXem(d.tong, x, g.dau, g.tien, g.lydo);
    return `<div class="dxt-dc" role="group" aria-label="Ghi điều chỉnh dòng ${esc(x.container)}"><strong>Ghi điều chỉnh dòng này</strong><div class="dxt-p-o">`
      + `<label class="dx-f">Bớt hay thêm<select data-f="dc-dau" id="dxt-dc-dau" class="dxt-sel"><option value="bot"${g.dau === 'bot' ? ' selected' : ''}>Bớt tiền</option><option value="them"${g.dau === 'them' ? ' selected' : ''}>Thêm tiền</option></select></label>`
      + `<label class="dx-f">Số tiền<input data-f="dc-tien" id="dxt-dc-tien" value="${esc(g.tien)}" placeholder="ví dụ 380.000" class="dx-money" autocomplete="off"></label>`
      + `<label class="dx-f grow">Lý do (bắt buộc)<input data-f="dc-lydo" id="dxt-dc-lydo" value="${esc(g.lydo)}" placeholder="ví dụ: HTH báo hạ sớm tính hai lần" maxlength="500" autocomplete="off"></label></div>`
      + `<div class="num" id="dxt-dc-xem">${esc(v.xem)}</div><div class="dx-loi" role="alert" id="dxt-dc-loi">${g.daBam ? esc(v.loi) : ''}</div>`
      + `<div class="dxt-p-nut"><button type="button" class="dx-btn solid big" data-act="ghi-dc" data-id="${id}" ${S.busy ? 'disabled' : ''}>${S.busy ? 'Đang ghi…' : 'Ghi điều chỉnh'}</button>`
      + '<button type="button" class="dx-btn big" data-act="thoi-dc">Thôi</button></div></div>';
  }
  // Khi gõ ở ô điều chỉnh, tiền về: chỉ thay phần chữ trước → sau, ô nhập giữ nguyên.
  function fillDc() {
    const x = S.data.dong.find(y => y.id === S.mo);
    if (!x || !S.f?.dc) return;
    const v = T.dcXem(S.data.tong, x, S.f.dc.dau, S.f.dc.tien, S.f.dc.lydo);
    $('dxt-dc-xem').textContent = v.xem;
    $('dxt-dc-loi').textContent = S.f.dc.daBam ? v.loi : '';
  }
  function fillTv() {
    const x = T.tvXem(S.data, S.panel.ngay, S.panel.tien);
    $('dxt-tv-xem').textContent = x.xem;
    $('dxt-tv-canh').textContent = x.canh;
    $('dxt-tv-loi').textContent = S.panel.daBam ? x.loi : '';
  }

  // ---------- Bảng giá ----------
  function giaHtml() {
    const g = S.gia, homNay = g.hom_nay;
    const tuyen = g.tuyen.filter(t => t.dang_dung);
    const rows = tuyen.map(t => {
      const { nay, sap } = T.giaHienTai(t, homNay);
      const sua = S.giaSua?.id === t.id;
      let html = `<div class="dxt-g-dong"><div class="dxt-g-r"><strong>${esc(t.loai === 'hang' ? t.hang : T.LOAI_PHU[t.loai])}</strong>`
        + `<span>${esc(t.di)}${t.den ? ` → ${esc(t.den)}` : ''}</span><span class="r num">${nay ? M.fmt(so(nay.gia_vnd)) : '—'}</span>`
        + `<span class="num muted">${nay ? M.ddmmyyyy(nay.tu_ngay) : ''}</span>`
        + `<button type="button" class="dx-icon" data-act="sua-gia" data-id="${t.id}" aria-label="Đổi giá ${esc(t.ten)}" aria-expanded="${sua}" title="Đổi giá">${ICON.sua}</button></div>`;
      if (sap.length) html += `<div class="dxt-g-lich num">${sap.map(v => `Từ ${M.ddmmyyyy(v.tu_ngay)}: ${M.fmt(so(v.gia_vnd))}`).join(' · ')}</div>`;
      if (sua) html += giaSuaHtml(t);
      return `${html}</div>`;
    }).join('');
    const ps = g.phat_sinh.map(p => {
      const sua = S.psSua?.ma === p.ma;
      return `<div class="dxt-g-dong"><div class="dxt-p-r"><strong>${esc(p.ten)}</strong><span class="sm">${esc(T.cachTinh(p))}</span>`
        + `<span class="r num">${esc(T.mucText(p))}</span><span class="${p.chi_ho ? 'dxt-chiho' : ''}">${p.chi_ho ? 'Chi hộ' : ''}</span>`
        + `<button type="button" class="dx-icon" data-act="sua-ps" data-ma="${p.ma}" aria-label="Sửa ${esc(p.ten)}" aria-expanded="${sua}" title="Sửa khoản này">${ICON.sua}</button></div>${sua ? psSuaHtml(p) : ''}</div>`;
    }).join('');
    return '<div class="dxt-gia">'
      + `<section class="dxt-g" aria-labelledby="dxt-g-tuyen"><div class="dxt-g-h"><h2 id="dxt-g-tuyen">Giá cước theo tuyến</h2><span class="muted">đội xe tính ${esc(g.ben.ten)}</span>`
      + `<button type="button" class="dx-btn line" data-act="mo-tuyen-moi">+ Thêm tuyến</button></div>${S.tuyenMoi ? tuyenMoiHtml() : ''}`
      + '<div class="dxt-g-hd dxt-g-r"><span>Hàng</span><span>Đi → đến</span><span class="r">Giá hôm nay</span><span>Từ ngày</span><span></span></div>'
      + (rows || '<p class="dx-empty">Chưa có tuyến nào. Bấm + Thêm tuyến.</p>')
      + '<p class="dxt-g-note">Rút mooc, thả mooc: 70% giá tuyến, làm tròn tới nghìn đồng. Tháng đã gửi HTH giữ giá cũ.</p></section>'
      + `<section class="dxt-g" aria-labelledby="dxt-g-ps"><div class="dxt-g-h"><h2 id="dxt-g-ps">Phát sinh</h2><span class="muted">mỗi khoản một cách tính</span></div>`
      + `<div class="dxt-g-hd dxt-p-r"><span>Khoản</span><span>Cách tính</span><span class="r">Mức</span><span>Chi hộ</span><span></span></div>${ps}`
      + '<p class="dxt-g-note">Chi hộ: đội xe trả giùm rồi đòi HTH đúng số đã trả, không tính vào lãi đội xe. Web đọc phát sinh từ ghi chú kiểu «_ Kiểm hoá 1150k».</p></section></div>';
  }
  function giaSuaHtml(t) {
    const f = S.giaSua;
    const ng = M.docNgayGo(f.tu, S.gia.hom_nay);
    const note = ng.v ? `Tháng đã gửi HTH giữ giá cũ. Chặng tháng đang gom từ ${M.ddmm(ng.v)} đổi theo giá mới: ${T.soChangDoi(t, ng.v)} chặng.` : 'Ghi ngày áp dụng kiểu 01/12.';
    return `<div class="dxt-g-sua"><div class="dxt-p-o"><label class="dx-f">Giá mới<input data-f="gia-val" id="dxt-gia-val" value="${esc(f.val)}" placeholder="ví dụ 12.200.000" class="dx-money" autocomplete="off"></label>`
      + `<label class="dx-f">Áp dụng từ ngày<input data-f="gia-tu" id="dxt-gia-tu" value="${esc(f.tu)}" placeholder="ngày/tháng" class="w130" autocomplete="off"></label></div>`
      + `<div class="sm" id="dxt-gia-note">${esc(note)}</div>${f.loi ? `<div class="dx-loi" role="alert">${esc(f.loi)}</div>` : ''}`
      + `<div class="dxt-p-nut"><button type="button" class="dx-btn solid big" data-act="luu-gia" data-id="${t.id}" ${S.busy ? 'disabled' : ''}>Lưu giá mới</button><button type="button" class="dx-btn big" data-act="thoi-gia">Thôi</button></div>`
      + `<div class="dxt-goc"><span class="muted sm">Tên gốc nhận ra:</span>${t.ten_goc.length ? t.ten_goc.map(k => `<span class="dxt-goc-i">${esc(T.tenGoc(k))}<button type="button" data-act="bo-goc" data-id="${t.id}" data-khoa="${esc(k)}" aria-label="Bỏ tên gốc ${esc(T.tenGoc(k))}" title="Bỏ tên gốc này">✕</button></span>`).join('') : '<span class="muted sm">chưa có (gắn ở bảng kê, tick «Nhớ»)</span>'}`
      + `<button type="button" class="dx-lk dxt-ngung" data-act="ngung-tuyen" data-id="${t.id}">Ngưng dùng tuyến này</button></div></div>`;
  }
  function tuyenMoiHtml() {
    const f = S.tuyenMoi;
    return `<div class="dxt-g-sua moi"><strong>Thêm tuyến</strong><div class="dxt-p-o"><label class="dx-f">Loại<select data-f="tm-loai" id="dxt-tm-loai" class="dxt-sel"><option value="hang"${f.loai === 'hang' ? ' selected' : ''}>Hàng</option><option value="chuyen_cang"${f.loai === 'chuyen_cang' ? ' selected' : ''}>Chuyển cảng</option><option value="tra_rong"${f.loai === 'tra_rong' ? ' selected' : ''}>Trả rỗng</option></select></label>`
      + (f.loai === 'hang' ? `<label class="dx-f">Hàng<input data-f="tm-hang" id="dxt-tm-hang" value="${esc(f.hang)}" placeholder="ví dụ Sầu riêng" autocomplete="off" maxlength="60"></label>` : '')
      + `<label class="dx-f">Đi (tỉnh, vùng)<input data-f="tm-di" id="dxt-tm-di" value="${esc(f.di)}" autocomplete="off" maxlength="100"></label>`
      + `<label class="dx-f">Đến<input data-f="tm-den" id="dxt-tm-den" value="${esc(f.den)}" placeholder="không bắt buộc" autocomplete="off" maxlength="100"></label>`
      + `<label class="dx-f">Giá<input data-f="tm-gia" id="dxt-tm-gia" value="${esc(f.gia)}" class="dx-money" autocomplete="off"></label>`
      + `<label class="dx-f">Từ ngày<input data-f="tm-tu" id="dxt-tm-tu" value="${esc(f.tu)}" placeholder="ngày/tháng/năm" class="w130" autocomplete="off"></label></div>`
      + `${f.loi ? `<div class="dx-loi" role="alert">${esc(f.loi)}</div>` : ''}<div class="dxt-p-nut"><button type="button" class="dx-btn solid big" data-act="them-tuyen" ${S.busy ? 'disabled' : ''}>Thêm tuyến</button><button type="button" class="dx-btn big" data-act="thoi-tuyen-moi">Thôi</button></div></div>`;
  }
  function psSuaHtml(p) {
    const f = S.psSua;
    const opt = (v, t) => `<option value="${v}"${f.cach === v ? ' selected' : ''}>${t}</option>`;
    return `<div class="dxt-g-sua"><div class="dxt-p-o"><label class="dx-f">Cách tính<select data-f="ps-cach" id="dxt-ps-cach" class="dxt-sel">${opt('co_dinh', 'Cố định')}${opt('theo_ngay', 'Theo ngày')}${opt('theo_don_vi', 'Theo số đơn vị')}${opt('nhap_tay', 'Nhập tay')}</select></label>`
      + (f.cach !== 'nhap_tay' ? `<label class="dx-f">${f.cach === 'theo_ngay' ? 'Mức ngày đầu' : f.cach === 'theo_don_vi' ? 'Mức mỗi đơn vị' : 'Mức'}<input data-f="ps-muc" id="dxt-ps-muc" value="${esc(f.muc)}" class="dx-money" autocomplete="off" placeholder="để trống: chưa có mức"></label>` : '')
      + (f.cach === 'theo_ngay' ? `<label class="dx-f">Mỗi ngày thêm<input data-f="ps-them" id="dxt-ps-them" value="${esc(f.them)}" class="dx-money" autocomplete="off"></label>` : '')
      + `<label class="dxt-chk"><input type="checkbox" data-f="ps-chiho" ${f.chiHo ? 'checked' : ''}> Chi hộ</label></div>`
      + `<label class="dx-f grow">Tên đọc trong ghi chú (cách nhau dấu phẩy)<input data-f="ps-ten" id="dxt-ps-ten" value="${esc(f.tenGoc)}" autocomplete="off"></label>`
      + `${f.loi ? `<div class="dx-loi" role="alert">${esc(f.loi)}</div>` : ''}<div class="sm muted">Đổi ở đây chỉ đổi cách đọc ghi chú của tháng đang gom; tháng đã gửi giữ số đã gửi.</div>`
      + `<div class="dxt-p-nut"><button type="button" class="dx-btn solid big" data-act="luu-ps" data-ma="${p.ma}" ${S.busy ? 'disabled' : ''}>Lưu</button><button type="button" class="dx-btn big" data-act="thoi-ps">Thôi</button></div></div>`;
  }

  // ---------- Thao tác ----------
  const dongCua = id => S.data.dong.find(x => (T.trangThai(S.data) === 'nhap' ? x.chang_id : x.id) === id);
  const ddmmHomNay = () => `${S.data.hom_nay.slice(8, 10)}/${S.data.hom_nay.slice(5, 7)}`;
  function nutChinh() {
    const tt = T.trangThai(S.data);
    if (tt === 'nhap') S.panel = { k: 'gui' };
    else if (tt === 'gui') S.panel = { k: 'doi' };
    else if (tt === 'doi') S.panel = { k: 'tv', ngay: ddmmHomNay(), tien: M.fmt(so(S.data.tong.con_vnd)), daBam: false };
    S.mo = null; S.f = null;
    draw();
    (tt === 'doi' ? $('dxt-tv-tien') : root.querySelector('.dxt-panel .dx-btn.solid'))?.focus();
  }
  async function guiBangKe() {
    const d = S.data, thang = d.thang, doi = d.tong.doi_vnd;
    await ghi('/api/v7/doixe/bang-ke/gui', { thang, doi_vnd: doi, so_chang: d.tong.so_chang }, async out => {
      S.panel = null;
      try {
        const name = await taiExcel(thang);
        bao(`Đã đánh dấu gửi bảng kê tháng ${T.tenThang(thang)} (đòi HTH ${M.fmt(so(out.doi_vnd))}). Đã tải file ${name}.`);
      } catch {
        bao(`Đã đánh dấu gửi bảng kê tháng ${T.tenThang(thang)}, nhưng chưa tải được file. Bấm nút tải Excel ở đầu bảng kê.`, 'warn');
      }
    });
  }
  function onAct(act, el) {
    const d = S.data;
    switch (act) {
      case 'man': go(el.dataset.man, el.dataset.man === 'gia' ? S.thang : S.thang); break;
      case 'thu-lai': load(); break;
      case 'dong-toast': S.toast = null; drawToast(); break;
      case 'thang': go('bangke', el.dataset.thang); break;
      case 'loc': S.loc = S.loc === el.dataset.loc && el.dataset.loc !== 'all' ? 'all' : el.dataset.loc; S.mo = null; S.f = null; draw(); break;
      case 'excel': taiExcel(d.thang).then(name => bao(`Đã tải ${name}.`), e => bao(`Chưa tải được file: ${e.message}`, 'err')); break;
      case 'lich-su': S.panel = { k: 'ls' }; S.lichSu = null; draw(); loadLichSu(); break;
      case 'nut-chinh': nutChinh(); break;
      case 'dong-panel': S.panel = null; draw(); root.querySelector('[data-act="nut-chinh"]')?.focus(); break;
      case 'gui': guiBangKe(); break;
      case 'doi-chieu': {
        const m = T.tenThang(d.thang);
        ghi('/api/v7/doixe/bang-ke/doi-chieu', { thang: d.thang, doi_vnd: d.tong.doi_vnd }, () => { S.panel = null; bao(`Đã ghi đối chiếu xong tháng ${m}. Chờ HTH trả tiền.`); });
        break;
      }
      case 'ghi-tv': {
        const p = S.panel, x = T.tvXem(d, p.ngay, p.tien);
        if (x.loi) { p.daBam = true; fillTv(); $('dxt-tv-loi')?.focus?.(); return; }
        const m = T.tenThang(d.thang);
        ghi('/api/v7/doixe/bang-ke/tien-ve', { thang: d.thang, ngay: x.ngay, so_tien_vnd: String(x.v) }, out => {
          S.panel = null;
          const con = so(out.con_sau_vnd);
          bao(con === 0 ? `Đã ghi tiền về. Tháng ${m} thu đủ.` : `Đã ghi tiền về. Tháng ${m} còn thiếu ${M.fmt(con)}.`, con === 0 ? 'ok' : 'warn');
        });
        break;
      }
      case 'mo-huy': S.panel = { k: 'huy', id: Number(el.dataset.id), lydo: '' }; draw(); $('dxt-huy-lydo')?.focus(); break;
      case 'huy-tv': {
        const p = S.panel, v = d.tien_ve.find(x => x.id === p.id);
        if (!p.lydo.trim() || !v) return;
        ghi('/api/v7/doixe/bang-ke/tien-ve/huy', { tien_ve_id: p.id, ly_do: p.lydo.trim() }, () => { S.panel = null; bao(`Đã hủy lần tiền về ${M.ddmm(v.ngay)}.`, 'warn'); });
        break;
      }
      case 'mo-dong': {
        const id = Number(el.dataset.id);
        S.mo = S.mo === id ? null : id;
        S.f = S.mo === null ? null : {};
        if (S.mo !== null && T.trangThai(d) === 'nhap' && !S.gia) loadGia();
        draw();
        break;
      }
      case 'mo-dc': S.mo = Number(el.dataset.id); S.f = { dc: { dau: 'bot', tien: '', lydo: '', daBam: false } }; S.panel = null; draw(); $('dxt-dc-tien')?.focus(); break;
      case 'thoi-dc': S.f = {}; draw(); break;
      case 'ghi-dc': {
        const x = dongCua(Number(el.dataset.id)), g = S.f.dc;
        const v = T.dcXem(d.tong, x, g.dau, g.tien, g.lydo);
        if (v.loi) { g.daBam = true; fillDc(); return; }
        ghi('/api/v7/doixe/bang-ke/dieu-chinh', { dong_id: x.id, so_tien_vnd: String(v.v), ly_do: g.lydo.trim() }, () => {
          S.f = {}; bao(`Đã ghi điều chỉnh ${M.fmtDau(v.v)} cho dòng ${x.container}.`);
        });
        break;
      }
      case 'dung-gia': {
        const x = dongCua(Number(el.dataset.id));
        ghi('/api/v7/doixe/thu/cuoc', { chang_id: x.chang_id, truoc: x.cuoc_vnd, gia_tri: null }, () => bao(`Dòng ${x.container} đã theo bảng giá.`));
        break;
      }
      case 'luu-cuoc': {
        const x = dongCua(Number(el.dataset.id)), r = M.docTien(S.f.cuoc ?? '');
        if (r.loi) { S.f.loiCuoc = `Giá cước: ${r.loi.toLowerCase()}. VND là số nguyên.`; draw(); return; }
        if (r.v === null && !x.cuoc_tay) { S.f.loiCuoc = 'Nhập giá cước.'; draw(); return; }
        ghi('/api/v7/doixe/thu/cuoc', { chang_id: x.chang_id, truoc: x.cuoc_tay ? x.cuoc_vnd : null, gia_tri: r.v === null ? null : String(r.v) },
          out => { S.f = {}; bao(out.khong_doi ? 'Giá bằng giá bảng: chặng vẫn theo bảng giá.' : `Đã lưu giá cước dòng ${x.container}.`); });
        break;
      }
      case 'gan-tuyen': {
        const x = dongCua(Number(el.dataset.id));
        const v = S.f.tuyen ?? (x.tuyen_id === null ? '' : String(x.tuyen_id));
        const nho = Boolean(x.khoa_tuyen && x.khoa_tuyen !== '|') && S.f.nho !== false;
        ghi('/api/v7/doixe/thu/tuyen', { chang_id: x.chang_id, tuyen_id: v ? Number(v) : null, nho },
          out => { S.f = {}; bao(nho ? `Đã gắn tuyến: ${out.so_chang} chặng ghi «${T.tenGoc(x.khoa_tuyen)}» tính theo tuyến này.` : `Đã gắn tuyến cho dòng ${x.container}.`); });
        break;
      }
      case 'luu-ghichu': {
        const x = dongCua(Number(el.dataset.id));
        const moi = (S.f.ghiChu ?? x.ghi_chu ?? '').trim() || null;
        if (moi === (x.ghi_chu ?? null)) return;
        ghi('/api/v7/doixe/chang/sua', { chang_id: x.chang_id, cot: 'ghi_chu', truoc: x.ghi_chu ?? null, gia_tri: moi }, () => { S.f = {}; bao(`Đã lưu ghi chú dòng ${x.container}.`); });
        break;
      }
      // Bảng giá
      case 'sua-gia': {
        const id = Number(el.dataset.id);
        const next = S.gia.hom_nay.slice(5, 7) === '12' ? '01/01' : `01/${String(Number(S.gia.hom_nay.slice(5, 7)) + 1).padStart(2, '0')}`;
        S.giaSua = S.giaSua?.id === id ? null : { id, val: '', tu: next, loi: '' };
        draw();
        $('dxt-gia-val')?.focus();
        break;
      }
      case 'thoi-gia': S.giaSua = null; draw(); break;
      case 'luu-gia': {
        const f = S.giaSua, r = M.docTien(f.val), ng = M.docNgayGo(f.tu, S.gia.hom_nay);
        if (r.loi || !r.v) { f.loi = r.loi ? `Giá: ${r.loi.toLowerCase()}.` : 'Nhập giá mới.'; draw(); return; }
        if (ng.loi || !ng.v) { f.loi = 'Ghi ngày áp dụng kiểu 01/12.'; draw(); return; }
        const t = S.gia.tuyen.find(x => x.id === f.id);
        ghi('/api/v7/doixe/gia', { tuyen_id: f.id, tu_ngay: ng.v, gia_vnd: String(r.v) },
          out => { S.giaSua = null; bao(`Đã lưu giá mới cho ${t.ten}: ${M.fmt(r.v)} từ ${M.ddmmyyyy(ng.v)}. ${out.so_chang} chặng tháng đang gom đổi theo.`); });
        break;
      }
      case 'bo-goc': case 'ngung-tuyen': {
        const t = S.gia.tuyen.find(x => x.id === Number(el.dataset.id));
        const goc = act === 'bo-goc' ? t.ten_goc.filter(k => k !== el.dataset.khoa) : [];
        const split = k => { const [hang, tinh] = k.split('|'); return { hang: hang || null, tinh: tinh || null }; };
        ghi('/api/v7/doixe/tuyen', { tuyen_id: t.id, loai: t.loai, hang: t.hang, di: t.di, den: t.den, ten_goc: goc.map(split),
          ...(act === 'ngung-tuyen' ? { dang_dung: false } : {}) },
          () => { S.giaSua = null; bao(act === 'bo-goc' ? 'Đã bỏ tên gốc.' : `Đã ngưng dùng tuyến ${t.ten}.`, 'warn'); });
        break;
      }
      case 'mo-tuyen-moi': S.tuyenMoi = { loai: 'hang', hang: '', di: '', den: '', gia: '', tu: `01/01/${S.gia.hom_nay.slice(0, 4)}`, loi: '' }; draw(); $('dxt-tm-hang')?.focus(); break;
      case 'thoi-tuyen-moi': S.tuyenMoi = null; draw(); break;
      case 'them-tuyen': {
        const f = S.tuyenMoi, r = M.docTien(f.gia), ng = M.docNgayGo(f.tu, S.gia.hom_nay);
        if (f.loai === 'hang' && !f.hang.trim()) { f.loi = 'Nhập tên hàng.'; draw(); return; }
        if (!f.di.trim()) { f.loi = 'Nhập nơi đi (tỉnh, vùng).'; draw(); return; }
        if (r.loi || !r.v) { f.loi = r.loi ? `Giá: ${r.loi.toLowerCase()}.` : 'Nhập giá.'; draw(); return; }
        if (ng.loi || !ng.v) { f.loi = 'Ghi ngày áp dụng kiểu 01/01/2026.'; draw(); return; }
        ghi('/api/v7/doixe/tuyen', { tuyen_id: null, loai: f.loai, hang: f.loai === 'hang' ? f.hang.trim() : null, di: f.di.trim(), den: f.den.trim() || null,
          ten_goc: [], gia_vnd: String(r.v), tu_ngay: ng.v }, () => { S.tuyenMoi = null; bao('Đã thêm tuyến.'); });
        break;
      }
      case 'sua-ps': {
        const p = S.gia.phat_sinh.find(x => x.ma === el.dataset.ma);
        S.psSua = S.psSua?.ma === p.ma ? null : { ma: p.ma, cach: p.cach, muc: p.muc_vnd ? M.fmt(so(p.muc_vnd)) : '', them: p.muc_them_vnd ? M.fmt(so(p.muc_them_vnd)) : '',
          chiHo: p.chi_ho, tenGoc: p.ten_goc.join(', '), loi: '' };
        draw();
        break;
      }
      case 'thoi-ps': S.psSua = null; draw(); break;
      case 'luu-ps': {
        const p = S.gia.phat_sinh.find(x => x.ma === el.dataset.ma), x = T.psGui(p, S.psSua);
        if (x.loi) { S.psSua.loi = x.loi; draw(); return; }
        ghi('/api/v7/doixe/phat-sinh', x.body, () => { S.psSua = null; bao(`Đã lưu khoản ${p.ten}.`); });
        break;
      }
      default:
    }
  }

  document.addEventListener('click', e => {
    const el = e.target.closest('[data-act]');
    if (!el || el.disabled) return;
    onAct(el.dataset.act, el);
  });
  document.addEventListener('input', e => {
    const f = e.target.dataset?.f;
    if (!f) return;
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    if (f === 'tv-ngay' || f === 'tv-tien') { S.panel[f.slice(3)] = v; fillTv(); return; }
    if (f === 'huy-lydo') { S.panel.lydo = v; const b = root.querySelector('[data-act="huy-tv"]'); if (b) b.disabled = !v.trim() || S.busy; return; }
    if (f === 'dc-tien' || f === 'dc-lydo') { S.f.dc[f.slice(3)] = v; fillDc(); return; }
    if (f === 'ct-cuoc') { S.f.cuoc = v; S.f.loiCuoc = ''; return; }
    if (f === 'ct-ghichu') { S.f.ghiChu = v; return; }
    if (f === 'gia-val' || f === 'gia-tu') {
      S.giaSua[f === 'gia-val' ? 'val' : 'tu'] = v; S.giaSua.loi = '';
      const t = S.gia.tuyen.find(x => x.id === S.giaSua.id), ng = M.docNgayGo(S.giaSua.tu, S.gia.hom_nay);
      $('dxt-gia-note').textContent = ng.v ? `Tháng đã gửi HTH giữ giá cũ. Chặng tháng đang gom từ ${M.ddmm(ng.v)} đổi theo giá mới: ${T.soChangDoi(t, ng.v)} chặng.` : 'Ghi ngày áp dụng kiểu 01/12.';
      return;
    }
    if (f.startsWith('tm-') && f !== 'tm-loai') { S.tuyenMoi[f.slice(3)] = v; return; }
    if (f === 'ps-muc' || f === 'ps-them' || f === 'ps-ten') { S.psSua[{ 'ps-muc': 'muc', 'ps-them': 'them', 'ps-ten': 'tenGoc' }[f]] = v; return; }
    if (f === 'ps-chiho') { S.psSua.chiHo = v; return; }
    if (f === 'ct-nho') { S.f.nho = v; }
  });
  document.addEventListener('change', e => {
    const f = e.target.dataset?.f;
    if (f === 'dc-dau') { S.f.dc.dau = e.target.value; fillDc(); }
    if (f === 'ct-tuyen') S.f.tuyen = e.target.value;
    if (f === 'tm-loai') { S.tuyenMoi.loai = e.target.value; draw(); }
    if (f === 'ps-cach') { S.psSua.cach = e.target.value; draw(); }
  });
  document.addEventListener('keydown', e => {
    const f = e.target.dataset?.f ?? '';
    if (e.key === 'Escape') {
      if (S.panel) { onAct('dong-panel', e.target); e.preventDefault(); }
      else if (S.f?.dc) { onAct('thoi-dc', e.target); e.preventDefault(); }
      return;
    }
    if (e.key !== 'Enter') return;
    const act = { 'tv-ngay': 'ghi-tv', 'tv-tien': 'ghi-tv', 'huy-lydo': 'huy-tv', 'dc-tien': 'ghi-dc', 'dc-lydo': 'ghi-dc', 'ct-cuoc': 'luu-cuoc',
      'ct-ghichu': 'luu-ghichu', 'gia-val': 'luu-gia', 'gia-tu': 'luu-gia', 'ps-muc': 'luu-ps', 'ps-them': 'luu-ps', 'ps-ten': 'luu-ps' }[f];
    if (!act) return;
    e.preventDefault();
    const btn = root.querySelector(`[data-act="${act}"]`);
    if (btn && !btn.disabled) btn.click();
  });
  document.addEventListener('focusout', e => {
    const f = e.target.dataset?.f;
    const money = { 'tv-tien': () => S.panel, 'dc-tien': () => S.f?.dc };
    if (money[f]) {
      const o = money[f](), k = f === 'tv-tien' ? 'tien' : 'tien', x = M.docTien(o?.[k]);
      if (o && !x.loi && x.v !== null) { o[k] = M.fmt(x.v); e.target.value = o[k]; }
    }
  });

  readUrl();
  draw();
  load();
})();
