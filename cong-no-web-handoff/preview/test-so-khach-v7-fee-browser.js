/* Trình duyệt (Playwright) cho phụ phí nhiều loại (PHU-PHI-01) trên sổ khách V7 bản live, theo tiêu chí frontend của
 * specs/v7-phu-phi-nhieu-loai.md. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, reload, settled } = require('./so-khach-v7-browser-world');

const feePosts = world => world.requests.filter(item => /\/fees\/|fee-columns/.test(item.path)).map(item => [item.path, item.body]);
const own = (page, target, type) => page.locator(`td.fee.own[data-fee-target="${target}"][data-fee-type="${type}"]`);
const other = (page, target) => page.locator(`td.fee-other[data-fee-target="${target}"]`);
const strip = body => Object.fromEntries(Object.entries(body).filter(([name]) => !['idempotency_key', 'customer_id', 'expected_version'].includes(name)));

test('sổ mặc định chỉ có cột Khác; ba cột riêng vẫn vừa 1280×720, Tổng tháng có tổng từng cột', async () => withPage(async ({ page, world }) => {
  await page.locator('.fee-other').first().waitFor();
  assert.deepEqual(await page.locator('.ledger-head th.fee-h').allInnerTexts(), ['Khác']);
  assert.equal(await page.locator('td.fee.own').count(), 0);
  // Dòng sổ gốc OLDU0000002: phụ phí cũ đã tách thành một khoản → ô Khác ghi số (một dòng), "1 khoản" ở chữ rê chuột (SO-GON-05).
  assert.equal(await other(page, 'legacy:22').innerText(), '3.000.000');
  assert.equal(await other(page, 'legacy:22').getAttribute('title'), 'Phụ phí khác (1 khoản)');
  world.feeColumns = [1, 2, 3];
  world.version += 1;
  await reload(page);
  // SO-GON-07: ba cột riêng chưa có khoản nào trong tháng thì ẩn; nút ở thanh bảng chuyến mở lại để gõ phí.
  assert.equal(await page.locator('td.fee.own').count(), 0);
  await page.getByRole('button', { name: 'Hiện 3 cột phí trống' }).click();
  await page.locator('td.fee.own').first().waitFor();
  assert.deepEqual(await page.locator('.ledger-head th.fee-h').allInnerTexts(), ['Neo', 'Điện', 'Ghép', 'Khác']);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  assert.equal(await page.locator('.ledger-book.fee-over').count(), 0, 'ba cột vừa màn: tiêu đề cột vẫn dính, không cuộn trong khung');
  assert.equal(await page.locator('#thang-2026-09 .subtotal td.fee').count(), 4);
  assert.equal(await page.locator('text=sổ gốc').count(), 0);
}, world => { world.feeHideEmpty = true; }));

test('COT-PHU-PHI-01 + SO-GON-07: bảy cột riêng trống ẩn; bấm Hiện thì cột hẹp, bảng cuộn ngang, Thành tiền ghim phải', async () => withPage(async ({ page }) => {
  await page.locator('.fee-other').first().waitFor();
  assert.deepEqual(await page.locator('.ledger-head th.fee-h').allInnerTexts(), ['Khác']);
  assert.equal(await page.locator('.ledger-book.fee-over').count(), 0, 'cột trống ẩn: bảng vừa khung');
  assert.equal(await page.evaluate(() => [...document.querySelectorAll('#thang-2026-09 .trip-list tr[data-row]')].every(tr => tr.getBoundingClientRect().height <= 40)), true, 'mỗi chuyến một dòng');
  await page.getByRole('button', { name: 'Hiện 7 cột phí trống' }).click();
  await page.locator('td.fee.own').first().waitFor();
  assert.deepEqual(await page.locator('.ledger-head th.fee-h').evaluateAll(list => list.map(th => th.textContent)),
    ['Lưu bãi', 'Ghép', 'Điện', 'Neo', 'Health + KĐ', 'Phí hủy', 'Sửa bill', 'Khác']);
  assert.equal(await page.locator('.ledger-head th.fee-narrow').count(), 7, 'sổ chưa có khoản nào của bảy loại');
  // SK-N1: chỉ thân bảng cuộn ngang (khung riêng); khung ngoài không cuộn nên hàng tiêu đề còn dính theo trang.
  const box = await page.evaluate(() => {
    const card = document.querySelector('#thang-2026-09 .trip-card');
    const body = card.querySelector('.trip-body-scroll');
    const amount = card.querySelector('.ledger-head th:last-child');
    body.scrollLeft = body.scrollWidth;
    const right = amount.getBoundingClientRect().right;
    return { over: Boolean(document.querySelector('.ledger-book.fee-over')), card: getComputedStyle(card).overflowX, scroll: getComputedStyle(body).overflowX,
      inside: right <= card.getBoundingClientRect().right + 1, label: amount.textContent, page: document.documentElement.scrollWidth <= innerWidth };
  });
  assert.deepEqual(box, { over: true, card: 'clip', scroll: 'auto', inside: true, label: 'Thành tiền', page: true });
  // Chưa cuộn ngang: cột Thành tiền ghim phải vẫn nằm trọn trong khung.
  const pinned = await page.evaluate(() => {
    const card = document.querySelector('#thang-2026-09 .trip-card');
    card.querySelector('.trip-body-scroll').scrollLeft = 0;
    const amount = card.querySelector('.trip-list tr[data-row] td:last-child').getBoundingClientRect();
    return amount.right <= card.getBoundingClientRect().right + 1 && amount.left >= card.getBoundingClientRect().left;
  });
  assert.equal(pinned, true, 'Thành tiền thấy được khi chưa cuộn ngang');
  await page.getByRole('button', { name: 'Ẩn cột phí trống' }).click();
  await page.getByRole('button', { name: 'Hiện 7 cột phí trống' }).waitFor();
}, world => {
  for (const [id, name, sort] of [[10, 'Health + KĐ', 7], [11, 'Lưu bãi', 8], [12, 'Phí hủy', 9], [13, 'Sửa bill', 10]]) {
    world.feeTypes.splice(world.feeTypes.length - 3, 0, { id, name, kind: 'service', sign: 'positive', system_key: null, active: true, sort });
  }
  world.feeColumns = [11, 3, 2, 1, 10, 12, 13];
  world.feeHideEmpty = true;
}));

// SK-N1 + SK-N5 (audit Sổ khách 25/11/2026): sổ bảy cột phí đều có khoản, 24 chuyến, tên nơi dài. Khung 1265×560 = màn 1280×560
// trừ thanh cuộn dọc 15px của Chrome Windows (headless không vẽ thanh cuộn).
const wideBook = world => {
  for (const [id, name, sort] of [[10, 'Health + KĐ', 7], [11, 'Lưu bãi', 8], [12, 'Phí hủy', 9], [13, 'Sửa bill', 10]]) {
    world.feeTypes.splice(world.feeTypes.length - 3, 0, { id, name, kind: 'service', sign: 'positive', system_key: null, active: true, sort });
  }
  world.feeColumns = [11, 3, 2, 1, 10, 12, 13];
  world.feeHideEmpty = true;
  const places = ['Kho hàng khu công nghiệp thử số một', 'Cảng A', 'Bãi container thử phía Nam', 'Cửa khẩu B'];
  world.trips = Array.from({ length: 24 }, (_, i) => {
    const fees = world.feeColumns.filter((_, k) => (i + k) % 3 === 0).map((type, k) => ({ id: 700 + i * 10 + k, fee_type_id: type, amount_vnd: '1500000', note: null }));
    return { id: 200 + i, month: '2026-09-01', container: `DEMU${String(1000000 + i)}`, carrier: 'Tàu thử', shipper: 'Chủ hàng thử có tên khá dài',
      event_date: `2026-09-${String(1 + i).padStart(2, '0')}`, origin: places[i % 4], destination: places[(i + 1) % 4], unit_price_vnd: '12000000',
      other_fee_vnd: null, amount_vnd: String(12000000 + fees.length * 1500000), status: 'confirmed', is_missing_price: false, is_fee_only: false,
      editable: true, info_editable: true, deleted: false, fee_lines: fees };
  });
  world.legacy = [];
};

test('SK-N1: bảng rộng ở 1280×560, cuộn tới chuyến cuối vẫn thấy hàng tiêu đề và Thành tiền; tiêu đề cuộn ngang theo thân bảng', async () => withPage(async ({ page }) => {
  await page.setViewportSize({ width: 1265, height: 560 });
  await reload(page);
  await page.locator('.trip-body-scroll .trip-list tr[data-row]').first().waitFor();
  assert.equal(await page.locator('.ledger-head th.fee-h').count(), 8, 'bảy cột riêng có khoản + Khác');
  const seen = await page.evaluate(() => {
    const rows = document.querySelectorAll('#thang-2026-09 .trip-list tr[data-row]');
    const last = rows[rows.length - 1];
    window.scrollTo({ top: scrollY + last.getBoundingClientRect().bottom - innerHeight + 20, behavior: 'instant' });
    const hit = el => { const b = el.getBoundingClientRect(); const top = document.elementFromPoint(b.left + 6, b.top + b.height / 2); return el === top || el.contains(top); };
    const head = document.querySelector('.ledger-head');
    return { headTop: head.getBoundingClientRect().top > 0, headAmount: hit(head.querySelector('th:last-child')), headFirst: hit(head.querySelector('th')),
      lastAmount: hit(last.lastElementChild), lastShown: last.getBoundingClientRect().bottom <= innerHeight };
  });
  assert.deepEqual(seen, { headTop: true, headAmount: true, headFirst: true, lastAmount: true, lastShown: true });
  // Cuộn ngang thân bảng: hàng tiêu đề đi theo, mỗi tiêu đề vẫn thẳng cột với ô của nó (trừ Thành tiền ghim phải).
  await page.evaluate(() => { document.querySelector('.trip-body-scroll').scrollLeft = 200; });
  await page.waitForFunction(() => document.querySelector('.trip-head-scroll').scrollLeft === 200);
  const aligned = await page.evaluate(() => {
    const ths = [...document.querySelectorAll('.ledger-head th')], tds = [...document.querySelector('.trip-list tr[data-row]').cells];
    return ths.slice(0, -1).every((th, index) => Math.abs(th.getBoundingClientRect().left - tds[index].getBoundingClientRect().left) < 1);
  });
  assert.equal(aligned, true);
  // Cuộn trên hàng tiêu đề (Shift + lăn chuột) cũng cuộn thân bảng.
  await page.evaluate(() => { document.querySelector('.trip-head-scroll').scrollLeft = 60; });
  await page.waitForFunction(() => document.querySelector('.trip-body-scroll').scrollLeft === 60);
}, wideBook));

test('SK-N5: ô bị cắt "…" có chữ rê chuột đủ chữ; Tuyến cắt nơi đi trước, giữ nơi đến', async () => withPage(async ({ page }) => {
  await page.setViewportSize({ width: 1265, height: 560 });
  await reload(page);
  await page.locator('.trip-list tr[data-row]').first().waitFor();
  const cells = await page.evaluate(() => [...document.querySelectorAll('.trip-list td')]
    .filter(td => [td, ...td.children].some(box => box.scrollWidth > box.clientWidth)).map(td => td.title));
  assert.ok(cells.length >= 24, `phải có ô bị cắt để kiểm (${cells.length})`);
  assert.equal(cells.filter(title => !title).length, 0, 'mọi ô bị cắt có title');
  // Chuyến 200: nơi đi dài, nơi đến ngắn → nơi đi co trước (về bề rộng tối thiểu 2em) rồi nơi đến mới co; chữ rê chuột ghép cả
  // tuyến. Không đo "nơi đến còn đủ" thẳng vì font Ubuntu của CI rộng hơn Segoe UI (ở Windows "Cảng A" còn đủ chữ).
  const route = await page.locator('tr[data-row="trip-200"] td.route-cell').evaluate(td => {
    const [from, , to] = td.children;
    const originFirst = to.scrollWidth <= to.clientWidth || from.clientWidth <= parseFloat(getComputedStyle(from).minWidth) + 1;
    return { from: from.scrollWidth > from.clientWidth, originFirst, toText: to.textContent, title: td.title };
  });
  assert.deepEqual(route, { from: true, originFirst: true, toText: 'Cảng A', title: 'Kho hàng khu công nghiệp thử số một → Cảng A' });
  if (process.platform === 'win32') {
    assert.equal(await page.locator('tr[data-row="trip-200"] td.route-cell>:last-child').evaluate(to => to.scrollWidth <= to.clientWidth), true, 'Segoe UI: nơi đến còn đủ chữ');
  }
  assert.equal(await page.locator('tr[data-row="trip-200"] td[data-field="shipper"]').getAttribute('title'), 'Chủ hàng thử có tên khá dài');
  assert.equal(await page.locator('tr[data-row="trip-200"]').evaluate(tr => tr.getBoundingClientRect().height), 35, 'ô Tuyến không làm dòng cao thêm');
}, wideBook));

test('SK-N5: sổ chuyến bộ (khách có transport_mode BO) gọi cột biển số là "Xe"', async () => withPage(async ({ page }) => {
  await page.locator('.trip-list tr[data-row]').first().waitFor();
  assert.equal(await page.locator('.ledger-head th').nth(2).innerText(), 'Xe');
  assert.equal(await page.locator('.info-edit[data-kind="trip"][data-id="11"][data-field="carrier"]').getAttribute('aria-label'), 'Sửa xe');
}, world => { world.customers = [{ id: 1, name: 'Khách Thử Sửa', status: 'active', transport_mode: 'BO' }]; }));

test('ô cột riêng: gõ số + Enter gửi một lệnh đặt loại; Esc trả lại, xóa trắng bỏ loại đó', async () => withPage(async ({ page, world }) => {
  const cell = own(page, 'trip:11', 1);
  await cell.click();
  await page.keyboard.press('Escape');
  await settled(page);
  assert.equal(feePosts(world).length, 0);
  await cell.click();
  await page.locator('.fee-own-input').fill('1.200.000');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '1.200.000');
  await settled(page);
  assert.deepEqual(feePosts(world).map(([path, body]) => [path, strip(body)]),
    [['/api/v7/trips/fees/set', { target: { trip_id: 11 }, fee_type_id: 1, amount_vnd: '1200000' }]]);
  // NHAP-NHANH-01: Thành tiền hiện "…" tới khi máy chủ trả số, nên chờ chứ không đọc ngay sau Enter.
  await page.waitForFunction(() => /51\.200\.000/.test(document.querySelector('tr[data-row="trip-11"]')?.innerText ?? ''));   // Thành tiền từ server
  // Số âm ở loại số dương: báo ngay tại ô, không gửi.
  await cell.click();
  await page.locator('.fee-own-input').fill('-5000');
  await page.keyboard.press('Enter');
  assert.match(await cell.locator('.cell-error').innerText(), /Loại này nhập số dương/);
  await page.locator('.fee-own-input').fill('');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '');
  await settled(page);
  assert.deepEqual(strip(feePosts(world).at(-1)[1]), { target: { trip_id: 11 }, fee_type_id: 1, amount_vnd: null });
}, world => { world.feeColumns = [1]; }));

test('khung Chi tiết phụ phí: thêm, đổi loại sang cột riêng, sửa số, xóa; Giảm trừ dương bị chặn tại form', async () => withPage(async ({ page, world }) => {
  await other(page, 'trip:11').click();
  const drawer = page.locator('.fee-drawer');
  await drawer.locator('.fee-close').waitFor();
  assert.match(await drawer.innerText(), /DEMU1234567/);
  assert.match(await drawer.innerText(), /Chưa có khoản phụ phí nào/);
  await drawer.locator('.fee-add-type').selectOption('8');
  await drawer.locator('.fee-add-amount').fill('200.000');
  await drawer.locator('.fee-add button[type="submit"]').click();
  assert.match(await drawer.locator('.fee-error').innerText(), /Giảm trừ nhập số âm/);
  await settled(page);
  assert.equal(feePosts(world).length, 0);
  await drawer.locator('.fee-add-type').selectOption('7');
  await drawer.locator('.fee-add-note').fill('lưu bãi');
  await drawer.locator('.fee-add button[type="submit"]').click();
  await drawer.locator('.fee-lines tbody tr').first().waitFor();
  await settled(page);
  assert.deepEqual(strip(feePosts(world)[0][1]), { targets: [{ trip_id: 11 }], fee_type_id: 7, amount_vnd: '200000', note: 'lưu bãi' });
  assert.equal(await other(page, 'trip:11').innerText(), '200.000');
  assert.match(await other(page, 'trip:11').getAttribute('aria-label'), /\(1 khoản\)$/);
  assert.match(await drawer.locator('.fee-sumline.calc').innerText(), /50\.000\.000 \+ 200\.000\s*50\.200\.000/);
  // Đổi loại sang Neo (cột riêng của sổ) → số chuyển qua cột Neo, ô Khác trống.
  await drawer.locator('.fee-line-type').first().selectOption('1');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '200.000');
  await settled(page);
  assert.equal(feePosts(world)[1][0], '/api/v7/trips/fees/replace');
  await settled(page);
  assert.deepEqual({ ...strip(feePosts(world)[1][1]), fee_line_id: 'id' }, { fee_line_id: 'id', fee_type_id: 1, amount_vnd: '200000', note: 'lưu bãi' });
  assert.match(await drawer.locator('.fee-tag').first().innerText(), /cột riêng/);
  // Sửa số tại khung: Enter lưu.
  await drawer.locator('.fee-amt').first().click();
  await drawer.locator('.fee-line-amount').fill('350000');
  await drawer.locator('.fee-line-amount').press('Enter');
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="trip:11"][data-fee-type="1"]')?.textContent === '350.000');
  // Xóa khoản.
  await drawer.locator('.fee-del').first().click();
  await page.waitForFunction(() => document.querySelector('.fee-drawer')?.textContent.includes('Chưa có khoản phụ phí nào'));
  await settled(page);
  assert.equal(feePosts(world).at(-1)[0], '/api/v7/trips/fees/void');
  await drawer.locator('.fee-close').click();
  assert.equal(await drawer.isVisible(), false);
}, world => { world.feeColumns = [1]; }));

test('thêm một khoản cho nhiều chuyến: một lệnh cho mọi chuyến đã chọn, bấm lặp không gửi hai lần', async () => withPage(async ({ page, world }) => {
  await page.locator('.fee-pick[data-fee-target="trip:11"]').check();
  await page.locator('.fee-pick[data-fee-target="legacy:22"]').check();
  assert.equal(await page.locator('.delete-prompt').count(), 0, 'bấm ô chọn không mở hỏi xóa dòng');
  assert.match(await page.locator('.fee-selbar').innerText(), /Đã chọn 2 chuyến/);
  await page.locator('.fee-batch').click();
  const drawer = page.locator('.fee-drawer');
  await drawer.locator('.fee-add-type').selectOption('4');
  await drawer.locator('.fee-add-amount').fill('300000');
  await drawer.locator('.fee-add button[type="submit"]').dblclick();
  await page.waitForFunction(() => !document.querySelector('.fee-selbar'));
  await settled(page);
  assert.deepEqual(feePosts(world).map(([path, body]) => [path, strip(body)]),
    [['/api/v7/trips/fees/add', { targets: [{ trip_id: 11 }, { legacy_row_id: 22 }], fee_type_id: 4, amount_vnd: '300000' }]]);
  assert.match(await page.locator('.live-notice').innerText(), /Đã thêm Bảo hiểm 300\.000 cho 2 chuyến/);
}));

test('tháng khóa: ô cột riêng chỉ đọc, khung không có form, không đánh dấu được; dòng chưa đơn giá cũng chỉ xem', async () => withPage(async ({ page, world }) => {
  await other(page, 'legacy:21').click();
  assert.match(await page.locator('.fee-drawer .fee-info').innerText(), /chưa có đơn giá/);
  assert.equal(await page.locator('.fee-drawer .fee-add').count(), 0);
  await page.locator('.fee-drawer .fee-close').click();
  assert.equal(await page.locator('.fee-pick[data-fee-target="legacy:21"]').count(), 0);
  world.locks = [{ month: '2026-09-01', locked: true }];
  world.version += 1;
  await reload(page);
  await other(page, 'trip:11').waitFor();
  assert.equal(await page.locator('#thang-2026-09 .fee-pick').count(), 0);
  assert.equal(await own(page, 'trip:11', 1).getAttribute('tabindex'), null);
  await own(page, 'trip:11', 1).click();
  assert.equal(await page.locator('.fee-own-input').count(), 0);
  await other(page, 'legacy:22').click();
  assert.match(await page.locator('.fee-drawer .fee-info').innerText(), /Tháng đã khóa — mở khóa tháng để sửa phụ phí/);
  assert.equal(await page.locator('.fee-drawer .fee-add').count(), 0);
  assert.equal(await page.locator('.fee-drawer select').count(), 0);
  await settled(page);
  assert.equal(feePosts(world).length, 0);
}, world => { world.feeColumns = [1]; }));

test('dòng sổ gốc có Thành tiền khác đơn giá + phụ phí: hỏi lại với số trước → sau; Enter không bấm luôn Ghi', async () => withPage(async ({ page, world }) => {
  await own(page, 'legacy:22', 1).click();
  await page.locator('.fee-own-input').fill('1000000');
  await page.keyboard.press('Enter');
  const box = page.locator('.fee-confirm');
  await box.locator('.fee-yes').waitFor();
  assert.match(await box.innerText(), /OLDU0000002: Thành tiền đang là 95\.000\.000 → 94\.000\.000 \(-1\.000\.000\)/);
  await settled(page);
  assert.equal(feePosts(world).length, 0, 'Enter vừa lưu ô không được bấm Ghi');
  await box.locator('.fee-no').click();
  await settled(page);
  assert.equal(feePosts(world).length, 0);
  await own(page, 'legacy:22', 1).click();
  await page.locator('.fee-own-input').fill('1000000');
  await page.keyboard.press('Enter');
  await box.locator('.fee-yes').click();
  await page.waitForFunction(() => document.querySelector('td.fee.own[data-fee-target="legacy:22"][data-fee-type="1"]')?.textContent === '1.000.000');
  await settled(page);
  assert.deepEqual(strip(feePosts(world)[0][1]), { target: { legacy_row_id: 22 }, fee_type_id: 1, amount_vnd: '1000000' });
}, world => { world.feeColumns = [1]; world.legacy[1].current.counted_vnd = '95000000'; }));

test('cài đặt phụ phí: bật cột riêng không giới hạn, đổi tên và thêm loại qua danh mục chung', async () => withPage(async ({ page, world }) => {
  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();   // SO-GON-06: menu Cài đặt ▾
  await page.locator('.fee-settings-open').click();
  const panel = page.locator('.fee-settings');
  await panel.locator('.fee-col[data-id="2"]').check();
  await page.waitForFunction(() => document.querySelectorAll('.ledger-head th.fee-h').length === 4);
  await settled(page);
  assert.deepEqual(strip(feePosts(world).at(-1)[1]), { fee_type_ids: [1, 3, 2] });
  // COT-PHU-PHI-01: không còn giới hạn 3 cột, ô thứ tư bật được.
  await panel.locator('.fee-col[data-id="4"]').check();
  await page.waitForFunction(() => document.querySelectorAll('.ledger-head th.fee-h').length === 5);
  await settled(page);
  assert.deepEqual(strip(feePosts(world).at(-1)[1]), { fee_type_ids: [1, 3, 2, 4] });
  assert.equal(await panel.locator('.fee-info').count(), 0);
  await panel.locator('.fee-col[data-id="4"]').uncheck();
  await page.waitForFunction(() => document.querySelectorAll('.ledger-head th.fee-h').length === 4);
  // Bỏ cột Ghép: số không mất, chỉ đổi cách hiện.
  await panel.locator('.fee-col[data-id="3"]').uncheck();
  await page.waitForFunction(() => document.querySelectorAll('.ledger-head th.fee-h').length === 3);
  // Tên loại là nút: Tab tới và Enter được (audit giao diện 23/11 F4).
  await panel.locator('td.fee-name[data-id="4"] .fee-name-btn').focus();
  await page.keyboard.press('Enter');
  await panel.locator('.fee-rename').fill('Bảo hiểm hàng');
  await panel.locator('.fee-rename').press('Enter');
  await page.waitForFunction(() => document.querySelector('.fee-settings')?.textContent.includes('Bảo hiểm hàng'));
  await panel.locator('.fee-new-name').fill('neo');
  await panel.locator('.fee-newtype button').click();
  assert.match(await panel.locator('.fee-error').innerText(), /Đã có loại neo/);
  await panel.locator('.fee-new-name').fill('Nâng hạ');
  await panel.locator('.fee-new-kind').selectOption('pass_through');
  await panel.locator('.fee-newtype button').click();
  await page.waitForFunction(() => document.querySelector('.fee-settings')?.textContent.includes('Nâng hạ'));
  assert.deepEqual(world.catalogRequests.map(({ idempotency_key: _key, ...rest }) => rest), [
    { command: 'rename_fee_type', fee_type_id: 4, name: 'Bảo hiểm hàng' }, { name: 'Nâng hạ', kind: 'pass_through' }]);
  assert.equal(await panel.locator('td.fee-name:not([data-id])').count(), 3, 'ba loại hệ thống không đổi tên');
  await page.keyboard.press('Escape');
  assert.equal(await panel.isVisible(), false);
}, world => { world.feeColumns = [1, 3]; }));

test('cài đặt phụ phí: Tắt tất cả, Bật tất cả giữ thứ tự cũ rồi thêm theo danh mục, Về mặc định theo thứ tự chứng từ', async () => withPage(async ({ page, world }) => {
  if (!await page.locator('.page-more').evaluate(node => node.open)) await page.locator('.page-more > summary').click();
  await page.locator('.book-settings > summary').click();
  await page.locator('.fee-settings-open').click();
  const panel = page.locator('.fee-settings');
  const heads = n => page.waitForFunction(count => document.querySelectorAll('.ledger-head th.fee-h').length === count, n);
  await panel.locator('.fee-col-none').click();
  await heads(1);   // chỉ còn cột Khác
  await settled(page);
  assert.deepEqual(strip(feePosts(world).at(-1)[1]), { fee_type_ids: [] });
  assert.equal(await panel.locator('.fee-col-none').isDisabled(), true);
  await panel.locator('.fee-col[data-id="4"]').check();
  await heads(2);
  await panel.locator('.fee-col-all').click();
  await heads(5);
  await settled(page);
  assert.deepEqual(strip(feePosts(world).at(-1)[1]), { fee_type_ids: [4, 1, 2, 3] }, 'loại hệ thống không thành cột riêng');
  assert.equal(await panel.locator('.fee-col-all').isDisabled(), true);
  await panel.locator('.fee-col-default').click();
  await heads(4);
  await settled(page);
  assert.deepEqual(strip(feePosts(world).at(-1)[1]), { fee_type_ids: [3, 2, 1] });
  assert.equal(await panel.locator('.fee-col-default').isDisabled(), true);
  assert.match(await panel.locator('.fee-types thead').innerText(), /Cột riêng trên sổ này \(3\)/);
}, world => { world.feeColumns = [1, 3]; }));
