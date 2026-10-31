/* Trình duyệt (Playwright) cho bàn phím trong bảng chuyến và Lịch sử viết thành câu (SO-GON-04, L5–L6 — PR 2d).
 * Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage, tripCell, legacyCell, posts } = require('./so-khach-v7-browser-world');

// Tháng 9/2026 có thứ tự dòng: sổ gốc 21, 22, rồi chuyến web 11, 13, 14 (14 đang CHỜ KIỂM: ô giá chỉ đọc).
function moreTrips(world) {
  const trip = (id, container, extra) => ({ id, month: '2026-09-01', container, carrier: `Tàu ${id}`, event_date: '2026-09-20', origin: 'Nơi E',
    destination: 'Nơi F', unit_price_vnd: '40000000', other_fee_vnd: null, amount_vnd: '40000000', status: 'confirmed', is_missing_price: false,
    is_fee_only: false, editable: true, info_editable: true, deleted: false, ...extra });
  world.trips.push(trip(13, 'DEMU0000013'), trip(14, 'DEMU0000014', { status: 'pending_review', review_reason: 'WEB_DUPLICATE' }));
}
// Ô đang có tiêu điểm: "dòng:cột:tên ô" (cột = vị trí ô trong hàng; ">THẺ" khi tiêu điểm ở phần tử trong ô), hoặc thẻ/BODY.
const focused = page => page.evaluate(() => {
  const el = document.activeElement, td = el?.closest?.('td'), row = td?.closest('tr[data-row]');
  return row ? `${row.dataset.row}:${td.cellIndex}:${td.dataset.field ?? ''}${el === td ? '' : `>${el.tagName}`}`
    : `${el?.tagName ?? 'BODY'}${el?.className ? `.${el.className.split(' ')[0]}` : ''}`;
});

test('ô chữ: Tab ghi rồi sang ô sửa kế (không về BODY); Enter ghi rồi xuống ô cùng cột; mũi tên đổi hàng khi không gõ', async () => withPage(async ({ page, world }) => {
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu đổi');
  await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="trip"][data-id="11"][data-field="carrier"]')?.textContent === 'Tàu đổi');
  assert.equal(await focused(page), 'trip-11:3:shipper');
  await page.keyboard.press('Shift+Tab');
  assert.equal(await focused(page), 'trip-11:2:carrier');

  await legacyCell(page, 21, 'carrier').click();
  await page.locator('.info-input').fill('Xe đổi');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="legacy"][data-id="21"][data-field="carrier"]')?.textContent === 'Xe đổi');
  assert.equal(await focused(page), 'legacy-22:2:carrier');
  // Enter ở ô đang đứng mở sửa; Enter nữa ghi rồi xuống hàng dưới (sang chuyến web).
  await page.keyboard.press('Enter');
  await page.locator('.info-input').fill('Xe hai');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="legacy"][data-id="22"][data-field="carrier"]')?.textContent === 'Xe hai');
  assert.equal(await focused(page), 'trip-11:2:carrier');
  // Không đổi gì: Enter chỉ xuống hàng, không gửi lệnh.
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  assert.equal(await focused(page), 'trip-13:2:carrier');
  assert.deepEqual(posts(world).map(([path]) => path), ['/api/v7/trips/info', '/api/v7/legacy/edit', '/api/v7/legacy/edit']);

  await page.keyboard.press('ArrowUp');
  assert.equal(await focused(page), 'trip-11:2:carrier');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('ArrowUp');
  assert.equal(await focused(page), 'legacy-21:2:carrier');
  await page.keyboard.press('ArrowUp');   // hàng đầu: đứng yên
  assert.equal(await focused(page), 'legacy-21:2:carrier');
  for (let step = 0; step < 5; step++) await page.keyboard.press('ArrowDown');
  assert.equal(await focused(page), 'trip-14:2:carrier');
  // Hàng cuối: Enter mở sửa, Enter nữa (không đổi) đứng lại ở chính ô đó, không rơi về BODY.
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  assert.equal(await focused(page), 'trip-14:2:carrier');
  // Ô giá của chuyến chờ kiểm chỉ đọc: vẫn đứng được, như ô Sheet.
  await page.locator('td.editable[data-trip="13"]').focus();
  await page.keyboard.press('ArrowDown');
  assert.equal(await focused(page), 'trip-14:7:');
  // Sổ tải lại (Làm mới, không dời tiêu điểm) khi đang đứng ở ô chỉ đọc: tiêu điểm về đúng ô đó trong bảng mới.
  await page.evaluate(() => { document.querySelector('tr[data-row="trip-14"]').oldRow = true; });
  await page.locator('#refresh-data').dispatchEvent('click');
  await page.waitForFunction(() => !document.querySelector('tr[data-row="trip-14"]').oldRow);
  assert.equal(await focused(page), 'trip-14:7:');
  await page.keyboard.press('ArrowUp');
  assert.equal(await focused(page), 'trip-13:7:unit_price_vnd');
  // Đang gõ thì mũi tên thuộc ô nhập; Esc bỏ sửa, tiêu điểm về ô.
  await tripCell(page, 'origin', 13).click();
  await page.keyboard.press('ArrowDown');
  assert.equal(await focused(page), 'trip-13:5:origin>INPUT');
  await page.keyboard.press('Escape');
  assert.equal(await focused(page), 'trip-13:5:origin');
  assert.equal(posts(world).length, 3);
}, moreTrips));

test('ô giá và ô cột phụ phí riêng: Tab ghi rồi sang ô kế, Enter ghi rồi xuống, không đổi thì chỉ đóng, Esc về ô', async () => withPage(async ({ page, world }) => {
  const price = id => page.locator(`td.editable[data-trip="${id}"]`);
  await price(11).click();
  await page.locator('.money-input').fill('55.000.000');
  await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.querySelector('td.editable[data-trip="11"]')?.textContent.startsWith('55.000.000'));
  assert.equal(await focused(page), 'trip-11:8:other_fee_vnd');
  assert.deepEqual(posts(world).at(-1), ['/api/v7/trips/price', { ...posts(world).at(-1)[1], trip_id: 11, unit_price_vnd: '55000000', other_fee_vnd: null }]);
  await price(13).click();
  await page.keyboard.press('Escape');
  assert.equal(await focused(page), 'trip-13:7:unit_price_vnd');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');   // không đổi: không gửi, ô nhập đóng sau khi tiêu điểm đã sang ô kế
  await page.waitForFunction(() => !document.querySelector('td.editable[data-trip="13"] input'));
  assert.equal(await focused(page), 'trip-13:8:other_fee_vnd');
  await price(11).click();
  await page.locator('.money-input').fill('56.000.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.editable[data-trip="11"]')?.textContent.startsWith('56.000.000'));
  assert.equal(await focused(page), 'trip-13:7:unit_price_vnd');
  assert.equal(posts(world).filter(([path]) => path === '/api/v7/trips/price').length, 2);

  // Cột phụ phí riêng (PHU-PHI-01): Enter ghi rồi xuống ô cùng cột hàng dưới.
  world.feeColumns = [1];
  await page.click('#refresh-data');
  const own = id => page.locator(`td.fee.own[data-fee-target="trip:${id}"][data-fee-type="1"]`);
  await own(11).waitFor();
  await own(11).click();
  await page.locator('.fee-own-input').fill('1.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '1.000');
  assert.equal(await focused(page), 'trip-13:8:');
  assert.equal(await own(13).evaluate(cell => cell === document.activeElement), true);
}, moreTrips));

test('Esc đóng mọi dòng hỏi trong bảng, không gửi lệnh, tiêu điểm về ô/nút đã mở; Esc kế tiếp mới đóng Lịch sử', async () => withPage(async ({ page, world }) => {
  // Mở bằng bàn phím (đứng ở ô/nút rồi Enter), Esc rồi xem tiêu điểm có về đúng chỗ đã mở.
  const esc = async (opener, prompt) => {
    await page.locator(opener).focus();
    await page.keyboard.press('Enter');
    await page.locator(prompt).waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator(prompt).count(), 0, prompt);
    assert.equal(await page.evaluate(selector => document.activeElement.matches(selector), opener), true, `${prompt}: ${await focused(page)}`);
  };
  const stt13 = 'td.row-delete[data-kind="trip"][data-id="13"]';
  await esc(stt13, '.delete-prompt');
  await esc('.review-open[data-trip="14"]', '.review-prompt');
  assert.equal(await page.locator('.review-open[data-trip="14"]').getAttribute('aria-expanded'), 'false');
  await tripCell(page, 'event_date', 13).click();
  await page.locator('.info-input').fill('01/10/2026');
  await page.keyboard.press('Enter');
  await page.locator('.move-ask').waitFor();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.move-ask').count(), 0);
  assert.equal(await focused(page), 'trip-13:4:event_date');
  assert.equal(await tripCell(page, 'event_date', 13).innerText(), '20/09/2026');
  await esc('td.receipt[data-pid="PH-001"]:not([data-field])', '.void-prompt');
  await esc('.add-month-adjustment[data-month="2026-09-01"]', '.month-adjustment-input');
  await esc('.month-lock[data-month="2026-09-01"]', '.lock-ask');
  assert.deepEqual(posts(world), []);

  await page.locator('.history-toggle').click();
  const panel = page.locator('#history-panel');
  await panel.waitFor();
  await esc(stt13, '.delete-prompt');
  assert.equal(await panel.isVisible(), true, 'Esc của dòng hỏi không đóng Lịch sử');
  await page.keyboard.press('Escape');
  await panel.waitFor({ state: 'hidden' });
  assert.equal(await focused(page), 'BUTTON.history-toggle');
}, world => {
  moreTrips(world);
  world.receipts.push({ id: 1, pid: 'PH-001', date: '2026-09-25', method: 'THU TIỀN', amount_vnd: '1000000', reference: null,
    voided_by_event: null, void_reason: null,
    allocations: [{ id: 1, month: '2026-09-01', kind: 'debt', amount_vnd: '1000000', superseded_by_event: null }] });
}));

test('Lịch sử: mỗi sự kiện một câu có tên ngắn người làm; lý do chỉ khi có; lọc theo loại giữ qua lần mở lại; Esc về nút', async () => withPage(async ({ page }) => {
  await page.locator('.history-toggle').click();
  const panel = page.locator('#history-panel');
  await panel.waitFor();
  const lines = () => panel.locator('.history-items > li:visible').evaluateAll(items => items.map(item => item.innerText.replace(/\s+/g, ' ').trim()));
  assert.deepEqual(await lines(), [
    '15/10/2026 10:12 · Thu · Ghi phiếu thu PH-001: 200.000.000 đ ngày 15/10/2026 · CHUYỂN KHOẢN (trừ T8 1.000.000 · T9 199.000.000)',
    '14/10/2026 09:00 · Thu · Hủy phiếu PH-000: 5.000 đ Lý do hủy: ghi trùng',
    '01/10/2026 08:00 · khoa · Khóa tháng 9/2026',
    '20/09/2026 15:30 · nhap · Sửa ô chuyến Chuyến DEMU1234567 · Hãng tàu: Tàu cũ → Tàu thử']);
  assert.doesNotMatch(await panel.innerText(), /Ghi chú\/lý do|@example/);
  assert.deepEqual(await panel.locator('.history-filter button').allInnerTexts(),
    ['Thu (2)', 'Chuyến (1)', 'Giá/phụ phí (0)', 'Khóa tháng (1)', 'Tất cả (4)']);

  await panel.locator('.history-filter button', { hasText: 'Thu' }).click();
  assert.equal((await lines()).length, 2);
  assert.equal(await panel.locator('.history-none').isVisible(), false);
  await panel.locator('.history-filter button', { hasText: 'Giá/phụ phí' }).click();
  assert.deepEqual(await lines(), []);
  assert.equal(await panel.locator('.history-none').innerText(), 'Không có thay đổi loại này.');
  assert.equal(await panel.locator('.history-filter button[aria-pressed="true"]').innerText(), 'Giá/phụ phí (0)');
  // Esc ở nút lọc đóng Lịch sử, tiêu điểm về nút Lịch sử; mở lại vẫn đang lọc.
  await page.keyboard.press('Escape');
  await panel.waitFor({ state: 'hidden' });
  assert.equal(await focused(page), 'BUTTON.history-toggle');
  await page.keyboard.press('Enter');
  await panel.waitFor();
  assert.equal(await panel.locator('.history-filter button[aria-pressed="true"]').innerText(), 'Giá/phụ phí (0)');
  await panel.locator('.history-filter button', { hasText: 'Tất cả' }).click();
  assert.equal((await lines()).length, 4);
}, world => {
  world.events.push(
    { kind: 'receipt', actor: 'thu.ke@example.test', actor_name: 'Thu', at: '2026-10-15T03:12:00Z', before: {}, after: { pid: 'PH-001', date: '2026-10-15',
      method: 'CHUYỂN KHOẢN', amount_vnd: '200000000', allocations: [{ month: '2026-08-01', kind: 'debt', amount_vnd: '1000000' },
        { month: '2026-09-01', kind: 'debt', amount_vnd: '199000000' }] } },
    { kind: 'void', actor: 'thu.ke@example.test', actor_name: 'Thu', at: '2026-10-14T02:00:00Z', before: { pid: 'PH-000', amount_vnd: '5000' },
      after: { pid: 'PH-000', void_reason: 'ghi trùng', allocations: [] } },
    { kind: 'month_lock', actor: 'khoa@example.test', at: '2026-10-01T01:00:00Z', before: { month: '2026-09-01', locked: false }, after: { month: '2026-09-01', locked: true } },
    { kind: 'trip_edit', actor: 'nhap@example.test', at: '2026-09-20T08:30:00Z', before: { trip: { id: 11, field: 'carrier', value: 'Tàu cũ' } },
      after: { trip: { id: 11, field: 'carrier', value: 'Tàu thử' } } });
}));

test('lưới bảng giá: mũi tên lên/xuống sang ô cùng cột hàng trên/dưới, giữ chữ đã gõ; hàng đầu đứng yên', async () => withPage(async ({ page }) => {
  const at = () => page.evaluate(() => `${document.activeElement?.dataset.r}:${document.activeElement?.dataset.c}`);
  await page.click('.price-table-open');
  const dialog = page.locator('.price-table-dialog');
  await dialog.locator('.price-grid-main').waitFor();
  await dialog.locator('input[data-r="0"][data-c="2"]').click();
  await page.keyboard.type('KHO A');
  await page.keyboard.press('ArrowDown');
  assert.equal(await at(), '1:2');
  await page.keyboard.press('ArrowDown');
  assert.equal(await at(), '2:2');
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('ArrowUp');
  assert.equal(await at(), '0:2');
  await page.keyboard.press('ArrowUp');
  assert.equal(await at(), '0:2');
  assert.equal(await dialog.locator('input[data-r="0"][data-c="2"]').inputValue(), 'KHO A');
  assert.equal(await dialog.locator('.price-dirty').isVisible(), true);
}));
