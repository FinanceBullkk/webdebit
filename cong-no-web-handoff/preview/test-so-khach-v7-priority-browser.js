const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, reload, viewMonth } = require('./so-khach-v7-browser-world');
const handoff = require('./so-khach-v7-handoff-world');

test('Handoff: kích thước, vị trí, năm cột phiếu và một cột tuyến ở hai khổ desktop', async () => withPage(async ({ page, world, shot }) => {
  for (const width of [1280, 1895]) {
    await page.setViewportSize({ width, height: 848 });
    await reload(page);
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

// Đo 12/11/2026 trên hao ở 390px: khối tổng tháng xếp dọc nhưng flex-basis 420px thành chiều cao, Còn nợ cuối tháng cách
// ba dòng trên ~250px; dải menu 76px ăn 1/5 bề ngang. Điện thoại: khối cao theo nội dung, menu chỉ còn nút ☰ ở đầu sổ.
test('Ưu tiên: điện thoại 390px, khối tổng tháng không có khoảng trống, menu thu về nút ☰', async () => withPage(async ({ page }) => {
  for (const width of [390, 900]) {
    await page.setViewportSize({ width, height: 844 });
    const gap = await page.evaluate(() => {
      const stats = document.querySelector('.month-stats').getBoundingClientRect(), end = document.querySelector('.month-stats .month-end').getBoundingClientRect();
      return { height: stats.height, below: stats.bottom - end.bottom };
    });
    assert.ok(gap.height < 260 && gap.below < 40, `${width}px ${JSON.stringify(gap)}`);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  const geo = await page.evaluate(() => {
    const r = el => document.querySelector(el).getBoundingClientRect();
    return { rail: r('.topbar').width, app: r('#app').left, who: r('.page-who').left, toggle: r('.topbar>.nav-toggle').right,
      navShown: getComputedStyle(document.querySelector('.topbar>nav')).display !== 'none' };
  });
  assert.ok(geo.rail <= 60 && geo.app === 0 && geo.who >= geo.toggle && !geo.navShown, JSON.stringify(geo));
  await page.locator('.nav-toggle').first().click();
  assert.equal(await page.locator('.topbar>nav a').evaluateAll(links => links.filter(a => a.getBoundingClientRect().width > 0).length), 6);
}));

// Dữ liệu giả cho danh sách phiếu: ô ngày Sheet lẫn chữ, phiếu chia ba tháng, phiếu máy đặt ngày có mã kỹ thuật.
const HASH_REF = 'Sheet #' + '5bd3cb'.repeat(10) + ': da tt · ngày theo cuối tháng khối Sheet';
function payWorld(world) {
  const debt = (month, amount_vnd) => ({ month, amount_vnd, kind: 'debt', superseded_by_event: null });
  const sheetPay = (id, raw_date, amount) => ({ id, month: '2026-09-01', kind: 'receipt', source_total_vnd: amount, editable: false,
    display: { row: id, raw_date, note: raw_date }, current: { counted_vnd: '-' + amount, month: '2026-09-01', deleted: false } });
  world.locks = [{ month: '2026-09-01', locked: true }];
  world.legacy.push(sheetPay(41, '16/9/2026 tt', '211000000'), sheetPay(42, 'đã tt', '12000000'), sheetPay(43, '', '3000000'));
  world.receipts = [
    { id: 1, pid: 'PH-001', date: '2026-09-30', method: 'THU TIỀN', amount_vnd: '333333333', reference: 'Sheet: 46295', voided_by_event: null,
      allocations: [debt('2026-04-01', '100000000'), debt('2026-05-01', '200000000'), debt('2026-06-01', '33333333')] },
    { id: 2, pid: 'PH-002', date: '2026-09-30', method: 'THU TIỀN', amount_vnd: '11000000', reference: HASH_REF, voided_by_event: null, allocations: [debt('2026-04-01', '11000000')] },
    { id: 3, pid: 'PH-003', date: '2026-09-04', method: 'THU TIỀN', amount_vnd: '5500000000', reference: 'Sheet: 4/9/2026 TT', voided_by_event: null,
      allocations: [debt('2026-06-01', '1500000'), debt('2026-07-01', '2000000000'), debt('2026-08-01', '3498500000')] },
    { id: 4, pid: 'PH-004', date: '2026-09-30', method: 'THU TIỀN', amount_vnd: '7000000', voided_by_event: null, allocations: [debt('2026-04-01', '7000000')],
      reference: 'Sheet #' + 'ab12'.repeat(16) + ': khách chuyển thay cho công ty bên kia đợt hai · ngày theo cuối tháng khối Sheet' },
  ];
}

test('Phiếu thu: ngày và ghi chú tách đúng cột, Trừ nợ mỗi tháng một dòng, số tiền thẳng cột, không hiện mã máy', async () => withPage(async ({ page }) => {
  for (const width of [1280, 1895]) {
    await page.setViewportSize({ width, height: 848 });
    await reload(page);
    await viewMonth(page, '2026-09');
    const rows = await page.locator('.pay-list tr').evaluateAll(all => all.map(row => {
      const cells = [...row.children];
      const money = cells[4].querySelector('.receipt-sum') ?? cells[4];
      const range = document.createRange();
      range.selectNodeContents(money);
      return { day: cells[0].innerText, note: cells[2].innerText, height: row.getBoundingClientRect().height, right: Math.round(range.getBoundingClientRect().right),
        clipped: cells.map(cell => cell.scrollWidth > cell.clientWidth).some(Boolean) };
    }));
    assert.deepEqual(rows.map(row => [row.day, row.note]), [
      ['16/09/2026', 'tt'], ['–', 'đã tt'], ['–', ''], ['30/09/2026', '+'], ['30/09/2026', 'da tt · ngày tượng trưng'], ['04/09/2026', 'TT'],
      ['30/09/2026', 'khách chuyển thay cho công ty bên kia đợt hai · ngày tượng trưng']]);
    assert.deepEqual(rows.filter(row => row.clipped), [], 'không ô nào bị cắt chữ');
    assert.equal(new Set(rows.map(row => row.right)).size, 1, 'số tiền sổ gốc và phiếu web thẳng một cột: ' + rows.map(row => row.right));
    assert.ok(rows[3].height <= 76, 'phiếu chia ba tháng cao ba dòng chữ, không bẻ tháng và số: ' + rows[3].height);
    assert.equal(rows[0].height, 33, 'khoản thu ghi chú ngắn giữ một dòng');
    // Ghi chú dài xuống dòng, không cắt: dấu "ngày tượng trưng" đứng cuối vẫn phải thấy đủ.
    const long = page.locator('td:has(>.receipt-ref[data-pid="PH-004"])');
    assert.ok(await long.evaluate(cell => cell.scrollHeight <= cell.clientHeight && cell.scrollWidth <= cell.clientWidth), 'ghi chú dài hiện đủ');
    const pairs = await page.locator('tr:has([data-pid="PH-001"]) .alloc-sum').evaluateAll(all => all.map(sum => {
      const box = sum.getBoundingClientRect(), month = sum.previousElementSibling.getBoundingClientRect();
      return { right: Math.round(box.right), sameLine: Math.abs(box.top - month.top) < 2 };
    }));
    assert.equal(pairs.length, 3);
    assert.ok(pairs.every(pair => pair.sameLine && pair.right === pairs[0].right), 'tháng và số cùng dòng, số thẳng cột phải');
    assert.doesNotMatch(await page.locator('.pay-block').innerText(), /Sheet|5bd3cb|46295/);
  }
}, payWorld));

test('Còn nợ cuối tháng cùng một hàng với nhãn; ghi chú, trừ nợ và số tiền của phiếu đứng gần nhau', async () => withPage(async ({ page }) => {
  for (const width of [1280, 1895]) {
    await page.setViewportSize({ width, height: 848 });
    await reload(page);
    await viewMonth(page, '2026-09');
    const line = await page.locator('.month-end').evaluate(node => {
      const range = document.createRange();
      range.selectNodeContents(node.firstChild);
      const label = range.getBoundingClientRect(), money = node.querySelector('b').getBoundingClientRect();
      const up = document.querySelector('.month-received b').getBoundingClientRect();
      return { sameLine: label.bottom > money.top && money.bottom > label.top, right: Math.round(money.right - up.right) };
    });
    assert.deepEqual(line, { sameLine: true, right: 0 }, `${width}px: số không rơi xuống dòng dưới, thẳng mép phải với các số trên`);
    const gaps = await page.locator('.pay-row:has(.alloc-lines)').first().evaluate(row => {
      const box = selector => row.querySelector(selector).getBoundingClientRect();
      const block = document.querySelector('.pay-block').getBoundingClientRect(), entry = document.querySelector('.pay-head .entry-open').getBoundingClientRect();
      return { note: box('.alloc-label').left - box('.receipt-ref').right, money: box('.receipt-sum').left - box('.alloc-lines').right, entryEdge: Math.round(block.right - entry.right), block: block.width };
    });
    assert.ok(gaps.note < 120, `${width}px: từ ghi chú sang Trừ nợ không phải đi qua khoảng trống: ${gaps.note}`);
    assert.ok(gaps.money < 120, `${width}px: từ Trừ nợ sang số tiền: ${gaps.money}`);
    assert.equal(gaps.entryEdge, 0, 'nút Ghi phiếu thu thẳng mép phải khối phiếu');
    assert.ok(gaps.block <= 860, `${width}px: khối phiếu ôm theo nội dung: ${gaps.block}`);
  }
}, world => {
  world.monthValues = { '2026-09-01': { prior_months_vnd: '25334328759', charges_vnd: '860000000', received_vnd: '6594000000', end_of_month_vnd: '19600328759' } };
  world.receipts = [{ id: 3, pid: 'PH-003', date: '2026-09-04', method: 'THU TIỀN', amount_vnd: '6594000000', reference: 'CK', voided_by_event: null,
    allocations: ['2026-06-01', '2026-07-01', '2026-08-01'].map(month => ({ month, amount_vnd: '2198000000', kind: 'debt', superseded_by_event: null })) }];
}));

test('Trang chọn khách: ô tìm sẵn con trỏ, đủ mọi sổ theo nhóm, không lặp mặt hàng, gõ thì lọc, Enter mở dòng đầu', async () => withPage(async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 560 });
  await page.goto(new URL('/so-khach-v7-live.html', page.url()).href);
  await page.waitForFunction(() => document.querySelector('#customer-count')?.textContent);
  assert.equal(await page.locator('.picker-head h1').innerText(), 'Sổ khách');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'customer-search');
  assert.equal(await page.locator('#customer-count').innerText(), '60 khách');
  assert.equal(await page.locator('#customer-list a').count(), 60, 'trang chọn khách không dừng ở 50 dòng');
  assert.deepEqual(await page.locator('#customer-list .customer-group').allInnerTexts(), ['Dừa (30)', 'Thanh long (30)']);
  assert.equal(await page.locator('#customer-list a').first().innerText(), 'Khách 2');
  assert.equal(await page.locator('#live-controls').isVisible(), false, 'chưa có sổ thì không có Làm mới');
  assert.equal(await page.locator('.dashboard-link').isVisible(), false, 'menu trái đã có Tổng quan');
  const geometry = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    page: document.documentElement.scrollHeight - document.documentElement.clientHeight,
    searchTop: document.querySelector('#customer-search').getBoundingClientRect().top,
    list: document.querySelector('#customer-list').scrollHeight > document.querySelector('#customer-list').clientHeight }));
  assert.deepEqual({ overflow: geometry.overflow, page: geometry.page, list: geometry.list }, { overflow: 0, page: 0, list: true }, 'danh sách tự cuộn, ô tìm không trôi khỏi màn');
  await page.locator('#customer-search').fill('khong co ai');
  assert.equal(await page.locator('#customer-count').innerText(), 'Không có khách nào khớp “khong co ai”');
  assert.equal(await page.locator('#customer-list').isVisible(), false);
  await page.locator('#customer-search').fill('thanh long');
  assert.equal(await page.locator('#customer-list a').count(), 30);
  assert.notEqual(await page.locator('#customer-list a').first().evaluate(node => getComputedStyle(node).backgroundColor), 'rgba(0, 0, 0, 0)', 'tô dòng Enter sẽ mở');
  await page.locator('#customer-search').blur();
  await page.locator('.picker-open').click();
  assert.equal(await page.evaluate(() => document.activeElement.id), 'customer-search', 'nút Tìm khách của menu đưa con trỏ về ô tìm');
  await page.locator('#customer-search').press('Enter');
  await page.waitForURL(/customer=1$/);
}, world => {
  world.customers = Array.from({ length: 60 }, (_, i) => ({ id: i + 1, name: `Khách ${i + 1}`, status: 'active', commodity: i % 2 ? 'Dừa' : 'Thanh long' }));
}));

