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
  const SHEET_CSS = `.dn-sheet{font:10px/1.35 Arial,sans-serif;color:#1c2430;background:#fff}
    .dn-top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding-bottom:10px;border-bottom:2px solid #1b3a5c}
    .dn-co{font-size:17px;font-weight:700;color:#1b3a5c}.dn-addr{color:#5f6b7a;font-size:9px;margin-top:2px}
    .dn-doc{text-align:right;white-space:nowrap}.dn-title{font-size:24px;font-weight:700;color:#1b3a5c;letter-spacing:1px}.dn-sub{color:#5f6b7a;font-size:10px}
    .dn-meta{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin:12px 0}
    .dn-label{font-size:8px;font-weight:700;color:#5f6b7a;letter-spacing:1px}.dn-customer{font-size:15px;font-weight:700;color:#1b3a5c;margin-top:2px}
    .dn-info{border-collapse:collapse;background:#f4f6f9;min-width:260px}.dn-info th{text-align:left;color:#1b3a5c;padding:3px 10px;font-size:9px}.dn-info td{text-align:right;padding:3px 10px;font-size:9px}
    .dn-table{width:100%;border-collapse:collapse;table-layout:fixed}.dn-table th,.dn-table td{padding:3px 3px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
    .dn-group th{background:#1b3a5c;color:#fff;font-size:9px;font-weight:700;letter-spacing:.3px;border-right:1px solid #fff}.dn-group th:last-child{border-right:0}
    .dn-head th{background:#e9eef4;color:#1b3a5c;font-size:8px;font-weight:700;border-bottom:1px solid #1b3a5c;white-space:normal;vertical-align:middle;line-height:1.2}
    .dn-head small{display:block;font-weight:400;font-size:7.5px;color:#5f6b7a}
    .dn-table tbody td{border-bottom:1px solid #d5dbe3;font-size:9px}.dn-table tbody tr:nth-child(even) td{background:#fafbfc}
    .dn-table .num{text-align:right;font-variant-numeric:tabular-nums}.dn-table .no{text-align:center;color:#5f6b7a}
    .dn-total td{border-top:2px solid #1b3a5c;font-weight:700;color:#1b3a5c;padding-top:6px}.dn-total td:first-child{text-align:right;font-size:10px}.dn-total .num{font-size:12px;overflow:visible}
    .dn-foot{margin-top:6px}.dn-status-row{text-align:right}
    .dn-status{display:inline-block;font-weight:700;font-size:9px;padding:2px 8px;border-radius:3px}.dn-status.is-done{color:#1e7b4f;background:#e6f4ec}.dn-status.is-open{color:#b4690e;background:#fdf1df}
    .dn-signs{display:flex;justify-content:space-between;padding:14px 80px 0}.dn-sign{text-align:center;min-width:180px}
    .dn-sign b{display:block;color:#1b3a5c;font-size:9px}.dn-sign i{display:block;color:#5f6b7a;font-size:8px;margin-top:44px}
    .dn-sheet *{-webkit-print-color-adjust:exact;print-color-adjust:exact}`;
  // In: tiêu đề cột lặp mỗi trang (thead), dòng TỔNG chỉ in một lần sau dòng cuối, không cắt ngang dòng/ô ký.
  const PRINT_CSS = `@page{size:A4 landscape;margin:8mm}body{margin:0}${SHEET_CSS}
    .dn-table thead{display:table-header-group}.dn-table tfoot{display:table-row-group}.dn-table tr,.dn-foot{page-break-inside:avoid}`;
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
  ctx.busyChecks.push(() => !dialog.hidden);
};
