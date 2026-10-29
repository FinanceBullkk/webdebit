/* DEBIT-NOTE-01: ghi phiếu debit note (từ SoKhachV7Model.debitNote) thành file .xlsx theo mẫu "COMMERCIAL INVOICE"
 * đang gửi khách, và dựng bảng HTML cùng nội dung cho hộp xem trước/bản in. Không thư viện ngoài: zip kiểu "stored"
 * (không nén) đủ cho Excel. Không tính tiền: số tiền lấy nguyên từ phiếu, chỉ đổi BigInt thành chữ số. */
const DebitNoteXlsx = (() => {
  const FROM = { name: 'HTH LOGISTICS DV TM CO.,LTD', address: '20/21/15 LE CONG PHAP, AN LAC WARD, BINH TAN DISTRICT, HO CHI MINH CITY, VIETNAM',
    tel: '', email: 'hth.logs@gmail.com' };
  // Cột như mẫu; fee = khóa trong row.fees của model.
  const COLUMNS = [
    { head: ['NO.', ''], width: 5 }, { head: ['CONTAINER NO.', '柜号'], width: 15 }, { head: ['LINE', '船东'], width: 8 },
    { head: ['SHIPPER', ''], width: 18 }, { head: ['NGÀY', '装柜日期'], width: 12 }, { head: ['KHO', '工厂'], width: 14 },
    { head: ['CẢNG ĐẾN', '目的港'], width: 13 }, { head: ['NEO', '押车'], width: 11, fee: 'neo' },
    { head: ['PHÍ ĐIỆN', '插电费'], width: 11, fee: 'dien' }, { head: ['ĐÓNG GHÉP', '井柜'], width: 11, fee: 'ghep' },
    { head: ['OTHER FEE', '其他费用'], width: 11, fee: 'other' }, { head: ['BẢO HIỂM', '保险'], width: 11, fee: 'baoHiem' },
    { head: ['KIỂM ĐỊNH', '(O + CD + VS)'], width: 12, fee: 'kiemDinh' }, { head: ['HEALTH CERT', ''], width: 11, fee: 'health' },
    { head: ['ĐƠN GIÁ', '单价'], width: 13 }, { head: ['TỔNG', '总计 (VND)'], width: 15 },
  ];
  const TOTAL_WIDTH = COLUMNS.reduce((sum, column) => sum + column.width, 0);   // bề rộng cột trên trang theo tỉ lệ cột Excel
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const isoDay = iso => /^\d{4}-\d{2}-\d{2}/.test(iso ?? '') ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '';
  const longDay = iso => `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}, ${iso.slice(0, 4)}`;
  const digits = value => value === null || value === undefined ? '' : value.toString();
  const grouped = value => value === null || value === undefined ? '' : (value < 0n ? '-' : '') + (value < 0n ? -value : value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const statusText = note => note.complete ? 'ĐÃ CHỐT' : 'CHƯA CHỐT';

  // Một dòng phiếu → giá trị từng cột (chữ hoặc BigInt/null cho cột tiền).
  function cells(row, index) {
    return [String(index + 1), row.feeOnly ? 'Phí lẻ' : row.container ?? '', row.carrier ?? '', row.shipper ?? '', isoDay(row.date),
      row.origin ?? '', row.destination ?? '', ...COLUMNS.slice(7, 14).map(column => row.fees[column.fee]), row.unitPriceVnd, row.totalVnd];
  }

  // ---- HTML (xem trước và in) ----
  function html(note, { customer, todayIso, escape }) {
    const head = COLUMNS.map(column => `<th>${escape(column.head[0])}${column.head[1] ? `<br>${escape(column.head[1])}` : ''}</th>`).join('');
    const body = note.rows.map((row, index) => `<tr>${cells(row, index).map((value, col) =>
      col < 7 ? `<td${col === 0 ? ' class="no"' : ''}>${escape(value)}</td>` : `<td class="num">${grouped(value)}</td>`).join('')}</tr>`).join('');
    return `<table class="dn-sheet"><colgroup>${COLUMNS.map(column => `<col style="width:calc(100% * ${column.width} / ${TOTAL_WIDTH})">`).join('')}</colgroup>
      <tr><td class="dn-title" colspan="16">COMMERCIAL INVOICE</td></tr>
      <tr><td colspan="13"></td><td class="dn-date-label">DATE:</td><td class="dn-date" colspan="2">${escape(longDay(todayIso))}</td></tr>
      <tr><td></td><td class="dn-label">FROM:</td><td class="dn-strong" colspan="14">${escape(FROM.name)}</td></tr>
      <tr><td colspan="2"></td><td>ADDRESS:</td><td colspan="2"></td><td class="dn-strong" colspan="11">${escape(FROM.address)}</td></tr>
      <tr><td colspan="2"></td><td>TEL:</td><td colspan="2"></td><td colspan="11">${escape(FROM.tel)}</td></tr>
      <tr><td colspan="2"></td><td>Email:</td><td colspan="2"></td><td class="dn-mail" colspan="11">${escape(FROM.email)}</td></tr>
      <tr><td></td><td class="dn-label">TO:</td><td colspan="14">${escape(customer)}</td></tr>
      <tr class="dn-gap"><td colspan="16"></td></tr>
      <tr class="dn-head">${head}</tr>${body}
      <tr class="dn-total"><td colspan="15">TỔNG( 总计)  VND</td><td class="num">${grouped(note.totalVnd)}</td></tr>
      <tr><td colspan="15"></td><td class="dn-status">${statusText(note)}</td></tr></table>`;
  }

  // ---- XLSX ----
  const xml = text => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const colName = index => String.fromCharCode(65 + index);   // 16 cột: A..P
  // Kiểu ô (chỉ số cellXfs trong styles.xml bên dưới).
  const S = { title: 1, label: 2, text: 3, dateBox: 4, head: 5, cell: 6, money: 7, center: 8, totalLabel: 9, totalMoney: 10, status: 11, mail: 12, dateLabel: 13 };
  const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0"/></numFmts>
<fonts count="7"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="20"/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FF1F4E79"/><name val="Arial"/></font><font><sz val="8"/><name val="Arial"/></font><font><b/><u/><sz val="10"/><color rgb="FF0563C1"/><name val="Arial"/></font></fonts>
<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2E75B6"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0000FF"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFC000"/></patternFill></fill></fills>
<borders count="2"><border/><border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/></border></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="14"><xf/>
<xf fontId="1" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf fontId="2" applyFont="1"/>
<xf/>
<xf fontId="3" fillId="3" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="right"/></xf>
<xf fontId="4" fillId="4" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf fontId="5" borderId="1" applyFont="1" applyBorder="1"/>
<xf numFmtId="164" fontId="5" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf fontId="5" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right"/></xf>
<xf fontId="4" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="164" fontId="2" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
<xf fontId="5" applyFont="1" applyAlignment="1"><alignment horizontal="right"/></xf>
<xf fontId="6" applyFont="1"/>
<xf fontId="2" applyFont="1" applyAlignment="1"><alignment horizontal="right"/></xf>
</cellXfs></styleSheet>`;

  function sheetXml(note, customer, todayIso) {
    const rows = [];
    const merges = [];
    const row = (number, list, height) => rows.push(`<row r="${number}"${height ? ` ht="${height}" customHeight="1"` : ''}>${list.join('')}</row>`);
    const text = (col, number, value, style) => `<c r="${colName(col)}${number}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
    const blank = (col, number, style) => `<c r="${colName(col)}${number}" s="${style}"/>`;
    const amount = (col, number, value, style) => value === null || value === undefined ? blank(col, number, style) : `<c r="${colName(col)}${number}" s="${style}"><v>${digits(value)}</v></c>`;
    row(1, [text(0, 1, 'COMMERCIAL INVOICE', S.title)], 30); merges.push('A1:P1');
    row(2, [text(13, 2, 'DATE:', S.dateLabel), text(14, 2, longDay(todayIso), S.dateBox), blank(15, 2, S.dateBox)]); merges.push('O2:P2');
    row(3, [text(1, 3, 'FROM:', S.label), text(2, 3, FROM.name, S.label)]);
    row(4, [text(2, 4, 'ADDRESS:', S.text), text(5, 4, FROM.address, S.label)]);
    row(5, [text(2, 5, 'TEL:', S.text), text(5, 5, FROM.tel, S.text)]);
    row(6, [text(2, 6, 'Email:', S.text), text(5, 6, FROM.email, S.mail)]);
    row(7, [text(1, 7, 'TO:', S.label), text(2, 7, customer, S.text)]);
    row(9, COLUMNS.map((column, col) => text(col, 9, column.head.filter(Boolean).join('\n'), S.head)), 42);
    note.rows.forEach((item, index) => {
      const number = 10 + index;
      row(number, cells(item, index).map((value, col) => col === 0 ? text(col, number, value, S.center)
        : col < 7 ? text(col, number, value, S.cell) : amount(col, number, value, S.money)));
    });
    const end = 10 + note.rows.length;
    row(end, [text(0, end, 'TỔNG( 总计)  VND', S.totalLabel), ...COLUMNS.slice(1, 15).map((_, col) => blank(col + 1, end, S.totalLabel)),
      amount(15, end, note.totalVnd, S.totalMoney)]);
    merges.push(`A${end}:O${end}`);
    row(end + 1, [text(15, end + 1, statusText(note), S.status)]);
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews>
<cols>${COLUMNS.map((column, col) => `<col min="${col + 1}" max="${col + 1}" width="${column.width}" customWidth="1"/>`).join('')}</cols>
<sheetData>${rows.join('')}</sheetData>
<mergeCells count="${merges.length}">${merges.map(ref => `<mergeCell ref="${ref}"/>`).join('')}</mergeCells>
<pageMargins left="0.3" right="0.3" top="0.4" bottom="0.4" header="0.2" footer="0.2"/>
<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>`;
  }

  function files(note, customer, todayIso) {
    const sheetName = xml(`T${note.monthKey.slice(5)}-${note.monthKey.slice(0, 4)}`);
    return {
      '[Content_Types].xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`,
      '_rels/.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
      'xl/workbook.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${sheetName}" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">'${sheetName}'!$A$1:$P$${11 + note.rows.length}</definedName></definedNames></workbook>`,
      'xl/_rels/workbook.xml.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
      'xl/styles.xml': STYLES,
      'xl/worksheets/sheet1.xml': sheetXml(note, customer, todayIso),
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

  const xlsx = (note, { customer, todayIso }) => zip(files(note, customer, todayIso));
  // Tên file không dấu, không ký tự lạ: debit-note-<khách>-<yyyy-mm>.xlsx
  const fileName = (customer, monthKey) => `debit-note-${String(customer).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
    .replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'khach'}-${monthKey}.xlsx`;

  return { FROM, COLUMNS, html, files, xlsx, zip, crc32, fileName, statusText };
})();
if (typeof module !== 'undefined') module.exports = DebitNoteXlsx;
