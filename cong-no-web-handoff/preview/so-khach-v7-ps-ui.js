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
  // Nhóm theo việc người nhập phải làm (bảng "Không tự tách" ở bước 1 của spec).
  const GROUPS = [
    ['Mở khóa tháng là tách được', ['MONTH_LOCKED']],
    ['Sửa trên web (bấm ô Khác của chuyến để mở chi tiết phụ phí)', ['TOTAL_DIFF', 'PS_COMBINED', 'NEED_HEALTH', 'NEED_KD', 'AMBIGUOUS', 'TYPED_CONFLICT', 'FEE_TYPE_MISSING']],
    ['Sửa ở Sheet hoặc bộ lập bill (lần đọc sau tự cập nhật)', ['WEB_NO_FEE', 'PS_TYPO', 'PS_BAD_AMOUNT', 'PS_SOURCE_ERROR']],
  ];
  const HINTS = {
    TOTAL_DIFF: 'Kiểm tab khách trên Sheet (sổ chính thức). Web sai thì sửa trong chi tiết phụ phí.',
    PS_COMBINED: 'Chia ra Health cert và Kiểm định trong chi tiết phụ phí.',
    NEED_HEALTH: 'Thêm khoản Health cert trong chi tiết phụ phí. Ghi xong thì dòng này tự hết.',
    NEED_KD: 'Thêm khoản Kiểm định trong chi tiết phụ phí. Ghi xong thì dòng này tự hết.',
    AMBIGUOUS: 'Phân loại tay ở đúng chuyến.',
    TYPED_CONFLICT: 'Web đã có khoản khác PS. Kiểm Sheet rồi sửa trong chi tiết phụ phí.',
    FEE_TYPE_MISSING: 'Thêm loại đó trong Cài đặt phụ phí.',
    WEB_NO_FEE: 'Ghi phí trên tab khách như mọi khi; có giá từ Sheet rồi thì chuyến này vào nút Tách.',
    PS_TYPO: 'Sửa bảng PS, hoặc phân loại tay trên web.',
    PS_BAD_AMOUNT: 'Sửa bảng PS, hoặc phân loại tay trên web.',
    PS_SOURCE_ERROR: 'Sửa trong bộ lập bill.',
  };
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
        ? `<span class="ps-same">Tổng tiền không đổi: phụ phí ${plan.count} chuyến vẫn là ${model.formatVnd(plan.totalVnd)} đ, tổng còn nợ giữ nguyên.</span>`
        : '<p role="alert"><strong>Kế hoạch tách làm đổi tổng tiền nên không tách.</strong> Tải lại sổ.</p>';
      return `<div class="price-panel confirm ps-panel" role="region" aria-label="Xác nhận tách phụ phí theo bảng PS"><p><strong>Tách phụ phí theo bảng PS cho ${plan.count} chuyến ${escape(months(ready))}?</strong></p><ul class="ps-list">${items}</ul>${same}<div class="price-actions"><button type="button" class="ps-write primary" ${plan.same ? '' : 'disabled'}>Tách ${plan.count} chuyến</button><button type="button" class="ps-cancel">Thôi</button></div></div>`;
    }
    if (psView?.error) return `<div class="price-panel err ps-panel" role="alert"><p><strong>Chưa tách chuyến nào.</strong> ${escape(psView.error)}</p><div class="price-actions"><button type="button" class="ps-reload primary">Tải lại sổ</button></div></div>`;
    if (psView !== 'review') return '';
    const line = item => {
      const month = monthKey(item.month);
      const jump = item.target_kind && root.querySelector(`[data-row="${CSS.escape(rowKey(item))}"]`)
        ? `<button type="button" class="ps-jump" data-target="${escape(rowKey(item))}">Xem dòng</button>` : '';
      const unlock = item.status === 'MONTH_LOCKED' && month
        ? `<button type="button" class="ps-unlock" data-month="${escape(month)}-01">Mở khóa tháng ${Number(month.slice(5))}</button>` : '';
      return `<li><div class="what">${what(item)} · ${escape(item.message)}${HINTS[item.status] ? `<small>${HINTS[item.status]}</small>` : ''}</div>${unlock}${jump}</li>`;
    };
    const review = ps.review ?? [];
    const groups = GROUPS.map(([title, codes]) => [title, review.filter(item => codes.includes(item.status))]).filter(([, items]) => items.length);
    return `<div class="price-panel ps-panel ps-review" role="region" aria-label="Phụ phí PS cần xem">${groups.map(([title, items]) => `<h3>${title}</h3><ul>${items.map(line).join('')}</ul>`).join('')}</div>`;
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
    const head = root.querySelector('.book-head');
    if (!head) return;
    if (ready.length && psView !== 'confirm') head.querySelector('.total')?.insertAdjacentHTML('beforebegin', `<button type="button" class="ps-approve">Tách ${ready.length} phụ phí theo bảng PS</button>`);
    // Một dải "cần xem" chung với giá từ Sheet; chưa có dải đó thì tự tạo.
    let anchor = head;
    while (anchor.nextElementSibling?.matches('.price-strip,.price-panel')) anchor = anchor.nextElementSibling;
    const toggle = ps.unavailable ? '<span class="ps-unavailable">Chưa đọc được bảng PS; nút tách phụ phí tạm ẩn tới lần đọc sau.</span>'
      : review.length ? `Phụ phí PS cần xem: <strong>${review.length}</strong> <button type="button" class="ps-review-toggle" aria-expanded="${psView === 'review'}">${psView === 'review' ? 'Đóng' : 'Xem'}</button>` : '';
    const strip = toggle && root.querySelector('.price-strip:has(.price-review-toggle)');
    if (strip) strip.insertAdjacentHTML('beforeend', `<span class="ps-sep">|</span>${toggle}`);
    else if (toggle) { anchor.insertAdjacentHTML('afterend', `<div class="price-strip ps-strip">${toggle}</div>`); anchor = anchor.nextElementSibling; }
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
  Object.assign(ctx, { psAfterRender });
};
