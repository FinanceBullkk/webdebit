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
  // SO-GON-02 (29/10/2026): bản live bỏ cột "Còn nợ cộng dồn" (luôn trống); còn nợ cuối tháng ở thanh tháng và dòng Tổng tháng.
  // PHU-PHI-01: bản live có 0–3 cột phụ phí riêng của sổ chen giữa Đơn giá và Khác, nên số cột đổi theo sổ (useLiveColumns).
  let labels = live ? ['STT', 'Số container', 'Hãng tàu', 'Shipper', 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá', 'Khác', 'Thành tiền', 'Ngày trả', 'Hình thức', 'Số tiền trả'] : ['STT', 'Số container', 'Hãng tàu', 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá', 'Phụ phí', 'Thành tiền', 'Ngày trả', 'Hình thức', 'Số tiền trả', 'Còn nợ cộng dồn'];
  let wide = live ? [52, 148, 104, 188, 104, 118, 118, 128, 116, 148, 124, 124, 224] : [52, 148, 104, 104, 118, 118, 128, 116, 148, 112, 112, 150, 158];
  const colTags = (from, to) => wide.slice(from, to).map((width, index) => `<col style="width:${width}px" class="col-${from + index}">`).join('');
  let widths = colTags(0, wide.length);
  let ownCount = 0;
  // Bề rộng từng cột ở hai khổ sổ (1696px màn rộng, 1258px màn 1280): [màn rộng, tối thiểu màn rộng, màn 1280, tối thiểu màn 1280].
  // Mỗi cột riêng lấy chỗ từ các cột theo thứ tự `shrinkOrder`, không cột nào hẹp hơn mức tối thiểu; 3 cột riêng vừa khít 1258px.
  const liveColumns = [[52, 44, 44, 40], [148, 120, 112, 108], [104, 80, 62, 58], [188, 120, 150, 90], [104, 96, 90, 86], [118, 90, 80, 70],
    [118, 90, 80, 70], [128, 110, 88, 84], [116, 100, 80, 76], [148, 120, 100, 96], [124, 100, 96, 84], [124, 100, 90, 78], [224, 150, 186, 120]];
  const shrinkOrder = [12, 3, 10, 11, 5, 6, 1, 2, 4, 7, 9, 8, 0];
  const isWide = () => typeof matchMedia !== 'function' || !matchMedia('(max-width:1877px)').matches;
  function useLiveColumns(ownNames) {
    const wideMode = isWide(), ownWidth = wideMode ? 110 : 66;
    const base = liveColumns.map(item => wideMode ? item[0] : item[2]);
    let need = ownNames.length * ownWidth;
    for (const index of shrinkOrder) {
      const take = Math.min(need, base[index] - liveColumns[index][wideMode ? 1 : 3]);
      base[index] -= take; need -= take;
    }
    ownCount = ownNames.length;
    labels = ['STT', 'Số container', 'Hãng tàu', 'Shipper', 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá', ...ownNames, 'Khác', 'Thành tiền', 'Ngày trả', 'Hình thức', 'Số tiền trả'];
    wide = [...base.slice(0, 8), ...ownNames.map(() => ownWidth), ...base.slice(8)];
    widths = colTags(0, wide.length);
  }
  // Chỉ số cột: chuyến 0..tripCols-1 (cụm phụ phí từ 8), phiếu thu 3 cột cuối.
  const tripCols = () => labels.length - 3;
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
    ${view.notice ?? ''}<div class="layout"><div class="ledger-book"><table class="ledger ledger-head" aria-label="Cột sổ khách"><colgroup>${widths}</colgroup><thead><tr class="columns">${labels.map((label, index) => {
      const payStart = live ? tripCols() : 9;
      const fee = live && index >= 8 && index < tripCols() - 1;
      return `<th scope="col" class="${index >= payStart && index <= payStart + 2 ? 'pay ' : ''}${index === payStart ? 'pay-start' : ''}${fee ? 'fee-h num' : ''}"${fee ? ' title="Phụ phí"' : ''}>${escape(label)}</th>`;
    }).join('')}</tr></thead></table>${view.sections}</div>
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
    pinReceipts();
    window.scrollTo(0, scrollY);
  }

  // Góp ý 28/10/2026: cuộn xuống trong tháng vẫn thấy các khoản đã thu. SO-GON-02: phiếu thu là danh sách riêng
  // bên phải (không chung hàng với chuyến); cả danh sách dính ngay dưới dòng tháng khi vừa màn. Dài hơn màn thì để yên
  // (không cắt khung: ô chọn sổ cấn trừ mở xuống dưới hàng nhập). Ô chữ chuyến bị cắt "…" thì rê chuột xem đủ.
  function pinReceipts() {
    if (typeof root.querySelectorAll !== 'function' || typeof getComputedStyle !== 'function') return;
    for (const table of root.querySelectorAll('section > table.ledger')) {
      const head = table.querySelector('tr.month th'), stick = table.querySelector('.pay-stick');
      if (!head || !stick) continue;
      const top = (Number.parseInt(getComputedStyle(head).top, 10) || 0) + head.offsetHeight;
      const fits = stick.offsetHeight <= window.innerHeight - top - 8;
      stick.classList.toggle('pinned', fits);
      stick.style.top = fits ? `${top}px` : '';
      for (const td of table.querySelectorAll('.trip-list td')) {
        if (td.scrollWidth > td.clientWidth && !td.title) td.title = td.textContent.trim();
      }
    }
  }
  if (typeof window.addEventListener === 'function') window.addEventListener('resize', pinReceipts);

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
      const button = document.querySelector('#refresh-data');
      if (button?.id === 'refresh-data') button.disabled = true;
      const updated = document.querySelector('#updated-at');
      if (updated?.id === 'updated-at') updated.textContent = 'Chọn khách để xem dữ liệu';
      return;
    }
    let snapshot = null;
    // Nút "Làm mới" đọc Sheet ngay (specs/v7-sheet-refresh.md); server chưa bật thì giữ chữ "Cập nhật …".
    let sheetRefresh = null;
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
    const openVoided = new Set(); // tháng (yyyy-mm) đang mở danh sách phiếu đã hủy; chỉ sống trong tab
    const movedTag = rowKey => moved.has(rowKey) ? `<tr class="moved-note"><td colspan="${tripCols()}"><span class="moved-tag">↪ Vừa chuyển từ T${Number(moved.get(rowKey).slice(5))}</span></td></tr>` : '';
    const fieldNames = { container: 'số container', carrier: 'hãng tàu', shipper: 'shipper', event_date: 'ngày chuyến', origin: 'nơi đi',
      destination: 'nơi đến', unit_price_vnd: 'đơn giá', other_fee_vnd: 'phụ phí' };
    const infoCell = (kind, id, field, text, classes = '') =>
      `<td class="info-edit ${classes}" data-kind="${kind}" data-id="${escape(id)}" data-field="${field}" tabindex="0" role="button" aria-label="Sửa ${fieldNames[field]}">${escape(text)}</td>`;
    const deleteCell = (kind, id, text, what, pick = '') =>
      `<td class="row-delete" data-kind="${kind}" data-id="${escape(id)}" tabindex="0" role="button" aria-label="Xóa hẳn ${escape(what)}" title="Bấm để xóa hẳn dòng này">${pick}${escape(text)}</td>`;
    // PHU-PHI-01: cụm cột phụ phí = cột riêng của sổ (0–3, theo fee_columns) + Khác. Số lấy từ fee_lines của server,
    // model cộng để hiện (ARCH-03). Ô cột riêng: bấm gõ số; ô Khác: mở khung chi tiết (so-khach-v7-fee-ui.js).
    let feeColumnIds = [];
    let feeTypes = [];
    const feeTypeName = id => feeTypes.find(type => Number(type.id) === Number(id))?.name ?? `Loại #${id}`;
    const feeCells = (target, what, lines, editable) => {
      const cells = model.feeCells(lines ?? [], feeColumnIds);
      const own = feeColumnIds.map((id, index) => `<td class="num fee own${editable ? ' fee-edit' : ''}" data-fee-target="${target}" data-fee-type="${id}"${editable ? ` tabindex="0" role="button" aria-label="Sửa ${escape(feeTypeName(id))} ${escape(what)}"` : ''}>${cells.own[index] === null ? '' : model.formatVnd(cells.own[index])}</td>`).join('');
      const other = cells.otherCount ? `<span class="fee-sum">${model.formatVnd(cells.otherVnd)}</span><small>${cells.otherCount} khoản</small>`
        : editable ? '<span class="fee-plus">+ thêm</span>' : '';
      return `${own}<td class="num fee fee-other" data-field="other_fee_vnd" data-fee-target="${target}" tabindex="0" role="button" aria-label="Chi tiết phụ phí ${escape(what)}">${other}</td>`;
    };
    const feeEmpty = () => feeColumnIds.map(() => empty('num fee')).join('') + empty('num fee');
    const feePick = (target, what, editable) => editable
      ? `<input type="checkbox" class="fee-pick" data-fee-target="${target}" aria-label="Chọn ${escape(what)} để thêm phụ phí">` : '';
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
          ? `${cell(stt || '–')}${cell(cur.container || 'Phí lẻ')}${cell(cur.carrier ?? '')}${cell(cur.shipper ?? '')}${cell(cur.event_date ? dateText(cur.event_date) : rawDay(t.raw_date))}${cell(cur.origin ?? '')}${cell(cur.destination ?? '')}${num(unitText[0])}${feeCells(`legacy:${trip.id}`, cur.container || 'phí lẻ', trip.fee_lines, false)}${num(cur.unit_price_vnd == null && cur.counted_vnd === '0' ? '–' : fmt(cur.counted_vnd))}`
          : cur
          ? `${deleteCell('legacy', trip.id, stt || '–', `dòng sổ gốc ${cur.container || 'phí lẻ'}`, feePick(`legacy:${trip.id}`, cur.container || 'phí lẻ', cur.unit_price_vnd != null))}${infoCell('legacy', trip.id, 'container', cur.container || 'Phí lẻ')}${infoCell('legacy', trip.id, 'carrier', cur.carrier ?? '')}${infoCell('legacy', trip.id, 'shipper', cur.shipper ?? '')}${infoCell('legacy', trip.id, 'event_date', cur.event_date ? dateText(cur.event_date) : rawDay(t.raw_date))}${infoCell('legacy', trip.id, 'origin', cur.origin ?? '')}${infoCell('legacy', trip.id, 'destination', cur.destination ?? '')}${infoCell('legacy', trip.id, 'unit_price_vnd', unitText[0], `num ${unitText[1]}`)}${feeCells(`legacy:${trip.id}`, cur.container || 'phí lẻ', trip.fee_lines, cur.unit_price_vnd != null)}${num(cur.unit_price_vnd == null && cur.counted_vnd === '0' ? '–' : fmt(cur.counted_vnd))}`
          : trip
          ? `${cell(String(t.stt ?? '').replace(/^(\d+)\.0+$/, '$1'))}${cell(t.container || 'Phí lẻ')}${cell(t.carrier ?? '')}${cell(t.shipper ?? '')}${cell(t.date ? dateText(t.date) : rawDay(t.raw_date))}${cell(t.from ?? '')}${cell(t.to ?? '')}${!t.unit_price && (t.flags ?? []).includes('MISSING_PRICE') ? '<td class="num missing">chưa có giá</td>' : num(moneyCell(t.unit_price))}${feeCells(`legacy:${trip.id}`, t.container || 'phí lẻ', trip.fee_lines, false)}${num(fmt(trip.source_total_vnd))}`
          : `${empty()}${empty()}${empty()}${empty()}${empty()}${empty()}${empty()}${empty('num')}${feeEmpty()}${empty('num')}`;
        // Hình thức thu không suy từ ghi chú (V7-MIG còn mở); ghi chú chỉ hiện khi không lặp lại cùng ngày.
        const day = sheetDay(r.raw_date);
        const noteText = r.note && r.note !== r.raw_date && sheetDay(r.note) !== day ? r.note : '';
        // XOA-THU-GOC-01: tháng mở thì bấm số tiền khoản thu sổ gốc để xóa hẳn.
        const payAmount = receipt && !locked
          ? `<td class="pay num row-delete" data-kind="legacy" data-id="${escape(receipt.id)}" tabindex="0" role="button" aria-label="Xóa hẳn khoản thu sổ gốc ${escape(fmt(receipt.source_total_vnd))}" title="Bấm để xóa hẳn khoản thu này">${fmt(receipt.source_total_vnd)}</td>`
          : num(fmt(receipt?.source_total_vnd), 'pay');
        const sheetPay = receipt ? `${cell(day, 'pay pay-start')}${cell(noteText, 'pay')}${payAmount}` : '';
        const rowKey = trip?.id != null ? `legacy-${trip.id}` : '';
        // SO-GON-02: khoản thu Sheet vào danh sách phiếu thu bên phải (giữ thứ tự Sheet), dòng chuyến chỉ còn ô chuyến.
        return { payRow: receipt ? `<tr class="pay-row legacy-pay">${sheetPay}</tr>` : '',
          tripRow: trip ? `<tr class="legacy${moved.has(rowKey) ? ' moved' : ''}"${rowKey ? ` data-row="${escape(rowKey)}"` : ''}>${tripCells}</tr>${movedTag(rowKey)}` : '' };
      });
    };
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
    // Mọi số tiền lấy nguyên từ GET; trang không cộng trừ tiền.
    function renderSnapshot(data) {
      snapshot = data;
      feeColumnIds = (data.fee_columns ?? []).map(column => Number(column.fee_type_id));
      useLiveColumns(feeColumnIds.map(feeTypeName));
      const updated = document.querySelector('#updated-at');
      if (updated?.id === 'updated-at') updated.textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`;
      sheetRefresh?.paint();
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
        ...(data.receipts ?? []).map(item => ({ month: item.date })),
        ...sheetRows.filter(item => item.sync_state === 'NEW' || !item.existing_id).map(item => ({ month: item.event_date }))]) {
        const key = monthKey(row.month);
        if (key && !groups.some(group => monthKey(group.month) === key)) groups.push({ month: `${key}-01`, placeholder: true });
      }
      groups.sort((a, b) => monthKey(a.month).localeCompare(monthKey(b.month)));
      const offsetAttrs = receipt => receipt.offset_pair_id == null ? ''
        : ` data-pair="${escape(receipt.offset_pair_id)}" data-other="${escape(receipt.counterparty_customer_id)}" data-other-name="${escape(receipt.counterparty_name)}"`;
      const offsetLink = receipt => receipt.offset_pair_id == null || receipt.voided_by_event != null ? ''
        : `<a class="offset-link" href="/so-khach-v7-live.html?customer=${encodeURIComponent(receipt.counterparty_customer_id)}">${receipt.outgoing ? 'sang' : 'từ'} ${escape(receipt.counterparty_name)}</a>`;
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
        // DA-THU-01: phiếu nằm ở tháng của ngày thu, đủ số tiền một lần (như Sheet); phần trừ nợ từng tháng chỉ ghi chữ nhỏ.
        const received = (data.receipts ?? []).filter(row => monthKey(row.date) === key).map(row => {
          const lines = (row.allocations ?? []).filter(line => row.voided_by_event != null
            ? line.superseded_by_event === row.voided_by_event : line.superseded_by_event === null);
          return { ...row, lines, line: { amount_vnd: row.amount_vnd, kind: lines[0]?.kind } };
        });
        const receipts = [...received, ...(outgoingByMonth.get(key) ?? [])];
        const adjustments = (data.adjustments ?? []).filter(row => monthKey(row.month) === key);
        const locked = lockFlags.has(key) ? lockFlags.get(key) : key !== openKey;
        // SO-GON-02 (29/10/2026, phương án A): chuyến bên trái, phiếu thu là danh sách riêng bên phải — không chung hàng,
        // để không đọc nhầm "chuyến này trả số tiền này". Danh sách: khoản thu Sheet (thứ tự Sheet), phiếu web, hàng nhập, phiếu đã hủy gom cuối.
        const legacy = legacyLines(historical.get(key) ?? [], locked);
        // Phiếu thu vẫn nhập trong tháng khóa; bảng nhập chuyến chỉ có khi mở khóa.
        const entryHere = active;
        const draftHere = active && !locked;
        // STT chuyến web nối tiếp các dòng chuyến từ Sheet của tháng (dòng Sheet vẽ trước, như thứ tự trên Sheet).
        const sttBase = new Set((historical.get(key) ?? []).filter(row => row.kind !== 'receipt').map(row => row.display?.row)).size;
        const referenceInline = receipt => {
          const voided = receipt.voided_by_event != null;
          // Phiếu chưa có tham chiếu chỉ còn dấu "+" nhỏ để thêm (bấm như cũ); có thì ghi "Tham chiếu: …".
          return receipt.reference
            ? `<small class="receipt receipt-edit receipt-ref${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="reference" tabindex="${voided ? '-1' : '0'}" role="button" aria-label="Sửa tham chiếu ${escape(receipt.pid)}">Tham chiếu: ${escape(receipt.reference)}</small>`
            : `<small class="receipt receipt-edit receipt-ref empty" data-pid="${escape(receipt.pid)}" data-field="reference" tabindex="0" role="button" aria-label="Thêm tham chiếu ${escape(receipt.pid)}" title="Thêm tham chiếu">+</small>`;
        };
        // Chỉ ghi khi phiếu trừ nợ tháng khác tháng của ngày thu hoặc chia nhiều tháng.
        const allocationInline = receipt => {
          const lines = receipt.voided_by_event == null ? receipt.lines ?? [] : [];
          if (!lines.length || lines.every(line => monthKey(line.month) === key)) return '';
          const parts = lines.map(line => `T${monthLabel(monthKey(line.month))}${lines.length > 1 ? ` ${fmt(line.amount_vnd)}` : ''}`);
          return `<small class="receipt-allocation">Trừ nợ ${parts.map(escape).join(' · ')}</small>`;
        };
        const payCells = (receipt, entry) => {
          const voided = receipt?.voided_by_event != null;
          const dateCell = receipt ? `<td class="pay pay-start receipt receipt-edit${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="date"${offsetAttrs(receipt)} tabindex="${voided ? '-1' : '0'}">${escape(dateText(receipt.date))}</td>` : `<td class="pay pay-start">${entry ? '<input class="empty-entry receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric"><span class="cell-error receipt-date-error" role="status"></span>' : ''}</td>`;
          const methodCell = receipt?.offset_pair_id != null ? `<td class="pay offset-method${voided ? ' voided-method' : ''}">${escape(voided ? 'ĐÃ HỦY' : receipt.line.kind === 'advance' ? 'ỨNG TRƯỚC' : 'CẤN TRỪ')}${offsetLink(receipt)}</td>` : receipt ? `<td class="pay receipt receipt-edit${voided ? ' voided-method' : ''}" data-pid="${escape(receipt.pid)}" data-field="method" tabindex="${voided ? '-1' : '0'}">${escape(voided ? 'ĐÃ HỦY' : receipt.line.kind === 'advance' ? 'ỨNG TRƯỚC' : receipt.method)}</td>` : `<td class="pay">${entry ? `<select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${method}</option>`).join('')}</select>` : ''}</td>`;
          const amountCell = receipt ? `<td class="pay num receipt${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}"${offsetAttrs(receipt)} tabindex="${voided ? '-1' : '0'}">${fmt(receipt.line.amount_vnd)}${receipt.outgoing ? '' : referenceInline(receipt)}${allocationInline(receipt)}</td>` : `<td class="pay num">${entry ? '<input class="empty-entry receipt-amount" aria-label="Số tiền trả" inputmode="numeric"><span class="cell-error receipt-amount-error" role="status"></span><input class="receipt-reference" aria-label="Tham chiếu" maxlength="500" placeholder="Tham chiếu (tùy chọn)">' : ''}</td>`;
          return dateCell + methodCell + amountCell;
        };
        const webRow = (trip, index) => {
          const pending = trip?.status === 'pending_review';
          const info = !locked && trip?.info_editable === true;
          const infoCells = info
            ? ['container', 'carrier', 'shipper', 'event_date', 'origin', 'destination'].map(field =>
              infoCell('trip', trip.id, field, field === 'event_date' ? dateText(trip.event_date) : trip[field] ?? '')).join('')
            : `${cell(trip?.container ?? '')}${cell(trip?.carrier ?? '')}${cell(trip?.shipper ?? '')}${cell(dateText(trip?.event_date))}${cell(trip?.origin ?? '')}${cell(trip?.destination ?? '')}`;
          const rowKey = trip ? `trip-${trip.id}` : '';
          const feeEditable = !locked && trip?.editable === true && trip.status === 'confirmed';
          const what = trip?.container || 'phí lẻ';
          return `<tr${rowKey ? ` data-row="${rowKey}"` : ''}${moved.has(rowKey) ? ' class="moved"' : ''}>${info ? deleteCell('trip', trip.id, trip.is_fee_only ? '–' : sttBase + index + 1, `chuyến ${what}`, feePick(`trip:${trip.id}`, what, feeEditable)) : trip && !trip.is_fee_only ? cell(sttBase + index + 1) : empty()}
            ${infoCells}
            ${pending || trip?.status === 'rejected' || locked ? num(trip?.is_missing_price ? trip.note === 'Chuyến đồng bộ' ? '' : 'chưa có giá' : fmt(trip?.unit_price_vnd)) : trip ? `<td class="num editable ${trip.is_missing_price ? 'missing' : ''}" data-trip="${trip.id}" data-field="unit_price_vnd" tabindex="0" role="button" aria-label="Sửa đơn giá chuyến ${index + 1}">${trip.is_missing_price ? trip.note === 'Chuyến đồng bộ' ? '' : 'chưa có giá' : fmt(trip.unit_price_vnd)}</td>` : empty('num')}
            ${trip ? feeCells(`trip:${trip.id}`, what, trip.fee_lines, feeEditable) : feeEmpty()}
            ${!trip ? empty('num') : pending && locked ? num('CHỜ KIỂM') : pending ? `<td class="num review-cell"><button type="button" class="review-open" data-trip="${trip.id}" aria-expanded="false" aria-label="Kết luận chuyến ${escape(trip.container)} đang CHỜ KIỂM">CHỜ KIỂM</button></td>` : trip.status === 'rejected' ? '<td class="num trip-rejected">ĐÃ LOẠI</td>' : num(fmt(trip.amount_vnd))}
            </tr>${movedTag(rowKey)}`;
        };
        const tripRows = legacy.map(line => line.tripRow).join('') + trips.map((trip, index) => webRow(trip, index)).join('');
        const kept = receipts.filter(row => row.voided_by_event == null);
        const voided = receipts.filter(row => row.voided_by_event != null);
        // Audit P0 29/10/2026: phiếu đã hủy không chiếm chỗ phiếu thật — gom một dòng mờ, bấm Xem mới hiện từng phiếu.
        const voidOpen = openVoided.has(key);
        const voidRows = voided.length ? `<tr class="void-summary"><td colspan="3">${voided.length} phiếu đã hủy, không tính tiền<button type="button" class="void-toggle" data-month="${escape(key)}" aria-expanded="${voidOpen}">${voidOpen ? 'Ẩn' : 'Xem'}</button></td></tr>`
          + (voidOpen ? voided.map(row => `<tr class="void-trace"><td colspan="3"><s>${fmt(row.line.amount_vnd)}</s> · ${[escape(dateText(row.date)), row.outgoing ? '' : `hủy ${escape(dateText(row.voided_on))}`, escape(row.void_reason)].filter(Boolean).join(' · ')}</td></tr>`).join('') : '') : '';
        const payRows = legacy.map(line => line.payRow).join('') + kept.map(receipt => `<tr class="pay-row">${payCells(receipt, false)}</tr>`).join('')
          + (entryHere ? `<tr class="pay-row pay-entry">${payCells(undefined, true)}</tr>` : '') + voidRows;
        const lines = `<tr class="month-body"><td class="trip-side" colspan="${tripCols()}"><table class="ledger-inner trip-list"><colgroup>${colTags(0, tripCols())}</colgroup><tbody>${tripRows}</tbody></table></td>`
          + `<td class="pay-side pay-start" colspan="3"><div class="pay-stick"><table class="ledger-inner pay-list" aria-label="Tiền khách trả tháng ${monthLabel(key)}"><colgroup>${colTags(tripCols(), labels.length)}</colgroup><tbody>${payRows}</tbody></table></div></td></tr>`;
        const sheetLines = sheetPending.map(row => `<tr class="${row.sync_state === 'NEW' ? 'sheet-new' : 'sheet-conflict'}">
          ${empty()}<td>${escape(row.container)}<small>${row.sync_state === 'NEW' ? 'CHỜ DUYỆT' : `KHÁC: ${conflictFields(row)}`}</small></td>${cell(row.carrier)}${cell(row.shipper)}${cell(dateText(row.event_date))}${cell(row.origin)}${cell(row.destination)}
          ${empty('num')}${feeEmpty()}${num('–')}${empty('pay pay-start')}${empty('pay')}${empty('pay num')}
          </tr>`).join('');
        // Góp ý 23/10/2026: không hiện dòng số dư đầu, dòng "Theo sổ gốc" và dòng chênh do sửa dòng cũ.
        // Các dòng đó vẫn nằm trong số tiền: dòng Tổng tháng lấy phát sinh/đã thu của Sheet từ server (DA-THU-01), chênh ghi ở Lịch sử.
        const adjustmentRows = adjustments.filter(row => row.legacy_row_id == null).map(row => `<tr class="adjustment"><td colspan="${tripCols() - 1}">Điều chỉnh ${row.trip_id ? 'chuyến' : 'cả tháng'}${row.note ? ` · ${escape(row.note)}` : ''}</td>${num(fmt(row.amount_vnd))}<td class="pay pay-start" colspan="3"></td></tr>`).join('');
        const totals = { chargesVnd: item.charges_vnd ?? '0', receivedVnd: item.received_vnd ?? '0' };
        // Dòng Tổng tháng: tổng từng cột phụ phí (chuyến đã tính tiền và dòng sổ gốc của tháng).
        const feeTotals = model.feeColumnTotals([...(historical.get(key) ?? []).filter(row => row.kind === 'trip'),
          ...trips.filter(trip => trip.status === 'confirmed')].map(row => row.fee_lines ?? []), feeColumnIds);
        const feeTotalCells = [...feeTotals.own, feeTotals.otherVnd].map(value => num(value === null ? '' : model.formatVnd(value), 'fee')).join('');
        const ghostRows = ghosts.map((ghost, index) => ghost.month !== key ? '' : `<tr class="ghost"><td colspan="${labels.length}">↪ ${escape(ghost.container || 'Chuyến')} (ngày cũ ${escape(dateText(ghost.oldIso))}) đã chuyển sang tháng ${monthLabel(ghost.to)}<button type="button" class="ghost-go" data-row="${escape(`${ghost.kind}-${ghost.id}`)}">Xem</button><button type="button" class="ghost-undo" data-ghost="${index}">Hoàn tác</button></td></tr>`).join('');
        return `<section id="thang-${escape(key)}"><table class="ledger${locked ? ' locked' : ''}" aria-label="Sổ khách tháng ${monthLabel(key)}"><colgroup>${widths}</colgroup><tbody>
          <tr class="month"><th colspan="${labels.length}" scope="rowgroup"><span class="month-title">THÁNG ${monthLabel(key)}<button class="month-lock" data-month="${escape(item.month)}" aria-label="${locked ? 'Mở khóa' : 'Khóa'} tháng ${monthLabel(key)}" title="${locked ? 'Đã khóa' : 'Đang mở'}" aria-pressed="${!locked}" ${active ? '' : 'disabled'}>${locked ? '🔒' : '🔓'}</button><em class="month-stats"><span>Nợ các tháng trước: <b>${fmt(item.prior_months_vnd)}</b></span><span>Phát sinh: <b>${fmt(totals.chargesVnd)}</b></span><span>Đã thu: <b>${fmt(totals.receivedVnd)}</b></span><span class="month-end">Còn nợ cuối tháng: <b>${fmt(item.end_of_month_vnd)}</b></span></em></span></th></tr>
          ${lines}${sheetLines}${adjustmentRows}${ghostRows}${draftHere ? draftGrid(key) : ''}
          <tr class="subtotal"><td colspan="8">Tổng tháng ${monthLabel(key)} <button class="add-month-adjustment" data-month="${escape(item.month)}" ${active && !locked ? '' : 'disabled'}>+ Điều chỉnh cả tháng</button></td>${feeTotalCells}${num(fmt(totals.chargesVnd))}<td class="pay pay-start">Đã thu<br>Còn nợ</td><td class="pay num subtotal-pay" colspan="2">${fmt(totals.receivedVnd)}<br><span class="month-end-amount">${fmt(item.end_of_month_vnd)}</span></td></tr><tr class="spacer"><td colspan="${labels.length}"></td></tr></tbody></table></section>`;
      };
      const sheetNotice = data.sheet_sync?.unavailable ? 'Không đọc được chuyến mới từ Sheet.' : '';
      const noticeHtml = `<p class="live-notice" role="status" style="padding:8px;background:#fff3d6" ${(message && message !== 'Đã lưu.') || !active || sheetNotice ? '' : 'hidden'}>${escape(message || sheetNotice || (active ? '' : 'Khách chưa có số dư đầu hiệu lực. Chưa thể ghi.'))}</p><button class="retry-command" ${api.hasPending() ? '' : 'hidden'}>Thử lại thao tác vừa gửi</button>`;
      const newCount = data.sheet_sync?.new_count ?? 0;
      renderShell({ customer: live.customerName(customerId) ?? `#${customerId}`, total: fmt(data.total_outstanding_vnd), notice: noticeHtml,
        sheetButton: `<button class="fee-settings-open" aria-haspopup="dialog">Cài đặt phụ phí</button>`
          + (newCount ? `<button class="sheet-approve" ${active ? '' : 'disabled'}>Duyệt ${newCount} chuyến mới</button>` : '')
          + (active && data.sheet_prices?.ready_count ? `<button class="price-approve">Ghi ${data.sheet_prices.ready_count} giá từ Sheet</button>` : ''),
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
      decoratePrices(data, active);
      markLoc(data);
      ctx.feeAfterRender?.();
    }
    // Mở từ "Việc cần làm" ở Tổng quan: ?loc=thieu-gia|cho-kiem tô các chuyến cần xử lý và có nút
    // nhảy tới từng dòng. Không ẩn dòng nào, để số cộng trong tháng vẫn đọc đúng như sổ.
    const LOC = {
      'thieu-gia': ['chuyến thiếu đơn giá', trip => trip.status === 'confirmed' && trip.is_missing_price === true],
      'cho-kiem': ['chuyến chờ kiểm', trip => trip.status === 'pending_review'],
    };
    let locKind = new URLSearchParams(location.search).get('loc');
    let locJumped = false;
    let locIndex = 0;
    function markLoc(data) {
      const rule = Object.hasOwn(LOC, locKind ?? '') ? LOC[locKind] : null;
      if (!rule) return;
      const hits = (data.trips ?? []).filter(trip => !trip.deleted && rule[1](trip))
        .map(trip => root.querySelector(`[data-row="trip-${trip.id}"]`)).filter(Boolean);
      hits.forEach(row => row.classList.add('loc-hit'));
      const bar = document.createElement('div');
      bar.className = 'loc-bar';
      bar.setAttribute('role', 'status');
      bar.innerHTML = hits.length
        ? `<span><b>${hits.length} ${rule[0]}</b> được tô vàng trong sổ.</span><button type="button" class="loc-next">Đến dòng tiếp ›</button><button type="button" class="loc-clear">Bỏ đánh dấu</button>`
        : `<span>Sổ này không còn ${rule[0]}.</span><a href="/dashboard-v7.html">Về Tổng quan</a><button type="button" class="loc-clear">Đóng</button>`;
      root.querySelector('.layout')?.before(bar);
      // Sổ có thể vẽ lại (tự cập nhật) giữa hai lần bấm: luôn đọc dòng đang có trên màn hình.
      const go = index => {
        const rows = [...root.querySelectorAll('tr.loc-hit')];
        if (!rows.length) return;
        locIndex = index % rows.length;
        rows[locIndex].scrollIntoView({ block: 'center' });
      };
      bar.querySelector('.loc-next')?.addEventListener('click', () => go(locIndex + 1));
      bar.querySelector('.loc-clear').addEventListener('click', () => {
        locKind = null;
        const query = new URLSearchParams(location.search); query.delete('loc');
        window.history.replaceState(null, '', `${location.pathname}?${query}`);   // `history` ở đây là danh sách Lịch sử của sổ
        root.querySelectorAll('tr.loc-hit').forEach(row => row.classList.remove('loc-hit'));
        root.querySelectorAll('.loc-bar').forEach(node => node.remove());
      });
      if (!locJumped && hits.length) { locJumped = true; go(0); }
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
    // Các phần màn hình ở so-khach-v7-*-ui.js (nạp trước file này) dùng chung phạm vi qua ctx;
    // cài theo đúng thứ tự cũ để trình nghe sự kiện đăng ký như trước khi tách.
    // Dòng hỏi/chi tiết chèn sau một hàng trải hết bảng chứa hàng đó (bảng chuyến, danh sách phiếu thu 3 cột, cả sổ).
    const spanOf = row => (typeof row?.closest === 'function' && row.closest('table')?.querySelector(':scope > colgroup')?.children.length) || labels.length;
    const ctx = { root, model, api, live, customerId, escape, fmt, spanOf, dateText, dateInput, monthKey, monthLabel, liveOpenMonth, methods, fieldNames, moved, ghosts, sheetFieldLabel, resolvableSheetFields, moneyText, referenceFields, showNotice, renderSnapshot, redraw, submit,
      columnCount: () => labels.length, feeOwnCount: () => ownCount, feeTypeName,
      get feeTypes() { return feeTypes; }, set feeTypes(value) { feeTypes = value; },
      get feeColumnIds() { return feeColumnIds; },
      get snapshot() { return snapshot; }, get rendering() { return rendering; },
      get historyOpen() { return historyOpen; }, set historyOpen(value) { historyOpen = value; } };
    for (const name of ['history', 'sheet', 'offset', 'edit', 'draft', 'fee']) window.SoKhachV7LiveParts[name]?.(ctx);
    const { eventLabels, describeEvent, eventTime, decoratePrices, offsetState, sourceRowHtml, renderSourceCell, draftsBy, draftGrid } = ctx;
    // Đổi khổ màn qua mốc 1878px thì bề rộng cột tính lại (cột phụ phí riêng lấy chỗ khác nhau ở hai khổ).
    if (typeof matchMedia === 'function') matchMedia('(max-width:1877px)').addEventListener?.('change', () => redraw());
    root.addEventListener('click', event => {
      const toggle = event.target.closest('.void-toggle');
      if (!toggle) return;
      if (!openVoided.delete(toggle.dataset.month)) openVoided.add(toggle.dataset.month);
      redraw();
      if (typeof CSS !== 'undefined') root.querySelector(`.void-toggle[data-month="${CSS.escape(toggle.dataset.month)}"]`)?.focus();
    });
    root.innerHTML = '<p role="status">Đang đọc sổ khách…</p>';
    let refreshing = true;
    api.read().catch(error => { root.innerHTML = `<p role="alert">${escape(error.message)}</p>`; }).finally(() => { refreshing = false; });
    const busy = () => api.hasPending() || draftsBy.size || ctx.feeBusy?.() || root.querySelector('input:focus,textarea:focus,select:focus,.offset-backdrop,.sheet-detail,.review-prompt,.month-adjustment-input,.void-prompt,.move-ask,.delete-prompt,.price-panel,.history-panel:not([hidden])')
      || [...root.querySelectorAll('.receipt-method')].some(input => input.value !== 'THU TIỀN')
      || [...root.querySelectorAll('.draft-input,.receipt-date,.receipt-amount,.receipt-reference,.info-input')].some(input => input.value.trim());
    async function refresh(manual = false) {
      if (refreshing) return;
      if (busy()) {
        const updated = document.querySelector('#updated-at');
        if (updated?.id === 'updated-at') updated.textContent = 'Tạm dừng tự cập nhật khi đang nhập hoặc xem chi tiết';
        if (manual) showNotice('Đóng chi tiết hoặc lưu/bỏ nháp trước khi làm mới.');
        return;
      }
      refreshing = true;
      try { await api.read(); } catch { showNotice('Không tải được sổ mới. Thử lại.'); }
      finally { refreshing = false; }
      if (manual) await sheetRefresh?.trigger();
      else await sheetRefresh?.load();
    }
    const refreshButton = document.querySelector('#refresh-data');
    if (globalThis.SheetRefresh) {
      sheetRefresh = globalThis.SheetRefresh.create({ node: document.querySelector('#updated-at'), button: refreshButton,
        onDone: () => (busy() || refreshing ? undefined : refresh()) });
      sheetRefresh.load();
    }
    if (refreshButton?.id === 'refresh-data') refreshButton.addEventListener('click', () => refresh(true));
    setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
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
