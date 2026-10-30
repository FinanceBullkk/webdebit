/* DEBIT-NOTE-02: bản in Debit Note theo mẫu v3 sếp duyệt 30/10/2026 (specs/v7-debit-note.md). Trang 1 tóm tắt khổ A4 dọc,
 * các trang chi tiết container khổ A4 ngang, chung một file khi "Lưu dưới dạng PDF". Chỉ dựng HTML/CSS từ chứng từ do
 * SoKhachV7Model.debitNote dựng và thông tin chứng từ người lập điền; mọi con số lấy từ model, ở đây chỉ định dạng. */
const DebitNotePrint = (() => {
  const { esc: escape } = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  // Tiền VND: dấu phẩy ngăn nghìn, 0 là "–", số âm trong ngoặc đơn, thiếu số để trống.
  function money(value) {
    if (value === null || value === undefined) return '';
    const text = value.toString();
    const digits = (text.startsWith('-') ? text.slice(1) : text).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    if (digits === '0') return '–';
    return text.startsWith('-') ? `(${digits})` : digits;
  }
  const containersText = count => `${count} container${count === 1 ? '' : 's'} · ${count}个柜`;
  const cssText = text => String(text ?? '').replace(/[\\"]/g, '\\$&').replace(/[\r\n]+/g, ' ');

  // Các giá trị suy ra từ chứng từ, dùng chung cho bản in và file Excel.
  function derive(note, doc, model) {
    const rate = doc.usd?.on ? model.parseRate(doc.usd.rate) : null;
    const cents = rate === null ? null : model.usdCents(note.totalVnd, rate);
    return { dueDate: model.addDays(doc.issueDate, doc.paymentDays), rate, cents, usd: model.usdText(cents),
      rateText: rate === null ? '' : `${money(rate)} VND/USD`, words: model.vndInWords(note.totalVnd) ?? '' };
  }

  function summaryPage(note, doc, d, model) {
    const issuer = doc.issuer ?? {}, buyer = doc.buyer ?? {}, pay = doc.payment ?? {};
    const contact = [issuer.taxId ? `Tax ID 税号: ${issuer.taxId}` : '', issuer.tel ? `Tel 电话: ${issuer.tel}` : '', issuer.email ? `Email 邮箱: ${issuer.email}` : '']
      .filter(Boolean).join('  ·  ');
    const info = [['Debit Note No.', '账单号', doc.number, true], ['Issue Date', '开单日期', model.dnDate(doc.issueDate)], ['Billing Period', '账单期间', note.period],
      ['Payment Terms', '付款条件', Number.isInteger(doc.paymentDays) ? `Net ${doc.paymentDays} days` : ''], ['Service', '服务', doc.service],
      ['VAT Invoice No.', '发票号码', doc.vatNo]];
    if (d.rate !== null) info.push(['Exchange Rate', '汇率', d.rateText]);
    const ports = note.summary.map(item => `<tr><td>${escape(item.port || '–')}</td><td class="num">${item.containers}</td><td class="num">${money(item.lumpSumVnd)}</td><td class="num">${money(item.otherVnd)}</td></tr>`).join('');
    const extra = note.additionalVnd !== null || note.charges.length
      ? `<tr><td>Additional charges  附加费用</td><td class="num">–</td><td class="num">–</td><td class="num">${money(note.additionalVnd)}</td></tr>` : '';
    const account = pay.currency === 'VND' ? ['VND Account', '越南盾账号'] : ['USD Account', '美元账号'];
    const payRows = [['Beneficiary', '收款人', pay.beneficiary, true], ['Address', '地址', pay.address], ['Bank', '开户银行', pay.bank], ['Bank Address', '银行地址', pay.bankAddress],
      [...account, pay.account, true], ['SWIFT Code', 'SWIFT代码', pay.swift, true], ['Payment Ref.', '汇款附言', doc.number, true]];
    const email = issuer.email ? escape(issuer.email) : '';
    return `<section class="dn-page dn-summary">
      <div class="dn-bar"></div>
      <div class="dn-top"><div><div class="dn-issuer">${escape(issuer.name)}</div><div class="dn-muted">${escape(issuer.address)}</div><div class="dn-muted">${escape(contact)}</div></div>
        <div class="dn-docname"><div class="dn-title">DEBIT NOTE</div><div class="dn-muted">账单</div></div></div>
      <div class="dn-two">
        <div class="dn-billto"><div class="dn-sec">BILL TO  ·  客户</div><div class="dn-cust">${escape(buyer.display)}</div>
          <div>${escape(buyer.legal)}</div><div class="dn-pre">${escape(buyer.address)}</div>${buyer.attn ? `<div class="dn-attn">Attn 联系人: ${escape(buyer.attn)}</div>` : ''}</div>
        <div class="dn-docinfo"><div class="dn-sec">DOCUMENT  ·  单据信息</div><table>${info.map(([en, cn, value, bold]) =>
          `<tr><th>${en}  <span>${cn}</span></th><td${bold ? ' class="b"' : ''}>${escape(value)}</td></tr>`).join('')}</table></div>
      </div>
      <div class="dn-due"><div><div class="dn-sec">AMOUNT DUE  ·  应付金额</div><div class="dn-amount">${money(note.totalVnd) || '—'} VND</div>
          ${d.usd ? `<div class="dn-usd">≈ ${d.usd} USD</div>` : ''}<div class="dn-muted">${containersText(note.containerCount)}</div></div>
        <div class="dn-right"><div class="dn-sec">DUE DATE  ·  付款截止日</div><div class="dn-duedate">${escape(model.dnDate(d.dueDate))}</div>
          <div class="dn-muted">Please pay by this date  ·  请于此日期前付款</div></div></div>
      <div class="dn-sumhead"><span class="dn-sec">CHARGE SUMMARY  ·  费用汇总</span><span class="dn-unit">Amounts in VND  ·  金额单位：越南盾</span></div>
      <table class="dn-sum"><thead><tr><th>DESTINATION PORT<br><span>目的港</span></th><th class="num">CONTAINERS<br><span>柜数</span></th>
        <th class="num">LUMP-SUM<br><span>单价合计</span></th><th class="num">OTHER FEES<br><span>其他费用</span></th></tr></thead>
        <tbody>${ports}${extra}<tr class="dn-sub"><td>Subtotal  小计</td><td class="num">${note.containerCount}</td><td class="num">${money(note.lumpSumVnd)}</td><td class="num">${money(note.otherVnd)}</td></tr></tbody></table>
      <div class="dn-totalbar"><span>TOTAL DUE  ·  应付总额</span><span>${money(note.subtotalVnd) || '—'} VND</span></div>
      <div class="dn-words"><span>Amount in words  英文大写</span><b>${escape(d.words)}</b></div>
      ${d.usd ? `<div class="dn-words"><span>Equivalent  折合美元</span><b>${d.usd} USD at ${escape(d.rateText)}${doc.usd?.source ? `  ·  ${escape(doc.usd.source)}` : ''}${model.dnDate(doc.usd?.date) ? `  ·  ${escape(model.dnDate(doc.usd.date))}` : ''}</b></div>` : ''}
      <div class="dn-sec dn-paysec">PAYMENT INFORMATION  ·  付款信息</div>
      <table class="dn-pay">${payRows.map(([en, cn, value, bold]) => `<tr><th>${en}  <span>${cn}</span></th><td${bold ? ' class="b"' : ''}>${escape(value)}</td></tr>`).join('')}</table>
      <div class="dn-sign"><div class="dn-sec">FOR AND ON BEHALF OF  ·  代表</div><div class="dn-signname">${escape(issuer.name)}</div>
        <div class="dn-signline">Authorized Signature &amp; Stamp  ·  授权签字及盖章</div></div>
      <div class="dn-notes"><div>Container details on the following page(s)  ·  Please quote the debit note no. with your payment${email ? `  ·  Billing queries: ${email}` : ''}</div>
        <div>明细见后页  ·  付款时请注明账单号${email ? `  ·  账单查询：${email}` : ''}</div></div>
    </section>`;
  }

  function detailPage(note, doc, model) {
    const withBl = note.rows.some(row => row.bl);
    const fees = note.feeColumns;
    const textCols = [['NO.', '序号', 'no'], ['CONTAINER NO.', '柜号', 'cont'], ...(withBl ? [['B/L NO.', '提单号', 'bl']] : []), ['LINE', '船东', 'line'],
      ['SHIPPER', '发货人', 'ship'], ['LOADING DATE', '装柜日期', 'date'], ['LOADING PLACE', '装柜地点', 'place'], ['POD', '目的港', 'pod']];
    const span = textCols.length + fees.length + 1;
    // Độ rộng cột theo tỷ lệ, chia lại khi số cột phí thay đổi để không cắt số tiền.
    const units = { no: 3.5, cont: 10.5, bl: 8, line: 6.5, ship: 12, date: 8.5, place: 9, pod: 7 };
    const widths = [...textCols.map(([, , key]) => units[key]), ...fees.map(fee => fee.code === 'LUMP_SUM' ? 8.5 : 8), 9.5];
    const sum = widths.reduce((total, width) => total + width, 0);
    const colgroup = `<colgroup>${widths.map(width => `<col style="width:${Math.round(width * 10000 / sum) / 100}%">`).join('')}</colgroup>`;
    const head = `<tr class="dn-dhead"><th colspan="${span}"><div class="dn-dtop"><div><div class="dn-dissuer">${escape(doc.issuer?.name)}</div><div class="dn-sec">CONTAINER DETAILS  ·  柜明细</div></div>
        <div class="dn-right"><div class="dn-dissuer">DEBIT NOTE  ${escape(doc.number)}</div><div class="dn-muted">${escape(doc.buyer?.display)}  ·  ${escape(note.period)}</div></div></div>
        <div class="dn-unit">Amounts in VND  ·  金额单位：越南盾</div></th></tr>
      <tr class="dn-colhead">${textCols.map(([en, cn, key]) => `<th class="h-${key}">${en}<br><span>${cn}</span></th>`).join('')}${fees.map(fee =>
        `<th class="num">${escape(fee.en)}<br><span>${escape(fee.cn)}</span></th>`).join('')}<th class="num">AMOUNT<br><span>金额</span></th></tr>`;
    const containerRow = row => `<tr><td class="no">${row.no}</td><td class="b">${escape(row.container)}</td>${withBl ? `<td>${escape(row.bl ?? '')}</td>` : ''}
      <td>${escape(row.carrier ?? '')}</td><td>${escape(row.shipper ?? '')}</td><td>${escape(model.dnDate(row.date))}</td><td>${escape(row.place.text)}</td><td>${escape(row.port.text)}</td>
      ${fees.map(fee => `<td class="num">${money(model.dnCell(fee.code, row))}</td>`).join('')}<td class="num b">${money(row.amountVnd)}</td></tr>`;
    const label = code => { const fee = model.DN_FEES.find(item => item.code === code); return `${fee.en}  ·  ${fee.cn}`; };
    const chargeRow = item => `<tr class="dn-charge"><td></td><td colspan="${withBl ? 4 : 3}">${escape(label(item.code))}</td><td>${escape(model.dnDate(item.date))}</td>
      <td colspan="2">${escape(item.note)}</td>${fees.map(fee => `<td class="num">${money(model.dnCell(fee.code, item))}</td>`).join('')}<td class="num b">${money(item.amountVnd)}</td></tr>`;
    const lines = [...note.rows.map(containerRow)];
    const charges = note.charges.map(chargeRow);
    if (charges.length) lines.push(`<tr class="dn-group"><td colspan="${span}">ADDITIONAL CHARGES  ·  附加费用</td></tr>`, ...charges);
    const total = `<tr class="dn-total"><td colspan="2">TOTAL  ·  合计</td><td colspan="${textCols.length - 2}" class="dn-count">${containersText(note.containerCount)}</td>
      ${fees.map(fee => `<td class="num">${money(fee.totalVnd)}</td>`).join('')}<td class="num">${money(note.totalVnd)}</td></tr>`;
    // Dòng TOTAL đi cùng dòng cuối để không đứng một mình ở đầu trang mới.
    const tail = lines.splice(Math.max(0, lines.length - 1));
    return `<section class="dn-page dn-detail"><table class="dn-items${fees.length > 3 ? ' is-wide' : ''}">${colgroup}<thead>${head}</thead>
      ${lines.length ? `<tbody>${lines.join('')}</tbody>` : ''}<tbody class="dn-end">${tail.join('')}${total}</tbody></table></section>`;
  }

  function html(note, doc, { model, draft = false }) {
    const d = derive(note, doc, model);
    return `<div class="dn${draft ? ' is-draft' : ''}">${draft ? '<div class="dn-draft" aria-hidden="true">DRAFT · 草稿</div>' : ''}${summaryPage(note, doc, d, model)}${detailPage(note, doc, model)}</div>`;
  }

  // Kiểu chung cho hộp xem trước và bản in (cỡ chữ, màu theo đặc tả v3).
  const SHEET_CSS = `.dn{font:9pt/1.35 Arial,Helvetica,sans-serif;color:#1F2933;position:relative}.dn *{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
    .dn table{border-collapse:collapse}.dn .num{text-align:right;font-variant-numeric:tabular-nums}.dn .b{font-weight:700}
    .dn-sec{font-size:7.5pt;font-weight:700;color:#97A1AD;letter-spacing:.2px;text-transform:none}.dn-muted{color:#5F6B7A;font-size:8pt}.dn-right{text-align:right}
    .dn-summary{display:flex;flex-direction:column}.dn-summary>*{flex-shrink:0}.dn-bar{height:5px;background:#14304F;margin-bottom:16px}
    .dn-top{display:flex;justify-content:space-between;gap:16px;padding-bottom:10px;border-bottom:2px solid #14304F}
    .dn-issuer{font-size:13pt;font-weight:700;color:#14304F;margin-bottom:3px}.dn-docname{text-align:right}.dn-title{font-size:20pt;font-weight:700;color:#14304F;line-height:1.1}
    .dn-two{display:flex;justify-content:space-between;gap:24px;margin:12px 0 10px}.dn-billto{flex:1}.dn-cust{font-size:12pt;font-weight:700;color:#14304F;margin:3px 0 2px}
    .dn-pre{white-space:pre-line}.dn-attn{margin-top:6px}.dn-docinfo{width:47%}.dn-docinfo table{width:100%}
    .dn-docinfo th,.dn-pay th{font-weight:400;color:#5F6B7A;font-size:8pt;text-align:left;padding:3px 10px 3px 0;white-space:nowrap;vertical-align:top}
    .dn-docinfo td{text-align:right;padding:2px 0;vertical-align:top}.dn-pay td{padding:2px 0}.dn-docinfo th,.dn-pay th{padding-top:2px;padding-bottom:2px}
    .dn-due{display:flex;justify-content:space-between;align-items:flex-start;background:#EEF2F7;padding:10px 14px}
    .dn-amount{font-size:22pt;font-weight:700;color:#14304F;line-height:1.2;margin:4px 0 2px}.dn-usd{font-size:10pt;font-weight:700;color:#14304F}
    .dn-duedate{font-size:16pt;font-weight:700;color:#14304F;margin:8px 0 6px}
    .dn-sumhead{display:flex;justify-content:space-between;margin:14px 0 4px}.dn-unit{color:#97A1AD;font-size:7.5pt;font-weight:400}
    .dn-sum{width:100%}.dn-sum th{font-size:8pt;color:#5F6B7A;text-align:left;padding:2px 0 3px;border-bottom:1px solid #DDE2E8}.dn-sum th.num{text-align:right}.dn-sum th span{font-weight:400}
    .dn-sum td{padding:4px 0;border-bottom:1px solid #DDE2E8}.dn-sum td.num{width:16%}.dn-sum .dn-sub td{font-weight:700;border-bottom:0}
    .dn-totalbar{display:flex;justify-content:space-between;background:#14304F;color:#fff;font-weight:700;font-size:11pt;padding:8px 14px}
    .dn-words{display:flex;gap:12px;margin-top:6px;font-size:8.5pt}.dn-words span{color:#5F6B7A;font-size:8pt;white-space:nowrap}.dn-words b{font-weight:400}
    .dn-paysec{margin-top:16px;padding-bottom:3px;border-bottom:1px solid #DDE2E8}.dn-pay{margin-top:4px}.dn-pay th{width:140px}
    .dn-sign{margin:14px 0 10px auto;width:48%;text-align:center}.dn-signname{font-weight:700;color:#14304F;margin-top:4px}
    .dn-signline{margin-top:40px;border-top:1px solid #DDE2E8;padding-top:5px;color:#5F6B7A;font-size:8pt}
    .dn-notes{margin-top:auto;padding-top:8px;border-top:1px solid #DDE2E8;color:#5F6B7A;font-size:7.5pt;line-height:1.7}
    .dn-items{width:100%;table-layout:fixed}.dn-items th,.dn-items td{padding:4px 6px;overflow-wrap:break-word;vertical-align:top}.dn-items td.num{white-space:nowrap}
    .dn-items.is-wide th,.dn-items.is-wide td{padding:4px 3px}.dn-items.is-wide tbody td{font-size:8.5pt}.dn-items.is-wide .dn-colhead th{font-size:7pt}
    .dn-dhead th{padding:0 0 4px;font-weight:400;text-align:left}.dn-dtop{display:flex;justify-content:space-between;padding-bottom:6px;border-bottom:2px solid #14304F}
    .dn-dissuer{font-size:11pt;font-weight:700;color:#14304F}.dn-dhead .dn-unit{text-align:right;padding-top:4px}
    .dn-colhead th{background:#14304F;color:#fff;font-size:8pt;font-weight:700;text-align:left;vertical-align:bottom;line-height:1.25;overflow-wrap:normal}.dn-colhead th.num{text-align:right}
    .dn-items tbody td{border-bottom:1px solid #DDE2E8;font-size:9pt}.dn-items tbody tr:nth-child(even) td{background:#F4F6F9}.dn-items .no{text-align:center;color:#5F6B7A}
    .dn-group td{font-size:7.5pt;font-weight:700;color:#97A1AD;background:#fff!important;padding-top:10px}.dn-charge td{white-space:normal}
    .dn-items .dn-total td{border-top:2px solid #14304F;border-bottom:0;background:#fff!important;font-weight:700;color:#14304F;padding-top:7px}.dn-items .dn-total td.dn-count{font-weight:400;color:#5F6B7A}
    .dn-draft{position:absolute;top:120px;left:0;right:0;text-align:center;font:700 64pt Arial,sans-serif;color:#b4232a22;transform:rotate(-24deg);pointer-events:none;z-index:2}`;
  // Xem trước trên màn hình: mỗi trang một tờ giấy; trang chi tiết là một tờ dài (khi in mới chia trang).
  const SCREEN_CSS = `${SHEET_CSS}
    .dn-page{background:#fff;box-shadow:0 1px 6px #0003;margin:0 auto 18px;padding:.4in .45in .6in}.dn-summary{width:210mm;min-height:297mm}.dn-detail{width:297mm}`;
  // In: trang 1 khổ dọc, trang chi tiết khổ ngang; tiêu đề bảng lặp mỗi trang; chân trang "<bên phát hành> · Debit Note | Page x of y".
  function printCss(issuerName) {
    const box = `@bottom-left{content:"${cssText(issuerName)} · Debit Note";font:7pt Arial,sans-serif;color:#97A1AD}
      @bottom-right{content:"Page " counter(page) " of " counter(pages);font:7pt Arial,sans-serif;color:#97A1AD}`;
    return `@page summary{size:A4 portrait;margin:.4in .45in .6in;${box}}@page detail{size:A4 landscape;margin:.4in .45in .6in;${box}}
      html,body{margin:0;background:#fff}${SHEET_CSS}
      .dn-summary{page:summary;min-height:calc(297mm - 1in - 2mm);break-after:page}.dn-detail{page:detail}
      .dn-items thead{display:table-header-group}.dn-items tr,.dn-end{break-inside:avoid}.dn-group{break-after:avoid}
      .dn-draft{position:fixed;top:40%}`;
  }

  // Trang 1 luôn vừa một trang A4 dọc: đo ở bề rộng vùng in, nếu cao hơn vùng in thì thu nhỏ cả trang (nhiều cảng đến).
  // Gọi từ trang cha sau khi ghi tài liệu vào khung in (CSP của web không cho script nội tuyến trong khung).
  function fitSummary(target) {
    const summary = target.querySelector('.dn-summary');
    if (!summary) return 1;
    const probe = target.createElement('div');
    probe.style.cssText = 'position:absolute;visibility:hidden;height:calc(297mm - 1in - 2mm);width:1px';
    target.body.append(probe);
    const limit = probe.getBoundingClientRect().height;
    probe.remove();
    const saved = [summary.style.width, summary.style.minHeight, summary.style.zoom];
    Object.assign(summary.style, { width: 'calc(210mm - 0.9in)', minHeight: '0', zoom: '1' });
    const height = summary.scrollHeight;
    [summary.style.width, summary.style.minHeight, summary.style.zoom] = saved;
    if (!(height > limit)) return 1;
    const zoom = Math.floor((limit / height) * 1000) / 1000;
    summary.style.zoom = String(zoom);
    summary.style.minHeight = `calc((297mm - 1in - 2mm) / ${zoom})`;
    return zoom;
  }

  return { html, derive, money, printCss, fitSummary, SHEET_CSS, SCREEN_CSS };
})();
if (typeof module !== 'undefined') module.exports = DebitNotePrint;
