/* Trình duyệt (Playwright) cho dán nhiều phiếu vào một sổ và phiếu điền sẵn từ trang Thu chi (PHIEU-WEB-01 mục 3–4).
 * Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { clock, withPage, posts, settled } = require('./so-khach-v7-browser-world');

const today = `${clock.slice(8, 10)}/${clock.slice(5, 7)}/${clock.slice(0, 4)}`;
const drawer = page => page.locator('.entry-drawer');
const receiptPosts = world => posts(world).filter(([path]) => path === '/api/v7/receipts').map(([, body]) => body);
async function openPaste(page) {
  await page.locator('.entry-open').click();
  await drawer(page).locator('.entry-paste-open').click();
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('paste-receipts')), true);
}

test('Dán nhiều phiếu: xem trước từng dòng và tổng nợ trước → sau, mỗi dòng một lệnh ghi theo thứ tự', async () => withPage(async ({ page, world, shot }) => {
  await openPaste(page);
  await drawer(page).locator('.paste-receipts').fill(`Ngày\tSố tiền\tHình thức\tTham chiếu\n${today}\t1.000.000\t\tCK 1\n${today}\t2000000\tỨng trước\tUNC 2`);
  const preview = drawer(page).locator('.paste-preview');
  assert.match(await preview.innerText(), /2 phiếu, tổng 3\.000\.000 đ\. Tổng còn nợ: 10\.000\.000 đ → 7\.000\.000 đ\./);
  assert.match(await preview.innerText(), /Dòng 2: [\d/]+ \(\d+ tháng \d+\) · 1\.000\.000 đ · THU TIỀN · CK 1/);
  assert.match(await preview.innerText(), /Dòng 3: [\d/]+ \(\d+ tháng \d+\) · 2\.000\.000 đ · ỨNG TRƯỚC · UNC 2/);
  assert.equal(await drawer(page).locator('.paste-save').innerText(), 'Ghi 2 phiếu');
  await settled(page);
  assert.equal(receiptPosts(world).length, 0, 'dán và xem trước chưa gửi lệnh nào');
  await shot('dan-nhieu-phieu');
  await drawer(page).locator('.paste-save').click();
  await drawer(page).waitFor({ state: 'hidden' });
  await settled(page);
  const sent = receiptPosts(world);
  assert.deepEqual(sent.map(body => [body.date, body.method, body.amount_vnd, body.reference, body.expected_version]),
    [[clock, 'THU TIỀN', '1000000', 'CK 1', 1], [clock, 'ỨNG TRƯỚC', '2000000', 'UNC 2', 2]]);
  assert.notEqual(sent[0].idempotency_key, sent[1].idempotency_key);
  assert.match(await page.locator('.cn-toast-text').innerText(), /Đã ghi 2 phiếu\./);
  // Mở lại khung: về bước nhập thường, ô dán trống.
  await page.locator('.entry-open').click();
  assert.equal(await drawer(page).locator('.entry-form').isVisible(), true);
  await drawer(page).locator('.entry-paste-open').click();
  assert.equal(await drawer(page).locator('.paste-receipts').inputValue(), '');
}, world => { world.total = '10000000'; }));

test('Dán nhiều phiếu: còn dòng lỗi thì không ghi; máy chủ từ chối thì dừng, dòng chưa ghi ở lại trong ô', async () => withPage(async ({ page, world }) => {
  await openPaste(page);
  await drawer(page).locator('.paste-receipts').fill(`${today}\t1.000.000\n${today}\tabc\n01/01/2099\t5\n${today}\t5\tcấn trừ`);
  const text = await drawer(page).locator('.paste-preview').innerText();
  assert.match(text, /Dòng 2: “abc” không đọc được thành số tiền\./);
  assert.match(text, /Dòng 3: ngày 01\/01\/2099 sau hôm nay\./);
  assert.match(text, /Dòng 4: cấn trừ phải ghi từng phiếu/);
  assert.equal(await drawer(page).locator('.paste-save').isDisabled(), true);
  await drawer(page).locator('.paste-receipts').fill(`${today}\t1.000.000\t\tCK A\n${today}\t2.000.000\t\tCK B`);
  world.failNext = { error: 'INVALID_RECEIPT', message: 'Phiếu không hợp lệ.' };
  await drawer(page).locator('.paste-save').click();
  await drawer(page).locator('.paste-error').filter({ hasText: 'Đã ghi 0/2 phiếu' }).waitFor();
  assert.match(await drawer(page).locator('.paste-error').innerText(), /Dòng 1 \([\d/]+, 1\.000\.000 đ\) không ghi được: Phiếu không hợp lệ\. Các dòng chưa ghi còn trong ô\./);
  assert.equal(await drawer(page).locator('.paste-receipts').inputValue(), `${today}\t1.000.000\t\tCK A\n${today}\t2.000.000\t\tCK B`);
  // Esc ở bước dán: về bước nhập thường, không đóng khung.
  await page.keyboard.press('Escape');
  assert.equal(await drawer(page).locator('.entry-form').isVisible(), true);
  assert.equal(world.receipts.length, 0);
}, world => { world.total = '10000000'; }));

test('Dán nhiều phiếu, mất mạng giữa chuỗi: ô dán xóa (không bấm lại thành hai phiếu), Thử lại trong khung ghi nốt', async () => withPage(async ({ page, world }) => {
  await openPaste(page);
  await drawer(page).locator('.paste-receipts').fill(`${today}\t1.000.000\t\tCK A\n${today}\t2.000.000\t\tCK B\n${today}\t3.000.000\t\tCK C`);
  let seen = 0;
  await page.route('**/api/v7/receipts', route => (++seen === 2 ? route.abort() : route.continue()));
  await drawer(page).locator('.paste-save').click();
  await drawer(page).locator('.paste-error').filter({ hasText: 'chưa rõ đã lưu' }).waitFor();
  assert.match(await drawer(page).locator('.paste-error').innerText(), /Đã ghi 1\/3 phiếu; phiếu tiếp theo chưa rõ đã lưu.*Đừng dán lại\./);
  assert.equal(await drawer(page).locator('.paste-receipts').inputValue(), '');
  assert.equal(await drawer(page).locator('.paste-save').isDisabled(), true);
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('paste-retry')), true);
  await drawer(page).locator('.paste-retry').click();
  await drawer(page).waitFor({ state: 'hidden' });
  await settled(page);
  assert.deepEqual(world.receipts.map(row => [row.amount_vnd, row.reference]), [['1000000', 'CK A'], ['2000000', 'CK B'], ['3000000', 'CK C']]);
  assert.match(await page.locator('.cn-toast-text').innerText(), /Đã ghi 3 phiếu\./);
}, world => { world.total = '10000000'; }));

