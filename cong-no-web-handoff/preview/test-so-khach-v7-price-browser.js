/* Trình duyệt (Playwright) cho bảng giá theo ngày hiệu lực (BANG-GIA-01, giai đoạn 2) và khung Bảng giá dạng ma trận
 * (BANG-GIA-05, specs/v7-bang-gia-ma-tran.md). Máy chủ giả, giá và tên giả, không chạm DB. */
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

// ---- Khung Bảng giá dạng ma trận (BANG-GIA-05) ----
async function pasteInto(page, selector, text) {
  await page.locator(selector).first().focus();
  await page.evaluate(value => {
    const data = new DataTransfer();
    data.setData('text/plain', value);
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  }, text);
}
const D = '.price-table-dialog';
const NOW = '2026-11-05T03:00:00Z';   // trạng thái đợt (hết hạn / đang dùng) tính theo hôm nay giờ VN
const rowsOf = page => page.locator(`${D} .pm-grid tbody tr`);
// Ô giá: hàng thứ r (theo thứ tự đang hiện), đợt thứ p trong các cột đang hiện, loại giá.
const price = (page, r, p, tier = 'khach') => rowsOf(page).nth(r).locator(`input[data-tier="${tier}"]`).nth(p);
const place = (page, r, field = 'kho') => rowsOf(page).nth(r).locator(`input[data-f="${field}"]`);
const heads = page => page.locator(`${D} th.ph`).evaluateAll(nodes => nodes.map(node => node.innerText.replace(/\s+/g, ' ').trim()));
const matrix = page => rowsOf(page).evaluateAll(nodes => nodes.map(node => [...node.querySelectorAll('input')].map(input => input.value)));
async function openTable(page) {
  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();   // SO-GON-06: menu Cài đặt ▾
  await page.click('.price-table-open');
  const dialog = page.locator(D);
  await dialog.locator('.pm-grid, .price-help').first().waitFor();
  return dialog;
}
// BANG-GIA-05: "Xem lại và lưu" mở bước xem lại (server lưu thử rồi hoàn tác); nút ở bước đó mới lưu thật.
const saves = world => posts(world).filter(([path]) => path === '/api/v7/price-table').map(([, body]) => body);
async function saveAndWait(page) {
  await page.locator(`${D} header .price-table-save`).click();
  await page.locator(`${D} .price-review-save:not([disabled])`).click();
  await page.waitForFunction(() => /Đã lưu bảng giá/.test(document.querySelector('.live-notice')?.textContent ?? ''));
}

