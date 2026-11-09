/* Sổ khách V7 bản live — Đối chiếu Sheet và ghi giá từ Sheet.
 * Tách từ so-khach-v7-ui.js (29/10/2026) để các PR ít đụng nhau; nạp trước so-khach-v7-ui.js,
 * dùng chung phạm vi của initLive qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).sheet = ctx => {
  'use strict';
  const { root, model, api, customerId, escape, spanOf, dateText, monthKey, monthLabel, sheetFieldLabel, resolvableSheetFields, showNotice, renderSnapshot, submit } = ctx;
    // Ghi giá từ Sheet (specs/v7-price-queue.md): null | 'confirm' | 'review' | { error }; giữ qua lần vẽ lại.
    let priceView = null;
    let priceApproval = null;
    const conflictSelection = new Set();
    // DUYET-TAI-HANG-01 (9/11/2026): chuyến mới duyệt ngay ở hàng của nó; thanh việc chỉ báo số và nút "Đến chuyến".
    const newRows = data => (data.sheet_sync?.items ?? []).filter(item => item.sync_state === 'NEW' && item.source_row != null);
    function newStrip(data, active) {
      const count = active ? newRows(data).length : 0;
      return count ? `<div class="price-strip sheet-new-strip"><span><strong>${count}</strong> chuyến mới từ Sheet chờ duyệt</span><button type="button" class="sheet-new-next">Đến chuyến${count > 1 ? ' tiếp' : ''}</button></div>` : '';
    }
    // ---- Ghi giá từ Sheet: server chọn dòng chắc chắn (READY), trang chỉ hiện và gửi một lệnh cho cả lô ----
    const priceRows = data => new Map([...(data.trips ?? []).map(row => [`trip-${row.id}`, row]),
      ...(data.legacy_rows ?? []).map(row => [`legacy-${row.id}`, row])]);
    const vndText = value => value == null ? '' : model.formatVnd(model.sheetVnd(value));
    const conflictKey = item => `${item.target_kind}:${item.target_id}:${item.source_row}`;
    const selectedConflicts = data => (data.sheet_prices?.review ?? []).filter(item =>
      item.status === 'CONFLICT' && item.batchable && conflictSelection.has(conflictKey(item)));
    function priceMonths(data, items) {
      const rows = priceRows(data);
      const keys = [...new Set(items.map(item => monthKey(rows.get(`${item.target_kind}-${item.target_id}`)?.month)).filter(Boolean))].sort();
      return keys.map(key => `tháng ${monthLabel(key)}`).join(', ');
    }
    function pricePanel(data) {
      const ready = data.sheet_prices?.ready ?? [];
      if (priceView === 'confirm' && ready.length) {
        const plan = model.planSheetPrices(ready, data.total_outstanding_vnd);
        return `<div class="price-panel confirm" role="region" aria-label="Xác nhận ghi giá từ Sheet"><p><strong>Ghi giá Sheet cho ${plan.count} chuyến ${escape(priceMonths(data, ready))}?</strong> Tổng còn nợ tăng <strong>${model.formatVnd(plan.increaseVnd)} đ</strong> (từ ${model.formatVnd(plan.beforeVnd)} lên ${model.formatVnd(plan.afterVnd)}). Phiếu thu tự phân bổ lại theo nợ cũ trước.</p><div class="price-actions"><button type="button" class="price-write primary">Ghi ${plan.count} giá</button><button type="button" class="price-cancel">Thôi</button></div></div>`;
      }
      if (priceView === 'conflict-confirm') {
        const chosen = selectedConflicts(data);
        const plan = model.planSheetPriceConflicts(chosen, data.total_outstanding_vnd);
        return `<div class="price-panel confirm" role="region" aria-label="Xác nhận lấy giá Sheet đã chọn"><p><strong>Lấy Sheet cho ${chosen.length} dòng đã chọn?</strong> Tổng còn nợ dự kiến ${model.formatVnd(plan.beforeVnd)} đ → ${model.formatVnd(plan.afterVnd)} đ (chênh ${model.formatVnd(plan.deltaVnd)} đ). Phiếu thu tự phân bổ lại theo nợ cũ trước.</p><ul>${chosen.map(item => `<li><div class="what">${escape(item.container)} · ${escape(dateText(item.date))} · giá Web ${vndText(item.web_unit_price_vnd)} đ → Sheet ${vndText(item.sheet_unit_price_vnd)} đ<small>Phụ phí Web ${vndText(item.web_other_fee_vnd ?? '0')} đ → Sheet ${vndText(item.sheet_other_fee_vnd ?? '0')} đ</small></div></li>`).join('')}</ul><div class="price-actions"><button type="button" class="price-conflict-write primary">Ghi ${chosen.length} giá</button><button type="button" class="price-conflict-cancel">Quay lại</button></div></div>`;
      }
      if (priceView?.error) return `<div class="price-panel err" role="alert"><p><strong>${priceView.unknown ? 'Chưa rõ kết quả.' : 'Chưa ghi giá nào.'}</strong> ${escape(priceView.error)}</p><div class="price-actions"><button type="button" class="price-reload primary">Tải lại sổ</button></div></div>`;
      if (priceView !== 'review') return '';
      const rows = priceRows(data);
      const line = item => {
        const what = `${escape(item.container)} · ${escape(dateText(item.date))}`;
        const month = monthKey(rows.get(`${item.target_kind}-${item.target_id}`)?.month);
        if (item.status === 'MONTH_LOCKED') return `<li><div class="what">${what} · giá Sheet ${vndText(item.sheet_unit_price_vnd)} đ<small>Tháng ${monthLabel(month)} đang khóa nên chưa ghi được.</small></div><button type="button" class="price-unlock" data-month="${escape(month)}-01">Mở khóa tháng ${Number(month.slice(5))}</button></li>`;
        if (item.status === 'CONFLICT') return `<li>${item.batchable ? `<input type="checkbox" class="price-conflict-select" aria-label="Chọn ${what} để lấy giá Sheet" data-key="${escape(conflictKey(item))}" ${conflictSelection.has(conflictKey(item)) ? 'checked' : ''}>` : ''}<div class="what">${what} · Web ${vndText(item.web_unit_price_vnd)} đ · Sheet ${vndText(item.sheet_unit_price_vnd)} đ<small>${item.batchable ? 'Web đã có giá khác Sheet.' : 'Cần xử lý riêng; không thể ghi hàng loạt.'}</small></div><button type="button" class="price-use-sheet" data-kind="${escape(item.target_kind)}" data-id="${escape(item.target_id)}" data-price="${escape(item.sheet_unit_price_vnd)}" data-fee="${escape(item.sheet_other_fee_vnd ?? '')}">Lấy Sheet</button></li>`;
        if (item.status === 'MANUAL') return `<li><div class="what">${what} · giá Sheet ${vndText(item.sheet_unit_price_vnd)} đ · phụ phí ${vndText(item.sheet_other_fee_vnd)} đ<small>Sheet có số âm (giảm trừ). Nhập tay tại ô của chuyến.</small></div></li>`;
        return `<li><div class="what">Dòng Sheet ${escape(item.source_row)} · ${what} · giá Sheet ${vndText(item.sheet_unit_price_vnd)} đ<small>Khớp nhiều chuyến cùng container. Điền giá tay tại ô của đúng chuyến.</small></div></li>`;
      };
      const selectable = (data.sheet_prices?.review ?? []).filter(item => item.status === 'CONFLICT' && item.batchable);
      const actions = selectable.length ? `<div class="price-conflict-actions"><button type="button" class="price-conflict-all">${conflictSelection.size === selectable.length ? 'Bỏ chọn tất cả' : `Chọn ${selectable.length} dòng đủ điều kiện`}</button><button type="button" class="price-conflict-confirm primary" ${conflictSelection.size ? '' : 'disabled'}>Xem trước ${conflictSelection.size} giá đã chọn</button></div>` : '';
      return `<div class="price-panel" role="region" aria-label="Giá từ Sheet cần xem">${actions}<ul>${(data.sheet_prices?.review ?? []).map(line).join('')}</ul></div>`;
    }
    function decoratePrices(data, active) {
      const prices = active ? data.sheet_prices ?? {} : {};
      for (const item of prices.ready ?? []) {
        const row = root.querySelector(`[data-row="${CSS.escape(`${item.target_kind}-${item.target_id}`)}"]`);
        if (!row) continue;
        row.classList.add('from-sheet');
        const price = row.querySelector('[data-field="unit_price_vnd"]');
        const fee = row.querySelector('[data-field="other_fee_vnd"]');
        if (price) price.innerHTML = `<span class="sheet-price">${vndText(item.sheet_unit_price_vnd)}<small>giá Sheet</small></span>`;
        if (fee && item.sheet_other_fee_vnd != null) fee.innerHTML = `<span class="sheet-price">${vndText(item.sheet_other_fee_vnd)}</span>`;
        if (fee?.nextElementSibling) fee.nextElementSibling.innerHTML = `<span class="sheet-price">${model.formatVnd(model.sheetPriceAmount(item))}<small>chưa tính</small></span>`;
      }
      if (!prices.ready_count && priceView === 'confirm') priceView = null;
      const review = prices.review ?? [];
      const available = new Set(review.filter(item => item.status === 'CONFLICT' && item.batchable).map(conflictKey));
      for (const key of conflictSelection) if (!available.has(key)) conflictSelection.delete(key);
      if (priceView === 'conflict-confirm' && !conflictSelection.size) priceView = 'review';
      if (!review.length && priceView === 'review') priceView = null;
      const strip = review.length ? `<div class="price-strip">Giá từ Sheet cần xem: <strong>${review.length}</strong> <button type="button" class="price-review-toggle" aria-expanded="${priceView === 'review'}">${priceView === 'review' ? 'Đóng' : 'Xem'}</button></div>` : '';
      // SO-GON-06: dải "cần xem" là một ô trong thanh việc; khung mở ra nằm ngay dưới thanh.
      root.querySelector('.book-tasks')?.insertAdjacentHTML('afterbegin', newStrip(data, active));
      root.querySelector('.book-tasks')?.insertAdjacentHTML('beforeend', strip);
      root.querySelector('.book-bar')?.insertAdjacentHTML('afterend', pricePanel(data));
    }
    const openSheetDetail = button => {
      const trip = ctx.snapshot.sheet_sync.items[Number(button.dataset.index)];
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
          ? `<small class="sheet-choice-hint">Sheet sửa booking sau khi chuyến đã vào sổ. Sổ giữ booking cũ, tiền không đổi.</small><div class="sheet-choice-actions"><button type="button" data-sheet-decision="keep_web" data-sheet-field="booking">Đã xem, hết báo</button></div>`
          : `<div class="sheet-choice-actions"><button type="button" data-sheet-decision="keep_web" data-sheet-field="${escape(field)}">Giữ web</button><button type="button" data-sheet-decision="use_sheet" data-sheet-field="${escape(field)}">Lấy Sheet</button></div>`;
        return `<div class="sheet-detail-field${changed ? ' sheet-value-conflict' : ''}"><span class="sheet-detail-label">${escape(sheetFieldLabel(field))}</span>${changed ? `<span class="sheet-detail-web">Web: ${escape(webValue)}</span><strong>Sheet: ${escape(value)}</strong>${actions}` : `<strong>${escape(value)}</strong>`}</div>`;
      }).join('');
      const detailRow = `<tr class="sheet-detail"><td colspan="${spanOf(tableRow)}"><div class="sheet-detail-content"><div class="sheet-detail-heading"><strong>↳ Dữ liệu từ Sheet</strong><span>${escape(trip.container)}</span></div><div class="sheet-detail-fields">${sheetFields}</div><p class="sheet-detail-status" role="status" hidden></p></div></td></tr>`;
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
      const trip = ctx.snapshot.sheet_sync.items[index];
      if (!trip || action.disabled) return;
      const rowKey = `${trip.existing_kind}-${trip.existing_id}`;
      // Báo ngay trong khung: băng thông báo đầu trang thường nằm ngoài màn hình khi đang ở dòng dưới.
      const detailNotice = text => {
        showNotice(text);
        const status = detail.isConnected && detail.querySelector('.sheet-detail-status');
        if (status) { status.textContent = text; status.hidden = false; }
      };
      const lockedText = 'Tháng đang khóa. Mở khóa tháng (nút 🔒 ở đầu tháng) rồi bấm Lấy Sheet.';
      // Lấy Sheet đi qua ổ khóa tháng (24/10/2026); chặn trước khi gửi để khỏi nhận lỗi muộn.
      if (action.dataset.sheetDecision === 'use_sheet' && detail.closest('table.ledger')?.classList.contains('locked')) {
        detailNotice(lockedText);
        return;
      }
      if (action.dataset.sheetField === 'event_date' && action.dataset.sheetDecision === 'use_sheet') {
        // Lấy ngày Sheet = sửa ô ngày như gõ tay: hỏi khi sang tháng khác, tháng khóa thì không sửa được.
        const dateCell = root.querySelector(`td.info-edit[data-kind="${CSS.escape(trip.existing_kind)}"][data-id="${CSS.escape(String(trip.existing_id))}"][data-field="event_date"]`);
        if (!dateCell) { detailNotice(lockedText); return; }
        detail.remove();
        const diffButton = row.querySelector('.sheet-diff');
        if (diffButton) { diffButton.textContent = 'Xem'; diffButton.setAttribute('aria-expanded', 'false'); }
        ctx.openInfoEdit(dateCell);
        const input = dateCell.querySelector('input');
        input.value = dateText(trip.event_date);
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        return;
      }
      action.disabled = true;
      try {
        const response = await fetch('/api/v7/sheet/resolve', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ customer_id: customerId, expected_version: ctx.snapshot.version,
            snapshot_sha256: ctx.snapshot.sheet_sync.snapshot_sha256, source_row: trip.source_row,
            target_kind: trip.existing_kind, target_id: trip.existing_id, field: action.dataset.sheetField,
            decision: action.dataset.sheetDecision, idempotency_key: crypto.randomUUID() }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.message || 'Không xử lý được dòng đối chiếu.');
        await api.read();
        const nextButton = root.querySelector(`[data-row="${CSS.escape(rowKey)}"] .sheet-diff`);
        if (nextButton) openSheetDetail(nextButton);
        showNotice('Đã xử lý đối chiếu.');
      } catch (error) { detailNotice(error.message); action.disabled = false; }
    });
    root.addEventListener('change', event => {
      const checkbox = event.target.closest('.price-conflict-select');
      if (!checkbox) return;
      if (checkbox.checked) conflictSelection.add(checkbox.dataset.key);
      else conflictSelection.delete(checkbox.dataset.key);
      renderSnapshot(ctx.snapshot);
      root.querySelector(`.price-conflict-select[data-key="${CSS.escape(checkbox.dataset.key)}"]`)?.focus();
    });
    root.addEventListener('click', async event => {
      const target = event.target.closest('.price-approve,.price-cancel,.price-review-toggle,.price-reload,.price-write,.price-unlock,.price-use-sheet,.price-conflict-all,.price-conflict-confirm,.price-conflict-cancel,.price-conflict-write');
      if (!target || target.disabled || !ctx.snapshot) return;
      if (target.matches('.price-conflict-all')) {
        const available = (ctx.snapshot.sheet_prices?.review ?? []).filter(item => item.status === 'CONFLICT' && item.batchable);
        if (conflictSelection.size === available.length) conflictSelection.clear();
        else for (const item of available) conflictSelection.add(conflictKey(item));
        renderSnapshot(ctx.snapshot);
        root.querySelector('.price-conflict-all')?.focus();
        return;
      }
      if (target.matches('.price-conflict-confirm,.price-conflict-cancel')) {
        priceView = target.matches('.price-conflict-confirm') ? 'conflict-confirm' : 'review';
        renderSnapshot(ctx.snapshot);
        root.querySelector(priceView === 'conflict-confirm' ? '.price-conflict-write' : '.price-conflict-confirm')?.focus();
        return;
      }
      if (target.matches('.price-conflict-write')) {
        if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
        const conflicts = selectedConflicts(ctx.snapshot).map(({ target_kind, target_id, source_row }) =>
          ({ target_kind, target_id, source_row }));
        if (!conflicts.length) return;
        const request = { customer_id: customerId, expected_version: ctx.snapshot.version,
          snapshot_sha256: ctx.snapshot.sheet_prices.snapshot_sha256, idempotency_key: crypto.randomUUID(), conflicts };
        target.disabled = true;
        let response, result;
        try {
          response = await fetch('/api/v7/sheet/prices/conflicts', { method: 'POST',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
          result = await response.json();
        } catch {
          priceView = { error: 'Tải lại sổ để kiểm tra trước khi thử lại.', unknown: true };
          renderSnapshot(ctx.snapshot);
          return;
        }
        if (!response.ok) {
          priceView = { error: result.message || 'Giá hoặc sổ đã đổi. Tải lại rồi xem lại.',
            unknown: result.error === 'RESULT_UNKNOWN' };
          renderSnapshot(ctx.snapshot);
          return;
        }
        conflictSelection.clear();
        priceView = 'review';
        try { await api.read(); } catch { showNotice('Đã ghi giá; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
        showNotice(result.complete === false
          ? `Đã ghi ${result.written} giá; còn ${result.remaining} giá chưa ghi (${result.error}). Xem lại các dòng còn lệch.`
          : `Đã ghi ${result.written} giá từ Sheet.`);
        return;
      }
      if (target.matches('.price-approve,.price-cancel,.price-review-toggle')) {
        priceView = target.matches('.price-approve') ? 'confirm'
          : target.matches('.price-review-toggle') && priceView !== 'review' ? 'review' : null;
        renderSnapshot(ctx.snapshot);
        root.querySelector(priceView === 'confirm' ? '.price-write' : '.price-review-toggle')?.focus();
        return;
      }
      if (target.matches('.price-reload')) {
        priceView = null;
        priceApproval = null;
        conflictSelection.clear();
        await api.read().catch(() => showNotice('Không tải được sổ mới. Thử lại.'));
        return;
      }
      if (target.matches('.price-unlock')) { ctx.askLock(target, target.dataset.month, false); return; }
      if (target.matches('.price-use-sheet')) {
        const { kind, id, price, fee } = target.dataset;
        target.disabled = true;
        if (kind === 'trip') await submit('price', { trip_id: Number(id), unit_price_vnd: price, other_fee_vnd: fee || null });
        else if (await submit('legacyEdit', { legacy_row_id: Number(id), field: 'unit_price_vnd', value: price }) && fee)
          await submit('legacyEdit', { legacy_row_id: Number(id), field: 'other_fee_vnd', value: fee });
        return;
      }
      // Ghi cả lô: giữ nguyên khóa khi chưa rõ kết quả để bấm lại không ghi trùng.
      if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
      priceApproval ??= { customer_id: customerId, expected_version: ctx.snapshot.version,
        snapshot_sha256: ctx.snapshot.sheet_prices.snapshot_sha256, idempotency_key: crypto.randomUUID() };
      target.disabled = true;
      let response, result;
      try {
        response = await fetch('/api/v7/sheet/prices', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(priceApproval) });
        result = await response.json();
      } catch {
        target.disabled = false;
        showNotice('Chưa rõ kết quả ghi giá. Tải lại sổ để kiểm tra trước khi thử lại.');
        return;
      }
      priceApproval = null;
      if (!response.ok) {
        priceView = { error: result.error === 'STALE_SHEET' ? 'Sheet đã đổi sau khi mở sổ.'
          : result.error === 'STALE_LEDGER' ? 'Sổ vừa thay đổi.' : result.message || 'Không ghi được giá từ Sheet.' };
        renderSnapshot(ctx.snapshot);
        return;
      }
      priceView = null;
      try { await api.read(); } catch { showNotice('Đã ghi giá; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
      showNotice(result.complete === false
        ? `Đã ghi ${result.written} giá; còn ${result.remaining} giá chưa ghi. Bấm "Ghi … giá từ Sheet" để ghi tiếp.`
        : `Đã ghi ${result.written} giá từ Sheet.`);
    });
    // Duyệt một chuyến tại hàng: cùng lệnh /api/v7/sheet/approve, chỉ dòng đó (source_rows). Chưa rõ kết quả thì bấm lại
    // gửi đúng khóa cũ để không dán trùng. Chuyến vào sổ chưa có giá nên tổng còn nợ không đổi lúc duyệt.
    const rowApprovals = new Map();
    let newJump = 0;
    const flash = row => { row.classList.remove('ps-flash'); void row.offsetWidth; row.classList.add('ps-flash'); };
    root.addEventListener('click', async event => {
      const button = event.target.closest('.sheet-row-approve,.sheet-new-next');
      if (!button || button.disabled || !ctx.snapshot) return;
      const items = newRows(ctx.snapshot);
      if (button.matches('.sheet-new-next')) {
        if (!items.length) return;
        const item = items[newJump++ % items.length];
        ctx.showMonth(monthKey(item.event_date));
        const row = root.querySelector(`tr[data-sheet-new="${CSS.escape(String(item.source_row))}"]`);
        if (!row) return;
        row.scrollIntoView({ block: 'center' });
        flash(row);
        row.querySelector('.sheet-row-approve')?.focus();
        return;
      }
      if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
      const sourceRow = Number(button.dataset.sourceRow);
      const item = items.find(entry => entry.source_row === sourceRow);
      if (!item) return;
      let body = rowApprovals.get(sourceRow);
      if (!body) {
        body = { customer_id: customerId, expected_version: ctx.snapshot.version, snapshot_sha256: ctx.snapshot.sheet_sync.snapshot_sha256,
          idempotency_key: crypto.randomUUID(), source_rows: [sourceRow] };
        rowApprovals.set(sourceRow, body);
      }
      button.disabled = true;
      button.textContent = 'Đang duyệt…';
      const what = `chuyến ${item.container} ngày ${dateText(item.event_date)}`;
      let response, result;
      try {
        response = await fetch('/api/v7/sheet/approve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        result = await response.json();
      } catch {
        button.disabled = false;
        button.textContent = 'Duyệt';
        showNotice(`Chưa rõ đã duyệt ${what} chưa. Bấm Duyệt lần nữa để thử lại đúng thao tác đó.`);
        return;
      }
      rowApprovals.delete(sourceRow);
      try { await api.read(); } catch { showNotice('Đã gửi lệnh duyệt; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
      const added = [...root.querySelectorAll('tr[data-row^="trip-"]')].find(row => row.children[1]?.textContent.startsWith(item.container));
      if (added) { added.scrollIntoView({ block: 'center' }); flash(added); }
      showNotice(!response.ok ? result.message || `Không duyệt được ${what}.`
        : result.review_count ? `Đã duyệt ${what}, nhưng nghi trùng với chuyến đã có nên thành "chờ kiểm": bấm nhãn chờ kiểm ở hàng đó để kết luận.`
          : `Đã duyệt ${what} vào tháng ${monthLabel(monthKey(item.event_date))}. Chưa có giá nên chưa tính tiền; có giá trên Sheet thì máy tự điền.`);
    });
    // ---- Sheet không còn dòng này (specs/v7-sheet-removed-trips.md): chỉ báo; xóa qua lệnh xóa chuyến có sẵn ----
    const removedRows = data => data.sheet_sync?.removed_items ?? [];
    const keepRequests = new Map();
    let removedJump = 0;
    function decorateRemoved(data, active) {
      const items = active ? removedRows(data) : [];
      for (const item of items) {
        const row = root.querySelector(`[data-row="trip-${CSS.escape(String(item.trip_id))}"]`);
        if (!row) continue;
        row.classList.add('sheet-removed');
        row.title = 'Sheet không còn dòng này. Web vẫn tính chuyến cho tới khi xóa.';
        row.insertAdjacentHTML('afterend', `<tr class="sheet-removed-notice" data-sheet-trip="${escape(item.trip_id)}"><td colspan="${spanOf(row)}"><div class="sheet-removed-content"><span class="sheet-removed-tag">Sheet không còn dòng này</span><span class="sheet-removed-actions"><button type="button" class="sheet-removed-delete" data-trip="${escape(item.trip_id)}">Xóa trên web</button><button type="button" class="sheet-removed-keep" data-trip="${escape(item.trip_id)}">Giữ</button></span></div></td></tr>`);
      }
      if (items.length) root.querySelector('.book-tasks')?.insertAdjacentHTML('beforeend', `<div class="price-strip sheet-removed-strip">Sheet không còn dòng của <strong>${items.length}</strong> chuyến đang tính trên web <button type="button" class="sheet-removed-next">Xem</button></div>`);
    }
    root.addEventListener('click', async event => {
      const button = event.target.closest('.sheet-removed-delete,.sheet-removed-keep,.sheet-removed-next,.sheet-removed-unlock');
      if (!button || !ctx.snapshot) return;
      event.stopImmediatePropagation();
      if (button.matches('.sheet-removed-unlock')) { ctx.askLock(button, button.dataset.month, false); return; }
      const items = removedRows(ctx.snapshot);
      if (button.matches('.sheet-removed-next')) {
        if (!items.length) return;
        // SO-GON-04: chuyến nằm trong tháng đang thu gọn thì hiện chi tiết tháng đó trước.
        const item = items[removedJump++ % items.length];
        ctx.showMonth(monthKey(item.month));
        const row = root.querySelector(`[data-row="trip-${CSS.escape(String(item.trip_id))}"]`);
        if (!row) return;
        row.scrollIntoView({ block: 'center' });
        row.nextElementSibling?.querySelector('.sheet-removed-delete')?.focus();
        return;
      }
      const item = items.find(entry => String(entry.trip_id) === button.dataset.trip);
      if (!item) return;
      const row = button.closest('tr');
      if (button.matches('.sheet-removed-keep')) {
        let body = keepRequests.get(item.trip_id);
        if (!body) {
          body = { customer_id: customerId, expected_version: ctx.snapshot.version, idempotency_key: crypto.randomUUID(),
            task_kind: 'removed', target_kind: 'trip', target_id: item.trip_id, source_fingerprint: item.source_fingerprint };
          keepRequests.set(item.trip_id, body);
        }
        button.disabled = true;
        try {
          const response = await fetch('/api/v7/sheet/tasks/keep', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
          const result = await response.json();
          keepRequests.delete(item.trip_id);
          if (!response.ok) { showNotice(result.message || 'Chưa giữ được chuyến. Tải lại sổ để đối chiếu.'); return; }
          await api.read();
          showNotice(`Đã giữ chuyến ${item.container}. Dòng Sheet liên quan đổi thì hỏi lại.`);
        } catch { showNotice('Chưa rõ kết quả giữ chuyến. Bấm Giữ để thử lại cùng thao tác.'); }
        finally { button.disabled = false; }
        return;
      }
      const wasOpen = row.nextElementSibling?.classList.contains('delete-prompt');
      root.querySelectorAll('.delete-prompt').forEach(prompt => prompt.remove());
      if (wasOpen) return;
      const what = `chuyến ${escape(item.container)} (${escape(dateText(item.event_date))}`;
      // Xóa chuyến tháng khóa vẫn bị chặn (24/10/2026): mở khóa là một thao tác riêng, có ghi Lịch sử.
      if (item.month_locked || row.closest('table.ledger')?.classList.contains('locked')) {
        const month = monthKey(item.month);
        row.insertAdjacentHTML('afterend', `<tr class="void-prompt delete-prompt"><td colspan="${spanOf(row)}">Tháng ${monthLabel(month)} đang khóa nên chưa xóa được ${what}). Mở khóa tháng rồi bấm lại "Xóa trên web". <button type="button" class="sheet-removed-unlock" data-month="${escape(month)}-01">Mở khóa tháng ${Number(month.slice(5))}</button> <button type="button" class="cancel-delete">Thôi</button></td></tr>`);
        row.nextElementSibling.querySelector('.sheet-removed-unlock').focus();
        return;
      }
      const amount = item.status !== 'confirmed' ? 'chưa tính vào số dư'
        : item.amount_vnd == null ? 'chưa có giá' : `thành tiền ${escape(ctx.fmt(item.amount_vnd))}`;
      // Dòng hỏi cùng dạng xóa chuyến ở ô STT: nút Xóa hẳn/Thôi do so-khach-v7-edit-ui.js xử lý (lệnh tripDelete).
      row.insertAdjacentHTML('afterend', `<tr class="void-prompt delete-prompt" data-kind="trip" data-id="${escape(item.trip_id)}"><td colspan="${spanOf(row)}">Sheet không còn dòng này. Xóa hẳn ${what}, ${amount}) trên web? Lịch sử ghi người xóa. <button type="button" class="confirm-delete">Xóa hẳn</button> <button type="button" class="cancel-delete">Thôi</button><span class="cell-error delete-error" role="alert"></span></td></tr>`);
      row.nextElementSibling.querySelector('.cancel-delete').focus();
    });
    Object.assign(ctx, { decoratePrices, removedAfterRender: decorateRemoved });
};
