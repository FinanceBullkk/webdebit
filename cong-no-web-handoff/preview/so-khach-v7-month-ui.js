/* Sổ khách V7 bản live — các bảng tháng: chọn tháng nào có bảng, tháng nào hiện chi tiết, thanh chip tháng dính đầu sổ, thanh
 * của từng bảng tháng (ổ khóa, Debit note, còn nợ cuối tháng), thân tháng (bảng chuyến của so-khach-v7-trips-ui.js bên trái,
 * phiếu thu của so-khach-v7-pay-ui.js bên phải), dòng điều chỉnh, dòng mờ "đã chuyển sang tháng", dòng Tổng tháng.
 * SO-GON-04 (31/10/2026): lúc mở sổ chỉ tháng hiện tại và tháng liền trước hiện chi tiết, tháng khác thu gọn một dòng; thanh
 * chip tháng thay danh sách tháng bên phải. Số tiền lấy nguyên từ GET; tổng cột phụ phí do model cộng (ARCH-03).
 * Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).month = ctx => {
  'use strict';
  const { root, model, escape, fmt, num, dateText, monthKey, monthLabel, liveOpenMonth, columns, ghosts, redraw, showNotice,
    legacyTripRow, webTripRow, sheetPendingRows, payRows } = ctx;
  const { short, monthTag } = CongNoFormat;
  // Chuyến Sheet chưa vào sổ: dòng mới, hoặc lệch mà chưa nối được dòng nào trong sổ.
  const sheetPending = row => row.sync_state === 'NEW' || !row.existing_id;
  // Xuống dòng giữa các hàng của bảng tháng, giữ đúng như trước khi tách file để DOM không đổi.
  const GAP = '\n          ';
  const prevMonth = key => {
    const year = Number(key.slice(0, 4)), month = Number(key.slice(5, 7));
    return month === 1 ? `${year - 1}-12` : `${year}-${String(month - 1).padStart(2, '0')}`;
  };

  // Tháng người dùng đã bấm Xem chi tiết (true) hoặc Thu gọn (false); chỉ sống trong tab, thắng mặc định.
  const shown = new Map();
  // ?month=yyyy-mm (từ Công nợ theo tháng, Đòi nợ): hiện chi tiết tháng đó và cuộn tới sau lần vẽ đầu có tháng đó.
  const wanted = /^\d{4}-(0[1-9]|1[0-2])$/.exec(new URLSearchParams(location.search).get('month') ?? '')?.[0] ?? null;
  if (wanted) shown.set(wanted, true);
  let scrollTarget = wanted;
  // Tháng đang hiện chi tiết ở lần vẽ gần nhất (để showMonth biết có cần vẽ lại không).
  let lastOpen = new Set();

  // Tháng có bảng, xếp theo tháng: tháng server có số; tháng hiện tại (giờ VN theo server, đồng hồ máy khi server cũ chưa trả)
  // dù chưa có dữ liệu, vì vẫn cần khối để ghi thu (trừ nợ cũ trước) và dán chuyến; tháng mà một dòng rơi vào.
  function bookMonths(data, active) {
    const openKey = monthKey(data.today_month) || liveOpenMonth;
    const groups = [...(data.months ?? [])];
    if (active && !groups.some(item => monthKey(item.month) === openKey)) {
      groups.push({ month: `${openKey}-01`, placeholder: true });
      groups.sort((a, b) => monthKey(a.month).localeCompare(monthKey(b.month)));
    }
    // Khoản "cấn trừ đi" của sổ nguồn nằm ở tháng của ngày trả, trong khối TIỀN KHÁCH TRẢ (số âm).
    const outgoing = new Map();
    for (const item of data.outgoing_offsets ?? []) {
      const key = monthKey(item.date);
      if (!outgoing.has(key)) outgoing.set(key, []);
      outgoing.get(key).push({ pid: item.pid, date: item.date, method: 'CẤN TRỪ', offset_pair_id: item.offset_pair_id,
        counterparty_customer_id: item.counterparty_customer_id, counterparty_name: item.counterparty_name, outgoing: true,
        void_reason: item.void_reason, voided_by_event: item.voided_by_event, line: { amount_vnd: item.amount_vnd, kind: 'offset' } });
      if (!groups.some(group => monthKey(group.month) === key)) groups.push({ month: `${key}-01`, placeholder: true });
    }
    // Đổi ngày sang tháng khác: chuyến/dòng sổ gốc tự sang bảng tháng đó, chưa có bảng thì bảng tự hiện.
    for (const row of [...(data.trips ?? []), ...(data.legacy_rows ?? []), ...ghosts,
      ...(data.receipts ?? []).map(item => ({ month: item.date })),
      ...(data.sheet_sync?.items ?? []).filter(sheetPending).map(item => ({ month: item.event_date }))]) {
      const key = monthKey(row.month);
      if (key && !groups.some(group => monthKey(group.month) === key)) groups.push({ month: `${key}-01`, placeholder: true });
    }
    groups.sort((a, b) => monthKey(a.month).localeCompare(monthKey(b.month)));
    return { groups, openKey, outgoing };
  }

  // Tháng hiện chi tiết: người dùng chọn thì theo người dùng; còn lại tháng hiện tại, tháng liền trước, tháng có dòng vừa chuyển
  // tới (ctx.ghosts) và tháng có dòng ?loc= cần xử lý. Tháng đã hiện chi tiết thì giữ trong tab tới khi người dùng bấm Thu gọn,
  // để tự cập nhật, bỏ đánh dấu ?loc= hay qua ngày không làm tháng đang xem tự thu lại.
  function openMonths(data, groups, openKey) {
    const auto = new Set([openKey, prevMonth(openKey), ...ghosts.map(ghost => ghost.to), ...(ctx.locMonths?.(data) ?? [])]);
    const keys = groups.map(item => monthKey(item.month));
    for (const key of keys) if (!shown.has(key) && auto.has(key)) shown.set(key, true);
    return new Set(keys.filter(key => shown.get(key) === true));
  }

  // Việc chờ của một tháng, cho chấm cam trên chip: cùng điều kiện với ?loc= (so-khach-v7-loc-ui.js) và dòng Sheet chờ.
  function monthWork(data, key) {
    const trips = (data.trips ?? []).filter(trip => !trip.deleted && monthKey(trip.month) === key);
    const sheet = (data.sheet_sync?.items ?? []).filter(item => monthKey(item.event_date) === key).length;
    return [[trips.filter(trip => trip.status === 'confirmed' && trip.is_missing_price === true).length, 'chưa có giá'],
      [trips.filter(trip => trip.status === 'pending_review').length, 'chờ kiểm'], [sheet, 'từ Sheet cần xem']]
      .filter(([count]) => count > 0);
  }

  // Dòng sổ gốc của tháng: chuyến và khoản thu cùng một hàng Sheet thành một cặp, giữ thứ tự hàng Sheet.
  // Chuyến vẽ ở bảng chuyến, khoản thu ở danh sách phiếu; `d` là các cột Sheet đã đọc (display).
  function legacyPairs(rows) {
    const byRow = new Map();
    for (const row of rows) {
      const d = typeof row.display === 'object' && row.display !== null ? row.display : {};
      const line = byRow.get(d.row) ?? {};
      line[row.kind === 'receipt' ? 'receipt' : 'trip'] = { ...row, d };
      byRow.set(d.row, line);
    }
    return [...byRow.values()];
  }

  // Thanh tháng: ổ khóa (V7-SO), Debit note khi tháng có chuyến tính tiền, còn nợ cuối tháng (SO-GON-03: mỗi số tiền của
  // tháng hiện một lần; rê chuột xem cách tính), nút Xem chi tiết / Thu gọn (SO-GON-04; không gọi "Mở tháng" vì mở tháng là
  // mở khóa). Tháng thu gọn ghi thêm số chuyến.
  function monthBar(item, key, { locked, active, debit, totals, open, tripCount }) {
    const label = monthLabel(key);
    const lock = `<button class="month-lock" data-month="${escape(item.month)}" aria-label="${locked ? 'Mở khóa' : 'Khóa'} tháng ${label}" `
      + `title="${locked ? 'Đã khóa' : 'Đang mở'}" aria-pressed="${!locked}" ${active ? '' : 'disabled'}>${locked ? '🔒' : '🔓'}</button>`;
    const debitButton = debit ? `<button class="debit-open" data-month="${escape(key)}" aria-haspopup="dialog">Debit note</button>` : '';
    const count = !open && tripCount ? `<span class="month-count">${tripCount} chuyến</span>` : '';
    const how = `Nợ các tháng trước ${fmt(item.prior_months_vnd)} + phát sinh ${fmt(totals.chargesVnd)} − đã thu ${fmt(totals.receivedVnd)}`;
    const toggle = `<button type="button" class="month-toggle" data-month="${escape(key)}" aria-expanded="${open}" `
      + `aria-controls="thang-${escape(key)}">${open ? 'Thu gọn' : 'Xem chi tiết'}</button>`;
    return `<tr class="month"><th colspan="${columns.count()}" scope="rowgroup"><span class="month-title">THÁNG ${label}${lock}${debitButton}${count}`
      + `<em class="month-stats"><span class="month-end" title="${how}">Còn nợ cuối tháng: <b>${fmt(item.end_of_month_vnd)}</b></span></em>`
      + `${toggle}</span></th></tr>`;
  }

  // Góp ý 23/10/2026: không hiện dòng số dư đầu, dòng "Theo sổ gốc" và dòng chênh do sửa dòng cũ.
  // Các dòng đó vẫn nằm trong số tiền: dòng Tổng tháng lấy phát sinh/đã thu của Sheet từ server (DA-THU-01), chênh ghi ở Lịch sử.
  // XOA-DC-THANG-01: điều chỉnh cả tháng xóa được khi tháng đang mở — bấm ô số tiền như xóa dòng chuyến.
  function adjustmentRows(adjustments, openHere) {
    const amount = row => row.trip_id == null && openHere
      ? `<td class="num row-delete" data-kind="adjustment" data-id="${escape(row.id)}" tabindex="0" role="button" `
        + `aria-label="Xóa hẳn điều chỉnh cả tháng ${escape(fmt(row.amount_vnd))}" title="Bấm để xóa hẳn dòng điều chỉnh này">${fmt(row.amount_vnd)}</td>`
      : num(fmt(row.amount_vnd));
    return adjustments.filter(row => row.legacy_row_id == null).map(row => `<tr class="adjustment"><td colspan="${columns.trip() - 1}">`
      + `Điều chỉnh ${row.trip_id ? 'chuyến' : 'cả tháng'}${row.note ? ` · ${escape(row.note)}` : ''}</td>${amount(row)}`
      + '<td class="pay pay-start" colspan="3"></td></tr>').join('');
  }

  // Tháng cũ của dòng vừa đổi ngày sang tháng khác: một dòng mờ có Xem / Hoàn tác (ctx.ghosts, so-khach-v7-edit-ui.js).
  const ghostRows = key => ghosts.map((ghost, index) => ghost.month !== key ? '' : `<tr class="ghost"><td colspan="${columns.count()}">`
    + `↪ ${escape(ghost.container || 'Chuyến')} (ngày cũ ${escape(dateText(ghost.oldIso))}) đã chuyển sang tháng ${monthLabel(ghost.to)}`
    + `<button type="button" class="ghost-go" data-row="${escape(`${ghost.kind}-${ghost.id}`)}">Xem</button>`
    + `<button type="button" class="ghost-undo" data-ghost="${index}">Hoàn tác</button></td></tr>`).join('');

  // Dòng Tổng tháng: tổng từng cột phụ phí (chuyến đã tính tiền và dòng sổ gốc của tháng), Thành tiền và Đã thu của server.
  function subtotalRow(item, key, { locked, active, feeTotalCells, totals }) {
    return `<tr class="subtotal"><td colspan="${columns.feeStart()}">Tổng tháng ${monthLabel(key)} `
      + `<button class="add-month-adjustment" data-month="${escape(item.month)}" ${active && !locked ? '' : 'disabled'}>+ Điều chỉnh cả tháng</button></td>`
      + `${feeTotalCells}${num(fmt(totals.chargesVnd))}<td class="pay pay-start">Đã thu</td>`
      + `<td class="pay num subtotal-pay" colspan="2">${fmt(totals.receivedVnd)}</td></tr><tr class="spacer"><td colspan="${columns.count()}"></td></tr>`;
  }

  function monthSection(item, { data, active, openKey, lockFlags, historical, outgoing, open }) {
    const key = monthKey(item.month);
    const legacyRows = historical.get(key) ?? [];
    const trips = (data.trips ?? []).filter(row => monthKey(row.month) === key);
    const locked = lockFlags.has(key) ? lockFlags.get(key) : key !== openKey;
    const legacy = legacyPairs(legacyRows);
    const totals = { chargesVnd: item.charges_vnd ?? '0', receivedVnd: item.received_vnd ?? '0' };
    const debit = legacy.some(line => line.trip) || trips.some(trip => trip.status === 'confirmed');
    // SO-GON-04: tháng thu gọn chỉ còn thanh tháng (cùng số tiền, ổ khóa, Debit note) và số chuyến; không vẽ dòng nào.
    if (!open.has(key)) {
      const tripCount = legacy.filter(line => line.trip).length + trips.length;
      return `<section id="thang-${escape(key)}"><table class="ledger month-collapsed${locked ? ' locked' : ''}" aria-label="Sổ khách tháng ${monthLabel(key)}, thu gọn">`
        + `<colgroup>${columns.all()}</colgroup><tbody>${monthBar(item, key, { locked, active, debit, totals, open: false, tripCount })}</tbody></table></section>`;
    }
    const sheetRows = (data.sheet_sync?.items ?? []).filter(row => monthKey(row.event_date) === key && sheetPending(row));
    // DA-THU-01: phiếu nằm ở tháng của ngày thu, đủ số tiền một lần (như Sheet); `lines` là phần trừ nợ còn hiệu lực
    // (phiếu đã hủy: phần bị hủy cùng lệnh hủy).
    const received = (data.receipts ?? []).filter(row => monthKey(row.date) === key).map(row => {
      const lines = (row.allocations ?? []).filter(line => row.voided_by_event != null
        ? line.superseded_by_event === row.voided_by_event : line.superseded_by_event === null);
      return { ...row, lines, line: { amount_vnd: row.amount_vnd, kind: lines[0]?.kind } };
    });
    const receipts = [...received, ...(outgoing.get(key) ?? [])];
    const adjustments = (data.adjustments ?? []).filter(row => monthKey(row.month) === key);
    // SO-GON-02 (29/10/2026, phương án A): chuyến bên trái, phiếu thu là danh sách riêng bên phải — không chung hàng,
    // để không đọc nhầm "chuyến này trả số tiền này".
    // Phiếu thu vẫn nhập trong tháng khóa. Không có bảng nhập chuyến: chuyến vào sổ từ Sheet (NHAP-SHEET-02).
    const entryHere = active;
    const openHere = active && !locked;
    // STT chuyến web nối tiếp các dòng chuyến từ Sheet của tháng (dòng Sheet vẽ trước, như thứ tự trên Sheet).
    const sttBase = new Set(legacyRows.filter(row => row.kind !== 'receipt').map(row => row.display?.row)).size;
    const tripRows = legacy.map(line => line.trip ? legacyTripRow(line.trip, locked) : '').join('')
      + trips.map((trip, index) => webTripRow(trip, index, { locked, sttBase })).join('');
    const pays = payRows(key, { legacy, receipts, entryHere, locked });
    const body = `<tr class="month-body"><td class="trip-side" colspan="${columns.trip()}">`
      + `<table class="ledger-inner trip-list${columns.shipper() ? '' : ' no-shipper'}"><colgroup>${columns.tags(0, columns.trip())}</colgroup>`
      + `<tbody>${tripRows}</tbody></table></td><td class="pay-side pay-start" colspan="3"><div class="pay-stick">`
      + `<table class="ledger-inner pay-list" aria-label="Tiền khách trả tháng ${monthLabel(key)}">`
      + `<colgroup>${columns.tags(columns.trip(), columns.count())}</colgroup><tbody>${pays}</tbody></table></div></td></tr>`;
    const feeTotals = model.feeColumnTotals([...legacyRows.filter(row => row.kind === 'trip'),
      ...trips.filter(trip => trip.status === 'confirmed')].map(row => row.fee_lines ?? []), ctx.feeColumnIds);
    const feeTotalCells = [...feeTotals.own, feeTotals.otherVnd].map(value => num(value === null ? '' : model.formatVnd(value), 'fee')).join('');
    return [`<section id="thang-${escape(key)}"><table class="ledger${locked ? ' locked' : ''}" aria-label="Sổ khách tháng ${monthLabel(key)}">`
      + `<colgroup>${columns.all()}</colgroup><tbody>`,
    monthBar(item, key, { locked, active, debit, totals, open: true }),
    `${body}${sheetPendingRows(sheetRows)}${adjustmentRows(adjustments, openHere)}${ghostRows(key)}`,
    `${subtotalRow(item, key, { locked, active, feeTotalCells, totals })}</tbody></table></section>`].join(GAP);
  }

  // Chip một tháng trên thanh tháng: "T9" (ghi năm khi khác năm hiện tại), còn nợ cuối tháng rút gọn, dấu khóa chỉ để xem
  // (khóa/mở khóa bấm ở thanh của bảng tháng) và chấm cam số việc chờ.
  function monthChip(item, { data, openKey, lockFlags }) {
    const key = monthKey(item.month);
    const locked = lockFlags.has(key) ? lockFlags.get(key) : key !== openKey;
    const end = item.end_of_month_vnd == null ? '–' : short(item.end_of_month_vnd);
    const work = monthWork(data, key);
    const todo = work.map(([count, what]) => `${count} ${what}`).join(' · ');
    const total = work.reduce((sum, [count]) => sum + count, 0);
    return `<a class="month-chip${locked ? ' locked' : ''}" href="#thang-${escape(key)}" data-month="${escape(key)}" `
      + `aria-label="Tháng ${monthLabel(key)} · còn nợ cuối tháng ${escape(end)}${locked ? ' · đã khóa' : ''}${todo ? ` · ${escape(todo)}` : ''}">`
      + `<span class="chip-name">${monthTag(`${key}-01`, Number(openKey.slice(0, 4)))}</span><b class="chip-end">${escape(end)}</b>`
      + `${locked ? '<span class="chip-lock" aria-hidden="true">🔒</span>' : ''}`
      + `${total ? `<span class="chip-work" title="${escape(todo)}" aria-hidden="true">${total}</span>` : ''}</a>`;
  }

  // Các bảng tháng và thanh chip tháng của một bản GET.
  function monthSections(data, active) {
    const { groups, openKey, outgoing } = bookMonths(data, active);
    const lockFlags = new Map((data.month_locks ?? []).map(row => [monthKey(row.month), row.locked]));
    const historical = new Map();
    for (const row of data.legacy_rows ?? []) {
      const key = monthKey(row.month);
      if (!historical.has(key)) historical.set(key, []);
      historical.get(key).push(row);
    }
    const open = openMonths(data, groups, openKey);
    lastOpen = open;
    const book = { data, active, openKey, lockFlags, historical, outgoing, open };
    return { sections: groups.map(item => monthSection(item, book)).join(''),
      chips: `<nav class="month-chips" aria-label="Các tháng của sổ">${groups.map(item => monthChip(item, book)).join('')}</nav>` };
  }

  // ---- Thu gọn / xem chi tiết, chip tháng, tháng đang xem ----
  const sectionOf = key => root.querySelector(`#thang-${key}`);
  // Bấm chip/nút thì cuộn mượt (theo CSS); lần cuộn tới ?month= lúc mở trang thì tức thì, vì lần vẽ lại ngay sau đó (danh sách
  // khách về) giữ vị trí cuộn đang có và sẽ cắt ngang một lần cuộn mượt.
  const scrollToMonth = (key, behavior = 'auto') => sectionOf(key)?.scrollIntoView({ block: 'start', behavior });
  // Tháng đang thu gọn thì hiện chi tiết (vẽ lại); trả về true khi có vẽ lại. Phần khác gọi trước khi tìm một dòng của tháng.
  function showMonth(key) {
    if (!key || lastOpen.has(key)) return false;
    shown.set(key, true);
    redraw();
    return true;
  }
  // Thu gọn không được làm mất chữ đang gõ hay dòng hỏi đang mở trong tháng đó.
  function busyIn(section) {
    const typed = [...section.querySelectorAll('.receipt-date,.receipt-amount,.receipt-reference,.info-input,.money-input,.month-amount,.month-note')]
      .some(input => input.value.trim());
    const method = [...section.querySelectorAll('.receipt-method')].some(select => select.value !== 'THU TIỀN');
    return typed || method || section.querySelector('.review-prompt,.void-prompt,.move-ask,.delete-prompt,.month-adjustment-input,.offset-source-row,.image-thumb');
  }
  root.addEventListener('click', event => {
    const toggle = event.target.closest('.month-toggle');
    if (toggle) {
      const key = toggle.dataset.month, open = toggle.getAttribute('aria-expanded') === 'true';
      const section = sectionOf(key);
      if (open && section && busyIn(section)) {
        showNotice(`Tháng ${monthLabel(key)} đang có ô nhập dở. Ghi hoặc bỏ ô đó trước khi thu gọn.`);
        return;
      }
      shown.set(key, !open);
      redraw();
      scrollToMonth(key);
      root.querySelector(`.month-toggle[data-month="${key}"]`)?.focus({ preventScroll: true });
      return;
    }
    const chip = event.target.closest('.month-chip');
    if (!chip) return;
    event.preventDefault();
    showMonth(chip.dataset.month);
    scrollToMonth(chip.dataset.month);
  });
  // Chip của tháng đang ở trên cùng vùng dữ liệu được tô (thay việc dính đầu của thanh tháng, SO-GON-04); sổ nhiều tháng thì
  // thanh chip cuộn ngang để chip đó luôn trong tầm nhìn.
  function markCurrent() {
    const bar = root.querySelector('.month-chips');
    if (!bar) return;
    const line = (root.querySelector('.ledger-head')?.getBoundingClientRect().bottom ?? 0) + 1;
    const sections = [...root.querySelectorAll('.ledger-book > section')];
    let current = sections[0]?.id;
    for (const section of sections) {
      if (section.getBoundingClientRect().top > line) break;
      current = section.id;
    }
    for (const chip of bar.querySelectorAll('.month-chip')) {
      const on = `thang-${chip.dataset.month}` === current;
      chip.classList.toggle('on', on);
      if (on) chip.setAttribute('aria-current', 'true'); else chip.removeAttribute('aria-current');
      if (on && (chip.offsetLeft < bar.scrollLeft || chip.offsetLeft + chip.offsetWidth > bar.scrollLeft + bar.clientWidth)) {
        bar.scrollLeft = chip.offsetLeft - (bar.clientWidth - chip.offsetWidth) / 2;
      }
    }
  }
  let marking = false;
  if (typeof window.addEventListener === 'function') {
    window.addEventListener('scroll', () => {
      if (marking) return;
      marking = true;
      requestAnimationFrame(() => { marking = false; markCurrent(); });
    }, { passive: true });
  }
  // Sau mỗi lần vẽ: cuộn tới tháng của ?month= (một lần) rồi tô chip tháng đang xem.
  function monthsAfterRender() {
    if (typeof root.querySelectorAll !== 'function') return;
    if (scrollTarget && sectionOf(scrollTarget)) {
      scrollToMonth(scrollTarget, 'instant');
      scrollTarget = null;
    }
    markCurrent();
  }

  Object.assign(ctx, { monthSections, monthsAfterRender, showMonth });
};
