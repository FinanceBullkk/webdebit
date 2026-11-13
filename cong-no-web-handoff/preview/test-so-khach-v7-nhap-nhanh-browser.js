/* Trình duyệt (Playwright): gõ xong hiện ngay như Sheet, lệnh ghi nền theo hàng đợi (NHAP-NHANH-01, specs/nhap-nhanh-01.md).
 * Máy chủ giả ghi chậm 400 ms để thấy ô hiện trước khi máy chủ trả lời. Dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, tripCell, posts } = require('./so-khach-v7-browser-world');

const WRITES = /\/api\/v7\/(trips\/(info|price|delete)|legacy\/(edit|delete))$/;
const slow = page => page.route(url => WRITES.test(url.pathname), async route => {
  await new Promise(done => setTimeout(done, 400));
  await route.continue();
});
const writes = world => posts(world).filter(([path]) => WRITES.test(path));
const idle = page => page.waitForFunction(() => !document.querySelector('.book-status-row.is-saving'));
const amount = page => page.locator('tr[data-row="trip-11"] > td:last-child');

test('gõ ba ô liên tiếp: cả ba hiện ngay, lệnh đi lần lượt với phiên bản nối tiếp, sổ chỉ đọc lại một lần', async () => withPage(async ({ page, world }) => {
  await slow(page);
  const reads = world.reads;
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu 1');
  await page.keyboard.press('Enter');
  assert.equal(await tripCell(page, 'carrier').innerText(), 'Tàu 1', 'hiện ngay, chưa chờ máy chủ');
  await tripCell(page, 'destination').click();
  await page.locator('.info-input').fill('Nơi mới');
  await page.keyboard.press('Tab');
  assert.equal(await tripCell(page, 'destination').innerText(), 'Nơi mới');
  await page.locator('td.editable[data-trip="11"]').focus();
  await page.keyboard.type('45000000');
  await page.keyboard.press('Enter');
  assert.match(await page.locator('td.editable[data-trip="11"]').innerText(), /^45\.000\.000/);
  assert.equal(await amount(page).innerText(), '…', 'Thành tiền chờ máy chủ tính, trang không tự cộng');
  await page.locator('.book-status-row.is-saving').waitFor();

  await idle(page);
  await page.waitForFunction(() => document.querySelector('tr[data-row="trip-11"] > td:last-child')?.textContent === '45.000.000');
  assert.deepEqual(writes(world).map(([path, body]) => [path, body.expected_version]),
    [['/api/v7/trips/info', 1], ['/api/v7/trips/info', 2], ['/api/v7/trips/price', 3]]);
  assert.equal(world.reads - reads, 1, 'đọc lại sổ một lần sau lệnh cuối');
  assert.equal(await tripCell(page, 'carrier').innerText(), 'Tàu 1');
  assert.equal(await page.locator('.live-notice').isVisible(), false, '"Đã lưu." không nổi');
}));

test('xóa dòng: dòng biến mất ngay, lệnh xóa ghi nền một lần', async () => withPage(async ({ page, world }) => {
  await slow(page);
  await page.locator('td.row-delete[data-kind="trip"][data-id="11"]').click();
  await page.locator('.delete-prompt .confirm-delete').click();
  assert.equal(await page.locator('tr[data-row="trip-11"], .delete-prompt').count(), 0, 'mất ngay, chưa chờ máy chủ');
  await idle(page);
  assert.equal(await page.locator('tr[data-row="trip-11"]').count(), 0);
  assert.deepEqual(writes(world).map(([path, body]) => [path, body.trip_id]), [['/api/v7/trips/delete', 11]]);
}));

test('lệnh thứ hai bị từ chối: ô đó và ô gõ sau về số cũ, tin báo nói ô nào chưa lưu và bao nhiêu ô sau đó', async () => withPage(async ({ page, world }) => {
  let sent = 0;
  await page.route(url => url.pathname === '/api/v7/trips/info', async route => {
    await new Promise(done => setTimeout(done, 300));
    if (++sent === 2) await route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ error: 'INVALID_TRIP_INPUT', message: 'Thiếu thông tin chuyến.' }) });
    else await route.continue();
  });
  for (const [field, value] of [['carrier', 'Tàu 1'], ['origin', 'Nơi X'], ['destination', 'Nơi Y']]) {
    await tripCell(page, field).click();
    await page.locator('.info-input').fill(value);
    await page.keyboard.press('Enter');
  }
  assert.deepEqual([await tripCell(page, 'origin').innerText(), await tripCell(page, 'destination').innerText()], ['Nơi X', 'Nơi Y']);
  await page.waitForFunction(() => /Chưa lưu ô nơi đi của chuyến DEMU1234567: Thiếu thông tin chuyến\. 1 ô sửa sau đó cũng chưa lưu/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  await page.waitForFunction(() => document.querySelector('.info-edit[data-kind="trip"][data-field="origin"]')?.textContent === 'Nơi A');
  assert.equal(await tripCell(page, 'destination').innerText(), 'Nơi B', 'ô gõ sau ô lỗi không gửi, về số cũ');
  assert.equal(await tripCell(page, 'carrier').innerText(), 'Tàu 1', 'ô trước đã lưu');
  assert.deepEqual(writes(world).map(([, body]) => body.field), ['carrier']);
  assert.equal(await page.locator('.retry-command').count(), 0);
}));

test('mất mạng ở lệnh giữa: băng đầu sổ có Thử lại; Thử lại gửi lại đúng lệnh đó (cùng khóa) rồi ghi nốt, không trùng', async () => withPage(async ({ page, world }) => {
  let sent = 0, lostKey = null;
  await page.route(url => url.pathname === '/api/v7/trips/info', async route => {
    await new Promise(done => setTimeout(done, 200));
    if (++sent === 2) { lostKey = JSON.parse(route.request().postData()).idempotency_key; await route.abort(); }
    else await route.continue();
  });
  for (const [field, value] of [['carrier', 'Tàu 1'], ['origin', 'Nơi X'], ['destination', 'Nơi Y']]) {
    await tripCell(page, field).click();
    await page.locator('.info-input').fill(value);
    await page.keyboard.press('Enter');
  }
  await page.locator('.retry-command').waitFor();
  assert.match(await page.locator('.book-status').innerText(), /Chưa rõ/);
  assert.equal(await tripCell(page, 'destination').innerText(), 'Nơi Y', 'ô chưa ghi vẫn giữ chữ vừa gõ');
  assert.deepEqual(writes(world).map(([, body]) => body.field), ['carrier']);
  await page.locator('.retry-command').click();
  await idle(page);
  await page.waitForFunction(() => !document.querySelector('.retry-command'));
  const sentNow = writes(world);
  assert.deepEqual(sentNow.map(([, body]) => [body.field, body.expected_version]), [['carrier', 1], ['origin', 2], ['destination', 3]]);
  assert.equal(sentNow[1][1].idempotency_key, lostKey, 'gửi lại cùng khóa');
  assert.deepEqual([await tripCell(page, 'origin').innerText(), await tripCell(page, 'destination').innerText()], ['Nơi X', 'Nơi Y']);
}));

test('ghi phiếu thu trong lúc hàng đợi còn lệnh: chờ hàng đợi xong rồi mới gửi, không báo "chưa rõ kết quả"', async () => withPage(async ({ page, world }) => {
  await slow(page);
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu 1');
  await page.keyboard.press('Enter');
  await page.locator('.entry-open').click();
  await page.locator('.entry-drawer .receipt-date').fill('20/09/2026');
  await page.locator('.entry-drawer .receipt-amount').fill('1.000.000');
  await page.locator('.entry-drawer .receipt-amount').press('Enter');
  const receipt = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v7/receipts');
  await page.locator('.entry-drawer .receipt-save').click();
  assert.equal(await page.locator('.entry-drawer .entry-error').innerText(), '', 'không chặn vì lệnh đang ghi nền');
  await receipt;
  const order = posts(world).map(([path]) => path).filter(path => path === '/api/v7/trips/info' || path === '/api/v7/receipts');
  assert.deepEqual(order, ['/api/v7/trips/info', '/api/v7/receipts'], 'phiếu thu gửi sau khi hàng đợi ghi xong');
  assert.doesNotMatch(await page.locator('.book-status').innerText(), /chưa rõ/i);
}));
