/* Sổ khách V7 bản live — các bảng tháng: chọn tháng nào có bảng, thanh tháng (ổ khóa, Debit note, còn nợ cuối tháng),
 * thân tháng (bảng chuyến của so-khach-v7-trips-ui.js bên trái, phiếu thu của so-khach-v7-pay-ui.js bên phải), dòng điều chỉnh,
 * dòng mờ "đã chuyển sang tháng", dòng Tổng tháng và danh sách tháng bên phải màn. Tách từ renderSnapshot của
 * so-khach-v7-ui.js (31/10/2026, DOM không đổi). Số tiền lấy nguyên từ GET; tổng cột phụ phí do model cộng (ARCH-03).
 * Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).month = ctx => {
  'use strict';
  const { model, escape, fmt, num, dateText, monthKey, monthLabel, liveOpenMonth, columns, ghosts,
    legacyTripRow, webTripRow, sheetPendingRows, payRows } = ctx;
  // Chuyến Sheet chưa vào sổ: dòng mới, hoặc lệch mà chưa nối được dòng nào trong sổ.
  const sheetPending = row => row.sync_state === 'NEW' || !row.existing_id;
  // Xuống dòng giữa các hàng của bảng tháng, giữ đúng như trước khi tách file để DOM không đổi.
  const GAP = '\n          ';

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
  // tháng hiện một lần; rê chuột xem cách tính).
  function monthBar(item, key, { locked, active, debit, totals }) {
    const label = monthLabel(key);
    const lock = `<button class="month-lock" data-month="${escape(item.month)}" aria-label="${locked ? 'Mở khóa' : 'Khóa'} tháng ${label}" `
      + `title="${locked ? 'Đã khóa' : 'Đang mở'}" aria-pressed="${!locked}" ${active ? '' : 'disabled'}>${locked ? '🔒' : '🔓'}</button>`;
    const debitButton = debit ? `<button class="debit-open" data-month="${escape(key)}" aria-haspopup="dialog">Debit note</button>` : '';
    const how = `Nợ các tháng trước ${fmt(item.prior_months_vnd)} + phát sinh ${fmt(totals.chargesVnd)} − đã thu ${fmt(totals.receivedVnd)}`;
    return `<tr class="month"><th colspan="${columns.count()}" scope="rowgroup"><span class="month-title">THÁNG ${label}${lock}${debitButton}`
      + `<em class="month-stats"><span class="month-end" title="${how}">Còn nợ cuối tháng: <b>${fmt(item.end_of_month_vnd)}</b></span></em></span></th></tr>`;
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

  function monthSection(item, { data, active, openKey, lockFlags, historical, outgoing }) {
    const key = monthKey(item.month);
    const legacyRows = historical.get(key) ?? [];
    const trips = (data.trips ?? []).filter(row => monthKey(row.month) === key);
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
    const locked = lockFlags.has(key) ? lockFlags.get(key) : key !== openKey;
    // SO-GON-02 (29/10/2026, phương án A): chuyến bên trái, phiếu thu là danh sách riêng bên phải — không chung hàng,
    // để không đọc nhầm "chuyến này trả số tiền này".
    const legacy = legacyPairs(legacyRows);
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
    const totals = { chargesVnd: item.charges_vnd ?? '0', receivedVnd: item.received_vnd ?? '0' };
    const feeTotals = model.feeColumnTotals([...legacyRows.filter(row => row.kind === 'trip'),
      ...trips.filter(trip => trip.status === 'confirmed')].map(row => row.fee_lines ?? []), ctx.feeColumnIds);
    const feeTotalCells = [...feeTotals.own, feeTotals.otherVnd].map(value => num(value === null ? '' : model.formatVnd(value), 'fee')).join('');
    const debit = legacy.some(line => line.trip) || trips.some(trip => trip.status === 'confirmed');
    return [`<section id="thang-${escape(key)}"><table class="ledger${locked ? ' locked' : ''}" aria-label="Sổ khách tháng ${monthLabel(key)}">`
      + `<colgroup>${columns.all()}</colgroup><tbody>`,
    monthBar(item, key, { locked, active, debit, totals }),
    `${body}${sheetPendingRows(sheetRows)}${adjustmentRows(adjustments, openHere)}${ghostRows(key)}`,
    `${subtotalRow(item, key, { locked, active, feeTotalCells, totals })}</tbody></table></section>`].join(GAP);
  }

  // Các bảng tháng và danh sách tháng (thanh bên phải) của một bản GET.
  function monthSections(data, active) {
    const { groups, openKey, outgoing } = bookMonths(data, active);
    const lockFlags = new Map((data.month_locks ?? []).map(row => [monthKey(row.month), row.locked]));
    const historical = new Map();
    for (const row of data.legacy_rows ?? []) {
      const key = monthKey(row.month);
      if (!historical.has(key)) historical.set(key, []);
      historical.get(key).push(row);
    }
    const book = { data, active, openKey, lockFlags, historical, outgoing };
    return { sections: groups.map(item => monthSection(item, book)).join(''),
      navigation: groups.map(item => `<a href="#thang-${escape(monthKey(item.month))}"><span>${monthLabel(monthKey(item.month))}</span>`
        + `<small>${fmt(item.outstanding_vnd)}</small></a>`).join('') };
  }

  Object.assign(ctx, { monthSections });
};