test('Sửa tham chiếu phiếu máy ghi: ô sửa không có mã, lưu vẫn giữ mã để máy nhận ra phiếu', async () => withPage(async ({ page }) => {
  await viewMonth(page, '2026-09');
  const reference = page.locator('.receipt-ref[data-pid="PH-002"][data-field="reference"]');
  await reference.click();
  const input = reference.locator('input');
  assert.equal(await input.inputValue(), 'da tt');
  await input.fill('khách chuyển thiếu');
  const saved = page.waitForRequest(request => request.url().endsWith('/api/v7/receipts/meta'));
  await input.press('Enter');
  const sent = (await saved).postDataJSON();
  assert.equal(sent.pid, 'PH-002');
  assert.equal(sent.reference, 'Sheet #' + '5bd3cb'.repeat(10) + ': khách chuyển thiếu · ngày theo cuối tháng khối Sheet');
}, world => {
  payWorld(world);
  world.locks = [{ month: '2026-09-01', locked: false }];
}));

test('Bảng chuyến 1280: tổng phụ phí đậm không dính mép, sổ có Shipper và ba cột riêng không tràn ngang', async () => withPage(async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await reload(page);
  await viewMonth(page, '2026-09');
  const fee = page.locator('.ledger tr.subtotal td.fee').last();
  assert.match(await fee.innerText(), /^17\.000\.000$/);
  const fit = await fee.evaluate(cell => {
    const range = document.createRange();
    range.selectNodeContents(cell);
    const text = range.getBoundingClientRect(), box = cell.getBoundingClientRect();
    return { left: text.left - box.left, right: box.right - text.right, width: box.width };
  });
  assert.ok(fit.width >= 100, 'cột Khác đủ rộng: ' + fit.width);
  // Máy CI Ubuntu không có Segoe UI, chữ đậm rộng hơn hẳn: đo sát mép ở nơi có font thật của người dùng.
  if (process.platform === 'win32') assert.ok(fit.left >= 4 && fit.right >= 8, 'số không dính mép: ' + JSON.stringify(fit));
  const widths = await page.evaluate(() => ({ page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    table: document.querySelector('.ledger-head').getBoundingClientRect().right - document.querySelector('.trip-card').getBoundingClientRect().right }));
  assert.equal(widths.page, 0);
  assert.ok(widths.table <= 0, 'bảng nằm trong thẻ: ' + widths.table);
}, world => {
  world.feeTypes.push({ id: 20, name: 'Neo', kind: 'service', sign: 'positive', active: true, sort: 20 },
    { id: 21, name: 'Ghép', kind: 'service', sign: 'positive', active: true, sort: 21 },
    { id: 22, name: 'Health + KĐ', kind: 'service', sign: 'positive', active: true, sort: 22 });
  world.feeColumns = [20, 21, 22];
  world.legacy[1].fee_lines = [{ id: 501, fee_type_id: 9, amount_vnd: '17000000', note: null }];
  world.legacy[1].current.other_fee_vnd = '17000000';
}));
