/* Sổ khách V7 bản live — Cấn trừ hai sổ (CT-2SO).
 * Tách từ so-khach-v7-ui.js (29/10/2026) để các PR ít đụng nhau; nạp trước so-khach-v7-ui.js,
 * dùng chung phạm vi của initLive qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).offset = ctx => {
  'use strict';
  const { root, model, api, live, customerId, escape, spanOf, dateText, dateInput, methods, referenceFields, showNotice } = ctx;
    // ---- Cấn trừ hai sổ (CT-2SO): server giữ số dư và chặn; trang chỉ chọn sổ, hiện số trước → sau và gửi lệnh ----
    const OUTSIDE = model.OFFSET_OUTSIDE;
    const offsetState = { sources: [], selected: null, open: false, query: '', error: '', row: null };
    // SO-GON-02: hàng chọn sổ nguồn nằm ngay dưới hàng nhập, trong danh sách phiếu thu (3 cột).
    const sourceRowHtml = '<tr class="offset-source-row"><td class="pay pay-start offset-source-cell" colspan="3"></td></tr>';
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
      const preview = model.planOffsetPreview({ source, targetOutstandingVnd: BigInt(ctx.snapshot.total_outstanding_vnd), amountVnd });
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
      rowEl.insertAdjacentHTML('afterend', `<tr class="void-prompt offset-void-prompt" data-pair="${escape(pair)}" data-other-version="${otherLedger.version}"><td colspan="${spanOf(rowEl)}"><div class="offset-void-head">Hủy cấn trừ ở cả hai sổ: ${both} — <strong>${escape(cellEl.textContent.replace('-', ''))}</strong></div><label>Lý do <input class="offset-void-reason" aria-label="Lý do hủy cấn trừ" aria-required="true" autocomplete="off"></label> <button type="button" class="confirm-offset-void">Hủy cả hai dòng</button> <button type="button" class="cancel-void">Bỏ qua</button><span class="cell-error offset-void-error" role="alert"></span></td></tr>`);
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
    Object.assign(ctx, { todayIso, startOffset, openOffsetReceipt, offsetState, sourceRowHtml, renderSourceCell });
};
