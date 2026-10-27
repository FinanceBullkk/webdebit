/* Bản xem sổ khách ẩn danh: chỉ lấy số tiền từ SoKhachV7Model. */
(() => {
  'use strict';
  const live = window.SoKhachV7Api;
  const book = live ? null : structuredClone(SO_KHACH_V7_MAU);
  const model = SoKhachV7Model;
  const root = document.querySelector('#app');
  const suppliedToday = new URLSearchParams(location.search).get('today');
  let today = '2026-10-19';
  if (suppliedToday && /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(suppliedToday)
    && !Number.isNaN(Date.parse(`${suppliedToday}T00:00:00Z`))) today = suppliedToday;
  const openMonth = today.slice(0, 7);
  const months = live ? [] : [...book.months].sort((a, b) => a.key.localeCompare(b.key));
  const locks = Object.fromEntries(months.map(month => [month.key, month.key !== openMonth]));
  const history = [];
  let historyOpen = false;
  let monthPrompt = null;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const conflictFields = row => row.changed_fields?.length
    ? row.changed_fields.map(field => ({ event_date: 'ngày', carrier: 'hãng tàu', shipper: 'shipper',
      shipper_unavailable: 'thiếu shipper Sheet', origin: 'nơi đi', destination: 'nơi đến', booking: 'booking' })[field] || field).join(', ')
    : ({ OTHER_CUSTOMER: 'khách khác', BASELINE_MATCH_UNRESOLVED: 'bản mốc chưa nối',
      CONTAINER_REUSED_OR_CHANGED: 'container đã dùng', AMBIGUOUS_MATCH: 'nhiều chuyến trùng' })[row.sync_reason] || 'chưa rõ';
  const sheetFieldLabel = field => ({ carrier: 'Hãng tàu', shipper: 'Shipper', event_date: 'Ngày chuyến', origin: 'Điểm đi', destination: 'Điểm đến', booking: 'Booking' }[field] || field);
  const resolvableSheetFields = new Set(['carrier', 'shipper', 'origin', 'destination', 'event_date', 'booking']);
  const monthLabel = key => `${Number(key.slice(5))}/${key.slice(0, 4)}`;
  const money = amount => amount === null || amount === undefined ? '–' : model.formatVnd(amount);
  const fieldMoney = amount => amount === null || amount === undefined ? '–' : model.formatVnd(model.parseVnd(amount));
  const outstanding = model?.formatOutstanding;
  const labels = live ? ['STT', 'Số container', 'Hãng tàu', 'Shipper', 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá', 'Phụ phí', 'Thành tiền', 'Ngày trả', 'Hình thức', 'Số tiền trả', 'Còn nợ cộng dồn'] : ['STT', 'Số container', 'Hãng tàu', 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá', 'Phụ phí', 'Thành tiền', 'Ngày trả', 'Hình thức', 'Số tiền trả', 'Còn nợ cộng dồn'];
  const wide = live ? [52, 148, 104, 128, 104, 118, 118, 128, 116, 148, 112, 112, 150, 158] : [52, 148, 104, 104, 118, 118, 128, 116, 148, 112, 112, 150, 158];
  const widths = wide.map((width, index) => `<col style="width:${width}px" class="col-${index}">`).join('');
  const cell = (value, classes = '') => `<td class="${classes}">${escape(value)}</td>`;
  const num = (value, classes = '') => cell(value, `num ${classes}`);
  const empty = (classes = '') => `<td class="${classes}"></td>`;
  const methods = ['THU TIỀN', 'CẤN TRỪ', 'ỨNG TRƯỚC', 'KHÁC'];
  let notice = '';
  let voidPrompt = null;

  function log(type, description, reason = '') {
    history.unshift({ time: new Date().toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }), type, description, reason });
  }

  function reallocate(plan = model.planReallocation(book)) {
    const old = new Map(months.flatMap(month => month.receipts.filter(receipt => receipt.voided === null)
      .map(receipt => [receipt.pid, new Set(months.filter(item => item.receipts.some(line => line.pid === receipt.pid && line.voided === null)).map(item => item.key))])));
    for (const month of months) month.receipts = month.receipts.filter(receipt => receipt.voided !== null);
    for (const line of plan.lines) months.find(month => month.key === line.monthKey).receipts.push(line.receipt);
    const changed = plan.changedPids.map(pid => {
      const before = [...(old.get(pid) ?? [])].map(monthLabel).join(', ');
      const after = months.filter(month => month.receipts.some(receipt => receipt.pid === pid && receipt.voided === null)).map(month => monthLabel(month.key)).join(', ');
      return `${pid}: tháng ${before} → tháng ${after}`;
    });
    if (changed.length) log('Phân bổ lại', changed.join(' · '));
    notice = plan.changedPids.length
      ? `Đã phân bổ lại khoản thu theo nợ cũ trước: ${plan.changedPids.join(', ')}` : '';
  }

  function editCell(value, field, index, month, classes = '') {
    return `<td class="num editable ${classes}" tabindex="0" role="button" aria-label="Sửa ${field === 'unitPriceVnd' ? 'đơn giá' : 'phụ phí'} dòng ${index + 1} tháng ${monthLabel(month.key)}" data-month="${month.key}" data-index="${index}" data-field="${field}">${escape(value)}</td>`;
  }

  function referenceFields(scope = root) {
    const reference = scope.querySelector('.receipt-reference')?.value.trim();
    return reference ? { reference } : {};
  }

  function referenceLine(receipt, entry = false) {
    if (!receipt && !entry) return '';
    const voided = receipt && (receipt.voided != null || receipt.voided_by_event != null);
    return `<tr class="reference-row"><td colspan="9"></td>${receipt
      ? `<td colspan="3" class="pay receipt receipt-edit${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="reference" tabindex="${voided ? '-1' : '0'}" role="button" aria-label="Sửa tham chiếu ${escape(receipt.pid)}">Tham chiếu: ${escape(receipt.reference || '–')}</td>`
      : '<td colspan="3" class="pay"><label>Tham chiếu <input class="receipt-reference" aria-label="Tham chiếu" maxlength="500" placeholder="Tùy chọn: số giao dịch, ngoại tệ/tỷ giá…"></label></td>'}<td></td></tr>`;
  }

  function renderLine(trip, receipt, index, month) {
    const result = trip ? model.tripAmount(trip) : null;
    const feeOnly = result?.isFeeOnly;
    const missing = result?.isMissingPrice;
    const pending = trip?.status === 'pending_review';
    const open = month.key === openMonth;
    const cells = [
      trip && !feeOnly ? cell(index + 1) : empty(),
      cell(trip?.container ?? (month.opening ? 'Nợ cũ chuyển sang sổ mới' : feeOnly ? 'Phí lẻ' : '')),
      cell(trip?.carrier ?? ''), cell(trip?.date ?? ''), cell(trip?.from ?? ''), cell(trip?.to ?? ''),
      pending ? num(fieldMoney(trip.unitPriceVnd)) : trip ? editCell(missing ? 'chưa có giá' : fieldMoney(trip.unitPriceVnd), 'unitPriceVnd', index, month, missing ? 'missing' : '') : empty('num'),
      pending ? num(fieldMoney(trip.otherFeeVnd)) : trip ? editCell(fieldMoney(trip.otherFeeVnd), 'otherFeeVnd', index, month) : empty('num'),
      trip ? num(pending ? 'CHỜ KIỂM' : missing ? '–' : money(result.amountVnd)) : empty('num'),
      receipt ? `<td class="pay pay-start receipt receipt-edit ${receipt.voided !== null ? 'voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="date" tabindex="${receipt.voided === null ? '0' : '-1'}">${escape(receipt.date)}</td>`
        : `<td class="pay pay-start">${open && index === month.receipts.length ? '<input class="empty-entry receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric"><span class="cell-error receipt-date-error" role="status"></span>' : ''}</td>`,
      receipt ? `<td class="pay receipt receipt-edit ${receipt.voided !== null ? 'voided-method' : ''}" data-pid="${escape(receipt.pid)}" data-field="method" tabindex="${receipt.voided === null ? '0' : '-1'}">${escape(receipt.voided !== null ? 'ĐÃ HỦY' : receipt.method)}</td>`
        : `<td class="pay">${open && index === month.receipts.length ? `<select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${method}</option>`).join('')}</select>` : ''}</td>`,
      receipt ? `<td class="pay num receipt ${receipt.voided !== null ? 'voided' : ''}" data-pid="${escape(receipt.pid)}" tabindex="${receipt.voided === null ? '0' : '-1'}">${escape(fieldMoney(receipt.amountVnd))}</td>`
        : `<td class="pay num">${open && index === month.receipts.length ? '<input class="empty-entry receipt-amount" aria-label="Số tiền trả" inputmode="numeric"><span class="cell-error receipt-amount-error" role="status"></span>' : ''}</td>`,
      empty('num'),
    ];
    const adjustmentRows = (month.adjustments ?? []).filter(item => trip && item.lineId === (trip.id ?? `${month.key}#${index}`)).map(adjustment =>
      `<tr class="adjustment"><td colspan="8">Điều chỉnh chuyến ${index + 1} · <label>Ghi chú <input class="adjustment-note" data-month="${month.key}" data-adj="${escape(adjustment.adjId)}" aria-label="Ghi chú điều chỉnh chuyến ${index + 1}" value="${escape(adjustment.reason ?? '')}" placeholder="Tùy chọn, Enter lưu"></label></td>${num(money(model.adjustmentAmount(adjustment)))}<td class="pay pay-start" colspan="4"></td></tr>`).join('');
    return `<tr>${cells.join('')}</tr>${referenceLine(receipt, open && index === month.receipts.length)}${adjustmentRows}`;
  }

  function renderMonth(month, summary, _balance) {
    const label = monthLabel(month.key);
    const open = month.key === openMonth;
    const editable = model.isMonthOpen(locks, month.key);
    const lineCount = Math.max(month.trips.length, month.receipts.length + (open ? 1 : 0));
    const lines = Array.from({ length: lineCount }, (_, index) => renderLine(month.trips[index], month.receipts[index], index, month)).join('');
    const prompt = voidPrompt?.monthKey === month.key ? `<tr class="void-prompt"><td colspan="13">Hủy phiếu ${escape(voidPrompt.pid)} — ${money(voidPrompt.totalVnd)} (${voidPrompt.monthCount} tháng) <label>Lý do <input class="void-reason" aria-label="Lý do hủy phiếu"></label> <button class="confirm-void">Hủy phiếu</button> <button class="cancel-void">Bỏ qua</button><span class="cell-error void-error" role="status"></span></td></tr>` : '';
    const traces = model.voidedLines(book, month.key).map(line => `<tr class="void-trace"><td colspan="13">${money(line.amountVnd)} · ${escape(line.date)} · ${escape(line.voidedOn)} · ${escape(line.reason)}</td></tr>`).join('');
    const status = open && notice ? `<tr class="receipt-status"><td colspan="13" role="status">${escape(notice)}</td></tr>` : '';
    const paste = editable ? `<tr class="paste-row"><td colspan="9"><label>Dán các dòng từ Sheet vào đây <textarea class="paste-input" data-month="${month.key}" rows="2" aria-label="Dán các dòng từ Sheet vào đây"></textarea></label><span class="paste-error" role="status"></span></td><td class="pay pay-start" colspan="4"></td></tr>` : '';
    const monthAdjustments = (month.adjustments ?? []).filter(item => !item.lineId).map(item => `<tr class="adjustment month-adjustment"><td colspan="8">Điều chỉnh cả tháng${item.reason ? ` · ${escape(item.reason)}` : ''}</td>${num(money(model.adjustmentAmount(item)))}<td class="pay pay-start" colspan="4"></td></tr>`).join('');
    const input = monthPrompt === month.key ? `<tr class="month-adjustment-input"><td colspan="8">Điều chỉnh cả tháng · <label>Ghi chú <input class="month-note" aria-label="Ghi chú điều chỉnh cả tháng ${label}"></label></td><td><input class="month-amount" aria-label="Số điều chỉnh cả tháng ${label}" inputmode="decimal" placeholder="+5.000.000"><span class="cell-error month-error" role="status"></span></td><td class="pay pay-start" colspan="4"></td></tr>` : '';
    return `<section id="thang-${escape(month.key)}"><table class="ledger${editable ? '' : ' locked'}" aria-label="Sổ khách tháng ${label}"><colgroup>${widths}</colgroup><tbody><tr class="month"><th colspan="13" scope="rowgroup"><span class="month-title">THÁNG ${label}<button class="month-lock" data-month="${month.key}" aria-label="${editable ? 'Khóa' : 'Mở khóa'} tháng ${label}" title="${editable ? 'Đang mở' : 'Đã khóa'}" aria-pressed="${editable}">${editable ? '🔓' : '🔒'}</button><em>Nợ các tháng trước: ${outstanding(summary.carryVnd)}</em></span></th></tr>${lines}${monthAdjustments}${input}${prompt}${traces}${status}${paste}<tr class="subtotal"><td colspan="8">Tổng tháng ${label} <button class="add-month-adjustment" data-month="${month.key}">+ Điều chỉnh cả tháng</button></td>${num(money(summary.totalChargesVnd))}<td class="pay pay-start" colspan="2">Đã thu</td>${num(outstanding(summary.receivedVnd), 'pay')}${num(outstanding(summary.endOfMonthVnd))}</tr><tr class="spacer"><td colspan="13"></td></tr></tbody></table></section>`;
  }

  function renderShell(view) {
    const scrollY = window.scrollY;
    // Một thanh đầu sổ (góp ý người dùng 23/10/2026): tên khách (bản live: chính ô tìm khách, gõ để đổi), Lịch sử, tổng còn nợ.
    const picker = live && document.querySelector('#customer-picker');
    root.innerHTML = `<div class="book-head">${live ? '<div class="picker-slot"></div>' : `<h1>Sổ khách · ${escape(view.customer)}</h1>`}<button class="history-toggle" aria-expanded="${historyOpen}" aria-controls="history-panel">Lịch sử</button>${view.sheetButton ?? ''}<div class="head-item total"><span>Tổng còn nợ (mọi tháng)</span><strong>${view.total}</strong></div></div>
    ${view.notice ?? ''}<div class="layout"><div class="ledger-book"><table class="ledger ledger-head" aria-label="Cột sổ khách"><colgroup>${widths}</colgroup><thead><tr class="columns">${labels.map((label, index) => `<th scope="col" class="${index >= (live ? 10 : 9) && index <= (live ? 12 : 11) ? 'pay ' : ''}${index === (live ? 10 : 9) ? 'pay-start' : ''}">${escape(label)}</th>`).join('')}</tr></thead></table>${view.sections}</div>
    <nav class="months-nav" aria-label="Danh sách tháng"><h2>DANH SÁCH THÁNG</h2>${view.navigation}</nav></div><aside id="history-panel" class="history-panel" aria-label="Lịch sử thay đổi" ${historyOpen ? '' : 'hidden'}><header><h2>Lịch sử</h2><button class="history-close" aria-label="Đóng lịch sử">Đóng</button></header>${view.history}</aside>`;
    const slot = root.querySelector('.picker-slot');
    if (picker && slot) {
      // Nút giữ nguyên trình nghe của api (lọc danh sách khách); chỉ dời vào thanh đầu sổ.
      slot.append(picker);
      picker.classList.add('in-head');
      picker.querySelector('label').textContent = 'Sổ khách';
      const search = picker.querySelector('#customer-search');
      if (document.activeElement !== search) search.value = view.customer;
      // Bấm vào tên là chọn hết chữ: gõ đè để tìm khách khác.
      if (!search.dataset.selectOnFocus) { search.dataset.selectOnFocus = '1'; search.addEventListener('focus', () => search.select()); }
    }
    window.scrollTo(0, scrollY);
  }

  function render() {
    const chain = model.monthChain(book);
    const remaining = model.outstandingByMonth(book);
    renderShell({ customer: book.customer,
      total: money(chain.totalOutstandingVnd),
      sections: months.map((month, index) => renderMonth(month, chain.months[index], remaining[index])).join(''),
      navigation: months.map((month, index) => `<a href="#thang-${escape(month.key)}"><span>${monthLabel(month.key)}</span><small>${outstanding(remaining[index].outstandingVnd)}</small></a>`).join(''),
      history: history.length ? `<ol>${history.map(item => `<li><time>${escape(item.time)}</time><span>Bản thử — chưa đăng nhập</span><strong>${escape(item.type)}</strong><p>${escape(item.description)}</p>${item.reason ? `<small>Ghi chú/lý do: ${escape(item.reason)}</small>` : ''}</li>`).join('')}</ol>` : '<p>Chưa có thay đổi nào</p>' });
  }

  function initLive() {
    const customerId = Number(new URLSearchParams(location.search).get('customer'));
    if (!Number.isSafeInteger(customerId) || customerId < 1) {
      root.innerHTML = '<p role="status" style="padding:16px;font-size:18px">Gõ tên khách vào ô “Tìm khách” phía trên rồi bấm vào tên để mở sổ.</p>';
      return;
    }
    let snapshot = null;
    let message = '';
    const clockParts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit' }).formatToParts(new Date());
    const liveOpenMonth = clockParts.find(part => part.type === 'year').value + '-' + clockParts.find(part => part.type === 'month').value;
    const fmt = value => value === null || value === undefined ? '–'
      : BigInt(value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const dateText = value => /^\d{4}-\d\d-\d\d$/.test(value ?? '') ? value.slice(8) + '/' + value.slice(5, 7) + '/' + value.slice(0, 4) : (value ?? '');
    const dateInput = value => /^\d\d\/\d\d\/\d{4}$/.test(value) ? value.slice(6) + '-' + value.slice(3, 5) + '-' + value.slice(0, 2) : value;
    const monthKey = value => typeof value === 'string' ? value.slice(0, 7) : '';
    // Source row from the Sheet copy: show what a reader needs, never raw objects or codes.
    // Sheet history in the ledger columns: a trip and a payment typed on the
    // same Sheet row share one line. Amounts come from the copy as digit strings; no maths here.
    // The loader resolves every serial date to one reading (dd/mm/yyyy); anything left here
    // is text typed in the Sheet ("da tt") and is shown as typed.
    // Ngày trong ô thu của Sheet: số ngày Excel ("46032.0", hệ 1900) hoặc chuỗi ISO có giờ → dd/mm/yyyy; chữ khác giữ nguyên.
    const sheetDay = value => {
      const text = String(value ?? '').trim();
      const serial = /^(\d{5})(\.0+)?$/.exec(text);
      if (serial && Number(serial[1]) >= 20000 && Number(serial[1]) <= 80000) {
        const date = new Date(Date.UTC(1899, 11, 30) + Number(serial[1]) * 86400000);
        return `${String(date.getUTCDate()).padStart(2, '0')}/${String(date.getUTCMonth() + 1).padStart(2, '0')}/${date.getUTCFullYear()}`;
      }
      const iso = /^(\d{4})-(\d\d)-(\d\d)(?:[ T]\d\d:\d\d(?::\d\d(?:\.\d+)?)?)?$/.exec(text);
      return iso ? `${iso[3]}/${iso[2]}/${iso[1]}` : text;
    };
    const rawDay = sheetDay;
    const moneyCell = value => /^-?\d+$/.test(value ?? '') ? fmt(value) : (value ?? '');
    // NHAP-SHEET-01: mọi ô chuyến (web và sổ gốc) sửa đè tại ô, kể cả tháng khóa; bấm STT để xóa hẳn.
    // Đổi ngày sang tháng khác (góp ý 23/10/2026): dòng vừa chuyển tô vàng ở tháng mới, tháng cũ giữ một dòng mờ
    // có Xem / Hoàn tác. Chỉ sống trong tab: tải lại trang là hết.
    const moved = new Map();   // `${kind}-${id}` → tháng cũ (yyyy-mm)
    const ghosts = [];         // { kind, id, month, to, container, oldIso }
    const movedTag = rowKey => moved.has(rowKey) ? `<td class="moved-tag">Vừa chuyển từ T${Number(moved.get(rowKey).slice(5))}</td>` : empty('num');
    const fieldNames = { container: 'số container', carrier: 'hãng tàu', shipper: 'shipper', event_date: 'ngày chuyến', origin: 'nơi đi',
      destination: 'nơi đến', unit_price_vnd: 'đơn giá', other_fee_vnd: 'phụ phí' };
    const infoCell = (kind, id, field, text, classes = '') =>
      `<td class="info-edit ${classes}" data-kind="${kind}" data-id="${escape(id)}" data-field="${field}" tabindex="0" role="button" aria-label="Sửa ${fieldNames[field]}">${escape(text)}</td>`;
    const deleteCell = (kind, id, text, what) =>
      `<td class="row-delete" data-kind="${kind}" data-id="${escape(id)}" tabindex="0" role="button" aria-label="Xóa hẳn ${escape(what)}" title="Bấm để xóa hẳn dòng này">${escape(text)}</td>`;
    const legacyLines = (rows, locked = false) => {
      const byRow = new Map();
      for (const row of rows) {
        const d = typeof row.display === 'object' && row.display !== null ? row.display : {};
        const line = byRow.get(d.row) ?? {};
        line[row.kind === 'receipt' ? 'receipt' : 'trip'] = { ...row, d };
        byRow.set(d.row, line);
      }
      return [...byRow.values()].map(({ trip, receipt }) => {
        const t = trip?.d ?? {}, r = receipt?.d ?? {};
        const cur = trip?.editable && trip.current ? trip.current : null;
        const stt = String(t.stt ?? '').replace(/^(\d+)\.0+$/, '$1');
        // Ô trống trong `current` nghĩa là bản gốc không đọc được thành số/ngày: hiện chữ Sheet, trừ khi đã bị xóa giá.
        const unitText = cur?.unit_price_vnd != null ? [fmt(cur.unit_price_vnd), '']
          : /^\d+$/.test(t.unit_price ?? '') || !t.unit_price && (t.flags ?? []).includes('MISSING_PRICE') ? ['chưa có giá', 'missing'] : [moneyCell(t.unit_price), ''];
        const tripCells = cur && locked
          ? `${cell(stt || '–')}${cell(cur.container || 'Phí lẻ')}${cell(cur.carrier ?? '')}${cell(cur.shipper ?? '')}${cell(cur.event_date ? dateText(cur.event_date) : rawDay(t.raw_date))}${cell(cur.origin ?? '')}${cell(cur.destination ?? '')}${num(unitText[0])}${num(cur.other_fee_vnd != null ? fmt(cur.other_fee_vnd) : moneyCell(t.fee_vnd))}${num(cur.unit_price_vnd == null && cur.counted_vnd === '0' ? '–' : fmt(cur.counted_vnd))}`
          : cur
          ? `${deleteCell('legacy', trip.id, stt || '–', `dòng sổ gốc ${cur.container || 'phí lẻ'}`)}${infoCell('legacy', trip.id, 'container', cur.container || 'Phí lẻ')}${infoCell('legacy', trip.id, 'carrier', cur.carrier ?? '')}${infoCell('legacy', trip.id, 'shipper', cur.shipper ?? '')}${infoCell('legacy', trip.id, 'event_date', cur.event_date ? dateText(cur.event_date) : rawDay(t.raw_date))}${infoCell('legacy', trip.id, 'origin', cur.origin ?? '')}${infoCell('legacy', trip.id, 'destination', cur.destination ?? '')}${infoCell('legacy', trip.id, 'unit_price_vnd', unitText[0], `num ${unitText[1]}`)}${infoCell('legacy', trip.id, 'other_fee_vnd', cur.other_fee_vnd != null ? fmt(cur.other_fee_vnd) : /^\d+$/.test(t.fee_vnd ?? '') ? '' : moneyCell(t.fee_vnd), 'num')}${num(cur.unit_price_vnd == null && cur.counted_vnd === '0' ? '–' : fmt(cur.counted_vnd))}`
          : trip
          ? `${cell(String(t.stt ?? '').replace(/^(\d+)\.0+$/, '$1'))}${cell(t.container || 'Phí lẻ')}${cell(t.carrier ?? '')}${cell(t.shipper ?? '')}${cell(t.date ? dateText(t.date) : rawDay(t.raw_date))}${cell(t.from ?? '')}${cell(t.to ?? '')}${!t.unit_price && (t.flags ?? []).includes('MISSING_PRICE') ? '<td class="num missing">chưa có giá</td>' : num(moneyCell(t.unit_price))}${num(moneyCell(t.fee_vnd))}${num(fmt(trip.source_total_vnd))}`
          : `${empty()}${empty()}${empty()}${empty()}${empty()}${empty()}${empty()}${empty('num')}${empty('num')}${empty('num')}`;
        // Hình thức thu không suy từ ghi chú (V7-MIG còn mở); ghi chú chỉ hiện khi không lặp lại cùng ngày.
        const day = sheetDay(r.raw_date);
        const noteText = r.note && r.note !== r.raw_date && sheetDay(r.note) !== day ? r.note : '';
        const sheetPay = receipt
          ? `${cell(day, 'pay pay-start')}${cell(noteText, 'pay')}${num(fmt(receipt.source_total_vnd), 'pay')}`
          : '';
        const rowKey = trip?.id != null ? `legacy-${trip.id}` : '';
        // `pay`: ba ô thu của phiếu web đặt vào hàng này khi hàng chưa có phiếu Sheet.
        return { hasReceipt: Boolean(receipt), html: pay => `<tr class="legacy${moved.has(rowKey) ? ' moved' : ''}"${rowKey ? ` data-row="${escape(rowKey)}"` : ''}>${tripCells}${sheetPay || pay || `${empty('pay pay-start')}${empty('pay')}${empty('pay num')}`}${movedTag(rowKey)}</tr>` };
      });
    };
    const eventLabels = { paste: 'Dán lô chuyến', price_edit: 'Sửa giá', adjust_trip: 'Điều chỉnh chuyến',
      adjust_month: 'Điều chỉnh cả tháng', receipt: 'Ghi thu', receipt_edit: 'Sửa thông tin phiếu', month_lock: 'Mở/khóa tháng',
      void: 'Hủy phiếu', reallocation: 'Phân bổ lại', import: 'Nhập số dư đầu', trip_review: 'Kết luận CHỜ KIỂM',
      trip_edit: 'Sửa ô chuyến', trip_delete: 'Xóa chuyến', legacy_edit: 'Sửa dòng sổ gốc', legacy_delete: 'Xóa dòng sổ gốc',
      sheet_conflict_resolved: 'Đối chiếu Sheet' };
    const reviewReasonText = { BASELINE_CODE_MATCH: 'Trùng mã với dòng sổ gốc', BASELINE_DATE_WINDOW: 'Cùng container, lệch ngày ≤3 ngày với dòng sổ gốc',
      WEB_DUPLICATE: 'Trùng chuyến đã nhập trên web', BATCH_DUPLICATE: 'Trùng trong cùng lô dán' };
    const cellText = (field, value) => value === null || value === undefined || value === '' ? '–'
      : field === 'event_date' ? dateText(value) : field.endsWith('_vnd') ? fmt(value) : String(value);
    // Một ô trước → sau, kèm chuyển tháng và số tính của dòng sổ gốc nếu đổi.
    function describeCellEvent(event) {
      const legacy = event.kind.startsWith('legacy');
      const before = (legacy ? event.before?.legacy : event.before?.trip) ?? {};
      const after = (legacy ? event.after?.legacy : event.after?.trip) ?? {};
      // Sự kiện sửa ô chuyến web chỉ mang id: lấy container từ sổ đang xem (chuyến đã xóa có ảnh đủ ở `before`).
      const known = legacy ? null : (snapshot?.trips ?? []).find(row => String(row.id) === String(before.id ?? after.id));
      const who = `${legacy ? 'Dòng sổ gốc' : 'Chuyến'} ${before.container || after.container || known?.container || '–'}`;
      if (event.kind.endsWith('_delete')) {
        const amount = legacy ? before.counted_vnd : before.amount_vnd;
        return `${who} · ${cellText('event_date', before.event_date)} · tháng ${monthLabel(monthKey(before.month ?? before.debt_month))} · ${legacy ? 'Số đang tính' : 'Thành tiền'}: ${fmt(amount)}`;
      }
      const field = after.field ?? before.field;
      const parts = [`${who} · ${{ origin: 'Nơi đi', destination: 'Nơi đến' }[field] ?? valueLabels[field] ?? 'Ô'}: ${cellText(field, before.value)} → ${cellText(field, after.value)}`];
      const from = legacy ? before.month : event.after?.moved_from_month, to = legacy ? after.month : event.after?.moved_to_month;
      if (from && to && monthKey(from) !== monthKey(to)) parts.push(`Chuyển tháng ${monthLabel(monthKey(from))} → ${monthLabel(monthKey(to))}`);
      if (legacy && before.counted_vnd !== after.counted_vnd) parts.push(`Số tính: ${fmt(before.counted_vnd)} → ${fmt(after.counted_vnd)}`);
      if (event.after?.review_reason) parts.push(`CHỜ KIỂM: ${reviewReasonText[event.after.review_reason] ?? 'Nghi trùng'}`);
      return parts.join(' · ');
    }
    const valueLabels = { amount_vnd: 'Số tiền', old_amount_vnd: 'Thành tiền trước', new_amount_vnd: 'Thành tiền sau',
      delta_vnd: 'Điều chỉnh', unit_price_vnd: 'Đơn giá', other_fee_vnd: 'Phụ phí', new_value_vnd: 'Giá trị mới',
      date: 'Ngày trả', event_date: 'Ngày chuyến', month: 'Tháng', debt_month: 'Tháng', pid: 'Phiếu',
      reference: 'Tham chiếu', method: 'Hình thức', container: 'Container', carrier: 'Hãng tàu', from: 'Nơi đi', to: 'Nơi đến',
      counterparty_name: 'Sổ bên kia', void_reason: 'Lý do hủy',
      unitPriceVnd: 'Đơn giá', otherFeeVnd: 'Phụ phí', openings: 'Số kỳ số dư đầu', legacy: 'Số dòng lịch sử' };
    function describe(value, kind) {
      if (!value || typeof value !== 'object') return 'Chưa có';
      const parts = [];
      for (const [name, item] of Object.entries(value)) {
        if (kind === 'paste' && name === 'date' && Object.hasOwn(value, 'event_date')) continue;
        if (name === 'price') parts.push(describe(item, kind));
        else if (name === 'trips' && Array.isArray(item)) parts.push(`Chuyến: ${item.map(trip => describe(trip, kind)).join('; ') || 'Chưa có'}`);
        else if (name === 'allocations' && Array.isArray(item)) parts.push(`Phân bổ: ${item.map(line =>
          `tháng ${monthLabel(monthKey(line.month))} · ${line.kind === 'advance' ? 'Ứng trước' : 'Trừ nợ'} · ${fmt(line.amount_vnd)}`).join('; ') || 'Không có'}`);
        else if (Object.hasOwn(valueLabels, name) && (item === null || typeof item !== 'object')) {
          const text = name.endsWith('_vnd') || name.endsWith('Vnd') ? fmt(item)
            : ['date', 'event_date'].includes(name) ? dateText(item)
              : ['month', 'debt_month'].includes(name) ? monthLabel(monthKey(item)) : item;
          const label = name === 'new_value_vnd'
            ? value.field === 'unit_price_vnd' ? 'Đơn giá' : value.field === 'other_fee_vnd' ? 'Phụ phí' : valueLabels[name]
            : name === 'date' && kind === 'paste' ? 'Ngày chuyến' : valueLabels[name];
          parts.push(`${label}: ${text ?? '–'}`);
        }
      }
      return parts.join(' · ') || 'Chưa có';
    }
    function describeEvent(event) {
      if (event.kind === 'sheet_conflict_resolved') {
        const before = event.before ?? {}, after = event.after ?? {};
        const label = { carrier: 'Hãng tàu', shipper: 'Shipper', origin: 'Điểm đi', destination: 'Điểm đến' }[after.field] ?? 'Ô';
        return `${label}: ${cellText(after.field, before.value)} → ${cellText(after.field, after.target_value)} · ${after.decision === 'use_sheet' ? 'Lấy Sheet' : 'Giữ web'}`;
      }
      if (event.kind === 'month_lock') return `${event.after?.locked ? 'Khóa' : 'Mở'} tháng ${monthLabel(monthKey(event.after?.month))}`;
      if (event.kind === 'trip_review') return `Chuyến ${event.after?.container || '–'}: ${event.after?.status === 'confirmed'
        ? 'tính vào sổ' : 'loại, không tính'}`;
      if (['trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete'].includes(event.kind)) return describeCellEvent(event);
      if (event.kind !== 'adjust_trip') return `${describe(event.before, event.kind)} → ${describe(event.after, event.kind)}`;
      const before = event.before ?? {}, after = event.after ?? {};
      const field = after.field ?? before.field;
      const fieldLabel = field === 'unit_price_vnd' ? 'Đơn giá' : field === 'other_fee_vnd' ? 'Phụ phí' : null;
      const parts = fieldLabel ? [`${fieldLabel}: ${fmt(before.new_value_vnd)} → ${fmt(after.new_value_vnd)}`] : [];
      parts.push(`Thành tiền: ${fmt(before.amount_vnd ?? after.old_amount_vnd)} → ${fmt(after.new_amount_vnd)}`);
      const delta = fmt(after.delta_vnd);
      parts.push(`Điều chỉnh: ${/^[0-9]/.test(delta) ? '+' : ''}${delta}`);
      return parts.join(' · ');
    }
    function eventTime(value) {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return 'Chưa rõ thời điểm';
      const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh',
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(date);
      const part = name => parts.find(item => item.type === name).value;
      return `${part('day')}/${part('month')}/${part('year')} ${part('hour')}:${part('minute')}`;
    }
    // ---- NHAP-SHEET-01 (1): bảng nhập kiểu Sheet thay ô "Dán các dòng từ Sheet". Nháp chỉ sống trong tab;
    // Lưu gửi một lệnh dán lô (paste_trips), server tự xếp từng chuyến vào tháng của ngày chuyến. ----
    const DRAFT_FIELDS = model.DRAFT_FIELDS;
    const draftLabels = { container: 'Số container', carrier: 'Hãng tàu', shipper: 'Shipper', date: 'Ngày chuyến', from: 'Nơi đi', to: 'Nơi đến', price: 'Đơn giá', fee: 'Phụ phí' };
    // Nháp chuyến theo từng tháng đang mở (mỗi tháng mở có bảng nhập riêng); lưu xong chuyến vào tháng của ngày chuyến.
    const draftsBy = new Map();
    const draftsOf = key => draftsBy.get(key) ?? [];
    const setDrafts = (key, rows) => { if (rows.length) draftsBy.set(key, rows); else draftsBy.delete(key); };
    let draftNote = { key: '', text: '' };
    const draftEmpty = row => DRAFT_FIELDS.every(name => !String(row[name] ?? '').trim());
    function draftGrid(key) {
      const drafts = draftsOf(key);
      const checked = drafts.map(row => model.checkDraft(row, todayIso()));
      const bad = checked.reduce((sum, item) => sum + Object.keys(item.errors).length, 0);
      const rows = [...drafts, model.blankDraft()].map((row, index) => {
        const result = index < drafts.length ? checked[index] : null;
        const cells = DRAFT_FIELDS.map(name => {
          const error = result?.errors[name];
          const missing = name === 'price' && result?.missing;
          return `<td class="${error ? 'bad' : ''}${missing ? ' missing' : ''}"${error ? ` title="${escape(error)}"` : ''}><input class="draft-input${['price', 'fee'].includes(name) ? ' money-input' : ''}" data-month="${escape(key)}" data-draft="${index}" data-field="${name}" value="${escape(row[name])}" aria-label="${draftLabels[name]} hàng nhập ${index + 1}"${error ? ` aria-invalid="true" aria-description="${escape(error)}"` : ''}${missing ? ' placeholder="chưa có giá"' : ''} autocomplete="off"></td>`;
        }).join('');
        const total = result ? (result.amountVnd === null ? '–' : model.formatVnd(result.amountVnd)) : '';
        return `<tr class="draft-row${result ? ' draft' : ''}"><td class="muted">${result ? 'nháp' : ''}</td>${cells}<td class="num${result?.warn ? ' warn' : ''}">${escape(total)}${result?.warn ? `<small>${escape(result.warn)}</small>` : ''}</td><td class="off pay-start"></td><td class="off"></td><td class="off"></td><td class="off"></td></tr>`;
      }).join('');
      const note = draftNote.key === key ? draftNote.text : '';
      return `<tr class="draft-caption"><td colspan="14">Nhập chuyến · dán từ Sheet vào ô bất kỳ của hàng trống, hoặc gõ tay (Tab sang ô kế, Enter xuống hàng)</td></tr>${rows}
        <tr class="draft-bar"><td colspan="14"><div><strong>${drafts.length} chuyến nháp</strong>${bad ? `<span class="cell-error">· ${bad} ô cần sửa</span>` : ''}<button type="button" class="draft-save" data-month="${escape(key)}" ${drafts.length && !bad ? '' : 'disabled'}>Lưu ${drafts.length} chuyến</button><button type="button" class="draft-discard" data-month="${escape(key)}" ${drafts.length ? '' : 'disabled'}>Bỏ nháp</button>${note ? `<span class="draft-note" role="status">${escape(note)}</span>` : ''}</div></td></tr>`;
    }
    // Vẽ lại sổ từ bản đang có (không tải lại), giữ con trỏ ở ô nháp/nút đang đứng.
    // Cờ rendering: thay DOM làm ô đang đứng mất focus; không coi đó là người dùng rời ô (tránh vẽ lại vòng tròn).
    let rendering = false;
    function redraw(focus) {
      if (!snapshot) return;
      rendering = true;
      // Ô ghi thu đang gõ dở (hàng nhập phiếu của từng tháng mở): vẽ lại bảng nháp không được làm mất.
      const typed = [...root.querySelectorAll('.receipt-date:not(.saved-receipt-input)')].flatMap(date => {
        const row = date.closest('tr'), section = row.closest('section')?.id;
        return [...row.querySelectorAll('.receipt-date, .receipt-method, .receipt-amount, .receipt-reference')]
          .map(box => ({ section, name: box.className.match(/receipt-(date|method|amount|reference)/)[0], value: box.value }));
      });
      try {
        renderSnapshot(snapshot);
        for (const box of typed) {
          const target = box.section && root.querySelector(`#${CSS.escape(box.section)} .${box.name}:not(.saved-receipt-input)`);
          if (target) target.value = box.value;
        }
        const offset = typed.find(box => box.name === 'receipt-method' && box.value === 'CẤN TRỪ');
        const entryRow = offset && root.querySelector(`#${CSS.escape(offset.section)} .receipt-date:not(.saved-receipt-input)`)?.closest('tr');
        if (entryRow) { entryRow.insertAdjacentHTML('afterend', sourceRowHtml); offsetState.row = entryRow; renderSourceCell(); }
        const input = focus && root.querySelector(`.draft-input[data-month="${focus.month}"][data-draft="${focus.row}"][data-field="${focus.field}"]`);
        if (input) { input.focus(); const end = focus.caret ?? input.value.length; input.setSelectionRange(end, end); }
      } finally { rendering = false; }
    }
    // Mọi số tiền lấy nguyên từ GET; trang không cộng trừ tiền (trừ dòng Tổng tháng, tính trong model).
    function renderSnapshot(data) {
      snapshot = data;
      const active = data.status === 'active';
      const sheetRows = data.sheet_sync?.items ?? [];
      // Tháng hiện tại và cờ khóa theo server (giờ VN); đồng hồ máy chỉ dùng khi server cũ chưa trả.
      const openKey = monthKey(data.today_month) || liveOpenMonth;
      const lockFlags = new Map((data.month_locks ?? []).map(row => [monthKey(row.month), row.locked]));
      const groups = [...(data.months ?? [])];
      // Tháng hiện tại chưa có dữ liệu vẫn cần khối để ghi thu (trừ nợ cũ trước) và dán chuyến.
      if (active && !groups.some(item => monthKey(item.month) === openKey)) {
        groups.push({ month: `${openKey}-01`, placeholder: true });
        groups.sort((a, b) => monthKey(a.month).localeCompare(monthKey(b.month)));
      }
      // Khoản "cấn trừ đi" của sổ nguồn nằm ở tháng của ngày trả, trong khối TIỀN KHÁCH TRẢ (số âm).
      const outgoingByMonth = new Map();
      for (const item of data.outgoing_offsets ?? []) {
        const key = monthKey(item.date);
        if (!outgoingByMonth.has(key)) outgoingByMonth.set(key, []);
        outgoingByMonth.get(key).push({ pid: item.pid, date: item.date, method: 'CẤN TRỪ', offset_pair_id: item.offset_pair_id,
          counterparty_customer_id: item.counterparty_customer_id, counterparty_name: item.counterparty_name, outgoing: true,
          void_reason: item.void_reason, voided_by_event: item.voided_by_event, line: { amount_vnd: item.amount_vnd, kind: 'offset' } });
        if (!groups.some(group => monthKey(group.month) === key)) groups.push({ month: `${key}-01`, placeholder: true });
      }
      // Đổi ngày sang tháng khác: chuyến/dòng sổ gốc tự sang bảng tháng đó, chưa có bảng thì bảng tự hiện.
      for (const row of [...(data.trips ?? []), ...(data.legacy_rows ?? []), ...ghosts,
        ...sheetRows.filter(item => item.sync_state === 'NEW' || !item.existing_id).map(item => ({ month: item.event_date }))]) {
        const key = monthKey(row.month);
        if (key && !groups.some(group => monthKey(group.month) === key)) groups.push({ month: `${key}-01`, placeholder: true });
      }
      groups.sort((a, b) => monthKey(a.month).localeCompare(monthKey(b.month)));
      const offsetAttrs = receipt => receipt.offset_pair_id == null ? ''
        : ` data-pair="${escape(receipt.offset_pair_id)}" data-other="${escape(receipt.counterparty_customer_id)}" data-other-name="${escape(receipt.counterparty_name)}"`;
      const offsetLink = receipt => receipt.offset_pair_id == null || receipt.voided_by_event != null ? ''
        : `<a class="offset-link" href="/so-khach-v7-live.html?customer=${encodeURIComponent(receipt.counterparty_customer_id)}">${receipt.outgoing ? 'sang' : 'từ'} ${escape(receipt.counterparty_name)}</a>`;
      const sourceFigures = new Map((data.source_exceptions ?? []).map(item => [monthKey(item.month), item]));
      const historical = new Map();
      for (const row of data.legacy_rows ?? []) {
        const key = monthKey(row.month);
        if (!historical.has(key)) historical.set(key, []);
        historical.get(key).push(row);
      }
      const section = item => {
        const key = monthKey(item.month);
        const trips = (data.trips ?? []).filter(row => monthKey(row.month) === key);
        const sheetPending = sheetRows.filter(row => monthKey(row.event_date) === key
          && (row.sync_state === 'NEW' || !row.existing_id));
        const received = (data.receipts ?? []).flatMap(row => (row.allocations ?? [])
          .filter(line => monthKey(line.month) === key && (row.voided_by_event != null
            ? line.superseded_by_event === row.voided_by_event : line.superseded_by_event === null))
          .map(line => ({ ...row, line })));
        const receipts = [...received, ...(outgoingByMonth.get(key) ?? [])];
        const opening = (data.opening ?? []).filter(row => monthKey(row.month) === key);
        const adjustments = (data.adjustments ?? []).filter(row => monthKey(row.month) === key);
        const locked = lockFlags.has(key) ? lockFlags.get(key) : key !== openKey;
        // Góp ý 23/10/2026: phiếu thu web nằm ở hàng kế tiếp sau phiếu thu cuối cùng của tháng (như trên Sheet), không dồn xuống cuối.
        // Hàng của tháng theo thứ tự hiển thị: dòng Sheet, rồi chuyến web; hết hàng thì thêm hàng chỉ có cột thu.
        const legacy = legacyLines(historical.get(key) ?? [], locked);
        // Phiếu thu vẫn nhập trong tháng khóa; bảng nhập chuyến chỉ có khi mở khóa.
        const entryHere = active;
        const draftHere = active && !locked;
        const firstFree = legacy.map(line => line.hasReceipt).lastIndexOf(true) + 1;
        const rowCount = Math.max(legacy.length + trips.length, firstFree + receipts.length + (entryHere ? 1 : 0));
        // STT chuyến web nối tiếp các dòng chuyến từ Sheet của tháng (dòng Sheet vẽ trước, như thứ tự trên Sheet).
        const sttBase = new Set((historical.get(key) ?? []).filter(row => row.kind !== 'receipt').map(row => row.display?.row)).size;
        const referenceInline = receipt => {
          const voided = receipt.voided_by_event != null;
          return `<small class="receipt receipt-edit receipt-ref${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="reference" tabindex="${voided ? '-1' : '0'}" role="button" aria-label="Sửa tham chiếu ${escape(receipt.pid)}">Tham chiếu: ${escape(receipt.reference || '–')}</small>`;
        };
        const payCells = (receipt, entry) => {
          const voided = receipt?.voided_by_event != null;
          const dateCell = receipt ? `<td class="pay pay-start receipt receipt-edit${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="date"${offsetAttrs(receipt)} tabindex="${voided ? '-1' : '0'}">${escape(dateText(receipt.date))}</td>` : `<td class="pay pay-start">${entry ? '<input class="empty-entry receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric"><span class="cell-error receipt-date-error" role="status"></span>' : ''}</td>`;
          const methodCell = receipt?.offset_pair_id != null ? `<td class="pay offset-method${voided ? ' voided-method' : ''}">${escape(voided ? 'ĐÃ HỦY' : receipt.line.kind === 'advance' ? 'ỨNG TRƯỚC' : 'CẤN TRỪ')}${offsetLink(receipt)}</td>` : receipt ? `<td class="pay receipt receipt-edit${voided ? ' voided-method' : ''}" data-pid="${escape(receipt.pid)}" data-field="method" tabindex="${voided ? '-1' : '0'}">${escape(voided ? 'ĐÃ HỦY' : receipt.line.kind === 'advance' ? 'ỨNG TRƯỚC' : receipt.method)}</td>` : `<td class="pay">${entry ? `<select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${method}</option>`).join('')}</select>` : ''}</td>`;
          const amountCell = receipt ? `<td class="pay num receipt${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}"${offsetAttrs(receipt)} tabindex="${voided ? '-1' : '0'}">${fmt(receipt.line.amount_vnd)}${receipt.outgoing ? '' : referenceInline(receipt)}</td>` : `<td class="pay num">${entry ? '<input class="empty-entry receipt-amount" aria-label="Số tiền trả" inputmode="numeric"><span class="cell-error receipt-amount-error" role="status"></span><input class="receipt-reference" aria-label="Tham chiếu" maxlength="500" placeholder="Tham chiếu (tùy chọn)">' : ''}</td>`;
          return dateCell + methodCell + amountCell;
        };
        const noPay = '<td class="pay pay-start"></td><td class="pay"></td><td class="pay num"></td>';
        const webRow = (trip, index, pay) => {
          const pending = trip?.status === 'pending_review';
          const info = !locked && trip?.info_editable === true;
          const infoCells = info
            ? ['container', 'carrier', 'shipper', 'event_date', 'origin', 'destination'].map(field =>
              infoCell('trip', trip.id, field, field === 'event_date' ? dateText(trip.event_date) : trip[field] ?? '')).join('')
            : `${cell(trip?.container ?? '')}${cell(trip?.carrier ?? '')}${cell(trip?.shipper ?? '')}${cell(dateText(trip?.event_date))}${cell(trip?.origin ?? '')}${cell(trip?.destination ?? '')}`;
          const rowKey = trip ? `trip-${trip.id}` : '';
          return `<tr${rowKey ? ` data-row="${rowKey}"` : ''}${moved.has(rowKey) ? ' class="moved"' : ''}>${info ? deleteCell('trip', trip.id, trip.is_fee_only ? '–' : sttBase + index + 1, `chuyến ${trip.container || 'phí lẻ'}`) : trip && !trip.is_fee_only ? cell(sttBase + index + 1) : empty()}
            ${infoCells}
            ${pending || trip?.status === 'rejected' || locked ? num(trip?.is_missing_price ? trip.note === 'Chuyến đồng bộ' ? '' : 'chưa có giá' : fmt(trip?.unit_price_vnd)) : trip ? `<td class="num editable ${trip.is_missing_price ? 'missing' : ''}" data-trip="${trip.id}" data-field="unit_price_vnd" tabindex="0" role="button" aria-label="Sửa đơn giá chuyến ${index + 1}">${trip.is_missing_price ? trip.note === 'Chuyến đồng bộ' ? '' : 'chưa có giá' : fmt(trip.unit_price_vnd)}</td>` : empty('num')}
            ${pending || trip?.status === 'rejected' || locked ? num(fmt(trip?.other_fee_vnd)) : trip ? `<td class="num editable" data-trip="${trip.id}" data-field="other_fee_vnd" tabindex="0" role="button" aria-label="Sửa phụ phí chuyến ${index + 1}">${fmt(trip.other_fee_vnd)}</td>` : empty('num')}
            ${!trip ? empty('num') : pending && locked ? num('CHỜ KIỂM') : pending ? `<td class="num review-cell"><button type="button" class="review-open" data-trip="${trip.id}" aria-expanded="false" aria-label="Kết luận chuyến ${escape(trip.container)} đang CHỜ KIỂM">CHỜ KIỂM</button></td>` : trip.status === 'rejected' ? '<td class="num trip-rejected">ĐÃ LOẠI</td>' : num(fmt(trip.amount_vnd))}
            ${pay}
            ${movedTag(rowKey)}</tr>`;
        };
        const lines = Array.from({ length: rowCount }, (_, position) => {
          const slot = position - firstFree;
          const receipt = slot >= 0 ? receipts[slot] : undefined;
          const pay = receipt || (entryHere && slot === receipts.length) ? payCells(receipt, !receipt) : null;
          if (position < legacy.length) return legacy[position].html(pay);
          return webRow(trips[position - legacy.length], position - legacy.length, pay ?? noPay);
        }).join('');
        const sheetLines = sheetPending.map(row => `<tr class="${row.sync_state === 'NEW' ? 'sheet-new' : 'sheet-conflict'}">
          ${empty()}<td>${escape(row.container)}<small>${row.sync_state === 'NEW' ? 'CHỜ DUYỆT' : `KHÁC: ${conflictFields(row)}`}</small></td>${cell(row.carrier)}${cell(row.shipper)}${cell(dateText(row.event_date))}${cell(row.origin)}${cell(row.destination)}
          ${empty('num')}${empty('num')}${num('–')}${empty('pay pay-start')}${empty('pay')}${empty('pay num')}${empty('num')}
          </tr>`).join('');
        // Góp ý 23/10/2026: không hiện dòng số dư đầu, dòng "Theo sổ gốc" và dòng chênh do sửa dòng cũ.
        // Các dòng đó vẫn nằm trong số tiền: dòng Tổng tháng tính như Sheet (model.sheetMonthTotals), chênh ghi ở Lịch sử.
        const adjustmentRows = adjustments.filter(row => row.legacy_row_id == null).map(row => `<tr class="adjustment"><td colspan="9">Điều chỉnh ${row.trip_id ? 'chuyến' : 'cả tháng'}${row.note ? ` · ${escape(row.note)}` : ''}</td>${num(fmt(row.amount_vnd))}<td class="pay pay-start" colspan="4"></td></tr>`).join('');
        const voidRows = receipts.filter(row => row.voided_by_event != null).map(row =>
          `<tr class="void-trace"><td colspan="14">${[fmt(row.line.amount_vnd), escape(dateText(row.date)), row.outgoing ? '' : escape(dateText(row.voided_on)), escape(row.void_reason)].filter(Boolean).join(' · ')}</td></tr>`).join('');
        const history = historical.get(key) ?? [];
        let totals = { chargesVnd: item.charges_vnd ?? '0', receivedVnd: item.received_vnd ?? '0' };
        try {
          totals = model.sheetMonthTotals({ ...totals, openingVnds: opening.map(row => row.amount_vnd),
            sourceChargeVnd: history.length ? sourceFigures.get(key)?.source_charge_vnd ?? null : null });
        } catch { /* số lạ từ server: giữ số server */ }
        const ghostRows = ghosts.map((ghost, index) => ghost.month !== key ? '' : `<tr class="ghost"><td colspan="14">↪ ${escape(ghost.container || 'Chuyến')} (ngày cũ ${escape(dateText(ghost.oldIso))}) đã chuyển sang tháng ${monthLabel(ghost.to)}<button type="button" class="ghost-go" data-row="${escape(`${ghost.kind}-${ghost.id}`)}">Xem</button><button type="button" class="ghost-undo" data-ghost="${index}">Hoàn tác</button></td></tr>`).join('');
        return `<section id="thang-${escape(key)}"><table class="ledger${locked ? ' locked' : ''}" aria-label="Sổ khách tháng ${monthLabel(key)}"><colgroup>${widths}</colgroup><tbody>
          <tr class="month"><th colspan="14" scope="rowgroup"><span class="month-title">THÁNG ${monthLabel(key)}<button class="month-lock" data-month="${escape(item.month)}" aria-label="${locked ? 'Mở khóa' : 'Khóa'} tháng ${monthLabel(key)}" title="${locked ? 'Đã khóa' : 'Đang mở'}" aria-pressed="${!locked}" ${active ? '' : 'disabled'}>${locked ? '🔒' : '🔓'}</button><em>Nợ các tháng trước: ${fmt(item.prior_months_vnd)}</em></span></th></tr>
          ${lines}${sheetLines}${adjustmentRows}${voidRows}${ghostRows}${draftHere ? draftGrid(key) : ''}
          <tr class="subtotal"><td colspan="9">Tổng tháng ${monthLabel(key)} <button class="add-month-adjustment" data-month="${escape(item.month)}" ${active && !locked ? '' : 'disabled'}>+ Điều chỉnh cả tháng</button></td>${num(fmt(totals.chargesVnd))}<td class="pay pay-start" colspan="2">Đã thu</td>${num(fmt(totals.receivedVnd), 'pay')}${num(fmt(item.end_of_month_vnd))}</tr><tr class="spacer"><td colspan="14"></td></tr></tbody></table></section>`;
      };
      const sheetNotice = data.sheet_sync?.unavailable ? 'Không đọc được chuyến mới từ Sheet.' : '';
      const noticeHtml = `<p class="live-notice" role="status" style="padding:8px;background:#fff3d6" ${(message && message !== 'Đã lưu.') || !active || sheetNotice ? '' : 'hidden'}>${escape(message || sheetNotice || (active ? '' : 'Khách chưa có số dư đầu hiệu lực. Chưa thể ghi.'))}</p><button class="retry-command" ${api.hasPending() ? '' : 'hidden'}>Thử lại thao tác vừa gửi</button>`;
      const newCount = data.sheet_sync?.new_count ?? 0;
      renderShell({ customer: live.customerName(customerId) ?? `#${customerId}`, total: fmt(data.total_outstanding_vnd), notice: noticeHtml,
        sheetButton: newCount ? `<button class="sheet-approve" ${active ? '' : 'disabled'}>Duyệt ${newCount} chuyến mới</button>` : '',
        sections: groups.map(section).join(''), navigation: groups.map(item => `<a href="#thang-${escape(monthKey(item.month))}"><span>${monthLabel(monthKey(item.month))}</span><small>${fmt(item.outstanding_vnd)}</small></a>`).join(''),
        history: (data.events ?? []).length ? `<ol>${data.events.map(event => `<li><time>${escape(eventTime(event.at))}</time><span>${escape(event.actor ?? 'Chưa rõ người thao tác')}</span><strong>${escape(Object.hasOwn(eventLabels, event.kind) ? eventLabels[event.kind] : 'Thao tác khác')}</strong><p>${escape(describeEvent(event))}</p><small>Ghi chú/lý do: ${escape(event.after?.note || event.after?.void_reason || event.after?.review_reason || event.after?.trips?.map(trip => trip.note).filter(Boolean).join('; ') || event.before?.note || '–')}</small></li>`).join('')}</ol>` : '<p>Chưa có thay đổi nào</p>' });
      for (const row of sheetRows.filter(item => item.sync_state === 'CONFLICT' && item.existing_id)) {
        const target = root.querySelector(`[data-row="${row.existing_kind}-${row.existing_id}"]`);
        if (target) {
          target.classList.add('sheet-conflict');
          target.title = 'Chuyến Sheet có dữ liệu khác. Giữ nguyên sổ hiện có.';
          const label = document.createElement('small'); label.textContent = `KHÁC: ${conflictFields(row)}`;
          target.children[1]?.append(label);
          const button = document.createElement('button'); button.type = 'button'; button.className = 'sheet-diff';
          button.dataset.index = String(sheetRows.indexOf(row)); button.textContent = 'Xem';
          button.setAttribute('aria-expanded', 'false');
          target.children[1]?.append(button);
        }
      }
    }
    function showNotice(value) {
      message = value;
      const status = root.querySelector('.live-notice');
      // "Đã lưu." trơn không hiện băng vàng: kết quả đã thấy ngay trên dòng (góp ý 23/10/2026).
      if (status) { status.textContent = value; status.hidden = !value || value === 'Đã lưu.'; }
      const retry = root.querySelector('.retry-command');
      if (retry) retry.hidden = !api.hasPending();
    }
    const api = live.create({ customerId, onSnapshot: renderSnapshot, onNotice: showNotice });
    const openSheetDetail = button => {
      const trip = snapshot.sheet_sync.items[Number(button.dataset.index)];
      const tableRow = button.closest('tr');
      if (tableRow.nextElementSibling?.classList.contains('sheet-detail')) {
        tableRow.nextElementSibling.remove();
        button.textContent = 'Xem';
        button.setAttribute('aria-expanded', 'false');
        return;
      }
      const sheetFields = ['carrier', 'shipper', 'event_date', 'origin', 'destination', 'booking'].map(field => {
        const value = field === 'event_date' ? dateText(trip.event_date) : trip[field] || '–';
        const changed = resolvableSheetFields.has(field) && (trip.changed_fields || []).includes(field);
        const webValue = field === 'event_date' ? dateText(trip.existing_values?.[field]) : trip.existing_values?.[field] || '–';
        // BOOKING-EDIT-01: booking đã ghi giữ nguyên, chỉ ghi nhận đã xem.
        const actions = !changed ? '' : field === 'booking'
          ? `<div class="sheet-choice-actions"><button type="button" data-sheet-decision="keep_web" data-sheet-field="booking">Giữ booking đã ghi</button></div>`
          : `<div class="sheet-choice-actions"><button type="button" data-sheet-decision="keep_web" data-sheet-field="${escape(field)}">Giữ web</button><button type="button" data-sheet-decision="use_sheet" data-sheet-field="${escape(field)}">Lấy Sheet</button></div>`;
        return `<div class="sheet-detail-field${changed ? ' sheet-value-conflict' : ''}"><span class="sheet-detail-label">${escape(sheetFieldLabel(field))}</span>${changed ? `<span class="sheet-detail-web">Web: ${escape(webValue)}</span><strong>Sheet: ${escape(value)}</strong>${actions}` : `<strong>${escape(value)}</strong>`}</div>`;
      }).join('');
      const detailRow = `<tr class="sheet-detail"><td colspan="14"><div class="sheet-detail-content"><div class="sheet-detail-heading"><strong>↳ Dữ liệu từ Sheet</strong><span>${escape(trip.container)}</span></div><div class="sheet-detail-fields">${sheetFields}</div></div></td></tr>`;
      tableRow.insertAdjacentHTML('afterend', detailRow);
      button.textContent = 'Đóng';
      button.setAttribute('aria-expanded', 'true');
    };
    root.addEventListener('click', event => {
      const button = event.target.closest('.sheet-diff');
      if (!button) return;
      event.stopImmediatePropagation();
      openSheetDetail(button);
    });
    root.addEventListener('click', async event => {
      const action = event.target.closest('[data-sheet-decision]');
      if (!action) return;
      const detail = action.closest('.sheet-detail');
      const row = detail?.previousElementSibling;
      const index = Number(row?.querySelector('.sheet-diff')?.dataset.index);
      const trip = snapshot.sheet_sync.items[index];
      if (!trip || action.disabled) return;
      const rowKey = `${trip.existing_kind}-${trip.existing_id}`;
      if (action.dataset.sheetField === 'event_date' && action.dataset.sheetDecision === 'use_sheet') {
        // Lấy ngày Sheet = sửa ô ngày như gõ tay: hỏi khi sang tháng khác, tháng khóa thì không sửa được.
        const dateCell = root.querySelector(`td.info-edit[data-kind="${CSS.escape(trip.existing_kind)}"][data-id="${CSS.escape(String(trip.existing_id))}"][data-field="event_date"]`);
        if (!dateCell) { showNotice('Tháng đang khóa. Mở khóa tháng rồi lấy ngày từ Sheet.'); return; }
        detail.remove();
        const diffButton = row.querySelector('.sheet-diff');
        if (diffButton) { diffButton.textContent = 'Xem'; diffButton.setAttribute('aria-expanded', 'false'); }
        openInfoEdit(dateCell);
        const input = dateCell.querySelector('input');
        input.value = dateText(trip.event_date);
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        return;
      }
      action.disabled = true;
      try {
        const response = await fetch('/api/v7/sheet/resolve', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ customer_id: customerId, expected_version: snapshot.version,
            snapshot_sha256: snapshot.sheet_sync.snapshot_sha256, source_row: trip.source_row,
            target_kind: trip.existing_kind, target_id: trip.existing_id, field: action.dataset.sheetField,
            decision: action.dataset.sheetDecision, idempotency_key: crypto.randomUUID() }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.message || 'Không xử lý được dòng đối chiếu.');
        await api.read();
        const nextButton = root.querySelector(`[data-row="${CSS.escape(rowKey)}"] .sheet-diff`);
        if (nextButton) openSheetDetail(nextButton);
        showNotice('Đã xử lý đối chiếu.');
      } catch (error) { showNotice(error.message); action.disabled = false; }
    });
    let sheetApproval = null;
    root.addEventListener('click', async event => {
      const button = event.target.closest('.sheet-approve');
      if (!button || button.disabled) return;
      if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
      sheetApproval ??= { customer_id: customerId, expected_version: snapshot.version,
        snapshot_sha256: snapshot.sheet_sync.snapshot_sha256, idempotency_key: crypto.randomUUID() };
      button.disabled = true;
      try {
        const response = await fetch('/api/v7/sheet/approve', { method: 'POST',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sheetApproval) });
        const result = await response.json();
        sheetApproval = null;
        try { await api.read(); } catch { showNotice('Đã xử lý lô duyệt; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
        showNotice(response.ok
          ? result.complete === false ? `Đã duyệt ${result.approved} chuyến; còn ${result.remaining} chuyến chưa duyệt (${result.error}).`
            : `Đã duyệt ${result.approved} chuyến${result.review_count ? `; ${result.review_count} chuyến nghi trùng cần kiểm` : ''}. Chuyến thiếu giá vẫn chưa tính tiền.`
          : result.message || 'Không duyệt được chuyến mới.');
      } catch { showNotice('Chưa rõ kết quả duyệt. Tải lại sổ để kiểm tra trước khi thử lại.'); }
      button.disabled = false;
    });
    const moneyText = (value, nullable = false) => {
      if (nullable && !value.trim()) return null;
      let number;
      try { number = model.parseVnd(value); } catch { throw Error('Số tiền không hợp lệ.'); }
      if (number > 9223372036854775807n) throw Error('Số tiền không hợp lệ.');
      return number.toString();
    };
    async function submit(action, fields) {
      try { return await api.submit(action, fields); }
      catch (error) { showNotice(error.message); }
    }
    // ---- Cấn trừ hai sổ (CT-2SO): server giữ số dư và chặn; trang chỉ chọn sổ, hiện số trước → sau và gửi lệnh ----
    const OUTSIDE = model.OFFSET_OUTSIDE;
    const offsetState = { sources: [], selected: null, open: false, query: '', error: '', row: null };
    const sourceRowHtml = '<tr class="offset-source-row"><td colspan="10"></td><td class="pay pay-start offset-source-cell" colspan="3"></td><td></td></tr>';
    const todayIso = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    const ownName = () => live.customerName(customerId) ?? `#${customerId}`;
    const validDate = value => /^\d{4}-\d\d-\d\d$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
    async function refreshSources() {
      try {
        offsetState.sources = model.parseOffsetSources(await api.loadOffsetSources()).sort((a, b) => a.label.localeCompare(b.label, 'vi'));
        offsetState.error = '';
      } catch { offsetState.sources = []; offsetState.error = 'Không đọc được danh sách sổ đang dư tiền.'; }
      if (offsetState.selected && offsetState.selected !== OUTSIDE) {
        offsetState.selected = offsetState.sources.find(item => item.customerId === offsetState.selected.customerId) ?? null;
        if (!offsetState.selected) offsetState.error = 'Sổ đã chọn không còn dư tiền, chọn lại.';
      }
    }
    function renderOptions() {
      const holder = root.querySelector('.offset-options');
      if (!holder) return;
      const found = model.filterOffsetSources(offsetState.sources, offsetState.query);
      holder.innerHTML = found.map(item => `<button type="button" role="option" class="offset-option" data-source="${escape(item.customerId)}"><span>${escape(item.label)}</span><strong>${model.formatVnd(item.outstandingVnd)}</strong></button>`).join('')
        + (found.length ? '' : `<p class="offset-none">${offsetState.sources.length ? 'Không tìm thấy sổ phù hợp' : 'Không có sổ nào đang dư tiền'}</p>`);
    }
    function renderSourceCell() {
      const holder = root.querySelector('.offset-source-cell');
      if (!holder) return;
      const chosen = offsetState.selected;
      const text = chosen === OUTSIDE ? 'Ngoài sổ · chỉ trừ sổ này' : chosen ? `${chosen.label} · ${model.formatVnd(chosen.outstandingVnd)}` : 'Chọn sổ đang dư tiền…';
      holder.innerHTML = `<div class="offset-caption">Lấy từ sổ</div><button type="button" class="offset-source-select" aria-haspopup="listbox" aria-expanded="${offsetState.open}">${escape(text)}</button><span class="cell-error offset-source-error" role="alert">${escape(offsetState.error)}</span>${offsetState.open
        ? `<div class="offset-picker" role="listbox" aria-label="Chọn sổ lấy tiền"><input class="offset-search" aria-label="Lọc theo tên khách hoặc mặt hàng" placeholder="Gõ tên khách hoặc mặt hàng để lọc…" value="${escape(offsetState.query)}" autocomplete="off"><div class="offset-options"></div><button type="button" role="option" class="offset-option offset-outside" data-source="OUTSIDE">Ngoài sổ (khoản phải trả, USD…) · chỉ trừ sổ này</button></div>` : ''}`;
      renderOptions();
    }
    async function showSourceRow(entryRow) {
      if (entryRow.nextElementSibling?.classList.contains('offset-source-row')) return;
      // Một ô chọn sổ nguồn tại một lúc: tháng khác đang chọn CẤN TRỪ thì trả về THU TIỀN.
      root.querySelectorAll('.offset-source-row').forEach(row => {
        const method = row.previousElementSibling?.querySelector('.receipt-method');
        if (method) method.value = methods[0];
        row.remove();
      });
      entryRow.insertAdjacentHTML('afterend', sourceRowHtml);
      Object.assign(offsetState, { selected: null, open: false, query: '', error: '', row: entryRow });
      renderSourceCell();
      await refreshSources();
      renderSourceCell();
    }
    function hideSourceRow(entryRow) {
      if (entryRow.nextElementSibling?.classList.contains('offset-source-row')) entryRow.nextElementSibling.remove();
      Object.assign(offsetState, { selected: null, open: false, query: '', error: '' });
    }
    function closeDialog() { root.querySelector('.offset-backdrop')?.remove(); }
    // Kết quả lệnh cấn trừ: thành công thì gọi done; lỗi thì ghi câu tiếng Việt từ bảng mã lỗi vào errorBox.
    function afterOffset(outcome, errorBox, done) {
      if (outcome.status === 'saved') { done(outcome.result); return; }
      if (outcome.status === 'error') {
        const code = outcome.result?.error;
        errorBox.textContent = model.offsetErrorMessage(code, outcome.result);
        if (code === 'OFFSET_EXCEEDS_CREDIT') refreshSources();
      }
    }
    function showOffsetDialog(entryRow, source, amountVnd, date) {
      const preview = model.planOffsetPreview({ source, targetOutstandingVnd: BigInt(snapshot.total_outstanding_vnd), amountVnd });
      const f = model.formatVnd;
      const card = (name, view) => `<div class="offset-card"><div class="offset-card-title">Sổ ${escape(name)}</div><div class="offset-card-values"><span>${f(view.beforeVnd)}</span><span aria-hidden="true">→</span><strong>${f(view.afterVnd)}</strong></div></div>`;
      root.insertAdjacentHTML('beforeend', `<div class="offset-backdrop"><section class="offset-dialog" role="dialog" aria-modal="true" aria-labelledby="offset-dialog-title">
        <h2 id="offset-dialog-title">Xác nhận cấn trừ giữa hai sổ</h2>
        <p class="offset-sentence">Cấn trừ <strong>${f(amountVnd)}</strong> từ sổ <strong>${escape(source.label)}</strong> sang sổ <strong>${escape(ownName())}</strong>.</p>
        <div class="offset-cards">${card(source.label, preview.source)}${card(ownName(), preview.target)}</div>
        ${preview.targetNegativeVnd === null ? '' : `<p class="offset-over">Sổ ${escape(ownName())} sẽ còn ${f(preview.targetNegativeVnd)}.</p>`}
        <p class="offset-date-note">Ngày phiếu: ${escape(dateText(date))} · Hai sổ được ghi cùng lúc.</p>
        <p class="offset-dialog-error cell-error" role="alert"></p>
        <div class="offset-actions"><button type="button" class="offset-back">Quay lại</button><button type="button" class="offset-confirm">Ghi cấn trừ</button></div></section></div>`);
      const box = root.querySelector('.offset-backdrop');
      // Giữ phím Enter không tự xác nhận khi vừa gõ số tiền xong.
      box.addEventListener('keydown', keyEvent => { if (keyEvent.repeat) keyEvent.preventDefault(); });
      box.querySelector('.offset-back').addEventListener('click', () => { closeDialog(); entryRow.querySelector('.receipt-amount')?.focus(); });
      box.querySelector('.offset-confirm').addEventListener('click', async clickEvent => {
        const button = clickEvent.currentTarget;
        button.disabled = true;
        try {
          const outcome = await api.submitOffset('offset', { source_customer_id: source.customerId, source_version: source.version, date, amount_vnd: amountVnd.toString(), ...referenceFields(entryRow) });
          afterOffset(outcome, box.querySelector('.offset-dialog-error'), result => {
            let text = 'Đã ghi cấn trừ.';
            try {
              const done = model.parseOffsetResult(result);
              text = `Đã ghi ${done.targetPid}: cấn trừ ${f(amountVnd)} từ sổ ${source.label} (phiếu ${done.sourcePid}). Sổ đó còn ${f(preview.source.afterVnd)}.`
                + (done.overpaymentVnd > 0n ? ` Phần thừa ${f(done.overpaymentVnd)} thành ứng trước.` : '');
            } catch { /* kết quả lạ: giữ câu chung, số liệu vẫn lấy từ sổ vừa tải */ }
            closeDialog();
            showNotice(text + (result.target_receipt?.duplicate_reference ? ' Tham chiếu trùng với phiếu khác trong sổ.' : ''));
          });
          if (outcome.status === 'stale' || outcome.status === 'unknown') closeDialog();
        } catch (error) { showNotice(error.message); closeDialog(); }
        button.disabled = false;
      });
      box.querySelector('.offset-confirm').focus();
    }
    // Enter ở ô số tiền khi hình thức là CẤN TRỪ. Trả true nếu đã xử lý; false để ghi thu như thường (Ngoài sổ).
    async function startOffset(row) {
      const dateBox = row.querySelector('.receipt-date'), amountBox = row.querySelector('.receipt-amount');
      const dateError = row.querySelector('.receipt-date-error'), amountError = row.querySelector('.receipt-amount-error');
      const sourceRow = row.nextElementSibling?.classList.contains('offset-source-row') ? row.nextElementSibling : null;
      dateError.textContent = ''; amountError.textContent = '';
      const date = dateInput(dateBox.value.trim());
      if (!validDate(date)) { dateError.textContent = model.offsetErrorMessage('INVALID_DATE'); dateBox.focus(); return true; }
      if (date > todayIso()) { dateError.textContent = model.offsetErrorMessage('FUTURE_DATE'); dateBox.focus(); return true; }
      const plan = model.planOffsetEntry({ source: offsetState.selected, amountText: amountBox.value });
      if (!plan.ok) {
        if (plan.code === 'SOURCE_REQUIRED') { offsetState.error = plan.message; renderSourceCell(); sourceRow?.querySelector('.offset-source-select')?.focus(); }
        else { amountError.textContent = plan.message; amountBox.focus(); }
        return true;
      }
      if (plan.outside) return false;
      offsetState.error = ''; renderSourceCell();
      showOffsetDialog(row, offsetState.selected, plan.amountVnd, date);
      return true;
    }
    // Bấm ngày trả hoặc số tiền của dòng cấn trừ (ở bên nào cũng được): đổi ngày hoặc hủy cả cặp.
    async function openOffsetReceipt(cellEl) {
      const { pid, pair, other, otherName, field } = cellEl.dataset;
      let otherLedger;
      try { otherLedger = await api.readOther(other); } catch (error) { showNotice(error.message); return; }
      const rowEl = cellEl.closest('tr');
      if (field === 'date') {
        const original = cellEl.innerHTML;
        cellEl.innerHTML = `<input class="saved-receipt-input" aria-label="Sửa ngày trả cấn trừ ${escape(pid)}" value="${escape(cellEl.textContent)}" inputmode="numeric"><span class="cell-error receipt-date-error" role="status"></span>`;
        const input = cellEl.querySelector('input'); input.focus(); input.select();
        input.addEventListener('keydown', async keyEvent => {
          if (keyEvent.key === 'Escape') { cellEl.innerHTML = original; return; }
          if (keyEvent.key !== 'Enter') return;
          keyEvent.preventDefault();
          const box = cellEl.querySelector('.receipt-date-error');
          const date = dateInput(input.value.trim());
          if (!validDate(date)) { box.textContent = model.offsetErrorMessage('INVALID_DATE'); return; }
          if (date > todayIso()) { box.textContent = model.offsetErrorMessage('FUTURE_DATE'); return; }
          try {
            const outcome = await api.submitOffset('offsetDate', { other_version: otherLedger.version, offset_pair_id: pair, date });
            afterOffset(outcome, box, () => showNotice(`Đã đổi ngày cấn trừ ${pid} sang ${dateText(date)} ở cả hai sổ.`));
          } catch (error) { box.textContent = error.message; }
        });
        return;
      }
      root.querySelector('.void-prompt')?.remove();
      const theirs = [...(otherLedger.receipts ?? []), ...(otherLedger.outgoing_offsets ?? [])].find(item => String(item.offset_pair_id) === pair);
      const both = `<strong>${escape(pid)}</strong> ở sổ <strong>${escape(ownName())}</strong> và <strong>${escape(theirs?.pid ?? '–')}</strong> ở sổ <strong>${escape(otherName)}</strong>`;
      rowEl.insertAdjacentHTML('afterend', `<tr class="void-prompt offset-void-prompt" data-pair="${escape(pair)}" data-other-version="${otherLedger.version}"><td colspan="14"><div class="offset-void-head">Hủy cấn trừ ở cả hai sổ: ${both} — <strong>${escape(cellEl.textContent.replace('-', ''))}</strong></div><label>Lý do <input class="offset-void-reason" aria-label="Lý do hủy cấn trừ" aria-required="true" autocomplete="off"></label> <button type="button" class="confirm-offset-void">Hủy cả hai dòng</button> <button type="button" class="cancel-void">Bỏ qua</button><span class="cell-error offset-void-error" role="alert"></span></td></tr>`);
      rowEl.nextElementSibling.querySelector('input').focus();
    }
    async function confirmOffsetVoid(promptRow) {
      const reason = promptRow.querySelector('.offset-void-reason').value.trim();
      const box = promptRow.querySelector('.offset-void-error');
      if (!reason) { box.textContent = model.offsetErrorMessage('VOID_REASON_REQUIRED'); return; }
      try {
        const outcome = await api.submitOffset('offsetVoid', { other_version: promptRow.dataset.otherVersion, offset_pair_id: promptRow.dataset.pair, reason });
        afterOffset(outcome, box, () => showNotice('Đã hủy cấn trừ ở cả hai sổ.'));
      } catch (error) { box.textContent = error.message; }
    }
    root.addEventListener('change', event => {
      if (!event.target.matches('.receipt-method')) return;
      const row = event.target.closest('tr');
      if (event.target.value === 'CẤN TRỪ') showSourceRow(row); else hideSourceRow(row);
    });
    root.addEventListener('input', event => {
      if (!event.target.matches('.offset-search')) return;
      offsetState.query = event.target.value;
      renderOptions();
    });
    root.addEventListener('keydown', event => {
      if (event.key === 'Escape' && root.querySelector('.offset-backdrop')) { closeDialog(); offsetState.row?.querySelector('.receipt-amount')?.focus(); return; }
      if (event.key === 'Escape' && offsetState.open) { offsetState.open = false; renderSourceCell(); root.querySelector('.offset-source-select')?.focus(); return; }
      if (event.key === 'Enter' && event.target.matches('.offset-void-reason')) { event.preventDefault(); confirmOffsetVoid(event.target.closest('tr')); }
    });
    root.addEventListener('click', async event => {
      if (offsetState.open && !event.target.closest('.offset-picker,.offset-source-select')) { offsetState.open = false; renderSourceCell(); }
      if (event.target.closest('.offset-source-select')) {
        if (offsetState.open) { offsetState.open = false; renderSourceCell(); return; }
        await refreshSources();
        Object.assign(offsetState, { open: true, query: '' });
        renderSourceCell();
        root.querySelector('.offset-search')?.focus();
        return;
      }
      const option = event.target.closest('.offset-option');
      if (option) {
        offsetState.selected = option.dataset.source === 'OUTSIDE' ? OUTSIDE : offsetState.sources.find(item => item.customerId === option.dataset.source) ?? null;
        Object.assign(offsetState, { open: false, error: '' });
        renderSourceCell();
        offsetState.row?.querySelector('.receipt-amount')?.focus();
        return;
      }
      if (event.target.closest('.confirm-offset-void')) await confirmOffsetVoid(event.target.closest('tr'));
    });
    // CHỜ KIỂM (NEWTRIP-01): mở dòng kết luận ngay dưới chuyến, khuôn như hỏi lý do hủy phiếu.
    const closeReview = () => {
      root.querySelectorAll('.review-prompt').forEach(item => item.remove());
      root.querySelectorAll('.review-open').forEach(item => item.setAttribute('aria-expanded', 'false'));
    };
    function openReview(button) {
      const row = button.closest('tr');
      const wasOpen = row.nextElementSibling?.classList.contains('review-prompt');
      closeReview();
      if (wasOpen) return;
      const trip = (snapshot?.trips ?? []).find(item => String(item.id) === button.dataset.trip);
      const why = Object.hasOwn(reviewReasonText, trip?.review_reason) ? reviewReasonText[trip.review_reason] : 'Nghi trùng';
      button.setAttribute('aria-expanded', 'true');
      row.insertAdjacentHTML('afterend', `<tr class="review-prompt" data-trip="${escape(button.dataset.trip)}"><td colspan="14"><div>Chuyến ${escape(trip?.container ?? '')} đang CHỜ KIỂM, chưa tính vào số dư — ${escape(why)}</div><label>Lý do kết luận <input class="review-reason" aria-label="Lý do kết luận" maxlength="500" autocomplete="off"></label> <button type="button" class="review-confirm">Tính vào sổ</button> <button type="button" class="review-reject">Loại, không tính</button> <button type="button" class="review-cancel">Thôi</button><span class="cell-error review-error" role="alert"></span></td></tr>`);
      row.nextElementSibling.querySelector('.review-reason').focus();
    }
    async function concludeReview(promptRow, decision) {
      const box = promptRow.querySelector('.review-error');
      const reason = promptRow.querySelector('.review-reason').value.trim();
      if (!reason) { box.textContent = 'Cần nhập lý do kết luận'; return; }
      if (reason.length > 500) { box.textContent = 'Lý do tối đa 500 ký tự'; return; }
      const result = await submit('tripReview', { trip_id: Number(promptRow.dataset.trip), decision, reason });
      if (result?.message) box.textContent = result.message;
    }
    // ---- NHAP-SHEET-01: một ô = một lệnh; Enter/Tab/rời ô là lưu, Esc trả lại. Server chọn kỳ nợ và phân bổ lại. ----
    const findRow = (kind, id) => kind === 'trip'
      ? (snapshot?.trips ?? []).find(row => String(row.id) === id)
      : (snapshot?.legacy_rows ?? []).find(row => String(row.id) === id);
    const rowValues = (kind, row) => kind === 'trip' ? row : row?.current ?? {};
    function startValue(kind, id, field) {
      const value = rowValues(kind, findRow(kind, id))[field];
      if (value === null || value === undefined) return '';
      return field === 'event_date' ? dateText(value) : field.endsWith('_vnd') ? fmt(value) : String(value);
    }
    function openInfoEdit(td) {
      if (td.querySelector('input')) return;
      const { kind, id, field } = td.dataset;
      const original = td.innerHTML;
      const start = startValue(kind, id, field);
      const hint = field === 'event_date' ? ' placeholder="dd/mm/yyyy" inputmode="numeric"' : field.endsWith('_vnd') ? ' inputmode="numeric"' : '';
      td.innerHTML = `<input class="info-input${field.endsWith('_vnd') ? ' money-input' : ''}" aria-label="${escape(fieldNames[field][0].toUpperCase() + fieldNames[field].slice(1))} mới" value="${escape(start)}"${hint}><span class="cell-error" role="status"></span>`;
      const input = td.querySelector('input');
      input.focus(); input.select();
      let state = 'editing';
      const askRow = () => td.closest('tr')?.nextElementSibling?.classList.contains('move-ask') ? td.closest('tr').nextElementSibling : null;
      const restore = () => { state = 'done'; askRow()?.remove(); td.innerHTML = original; };
      // Ngày mới thuộc tháng khác: chưa lưu, hỏi lại ngay dưới dòng (chặn gõ nhầm 10/09 thay 10/10). Hỏi, không chặn.
      function askMove(value, before) {
        state = 'asking';
        const to = monthKey(value);
        const lock = (snapshot?.month_locks ?? []).find(row => monthKey(row.month) === to);
        const locked = lock ? lock.locked : to !== (monthKey(snapshot?.today_month) || liveOpenMonth);
        const what = `${kind === 'trip' ? 'chuyến' : 'dòng'} ${rowValues(kind, before).container || 'phí lẻ'}`;
        td.closest('tr').insertAdjacentHTML('afterend', `<tr class="move-ask"><td colspan="14">Ngày ${escape(dateText(value))} thuộc tháng ${monthLabel(to)}${locked ? ' (đã khóa)' : ''}. Chuyển ${escape(what)} sang tháng ${monthLabel(to)}? <button type="button" class="move-yes">Chuyển sang tháng ${monthLabel(to)}</button> <button type="button" class="move-no">Giữ ngày cũ (${escape(start)})</button></td></tr>`);
        const row = askRow();
        row.querySelector('.move-yes').addEventListener('click', () => { row.remove(); state = 'editing'; save(true); });
        row.querySelector('.move-no').addEventListener('click', () => { restore(); td.focus(); });
        row.querySelector('.move-yes').focus();
      }
      const save = async (confirmedMove = false) => {
        if (state !== 'editing') return;
        if (input.value.trim() === start.trim()) { restore(); return; }
        const box = td.querySelector('.cell-error');
        let value;
        try { value = model.parseCellEdit(field, input.value, todayIso()); } catch (error) { box.textContent = error.message; return; }
        const before = findRow(kind, id);
        if (field === 'event_date' && !confirmedMove && before && monthKey(value) !== monthKey(before.month)) { askMove(value, before); return; }
        const oldIso = rowValues(kind, before).event_date;
        state = 'saving';
        const result = kind === 'trip'
          ? await submit('tripInfo', { trip_id: Number(id), field, value })
          : await submit('legacyEdit', { legacy_row_id: Number(id), field, value });
        if (result?.error === 'NO_CHANGE') { if (td.isConnected) restore(); return; }
        if (result?.message) { state = 'editing'; if (td.isConnected) { box.textContent = result.message; input.focus(); } return; }
        state = 'done';
        // Sau khi lưu, sổ đã tải lại: báo những gì người dùng không thấy ngay trên dòng đang sửa.
        const after = findRow(kind, id);
        if (kind === 'trip' && after?.status === 'pending_review' && before?.status !== 'pending_review')
          showNotice(`Đã lưu. Chuyến thành CHỜ KIỂM, chưa tính vào số dư — ${reviewReasonText[after.review_reason] ?? 'nghi trùng'}.`);
        if (before && after && monthKey(before.month) !== monthKey(after.month)) {
          const rowKey = `${kind}-${id}`;
          const back = ghosts.findIndex(ghost => `${ghost.kind}-${ghost.id}` === rowKey && ghost.month === monthKey(after.month));
          if (back >= 0) { ghosts.splice(back, 1); moved.delete(rowKey); }   // sửa ngày về tháng cũ = như Hoàn tác
          else {
            for (let index = ghosts.length - 1; index >= 0; index--) if (`${ghosts[index].kind}-${ghosts[index].id}` === rowKey) ghosts.splice(index, 1);
            ghosts.push({ kind, id, month: monthKey(before.month), to: monthKey(after.month), container: rowValues(kind, after).container, oldIso });
            moved.set(rowKey, monthKey(before.month));
          }
          redraw();
          showRow(rowKey);
        }
      };
      input.addEventListener('keydown', keyEvent => {
        if (keyEvent.key === 'Escape') { keyEvent.stopPropagation(); restore(); td.focus(); return; }
        if (keyEvent.key === 'Enter') { keyEvent.preventDefault(); keyEvent.stopPropagation(); save(); }
      });
      // Tab hoặc bấm ra ngoài: lưu như Sheet; ô lỗi giữ nguyên ô nhập kèm lý do.
      input.addEventListener('blur', () => { save(); });
    }
    function openDelete(td) {
      const row = td.closest('tr');
      const wasOpen = row.nextElementSibling?.classList.contains('delete-prompt');
      root.querySelectorAll('.delete-prompt').forEach(item => item.remove());
      if (wasOpen) return;
      const { kind, id } = td.dataset;
      const data = findRow(kind, id);
      const values = rowValues(kind, data);
      const amount = kind === 'trip'
        ? data?.status === 'confirmed' || data?.status === undefined ? `thành tiền ${fmt(data?.amount_vnd)}` : 'chưa tính vào số dư'
        : `đang tính ${fmt(values.counted_vnd)}`;
      const what = `${kind === 'trip' ? 'chuyến' : 'dòng sổ gốc'} ${values.container || 'phí lẻ'} (${values.event_date ? dateText(values.event_date) : 'không ngày'}, ${amount})`;
      const extra = kind === 'legacy' ? ' Số dư đầu không đổi; phần trừ ghi ở dòng điều chỉnh sổ gốc của tháng.' : '';
      row.insertAdjacentHTML('afterend', `<tr class="void-prompt delete-prompt" data-kind="${escape(kind)}" data-id="${escape(id)}"><td colspan="14">Xóa hẳn ${escape(what)}?${escape(extra)} <button type="button" class="confirm-delete">Xóa hẳn</button> <button type="button" class="cancel-delete">Thôi</button><span class="cell-error delete-error" role="alert"></span></td></tr>`);
      row.nextElementSibling.querySelector('.cancel-delete').focus();
    }
    async function confirmDelete(promptRow) {
      const { kind, id } = promptRow.dataset;
      const result = kind === 'trip'
        ? await submit('tripDelete', { trip_id: Number(id) })
        : await submit('legacyDelete', { legacy_row_id: Number(id) });
      if (result?.message && promptRow.isConnected) promptRow.querySelector('.delete-error').textContent = result.message;
    }
    root.addEventListener('click', async event => {
      const infoEdit = event.target.closest('td.info-edit');
      if (infoEdit) { openInfoEdit(infoEdit); return; }
      const rowDelete = event.target.closest('td.row-delete');
      if (rowDelete) { openDelete(rowDelete); return; }
      const deleteRow = event.target.closest('.delete-prompt');
      if (deleteRow) {
        if (event.target.closest('.cancel-delete')) { deleteRow.remove(); return; }
        if (event.target.closest('.confirm-delete')) { event.target.disabled = true; await confirmDelete(deleteRow); event.target.disabled = false; return; }
        return;
      }
      const reviewOpen = event.target.closest('.review-open');
      if (reviewOpen) { openReview(reviewOpen); return; }
      const reviewRow = event.target.closest('.review-prompt');
      if (reviewRow) {
        if (event.target.closest('.review-cancel')) { closeReview(); return; }
        if (event.target.closest('.review-confirm')) { await concludeReview(reviewRow, 'confirm'); return; }
        if (event.target.closest('.review-reject')) { await concludeReview(reviewRow, 'reject'); return; }
      }
      if (event.target.closest('.history-toggle')) { historyOpen = !historyOpen; if (snapshot) renderSnapshot(snapshot); return; }
      if (event.target.closest('.history-close')) { historyOpen = false; if (snapshot) renderSnapshot(snapshot); return; }
      if (event.target.closest('.retry-command')) { await api.retry(); return; }
      // Ô tìm khách nằm trên đầu trang, trôi mất khi cuộn: nút ở thanh tiêu đề đưa về đó và mở danh sách.
      if (event.target.closest('.change-customer')) { window.scrollTo(0, 0); live.showCustomers(); return; }
      const lock = event.target.closest('.month-lock');
      if (lock) { await submit('lock', { month: lock.dataset.month, locked: lock.getAttribute('aria-pressed') === 'true' }); return; }
      const add = event.target.closest('.add-month-adjustment');
      if (add) {
        const row = add.closest('tr');
        if (!row.previousElementSibling?.classList.contains('month-adjustment-input')) row.insertAdjacentHTML('beforebegin',
          `<tr class="month-adjustment-input" data-month="${escape(add.dataset.month)}"><td colspan="9">Điều chỉnh cả tháng · <label>Ghi chú <input class="month-note" aria-label="Ghi chú điều chỉnh cả tháng"></label></td><td><input class="month-amount" aria-label="Số điều chỉnh cả tháng" placeholder="+5.000.000"><span class="cell-error" role="status"></span></td><td class="pay pay-start" colspan="4"></td></tr>`);
        row.previousElementSibling.querySelector('.month-amount').focus(); return;
      }
      const editable = event.target.closest('td.editable');
      if (editable && !editable.querySelector('input')) {
        const trip = snapshot.trips.find(row => row.id === Number(editable.dataset.trip));
        const field = editable.dataset.field;
        const locked = !trip.editable;
        const original = editable.innerHTML;
        editable.innerHTML = `<input class="money-input" aria-label="${field === 'unit_price_vnd' ? 'Đơn giá mới' : 'Phụ phí mới'}" value="${locked ? '' : escape(trip[field] === null ? '' : fmt(trip[field]))}">${locked ? '<label>Ghi chú <input class="adjustment-note" aria-label="Ghi chú điều chỉnh chuyến (tùy chọn)"></label>' : ''}<span class="cell-error" role="status"></span>`;
        const input = editable.querySelector('input'); input.focus(); input.select();
        const save = async keyEvent => {
          if (keyEvent.key === 'Escape') { editable.innerHTML = original; return; }
          if (keyEvent.key !== 'Enter') return;
          keyEvent.preventDefault();
          try {
            const value = moneyText(input.value, !locked);
            if (locked) {
              const result = await submit('tripAdjust', { trip_id: trip.id, field, new_value_vnd: value,
                note: editable.querySelector('.adjustment-note').value.trim() });
              if (result?.message) editable.querySelector('.cell-error').textContent = result.message;
            }
            else await submit('price', { trip_id: trip.id, unit_price_vnd: field === 'unit_price_vnd' ? value : trip.unit_price_vnd,
              other_fee_vnd: field === 'other_fee_vnd' ? value : trip.other_fee_vnd });
          } catch (error) { editable.querySelector('.cell-error').textContent = error.message; }
        };
        input.addEventListener('keydown', save);
        editable.querySelector('.adjustment-note')?.addEventListener('keydown', save);
        return;
      }
      const receipt = event.target.closest('small.receipt-ref') ?? event.target.closest('td.receipt[data-pid]');
      // Ô số tiền (không có data-field) chứa cả ô sửa tham chiếu: ô tham chiếu đang mở không được chặn việc hủy phiếu.
      const editorOpen = () => (receipt.dataset?.field ? receipt.querySelector('input,select') : event.target.closest?.('input,select'));
      if (receipt && !receipt.classList.contains('voided') && !receipt.classList.contains('voided-method') && !editorOpen()) {
        if (receipt.dataset.pair && receipt.dataset.field !== 'reference') { await openOffsetReceipt(receipt); return; }
        // Mỗi lần chỉ một ô sửa: đóng các ô sửa phiếu đang mở dở trước khi mở ô mới.
        root.querySelectorAll?.('.receipt-cancel-edit').forEach(open => open.dispatchEvent(new Event('cancel-edit')));
        const original = receipt.innerHTML, field = receipt.dataset.field, pid = receipt.dataset.pid;
        if (!field) {
          const row = receipt.closest('tr');
          root.querySelector('.void-prompt')?.remove();
          const saved = snapshot.receipts.find(item => item.pid === pid);
          row.insertAdjacentHTML('afterend', `<tr class="void-prompt" data-pid="${escape(pid)}"><td colspan="14">Hủy phiếu ${escape(pid)} — ${fmt(saved.amount_vnd)} <label>Lý do <input class="void-reason" aria-label="Lý do hủy phiếu"></label> <button class="confirm-void">Hủy phiếu</button> <button class="cancel-void">Bỏ qua</button><span class="cell-error" role="status"></span></td></tr>`);
          row.nextElementSibling.querySelector('input').focus(); return;
        }
        receipt.innerHTML = field === 'reference' ? `<input class="saved-receipt-input" aria-label="Sửa tham chiếu" maxlength="500" value="${escape(snapshot.receipts.find(item => item.pid === pid)?.reference)}">` : field === 'date' ? `<input class="saved-receipt-input" aria-label="Sửa ngày trả" value="${escape(receipt.textContent)}"><span class="cell-error receipt-date-error" role="status"></span>` :
          `<select class="saved-receipt-input" aria-label="Sửa hình thức">${methods.map(method => `<option${method === receipt.textContent ? ' selected' : ''}>${method}</option>`).join('')}</select>`;
        const input = receipt.querySelector('.saved-receipt-input'); input.focus();
        receipt.classList.add?.('receipt-cancel-edit');
        receipt.addEventListener?.('cancel-edit', () => { receipt.innerHTML = original; receipt.classList.remove('receipt-cancel-edit'); }, { once: true });
        input.addEventListener('keydown', async keyEvent => {
          if (keyEvent.key === 'Escape') { receipt.innerHTML = original; receipt.classList.remove?.('receipt-cancel-edit'); return; }
          if (keyEvent.key === 'Enter') {
            keyEvent.preventDefault();
            const result = await submit('receiptMeta', { pid, [field]: field === 'date' ? dateInput(input.value) : input.value });
            if (field === 'date' && result?.message) receipt.querySelector('.receipt-date-error').textContent = result.message;
          }
        }); return;
      }
      if (event.target.closest('.confirm-void')) {
        const row = event.target.closest('tr');
        const reason = row.querySelector('input').value.trim();
        if (!reason) { row.querySelector('.cell-error').textContent = 'Cần nhập lý do'; return; }
        await submit('receiptVoid', { pid: row.dataset.pid, reason });
      }
      if (event.target.closest('.cancel-void')) event.target.closest('tr').remove();
    });
    root.addEventListener('keydown', async event => {
      if (event.key !== 'Enter') return;
      if (event.target.matches('td.editable,td.receipt,td.info-edit,td.row-delete,small.receipt-ref')) { event.preventDefault(); event.target.click(); return; }
      if (event.target.matches('.month-amount,.month-note')) {
        event.preventDefault();
        const row = event.target.closest('tr');
        try {
          const amount = row.querySelector('.month-amount').value.trim();
          const negative = amount.startsWith('-');
          const digits = moneyText(negative || amount.startsWith('+') ? amount.slice(1) : amount);
          if (digits === '0') throw Error('Số điều chỉnh phải khác 0.');
          await submit('monthAdjust', { debt_month: row.dataset.month,
            amount_vnd: negative ? '-' + digits : digits, note: row.querySelector('.month-note').value.trim() });
        }
        catch (error) { showNotice(error.message); }
      }
      if (event.target.matches('.receipt-amount') || event.target.matches('.receipt-reference')) {
        event.preventDefault();
        const row = event.target.closest('tr');
        try {
          row.querySelector('.receipt-date-error').textContent = '';
          if (row.querySelector('.receipt-method').value === 'CẤN TRỪ' && await startOffset(row)) return;
          const result = await submit('receipt', { date: dateInput(row.querySelector('.receipt-date').value), method: row.querySelector('.receipt-method').value,
            amount_vnd: moneyText(row.querySelector('.receipt-amount').value), ...referenceFields(row) });
          if (result?.error === 'FUTURE_RECEIPT_DATE') {
            row.querySelector('.receipt-date-error').textContent = result.message;
            row.querySelector('.receipt-date').focus();
          }
        }
        catch (error) { showNotice(error.message); }
      }
      if (event.target.matches('.receipt-date')) { event.preventDefault(); event.target.closest('tr').querySelector('.receipt-amount').focus(); }
    });
    root.addEventListener('input', event => {
      if (event.target.matches('.receipt-date') && event.target.value.length === 10) event.target.closest('tr').querySelector('.receipt-amount').focus();
    });
    // ---- Bảng nhập: gõ chỉ ghi vào nháp, vẽ lại khi rời ô (không phá bộ gõ tiếng Việt giữa chừng),
    // trừ lần đầu gõ vào hàng trống: cần mọc ngay một hàng trống mới bên dưới. ----
    const draftAt = element => element?.matches?.('.draft-input') ? { month: element.dataset.month, row: Number(element.dataset.draft), field: element.dataset.field } : null;
    root.addEventListener('input', event => {
      const here = draftAt(event.target);
      if (!here) return;
      const drafts = [...draftsOf(here.month)];
      const fresh = here.row === drafts.length;
      drafts[here.row] ??= model.blankDraft();
      drafts[here.row][here.field] = event.target.value;
      setDrafts(here.month, drafts);
      draftNote = { key: '', text: '' };
      if (fresh && !event.isComposing) redraw({ ...here, caret: event.target.selectionStart });
    });
    root.addEventListener('compositionend', event => {
      const here = draftAt(event.target);
      const count = here && draftsOf(here.month).length;
      if (here && here.row === count - 1 && !root.querySelector(`.draft-input[data-month="${here.month}"][data-draft="${count}"]`)) redraw({ ...here, caret: event.target.selectionStart });
    });
    root.addEventListener('paste', event => {
      const here = draftAt(event.target);
      if (!here) return;
      const text = event.clipboardData.getData('text/plain');
      if (!/[\t\n]/.test(text.replace(/\r?\n$/, ''))) return;   // một ô: dán như thường
      event.preventDefault();
      const read = model.spreadPaste(text, here.field);
      const drafts = [...draftsOf(here.month)];
      read.rows.forEach((row, offset) => {
        const index = here.row + offset;
        // Dán theo cột web (không thấy container): chỉ đè các ô được dán, giữ ô khác của hàng nháp.
        drafts[index] = read.byColumn ? model.tidyDraft({ ...(drafts[index] ?? model.blankDraft()), ...Object.fromEntries(DRAFT_FIELDS.filter(name => row[name]).map(name => [name, row[name]])) }) : row;
      });
      setDrafts(here.month, drafts);
      draftNote = { key: here.month, text: [read.payments ? 'Phần tiền khách trả trong vùng dán đã bỏ qua — khoản thu ghi ở ô Ngày trả / Số tiền trả.' : '',
        read.skipped ? `Bỏ qua ${read.skipped} hàng trống hoặc hàng cộng.` : ''].filter(Boolean).join(' ') };
      redraw({ month: here.month, row: Math.min(here.row + read.rows.length, drafts.length), field: 'container' });
    });
    root.addEventListener('focusout', event => {
      const left = draftAt(event.target);
      if (!left || rendering) return;
      const drafts = [...draftsOf(left.month)];
      if (drafts[left.row]) { drafts[left.row] = model.tidyDraft(drafts[left.row]); setDrafts(left.month, drafts); }
      requestAnimationFrame(() => {
        const next = draftAt(document.activeElement);
        // Sang ô nháp khác hoặc ra ngoài trang: vẽ lại để hiện lỗi/thành tiền; đang ở ô khác của sổ thì để yên.
        if (next || !root.contains(document.activeElement)) {
          const same = next?.month === left.month;
          const keep = next && (same ? { ...next, row: next.row - drafts.slice(0, next.row).filter(draftEmpty).length } : next);
          setDrafts(left.month, drafts.filter((row, index) => !draftEmpty(row) || (same && index === next.row)));
          redraw(keep);
        }
      });
    });
    root.addEventListener('keydown', event => {
      const here = draftAt(event.target);
      if (!here || !['Enter', 'ArrowDown', 'ArrowUp'].includes(event.key)) return;
      event.preventDefault();
      const row = Math.max(0, Math.min(draftsOf(here.month).length, here.row + (event.key === 'ArrowUp' ? -1 : 1)));
      root.querySelector(`.draft-input[data-month="${here.month}"][data-draft="${row}"][data-field="${here.field}"]`)?.focus();
    });
    root.addEventListener('click', async event => {
      const discard = event.target.closest('.draft-discard');
      if (discard) {
        const key = discard.dataset.month;
        if (confirm(`Bỏ ${draftsOf(key).length} chuyến nháp?`)) { setDrafts(key, []); draftNote = { key: '', text: '' }; redraw(); }
        return;
      }
      const save = event.target.closest('.draft-save');
      if (!save) return;
      const key = save.dataset.month;
      const drafts = draftsOf(key);
      const checked = drafts.map(row => model.checkDraft(row, todayIso()));
      if (!drafts.length || checked.some(item => !item.trip)) { redraw(); return; }
      save.disabled = true;
      const count = drafts.length;
      const result = await submit('paste', { debt_month: `${key}-01`, trips: checked.map(item => item.trip) });
      if (api.lastOutcome()?.status === 'saved') {
        const ids = new Set((api.lastOutcome().result?.pending_review ?? []).map(item => String(item.trip_id)));
        setDrafts(key, []);
        draftNote = { key, text: `Đã lưu ${count} chuyến${ids.size ? ` (${ids.size} chuyến CHỜ KIỂM: nghi trùng, chưa tính nợ)` : ''}.` };
        showNotice('');
        redraw({ month: key, row: 0, field: 'container' });
      } else if (result?.message) { draftNote = { key, text: result.message }; redraw(); }
    });
    window.addEventListener?.('beforeunload', event => { if (draftsBy.size) event.preventDefault(); });
    // ---- Chuyển tháng: Xem / Hoàn tác ở dòng mờ của tháng cũ ----
    const showRow = rowKey => {
      const row = root.querySelector(`tr[data-row="${rowKey}"]`);
      row?.scrollIntoView({ block: 'center' });
      return row;
    };
    root.addEventListener('click', async event => {
      const go = event.target.closest('.ghost-go');
      if (go) { showRow(go.dataset.row); return; }
      const undo = event.target.closest('.ghost-undo');
      if (!undo) return;
      const ghost = ghosts[Number(undo.dataset.ghost)];
      if (!ghost) return;
      undo.disabled = true;
      const result = ghost.kind === 'trip'
        ? await submit('tripInfo', { trip_id: Number(ghost.id), field: 'event_date', value: ghost.oldIso })
        : await submit('legacyEdit', { legacy_row_id: Number(ghost.id), field: 'event_date', value: ghost.oldIso });
      if (api.lastOutcome()?.status !== 'saved') { if (result?.message) showNotice(result.message); undo.disabled = false; return; }
      ghosts.splice(ghosts.indexOf(ghost), 1);
      moved.delete(`${ghost.kind}-${ghost.id}`);
      showNotice('');
      redraw();
      showRow(`${ghost.kind}-${ghost.id}`);
    });
    root.innerHTML = '<p role="status">Đang đọc sổ khách…</p>';
    api.read().catch(error => { root.innerHTML = `<p role="alert">${escape(error.message)}</p>`; });
    setInterval(() => {
      if (document.hidden || api.hasPending() || root.querySelector('input:focus,textarea:focus,select:focus')
        || [...root.querySelectorAll('.draft-input,.receipt-date,.receipt-amount,.receipt-reference,.info-input')]
          .some(input => input.value.trim())) return;
      api.read().catch(() => showNotice('Không tải được chuyến mới. Thử tải lại trang.'));
    }, 60_000);
  }

  function startEdit(cell) {
    notice = '';
    if (cell.querySelector('input')) return;
    const { month, index, field } = cell.dataset;
    const trip = months.find(item => item.key === month).trips[Number(index)];
    const original = cell.innerHTML;
    cell.innerHTML = `<input class="money-input" aria-label="${escape(cell.getAttribute('aria-label'))}" value="${escape(trip[field] === null ? '' : fieldMoney(trip[field]))}"><span class="cell-error" role="status"></span>`;
    const input = cell.querySelector('input');
    input.focus(); input.select();
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { cell.innerHTML = original; cell.focus(); }
      if (event.key !== 'Enter') return;
      event.preventDefault();
      let value = null;
      const lineId = trip.id ?? `${month}#${index}`;
      try { if (input.value.trim()) value = model.parseVnd(input.value).toString(); }
      catch { cell.querySelector('.cell-error').textContent = 'Số tiền không hợp lệ'; return; }
      if (model.isMonthOpen(locks, month)) {
        const before = trip[field] === null ? '–' : fieldMoney(trip[field]);
        trip[field] = value;
        log('Sửa đè ' + (field === 'unitPriceVnd' ? 'đơn giá' : 'phụ phí'), `Tháng ${monthLabel(month)}, chuyến ${Number(index) + 1}: ${before} → ${value === null ? '–' : fieldMoney(value)}`);
        reallocate();
      }
      else {
        let amount;
        try { amount = model.amountWith(trip, { [field]: value }); }
        catch { cell.querySelector('.cell-error').textContent = 'Chuyến chưa có giá'; return; }
        const owner = months.find(item => item.key === month);
        owner.adjustments ??= [];
        const planned = model.planAdjustment(book, locks, { monthKey: month, lineId, newAmountVnd: amount.toString() });
        if (planned) {
          owner.adjustments.push(planned);
          log('Điều chỉnh chuyến', `Tháng ${monthLabel(month)}, chuyến ${Number(index) + 1}: ${money(planned.oldAmountVnd)} → ${money(planned.newAmountVnd)}`);
          reallocate();
        }
      }
      render();
    });
  }

  function saveReceipt(input) {
    const row = input.closest('tr');
    const date = row.querySelector('.receipt-date');
    const amount = row.querySelector('.receipt-amount');
    const method = row.querySelector('.receipt-method').value;
    const reference = referenceFields().reference ?? null;
    row.querySelectorAll('.receipt-date-error,.receipt-amount-error').forEach(error => { error.textContent = ''; });
    let amountVnd;
    try { amountVnd = model.parsePositiveVnd(amount.value); }
    catch { row.querySelector('.receipt-amount-error').textContent = 'Số tiền phải lớn hơn 0 và đúng định dạng'; amount.focus(); return; }
    const pid = model.nextReceiptPid(book);
    let plan;
    try { plan = model.planReceipt(book, { pid, date: date.value, method, amountVnd: amountVnd.toString() }); }
    catch { row.querySelector('.receipt-date-error').textContent = 'Ngày trả không hợp lệ'; date.focus(); return; }
    for (const line of plan.lines) months.find(month => month.key === line.monthKey).receipts.push({
      pid, reference, date: date.value, method: line.kind === 'advance' ? 'ỨNG TRƯỚC' : method,
      amountVnd: line.amountVnd, kind: line.kind, ...(line.kind === 'advance' ? { receiptMethod: method } : {}), voided: null,
    });
    notice = model.receiptNotice(pid, plan) + (reference && months.some(month => month.receipts.some(item => item.pid !== pid && item.reference === reference)) ? ' Tham chiếu trùng với phiếu khác trong sổ.' : '');
    log('Ghi thu', `${pid}: 0 → ${money(amountVnd)}. ${notice}`);
    voidPrompt = null;
    render();
  }

  function startReceiptEdit(cell) {
    if (cell.querySelector('input,select')) return;
    const { pid, field } = cell.dataset;
    const original = cell.innerHTML;
    const value = field === 'reference' ? months.flatMap(month => month.receipts).find(item => item.pid === pid)?.reference ?? '' : cell.textContent;
    cell.innerHTML = field === 'reference' ? `<input class="saved-receipt-input" aria-label="Sửa tham chiếu ${escape(pid)}" maxlength="500" value="${escape(value)}"><span class="cell-error" role="status"></span>` : field === 'date'
      ? `<input class="saved-receipt-input receipt-date" aria-label="Sửa ngày trả ${escape(pid)}" value="${escape(value)}" inputmode="numeric"><span class="cell-error" role="status"></span>`
      : `<select class="saved-receipt-input receipt-method" aria-label="Sửa hình thức ${escape(pid)}">${methods.map(method => `<option${method === value ? ' selected' : ''}>${method}</option>`).join('')}</select><span class="cell-error" role="status"></span>`;
    const input = cell.querySelector('.saved-receipt-input');
    input.focus();
    if (field === 'date') input.select();
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.stopPropagation(); cell.innerHTML = original; cell.focus(); return; }
      if (event.key !== 'Enter') return;
      event.preventDefault(); event.stopPropagation();
      let plan;
      try { plan = model.planReceiptEdit(book, pid, { [field]: input.value }); }
      catch { cell.querySelector('.cell-error').textContent = field === 'date' ? 'Ngày trả không hợp lệ' : 'Hình thức không hợp lệ'; return; }
      log(field === 'reference' ? 'Sửa tham chiếu phiếu' : field === 'date' ? 'Sửa ngày phiếu' : 'Sửa hình thức phiếu', `${pid}: ${value} → ${input.value}`);
      for (const line of plan.lines) months.find(month => month.key === line.monthKey).receipts[line.index] = line.receipt;
      if (plan.reallocation) reallocate(plan.reallocation);
      notice = field === 'reference' && input.value.trim() && months.some(month => month.receipts.some(item => item.pid !== pid && item.reference === input.value.trim())) ? 'Tham chiếu trùng với phiếu khác trong sổ.' : '';
      render();
    });
  }

  if (!live) root.addEventListener('click', event => {
    if (event.target.closest('.history-toggle')) { historyOpen = !historyOpen; render(); return; }
    if (event.target.closest('.history-close')) { historyOpen = false; render(); root.querySelector('.history-toggle').focus(); return; }
    const lock = event.target.closest('.month-lock');
    if (lock) { locks[lock.dataset.month] = !locks[lock.dataset.month]; log(locks[lock.dataset.month] ? 'Khóa tháng' : 'Mở tháng', `Tháng ${monthLabel(lock.dataset.month)}`); render(); return; }
    const addMonth = event.target.closest('.add-month-adjustment');
    if (addMonth) { monthPrompt = addMonth.dataset.month; render(); root.querySelector(`#thang-${monthPrompt} .month-amount`).focus(); return; }
    const cell = event.target.closest('td.editable');
    if (cell) { startEdit(cell); return; }
    const receipt = event.target.closest('td.receipt[data-pid]');
    if (receipt && !receipt.classList.contains('voided') && !receipt.classList.contains('voided-method')) {
      if (receipt.classList.contains('receipt-edit')) { startReceiptEdit(receipt); return; }
      const pid = receipt.dataset.pid;
      const details = model.receiptDetails(book, pid);
      voidPrompt = { pid, monthKey: receipt.closest('section').id.slice(6), totalVnd: details.totalVnd, monthCount: details.monthKeys.length };
      notice = '';
      render();
      root.querySelector('.void-reason')?.focus();
      return;
    }
    if (event.target.matches('.cancel-void')) { voidPrompt = null; render(); return; }
    if (event.target.matches('.confirm-void')) {
      const reasonInput = root.querySelector('.void-reason');
      const reason = reasonInput.value.trim();
      if (!reason) { root.querySelector('.void-error').textContent = 'Cần nhập lý do'; reasonInput.focus(); return; }
      const voidedOn = today.split('-').reverse().join('/');
      const plan = model.planVoid(book, voidPrompt.pid, reason, voidedOn);
      log('Hủy phiếu', `${voidPrompt.pid}: ${money(plan.totalVnd)} → đã hủy`, reason);
      for (const line of plan.lines) months.find(month => month.key === line.monthKey).receipts[line.index] = line.receipt;
      voidPrompt = null;
      notice = '';
      render();
    }
  });
  if (!live) root.addEventListener('keydown', event => {
    if (event.target.matches('.month-amount,.month-note') && event.key === 'Enter') {
      event.preventDefault();
      const row = event.target.closest('tr');
      const amount = row.querySelector('.month-amount');
      const reason = row.querySelector('.month-note').value.trim();
      let planned;
      try { planned = model.planMonthAdjustment(book, { monthKey: monthPrompt, amount: amount.value, reason }); }
      catch { row.querySelector('.month-error').textContent = 'Số điều chỉnh phải khác 0 và đúng định dạng'; amount.focus(); return; }
      const owner = months.find(month => month.key === monthPrompt);
      owner.adjustments ??= [];
      owner.adjustments.push(planned);
      log('Điều chỉnh cả tháng', `Tháng ${monthLabel(monthPrompt)}: 0 → ${money(model.adjustmentAmount(planned))}`, reason);
      monthPrompt = null;
      reallocate(); render(); return;
    }
    if (event.target.matches('td.editable') && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); startEdit(event.target); }
    if (event.target.matches('td.receipt[data-pid]') && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); event.target.click(); }
    if (event.target.matches('.receipt-date') && event.key === 'Enter') { event.preventDefault(); event.target.closest('tr').querySelector('.receipt-amount').focus(); }
    if ((event.target.matches('.receipt-amount') || event.target.matches('.receipt-reference')) && event.key === 'Enter') { event.preventDefault(); saveReceipt(root.querySelector('.receipt-amount')); }
    if (event.target.matches('.adjustment-note') && event.key === 'Enter') {
      event.preventDefault();
      const { month, adj } = event.target.dataset;
      const owner = months.find(item => item.key === month);
      const item = owner.adjustments.find(adjustment => adjustment.adjId === adj);
      if (!item) return;
      if (item.reason !== event.target.value.trim()) log('Ghi chú điều chỉnh chuyến', `Tháng ${monthLabel(month)}, ${money(model.adjustmentAmount(item))}: ${item.reason || '–'} → ${event.target.value.trim() || '–'}`, event.target.value.trim());
      owner.adjustments[owner.adjustments.indexOf(item)] = { ...item, reason: event.target.value.trim() };
      render();
    }
  });
  if (!live) root.addEventListener('paste', event => {
    if (!event.target.matches('.paste-input')) return;
    event.preventDefault();
    const result = model.parsePastedTrips(event.clipboardData.getData('text/plain'));
    const error = event.target.closest('tr').querySelector('.paste-error');
    if (result.errors) { error.textContent = result.errors.join(' · '); return; }
    const classified = model.classifyPastedTrips(result.trips, months.flatMap(month => month.trips));
    months.find(item => item.key === event.target.dataset.month).trips.push(...classified);
    log('Dán lô', `Tháng ${monthLabel(event.target.dataset.month)}: 0 → ${result.trips.length} dòng`);
    reallocate();
    render();
  });
  if (!live) root.addEventListener('input', event => {
    if (event.target.matches('.receipt-date:not(.saved-receipt-input)') && event.target.value.length === 10) event.target.closest('tr').querySelector('.receipt-amount').focus();
    if (event.target.matches('.void-reason')) root.querySelector('.void-error').textContent = '';
  });
  if (!live) document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && historyOpen) { historyOpen = false; render(); root.querySelector('.history-toggle').focus(); }
  });
  if (live) initLive(); else render();
})();
