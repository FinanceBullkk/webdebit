/* Trình duyệt (Playwright): dán cả cột giá vào ô Đơn giá (GIA-O-01 phần B, specs/v7-o-gia-nhu-sheet.md).
 * Máy chủ giả giữ phiên bản sổ như API thật (lệnh sai phiên bản → STALE_LEDGER, lệnh đúng trả phiên bản mới). Dữ liệu giả. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, posts } = require('./so-khach-v7-browser-world');

// Tháng 9/2026 (mở): sổ gốc 21, 22; chuyến web 11 (50 triệu), 13 (chưa giá), 15 (40 triệu), 14 (chờ kiểm). Tổng còn nợ 100 triệu.
function world(w) {
  const trip = (id, date, extra) => ({ id, month: '2026-09-01', container: `DEMU00000${id}`, carrier: `Tàu ${id}`, event_date: date, origin: 'Nơi E',
    destination: 'Nơi F', unit_price_vnd: '40000000', other_fee_vnd: null, amount_vnd: '40000000', status: 'confirmed', is_missing_price: false,
    is_fee_only: false, editable: true, info_editable: true, deleted: false, ...extra });
  w.trips.push(trip(13, '2026-09-20', { unit_price_vnd: null, amount_vnd: null, is_missing_price: true }), trip(15, '2026-09-21'),
    trip(14, '2026-09-22', { status: 'pending_review', review_reason: 'WEB_DUPLICATE' }));
  w.total = '100000000';
}
const price = (page, id) => page.locator(`td.editable[data-trip="${id}"]`);
const pricePosts = w => posts(w).filter(([path]) => path === '/api/v7/trips/price').map(([, body]) => body);
async function paste(page, id, text) {
  await price(page, id).focus();
  await page.evaluate(value => {
    const data = new DataTransfer();
    data.setData('text/plain', value);
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  }, text);
  await page.locator('.paste-review').waitFor();
}
const toast = page => page.locator('.cn-toast .live-notice');

test('một cột theo thứ tự: xem lại giá cũ → mới và nợ trước → sau, Thôi/Esc không gửi; Ghi gửi lần lượt, phiên bản nối tiếp', async () => withPage(async ({ page, world: w }) => {
  await paste(page, 11, '45000000\n30.000.000\n42,000,000\n47000000\n');
  const review = page.locator('.paste-review');
  const text = await review.innerText();
  assert.match(text, /Ghi giá cho 3 chuyến\?/);
  assert.match(text, /Tổng còn nợ 100\.000\.000 đ → 127\.000\.000 đ/);
  assert.match(text, /DEMU1234567 · 15\/09\/2026 · 50\.000\.000 đ → 45\.000\.000 đ\s*ghi đè giá đang có/);
  assert.match(text, /DEMU0000013 · 20\/09\/2026 · chưa có giá → 30\.000\.000 đ/);
  assert.match(text, /Dòng 4 · DEMU0000014 · không ghi: chờ kiểm/);
  assert.equal(await page.evaluate(() => document.activeElement.classList.contains('paste-cancel')), true, 'tiêu điểm vào Thôi, không vào Ghi');
  await page.keyboard.press('Escape');
  assert.equal(await review.count(), 0);
  assert.equal(await price(page, 11).evaluate(cell => cell === document.activeElement), true, 'Esc trả tiêu điểm về ô đã dán');
  await paste(page, 11, '45000000\n30000000\n42000000');
  await page.locator('.paste-cancel').click();
  assert.equal(pricePosts(w).length, 0);

  await paste(page, 11, '45000000\n30000000\n42000000');
  await page.locator('.paste-write').click();
  await page.waitForFunction(() => document.querySelector('td.editable[data-trip="13"]')?.textContent.startsWith('30.000.000'));
  assert.deepEqual(pricePosts(w).map(body => [body.trip_id, body.unit_price_vnd, body.other_fee_vnd, body.expected_version]),
    [[11, '45000000', null, 1], [13, '30000000', null, 2], [15, '42000000', null, 3]]);
  assert.equal(new Set(pricePosts(w).map(body => body.idempotency_key)).size, 3);
  assert.match(await toast(page).innerText(), /Đã ghi 3 giá\./);
  assert.equal(await page.locator('.paste-review').count(), 0);
  assert.equal(await price(page, 11).evaluate(cell => cell === document.activeElement), true, 'ghi xong tiêu điểm về ô đã dán');
}, world));

test('hai cột theo container; chữ dán sai thì chặn, nêu dòng; đang gõ trong ô thì dán như chữ thường', async () => withPage(async ({ page, world: w }) => {
  await paste(page, 15, 'DEMU0000013\t31000000\nXXXU9999999\t1000000');
  const text = await page.locator('.paste-review').innerText();
  assert.match(text, /Ghi giá cho 1 chuyến\? Ghép theo số container\./);
  assert.match(text, /DEMU0000013 · 20\/09\/2026 · chưa có giá → 31\.000\.000 đ/);
  assert.match(text, /Dòng 2 · XXXU9999999 · không ghi: không có trong sổ/);
  await page.locator('.paste-cancel').click();

  await paste(page, 15, '45000000\nabc');
  assert.match(await page.locator('.paste-review .price-panel.err').innerText(), /Chưa dán được: chưa ghi gì\.[\s\S]*Dòng 2: “abc” không đọc được/);
  assert.equal(await page.locator('.paste-write').count(), 0);
  await page.locator('.paste-cancel').click();
  assert.equal(await price(page, 15).evaluate(cell => cell === document.activeElement), true);

  await page.keyboard.press('Enter');   // mở ô với giá đang có
  await page.evaluate(() => {
    const data = new DataTransfer();
    data.setData('text/plain', '45000000\n46000000');
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  });
  assert.equal(await page.locator('.paste-review').count(), 0);
  assert.equal(pricePosts(w).length, 0);
}, world));

test('mất mạng giữa chừng: Thử lại gửi đúng lệnh cũ rồi ghi tiếp; lỗi giữa chừng thì dừng và báo đã ghi bao nhiêu', async () => {
  await withPage(async ({ page, world: w }) => {
    const lost = [];
    let seen = 0;
    await page.route('**/api/v7/trips/price', async route => {
      seen += 1;
      if (seen === 2) { lost.push(route.request().postDataJSON()); return route.abort(); }
      return route.continue();
    });
    await paste(page, 11, '45000000\n30000000\n42000000');
    await page.locator('.paste-write').click();
    await page.locator('.retry-command').waitFor();
    assert.equal(pricePosts(w).length, 1);
    await page.locator('.retry-command').click();
    await page.waitForFunction(() => document.querySelector('td.editable[data-trip="15"]')?.textContent.startsWith('42.000.000'));
    assert.deepEqual(pricePosts(w)[1], lost[0], 'gửi lại đúng thân lệnh và khóa cũ');
    assert.deepEqual(pricePosts(w).map(body => [body.trip_id, body.expected_version]), [[11, 1], [13, 2], [15, 3]]);
    assert.equal(await page.locator('.retry-command').count(), 0);
  }, world);
  await withPage(async ({ page, world: w }) => {
    let seen = 0;
    await page.route('**/api/v7/trips/price', async route => {
      seen += 1;
      if (seen === 2) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ error: 'STALE_LEDGER', message: 'Sổ vừa thay đổi.' }) });
      return route.continue();
    });
    await paste(page, 11, '45000000\n30000000\n42000000');
    await page.locator('.paste-write').click();
    await page.waitForFunction(() => /Ghi được 1\/3 giá rồi dừng/.test(document.querySelector('.cn-toast .live-notice')?.textContent ?? ''));
    assert.match(await toast(page).innerText(), /Ghi được 1\/3 giá rồi dừng: Sổ vừa thay đổi\./);
    assert.deepEqual(pricePosts(w).map(body => body.trip_id), [11]);
    assert.equal(await page.locator('.retry-command').count(), 0);
  }, world);
});
