/* Trình duyệt (Playwright) cho bảng chuyến Sổ khách trên điện thoại (DIEN-THOAI-CHUYEN-01, specs/v7-so-khach-dien-thoai.md):
 * dưới 760px chỉ ba cột Ngày chuyến · Số container · Thành tiền, bấm hàng mở khung chi tiết, không sửa, không gửi lệnh.
 * Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, reload } = require('./so-khach-v7-browser-world');

// Tháng 9/2026 của sổ giả có đủ trạng thái: chuyến web đủ giá, sổ gốc chưa giá, sổ gốc có phụ phí, chuyến chờ kiểm,
// chuyến Sheet mới (có nút Duyệt trên máy tính) và chuyến Sheet chưa nối được vào sổ.
const allStates = world => {
  world.trips.push({ ...world.trips[0], id: 12, container: 'PEND0000001', event_date: '2026-09-18', status: 'pending_review', amount_vnd: null });
  world.sheetSync = { snapshot_sha256: 'a'.repeat(64), new_count: 1, conflict_count: 1, items: [
    { sync_state: 'NEW', source_row: 5, book_match: 'COMMODITY_UNKNOWN', event_date: '2026-09-20', container: 'NEWU1234567', carrier: 'WH', origin: 'A', destination: 'B' },
    { sync_state: 'CONFLICT', source_row: 9, sync_reason: 'OTHER_CUSTOMER', event_date: '2026-09-21', container: 'OTHU7654321', carrier: 'WH', origin: 'A', destination: 'B' },
  ] };
};
const phone = async page => {
  await page.setViewportSize({ width: 390, height: 844 });
  await reload(page);
  await page.locator('.trip-card tr.ph-row').first().waitFor();
};
const row = (page, container) => page.locator('.trip-card tr.ph-row', { has: page.locator('.ph-cont', { hasText: container }) });
const sheetText = async page => (await page.locator('.ph-sheet .ph-panel').innerText()).replace(/\s+/g, ' ');

test('điện thoại 390px: bảng chuyến ba cột, nhãn trạng thái thay số tiền, dòng cộng bằng Phát sinh', async () => withPage(async ({ page, shot }) => {
  await phone(page);
  const layout = await page.evaluate(() => {
    const shown = el => getComputedStyle(el).display !== 'none';
    const rows = [...document.querySelectorAll('.trip-card tr.ph-row')];
    return {
      side: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      heads: [...document.querySelectorAll('.trip-card .ledger-head th')].filter(shown).map(th => th.textContent),
      cells: [...new Set(rows.map(tr => [...tr.cells].filter(shown).map(td => td.className.match(/ph-\w+/)[0]).join(' ')))],
      low: rows.filter(tr => tr.getBoundingClientRect().height < 44).length,
      rows: rows.length,
    };
  });
  assert.deepEqual(layout, { side: 0, heads: ['Số container', 'Ngày chuyến', 'Thành tiền'], cells: ['ph-cont ph-date ph-amt'], low: 0, rows: 6 });
  const amount = async container => (await row(page, container).locator('.ph-amt').innerText()).trim();
  assert.equal(await amount('DEMU1234567'), '50.000.000');
  assert.equal(await amount('OLDU0000001'), 'Chưa có giá');
  assert.equal(await amount('OLDU0000002'), '93.000.000');
  assert.equal(await amount('PEND0000001'), 'chờ kiểm');
  assert.equal(await amount('NEWU1234567'), 'Chờ duyệt');
  assert.equal(await amount('OTHU7654321'), 'Sheet khác');
  assert.equal(await row(page, 'NEWU1234567').locator('.ph-cont').innerText(), 'NEWU1234567');
  assert.match(await page.locator('.trip-card tr.subtotal').innerText(), /^Cộng tháng, bằng Phát sinh\s+143\.000\.000$/);
  await shot('dien-thoai-390');
}, allStates));

test('điện thoại 390px: bấm hàng mở khung chi tiết, không mở ô sửa, không gửi lệnh; Chuyến sau, Esc', async () => withPage(async ({ page, world, shot }) => {
  await phone(page);
  await row(page, 'OLDU0000002').locator('.ph-cont').click();
  const panel = page.locator('.ph-sheet');
  await panel.waitFor();
  assert.equal(await page.locator('#ph-title').textContent(), 'OLDU0000002');
  assert.equal(await page.locator('.ph-sub').textContent(), 'Chuyến 2 · 03/09/2026');
  assert.deepEqual(await page.locator('.ph-info dt').allTextContents(), ['Hãng tàu', 'Shipper', 'Tuyến']);
  assert.deepEqual(await page.locator('.ph-info dd').allTextContents(), ['Xe 2', '–', 'Nơi C → Nơi D']);
  assert.deepEqual(await page.locator('.ph-line').evaluateAll(lines => lines.map(line => line.innerText.replace(/\s+/g, ' ').trim())),
    ['Đơn giá 90.000.000', '+ Khác 3.000.000', '= Thành tiền 93.000.000']);
  assert.equal(await page.locator('.ph-close').evaluate(el => el === document.activeElement), true);
  await shot('dien-thoai-390-chi-tiet');
  // Chuyến chưa giá: câu vì sao chưa tính vào nợ.
  await page.locator('.ph-sheet [data-ph="prev"]').click();
  assert.equal(await page.locator('#ph-title').textContent(), 'OLDU0000001');
  assert.match(await sheetText(page), /Chưa có giá nên chưa tính vào nợ\./);
  // Hàng đầu bảng: không có Chuyến trước.
  const first = await page.locator('.trip-card tr.ph-row .ph-cont').first().innerText();
  await page.keyboard.press('Escape');
  await page.locator('.trip-card tr.ph-row').first().click();
  assert.equal(await page.locator('#ph-title').textContent(), first);
  assert.equal(await page.locator('.ph-sheet [data-ph="prev"]').isDisabled(), true);
  // Chuyến Sheet mới: không có nút Duyệt trong khung, câu vì sao máy chưa duyệt.
  await page.keyboard.press('Escape');
  assert.equal(await panel.isHidden(), true);
  await row(page, 'NEWU1234567').click();
  assert.match(await sheetText(page), /Chuyến mới từ Sheet, chưa tính vào nợ cho tới khi duyệt \(Sheet chưa ghi mặt hàng\)\./);
  assert.equal(await page.locator('.ph-sheet button', { hasText: 'Duyệt' }).count(), 0);
  await page.locator('.ph-veil').click({ position: { x: 20, y: 20 } });
  assert.equal(await panel.isHidden(), true);
  assert.equal(await page.locator('#app td input:not(.fee-pick), #app .delete-prompt, #app .review-prompt').count(), 0, 'không mở ô sửa hay hỏi xóa');
  assert.deepEqual(world.requests, [], 'không gửi lệnh nào');
}, allStates));

test('điện thoại: sổ tự tải lại khi khung đang mở thì khung đọc số mới; màn rộng không có khung', async () => withPage(async ({ page, world }) => {
  await phone(page);
  await row(page, 'DEMU1234567').click();
  assert.match(await sheetText(page), /= Thành tiền 50\.000\.000/);
  world.trips[0].unit_price_vnd = '55000000';
  world.trips[0].amount_vnd = '55000000';
  world.version += 1;
  // Tự cập nhật trong trang (như mỗi 60 giây): sổ vẽ lại cả #app, khung nằm ngoài #app nên còn và đọc lại hàng cùng khóa.
  await page.evaluate(() => { document.querySelector('#updated-at').textContent = ''; document.dispatchEvent(new Event('visibilitychange')); });
  await page.waitForFunction(() => /55\.000\.000/.test(document.querySelector('.ph-sheet .ph-money')?.textContent ?? ''));
  assert.equal(await page.locator('.ph-sheet').isVisible(), true);
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1280, height: 720 });
  await reload(page);
  assert.equal(await page.locator('.trip-card .ph-tag:visible, .trip-card .ph-only:visible').count(), 0);
  await page.locator('td[data-trip="11"][data-field="unit_price_vnd"]').click();
  assert.equal(await page.locator('.ph-sheet').isHidden(), true);
  assert.equal(await page.locator('td[data-trip="11"] input.money-input').count(), 1, 'màn rộng vẫn sửa tại ô');
}));
