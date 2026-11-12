/* Tình hình trang khách: bản đọc để quyết cho sếp (TINH-HINH-01), tương tác theo TUONG-TAC-01. Một màn 1265×560 trả lời nợ bao nhiêu,
 * có đang trả không, còn đi hàng không, nợ tăng hay giảm; không gợi ý việc. Số từ sổ, Tổng quan và dấu hứa trả; dữ liệu phụ đọc khi mở thẻ.
 * Bấm là mở hoặc ghim tại chỗ, không gọi API; chỉ các nút data-go mới sang thẻ Sổ. Trường ctx: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).overview = ctx => {
  'use strict';
  const { root, model, api, escape, monthKey, monthLabel, liveOpenMonth, showTab, showMonth, bookWork, todayIso } = ctx;
  const { toBig, full, short, monthTag, loadError, barWidth } = CongNoFormat;
  const M = TinhHinhModel;
  // Cùng chữ với Tổng quan (DashboardModel.RISK, reasons) để hai nơi gọi một khách như nhau; DASH-05 (4): "Trong hạn" chỉ cho tiền.
  const RISK = { high: 'Rủi ro cao', watch: 'Theo dõi', ok: 'Không quá hạn' };
  const side = { debt: { state: 'idle', read: 'readDebt' }, marks: { state: 'idle', read: 'readMarks' } };
  // Trạng thái bấm của thẻ: giữ qua các lần vẽ lại (nguồn phụ về sau, ghi sổ), không ghi lên địa chỉ.
  const ui = { detail: null, pin: null, open: null, limit: 4 };
  const LIMIT = 4, MORE = 10, PLOT = 112, CHART_H = 136;
  let view = { series: null, counts: null };
  const shown = () => document.body?.dataset.the === 'tinh-hinh';
  const loaded = item => item.state !== 'error' && Object.hasOwn(item, 'data');
  const thisMonth = () => monthKey(ctx.snapshot?.today_month) || liveOpenMonth;
  const tag = key => monthTag(`${key}-01`, Number(thisMonth().slice(0, 4)));
  const shift = (key, by) => {
    const n = Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1 + by;
    return `${Math.floor(n / 12)}-${String(n % 12 + 1).padStart(2, '0')}`;
  };
  const dayMonth = iso => `${Number(iso.slice(8, 10))}/${Number(iso.slice(5, 7))}`;
  const endOf = key => dayMonth(new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)), 0)).toISOString().slice(0, 10));
  const svg = path => `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;
  const CARET = open => svg(open ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6');
  const CLOSE = svg('M6 6l12 12M18 6L6 18');
  const NEXT = svg('M9 6l6 6-6 6');
  // Nhãn đọc màn hình luôn bắt đầu bằng chữ trên nút (WCAG 2.5.3), `more` nói thêm nút mở gì.
  const button = (go, text, more = '', kind = 'ov-go') => `<button type="button" class="${kind}" data-go="${escape(go)}"`
    + `${more ? ` aria-label="${escape(`${text} — ${more}`)}"` : ''}>${escape(text)}</button>`;

  // Đọc nguồn phụ khi thẻ đang mở: lần đầu, khi sổ đổi phiên bản (vừa ghi) hoặc lần đọc đã quá 60 giây; `only` là nút Thử lại.
  function wake(only = null) {
    const version = ctx.snapshot?.version;
    for (const [name, item] of Object.entries(side)) {
      const fresh = item.state !== 'idle' && item.version === version && Date.now() - item.at < 60_000;
      if (item.state === 'loading' || (only ? only !== name : !shown() || fresh)) continue;
      Object.assign(item, { state: 'loading', version });
      api[item.read]().then(data => Object.assign(item, { state: 'ok', data }), () => { item.state = 'error'; })
        .finally(() => { item.at = Date.now(); paint(); });
    }
  }
  // Nguồn phụ về sau hoặc vừa bấm: chỉ vẽ lại khung thẻ Tình hình; tiêu điểm đang ở một nút của thẻ thì về nút cùng việc —
  // nút data-ui, data-go, hoặc nút sang thẻ khác (data-the, nhớ cả thứ tự); nút vừa mất thì về `focusTo`.
  function paint(focusTo = null) {
    const pane = root.querySelector('#the-tinh-hinh');
    if (!pane || !ctx.snapshot) return;
    const active = pane.contains(document.activeElement) ? document.activeElement : null;
    const key = active?.dataset.ui ? `[data-ui="${CSS.escape(active.dataset.ui)}"]` : active?.dataset.go ? `[data-go="${CSS.escape(active.dataset.go)}"]`
      : active?.dataset.the ? `[data-the="${CSS.escape(active.dataset.the)}"]` : null;
    const nth = key ? [...pane.querySelectorAll(key)].indexOf(active) : -1;
    pane.innerHTML = body(ctx.snapshot);
    const again = key ? pane.querySelectorAll(key)[nth] ?? pane.querySelector(key) : null;
    (again ?? (focusTo && active ? pane.querySelector(focusTo) : null))?.focus();
  }

  // ---- Dải đầu: nợ theo hạn, nhãn rủi ro; bấm một phần nợ mở từng tháng ngay bên dưới ----
  function tierRows(key, tiers) {
    const rows = tiers.groups[key];
    const top = rows.reduce((max, row) => (row.amount > max ? row.amount : max), 0n);
    return rows.map(row => {
      const note = key === 'late' ? `quá hạn ${M.ago(row.days)}` : key === 'due' ? `còn ${-row.days} ngày · hạn ${dayMonth(row.dueDate)}` : `hạn ${dayMonth(row.dueDate)}`;
      return `<button type="button" class="ov-row" data-go="thang:${escape(row.key)}" aria-label="${escape(`${tag(row.key)} — ${full(row.amount)}, ${note}, mở sổ tháng ${monthLabel(row.key)}`)}">`
        + `<b>${escape(tag(row.key))}</b><span class="ov-row-bar"><i class="ov-key ${key}" style="width:${barWidth(row.amount, top)}%"></i></span>`
        + `<strong>${escape(short(row.amount))}</strong><small class="${key === 'late' ? 'late' : ''}">${escape(note)}</small>${NEXT}</button>`;
    }).join('');
  }
  function detailPanel(tiers, parts) {
    const part = parts.find(([, , kind]) => kind === ui.detail);
    if (!part) return '';
    const [label, value, kind, month] = part;
    const head = (title, sub) => `<div class="ov-panel-head"><strong>${escape(title)}</strong><span>${escape(sub)}</span>`
      + `<button type="button" class="ov-close" data-ui="close" aria-label="Đóng">${CLOSE}</button></div>`;
    const inner = tiers?.matches ? head(`${label} · ${short(toBig(value))}`, 'theo tháng nợ, bấm dòng để mở sổ') + tierRows(kind, tiers)
      : head(label, 'chưa tách được theo tháng') + (month ? button(`thang:${monthKey(month)}`, 'Mở ở Sổ', '', 'ov-link-btn') : '');
    return `<div class="ov-panel" id="ov-panel">${inner}</div>`;
  }

  const clock = at => new Date(at).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false });
  function referenceHero(data, months) {
    const debt = side.debt, row = loaded(debt) ? debt.data.row : null;
    const riskCode = row?.risk ?? 'unknown';
    const riskName = RISK[riskCode] ?? (debt.state === 'error' ? 'Chưa đọc được rủi ro' : 'Đang đọc rủi ro');
    const tiers = row?.tiers_vnd ?? [];
    const asOf = loaded(debt) ? debt.data.asOf : null;
    const parts = row ? [
      ['Quá hạn', row.overdue_vnd, 'late', row.oldest_open_month],
      [`Đến hạn ${endOf(asOf.slice(0, 7))}`, tiers[1], 'due', shift(asOf.slice(0, 7), -(debt.data.rule.due_after_months ?? 1))],
      ['Chưa đến hạn', tiers[0], 'future', null],
    ].filter(([, value]) => value != null && toBig(value) > 0n) : [];
    const total = toBig(data.total_outstanding_vnd), credit = model.creditOf(data.total_outstanding_vnd);
    const positive = parts.reduce((sum, [, value]) => sum + toBig(value), 0n);
    const hot = parts.some(([, , kind]) => kind === ui.detail) ? ` data-hot="${ui.detail}"` : '';
    const segments = positive > 0n ? parts.map(([label, value, kind]) => `<span class="ov-segment ${kind}" data-ui="detail:${kind}" data-tier="${kind}" style="flex:${toBig(value)}" title="${escape(label)} ${full(value)}"><i class="ov-key ${kind}"></i></span>`).join('') : '';
    const partHtml = parts.map(([label, value, kind]) => `<button type="button" class="ov-part" data-ui="detail:${kind}" data-tier="${kind}" aria-expanded="${ui.detail === kind}">`
      + `<span><i class="ov-key ${kind}"></i>${escape(label)}</span><b>${short(toBig(value))}${CARET(ui.detail === kind)}</b></button>`).join('');
    const riskHtml = credit > 0n ? '' : `<span class="ov-risk r-${escape(riskCode)}">${escape(riskName)}</span>`;
    // Lúc web đọc số, không phải độ mới của Sheet: chưa có API cho độ mới (TINH-HINH-01).
    const when = loaded(debt) && debt.at ? `<small class="ov-as-of">Số trên web lúc ${clock(debt.at)}</small>` : '';
    return `<section class="ov-hero ${escape(riskCode)}" aria-label="Công nợ hôm nay"><div class="ov-hero-debt">`
      + `<div class="ov-hero-label">${credit > 0n ? 'Khách trả trước' : 'Còn nợ'} ${riskHtml}</div>`
      + `<strong class="ov-total">${full(credit > 0n ? credit : total)}</strong>${when}</div>`
      + `<div class="ov-hero-split"><div class="ov-segments" id="ov-segments" aria-hidden="true"${hot}>${segments}</div>`
      + `<div class="ov-parts">${partHtml || (total < 0n ? '<span>Khách trả trước</span>' : debt.state === 'error' ? '' : '<span>Đang đọc cơ cấu nợ…</span>')}</div></div>`
      + `${debt.state === 'error' ? `<p class="ov-error" role="alert">${escape(loadError('số quá hạn'))} ${button('retry:debt', 'Thử lại')}</p>` : ''}`
      + `${pendingLine(data)}${detailPanel(months, parts)}</section>`;
  }
  // Chuyến chưa vào số nợ: nói rõ loại và số lượng, bấm là tới đúng chỗ ở thẻ Sổ (cùng số với chấm cam trên chip tháng).
  function pendingLine(data) {
    const work = bookWork(data);
    if (!work.length) return '';
    return `<p class="ov-pending-line"><span>Còn nợ chưa tính:</span>${work.map(([count, what, kind]) => button(`loc:${kind}`, `${count} chuyến ${what}`, 'mở ở thẻ Sổ', 'ov-pending-go')).join('')}</p>`;
  }

  // ---- Bốn dữ kiện: khách có đang trả không, còn đi hàng không, nợ cũ tới đâu ----
  function factCell(label, value, sub, kind = '') {
    return `<div class="ov-keyfact${kind ? ` ${kind}` : ''}"><span>${escape(label)}</span><b>${escape(value)}</b><small>${escape(sub)}</small></div>`;
  }
  function referenceFacts(data, series, months, events) {
    const debt = side.debt, row = loaded(debt) ? debt.data.row : null;
    const failed = debt.state === 'error';
    const waitText = failed ? '—' : loaded(debt) ? 'Chưa có' : 'Đang đọc…';
    const key = thisMonth();
    const item = series.items.find(entry => entry.key === key);
    const thu = item?.present
      ? factCell(`Thu ${tag(key)}`, short(item.receivedVnd ?? 0n), `phát sinh ${short(item.chargesVnd ?? 0n)}`)
      : factCell(`Thu ${tag(key)}`, '0 đ', 'chưa có chuyến hay phiếu thu');
    // Trả gần nhất: ngày theo Tổng quan; sổ không có dòng ở Tổng quan (không nợ) thì lấy khoản mới nhất trong sổ.
    const lastPaid = events.find(entry => entry.kind === 'paid');
    const paidDate = row ? row.last_receipt_date : lastPaid?.date ?? null;
    const paidExact = row ? row.last_receipt_exact : true;
    const paid = paidDate ? M.factDate(paidDate, paidExact) : lastPaid ? `T${monthLabel(lastPaid.key)}` : waitText;
    const paidAmount = paidDate ? M.paidOn(events, paidDate, paidExact) : lastPaid?.amount ?? null;
    const paidAgo = row && paidExact && row.pay_days != null ? (row.pay_days === 0 ? 'hôm nay' : `${M.ago(row.pay_days)} trước`) : '';
    const paidSub = [paidAmount === null ? '' : short(paidAmount), paidAgo].filter(Boolean).join(' · ');
    // Đi hàng: cùng chữ với Tổng quan; sổ không có ở Tổng quan thì lấy ngày chuyến mới nhất trong sổ.
    const newestTrip = [...(data.trips ?? []), ...(data.legacy_rows ?? []).filter(line => line.kind !== 'receipt')].map(line => line.event_date ?? line.current?.event_date).filter(Boolean).sort().at(-1);
    const tripDate = row?.last_trip_date ? M.factDate(row.last_trip_date, row.last_trip_exact) : newestTrip ? CongNoFormat.dateText(newestTrip) : waitText;
    const before = shift(key, -1);
    const tripSub = `${tag(key)}: ${view.counts.get(key) ?? 0} chuyến · ${tag(before)}: ${view.counts.get(before) ?? 0}`;
    // Quá hạn lâu nhất: tháng nợ cũ nhất còn tiền; số tiền chỉ ghi khi từng tháng cộng khớp Tổng quan.
    const oldest = months?.groups.late.find(entry => entry.amount > 0n);
    const lateCell = oldest ? factCell('Quá hạn lâu nhất', `${tag(oldest.key)} · ${M.ago(oldest.days)}`, months.matches ? `còn ${short(oldest.amount)}` : '', 'late')
      : factCell('Quá hạn lâu nhất', failed ? '—' : loaded(debt) ? 'Không có' : 'Đang đọc…', '');
    return `<div class="ov-keyfacts" role="group" aria-label="Dữ kiện của khách">${factCell('Trả gần nhất', paid, paidSub)}${thu}${factCell('Đi hàng gần nhất', tripDate, tripSub)}${lateCell}</div>`;
  }

  // ---- Hình 12 tháng ----
  const px = at => Math.round(at * PLOT * 10) / 10;
  function barHtml(item, kind, at, value, zero, what) {
    if (at === null) return '';
    const bottom = Math.min(px(at), px(zero));
    const height = Math.max(Math.abs(px(at) - px(zero)), value === 0n ? 0 : 1);
    return `<span class="ov-bar ${kind}" data-month="${item.key}" data-vnd="${value}" data-what="${what}" style="bottom:${bottom}px;height:${height}px"></span>`;
  }
  function columnHtml(item, plot) {
    const on = ui.pin === item.key;
    const today = todayIso();
    const sub = item.key === today.slice(0, 7) ? `<small>đến ${dayMonth(today)}</small>` : '';
    // Phần năm ("/2025") tách riêng để điện thoại ẩn đi, nhãn chỉ còn T12 (DIEN-THOAI-SEP-01).
    const [month, year] = tag(item.key).split('/');
    const name = `<span class="ov-name">${month}${year ? `<span class="ov-year">/${year}</span>` : ''}${sub}</span>`;
    const inner = `<span class="ov-plot">${plot}</span>${name}`;
    if (!item.present) return `<span class="ov-month off" title="${escape(`${tag(item.key)}: không có dòng`)}">${inner}</span>`;
    const label = `${tag(item.key)} — phát sinh ${full(item.chargesVnd ?? 0n)}, đã thu ${full(item.receivedVnd ?? 0n)}, còn nợ cuối tháng ${item.endVnd === null ? '–' : full(item.endVnd)}, `
      + `${view.counts.get(item.key)} chuyến. ${on ? 'Bấm để bỏ ghim.' : 'Bấm để ghim tháng này.'}`;
    return `<button type="button" class="ov-month${on ? ' on' : ''}" data-ui="pin:${item.key}" data-key="${item.key}" aria-pressed="${on}" aria-label="${escape(label)}">${inner}</button>`;
  }
  function chartColumns(series) {
    return series.items.map(item => columnHtml(item, barHtml(item, 'ps', item.chargesAt, item.chargesVnd, series.zeroAt, 'phát sinh')
      + barHtml(item, 'thu', item.receivedAt, item.receivedVnd, series.zeroAt, 'đã thu')
      + (item.endAt === null || item.carried ? '' : `<span class="ov-point" data-month="${item.key}" data-vnd="${item.endVnd}" style="bottom:${px(item.endAt)}px"></span>`))).join('');
  }
  function chartLine(series) {
    const { items } = series;
    const y = at => Math.round((CHART_H - at * PLOT) * 10) / 10;
    const points = items.map((item, index) => [index, item]).filter(([, item]) => item.endAt !== null);
    if (!points.length) return '';
    const line = points.map(([index, item]) => `${(index + 0.5) * 100},${y(item.endAt)}`).join(' ');
    const zero = y(series.zeroAt);
    const area = points.length > 1 ? `<polygon class="ov-area" points="${(points[0][0] + 0.5) * 100},${zero} ${line} ${(points.at(-1)[0] + 0.5) * 100},${zero}"/>` : '';
    const last = items[series.last];
    const left = (series.last + 0.5) / items.length * 100;
    return `<svg class="ov-lines" viewBox="0 0 ${items.length * 100} ${CHART_H}" preserveAspectRatio="none" aria-hidden="true">${area}<polyline class="ov-line" points="${line}"/></svg>`
      + `<span class="ov-num" data-month="${last.key}" style="left:${left}%;top:${Math.max(0, y(last.endAt) - 30)}px">${escape(short(last.endVnd))}</span>`;
  }
  const LEGEND = [['ps', 'Phát sinh'], ['thu', 'Đã thu'], ['line', 'Còn nợ cuối tháng']];
  function figures(key) {
    const item = view.series.items.find(row => row.key === key);
    return [['Phát sinh', item.chargesVnd], ['Đã thu', item.receivedVnd], ['Còn nợ cuối tháng', item.endVnd]].map(([label, value]) => [label, value === null ? '—' : value])
      .concat([['Chuyến', view.counts.get(key)]]);
  }
  // Màn cảm ứng không rê chuột được (điện thoại, DIEN-THOAI-SEP-01): chạm một tháng là ghim, khung số hiện ngay dưới biểu đồ.
  const touchOnly = () => typeof matchMedia === 'function' && matchMedia('(hover: none)').matches;
  function pinBar() {
    if (!ui.pin || !view.series.items.some(row => row.key === ui.pin && row.present)) return `<p class="ov-note">${touchOnly() ? 'Chạm một tháng để xem số' : 'Rê chuột xem số, bấm một tháng để ghim'}</p>`;
    const cells = figures(ui.pin).map(([label, value]) => `<span><small>${escape(label)}</small><b>${escape(typeof value === 'bigint' ? short(value) : String(value))}</b></span>`).join('');
    return `<div class="ov-pin" id="ov-pin"><strong>${escape(tag(ui.pin))}</strong>${cells}${button(`thang:${ui.pin}`, `Mở sổ ${tag(ui.pin)}`, '', 'ov-pin-open')}`
      + `<button type="button" class="ov-close" data-ui="unpin" aria-label="${escape(`Bỏ ghim ${tag(ui.pin)}`)}">${CLOSE}</button></div>`;
  }
  function trend(series) {
    const legend = LEGEND.map(([kind, text]) => `<span><i class="ov-sw ${kind}"></i>${escape(text)}</span>`).join('');
    return `<section class="ov-block" id="ov-trend" aria-labelledby="ov-trend-title"><div class="ov-chart-head"><h2 id="ov-trend-title">Còn nợ 12 tháng</h2><p class="ov-legend">${legend}</p></div>`
      + `<div class="ov-chart" id="ov-chart"><div class="ov-columns" style="--months:${series.items.length}">${chartColumns(series)}</div>${chartLine(series)}<div class="ov-tip" id="ov-tip" role="status" hidden></div></div>${pinBar()}</section>`;
  }

  // ---- Tiền về và hứa trả ----
  function eventHtml(row) {
    const open = ui.open === row.id;
    const when = row.date ? CongNoFormat.dateText(row.date) : `T${monthLabel(row.key)}`;
    const go = row.go === 'trao-doi' ? '<button type="button" class="tab-go ov-event-go" data-the="trao-doi">Mở thẻ Trao đổi</button>'
      : button(row.go, `Xem ở Sổ ${tag(row.key)}`, '', 'ov-event-go');
    const detail = open ? `<div class="ov-event-detail">${row.lines.map(([label, value]) => `<div><span>${escape(label)}</span><b>${escape(value)}</b></div>`).join('')}${go}</div>` : '';
    return `<li><button type="button" class="ov-event-row ${row.kind}" data-ui="event:${escape(row.id)}" data-key="${row.key}" aria-expanded="${open}"><time>${escape(when)}</time>`
      + `<span><b>${escape(row.title)}</b>${row.sub ? `<small>${escape(row.sub)}</small>` : ''}</span>${CARET(open)}</button>${detail}</li>`;
  }
  function referenceActivity(events) {
    const rows = ui.pin ? events.filter(row => row.key === ui.pin) : events;
    const chip = ui.pin ? `<button type="button" class="ov-chip" data-ui="unpin" aria-label="${escape(`Bỏ lọc ${tag(ui.pin)}`)}"><span>${escape(tag(ui.pin))}${CLOSE}</span></button>` : '';
    const empty = ui.pin ? `Không có khoản thu trong ${tag(ui.pin)}.` : 'Chưa có khoản thu nào trên sổ.';
    const more = rows.length > ui.limit ? `<button type="button" class="ov-more" data-ui="more">Xem thêm ${Math.min(MORE, rows.length - ui.limit)}</button>` : '';
    return `<section class="ov-activity"><div class="ov-section-head"><h2>Tiền về và hứa trả</h2>${chip}</div>`
      + `<ol>${rows.slice(0, ui.limit).map(eventHtml).join('') || `<li class="ov-none">${escape(empty)}</li>`}</ol>${more}`
      + `${side.marks.state === 'error' ? `<p class="ov-error" role="alert">${escape(loadError('hứa trả'))} ${button('retry:marks', 'Thử lại')}</p>` : ''}</section>`;
  }

  function content(data) {
    if (data.status !== 'active') {
      return '<div class="ov-block" role="status"><p>Khách chưa có số dư đầu hiệu lực. Chưa có số để xem.</p>'
        + '<button type="button" class="tab-go" data-the="so">Mở thẻ Sổ</button></div>';
    }
    const series = model.monthSeries(data.months ?? [], thisMonth());
    view = { series, counts: new Map(series.items.map(item => [item.key, M.tripCount(data, item.key)])) };
    if (ui.pin && !series.items.some(item => item.key === ui.pin && item.present)) ui.pin = null;
    const debt = side.debt, row = loaded(debt) ? debt.data.row : null;
    const months = row ? M.debtTiers(row, debt.data.asOf, debt.data.rule.due_after_months ?? 1) : null;
    const events = M.moneyEvents(data, { marks: loaded(side.marks) ? side.marks.data : [], today: todayIso() });
    return referenceHero(data, months) + referenceFacts(data, series, months, events) + `<div class="ov-main-row">${trend(series)}${referenceActivity(events)}</div>`;
  }
  // Dữ liệu lạ làm thẻ vẽ lỗi thì chỉ thẻ này báo, thẻ Sổ vẫn dùng được.
  function body(data) {
    try { return content(data); } catch { return '<div class="ov-block" role="alert"><p>Chưa vẽ được thẻ Tình hình. Số của khách xem ở thẻ Sổ.</p></div>'; }
  }
  // Khung thẻ Tình hình, vẽ cùng lần với cả sổ (so-khach-v7-tabs-ui.js đặt sau thẻ Sổ).
  function overviewPane() {
    if (ctx.snapshot?.status === 'active') wake();
    return `<section class="tab-pane ov" id="the-tinh-hinh" role="tabpanel" aria-labelledby="tab-tinh-hinh">${ctx.snapshot ? body(ctx.snapshot) : ''}</section>`;
  }
  // Vừa mở thẻ Tình hình: đọc nguồn phụ nếu cần, vẽ lại khung (hiện "Đang đọc…").
  function tabShown(id) {
    if (id !== 'tinh-hinh' || ctx.snapshot?.status !== 'active') return;
    wake();
    paint();
  }

  // Bấm một tháng: sang thẻ Sổ, ghi month= lên địa chỉ (tải lại vẫn đúng tháng), hiện chi tiết tháng đó rồi cuộn tới.
  function openMonth(key) {
    const query = new URLSearchParams(location.search);
    query.set('month', key);
    window.history.replaceState(window.history.state, '', `${location.pathname}?${query}`);
    showMonth(key);
    root.querySelector(`#thang-${key}`)?.scrollIntoView({ block: 'start', behavior: 'instant' });
  }
  // Bấm trong thẻ, không rời thẻ: đổi `ui` rồi chỉ vẽ lại khung này.
  function act(action) {
    const at = action.indexOf(':');
    const what = at < 0 ? action : action.slice(0, at);
    const value = at < 0 ? '' : action.slice(at + 1);
    const pin = key => { ui.pin = ui.pin === key ? null : key; ui.open = null; ui.limit = LIMIT; };
    let focusTo = null;
    if (what === 'detail') ui.detail = ui.detail === value ? null : value;
    else if (what === 'close') { focusTo = `button[data-ui="detail:${ui.detail}"]`; ui.detail = null; }
    else if (what === 'pin') pin(value);
    else if (what === 'unpin') { focusTo = `[data-ui="pin:${ui.pin}"]`; pin(ui.pin); }
    else if (what === 'event') ui.open = ui.open === value ? null : value;
    else if (what === 'more') { focusTo = '.ov-activity ol li:last-child button'; ui.limit += MORE; }
    paint(focusTo);
    // Có dòng Chưa tính thì dải số của tháng ghim có thể rơi dưới mép màn 1280×560: bấm mà không thấy nút Mở sổ thì như chưa bấm.
    if (what === 'pin' && ui.pin) root.querySelector('#ov-pin')?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  }
  root.addEventListener('click', event => {
    const local = event.target.closest?.('#the-tinh-hinh [data-ui]');
    if (local) { act(local.dataset.ui); return; }
    const target = event.target.closest?.('#the-tinh-hinh [data-go]');
    if (!target) return;
    const [what, value] = target.dataset.go.split(':');
    if (what === 'retry') { wake(value); paint(); return; }
    showTab('so');
    if (what === 'thang') openMonth(value);
    else if (what === 'loc') ctx.showLoc(value);
  });

  // Rê hoặc Tab: tô đoạn nợ, hiện số của tháng. Chỉ đổi lớp và bong bóng, không vẽ lại khung.
  function pointTier(tier) {
    const bar = root.querySelector('#ov-segments');
    if (!bar) return;
    const sticky = ['late', 'due', 'future'].includes(ui.detail) ? ui.detail : null;
    if (tier ?? sticky) bar.dataset.hot = tier ?? sticky; else delete bar.dataset.hot;
  }
  function pointMonth(key) {
    const chart = root.querySelector('#ov-chart');
    const tip = root.querySelector('#ov-tip');
    if (!chart || !tip || !view.series) return;
    chart.querySelectorAll('.ov-month.hot').forEach(node => node.classList.remove('hot'));
    const index = key ? view.series.items.findIndex(item => item.key === key) : -1;
    if (index < 0) { tip.hidden = true; return; }
    chart.querySelector(`.ov-month[data-key="${key}"]`)?.classList.add('hot');
    if (key === ui.pin) { tip.hidden = true; return; }
    tip.innerHTML = `<b>${escape(tag(key))}</b>${figures(key).map(([label, value]) => `<span><small>${escape(label)}</small><strong>${escape(typeof value === 'bigint' ? full(value) : String(value))}</strong></span>`).join('')}`;
    const count = view.series.items.length;
    tip.style.left = `${(index + 0.5) / count * 100}%`;
    tip.style.transform = index < 2 ? 'translateX(-14%)' : index > count - 3 ? 'translateX(-86%)' : 'translateX(-50%)';
    tip.hidden = false;
  }
  function point(event) {
    if (!shown()) return;
    const inside = event.target.closest?.('#the-tinh-hinh') ? event.target : null;
    pointTier(inside?.closest('[data-tier]')?.dataset.tier ?? null);
    pointMonth(inside?.closest('[data-key]')?.dataset.key ?? null);
  }
  root.addEventListener('pointerover', point);
  root.addEventListener('focusin', point);
  root.addEventListener('pointerleave', () => { pointTier(null); pointMonth(null); });

  Object.assign(ctx, { overviewPane, tabShown });
};
