(() => {
  'use strict';
  // BANG-THU-01, BANG-THU-02: tiền về theo ngày, gom mọi sổ, chỉ xem, năm cách xem. Không lọc thì số tháng là số của get_receipt_book;
  // lọc, gom nhóm và thanh tỷ lệ tính ở bang-thu-model.js, file này chỉ định dạng (ARCH-03).
  const F = CongNoFormat;
  const M = BangThuModel;
  const root = document.getElementById('bang-thu');
  const $ = id => document.getElementById(id);
  const { esc, dateText, full, monthTag, monthTitle, monthLabel } = F;
  const number = value => F.toBig(value).toLocaleString('vi-VN');
  const short = value => F.short(value, 'tr');
  const tipAttr = lines => ` data-tip="${esc(lines.filter(Boolean).join('\n'))}"`;
  const svg = body => `<svg viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
  const ICON = {
    prev: svg('<path d="M15 6l-6 6 6 6"/>'),
    next: svg('<path d="M9 6l6 6-6 6"/>'),
    people: svg('<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6"/>'),
    receipt: svg('<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>'),
    sheet: svg('<path d="M5 3h10l4 4v14H5z"/><path d="M15 3v4h4M9 13h6M9 17h6"/>'),
    clock: svg('<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 2h6"/>'),
    calendar: svg('<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>'),
    box: svg('<path d="M3 8l9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5M12 13v8"/>'),
    bars: svg('<path d="M4 20V10M10 20V4M16 20v-8M3 20h18"/>'),
    funnel: svg('<path d="M4 5h16l-6 8v6l-4-2v-4z"/>'),
    swap: svg('<path d="M4 8h13l-3-3M20 16H7l3 3"/>'),
    ban: svg('<circle cx="12" cy="12" r="9"/><path d="M6 6l12 12"/>'),
    info: svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/>'),
  };
  const PLAIN_METHOD = 'THU TIỀN';
  const VIEWS = [
    { id: 'ngay', label: 'Theo ngày', icon: ICON.calendar, tip: 'Ngày nào thu bao nhiêu, ai trả' },
    { id: 'khach', label: 'Theo khách', icon: ICON.people, tip: 'Cả tháng ai trả bao nhiêu' },
    { id: 'mat-hang', label: 'Theo mặt hàng', icon: ICON.box, tip: 'Mặt hàng nào thu được bao nhiêu' },
    { id: 'thang-no', label: 'Theo tháng nợ', icon: ICON.receipt, tip: 'Tiền về tháng này trừ vào nợ tháng nào' },
    { id: '12-thang', label: '12 tháng', icon: ICON.bars, tip: 'Tiền về từng tháng' },
  ];
  const DEFAULT_VIEW = 'ngay';
  const YEAR_VIEW = '12-thang';

  const query = new URLSearchParams(location.search);
  const state = {
    month: /^\d{4}-(0[1-9]|1[0-2])$/.test(query.get('month') ?? '') ? query.get('month') : null,
    view: VIEWS.some(view => view.id === query.get('xem')) ? query.get('xem') : DEFAULT_VIEW,
    com: query.get('mh') || null,
    book: null, inbox: null, customers: null, labels: null, coms: null, options: [], showVoided: false, painted: null,
  };
  let turn = 0;

  const json = async url => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw Error(url);
    return response.json();
  };
  const monthKey = iso => String(iso ?? '').slice(0, 7);
  const dayMonth = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  const count = (n, what = 'phiếu') => `${n.toLocaleString('vi-VN')} ${what}`;
  const ledgerHref = (id, month) => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}&amp;month=${esc(monthKey(month))}`;
  // Bộ lọc chỉ có tác dụng khi đã biết mặt hàng của sổ và không ở tab 12 tháng (dữ liệu tháng chỉ có tổng).
  const activeCom = () => (state.coms && state.view !== YEAR_VIEW ? state.com : null);

  // Tên sổ tách hai phần: tên đậm, mặt hàng nhỏ bên cạnh. Sổ trùng tên giữ " · sổ <id>" của customerLabels để phân biệt.
  function whoOf(id, fallback) {
    const row = state.customers?.get(String(id));
    const name = row ? row.display_name ?? row.name : fallback;
    const label = state.labels?.get(String(id)) ?? name;
    return { name, label, extra: label.startsWith(`${name} · `) ? label.slice(name.length + 3) : '' };
  }
  function whoCell(id, fallback, month, { hideCommodity = false } = {}) {
    const { name, label, extra } = whoOf(id, fallback);
    const shown = hideCommodity ? /(?:^| · )(sổ \d+)$/.exec(extra)?.[1] ?? '' : extra;
    return `<td class="who"><a class="row-link" href="${ledgerHref(id, month)}" title="Mở sổ ${esc(label)}, tháng ${esc(monthLabel(month))}"><span class="nm">${esc(name)}</span>${shown ? ` <small>${esc(shown)}</small>` : ''}</a></td>`;
  }
  const DASH = '<span class="dash">—</span>';
  const moneyOr = (has, value) => (has ? esc(number(value)) : DASH);
  const shareBar = (pct, head = false) => (pct > 0 ? `<div class="share${head ? ' head' : ''}" aria-hidden="true" style="width:${pct}%"></div>` : '');
  const goCell = `<td class="go" aria-hidden="true">${ICON.next}</td>`;
  const goHead = '<th scope="col" class="c-go"><span class="sr-only">Mở sổ</span></th>';

  // Ngày trước ngày `iso`, tính theo lịch, không phụ thuộc múi giờ máy.
  function dayBefore(iso) {
    const [year, month, day] = iso.split('-').map(Number);
    return new Date(Date.UTC(year, month - 1, day - 1)).toISOString().slice(0, 10);
  }
  function dayLabel(iso, asOf) {
    if (iso === asOf) return `Hôm nay ${dayMonth(iso)}`;
    if (iso === dayBefore(asOf)) return `Hôm qua ${dayMonth(iso)}`;
    return dayMonth(iso);
  }

  // Cột Trừ nợ. Phiếu web: các tháng đang được trừ. Dòng Sheet không có phân bổ riêng: tháng của khối ghi nó.
  function debtCell(row, year) {
    if (row.source === 'sheet') {
      const tag = monthTag(row.book_month, year);
      return `<td class="debt" title="Ghi ở khối ${esc(monthLabel(row.book_month))} trên Sheet">${esc(tag)}</td>`;
    }
    const lines = row.allocations ?? [];
    if (!lines.length) return '<td class="debt">—</td>';
    const seen = new Set();
    const parts = [];
    for (const line of lines) {
      const text = line.kind === 'advance' ? 'ứng trước' : monthTag(line.month, year);
      if (!seen.has(text)) { seen.add(text); parts.push(text); }
    }
    const title = lines.map(line => `${line.kind === 'advance' ? 'Ứng trước' : `T${monthLabel(line.month)}`} ${number(line.amount_vnd)}`).join(' · ');
    return `<td class="debt" title="${esc(title)}">${esc(parts.join(', '))}</td>`;
  }
  function noteText(row) {
    const method = row.method && row.method !== PLAIN_METHOD ? row.method : '';
    return [method, row.note ?? ''].filter(Boolean).join(' · ');
  }
  function receiptRow(row, year) {
    const note = noteText(row);
    return `<tr class="pay">${whoCell(row.customer_id, row.name, row.book_month)}<td class="num amt">${esc(number(row.amount_vnd))}</td>`
      + `<td class="note"${note ? ` title="${esc(note)}"` : ''}>${esc(note)}</td>${debtCell(row, year)}${goCell}</tr>`;
  }

  // ---- Theo ngày ----
  function byDayTable(scoped, book, year) {
    const head = `<thead><tr><th scope="col" class="c-who">Khách</th><th scope="col" class="num c-amt" title="Đồng, chính xác tới từng đồng">Số tiền <small>đ</small></th>`
      + `<th scope="col" class="c-note">Ghi chú</th><th scope="col" class="c-debt" title="Tháng nợ mà khoản này trừ vào">Trừ nợ</th>${goHead}</tr></thead>`;
    const days = scoped.days.map(day => `<tbody class="day"><tr class="group-head" id="ngay-${Number(day.date.slice(8, 10))}"><th scope="rowgroup">${esc(dayLabel(day.date, book.as_of))} <small>${esc(count(day.count))}</small></th>`
      + `<td class="num">${esc(number(day.total_vnd))}</td><td colspan="3"></td></tr>${day.rows.map(row => receiptRow(row, year)).join('')}</tbody>`).join('');
    const undated = scoped.undated.length ? `<tbody class="day undated"><tr class="group-head undated-head" id="khong-ro-ngay"><th scope="rowgroup">Không rõ ngày thu <small>${esc(count(scoped.undated.length))}</small></th>`
      + `<td class="num">${esc(number(scoped.summary.undated_vnd))}</td><td colspan="3" class="hint">chưa cộng vào tổng tháng</td></tr>${scoped.undated.map(row => receiptRow(row, year)).join('')}</tbody>` : '';
    return `<table class="thu by-day">${head}${days}${undated}</table>`;
  }

  // ---- Theo khách, Theo mặt hàng, Theo tháng nợ: cùng bộ cột ----
  function groupedHead(first, showUndated) {
    return `<thead><tr><th scope="col" class="c-who">${esc(first)}</th><th scope="col" class="c-share">Phần trong tháng</th>`
      + `<th scope="col" class="num c-amt" title="Đồng, tổng khoản có ngày thu trong tháng">Đã trả <small>đ</small></th>`
      + `<th scope="col" class="num c-count" title="Số phiếu có ngày thu; phiếu chia nhiều tháng nợ tính ở mỗi tháng">Số lần</th>`
      + `${showUndated ? '<th scope="col" class="num c-und" title="Đồng, chưa cộng vào Đã trả">Không rõ ngày <small>đ</small></th>' : ''}`
      + `<th scope="col" class="c-last">Trả gần nhất</th>${goHead}</tr></thead>`;
  }
  function customerLine(row, showUndated, { inGroup = false, hideCommodity = false } = {}) {
    return `<tr class="pay${inGroup ? ' in-group' : ''}">${whoCell(row.id, row.name, row.month, { hideCommodity })}`
      + `<td class="td-share">${shareBar(row.pct)}</td>`
      + `<td class="num amt">${moneyOr(row.count, row.total)}</td><td class="num td-count">${row.count || DASH}</td>`
      + `${showUndated ? `<td class="num und-amt">${moneyOr(row.undatedCount, row.undated)}</td>` : ''}`
      + `<td class="when">${row.lastDate ? esc(dateText(row.lastDate)) : DASH}</td>${goCell}</tr>`;
  }
  function groupHead(group, label, tip, showUndated) {
    return `<tr class="group-head"${tip ? ` title="${esc(tip)}"` : ''}><th scope="rowgroup">${esc(label)} <small>${esc(count(group.rows.length, 'khách'))}</small></th>`
      + `<td class="td-share">${shareBar(group.pct, true)}</td>`
      + `<td class="num">${moneyOr(group.count, group.total)}</td><td class="num td-count">${group.count || DASH}</td>`
      + `${showUndated ? `<td class="num">${moneyOr(group.undatedCount, group.undated)}</td>` : ''}<td colspan="2"></td></tr>`;
  }

  function byCustomerTable(scoped) {
    const rows = M.byCustomer(scoped);
    const showUndated = rows.some(row => row.undatedCount > 0);
    return `<table class="thu by-customer">${groupedHead('Khách', showUndated)}<tbody>${rows.map(row => customerLine(row, showUndated)).join('')}</tbody></table>`;
  }
  function byCommodityTable(scoped) {
    const groups = M.byCommodity(scoped, state.coms);
    const showUndated = groups.some(group => group.undatedCount > 0);
    const body = groups.map(group => `<tbody class="group">${groupHead(group, group.key, '', showUndated)}${group.rows.map(row => customerLine(row, showUndated, { inGroup: true, hideCommodity: true })).join('')}</tbody>`).join('');
    return `<table class="thu by-commodity">${groupedHead('Mặt hàng · khách', showUndated)}${body}</table>`;
  }
  function debtGroupLabel(group, year) {
    if (group.kind === 'advance') return { label: 'Ứng trước', tip: 'Phần tiền vượt nợ, còn nằm trong sổ khách' };
    if (group.kind === 'none') return { label: 'Chưa phân bổ', tip: 'Phần tiền chưa trừ vào tháng nợ nào' };
    return { label: `Nợ ${monthTag(group.month, year)}`, tip: `Tiền về trong tháng này trừ vào nợ ${monthLabel(group.month)}` };
  }
  function byDebtTable(scoped, year) {
    const groups = M.byDebtMonth(scoped);
    const showUndated = groups.some(group => group.undatedCount > 0);
    const body = groups.map(group => {
      const { label, tip } = debtGroupLabel(group, year);
      return `<tbody class="group">${groupHead(group, label, tip, showUndated)}${group.rows.map(row => customerLine(row, showUndated, { inGroup: true })).join('')}</tbody>`;
    }).join('');
    return `<table class="thu by-debt">${groupedHead('Tháng nợ · khách', showUndated)}${body}</table>`;
  }

  // ---- 12 tháng ----
  function yearTable(book) {
    const filter = state.com ? `&amp;mh=${esc(encodeURIComponent(state.com))}` : '';
    const rows = M.lastYear(book).map(row => {
      const tag = `T${monthLabel(row.month)}`;
      const current = row.month === book.month;
      const name = row.has ? `<a class="row-link" href="?month=${esc(monthKey(row.month))}${filter}" title="Xem ${esc(monthTitle(row.month).toLowerCase())} theo ngày"><span class="nm">${esc(tag)}</span></a>`
        : `<span class="nm none" title="Tháng này không có phiếu thu">${esc(tag)}</span>`;
      const bars = `${row.pct > 0 ? `<i style="width:${row.pct}%"></i>` : ''}${row.undatedPct > 0 ? `<i class="u" style="width:${row.undatedPct}%"></i>` : ''}`;
      return `<tr class="${row.has ? 'pay' : 'idle'}${current ? ' current' : ''}"${current ? ' aria-current="true"' : ''}><td class="who">${name}</td>`
        + `<td><div class="split" aria-hidden="true">${bars}</div></td>`
        + `<td class="num amt">${moneyOr(row.count, row.total)}</td><td class="num und-amt">${moneyOr(row.undatedCount, row.undated)}</td>`
        + `<td class="num">${row.count || DASH}</td>${row.has ? goCell : '<td class="go"></td>'}</tr>`;
    }).join('');
    return `<table class="thu by-year"><thead><tr><th scope="col" class="c-month">Tháng</th><th scope="col" title="Xanh: có ngày thu trong tháng · vàng: không rõ ngày, tính ở tháng ghi trên Sheet">Tiền về</th>`
      + `<th scope="col" class="num c-amt" title="Đồng, tổng khoản có ngày thu trong tháng">Theo ngày thu <small>đ</small></th><th scope="col" class="num c-und" title="Đồng, nằm ở tháng ghi trên Sheet">Không rõ ngày <small>đ</small></th>`
      + `<th scope="col" class="num c-count" title="Số phiếu có ngày thu trong tháng">Số phiếu</th><th scope="col" class="c-go"><span class="sr-only">Mở tháng</span></th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  // ---- Khối tiền về ----
  function pendingPill(pending) {
    if (!pending) return '';
    if (pending === 'computing') {
      return `<span class="pill warn" id="pending" tabindex="0"${tipAttr(['Đang kiểm phiếu thu trên Sheet chờ ghi', 'Máy chủ vừa khởi động, mất vài phút', 'Số ở đây có thể còn thiếu'])}>${ICON.clock}Đang kiểm Sheet</span>`;
    }
    if (pending === 'unknown') {
      return `<span class="pill warn" id="pending" tabindex="0"${tipAttr(['Chưa kiểm được phiếu thu trên Sheet chờ ghi', 'Số ở đây có thể còn thiếu'])}>${ICON.sheet}Chưa kiểm được Sheet</span>`;
    }
    return `<a class="pill warn" id="pending" href="/viec-can-lam.html"${tipAttr([`Còn ${count(pending.count)} trên Sheet chưa ghi vào web`, `${full(pending.amount)} · số ở đây có thể còn thiếu`, 'Bấm để mở Việc cần làm'])}>${ICON.sheet}${pending.count} · ${esc(short(pending.amount))}<span class="sr-only"> phiếu trên Sheet chưa ghi</span></a>`;
  }
  function stripPart(scoped, book) {
    const mm = book.month.slice(5, 7);
    const cells = M.dayStrip(scoped, book).map(cell => {
      const name = `${String(cell.day).padStart(2, '0')}/${mm}`;
      const look = `${cell.today ? ' is-today' : ''}${cell.future ? ' is-future' : ''}`;
      const label = cell.day === 1 || cell.day % 5 === 0 || cell.today ? cell.day : '';
      const mark = `<span class="lab">${label}</span>`;
      if (cell.total == null) return `<div class="${look.trim()}"${tipAttr([name, cell.future ? 'Chưa tới' : 'Không có phiếu'])}>${mark}</div>`;
      const text = `${name}: ${full(cell.total)} · ${count(cell.count)}`;
      return `<a class="${look.trim()}" href="#ngay-${cell.day}" aria-label="${esc(text)}"${tipAttr([name, `${full(cell.total)} · ${count(cell.count)}`, 'Bấm để tới ngày này'])}><span class="bar" style="--h:${cell.pct}"></span>${mark}</a>`;
    });
    return `<div class="day-strip" id="day-strip" style="--days:${cells.length}">${cells.join('')}</div>`;
  }
  function bandPart(scoped, book, pending) {
    const s = scoped.summary;
    const com = activeCom();
    const hasMoney = F.toBig(s.total_vnd) !== 0n;
    const year = book.month.slice(0, 4);
    const label = `Thu tháng ${Number(book.month.slice(5, 7))}${year === book.as_of.slice(0, 4) ? '' : `/${year}`}${com ? ` · ${com}` : ''}`;
    const counts = s.count ? `<span class="pill" id="pill-customers" tabindex="0"${tipAttr([`${count(s.customers, 'khách')} trả trong tháng`])}>${ICON.people}${s.customers}<span class="sr-only"> khách</span></span>`
      + `<span class="pill" id="pill-receipts" tabindex="0"${tipAttr([`${count(s.count)} có ngày thu trong tháng`])}>${ICON.receipt}${s.count}<span class="sr-only"> phiếu</span></span>` : '';
    const undated = s.undated_count ? `<a class="pill undated" id="fig-undated" href="#khong-ro-ngay"${tipAttr([`${count(s.undated_count)} không rõ ngày thu`, `${full(s.undated_vnd)} · chưa cộng vào tổng tháng`, 'Sheet không ghi ngày hoặc ngày vô lý', 'Bấm để xem'])}>Không rõ ngày ${esc(short(s.undated_vnd))}</a>` : '';
    const strip = state.view === DEFAULT_VIEW && (scoped.days.length || scoped.undated.length) ? stripPart(scoped, book) : '';
    const today = book.month === book.today_month ? `<div class="today-card" id="fig-today"><span class="lbl">Hôm nay ${esc(dayMonth(book.as_of))}</span>`
      + (s.today_count ? `<b tabindex="0"${tipAttr([`Hôm nay ${dayMonth(book.as_of)}`, full(s.today_vnd)])}>${esc(short(s.today_vnd))}</b><small>${ICON.receipt}${esc(count(s.today_count))}</small>` : '<span class="none">Chưa có phiếu</span>')
      + '</div>' : '';
    return `<section class="band" aria-label="Tiền về trong tháng"><div class="band-main" id="fig-month"><span class="lbl">${esc(label)}</span><div class="band-row">`
      + `<b class="big-money${hasMoney ? '' : ' zero'}" tabindex="0"${tipAttr([label, full(s.total_vnd)])}>${esc(short(s.total_vnd))}</b>${counts}${pendingPill(pending)}${undated}</div>${strip}</div>${today}</section>`;
  }

  // ---- Hàng tab và bộ lọc ----
  function barPart() {
    const views = VIEWS.map(view => `<button type="button" class="view" id="view-${view.id}" data-view="${view.id}" aria-pressed="${state.view === view.id}"${tipAttr([view.label, view.tip])}>${view.icon}${esc(view.label)}</button>`).join('');
    const filter = state.coms && state.view !== YEAR_VIEW ? `<label class="com-pick" id="com-pick">${ICON.funnel}<span class="sr-only">Mặt hàng</span><select id="com-filter" aria-label="Lọc theo mặt hàng">`
      + `<option value="">Mọi mặt hàng</option>${state.options.map(key => `<option value="${esc(key)}"${key === state.com ? ' selected' : ''}>${esc(key)}</option>`).join('')}</select></label>` : '';
    return `<div class="list-bar"><div class="views" role="group" aria-label="Cách xem">${views}</div>${filter}</div>`;
  }

  // ---- Chân bảng ----
  const SHEET_NOTE = 'Sheet ghi khoản thu ở tháng nợ, bảng này xếp theo ngày tiền về, nên tổng tháng có thể khác "Đã thu" của tháng đó trong sổ.';
  function footPart(scoped) {
    if (state.view === YEAR_VIEW) return `<div class="foot"><p class="line" id="sheet-note">${ICON.info}<span>${esc(SHEET_NOTE)}</span></p></div>`;
    const offsets = scoped.offsets.length ? `<div id="offsets"><p class="line" title="Cấn trừ giữa hai sổ không phải tiền mới vào, không cộng vào bảng">${ICON.swap}<span>Cấn trừ giữa hai sổ, không cộng vào bảng</span></p><ul>`
      + scoped.offsets.map(row => {
        const from = whoOf(row.source_customer_id, row.source_name).label;
        const to = whoOf(row.target_customer_id, row.target_name).label;
        return `<li>${esc(dateText(row.date))} · <a href="${ledgerHref(row.source_customer_id, row.date)}">${esc(from)}</a> sang <a href="${ledgerHref(row.target_customer_id, row.date)}">${esc(to)}</a> · <span class="money">${esc(number(row.amount_vnd))}</span></li>`;
      }).join('')
      + '</ul></div>' : '';
    const voided = scoped.voided.length ? `<div id="voided"><p class="line">${ICON.ban}<span>${esc(count(scoped.voided.length))} đã hủy, không tính tiền</span><button type="button" class="link" id="void-toggle" aria-expanded="${state.showVoided}">${state.showVoided ? 'Ẩn' : 'Xem'}</button></p>`
      + (state.showVoided ? `<ul>${scoped.voided.map(row => `<li><s class="money">${esc(number(row.amount_vnd))}</s> · <a href="${ledgerHref(row.customer_id, row.date)}">${esc(whoOf(row.customer_id, row.name).label)}</a> · ${esc(dateText(row.date))} · hủy ${esc(dateText(row.voided_on))}${row.void_reason ? ` · ${esc(row.void_reason)}` : ''}</li>`).join('')}</ul>` : '')
      + '</div>' : '';
    const hasRows = scoped.days.length || scoped.undated.length;
    const moves = state.view === 'thang-no' && hasRows ? `<p class="line" id="realloc-note">${ICON.info}<span>Khi sổ được điều chỉnh, phiếu web được phân bổ lại theo nợ cũ trước, nên số ở đây có thể đổi.</span></p>` : '';
    const note = scoped.summary.has_sheet ? `<p class="line" id="sheet-note">${ICON.info}<span>${esc(SHEET_NOTE)}</span></p>` : '';
    const body = offsets + voided + moves + note;
    return body ? `<div class="foot">${body}</div>` : '';
  }

  function listBody(scoped, book) {
    const year = Number(book.month.slice(0, 4));
    if (state.view === YEAR_VIEW) return yearTable(book);
    if (state.view === 'mat-hang' && !state.coms) return '<p class="empty" id="no-commodity">Chưa tải được danh sách mặt hàng. Bấm Làm mới để thử lại.</p>';
    if (!scoped.days.length && !scoped.undated.length) {
      const com = activeCom();
      return `<p class="empty" id="empty">${esc(com ? `Không có phiếu ${com} trong ${monthTitle(book.month).toLowerCase()}.` : `${monthTitle(book.month)} chưa có phiếu thu.`)}</p>`;
    }
    if (state.view === 'khach') return byCustomerTable(scoped);
    if (state.view === 'mat-hang') return byCommodityTable(scoped);
    if (state.view === 'thang-no') return byDebtTable(scoped, year);
    return byDayTable(scoped, book, year);
  }

  function monthOptions(book) {
    const months = book.months.map(item => item.month);
    if (!months.includes(book.month)) months.push(book.month);
    months.sort().reverse();
    const at = months.indexOf(book.month);
    return { newer: months[at - 1], older: months[at + 1],
      options: months.map(month => `<option value="${esc(monthKey(month))}"${month === book.month ? ' selected' : ''}>${esc(monthTitle(month))}</option>`).join('') };
  }
  function paintMonthNav(book) {
    const { newer, older, options } = monthOptions(book);
    const step = (id, label, icon, target, edge) => `<button type="button" class="btn icon-btn step" id="${id}" aria-label="${label}"${target ? ` data-month="${esc(monthKey(target))}"${tipAttr([monthTitle(target)])}` : ` disabled${tipAttr([edge])}`}>${icon}</button>`;
    $('month-nav').innerHTML = `${step('month-older', 'Tháng trước', ICON.prev, older, 'Không còn tháng cũ hơn')}<select id="month-pick" aria-label="Chọn tháng">${options}</select>${step('month-newer', 'Tháng sau', ICON.next, newer, 'Đang ở tháng mới nhất')}`;
  }

  function paint() {
    const book = state.book;
    if (!book) return;
    const com = activeCom();
    const pending = M.pending(state.inbox, com, state.coms);
    const signature = JSON.stringify([book, pending, state.view, com, state.options, state.showVoided, state.labels ? [...state.labels] : null]);
    if (signature === state.painted) return;
    state.painted = signature;
    const focused = document.activeElement?.id;
    const scoped = M.scope(book, com, state.coms);
    paintMonthNav(book);
    root.innerHTML = `${bandPart(scoped, book, pending)}<section class="list" aria-label="Danh sách phiếu thu">${barPart()}${listBody(scoped, book)}${footPart(scoped)}</section>`;
    // Vẽ lại không làm mất tiêu điểm; nút đổi tháng vừa bị khóa (hết tháng) thì chuyển sang nút còn lại.
    const again = focused ? $(focused) : null;
    if (again?.disabled) $(focused === 'month-older' ? 'month-newer' : 'month-older')?.focus();
    else again?.focus();
  }

  // Giữ tháng, tab và bộ lọc trên địa chỉ để bấm Back từ sổ về đúng chỗ và gửi link được.
  function syncAddress() {
    const params = new URLSearchParams();
    if (state.month) params.set('month', state.month);
    if (state.view !== DEFAULT_VIEW) params.set('xem', state.view);
    if (state.com) params.set('mh', state.com);
    const text = params.toString();
    history.replaceState(null, '', `${location.pathname}${text ? `?${text}` : ''}`);
  }

  function markUpdated(asOf) {
    const seconds = new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });
    const clock = $('as-of');
    clock.textContent = seconds.slice(0, 5);
    clock.dataset.tip = [`Số liệu đến ${dateText(asOf)}`, `Cập nhật ${seconds} · tự tải mỗi 60 giây`].join('\n');
    $('updated-at').textContent = `Cập nhật ${seconds} · tự tải mỗi 60 giây`;
  }

  function useCustomers(customers) {
    state.customers = new Map(customers.map(row => [String(row.id), row]));
    state.labels = F.customerLabels(customers);
    state.coms = M.commodityMap(customers);
    state.options = M.commodityOptions(state.coms);
    // Link cũ trỏ tới mặt hàng không còn thì bỏ lọc.
    if (state.com && !state.options.includes(state.com)) { state.com = null; syncAddress(); }
    globalThis.AppNav?.setCustomers(customers);
  }

  async function load() {
    const mine = ++turn;
    try {
      const [book, customers, inbox] = await Promise.all([
        json(`/api/v7/receipt-book${state.month ? `?month=${state.month}-01` : ''}`),
        state.labels ? null : json('/api/v7/customers').then(body => body.customers ?? []).catch(() => null),
        json('/api/v7/inbox').catch(() => null),
      ]);
      if (mine !== turn) return;   // người dùng vừa đổi tháng: lượt mới hơn sẽ vẽ
      if (customers) useCustomers(customers);
      state.book = book;
      state.inbox = inbox;
      const banner = $('demo-banner');
      banner.hidden = !book.demo && !book.real_copy;
      banner.textContent = book.real_copy ? 'Dữ liệu thật · bản sao cô lập, chưa phải prod' : book.demo ? 'Dữ liệu thử · DỮ LIỆU GIẢ' : '';
      markUpdated(book.as_of);
      paint();
      $('error').hidden = true;
    } catch {
      if (mine !== turn) return;
      const alert = $('error');
      alert.hidden = false;
      alert.innerHTML = `${esc(F.loadError('bảng thu'))}<button type="button" class="btn" id="retry">Thử lại</button>`;
      if (!state.book) root.replaceChildren();
    }
  }

  function showMonth(month) {
    state.month = month;
    state.showVoided = false;
    syncAddress();
    if (state.book) root.querySelector('.list')?.setAttribute('aria-busy', 'true');
    load();
  }

  const page = document.querySelector('main.page');
  page.addEventListener('click', event => {
    const step = event.target.closest('.step');
    if (step?.dataset.month) { showMonth(step.dataset.month); return; }
    const view = event.target.closest('[data-view]');
    if (view) { state.view = view.dataset.view; syncAddress(); paint(); return; }
    if (event.target.closest('#void-toggle')) { state.showVoided = !state.showVoided; paint(); return; }
    // Chip Không rõ ngày ở tab khác: sang Theo ngày rồi mới tới được nhóm đó.
    if (event.target.closest('#fig-undated') && state.view !== DEFAULT_VIEW) {
      event.preventDefault();
      state.view = DEFAULT_VIEW;
      syncAddress();
      paint();
      $('khong-ro-ngay')?.scrollIntoView();
    }
  });
  page.addEventListener('change', event => {
    if (event.target.id === 'month-pick') showMonth(event.target.value);
    if (event.target.id === 'com-filter') { state.com = event.target.value || null; syncAddress(); paint(); }
  });
  $('error').addEventListener('click', event => { if (event.target.id === 'retry') load(); });
  $('refresh-data').addEventListener('click', load);
  globalThis.DataTip.mount('main.page');

  load();
  // Ô chọn đang mở thì không vẽ lại, tránh đóng mất danh sách đang chọn.
  setInterval(() => { if (!document.hidden && !['month-pick', 'com-filter'].includes(document.activeElement?.id)) load(); }, 60_000);
})();
