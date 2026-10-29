/* Sổ khách V7 bản live — Debit note theo tháng công nợ (DEBIT-NOTE-01, specs/v7-debit-note.md).
 * Nút "Debit note" ở tiêu đề tháng mở hộp xem trước; Tải Excel (debit-note-xlsx.js) hoặc In / Lưu PDF (hộp in trình duyệt).
 * Chỉ đọc bản sổ đã tải và danh mục phụ phí; dòng phiếu và tổng do model dựng (ARCH-03). Không gửi lệnh nào. */
(window.SoKhachV7LiveParts ??= {}).debit = ctx => {
  'use strict';
  const { root, model, live, customerId, escape, monthLabel } = ctx;
  if (typeof document.createElement !== 'function') return;   // trang thử không có DOM thật
  const writer = DebitNoteXlsx;   // debit-note-xlsx.js nạp trước
  const dialog = document.createElement('div');
  dialog.className = 'debit-dialog';
  dialog.hidden = true;
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-label', 'Debit note');
  document.body.append(dialog);
  let open = null;   // { note, customer, todayIso, opener }

  const todayIso = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const notices = note => [
    note.missingCount ? `${note.missingCount} chuyến chưa có giá: Đơn giá và Tổng để trống, phiếu ghi CHƯA CHỐT.` : '',
    note.pendingCount ? `${note.pendingCount} chuyến đang CHỜ KIỂM không lên phiếu.` : '',
    note.adjustmentCount ? `Tháng có ${note.adjustmentCount} dòng điều chỉnh, không lên phiếu.` : '',
  ].filter(Boolean);

  function show(monthKey, opener) {
    const note = model.debitNote(ctx.snapshot ?? {}, monthKey, ctx.feeTypes ?? []);
    open = { note, customer: live.customerName(customerId) ?? `#${customerId}`, todayIso: todayIso(), opener };
    const lines = notices(note);
    dialog.innerHTML = `<div class="debit-panel"><header><h2>Debit note tháng ${escape(monthLabel(monthKey))}<small>${note.rows.length} dòng · ${escape(writer.statusText(note))}</small></h2>
      <button type="button" class="debit-excel">Tải Excel</button><button type="button" class="debit-print">In / Lưu PDF</button><button type="button" class="debit-close">Đóng</button></header>
      ${lines.length ? `<ul class="debit-notes" role="status">${lines.map(line => `<li>${escape(line)}</li>`).join('')}</ul>` : ''}
      <div class="debit-body">${writer.html(note, { customer: open.customer, todayIso: open.todayIso, escape })}</div></div>`;
    dialog.hidden = false;
    dialog.querySelector('.debit-excel').focus();
  }
  function close() {
    const opener = open?.opener;
    dialog.hidden = true; dialog.innerHTML = ''; open = null;
    const again = opener?.dataset?.month && root.querySelector(`.debit-open[data-month="${CSS.escape(opener.dataset.month)}"]`);
    (again || opener)?.focus?.();
  }
  function download() {
    const bytes = writer.xlsx(open.note, { customer: open.customer, todayIso: open.todayIso });
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
    const link = document.createElement('a');
    link.href = url; link.download = writer.fileName(open.customer, open.note.monthKey);
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  // In bằng khung ẩn để không bị chặn cửa sổ bật lên; chọn "Lưu dưới dạng PDF" trong hộp in để ra file PDF.
  function print() {
    const frame = document.createElement('iframe');
    frame.className = 'debit-print-frame';
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;width:0;height:0;border:0;right:0;bottom:0';
    document.body.append(frame);
    const sheet = dialog.querySelector('.debit-body').innerHTML;
    const title = writer.fileName(open.customer, open.note.monthKey).replace(/\.xlsx$/, '');
    frame.contentDocument.open();
    frame.contentDocument.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escape(title)}</title><style>${PRINT_CSS}</style></head><body>${sheet}</body></html>`);
    frame.contentDocument.close();
    frame.contentWindow.focus();
    frame.contentWindow.print();
    setTimeout(() => frame.remove(), 60000);
  }
  // Bảng phiếu dùng chung một bộ kiểu cho hộp xem trước và bản in.
  const SHEET_CSS = `.dn-sheet{font:10px Arial,sans-serif;color:#000;border-collapse:collapse;width:100%;table-layout:fixed}.dn-sheet td,.dn-sheet th{padding:2px 4px;overflow:hidden}
    .dn-title{background:#2e75b6;color:#fff;font-size:22px;font-weight:700;text-align:center;padding:6px}
    .dn-date-label{text-align:right;font-weight:700}.dn-date{background:#00f;color:#fff;font-weight:700;text-align:right}
    .dn-label,.dn-strong{font-weight:700}.dn-mail{color:#0563c1;font-weight:700;text-decoration:underline}.dn-gap td{height:8px}
    .dn-head th{background:#ffc000;color:#1f4e79;border:1px solid #000;font-size:10px;vertical-align:middle}
    .dn-sheet tr:not(.dn-head) td{white-space:nowrap}.dn-head ~ tr td{border:1px solid #000;font-size:9px}
    .dn-sheet .num{text-align:right}.dn-sheet .no{text-align:right}
    .dn-total td{font-weight:700;color:#1f4e79;text-align:center}.dn-total .num{color:#000}
    .dn-sheet tr:last-child td{border:0;text-align:right;font-size:8px}
    .dn-sheet *{-webkit-print-color-adjust:exact;print-color-adjust:exact}`;
  const PRINT_CSS = `@page{size:A4 landscape;margin:8mm}body{margin:0}${SHEET_CSS}`;
  const style = document.createElement('style');
  style.textContent = SHEET_CSS;
  document.head.append(style);

  root.addEventListener('click', event => {
    const button = event.target.closest('.debit-open');
    if (button) show(button.dataset.month, button);
  });
  dialog.addEventListener('click', event => {
    if (event.target.closest('.debit-close') || event.target === dialog) close();
    else if (event.target.closest('.debit-excel')) download();
    else if (event.target.closest('.debit-print')) print();
  });
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key !== 'Tab') return;   // giữ Tab trong hộp
    const items = [...dialog.querySelectorAll('button')];
    const at = items.indexOf(document.activeElement);
    if (event.shiftKey && at <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
    else if (!event.shiftKey && at === items.length - 1) { event.preventDefault(); items[0].focus(); }
  });
  ctx.debitBusy = () => !dialog.hidden;
};