test('ma trận: dán vùng Sheet phẳng vào bảng trống (bỏ tiêu đề, ô trống, số có dấu phẩy, ngày một chữ số, cột shipper TT) thì gộp thành đợt × nơi đi', async () => withPage(async ({ page, world, shot }) => {
  const dialog = await openTable(page);
  assert.match(await dialog.locator('.price-help').innerText(), /Sổ này chưa có bảng giá/);
  await shot('bang-gia-trong');
  await pasteInto(page, `${D} .pm-paste`, [
    'EFFECTIVE FROM\tEFFECTIVE TO\tLOCATION\tKHÁCH PRICE\tTT PRICE\t\tSHIPPER ÁP GIÁ TT',
    '11/09/2026\t9/10/2026\tDAK LAK\t75,000,000\t95,000,000\t\tTT chuẩn',
    '11/09/2026\t9/10/2026\tlam  dong\t70,000,000\t90,000,000',
    '10/10/2026\t\tDAK LAK\t75,000,000\t85,000,000',
    '10/10/2026\t\tVINH LONG\t\t75,000,000'].join('\n'));
  assert.match(await dialog.locator('.price-msg').innerText(), /Đã dán 4 dòng giá vào 2 đợt và 1 shipper áp giá TT/);
  assert.deepEqual(await heads(page), ['11/09 – 09/10/2026 hết hạn', 'Từ 10/10/2026 đang dùng']);
  assert.deepEqual(await matrix(page), [
    ['DAK LAK', '', '75.000.000', '95.000.000', '75.000.000', '85.000.000'],
    ['LAM DONG', '', '70.000.000', '90.000.000', '', ''],
    ['VINH LONG', '', '', '', '', '75.000.000']]);
  assert.equal(await price(page, 2, 1).getAttribute('placeholder'), '—', 'ô trống hiện "—", không phải 0');
  assert.equal(await price(page, 0, 1, 'tt').evaluate(input => input.classList.contains('changed')), true, 'giá khác đợt trước thì đậm');
  assert.equal(await price(page, 0, 1).evaluate(input => input.classList.contains('changed')), false);
  assert.match(await dialog.locator('.pm-ships').innerText(), /TT CHUẨN\s*4 chuyến/);
  assert.match(await dialog.locator('.price-dirty').innerText(), /Chưa lưu · 7 ô giá đổi/);
  assert.match(await dialog.locator('.pm-hint').innerText(), /Lưu xong, chuyến đang theo bảng ở tháng mở tự đổi giá/);

  // Dán lại một dòng đã sửa trên Sheet: ô cùng đợt cùng nơi đi bị thay, không thêm hàng.
  await dialog.locator('.price-paste-open').click();
  await pasteInto(page, '#pm-paste-side', '10/10/2026\t\tDAK LAK\t76,000,000\t85,000,000\n');
  assert.match(await dialog.locator('.price-msg').innerText(), /Đã dán 1 dòng giá vào 1 đợt/);
  assert.equal(await rowsOf(page).count(), 3);
  assert.equal(await price(page, 0, 1).inputValue(), '76.000.000');

  await saveAndWait(page);
  assert.deepEqual(posts(world).map(([path]) => path), ['/api/v7/price-table/preview', '/api/v7/price-table']);
  const [body] = saves(world);
  assert.equal(body.expected_version, 1);
  assert.deepEqual(body.price_table, { tt_shippers: ['TT CHUẨN'],
    locations: [{ name: 'DAK LAK', aliases: [] }, { name: 'LAM DONG', aliases: [] }, { name: 'VINH LONG', aliases: [] }],
    periods: [{ valid_from: '2026-09-11', valid_to: '2026-10-09', rates: [
      { location: 'DAK LAK', destination: '', tier: 'khach', unit_price_vnd: '75000000' }, { location: 'DAK LAK', destination: '', tier: 'tt', unit_price_vnd: '95000000' },
      { location: 'LAM DONG', destination: '', tier: 'khach', unit_price_vnd: '70000000' }, { location: 'LAM DONG', destination: '', tier: 'tt', unit_price_vnd: '90000000' }] },
    { valid_from: '2026-10-10', valid_to: null, rates: [
      { location: 'DAK LAK', destination: '', tier: 'khach', unit_price_vnd: '76000000' }, { location: 'DAK LAK', destination: '', tier: 'tt', unit_price_vnd: '85000000' },
      { location: 'VINH LONG', destination: '', tier: 'tt', unit_price_vnd: '75000000' }] }] });
}, world => {
  world.bookShippers = [{ name: 'TT CHUẨN', tier: 'khach', trip_count: 4 }];
  world.clock = NOW;
}));

// Bảng đã lưu, đợt không đều: GIA LAI chỉ có ở đợt giữa, DAK LAK có thêm hàng nơi đến riêng; tên khác DAKLAK; 4 đợt (1 đợt cũ ẩn).
const uneven = { tt_shippers: ['HOA SEN 88'], locations: [{ name: 'DAK LAK', aliases: ['DAKLAK'] }, { name: 'GIA LAI', aliases: [] }, { name: 'LONG AN', aliases: [] }],
  periods: [
    { valid_from: '2026-06-01', valid_to: '2026-07-31', rates: [{ location: 'LONG AN', destination: '', tier: 'khach', unit_price_vnd: '50000000' }] },
    { valid_from: '2026-08-01', valid_to: '2026-09-14', rates: [
      { location: 'DAK LAK', destination: '', tier: 'khach', unit_price_vnd: '65000000' }, { location: 'DAK LAK', destination: '', tier: 'tt', unit_price_vnd: '79000000' },
      { location: 'LONG AN', destination: '', tier: 'khach', unit_price_vnd: '52000000' }] },
    { valid_from: '2026-09-15', valid_to: '2026-10-09', rates: [
      { location: 'DAK LAK', destination: '', tier: 'khach', unit_price_vnd: '65000000' }, { location: 'DAK LAK', destination: 'TÂN THANH', tier: 'khach', unit_price_vnd: '67000000' },
      { location: 'GIA LAI', destination: '', tier: 'khach', unit_price_vnd: '80000000' }, { location: 'LONG AN', destination: '', tier: 'khach', unit_price_vnd: '52000000' }] },
    { valid_from: '2026-10-10', valid_to: null, rates: [
      { location: 'DAK LAK', destination: '', tier: 'khach', unit_price_vnd: '67000000' }, { location: 'DAK LAK', destination: '', tier: 'tt', unit_price_vnd: '81000000' },
      { location: 'DAK LAK', destination: 'TÂN THANH', tier: 'khach', unit_price_vnd: '69000000' }, { location: 'LONG AN', destination: '', tier: 'khach', unit_price_vnd: '52000000' }] }] };

