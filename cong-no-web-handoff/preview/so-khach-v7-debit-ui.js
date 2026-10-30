/* Sổ khách V7 bản live — Debit Note theo tháng công nợ (DEBIT-NOTE-01, mẫu v3 DEBIT-NOTE-02, specs/v7-debit-note.md).
 * Nút "Debit note" ở tiêu đề tháng mở hộp: bên trái điền thông tin chứng từ (số, ngày, bên phát hành, khách, thanh toán,
 * tỷ giá), bên phải là các điểm chặn/cảnh báo và bản xem trước. Xuất PDF (hộp in trình duyệt) và Excel đối chiếu.
 * Dòng chứng từ, tổng, quy đổi USD và kiểm tra do model dựng (ARCH-03). Không gửi lệnh nào; thông tin công ty và khách
 * người lập đã điền được trình duyệt này nhớ để lần sau điền sẵn (không lưu lên máy chủ). */
(window.SoKhachV7LiveParts ??= {}).debit = ctx => {
  'use strict';
  const { root, model, live, customerId, escape, monthLabel } = ctx;
  if (typeof document.createElement !== 'function') return;   // trang thử không có DOM thật
  const printer = DebitNotePrint, writer = DebitNoteXlsx;     // debit-note-print.js, debit-note-xlsx.js nạp trước
  // Bên phát hành chọn được; chỉ điền sẵn thông tin công khai, phần còn lại người lập điền một lần, trình duyệt nhớ.
  const ISSUERS = [
    { code: 'HTH', label: 'HTH Logistics', issuer: { name: 'HTH LOGISTICS DV TM CO.,LTD',
      address: '20/21/15 Le Cong Phap, An Lac Ward, Binh Tan District, Ho Chi Minh City, Vietnam', email: 'hth.logs@gmail.com' } },
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

  function show(monthKey, opener) {
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
    else if (event.target.closest('.debit-excel')) download();
    else if (event.target.closest('.debit-print')) print();
  });
  dialog.addEventListener('input', event => {
    if (!open || !event.target.closest('.debit-form, .debit-ack') || event.target.name === 'issuerCode') return;   // đổi công ty xử lý ở change
    if (event.target.name === 'number') event.target.dataset.touched = '1';
    refresh();
  });
  dialog.addEventListener('change', event => {
    if (!open) return;
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
