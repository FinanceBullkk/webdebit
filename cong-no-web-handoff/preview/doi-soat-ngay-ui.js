/* SO-TIEN P0-a lát 2: trang Đối soát ngày (specs/so-tien-p0a-lat2.md, mục Màn hình) — mục tiêu: chốt từng ngày. Cột trái là các ngày
 * từ số dư mở (mới nhất trên) với hai chữ trạng thái; bên phải là ngày đang chọn theo đúng thứ tự việc: ① số dư cuối ngày (sổ so với
 * bằng chứng ngân hàng, lý do chưa ký bằng câu thường, nhập số dư ngân hàng, Ký số dư) → ② giao dịch trong ngày (Phân bổ, Ký đối
 * soát) → ③ lịch sử ký, mở lại có lý do. Kiểm ngày chạy ở SQL (cùng hàm với lệnh ký); trang chỉ hiện kết quả. Tiền tính ở
 * so-tien-model.js, không ở đây (ARCH-03). Mặc định mở ngày cũ nhất đủ sao kê còn việc. */
(() => {
  'use strict';
  const F = CongNoFormat;
  const M = SoTienModel;
  const esc = F.esc;
  const API = '/api/v7/tien';
  const $ = selector => document.querySelector(selector);
  const params = new URLSearchParams(location.search);
  const S = {
    me: null, off: false, accounts: [], accountId: Number(params.get('account')) || null, days: null, today: null,
    date: /^\d{4}-\d{2}-\d{2}$/.test(params.get('date') ?? '') ? params.get('date') : null, day: null, tx: [], txDesc: false,
    evidence: null, alloc: null, customers: undefined, busy: false, toast: null, giuBao: null,
    windowEnd: null, from: null, openingAsOf: null,   // cột ngày: 93 ngày tới windowEnd (null: tới hôm nay)
  };
  const net = DoiXeChung.tao({
    S, draw, load, toastBox: $('#st-toast'), esc, tienTo: 'dsn', toastMs: 7000,
    matMang: 'Mất kết nối. Việc đang làm vẫn còn trên màn; bấm lại khi có mạng (không ghi hai lần).',
    taiLai: ['STALE_VERSION', 'DAY_NOT_READY', 'DAY_SIGNED'],
  });
  const can = role => M.has(S.day?.roles, role);
  const empty = text => `<section class="nd-card"><p class="st-empty">${esc(text)}</p></section>`;
  const dirText = d => (d === 'in' ? 'Thu' : 'Chi');

  function showError(text) {
    const box = $('#error');
    box.textContent = text;
    box.hidden = false;
  }

  async function load() {
    try {
      if (!S.me) {
        try {
          S.me = await net.getJson(`${API}/me`);
        } catch (e) {
          if (e.code !== 'TIEN_OFF') throw e;
          S.off = true;
        }
      }
      if (S.me?.visible) {
        S.accounts = (await net.getJson(`${API}/accounts`)).accounts;
        if (!S.accounts.some(a => a.id === S.accountId)) S.accountId = S.accounts[0]?.id ?? null;
      }
      if (S.me?.visible && S.accountId) {
        const id = S.accountId;
        const range = S.windowEnd ? `?from=${M.addDays(S.windowEnd, -92)}&to=${S.windowEnd}` : '';
        const coverage = await net.getJson(`${API}/accounts/${id}/coverage${range}`);
        S.today = coverage.today;
        S.from = coverage.from;
        S.openingAsOf = coverage.opening_as_of;
        S.days = coverage.days.filter(d => d.coverage !== 'before_opening' && d.coverage !== 'future');
        S.date ??= M.nextDay(S.days);
        if (S.date) {
          const date = S.date;
          S.day = null;
          const [day, tx] = await Promise.all([net.getJson(`${API}/accounts/${id}/days/${date}`),
            net.getJson(`${API}/accounts/${id}/transactions?from=${date}&to=${date}`)]);
          if (date === S.date) {
            S.day = day;
            S.tx = tx.transactions;
            S.txDesc = tx.description_visible;
          }
        }
      }
      $('#error').hidden = true;
    } catch (e) {
      showError(e.message);
    }
    document.body.dataset.loaded = '1';
    draw();
  }

  // ---------- vẽ ----------
  function accountHtml() {
    const label = a => `${a.bank_code} ••••${a.account_last4} · ${a.currency}`;
    if (S.accounts.length > 1) {
      return `<label class="st-account"><select data-act="account" aria-label="Tài khoản">${
        S.accounts.map(a => `<option value="${a.id}"${a.id === S.accountId ? ' selected' : ''}>${esc(label(a))}</option>`).join('')}</select></label>`;
    }
    const one = S.accounts.find(a => a.id === S.accountId);
    return one ? `<span class="st-account">${esc(label(one))}</span>` : '';
  }

  function daysHtml() {
    if (!S.days.length) return `<nav class="nd-card st-days" aria-label="Các ngày"><p class="st-empty">Chưa có ngày nào từ số dư mở.</p></nav>`;
    const items = S.days.map(d => {
      // Hôm nay chưa có sao kê là bình thường (kế toán tải lúc 17h, QD-04): chữ thường, không đỏ.
      const todayMissing = d.date === S.today && d.coverage === 'missing';
      const cov = todayMissing ? 'Chưa tải sao kê' : M.dayCoverageText(d);
      const covClass = d.coverage_status === 'signed' ? 'ok' : d.coverage === 'missing' && !todayMissing ? 'bad' : '';
      const biz = d.business_status === 'signed' ? 'ok' : '';
      return `<li><button type="button" data-act="day" data-date="${d.date}" data-f="day-${d.date}" aria-current="${d.date === S.date}">
        <span class="d">${esc(M.weekday(d.date))} ${M.shortDate(d.date)}</span><span class="n">${d.transactions} giao dịch</span>
        <span class="s">Số dư: <b class="${covClass}">${esc(cov)}</b> · Đối soát: <b class="${biz}">${esc(M.SIGN[d.business_status])}</b></span></button></li>`;
    }).join('');
    const older = S.openingAsOf && S.from && S.openingAsOf < S.from
      ? `<button type="button" class="nd-btn st-days-more" data-act="days-older">Ngày trước ${M.vnDate(S.from)}</button>` : '';
    const newer = S.windowEnd ? '<button type="button" class="nd-btn st-days-more" data-act="days-newest">Về các ngày gần nhất</button>' : '';
    return `<nav class="nd-card st-days" aria-label="Các ngày">${newer}<ul>${items}</ul>${older}</nav>`;
  }

  function lastRow(track, action) {
    return S.day.history.find(h => h.track === track && h.action === action);
  }

  function evidenceLabel(e) {
    if (e.source === 'file') return `File sao kê (lô #${e.import_id}) · ${e.current ? 'bản mới nhất, dùng để ký' : 'bản cũ, chỉ để xem'}`;
    return `${M.SOURCE[e.source] ?? e.source}: ${e.note} · ${e.actor} ${M.stamp(e.at)}${e.role_overlap ? ' · người nhập lô tự nhập' : ''}`;
  }

  function balanceHtml() {
    const d = S.day;
    const signed = d.coverage_status === 'signed';
    const status = signed ? '<span class="st-tag ok">Đã ký số dư</span>' : d.ready ? '<span class="st-tag ok">Khớp, chờ ký</span>'
      : `<span class="st-tag ${d.reasons.includes('BALANCE_DIFFERENCE') ? 'bad' : 'warn'}">Chưa ký được</span>`;
    const evidence = d.evidence.map(e => `<tr><td>${esc(evidenceLabel(e))}</td><td class="st-money">${esc(M.money(e.amount_minor))}</td>
      <td><span class="st-tag ${e.difference_minor === '0' ? 'ok' : e.current ? 'bad' : ''}">${esc(M.diffText(e.difference_minor))}</span></td></tr>`).join('');
    const reasons = d.reasons.map(code => {
      let text = M.REASON[code] ?? code;
      if (code === 'MISSING_DAYS_BEFORE') text += ` Ngày: ${d.missing_before.map(M.shortDate).join(', ')}${d.missing_before_count > d.missing_before.length ? '…' : ''}.`;
      if (code === 'PENDING_IMPORT') text += ` <a href="/so-tien.html?account=${S.accountId}&lo=${d.pending_imports[0]}">Mở lô ở Sổ tiền ›</a>`;
      return `<li>${code === 'PENDING_IMPORT' ? text.replace(/^[^<]+/, m => esc(m)) : esc(text)}</li>`;
    }).join('');
    const bad = d.reasons.includes('BALANCE_DIFFERENCE');
    const signedRow = signed ? lastRow('coverage', 'sign') : null;
    const signedHtml = signedRow ? `<p class="st-signed"><span>Ký bởi <b>${esc(signedRow.by.actor)}</b> lúc ${M.stamp(signedRow.by.at)}</span>${signedRow.role_overlap ? '<span class="st-tag warn">Người ký cũng là người nhập (trùng vai)</span>' : ''}</p>` : '';
    const recheck = signed && !d.ready ? `<ul class="st-reasons bad"><li>Ngày đã ký nhưng kiểm lại hiện không qua:</li>${reasons}</ul>` : '';
    const reasonList = !signed && !d.ready ? `<ul class="st-reasons ${bad ? 'bad' : ''}">${reasons}</ul>` : '';
    const form = S.evidence ? `<div class="st-form" role="group" aria-label="Nhập số dư ngân hàng">
      <label>Số dư cuối ngày theo ngân hàng<input data-ev="amount" data-f="ev-amount" inputmode="numeric" autocomplete="off" value="${esc(S.evidence.amount)}"></label>
      <label>Lấy từ<select data-ev="source">${['bank_pdf', 'bank_app', 'bank_paper', 'other'].map(s => `<option value="${s}"${s === S.evidence.source ? ' selected' : ''}>${esc(M.SOURCE[s])}</option>`).join('')}</select></label>
      <label>Ghi chú (bắt buộc)<input data-ev="note" data-f="ev-note" maxlength="500" placeholder="Ví dụ: sao kê PDF tải lúc 17:05" value="${esc(S.evidence.note)}"></label>
      <span class="st-form-acts"><button type="button" class="nd-btn" data-act="ev-cancel">Thôi</button>
      <button type="button" class="nd-btn primary" data-act="ev-save"${S.busy ? ' disabled' : ''}>Lưu số dư</button></span></div>` : '';
    const acts = [];
    if (can('tien_review') && !signed && !S.evidence) acts.push('<button type="button" class="nd-btn" data-act="ev-open">Nhập số dư ngân hàng</button>');
    if (can('tien_review') && signed) acts.push(`<button type="button" class="nd-btn" data-act="reopen" data-track="coverage"${S.busy ? ' disabled' : ''}>Mở lại ngày</button>`);
    if (can('tien_review') && !signed) acts.push(`<button type="button" class="nd-btn primary" data-act="sign-coverage"${!d.ready || S.busy ? ' disabled' : ''}>Ký số dư</button>`);
    return `<section class="nd-card" aria-labelledby="st-bal-title"><div class="nd-card-head"><span class="st-step">1</span>
      <h2 id="st-bal-title">Số dư cuối ngày ${esc(M.weekday(d.date))} ${M.vnDate(d.date)}</h2>${status}</div>
      <table class="st-table st-evidence"><tbody><tr><td><b>Số dư sổ tiền</b> (từ sao kê đã ghi)</td><td class="st-money"><b>${esc(M.money(d.ledger_closing_minor))}</b></td><td></td></tr>
      ${evidence || '<tr><td colspan="3" class="st-muted">Chưa có số dư ngân hàng cho ngày này.</td></tr>'}</tbody></table>
      ${reasonList}${recheck}${signedHtml}${form}<div class="st-acts">${acts.join('')}</div></section>`;
  }

  function txHtml() {
    const d = S.day;
    const biz = d.business;
    const signed = d.business_status === 'signed';
    const rows = S.tx.filter(t => !t.voided).map(t => `<tr><td>${dirText(t.direction)} <span class="st-muted st-small">#${t.id}</span></td><td class="st-money">${esc(M.money(t.amount_minor))}</td>
      <td>${esc(t.bank_ref ?? '')}</td>${S.txDesc ? `<td class="st-desc">${esc(t.description ?? '')}</td>` : ''}
      <td><span class="st-tag ${t.status === 'applied' || t.status === 'matched' ? 'ok' : 'warn'}">${esc(M.STATUS[t.status])}</span></td>
      <td class="st-money">${esc(M.money(t.unallocated_minor))}</td>
      <td>${can('tien_phan_bo') ? `<button type="button" class="nd-btn" data-act="alloc" data-id="${t.id}"${S.busy ? ' disabled' : ''}>Phân bổ</button>` : ''}</td></tr>`).join('');
    const signedRow = signed ? lastRow('business', 'sign') : null;
    const signedHtml = signedRow ? `<p class="st-signed"><span>Ký đối soát bởi <b>${esc(signedRow.by.actor)}</b> lúc ${M.stamp(signedRow.by.at)} · lúc ký còn ${signedRow.snapshot.not_fully_allocated} khoản chưa phân bổ đủ</span>${signedRow.role_overlap ? '<span class="st-tag warn">Người ký cũng nhập hoặc phân bổ (trùng vai)</span>' : ''}</p>` : '';
    const acts = [];
    if (can('tien_review') && signed) acts.push(`<button type="button" class="nd-btn" data-act="reopen" data-track="business"${S.busy ? ' disabled' : ''}>Mở lại đối soát</button>`);
    if (can('tien_review') && !signed) {
      acts.push(`<button type="button" class="nd-btn primary" data-act="sign-business"${d.coverage_status !== 'signed' || S.busy ? ' disabled' : ''}>Ký đối soát</button>`);
    }
    const note = !signed && d.coverage_status !== 'signed' ? '<p class="st-hint st-pad">Ký số dư trước, rồi ký đối soát.</p>'
      : !signed ? '<p class="st-hint st-pad">Ký được khi còn khoản chưa rõ; số khoản còn lại được ghi lại lúc ký.</p>' : '';
    return `<section class="nd-card" aria-labelledby="st-tx-title"><div class="nd-card-head"><span class="st-step">2</span><h2 id="st-tx-title">Giao dịch trong ngày</h2>
      <span class="st-small st-muted">${biz.transactions} giao dịch · ${biz.not_fully_allocated} chưa phân bổ đủ</span>${signed ? '<span class="st-tag ok">Đã ký đối soát</span>' : ''}</div>
      ${rows ? `<div class="st-scroll"><table class="st-table"><thead><tr><th>Thu/Chi</th><th class="st-money">Số tiền</th><th>Mã GD</th>${S.txDesc ? '<th>Nội dung</th>' : ''}
      <th>Trạng thái</th><th class="st-money">Chưa phân bổ</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="st-empty">Không có giao dịch trong ngày này.</p>'}
      ${signedHtml}${note}<div class="st-acts">${acts.join('')}</div></section>`;
  }

  function historyHtml() {
    if (!S.day.history.length) return '';
    const track = { coverage: 'Số dư', business: 'Đối soát' };
    const items = S.day.history.map(h => `<li>${track[h.track]}: <b>${h.action === 'sign' ? 'ký' : 'mở lại'}</b> · ${esc(h.by?.actor ?? '')} ${M.stamp(h.by?.at)}${h.role_overlap ? ' · trùng vai' : ''}${h.note ? ` · ${esc(h.note)}` : ''}</li>`).join('');
    return `<section class="nd-card" aria-labelledby="st-hist-title"><div class="nd-card-head"><span class="st-step">3</span><h2 id="st-hist-title">Lịch sử ký</h2></div><ul class="st-hist">${items}</ul></section>`;
  }

  function draw() {
    $('#st-account').innerHTML = S.me?.visible ? accountHtml() : '';
    if (S.accountId) $('#st-to-book').href = `/so-tien.html?account=${S.accountId}`;
    const root = $('#st-root');
    let html;
    if (S.off) html = empty('Sổ tiền chưa bật trên máy này.');
    else if (!S.me) return;
    else if (!S.me.visible) html = empty('Bạn chưa được cấp vai sổ tiền. Báo người quản trị sổ tiền cấp vai cho tài khoản đăng nhập của bạn.');
    else if (!S.accountId) html = empty('Chưa có tài khoản ngân hàng nào bạn được xem.');
    else if (!S.days) return;
    else if (!S.days.length && !S.day) html = empty('Tài khoản chưa có số dư mở, hoặc chưa tới ngày số dư mở.');
    else html = `<div class="st-days-layout">${daysHtml()}<div class="st-day">${S.day?.date === S.date ? balanceHtml() + txHtml() + historyHtml() : ''}</div></div>`;
    DoiXeChung.withFocus(() => { root.innerHTML = html; });
    net.drawToast();
    if (S.alloc) drawAlloc();
  }

  // ---------- phân bổ ----------
  function refInput(line, i) {
    const target = M.TARGET[line.kind];
    if (!target?.ref) return '<span class="none">Không cần</span>';
    if (target.ref === 'customer_id' && Array.isArray(S.customers)) {
      return `<select data-line="${i}" data-field="ref" data-f="ref-${i}" aria-label="Sổ khách"><option value="">Chọn sổ khách</option>${S.customers.map(c =>
        `<option value="${c.id}"${String(c.id) === String(line.ref) ? ' selected' : ''}>${esc(c.name)}</option>`).join('')}</select>`;
    }
    const label = target.ref === 'category' ? 'Mục chi' : target.ref === 'customer_id' ? 'Mã sổ khách' : 'Mã giao dịch chân kia (#)';
    return `<input data-line="${i}" data-field="ref" data-f="ref-${i}" value="${esc(line.ref)}" placeholder="${label}" aria-label="${label}"${target.ref === 'category' ? '' : ' inputmode="numeric"'}>`;
  }

  function drawAlloc() {
    const a = S.alloc;
    const t = a.tx;
    const kinds = M.TARGETS.filter(k => !k.dir || k.dir === t.direction);
    const left = M.remaining(t.amount_minor, a.lines);
    const rows = a.lines.map((line, i) => `<div class="st-alloc-row">
      <select data-line="${i}" data-field="kind" data-f="kind-${i}" aria-label="Loại">${kinds.map(k => `<option value="${k.kind}"${k.kind === line.kind ? ' selected' : ''}>${esc(k.label)}</option>`).join('')}</select>
      ${refInput(line, i)}<input data-line="${i}" data-field="amount" data-f="amount-${i}" value="${esc(line.amount)}" inputmode="numeric" aria-label="Số tiền" class="st-money">
      <input data-line="${i}" data-field="note" data-f="note-${i}" value="${esc(line.note)}" maxlength="500" placeholder="Ghi chú" aria-label="Ghi chú">
      <button type="button" class="nd-icon" data-act="alloc-remove" data-line="${i}" aria-label="Bỏ dòng ${i + 1}">✕</button></div>`).join('');
    const body = `<p class="st-alloc-tx">${M.vnDate(t.booking_date)} · ${dirText(t.direction)} ${esc(M.money(t.amount_minor))}${t.bank_ref ? ` · mã ${esc(t.bank_ref)}` : ''}${t.description ? ` · ${esc(t.description)}` : ''}</p>
      ${a.lines.length ? '<div class="st-alloc-head"><span>Loại</span><span>Đích</span><span>Số tiền</span><span>Ghi chú</span><span></span></div>' : ''}${rows}
      <button type="button" class="nd-btn" data-act="alloc-add">Thêm dòng</button>
      <p class="st-left${left.startsWith('-') ? ' bad' : ''}" id="st-alloc-left">${left.startsWith('-') ? `Vượt số tiền giao dịch ${esc(M.money(left.slice(1)))}` : `Còn lại chưa phân bổ: ${esc(M.money(left))}`}</p>
      ${a.current.length ? `<label class="nd-field">Lý do (bắt buộc khi bỏ hay đổi dòng đã có)<input data-alloc-reason data-f="alloc-reason" maxlength="500" value="${esc(a.reason)}"></label>` : ''}
      ${a.error ? `<p class="st-left bad" role="alert">${esc(a.error)}</p>` : ''}`;
    DoiXeChung.withFocus(() => { $('#st-alloc-body').innerHTML = body; });
  }

  async function openAlloc(id) {
    try {
      const detail = await net.getJson(`${API}/transactions/${id}`);
      if (S.customers === undefined && M.TARGETS.some(t => t.ref === 'customer_id')) {
        S.customers = await net.getJson('/api/v7/customers').then(r => (r.customers ?? []).filter(c => !c.status || c.status === 'active')
          .map(c => ({ id: c.id, name: c.name })).sort((a, b) => a.name.localeCompare(b.name, 'vi')), () => null);
      }
      const t = detail.transaction;
      const lines = detail.allocations.map(l => ({ kind: l.target_kind, ref: String(Object.values(l.target_ref)[0] ?? ''), amount: M.money(l.amount_minor), note: l.note ?? '' }));
      if (!lines.length) lines.push({ kind: t.direction === 'in' ? 'customer_unapplied' : 'expense_category', ref: '', amount: M.money(t.unallocated_minor), note: '' });
      S.alloc = { tx: t, current: detail.allocations.map(l => ({ target_kind: l.target_kind, target_ref: l.target_ref, amount_minor: l.amount_minor, note: l.note })),
        lines, reason: '', error: null };
      drawAlloc();
      $('#st-alloc').showModal();
    } catch (e) {
      net.bao(e.message, 'err');
    }
  }

  async function saveAlloc() {
    const a = S.alloc;
    const built = M.allocationLines(a.lines);
    const left = M.remaining(a.tx.amount_minor, a.lines);
    a.error = built.error ?? (left.startsWith('-') ? 'Tổng các dòng vượt số tiền giao dịch.' : null);
    const reason = M.clean(a.reason);
    if (!a.error && M.changesExisting(a.current, built.lines) && !reason) a.error = 'Bỏ hay đổi dòng đã có: ghi lý do.';
    if (a.error) { drawAlloc(); return; }
    if (S.busy) return;
    S.busy = true;
    try {
      const out = await net.post(`${API}/allocations`, { transaction_id: a.tx.id, expected_version: a.tx.version, lines: built.lines, ...(reason ? { reason } : {}) });
      S.alloc = null;
      $('#st-alloc').close();
      S.busy = false;
      await load();
      net.bao(out.unchanged ? 'Phân bổ không đổi.' : `Đã lưu phân bổ. Còn lại chưa phân bổ: ${M.money(out.unallocated_minor)}.`);
    } catch (e) {
      S.busy = false;
      if (!S.alloc) return;
      a.error = e.message;
      if (e.code === 'STALE_VERSION') {
        a.error += ' Đã đọc lại giao dịch; xem lại các dòng rồi bấm Lưu lần nữa.';
        try {
          const fresh = await net.getJson(`${API}/transactions/${a.tx.id}`);
          a.tx = fresh.transaction;
          a.current = fresh.allocations.map(l => ({ target_kind: l.target_kind, target_ref: l.target_ref, amount_minor: l.amount_minor, note: l.note }));
        } catch { /* giữ version cũ; bấm Lưu lại sẽ báo tiếp */ }
      }
      drawAlloc();
    }
  }

  // ---------- thao tác ----------
  function askReason(title, text, ok) {
    const dialog = $('#st-reason');
    $('#st-reason-title').textContent = title;
    $('#st-reason-text').textContent = text;
    $('#st-reason-ok').textContent = ok;
    const input = $('#st-reason-input');
    input.value = '';
    dialog.showModal();
    input.focus();
    return new Promise(resolve => {
      const onCancel = () => done(null);
      function done(value) {
        dialog.removeEventListener('click', onClick);
        dialog.removeEventListener('cancel', onCancel);
        dialog.close();
        resolve(value);
      }
      function onClick(event) {
        const act = event.target.closest('[data-act]')?.dataset.act;
        if (act === 'reason-cancel') done(null);
        if (act === 'reason-ok') {
          if (!M.clean(input.value)) { input.focus(); return; }
          done(M.clean(input.value));
        }
      }
      dialog.addEventListener('click', onClick);
      dialog.addEventListener('cancel', onCancel);
    });
  }

  function pickDay(date) {
    S.date = date;
    S.evidence = null;
    const q = new URLSearchParams({ account: String(S.accountId), date });
    history.replaceState(null, '', `?${q}`);
    load();
  }

  function saveEvidence() {
    const e = S.evidence;
    const amount = M.readAmount(e.amount, { signed: true });
    if (amount === null) { net.bao('Số dư phải là số nguyên, ví dụ 1.250.000.', 'err'); return; }
    if (!M.clean(e.note)) { net.bao('Ghi chú lấy số dư từ đâu (bắt buộc).', 'err'); return; }
    net.ghi(`${API}/balance-evidence`, { account_id: S.accountId, as_of_date: S.date, amount_minor: amount, source: e.source, note: M.clean(e.note) }, out => {
      S.evidence = null;
      net.bao(out.role_overlap ? 'Đã lưu số dư ngân hàng (bạn cũng là người nhập lô của ngày này: có đánh dấu trùng vai).' : 'Đã lưu số dư ngân hàng.');
    });
  }

  document.addEventListener('change', event => {
    const el = event.target;
    if (el.dataset.act === 'account') {
      Object.assign(S, { accountId: Number(el.value), date: null, day: null, evidence: null, windowEnd: null });
      load();
      return;
    }
    if (el.dataset.ev) S.evidence[el.dataset.ev] = el.value;
    // Chỉ ô chọn mới vẽ lại hộp (đổi loại thì ô đích đổi theo). Ô gõ đã cập nhật ở sự kiện input; vẽ lại khi ô gõ mất focus sẽ thay
    // nút người dùng vừa nhấn chuột xuống (Thêm dòng, Lưu) bằng nút mới và cú bấm bị mất.
    if (el.dataset.field && S.alloc && el.tagName === 'SELECT') {
      const line = S.alloc.lines[Number(el.dataset.line)];
      line[el.dataset.field] = el.value;
      if (el.dataset.field === 'kind') line.ref = '';
      drawAlloc();
    }
  });
  document.addEventListener('input', event => {
    const el = event.target;
    if (el.dataset.ev) S.evidence[el.dataset.ev] = el.value;
    if (el.matches('[data-alloc-reason]') && S.alloc) S.alloc.reason = el.value;
    if (el.dataset.field && S.alloc && el.tagName === 'INPUT') {
      S.alloc.lines[Number(el.dataset.line)][el.dataset.field] = el.value;
      if (el.dataset.field === 'amount') {
        const left = M.remaining(S.alloc.tx.amount_minor, S.alloc.lines);
        const box = $('#st-alloc-left');
        box.className = `st-left${left.startsWith('-') ? ' bad' : ''}`;
        box.textContent = left.startsWith('-') ? `Vượt số tiền giao dịch ${M.money(left.slice(1))}` : `Còn lại chưa phân bổ: ${M.money(left)}`;
      }
    }
  });
  document.addEventListener('click', event => {
    const inReason = event.target.closest('#st-reason');
    if (inReason) return;
    const el = event.target.closest('[data-act], #refresh-data');
    if (!el) return;
    if (el.id === 'refresh-data') { load(); return; }
    const act = el.dataset.act;
    if (act === 'dong-toast') { S.toast = null; net.drawToast(); }
    if (act === 'day') pickDay(el.dataset.date);
    if (act === 'ev-open') { S.evidence = { amount: '', source: 'bank_pdf', note: '' }; draw(); }
    if (act === 'ev-save') saveEvidence();
    if (act === 'ev-cancel') { S.evidence = null; draw(); }
    if (act === 'days-older') { S.windowEnd = M.addDays(S.from, -1); load(); }
    if (act === 'days-newest') { S.windowEnd = null; load(); }
    if (act === 'sign-coverage') {
      net.ghi(`${API}/days/sign-coverage`, { account_id: S.accountId, business_date: S.date, expected_version: S.day.account_version },
        out => net.bao(out.changed ? `Đã ký số dư ngày ${M.vnDate(S.date)}${out.role_overlap ? ' (có đánh dấu trùng vai)' : ''}.` : 'Ngày này đã ký trước đó.'));
    }
    if (act === 'sign-business') {
      net.ghi(`${API}/days/sign-business`, { account_id: S.accountId, business_date: S.date },
        out => net.bao(out.changed ? `Đã ký đối soát ngày ${M.vnDate(S.date)}; còn ${out.not_fully_allocated} khoản chưa phân bổ đủ.` : 'Ngày này đã ký đối soát trước đó.'));
    }
    if (act === 'reopen') {
      const track = el.dataset.track;
      askReason(track === 'coverage' ? 'Mở lại ngày' : 'Mở lại đối soát',
        track === 'coverage' ? 'Bỏ chữ ký số dư của ngày này và mọi ngày sau đang ký (số dư cuối các ngày đó phụ thuộc ngày này), kèm chữ ký đối soát nếu có, để nhập giao dịch muộn hoặc sửa lô. Lý do vào lịch sử.'
          : 'Bỏ chữ ký đối soát của ngày này (ví dụ để rà lại phân bổ). Chữ ký số dư giữ nguyên. Lý do vào lịch sử.', 'Mở lại')
        .then(reason => reason && net.ghi(`${API}/days/reopen`, { account_id: S.accountId, business_date: S.date, track, reason },
          out => net.bao(out.reopened_days?.length > 1 ? `Đã mở lại ${out.reopened_days.length} ngày: ${out.reopened_days.map(M.shortDate).join(', ')}.` : 'Đã mở lại.')));
    }
    if (act === 'alloc') openAlloc(Number(el.dataset.id));
    if (act === 'alloc-add' && S.alloc) {
      S.alloc.lines.push({ kind: S.alloc.tx.direction === 'in' ? 'customer_unapplied' : 'expense_category', ref: '', amount: '', note: '' });
      drawAlloc();
    }
    if (act === 'alloc-remove' && S.alloc) { S.alloc.lines.splice(Number(el.dataset.line), 1); drawAlloc(); }
    if (act === 'alloc-cancel') { S.alloc = null; $('#st-alloc').close(); }
    if (act === 'alloc-save' && S.alloc) saveAlloc();
  });
  $('#st-alloc').addEventListener('cancel', () => { S.alloc = null; });

  load();
})();
