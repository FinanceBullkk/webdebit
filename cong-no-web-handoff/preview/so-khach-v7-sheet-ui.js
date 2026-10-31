/* Sổ khách V7 bản live — Đối chiếu Sheet và ghi giá từ Sheet.
 * Tách từ so-khach-v7-ui.js (29/10/2026) để các PR ít đụng nhau; nạp trước so-khach-v7-ui.js,
 * dùng chung phạm vi của initLive qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).sheet = ctx => {
  'use strict';
  const { root, model, api, customerId, escape, spanOf, dateText, monthKey, monthLabel, sheetFieldLabel, resolvableSheetFields, showNotice, renderSnapshot, submit } = ctx;
    // Ghi giá từ Sheet (specs/v7-price-queue.md): null | 'confirm' | 'review' | { error }; giữ qua lần vẽ lại.
    let priceView = null;
    let priceApproval = null;
    // ---- Ghi giá từ Sheet: server chọn dòng chắc chắn (READY), trang chỉ hiện và gửi một lệnh cho cả lô ----
    const priceRows = data => new Map([...(data.trips ?? []).map(row => [`trip-${row.id}`, row]),
      ...(data.legacy_rows ?? []).map(row => [`legacy-${row.id}`, row])]);
    const vndText = value => value == null ? '' : model.formatVnd(model.sheetVnd(value));
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
      if (priceView?.error) return `<div class="price-panel err" role="alert"><p><strong>Chưa ghi giá nào.</strong> ${escape(priceView.error)}</p><div class="price-actions"><button type="button" class="price-reload primary">Tải lại sổ</button></div></div>`;
      if (priceView !== 'review') return '';
      const rows = priceRows(data);
      const line = item => {
        const what = `${escape(item.container)} · ${escape(dateText(item.date))}`;
        const month = monthKey(rows.get(`${item.target_kind}-${item.target_id}`)?.month);
        if (item.status === 'MONTH_LOCKED') return `<li><div class="what">${what} · giá Sheet ${vndText(item.sheet_unit_price_vnd)} đ<small>Tháng ${monthLabel(month)} đang khóa nên chưa ghi được.</small></div><button type="button" class="price-unlock" data-month="${escape(month)}-01">Mở khóa tháng ${Number(month.slice(5))}</button></li>`;
        if (item.status === 'CONFLICT') return `<li><div class="what">${what} · Web ${vndText(item.web_unit_price_vnd)} đ · Sheet ${vndText(item.sheet_unit_price_vnd)} đ<small>Web đã có giá khác Sheet.</small></div><button type="button" class="price-use-sheet" data-kind="${escape(item.target_kind)}" data-id="${escape(item.target_id)}" data-price="${escape(item.sheet_unit_price_vnd)}" data-fee="${escape(item.sheet_other_fee_vnd ?? '')}">Lấy Sheet</button></li>`;
        if (item.status === 'MANUAL') return `<li><div class="what">${what} · giá Sheet ${vndText(item.sheet_unit_price_vnd)} đ · phụ phí ${vndText(item.sheet_other_fee_vnd)} đ<small>Sheet có số âm (giảm trừ). Nhập tay tại ô của chuyến.</small></div></li>`;
        return `<li><div class="what">Dòng Sheet ${escape(item.source_row)} · ${what} · giá Sheet ${vndText(item.sheet_unit_price_vnd)} đ<small>Khớp nhiều chuyến cùng container. Điền giá tay tại ô của đúng chuyến.</small></div></li>`;
      };
      return `<div class="price-panel" role="region" aria-label="Giá từ Sheet cần xem"><ul>${(data.sheet_prices?.review ?? []).map(line).join('')}</ul></div>`;
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
      if (!review.length && priceView === 'review') priceView = null;
      const strip = review.length ? `<div class="price-strip">Giá từ Sheet cần xem: <strong>${review.length}</strong> <button type="button" class="price-review-toggle" aria-expanded="${priceView === 'review'}">${priceView === 'review' ? 'Đóng' : 'Xem'}</button></div>` : '';
      root.querySelector('.book-head')?.insertAdjacentHTML('afterend', strip + pricePanel(data));
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
          ? `<div class="sheet-choice-actions"><button type="button" data-sheet-decision="keep_web" data-sheet-field="booking">Giữ booking đã ghi</button></div>`
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
    root.addEventListener('click', async event => {
      const target = event.target.closest('.price-approve,.price-cancel,.price-review-toggle,.price-reload,.price-write,.price-unlock,.price-use-sheet');
      if (!target || target.disabled || !ctx.snapshot) return;
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
        await api.read().catch(() => showNotice('Không tải được sổ mới. Thử lại.'));
        return;
      }
      if (target.matches('.price-unlock')) { await submit('lock', { month: target.dataset.month, locked: false }); return; }
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
    let sheetApproval = null;
    root.addEventListener('click', async event => {
      const button = event.target.closest('.sheet-approve');
      if (!button || button.disabled) return;
      if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
      sheetApproval ??= { customer_id: customerId, expected_version: ctx.snapshot.version,
        snapshot_sha256: ctx.snapshot.sheet_sync.snapshot_sha256, idempotency_key: crypto.randomUUID() };
      button.disabled = true;
      try {
        const response = await fetch('/api/v7/sheet/approve', { method: 'POST',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sheetApproval) });
        const result = await response.json();
        sheetApproval = null;
        try { await api.read(); } catch { showNotice('Đã xử lý lô duyệt; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
        showNotice(response.ok
          ? result.complete === false ? `Đã duyệt ${result.approved} chuyến; còn ${result.remaining} chuyến chưa duyệt (${result.error}).`
            : `Đã duyệt ${result.approved} chuyến${result.review_count ? `; ${result.review_count} chuyến nghi trùng cần kiểm` : ''}. Chuyến thiếu giá vẫn chưa tính tiền.`
          : result.message || 'Không duyệt được chuyến mới.');
      } catch { showNotice('Chưa rõ kết quả duyệt. Tải lại sổ để kiểm tra trước khi thử lại.'); }
      button.disabled = false;
    });
    // ---- Sheet không còn dòng này (specs/v7-sheet-removed-trips.md): chỉ báo; xóa qua lệnh xóa chuyến có sẵn ----
    // "Giữ" nhớ trên máy này theo bản chụp Sheet; bản chụp mới (hash khác) thì hỏi lại. Không ghi gì lên server.
    const keptKey = data => `sokhach-v7-sheet-giu:${customerId}:${data.sheet_sync?.snapshot_sha256 ?? ''}`;
    // Trình duyệt chặn localStorage thì vẫn nhớ trong phiên này.
    const keptMemory = new Map();
    const keptIds = data => {
      const ids = new Set(keptMemory.get(keptKey(data)) ?? []);
      try { for (const id of JSON.parse(localStorage.getItem(keptKey(data)) ?? '[]')) ids.add(String(id)); } catch { /* chỉ còn bản trong phiên */ }
      return ids;
    };
    const removedRows = data => {
      const kept = keptIds(data);
      return (data.sheet_sync?.removed_items ?? []).filter(item => !kept.has(String(item.trip_id)));
    };
    let removedJump = 0;
    function decorateRemoved(data, active) {
      const items = active ? removedRows(data) : [];
      for (const item of items) {
        const row = root.querySelector(`[data-row="trip-${CSS.escape(String(item.trip_id))}"]`);
        if (!row) continue;
        row.classList.add('sheet-removed');
        row.title = 'Sheet không còn dòng này. Web vẫn tính chuyến cho tới khi xóa.';
        row.children[1]?.insertAdjacentHTML('beforeend', `<small class="sheet-removed-tag">Sheet không còn dòng này</small><span class="sheet-removed-actions"><button type="button" class="sheet-removed-delete" data-trip="${escape(item.trip_id)}">Xóa trên web</button><button type="button" class="sheet-removed-keep" data-trip="${escape(item.trip_id)}">Giữ</button></span>`);
      }
      if (items.length) root.querySelector('.book-head')?.insertAdjacentHTML('afterend', `<div class="price-strip sheet-removed-strip">Sheet không còn dòng của <strong>${items.length}</strong> chuyến đang tính trên web <button type="button" class="sheet-removed-next">Xem</button></div>`);
    }
    root.addEventListener('click', async event => {
      const button = event.target.closest('.sheet-removed-delete,.sheet-removed-keep,.sheet-removed-next,.sheet-removed-unlock');
      if (!button || !ctx.snapshot) return;
      event.stopImmediatePropagation();
      if (button.matches('.sheet-removed-unlock')) { button.disabled = true; await submit('lock', { month: button.dataset.month, locked: false }); return; }
      const items = removedRows(ctx.snapshot);
      if (button.matches('.sheet-removed-next')) {
        if (!items.length) return;
        // SO-GON-04: chuyến nằm trong tháng đang thu gọn thì hiện chi tiết tháng đó trước.
        const item = items[removedJump++ % items.length];
        ctx.showMonth(monthKey(item.month));
        const row = root.querySelector(`[data-row="trip-${CSS.escape(String(item.trip_id))}"]`);
        if (!row) return;
        row.scrollIntoView({ block: 'center' });
        row.querySelector('.sheet-removed-delete')?.focus();
        return;
      }
      const item = items.find(entry => String(entry.trip_id) === button.dataset.trip);
      if (!item) return;
      const row = button.closest('tr');
      if (button.matches('.sheet-removed-keep')) {
        const kept = keptIds(ctx.snapshot);
        kept.add(String(item.trip_id));
        keptMemory.set(keptKey(ctx.snapshot), kept);
        try { localStorage.setItem(keptKey(ctx.snapshot), JSON.stringify([...kept])); } catch { /* chỉ nhớ trong phiên */ }
        renderSnapshot(ctx.snapshot);
        showNotice(`Đã giữ chuyến ${item.container}. Sheet có bản mới thì sổ hỏi lại.`);
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
