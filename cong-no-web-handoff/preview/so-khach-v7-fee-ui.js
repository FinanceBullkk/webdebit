/* Sổ khách V7 bản live — Phụ phí nhiều loại (PHU-PHI-01, specs/v7-phu-phi-nhieu-loai.md), theo mockup
 * preview/mockups/phu-phi-nhieu-loai đã duyệt 29/10/2026: ô cột riêng gõ số, khung Chi tiết phụ phí, thêm một khoản
 * cho nhiều chuyến, Cài đặt loại phụ phí. Nạp trước so-khach-v7-ui.js, dùng chung phạm vi initLive qua ctx (hợp đồng: so-khach-v7-ctx.js).
 * Mọi số tiền lấy từ server; model chỉ cộng các khoản để hiện và tính trước Thành tiền khi hỏi lại. */
(window.SoKhachV7LiveParts ??= {}).fee = ctx => {
  'use strict';
  const { root, model, api, escape, monthKey, showNotice, redraw, submit } = ctx;
  const vndText = value => value === null || value === undefined ? '–' : model.formatVnd(BigInt(value));
  const selected = new Set();          // đích đang đánh dấu ("trip:12", "legacy:5")
  let drawer = null;                   // { target } | { batch: true }
  let drawerError = '';
  let settingsError = '';
  let editingLine = null;              // id khoản đang sửa số trong khung
  let renaming = null;                 // id loại đang đổi tên trong cài đặt

  let typesError = '';
  // Khung, hộp hỏi và cài đặt nằm ngoài #app (sổ vẽ lại #app mỗi lần đọc); trang thử không có DOM thật thì dùng vỏ rỗng.
  const layer = (tag, className, attrs = []) => {
    if (typeof document.createElement !== 'function') {
      return { hidden: true, innerHTML: '', onclick: null, onkeydown: null, addEventListener() {}, setAttribute() {},
        querySelector: () => null, contains: () => false };
    }
    const element = document.createElement(tag);
    element.className = className;
    element.hidden = true;
    for (const [name, value] of attrs) element.setAttribute(name, value);
    document.body.append(element);
    return element;
  };
  const drawerEl = layer('aside', 'fee-drawer', [['aria-label', 'Chi tiết phụ phí']]);
  const confirmEl = layer('div', 'fee-confirm', [['role', 'dialog'], ['aria-modal', 'true'], ['aria-label', 'Hỏi lại trước khi ghi phụ phí']]);
  const settingsEl = layer('div', 'fee-settings', [['role', 'dialog'], ['aria-modal', 'true'], ['aria-label', 'Cài đặt loại phụ phí']]);

  const types = () => ctx.feeTypes ?? [];
  const typeOf = id => types().find(type => Number(type.id) === Number(id));
  const isSystem = type => type?.system_key != null;
  // Khoản mới chọn được: loại đang dùng, trừ "Phụ phí ban đầu" (chỉ migration tạo). Khoản cũ giữ được loại hiện có.
  const usable = keep => types().filter(type => type.active && type.system_key !== 'initial' || Number(type.id) === Number(keep));
  const options = (selectedId, keep) => usable(keep).map(type =>
    `<option value="${type.id}"${Number(type.id) === Number(selectedId) ? ' selected' : ''}>${escape(type.name)}</option>`).join('');

  function monthLocked(key) {
    const snapshot = ctx.snapshot;
    const flag = (snapshot?.month_locks ?? []).find(row => monthKey(row.month) === key);
    return flag ? flag.locked : key !== monthKey(snapshot?.today_month);
  }
  // Đích của một lệnh phụ phí: chuyến web hoặc dòng sổ gốc, kèm lý do không sửa được nếu có.
  function findTarget(target) {
    const [kind, idText] = String(target).split(':');
    const id = Number(idText);
    const snapshot = ctx.snapshot;
    if (kind === 'trip') {
      const row = (snapshot?.trips ?? []).find(trip => trip.id === id);
      if (!row) return null;
      const locked = monthLocked(monthKey(row.month));
      const blocked = locked ? 'Tháng đã khóa — mở khóa tháng để sửa phụ phí.'
        : row.status === 'pending_review' ? 'Chuyến đang CHỜ KIỂM — kết luận chuyến trước rồi mới sửa phụ phí.'
        : row.status !== 'confirmed' ? 'Chuyến đã loại, không sửa phụ phí.' : '';
      return { target, payload: { trip_id: id }, row, lines: row.fee_lines ?? [], what: row.container || 'phí lẻ',
        date: row.event_date, unitPrice: row.unit_price_vnd, locked, blocked, countedDiffers: false };
    }
    const row = (snapshot?.legacy_rows ?? []).find(item => item.id === id && item.kind !== 'receipt');
    if (!row) return null;
    const cur = row.current ?? {};
    const locked = monthLocked(monthKey(row.month));
    const blocked = locked ? 'Tháng đã khóa — mở khóa tháng để sửa phụ phí.'
      : cur.unit_price_vnd == null ? 'Dòng này chưa có đơn giá — điền đơn giá trước rồi mới sửa phụ phí.' : '';
    return { target, payload: { legacy_row_id: id }, row, lines: row.fee_lines ?? [], what: cur.container || 'phí lẻ',
      date: cur.event_date, unitPrice: cur.unit_price_vnd, counted: cur.counted_vnd, locked, blocked,
      countedDiffers: row.counted_differs === true };
  }

  // Dòng sổ gốc có Thành tiền khác đơn giá + phụ phí: lần sửa phí đầu tiên tính lại Thành tiền — hỏi trước khi ghi.
  function confirmRecount(items) {
    const changing = items.filter(item => item.info.countedDiffers);
    if (!changing.length) return Promise.resolve(true);
    return new Promise(resolve => {
      const rows = changing.map(({ info, change }) => {
        const preview = model.recountPreview(info.counted, info.unitPrice, info.lines, change);
        return `<li><b>${escape(info.what)}</b>: Thành tiền đang là <b>${model.formatVnd(preview.beforeVnd)}</b> → <b>${model.formatVnd(preview.afterVnd)}</b>
          (${preview.deltaVnd >= 0n ? '+' : ''}${model.formatVnd(preview.deltaVnd)})</li>`;
      }).join('');
      confirmEl.innerHTML = `<div class="fee-confirm-box"><h2>Thành tiền sẽ đổi</h2>
        <p>${changing.length > 1 ? `${changing.length} dòng có` : 'Dòng này có'} Thành tiền khác đơn giá + phụ phí. Sau lệnh này Thành tiền tính lại = đơn giá + các khoản phụ phí:</p>
        <ul>${rows}</ul><p class="fee-muted">Số dư đầu không đổi; phần chênh ghi ở Lịch sử.</p>
        <div class="fee-actions"><button type="button" class="fee-no">Thôi</button><button type="button" class="fee-yes">Ghi</button></div></div>`;
      confirmEl.hidden = false;
      // Đặt con trỏ sau một nhịp: phím Enter vừa lưu ô không được bấm luôn nút Ghi.
      setTimeout(() => confirmEl.querySelector('.fee-yes')?.focus(), 0);
      const close = answer => { confirmEl.hidden = true; confirmEl.innerHTML = ''; confirmEl.onclick = null; confirmEl.onkeydown = null; resolve(answer); };
      confirmEl.onclick = event => {
        if (event.target.closest('.fee-yes')) close(true);
        else if (event.target.closest('.fee-no') || event.target === confirmEl) close(false);
      };
      confirmEl.onkeydown = event => { if (event.key === 'Escape') close(false); };
    });
  }

  // Gửi một lệnh sổ; trả '' khi đã lưu, thông báo lỗi khi không.
  async function send(action, fields) {
    const result = await submit(action, fields);
    const outcome = api.lastOutcome();
    if (outcome?.status === 'saved') return '';
    return result?.message || outcome?.result?.message
      || (outcome?.status === 'stale' ? 'Sổ vừa thay đổi. Kiểm tra dữ liệu mới rồi thực hiện lại.' : 'Chưa lưu được. Thử lại.');
  }

  // ---- Ô cột riêng: bấm → gõ số → Enter lưu (một lệnh "đặt loại = số"), Esc thôi; xóa trắng = bỏ mọi khoản loại đó. ----
  function openOwn(td) {
    const info = findTarget(td.dataset.feeTarget);
    if (!info) return;
    if (info.blocked) { showNotice(info.blocked); return; }
    const typeId = Number(td.dataset.feeType);
    td.innerHTML = `<input class="fee-own-input" inputmode="numeric" aria-label="${escape(ctx.feeTypeName(typeId))} mới" value="${escape(td.textContent.trim())}"><span class="cell-error" role="status"></span>`;
    const input = td.querySelector('input');
    input.focus(); input.select();
    input.addEventListener('keydown', async event => {
      if (event.key === 'Escape') { event.preventDefault(); redraw(); return; }
      if (event.key !== 'Enter') return;
      event.preventDefault();
      const error = td.querySelector('.cell-error');
      let amount;
      try { amount = model.parseFeeInput(input.value, typeOf(typeId)?.sign, { allowBlank: true }); }
      catch (problem) { error.textContent = problem.message; return; }
      const current = model.feeCells(info.lines, [typeId]).own[0];
      if (current === amount) { redraw(); return; }
      if (!await confirmRecount([{ info, change: { set: { typeId, amountVnd: amount } } }])) { redraw(); return; }
      const message = await send('feeSet', { target: info.payload, fee_type_id: typeId, amount_vnd: amount === null ? null : amount.toString() });
      if (message && td.isConnected) td.querySelector('.cell-error').textContent = message;
    });
  }

  // ---- Khung Chi tiết phụ phí ----
  function drawerHtml() {
    if (drawer.batch) {
      const targets = [...selected].map(findTarget).filter(Boolean);
      return `<header><h2>Thêm một khoản cho ${targets.length} chuyến<small>${targets.map(info => escape(info.what)).join(', ')}</small></h2><button type="button" class="fee-close">Đóng</button></header>
        <div class="fee-body"><p>Mỗi chuyến nhận một khoản giống nhau. Tất cả cùng vào, hoặc không chuyến nào vào.</p>${addForm(`Thêm cho ${targets.length} chuyến`)}</div>`;
    }
    const info = findTarget(drawer.target);
    const frozen = Boolean(info.blocked);
    const rows = info.lines.map(line => {
      const type = typeOf(line.fee_type_id);
      const tags = (ctx.feeColumnIds.includes(Number(line.fee_type_id)) ? '<span class="fee-tag">cột riêng</span>' : '')
        + (type?.kind === 'pass_through' ? '<span class="fee-tag pass">chi hộ</span>' : '');
      if (frozen) return `<tr><td>${escape(type?.name ?? ctx.feeTypeName(line.fee_type_id))}${tags ? `<br>${tags}` : ''}</td><td class="num"><b>${vndText(line.amount_vnd)}</b></td><td>${escape(line.note ?? '')}</td><td></td></tr>`;
      const amount = editingLine === line.id
        ? `<input class="fee-line-amount" data-line="${line.id}" inputmode="numeric" value="${vndText(line.amount_vnd)}" aria-label="Số tiền mới">`
        : vndText(line.amount_vnd);
      return `<tr><td><select class="fee-line-type" data-line="${line.id}" aria-label="Loại">${options(line.fee_type_id, line.fee_type_id)}</select>${tags}</td>
        <td class="num fee-amt" data-line="${line.id}" tabindex="0" role="button" aria-label="Sửa số tiền ${vndText(line.amount_vnd)}">${amount}</td>
        <td><input class="fee-line-note" data-line="${line.id}" value="${escape(line.note ?? '')}" placeholder="Ghi chú" aria-label="Ghi chú" maxlength="2000"></td>
        <td><button type="button" class="fee-del" data-line="${line.id}" aria-label="Xóa khoản ${escape(type?.name ?? '')} ${vndText(line.amount_vnd)}" title="Xóa khoản">🗑</button></td></tr>`;
    }).join('');
    const total = model.feeCells(info.lines, []).totalVnd;
    return `<header><h2>Chi tiết phụ phí<small>${escape(info.what)}${info.date ? ` · ${escape(ctx.dateText(info.date))}` : ''}${info.unitPrice != null ? ` · đơn giá ${vndText(info.unitPrice)}` : ''}</small></h2><button type="button" class="fee-close">Đóng</button></header>
      <div class="fee-body">${typesError ? `<p class="fee-error">${escape(typesError)}</p>` : ''}${info.blocked ? `<p class="fee-info">${escape(info.blocked)}</p>` : ''}
        ${info.lines.length ? `<table class="fee-lines"><thead><tr><th>Loại</th><th class="num">Số tiền</th><th>Ghi chú</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : '<p class="fee-muted">Chưa có khoản phụ phí nào.</p>'}
        <div class="fee-sumline"><span>Tổng phụ phí</span><span>${total === null ? '–' : model.formatVnd(total)}</span></div>
        <div class="fee-sumline calc">${calcLine(info, total)}</div>
        ${frozen ? '' : addForm('Thêm')}</div>`;
  }
  // Thành tiền ngay trong khung (khung che cột Thành tiền của sổ): số server, phép tính chỉ để đọc.
  function calcLine(info, total) {
    const amount = info.target.startsWith('trip:') ? info.row.amount_vnd : info.counted;
    if (amount == null) return '<span>Thành tiền</span><b>chưa tính — thiếu đơn giá</b>';
    if (info.countedDiffers) return `<span>Thành tiền đang là</span><b>${vndText(amount)}</b>`;
    return `<span>Thành tiền${info.unitPrice != null ? ` = ${vndText(info.unitPrice)} + ${total === null ? '0' : model.formatVnd(total)}` : ''}</span><b>${vndText(amount)}</b>`;
  }
  function addForm(label) {
    const other = types().find(type => type.system_key === 'other');
    return `<form class="fee-add"><h3>Thêm khoản</h3><select class="fee-add-type" aria-label="Loại">${options(other?.id)}</select>
      <input class="fee-add-amount" inputmode="numeric" placeholder="Số tiền" aria-label="Số tiền"><input class="fee-add-note" placeholder="Ghi chú (tùy chọn)" aria-label="Ghi chú" maxlength="2000">
      <p class="fee-error" role="alert">${escape(drawerError)}</p><button type="submit">${label}</button></form>`;
  }
  function renderDrawer() {
    if (drawer && !drawer.batch && !findTarget(drawer.target)) drawer = null;
    if (drawer?.batch && !selected.size) drawer = null;
    drawerEl.hidden = !drawer;
    drawerEl.innerHTML = drawer ? drawerHtml() : '';
    root.querySelectorAll('.fee-other.open').forEach(cell => cell.classList.remove('open'));
    if (drawer?.target) root.querySelector(`.fee-other[data-fee-target="${drawer.target}"]`)?.classList.add('open');
  }
  function openDrawer(next) { drawer = next; drawerError = ''; editingLine = null; renderDrawer(); drawerEl.querySelector(next.batch ? '.fee-add-amount' : '.fee-close')?.focus(); }
  function closeDrawer() {
    const back = drawer?.target;
    drawer = null; renderDrawer();
    if (back) root.querySelector(`.fee-other[data-fee-target="${back}"]`)?.focus();
  }
  async function drawerCommand(action, fields, items) {
    if (!await confirmRecount(items)) return;
    drawerError = await send(action, fields);
    editingLine = null;
    renderDrawer();
    return drawerError === '';
  }
  const lineOf = id => findTarget(drawer.target)?.lines.find(line => line.id === Number(id));

  drawerEl.addEventListener('click', event => {
    if (event.target.closest('.fee-close')) { closeDrawer(); return; }
    const amount = event.target.closest('.fee-amt');
    if (amount && !amount.querySelector('input')) {
      editingLine = Number(amount.dataset.line); renderDrawer();
      const input = drawerEl.querySelector('.fee-line-amount'); input.focus(); input.select(); return;
    }
    const remove = event.target.closest('.fee-del');
    if (remove) {
      const info = findTarget(drawer.target);
      drawerCommand('feeVoid', { fee_line_id: Number(remove.dataset.line) }, [{ info, change: { void: { lineId: remove.dataset.line } } }]);
    }
  });
  drawerEl.addEventListener('change', event => {
    const line = event.target.dataset.line && lineOf(event.target.dataset.line);
    if (!line) return;
    if (event.target.matches('.fee-line-type')) {
      const typeId = Number(event.target.value);
      try { model.parseFeeInput(String(line.amount_vnd), typeOf(typeId)?.sign); }
      catch (problem) { drawerError = problem.message; renderDrawer(); return; }
      // Đổi loại không đổi số tiền: Thành tiền giữ nguyên, không cần hỏi lại.
      drawerCommand('feeReplace', { fee_line_id: line.id, fee_type_id: typeId, amount_vnd: String(line.amount_vnd), note: line.note ?? '' }, []);
    }
    if (event.target.matches('.fee-line-note') && event.target.value.trim() !== (line.note ?? '')) {
      drawerCommand('feeReplace', { fee_line_id: line.id, fee_type_id: Number(line.fee_type_id), amount_vnd: String(line.amount_vnd),
        note: event.target.value.trim() }, []);
    }
  });
  drawerEl.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !event.target.matches('.fee-line-amount')) { event.preventDefault(); closeDrawer(); return; }
    if (event.target.matches('.fee-amt') && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); event.target.click(); return; }
    if (!event.target.matches('.fee-line-amount')) return;
    if (event.key === 'Escape') { event.preventDefault(); editingLine = null; renderDrawer(); return; }
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const line = lineOf(event.target.dataset.line), info = findTarget(drawer.target);
    let amount;
    try { amount = model.parseFeeInput(event.target.value, typeOf(line.fee_type_id)?.sign); }
    catch (problem) { drawerError = `${problem.message}${problem.message.startsWith('Nhập số') ? ' — muốn bỏ khoản thì bấm thùng rác' : ''}`; renderDrawer(); return; }
    if (amount === BigInt(line.amount_vnd)) { editingLine = null; renderDrawer(); return; }
    drawerCommand('feeReplace', { fee_line_id: line.id, fee_type_id: Number(line.fee_type_id), amount_vnd: amount.toString(), note: line.note ?? '' },
      [{ info, change: { replace: { lineId: line.id, amountVnd: amount } } }]);
  });
  drawerEl.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target;
    const typeId = Number(form.querySelector('.fee-add-type').value), note = form.querySelector('.fee-add-note').value.trim();
    let amount;
    try { amount = model.parseFeeInput(form.querySelector('.fee-add-amount').value, typeOf(typeId)?.sign); }
    catch (problem) { form.querySelector('.fee-error').textContent = problem.message; form.querySelector('.fee-add-amount').focus(); return; }
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;   // bấm lặp không gửi hai lệnh
    if (drawer.batch) {
      const infos = [...selected].map(findTarget).filter(Boolean);
      const ok = await drawerCommand('feeAdd', { targets: infos.map(info => info.payload), fee_type_id: typeId, amount_vnd: amount.toString(), ...(note ? { note } : {}) },
        infos.map(info => ({ info, change: { add: { typeId, amountVnd: amount } } })));
      if (ok) {
        showNotice(`Đã thêm ${ctx.feeTypeName(typeId)} ${model.formatVnd(amount)} cho ${infos.length} chuyến.`);
        selected.clear(); drawer = null; renderDrawer(); renderSelection();
      } else if (button.isConnected) button.disabled = false;
      return;
    }
    const info = findTarget(drawer.target);
    const ok = await drawerCommand('feeAdd', { targets: [info.payload], fee_type_id: typeId, amount_vnd: amount.toString(), ...(note ? { note } : {}) },
      [{ info, change: { add: { typeId, amountVnd: amount } } }]);
    if (ok) drawerEl.querySelector('.fee-add-amount')?.focus();
    else if (button.isConnected) button.disabled = false;
  });

  // ---- Đánh dấu nhiều chuyến ----
  function renderSelection() {
    for (const target of [...selected]) {
      const info = findTarget(target);
      if (!info || info.blocked) selected.delete(target);
    }
    root.querySelectorAll('.fee-pick').forEach(box => { box.checked = selected.has(box.dataset.feeTarget); });
    root.querySelector('.fee-selbar')?.remove();
    if (!selected.size) return;
    const bar = document.createElement('div');
    bar.className = 'fee-selbar';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Chuyến đã chọn');
    bar.innerHTML = `<strong>Đã chọn ${selected.size} chuyến</strong><button type="button" class="fee-batch">Thêm một khoản phụ phí cho ${selected.size} chuyến</button><button type="button" class="fee-unselect">Bỏ chọn</button>`;
    root.querySelector('.book-head')?.after(bar);
  }
  root.addEventListener('change', event => {
    if (!event.target.matches('.fee-pick')) return;
    if (event.target.checked) selected.add(event.target.dataset.feeTarget); else selected.delete(event.target.dataset.feeTarget);
    renderSelection();
    if (drawer?.batch) renderDrawer();
  });
  root.addEventListener('click', event => {
    if (event.target.closest('.fee-pick')) return;
    const own = event.target.closest('td.fee.own[data-fee-type]');
    if (own && !own.querySelector('input')) {
      const info = findTarget(own.dataset.feeTarget);
      if (info?.blocked) showNotice(info.blocked); else if (own.classList.contains('fee-edit')) openOwn(own);
      return;
    }
    const other = event.target.closest('td.fee-other');
    if (other) { openDrawer({ target: other.dataset.feeTarget }); return; }
    if (event.target.closest('.fee-batch')) { openDrawer({ batch: true }); return; }
    if (event.target.closest('.fee-unselect')) { selected.clear(); renderSelection(); if (drawer?.batch) closeDrawer(); return; }
    if (event.target.closest('.fee-settings-open')) openSettings();
  });
  root.addEventListener('keydown', event => {
    if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('td.fee[role="button"]')) { event.preventDefault(); event.target.click(); }
  });

  // ---- Cài đặt loại phụ phí ----
  function usedHere(typeId) {
    const snapshot = ctx.snapshot;
    return [...(snapshot?.trips ?? []), ...(snapshot?.legacy_rows ?? [])]
      .filter(row => (row.fee_lines ?? []).some(line => Number(line.fee_type_id) === Number(typeId))).length;
  }
  function renderSettings() {
    const columns = ctx.feeColumnIds;
    const rows = types().map(type => {
      const id = Number(type.id), position = columns.indexOf(id), system = isSystem(type);
      const name = renaming === id ? `<input class="fee-rename" data-id="${id}" value="${escape(type.name)}" aria-label="Tên mới" maxlength="200">` : escape(type.name);
      const column = type.system_key === 'other' ? '<span class="fee-muted">luôn là cột Khác</span>'
        : system ? '<span class="fee-muted">hiện ở cột Khác</span>'
        : `<label class="fee-colbox"><input type="checkbox" class="fee-col" data-id="${id}"${position >= 0 ? ' checked' : ''}${position < 0 && (columns.length >= 3 || !type.active) ? ' disabled' : ''} aria-label="Cột riêng ${escape(type.name)}">${position >= 0 ? `<span class="fee-pos">${position + 1}</span>` : ''}</label>`;
      const move = position >= 0 ? `<button type="button" class="fee-move" data-id="${id}" data-step="-1" ${position === 0 ? 'disabled' : ''} aria-label="Đưa ${escape(type.name)} sang trái">←</button> <button type="button" class="fee-move" data-id="${id}" data-step="1" ${position === columns.length - 1 ? 'disabled' : ''} aria-label="Đưa ${escape(type.name)} sang phải">→</button>` : '';
      const kind = type.system_key === 'discount' ? 'số âm' : system ? '–'
        : `<select class="fee-kind" data-id="${id}" aria-label="Tính chất ${escape(type.name)}"><option value="service"${type.kind === 'service' ? ' selected' : ''}>Phí dịch vụ</option><option value="pass_through"${type.kind === 'pass_through' ? ' selected' : ''}>Chi hộ</option></select>`;
      return `<tr class="${type.active ? '' : 'off'}"><td class="fee-name"${system ? '' : ` data-id="${id}" title="Bấm để đổi tên"`}>${name}${system ? '<br><span class="fee-muted">loại hệ thống — không đổi tên, không ngừng dùng</span>' : ''}${type.active ? '' : ' <span class="fee-muted">(ngừng dùng)</span>'}</td>
        <td>${kind}</td><td class="num">${usedHere(id)}</td><td>${column}</td><td>${move}</td>
        <td>${system ? '' : `<button type="button" class="fee-active" data-id="${id}" data-active="${type.active ? 'false' : 'true'}">${type.active ? 'Ngừng dùng' : 'Dùng lại'}</button>`}</td></tr>`;
    }).join('');
    settingsEl.innerHTML = `<div class="fee-panel"><header><h2>Cài đặt loại phụ phí</h2><button type="button" class="fee-settings-close">Đóng</button></header><div class="fee-panel-body">
      <p class="fee-muted">Danh mục dùng chung cho mọi sổ. <b>Cột riêng</b> chỉ áp cho sổ đang mở: tối đa 3 loại, còn lại hiện ở cột Khác. Bỏ cột riêng không mất số. <b>Chi hộ</b> chỉ là nhãn, vẫn cộng nợ khách.</p>
      ${columns.length >= 3 ? '<p class="fee-info">Đã đủ 3 cột riêng — bỏ chọn một cột trước khi chọn loại khác.</p>' : ''}
      <p class="fee-error" role="alert">${escape(settingsError || typesError)}</p>
      <table class="fee-types"><thead><tr><th>Loại</th><th>Tính chất</th><th class="num">Chuyến dùng ở sổ này</th><th>Cột riêng trên sổ này (${columns.length}/3)</th><th>Thứ tự</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      <form class="fee-newtype"><b>Thêm loại</b><input class="fee-new-name" placeholder="Tên loại, ví dụ Nâng hạ" aria-label="Tên loại mới" maxlength="200"><select class="fee-new-kind" aria-label="Tính chất loại mới"><option value="service">Phí dịch vụ</option><option value="pass_through">Chi hộ</option></select><button type="submit">Thêm loại</button></form>
    </div></div>`;
  }
  function openSettings() { settingsError = ''; renaming = null; settingsEl.hidden = false; renderSettings(); settingsEl.querySelector('.fee-settings-close')?.focus(); }
  function closeSettings() { settingsEl.hidden = true; settingsEl.innerHTML = ''; renaming = null; root.querySelector('.fee-settings-open')?.focus(); }
  async function reloadTypes() {
    try { ctx.feeTypes = await api.loadFeeTypes(); typesError = ''; } catch (problem) { settingsError = problem.message; }
    redraw();
  }
  async function catalog(fields) {
    let outcome;
    try { outcome = await api.submitCatalog(fields.command ? 'feeTypeUpdate' : 'feeTypeAdd', fields); }
    catch (problem) { settingsError = problem.message; renderSettings(); return false; }
    settingsError = outcome.status === 'saved' ? '' : outcome.result?.message || 'Chưa lưu được. Thử lại.';
    renaming = null;
    await reloadTypes();
    return outcome.status === 'saved';
  }
  async function setColumns(ids) {
    settingsError = await send('feeColumns', { fee_type_ids: ids });
    if (!settingsEl.hidden) renderSettings();
  }
  settingsEl.addEventListener('click', event => {
    if (event.target.closest('.fee-settings-close') || event.target === settingsEl) { closeSettings(); return; }
    const move = event.target.closest('.fee-move');
    if (move) {
      const ids = [...ctx.feeColumnIds], index = ids.indexOf(Number(move.dataset.id)), next = index + Number(move.dataset.step);
      [ids[index], ids[next]] = [ids[next], ids[index]];
      setColumns(ids); return;
    }
    const active = event.target.closest('.fee-active');
    if (active) { catalog({ command: 'set_fee_type_active', fee_type_id: Number(active.dataset.id), active: active.dataset.active === 'true' }); return; }
    const name = event.target.closest('td.fee-name[data-id]');
    if (name && !name.querySelector('input')) { renaming = Number(name.dataset.id); renderSettings(); const input = settingsEl.querySelector('.fee-rename'); input.focus(); input.select(); }
  });
  settingsEl.addEventListener('change', event => {
    if (event.target.matches('.fee-col')) {
      const id = Number(event.target.dataset.id);
      setColumns(event.target.checked ? [...ctx.feeColumnIds, id] : ctx.feeColumnIds.filter(item => item !== id)); return;
    }
    if (event.target.matches('.fee-kind')) catalog({ command: 'set_fee_type_kind', fee_type_id: Number(event.target.dataset.id), kind: event.target.value });
  });
  settingsEl.addEventListener('keydown', event => {
    if (event.target.matches('.fee-rename')) {
      if (event.key === 'Escape') { event.preventDefault(); renaming = null; renderSettings(); return; }
      if (event.key !== 'Enter') return;
      event.preventDefault();
      const value = event.target.value.trim(), type = typeOf(event.target.dataset.id);
      if (!value) { settingsError = 'Nhập tên loại'; renderSettings(); return; }
      if (value === type.name) { renaming = null; renderSettings(); return; }
      catalog({ command: 'rename_fee_type', fee_type_id: Number(type.id), name: value });
      return;
    }
    if (event.key === 'Escape') { event.preventDefault(); closeSettings(); }
  });
  settingsEl.addEventListener('submit', async event => {
    event.preventDefault();
    const name = settingsEl.querySelector('.fee-new-name').value.trim();
    if (!name) { settingsError = 'Nhập tên loại'; renderSettings(); return; }
    if (types().some(type => type.name.toLowerCase() === name.toLowerCase())) { settingsError = `Đã có loại ${name}`; renderSettings(); return; }
    await catalog({ name, kind: settingsEl.querySelector('.fee-new-kind').value });
  });

  // ---- Gắn vào vòng vẽ của sổ ----
  ctx.feeAfterRender = () => {
    if (typeof document.createElement !== 'function') return;   // trang thử không có DOM thật
    renderSelection();
    renderDrawer();
    if (!settingsEl.hidden) renderSettings();
  };
  // Đang mở khung, hộp hỏi lại, cài đặt hoặc còn chuyến đánh dấu: tạm dừng tự tải lại sổ.
  ctx.busyChecks.push(() => Boolean(drawer) || !confirmEl.hidden || !settingsEl.hidden || selected.size > 0 || Boolean(root.querySelector?.('.fee-own-input')));
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !confirmEl.hidden || drawerEl.contains(event.target) || settingsEl.contains(event.target)) return;
    if (!settingsEl.hidden) closeSettings(); else if (drawer) closeDrawer();
  });
  // Danh mục dùng tên cho cột riêng và ô chọn loại; đọc lỗi thì cột hiện "Loại #id" và khung báo lỗi, sổ vẫn dùng được.
  api.loadFeeTypes().then(list => { ctx.feeTypes = list; typesError = ''; redraw(); })
    .catch(() => { typesError = 'Không đọc được danh mục phụ phí. Tải lại trang.'; });
};
