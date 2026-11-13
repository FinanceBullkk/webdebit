/* Sổ khách V7 bản live — Tách phụ phí theo bảng PS (specs/v7-phu-phi-tu-ps.md, PR-2; mockup mockups/tach-phu-phi-ps).
 * Server tính chuyến tách được (READY) và chuyến cần xem từ bản chụp CONT_MASTER; trang chỉ hiện và gửi một lệnh
 * cho cả lô. Tách chỉ đổi loại khoản, không đổi tiền. Nạp trước so-khach-v7-ui.js, dùng chung phạm vi qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).ps = ctx => {
  'use strict';
  const { root, model, api, customerId, escape, spanOf, dateText, monthKey, monthLabel, showNotice, renderSnapshot, submit } = ctx;
  // null | 'confirm' | 'review' | { error }; giữ qua lần vẽ lại. psDone: chuyến vừa tách, tô xanh tới thao tác sau.
  let psView = null;
  let psApproval = null;
  let psDone = new Set();
  let nextJump = 0;
  const rowKey = item => `${item.target_kind}-${item.target_id}`;
  const linesText = lines => escape(model.feeLinesText(lines, ctx.feeTypeName));
  const what = item => `<span class="ps-cont">${escape(item.container ?? '')}</span> · ${escape(dateText(item.date))}`;
  // PS-HOI-01 (9/11/2026): mỗi dòng là một câu hỏi có nút trả lời, không chia theo mã lỗi. [câu hỏi, nút hết báo, cách làm
  // nếu trả lời ngược lại]. Trả lời "hết báo" chỉ ghi Lịch sử, không đổi tiền; ô PS hoặc phí chuyến trên web đổi thì hỏi lại.
  const ASK = {
    WEB_NO_FEE: ['Có thu thêm khách khoản này không?', 'Không thu, hết báo', 'Có thu: ghi phí trên tab khách ở Sheet, web tự cập nhật.'],
    PS_BAD_AMOUNT: ['Khoản này có thu khách không?', 'Không thu, hết báo', 'Có thu: ghi phí trên tab khách ở Sheet (số nguyên), web tự cập nhật.'],
    PS_TYPO: ['Số trên PS có đúng không?', 'Bỏ qua, hết báo', 'Gõ sai: sửa bảng PS, lần đọc sau tự cập nhật.'],
    TOTAL_DIFF: ['Phụ phí trên sổ khách đã đúng chưa?', 'Sổ khách đúng, hết báo', 'Chưa đúng: sửa phí trên tab khách ở Sheet.'],
    TYPED_CONFLICT: ['Giữ cách chia loại phí trên web?', 'Giữ, hết báo', 'Theo PS: bấm ô Khác của chuyến, sửa chi tiết phụ phí.'],
    NEED_HEALTH: ['Chuyến này có tính Health cert không?', 'Không tính, hết báo', 'Có tính: bấm ô Khác của chuyến, thêm khoản Health cert.'],
    NEED_KD: ['Chuyến này có tính Kiểm định không?', 'Không tính, hết báo', 'Có tính: bấm ô Khác của chuyến, thêm khoản Kiểm định.'],
    PS_SOURCE_ERROR: ['Bộ lập bill báo lỗi ở dòng này.', 'Bỏ qua, hết báo', 'Cần sửa: sửa trong bộ lập bill.'],
  };
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
  // PS-TAI-HANG-01 (13/11/2026): câu hỏi Phụ phí PS nằm ngay dưới hàng chuyến của nó, như duyệt chuyến mới tại hàng
  // (DUYET-TAI-HANG-01); không còn khung lớn chen giữa đầu sổ và bảng chuyến. Nội dung câu, nút và luật trả lời giữ PS-HOI-01.
  const keepButton = (items, label) => `<button type="button" class="ps-keep" data-keys="${escape(items.map(item => item.source_fingerprint + ':' + rowKey(item)).join(' '))}">${escape(label)}</button>`;
  const contList = items => items.length > 3 ? `${items.slice(0, 2).map(item => item.container).join(', ')} và ${items.length - 2} cont khác` : items.map(item => item.container).join(', ');
  function askLine(item, groups) {
    const tag = '<span class="ps-tag">Phụ phí PS</span>';
    if (item.keepable && ASK[item.status]) {
      const [ask, keep, other] = ASK[item.status];
      // Cùng một khoản PS chia cho nhiều cont: một nút trả lời cho cả nhóm, nói rõ cont nào đi cùng.
      const group = groups.get(groupKey(item));
      const mates = group.filter(entry => entry !== item);
      return `<div class="ps-ask-line"><p>${tag}<span class="ps-says">${escape(item.message)}${mates.length ? ` <span class="ps-count">(cùng khoản với ${escape(contList(mates))})</span>` : ''}</span></p>`
        + `<p><strong class="ps-q">${escape(ask)}</strong>${keepButton(group, group.length > 1 ? `${keep} (${group.length} cont)` : keep)}<small>${escape(other)}</small></p></div>`;
    }
    const month = monthKey(item.month);
    const unlock = item.status === 'MONTH_LOCKED' && month
      ? `<button type="button" class="ps-unlock" data-month="${escape(month)}-01">Mở khóa tháng ${Number(month.slice(5))}</button>` : '';
    return `<div class="ps-ask-line"><p>${tag}<span class="ps-says">${escape(item.message)}</span></p>${HINTS[item.status] || unlock ? `<p>${unlock}${HINTS[item.status] ? `<small>${HINTS[item.status]}</small>` : ''}</p>` : ''}</div>`;
  }
  function decorateAsks(review) {
    const groups = new Map();
    for (const item of review.filter(item => item.keepable && ASK[item.status])) {
      if (!groups.has(groupKey(item))) groups.set(groupKey(item), []);
      groups.get(groupKey(item)).push(item);
    }
    const byRow = new Map();
    for (const item of review.filter(item => item.target_kind)) {
      if (!byRow.has(rowKey(item))) byRow.set(rowKey(item), []);
      byRow.get(rowKey(item)).push(item);
    }
    for (const [key, items] of byRow) {
      const row = root.querySelector(`[data-row="${CSS.escape(key)}"]`);
      if (!row) continue;   // tháng khác: hiện khi xem tháng đó
      row.classList.add('ps-asked');
      row.insertAdjacentHTML('afterend', `<tr class="ps-ask-row" data-ps-row="${escape(key)}"><td colspan="${spanOf(row)}">${items.map(item => askLine(item, groups)).join('')}</td></tr>`);
    }
  }
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
    if (!loose && psView === 'review') psView = null;
    const toggle = ps.unavailable ? '<span class="ps-unavailable">Chưa đọc được bảng PS; nút tách phụ phí tạm ẩn tới lần đọc sau.</span>'
      : review.length ? `<span>Phụ phí PS cần trả lời: <strong>${review.length}</strong></span>`
        + (placed ? `<button type="button" class="ps-next">Đến dòng${placed > 1 ? ' tiếp' : ''}</button>` : '')
        + (loose ? `<span class="ps-sep">·</span><span>${loose} dòng không gắn chuyến</span> <button type="button" class="ps-review-toggle" aria-expanded="${psView === 'review'}">${psView === 'review' ? 'Đóng' : 'Xem'}</button>` : '') : '';
    if (toggle) bar.querySelector('.book-tasks')?.insertAdjacentHTML('beforeend', `<div class="price-strip ps-strip">${toggle}</div>`);
    anchor.insertAdjacentHTML('afterend', panel(ps));
  }
  root.addEventListener('click', async event => {
    const target = event.target.closest('.ps-approve,.ps-cancel,.ps-review-toggle,.ps-reload,.ps-write,.ps-unlock,.ps-next');
    if (!target || target.disabled || !ctx.snapshot) return;
    if (target.matches('.ps-next')) {
      // Lần lượt từng chuyến có câu hỏi: mở đúng tháng, cuộn tới hàng, con trỏ vào nút trả lời.
      const keys = [...new Map((ctx.snapshot.ps_fees?.review ?? []).filter(item => item.target_kind).map(item => [rowKey(item), item])).values()];
      if (!keys.length) return;
      const item = keys[nextJump++ % keys.length];
      ctx.showMonth(monthKey(item.month));
      const row = root.querySelector(`[data-row="${CSS.escape(rowKey(item))}"]`);
      if (!row) { showNotice(`Không thấy chuyến ${item.container ?? ''} trên sổ đang xem.`); return; }
      row.scrollIntoView({ block: 'center' });
      row.classList.remove('ps-flash');
      void row.offsetWidth;
      row.classList.add('ps-flash');
      root.querySelector(`tr.ps-ask-row[data-ps-row="${CSS.escape(rowKey(item))}"]`)?.querySelector('button')?.focus({ preventScroll: true });
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
    const wanted = button.dataset.keys.split(' ');
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
      try { await api.read(); } catch { showNotice('Đã ghi câu trả lời; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
    }
    showNotice(`Đã ghi câu trả lời cho ${done} cont; tiền không đổi, Lịch sử ghi người trả lời. Bảng PS đổi thì máy hỏi lại.`);
  });
  Object.assign(ctx, { psAfterRender });
};
