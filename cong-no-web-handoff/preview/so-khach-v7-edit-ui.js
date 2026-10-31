/* Sổ khách V7 bản live — CHỜ KIỂM, sửa ô chuyến/phiếu, xóa dòng, chuyển tháng.
 * Tách từ so-khach-v7-ui.js (29/10/2026) để các PR ít đụng nhau; nạp trước so-khach-v7-ui.js,
 * dùng chung phạm vi của initLive qua ctx (xem so-khach-v7-ui.js). */
(window.SoKhachV7LiveParts ??= {}).edit = ctx => {
  'use strict';
  const { root, model, api, live, escape, fmt, spanOf, dateText, dateInput, monthKey, monthLabel, liveOpenMonth, methods, fieldNames, moved, ghosts, moneyText, referenceFields, reviewReasonText, todayIso, startOffset, openOffsetReceipt, showNotice, redraw, submit } = ctx;
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
      const trip = (ctx.snapshot?.trips ?? []).find(item => String(item.id) === button.dataset.trip);
      const why = Object.hasOwn(reviewReasonText, trip?.review_reason) ? reviewReasonText[trip.review_reason] : 'Nghi trùng';
      button.setAttribute('aria-expanded', 'true');
      row.insertAdjacentHTML('afterend', `<tr class="review-prompt" data-trip="${escape(button.dataset.trip)}"><td colspan="${spanOf(row)}"><div>Chuyến ${escape(trip?.container ?? '')} đang CHỜ KIỂM, chưa tính vào số dư — ${escape(why)}</div><label>Lý do kết luận <input class="review-reason" aria-label="Lý do kết luận" maxlength="500" autocomplete="off"></label> <button type="button" class="review-confirm">Tính vào sổ</button> <button type="button" class="review-reject">Loại, không tính</button> <button type="button" class="review-cancel">Thôi</button><span class="cell-error review-error" role="alert"></span></td></tr>`);
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
      ? (ctx.snapshot?.trips ?? []).find(row => String(row.id) === id)
      : (ctx.snapshot?.legacy_rows ?? []).find(row => String(row.id) === id);
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
        const lock = (ctx.snapshot?.month_locks ?? []).find(row => monthKey(row.month) === to);
        const locked = lock ? lock.locked : to !== (monthKey(ctx.snapshot?.today_month) || liveOpenMonth);
        const what = `${kind === 'trip' ? 'chuyến' : 'dòng'} ${rowValues(kind, before).container || 'phí lẻ'}`;
        td.closest('tr').insertAdjacentHTML('afterend', `<tr class="move-ask"><td colspan="${spanOf(td.closest('tr'))}">Ngày ${escape(dateText(value))} thuộc tháng ${monthLabel(to)}${locked ? ' (đã khóa)' : ''}. Chuyển ${escape(what)} sang tháng ${monthLabel(to)}? <button type="button" class="move-yes">Chuyển sang tháng ${monthLabel(to)}</button> <button type="button" class="move-no">Giữ ngày cũ (${escape(start)})</button></td></tr>`);
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
      if (kind === 'adjustment') {
        const adjustment = (ctx.snapshot?.adjustments ?? []).find(row => String(row.id) === id);
        row.insertAdjacentHTML('afterend', `<tr class="void-prompt delete-prompt" data-kind="adjustment" data-id="${escape(id)}"><td colspan="${spanOf(row)}">Xóa hẳn điều chỉnh cả tháng ${escape(fmt(adjustment?.amount_vnd))}${adjustment?.note ? ` (${escape(adjustment.note)})` : ''}? Nợ tháng bỏ đúng số này; Lịch sử vẫn ghi. <button type="button" class="confirm-delete">Xóa hẳn</button> <button type="button" class="cancel-delete">Thôi</button><span class="cell-error delete-error" role="alert"></span></td></tr>`);
        row.nextElementSibling.querySelector('.cancel-delete').focus();
        return;
      }
      const data = findRow(kind, id);
      const values = rowValues(kind, data);
      const paid = kind === 'legacy' && data?.kind === 'receipt';
      const amount = kind === 'trip'
        ? data?.status === 'confirmed' || data?.status === undefined ? `thành tiền ${fmt(data?.amount_vnd)}` : 'chưa tính vào số dư'
        : `đang tính ${fmt(values.counted_vnd)}`;
      const what = paid
        ? `khoản thu sổ gốc ${fmt(data.source_total_vnd)}${data.display?.container ? ` (${data.display.container})` : ''}`
        : `${kind === 'trip' ? 'chuyến' : 'dòng sổ gốc'} ${values.container || 'phí lẻ'} (${values.event_date ? dateText(values.event_date) : 'không ngày'}, ${amount})`;
      const extra = paid ? ` Nợ tăng lại ${fmt(data.source_total_vnd)}; số dư đầu không đổi, phần cộng ghi ở dòng điều chỉnh sổ gốc của tháng.`
        : kind === 'legacy' ? ' Số dư đầu không đổi; phần trừ ghi ở dòng điều chỉnh sổ gốc của tháng.' : '';
      row.insertAdjacentHTML('afterend', `<tr class="void-prompt delete-prompt" data-kind="${escape(kind)}" data-id="${escape(id)}"><td colspan="${spanOf(row)}">Xóa hẳn ${escape(what)}?${escape(extra)} <button type="button" class="confirm-delete">Xóa hẳn</button> <button type="button" class="cancel-delete">Thôi</button><span class="cell-error delete-error" role="alert"></span></td></tr>`);
      row.nextElementSibling.querySelector('.cancel-delete').focus();
    }
    async function confirmDelete(promptRow) {
      const { kind, id } = promptRow.dataset;
      const result = kind === 'trip'
        ? await submit('tripDelete', { trip_id: Number(id) })
        : kind === 'adjustment'
          ? await submit('monthAdjustDelete', { adjustment_id: Number(id) })
          : await submit('legacyDelete', { legacy_row_id: Number(id) });
      if (result?.message && promptRow.isConnected) promptRow.querySelector('.delete-error').textContent = result.message;
    }
    // Bảng Lịch sử: mở/đóng vẽ lại sổ (giữ ô đang gõ), tiêu điểm về nút "Lịch sử". Esc đóng bảng (audit UX 31/10/2026),
    // trừ khi Esc thuộc ô đang sửa ngoài bảng hoặc một hộp khác đang mở (hộp đó tự đóng trước).
    const setHistory = open => {
      ctx.historyOpen = open;
      if (ctx.snapshot) redraw();
      root.querySelector('.history-toggle')?.focus();
    };
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || !ctx.historyOpen || event.defaultPrevented) return;
      const inPanel = root.querySelector('.history-panel')?.contains(event.target);
      if (!inPanel && (event.target.matches?.('input,select,textarea') || event.target.closest?.('[role="dialog"],[aria-modal="true"],.fee-drawer,.image-viewer')
        || document.querySelector('[aria-modal="true"]:not([hidden]),.offset-backdrop'))) return;
      setHistory(false);
    });
    root.addEventListener('click', async event => {
      const infoEdit = event.target.closest('td.info-edit');
      if (infoEdit) { openInfoEdit(infoEdit); return; }
      const rowDelete = event.target.closest('td.row-delete');
      // Ô chọn chuyến để thêm phụ phí cho nhiều chuyến (PHU-PHI-01) nằm trong ô STT: bấm ô chọn không phải xóa dòng.
      if (rowDelete && !event.target.closest('.fee-pick')) { openDelete(rowDelete); return; }
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
      if (event.target.closest('.history-toggle')) { setHistory(!ctx.historyOpen); return; }
      if (event.target.closest('.history-close')) { setHistory(false); return; }
      if (event.target.closest('.retry-command')) { await api.retry(); return; }
      // Ô tìm khách nằm trên đầu trang, trôi mất khi cuộn: nút ở thanh tiêu đề đưa về đó và mở danh sách.
      if (event.target.closest('.change-customer')) { window.scrollTo(0, 0); live.showCustomers(); return; }
      const lock = event.target.closest('.month-lock');
      if (lock) { await submit('lock', { month: lock.dataset.month, locked: lock.getAttribute('aria-pressed') === 'true' }); return; }
      const add = event.target.closest('.add-month-adjustment');
      if (add) {
        const row = add.closest('tr');
        if (!row.previousElementSibling?.classList.contains('month-adjustment-input')) row.insertAdjacentHTML('beforebegin',
          // Ô số tiền nằm dưới cột Thành tiền: số cột đổi theo sổ (cột phụ phí riêng, cột Shipper chỉ hiện khi có dữ liệu).
          `<tr class="month-adjustment-input" data-month="${escape(add.dataset.month)}"><td colspan="${ctx.columnCount() - 4}">Điều chỉnh cả tháng · <label>Ghi chú <input class="month-note" aria-label="Ghi chú điều chỉnh cả tháng"></label></td><td><input class="month-amount" aria-label="Số điều chỉnh cả tháng" placeholder="+5.000.000"><span class="cell-error" role="status"></span></td><td class="pay pay-start" colspan="3"></td></tr>`);
        row.previousElementSibling.querySelector('.month-amount').focus(); return;
      }
      const editable = event.target.closest('td.editable');
      if (editable && !editable.querySelector('input')) {
        const trip = ctx.snapshot.trips.find(row => row.id === Number(editable.dataset.trip));
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
          const saved = ctx.snapshot.receipts.find(item => item.pid === pid);
          // Góp ý 29/10/2026: hộp hủy xếp dọc (tiêu đề, ô lý do đủ rộng, hai nút) cho vừa vùng phiếu thu hẹp.
          row.insertAdjacentHTML('afterend', `<tr class="void-prompt" data-pid="${escape(pid)}"><td colspan="${spanOf(row)}"><div class="void-box"><div class="void-head"><b>Hủy phiếu ${escape(pid)}</b> · ${fmt(saved.amount_vnd)} đ</div>`
            + `<p class="void-note">Số tiền phiếu không sửa được. Ghi sai thì hủy phiếu này rồi ghi phiếu mới.</p>`
            + `<label class="void-label">Lý do hủy (bắt buộc)<input class="void-reason" aria-label="Lý do hủy phiếu" placeholder="Ví dụ: ghi trùng, sai số tiền"></label><span class="cell-error" role="status"></span>`
            + `<div class="void-actions"><button type="button" class="cancel-void">Bỏ qua</button><button type="button" class="confirm-void">Hủy phiếu</button></div></div></td></tr>`);
          row.nextElementSibling.querySelector('input').focus(); return;
        }
        receipt.innerHTML = field === 'reference' ? `<input class="saved-receipt-input" aria-label="Sửa tham chiếu" maxlength="500" value="${escape(ctx.snapshot.receipts.find(item => item.pid === pid)?.reference)}">` : field === 'date' ? `<input class="saved-receipt-input" aria-label="Sửa ngày trả" value="${escape(receipt.textContent)}"><span class="cell-error receipt-date-error" role="status"></span>` :
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
        await saveNewReceipt(event.target.closest('tr'));
      }
      if (event.target.matches('.receipt-date')) { event.preventDefault(); event.target.closest('tr').querySelector('.receipt-amount').focus(); }
      if (event.target.matches('.void-reason')) { event.preventDefault(); event.target.closest('tr').querySelector('.confirm-void').click(); }
    });
    // Ghi phiếu mới: Enter ở ô số tiền/tham chiếu hoặc nút "Ghi phiếu" của khung nhập đi cùng một đường.
    async function saveNewReceipt(row) {
      try {
        row.querySelector('.receipt-date-error').textContent = '';
        if (row.querySelector('.receipt-method').value === 'CẤN TRỪ' && await startOffset(row)) return;
        const result = await submit('receipt', { date: dateInput(row.querySelector('.receipt-date').value), method: row.querySelector('.receipt-method').value,
          amount_vnd: moneyText(row.querySelector('.receipt-amount').value), ...referenceFields(row) });
        if (result?.error === 'FUTURE_RECEIPT_DATE') {
          row.querySelector('.receipt-date-error').textContent = result.message;
          row.querySelector('.receipt-date').focus();
        }
        // CHUNG-TU-01: phiếu đã ghi đúng tiền trước, rồi mới đính ảnh đã dán ở hàng nhập của tháng này.
        const done = api.lastOutcome();
        if (done?.status === 'saved') await ctx.afterReceiptSaved?.(row.closest('section')?.id.slice(6), done.result?.pid);
      }
      catch (error) { showNotice(error.message); }
    }
    root.addEventListener('click', async event => {
      const save = event.target.closest('.receipt-save');
      if (!save || save.disabled) return;
      save.disabled = true;
      try { await saveNewReceipt(save.closest('tr')); } finally { save.disabled = false; }
    });
    root.addEventListener('input', event => {
      if (event.target.matches('.receipt-date') && event.target.value.length === 10) event.target.closest('tr').querySelector('.receipt-amount').focus();
    });
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
    Object.assign(ctx, { openInfoEdit });
};
