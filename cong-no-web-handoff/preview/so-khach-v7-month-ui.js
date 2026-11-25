/* Sổ khách V7 bản live — các bảng tháng: tháng nào có chip, tháng nào đang xem, thanh chip tháng dính đầu sổ, thanh của
 * bảng tháng (ổ khóa, Debit note, dòng tóm tắt tiền của tháng), thân tháng (bảng chuyến của so-khach-v7-trips-ui.js bên trái,
 * phiếu thu của so-khach-v7-pay-ui.js bên phải), dòng điều chỉnh, dòng mờ "đã chuyển sang tháng", dòng Tổng tháng.
 * SO-GON-05 (1/11/2026, thay H1 của SO-GON-04): một tháng trên màn hình; hàng chip là chỗ chọn tháng duy nhất. Số tiền lấy
 * nguyên từ GET; tổng cột phụ phí do model cộng (ARCH-03).
 * Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).month = ctx => {
  'use strict';
  const { root, model, escape, fmt, num, dateText, monthKey, monthLabel, liveOpenMonth, columns, ghosts, redraw, showNotice,
    legacyTripRow, webTripRow, sheetPendingRows, bookingMissingRows, payRows } = ctx;
  const { short } = CongNoFormat;
  // Chuyến Sheet chưa vào sổ: dòng mới, hoặc lệch mà chưa nối được dòng nào trong sổ.
  const sheetPending = row => row.sync_state === 'NEW' || !row.existing_id;
  // DONG-MO-BOOKING-01: chuyến booking sổ chưa có; bỏ chuyến đã hiện thành dòng Sheet chờ (cùng container, lệch không quá 3 ngày).
  const contKey = value => String(value ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const near = (a, b) => Math.abs(Date.parse(String(a).slice(0, 10)) - Date.parse(String(b).slice(0, 10))) <= 3 * 86400000;
  const bookingMissing = (data, key, sheetRows) => (data.booking_missing?.items ?? []).filter(row => monthKey(row.date) === key
    && !sheetRows.some(other => contKey(other.container) === contKey(row.container) && near(other.event_date, row.date)));
  // Xuống dòng giữa các hàng của bảng tháng, giữ đúng như trước khi tách file để DOM không đổi.
  const GAP = '\n          ';

  // ?month=yyyy-mm (từ Công nợ theo tháng, Đòi nợ): xem tháng đó và cuộn tới sau lần vẽ đầu có tháng đó.
  const wanted = /^\d{4}-(0[1-9]|1[0-2])$/.exec(new URLSearchParams(location.search).get('month') ?? '')?.[0] ?? null;
  // Tháng đang xem (SO-GON-05): chọn ở lần vẽ đầu, rồi chỉ đổi khi người dùng bấm chip hoặc một phần gọi showMonth; chỉ sống
  // trong tab. Tự cập nhật, bỏ đánh dấu ?loc= hay qua ngày không làm sổ tự nhảy tháng.
  let selected = wanted;
  let scrollTarget = wanted;
  // Tháng đang hiện ở lần vẽ gần nhất (để showMonth biết có cần vẽ lại không).
  let lastOpen = null;

  // Tháng có bảng, xếp theo tháng: tháng server có số; tháng hiện tại (giờ VN theo server, đồng hồ máy khi server cũ chưa trả)
  // dù chưa có dữ liệu, để thanh tháng luôn có tháng đang làm; tháng mà một dòng rơi vào.
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
      ...(data.sheet_sync?.items ?? []).filter(sheetPending).map(item => ({ month: item.event_date })),
      ...(data.booking_missing?.items ?? []).map(item => ({ month: item.date }))]) {
      const key = monthKey(row.month);
      if (key && !groups.some(group => monthKey(group.month) === key)) groups.push({ month: `${key}-01`, placeholder: true });
    }
    groups.sort((a, b) => monthKey(a.month).localeCompare(monthKey(b.month)));
    return { groups, openKey, outgoing };
  }

  // Tháng có số liệu: có phát sinh hoặc đã thu khác 0 (số của server), hoặc có dòng rơi vào (chuyến, sổ gốc, phiếu thu,
  // chuyến Sheet chờ). Tháng hiện tại server trả toàn 0 khi chưa có gì thì không tính.
  const nonZero = value => value != null && !/^-?0*$/.test(String(value));
  function hasRows(data, item) {
    const key = monthKey(item.month);
    return nonZero(item.charges_vnd) || nonZero(item.received_vnd)
      || [...(data.trips ?? []), ...(data.legacy_rows ?? []), ...(data.receipts ?? []).map(row => ({ month: row.date })),
      ...(data.sheet_sync?.items ?? []).filter(sheetPending).map(row => ({ month: row.event_date }))].some(row => monthKey(row.month) === key);
  }
  // Tháng đang xem (SO-GON-05): giữ tháng đã chọn nếu còn chip; chưa chọn thì tháng của ?loc=, rồi tháng hiện tại có số liệu,
  // rồi tháng gần nhất có số liệu, cuối cùng là tháng hiện tại.
  function openMonths(data, groups, openKey) {
    const keys = groups.map(item => monthKey(item.month));
    if (!selected || !keys.includes(selected)) {
      const filled = groups.filter(item => hasRows(data, item)).map(item => monthKey(item.month));
      selected = (ctx.locMonths?.(data) ?? []).find(key => keys.includes(key))
        ?? (filled.includes(openKey) ? openKey : filled.filter(key => key <= openKey).at(-1) ?? filled.at(-1) ?? openKey);
    }
    return selected;
  }

  // Việc chờ của một tháng, cho chấm cam trên chip: cùng điều kiện với ?loc= (so-khach-v7-loc-ui.js) và dòng Sheet chờ.
  // Mỗi mục [số, tên, loại]: loại thieu-gia/cho-kiem là ?loc=, sheet là chuyến Sheet chờ.
  function monthWork(data, key) {
    const trips = (data.trips ?? []).filter(trip => !trip.deleted && monthKey(trip.month) === key);
    const sheet = (data.sheet_sync?.items ?? []).filter(item => monthKey(item.event_date) === key).length;
    return [[trips.filter(trip => trip.status === 'confirmed' && trip.is_missing_price === true).length, 'chưa có giá', 'thieu-gia'],
      [trips.filter(trip => trip.status === 'pending_review').length, 'chờ kiểm', 'cho-kiem'], [sheet, 'từ Sheet cần xem', 'sheet']]
      .filter(([count]) => count > 0);
  }
  // Việc chờ của cả sổ: cộng mọi chip tháng theo loại, giữ thứ tự loại như trên. Số trên thẻ Sổ và khối "Còn gì làm số chưa
  // đúng" của thẻ Tình hình (TRANG-KHACH-01) cùng lấy ở đây nên luôn bằng tổng chấm cam.
  function bookWork(data, groups = bookMonths(data, data.status === 'active').groups) {
    const total = new Map();
    for (const item of groups) {
      for (const [count, what, kind] of monthWork(data, monthKey(item.month))) total.set(kind, [(total.get(kind)?.[0] ?? 0) + count, what, kind]);
    }
    return ['thieu-gia', 'cho-kiem', 'sheet'].filter(kind => total.has(kind)).map(kind => total.get(kind));
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

  // Thanh tháng: ổ khóa (V7-SO) kèm chữ trạng thái, Debit note khi tháng có chuyến tính tiền, dòng tóm tắt Nợ đầu tháng +
  // Phát sinh − Đã thu = Còn nợ cuối tháng (SO-GON-05; số lấy nguyên từ GET, mỗi số tiền của tháng vẫn hiện một lần như SO-GON-03).
  function monthBar(item, key, { locked, active, debit, totals }) {
    const label = monthLabel(key);
    // SK-N11: chữ rê chuột và tên đọc cho trình đọc màn hình nói cùng một câu: trạng thái rồi việc nút làm.
    const lockSay = locked ? `Đang khóa · bấm để mở khóa tháng ${label}` : `Đang mở · bấm để khóa tháng ${label}`;
    const lock = `<button class="month-lock" data-month="${escape(item.month)}" aria-label="${lockSay}" `
      + `title="${lockSay}" aria-pressed="${!locked}" ${active ? '' : 'disabled'}>${locked ? '<svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>' : '<svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/></svg>'}</button>`
      + `<span class="month-lock-text">${locked ? 'Đã khóa' : 'Đang mở'}</span>`;
    const debitButton = debit ? `<button class="debit-open" data-month="${escape(key)}" aria-haspopup="dialog" aria-label="Debit note tháng ${label}" title="Debit note tháng ${label}"><svg viewBox="0 0 24 24"><path d="M7 9V3h10v6"/><rect x="4" y="9" width="16" height="8" rx="1.5"/><path d="M7 14h10v7H7z"/></svg></button>` : '';
    const part = (name, value, cls) => `<span class="${cls}">${name} <b>${fmt(value)}${cls === 'month-end' && value != null ? ' đ' : ''}</b></span>`;
    const stats = `${part('Nợ đầu tháng', item.prior_months_vnd, 'month-prior')}<i aria-hidden="true">+</i>`
      + `${part('Phát sinh', totals.chargesVnd, 'month-charges')}<i aria-hidden="true">−</i>${part('Khách trả', totals.receivedVnd, 'month-received')}`
      + `<i aria-hidden="true">=</i>${part('Còn nợ cuối tháng', item.end_of_month_vnd, 'month-end')}`;
    return `<tr class="month"><th colspan="${columns.count()}" scope="rowgroup"><span class="month-title">THÁNG ${label}${lock}${debitButton}`
      + `</span></th></tr><tr class="month-summary"><td colspan="${columns.count()}"><div class="month-summary-layout">`
      + `<em class="month-stats" aria-label="Đối chiếu số nợ tháng ${label}">${stats}</em><div class="month-pay-slot"></div></div></td></tr>`;
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
      + `Điều chỉnh ${row.trip_id ? 'chuyến' : 'cả tháng'}${row.note ? ` · ${escape(row.note)}` : ''}</td>${amount(row)}</tr>`).join('');
  }

  // Tháng cũ của dòng vừa đổi ngày sang tháng khác: một dòng mờ có Xem / Hoàn tác (ctx.ghosts, so-khach-v7-edit-ui.js).
  const ghostRows = key => ghosts.map((ghost, index) => ghost.month !== key ? '' : `<tr class="ghost"><td colspan="${columns.count()}">`
    + `↪ ${escape(ghost.container || 'Chuyến')} (ngày cũ ${escape(dateText(ghost.oldIso))}) đã chuyển sang tháng ${monthLabel(ghost.to)}`
    + `<button type="button" class="ghost-go" data-row="${escape(`${ghost.kind}-${ghost.id}`)}">Xem</button>`
    + `<button type="button" class="ghost-undo" data-ghost="${index}">Hoàn tác</button></td></tr>`).join('');

  // Dòng Tổng tháng: tổng từng cột phụ phí (chuyến đã tính tiền và dòng sổ gốc của tháng) và Thành tiền của server. Đã thu ở
  // dòng tóm tắt của thanh tháng và đầu khối phiếu thu (SO-GON-06).
  function subtotalRow(item, key, { locked, active, feeTotalCells, totals }) {
    return `<tr class="subtotal"><td colspan="${columns.unitPrice()}">`
      // SK-N11: nút tắt ở tháng khóa nói lý do khi rê chuột.
      + `<button class="add-month-adjustment" data-month="${escape(item.month)}" ${active && !locked ? ''
        : `disabled${locked ? ' title="Tháng đang khóa, mở khóa trước"' : ''}`}>+ Điều chỉnh cả tháng</button></td>`
      + `<td class="num unit-total" title="Chỉ cộng giá đã có; bỏ qua chuyến thiếu giá, chờ kiểm hoặc đã loại">${fmt(totals.unitPriceVnd)}</td>`
      + `${feeTotalCells}${num(fmt(totals.chargesVnd), 'amount-total')}</tr><tr class="spacer"><td colspan="${columns.count()}"></td></tr>`;
  }

  function monthSection(item, { data, active, openKey, lockFlags, historical, outgoing }) {
    const key = monthKey(item.month);
    const legacyRows = historical.get(key) ?? [];
    const trips = (data.trips ?? []).filter(row => monthKey(row.month) === key);
    const locked = lockFlags.has(key) ? lockFlags.get(key) : key !== openKey;
    const legacy = legacyPairs(legacyRows);
    const totals = { chargesVnd: item.charges_vnd, receivedVnd: item.received_vnd, unitPriceVnd: model.unitPriceTotal(trips, legacyRows) };
    const debit = legacy.some(line => line.trip) || trips.some(trip => trip.status === 'confirmed');
    // CHUYEN-KHONG-HOI-01: dòng chờ tab Sheet hiện ở tháng của nó để xem; không tạo bảng tháng, không tính vào chấm việc.
    const sheetRows = [...(data.sheet_sync?.items ?? []).filter(row => monthKey(row.event_date) === key && sheetPending(row)),
      ...(data.sheet_sync?.waiting_items ?? []).filter(row => monthKey(row.event_date) === key)];
    // DA-THU-01: phiếu nằm ở tháng của ngày thu, đủ số tiền một lần (như Sheet); `lines` là phần trừ nợ còn hiệu lực
    // (phiếu đã hủy: phần bị hủy cùng lệnh hủy).
    const received = (data.receipts ?? []).filter(row => monthKey(row.date) === key).map(row => {
      const lines = (row.allocations ?? []).filter(line => row.voided_by_event != null
        ? line.superseded_by_event === row.voided_by_event : line.superseded_by_event === null);
      return { ...row, lines, line: { amount_vnd: row.amount_vnd, kind: lines[0]?.kind } };
    });
    const receipts = [...received, ...(outgoing.get(key) ?? [])];
    const adjustments = (data.adjustments ?? []).filter(row => monthKey(row.month) === key);
    // SO-GON-02 (29/10/2026, phương án A): phiếu thu là danh sách riêng, không chung hàng với chuyến, để không đọc nhầm
    // "chuyến này trả số tiền này". SO-GON-06 (1/11/2026): danh sách đó là khối ở đầu tháng, bảng chuyến dùng hết bề ngang.
    // Không có bảng nhập chuyến: chuyến vào sổ từ Sheet (NHAP-SHEET-02). Phiếu thu ghi ở khung "Ghi phiếu thu" (SO-GON-04).
    const openHere = active && !locked;
    // STT chuyến web nối tiếp các dòng chuyến từ Sheet của tháng (dòng Sheet vẽ trước, như thứ tự trên Sheet).
    const sttBase = new Set(legacyRows.filter(row => row.kind !== 'receipt').map(row => row.display?.row)).size;
    const tripRows = legacy.map(line => line.trip ? legacyTripRow(line.trip, locked) : '').join('')
      + trips.map((trip, index) => webTripRow(trip, index, { locked, sttBase })).join('');
    const pays = payRows(key, { legacy, receipts, locked });
    const payBlock = `<tr class="month-pay"><td colspan="${columns.count()}"><div class="pay-block">`
      + `<div class="pay-head">Khách trả trong tháng <span class="pay-count">· ${legacy.filter(line => line.receipt).length + receipts.filter(row => row.voided_by_event == null).length} phiếu</span>${pays ? '' : '<span class="pay-empty">Chưa có phiếu thu</span>'}</div>`
      + `<table class="ledger-inner pay-list${pays ? '' : ' empty'}" aria-label="Tiền khách trả tháng ${monthLabel(key)}">`
      + `<colgroup><col style="width:84px"><col style="width:104px"><col><col style="width:112px"><col style="width:104px"></colgroup><tbody>${pays}</tbody></table></div></td></tr>`;
    // SO-CHI-TIET-01: sổ có bảng chi tiết thì bảng đó thay bảng chuyến, chỉ để xem; sửa ở bảng sổ (nút trên thanh chuyến).
    const detailed = ctx.detailOn(data);
    const missing = detailed ? ctx.detailMissing(data, key) : trips.filter(row => row.is_missing_price && row.status === 'confirmed').length
      + legacy.filter(line => line.trip && line.trip.current?.unit_price_vnd == null && (line.trip.d.flags ?? []).includes('MISSING_PRICE')).length;
    const badge = missing ? `<button type="button" class="month-missing" data-missing-month="${escape(key)}" title="Xem ${missing} chuyến chưa có giá">ⓘ ${missing} chưa giá</button>` : '';
    const heading = detailed ? `<h3>${ctx.detailCount(data, key)} chuyến trong tháng</h3>`
      : `<h3>Chuyến trong tháng <span>· ${sttBase + trips.filter(row => !row.deleted).length} chuyến</span></h3>`;
    // SO-GON-07 (sửa đổi 25/11/2026): tháng mở hiện đủ cột phụ phí riêng, tháng khóa ẩn cột trống; nút đổi tạm cho tháng đang xem
    // (bảng chi tiết có cột riêng của nó). Nút ghi số cột sẽ ẩn/hiện để người dùng biết bảng đang thiếu cột nào.
    const feeToggle = detailed || !ctx.feeEmpty ? ''
      : `<button type="button" class="fee-cols-toggle" aria-pressed="${ctx.feeShowAll}">${ctx.feeShowAll ? `Ẩn ${ctx.feeEmpty} cột phí trống` : `Hiện ${ctx.feeEmpty} cột phí trống`}</button>`;
    const toolbar = `<div class="trip-toolbar">${heading}${feeToggle}${ctx.detailTools(data, key)}<div class="trip-tools"></div></div>`;
    const body = `${payBlock}<tr class="month-body"><td class="trip-side" colspan="${columns.trip()}">`
      + (detailed ? ctx.detailTable(data, key) : `<table class="ledger-inner trip-list${columns.shipper() ? '' : ' no-shipper'}"><colgroup>${columns.tags(0, columns.trip())}</colgroup>`
      + `<tbody>${tripRows}</tbody></table>`) + '</td></tr>';
    const feeTotals = model.feeColumnTotals([...legacyRows.filter(row => row.kind === 'trip'),
      ...trips.filter(trip => trip.status === 'confirmed')].map(row => row.fee_lines ?? []), ctx.shownFeeIds);
    const feeTotalCells = [...feeTotals.own, feeTotals.otherVnd].map(value => num(value === null ? '' : model.formatVnd(value), 'fee')).join('');
    return [`<section id="thang-${escape(key)}"><table class="ledger${locked ? ' locked' : ''}" aria-label="Sổ khách tháng ${monthLabel(key)}">`
      + `<colgroup>${columns.all()}</colgroup><tbody>`,
    monthBar(item, key, { locked, active, debit, totals }).replace('Phát sinh <b>', `Phát sinh ${badge}<b>`),
    detailed ? body : `${body}${sheetPendingRows(sheetRows)}${bookingMissingRows(bookingMissing(data, key, sheetRows))}${adjustmentRows(adjustments, openHere)}${ghostRows(key)}`,
    `${detailed ? '' : subtotalRow(item, key, { locked, active, feeTotalCells, totals })}</tbody></table>${toolbar}</section>`].join(GAP);
  }

  // Chip một tháng trên thanh tháng (THANH-THANG-01, thay cách ghi năm của SK-N8): chữ luôn là "T9", năm đứng riêng ở nhãn
  // nhóm phía trước; chip đang xem chỉ đổi màu, không đổi chữ. Dấu khóa chỉ để xem (khóa/mở khóa bấm ở thanh của bảng tháng),
  // chấm cam là số việc chờ.
  function monthChip(item, { data, openKey, lockFlags }) {
    const key = monthKey(item.month);
    const locked = lockFlags.has(key) ? lockFlags.get(key) : key !== openKey;
    const end = item.end_of_month_vnd == null ? '–' : short(item.end_of_month_vnd);
    const work = monthWork(data, key);
    const todo = work.map(([count, what]) => `${count} ${what}`).join(' · ');
    const total = work.reduce((sum, [count]) => sum + count, 0);
    return `<a class="month-chip${locked ? ' locked' : ''}${key === selected ? ' on' : ''}" href="#thang-${escape(key)}" data-month="${escape(key)}" `
      + `${key === selected ? 'aria-current="true" ' : ''}`
      + `aria-label="Tháng ${monthLabel(key)} · còn nợ cuối tháng ${escape(end)}${locked ? ' · đã khóa' : ''}${todo ? ` · ${escape(todo)}` : ''}">`
      + `<span class="chip-name">T${Number(key.slice(5, 7))}</span>`
      + `${locked ? '<span class="chip-lock" aria-hidden="true">🔒</span>' : ''}`
      + `${total ? `<span class="chip-work" title="${escape(todo)}" aria-hidden="true">${total}</span>` : ''}</a>`;
  }

  // THANH-THANG-01 (26/11/2026, người dùng chọn hướng A): thanh tháng là một dải liên tục chia nhóm theo năm, mỗi năm từ tháng
  // đầu của sổ (hoặc T1) tới tháng cuối của sổ (hoặc T12); tháng không có số liệu vẫn có ô mờ không bấm được để vị trí tháng cố
  // định và thấy rõ khoảng trống. Nhãn năm là nút thu/mở nhóm (sửa đổi cùng ngày). Mặc định: sổ không quá FIT_MONTHS tháng (vừa
  // một hàng ở 1280) mở hết; sổ dài hơn chỉ mở năm của tháng đang xem và năm mới nhất. Người bấm thu/mở năm nào thì nhớ trong tab.
  const FIT_MONTHS = 16;
  const yearOpen = new Map();
  const monthIndex = key => Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1;
  const keyOf = index => `${Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, '0')}`;
  function monthStrip(groups, book, open) {
    const byKey = new Map(groups.map(item => [monthKey(item.month), item]));
    const keys = [...byKey.keys()];
    if (!keys.length) return '';
    const [first, last] = [monthIndex(keys[0]), monthIndex(keys.at(-1))];
    const years = [...new Set(keys.map(key => key.slice(0, 4)))];
    const shown = new Set(last - first < FIT_MONTHS ? years : [keys.at(-1).slice(0, 4), (open ?? keys.at(-1)).slice(0, 4)]);
    return years.map(year => {
      const expanded = yearOpen.get(year) ?? shown.has(year);
      const current = (open ?? '').startsWith(year);
      const count = keys.filter(key => key.startsWith(year)).length;
      const cells = [];
      for (let index = Math.max(first, Number(year) * 12); index <= Math.min(last, Number(year) * 12 + 11); index += 1) {
        const key = keyOf(index);
        cells.push(byKey.has(key) ? monthChip(byKey.get(key), book)
          : `<span class="month-empty" title="Tháng ${monthLabel(key)} không có số liệu">T${index % 12 + 1}</span>`);
      }
      return `<span class="month-group${expanded ? '' : ' collapsed'}"><button type="button" class="month-year${current ? ' current' : ''}" `
        + `data-year="${year}" aria-expanded="${expanded}" title="${expanded ? 'Thu gọn' : 'Mở'} năm ${year} (${count} tháng có số liệu)">`
        + `${year} <span aria-hidden="true">${expanded ? '▾' : '▸'}</span></button>${cells.join('')}</span>`;
    }).join('');
  }
  // Thu/mở một năm ngay trên thanh, không vẽ lại sổ (chữ đang gõ ở tháng đang xem không mất); lần vẽ sau theo yearOpen.
  function toggleYear(button) {
    const expanded = button.getAttribute('aria-expanded') !== 'true';
    yearOpen.set(button.dataset.year, expanded);
    button.closest('.month-group').classList.toggle('collapsed', !expanded);
    button.setAttribute('aria-expanded', String(expanded));
    button.title = `${expanded ? 'Thu gọn' : 'Mở'}${button.title.replace(/^(Thu gọn|Mở)/, '')}`;
    button.lastElementChild.textContent = expanded ? '▾' : '▸';
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
    const book = { data, active, openKey, lockFlags, historical, outgoing };
    // Chỉ vẽ tháng đang xem (SO-GON-05). work: tổng số việc chờ của mọi chip (số trên thẻ Sổ của trang khách, TRANG-KHACH-01).
    return { sections: groups.filter(item => monthKey(item.month) === open).map(item => monthSection(item, book)).join(''),
      chips: `<nav class="month-chips" aria-label="Các tháng của sổ">${monthStrip(groups, book, open)}</nav>`,
      work: bookWork(data, groups).reduce((sum, [count]) => sum + count, 0) };
  }

  // ---- Chip tháng, tháng đang xem ----
  const sectionOf = key => root.querySelector(`#thang-${key}`);
  // Bấm chip thì cuộn về đầu tháng (đầu sổ, dưới phần dính); lần cuộn tới ?month= lúc mở trang thì tức thì, vì lần vẽ lại ngay
  // sau đó (danh sách khách về) giữ vị trí cuộn đang có và sẽ cắt ngang một lần cuộn mượt.
  const scrollToMonth = (key, behavior = 'auto') => sectionOf(key)?.scrollIntoView({ block: 'start', behavior });
  // Chuyển sang xem một tháng (vẽ lại); trả về true khi có vẽ lại. Phần khác gọi trước khi tìm một dòng của tháng.
  function showMonth(key) {
    if (!key || lastOpen === key) return false;
    selected = key;
    redraw();
    return true;
  }
  // Đổi tháng không được làm mất chữ đang gõ hay dòng hỏi đang mở ở tháng đang xem (khung Ghi phiếu thu nằm ngoài sổ, không
  // bị ảnh hưởng).
  function busyIn(section) {
    return [...section.querySelectorAll('.info-input,.money-input,.month-amount,.month-note,.saved-receipt-input')].some(input => input.value.trim())
      || section.querySelector('.review-prompt,.void-prompt,.move-ask,.delete-prompt,.month-adjustment-input,.lock-ask,.paste-review');
  }
  root.addEventListener('click', event => {
    if (event.target.closest('.fee-cols-toggle')) { ctx.toggleFeeColumns(); return; }
    const missing = event.target.closest('.month-missing');
    if (missing) {
      // Bảng chi tiết tự lọc được tại chỗ, không phải rời sang bảng sổ.
      if (ctx.detailOn(ctx.snapshot)) ctx.detailShowMissing(missing.dataset.missingMonth);
      else ctx.showLoc('thieu-gia');
      return;
    }
    const year = event.target.closest('.month-year');
    if (year) { toggleYear(year); return; }
    const chip = event.target.closest('.month-chip');
    if (!chip) return;
    event.preventDefault();
    const key = chip.dataset.month;
    const section = lastOpen && key !== lastOpen ? sectionOf(lastOpen) : null;
    if (section && busyIn(section)) {
      showNotice(`Tháng ${monthLabel(lastOpen)} còn ô đang sửa hoặc câu hỏi chưa trả lời. Làm xong hoặc bấm Thôi rồi hãy sang tháng khác.`);
      return;
    }
    showMonth(key);
    scrollToMonth(key);
    root.querySelector(`.month-chip[data-month="${key}"]`)?.focus({ preventScroll: true });
  });
  // Chip của tháng đang xem được tô (lúc vẽ); sổ nhiều tháng thì thanh chip cuộn ngang để chip đó luôn trong tầm nhìn.
  function markCurrent() {
    const bar = root.querySelector('.month-chips');
    const chip = bar?.querySelector('.month-chip.on');
    if (chip && (chip.offsetLeft < bar.scrollLeft || chip.offsetLeft + chip.offsetWidth > bar.scrollLeft + bar.clientWidth)) {
      bar.scrollLeft = chip.offsetLeft - (bar.clientWidth - chip.offsetWidth) / 2;
    }
  }
  // Sau mỗi lần vẽ: cuộn tới tháng của ?month= (một lần) rồi đưa chip tháng đang xem vào tầm nhìn.
  function monthsAfterRender() {
    if (typeof root.querySelectorAll !== 'function') return;
    if (scrollTarget && sectionOf(scrollTarget)) {
      scrollToMonth(scrollTarget, 'instant');
      scrollTarget = null;
    }
    markCurrent();
  }

  // Tháng sẽ vẽ của bản GET này (cùng luật monthSections): phần lõi cần trước khi dựng khung cột (SO-GON-07).
  function shownMonthKey(data) {
    const { groups, openKey } = bookMonths(data, data.status === 'active');
    return openMonths(data, groups, openKey);
  }
  // Tháng đang xem có sửa được không (cùng luật khóa của monthSection): SO-GON-07 sửa đổi 25/11/2026 hiện đủ cột phí ở tháng mở.
  function shownMonthOpen(data) {
    const active = data.status === 'active';
    const { groups, openKey } = bookMonths(data, active);
    const key = openMonths(data, groups, openKey);
    const lock = (data.month_locks ?? []).find(row => monthKey(row.month) === key);
    return active && !(lock ? lock.locked : key !== openKey);
  }

  Object.assign(ctx, { monthSections, monthsAfterRender, showMonth, bookWork, shownMonthKey, shownMonthOpen });
};
