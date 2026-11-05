/* Trình duyệt (Playwright) cho bảng chi tiết của sổ (SO-CHI-TIET-01, specs/v7-so-chi-tiet.md). Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { todayMonth, viewMonth, withPage } = require('./so-khach-v7-browser-world');

const KEY = todayMonth.slice(0, 7);
// Dòng khách tự trả cước, cộng được; mỗi trạng thái khác ghi đè phần của nó.
const base = (id, container, extra) => ({ kind: 'legacy', id, month: KEY, container, has_detail: true, day: '03/09', bill: `MAU${id}`, ship: 'TÀU MẪU 201N', etd: '06/09', eta: '10/09',
  from: 'KHO MỘT - TỈNH A', to: 'SHEKOU', of_counted: false, ledger_vnd: '22750200', differs: false, fee_vnd: '565000', service_vnd: '6000000', truck_vnd: '14500000', of_vnd: '21000000',
  vat_vnd: '1685200', total_vnd: '22750200', sheet_total_vnd: '22750200', state: 'ok', adds_up: true, phi_vnd: '22750200', parts_vnd: '22750200', adds_diff_vnd: null, sheet_diff_vnd: '0', ...extra });
const unlisted = { has_detail: false, bill: '', etd: '', eta: '', fee_vnd: null, service_vnd: null, truck_vnd: null, of_vnd: null, vat_vnd: null, sheet_total_vnd: null,
  adds_up: false, phi_vnd: null, parts_vnd: null, sheet_diff_vnd: null };
const DETAILS = { rows: [
  base(1, 'ABCU2000011', {}),
  base(2, 'ABCU2000026', { of_counted: true, of_vnd: '12500000', ledger_vnd: '35250200', total_vnd: '35250200', sheet_total_vnd: '35250200', parts_vnd: '35250200' }),
  base(3, 'ABCU2000032', { state: 'differs', differs: true, ledger_vnd: '22000000', total_vnd: '22000000', sheet_diff_vnd: '750200' }),
  base(4, 'ABCU2000047', { state: 'differs', differs: true, ledger_vnd: '23000000', total_vnd: '23000000', sheet_diff_vnd: '-249800' }),
  base(5, 'ABCU2000053', { state: 'no_add', adds_up: false, of_counted: true, of_vnd: '12500000', parts_vnd: '35250200', ledger_vnd: '32680200', total_vnd: '32680200', sheet_total_vnd: '32680200', adds_diff_vnd: '2570000' }),
  base(6, 'ABCU2000068', { ...unlisted, state: 'no_detail', ledger_vnd: '5000000', total_vnd: '5000000' }),
  base(7, 'ABCU2000074', { ...unlisted, state: 'no_price', ledger_vnd: '0', total_vnd: null }),
  base(8, '', { ...unlisted, state: 'loose', from: '', to: '', ship: '', ledger_vnd: '700000', total_vnd: '700000' }),
], months: { [KEY]: { fee_vnd: '1695000', service_vnd: '18000000', truck_vnd: '43500000', vat_vnd: '5055600', of_counted_vnd: '25000000', of_customer_vnd: '63000000',
  total_vnd: '141380600', no_detail: 2, differs: ['ABCU2000032', 'ABCU2000047'], sheet_diff_vnd: '500400', charges_vnd: '141380600', diff_vnd: '0',
  compare_differs: 2, compare_diff_vnd: '500400', compare_no_add: 1 } } };
const STATE_ROWS = DETAILS.rows.length;
const trip = { id: 900, month: `${KEY}-01`, container: 'ABCU2000011', carrier: 'WH', event_date: todayMonth, origin: 'KHO', destination: 'CANG', unit_price_vnd: '1000000', other_fee_vnd: null,
  amount_vnd: '1000000', status: 'confirmed', is_missing_price: false, is_fee_only: false, editable: true, info_editable: true, deleted: false };
const withDetails = (world, details = DETAILS) => {
  world.month = null;
  world.details = details;
  world.trips = [trip];
};
// Tháng đủ số: không báo gì, không chip.
const CLEAN = { rows: [base(1, 'ABCU2000011', {})], months: { [KEY]: { ...DETAILS.months[KEY], total_vnd: '22750200', charges_vnd: '22750200', no_detail: 0, differs: [], sheet_diff_vnd: '0',
  compare_differs: 0, compare_diff_vnd: '0', compare_no_add: 0, of_customer_vnd: '21000000' } } };
const row = (page, id) => page.locator(`tr[data-detail="legacy-${id}"]`);
const texts = async locator => (await locator.allInnerTexts()).map(item => item.replace(/\s+/g, ' ').trim());
const rowIds = page => page.locator('.detail-table tbody tr[data-detail]').evaluateAll(rows => rows.map(item => item.dataset.detail));
const lines = page => page.locator('tr.dt-more .dt-line').evaluateAll(items => items.map(item => [...item.children].map(cell => cell.textContent).join('|')));

test('Bảng gọn là mặc định: cột phép cộng, cước khách tự trả đứng ngoài, mỗi trạng thái ghi bằng chữ', async () => withPage(async ({ page }) => {
  await page.locator('.dt-gon').waitFor();
  assert.deepEqual(await texts(page.locator('.dt-gon thead th')), ['STT', 'Số container', 'Ngày đóng', 'Nơi đóng hàng → Cảng đến', 'Phí mình thu', '+ Cước tàu mình thu', '= Tổng', 'Cước khách tự trả (không tính)', '']);
  assert.equal(await page.locator('.dt-gon tbody tr').count(), STATE_ROWS);
  assert.equal(await page.locator('.trip-list').count(), 0);
  assert.equal(await page.locator('.trip-card > .ledger-head').isVisible(), false);
  assert.equal(await page.locator('.trip-toolbar h3').innerText(), '7 chuyến trong tháng');
  // Cộng được: khách tự trả nằm ngoài phép cộng, mình thu nằm trong.
  assert.deepEqual(await texts(row(page, 1).locator('td')), ['1', 'ABCU2000011', '03/09', 'KHO MỘT - TỈNH A → SHEKOU', '22.750.200', '–', '22.750.200', '21.000.000', '']);
  assert.deepEqual(await texts(row(page, 2).locator('td.num')), ['22.750.200', '12.500.000', '35.250.200', '–']);
  // Khác sổ: chữ hơn/kém, ô Tổng theo sổ có viền cam, nền xám nhạt.
  const over = row(page, 3).locator('.dt-status');
  assert.equal(await over.innerText(), 'Bảng kê hơn 750.200');
  assert.equal(await row(page, 4).locator('.dt-status').innerText(), 'Bảng kê kém 249.800');
  assert.equal(await row(page, 3).locator('.dt-total').innerText(), '22.000.000');
  assert.equal(await row(page, 3).locator('.dt-total').getAttribute('title'), 'Bảng kê ghi 22.750.200');
  assert.equal((await row(page, 3).locator('.dt-total').evaluate(cell => getComputedStyle(cell).outlineColor)), 'rgb(199, 119, 0)');
  assert.equal((await over.evaluate(cell => getComputedStyle(cell).backgroundColor)), 'rgb(248, 249, 251)');
  // Không cộng ra Tổng: nhãn trung tính, không kết luận bên nào sai.
  assert.equal(await row(page, 5).locator('.dt-status').innerText(), 'Bảng kê không cộng ra Tổng');
  assert.equal((await row(page, 5).locator('.dt-total').evaluate(cell => getComputedStyle(cell).outlineColor)), 'rgb(199, 119, 0)');
  assert.doesNotMatch(await page.locator('.detail-table').innerText(), /cộng thừa|sai/i);
  // Chưa có trên bảng kê: chữ xám. Chưa có giá: nền cam, Tổng trống, không hiện như 0.
  const quiet = row(page, 6).locator('.dt-status');
  assert.equal(await quiet.innerText(), 'Chưa có trên bảng kê');
  assert.equal((await quiet.evaluate(cell => getComputedStyle(cell).color)), 'rgb(111, 109, 103)');
  const missing = row(page, 7).locator('.dt-status');
  assert.equal(await missing.innerText(), 'Chưa có giá');
  assert.equal((await missing.evaluate(cell => getComputedStyle(cell).backgroundColor)), 'rgb(253, 243, 225)');
  assert.equal(await row(page, 7).locator('.dt-total').innerText(), '–');
  // Không container.
  assert.deepEqual(await texts(row(page, 8).locator('td')), ['–', 'Phí lẻ', '03/09', '–', 'Không gắn container', '700.000', '–', '']);
  // Dòng cuối: cùng số với Phát sinh, cộng riêng cước khách tự trả.
  assert.deepEqual(await texts(page.locator('.dt-gon tfoot td')), ['Cộng cả tháng, bằng Phát sinh', '141.380.600', '63.000.000', '']);
}, withDetails));

test('Bấm cả dòng để bung tại chỗ: thông tin chuyến và phép cộng; một dòng mở một lúc, bấm lại thì thu', async () => withPage(async ({ page }) => {
  await page.locator('.dt-gon').waitFor();
  await row(page, 1).locator('.dt-route').click();
  assert.deepEqual(await texts(page.locator('tr.dt-more .dt-infos dd')), ['MAU1', 'TÀU MẪU 201N', '06/09 · 10/09', 'KHO MỘT - TỈNH A', 'SHEKOU']);
  assert.deepEqual(await texts(page.locator('tr.dt-more .dt-infos dt')), ['Bill', 'Tên tàu', 'ETD · ETA', 'Nơi đóng hàng', 'Cảng đến']);
  assert.deepEqual(await lines(page), ['|Phí phát sinh|565.000', '+|Phí DV hải quan|6.000.000', '+|Cước nội địa|14.500.000', '+|VAT 8%|1.685.200', '=|Tổng|22.750.200', '|Cước tàu khách tự trả, không tính|21.000.000']);
  assert.equal(await row(page, 1).locator('.dt-arrow').getAttribute('aria-expanded'), 'true');
  // Mình thu cước: có dòng cộng cước trong phép cộng. Mở dòng khác thì dòng trước thu lại.
  await row(page, 2).click();
  assert.equal(await page.locator('tr.dt-more').count(), 1);
  assert.deepEqual((await lines(page)).slice(-2), ['+|Cước tàu mình thu|12.500.000', '=|Tổng|35.250.200']);
  // Khác sổ: khoản của bảng kê, bảng kê ghi, sổ đang tính, phần chênh.
  await row(page, 3).click();
  assert.deepEqual((await lines(page)).slice(4), ['=|Bảng kê ghi|22.750.200', '|Sổ đang tính, số nợ theo số này|22.000.000', '|Bảng kê hơn sổ|750.200', '|Cước tàu khách tự trả, không tính|21.000.000']);
  assert.match(await page.locator('.dt-hint').innerText(), /Nếu bảng kê đã cũ, dán lại trên Sheet/);
  await row(page, 4).click();
  assert.deepEqual((await lines(page)).slice(4, 7), ['=|Bảng kê ghi|22.750.200', '|Sổ đang tính, số nợ theo số này|23.000.000', '|Bảng kê kém sổ|249.800']);
  // Không cộng ra Tổng: không đặt dấu = trước số không phải kết quả, không ngụ ý sai.
  await row(page, 5).click();
  assert.deepEqual((await lines(page)).slice(4), ['+|Cước tàu|12.500.000', '=|Các khoản cộng lại|35.250.200', '|Tổng ghi trên bảng kê, sổ đang tính số này|32.680.200', '|Các khoản hơn Tổng|2.570.000']);
  assert.equal(await page.locator('tr.dt-more .dt-hint').count(), 0);
  assert.doesNotMatch(await page.locator('tr.dt-more').innerText(), /thừa|sai|xem lại/i);
  await row(page, 6).click();
  assert.deepEqual(await lines(page), ['=|Sổ đang tính|5.000.000']);
  assert.match(await page.locator('.dt-hint').innerText(), /Chưa tách được từng khoản/);
  // Chưa có giá: máy lấy giá theo Sheet, không gợi ý nhập ở bảng sổ.
  await row(page, 7).click();
  assert.equal(await page.locator('.dt-hint').innerText(), 'Chờ giá từ Sheet. Chuyến này chưa tính vào nợ.');
  assert.doesNotMatch(await page.locator('.detail-table').innerText(), /Nhập giá/);
  await row(page, 8).click();
  assert.deepEqual(await texts(page.locator('tr.dt-more .dt-infos dt')), ['Ngày']);
  assert.equal(await page.locator('.dt-hint').innerText(), 'Khoản này lấy nguyên từ sổ.');
  await row(page, 8).click();
  assert.equal(await page.locator('tr.dt-more').count(), 0);
  // Bàn phím: Enter ở mũi tên bung, tiêu điểm vẫn ở đó. Kéo chọn số container thì không bung.
  await row(page, 1).locator('.dt-arrow').focus();
  await page.keyboard.press('Enter');
  await page.locator('tr.dt-more').waitFor();
  assert.equal(await page.evaluate(() => document.activeElement.dataset.open), 'legacy-1');
  await page.keyboard.press('Enter');
  const box = await row(page, 2).locator('.dt-cont').boundingBox();
  await page.mouse.move(box.x + 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + 60, box.y + box.height / 2);
  await page.mouse.up();
  assert.equal(await page.locator('tr.dt-more').count(), 0);
}, withDetails));

test('Chip lọc: số 0 thì ẩn, bấm lại để bỏ, không có Tất cả; lọc Đối chiếu có dòng báo phần chênh; STT giữ theo cả tháng', async () => withPage(async ({ page }) => {
  await page.locator('.dt-gon').waitFor();
  const chips = page.locator('.dt-chip');
  assert.deepEqual(await texts(chips), ['Chưa có giá 1', 'Đối chiếu bảng kê 3', 'Chưa có trên bảng kê 1']);
  assert.equal(await page.locator('.detail-note').count(), 0);
  await chips.nth(1).click();
  assert.deepEqual(await rowIds(page), ['legacy-3', 'legacy-4', 'legacy-5']);
  assert.equal(await row(page, 3).locator('td').first().innerText(), '3');
  assert.equal(await chips.nth(1).innerText(), 'Đối chiếu bảng kê 3 ✕');
  assert.equal(await chips.nth(1).getAttribute('aria-pressed'), 'true');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.filter), 'doi-chieu');
  assert.equal(await page.locator('.detail-note').innerText(), 'Bảng kê khác sổ ở 2 container, cộng lại hơn sổ 500.400. 1 container có các khoản bảng kê không cộng ra Tổng. Tổng và số nợ theo sổ.');
  // Dòng cuối vẫn của cả tháng.
  assert.equal(await page.locator('.dt-foot-total').innerText(), '141.380.600');
  await chips.nth(0).click();
  assert.deepEqual(await rowIds(page), ['legacy-7']);
  assert.equal(await page.locator('.detail-note').count(), 0);
  await chips.nth(2).click();
  assert.deepEqual(await rowIds(page), ['legacy-6']);
  await chips.nth(2).click();
  assert.equal(await page.locator('.detail-table tbody tr').count(), STATE_ROWS);
  assert.equal(await page.locator('.dt-chip[aria-pressed="true"]').count(), 0);
}, withDetails));

test('Bấm nhãn "N chưa giá" ở đầu tháng thì bật chip Chưa có giá ngay tại bảng chi tiết', async () => withPage(async ({ page }) => {
  await page.locator('.dt-gon').waitFor();
  const badge = page.locator('.month-missing');
  assert.equal(await badge.innerText(), 'ⓘ 1 chưa giá');
  await badge.click();
  assert.deepEqual(await rowIds(page), ['legacy-7']);
  assert.equal(await page.locator('.dt-chip[data-filter="chua-gia"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.filter), 'chua-gia');
  // Vẫn ở bảng chi tiết, không sang ?loc=.
  assert.equal(new URL(page.url()).searchParams.has('loc'), false);
  assert.equal(await page.locator('.trip-list').count(), 0);
  // Bấm lại nhãn thì vẫn bật, không tắt.
  await badge.click();
  assert.deepEqual(await rowIds(page), ['legacy-7']);
}, withDetails));

test('Tháng đủ số không hiện chip; cộng các dòng lệch Phát sinh thì báo và không ghi "bằng Phát sinh"', async () => {
  await withPage(async ({ page }) => {
    await page.locator('.dt-gon').waitFor();
    assert.equal(await page.locator('.dt-chips').count(), 0);
    assert.equal(await page.locator('.detail-note').count(), 0);
    assert.equal(await page.locator('.dt-foot-label').innerText(), 'Cộng cả tháng, bằng Phát sinh');
  }, world => withDetails(world, CLEAN));
  await withPage(async ({ page }) => {
    await page.locator('.dt-gon').waitFor();
    assert.equal(await page.locator('.detail-note').innerText(), 'Cộng các dòng 22.750.200, Phát sinh của sổ 23.000.000: lệch 249.800.');
    assert.equal(await page.locator('.dt-foot-label').innerText(), 'Phát sinh của sổ');
    assert.equal(await page.locator('.dt-foot-total').innerText(), '23.000.000');
  }, world => withDetails(world, { ...CLEAN, months: { [KEY]: { ...CLEAN.months[KEY], charges_vnd: '23000000', diff_vnd: '249800' } } }));
});

test('Đủ cột: 15 cột theo file, có chip lọc, trạng thái ghi bằng chữ, nhớ lựa chọn', async () => withPage(async ({ page }) => {
  await page.locator('.dt-gon').waitFor();
  assert.equal(await page.locator('.dt-mode[data-mode="gon"]').getAttribute('aria-pressed'), 'true');
  await page.locator('.dt-mode[data-mode="du"]').click();
  await page.locator('.dt-du').waitFor();
  assert.deepEqual(await texts(page.locator('.dt-du thead th')), ['STT', 'Số container', 'Bill', 'Tên tàu', 'Ngày đóng', 'ETD', 'ETA', 'Nơi đóng hàng', 'Cảng đến',
    'Phí phát sinh', 'Phí DV hải quan', 'Cước nội địa', 'Cước tàu OF', 'VAT 8%', 'Tổng']);
  assert.equal(await row(page, 1).locator('.dt-of-customer').innerText(), '21.000.000');
  assert.equal(await row(page, 2).locator('.dt-of-own').innerText(), '12.500.000');
  assert.equal(await row(page, 3).locator('.dt-status').innerText(), 'Bảng kê hơn 750.200');
  assert.equal(await row(page, 3).locator('.dt-differs').getAttribute('title'), 'Bảng kê ghi 22.750.200');
  assert.equal(await row(page, 5).locator('.dt-status').innerText(), 'Bảng kê không cộng ra Tổng');
  assert.match(await row(page, 5).locator('.dt-differs').getAttribute('title'), /cộng lại 35\.250\.200, Tổng bảng kê ghi 32\.680\.200/);
  assert.equal(await row(page, 6).locator('.dt-status').innerText(), 'Chưa có trên bảng kê');
  assert.equal(await row(page, 7).locator('.dt-status').innerText(), 'Chưa có giá');
  assert.equal(await row(page, 8).locator('.dt-status').innerText(), 'Không gắn container');
  assert.match(await page.locator('.dt-foot-row').innerText(), /Mình thu, tính vào Tổng[\s\S]*Khách tự trả 63\.000\.000, không tính[\s\S]*Cộng cả tháng, bằng Phát sinh: 141\.380\.600/);
  // Dòng ở Đủ cột không bung.
  await row(page, 1).click();
  assert.equal(await page.locator('tr.dt-more').count(), 0);
  await page.locator('.dt-chip').nth(1).click();
  assert.deepEqual(await rowIds(page), ['legacy-3', 'legacy-4', 'legacy-5']);
  await page.reload();
  await page.locator('.dt-du').waitFor();
  assert.equal(await page.locator('.dt-mode[data-mode="du"]').getAttribute('aria-pressed'), 'true');
}, withDetails));

test('Ngày gõ nhầm trên bảng kê: Đủ cột hiện dấu ?, rê chuột thấy nguyên văn, không đè cột bên cạnh; bảng gọn ghi nguyên văn', async () => withPage(async ({ page }) => {
  await page.locator('.dt-gon').waitFor();
  await row(page, 1).click();
  assert.deepEqual((await texts(page.locator('tr.dt-more .dt-infos dd')))[2], '5/110/2026 · 10/09');
  await page.locator('.dt-mode[data-mode="du"]').click();
  await page.locator('.dt-du').waitFor();
  // Cột ETD là cột thứ 6, ETA thứ 7.
  const cells = row(page, 1).locator('td');
  const etd = cells.nth(5);
  assert.equal(await etd.innerText(), '?');
  assert.equal(await etd.getAttribute('title'), 'Bảng kê ghi 5/110/2026, chưa đọc được ngày. Sửa trên Sheet.');
  assert.equal(await etd.getAttribute('aria-label'), 'Bảng kê ghi 5/110/2026, chưa đọc được ngày. Sửa trên Sheet.');
  assert.equal(await etd.evaluate(cell => getComputedStyle(cell).outlineColor), 'rgb(199, 119, 0)');
  assert.equal(await cells.nth(6).innerText(), '10/09');
  // Không đè cột: nội dung nằm gọn trong ô, cả với font rộng.
  const fits = locator => locator.evaluate(cell => {
    const range = document.createRange();
    range.selectNodeContents(cell);
    return range.getBoundingClientRect().right <= cell.getBoundingClientRect().right;
  });
  assert.equal(await fits(etd), true);
  await page.addStyleTag({ content: 'body,body *{font-family:Verdana,"DejaVu Sans",sans-serif !important}' });
  assert.equal(await fits(etd), true);
  // Ngày đọc được và ngày ngắn không năm vẫn hiện bình thường; ô trống vẫn trống.
  assert.equal(await row(page, 2).locator('td').nth(5).innerText(), '3/10');
  assert.equal(await row(page, 2).locator('td').nth(5).getAttribute('title'), null);
  assert.equal(await row(page, 3).locator('td').nth(5).innerText(), '');
  assert.equal(await row(page, 3).locator('td').nth(5).getAttribute('title'), null);
}, world => withDetails(world, { ...CLEAN, rows: [base(1, 'ABCU2000011', { etd: '5/110/2026' }), base(2, 'ABCU2000026', { etd: '3/10' }), base(3, 'ABCU2000032', { etd: '' })] })));

// Số giả cỡ một tháng lớn và chữ dài: hàng trăm triệu ở dòng, hàng tỷ ở dòng cộng.
const BIG = { rows: [
  base(1, 'ABCU2000011', { state: 'no_price', differs: true, total_vnd: null, ledger_vnd: '0', sheet_total_vnd: '44111222' }),
  base(2, 'ABCU2000026', { from: 'KHO MỘT - TỈNH A VÀ MỘT TÊN KHO RẤT DÀI, GẦN CỬA KHẨU SỐ HAI', to: '深圳 SHEKOU PORT', phi_vnd: '888777666', of_counted: true, of_vnd: '777666555', total_vnd: '999888777', ledger_vnd: '999888777', sheet_total_vnd: '999888777' }),
  base(3, 'ABCU2000032', { state: 'no_add', adds_up: false, of_vnd: '888777666', total_vnd: '999888777', ledger_vnd: '999888777', sheet_total_vnd: '999888777', parts_vnd: '999888777', adds_diff_vnd: '-123456' }),
  base(4, 'ABCU2000047', { state: 'differs', differs: true, sheet_diff_vnd: '-123456789', total_vnd: '999888777', ledger_vnd: '999888777', of_vnd: '888777666' }),
], months: { [KEY]: { fee_vnd: '28111222', service_vnd: '288111222', truck_vnd: '299333444', vat_vnd: '98765432', of_counted_vnd: '511222333', of_customer_vnd: '1777555444',
  total_vnd: '12999888777', no_detail: 0, differs: ['ABCU2000011'], sheet_diff_vnd: '-123456789', charges_vnd: '12999888777', diff_vnd: '0', compare_differs: 1, compare_diff_vnd: '-123456789', compare_no_add: 1 } } };

const measure = page => page.evaluate(() => {
  const overflow = cell => {
    const range = document.createRange();
    range.selectNodeContents(cell);
    const style = getComputedStyle(cell);
    const room = cell.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    return range.getBoundingClientRect().width > room + 0.5;
  };
  const tall = button => button.getBoundingClientRect().height;
  return {
    overflowing: [...document.querySelectorAll('.detail-table td.num, .detail-table td.dt-cont, .detail-table .dt-status')].filter(overflow).map(cell => cell.innerText),
    fits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    tableFits: document.querySelector('.detail-table').getBoundingClientRect().right <= document.documentElement.clientWidth,
    route: document.querySelector('.dt-route')?.getBoundingClientRect().width ?? null,
    from: document.querySelector('.dt-du .c-from')?.getBoundingClientRect().width ?? null,
    short: [...document.querySelectorAll('.dt-chip, .dt-mode, .dt-edit, .trip-tools button')].filter(button => button.getClientRects().length && tall(button) < 40).map(button => button.outerHTML.slice(0, 120)),
    rowsLow: [...document.querySelectorAll('tr.dt-row')].filter(item => item.getBoundingClientRect().height < 44).length,
  };
});

test('Không tràn cột, không cuộn ngang ở 1280, kể cả font rộng, thanh cuộn 15px; vùng bấm đủ; tên dài xuống dòng không cắt', async () => withPage(async ({ page, shot }) => {
  // Chrome trên Windows có thanh cuộn dọc 15px mà headless không có: thu bề ngang tương đương.
  for (const width of [1280, 1265]) {
    await page.setViewportSize({ width, height: 720 });
    for (const mode of ['gon', 'du']) {
      await page.locator(`.dt-mode[data-mode="${mode}"]`).click();
      await page.locator(`.dt-${mode}`).waitFor();
      const usual = await measure(page);
      // Máy thiếu Segoe UI (CI Ubuntu) dùng font rộng hơn: đo lại, đỏ thì nới bố cục.
      const wide = await page.addStyleTag({ content: 'body,body *{font-family:Verdana,"DejaVu Sans",sans-serif !important}' });
      const wider = await measure(page);
      await wide.evaluate(node => node.remove());
      for (const result of [usual, wider]) {
        assert.deepEqual(result.overflowing, [], `${mode} ${width}: số tràn cột`);
        assert.equal(result.fits, true, `${mode} ${width}: cuộn ngang`);
        assert.equal(result.tableFits, true, `${mode} ${width}: bảng vượt khung`);
        assert.deepEqual(result.short, [], `${mode} ${width}: nút thấp hơn vùng bấm`);
        if (mode === 'gon') {
          assert.ok(result.route >= 180, `cột tuyến đường còn đọc được: ${result.route}px`);
          assert.equal(result.rowsLow, 0, 'dòng cao ít nhất 44px');
        } else {
          assert.ok(result.from >= 110, `cột Nơi đóng hàng còn đọc được: ${result.from}px`);
        }
      }
    }
  }
  await page.locator('.dt-mode[data-mode="gon"]').click();
  await page.locator('.dt-gon').waitFor();
  // Tên kho dài không bị cắt ở bảng gọn: xuống dòng.
  const route = row(page, 2).locator('.dt-route');
  assert.equal(await route.evaluate(cell => cell.scrollWidth <= cell.clientWidth && getComputedStyle(cell).textOverflow !== 'ellipsis'), true);
  assert.match(await route.innerText(), /深圳 SHEKOU PORT/);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.evaluate(() => document.fonts.ready);
  // Mở dòng ở khung thật 1280: ảnh để xem bằng mắt.
  await row(page, 3).click();
  await shot('so-chi-tiet-gon-1280');
}, world => withDetails(world, BIG)));

test('Vùng bấm và tiêu điểm: nhãn chưa giá đủ 40px bằng vùng trong suốt, dòng có trạng thái rê chuột, mũi tên có viền tiêu điểm', async () => withPage(async ({ page, shot }) => {
  await page.locator('.dt-gon').waitFor();
  const hit = await page.locator('.month-missing').evaluate(button => {
    const after = getComputedStyle(button, '::after');
    return button.getBoundingClientRect().height + parseFloat(after.top) * -1 + parseFloat(after.bottom) * -1;
  });
  assert.ok(hit >= 40, `vùng bấm nhãn: ${hit}px`);
  await row(page, 1).hover();
  assert.equal(await row(page, 1).locator('.dt-route').evaluate(cell => getComputedStyle(cell).backgroundColor), 'rgb(234, 242, 252)');
  await page.mouse.move(0, 0);
  await row(page, 1).locator('.dt-arrow').focus();
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab');
  assert.equal(await row(page, 1).evaluate(item => getComputedStyle(item).outlineStyle), 'solid');
  await page.evaluate(() => document.fonts.ready);
  await shot('so-chi-tiet-gon-trang-thai');
  await page.locator('.dt-mode[data-mode="du"]').click();
  await page.locator('.dt-du').waitFor();
  await shot('so-chi-tiet-du-cot');
}, withDetails));

test('Tự tải lại giữ nguyên lọc và dòng đang mở; đầu bảng dính khi cuộn', async () => withPage(async ({ page, world }) => {
  await page.setViewportSize({ width: 1280, height: 560 });
  await page.locator('.dt-gon').waitFor();
  await page.locator('.dt-chip[data-filter="doi-chieu"]').click();
  await row(page, 3).click();
  await page.locator('tr.dt-more').waitFor();
  // Bản mới về: lọc và dòng mở còn nguyên.
  world.details = { ...DETAILS, rows: DETAILS.rows.map(item => item.id === 3 ? { ...item, sheet_diff_vnd: '100000' } : item) };
  world.version += 1;
  await page.locator('#refresh-data').click();
  await page.locator('tr[data-detail="legacy-3"] .dt-status', { hasText: 'Bảng kê hơn 100.000' }).waitFor();
  assert.deepEqual(await rowIds(page), ['legacy-3', 'legacy-4', 'legacy-5']);
  assert.equal(await row(page, 3).locator('.dt-arrow').getAttribute('aria-expanded'), 'true');
  // Dòng cuối cùng của nhóm lọc vừa hết: về đủ bảng, không để trống.
  world.details = { ...DETAILS, rows: DETAILS.rows.filter(item => !['differs', 'no_add'].includes(item.state)) };
  world.version += 1;
  await page.locator('#refresh-data').click();
  await page.locator('.dt-chip[data-filter="doi-chieu"]').waitFor({ state: 'detached' });
  assert.equal(await page.locator('.detail-table tbody tr[data-detail]').count(), STATE_ROWS - 3);
  // Đầu bảng dính dưới phần đầu trang khi cuộn.
  world.details = { rows: Array.from({ length: 40 }, (_, index) => base(index + 1, `ABCU2${String(index).padStart(6, '0')}`, {})), months: CLEAN.months };
  world.version += 1;
  await page.locator('#refresh-data').click();
  await page.locator('tr[data-detail="legacy-40"]').waitFor();
  await row(page, 30).scrollIntoViewIfNeeded();
  const sticky = await page.evaluate(() => {
    const head = document.querySelector('.detail-table thead th').getBoundingClientRect();
    return { top: head.top, onScreen: head.top >= 0 && head.bottom < innerHeight, scrolled: scrollY > 0, position: getComputedStyle(document.querySelector('.detail-table thead th')).position };
  });
  assert.equal(sticky.position, 'sticky');
  assert.equal(sticky.scrolled, true);
  assert.equal(sticky.onScreen, true, JSON.stringify(sticky));
}, withDetails));

test('Nút Sửa ở bảng sổ đổi bảng, nhớ lựa chọn, focus giữ ở nút; ?loc= luôn hiện bảng sổ', async () => withPage(async ({ page }) => {
  await page.locator('.detail-table').waitFor();
  assert.equal(await page.locator('.detail-toggle').getAttribute('aria-label'), 'Sửa ở bảng sổ');
  assert.equal((await page.locator('.detail-toggle').innerText()).trim(), '');
  await page.locator('.detail-toggle').click();
  await page.locator('.trip-list').waitFor();
  assert.equal(await page.locator('.detail-table').count(), 0);
  assert.equal(await page.locator('.dt-mode').count(), 0);
  assert.equal(await page.locator('.detail-toggle').innerText(), 'Xem bảng chi tiết');
  assert.equal(await page.evaluate(() => document.activeElement.classList.contains('detail-toggle')), true);
  await page.reload();
  await page.locator('.trip-list').waitFor();
  assert.equal(await page.locator('.detail-toggle').innerText(), 'Xem bảng chi tiết');
  await page.locator('.detail-toggle').click();
  await page.locator('.dt-gon').waitFor();
  const url = new URL(page.url());
  url.searchParams.set('loc', 'thieu-gia');
  await page.goto(url.href);
  await page.locator('.trip-list').waitFor();
  assert.equal(await page.locator('.detail-toggle').count(), 0);
}, withDetails));

test('Sổ đã nhớ giá trị cũ "chi-tiet": mở bảng gọn', async () => withPage(async ({ page }) => {
  await page.locator('.detail-table').waitFor();
  await page.evaluate(() => localStorage.setItem('so-khach-bang', 'chi-tiet'));
  await page.reload();
  await page.locator('.dt-gon').waitFor();
}, withDetails));

test('Sổ không có bảng chi tiết: giữ nguyên bảng sổ, không có nút', async () => withPage(async ({ page }) => {
  await page.locator('.trip-list').waitFor();
  assert.equal(await page.locator('.detail-toggle, .detail-table, .dt-mode, .dt-chip').count(), 0);
  assert.match(await page.locator('.trip-toolbar h3').innerText(), /Chuyến trong tháng · \d+ chuyến/);
}, world => { world.month = null; world.details = { rows: [], months: {} }; }));

// Dòng hỏi khóa tháng nằm dưới thanh công cụ, không lọt vào nhóm nút icon (.trip-tools button rộng cố định 36–40px).
async function assertLockAskLayout(page) {
  const lock = page.locator(`.month-lock[data-month="${todayMonth}"]`);
  const measureAsk = () => page.evaluate(() => {
    const ask = document.querySelector('.lock-ask');
    const card = ask.closest('.trip-card').getBoundingClientRect();
    const tools = document.querySelector('.trip-tools').getBoundingClientRect();
    const box = ask.getBoundingClientRect();
    return {
      inTools: Boolean(ask.closest('.trip-tools')),
      belowTools: box.top >= tools.bottom,
      fullWidth: Math.abs(box.width - card.width) <= 2,
      fits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      buttons: [...ask.querySelectorAll('button')].map(button => {
        const range = document.createRange();
        range.selectNodeContents(button);
        return { text: button.innerText, lines: range.getClientRects().length, height: button.getBoundingClientRect().height, clipped: button.scrollWidth > button.clientWidth };
      }),
    };
  });
  for (const width of [1280, 1265]) {
    await page.setViewportSize({ width, height: 720 });
    await lock.click();
    const usual = await measureAsk();
    const wide = await page.addStyleTag({ content: 'body,body *{font-family:Verdana,"DejaVu Sans",sans-serif !important}' });
    const wider = await measureAsk();
    await wide.evaluate(node => node.remove());
    for (const result of [usual, wider]) {
      assert.equal(result.inTools, false, `${width}: dòng hỏi lọt vào nhóm nút icon`);
      assert.equal(result.belowTools, true, `${width}: dòng hỏi không nằm dưới thanh công cụ`);
      assert.equal(result.fullWidth, true, `${width}: dòng hỏi không rộng hết khung bảng`);
      assert.equal(result.fits, true, `${width}: cuộn ngang`);
      assert.equal(result.buttons.length, 2);
      for (const button of result.buttons) {
        assert.equal(button.lines, 1, `${width}: nút "${button.text}" xuống dòng`);
        assert.equal(button.clipped, false, `${width}: nút "${button.text}" bị cắt`);
        assert.ok(button.height >= 36, `${width}: nút "${button.text}" thấp ${button.height}px`);
      }
    }
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.lock-ask').count(), 0);
  }
  await page.setViewportSize({ width: 1280, height: 720 });
}

test('Dòng hỏi khóa tháng ở bảng chi tiết: riêng một dòng dưới thanh công cụ, nút không bị bóp', async () => withPage(async ({ page }) => {
  await page.locator('.dt-gon').waitFor();
  await assertLockAskLayout(page);
}, withDetails));

test('Dòng hỏi khóa tháng ở bảng chuyến thường: riêng một dòng dưới thanh công cụ, nút không bị bóp', async () => withPage(async ({ page }) => {
  await viewMonth(page, KEY);
  await assertLockAskLayout(page);
}, world => { world.locks = [{ month: todayMonth, locked: false }]; }));

test('Tên gọi bảng kê chỉ đặt một chỗ để đổi được', () => {
  const code = fs.readFileSync(path.join(__dirname, 'so-khach-v7-detail-ui.js'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  assert.equal(code.match(/bảng kê/gi).length, 1);
});