test('ma trận: đợt không đều, đợt cũ ẩn; đổi giá từ ngày thêm cột chép giá, đợt cũ kết thúc ngày liền trước; dán một cột giá; lưu giữ tên khác', async () => withPage(async ({ page, world, shot }) => {
  const dialog = await openTable(page);
  assert.deepEqual(await heads(page), ['01/08 – 14/09/2026 hết hạn', '15/09 – 09/10/2026 hết hạn', 'Từ 10/10/2026 đang dùng']);
  assert.equal(await dialog.locator('.pm-older').innerText(), '‹ Xem 1 đợt cũ hơn');
  assert.deepEqual(await matrix(page), [
    ['DAK LAK', '', '65.000.000', '79.000.000', '65.000.000', '', '67.000.000', '81.000.000'],
    ['DAK LAK', 'TÂN THANH', '', '', '67.000.000', '', '69.000.000', ''],
    ['GIA LAI', '', '', '', '80.000.000', '', '', ''],
    ['LONG AN', '', '52.000.000', '', '52.000.000', '', '52.000.000', '']]);
  assert.equal(await dialog.locator('.price-dirty').isVisible(), false);
  assert.equal(await price(page, 3, 0).evaluate(input => input.classList.contains('changed')), true, 'so với đợt 06/2026 đang ẩn');
  await dialog.locator('.pm-older').click();
  assert.equal((await heads(page)).length, 4);
  await dialog.locator('.pm-older').click();
  assert.equal((await heads(page)).length, 3);

  await dialog.locator('.pm-find').fill('dak');
  assert.equal(await rowsOf(page).count(), 2);
  await dialog.locator('.pm-find').fill('');

  await dialog.locator('.price-new-open').click();
  await page.fill('.price-new-from', '10/11/2026');
  await dialog.locator('.price-new-ok').click();
  assert.deepEqual(await heads(page), ['15/09 – 09/10/2026 hết hạn', '10/10 – 09/11/2026 đang dùng', 'Từ 10/11/2026 đợt mới']);
  assert.match(await dialog.locator('.pm-side').innerText(), /Đợt giá mới[\s\S]*Đợt 10\/10\/2026 tự kết thúc ngày 09\/11\/2026\.[\s\S]*0 nơi đi đổi giá/);
  assert.deepEqual((await matrix(page)).map(row => row.slice(-2)), [['67.000.000', '81.000.000'], ['69.000.000', ''], ['', ''], ['52.000.000', '']]);
  assert.equal(await page.evaluate(() => document.activeElement?.dataset.tier), 'khach', 'con trỏ ở ô giá đầu của cột mới');

  // Dán một cột giá (2 dòng) vào cột mới từ hàng DAK LAK → TÂN THANH: điền xuống, GIA LAI có giá.
  await price(page, 1, 2).focus();
  await page.evaluate(() => {
    const data = new DataTransfer();
    data.setData('text/plain', '70,000,000\n82,000,000\n');
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  });
  assert.match(await dialog.locator('.price-msg').innerText(), /Đã dán 2 ô giá vào đợt Từ 10\/11\/2026/);
  assert.deepEqual(await Promise.all([1, 2].map(r => price(page, r, 2).inputValue())), ['70.000.000', '82.000.000']);
  assert.equal(await price(page, 1, 2).evaluate(input => input.classList.contains('edited')), true, 'ô sửa tô vàng');
  assert.match(await dialog.locator('.pm-counts').innerText(), /2 nơi đi đổi giá/);
  // Sửa ngày đợt mới: ngày kết thúc của đợt cũ đi theo.
  await page.fill('#pm-from', '15/11/2026');
  await page.press('#pm-from', 'Enter');
  assert.deepEqual((await heads(page)).slice(1), ['10/10 – 14/11/2026 đang dùng', 'Từ 15/11/2026 đợt mới']);
  await shot('bang-gia-dot-moi');

  await saveAndWait(page);
  const table = saves(world)[0].price_table;
  assert.deepEqual(table.locations, uneven.locations);
  assert.deepEqual(table.tt_shippers, ['HOA SEN 88']);
  assert.deepEqual(table.periods.map(period => [period.valid_from, period.valid_to, period.rates.length]),
    [['2026-06-01', '2026-07-31', 1], ['2026-08-01', '2026-09-14', 3], ['2026-09-15', '2026-10-09', 4], ['2026-10-10', '2026-11-14', 4], ['2026-11-15', null, 5]]);
  assert.deepEqual(table.periods[4].rates.map(rate => [rate.location, rate.destination, rate.tier, rate.unit_price_vnd]), [
    ['DAK LAK', '', 'khach', '67000000'], ['DAK LAK', '', 'tt', '81000000'], ['DAK LAK', 'TÂN THANH', 'khach', '70000000'],
    ['GIA LAI', '', 'khach', '82000000'], ['LONG AN', '', 'khach', '52000000']]);
}, world => { world.priceTable = uneven; world.clock = NOW; }));

