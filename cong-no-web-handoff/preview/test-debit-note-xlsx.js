const test = require('node:test');
const assert = require('node:assert/strict');
const zlib = require('node:zlib');
const writer = require('./debit-note-xlsx.js');

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

const fees = (values = {}) => ({ neo: null, dien: null, ghep: null, other: null, baoHiem: null, kiemDinh: null, health: null, ...values });
const note = { monthKey: '2026-10', complete: false, totalVnd: null, rows: [
  { container: 'SEGU0000001', carrier: 'WH', shipper: 'Chủ hàng <A&B>', date: '2026-10-03', origin: 'Kho', destination: 'Cảng',
    fees: fees({ neo: 2000000n, health: 300000n }), unitPriceVnd: 80000000n, totalVnd: 82300000n },
  { container: 'SEGU0000002', carrier: 'WH', shipper: 'S', date: '2026-10-06', origin: 'Kho', destination: 'Cảng',
    fees: fees(), unitPriceVnd: null, totalVnd: null },
] };

test('DEBIT-NOTE-02 xlsx is a valid zip with the template columns, exact numbers and blanks for missing price', () => {
  const bytes = writer.xlsx(note, { customer: 'Khách Thử 三川', todayIso: '2026-10-29' });
  assert.equal(writer.crc32(Buffer.from('123456789')), 0xCBF43926);
  const files = unzip(bytes);
  assert.deepEqual(Object.keys(files).sort(), ['[Content_Types].xml', '_rels/.rels', 'xl/_rels/workbook.xml.rels', 'xl/styles.xml', 'xl/workbook.xml', 'xl/worksheets/sheet1.xml']);
  const sheet = files['xl/worksheets/sheet1.xml'];
  assert.match(sheet, /COMMERCIAL INVOICE/);
  assert.match(sheet, /29\/10\/2026/);
  assert.match(sheet, /Tháng 10\/2026 · 2026年10月/);
  assert.match(sheet, /PHỤ PHÍ · 附加费/);
  assert.match(sheet, /<mergeCell ref="H10:N10"\/>/);
  assert.match(sheet, /Khách Thử 三川/);
  assert.match(sheet, /Chủ hàng &lt;A&amp;B&gt;/);
  assert.match(sheet, /<c r="H12" s="12"><v>2000000<\/v><\/c>/);
  assert.match(sheet, /<c r="N12" s="12"><v>300000<\/v><\/c>/);
  assert.match(sheet, /<c r="P12" s="12"><v>82300000<\/v><\/c>/);
  assert.match(sheet, /<c r="E12" s="11" t="inlineStr"><is><t xml:space="preserve">03\/10\/2026<\/t>/);
  assert.match(sheet, /<c r="O13" s="12"\/><c r="P13" s="12"\/>/);
  assert.match(sheet, /<c r="O14" s="15"\/><c r="P14" s="15"\/>/);
  assert.match(sheet, /CHƯA CHỐT/);
  assert.match(sheet, /<mergeCell ref="A14:N14"\/>/);
  assert.match(sheet, /<mergeCell ref="O14:P14"\/>/);
  assert.match(files['xl/workbook.xml'], /name="T10-2026"/);
  assert.match(files['xl/workbook.xml'], /Print_Titles.*\$10:\$11/);
  assert.match(files['xl/workbook.xml'], /\$A\$1:\$P\$18/);
  for (const [name, text] of Object.entries(files)) assert.match(text, /^<\?xml version="1.0"/, name);
});

test('DEBIT-NOTE-02 html preview and file name', () => {
  const escape = text => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const html = writer.html({ ...note, complete: true, totalVnd: 82300000n, rows: [note.rows[0]] }, { customer: 'K', todayIso: '2026-01-05', escape });
  assert.match(html, /05\/01\/2026/);
  assert.match(html, /class="dn-status is-done"/);
  assert.match(html, /<td class="num">80,000,000<\/td><td class="num">82,300,000<\/td>/);
  assert.match(html, /ĐÃ CHỐT/);
  assert.equal(writer.fileName('Tâm Xuyên / ĐẠI', '2026-10'), 'debit-note-Tam-Xuyen-DAI-2026-10.xlsx');
  assert.equal(writer.fileName('三川', '2026-10'), 'debit-note-khach-2026-10.xlsx');
});
