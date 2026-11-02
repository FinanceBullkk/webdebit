/* Tình hình trang khách: bố cục theo mockup TinhHinh.dc.html người dùng đưa 02/11/2026.
 * Số từ sổ, Tổng quan và dấu hứa trả; không dùng số mẫu. Dữ liệu phụ đọc khi mở thẻ.
 * B1 chưa có API trả sau hạn nên ô đó hiện “—”. Trường ctx: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).overview = ctx => {
  'use strict';
  const { root, model, api, escape, monthKey, monthLabel, liveOpenMonth, showTab, showMonth, bookWork } = ctx;
  const { toBig, full, short, monthTag, dateText, vnDay, loadError } = CongNoFormat;
  // Cùng chữ với Tổng quan (DashboardModel.RISK, reasons) để hai nơi gọi một khách như nhau.
  const RISK = { high: 'Rủi ro cao', watch: 'Theo dõi', ok: 'Trong hạn' };
  const side = { debt: { state: 'idle', read: 'readDebt' }, reminders: { state: 'idle', read: 'readReminders' }, marks: { state: 'idle', read: 'readMarks' }, chats: { state: 'idle', read: 'findChats' } };
  const shown = () => document.body?.dataset.the === 'tinh-hinh';
  const loaded = item => item.state !== 'error' && Object.hasOwn(item, 'data');
  const thisMonth = () => monthKey(ctx.snapshot?.today_month) || liveOpenMonth;
  const tag = key => monthTag(`${key}-01`, Number(thisMonth().slice(0, 4)));
  // Số ngày thành chữ như Tổng quan (DashboardModel.ago): tới 90 ngày đếm ngày, lâu hơn đếm tháng.
  const shift = (key, by) => {
    const n = Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1 + by;
    return `${Math.floor(n / 12)}-${String(n % 12 + 1).padStart(2, '0')}`;
  };
  // Hạn trả (DASH-03 (1)): nợ tháng M đến hạn ngày cuối tháng M + due_after_months. Ngày đếm theo lịch (số ngày UTC).
  const dueDay = (key, after) => Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) + after, 0) / 86400000;
  const endOf = key => { const date = new Date(dueDay(key, 0) * 86400000); return `${date.getUTCDate()}/${date.getUTCMonth() + 1}`; };
  // Nhãn đọc màn hình luôn bắt đầu bằng chữ trên nút (WCAG 2.5.3), `more` nói thêm nút mở gì.
  const button = (go, text, more = '', kind = 'ov-go') => `<button type="button" class="${kind}" data-go="${escape(go)}"`
    + `${more ? ` aria-label="${escape(`${text} — ${more}`)}"` : ''}>${escape(text)}</button>`;
  const block = (title, html) => `<section class="ov-block"><h2>${title}</h2>${html}</section>`;

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
  // Nguồn phụ về sau lần vẽ sổ: chỉ vẽ lại khung thẻ Tình hình; tiêu điểm đang ở một nút của thẻ thì về nút cùng việc.
  function paint() {
    const pane = root.querySelector('#the-tinh-hinh');
    if (!pane || !ctx.snapshot) return;
    const focus = pane.contains(document.activeElement) ? document.activeElement.dataset?.go : null;
    pane.innerHTML = body(ctx.snapshot);
    if (focus) pane.querySelector(`[data-go="${CSS.escape(focus)}"]`)?.focus();
  }

  // Tên tháng dưới hình, thẳng cột với hình: tháng có trong sổ là nút mở thẻ Sổ tháng đó (vùng bấm 40px, Tab tới được).
  const monthRow = (items, label) => `<div class="ov-months" style="grid-template-columns:repeat(${items.length},1fr)">${items.map(item => (item.present
    ? button(`thang:${item.key}`, tag(item.key), label(item), 'ov-month') : `<span class="ov-month off">${tag(item.key)}</span>`)).join('')}</div>`;
  // Khối 2: cột kép phát sinh (xám) và đã thu (navy), đường Còn nợ cuối tháng, ghi số ở điểm thấp nhất và điểm cuối. Tháng không có
  // dòng thì không có cột (không phải 0) và đường giữ số tháng trước. Bấm cột một tháng hoặc tên tháng thì sang thẻ Sổ tháng đó.
  function trend(series) {
    const { items } = series, W = 1200, H = 214, TOP = 30, PLOT = 174, col = W / items.length;
    const y = at => Math.round((TOP + (1 - at) * PLOT) * 10) / 10;
    const zero = y(series.zeroAt), mid = index => col * (index + 0.5);
    const bar = (item, kind, at, value, x, what) => (at === null ? '' : `<rect class="ov-bar ${kind}" data-month="${item.key}" data-vnd="${value}" `
      + `x="${x}" y="${Math.min(y(at), zero)}" width="22" height="${Math.max(Math.abs(y(at) - zero), value === 0n ? 0 : 1)}">`
      + `<title>Tháng ${monthLabel(item.key)} · ${what} ${full(value)}</title></rect>`);
    const columns = items.map((item, index) => (item.present ? `<g class="ov-col" data-go="thang:${item.key}">`
      + `<rect class="ov-hit" x="${col * index}" y="0" width="${col}" height="${H}"><title>Mở sổ tháng ${monthLabel(item.key)}</title></rect>`
      + `${bar(item, 'ps', item.chargesAt, item.chargesVnd, mid(index) - 24, 'phát sinh')}`
      + `${bar(item, 'thu', item.receivedAt, item.receivedVnd, mid(index) + 2, 'đã thu')}</g>` : '')).join('');
    const points = items.map((item, index) => [index, item]).filter(([, item]) => item.endAt !== null);
    const line = points.map(([index, item]) => `${mid(index)},${y(item.endAt)}`).join(' ');
    const area = points.length > 1 ? `<polygon class="ov-area" points="${mid(points[0][0])},${zero} ${line} ${mid(points.at(-1)[0])},${zero}"/>` : '';
    const dots = points.filter(([, item]) => !item.carried).map(([index, item]) => `<circle class="ov-point" data-go="thang:${item.key}" `
      + `data-month="${item.key}" data-vnd="${item.endVnd}" cx="${mid(index)}" cy="${y(item.endAt)}" r="5">`
      + `<title>Tháng ${monthLabel(item.key)} · còn nợ cuối tháng ${full(item.endVnd)}</title></circle>`).join('');
    const labels = [series.last].filter(index => index !== null).map(index => {
      const at = y(items[index].endAt), anchor = index === 0 ? 'start' : index === items.length - 1 ? 'end' : 'middle';
      return `<text class="ov-num" data-month="${items[index].key}" x="${mid(index)}" y="${at < TOP + 4 ? at + 24 : at - 12}" `
        + `text-anchor="${anchor}">${escape(short(items[index].endVnd))}</text>`;
    }).join('');
    return block('Còn nợ 12 tháng', `<p class="ov-note">Bấm một tháng để mở sổ tháng đó</p>`
      + `<div class="ov-chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Phát sinh, đã thu và còn nợ cuối tháng, ${items.length} tháng `
      + `tới tháng ${monthLabel(items.at(-1).key)}">${area}<line class="ov-zero" x1="0" x2="${W}" y1="${zero}" y2="${zero}"/>${columns}`
      + `<polyline class="ov-line" points="${line}"/>${dots}${labels}</svg>${monthRow(items, item => `mở sổ tháng ${monthLabel(item.key)}: phát sinh `
        + `${full(item.chargesVnd ?? 0n)}, đã thu ${full(item.receivedVnd ?? 0n)}, còn nợ cuối tháng ${item.endVnd === null ? '–' : full(item.endVnd)}`)}</div>`
      + '<p class="ov-legend"><span><i class="ov-sw ps"></i>Phát sinh</span><span><i class="ov-sw thu"></i>Đã thu</span>'
      + '<span><i class="ov-sw line"></i>Còn nợ cuối tháng</span></p>');
  }

  // ponytail: Chỉ hiện số ngày trả trễ khi API B1 có kết quả; thêm API đó sau migration B1.
  function referenceHero(data) {
    const debt = side.debt, row = loaded(debt) ? debt.data.row : null;
    const riskCode = row?.risk ?? 'unknown';
    const riskName = RISK[riskCode] ?? (debt.state === 'error' ? 'Chưa đọc được rủi ro' : 'Đang đọc rủi ro');
    const pending = bookWork(data).reduce((sum, [count]) => sum + count, 0);
    const tiers = row?.tiers_vnd ?? [];
    const parts = row ? [
      ['Quá hạn', row.overdue_vnd, 'late', row.oldest_open_month],
      [`Đến hạn ${endOf(debt.data.asOf.slice(0, 7))}`, tiers[1], 'due', shift(debt.data.asOf.slice(0, 7), -(debt.data.rule.due_after_months ?? 1))],
      ['Chưa đến hạn', tiers[0], 'future', null],
    ].filter(([, value]) => value != null && toBig(value) > 0n) : [];
    const total = toBig(data.total_outstanding_vnd), credit = model.creditOf(data.total_outstanding_vnd);
    const positive = parts.reduce((sum, [, value]) => sum + toBig(value), 0n);
    const segments = positive > 0n ? parts.map(([label, value, kind]) => `<span class="ov-segment ${kind}" style="flex:${toBig(value)}" title="${escape(label)} ${full(value)}"></span>`).join('') : '';
    const partHtml = parts.map(([label, value, kind, month]) => `<div class="ov-part"><span><i class="ov-key ${kind}"></i>${escape(label)}</span>`
      + `${month ? button(`thang:${monthKey(month)}`, short(toBig(value)), `mở sổ tháng ${monthLabel(monthKey(month))}`, 'ov-part-link') : `<b>${short(toBig(value))}</b>`}</div>`).join('');
    const marks = loaded(side.marks) ? side.marks.data : [];
    const promise = marks.find(mark => mark.kind === 'promise' && mark.status === 'pending');
    const unavailable = side.marks.state === 'error' || debt.state === 'error';
    const next = unavailable ? ['Chưa xác định việc tiếp theo', 'Kiểm tra dữ liệu rồi thử lại', 'unknown']
      : !loaded(side.marks) || !loaded(debt) ? ['Đang đọc việc tiếp theo…', '', 'unknown']
      : promise ? ['Chờ hứa trả', `${full(promise.amount_vnd)} · hẹn ${dateText(promise.on_date)}`, 'wait']
      : row && toBig(row.overdue_vnd) > 0n ? ['Nhắc nợ ngay', 'Có nợ quá hạn · xem thẻ Trao đổi', 'remind']
        : ['Chưa cần làm gì', 'Theo dõi hạn trả trong Sổ', 'ok'];
    return `<section class="ov-hero ${escape(riskCode)}" aria-label="Công nợ hôm nay"><div class="ov-hero-debt">`
      + `<div class="ov-hero-label">${credit > 0n ? 'Khách trả trước' : 'Còn nợ'} ${credit > 0n ? '' : `<span class="ov-risk r-${escape(riskCode)}">${escape(riskName)}</span>`}`
      + `${pending ? `<button type="button" class="ov-pending tab-go" data-the="so">+${pending} việc cần xem</button>` : ''}</div>`
      + `<strong class="ov-total">${full(credit > 0n ? credit : total)}</strong><div class="ov-segments" aria-hidden="true">${segments}</div>`
      + `<div class="ov-parts">${partHtml || (total < 0n ? '<span>Khách trả trước</span>' : debt.state === 'error' ? '' : '<span>Đang đọc cơ cấu nợ…</span>')}</div>`
      + `${debt.state === 'error' ? `<p class="ov-error" role="alert">${escape(loadError('số quá hạn'))} ${button('retry:debt', 'Thử lại')}</p>` : ''}</div>`
      + `<div class="ov-next"><span class="ov-eyebrow">Việc tiếp theo</span><div class="ov-next-main"><span class="ov-next-icon" aria-hidden="true">${next[2] === 'wait' ? '◷' : next[2] === 'remind' ? '!' : '✓'}</span>`
      + `<div><strong>${next[0]}</strong><small>${next[1]}</small></div></div>`
      + `${side.marks.state === 'error' ? `<p class="ov-error" role="alert">${escape(loadError('hứa trả'))} ${button('retry:marks', 'Thử lại')}</p>` : ''}`
      + `${promise ? `<p class="ov-countdown">Hẹn ${dateText(promise.on_date)} · ${escape(promise.status === 'pending' ? 'đang chờ' : promise.status)}</p>` : ''}`
      + `<div class="ov-next-actions">${promise ? button('copy', 'Vẫn nhắc nợ', 'copy tin nhắc và ghi đã nhắc hôm nay', 'ov-copy')
        : '<button type="button" class="tab-go" data-the="trao-doi">Xem Trao đổi</button>'}`
      + `${promise ? '<button type="button" class="tab-go" data-the="trao-doi">Xem Trao đổi</button>' : ''}</div></div></section>`;
  }

  function referenceStats(data, series) {
    const revenue = model.seriesCharges(series);
    const months = series.items.slice(-6);
    const counts = months.map(item => (data.trips ?? []).filter(trip => monthKey(trip.month) === item.key && !trip.deleted && trip.status !== 'rejected' && !trip.is_fee_only).length
      + (data.legacy_rows ?? []).filter(row => monthKey(row.month) === item.key && row.kind !== 'receipt' && !row.current?.deleted).length);
    const recent = loaded(side.debt) ? side.debt.data.row : null;
    const last = recent?.last_trip_date ? (recent.last_trip_exact ? dateText(recent.last_trip_date) : `trong tháng ${monthLabel(recent.last_trip_date)}`)
      : dateText([...(data.trips ?? []), ...(data.legacy_rows ?? [])].map(row => row.event_date ?? row.current?.event_date).filter(Boolean).sort().at(-1));
    const max = Math.max(1, ...counts);
    return `<div class="ov-stats"><section class="ov-stat"><span>Trễ trung bình sau hạn <small>12 tháng</small></span><strong>—</strong>`
      + '<div class="ov-late-scale" aria-hidden="true"></div><p>Chưa đủ dữ liệu trả sau hạn</p></section>'
      + `<section class="ov-stat"><span>Doanh thu <small>12 tháng</small></span><strong>${revenue === null ? '—' : short(revenue)}</strong>`
      + '<p>Phát sinh đã ghi sổ trong 12 tháng</p></section>'
      + `<section class="ov-stat"><span>Đi hàng <small>6 tháng</small></span><strong>${counts.at(-1)} chuyến tháng này</strong>`
      + `<p>${last ? `gần nhất ${last}` : 'Chưa rõ chuyến gần nhất'}</p><div class="ov-spark" aria-hidden="true">`
      + `${counts.map(count => `<i style="height:${Math.max(2, count / max * 44)}px" title="${count} chuyến"></i>`).join('')}</div></section></div>`;
  }

  function referenceActivity(data) {
    const receipt = (data.receipts ?? []).filter(row => row.voided_by_event == null).map(row => ({ date: row.date, text: `Khách trả ${full(row.amount_vnd)}`, sub: row.method ?? '', kind: 'paid' }));
    const tripGroups = new Map();
    for (const row of data.trips ?? []) {
      if (row.deleted || row.status !== 'confirmed' || row.is_fee_only) continue;
      const key = `${row.event_date}|${row.destination ?? ''}`;
      tripGroups.set(key, { date: row.event_date, destination: row.destination ?? '', count: (tripGroups.get(key)?.count ?? 0) + 1 });
    }
    const trip = [...tripGroups.values()].map(row => ({ date: row.date, text: `${row.count} chuyến đi hàng`, sub: row.destination, kind: 'trip' }));
    const mark = (loaded(side.marks) ? side.marks.data : []).filter(row => row.status !== 'cancelled').map(row => ({ date: row.message_at ? vnDay(row.message_at) : String(row.created_on ?? '').slice(0, 10),
      text: row.kind === 'promise' ? `Hứa trả ${full(row.amount_vnd)}` : row.kind === 'paid_claim' ? `Báo đã chuyển ${full(row.amount_vnd)}` : 'Ghi chú',
      sub: row.kind === 'promise' ? `hẹn ${dateText(row.on_date)} · ${row.status === 'pending' ? 'đang chờ' : row.status}` : '', kind: 'mark' }));
    const reminder = loaded(side.reminders) && side.reminders.data ? [{ date: side.reminders.data.last_reminded, text: 'Nhắc nợ gần nhất', sub: `đã nhắc ${side.reminders.data.reminder_count} lần`, kind: 'remind' }] : [];
    const chats = loaded(side.chats) ? side.chats.data.conversations ?? [] : [];
    const chat = chats.filter(row => row.last_message_at).map(row => ({ date: vnDay(row.last_message_at), text: 'Zalo gần nhất', sub: row.display_name ?? '', kind: 'remind' }));
    const rows = [...receipt, ...trip, ...mark, ...reminder, ...chat].filter(row => /^\d{4}-\d\d-\d\d$/.test(row.date ?? '')).sort((a, b) => b.date.localeCompare(a.date)).slice(0, 4);
    return `<section class="ov-activity"><div class="ov-section-head"><h2>Hoạt động gần đây</h2><button type="button" class="tab-go" data-the="trao-doi">Tất cả ›</button></div>`
      + `<ol>${rows.map(row => `<li><span class="ov-event ${row.kind}" aria-hidden="true">${row.kind === 'paid' ? 'đ' : row.kind === 'mark' ? '!' : row.kind === 'remind' ? '↗' : '▸'}</span>`
        + `<span><b>${escape(row.text)}</b><small>${escape(row.sub)}</small></span><time>${dateText(row.date)}</time></li>`).join('') || '<li>Chưa có hoạt động gần đây.</li>'}</ol>`
      + `${side.reminders.state === 'error' ? `<p class="ov-error" role="alert">${escape(loadError('lần nhắc nợ'))} ${button('retry:reminders', 'Thử lại')}</p>` : ''}`
      + `${side.chats.state === 'error' ? `<p class="ov-error" role="alert">${escape(loadError('hội thoại Zalo'))} ${button('retry:chats', 'Thử lại')}</p>` : ''}</section>`;
  }

  function content(data) {
    if (data.status !== 'active') {
      return '<div class="ov-block" role="status"><p>Khách chưa có số dư đầu hiệu lực. Chưa có số để xem.</p>'
        + '<button type="button" class="tab-go" data-the="so">Mở thẻ Sổ</button></div>';
    }
    const series = model.monthSeries(data.months ?? [], thisMonth());
    return referenceHero(data) + referenceStats(data, series) + `<div class="ov-main-row">${trend(series)}${referenceActivity(data)}</div>`;
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
  root.addEventListener('click', event => {
    const target = event.target.closest?.('#the-tinh-hinh [data-go]');
    if (!target) return;
    const [what, value] = target.dataset.go.split(':');
    if (what === 'retry') { wake(value); paint(); return; }
    if (what === 'copy') { showTab('trao-doi'); root.querySelector('#the-trao-doi [data-go="copy"]')?.click(); return; }
    showTab('so');
    if (what === 'thang') openMonth(value);
    else if (what === 'loc') ctx.showLoc(value);
  });

  Object.assign(ctx, { overviewPane, tabShown });
};
