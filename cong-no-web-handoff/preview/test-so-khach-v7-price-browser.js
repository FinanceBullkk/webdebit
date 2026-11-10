/* Trình duyệt (Playwright) cho bảng giá theo ngày hiệu lực (BANG-GIA-01, giai đoạn 2). Máy chủ giả, giá giả, không chạm DB. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, posts } = require('./so-khach-v7-browser-world');

const status = trips => ({ customer_id: 1, version: 1, has_table: true, trips,
  ready_count: trips.filter(row => row.ready).length, ready_total_vnd: '85000000', ready_months: ['2026-09-01'],
  reapply_count: trips.filter(row => row.differs && row.from_table).length });
const lookup = (price, tier = 'khach') => ({ unit_price_vnd: price, tier, location: 'DAK LAK', destination: 'CẢNG B', valid_from: '2026-09-10', valid_to: null });
const missingTrip = { id: 12, month: '2026-09-01', container: 'NEWU0000012', carrier: 'Tàu thử', shipper: 'TT GIẢ', event_date: '2026-09-16',
  origin: 'DAK LAK', destination: 'Cảng B', unit_price_vnd: null, other_fee_vnd: null, amount_vnd: null, status: 'confirmed',
  is_missing_price: true, is_fee_only: false, editable: true, info_editable: true, deleted: false };

test('chuyến chưa có giá: chữ "theo bảng" ở ô, áp cả lô qua khung hỏi lại; giá gõ tay khác bảng được tô', async () => withPage(async ({ page, world, shot }) => {
  await page.waitForSelector('.price-table-apply');
  assert.equal(await page.locator('.price-table-apply').innerText(), 'Điền giá theo bảng (1 chuyến)');
  const missing = page.locator('[data-row="trip-12"] td').nth(6);
  assert.match(await missing.innerText(), /chưa có giá\s*bảng 85\.000\.000/);
  const typed = page.locator('[data-row="trip-11"] td').nth(6);
  assert.match(await typed.innerText(), /50\.000\.000\s*bảng 55\.000\.000/);
  assert.equal(await typed.evaluate(cell => cell.classList.contains('price-differs')), true);
  await shot('bang-gia-o-don-gia');

  await page.click('.price-table-apply');
  const panel = page.locator('.price-panel.confirm');
  assert.match(await panel.innerText(), /Điền giá theo bảng cho 1 chuyến tháng 9\/2026\?[\s\S]*Tổng còn nợ tăng 85\.000\.000 đ[\s\S]*NEWU0000012[\s\S]*85\.000\.000\s+giá TT/);
  assert.equal(world.requests.length, 0, 'mở khung hỏi lại chưa gửi lệnh');
  await page.click('.price-table-cancel');
  assert.equal(await panel.count(), 0);
  await page.click('.price-table-apply');
  await page.click('.price-table-write');
  await page.waitForFunction(() => /Đã điền giá theo bảng cho 1 chuyến/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const [[path, body]] = posts(world);
  assert.equal(path, '/api/v7/price-table/apply');
  assert.deepEqual([body.customer_id, body.expected_version, body.trip_ids], [1, 1, [12]]);
  assert.match(body.idempotency_key, /^[0-9a-f-]{36}$/);
  await page.waitForSelector('.price-table-apply', { state: 'detached' });
  assert.match(await page.locator('[data-row="trip-12"] td').nth(6).innerText(), /85\.000\.000\s*theo bảng/);
}, world => {
  world.trips.push({ ...missingTrip });
  world.priceStatus = status([
    { trip_id: 11, unit_price_vnd: '50000000', from_table: false, lookup: lookup('55000000'), ready: false, differs: true },
    { trip_id: 12, unit_price_vnd: null, from_table: false, lookup: lookup('85000000', 'tt'), ready: true, differs: false }]);
}));

test('bảng giá đổi: chuyến theo giá cũ của bảng có dải "Áp lại giá mới"; lý do không tra được hiện ở ô', async () => withPage(async ({ page, world }) => {
  await page.waitForSelector('.price-reapply-open');
  assert.match(await page.locator('.price-strip').innerText(), /1\s+chuyến đang ghi theo giá cũ của bảng/);
  assert.match(await page.locator('[data-row="trip-12"] td').nth(6).innerText(), /chưa có giá\s*ngoài bảng giá/);
  assert.equal(await page.locator('.price-table-apply').count(), 0);
  await page.click('.price-reapply-open');
  assert.match(await page.locator('.price-panel.confirm').innerText(), /Áp lại giá mới của bảng cho 1 chuyến/);
  await page.click('.price-table-write');
  await page.waitForFunction(() => /Đã áp lại giá theo bảng/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  assert.deepEqual(posts(world).map(([path, body]) => [path, body.trip_ids]), [['/api/v7/price-table/apply', [11]]]);
}, world => {
  world.trips.push({ ...missingTrip, origin: 'CAN THO' });
  world.priceStatus = status([
    { trip_id: 11, unit_price_vnd: '50000000', from_table: true, lookup: lookup('52000000'), ready: false, differs: true },
    { trip_id: 12, unit_price_vnd: null, from_table: false, lookup: { reason: 'UNKNOWN_LOCATION' }, ready: false, differs: false }]);
}));

async function pasteInto(page, selector, text) {
  await page.locator(selector).focus();
  await page.evaluate(([sel, value]) => {
    const data = new DataTransfer();
    data.setData('text/plain', value);
    document.querySelector(sel).dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  }, [selector, text]);
}
const cell = (r, c) => `.price-table-dialog input[data-r="${r}"][data-c="${c}"]`;
const rowStatus = (page, r) => page.locator('.price-table-dialog tbody tr').nth(r).locator('td.st').innerText();

test('khung Bảng giá: dán vùng Sheet vào lưới (bỏ tiêu đề, lấy cột shipper TT), lỗi tại dòng, đổi giá từ ngày, lưu đúng dữ liệu gửi server', async () => withPage(async ({ page, world, shot }) => {
  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();   // SO-GON-06: menu Cài đặt ▾
  await page.click('.price-table-open');
  const dialog = page.locator('.price-table-dialog');
  await dialog.locator('.price-help').waitFor();
  await shot('bang-gia-trong');

  // Dòng tiêu đề bị bỏ; ngày một chữ số đọc được; giá có dấu phẩy; ô giá trống là chưa có giá; cột thứ 7 là shipper áp giá TT.
  await pasteInto(page, cell(0, 0), [
    'EFFECTIVE FROM\tEFFECTIVE TO\tLOCATION\tKHÁCH PRICE\tTT PRICE\t\tSHIPPER ÁP GIÁ TT',
    '11/09/2026\t9/10/2026\tDAK LAK\t75,000,000\t95,000,000\t\tTT chuẩn',
    '11/09/2026\t9/10/2026\tLAM DONG\t70,000,000\t90,000,000',
    '10/10/2026\t\tDAK LAK\t75,000,000\t85,000,000',
    '10/10/2026\t\tVINH LONG\t\t75,000,000'].join('\n'));
  assert.match(await dialog.locator('.price-msg').innerText(), /Đã dán 4 dòng giá và 1 shipper áp giá TT/);
  assert.equal(await page.inputValue(cell(0, 1)), '09/10/2026');
  assert.equal(await page.inputValue(cell(0, 4)), '75.000.000');
  assert.equal(await page.inputValue(cell(3, 4)), '');
  assert.equal(await page.inputValue('.price-table-dialog input[data-s="0"]'), 'TT CHUẨN');
  assert.match(await dialog.locator('.price-grid-ship').innerText(), /4 chuyến/);
  assert.equal(await dialog.locator('.price-grid-main tbody tr').count(), 7, '4 dòng + 3 hàng trống');
  assert.equal(await dialog.locator('.price-dirty').isVisible(), true);
  assert.equal(await rowStatus(page, 0), 'Thiếu nơi đến', 'bảng giá Sheet cũ không tự áp mọi nơi đến');
  for (let row = 0; row < 4; row += 1) await page.fill(cell(row, 3), 'CẢNG B');

  // Ngày sai báo ngay tại dòng; Lưu bị chặn, chưa gửi gì.
  await page.fill(cell(2, 0), '32/10/2026');
  assert.equal(await rowStatus(page, 2), 'Từ ngày sai');
  assert.equal(await dialog.locator('.price-grid-main tbody tr').nth(2).locator('td.bad').count(), 1);
  await dialog.locator('header .price-table-save').click();
  assert.match(await dialog.locator('.price-msg').innerText(), /Chưa lưu: 1 dòng sai/);
  assert.equal(world.requests.length, 0);
  // Trùng ngày cùng nơi đi, cùng loại giá: báo dòng trùng.
  await page.fill(cell(2, 0), '01/10/2026');
  assert.equal(await rowStatus(page, 2), 'Trùng ngày dòng 1');
  await page.fill(cell(2, 0), '10/10/2026');
  await page.press(cell(2, 0), 'Enter');
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.r), '3', 'Enter xuống hàng dưới');

  // Đổi giá từ ngày: dòng đang dùng kết thúc ngày liền trước, dòng mới chép giá để sửa.
  await dialog.locator('.price-new-open').click();
  await page.fill('.price-new-from', '01/11/2026');
  await dialog.locator('.price-new-ok').click();
  assert.equal(await dialog.locator('tr.fresh').count(), 2);
  assert.equal(await page.inputValue(cell(2, 1)), '31/10/2026');
  assert.equal(await page.inputValue(cell(4, 0)), '01/11/2026');
  assert.equal(await page.inputValue(cell(4, 5)), '85.000.000');
  await page.fill(cell(4, 5), '80000000');
  await shot('bang-gia-khung');
  await dialog.locator('header .price-table-save').click();
  await page.waitForFunction(() => /Đã lưu bảng giá/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  assert.equal(await dialog.isVisible(), false, 'lưu xong thì đóng khung');
  const [[path, body]] = posts(world);
  assert.equal(path, '/api/v7/price-table');
  assert.equal(body.expected_version, 1);
  const table = body.price_table;
  assert.deepEqual(table.tt_shippers, ['TT CHUẨN']);
  assert.deepEqual(table.locations, [{ name: 'DAK LAK', aliases: [] }, { name: 'LAM DONG', aliases: [] }, { name: 'VINH LONG', aliases: [] }]);
  assert.deepEqual(table.periods.map(period => [period.valid_from, period.valid_to, period.rates.length]),
    [['2026-09-11', '2026-10-09', 4], ['2026-10-10', '2026-10-31', 3], ['2026-11-01', null, 3]]);
  assert.deepEqual(table.periods[2].rates, [
    { location: 'DAK LAK', destination: 'CẢNG B', tier: 'khach', unit_price_vnd: '75000000' }, { location: 'DAK LAK', destination: 'CẢNG B', tier: 'tt', unit_price_vnd: '80000000' },
    { location: 'VINH LONG', destination: 'CẢNG B', tier: 'tt', unit_price_vnd: '75000000' }]);
}, world => {
  world.bookShippers = [{ name: 'TT CHUẨN', tier: 'khach', trip_count: 4 }];
}));

const saveEditedTable = async (page, price) => {
  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();
  await page.click('.price-table-open');
  const dialog = page.locator('.price-table-dialog');
  await dialog.locator('.price-grid-main').waitFor();
  await page.fill(cell(0, 4), price);
  return dialog;
};
const savedTable = { tt_shippers: [], locations: [{ name: 'DAK LAK', aliases: [] }], periods: [
  { valid_from: '2026-09-11', valid_to: null, rates: [{ location: 'DAK LAK', destination: 'CẢNG B', tier: 'khach', unit_price_vnd: '75000000' }] }] };

test('cùng nơi đi, hai nơi đến giữ hai dòng giá riêng khi mở và lưu', async () => withPage(async ({ page, world }) => {
  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();
  await page.click('.price-table-open');
  await page.locator('.price-grid-main').waitFor();
  assert.deepEqual(await page.locator('.price-grid-main input[data-c="3"]').first().inputValue(), 'CẢNG A');
  assert.deepEqual(await page.locator('.price-grid-main input[data-c="3"]').nth(1).inputValue(), 'CẢNG B');
  await page.fill(cell(0, 4), '71000000');
  await page.locator('.price-table-dialog header .price-table-save').click();
  await page.waitForFunction(() => /Đã lưu bảng giá/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const rates = posts(world)[0][1].price_table.periods[0].rates;
  assert.deepEqual(rates.map(rate => [rate.destination, rate.unit_price_vnd]), [['CẢNG A', '71000000'], ['CẢNG B', '75000000']]);
}, world => {
  world.priceTable = { ...savedTable, periods: [{ valid_from: '2026-09-11', valid_to: null, rates: [
    { location: 'DAK LAK', destination: 'CẢNG A', tier: 'khach', unit_price_vnd: '70000000' },
    { location: 'DAK LAK', destination: 'CẢNG B', tier: 'khach', unit_price_vnd: '75000000' }] }] };
}));

test('BANG-GIA-02: lưu bảng giá báo trước khi lưu; sau khi lưu báo từng chuyến giá cũ → mới, tháng khóa và chuyến hết giá; chỉ gửi một lệnh', async () => withPage(async ({ page, world, shot }) => {
  const dialog = await saveEditedTable(page, '76000000');
  assert.match(await dialog.locator('.price-dirty').innerText(), /Lưu xong, chuyến đang theo bảng tự đổi giá/);
  await shot('bang-gia-chua-luu');
  await dialog.locator('header .price-table-save').click();
  await page.waitForFunction(() => /Đã lưu bảng giá/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const notice = await page.locator('.live-notice').innerText();
  assert.match(notice, /Đã đổi giá 4 chuyến: FAKE-1 75\.000\.000 → 76\.000\.000; FAKE-2 75\.000\.000 → 76\.000\.000; FAKE-3 77\.000\.000 → 76\.000\.000 và 1 chuyến khác \(xem Lịch sử\)\./);
  assert.match(notice, /Tổng tiền các chuyến tăng 2\.000\.000 đ\./);
  assert.match(notice, /2 chuyến ở tháng khóa chưa đổi: mở khóa tháng rồi bấm "Áp lại giá mới"\./);
  assert.match(notice, /1 chuyến không còn giá trong bảng mới, giữ giá đang ghi\./);
  assert.doesNotMatch(notice, /không tự đổi/);
  assert.equal(await page.locator('.page-more').evaluate(node => node.open), false, 'menu ⋯ không che thông báo');
  await shot('bang-gia-da-doi');
  assert.deepEqual(posts(world).map(([path]) => path), ['/api/v7/price-table'], 'đổi giá nằm trong lệnh lưu, không gửi lệnh áp riêng');
}, world => {
  world.priceTable = savedTable;
  world.repricedTrips = ['1', '2', '3', '4'].map((n, index) => ({ trip_id: index + 1, container: `FAKE-${n}`, before_vnd: index === 2 ? '77000000' : '75000000', after_vnd: '76000000' }));
  world.repricedDelta = '2000000';
  world.lockedTrips = 2;
  world.noPriceTrips = 1;
}));

test('BANG-GIA-02: giá giảm thì báo giảm; không có chuyến nào đổi thì chỉ báo đã lưu', async () => withPage(async ({ page, world }) => {
  const dialog = await saveEditedTable(page, '74000000');
  await dialog.locator('header .price-table-save').click();
  await page.waitForFunction(() => /Tổng tiền các chuyến giảm 1\.000\.000 đ\./.test(document.querySelector('.live-notice')?.textContent ?? ''));
  world.repricedTrips = [];
  world.repricedDelta = '0';
  const again = await saveEditedTable(page, '73000000');
  await again.locator('header .price-table-save').click();
  await page.waitForFunction(() => document.querySelector('.live-notice')?.textContent === 'Đã lưu bảng giá.');
}, world => {
  world.priceTable = savedTable;
  world.repricedTrips = [{ trip_id: 1, container: 'FAKE-1', before_vnd: '75000000', after_vnd: '74000000' }];
  world.repricedDelta = '-1000000';
}));

test('bảng giá đã lưu hiện lại thành lưới; tên khác của nơi đi giữ nguyên; lỗi server giữ bảng đang sửa; đóng khi chưa lưu thì hỏi', async () => withPage(async ({ page, world }) => {
  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();   // SO-GON-06: menu Cài đặt ▾
  await page.click('.price-table-open');
  const dialog = page.locator('.price-table-dialog');
  await dialog.locator('.price-grid-main').waitFor();
  assert.equal(await page.inputValue(cell(0, 2)), 'DAK LAK');
  assert.equal(await page.inputValue(cell(0, 5)), '95.000.000');
  assert.equal(await page.inputValue(cell(1, 0)), '10/10/2026');
  assert.equal(await page.inputValue(cell(1, 4)), '75.000.000');
  assert.equal(await page.inputValue(cell(1, 5)), '');
  assert.equal(await rowStatus(page, 0), 'Hết hạn');
  assert.equal(await rowStatus(page, 1), 'Đang dùng');
  assert.equal(await dialog.locator('.price-help').count(), 0);
  assert.equal(await dialog.locator('.price-dirty').isVisible(), false);

  await page.fill(cell(1, 5), '85.000.000');
  world.failNext = { error: 'PRICE_PERIOD_OVERLAP', message: 'Hai đợt giá trùng ngày ở cùng kho và cùng loại giá.' };
  await dialog.locator('header .price-table-save').click();
  await dialog.locator('.price-msg.bad', { hasText: 'trùng ngày' }).waitFor();
  assert.equal(await page.inputValue(cell(1, 5)), '85.000.000');
  await dialog.locator('header .price-table-save').click();
  await page.waitForFunction(() => /Đã lưu bảng giá/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const [, body] = posts(world).at(-1);
  assert.deepEqual(body.price_table.locations, [{ name: 'DAK LAK', aliases: ['DAKLAK'] }]);
  assert.deepEqual(body.price_table.tt_shippers, ['TT CHUẨN']);

  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();   // SO-GON-06: menu Cài đặt ▾
  await page.click('.price-table-open');
  await dialog.locator('.price-grid-main').waitFor();
  await page.fill(cell(0, 4), '1');
  await page.keyboard.press('Escape');
  assert.match(await dialog.locator('.price-msg.ask').innerText(), /thay đổi chưa lưu/);
  await dialog.locator('.price-discard').click();
  assert.equal(await dialog.isVisible(), false);
}, world => {
  world.priceTable = { tt_shippers: ['TT CHUẨN'], locations: [{ name: 'DAK LAK', aliases: ['DAKLAK'] }], periods: [
    { valid_from: '2026-09-11', valid_to: '2026-10-09', rates: [{ location: 'DAK LAK', destination: 'CẢNG B', tier: 'khach', unit_price_vnd: '75000000' }, { location: 'DAK LAK', destination: 'CẢNG B', tier: 'tt', unit_price_vnd: '95000000' }] },
    { valid_from: '2026-10-10', valid_to: null, rates: [{ location: 'DAK LAK', destination: 'CẢNG B', tier: 'khach', unit_price_vnd: '75000000' }] }] };
}));
