/* Trình duyệt (Playwright) cho phụ phí nhiều loại (PHU-PHI-01) trên sổ khách V7 bản live, theo tiêu chí frontend của
 * specs/v7-phu-phi-nhieu-loai.md. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage } = require('./so-khach-v7-browser-world');

const feePosts = world => world.requests.filter(item => /\/fees\/|fee-columns/.test(item.path)).map(item => [item.path, item.body]);
const own = (page, target, type) => page.locator(`td.fee.own[data-fee-target="${target}"][data-fee-type="${type}"]`);
const other = (page, target) => page.locator(`td.fee-other[data-fee-target="${target}"]`);
const strip = body => Object.fromEntries(Object.entries(body).filter(([name]) => !['idempotency_key', 'customer_id', 'expected_version'].includes(name)));

test('sổ mặc định chỉ có cột Khác; ba cột riêng vẫn vừa 1280×720, Tổng tháng có tổng từng cột', async () => withPage(async ({ page, world }) => {
  await page.locator('.fee-other').first().waitFor();
  assert.deepEqual(await page.locator('.ledger-head th.fee-h').allInnerTexts(), ['Khác']);
  assert.equal(await page.locator('td.fee.own').count(), 0);
  // Dòng sổ gốc OLDU0000002: phụ phí cũ đã tách thành một khoản → ô Khác ghi số và "1 khoản".
  assert.match(await other(page, 'legacy:22').innerText(), /3\.000\.000\s*1 khoản/);
  world.feeColumns = [1, 2, 3];
  world.version += 1;
  await page.reload();
  await page.locator('td.fee.own').first().waitFor();
  assert.deepEqual(await page.locator('.ledger-head th.fee-h').allInnerTexts(), ['Neo', 'Điện', 'Ghép', 'Khác']);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  assert.equal(await page.locator('#thang-2026-09 .subtotal td.fee').count(), 4);
  assert.equal(await page.locator('text=sổ gốc').count(), 0);
}));

test('ô cột riêng: gõ số + Enter gửi một lệnh đặt loại; Esc trả lại, xóa trắng bỏ loại đó', async () => withPage(async ({ page, world }) => {
  const cell = own(page, 'trip:11', 1);
  await cell.click();
  await page.keyboard.press('Escape');
  assert.equal(feePosts(world).length, 0);
  await cell.click();
  await page.locator('.fee-own-input').fill('1.200.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '1.200.000');
  assert.deepEqual(feePosts(world).map(([path, body]) => [path, strip(body)]),
    [['/api/v7/trips/fees/set', { target: { trip_id: 11 }, fee_type_id: 1, amount_vnd: '1200000' }]]);
  assert.match(await page.locator('tr[data-row="trip-11"]').innerText(), /51\.200\.000/);   // Thành tiền từ server
  // Số âm ở loại số dương: báo ngay tại ô, không gửi.
  await cell.click();
  await page.locator('.fee-own-input').fill('-5000');
  await page.keyboard.press('Enter');
  assert.match(await cell.locator('.cell-error').innerText(), /Loại này nhập số dương/);
  await page.locator('.fee-own-input').fill('');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '');
  assert.deepEqual(strip(feePosts(world).at(-1)[1]), { target: { trip_id: 11 }, fee_type_id: 1, amount_vnd: null });
}, world => { world.feeColumns = [1]; }));

test('khung Chi tiết phụ phí: thêm, đổi loại sang cột riêng, sửa số, xóa; Giảm trừ dương bị chặn tại form', async () => withPage(async ({ page, world }) => {
  await other(page, 'trip:11').click();
  const drawer = page.locator('.fee-drawer');
  await drawer.locator('.fee-close').waitFor();
  assert.match(await drawer.innerText(), /DEMU1234567/);
  assert.match(await drawer.innerText(), /Chưa có khoản phụ phí nào/);
  await drawer.locator('.fee-add-type').selectOption('8');
  await drawer.locator('.fee-add-amount').fill('200.000');
  await drawer.locator('.fee-add button[type="submit"]').click();
  assert.match(await drawer.locator('.fee-error').innerText(), /Giảm trừ nhập số âm/);
  assert.equal(feePosts(world).length, 0);
  await drawer.locator('.fee-add-type').selectOption('7');
  await drawer.locator('.fee-add-note').fill('lưu bãi');
  await drawer.locator('.fee-add button[type="submit"]').click();
  await drawer.locator('.fee-lines tbody tr').first().waitFor();
  assert.deepEqual(strip(feePosts(world)[0][1]), { targets: [{ trip_id: 11 }], fee_type_id: 7, amount_vnd: '200000', note: 'lưu bãi' });
  assert.match(await other(page, 'trip:11').innerText(), /200\.000\s*1 khoản/);
  assert.match(await drawer.locator('.fee-sumline.calc').innerText(), /50\.000\.000 \+ 200\.000\s*50\.200\.000/);
  // Đổi loại sang Neo (cột riêng của sổ) → số chuyển qua cột Neo, ô Khác trống.
  await drawer.locator('.fee-line-type').first().selectOption('1');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '200.000');
  assert.equal(feePosts(world)[1][0], '/api/v7/trips/fees/replace');
  assert.deepEqual({ ...strip(feePosts(world)[1][1]), fee_line_id: 'id' }, { fee_line_id: 'id', fee_type_id: 1, amount_vnd: '200000', note: 'lưu bãi' });
  assert.match(await drawer.locator('.fee-tag').first().innerText(), /cột riêng/);
  // Sửa số tại khung: Enter lưu.
  await drawer.locator('.fee-amt').first().click();
  await drawer.locator('.fee-line-amount').fill('350000');
  await drawer.locator('.fee-line-amount').press('Enter');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '350.000');
  // Xóa khoản.
  await drawer.locator('.fee-del').first().click();
  await page.waitForFunction(() => document.querySelector('.fee-drawer')?.textContent.includes('Chưa có khoản phụ phí nào'));
  assert.equal(feePosts(world).at(-1)[0], '/api/v7/trips/fees/void');
  await drawer.locator('.fee-close').click();
  assert.equal(await drawer.isVisible(), false);
}, world => { world.feeColumns = [1]; }));

test('thêm một khoản cho nhiều chuyến: một lệnh cho mọi chuyến đã chọn, bấm lặp không gửi hai lần', async () => withPage(async ({ page, world }) => {
  await page.locator('.fee-pick[data-fee-target="trip:11"]').check();
  await page.locator('.fee-pick[data-fee-target="legacy:22"]').check();
  assert.equal(await page.locator('.delete-prompt').count(), 0, 'bấm ô chọn không mở hỏi xóa dòng');
  assert.match(await page.locator('.fee-selbar').innerText(), /Đã chọn 2 chuyến/);
  await page.locator('.fee-batch').click();
  const drawer = page.locator('.fee-drawer');
  await drawer.locator('.fee-add-type').selectOption('4');
  await drawer.locator('.fee-add-amount').fill('300000');
  await drawer.locator('.fee-add button[type="submit"]').dblclick();
  await page.waitForFunction(() => !document.querySelector('.fee-selbar'));
  assert.deepEqual(feePosts(world).map(([path, body]) => [path, strip(body)]),
    [['/api/v7/trips/fees/add', { targets: [{ trip_id: 11 }, { legacy_row_id: 22 }], fee_type_id: 4, amount_vnd: '300000' }]]);
  assert.match(await page.locator('.live-notice').innerText(), /Đã thêm Bảo hiểm 300\.000 cho 2 chuyến/);
}));

test('tháng khóa: ô cột riêng chỉ đọc, khung không có form, không đánh dấu được; dòng chưa đơn giá cũng chỉ xem', async () => withPage(async ({ page, world }) => {
  await other(page, 'legacy:21').click();
  assert.match(await page.locator('.fee-drawer .fee-info').innerText(), /chưa có đơn giá/);
  assert.equal(await page.locator('.fee-drawer .fee-add').count(), 0);
  await page.locator('.fee-drawer .fee-close').click();
  assert.equal(await page.locator('.fee-pick[data-fee-target="legacy:21"]').count(), 0);
  world.locks = [{ month: '2026-09-01', locked: true }];
  world.version += 1;
  await page.reload();
  await other(page, 'trip:11').waitFor();
  assert.equal(await page.locator('#thang-2026-09 .fee-pick').count(), 0);
  assert.equal(await own(page, 'trip:11', 1).getAttribute('tabindex'), null);
  await own(page, 'trip:11', 1).click();
  assert.equal(await page.locator('.fee-own-input').count(), 0);
  await other(page, 'legacy:22').click();
  assert.match(await page.locator('.fee-drawer .fee-info').innerText(), /Tháng đã khóa — mở khóa tháng để sửa phụ phí/);
  assert.equal(await page.locator('.fee-drawer .fee-add').count(), 0);
  assert.equal(await page.locator('.fee-drawer select').count(), 0);
  assert.equal(feePosts(world).length, 0);
}, world => { world.feeColumns = [1]; }));

test('dòng sổ gốc có Thành tiền khác đơn giá + phụ phí: hỏi lại với số trước → sau; Enter không bấm luôn Ghi', async () => withPage(async ({ page, world }) => {
  await own(page, 'legacy:22', 1).click();
  await page.locator('.fee-own-input').fill('1000000');
  await page.keyboard.press('Enter');
  const box = page.locator('.fee-confirm');
  await box.locator('.fee-yes').waitFor();
  assert.match(await box.innerText(), /OLDU0000002: Thành tiền đang là 95\.000\.000 → 94\.000\.000 \(-1\.000\.000\)/);
  assert.equal(feePosts(world).length, 0, 'Enter vừa lưu ô không được bấm Ghi');
  await box.locator('.fee-no').click();
  assert.equal(feePosts(world).length, 0);
  await own(page, 'legacy:22', 1).click();
  await page.locator('.fee-own-input').fill('1000000');
  await page.keyboard.press('Enter');
  await box.locator('.fee-yes').click();
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="legacy:22"][data-fee-type="1"]')?.textContent === '1.000.000');
  assert.deepEqual(strip(feePosts(world)[0][1]), { target: { legacy_row_id: 22 }, fee_type_id: 1, amount_vnd: '1000000' });
}, world => { world.feeColumns = [1]; world.legacy[1].current.counted_vnd = '95000000'; }));

test('cài đặt phụ phí: bật cột riêng, đủ 3 thì khóa ô thứ tư, đổi tên và thêm loại qua danh mục chung', async () => withPage(async ({ page, world }) => {
  await page.locator('.fee-settings-open').click();
  const panel = page.locator('.fee-settings');
  await panel.locator('.fee-col[data-id="2"]').check();
  await page.waitForFunction(() => document.querySelectorAll('.ledger-head th.fee-h').length === 4);
  assert.deepEqual(strip(feePosts(world).at(-1)[1]), { fee_type_ids: [1, 3, 2] });
  assert.equal(await panel.locator('.fee-col[data-id="4"]').isDisabled(), true);
  assert.match(await panel.locator('.fee-info').innerText(), /Đã đủ 3 cột riêng/);
  // Bỏ cột Ghép: số không mất, chỉ đổi cách hiện.
  await panel.locator('.fee-col[data-id="3"]').uncheck();
  await page.waitForFunction(() => document.querySelectorAll('.ledger-head th.fee-h').length === 3);
  await panel.locator('td.fee-name[data-id="4"]').click();
  await panel.locator('.fee-rename').fill('Bảo hiểm hàng');
  await panel.locator('.fee-rename').press('Enter');
  await page.waitForFunction(() => document.querySelector('.fee-settings')?.textContent.includes('Bảo hiểm hàng'));
  await panel.locator('.fee-new-name').fill('neo');
  await panel.locator('.fee-newtype button').click();
  assert.match(await panel.locator('.fee-error').innerText(), /Đã có loại neo/);
  await panel.locator('.fee-new-name').fill('Nâng hạ');
  await panel.locator('.fee-new-kind').selectOption('pass_through');
  await panel.locator('.fee-newtype button').click();
  await page.waitForFunction(() => document.querySelector('.fee-settings')?.textContent.includes('Nâng hạ'));
  assert.deepEqual(world.catalogRequests.map(({ idempotency_key: _key, ...rest }) => rest), [
    { command: 'rename_fee_type', fee_type_id: 4, name: 'Bảo hiểm hàng' }, { name: 'Nâng hạ', kind: 'pass_through' }]);
  assert.equal(await panel.locator('td.fee-name:not([data-id])').count(), 3, 'ba loại hệ thống không đổi tên');
  await page.keyboard.press('Escape');
  assert.equal(await panel.isVisible(), false);
}, world => { world.feeColumns = [1, 3]; }));
