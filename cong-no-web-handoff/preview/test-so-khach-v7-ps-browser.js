/* Trình duyệt (Playwright) cho tách phụ phí theo bảng PS (specs/v7-phu-phi-tu-ps.md, PR-2). Máy chủ giả, số giả, không chạm DB. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { withPage, posts } = require('./so-khach-v7-browser-world');

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
      item({ container: 'DEMU0800001', date: '2026-08-20', target_kind: 'trip', target_id: 99, month: '2026-08', status: 'MONTH_LOCKED', message: 'Tháng 08/2026 đang khóa' }),
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

test('PS cần trả lời: mỗi câu một nút, cùng câu gom một nút cho cả nhóm, hết báo không đổi tiền', async () => withPage(async ({ page, world, shot }) => {
  await page.waitForSelector('.ps-review-toggle');
  assert.match(await page.locator('.price-strip').innerText(), /Phụ phí PS cần trả lời:\s*5/);
  await page.click('.ps-review-toggle');
  const panel = page.locator('.ps-review');
  assert.match(await panel.locator('.ps-intro').innerText(), /Tiền trên web chưa đổi/);
  const asks = await panel.locator('.ps-ask').allInnerTexts();
  assert.equal(asks.length, 2);
  assert.match(asks[0], /PS đánh dấu Health cert[\s\S]*Chuyến này có tính Health cert không\?[\s\S]*Không tính, hết báo[\s\S]*thêm khoản Health cert/);
  assert.match(asks[1], /Khác = 315789\.5[\s\S]*· 2 cont[\s\S]*OLDU0000001[\s\S]*DEMU1234567[\s\S]*Khoản này có thu khách không\?[\s\S]*Không thu, hết báo \(2 cont\)/);
  const rest = await panel.locator('h3 + ul li').allInnerTexts();
  assert.match(rest[0], /DEMU0800001 · 20\/08\/2026 · Tháng 08\/2026 đang khóa[\s\S]*Máy tự tách ở lượt chạy sau/);
  assert.match(rest[1], /Bộ lập bill báo lỗi: PS trùng dòng/);
  assert.equal(await panel.locator('h3 + ul li').nth(0).locator('.ps-jump').count(), 0, 'chuyến không có trên sổ: không có Xem dòng');
  await shot('ps-can-tra-loi');
  await panel.locator('.ps-ask').nth(1).locator('.ps-jump').first().click();
  assert.equal(await page.locator('[data-row="legacy-21"]').evaluate(row => row.classList.contains('ps-flash')), true);
  const total = await page.locator('.book-head .head-item.total strong').textContent();
  await panel.locator('.ps-ask').nth(1).locator('.ps-keep').click();
  await page.waitForFunction(() => /Đã ghi câu trả lời cho 2 cont/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const keeps = posts(world).filter(([path]) => path === '/api/v7/sheet/tasks/keep').map(([, body]) => body);
  assert.deepEqual(keeps.map(body => [body.task_kind, body.target_kind, body.target_id, body.source_fingerprint]),
    [['ps', 'legacy', 21, 'c'.repeat(64)], ['ps', 'trip', 11, 'd'.repeat(64)]]);
  assert.equal(keeps[1].expected_version, keeps[0].expected_version + 1, 'lệnh sau dùng version mới');
  assert.match(await page.locator('.price-strip').innerText(), /Phụ phí PS cần trả lời:\s*3/);
  assert.equal(await page.locator('.book-head .head-item.total strong').textContent(), total, 'tiền không đổi');
  await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/v7/months/lock')), page.locator('.ps-unlock').click()]);
  assert.deepEqual(posts(world).filter(([path]) => path === '/api/v7/months/lock').map(([, body]) => [body.month, body.locked]), [['2026-08-01', false]]);
}, setup));

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
