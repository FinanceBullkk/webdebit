/* Sổ khách V7 bản live — Debit Note theo tháng công nợ (DEBIT-NOTE-01, mẫu v3 DEBIT-NOTE-02, specs/v7-debit-note.md).
 * Nút "Debit note" ở tiêu đề tháng mở hộp: bên trái điền thông tin chứng từ (số, ngày, bên phát hành, khách, thanh toán,
 * tỷ giá), bên phải là các điểm chặn/cảnh báo và bản xem trước. Xuất PDF (hộp in trình duyệt) và Excel đối chiếu.
 * Dòng chứng từ, tổng, quy đổi USD và kiểm tra do model dựng (ARCH-03). Không gửi lệnh nào; thông tin công ty và khách
 * người lập đã điền được trình duyệt này nhớ để lần sau điền sẵn (không lưu lên máy chủ). */
(window.SoKhachV7LiveParts ??= {}).debit = ctx => {
  'use strict';
  const { root, model, live, customerId, escape, monthLabel } = ctx;
  if (typeof document.createElement !== 'function') return;   // trang thử không có DOM thật
  const printer = DebitNotePrint, writer = DebitNoteXlsx;     // debit-note-print.js, debit-note-xlsx.js (và debit-note-v4*.js) nạp trước
  // Bên phát hành chọn được; chỉ điền sẵn thông tin công khai, phần còn lại người lập điền một lần, trình duyệt nhớ.
  const ISSUERS = [
    { code: 'HTH', label: 'HTH Logistics', issuer: { name: 'HTH LOGISTICS DV TM CO.,LTD',
      address: '21/20/15 Le Cong Phep Street, An Lac Ward, Ho Chi Minh City, Vietnam', email: 'hth.logs@gmail.com' } },
    { code: 'NSX', label: 'Nông Sản Xanh', issuer: { name: 'GREEN AGRICULTURAL PRODUCTS EXPORT TRADING CO.,LTD', taxId: '0319147624' } },
    { code: 'DN', label: 'Công ty khác', issuer: {} },
  ];
  const PROFILE_KEY = 'debit-note:v3:profiles', CUSTOMER_KEY = `debit-note:v3:customer:${customerId}`;
  const read = key => { try { return JSON.parse(localStorage.getItem(key) ?? 'null') ?? {}; } catch { return {}; } };
  const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* không nhớ được cũng không sao */ } };
  const blankIssuer = { name: '', address: '', taxId: '', tel: '', email: '' };
  const blankPayment = { beneficiary: '', address: '', bank: '', bankAddress: '', account: '', currency: 'USD', swift: '' };
  const profile = code => {
    const saved = read(PROFILE_KEY)[code] ?? {};
    return { issuer: { ...blankIssuer, ...ISSUERS.find(item => item.code === code)?.issuer, ...saved.issuer }, payment: { ...blankPayment, ...saved.payment } };
  };

  const dialog = document.createElement('div');
  dialog.className = 'debit-dialog';
  dialog.hidden = true;
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-label', 'Debit note');
  document.body.append(dialog);
  let open = null;   // { note, monthKey, opener, state }

  const todayIso = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  // Dịch vụ mặc định theo sổ: cảng = Sea freight, bộ = Road freight; sầu riêng = Durian.
  function defaultService() {
    const row = live.customerRow?.(customerId) ?? {};
    const mode = row.transport_mode === 'BO' ? 'Road freight 陆运' : 'Sea freight 海运';
    const goods = /sau ?rieng/.test(String(row.commodity ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()) ? 'Durian 榴莲' : '';
    return [mode, goods].filter(Boolean).join(' · ');
  }
  function defaultDisplay() {
    const row = live.customerRow?.(customerId);
    return String(row?.display_name ?? row?.name ?? live.customerName(customerId) ?? '').split(' · ')[0];
  }

  const field = (name, label, value, { type = 'text', area = false, hint = '' } = {}) => `<label class="debit-field"><span>${escape(label)}</span>${area
    ? `<textarea name="${name}" rows="2">${escape(value)}</textarea>`
    : `<input name="${name}" type="${type}" value="${escape(value)}"${type === 'number' ? ' min="0" max="365" step="1"' : ''} autocomplete="off">`}${hint ? `<small>${escape(hint)}</small>` : ''}</label>`;
  function form(state) {
    const { issuer, buyer, payment, usd } = state;
    return `<form class="debit-form" novalidate>
      <fieldset><legend>Chứng từ</legend>${field('number', 'Số debit note', state.number)}${field('issueDate', 'Ngày phát hành', state.issueDate, { type: 'date' })}
        ${field('paymentDays', 'Số ngày thanh toán', String(state.paymentDays), { type: 'number', hint: 'Hạn thanh toán = ngày phát hành + số ngày.' })}
        ${field('service', 'Dịch vụ (in trên chứng từ)', state.service)}${field('vatNo', 'Số hóa đơn GTGT (nếu có)', state.vatNo)}</fieldset>
      <fieldset><legend>Bên phát hành</legend><label class="debit-field"><span>Công ty</span><select name="issuerCode">${ISSUERS.map(item =>
        `<option value="${item.code}"${item.code === state.issuerCode ? ' selected' : ''}>${escape(item.label)}</option>`).join('')}</select></label>
        ${field('issuer.name', 'Tên', issuer.name)}${field('issuer.address', 'Địa chỉ', issuer.address, { area: true })}${field('issuer.taxId', 'Mã số thuế', issuer.taxId)}
        ${field('issuer.tel', 'Điện thoại', issuer.tel)}${field('issuer.email', 'Email', issuer.email)}</fieldset>
      <fieldset><legend>Khách (BILL TO)</legend>${field('buyer.display', 'Tên hiển thị', buyer.display)}${field('buyer.legal', 'Tên pháp lý', buyer.legal)}
        ${field('buyer.address', 'Địa chỉ', buyer.address, { area: true })}${field('buyer.attn', 'Người nhận (Attn)', buyer.attn)}</fieldset>
      <fieldset><legend>Thanh toán</legend>${field('payment.beneficiary', 'Người nhận tiền', payment.beneficiary)}${field('payment.address', 'Địa chỉ người nhận', payment.address, { area: true })}
        ${field('payment.bank', 'Ngân hàng', payment.bank)}${field('payment.bankAddress', 'Địa chỉ ngân hàng', payment.bankAddress, { area: true })}
        ${field('payment.account', 'Số tài khoản', payment.account)}<label class="debit-field"><span>Loại tiền tài khoản</span><select name="payment.currency">${['USD', 'VND'].map(code =>
          `<option${code === payment.currency ? ' selected' : ''}>${code}</option>`).join('')}</select></label>${field('payment.swift', 'SWIFT', payment.swift)}</fieldset>
      <fieldset><legend>Quy đổi USD</legend><label class="debit-check"><input type="checkbox" name="usd.on"${usd.on ? ' checked' : ''}> In thêm số tiền quy đổi USD</label>
        ${field('usd.rate', 'Tỷ giá VND/USD', usd.rate, { hint: 'Một tỷ giá cho cả chứng từ, quy đổi một lần trên tổng.' })}${field('usd.source', 'Nguồn tỷ giá', usd.source)}
        ${field('usd.date', 'Ngày lấy tỷ giá', usd.date, { type: 'date' })}</fieldset></form>`;
  }
  // Đọc form → thông tin chứng từ (chỉ chữ; số tiền không nhập ở đây).
  function readForm() {
    const state = { issuer: {}, buyer: {}, payment: {}, usd: {} };
    for (const input of dialog.querySelectorAll('.debit-form [name]')) {
      const value = input.type === 'checkbox' ? input.checked : input.value.trim();
      const [head, tail] = input.name.split('.');
      if (tail) state[head][tail] = value; else state[head] = value;
    }
    state.paymentDays = /^\d+$/.test(state.paymentDays) ? Number(state.paymentDays) : NaN;
    return state;
  }

  const LEVEL = { block: 'Chặn', warn: 'Cảnh báo', info: 'Lưu ý' };
  function refresh() {
    const state = readForm();
    const checks = model.debitNoteChecks(open.note, state);
    const blocks = checks.filter(item => item.level === 'block').length, warns = checks.filter(item => item.level === 'warn').length;
    const ack = dialog.querySelector('.debit-ack input');
    const official = blocks === 0 && (warns === 0 || ack?.checked === true);
    open.state = state; open.official = official;
    dialog.querySelector('.debit-checks').innerHTML = checks.length ? checks.map(item => `<li class="is-${item.level}"><b>${LEVEL[item.level]}:</b> ${escape(item.text)}</li>`).join('')
      : '<li class="is-ok">Đủ điều kiện phát hành.</li>';
    const ackLabel = dialog.querySelector('.debit-ack');
    ackLabel.hidden = blocks > 0 || warns === 0;
    dialog.querySelector('.debit-status').textContent = `${open.note.containerCount} container · ${official ? 'bản chính thức' : 'bản nháp'}`;
    dialog.querySelector('.debit-print').textContent = official ? 'In / Lưu PDF' : 'In bản nháp';
    dialog.querySelector('.debit-excel').textContent = official ? 'Tải Excel' : 'Excel bản nháp';
    preview(printer.html(open.note, state, { model, draft: !official }));
    remember(state);
  }
  // Bản xem trước nằm trong khung riêng để CSS của trang sổ không lọt vào; chỉ thay nội dung nên giữ được chỗ đang cuộn.
  function preview(html) {
    const target = dialog.querySelector('.debit-preview')?.contentDocument;
    if (!target) return;
    if (!target.querySelector('.debit-root')) {
      target.open();
      target.write(`<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#e6e9ee}body{padding:12px}${printer.SCREEN_CSS}.dn{zoom:.82}</style></head><body><div class="debit-root"></div></body></html>`);
      target.close();
    }
    target.querySelector('.debit-root').innerHTML = html;
  }
  function remember(state) {
    write(PROFILE_KEY, { ...read(PROFILE_KEY), [state.issuerCode]: { issuer: state.issuer, payment: state.payment } });
    write(CUSTOMER_KEY, { issuerCode: state.issuerCode, buyer: state.buyer, paymentDays: state.paymentDays, service: state.service, usd: { on: state.usd.on, source: state.usd.source } });
  }

  function showV3(monthKey, opener) {
    const note = model.debitNote(ctx.snapshot ?? {}, monthKey, ctx.feeTypes ?? []);
    const saved = read(CUSTOMER_KEY);
    const issuerCode = ISSUERS.some(item => item.code === saved.issuerCode) ? saved.issuerCode : 'HTH';
    const company = profile(issuerCode);
    const state = { number: model.suggestNumber(issuerCode, monthKey), issueDate: todayIso(), paymentDays: Number.isInteger(saved.paymentDays) ? saved.paymentDays : 15,
      service: saved.service || defaultService(), vatNo: '', issuerCode, issuer: company.issuer, payment: company.payment,
      buyer: { display: defaultDisplay(), legal: '', address: '', attn: '', ...saved.buyer },
      usd: { on: saved.usd?.on === true, rate: '', source: saved.usd?.source ?? '', date: todayIso() } };
    open = { note, monthKey, opener };
    dialog.innerHTML = `<div class="debit-panel"><header><h2>Debit note tháng ${escape(monthLabel(monthKey))}<small class="debit-status"></small></h2>
      <button type="button" class="debit-print">In / Lưu PDF</button><button type="button" class="debit-excel">Tải Excel</button><button type="button" class="debit-close">Đóng</button></header>
      <div class="debit-main">${form(state)}<div class="debit-side"><div class="debit-review" role="status"><ul class="debit-checks"></ul>
        <label class="debit-ack" hidden><input type="checkbox"> Tôi đã xem các cảnh báo, phát hành bản chính thức</label></div>
        <div class="debit-body"><iframe class="debit-preview" title="Xem trước debit note"></iframe></div></div></div></div>`;
    dialog.hidden = false;
    refresh();
    dialog.querySelector('.debit-print').focus();
  }
  // ---- Mẫu v4 (DEBIT-NOTE-03, docs/debit-note-v4/SPEC.md): một trang A4 ngang, 6 phép kiểm, sai thì không xuất. ----
  // Mẫu nào do cấu hình máy chủ quyết (GET /api/v7/debit-note/config, mặc định v3); ?debit=v4 hoặc ?debit=v3 trên địa chỉ trang
  // để xem thử mẫu kia. Tên phí lấy từ cấu hình; công ty phát hành (đầu trang) và tài khoản nhận tiền chọn từ Thông tin cty (THONG-TIN-CTY-01) hoặc theo cấu hình.
  const V4_CUSTOMER_KEY = `debit-note:v4:customer:${customerId}`;
  let configLoad = null;
  // THONG-TIN-CTY-01: danh bạ khách và tài khoản nhận tiền đọc từ Sheet thông tin khách hàng (GET /api/v7/company-info).
  const ACCOUNT_CN = { USD: '美元账号', VND: '越南盾账号', CNY: '人民币账号', EUR: '欧元账号' };
  const tail = number => `…${String(number ?? '').slice(-4)}`;
  const accountsOf = directory => (directory?.available ? directory.accounts : []);
  // Mỗi khách một nhãn để chọn: tên (cột A hoặc dòng đầu khối); trùng tên thì kèm dòng bắt đầu trên Sheet.
  const customersOf = directory => {
    const list = directory?.available ? directory.customers : [];
    const count = new Map();
    for (const item of list) count.set(item.name, (count.get(item.name) ?? 0) + 1);
    return list.map(item => ({ ...item, pickLabel: count.get(item.name) > 1 ? `${item.name} · dòng ${item.rows[0]}` : item.name }));
  };
  // Chữ Việt bỏ dấu khi in đầu trang (chứng từ không in tiếng Việt, DEBIT-NOTE-03).
  const plain = value => (value == null ? value : String(value).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D'));
  // Công ty phát hành chọn từ Thông tin cty thay cả đầu trang (tên, địa chỉ, MST, điện thoại, email) cho riêng chứng từ này;
  // tài khoản chọn ở hộp thay phần ngân hàng. Không chọn thì theo cấu hình máy chủ.
  function effectiveConfig(config, account, issuer) {
    let out = config;
    if (issuer) {
      const h = issuer.header ?? {};
      out = { ...out, company: { name: plain(h.name || issuer.company), address: plain(h.address), tax_id: plain(h.tax_id), tel: plain(h.tel), email: h.email } };
    }
    if (!account) return out;
    const payment = { ...(out?.payment ?? {}), beneficiary: account.beneficiary, bank: account.bank, account: account.account, swift: account.swift };
    if (account.currency) Object.assign(payment, { account_label_en: `${account.currency} Account`, account_label_cn: ACCOUNT_CN[account.currency] ?? '账号' });
    return { ...out, payment };
  }
  const issuerOf = (directory, label) => (label ? customersOf(directory).find(item => item.pickLabel === label) ?? null : null);
  function formV4(state) {
    const c = state.customer, directory = open.directory, accounts = accountsOf(directory);
    const company = open.config?.company?.name;
    const pickHint = open.directoryError ? `Chưa đọc được Thông tin cty: ${open.directoryError}` : directory?.available
      ? `Chọn một công ty thì đầu trang in tên, địa chỉ, MST, điện thoại, email theo Thông tin cty. Để trống thì theo cấu hình${company ? ` (${company})` : ''}.`
      : 'Máy chủ chưa đọc Sheet thông tin khách hàng.';
    const configured = open.config?.payment?.account;
    const accountOptions = [`<option value="">${escape(configured ? `Theo cấu hình máy chủ (${tail(configured)})` : 'Chưa chọn')}</option>`,
      ...accounts.map(item => `<option value="${escape(item.id)}"${item.id === state.account ? ' selected' : ''}>${escape([item.label, item.beneficiary, tail(item.account)].filter(Boolean).join(' · '))}</option>`)];
    return `<form class="debit-form" novalidate>
      <fieldset><legend>Chứng từ</legend>${field('number', 'Số debit note', state.number)}${field('issueDate', 'Ngày phát hành', state.issueDate,
        { type: 'date', hint: 'Để trống thì in [Issue date] (đang chờ team chốt).' })}</fieldset>
      <fieldset><legend>Công ty phát hành (đầu trang)</legend><label class="debit-field"><span>Chọn từ Thông tin cty</span><input name="issuer" list="debit-company-list"
        value="${escape(state.issuer)}" placeholder="Gõ tên công ty" autocomplete="off"${customersOf(directory).length ? '' : ' disabled'}><datalist id="debit-company-list">${
        customersOf(directory).map(item => `<option value="${escape(item.pickLabel)}"></option>`).join('')}</datalist><small>${escape(pickHint)}</small></label></fieldset>
      <fieldset><legend>Khách (BILL TO)</legend>${field('customer.nameEn', 'Tên khách (chữ Latin)', c.nameEn)}${field('customer.nameZh', 'Tên tiếng Trung', c.nameZh)}
        ${field('customer.legal', 'Tên pháp lý và địa chỉ', c.legal, { area: true, hint: 'Để trống thì in [Customer legal name & address].' })}
        ${field('customer.contact', 'Người liên hệ (Attn)', c.contact)}</fieldset>
      <fieldset><legend>Tài khoản nhận tiền</legend><label class="debit-field"><span>Tài khoản in trên chứng từ</span><select name="account">${accountOptions.join('')}</select>
        <small>Danh sách theo tab Thông tin cty.</small></label></fieldset>
      <p class="debit-note-v4">Tên phí lấy theo cấu hình máy chủ. Chữ tiếng Việt được bỏ dấu khi in.</p></form>`;
  }
  function readFormV4() {
    const state = { customer: {} };
    for (const input of dialog.querySelectorAll('.debit-form [name]')) {
      const [head, tail] = input.name.split('.');
      if (tail) state[head][tail] = input.value.trim(); else state[head] = input.value.trim();
    }
    return state;
  }
  // Dựng chứng từ, kiểm, chia trang (đo trong khung xem trước) rồi vẽ; nút xuất khóa khi còn phép kiểm sai.
  function refreshV4() {
    const state = readFormV4();
    const account = accountsOf(open.directory).find(item => item.id === state.account) ?? null;
    const config = effectiveConfig(open.config, account, issuerOf(open.directory, state.issuer));
    const doc = DebitNoteV4.fromLedger(ctx.snapshot ?? {}, open.monthKey, { model, feeTypes: ctx.feeTypes ?? [], feeColumnIds: ctx.feeColumnIds ?? [],
      config, form: state });
    const checks = [...(open.configError ? [{ level: 'block', text: `Không đọc được cấu hình debit note: ${open.configError}` }] : []),
      ...(config?.payment?.account ? [] : [{ level: 'warn', text: 'Chưa chọn tài khoản nhận tiền: chứng từ in [Account no.].' }]), ...DebitNoteV4.checks(doc)];
    const blocks = checks.filter(item => item.level === 'block').length, warns = checks.filter(item => item.level === 'warn').length;
    const ack = dialog.querySelector('.debit-ack input');
    const ready = blocks === 0 && (warns === 0 || ack?.checked === true);
    Object.assign(open, { state, doc, ready });
    dialog.querySelector('.debit-checks').innerHTML = checks.length ? checks.map(item => `<li class="is-${item.level}"><b>${LEVEL[item.level]}:</b> ${escape(item.text)}</li>`).join('')
      : '<li class="is-ok">Đủ 6 phép kiểm, xuất được.</li>';
    dialog.querySelector('.debit-ack').hidden = blocks > 0 || warns === 0;
    for (const button of dialog.querySelectorAll('.debit-print, .debit-excel')) button.disabled = !ready;
    const target = dialog.querySelector('.debit-preview')?.contentDocument;
    if (target) {
      if (!target.querySelector('.debit-root')) {
        target.open();
        target.write('<!doctype html><html lang="en"><head><meta charset="utf-8"><style>html,body{margin:0;background:#e6e9ee}body{padding:12px}'
          + '.debit-root{zoom:.6}.debit-root [data-page]{margin:0 auto 16px;box-shadow:0 1px 6px #0003}</style></head><body><div class="debit-root"></div></body></html>');
        target.close();
      }
      open.pages = DebitNoteV4.split(doc, target);
      target.querySelector('.debit-root').innerHTML = DebitNoteV4.pagesHtml(doc, open.pages);
    }
    const count = open.pages?.length ?? 0;
    dialog.querySelector('.debit-status').textContent = `${doc.total.count} container · ${count} trang · ${blocks ? 'chưa xuất được' : 'mẫu v4'}`;
    write(V4_CUSTOMER_KEY, { customer: state.customer, issuer: state.issuer ?? '', account: state.account ?? '' });
  }
  function showV4(monthKey, opener, config, configError = '', directory = null, directoryError = '') {
    const remembered = read(V4_CUSTOMER_KEY), saved = remembered.customer ?? {};
    const name = DebitNoteV4.splitName(defaultDisplay());
    // Tài khoản đã nhớ mà không còn trên Sheet thì coi như chưa chọn.
    const account = accountsOf(directory).some(item => item.id === remembered.account) ? remembered.account : '';
    const state = { number: model.suggestNumber('HTH', monthKey), issueDate: '', issuer: remembered.issuer ?? '', account,
      customer: { nameEn: saved.nameEn || name.en, nameZh: saved.nameZh ?? name.zh, legal: saved.legal ?? '', contact: saved.contact ?? '' } };
    open = { v4: true, monthKey, opener, config, configError, directory, directoryError };
    dialog.innerHTML = `<div class="debit-panel"><header><h2>Debit note tháng ${escape(monthLabel(monthKey))}<small class="debit-status"></small></h2>
      <button type="button" class="debit-print">In / Lưu PDF</button><button type="button" class="debit-excel">Tải Excel</button><button type="button" class="debit-close">Đóng</button></header>
      <div class="debit-main">${formV4(state)}<div class="debit-side"><div class="debit-review" role="status"><ul class="debit-checks"></ul>
        <label class="debit-ack" hidden><input type="checkbox"> Tôi đã xem các cảnh báo, cho xuất</label></div>
        <div class="debit-body"><iframe class="debit-preview" title="Xem trước debit note"></iframe></div></div></div></div>`;
    dialog.hidden = false;
    refreshV4();
    dialog.querySelector('.debit-close').focus();
  }
  function downloadV4() {
    if (!open.ready) return;
    const bytes = DebitNoteV4Xlsx.xlsx(open.doc);
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
    const link = document.createElement('a');
    link.href = url; link.download = `${DebitNoteV4Xlsx.baseName(open.doc)}.xlsx`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  // In bằng khung ẩn: chia trang lại trong chính khung in (cùng bề ngang 297mm), khổ A4 ngang lề 0 theo @page.
  function printV4() {
    if (!open.ready) return;
    const frame = document.createElement('iframe');
    frame.className = 'debit-print-frame';
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;width:297mm;height:210mm;border:0;right:0;bottom:0;visibility:hidden';
    document.body.append(frame);
    const target = frame.contentDocument;
    target.open();
    target.write(`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${escape(DebitNoteV4Xlsx.baseName(open.doc))}</title><style>${DebitNoteV4.PRINT_CSS}</style></head><body></body></html>`);
    target.close();
    const pages = DebitNoteV4.split(open.doc, target);
    target.body.innerHTML = DebitNoteV4.pagesHtml(open.doc, pages);
    frame.contentWindow.focus();
    frame.contentWindow.print();
    setTimeout(() => frame.remove(), 60000);
  }
  async function show(monthKey, opener) {
    configLoad ??= ctx.api.readDebitConfig();
    let config = null, configError = '';
    try { config = await configLoad; } catch (error) { configError = error.message; configLoad = null; }
    const asked = new URLSearchParams(location.search).get('debit');
    const template = ['v3', 'v4'].includes(asked) ? asked : config?.template ?? 'v3';
    if (template !== 'v4') { showV3(monthKey, opener); return; }
    // Danh bạ đọc lại mỗi lần mở hộp (Sheet sửa xong thì lần mở sau thấy); lỗi thì hộp vẫn dùng như trước.
    let directory = null, directoryError = '';
    try { directory = await (ctx.api.readCompanyInfo?.() ?? null); } catch (error) { directoryError = error.message; }
    showV4(monthKey, opener, config ?? {}, configError, directory, directoryError);
  }

  function close() {
    const opener = open?.opener;
    dialog.hidden = true; dialog.innerHTML = ''; open = null;
    const again = opener?.dataset?.month && root.querySelector(`.debit-open[data-month="${CSS.escape(opener.dataset.month)}"]`);
    (again || opener)?.focus?.();
  }
  const baseName = () => writer.baseName(open.state, open.monthKey, !open.official);
  function download() {
    const bytes = writer.xlsx(open.note, open.state, { model, draft: !open.official });
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
    const link = document.createElement('a');
    link.href = url; link.download = `${baseName()}.xlsx`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  // In bằng khung ẩn để không bị chặn cửa sổ bật lên; chọn "Lưu dưới dạng PDF" để ra file PDF (tên file = tiêu đề).
  function print() {
    const frame = document.createElement('iframe');
    frame.className = 'debit-print-frame';
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;width:0;height:0;border:0;right:0;bottom:0';
    document.body.append(frame);
    frame.contentDocument.open();
    frame.contentDocument.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escape(baseName())}</title><style>${printer.printCss(open.state.issuer.name)}</style></head>
      <body>${printer.html(open.note, open.state, { model, draft: !open.official })}</body></html>`);
    frame.contentDocument.close();
    printer.fitSummary(frame.contentDocument);
    frame.contentWindow.focus();
    frame.contentWindow.print();
    setTimeout(() => frame.remove(), 60000);
  }
  root.addEventListener('click', event => {
    const button = event.target.closest('.debit-open');
    if (button) show(button.dataset.month, button);
  });
  dialog.addEventListener('click', event => {
    if (event.target.closest('.debit-close') || event.target === dialog) close();
    else if (event.target.closest('.debit-excel')) (open?.v4 ? downloadV4 : download)();
    else if (event.target.closest('.debit-print')) (open?.v4 ? printV4 : print)();
  });
  dialog.addEventListener('input', event => {
    if (!open || !event.target.closest('.debit-form, .debit-ack') || event.target.name === 'issuerCode') return;   // đổi công ty xử lý ở change
    if (event.target.name === 'number') event.target.dataset.touched = '1';
    (open.v4 ? refreshV4 : refresh)();
  });
  dialog.addEventListener('change', event => {
    if (!open) return;
    if (open.v4) { if (event.target.closest('.debit-form, .debit-ack')) refreshV4(); return; }
    if (event.target.name === 'issuerCode') {   // đổi bên phát hành: điền lại thông tin công ty và gợi ý số mới
      const company = profile(event.target.value);
      for (const [group, values] of Object.entries(company))
        for (const [key, value] of Object.entries(values)) { const input = dialog.querySelector(`[name="${group}.${key}"]`); if (input) input.value = value ?? ''; }
      const number = dialog.querySelector('[name="number"]');
      if (!number.dataset.touched) number.value = model.suggestNumber(event.target.value, open.monthKey);
    }
    if (event.target.closest('.debit-form, .debit-ack')) refresh();
  });
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key !== 'Tab') return;   // giữ Tab trong hộp
    const items = [...dialog.querySelectorAll('button, input, select, textarea')].filter(item => !item.closest('[hidden]'));
    const at = items.indexOf(document.activeElement);
    if (event.shiftKey && at <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
    else if (!event.shiftKey && at === items.length - 1) { event.preventDefault(); items[0].focus(); }
  });
  ctx.busyChecks.push(() => !dialog.hidden);
};
