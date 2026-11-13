/* Bảng sổ × loại việc của tab Dọn chi tiết (package 2/11, VIEC-DOI-CHIEU-01); render gom cả ba tab. */
globalThis.InboxTable = (() => {
  'use strict';
  const MACHINE_LOGIN = 'may-theo-sheet';
  const groups = [
    { key: 'money', label: 'Tiền vào sổ', keys: ['receipts', 'prices', 'missing', 'removed'] },
    { key: 'trips', label: 'Chuyến', keys: ['trips_new', 'trips_check', 'pending'] },
    { key: 'setup', label: 'Thiết lập sổ', keys: ['baseline', 'commodity', 'transport', 'ps', 'text_diff'] },
  ];
  const paths = {
    book: 'M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11',
    truck: 'M3 7h11v9H3zM14 10h4l3 3v3h-7z', receipt: 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6',
    pencil: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4', pick: 'M6 3h12a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3zM7.5 12.5l3 3 6-7',
    down: 'M6 9l6 6 6-6', up: 'M6 15l6-6 6 6', right: 'M9 6l6 6-6 6', left: 'M15 6l-6 6 6 6', check: 'M5 12.5l4.5 4.5L19 7',
    tag: 'M3 12V4h8l10 10-8 8zM7.5 7.5h.01',
  };
  const icon = (name, size = 14) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]}"/>${name === 'truck' ? '<circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>' : ''}</svg>`;
  const count = (b, key) => typeof b[key] === 'object' && b[key] !== null ? (b[key].count ?? b[key].ready + b[key].review) : b[key] ?? 0;
  function parseMillions(text) {
    const match = /^(\d+)(?:[,.](\d{1,6}))?$/.exec(String(text).trim());
    if (!match) throw Error('Nhập giá bằng triệu đồng, dùng dấu phẩy cho phần lẻ.');
    const value = BigInt(match[1]) * 1000000n + BigInt((match[2] ?? '').padEnd(6, '0'));
    if (value <= 0n || value > 9223372036854775807n) throw Error('Giá phải lớn hơn 0 và trong giới hạn số tiền.');
    return value.toString();
  }
  function million(value) {
    if (value == null) return '—';
    const n = BigInt(value), abs = n < 0n ? -n : n;
    const rounded = (abs + 50000n) / 100000n;
    return `${n < 0n ? '−' : ''}${(rounded / 10n).toLocaleString('vi-VN')}${rounded % 10n ? `,${rounded % 10n}` : ''}`;
  }
  function millionInput(value) {
    const n = BigInt(value), fraction = (n % 1000000n).toString().padStart(6, '0').replace(/0+$/, '');
    return `${n / 1000000n}${fraction ? ',' + fraction : ''}`;
  }
  // Chuyến chưa giá theo server (`is_missing_price`: chưa đơn giá và không phải dòng phí lẻ không container). Bản thiếu trường đó
  // thì tính theo cùng luật. Dòng phí lẻ đã tính nợ bằng phụ phí: ghi đơn giá vào đó là cộng nợ sai.
  const isMissing = r => r.status === 'confirmed' && r.unit_price_vnd == null
    && (typeof r.is_missing_price === 'boolean' ? r.is_missing_price : !(r.other_fee_vnd != null && !r.container));
  // GIA-TUYEN-01: chuyến chưa giá sửa được, gom theo nơi đi → nơi đến + shipper (bảng giá tách giá TT theo shipper, BANG-GIA-01).
  // Chuyến thiếu container, nơi đi hoặc nơi đến không gom. `last`: giá của chuyến đã có giá cùng khóa, ngày chuyến gần nhất; chỉ để gợi ý.
  function priceGroups(ledger) {
    const trips = ledger?.trips ?? [];
    const key = r => (r.origin && r.destination ? JSON.stringify([r.origin, r.destination, r.shipper ?? '']) : null);
    const last = new Map();
    for (const r of trips) {
      const k = key(r);
      if (!k || r.status !== 'confirmed' || r.unit_price_vnd == null || BigInt(r.unit_price_vnd) <= 0n) continue;
      const seen = last.get(k), date = r.event_date ?? '';
      if (!seen || date > seen.date || (date === seen.date && r.id > seen.id)) last.set(k, { price: r.unit_price_vnd, date, id: r.id });
    }
    const groups = new Map();
    for (const r of trips) {
      const k = key(r);
      if (!k || !r.container || !isMissing(r) || r.editable !== true) continue;
      if (!groups.has(k)) groups.set(k, { key: k, origin: r.origin, destination: r.destination, shipper: r.shipper ?? '', trips: [], last: last.get(k) ?? null });
      groups.get(k).trips.push(r);
    }
    const list = [...groups.values()];
    for (const g of list) {
      g.trips.sort((a, b) => (a.event_date ?? '').localeCompare(b.event_date ?? '') || a.id - b.id);
      // Shipper chỉ ghi ra khi cùng tuyến có nhiều nhóm, để không thêm chữ thừa.
      const twins = list.filter(o => o.origin === g.origin && o.destination === g.destination).length > 1;
      g.label = `${g.origin} → ${g.destination}${twins ? ` · ${g.shipper || 'không shipper'}` : ''}`;
    }
    return list.sort((a, b) => b.trips.length - a.trips.length || (a.trips[0].event_date ?? '').localeCompare(b.trips[0].event_date ?? ''));
  }
  // MAY-DOI-SOAT-01: sổ đã khớp Sheet ở lượt đối soát gần nhất, tổng chưa đổi từ đó: việc từ Sheet và "chưa giá" còn treo không làm số
  // đúng hơn nên không tính vào số trên menu. Chờ kiểm, số dư đầu, mặt hàng vẫn tính vì chỉ người quyết được. Tab Dọn chi tiết hiện hết.
  function books(data, dashboard, unsorted = [], showMatched = false) {
    const map = new Map((data?.books ?? []).filter(b => showMatched || !b.sheet_matched).map(b => [b.customer_id, { ...b }]));
    const add = (items, key) => (items ?? []).forEach(item => {
      if (!map.has(item.customer_id)) map.set(item.customer_id, { customer_id: item.customer_id });
      map.get(item.customer_id)[key] = item.count ?? 1;
    });
    const settled = new Set(showMatched ? [] : data?.reconcile?.matched_ids ?? []);
    add(dashboard?.todo.missing_price.filter(item => !settled.has(item.customer_id)), 'missing'); add(dashboard?.todo.pending_review, 'pending');
    add(dashboard?.todo.no_baseline, 'baseline');
    // Sổ đã có mặt hàng mà vẫn "chưa phân loại" là Sầu riêng thiếu cảng/bộ: chỉ hỏi đúng phần còn thiếu.
    add(unsorted.filter(item => !item.commodity), 'commodity'); add(unsorted.filter(item => item.commodity), 'transport');
    return [...map.values()].filter(b => groups.some(g => g.keys.some(key => count(b, key))));
  }
  function render(data, opts) {
    const { F, esc, label, href, dashboard, unsorted, selected = new Set(), selectedPrices = new Set(), review, result, busy, filter, open, details, tab = 'lech', dc } = opts;
    const old = globalThis.InboxCard;
    const view = globalThis.DoiChieuView;
    const now = opts.now ?? Date.now();
    const reconcile = data?.reconcile;
    // Khoản của khách lệch nằm ở bảng đối chiếu; ở đây chỉ còn phần không làm số nợ đúng hơn (VIEC-DOI-CHIEU-01).
    const inStatement = globalThis.DoiChieuModel.openIds(reconcile);
    const strip = b => (inStatement.has(b.customer_id) ? { ...b, inStatement: true, receipts: { ready: 0, review: 0 }, prices: { ready: 0, review: 0 } } : b);
    const rank = b => (count(b, 'removed') ? 1000000 : 0) + Number(BigInt(b.receipts?.ready_amount_vnd ?? '0') / 100000n) + count(b, 'missing') + (groups[0].keys.some(k => count(b, k)) ? 1 : 0);
    const list = books(data, dashboard, unsorted ?? [], true).map(strip).filter(b => groups.some(g => g.keys.some(key => count(b, key)))).sort((a, b) => rank(b) - rank(a) || label(a).localeCompare(label(b), 'vi'));
    const ready = list.filter(b => b.receipts && old.canWrite(b));
    const selectedCount = list.reduce((n, b) => n + (selected.has(b.customer_id) ? b.receipts.ready : 0) + (selectedPrices.has(b.customer_id) ? b.prices.ready : 0), 0);
    const hasReady = ready.length || list.some(b => b.prices?.ready);
    const partial = !data || ['computing', 'unavailable'].includes(data.state) || data.failed?.length || !dashboard || opts.unsorted === null;
    const total = list.length ? `<strong>${list.length}</strong><span>sổ còn việc</span>` : partial ? '<strong>Chưa đủ dữ liệu</strong>' : '<strong class="all-done">Hết việc</strong>';
    const computing = data?.state === 'computing' ? `đang tính việc từ Sheet ${data.books_done ?? 0}/${data.books_total ?? '—'} sổ` : '';
    const person = (name, trips, second, index, tip, machine = false, prices = 0) => `<span class="actor-chip actor-${index % 3}" title="${esc(tip)}"><i aria-hidden="true">${esc(name.slice(0, 1))}</i><b>${esc(name)}</b><span>${icon('truck')}<strong>${trips}</strong></span><span>${icon(machine ? 'pencil' : 'receipt')}<strong>${second}</strong></span>${prices ? `<span>${icon('tag')}<strong>${prices}</strong></span>` : ''}</span>`;
    const bot = data?.auto ?? {};
    // Máy có chip riêng với chi tiết chữ, chuyến, giá; dòng của máy trong số liệu hôm nay chỉ dùng khi chưa có chip đó, và không hiện tên kỹ thuật.
    const botChip = bot.today_count || bot.today_trips || bot.today_prices || bot.today_ps;
    const people = (dashboard?.today.by_actor ?? []).filter(p => p.actor !== MACHINE_LOGIN || !botChip).map((p, i) => { const name = p.actor === MACHINE_LOGIN ? 'Máy' : p.actor; return person(name, p.trips, p.receipts, i, `${name}: ${p.trips} chuyến, ${p.receipts} phiếu thu ${F.full(p.received_vnd)}, hủy ${p.voids} phiếu`); }).join('')
      + (botChip ? person('Máy', bot.today_trips ?? 0, bot.today_count ?? 0, 2, `Máy theo Sheet hôm nay: ${bot.today_trips ?? 0} chuyến mới, ${bot.today_count ?? 0} ô chữ, ${bot.today_prices ?? 0} giá${bot.today_ps ? `, ${bot.today_ps} phụ phí phân loại` : ''}`, true, bot.today_prices ?? 0) : '');
    const errors = !data ? `<p class="inbox-error" role="alert">${esc(opts.failedText)} <button type="button" class="btn" data-inbox-retry>Thử lại</button></p>` : data.state === 'unavailable' ? '<p class="inbox-note warn">Chưa đọc được bản lấy từ Sheet. Bấm Làm mới để lấy lại; việc dưới đây có thể thiếu.</p>' : data.failed?.length ? `<p class="inbox-note warn">${data.failed.length} sổ chưa tính được, việc của các sổ này có thể thiếu.</p>` : '';
    const nothing = !data || !dashboard ? 'Chưa đủ dữ liệu' : undefined;
    const showFilters = list.length >= 5;
    const chips = !showFilters ? '' : `<button type="button" class="filter-chip" data-filter="" aria-pressed="${!filter}">Tất cả</button>${groups.map(g => `<button type="button" class="filter-chip" data-filter="${g.key}" aria-pressed="${filter === g.key}" title="Một sổ có thể có nhiều loại việc · bấm để lọc"><span>${g.label}</span><b>${icon('book')}${list.filter(b => g.keys.some(key => count(b, key))).length}</b></button>`).join('')}`;
    const toggle = b => `data-open-book="${b.customer_id}" aria-expanded="${open === b.customer_id}" aria-controls="book-detail-${b.customer_id}"`;
    const pill = (b, n, text, tone = '') => `<button type="button" class="work-pill ${tone}" ${toggle(b)} title="Bấm để xử lý ngay tại dòng"><strong>${n}</strong>${text}</button>`;
    const cell = (b, key) => {
      const n = count(b, key); if (!n) return '';
      if (key === 'receipts') return `${old.canWrite(b) ? `<label class="ready-pick" title="${b.receipts.ready} phiếu sẵn sàng · ${esc(F.full(b.receipts.ready_amount_vnd))}"><input type="checkbox" data-pick="${b.customer_id}" aria-label="Chọn phiếu thu của ${esc(label(b))}"${selected.has(b.customer_id) ? ' checked' : ''}${busy ? ' disabled' : ''}>${million(b.receipts.ready_amount_vnd)} tr</label>` : b.receipts.ready ? pill(b, b.receipts.ready, 'chưa đủ dữ liệu', 'warn') : ''}${b.receipts.review ? pill(b, old.canWrite(b) ? `+${b.receipts.review}` : b.receipts.review, old.canWrite(b) ? '' : 'cần xem', 'warn') : ''}`;
      if (key === 'prices') return `${b.prices.ready ? `<label class="ready-pick"><input type="checkbox" data-pick-price="${b.customer_id}" aria-label="Chọn giá Sheet của ${esc(label(b))}"${selectedPrices.has(b.customer_id) ? ' checked' : ''}${busy ? ' disabled' : ''}>${b.prices.ready} giá Sheet</label>` : ''}${b.prices.review ? pill(b, b.prices.review, 'giá khác', 'warn') : ''}`;
      const words = { missing: 'chưa giá', removed: 'Sheet xóa', trips_new: 'mới', baseline: 'số dư', commodity: 'mặt hàng', transport: 'cảng/bộ', ps: 'PS', text_diff: 'ô chữ' };
      return pill(b, ['baseline', 'commodity', 'transport'].includes(key) ? '' : n, words[key], key === 'removed' ? 'danger' : key === 'missing' ? 'warn' : '');
    };
    const columns = [['receipts'], ['prices', 'missing'], ['removed', 'checks', 'trips_new'], ['baseline', 'commodity', 'transport', 'ps', 'text_diff']];
    const dim = i => filter && (i < 2 ? 'money' : i === 2 ? 'trips' : 'setup') !== filter ? ' class="dimmed"' : '';
    const shown = list.filter(b => !filter || groups.find(g => g.key === filter)?.keys.some(key => count(b, key)));
    const rows = shown.map(b => {
      const failed = result?.books?.find(row => row.customer_id === b.customer_id && !row.ok);
      const detail = open === b.customer_id ? `<tr class="work-detail" id="book-detail-${b.customer_id}"><td colspan="6">${detailHtml(b, details?.get(b.customer_id), opts)}<a class="open-book" href="${href(b.customer_id)}">Mở cả sổ ${icon('right')}</a></td></tr>` : '';
      return `<tr class="work-row${open === b.customer_id ? ' expanded' : ''}${count(b, 'removed') ? ' has-removed' : ''}" data-book="${b.customer_id}"><th scope="row"><button class="book-name" type="button" ${toggle(b)} title="Bấm để xử lý việc của ${esc(label(b))} ngay tại đây">${esc(label(b))}</button>${failed ? `<p class="row-error" role="alert">${esc(failed.message)}</p>` : ''}</th>${columns.map((keys, i) => `<td${dim(i)}><div class="cell-pills">${keys.map(key => key === 'checks' ? count(b, 'trips_check') + count(b, 'pending') ? pill(b, count(b, 'trips_check') + count(b, 'pending'), 'cần xem', 'warn') : '' : cell(b, key)).join('')}</div></td>`).join('')}<td><button class="row-toggle" type="button" ${toggle(b)} aria-label="${open === b.customer_id ? 'Đóng' : 'Xử lý'} sổ ${esc(label(b))}">${icon(open === b.customer_id ? 'up' : 'down', 16)}</button></td></tr>${detail}`;
    }).join('');
    const totalCount = key => list.reduce((sum, b) => sum + count(b, key), 0);
    const footPart = key => {
      const n = totalCount(key);
      if (key === 'checks') return totalCount('trips_check') + totalCount('pending') ? `${totalCount('trips_check') + totalCount('pending')} cần xem` : '';
      if (!n) return '';
      if (key === 'receipts') return `${million(F.sum(ready.map(b => b.receipts.ready_amount_vnd)))} tr${list.reduce((s, b) => s + (b.receipts?.review ?? 0), 0) ? ` +${list.reduce((s, b) => s + (b.receipts?.review ?? 0), 0)}` : ''}`;
      if (key === 'prices') return [list.reduce((s, b) => s + (b.prices?.ready ?? 0), 0), list.reduce((s, b) => s + (b.prices?.review ?? 0), 0)].map((n, i) => n ? `${n} ${i ? 'giá khác' : 'giá Sheet'}` : '').filter(Boolean).join(' · ');
      return `${n} ${{ missing: 'chưa giá', removed: 'Sheet xóa', trips_new: 'mới', baseline: 'số dư đầu', commodity: 'mặt hàng', transport: 'cảng/bộ', ps: 'PS', text_diff: 'ô chữ' }[key]}`;
    };
    const foot = showFilters ? `<tfoot><tr><th scope="row">Cộng</th>${columns.map((keys, i) => `<td${dim(i)}>${keys.map(footPart).filter(Boolean).join(' · ')}</td>`).join('')}<td></td></tr></tfoot>` : '';
    const table = shown.length ? `<div class="work-scroll"><table class="work-table"><thead><tr><th scope="col">Khách</th>${['Phiếu thu <span class="muted">tr</span>', 'Giá chuyến', 'Chuyến cần xử lý', 'Thiết lập sổ'].map((text, i) => `<th scope="col"${dim(i)}>${text}</th>`).join('')}<th scope="col"><span class="sr-only">Mở</span></th></tr></thead><tbody>${rows}</tbody>${foot}</table></div>` : `<p class="empty">${icon('check', 28)}${filter ? 'Không có sổ nào có việc loại này.' : partial ? 'Đang chờ đủ dữ liệu để tính việc.' : 'Hôm nay không còn việc.'}</p>`;
    const textCount = totalCount('text_diff');
    const textNote = textCount ? `<p class="inbox-note">Lệch chữ: ${textCount} chỗ ở ${list.filter(b => b.text_diff > 0).length} sổ. Không đụng tiền; ${data?.auto?.text_enabled ? 'máy lấy theo Sheet ở lượt tính tới.' : 'máy chưa bật tự lấy theo Sheet.'}</p>` : '';
    const don = `<section class="inbox work-card" aria-labelledby="h-inbox"><div class="work-toolbar"><h2 id="h-inbox" class="band-count">${total}</h2>${chips}${hasReady ? `<button class="btn pick-ready" type="button" data-pick-ready${busy ? ' disabled' : ''}>${icon('pick', 17)}Chọn hết mục sẵn sàng ghi</button>` : ''}${selectedCount ? `<button class="btn primary" type="button" data-review${busy ? ' disabled' : ''}>Xem lại ${selectedCount} mục ${icon('right', 16)}</button>` : ''}</div><p class="dc-lead">Các việc này không làm tổng nợ lệch Sheet. Làm khi rảnh; để đó số nợ vẫn đúng.</p>${review?.length ? `<div class="work-scroll">${old.reviewHtml(review, F, esc, label, busy)}</div>` : ''}${opts.actionHtml ?? ''}${opts.undoHtml ?? ''}${table}${textNote}</section>`;
    const lech = view.lechHtml(reconcile, dc, { F, esc, href, now, action: opts.action, busy, nothing });
    const may = view.mayHtml(opts.act, people, { esc, href });
    const counts = { lech: globalThis.DoiChieuModel.openRows(reconcile).length + (reconcile?.outside_tabs?.length ?? 0), don: list.length, may: view.machineCount(bot, reconcile) };
    return `${view.statusHtml(reconcile, { esc, now, stale: opts.stale, computing, nothing, F, href, tongOpen: opts.tongOpen })}${errors}${view.tabsHtml(tab, counts)}${old.resultHtml(result, F, esc, label, href)}${opts.notice ? (opts.notice.warn ? `<p class="inbox-result warn" role="alert">${esc(opts.notice.text)}</p>` : `<p class="inbox-result" role="status">${icon('check', 18)}${esc(opts.notice)}</p>`) : ''}<div class="viec-panel" role="tabpanel">${tab === 'don' ? don : tab === 'may' ? may : lech}</div>`;
  }
  function detailHtml(book, ledger, opts) {
    const { F, esc, href, action } = opts;
    const day = iso => iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : '—';
    const link = text => `<a href="${href(book.customer_id)}">${text}${icon('right')}</a>`;
    const btn = (text, attrs, tone = '') => `<button type="button" class="btn ${tone}" ${attrs}${opts.busy ? ' disabled' : ''}>${text}</button>`;
    // `more.cls`: lớp thêm cho dòng (hàng tuyến, chuyến trong tuyến); `more.dateText`: chữ ở cột ngày thay cho ngày của dòng.
    const item = (obj, date, desc, amount, buttons, key = '', more = {}) => {
      const pending = action?.rowKey === key;
      return `<li class="${[pending ? 'pending-action' : '', more.cls ?? ''].join(' ').trim()}"${key ? ` data-detail-key="${esc(key)}"` : ''}><b title="${esc(obj)}">${esc(obj)}</b><span>${esc(more.dateText ?? day(date))}</span><span class="detail-description${pending ? ' action-description' : ''}" title="${esc(pending ? action.text : desc)}">${pending ? `<span id="h-action">${esc(action.inlineText ?? action.text)}</span>` : esc(desc)}</span><b class="money" title="${amount == null ? '' : esc(F.full(amount))}">${amount == null ? '' : million(amount)}</b><div class="detail-actions">${pending ? `${action.path ? btn(action.unknown ? 'Thử lại' : 'Xác nhận', 'data-action-write', 'primary') : ''}${action.unknown ? '' : btn('Thôi', 'data-action-cancel')}` : buttons}</div>${pending && action.reasonRequired ? `<label class="review-reason">Lý do kết luận <input data-action-reason maxlength="500" required aria-label="Lý do kết luận ${esc(obj)}" value="${esc(action.body.reason)}"${action.unknown ? ' disabled' : ''}></label>` : ''}${pending && action.error ? `<p class="row-error" role="alert">${esc(action.error)}</p>` : ''}</li>`;
    };
    const section = (label, rows, hint, tone = '', countText = null) => rows.length ? `<section class="detail-group ${tone}"><h3><i></i>${label}<span>${countText ?? `${rows.length} ${{ 'Phiếu cần xem': 'phiếu', 'Thiết lập sổ': 'việc' }[label] ?? 'chuyến'}`}</span><small>· ${hint}</small></h3><ul class="detail-items">${rows.join('')}</ul></section>` : '';
    const receiptRows = (book.inStatement ? [] : ledger?.sheet_receipts?.review ?? book.receipts?.items?.filter(r => r.status !== 'READY') ?? []).map(r => item('Phiếu thu', r.date, r.note || 'Máy chưa tự khớp được phiếu này; đối chiếu chứng từ trong sổ', r.amount_vnd,
      r.status === 'NO_DATE' && r.source_fingerprint && r.debt_month
        ? `<input class="inline-price" data-receipt-date="${r.source_fingerprint}" placeholder="ngày dd/mm" aria-label="Ngày phiếu thu năm ${esc(r.debt_month.slice(0, 4))}">${btn('Ghi phiếu', `data-record-sheet-receipt="${r.source_fingerprint}"`)}`
        : link('Xem phiếu trong sổ'), `receipt:${r.source_fingerprint}`));
    if (ledger === undefined || ledger === null) return section('Phiếu cần xem', receiptRows, 'máy chỉ tự ghi khi khớp đúng tổng Sheet', 'warn') + (ledger === undefined ? '<p class="loading">Đang tải chi tiết sổ…</p>' : `<p role="alert">Không tải được chi tiết sổ. ${btn('Thử lại', `data-detail-retry="${book.customer_id}"`)}</p>`);
    const removed = (ledger.sheet_sync?.removed_items ?? []).map(r => item(r.container, r.event_date ?? r.date, `${r.origin ?? ''}${r.destination ? ` → ${r.destination}` : ''} · Sheet không còn dòng này`, r.amount_vnd,
      r.month_locked ? link('Mở trong sổ') : `${btn('Xóa chuyến', `data-remove-trip="${r.trip_id}"`, 'danger')}${btn('Giữ', `data-keep-trip="${r.trip_id}"`)}`, `removed:${r.trip_id}`));
    const fee = value => (value == null ? 'trống' : million(value));
    const conflictText = r => (r.web_unit_price_vnd === r.sheet_unit_price_vnd ? `Đơn giá ${million(r.web_unit_price_vnd)} · phụ phí web ${fee(r.web_other_fee_vnd)} → Sheet ${fee(r.sheet_other_fee_vnd)}` : `Trên web ${million(r.web_unit_price_vnd)} · trên Sheet ${million(r.sheet_unit_price_vnd)}`);
    const prices = (book.inStatement ? [] : ledger.sheet_prices?.review ?? []).map(r => item(r.container, r.date, r.status === 'CONFLICT' ? conflictText(r) : 'Cần đối chiếu giá trong sổ', null, r.status === 'CONFLICT' && r.source_fingerprint ? `${r.month_locked ? '' : btn('Lấy giá Sheet', `data-use-sheet-price="${r.target_kind}:${r.target_id}"`)}${btn('Giữ giá web', `data-keep-price="${r.target_kind}:${r.target_id}"`)}${link('Mở để đối chiếu')}` : link('Mở để đối chiếu'), `sheet-price:${r.target_kind}:${r.target_id}`));
    const suggestedOf = r => {
      const rate = ledger.price_status?.trips?.find(p => p.trip_id === r.id && p.ready)?.lookup?.unit_price_vnd;
      return rate == null ? '' : millionInput(rate);
    };
    const tripItem = (r, group = null) => {
      const suggested = suggestedOf(r);
      const hint = suggested ? `bảng giá gợi ý ${suggested}` : group ? '' : 'sổ chưa có giá gợi ý';
      // Chuyến trong một tuyến: tuyến đã ở hàng trên, dòng chỉ còn gợi ý của bảng giá (nếu có).
      const desc = group ? hint : `${r.origin ?? ''}${r.destination ? ` → ${r.destination}` : ''} · ${hint}`;
      return item(r.container, r.event_date, desc, null,
        r.editable === true ? `<input class="inline-price" inputmode="decimal" aria-label="Đơn giá triệu đồng cho ${esc(r.container)}" data-manual-price="${r.id}"${group ? ` data-price-route="${esc(group.key)}"` : ''} data-suggested-price="${suggested}" placeholder="giá, tr">${btn('Ghi giá', `data-command="price" data-trip="${r.id}"`)}` : link('Mở trong sổ'), `price:${r.id}`, group ? { cls: 'price-child' } : {});
    };
    // Tuyến có từ hai chuyến: một hàng tuyến gõ giá một lần, điền xuống các chuyến bên dưới (GIA-TUYEN-01).
    const groupItem = g => {
      const shared = new Set(g.trips.map(suggestedOf));
      const common = shared.size === 1 ? [...shared][0] : '';
      const range = `${day(g.trips[0].event_date)}${g.trips.length > 1 && g.trips.at(-1).event_date !== g.trips[0].event_date ? `–${day(g.trips.at(-1).event_date)}` : ''}`;
      // Giá gần nhất là nút điền (người bấm mới vào ô), đặt ở vùng thao tác để tên tuyến không bị cắt.
      const last = g.last ? `<button type="button" class="use-last" data-use-last="${esc(g.key)}" data-last-price="${millionInput(g.last.price)}" title="Điền giá của chuyến gần nhất cùng tuyến đã có giá (${esc(F.dateText(g.last.date))})"${opts.busy ? ' disabled' : ''}>Giá gần nhất ${millionInput(g.last.price)} tr · ${esc(day(g.last.date))}</button>` : '';
      return item(`${g.trips.length} chuyến`, null, `${g.label} · ${range}`, null,
        `${last}<input class="inline-price" inputmode="decimal" aria-label="Đơn giá triệu đồng cho cả tuyến ${esc(g.label)}" data-group-price="${esc(g.key)}" data-suggested-price="${common}" placeholder="giá, tr">${btn('Ghi giá', `data-price-group="${esc(g.key)}"`, 'primary group-write')}`,
        `price-group:${g.key}`, { cls: 'price-group', dateText: '' });
    };
    const missingTrips = (ledger.trips ?? []).filter(isMissing);
    const groups = priceGroups(ledger).filter(g => g.trips.length > 1);
    const grouped = new Set(groups.flatMap(g => g.trips.map(r => r.id)));
    const missing = [...groups.flatMap(g => [groupItem(g), ...g.trips.map(r => tripItem(r, g))]), ...missingTrips.filter(r => !grouped.has(r.id)).map(r => tripItem(r))];
    const routeCount = groups.length + missingTrips.length - grouped.size;
    const missingCount = `${missingTrips.length} chuyến${groups.length ? ` · ${routeCount} tuyến` : ''}`;
    const pending = (ledger.trips ?? []).filter(r => r.status === 'pending_review').map(r => item(r.container, r.event_date, r.review_reason || 'Nghi trùng, chưa cộng vào nợ', r.unit_price_vnd == null ? null : SoKhachV7Model.tripAmount({ unitPriceVnd: r.unit_price_vnd, otherFeeVnd: r.other_fee_vnd, container: r.container, status: 'confirmed' }).amountVnd?.toString(),
      r.editable === true ? `${btn(r.unit_price_vnd == null ? 'Đúng, giữ' : 'Đúng, tính nợ', `data-command="confirm" data-trip="${r.id}"`)}${btn('Trùng, bỏ', `data-command="reject" data-trip="${r.id}"`)}` : link('Mở trong sổ'), `review:${r.id}`));
    // Chuyến bộ (NGUON-CHUYEN-01): dòng của sheet_road mang sẵn `message`; máy đưa vào sổ, người mở sổ khi vướng.
    const sheet = [...(ledger.sheet_sync?.items ?? []), ...(ledger.sheet_road?.items ?? [])].filter(r => ['NEW', 'CONFLICT'].includes(r.sync_state)).map(r => item(r.container, r.event_date ?? r.date, r.message || { OTHER_BOOK_LEGACY: 'Đã có ở sổ khác · sửa tên khách trên Sheet nếu nhầm', OTHER_CUSTOMER: 'Container ở khách khác', COMMODITY_UNKNOWN: 'Sheet chưa ghi mặt hàng', DIFFERENT_FIELDS: 'Sheet khác thông tin trong sổ', CONTAINER_REUSED_OR_CHANGED: 'Container đã có trong sổ · tab khách chưa có dòng riêng' }[r.sync_reason] || 'Máy chưa chắc vào sổ nào', null,
      r.sync_state === 'NEW' && r.candidate_books?.length && r.source_fingerprint
        ? `<select class="inline-price" data-trip-book="${r.source_fingerprint}" aria-label="Sổ nhận chuyến ${esc(r.container)}"><option value="">Chọn sổ</option>${r.candidate_books.map(c => `<option value="${c.id}">${esc(c.commodity ? `Sổ ${c.commodity}` : c.display_name ?? c.name)}</option>`).join('')}</select>${btn('Vào sổ', `data-assign-trip="${r.source_fingerprint}"`)}`
        : link('Mở trong sổ'), `assignment:${r.source_fingerprint}`));
    const ps = [...(ledger.ps_fees?.ready ?? []), ...(ledger.ps_fees?.review ?? [])].map(r => item(r.container || 'Dòng PS', r.event_date ?? r.date, 'Tách vào cột phụ phí · không đổi tổng tiền', null, link('Mở trong sổ')));
    const setup = [book.baseline ? item('Số dư đầu kỳ', null, 'Chưa có · đối chiếu sổ gốc rồi nhập', null, link('Mở sổ để nhập')) : '', book.commodity ? item('Mặt hàng', null, 'Chưa gán mặt hàng chính của sổ', null, `<select class="inline-price" data-commodity="${book.customer_id}" aria-label="Mặt hàng của sổ"><option value="">Chọn mặt hàng</option>${['Sầu riêng', 'Thanh long', 'Chuối', 'Mít', 'Dừa'].map(name => `<option>${name}</option>`).join('')}</select>${btn('Lưu', 'data-save-commodity')}`, 'commodity') : '',
      book.transport ? item('Cảng/bộ', null, 'Sổ sầu riêng chưa rõ đi cảng hay đi bộ', null, `<select class="inline-price" data-transport="${book.customer_id}" aria-label="Cảng hay bộ của sổ"><option value="">Chọn cảng/bộ</option><option value="CANG">Cảng</option><option value="BO">Bộ</option></select>${btn('Lưu', 'data-save-transport')}`, 'transport') : ''].filter(Boolean);
    // ponytail: phụ phí PS và số dư đầu chưa có lệnh xử lý tại dòng; hai nhóm này vẫn mở sổ thật.
    return section('Sheet đã xóa', removed, 'đang tính nợ nhưng Sheet không còn, nợ có thể thừa', 'danger')
      + section('Phiếu cần xem', receiptRows, 'máy chỉ tự ghi khi khớp đúng tổng Sheet', 'warn')
      + section('Giá khác', prices, 'hai giá cho cùng chuyến, chọn một', 'warn')
      + section('Chưa giá', missing, groups.length ? 'chưa cộng vào nợ · gõ giá ở hàng tuyến để điền cả tuyến' : 'chưa cộng vào nợ', 'warn', missingCount)
      + section('Chờ kiểm', pending, 'nghi trùng, chưa cộng vào nợ', 'warn')
      + section('Chuyến mới / ở sổ khác', sheet, 'máy chưa chắc vào sổ nào')
      + (ledger.sheet_sync?.items?.some(r => r.sync_state === 'NEW') ? btn('Vào sổ · chuyến mới', 'data-command="approve"') : '')
      + section('Phụ phí PS', ps, 'không đổi tổng tiền')
      + (ledger.ps_fees?.ready?.length ? btn(`Tách ${ledger.ps_fees.ready.length} dòng`, 'data-command="ps"') : '')
      + section('Thiết lập sổ', setup, 'cần đối chiếu sổ gốc');
  }
  return { render, books, count, parseMillions, million, millionInput, priceGroups, icon };
})();
