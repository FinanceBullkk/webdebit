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
  const monthLabel = key => `${Number(key.slice(5))}/${key.slice(0, 4)}`;
  const money = amount => amount === null || amount === undefined ? '–' : model.formatVnd(amount);
  const fieldMoney = amount => amount === null || amount === undefined ? '–' : model.formatVnd(model.parseVnd(amount));
  const outstanding = model?.formatOutstanding;
  const labels = ['STT', 'Số container', 'Hãng tàu / số xe', 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá', 'Phụ phí', 'Thành tiền', 'Ngày trả', 'Hình thức', 'Số tiền trả', 'Còn nợ cộng dồn', 'Vết'];
  const wide = [52, 148, 104, 104, 118, 118, 128, 116, 148, 112, 112, 150, 158, 96];
  const widths = wide.map((width, index) => `<col style="width:${width}px" class="col-${index}">`).join('');
  const cell = (value, classes = '') => `<td class="${classes}">${escape(value)}</td>`;
  const num = (value, classes = '') => cell(value, `num ${classes}`);
  const empty = (classes = '') => `<td class="${classes}"></td>`;
  const methods = ['THU TIỀN', 'CẤN TRỪ', 'ỨNG TRƯỚC', 'KHÁC'];
  let notice = '';
  let voidPrompt = null;

  function log(type, description, reason = '') {
    history.unshift({ time: new Date().toLocaleString('vi-VN'), type, description, reason });
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

  function renderLine(trip, receipt, index, month) {
    const result = trip ? model.tripAmount(trip) : null;
    const feeOnly = result?.isFeeOnly;
    const missing = result?.isMissingPrice;
    const open = month.key === openMonth;
    const cells = [
      trip && !feeOnly ? cell(index + 1) : empty(),
      cell(trip?.container ?? (month.opening ? 'Nợ cũ chuyển sang sổ mới' : feeOnly ? 'Phí lẻ' : '')),
      cell(trip?.carrier ?? ''), cell(trip?.date ?? ''), cell(trip?.from ?? ''), cell(trip?.to ?? ''),
      trip ? editCell(missing ? 'chưa có giá' : fieldMoney(trip.unitPriceVnd), 'unitPriceVnd', index, month, missing ? 'missing' : '') : empty('num'),
      trip ? editCell(fieldMoney(trip.otherFeeVnd), 'otherFeeVnd', index, month) : empty('num'),
      trip ? num(missing ? '–' : money(result.amountVnd)) : empty('num'),
      receipt ? `<td class="pay pay-start receipt receipt-edit ${receipt.voided !== null ? 'voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="date" tabindex="${receipt.voided === null ? '0' : '-1'}">${escape(receipt.date)}</td>`
        : `<td class="pay pay-start">${open && index === month.receipts.length ? '<input class="empty-entry receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric"><span class="cell-error receipt-date-error" role="status"></span>' : ''}</td>`,
      receipt ? `<td class="pay receipt receipt-edit ${receipt.voided !== null ? 'voided-method' : ''}" data-pid="${escape(receipt.pid)}" data-field="method" tabindex="${receipt.voided === null ? '0' : '-1'}">${escape(receipt.voided !== null ? 'ĐÃ HỦY' : receipt.method)}</td>`
        : `<td class="pay">${open && index === month.receipts.length ? `<select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${method}</option>`).join('')}</select>` : ''}</td>`,
      receipt ? `<td class="pay num receipt ${receipt.voided !== null ? 'voided' : ''}" data-pid="${escape(receipt.pid)}" tabindex="${receipt.voided === null ? '0' : '-1'}">${escape(fieldMoney(receipt.amountVnd))}</td>`
        : `<td class="pay num">${open && index === month.receipts.length ? '<input class="empty-entry receipt-amount" aria-label="Số tiền trả" inputmode="numeric"><span class="cell-error receipt-amount-error" role="status"></span>' : ''}</td>`,
      empty('num'), trip ? cell(trip.src ?? '', 'source') : empty('source'),
    ];
    const adjustmentRows = (month.adjustments ?? []).filter(item => trip && item.lineId === (trip.id ?? `${month.key}#${index}`)).map(adjustment =>
      `<tr class="adjustment"><td colspan="8">Điều chỉnh chuyến ${index + 1} · <label>Ghi chú <input class="adjustment-note" data-month="${month.key}" data-adj="${escape(adjustment.adjId)}" aria-label="Ghi chú điều chỉnh chuyến ${index + 1}" value="${escape(adjustment.reason ?? '')}" placeholder="Tùy chọn, Enter lưu"></label></td>${num(money(model.adjustmentAmount(adjustment)))}<td class="pay pay-start" colspan="4"></td><td></td></tr>`).join('');
    return `<tr>${cells.join('')}</tr>${adjustmentRows}`;
  }

  function renderMonth(month, summary, _balance) {
    const label = monthLabel(month.key);
    const open = month.key === openMonth;
    const editable = model.isMonthOpen(locks, month.key);
    const badge = editable ? 'Đang mở' : 'Đã khóa';
    const lineCount = Math.max(month.trips.length, month.receipts.length + (open ? 1 : 0));
    const lines = Array.from({ length: lineCount }, (_, index) => renderLine(month.trips[index], month.receipts[index], index, month)).join('');
    const prompt = voidPrompt?.monthKey === month.key ? `<tr class="void-prompt"><td colspan="14">Hủy phiếu ${escape(voidPrompt.pid)} — ${money(voidPrompt.totalVnd)} (${voidPrompt.monthCount} tháng) <label>Lý do <input class="void-reason" aria-label="Lý do hủy phiếu"></label> <button class="confirm-void">Hủy phiếu</button> <button class="cancel-void">Bỏ qua</button><span class="cell-error void-error" role="status"></span></td></tr>` : '';
    const traces = model.voidedLines(book, month.key).map(line => `<tr class="void-trace"><td colspan="14">${money(line.amountVnd)} · ${escape(line.date)} · ${escape(line.voidedOn)} · ${escape(line.reason)}</td></tr>`).join('');
    const status = open && notice ? `<tr class="receipt-status"><td colspan="14" role="status">${escape(notice)}</td></tr>` : '';
    const paste = editable ? `<tr class="paste-row"><td colspan="9"><label>Dán các dòng từ Sheet vào đây <textarea class="paste-input" data-month="${month.key}" rows="2" aria-label="Dán các dòng từ Sheet vào đây"></textarea></label><span class="paste-error" role="status"></span></td><td class="pay pay-start" colspan="5"></td></tr>` : '';
    const monthAdjustments = (month.adjustments ?? []).filter(item => !item.lineId).map(item => `<tr class="adjustment month-adjustment"><td colspan="8">Điều chỉnh cả tháng${item.reason ? ` · ${escape(item.reason)}` : ''}</td>${num(money(model.adjustmentAmount(item)))}<td class="pay pay-start" colspan="5"></td></tr>`).join('');
    const input = monthPrompt === month.key ? `<tr class="month-adjustment-input"><td colspan="8">Điều chỉnh cả tháng · <label>Ghi chú <input class="month-note" aria-label="Ghi chú điều chỉnh cả tháng ${label}"></label></td><td><input class="month-amount" aria-label="Số điều chỉnh cả tháng ${label}" inputmode="decimal" placeholder="+5.000.000"><span class="cell-error month-error" role="status"></span></td><td class="pay pay-start" colspan="5"></td></tr>` : '';
    return `<section id="thang-${escape(month.key)}"><table class="ledger" aria-label="Sổ khách tháng ${label}"><colgroup>${widths}</colgroup><tbody><tr class="month"><th colspan="14" scope="rowgroup"><span class="month-title">THÁNG ${label}<button class="month-lock" data-month="${month.key}" aria-label="${editable ? 'Khóa' : 'Mở khóa'} tháng ${label}" aria-pressed="${editable}">${editable ? '🔓' : '🔒'}</button><span class="badge ${editable ? 'open' : ''}">${badge}</span><em>Nợ các tháng trước: ${outstanding(summary.carryVnd)}</em></span></th></tr>${lines}${monthAdjustments}${input}${prompt}${traces}${status}${paste}<tr class="subtotal"><td colspan="8">Cộng tháng ${label} (${summary.tripCount} chuyến) · Phát sinh <button class="add-month-adjustment" data-month="${month.key}">+ Điều chỉnh cả tháng</button></td>${num(money(summary.totalChargesVnd))}<td class="pay pay-start" colspan="2">Đã thu</td>${num(outstanding(summary.receivedVnd), 'pay')}${num(outstanding(summary.endOfMonthVnd))}${empty('source')}</tr><tr class="spacer"><td colspan="14"></td></tr></tbody></table></section>`;
  }

  function renderShell(view) {
    const scrollY = window.scrollY;
    root.innerHTML = `<div class="book-head"><h1>Sổ khách · ${escape(view.customer)}</h1><button class="history-toggle" aria-expanded="${historyOpen}" aria-controls="history-panel">Lịch sử</button><div class="head-item"><span>Từ tháng</span><strong>${view.firstMonth}</strong></div><div class="head-item"><span>Chờ xử lý</span><strong>${view.pending}</strong></div><div class="head-item total"><span>Tổng còn nợ (mọi tháng)</span><strong>${view.total}</strong></div></div>
    ${view.notice ?? ''}<div class="layout"><div class="ledger-book"><table class="ledger ledger-head" aria-label="Cột sổ khách"><colgroup>${widths}</colgroup><thead><tr class="group"><th colspan="9">CHUYẾN HÀNG · ô cam: chưa có giá, ngoài số dư</th><th colspan="3" class="group-pay">TIỀN KHÁCH TRẢ</th><th>NỢ</th><th class="source">NGUỒN</th></tr><tr class="columns">${labels.map((label, index) => `<th scope="col" class="${index >= 9 && index <= 11 ? 'pay ' : ''}${index === 9 ? 'pay-start ' : ''}${index === 13 ? 'source' : ''}">${escape(label)}</th>`).join('')}</tr></thead></table>${view.sections}</div>
    <nav class="months-nav" aria-label="Danh sách tháng"><h2>DANH SÁCH THÁNG</h2>${view.navigation}</nav></div><aside id="history-panel" class="history-panel" aria-label="Lịch sử thay đổi" ${historyOpen ? '' : 'hidden'}><header><h2>Lịch sử</h2><button class="history-close" aria-label="Đóng lịch sử">Đóng</button></header>${view.history}</aside>`;
    window.scrollTo(0, scrollY);
  }

  function render() {
    const chain = model.monthChain(book);
    const remaining = model.outstandingByMonth(book);
    const pending = model.pendingCounts(book);
    renderShell({ customer: book.customer, firstMonth: monthLabel(months[0].key),
      pending: `${pending.missingPrice} chuyến chưa có giá · ${pending.uncertainReceipts} khoản thu chưa chắc`,
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
    // Sheet history in the same 14 columns as the Sheet: a trip and a payment typed on the
    // same Sheet row share one line. Amounts come from the copy as digit strings; no maths here.
    // The loader resolves every serial date to one reading (dd/mm/yyyy); anything left here
    // is text typed in the Sheet ("da tt") and is shown as typed.
    const rawDay = value => value ?? '';
    const moneyCell = value => /^-?\d+$/.test(value ?? '') ? fmt(value) : (value ?? '');
    const legacyLines = rows => {
      const byRow = new Map();
      for (const row of rows) {
        const d = typeof row.display === 'object' && row.display !== null ? row.display : {};
        const line = byRow.get(d.row) ?? {};
        line[row.kind === 'receipt' ? 'receipt' : 'trip'] = { ...row, d };
        byRow.set(d.row, line);
      }
      return [...byRow.values()].map(({ trip, receipt }) => {
        const t = trip?.d ?? {}, r = receipt?.d ?? {};
        const tripCells = trip
          ? `${cell(String(t.stt ?? '').replace(/^(\d+)\.0+$/, '$1'))}${cell(t.container || 'Phí lẻ')}${cell(t.carrier ?? '')}${cell(t.date ? dateText(t.date) : rawDay(t.raw_date))}${cell(t.from ?? '')}${cell(t.to ?? '')}${!t.unit_price && (t.flags ?? []).includes('MISSING_PRICE') ? '<td class="num missing">chưa có giá</td>' : num(moneyCell(t.unit_price))}${num(moneyCell(t.fee_vnd))}${num(fmt(trip.source_total_vnd))}`
          : `${empty()}${empty()}${empty()}${empty()}${empty()}${empty()}${empty('num')}${empty('num')}${empty('num')}`;
        const payCells = receipt
          // Payment form is not inferred from the note (V7-MIG still open); show the note once.
          ? `${cell(r.raw_date ?? '', 'pay pay-start')}${cell(r.note && r.note !== r.raw_date ? r.note : '', 'pay')}${num(fmt(receipt.source_total_vnd), 'pay')}`
          : `${empty('pay pay-start')}${empty('pay')}${empty('pay num')}`;
        return `<tr class="legacy" title="Từ sổ gốc, đã nằm trong số dư đầu">${tripCells}${payCells}${empty('num')}${empty('source')}</tr>`;
      }).join('');
    };
    const eventLabels = { paste: 'Dán lô chuyến', price_edit: 'Sửa giá', adjust_trip: 'Điều chỉnh chuyến',
      adjust_month: 'Điều chỉnh cả tháng', receipt: 'Ghi thu', receipt_edit: 'Sửa ngày/hình thức phiếu',
      void: 'Hủy phiếu', reallocation: 'Phân bổ lại', import: 'Nhập số dư đầu' };
    const valueLabels = { amount_vnd: 'Số tiền', old_amount_vnd: 'Thành tiền trước', new_amount_vnd: 'Thành tiền sau',
      delta_vnd: 'Điều chỉnh', unit_price_vnd: 'Đơn giá', other_fee_vnd: 'Phụ phí', new_value_vnd: 'Giá trị mới',
      date: 'Ngày trả', event_date: 'Ngày chuyến', month: 'Tháng', debt_month: 'Tháng', pid: 'Phiếu',
      method: 'Hình thức', container: 'Container', carrier: 'Hãng tàu / số xe', from: 'Nơi đi', to: 'Nơi đến',
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
    // Mọi số tiền lấy nguyên từ GET; trang không cộng trừ tiền.
    function renderSnapshot(data) {
      snapshot = data;
      const active = data.status === 'active';
      // Tháng hiện tại và cờ khóa theo server (giờ VN); đồng hồ máy chỉ dùng khi server cũ chưa trả.
      const openKey = monthKey(data.today_month) || liveOpenMonth;
      const lockFlags = new Map((data.month_locks ?? []).map(row => [monthKey(row.month), row.locked]));
      const groups = [...(data.months ?? [])];
      // Tháng hiện tại chưa có dữ liệu vẫn cần khối để ghi thu (trừ nợ cũ trước) và dán chuyến.
      if (active && !groups.some(item => monthKey(item.month) === openKey)) {
        groups.push({ month: `${openKey}-01`, placeholder: true });
        groups.sort((a, b) => monthKey(a.month).localeCompare(monthKey(b.month)));
      }
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
        const receipts = (data.receipts ?? []).flatMap(row => (row.allocations ?? [])
          .filter(line => monthKey(line.month) === key && (row.voided_by_event != null
            ? line.superseded_by_event === row.voided_by_event : line.superseded_by_event === null))
          .map(line => ({ ...row, line })));
        const opening = (data.opening ?? []).filter(row => monthKey(row.month) === key);
        const adjustments = (data.adjustments ?? []).filter(row => monthKey(row.month) === key);
        const locked = lockFlags.has(key) ? lockFlags.get(key) : key !== openKey;
        const n = Math.max(trips.length, receipts.length + (active && key === openKey ? 1 : 0), 1);
        const lines = Array.from({ length: n }, (_, index) => {
          const trip = trips[index], receipt = receipts[index];
          const voided = receipt?.voided_by_event != null;
          return `<tr>${trip && !trip.is_fee_only ? cell(index + 1) : empty()}
            ${cell(trip?.container ?? '')}${cell(trip?.carrier ?? '')}${cell(dateText(trip?.event_date))}${cell(trip?.origin ?? '')}${cell(trip?.destination ?? '')}
            ${trip ? `<td class="num editable ${trip.is_missing_price ? 'missing' : ''}" data-trip="${trip.id}" data-field="unit_price_vnd" tabindex="0" role="button" aria-label="Sửa đơn giá chuyến ${index + 1}">${trip.is_missing_price ? 'chưa có giá' : fmt(trip.unit_price_vnd)}</td>` : empty('num')}
            ${trip ? `<td class="num editable" data-trip="${trip.id}" data-field="other_fee_vnd" tabindex="0" role="button" aria-label="Sửa phụ phí chuyến ${index + 1}">${fmt(trip.other_fee_vnd)}</td>` : empty('num')}
            ${trip ? num(fmt(trip.amount_vnd)) : empty('num')}
            ${receipt ? `<td class="pay pay-start receipt receipt-edit${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="date" tabindex="${voided ? '-1' : '0'}">${escape(dateText(receipt.date))}</td>` : `<td class="pay pay-start">${active && key === openKey && index === receipts.length ? '<input class="empty-entry receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric"><span class="cell-error receipt-date-error" role="status"></span>' : ''}</td>`}
            ${receipt ? `<td class="pay receipt receipt-edit${voided ? ' voided-method' : ''}" data-pid="${escape(receipt.pid)}" data-field="method" tabindex="${voided ? '-1' : '0'}">${escape(voided ? 'ĐÃ HỦY' : receipt.line.kind === 'advance' ? 'ỨNG TRƯỚC' : receipt.method)}</td>` : `<td class="pay">${active && key === openKey && index === receipts.length ? `<select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${method}</option>`).join('')}</select>` : ''}</td>`}
            ${receipt ? `<td class="pay num receipt${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" tabindex="${voided ? '-1' : '0'}">${fmt(receipt.line.amount_vnd)}</td>` : `<td class="pay num">${active && key === openKey && index === receipts.length ? '<input class="empty-entry receipt-amount" aria-label="Số tiền trả" inputmode="numeric">' : ''}</td>`}
            ${empty('num')}${cell(trip?.src ?? '', 'source')}</tr>`;
        }).join('');
        const openingRows = opening.map(row => `<tr class="adjustment"><td colspan="8">Nợ cũ chuyển sang sổ mới</td>${num(fmt(row.amount_vnd))}<td class="pay pay-start" colspan="5">Số dư đầu đã nằm trong tổng, không cộng lần nữa</td></tr>`).join('');
        const adjustmentRows = adjustments.map(row => `<tr class="adjustment"><td colspan="8">Điều chỉnh ${row.trip_id ? 'chuyến' : 'cả tháng'}${row.note ? ` · ${escape(row.note)}` : ''}</td>${num(fmt(row.amount_vnd))}<td class="pay pay-start" colspan="5"></td></tr>`).join('');
        const voidRows = receipts.filter(row => row.voided_by_event != null).map(row =>
          `<tr class="void-trace"><td colspan="14">${fmt(row.line.amount_vnd)} · ${escape(dateText(row.date))} · ${escape(dateText(row.voided_on))} · ${escape(row.void_reason)}</td></tr>`).join('');
        const history = historical.get(key) ?? [];
        // Option (b), 20/10/2026: Sheet figures beside the ledger subtotal, for comparison only.
        const source = sourceFigures.get(key);
        const sourceRow = history.length && source && (source.source_charge_vnd != null || source.source_cumulative_vnd != null)
          ? `<tr class="source-total"><td colspan="8">Theo sổ gốc (để đối chiếu, đã nằm trong số dư đầu) · Phát sinh</td>${num(fmt(source.source_charge_vnd))}<td class="pay pay-start" colspan="2">Đã thu</td>${num(fmt(source.source_receipt_vnd), 'pay')}${num(fmt(source.source_cumulative_vnd))}${empty('source')}</tr>`
          : '';
        const legacyRows = history.length ? `<tr class="legacy-caption"><td colspan="14">Từ sổ gốc · đã nằm trong số dư đầu, chỉ để đối chiếu, không cộng lại</td></tr>${legacyLines(history)}` : '';
        const paste = active && !locked ? `<tr class="paste-row"><td colspan="9"><label>Dán các dòng từ Sheet vào đây <textarea class="paste-input" data-month="${key}" rows="2" aria-label="Dán các dòng từ Sheet vào đây"></textarea></label><span class="paste-error" role="status"></span></td><td class="pay pay-start" colspan="5"></td></tr>` : '';
        return `<section id="thang-${escape(key)}"><table class="ledger" aria-label="Sổ khách tháng ${monthLabel(key)}"><colgroup>${widths}</colgroup><tbody>
          <tr class="month"><th colspan="14" scope="rowgroup"><span class="month-title">THÁNG ${monthLabel(key)}<button class="month-lock" data-month="${escape(item.month)}" aria-label="${locked ? 'Mở khóa' : 'Khóa'} tháng ${monthLabel(key)}" aria-pressed="${!locked}" ${active ? '' : 'disabled'}>${locked ? '🔒' : '🔓'}</button><span class="badge ${locked ? '' : 'open'}">${locked ? 'Đã khóa' : 'Đang mở'}</span><em>Nợ các tháng trước: ${fmt(item.prior_months_vnd)}</em></span></th></tr>
          ${openingRows}${lines}${adjustmentRows}${voidRows}${legacyRows}${paste}
          <tr class="subtotal"><td colspan="8">Cộng tháng ${monthLabel(key)} (${trips.length} chuyến) · Phát sinh <button class="add-month-adjustment" data-month="${escape(item.month)}" ${active ? '' : 'disabled'}>+ Điều chỉnh cả tháng</button></td>${num(fmt(item.charges_vnd))}<td class="pay pay-start" colspan="2">Đã thu</td>${num(fmt(item.received_vnd), 'pay')}${num(fmt(item.end_of_month_vnd))}${empty('source')}</tr>${sourceRow}<tr class="spacer"><td colspan="14"></td></tr></tbody></table></section>`;
      };
      const noticeHtml = `<p class="live-notice" role="status" style="padding:8px;background:#fff3d6" ${message || !active ? '' : 'hidden'}>${escape(message || (active ? '' : 'Khách chưa có số dư đầu hiệu lực. Chưa thể ghi.'))}</p><button class="retry-command" ${api.hasPending() ? '' : 'hidden'}>Thử lại thao tác vừa gửi</button>`;
      renderShell({ customer: live.customerName(customerId) ?? `#${customerId}`, firstMonth: groups.length ? monthLabel(monthKey(groups[0].month)) : '–',
        pending: `${data.pending_count ?? '–'} chuyến chưa có giá`, total: fmt(data.total_outstanding_vnd), notice: noticeHtml,
        sections: groups.map(section).join(''), navigation: groups.map(item => `<a href="#thang-${escape(monthKey(item.month))}"><span>${monthLabel(monthKey(item.month))}</span><small>${fmt(item.outstanding_vnd)}</small></a>`).join(''),
        history: (data.events ?? []).length ? `<ol>${data.events.map(event => `<li><time>${escape(eventTime(event.at))}</time><span>${escape(event.actor ?? 'Chưa rõ người thao tác')}</span><strong>${escape(Object.hasOwn(eventLabels, event.kind) ? eventLabels[event.kind] : 'Thao tác khác')}</strong><p>${escape(describeEvent(event))}</p><small>Ghi chú/lý do: ${escape(event.after?.note || event.after?.void_reason || event.after?.trips?.map(trip => trip.note).filter(Boolean).join('; ') || event.before?.note || '–')}</small></li>`).join('')}</ol>` : '<p>Chưa có thay đổi nào</p>' });
    }
    function showNotice(value) {
      message = value;
      const status = root.querySelector('.live-notice');
      if (status) { status.textContent = value; status.hidden = !value; }
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
    root.addEventListener('click', async event => {
      if (event.target.closest('.history-toggle')) { historyOpen = !historyOpen; if (snapshot) renderSnapshot(snapshot); return; }
      if (event.target.closest('.history-close')) { historyOpen = false; if (snapshot) renderSnapshot(snapshot); return; }
      if (event.target.closest('.retry-command')) { await api.retry(); return; }
      const lock = event.target.closest('.month-lock');
      if (lock) { await submit('lock', { month: lock.dataset.month, locked: lock.getAttribute('aria-pressed') === 'true' }); return; }
      const add = event.target.closest('.add-month-adjustment');
      if (add) {
        const row = add.closest('tr');
        if (!row.previousElementSibling?.classList.contains('month-adjustment-input')) row.insertAdjacentHTML('beforebegin',
          `<tr class="month-adjustment-input" data-month="${escape(add.dataset.month)}"><td colspan="8">Điều chỉnh cả tháng · <label>Ghi chú <input class="month-note" aria-label="Ghi chú điều chỉnh cả tháng"></label></td><td><input class="month-amount" aria-label="Số điều chỉnh cả tháng" placeholder="+5.000.000"><span class="cell-error" role="status"></span></td><td class="pay pay-start" colspan="5"></td></tr>`);
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
      const receipt = event.target.closest('td.receipt[data-pid]');
      if (receipt && !receipt.classList.contains('voided') && !receipt.classList.contains('voided-method') && !receipt.querySelector('input,select')) {
        const original = receipt.innerHTML, field = receipt.dataset.field, pid = receipt.dataset.pid;
        if (!field) {
          const row = receipt.closest('tr');
          root.querySelector('.void-prompt')?.remove();
          const saved = snapshot.receipts.find(item => item.pid === pid);
          row.insertAdjacentHTML('afterend', `<tr class="void-prompt" data-pid="${escape(pid)}"><td colspan="14">Hủy phiếu ${escape(pid)} — ${fmt(saved.amount_vnd)} <label>Lý do <input class="void-reason" aria-label="Lý do hủy phiếu"></label> <button class="confirm-void">Hủy phiếu</button> <button class="cancel-void">Bỏ qua</button><span class="cell-error" role="status"></span></td></tr>`);
          row.nextElementSibling.querySelector('input').focus(); return;
        }
        receipt.innerHTML = field === 'date' ? `<input class="saved-receipt-input" aria-label="Sửa ngày trả" value="${escape(receipt.textContent)}"><span class="cell-error receipt-date-error" role="status"></span>` :
          `<select class="saved-receipt-input" aria-label="Sửa hình thức">${methods.map(method => `<option${method === receipt.textContent ? ' selected' : ''}>${method}</option>`).join('')}</select>`;
        const input = receipt.querySelector('.saved-receipt-input'); input.focus();
        input.addEventListener('keydown', async keyEvent => {
          if (keyEvent.key === 'Escape') { receipt.innerHTML = original; return; }
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
      if (event.target.matches('td.editable,td.receipt')) { event.preventDefault(); event.target.click(); return; }
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
      if (event.target.matches('.receipt-amount')) {
        event.preventDefault();
        const row = event.target.closest('tr');
        try {
          row.querySelector('.receipt-date-error').textContent = '';
          const result = await submit('receipt', { date: dateInput(row.querySelector('.receipt-date').value), method: row.querySelector('.receipt-method').value,
            amount_vnd: moneyText(event.target.value) });
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
    root.addEventListener('paste', async event => {
      if (!event.target.matches('.paste-input')) return;
      event.preventDefault();
      try {
        const parsed = model.parsePastedTrips(event.clipboardData.getData('text/plain'));
        if (parsed.errors) throw Error(parsed.errors.join(' · '));
        await submit('paste', { debt_month: event.target.dataset.month + '-01', trips: parsed.trips });
      } catch (error) { event.target.closest('tr').querySelector('.paste-error').textContent = error.message; }
    });
    root.innerHTML = '<p role="status">Đang đọc sổ khách…</p>';
    api.read().catch(error => { root.innerHTML = `<p role="alert">${escape(error.message)}</p>`; });
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
    row.querySelectorAll('.receipt-date-error,.receipt-amount-error').forEach(error => { error.textContent = ''; });
    let amountVnd;
    try { amountVnd = model.parsePositiveVnd(amount.value); }
    catch { row.querySelector('.receipt-amount-error').textContent = 'Số tiền phải lớn hơn 0 và đúng định dạng'; amount.focus(); return; }
    const pid = model.nextReceiptPid(book);
    let plan;
    try { plan = model.planReceipt(book, { pid, date: date.value, method, amountVnd: amountVnd.toString() }); }
    catch { row.querySelector('.receipt-date-error').textContent = 'Ngày trả không hợp lệ'; date.focus(); return; }
    for (const line of plan.lines) months.find(month => month.key === line.monthKey).receipts.push({
      pid, date: date.value, method: line.kind === 'advance' ? 'ỨNG TRƯỚC' : method,
      amountVnd: line.amountVnd, kind: line.kind, ...(line.kind === 'advance' ? { receiptMethod: method } : {}), voided: null,
    });
    notice = model.receiptNotice(pid, plan);
    log('Ghi thu', `${pid}: 0 → ${money(amountVnd)}. ${notice}`);
    voidPrompt = null;
    render();
  }

  function startReceiptEdit(cell) {
    if (cell.querySelector('input,select')) return;
    const { pid, field } = cell.dataset;
    const original = cell.innerHTML;
    const value = cell.textContent;
    cell.innerHTML = field === 'date'
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
      log(field === 'date' ? 'Sửa ngày phiếu' : 'Sửa hình thức phiếu', `${pid}: ${value} → ${input.value}`);
      for (const line of plan.lines) months.find(month => month.key === line.monthKey).receipts[line.index] = line.receipt;
      if (plan.reallocation) reallocate(plan.reallocation);
      render();
    });
  }

  if (!live) root.addEventListener('click', event => {
    if (event.target.closest('.history-toggle')) { historyOpen = !historyOpen; render(); return; }
    if (event.target.closest('.history-close')) { historyOpen = false; render(); root.querySelector('.history-toggle').focus(); return; }
    const lock = event.target.closest('.month-lock');
    if (lock) { locks[lock.dataset.month] = !locks[lock.dataset.month]; render(); return; }
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
    if (event.target.matches('.receipt-amount') && event.key === 'Enter') { event.preventDefault(); saveReceipt(event.target); }
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
    months.find(item => item.key === event.target.dataset.month).trips.push(...result.trips);
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
