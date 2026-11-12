/* DEBIT-NOTE-03: file Excel đi kèm PDF debit note mẫu v4, bố cục theo cùng thiết kế (docs/debit-note-v4/SPEC.md):
 * thanh navy ở mép trên, đầu trang (tên công ty | DEBIT NOTE 账单), kẻ navy, BILL TO | DOCUMENT, bảng container (tiêu đề nền
 * #E6EBF2, chữ Anh đậm trên, chữ Trung thường dưới; kẻ dòng #B8C0CB; Total kẻ đơn trên, kẻ đôi dưới, ô Amount chữ navy),
 * PAYMENT INFORMATION | ACCOUNT STATUS (số thẳng cột Amount), chân trang. Font Times New Roman, chỉ thường và đậm, không kẻ
 * dọc. Bảng không gộp ô để khách lọc, sắp, cộng được; số tiền là số thật, ngày là ngày thật. Chỉ ghi lại số của chứng từ
 * (debit-note-v4.js), không tính tiền. Zip dùng chung với mẫu v3 (debit-note-xlsx.js). In: A4 ngang, vừa một trang ngang,
 * lặp hàng tiêu đề bảng, chân trang "Page x of n". */
const DebitNoteV4Xlsx = (() => {
  'use strict';
  const base = typeof DebitNoteXlsx !== 'undefined' ? DebitNoteXlsx : require('./debit-note-xlsx.js');
  const xml = text => String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const colName = index => (index >= 26 ? String.fromCharCode(64 + Math.floor(index / 26)) : '') + String.fromCharCode(65 + (index % 26));
  const shown = (value, label) => value === null || value === undefined || String(value).trim() === '' ? `[${label}]` : String(value);
  const money = value => value === null || value === undefined ? '' : value === 0n ? '–' : (value < 0n ? `(${(-value).toString()})` : value.toString()).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

  // ---- Kiểu (màu, cỡ chữ theo SPEC 4.4; cỡ Excel tính theo pt) ----
  const NAVY = 'FF14304F', TEXT = 'FF1F2933', GRAY = 'FF5F6B7A', LINE = 'FFB8C0CB', HEAD = 'FFE6EBF2';
  const FONT = 'Times New Roman';
  const FONTS = { body: [10, TEXT], bold: [10, TEXT, true], label: [9, GRAY], fieldLabel: [10, GRAY], section: [9, GRAY, true], company: [13, NAVY, true],
    title: [20, NAVY, true], head: [9, NAVY, true], navyBold: [10, NAVY, true] };
  const BORDERS = { none: '', line: `<bottom style="thin"><color rgb="${LINE}"/></bottom>`,
    total: `<top style="thin"><color rgb="${NAVY}"/></top><bottom style="double"><color rgb="${NAVY}"/></bottom>`,
    outstanding: `<top style="thin"><color rgb="${GRAY}"/></top>`, rule: `<bottom style="medium"><color rgb="${NAVY}"/></bottom>`,
    footer: `<top style="thin"><color rgb="${LINE}"/></top>` };
  const FILLS = { none: 0, gray125: 1, navy: 2, head: 3 };
  const FMT = { money: 164, date: 165 };
  // Tên kiểu → [font, border, fill, numFmt, căn ngang, căn dọc, xuống dòng, lùi vào].
  const XF = {
    default: ['body'], band: ['body', 'none', 'navy'], rule: ['body', 'rule'],
    company: ['company', 'none', 'none', 0, 'left', 'bottom'], title: ['title', 'none', 'none', 0, 'right', 'bottom'],
    address: ['label', 'none', 'none', 0, 'left', 'top'],
    section: ['section', 'none', 'none', 0, 'left', 'top'], sectionCn: ['label', 'none', 'none', 0, 'left', 'top'],
    field: ['fieldLabel', 'none', 'none', 0, 'left', 'top'], value: ['body', 'none', 'none', 0, 'left', 'top', true],
    valueBold: ['bold', 'none', 'none', 0, 'left', 'top'], valueDate: ['body', 'none', 'none', FMT.date, 'left', 'top'],
    head: ['head', 'none', 'head', 0, 'left', 'bottom', true], headNum: ['head', 'none', 'head', 0, 'right', 'bottom', true],
    headIndent: ['head', 'none', 'head', 0, 'left', 'bottom', true, 1], container: ['body', 'line', 'none', 0, 'left', 'center', false, 1],
    containerEnd: ['body', 'none', 'none', 0, 'left', 'center', false, 1],
    text: ['body', 'line', 'none', 0, 'left', 'center'], no: ['body', 'line', 'none', 0, 'right', 'center'],
    money: ['body', 'line', 'none', FMT.money, 'right', 'center'], date: ['body', 'line', 'none', FMT.date, 'left', 'center'],
    textEnd: ['body', 'none', 'none', 0, 'left', 'center'], noEnd: ['body', 'none', 'none', 0, 'right', 'center'],
    moneyEnd: ['body', 'none', 'none', FMT.money, 'right', 'center'], dateEnd: ['body', 'none', 'none', FMT.date, 'left', 'center'],
    totalText: ['bold', 'total', 'none', 0, 'left', 'center'], totalMoney: ['bold', 'total', 'none', FMT.money, 'right', 'center'],
    totalAmount: ['navyBold', 'total', 'none', FMT.money, 'right', 'center'],
    status: ['body', 'none', 'none', 0, 'left', 'top'], statusDate: ['body', 'none', 'none', FMT.date, 'left', 'top'],
    statusMoney: ['body', 'none', 'none', FMT.money, 'right', 'top'],
    outText: ['bold', 'outstanding', 'none', 0, 'left', 'top'], outMoney: ['bold', 'outstanding', 'none', FMT.money, 'right', 'top'],
    footer: ['label', 'footer', 'none', 0, 'left', 'center'], footerRight: ['label', 'footer', 'none', 0, 'right', 'center'],
  };
  const FONT_KEYS = Object.keys(FONTS), BORDER_KEYS = Object.keys(BORDERS), XF_KEYS = Object.keys(XF);
  const S = Object.fromEntries(XF_KEYS.map((key, index) => [key, index]));
  const fontXml = ([size, color, bold]) => `<font>${bold ? '<b/>' : ''}<sz val="${size}"/><color rgb="${color}"/><name val="${FONT}"/></font>`;
  const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="${FMT.money}" formatCode="#,##0;(#,##0);&quot;–&quot;"/><numFmt numFmtId="${FMT.date}" formatCode="[$-409]dd mmm yyyy"/></numFmts>
<fonts count="${FONT_KEYS.length}">${FONT_KEYS.map(key => fontXml(FONTS[key])).join('')}</fonts>
<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="${NAVY}"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="${HEAD}"/></patternFill></fill></fills>
<borders count="${BORDER_KEYS.length}">${BORDER_KEYS.map(key => `<border>${BORDERS[key]}</border>`).join('')}</borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="${XF_KEYS.length}">${XF_KEYS.map(key => {
    const [font, border = 'none', fill = 'none', fmt = 0, horizontal, vertical, wrap, indent] = XF[key];
    const align = horizontal || vertical || wrap ? `<alignment${horizontal ? ` horizontal="${horizontal}"` : ''}${vertical ? ` vertical="${vertical}"` : ''}${wrap ? ' wrapText="1"' : ''}${indent ? ` indent="${indent}"` : ''}/>` : '';
    return `<xf numFmtId="${fmt}" fontId="${FONT_KEYS.indexOf(font)}" fillId="${FILLS[fill]}" borderId="${BORDER_KEYS.indexOf(border)}" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"${align ? ' applyAlignment="1">' + align + '</xf>' : '/>'}`;
  }).join('')}</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;
  // Một đoạn chữ trong ô nhiều kiểu (chữ Anh đậm, chữ Trung thường) — như trang mẫu.
  const run = (text, [size, color, bold]) => `<r><rPr>${bold ? '<b/>' : ''}<sz val="${size}"/><color rgb="${color}"/><rFont val="${FONT}"/></rPr><t xml:space="preserve">${xml(text)}</t></r>`;

  // ---- Lưới ô: ô ghi theo (hàng, cột), xuất theo thứ tự; gộp ô kèm kiểu cho mọi ô trong vùng gộp (để kẻ liền). ----
  function grid() {
    const rows = new Map(), heights = new Map(), merges = [];
    const ref = (r, c) => `${colName(c)}${r}`;
    const put = (r, c, inner) => { if (!rows.has(r)) rows.set(r, new Map()); rows.get(r).set(c, inner); };
    const cell = {
      blank: (r, c, style) => put(r, c, `<c r="${ref(r, c)}" s="${S[style]}"/>`),
      text: (r, c, value, style) => put(r, c, `<c r="${ref(r, c)}" s="${S[style]}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`),
      rich: (r, c, runs, style) => put(r, c, `<c r="${ref(r, c)}" s="${S[style]}" t="inlineStr"><is>${runs.join('')}</is></c>`),
      num: (r, c, value, style) => value === null || value === undefined ? cell.blank(r, c, style) : put(r, c, `<c r="${ref(r, c)}" s="${S[style]}"><v>${value.toString()}</v></c>`),
      date: (r, c, iso, style) => base.serial(iso) === null ? cell.blank(r, c, style) : put(r, c, `<c r="${ref(r, c)}" s="${S[style]}"><v>${base.serial(iso)}</v></c>`),
    };
    // Vùng c1..c2 trên một hàng: ô đầu mang nội dung, các ô sau trống cùng kiểu; gộp khi nhiều hơn một ô.
    const span = (r, c1, c2, write, style) => {
      write(c1);
      for (let c = c1 + 1; c <= c2; c++) cell.blank(r, c, style);
      if (c2 > c1) merges.push(`${ref(r, c1)}:${ref(r, c2)}`);
    };
    const height = (r, value) => heights.set(r, value);
    const sheetData = () => [...rows.keys()].sort((a, b) => a - b).map(r => `<row r="${r}"${heights.has(r) ? ` ht="${heights.get(r)}" customHeight="1"` : ''}>`
      + `${[...rows.get(r).keys()].sort((a, b) => a - b).map(c => rows.get(r).get(c)).join('')}</row>`).join('');
    return { cell, span, height, merges, sheetData, last: () => Math.max(...rows.keys()) };
  }

  // Hai khối cạnh nhau như trang mẫu: khối trái từ cột A, khối phải từ cột R. Đủ cột (từ 11) thì tên khối nằm bên trái của khối
  // (A–B; R–R+1); ít cột hơn thì tên khối thành một hàng riêng ở trên khối. Nhãn trường và giá trị theo sau.
  function layout(doc) {
    const n = 8 + doc.columns.length, last = n - 1, side = n >= 11;
    const R = side ? 6 : 5;
    return { n, last, side, R, leftField: side ? 2 : 0, leftValue: side ? 4 : 2, rightField: side ? R + 2 : R };
  }
  // Ô Loading place / POD: tên tiếng Trung theo cùng cờ show_place_cn với bản in (DEBIT-NOTE-03, DIA-DIEM-01).
  const placeText = (doc, place) => (doc.showPlaceCn && place.cn ? `${place.text}  ${place.cn}` : place.text);
  // Độ rộng ước lượng của một chuỗi theo đơn vị cột Excel (chữ Hán rộng gần gấp đôi).
  const textWidth = text => [...String(text ?? '')].reduce((sum, ch) => sum + (/[⺀-￯]/.test(ch) ? 1.9 : 1), 0);
  // Bề rộng cột (đơn vị Excel ≈ một chữ số Times 10pt). Cột chữ theo tỉ lệ px của trang mẫu; cột tiền đủ cho số lớn nhất
  // (kể cả dòng Total chữ đậm) và tiêu đề tiếng Anh một dòng. Các khối dưới bảng được đủ chỗ trước; phần còn lại cho Shipper
  // (cột co giãn) để cả bảng rộng như một trang A4 ngang.
  function widths(doc, lay = layout(doc)) {
    const cols = [5, 16, 8, 18, 13, 13.5, 11.5];
    // Loading place / POD: rộng theo chữ dài nhất (có tên tiếng Trung khi show_place_cn bật), để chữ không bị cắt.
    for (const [col, key] of [[5, 'place'], [6, 'pod']])
      cols[col] = Math.max(cols[col], ...doc.rows.filter(row => !row.feeOnly).map(row => Math.ceil(textWidth(placeText(doc, row[key])) + 2)));
    const moneyWidth = (values, en, cn, px) => Math.ceil(Math.max(px / 5.8, ...values.map(value => money(value).length * 1.05 + 2.5), en.length * 0.95 + 2, textWidth(cn) + 1.5));
    for (const column of doc.columns) cols.push(moneyWidth([...doc.rows.map(row => row.cells[column.code] ?? null), doc.total.cells[column.code]], column.en, column.cn, column.width));
    cols.push(moneyWidth([...doc.rows.map(row => row.amount), doc.total.amount, doc.account?.opening, doc.account?.outstanding,
      doc.account?.payments === null || doc.account?.payments === undefined ? null : -doc.account.payments], 'Amount', '金额', 84));
    const width = (from, to) => cols.slice(from, to + 1).reduce((sum, value) => sum + value, 0);
    const need = (from, to, min) => { const gap = min - width(from, to); if (gap > 0) cols[to] += Math.ceil(gap); };
    const p = doc.payment ?? {};
    const longest = list => Math.max(...list.map(textWidth)) + 2;
    need(lay.leftField, lay.leftField + 1, longest(['SWIFT Code SWIFT代码', `${p.account_label_en ?? p.accountLabelEn ?? ''} ${p.account_label_cn ?? p.accountLabelCn ?? ''}`]) + 1);
    need(lay.leftValue, lay.R - 1, longest([p.beneficiary ?? '[Beneficiary]', p.bank ?? '[Bank]', p.account ?? '[Account no.]', p.swift ?? '[SWIFT code]']));
    need(lay.rightField, lay.last - 2, longest(['Payments received · 本期已收款', 'Outstanding balance · 未结余额', 'Billing Period 账单期间']));
    cols[3] = Math.max(cols[3], 175 - width(0, lay.last) + cols[3]);
    return cols;
  }

  function sheet(doc) {
    const g = grid(), { cell, span } = g;
    const lay = layout(doc), cols = widths(doc, lay);
    const { last, side, R, leftField, leftValue, rightField } = lay, amountCol = last;
    const c = doc.company, cust = doc.customer, p = doc.payment, a = doc.account ?? {};
    const width = (from, to) => cols.slice(from, to + 1).reduce((sum, value) => sum + value, 0);
    // Nhãn trường của khối phải: từ rightField tới khi đủ 22 đơn vị; giá trị DOCUMENT theo ngay sau (như trang mẫu).
    let fieldEnd = rightField;
    while (fieldEnd < last - 2 && width(rightField, fieldEnd) < 22) fieldEnd++;

    // Thanh navy 6px, đầu trang, kẻ navy 2px.
    for (let col = 0; col <= last; col++) cell.blank(1, col, 'band');
    g.height(1, 4.5); g.height(2, 12);
    span(3, 0, last - 5, col => cell.text(3, col, shown(c.name, 'Company name'), 'company'), 'company');
    span(3, last - 4, last, col => cell.rich(3, col, [run('DEBIT NOTE', FONTS.title), run('  账单', [12, GRAY])], 'title'), 'title');
    g.height(3, 30);
    span(4, 0, last, col => cell.text(4, col, `${shown(c.address, 'Company address')} · Tax ID 税号: ${shown(c.taxId, 'Tax ID')} · Tel 电话: ${shown(c.tel, 'Phone')} · Email 邮箱: ${shown(c.email, 'Email')}`, 'address'), 'address');
    g.height(4, 15);
    for (let col = 0; col <= last; col++) cell.blank(5, col, 'rule');
    g.height(5, 8); g.height(6, 12);

    // Khối có tên ở bên (side) hoặc ở hàng trên; trả về hàng bắt đầu ghi các dòng của khối.
    const blockStart = (row, from, to, en, cn) => {
      if (side) {
        span(row, from, from + 1, col => cell.text(row, col, en, 'section'), 'section');
        span(row + 1, from, from + 1, col => cell.text(row + 1, col, cn, 'sectionCn'), 'sectionCn');
        return row;
      }
      span(row, from, to, col => cell.rich(row, col, [run(en, FONTS.section), run(` · ${cn}`, FONTS.label)], 'section'), 'section');
      return row + 1;
    };
    const pair = (row, fieldFrom, fieldTo, valueFrom, valueTo, label, write, style) => {
      span(row, fieldFrom, fieldTo, col => cell.text(row, col, label, 'field'), 'field');
      span(row, valueFrom, valueTo, write, style);
    };

    // BILL TO | DOCUMENT.
    let row = 7;
    const billRow = blockStart(row, 0, R - 1, 'BILL TO', '客户'), docRow = blockStart(row, R, last, 'DOCUMENT', '单据信息');
    // Tên và địa chỉ dài tự ngắt thành nhiều hàng cùng cao 15pt (không dùng ô xuống dòng): hàng của khối DOCUMENT bên cạnh
    // không bị kéo cao theo. Tên: phần Latin đậm, phần chữ Hán thường.
    const room = width(leftField, R - 1) / 1.2;
    const wrap = tokens => tokens.reduce((list, token) => {
      const line = list.at(-1);
      if (line.length && textWidth([...line.map(item => item.text), token.text].join(' ')) > room) list.push([token]); else line.push(token);
      return list;
    }, [[]]);
    const tokens = (text, bold) => String(text).split(/\s+/).filter(Boolean).map(word => ({ text: word, bold }));
    const nameLines = wrap([...tokens(shown(cust.nameEn, 'Customer name'), true), ...tokens(cust.nameZh ?? '', false)]);
    const legalLines = wrap(tokens(shown(cust.legal, 'Customer legal name & address'), false));
    let at = billRow;
    for (const line of nameLines) {
      const runs = line.map((token, index) => run(`${index ? ' ' : ''}${token.text}`, token.bold ? FONTS.bold : FONTS.body));
      const r = at++;
      span(r, leftField, R - 1, col => cell.rich(r, col, runs, 'value'), 'value');
    }
    for (const line of legalLines) {
      const r = at++;
      span(r, leftField, R - 1, col => cell.text(r, col, line.map(token => token.text).join(' '), 'value'), 'value');
    }
    const docRows = [['Debit Note No. 账单号', col => cell.text(docRow, col, shown(doc.number, 'Debit note no.'), 'valueBold'), 'valueBold'],
      ['Issue Date 开单日期', col => doc.issueDate ? cell.date(docRow + 1, col, doc.issueDate, 'valueDate') : cell.text(docRow + 1, col, '[Issue date]', 'value'), doc.issueDate ? 'valueDate' : 'value'],
      ['Billing Period 账单期间', col => cell.text(docRow + 2, col, doc.period, 'value'), 'value'],
      ['Currency 币种', col => cell.text(docRow + 3, col, doc.currency, 'value'), 'value']];
    docRows.forEach(([label, write, style], index) => pair(docRow + index, rightField, fieldEnd, fieldEnd + 1, last, label, write, style));
    row = Math.max(at, docRow + 4) + 1;   // BILL TO hết ở dòng tên pháp lý (đã bỏ dòng Attn)
    g.height(row - 1, 12);

    // Bảng container: tiêu đề hai dòng (Anh đậm, Trung thường), không gộp ô.
    const header = row;
    const heads = [['No.', '序号'], ['Container no.', '柜号'], ['Line', '船东'], ['Shipper', '发货人'], ['Loading date', '装柜日期'], ['Loading place', '装柜地点'],
      ['POD', '目的港'], ...doc.columns.map(column => [column.en, column.cn]), ['Amount', '金额']];
    heads.forEach(([en, cn], col) => cell.rich(header, col, [run(en, FONTS.head), run(`\n${cn}`, [9, NAVY])], col === 0 || col >= 7 ? 'headNum' : col === 1 ? 'headIndent' : 'head'));
    g.height(header, 30);
    doc.rows.forEach((item, index) => {
      const r = header + 1 + index, end = index === doc.rows.length - 1 ? 'End' : '';
      if (item.feeOnly) {
        cell.blank(r, 0, `no${end}`); cell.text(r, 1, 'Additional charge · 附加费用', `container${end}`); cell.blank(r, 2, `text${end}`); cell.blank(r, 3, `text${end}`);
      } else {
        cell.num(r, 0, item.no, `no${end}`); cell.text(r, 1, item.container, `container${end}`); cell.text(r, 2, item.line, `text${end}`); cell.text(r, 3, item.shipper, `text${end}`);
      }
      cell.date(r, 4, item.date, `date${end}`);
      cell.text(r, 5, item.feeOnly ? '' : placeText(doc, item.place), `text${end}`); cell.text(r, 6, item.feeOnly ? '' : placeText(doc, item.pod), `text${end}`);
      doc.columns.forEach((column, k) => cell.num(r, 7 + k, item.cells[column.code] ?? (item.feeOnly && column.code === 'LUMP_SUM' ? null : 0n), `money${end}`));
      cell.num(r, amountCol, item.amount, `money${end}`);
      g.height(r, 18);
    });
    const total = header + doc.rows.length + 1;
    span(total, 0, 6, col => cell.rich(total, col, [run(`Total, ${doc.total.count} container${doc.total.count === 1 ? '' : 's'}`, FONTS.bold), run(' · 合计', FONTS.body)], 'totalText'), 'totalText');
    doc.columns.forEach((column, k) => cell.num(total, 7 + k, doc.total.cells[column.code], 'totalMoney'));
    cell.num(total, amountCol, doc.total.amount, 'totalAmount');
    g.height(total, 21);
    g.height(total + 1, 20);

    // PAYMENT INFORMATION | ACCOUNT STATUS; số ACCOUNT STATUS nằm ở cột Amount của bảng.
    row = total + 2;
    const payStart = side ? (() => {
      span(row, 0, 1, col => cell.text(row, col, 'PAYMENT', 'section'), 'section');
      span(row + 1, 0, 1, col => cell.text(row + 1, col, 'INFORMATION', 'section'), 'section');
      span(row + 2, 0, 1, col => cell.text(row + 2, col, '付款信息', 'sectionCn'), 'sectionCn');
      return row;
    })() : blockStart(row, 0, R - 1, 'PAYMENT INFORMATION', '付款信息');
    // ACCOUNT STATUS tùy chọn (doc.showAccount): không in thì không có khối bên phải.
    const withStatus = doc.showAccount !== false;
    const statusStart = !withStatus ? payStart : side ? (() => {
      ['ACCOUNT STATUS', '账户情况', 'For reference only', '仅供参考'].forEach((text, index) => {
        const style = index === 0 ? 'section' : 'sectionCn';
        span(row + index, R, R + 1, col => cell.text(row + index, col, text, style), style);
      });
      return row;
    })() : (() => {
      span(row, R, last, col => cell.rich(row, col, [run('ACCOUNT STATUS', FONTS.section), run(' · 账户情况 · For reference only 仅供参考', FONTS.label)], 'section'), 'section');
      return row + 1;
    })();
    [['Beneficiary 收款人', shown(p.beneficiary, 'Beneficiary'), 'value'], ['Bank 开户银行', shown(p.bank, 'Bank'), 'value'],
      [`${p.accountLabelEn} ${p.accountLabelCn}`, shown(p.account, 'Account no.'), 'valueBold'], ['SWIFT Code SWIFT代码', shown(p.swift, 'SWIFT code'), 'value'],
      ['Payment Ref. 汇款附言', shown(doc.number, 'Debit note no.'), 'value']]
      .forEach(([label, value, style], index) => pair(payStart + index, leftField, leftField + 1, leftValue, R - 1, label, col => cell.text(payStart + index, col, value, style), style));
    const paid = a.payments === null || a.payments === undefined ? null : -a.payments;
    const status = [['Opening balance · 期初余额', a.openingDate, a.opening], ['This debit note · 本期账单', doc.issueDate ?? '[Issue date]', a.thisNote],
      ['Payments received · 本期已收款', a.paymentsDate, paid]];
    let out = payStart + 4;
    if (withStatus) {
      status.forEach(([label, day, value], index) => {
        const r = statusStart + index;
        span(r, rightField, last - 2, col => cell.text(r, col, label, 'status'), 'status');
        if (day && /^\d{4}-/.test(day)) cell.date(r, last - 1, day, 'statusDate'); else cell.text(r, last - 1, day ?? '', 'status');
        cell.num(r, amountCol, value, 'statusMoney');
      });
      out = statusStart + 3;
      span(out, rightField, last - 2, col => cell.rich(out, col, [run('Outstanding balance', FONTS.bold), run(' · 未结余额', FONTS.body)], 'outText'), 'outText');
      cell.blank(out, last - 1, 'outText');
      cell.num(out, amountCol, a.outstanding, 'outMoney');
    }
    for (let r = Math.min(payStart, statusStart); r <= Math.max(payStart + 4, out); r++) g.height(r, 15);

    // Chân trang.
    const foot = Math.max(payStart + 4, out) + 2;
    g.height(foot - 1, 18);
    span(foot, 0, last - 2, col => cell.text(foot, col, `Debit Note ${shown(doc.number, 'Debit note no.')} · Billing queries 账单查询: ${shown(c.email, 'Email')}`, 'footer'), 'footer');
    span(foot, last - 1, last, col => cell.blank(foot, col, 'footerRight'), 'footerRight');
    g.height(foot, 18);

    return { lastRow: foot, header, lastData: total - 1, amountCol, xml: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
<sheetViews><sheetView workbookViewId="0" showGridLines="0" zoomScale="90" zoomScaleNormal="90"/></sheetViews>
<sheetFormatPr defaultRowHeight="15" customHeight="1"/>
<cols>${cols.map((width, col) => `<col min="${col + 1}" max="${col + 1}" width="${width}" customWidth="1"/>`).join('')}</cols>
<sheetData>${g.sheetData()}</sheetData>
<mergeCells count="${g.merges.length}">${g.merges.map(range => `<mergeCell ref="${range}"/>`).join('')}</mergeCells>
<printOptions horizontalCentered="1"/>
<pageMargins left="0.4" right="0.4" top="0.35" bottom="0.5" header="0.2" footer="0.25"/>
<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>
<headerFooter><oddFooter>&amp;R&amp;"${FONT},Regular"&amp;9&amp;K5F6B7APage &amp;P of &amp;N</oddFooter></headerFooter>
</worksheet>` };
  }

  function files(doc) {
    const out = sheet(doc), name = 'Debit Note', lastCol = colName(out.amountCol);
    return {
      '[Content_Types].xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`,
      '_rels/.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
      'xl/_rels/workbook.xml.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
      'xl/workbook.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${name}" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">'${name}'!$A$1:$${lastCol}$${out.lastRow}</definedName><definedName name="_xlnm.Print_Titles" localSheetId="0">'${name}'!$${out.header}:$${out.header}</definedName></definedNames></workbook>`,
      'xl/styles.xml': STYLES,
      'xl/worksheets/sheet1.xml': out.xml,
    };
  }

  const xlsx = doc => base.zip(files(doc));
  // Tên file như mẫu v3: <số chứng từ>_<khách>_<yyyy-mm>.
  const baseName = doc => base.baseName({ number: doc.number, buyer: { display: doc.customer.nameEn } }, doc.monthKey);
  return { xlsx, files, sheet, baseName, widths, layout };
})();
if (typeof module !== 'undefined') module.exports = DebitNoteV4Xlsx;
