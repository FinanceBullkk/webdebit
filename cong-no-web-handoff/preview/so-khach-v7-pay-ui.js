/* Sổ khách V7 bản live — danh sách phiếu thu bên phải của mỗi tháng (SO-GON-02, phương án A 29/10/2026): khoản thu Sheet
 * (thứ tự Sheet), phiếu web, khung "Ghi phiếu mới", phiếu đã hủy gom cuối. Tách từ renderSnapshot của so-khach-v7-ui.js
 * (31/10/2026, DOM không đổi). Số tiền lấy nguyên từ GET, chỉ định dạng (ARCH-03). Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).pay = ctx => {
  'use strict';
  const { root, escape, fmt, cell, num, dateText, sheetDay, monthKey, monthLabel, methods, redraw } = ctx;
  // Tháng (yyyy-mm) đang mở danh sách phiếu đã hủy; chỉ sống trong tab.
  const openVoided = new Set();
  const offsetAttrs = receipt => receipt.offset_pair_id == null ? ''
    : ` data-pair="${escape(receipt.offset_pair_id)}" data-other="${escape(receipt.counterparty_customer_id)}"`
      + ` data-other-name="${escape(receipt.counterparty_name)}"`;
  const offsetLink = receipt => receipt.offset_pair_id == null || receipt.voided_by_event != null ? ''
    : `<a class="offset-link" href="/so-khach-v7-live.html?customer=${encodeURIComponent(receipt.counterparty_customer_id)}">`
      + `${receipt.outgoing ? 'sang' : 'từ'} ${escape(receipt.counterparty_name)}</a>`;
  // Phiếu chưa có tham chiếu chỉ còn dấu "+" nhỏ để thêm (bấm như cũ); có thì ghi "Tham chiếu: …".
  const referenceInline = receipt => {
    const voided = receipt.voided_by_event != null;
    return receipt.reference
      ? `<small class="receipt receipt-edit receipt-ref${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="reference" `
        + `tabindex="${voided ? '-1' : '0'}" role="button" aria-label="Sửa tham chiếu ${escape(receipt.pid)}">Tham chiếu: ${escape(receipt.reference)}</small>`
      : `<small class="receipt receipt-edit receipt-ref empty" data-pid="${escape(receipt.pid)}" data-field="reference" tabindex="0" role="button" `
        + `aria-label="Thêm tham chiếu ${escape(receipt.pid)}" title="Thêm tham chiếu">+</small>`;
  };
  // DA-THU-01: phiếu nằm ở tháng của ngày thu, đủ số tiền một lần (như Sheet); phần trừ nợ từng tháng chỉ ghi chữ nhỏ,
  // và chỉ ghi khi phiếu trừ nợ tháng khác tháng của ngày thu hoặc chia nhiều tháng.
  const allocationInline = (receipt, key) => {
    const lines = receipt.voided_by_event == null ? receipt.lines ?? [] : [];
    if (!lines.length || lines.every(line => monthKey(line.month) === key)) return '';
    const parts = lines.map(line => `T${monthLabel(monthKey(line.month))}${lines.length > 1 ? ` ${fmt(line.amount_vnd)}` : ''}`);
    return `<small class="receipt-allocation">Trừ nợ ${parts.map(escape).join(' · ')}</small>`;
  };
  const methodText = (receipt, voided, plain) => voided ? 'ĐÃ HỦY' : receipt.line.kind === 'advance' ? 'ỨNG TRƯỚC' : plain;
  function payCells(receipt, key) {
    const voided = receipt.voided_by_event != null;
    const tab = voided ? '-1' : '0';
    const dateCell = `<td class="pay pay-start receipt receipt-edit${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}" data-field="date"`
      + `${offsetAttrs(receipt)} tabindex="${tab}">${escape(dateText(receipt.date))}</td>`;
    const methodCell = receipt.offset_pair_id != null
      ? `<td class="pay offset-method${voided ? ' voided-method' : ''}">${escape(methodText(receipt, voided, 'CẤN TRỪ'))}${offsetLink(receipt)}</td>`
      : `<td class="pay receipt receipt-edit${voided ? ' voided-method' : ''}" data-pid="${escape(receipt.pid)}" data-field="method" tabindex="${tab}">`
        + `${escape(methodText(receipt, voided, receipt.method))}</td>`;
    // Số tiền một dòng riêng; tham chiếu, tháng trừ nợ và nút ảnh gom thành một dòng nhỏ bên dưới.
    const meta = `${receipt.outgoing ? '' : referenceInline(receipt)}${allocationInline(receipt, key)}${ctx.imageClip?.(receipt) ?? ''}`;
    const amountCell = `<td class="pay num receipt${voided ? ' voided' : ''}" data-pid="${escape(receipt.pid)}"${offsetAttrs(receipt)} tabindex="${tab}">`
      + `<span class="receipt-sum">${fmt(receipt.line.amount_vnd)}</span>${meta ? `<span class="receipt-meta">${meta}</span>` : ''}</td>`;
    return dateCell + methodCell + amountCell;
  }
  // Góp ý 29/10/2026: hàng nhập phiếu là một khung có nhãn từng ô, chỗ dán ảnh và nút "Ghi phiếu" (Enter vẫn ghi),
  // không ép vào ba cột hẹp nữa. Tên lớp các ô giữ nguyên để đường ghi (edit-ui, offset-ui) không đổi.
  // GAP: xuống dòng giữa các thẻ của khung, giữ đúng như trước khi tách file để DOM không đổi.
  const GAP = '\n          ';
  const payField = (label, input) => `<label class="pay-field"><span>${label}</span>${input}</label>`;
  const entryForm = key => [
    '<tr class="pay-row pay-entry"><td class="pay pay-start pay-form" colspan="3"><div class="pay-form-card">',
    '<div class="pay-form-title">Ghi phiếu mới</div>',
    '<div class="pay-form-grid">',
    payField('Ngày trả', '<input class="empty-entry receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric">'
      + '<span class="cell-error receipt-date-error" role="status"></span>'),
    payField('Hình thức', `<select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${method}</option>`).join('')}</select>`),
    payField('Số tiền (VND)', '<input class="empty-entry receipt-amount" aria-label="Số tiền trả" inputmode="numeric">'
      + '<span class="cell-error receipt-amount-error" role="status"></span>'),
    payField('Tham chiếu', '<input class="receipt-reference" aria-label="Tham chiếu" maxlength="500" placeholder="Tùy chọn">'),
    `</div>${ctx.imageEntryBox?.(key) ?? ''}`,
    '<div class="pay-form-actions"><button type="button" class="receipt-save">Ghi phiếu</button></div></div></td></tr>',
  ].join(GAP);
  // Khoản thu Sheet (dòng sổ gốc): ngày Sheet, ghi chú, số tiền. Hình thức thu không suy từ ghi chú (V7-MIG còn mở);
  // ghi chú chỉ hiện khi không lặp lại cùng ngày. XOA-THU-GOC-01: tháng mở thì bấm số tiền để xóa hẳn.
  function legacyPayRow(receipt, locked) {
    const r = receipt.d;
    const day = sheetDay(r.raw_date);
    const noteText = r.note && r.note !== r.raw_date && sheetDay(r.note) !== day ? r.note : '';
    const payAmount = !locked
      ? `<td class="pay num row-delete" data-kind="legacy" data-id="${escape(receipt.id)}" tabindex="0" role="button" `
        + `aria-label="Xóa hẳn khoản thu sổ gốc ${escape(fmt(receipt.source_total_vnd))}" title="Bấm để xóa hẳn khoản thu này">`
        + `${fmt(receipt.source_total_vnd)}</td>`
      : num(fmt(receipt.source_total_vnd), 'pay');
    return `<tr class="pay-row legacy-pay">${cell(day, 'pay pay-start')}${cell(noteText, 'pay')}${payAmount}</tr>`;
  }
  // Audit P0 29/10/2026: phiếu đã hủy không chiếm chỗ phiếu thật — gom một dòng mờ, bấm Xem mới hiện từng phiếu.
  function voidRows(key, voided) {
    if (!voided.length) return '';
    const open = openVoided.has(key);
    const trace = row => `<tr class="void-trace"><td colspan="3"><s>${fmt(row.line.amount_vnd)}</s> · `
      + [escape(dateText(row.date)), row.outgoing ? '' : `hủy ${escape(dateText(row.voided_on))}`, escape(row.void_reason)].filter(Boolean).join(' · ')
      + `${ctx.imageClip?.(row) ?? ''}</td></tr>`;
    return `<tr class="void-summary"><td colspan="3">${voided.length} phiếu đã hủy, không tính tiền <button type="button" class="void-toggle" `
      + `data-month="${escape(key)}" aria-expanded="${open}">${open ? 'Ẩn' : 'Xem'}</button></td></tr>`
      + (open ? voided.map(trace).join('') : '');
  }
  // Các hàng của danh sách phiếu tháng `key`: legacy là cặp dòng sổ gốc của tháng (so-khach-v7-month-ui.js),
  // receipts là phiếu web và khoản cấn trừ đi đã gắn `line`; khung nhập hiện khi sổ ghi được (entryHere).
  function payRows(key, { legacy, receipts, entryHere, locked }) {
    const kept = receipts.filter(row => row.voided_by_event == null);
    const voided = voidRows(key, receipts.filter(row => row.voided_by_event != null));
    return legacy.map(line => line.receipt ? legacyPayRow(line.receipt, locked) : '').join('')
      + kept.map(receipt => `<tr class="pay-row">${payCells(receipt, key)}</tr>`).join('')
      + (entryHere ? entryForm(key) : '') + voided;
  }
  root.addEventListener('click', event => {
    const toggle = event.target.closest('.void-toggle');
    if (!toggle) return;
    if (!openVoided.delete(toggle.dataset.month)) openVoided.add(toggle.dataset.month);
    redraw();
    if (typeof CSS !== 'undefined') root.querySelector(`.void-toggle[data-month="${CSS.escape(toggle.dataset.month)}"]`)?.focus();
  });
  Object.assign(ctx, { payRows });
};
