const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage } = require('./so-khach-v7-browser-world');
const handoff = require('./so-khach-v7-handoff-world');

test('Handoff: kích thước, vị trí, năm cột phiếu và một cột tuyến ở hai khổ desktop', async () => withPage(async ({ page, world, shot }) => {
  for (const width of [1280, 1895]) {
    await page.setViewportSize({ width, height: 848 });
    await page.reload();
    await page.locator('.month-card').waitFor();
    const geometry = await page.evaluate(() => {
      const box = selector => document.querySelector(selector).getBoundingClientRect();
      const card = box('.month-card'), trips = box('.trip-card');
      return { nav: box('.topbar').width, header: box('.book-head').height, card: card.height,
        gap: trips.top - card.bottom, toolbar: box('.trip-toolbar').height,
        row: box('.trip-list tr').height, pay: box('.pay-list tr').height,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
    });
    assert.ok(geometry.card >= 180 && geometry.card <= 210, 'khối số dư đủ chỗ theo font, không cắt chữ hoặc số');
    assert.deepEqual({ ...geometry, card: 0 }, { nav: 76, header: 52, card: 0, gap: 10, toolbar: 48, row: 35, pay: 33, overflow: 0 });
    const attachments = page.locator('.receipt-money>.image-clip');
    assert.deepEqual(await attachments.allTextContents(), ['📎', '📎']);
    for (const button of await attachments.all()) {
      assert.equal(await button.isVisible(), true);
      assert.equal(await button.evaluate(node => {
        const amount = node.closest('tr').querySelector('.receipt-sum').getBoundingClientRect();
        const box = node.getBoundingClientRect();
        return box.height >= 24 && box.left - amount.right >= 8 && Math.abs(box.top + box.height / 2 - amount.top - amount.height / 2) < 1;
      }), true, 'icon cạnh số tiền, cách 8px, cùng hàng và không che tiền');
    }
    assert.deepEqual(await page.locator('.ledger-head th').allTextContents(), ['STT', 'Số container', 'Hãng tàu', 'Shipper', 'Ngày chuyến', 'Tuyến', 'Đơn giá', 'Nâng hạ', 'Khác', 'Thành tiền']);
    assert.equal(await page.locator('.pay-list tr').first().locator('td').count(), 5);
    assert.equal(await page.locator('.trip-list .route-cell').count(), 8);
    assert.equal(await page.locator('.trip-tools button').count(), 3);
    assert.equal(await page.locator('.month-missing').innerText(), 'ⓘ 2 chưa giá');
    assert.equal(await page.locator('#demo-banner').isVisible(), true);
    assert.equal(await page.locator('.history-toggle').isVisible(), false);
    assert.equal(await page.locator('.month-chip.on .chip-name').innerText(), 'Tháng 11/2026');
    assert.equal(await page.locator('.subtotal .unit-total').innerText(), '57.000.000');
    // Thành tiền ở dòng cộng là phát sinh tháng của GET (months[].charges_vnd), bằng tổng Thành tiền các dòng có giá.
    const rows = await page.locator('.trip-list td.trip-amount').allInnerTexts();
    const sum = rows.map(text => text.replace(/\D/g, '')).filter(Boolean).reduce((total, digits) => total + BigInt(digits), 0n);
    assert.deepEqual([await page.locator('.subtotal .amount-total').innerText(), sum], ['58.750.000', 58750000n]);
    assert.equal(await page.locator('.subtotal').innerText().then(text => text.includes('Cộng cột')), false);
    const colors = await page.locator('.ledger-head th:is(.unit-h,.fee-h,.amount-h)').evaluateAll(nodes =>
      nodes.map(node => getComputedStyle(node).backgroundColor));
    assert.equal(new Set(colors).size, 3);
    const padding = await page.locator('.ledger-head th.num,.trip-list td.num,.subtotal td.num').evaluateAll(cells =>
      cells.every(cell => getComputedStyle(cell).paddingLeft === '10px' && getComputedStyle(cell).paddingRight === '10px'));
    assert.equal(padding, true, 'tiêu đề, ô tiền và tổng có cùng khoảng đệm hai bên');
    const warningColor = await page.locator('.trip-list td.unit-price:not(.missing)').first().evaluate(cell => {
      cell.classList.add('price-differs');
      const color = getComputedStyle(cell).backgroundColor;
      cell.classList.remove('price-differs');
      return color;
    });
    assert.equal(warningColor, 'rgb(255, 243, 209)');
    await shot(`handoff-${width}`);
  }
  assert.deepEqual(world.requests, [], 'xem và đổi cỡ không ghi tiền');
}, handoff));

test('Tuyến: hai đầu sửa riêng, Enter lưu rồi xuống đúng đầu tuyến hàng kế', async () => withPage(async ({ page, world }) => {
  const origin = id => page.locator(`.route-cell .info-edit[data-id="${id}"][data-field="origin"]`);
  await origin(11).click();
  await page.locator('.info-input').fill('Kho mới');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.route-cell [data-id="11"][data-field="origin"]')?.textContent === 'Kho mới');
  assert.equal(world.requests.at(-1).body.field, 'origin');
  assert.equal(await origin(12).evaluate(node => node === document.activeElement), true);
  await page.keyboard.press('ArrowUp');
  assert.equal(await origin(11).evaluate(node => node === document.activeElement), true);
  await page.locator('.route-cell [data-id="11"][data-field="destination"]').click();
  await page.locator('.info-input').fill('Cảng mới');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('.route-cell [data-id="11"][data-field="destination"]')?.textContent === 'Cảng mới');
  assert.equal(world.requests.at(-1).body.field, 'destination');
  assert.equal(world.requests.length, 2);
}, handoff));

