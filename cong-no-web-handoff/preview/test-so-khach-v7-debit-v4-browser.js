/* Trình duyệt (Playwright) cho hộp Debit note mẫu v4 (DEBIT-NOTE-03, docs/debit-note-v4/SPEC.md) trên sổ khách V7 bản live:
 * mẫu chọn theo cấu hình máy chủ (?debit= để xem thử), 6 phép kiểm khóa nút xuất, xem trước chia trang, In dựng trang A4
 * ngang, tải Excel. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { withPage } = require('./so-khach-v7-browser-world');

const config = { ...JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'web', 'debit-note-config.default.json'), 'utf8')), template: 'v4' };
// Đủ giá cho cả tháng 9: dòng sổ gốc OLDU0000001 có giá 40.000.000, số container đúng ISO 6346.
const priced = world => {
  world.debitConfig = config;
  world.legacy[0].current = { ...world.legacy[0].current, container: 'CSQU3054383', unit_price_vnd: '40000000', counted_vnd: '40000000' };
  world.legacy[1].current = { ...world.legacy[1].current, container: 'TSTU1000019' };
  world.trips[0] = { ...world.trips[0], container: 'TSTU1000024' };
};

test('Debit note v4: cấu hình chọn v4; thiếu giá thì chặn và khóa nút xuất; đủ giá thì xem trước 1 trang, cảnh báo cần xác nhận', async () => withPage(async ({ page, world }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  assert.deepEqual(world.debitConfigReads, ['']);
  assert.match(await dialog.locator('.debit-checks').innerText(), /Chặn: 1 dòng chưa có giá hoặc số tiền\./);
  assert.match(await dialog.locator('.debit-checks').innerText(), /Chặn: Phép 1: dòng 1 OLDU0000001: Amount \(trống\)/);
  assert.equal(await dialog.locator('.debit-print').isDisabled(), true);
  assert.equal(await dialog.locator('.debit-excel').isDisabled(), true);
  assert.equal(await dialog.locator('[name="number"]').inputValue(), 'HTH-2609-001');
  assert.equal(await dialog.locator('[name="customer.nameEn"]').inputValue(), 'Khach Thu Sua');   // không in tiếng Việt
  assert.equal(await dialog.locator('[name="issuer.name"]').count(), 0);   // công ty, ngân hàng theo cấu hình, không điền ở hộp
  await page.keyboard.press('Escape');
  assert.deepEqual(world.requests, []);   // chỉ đọc
}, world => { world.debitConfig = config; }));

test('Debit note v4: đủ giá thì hết chặn; xác nhận cảnh báo mới xuất; In dựng trang A4 ngang có Total; Excel; ?debit=v3 về mẫu cũ', async () => withPage(async ({ page, shot }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  const checks = await dialog.locator('.debit-checks').innerText();
  assert.doesNotMatch(checks, /Chặn:/);
  assert.match(checks, /Cảnh báo: Nơi đóng hàng ngoài danh mục/);
  assert.match(await dialog.locator('h2').innerText(), /3 container · 1 trang · mẫu v4/);
  assert.equal(await dialog.locator('.debit-print').isDisabled(), true);
  await dialog.locator('.debit-ack input').check();
  assert.equal(await dialog.locator('.debit-print').isDisabled(), false);
  await shot('debit-note-v4-xem-truoc');
  // Bảng: cột theo cột phụ phí của sổ (sổ thử không có cột riêng: Unit price, Khác), Total là số phải trả.
  const head = await view.locator('[data-reftop] > span > span:first-child').allInnerTexts();
  assert.deepEqual(head, ['No.', 'Container no.', 'Line', 'Shipper', 'Loading date', 'Loading place', 'POD', 'Unit price', 'Other fees', 'Amount']);
  assert.match(await view.locator('[data-total]').innerText(), /Total, 3 containers · 合计\s+180,000,000\s+3,000,000\s+183,000,000/);
  assert.match(await view.locator('[data-blk="BOTTOM"]').innerText(), /\[Beneficiary\][\s\S]*This debit note · 本期账单\s+\[Issue date\]\s+183,000,000/);
  assert.doesNotMatch(await view.locator('[data-page]').innerText(), /[À-ỹ]/u);

  await dialog.locator('[name="issueDate"]').fill('2026-10-05');
  assert.match(await view.locator('[data-blk="INFO"]').innerText(), /Issue Date 开单日期\s+05 Oct 2026/);
  await page.evaluate(() => {
    window.__printed = 0;
    const original = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow').get;
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', { get() { const win = original.call(this); win.print = () => { window.__printed++; }; win.focus = () => {}; return win; } });
  });
  await dialog.locator('.debit-print').click();
  assert.equal(await page.evaluate(() => window.__printed), 1);
  const printed = await page.evaluate(() => { const target = document.querySelector('.debit-print-frame').contentDocument;
    return { pages: target.querySelectorAll('[data-page]').length, kind: target.querySelector('[data-page]').dataset.page, title: target.title,
      rows: target.querySelectorAll('[data-row]').length, page: target.styleSheets[0].cssRules[0].cssText }; });
  assert.deepEqual(printed, { pages: 1, kind: 'single', title: 'HTH-2609-001_Khach-Thu-Sua_2026-09', rows: 3, page: '@page { size: a4 landscape; margin: 0px; }' });

  const [download] = await Promise.all([page.waitForEvent('download'), dialog.locator('.debit-excel').click()]);
  assert.equal(download.suggestedFilename(), 'HTH-2609-001_Khach-Thu-Sua_2026-09.xlsx');
  assert.equal(fs.readFileSync(await download.path()).subarray(0, 2).toString(), 'PK');
  await dialog.locator('.debit-close').click();

  // Thông tin khách người lập điền được trình duyệt nhớ theo sổ.
  await page.locator('#thang-2026-09 .debit-open').click();
  await dialog.locator('[name="customer.contact"]').fill('Mr Li');
  await dialog.locator('.debit-close').click();
  await page.locator('#thang-2026-09 .debit-open').click();
  assert.equal(await dialog.locator('[name="customer.contact"]').inputValue(), 'Mr Li');
  await dialog.locator('.debit-close').click();

  await page.goto(page.url().replace(/&debit=v4|$/, '&debit=v3'));
  await page.locator('#thang-2026-09 .debit-open').click();
  await page.frameLocator('.debit-preview').locator('.dn-items').waitFor();   // mẫu v3 vẫn bật lại được
  assert.equal(await dialog.locator('[name="issuer.name"]').count(), 1);
}, priced));

test('Debit note v4: ?debit=v4 khi máy chủ chưa có cấu hình thì chặn và nêu lý do; không có ?debit thì vẫn mẫu v3', async () => withPage(async ({ page }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  await page.frameLocator('.debit-preview').locator('[data-page]').first().waitFor();
  assert.match(await dialog.locator('.debit-checks').innerText(), /Chặn: Không đọc được cấu hình debit note/);
  assert.equal(await dialog.locator('.debit-print').isDisabled(), true);
  await dialog.locator('.debit-close').click();
  await page.goto(page.url().replace('&debit=v4', ''));
  await page.locator('#thang-2026-09 .debit-open').click();
  await page.frameLocator('.debit-preview').locator('.dn-items').waitFor();
}, world => { world.query = '&debit=v4'; }));

// THONG-TIN-CTY-01: danh bạ khách và tài khoản nhận tiền từ Sheet thông tin khách hàng (dữ liệu giả).
const COMPANY = {
  available: true, read_at: '2026-11-12T07:05:00+00:00', counts: {},
  accounts: [
    { id: 'a000000000001', title: '(VND) NGAN HANG GIA', label: 'VND · NGAN HANG GIA', currency: 'VND', beneficiary: 'CONG TY GIA', address: null, bank: 'TEST BANK',
      bank_address: null, account: '1234567890', swift: null, lines: [] },
    { id: 'a000000000002', title: '(USD) BANK B', label: 'USD · BANK B', currency: 'USD', beneficiary: 'TEST CO', address: null, bank: 'BANK B',
      bank_address: null, account: '000123', swift: 'TESTVNVX', lines: [] },
  ],
  customers: [{ name: 'Khach Thu Sua Co', company: 'KHACH THU SUA CO.,LTD', rows: [21, 27], shipper: 'KHACH THU SUA CO.,LTD', invoice: 'KHACH THU SUA CO.,LTD\nMST: 0000000009\nDia chi gia', bank: '' }],
};

test('Debit note v4: chọn khách từ Thông tin cty điền ô pháp lý; chọn tài khoản thì PAYMENT in theo tài khoản; chưa chọn thì cảnh báo; nhớ theo sổ', async () => withPage(async ({ page, world }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  assert.deepEqual(world.companyInfoReads, ['']);
  assert.match(await dialog.locator('.debit-checks').innerText(), /Cảnh báo: Chưa chọn tài khoản nhận tiền: chứng từ in \[Account no\.\]\./);
  assert.deepEqual(await dialog.locator('[name="account"] option').allInnerTexts(), ['Chưa chọn', 'VND · NGAN HANG GIA · CONG TY GIA · …7890', 'USD · BANK B · TEST CO · …0123']);

  await dialog.locator('[name="pick"]').fill('Khach Thu Sua Co');
  assert.equal(await dialog.locator('[name="customer.legal"]').inputValue(), 'KHACH THU SUA CO.,LTD\nMST: 0000000009\nDia chi gia');
  await dialog.locator('[name="customer.legal"]').fill('KHACH THU SUA CO.,LTD (sua tay)');   // vẫn sửa tay được, không bị điền đè
  await dialog.locator('[name="account"]').selectOption('a000000000002');
  const bottom = await view.locator('[data-blk="BOTTOM"]').innerText();
  assert.match(bottom, /Beneficiary 收款人\s+TEST CO/);
  assert.match(bottom, /Bank 开户银行\s+BANK B/);
  assert.match(bottom, /USD Account 美元账号\s+000123/);
  assert.match(bottom, /SWIFT Code SWIFT代码\s+TESTVNVX/);
  assert.doesNotMatch(await dialog.locator('.debit-checks').innerText(), /Chưa chọn tài khoản/);
  await dialog.locator('[name="account"]').selectOption('a000000000001');
  assert.match(await view.locator('[data-blk="BOTTOM"]').innerText(), /VND Account 越南盾账号\s+1234567890/);
  await dialog.locator('.debit-close').click();

  await page.locator('#thang-2026-09 .debit-open').click();
  await view.locator('[data-page]').first().waitFor();
  assert.equal(await dialog.locator('[name="account"]').inputValue(), 'a000000000001');
  assert.equal(await dialog.locator('[name="customer.legal"]').inputValue(), 'KHACH THU SUA CO.,LTD (sua tay)');
  await dialog.locator('.debit-close').click();

  // Tài khoản đã nhớ mà Sheet bỏ đi thì coi như chưa chọn.
  world.companyInfo = { ...COMPANY, accounts: COMPANY.accounts.slice(1) };
  await page.locator('#thang-2026-09 .debit-open').click();
  await view.locator('[data-page]').first().waitFor();
  assert.equal(await dialog.locator('[name="account"]').inputValue(), '');
  assert.match(await dialog.locator('.debit-checks').innerText(), /Chưa chọn tài khoản nhận tiền/);
  assert.deepEqual(world.requests, []);   // chỉ đọc
}, world => { priced(world); world.companyInfo = COMPANY; }));

test('Debit note v4: chưa bật Thông tin cty thì ô chọn khách khóa và nêu lý do; hộp vẫn xuất được như trước', async () => withPage(async ({ page }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  await page.frameLocator('.debit-preview').locator('[data-page]').first().waitFor();
  assert.equal(await dialog.locator('[name="pick"]').isDisabled(), true);
  assert.match(await dialog.locator('.debit-field', { has: page.locator('[name="pick"]') }).innerText(), /Máy chủ chưa đọc Sheet thông tin khách hàng\./);
  assert.deepEqual(await dialog.locator('[name="account"] option').allInnerTexts(), ['Chưa chọn']);
  await dialog.locator('.debit-ack input').check();
  assert.equal(await dialog.locator('.debit-print').isDisabled(), false);
}, priced));
