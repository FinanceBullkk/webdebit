/* Tổng quan công nợ (DASH-05, 2/11/2026: bản ít chữ theo canvas): dải đầu Còn phải thu + hạn trả, thẻ Thu tháng,
   chip mức rủi ro lọc bảng khách. Mỗi số một chỗ; chữ đầy đủ ở ô chú thích khi rê chuột hoặc focus (data-tip). */
(() => {
  'use strict';
  const F = CongNoFormat;
  const M = DashboardModel;
  const root = document.querySelector('#dashboard');
  const $ = id => document.getElementById(id);
  const { esc, fold, commodityText, customerLabels } = F;
  const ledgerHref = id => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}`;
  // DASH-05 (2): bấm tên khách mở trang khách ở thẻ Tình hình; ô tìm khách vẫn mở thẻ Sổ.
  const pageHref = id => `${ledgerHref(id)}&the=tinh-hinh`;
  // Sang Công nợ theo tháng: chỉ khách còn nợ, xếp nợ nhiều nhất trước.
  const matrixHref = () => '/cong-no-theo-thang.html?con-no=1&xep=con-no';
  // Số rút gọn trên dải đầu và chip ("2,48 tỷ", "350 tr"); bảng ghi triệu không đơn vị (F.millions).
  const short = value => F.short(value, 'tr');
  const positive = value => String(value).replace(/^-/, '');
  const tipAttr = lines => ` data-tip="${esc(lines.filter(Boolean).join('\n'))}"`;
  const svg = body => `<svg viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
  const ICON = {
    people: svg('<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6"/>'),
    tag: svg('<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="7.5" r="1.2"/><path d="M14 9l-5 5"/>'),
    wallet: svg('<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M12 9v6M9 12h6"/>'),
    funnel: svg('<path d="M4 5h16l-6 8v6l-4-2v-4z"/>'),
    calendar: svg('<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>'),
    clock: svg('<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 2h6"/>'),
    cash: svg('<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>'),
    truck: svg('<path d="M3 7h11v9H3zM14 10h4l3 3v3h-7z"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>'),
    next: svg('<path d="M9 6l6 6-6 6"/>'),
    close: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
  };
  // Tên ngắn cho bảng: tên Sheet; trùng tên thì thêm mặt hàng, vẫn trùng thì thêm số sổ.
  const shortLabels = customers => {
    const base = row => row.display_name ?? row.name;
    const withCommodity = row => `${base(row)} · ${commodityText(row.commodity, row.transport_mode)}`;
    return new Map(customers.map(row => {
      if (customers.filter(item => base(item) === base(row)).length < 2) return [String(row.id), base(row)];
      if (customers.filter(item => withCommodity(item) === withCommodity(row)).length < 2) return [String(row.id), withCommodity(row)];
      return [String(row.id), `${withCommodity(row)} · sổ ${row.id}`];
    }));
  };
  const SORTS = { tong: 'total', 'chua-tra': 'pay', 'di-hang': 'trip' };
  const RISK_URL = { cao: 'high', 'theo-doi': 'watch', 'khong-qua-han': 'ok' };
  const PAGE_ROWS = 10;
  let loading = false;
  // Nút Làm mới đọc Sheet ngay (specs/v7-sheet-refresh.md); chữ trạng thái chỉ hiện khi đang lấy hoặc lỗi.
  let sheetRefresh = null;
  let searchReady = false;
  let currentCustomers = [];
  // tier: nhóm hạn trả đang lọc (0–4); risk: mức rủi ro; com: mặt hàng; sort: cột xếp; all: đã mở hết danh sách.
  const state = { tier: null, risk: null, com: null, sort: 'overdue', all: false, data: null, debt: null, rows: null, ready: false,
    tiers: [], rk: null, coms: [], names: new Map() };
  const nameOf = id => state.names.get(String(id)) ?? state.rows?.find(row => row.id === id)?.name ?? `Sổ ${id}`;
  const comOf = key => state.coms.find(item => item.key === key) ?? null;
  const tierValue = i => state.debt.due_tiers.find(item => item.tier === M.TIERS[i])?.receivable_vnd ?? '0';
  // Màu chữ số tiền theo nhóm: quá hạn 1–2 tháng cam, từ 3 tháng đỏ.
  const tierInk = i => (i >= 3 ? 'red' : i === 2 ? 'amber' : '');

  function markUpdated(asOf) {
    const clock = $('as-of');
    // Giờ cập nhật theo giờ VN: đồng hồ ghi HH:MM, chú thích ghi đủ giây.
    const seconds = new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });
    if (asOf) clock.dataset.asOf = `${asOf.slice(8, 10)}/${asOf.slice(5, 7)}/${asOf.slice(0, 4)}`;
    clock.textContent = seconds.slice(0, 5);
    clock.dataset.tip = [`Số liệu đến ${clock.dataset.asOf ?? '—'}`, `Cập nhật ${seconds} · tự tải mỗi 60 giây`].join('\n');
    $('updated-at').textContent = `Cập nhật ${seconds} · tự tải mỗi 60 giây`;
    sheetRefresh?.paint();
  }

  // 1. Dải đầu: Còn phải thu + nút đếm; ngoặc Trong hạn/Quá hạn, thanh 5 đoạn chỉ là hình, số ở 5 ô.
  function owePart(data, debt) {
    const total = data.receivable.total_vnd;
    const missing = data.todo.missing_price.reduce((count, item) => count + item.count, 0);
    const credit = data.credit.customers ? short(positive(data.credit.total_vnd)) : null;
    const pills = `<span class="pill" tabindex="0"${tipAttr([`${data.receivable.customers} khách đang nợ`])}>${ICON.people}${data.receivable.customers}<span class="sr-only"> khách đang nợ</span></span>`
      + (missing ? `<a class="pill warn" id="missing-price" href="/viec-can-lam.html"${tipAttr([`${missing} chuyến chưa có đơn giá`, 'Chưa tính vào số Còn phải thu · bấm để mở Việc cần làm'])}>${ICON.tag}${missing}<span class="sr-only"> chuyến chưa giá</span></a>` : '')
      + (credit ? `<span class="pill credit" id="credit" tabindex="0"${tipAttr([`${data.credit.customers} khách trả thừa ${credit}`, 'Tính riêng, không trừ vào số Còn phải thu'])}>${ICON.wallet}${esc(credit)}<span class="sr-only"> khách trả thừa</span></span>` : '');
    const head = `<span class="lbl" id="h-owe">Còn phải thu</span><div class="owe-row"><b class="big-money" tabindex="0"${tipAttr(['Còn phải thu', F.full(total)])}>${esc(short(total))}</b>${pills}</div>`;
    if (!debt) return `${head}<p class="empty">Chưa tải được phần quá hạn. Bấm Làm mới để thử lại.</p>`;
    const whole = debt.receivable_vnd;
    if (F.toBig(whole) <= 0n) return `${head}<p class="empty">Chưa có khách đang nợ.</p>`;
    const values = M.TIERS.map((_, i) => tierValue(i));
    const inTerm = F.sum(values.slice(0, 2));
    const late = debt.summary.overdue_vnd;
    const credited = state.rk?.credit.count ? `Đã trừ ${state.rk.credit.count} khách dư ở nợ cũ ${short(-state.rk.credit.overdue)}` : '';
    const brk = `<div class="brk"><div class="in" style="width:max(${F.barWidth(inTerm, whole)}%,9.5em)" tabindex="0"${tipAttr(['Trong hạn: chưa quá hạn', `${short(inTerm)} · ${F.percent(inTerm, whole)} còn phải thu`, F.full(inTerm)])}>Trong hạn <strong>${esc(short(inTerm))}</strong></div>`
      + `<div class="late" tabindex="0"${tipAttr(['Quá hạn', `${short(late)} · ${F.percent(late, whole)} còn phải thu`, credited, F.full(late)])}>Quá hạn <strong>${esc(short(late))}</strong></div></div>`;
    const count = i => (state.ready ? state.rows.filter(row => row.tiers[i] > 0n).length : null);
    const tip = i => [`${state.tiers[i].label} (${state.tiers[i].span})`,
      `${short(values[i])}${count(i) == null ? '' : ` · ${count(i)} khách`} · ${F.percent(values[i], whole)} còn phải thu`, F.full(values[i]), 'Bấm để lọc bảng'];
    const bar = `<div class="age-bar">${values.map((value, i) => (F.toBig(value) > 0n
      ? `<button type="button" class="t${i}" data-tier="${i}" aria-label="Lọc khách: ${esc(state.tiers[i].label)}" style="flex:${F.barWidth(value, whole)} 1 0"${tipAttr(tip(i))}></button>` : '')).join('')}</div>`;
    const tiles = `<div class="tiles">${values.map((value, i) => `<button type="button" class="tile" data-tier="${i}" aria-pressed="false"${F.toBig(value) > 0n ? '' : ' disabled'}${tipAttr(tip(i))}>
        <span class="tl"><i class="sw t${i}" aria-hidden="true"></i>${esc(state.tiers[i].tile)}</span><b class="${tierInk(i)}">${esc(short(value))}</b></button>`).join('')}</div>`;
    return `${head}${brk}${bar}${tiles}`;
  }

  // Thẻ Thu tháng: đã thu (xanh lá) / phát sinh, thước có vạch hôm nay, số ngày còn lại của tháng.
  function monthPart(data, debt) {
    const p = M.monthProgress(debt?.as_of ?? data.as_of, debt?.this_month);
    const head = `<h2 id="h-month">Thu tháng ${p.month}</h2>`;
    if (!debt) return `${head}<p class="empty">Chưa tải được số thu tháng này.</p>`;
    const ratio = p.percent ? `Đã thu ${p.percent} phát sinh tháng ${p.month}` : `Tháng ${p.month} chưa phát sinh`;
    return `${head}<div class="m-nums"><span class="got"><b tabindex="0"${tipAttr(['Đã thu', F.full(p.received)])}>${esc(short(p.received))}</b><small>đã thu</small></span>
        <span class="chg"><b tabindex="0"${tipAttr(['Phát sinh tháng này', F.full(p.charges)])}>${esc(short(p.charges))}</b><small>phát sinh</small></span></div>
      <div class="meter" role="img" tabindex="0" aria-label="${esc(`${ratio}; hôm nay ${p.day}/${p.month}`)}"${tipAttr([ratio, `Vạch đen: hôm nay ${p.day}/${p.month}`])}><div class="fill" style="width:${p.fill}%"></div><div class="today" style="left:${p.dayPct}%"></div></div>
      <span class="left" tabindex="0"${tipAttr([`Tới cuối tháng ${p.days}/${p.month}`])}>${ICON.clock}${p.left ? `còn ${p.left} ngày` : 'ngày cuối tháng'}</span>`;
  }

  // 2. Bảng khách: hàng chip mức rủi ro, bảng triệu, ô ngày là viên màu theo ngưỡng.
  function listPart() {
    const rule = state.debt?.rule;
    const th = (sort, label, unit, icon, tip) => `<th scope="col" class="r"${sort ? ` data-col="${sort}"` : ''}><button type="button" data-sort="${sort}"${tipAttr(tip)}>${icon ?? ''}<span${sort === 'overdue' ? ' id="col-first"' : ''}>${label}</span> <small>${unit}</small></button></th>`;
    const head = rule ? `<thead><tr><th scope="col">Khách</th><th scope="col" class="bar-h">Theo hạn trả</th>
        ${th('overdue', 'Quá hạn', 'tr', null, ['Triệu đồng', 'Bấm để xếp'])}${th('total', 'Còn nợ', 'tr', null, ['Triệu đồng', 'Bấm để xếp'])}
        ${th('pay', 'Trả', 'ngày', ICON.cash, ['Số ngày từ lần khách trả gần nhất', `Đỏ khi quá ${rule.no_pay_days} ngày hoặc chưa trả lần nào · bấm để xếp`])}
        ${th('trip', 'Đi hàng', 'ngày', ICON.truck, ['Số ngày từ chuyến gần nhất', `Đỏ khi quá ${rule.no_trip_days} ngày hoặc chưa có chuyến · bấm để xếp`])}
        <th scope="col" class="go"><span class="sr-only">Mở</span></th></tr></thead>` : '';
    return `<section class="debtors" aria-labelledby="h-list"><div class="list-head"><h2 id="h-list">Khách cần đòi trước</h2>
        <label class="com-pick" id="com-pick">${ICON.funnel}<span class="sr-only">Mặt hàng</span><select id="com-filter" aria-label="Lọc theo mặt hàng"></select></label>
        <a class="btn icon-btn" href="${matrixHref()}" aria-label="Mở Công nợ theo tháng"${tipAttr(['Công nợ theo tháng', 'Soi nợ từng khách theo tháng'])}>${ICON.calendar}</a></div>
      <div class="risk-chips" id="chips" role="group" aria-label="Lọc theo mức rủi ro"></div>
      <p class="note" id="list-note" role="note" hidden></p>
      <div class="tbl-wrap"><table class="dtable">${head}<tbody id="list"></tbody></table></div>
      <p class="empty" id="list-empty" hidden></p><div class="more" id="list-more"></div></section>`;
  }

  function paintChips() {
    const node = $('chips');
    if (!state.rk) { node.hidden = true; return; }
    node.hidden = false;
    const off = state.ready ? '' : ' disabled';
    const tips = { high: `Có quá hạn và: quá hạn từ 3 tháng, hoặc trên ${state.debt.rule.no_pay_days} ngày chưa trả, hoặc trên ${state.debt.rule.no_trip_days} ngày không đi hàng`,
      watch: 'Có quá hạn, chưa tới mức rủi ro cao', ok: 'Không có nợ quá hạn' };
    const chip = group => `<button type="button" class="rchip r-${group.key}" data-risk="${group.key}" aria-pressed="${state.risk === group.key}"${off}${tipAttr([
      `${group.label}: ${group.count} khách`, tips[group.key], group.key === 'ok' ? '' : `Tiền quá hạn ${short(group.overdue)}`, 'Bấm để lọc bảng'])}>
        <i class="rdot" aria-hidden="true"></i><span class="rl">${esc(group.label)}</span><span class="n">${ICON.people}${group.count}<span class="sr-only"> khách</span></span>${group.key !== 'ok' && group.count
          ? `<span class="amt">${esc(short(group.overdue))}</span>` : ''}</button>`;
    const tier = state.tier == null ? '' : `<button type="button" class="rchip tier-x" data-clear="tier" aria-label="Bỏ lọc ${esc(state.tiers[state.tier].label)}"${tipAttr([`Đang lọc: ${state.tiers[state.tier].label} (${state.tiers[state.tier].span})`, 'Bấm để bỏ lọc'])}>
        <i class="sw t${state.tier}" aria-hidden="true"></i>${esc(state.tiers[state.tier].tile)}${ICON.close}</button>`;
    node.innerHTML = `<button type="button" class="rchip all" data-risk="" aria-pressed="${state.risk == null}"${off}>Tất cả</button>${state.rk.groups.map(chip).join('')}${tier}`;
  }

  function paintList() {
    const rule = state.debt?.rule;
    const empty = $('list-empty');
    const select = $('com-filter');
    $('list-note').hidden = !state.rows || state.ready;
    $('list-note').textContent = 'Số từng khách chưa khớp tổng; xem chi tiết ở Công nợ theo tháng.';
    if (!state.rows) {
      $('list').innerHTML = '';
      $('list-more').innerHTML = '';
      empty.hidden = false;
      empty.textContent = 'Chưa tải được danh sách khách. Bấm Làm mới để thử lại.';
      $('com-pick').hidden = true;
      return;
    }
    $('com-pick').hidden = !state.coms.length;
    select.disabled = !state.ready;
    select.innerHTML = `<option value="">Mọi mặt hàng</option>${state.coms.map(item => `<option value="${esc(item.key)}">${esc(item.label)}</option>`).join('')}`;
    select.value = state.com ?? '';
    $('col-first').textContent = state.tier != null ? 'Nhóm này' : 'Quá hạn';
    document.querySelectorAll('.dtable th[data-col]').forEach(cell => {
      if (cell.dataset.col === state.sort) cell.setAttribute('aria-sort', 'descending'); else cell.removeAttribute('aria-sort');
    });
    const rows = M.filterRows(state.rows, { tier: state.tier, risk: state.risk, com: state.com, sort: state.sort });
    const shown = state.all ? rows : rows.slice(0, PAGE_ROWS);
    const max = shown.reduce((top, item) => (item.row.total > top ? item.row.total : top), 0n);
    const day = (days, limit) => { const cell = M.dayCell(days, limit, rule.active_trip_days); return `<span class="days${cell.tone ? ` ${cell.tone}` : ''}">${esc(cell.text)}</span>`; };
    const late = state.tier == null || state.tier >= 2;
    $('list').innerHTML = shown.map(({ row, first }) => `<tr data-id="${row.id}"${tipAttr([nameOf(row.id), `${M.RISK[row.risk] ?? ''} — ${row.why}`,
        `Còn nợ ${F.full(row.total)}`, 'Bấm để mở Tình hình'])}>
        <td class="who"><a href="${pageHref(row.id)}"><i class="rdot r-${esc(row.risk)}" aria-hidden="true"></i><span class="sr-only">${esc(M.RISK[row.risk] ?? '')}: </span><span class="nm">${esc(nameOf(row.id))}</span></a></td>
        <td class="bar"><span class="mbar" aria-hidden="true" style="width:${F.barWidth(row.total, max)}%">${row.tiers.map((value, i) => (value > 0n ? `<i class="t${i}" style="flex:${F.barWidth(value, row.total)} 1 0"></i>` : '')).join('')}</span></td>
        <td class="num od${first > 0n ? (late ? ' red' : '') : ' zero'}">${first === 0n ? '–' : esc(F.millions(first))}</td>
        <td class="num tot">${esc(F.millions(row.total))}</td>
        <td class="d">${day(row.payDays, rule.no_pay_days)}</td><td class="d">${day(row.tripDays, rule.no_trip_days)}</td>
        <td class="go" aria-hidden="true">${ICON.next}</td></tr>`).join('');
    empty.hidden = shown.length > 0;
    empty.textContent = state.tier != null || state.risk != null || state.com != null ? 'Không có khách nào khớp bộ lọc.' : 'Không có khách đang nợ.';
    $('list-more').innerHTML = rows.length > shown.length ? `<button type="button" class="btn" data-more>Hiện cả ${rows.length} khách</button>` : '';
  }

  function paintTiers() {
    document.querySelectorAll('#dashboard [data-tier]').forEach(el => {
      const on = Number(el.dataset.tier) === state.tier;
      if (el.classList.contains('tile')) el.setAttribute('aria-pressed', String(on));
      el.classList.toggle('dim', state.tier != null && !on);
    });
  }

  function paint() { paintTiers(); paintChips(); paintList(); }

  function render(data, debt, customers = []) {
    state.names = shortLabels(customers);
    root.innerHTML = `<section class="strip" aria-labelledby="h-owe"><div class="owe">${owePart(data, debt)}</div>
      <div class="month-card" role="group" aria-labelledby="h-month">${monthPart(data, debt)}</div></section>${listPart()}`;
    paint();
  }

  // Trạng thái trên địa chỉ trang: ?han= (0–4), ?muc= (mức rủi ro), ?mh= (mặt hàng), ?xep=tong|chua-tra|di-hang.
  const params = () => new URLSearchParams(location.search);
  const writeUrl = () => {
    const query = params();
    const set = (key, value) => (value == null ? query.delete(key) : query.set(key, value));
    set('han', state.tier == null ? null : String(state.tier));
    set('muc', Object.keys(RISK_URL).find(key => RISK_URL[key] === state.risk) ?? null);
    set('mh', state.com);
    set('xep', Object.keys(SORTS).find(key => SORTS[key] === state.sort) ?? null);
    // Tham số của bản cũ (ô ma trận DASH-04, ngăn kéo, tab cũ) không còn nghĩa.
    for (const key of ['nhom', 'khach', 'xem']) query.delete(key);
    history.replaceState(null, '', location.pathname + (query.toString() ? `?${query}` : ''));
  };
  const readUrl = () => {
    const query = params();
    state.tier = /^[0-4]$/.test(query.get('han') ?? '') ? Number(query.get('han')) : null;
    state.risk = RISK_URL[query.get('muc')] ?? null;
    const nhom = query.get('nhom');
    // Link cũ của DASH-03 (?nhom=com:<mặt hàng>) vẫn mở đúng lọc mặt hàng.
    state.com = query.get('mh') || (nhom?.startsWith('com:') ? nhom.slice(4) || null : null);
    state.sort = SORTS[query.get('xep')] ?? 'overdue';
  };
  // Bỏ lọc không còn nghĩa khi số liệu mới không có nhóm đó, hoặc danh sách chưa khớp tổng.
  const dropStale = () => {
    if (!state.ready) { state.tier = null; state.risk = null; state.com = null; }
    if (state.com != null && !comOf(state.com)) state.com = null;
  };

  root.addEventListener('click', event => {
    const tier = event.target.closest('[data-tier]');
    if (tier) {
      if (!state.ready) { location.href = matrixHref(); return; }
      state.tier = state.tier === Number(tier.dataset.tier) ? null : Number(tier.dataset.tier);
      writeUrl(); paint(); return;
    }
    const risk = event.target.closest('[data-risk]');
    if (risk) {
      const key = risk.dataset.risk || null;
      state.risk = state.risk === key ? null : key;
      writeUrl(); paint(); return;
    }
    if (event.target.closest('[data-clear="tier"]')) { state.tier = null; writeUrl(); paint(); return; }
    const sort = event.target.closest('[data-sort]');
    if (sort) { state.sort = sort.dataset.sort; writeUrl(); paintList(); return; }
    if (event.target.closest('[data-more]')) { state.all = true; paintList(); return; }
    // Bấm chỗ khác trên dòng khách cũng mở trang khách như bấm tên.
    const line = event.target.closest('#list tr[data-id]');
    if (line && !event.target.closest('a')) location.href = pageHref(Number(line.dataset.id));
  });
  root.addEventListener('change', event => {
    if (event.target.id !== 'com-filter') return;
    state.com = event.target.value || null;
    writeUrl(); paint();
  });

  // Ô chú thích khi rê chuột hoặc focus bàn phím: dòng đầu đậm, các dòng sau là chi tiết.
  const tip = $('tip');
  const hideTip = () => { tip.hidden = true; };
  function showTip(el) {
    if (el.disabled || !el.dataset.tip) return hideTip();
    tip.replaceChildren(...el.dataset.tip.split('\n').map((line, index) => {
      const node = document.createElement(index === 0 ? 'b' : 'span');
      node.textContent = line;
      return node;
    }));
    tip.hidden = false;
    const box = el.getBoundingClientRect();
    const left = Math.min(Math.max(8, box.left + box.width / 2 - tip.offsetWidth / 2), innerWidth - tip.offsetWidth - 8);
    const above = box.top - tip.offsetHeight - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${above > 8 ? above : box.bottom + 8}px`;
  }
  const tipOf = target => target.closest?.('.tq-page [data-tip]');
  document.addEventListener('pointerover', event => { const el = tipOf(event.target); if (el) showTip(el); else hideTip(); });
  document.addEventListener('focusin', event => { const el = tipOf(event.target); if (el) showTip(el); else hideTip(); });
  document.addEventListener('focusout', hideTip);
  addEventListener('scroll', hideTip, { passive: true });
  window.addEventListener('popstate', () => { readUrl(); if (state.data) { dropStale(); paint(); } });

  function setupSearch(customers) {
    currentCustomers = customers;
    if (searchReady) return;
    searchReady = true;
    const input = $('customer-search');
    const results = $('customer-results');
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
      const banner = $('demo-banner');
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
      state.rk = state.rows ? M.risks(state.rows) : null;
      // Tổng từng khách phải bằng 5 nhóm của server, chip phải bằng summary; lệch thì không lọc tại chỗ.
      state.ready = Boolean(state.rows) && M.totalsMatch(state.rows, debt) && M.riskMatches(state.rk, debt.summary);
      state.tiers = M.tierLabels(debt?.as_of ?? data.as_of, debt?.rule);
      state.coms = state.rows ? M.commodities(state.rows) : [];
      dropStale();
      render(data, debt, customers);
      setupSearch(customers);
      paintTodoBadge(data, state.rows);
      $('error').hidden = true;
      markUpdated(data.as_of);
    } catch {
      const alert = $('error');
      alert.hidden = false;
      // Audit UX 31/10/2026 (P1-6): một câu tiếng Việt "chuyện gì · cần làm gì" và nút Thử lại; không bao giờ hiện chữ của trình duyệt.
      alert.innerHTML = `${esc(F.loadError('tổng quan công nợ'))} <button type="button" class="btn" data-retry>Thử lại</button>`;
      if (!root.querySelector('.strip')) root.replaceChildren();
    } finally { loading = false; }
  }

  readUrl();
  load();
  const refresh = () => { if (document.activeElement?.id === 'customer-search') return; load(); sheetRefresh?.load(); };
  $('error').addEventListener('click', event => { if (event.target.closest('[data-retry]')) load(); });
  const button = $('refresh-data');
  if (globalThis.SheetRefresh) {
    sheetRefresh = globalThis.SheetRefresh.create({ node: $('updated-at'), button, onDone: () => load() });
    sheetRefresh.load();
  }
  button?.addEventListener('click', () => { load(); sheetRefresh?.trigger(); });
  $('nav-toggle').addEventListener('click', event => {
    const toggle = event.currentTarget;
    const expanded = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.closest('.todo-nav').classList.toggle('menu-open', expanded);
  });
  setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
