/* DEBIT-NOTE-03: file Excel đối chiếu đi kèm PDF debit note mẫu v4. Một sheet "Debit Note": thông tin chứng từ, bảng cùng
 * cột với PDF (No., Container no., Line, Shipper, Loading date, Loading place, POD, các cột phí đang hiện, Amount), dòng
 * Total, rồi ACCOUNT STATUS và PAYMENT INFORMATION. Số tiền là số thật, ngày là ngày thật; không gộp ô trong bảng, cố định
 * hàng tiêu đề. Chỉ ghi lại số của chứng từ (debit-note-v4.js), không tính tiền. Zip dùng chung với mẫu v3 (debit-note-xlsx.js). */
const DebitNoteV4Xlsx = (() => {
  'use strict';
  const base = typeof DebitNoteXlsx !== 'undefined' ? DebitNoteXlsx : require('./debit-note-xlsx.js');
  const xml = text => String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const colName = index => (index >= 26 ? String.fromCharCode(64 + Math.floor(index / 26)) : '') + String.fromCharCode(65 + (index % 26));
  const S = { title: 1, label: 2, value: 3, bold: 4, head: 5, headNum: 6, text: 7, money: 8, date: 9, num: 10, totalText: 11, totalMoney: 12, statusMoney: 13, statusBold: 14, dateValue: 15 };
  const NAVY = 'FF14304F', LINE = 'FFB8C0CB', GRAY = 'FF5F6B7A', HEAD = 'FFE6EBF2';
  const font = (extra, color = 'FF1F2933', size = 10) => `<font>${extra}<sz val="${size}"/><color rgb="${color}"/><name val="Times New Roman"/></font>`;
  const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0;(#,##0);&quot;–&quot;"/><numFmt numFmtId="165" formatCode="[$-409]dd mmm yyyy"/></numFmts>
<fonts count="5">${[font(''), font('<b/>', NAVY, 16), font('', GRAY), font('<b/>'), font('<b/>', NAVY)].join('')}</fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="${HEAD}"/></patternFill></fill></fills>
<borders count="4"><border/><border><bottom style="thin"><color rgb="${LINE}"/></bottom></border><border><top style="thin"><color rgb="${NAVY}"/></top><bottom style="double"><color rgb="${NAVY}"/></bottom></border><border><top style="thin"><color rgb="${GRAY}"/></top></border></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="16"><xf/>
<xf fontId="1" applyFont="1"/>
<xf fontId="2" applyFont="1"/>
<xf fontId="0" applyFont="1"/>
<xf fontId="3" applyFont="1"/>
<xf fontId="4" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="bottom" wrapText="1"/></xf>
<xf fontId="4" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="right" vertical="bottom" wrapText="1"/></xf>
<xf fontId="0" borderId="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="165" fontId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left"/></xf>
<xf fontId="0" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right"/></xf>
<xf fontId="3" borderId="2" applyFont="1" applyBorder="1"/>
<xf numFmtId="164" fontId="3" borderId="2" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" applyNumberFormat="1" applyFont="1"/>
<xf numFmtId="164" fontId="3" borderId="3" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="165" fontId="0" applyNumberFormat="1" applyFont="1" applyAlignment="1"><alignment horizontal="left"/></xf>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;

  const shown = (value, label) => value === null || value === undefined || String(value).trim() === '' ? `[${label}]` : String(value);

  function sheet(doc) {
    const rows = [];
    const row = (number, cells, height) => rows.push(`<row r="${number}"${height ? ` ht="${height}" customHeight="1"` : ''}>${cells.join('')}</row>`);
    const text = (col, number, value, style) => `<c r="${colName(col)}${number}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
    const empty = (col, number, style) => `<c r="${colName(col)}${number}" s="${style}"/>`;
    const num = (col, number, value, style) => value === null || value === undefined ? empty(col, number, style) : `<c r="${colName(col)}${number}" s="${style}"><v>${value.toString()}</v></c>`;
    const date = (col, number, iso, style) => base.serial(iso) === null ? empty(col, number, style) : `<c r="${colName(col)}${number}" s="${style}"><v>${base.serial(iso)}</v></c>`;
    const fees = doc.columns, amountCol = 7 + fees.length;
    const c = doc.company, cust = doc.customer, p = doc.payment, a = doc.account ?? {};
    row(1, [text(0, 1, c.name ?? '[Company name]', S.title), text(amountCol, 1, 'DEBIT NOTE · 账单', S.title)], 24);
    const top = [['Debit Note No. 账单号', shown(doc.number, 'Debit note no.'), S.bold], ['Issue Date 开单日期', null, S.dateValue],
      ['Billing Period 账单期间', doc.period, S.value], ['Currency 币种', doc.currency, S.value],
      ['Bill to 客户', [shown(cust.nameEn, 'Customer name'), cust.nameZh].filter(Boolean).join(' '), S.bold],
      ['Legal name & address', shown(cust.legal, 'Customer legal name & address'), S.value], ['Attn 联系人', shown(cust.contact, 'Contact'), S.value]];
    top.forEach(([label, value, style], index) => {
      const number = 2 + index;
      const cell = index === 1 ? (doc.issueDate ? date(2, number, doc.issueDate, style) : text(2, number, '[Issue date]', S.value)) : text(2, number, value, style);
      row(number, [text(0, number, label, S.label), cell]);
    });
    const HEADER = 10;
    const head = [['No.', '序号'], ['Container no.', '柜号'], ['Line', '船东'], ['Shipper', '发货人'], ['Loading date', '装柜日期'], ['Loading place', '装柜地点'],
      ['POD', '目的港'], ...fees.map(fee => [fee.en, fee.cn]), ['Amount', '金额']];
    row(HEADER, head.map(([en, cn], col) => text(col, HEADER, `${en}\n${cn}`, col >= 7 || col === 0 ? S.headNum : S.head)), 32);
    let number = HEADER;
    for (const item of doc.rows) {
      number++;
      const lead = item.feeOnly
        ? [empty(0, number, S.num), empty(1, number, S.text), empty(2, number, S.text), text(3, number, 'Additional charge · 附加费用', S.text)]
        : [num(0, number, item.no, S.num), text(1, number, item.container, S.text), text(2, number, item.line, S.text), text(3, number, item.shipper, S.text)];
      row(number, [...lead, date(4, number, item.date, S.date), text(5, number, item.feeOnly ? '' : item.place.text, S.text), text(6, number, item.feeOnly ? '' : item.pod.text, S.text),
        ...fees.map((fee, k) => num(7 + k, number, item.cells[fee.code] ?? (item.feeOnly && fee.code === 'LUMP_SUM' ? null : 0n), S.money)), num(amountCol, number, item.amount, S.money)]);
    }
    const lastData = number;
    number++;
    row(number, [text(0, number, `Total, ${doc.total.count} container${doc.total.count === 1 ? '' : 's'} · 合计`, S.totalText), ...[1, 2, 3, 4, 5, 6].map(col => empty(col, number, S.totalText)),
      ...fees.map((fee, k) => num(7 + k, number, doc.total.cells[fee.code], S.totalMoney)), num(amountCol, number, doc.total.amount, S.totalMoney)]);
    number += 2;
    row(number, [text(0, number, 'ACCOUNT STATUS · 账户情况 · For reference only 仅供参考', S.label)]);
    const status = [['Opening balance · 期初余额', a.openingDate, a.opening, S.statusMoney], ['This debit note · 本期账单', doc.issueDate, a.thisNote, S.statusMoney],
      ['Payments received · 本期已收款', a.paymentsDate, a.payments === null || a.payments === undefined ? null : -a.payments, S.statusMoney],
      ['Outstanding balance · 未结余额', null, a.outstanding, S.statusBold]];
    for (const [label, iso, value, style] of status) {
      number++;
      row(number, [text(0, number, label, style === S.statusBold ? S.bold : S.value), iso ? date(amountCol - 1, number, iso, S.dateValue) : empty(amountCol - 1, number, S.value),
        num(amountCol, number, value, style)]);
    }
    number += 2;
    row(number, [text(0, number, 'PAYMENT INFORMATION · 付款信息', S.label)]);
    for (const [label, value, style] of [['Beneficiary 收款人', shown(p.beneficiary, 'Beneficiary'), S.value], ['Bank 开户银行', shown(p.bank, 'Bank'), S.value],
      [`${p.accountLabelEn} ${p.accountLabelCn}`, shown(p.account, 'Account no.'), S.bold], ['SWIFT Code SWIFT代码', shown(p.swift, 'SWIFT code'), S.value],
      ['Payment Ref. 汇款附言', shown(doc.number, 'Debit note no.'), S.value]]) {
      number++;
      row(number, [text(0, number, label, S.label), text(2, number, value, style)]);
    }
    const widths = [6, 15, 8, 28, 13, 15, 12, ...fees.map(fee => Math.max(12, Math.round(fee.width / 6.5))), 16];
    return { lastRow: number, header: HEADER, lastData, amountCol, xml: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="${HEADER}" topLeftCell="A${HEADER + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>${widths.map((width, col) => `<col min="${col + 1}" max="${col + 1}" width="${width}" customWidth="1"/>`).join('')}</cols>
<sheetData>${rows.join('')}</sheetData>
<autoFilter ref="A${HEADER}:${colName(amountCol)}${lastData}"/>
<pageMargins left="0.4" right="0.4" top="0.4" bottom="0.5" header="0.2" footer="0.3"/>
<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>
<headerFooter><oddFooter>&amp;L&amp;9Debit Note ${xml(shown(doc.number, 'Debit note no.'))}&amp;R&amp;9Page &amp;P of &amp;N</oddFooter></headerFooter>
</worksheet>` };
  }

  function files(doc) {
    const out = sheet(doc), name = 'Debit Note', last = colName(out.amountCol);
    return {
      '[Content_Types].xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`,
      '_rels/.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
      'xl/_rels/workbook.xml.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
      'xl/workbook.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${name}" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'${name}'!$A$${out.header}:$${last}$${out.lastData}</definedName><definedName name="_xlnm.Print_Area" localSheetId="0">'${name}'!$A$1:$${last}$${out.lastRow}</definedName><definedName name="_xlnm.Print_Titles" localSheetId="0">'${name}'!$${out.header}:$${out.header}</definedName></definedNames></workbook>`,
      'xl/styles.xml': STYLES,
      'xl/worksheets/sheet1.xml': out.xml,
    };
  }

  const xlsx = doc => base.zip(files(doc));
  // Tên file như mẫu v3: <số chứng từ>_<khách>_<yyyy-mm>.
  const baseName = doc => base.baseName({ number: doc.number, buyer: { display: doc.customer.nameEn } }, doc.monthKey);
  return { xlsx, files, sheet, baseName };
})();
if (typeof module !== 'undefined') module.exports = DebitNoteV4Xlsx;
