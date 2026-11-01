/* Sổ khách V7 bản live — thẻ Tình hình của trang khách (TRANG-KHACH-01, specs/v7-trang-khach.md, PR A2): khách này đang thế
 * nào, đọc từ trên xuống, mỗi câu hỏi một khối, số nằm trong hình, không câu kết luận (DASH-04):
 *   1. Khách đang nợ mình bao nhiêu: Còn nợ, Quá hạn, Đến hạn cuối tháng này, Thu tháng này; mức rủi ro kèm dữ kiện.
 *   2. Nợ đang tăng hay giảm: 12 tháng phát sinh, đã thu, Còn nợ cuối tháng; bấm một tháng thì sang thẻ Sổ tháng đó.
 *   4. Khách còn đi hàng không: số chuyến 6 tháng, lần đi hàng gần nhất.
 *   5. Còn gì làm số chưa đúng: việc chờ của sổ, mỗi dòng mở thẻ Sổ đúng chỗ.
 *   6. Lần cuối nói chuyện với khách, phần A: lần nhắc gần nhất, tin Zalo gần nhất (PR A3), sang thẻ Trao đổi.
 * Khối 3 (trả sau hạn) chờ hàm đọc mới (B1). Thẻ chỉ đọc, không ghi tiền: tiền lấy nguyên từ GET, chuỗi tháng do model dựng
 * (ARCH-03). Sổ (GET /api/v7/ledger) vẽ cùng lần với thẻ Sổ; Tổng quan (dashboard/debt), lần nhắc (reminders) và hội thoại Zalo
 * chỉ đọc khi thẻ đang mở, đọc lại khi sổ đổi phiên bản hoặc lần đọc đã quá 60 giây; nguồn nào lỗi thì chỉ khối đó báo lỗi kèm
 * Thử lại.
 * Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).overview = ctx => {
  'use strict';
  const { root, model, api, escape, monthKey, monthLabel, liveOpenMonth, showTab, showMonth, bookWork } = ctx;
  const { toBig, full, short, monthTag, dateText, vnDay, loadError } = CongNoFormat;
  // Cùng chữ với Tổng quan (DashboardModel.RISK, reasons) để hai nơi gọi một khách như nhau.
  const RISK = { high: 'Rủi ro cao', watch: 'Theo dõi', ok: 'Trong hạn' };
  const SOURCE = { 'copy-button': 'bấm Copy tin nhắc', zalo: 'Zalo', manual: 'ghi tay' };
  // Nút ở dải việc chờ đầu thẻ Sổ (SO-GON-04 L7) mà mỗi lô từ Sheet hay bảng PS mở tới.
  const TASKS = { sheet: '.sheet-approve', price: '.price-approve,.price-review-toggle', receipt: '.receipt-approve,.receipt-review-toggle',
    ps: '.ps-approve,.ps-review-toggle' };
  const side = { debt: { state: 'idle', read: 'readDebt' }, reminders: { state: 'idle', read: 'readReminders' }, chats: { state: 'idle', read: 'findChats' } };
  const shown = () => document.body?.dataset.the === 'tinh-hinh';
  const loaded = item => item.state !== 'error' && Object.hasOwn(item, 'data');
  const thisMonth = () => monthKey(ctx.snapshot?.today_month) || liveOpenMonth;
  const tag = key => monthTag(`${key}-01`, Number(thisMonth().slice(0, 4)));
  // Số ngày thành chữ như Tổng quan (DashboardModel.ago): tới 90 ngày đếm ngày, lâu hơn đếm tháng.
  const span = days => (days > 90 ? `${Math.floor(days / 30)} tháng` : `${days} ngày`);
  const ago = days => (days ? `${span(days)} trước` : 'hôm nay');
  const shift = (key, by) => {
    const n = Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1 + by;
    return `${Math.floor(n / 12)}-${String(n % 12 + 1).padStart(2, '0')}`;
  };
  // Hạn trả (DASH-03 (1)): nợ tháng M đến hạn ngày cuối tháng M + due_after_months. Ngày đếm theo lịch (số ngày UTC).
  const dueDay = (key, after) => Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) + after, 0) / 86400000;
  const day = iso => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))) / 86400000;
  const endOf = key => { const date = new Date(dueDay(key, 0) * 86400000); return `${date.getUTCDate()}/${date.getUTCMonth() + 1}`; };
  const card = (label, value, sub, tone = '') => `<div class="ov-card${tone}"><span class="ov-label">${label}</span>`
    + `<b class="ov-value">${value}</b><span class="ov-sub">${sub}</span></div>`;
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

  // Khối 1. Còn nợ và Thu tháng này lấy ở sổ: đúng số đầu trang và dòng Tổng tháng (DA-THU-01). Quá hạn, Đến hạn và mức rủi ro
  // lấy dòng của khách ở Tổng quan (dashboard/debt), cùng số với ngăn kéo Tổng quan. Khách đang dư (CAN-DU-01): không có quá hạn.
  function owed(data, now) {
    const month = `tháng ${Number(now.key.slice(5))}`;
    const paid = card(`Thu ${month}`, full(now.receivedVnd ?? 0n),
      now.present ? `phát sinh ${month}: ${full(now.chargesVnd ?? 0n)}` : `${month} chưa có chuyến hay phiếu thu`);
    const credit = model.creditOf(data.total_outstanding_vnd);
    if (credit > 0n) return block('Khách đang nợ mình bao nhiêu', `<div class="ov-cards">${card('Khách đang dư', full(credit), 'trả trước', ' wide')}${paid}</div>`);
    const open = (data.months ?? []).filter(row => toBig(row.outstanding_vnd ?? '0') > 0n).map(row => monthKey(row.month)).sort();
    const owing = card('Còn nợ', full(data.total_outstanding_vnd), open.length > 1 ? `${open.length} tháng còn nợ: ${tag(open[0])} → ${tag(open.at(-1))}`
      : open.length ? `còn nợ ${tag(open[0])}` : 'không tháng nào còn nợ');
    const debt = side.debt;
    const middle = debt.state === 'error'
      ? `<div class="ov-card wide ov-error" role="alert"><span>${escape(loadError('số quá hạn'))}</span>${button('retry:debt', 'Thử lại')}</div>`
      : loaded(debt) ? due(debt.data, data.total_outstanding_vnd)
        : card('Quá hạn', '…', 'Đang đọc số ở Tổng quan') + card('Đến hạn cuối tháng này', '…', '');
    return block('Khách đang nợ mình bao nhiêu', `<div class="ov-cards">${owing}${middle}${paid}</div>${loaded(debt) && debt.data.row ? risk(debt.data.row) : ''}`);
  }
  // Quá hạn: các tháng nợ đã quá hạn (nhóm 1–2, 3–6, trên 6 tháng của Tổng quan), lâu nhất bao nhiêu ngày; bấm thì sang thẻ Sổ ở
  // tháng đó. Đến hạn: nhóm "đến hạn cuối tháng này", kèm khoản kế tiếp (nhóm chưa đến hạn, hạn cuối tháng sau).
  function due({ asOf, rule, row }, total) {
    if (!row) {   // Tổng quan chỉ có sổ đang nợ
      const none = toBig(total) > 0n ? ['–', 'Tổng quan chưa có sổ này'] : ['0 đ', 'Không có nợ quá hạn'];
      return card('Quá hạn', ...none) + card('Đến hạn cuối tháng này', none[0], '');
    }
    const after = rule.due_after_months ?? 1, now = asOf.slice(0, 7), overdue = toBig(row.overdue_vnd) > 0n;
    const late = (row.months ?? []).filter(item => monthKey(item.month) <= shift(now, -1 - after) && toBig(item.outstanding_vnd) > 0n)
      .map(item => monthKey(item.month)).sort();
    const months = late.length > 3 ? `${late.length} tháng, từ ${tag(late[0])}` : late.map(tag).join(', ');
    const lateSub = overdue && late.length ? button(`thang:${late[0]}`, `${months} · lâu nhất ${span(day(asOf) - dueDay(late[0], after))}`,
      `mở sổ tháng ${monthLabel(late[0])}, tháng quá hạn lâu nhất`, 'ov-link') : 'Không có nợ quá hạn';
    const [notDue, dueNow] = row.tiers_vnd ?? [];
    const next = notDue && toBig(notDue) > 0n ? ` · kế tiếp ${short(notDue)} hạn ${endOf(shift(now, 1))}` : '';
    return card('Quá hạn', full(row.overdue_vnd), lateSub, overdue ? ' late' : '')
      + card(`Đến hạn ${endOf(now)}`, full(dueNow ?? '0'), `nợ ${tag(shift(now, -after))}${next}`);
  }
  // Mức rủi ro (DASH-03 (2)) kèm dữ kiện tạo ra nó: lần trả và lần đi hàng gần nhất. Dòng sổ gốc không ghi ngày thì chỉ biết tháng.
  function risk(row) {
    const when = (date, exact) => (exact ? dateText(date) : `trong tháng ${monthLabel(date)}`);
    const facts = [row.last_receipt_date ? `Trả gần nhất ${when(row.last_receipt_date, row.last_receipt_exact)} · ${ago(row.pay_days)}` : 'Chưa trả lần nào',
      row.last_trip_date ? `Đi hàng gần nhất ${when(row.last_trip_date, row.last_trip_exact)} · ${ago(row.trip_days)}` : 'Chưa có chuyến'];
    return `<p class="ov-facts"><span class="ov-risk r-${escape(row.risk)}">${escape(RISK[row.risk] ?? row.risk)}</span>`
      + `${facts.map(fact => `<span class="ov-fact">${escape(fact)}</span>`).join('')}</p>`;
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
    const labels = [...new Set([series.low, series.last])].filter(index => index !== null).map(index => {
      const at = y(items[index].endAt), anchor = index === 0 ? 'start' : index === items.length - 1 ? 'end' : 'middle';
      return `<text class="ov-num" data-month="${items[index].key}" x="${mid(index)}" y="${at < TOP + 4 ? at + 24 : at - 12}" `
        + `text-anchor="${anchor}">${escape(short(items[index].endVnd))}</text>`;
    }).join('');
    return block('Nợ đang tăng hay giảm?', `<p class="ov-note">${items.length} tháng gần nhất · bấm một tháng để mở sổ tháng đó</p>`
      + `<div class="ov-chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Phát sinh, đã thu và còn nợ cuối tháng, ${items.length} tháng `
      + `tới tháng ${monthLabel(items.at(-1).key)}">${area}<line class="ov-zero" x1="0" x2="${W}" y1="${zero}" y2="${zero}"/>${columns}`
      + `<polyline class="ov-line" points="${line}"/>${dots}${labels}</svg>${monthRow(items, item => `mở sổ tháng ${monthLabel(item.key)}: phát sinh `
        + `${full(item.chargesVnd ?? 0n)}, đã thu ${full(item.receivedVnd ?? 0n)}, còn nợ cuối tháng ${item.endVnd === null ? '–' : full(item.endVnd)}`)}</div>`
      + '<p class="ov-legend"><span><i class="ov-sw ps"></i>Phát sinh</span><span><i class="ov-sw thu"></i>Đã thu</span>'
      + '<span><i class="ov-sw line"></i>Còn nợ cuối tháng</span></p>');
  }

  // Khối 4: số chuyến mỗi tháng trong 6 tháng — dòng chuyến web (trừ đã xóa, đã loại và phí lẻ) và dòng chuyến sổ gốc chưa xóa;
  // đếm dòng, không phải tiền (chuyến chưa có giá, chờ kiểm vẫn là chuyến đã chạy). Lần đi hàng gần nhất lấy ở Tổng quan như
  // khối 1; sổ không có ở Tổng quan thì lấy ngày chuyến mới nhất trong sổ.
  function trips(data, items) {
    const counts = new Map(items.map(item => [item.key, 0]));
    let latest = '';
    const add = (month, date) => {
      if (counts.has(monthKey(month))) counts.set(monthKey(month), counts.get(monthKey(month)) + 1);
      if (/^\d{4}-\d\d-\d\d$/.test(date ?? '') && date > latest) latest = date;
    };
    for (const trip of data.trips ?? []) if (!trip.deleted && trip.status !== 'rejected' && !trip.is_fee_only) add(trip.month, trip.event_date);
    for (const row of data.legacy_rows ?? []) if (row.kind !== 'receipt' && !row.current?.deleted) add(row.month, row.current?.event_date);
    const row = loaded(side.debt) ? side.debt.data.row : null;
    const last = row?.last_trip_date ? (row.last_trip_exact ? dateText(row.last_trip_date) : `trong tháng ${monthLabel(row.last_trip_date)}`) : dateText(latest);
    // Khung hình gần bằng bề rộng khối ở màn 1280 (một phần ba trang) để số trên cột giữ cỡ chữ thật.
    const top = Math.max(1, ...counts.values()), W = 380, H = 124, BASE = 108, col = W / items.length;
    const bars = items.map((item, index) => {
      const count = counts.get(item.key), h = Math.round(count / top * 80), x = col * index;
      return `<g class="ov-col"${item.present ? ` data-go="thang:${item.key}"` : ''}><rect class="ov-hit" x="${x}" y="0" width="${col}" height="${H}"/>`
        + `<rect class="ov-bar trip" data-month="${item.key}" data-count="${count}" x="${x + col / 2 - 16}" y="${BASE - h}" width="32" height="${h}"/>`
        + `<text class="ov-num" x="${x + col / 2}" y="${BASE - h - 6}" text-anchor="middle">${count}</text></g>`;
    }).join('');
    return block('Khách còn đi hàng không?', `<p class="ov-note">Số chuyến mỗi tháng · ${last ? `đi hàng gần nhất ${last}` : 'chưa có chuyến'}</p>`
      + `<div class="ov-chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Số chuyến mỗi tháng, ${items.length} tháng tới tháng `
      + `${monthLabel(items.at(-1).key)}"><line class="ov-zero" x1="0" x2="${W}" y1="${BASE}" y2="${BASE}"/>${bars}</svg>`
      + `${monthRow(items, item => `mở sổ tháng ${monthLabel(item.key)}: ${counts.get(item.key)} chuyến`)}</div>`);
  }

  // Khối 5: việc làm số chưa đúng. Chuyến chưa có giá, chờ kiểm và chuyến từ Sheet đếm như chấm cam trên chip tháng (bookWork của
  // so-khach-v7-month-ui.js); lô giá, phiếu thu từ Sheet và phụ phí theo bảng PS như dải nút đầu thẻ Sổ. Mỗi dòng mở thẻ Sổ đúng
  // chỗ: ?loc= tô dòng cần xử lý, lô thì tới nút của lô. Tách phụ phí theo PS không đổi tổng tiền nên không vào câu "chưa tính".
  function todo(data) {
    const lot = (item, what, kind, verb) => {
      const parts = [[item?.ready_count ?? item?.ready?.length ?? 0, `chờ ${verb}`], [item?.review?.length ?? 0, 'cần xem']]
        .filter(([count]) => count > 0).map(([count, text]) => `${count} ${text}`);
      return parts.length ? [[`${what}: ${parts.join(', ')}`, `viec:${kind}`]] : [];
    };
    const rows = [...bookWork(data).map(([count, what, kind]) => [`${count} chuyến ${what}`, kind === 'sheet' ? 'viec:sheet' : `loc:${kind}`]),
      ...lot(data.sheet_prices, 'Giá từ Sheet', 'price', 'ghi'), ...lot(data.sheet_receipts, 'Phiếu thu từ Sheet', 'receipt', 'ghi')];
    const list = [...rows, ...lot(data.ps_fees, 'Phụ phí theo bảng PS', 'ps', 'tách')]
      .map(([text, go]) => `<div class="ov-task"><span>${escape(text)}</span>${button(go, 'Xem trong sổ', text)}</div>`).join('');
    return block('Còn gì làm số chưa đúng?', list
      ? `${list}${rows.length ? '<p class="ov-note">Còn nợ ở trên chưa tính các dòng này.</p>' : ''}` : '<p>Sổ không còn việc chờ.</p>');
  }

  // Khối 6, phần A: lần nhắc gần nhất (reminder_log, NHAC-NO-01) và tin Zalo gần nhất của hội thoại tìm theo tên khách, như thẻ
  // Trao đổi (PR A3). Hứa trả ở giai đoạn B2.
  function talk() {
    const item = side.reminders, chats = side.chats;
    const line = item.state === 'error' ? `${escape(loadError('lần nhắc nợ'))} ${button('retry:reminders', 'Thử lại')}`
      : !loaded(item) ? 'Đang đọc lần nhắc nợ…'
        : item.data ? escape(`Nhắc gần nhất ${dateText(item.data.last_reminded)} · ${SOURCE[item.data.last_source] ?? item.data.last_source} · `
          + `đã nhắc ${item.data.reminder_count} lần`) : 'Chưa nhắc lần nào.';
    const latest = loaded(chats) ? (chats.data.conversations ?? []).find(row => row.last_message_at) : null;
    const chat = chats.state === 'error' ? `${escape(loadError('hội thoại Zalo'))} ${button('retry:chats', 'Thử lại')}`
      : !loaded(chats) ? 'Đang tìm hội thoại Zalo…' : chats.data.conversations === null ? 'Chưa có dữ liệu chat trên máy chủ.'
        : latest ? escape(`Zalo gần nhất ${dateText(vnDay(latest.last_message_at))} · ${latest.display_name ?? 'hội thoại chưa rõ tên'}`)
          : 'Không thấy hội thoại Zalo có tên khách.';
    return block('Lần cuối nói chuyện với khách', `<p class="ov-talk"${item.state === 'error' ? ' role="alert"' : ''}>${line}</p>`
      + `<p class="ov-chat"${chats.state === 'error' ? ' role="alert"' : ''}>${chat}</p>`
      + '<button type="button" class="tab-go" data-the="trao-doi">Xem thẻ Trao đổi</button>');
  }

  function content(data) {
    if (data.status !== 'active') {
      return '<div class="ov-block" role="status"><p>Khách chưa có số dư đầu hiệu lực. Chưa có số để xem.</p>'
        + '<button type="button" class="tab-go" data-the="so">Mở thẻ Sổ</button></div>';
    }
    const series = model.monthSeries(data.months ?? [], thisMonth());
    return owed(data, series.items.at(-1)) + trend(series)
      + `<div class="ov-row">${trips(data, series.items.slice(-6))}${todo(data)}${talk()}</div>`;
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
    showTab('so');
    if (what === 'thang') openMonth(value);
    else if (what === 'loc') ctx.showLoc(value);
    else {
      window.scrollTo({ top: 0, behavior: 'instant' });
      root.querySelector(TASKS[value])?.focus({ preventScroll: true });
    }
  });

  Object.assign(ctx, { overviewPane, tabShown });
};
