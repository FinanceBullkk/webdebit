/* Trình duyệt (Playwright) cho Debit Note theo tháng công nợ (DEBIT-NOTE-01, mẫu v3 DEBIT-NOTE-02) trên sổ khách V7 bản live,
 * theo specs/v7-debit-note.md. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { withPage } = require('./so-khach-v7-browser-world');

// Chuyến web tháng 9 có một khoản Neo; dòng sổ gốc OLDU0000001 chưa có giá, OLDU0000002 có Phụ phí ban đầu 3.000.000.
const withNeo = world => {
  world.trips[0].fee_lines = [{ id: 700, fee_type_id: 1, amount_vnd: '2000000', note: null }];
  world.trips[0].amount_vnd = '52000000';
};
const rowsOf = view => view.locator('.dn-items tbody tr:not(.dn-total)').evaluateAll(list => list.map(row => [...row.cells].map(cell => cell.textContent.trim())));

test('Debit note: thiếu giá thì chặn và chỉ ra bản nháp; xem trước đúng chuyến của tháng; tải Excel; Esc trả focus', async () => withPage(async ({ page, world, shot }) => {
  const open = page.locator('#thang-2026-09 .debit-open');
  await open.waitFor();
  assert.equal(await page.locator('.debit-open').count(), 1);   // tháng hiện tại chưa có chuyến: không có nút
  await open.click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('.dn-items').waitFor();
  assert.equal(await page.evaluate(() => document.activeElement?.className), 'debit-print');
  assert.match(await dialog.locator('h2').innerText(), /Debit note tháng 9\/2026\s*3 container · bản nháp/);
  assert.match(await dialog.locator('.debit-checks').innerText(), /Chặn: 1 dòng chưa có giá hoặc số tiền\./);
  assert.match(await dialog.locator('.debit-checks').innerText(), /Chặn: Còn thiếu: MST bên phát hành, Tên pháp lý của khách/);
  assert.equal(await dialog.locator('.debit-print').innerText(), 'In bản nháp');
  assert.equal(await dialog.locator('.debit-excel').innerText(), 'Excel bản nháp');
  assert.equal(await view.locator('.dn-draft').count(), 1);
  assert.equal(await dialog.locator('.debit-ack').isHidden(), true);
  assert.equal(await dialog.locator('[name="number"]').inputValue(), 'HTH-2609-001');
  assert.equal(await dialog.locator('[name="buyer.display"]').inputValue(), 'Khách Thử Sửa');
  assert.equal(await dialog.locator('[name="service"]').inputValue(), 'Sea freight 海运');
  const rows = await rowsOf(view);
  assert.equal(rows.length, 3);
  assert.deepEqual(rows[0].slice(0, 7), ['1', 'OLDU0000001', 'Xe 1', 'Chủ hàng thử', '02 Sep 2026', 'Nơi C', 'Nơi D']);
  assert.deepEqual(rows[0].slice(7), ['', '', '', '']);
  assert.deepEqual(rows[1].slice(7), ['90,000,000', '', '3,000,000', '93,000,000']);
  assert.deepEqual(rows[2], ['3', 'DEMU1234567', 'Tàu thử', '', '15 Sep 2026', 'Nơi A', 'Nơi B', '50,000,000', '2,000,000', '', '52,000,000']);
  assert.deepEqual(await view.locator('.dn-colhead th.num').evaluateAll(list => list.map(cell => cell.firstChild.textContent)), ['LUMP-SUM', 'OVERSTAY', 'OTHER FEES', 'AMOUNT']);
  assert.match(await view.locator('.dn-total').innerText(), /TOTAL · 合计\s+3 containers · 3个柜/);
  assert.match(await view.locator('.dn-cust').innerText(), /Khách Thử Sửa/);
  assert.equal(await view.locator('.dn-amount').innerText(), '— VND');   // thiếu giá: không in số, không coi là 0
  await shot('debit-note-xem-truoc');

  const [download] = await Promise.all([page.waitForEvent('download'), dialog.locator('.debit-excel').click()]);
  assert.equal(download.suggestedFilename(), 'HTH-2609-001_Khach-Thu-Sua_2026-09_DRAFT.xlsx');
  assert.equal(fs.readFileSync(await download.path()).subarray(0, 2).toString(), 'PK');

  await page.keyboard.press('Escape');
  assert.equal(await dialog.isHidden(), true);
  assert.equal(await page.evaluate(() => document.activeElement?.className), 'debit-open');
  assert.deepEqual(world.requests, []);   // chỉ đọc: không gửi lệnh nào
}, withNeo));

test('Debit note: đủ thông tin thì hết chặn; cảnh báo cần xác nhận mới ra bản chính thức; In dựng đủ dòng; nhớ thông tin; đổi bên phát hành', async () => withPage(async ({ page }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('.dn-items').waitFor();
  const fill = async (name, value) => dialog.locator(`.debit-form [name="${name}"]`).fill(value);
  await fill('issuer.taxId', '0000000001');
  await fill('buyer.legal', 'BUYER LEGAL CO., LTD');
  await fill('buyer.address', 'Buyer address');
  await fill('payment.beneficiary', 'HTH LOGISTICS DV TM CO.,LTD');
  await fill('payment.bank', 'Sample Bank');
  await fill('payment.account', '000111');
  await fill('payment.swift', 'BANKXXXX');
  const checks = await dialog.locator('.debit-checks').innerText();
  assert.doesNotMatch(checks, /Chặn:/);
  assert.match(checks, /Cảnh báo: 1 container có LUMP-SUM bằng 0\./);
  assert.match(checks, /Lưu ý: 1 chuyến đang CHỜ KIỂM không lên chứng từ\./);
  assert.equal(await dialog.locator('.debit-print').innerText(), 'In bản nháp');
  await dialog.locator('.debit-ack input').check();
  assert.equal(await dialog.locator('.debit-print').innerText(), 'In / Lưu PDF');
  assert.match(await dialog.locator('h2').innerText(), /3 container · bản chính thức/);
  assert.equal(await view.locator('.dn-draft').count(), 0);
  assert.equal(await view.locator('.dn-amount').innerText(), '143,000,000 VND');
  assert.equal(await view.locator('.dn-totalbar span').last().innerText(), '143,000,000 VND');

  await page.evaluate(() => { window.__printed = 0; HTMLIFrameElement.prototype.focus = () => {}; });
  await page.evaluate(() => {
    const original = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow').get;
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', { get() { const win = original.call(this); win.print = () => { window.__printed++; }; return win; } });
  });
  await dialog.locator('.debit-print').click();
  assert.equal(await page.evaluate(() => window.__printed), 1);
  const printed = await page.evaluate(() => { const target = document.querySelector('.debit-print-frame').contentDocument;
    return { rows: target.querySelectorAll('.dn-items tbody tr:not(.dn-total)').length, title: target.title, draft: target.querySelectorAll('.dn-draft').length,
      page: [...target.styleSheets[0].cssRules].some(rule => rule.cssText.startsWith('@page summary')) }; });
  assert.deepEqual(printed, { rows: 3, title: 'HTH-2609-001_Khach-Thu-Sua_2026-09', draft: 0, page: true });

  await dialog.locator('.debit-close').click();
  assert.equal(await dialog.isHidden(), true);
  await page.locator('#thang-2026-09 .debit-open').click();
  await view.locator('.dn-items').waitFor();
  assert.equal(await dialog.locator('[name="issuer.taxId"]').inputValue(), '0000000001');   // trình duyệt nhớ
  assert.equal(await dialog.locator('[name="buyer.legal"]').inputValue(), 'BUYER LEGAL CO., LTD');
  await dialog.locator('[name="issuerCode"]').selectOption('NSX');
  assert.equal(await dialog.locator('[name="issuer.name"]').inputValue(), 'GREEN AGRICULTURAL PRODUCTS EXPORT TRADING CO.,LTD');
  assert.equal(await dialog.locator('[name="issuer.taxId"]').inputValue(), '0319147624');
  assert.equal(await dialog.locator('[name="number"]').inputValue(), 'NSX-2609-001');
  assert.match(await dialog.locator('.debit-checks').innerText(), /Còn thiếu: Người nhận tiền, Ngân hàng, Số tài khoản, SWIFT/);
  await dialog.locator('[name="issuerCode"]').selectOption('HTH');
  assert.equal(await dialog.locator('[name="issuer.taxId"]').inputValue(), '0000000001');
  assert.equal(await dialog.locator('[name="payment.swift"]').inputValue(), 'BANKXXXX');
}, world => {
  world.legacy[0].current = { ...world.legacy[0].current, container: 'CSQU3054383', unit_price_vnd: '0', counted_vnd: '0' };
  world.legacy[1].current = { ...world.legacy[1].current, container: 'TSTU1000019', shipper: 'Chủ hàng 2' };
  world.trips[0] = { ...world.trips[0], container: 'TSTU1000024', shipper: 'Chủ hàng 3' };
  world.trips.push({ ...world.trips[0], id: 12, container: 'PEND0000001', status: 'pending_review', amount_vnd: null });
}));
