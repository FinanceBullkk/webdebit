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
    const jump = item => item.target_kind && root.querySelector(`[data-row="${CSS.escape(rowKey(item))}"]`)
      ? `<button type="button" class="ps-jump" data-target="${escape(rowKey(item))}">Xem dòng</button>` : '';
    const keepButton = (items, label) => `<button type="button" class="ps-keep" data-keys="${escape(items.map(item => item.source_fingerprint + ':' + rowKey(item)).join(' '))}">${escape(label)}</button>`;
    const review = ps.review ?? [];
    // Dòng trả lời được, cùng câu (ví dụ cùng một khoản PS chia cho nhiều cont): gom một khối, một nút cho cả nhóm.
    const groups = new Map();
    for (const item of review.filter(item => item.keepable && ASK[item.status])) {
      if (!groups.has(groupKey(item))) groups.set(groupKey(item), []);
      groups.get(groupKey(item)).push(item);
    }
    const asked = [...groups.values()].map(items => {
      const [ask, keep, other] = ASK[items[0].status];
      const conts = items.map(item => `<li><div class="what">${what(item)}</div>${jump(item)}</li>`).join('');
      return `<section class="ps-ask"><p class="ps-says">${escape(items[0].message)}${items.length > 1 ? ` <span class="ps-count">· ${items.length} cont</span>` : ''}</p>`
        + `<ul class="ps-conts">${conts}</ul><p class="ps-q"><strong>${escape(ask)}</strong></p>`
        + `<div class="ps-answer">${keepButton(items, items.length > 1 ? `${keep} (${items.length} cont)` : keep)}<small>${escape(other)}</small></div></section>`;
    }).join('');
    const rest = review.filter(item => !(item.keepable && ASK[item.status])).map(item => {
      const month = monthKey(item.month);
      const unlock = item.status === 'MONTH_LOCKED' && month
        ? `<button type="button" class="ps-unlock" data-month="${escape(month)}-01">Mở khóa tháng ${Number(month.slice(5))}</button>` : '';
      return `<li><div class="what">${what(item)} · ${escape(item.message)}${HINTS[item.status] ? `<small>${HINTS[item.status]}</small>` : ''}</div>${unlock}${jump(item)}</li>`;
    }).join('');
    return `<div class="price-panel ps-panel ps-review" role="region" aria-label="Phụ phí PS cần trả lời">`
      + '<p class="ps-intro">Bảng chi phí PS ghi khác sổ khách. <strong>Tiền trên web chưa đổi.</strong> Trả lời từng câu để hết báo; ô PS hoặc phí của chuyến đổi thì máy hỏi lại.</p>'
      + asked + (rest ? `<h3>Máy hoặc bạn sửa ở chỗ khác</h3><ul>${rest}</ul>` : '') + '</div>';
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
    // Một dải "cần xem" chung với giá từ Sheet (một ô trong thanh việc, SO-GON-06); chưa có dải đó thì tự tạo.
    let anchor = bar;
    while (anchor.nextElementSibling?.matches('.price-panel')) anchor = anchor.nextElementSibling;
    const toggle = ps.unavailable ? '<span class="ps-unavailable">Chưa đọc được bảng PS; nút tách phụ phí tạm ẩn tới lần đọc sau.</span>'
      : review.length ? `Phụ phí PS cần trả lời: <strong>${review.length}</strong> <button type="button" class="ps-review-toggle" aria-expanded="${psView === 'review'}">${psView === 'review' ? 'Đóng' : 'Xem'}</button>` : '';
    const strip = toggle && root.querySelector('.price-strip:has(.price-review-toggle)');
    if (strip) strip.insertAdjacentHTML('beforeend', `<span class="ps-sep">|</span>${toggle}`);
    else if (toggle) bar.querySelector('.book-tasks')?.insertAdjacentHTML('beforeend', `<div class="price-strip ps-strip">${toggle}</div>`);
    anchor.insertAdjacentHTML('afterend', panel(ps));
  }
  root.addEventListener('click', async event => {
    const target = event.target.closest('.ps-approve,.ps-cancel,.ps-review-toggle,.ps-reload,.ps-write,.ps-unlock,.ps-jump');
    if (!target || target.disabled || !ctx.snapshot) return;
    if (target.matches('.ps-jump')) {
      const row = root.querySelector(`[data-row="${CSS.escape(target.dataset.target)}"]`);
      row?.scrollIntoView({ block: 'center' });
      row?.classList.remove('ps-flash');
      void row?.offsetWidth;
      row?.classList.add('ps-flash');
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