test('ma trận: lỗi hiện bằng chữ tại đầu cột và tại ô (ngày sai, đến trước từ, trùng ngày, giá sai, thiếu nơi đi), Lưu bị chặn; sửa đợt, bỏ đợt, thêm và bỏ nơi đi', async () => withPage(async ({ page, world, shot }) => {
  const dialog = await openTable(page);
  // Ngày sai của đợt: báo ở đầu cột và khối phải, không tô cả cột.
  await dialog.locator('.pm-period').nth(1).click();
  await page.fill('#pm-from', '32/09/2026');
  assert.match((await heads(page))[1], /Từ ngày sai/);
  assert.equal(await dialog.locator('.pm-error').innerText(), 'Từ ngày sai');
  assert.equal(await dialog.locator('.pm-grid input.bad').count(), 0, 'lỗi ngày không tô ô giá');
  await page.fill('#pm-from', '15/09/2026');
  await page.fill('#pm-to', '01/09/2026');
  assert.match((await heads(page))[1], /Đến trước Từ ngày/);
  // Trùng ngày cùng nơi đi + nơi đến + loại giá: hai ô liên quan có viền, chữ ở đầu hai cột và trong danh sách lỗi.
  await page.fill('#pm-to', '15/10/2026');
  await page.press('#pm-to', 'Enter');
  const titles = await heads(page);
  assert.match(titles[1], /Trùng ngày đợt 10\/10\/2026/);
  assert.match(titles[2], /Trùng ngày đợt 15\/09\/2026/);
  assert.match(await dialog.locator('.pm-errors').innerText(), /DAK LAK: đợt 10\/10\/2026 trùng ngày đợt 15\/09\/2026 \(giá khách\)/);
  assert.equal(await dialog.locator('.pm-grid input.bad').count(), 6, 'DAK LAK, DAK LAK → TÂN THANH, LONG AN ở hai đợt');
  await page.fill('#pm-to', '09/10/2026');
  await page.press('#pm-to', 'Enter');
  assert.equal(await dialog.locator('.pm-errors').isVisible(), false);
  // Giá không đọc được: viền ở đúng ô, chữ trong danh sách lỗi có nút Sửa.
  await price(page, 3, 2).fill('5x');
  assert.match(await dialog.locator('.pm-errors').innerText(), /LONG AN, đợt 10\/10\/2026: Giá khách sai/);
  assert.equal(await price(page, 3, 2).getAttribute('aria-invalid'), 'true');
  // Hàng mới có giá mà thiếu nơi đi.
  await dialog.locator('.price-row-add').click();
  assert.equal(await page.evaluate(() => document.activeElement?.dataset.f), 'kho');
  await price(page, 4, 2, 'tt').fill('60000000');
  assert.match(await dialog.locator('.pm-errors').innerText(), /Hàng 5: thiếu Nơi đi/);
  await dialog.locator('header .price-table-save').click();
  assert.match(await dialog.locator('.pm-errors').innerText(), /^Chưa lưu được: 2 lỗi cần sửa/);
  assert.equal(await page.evaluate(() => document.activeElement?.className), 'pm-goto', 'con trỏ ở nút Sửa của lỗi đầu');
  assert.equal(world.requests.length, 0, 'còn lỗi thì không gửi gì');
  await shot('bang-gia-loi');
  await dialog.locator('.pm-goto').first().click();
  assert.equal(await page.evaluate(() => document.activeElement?.dataset.tier), 'khach');
  await price(page, 3, 2).fill('53,000,000');
  await place(page, 4).fill('can tho');
  await place(page, 4).press('Enter');
  assert.equal(await place(page, 4).inputValue(), 'CAN THO');
  assert.equal(await dialog.locator('.pm-errors').isVisible(), false);
  // Bỏ hàng GIA LAI và bỏ đợt cũ nhất đang hiện.
  await rowsOf(page).nth(2).locator('.price-row-drop').click();
  await dialog.locator('.pm-period').first().click();
  await dialog.locator('.price-period-drop').click();
  assert.match(await dialog.locator('.price-msg').innerText(), /Đã bỏ đợt 01\/08 – 14\/09\/2026/);
  await saveAndWait(page);
  const table = saves(world)[0].price_table;
  assert.deepEqual(table.periods.map(period => period.valid_from), ['2026-06-01', '2026-09-15', '2026-10-10']);
  assert.deepEqual(table.locations.map(item => item.name), ['DAK LAK', 'LONG AN', 'CAN THO']);
  assert.deepEqual(table.periods[2].rates.filter(rate => rate.location !== 'DAK LAK'), [
    { location: 'LONG AN', destination: '', tier: 'khach', unit_price_vnd: '53000000' }, { location: 'CAN THO', destination: '', tier: 'tt', unit_price_vnd: '60000000' }]);
}, world => { world.priceTable = uneven; world.clock = NOW; }));

