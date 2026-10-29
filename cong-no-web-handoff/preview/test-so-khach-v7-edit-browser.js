/* Trình duyệt (Playwright) cho sửa/xóa tại ô (NHAP-SHEET-01) trên sổ khách V7. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { clock, todayMonth, withPage, tripCell, legacyCell, posts } = require('./so-khach-v7-browser-world');

test('Danh sách phiếu thu (cả hàng nhập) dính ngay dưới dòng tháng khi cuộn; không chung hàng với chuyến', async () => withPage(async ({ page }) => {
  const pinned = await page.locator('.receipt-amount').first().evaluate(input => {
    const stick = input.closest('.pay-stick'), head = input.closest('section').querySelector('tr.month th');
    return { sticky: getComputedStyle(stick).position, top: Number.parseInt(stick.style.top, 10), below: Number.parseInt(getComputedStyle(head).top, 10) + head.offsetHeight,
      inTrips: Boolean(input.closest('.trip-list')) };
  });
  assert.equal(pinned.sticky, 'sticky');
  assert.equal(pinned.top, pinned.below);
  assert.equal(pinned.inTrips, false);
  assert.equal(await page.locator('.trip-list td.pay').count(), 0);
}));

test('Sổ khách làm mới thủ công nhưng giữ dữ liệu đang gõ',async () => withPage(async ({ page, world }) => {
  const amount = page.locator('.receipt-amount').first();
  await amount.fill('123');
  const before = world.reads;
  await page.locator('#refresh-data').click();
  assert.equal(world.reads, before);
  assert.equal(await amount.inputValue(), '123');
  await amount.fill('');
  await page.locator('#refresh-data').click();
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Cập nhật'));
  assert.equal(world.reads, before + 1);
}));



test('tháng khóa: cột chuyến chỉ đọc; phiếu thu vẫn nhập được', async () => withPage(async ({ page, world }) => {
  const sept = page.locator('#thang-2026-09');
  assert.equal(await sept.locator('td.info-edit,td.row-delete,td.editable,.draft-input').count(), 0);
  assert.equal(await sept.locator('.add-month-adjustment').isDisabled(), true);
  assert.equal(await sept.locator('.receipt-amount').count(), 1);
  assert.equal(world.requests.length, 0);
}, world => { world.locks = [{ month: '2026-09-01', locked: true }]; world.trips[0].editable = false; world.trips[0].info_editable = false; }));

test('chuyến web tháng mở: sửa ô bằng Enter, Esc trả lại, Tab lưu; ghi Lịch sử trước → sau', async () => withPage(async ({ page, world, shot }) => {
  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu đổi');
  await page.keyboard.press('Escape');
  assert.equal(await tripCell(page, 'carrier').innerText(), 'Tàu thử');
  assert.equal(world.requests.length, 0);

  await tripCell(page, 'carrier').click();
  await page.locator('.info-input').fill('Tàu đổi');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="trip"][data-field="carrier"]')?.textContent === 'Tàu đổi');
  const sent = world.requests.at(-1);
  assert.equal(sent.path, '/api/v7/trips/info');
  assert.deepEqual({ ...sent.body, idempotency_key: 'k' }, { customer_id: 1, expected_version: 1, idempotency_key: 'k', trip_id: 11, field: 'carrier', value: 'Tàu đổi' });

  await tripCell(page, 'destination').click();
  await page.locator('.info-input').fill('Nơi mới');
  await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="trip"][data-field="destination"]')?.textContent === 'Nơi mới');
  assert.equal(world.requests.length, 2);

  // Bấm vào rồi rời ô không đổi gì: không gửi lệnh.
  await tripCell(page, 'origin').click();
  await page.locator('.book-head .head-item.total').click();
  assert.equal(world.requests.length, 2);

  await page.locator('.history-toggle').click();
  assert.match(await page.locator('#history-panel').innerText(), /Sửa ô chuyến[\s\S]*Chuyến DEMU1234567 · Hãng tàu: Tàu thử → Tàu đổi/);
  await shot('sua-o-chuyen-web');
}));

test('đổi ngày sang tháng khác: hỏi lại trước khi chuyển; Chuyển → dòng vàng ở tháng mới, dòng mờ Hoàn tác ở tháng cũ', async () => withPage(async ({ page, world, shot }) => {
  await tripCell(page, 'event_date').click();
  await page.locator('.info-input').fill('31/02/2026');
  await page.keyboard.press('Enter');
  assert.match(await tripCell(page, 'event_date').locator('.cell-error').innerText(), /dd\/mm\/yyyy/);
  assert.equal(world.requests.length, 0);

  // Ngày thuộc tháng khác: chưa gửi, hỏi lại ngay dưới dòng; Giữ ngày cũ trả lại ô.
  await page.locator('.info-input').fill('5/8/2026');
  await page.keyboard.press('Enter');
  const ask = page.locator('.move-ask');
  assert.match(await ask.innerText(), /Ngày 05\/08\/2026 thuộc tháng 8\/2026\. Chuyển chuyến DEMU1234567 sang tháng 8\/2026\?/);
  assert.equal(world.requests.length, 0);
  await ask.locator('.move-no').click();
  assert.equal(await page.locator('.move-ask').count(), 0);
  assert.equal(await tripCell(page, 'event_date').innerText(), '15/09/2026');
  assert.equal(world.requests.length, 0);

  await tripCell(page, 'event_date').click();
  await page.locator('.info-input').fill('5/8/2026');
  await page.keyboard.press('Enter');
  await page.locator('.move-ask .move-yes').click();
  await page.locator('#thang-2026-08 tr.moved').waitFor();
  assert.equal(world.requests.at(-1).body.value, '2026-08-05');
  assert.equal(await page.locator('#thang-2026-08 td.info-edit[data-field="event_date"]').innerText(), '05/08/2026');
  assert.match(await page.locator('#thang-2026-08 tr.moved + tr.moved-note .moved-tag').innerText(), /Vừa chuyển từ T9/);
  assert.equal(await page.locator('#thang-2026-09 td.info-edit[data-kind="trip"]').count(), 0);
  assert.match(await page.locator('#thang-2026-09 .ghost').innerText(), /DEMU1234567 \(ngày cũ 15\/09\/2026\) đã chuyển sang tháng 8\/2026/);
  assert.equal(await page.locator('.live-notice').isVisible(), false);
  await shot('chuyen-thang');

  // Hoàn tác: gửi lại ngày cũ, dòng về tháng 9, hết dòng mờ và màu vàng.
  await page.locator('#thang-2026-09 .ghost-undo').click();
  await page.locator('#thang-2026-09 td.info-edit[data-kind="trip"][data-field="event_date"]').waitFor();
  assert.equal(world.requests.at(-1).body.value, '2026-09-15');
  assert.equal(await page.locator('.ghost, tr.moved').count(), 0);
}, world => { world.locks.push({ month: '2026-08-01', locked: false }); }));

test('lỗi server hiện tại ô và giữ ô nhập', async () => withPage(async ({ page, world }) => {
  world.failNext = { error: 'INVALID_TRIP_INPUT', message: 'Thiếu thông tin chuyến.' };
  await tripCell(page, 'container').click();
  await page.locator('.info-input').fill('');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="trip"][data-field="container"] .cell-error')?.textContent === 'Thiếu thông tin chuyến.');
  assert.equal(await page.locator('.info-input').count(), 1);
}));

test('dòng sổ gốc: điền giá dòng thiếu giá, sửa giá; dòng điều chỉnh sổ gốc cộng phần chênh của tháng', async () => withPage(async ({ page, world, shot }) => {
  // 23/10/2026: không còn chú thích "Từ sổ gốc" và dòng chênh; dòng cũ trông và sửa như chuyến web.
  assert.equal(await page.locator('.legacy-caption, .source-total').count(), 0);
  const cells = page.locator('[data-row="legacy-21"] > td');
  assert.equal(await cells.count(), 10);   // SO-GON-02: hàng chuyến chỉ còn 10 ô chuyến, phiếu thu ở danh sách riêng
  assert.equal(await cells.nth(3).innerText(), 'Chủ hàng thử');
  assert.equal(await cells.nth(4).innerText(), '02/09/2026');
  const price = legacyCell(page, 21, 'unit_price_vnd');
  assert.equal(await price.innerText(), 'chưa có giá');
  assert.match(await price.getAttribute('class'), /missing/);
  await price.click();
  assert.equal(await page.locator('.info-input').inputValue(), '');
  await page.locator('.info-input').fill('70.000.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="legacy"][data-id="21"][data-field="unit_price_vnd"]')?.textContent === '70.000.000');
  assert.deepEqual(posts(world).at(-1), ['/api/v7/legacy/edit', { customer_id: 1, expected_version: 1, idempotency_key: world.requests.at(-1).body.idempotency_key,
    legacy_row_id: 21, field: 'unit_price_vnd', value: '70000000' }]);
  assert.equal(await legacyCell(page, 21, 'unit_price_vnd').innerText(), '70.000.000');

  await legacyCell(page, 22, 'unit_price_vnd').click();
  assert.equal(await page.locator('.info-input').inputValue(), '90.000.000');
  await page.locator('.info-input').fill('85.000.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.info-edit[data-kind="legacy"][data-id="22"][data-field="unit_price_vnd"]')?.textContent === '85.000.000');
  assert.equal(await page.locator('.legacy-adjustment').count(), 0);

  await page.locator('.history-toggle').click();
  assert.match(await page.locator('#history-panel').innerText(), /Sửa dòng sổ gốc[\s\S]*Dòng sổ gốc OLDU0000002 · Đơn giá: 90\.000\.000 → 85\.000\.000 · Số tính: 93\.000\.000 → 88\.000\.000/);
  await shot('sua-dong-so-goc');
}));

test('bấm STT để xóa hẳn: hỏi xác nhận có ngày và số tiền; Thôi giữ nguyên; Xóa hẳn gửi một lệnh', async () => withPage(async ({ page, world, shot }) => {
  const stt = page.locator('td.row-delete[data-kind="trip"][data-id="11"]');
  await stt.click();
  const prompt = page.locator('.delete-prompt');
  assert.match(await prompt.innerText(), /Xóa hẳn chuyến DEMU1234567 \(15\/09\/2026, thành tiền 50\.000\.000\)\?/);
  await shot('xoa-chuyen-xac-nhan');
  await prompt.locator('.cancel-delete').click();
  assert.equal(await page.locator('.delete-prompt').count(), 0);
  assert.equal(world.requests.length, 0);

  await stt.click();
  await page.locator('.confirm-delete').click();
  await page.waitForFunction(() => !document.querySelector('td.row-delete[data-kind="trip"]'));
  assert.deepEqual(posts(world).map(([url, body]) => [url, body.trip_id]), [['/api/v7/trips/delete', 11]]);

  await page.locator('td.row-delete[data-kind="legacy"][data-id="22"]').click();
  assert.match(await page.locator('.delete-prompt').innerText(), /Xóa hẳn dòng sổ gốc OLDU0000002 \(03\/09\/2026, đang tính 93\.000\.000\)\? Số dư đầu không đổi/);
  await page.locator('.confirm-delete').click();
  await page.waitForFunction(() => !document.querySelector('td.row-delete[data-id="22"]'));
  assert.equal(world.requests.at(-1).path, '/api/v7/legacy/delete');
  assert.equal(await page.locator('.legacy-adjustment').count(), 0);
}));

test('XOA-THU-GOC-01: tháng mở bấm số tiền khoản thu sổ gốc để xóa hẳn; tháng khóa không có nút', async () => withPage(async ({ page, world }) => {
  assert.equal(await page.locator('td.row-delete[data-kind="legacy"][data-id="25"]').count(), 0);
  const amount = page.locator('td.row-delete[data-kind="legacy"][data-id="24"]');
  assert.equal(await amount.innerText(), '1.234.567');
  await amount.click();
  assert.match(await page.locator('.delete-prompt').innerText(), /Xóa hẳn khoản thu sổ gốc 1\.234\.567 \(TTNU0000009\)\? Nợ tăng lại 1\.234\.567/);
  await page.locator('.confirm-delete').click();
  await page.waitForFunction(() => !document.querySelector('td.row-delete[data-id="24"]'));
  assert.deepEqual(posts(world).map(([url, body]) => [url, body.legacy_row_id]), [['/api/v7/legacy/delete', 24]]);
}, world => {
  world.locks = [{ month: '2026-09-01', locked: true }];
  world.legacy.push({ id: 24, month: todayMonth, kind: 'receipt', source_total_vnd: '1234567', editable: false,
    current: { month: todayMonth, deleted: false, counted_vnd: '1234567' }, display: { row: 9, container: 'TTNU0000009', raw_date: '', note: '' } },
  { id: 25, month: '2026-09-01', kind: 'receipt', source_total_vnd: '1000000', editable: false,
    current: { month: '2026-09-01', deleted: false, counted_vnd: '1000000' }, display: { row: 8, raw_date: '', note: '' } });
}));

test('bảng nhập kiểu Sheet: dán hàng từ tab khách vào hàng trống, ô lỗi chặn Lưu, Lưu gửi một lệnh dán lô', async () => withPage(async ({ page, world, shot }) => {
  assert.equal(await page.locator('.paste-input').count(), 0);
  const blank = page.locator(`#thang-${todayMonth.slice(0, 7)} .draft-input[data-draft="0"][data-field="carrier"]`);
  await blank.click();
  const day = `${clock.slice(8)}/${clock.slice(5, 7)}/${clock.slice(0, 4)}`;
  const rows = [['1', 'NEWU0000001', 'Tàu mới', day, 'Nơi A', 'Nơi B', '1,000,000', '', '', '90,000,000', '91,000,000', day, 'ck', '5,000,000'],
    ['2', 'NEWU0000002', 'Tàu mới', day, 'Nơi A', '', '', '', '', '', '0']].map(row => row.join('\t')).join('\n');
  await page.evaluate(text => {
    const data = new DataTransfer();
    data.setData('text/plain', text);
    document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  }, rows);
  await page.locator('.draft-row.draft').nth(1).waitFor();
  assert.equal(await page.locator('.draft-input[data-draft="0"][data-field="container"]').inputValue(), 'NEWU0000001');
  assert.equal(await page.locator('.draft-input[data-draft="0"][data-field="fee"]').inputValue(), '1.000.000');
  assert.match(await page.locator('.draft-note').innerText(), /Phần tiền khách trả trong vùng dán đã bỏ qua/);
  // Hàng 2 thiếu nơi đến: ô đỏ, nút Lưu tắt; thiếu giá chỉ tô cam, không chặn.
  assert.match(await page.locator('.draft-input[data-draft="1"][data-field="to"]').locator('..').getAttribute('class'), /bad/);
  assert.equal(await page.locator('.draft-save').isDisabled(), true);
  await page.locator('.draft-input[data-draft="1"][data-field="to"]').fill('Nơi C');
  await page.locator('.draft-input[data-draft="1"][data-field="from"]').click();
  await page.waitForFunction(() => !document.querySelector('.draft-save').disabled);
  assert.equal(world.requests.length, 0);
  await shot('bang-nhap-nhap');
  await page.locator('.draft-save').click();
  await page.waitForFunction(() => /Đã lưu 2 chuyến/.test(document.querySelector('.draft-note')?.textContent ?? ''));
  const sent = world.requests.at(-1);
  assert.equal(sent.path, '/api/v7/trips/paste');
  assert.deepEqual(sent.body.trips, [
    { container: 'NEWU0000001', carrier: 'Tàu mới', date: day, from: 'Nơi A', to: 'Nơi B', unitPriceVnd: '90000000', otherFeeVnd: '1000000', note: '', src: '' },
    { container: 'NEWU0000002', carrier: 'Tàu mới', date: day, from: 'Nơi A', to: 'Nơi C', unitPriceVnd: null, otherFeeVnd: null, note: '', src: '' }]);
  assert.equal(await page.locator('.draft-row.draft').count(), 0);
  assert.equal(await page.locator('td.info-edit[data-kind="trip"][data-field="container"]').filter({ hasText: 'NEWU0000002' }).count(), 1);
}, world => { world.locks = [{ month: '2026-09-01', locked: true }]; }));

test('tháng cũ đã mở khóa có hàng nhập phiếu và bảng nhập chuyến riêng; nháp không lẫn tháng, ô thu gõ dở không mất', async () => withPage(async ({ page, world, shot }) => {
  const sept = page.locator('#thang-2026-09');
  const current = page.locator(`#thang-${todayMonth.slice(0, 7)}`);
  await sept.locator('.draft-input[data-field="container"]').first().waitFor();
  for (const selector of ['.receipt-date:not(.saved-receipt-input)', '.receipt-method', '.receipt-amount', '.receipt-reference']) assert.equal(await sept.locator(selector).count(), 1);
  // Gõ nháp ở tháng 9 không làm hiện nháp ở tháng hiện tại.
  const entry = sept.locator('.draft-row').first();
  await entry.locator('.draft-input[data-field="container"]').fill('NEWU7654321');
  await sept.locator('.receipt-amount').fill('1.000.000');
  await entry.locator('.draft-input[data-field="carrier"]').click();
  await page.waitForFunction(() => document.querySelector('#thang-2026-09 .draft-bar strong')?.textContent === '1 chuyến nháp');
  assert.equal(await current.locator('.draft-bar strong').innerText(), '0 chuyến nháp');
  // Bảng nháp vẽ lại không làm mất ô thu đang gõ.
  assert.equal(await sept.locator('.receipt-amount').inputValue(), '1.000.000');
  await shot('nhap-thang-cu-mo-khoa');
  assert.equal(world.requests.length, 0);
}, world => { world.locks = [{ month: '2026-09-01', locked: false }]; }));

test('bàn phím: Enter trên ô mở sửa; 1280×720 không cuộn ngang', async () => withPage(async ({ page }) => {
  await tripCell(page, 'origin').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('.info-input').count(), 1);
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
}));

// SO-GON-02 (29/10/2026): phiếu thu là danh sách riêng bên phải: khoản thu Sheet trước, phiếu web, rồi hàng nhập.
const webReceipt = (pid, month, date, amount, reference = null) => ({ id: pid, pid, reference, date, method: 'THU TIỀN', amount_vnd: amount, void_reason: null,
  offset_pair_id: null, counterparty_customer_id: null, counterparty_name: null, voided_on: null, voided_by_event: null,
  allocations: [{ month, amount_vnd: amount, kind: 'debt', superseded_by_event: null }] });
// Mỗi hàng của danh sách phiếu thu trong tháng → [ngày trả, hình thức, số tiền, có phải hàng nhập].
const payRows = (page, key) => page.evaluate(id => [...document.querySelectorAll(`#thang-${id} .pay-list tr.pay-row`)]
  .map(tr => { const pay = [...tr.querySelectorAll('td.pay')]; const entry = tr.querySelector('.receipt-date');
    return { date: pay[0]?.textContent.trim() ?? '', method: pay[1]?.textContent.trim() ?? '', amount: pay[2]?.firstChild?.textContent?.trim?.() ?? '', entry: Boolean(entry) }; }), key);

test('danh sách phiếu thu: khoản thu Sheet trước, phiếu web sau, ô nhập cuối; ngày Sheet dd/mm/yyyy', async () => withPage(async ({ page, world, shot }) => {
  world.legacy.push({ id: 23, month: '2026-09-01', kind: 'receipt', source_total_vnd: '1000000', editable: false, current: { month: '2026-09-01', deleted: false },
    display: { row: 5, raw_date: '46032.0', note: '2026-01-10 00:00:00' } });
  world.receipts.push(webReceipt('PH-001', '2026-09-01', '2026-09-11', '2000000', 'REF-A'), webReceipt('PH-002', '2026-09-01', '2026-09-12', '3000000'),
    webReceipt('PH-003', '2026-09-01', '2026-09-13', '4000000'), webReceipt('PH-004', todayMonth, clock, '5000000'));
  await page.reload();
  await page.waitForSelector('#thang-2026-09');
  // Tháng 9: khoản thu Sheet, ba phiếu web, rồi hàng nhập.
  const sept = await payRows(page, '2026-09');
  assert.equal(sept.length, 5);
  assert.equal(sept[0].date, '10/01/2026');   // 46032 = 10/01/2026, ghi chú lặp cùng ngày bị bỏ
  assert.equal(sept[0].method, '');
  assert.deepEqual(sept.slice(1, 4).map(row => row.date), ['11/09/2026', '12/09/2026', '13/09/2026']);
  assert.equal(sept[4].entry, true);
  assert.equal(await page.locator('#thang-2026-09 [data-pid="PH-001"][data-field="date"]').count(), 1);
  // Tháng hiện tại: một phiếu ở hàng 1, ô nhập ở hàng 2 (cuối), tham chiếu nằm trong ô số tiền.
  const now = await payRows(page, todayMonth.slice(0, 7));
  assert.equal(now.length, 2);
  assert.equal(now[0].entry, false);
  assert.equal(now[1].entry, true);
  assert.equal(await page.locator(`#thang-${todayMonth.slice(0, 7)} .receipt-amount`).locator('xpath=ancestor::td').locator('.receipt-reference').count(), 1);
  // Tham chiếu là chữ nhỏ trong ô Số tiền trả, bấm để sửa; không còn hàng Tham chiếu riêng.
  assert.equal(await page.locator('tr.reference-row').count(), 0);
  const reference = page.locator('.receipt-ref[data-pid="PH-001"][data-field="reference"]');
  assert.equal(await reference.innerText(), 'Tham chiếu: REF-A');
  await reference.click();
  assert.equal(await reference.locator('input').inputValue(), 'REF-A');
  await reference.locator('input').press('Escape');
  assert.equal(await reference.innerText(), 'Tham chiếu: REF-A');
  // Bấm vào ô số tiền (không phải chữ tham chiếu) vẫn mở hỏi hủy phiếu.
  await page.locator('td.receipt[data-pid="PH-002"]:not([data-field])').click({ position: { x: 4, y: 4 } });
  assert.equal(await page.locator('.void-prompt[data-pid="PH-002"]').count(), 1);
  await page.locator('.cancel-void').click();
  await shot('phieu-thu-hang-ke-tiep');
  // Tháng chưa có phiếu: ô nhập ở hàng 1.
  world.receipts.length = 0; world.legacy.pop();
  await page.reload();
  await page.waitForSelector('#thang-2026-09');
  assert.equal((await payRows(page, '2026-09')).some(row => row.date !== ''), false);
  const empty = await payRows(page, todayMonth.slice(0, 7));
  assert.equal(empty.length, 1);
  assert.equal(empty[0].entry, true);
}));

test('mở từ Việc cần làm (?loc=thieu-gia): tô chuyến thiếu giá, nhảy tới dòng, bỏ đánh dấu; không ẩn dòng nào', async () => withPage(async ({ page }) => {
  await page.locator('.loc-bar').waitFor();
  assert.match(await page.locator('.loc-bar').innerText(), /1 chuyến thiếu đơn giá/);
  assert.equal(await page.locator('tr.loc-hit').count(), 1);
  assert.equal(await page.locator('tr.loc-hit').getAttribute('data-row'), 'trip-12');
  assert.equal(await page.locator('tr[data-row="trip-11"]').count(), 1);
  await page.locator('.loc-next').click();
  await page.locator('.loc-clear').click();
  assert.equal(await page.locator('tr.loc-hit').count(), 0);
  assert.equal(await page.locator('.loc-bar').count(), 0);
  assert.doesNotMatch(await page.evaluate(() => location.search), /loc=/);
}, world => {
  world.query = '&loc=thieu-gia';
  world.trips.push({ ...world.trips[0], id: 12, container: 'DEMU7654321', unit_price_vnd: null, amount_vnd: null, is_missing_price: true });
}));
