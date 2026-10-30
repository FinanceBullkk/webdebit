/* DEBIT-NOTE-02: file Excel đối chiếu gửi kèm PDF Debit Note (mẫu v3 sếp duyệt 30/10/2026, specs/v7-debit-note.md).
 * Một sheet; phía trên là số chứng từ, ngày, kỳ, bên phát hành, bên mua, tỷ giá; bảng dữ liệu cột cố định như file Statement
 * khách đang đối chiếu: NO., CONTAINER NO., SHIPPER, DATE, FROM, TO, đủ 8 cột phí (thêm loại ngoài danh mục khi phát sinh),
 * TOTAL (VND). Số tiền là số thật, không gộp ô trong bảng, cố định hàng tiêu đề; USD chỉ ở dòng tổng. Không thư viện ngoài:
 * zip kiểu "stored" (không nén) đủ cho Excel. Không tính tiền: số lấy nguyên từ chứng từ do model dựng. */
const DebitNoteXlsx = (() => {
  const xml = text => String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const colName = index => (index >= 26 ? String.fromCharCode(64 + Math.floor(index / 26)) : '') + String.fromCharCode(65 + (index % 26));
  // Ngày Excel (số ngày từ 30/12/1899) từ chuỗi yyyy-mm-dd; định dạng [$-409] để luôn hiện tên tháng tiếng Anh.
  const serial = iso => /^\d{4}-\d{2}-\d{2}/.test(iso ?? '') ? (Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) - Date.UTC(1899, 11, 30)) / 86400000 : null;
  const HEADER_ROW = 9;   // hàng tiêu đề cố định qua các tháng; dữ liệu từ hàng 10
  // Kiểu ô (chỉ số cellXfs trong styles.xml).
  const S = { title: 1, label: 2, value: 3, valueBold: 4, head: 5, text: 6, money: 7, date: 8, center: 9, totalText: 10, totalMoney: 11, usd: 12, headNum: 13, dateValue: 14 };
  const NAVY = 'FF14304F', LINE = 'FFDDE2E8', GRAY = 'FF5F6B7A';
  const font = (extra, color = 'FF1F2933', sz = 9) => `<font>${extra}<sz val="${sz}"/><color rgb="${color}"/><name val="Arial"/></font>`;
  const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3"><numFmt numFmtId="164" formatCode="#,##0;(#,##0);&quot;–&quot;"/><numFmt numFmtId="165" formatCode="[$-409]dd mmm yyyy"/><numFmt numFmtId="166" formatCode="#,##0.00"/></numFmts>
<fonts count="6">${[font(''), font('<b/>', NAVY, 14), font('', GRAY, 8), font('<b/>'), font('<b/>', 'FFFFFFFF', 8), font('<b/>', NAVY)].join('')}</fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="${NAVY}"/></patternFill></fill></fills>
<borders count="3"><border/><border><bottom style="thin"><color rgb="${LINE}"/></bottom></border><border><top style="medium"><color rgb="${NAVY}"/></top></border></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="15"><xf/>
<xf fontId="1" applyFont="1"/>
<xf fontId="2" applyFont="1"/>
<xf fontId="0" applyFont="1"/>
<xf fontId="3" applyFont="1"/>
<xf fontId="4" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf fontId="0" borderId="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="164" fontId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="165" fontId="0" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left"/></xf>
<xf fontId="0" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="5" borderId="2" applyFont="1" applyBorder="1"/>
<xf numFmtId="164" fontId="5" borderId="2" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="166" fontId="5" applyNumberFormat="1" applyFont="1"/>
<xf fontId="4" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="right" vertical="center" wrapText="1"/></xf>
<xf numFmtId="165" fontId="0" applyNumberFormat="1" applyFont="1" applyAlignment="1"><alignment horizontal="left"/></xf>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;

  function sheetXml(note, doc, model, draft) {
    const rows = [];
    const row = (number, list, height) => rows.push(`<row r="${number}"${height ? ` ht="${height}" customHeight="1"` : ''}>${list.join('')}</row>`);
    const text = (col, number, value, style) => `<c r="${colName(col)}${number}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
    const blank = (col, number, style) => `<c r="${colName(col)}${number}" s="${style}"/>`;
    const num = (col, number, value, style) => value === null || value === undefined ? blank(col, number, style) : `<c r="${colName(col)}${number}" s="${style}"><v>${value.toString()}</v></c>`;
    const date = (col, number, iso, style) => serial(iso) === null ? blank(col, number, style) : `<c r="${colName(col)}${number}" s="${style}"><v>${serial(iso)}</v></c>`;
    const rate = doc.usd?.on ? model.parseRate(doc.usd.rate) : null;
    const cents = rate === null ? null : model.usdCents(note.totalVnd, rate);
    const fees = note.excelColumns;
    const totalCol = 6 + fees.length;
    row(1, [text(0, 1, `DEBIT NOTE  ·  账单${draft ? '  —  DRAFT · 草稿' : ''}`, S.title)], 22);
    const top = [['Debit Note No.  账单号', doc.number, S.valueBold], ['Issue Date  开单日期', null, S.dateValue], ['Billing Period  账单期间', note.period, S.value],
      ['From  开票方', doc.issuer?.name, S.value], ['To  客户', [doc.buyer?.legal, doc.buyer?.display].filter(Boolean).join('  ·  '), S.value],
      ['Exchange Rate  汇率', rate === null ? '' : `${rate.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')} VND/USD${doc.usd?.source ? `  ·  ${doc.usd.source}` : ''}${model.dnDate(doc.usd?.date) ? `  ·  ${model.dnDate(doc.usd.date)}` : ''}`, S.value]];
    top.forEach(([label, value, style], index) => {
      const number = 2 + index;
      row(number, [text(0, number, label, S.label), index === 1 ? date(2, number, doc.issueDate, style) : text(2, number, value ?? '', style)]);
    });
    const head = [['NO.', '序号'], ['CONTAINER NO.', '柜号'], ['SHIPPER', '发货人'], ['DATE', '装柜日期'], ['FROM', '装柜地点'], ['TO', '目的港'],
      ...fees.map(fee => [fee.en, fee.cn]), ['TOTAL (VND)', '金额']];
    row(HEADER_ROW, head.map(([en, cn], col) => text(col, HEADER_ROW, `${en}\n${cn}`, col >= 6 ? S.headNum : S.head)), 30);
    let number = HEADER_ROW;
    for (const item of note.rows) {
      number++;
      row(number, [num(0, number, item.no, S.center), text(1, number, item.container, S.text), text(2, number, item.shipper ?? '', S.text), date(3, number, item.date, S.date),
        text(4, number, item.place.text, S.text), text(5, number, item.port.text, S.text), ...fees.map((fee, k) => num(6 + k, number, model.dnCell(fee.code, item), S.money)),
        num(totalCol, number, item.amountVnd, S.money)]);
    }
    for (const item of note.charges) {
      number++;
      const fee = model.DN_FEES.find(entry => entry.code === item.code);
      row(number, [blank(0, number, S.center), blank(1, number, S.text), text(2, number, `${fee.en}  ·  ${fee.cn}`, S.text), date(3, number, item.date, S.date),
        text(4, number, item.note, S.text), blank(5, number, S.text), ...fees.map((entry, k) => num(6 + k, number, model.dnCell(entry.code, item), S.money)),
        num(totalCol, number, item.amountVnd, S.money)]);
    }
    number++;
    row(number, [text(0, number, 'TOTAL  ·  合计', S.totalText), text(1, number, `${note.containerCount} containers  ·  ${note.containerCount}个柜`, S.totalText),
      ...[2, 3, 4, 5].map(col => blank(col, number, S.totalText)), ...fees.map((fee, k) => num(6 + k, number, fee.totalVnd, S.totalMoney)), num(totalCol, number, note.totalVnd, S.totalMoney)]);
    if (cents !== null) {
      number++;
      row(number, [text(totalCol - 2, number, `TOTAL (USD)  折合美元 @ ${rate.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')}`, S.label), `<c r="${colName(totalCol)}${number}" s="${S.usd}"><v>${model.usdText(cents).replace(/,/g, '')}</v></c>`]);
    }
    const widths = [6, 15, 22, 13, 18, 12, ...fees.map(fee => fee.code === 'LUMP_SUM' ? 14 : 13), 16];
    return { lastRow: number, xml: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="${HEADER_ROW}" topLeftCell="A${HEADER_ROW + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>${widths.map((width, col) => `<col min="${col + 1}" max="${col + 1}" width="${width}" customWidth="1"/>`).join('')}</cols>
<sheetData>${rows.join('')}</sheetData>
<autoFilter ref="A${HEADER_ROW}:${colName(totalCol)}${HEADER_ROW + note.rows.length + note.charges.length}"/>
<pageMargins left="0.45" right="0.45" top="0.4" bottom="0.6" header="0.2" footer="0.3"/>
<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>
<headerFooter><oddFooter>&amp;L&amp;8${xml(doc.issuer?.name)} · Debit Note ${xml(doc.number)}&amp;R&amp;8Page &amp;P of &amp;N</oddFooter></headerFooter>
</worksheet>` };
  }

  function files(note, doc, model, draft = false) {
    const sheet = sheetXml(note, doc, model, draft);
    const name = 'Statement';
    const last = colName(6 + note.excelColumns.length);
    return {
      '[Content_Types].xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`,
      '_rels/.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
      'xl/workbook.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${name}" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">${name}!$A$${HEADER_ROW}:$${last}$${HEADER_ROW + note.rows.length + note.charges.length}</definedName><definedName name="_xlnm.Print_Area" localSheetId="0">${name}!$A$1:$${last}$${sheet.lastRow}</definedName><definedName name="_xlnm.Print_Titles" localSheetId="0">${name}!$${HEADER_ROW}:$${HEADER_ROW}</definedName></definedNames></workbook>`,
      'xl/_rels/workbook.xml.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
      'xl/styles.xml': STYLES,
      'xl/worksheets/sheet1.xml': sheet.xml,
    };
  }

  // ---- Zip "stored" ----
  const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  function crc32(bytes) {
    let crc = 0xFFFFFFFF;
    for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >>> 8);
    return (crc ^ 0xFFFFFFFF) >>> 0;
  }
  function zip(entries) {
    const encoder = new TextEncoder();
    const chunks = [], central = [];
    let offset = 0;
    const header = (size, write) => { const buffer = new Uint8Array(size); write(new DataView(buffer.buffer)); return buffer; };
    for (const [name, content] of Object.entries(entries)) {
      const nameBytes = encoder.encode(name), data = encoder.encode(content), crc = crc32(data);
      // 0x21 = 01/01/1980 00:00 (giờ DOS); bit 11 = tên UTF-8.
      const common = view => { view.setUint16(4, 20, true); view.setUint16(6, 0x0800, true); view.setUint16(8, 0, true);
        view.setUint16(10, 0, true); view.setUint16(12, 0x21, true); view.setUint32(14, crc, true);
        view.setUint32(18, data.length, true); view.setUint32(22, data.length, true); view.setUint16(26, nameBytes.length, true); };
      const local = header(30, view => { view.setUint32(0, 0x04034b50, true); common(view); });
      chunks.push(local, nameBytes, data);
      central.push(header(46, view => {
        view.setUint32(0, 0x02014b50, true); view.setUint16(4, 20, true);
        [6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26].forEach(at => view.setUint16(at, new DataView(local.buffer).getUint16(at - 2, true), true));
        view.setUint16(28, nameBytes.length, true); view.setUint32(42, offset, true);
      }), nameBytes);
      offset += local.length + nameBytes.length + data.length;
    }
    const centralSize = central.reduce((size, part) => size + part.length, 0);
    const count = Object.keys(entries).length;
    const end = header(22, view => { view.setUint32(0, 0x06054b50, true); view.setUint16(8, count, true); view.setUint16(10, count, true);
      view.setUint32(12, centralSize, true); view.setUint32(16, offset, true); });
    const parts = [...chunks, ...central, end];
    const out = new Uint8Array(parts.reduce((size, part) => size + part.length, 0));
    let at = 0;
    for (const part of parts) { out.set(part, at); at += part.length; }
    return out;
  }

  const xlsx = (note, doc, { model, draft = false }) => zip(files(note, doc, model, draft));
  // Tên file: <số chứng từ>_<khách>_<yyyy-mm>; "/" trong số chứng từ thành "-"; chữ không phải ASCII bỏ đi.
  function baseName(doc, monthKey, draft = false) {
    const clean = text => String(text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd')
      .replace(/[^A-Za-z0-9-]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
    const number = clean(String(doc.number ?? '').replace(/\//g, '-')) || 'DEBIT-NOTE';
    return `${number}_${clean(doc.buyer?.display).slice(0, 40) || 'khach'}_${monthKey}${draft ? '_DRAFT' : ''}`;
  }

  return { xlsx, files, zip, crc32, baseName, serial };
})();
if (typeof module !== 'undefined') module.exports = DebitNoteXlsx;