test('ma trận: shipper áp giá TT ở khối phải — đếm chuyến, shipper trong sổ đang lấy giá khách, tên gần giống chuyển sang giá TT, thêm và bỏ', async () => withPage(async ({ page, world }) => {
  const dialog = await openTable(page);
  const side = dialog.locator('.pm-side');
  assert.match(await side.locator('.pm-ships').innerText(), /HOA SEN 88\s*28 chuyến/);
  assert.deepEqual(await side.locator('.pm-khach li').allInnerTexts().then(items => items.map(item => item.replace(/\s+/g, ' ').trim())),
    ['BIỂN XANH 37 chuyến', 'HOASEN 88 4 chuyến Gần giống HOA SEN 88 Chuyển sang giá TT']);
  await side.locator('.price-ship-move').click();
  assert.match(await side.locator('.pm-ships').innerText(), /HOASEN 88\s*4 chuyến/);
  assert.equal(await side.locator('.pm-khach li').count(), 1);
  await page.fill('#pm-ship-new', ' sao  mai ');
  await page.press('#pm-ship-new', 'Enter');
  assert.match(await side.locator('.pm-ships').innerText(), /SAO MAI\s*chưa có chuyến/);
  await side.locator('.price-ship-drop').first().click();
  assert.match(await dialog.locator('.price-dirty').innerText(), /^Chưa lưu$/);
  await saveAndWait(page);
  assert.deepEqual(saves(world)[0].price_table.tt_shippers, ['HOASEN 88', 'SAO MAI']);
}, world => {
  world.priceTable = uneven;
  world.clock = NOW;
  world.bookShippers = [{ name: 'HOA SEN 88', tier: 'tt', trip_count: 28 }, { name: 'HOASEN 88', tier: 'khach', trip_count: 4 }, { name: 'Biển  Xanh', tier: 'khach', trip_count: 37 }];
}));

