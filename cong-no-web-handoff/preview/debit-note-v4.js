/* DEBIT-NOTE-03: Debit Note mẫu v4 — một trang A4 ngang (docs/debit-note-v4/SPEC.md, trang mẫu docs/debit-note-v4/reference/).
 * Bốn khối: đầu trang + BILL TO | DOCUMENT, bảng container + dòng Total (ô Amount là số phải trả), PAYMENT INFORMATION |
 * ACCOUNT STATUS. Module này dựng chứng từ từ sổ V7 (hoặc từ dữ liệu mẫu), chạy 6 phép kiểm của SPEC mục 7, dựng HTML từng
 * trang với CSS chép từ trang mẫu, và chia trang theo chiều cao đo thật (SPEC mục 6). Mọi số tiền là BigInt VND; không số nào
 * nhập tay. Thông tin công ty, ngân hàng và tên phí Anh/Trung lấy từ cấu hình (GET /api/v7/debit-note/config), không viết
 * cứng ở đây. */
const DebitNoteV4 = (() => {
  'use strict';
  const { esc } = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');

  // ---- Số, ngày, chữ ----
  const big = value => value === null || value === undefined || value === '' ? null : BigInt(String(value));
  const sum = list => list.reduce((total, value) => total + value, 0n);
  const group = digits => digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  // Ô tiền: phẩy ngăn nghìn, 0 là "–" (U+2013), số âm trong ngoặc; thiếu số để trống.
  function money(value) {
    if (value === null || value === undefined) return '';
    if (value === 0n) return '–';
    return value < 0n ? `(${group((-value).toString())})` : group(value.toString());
  }
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const isoDay = value => /^\d{4}-\d{2}-\d{2}/.test(String(value ?? '')) ? String(value).slice(0, 10) : null;
  const dateText = iso => isoDay(iso) ? `${iso.slice(8, 10)} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}` : null;
  const periodText = monthKey => `${MONTHS[Number(monthKey.slice(5, 7)) - 1]} ${monthKey.slice(0, 4)}`;
  // "02 Nov 2026" → "2026-11-02" (dữ liệu mẫu ghi ngày dạng in).
  function parseDateText(text) {
    const match = /^(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})$/.exec(String(text ?? '').trim());
    const month = match ? MONTHS.indexOf(match[2]) + 1 : 0;
    return month ? `${match[3]}-${String(month).padStart(2, '0')}-${match[1].padStart(2, '0')}` : null;
  }
  // Bản gửi khách không có tiếng Việt (SPEC 4.3): chữ Latin bỏ dấu, chữ Trung giữ nguyên.
  const latin = text => String(text ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
    .replace(/\s+/g, ' ').trim();
  // Tên hiển thị "FANYA 泛亚" → phần Latin và phần chữ Hán.
  function splitName(text) {
    const value = String(text ?? '').trim();
    const zh = (value.match(/[\p{Script=Han}（）]+/gu) ?? []).join(' ');
    return { en: latin(value.replace(/[\p{Script=Han}（）]+/gu, ' ')), zh };
  }
  const blank = value => value === null || value === undefined || String(value).trim() === '';
  const shown = (value, label) => blank(value) ? `[${label}]` : String(value);

  // ---- Cột phí ----
  // Cột của chứng từ theo cột phụ phí của sổ (PHU-PHI-01): Unit price, các cột riêng của sổ theo thứ tự sổ, rồi Khác.
  // Mỗi cột mang mã loại phí (SoKhachV7Model.dnFeeCode) để lấy tên Anh/Trung và bề rộng ở cấu hình.
  function feeLabel(config, code) {
    const item = config?.fees?.[code];
    return { code, en: item?.en ?? `[${code}]`, cn: item?.cn ?? '', width: Number.isInteger(item?.width) ? item.width : 84 };
  }

  // ---- Dựng chứng từ từ sổ V7 (bản GET đang vẽ) ----
  // form: { number, issueDate, customer: { nameEn, nameZh, legal, contact } } do người lập điền ở hộp.
  function fromLedger(ledger, monthKey, { model, feeTypes = [], feeColumnIds = [], config, form = {} }) {
    const month = row => String(row.month ?? '').slice(0, 7);
    const names = new Map(feeTypes.map(type => [Number(type.id), type.name]));
    const codeOfType = id => model.dnFeeCode(names.get(Number(id)));
    const own = [...new Set(feeColumnIds.map(codeOfType))].filter(code => code !== 'OTHER');
    const lineCode = line => own.includes(codeOfType(line.fee_type_id)) ? codeOfType(line.fee_type_id) : 'OTHER';
    const issues = [];
    const rows = [];
    const add = (info, lines, unitVnd, ledgerVnd, feeOnly) => {
      const cells = { LUMP_SUM: feeOnly ? null : unitVnd };
      for (const line of Array.isArray(lines) ? lines : []) {
        const code = lineCode(line);
        cells[code] = (cells[code] ?? 0n) + big(line.amount_vnd);
      }
      const place = model.dnPlace(info.origin, model.DN_PLACES), pod = model.dnPlace(info.destination, model.DN_PORTS);
      rows.push({ feeOnly, container: feeOnly ? '' : model.containerCheck(info.container).id, line: latin(info.carrier), shipper: latin(info.shipper),
        date: isoDay(info.date), place: { text: latin(place.text), cn: place.cn, known: place.known }, pod: { text: latin(pod.text), cn: pod.cn, known: pod.known },
        cells, amount: ledgerVnd, missingPrice: !feeOnly && unitVnd === null });
    };
    for (const row of ledger.legacy_rows ?? []) {
      if (row.kind !== 'trip' || month(row) !== monthKey || row.current?.deleted) continue;
      const cur = row.editable && row.current ? row.current : null, d = row.display ?? {};
      const unitVnd = cur ? big(cur.unit_price_vnd) : /^-?\d+$/.test(d.unit_price ?? '') ? big(d.unit_price) : null;
      const ledgerVnd = cur ? (cur.unit_price_vnd == null && cur.counted_vnd === '0' ? null : big(cur.counted_vnd))
        : (d.flags ?? []).includes('MISSING_PRICE') ? null : big(row.source_total_vnd);
      const info = cur ? { container: cur.container, carrier: cur.carrier, shipper: cur.shipper, date: cur.event_date, origin: cur.origin, destination: cur.destination }
        : { container: d.container, carrier: d.carrier, shipper: d.shipper, date: d.date, origin: d.from, destination: d.to };
      add(info, row.fee_lines, unitVnd, ledgerVnd, !info.container);
    }
    let pendingCount = 0;
    for (const trip of ledger.trips ?? []) {
      if (month(trip) !== monthKey || trip.deleted) continue;
      if (trip.status !== 'confirmed') { if (trip.status === 'pending_review') pendingCount++; continue; }
      const info = { container: trip.container, carrier: trip.carrier, shipper: trip.shipper, date: trip.event_date, origin: trip.origin, destination: trip.destination };
      add(info, trip.fee_lines, trip.is_missing_price ? null : big(trip.unit_price_vnd), trip.is_missing_price ? null : big(trip.amount_vnd), trip.is_fee_only === true);
    }
    const missing = rows.filter(row => row.missingPrice || row.amount === null).length;
    if (missing) issues.push({ level: 'block', text: `${missing} dòng chưa có giá hoặc số tiền.` });
    if (pendingCount) issues.push({ level: 'info', text: `${pendingCount} chuyến đang CHỜ KIỂM không lên chứng từ.` });

    const codes = ['LUMP_SUM', ...own, 'OTHER'];
    const doc = assemble({ rows, codes, config, monthKey, form });
    doc.issues.push(...issues);
    const places = [...new Set(doc.rows.filter(row => !row.feeOnly && !row.place.known).map(row => row.place.text || '(trống)'))];
    const ports = [...new Set(doc.rows.filter(row => !row.feeOnly && !row.pod.known).map(row => row.pod.text || '(trống)'))];
    if (places.length) doc.issues.push({ level: 'warn', text: `Nơi đóng hàng ngoài danh mục: ${places.join(', ')}.` });
    if (ports.length) doc.issues.push({ level: 'warn', text: `Cảng đến ngoài danh mục: ${ports.join(', ')}.` });
    const bad = doc.rows.filter(row => !row.feeOnly && !model.containerCheck(row.container).valid).map(row => row.container || '(trống)');
    if (bad.length) doc.issues.push({ level: 'warn', text: `Số container sai theo ISO 6346: ${bad.join(', ')}.` });

    // ACCOUNT STATUS: số của tháng lấy nguyên từ máy chủ (months[]). Opening = nợ trước tháng công nợ; Payments received =
    // phiếu thu, cấn trừ và điều chỉnh trong tháng = đã thu − (phát sinh của tháng − số của chứng từ); Outstanding = còn nợ
    // cuối tháng. Người dùng chốt 10/11/2026.
    const item = (ledger.months ?? []).find(row => month(row) === monthKey);
    if (!item) doc.issues.push({ level: 'block', text: 'Máy chủ chưa trả số nợ của tháng này (ACCOUNT STATUS).' });
    const opening = big(item?.prior_months_vnd), charges = big(item?.charges_vnd), received = big(item?.received_vnd), end = big(item?.end_of_month_vnd);
    const total = doc.total.amount;
    const adjustments = charges === null || total === null ? null : charges - total;
    const payments = received === null || adjustments === null ? null : received - adjustments;
    const inMonth = value => String(value ?? '').slice(0, 7) === monthKey;
    const paidDays = [...(ledger.receipts ?? []).filter(row => inMonth(row.date) && row.voided_by_event == null && row.void_reason == null),
      ...(ledger.outgoing_offsets ?? []).filter(row => inMonth(row.date) && row.voided_by_event == null && row.void_reason == null)]
      .map(row => isoDay(row.date)).filter(Boolean).sort();
    doc.account = { opening, openingDate: `${monthKey}-01`, thisNote: total, payments, paymentsDate: paidDays.at(-1) ?? null, outstanding: end,
      received, adjustments };
    if (adjustments !== null && adjustments !== 0n)
      doc.issues.push({ level: 'info', text: `Tháng có điều chỉnh ${money(adjustments)} đ (phát sinh của sổ khác số chứng từ): đã tính vào Payments received.` });
    return doc;
  }

  // ---- Dựng chứng từ từ dữ liệu mẫu (docs/debit-note-v4/data/*.json) ----
  const SAMPLE_KEYS = { lump_sum: 'LUMP_SUM', storage: 'STORAGE', generator_electricity: 'GENSET', overstay: 'OVERSTAY', hc_fee: 'HC_FEE' };
  function fromSample(data, config) {
    const rows = data.containers.map(item => ({ feeOnly: false, container: item.container_no, line: item.line, shipper: item.shipper,
      date: parseDateText(item.loading_date), place: { text: item.loading_place, cn: '', known: true }, pod: { text: item.pod, cn: '', known: true },
      cells: Object.fromEntries(Object.entries(SAMPLE_KEYS).map(([key, code]) => [code, big(item[key])])), amount: big(item.amount) }));
    const period = data.document.billing_period, monthKey = `${/\d{4}/.exec(period)[0]}-${String(MONTHS.indexOf(period.slice(0, 3)) + 1).padStart(2, '0')}`;
    const doc = assemble({ rows, codes: Object.values(SAMPLE_KEYS), config, monthKey,
      form: { number: data.document.debit_note_no, issueDate: data.document.issue_date,
        customer: { nameEn: data.customer.name_en, nameZh: data.customer.name_zh, legal: data.customer.legal_name_address, contact: data.customer.contact } } });
    const status = data.account_status;
    const opening = big(status.opening_balance), payments = big(status.payments_received), total = doc.total.amount;
    doc.account = { opening, openingDate: parseDateText(status.opening_date), thisNote: total, payments, paymentsDate: parseDateText(status.payments_date),
      outstanding: opening + total - payments, received: payments, adjustments: 0n };
    return doc;
  }

  // Phần chung: xếp dòng, đánh số, chọn cột (cột phí có ô khác 0 trên cả chứng từ mới hiện), cộng Total.
  function assemble({ rows, codes, config, monthKey, form }) {
    const key = row => row.date ?? '9999-99-99';
    const containers = rows.filter(row => !row.feeOnly).sort((a, b) => key(a).localeCompare(key(b)) || a.container.localeCompare(b.container));
    const extras = rows.filter(row => row.feeOnly).sort((a, b) => key(a).localeCompare(key(b)));
    const ordered = [...containers.map((row, index) => ({ ...row, no: index + 1 })), ...extras.map(row => ({ ...row, no: null }))];
    const used = codes.filter(code => code === 'LUMP_SUM' || ordered.some(row => row.cells[code] != null && row.cells[code] !== 0n));
    const columns = used.map(code => feeLabel(config, code));
    const columnTotal = code => sum(ordered.map(row => row.cells[code] ?? 0n));
    const amounts = ordered.map(row => row.amount);
    const customer = form.customer ?? {};
    const company = config?.company ?? {}, payment = config?.payment ?? {};
    return {
      monthKey, period: periodText(monthKey), number: form.number ?? null, issueDate: isoDay(form.issueDate), currency: 'VND',
      company: { name: company.name, address: company.address, taxId: company.tax_id, tel: company.tel, email: company.email },
      payment: { beneficiary: payment.beneficiary, bank: payment.bank, accountLabelEn: payment.account_label_en ?? 'Account',
        accountLabelCn: payment.account_label_cn ?? '账号', account: payment.account, swift: payment.swift },
      customer: { nameEn: latin(customer.nameEn), nameZh: String(customer.nameZh ?? '').trim(), legal: latin(customer.legal), contact: latin(customer.contact) },
      showPlaceCn: config?.show_place_cn === true,
      columns, rows: ordered,
      total: { cells: Object.fromEntries(used.map(code => [code, columnTotal(code)])), amount: amounts.some(value => value === null) ? null : sum(amounts),
        count: containers.length },
      account: null, issues: [],
    };
  }

  // ---- Sáu phép kiểm (SPEC mục 7). Sai phép nào thì không xuất; câu báo nêu phép và các con số. ----
  function checks(doc) {
    const out = [];
    const fail = (rule, text) => out.push({ level: 'block', rule, text: `Phép ${rule}: ${text}` });
    const visible = doc.columns.map(column => column.code);
    for (const row of doc.rows) {
      const parts = Object.values(row.cells).filter(value => value !== null);
      const expected = sum(parts);
      if (row.amount === null || row.amount !== expected)
        fail(1, `dòng ${row.no ?? row.date ?? ''} ${row.container || 'phí lẻ'}: Amount ${money(row.amount) || '(trống)'} ≠ ${visible.filter(code => row.cells[code] != null).map(code => money(row.cells[code])).join(' + ')} = ${money(expected)}.`);
      const hidden = Object.keys(row.cells).filter(code => !visible.includes(code) && row.cells[code] !== null && row.cells[code] !== 0n);
      if (hidden.length) fail(1, `dòng ${row.no ?? ''} ${row.container}: có phí ở cột không hiện (${hidden.join(', ')}).`);
    }
    const rowsTotal = doc.rows.some(row => row.amount === null) ? null : sum(doc.rows.map(row => row.amount));
    if (doc.total.amount === null || rowsTotal === null || doc.total.amount !== rowsTotal)
      fail(2, `Total Amount ${money(doc.total.amount) || '(trống)'} ≠ tổng Amount các dòng ${money(rowsTotal) || '(trống)'}.`);
    const columnsTotal = sum(visible.map(code => doc.total.cells[code] ?? 0n));
    for (const code of visible) {
      const real = sum(doc.rows.map(row => row.cells[code] ?? 0n));
      if (doc.total.cells[code] !== real) fail(3, `tổng cột ${code} in ${money(doc.total.cells[code])} ≠ cộng các dòng ${money(real)}.`);
    }
    if (doc.total.amount === null || columnsTotal !== doc.total.amount)
      fail(3, `tổng các cột phí ${money(columnsTotal)} ≠ Total Amount ${money(doc.total.amount) || '(trống)'}.`);
    const count = doc.rows.filter(row => !row.feeOnly).length;
    if (count !== doc.total.count) fail(4, `có ${count} dòng container nhưng dòng Total ghi ${doc.total.count} containers.`);
    const account = doc.account ?? {};
    if (account.thisNote === null || account.thisNote === undefined || account.thisNote !== doc.total.amount)
      fail(5, `This debit note ${money(account.thisNote) || '(trống)'} ≠ Total Amount ${money(doc.total.amount) || '(trống)'}.`);
    const parts = [account.opening, account.thisNote, account.payments, account.outstanding];
    if (parts.some(value => value === null || value === undefined) || account.opening + account.thisNote - account.payments !== account.outstanding)
      fail(6, `Opening ${money(account.opening) || '(trống)'} + This debit note ${money(account.thisNote) || '(trống)'} − Payments ${money(account.payments) || '(trống)'}`
        + ` ≠ Outstanding ${money(account.outstanding) || '(trống)'}.`);
    if (!doc.rows.length) out.push({ level: 'block', rule: 0, text: 'Tháng này không có chuyến nào để lập chứng từ.' });
    return [...doc.issues, ...out];
  }

  // ---- HTML (CSS chép từ docs/debit-note-v4/reference/*.html, SPEC mục 4–5) ----
  const FONT = "'Times New Roman', 'Liberation Serif', Tinos, SimSun, 'Songti SC', 'Noto Serif CJK SC', 'Noto Serif SC', serif";
  const PAGE = `width: 297mm; height: 210mm; box-sizing: border-box; background: #FFFFFF; font-family: ${FONT}; font-size: 12px; line-height: 18px; color: #1F2933; font-variant-numeric: tabular-nums; display: flex; flex-direction: column`;
  const GAP = '<div style="flex: 1 1 0; min-height: 10px; max-height: 20px"></div>';
  const GROW = '<div style="flex: 1 1 0; min-height: 10px"></div>';
  const RULE = '<div data-rule style="flex: none; margin: 0 40px; border-top: 2px solid #14304F"></div>';
  const LABEL = 'font-size: 11px; line-height: 16px; color: #5F6B7A';
  const SEC = 'font-weight: 700; letter-spacing: 0.6px';
  const NUM = 'text-align: right; padding-left: 8px';
  // Ô chữ: chữ dài xuống dòng trong ô (dòng cao lên, phép đo chia trang tính được), không tràn sang cột bên.
  const TEXT = 'min-width: 0; overflow-wrap: anywhere';
  // Cột chữ cố định (SPEC 4.2, không có B/L no. theo người dùng 10/11/2026): No., Container no., Line, Shipper (co giãn),
  // Loading date, Loading place, POD.
  const TEXT_COLUMNS = [['No.', '序号', '28px', 'text-align: right'], ['Container no.', '柜号', '94px', 'padding-left: 10px'], ['Line', '船东', '40px', ''],
    ['Shipper', '发货人', '1fr', ''], ['Loading date', '装柜日期', '74px', ''], ['Loading place', '装柜地点', '76px', ''], ['POD', '目的港', '66px', '']];
  const gridOf = doc => [...TEXT_COLUMNS.map(column => column[2]), ...doc.columns.map(column => `${column.width}px`), '84px'].join(' ');
  const moneySpan = (value, extra = '') => `<span style="${NUM}${value !== null && value < 0n ? '; margin-right: -0.333em' : ''}${extra}">${money(value)}</span>`;
  const pair = (label, value, bold = false) => `<div style="display: flex; align-items: baseline"><span style="width: 136px; flex: none; color: #5F6B7A">${esc(label)}</span>`
    + `<span${bold ? ' style="font-weight: 700"' : ''}>${esc(value)}</span></div>`;
  const section = (lines, body) => `<div style="display: grid; grid-template-columns: 120px 1fr; align-items: baseline"><div style="${LABEL}">${lines.map((line, index) =>
    `<div${line.bold ? ` style="${SEC}"` : ''}${index === 0 ? ' data-lab' : ''}>${esc(line.text)}</div>`).join('')}</div><div>${body}</div></div>`;
  const placeText = (doc, place) => `${esc(place.text)}${doc.showPlaceCn && place.cn ? `<br>${esc(place.cn)}` : ''}`;

  function letterhead(doc, compact) {
    const c = doc.company;
    const second = compact
      ? `Debit Note No. 账单号 ${shown(doc.number, 'Debit note no.')} · Bill to 客户 ${[shown(doc.customer.nameEn, 'Customer name'), doc.customer.nameZh].filter(Boolean).join(' ')} · Billing Period 账单期间 ${doc.period} · Currency 币种 ${doc.currency}`
      : `${shown(c.address, 'Company address')} · Tax ID 税号: ${shown(c.taxId, 'Tax ID')} · Tel 电话: ${shown(c.tel, 'Phone')} · Email 邮箱: ${shown(c.email, 'Email')}`;
    return `<div data-blk="LH" style="flex: none; padding: 24px 40px 0; margin-bottom: -4.29px"><div style="display: grid; grid-template-columns: 1fr auto; column-gap: 40px; align-items: baseline">`
      + `<div style="font-size: 16px; line-height: 32px; font-weight: 700; color: #14304F; letter-spacing: 1px">${esc(shown(c.name, 'Company name'))}</div>`
      + '<div style="font-size: 26px; line-height: 32px; font-weight: 700; color: #14304F; letter-spacing: 1px; text-align: right">DEBIT NOTE<span style="font-size: 16px; font-weight: 400; letter-spacing: 0; color: #5F6B7A; margin-left: 12px">账单</span></div>'
      + `<div style="grid-column: 1 / -1; ${LABEL}">${esc(second)}</div></div></div>`;
  }

  function info(doc) {
    const cust = doc.customer;
    const billTo = `<div style="font-weight: 700">${esc(shown(cust.nameEn, 'Customer name'))}${cust.nameZh ? `<span style="font-weight: 400"> ${esc(cust.nameZh)}</span>` : ''}</div>`
      + `<div>${esc(shown(cust.legal, 'Customer legal name & address'))}</div>`
      + `<div style="display: flex; align-items: baseline"><span style="width: 136px; flex: none; color: #5F6B7A">Attn 联系人</span><span>${esc(shown(cust.contact, 'Contact'))}</span></div>`;
    const documentInfo = pair('Debit Note No. 账单号', shown(doc.number, 'Debit note no.'), true) + pair('Issue Date 开单日期', dateText(doc.issueDate) ?? '[Issue date]')
      + pair('Billing Period 账单期间', doc.period) + pair('Currency 币种', doc.currency);
    return '<div data-blk="INFO" style="flex: none; padding: 0 40px; margin-top: -5.43px; margin-bottom: -4.95px"><div style="display: grid; grid-template-columns: 1fr 1fr; column-gap: 40px; align-items: start">'
      + section([{ text: 'BILL TO', bold: true }, { text: '客户' }], billTo) + section([{ text: 'DOCUMENT', bold: true }, { text: '单据信息' }], documentInfo) + '</div></div>';
  }

  function table(doc, rows, withTotal) {
    const grid = gridOf(doc);
    const head = `<div data-reftop style="display: grid; grid-template-columns: ${grid}; align-items: end; padding: 6px 8px 6px 0; background: #E6EBF2; font-size: 11px; line-height: 16px; color: #14304F">`
      + [...TEXT_COLUMNS.map(([en, cn, , style]) => [en, cn, style]), ...doc.columns.map(column => [column.en, column.cn, NUM]), ['Amount', '金额', NUM]]
        .map(([en, cn, style]) => `<span style="${style}"><span style="display: block; font-weight: 700; white-space: nowrap">${esc(en)}</span><span style="display: block">${esc(cn)}</span></span>`).join('')
      + '</div>';
    const line = (row, last) => {
      const border = last ? '' : '; border-bottom: 1px solid #B8C0CB';
      const lead = row.feeOnly
        ? `<span style="text-align: right"></span><span style="grid-column: 2 / 5; padding-left: 10px; ${TEXT}">Additional charge · 附加费用</span><span>${esc(dateText(row.date) ?? '')}</span><span></span><span></span>`
        : `<span style="text-align: right">${row.no}</span><span style="padding-left: 10px; ${TEXT}">${esc(row.container)}</span><span style="${TEXT}">${esc(row.line)}</span>`
          + `<span style="${TEXT}">${esc(row.shipper)}</span><span>${esc(dateText(row.date) ?? '')}</span><span style="${TEXT}">${placeText(doc, row.place)}</span><span style="${TEXT}">${placeText(doc, row.pod)}</span>`;
      return `<div data-row style="display: grid; grid-template-columns: ${grid}; align-items: baseline; padding: 3px 8px 3px 0${border}">${lead}`
        + `${doc.columns.map(column => moneySpan(row.cells[column.code] ?? (row.feeOnly && column.code === 'LUMP_SUM' ? null : 0n))).join('')}${moneySpan(row.amount)}</div>`;
    };
    const body = rows.map((row, index) => line(row, index === rows.length - 1)).join('');
    const total = withTotal
      ? `<div data-total style="display: grid; grid-template-columns: ${grid}; align-items: baseline; padding: 5px 8px 5px 0; border-top: 1px solid #14304F; border-bottom: 3px double #14304F; font-weight: 700">`
        + `<span style="grid-column: 1 / ${TEXT_COLUMNS.length + 1}">Total, ${doc.total.count} container${doc.total.count === 1 ? '' : 's'}<span style="font-weight: 400"> · 合计</span></span>`
        + `${doc.columns.map(column => moneySpan(doc.total.cells[column.code])).join('')}${moneySpan(doc.total.amount, '; color: #14304F')}</div>`
      : '';
    return `<div data-blk="TABLE" style="flex: none; padding: 0 40px; margin-top: 0.00px; margin-bottom: 0.00px">${head}${body}${total}</div>`;
  }

  function bottom(doc) {
    const p = doc.payment, a = doc.account ?? {};
    const payment = pair('Beneficiary 收款人', shown(p.beneficiary, 'Beneficiary')) + pair('Bank 开户银行', shown(p.bank, 'Bank'))
      + pair(`${p.accountLabelEn} ${p.accountLabelCn}`, shown(p.account, 'Account no.'), true) + pair('SWIFT Code SWIFT代码', shown(p.swift, 'SWIFT code'))
      + pair('Payment Ref. 汇款附言', shown(doc.number, 'Debit note no.'));
    const status = (label, date, value, extra = '') => `<div style="display: grid; grid-template-columns: 1fr 80px 110px; align-items: baseline; padding-right: 8px${extra}">`
      + `<span>${label}</span><span>${esc(date)}</span>${moneySpan(value).replace(`padding-left: 8px`, 'padding-left: 0')}</div>`;
    const paid = a.payments === null || a.payments === undefined ? null : -a.payments;
    const account = status('Opening balance · 期初余额', dateText(a.openingDate) ?? '', a.opening)
      + status('This debit note · 本期账单', dateText(doc.issueDate) ?? '[Issue date]', a.thisNote)
      + status('Payments received · 本期已收款', dateText(a.paymentsDate) ?? '', paid)
      + status('Outstanding balance<span style="font-weight: 400"> · 未结余额</span>', '', a.outstanding, '; margin-top: 3px; padding-top: 3px; border-top: 1px solid #5F6B7A; font-weight: 700');
    return '<div data-blk="BOTTOM" style="flex: none; padding: 0 40px; margin-top: -5.43px; margin-bottom: -4.95px"><div style="display: grid; grid-template-columns: 1fr 1fr; column-gap: 40px; align-items: start">'
      + section([{ text: 'PAYMENT', bold: true }, { text: 'INFORMATION', bold: true }, { text: '付款信息' }], payment)
      + section([{ text: 'ACCOUNT STATUS', bold: true }, { text: '账户情况' }, { text: 'For reference only' }, { text: '仅供参考' }], account) + '</div></div>';
  }

  function footer(doc, last, page, pages) {
    const left = last ? `Debit Note ${shown(doc.number, 'Debit note no.')} · Billing queries 账单查询: ${shown(doc.company.email, 'Email')}`
      : `Debit Note ${shown(doc.number, 'Debit note no.')} · Continued on next page · 续下页`;
    return '<div style="flex: none; padding: 0 40px 24px"><div data-rule data-footer style="display: flex; justify-content: space-between; align-items: baseline; padding-top: 8px; border-top: 1px solid #B8C0CB; font-size: 11px; line-height: 16px; color: #5F6B7A">'
      + `<span>${esc(left)}</span><span>Page ${page} of ${pages}</span></div></div>`;
  }

  // Một trang theo loại (SPEC mục 6): single | first | middle | last. measure = true: chiều cao tự nhiên để đo.
  function pageHtml(doc, kind, rows, page = 1, pages = 1, { measure = false } = {}) {
    const full = kind === 'single' || kind === 'first', last = kind === 'single' || kind === 'last';
    const style = measure ? PAGE.replace('height: 210mm', 'height: auto') : PAGE;
    return `<div data-page="${kind}" style="${style}"><div style="height: 6px; flex: none; background: #14304F"></div>${letterhead(doc, !full)}${GAP}${RULE}${GAP}`
      + `${full ? `${info(doc)}${GAP}` : ''}${table(doc, rows, last)}${GROW}${last ? `${bottom(doc)}${GAP}` : ''}${footer(doc, last, page, pages)}</div>`;
  }

  // ---- Chia trang theo chiều cao đo thật (SPEC mục 6) ----
  // fits(kind, rows) → true khi trang loại kind với các dòng đó vừa một trang. Dòng Total luôn đi cùng ít nhất 3 dòng.
  function paginate(rows, fits) {
    if (fits('single', rows)) return [{ kind: 'single', rows }];
    const pages = [];
    let at = 0, kind = 'first';
    for (;;) {
      const rest = rows.slice(at);
      if (kind !== 'first' && (rest.length <= 1 || fits('last', rest))) { pages.push({ kind: 'last', rows: rest }); break; }
      const cand = rest.slice(0, Math.max(rest.length - 3, 1));
      let low = 1, high = cand.length;   // số dòng lớn nhất vừa trang, tìm nhị phân; một dòng không vừa vẫn xếp một dòng
      while (low < high) {
        const mid = Math.ceil((low + high) / 2);
        if (fits(kind, cand.slice(0, mid))) low = mid; else high = mid - 1;
      }
      pages.push({ kind, rows: rest.slice(0, low) });
      at += low; kind = 'middle';
    }
    return pages;
  }

  // Đo trong một document thật (khung in hoặc trang Playwright): dựng trang ở chiều cao tự nhiên rồi so với 210mm.
  function measurer(target) {
    const box = target.createElement('div');
    box.style.cssText = 'position:absolute;left:-10000px;top:0;visibility:hidden';
    target.body.append(box);
    box.innerHTML = '<div style="height: 210mm"></div>';
    const limit = box.firstChild.getBoundingClientRect().height;
    return {
      fits(doc, kind, rows) {
        box.innerHTML = pageHtml(doc, kind, rows, 99, 99, { measure: true });
        return box.firstChild.getBoundingClientRect().height <= limit + 0.5;
      },
      done() { box.remove(); },
    };
  }
  function split(doc, target) {
    const measure = measurer(target);
    try { return paginate(doc.rows, (kind, rows) => measure.fits(doc, kind, rows)); } finally { measure.done(); }
  }

  const PRINT_CSS = '@page{size:A4 landscape;margin:0} html,body{margin:0;width:297mm} body{margin:0}'
    + ' [data-page]{break-after:page;-webkit-print-color-adjust:exact;print-color-adjust:exact;overflow:hidden} [data-page]:last-child{break-after:auto}';
  const pagesHtml = (doc, pages) => pages.map((page, index) => pageHtml(doc, page.kind, page.rows, index + 1, pages.length)).join('');
  // Cả tài liệu để in/xuất PDF: các trang đã chia, mỗi trang một tờ A4 ngang.
  const documentHtml = (doc, pages, title = '') => `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(title)}</title>`
    + `<style>${PRINT_CSS}</style></head><body>${pagesHtml(doc, pages)}</body></html>`;

  return { fromLedger, fromSample, checks, pageHtml, paginate, measurer, split, pagesHtml, documentHtml, money, dateText, periodText, latin, splitName,
    PRINT_CSS, TEXT_COLUMNS };
})();
if (typeof module !== 'undefined') module.exports = DebitNoteV4;
