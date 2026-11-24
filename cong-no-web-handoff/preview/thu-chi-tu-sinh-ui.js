/* THU-CHI-02 đợt 0: giao diện bản bấm thử "Thu chi tự sinh". Chỉ vẽ và bắt thao tác; mọi số tiền và câu chữ về tiền do
   thu-chi-tu-sinh-model.js trả về (ARCH-03). Không gọi /api/, không ghi gì ra ngoài trình duyệt; localStorage (có try/catch) chỉ nhớ vai và
   bước đang xem. Mỗi vai một màn: Sếp (Dòng tiền), Kế toán (Sổ tiền, ngoại lệ, chờ chuyển, quỹ, việc team công nợ), Tiền hàng (ví khách TQ),
   Nhân viên (đề nghị chi). */
(() => {
  'use strict';
  const M = ThuChiTuSinhModel;
  const { esc } = CongNoFormat;
  const $ = selector => document.querySelector(selector);
  const STORE_ROLE = 'tcs-role';
  const STORE_STEP = 'tcs-step';

  const EXAMPLES = {
    chi_thuong: { type: 'chi_thuong', payeeId: 'cang-y', walletId: '', amountText: '8.000.000', container: 'MAUU1000101', note: 'Phí nâng hạ container', attached: true },
    chi_ho: { type: 'chi_ho', payeeId: 'nha-vuon-1', walletId: 'tq1', amountText: '120.000.000', container: '', note: 'Chi hộ khách TQ cho nhà vườn', attached: true },
    ung_tien_mat: { type: 'ung_tien_mat', payeeId: 'nguoi-nhan-1', walletId: 'tq2', amountText: '30.000.000', container: '', note: 'Ứng tiền mặt cho người của khách TQ', attached: false },
  };
  const blankForm = () => ({ type: 'chi_thuong', payeeId: '', walletId: '', amountText: '', container: '', note: '', attached: false });
  const ui = {
    sim: M.newSim(), role: 'sep', tab: { ketoan: 'so-tien', nhanvien: 'ds' }, wallet: 'tq1', account: 'all', openId: null, rejecting: null,
    f: { ...blankForm(), comment: '', counted: '', rejectReason: '', expWallet: '', expAmount: '', expNote: '' },
    errors: {}, note: null, stepsOpen: window.matchMedia('(min-width:1000px)').matches,
  };

  // ---- Lưu vai và bước đang xem ----
  const remember = () => {
    try { localStorage.setItem(STORE_ROLE, ui.role); localStorage.setItem(STORE_STEP, String(ui.sim.cursor)); } catch { /* không có localStorage thì thôi */ }
  };
  function restore() {
    try {
      const role = localStorage.getItem(STORE_ROLE);
      if (M.ROLES.some(item => item.id === role)) ui.role = role;
      const cursor = Number(localStorage.getItem(STORE_STEP));
      if (Number.isInteger(cursor) && cursor > 0 && cursor <= M.STEPS.length) for (let index = 0; index < cursor; index += 1) M.next(ui.sim);
    } catch { /* bỏ qua */ }
  }

  // ---- Mảnh HTML dùng chung ----
  const button = (act, label, { id = '', cls = '', extra = '' } = {}) => `<button type="button" class="tcs-btn ${cls}" data-act="${act}"${id ? ` data-id="${esc(id)}"` : ''} ${extra}>${esc(label)}</button>`;
  const fig = (key, label, text, value, { cls = '', sub = '' } = {}) => `<div class="tcs-fig ${cls}"><small>${esc(label)}</small><b data-fig="${key}" data-value="${esc(value)}">${esc(text)}</b>${sub ? `<span>${sub}</span>` : ''}</div>`;
  const empty = text => `<p class="tcs-empty">${esc(text)}</p>`;
  const stepTime = () => `${ui.sim.state.today} ${M.stepNow(ui.sim)?.time ?? '17:45'}`;
  const errOf = key => (ui.errors[key] ? `<p class="tcs-err" id="err-${key}" role="alert">${esc(ui.errors[key])}</p>` : '');
  const badOf = key => (ui.errors[key] ? ' bad' : '');
  const describe = key => (ui.errors[key] ? ` aria-invalid="true" aria-describedby="err-${key}"` : '');
  function say(text, bad = false) { ui.note = { text, bad }; }
  function options(list, value, placeholder) {
    return `<option value="">${esc(placeholder)}</option>${list.map(item => `<option value="${esc(item.id)}"${item.id === value ? ' selected' : ''}>${esc(item.name)}</option>`).join('')}`;
  }
  const tag = (text, tone = 'neutral') => `<span class="tag ${tone}">${esc(text)}</span>`;

  // ---- Kịch bản (cột trái) ----
  function renderScenario() {
    const sim = ui.sim;
    const step = M.stepNow(sim);
    const total = M.STEPS.length;
    const doneByHand = step && M.stepStatus(sim, sim.cursor) === 'da-lam-tay';
    const bot = M.lastBot(sim.state);
    const list = M.STEPS.map((item, index) => {
      const status = M.stepStatus(sim, index);
      const word = { xong: 'Xong', 'dang-cho': 'Đang chờ', 'da-lam-tay': 'Đã làm tay', 'chua-toi': 'Chưa tới' }[status];
      return `<li${index === sim.cursor ? ' aria-current="step"' : ''}><span class="t">${esc(item.time)}</span><span>${esc(item.title)}</span><span class="s">${word}</span></li>`;
    }).join('');
    const head = step
      ? `<p class="tcs-step-title" data-step="${step.n}">Bước ${step.n} · ${esc(step.time)} · ${esc(step.title)}</p><p class="tcs-step-text">${esc(step.text)}</p>
         <p class="tcs-human">${doneByHand ? 'Bạn đã làm xong việc của bước này. Bấm Tiếp để sang bước sau.' : `Việc của bạn: ${esc(step.human)} Hoặc bấm Tiếp để máy làm thay.`}</p>`
      : '<p class="tcs-step-title" data-step="end">Hết ngày</p><p class="tcs-step-text">Đã chạy hết 11 bước. Bấm Đặt lại để chạy lại từ đầu ngày.</p>';
    const there = step && (ui.role !== step.role || (step.role === 'ketoan' && ui.tab.ketoan !== step.tab) || (step.role === 'nhanvien' && ui.tab.nhanvien !== (step.tab === 'tao' ? 'tao' : 'ds')))
      ? button('goto', `Mở màn ${M.ROLES.find(item => item.id === step.role).label}`, { cls: 'primary' }) : '';
    $('#scenario').innerHTML = `<div class="top"><h2>Kịch bản một ngày</h2><span data-progress>Đã làm ${sim.cursor} / ${total} bước</span>
      <div class="go">${button('back', 'Trước', { extra: sim.cursor === 0 ? 'disabled' : '' })}${button('next', step ? 'Tiếp' : 'Hết ngày', { cls: 'primary', extra: step ? '' : 'disabled' })}${button('reset', 'Đặt lại')}</div></div>
      ${head}${there ? `<div class="tcs-human">${there}</div>` : ''}
      ${bot ? `<p class="tcs-bot">Bot (mô phỏng) nhắn ${esc(bot.to)}: ${esc(bot.text)}</p>` : ''}
      <details${ui.stepsOpen ? ' open' : ''}><summary>Cả 11 bước</summary><ol class="tcs-steps">${list}</ol></details>`;
  }

  function renderRoles() {
    $('#roles').innerHTML = `<b>Xem như:</b>${M.ROLES.map(item => `<button type="button" class="tcs-role" data-act="role" data-id="${item.id}" aria-pressed="${item.id === ui.role}" title="${esc(item.note)}">${esc(item.label)}</button>`).join('')}`;
  }

  // ---- Sếp: Dòng tiền ----
  function requestCard(view) {
    const wallet = view.wallet;
    const warn = wallet && (wallet.over || wallet.overLimit)
      ? `<p class="warnline">${wallet.over ? `Vượt số dư ví: ví ${esc(wallet.name)} còn ${esc(wallet.balanceText)}, đề nghị ${esc(view.amountText)}; sau khi chi còn ${esc(wallet.afterText)}.` : ''}${wallet.overLimit ? ` Quá hạn mức ứng ${esc(wallet.limitText)}.` : ''}</p>` : '';
    const rejecting = ui.rejecting === view.id;
    return `<article class="tcs-ask" data-request="${esc(view.id)}"><div class="head"><b>${esc(view.code)}</b><span>${esc(view.typeText)}</span><span class="amt">${esc(view.amountText)}</span></div>
      <p class="meta">Người nhận: ${esc(view.payee)} · Loại chi: ${esc(view.category)}${view.container ? ` · Container ${esc(view.container)}` : ''}${view.note ? ` · ${esc(view.note)}` : ''}</p>
      <p class="meta">${view.attachment ? `Ảnh đính kèm: ${esc(view.attachment)} (ảnh giả)` : 'Chưa có ảnh đính kèm'} · Người đề nghị: ${esc(view.by)}</p>${warn}
      ${rejecting ? `<div class="why"><label class="tcs-field${badOf('reason')}"><span>Lý do từ chối</span><input type="text" data-f="rejectReason" value="${esc(ui.f.rejectReason)}"${describe('reason')}></label>${errOf('reason')}
        <div class="acts">${button('reject-send', 'Gửi từ chối', { id: view.id, cls: 'danger' })}${button('reject-cancel', 'Không từ chối')}</div></div>`
        : `<div class="acts">${button('approve', 'Duyệt', { id: view.id, cls: 'primary' })}${button('reject-open', 'Từ chối', { id: view.id, cls: 'danger' })}</div>`}</article>`;
  }
  function viewSep() {
    const state = ui.sim.state;
    const d = M.dongTien(state);
    const asks = M.pendingApproval(state);
    const flags = M.openFlags(state);
    const unknown = M.exceptions(state).filter(item => item.kind === 'chua_ro');
    const askHtml = asks.map(requestCard).join('')
      + flags.map(flag => `<article class="tcs-ask red" data-flag="${esc(flag.id)}"><div class="head"><b>${esc(flag.title)}</b></div><p class="meta">${esc(flag.text)}</p>
        ${flag.clearable ? `<div class="acts">${button('approve-late', 'Duyệt bù', { id: flag.id, cls: 'primary' })}</div>` : '<p class="meta">Cờ này chưa có cách gỡ trong bản thử: kế toán xem lại.</p>'}</article>`).join('')
      + unknown.map(item => `<article class="tcs-ask"><div class="head"><b>${esc(item.title)}</b><span class="amt">${esc(item.amountText)}</span></div><p class="meta">${esc(item.text)}</p><p class="meta">Kế toán đang xử lý, sếp không phải làm gì.</p></article>`).join('');
    const month = M.monthByCategory(state);
    const bars = (rows, cls) => `<ul class="tcs-bars ${cls}">${rows.map(row => `<li><span>${esc(row.name)}</span><span class="val">${esc(row.text)}</span><span class="bar" aria-hidden="true"><i style="width:${row.pct}%"></i></span></li>`).join('')}</ul>`;
    return `<section class="tcs-card" aria-label="Dòng tiền"><h2>Dòng tiền · ${esc(state.today.split('-').reverse().join('/'))}</h2><div class="tcs-figs">
      ${fig('vnd', 'Tiền đồng đang có', M.money(d.vnd), d.vnd)}
      ${fig('usd', 'Đô la đang có', M.money(d.usd, 'USD'), d.usd)}
      ${fig('owed', 'Đang ứng cho khách Trung Quốc', M.money(d.owed), d.owed, { cls: d.owed > 0n ? 'warn' : '' })}
      ${fig('can-sep', 'Cần sếp', String(d.canSep.total), d.canSep.total, { cls: d.canSep.total > 0 ? 'need' : '', sub: `${d.canSep.waiting} chờ duyệt · ${d.canSep.unapproved} chi chưa duyệt · ${d.canSep.unknown} tiền về chưa rõ` })}
      ${fig('vao', 'Hôm nay vào (đồng)', M.money(d.today.vao), d.today.vao, { sub: `Đô la vào: ${esc(M.money(d.today.vaoUsd, 'USD'))}` })}
      ${fig('ra', 'Hôm nay ra (đồng)', M.money(d.today.ra), d.today.ra, { sub: `Đô la ra: ${esc(M.money(d.today.raUsd, 'USD'))}` })}</div></section>
      <section class="tcs-card" aria-label="Cần sếp"><h2>Cần sếp (${d.canSep.total})</h2>${askHtml || empty('Không có gì chờ sếp.')}</section>
      <section class="tcs-card" aria-label="Tiền theo tài khoản"><h2>Tiền đang có theo tài khoản và quỹ</h2><ul class="tcs-list">${d.accounts.map(item => `<li><span class="name">${esc(item.name)}</span><span class="val">${esc(M.money(item.balance, item.currency))}</span></li>`).join('')}</ul>
        ${d.personal.map(item => `<p class="tcs-empty">${esc(item.name)}: việc riêng, ${esc(M.money(item.balance))}. Không tính vào tổng và không vào thống kê.</p>`).join('')}</section>
      <section class="tcs-card" aria-label="Tháng này"><h2>Tháng này · thu theo khách</h2>${bars(month.thu, 'in')}<h2>Tháng này · chi theo loại chi</h2>${bars(month.chi, 'out')}
        <p class="tcs-empty">Chỉ tính tiền đồng. Tiền hàng khách Trung Quốc và chuyển giữa tài khoản không tính vào đây.</p></section>`;
  }

  // ---- Kế toán ----
  function ledgerRows(rows) {
    if (!rows.length) return empty('Chưa có giao dịch nào. Bấm Tiếp ở bước 1 để sao kê sáng về.');
    return `<div class="tcs-ledger"><div class="tcs-row head" aria-hidden="true"><span>Giờ</span><span>Tài khoản</span><span>Người đối ứng</span><span>Số tiền</span><span>Ghép vào</span></div>
      ${rows.map(row => `<div class="tcs-row${row.unresolved ? ' bad' : ''}" data-txn="${esc(row.id)}"><span class="time">${esc(row.clock)}</span><span class="acc">${esc(row.account)}</span>
        <span class="who">${esc(row.who)}${row.content ? `<small>${esc(row.content)}</small>` : ''}</span><span class="amt ${row.dir}">${esc(row.amountText)}</span>
        <span class="to"><b>${esc(row.sheet)}</b>${row.unresolved ? ' · cần xem' : ''}${row.target ? `<small>${esc(row.target)}</small>` : ''}<small>${esc(row.rule)}${row.fee ? ` · ${esc(row.fee)}` : ''}</small></span></div>`).join('')}</div>`;
  }
  function exceptionHtml(state) {
    const items = M.exceptions(state);
    const dir = M.directory(state);
    const flags = M.openFlags(state);
    const rows = items.map(item => {
      const attach = item.kind !== 'chi_chua_de_nghi';
      return `<article class="tcs-ask ${item.kind === 'chi_chua_de_nghi' ? 'red' : ''}" data-exception="${esc(item.txn.id)}"><div class="head"><b>${esc(item.title)}</b><span class="amt">${esc(item.amountText)}</span></div><p class="meta">${esc(item.text)}</p>
        ${attach ? `<div class="tcs-inline"><label class="tcs-field${badOf(`attach-${item.txn.id}`)}"><span>Gắn cho khách</span><select data-f="cust-${esc(item.txn.id)}"${describe(`attach-${item.txn.id}`)}>${options(dir.customers, ui.f[`cust-${item.txn.id}`] ?? '', 'Chọn khách')}</select></label>
          <label class="tcs-check"><input type="checkbox" data-f="rem-${esc(item.txn.id)}"${ui.f[`rem-${item.txn.id}`] ? ' checked' : ''}> Nhớ người chuyển</label>${button('attach', 'Gắn khách', { id: item.txn.id, cls: 'primary' })}</div>${errOf(`attach-${item.txn.id}`)}`
          : '<p class="meta">Chờ đề nghị duyệt hoặc sếp duyệt bù. Kế toán và người chuyển không tự gỡ được.</p>'}</article>`;
    }).join('');
    const others = flags.filter(flag => flag.type !== 'chi_chua_duyet').map(flag => `<li><span class="name">${esc(flag.title)}</span><span class="sub">${esc(flag.text)}</span></li>`).join('');
    return `${rows || empty('Hộp ngoại lệ trống: máy ghép được hết.')}${others ? `<h3>Cờ khác</h3><ul class="tcs-list">${others}</ul>` : ''}`;
  }
  function waitingHtml(state) {
    const list = M.approvedWaiting(state);
    if (!list.length) return empty('Chưa có đề nghị nào đã duyệt đang chờ chuyển.');
    return list.map(view => `<article class="tcs-ask" data-request="${esc(view.id)}"><div class="head"><b>${esc(view.code)}</b><span>${esc(view.typeText)}</span><span class="amt">${esc(view.amountText)}</span></div>
      <p class="meta">Chuyển cho ${esc(view.payee)} · ${esc(view.statusText)}</p><p class="tcs-copy" data-copy="${esc(view.id)}">${esc(view.transferText)}</p>
      <div class="acts">${button('copy', 'Chép nội dung', { id: view.id })}${button('transferred', view.status === 'da_chuyen' ? 'Đã chuyển, chờ ngân hàng' : 'Đã chuyển (mô phỏng)', { id: view.id, cls: 'primary', extra: view.status === 'da_chuyen' ? 'disabled' : '' })}</div></article>`).join('');
  }
  function cashHtml(state) {
    const cash = M.cashView(state);
    const waiting = M.cashWaiting(state);
    const give = waiting.map(view => `<article class="tcs-ask" data-request="${esc(view.id)}"><div class="head"><b>${esc(view.code)}</b><span>Ứng tiền mặt</span><span class="amt">${esc(view.amountText)}</span></div><p class="meta">Giao cho ${esc(view.payee)}</p>
      <label class="tcs-check"><input type="checkbox" data-f="photo-${esc(view.id)}"${ui.f[`photo-${view.id}`] ? ' checked' : ''}> Có ảnh biên bản bàn giao (ảnh giả)</label>${errOf(`photo-${view.id}`)}
      <div class="acts">${button('handover', 'Giao tiền mặt', { id: view.id, cls: 'primary' })}</div></article>`).join('');
    return `<div class="tcs-figs">${fig('quy', 'Quỹ tiền mặt theo sổ', cash.balanceText, cash.balance)}</div>
      <h3>Đề nghị ứng đã duyệt, chờ giao</h3>${give || empty('Không có đề nghị ứng tiền mặt nào chờ giao.')}
      <h3>Kiểm quỹ</h3><div class="tcs-inline"><label class="tcs-field${badOf('counted')}"><span>Số tiền đếm được (đồng)</span><input type="text" inputmode="numeric" data-f="counted" value="${esc(ui.f.counted)}"${describe('counted')}></label>${button('count', 'Ghi số đếm', { cls: 'primary' })}</div>${errOf('counted')}
      ${cash.counts.length ? `<ul class="tcs-list">${cash.counts.map(item => `<li><span class="name">${esc(item.clock)} · đếm ${esc(item.countedText)}, sổ ${esc(item.expectedText)}</span><span class="val">${esc(item.diffText)}</span></li>`).join('')}</ul>` : empty('Chưa kiểm quỹ hôm nay.')}
      <h3>Giao dịch của quỹ</h3>${ledgerRows(M.txnRows(state, { accountId: 'quy' }))}`;
  }
  function teamHtml(state) {
    const drafts = M.draftRows(state);
    const unknown = M.exceptions(state).filter(item => item.kind === 'chua_ro');
    return `<h3>Phiếu thu điền sẵn (chờ team công nợ ghi)</h3>${drafts.length ? `<ul class="tcs-list">${drafts.map(row => `<li><span class="name">${esc(row.customer)} · ${esc(row.date)}</span><span class="val">${esc(row.amountText)}</span><span class="sub">Mã giao dịch ${esc(row.reference)}</span></li>`).join('')}</ul>` : empty('Chưa có phiếu điền sẵn.')}
      <p class="tcs-empty">Bản thử không ghi phiếu vào sổ nợ. Thật ra team công nợ bấm ghi và phiếu trừ nợ cũ trước như sổ đang làm.</p>
      <h3>Tiền về chưa rõ của ai</h3>${unknown.length ? `<ul class="tcs-list">${unknown.map(item => `<li><span class="name">${esc(item.text)}</span><span class="val">${esc(item.amountText)}</span></li>`).join('')}</ul>` : empty('Không có tiền về nào chưa rõ.')}`;
  }
  function viewKetoan() {
    const state = ui.sim.state;
    const tabs = [
      ['so-tien', 'Sổ tiền', ''], ['ngoai-le', 'Hộp ngoại lệ', M.exceptions(state).length], ['cho-chuyen', 'Chờ chuyển', M.approvedWaiting(state).length],
      ['quy', 'Quỹ tiền mặt', M.cashWaiting(state).length], ['cong-no', 'Việc team công nợ', M.draftRows(state).length],
    ];
    const tab = ui.tab.ketoan;
    const accounts = M.accountsView(state);
    let body;
    if (tab === 'so-tien') {
      const fees = M.feeRows(state);
      body = `<div class="tcs-inline"><label class="tcs-field"><span>Tài khoản</span><select data-f="account"><option value="all">Tất cả tài khoản</option>${accounts.map(item => `<option value="${item.id}"${ui.account === item.id ? ' selected' : ''}>${esc(item.name)} · ${esc(item.balanceText)}</option>`).join('')}</select></label></div>
        ${ledgerRows(M.txnRows(state, ui.account === 'all' ? {} : { accountId: ui.account }))}
        ${fees.length ? `<h3>Phí ngân hàng đã tách</h3><ul class="tcs-list">${fees.map(row => `<li><span class="name">${esc(row.text)}</span></li>`).join('')}</ul>` : ''}`;
    } else if (tab === 'ngoai-le') body = exceptionHtml(state);
    else if (tab === 'cho-chuyen') body = waitingHtml(state);
    else if (tab === 'quy') body = cashHtml(state);
    else body = teamHtml(state);
    return `<section class="tcs-card" aria-label="Kế toán"><div class="tcs-tabs" role="tablist" aria-label="Việc của kế toán">${tabs.map(([id, label, count]) => `<button type="button" class="tcs-tab" role="tab" data-act="tab" data-id="${id}" aria-selected="${id === tab}">${esc(label)}${count !== '' && count > 0 ? ` <b>${count}</b>` : ''}</button>`).join('')}</div></section>
      <section class="tcs-card" aria-label="${esc(tabs.find(item => item[0] === tab)[1])}">${body}</section>`;
  }

  // ---- Tiền hàng: ví khách Trung Quốc ----
  function viewTienhang() {
    const state = ui.sim.state;
    const wallets = state.wallets.map(wallet => M.walletView(state, wallet.id));
    const current = wallets.find(item => item.id === ui.wallet) ?? wallets[0];
    const rows = M.walletStatement(state, current.id);
    const exchange = M.exchangeNote(state);
    const dir = M.directory(state);
    const expect = M.expectationRows(state);
    const list = wallets.map(item => `<button type="button" class="tcs-wbtn${item.negative ? ' neg' : ''}" data-act="wallet" data-id="${item.id}" aria-pressed="${item.id === current.id}"><span>${esc(item.name)}</span><b data-wallet="${item.id}">${esc(M.money(item.balance))}</b>
      <small>${item.negative ? 'Đang ứng: công ty ứng trước cho khách' : 'Số dư còn lại'}${item.pendingUsd > 0n ? ` · USD chờ bán ${esc(M.money(item.pendingUsd, 'USD'))}` : ''}</small>${item.alerts.map(text => `<small class="tcs-err">${esc(text)}</small>`).join('')}</button>`).join('');
    return `<div class="tcs-wallets"><section class="tcs-card" aria-label="Ví khách"><h2>Ví khách Trung Quốc</h2><div class="tcs-wlist">${list}</div></section>
      <section class="tcs-card tcs-stmt" aria-label="Sao kê ví"><h2>Sao kê ví ${esc(current.name)}</h2><div class="tcs-ledger">${rows.map(row => `<div class="tcs-row"><span class="time">${esc(row.clock)}</span><span class="who"><b>${esc(row.label)}</b>${row.detail ? `<small>${esc(row.detail)}</small>` : ''}</span>
        <span class="amt ${row.deltaText.startsWith('+') ? 'in' : row.deltaText.startsWith('−') ? 'out' : ''}">${row.deltaText ? `${esc(row.deltaText)}<small>Còn lại ${esc(row.afterText)}</small>` : `Còn lại ${esc(row.afterText)}`}</span></div>`).join('')}</div>
        ${exchange.length ? `<h3>Lần bán USD hôm nay</h3><ul class="tcs-list">${exchange.map(item => `<li><span class="name">${esc(item.usdText)} → ${esc(item.vndText)}</span><span class="sub">Tỷ giá ngân hàng ${esc(item.rateText)}; tỷ giá tính khách ${esc(item.customerRateText)}; chênh ${esc(item.gapText)} (chưa chốt tính là thu hay không).</span></li>`).join('')}</ul>` : ''}</section></div>
      <section class="tcs-card" aria-label="Tiền chờ về"><h2>Tiền chờ về</h2>${expect.length ? `<ul class="tcs-list">${expect.map(item => `<li data-expect="${esc(item.id)}"><span class="name">${esc(item.name)} · ${esc(item.amountText)}</span><span class="val">${esc(item.statusText)}</span>${item.note ? `<span class="sub">${esc(item.note)}</span>` : ''}</li>`).join('')}</ul>` : empty('Chưa ghi khoản nào đang chờ về.')}
        <div class="tcs-inline"><label class="tcs-field${badOf('wallet')}"><span>Khách</span><select data-f="expWallet"${describe('wallet')}>${options(dir.wallets, ui.f.expWallet, 'Chọn khách')}</select></label>${errOf('wallet')}
        <label class="tcs-field${badOf('amount')}"><span>Số đô la sẽ về</span><input type="text" inputmode="numeric" data-f="expAmount" value="${esc(ui.f.expAmount)}"${describe('amount')}></label>
        <label class="tcs-field"><span>Ghi chú</span><input type="text" data-f="expNote" value="${esc(ui.f.expNote)}"></label>${button('expect', 'Ghi tiền chờ về', { cls: 'primary' })}</div>${errOf('amount')}</section>`;
  }

  // ---- Nhân viên: đề nghị chi ----
  function requestDetail(view, state) {
    const bot = M.botFor(state, view.code);
    const wallet = view.wallet && (view.wallet.over || view.wallet.overLimit)
      ? `<p class="tcs-err">${view.wallet.over ? `Vượt số dư ví: ví ${esc(view.wallet.name)} còn ${esc(view.wallet.balanceText)}, cần sếp duyệt.` : ''}</p>` : '';
    return `<section class="tcs-card" aria-label="Chi tiết đề nghị"><div class="tcs-inline">${button('close-request', 'Về danh sách')}</div><h2 data-code="${esc(view.code)}">${esc(view.code)} · ${esc(view.typeText)}</h2>
      <p><b>${esc(view.amountText)}</b> cho ${esc(view.payee)} ${tag(view.statusText, view.status === 'da_khop' ? 'credit' : view.status === 'tu_choi' ? 'critical' : 'warning')}</p>
      <p class="tcs-step-text">Loại chi: ${esc(view.category)}${view.container ? ` · Container ${esc(view.container)}` : ''}${view.note ? ` · ${esc(view.note)}` : ''}${view.attachment ? ` · Ảnh: ${esc(view.attachment)} (ảnh giả)` : ''}</p>${wallet}
      <ul class="tcs-time-line" aria-label="Dòng thời gian">${view.steps.map(step => `<li class="${step.done ? 'done' : 'todo'}"><span class="mark" aria-hidden="true">${step.done ? '✓' : '○'}</span><b>${esc(step.label)}</b><span>${step.done ? 'Xong' : 'Chưa tới'}</span>${step.done ? `<span class="at">${esc(step.at)} · ${esc(step.by)}</span><span class="tx">${esc(step.text)}</span>` : ''}</li>`).join('')}</ul>
      ${view.reason ? `<p class="tcs-err">Lý do từ chối: ${esc(view.reason)}</p>` : ''}
      ${bot.length ? `<div class="tcs-botmsg"><b>Bot (mô phỏng) đã nhắn:</b><br>${bot.map(item => `${esc(item.clock)} → ${esc(item.to)}: ${esc(item.text)}`).join('<br>')}</div>` : ''}</section>
      <section class="tcs-card" aria-label="Trao đổi"><h2>Trao đổi</h2>${view.comments.length ? `<ul class="tcs-chat">${view.comments.map(item => `<li><small>${esc(item.clock)} · ${esc(item.by)}</small><br>${esc(item.text)}</li>`).join('')}</ul>` : empty('Chưa có trao đổi nào.')}
        <div class="tcs-inline"><label class="tcs-field${badOf('text')}"><span>Viết thêm</span><input type="text" data-f="comment" value="${esc(ui.f.comment)}"${describe('text')}></label>${button('comment', 'Gửi', { id: view.id, cls: 'primary' })}</div>${errOf('text')}</section>`;
  }
  function requestForm(state) {
    const dir = M.directory(state);
    const form = ui.f;
    const needWallet = form.type !== 'chi_thuong';
    const needPhoto = form.type !== 'ung_tien_mat';
    return `<section class="tcs-card" aria-label="Tạo đề nghị chi"><h2>Tạo đề nghị chi</h2><form class="tcs-form" id="request-form" novalidate>
      <div class="tcs-field${badOf('type')}"><span id="type-label">Loại chi</span><div class="tcs-kinds" role="group" aria-labelledby="type-label">${Object.entries(M.TYPES).map(([id, label]) => `<button type="button" class="tcs-kind" data-act="kind" data-id="${id}" aria-pressed="${form.type === id}">${esc(label)}</button>`).join('')}</div>${errOf('type')}</div>
      <label class="tcs-field${badOf('payee')}"><span>Người nhận</span><select data-f="payeeId"${describe('payee')}>${options(dir.payees, form.payeeId, 'Chọn người nhận')}</select></label>${errOf('payee')}
      ${needWallet ? `<label class="tcs-field${badOf('wallet')}"><span>Khách Trung Quốc</span><select data-f="walletId"${describe('wallet')}>${options(dir.wallets, form.walletId, 'Chọn khách')}</select></label>${errOf('wallet')}` : ''}
      <label class="tcs-field${badOf('amount')}"><span>Số tiền (đồng)</span><input type="text" inputmode="numeric" data-f="amountText" value="${esc(form.amountText)}" placeholder="Ví dụ 8.000.000"${describe('amount')}></label>${errOf('amount')}
      <label class="tcs-field"><span>Container (nếu có)</span><input type="text" data-f="container" value="${esc(form.container)}"></label>
      <label class="tcs-field"><span>Ghi chú</span><input type="text" data-f="note" value="${esc(form.note)}"></label>
      ${needPhoto ? `<div class="tcs-field${badOf('attachment')}"><label class="tcs-check"><input type="checkbox" data-f="attached"${form.attached ? ' checked' : ''}${describe('attachment')}> Đính kèm ảnh hóa đơn hoặc bảng kê (ảnh giả)</label>${errOf('attachment')}</div>` : ''}
      <div class="tcs-inline">${button('example', 'Điền ví dụ')}${button('create', 'Gửi đề nghị', { cls: 'primary' })}</div></form></section>`;
  }
  function viewNhanvien() {
    const state = ui.sim.state;
    const open = ui.openId ? M.requestView(state, ui.openId) : null;
    if (open) return requestDetail(open, state);
    const list = M.requestList(state);
    const tab = ui.tab.nhanvien;
    const tabs = `<div class="tcs-tabs" role="tablist" aria-label="Đề nghị chi"><button type="button" class="tcs-tab" role="tab" data-act="tab" data-id="ds" aria-selected="${tab === 'ds'}">Đề nghị của tôi${list.length ? ` <b>${list.length}</b>` : ''}</button>
      <button type="button" class="tcs-tab" role="tab" data-act="tab" data-id="tao" aria-selected="${tab === 'tao'}">Tạo đề nghị</button></div>`;
    if (tab === 'tao') return `<section class="tcs-card">${tabs}</section>${requestForm(state)}`;
    return `<section class="tcs-card">${tabs}</section><section class="tcs-card" aria-label="Đề nghị của tôi"><h2>Đề nghị của tôi</h2>${list.length ? list.map(view => `<button type="button" class="tcs-req" data-act="open-request" data-id="${esc(view.id)}">
      <span class="head"><b>${esc(view.code)}</b><span>${esc(view.typeText)}</span><b>${esc(view.amountText)}</b></span><small>${esc(view.payee)} · ${esc(view.statusText)}</small></button>`).join('') : empty('Chưa có đề nghị nào. Bấm "Tạo đề nghị".')}</section>`;
  }

  // ---- Vẽ và giữ chỗ đứng của bàn phím ----
  const keyOf = element => (element ? [element.dataset?.act, element.dataset?.id, element.dataset?.f, element.getAttribute?.('role')].join('|') : '');
  function render() {
    const focusKey = keyOf(document.activeElement);
    const caret = document.activeElement?.dataset?.f ? document.activeElement.selectionStart : null;
    renderRoles();
    renderScenario();
    $('#view').innerHTML = { sep: viewSep, ketoan: viewKetoan, tienhang: viewTienhang, nhanvien: viewNhanvien }[ui.role]();
    const note = $('#note');
    note.hidden = !ui.note;
    note.textContent = ui.note?.text ?? '';
    note.classList.toggle('bad', Boolean(ui.note?.bad));
    const target = [...document.querySelectorAll('[data-act],[data-f],[role=tab]')].find(element => keyOf(element) === focusKey);
    const invalid = $('#view [aria-invalid="true"]');
    (invalid ?? target)?.focus();
    if (!invalid && target && caret !== null && target.setSelectionRange) { try { target.setSelectionRange(caret, caret); } catch { /* ô không có con trỏ */ } }
    remember();
  }

  // ---- Thao tác ----
  const act = (op, args) => M.act(ui.sim, op, { time: stepTime(), ...args });
  function fail(result, fallback) {
    ui.errors = result.errors ?? {};
    say(result.error ?? fallback, true);
  }
  function jumpToStep(step) {
    if (!step) return;
    ui.role = step.role;
    if (step.role === 'ketoan') ui.tab.ketoan = step.tab;
    if (step.role === 'nhanvien') { ui.tab.nhanvien = step.tab === 'tao' ? 'tao' : 'ds'; ui.openId = null; }
  }
  const handlers = {
    role(id) { ui.role = id; ui.errors = {}; ui.note = null; ui.openId = null; ui.rejecting = null; },
    tab(id) { ui.tab[ui.role] = id; ui.errors = {}; ui.note = null; ui.openId = null; },
    goto() { jumpToStep(M.stepNow(ui.sim)); },
    next() {
      const step = M.stepNow(ui.sim);
      M.next(ui.sim);
      ui.errors = {};
      jumpToStep(step);
      say(step ? `Đã làm bước ${step.n}: ${step.title}.` : '');
      if (!step) ui.note = null;
    },
    back() { M.back(ui.sim); ui.errors = {}; ui.openId = null; ui.rejecting = null; jumpToStep(M.stepNow(ui.sim)); say('Đã lùi một bước.'); },
    reset() { M.reset(ui.sim); ui.errors = {}; ui.openId = null; ui.rejecting = null; ui.f = { ...ui.f, ...blankForm(), counted: '', comment: '', rejectReason: '' }; say('Đã đặt lại về đầu ngày.'); },
    approve(id) {
      const result = act('approveRequest', { id, role: 'sep' });
      if (result.ok) say(`Đã duyệt ${id}.`); else fail(result);
    },
    'reject-open'(id) { ui.rejecting = id; ui.errors = {}; ui.f.rejectReason = ''; },
    'reject-cancel'() { ui.rejecting = null; ui.errors = {}; },
    'reject-send'(id) {
      const result = act('rejectRequest', { id, role: 'sep', reason: ui.f.rejectReason });
      if (result.ok) { ui.rejecting = null; ui.errors = {}; say(`Đã từ chối ${id}.`); } else fail(result);
    },
    'approve-late'(id) {
      const result = act('approveLate', { flagId: id, role: 'sep' });
      if (result.ok) say('Đã duyệt bù, cờ đã gỡ.'); else fail(result);
    },
    attach(id) {
      const customerId = ui.f[`cust-${id}`] ?? '';
      const result = act('attachInflow', { txnId: id, customerId, remember: Boolean(ui.f[`rem-${id}`]), by: 'Kế toán' });
      if (result.ok) { ui.errors = {}; say(`Đã gắn khách. Phiếu thu điền sẵn ${result.draftId} đã hiện ở việc của team công nợ${result.remembered ? '; lần sau máy tự nhận người chuyển này' : ''}.`); }
      else { ui.errors = { [`attach-${id}`]: customerId ? result.error : 'Chọn khách trước khi gắn.' }; say('Chưa gắn được.', true); }
    },
    copy(id) {
      const view = M.requestView(ui.sim.state, id);
      try { const pending = navigator.clipboard?.writeText(view.transferText); if (pending?.catch) pending.catch(() => {}); } catch { /* không có clipboard thì vẫn hiện nội dung để chép tay */ }
      say(`Đã chép nội dung chuyển khoản: ${view.transferText}`);
    },
    transferred(id) {
      const result = act('markTransferred', { id });
      if (result.ok) say(`${id}: đã chuyển (mô phỏng). Chờ sao kê ngân hàng về để khớp.`); else fail(result);
    },
    handover(id) {
      const result = act('handOverCash', { id, photo: Boolean(ui.f[`photo-${id}`]) });
      if (result.ok) { ui.errors = {}; say(`${id}: đã giao tiền mặt, quỹ đã trừ, ví khách đã ghi ứng.`); } else { ui.errors = { [`photo-${id}`]: result.error }; say(result.error, true); }
    },
    count() {
      const result = act('countCash', { countedText: ui.f.counted });
      if (result.ok) { ui.errors = {}; ui.f.counted = ''; say(result.diff === 0n ? 'Kiểm quỹ: khớp.' : 'Kiểm quỹ: lệch, đã có cờ.', result.diff !== 0n); } else fail(result);
    },
    wallet(id) { ui.wallet = id; },
    expect() {
      const result = act('createExpectation', { walletId: ui.f.expWallet, amountText: ui.f.expAmount, note: ui.f.expNote });
      if (result.ok) { ui.errors = {}; ui.f.expAmount = ''; ui.f.expNote = ''; say('Đã ghi tiền chờ về.'); } else fail(result);
    },
    kind(id) { ui.f.type = id; ui.errors = {}; if (id === 'chi_thuong') ui.f.walletId = ''; },
    example() { ui.f = { ...ui.f, ...EXAMPLES[ui.f.type] }; ui.errors = {}; say('Đã điền ví dụ.'); },
    create() {
      const form = ui.f;
      const result = act('createRequest', { type: form.type, payeeId: form.payeeId, walletId: form.walletId, amountText: form.amountText, container: form.container, note: form.note,
        attachment: form.attached ? 'hoa-don-gia.png' : '', by: 'Nhân viên 1' });
      if (!result.ok) { fail(result); return; }
      ui.errors = {};
      ui.f = { ...ui.f, ...blankForm(), type: form.type };
      ui.tab.nhanvien = 'ds';
      ui.openId = result.id;
      say(`Đã gửi đề nghị ${result.code}. Bot (mô phỏng) đã báo sếp.`);
    },
    'open-request'(id) { ui.openId = id; ui.errors = {}; ui.note = null; },
    'close-request'() { ui.openId = null; ui.errors = {}; },
    comment(id) {
      const result = act('addComment', { id, text: ui.f.comment, by: 'Nhân viên 1' });
      if (result.ok) { ui.errors = {}; ui.f.comment = ''; say('Đã gửi lời trao đổi.'); } else fail(result);
    },
  };

  document.addEventListener('click', event => {
    const element = event.target.closest('[data-act]');
    if (!element || element.disabled) return;
    ui.note = null;
    handlers[element.dataset.act]?.(element.dataset.id);
    render();
  });
  const onField = event => {
    const element = event.target.closest('[data-f]');
    if (!element) return;
    const key = element.dataset.f;
    const value = element.type === 'checkbox' ? element.checked : element.value;
    if (key === 'account') { ui.account = value; if (event.type === 'change') render(); return; }
    ui.f[key] = value;
    if (event.type === 'change' && (element.tagName === 'SELECT' || element.type === 'checkbox')) { if (ui.errors) { ui.errors = {}; } render(); }
  };
  document.addEventListener('input', onField);
  document.addEventListener('change', onField);
  document.addEventListener('toggle', event => { if (event.target.tagName === 'DETAILS') ui.stepsOpen = event.target.open; }, true);
  document.addEventListener('submit', event => event.preventDefault());

  restore();
  render();
})();
