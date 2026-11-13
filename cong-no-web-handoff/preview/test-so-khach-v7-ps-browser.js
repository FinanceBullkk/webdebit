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
        source_fingerprint: 'c'.repeat(64), ps_field: 'Khác', ps_value: '315789.5', message: 'PS ghi Khác = 315789.5, không phải số đồng nguyên nên máy không đọc' }),
      item({ container: 'DEMU1234567', date: '2026-09-15', target_kind: 'trip', target_id: 11, month: '2026-09', status: 'PS_BAD_AMOUNT', keepable: true,
        source_fingerprint: 'd'.repeat(64), ps_field: 'Khác', ps_value: '315789.5', message: 'PS ghi Khác = 315789.5, không phải số đồng nguyên nên máy không đọc' }),
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

test('phụ phí phát sinh trong ô Khác: nhãn cam, bấm mở hộp nhỏ, cùng khoản trả lời một lần, Đến cont, không đổi tiền', async () => withPage(async ({ page, world, shot }) => {
  await page.waitForSelector('.ps-next');
  const strip = page.locator('.ps-strip');
  assert.match(await strip.innerText(), /3 cont có phụ phí phát sinh cần xem\s*Đến cont tiếp\s*·\s*1 dòng phụ phí phát sinh không gắn chuyến\s*Xem/);
  assert.equal(await page.locator('.ps-review').count(), 0, 'không có khung lớn giữa đầu sổ và bảng chuyến');
  assert.equal(await page.locator('tr.ps-ask-row').count(), 0, 'không chen hàng nào vào bảng chuyến');
  // PS-O-KHAC-01: nhãn nằm trong ô Khác của đúng chuyến.
  const chip = key => page.locator(`[data-row="${key}"] td.fee-other .ps-chip`);
  assert.equal(await chip('legacy-21').innerText(), '315789.5 ?');
  assert.equal(await chip('legacy-22').innerText(), 'chờ tách');
  assert.equal(await chip('trip-11').innerText(), 'Health ? · 2', 'một chuyến hai câu: nhãn ghi số câu');
  await shot('ps-nhan-trong-o-khac');

  // Bấm nhãn chỉ mở hộp, không mở khung chi tiết phụ phí của ô.
  await chip('trip-11').click();
  const pop = page.locator('.ps-pop');
  assert.equal(await page.locator('.fee-other.open').count(), 0, 'khung chi tiết phụ phí không mở');
  const items = await pop.locator('.ps-pop-item').allInnerTexts();
  assert.equal(items.length, 2);
  assert.match(items[0], /Bảng chi phí đánh dấu Health cert[\s\S]*Chuyến này có tính Health cert không\?[\s\S]*Không tính[\s\S]*Có tính: nhập giá Health cert/);
  assert.match(items[1], /Bảng chi phí ghi số lẻ[\s\S]*Ô Khác 315789\.5: không phải số đồng nguyên[\s\S]*Khoản này có tính khách không\?[\s\S]*Trả lời luôn cho OLDU0000001 \(cùng khoản\)[\s\S]*Không tính khách[\s\S]*Tính khách…/);
  assert.equal(await pop.locator('.ps-how').first().isHidden(), true, 'cách làm khi có tính chỉ hiện khi bấm');
  await pop.locator('.ps-yes').click();
  assert.match(await pop.locator('.ps-how').first().innerText(), /Ghi phụ phí \(số đồng nguyên\) trên tab khách ở Sheet/);
  assert.equal(world.requests.length, 0, 'mở hộp, bấm "Tính khách…" không gửi lệnh nào');
  await shot('ps-hop-nho');
  await page.keyboard.press('Escape');
  assert.equal(await pop.count(), 0);
  assert.equal(await page.evaluate(() => document.activeElement?.className), 'ps-chip', 'Esc đưa con trỏ về nhãn');

  // Đến cont: lần lượt từng chuyến, mở hộp, con trỏ vào nút đầu.
  await page.click('.ps-next');
  assert.equal(await page.locator('[data-row="legacy-22"]').evaluate(row => row.classList.contains('ps-flash')), true);
  assert.match(await pop.innerText(), /Chưa tách phụ phí: tháng đang khóa[\s\S]*Mở khóa tháng 9/);
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Mở khóa tháng 9');
  await page.click('.ps-next');
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Không tính');
  await page.click('.ps-next');
  assert.equal(await page.locator('[data-row="legacy-21"]').evaluate(row => row.classList.contains('ps-flash')), true);
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Không tính khách');
  await strip.locator('span').first().click();
  assert.equal(await pop.count(), 0, 'bấm ra ngoài thì đóng');

  const total = await page.locator('.book-head .head-item.total strong').textContent();
  await chip('legacy-21').click();
  await pop.locator('.ps-keep').click();
  await page.waitForFunction(() => /Đã ghi câu trả lời cho 2 cont/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  const keeps = posts(world).filter(([path]) => path === '/api/v7/sheet/tasks/keep').map(([, body]) => body);
  assert.deepEqual(keeps.map(body => [body.task_kind, body.target_kind, body.target_id, body.source_fingerprint]),
    [['ps', 'legacy', 21, 'c'.repeat(64)], ['ps', 'trip', 11, 'd'.repeat(64)]]);
  assert.equal(keeps[1].expected_version, keeps[0].expected_version + 1, 'lệnh sau dùng version mới');
  assert.equal(await pop.count(), 0, 'trả lời xong thì hộp đóng');
  assert.equal(await chip('legacy-21').count(), 0, 'đã trả lời: nhãn mất');
  assert.equal(await chip('trip-11').innerText(), 'Health ?', 'chuyến còn câu Health cert');
  assert.equal(await page.locator('.book-head .head-item.total strong').textContent(), total, 'số nợ không đổi');
  await chip('legacy-22').click();
  await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/v7/months/lock')), pop.locator('.ps-unlock').click()]);
  assert.deepEqual(posts(world).filter(([path]) => path === '/api/v7/months/lock').map(([, body]) => [body.month, body.locked]), [['2026-09-01', false]]);
}, setup));

test('phụ phí phát sinh: bỏ tick cùng khoản thì chỉ trả lời chuyến đang mở; "Có tính" mở chi tiết phụ phí', async () => withPage(async ({ page, world }) => {
  const chip = key => page.locator(`[data-row="${key}"] td.fee-other .ps-chip`);
  await chip('legacy-21').click();
  await page.locator('.ps-pop .ps-group-pick').uncheck();
  await page.locator('.ps-pop .ps-keep').click();
  await page.waitForFunction(() => /Đã ghi câu trả lời cho 1 cont/.test(document.querySelector('.live-notice')?.textContent ?? ''));
  assert.deepEqual(posts(world).filter(([path]) => path === '/api/v7/sheet/tasks/keep').map(([, body]) => [body.target_kind, body.target_id]), [['legacy', 21]]);
  await chip('trip-11').click();
  await page.locator('.ps-pop .ps-fee-open').click();
  assert.equal(await page.locator('.ps-pop').count(), 0);
  await page.waitForFunction(() => document.querySelector('.fee-other.open[data-fee-target]'));
}, setup));

test('phụ phí phát sinh ở tháng khác: Đến cont mở đúng tháng, hộp có ba số', async () => withPage(async ({ page }) => {
  await page.waitForSelector('.ps-next');
  assert.equal(await page.locator('.ps-chip').count(), 0, 'tháng đang xem không có nhãn');
  assert.equal(await page.locator('.ps-next').innerText(), 'Đến cont');
  await page.click('.ps-next');
  await page.waitForSelector('[data-row="trip-11"] .ps-chip');
  assert.equal(await page.locator('[data-row="trip-11"] .ps-chip').innerText(), '+315.789');
  assert.match(await page.locator('.ps-pop').innerText(),
    /ABCU1000099 · 15\/09\/2026[\s\S]*Phụ phí phát sinh chưa tính khách\s*Bảng chi phí ghi\s*315\.789 đ\s*Sổ khách đang tính\s*0 đ\s*Chênh\s*\+315\.789 đ[\s\S]*Không tính khách\s*Tính khách…/);
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Không tính khách');
}, world => {
  world.month = clock.slice(0, 7);   // tháng hiện tại; chuyến có câu hỏi ở tháng 9
  world.psFees = { snapshot_sha256: sha, ready_count: 0, review_count: 1, ready: [], review: [
    item({ container: 'ABCU1000099', date: '2026-09-15', target_kind: 'trip', target_id: 11, month: '2026-09', status: 'WEB_NO_FEE', keepable: true,
      ps_total: '315789', source_fingerprint: 'f'.repeat(64), message: 'PS ghi 315.789 đ phụ phí, sổ khách chưa thu' })] };
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
