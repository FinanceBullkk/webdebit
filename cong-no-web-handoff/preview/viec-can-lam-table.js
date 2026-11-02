/* Bảng bốn cột đã chọn 2/11. Chỉ gom bằng ID sổ; bộ đếm Sheet và sổ web giữ riêng nguồn. */
globalThis.InboxTable = (() => {
  'use strict';
  const groups = [
    { key: 'money', label: 'Tiền vào sổ', keys: ['receipts', 'prices', 'missing', 'removed'] },
    { key: 'trips', label: 'Chuyến', keys: ['trips_new', 'trips_check', 'pending'] },
    { key: 'setup', label: 'Thiết lập sổ', keys: ['baseline', 'commodity', 'ps', 'text_diff'] },
  ];
  const count = (b, key) => typeof b[key] === 'object' ? (b[key].count ?? b[key].ready + b[key].review) : b[key] ?? 0;
  function books(data, dashboard, unsorted = []) {
    const map = new Map((data?.books ?? []).map(b => [b.customer_id, { ...b }]));
    const add = (items, key) => (items ?? []).forEach(item => {
      if (!map.has(item.customer_id)) map.set(item.customer_id, { customer_id: item.customer_id });
      map.get(item.customer_id)[key] = item.count ?? 1;
    });
    add(dashboard?.todo.missing_price, 'missing');
    add(dashboard?.todo.pending_review, 'pending');
    add(dashboard?.todo.no_baseline, 'baseline');
    add(unsorted, 'commodity');
    return [...map.values()].filter(b => groups.some(g => g.keys.some(key => count(b, key))));
  }
  function render(data, opts) {
    const { F, esc, label, href, dashboard, unsorted, selected = new Set(), selectedPrices = new Set(), review, result, busy, filter, open, details } = opts;
    const old = globalThis.InboxCard;
    const list = books(data, dashboard, unsorted ?? []).sort((a, b) => {
      const amount = b => BigInt(b.receipts?.amount_vnd ?? '0') + BigInt(b.removed?.amount_vnd ?? '0');
      return amount(a) === amount(b) ? label(a).localeCompare(label(b), 'vi') : amount(a) > amount(b) ? -1 : 1;
    });
    const ready = list.filter(b => b.receipts && old.canWrite(b));
    const picked = new Set([...ready.filter(b => selected.has(b.customer_id)).map(b => b.customer_id), ...selectedPrices]);
    const hasReady = ready.length || list.some(b => b.prices?.ready);
    const progress = data?.state === 'computing' ? `<span class="computing loading">đang tính việc từ Sheet ${data.books_done ?? 0}/${data.books_total ?? '—'} sổ</span>` : '';
    const partial = !data || ['computing', 'unavailable'].includes(data.state) || data.failed?.length || !dashboard || opts.unsorted === null;
    const total = list.length ? `<strong>${list.length}</strong> sổ còn việc` : partial ? '<strong>Chưa đủ dữ liệu</strong>' : '<strong>Hết việc</strong>';
    const machine = data?.auto;
    const people = (dashboard?.today.by_actor ?? []).map(p => `<span class="actor-chip" title="${esc(`${p.actor}: ${p.trips} chuyến, ${p.receipts} phiếu thu ${F.full(p.received_vnd)}, ${p.voids} phiếu hủy`)}"><i aria-hidden="true">${esc(p.actor.slice(0, 1))}</i><b>${esc(p.actor)}</b> ${p.trips} chuyến · ${p.receipts} phiếu</span>`).join('')
      + (machine?.today_count || machine?.today_trips ? `<span class="actor-chip"><i aria-hidden="true">M</i><b>Máy</b> ${machine.today_trips ?? 0} chuyến · ${machine.today_count ?? 0} ô chữ</span>` : '');
    const auto = old.autoHtml(data?.auto, esc, label, href);
    const band = `<section class="work-band" aria-label="Còn việc và đã ghi hôm nay"><div class="band-count">${total}</div>${hasReady ? `<button class="btn" type="button" data-pick-ready${busy ? ' disabled' : ''}>Chọn hết mục sẵn sàng ghi</button>` : ''}${progress}<div class="today-inline"><span>Đã ghi hôm nay</span>${people || '<span class="muted">Chưa có giao dịch nào hôm nay.</span>'}${auto ? `<button class="btn" type="button" data-auto aria-expanded="${!!opts.showAuto}">Soát ${opts.showAuto ? '⌃' : '⌄'}</button>` : ''}</div>${auto && opts.showAuto ? `<div class="auto-list">${auto}</div>` : ''}</section>`;
    const errors = !data ? `<p class="inbox-error" role="alert">${esc(opts.failedText)} <button type="button" class="btn" data-inbox-retry>Thử lại</button></p>`
      : data.state === 'unavailable' ? '<p class="inbox-note warn">Chưa đọc được bản lấy từ Sheet. Bấm Làm mới để lấy lại; việc dưới đây có thể thiếu.</p>'
        : data.failed?.length ? `<p class="inbox-note warn">${data.failed.length} sổ chưa tính được, việc của các sổ này có thể thiếu.</p>` : '';
    const chips = `<h2 id="h-inbox">Việc chờ theo sổ</h2><button type="button" class="filter-chip" data-filter="" aria-pressed="${!filter}">Tất cả</button>${groups.map(g => `<button type="button" class="filter-chip" data-filter="${g.key}" aria-pressed="${filter === g.key}">${g.label} <b>${list.filter(b => g.keys.some(key => count(b, key))).length}</b></button>`).join('')}`;
    const toggle = b => `data-open-book="${b.customer_id}" aria-expanded="${open === b.customer_id}" aria-controls="book-detail-${b.customer_id}"`;
    const pill = (b, text, tone = '') => `<button type="button" class="work-pill ${tone}" ${toggle(b)}>${esc(text)}</button>`;
    const cell = (b, keys) => keys.map(key => {
      const n = count(b, key);
      if (!n) return '';
      if (key === 'receipts') return `${old.canWrite(b) ? `<label class="ready-pick"><input type="checkbox" data-pick="${b.customer_id}" aria-label="Chọn phiếu thu của ${esc(label(b))}"${selected.has(b.customer_id) ? ' checked' : ''}${busy ? ' disabled' : ''}><span title="${esc(F.full(b.receipts.ready_amount_vnd))}">${esc(F.short(b.receipts.ready_amount_vnd, 'tr'))}</span></label>` : b.receipts.ready ? pill(b, `${b.receipts.ready} phiếu chưa đủ dữ liệu`, 'warn') : ''}${b.receipts.review ? pill(b, `${b.receipts.review} cần xem`, 'warn') : ''}`;
      if (key === 'prices') return `${b.prices.ready ? `<label class="ready-pick"><input type="checkbox" data-pick-price="${b.customer_id}" aria-label="Chọn giá Sheet của ${esc(label(b))}"${selectedPrices.has(b.customer_id) ? ' checked' : ''}${busy ? ' disabled' : ''}>${b.prices.ready} giá Sheet</label>` : ''}${b.prices.review ? pill(b, `${b.prices.review} giá khác`, 'warn') : ''}`;
      const text = { prices: `${b.prices?.ready ?? 0} giá Sheet${b.prices?.review ? ` · ${b.prices.review} giá cần xem` : ''}`, missing: `${n} chưa giá`, removed: `${n} Sheet xóa`, trips_new: `${n} mới`, trips_check: `${n} cần xem`, pending: `${n} chờ kiểm`, baseline: 'số dư đầu', commodity: 'mặt hàng', ps: `${n} phụ phí PS`, text_diff: `${n} ô chữ` }[key];
      return pill(b, text, ['removed'].includes(key) ? 'danger' : ['missing', 'trips_check', 'pending', 'prices'].includes(key) ? 'warn' : '');
    }).join('');
    const columns = [['receipts'], ['prices', 'missing'], ['removed', 'trips_check', 'pending', 'trips_new'], ['baseline', 'commodity', 'ps', 'text_diff']];
    const shown = list.filter(b => !filter || groups.find(g => g.key === filter)?.keys.some(key => count(b, key)));
    const rows = shown.map(b => {
      const failed = result?.books?.find(row => row.customer_id === b.customer_id && !row.ok);
      const detail = open === b.customer_id ? `<tr class="work-detail" id="book-detail-${b.customer_id}"><td colspan="6">${detailHtml(b, details?.get(b.customer_id), opts)}<a class="open-book" href="${href(b.customer_id)}">Mở cả sổ ›</a></td></tr>` : '';
      return `<tr class="work-row${open === b.customer_id ? ' expanded' : ''}" data-book="${b.customer_id}"><th scope="row"><button class="book-name" type="button" ${toggle(b)} title="${esc(label(b))}">${esc(label(b))}</button>${failed ? `<p class="row-error" role="alert">${esc(failed.message)}</p>` : ''}</th>${columns.map(keys => `<td><div class="cell-pills">${cell(b, keys)}</div></td>`).join('')}<td><button class="row-toggle" type="button" ${toggle(b)} aria-label="${open === b.customer_id ? 'Đóng' : 'Xử lý'} sổ ${esc(label(b))}">${open === b.customer_id ? '⌃' : '⌄'}</button></td></tr>${detail}`;
    }).join('');
    const table = shown.length ? `<div class="work-scroll"><table class="work-table"><colgroup><col class="name-col"><col><col><col><col><col class="toggle-col"></colgroup><thead><tr><th scope="col">Khách</th><th scope="col">Phiếu thu <span class="muted">tr</span></th><th scope="col">Giá chuyến</th><th scope="col">Chuyến cần xử lý</th><th scope="col">Thiết lập sổ</th><th scope="col"><span class="sr-only">Mở</span></th></tr></thead><tbody>${rows}</tbody><tfoot><tr><th scope="row">Cộng</th>${columns.map(keys => `<td>${keys.map(key => { const n = shown.reduce((sum, b) => sum + count(b, key), 0); return n ? `${n} ${{ receipts: 'phiếu', prices: 'giá Sheet', missing: 'chưa giá', removed: 'Sheet xóa', trips_new: 'mới', trips_check: 'cần xem', pending: 'chờ kiểm', baseline: 'số dư đầu', commodity: 'mặt hàng', ps: 'phụ phí PS', text_diff: 'ô chữ' }[key]}` : ''; }).filter(Boolean).join(' · ')}</td>`).join('')}<td></td></tr></tfoot></table></div>` : `<p class="empty">${filter ? 'Không có sổ nào có việc loại này.' : partial ? 'Đang chờ đủ dữ liệu để tính việc.' : 'Hôm nay không còn việc.'}</p>`;
    const when = data?.sheet_at ? `Sheet lúc ${new Date(data.sheet_at).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' })}` : '';
    const textBooks = list.filter(b => b.text_diff > 0);
    const textCount = textBooks.reduce((sum, b) => sum + b.text_diff, 0);
    const textNote = textCount ? `<p class="inbox-note">Lệch chữ: ${textCount} chỗ ở ${textBooks.length} sổ. Không đụng tiền; ${data?.auto?.text_enabled ? 'máy lấy theo Sheet ở lượt tính tới.' : 'máy chưa bật tự lấy theo Sheet.'}</p>` : '';
    return `${band}<section class="inbox work-card" aria-labelledby="h-inbox"><div class="work-toolbar">${chips}${picked.size ? `<button class="btn primary" type="button" data-review${busy ? ' disabled' : ''}>Xem lại ${picked.size} sổ</button>` : ''}</div>${errors}${opts.notice ? `<p class="inbox-result" role="status">${esc(opts.notice)}</p>` : ''}${old.resultHtml(result, F, esc, label, href)}${review?.length ? `<div class="work-scroll">${old.reviewHtml(review, F, esc, label, busy)}</div>` : ''}${opts.actionHtml ?? ''}${table}${textNote}<p class="work-stamp">${esc(when)}${data?.refreshing ? ' · đang cập nhật…' : ''}</p></section>`;
  }
  function detailHtml(book, ledger, { F, esc, href }) {
    const dateText = globalThis.InboxCard.dayText;
    // ponytail: ngoại lệ thiếu hợp đồng sửa tại hộp mở sổ hiện hành; thêm tại dòng khi có lệnh đã kiểm và nguồn tiền rõ.
    const link = (text, loc = '') => `<a class="btn" href="${href(book.customer_id)}${loc ? `&amp;loc=${loc}` : ''}">${text}</a>`;
    const receipts = book.receipts?.items ?? [];
    const receiptHtml = receipts.length ? `<section><h3>Phiếu thu</h3><ul class="detail-items">${receipts.map(row => `<li><b>${row.date ? esc(dateText(row.date)) : 'Không rõ ngày'}</b><span>${esc(row.note ?? '')}</span><b class="money">${row.amount_vnd == null ? '—' : esc(F.full(row.amount_vnd))}</b><span>${row.status === 'READY' ? 'Sẵn sàng ghi' : 'Cần xem'}</span>${row.status === 'READY' ? '' : link('Xem phiếu trong sổ')}</li>`).join('')}</ul></section>` : '';
    if (ledger === undefined) return `${receiptHtml}<p class="loading">Đang tải chi tiết sổ…</p>`;
    if (ledger === null) return `${receiptHtml}<p role="alert">Không tải được chi tiết sổ. <button class="btn" type="button" data-detail-retry="${book.customer_id}">Thử lại</button></p>`;
    const sections = [
      ['Giá từ Sheet', [...(ledger.sheet_prices?.ready ?? []), ...(ledger.sheet_prices?.review ?? [])], 'prices'],
      ['Chuyến Sheet không còn', ledger.sheet_sync?.removed_items ?? [], 'removed'],
      ['Chuyến từ Sheet cần xử lý', (ledger.sheet_sync?.items ?? []).filter(r => ['NEW', 'CONFLICT'].includes(r.sync_state)), 'sheet'],
      ['Chuyến chưa giá', (ledger.trips ?? []).filter(r => r.unit_price_vnd == null && r.status === 'confirmed'), 'missing'],
      ['Chuyến chờ kiểm', (ledger.trips ?? []).filter(r => r.status === 'pending_review'), 'pending'],
      ['Phụ phí PS', [...(ledger.ps_fees?.ready ?? []), ...(ledger.ps_fees?.review ?? [])], 'ps'],
    ].filter(([, rows]) => rows.length).map(([title, rows, kind]) => `<section><h3>${title} · ${rows.length}</h3><ul class="detail-items">${rows.map(r => {
      const words = { OTHER_BOOK_LEGACY: 'Đã có ở sổ khác', OTHER_CUSTOMER: 'Container ở khách khác', CONTAINER_REUSED_OR_CHANGED: 'Container đã dùng', DIFFERENT_FIELDS: 'Sheet khác thông tin trong sổ', READY: 'Sẵn sàng ghi', CONFLICT: 'Khác giá web', MONTH_LOCKED: 'Tháng đang khóa', NEW: 'Chuyến mới', pending_review: 'Chờ kiểm' };
      let action = link('Mở trong sổ', kind === 'missing' ? 'thieu-gia' : kind === 'pending' ? 'cho-kiem' : '');
      if (kind === 'removed' && !r.month_locked) action = `<button class="btn" type="button" data-remove-trip="${r.trip_id}">Xóa chuyến</button><button class="btn" type="button" data-keep-trip="${r.trip_id}">Giữ</button>`;
      if (kind === 'missing' && r.editable === true) action = `<label>Đơn giá (đ) <input class="inline-price" inputmode="numeric" aria-label="Đơn giá cho ${esc(r.container)}" data-manual-price="${r.id}" placeholder="9.200.000"></label><button class="btn" type="button" data-command="price" data-trip="${r.id}">Ghi giá</button>`;
      if (kind === 'pending' && r.editable === true) action = `<label>Lý do <input maxlength="500" data-reason="${r.id}" aria-label="Lý do kết luận ${esc(r.container)}"></label><button class="btn" type="button" data-command="confirm" data-trip="${r.id}">Đúng, tính nợ</button><button class="btn" type="button" data-command="reject" data-trip="${r.id}">Trùng, bỏ</button>`;
      return `<li><b>${esc(r.container ?? '—')}</b><span>${esc(dateText(r.date ?? r.event_date))}</span><span>${esc(r.message ?? words[r.sync_reason ?? r.status ?? r.sync_state] ?? 'Cần xem trong sổ')}</span><b class="money">${r.sheet_unit_price_vnd != null ? esc(F.full(r.sheet_unit_price_vnd)) : r.amount_vnd != null ? esc(F.full(r.amount_vnd)) : '—'}</b>${action}</li>`;
    }).join('')}</ul>${kind === 'prices' && ledger.sheet_prices?.ready?.length ? `<button type="button" class="btn" data-price-review="${book.customer_id}">Xem lại ${ledger.sheet_prices.ready.length} giá Sheet</button>` : ''}${kind === 'ps' && ledger.ps_fees?.ready?.length ? '<button type="button" class="btn" data-command="ps">Tách phụ phí sẵn sàng</button>' : ''}${kind === 'sheet' && ledger.sheet_sync?.items?.some(r => r.sync_state === 'NEW') ? '<button type="button" class="btn" data-command="approve">Xem lại chuyến mới</button>' : ''}</section>`).join('');
    return `${receiptHtml}${sections}${book.baseline || book.commodity ? `<section><h3>Thiết lập sổ</h3>${book.baseline ? link('Nhập số dư đầu') : ''} ${book.commodity ? link('Gán mặt hàng / cảng-bộ') : ''}</section>` : ''}`;
  }
  return { render, books, count };
})();
