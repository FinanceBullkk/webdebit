/* Sổ khách V7 bản live — Ghi phiếu thu từ Sheet (specs/v7-receipt-queue.md, THU-SHEET-01).
 * Server chọn phiếu chắc chắn (READY), trang chỉ hiện và gửi một lệnh cho cả lô; phiếu còn lại
 * nằm ở "Phiếu thu Sheet cần xem". Nạp trước so-khach-v7-ui.js, dùng chung phạm vi qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).receipts = ctx => {
  'use strict';
  const { root, model, api, customerId, escape, showNotice, renderSnapshot } = ctx;
  // null | 'confirm' | 'review' | { error }; giữ qua lần vẽ lại.
  let view = null;
  let approval = null;
  const money = value => model.formatVnd(model.sheetVnd(value));
  const day = iso => /^\d{4}-\d\d-\d\d$/.test(iso ?? '') ? `${iso.slice(8)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '';
  const month = key => `${Number(String(key).slice(5, 7))}/${String(key).slice(0, 4)}`;
  const note = item => item.note ? ` · Sheet ghi "${escape(item.note)}"` : '';

  function button(data, active) {
    const count = active ? data.sheet_receipts?.ready_count : 0;
    return count ? `<button class="receipt-approve">Ghi ${count} phiếu thu từ Sheet</button>` : '';
  }

  function panel(data) {
    const ready = data.sheet_receipts?.ready ?? [];
    if (view === 'confirm' && ready.length) {
      const plan = model.planSheetReceipts(ready, data.total_outstanding_vnd);
      const lines = ready.map(item => `<li><div class="what">${day(item.date)} · <strong>${money(item.amount_vnd)} đ</strong> · nợ tháng ${month(item.debt_month)} trên Sheet${note(item)}</div></li>`).join('');
      return `<div class="price-panel confirm receipt-panel" role="region" aria-label="Xác nhận ghi phiếu thu từ Sheet"><p><strong>Ghi ${plan.count} phiếu thu từ Sheet, tổng ${model.formatVnd(plan.totalVnd)} đ?</strong> Tổng còn nợ giảm từ ${model.formatVnd(plan.beforeVnd)} xuống ${model.formatVnd(plan.afterVnd)}. Phiếu tự phân bổ theo nợ cũ trước.</p><ul>${lines}</ul><div class="price-actions"><button type="button" class="receipt-write primary">Ghi ${plan.count} phiếu</button><button type="button" class="receipt-cancel">Thôi</button></div></div>`;
    }
    if (view?.error) return `<div class="price-panel err receipt-panel" role="alert"><p><strong>Chưa ghi phiếu thu nào.</strong> ${escape(view.error)}</p><div class="price-actions"><button type="button" class="receipt-reload primary">Tải lại sổ</button></div></div>`;
    if (view !== 'review') return '';
    const line = item => {
      const what = `Nợ tháng ${month(item.debt_month)} · ${money(item.amount_vnd)} đ${note(item)}`;
      if (item.status === 'NO_DATE') return `<li><div class="what">${what}<small>Sheet không ghi ngày thu. Hỏi ngày thu rồi nhập tay ở hàng phiếu thu.</small></div></li>`;
      if (item.status === 'FUTURE_DATE') return `<li><div class="what">${what}<small>Ngày thu ${day(item.date)} sau hôm nay. Sửa ngày trên Sheet.</small></div></li>`;
      if (item.status === 'WEB_DELETED') return `<li><div class="what">${what}<small>Web đã xóa khoản thu sổ gốc này, Sheet vẫn còn. Muốn trừ lại thì nhập phiếu tay.</small></div></li>`;
      const old = (item.web_legacy ?? []).map(entry => `${money(entry.amount_vnd)} đ`).join(', ');
      const first = item.web_legacy?.[0]?.id;
      return `<li><div class="what">${what}<small>Sheet đã sửa phiếu thu tháng ${month(item.debt_month)}: web còn khoản thu sổ gốc ${old} không thấy trên Sheet. Xóa khoản cũ (bấm ô số tiền của nó) thì lần lấy Sheet sau phiếu này vào lô ghi.</small></div>${first == null ? '' : `<button type="button" class="receipt-goto" data-id="${escape(first)}">Xem khoản cũ</button>`}</li>`;
    };
    return `<div class="price-panel receipt-panel" role="region" aria-label="Phiếu thu từ Sheet cần xem"><ul>${(data.sheet_receipts?.review ?? []).map(line).join('')}</ul></div>`;
  }

  function decorate(data, active) {
    const receipts = active ? data.sheet_receipts ?? {} : {};
    if (!receipts.ready_count && view === 'confirm') view = null;
    const review = receipts.review ?? [];
    if (!review.length && view === 'review') view = null;
    const strip = review.length ? `<div class="price-strip receipt-strip">Phiếu thu Sheet cần xem: <strong>${review.length}</strong> <button type="button" class="receipt-review-toggle" aria-expanded="${view === 'review'}">${view === 'review' ? 'Đóng' : 'Xem'}</button></div>` : '';
    root.querySelector('.book-head')?.insertAdjacentHTML('afterend', strip + panel(data));
  }

  root.addEventListener('click', async event => {
    const target = event.target.closest('.receipt-approve,.receipt-cancel,.receipt-review-toggle,.receipt-reload,.receipt-write,.receipt-goto');
    if (!target || target.disabled || !ctx.snapshot) return;
    if (target.matches('.receipt-approve,.receipt-cancel,.receipt-review-toggle')) {
      view = target.matches('.receipt-approve') ? 'confirm'
        : target.matches('.receipt-review-toggle') && view !== 'review' ? 'review' : null;
      renderSnapshot(ctx.snapshot);
      root.querySelector(view === 'confirm' ? '.receipt-write' : '.receipt-review-toggle')?.focus();
      return;
    }
    if (target.matches('.receipt-goto')) {
      const cell = root.querySelector(`td.row-delete[data-kind="legacy"][data-id="${CSS.escape(target.dataset.id)}"]`);
      if (!cell) { showNotice('Tháng của khoản cũ đang khóa. Mở khóa tháng rồi bấm ô số tiền để xóa.'); return; }
      cell.scrollIntoView({ block: 'center' });
      cell.focus();
      return;
    }
    if (target.matches('.receipt-reload')) {
      view = null;
      approval = null;
      await api.read().catch(() => showNotice('Không tải được sổ mới. Thử lại.'));
      return;
    }
    // Ghi cả lô: giữ nguyên khóa khi chưa rõ kết quả để bấm lại không ghi trùng.
    if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
    approval ??= { customer_id: customerId, expected_version: ctx.snapshot.version,
      snapshot_sha256: ctx.snapshot.sheet_receipts.snapshot_sha256, idempotency_key: crypto.randomUUID() };
    target.disabled = true;
    let response, result;
    try {
      response = await fetch('/api/v7/sheet/receipts', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(approval) });
      result = await response.json();
    } catch {
      target.disabled = false;
      showNotice('Chưa rõ kết quả ghi phiếu thu. Tải lại sổ để kiểm tra trước khi thử lại.');
      return;
    }
    approval = null;
    if (!response.ok) {
      view = { error: result.error === 'STALE_SHEET' ? 'Sheet đã đổi sau khi mở sổ.'
        : result.error === 'STALE_LEDGER' ? 'Sổ vừa thay đổi.' : result.message || 'Không ghi được phiếu thu từ Sheet.' };
      renderSnapshot(ctx.snapshot);
      return;
    }
    view = null;
    try { await api.read(); } catch { showNotice('Đã ghi phiếu thu; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
    showNotice(result.complete === false
      ? `Đã ghi ${result.written} phiếu thu; còn ${result.remaining} phiếu chưa ghi. Bấm "Ghi … phiếu thu từ Sheet" để ghi tiếp.`
      : `Đã ghi ${result.written} phiếu thu từ Sheet.`);
  });

  Object.assign(ctx, { receiptButton: button, receiptsAfterRender: decorate });
};
