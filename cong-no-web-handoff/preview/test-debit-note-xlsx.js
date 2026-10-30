const test = require('node:test');
const assert = require('node:assert/strict');
const zlib = require('node:zlib');
const model = require('./so-khach-v7-model.js');
const writer = require('./debit-note-xlsx.js');
const printer = require('./debit-note-print.js');

// Đọc lại zip "stored" do writer ghi: kiểm chữ ký, CRC và lấy nội dung từng file.
function unzip(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const end = bytes.length - 22;
  assert.equal(view.getUint32(end, true), 0x06054b50);
  const count = view.getUint16(end + 10, true);
  let at = view.getUint32(end + 16, true);
  const files = {};
  for (let index = 0; index < count; index++) {
    assert.equal(view.getUint32(at, true), 0x02014b50);
    const size = view.getUint32(at + 20, true), nameLength = view.getUint16(at + 28, true), local = view.getUint32(at + 42, true);
    const name = Buffer.from(bytes.subarray(at + 46, at + 46 + nameLength)).toString('utf8');
    assert.equal(view.getUint32(local, true), 0x04034b50);
    assert.equal(view.getUint32(local + 22, true), size, name);
    const start = local + 30 + view.getUint16(local + 26, true);
    const data = Buffer.from(bytes.subarray(start, start + size));
    assert.equal(zlib.crc32(data), view.getUint32(at + 16, true), name);
    files[name] = data.toString('utf8');
    at += 46 + nameLength;
  }
  return files;
}

// Chứng từ thử: 2 container (một có phí Neo), 1 dòng phí hủy không gắn container; tên giả, số container đúng ISO 6346.
const feeTypes = [{ id: 1, name: 'Neo' }, { id: 11, name: 'Phí hủy cont' }];
const trip = (id, container, day, port, price, lines = []) => ({ id, month: '2026-09-01', container, carrier: 'WH', shipper: 'Chủ hàng <A&B>', event_date: `2026-09-${day}`,
  origin: 'DAKLAK', destination: port, unit_price_vnd: String(price), status: 'confirmed', is_missing_price: false, is_fee_only: false,
  fee_lines: lines, amount_vnd: String(price + lines.reduce((sum, line) => sum + Number(line.amount_vnd), 0)) });
const ledger = { trips: [
  trip(1, 'CSQU3054383', '03', 'XIAMEN', 80000000, [{ fee_type_id: 1, amount_vnd: '2000000' }]),
  trip(2, 'TSTU1000019', '06', 'QINGDAO', 75000000),
  { id: 3, month: '2026-09-01', container: null, event_date: '2026-09-10', status: 'confirmed', is_fee_only: true, unit_price_vnd: null, amount_vnd: '25000000',
    fee_lines: [{ fee_type_id: 11, amount_vnd: '25000000', note: 'BK-001' }] },
] };
const note = model.debitNote(ledger, '2026-09', feeTypes);
const doc = { number: 'HTH/2609-001', issueDate: '2026-10-30', paymentDays: 15, service: 'Sea freight 海运', vatNo: '',
  issuer: { name: 'ISSUER CO., LTD', address: 'Addr', taxId: '0000000001', tel: '', email: 'billing@example.com' },
  buyer: { display: 'Khách Thử 三川', legal: 'BUYER LEGAL CO., LTD', address: 'Buyer address', attn: '' },
  payment: { beneficiary: 'ISSUER CO., LTD', address: 'A', bank: 'Bank', bankAddress: 'B', account: '000111', currency: 'USD', swift: 'BANKXXXX' },
  usd: { on: true, rate: '25,950', source: 'Bank selling rate', date: '2026-10-30' } };

