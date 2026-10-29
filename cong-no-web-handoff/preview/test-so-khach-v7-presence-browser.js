/* Trình duyệt (Playwright) cho PRESENCE-01 mức 1 trên sổ khách V7: người khác đang ở đâu, ô đang chọn/đang sửa,
 * câu báo sổ vừa đổi kèm tên. Máy chủ giả không có SSE nên trang hỏi định kỳ. Dữ liệu giả. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage, tripCell } = require('./so-khach-v7-browser-world');

const lan = { id: 'p1', name: 'Lan', color: 0, page: 'so-khach', customer_id: 1, month: '2026-09', cell: { row: 'trip:11', col: 'c2', editing: true }, pointer: null };
const hoa = { id: 'p2', name: 'Hoa', color: 2, page: 'dashboard', customer_id: null, month: null, cell: null, pointer: null };

test('thấy người khác: vòng tròn, ô đang sửa, bấm vòng tròn thì tới ô đó', async () => withPage(async ({ page, shot }) => {
  await page.locator('.presence-avatar').nth(1).waitFor();
  const avatars = await page.locator('.presence-avatar').evaluateAll(nodes => nodes.map(node => [node.getAttribute('aria-label'), node.classList.contains('away')]));
  assert.deepEqual(avatars, [['Lan · đang mở sổ này, tháng 9/2026 · đang sửa', false], ['Hoa · đang ở Tổng quan', true]]);
  const cell = page.locator('tr[data-row="trip-11"] > td').nth(2);
  await page.waitForFunction(() => document.querySelector('tr[data-row="trip-11"]')?.cells[2].classList.contains('presence-cell'));
  assert.equal(await cell.getAttribute('data-presence'), 'Lan đang sửa…');
  assert.match(await cell.getAttribute('class'), /editing/);
  await shot('presence-dang-sua');
  await page.locator('.presence-avatar').first().click();
  assert.match(await cell.getAttribute('class'), /presence-flash/);
  await page.locator('.presence-avatar').nth(1).click();   // người ở trang khác: không nhảy, không lỗi
}, world => { world.people = [lan, hoa]; }));

test('báo vị trí của mình: khóa dòng + cột, đang sửa khi mở ô nhập', async () => withPage(async ({ page, world }) => {
  const cell = tripCell(page, 'carrier');
  const col = `c${await cell.evaluate(td => td.cellIndex)}`;
  await cell.click();
  await page.locator('.info-input').waitFor();
  const deadline = Date.now() + 6000;
  let last;
  while (Date.now() < deadline) {
    last = (world.presenceReports ?? []).at(-1);
    if (last?.cell?.editing) break;
    await page.waitForTimeout(100);
  }
  assert.deepEqual({ ...last, tab: 'x' }, { tab: 'x', page: 'so-khach', customer_id: 1, month: '2026-09', cell: { row: 'trip:11', col, editing: true } });
  assert.equal(world.requests.length, 0);   // báo vị trí không lẫn vào lệnh ghi sổ
}));

test('lưu lúc sổ vừa đổi: câu báo kèm tên người cùng mở sổ', async () => withPage(async ({ page, world }) => {
  await page.locator('.presence-avatar').first().waitFor();
  world.version += 1;   // người khác vừa ghi
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu đổi');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.live-notice')?.textContent.includes('Lan cũng đang mở sổ này'));
  assert.equal(await page.locator('.live-notice').innerText(), 'Sổ vừa thay đổi (Lan cũng đang mở sổ này). Kiểm tra dữ liệu mới rồi thực hiện lại.');
}, world => { world.people = [{ ...lan, cell: null }]; }));
