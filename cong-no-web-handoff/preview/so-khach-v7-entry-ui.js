/* Sổ khách V7 bản live — Ghi phiếu thu tay (SO-GON-04, specs/v7-so-khach-ux-dot-2.md L2). Một nút "Ghi phiếu thu" ở đầu sổ
 * mở khung bên phải, cùng mẫu ngăn phụ phí: khung nằm ngoài #app nên vẽ lại sổ không mất chữ đang gõ. Enter ở ô Số tiền (hoặc
 * nút Xem lại) hiện bước xem lại, chưa gửi lệnh; nút Ghi phiếu mới gửi đúng một lệnh. Ghi xong: tháng của phiếu hiện chi tiết,
 * dòng phiếu tô 3 giây, băng kết quả ghi phần trừ nợ theo sổ vừa tải và nút "Hủy phiếu vừa ghi" (H3: mở dòng hủy phiếu có lý do
 * điền sẵn, người dùng tự bấm Hủy phiếu). Hình thức CẤN TRỪ đi hộp xác nhận của so-khach-v7-offset-ui.js. Tiền tính ở model
 * (ARCH-03). Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).entry = ctx => {
  'use strict';
  const { root, model, api, live, customerId, escape, fmt, dateText, monthKey, monthLabel, liveOpenMonth, methods, moneyText,
    referenceFields, showNotice, submit } = ctx;
  // Khóa nháp ảnh chứng từ của khung (so-khach-v7-images-ui.js giữ ảnh theo khóa này tới khi phiếu ghi xong).
  const KEY = 'phieu-moi';
  const VOID_REASON = 'Ghi nhầm, hủy ngay sau khi ghi';
  let step = 'form';     // 'form' | 'review'
  let review = null;     // { date, method, amount, reference } đã kiểm, chờ bấm Ghi phiếu
  let saving = false;
  let lastSaved = null;  // { pid, date, amount, duplicate, imageText } cho băng kết quả
  const drawer = typeof document.createElement === 'function' ? document.createElement('aside') : null;
  if (drawer) {
    drawer.className = 'entry-drawer';
    drawer.hidden = true;
    drawer.setAttribute('aria-label', 'Ghi phiếu thu');
    document.body.append(drawer);
  }
  const $ = selector => drawer.querySelector(selector);
  const isOpen = () => Boolean(drawer && !drawer.hidden);
  const active = () => ctx.snapshot?.status === 'active';
  // Khung đang mở thì tạm dừng tự cập nhật, để số trước → sau ở bước xem lại không đổi dưới tay.
  ctx.busyChecks.push(isOpen);

  const formHtml = () => `<header><h2>Ghi phiếu thu<small class="entry-customer"></small></h2><button type="button" class="entry-close">Đóng</button></header>
    <div class="entry-body"><div class="entry-form">
      <label class="entry-field"><span>Ngày trả</span><span class="entry-date"><input class="receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric" autocomplete="off"><button type="button" class="entry-today">Hôm nay</button></span></label>
      <span class="cell-error receipt-date-error" role="status"></span>
      <label class="entry-field"><span>Hình thức</span><select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${escape(method)}</option>`).join('')}</select></label>
      <div class="offset-slot"></div>
      <label class="entry-field"><span>Số tiền (VND)</span><input class="receipt-amount" aria-label="Số tiền trả" inputmode="numeric" autocomplete="off"></label>
      <span class="cell-error receipt-amount-error" role="status"></span>
      <label class="entry-field"><span>Tham chiếu</span><input class="receipt-reference" aria-label="Tham chiếu" maxlength="500" placeholder="Tùy chọn" autocomplete="off"></label>
      <div class="entry-images"></div>
      <div class="entry-actions"><button type="button" class="entry-next">Xem lại</button></div>
    </div><div class="entry-review" role="region" aria-label="Xem lại phiếu thu trước khi ghi" hidden></div></div>`;
  const paintImages = () => { if (drawer?.firstChild) $('.entry-images').innerHTML = ctx.imageEntryBox?.(KEY) ?? ''; };
  function showStep(next) {
    step = next;
    $('.entry-form').hidden = next !== 'form';
    $('.entry-review').hidden = next !== 'review';
  }
  function open() {
    if (!drawer || !active()) return;
    if (!drawer.firstChild) drawer.innerHTML = formHtml();
    $('.entry-customer').textContent = live.customerName(customerId) ?? '';
    drawer.hidden = false;
    paintImages();
    showStep(step);
    (step === 'review' ? $('.receipt-save') : $(`.${$('.receipt-date').value ? 'receipt-amount' : 'receipt-date'}`)).focus();
  }
  function close() {
    if (!isOpen()) return;
    drawer.hidden = true;
    if (step === 'review') { review = null; showStep('form'); }
    root.querySelector('.entry-open')?.focus();
  }
  // Khung về trống cho phiếu sau; hình thức về THU TIỀN (sự kiện change để ô chọn sổ cấn trừ tự ẩn).
  function resetForm() {
    for (const box of drawer.querySelectorAll('.receipt-date,.receipt-amount,.receipt-reference')) box.value = '';
    for (const box of drawer.querySelectorAll('.cell-error')) box.textContent = '';
    const method = $('.receipt-method');
    if (method.value !== methods[0]) { method.value = methods[0]; method.dispatchEvent(new Event('change', { bubbles: true })); }
    review = null;
    showStep('form');
  }
  function fieldError(field, text) {
    $(`.${field}-error`).textContent = text;
    $(`.${field}`).focus();
  }

  // Bước 1 → bước xem lại: kiểm ngày, số tiền; chưa gửi lệnh nào.
  async function next() {
    const form = $('.entry-form');
    for (const box of form.querySelectorAll('.cell-error')) box.textContent = '';
    const method = $('.receipt-method').value;
    // CẤN TRỪ: phần cấn trừ kiểm và mở hộp xác nhận của nó; "Ngoài sổ" thì đi tiếp như phiếu thường.
    if (method === 'CẤN TRỪ' && await ctx.startOffset(form)) return;
    let date, amount;
    try { date = model.parseCellEdit('event_date', $('.receipt-date').value, null); }
    catch { fieldError('receipt-date', 'Ngày trả phải dạng dd/mm/yyyy.'); return; }
    if (date > ctx.todayIso()) { fieldError('receipt-date', 'Ngày trả không được sau hôm nay.'); return; }
    if (!$('.receipt-amount').value.trim()) { fieldError('receipt-amount', 'Nhập số tiền khách trả.'); return; }
    try { amount = moneyText($('.receipt-amount').value); } catch (error) { fieldError('receipt-amount', error.message); return; }
    if (amount === '0') { fieldError('receipt-amount', 'Số tiền phải lớn hơn 0.'); return; }
    review = { date, method, amount, reference: referenceFields(form).reference ?? null };
    paintReview();
    showStep('review');
    $('.receipt-save').focus();
  }
  // Bước xem lại (H5): phiếu nằm ở tháng của ngày trả; tổng còn nợ trước → sau từ model; phân bổ từng tháng do server quyết định
  // nên chỉ hiện sau khi ghi. Tháng khóa vẫn ghi được phiếu (ghi phiếu không xét ổ khóa).
  function paintReview() {
    const data = ctx.snapshot;
    const plan = model.planReceiptPreview(data.total_outstanding_vnd, review.amount);
    const key = monthKey(review.date);
    const lock = (data.month_locks ?? []).find(row => monthKey(row.month) === key);
    const locked = lock ? lock.locked : key !== (monthKey(data.today_month) || liveOpenMonth);
    const images = drawer.querySelectorAll('.entry-images .image-thumb').length;
    $('.entry-review').innerHTML = `<p class="entry-sum">Ghi phiếu <b>${fmt(review.amount)} đ</b> · ${escape(review.method)} · ngày ${escape(dateText(review.date))}, nằm ở tháng ${monthLabel(key)}.</p>`
      + `<p>Tổng còn nợ: ${model.formatVnd(plan.beforeVnd)} đ → <b>${model.formatVnd(plan.afterVnd)} đ</b>.</p>`
      + (plan.creditVnd > 0n ? `<p class="entry-note">Sau phiếu này khách dư ${model.formatVnd(plan.creditVnd)} đ.</p>` : '')
      + (locked ? `<p class="entry-note">Tháng ${monthLabel(key)} đang khóa; phiếu vẫn ghi được.</p>` : '')
      + (review.reference ? `<p>Tham chiếu: ${escape(review.reference)}</p>` : '')
      + (images ? `<p>Kèm ${images} ảnh chứng từ.</p>` : '')
      + '<p class="entry-hint">Phần trừ nợ từng tháng hiện ngay sau khi ghi.</p><p class="cell-error entry-error" role="alert"></p>'
      + '<div class="entry-actions"><button type="button" class="entry-back">Sửa lại</button><button type="button" class="receipt-save">Ghi phiếu</button></div>';
  }

  async function save() {
    if (saving || !review) return;
    saving = true;
    const button = $('.receipt-save');
    button.disabled = true;
    const sent = review;
    try {
      const result = await submit('receipt', { date: sent.date, method: sent.method, amount_vnd: sent.amount,
        ...(sent.reference ? { reference: sent.reference } : {}) });
      await settle(sent, result);
    } finally {
      saving = false;
      if (button.isConnected) button.disabled = false;
    }
  }
  // Kết quả lệnh ghi: lưu được thì xong; ngày sau hôm nay về ô Ngày; sổ đổi thì xem lại số mới; mất mạng thì Thử lại cùng lệnh
  // (cùng khóa chống trùng, không ghi hai lần).
  async function settle(sent, result) {
    const outcome = api.lastOutcome();
    if (outcome?.status === 'saved') { await done(sent, outcome.result); return; }
    if (result?.error === 'FUTURE_RECEIPT_DATE') { review = null; showStep('form'); fieldError('receipt-date', result.message || 'Ngày trả không được sau hôm nay.'); return; }
    if (outcome?.status === 'stale') { paintReview(); $('.entry-error').textContent = 'Sổ vừa thay đổi. Xem lại số rồi bấm Ghi phiếu lần nữa.'; return; }
    const box = $('.entry-error');
    if (outcome?.status === 'unknown' || api.hasPending()) {
      box.innerHTML = 'Chưa rõ phiếu đã lưu chưa (mất kết nối). Bấm Thử lại: phiếu không bị ghi hai lần. <button type="button" class="entry-retry">Thử lại</button>';
      return;
    }
    box.textContent = result?.message || 'Không ghi được phiếu. Thử lại.';
  }
  async function done(sent, result) {
    const pid = result?.pid ?? null;
    const imageText = pid ? await ctx.afterReceiptSaved?.(KEY, pid) ?? '' : '';
    resetForm();
    drawer.hidden = true;
    lastSaved = { pid, date: sent.date, amount: sent.amount, duplicate: Boolean(result?.duplicate_reference), imageText };
    showNotice('');   // băng kết quả thay câu "Đã lưu."
    if (!ctx.showMonth(monthKey(sent.date))) paintStrip();
    const row = pid ? root.querySelector(`td.receipt[data-pid="${CSS.escape(pid)}"][data-field="date"]`)?.closest('tr') : null;
    if (row) {
      row.classList.add('just-saved');
      row.scrollIntoView({ block: 'center' });
      setTimeout(() => row.classList.remove('just-saved'), 3000);
    }
    root.querySelector('.entry-open')?.focus({ preventScroll: true });
  }

  // Băng kết quả ngay dưới đầu sổ: phần trừ nợ lấy từ phiếu trong sổ vừa tải (đúng số server); phiếu đã hủy thì băng tự tắt.
  function paintStrip() {
    root.querySelector('.saved-strip')?.remove();
    if (!lastSaved || typeof root.querySelector !== 'function') return;
    const receipt = (ctx.snapshot?.receipts ?? []).find(row => row.pid === lastSaved.pid);
    if (lastSaved.pid && (!receipt || receipt.voided_by_event != null)) { lastSaved = null; return; }
    const lines = (receipt?.allocations ?? []).filter(line => line.superseded_by_event == null);
    const debt = lines.filter(line => line.kind !== 'advance').map(line => `T${monthLabel(monthKey(line.month))} ${fmt(line.amount_vnd)}`);
    const advance = lines.filter(line => line.kind === 'advance').map(line => `ứng trước ${fmt(line.amount_vnd)}`);
    const text = [`Đã ghi phiếu${lastSaved.pid ? ` ${lastSaved.pid}` : ''}`, `${fmt(lastSaved.amount)} đ`, `ngày ${dateText(lastSaved.date)}`,
      ...(debt.length ? [`trừ nợ ${debt.join(' · ')}`] : []), ...advance].join(' · ')
      + (lastSaved.duplicate ? '. Tham chiếu trùng với phiếu khác trong sổ.' : '.') + (lastSaved.imageText ? ` ${lastSaved.imageText}` : '');
    root.querySelector('.book-bar')?.insertAdjacentHTML('afterend', `<div class="saved-strip" role="status"><span>${escape(text)}</span>`
      + (lastSaved.pid ? `<button type="button" class="saved-void" data-pid="${escape(lastSaved.pid)}">Hủy phiếu vừa ghi</button>` : '')
      + '<button type="button" class="saved-close">Đóng</button></div>');
  }
  // "Hủy phiếu vừa ghi" (H3): mở dòng hủy phiếu sẵn có (so-khach-v7-edit-ui.js, lý do bắt buộc) với lý do điền sẵn, sửa được.
  function voidJustSaved(pid) {
    const receipt = (ctx.snapshot?.receipts ?? []).find(row => row.pid === pid);
    if (!receipt) return;
    ctx.showMonth(monthKey(receipt.date));
    const cell = root.querySelector(`td.receipt[data-pid="${CSS.escape(pid)}"]:not([data-field])`);
    if (!cell) return;
    cell.scrollIntoView({ block: 'center' });
    cell.click();
    const reason = root.querySelector(`.void-prompt[data-pid="${CSS.escape(pid)}"] .void-reason`);
    if (reason) { reason.value = VOID_REASON; reason.select(); }
  }

  root.addEventListener('click', event => {
    if (event.target.closest('.entry-open')) { open(); return; }
    if (event.target.closest('.saved-close')) { lastSaved = null; paintStrip(); return; }
    const undo = event.target.closest('.saved-void');
    if (undo) voidJustSaved(undo.dataset.pid);
  });
  if (drawer) {
    drawer.addEventListener('click', async event => {
      const button = event.target.closest('button');
      if (!button || button.disabled) return;
      if (button.matches('.entry-close')) close();
      else if (button.matches('.entry-today')) { $('.receipt-date').value = dateText(ctx.todayIso()); $('.receipt-amount').focus(); }
      else if (button.matches('.entry-next')) await next();
      else if (button.matches('.entry-back')) { review = null; showStep('form'); $('.receipt-amount').focus(); }
      else if (button.matches('.receipt-save')) await save();
      else if (button.matches('.entry-retry')) {
        button.disabled = true;
        await api.retry();
        if (review) await settle(review, undefined);
      }
    });
    drawer.addEventListener('keydown', async event => {
      // Giữ phím Enter không tự bấm Ghi phiếu khi vừa sang bước xem lại.
      if (event.key === 'Enter' && event.repeat) { event.preventDefault(); return; }
      if (event.key === 'Escape') {
        if (drawer.querySelector('.offset-picker')) return;   // Esc đóng danh sách chọn sổ trước (offset-ui)
        event.preventDefault();
        if (step === 'review') { review = null; showStep('form'); $('.receipt-amount').focus(); } else close();
        return;
      }
      if (event.key !== 'Enter') return;
      if (event.target.matches('.receipt-date')) { event.preventDefault(); $('.receipt-amount').focus(); return; }
      if (event.target.matches('.receipt-amount,.receipt-reference')) { event.preventDefault(); await next(); }
    });
    drawer.addEventListener('input', event => {
      if (event.target.matches('.receipt-date') && event.target.value.length === 10) $('.receipt-amount').focus();
    });
  }

  const entryButton = on => `<button type="button" class="entry-open" ${on ? '' : 'disabled'}>Ghi phiếu thu</button>`;
  function entryAfterRender() { paintStrip(); paintImages(); }
  // Ảnh dán khi không đứng ở ô nhập nào: vào khung Ghi phiếu thu (mở khung nếu đang đóng); sổ chưa ghi được thì null.
  function entryImageKey() {
    if (!active() || !drawer) return null;
    if (!isOpen()) open();
    return KEY;
  }
  // Cấn trừ ghi xong (so-khach-v7-offset-ui.js): khung về trống và đóng.
  function afterOffsetSaved() {
    if (!drawer?.firstChild) return;
    resetForm();
    drawer.hidden = true;
  }
  Object.assign(ctx, { entryButton, entryAfterRender, entryImageKey, afterOffsetSaved });
};
