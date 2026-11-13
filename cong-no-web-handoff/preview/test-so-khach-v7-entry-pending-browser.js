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

test('phiếu chưa rõ: không cho Sửa lại sang phiếu khác; Thử lại ghi đúng phiếu cũ, báo đúng số của nó', async () => withPage(async ({ page, world }) => {
  await unknownReceipt(page, '2000');
  await drawer(page).locator('.entry-back').click();
  assert.match(await drawer(page).locator('.entry-error').innerText(), /Bấm Thử lại \(phiếu không bị ghi hai lần\) trước khi sửa/);
  assert.equal(await drawer(page).locator('.entry-review').isVisible(), true, 'vẫn ở bước xem lại của phiếu chưa rõ');
  await drawer(page).locator('.receipt-save').click();
  assert.equal(receiptPosts(world).length, 0);
  // Đóng rồi mở lại khung khi phiếu còn chờ: vẫn là bước xem lại của đúng phiếu đó.
  await drawer(page).locator('.entry-close').click();
  await page.locator('.entry-open').click();
  assert.equal(await drawer(page).locator('.entry-review').isVisible(), true);
  await drawer(page).locator('.entry-retry').click();
  await page.locator('.saved-strip').waitFor();
  assert.deepEqual(receiptPosts(world).map(([, body]) => body.amount_vnd), ['2000']);
  assert.match(await page.locator('.saved-strip').innerText(), /2\.000/);
}));

test('phiếu chưa rõ đã lưu nhờ Thử lại ở đầu sổ: Ghi phiếu, Thử lại hay mở lại khung đều không gửi lần hai, hiện băng đã ghi', async () => {
  for (const how of ['.receipt-save', '.entry-retry', 'reopen']) {
    await withPage(async ({ page, world }) => {
      await unknownReceipt(page, '2000');
      if (how === 'reopen') await drawer(page).locator('.entry-close').click();
      await page.locator('.retry-command').evaluate(node => node.click());   // nút ở đầu sổ (khung phiếu có thể che)
      await page.waitForFunction(() => !document.querySelector('.retry-command'));
      assert.equal(receiptPosts(world).length, 1);
      if (how === 'reopen') await page.locator('.entry-open').click(); else await drawer(page).locator(how).click();
      await page.locator('.saved-strip').waitFor();
      assert.match(await page.locator('.saved-strip').innerText(), /2\.000/);
      assert.equal(await drawer(page).isHidden(), true);
      assert.equal(receiptPosts(world).length, 1, `${how}: không gửi phiếu lần hai`);
    });
  }
});

test('Thử lại ở khung bị từ chối (sổ vừa đổi): nói rõ chưa ghi, Ghi phiếu sau đó là phiếu mới, đúng một phiếu', async () => withPage(async ({ page, world }) => {
  await unknownReceipt(page, '2000');
  world.version += 1;   // sổ đổi ở máy khác trong lúc mất mạng: lệnh cũ (chưa tới server) bị từ chối vì phiên bản
  await drawer(page).locator('.entry-retry').click();
  await drawer(page).locator('.entry-error').filter({ hasText: 'Sổ vừa thay đổi' }).waitFor();
  assert.equal(world.receipts.length, 0);
  await drawer(page).locator('.receipt-save').click();
  await page.locator('.saved-strip').waitFor();
  assert.equal(world.receipts.length, 1);
}));

test('phiếu chưa rõ: Esc ở bước xem lại không về bước nhập; bấm Thử lại hai lần không lỗi, đúng một phiếu', async () => withPage(async ({ page, world }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await unknownReceipt(page, '2000');
  await drawer(page).locator('.receipt-save').focus();
  await page.keyboard.press('Escape');
  assert.equal(await drawer(page).locator('.entry-review').isVisible(), true, 'Esc không về bước nhập khi phiếu còn chờ');
  assert.match(await drawer(page).locator('.entry-error').innerText(), /trước khi sửa/);
  await page.route('**/api/v7/receipts', async route => { await new Promise(resolve => setTimeout(resolve, 300)); return route.continue(); });
  await drawer(page).locator('.entry-retry').first().click();
  await drawer(page).locator('.receipt-save').evaluate(node => node.click()).catch(() => {});
  await drawer(page).locator('.entry-retry').first().evaluate(node => node.click()).catch(() => {});
  await page.locator('.saved-strip').waitFor();
  assert.equal(world.receipts.length, 1);
  assert.deepEqual(errors, []);
}));
