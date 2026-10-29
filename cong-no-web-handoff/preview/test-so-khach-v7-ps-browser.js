/* Trình duyệt (Playwright) cho tách phụ phí theo bảng PS (specs/v7-phu-phi-tu-ps.md, PR-2). Máy chủ giả, số giả, không chạm DB. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { withPage, posts } = require('./so-khach-v7-browser-world');

const sha = 'b'.repeat(64);
const item = (fields) => ({ key: `${fields.container}|${fields.date}`, source_row: 3, bill_month: '09/2026', ps_source: 'PS T9',
  ps_total: null, web_total: null, before: [], after: [], message: '', ...fields });
// Sổ bật ba cột riêng Neo, Điện, Ghép. Chuyến web 11 và dòng sổ gốc 22 tách được; bốn dòng cần xem.
function setup(world) {
  world.feeColumns = [1, 2, 3];
  world.trips[0].fee_lines = [{ id: 601, fee_type_id: 9, amount_vnd: '2000000', note: null }];
  Object.assign(world.trips[0], { other_fee_vnd: '2000000', amount_vnd: '52000000' });
  world.psFees = { snapshot_sha256: sha, ready_count: 2, review_count: 4,
    ready: [
      item({ container: 'DEMU1234567', date: '2026-09-15', target_kind: 'trip', target_id: 11, month: '2026-09', status: 'READY',
        before: [{ id: 601, fee_type_id: 9, amount_vnd: '2000000', note: null }],
        after: [{ fee_type_id: 1, amount_vnd: '1500000', note: null }, { fee_type_id: 2, amount_vnd: '500000', note: null }] }),
      item({ container: 'OLDU0000002', date: '2026-09-03', target_kind: 'legacy', target_id: 22, month: '2026-09', status: 'READY',
        before: [{ id: 501, fee_type_id: 9, amount_vnd: '3000000', note: null }], after: [{ fee_type_id: 3, amount_vnd: '3000000', note: null }] })],
    review: [
      item({ container: 'DEMU0800001', date: '2026-08-20', target_kind: 'trip', target_id: 99, month: '2026-08', status: 'MONTH_LOCKED', message: 'Tháng 08/2026 đang khóa' }),
      item({ container: 'DEMU1234567', date: '2026-09-15', target_kind: 'trip', target_id: 11, month: '2026-09', status: 'NEED_HEALTH', message: 'PS đánh dấu Health cert — nhập giá tay' }),
      item({ container: 'OLDU0000001', date: '2026-09-02', target_kind: 'legacy', target_id: 21, month: '2026-09', status: 'WEB_NO_FEE', message: 'PS 1.200.000 đ · web chưa có phụ phí' }),
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

test('PS cần xem: chia nhóm theo việc phải làm, mở khóa tháng, Xem dòng chỉ khi chuyến có trên sổ', async () => withPage(async ({ page, world, shot }) => {
  await page.waitForSelector('.ps-review-toggle');
  assert.match(await page.locator('.price-strip').innerText(), /Phụ phí PS cần xem:\s*4/);
  await page.click('.ps-review-toggle');
  const panel = page.locator('.ps-review');
  assert.deepEqual(await panel.locator('h3').allInnerTexts(), ['Mở khóa tháng là tách được',
    'Sửa trên web (bấm ô Khác của chuyến để mở chi tiết phụ phí)', 'Sửa ở Sheet hoặc bộ lập bill (lần đọc sau tự cập nhật)']);
  const items = await panel.locator('li').allInnerTexts();
  assert.match(items[0], /DEMU0800001 · 20\/08\/2026 · Tháng 08\/2026 đang khóa/);
  assert.match(items[1], /PS đánh dấu Health cert — nhập giá tay[\s\S]*Thêm khoản Health cert/);
  assert.match(items[2], /web chưa có phụ phí[\s\S]*Ghi phí trên tab khách/);
  assert.match(items[3], /Bộ lập bill báo lỗi: PS trùng dòng[\s\S]*Sửa trong bộ lập bill/);
  assert.equal(await panel.locator('li').nth(0).locator('.ps-jump').count(), 0, 'chuyến không có trên sổ: không có Xem dòng');
  assert.equal(await panel.locator('li').nth(3).locator('.ps-jump').count(), 0);
  await shot('ps-can-xem');
  await panel.locator('li').nth(2).locator('.ps-jump').click();
  assert.equal(await page.locator('[data-row="legacy-21"]').evaluate(row => row.classList.contains('ps-flash')), true);
  await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/v7/months/lock')), panel.locator('.ps-unlock').click()]);
  assert.deepEqual(posts(world).map(([path, body]) => [path, body.month, body.locked]), [['/api/v7/months/lock', '2026-08-01', false]]);
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