test('Thiếu giá: nền cả ô, nhập ngay trong ô với một viền focus; Esc giữ NULL', async () => withPage(async ({ page, world, shot }) => {
  const cell = page.locator('.trip-list td.missing').first();
  const before = await cell.evaluate(node => ({ background: getComputedStyle(node).backgroundColor, image: getComputedStyle(node).backgroundImage }));
  assert.deepEqual(before, { background: 'rgb(253, 243, 225)', image: 'none' });
  await cell.click();
  const input = cell.locator('input');
  assert.equal(await input.inputValue(), '');
  assert.deepEqual(await input.evaluate(node => {
    const style = getComputedStyle(node), parent = getComputedStyle(node.parentElement);
    return { background: style.backgroundColor, border: style.borderTopWidth, outline: style.outlineWidth, cellOutline: parent.outlineWidth, cellBackground: parent.backgroundColor };
  }), { background: 'rgba(0, 0, 0, 0)', border: '0px', outline: '0px', cellOutline: '2px', cellBackground: before.background });
  await shot('money-edit-missing');
  await input.fill('9.000.000');
  await page.keyboard.press('Escape');
  assert.equal(await cell.innerText(), 'chưa có giá');
  const fee = page.locator('td.fee.own[data-fee-target="trip:15"]').first();
  await fee.click();
  const feeInput = fee.locator('input');
  assert.deepEqual(await feeInput.evaluate(node => {
    const style = getComputedStyle(node), parent = getComputedStyle(node.parentElement);
    return { background: style.backgroundColor, border: style.borderTopWidth, outline: style.outlineWidth, cellOutline: parent.outlineWidth };
  }), { background: 'rgba(0, 0, 0, 0)', border: '0px', outline: '0px', cellOutline: '2px' });
  await shot('money-edit-fee');
  await page.keyboard.press('Escape');
  assert.deepEqual(world.requests, []);
}, handoff));

test('Ưu tiên: số API cạnh phiếu thu, trên cột chuyến; mỗi số tháng một chỗ; không ghi tiền khi mở sổ', async () => withPage(async ({ page, world, shot }) => {
  await page.setViewportSize({ width: 1280, height: 560 });
  const geometry = await page.evaluate(() => {
    const box = selector => document.querySelector(selector).getBoundingClientRect();
    const stats = box('.month-stats'), pays = box('.pay-block'), columns = box('.ledger-head');
    return { sideBySide: stats.right <= pays.left && pays.top < stats.bottom,
      below: columns.top >= Math.max(stats.bottom, pays.bottom), overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
  });
  assert.deepEqual(geometry, { sideBySide: true, below: true, overflow: 0 });
  assert.deepEqual(await page.locator('.month-stats b').allTextContents(), ['412.600.000', '58.750.000', '150.000.000', '321.350.000 đ']);
  assert.equal(await page.locator('.month-chip .chip-end').count(), 0);
  assert.equal(await page.locator('.subtotal').innerText().then(text => text.includes('58.750.000')), true);
  assert.equal(await page.locator('.entry-open').count(), 1);
  assert.equal(world.requests.length, 0);
  await shot('uu-tien-1280');
}, world => {
  world.monthValues = { '2026-09-01': { prior_months_vnd: '412600000', charges_vnd: '58750000', received_vnd: '150000000', end_of_month_vnd: '321350000' } };
  world.receipts = [{ id: 1, pid: 'PH-001', date: '2026-09-15', method: 'THU TIỀN', amount_vnd: '150000000', reference: 'Chứng từ mẫu',
    voided_by_event: null, allocations: [{ month: '2026-09-01', amount_vnd: '150000000', superseded_by_event: null }] }];
}));

test('Ưu tiên: giữ NULL và số âm từ API; mở menu và đổi khách bằng bàn phím', async () => withPage(async ({ page, world }) => {
  assert.deepEqual(await page.locator('.month-stats b').allTextContents(), ['–', '–', '–', '-12.345 đ']);
  await page.locator('.nav-toggle').first().click();
  assert.equal(await page.locator('.nav-toggle').first().getAttribute('aria-expanded'), 'true');
  await page.locator('.customer-switch').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#customer-search').isVisible(), true);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#customer-search').isVisible(), false);
  assert.equal(await page.locator('.customer-switch').evaluate(node => node === document.activeElement), true);
  assert.equal(world.requests.length, 0);
  await page.goto(new URL('/so-khach-v7-live.html', page.url()).href);
  await page.locator('.nav-toggle').first().click();
  assert.equal(await page.locator('.nav-toggle').first().getAttribute('aria-expanded'), 'true', 'menu vẫn dùng được trước khi chọn khách');
}, world => { world.monthValues = { '2026-09-01': { prior_months_vnd: null, charges_vnd: null, received_vnd: null, end_of_month_vnd: '-12345' } }; }));

test('Ưu tiên: 1265px có ba cột phí; màn hẹp chỉ cuộn ngang trong vùng sổ', async () => withPage(async ({ page, shot }) => {
  for (const width of [1265, 700, 390]) {
    await page.setViewportSize({ width, height: 560 });
    await page.waitForFunction(() => document.documentElement.scrollWidth === document.documentElement.clientWidth);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, `${width}px`);
    assert.equal(await page.locator('.ledger-head .fee-h').count(), 4);
  }
  await shot('uu-tien-390');
}, world => { world.feeColumns = [1, 2, 3]; }));
