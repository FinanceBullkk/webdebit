/* Giá trị và hành vi thị giác theo package Việc cần làm bốn cột ngày 2/11. */
globalThis.InboxTable = (() => {
  'use strict';
  const groups = [
    { key: 'money', label: 'Tiền vào sổ', keys: ['receipts', 'prices', 'missing', 'removed'] },
    { key: 'trips', label: 'Chuyến', keys: ['trips_new', 'trips_check', 'pending'] },
    { key: 'setup', label: 'Thiết lập sổ', keys: ['baseline', 'commodity', 'ps', 'text_diff'] },
  ];
  const paths = {
    book: 'M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11',
    truck: 'M3 7h11v9H3zM14 10h4l3 3v3h-7z', receipt: 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6',
    pencil: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4', pick: 'M6 3h12a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3zM7.5 12.5l3 3 6-7',
    down: 'M6 9l6 6 6-6', up: 'M6 15l6-6 6 6', right: 'M9 6l6 6-6 6', check: 'M5 12.5l4.5 4.5L19 7',
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
  function books(data, dashboard, unsorted = []) {
    const map = new Map((data?.books ?? []).map(b => [b.customer_id, { ...b }]));
    const add = (items, key) => (items ?? []).forEach(item => {
      if (!map.has(item.customer_id)) map.set(item.customer_id, { customer_id: item.customer_id });
      map.get(item.customer_id)[key] = item.count ?? 1;
    });
    add(dashboard?.todo.missing_price, 'missing'); add(dashboard?.todo.pending_review, 'pending');
    add(dashboard?.todo.no_baseline, 'baseline'); add(unsorted, 'commodity');
    return [...map.values()].filter(b => groups.some(g => g.keys.some(key => count(b, key))));
  }
  function render(data, opts) {
    const { F, esc, label, href, dashboard, unsorted, selected = new Set(), selectedPrices = new Set(), review, result, busy, filter, open, details } = opts;
    const old = globalThis.InboxCard;
    const rank = b => (count(b, 'removed') ? 1000000 : 0) + Number(BigInt(b.receipts?.ready_amount_vnd ?? '0') / 100000n) + count(b, 'missing') + (groups[0].keys.some(k => count(b, k)) ? 1 : 0);
    const list = books(data, dashboard, unsorted ?? []).sort((a, b) => rank(b) - rank(a) || label(a).localeCompare(label(b), 'vi'));
    const ready = list.filter(b => b.receipts && old.canWrite(b));
    const selectedCount = list.reduce((n, b) => n + (selected.has(b.customer_id) ? b.receipts.ready : 0) + (selectedPrices.has(b.customer_id) ? b.prices.ready : 0), 0);
    const hasReady = ready.length || list.some(b => b.prices?.ready);
    const partial = !data || ['computing', 'unavailable'].includes(data.state) || data.failed?.length || !dashboard || opts.unsorted === null;
    const total = list.length ? `<strong>${list.length}</strong><span>sổ còn việc</span>` : partial ? '<strong>Chưa đủ dữ liệu</strong>' : '<strong class="all-done">Hết việc</strong>';
    const progress = data?.state === 'computing' ? `<span class="computing">đang tính việc từ Sheet ${data.books_done ?? 0}/${data.books_total ?? '—'} sổ</span>` : '';
    const person = (name, trips, second, index, tip, machine = false) => `<span class="actor-chip actor-${index % 3}" title="${esc(tip)}"><i aria-hidden="true">${esc(name.slice(0, 1))}</i><b>${esc(name)}</b><span>${icon('truck')}<strong>${trips}</strong></span><span>${icon(machine ? 'pencil' : 'receipt')}<strong>${second}</strong></span></span>`;
    const people = (dashboard?.today.by_actor ?? []).map((p, i) => person(p.actor, p.trips, p.receipts, i, `${p.actor}: ${p.trips} chuyến, ${p.receipts} phiếu thu ${F.full(p.received_vnd)}, hủy ${p.voids} phiếu`)).join('')
      + (data?.auto?.today_count || data?.auto?.today_trips ? person('Máy', data.auto.today_trips ?? 0, data.auto.today_count ?? 0, 2, 'Máy theo Sheet: chuyến mới và ô chữ đã lấy hôm nay', true) : '');
    const auto = old.autoHtml(data?.auto, esc, label, href);
    const band = `<section class="work-band" aria-label="Còn việc và đã ghi hôm nay"><div class="band-count">${total}</div>${hasReady ? `<button class="btn pick-ready" type="button" data-pick-ready${busy ? ' disabled' : ''}>${icon('pick', 17)}Chọn hết mục sẵn sàng ghi</button>` : ''}${progress}<div class="today-inline"><span>Đã ghi hôm nay</span>${people || '<span class="muted">Chưa có giao dịch nào hôm nay.</span>'}${auto ? `<button class="btn auto-toggle" type="button" data-auto aria-expanded="${!!opts.showAuto}">Soát ${icon(opts.showAuto ? 'up' : 'down')}</button>` : ''}</div>${auto && opts.showAuto ? `<div class="auto-list">${auto}</div>` : ''}</section>`;
    const errors = !data ? `<p class="inbox-error" role="alert">${esc(opts.failedText)} <button type="button" class="btn" data-inbox-retry>Thử lại</button></p>` : data.state === 'unavailable' ? '<p class="inbox-note warn">Chưa đọc được bản lấy từ Sheet. Bấm Làm mới để lấy lại; việc dưới đây có thể thiếu.</p>' : data.failed?.length ? `<p class="inbox-note warn">${data.failed.length} sổ chưa tính được, việc của các sổ này có thể thiếu.</p>` : '';
    const chips = `<h2 id="h-inbox">Việc chờ theo sổ</h2><button type="button" class="filter-chip" data-filter="" aria-pressed="${!filter}">Tất cả</button>${groups.map(g => `<button type="button" class="filter-chip" data-filter="${g.key}" aria-pressed="${filter === g.key}" title="Một sổ có thể có nhiều loại việc · bấm để lọc"><span>${g.label}</span><b>${icon('book')}${list.filter(b => g.keys.some(key => count(b, key))).length}</b></button>`).join('')}`;
    const toggle = b => `data-open-book="${b.customer_id}" aria-expanded="${open === b.customer_id}" aria-controls="book-detail-${b.customer_id}"`;
    const pill = (b, n, text, tone = '') => `<button type="button" class="work-pill ${tone}" ${toggle(b)} title="Bấm để xử lý ngay tại dòng"><strong>${n}</strong>${text}</button>`;
    const cell = (b, key) => {
      const n = count(b, key); if (!n) return '';
      if (key === 'receipts') return `${old.canWrite(b) ? `<label class="ready-pick" title="${b.receipts.ready} phiếu sẵn sàng · ${esc(F.full(b.receipts.ready_amount_vnd))}"><input type="checkbox" data-pick="${b.customer_id}" aria-label="Chọn phiếu thu của ${esc(label(b))}"${selected.has(b.customer_id) ? ' checked' : ''}${busy ? ' disabled' : ''}>${million(b.receipts.ready_amount_vnd)} tr</label>` : b.receipts.ready ? pill(b, b.receipts.ready, 'chưa đủ dữ liệu', 'warn') : ''}${b.receipts.review ? pill(b, old.canWrite(b) ? `+${b.receipts.review}` : b.receipts.review, old.canWrite(b) ? '' : 'cần xem', 'warn') : ''}`;
      if (key === 'prices') return `${b.prices.ready ? `<label class="ready-pick"><input type="checkbox" data-pick-price="${b.customer_id}" aria-label="Chọn giá Sheet của ${esc(label(b))}"${selectedPrices.has(b.customer_id) ? ' checked' : ''}${busy ? ' disabled' : ''}>${b.prices.ready} giá Sheet</label>` : ''}${b.prices.review ? pill(b, b.prices.review, 'giá khác', 'warn') : ''}`;
      const words = { missing: 'chưa giá', removed: 'Sheet xóa', trips_new: 'mới', baseline: 'số dư', commodity: 'mặt hàng', ps: 'PS', text_diff: 'ô chữ' };
      return pill(b, ['baseline', 'commodity'].includes(key) ? '' : n, words[key], key === 'removed' ? 'danger' : key === 'missing' ? 'warn' : '');
    };
    const columns = [['receipts'], ['prices', 'missing'], ['removed', 'checks', 'trips_new'], ['baseline', 'commodity', 'ps', 'text_diff']];
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
      return `${n} ${{ missing: 'chưa giá', removed: 'Sheet xóa', trips_new: 'mới', baseline: 'số dư đầu', commodity: 'mặt hàng', ps: 'PS', text_diff: 'ô chữ' }[key]}`;
    };
    const table = shown.length ? `<div class="work-scroll"><table class="work-table"><thead><tr><th scope="col">Khách</th>${['Phiếu thu <span class="muted">tr</span>', 'Giá chuyến', 'Chuyến cần xử lý', 'Thiết lập sổ'].map((text, i) => `<th scope="col"${dim(i)}>${text}</th>`).join('')}<th scope="col"><span class="sr-only">Mở</span></th></tr></thead><tbody>${rows}</tbody><tfoot><tr><th scope="row">Cộng</th>${columns.map((keys, i) => `<td${dim(i)}>${keys.map(footPart).filter(Boolean).join(' · ')}</td>`).join('')}<td></td></tr></tfoot></table></div>` : `<p class="empty">${icon('check', 28)}${filter ? 'Không có sổ nào có việc loại này.' : partial ? 'Đang chờ đủ dữ liệu để tính việc.' : 'Hôm nay không còn việc.'}</p>`;
    const textCount = totalCount('text_diff');
    const textNote = textCount ? `<p class="inbox-note">Lệch chữ: ${textCount} chỗ ở ${list.filter(b => b.text_diff > 0).length} sổ. Không đụng tiền; ${data?.auto?.text_enabled ? 'máy lấy theo Sheet ở lượt tính tới.' : 'máy chưa bật tự lấy theo Sheet.'}</p>` : '';
    return `${band}${old.resultHtml(result, F, esc, label, href)}${opts.notice ? `<p class="inbox-result" role="status">${icon('check', 18)}${esc(opts.notice)}</p>` : ''}<section class="inbox work-card" aria-labelledby="h-inbox"><div class="work-toolbar">${chips}${selectedCount ? `<button class="btn primary" type="button" data-review${busy ? ' disabled' : ''}>Xem lại ${selectedCount} mục ${icon('right', 16)}</button>` : ''}</div>${errors}${review?.length ? `<div class="work-scroll">${old.reviewHtml(review, F, esc, label, busy)}</div>` : ''}${opts.actionHtml ?? ''}${table}${textNote}</section>`;
  }
  function detailHtml(book, ledger, opts) {
    const { F, esc, href, action } = opts;
    const day = iso => iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : '—';
    const link = text => `<a href="${href(book.customer_id)}">${text}${icon('right')}</a>`;
    const btn = (text, attrs, tone = '') => `<button type="button" class="btn ${tone}" ${attrs}${opts.busy ? ' disabled' : ''}>${text}</button>`;
    const item = (obj, date, desc, amount, buttons, key = '') => {
      const pending = action?.rowKey === key;
      return `<li class="${pending ? 'pending-action' : ''}"${key ? ` data-detail-key="${key}"` : ''}><b title="${esc(obj)}">${esc(obj)}</b><span>${esc(day(date))}</span><span class="detail-description${pending ? ' action-description' : ''}" title="${esc(pending ? action.text : desc)}">${pending ? `<span id="h-action">${esc(action.inlineText ?? action.text)}</span>` : esc(desc)}</span><b class="money" title="${amount == null ? '' : esc(F.full(amount))}">${amount == null ? '' : million(amount)}</b><div class="detail-actions">${pending ? `${action.path ? btn(action.unknown ? 'Thử lại' : 'Xác nhận', 'data-action-write', 'primary') : ''}${action.unknown ? '' : btn('Thôi', 'data-action-cancel')}` : buttons}</div>${pending && action.reasonRequired ? `<label class="review-reason">Lý do kết luận <input data-action-reason maxlength="500" required aria-label="Lý do kết luận ${esc(obj)}" value="${esc(action.body.reason)}"${action.unknown ? ' disabled' : ''}></label>` : ''}${pending && action.error ? `<p class="row-error" role="alert">${esc(action.error)}</p>` : ''}</li>`;
    };
    const section = (label, rows, hint, tone = '') => rows.length ? `<section class="detail-group ${tone}"><h3><i></i>${label}<span>${rows.length} ${label === 'Phiếu cần xem' ? 'phiếu' : 'chuyến'}</span><small>· ${hint}</small></h3><ul class="detail-items">${rows.join('')}</ul></section>` : '';
    const receiptRows = (ledger?.sheet_receipts?.review ?? book.receipts?.items?.filter(r => r.status !== 'READY') ?? []).map(r => item('Phiếu thu', r.date, r.note || 'Máy không ghi phiếu thiếu ngày; đối chiếu chứng từ trong sổ', r.amount_vnd, link('Xem phiếu trong sổ')));
    if (ledger === undefined || ledger === null) return section('Phiếu cần xem', receiptRows, 'máy không ghi phiếu thiếu ngày', 'warn') + (ledger === undefined ? '<p class="loading">Đang tải chi tiết sổ…</p>' : `<p role="alert">Không tải được chi tiết sổ. ${btn('Thử lại', `data-detail-retry="${book.customer_id}"`)}</p>`);
    const removed = (ledger.sheet_sync?.removed_items ?? []).map(r => item(r.container, r.event_date ?? r.date, `${r.origin ?? ''}${r.destination ? ` → ${r.destination}` : ''} · Sheet không còn dòng này`, r.amount_vnd,
      r.month_locked ? link('Mở trong sổ') : `${btn('Xóa chuyến', `data-remove-trip="${r.trip_id}"`, 'danger')}${btn('Giữ', `data-keep-trip="${r.trip_id}"`)}`, `removed:${r.trip_id}`));
    const prices = (ledger.sheet_prices?.review ?? []).map(r => item(r.container, r.date, r.status === 'CONFLICT' ? `Trên web ${million(r.web_unit_price_vnd)} · trên Sheet ${million(r.sheet_unit_price_vnd)}` : 'Cần đối chiếu giá trong sổ', null, link('Mở để đối chiếu')));
    const missing = (ledger.trips ?? []).filter(r => r.unit_price_vnd == null && r.status === 'confirmed').map(r => {
      const rate = ledger.price_status?.trips?.find(p => p.trip_id === r.id && p.ready)?.lookup?.unit_price_vnd;
      const suggested = rate == null ? '' : millionInput(rate);
      return item(r.container, r.event_date, `${r.origin ?? ''}${r.destination ? ` → ${r.destination}` : ''} · ${suggested ? `bảng giá gợi ý ${suggested}` : 'sổ chưa có giá gợi ý'}`, null,
        r.editable === true ? `<input class="inline-price" inputmode="decimal" aria-label="Đơn giá triệu đồng cho ${esc(r.container)}" data-manual-price="${r.id}" data-suggested-price="${suggested}" placeholder="giá, tr">${btn('Ghi giá', `data-command="price" data-trip="${r.id}"`)}` : link('Mở trong sổ'), `price:${r.id}`);
    });
    const pending = (ledger.trips ?? []).filter(r => r.status === 'pending_review').map(r => item(r.container, r.event_date, r.review_reason || 'Nghi trùng, chưa cộng vào nợ', r.unit_price_vnd == null ? null : SoKhachV7Model.tripAmount({ unitPriceVnd: r.unit_price_vnd, otherFeeVnd: r.other_fee_vnd, container: r.container, status: 'confirmed' }).amountVnd?.toString(),
      r.editable === true ? `${btn(r.unit_price_vnd == null ? 'Đúng, giữ' : 'Đúng, tính nợ', `data-command="confirm" data-trip="${r.id}"`)}${btn('Trùng, bỏ', `data-command="reject" data-trip="${r.id}"`)}` : link('Mở trong sổ'), `review:${r.id}`));
    const sheet = (ledger.sheet_sync?.items ?? []).filter(r => ['NEW', 'CONFLICT'].includes(r.sync_state)).map(r => item(r.container, r.event_date ?? r.date, r.message || { OTHER_BOOK_LEGACY: 'Đã có ở sổ khác · sửa tên khách trên Sheet nếu nhầm', OTHER_CUSTOMER: 'Container ở khách khác', COMMODITY_UNKNOWN: 'Sheet chưa ghi mặt hàng', DIFFERENT_FIELDS: 'Sheet khác thông tin trong sổ' }[r.sync_reason] || 'Máy chưa chắc vào sổ nào', null, link('Mở trong sổ')));
    const ps = [...(ledger.ps_fees?.ready ?? []), ...(ledger.ps_fees?.review ?? [])].map(r => item(r.container || 'Dòng PS', r.event_date ?? r.date, 'Tách vào cột phụ phí · không đổi tổng tiền', null, link('Mở trong sổ')));
    const setup = [book.baseline ? item('Số dư đầu kỳ', null, 'Chưa có · đối chiếu sổ gốc rồi nhập', null, link('Mở sổ để nhập')) : '', book.commodity ? item('Mặt hàng', null, 'Chưa gán mặt hàng chính của sổ', null, link('Mở sổ để gán')) : ''].filter(Boolean);
    // ponytail: hợp đồng backend chưa có lệnh xác nhận ngày phiếu, giá xung đột, gán sổ/mặt hàng; giữ đường xử lý sổ thật tới khi bổ sung lệnh có kiểm nguồn.
    return section('Sheet đã xóa', removed, 'đang tính nợ nhưng Sheet không còn, nợ có thể thừa', 'danger')
      + section('Phiếu cần xem', receiptRows, 'máy không ghi phiếu thiếu ngày', 'warn')
      + section('Giá khác', prices, 'hai giá cho cùng chuyến, chọn một', 'warn')
      + section('Chưa giá', missing, 'chưa cộng vào nợ', 'warn')
      + section('Chờ kiểm', pending, 'nghi trùng, chưa cộng vào nợ', 'warn')
      + section('Chuyến mới / ở sổ khác', sheet, 'máy chưa chắc vào sổ nào')
      + (ledger.sheet_sync?.items?.some(r => r.sync_state === 'NEW') ? btn('Vào sổ · chuyến mới', 'data-command="approve"') : '')
      + section('Phụ phí PS', ps, 'không đổi tổng tiền')
      + (ledger.ps_fees?.ready?.length ? btn(`Tách ${ledger.ps_fees.ready.length} dòng`, 'data-command="ps"') : '')
      + section('Thiết lập sổ', setup, 'cần đối chiếu sổ gốc');
  }
  return { render, books, count, parseMillions, million, icon };
})();
