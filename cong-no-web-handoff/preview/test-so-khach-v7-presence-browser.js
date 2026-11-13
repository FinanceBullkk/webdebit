/* Trình duyệt (Playwright) cho PRESENCE-01 mức 1 trên sổ khách V7: người khác đang ở đâu, ô đang chọn/đang sửa,
 * câu báo sổ vừa đổi kèm tên. Máy chủ giả không có SSE nên trang hỏi định kỳ. Dữ liệu giả. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { todayMonth, withPage, tripCell, reload } = require('./so-khach-v7-browser-world');

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
  const { pointer: _pointer, ...report } = last;   // chuột vừa bấm ô cũng được báo (mức 2), kiểm riêng ở test dưới
  assert.deepEqual({ ...report, tab: 'x' }, { tab: 'x', page: 'so-khach', customer_id: 1, month: '2026-09', cell: { row: 'trip:11', col, editing: true } });
  assert.equal(world.requests.length, 0);   // báo vị trí không lẫn vào lệnh ghi sổ
}));

test('lưu lúc sổ vừa đổi: câu báo kèm tên người cùng mở sổ', async () => withPage(async ({ page, world }) => {
  await page.locator('.presence-avatar').first().waitFor();
  world.version += 1;   // người khác vừa ghi
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu đổi');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.live-notice')?.textContent.includes('Lan cũng đang mở sổ này'));
  // NHAP-NHANH-01: lệnh ghi nền nên câu nói rõ ô nào chưa lưu.
  assert.equal(await page.locator('.live-notice').innerText(), 'Chưa lưu ô hãng tàu của chuyến DEMU1234567: Sổ vừa thay đổi (Lan cũng đang mở sổ này). Kiểm tra dữ liệu mới rồi thực hiện lại.');
}, world => { world.people = [{ ...lan, cell: null }]; }));

// Mức 2: mũi tên chuột người khác neo theo ô; nút Ẩn con trỏ nhớ sau tải lại.
const pointerAt = page => page.evaluate(() => {
  const arrow = document.querySelector('.presence-pointer');
  const td = document.querySelector('tr[data-row="trip-11"]')?.cells[2].getBoundingClientRect();
  if (!arrow || !td) return null;
  const x = parseFloat(arrow.style.left) - scrollX, y = parseFloat(arrow.style.top) - scrollY;
  return { inside: x >= td.left && x <= td.right && y >= td.top && y <= td.bottom, name: arrow.textContent };
});

test('mũi tên chuột người khác nằm đúng ô ở mọi cỡ màn hình; Ẩn con trỏ nhớ sau tải lại', async () => withPage(async ({ page, shot }) => {
  await page.locator('.presence-pointer').waitFor();
  assert.deepEqual(await pointerAt(page), { inside: true, name: 'Lan' });
  await shot('presence-con-tro');
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.waitForFunction(() => document.querySelector('.presence-pointer'));
  await page.waitForTimeout(300);
  assert.deepEqual(await pointerAt(page), { inside: true, name: 'Lan' });
  const toggle = page.locator('.settings-menu .presence-toggle');
  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();   // SO-GON-06: menu Cài đặt ▾
  assert.equal(await toggle.innerText(), 'Ẩn con trỏ');
  await toggle.click();
  assert.equal(await page.locator('.book-settings[open]').count(), 0, 'bấm một mục thì menu đóng');
  assert.equal(await page.locator('.presence-pointer').count(), 0);
  assert.equal(await page.locator('tr[data-row="trip-11"] > td').nth(2).getAttribute('data-presence'), 'Lan');   // vẫn thấy ô họ chọn
  await reload(page);
  await page.locator('.presence-avatar').first().waitFor();
  assert.equal(await page.locator('.settings-menu .presence-toggle').textContent(), 'Hiện con trỏ');
  await page.waitForTimeout(500);
  assert.equal(await page.locator('.presence-pointer').count(), 0);
}, world => { world.people = [{ ...lan, cell: { row: 'trip:11', col: 'c2', editing: false }, pointer: { row: 'trip:11', col: 'c2', fx: 500, fy: 500 } }]; }));

test('báo chuột của mình: ô + phần nghìn trong ô; rời bảng thì bỏ', async () => withPage(async ({ page, world }) => {
  const cell = tripCell(page, 'carrier');
  const col = `c${await cell.evaluate(td => td.cellIndex)}`;
  const box = await cell.boundingBox();
  await page.mouse.move(box.x + box.width / 4, box.y + box.height / 2);
  const reported = async check => {
    const deadline = Date.now() + 6000;
    while (Date.now() < deadline) {
      const last = (world.presenceReports ?? []).at(-1);
      if (check(last)) return last;
      await page.waitForTimeout(50);
    }
    return (world.presenceReports ?? []).at(-1);
  };
  const moved = await reported(last => last?.pointer);
  assert.equal(moved.pointer.row, 'trip:11');
  assert.equal(moved.pointer.col, col);
  assert.ok(Math.abs(moved.pointer.fx - 250) <= 30 && Math.abs(moved.pointer.fy - 500) <= 60, JSON.stringify(moved.pointer));
  await page.mouse.move(5, 5);   // lên thanh trên cùng, ra khỏi bảng
  assert.equal((await reported(last => last && last.pointer === null)).pointer, null);
  assert.equal(world.requests.length, 0);
}));

// Bảng chi tiết (SO-CHI-TIET-01) là bảng mặc định của sổ có bảng kê: dòng có data-detail, không có data-row.
const KEY = todayMonth.slice(0, 7);
const detailRow = { kind: 'legacy', id: 1, month: KEY, container: 'ABCU2000011', has_detail: true, day: '03/09', bill: 'MAU1', ship: 'TÀU MẪU', etd: '06/09', eta: '10/09', from: 'KHO', to: 'SHEKOU',
  of_counted: false, ledger_vnd: '22750200', differs: false, fee_vnd: '565000', service_vnd: '6000000', truck_vnd: '14500000', of_vnd: '21000000', vat_vnd: '1685200', total_vnd: '22750200',
  sheet_total_vnd: '22750200', state: 'ok', adds_up: true, phi_vnd: '22750200', parts_vnd: '22750200', adds_diff_vnd: null, sheet_diff_vnd: '0' };
const withDetail = (world, people = []) => {
  world.month = null;
  world.trips = [{ id: 900, month: `${KEY}-01`, container: 'ABCU2000011', carrier: 'WH', event_date: todayMonth, origin: 'KHO', destination: 'CANG', unit_price_vnd: '1000000', other_fee_vnd: null,
    amount_vnd: '1000000', status: 'confirmed', is_missing_price: false, is_fee_only: false, editable: true, info_editable: true, deleted: false }];
  world.details = { rows: [detailRow], months: { [KEY]: { total_vnd: '22750200', charges_vnd: '22750200', of_customer_vnd: '21000000', diff_vnd: '0', no_detail: 0, differs: [], sheet_diff_vnd: '0', compare_differs: 0, compare_diff_vnd: '0', compare_no_add: 0 } } };
  world.people = people;
};
const pointerInCell = (page, index) => page.evaluate(i => {
  const arrow = document.querySelector('.presence-pointer');
  const td = document.querySelector('tr[data-detail="legacy-1"]')?.cells[i].getBoundingClientRect();
  if (!arrow || !td) return false;
  const x = parseFloat(arrow.style.left) - scrollX, y = parseFloat(arrow.style.top) - scrollY;
  return x >= td.left && x <= td.right && y >= td.top && y <= td.bottom;
}, index);
const onDetail = (col, fx = 500) => ({ ...lan, cell: null, pointer: { row: 'legacy:1', col, fx, fy: 500 } });

test('bảng chi tiết: báo được chuột của mình, kèm cột theo đúng bảng đang xem', async () => withPage(async ({ page, world }) => {
  const cell = page.locator('tr[data-detail="legacy-1"] > td').nth(1);
  await cell.waitFor();
  const box = await cell.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  const deadline = Date.now() + 6000;
  let last;
  while (Date.now() < deadline) {
    last = (world.presenceReports ?? []).at(-1);
    if (last?.pointer) break;
    await page.waitForTimeout(50);
  }
  assert.equal(last?.pointer?.row, 'legacy:1');
  assert.equal(last?.pointer?.col, 'g1');
}, world => withDetail(world)));

test('bảng chi tiết: thấy mũi tên người khác ngay tại ô họ đang trỏ', async () => withPage(async ({ page }) => {
  await page.locator('.presence-pointer').waitFor();
  assert.equal(await pointerInCell(page, 3), true);
}, world => withDetail(world, [onDetail('g3')])));

test('hai người xem hai bảng khác nhau: mũi tên về ô container của đúng dòng, không sang cột sai', async () => withPage(async ({ page }) => {
  await page.locator('.presence-pointer').waitFor();
  assert.equal(await pointerInCell(page, 1), true);   // người kia trỏ cột 12 của Đủ cột; bảng gọn của mình chỉ có 9 cột
}, world => withDetail(world, [onDetail('d12')])));

test('chưa bấm ô nào vẫn báo tháng đang xem, để người khác biết vì sao không thấy mũi tên của mình', async () => withPage(async ({ page, world }) => {
  await page.locator('tr[data-detail="legacy-1"]').waitFor();
  const deadline = Date.now() + 6000;
  while (Date.now() < deadline && !(world.presenceReports ?? []).at(-1)?.month) await page.waitForTimeout(100);
  assert.equal((world.presenceReports ?? []).at(-1)?.month, KEY);
}, world => withDetail(world)));

test('quay lại tab: báo ngay, không đợi nhịp 10 giây', async () => withPage(async ({ page, world }) => {
  await page.locator('tr[data-detail="legacy-1"]').waitFor();
  // Máy chủ giả không có SSE nên trang hỏi mỗi 2 giây: đo ngay sau một lần báo, cửa sổ 500 ms không dính lần hỏi kế tiếp.
  const count = () => (world.presenceReports ?? []).length;
  const seen = count();
  const until = Date.now() + 6000;
  while (Date.now() < until && count() === seen) await page.waitForTimeout(10);
  const before = count();
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  const deadline = Date.now() + 500;
  while (Date.now() < deadline && count() === before) await page.waitForTimeout(10);
  assert.ok(count() > before, 'không gửi báo vị trí khi tab hiện lại');
}, world => withDetail(world)));
