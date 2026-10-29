/* Sổ khách V7 bản live — Bảng nhập chuyến kiểu Sheet (NHAP-SHEET-01).
 * Tách từ so-khach-v7-ui.js (29/10/2026) để các PR ít đụng nhau; nạp trước so-khach-v7-ui.js,
 * dùng chung phạm vi của initLive qua ctx (xem so-khach-v7-ui.js). */
(window.SoKhachV7LiveParts ??= {}).draft = ctx => {
  'use strict';
  const { root, model, api, escape, todayIso, showNotice, redraw, submit } = ctx;
    // ---- NHAP-SHEET-01 (1): bảng nhập kiểu Sheet thay ô "Dán các dòng từ Sheet". Nháp chỉ sống trong tab;
    // Lưu gửi một lệnh dán lô (paste_trips), server tự xếp từng chuyến vào tháng của ngày chuyến. ----
    const DRAFT_FIELDS = model.DRAFT_FIELDS;
    const draftLabels = { container: 'Số container', carrier: 'Hãng tàu', shipper: 'Shipper', date: 'Ngày chuyến', from: 'Nơi đi', to: 'Nơi đến', price: 'Đơn giá', fee: 'Phụ phí' };
    // Nháp chuyến theo từng tháng đang mở (mỗi tháng mở có bảng nhập riêng); lưu xong chuyến vào tháng của ngày chuyến.
    const draftsBy = new Map();
    const draftsOf = key => draftsBy.get(key) ?? [];
    const setDrafts = (key, rows) => { if (rows.length) draftsBy.set(key, rows); else draftsBy.delete(key); };
    let draftNote = { key: '', text: '' };
    const draftEmpty = row => DRAFT_FIELDS.every(name => !String(row[name] ?? '').trim());
    function draftGrid(key) {
      const drafts = draftsOf(key);
      const checked = drafts.map(row => model.checkDraft(row, todayIso()));
      const bad = checked.reduce((sum, item) => sum + Object.keys(item.errors).length, 0);
      const rows = [...drafts, model.blankDraft()].map((row, index) => {
        const result = index < drafts.length ? checked[index] : null;
        const cells = DRAFT_FIELDS.map(name => {
          const error = result?.errors[name];
          const missing = name === 'price' && result?.missing;
          return `<td class="${error ? 'bad' : ''}${missing ? ' missing' : ''}"${error ? ` title="${escape(error)}"` : ''}><input class="draft-input${['price', 'fee'].includes(name) ? ' money-input' : ''}" data-month="${escape(key)}" data-draft="${index}" data-field="${name}" value="${escape(row[name])}" aria-label="${draftLabels[name]} hàng nhập ${index + 1}"${error ? ` aria-invalid="true" aria-description="${escape(error)}"` : ''}${missing ? ' placeholder="chưa có giá"' : ''} autocomplete="off"></td>`;
        }).join('');
        const total = result ? (result.amountVnd === null ? '–' : model.formatVnd(result.amountVnd)) : '';
        return `<tr class="draft-row${result ? ' draft' : ''}"><td class="muted">${result ? 'nháp' : ''}</td>${cells}<td class="num${result?.warn ? ' warn' : ''}">${escape(total)}${result?.warn ? `<small>${escape(result.warn)}</small>` : ''}</td><td class="off pay-start"></td><td class="off"></td><td class="off"></td></tr>`;
      }).join('');
      const note = draftNote.key === key ? draftNote.text : '';
      return `<tr class="draft-caption"><td colspan="13">Nhập chuyến · dán từ Sheet vào ô bất kỳ của hàng trống, hoặc gõ tay (Tab sang ô kế, Enter xuống hàng)</td></tr>${rows}
        <tr class="draft-bar"><td colspan="13"><div><strong>${drafts.length} chuyến nháp</strong>${bad ? `<span class="cell-error">· ${bad} ô cần sửa</span>` : ''}<button type="button" class="draft-save" data-month="${escape(key)}" ${drafts.length && !bad ? '' : 'disabled'}>Lưu ${drafts.length} chuyến</button><button type="button" class="draft-discard" data-month="${escape(key)}" ${drafts.length ? '' : 'disabled'}>Bỏ nháp</button>${note ? `<span class="draft-note" role="status">${escape(note)}</span>` : ''}</div></td></tr>`;
    }
    // ---- Bảng nhập: gõ chỉ ghi vào nháp, vẽ lại khi rời ô (không phá bộ gõ tiếng Việt giữa chừng),
    // trừ lần đầu gõ vào hàng trống: cần mọc ngay một hàng trống mới bên dưới. ----
    const draftAt = element => element?.matches?.('.draft-input') ? { month: element.dataset.month, row: Number(element.dataset.draft), field: element.dataset.field } : null;
    root.addEventListener('input', event => {
      const here = draftAt(event.target);
      if (!here) return;
      const drafts = [...draftsOf(here.month)];
      const fresh = here.row === drafts.length;
      drafts[here.row] ??= model.blankDraft();
      drafts[here.row][here.field] = event.target.value;
      setDrafts(here.month, drafts);
      draftNote = { key: '', text: '' };
      if (fresh && !event.isComposing) redraw({ ...here, caret: event.target.selectionStart });
    });
    root.addEventListener('compositionend', event => {
      const here = draftAt(event.target);
      const count = here && draftsOf(here.month).length;
      if (here && here.row === count - 1 && !root.querySelector(`.draft-input[data-month="${here.month}"][data-draft="${count}"]`)) redraw({ ...here, caret: event.target.selectionStart });
    });
    root.addEventListener('paste', event => {
      const here = draftAt(event.target);
      if (!here) return;
      const text = event.clipboardData.getData('text/plain');
      if (!/[\t\n]/.test(text.replace(/\r?\n$/, ''))) return;   // một ô: dán như thường
      event.preventDefault();
      const read = model.spreadPaste(text, here.field);
      const drafts = [...draftsOf(here.month)];
      read.rows.forEach((row, offset) => {
        const index = here.row + offset;
        // Dán theo cột web (không thấy container): chỉ đè các ô được dán, giữ ô khác của hàng nháp.
        drafts[index] = read.byColumn ? model.tidyDraft({ ...(drafts[index] ?? model.blankDraft()), ...Object.fromEntries(DRAFT_FIELDS.filter(name => row[name]).map(name => [name, row[name]])) }) : row;
      });
      setDrafts(here.month, drafts);
      draftNote = { key: here.month, text: [read.payments ? 'Phần tiền khách trả trong vùng dán đã bỏ qua — khoản thu ghi ở ô Ngày trả / Số tiền trả.' : '',
        read.skipped ? `Bỏ qua ${read.skipped} hàng trống hoặc hàng cộng.` : ''].filter(Boolean).join(' ') };
      redraw({ month: here.month, row: Math.min(here.row + read.rows.length, drafts.length), field: 'container' });
    });
    root.addEventListener('focusout', event => {
      const left = draftAt(event.target);
      if (!left || ctx.rendering) return;
      const drafts = [...draftsOf(left.month)];
      if (drafts[left.row]) { drafts[left.row] = model.tidyDraft(drafts[left.row]); setDrafts(left.month, drafts); }
      requestAnimationFrame(() => {
        const next = draftAt(document.activeElement);
        // Sang ô nháp khác hoặc ra ngoài trang: vẽ lại để hiện lỗi/thành tiền; đang ở ô khác của sổ thì để yên.
        if (next || !root.contains(document.activeElement)) {
          const same = next?.month === left.month;
          const keep = next && (same ? { ...next, row: next.row - drafts.slice(0, next.row).filter(draftEmpty).length } : next);
          setDrafts(left.month, drafts.filter((row, index) => !draftEmpty(row) || (same && index === next.row)));
          redraw(keep);
        }
      });
    });
    root.addEventListener('keydown', event => {
      const here = draftAt(event.target);
      if (!here || !['Enter', 'ArrowDown', 'ArrowUp'].includes(event.key)) return;
      event.preventDefault();
      const row = Math.max(0, Math.min(draftsOf(here.month).length, here.row + (event.key === 'ArrowUp' ? -1 : 1)));
      root.querySelector(`.draft-input[data-month="${here.month}"][data-draft="${row}"][data-field="${here.field}"]`)?.focus();
    });
    root.addEventListener('click', async event => {
      const discard = event.target.closest('.draft-discard');
      if (discard) {
        const key = discard.dataset.month;
        if (confirm(`Bỏ ${draftsOf(key).length} chuyến nháp?`)) { setDrafts(key, []); draftNote = { key: '', text: '' }; redraw(); }
        return;
      }
      const save = event.target.closest('.draft-save');
      if (!save) return;
      const key = save.dataset.month;
      const drafts = draftsOf(key);
      const checked = drafts.map(row => model.checkDraft(row, todayIso()));
      if (!drafts.length || checked.some(item => !item.trip)) { redraw(); return; }
      save.disabled = true;
      const count = drafts.length;
      const result = await submit('paste', { debt_month: `${key}-01`, trips: checked.map(item => item.trip) });
      if (api.lastOutcome()?.status === 'saved') {
        const ids = new Set((api.lastOutcome().result?.pending_review ?? []).map(item => String(item.trip_id)));
        setDrafts(key, []);
        draftNote = { key, text: `Đã lưu ${count} chuyến${ids.size ? ` (${ids.size} chuyến CHỜ KIỂM: nghi trùng, chưa tính nợ)` : ''}.` };
        showNotice('');
        redraw({ month: key, row: 0, field: 'container' });
      } else if (result?.message) { draftNote = { key, text: result.message }; redraw(); }
    });
    window.addEventListener?.('beforeunload', event => { if (draftsBy.size) event.preventDefault(); });
    Object.assign(ctx, { draftsBy, draftGrid });
};
