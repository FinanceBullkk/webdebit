/* Trình duyệt (Playwright): chọn vùng ô ở bảng chuyến và Ctrl+C chép như Sheet (CHEP-O-01, specs/v7-chep-vung-o.md). Dữ liệu giả.
 * Tháng 9/2026: sổ gốc 21 (OLDU0000001, chưa có giá), 22 (OLDU0000002, 90 triệu); chuyến web 11 (DEMU1234567, 50 triệu). */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, legacyCell, posts } = require('./so-khach-v7-browser-world');

// Bắt đúng chữ trang đặt vào clipboard ở lần Ctrl+C (trình nghe của test chạy sau trình nghe của trang).
async function copy(page) {
  await page.evaluate(() => {
    window.copied = null;
    document.addEventListener('copy', event => { window.copied = event.defaultPrevented ? event.clipboardData.getData('text/plain') : null; }, { once: true });
  });
  await page.keyboard.press('Control+C');
  return page.evaluate(() => window.copied);
}
const center = async locator => { const box = await locator.boundingBox(); return [box.x + box.width / 2, box.y + box.height / 2]; };
const price = page => page.locator('td.editable[data-trip="11"]');
const ranged = page => page.locator('table.trip-list td.cell-range');

test('kéo chuột qua các ô: tô vùng, không mở ô sửa, không bôi chữ; Ctrl+C chép Tab/dòng, số liền, Tuyến hai cột', async () => withPage(async ({ page, world: w }) => {
  const [x1, y1] = await center(legacyCell(page, 21, 'container'));
  const [x2, y2] = await center(price(page));
  await page.mouse.move(x1, y1);
  await page.mouse.down();
  await page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, { steps: 4 });
  await page.mouse.move(x2, y2, { steps: 4 });
  await page.mouse.up();
  assert.equal(await page.locator('table.trip-list input:not([type="checkbox"])').count(), 0, 'kéo xong không mở ô sửa');
  assert.equal(await page.evaluate(() => String(window.getSelection())), '', 'không bôi chữ của trình duyệt');
  assert.equal(await ranged(page).count(), 3 * 6, 'ba hàng × sáu cột (Container → Đơn giá)');
  assert.equal(await copy(page), [
    'OLDU0000001\tXe 1\tChủ hàng thử\t02/09/2026\tNơi C\tNơi D\t',
    'OLDU0000002\tXe 2\t\t03/09/2026\tNơi C\tNơi D\t90000000',
    'DEMU1234567\tTàu thử\t\t15/09/2026\tNơi A\tNơi B\t50000000',
  ].join('\n'));
  assert.match(await page.locator('.cn-toast').innerText(), /Đã chép 3 hàng × 7 cột/);
  // Bấm ra chỗ khác thì bỏ vùng; chép chỉ đọc, không gửi lệnh nào.
  await page.mouse.click(5, 5);
  assert.equal(await ranged(page).count(), 0);
  assert.equal(posts(w).length, 0);
}));

test('đứng ở ô: Ctrl+C chép một ô; Shift+mũi tên, Shift+bấm mở rộng vùng; Esc bỏ vùng', async () => withPage(async ({ page }) => {
  await price(page).focus();
  assert.equal(await copy(page), '50000000');
  await page.keyboard.press('Shift+ArrowUp');
  await page.keyboard.press('Shift+ArrowUp');
  await page.keyboard.press('Shift+ArrowLeft');
  assert.equal(await copy(page), 'Nơi C\tNơi D\t\nNơi C\tNơi D\t90000000\nNơi A\tNơi B\t50000000');
  assert.equal(await page.locator('table.trip-list input:not([type="checkbox"])').count(), 0);
  await page.keyboard.press('Escape');
  assert.equal(await ranged(page).count(), 0);
  assert.equal(await copy(page), '50000000', 'bỏ vùng thì lại chép ô đang đứng');

  // Shift+bấm: từ ô đang đứng tới ô bấm, không mở ô sửa của ô bấm.
  await legacyCell(page, 22, 'carrier').click({ modifiers: ['Shift'] });
  assert.equal(await page.locator('table.trip-list input:not([type="checkbox"])').count(), 0);
  assert.equal(await copy(page), 'Xe 2\t\t03/09/2026\tNơi C\tNơi D\t90000000\nTàu thử\t\t15/09/2026\tNơi A\tNơi B\t50000000');
  // Đang gõ trong ô: Ctrl+C là của ô nhập, trang không chen vào.
  await legacyCell(page, 22, 'carrier').click();
  await page.locator('table.trip-list input:not([type="checkbox"])').waitFor();
  assert.equal(await copy(page), null);
}));