test('DEBIT-NOTE-02 Excel đối chiếu: tiêu đề cố định hàng 9, đủ 8 cột phí, số thật, ngày thật, không gộp ô, USD chỉ ở dòng tổng', () => {
  assert.equal(writer.crc32(Buffer.from('123456789')), 0xCBF43926);
  const files = unzip(writer.xlsx(note, doc, { model }));
  assert.deepEqual(Object.keys(files).sort(), ['[Content_Types].xml', '_rels/.rels', 'xl/_rels/workbook.xml.rels', 'xl/styles.xml', 'xl/workbook.xml', 'xl/worksheets/sheet1.xml']);
  const sheet = files['xl/worksheets/sheet1.xml'];
  const heads = [...sheet.matchAll(/<c r="([A-Z]+)9" s="\d+" t="inlineStr"><is><t xml:space="preserve">([^<]*)<\/t>/g)].map(match => [match[1], match[2].split('\n')[0]]);
  assert.deepEqual(heads, [['A', 'NO.'], ['B', 'CONTAINER NO.'], ['C', 'SHIPPER'], ['D', 'DATE'], ['E', 'FROM'], ['F', 'TO'], ['G', 'LUMP-SUM'], ['H', 'STORAGE'],
    ['I', 'TRUCKING'], ['J', 'GENERATOR / ELECTRICITY FEE'], ['K', 'OVERSTAY'], ['L', 'HC FEE'], ['M', 'CANCELLATION FEE'], ['N', 'AMD FEE'], ['O', 'TOTAL (VND)']]);
  assert.match(sheet, /<pane ySplit="9" topLeftCell="A10" activePane="bottomLeft" state="frozen"\/>/);
  assert.doesNotMatch(sheet, /mergeCell/);
  assert.match(sheet, /<c r="B10" s="6" t="inlineStr"><is><t xml:space="preserve">CSQU3054383<\/t>/);
  assert.match(sheet, /<c r="C10" s="6" t="inlineStr"><is><t xml:space="preserve">Chủ hàng &lt;A&amp;B&gt;<\/t>/);
  assert.match(sheet, /<c r="D10" s="8"><v>46268<\/v><\/c>/);   // 03 Sep 2026 là ngày thật
  assert.match(sheet, /<c r="E10" s="6" t="inlineStr"><is><t xml:space="preserve">Dak Lak<\/t>/);
  assert.match(sheet, /<c r="G10" s="7"><v>80000000<\/v><\/c>/);
  assert.match(sheet, /<c r="K10" s="7"><v>2000000<\/v><\/c>/);
  assert.match(sheet, /<c r="O10" s="7"><v>82000000<\/v><\/c>/);
  // Dòng phí không gắn container: không số thứ tự, ô container trống, số tiền ở cột CANCELLATION FEE.
  assert.match(sheet, /<c r="A12" s="9"\/><c r="B12" s="6"\/><c r="C12" s="6" t="inlineStr"><is><t xml:space="preserve">CANCELLATION FEE {2}· {2}取消订柜费<\/t>/);
  assert.match(sheet, /<c r="M12" s="7"><v>25000000<\/v><\/c>/);
  assert.match(sheet, /<c r="B13" s="10" t="inlineStr"><is><t xml:space="preserve">2 containers {2}· {2}2个柜<\/t>/);
  assert.match(sheet, /<c r="O13" s="11"><v>182000000<\/v><\/c>/);
  assert.match(sheet, /<c r="O14" s="12"><v>7013.49<\/v><\/c>/);   // 182,000,000 ÷ 25,950 quy đổi một lần
  assert.equal((sheet.match(/s="12"/g) ?? []).length, 1);
  assert.match(files['xl/styles.xml'], /formatCode="#,##0;\(#,##0\);&quot;–&quot;"/);
  assert.match(files['xl/styles.xml'], /formatCode="\[\$-409\]dd mmm yyyy"/);
  assert.match(files['xl/workbook.xml'], /Print_Titles" localSheetId="0">Statement!\$9:\$9/);
  assert.match(unzip(writer.xlsx(note, doc, { model, draft: true }))['xl/worksheets/sheet1.xml'], /DRAFT · 草稿/);
  for (const [name, text] of Object.entries(files)) assert.match(text, /^<\?xml version="1.0"/, name);
});

test('DEBIT-NOTE-02 tên file theo số chứng từ, khách, kỳ', () => {
  assert.equal(writer.baseName(doc, '2026-09'), 'HTH-2609-001_Khach-Thu_2026-09');
  assert.equal(writer.baseName({ number: '0826AB/CD', buyer: { display: 'KHACH 三川' } }, '2026-08', true), '0826AB-CD_KHACH_2026-08_DRAFT');
  assert.equal(writer.baseName({}, '2026-08'), 'DEBIT-NOTE_khach_2026-08');
});

test('DEBIT-NOTE-02 bản in: trang 1 tóm tắt, trang chi tiết chỉ hiện cột phí có phát sinh, dòng phí riêng không đánh số', () => {
  const html = printer.html(note, doc, { model });
  assert.match(html, /<section class="dn-page dn-summary">[\s\S]*<section class="dn-page dn-detail">/);
  assert.match(html, /<div class="dn-amount">182,000,000 VND<\/div>/);
  assert.match(html, /≈ 7,013.49 USD/);
  assert.match(html, /14 Nov 2026/);
  assert.match(html, /Net 15 days/);
  assert.match(html, /SAY VIETNAM DONG ONE HUNDRED EIGHTY-TWO MILLION ONLY/);
  assert.match(html, /Equivalent {2}折合美元<\/span><b>7,013.49 USD at 25,950 VND\/USD/);
  assert.match(html, /<td>Xiamen<\/td><td class="num">1<\/td><td class="num">80,000,000<\/td><td class="num">2,000,000<\/td>/);
  assert.match(html, /<td>Additional charges {2}附加费用<\/td><td class="num">–<\/td><td class="num">–<\/td><td class="num">25,000,000<\/td>/);
  assert.match(html, /<td>Subtotal {2}小计<\/td><td class="num">2<\/td><td class="num">155,000,000<\/td><td class="num">27,000,000<\/td>/);
  assert.match(html, /Payment Ref\. {2}<span>汇款附言<\/span><\/th><td class="b">HTH\/2609-001<\/td>/);
  const heads = [...html.matchAll(/<th class="num">([^<]+)<br>/g)].map(match => match[1]);
  assert.deepEqual(heads.slice(-4), ['LUMP-SUM', 'OVERSTAY', 'CANCELLATION FEE', 'AMOUNT']);
  assert.doesNotMatch(html, /STORAGE<br>/);
  assert.doesNotMatch(html, /B\/L NO\./);   // chưa dòng nào có số B/L
  assert.match(html, /<tr class="dn-charge"><td><\/td><td colspan="3">CANCELLATION FEE {2}· {2}取消订柜费<\/td><td>10 Sep 2026<\/td>\s*<td colspan="2">BK-001<\/td>/);
  assert.match(html, /<td class="no">2<\/td>/);
  assert.doesNotMatch(html, /<td class="no">3<\/td>/);
  assert.match(html, /Chủ hàng &lt;A&amp;B&gt;/);
  assert.match(html, /<tbody class="dn-end">[\s\S]*TOTAL {2}· {2}合计[\s\S]*2 containers · 2个柜/);
  assert.doesNotMatch(html, /DRAFT/);
  assert.match(printer.html(note, doc, { model, draft: true }), /DRAFT · 草稿/);
  assert.deepEqual([0n, -1500n, 1234567n, null].map(printer.money), ['–', '(1,500)', '1,234,567', '']);
  assert.match(printer.printCss('A "B" CO'), /@page summary\{size:A4 portrait;margin:\.4in \.45in \.6in;/);
  assert.match(printer.printCss('A "B" CO'), /content:"A \\"B\\" CO · Debit Note"/);
});
