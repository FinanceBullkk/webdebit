/* Trình duyệt (Playwright) cho tách phụ phí theo bảng PS (specs/v7-phu-phi-tu-ps.md, PR-2). Máy chủ giả, số giả, không chạm DB. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { clock, withPage, posts } = require('./so-khach-v7-browser-world');

const sha = 'b'.repeat(64);
const item = (fields) => ({ key: `${fields.container}|${fields.date}`, source_row: 3, bill_month: '09/2026', ps_source: 'PS T9',
  ps_total: null, web_total: null, before: [], after: [], message: '', ...fields });
// Sổ bật ba cột riêng Neo, Điện, Ghép. Chuyến web 11 và dòng sổ gốc 22 tách được; năm dòng cần trả lời.
function setup(world) {
  world.feeColumns = [1, 2, 3];
  world.trips[0].fee_lines = [{ id: 601, fee_type_id: 9, amount_vnd: '2000000', note: null }];
  Object.assign(world.trips[0], { other_fee_vnd: '2000000', amount_vnd: '52000000' });
  world.psFees = { snapshot_sha256: sha, ready_count: 2, review_count: 5,
    ready: [
      item({ container: 'DEMU1234567', date: '2026-09-15', target_kind: 'trip', target_id: 11, month: '2026-09', status: 'READY',
        before: [{ id: 601, fee_type_id: 9, amount_vnd: '2000000', note: null }],
        after: [{ fee_type_id: 1, amount_vnd: '1500000', note: null }, { fee_type_id: 2, amount_vnd: '500000', note: null }] }),
      item({ container: 'OLDU0000002', date: '2026-09-03', target_kind: 'legacy', target_id: 22, month: '2026-09', status: 'READY',
        before: [{ id: 501, fee_type_id: 9, amount_vnd: '3000000', note: null }], after: [{ fee_type_id: 3, amount_vnd: '3000000', note: null }] })],
    review: [
      item({ container: 'OLDU0000002', date: '2026-09-03', target_kind: 'legacy', target_id: 22, month: '2026-09', status: 'MONTH_LOCKED', message: 'Tháng 09/2026 đang khóa' }),
      item({ container: 'DEMU1234567', date: '2026-09-15', target_kind: 'trip', target_id: 11, month: '2026-09', status: 'NEED_HEALTH', keepable: true, source_fingerprint: 'e'.repeat(64), message: 'PS đánh dấu Health cert — nhập giá tay' }),
      item({ container: 'OLDU0000001', date: '2026-09-02', target_kind: 'legacy', target_id: 21, month: '2026-09', status: 'PS_BAD_AMOUNT', keepable: true,
        source_fingerprint: 'c'.repeat(64), message: 'PS ghi Khác = 315789.5, không phải số đồng nguyên nên máy không đọc' }),
      item({ container: 'DEMU1234567', date: '2026-09-15', target_kind: 'trip', target_id: 11, month: '2026-09', status: 'PS_BAD_AMOUNT', keepable: true,
        source_fingerprint: 'd'.repeat(64), message: 'PS ghi Khác = 315789.5, không phải số đồng nguyên nên máy không đọc' }),
      item({ container: 'DEMU0900009', date: '2026-09-25', target_kind: '', target_id: '', month: '', status: 'PS_SOURCE_ERROR', message: 'Bộ lập bill báo lỗi: PS trùng dòng' })] };
}
const ownCells = async (page, row) => page.locator(`[data-row="${row}"] td.fee.own`).allInnerTexts();

test('tách PS: nút đúng số, khung xác nhận "Tổng tiền không đổi", tách xong ô cột riêng có số và Thành tiền giữ nguyên', async () => withPage(async ({ page, world, shot }) => {
  await page.waitForSelector('.ps-approve');
  assert.equal(await page.locator('.ps-approve').innerText(), 'Tách 2 phụ phí theo bảng PS');
  assert.equal(await page.locator('[data-row="trip-11"]').evaluate(row => row.classList.contains('ps-ready')), true);
  assert.match(await page.locator('[data-row="trip-11"]').innerText(), /52\.000\.000/);
  await shot('ps-co-chuyen-tach-duoc');

  await page.click('.ps-approve');
  const panel = page.locator('.ps-panel.confirm');
  const text = await panel.innerText();
  assert.match(text, /Tách phụ phí theo bảng PS cho 2 chuyến tháng 9\/2026\?/);
  assert.match(text, /DEMU1234567 · 15\/09\/2026 · Phụ phí ban đầu 2\.000\.000\s*→\s*Neo 1\.500\.000 \+ Điện 500\.000/);
  assert.match(text, /OLDU0000002 · 03\/09\/2026 · Phụ phí ban đầu 3\.000\.000\s*→\s*Ghép 3\.000\.000/);
  assert.match(text, /Tổng tiền không đổi: phụ phí 2 chuyến vẫn là 5\.000\.000 đ, tổng còn nợ giữ nguyên\./);
  assert.equal(await page.evaluate(() => document.activeElement?.className), 'ps-write primary', 'con trỏ ở nút Tách');
  assert.deepEqual(await ownCells(page, 'trip-11'), ['1.500.000', '500.000', ''], 'ô hiện kết quả dự kiến');
  assert.equal(await page.locator('.ps-approve').count(), 0);
  assert.equal(world.requests.length, 0, 'mở khung chưa gửi lệnh');
  await shot('ps-khung-xac-nhan');
  await page.click('.ps-cancel');
  assert.equal(await panel.count(), 0);
  assert.deepEqual(await ownCells(page, 'trip-11'), ['', '', ''], 'Thôi thì ô về như cũ');

  await page.click('.ps-approve');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => /Đã tách phụ phí 2 chuyến theo bảng PS\. Tổng tiền không đổi/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const [[path, body]] = posts(world);
  assert.equal(path, '/api/v7/ps/fees');
  assert.deepEqual(Object.keys(body).sort(), ['customer_id', 'expected_version', 'idempotency_key', 'snapshot_sha256']);
  assert.deepEqual([body.customer_id, body.expected_version, body.snapshot_sha256], [1, 1, sha]);
  assert.deepEqual(await ownCells(page, 'trip-11'), ['1.500.000', '500.000', '']);
  assert.deepEqual(await ownCells(page, 'legacy-22'), ['', '', '3.000.000']);
  assert.match(await page.locator('[data-row="trip-11"]').innerText(), /52\.000\.000/, 'Thành tiền không đổi');
  assert.equal(await page.locator('[data-row="trip-11"]').evaluate(row => row.classList.contains('ps-done')), true);
  assert.equal(await page.locator('.ps-approve').count(), 0);
  await shot('ps-da-tach');
}, setup));

test('PS cần trả lời tại hàng: câu hỏi dưới hàng chuyến, cùng khoản một nút cho cả nhóm, Đến dòng, hết báo không đổi tiền', async () => withPage(async ({ page, world, shot }) => {
  await page.waitForSelector('.ps-next');
  const strip = page.locator('.ps-strip');
  assert.match(await strip.innerText(), /Phụ phí PS cần trả lời:\s*5\s*Đến dòng tiếp\s*·\s*1 dòng không gắn chuyến\s*Xem/);
  assert.equal(await page.locator('.ps-review').count(), 0, 'không còn khung lớn giữa đầu sổ và bảng chuyến');
  // PS-TAI-HANG-01: hàng câu hỏi nằm ngay sau hàng chuyến của nó.
  const after = key => page.evaluate(key => document.querySelector(`[data-row="${key}"]`).nextElementSibling?.dataset.psRow, key);
  assert.deepEqual([await after('legacy-21'), await after('legacy-22'), await after('trip-11')], ['legacy-21', 'legacy-22', 'trip-11']);
  const ask = key => page.locator(`tr.ps-ask-row[data-ps-row="${key}"]`);
  const trip = await ask('trip-11').locator('.ps-ask-line').allInnerTexts();
  assert.equal(trip.length, 2, 'một chuyến hai câu: hai dòng trong cùng hàng hỏi');
  assert.match(trip[0], /PS đánh dấu Health cert[\s\S]*Chuyến này có tính Health cert không\?[\s\S]*Không tính, hết báo[\s\S]*thêm khoản Health cert/);
  assert.match(trip[1], /Khác = 315789\.5[\s\S]*cùng khoản với OLDU0000001[\s\S]*Khoản này có thu khách không\?[\s\S]*Không thu, hết báo \(2 cont\)/);
  assert.match(await ask('legacy-21').innerText(), /cùng khoản với DEMU1234567[\s\S]*Không thu, hết báo \(2 cont\)/);
  assert.match(await ask('legacy-22').innerText(), /Tháng 09\/2026 đang khóa[\s\S]*Mở khóa tháng 9[\s\S]*Máy tự tách ở lượt chạy sau/);
  await page.click('.ps-review-toggle');
  assert.match(await page.locator('.ps-review').innerText(), /DEMU0900009 · 25\/09\/2026 · Bộ lập bill báo lỗi: PS trùng dòng/);
  await page.click('.ps-review-toggle');
  assert.equal(await page.locator('.ps-review').count(), 0);
  await shot('ps-can-tra-loi-tai-hang');

  await page.click('.ps-next');
  assert.equal(await page.locator('[data-row="legacy-22"]').evaluate(row => row.classList.contains('ps-flash')), true);
  assert.equal(await page.evaluate(() => document.activeElement?.className), 'ps-unlock', 'con trỏ vào nút của hàng đó');
  await page.click('.ps-next');
  assert.equal(await page.locator('[data-row="trip-11"]').evaluate(row => row.classList.contains('ps-flash')), true);
  assert.equal(await page.evaluate(() => document.activeElement?.closest('tr')?.dataset.psRow), 'trip-11');

  const total = await page.locator('.book-head .head-item.total strong').textContent();
  await ask('legacy-21').locator('.ps-keep').click();
  await page.waitForFunction(() => /Đã ghi câu trả lời cho 2 cont/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const keeps = posts(world).filter(([path]) => path === '/api/v7/sheet/tasks/keep').map(([, body]) => body);
  assert.deepEqual(keeps.map(body => [body.task_kind, body.target_kind, body.target_id, body.source_fingerprint]),
    [['ps', 'legacy', 21, 'c'.repeat(64)], ['ps', 'trip', 11, 'd'.repeat(64)]]);
  assert.equal(keeps[1].expected_version, keeps[0].expected_version + 1, 'lệnh sau dùng version mới');
  assert.match(await strip.innerText(), /Phụ phí PS cần trả lời:\s*3/);
  assert.equal(await ask('legacy-21').count(), 0, 'đã trả lời: hàng hỏi mất');
  assert.equal(await ask('trip-11').locator('.ps-ask-line').count(), 1, 'chuyến còn câu Health cert');
  assert.equal(await page.locator('.book-head .head-item.total strong').textContent(), total, 'tiền không đổi');
  await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/v7/months/lock')), ask('legacy-22').locator('.ps-unlock').click()]);
  assert.deepEqual(posts(world).filter(([path]) => path === '/api/v7/months/lock').map(([, body]) => [body.month, body.locked]), [['2026-09-01', false]]);
}, setup));

test('PS cần trả lời ở tháng khác: Đến dòng mở đúng tháng rồi tới hàng', async () => withPage(async ({ page }) => {
  await page.waitForSelector('.ps-next');
  assert.equal(await page.locator('tr.ps-ask-row').count(), 0, 'tháng đang xem không có câu hỏi');
  assert.equal(await page.locator('.ps-next').innerText(), 'Đến dòng');
  await page.click('.ps-next');
  await page.waitForSelector('tr.ps-ask-row[data-ps-row="trip-11"]');
  assert.equal(await page.locator('[data-row="trip-11"]').evaluate(row => row.classList.contains('ps-flash')), true);
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Không thu, hết báo');
}, world => {
  world.month = clock.slice(0, 7);   // tháng hiện tại; chuyến có câu hỏi ở tháng 9
  world.psFees = { snapshot_sha256: sha, ready_count: 0, review_count: 1, ready: [], review: [
    item({ container: 'DEMU1234567', date: '2026-09-15', target_kind: 'trip', target_id: 11, month: '2026-09', status: 'WEB_NO_FEE', keepable: true,
      source_fingerprint: 'f'.repeat(64), message: 'PS ghi 315.789 đ phụ phí, sổ khách chưa thu' })] };
}));

test('bảng PS đổi sau khi mở sổ: không tách chuyến nào, Tải lại sổ', async () => withPage(async ({ page, world }) => {
  await page.click('.ps-approve');
  await page.click('.ps-write');
  const panel = page.locator('.ps-panel.err');
  await panel.waitFor();
  assert.match(await panel.innerText(), /Chưa tách chuyến nào\. Bảng PS đã đổi sau khi mở sổ\. Tải lại rồi tách\./);
  assert.deepEqual(await ownCells(page, 'trip-11'), ['', '', '']);
  const reads = world.reads;
  await panel.locator('.ps-reload').click();
  await page.waitForFunction(() => !document.querySelector('.ps-panel.err'));
  assert.ok(world.reads > reads);
}, world => { setup(world); world.psStale = true; }));

test('chưa đọc được bảng PS: sổ vẫn dùng, nút tách ẩn', async () => withPage(async ({ page }) => {
  await page.waitForSelector('.ps-unavailable');
  assert.match(await page.locator('.price-strip').innerText(), /Chưa đọc được bảng PS; nút tách phụ phí tạm ẩn/);
  assert.equal(await page.locator('.ps-approve').count(), 0);
}, world => { world.psFees = { unavailable: true, ready: [], review: [], ready_count: 0, review_count: 0 }; }));
