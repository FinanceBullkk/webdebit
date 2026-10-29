// Bản xem Tổng quan quản lý công nợ: vẽ từ MOCK (data.js), không gọi API.
// Tương tác giữ như Tổng quan đã duyệt 29/10/2026: bấm nhóm để lọc danh sách khách tại chỗ, bấm khách mở ngăn kéo.
(() => {
  'use strict';
  const D = window.MOCK;
  const $ = id => document.getElementById(id);
  const esc = D.esc;
  const root = $('dashboard');
  // tier: nhóm hạn trả đang lọc (0–4); cls: {dim, key} lớp phân loại đang lọc; dim: tiêu chí đang xem; sort: cột xếp.
  const state = { tier: null, cls: null, dim: 'risk', sort: 'overdue' };
  const money = value => `<span class="money" title="${esc(D.full(value))}">${esc(D.short(value))}</span>`;
  const dimOf = key => D.DIMS.find(dim => dim.key === key);
  const classOf = (dimKey, key) => dimOf(dimKey).groups.find(item => item.key === key);
  const filtered = () => state.tier != null || state.cls != null;
  const RISK = { high: ['critical', 'Rủi ro cao'], watch: ['warning', 'Theo dõi'], ok: [null, 'Trong hạn'] };
  const riskTag = row => RISK[row.risk][0] ? `<span class="tag ${RISK[row.risk][0]}">${RISK[row.risk][1]}</span>` : '';

  function receivableCard() {
    const [figure, unit] = D.hero(D.receivable);
    const month = D.AS_OF.month;
    return `<section class="card receivable" aria-labelledby="h-rec"><h2 id="h-rec">Còn phải thu</h2>
      <div class="big-money" title="${esc(D.full(D.receivable))}">${esc(figure)}<small>${unit}</small></div>
      <div class="substat"><span class="money">${esc(D.full(D.receivable))}</span> · ${D.debtors.length} khách đang nợ</div>
      <div class="minis">
        <div class="mini"><div class="k">Đã thu tháng ${month}</div><div class="v">${money(D.paidThisMonth)}</div><div class="s">phát sinh ${money(D.chargedThisMonth)}</div></div>
        <button type="button" class="mini risk" data-cls="risk:high" aria-pressed="false"><div class="k">Khách rủi ro cao</div><div class="v">${D.high.length} khách</div><div class="s">quá hạn ${money(D.highOverdue)}</div></button>
      </div>
      <p class="hero-foot">Chưa tính ${D.missingTrips} chuyến thiếu đơn giá · ${D.creditors.length} khách đang dư ${money(-D.credit)}, tính riêng</p></section>`;
  }

  function dueCard() {
    const total = D.receivable;
    const mark = (D.tiers[0] + D.tiers[1]) / total * 100;
    const segments = D.tiers.map((value, i) => value > 0 ? `<span data-tier="${i}" data-tip="tier:${i}" style="flex:${value};background:var(--due-${i})"></span>` : '').join('');
    const legend = D.TIERS.map((tier, i) => `<button type="button" class="${i >= 2 ? 'late' : ''}" data-tier="${i}" data-tip="tier:${i}" aria-pressed="false">
        <div class="k"><span class="sw" style="background:var(--due-${i})"></span>${esc(tier.label)}</div>
        <div class="v">${money(D.tiers[i])}<span class="p">${D.pct(D.tiers[i], total)}</span></div><div class="m">${esc(tier.span)}</div></button>`).join('');
    return `<section class="card due" id="due-card" aria-labelledby="h-due"><div class="card-head"><h2 id="h-due">Nợ theo hạn trả</h2><span class="aside">hạn trả: cuối tháng sau tháng phát sinh</span></div>
      <p class="age-note"><b>${esc(D.short(D.overdue))} (${D.pct(D.overdue, total)})</b> đã quá hạn, trong đó <b>${esc(D.short(D.longOverdue))}</b> quá hạn từ 3 tháng trở lên.</p>
      <div class="due-wrap"><div class="age-bar" role="img" aria-label="${esc(D.TIERS.map((tier, i) => `${tier.label} ${D.short(D.tiers[i])}`).join(', '))}">${segments}</div>
        <div class="due-mark" style="left:${mark}%"><span class="l">trong hạn</span><span class="r">quá hạn</span></div></div>
      <div class="age-legend">${legend}</div></section>`;
  }

  const listCard = () => `<section class="card debtors" aria-labelledby="h-list"><div class="card-head"><h2 id="h-list"></h2><span class="aside" id="list-aside"></span></div>
      <div class="dhead"><span>Khách</span><span class="mb-h">Cơ cấu nợ</span><button type="button" data-sort="overdue" id="col-first"></button><button type="button" data-sort="total">Còn nợ</button></div>
      <div id="list"></div><div class="tbl-foot"><a href="#" id="list-all"></a></div></section>`;

  const classifyCard = () => `<section class="card classify" id="cls-card" aria-labelledby="h-cls"><div class="card-head"><h2 id="h-cls">Phân loại khách đang nợ</h2><span class="aside">còn nợ · tỷ đồng</span></div>
      <div class="seg" role="tablist" aria-label="Phân loại theo">${D.DIMS.map(dim => `<button type="button" role="tab" data-dim="${dim.key}">${esc(dim.tab)}</button>`).join('')}</div>
      <p class="age-note" id="cls-lead"></p><div class="bars" id="cls-bars"></div></section>`;

  function listRows() {
    let rows = D.debtors;
    if (state.tier != null) rows = rows.filter(row => row.tiers[state.tier] > 0);
    if (state.cls) rows = rows.filter(row => row[state.cls.dim] === state.cls.key);
    // Cột số đầu: tiền quá hạn; khi lọc theo nhóm hạn trả thì là phần nợ thuộc nhóm đó.
    const first = row => state.tier != null ? row.tiers[state.tier] : row.overdue;
    return rows.map(row => ({ row, first: first(row) }))
      .sort((a, b) => state.sort === 'total' ? b.row.total - a.row.total || b.first - a.first : b.first - a.first || b.row.total - a.row.total);
  }

  function paintList() {
    const rows = listRows();
    const shown = rows.slice(0, 10);
    const max = Math.max(1, ...shown.map(item => item.row.total));
    $('h-list').textContent = filtered() ? `${rows.length} khách theo lọc` : 'Khách cần đòi trước';
    $('list-aside').textContent = filtered()
      ? `tổng ${D.short(D.sum(rows.map(item => item.first)))} · tỷ đồng`
      : `${D.overdueCustomers}/${D.debtors.length} khách có nợ quá hạn · tỷ đồng`;
    $('col-first').textContent = state.tier != null ? 'Nợ nhóm này' : 'Quá hạn';
    document.querySelectorAll('[data-sort]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.sort === state.sort)));
    $('list').innerHTML = shown.length ? shown.map(({ row, first }) => `<button type="button" class="drow" data-khach="${row.id}" data-tip="khach:${row.id}" aria-haspopup="dialog">
        <span class="who"><span class="nm">${esc(row.name)}</span>${riskTag(row)}<span class="why">${esc(row.why)}</span></span>
        <span class="mbar" aria-hidden="true"><span style="width:${row.total / max * 100}%">${row.tiers.map((value, i) => value > 0 ? `<i style="flex:${value};background:var(--due-${i})"></i>` : '').join('')}</span></span>
        <span class="num od${first > 0 ? '' : ' zero'}" title="${esc(D.full(first))}">${esc(D.billions(first))}</span>
        <span class="num" title="${esc(D.full(row.total))}">${esc(D.billions(row.total))}</span></button>`).join('')
      : '<p class="empty">Không có khách nào khớp lọc này.</p>';
    $('list-all').textContent = rows.length > shown.length ? `Xem cả ${rows.length} khách ở Công nợ theo tháng ›` : 'Xem ở Công nợ theo tháng ›';
  }

  function paintClassify() {
    const dim = dimOf(state.dim);
    document.querySelectorAll('[data-dim]').forEach(button => button.setAttribute('aria-selected', String(button.dataset.dim === state.dim)));
    $('cls-lead').innerHTML = dim.lead(dim.groups);
    const max = Math.max(...dim.groups.map(item => item.total));
    const firstGrey = dim.groups.find(item => item.tone === 'grey');
    $('cls-bars').innerHTML = dim.groups.map(item => {
      const on = state.cls?.dim === dim.key && state.cls.key === item.key;
      return `<button type="button" class="bar-row${item.tone ? ` ${item.tone}` : ''}${item === firstGrey && dim.key === 'com' ? ' first' : ''}" data-cls="${dim.key}:${esc(item.key)}" data-tip="cls:${dim.key}:${esc(item.key)}" aria-pressed="${on}">
        <span class="line"><span class="nm">${esc(item.label)}</span><span class="cnt">${item.count} khách</span><span class="val money">${esc(D.billions(item.total))}</span></span>
        <span class="track"><i style="width:${item.total / max * 100}%"></i></span></button>`;
    }).join('');
    $('cls-card').classList.toggle('picking', state.cls?.dim === dim.key);
  }

  function paintFilters() {
    $('due-card').classList.toggle('picking', state.tier != null);
    document.querySelectorAll('[data-tier]').forEach(el => {
      const on = Number(el.dataset.tier) === state.tier;
      if (el.tagName === 'BUTTON') el.setAttribute('aria-pressed', String(on)); else el.classList.toggle('on', on);
    });
    document.querySelector('.mini.risk').setAttribute('aria-pressed', String(state.cls?.dim === 'risk' && state.cls.key === 'high'));
    $('filterbar').hidden = !filtered();
    const chip = (text, what) => `<span class="chip">${esc(text)}<button type="button" data-clear="${what}" aria-label="Bỏ lọc ${esc(text)}">✕</button></span>`;
    $('chips').innerHTML = (state.tier != null ? chip(`Nợ ${D.TIERS[state.tier].label.toLowerCase()}`, 'tier') : '')
      + (state.cls ? chip(`${dimOf(state.cls.dim).title}: ${classOf(state.cls.dim, state.cls.key).label.toLowerCase()}`, 'cls') : '');
  }

  function paint() { paintFilters(); paintList(); paintClassify(); }

  function render() {
    root.innerHTML = `<div class="grid">${receivableCard()}${dueCard()}
      <div class="filterbar" id="filterbar" hidden><span>Đang lọc danh sách khách:</span><span class="chips" id="chips"></span><button type="button" class="clear-all" data-clear="all">Bỏ lọc</button></div>
      ${listCard()}${classifyCard()}</div>`;
    paint();
  }

  root.addEventListener('click', event => {
    const tier = event.target.closest('[data-tier]');
    if (tier) { state.tier = state.tier === Number(tier.dataset.tier) ? null : Number(tier.dataset.tier); return paint(); }
    const cls = event.target.closest('[data-cls]');
    if (cls) {
      const [dim, key] = [cls.dataset.cls.slice(0, cls.dataset.cls.indexOf(':')), cls.dataset.cls.slice(cls.dataset.cls.indexOf(':') + 1)];
      state.cls = state.cls?.dim === dim && state.cls.key === key ? null : { dim, key };
      state.dim = dim;
      return paint();
    }
    const dim = event.target.closest('[data-dim]');
    if (dim) { state.dim = dim.dataset.dim; return paintClassify(); }
    const sort = event.target.closest('[data-sort]');
    if (sort) { state.sort = sort.dataset.sort; return paintList(); }
    const clear = event.target.closest('[data-clear]');
    if (clear) {
      if (clear.dataset.clear !== 'cls') state.tier = null;
      if (clear.dataset.clear !== 'tier') state.cls = null;
      return paint();
    }
    const customer = event.target.closest('[data-khach]');
    if (customer) openDrawer(Number(customer.dataset.khach), customer);
  });

  // Ô thông tin khi rê chuột hoặc focus: số đứng đầu, chi tiết theo sau.
  function tipText(key) {
    const [kind, a, ...rest] = key.split(':');
    const b = rest.join(':');
    if (kind === 'tier') {
      const i = Number(a);
      const count = D.debtors.filter(row => row.tiers[i] > 0).length;
      return [D.TIERS[i].label, D.short(D.tiers[i]), `${D.pct(D.tiers[i], D.receivable)} còn phải thu · ${count} khách · ${D.TIERS[i].span}`, D.full(D.tiers[i])];
    }
    if (kind === 'cls') {
      const item = classOf(a, b);
      return [item.label, D.short(item.total), `${D.pct(item.total, D.receivable)} còn phải thu · ${item.names.join(', ')}`, D.full(item.total)];
    }
    const row = D.debtors.find(item => item.id === Number(a));
    return [row.name, `Quá hạn ${D.short(row.overdue)}`, `còn nợ ${D.short(row.total)} · ${row.why}`, 'Bấm để xem nhanh'];
  }
  const tip = $('tip');
  const hideTip = () => { tip.hidden = true; };
  function showTip(el) {
    tip.replaceChildren(...tipText(el.dataset.tip).map((line, index) => {
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

  // Ngăn kéo xem nhanh: còn nợ, quá hạn, vì sao ở mức rủi ro này, nợ theo tháng tô theo nhóm hạn trả.
  let lastFocus = null;
  function openDrawer(id, trigger) {
    const row = D.debtors.find(item => item.id === id);
    if (!row) return;
    hideTip();
    $('d-name').textContent = row.name;
    $('d-sub').textContent = D.comText(row);
    const months = row.months.filter(item => item.value !== 0);
    const max = Math.max(...months.map(item => Math.abs(item.value)));
    const missing = D.TODO.missingPrice.find(item => item.id === id);
    $('d-body').innerHTML = `<div class="dtotals"><div><span>Còn nợ</span><b>${money(row.total)}</b></div><div class="late"><span>Quá hạn</span><b>${money(row.overdue)}</b></div></div>
      <h3>${RISK[row.risk][1]} — vì sao</h3><ul class="reasons">${D.reasons(row).map(text => `<li>${esc(text)}</li>`).join('')}</ul>
      <h3>Còn nợ theo tháng phát sinh</h3>${months.map(item => `<div class="mrow"><span>${esc(item.label)}<small>${esc(D.TIERS[item.tier].label)}</small></span><span class="track"><i style="width:${Math.abs(item.value) / max * 100}%;background:var(--due-${item.tier})"></i></span><span class="r money" title="${esc(D.full(item.value))}">${esc(D.short(item.value))}</span></div>`).join('')}
      ${missing ? `<p class="flags">${missing.count} chuyến thiếu đơn giá — chưa tính vào số trên.</p>` : ''}`;
    lastFocus = trigger ?? document.activeElement;
    $('scrim').hidden = false;
    $('drawer').hidden = false;
    $('d-close').focus();
  }
  function closeDrawer() {
    $('scrim').hidden = true;
    $('drawer').hidden = true;
    lastFocus?.focus?.();
  }
  $('d-close').addEventListener('click', closeDrawer);
  $('scrim').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('drawer').hidden) closeDrawer(); });

  $('as-of').textContent = `Số liệu đến ${D.AS_OF.label}`;
  $('todo-badge').textContent = D.todoCustomers;
  render();
})();
