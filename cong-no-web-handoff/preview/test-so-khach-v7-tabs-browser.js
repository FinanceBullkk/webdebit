/* Trình duyệt (Playwright) cho vỏ trang khách (TRANG-KHACH-01, specs/v7-trang-khach.md, PR A1): tham số the=, thẻ mặc định K2,
 * đổi thẻ không tải lại trang và không thêm lịch sử, bàn phím, đầu trang ≤ 44px, chữ đang gõ còn nguyên khi đổi thẻ.
 * Máy chủ giả, dữ liệu giả, 1280×720; không chạm DB hay Sheet. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { todayMonth, withPage } = require('./so-khach-v7-browser-world');

// Thẻ đang mở: thẻ được chọn trên thanh thẻ, khung đang hiện, địa chỉ.
const state = page => page.evaluate(() => ({
  selected: [...document.querySelectorAll('.page-tab[aria-selected="true"]')].map(tab => tab.dataset.the),
  shown: [...document.querySelectorAll('#app > .tab-pane')].filter(pane => getComputedStyle(pane).display !== 'none').map(pane => pane.id),
  search: location.search }));
const focused = page => page.evaluate(() => document.activeElement.id || document.activeElement.className);
const trip = (id, month, extra = {}) => ({ id, month, container: `TABS${String(id).padStart(7, '0')}`, carrier: 'Tàu thử', event_date: `${month.slice(0, 8)}20`,
  origin: 'Nơi A', destination: 'Nơi B', unit_price_vnd: '1000000', other_fee_vnd: null, amount_vnd: '1000000', status: 'confirmed',
  is_missing_price: false, is_fee_only: false, editable: true, info_editable: true, deleted: false, ...extra });

test('the= mở đúng thẻ; không ghi thẻ, có month= hoặc loc=, hay thẻ lạ thì mở thẻ Sổ (K2)', async () => withPage(async ({ page }) => {
  const base = page.url().split('?')[0];
  for (const [query, tab] of [['', 'so'], ['&the=tinh-hinh', 'tinh-hinh'], ['&the=so', 'so'], ['&the=trao-doi', 'trao-doi'], ['&the=ho-so', 'ho-so'],
    ['&the=tinh-hinh&month=2026-09', 'so'], ['&loc=thieu-gia&the=ho-so', 'so'], ['&the=khong-co', 'so']]) {
    await page.goto(`${base}?customer=1${query}`);
    await page.waitForSelector('.book-head .page-tab');
    const now = await state(page);
    assert.deepEqual([now.selected, now.shown], [[tab], [`the-${tab}`]], query);
    // Đầu trang (tên khách, tổng còn nợ, Ghi phiếu thu) ở mọi thẻ; sổ chỉ hiện ở thẻ Sổ.
    assert.equal(await page.locator('.book-head .head-item.total strong').innerText(), '0 đ', query);
    assert.equal(await page.locator('.book-head .entry-open').isVisible(), true, query);
    assert.equal(await page.locator('.ledger-book').isVisible(), tab === 'so', query);
  }
}));

test('Bấm thẻ: địa chỉ đổi, trang không tải lại, không thêm lịch sử; Back và "← Quay lại" về trang trước', async () => withPage(async ({ page, world }) => {
  await page.evaluate(() => { window.sameDocument = true; });
  const before = await page.evaluate(() => history.length);
  const reads = world.reads;
  // Rời thẻ Sổ thì bỏ month= (month= luôn mở Sổ); thẻ Sổ không ghi the=.
  for (const [tab, search] of [['tinh-hinh', '?customer=1&the=tinh-hinh'], ['trao-doi', '?customer=1&the=trao-doi'], ['ho-so', '?customer=1&the=ho-so'],
    ['so', '?customer=1']]) {
    await page.locator(`#tab-${tab}`).click();
    assert.deepEqual(await state(page), { selected: [tab], shown: [`the-${tab}`], search });
  }
  // Thẻ chưa có nội dung có nút về thẻ Sổ; tiêu điểm về thẻ Sổ trên thanh.
  await page.locator('#tab-ho-so').click();
  await page.locator('#the-ho-so .tab-go').click();
  assert.deepEqual((await state(page)).selected, ['so']);
  assert.equal(await focused(page), 'tab-so');
  assert.deepEqual(await page.evaluate(() => [window.sameDocument, history.length]), [true, before]);
  assert.equal(world.reads, reads, 'đổi thẻ không đọc lại sổ');
  await page.goBack();
  assert.equal(page.url(), 'about:blank');
  await page.goForward();
  await page.waitForSelector('.book-head .page-tab');
  assert.match(page.url(), /\?customer=1$/);
  assert.equal(await page.locator('.page-back').innerText(), '← Quay lại');
  await page.locator('.page-back').click();
  await page.waitForURL('about:blank');
}));

test('Bàn phím: Tab tới thanh thẻ, mũi tên trái/phải chuyển thẻ, Enter/Space mở; vùng bấm ở đầu trang ≥ 40px', async () => withPage(async ({ page }) => {
  await page.locator('.page-back').focus();
  await page.keyboard.press('Tab');
  assert.equal(await focused(page), 'tab-so');
  await page.keyboard.press('ArrowRight');
  assert.equal(await focused(page), 'tab-trao-doi');
  assert.deepEqual((await state(page)).selected, ['so'], 'mũi tên chỉ chuyển tiêu điểm, Enter mới mở');
  await page.keyboard.press('Enter');
  assert.deepEqual(await state(page), { selected: ['trao-doi'], shown: ['the-trao-doi'], search: '?customer=1&the=trao-doi' });
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  assert.equal(await focused(page), 'tab-tinh-hinh', 'hết thẻ thì vòng về đầu');
  await page.keyboard.press('Space');
  assert.deepEqual((await state(page)).selected, ['tinh-hinh']);
  await page.keyboard.press('ArrowLeft');
  assert.equal(await focused(page), 'tab-ho-so');
  await page.keyboard.press('Home');
  assert.equal(await focused(page), 'tab-tinh-hinh');
  await page.keyboard.press('End');
  assert.equal(await focused(page), 'tab-ho-so');
  await page.keyboard.press('Tab');
  assert.equal(await focused(page), 'entry-open', 'Tab rời thanh thẻ');
  const small = await page.evaluate(() => [...document.querySelectorAll('.book-head :is(a,button)')].map(node => [node.id || node.className, node.getBoundingClientRect()])
    .filter(([, box]) => box.height < 40 || box.width < 40).map(([name, box]) => `${name} ${box.width}×${box.height}`));
  assert.deepEqual(small, []);
}));

const LONG = 'CÔNG TY TNHH NÔNG SẢN XUẤT KHẨU GIẢ MIỀN TÂY';
test('Đầu trang một dòng ≤ 44px, tên khách dài không bị cắt; thẻ Sổ: phần dính ≤ 180px, không cuộn ngang ở 1280', async () => withPage(async ({ page }) => {
  const head = await page.evaluate(() => {
    const box = selector => document.querySelector(selector).getBoundingClientRect();
    const bar = box('.book-head'), who = box('.page-who');
    return { height: bar.height, inside: who.top >= bar.top && who.bottom <= bar.bottom - 2 && who.right <= box('.page-tabs').left,
      name: document.querySelector('.page-name').innerText, meta: document.querySelector('.page-meta').innerText };
  });
  assert.ok(head.height <= 44, `đầu trang ${head.height}px`);
  assert.ok(head.inside, 'tên khách và mặt hàng nằm gọn trong đầu trang, không chờm sang thanh thẻ');
  assert.deepEqual([head.name, head.meta], [LONG, 'Sầu riêng · cảng']);
  assert.equal(await page.locator('.book-head .head-item.total strong').innerText(), '12.345.678.900 đ');
  await page.evaluate(() => window.scrollTo({ top: 1200, behavior: 'instant' }));
  const geo = await page.evaluate(() => ({ banner: document.querySelector('#demo-banner').offsetHeight,
    chips: document.querySelector('.month-chips').getBoundingClientRect().top, bottom: document.querySelector('.ledger-head').getBoundingClientRect().bottom,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth }));
  assert.ok(geo.bottom - geo.banner <= 180, `phần dính ${geo.bottom - geo.banner}px`);
  assert.equal(geo.chips - geo.banner, 100, 'thanh tháng dính ngay dưới đầu trang');
  assert.equal(geo.overflow, 0);
}, world => {
  world.trips.push(...Array.from({ length: 40 }, (_, index) => trip(300 + index, '2026-09-01')));
  world.total = '12345678900';
  world.customers = [{ id: 1, name: LONG, commodity: 'Sầu riêng', transport_mode: 'CANG', status: 'active' }];
}));

test('Đang gõ dở trong khung Ghi phiếu thu, sang thẻ khác rồi quay lại: số đã gõ còn nguyên; Ghi phiếu thu ở thẻ khác mở thẻ Sổ', async () => withPage(async ({ page, world }) => {
  const drawer = page.locator('.entry-drawer');
  const values = () => drawer.locator('.receipt-date,.receipt-amount,.receipt-reference').evaluateAll(inputs => inputs.map(input => input.value));
  await page.locator('.book-head .entry-open').click();
  await drawer.locator('.receipt-date').fill('15/09/2026');
  await drawer.locator('.receipt-amount').fill('1.234.567');
  await drawer.locator('.receipt-reference').fill('CK thử');
  await page.locator('#tab-tinh-hinh').click();
  assert.deepEqual([await drawer.isVisible(), await page.locator('#the-so').isVisible()], [false, false], 'khung và sổ ẩn ở thẻ khác');
  await page.locator('#tab-so').click();
  assert.equal(await drawer.isVisible(), true);
  assert.deepEqual(await values(), ['15/09/2026', '1.234.567', 'CK thử']);
  await drawer.locator('.entry-close').click();
  await page.locator('#tab-ho-so').click();
  await page.locator('.book-head .entry-open').click();
  assert.deepEqual(await state(page), { selected: ['so'], shown: ['the-so'], search: '?customer=1' });
  assert.equal(await drawer.isVisible(), true);
  assert.equal(await focused(page), 'receipt-amount');
  assert.deepEqual(await values(), ['15/09/2026', '1.234.567', 'CK thử']);
  assert.equal(world.requests.length, 0, 'chưa gửi lệnh nào');
}));

test('Sổ tự cập nhật lúc đang ở thẻ khác: quay lại thẻ Sổ đúng chỗ cuộn, danh sách phiếu dính và chip tháng đo lại đúng', async () => withPage(async ({ page, world }) => {
  const probe = () => page.evaluate(() => {
    const head = document.querySelector('.ledger-head');
    return { y: Math.round(window.scrollY), top: document.querySelector('#thang-2026-09 .pay-stick.pinned')?.style.top,
      want: `${Math.round(Number.parseFloat(getComputedStyle(head).top) + head.offsetHeight)}px`,
      chip: document.querySelector('.month-chip[aria-current="true"]')?.dataset.month };
  });
  await page.evaluate(() => window.scrollTo({ top: 400, behavior: 'instant' }));
  await page.waitForFunction(() => document.querySelector('.month-chip[aria-current="true"]')?.dataset.month === '2026-09');
  const before = await probe();
  await page.locator('#tab-tinh-hinh').click();
  const reads = world.reads;
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));   // tự cập nhật: đọc lại và vẽ lại cả sổ
  await page.waitForFunction(() => document.querySelector('#updated-at').textContent.startsWith('Cập nhật'));
  assert.equal(world.reads, reads + 1);
  await page.locator('#tab-so').click();
  await page.waitForFunction(() => document.querySelector('.month-chip[aria-current="true"]')?.dataset.month === '2026-09');
  const after = await probe();
  assert.deepEqual(after, before);
  assert.equal(after.top, after.want, 'danh sách phiếu dính ngay dưới tiêu đề cột');
}, world => {
  world.trips.push(...Array.from({ length: 30 }, (_, index) => trip(300 + index, '2026-09-01')));
  world.receipts.push({ id: 1, pid: 'PH-001', date: '2026-09-25', method: 'THU TIỀN', amount_vnd: '5000000', reference: null, voided_by_event: null,
    void_reason: null, allocations: [{ id: 1, month: '2026-09-01', kind: 'debt', amount_vnd: '5000000', superseded_by_event: null }] });
}));

test('Ô tìm khách ở thanh trên như các trang khác: gõ thì hiện danh sách, rời ô thì đóng; sổ đọc lỗi vẫn tìm được khách', async () => withPage(async ({ page }) => {
  const search = page.locator('.topbar #customer-picker.in-bar #customer-search');
  const list = page.locator('#customer-list');
  assert.equal(await search.getAttribute('placeholder'), 'Tìm khách để mở sổ');
  assert.equal(await list.isVisible(), false);
  await search.fill('thu');
  assert.deepEqual(await list.locator('a').allInnerTexts(), ['Khách Thử Sửa']);
  assert.equal(await list.isVisible(), true);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, 'danh sách không tràn mép phải');
  await page.locator('#tab-tinh-hinh').focus();
  assert.equal(await list.isVisible(), false);
  await page.route(/\/api\/v7\/ledger\?/, route => route.abort());
  await page.reload();
  await page.locator('.load-error').waitFor();
  assert.equal(await search.isVisible(), true);
}));

test('Thẻ Sổ ghi số việc chờ, bằng tổng chấm cam trên các chip tháng', async () => withPage(async ({ page }) => {
  const chips = await page.locator('.month-chip .chip-work').allInnerTexts();
  assert.equal(chips.length, 2);
  assert.equal(await page.locator('#tab-so .tab-work').innerText(), String(chips.reduce((sum, text) => sum + Number(text), 0)));
  assert.equal(await page.locator('#tab-so').getAttribute('aria-label'), 'Sổ · 3 việc chờ');
}, world => {
  Object.assign(world.trips[0], { unit_price_vnd: null, amount_vnd: null, is_missing_price: true });
  world.trips.push(trip(41, '2026-09-01', { status: 'pending_review', review_reason: 'WEB_DUPLICATE', amount_vnd: null, editable: false }),
    trip(42, todayMonth, { status: 'pending_review', review_reason: 'WEB_DUPLICATE', amount_vnd: null, editable: false }));
}));
