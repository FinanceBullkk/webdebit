/* Tổng quan công nợ (DASH-05, 2/11/2026: bản ít chữ theo canvas): dải đầu Còn phải thu + hạn trả, thẻ Thu tháng,
   khối Công nợ theo mặt hàng (DASH-07, 9/11/2026), chip mức rủi ro lọc bảng khách. Mỗi số một chỗ; chữ đầy đủ ở ô chú
   thích khi rê chuột hoặc focus (data-tip). */
(() => {
  'use strict';
  const F = CongNoFormat;
  const M = DashboardModel;
  const root = document.querySelector('#dashboard');
  const $ = id => document.getElementById(id);
  const { esc, commodityText } = F;
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

  // Lọc chéo (DASH-08): bộ lọc hiện tại và tên của nó cho nhãn "đang lọc" trên các khối.
  const filter = () => ({ tier: state.tier, risk: state.risk, com: state.com });
  const scopeName = skip => [skip !== 'com' && state.com, skip !== 'risk' && state.risk && M.RISK[state.risk],
    skip !== 'tier' && state.tier != null && state.tiers[state.tier].label].filter(Boolean).join(' · ');
  const scopeTag = (skip, tip) => {
    const name = state.ready ? scopeName(skip) : '';
    return name ? `<span class="scope-tag" tabindex="0"${tipAttr([`Đang lọc: ${name}`, tip])}>${esc(name)}</span>` : '';
  };

  // 1. Dải đầu: Còn phải thu + nút đếm; ngoặc Trong hạn/Quá hạn, thanh 5 đoạn chỉ là hình, số ở 5 ô. Đang lọc mức rủi
  // ro hoặc mặt hàng thì mọi số tính lại cho phạm vi đó; lọc hạn trả chỉ tô ô đang chọn (chiều của chính khối).
  function owePart(data, debt) {
    const scoped = state.ready && (state.risk != null || state.com != null);
    const sc = scoped ? M.totals(M.scope(state.rows, filter(), 'tier')) : null;
    const total = scoped ? sc.total : data.receivable.total_vnd;
    const people = scoped ? sc.count : data.receivable.customers;
    const missing = data.todo.missing_price.reduce((count, item) => count + item.count, 0);
    const credit = data.credit.customers ? short(positive(data.credit.total_vnd)) : null;
    // Chuyến chưa giá và khách trả thừa là số cả công ty, không tách theo lọc: ẩn khi đang lọc.
    const pills = `<span class="pill" tabindex="0"${tipAttr([`${people} khách đang nợ`])}>${ICON.people}${people}<span class="sr-only"> khách đang nợ</span></span>`
      + (missing && !scoped ? `<a class="pill warn" id="missing-price" href="/viec-can-lam.html"${tipAttr([`${missing} chuyến chưa có đơn giá`, 'Chưa tính vào số Còn phải thu · bấm để mở Việc cần làm'])}>${ICON.tag}${missing}<span class="sr-only"> chuyến chưa giá</span></a>` : '')
      + (credit && !scoped ? `<span class="pill credit" id="credit" tabindex="0"${tipAttr([`${data.credit.customers} khách trả thừa ${credit}`, 'Tính riêng, không trừ vào số Còn phải thu'])}>${ICON.wallet}${esc(credit)}<span class="sr-only"> khách trả thừa</span></span>` : '');
    const head = `<span class="lbl" id="h-owe">Còn phải thu${scopeTag('tier', 'Số của dải đầu chỉ tính khách trong phạm vi lọc')}</span><div class="owe-row"><b class="big-money" tabindex="0"${tipAttr(['Còn phải thu', F.full(total)])}>${esc(short(total))}</b>${pills}</div>`;
    if (!debt) return `${head}<p class="empty">Chưa tải được phần quá hạn. Bấm Làm mới để thử lại.</p>`;
    const whole = scoped ? sc.total : debt.receivable_vnd;
    if (scoped && !sc.count) return `${head}<p class="empty">Không có khách nào khớp bộ lọc.</p>`;
    if (F.toBig(whole) <= 0n) return `${head}<p class="empty">Chưa có khách đang nợ.</p>`;
    const values = scoped ? sc.tiers : M.TIERS.map((_, i) => tierValue(i));
    const inTerm = F.sum(values.slice(0, 2));
    const late = scoped ? sc.overdue : debt.summary.overdue_vnd;
    const cr = scoped ? sc.credit : state.rk?.credit;
    const credited = cr?.count ? `Đã trừ ${cr.count} khách dư ở nợ cũ ${short(-cr.overdue)}` : '';
    const brk = `<div class="brk"><div class="in" style="width:max(${F.barWidth(inTerm, whole)}%,9.5em)" tabindex="0"${tipAttr(['Trong hạn: chưa quá hạn', `${short(inTerm)} · ${F.percent(inTerm, whole)} còn phải thu`, F.full(inTerm)])}>Trong hạn <strong>${esc(short(inTerm))}</strong></div>`
      + `<div class="late" tabindex="0"${tipAttr(['Quá hạn', `${short(late)} · ${F.percent(late, whole)} còn phải thu`, credited, F.full(late)])}>Quá hạn <strong>${esc(short(late))}</strong></div></div>`;
    const inScope = state.ready ? M.scope(state.rows, filter(), 'tier') : null;
    const count = i => (inScope ? inScope.filter(row => row.tiers[i] > 0n).length : null);
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
    // Lọc chéo (DASH-08): có số từng sổ (this_month.customers) thì thẻ tính theo cả ba lọc; API cũ chưa có thì thẻ giữ số cả
    // công ty và ghi rõ "cả công ty" khi đang lọc.
    const filtered = state.ready && (state.tier != null || state.risk != null || state.com != null);
    const flow = filtered ? M.monthFlow(debt?.this_month, state.rows, state.coms, filter()) : null;
    const p = M.monthProgress(debt?.as_of ?? data.as_of, flow ?? debt?.this_month);
    const only = state.tier != null || state.risk != null ? 'Chỉ tính sổ đang nợ trong phạm vi; sổ đã hết nợ không có nhóm hạn trả hay mức rủi ro' : 'Gồm cả sổ đã hết nợ của mặt hàng này';
    const whole = !filtered ? '' : flow ? scopeTag(null, only)
      : `<span class="scope-tag all" tabindex="0"${tipAttr(['Số cả công ty', 'Thẻ này chưa tính theo lọc'])}>cả công ty</span>`;
    const head = `<div class="m-head"><h2 id="h-month">Thu tháng ${p.month}${whole}</h2><a class="m-link" href="/bang-thu.html">Bảng thu ›</a></div>`;
    if (!debt) return `${head}<p class="empty">Chưa tải được số thu tháng này.</p>`;
    const ratio = p.percent ? `Đã thu ${p.percent} phát sinh tháng ${p.month}` : `Tháng ${p.month} chưa phát sinh`;
    return `${head}<div class="m-nums"><span class="got"><b tabindex="0"${tipAttr(['Đã thu', F.full(p.received)])}>${esc(short(p.received))}</b><small>đã thu</small></span>
        <span class="chg"><b tabindex="0"${tipAttr(['Phát sinh tháng này', F.full(p.charges)])}>${esc(short(p.charges))}</b><small>phát sinh</small></span></div>
      <div class="meter" role="img" tabindex="0" aria-label="${esc(`${ratio}; hôm nay ${p.day}/${p.month}`)}"${tipAttr([ratio, `Vạch đen: hôm nay ${p.day}/${p.month}`])}><div class="fill" style="width:${p.fill}%"></div><div class="today" style="left:${p.dayPct}%"></div></div>
      <span class="left" tabindex="0"${tipAttr([`Tới cuối tháng ${p.days}/${p.month}`])}>${ICON.clock}${p.left ? `còn ${p.left} ngày` : 'ngày cuối tháng'}</span>`;
  }

  // 2. Công nợ theo mặt hàng (DASH-07): mỗi mặt hàng một dòng, chia hai cột; thanh dài theo còn phải thu (cùng thang =
  // mặt hàng nhiều nhất), phần xanh trong hạn, phần đỏ quá hạn. Bấm dòng = lọc bảng khách. Chỉ hiện khi số từng khách
  // khớp tổng server, nên các dòng cộng lại đúng bằng Còn phải thu của dải đầu.
  // Lọc chéo (DASH-08): đang lọc hạn trả hoặc mức rủi ro thì mỗi dòng chỉ còn khách và tiền trong phạm vi đó; lọc hạn trả
  // thì cột tiền là tiền của nhóm hạn trả ("Nhóm này"), như cột đầu của bảng khách. Nhóm và thứ tự dòng giữ nguyên.
  function comPart() {
    if (!state.ready || !state.coms.length) return '';
    const view = M.comView(M.scope(state.rows, filter(), 'com'), state.coms, state.tier);
    const whole = F.sum(view.map(item => item.total));
    const max = view.reduce((top, item) => (item.total > top ? item.total : top), 0n);
    const what = state.tier == null ? 'Còn phải thu' : state.tiers[state.tier].label;
    const line = item => `<button type="button" class="com-line${item.count ? '' : ' none'}" data-com="${esc(item.key)}" aria-pressed="false" aria-label="Lọc khách: ${esc(item.label)}"${tipAttr([
        item.label, `${what} ${short(item.total)} · ${F.percent(item.total, whole)} tổng`,
        item.late > 0n ? `Quá hạn ${short(item.late)}` : 'Không có nợ quá hạn', `${item.count} khách`,
        item.members.length ? `Gồm: ${item.members.join(', ')}` : '',
        item.key === M.UNSORTED ? 'Sổ chưa gán mặt hàng, hoặc sầu riêng chưa ghi cảng/bộ' : '', 'Bấm để lọc bảng khách'])}>
        <span class="cn${item.tone === 'grey' ? ' grey' : ''}">${esc(item.label)}</span>
        <span class="cbar" aria-hidden="true"><span style="width:${F.barWidth(item.total, max)}%"><i class="in" style="flex:${F.barWidth(item.total - item.late, item.total)} 1 0"></i>${item.late > 0n
          ? `<i class="late" style="flex:${F.barWidth(item.late, item.total)} 1 0"></i>` : ''}</span></span>
        <b class="ct">${item.count ? esc(short(item.total)) : '–'}</b><span class="co">${item.late > 0n ? esc(short(item.late)) : '–'}</span>
        <span class="cc">${ICON.people}${item.count}<span class="sr-only"> khách</span></span></button>`;
    const half = Math.ceil(view.length / 2);
    const col = list => (list.length ? `<div class="com-col"><div class="com-th" aria-hidden="true"><span>Mặt hàng</span><span></span><span>${state.tier == null ? 'Còn phải thu' : 'Nhóm này'}</span><span>Quá hạn</span><span>Khách</span></div>${list.map(line).join('')}</div>` : '');
    return `<section class="com-band" aria-labelledby="h-com"><div class="com-head"><h2 id="h-com">Công nợ theo mặt hàng</h2>${scopeTag('com', 'Mỗi dòng chỉ tính khách trong phạm vi lọc')}
        <span class="legend" aria-hidden="true"><i class="in"></i>Trong hạn<i class="late"></i>Quá hạn</span></div>
      <div class="com-grid">${col(view.slice(0, half))}${col(view.slice(half))}</div></section>`;
  }

  function paintComs() {
    document.querySelectorAll('#dashboard .com-line').forEach(el => {
      const on = el.dataset.com === state.com;
      el.setAttribute('aria-pressed', String(on));
      el.classList.toggle('dim', state.com != null && !on);
    });
  }

  // 3. Bảng khách: hàng chip mức rủi ro, bảng triệu, ô ngày là viên màu theo ngưỡng.
  function listPart() {
    const rule = state.debt?.rule;
    const th = (sort, label, unit, icon, tip) => `<th scope="col" class="r"${sort ? ` data-col="${sort}"` : ''}><button type="button" data-sort="${sort}"${tipAttr(tip)}>${icon ?? ''}<span${sort === 'overdue' ? ' id="col-first"' : ''}>${label}</span> <small>${unit}</small></button></th>`;
    const head = rule ? `<thead><tr><th scope="col">Khách</th><th scope="col" class="bar-h">Theo hạn trả</th>
        ${th('overdue', 'Quá hạn', 'tr', null, ['Triệu đồng', 'Bấm để xếp'])}${th('total', 'Còn nợ', 'tr', null, ['Triệu đồng', 'Bấm để xếp'])}
        ${th('pay', 'Trả', 'ngày', ICON.cash, ['Số ngày từ lần khách trả gần nhất', `Đỏ khi quá ${rule.no_pay_days} ngày hoặc chưa trả lần nào · bấm để xếp`])}
        ${th('trip', 'Đi hàng', 'ngày', ICON.truck, ['Số ngày từ chuyến gần nhất', `Đỏ khi quá ${rule.no_trip_days} ngày hoặc chưa có chuyến · bấm để xếp`])}
        <th scope="col" class="go"><span class="sr-only">Mở</span></th></tr></thead>` : '';
    return `<section class="debtors" aria-labelledby="h-list"><div class="list-head"><h2 id="h-list">Khách cần đòi trước</h2>
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
    // Lọc chéo (DASH-08): số khách và tiền tính trong phạm vi lọc hạn trả + mặt hàng; lọc hạn trả thì tiền là tiền nhóm đó.
    const groups = state.ready ? M.riskView(M.scope(state.rows, filter(), 'risk'), state.tier)
      : state.rk.groups.map(group => ({ ...group, amount: group.overdue }));
    const what = state.tier == null ? 'Tiền quá hạn' : state.tiers[state.tier].label;
    const showAmt = group => group.count > 0 && (state.tier != null ? group.amount !== 0n : group.key !== 'ok');
    const chip = group => `<button type="button" class="rchip r-${group.key}" data-risk="${group.key}" aria-pressed="${state.risk === group.key}"${off}${tipAttr([
      `${group.label}: ${group.count} khách`, tips[group.key], showAmt(group) ? `${what} ${short(group.amount)}` : '', 'Bấm để lọc bảng'])}>
        <i class="rdot" aria-hidden="true"></i><span class="rl">${esc(group.label)}</span><span class="n">${ICON.people}${group.count}<span class="sr-only"> khách</span></span>${showAmt(group)
          ? `<span class="amt">${esc(short(group.amount))}</span>` : ''}</button>`;
    const tier = state.tier == null ? '' : `<button type="button" class="rchip tier-x" data-clear="tier" aria-label="Bỏ lọc ${esc(state.tiers[state.tier].label)}"${tipAttr([`Đang lọc: ${state.tiers[state.tier].label} (${state.tiers[state.tier].span})`, 'Bấm để bỏ lọc'])}>
        <i class="sw t${state.tier}" aria-hidden="true"></i>${esc(state.tiers[state.tier].tile)}${ICON.close}</button>`;
    // Đang lọc mặt hàng (bấm dòng ở khối Công nợ theo mặt hàng hoặc link ?mh=): chip bỏ lọc cùng hàng, như chip hạn trả.
    const com = state.com == null ? '' : `<button type="button" class="rchip tier-x com-x" data-clear="com" aria-label="Bỏ lọc mặt hàng ${esc(state.com)}"${tipAttr([`Đang lọc mặt hàng: ${state.com}`, 'Bấm để bỏ lọc'])}>
        ${esc(state.com)}${ICON.close}</button>`;
    node.innerHTML = `<button type="button" class="rchip all" data-risk="" aria-pressed="${state.risk == null}"${off}>Tất cả</button>${groups.map(chip).join('')}${tier}${com}`;
  }

  function paintList() {
    const rule = state.debt?.rule;
    const empty = $('list-empty');
    $('list-note').hidden = !state.rows || state.ready;
    $('list-note').textContent = 'Số từng khách chưa khớp tổng; xem chi tiết ở Công nợ theo tháng.';
    if (!state.rows) {
      $('list').innerHTML = '';
      $('list-more').innerHTML = '';
      empty.hidden = false;
      empty.textContent = 'Chưa tải được danh sách khách. Bấm Làm mới để thử lại.';
      return;
    }
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

  // Lọc chéo (DASH-08): mỗi lần đổi lọc vẽ lại dải đầu, thẻ tháng và khối mặt hàng theo phạm vi mới; nút đang được focus
  // (ô hạn trả, dòng mặt hàng, chip) được focus lại sau khi vẽ để người dùng bàn phím không mất chỗ.
  function repaintBlocks() {
    const focused = document.activeElement?.closest?.('#dashboard [data-tier], #dashboard [data-com], #dashboard [data-risk], #dashboard [data-clear]');
    const key = focused ? ['data-tier', 'data-com', 'data-risk', 'data-clear'].map(name => [name, focused.getAttribute(name)]).find(([, value]) => value != null) : null;
    const tag = focused?.tagName;
    root.querySelector('.owe').innerHTML = owePart(state.data, state.debt);
    root.querySelector('.month-card').innerHTML = monthPart(state.data, state.debt);
    const band = root.querySelector('.com-band');
    if (band) band.outerHTML = comPart();
    return () => {
      if (!key) return;
      const again = [...root.querySelectorAll(`[${key[0]}]`)].find(el => el.getAttribute(key[0]) === key[1] && el.tagName === tag);
      again?.focus();
    };
  }

  function paint() { const refocus = repaintBlocks(); paintTiers(); paintComs(); paintChips(); paintList(); refocus(); }

  function render(data, debt, customers = []) {
    state.names = shortLabels(customers);
    root.innerHTML = `<section class="strip" aria-labelledby="h-owe"><div class="owe"></div>
      <div class="month-card" role="group" aria-labelledby="h-month"></div></section>${comPart()}${listPart()}`;
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
    if (event.target.closest('[data-clear="com"]')) { state.com = null; writeUrl(); paint(); return; }
    const com = event.target.closest('[data-com]');
    if (com) { state.com = state.com === com.dataset.com ? null : com.dataset.com; writeUrl(); paint(); return; }
    const sort = event.target.closest('[data-sort]');
    if (sort) { state.sort = sort.dataset.sort; writeUrl(); paintList(); return; }
    if (event.target.closest('[data-more]')) { state.all = true; paintList(); return; }
    // Bấm chỗ khác trên dòng khách cũng mở trang khách như bấm tên.
    const line = event.target.closest('#list tr[data-id]');
    if (line && !event.target.closest('a')) location.href = pageHref(Number(line.dataset.id));
  });

  globalThis.DataTip.mount('.tq-page');
  window.addEventListener('popstate', () => { readUrl(); if (state.data) { dropStale(); paint(); } });

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
      globalThis.AppNav?.setCustomers(customers);
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
  setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
