/* Trình duyệt (Playwright) cho bảng chi tiết của sổ (SO-CHI-TIET-01, specs/v7-so-chi-tiet.md). Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { todayMonth, withPage } = require('./so-khach-v7-browser-world');

const KEY = todayMonth.slice(0, 7);
const base = (id, container, extra) => ({ kind: 'legacy', id, month: KEY, container, has_detail: true, day: '03/09', bill: `MAU${id}`, ship: 'TÀU MẪU 201N', etd: '06/09', eta: '10/09',
  from: 'KHO MỘT - TỈNH A', to: 'SHEKOU', of_counted: false, ledger_vnd: '22500000', differs: false, fee_vnd: '565000', service_vnd: '6000000', truck_vnd: '14500000', of_vnd: '21000000',
  vat_vnd: '1685200', total_vnd: '22750200', ...extra });
const DETAILS = { rows: [
  base(1, 'ABCU2000011', {}),
  base(2, 'ABCU2000026', { of_counted: true, of_vnd: '12500000', total_vnd: '44400000', ledger_vnd: '44400000' }),
  base(3, 'ABCU2000032', { differs: true, ledger_vnd: '22000000', total_vnd: '22000000', sheet_total_vnd: '22750200' }),
  base(4, 'ABCU2000047', { has_detail: false, bill: '', etd: '', eta: '', fee_vnd: null, service_vnd: null, truck_vnd: null, of_vnd: null, vat_vnd: null, total_vnd: null, ledger_vnd: '0' }),
  base(5, 'ABCU2000053', { has_detail: false, fee_vnd: null, service_vnd: null, truck_vnd: null, of_vnd: null, vat_vnd: null, total_vnd: '5000000', ledger_vnd: '5000000' }),
  base(6, '', { has_detail: false, fee_vnd: null, service_vnd: null, truck_vnd: null, of_vnd: null, vat_vnd: null, total_vnd: '700000', ledger_vnd: '700000' }),
], months: { [KEY]: { fee_vnd: '1695000', service_vnd: '18000000', truck_vnd: '43500000', vat_vnd: '5055600', of_counted_vnd: '12500000', of_customer_vnd: '42000000',
  total_vnd: '94850200', no_detail: 3, differs: ['ABCU2000032'], sheet_diff_vnd: '750200', charges_vnd: '95000000', diff_vnd: '149800' } } };
const withDetails = world => {
  world.month = null;
  world.details = DETAILS;
  world.trips = [{ id: 900, month: `${KEY}-01`, container: 'ABCU2000011', carrier: 'WH', event_date: todayMonth, origin: 'KHO', destination: 'CANG', unit_price_vnd: '1000000', other_fee_vnd: null,
    amount_vnd: '1000000', status: 'confirmed', is_missing_price: false, is_fee_only: false, editable: true, info_editable: true, deleted: false }];
};

test('Sổ có bảng chi tiết: theo cột bảng kê, tô màu, một dòng mỗi container, chú thích bằng chữ', async () => withPage(async ({ page }) => {
  await page.locator('.detail-table').waitFor();
  assert.deepEqual(await page.locator('.detail-table thead th').allInnerTexts(), ['STT', 'Số container', 'Bill', 'Tên tàu', 'Ngày đóng', 'ETD', 'ETA', 'Nơi đóng hàng', 'Cảng đến',
    'Phí phát sinh', 'Phí DV hải quan', 'Cước nội địa', 'Cước tàu OF', 'VAT 8%', 'Tổng']);
  assert.equal(await page.locator('.detail-table tbody tr').count(), 6);
  assert.equal(await page.locator('.trip-list').count(), 0);
  assert.equal(await page.locator('.trip-card > .ledger-head').isVisible(), false);
  // Khách tự trả: cam, không vào Tổng; mình thu: xanh, trong Tổng.
  assert.equal(await page.locator('tr[data-detail="legacy-1"] .dt-of-customer').innerText(), '21.000.000');
  assert.equal(await page.locator('tr[data-detail="legacy-1"] .dt-total').innerText(), '22.750.200');
  assert.equal(await page.locator('tr[data-detail="legacy-2"] .dt-of-own').innerText(), '12.500.000');
  assert.match(await page.locator('.detail-legend').innerText(), /Mình thu, tính vào Tổng[\s\S]*Khách tự trả, không tính/);
  assert.match(await page.locator('.dt-customer-sum').innerText(), /Khách tự trả cước tàu: 42\.000\.000, không tính vào Tổng/);
  // Tổng chân bảng là Phát sinh của sổ; thanh chuyến đếm container, không đếm dòng Phí lẻ.
  assert.equal(await page.locator('.detail-table tfoot td').last().innerText(), '95.000.000');
  assert.match(await page.locator('.trip-toolbar h3').innerText(), /5 chuyến/);
  // Thiếu dữ liệu: chữ rõ, không hiện như 0.
  assert.equal(await page.locator('tr[data-detail="legacy-4"] .dt-missing').innerText(), 'chưa có giá');
  assert.equal(await page.locator('tr[data-detail="legacy-4"] .dt-total').innerText(), '–');
  assert.equal(await page.locator('tr[data-detail="legacy-5"] .dt-no-detail').innerText(), 'chưa có trên bảng kê');
  assert.match(await page.locator('tr[data-detail="legacy-6"]').innerText(), /Phí lẻ/);
  // Khác bảng kê chỉ báo; ô Tổng hiện số của sổ, số bảng kê ở chữ rê chuột.
  const note = await page.locator('.detail-note').innerText();
  assert.match(note, /Bảng kê khác sổ ở 1 container \(ABCU2000032\), bảng kê hơn sổ 750\.200\. Cột Tổng theo sổ\./);
  assert.match(note, /Cộng các dòng 94\.850\.200, Phát sinh của sổ 95\.000\.000: lệch 149\.800\./);
  assert.match(note, /3 chuyến chưa có trên bảng kê\./);
  assert.equal(await page.locator('tr[data-detail="legacy-3"] .dt-differs').innerText(), '22.000.000');
  assert.equal(await page.locator('tr[data-detail="legacy-3"] .dt-differs').getAttribute('title'), 'Bảng kê ghi 22.750.200');
  assert.match(await page.locator('.dt-differs-key').innerText(), /Bảng kê khác sổ, Tổng theo sổ/);
  // Vừa khung 1280: không cuộn ngang, chữ dài bị cắt có chữ rê chuột.
  await page.setViewportSize({ width: 1280, height: 720 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
  assert.equal(await page.locator('tr[data-detail="legacy-1"] .dt-text').first().getAttribute('title'), 'MAU1');
}, withDetails));

// Số giả cỡ một tháng lớn: hàng trăm triệu ở cột phí, hàng tỷ ở cột Tổng.
const BIG = { rows: [
  base(1, 'ABCU2000011', { differs: true, total_vnd: null, ledger_vnd: '0', sheet_total_vnd: '44111222' }),
  base(2, 'ABCU2000026', { from: 'KHO MỘT - TỈNH A VÀ MỘT TÊN KHO RẤT DÀI', total_vnd: '22750200', ledger_vnd: '22750200', sheet_total_vnd: '22750200' }),
], months: { [KEY]: { fee_vnd: '28111222', service_vnd: '288111222', truck_vnd: '299333444', vat_vnd: '98765432', of_counted_vnd: '511222333', of_customer_vnd: '255666777',
  total_vnd: '1999888777', no_detail: 0, differs: ['ABCU2000011'], sheet_diff_vnd: '-123456789', charges_vnd: '1999888777', diff_vnd: '0' } } };

test('Số lớn ở chân bảng không tràn cột ở 1280; sổ chưa có giá mà bảng kê có giá: Tổng trống, viền cam, chênh âm ghi "kém"', async () => withPage(async ({ page, shot }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.locator('.detail-table').waitFor();
  const measure = () => page.evaluate(() => ({
    overflowing: [...document.querySelectorAll('.detail-table tfoot td.num')].flatMap(cell => {
      const range = document.createRange();
      range.selectNodeContents(cell);
      const style = getComputedStyle(cell);
      const room = cell.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      return range.getBoundingClientRect().width > room ? [cell.innerText] : [];
    }),
    fits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    from: document.querySelector('.detail-table .c-from').getBoundingClientRect().width,
  }));
  const usual = await measure();
  // Máy thiếu Segoe UI (CI Ubuntu) dùng font rộng hơn: đo lại, đỏ thì nới bố cục.
  const wide = await page.addStyleTag({ content: 'body,body *{font-family:Verdana,"DejaVu Sans",sans-serif !important}' });
  const wider = await measure();
  await wide.evaluate(node => node.remove());
  for (const result of [usual, wider]) {
    assert.deepEqual(result.overflowing, []);
    assert.equal(result.fits, true);
    assert.ok(result.from >= 110, `cột Nơi đóng hàng còn đọc được: ${result.from}px`);
  }
  const missing = page.locator('tr[data-detail="legacy-1"] .dt-differs');
  assert.equal(await missing.innerText(), '–');
  assert.equal(await missing.getAttribute('title'), 'Sổ chưa có giá, bảng kê ghi 44.111.222');
  assert.match(await page.locator('.detail-note').innerText(), /bảng kê kém sổ 123\.456\.789/);
  await page.evaluate(() => document.fonts.ready);
  await shot('so-chi-tiet-tong-theo-so-1280');
}, world => { withDetails(world); world.details = BIG; }));

test('Nút đổi về bảng sổ để sửa, nhớ lựa chọn, focus giữ ở nút; ?loc= luôn hiện bảng sổ', async () => withPage(async ({ page }) => {
  await page.locator('.detail-table').waitFor();
  await page.locator('.detail-toggle').click();
  await page.locator('.trip-list').waitFor();
  assert.equal(await page.locator('.detail-table').count(), 0);
  assert.equal(await page.locator('.detail-toggle').innerText(), 'Xem bảng chi tiết');
  assert.equal(await page.evaluate(() => document.activeElement.className), 'detail-toggle');
  await page.reload();
  await page.locator('.trip-list').waitFor();
  assert.equal(await page.locator('.detail-toggle').innerText(), 'Xem bảng chi tiết');
  await page.locator('.detail-toggle').click();
  await page.locator('.detail-table').waitFor();
  assert.equal(await page.locator('.detail-toggle').innerText(), 'Xem bảng sổ để sửa');
  const url = new URL(page.url());
  url.searchParams.set('loc', 'thieu-gia');
  await page.goto(url.href);
  await page.locator('.trip-list').waitFor();
  assert.equal(await page.locator('.detail-toggle').count(), 0);
}, withDetails));

test('Sổ không có bảng chi tiết: giữ nguyên bảng sổ, không có nút', async () => withPage(async ({ page }) => {
  await page.locator('.trip-list').waitFor();
  assert.equal(await page.locator('.detail-toggle, .detail-table').count(), 0);
}, world => { world.month = null; world.details = { rows: [], months: {} }; }));