test('ma trận: sổ chưa ghi shipper thì khối phải nói rõ mọi chuyến lấy giá khách', async () => withPage(async ({ page }) => {
  const dialog = await openTable(page);
  assert.match(await dialog.locator('.pm-side').innerText(), /Chuyến trong sổ chưa có tên shipper: mọi chuyến lấy giá khách\./);
}, world => { world.priceTable = uneven; world.clock = NOW; }));

test('ma trận: lỗi server và STALE_LEDGER giữ bảng đang sửa; Esc đóng khối phải trước, rồi hỏi khi còn thay đổi', async () => withPage(async ({ page, world }) => {
  const dialog = await openTable(page);
  await price(page, 0, 2, 'tt').fill('85.000.000');
  world.failNext = { error: 'PRICE_PERIOD_OVERLAP', message: 'Hai đợt giá trùng ngày ở cùng kho và cùng loại giá.' };
  await dialog.locator('header .price-table-save').click();
  await dialog.locator('.price-msg.bad', { hasText: 'trùng ngày' }).waitFor();
  assert.equal(await price(page, 0, 2, 'tt').inputValue(), '85.000.000');
  world.version = 7;   // sổ đổi ở nơi khác
  await dialog.locator('header .price-table-save').click();
  await dialog.locator('.price-msg.bad', { hasText: 'Sổ vừa thay đổi ở nơi khác' }).waitFor();
  assert.equal(await price(page, 0, 2, 'tt').inputValue(), '85.000.000');
  assert.equal(await dialog.isVisible(), true);

  await dialog.locator('.price-new-open').click();
  await page.keyboard.press('Escape');
  assert.equal(await dialog.locator('.pm-side h3').innerText(), 'Shipper áp giá TT', 'Esc đóng khối Đợt giá mới');
  await page.keyboard.press('Escape');
  assert.match(await dialog.locator('.price-msg.ask').innerText(), /thay đổi chưa lưu/);
  await page.keyboard.press('Escape');
  assert.equal(await dialog.locator('.price-msg.ask').count(), 0, 'Esc lần nữa là Ở lại');
  await dialog.locator('.price-table-close').click();
  await dialog.locator('.price-discard').click();
  assert.equal(await dialog.isVisible(), false);
}, world => { world.priceTable = uneven; world.clock = NOW; }));

test('ma trận ở 1280×560 có thanh cuộn: 3 đợt vừa khung không cuộn ngang; nút Lưu, đợt đang dùng và danh sách lỗi nằm trên mép 560', async () => withPage(async ({ page }) => {
  await page.setViewportSize({ width: 1265, height: 560 });
  const dialog = await openTable(page);
  await price(page, 0, 2).fill('abc');
  const box = await page.evaluate(() => {
    const rect = selector => document.querySelector(selector).getBoundingClientRect();
    const scroll = document.querySelector('.pm-scroll');
    return { overflow: scroll.scrollWidth - scroll.clientWidth, save: rect('.price-table-save').bottom, now: rect('th.ph.st-now').bottom,
      errors: rect('.pm-errors').bottom, rows: [...document.querySelectorAll('.pm-grid tbody tr')].filter(row => row.getBoundingClientRect().bottom <= 548).length };
  });
  assert.ok(box.overflow <= 0, `cuộn ngang ${box.overflow}px`);
  assert.ok(box.save < 560 && box.now < 560 && box.errors < 560, JSON.stringify(box));
  assert.equal(box.rows, 4, 'cả 4 hàng giả nằm trong khung');
  assert.equal(await dialog.locator('.pm-hint').isVisible(), true);
}, world => { world.priceTable = uneven; world.clock = NOW; }));

const savedTable = { tt_shippers: [], locations: [{ name: 'DAK LAK', aliases: [] }], periods: [
  { valid_from: '2026-09-11', valid_to: null, rates: [{ location: 'DAK LAK', destination: 'CẢNG B', tier: 'khach', unit_price_vnd: '75000000' }] }] };
const saveEditedTable = async (page, value) => {
  const dialog = await openTable(page);
  await price(page, 0, 0).fill(value);
  return dialog;
};

