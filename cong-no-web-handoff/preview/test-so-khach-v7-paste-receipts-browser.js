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
  assert.match(await preview.innerText(), /Dòng 2: [\d/]+ · 1\.000\.000 đ · THU TIỀN · CK 1/);
  assert.match(await preview.innerText(), /Dòng 3: [\d/]+ · 2\.000\.000 đ · ỨNG TRƯỚC · UNC 2/);
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
  await drawer(page).locator('.paste-receipts').fill(`${today}\t1.000.000\tCK A\n${today}\t2.000.000\tCK B`);
  world.failNext = { error: 'INVALID_RECEIPT', message: 'Phiếu không hợp lệ.' };
  await drawer(page).locator('.paste-save').click();
  await drawer(page).locator('.paste-error').filter({ hasText: 'Đã ghi 0/2 phiếu' }).waitFor();
  assert.match(await drawer(page).locator('.paste-error').innerText(), /Dòng 1 \([\d/]+, 1\.000\.000 đ\) không ghi được: Phiếu không hợp lệ\. Các dòng chưa ghi còn trong ô\./);
  assert.equal(await drawer(page).locator('.paste-receipts').inputValue(), `${today}\t1.000.000\tCK A\n${today}\t2.000.000\tCK B`);
  // Esc ở bước dán: về bước nhập thường, không đóng khung.
  await page.keyboard.press('Escape');
  assert.equal(await drawer(page).locator('.entry-form').isVisible(), true);
  assert.equal(world.receipts.length, 0);
}, world => { world.total = '10000000'; }));

test('Dán nhiều phiếu, mất mạng giữa chuỗi: ô dán xóa (không bấm lại thành hai phiếu), Thử lại trong khung ghi nốt', async () => withPage(async ({ page, world }) => {
  await openPaste(page);
  await drawer(page).locator('.paste-receipts').fill(`${today}\t1.000.000\tCK A\n${today}\t2.000.000\tCK B\n${today}\t3.000.000\tCK C`);
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
