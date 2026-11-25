/* Sổ khách V7 bản live — Một lần chuyển cho nhiều sổ (PHIEU-WEB-01 mục 2). Khung riêng cùng mẫu khung Ghi phiếu thu (ngoài #app),
 * mở từ nút "Một lần chuyển cho nhiều sổ…" của khung đó. Người nhập tổng tiền chuyển, ngày, hình thức, tham chiếu, rồi chia cho
 * các sổ: sổ đang mở đứng đầu, thêm sổ bằng ô tìm. Tổng các phần phải đúng bằng tổng chuyển (model.planReceiptSplit).
 * Mỗi phần là một phiếu riêng ở sổ đó: một lệnh record_receipt mỗi sổ, khóa chống trùng riêng đặt lúc xem lại, gửi lần lượt.
 * Không có giao dịch chung nhiều sổ: lệnh lỗi giữa chừng thì dừng, báo phần đã ghi và phần chưa; "Ghi tiếp" gửi lại đúng các
 * khóa cũ nên phần đã lưu không thành hai phiếu. Tham chiếu đã dùng ở sổ khác trong tháng (Bảng thu) chỉ cảnh báo. Tiền tính ở
 * model (ARCH-03). Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).split = ctx => {
  'use strict';
  const { root, model, api, live, customerId, escape, dateText, monthLabel, methods, showNotice } = ctx;
  const F = CongNoFormat;
  const METHODS = methods.filter(method => method !== 'CẤN TRỪ');
  let step = 'form';   // 'form' | 'review' | 'result'
  let parts = [];      // [{ customerId, label, amountText }]
  let books = null;    // sổ đang hoạt động để chọn: [{ customerId, label, key }]
  let picking = false;
  let review = null;   // { date, method, reference, parts: [{ customerId, label, amountVnd, version, beforeVnd, key, status, pid, message }], warn }
  let saving = false;
  const drawer = typeof document.createElement === 'function' ? document.createElement('aside') : null;
  if (drawer) {
    drawer.className = 'split-drawer';
    drawer.hidden = true;
    drawer.setAttribute('aria-label', 'Một lần chuyển cho nhiều sổ');
    document.body.append(drawer);
  }
  const $ = selector => drawer.querySelector(selector);
  const isOpen = () => Boolean(drawer && !drawer.hidden);
  ctx.busyChecks.push(isOpen);
  const ownName = () => live.customerName(customerId) ?? `Sổ ${customerId}`;
  const money = value => model.formatVnd(value);

  const formHtml = () => `<header><h2>Một lần chuyển cho nhiều sổ<small>Mỗi sổ một phiếu, cùng ngày và tham chiếu</small></h2><button type="button" class="split-close">Đóng</button></header>
    <div class="entry-body"><div class="entry-form split-form">
      <label class="entry-field"><span>Ngày trả</span><span class="entry-date"><input class="split-date" aria-label="Ngày trả" placeholder="dd/mm/yyyy" inputmode="numeric" autocomplete="off"><button type="button" class="split-today">Hôm nay</button></span></label>
      <span class="cell-error split-date-error" role="status"></span>
      <label class="entry-field"><span>Hình thức</span><select class="split-method" aria-label="Hình thức">${METHODS.map(method => `<option>${escape(method)}</option>`).join('')}</select></label>
      <label class="entry-field"><span>Tổng tiền khách chuyển (VND)</span><input class="split-total receipt-amount" aria-label="Tổng tiền khách chuyển" inputmode="numeric" autocomplete="off"></label>
      <span class="cell-error split-total-error" role="status"></span>
      <label class="entry-field"><span>Tham chiếu</span><input class="split-reference" aria-label="Tham chiếu" maxlength="500" placeholder="Tùy chọn" autocomplete="off"></label>
      <div class="split-parts" role="group" aria-label="Chia cho các sổ"></div>
      <p class="split-progress" role="status"></p>
      <span class="cell-error split-error" role="alert"></span>
      <div class="entry-actions"><button type="button" class="split-next entry-next">Xem lại</button></div>
    </div><div class="entry-review split-review" role="region" aria-label="Xem lại các phiếu trước khi ghi" hidden></div></div>`;

  function showStep(next) {
    step = next;
    $('.split-form').hidden = next !== 'form';
    $('.split-review').hidden = next === 'form';
  }
  // Danh sách phần: sổ đang mở đứng đầu, không bỏ được; sổ khác có nút Bỏ. Ô tìm sổ mở dưới danh sách khi bấm "+ Thêm sổ".
  function paintParts() {
    const rows = parts.map((part, index) => `<div class="split-row" data-index="${index}"><label class="entry-field"><span>${escape(part.label)}</span>`
      + `<input class="split-amount receipt-amount" data-index="${index}" aria-label="Số tiền cho sổ ${escape(part.label)}" inputmode="numeric" autocomplete="off" value="${escape(part.amountText)}"></label>`
      + (index ? `<button type="button" class="split-remove" data-index="${index}" aria-label="Bỏ sổ ${escape(part.label)}">Bỏ</button>` : '')
      + `<span class="cell-error split-part-error" data-index="${index}" role="status"></span></div>`).join('');
    const picker = picking ? `<div class="split-picker"><input class="split-search" aria-label="Tìm sổ theo tên khách" placeholder="Gõ tên khách để tìm…" autocomplete="off"><div class="split-options" role="listbox" aria-label="Chọn sổ"></div></div>` : '';
    $('.split-parts').innerHTML = `<div class="split-caption">Chia cho các sổ</div>${rows}${picker}<button type="button" class="split-add">+ Thêm sổ</button>`;
    if (picking) paintOptions();
    paintProgress();
  }
  function paintOptions() {
    const holder = $('.split-options');
    if (!holder) return;
    if (!books) { holder.innerHTML = '<p class="offset-none">Đang tải danh sách sổ…</p>'; return; }
    const query = F.fold($('.split-search')?.value ?? '');
    const taken = new Set(parts.map(part => String(part.customerId)));
    const found = books.filter(book => !taken.has(String(book.customerId)) && (!query || book.key.includes(query))).slice(0, 8);
    holder.innerHTML = found.map(book => `<button type="button" role="option" class="offset-option split-option" data-customer="${escape(book.customerId)}"><span>${escape(book.label)}</span></button>`).join('')
      || '<p class="offset-none">Không tìm thấy sổ phù hợp</p>';
  }
  // Dòng dưới danh sách: đã chia bao nhiêu so với tổng chuyển, còn lệch bao nhiêu (đúng bằng thì báo khớp).
  function paintProgress() {
    const plan = model.planReceiptSplit($('.split-total').value, parts);
    const box = $('.split-progress');
    box.classList.toggle('split-even', plan.restVnd === 0n);
    box.textContent = plan.totalVnd === null ? `Đã chia ${money(plan.sumVnd)} đ.`
      : plan.restVnd === 0n ? `Đã chia đủ ${money(plan.sumVnd)} đ.`
        : `Đã chia ${money(plan.sumVnd)} / ${money(plan.totalVnd)} đ · ${plan.restVnd > 0n ? 'còn' : 'thừa'} ${money(plan.restVnd > 0n ? plan.restVnd : -plan.restVnd)} đ.`;
  }
  async function loadBooks() {
    if (books) return;
    try {
      const rows = ((await CongNoNet.customers()).customers ?? []).filter(row => row.status === 'active' && !row.archived);
      const labels = F.customerLabels(rows);
      books = rows.map(row => ({ customerId: row.id, label: labels.get(String(row.id)), key: F.fold(labels.get(String(row.id))) }))
        .sort((a, b) => a.label.localeCompare(b.label, 'vi'));
    } catch (error) { books = []; $('.split-error').textContent = CongNoNet.messageOf(error); }
    paintOptions();
  }

  // Lần chia dở lưu ở máy (localStorage) từ lúc gửi lệnh đầu tới khi mọi phần xong hay người bỏ: tải lại trang hay sang sổ khác
  // thì mở lại "Chia cho nhiều sổ…" là về đúng các khóa cũ. Trang không biết login (danh tính chỉ ở máy chủ, qua Tailscale), nên
  // lưu theo trình duyệt của máy đó. Trình duyệt chặn lưu thì vẫn còn trong bộ nhớ và câu hỏi khi rời trang.
  const STORE = 'webdebit:chia-do';
  function persist() {
    try {
      if (!review?.started || review.parts.every(done)) { localStorage.removeItem(STORE); return; }
      localStorage.setItem(STORE, JSON.stringify({ ...review, ask: false, totalVnd: review.totalVnd.toString(),
        parts: review.parts.map(({ fixText: _typing, ...part }) => ({ ...part, amountVnd: part.amountVnd.toString() })) }));
    } catch { /* không lưu được: còn bộ nhớ và beforeunload */ }
  }
  function forget() { try { localStorage.removeItem(STORE); } catch { /* không có gì để xóa */ } }
  function restore() {
    try {
      const data = JSON.parse(localStorage.getItem(STORE) ?? 'null');
      if (!Array.isArray(data?.parts) || !data.parts.length || !/^[0-9]+$/.test(String(data.totalVnd))) return null;
      return { ...data, totalVnd: BigInt(data.totalVnd), parts: data.parts.map(part => ({ ...part, amountVnd: BigInt(part.amountVnd),
        status: part.status === 'new' ? 'waiting' : part.status })) };
    } catch { return null; }
  }
  if (typeof addEventListener === 'function') {
    addEventListener('beforeunload', event => {
      if (!review?.started || review.parts.every(done)) return;
      event.preventDefault();
      event.returnValue = '';
    });
  }

  /** Mở khung; `seed` là chữ đang gõ ở khung Ghi phiếu thu (ngày, hình thức, số tiền, tham chiếu) để không gõ lại. */
  function openSplit(seed = {}) {
    if (!drawer || ctx.snapshot?.status !== 'active') return;
    // Lần chia dở (đã gửi ít nhất một lệnh): trong bộ nhớ, hoặc lưu ở máy khi trang vừa tải lại hay đang ở sổ khác. Mở lại đúng
    // bước kết quả với các khóa cũ, không bắt đầu lần chia mới (khóa mới sẽ ghi lần hai các sổ đã lưu).
    if (!review) { const kept = restore(); if (kept) { review = kept; step = 'result'; } }
    if (step === 'result' && review && !review.parts.every(done)) {
      if (!drawer.firstChild) drawer.innerHTML = formHtml();
      paintReview();
      showStep('result');
      drawer.hidden = false;
      $('.split-review button')?.focus();
      return;
    }
    drawer.innerHTML = formHtml();
    $('.split-date').value = seed.date ?? '';
    if (METHODS.includes(seed.method)) $('.split-method').value = seed.method;
    $('.split-total').value = seed.amount ?? '';
    $('.split-reference').value = seed.reference ?? '';
    parts = [{ customerId, label: ownName(), amountText: '' }];
    picking = false; review = null;
    paintParts();
    showStep('form');
    drawer.hidden = false;
    $(`.${seed.date ? 'split-total' : 'split-date'}`).focus();
  }
  function close() {
    if (!isOpen() || saving) return;
    drawer.hidden = true;
    root.querySelector('.entry-open')?.focus();
  }
  function readParts() {
    for (const input of drawer.querySelectorAll('.split-amount')) parts[Number(input.dataset.index)].amountText = input.value;
  }
  // Chữ đang gõ ở ô sửa số tiền của bước kết quả: giữ qua lần vẽ lại.
  function readFixes() {
    for (const input of drawer.querySelectorAll('.split-fix')) review.parts[Number(input.dataset.index)].fixText = input.value;
  }
  function clearErrors() { for (const box of drawer.querySelectorAll('.cell-error')) box.textContent = ''; }

  // Bước nhập → xem lại: kiểm ngày, tổng, từng phần; đọc phiên bản và tổng nợ của từng sổ; chưa gửi lệnh nào.
  async function next() {
    readParts();
    clearErrors();
    let date;
    try { date = model.parseCellEdit('event_date', $('.split-date').value, null); }
    catch { $('.split-date-error').textContent = 'Ngày trả phải dạng dd/mm/yyyy.'; $('.split-date').focus(); return; }
    if (date > ctx.todayIso()) { $('.split-date-error').textContent = 'Ngày trả không được sau hôm nay.'; $('.split-date').focus(); return; }
    const plan = model.planReceiptSplit($('.split-total').value, parts);
    if (!plan.ok) {
      if (plan.code.startsWith('TOTAL')) { $('.split-total-error').textContent = plan.message; $('.split-total').focus(); return; }
      if (plan.index !== null) {
        drawer.querySelector(`.split-part-error[data-index="${plan.index}"]`).textContent = plan.message;
        drawer.querySelector(`.split-amount[data-index="${plan.index}"]`).focus();
        return;
      }
      $('.split-error').textContent = plan.message;
      (plan.code === 'TOO_FEW' ? $('.split-add') : $('.split-total')).focus();
      return;
    }
    const button = $('.split-next');
    button.disabled = true;
    try {
      const ledgers = await Promise.all(plan.parts.map(part => String(part.customerId) === String(customerId) ? ctx.snapshot : api.readOther(part.customerId)));
      const closed = ledgers.findIndex(data => data?.status !== 'active');
      if (closed >= 0) { $('.split-error').textContent = `Sổ ${parts[closed].label} chưa có số dư đầu, chưa ghi phiếu được.`; return; }
      const reference = $('.split-reference').value.trim() || null;
      const used = await usedElsewhere(reference, date);
      // Sổ trong lần chia đã có phiếu chưa hủy cùng tham chiếu và cùng số tiền (Bảng thu của tháng): phần đó mặc định không ghi,
      // người bấm "Vẫn ghi" mới ghi (review #675 lần 2: lần chia trước bị mất trạng thái rồi nhập lại).
      const same = part => used.rows.find(row => String(row.customer_id) === String(part.customerId) && String(row.amount_vnd) === part.amountVnd.toString());
      review = { date, method: $('.split-method').value, reference, warn: used.warn, totalVnd: plan.totalVnd, ask: false, started: false,
        parts: plan.parts.map((part, index) => {
          const dup = same(part);
          return { customerId: part.customerId, label: parts[index].label, amountVnd: part.amountVnd, version: ledgers[index].version,
            beforeVnd: ledgers[index].total_outstanding_vnd, key: crypto.randomUUID(), status: 'new',
            ...(dup ? { dup: { pid: dup.pid ?? null, date: dup.date ?? null }, skip: true } : {}) };
        }) };
    } catch (error) { $('.split-error').textContent = CongNoNet.messageOf(error); return; }
    finally { button.disabled = false; }
    paintReview();
    showStep('review');
    $('.entry-sum').focus();
  }
  // Tham chiếu đã có ở phiếu web khác trong tháng của ngày trả (Bảng thu gom mọi sổ): chỉ cảnh báo, không chặn — cùng một lần
  // chuyển ghi lại là nhầm, nhưng hai lần chuyển cùng chữ "CK" là thường. Không đọc được Bảng thu thì nói rõ là chưa kiểm.
  async function usedElsewhere(reference, date) {
    const none = { warn: '', rows: [] };
    if (!reference) return none;
    const key = F.fold(F.receiptNote(reference).text);
    if (!key) return none;
    let book;
    try { book = await CongNoNet.fetchJson(`/api/v7/receipt-book?month=${date.slice(0, 7)}-01`, { what: 'phiếu thu trong tháng' }); }
    catch { return { warn: 'Chưa kiểm được tham chiếu này ở sổ khác (không đọc được Bảng thu).', rows: [] }; }
    const rows = [...(book?.days ?? []).flatMap(day => day.rows ?? []), ...(book?.undated ?? [])]
      .filter(row => row.source === 'web' && F.fold(row.note ?? '') === key);
    if (!rows.length) return none;
    const one = row => `sổ ${escape(row.name)} (${escape(row.pid ?? '')}, ${F.full(row.amount_vnd)}${row.date ? `, ngày ${escape(dateText(row.date))}` : ''})`;
    return { rows, warn: `Tham chiếu này đã có ở ${rows.slice(0, 3).map(one).join('; ')}${rows.length > 3 ? ` và ${rows.length - 3} phiếu khác` : ''}. Kiểm lại có phải cùng một lần chuyển đã ghi rồi không.` };
  }
  const STATUS = { saved: 'Đã ghi', new: '', error: 'Không ghi được', unknown: 'Chưa rõ đã lưu', stale: 'Sổ vừa thay đổi', waiting: 'Chưa ghi' };
  // Phần xong: đã ghi, hoặc người để "không ghi" vì sổ đó đã có phiếu cùng tham chiếu và số tiền.
  const done = part => part.status === 'saved' || Boolean(part.skip);
  function paintReview() {
    const writing = review.parts.filter(part => !part.skip);
    const total = writing.reduce((sum, part) => sum + part.amountVnd, 0n);
    const count = writing.length;
    const lines = review.parts.map((part, index) => {
      const plan = model.planReceiptPreview(part.beforeVnd, part.amountVnd.toString());
      const status = part.skip && part.status !== 'saved' ? ' <b class="split-status split-st-skip">Không ghi</b>'
        : STATUS[part.status] ? ` <b class="split-status split-st-${part.status}">${STATUS[part.status]}${part.pid ? ` ${escape(part.pid)}` : ''}</b>` : '';
      const dup = part.dup && part.status !== 'saved'
        ? `<label class="paste-flag"><input type="checkbox" class="split-dup" data-index="${index}"${part.skip ? '' : ' checked'}${part.status === 'unknown' ? ' disabled' : ''}> Vẫn ghi: sổ này đã có ${escape(part.dup.pid ?? 'phiếu')} cùng tham chiếu và số tiền${part.dup.date ? `, ngày ${escape(dateText(part.dup.date))}` : ''}</label>` : '';
      const amount = step === 'result' && fixable(part)
        ? `<input class="split-fix receipt-amount" data-index="${index}" aria-label="Số tiền cho sổ ${escape(part.label)}" inputmode="numeric" autocomplete="off" value="${escape(part.fixText ?? money(part.amountVnd))}"> đ`
        : `${money(part.amountVnd)} đ`;
      return `<li><strong>${escape(part.label)}</strong>: ${amount} · còn nợ ${money(plan.beforeVnd)} → <b>${money(plan.afterVnd)}</b> đ`
        + (plan.creditVnd > 0n ? ` (khách dư ${money(plan.creditVnd)} đ)` : '') + status
        + (part.message ? `<small class="cell-error">${escape(part.message)}</small>` : '') + dup + '</li>';
    }).join('');
    const left = review.parts.filter(part => !done(part)).length;
    const unknown = review.parts.some(part => part.status === 'unknown');
    const actions = step === 'result' && left && review.ask
      ? `<div class="lock-ask split-ask" role="group" aria-label="Đóng khi còn phiếu chưa ghi"><span>Còn ${left} phiếu chưa ghi. Đóng thì giữ nguyên: bấm lại "Chia cho nhiều sổ…" để ghi tiếp.</span>`
        + '<button type="button" class="split-stop">Đóng, ghi sau</button><button type="button" class="split-stay">Ở lại</button>'
        + (unknown ? '' : `<button type="button" class="split-drop">Bỏ ${left} phiếu chưa ghi</button>`) + '</div>'
      : step === 'result' && left
      ? `<div class="entry-actions"><button type="button" class="split-close">Đóng</button><button type="button" class="split-save receipt-save">Ghi tiếp ${left} phiếu</button></div>`
      : step === 'result' ? '<div class="entry-actions"><button type="button" class="split-close">Đóng</button></div>'
        : `<div class="entry-actions"><button type="button" class="split-back">Sửa lại</button><button type="button" class="split-save receipt-save">Ghi ${count} phiếu</button></div>`;
    $('.split-review').innerHTML = `<p class="entry-sum" tabindex="-1">Ghi <b>${count} phiếu</b>, tổng <b>${money(total)} đ</b> · ${escape(review.method)} · ngày ${escape(dateText(review.date))}, nằm ở tháng ${monthLabel(review.date.slice(0, 7))}.</p>`
      + `<ul class="split-lines">${lines}</ul>`
      + (review.reference ? `<p>Tham chiếu (cả ${count} phiếu): ${escape(review.reference)}</p>` : '')
      + (review.warn ? `<p class="entry-note">${review.warn}</p>` : '')
      + (review.reference ? '' : '<p class="entry-note">Chưa có tham chiếu. Nên ghi mã giao dịch ngân hàng cho lần chia nhiều sổ: sau này đối chiếu và nhận ra ghi trùng dễ hơn.</p>')
      + (step === 'result' && left ? `<p class="entry-note">Còn ${left} phiếu chưa ghi. Bấm Ghi tiếp: phiếu đã lưu không bị ghi lại.${review.parts.some(fixable) ? ' Phiếu bị từ chối hay chưa gửi sửa được số tiền; tổng các phần vẫn phải bằng tổng chuyển.' : ''}</p><p class="cell-error split-fix-error" role="alert"></p>` : '')
      + '<p class="entry-hint">Mỗi sổ một phiếu riêng, trừ nợ cũ trước ở sổ đó.</p>' + actions;
  }

  // Một lệnh ghi phiếu cho một sổ, bằng khóa đã đặt lúc xem lại (gửi lại không thành hai phiếu).
  async function post(part) {
    const body = { customer_id: part.customerId, expected_version: part.version, idempotency_key: part.key, date: review.date,
      method: review.method, amount_vnd: part.amountVnd.toString(), ...(review.reference ? { reference: review.reference } : {}) };
    let response, result;
    try {
      response = await fetch('/api/v7/receipts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      result = await response.json();
    } catch { return { status: 'unknown' }; }
    if (response.ok) return { status: 'saved', pid: result.pid ?? null };
    if (result?.error === 'STALE_LEDGER') return { status: 'stale' };
    if (result?.error === 'RESULT_UNKNOWN') return { status: 'unknown' };
    return { status: 'error', message: result?.message || 'Không ghi được phiếu.' };
  }
  // Phần sửa được ở bước kết quả: bị từ chối dứt khoát hay chưa gửi. Phần "chưa rõ đã lưu" thì không: phải gửi lại đúng lệnh cũ.
  const fixable = part => part.status === 'error' || part.status === 'waiting';
  // Số tiền sửa ở bước kết quả: tổng mọi phần (cả phần đã ghi) phải bằng tổng chuyển. Phần đổi số nhận khóa mới (lệnh khác,
  // phiếu khác); phần giữ số giữ khóa cũ. Trả câu lỗi, hoặc '' khi hợp lệ.
  function applyFixes() {
    const next = review.parts.map(part => {
      if (!fixable(part) || part.fixText == null) return part.amountVnd;
      try { const value = model.parseVnd(part.fixText); return value > 0n ? value : null; } catch { return null; }
    });
    const bad = next.findIndex(value => value === null);
    if (bad >= 0) return `Số tiền cho sổ ${review.parts[bad].label} không đọc được. ${model.MONEY_INPUT_HELP}`;
    const sum = next.reduce((total, value) => total + value, 0n);
    if (sum !== review.totalVnd) return `Tổng các phần ${money(sum)} đ khác tổng chuyển ${money(review.totalVnd)} đ.`;
    review.parts.forEach((part, index) => {
      if (next[index] !== part.amountVnd) Object.assign(part, { amountVnd: next[index], key: crypto.randomUUID(), status: 'waiting', message: '' });
      delete part.fixText;
    });
    return '';
  }
  async function save() {
    if (saving || !review) return;
    if (step === 'result') {
      readFixes();
      const problem = applyFixes();
      if (problem) { $('.split-fix-error').textContent = problem; return; }
    }
    if (api.hasPending()) { showNotice('Còn thao tác khác chưa rõ kết quả. Xong việc đó (nút Thử lại ở đầu sổ) rồi ghi.'); return; }
    if (!review.parts.some(part => !done(part))) return;
    saving = true;
    review.started = true;
    for (const button of drawer.querySelectorAll('.split-review button')) button.disabled = true;
    try {
      for (const part of review.parts) {
        if (done(part)) continue;
        // Trước khi gửi: lưu phần này là "chưa rõ" cùng khóa của nó, để trang tải lại giữa chừng vẫn gửi lại đúng lệnh này.
        const before = part.status;
        part.status = 'unknown';
        persist();
        part.status = before;
        let outcome = await post(part);
        // Sổ đổi từ lúc xem lại (người khác vừa ghi): đọc phiên bản mới rồi gửi lại một lần cùng khóa. Số tiền phiếu không đổi;
        // phần trừ nợ do server tính theo sổ lúc ghi.
        if (outcome.status === 'stale') {
          try { part.version = (await api.readOther(part.customerId)).version; outcome = await post(part); } catch { outcome = { status: 'unknown' }; }
        }
        Object.assign(part, { status: outcome.status, pid: outcome.pid ?? part.pid ?? null, message: outcome.message ?? '' });
        if (outcome.status !== 'saved') {
          if (outcome.status === 'unknown') part.message = 'Mất kết nối khi ghi. Bấm Ghi tiếp: phiếu không bị ghi hai lần.';
          for (const rest of review.parts) if (rest.status === 'new') rest.status = 'waiting';
          break;
        }
      }
    } finally { saving = false; persist(); }
    step = 'result';
    const saved = review.parts.filter(part => part.status === 'saved');
    if (saved.some(part => String(part.customerId) === String(customerId))) await api.read().catch(() => showNotice('Đã ghi; không tải được sổ mới. Tải lại trang để kiểm tra.'));
    if (review.parts.every(done)) {
      forget();
      drawer.hidden = true;
      showNotice(`Đã ghi ${saved.length} phiếu, tổng ${money(saved.reduce((sum, part) => sum + part.amountVnd, 0n))} đ: `
        + saved.map(part => `${part.label} ${part.pid ?? ''} ${money(part.amountVnd)} đ`.replace(/\s+/g, ' ')).join('; ') + '.');
      review = null; step = 'form';
      root.querySelector('.entry-open')?.focus({ preventScroll: true });
      return;
    }
    paintReview();
    $('.entry-sum').focus();
  }

  if (drawer) {
    drawer.addEventListener('click', async event => {
      const button = event.target.closest('button');
      if (!button || button.disabled) return;
      if (button.matches('.split-close')) {
        // Còn phiếu chưa ghi (bị từ chối, chưa gửi, chưa rõ đã lưu): hỏi trước, không bỏ lần chia dở. Bỏ rồi mở lại với khóa mới
        // sẽ ghi lần hai các sổ đã lưu.
        if (step === 'result' && review && !review.parts.every(done)) { readFixes(); review.ask = true; paintReview(); $('.split-stay').focus(); return; }
        if (step === 'result') { review = null; step = 'form'; }
        close();
      }
      else if (button.matches('.split-stop')) { readFixes(); review.ask = false; paintReview(); close(); }
      else if (button.matches('.split-stay')) { review.ask = false; paintReview(); $('.split-save').focus(); }
      else if (button.matches('.split-drop')) {
        // Chỉ khi không còn phiếu chưa rõ: phần bị từ chối hay chưa gửi chưa ghi gì ở sổ, bỏ không mất phiếu nào.
        if (review.parts.some(part => part.status === 'unknown')) return;
        const saved = review.parts.filter(part => part.status === 'saved');
        showNotice(`Đã bỏ phần chưa ghi của lần chia. Đã ghi ${saved.length} phiếu: ` + (saved.map(part => `${part.label} ${part.pid ?? ''}`.trim()).join('; ') || 'không có') + '.');
        forget();
        review = null; step = 'form'; close();
      }
      else if (button.matches('.split-today')) { $('.split-date').value = dateText(ctx.todayIso()); $('.split-total').focus(); }
      else if (button.matches('.split-add')) { readParts(); picking = true; paintParts(); $('.split-search').focus(); await loadBooks(); }
      else if (button.matches('.split-option')) {
        readParts();
        const book = books.find(item => String(item.customerId) === button.dataset.customer);
        if (book) parts.push({ customerId: book.customerId, label: book.label, amountText: '' });
        picking = false;
        paintParts();
        drawer.querySelector(`.split-amount[data-index="${parts.length - 1}"]`)?.focus();
      }
      else if (button.matches('.split-remove')) { readParts(); parts.splice(Number(button.dataset.index), 1); paintParts(); $('.split-add').focus(); }
      else if (button.matches('.split-next')) await next();
      else if (button.matches('.split-back')) { review = null; showStep('form'); $('.split-total').focus(); }
      else if (button.matches('.split-save')) await save();
    });
    drawer.addEventListener('input', event => {
      if (event.target.matches('.split-search')) { paintOptions(); return; }
      if (event.target.matches('.split-fix')) { readFixes(); $('.split-fix-error').textContent = ''; return; }
      if (event.target.matches('.split-dup')) {
        const part = review.parts[Number(event.target.dataset.index)];
        part.skip = !event.target.checked;
        readFixes();
        paintReview();
        drawer.querySelector(`.split-dup[data-index="${event.target.dataset.index}"]`)?.focus();
        persist();
        return;
      }
      if (event.target.matches('.split-amount')) { readParts(); event.target.closest('.split-row').querySelector('.split-part-error').textContent = ''; }
      if (event.target.matches('.split-total')) $('.split-total-error').textContent = '';
      if (event.target.matches('.split-date')) $('.split-date-error').textContent = '';
      if (event.target.matches('.split-amount,.split-total')) { $('.split-error').textContent = ''; paintProgress(); }
    });
    // Rời ô tiền: số đọc được thì ghi lại có nhóm nghìn như khung Ghi phiếu thu.
    drawer.addEventListener('focusout', event => {
      if (!event.target.matches('.split-amount,.split-total')) return;
      const shown = model.readMoneyInput(event.target.value);
      if (shown) { event.target.value = shown; readParts(); }
    });
    drawer.addEventListener('keydown', async event => {
      if (event.key === 'Enter' && event.repeat) { event.preventDefault(); return; }
      if (event.key === 'Escape') {
        event.preventDefault();
        if (picking) { picking = false; readParts(); paintParts(); $('.split-add').focus(); }
        else if (step === 'review') { review = null; showStep('form'); $('.split-total').focus(); }
        else close();
        return;
      }
      if (event.key !== 'Enter' || step !== 'form') return;
      if (event.target.matches('.split-search')) { event.preventDefault(); $('.split-option')?.click(); return; }
      if (event.target.matches('.split-date')) { event.preventDefault(); $('.split-total').focus(); return; }
      if (event.target.matches('.split-total,.split-reference,.split-amount')) { event.preventDefault(); await next(); }
    });
  }
  Object.assign(ctx, { openSplit });
};