test('cùng nơi đi, hai nơi đến giữ hai hàng giá riêng khi mở và lưu', async () => withPage(async ({ page, world }) => {
  await openTable(page);
  assert.deepEqual([await place(page, 0, 'den').inputValue(), await place(page, 1, 'den').inputValue()], ['CẢNG A', 'CẢNG B']);
  await price(page, 0, 0).fill('71000000');
  await saveAndWait(page);
  const rates = saves(world)[0].price_table.periods[0].rates;
  assert.deepEqual(rates.map(rate => [rate.destination, rate.unit_price_vnd]), [['CẢNG A', '71000000'], ['CẢNG B', '75000000']]);
}, world => {
  world.priceTable = { ...savedTable, periods: [{ valid_from: '2026-09-11', valid_to: null, rates: [
    { location: 'DAK LAK', destination: 'CẢNG A', tier: 'khach', unit_price_vnd: '70000000' },
    { location: 'DAK LAK', destination: 'CẢNG B', tier: 'khach', unit_price_vnd: '75000000' }] }] };
}));

test('BANG-GIA-02: lưu bảng giá báo trước khi lưu; sau khi lưu báo từng chuyến giá cũ → mới, tháng khóa và chuyến hết giá; chỉ gửi một lệnh', async () => withPage(async ({ page, world, shot }) => {
  const dialog = await saveEditedTable(page, '76000000');
  assert.match(await dialog.locator('.pm-hint').innerText(), /Lưu xong, chuyến đang theo bảng ở tháng mở tự đổi giá/);
  await shot('bang-gia-chua-luu');
  await saveAndWait(page);
  const notice = await page.locator('.live-notice').innerText();
  assert.match(notice, /Đã đổi giá 4 chuyến: FAKE-1 75\.000\.000 → 76\.000\.000; FAKE-2 75\.000\.000 → 76\.000\.000; FAKE-3 77\.000\.000 → 76\.000\.000 và 1 chuyến khác \(xem Lịch sử\)\./);
  assert.match(notice, /Tổng tiền các chuyến tăng 2\.000\.000 đ\./);
  assert.match(notice, /2 chuyến ở tháng khóa chưa đổi: mở khóa tháng rồi bấm "Áp lại giá mới"\./);
  assert.match(notice, /1 chuyến không còn giá trong bảng mới, giữ giá đang ghi\./);
  assert.doesNotMatch(notice, /không tự đổi/);
  assert.equal(await page.locator('.page-more').evaluate(node => node.open), false, 'menu ⋯ không che thông báo');
  assert.equal(await dialog.isVisible(), false, 'lưu xong thì đóng khung');
  await shot('bang-gia-da-doi');
  assert.deepEqual(posts(world).map(([path]) => path), ['/api/v7/price-table/preview', '/api/v7/price-table'], 'đổi giá nằm trong lệnh lưu, không gửi lệnh áp riêng');
}, world => {
  world.priceTable = savedTable;
  world.repricedTrips = ['1', '2', '3', '4'].map((n, index) => ({ trip_id: index + 1, container: `FAKE-${n}`, before_vnd: index === 2 ? '77000000' : '75000000', after_vnd: '76000000' }));
  world.repricedDelta = '2000000';
  world.lockedTrips = 2;
  world.noPriceTrips = 1;
}));

test('BANG-GIA-02: giá giảm thì báo giảm; không có chuyến nào đổi thì chỉ báo đã lưu', async () => withPage(async ({ page, world }) => {
  await saveEditedTable(page, '74000000');
  await saveAndWait(page);
  await page.waitForFunction(() => /Tổng tiền các chuyến giảm 1\.000\.000 đ\./.test(document.querySelector('.live-notice')?.textContent ?? ''));
  world.repricedTrips = [];
  world.repricedDelta = '0';
  await saveEditedTable(page, '73000000');
  await saveAndWait(page);
  await page.waitForFunction(() => document.querySelector('.live-notice')?.textContent === 'Đã lưu bảng giá.');
}, world => {
  world.priceTable = savedTable;
  world.repricedTrips = [{ trip_id: 1, container: 'FAKE-1', before_vnd: '75000000', after_vnd: '74000000' }];
  world.repricedDelta = '-1000000';
}));

