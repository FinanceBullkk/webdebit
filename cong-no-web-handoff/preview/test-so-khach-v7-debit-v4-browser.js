/* Trình duyệt (Playwright) cho hộp Debit note mẫu v4 theo luồng D (DEBIT-NOTE-03, người dùng chốt 12/11/2026; specs/v7-debit-note.md
 * Mẫu v4 → Luồng): mẫu chọn theo cấu hình máy chủ (?debit= để xem thử), ba ô gõ tìm tên từ Thông tin cty, bảng có gì xuất nấy
 * (không ô xác nhận, chuyến chưa có giá in trống), Excel là nút chính, xong hiện lời nhắn, đổi tháng trong hộp, điện thoại gửi
 * Excel qua khung chia sẻ. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
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

// THONG-TIN-CTY-01: danh bạ khách và tài khoản nhận tiền từ Sheet thông tin khách hàng (dữ liệu giả).
const COMPANY = {
  available: true, read_at: '2026-11-12T07:05:00+00:00', counts: {},
  accounts: [
    { id: 'a000000000001', title: '(VND) NGAN HANG GIA', label: 'VND · NGAN HANG GIA', currency: 'VND', beneficiary: 'CONG TY GIA', address: null, bank: 'TEST BANK',
      bank_address: null, account: '1234567890', swift: null, lines: [] },
    { id: 'a000000000002', title: '(USD) BANK B', label: 'USD · BANK B', currency: 'USD', beneficiary: 'TEST CO', address: null, bank: 'BANK B',
      bank_address: null, account: '000123', swift: 'TESTVNVX', lines: [] },
  ],
  customers: [{ name: 'Cong Ty Phat Hanh', company: 'PHAT HANH CO.,LTD', rows: [21, 27], shipper: 'PHAT HANH CO.,LTD\nADD: 9 FAKE ST\nTAX CODE: 0000000009',
    invoice: 'CONG TY TNHH PHAT HANH', bank: '',
    header: { name: 'PHAT HANH CO.,LTD', address: '9 Đường Giả, Phường Giả', tax_id: '0000000009', tel: '028 000 000', email: 'ph@thu.test' } }],
};
const box = (page, kind) => page.locator(`.dn4-pick[data-kind="${kind}"]`);
const options = (page, kind) => box(page, kind).locator('.dn4-opt b').allInnerTexts();
// Chọn một dòng như người dùng: bấm vào ô, gõ, nhấn chuột vào dòng (chọn lúc nhấn, trước khi ô mất chọn).
async function pick(page, kind, typed, text) {
  await page.locator(`#dn4-${kind}`).click();
  await page.locator(`#dn4-${kind}`).fill(typed);
  await box(page, kind).locator('.dn4-opt', { hasText: text }).first().dispatchEvent('mousedown');
}

test('Debit note v4: bảng có gì xuất nấy — chuyến chưa có giá không chặn, in trống; không ô xác nhận; Tải Excel xong hiện tên file và lời nhắn', async () => withPage(async ({ page, world }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  assert.deepEqual(world.debitConfigReads, ['']);
  assert.equal(await dialog.locator('.debit-checks').isHidden(), true);
  assert.equal(await dialog.locator('.debit-ack, [name="number"], [name="issueDate"], [name="customer.legal"]').count(), 0);
  assert.equal(await dialog.locator('.debit-excel').isDisabled(), false);
  assert.equal(await dialog.locator('.debit-excel').innerText(), 'Tải Excel');
  assert.equal(await dialog.locator('.debit-print').innerText(), 'PDF');
  assert.equal(await dialog.locator('.debit-status').innerText(), '3 container · 143.000.000 đ · 1 chuyến chưa có giá');
  const row = await view.locator('[data-row]', { hasText: 'OLDU0000001' }).innerText();
  assert.doesNotMatch(row, /\d{1,3}(,\d{3})+/);   // Unit price và Amount trống, không in 0
  assert.match(row, /Noi D(\n–){8}$/);             // bảy cột phí luôn in (DEBIT-NOTE-04) + Other fees, đều "–" (không có phí)
  assert.match(await view.locator('[data-total]').innerText(), /140,000,000(\s+–){7}\s+3,000,000\s+143,000,000/);
  assert.match(await view.locator('[data-blk="INFO"]').innerText(), /HTH-2609-001[\s\S]*\[Issue date\]/);   // số theo gợi ý, ngày chưa chốt
  assert.equal(await dialog.locator('.dn4-month').inputValue(), '2026-09');

  const [download] = await Promise.all([page.waitForEvent('download'), dialog.locator('.debit-excel').click()]);
  assert.equal(download.suggestedFilename(), 'HTH-2609-001_Khach-Thu-Sua_2026-09.xlsx');
  assert.equal(fs.readFileSync(await download.path()).subarray(0, 2).toString(), 'PK');
  assert.match(await dialog.locator('.dn4-done').innerText(), /Đã tải file Excel\s+HTH-2609-001_Khach-Thu-Sua_2026-09\.xlsx/);
  assert.equal(await dialog.locator('.dn4-msg').innerText(),
    'Gửi anh/chị debit note tháng 9/2026: 3 container, tổng 143.000.000 đ.\n您好，附上2026年9月账单：3个柜，合计143,000,000越南盾。');
  assert.equal(await dialog.locator('.dn4-form').isHidden(), true);
  await dialog.locator('.dn4-copy').click();
  await page.waitForFunction(() => document.querySelector('.dn4-copy').textContent === 'Đã copy');   // clipboard có thể treo tới 0,8 giây rồi chép dự phòng
  await dialog.locator('.dn4-back').click();
  assert.equal(await dialog.locator('.dn4-form').isVisible(), true);
  await page.keyboard.press('Escape');
  assert.equal(await dialog.isHidden(), true);
  assert.deepEqual(world.requests, []);   // chỉ đọc
}, world => { world.debitConfig = config; }));

test('Debit note v4: đủ giá; In PDF dựng trang A4 ngang; ACCOUNT STATUS tùy chọn và nhớ theo sổ; không in tiếng Việt; ?debit=v3 về mẫu cũ', async () => withPage(async ({ page }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  assert.equal(await dialog.locator('.debit-status').innerText(), '3 container · 183.000.000 đ');
  const head = await view.locator('[data-reftop] > span > span:first-child').allInnerTexts();
  assert.deepEqual(head, ['No.', 'Container no.', 'Line', 'Shipper', 'Loading date', 'Loading place', 'POD', 'Unit price', 'Storage', 'Trucking',
    'Generator / electricity fee', 'Overstay', 'HC fee', 'Cancellation fee', 'AMD fee', 'Other fees', 'Amount']);
  assert.match(await view.locator('[data-total]').innerText(), /Total, 3 containers · 合计\s+180,000,000(\s+–){7}\s+3,000,000\s+183,000,000/);
  assert.equal(await dialog.locator('[name="accountStatus"]').isChecked(), false);
  assert.doesNotMatch(await view.locator('[data-blk="BOTTOM"]').innerText(), /ACCOUNT STATUS/);
  await dialog.locator('[name="accountStatus"]').check();
  assert.match(await view.locator('[data-blk="BOTTOM"]').innerText(), /\[Beneficiary\][\s\S]*ACCOUNT STATUS[\s\S]*This debit note · 本期账单\s+\[Issue date\]\s+183,000,000/);
  assert.doesNotMatch(await view.locator('[data-page]').innerText(), /[À-ỹ]/u);
  await page.evaluate(() => {
    window.__printed = 0;
    const original = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow').get;
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', { get() { const win = original.call(this); win.print = () => { window.__printed++; }; win.focus = () => {}; return win; } });
  });
  await dialog.locator('.debit-print').click();
  assert.equal(await page.evaluate(() => window.__printed), 1);
  const printed = await page.evaluate(() => { const target = document.querySelector('.debit-print-frame').contentDocument;
    return { pages: target.querySelectorAll('[data-page]').length, kind: target.querySelector('[data-page]').dataset.page, title: target.title,
      rows: target.querySelectorAll('[data-row]').length, page: [...target.styleSheets[0].cssRules].find(rule => rule.cssText.startsWith('@page')).cssText,
      inflate: target.querySelector('style').textContent.includes('html{-webkit-text-size-adjust:100%;text-size-adjust:100%}') }; });
  assert.deepEqual(printed, { pages: 1, kind: 'single', title: 'HTH-2609-001_Khach-Thu-Sua_2026-09', rows: 3, page: '@page { size: a4 landscape; margin: 0px; }', inflate: true });
  await dialog.locator('.debit-close').click();
  await page.locator('#thang-2026-09 .debit-open').click();
  assert.equal(await dialog.locator('[name="accountStatus"]').isChecked(), true);   // nhớ theo sổ
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
  assert.match(await dialog.locator('.debit-checks').innerText(), /Chưa xuất được: Không đọc được cấu hình debit note/);
  assert.equal(await dialog.locator('.debit-print').isDisabled(), true);
  assert.equal(await dialog.locator('.debit-excel').isDisabled(), true);
  await dialog.locator('.debit-close').click();
  await page.goto(page.url().replace('&debit=v4', ''));
  await page.locator('#thang-2026-09 .debit-open').click();
  await page.frameLocator('.debit-preview').locator('.dn-items').waitFor();
}, world => { world.query = '&debit=v4'; }));

test('Debit note v4: ba ô gõ tìm tên từ Thông tin cty (Đứng tên, Nhận tiền vào theo tên chủ tài khoản, Gửi cho); lọc bỏ dấu; Esc đóng danh sách; nhớ theo sổ', async () => withPage(async ({ page, world }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  assert.deepEqual(world.companyInfoReads, ['']);
  assert.equal(await page.locator('#dn4-issuer').inputValue(), 'HTH LOGISTICS DV TM CO.,LTD');   // chưa chọn: theo cấu hình
  assert.equal(await page.locator('#dn4-account').inputValue(), 'Chưa chọn');
  assert.equal(await box(page, 'account').locator('.dn4-note').innerText(), 'Chứng từ in [Account no.]');
  assert.match(await view.locator('[data-blk="LH"]').innerText(), /^HTH LOGISTICS DV TM CO.,LTD[\s\S]*21\/20\/15 Le Cong Phep Street/);

  // Nhận tiền vào: bấm vào thả cả danh sách, dòng chính là tên chủ tài khoản; gõ thì lọc, khớp tên lên trước.
  await page.locator('#dn4-account').click();
  assert.deepEqual(await options(page, 'account'), ['Chưa chọn', 'CONG TY GIA', 'TEST CO']);
  assert.deepEqual(await box(page, 'account').locator('.dn4-opt span').allInnerTexts(), ['Chứng từ in [Account no.]', 'TEST BANK · VND · …7890', 'BANK B · USD · …0123']);
  await page.locator('#dn4-account').fill('test');
  assert.deepEqual(await options(page, 'account'), ['TEST CO', 'CONG TY GIA']);
  await page.keyboard.press('Escape');   // đóng danh sách, không đóng hộp
  assert.equal(await dialog.isVisible(), true);
  assert.equal(await box(page, 'account').locator('.dn4-list').isHidden(), true);
  assert.equal(await page.locator('#dn4-account').inputValue(), 'Chưa chọn');
  await page.locator('#dn4-account').fill('test');
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#dn4-account').inputValue(), 'TEST CO');
  assert.equal(await box(page, 'account').locator('.dn4-note').innerText(), 'BANK B · USD · STK 000123 · SWIFT TESTVNVX');
  const bottom = await view.locator('[data-blk="BOTTOM"]').innerText();
  assert.match(bottom, /Beneficiary 收款人\s+TEST CO/);
  assert.match(bottom, /USD Account 美元账号\s+000123/);
  assert.match(bottom, /SWIFT Code SWIFT代码\s+TESTVNVX/);
  await page.locator('#dn4-account').click();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#dn4-account').inputValue(), 'CONG TY GIA');
  assert.match(await view.locator('[data-blk="BOTTOM"]').innerText(), /VND Account 越南盾账号\s+1234567890/);

  // Đứng tên: gõ không dấu vẫn ra; đầu trang in theo công ty đó, bỏ dấu khi in.
  await pick(page, 'issuer', 'phat hanh', 'Cong Ty Phat Hanh');
  const head = await view.locator('[data-blk="LH"]').innerText();
  assert.match(head, /^PHAT HANH CO.,LTD/);
  assert.match(head, /9 Duong Gia, Phuong Gia · Tax ID 税号: 0000000009 · Tel 电话: 028 000 000 · Email 邮箱: ph@thu.test/);
  assert.match(await view.locator('[data-blk="INFO"]').innerText(), /\[Customer legal name & address\]/);   // không đụng BILL TO
  // Công ty đứng tên không có tài khoản ở cột ngân hàng: tài khoản cũ (của công ty khác) bỏ chọn và nêu lý do.
  assert.equal(await page.locator('#dn4-account').inputValue(), 'Chưa chọn');
  assert.equal(await box(page, 'account').locator('.dn4-note').innerText(),
    'Cong Ty Phat Hanh chưa có tài khoản ở cột ngân hàng trên Sheet. Chứng từ in [Account no.]');
  await pick(page, 'account', 'gia', 'CONG TY GIA');
  await page.locator('#dn4-bill').click();
  await page.locator('#dn4-bill').fill('khong co');
  assert.equal(await box(page, 'bill').locator('.dn4-empty').innerText(), 'Không có tên này trong Thông tin cty.');
  await pick(page, 'bill', 'cong ty', 'Cong Ty Phat Hanh');
  assert.match(await view.locator('[data-blk="INFO"]').innerText(), /PHAT HANH CO.,LTD, 9 Duong Gia, Phuong Gia, Tax ID 0000000009/);
  assert.equal(await box(page, 'bill').locator('.dn4-note').innerText(), 'PHAT HANH CO.,LTD, 9 Đường Giả, Phường Giả, Tax ID 0000000009');
  await dialog.locator('.debit-close').click();

  await page.locator('#thang-2026-09 .debit-open').click();
  await view.locator('[data-page]').first().waitFor();
  assert.deepEqual(await Promise.all(['issuer', 'account', 'bill'].map(kind => page.locator(`#dn4-${kind}`).inputValue())),
    ['Cong Ty Phat Hanh', 'CONG TY GIA', 'Cong Ty Phat Hanh']);   // nhớ theo sổ
  await dialog.locator('.debit-close').click();

  // Tài khoản đã nhớ mà Sheet bỏ đi thì coi như chưa chọn.
  world.companyInfo = { ...COMPANY, accounts: COMPANY.accounts.slice(1) };
  await page.locator('#thang-2026-09 .debit-open').click();
  await view.locator('[data-page]').first().waitFor();
  assert.equal(await page.locator('#dn4-account').inputValue(), 'Chưa chọn');
  assert.deepEqual(world.requests, []);   // chỉ đọc
}, world => { priced(world); world.companyInfo = COMPANY; }));

// TAI-KHOAN-COT-E-01: tài khoản ở cột ngân hàng cùng khối là tài khoản của chính công ty đứng tên (dữ liệu giả).
const OWN = [
  { id: 'e000000000001', currency: 'CNY', beneficiary: 'MINI CO', address: null, bank: 'NH GIA CNY', bank_address: null, account: '7000007', swift: 'GIACVNVX' },
  { id: 'e000000000002', currency: 'USD', beneficiary: 'MINI COMPANY LIMITED', address: '1 FAKE ST', bank: 'NH GIA USD', bank_address: '2 DUONG',
    account: '8000 008', swift: 'GIAUVNVX' },
  { id: 'e000000000003', currency: 'USD', beneficiary: 'MINI CO', address: null, bank: 'BANK B HUNG VUONG', bank_address: null, account: '000 123', swift: 'TESTVNVX' },
];
const WITH_OWN = { ...COMPANY, customers: [...COMPANY.customers, { name: 'MINI', company: 'MINI COMPANY LIMITED', rows: [3, 16], shipper: 'MINI COMPANY LIMITED',
  invoice: 'CONG TY TNHH MINI', bank: '', header: { name: 'MINI COMPANY LIMITED', address: '1 Fake St', tax_id: '0000000011', tel: null, email: null }, accounts: OWN }] };

test('Debit note v4: chọn công ty đứng tên thì Nhận tiền vào tự lấy tài khoản USD cùng khối trên Sheet; tài khoản của khối lên đầu, bỏ số trùng; vẫn đổi được; nhớ theo sổ', async () => withPage(async ({ page }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  await pick(page, 'issuer', 'mini', 'MINI');
  assert.equal(await page.locator('#dn4-account').inputValue(), 'MINI COMPANY LIMITED');   // USD đầu tiên, bỏ qua CNY đứng trước
  assert.equal(await box(page, 'account').locator('.dn4-note').innerText(), 'NH GIA USD · USD · STK 8000 008 · SWIFT GIAUVNVX');
  const bottom = await view.locator('[data-blk="BOTTOM"]').innerText();
  assert.match(bottom, /Beneficiary 收款人\s+MINI COMPANY LIMITED/);
  assert.match(bottom, /USD Account 美元账号\s+8000 008/);
  assert.match(await view.locator('[data-blk="LH"]').innerText(), /^MINI COMPANY LIMITED/);

  await page.locator('#dn4-account').click();
  assert.deepEqual(await options(page, 'account'), ['Chưa chọn', 'MINI CO', 'MINI COMPANY LIMITED', 'MINI CO', 'CONG TY GIA']);   // TEST CO trùng số …123 nên ẩn
  assert.deepEqual((await box(page, 'account').locator('.dn4-opt span').allInnerTexts()).slice(1, 3),
    ['NH GIA CNY · CNY · …0007 · của MINI', 'NH GIA USD · USD · …0008 · của MINI']);   // đuôi theo chữ số, bỏ dấu cách
  await page.keyboard.press('Escape');
  await pick(page, 'account', 'cny', 'NH GIA CNY');   // vẫn đổi được
  assert.match(await view.locator('[data-blk="BOTTOM"]').innerText(), /CNY Account 人民币账号\s+7000007/);
  await dialog.locator('.debit-close').click();

  await page.locator('#thang-2026-09 .debit-open').click();
  await view.locator('[data-page]').first().waitFor();
  assert.deepEqual(await Promise.all(['issuer', 'account'].map(kind => page.locator(`#dn4-${kind}`).inputValue())), ['MINI', 'MINI CO']);   // nhớ theo sổ

  // Về công ty theo cấu hình: tài khoản về theo cấu hình.
  await page.locator('#dn4-issuer').click();
  await box(page, 'issuer').locator('.dn4-opt').first().dispatchEvent('mousedown');
  assert.equal(await page.locator('#dn4-account').inputValue(), 'Chưa chọn');
  assert.equal(await box(page, 'account').locator('.dn4-note').innerText(), 'Chứng từ in [Account no.]');
}, world => { priced(world); world.companyInfo = WITH_OWN; }));

test('Debit note v4: chưa bật Thông tin cty thì nêu lý do, ô chỉ còn lựa chọn theo cấu hình; vẫn xuất được', async () => withPage(async ({ page }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  await page.frameLocator('.debit-preview').locator('[data-page]').first().waitFor();
  assert.equal(await dialog.locator('.dn4-warn').innerText(), 'Máy chủ chưa đọc Sheet thông tin khách hàng.');
  await page.locator('#dn4-account').click();
  assert.deepEqual(await options(page, 'account'), ['Chưa chọn']);
  assert.equal(await dialog.locator('.debit-excel').isDisabled(), false);
}, priced));

test('Debit note v4: đổi tháng ngay trong hộp (các tháng có nút Debit note trên sổ)', async () => withPage(async ({ page }) => {
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  assert.deepEqual(await dialog.locator('.dn4-month option').evaluateAll(items => items.map(item => item.value)), ['2026-09', '2026-08']);
  await dialog.locator('.dn4-month').selectOption('2026-08');
  assert.match(await view.locator('[data-blk="INFO"]').innerText(), /HTH-2608-001[\s\S]*Aug 2026/);
  assert.equal(await dialog.locator('.debit-status').innerText(), '1 container · 70.000.000 đ');
  const [download] = await Promise.all([page.waitForEvent('download'), dialog.locator('.debit-excel').click()]);
  assert.equal(download.suggestedFilename(), 'HTH-2608-001_Khach-Thu-Sua_2026-08.xlsx');
}, world => {
  priced(world);
  world.trips.push({ ...world.trips[0], id: 12, month: '2026-08-01', container: 'TSTU2000006', event_date: '2026-08-10', unit_price_vnd: '70000000', amount_vnd: '70000000' });
}));

// DIEN-THOAI-DEBIT-01 + luồng D: dưới 760px hộp phủ cả màn; một hàng đầu (tên, tháng, ✕); xem trước thu nhỏ ở trên; ô chọn cuộn;
// nút Gửi Excel và PDF dính đáy; Gửi Excel mở khung chia sẻ của máy khi trình duyệt chia sẻ được file.
test('Debit note trên điện thoại 390px: xem trước ở trên vừa khung, nút dính đáy, Gửi Excel qua khung chia sẻ; 1280 về hai cột', async () => withPage(async ({ page, shot }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => {
    window.__shared = [];
    navigator.canShare = data => Array.isArray(data?.files) && data.files.length === 1;
    navigator.share = async data => { window.__shared.push(data.files.map(file => [file.name, file.type, file.size > 0])); };
  });
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  const view = page.frameLocator('.debit-preview');
  await view.locator('[data-page]').first().waitFor();
  const at = selector => dialog.locator(selector).first().boundingBox();
  assert.deepEqual(await at('.debit-panel'), { x: 0, y: 0, width: 390, height: 844 });
  for (const name of ['.debit-excel', '.debit-print', '.debit-close', '.dn4-month', '#dn4-account']) {
    const item = await at(name);
    assert.ok(item.height >= 44 && item.x >= 0 && item.x + item.width <= 390, `${name} ${JSON.stringify(item)}`);
  }
  const [body, side, excel] = [await at('.debit-body'), await at('.dn4-side'), await at('.debit-excel')];
  assert.ok(body.y < side.y, 'xem trước ở trên các ô chọn');
  assert.ok(excel.y + excel.height <= 844 && excel.y > 700, `nút dính đáy ${JSON.stringify(excel)}`);
  assert.equal(await dialog.locator('.debit-excel').innerText(), 'Gửi Excel');
  assert.equal(await page.locator('#dn4-account').evaluate(el => getComputedStyle(el).fontSize), '16px');   // Safari không tự phóng to
  const fit = () => view.locator('.debit-root').evaluate(el => ({ zoom: el.style.zoom, fits: document.documentElement.scrollWidth <= document.documentElement.clientWidth }));
  const narrow = await fit();
  assert.ok(Number(narrow.zoom) > 0.2 && Number(narrow.zoom) < 0.6 && narrow.fits, JSON.stringify(narrow));
  assert.equal(await view.locator('style').first().evaluate(el => el.textContent.startsWith('html{-webkit-text-size-adjust:100%;text-size-adjust:100%}')), true);
  await shot('debit-note-dien-thoai-390');
  await dialog.locator('.debit-excel').click();
  assert.deepEqual(await page.evaluate(() => window.__shared), [[['HTH-2609-001_Khach-Thu-Sua_2026-09.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', true]]]);
  assert.match(await dialog.locator('.dn4-done').innerText(), /Đã mở khung gửi file/);
  await dialog.locator('.dn4-back').click();
  // Màn rộng: hai cột, cột trái 380px, nút về Tải Excel, xem trước vừa khung (tối đa .74).
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.waitForFunction(() => document.querySelector('.debit-excel').textContent === 'Tải Excel');
  assert.equal((await at('.dn4-side')).width, 380);
  const wide = await fit();
  assert.ok(Number(wide.zoom) > 0.6 && Number(wide.zoom) <= 0.74 && wide.fits, JSON.stringify(wide));
}, priced));

// DIEN-THOAI-DEBIT-01, bổ sung 13/11: khung iPhone 13 trong Safari (390×664, đã trừ thanh địa chỉ) — danh sách của ô dưới cùng không bị thanh
// nút đáy che: mở danh sách thì ẩn xem trước và thanh nút, ô lên đầu vùng cuộn, thấy trọn danh sách; chọn xong trả lại như cũ.
test('Debit note trên iPhone 390×664: danh sách "Gửi cho" thấy trọn, chọn xong hiện lại xem trước và nút Gửi Excel', async () => withPage(async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 664 });
  await page.locator('#thang-2026-09 .debit-open').click();
  const dialog = page.locator('.debit-dialog');
  await page.frameLocator('.debit-preview').locator('[data-page]').first().waitFor();
  const seen = kind => page.evaluate(k => {
    const list = document.querySelector(`#dn4-${k}-list`).getBoundingClientRect(), form = document.querySelector('.dn4-form').getBoundingClientRect();
    const bar = document.querySelector('.dn4-actions').getBoundingClientRect();
    const floor = bar.height ? Math.min(form.bottom, bar.top) : form.bottom;
    const pick = document.querySelector(`.dn4-pick[data-kind="${k}"]`).getBoundingClientRect();
    return { top: list.top, bottom: list.bottom, floor, lift: pick.top - form.top, options: document.querySelectorAll(`#dn4-${k}-list .dn4-opt`).length };
  }, kind);
  for (const kind of ['issuer', 'account', 'bill']) {
    await page.locator(`#dn4-${kind}`).click();
    const box = await seen(kind);
    assert.ok(box.options >= 2 && box.bottom <= box.floor + 1 && box.top >= 0, `${kind} ${JSON.stringify(box)}`);
    // Ô lên sát đầu vùng cuộn (kể cả ô dưới cùng): bàn phím iPhone che nửa dưới nên danh sách phải bắt đầu ở phần trên màn.
    assert.ok(Math.abs(box.lift) <= 2, `${kind} chưa lên đầu khung ${JSON.stringify(box)}`);
    assert.equal(await dialog.locator('.debit-body').isHidden(), true);
    assert.equal(await dialog.locator('.debit-excel').isHidden(), true);
    await page.locator('.dn4-month').focus();   // rời ô: đóng danh sách, trả lại xem trước và thanh nút
    assert.equal(await dialog.locator('.debit-excel').isVisible(), true);
  }
  await page.locator('#dn4-bill').click();
  await page.locator('#dn4-bill').fill('khach 7');
  await box(page, 'bill').locator('.dn4-opt', { hasText: 'Khach So 7' }).dispatchEvent('mousedown');
  assert.equal(await page.locator('#dn4-bill').inputValue(), 'Khach So 7');
  assert.equal(await page.evaluate(() => document.activeElement?.id ?? ''), '', 'chọn xong thì cất bàn phím');
  assert.equal(await dialog.locator('.debit-body').isVisible(), true);
  assert.equal(await dialog.locator('.debit-excel').innerText(), 'Gửi Excel');
  assert.equal(await dialog.locator('.dn4').evaluate(el => el.classList.contains('is-picking')), false);
  assert.match(await page.frameLocator('.debit-preview').locator('[data-blk="INFO"]').innerText(), /KHACH 7 CO\.,LTD/);
}, world => {
  priced(world);
  const many = Array.from({ length: 8 }, (_, i) => ({ ...COMPANY.customers[0], name: `Khach So ${i + 1}`, company: `KHACH ${i + 1} CO.,LTD`,
    header: { ...COMPANY.customers[0].header, name: `KHACH ${i + 1} CO.,LTD` } }));
  world.companyInfo = { ...COMPANY, customers: [...COMPANY.customers, ...many] };
}));
