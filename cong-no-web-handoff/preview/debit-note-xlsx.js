/* DEBIT-NOTE-01: ghi phiếu debit note (từ SoKhachV7Model.debitNote) thành file .xlsx theo mẫu "COMMERCIAL INVOICE"
 * gửi khách, và dựng bảng HTML cùng nội dung cho hộp xem trước/bản in. Bố cục 30/10/2026 (DEBIT-NOTE-02): khối công ty
 * và tiêu đề, khối BILL TO và thông tin phiếu, bảng chuyến có nhóm cột, khối tổng, ô ký; cùng 16 cột như mẫu cũ.
 * Không thư viện ngoài: zip kiểu "stored" (không nén) đủ cho Excel. Không tính tiền: số tiền lấy nguyên từ phiếu,
 * chỉ đổi BigInt thành chữ số. */
const DebitNoteXlsx = (() => {
  const FROM = { name: 'HTH LOGISTICS DV TM CO.,LTD', address: '20/21/15 LE CONG PHAP, AN LAC WARD, BINH TAN DISTRICT, HO CHI MINH CITY, VIETNAM',
    tel: '', email: 'hth.logs@gmail.com' };
  // Cột như mẫu; fee = khóa trong row.fees của model. Ba nhóm cột: chuyến (7), phụ phí (7), thành tiền (2).
  const COLUMNS = [
    { head: ['NO.', ''], width: 5 }, { head: ['CONTAINER NO.', '柜号'], width: 15 }, { head: ['LINE', '船东'], width: 8 },
    { head: ['SHIPPER', ''], width: 21 }, { head: ['NGÀY', '装柜日期'], width: 12 }, { head: ['KHO', '工厂'], width: 14 },
    { head: ['CẢNG ĐẾN', '目的港'], width: 13 }, { head: ['NEO', '押车'], width: 10, fee: 'neo' },
    { head: ['PHÍ ĐIỆN', '插电费'], width: 10, fee: 'dien' }, { head: ['ĐÓNG GHÉP', '井柜'], width: 10, fee: 'ghep' },
    { head: ['OTHER FEE', '其他费用'], width: 11, fee: 'other' }, { head: ['BẢO HIỂM', '保险'], width: 11, fee: 'baoHiem' },
    { head: ['KIỂM ĐỊNH', '(O + CD + VS)'], width: 12, fee: 'kiemDinh' }, { head: ['HEALTH CERT', ''], width: 11, fee: 'health' },
    { head: ['ĐƠN GIÁ', '单价'], width: 13 }, { head: ['TỔNG', '总计 (VND)'], width: 15 },
  ];
  const GROUPS = [{ label: 'THÔNG TIN CHUYẾN · 柜信息', span: 7 }, { label: 'PHỤ PHÍ · 附加费', span: 7 }, { label: 'THÀNH TIỀN · 金额', span: 2 }];
  const TOTAL_WIDTH = COLUMNS.reduce((sum, column) => sum + column.width, 0);   // bề rộng cột trên trang theo tỉ lệ cột Excel
  const TOTAL_LABEL = 'TỔNG CỘNG · 总计 (VND)';
  const SIGN = { maker: ['Người lập · 制表', '(Ký, ghi rõ họ tên · 签名)'], customer: ['Xác nhận của khách hàng · 客户确认', '(Ký, ghi rõ họ tên · 签名)'] };
  const isoDay = iso => /^\d{4}-\d{2}-\d{2}/.test(iso ?? '') ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : '';
  const monthText = key => `Tháng ${Number(key.slice(5, 7))}/${key.slice(0, 4)} · ${key.slice(0, 4)}年${Number(key.slice(5, 7))}月`;
  const digits = value => value === null || value === undefined ? '' : value.toString();
  const grouped = value => value === null || value === undefined ? '' : (value < 0n ? '-' : '') + (value < 0n ? -value : value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const statusText = note => note.complete ? 'ĐÃ CHỐT' : 'CHƯA CHỐT';
  const contact = () => [FROM.tel ? `Tel: ${FROM.tel}` : '', `Email: ${FROM.email}`].filter(Boolean).join('  ·  ');
  const meta = (note, todayIso) => [['Ngày · 日期', isoDay(todayIso)], ['Kỳ công nợ · 账期', monthText(note.monthKey)], ['Tiền tệ · 币种', 'VND']];

  // Một dòng phiếu → giá trị từng cột (chữ hoặc BigInt/null cho cột tiền).
  function cells(row, index) {
    return [String(index + 1), row.feeOnly ? 'Phí lẻ' : row.container ?? '', row.carrier ?? '', row.shipper ?? '', isoDay(row.date),
      row.origin ?? '', row.destination ?? '', ...COLUMNS.slice(7, 14).map(column => row.fees[column.fee]), row.unitPriceVnd, row.totalVnd];
  }

  // ---- HTML (xem trước và in) ----
  function html(note, { customer, todayIso, escape }) {
    const group = GROUPS.map(item => `<th colspan="${item.span}">${escape(item.label)}</th>`).join('');
    const head = COLUMNS.map(column => `<th>${escape(column.head[0])}${column.head[1] ? `<small>${escape(column.head[1])}</small>` : ''}</th>`).join('');
    const body = note.rows.map((row, index) => `<tr>${cells(row, index).map((value, col) =>
      col < 7 ? `<td${col === 0 ? ' class="no"' : ''}>${escape(value)}</td>` : `<td class="num">${grouped(value)}</td>`).join('')}</tr>`).join('');
    const info = meta(note, todayIso).map(([label, value]) => `<tr><th>${escape(label)}</th><td>${escape(value)}</td></tr>`).join('');
    const sign = ([label, hint]) => `<div class="dn-sign"><b>${escape(label)}</b><i>${escape(hint)}</i></div>`;
    return `<div class="dn-sheet">
      <header class="dn-top"><div class="dn-from"><div class="dn-co">${escape(FROM.name)}</div><div class="dn-addr">${escape(FROM.address)}</div><div class="dn-addr">${escape(contact())}</div></div>
        <div class="dn-doc"><div class="dn-title">COMMERCIAL INVOICE</div><div class="dn-sub">Bảng kê công nợ · 对账单</div></div></header>
      <section class="dn-meta"><div class="dn-billto"><div class="dn-label">BILL TO · 客户</div><div class="dn-customer">${escape(customer)}</div></div>
        <table class="dn-info">${info}</table></section>
      <table class="dn-table"><colgroup>${COLUMNS.map(column => `<col style="width:calc(100% * ${column.width} / ${TOTAL_WIDTH})">`).join('')}</colgroup>
        <thead><tr class="dn-group">${group}</tr><tr class="dn-head">${head}</tr></thead>
        <tbody>${body}</tbody>
        <tfoot><tr class="dn-total"><td colspan="14">${escape(TOTAL_LABEL)}</td><td class="num" colspan="2">${grouped(note.totalVnd)}</td></tr></tfoot></table>
      <footer class="dn-foot"><div class="dn-status-row"><span class="dn-status ${note.complete ? 'is-done' : 'is-open'}">${statusText(note)}</span></div>
        <div class="dn-signs">${sign(SIGN.maker)}${sign(SIGN.customer)}</div></footer></div>`;
  }

  // ---- XLSX ----
  const xml = text => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const colName = index => String.fromCharCode(65 + index);   // 16 cột: A..P
  // Kiểu ô (chỉ số cellXfs trong styles.xml bên dưới).
  const S = { company: 1, title: 2, addr: 3, sub: 4, label: 5, customer: 6, metaLabel: 7, metaValue: 8, group: 9, head: 10, cell: 11, money: 12,
    center: 13, totalLabel: 14, totalMoney: 15, statusDone: 16, statusOpen: 17, signLabel: 18, signHint: 19 };
  const NAVY = 'FF1B3A5C', GRAY = 'FF5F6B7A', LINE = 'FFD5DBE3';
  const font = (sz, extra = '', color = '') => `<font>${extra}<sz val="${sz}"/>${color ? `<color rgb="${color}"/>` : ''}<name val="Arial"/></font>`;
  const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0"/></numFmts>
<fonts count="15">${[font(10), font(16, '<b/>', NAVY), font(20, '<b/>', NAVY), font(9, '', GRAY), font(8, '<b/>', GRAY), font(13, '<b/>', NAVY),
    font(9, '<b/>', NAVY), font(9), font(9, '<b/>', 'FFFFFFFF'), font(8, '<b/>', NAVY), font(10, '<b/>', NAVY), font(12, '<b/>', NAVY),
    font(9, '<b/>', 'FF1E7B4F'), font(9, '<b/>', 'FFB4690E'), font(8, '<i/>', GRAY)].join('')}</fonts>
<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="${NAVY}"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE9EEF4"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF4F6F9"/></patternFill></fill></fills>
<borders count="4"><border/><border><bottom style="thin"><color rgb="${LINE}"/></bottom></border><border><top style="medium"><color rgb="${NAVY}"/></top></border><border><bottom style="thin"><color rgb="${NAVY}"/></bottom></border></borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="20"><xf/>
<xf fontId="1" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf fontId="2" applyFont="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf fontId="3" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf fontId="3" applyFont="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf fontId="4" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf fontId="5" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf fontId="6" fillId="4" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" indent="1"/></xf>
<xf fontId="7" fillId="4" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="right" vertical="center" indent="1"/></xf>
<xf fontId="8" fillId="2" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf fontId="9" fillId="3" borderId="3" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf fontId="7" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="164" fontId="7" borderId="1" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf fontId="7" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf fontId="10" borderId="2" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="164" fontId="11" borderId="2" applyNumberFormat="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf fontId="12" applyFont="1" applyAlignment="1"><alignment horizontal="right"/></xf>
<xf fontId="13" applyFont="1" applyAlignment="1"><alignment horizontal="right"/></xf>
<xf fontId="6" applyFont="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="14" applyFont="1" applyAlignment="1"><alignment horizontal="center"/></xf>
</cellXfs></styleSheet>`;

  const HEAD_ROWS = 11;   // dòng 10 nhóm cột, dòng 11 tên cột; dữ liệu từ dòng 12
  function sheetXml(note, customer, todayIso) {
    const rows = [];
    const merges = [];
    const row = (number, list, height) => rows.push(`<row r="${number}"${height ? ` ht="${height}" customHeight="1"` : ''}>${list.join('')}</row>`);
    const text = (col, number, value, style) => `<c r="${colName(col)}${number}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
    const blank = (col, number, style) => `<c r="${colName(col)}${number}" s="${style}"/>`;
    const amount = (col, number, value, style) => value === null || value === undefined ? blank(col, number, style) : `<c r="${colName(col)}${number}" s="${style}"><v>${digits(value)}</v></c>`;
    // Ô gộp from..to trên dòng number: ô đầu có chữ, các ô sau trống cùng kiểu (để nền/viền liền).
    const span = (number, from, to, value, style) => { merges.push(`${colName(from)}${number}:${colName(to)}${number}`);
      return [text(from, number, value, style), ...Array.from({ length: to - from }, (_, k) => blank(from + 1 + k, number, style))]; };
    row(1, [...span(1, 0, 7, FROM.name, S.company), ...span(1, 8, 15, 'COMMERCIAL INVOICE', S.title)], 30);
    row(2, [...span(2, 0, 7, FROM.address, S.addr), ...span(2, 8, 15, 'Bảng kê công nợ · 对账单', S.sub)], 14);
    row(3, [...span(3, 0, 7, contact(), S.addr)], 14);
    row(4, [], 8);
    const info = meta(note, todayIso);
    row(5, [...span(5, 0, 6, 'BILL TO · 客户', S.label), ...span(5, 12, 13, info[0][0], S.metaLabel), ...span(5, 14, 15, info[0][1], S.metaValue)], 18);
    row(6, [...span(6, 0, 6, customer, S.customer), ...span(6, 12, 13, info[1][0], S.metaLabel), ...span(6, 14, 15, info[1][1], S.metaValue)], 20);
    row(7, [...span(7, 12, 13, info[2][0], S.metaLabel), ...span(7, 14, 15, info[2][1], S.metaValue)], 18);
    row(9, [], 6);
    let at = 0;
    row(10, GROUPS.flatMap(group => { const list = span(10, at, at + group.span - 1, group.label, S.group); at += group.span; return list; }), 18);
    row(11, COLUMNS.map((column, col) => text(col, 11, column.head.filter(Boolean).join('\n'), S.head)), 30);
    note.rows.forEach((item, index) => {
      const number = HEAD_ROWS + 1 + index;
      row(number, cells(item, index).map((value, col) => col === 0 ? text(col, number, value, S.center)
        : col < 7 ? text(col, number, value, S.cell) : amount(col, number, value, S.money)), 16);
    });
    const end = HEAD_ROWS + 1 + note.rows.length;
    merges.push(`O${end}:P${end}`);   // số tổng gộp hai cột cuối cho đủ chỗ
    row(end, [...span(end, 0, 13, TOTAL_LABEL, S.totalLabel), amount(14, end, note.totalVnd, S.totalMoney), blank(15, end, S.totalMoney)], 22);
    row(end + 1, [text(15, end + 1, statusText(note), note.complete ? S.statusDone : S.statusOpen)], 16);
    row(end + 3, [...span(end + 3, 1, 3, SIGN.maker[0], S.signLabel), ...span(end + 3, 11, 14, SIGN.customer[0], S.signLabel)], 16);
    row(end + 4, [...span(end + 4, 1, 3, SIGN.maker[1], S.signHint), ...span(end + 4, 11, 14, SIGN.customer[1], S.signHint)], 14);
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>
<sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews>
<cols>${COLUMNS.map((column, col) => `<col min="${col + 1}" max="${col + 1}" width="${column.width}" customWidth="1"/>`).join('')}</cols>
<sheetData>${rows.join('')}</sheetData>
<mergeCells count="${merges.length}">${merges.map(ref => `<mergeCell ref="${ref}"/>`).join('')}</mergeCells>
<pageMargins left="0.3" right="0.3" top="0.4" bottom="0.5" header="0.2" footer="0.25"/>
<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>
<headerFooter><oddFooter>&amp;L&amp;8${xml(FROM.name)} · Debit note&amp;R&amp;8Trang &amp;P / &amp;N</oddFooter></headerFooter>
</worksheet>`;
  }

  function files(note, customer, todayIso) {
    const sheetName = xml(`T${note.monthKey.slice(5)}-${note.monthKey.slice(0, 4)}`);
    const lastRow = HEAD_ROWS + 1 + note.rows.length + 4;
    return {
      '[Content_Types].xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`,
      '_rels/.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
      // Print_Titles: in nhiều trang thì hai dòng tiêu đề cột (10–11) lặp lại đầu mỗi trang.
      'xl/workbook.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${sheetName}" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">'${sheetName}'!$A$1:$P$${lastRow}</definedName><definedName name="_xlnm.Print_Titles" localSheetId="0">'${sheetName}'!$10:$11</definedName></definedNames></workbook>`,
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

  return { FROM, COLUMNS, GROUPS, html, files, xlsx, zip, crc32, fileName, statusText };
})();
if (typeof module !== 'undefined') module.exports = DebitNoteXlsx;
