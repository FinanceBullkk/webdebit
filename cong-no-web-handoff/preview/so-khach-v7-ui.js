/* Bản xem sổ khách ẩn danh: chỉ lấy số tiền từ SoKhachV7Model.
 * Bản live (initLive) chỉ giữ trạng thái, dựng ctx, vẽ đầu sổ và tự làm mới; mỗi vùng màn hình do một phần
 * so-khach-v7-*-ui.js vẽ, theo hợp đồng ctx ở so-khach-v7-ctx.js. */
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
  // Thoát HTML và nhãn tháng "7/2026" dùng chung (CongNoFormat); các phần nhận qua ctx dưới tên escape/monthLabel.
  const { esc: escape, monthLabel, loadError } = CongNoFormat;
  const sheetFieldLabel = field => ({ carrier: 'Hãng tàu', shipper: 'Shipper', event_date: 'Ngày chuyến', origin: 'Điểm đi',
    destination: 'Điểm đến', booking: 'Booking' }[field] || field);
  const resolvableSheetFields = new Set(['carrier', 'shipper', 'origin', 'destination', 'event_date', 'booking']);
  const money = amount => amount === null || amount === undefined ? '–' : model.formatVnd(amount);
  const fieldMoney = amount => amount === null || amount === undefined ? '–' : model.formatVnd(model.parseVnd(amount));
  const outstanding = model?.formatOutstanding;
  // SO-GON-02 (29/10/2026): bản live bỏ cột "Còn nợ cộng dồn" (luôn trống); còn nợ cuối tháng ở thanh tháng.
  // SO-GON-03 (29/10/2026): mỗi số tiền của tháng hiện một lần — thanh tháng chỉ ghi còn nợ cuối tháng (rê chuột xem
  // cách tính), dòng Tổng tháng chỉ cộng cột (phụ phí, Thành tiền, Đã thu).
  // PHU-PHI-01: bản live có 0–3 cột phụ phí riêng của sổ chen giữa Đơn giá và Khác, nên số cột đổi theo sổ (useLiveColumns).
  let labels = live
    ? ['STT', 'Số container', 'Hãng tàu', 'Shipper', 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá', 'Khác', 'Thành tiền', 'Ngày trả', 'Hình thức',
      'Số tiền trả']
    : ['STT', 'Số container', 'Hãng tàu', 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá', 'Phụ phí', 'Thành tiền', 'Ngày trả', 'Hình thức',
      'Số tiền trả', 'Còn nợ cộng dồn'];
  let wide = live ? [52, 148, 104, 188, 104, 118, 118, 128, 116, 148, 124, 124, 224] : [52, 148, 104, 104, 118, 118, 128, 116, 148, 112, 112, 150, 158];
  const colTags = (from, to) => wide.slice(from, to).map((width, index) => `<col style="width:${width}px" class="col-${from + index}">`).join('');
  let widths = colTags(0, wide.length);
  let ownCount = 0;
  // Bề rộng từng cột ở hai khổ sổ (1696px màn rộng, 1258px màn 1280): [màn rộng, tối thiểu màn rộng, màn 1280, tối thiểu màn 1280].
  // Mỗi cột riêng lấy chỗ từ các cột theo thứ tự `shrinkOrder`, không cột nào hẹp hơn mức tối thiểu.
  // SO-GON-04 (H4): số tiền 16px, nên ở màn 1280 cột tiền (Đơn giá, Khác, Thành tiền) không co dưới chỗ cần cho số 16px; cột chữ
  // (cắt "…", rê chuột xem đủ) co trước. Co hết vẫn thiếu (Shipper + 3 cột riêng) thì cả sổ dùng khổ chật: số 15px, cột tiền hẹp lại.
  const liveColumns = [[52, 44, 44, 40], [148, 120, 112, 104], [104, 80, 62, 50], [188, 120, 130, 64], [104, 96, 90, 86], [118, 90, 80, 56],
    [118, 90, 80, 56], [128, 110, 100, 100], [116, 100, 88, 88], [148, 120, 120, 120], [124, 100, 90, 84], [124, 100, 84, 78], [224, 150, 178, 120]];
  const shrinkOrder = [12, 3, 10, 11, 5, 6, 1, 2, 4, 7, 9, 8, 0];
  // Khổ chật (chỉ màn 1280): cột riêng 80px, Đơn giá 92, Khác 80, Thành tiền 108 — vừa số 15px.
  const TIGHT_OWN = 80, TIGHT_MONEY = [[7, 92], [8, 80], [9, 108]];
  let tight = false;
  const isWide = () => typeof matchMedia !== 'function' || !matchMedia('(max-width:1877px)').matches;
  // Audit UX 31/10/2026 (P0-2): cột Shipper chỉ hiện khi sổ có ít nhất một dòng có shipper (sổ thật và sổ giả hiện đều trống).
  // Bỏ cột thì cột phụ phí riêng lấy chỗ của nó trước; phần còn lại chia cho hãng tàu, nơi đi, nơi đến (cột chữ hay bị cắt "…").
  const SHIPPER = 3;
  let showShipper = true;
  const shipperCell = html => showShipper ? html : '';
  function useLiveColumns(ownNames, shipper = true) {
    const wideMode = isWide();
    let ownWidth = wideMode ? 110 : 88;
    const base = liveColumns.map(item => wideMode ? item[0] : item[2]);
    const floor = liveColumns.map(item => wideMode ? item[1] : item[3]);
    if (!shipper) floor[SHIPPER] = 0;
    let need = ownNames.length * ownWidth;
    for (const index of shipper ? shrinkOrder : [SHIPPER, ...shrinkOrder.filter(item => item !== SHIPPER)]) {
      const take = Math.min(need, base[index] - floor[index]);
      base[index] -= take; need -= take;
    }
    tight = need > 0;
    if (tight) {
      need = Math.max(0, need - ownNames.length * (ownWidth - TIGHT_OWN));
      ownWidth = TIGHT_OWN;
      for (const [index, width] of TIGHT_MONEY) {
        const take = Math.min(need, base[index] - width);
        base[index] -= take; need -= take;
      }
    }
    if (!shipper) {
      const spare = base[SHIPPER], carrier = Math.round(spare * 0.3), origin = Math.round(spare * 0.35);
      base[2] += carrier; base[5] += origin; base[6] += spare - carrier - origin;
      base.splice(SHIPPER, 1);
    }
    showShipper = shipper;
    ownCount = ownNames.length;
    const tripNames = ['STT', 'Số container', 'Hãng tàu', ...(shipper ? ['Shipper'] : []), 'Ngày chuyến', 'Nơi đi', 'Nơi đến', 'Đơn giá'];
    labels = [...tripNames, ...ownNames, 'Khác', 'Thành tiền', 'Ngày trả', 'Hình thức', 'Số tiền trả'];
    wide = [...base.slice(0, tripNames.length), ...ownNames.map(() => ownWidth), ...base.slice(tripNames.length)];
    widths = colTags(0, wide.length);
  }
  // Chỉ số cột: chuyến 0..tripCols-1 (cụm phụ phí từ feeStart()), phiếu thu 3 cột cuối.
  const tripCols = () => labels.length - 3;
  // Cột phụ phí riêng đầu tiên (ngay sau Đơn giá): 8 khi có cột Shipper, 7 khi không.
  const feeStart = () => tripCols() - ownCount - 2;
  // Khung cột cho các phần vẽ bản live (ctx.columns): luôn đọc bố cục hiện tại, useLiveColumns đổi nó mỗi lần vẽ.
  const columns = { count: () => labels.length, trip: tripCols, feeStart, unitPrice: () => feeStart() - 1, tags: colTags,
    all: () => widths, shipper: () => showShipper, shipperCell };
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
      .map(receipt => [receipt.pid, new Set(months.filter(item => item.receipts.some(line => line.pid === receipt.pid && line.voided === null))
        .map(item => item.key))])));
    for (const month of months) month.receipts = month.receipts.filter(receipt => receipt.voided !== null);
    for (const line of plan.lines) months.find(month => month.key === line.monthKey).receipts.push(line.receipt);
    const changed = plan.changedPids.map(pid => {
      const before = [...(old.get(pid) ?? [])].map(monthLabel).join(', ');
      const after = months.filter(month => month.receipts.some(receipt => receipt.pid === pid && receipt.voided === null))
        .map(month => monthLabel(month.key)).join(', ');
      return `${pid}: tháng ${before} → tháng ${after}`;
    });
    if (changed.length) log('Phân bổ lại', changed.join(' · '));
    notice = plan.changedPids.length
      ? `Đã phân bổ lại khoản thu theo nợ cũ trước: ${plan.changedPids.join(', ')}` : '';
  }

  function editCell(value, field, index, month, classes = '') {
    const what = field === 'unitPriceVnd' ? 'đơn giá' : 'phụ phí';
    return `<td class="num editable ${classes}" tabindex="0" role="button" aria-label="Sửa ${what} dòng ${index + 1} tháng ${monthLabel(month.key)}" `
      + `data-month="${month.key}" data-index="${index}" data-field="${field}">${escape(value)}</td>`;
  }

  function referenceFields(scope = root) {
    const reference = scope.querySelector('.receipt-reference')?.value.trim();
    return reference ? { reference } : {};
  }

  function referenceLine(receipt, entry = false) {
    if (!receipt && !entry) return '';
    const voided = receipt && (receipt.voided != null || receipt.voided_by_event != null);
    const reference = receipt
      ? `<td colspan="3" class="pay receipt receipt-edit${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="reference" `
        + `tabindex="${voided ? '-1' : '0'}" role="button" aria-label="Sửa tham chiếu ${escape(receipt.pid)}">`
        + `Tham chiếu: ${escape(receipt.reference || '–')}</td>`
      : '<td colspan="3" class="pay"><label>Tham chiếu <input class="receipt-reference" aria-label="Tham chiếu" maxlength="500" '
        + 'placeholder="Tùy chọn: số giao dịch, ngoại tệ/tỷ giá…"></label></td>';
    return `<tr class="reference-row"><td colspan="9"></td>${reference}<td></td></tr>`;
  }

  function renderLine(trip, receipt, index, month) {
    const result = trip ? model.tripAmount(trip) : null;
    const feeOnly = result?.isFeeOnly;
    const missing = result?.isMissingPrice;
    const pending = trip?.status === 'pending_review';
    const open = month.key === openMonth;
    const entry = open && index === month.receipts.length;
    let payCells;
    if (receipt) {
      const voided = receipt.voided !== null, pid = escape(receipt.pid), tab = receipt.voided === null ? '0' : '-1';
      payCells = [
        `<td class="pay pay-start receipt receipt-edit ${voided ? 'voided' : ''}" data-pid="${pid}" data-field="date" tabindex="${tab}">`
          + `${escape(receipt.date)}</td>`,
        `<td class="pay receipt receipt-edit ${voided ? 'voided-method' : ''}" data-pid="${pid}" data-field="method" tabindex="${tab}">`
          + `${escape(voided ? 'ĐÃ HỦY' : receipt.method)}</td>`,
        `<td class="pay num receipt ${voided ? 'voided' : ''}" data-pid="${pid}" tabindex="${tab}">${escape(fieldMoney(receipt.amountVnd))}</td>`];
    } else {
      payCells = [
        `<td class="pay pay-start">${entry ? '<input class="empty-entry receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric">'
          + '<span class="cell-error receipt-date-error" role="status"></span>' : ''}</td>`,
        `<td class="pay">${entry
          ? `<select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${method}</option>`).join('')}</select>` : ''}</td>`,
        `<td class="pay num">${entry ? '<input class="empty-entry receipt-amount" aria-label="Số tiền trả" inputmode="numeric">'
          + '<span class="cell-error receipt-amount-error" role="status"></span>' : ''}</td>`];
    }
    const cells = [
      trip && !feeOnly ? cell(index + 1) : empty(),
      cell(trip?.container ?? (month.opening ? 'Nợ cũ chuyển sang sổ mới' : feeOnly ? 'Phí lẻ' : '')),
      cell(trip?.carrier ?? ''), cell(trip?.date ?? ''), cell(trip?.from ?? ''), cell(trip?.to ?? ''),
      pending ? num(fieldMoney(trip.unitPriceVnd))
        : trip ? editCell(missing ? 'chưa có giá' : fieldMoney(trip.unitPriceVnd), 'unitPriceVnd', index, month, missing ? 'missing' : '') : empty('num'),
      pending ? num(fieldMoney(trip.otherFeeVnd)) : trip ? editCell(fieldMoney(trip.otherFeeVnd), 'otherFeeVnd', index, month) : empty('num'),
      trip ? num(pending ? 'CHỜ KIỂM' : missing ? '–' : money(result.amountVnd)) : empty('num'),
      ...payCells,
      empty('num'),
    ];
    const adjustmentRows = (month.adjustments ?? []).filter(item => trip && item.lineId === (trip.id ?? `${month.key}#${index}`))
      .map(adjustment => `<tr class="adjustment"><td colspan="8">Điều chỉnh chuyến ${index + 1} · <label>Ghi chú <input class="adjustment-note" `
        + `data-month="${month.key}" data-adj="${escape(adjustment.adjId)}" aria-label="Ghi chú điều chỉnh chuyến ${index + 1}" `
        + `value="${escape(adjustment.reason ?? '')}" placeholder="Tùy chọn, Enter lưu"></label></td>${num(money(model.adjustmentAmount(adjustment)))}`
        + '<td class="pay pay-start" colspan="4"></td></tr>').join('');
    return `<tr>${cells.join('')}</tr>${referenceLine(receipt, entry)}${adjustmentRows}`;
  }

  function renderMonth(month, summary, _balance) {
    const label = monthLabel(month.key);
    const open = month.key === openMonth;
    const editable = model.isMonthOpen(locks, month.key);
    const lineCount = Math.max(month.trips.length, month.receipts.length + (open ? 1 : 0));
    const lines = Array.from({ length: lineCount }, (_, index) => renderLine(month.trips[index], month.receipts[index], index, month)).join('');
    const prompt = voidPrompt?.monthKey === month.key
      ? `<tr class="void-prompt"><td colspan="13">Hủy phiếu ${escape(voidPrompt.pid)} — ${money(voidPrompt.totalVnd)} (${voidPrompt.monthCount} tháng) `
        + '<label>Lý do <input class="void-reason" aria-label="Lý do hủy phiếu"></label> <button class="confirm-void">Hủy phiếu</button> '
        + '<button class="cancel-void">Bỏ qua</button><span class="cell-error void-error" role="status"></span></td></tr>' : '';
    const traces = model.voidedLines(book, month.key).map(line => '<tr class="void-trace"><td colspan="13">'
      + `${money(line.amountVnd)} · ${escape(line.date)} · ${escape(line.voidedOn)} · ${escape(line.reason)}</td></tr>`).join('');
    const status = open && notice ? `<tr class="receipt-status"><td colspan="13" role="status">${escape(notice)}</td></tr>` : '';
    const paste = editable ? '<tr class="paste-row"><td colspan="9"><label>Dán các dòng từ Sheet vào đây '
      + `<textarea class="paste-input" data-month="${month.key}" rows="2" aria-label="Dán các dòng từ Sheet vào đây"></textarea></label>`
      + '<span class="paste-error" role="status"></span></td><td class="pay pay-start" colspan="4"></td></tr>' : '';
    const monthAdjustments = (month.adjustments ?? []).filter(item => !item.lineId).map(item => '<tr class="adjustment month-adjustment"><td colspan="8">'
      + `Điều chỉnh cả tháng${item.reason ? ` · ${escape(item.reason)}` : ''}</td>${num(money(model.adjustmentAmount(item)))}`
      + '<td class="pay pay-start" colspan="4"></td></tr>').join('');
    const input = monthPrompt === month.key ? '<tr class="month-adjustment-input"><td colspan="8">Điều chỉnh cả tháng · '
      + `<label>Ghi chú <input class="month-note" aria-label="Ghi chú điều chỉnh cả tháng ${label}"></label></td>`
      + `<td><input class="month-amount" aria-label="Số điều chỉnh cả tháng ${label}" inputmode="decimal" placeholder="+5.000.000">`
      + '<span class="cell-error month-error" role="status"></span></td><td class="pay pay-start" colspan="4"></td></tr>' : '';
    const head = `<tr class="month"><th colspan="13" scope="rowgroup"><span class="month-title">THÁNG ${label}<button class="month-lock" `
      + `data-month="${month.key}" aria-label="${editable ? 'Khóa' : 'Mở khóa'} tháng ${label}" title="${editable ? 'Đang mở' : 'Đã khóa'}" `
      + `aria-pressed="${editable}">${editable ? '🔓' : '🔒'}</button><em>Nợ các tháng trước: ${outstanding(summary.carryVnd)}</em></span></th></tr>`;
    const subtotal = `<tr class="subtotal"><td colspan="8">Tổng tháng ${label} <button class="add-month-adjustment" data-month="${month.key}">`
      + `+ Điều chỉnh cả tháng</button></td>${num(money(summary.totalChargesVnd))}<td class="pay pay-start" colspan="2">Đã thu</td>`
      + `${num(outstanding(summary.receivedVnd), 'pay')}${num(outstanding(summary.endOfMonthVnd))}</tr><tr class="spacer"><td colspan="13"></td></tr>`;
    return `<section id="thang-${escape(month.key)}"><table class="ledger${editable ? '' : ' locked'}" aria-label="Sổ khách tháng ${label}">`
      + `<colgroup>${widths}</colgroup><tbody>${head}${lines}${monthAdjustments}${input}${prompt}${traces}${status}${paste}${subtotal}</tbody>`
      + '</table></section>';
  }

  function renderShell(view) {
    const scrollY = window.scrollY;
    // Một thanh đầu sổ (góp ý người dùng 23/10/2026): tên khách, Lịch sử, tổng còn nợ.
    // Bản live là trang khách (TRANG-KHACH-01, A1): đầu trang một dòng = ← Quay lại, tên khách, mặt hàng, thanh bốn thẻ
    // (so-khach-v7-tabs-ui.js, phần đó cũng dời ô tìm khách lên thanh trên), Tổng còn nợ, nút chính "Ghi phiếu thu" và nút phụ
    // Lịch sử (SO-GON-04 L7). Phần còn lại của sổ — dải nút việc chờ và "Làm mới" (không dính), các bảng tháng — là thẻ Sổ
    // (#the-so); khung các thẻ khác nằm sau.
    const liveControls = live && document.querySelector('#live-controls');
    const history = `<button class="history-toggle" aria-expanded="${historyOpen}" aria-controls="history-panel">Lịch sử</button>`;
    const total = `<div class="head-item total"><span>Tổng còn nợ (mọi tháng)</span><strong>${view.total}</strong></div></div>`;
    const head = live
      ? `<div class="book-head">${view.pageHead}<div class="head-item total"><span>Tổng còn nợ</span><strong>${view.total}</strong></div>`
        + `${view.entryButton}${history}</div>`
      : `<div class="book-head"><h1>Sổ khách · ${escape(view.customer)}</h1>${history}${view.sheetButton ?? ''}${total}`;
    const payStart = live ? tripCols() : 9;
    const columnHead = labels.map((label, index) => {
      const fee = live && index >= feeStart() && index < tripCols() - 1;
      return `<th scope="col" class="${index >= payStart && index <= payStart + 2 ? 'pay ' : ''}${index === payStart ? 'pay-start' : ''}`
        + `${fee ? 'fee-h num' : ''}"${fee ? ' title="Phụ phí"' : ''}>${escape(label)}</th>`;
    }).join('');
    // Hai lần xuống dòng giữa ba khối giữ đúng như bản trước (DOM không đổi). Bản live (SO-GON-04): thanh chip tháng dính ngay
    // trên tiêu đề cột thay danh sách tháng bên phải; bản fixture giữ danh sách tháng. Khung Lịch sử nằm ngoài thẻ Sổ (mở được ở
    // mọi thẻ, nút ở đầu trang).
    const aside = `<aside id="history-panel" class="history-panel" aria-label="Lịch sử thay đổi" ${historyOpen ? '' : 'hidden'}><header><h2>Lịch sử</h2>`
      + `<button class="history-close" aria-label="Đóng lịch sử">Đóng</button></header>${view.history}</aside>`;
    const book = `${view.notice ?? ''}<div class="layout"><div class="ledger-book${tight ? ' tight' : ''}">${view.chips ?? ''}<table class="ledger ledger-head" aria-label="Cột sổ khách">`
      + `<colgroup>${widths}</colgroup><thead><tr class="columns">${columnHead}</tr></thead></table>${view.sections}</div>`;
    root.innerHTML = (live
      ? [head, '<div id="the-so" class="tab-pane" role="tabpanel" aria-labelledby="tab-so"><div class="book-bar">'
        + `<div class="book-tasks">${view.barButtons}</div><div class="live-slot"></div></div>${book}`, `</div></div>${aside}${view.panes}`]
      : [head, book, `<nav class="months-nav" aria-label="Danh sách tháng"><h2>DANH SÁCH THÁNG</h2>${view.navigation}</nav></div>${aside}`]).join('\n    ');
    // "Cập nhật … · Làm mới" giữ trình nghe của sheet-refresh.js: chỉ dời vào dải đầu thẻ Sổ.
    const liveSlot = root.querySelector('.live-slot');
    if (liveControls && liveSlot) liveSlot.append(liveControls);
    pinReceipts();
    window.scrollTo(0, scrollY);
  }

  // Góp ý 28/10/2026: cuộn xuống trong tháng vẫn thấy các khoản đã thu. SO-GON-02: phiếu thu là danh sách riêng
  // bên phải (không chung hàng với chuyến); cả danh sách dính khi vừa màn. Dài hơn màn thì để yên
  // (không cắt khung: ô chọn sổ cấn trừ mở xuống dưới hàng nhập). Ô chữ chuyến bị cắt "…" thì rê chuột xem đủ.
  // Bản fixture dính dưới dòng tháng; bản live (SO-GON-04: dòng tháng không dính nữa) dính dưới tiêu đề cột.
  function pinReceipts() {
    if (typeof root.querySelectorAll !== 'function' || typeof getComputedStyle !== 'function') return;
    const columnHead = live ? root.querySelector('.ledger-head') : null;
    for (const table of root.querySelectorAll('section > table.ledger')) {
      const head = columnHead ?? table.querySelector('tr.month th'), stick = table.querySelector('.pay-stick');
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
    const historyItem = item => `<li><time>${escape(item.time)}</time><span>Bản thử — chưa đăng nhập</span><strong>${escape(item.type)}</strong>`
      + `<p>${escape(item.description)}</p>${item.reason ? `<small>Ghi chú/lý do: ${escape(item.reason)}</small>` : ''}</li>`;
    renderShell({ customer: book.customer,
      total: money(chain.totalOutstandingVnd),
      sections: months.map((month, index) => renderMonth(month, chain.months[index], remaining[index])).join(''),
      navigation: months.map((month, index) => `<a href="#thang-${escape(month.key)}"><span>${monthLabel(month.key)}</span>`
        + `<small>${outstanding(remaining[index].outstandingVnd)}</small></a>`).join(''),
      history: history.length ? `<ol>${history.map(historyItem).join('')}</ol>` : '<p>Chưa có thay đổi nào</p>' });
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
    const dateText = value => /^\d{4}-\d\d-\d\d$/.test(value ?? '')
      ? value.slice(8) + '/' + value.slice(5, 7) + '/' + value.slice(0, 4) : (value ?? '');
    const dateInput = value => /^\d\d\/\d\d\/\d{4}$/.test(value) ? value.slice(6) + '-' + value.slice(3, 5) + '-' + value.slice(0, 2) : value;
    const monthKey = value => typeof value === 'string' ? value.slice(0, 7) : '';
    // Ngày trong ô của Sheet (dòng sổ gốc): số ngày Excel ("46032.0", hệ 1900) hoặc chuỗi ISO có giờ → dd/mm/yyyy; chữ khác giữ nguyên.
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
    // Đổi ngày sang tháng khác (góp ý 23/10/2026): dòng vừa chuyển tô vàng ở tháng mới, tháng cũ giữ một dòng mờ
    // có Xem / Hoàn tác. Chỉ sống trong tab: tải lại trang là hết.
    const moved = new Map();   // `${kind}-${id}` → tháng cũ (yyyy-mm)
    const ghosts = [];         // { kind, id, month, to, container, oldIso }
    const fieldNames = { container: 'số container', carrier: 'hãng tàu', shipper: 'shipper', event_date: 'ngày chuyến', origin: 'nơi đi',
      destination: 'nơi đến', unit_price_vnd: 'đơn giá', other_fee_vnd: 'phụ phí' };
    // PHU-PHI-01: cột phụ phí riêng của sổ (fee_columns, đọc lại mỗi lần vẽ) và danh mục loại phụ phí (so-khach-v7-fee-ui.js nạp).
    let feeColumnIds = [];
    let feeTypes = [];
    const feeTypeName = id => feeTypes.find(type => Number(type.id) === Number(id))?.name ?? `Loại #${id}`;
    // Vẽ lại sổ từ bản đang có (không tải lại). Khung Ghi phiếu thu nằm ngoài #app (so-khach-v7-entry-ui.js) nên chữ đang gõ
    // ở đó không mất khi vẽ lại.
    function redraw() {
      if (snapshot) renderSnapshot(snapshot);
    }
    // Đầu trang: tổng còn nợ, băng thông báo, nút chính "Ghi phiếu thu" (so-khach-v7-entry-ui.js) và dải nút của các phần ngay
    // dưới đầu trang ở thẻ Sổ (phụ phí, bảng giá, duyệt Sheet, giá và phiếu thu Sheet) — SO-GON-04 L7. Tên khách và thanh thẻ:
    // so-khach-v7-tabs-ui.js.
    function headView(data, active) {
      const sheetNotice = data.sheet_sync?.unavailable ? 'Không đọc được chuyến mới từ Sheet.' : '';
      const shown = (message && message !== 'Đã lưu.') || !active || sheetNotice;
      const text = message || sheetNotice || (active ? '' : 'Khách chưa có số dư đầu hiệu lực. Chưa thể ghi.');
      const notice = `<p class="live-notice" role="status" style="padding:8px;background:#fff3d6" ${shown ? '' : 'hidden'}>${escape(text)}</p>`
        + `<button class="retry-command" ${api.hasPending() ? '' : 'hidden'}>Thử lại thao tác vừa gửi</button>`;
      const newCount = data.sheet_sync?.new_count ?? 0;
      const barButtons = (newCount ? `<button class="sheet-approve" ${active ? '' : 'disabled'}>Duyệt ${newCount} chuyến mới</button>` : '')
        + (active && data.sheet_prices?.ready_count ? `<button class="price-approve">Ghi ${data.sheet_prices.ready_count} giá từ Sheet</button>` : '')
        + (ctx.receiptButton?.(data, active) ?? '')
        + `<button class="fee-settings-open" aria-haspopup="dialog">Cài đặt phụ phí</button>${ctx.priceButtons?.(active) ?? ''}`;
      return { total: `${fmt(data.total_outstanding_vnd)}${data.total_outstanding_vnd == null ? '' : ' đ'}`, notice,
        entryButton: ctx.entryButton(active), barButtons };
    }
    // Vẽ cả sổ từ một bản GET; mọi số tiền lấy nguyên từ GET, trang không cộng trừ tiền. Bảng tháng: so-khach-v7-month-ui.js
    // (bảng chuyến: trips-ui, phiếu thu: pay-ui); Lịch sử: history-ui; thanh ?loc: loc-ui; móc sau khi vẽ của các phần khác.
    function renderSnapshot(data) {
      const focus = ctx.focusMark();   // vẽ lại thay cả #app: giữ tiêu điểm ở đúng ô (so-khach-v7-edit-ui.js)
      snapshot = data;
      ctx.imagesOnSnapshot?.(data);
      ctx.priceOnSnapshot?.(data);
      feeColumnIds = (data.fee_columns ?? []).map(column => Number(column.fee_type_id));
      // Cột Shipper chỉ hiện khi có dòng có shipper: chuyến web, dòng sổ gốc, chuyến Sheet chờ duyệt (các dòng sổ vẽ ra).
      const shipperRows = [...(data.trips ?? []).filter(row => !row.deleted),
        ...(data.legacy_rows ?? []).filter(row => !row.current?.deleted).flatMap(row => [row.current, row.display]),
        ...(data.sheet_sync?.items ?? []).filter(row => row.sync_state === 'NEW' || !row.existing_id)];
      useLiveColumns(feeColumnIds.map(feeTypeName), shipperRows.some(row => String(row?.shipper ?? '').trim() !== ''));
      const updated = document.querySelector('#updated-at');
      const time = new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });
      if (updated?.id === 'updated-at') updated.textContent = `Cập nhật ${time} · tự tải mỗi 60 giây`;
      sheetRefresh?.paint();
      const active = data.status === 'active';
      const head = headView(data, active);
      const { sections, chips, work } = monthSections(data, active);
      renderShell({ ...head, sections, chips, pageHead: ctx.pageHead(work), panes: ctx.tabPanes(), history: historyList(data.events ?? []) });
      conflictsAfterRender(data);
      decoratePrices(data, active);
      ctx.removedAfterRender?.(data, active);
      ctx.receiptsAfterRender?.(data, active);
      ctx.priceAfterRender?.(active);
      ctx.psAfterRender?.(data, active);
      ctx.entryAfterRender();
      monthsAfterRender();
      locAfterRender(data);
      ctx.feeAfterRender?.();
      ctx.focusBack(focus);
    }
    function showNotice(value) {
      message = ctx.presenceStale ? ctx.presenceStale(value) : value;
      const status = root.querySelector('.live-notice');
      // "Đã lưu." trơn không hiện băng vàng: kết quả đã thấy ngay trên dòng (góp ý 23/10/2026).
      if (status) { status.textContent = message; status.hidden = !message || message === 'Đã lưu.'; }
      const retry = root.querySelector('.retry-command');
      if (retry) retry.hidden = !api.hasPending();
    }
    // Danh sách khách về sau sổ thì vẽ lại qua redraw để không xóa ô ghi thu/CẤN TRỪ đang gõ dở.
    const api = live.create({ customerId, onSnapshot: renderSnapshot, onRedraw: () => redraw(), onNotice: showNotice });
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
    // Dòng hỏi/chi tiết chèn sau một hàng trải hết bảng chứa hàng đó (bảng chuyến, danh sách phiếu thu 3 cột, cả sổ).
    const spanOf = row => (typeof row?.closest === 'function' && row.closest('table')?.querySelector(':scope > colgroup')?.children.length)
      || labels.length;
    // Hợp đồng ctx (trường, ai ghi, ai đọc, thứ tự cài các phần): so-khach-v7-ctx.js. install() cài các phần đã đăng ký vào
    // window.SoKhachV7LiveParts theo thứ tự trong hợp đồng — cũng là thứ tự trình nghe sự kiện trên #app — rồi mới tới
    // trình nghe của lõi bên dưới; phần đọc trường chưa có hoặc ghi trường không khai thì dừng ngay.
    const ctx = { root, model, api, live, customerId, escape, fmt, cell, num, empty, spanOf, dateText, sheetDay, dateInput, monthKey, monthLabel,
      liveOpenMonth, methods, fieldNames, moved, ghosts, sheetFieldLabel, resolvableSheetFields, moneyText, referenceFields,
      showNotice, renderSnapshot, redraw, submit, columns, feeTypeName,
      get feeTypes() { return feeTypes; }, set feeTypes(value) { feeTypes = value; },
      get feeColumnIds() { return feeColumnIds; }, get snapshot() { return snapshot; },
      get historyOpen() { return historyOpen; }, set historyOpen(value) { historyOpen = value; },
      busyChecks: [] };
    SoKhachV7Ctx.install(ctx, window.SoKhachV7LiveParts ?? {});
    const { monthSections, monthsAfterRender, historyList, conflictsAfterRender, decoratePrices, locAfterRender } = ctx;
    // Đổi khổ màn qua mốc 1878px thì bề rộng cột tính lại (cột phụ phí riêng lấy chỗ khác nhau ở hai khổ).
    if (typeof matchMedia === 'function') matchMedia('(max-width:1877px)').addEventListener?.('change', () => redraw());
    // Audit UX 31/10/2026 (P1-6): đọc sổ lỗi thì một câu tiếng Việt và nút Thử lại; không hiện chữ của trình duyệt.
    let refreshing = false;
    const firstRead = () => {
      root.innerHTML = '<p role="status">Đang đọc sổ khách…</p>';
      refreshing = true;
      api.read().catch(() => {
        root.innerHTML = `<div class="load-error" role="alert"><p>${escape(loadError('sổ khách'))}</p>`
          + '<button type="button" class="load-retry">Thử lại</button></div>';
      }).finally(() => { refreshing = false; });
    };
    root.addEventListener('click', event => { if (event.target.closest('.load-retry')) firstRead(); });
    firstRead();
    // Đang nhập hoặc đang mở chi tiết thì không tự cập nhật (vẽ lại sẽ xóa ô đang gõ hoặc đóng khung đang xem).
    const BUSY_OPEN = 'input:focus,textarea:focus,select:focus,.offset-backdrop,.sheet-detail,.review-prompt,.month-adjustment-input,'
      + '.void-prompt,.move-ask,.delete-prompt,.lock-ask,.price-panel,.history-panel:not([hidden])';
    const busy = () => api.hasPending() || ctx.busyChecks.some(check => check()) || root.querySelector(BUSY_OPEN)
      || [...root.querySelectorAll('.info-input')].some(input => input.value.trim());
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
    const current = trip[field] === null ? '' : fieldMoney(trip[field]);
    cell.innerHTML = `<input class="money-input" aria-label="${escape(cell.getAttribute('aria-label'))}" value="${escape(current)}">`
      + '<span class="cell-error" role="status"></span>';
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
        log('Sửa đè ' + (field === 'unitPriceVnd' ? 'đơn giá' : 'phụ phí'),
          `Tháng ${monthLabel(month)}, chuyến ${Number(index) + 1}: ${before} → ${value === null ? '–' : fieldMoney(value)}`);
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
          log('Điều chỉnh chuyến',
            `Tháng ${monthLabel(month)}, chuyến ${Number(index) + 1}: ${money(planned.oldAmountVnd)} → ${money(planned.newAmountVnd)}`);
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
    const duplicate = reference && months.some(month => month.receipts.some(item => item.pid !== pid && item.reference === reference));
    notice = model.receiptNotice(pid, plan) + (duplicate ? ' Tham chiếu trùng với phiếu khác trong sổ.' : '');
    log('Ghi thu', `${pid}: 0 → ${money(amountVnd)}. ${notice}`);
    voidPrompt = null;
    render();
  }

  function startReceiptEdit(cell) {
    if (cell.querySelector('input,select')) return;
    const { pid, field } = cell.dataset;
    const original = cell.innerHTML;
    const value = field === 'reference' ? months.flatMap(month => month.receipts).find(item => item.pid === pid)?.reference ?? '' : cell.textContent;
    cell.innerHTML = (field === 'reference'
      ? `<input class="saved-receipt-input" aria-label="Sửa tham chiếu ${escape(pid)}" maxlength="500" value="${escape(value)}">`
      : field === 'date'
        ? `<input class="saved-receipt-input receipt-date" aria-label="Sửa ngày trả ${escape(pid)}" value="${escape(value)}" inputmode="numeric">`
        : `<select class="saved-receipt-input receipt-method" aria-label="Sửa hình thức ${escape(pid)}">`
          + `${methods.map(method => `<option${method === value ? ' selected' : ''}>${method}</option>`).join('')}</select>`)
      + '<span class="cell-error" role="status"></span>';
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
      const duplicate = field === 'reference' && input.value.trim()
        && months.some(month => month.receipts.some(item => item.pid !== pid && item.reference === input.value.trim()));
      notice = duplicate ? 'Tham chiếu trùng với phiếu khác trong sổ.' : '';
      render();
    });
  }

  if (!live) root.addEventListener('click', event => {
    if (event.target.closest('.history-toggle')) { historyOpen = !historyOpen; render(); return; }
    if (event.target.closest('.history-close')) { historyOpen = false; render(); root.querySelector('.history-toggle').focus(); return; }
    const lock = event.target.closest('.month-lock');
    if (lock) {
      locks[lock.dataset.month] = !locks[lock.dataset.month];
      log(locks[lock.dataset.month] ? 'Khóa tháng' : 'Mở tháng', `Tháng ${monthLabel(lock.dataset.month)}`);
      render();
      return;
    }
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
    const activate = event.key === 'Enter' || event.key === ' ';
    if (event.target.matches('td.editable') && activate) { event.preventDefault(); startEdit(event.target); }
    if (event.target.matches('td.receipt[data-pid]') && activate) { event.preventDefault(); event.target.click(); }
    if (event.target.matches('.receipt-date') && event.key === 'Enter') {
      event.preventDefault();
      event.target.closest('tr').querySelector('.receipt-amount').focus();
    }
    if ((event.target.matches('.receipt-amount') || event.target.matches('.receipt-reference')) && event.key === 'Enter') {
      event.preventDefault();
      saveReceipt(root.querySelector('.receipt-amount'));
    }
    if (event.target.matches('.adjustment-note') && event.key === 'Enter') {
      event.preventDefault();
      const { month, adj } = event.target.dataset;
      const owner = months.find(item => item.key === month);
      const item = owner.adjustments.find(adjustment => adjustment.adjId === adj);
      if (!item) return;
      const note = event.target.value.trim();
      if (item.reason !== note) {
        log('Ghi chú điều chỉnh chuyến', `Tháng ${monthLabel(month)}, ${money(model.adjustmentAmount(item))}: ${item.reason || '–'} → ${note || '–'}`, note);
      }
      owner.adjustments[owner.adjustments.indexOf(item)] = { ...item, reason: note };
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
    if (event.target.matches('.receipt-date:not(.saved-receipt-input)') && event.target.value.length === 10) {
      event.target.closest('tr').querySelector('.receipt-amount').focus();
    }
    if (event.target.matches('.void-reason')) root.querySelector('.void-error').textContent = '';
  });
  if (!live) document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && historyOpen) { historyOpen = false; render(); root.querySelector('.history-toggle').focus(); }
  });
  if (live) initLive(); else render();
})();