test('Review #676: số nghi nhầm đơn vị phải bấm "Đúng số này"; dòng có thể đã ghi mặc định không ghi; cảnh báo ngày đảo, nhiều tháng', async () => withPage(async ({ page, world, shot }) => {
  await openPaste(page);
  await drawer(page).locator('.paste-receipts').fill(`${today}\t50\n${today}\t5.000.000\t\tCK trùng\n${today}\t2.000.000\t\tCK mới`);
  const preview = drawer(page).locator('.paste-preview');
  let text = await preview.innerText();
  assert.match(text, /2 phiếu, tổng 2\.000\.050 đ/, 'dòng có thể đã ghi không tính');
  assert.match(text, /Dòng 2:[^\n]*không ghi/);
  assert.match(text, /Vẫn ghi: có thể đã ghi rồi \(PH-001 cùng số tiền/);
  assert.match(text, /Bấm "Đúng số này" ở dòng 1 rồi mới ghi được\./);
  assert.equal(await drawer(page).locator('.paste-save').isDisabled(), true);
  await shot('dan-nhieu-phieu-hoi');
  await drawer(page).locator('.paste-ok[data-line="1"]').check();
  assert.equal(await drawer(page).locator('.paste-save').innerText(), 'Ghi 2 phiếu');
  await drawer(page).locator('.paste-dup[data-line="2"]').check();
  assert.equal(await drawer(page).locator('.paste-save').innerText(), 'Ghi 3 phiếu');
  await drawer(page).locator('.paste-dup[data-line="2"]').uncheck();
  await drawer(page).locator('.paste-save').click();
  await drawer(page).waitFor({ state: 'hidden' });
  await settled(page);
  assert.deepEqual(receiptPosts(world).map(body => [body.amount_vnd, body.reference ?? null]), [['50', null], ['2000000', 'CK mới']]);
  // Bảng có dấu hiệu tháng/ngày: nhắc ở bản xem trước, đánh dấu từng dòng mơ hồ; lô nhiều tháng cũng nhắc.
  await openPaste(page);
  await drawer(page).locator('.paste-receipts').fill(`5/1/2026\t3.000.000\n3/13/2026\t3.000.000`);
  text = await preview.innerText();
  assert.match(text, /Dòng 2 ghi ngày kiểu tháng\/ngày/);
  assert.match(text, /Dòng 1: 05\/01\/2026 \(5 tháng 1\) \(kiểm ngày\/tháng\)/);
  await drawer(page).locator('.paste-receipts').fill(`5/10/2026\t3.000.000\n${today}\t3.000.000`);
  assert.match(await preview.innerText(), /Các phiếu nằm ở 2 tháng/);
  assert.match(await preview.innerText(), /Dòng 1 nằm ở tháng đang khóa; phiếu vẫn ghi được\./);
}, world => {
  world.total = '10000000';
  // Sổ đã có phiếu 5.000.000 đ hôm nay: dòng cùng số trong ±3 ngày là "có thể đã ghi".
  world.receipts.push({ id: 1, pid: 'PH-001', date: clock, method: 'THU TIỀN', amount_vnd: '5000000', reference: null, voided_by_event: null, void_reason: null,
    allocations: [{ id: 1, month: `${clock.slice(0, 7)}-01`, kind: 'debt', amount_vnd: '5000000', superseded_by_event: null }] });
}));

test('Review #676 lần 2: ngày bằng chữ; dòng giống dòng trước trong bảng không ghi; "Đúng cả bảng"; sổ đổi sau xem trước thì dừng, xem lại', async () => withPage(async ({ page, world }) => {
  await openPaste(page);
  await drawer(page).locator('.paste-receipts').fill(`${today}\t50\t\tA\n${today}\t60\t\tB\n${today}\t3.000.000\t\tUNC 9\n${today}\t3.000.000\t\tUNC 9\n${today}\t500.000\t\tlẻ`);
  const preview = drawer(page).locator('.paste-preview');
  let text = await preview.innerText();
  const words = `${Number(clock.slice(8))} tháng ${Number(clock.slice(5, 7))}`;
  assert.ok(text.includes(`Dòng 1: ${today} (${words})`), 'ngày bằng chữ cạnh ngày số');
  assert.match(text, /Dòng 4:[^\n]*không ghi/);
  assert.match(text, /Vẫn ghi: giống dòng 3 trong bảng này/);
  assert.doesNotMatch(text, /Dòng 5:[^\n]*\n[^\n]*Đúng số này/, '500.000 đ là khoản lẻ thật, không hỏi');
  assert.match(text, /Bấm "Đúng số này" ở dòng 1, 2 rồi mới ghi được\./);
  await drawer(page).locator('.paste-ok-all').click();
  assert.equal(await drawer(page).locator('.paste-save').innerText(), 'Ghi 4 phiếu');
  assert.equal(await drawer(page).locator('.paste-ok:checked').count(), 2);
  // Sổ đổi trong lúc khung đóng (người khác ghi một phiếu 500.000 đ): mở lại, bấm Ghi thì dừng và vẽ lại bản xem trước.
  await drawer(page).locator('.entry-close').click();
  world.receipts.push({ id: 9, pid: 'PH-009', date: clock, method: 'THU TIỀN', amount_vnd: '500000', reference: null, voided_by_event: null, void_reason: null,
    allocations: [{ id: 9, month: `${clock.slice(0, 7)}-01`, kind: 'debt', amount_vnd: '500000', superseded_by_event: null }] });
  world.version += 1;
  const reads = world.reads;
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  for (let tries = 0; tries < 50 && world.reads <= reads; tries += 1) await page.waitForTimeout(100);
  await settled(page);
  assert.ok(world.reads > reads, 'sổ đọc lại khi khung đóng');
  await page.locator('.entry-open').click();
  await drawer(page).locator('.paste-save').click();
  await drawer(page).locator('.paste-error').filter({ hasText: 'Sổ vừa thay đổi sau bản xem trước' }).waitFor();
  text = await preview.innerText();
  assert.match(text, /Vẫn ghi: có thể đã ghi rồi \(PH-009/);
  assert.equal(await drawer(page).locator('.paste-save').innerText(), 'Ghi 3 phiếu', 'bản xem trước mới: dòng 500.000 đ thành có thể đã ghi');
  await settled(page);
  assert.equal(receiptPosts(world).length, 0, 'không ghi theo danh sách cũ');
}, world => { world.total = '10000000'; }));

test('Review #676 lần 2: khung một phiếu cùng luật hỏi lại số dưới 100.000 đ', async () => withPage(async ({ page, world }) => {
  await page.locator('.entry-open').click();
  await drawer(page).locator('.receipt-date').fill(today);
  await drawer(page).locator('.receipt-amount').fill('50');
  await drawer(page).locator('.receipt-amount').press('Enter');
  assert.match(await drawer(page).locator('.entry-review').innerText(), /Đúng số này\. 50 đ là dưới 100\.000 đ/);
  await drawer(page).locator('.receipt-save').click();
  assert.match(await drawer(page).locator('.entry-error').innerText(), /bấm "Đúng số này" trước khi ghi/);
  await settled(page);
  assert.equal(receiptPosts(world).length, 0);
  await drawer(page).locator('.entry-doubt-ok').check();
  await drawer(page).locator('.receipt-save').click();
  await page.locator('.saved-strip').waitFor();
  assert.deepEqual(receiptPosts(world).map(body => body.amount_vnd), ['50']);
}, world => { world.total = '10000000'; }));

test('Review #676: Thử lại vẫn mất kết nối thì giữ nút Thử lại trong khung, không mất chuỗi', async () => withPage(async ({ page, world }) => {
  await openPaste(page);
  await drawer(page).locator('.paste-receipts').fill(`${today}\t1.000.000\t\tCK A\n${today}\t2.000.000\t\tCK B`);
  let seen = 0;
  await page.route('**/api/v7/receipts', route => (++seen <= 2 ? route.abort() : route.continue()));
  await drawer(page).locator('.paste-save').click();
  await drawer(page).locator('.paste-retry').waitFor();
  await drawer(page).locator('.paste-retry').click();
  await drawer(page).locator('.paste-error').filter({ hasText: 'Vẫn chưa rõ' }).waitFor();
  assert.equal(await drawer(page).locator('.paste-retry').isEnabled(), true);
  await drawer(page).locator('.paste-retry').click();
  await drawer(page).waitFor({ state: 'hidden' });
  await settled(page);
  assert.deepEqual(world.receipts.map(row => row.reference), ['CK A', 'CK B']);
}, world => { world.total = '10000000'; }));

test('Phiếu từ Thu chi: mở khung của đúng sổ, điền sẵn ngày, số tiền, tham chiếu; chưa gửi lệnh; nháp dùng một lần', async () => withPage(async ({ page, world, shot }) => {
  await drawer(page).waitFor({ state: 'visible' });
  assert.equal(await drawer(page).locator('.receipt-date').inputValue(), today);
  assert.equal(await drawer(page).locator('.receipt-amount').inputValue(), '5.000.000');
  assert.equal(await drawer(page).locator('.receipt-reference').inputValue(), 'CK NH thử 14:32 (ảnh Zalo)');
  assert.match(await drawer(page).locator('.entry-from').innerText(), /Điền sẵn từ Thu chi/);
  assert.equal(new URL(page.url()).searchParams.has('ghi-phieu'), false, 'bỏ dấu ghi-phieu khỏi địa chỉ, tải lại không mở lần nữa');
  assert.equal(await page.evaluate(() => sessionStorage.getItem('webdebit:phieu-nhap')), null);
  await shot('phieu-tu-thu-chi');
  await settled(page);
  assert.equal(receiptPosts(world).length, 0, 'chỉ điền sẵn, người tự bấm ghi');
  await drawer(page).locator('.receipt-amount').press('Enter');
  await drawer(page).locator('.receipt-save').click();
  await page.locator('.saved-strip').waitFor();
  assert.deepEqual(receiptPosts(world).map(body => [body.date, body.amount_vnd, body.reference]), [[clock, '5000000', 'CK NH thử 14:32 (ảnh Zalo)']]);
}, world => {
  world.query = '&ghi-phieu=1';
  world.beforeOpen = page => page.addInitScript(([date]) => {
    if (sessionStorage.getItem('test-seeded')) return;
    sessionStorage.setItem('test-seeded', '1');
    sessionStorage.setItem('webdebit:phieu-nhap', JSON.stringify({ customerId: 1, date, amount: '5000000', reference: 'CK NH thử 14:32 (ảnh Zalo)', at: Date.now() }));
  }, [clock]);
}));

test('Phiếu từ Thu chi của sổ khác hay nháp cũ: không mở khung, không điền', async () => withPage(async ({ page }) => {
  await page.waitForTimeout(300);
  assert.equal(await drawer(page).isHidden(), true);
  assert.equal(await page.evaluate(() => sessionStorage.getItem('webdebit:phieu-nhap')), null, 'nháp không đúng sổ cũng bị bỏ');
}, world => {
  world.query = '&ghi-phieu=1';
  world.beforeOpen = page => page.addInitScript(() => {
    if (sessionStorage.getItem('test-seeded')) return;
    sessionStorage.setItem('test-seeded', '1');
    sessionStorage.setItem('webdebit:phieu-nhap', JSON.stringify({ customerId: 2, date: '2026-11-01', amount: '5000000', reference: 'x', at: Date.now() }));
  });
}));
