/* Trình duyệt (Playwright) cho thông báo nổi THONG-BAO-01 (specs/v7-thong-bao.md) trên sổ khách live: tin xong tự tắt,
 * tin cần xem/lỗi giữ tới khi bấm ×, lệnh chưa rõ kết quả vào băng đầu sổ có nút Thử lại. Máy chủ giả, dữ liệu giả. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, tripCell, posts } = require('./so-khach-v7-browser-world');

const toast = page => page.locator('.cn-toast');

test('phân loại câu: xong / cần xem / lỗi', async () => withPage(async ({ page }) => {
  const kinds = await page.evaluate(() => [
    'Đã điền giá theo bảng cho 1 chuyến.',
    'Đã tách phụ phí 2 chuyến theo bảng PS. Tổng tiền không đổi.',
    'Đã lưu. Tham chiếu trùng với phiếu khác trong sổ.',
    'Đã lưu bảng giá; không tải được sổ mới. Tải lại trang để kiểm tra.',
    'Đã duyệt chuyến NEWU1234567. Chưa có giá nên chưa tính tiền.',
    'Sổ vừa thay đổi. Kiểm tra dữ liệu mới rồi thực hiện lại.',
    'Không tải được sổ mới. Thử lại.',
    'Chưa rõ lệnh đã lưu. Thử lại bằng cùng yêu cầu.',
  ].map(window.CongNoThongBao.kindOf));
  assert.deepEqual(kinds, ['ok', 'ok', 'warn', 'warn', 'warn', 'warn', 'error', 'error']);
}));

test('tin xong: nổi góc dưới trái, không che sổ phía trên, tự tắt; rê chuột thì dừng đếm', async () => withPage(async ({ page, shot }) => {
  await page.locator('.book-status').waitFor({ state: 'attached' });
  assert.equal(await page.locator('.book-status').innerText(), '', 'sổ bình thường không có băng');
  await page.clock.install();
  await page.evaluate(() => window.CongNoThongBao.show('Đã điền giá theo bảng cho 1 chuyến.'));
  await toast(page).waitFor();
  assert.equal(await toast(page).getAttribute('role'), 'status');
  assert.equal(await page.locator('.live-notice').innerText(), 'Đã điền giá theo bảng cho 1 chuyến.');
  const box = await toast(page).boundingBox();
  const view = page.viewportSize();
  assert.ok(box.x >= 76 && box.x < 120, `góc trái, sau thanh điều hướng: x=${box.x}`);
  assert.ok(view.height - (box.y + box.height) <= 24, 'sát đáy màn');
  assert.ok(await page.evaluate(() => document.activeElement === document.body || !document.activeElement.closest('.cn-toast')), 'không lấy tiêu điểm');
  await shot('thong-bao-xong');
  await toast(page).hover();
  await page.clock.runFor(15000);
  assert.equal(await toast(page).isVisible(), true, 'đang rê chuột thì không tắt');
  await page.mouse.move(640, 200);
  await page.clock.runFor(6000);
  assert.equal(await toast(page).isVisible(), false);
}));

test('sổ vừa đổi khi lưu: tin cần xem không tự tắt, × và Esc tắt', async () => withPage(async ({ page, world, shot }) => {
  await page.clock.install();
  world.version += 1;   // người khác vừa ghi
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu đổi');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => /Sổ vừa thay đổi/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  assert.match(await toast(page).getAttribute('class'), /is-warn/);
  await page.clock.runFor(30000);
  assert.equal(await toast(page).isVisible(), true, 'tin cần xem giữ tới khi tắt');
  await shot('thong-bao-can-xem');
  await page.locator('.cn-toast-close').click();
  assert.equal(await toast(page).isVisible(), false);
  // Câu mới hiện lại; Esc trong thông báo cũng tắt.
  await page.evaluate(() => window.CongNoThongBao.show('Không tải được sổ mới. Thử lại.'));
  assert.equal(await toast(page).getAttribute('role'), 'alert');
  await page.locator('.cn-toast-close').focus();
  await page.keyboard.press('Escape');
  assert.equal(await toast(page).isVisible(), false);
}));

test('mất mạng khi lưu: không nổi, băng đầu sổ báo chưa rõ kèm Thử lại; Thử lại gửi đúng lệnh một lần rồi băng tắt', async () => withPage(async ({ page, world, shot }) => {
  await page.route('**/api/v7/trips/info', route => route.abort('failed'), { times: 1 });
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu mới');
  await page.keyboard.press('Enter');
  const retry = page.locator('.book-status .retry-command');
  await retry.waitFor();
  assert.match(await page.locator('.book-status-row.is-error').innerText(), /Chưa rõ lệnh đã lưu/);
  assert.equal(await toast(page).isVisible(), false, 'tình trạng ở băng, không nổi thêm');
  assert.equal(posts(world).length, 0);
  await shot('thong-bao-chua-ro');
  await retry.click();
  await page.locator('.book-status .retry-command').waitFor({ state: 'detached' });
  assert.equal(posts(world).length, 1);
  assert.equal(await page.locator('.book-status').innerText(), '');
}));
