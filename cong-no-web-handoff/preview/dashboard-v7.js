(() => {
  'use strict';
  const F = CongNoFormat;
  const M = DashboardModel;
  const root = document.querySelector('#dashboard');
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const ledgerHref = id => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}`;
  // Số rút gọn, rê chuột thấy số đồng chính xác.
  const amount = value => `<span class="money" title="${esc(F.full(value))}">${esc(F.short(value))}</span>`;
  const positive = value => String(value).replace(/^-/, '');
  const fold = value => String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[đĐ]/g, 'd').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const transportText = mode => ({ CANG: 'cảng', 'CẢNG': 'cảng', BO: 'bộ', 'BỘ': 'bộ' })[mode] ?? (mode ? String(mode).toLowerCase() : '');
  const commodityText = (commodity, mode) => commodity ? `${commodity}${transportText(mode) ? ` · ${transportText(mode)}` : ''}` : 'Chưa phân loại';
  const customerLabel = row => row.label ?? `${row.display_name ?? row.name}${row.commodity ? ` · ${commodityText(row.commodity, row.transport_mode)}` : ''}`;
  const customerLabels = customers => {
    const counts = new Map();
    for (const row of customers) counts.set(customerLabel(row), (counts.get(customerLabel(row)) ?? 0) + 1);
    return new Map(customers.map(row => [String(row.id), counts.get(customerLabel(row)) > 1 ? `${customerLabel(row)} · sổ ${row.id}` : customerLabel(row)]));
  };
  // Tên ngắn cho danh sách: tên Sheet; trùng tên thì thêm mặt hàng, vẫn trùng thì thêm số sổ.
  const shortLabels = customers => {
    const base = row => row.display_name ?? row.name;
    const withCommodity = row => `${base(row)} · ${commodityText(row.commodity, row.transport_mode)}`;
    return new Map(customers.map(row => {
      if (customers.filter(item => base(item) === base(row)).length < 2) return [String(row.id), base(row)];
      if (customers.filter(item => withCommodity(item) === withCommodity(row)).length < 2) return [String(row.id), withCommodity(row)];
      return [String(row.id), `${withCommodity(row)} · sổ ${row.id}`];
    }));
  };
  // Đoạn chiếm dưới 7% tổng là đoạn hẹp: không ghi số trong thanh, không nhãn dưới thanh, liệt kê một dòng riêng.
  const NARROW = 7;
  const SORTS = { tong: 'total', 'chua-tra': 'pay', 'di-hang': 'trip' };
  let loading = false;
  // Nút "Làm mới" đọc Sheet ngay (specs/v7-sheet-refresh.md); server chưa bật thì giữ chữ "Cập nhật …".
  let sheetRefresh = null;
  let searchReady = false;
  let currentCustomers = [];
  // tier: nhóm hạn trả đang lọc (0–4); cls: {dim:'mx', key} ô ma trận đang lọc; com: mặt hàng đang lọc; sort: cột xếp.
  const state = { tier: null, cls: null, com: null, sort: 'overdue', data: null, debt: null, rows: null, ready: false,
    tiers: [], mx: null, coms: [], names: new Map() };
  const markUpdated = () => { const node = document.querySelector('#updated-at'); if (node) node.textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`; sheetRefresh?.paint(); };
  const nameOf = id => state.names.get(String(id)) ?? state.rows?.find(row => row.id === id)?.name ?? `Sổ ${id}`;
  const cellOf = cls => (cls?.dim === 'mx' ? state.mx?.cells.find(item => item.key === cls.key) ?? null : null);
  const comOf = key => state.coms.find(item => item.key === key) ?? null;
  const filtered = () => state.tier != null || state.cls != null || state.com != null;

  // 1. Nợ theo hạn trả: số headline, ngoặc trong hạn | quá hạn, một thanh lớn 5 đoạn có số trong đoạn, nhãn thẳng hàng dưới đoạn.
  function dueCard(data, debt) {
    const total = data.receivable.total_vnd;
    const head = `<div class="card-head"><h2 id="h-due">Còn phải thu <b class="big-money" title="${esc(F.full(total))}">${esc(F.short(total))}</b><small>${data.receivable.customers} khách đang nợ</small></h2>
      <span class="aside hint" title="Nợ tháng M đến hạn cuối tháng M+1, chung cho mọi sổ">hạn trả: cuối tháng sau ⓘ</span></div>`;
    if (!debt) return `<section class="card due" id="due-card" aria-labelledby="h-due">${head}<p class="empty">Chưa tải được phần quá hạn. Bấm Làm mới để thử lại.</p></section>`;
    const whole = debt.receivable_vnd;
    const values = M.TIERS.map(tier => debt.due_tiers.find(item => item.tier === tier)?.receivable_vnd ?? '0');
    if (F.toBig(whole) <= 0n) return `<section class="card due" id="due-card" aria-labelledby="h-due">${head}<p class="empty">Chưa có khách đang nợ.</p></section>`;
    const inTerm = F.sum(values.slice(0, 2));
    const wide = values.map(value => F.barWidth(value, whole) >= NARROW);
    const brk = `<div class="brk"><div class="in" style="flex:${F.barWidth(inTerm, whole)}">Trong hạn <b>${esc(F.short(inTerm))}</b></div>
      <div class="late" style="flex:${F.barWidth(debt.summary.overdue_vnd, whole)}">Quá hạn <b>${esc(F.short(debt.summary.overdue_vnd))}</b> · ${esc(F.percent(debt.summary.overdue_vnd, whole))} · ${debt.summary.overdue_customers} khách</div></div>`;
    const bar = `<div class="age-bar" role="img" aria-label="${esc(state.tiers.map((tier, i) => `${tier.label} ${F.short(values[i])}`).join(', '))}">${values.map((value, i) => F.toBig(value) > 0n
      ? `<span class="t${i}" data-tier="${i}" data-tip="tier:${i}" style="flex:${F.barWidth(value, whole)};background:var(--due-${i})">${wide[i] ? esc(F.short(value)) : ''}</span>` : '').join('')}</div>`;
    const labels = `<div class="lab">${values.map((value, i) => (F.toBig(value) > 0n ? (wide[i]
      ? `<button type="button" data-tier="${i}" data-tip="tier:${i}" aria-pressed="false" style="flex:${F.barWidth(value, whole)}"><b>${esc(state.tiers[i].label.replace(/^Quá hạn /, '').replace(/^./, c => c.toUpperCase()))}</b>${esc(state.tiers[i].span)}</button>`
      : `<span style="flex:${F.barWidth(value, whole)}"></span>`) : '')).join('')}</div>`;
    const narrow = values.map((value, i) => (F.toBig(value) > 0n && !wide[i]
      ? `<button type="button" data-tier="${i}" data-tip="tier:${i}" aria-pressed="false"><i style="background:var(--due-${i})"></i>${esc(state.tiers[i].short)} <b>${esc(F.short(value))}</b> (${esc(state.tiers[i].span)})</button>` : '')).filter(Boolean);
    return `<section class="card due" id="due-card" aria-labelledby="h-due">${head}${brk}${bar}<div class="age-legend">${labels}${narrow.length ? `<p class="tiny">Đoạn hẹp: ${narrow.join(' · ')}</p>` : ''}</div></section>`;
  }

  // 2. Thu tháng này: thước đo đã thu / phát sinh, vạch "hôm nay" trong tháng; chú thích chuyến thiếu giá và khách dư.
  function monthCard(data, debt) {
    const missing = data.todo.missing_price.reduce((count, item) => count + item.count, 0);
    const notes = [missing ? `Chưa tính ${missing} chuyến thiếu đơn giá` : '',
      data.credit.customers ? `${data.credit.customers} khách đang dư ${F.short(positive(data.credit.total_vnd))}, tính riêng` : ''].filter(Boolean);
    const foot = notes.length ? `<p class="hero-foot">${esc(notes.join(' · '))}</p>` : '';
    const p = M.monthProgress(debt?.as_of ?? data.as_of, debt?.this_month);
    const head = `<div class="card-head"><h2 id="h-month">Thu tháng ${p.month}</h2><span class="aside">đã thu / phát sinh</span></div>`;
    if (!debt) return `<section class="card month" aria-labelledby="h-month">${head}<p class="empty">Chưa tải được số thu tháng này.</p>${foot}</section>`;
    const meter = `<div class="meter" role="img" aria-label="Đã thu ${esc(F.short(p.received))} trên phát sinh ${esc(F.short(p.charges))}${p.percent ? ` (${esc(p.percent)})` : ''}">
        <div class="fill" style="width:${p.fill}%"></div><div class="today${p.dayPct < 30 ? ' early' : ''}" style="left:${p.dayPct}%"><span>hôm nay ${p.day}/${p.month}</span></div></div>
      <div class="mrow"><div class="got"><b>${amount(p.received)}</b>đã thu${p.percent ? ` · ${esc(p.percent)}` : ''}</div>
        <div class="chg"><b>${amount(p.charges)}</b>${p.charges > 0n ? 'phát sinh tháng này' : 'chưa phát sinh'}</div></div>`;
    return `<section class="card month" aria-labelledby="h-month">${head}${meter}${foot}</section>`;
  }

  // 3. Khách cần đòi trước: bảng, hình là cột cơ cấu nợ trên cùng thang; lý do là hai cột số ngày tô theo ngưỡng.
  const listCard = () => `<section class="card debtors" aria-labelledby="h-list"><div class="card-head"><h2 id="h-list">Khách cần đòi trước</h2>
      <span class="aside" id="list-aside"></span><label class="com-pick"><select id="com-filter" aria-label="Lọc theo mặt hàng"></select></label></div>
      <div class="dhead"><span>Khách</span><span class="mb-h">Cơ cấu nợ · cùng thang</span><button type="button" data-sort="overdue" id="col-first">Quá hạn</button><button type="button" data-sort="total">Còn nợ</button><button type="button" data-sort="pay" class="dh">Chưa trả</button><button type="button" data-sort="trip" class="dh">Đi hàng</button></div>
      <div id="list"></div>
      <div class="tbl-foot"><span class="lg" id="list-legend"></span><a id="list-all" href="/cong-no-theo-thang.html?con-no=1"></a></div></section>`;

  // 4. Khách quá hạn đang ở đâu: ma trận 2×2 trả gần nhất × đi hàng gần nhất; bấm ô = lọc bảng.
  const matrixCard = () => `<section class="card matrix" id="mx-card" aria-labelledby="h-mx"><div class="card-head"><h2 id="h-mx">Khách quá hạn đang ở đâu</h2><span class="aside">bấm ô để lọc bảng</span></div>
      ${state.mx ? '<div class="mx" id="mx"></div>' : '<p class="empty">Chưa tải được phân loại khách. Bấm Làm mới để thử lại.</p>'}</section>`;

  function paintList() {
    const rule = state.debt?.rule;
    $('list-legend').innerHTML = rule ? `<span><i class="dot r-high"></i>Rủi ro cao</span><span><i class="dot r-watch"></i>Theo dõi</span><span>ngày đỏ: chưa trả &gt; ${rule.no_pay_days} · không đi hàng &gt; ${rule.no_trip_days}</span>` : '';
    if (!state.rows) {
      $('list').innerHTML = '<p class="empty">Chưa tải được danh sách khách quá hạn. Bấm Làm mới để thử lại.</p>';
      $('list-aside').textContent = '';
      $('list-all').textContent = 'Xem ở Công nợ theo tháng ›';
      $('com-filter').hidden = true;
      return;
    }
    const rows = M.filterRows(state.rows, { tier: state.tier, cls: state.cls, com: state.com, sort: state.sort });
    const shown = rows.slice(0, 10);
    const max = shown.reduce((top, item) => (item.row.total > top ? item.row.total : top), 0n);
    $('h-list').textContent = filtered() ? `${rows.length} khách theo lọc` : 'Khách cần đòi trước';
    $('list-aside').textContent = filtered()
      ? `tổng ${F.short(F.sum(rows.map(item => item.first)))} · tỷ đồng`
      : `${state.debt.summary.overdue_customers}/${state.rows.length} khách có nợ quá hạn · tỷ đồng`;
    $('col-first').textContent = state.tier != null ? 'Nợ nhóm này' : 'Quá hạn';
    document.querySelectorAll('[data-sort]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.sort === state.sort)));
    const select = $('com-filter');
    select.hidden = !state.coms.length;
    select.disabled = !state.ready;
    select.innerHTML = `<option value="">Mặt hàng: tất cả</option>${state.coms.map(item => `<option value="${esc(item.key)}">${esc(item.label)} · ${item.count}</option>`).join('')}`;
    select.value = state.com ?? '';
    const day = (days, limit, never) => { const cell = M.dayCell(days, limit, rule.active_trip_days, never); return `<span class="days${cell.tone ? ` ${cell.tone}` : ''}">${esc(cell.text)}</span>`; };
    $('list').innerHTML = shown.length ? shown.map(({ row, first }) => `<button type="button" class="drow" data-khach="${row.id}" data-tip="khach:${row.id}" aria-haspopup="dialog" title="${esc(M.RISK[row.risk] ?? '')} — ${esc(row.why)}">
        <span class="who"><i class="dot r-${esc(row.risk)}" aria-hidden="true"></i><span class="nm">${esc(nameOf(row.id))}</span></span>
        <span class="mbar" aria-hidden="true"><span style="width:${F.barWidth(row.total, max)}%">${row.tiers.map((value, i) => value > 0n ? `<i style="flex:${F.barWidth(value, row.total)};background:var(--due-${i})"></i>` : '').join('')}</span></span>
        <span class="num od${first > 0n ? '' : ' zero'}" title="${esc(F.full(first))}">${esc(F.billions(first))}</span>
        <span class="num" title="${esc(F.full(row.total))}">${esc(F.billions(row.total))}</span>
        ${day(row.payDays, rule.no_pay_days, 'chưa trả')}${day(row.tripDays, rule.no_trip_days, 'chưa có')}</button>`).join('')
      : `<p class="empty">${filtered() ? 'Không có khách nào khớp lọc này.' : 'Không có khách đang nợ.'}</p>`;
    $('list-all').textContent = rows.length > shown.length ? `Xem cả ${rows.length} khách ở Công nợ theo tháng ›` : 'Xem ở Công nợ theo tháng ›';
  }

  function paintMatrix() {
    const mx = state.mx;
    if (!mx) return;
    const cell = key => mx.cells.find(item => item.key === key);
    const box = key => { const c = cell(key); const on = state.cls?.dim === 'mx' && state.cls.key === key;
      return `<button type="button" class="c h${c.bad}" data-cls="mx:${key}" data-tip="cls:mx:${key}" aria-pressed="${on}"${state.ready ? '' : ' disabled'}><b>${c.count} khách</b><span>${c.count ? `quá hạn ${esc(F.short(c.overdue))}` : '—'}</span></button>`; };
    $('mx').innerHTML = `<div></div><div class="h">${esc(mx.cols[0])}</div><div class="h">${esc(mx.cols[1])}</div>
      <div class="v">${esc(mx.lines[0])}</div>${box('p0t0')}${box('p1t0')}
      <div class="v">${esc(mx.lines[1])}</div>${box('p0t1')}${box('p1t1')}`
      + (state.ready ? '' : '<p class="mx-note" role="note">Số từng khách chưa khớp tổng; xem chi tiết ở Công nợ theo tháng.</p>');
    $('mx-card').classList.toggle('picking', state.cls?.dim === 'mx');
  }

  function paintFilters() {
    $('due-card').classList.toggle('picking', state.tier != null);
    document.querySelectorAll('#due-card [data-tier]').forEach(el => {
      const on = Number(el.dataset.tier) === state.tier;
      if (el.tagName === 'BUTTON') el.setAttribute('aria-pressed', String(on)); else el.classList.toggle('on', on);
    });
    $('filterbar').hidden = !filtered();
    const chip = (text, what) => `<span class="chip">${esc(text)}<button type="button" data-clear="${what}" aria-label="Bỏ lọc ${esc(text)}">✕</button></span>`;
    const cell = cellOf(state.cls);
    $('chips').innerHTML = (state.tier != null ? chip(`Nợ ${state.tiers[state.tier].short}`, 'tier') : '')
      + (cell ? chip(`Khách: ${cell.label.toLowerCase()}`, 'cls') : '')
      + (state.com != null ? chip(`Mặt hàng: ${comOf(state.com)?.label ?? state.com}`, 'com') : '');
  }

  function paint() { paintFilters(); paintList(); paintMatrix(); }

  function render(data, debt, customers = []) {
    state.names = shortLabels(customers);
    root.innerHTML = `<div class="grid">${dueCard(data, debt)}${monthCard(data, debt)}
      <div class="filterbar" id="filterbar" hidden><span>Đang lọc danh sách khách:</span><span class="chips" id="chips"></span><button type="button" class="clear-all" data-clear="all">Bỏ lọc</button></div>
      ${listCard()}${matrixCard()}</div>`;
    paint();
  }

  // Trạng thái trên địa chỉ trang: ?han= (0–4), ?nhom=mx:<ô>, ?mh= (mặt hàng), ?xep=tong|chua-tra|di-hang, ?khach= (ngăn kéo).
  const params = () => new URLSearchParams(location.search);
  const writeUrl = () => {
    const query = params();
    const set = (key, value) => (value == null ? query.delete(key) : query.set(key, value));
    set('han', state.tier == null ? null : String(state.tier));
    set('nhom', state.cls ? `${state.cls.dim}:${state.cls.key}` : null);
    set('mh', state.com);
    set('xep', Object.keys(SORTS).find(key => SORTS[key] === state.sort) ?? null);
    query.delete('xem');
    history.replaceState(null, '', location.pathname + (query.toString() ? `?${query}` : ''));
  };
  const readUrl = () => {
    const query = params();
    state.tier = /^[0-4]$/.test(query.get('han') ?? '') ? Number(query.get('han')) : null;
    const nhom = query.get('nhom');
    state.cls = nhom && nhom.startsWith('mx:') ? { dim: 'mx', key: nhom.slice(3) } : null;
    // Link cũ của DASH-03 (?nhom=com:<mặt hàng>) vẫn mở đúng lọc mặt hàng.
    state.com = query.get('mh') || (nhom?.startsWith('com:') ? nhom.slice(4) || null : null);
    state.sort = SORTS[query.get('xep')] ?? 'overdue';
  };
  // Bỏ lọc không còn nghĩa khi số liệu mới không có nhóm đó, hoặc danh sách chưa khớp tổng.
  const dropStale = () => {
    if (!state.ready) { state.tier = null; state.cls = null; state.com = null; }
    if (state.cls && !cellOf(state.cls)) state.cls = null;
    if (state.com != null && !comOf(state.com)) state.com = null;
  };

  root.addEventListener('click', event => {
    const tier = event.target.closest('[data-tier]');
    if (tier) {
      if (!state.ready) { location.href = '/cong-no-theo-thang.html?con-no=1'; return; }
      state.tier = state.tier === Number(tier.dataset.tier) ? null : Number(tier.dataset.tier);
      writeUrl(); paint(); return;
    }
    const cls = event.target.closest('[data-cls]');
    if (cls && state.ready) {
      const value = cls.dataset.cls;
      const pick = { dim: value.slice(0, value.indexOf(':')), key: value.slice(value.indexOf(':') + 1) };
      state.cls = state.cls?.dim === pick.dim && state.cls.key === pick.key ? null : pick;
      writeUrl(); paint(); return;
    }
    const sort = event.target.closest('[data-sort]');
    if (sort) { state.sort = sort.dataset.sort; writeUrl(); paintList(); return; }
    const clear = event.target.closest('[data-clear]');
    if (clear) {
      const what = clear.dataset.clear;
      if (what === 'all' || what === 'tier') state.tier = null;
      if (what === 'all' || what === 'cls') state.cls = null;
      if (what === 'all' || what === 'com') state.com = null;
      writeUrl(); paint(); return;
    }
    const customer = event.target.closest('[data-khach]');
    if (customer) {
      openDrawer(Number(customer.dataset.khach), customer);
      const query = params(); query.set('khach', customer.dataset.khach);
      history.pushState(null, '', `${location.pathname}?${query}`);
      pushed = true;
    }
  });
  root.addEventListener('change', event => {
    if (event.target.id !== 'com-filter') return;
    state.com = event.target.value || null;
    writeUrl(); paint();
  });

  // Ô thông tin khi rê chuột hoặc focus bàn phím: số đứng đầu, chi tiết theo sau.
  function tipText(key) {
    const kind = key.slice(0, key.indexOf(':'));
    const rest = key.slice(key.indexOf(':') + 1);
    const total = state.debt?.receivable_vnd ?? '0';
    if (kind === 'tier') {
      const i = Number(rest);
      const value = state.debt.due_tiers.find(item => item.tier === M.TIERS[i])?.receivable_vnd ?? '0';
      const count = state.ready ? state.rows.filter(row => row.tiers[i] > 0n).length : null;
      return [state.tiers[i].label, F.short(value), `${F.percent(value, total)} còn phải thu${count == null ? '' : ` · ${count} khách`} · ${state.tiers[i].span}`, F.full(value)];
    }
    if (kind === 'cls') {
      const item = cellOf({ dim: rest.slice(0, rest.indexOf(':')), key: rest.slice(rest.indexOf(':') + 1) });
      if (!item) return null;
      return [item.label, `Quá hạn ${F.short(item.overdue)}`, `${F.percent(item.overdue, total)} còn phải thu · ${item.count} khách · còn nợ ${F.short(item.total)}`, F.full(item.overdue)];
    }
    const row = state.rows?.find(item => item.id === Number(rest));
    if (!row) return null;
    return [nameOf(row.id), `Quá hạn ${F.short(row.overdue)}`, `còn nợ ${F.short(row.total)} · ${row.why}`, 'Bấm để xem nhanh'];
  }
  const tip = $('tip');
  const hideTip = () => { tip.hidden = true; };
  function showTip(el) {
    if (el.disabled) return hideTip();
    const text = tipText(el.dataset.tip);
    if (!text) return hideTip();
    tip.replaceChildren(...text.map((line, index) => {
      const node = document.createElement(index === 1 ? 'b' : 'span');
      node.textContent = line;
      return node;
    }));
    tip.hidden = false;
    const box = el.getBoundingClientRect();
    const left = Math.min(Math.max(8, box.left + box.width / 2 - tip.offsetWidth / 2), innerWidth - tip.offsetWidth - 8);
    const above = box.top - tip.offsetHeight - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${above > 64 ? above : box.bottom + 8}px`;
  }
  document.addEventListener('pointerover', event => { const el = event.target.closest?.('#dashboard [data-tip]'); if (el) showTip(el); else hideTip(); });
  document.addEventListener('focusin', event => { const el = event.target.closest?.('#dashboard [data-tip]'); if (el) showTip(el); else hideTip(); });
  document.addEventListener('focusout', hideTip);
  addEventListener('scroll', hideTip, { passive: true });

  // Ngăn kéo xem nhanh một khách: còn nợ, quá hạn, vì sao ở mức rủi ro này, nợ theo tháng tô theo nhóm hạn trả.
  let lastFocus = null;
  let pushed = false;
  function openDrawer(id, trigger = null) {
    const row = state.rows?.find(item => item.id === id);
    if (!row) return;
    hideTip();
    $('d-name').textContent = nameOf(id);
    $('d-sub').textContent = commodityText(row.commodity, row.transportMode);
    const months = row.months.filter(item => item.value !== 0n);
    const max = months.reduce((top, item) => (item.value > top ? item.value : top), 0n);
    const missing = state.data.todo.missing_price.find(item => item.customer_id === id);
    $('d-body').innerHTML = `<div class="dtotals"><div><span>Còn nợ</span><b>${amount(row.total)}</b></div><div class="late"><span>Quá hạn</span><b>${amount(row.overdue)}</b></div></div>
      <h3>${M.RISK[row.risk]} — vì sao</h3><ul class="reasons">${M.reasons(row, state.debt.rule).map(text => `<li>${esc(text)}</li>`).join('')}</ul>
      <h3>Còn nợ theo tháng phát sinh</h3>${months.map(item => `<div class="mrow"><span>Tháng ${esc(`${item.key.slice(5, 7)}/${item.key.slice(0, 4)}`)}<small>${esc(state.tiers[item.tier].label)}</small></span><span class="track"><i style="width:${F.barWidth(item.value, max)}%;background:var(--due-${item.tier})"></i></span><span class="r money" title="${esc(F.full(item.value))}">${item.value < 0n ? `dư ${esc(F.short(-item.value))}` : esc(F.short(item.value))}</span></div>`).join('')}
      ${missing ? `<p class="flags">${missing.count} chuyến thiếu đơn giá — chưa tính vào số trên.</p>` : ''}`;
    $('d-open').href = ledgerHref(id);
    $('d-matrix').href = '/cong-no-theo-thang.html?con-no=1';
    lastFocus = trigger ?? document.activeElement;
    $('scrim').hidden = false;
    $('drawer').hidden = false;
    $('d-close').focus();
  }
  function closeDrawer() {
    $('scrim').hidden = true;
    $('drawer').hidden = true;
    const again = lastFocus?.dataset?.khach && document.querySelector(`#list [data-khach="${lastFocus.dataset.khach}"]`);
    (again || lastFocus)?.focus?.();
  }
  const leave = () => {
    if ($('drawer').hidden) return;
    if (pushed) { pushed = false; history.back(); return; }
    closeDrawer();
    const query = params(); query.delete('khach');
    history.replaceState(null, '', location.pathname + (query.toString() ? `?${query}` : ''));
  };
  $('d-close').addEventListener('click', leave);
  $('scrim').addEventListener('click', leave);
  document.addEventListener('keydown', event => {
    if ($('drawer').hidden) return;
    if (event.key === 'Escape') leave();
    if (event.key === 'Tab') {
      const focusable = [...$('drawer').querySelectorAll('button,a[href]')];
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  window.addEventListener('popstate', () => {
    pushed = false;
    readUrl();
    if (state.data) { dropStale(); paint(); }
    const id = Number(params().get('khach'));
    if (id) openDrawer(id); else if (!$('drawer').hidden) closeDrawer();
  });

  function setupSearch(customers) {
    currentCustomers = customers;
    if (searchReady) return;
    searchReady = true;
    const input = document.querySelector('#customer-search');
    const results = document.querySelector('#customer-results');
    const draw = () => {
      const query = fold(input.value);
      const labels = customerLabels(currentCustomers);
      const found = currentCustomers.filter(item => [item.name, item.display_name, item.label, item.commodity, ...(item.aliases ?? [])]
        .some(value => fold(value).includes(query))).slice(0, 20);
      results.innerHTML = found.map(item => `<a role="option" href="${ledgerHref(item.id)}">${esc(labels.get(String(item.id)))}</a>`).join('');
      results.hidden = !query || !found.length;
    };
    input.addEventListener('input', draw);
    input.addEventListener('focus', draw);
    document.addEventListener('click', event => { if (!event.target.closest('.search')) results.hidden = true; });
  }

  // Số trên mục "Việc cần làm": khách có chuyến thiếu giá/chờ kiểm, chưa có số dư đầu, cần gán mặt hàng.
  function paintTodoBadge(data, rows) {
    const badge = $('todo-badge');
    if (!badge) return;
    const ids = new Set([...data.todo.missing_price, ...data.todo.pending_review, ...data.todo.no_baseline].map(item => item.customer_id));
    for (const row of rows ?? []) if (row.com === M.UNSORTED) ids.add(row.id);
    badge.textContent = ids.size ? String(ids.size) : '';
    badge.hidden = !ids.size;
    badge.setAttribute('aria-label', `${ids.size} khách cần xem`);
  }

  const json = async url => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw Error(url);
    return response.json();
  };

  async function load() {
    if (loading) return;
    loading = true;
    try {
      const response = await fetch('/api/v7/dashboard', { cache: 'no-store' });
      if (!response.ok) throw Error('Không tải được tổng quan công nợ.');
      const data = await response.json();
      const [year, month, day] = data.as_of.split('-');
      document.querySelector('#as-of').textContent = `Số liệu đến ${day}/${month}/${year}`;
      const banner = document.querySelector('#demo-banner');
      if (data.demo || data.real_copy) {
        banner.hidden = false;
        banner.textContent = data.real_copy ? 'Dữ liệu thật · bản sao cô lập, chưa phải prod' : 'Dữ liệu thử · DỮ LIỆU GIẢ · Không phải sổ thật';
      }
      // Phần quá hạn và danh sách khách là phần thêm: lỗi thì trang vẫn đọc được số tổng.
      const [customers, debt] = await Promise.all([
        json('/api/v7/customers').then(body => body.customers ?? []).catch(() => []),
        json('/api/v7/dashboard/debt').catch(() => null),
      ]);
      state.data = data;
      state.debt = debt;
      try {
        state.rows = debt ? M.debtors(debt) : null;
      } catch {
        state.rows = null;
      }
      state.mx = state.rows ? M.matrix(state.rows, debt.rule) : null;
      // Tổng 4 ô ma trận phải bằng ngoặc "Quá hạn" (summary); lệch thì như danh sách lệch tổng: không lọc tại chỗ.
      state.ready = Boolean(state.rows) && M.totalsMatch(state.rows, debt) && M.matrixMatches(state.mx, debt.summary);
      state.tiers = M.tierLabels(debt?.as_of ?? data.as_of, debt?.rule);
      state.coms = state.rows ? M.commodities(state.rows) : [];
      dropStale();
      render(data, debt, customers);
      setupSearch(customers);
      paintTodoBadge(data, state.rows);
      document.querySelector('#error').hidden = true;
      markUpdated();
      const open = Number(params().get('khach'));
      if (open && $('drawer').hidden) openDrawer(open);
    } catch (error) {
      const alert = document.querySelector('#error');
      alert.hidden = false;
      alert.textContent = error.message;
      if (!root.querySelector('.grid')) root.replaceChildren();
    } finally { loading = false; }
  }

  readUrl();
  load();
  const refresh = () => { if (document.activeElement?.id === 'customer-search' || !$('drawer').hidden) return; load(); sheetRefresh?.load(); };
  const button = document.querySelector('#refresh-data');
  if (globalThis.SheetRefresh) {
    sheetRefresh = globalThis.SheetRefresh.create({ node: document.querySelector('#updated-at'), button, onDone: () => load() });
    sheetRefresh.load();
  }
  button?.addEventListener('click', () => { load(); sheetRefresh?.trigger(); });
  setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
