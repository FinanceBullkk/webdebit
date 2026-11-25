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
  let step = 'form';     // 'form' | 'review' | 'paste'
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
      <p class="entry-note entry-from" hidden></p>
      <label class="entry-field"><span>Ngày trả</span><span class="entry-date"><input class="receipt-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric" autocomplete="off"><button type="button" class="entry-today">Hôm nay</button></span></label>
      <span class="cell-error receipt-date-error" role="status"></span>
      <label class="entry-unknown"><input type="checkbox" class="receipt-unknown"> Không rõ ngày trả</label>
      <label class="entry-field entry-month" hidden><span>Tháng khách trả</span><select class="receipt-month" aria-label="Tháng khách trả"></select></label>
      <span class="entry-symbolic-hint" role="status"></span>
      <span class="cell-error receipt-month-error" role="status"></span>
      <label class="entry-field"><span>Hình thức</span><select class="receipt-method" aria-label="Hình thức">${methods.map(method => `<option>${escape(method)}</option>`).join('')}</select></label>
      <div class="offset-slot"></div>
      <label class="entry-field"><span>Số tiền (VND)</span><input class="receipt-amount" aria-label="Số tiền trả" inputmode="numeric" autocomplete="off"></label>
      <span class="entry-amount-hint" role="status"></span>
      <span class="cell-error receipt-amount-error" role="status"></span>
      <label class="entry-field"><span>Tham chiếu</span><input class="receipt-reference" aria-label="Tham chiếu" maxlength="500" placeholder="Tùy chọn" autocomplete="off"></label>
      <div class="entry-images"></div>
      <div class="entry-more"><button type="button" class="entry-split">Chia cho nhiều sổ…</button><button type="button" class="entry-paste-open">Dán nhiều phiếu…</button></div>
      <div class="entry-actions"><button type="button" class="entry-next">Xem lại</button></div>
    </div><div class="entry-review" role="region" aria-label="Xem lại phiếu thu trước khi ghi" hidden></div>
    <div class="entry-paste" role="region" aria-label="Dán nhiều phiếu thu" hidden>
      <p class="entry-hint">Chép từ Sheet các cột theo thứ tự <b>Ngày trả · Số tiền · Hình thức · Tham chiếu</b> (Hình thức để trống là THU TIỀN; hai cột sau không bắt buộc), rồi dán vào ô dưới. Mỗi dòng một phiếu của sổ này.</p>
      <textarea class="paste-receipts" aria-label="Bảng phiếu thu dán vào" rows="6" spellcheck="false"></textarea>
      <div class="paste-preview" role="status"></div>
      <p class="cell-error paste-error" role="alert"></p>
      <div class="entry-actions"><button type="button" class="paste-back">Quay lại</button><button type="button" class="paste-save" disabled>Ghi phiếu</button></div>
    </div></div>`;
  const paintImages = () => { if (drawer?.firstChild) $('.entry-images').innerHTML = ctx.imageEntryBox?.(KEY) ?? ''; };
  function showStep(next) {
    step = next;
    $('.entry-form').hidden = next !== 'form';
    $('.entry-review').hidden = next !== 'review';
    $('.entry-paste').hidden = next !== 'paste';
  }

  // PHIEU-WEB-01 mục 3: dán nhiều phiếu vào sổ này. Đọc bảng ở model (parseReceiptPaste), xem trước từng dòng và tổng còn nợ
  // trước → sau; còn dòng lỗi thì không ghi. Ghi bằng chuỗi lệnh của sổ (api.submitSeries, như dán cột giá): mỗi phiếu một lệnh
  // record_receipt, lệnh sau dùng phiên bản lệnh trước; lỗi thì dừng, các dòng chưa ghi ở lại trong ô; mất mạng thì Thử lại ở
  // khung (hay ở đầu sổ) gửi lại đúng lệnh đó (không ghi hai lần).
  let pasteBusy = false;
  // Xác nhận theo số dòng của bảng đang dán: số nghi nhầm đơn vị đã kiểm (`pasteOk`), dòng có thể đã ghi mà người vẫn muốn ghi
  // (`pasteDup`). Dán lại hay sửa ô thì xóa, hỏi lại từ đầu.
  const pasteOk = new Set(), pasteDup = new Set();
  // Tháng khóa như bước xem lại của phiếu đơn: theo ổ khóa của sổ, chưa có dòng khóa thì chỉ tháng hiện tại mở.
  const monthLocked = key => {
    const data = ctx.snapshot ?? {};
    const lock = (data.month_locks ?? []).find(row => monthKey(row.month) === key);
    return lock ? lock.locked : key !== (monthKey(data.today_month) || liveOpenMonth);
  };
  function pastePlan() {
    const plan = model.parseReceiptPaste($('.paste-receipts').value, ctx.todayIso(), { receipts: ctx.snapshot?.receipts ?? [], isLocked: monthLocked });
    // Dòng có thể đã ghi: mặc định không ghi (người bấm "Vẫn ghi" mới ghi). Số nghi nhầm đơn vị: phải bấm "Đúng số này".
    plan.send = plan.rows.filter(row => !row.duplicate || pasteDup.has(row.line));
    plan.unchecked = plan.send.filter(row => row.doubt && !pasteOk.has(row.line));
    return plan;
  }
  function pasteRow(row) {
    const marks = [
      row.duplicate ? `<label class="paste-flag"><input type="checkbox" class="paste-dup" data-line="${row.line}"${pasteDup.has(row.line) ? ' checked' : ''}> Vẫn ghi: ${row.duplicate.line
        ? `giống dòng ${row.duplicate.line} trong bảng này (cùng số tiền, tham chiếu, ngày gần nhau)`
        : `có thể đã ghi rồi (${escape(row.duplicate.pid ?? 'phiếu')} cùng số tiền, ngày ${escape(dateText(row.duplicate.date))})`}</label>` : '',
      row.doubt && (!row.duplicate || pasteDup.has(row.line)) ? `<label class="paste-flag"><input type="checkbox" class="paste-ok" data-line="${row.line}"${pasteOk.has(row.line) ? ' checked' : ''}> Đúng số này. ${escape(row.doubtText)}</label>` : '',
      row.locked ? '<small>Tháng đang khóa; phiếu vẫn ghi được.</small>' : '',
    ].filter(Boolean).join('');
    const skipped = row.duplicate && !pasteDup.has(row.line);
    // Ngày bằng chữ cạnh ngày số (review #676 lần 2): bảng ghi tháng/ngày mà cả hai phần ≤ 12 máy không nhận ra, người nhìn chữ thì thấy.
    const day = `${Number(row.date.slice(8))} tháng ${Number(row.date.slice(5, 7))}`;
    return `<li${skipped ? ' class="paste-skip"' : ''}>Dòng ${row.line}: ${escape(dateText(row.date))} <span class="paste-day">(${day})</span>${row.maybeSwapped ? ' <b class="paste-date-mark">(kiểm ngày/tháng)</b>' : ''} · <b>${fmt(row.amountVnd.toString())} đ</b> · ${escape(row.method)}${row.reference ? ` · ${escape(row.reference)}` : ''}${skipped ? ' · <b>không ghi</b>' : ''}${marks}</li>`;
  }
  function paintPaste() {
    const plan = pastePlan(), box = $('.paste-preview'), save = $('.paste-save');
    $('.paste-error').textContent = '';
    if (!$('.paste-receipts').value.trim()) { box.innerHTML = ''; save.disabled = true; save.textContent = 'Ghi phiếu'; return; }
    const total = plan.send.reduce((sum, row) => sum + row.amountVnd, 0n);
    const money = model.planReceiptPreview(ctx.snapshot.total_outstanding_vnd, total.toString());
    // Cảnh báo ngày chỉ hiện khi bảng có dấu hiệu tháng/ngày; không có thì bỏ dấu "(kiểm ngày/tháng)" ở từng dòng cho đỡ rối.
    const swapped = plan.warnings.some(text => text.includes('tháng/ngày'));
    for (const row of plan.rows) row.maybeSwapped &&= swapped;
    box.innerHTML = (plan.errors.length ? `<ul class="paste-errors">${plan.errors.map(text => `<li>${escape(text)}</li>`).join('')}</ul><p class="entry-note">Sửa các dòng lỗi trên Sheet rồi chép, dán lại. Còn dòng lỗi thì chưa ghi phiếu nào.</p>` : '')
      + plan.warnings.map(text => `<p class="entry-note paste-warn">${escape(text)}</p>`).join('')
      + (plan.rows.length ? `<p class="paste-sum">${plan.send.length} phiếu, tổng <b>${fmt(total.toString())} đ</b>. Tổng còn nợ: ${model.formatVnd(money.beforeVnd)} đ → <b>${model.formatVnd(money.afterVnd)} đ</b>.</p><ol class="paste-rows">${plan.rows.map(pasteRow).join('')}</ol>` : '')
      + (plan.unchecked.length ? `<p class="entry-note">Bấm "Đúng số này" ở dòng ${plan.unchecked.map(row => row.line).join(', ')} rồi mới ghi được.`
        + (plan.unchecked.length > 1 ? ' <button type="button" class="paste-ok-all">Đúng cả bảng</button>' : '') + '</p>' : '');
    // Khóa bản xem trước: lúc bấm Ghi, danh sách và sổ phải đúng như bản người đang nhìn (review #676 lần 2).
    pasteShown = { sig: pasteSig(plan), version: ctx.snapshot?.version ?? null };
    save.disabled = Boolean(plan.errors.length) || !plan.send.length || Boolean(plan.unchecked.length) || pasteBusy;
    save.textContent = plan.send.length ? `Ghi ${plan.send.length} phiếu` : 'Ghi phiếu';
  }
  let pasteShown = null;
  const pasteSig = plan => JSON.stringify(plan.send.map(row => [row.line, row.date, row.method, row.amountVnd.toString(), row.reference]));
  async function savePaste() {
    if (pasteBusy) return;
    const plan = pastePlan();
    if (plan.errors.length || !plan.send.length || plan.unchecked.length) return;
    if (!pasteShown || pasteShown.sig !== pasteSig(plan) || pasteShown.version !== (ctx.snapshot?.version ?? null)) {
      // Sổ hay bảng đổi sau bản xem trước: không ghi theo danh sách khác cái người đã đọc. Vẽ lại bản xem trước, người bấm lại.
      paintPaste();
      $('.paste-error').textContent = 'Sổ vừa thay đổi sau bản xem trước. Xem lại danh sách và số trước → sau rồi bấm Ghi lần nữa.';
      return;
    }
    if (api.hasPending()) { $('.paste-error').textContent = 'Còn thao tác khác chưa xong hoặc chưa rõ đã lưu. Xong việc đó (nút Thử lại ở đầu sổ) rồi bấm Ghi.'; return; }
    const lines = $('.paste-receipts').value.replace(/\r\n?/g, '\n').split('\n');
    pasteBusy = true;
    $('.paste-save').disabled = true;
    let outcome;
    try {
      outcome = await api.submitSeries('receipt', plan.send.map(row => ({ date: row.date, method: row.method, amount_vnd: row.amountVnd.toString(),
        ...(row.reference ? { reference: row.reference } : {}) })), 'phiếu');
    } catch (error) { $('.paste-error').textContent = error.message; $('.paste-save').disabled = false; return; }
    finally { pasteBusy = false; }
    pasteOk.clear(); pasteDup.clear();
    settlePaste(outcome, plan.send, lines);
  }
  // Kết quả chuỗi ghi: xong thì đóng khung; bị từ chối thì để lại dòng chưa ghi; chưa rõ thì xóa ô dán (chuỗi còn giữ ở sổ) và
  // cho Thử lại ngay trong khung: gửi lại đúng lệnh chưa rõ rồi ghi nốt các dòng sau, không ghi hai lần.
  function settlePaste(outcome, rows, lines) {
    if (outcome?.status === 'saved') {
      $('.paste-receipts').value = '';
      paintPaste();
      showStep('form');
      drawer.hidden = true;
      ctx.showMonth(monthKey(rows[rows.length - 1].date));
      root.querySelector('.entry-open')?.focus({ preventScroll: true });
      return;
    }
    if (outcome?.status === 'stopped') {
      // Dòng đã ghi rời khỏi ô; dòng lỗi và các dòng sau ở lại để sửa rồi ghi tiếp (không ghi lại dòng đã lưu).
      const failed = rows[outcome.done];
      $('.paste-receipts').value = lines ? rows.slice(outcome.done).map(row => lines[row.line - 1]).join('\n') : '';
      paintPaste();
      $('.paste-error').textContent = `Đã ghi ${outcome.done}/${outcome.total} phiếu. Dòng ${failed.line} (${dateText(failed.date)}, ${fmt(failed.amountVnd.toString())} đ) không ghi được: ${String(outcome.result?.message || 'máy chủ từ chối').replace(/\.$/, '')}.${lines ? ' Các dòng chưa ghi còn trong ô.' : ' Dán lại từ dòng này.'}`;
      $('.paste-receipts').focus();
      return;
    }
    pasteRetry = rows;
    $('.paste-receipts').value = '';
    paintPaste();
    $('.paste-error').innerHTML = `Đã ghi ${outcome?.done ?? 0}/${rows.length} phiếu; phiếu tiếp theo chưa rõ đã lưu (mất kết nối). Bấm Thử lại: máy ghi nốt các dòng còn lại, không ghi hai lần. Đừng dán lại. <button type="button" class="paste-retry">Thử lại</button>`;
    $('.paste-retry').focus();
  }
  let pasteRetry = null;   // các dòng của chuỗi chưa rõ, để báo kết quả sau Thử lại
  async function retryPaste() {
    if (!pasteRetry || pasteBusy) return;
    const rows = pasteRetry;
    pasteBusy = true;
    $('.paste-retry').disabled = true;
    try { await api.retry(); } catch (error) {
      // Thử lại lỗi (lệnh khác đang chạy, mất mạng nữa): giữ nút Thử lại, chuỗi vẫn chưa rõ.
      $('.paste-error').innerHTML = `${escape(error.message)} Phiếu tiếp theo vẫn chưa rõ đã lưu. <button type="button" class="paste-retry">Thử lại</button>`;
      return;
    } finally { pasteBusy = false; }
    if (api.lastOutcome()?.status === 'unknown') {
      $('.paste-error').innerHTML = 'Vẫn chưa rõ phiếu đã lưu chưa (mất kết nối). Bấm Thử lại lần nữa: phiếu không bị ghi hai lần. <button type="button" class="paste-retry">Thử lại</button>';
      $('.paste-retry').focus();
      return;
    }
    pasteRetry = null;
    settlePaste(api.lastOutcome(), rows, null);
  }
  async function open() {
    if (!drawer || !active()) return;
    // Phiếu chưa rõ đã có kết quả ở đầu sổ trong lúc khung đóng: xử lý trước (đã lưu thì hiện băng kết quả, không mở khung trống
    // rồi xóa mất phiếu người dùng gõ tiếp).
    if (own && api.pendingKey() !== own.key && await resolveOwn()) return;
    ctx.showTab('so');   // trang khách (TRANG-KHACH-01): khung thuộc thẻ Sổ, đang ở thẻ khác thì sang thẻ Sổ trước
    if (!drawer.firstChild) drawer.innerHTML = formHtml();
    $('.entry-customer').textContent = live.customerName(customerId) ?? '';
    drawer.hidden = false;
    paintImages();
    showStep(step);
    (step === 'review' ? $('.entry-review .entry-sum') : step === 'paste' ? $('.paste-receipts')
      : $(`.${$('.receipt-date').value || $('.receipt-unknown').checked ? 'receipt-amount' : 'receipt-date'}`)).focus();
  }
  // SK-C2: sang bước xem lại thì tiêu điểm vào câu tóm tắt, không vào nút Ghi phiếu: Enter, Enter theo thói quen Sheet không
  // ghi tiền khi người gõ chưa đọc dòng trước → sau. Muốn ghi phải Tab tới Ghi phiếu (hay bấm), rồi Enter.
  const focusReview = () => $('.entry-sum')?.focus();
  // Số đã hiểu có nhóm nghìn hiện ngay dưới ô khi gõ (SK-N10); chưa đọc được thì để trống, lỗi chỉ báo khi bấm Xem lại.
  const paintAmountHint = () => {
    const shown = model.readMoneyInput($('.receipt-amount').value);
    $('.entry-amount-hint').textContent = shown ? `Hiểu là ${shown} đ` : '';
  };
  // "Không rõ ngày trả": ô ngày tắt, hiện ô chọn tháng (12 tháng tới tháng hiện tại, chưa chọn sẵn để không ghi nhầm tháng) và
  // câu ngày sẽ ghi. Bỏ chọn thì về ô ngày như cũ.
  function paintUnknown() {
    const unknown = $('.receipt-unknown').checked, select = $('.receipt-month');
    $('.receipt-date').disabled = unknown;
    $('.entry-today').disabled = unknown;
    $('.entry-month').hidden = !unknown;
    if (unknown) {   // dựng lại mỗi lần đánh dấu: trang mở qua nửa đêm ngày 1 vẫn có tháng mới (review #671)
      const today = ctx.todayIso();
      let n = Number(today.slice(0, 4)) * 12 + Number(today.slice(5, 7)) - 1;
      const months = Array.from({ length: 12 }, () => { const key = `${Math.floor(n / 12)}-${String(n % 12 + 1).padStart(2, '0')}`; n -= 1; return key; });
      select.innerHTML = '<option value="">Chọn tháng…</option>' + months.map(key => `<option value="${key}">Tháng ${monthLabel(key)}</option>`).join('');
    }
    if (!unknown) select.value = '';
    $('.receipt-date-error').textContent = '';
    $('.receipt-month-error').textContent = '';
    paintSymbolicHint();
  }
  const paintSymbolicHint = () => {
    const month = $('.receipt-unknown').checked && $('.receipt-month').value;
    $('.entry-symbolic-hint').textContent = month ? `Ghi ngày ${dateText(CongNoFormat.symbolicDate(month, ctx.todayIso()))} (ngày tượng trưng).` : '';
  };
  function close() {
    if (!isOpen()) return;
    drawer.hidden = true;
    if (step === 'review' && !own) { review = null; showStep('form'); }   // phiếu chưa rõ: giữ bước xem lại của đúng phiếu đó
    root.querySelector('.entry-open')?.focus();
  }
  // Khung về trống cho phiếu sau; hình thức về THU TIỀN (sự kiện change để ô chọn sổ cấn trừ tự ẩn).
  function resetForm() {
    for (const box of drawer.querySelectorAll('.receipt-date,.receipt-amount,.receipt-reference')) box.value = '';
    for (const box of drawer.querySelectorAll('.cell-error,.entry-amount-hint')) box.textContent = '';
    $('.entry-from').hidden = true;
    $('.receipt-unknown').checked = false;
    paintUnknown();
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
    if (method === 'CẤN TRỪ' && $('.receipt-unknown').checked) { fieldError('receipt-month', 'Cấn trừ cần ngày cụ thể. Bỏ chọn "Không rõ ngày trả" rồi gõ ngày.'); return; }
    if (method === 'CẤN TRỪ' && await ctx.startOffset(form)) return;
    let date, amount;
    const unknown = $('.receipt-unknown').checked;
    if (unknown) {
      // PHIEU-WEB-01: không rõ ngày trả thì ngày tượng trưng của tháng khách trả (cuối tháng, không sau hôm nay), cùng luật máy Sheet.
      if (!$('.receipt-month').value) { fieldError('receipt-month', 'Chọn tháng khách trả.'); return; }
      date = CongNoFormat.symbolicDate($('.receipt-month').value, ctx.todayIso());
    } else {
      try { date = model.parseCellEdit('event_date', $('.receipt-date').value, null); }
      catch { fieldError('receipt-date', 'Ngày trả phải dạng dd/mm/yyyy.'); return; }
      if (date > ctx.todayIso()) { fieldError('receipt-date', 'Ngày trả không được sau hôm nay.'); return; }
    }
    if (!$('.receipt-amount').value.trim()) { fieldError('receipt-amount', 'Nhập số tiền khách trả.'); return; }
    try { amount = moneyText($('.receipt-amount').value); } catch { fieldError('receipt-amount', model.MONEY_INPUT_HELP); return; }
    if (amount === '0') { fieldError('receipt-amount', 'Số tiền phải lớn hơn 0.'); return; }
    const reference = referenceFields(form).reference ?? null;
    review = { date, method, amount, symbolic: unknown, reference: unknown ? CongNoFormat.symbolicReference(reference) : reference };
    paintReview();
    showStep('review');
    focusReview();
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
    $('.entry-review').innerHTML = `<p class="entry-sum" tabindex="-1">Ghi phiếu <b>${fmt(review.amount)} đ</b> · ${escape(review.method)} · ngày ${escape(dateText(review.date))}${review.symbolic ? ' (ngày tượng trưng)' : ''}, nằm ở tháng ${monthLabel(key)}.</p>`
      + (review.symbolic ? '<p class="entry-note">Không rõ ngày trả: ghi ngày cuối tháng (không sau hôm nay), tham chiếu có chữ "ngày tượng trưng". Biết ngày thật thì sửa ngày ở dòng phiếu.</p>' : '')
      + `<p>Tổng còn nợ: ${model.formatVnd(plan.beforeVnd)} đ → <b>${model.formatVnd(plan.afterVnd)} đ</b>.</p>`
      + (plan.creditVnd > 0n ? `<p class="entry-note">Sau phiếu này khách dư ${model.formatVnd(plan.creditVnd)} đ.</p>` : '')
      + (locked ? `<p class="entry-note">Tháng ${monthLabel(key)} đang khóa; phiếu vẫn ghi được.</p>` : '')
      + (review.reference ? `<p>Tham chiếu: ${escape(review.reference)}</p>` : '')
      + (images ? `<p>Kèm ${images} ảnh chứng từ.</p>` : '')
      // Cùng luật hỏi lại số nghi nhầm đơn vị với dán nhiều phiếu (receiptDoubt): phải bấm "Đúng số này" mới ghi.
      + (model.receiptDoubt(review.amount) ? `<label class="paste-flag entry-doubt"><input type="checkbox" class="entry-doubt-ok"${review.doubtOk ? ' checked' : ''}> Đúng số này. ${escape(model.receiptDoubtText(review.amount))}</label>` : '')
      + '<p class="entry-hint">Phần trừ nợ từng tháng hiện ngay sau khi ghi.</p><p class="cell-error entry-error" role="alert"></p>'
      + '<div class="entry-actions"><button type="button" class="entry-back">Sửa lại</button><button type="button" class="receipt-save">Ghi phiếu</button></div>';
  }

  // Phiếu của khung này "chưa rõ đã lưu" (mất mạng khi ghi): giữ khóa lệnh và nội dung phiếu đó. Khung chỉ cho Thử lại đúng
  // lệnh này; phiếu sửa lại hay phiếu mới không gửi khi lệnh còn chờ (gửi thì sổ từ chối, Thử lại sẽ ghi phiếu cũ mà báo phiếu
  // mới). Lệnh đã có kết quả ở chỗ khác (Thử lại ở đầu sổ) thì không gửi lại (khóa mới là hai phiếu): đóng khung, báo kiểm danh sách.
  let own = null;   // { key, sent }
  let retrying = false;
  const ownWaiting = 'Phiếu vừa gửi chưa rõ đã lưu chưa. Bấm Thử lại (phiếu không bị ghi hai lần) trước khi sửa hay ghi phiếu khác. <button type="button" class="entry-retry">Thử lại</button>';
  // Phiếu chưa rõ đã có kết quả ở chỗ khác (Thử lại ở đầu sổ): hỏi đúng kết quả của khóa lệnh đó. Đã lưu thì như ghi xong (ảnh
  // nháp đính vào đúng phiếu đó, băng kết quả); bị từ chối thì nói rõ, giữ phiếu để xem lại rồi ghi lại. Không gửi lại tự động.
  async function resolveOwn() {
    // Lệnh khác đang chạy hay chưa rõ: chưa xử lý (đính ảnh nháp vào phiếu lúc này sẽ bị từ chối mà nháp đã xóa).
    if (api.hasPending()) { $('.entry-error').textContent = 'Đang có thao tác khác chưa xong. Chờ xong (hay bấm Thử lại ở đầu sổ) rồi bấm lại.'; return false; }
    const result = api.outcomeOf(own.key), sent = own.sent;
    own = null;
    if (result?.status === 'saved') { await done(sent, result.result); return true; }
    if (!result) {
      // Không còn biết kết quả: xóa phiếu khỏi khung để không gửi lại bằng một cú bấm (gửi lại là khóa mới, có thể thành hai phiếu).
      resetForm();
      $('.receipt-date-error').textContent = 'Chưa biết kết quả phiếu vừa gửi. Kiểm tra danh sách phiếu thu; chưa có thì nhập lại.';
      return false;
    }
    if (result.status === 'stale') paintReview();
    $('.entry-error').textContent = result.status === 'stale' ? 'Phiếu vừa gửi không ghi được vì sổ vừa thay đổi. Xem lại số rồi bấm Ghi phiếu.'
      : `Phiếu vừa gửi không ghi được: ${result.result?.message || 'server từ chối'}. Xem lại rồi bấm Ghi phiếu.`;
    return false;
  }
  async function save() {
    if (saving || !review) return;
    if (own) {
      if (api.pendingKey() !== own.key) await resolveOwn();
      else $('.entry-error').innerHTML = ownWaiting;
      return;
    }
    // Số nghi nhầm đơn vị (receiptDoubt, cùng luật dán nhiều phiếu): phải bấm "Đúng số này" mới gửi. Xác nhận giữ trong phiếu đang
    // xem lại, sổ đổi rồi vẽ lại bước xem lại thì không phải bấm lại.
    if (model.receiptDoubt(review.amount) && !review.doubtOk) {
      $('.entry-error').textContent = 'Số tiền nằm ngoài khoảng thường gặp. Kiểm lại rồi bấm "Đúng số này" trước khi ghi.';
      $('.entry-doubt-ok')?.focus();
      return;
    }
    // Còn lệnh khác chưa rõ kết quả (hay chuỗi giá đang ghi): không gửi phiếu. Gửi thì sổ từ chối, mà khung này lại tưởng
    // phiếu là lệnh "chưa rõ" và Thử lại ở đây sẽ chạy tiếp lệnh kia rồi báo đã ghi phiếu.
    if (api.hasPending()) {
      $('.entry-error').textContent = 'Còn thao tác khác chưa xong hoặc chưa rõ đã lưu. Xong việc đó (nút Thử lại ở đầu sổ) rồi bấm Ghi phiếu.';
      return;
    }
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
    // Có kết quả dứt khoát mà không lưu (bị từ chối): phiếu này không còn "chưa rõ", lần Ghi phiếu sau là phiếu mới.
    if (outcome?.status !== 'unknown' && !api.hasPending()) own = null;
    result ??= outcome?.result;
    if (result?.error === 'FUTURE_RECEIPT_DATE') { review = null; showStep('form'); fieldError('receipt-date', result.message || 'Ngày trả không được sau hôm nay.'); return; }
    if (outcome?.status === 'stale') { paintReview(); $('.entry-error').textContent = 'Sổ vừa thay đổi. Xem lại số rồi bấm Ghi phiếu lần nữa.'; return; }
    const box = $('.entry-error');
    if (outcome?.status === 'unknown' || api.hasPending()) {
      const key = api.pendingKey();
      own = key ? { key, sent } : null;
      box.innerHTML = 'Chưa rõ phiếu đã lưu chưa (mất kết nối). Bấm Thử lại: phiếu không bị ghi hai lần. <button type="button" class="entry-retry">Thử lại</button>';
      return;
    }
    box.textContent = result?.message || 'Không ghi được phiếu. Thử lại.';
  }
  async function done(sent, result) {
    own = null;
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
      else if (button.matches('.entry-paste-open')) { showStep('paste'); paintPaste(); $('.paste-receipts').focus(); }
      else if (button.matches('.paste-back')) { showStep('form'); $('.entry-paste-open').focus(); }
      else if (button.matches('.paste-save')) await savePaste();
      else if (button.matches('.paste-ok-all')) { for (const row of pastePlan().unchecked) pasteOk.add(row.line); paintPaste(); $('.paste-save').focus(); }
      else if (button.matches('.paste-retry')) await retryPaste();
      else if (button.matches('.entry-split')) {
        // PHIEU-WEB-01 mục 2: một lần chuyển cho nhiều sổ mở khung riêng, mang theo chữ đang gõ; khung này về trống và đóng.
        // Phiếu chưa rõ đã lưu thì xử lý trước, như nút Sửa lại.
        if (own) { if (api.pendingKey() !== own.key) await resolveOwn(); else $('.entry-error').innerHTML = ownWaiting; return; }
        const seed = { date: $('.receipt-unknown').checked ? '' : $('.receipt-date').value.trim(), method: $('.receipt-method').value,
          amount: $('.receipt-amount').value.trim(), reference: $('.receipt-reference').value.trim() };
        resetForm();
        drawer.hidden = true;
        ctx.openSplit(seed);
      }
      else if (button.matches('.entry-back')) {
        // Phiếu chưa rõ: không cho sửa (sửa rồi Thử lại sẽ lẫn ảnh và số của hai phiếu); có kết quả rồi thì xử lý kết quả trước.
        if (own) { if (api.pendingKey() !== own.key) await resolveOwn(); else $('.entry-error').innerHTML = ownWaiting; return; }
        review = null; showStep('form'); $('.receipt-amount').focus();
      }
      else if (button.matches('.receipt-save')) await save();
      else if (button.matches('.entry-retry')) {
        // Lệnh đang chờ không còn là phiếu của khung (đã xong ở đầu sổ, hay là lệnh khác): không chạy lệnh đó từ đây.
        if (!own || retrying) return;
        if (api.pendingKey() !== own.key) { await resolveOwn(); return; }
        retrying = true;
        const sent = own.sent;
        for (const node of drawer.querySelectorAll('.entry-retry')) node.disabled = true;
        try { await api.retry(); await settle(sent, undefined); } finally { retrying = false; }
      }
    });
    drawer.addEventListener('keydown', async event => {
      // Giữ phím Enter không tự bấm Ghi phiếu khi vừa sang bước xem lại.
      if (event.key === 'Enter' && event.repeat) { event.preventDefault(); return; }
      if (event.key === 'Escape') {
        if (drawer.querySelector('.offset-picker')) return;   // Esc đóng danh sách chọn sổ trước (offset-ui)
        event.preventDefault();
        if (step === 'review' && own) {   // như nút Sửa lại: phiếu chưa rõ không về bước nhập
          if (api.pendingKey() !== own.key) await resolveOwn(); else $('.entry-error').innerHTML = ownWaiting;
          return;
        }
        if (step === 'review') { review = null; showStep('form'); $('.receipt-amount').focus(); }
        else if (step === 'paste') { showStep('form'); $('.entry-paste-open').focus(); }
        else close();
        return;
      }
      if (event.key !== 'Enter') return;
      if (event.target.matches('.receipt-date')) { event.preventDefault(); $('.receipt-amount').focus(); return; }
      if (event.target.matches('.receipt-amount,.receipt-reference')) { event.preventDefault(); await next(); }
    });
    drawer.addEventListener('input', event => {
      // Sửa ô thì lỗi cũ của ô đó tắt ngay (không đợi lần Xem lại sau); số tiền hiện số đã hiểu có nhóm nghìn.
      if (event.target.matches('.paste-receipts')) { pasteOk.clear(); pasteDup.clear(); paintPaste(); return; }
      if (event.target.matches('.entry-doubt-ok') && review) { review.doubtOk = event.target.checked; $('.entry-error').textContent = ''; return; }
      if (event.target.matches('.paste-ok,.paste-dup')) {
        const set = event.target.matches('.paste-ok') ? pasteOk : pasteDup, line = Number(event.target.dataset.line);
        if (event.target.checked) set.add(line); else set.delete(line);
        paintPaste();
        drawer.querySelector(`.${event.target.className}[data-line="${line}"]`)?.focus();
        return;
      }
      if (event.target.matches('.receipt-date')) $('.receipt-date-error').textContent = '';
      if (event.target.matches('.receipt-amount')) { $('.receipt-amount-error').textContent = ''; paintAmountHint(); }
      if (event.target.matches('.receipt-date') && event.target.value.length === 10) $('.receipt-amount').focus();
    });
    drawer.addEventListener('change', event => {
      if (event.target.matches('.receipt-unknown')) { paintUnknown(); (event.target.checked ? $('.receipt-month') : $('.receipt-date')).focus(); }
      if (event.target.matches('.receipt-month')) { $('.receipt-month-error').textContent = ''; paintSymbolicHint(); }
    });
    // Rời ô Số tiền: số đọc được thì ghi lại có nhóm nghìn (cùng số, dễ soát thừa thiếu số 0); chưa đọc được thì giữ nguyên chữ gõ.
    drawer.addEventListener('focusout', event => {
      if (!event.target.matches('.receipt-amount')) return;
      const shown = model.readMoneyInput(event.target.value);
      if (shown) event.target.value = shown;
      paintAmountHint();
    });
  }

  const entryButton = on => `<button type="button" class="entry-open" ${on ? '' : 'disabled'}>+ Ghi phiếu thu</button>`;
  // PHIEU-WEB-01 mục 4: trang Thu chi mở sổ với ?ghi-phieu=1 và để phiếu nháp (ngày, số tiền, tham chiếu đọc từ tin/ảnh) trong
  // sessionStorage. Lần vẽ đầu: đúng sổ, nháp còn mới (dưới 15 phút) thì mở khung và điền sẵn; người xem lại rồi tự bấm ghi.
  // Nháp dùng một lần; ngày sau hôm nay thì không điền ngày.
  let fromThuChi = typeof location !== 'undefined' && new URLSearchParams(location.search).get('ghi-phieu') === '1';
  function takeDraft() {
    let draft;
    try { draft = JSON.parse(sessionStorage.getItem('webdebit:phieu-nhap') ?? 'null'); sessionStorage.removeItem('webdebit:phieu-nhap'); } catch { draft = null; }
    try { const url = new URL(location.href); url.searchParams.delete('ghi-phieu'); history.replaceState(history.state, '', url); } catch { /* giữ địa chỉ */ }
    if (!draft || String(draft.customerId) !== String(customerId) || !(Date.now() - draft.at < 15 * 60 * 1000)) return null;
    return draft;
  }
  async function openFromThuChi() {
    fromThuChi = false;
    const draft = takeDraft();
    if (!draft || !active() || isOpen()) return;
    await open();
    if (step !== 'form' || own) return;
    resetForm();
    if (/^\d{4}-\d\d-\d\d$/.test(draft.date ?? '') && draft.date <= ctx.todayIso()) $('.receipt-date').value = dateText(draft.date);
    if (/^[1-9][0-9]*$/.test(draft.amount ?? '')) $('.receipt-amount').value = fmt(draft.amount);
    $('.receipt-reference').value = String(draft.reference ?? '').slice(0, 500);
    paintAmountHint();
    const note = $('.entry-from');
    note.textContent = 'Điền sẵn từ Thu chi (tin, ảnh Zalo). Kiểm ngày và số tiền với chứng từ rồi bấm Xem lại.';
    note.hidden = false;
    $('.receipt-amount').focus();
  }
  function entryAfterRender() { paintStrip(); paintImages(); if (fromThuChi) openFromThuChi(); }
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
