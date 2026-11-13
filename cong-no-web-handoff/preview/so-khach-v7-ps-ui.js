/* Sổ khách V7 bản live — Tách phụ phí theo bảng PS (specs/v7-phu-phi-tu-ps.md, PR-2; mockup mockups/tach-phu-phi-ps).
 * Server tính chuyến tách được (READY) và chuyến cần xem từ bản chụp CONT_MASTER; trang chỉ hiện và gửi một lệnh
 * cho cả lô. Tách chỉ đổi loại khoản, không đổi tiền. Nạp trước so-khach-v7-ui.js, dùng chung phạm vi qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).ps = ctx => {
  'use strict';
  const { root, model, api, customerId, escape, dateText, monthKey, monthLabel, showNotice, renderSnapshot, submit } = ctx;
  // null | 'confirm' | 'review' | { error }; giữ qua lần vẽ lại. psDone: chuyến vừa tách, tô xanh tới thao tác sau.
  let psView = null;
  let psApproval = null;
  let psDone = new Set();
  let nextJump = 0;
  const rowKey = item => `${item.target_kind}-${item.target_id}`;
  const linesText = lines => escape(model.feeLinesText(lines, ctx.feeTypeName));
  const what = item => `<span class="ps-cont">${escape(item.container ?? '')}</span> · ${escape(dateText(item.date))}`;
  // PS-HOI-01: câu trả lời được bằng nút "không" (chỉ ghi Lịch sử, không đổi tiền); ô PS hoặc phí chuyến trên web đổi thì hỏi lại.
  const ASK = new Set(['WEB_NO_FEE', 'PS_BAD_AMOUNT', 'PS_TYPO', 'TOTAL_DIFF', 'TYPED_CONFLICT', 'NEED_HEALTH', 'NEED_KD', 'PS_SOURCE_ERROR']);
  const HINTS = {
    MONTH_LOCKED: 'Máy tự tách ở lượt chạy sau (tiền không đổi). Muốn tách ngay thì mở khóa tháng.',
    AMBIGUOUS: 'Container khớp nhiều chuyến nên máy không biết chuyến nào: phân loại tay ở đúng chuyến.',
    FEE_TYPE_MISSING: 'Thêm loại đó trong Cài đặt phụ phí.',
  };
  const groupKey = item => `${item.status}|${item.message}`;
  function months(items) {
    const keys = [...new Set(items.map(item => monthKey(item.month)).filter(Boolean))].sort();
    return keys.map(key => `tháng ${monthLabel(key)}`).join(', ');
  }
  function panel(ps) {
    const ready = ps.ready ?? [];
    if (psView === 'confirm' && ready.length) {
      const plan = model.planPsFees(ready);
      const items = ready.map(item => `<li><div class="what">${what(item)} · ${linesText(item.before)}<span class="ps-arrow">→</span>${linesText(item.after)}</div></li>`).join('');
      const same = plan.same
        ? `<span class="ps-same">${plan.fills ? `Tổng còn nợ giữ nguyên: ${plan.fills} chuyến chỉ ghi đủ khoản đã tính sẵn trong Thành tiền.` : `Tổng tiền không đổi: phụ phí ${plan.count} chuyến vẫn là ${model.formatVnd(plan.totalVnd)} đ, tổng còn nợ giữ nguyên.`}</span>`
        : '<p role="alert"><strong>Kế hoạch tách làm đổi tổng tiền nên không tách.</strong> Tải lại sổ.</p>';
      return `<div class="price-panel confirm ps-panel" role="region" aria-label="Xác nhận tách phụ phí theo bảng PS"><p><strong>Tách phụ phí theo bảng PS cho ${plan.count} chuyến ${escape(months(ready))}?</strong></p><ul class="ps-list">${items}</ul>${same}<div class="price-actions"><button type="button" class="ps-write primary" ${plan.same ? '' : 'disabled'}>Tách ${plan.count} chuyến</button><button type="button" class="ps-cancel">Thôi</button></div></div>`;
    }
    if (psView?.error) return `<div class="price-panel err ps-panel" role="alert"><p><strong>Chưa tách chuyến nào.</strong> ${escape(psView.error)}</p><div class="price-actions"><button type="button" class="ps-reload primary">Tải lại sổ</button></div></div>`;
    if (psView !== 'review') return '';
    // Chỉ còn các dòng PS không gắn được chuyến nào trên sổ (ví dụ lỗi của bộ lập bill); dòng có chuyến hỏi ngay ở hàng.
    const loose = (ps.review ?? []).filter(item => !item.target_kind)
      .map(item => `<li><div class="what">${what(item)} · ${escape(item.message)}${HINTS[item.status] ? `<small>${HINTS[item.status]}</small>` : ''}</div></li>`).join('');
    return `<div class="price-panel ps-panel ps-review" role="region" aria-label="Dòng PS không gắn được chuyến"><ul>${loose}</ul></div>`;
  }
  // PS-O-KHAC-01 (13/11/2026, thay hàng hỏi của PS-TAI-HANG-01): mỗi chuyến có phụ phí phát sinh cần xem có một nhãn cam trong
  // ô Khác; bấm nhãn mở hộp nhỏ cạnh ô: bảng chi phí ghi bao nhiêu, sổ khách đang tính bao nhiêu, chênh bao nhiêu, và hai nút
  // ngang nhau. Nút "không" chỉ ghi Lịch sử, không đổi tiền (PS-HOI-01); nút "có" chỉ chỗ sửa vì web không cộng tiền theo PS.
  const big = value => value == null || value === '' ? null : BigInt(value);
  const money = value => `${model.formatVnd(value)} đ`;
  const signed = value => `${value > 0n ? '+' : ''}${model.formatVnd(value)}`;
  const SHEET_HOW = 'Ghi phụ phí trên tab khách ở Sheet; web tự cập nhật ở lần đọc Sheet sau.';
  function explain(item) {
    const ps = big(item.ps_total), web = big(item.web_total) ?? 0n;
    const nums = value => [['Bảng chi phí ghi', money(value)], ['Sổ khách đang tính', money(web)], ['Chênh', `${signed(value - web)} đ`, 'ps-diff']];
    const cell = item.ps_value != null ? `${item.ps_field ?? ''} ${item.ps_value}`.trim() : null;
    switch (item.status) {
      case 'WEB_NO_FEE': return ps === null ? null : { chip: signed(ps), title: 'Phụ phí phát sinh chưa tính khách', nums: nums(ps),
        no: 'Không tính khách', yes: 'Tính khách…', how: SHEET_HOW };
      case 'TOTAL_DIFF': return ps === null ? null : { chip: signed(ps - web), title: 'Phụ phí phát sinh khác sổ khách', nums: nums(ps),
        no: 'Sổ khách đúng', yes: 'Theo bảng chi phí…', how: 'Sửa phụ phí trên tab khách ở Sheet; web tự cập nhật ở lần đọc Sheet sau.' };
      case 'PS_BAD_AMOUNT': return { chip: `${item.ps_value ?? 'số lẻ'} ?`, title: 'Bảng chi phí ghi số lẻ',
        text: cell ? `Ô ${cell}: không phải số đồng nguyên nên máy không đọc được.` : item.message,
        ask: 'Khoản này có tính khách không?', no: 'Không tính khách', yes: 'Tính khách…',
        how: 'Ghi phụ phí (số đồng nguyên) trên tab khách ở Sheet; web tự cập nhật ở lần đọc Sheet sau.' };
      case 'PS_TYPO': return { chip: `${cell ?? 'số lạ'} ?`, title: 'Bảng chi phí có thể gõ sai',
        text: cell ? `Ô ${cell} nhỏ bất thường.` : item.message, ask: 'Số này có đúng không?', no: 'Số đúng, bỏ qua', yes: 'Gõ sai…',
        how: 'Sửa trên bảng chi phí; lần đọc sau web tự cập nhật.' };
      case 'TYPED_CONFLICT': return { chip: 'loại ?', title: 'Loại phụ phí khác bảng chi phí',
        text: 'Tổng tiền bằng nhau, nhưng sổ khách chia loại phụ phí khác bảng chi phí.', ask: 'Giữ cách chia trên sổ khách?',
        no: 'Giữ như sổ khách', fee: 'Chia lại từng khoản' };
      case 'NEED_HEALTH': case 'NEED_KD': {
        const name = item.status === 'NEED_HEALTH' ? 'Health cert' : 'Kiểm định';
        return { chip: `${item.status === 'NEED_HEALTH' ? 'Health' : 'KĐ'} ?`, title: `Bảng chi phí đánh dấu ${name}`,
          text: `Bảng chi phí đánh dấu chuyến này có ${name} nhưng không ghi giá.`, ask: `Chuyến này có tính ${name} không?`,
          no: 'Không tính', fee: `Có tính: nhập giá ${name}` };
      }
      case 'PS_SOURCE_ERROR': return { chip: 'lỗi ?', title: 'Bộ lập bill báo lỗi ở dòng này', text: item.message,
        no: 'Bỏ qua', yes: 'Cần sửa…', how: 'Sửa trong bộ lập bill; lần đọc sau web tự cập nhật.' };
      case 'MONTH_LOCKED': return { chip: 'chờ tách', title: 'Chưa tách phụ phí: tháng đang khóa', text: HINTS.MONTH_LOCKED, unlock: true };
      default: return { chip: '?', title: item.message || 'Phụ phí phát sinh cần xem', text: HINTS[item.status] ?? '' };
    }
  }
  const keyOf = item => `${item.source_fingerprint}:${rowKey(item)}`;
  const contList = items => items.length > 3 ? `${items.slice(0, 2).map(item => item.container).join(', ')} và ${items.length - 2} cont khác` : items.map(item => item.container).join(', ');
  // Chuyến đang mở hộp, câu đã bấm "có…" (hiện cách làm), câu bỏ tick "trả lời luôn cho cont cùng khoản"; giữ qua lần vẽ lại.
  let openKey = null;
  const shown = new Set();
  const alone = new Set();
  let asked = { byRow: new Map(), groups: new Map() };
  function decorateAsks(review) {
    const groups = new Map();
    for (const item of review.filter(item => item.keepable && ASK.has(item.status))) {
      if (!groups.has(groupKey(item))) groups.set(groupKey(item), []);
      groups.get(groupKey(item)).push(item);
    }
    const byRow = new Map();
    for (const item of review.filter(item => item.target_kind && explain(item))) {
      if (!byRow.has(rowKey(item))) byRow.set(rowKey(item), []);
      byRow.get(rowKey(item)).push(item);
    }
    asked = { byRow, groups };
    for (const [key, items] of byRow) {
      const row = root.querySelector(`[data-row="${CSS.escape(key)}"]`);
      if (!row) continue;   // tháng khác: hiện khi xem tháng đó
      row.classList.add('ps-asked');
      const cell = row.querySelector('td.fee-other') ?? row.querySelector('td:last-child');
      const label = `${explain(items[0]).chip}${items.length > 1 ? ` · ${items.length}` : ''}`;
      cell?.insertAdjacentHTML('afterbegin', `<button type="button" class="ps-chip" data-ps-row="${escape(key)}" aria-haspopup="dialog" `
        + `aria-expanded="${openKey === key}" aria-label="Phụ phí phát sinh cần xem: ${escape(items[0].container ?? '')}">${escape(label)}</button>`);
    }
  }
  function popItem(item) {
    const view = explain(item);
    const group = asked.groups.get(groupKey(item)) ?? [item];
    const mates = group.filter(entry => entry !== item);
    const month = monthKey(item.month);
    const keep = item.keepable && view.no
      ? `<button type="button" class="ps-keep primary" data-own="${escape(keyOf(item))}" data-keys="${escape(group.map(keyOf).join(' '))}">${escape(view.no)}</button>` : '';
    const yes = view.fee ? `<button type="button" class="ps-fee-open" data-target="${escape(rowKey(item))}">${escape(view.fee)}</button>`
      : view.yes ? `<button type="button" class="ps-yes" data-item="${escape(keyOf(item))}" aria-expanded="${shown.has(keyOf(item))}">${escape(view.yes)}</button>` : '';
    const unlock = view.unlock && month ? `<button type="button" class="ps-unlock primary" data-month="${escape(month)}-01">Mở khóa tháng ${Number(month.slice(5))}</button>` : '';
    return `<section class="ps-pop-item"><h3>${escape(view.title)}</h3>`
      + (view.nums ? `<dl class="ps-nums">${view.nums.map(([label, value, cls]) => `<div${cls ? ` class="${cls}"` : ''}><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`).join('')}</dl>` : '')
      + (view.text ? `<p>${escape(view.text)}</p>` : '') + (view.ask ? `<p class="ps-q">${escape(view.ask)}</p>` : '')
      + (keep && mates.length ? `<label class="ps-group"><input type="checkbox" class="ps-group-pick" data-item="${escape(keyOf(item))}"${alone.has(keyOf(item)) ? '' : ' checked'}> Trả lời luôn cho ${escape(contList(mates))} (cùng khoản)</label>` : '')
      + `<div class="ps-pop-actions">${keep}${yes}${unlock}</div>`
      + (view.how ? `<p class="ps-how"${shown.has(keyOf(item)) ? '' : ' hidden'}>${escape(view.how)}</p>` : '') + '</section>';
  }
  function placePop() {
    const pop = root.querySelector('.ps-pop');
    const chip = openKey && root.querySelector(`.ps-chip[data-ps-row="${CSS.escape(openKey)}"]`);
    if (!pop || !chip) return;
    const rect = chip.getBoundingClientRect();
    const width = pop.offsetWidth, height = pop.offsetHeight;
    pop.style.left = `${Math.max(8, Math.min(rect.right - width, innerWidth - width - 8))}px`;
    pop.style.top = `${rect.bottom + 8 + height > innerHeight - 8 && rect.top - height - 8 > 0 ? rect.top - height - 8 : rect.bottom + 8}px`;
  }
  function renderPop() {
    root.querySelectorAll('.ps-pop').forEach(node => node.remove());
    const items = openKey && asked.byRow.get(openKey);
    if (!items || !root.querySelector(`.ps-chip[data-ps-row="${CSS.escape(openKey)}"]`)) { openKey = null; return; }
    root.insertAdjacentHTML('beforeend', `<div class="ps-pop" role="dialog" aria-label="Phụ phí phát sinh ${escape(items[0].container ?? '')}">`
      + `<div class="ps-pop-head"><span>${what(items[0])}</span><button type="button" class="ps-pop-close" aria-label="Đóng">×</button></div>${items.map(popItem).join('')}</div>`);
    placePop();
  }
  function openPop(key) {
    openKey = key;
    root.querySelectorAll('.ps-chip').forEach(chip => chip.setAttribute('aria-expanded', String(chip.dataset.psRow === key)));
    renderPop();
    root.querySelector('.ps-pop .ps-pop-actions button')?.focus({ preventScroll: true });
  }
  function closePop(focusChip) {
    const key = openKey;
    openKey = null;
    root.querySelectorAll('.ps-pop').forEach(node => node.remove());
    root.querySelectorAll('.ps-chip[aria-expanded="true"]').forEach(chip => chip.setAttribute('aria-expanded', 'false'));
    if (focusChip && key) root.querySelector(`.ps-chip[data-ps-row="${CSS.escape(key)}"]`)?.focus();
  }
  // Nhãn nằm trong ô Khác (ô mở chi tiết phụ phí): bắt ở pha bắt sự kiện để bấm nhãn chỉ mở hộp. Bấm ngoài hộp thì đóng.
  document.addEventListener('click', event => {
    const chip = event.target.closest?.('.ps-chip');
    if (chip && root.contains(chip)) {
      event.stopPropagation();
      event.preventDefault();
      if (openKey === chip.dataset.psRow) closePop(); else openPop(chip.dataset.psRow);
      return;
    }
    if (openKey && !event.target.closest?.('.ps-pop')) closePop();
  }, true);
  document.addEventListener('keydown', event => { if (openKey && event.key === 'Escape') { event.preventDefault(); closePop(true); } });
  document.addEventListener('scroll', placePop, { capture: true, passive: true });
  window.addEventListener?.('resize', placePop);
  root.addEventListener('change', event => {
    const pick = event.target.closest('.ps-group-pick');
    if (!pick) return;
    if (pick.checked) alone.delete(pick.dataset.item); else alone.add(pick.dataset.item);
  });
  root.addEventListener('click', event => {
    const button = event.target.closest('.ps-pop-close,.ps-yes,.ps-fee-open');
    if (!button) return;
    if (button.matches('.ps-pop-close')) { closePop(true); return; }
    if (button.matches('.ps-yes')) {
      const key = button.dataset.item;
      if (shown.has(key)) shown.delete(key); else shown.add(key);
      button.setAttribute('aria-expanded', String(shown.has(key)));
      const how = button.closest('.ps-pop-item')?.querySelector('.ps-how');
      if (how) how.hidden = !shown.has(key);
      placePop();
      return;
    }
    // "Có tính" với khoản theo loại: mở đúng khung chi tiết phụ phí của chuyến (cùng chỗ bấm ô Khác).
    const cell = root.querySelector(`[data-row="${CSS.escape(button.dataset.target)}"] td.fee-other`);
    closePop();
    cell?.click();
  });
  // Cụm ô phụ phí của một dòng hiện theo danh sách khoản (khi xác nhận: kết quả dự kiến sau khi tách).
  function showLines(row, lines) {
    const cells = model.feeCells(lines, ctx.feeColumnIds);
    ctx.feeColumnIds.forEach((id, index) => {
      const cell = row.querySelector(`td.fee.own[data-fee-type="${CSS.escape(String(id))}"]`);
      if (cell) cell.textContent = cells.own[index] === null ? '' : model.formatVnd(cells.own[index]);
    });
    const other = row.querySelector('td.fee-other');
    if (other) other.innerHTML = cells.otherCount ? `<span class="fee-sum">${model.formatVnd(cells.otherVnd)}</span><small>${cells.otherCount} khoản</small>` : '';
  }
  function psAfterRender(data, active) {
    const ps = active ? data.ps_fees ?? {} : {};
    const ready = ps.ready ?? [];
    const review = ps.review ?? [];
    if (!ready.length && psView === 'confirm') psView = null;
    if (!review.length && psView === 'review') psView = null;
    for (const key of psDone) root.querySelector(`[data-row="${CSS.escape(key)}"]`)?.classList.add('ps-done');
    for (const item of ready) {
      const row = root.querySelector(`[data-row="${CSS.escape(rowKey(item))}"]`);
      if (!row) continue;
      row.classList.add(psView === 'confirm' ? 'ps-plan' : 'ps-ready');
      if (psView === 'confirm') showLines(row, item.after);
    }
    // SO-GON-04 (L7): nút việc chờ nằm ở dải ngay dưới đầu sổ, cùng các nút ghi từ Sheet.
    const bar = root.querySelector('.book-bar');
    if (!bar) return;
    if (ready.length && psView !== 'confirm') bar.querySelector('.book-tasks')?.insertAdjacentHTML('afterbegin', `<button type="button" class="ps-approve">Tách ${ready.length} phụ phí theo bảng PS</button>`);
    decorateAsks(review);
    // Thanh việc chỉ báo số và nút "Đến dòng" (như "Đến chuyến" của chuyến mới); dòng không gắn chuyến mới cần nút Xem.
    let anchor = bar;
    while (anchor.nextElementSibling?.matches('.price-panel')) anchor = anchor.nextElementSibling;
    const placed = review.filter(item => item.target_kind).length;
    const loose = review.length - placed;
    const conts = new Set(review.filter(item => item.target_kind).map(rowKey)).size;
    if (!loose && psView === 'review') psView = null;
    const toggle = ps.unavailable ? '<span class="ps-unavailable">Chưa đọc được bảng PS; nút tách phụ phí tạm ẩn tới lần đọc sau.</span>'
      : review.length ? (placed ? `<span><strong>${conts}</strong> cont có phụ phí phát sinh cần xem</span><button type="button" class="ps-next">Đến cont${conts > 1 ? ' tiếp' : ''}</button>` : '')
        + (loose ? `${placed ? '<span class="ps-sep">·</span>' : ''}<span>${loose} dòng phụ phí phát sinh không gắn chuyến</span> <button type="button" class="ps-review-toggle" aria-expanded="${psView === 'review'}">${psView === 'review' ? 'Đóng' : 'Xem'}</button>` : '') : '';
    if (toggle) bar.querySelector('.book-tasks')?.insertAdjacentHTML('beforeend', `<div class="price-strip ps-strip">${toggle}</div>`);
    anchor.insertAdjacentHTML('afterend', panel(ps));
    renderPop();
  }
  root.addEventListener('click', async event => {
    const target = event.target.closest('.ps-approve,.ps-cancel,.ps-review-toggle,.ps-reload,.ps-write,.ps-unlock,.ps-next');
    if (!target || target.disabled || !ctx.snapshot) return;
    if (target.matches('.ps-next')) {
      // Lần lượt từng chuyến có câu hỏi: mở đúng tháng, cuộn tới hàng, con trỏ vào nút trả lời.
      const keys = [...asked.byRow.values()].map(items => items[0]);
      if (!keys.length) return;
      const item = keys[nextJump++ % keys.length];
      ctx.showMonth(monthKey(item.month));
      const row = root.querySelector(`[data-row="${CSS.escape(rowKey(item))}"]`);
      if (!row) { showNotice(`Không thấy chuyến ${item.container ?? ''} trên sổ đang xem.`); return; }
      row.scrollIntoView({ block: 'center' });
      row.classList.remove('ps-flash');
      void row.offsetWidth;
      row.classList.add('ps-flash');
      openPop(rowKey(item));
      return;
    }
    if (target.matches('.ps-approve,.ps-cancel,.ps-review-toggle')) {
      psDone = new Set();
      psView = target.matches('.ps-approve') ? 'confirm'
        : target.matches('.ps-review-toggle') && psView !== 'review' ? 'review' : null;
      renderSnapshot(ctx.snapshot);
      root.querySelector(psView === 'confirm' ? '.ps-write' : '.ps-review-toggle')?.focus();
      return;
    }
    if (target.matches('.ps-reload')) {
      psView = null;
      psApproval = null;
      await api.read().catch(() => showNotice('Không tải được sổ mới. Thử lại.'));
      return;
    }
    if (target.matches('.ps-unlock')) { await submit('lock', { month: target.dataset.month, locked: false }); return; }
    // Tách cả lô: giữ nguyên khóa khi chưa rõ kết quả để bấm lại không tách trùng (server cũng chặn theo từng chuyến).
    if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
    const ps = ctx.snapshot.ps_fees;
    psApproval ??= { customer_id: customerId, expected_version: ctx.snapshot.version,
      snapshot_sha256: ps.snapshot_sha256, idempotency_key: crypto.randomUUID() };
    const keys = (ps.ready ?? []).map(rowKey);
    const plan = model.planPsFees(ps.ready);
    target.disabled = true;
    let response, result;
    try {
      response = await fetch('/api/v7/ps/fees', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(psApproval) });
      result = await response.json();
    } catch {
      target.disabled = false;
      showNotice('Chưa rõ kết quả tách phụ phí. Tải lại sổ để kiểm tra trước khi thử lại.');
      return;
    }
    psApproval = null;
    if (!response.ok) {
      psView = { error: result.error === 'STALE_SHEET' ? 'Bảng PS đã đổi sau khi mở sổ. Tải lại rồi tách.'
        : result.error === 'STALE_LEDGER' ? 'Sổ vừa thay đổi. Tải lại rồi tách.' : result.message || 'Không tách được phụ phí theo bảng PS.' };
      renderSnapshot(ctx.snapshot);
      return;
    }
    psView = null;
    psDone = new Set(result.complete === false ? [] : keys);
    try { await api.read(); } catch { showNotice('Đã tách phụ phí; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
    showNotice(result.complete === false
      ? `Đã tách ${result.written} chuyến; còn ${result.remaining} chuyến chưa tách. Bấm "Tách … phụ phí theo bảng PS" để tách tiếp.`
      : `Đã tách phụ phí ${result.written} chuyến theo bảng PS. Tổng tiền không đổi${plan.same ? ` (${model.formatVnd(plan.totalVnd)} đ phụ phí)` : ''}; Lịch sử ghi từng chuyến.`);
  });
  // "… hết báo": một lệnh giữ cho mỗi chuyến (keep_sheet_task 'ps'), lần lượt, đọc lại sổ giữa hai lệnh để có version mới.
  // Chưa rõ kết quả thì bấm lại gửi đúng khóa cũ (không ghi Lịch sử hai lần).
  const keepBodies = new Map();
  root.addEventListener('click', async event => {
    const button = event.target.closest('.ps-keep');
    if (!button || button.disabled || !ctx.snapshot) return;
    if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
    // Bỏ tick "trả lời luôn cho cont cùng khoản" thì chỉ trả lời chuyến đang mở.
    const wanted = (button.closest('.ps-pop-item')?.querySelector('.ps-group-pick')?.checked === false ? button.dataset.own : button.dataset.keys).split(' ');
    button.disabled = true;
    let done = 0;
    for (const key of wanted) {
      const [fingerprint, target] = key.split(':');
      const split = target.indexOf('-');
      let body = keepBodies.get(key);
      if (!body) {
        body = { customer_id: customerId, expected_version: ctx.snapshot.version, idempotency_key: crypto.randomUUID(), task_kind: 'ps',
          target_kind: target.slice(0, split), target_id: Number(target.slice(split + 1)), source_fingerprint: fingerprint };
        keepBodies.set(key, body);
      }
      let response, result;
      try {
        response = await fetch('/api/v7/sheet/tasks/keep', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        result = await response.json();
      } catch {
        button.disabled = false;
        showNotice(`Chưa rõ kết quả${done ? ` (đã xong ${done}/${wanted.length})` : ''}. Bấm lại để thử đúng thao tác đó.`);
        return;
      }
      keepBodies.delete(key);
      if (!response.ok) {
        await api.read().catch(() => {});
        showNotice(`${done ? `Đã trả lời ${done}/${wanted.length} cont. ` : ''}${result.message || 'Dòng PS hoặc sổ vừa đổi. Xem lại câu hỏi.'}`);
        return;
      }
      done += 1;
      if (done === wanted.length) openKey = null;
      try { await api.read(); } catch { showNotice('Đã ghi câu trả lời; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
    }
    showNotice(`Đã ghi câu trả lời cho ${done} cont; số nợ không đổi, Lịch sử ghi người chọn. Bảng chi phí đổi thì máy hỏi lại.`);
  });
  Object.assign(ctx, { psAfterRender });
};
