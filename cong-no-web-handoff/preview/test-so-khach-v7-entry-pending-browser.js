/* Trình duyệt (Playwright): khung Ghi phiếu thu khi còn lệnh chưa rõ kết quả (review GIA-O-01 B). Phiếu "chưa rõ" của khung
 * chỉ được Thử lại đúng phiếu đó; đã có kết quả ở đầu sổ thì không gửi lại. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { clock, withPage, posts } = require('./so-khach-v7-browser-world');

const today = `${clock.slice(8, 10)}/${clock.slice(5, 7)}/${clock.slice(0, 4)}`;
const drawer = page => page.locator('.entry-drawer');
const receiptPosts = world => posts(world).filter(([path]) => path === '/api/v7/receipts');
async function fill(page, date, amount) {
  if (await drawer(page).isHidden()) await page.locator('.entry-open').click();
  await drawer(page).locator('.receipt-date').fill(date);
  await drawer(page).locator('.receipt-amount').fill(amount);
  await drawer(page).locator('.receipt-amount').press('Enter');
}
async function unknownReceipt(page, amount) {
  await fill(page, today, amount);
  await page.route('**/api/v7/receipts', route => route.abort(), { times: 1 });
  await drawer(page).locator('.receipt-save').click();
  await drawer(page).locator('.entry-retry').waitFor();
}

test('phiếu chưa rõ rồi sửa lại sang số khác: không gửi phiếu mới; Thử lại ghi đúng phiếu cũ và báo đúng số của phiếu cũ', async () => withPage(async ({ page, world }) => {
  await unknownReceipt(page, '2000');
  await drawer(page).locator('.entry-back').click();
  await drawer(page).locator('.receipt-amount').fill('3000');
  await drawer(page).locator('.receipt-amount').press('Enter');
  await drawer(page).locator('.receipt-save').click();
  assert.match(await drawer(page).locator('.entry-error').innerText(), /Phiếu vừa gửi chưa rõ đã lưu chưa/);
  assert.equal(receiptPosts(world).length, 0);
  await drawer(page).locator('.entry-retry').click();
  await page.locator('.saved-strip').waitFor();
  assert.deepEqual(receiptPosts(world).map(([, body]) => body.amount_vnd), ['2000']);
  const strip = await page.locator('.saved-strip').innerText();
  assert.match(strip, /2\.000/);
  assert.doesNotMatch(strip, /3\.000/);
}));

test('phiếu chưa rõ đã Thử lại ở đầu sổ: Ghi phiếu hay Thử lại ở khung không gửi lần hai, khung đóng và báo kiểm danh sách', async () => {
  for (const button of ['.receipt-save', '.entry-retry']) {
    await withPage(async ({ page, world }) => {
      await unknownReceipt(page, '2000');
      await page.locator('.retry-command').evaluate(node => node.click());   // nút ở đầu sổ (khung phiếu có thể che)
      await page.waitForFunction(() => !document.querySelector('.retry-command'));
      assert.equal(receiptPosts(world).length, 1);
      await drawer(page).locator(button).click();
      assert.equal(await drawer(page).isHidden(), true);
      assert.equal(receiptPosts(world).length, 1, 'không gửi phiếu lần hai');
      assert.match(await page.locator('.cn-toast .live-notice').innerText(), /đã có kết quả/);
    });
  }
});
