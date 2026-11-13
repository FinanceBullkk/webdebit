/* Sổ khách V7 bản live — Debit Note theo tháng công nợ (DEBIT-NOTE-01, mẫu v3 DEBIT-NOTE-02, specs/v7-debit-note.md).
 * Nút "Debit note" ở tiêu đề tháng mở hộp: bên trái điền thông tin chứng từ (số, ngày, bên phát hành, khách, thanh toán,
 * tỷ giá), bên phải là các điểm chặn/cảnh báo và bản xem trước. Xuất PDF (hộp in trình duyệt) và Excel đối chiếu.
 * Dòng chứng từ, tổng, quy đổi USD và kiểm tra do model dựng (ARCH-03). Không gửi lệnh nào; thông tin công ty và khách
 * người lập đã điền được trình duyệt này nhớ để lần sau điền sẵn (không lưu lên máy chủ).
 * Mẫu v4 (DEBIT-NOTE-03) dùng hộp khác theo luồng D: ba ô gõ tìm tên, Excel là nút chính, bảng có gì xuất nấy (phần cuối file). */
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

  // Safari trên iPhone tự phóng to chữ khi khối nội dung rộng hơn khung (trang A4 1123px trong khung 390px), cột giữ bề rộng px
  // nên chữ xuống dòng, đè lên nhau và phép chia trang đo sai. Mọi khung xem trước và khung in tắt việc này (DIEN-THOAI-DEBIT-01).
  const NO_INFLATE = 'html{-webkit-text-size-adjust:100%;text-size-adjust:100%}';
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
      target.write(`<!doctype html><html><head><meta charset="utf-8"><style>${NO_INFLATE}html,body{margin:0;background:#e6e9ee}body{padding:12px}${printer.SCREEN_CSS}.debit-root{zoom:.82}</style></head><body><div class="debit-root"></div></body></html>`);
      target.close();
    }
    target.querySelector('.debit-root').innerHTML = html;
    fitPreview();
  }
  // Điện thoại (DIEN-THOAI-DEBIT-01): thu bản xem trước vừa bề ngang khung để thấy cả trang, không cuộn ngang trong khung.
  // Màn rộng giữ cỡ cũ (v3 .82, v4 .6). Phép chia trang v4 đo ngoài .debit-root nên zoom không đổi số trang.
  const narrow = () => typeof matchMedia === 'function' && matchMedia('(max-width: 760px)').matches;
  function fitPreview() {
    const target = dialog.querySelector('.debit-preview')?.contentDocument, box = target?.querySelector('.debit-root');
    if (!box || !open) return;
    const [max, pagePx] = open.v4 ? [0.74, 1123] : [0.82, 1209];   // v4: A4 ngang 297mm; v3: trang kê 297mm + lề 0,9in
    const room = target.documentElement.clientWidth - 24;          // body padding 12px hai bên
    // v4 (luồng D) luôn vừa bề ngang khung, tối đa .74; v3 chỉ thu trên điện thoại như cũ.
    box.style.zoom = (open.v4 || narrow()) && room > 0 ? String(Math.min(max, Math.floor((room / pagePx) * 100) / 100)) : '';
  }
  addEventListener('resize', () => {
    if (!open) return;
    fitPreview();
    if (open.v4) dialog.querySelector('.debit-excel').textContent = narrow() ? 'Gửi Excel' : 'Tải Excel';
  });
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
  const tail = number => `…${(String(number ?? '').replace(/\D/g, '') || String(number ?? '')).slice(-4)}`;   // số viết có dấu cách: "1044 009 276"
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
  // TAI-KHOAN-COT-E-01: tài khoản ở cột E (THONG TIN NGAN HANG) cùng khối với công ty đứng tên là tài khoản của chính công ty đó.
  // Chọn công ty đứng tên thì "Nhận tiền vào" tự chọn tài khoản USD đầu tiên của khối; danh sách để tài khoản của khối lên đầu,
  // rồi tới các tài khoản ở tab TÀI KHOẢN USD (bỏ số trùng).
  const digitsOf = number => String(number ?? '').replace(/\D/g, '');
  function accountsFor(directory, issuerLabel) {
    const issuer = issuerOf(directory, issuerLabel);
    const own = (issuer?.accounts ?? []).map(item => ({ ...item, own: issuer.pickLabel }));
    const seen = new Set(own.map(item => digitsOf(item.account)));
    return [...own, ...accountsOf(directory).filter(item => !seen.has(digitsOf(item.account)))];
  }
  const ownDefault = issuer => {
    const own = issuer?.accounts ?? [];
    return (own.find(item => item.currency === 'USD') ?? own.find(item => !item.currency) ?? own[0])?.id ?? '';
  };
  // ---- Hộp v4 theo luồng D (DEBIT-NOTE-03, người dùng chốt 12/11/2026; specs/v7-debit-note.md Mẫu v4 → Luồng). ----
  // Người dùng làm debit note từng khách, khi cần; công ty đứng tên, tài khoản và công ty khách đổi theo từng lần; gửi file Excel
  // qua Zalo hoặc WeChat. Nên: ba ô gõ tìm tên (chọn sẵn như lần trước của sổ), Excel là nút chính, không có ô xác nhận
  // (bảng có gì xuất nấy); chỉ chặn khi không có chuyến, không đọc được cấu hình hoặc phép cộng của chứng từ sai.
  const fold = text => String(text ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();
  const dotted = value => (value === null || value === undefined ? '' : value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.'));
  // Gửi cho: tên, địa chỉ, MST của công ty khách theo Thông tin cty, in ở ô tên pháp lý của BILL TO (bỏ dấu khi in).
  const billText = item => (item ? [item.header?.name || item.company || item.name, item.header?.address,
    item.header?.tax_id ? `Tax ID ${item.header.tax_id}` : ''].filter(Boolean).join(', ') : '');
  const companyLine = item => [item.header?.name || item.company, item.header?.address].filter(Boolean).join(' · ');
  const PICKS = [['issuer', 'Đứng tên', 'Gõ tên công ty'], ['account', 'Nhận tiền vào', 'Gõ tên chủ tài khoản, ngân hàng'],
    ['bill', 'Gửi cho', 'Gõ tên công ty khách']];
  // Các lựa chọn của một ô: id, dòng chính, dòng phụ (trong danh sách), dòng xem lại (dưới ô), chữ để tìm.
  function pickOptions(kind) {
    const directory = open.directory, config = open.config ?? {};
    if (kind === 'account') {
      const pay = config.payment ?? {};
      const first = pay.account
        ? { id: '', main: pay.beneficiary || 'Tài khoản theo cấu hình', sub: [pay.bank, tail(pay.account), 'theo cấu hình'].filter(Boolean).join(' · ') }
        : { id: '', main: 'Chưa chọn', sub: 'Chứng từ in [Account no.]' };
      return [{ ...first, note: first.sub },
        ...accountsFor(directory, open.state.issuer).map(item => ({ id: item.id, main: item.beneficiary || item.label,
          sub: [item.bank, item.currency, tail(item.account), item.own ? `của ${item.own}` : ''].filter(Boolean).join(' · '),
          note: [item.bank, item.currency, `STK ${item.account}`, item.swift ? `SWIFT ${item.swift}` : ''].filter(Boolean).join(' · ') }))];
    }
    const companies = customersOf(directory).map(item => ({ id: item.pickLabel, main: item.pickLabel, sub: item.header?.name || item.company || '', item }));
    if (kind === 'issuer') {
      const company = config.company ?? {};
      return [{ id: '', main: company.name || 'Theo cấu hình', sub: 'Mặc định (theo cấu hình)', note: [company.name, company.address].filter(Boolean).join(' · ') },
        ...companies.map(option => ({ ...option, note: companyLine(option.item) }))];
    }
    return [{ id: '', main: 'Chưa chọn', sub: 'Chứng từ in [Customer legal name & address]', note: 'Chứng từ in [Customer legal name & address]' },
      ...companies.map(option => ({ ...option, note: billText(option.item) }))];
  }
  const chosen = kind => pickOptions(kind).find(option => option.id === open.state[kind]) ?? pickOptions(kind)[0];
  const searchIcon = '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="#3e5871" stroke-width="2"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>';
  function picksHtml() {
    const unread = open.directoryError ? `Chưa đọc được Thông tin cty: ${open.directoryError}` : open.directory?.available ? '' : 'Máy chủ chưa đọc Sheet thông tin khách hàng.';
    return PICKS.map(([kind, label, hint]) => `<div class="dn4-pick" data-kind="${kind}"><label for="dn4-${kind}">${label}</label>`
      + `<div class="dn4-combo"><input id="dn4-${kind}" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="dn4-${kind}-list" autocomplete="off" placeholder="${escape(hint)}">`
      + `${searchIcon}<div class="dn4-list" id="dn4-${kind}-list" role="listbox" aria-label="${label}" hidden></div></div><small class="dn4-note"></small></div>`).join('')
      + (unread ? `<p class="dn4-warn">${escape(unread)}</p>` : '')
      + `<label class="dn4-check"><input type="checkbox" name="accountStatus"${open.state.accountStatus ? ' checked' : ''}> In thêm ACCOUNT STATUS</label>`;
  }
  // Ô gõ tìm: bấm vào là thả cả danh sách (chữ trong ô xóa, chữ cũ thành gợi ý), gõ là lọc, bỏ dấu khi so; rời ô thì hiện lại lựa chọn.
  const comboOf = kind => dialog.querySelector(`.dn4-pick[data-kind="${kind}"]`);
  function showPick(kind) {
    const box = comboOf(kind), option = chosen(kind);
    box.querySelector('input').value = option.main;
    const issuer = kind === 'account' && !open.state.account ? issuerOf(open.directory, open.state.issuer) : null;
    box.querySelector('.dn4-note').textContent = issuer && !issuer.accounts?.length
      ? `${issuer.pickLabel} chưa có tài khoản ở cột ngân hàng trên Sheet. ${option.note}` : option.note;
  }
  function openList(kind, query = '') {
    const box = comboOf(kind), input = box.querySelector('input'), list = box.querySelector('.dn4-list');
    const words = fold(query).split(/\s+/).filter(Boolean);
    // Khớp ở dòng chính (tên công ty, tên chủ tài khoản) lên trước khớp ở ngân hàng, địa chỉ.
    const has = text => words.every(word => fold(text).includes(word));
    const found = pickOptions(kind).filter(option => has(`${option.main} ${option.sub} ${option.note}`));
    const options = [...found.filter(option => has(option.main)), ...found.filter(option => !has(option.main))];
    list.innerHTML = options.length ? options.map((option, index) => `<div class="dn4-opt${index === 0 ? ' is-active' : ''}" role="option" id="dn4-${kind}-${index}"`
      + ` data-id="${escape(option.id)}" aria-selected="${option.id === open.state[kind]}"><b>${escape(option.main)}</b><span>${escape(option.sub)}</span></div>`).join('')
      : '<div class="dn4-empty">Không có tên này trong Thông tin cty.</div>';
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    input.setAttribute('aria-activedescendant', options.length ? `dn4-${kind}-0` : '');
    fitList(kind);
  }
  // Điện thoại (DIEN-THOAI-DEBIT-01, bổ sung 13/11): danh sách thả xuống của ô dưới cùng bị thanh nút đáy và bàn phím che (đo khung iPhone 13
  // trên WebKit 13/11/2026: "Gửi cho" chỉ thấy 27/260px). Khi danh sách mở: ẩn xem trước và thanh nút (.is-picking), kéo ô lên
  // đầu vùng cuộn, danh sách cao vừa phần màn còn thấy trên bàn phím (visualViewport); đóng danh sách thì trả lại như cũ.
  let picking = null;
  function fitList(kind) {
    if (!narrow()) return;
    const panel = dialog.querySelector('.dn4'), form = dialog.querySelector('.dn4-form'), box = comboOf(kind);
    const input = box.querySelector('input'), list = box.querySelector('.dn4-list');
    if (picking !== kind) {
      picking = kind;
      panel.classList.add('is-picking');
      form.scrollTop += box.getBoundingClientRect().top - form.getBoundingClientRect().top;
    }
    const view = window.visualViewport, bottom = view ? view.offsetTop + view.height : innerHeight;
    list.style.maxHeight = `${Math.max(132, Math.floor(bottom - input.getBoundingClientRect().bottom - 10))}px`;
  }
  function unfitList(kind) {
    if (picking !== kind) return;
    picking = null;
    dialog.querySelector('.dn4')?.classList.remove('is-picking');
    comboOf(kind)?.querySelector('.dn4-list').style.removeProperty('max-height');
  }
  window.visualViewport?.addEventListener('resize', () => { if (open?.v4 && picking) fitList(picking); });
  function closeList(kind) {
    const box = comboOf(kind);
    if (!box) return;
    box.querySelector('.dn4-list').hidden = true;
    box.querySelector('input').setAttribute('aria-expanded', 'false');
    box.querySelector('input').removeAttribute('aria-activedescendant');
    unfitList(kind);
    showPick(kind);
  }
  function choose(kind, id) {
    const changed = open.state[kind] !== id;
    open.state[kind] = id;
    closeList(kind);
    if (narrow()) comboOf(kind).querySelector('input').blur();   // điện thoại: chọn xong thì cất bàn phím, hiện lại nút Gửi Excel
    if (kind === 'issuer' && changed) {   // đổi công ty đứng tên: tài khoản theo khối của công ty đó
      open.state.account = ownDefault(issuerOf(open.directory, id));
      showPick('account');
    }
    refreshV4();
  }
  function moveActive(kind, step) {
    const box = comboOf(kind), items = [...box.querySelectorAll('.dn4-opt')];
    if (!items.length) return;
    const at = Math.max(0, items.findIndex(item => item.classList.contains('is-active')));
    const next = items[(at + step + items.length) % items.length];
    items[at].classList.remove('is-active');
    next.classList.add('is-active');
    next.scrollIntoView({ block: 'nearest' });
    box.querySelector('input').setAttribute('aria-activedescendant', next.id);
  }
  const fileName = () => `${DebitNoteV4Xlsx.baseName(open.doc)}.xlsx`;
  // Dựng chứng từ theo lựa chọn, chia trang (đo trong khung xem trước) rồi vẽ; nút xuất chỉ khóa khi còn chặn.
  function refreshV4() {
    const s = open.state;
    const account = accountsFor(open.directory, s.issuer).find(item => item.id === s.account) ?? null;
    const bill = customersOf(open.directory).find(item => item.pickLabel === s.bill) ?? null;
    const config = effectiveConfig(open.config, account, issuerOf(open.directory, s.issuer));
    const form = { number: model.suggestNumber('HTH', open.monthKey), issueDate: '', accountStatus: s.accountStatus,
      customer: { nameEn: s.nameEn, nameZh: s.nameZh, legal: billText(bill) } };
    const doc = DebitNoteV4.fromLedger(ctx.snapshot ?? {}, open.monthKey, { model, feeTypes: ctx.feeTypes ?? [], feeColumnIds: ctx.feeColumnIds ?? [], config, form });
    const blocks = [...(open.configError ? [{ text: `Không đọc được cấu hình debit note: ${open.configError}` }] : []),
      ...DebitNoteV4.checks(doc).filter(item => item.level === 'block')];
    Object.assign(open, { doc, ready: blocks.length === 0 });
    const stop = dialog.querySelector('.debit-checks');
    stop.hidden = !blocks.length;
    stop.textContent = blocks.map(item => `Chưa xuất được: ${item.text}`).join(' ');
    for (const button of dialog.querySelectorAll('.debit-print, .debit-excel')) button.disabled = !open.ready;
    dialog.querySelector('.debit-excel').textContent = narrow() ? 'Gửi Excel' : 'Tải Excel';
    const missing = doc.rows.filter(row => !row.feeOnly && row.amount === null).length;
    dialog.querySelector('.debit-status').textContent = [`${doc.total.count} container`, `${dotted(doc.total.amount)} đ`,
      missing ? `${missing} chuyến chưa có giá` : ''].filter(Boolean).join(' · ');
    const target = dialog.querySelector('.debit-preview')?.contentDocument;
    if (target) {
      if (!target.querySelector('.debit-root')) {
        target.open();
        target.write(`<!doctype html><html lang="en"><head><meta charset="utf-8"><style>${NO_INFLATE}html,body{margin:0;background:#e6e9ee}body{padding:12px}`
          + '.debit-root{zoom:.6}.debit-root [data-page]{margin:0 auto 16px;box-shadow:0 1px 6px #0003}</style></head><body><div class="debit-root"></div></body></html>');
        target.close();
      }
      open.pages = DebitNoteV4.split(doc, target);
      target.querySelector('.debit-root').innerHTML = DebitNoteV4.pagesHtml(doc, open.pages);
      fitPreview();
    }
    write(V4_CUSTOMER_KEY, { customer: { nameEn: s.nameEn, nameZh: s.nameZh }, issuer: s.issuer, account: s.account, bill: s.bill, accountStatus: s.accountStatus === true });
  }
  // Tháng chọn được trong hộp: các tháng có chuyến lên chứng từ (chuyến web đã xác nhận, dòng chuyến của sổ gốc), mới trước.
  const monthsOnBook = () => {
    const snap = ctx.snapshot ?? {}, month = row => String(row.month ?? '').slice(0, 7);
    return [...new Set([...(snap.trips ?? []).filter(trip => !trip.deleted && trip.status === 'confirmed').map(month),
      ...(snap.legacy_rows ?? []).filter(row => row.kind === 'trip' && !row.current?.deleted).map(month)].filter(Boolean))];
  };
  function showV4(monthKey, opener, config, configError = '', directory = null, directoryError = '') {
    const remembered = read(V4_CUSTOMER_KEY), saved = remembered.customer ?? {};
    const name = DebitNoteV4.splitName(defaultDisplay());
    const companies = customersOf(directory);
    // Lựa chọn đã nhớ mà không còn trên Sheet thì coi như chưa chọn.
    const keep = (value, list, key) => (list.some(item => item[key] === value) ? value : '');
    const issuer = keep(remembered.issuer, companies, 'pickLabel');
    open = { v4: true, monthKey, opener, config, configError, directory, directoryError,
      state: { issuer, account: keep(remembered.account, accountsFor(directory, issuer), 'id'), bill: keep(remembered.bill, companies, 'pickLabel'),
        accountStatus: remembered.accountStatus === true, nameEn: saved.nameEn || name.en, nameZh: saved.nameZh ?? name.zh } };
    picking = null;
    const months = [...new Set([monthKey, ...monthsOnBook()])].sort().reverse();
    dialog.innerHTML = `<div class="debit-panel dn4"><header><div class="dn4-head"><h2>Debit note · ${escape(defaultDisplay())}</h2><small class="debit-status"></small></div>`
      + `<select class="dn4-month" aria-label="Tháng công nợ">${months.map(key => `<option value="${key}"${key === monthKey ? ' selected' : ''}>Tháng ${escape(monthLabel(key))}</option>`).join('')}</select>`
      + '<button type="button" class="debit-close" aria-label="Đóng"><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5l10 10M15 5L5 15"/></svg></button></header>'
      + `<div class="debit-main"><div class="dn4-side"><div class="dn4-form">${picksHtml()}</div><div class="dn4-done" hidden></div>`
      + '<div class="dn4-actions"><p class="debit-checks" role="status" hidden></p><button type="button" class="debit-excel dn4-primary">Tải Excel</button><button type="button" class="debit-print">PDF</button></div></div>'
      + '<div class="debit-body"><iframe class="debit-preview" title="Xem trước debit note"></iframe></div></div></div>';
    dialog.hidden = false;
    for (const [kind] of PICKS) showPick(kind);
    refreshV4();
    dialog.querySelector(open.ready ? '.debit-excel' : '.debit-close').focus();
  }
  function blobOf(bytes) { return new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }); }
  function downloadV4(bytes) {
    const url = URL.createObjectURL(blobOf(bytes));
    const link = document.createElement('a');
    link.href = url; link.download = fileName();
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  // Điện thoại: mở khung chia sẻ của máy (chọn Zalo, WeChat) nếu trình duyệt chia sẻ được file; không thì tải về như máy tính.
  async function sendV4() {
    if (!open.ready) return;
    const bytes = DebitNoteV4Xlsx.xlsx(open.doc), name = fileName();
    const file = narrow() && typeof File === 'function' ? new File([bytes], name, { type: blobOf(bytes).type }) : null;
    if (file && navigator.canShare?.({ files: [file] })) {
      try { await navigator.share({ files: [file], title: name }); showDone(true); }
      catch (error) { if (error?.name !== 'AbortError') { downloadV4(bytes); showDone(false); } }
      return;
    }
    downloadV4(bytes);
    showDone(false);
  }
  // Xuất xong: tên file và lời nhắn Việt/Trung để dán kèm file vào Zalo/WeChat.
  function messageOf(doc) {
    const [year, month] = doc.monthKey.split('-').map(Number);
    return `Gửi anh/chị debit note tháng ${month}/${year}: ${doc.total.count} container, tổng ${dotted(doc.total.amount)} đ.\n`
      + `您好，附上${year}年${month}月账单：${doc.total.count}个柜，合计${DebitNoteV4.money(doc.total.amount)}越南盾。`;
  }
  function showDone(shared) {
    const done = dialog.querySelector('.dn4-done');
    done.innerHTML = `<p class="dn4-done-title"><svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"/></svg>`
      + `${shared ? 'Đã mở khung gửi file' : 'Đã tải file Excel'}</p><p class="dn4-file">${escape(fileName())}</p><p class="dn4-msg">${escape(messageOf(open.doc))}</p>`
      + '<div class="dn4-done-actions"><button type="button" class="dn4-copy">Copy lời nhắn</button><button type="button" class="dn4-back">Sửa lại</button></div>';
    done.hidden = false;
    dialog.querySelector('.dn4-form').hidden = true;
    dialog.querySelector('.dn4-actions').hidden = true;
    done.querySelector('.dn4-copy').focus();
  }
  function hideDone() {
    dialog.querySelector('.dn4-done').hidden = true;
    dialog.querySelector('.dn4-form').hidden = false;
    dialog.querySelector('.dn4-actions').hidden = false;
    dialog.querySelector('.debit-excel').focus();
  }
  async function copyMessage(button) {
    const text = messageOf(open.doc);
    // Clipboard của trình duyệt có thể treo khi chờ quyền (Chrome không giao diện trên Linux) thay vì báo lỗi: chờ tối đa 0,8 giây.
    const wrote = await Promise.race([navigator.clipboard?.writeText(text).then(() => true, () => false) ?? Promise.resolve(false),
      new Promise(resolve => { setTimeout(() => resolve(false), 800); })]);
    if (!wrote) {   // trình duyệt chặn clipboard (trang không an toàn, chưa cho quyền): chép bằng ô ẩn
      const area = document.createElement('textarea');
      area.value = text; area.setAttribute('readonly', ''); area.style.cssText = 'position:fixed;left:-9999px';
      document.body.append(area); area.select(); document.execCommand?.('copy'); area.remove();
    }
    button.textContent = 'Đã copy';
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
    target.write(`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${escape(DebitNoteV4Xlsx.baseName(open.doc))}</title><style>${NO_INFLATE}${DebitNoteV4.PRINT_CSS}</style></head><body></body></html>`);
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
    frame.contentDocument.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escape(baseName())}</title><style>${NO_INFLATE}${printer.printCss(open.state.issuer.name)}</style></head>
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
    else if (event.target.closest('.debit-excel')) (open?.v4 ? sendV4 : download)();
    else if (event.target.closest('.debit-print')) (open?.v4 ? printV4 : print)();
    else if (event.target.closest('.dn4-copy')) copyMessage(event.target.closest('.dn4-copy'));
    else if (event.target.closest('.dn4-back')) hideDone();
    else if (open?.v4 && event.target.matches('.dn4-combo input') && comboOf(kindOf(event.target)).querySelector('.dn4-list').hidden) {
      event.target.value = '';   // bấm lại vào ô đang chọn (sau khi đã chọn một dòng) thì thả lại cả danh sách
      openList(kindOf(event.target));
    }
  });
  // Ô gõ tìm của hộp v4: bấm vào thả danh sách, gõ lọc, bấm (nhấn chuột) một dòng là chọn; rời ô là đóng.
  const kindOf = target => target?.closest?.('.dn4-pick')?.dataset.kind;
  dialog.addEventListener('focusin', event => {
    const kind = open?.v4 && event.target.matches('.dn4-combo input') && kindOf(event.target);
    if (!kind) return;
    event.target.placeholder = chosen(kind).main;
    event.target.value = '';
    openList(kind);
  });
  dialog.addEventListener('focusout', event => {
    const kind = open?.v4 && event.target.matches('.dn4-combo input') && kindOf(event.target);
    if (kind) closeList(kind);
  });
  dialog.addEventListener('mousedown', event => {
    const option = open?.v4 && event.target.closest('.dn4-opt');
    if (!option) return;
    event.preventDefault();   // giữ con trỏ ở ô, chọn trước khi ô mất chọn
    choose(kindOf(option), option.dataset.id);
  });
  dialog.addEventListener('input', event => {
    if (open?.v4) { const kind = event.target.matches('.dn4-combo input') && kindOf(event.target); if (kind) openList(kind, event.target.value); return; }
    if (!open || !event.target.closest('.debit-form, .debit-ack') || event.target.name === 'issuerCode') return;   // đổi công ty xử lý ở change
    if (event.target.name === 'number') event.target.dataset.touched = '1';
    (open.v4 ? refreshV4 : refresh)();
  });
  dialog.addEventListener('change', event => {
    if (!open) return;
    if (open.v4) {
      if (event.target.name === 'accountStatus') { open.state.accountStatus = event.target.checked; refreshV4(); }
      else if (event.target.matches('.dn4-month')) { open.monthKey = event.target.value; refreshV4(); }
      return;
    }
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
    const kind = open?.v4 && event.target.matches?.('.dn4-combo input') && kindOf(event.target);
    if (kind) {
      const list = comboOf(kind).querySelector('.dn4-list');
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); if (list.hidden) openList(kind); else moveActive(kind, event.key === 'ArrowDown' ? 1 : -1); return; }
      if (event.key === 'Enter') { event.preventDefault(); const active = list.querySelector('.dn4-opt.is-active'); if (!list.hidden && active) choose(kind, active.dataset.id); return; }
      if (event.key === 'Escape' && !list.hidden) { event.preventDefault(); closeList(kind); event.target.select(); return; }
    }
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key !== 'Tab') return;   // giữ Tab trong hộp
    const items = [...dialog.querySelectorAll('button, input, select, textarea')].filter(item => !item.closest('[hidden]'));
    const at = items.indexOf(document.activeElement);
    if (event.shiftKey && at <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
    else if (!event.shiftKey && at === items.length - 1) { event.preventDefault(); items[0].focus(); }
  });
  ctx.busyChecks.push(() => !dialog.hidden);
};