test('BANG-GIA-05: Xem lại trước khi lưu — số chuyến đổi giá do server tính, bảng đổi gì, quay lại sửa giữ bảng; lưu đúng bảng đã xem', async () => withPage(async ({ page, world, shot }) => {
  const dialog = await openTable(page);
  await dialog.locator('.price-new-open').click();
  await page.fill('.price-new-from', '10/11/2026');
  await dialog.locator('.price-new-ok').click();
  await price(page, 0, 2).fill('69,000,000');
  await price(page, 0, 2).press('Enter');
  await dialog.locator('header .price-table-save').click();
  const review = page.locator(`${D} .price-review`);
  await review.locator('.rv-tiles').waitFor();
  await shot('bang-gia-xem-lai');
  assert.equal(await review.locator('.price-review-save').innerText(), 'Lưu và đổi giá 2 chuyến');
  assert.deepEqual(await review.locator('.rv-tile').evaluateAll(nodes => nodes.map(node => node.innerText.replace(/\s+/g, ' ').trim())),
    ['2 chuyến tự đổi sang giá mới', '+4.000.000 đ còn nợ của khách tăng']);
  assert.equal(await review.locator('.rv-kept').innerText(), 'Giữ nguyên giá: 1 chuyến giá gõ tay khác bảng; 3 chuyến ở tháng khóa.');
  assert.match(await review.locator('.rv-trips').innerText(), /FAKE-1\s+[\s\S]*giá khách\s+67\.000\.000\s+69\.000\.000/);
  const table = await review.locator('.rv-table').innerText();
  assert.match(table, /Thêm đợt giá từ 10\/11\/2026\./);
  assert.match(table, /Đợt 10\/10\/2026 kết thúc ngày 09\/11\/2026\./);
  assert.match(table, /Đợt từ 10\/11\/2026\s+DAK LAK giá khách\s+67\.000\.000\s+69\.000\.000\s+\+2\.000\.000/);
  assert.doesNotMatch(table, /LONG AN/, 'giá giữ như đợt trước không liệt kê');
  assert.deepEqual(posts(world).map(([path]) => path), ['/api/v7/price-table/preview'], 'xem lại chưa ghi gì');
  const previewed = posts(world)[0][1];

  // Quay lại sửa (và Esc) giữ nguyên bảng đang sửa.
  await review.locator('.price-review-back').click();
  assert.equal(await price(page, 0, 2).inputValue(), '69.000.000');
  await dialog.locator('header .price-table-save').click();
  await review.locator('.rv-tiles').waitFor();
  await page.keyboard.press('Escape');
  assert.equal(await review.count(), 0);
  assert.equal(await dialog.locator('.pm-grid').isVisible(), true);

  await saveAndWait(page);
  const [body] = saves(world);
  assert.deepEqual([body.expected_version, body.price_table], [previewed.expected_version, previewed.price_table], 'lưu đúng bảng và phiên bản đã xem');
  assert.notEqual(body.idempotency_key, previewed.idempotency_key);
  assert.equal(saves(world).length, 1);
}, world => {
  world.priceTable = uneven;
  world.clock = NOW;
  world.repricedTrips = [{ trip_id: 11, container: 'FAKE-1', before_vnd: '67000000', after_vnd: '69000000' }, { trip_id: 12, container: 'FAKE-2', before_vnd: '67000000', after_vnd: '69000000' }];
  world.repricedDelta = '4000000';
  world.typedTrips = 1;
  world.lockedTrips = 3;
}));

test('BANG-GIA-05: máy chủ chưa tính được bước xem lại thì vẫn thấy bảng đổi gì và lưu được, lưu xong báo từng chuyến', async () => withPage(async ({ page }) => {
  await saveEditedTable(page, '76000000');
  await page.locator(`${D} header .price-table-save`).click();
  const review = page.locator(`${D} .price-review`);
  await review.locator('.rv-trips', { hasText: 'Chưa tính được trước chuyến nào đổi giá' }).waitFor();
  assert.equal(await review.locator('.price-review-save').innerText(), 'Lưu bảng giá');
  await review.locator('.price-review-save').click();
  await page.waitForFunction(() => /Đã đổi giá 1 chuyến/.test(document.querySelector('.live-notice')?.textContent ?? ''));
}, world => {
  world.priceTable = savedTable;
  world.previewFail = true;
  world.repricedTrips = [{ trip_id: 1, container: 'FAKE-1', before_vnd: '75000000', after_vnd: '76000000' }];
  world.repricedDelta = '1000000';
}));
