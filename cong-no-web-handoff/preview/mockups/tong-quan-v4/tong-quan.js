/* Bản xem Tổng quan v4 (DASH-06, ĐỀ XUẤT bố cục): dải đầu giữ như DASH-05; thẻ "Còn phải thu 12 tháng" thay thẻ Thu tháng;
   khối "Nợ quá hạn nằm ở đâu" chia khách theo còn đi hàng × còn trả. Dữ liệu giả ở data.js (triệu đồng); mọi số tính từ đó và
   phải cộng về cùng một tổng trước khi vẽ. Nhãn nhóm hạn trả, tên tháng dùng đúng hàm của Tổng quan thật (DashboardModel). */
(() => {
  'use strict';
  const F = CongNoFormat;
  const M = DashboardModel;
  const D = window.MOCK;
  const R = D.rule;
  const root = document.getElementById('dashboard');
  const vnd = tr => BigInt(tr) * 1000000n;
  const short = value => F.short(value, 'tr');
  const ty = value => `${F.billions(value)} tỷ`;
  const sum = list => list.reduce((total, value) => total + value, 0n);
  const tip = lines => ` data-tip="${F.esc(lines.filter(Boolean).join('\n'))}"`;
  const svg = body => `<svg viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
  const ICON = {
    people: svg('<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6"/>'),
    tag: svg('<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="7.5" r="1.2"/><path d="M14 9l-5 5"/>'),
    funnel: svg('<path d="M4 5h16l-6 8v6l-4-2v-4z"/>'),
    calendar: svg('<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>'),
    next: svg('<path d="M9 6l6 6-6 6"/>'),
  };
  const asOf = D.asOf;
  const year = Number(asOf.slice(0, 4));
  const tag = key => F.monthTag(`${key}-01`, year);
  const dayMonth = iso => `${Number(iso.slice(8, 10))}/${Number(iso.slice(5, 7))}`;
  const labels = M.tierLabels(asOf, R);

  // Bốn tình trạng + Không quá hạn (DASH-06). Chưa trả lần nào tính là không trả; chưa có chuyến tính là không đi hàng.
  const GROUPS = [
    { key: 'ship', label: 'Vẫn đi hàng, không trả', rule: `có chuyến trong ${R.active_trip_days} ngày qua · hơn ${R.no_pay_days} ngày chưa trả`,
      full: `Có chuyến trong ${R.active_trip_days} ngày qua, nhưng hơn ${R.no_pay_days} ngày chưa trả hoặc chưa trả lần nào` },
    { key: 'stop', label: 'Ngừng đi hàng, không trả', rule: `không có chuyến trong ${R.active_trip_days} ngày qua · hơn ${R.no_pay_days} ngày chưa trả`,
      full: `Không có chuyến trong ${R.active_trip_days} ngày qua, và hơn ${R.no_pay_days} ngày chưa trả hoặc chưa trả lần nào` },
    { key: 'old', label: 'Vẫn trả, còn nợ cũ', rule: `có trả trong ${R.no_pay_days} ngày qua · còn nợ quá hạn từ ${R.long_overdue_months} tháng`,
      full: `Có trả trong ${R.no_pay_days} ngày qua, nhưng còn nợ quá hạn từ ${R.long_overdue_months} tháng` },
    { key: 'short', label: 'Vẫn trả, quá hạn ngắn', rule: `có trả trong ${R.no_pay_days} ngày qua · nợ quá hạn dưới ${R.long_overdue_months} tháng`,
      full: `Có trả trong ${R.no_pay_days} ngày qua, nợ quá hạn chưa tới ${R.long_overdue_months} tháng` },
    { key: 'ok', label: 'Không quá hạn', rule: 'không có nợ quá hạn', full: 'Không có nợ quá hạn' },
  ];

  /** Một khách: 5 nhóm hạn trả, quá hạn, nhóm hạn của khoản quá hạn lâu nhất, tình trạng. */
  function derive(c) {
    const tiers = [0n, 0n, 0n, 0n, 0n];
    const months = Object.entries(c.months).sort(([a], [b]) => a.localeCompare(b));
    for (const [key, tr] of months) tiers[M.tierOfMonth(`${key}-01`, asOf, R)] += vnd(tr);
    const total = sum(tiers);
    const overdue = tiers[2] + tiers[3] + tiers[4];
    const longOverdue = tiers[3] + tiers[4];
    const oldest = months.find(([, tr]) => tr > 0)?.[0] ?? null;
    const oldestTier = oldest ? M.tierOfMonth(`${oldest}-01`, asOf, R) : null;
    const unpaid = c.payDays == null || c.payDays > R.no_pay_days;
    const shipping = c.tripDays != null && c.tripDays <= R.active_trip_days;
    const sit = overdue <= 0n ? 'ok' : unpaid ? (shipping ? 'ship' : 'stop') : longOverdue > 0n ? 'old' : 'short';
    return { ...c, tiers, total, overdue, longOverdue, oldest, oldestTier, sit };
  }
  const rows = D.customers.map(derive);
  const receivable = sum(rows.map(row => row.total));
  const tierTotals = [0, 1, 2, 3, 4].map(i => sum(rows.map(row => row.tiers[i])));
  const overdue = tierTotals[2] + tierTotals[3] + tierTotals[4];
  const series = D.months.map(m => ({ ...m, ch: vnd(m.charges), got: vnd(m.received), end: vnd(m.end) }));
  // Kiểm cộng của bản xem: 5 nhóm = còn phải thu = điểm cuối hình 12 tháng; mỗi tháng = cuối tháng trước + phát sinh − đã thu.
  const consistent = sum(tierTotals) === receivable && series.at(-1).end === receivable
    && series.every((m, i) => i === 0 || series[i - 1].end + m.ch - m.got === m.end);
  if (!consistent) throw Error('Dữ liệu giả của bản xem không cộng về cùng tổng.');

  const state = { tier: null, sit: null, com: '', sort: 'overdue', all: new Set() };

  // 1. Dải đầu: như DASH-05 (Còn phải thu, nút đếm, ngoặc Trong hạn / Quá hạn, thanh 5 đoạn, 5 ô).
  function owePart() {
    const count = i => rows.filter(row => row.tiers[i] > 0n).length;
    const tierTip = i => [`${labels[i].label} (${labels[i].span})`, `${short(tierTotals[i])} · ${count(i)} khách · ${F.percent(tierTotals[i], receivable)} còn phải thu`, F.full(tierTotals[i]), 'Bấm để lọc bảng'];
    const inTerm = tierTotals[0] + tierTotals[1];
    const ink = i => (i >= 3 ? 'red' : i === 2 ? 'amber' : '');
    return `<span class="lbl" id="h-owe">Còn phải thu</span>
      <div class="owe-row"><b class="big-money" tabindex="0"${tip(['Còn phải thu', F.full(receivable)])}>${short(receivable)}</b>
        <span class="pill" tabindex="0"${tip([`${rows.length} khách đang nợ`])}>${ICON.people}${rows.length}<span class="sr-only"> khách đang nợ</span></span>
        <a class="pill warn" href="#"${tip([`${D.missingPriceTrips} chuyến chưa có đơn giá`, 'Chưa tính vào số Còn phải thu · bấm để mở Việc cần làm'])}>${ICON.tag}${D.missingPriceTrips}<span class="sr-only"> chuyến chưa giá</span></a></div>
      <div class="brk"><div class="in" style="width:max(${F.barWidth(inTerm, receivable)}%,9.5em)" tabindex="0"${tip(['Trong hạn: chưa quá hạn', `${short(inTerm)} · ${F.percent(inTerm, receivable)} còn phải thu`])}>Trong hạn <strong>${short(inTerm)}</strong></div>
        <div class="late" tabindex="0"${tip(['Quá hạn', `${short(overdue)} · ${F.percent(overdue, receivable)} còn phải thu`])}>Quá hạn <strong>${short(overdue)}</strong></div></div>
      <div class="age-bar">${tierTotals.map((value, i) => (value > 0n ? `<button type="button" class="t${i}" data-tier="${i}" aria-label="Lọc khách: ${F.esc(labels[i].label)}" style="flex:${F.barWidth(value, receivable)} 1 0"${tip(tierTip(i))}></button>` : '')).join('')}</div>
      <div class="tiles">${tierTotals.map((value, i) => `<button type="button" class="tile" data-tier="${i}" aria-pressed="false"${tip(tierTip(i))}>
        <span class="tl"><i class="sw t${i}" aria-hidden="true"></i>${F.esc(labels[i].tile)}</span><b class="${ink(i)}">${short(value)}</b></button>`).join('')}</div>`;
  }

  // 2. Thẻ 12 tháng (thay thẻ Thu tháng): hai hình chồng, mỗi hình một thang — đường Còn phải thu cuối tháng ở trên, cột phát sinh /
  //    đã thu ở dưới (không dùng hai trục trên một hình). Rê hoặc focus một tháng để xem số.
  function trendPart() {
    const LINE_TOP = 6, LINE_H = 32, BAR_H = 34;
    // Toạ độ vẽ (px, % bề rộng) làm tròn một số lẻ; không phải tiền.
    const r1 = n => Math.round(n * 10) / 10;
    const ends = series.map(m => m.end);
    const lo = ends.reduce((a, b) => (b < a ? b : a));
    const hi = ends.reduce((a, b) => (b > a ? b : a));
    const yOf = value => (hi === lo ? LINE_TOP + LINE_H / 2 : LINE_TOP + (1 - Number((value - lo) * 10000n / (hi - lo)) / 10000) * LINE_H);
    const xOf = i => (i + 0.5) / series.length * 100;
    const flowMax = series.reduce((top, m) => [m.ch, m.got].reduce((a, b) => (b > a ? b : a), top), 0n);
    const barH = value => Math.max(value > 0n ? 2 : 0, Math.round(Number(value * 1000n / flowMax) / 1000 * BAR_H));
    const pts = series.map((m, i) => `${r1(xOf(i) * 12)},${r1(yOf(m.end))}`).join(' ');
    const last = series.length - 1;
    const low = ends.indexOf(lo);
    const now = series[last];
    const cols = series.map((m, i) => `<span class="tr-col" tabindex="0"${tip([`${tag(m.month)}${i === last ? ` · đến ${dayMonth(asOf)}` : ''}`,
      `Phát sinh ${short(m.ch)} · Đã thu ${short(m.got)}`, `Còn phải thu cuối tháng ${short(m.end)}`])}>
        <i class="tr-bar ps" style="height:${barH(m.ch)}px"></i><i class="tr-bar thu" style="height:${barH(m.got)}px"></i></span>`).join('');
    const label = `Còn phải thu cuối tháng từ ${short(series[0].end)} (${tag(series[0].month)}) tới ${short(now.end)} (${tag(now.month)}, đến ${dayMonth(asOf)}); thấp nhất ${short(lo)}`;
    return `<div class="tr-head"><h2 id="h-trend">Còn phải thu 12 tháng</h2>
        <span class="tr-legend"><span><i class="tr-sw ps"></i>Phát sinh</span><span><i class="tr-sw thu"></i>Đã thu</span></span></div>
      <div class="tr-plot" role="img" aria-label="${F.esc(label)}">
        <svg class="tr-line" viewBox="0 0 1200 46" preserveAspectRatio="none" aria-hidden="true">
          <polygon class="tr-area" points="${r1(xOf(0) * 12)},44 ${pts} ${r1(xOf(last) * 12)},44"/><polyline class="tr-l" points="${pts}"/></svg>
        <span class="tr-sep" aria-hidden="true"></span>
        <i class="tr-dot" style="left:${xOf(low)}%;top:${r1(yOf(lo))}px" aria-hidden="true"></i>
        <i class="tr-dot" style="left:${xOf(last)}%;top:${r1(yOf(now.end))}px" aria-hidden="true"></i>
        <span class="tr-num" style="left:0;top:${r1(yOf(lo) - 20)}px" aria-hidden="true">${short(lo)}</span>
        <span class="tr-num" style="right:0;top:${r1(yOf(now.end) + 6)}px" aria-hidden="true">${short(now.end)}</span>
        <div class="tr-cols">${cols}</div></div>
      <div class="tr-months" aria-hidden="true">${series.map(m => `<span>T${Number(m.month.slice(5, 7))}</span>`).join('')}</div>
      <p class="tr-now">${tag(now.month)} đến ${dayMonth(asOf)}: đã thu <b>${short(now.got)}</b> · phát sinh <b>${short(now.ch)}</b><a href="#">Bảng thu ›</a></p>`;
  }

  // 3. Nợ quá hạn nằm ở đâu: ô tình trạng (lọc bảng), bảng chia nhóm theo tình trạng, trong nhóm xếp theo cột đang chọn.
  const groupOf = key => GROUPS.find(g => g.key === key);
  function cards() {
    return GROUPS.map(g => {
      const members = rows.filter(row => row.sit === g.key);
      const late = sum(members.map(row => row.overdue));
      const amount = g.key === 'ok' ? '' : `<b class="amt">${ty(late)}</b>`;
      const share = g.key === 'ok' ? '' : `Tiền quá hạn ${ty(late)} · ${F.percent(late, overdue)} tổng quá hạn`;
      return `<button type="button" class="sit s-${g.key}" data-sit="${g.key}" aria-pressed="${state.sit === g.key}"${tip([`${g.label}: ${members.length} khách`, g.full, share, 'Bấm để lọc bảng, bấm lại để bỏ'])}>
        <span class="sl"><i class="rdot" aria-hidden="true"></i>${g.label}</span>
        <span class="sv"><span class="n">${ICON.people}${members.length}<span class="sr-only"> khách</span></span>${amount}</span></button>`;
    }).join('');
  }
  const days = value => (value == null ? Infinity : value);
  const cmp = (a, b) => (b > a ? 1 : b < a ? -1 : 0);
  function sorted(list) {
    const first = row => (state.tier == null ? row.overdue : row.tiers[state.tier]);
    return [...list].sort((a, b) => (state.sort === 'total' ? cmp(a.total, b.total) : state.sort === 'pay' ? cmp(days(a.payDays), days(b.payDays))
      : state.sort === 'trip' ? cmp(days(a.tripDays), days(b.tripDays)) : cmp(first(a), first(b))) || cmp(a.total, b.total) || a.name.localeCompare(b.name, 'vi'));
  }
  function rowHtml(row) {
    const first = state.tier == null ? row.overdue : row.tiers[state.tier];
    const late = state.tier == null || state.tier >= 2;
    const unpaid = row.sit === 'ship' || row.sit === 'stop';
    const day = (value, hot) => `<span class="days${hot ? ' bad' : ''}">${value == null ? 'chưa' : value}</span>`;
    const age = row.oldestTier != null && row.oldestTier >= 2
      ? `<span class="age${row.sit === 'old' ? ' hot' : ''}"><i class="sw t${row.oldestTier}" aria-hidden="true"></i>${F.esc(labels[row.oldestTier].tile)}</span>` : '<span class="age none">–</span>';
    const oldTip = row.oldest && row.oldestTier >= 2 ? `Quá hạn lâu nhất: nợ ${tag(row.oldest)}, ${labels[row.oldestTier].label.toLowerCase()}` : 'Không có nợ quá hạn';
    return `<tr data-id="${row.id}"${tip([row.name, `${groupOf(row.sit).label} · ${oldTip}`, `Còn nợ ${F.full(row.total)}`, 'Bấm để mở Tình hình'])}>
      <td class="who"><a href="#"><span class="nm">${F.esc(row.name)}</span></a></td>
      <td class="num od${first > 0n ? (late ? ' red' : '') : ' zero'}">${first > 0n ? F.millions(first) : '–'}</td>
      <td class="agec">${age}</td>
      <td class="d">${day(row.payDays, unpaid)}</td>
      <td class="d">${day(row.tripDays, row.sit === 'stop')}</td>
      <td class="num tot">${F.millions(row.total)}</td>
      <td class="go" aria-hidden="true">${ICON.next}</td></tr>`;
  }
  function body() {
    const LIMIT = 5;
    const keep = row => (state.tier == null || row.tiers[state.tier] > 0n) && (!state.com || row.com === state.com);
    const html = GROUPS.filter(g => !state.sit || state.sit === g.key).map(g => {
      const list = sorted(rows.filter(row => row.sit === g.key && keep(row)));
      if (!list.length) return '';
      const shown = state.all.has(g.key) ? list : list.slice(0, LIMIT);
      const more = list.length > shown.length ? `<tr class="grp-more"><td colspan="7"><button type="button" class="btn" data-more="${g.key}">Hiện cả ${list.length} khách</button></td></tr>` : '';
      return `<tbody data-sit="${g.key}"><tr class="grp s-${g.key}"><th colspan="7" scope="rowgroup"><i class="rdot" aria-hidden="true"></i>${g.label}<small>${g.rule}</small></th></tr>
        ${shown.map(rowHtml).join('')}${more}</tbody>`;
    }).join('');
    return html || '<tbody><tr class="grp-more"><td colspan="7" class="empty">Không có khách nào khớp bộ lọc.</td></tr></tbody>';
  }
  function listPart() {
    const coms = [...new Set(rows.map(row => row.com))]
      .map(key => ({ key, total: sum(rows.filter(row => row.com === key).map(row => row.total)) }))
      .sort((a, b) => (a.key === 'Khác') - (b.key === 'Khác') || cmp(a.total, b.total));
    const th = (sort, text, unit) => `<th scope="col" class="r" data-col="${sort}"><button type="button" data-sort="${sort}"><span>${text}</span><small>${unit}</small></button></th>`;
    return `<div class="list-head"><h2 id="h-list">Nợ quá hạn nằm ở đâu</h2>
        <label class="com-pick">${ICON.funnel}<span class="sr-only">Mặt hàng</span><select id="com-filter" aria-label="Lọc theo mặt hàng">
          <option value="">Mọi mặt hàng</option>${coms.map(c => `<option value="${F.esc(c.key)}">${F.esc(c.key)}</option>`).join('')}</select></label>
        <a class="btn icon-btn" href="#" aria-label="Mở Công nợ theo tháng"${tip(['Công nợ theo tháng', 'Soi nợ từng khách theo tháng'])}>${ICON.calendar}</a></div>
      <div class="sit-cards" id="cards" role="group" aria-label="Lọc theo tình trạng khách">${cards()}</div>
      <div class="tbl-wrap"><table class="dtable gtable"><thead><tr><th scope="col" class="who-h">Khách</th>
        ${th('overdue', state.tier == null ? 'Quá hạn' : 'Nhóm này', 'triệu')}<th scope="col" class="age-h">Quá hạn lâu nhất</th>
        ${th('pay', 'Trả gần nhất', 'ngày trước')}${th('trip', 'Đi hàng gần nhất', 'ngày trước')}${th('total', 'Còn nợ', 'triệu')}
        <th scope="col" class="go"><span class="sr-only">Mở</span></th></tr></thead>${body()}</table></div>`;
  }

  // Mặt hàng như Tổng quan: mặt hàng dưới 1% còn phải thu gom "Khác".
  for (const row of rows) {
    const share = sum(rows.filter(item => item.commodity === row.commodity).map(item => item.total));
    row.com = share * 100n < receivable ? 'Khác' : row.commodity;
  }

  function paint() {
    document.querySelectorAll('[data-tier]').forEach(el => {
      const on = Number(el.dataset.tier) === state.tier;
      if (el.classList.contains('tile')) el.setAttribute('aria-pressed', String(on));
      el.classList.toggle('dim', state.tier != null && !on);
    });
    const list = document.getElementById('list-root');
    list.innerHTML = listPart();
    list.querySelector('#com-filter').value = state.com;
    list.querySelectorAll('th[data-col]').forEach(cell => {
      if (cell.dataset.col === state.sort) cell.setAttribute('aria-sort', 'descending'); else cell.removeAttribute('aria-sort');
    });
  }

  root.innerHTML = `<section class="strip" aria-labelledby="h-owe"><div class="owe">${owePart()}</div>
      <div class="trend-card" role="group" aria-labelledby="h-trend">${trendPart()}</div></section>
    <section class="debtors" id="list-root" aria-labelledby="h-list"></section>`;
  paint();

  root.addEventListener('click', event => {
    const tier = event.target.closest('[data-tier]');
    if (tier) { state.tier = state.tier === Number(tier.dataset.tier) ? null : Number(tier.dataset.tier); paint(); return; }
    const sit = event.target.closest('[data-sit]');
    if (sit && sit.tagName === 'BUTTON') { state.sit = state.sit === sit.dataset.sit ? null : sit.dataset.sit; paint(); return; }
    const sort = event.target.closest('[data-sort]');
    if (sort) { state.sort = sort.dataset.sort; paint(); return; }
    const more = event.target.closest('[data-more]');
    if (more) { state.all.add(more.dataset.more); paint(); return; }
    if (event.target.closest('a[href="#"]')) event.preventDefault();
  });
  root.addEventListener('change', event => {
    if (event.target.id !== 'com-filter') return;
    state.com = event.target.value;
    paint();
  });
  globalThis.DataTip.mount('.tq-page');
})();
