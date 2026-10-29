/* Trình duyệt (Playwright) cho bảng giá theo ngày hiệu lực (BANG-GIA-01, giai đoạn 2). Máy chủ giả, giá giả, không chạm DB. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage, posts } = require('./so-khach-v7-browser-world');

const status = trips => ({ customer_id: 1, version: 1, has_table: true, trips,
  ready_count: trips.filter(row => row.ready).length, ready_total_vnd: '85000000', ready_months: ['2026-09-01'],
  reapply_count: trips.filter(row => row.differs && row.from_table).length });
const lookup = (price, tier = 'khach') => ({ unit_price_vnd: price, tier, location: 'DAK LAK', valid_from: '2026-09-10', valid_to: null });
const missingTrip = { id: 12, month: '2026-09-01', container: 'NEWU0000012', carrier: 'Tàu thử', shipper: 'TT GIẢ', event_date: '2026-09-16',
  origin: 'DAK LAK', destination: 'Cảng B', unit_price_vnd: null, other_fee_vnd: null, amount_vnd: null, status: 'confirmed',
  is_missing_price: true, is_fee_only: false, editable: true, info_editable: true, deleted: false };

test('chuyến chưa có giá: chữ "theo bảng" ở ô, áp cả lô qua khung hỏi lại; giá gõ tay khác bảng được tô', async () => withPage(async ({ page, world, shot }) => {
  await page.waitForSelector('.price-table-apply');
  assert.equal(await page.locator('.price-table-apply').innerText(), 'Áp giá theo bảng cho 1 chuyến');
  const missing = page.locator('[data-row="trip-12"] td').nth(7);
  assert.match(await missing.innerText(), /chưa có giá\s*bảng: 85\.000\.000 \(TT\)/);
  const typed = page.locator('[data-row="trip-11"] td').nth(7);
  assert.match(await typed.innerText(), /50\.000\.000\s*khác bảng: 55\.000\.000/);
  assert.equal(await typed.evaluate(cell => cell.classList.contains('price-differs')), true);
  await shot('bang-gia-o-don-gia');

  await page.click('.price-table-apply');
  const panel = page.locator('.price-panel.confirm');
  assert.match(await panel.innerText(), /Áp giá theo bảng cho 1 chuyến chưa có giá \(tháng 9\/2026\)\?[\s\S]*Tổng còn nợ tăng 85\.000\.000 đ/);
  assert.equal(world.requests.length, 0, 'mở khung hỏi lại chưa gửi lệnh');
  await page.click('.price-table-cancel');
  assert.equal(await panel.count(), 0);
  await page.click('.price-table-apply');
  await page.click('.price-table-write');
  await page.waitForFunction(() => /Đã áp giá theo bảng cho 1 chuyến/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const [[path, body]] = posts(world);
  assert.equal(path, '/api/v7/price-table/apply');
  assert.deepEqual([body.customer_id, body.expected_version, body.trip_ids], [1, 1, [12]]);
  assert.match(body.idempotency_key, /^[0-9a-f-]{36}$/);
  await page.waitForSelector('.price-table-apply', { state: 'detached' });
  assert.match(await page.locator('[data-row="trip-12"] td').nth(7).innerText(), /85\.000\.000\s*theo bảng \(TT\)/);
}, world => {
  world.trips.push({ ...missingTrip });
  world.priceStatus = status([
    { trip_id: 11, unit_price_vnd: '50000000', from_table: false, lookup: lookup('55000000'), ready: false, differs: true },
    { trip_id: 12, unit_price_vnd: null, from_table: false, lookup: lookup('85000000', 'tt'), ready: true, differs: false }]);
}));

test('bảng giá đổi: chuyến theo giá cũ của bảng có dải "Áp lại giá mới"; lý do không tra được hiện ở ô', async () => withPage(async ({ page, world }) => {
  await page.waitForSelector('.price-reapply-open');
  assert.match(await page.locator('.price-strip').innerText(), /1\s+chuyến đang ghi theo giá cũ của bảng/);
  assert.match(await page.locator('[data-row="trip-12"] td').nth(7).innerText(), /kho chưa có trong bảng giá/);
  assert.equal(await page.locator('.price-table-apply').count(), 0);
  await page.click('.price-reapply-open');
  assert.match(await page.locator('.price-panel.confirm').innerText(), /Áp lại giá mới của bảng cho 1 chuyến/);
  await page.click('.price-table-write');
  await page.waitForFunction(() => /Đã áp giá theo bảng/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  assert.deepEqual(posts(world).map(([path, body]) => [path, body.trip_ids]), [['/api/v7/price-table/apply', [11]]]);
}, world => {
  world.trips.push({ ...missingTrip, origin: 'CAN THO' });
  world.priceStatus = status([
    { trip_id: 11, unit_price_vnd: '50000000', from_table: true, lookup: lookup('52000000'), ready: false, differs: true },
    { trip_id: 12, unit_price_vnd: null, from_table: false, lookup: { reason: 'UNKNOWN_LOCATION' }, ready: false, differs: false }]);
}));

test('khung Bảng giá: dán từ Sheet thành đợt giá, thêm đợt đóng đợt cũ, soát shipper, lưu đúng dữ liệu gửi server', async () => withPage(async ({ page, world, shot }) => {
  await page.click('.price-table-open');
  const dialog = page.locator('.price-table-dialog');
  await dialog.locator('.price-paste-open').waitFor();
  assert.match(await dialog.innerText(), /TT CHUẨN \(4 chuyến\)[\s\S]*Thêm vào TT/);

  // Dòng tiêu đề bị bỏ; ngày một chữ số đọc được; giá có dấu phẩy; ô giá trống là không có giá.
  await dialog.locator('.price-paste-open').click();
  await dialog.locator('.price-paste-text').fill([
    'EFFECTIVE FROM\tEFFECTIVE TO\tLOCATION\tKHÁCH PRICE\tTT PRICE',
    '11/09/2026\t9/10/2026\tDAK LAK\t75,000,000\t95,000,000',
    '11/09/2026\t9/10/2026\tLAM DONG\t70,000,000\t90,000,000',
    '10/10/2026\t\tDAK LAK\t75,000,000\t85,000,000',
    '10/10/2026\t\tVINH LONG\t\t75,000,000'].join('\n'));
  await dialog.locator('.price-paste-read').click();
  assert.match(await dialog.innerText(), /Đã đọc 4 dòng thành 2 đợt giá/);
  assert.equal(await dialog.locator('.price-period').count(), 2);
  assert.equal(await dialog.locator('.price-loc-name').count(), 3);

  // Ngày sai báo ngay tại khung, chưa gửi gì.
  await dialog.locator('.price-from[data-p="1"]').fill('32/10/2026');
  await dialog.locator('.price-table-save').click();
  assert.match(await dialog.locator('.fee-error').innerText(), /Đợt 2: ngày bắt đầu "32\/10\/2026" không đúng dạng/);
  assert.equal(world.requests.length, 0);
  await dialog.locator('.price-from[data-p="1"]').fill('10/10/2026');

  // Thêm đợt mới: đợt đang áp dụng tự đóng vào ngày liền trước, giá chép sang để sửa.
  await dialog.locator('.price-period-add').click();
  await dialog.locator('.price-new-from').fill('01/11/2026');
  await dialog.locator('.price-new-ok').click();
  assert.equal(await dialog.locator('.price-to[data-p="1"]').inputValue(), '31/10/2026');
  assert.equal(await dialog.locator('.price-rate[data-p="2"][data-tier="tt"]').first().inputValue(), '85.000.000');
  await dialog.locator('.price-rate[data-p="2"][data-tier="tt"]').first().fill('80000000');

  await dialog.locator('.price-loc-aliases').first().fill('DAKLAK, DAKLAK-得乐');
  await dialog.locator('.price-shipper-add').click();
  await shot('bang-gia-khung');
  await dialog.locator('.price-table-save').click();
  await dialog.locator('.fee-info', { hasText: 'Đã lưu bảng giá' }).waitFor();
  const [[path, body]] = posts(world);
  assert.equal(path, '/api/v7/price-table');
  assert.equal(body.expected_version, 1);
  const table = body.price_table;
  assert.deepEqual(table.tt_shippers, ['TT CHUẨN']);
  assert.deepEqual(table.locations, [{ name: 'DAK LAK', aliases: ['DAKLAK', 'DAKLAK-得乐'] }, { name: 'LAM DONG', aliases: [] }, { name: 'VINH LONG', aliases: [] }]);
  assert.deepEqual(table.periods.map(period => [period.valid_from, period.valid_to, period.rates.length]),
    [['2026-09-11', '2026-10-09', 4], ['2026-10-10', '2026-10-31', 3], ['2026-11-01', null, 3]]);
  assert.deepEqual(table.periods[2].rates, [
    { location: 'DAK LAK', tier: 'khach', unit_price_vnd: '75000000' }, { location: 'DAK LAK', tier: 'tt', unit_price_vnd: '80000000' },
    { location: 'VINH LONG', tier: 'tt', unit_price_vnd: '75000000' }]);

  // Server từ chối: câu lỗi hiện trong khung, bảng đang sửa giữ nguyên.
  world.failNext = { error: 'PRICE_PERIOD_OVERLAP', message: 'Hai đợt giá trùng ngày ở cùng kho và cùng loại giá.' };
  await dialog.locator('.price-to[data-p="2"]').fill('02/11/2026');
  await dialog.locator('.price-table-save').click();
  await dialog.locator('.fee-error', { hasText: 'trùng ngày' }).waitFor();
  assert.equal(await dialog.locator('.price-to[data-p="2"]').inputValue(), '02/11/2026');
  await page.keyboard.press('Escape');
  assert.equal(await dialog.isVisible(), false);
}, world => {
  world.bookShippers = [{ name: 'TT CHUẨN', tier: 'khach', trip_count: 4 }];
}));
