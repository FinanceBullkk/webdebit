/* Trình duyệt (Playwright) cho "Một lần chuyển cho nhiều sổ" (PHIEU-WEB-01 mục 2): chia tổng chuyển cho các sổ, chặn khi tổng các
 * phần lệch, mỗi sổ một lệnh ghi phiếu có khóa riêng, lỗi giữa chừng thì Ghi tiếp chỉ gửi phần chưa ghi, cảnh báo tham chiếu đã dùng
 * ở sổ khác. Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { clock, withPage, reload, posts, settled } = require('./so-khach-v7-browser-world');

const today = `${clock.slice(8, 10)}/${clock.slice(5, 7)}/${clock.slice(0, 4)}`;
const split = page => page.locator('.split-drawer');
const receiptPosts = world => posts(world).filter(([path]) => path === '/api/v7/receipts').map(([, body]) => body);
const setup = world => {
  world.total = '40000000';
  world.customers = [{ id: 1, name: 'Khách Thử Sửa', status: 'active' }, { id: 2, name: 'Khách Hai', status: 'active' },
    { id: 3, name: 'Khách Ba', status: 'active' }, { id: 4, name: 'Khách Cũ', status: 'active', archived: true }];
  world.books = { 2: { version: 7, total: '25000000' }, 3: { version: 3, total: '0' } };
};
// Từ khung Ghi phiếu thu đã gõ ngày, tổng và tham chiếu: mở khung chia, thêm "Khách Hai".
async function openWithTwo(page) {
  await page.locator('.entry-open').click();
  await page.locator('.entry-drawer .receipt-date').fill(today);
  await page.locator('.entry-drawer .receipt-amount').fill('50.000.000');
  await page.locator('.entry-drawer .receipt-reference').fill('UNC 777');
  await page.locator('.entry-drawer .entry-split').click();
  await split(page).locator('.split-form').waitFor();
  await split(page).locator('.split-add').click();
  await split(page).locator('.split-search').fill('hai');
  await split(page).locator('.split-option').first().waitFor();
  await split(page).locator('.split-search').press('Enter');
}

test('Chia một lần chuyển cho hai sổ: mang chữ đã gõ sang, chặn khi tổng lệch, xem lại từng sổ, mỗi sổ một phiếu', async () => withPage(async ({ page, world, shot }) => {
  world.receiptBook = { days: [{ date: clock, rows: [{ source: 'web', pid: 'PH-009', customer_id: 3, name: 'Khách Ba', amount_vnd: '5000000', date: clock, note: 'UNC 777' }] }], undated: [] };
  await openWithTwo(page);
  assert.equal(await page.locator('.entry-drawer').isHidden(), true, 'khung Ghi phiếu thu đóng khi mở khung chia');
  assert.equal(await split(page).locator('.split-date').inputValue(), today);
  assert.equal(await split(page).locator('.split-total').inputValue(), '50.000.000');
  assert.equal(await split(page).locator('.split-reference').inputValue(), 'UNC 777');
  assert.deepEqual(await split(page).locator('.split-row .entry-field span').allInnerTexts(), ['Khách Thử Sửa', 'Khách Hai']);
  assert.equal(await page.evaluate(() => document.activeElement?.dataset.index), '1', 'chọn sổ xong thì tiêu điểm ở ô tiền của sổ đó');
  // Sổ lưu trữ và sổ đã có trong danh sách không hiện để chọn.
  await split(page).locator('.split-add').click();
  assert.deepEqual(await split(page).locator('.split-option').allInnerTexts(), ['Khách Ba']);
  await page.keyboard.press('Escape');
  await split(page).locator('.split-amount[data-index="0"]').fill('30000000');
  await split(page).locator('.split-amount[data-index="1"]').fill('15.000.000');
  assert.equal(await split(page).locator('.split-progress').innerText(), 'Đã chia 45.000.000 / 50.000.000 đ · còn 5.000.000 đ.');
  await split(page).locator('.split-amount[data-index="1"]').press('Enter');
  assert.match(await split(page).locator('.split-error').innerText(), /khác tổng chuyển 50\.000\.000 đ: còn thiếu 5\.000\.000 đ/);
  await split(page).locator('.split-amount[data-index="1"]').fill('20.000.000');
  assert.equal(await split(page).locator('.split-progress').innerText(), 'Đã chia đủ 50.000.000 đ.');
  assert.equal(await split(page).locator('.split-error').innerText(), '', 'sửa số thì câu lỗi tổng lệch cũ tắt');
  await shot('chia-nhieu-so-nhap');
  await split(page).locator('.split-amount[data-index="1"]').press('Enter');
  const review = split(page).locator('.split-review');
  await review.waitFor();
  const text = await review.innerText();
  assert.ok(text.includes(`Ghi 2 phiếu, tổng 50.000.000 đ · THU TIỀN · ngày ${today}`));
  assert.match(text, /Khách Thử Sửa: 30\.000\.000 đ · còn nợ 40\.000\.000 → 10\.000\.000 đ/);
  assert.match(text, /Khách Hai: 20\.000\.000 đ · còn nợ 25\.000\.000 → 5\.000\.000 đ/);
  assert.match(text, /Tham chiếu \(cả 2 phiếu\): UNC 777/);
  assert.match(text, /Tham chiếu này đã có ở sổ Khách Ba \(PH-009, 5\.000\.000 đ/);
  await settled(page);
  assert.equal(receiptPosts(world).length, 0, 'xem lại chưa gửi lệnh nào');
  await shot('chia-nhieu-so-xem-lai');
  await split(page).locator('.split-save').click();
  await split(page).waitFor({ state: 'hidden' });
  await settled(page);
  const sent = receiptPosts(world);
  assert.deepEqual(sent.map(body => [body.customer_id, body.amount_vnd, body.date, body.reference, body.method]),
    [[1, '30000000', clock, 'UNC 777', 'THU TIỀN'], [2, '20000000', clock, 'UNC 777', 'THU TIỀN']]);
  assert.equal(sent[1].expected_version, 7);
  assert.notEqual(sent[0].idempotency_key, sent[1].idempotency_key, 'mỗi sổ một khóa chống trùng');
  assert.match(await page.locator('.cn-toast-text').innerText(), /Đã ghi 2 phiếu, tổng 50\.000\.000 đ: Khách Thử Sửa PH-001 30\.000\.000 đ; Khách Hai PH-B1 20\.000\.000 đ\./);
}, setup));

test('Lỗi giữa chừng: dừng, báo phần đã ghi; Ghi tiếp chỉ gửi phần chưa ghi, cùng khóa nên không thành hai phiếu', async () => withPage(async ({ page, world }) => {
  await openWithTwo(page);
  await split(page).locator('.split-add').click();
  await split(page).locator('.split-search').fill('ba');
  await split(page).locator('.split-search').press('Enter');
  await split(page).locator('.split-amount[data-index="0"]').fill('10.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('20.000.000');
  await split(page).locator('.split-amount[data-index="2"]').fill('20.000.000');
  await split(page).locator('.split-next').click();
  await split(page).locator('.split-review').waitFor();
  // Sổ thứ hai: máy chủ lưu rồi mất kết nối (chưa rõ); sổ thứ ba chưa gửi.
  world.books[2].dropNext = true;
  await split(page).locator('.split-save').click();
  await split(page).locator('.split-review .split-st-unknown').waitFor();
  let text = await split(page).locator('.split-review').innerText();
  assert.match(text, /Khách Thử Sửa: 10\.000\.000[^\n]*Đã ghi PH-001/);
  assert.match(text, /Khách Hai: 20\.000\.000[^\n]*Chưa rõ đã lưu/);
  assert.match(text, /Khách Ba:[^\n]*Chưa ghi/);
  assert.equal(await split(page).locator('.split-fix[data-index="2"]').inputValue(), '20.000.000');
  assert.match(text, /Còn 2 phiếu chưa ghi/);
  assert.equal(await split(page).locator('.split-save').innerText(), 'Ghi tiếp 2 phiếu');
  // Sổ thứ ba vừa đổi (người khác ghi): trang đọc phiên bản mới rồi gửi lại cùng khóa.
  world.books[3].version += 1;
  await split(page).locator('.split-save').click();
  await split(page).waitFor({ state: 'hidden' });
  await settled(page);
  const sent = receiptPosts(world);
  assert.deepEqual(sent.map(body => body.customer_id), [1, 2, 2, 3, 3], 'sổ đang mở không gửi lại; sổ Hai gửi lại đúng khóa cũ; sổ Ba gửi lại sau khi sổ đổi');
  assert.equal(sent[1].idempotency_key, sent[2].idempotency_key);
  assert.equal(world.books[2].receipts.length, 1, 'gửi lại cùng khóa không thành hai phiếu');
  assert.equal(world.books[3].receipts.length, 1);
  assert.equal(world.receipts.length, 1);
  // Lỗi dứt khoát (bị từ chối): báo câu của máy chủ ở đúng dòng, không gửi các sổ sau.
  await openWithTwo(page);
  await split(page).locator('.split-amount[data-index="0"]').fill('25.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('25.000.000');
  await split(page).locator('.split-next').click();
  await split(page).locator('.split-review').waitFor();
  world.failNext = { error: 'INVALID_RECEIPT', message: 'Phiếu không hợp lệ.' };
  await split(page).locator('.split-save').click();
  await split(page).locator('.split-review .split-st-error').waitFor();
  text = await split(page).locator('.split-review').innerText();
  assert.match(text, /Khách Thử Sửa:[^\n]*Không ghi được\s*Phiếu không hợp lệ\./);
  assert.match(text, /Khách Hai:[^\n]*Chưa ghi/);
  assert.equal(await split(page).locator('.split-fix[data-index="0"]').inputValue(), '25.000.000', 'phần bị từ chối sửa được số');
  assert.equal(receiptPosts(world).length, 6, 'dừng ở sổ lỗi, sổ sau chưa gửi');
}, setup));

test('Đóng khi còn phiếu chưa ghi: hỏi trước, giữ lần chia dở; mở lại ghi tiếp; phần bị từ chối sửa số với khóa mới', async () => withPage(async ({ page, world, shot }) => {
  await openWithTwo(page);
  await split(page).locator('.split-add').click();
  await split(page).locator('.split-search').fill('ba');
  await split(page).locator('.split-search').press('Enter');
  await split(page).locator('.split-amount[data-index="0"]').fill('20.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('15.000.000');
  await split(page).locator('.split-amount[data-index="2"]').fill('15.000.000');
  await split(page).locator('.split-next').click();
  await split(page).locator('.split-review').waitFor();
  world.books[2].failNext = { error: 'INVALID_RECEIPT', message: 'Phiếu không hợp lệ.' };
  await split(page).locator('.split-save').click();
  await split(page).locator('.split-review .split-st-error').waitFor();
  // Đóng: hỏi, không bỏ. "Đóng, ghi sau" giữ nguyên; mở lại từ khung Ghi phiếu thu thì về đúng bước kết quả.
  await split(page).locator('.split-review .split-close').click();
  const ask = split(page).locator('.split-ask');
  assert.match(await ask.innerText(), /Còn 2 phiếu chưa ghi\. Đóng thì giữ nguyên/);
  assert.equal(await ask.locator('.split-drop').innerText(), 'Bỏ 2 phiếu chưa ghi');
  await shot('chia-nhieu-so-dong-hoi');
  await ask.locator('.split-stop').click();
  assert.equal(await split(page).isHidden(), true);
  await page.locator('.entry-open').click();
  await page.locator('.entry-drawer .entry-split').click();
  const text = await split(page).locator('.split-review').innerText();
  assert.match(text, /Khách Thử Sửa: 20\.000\.000[^\n]*Đã ghi PH-001/);
  assert.match(text, /Khách Hai:[^\n]*Không ghi được/);
  // Sửa số: tổng phải vẫn bằng tổng chuyển; phần đổi số nhận khóa mới, phần đã ghi không gửi lại.
  await split(page).locator('.split-fix[data-index="1"]').fill('10.000.000');
  await split(page).locator('.split-save').click();
  assert.match(await split(page).locator('.split-fix-error').innerText(), /Tổng các phần 45\.000\.000 đ khác tổng chuyển 50\.000\.000 đ\./);
  await split(page).locator('.split-fix[data-index="2"]').fill('20.000.000');
  await split(page).locator('.split-save').click();
  await split(page).waitFor({ state: 'hidden' });
  await settled(page);
  const sent = receiptPosts(world);
  assert.deepEqual(sent.map(body => [body.customer_id, body.amount_vnd]), [[1, '20000000'], [2, '15000000'], [2, '10000000'], [3, '20000000']]);
  assert.notEqual(sent[1].idempotency_key, sent[2].idempotency_key, 'phần đổi số là lệnh mới');
  assert.equal(world.receipts.length, 1, 'sổ đã ghi không bị ghi lần hai');
  assert.deepEqual([world.books[2].receipts.length, world.books[3].receipts.length], [1, 1]);
}, setup));

test('Đóng khi có phiếu chưa rõ đã lưu: không có nút bỏ; thiếu tham chiếu thì nhắc ở bước xem lại', async () => withPage(async ({ page, world }) => {
  await openWithTwo(page);
  await split(page).locator('.split-reference').fill('');
  await split(page).locator('.split-amount[data-index="0"]').fill('25.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('25.000.000');
  await split(page).locator('.split-next').click();
  await split(page).locator('.split-review').waitFor();
  assert.match(await split(page).locator('.split-review').innerText(), /Chưa có tham chiếu\. Nên ghi mã giao dịch ngân hàng/);
  world.books[2].dropNext = true;
  await split(page).locator('.split-save').click();
  await split(page).locator('.split-review .split-st-unknown').waitFor();
  assert.equal(await split(page).locator('.split-fix').count(), 0, 'phần chưa rõ không sửa số: phải gửi lại đúng lệnh cũ');
  await split(page).locator('.split-review .split-close').click();
  assert.equal(await split(page).locator('.split-ask .split-drop').count(), 0);
  await split(page).locator('.split-ask .split-stay').click();
  await split(page).locator('.split-save').click();
  await split(page).waitFor({ state: 'hidden' });
  assert.equal(world.books[2].receipts.length, 1);
}, setup));

test('Chặn tại chỗ: ngày sau hôm nay, thiếu tổng, chỉ một sổ, phần trống; Esc lần lượt đóng ô tìm, khung', async () => withPage(async ({ page, world }) => {
  await page.locator('.entry-open').click();
  await page.locator('.entry-drawer .entry-split').click();
  await split(page).locator('.split-form').waitFor();   // mở khung chờ khóa tab (navigator.locks)
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('split-date')), true);
  await split(page).locator('.split-date').fill('01/01/2099');
  await split(page).locator('.split-next').click();
  assert.equal(await split(page).locator('.split-date-error').innerText(), 'Ngày trả không được sau hôm nay.');
  await split(page).locator('.split-date').fill(today);
  await split(page).locator('.split-next').click();
  assert.equal(await split(page).locator('.split-total-error').innerText(), 'Nhập tổng tiền khách chuyển.');
  await split(page).locator('.split-total').fill('1.000.000');
  await split(page).locator('.split-amount[data-index="0"]').fill('1.000.000');
  await split(page).locator('.split-next').click();
  assert.match(await split(page).locator('.split-error').innerText(), /Chọn ít nhất hai sổ/);
  await split(page).locator('.split-add').click();
  await split(page).locator('.split-option', { hasText: 'Khách Ba' }).click();
  await split(page).locator('.split-next').click();
  assert.equal(await split(page).locator('.split-part-error[data-index="1"]').innerText(), 'Nhập số tiền cho sổ này.');
  await split(page).locator('.split-remove').click();
  assert.equal(await split(page).locator('.split-row').count(), 1);
  await split(page).locator('.split-add').click();
  await page.keyboard.press('Escape');
  assert.equal(await split(page).locator('.split-picker').count(), 0);
  await page.keyboard.press('Escape');
  assert.equal(await split(page).isHidden(), true);
  await settled(page);
  assert.equal(receiptPosts(world).length, 0);
}, setup));

test('Review #675 lần 2: tải lại trang giữa lần chia (có hỏi khi rời trang) thì mở lại về đúng bước kết quả, khóa cũ, sổ đã ghi không ghi lần hai', async () => withPage(async ({ page, world }) => {
  await openWithTwo(page);
  await split(page).locator('.split-amount[data-index="0"]').fill('30.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('20.000.000');
  await split(page).locator('.split-next').click();
  await split(page).locator('.split-review').waitFor();
  world.books[2].dropNext = true;   // máy chủ lưu mà trang không nhận được kết quả
  await split(page).locator('.split-save').click();
  await split(page).locator('.split-review .split-st-unknown').waitFor();
  const dialogs = [];
  page.on('dialog', dialog => { dialogs.push(dialog.type()); dialog.accept(); });
  await reload(page);
  assert.deepEqual(dialogs, ['beforeunload'], 'còn phiếu chưa rõ thì trình duyệt hỏi trước khi rời trang');
  await page.locator('.entry-open').click();
  await page.locator('.entry-drawer .entry-split').click();
  const text = await split(page).locator('.split-review').innerText();
  assert.match(text, /Khách Thử Sửa: 30\.000\.000[^\n]*Đã ghi PH-001/);
  assert.match(text, /Khách Hai: 20\.000\.000[^\n]*Chưa rõ đã lưu/);
  await split(page).locator('.split-save').click();
  await split(page).waitFor({ state: 'hidden' });
  await settled(page);
  const sent = receiptPosts(world);
  assert.deepEqual(sent.map(body => body.customer_id), [1, 2, 2], 'sổ đã ghi không gửi lại');
  assert.equal(sent[1].idempotency_key, sent[2].idempotency_key, 'gửi lại đúng khóa cũ sau khi tải lại trang');
  assert.deepEqual([world.receipts.length, world.books[2].receipts.length], [1, 1]);
  assert.equal(await page.evaluate(() => localStorage.getItem('webdebit:chia-do')), null, 'xong hết thì xóa trạng thái lưu ở máy');
}, setup));

test('Review #675 lần 2: sổ trong lần chia đã có phiếu cùng tham chiếu và số tiền thì phần đó mặc định không ghi; "Vẫn ghi" mới ghi', async () => withPage(async ({ page, world }) => {
  world.receiptBook = { days: [{ date: clock, rows: [{ source: 'web', pid: 'PH-B7', customer_id: 2, name: 'Khách Hai', amount_vnd: '20000000', date: clock, note: 'UNC 777' }] }], undated: [] };
  await openWithTwo(page);
  await split(page).locator('.split-amount[data-index="0"]').fill('30.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('20.000.000');
  await split(page).locator('.split-next').click();
  const review = split(page).locator('.split-review');
  await review.waitFor();
  let text = await review.innerText();
  assert.match(text, /Ghi 1 phiếu, tổng 30\.000\.000 đ/);
  assert.match(text, /Khách Hai: 20\.000\.000[^\n]*Không ghi/);
  assert.match(text, /Vẫn ghi: sổ này đã có PH-B7 cùng tham chiếu và số tiền/);
  await review.locator('.split-dup').check();
  text = await review.innerText();
  assert.match(text, /Ghi 2 phiếu, tổng 50\.000\.000 đ/);
  await review.locator('.split-dup').uncheck();
  await review.locator('.split-save').click();
  await split(page).waitFor({ state: 'hidden' });
  await settled(page);
  assert.deepEqual(receiptPosts(world).map(body => body.customer_id), [1]);
}, setup));

test('Sau review #675: thiếu tham chiếu thì kiểm trùng theo số tiền và ngày ±3 ở từng sổ; phần trùng mặc định không ghi', async () => withPage(async ({ page, world }) => {
  world.receiptBook = { days: [{ date: clock, rows: [{ source: 'web', pid: 'PH-B3', customer_id: 2, name: 'Khách Hai', amount_vnd: '20000000', date: clock, note: '' }] }], undated: [] };
  await openWithTwo(page);
  await split(page).locator('.split-reference').fill('');
  await split(page).locator('.split-amount[data-index="0"]').fill('30.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('20.000.000');
  await split(page).locator('.split-next').click();
  const review = split(page).locator('.split-review');
  await review.waitFor();
  const text = await review.innerText();
  assert.match(text, /Khách Hai: 20\.000\.000[^\n]*Không ghi/);
  assert.match(text, /Vẫn ghi: sổ này đã có PH-B3 cùng số tiền, ngày gần nhau/);
  assert.match(text, /Ghi 1 phiếu, tổng 30\.000\.000 đ/);
}, setup));

test('Sau review #675: bản lưu lần chia hỏng thì tự xóa, báo, nút Chia cho nhiều sổ vẫn mở khung mới', async () => withPage(async ({ page }) => {
  await page.locator('.entry-open').click();
  await page.locator('.entry-drawer .entry-split').click();
  await split(page).locator('.split-form').waitFor();
  assert.equal(await page.evaluate(() => localStorage.getItem('webdebit:chia-do')), null);
  assert.match(await page.locator('.cn-toast-text').innerText(), /Bản lưu lần chia nhiều sổ dở bị hỏng nên đã bỏ/);
}, world => {
  setup(world);
  world.beforeOpen = page => page.addInitScript(() => {
    if (sessionStorage.getItem('seeded')) return;
    sessionStorage.setItem('seeded', '1');
    localStorage.setItem('webdebit:chia-do', '{"parts":[{"customerId":1,"key":"x"}],"totalVnd":"abc"');
  });
}));

// Lần chia dở mà máy chủ đã từ chối phần sổ Hai: dùng cho các test về bản lưu.
async function leaveUnfinished(page, world) {
  await openWithTwo(page);
  await split(page).locator('.split-amount[data-index="0"]').fill('30.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('20.000.000');
  await split(page).locator('.split-next').click();
  await split(page).locator('.split-review').waitFor();
  world.books[2].failNext = { error: 'INVALID_RECEIPT', message: 'Phiếu không hợp lệ.' };
  await split(page).locator('.split-save').click();
  await split(page).locator('.split-review .split-st-error').waitFor();
}

test('Review #679: khung chia chỉ mở để ghi ở một tab (navigator.locks); tab khác chỉ xem, không gửi; đóng ở tab đầu thì tab kia ghi được', async () => withPage(async ({ page, world }) => {
  await leaveUnfinished(page, world);
  const other = await page.context().newPage();
  await other.goto(page.url());
  await other.locator('.book-head').waitFor();
  await other.locator('.entry-open').click();
  await other.locator('.entry-drawer .entry-split').click();
  const view = other.locator('.split-drawer .split-review');
  await view.locator('.split-elsewhere').waitFor();
  assert.match(await view.innerText(), /Khung chia nhiều sổ đang mở ở tab khác/);
  assert.match(await view.innerText(), /Khách Thử Sửa: 30\.000\.000[^\n]*Đã ghi PH-001/, 'tab kia vẫn xem được lần chia dở');
  assert.equal(await view.locator('button:not([disabled]),input:not([disabled])').count(), 0, 'không nút ghi, không ô sửa');
  await other.locator('.split-drawer header .split-close').click();
  // Tab đầu đóng khung (giữ lần chia dở) là nhả khóa; tab kia mở lại thì ghi tiếp được, đúng khóa cũ.
  await split(page).locator('.split-review .split-close').click();
  await split(page).locator('.split-ask .split-stop').click();
  await other.locator('.entry-open').click();
  await other.locator('.entry-drawer .entry-split').click();
  await other.locator('.split-drawer .split-save').waitFor();
  assert.equal(await other.locator('.split-drawer .split-elsewhere').count(), 0);
  await other.locator('.split-drawer .split-save').click();
  await other.locator('.split-drawer').waitFor({ state: 'hidden' });
  await settled(other);
  assert.deepEqual(receiptPosts(world).map(body => body.customer_id), [1, 2, 2], 'sổ đã ghi không gửi lại');
  assert.equal(world.books[2].receipts.length, 1);
  await other.close();
}, setup));

test('Review #679: bản lưu đã thành của lần chia khác thì không ghi đè, không gửi khóa cũ', async () => withPage(async ({ page, world }) => {
  await leaveUnfinished(page, world);
  const posted = receiptPosts(world).length;
  await page.evaluate(() => {
    const data = JSON.parse(localStorage.getItem('webdebit:chia-do'));
    localStorage.setItem('webdebit:chia-do', JSON.stringify({ ...data, id: 'lan-chia-khac' }));
  });
  await split(page).locator('.split-save').click();
  assert.match(await page.locator('.cn-toast-text').innerText(), /Bản lưu lần chia đã đổi ở nơi khác/);
  await settled(page);
  assert.equal(receiptPosts(world).length, posted);
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('webdebit:chia-do')).id), 'lan-chia-khac', 'bản của lần kia giữ nguyên');
}, setup));

test('Review #679: còn lần chia dở khác trên máy thì không bắt đầu ghi lần chia mới', async () => withPage(async ({ page, world }) => {
  await openWithTwo(page);
  await split(page).locator('.split-amount[data-index="0"]').fill('30.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('20.000.000');
  await split(page).locator('.split-next').click();
  await split(page).locator('.split-review').waitFor();
  await page.evaluate(() => localStorage.setItem('webdebit:chia-do', JSON.stringify({ id: 'lan-truoc', started: true, date: '2026-11-01', method: 'THU TIỀN',
    reference: 'CK', totalVnd: '3000000', parts: [
      { customerId: 1, label: 'A', key: 'khoa-cu-0001', amountVnd: '1000000', beforeVnd: '0', version: 1, status: 'saved', pid: 'PH-9' },
      { customerId: 2, label: 'B', key: 'khoa-cu-0002', amountVnd: '2000000', beforeVnd: '0', version: 1, status: 'unknown' }] })));
  await split(page).locator('.split-save').click();
  assert.match(await page.locator('.cn-toast-text').innerText(), /Còn một lần chia nhiều sổ dở chưa xong/);
  await settled(page);
  assert.equal(receiptPosts(world).length, 0);
}, setup));

test('Review #679: thiếu tham chiếu thì kiểm cả tháng liền kề (±3 ngày) và cả dòng thu sổ gốc', async () => withPage(async ({ page, world }) => {
  const first = `${clock.slice(0, 8)}01`;
  const prevEnd = new Date(Date.parse(`${first}T00:00:00Z`) - 86400000).toISOString().slice(0, 10);
  world.receiptBook = { days: [{ date: prevEnd, rows: [{ source: 'sheet', pid: null, customer_id: 2, name: 'Khách Hai', amount_vnd: '20000000', date: prevEnd, note: null }] }], undated: [] };
  await openWithTwo(page);
  await split(page).locator('.split-date').fill(`01/${clock.slice(5, 7)}/${clock.slice(0, 4)}`);
  await split(page).locator('.split-reference').fill('');
  await split(page).locator('.split-amount[data-index="0"]').fill('30.000.000');
  await split(page).locator('.split-amount[data-index="1"]').fill('20.000.000');
  await split(page).locator('.split-next').click();
  const review = split(page).locator('.split-review');
  await review.waitFor();
  assert.ok(world.bookReads.some(query => query.includes(`month=${prevEnd.slice(0, 7)}-01`)), 'đọc Bảng thu tháng trước');
  assert.match(await review.innerText(), /Vẫn ghi: sổ này đã có dòng thu sổ gốc cùng số tiền, ngày gần nhau/);
}, setup));

test('Review #679: bản lưu đúng cú pháp JSON mà sai kiểu (số tiền chữ, tổng lệch, sổ lặp) thì tự xóa và báo', async () => withPage(async ({ page }) => {
  for (const broken of [
    { amountVnd: 'abc' },
    { totalVnd: '999' },
    { duplicateBook: true },
  ]) {
    await page.evaluate(change => {
      const part = (customerId, amountVnd) => ({ customerId, label: 'A', key: `khoa-${customerId}-00001`, amountVnd, beforeVnd: '0', version: 1, status: 'error' });
      const parts = [part(1, change.amountVnd ?? '1000000'), part(change.duplicateBook ? 1 : 2, '2000000')];
      localStorage.setItem('webdebit:chia-do', JSON.stringify({ id: 'x', started: true, date: '2026-11-01', method: 'THU TIỀN', reference: null,
        totalVnd: change.totalVnd ?? (change.amountVnd ? '3000000' : '3000000'), parts }));
    }, broken);
    await page.locator('.entry-open').click();
    await page.locator('.entry-drawer .entry-split').click();
    await split(page).locator('.split-form').waitFor();
    assert.equal(await page.evaluate(() => localStorage.getItem('webdebit:chia-do')), null, JSON.stringify(broken));
    assert.match(await page.locator('.cn-toast-text').innerText(), /bị hỏng nên đã bỏ/);
    await split(page).locator('.split-close').click();
  }
}, setup));

test('Review #679 lần 2: tab đầu đóng khung, tab sau sửa số rồi ghi; tab đầu mở lại nạp bản lưu, không gửi lại khóa cũ (cả khi bản lưu đã trống)', async () => withPage(async ({ page, world }) => {
  const three = async tab => {
    await tab.locator('.entry-open').click();
    await tab.locator('.entry-drawer .receipt-date').fill(today);
    await tab.locator('.entry-drawer .receipt-amount').fill('50.000.000');
    await tab.locator('.entry-drawer .receipt-reference').fill('UNC 900');
    await tab.locator('.entry-drawer .entry-split').click();
    await tab.locator('.split-drawer .split-form').waitFor();
    for (const name of ['hai', 'ba']) {
      await tab.locator('.split-drawer .split-add').click();
      await tab.locator('.split-drawer .split-search').fill(name);
      await tab.locator('.split-drawer .split-search').press('Enter');
    }
    for (const [index, amount] of [[0, '20.000.000'], [1, '15.000.000'], [2, '15.000.000']]) await tab.locator(`.split-drawer .split-amount[data-index="${index}"]`).fill(amount);
    await tab.locator('.split-drawer .split-next').click();
    await tab.locator('.split-drawer .split-review').waitFor();
  };
  const reopen = async tab => {
    await tab.locator('.entry-open').click();
    await tab.locator('.entry-drawer .entry-split').click();
    await tab.locator('.split-drawer').waitFor({ state: 'visible' });   // mở khung chờ khóa tab
  };
  // Lượt 1: tab A ghi được sổ đang mở, sổ Hai bị từ chối; A đóng, ghi sau.
  await three(page);
  world.books[2].failNext = { error: 'INVALID_RECEIPT', message: 'Phiếu không hợp lệ.' };
  await split(page).locator('.split-save').click();
  await split(page).locator('.split-review .split-st-error').waitFor();
  await split(page).locator('.split-review .split-close').click();
  await split(page).locator('.split-ask .split-stop').click();
  // Tab B giữ khung, sửa số sổ Hai và Ba (khóa mới), ghi; sổ Ba lại bị từ chối nên bản lưu vẫn còn, cùng mã lần chia.
  const other = await page.context().newPage();
  await other.goto(page.url());
  await other.locator('.book-head').waitFor();
  await reopen(other);
  await other.locator('.split-drawer .split-fix[data-index="1"]').fill('10.000.000');
  await other.locator('.split-drawer .split-fix[data-index="2"]').fill('20.000.000');
  world.books[3].failNext = { error: 'INVALID_RECEIPT', message: 'Phiếu không hợp lệ.' };
  await other.locator('.split-drawer .split-save').click();
  await other.locator('.split-drawer .split-lines li', { hasText: 'Khách Ba' }).locator('.split-st-error').waitFor();
  await other.locator('.split-drawer .split-lines li', { hasText: 'Khách Hai' }).locator('.split-st-saved').waitFor();
  await other.locator('.split-drawer .split-review .split-close').click();
  await other.locator('.split-drawer .split-ask .split-stop').click();
  // Tab A mở lại: thấy bản của B (Hai đã ghi 10 triệu), Ghi tiếp chỉ gửi sổ Ba bằng khóa của B.
  await reopen(page);
  const text = await split(page).locator('.split-review').innerText();
  assert.match(text, /Khách Hai: 10\.000\.000[^\n]*Đã ghi/);
  const sent = receiptPosts(world).length;
  await split(page).locator('.split-save').click();
  await split(page).waitFor({ state: 'hidden' });
  await settled(page);
  const posts = receiptPosts(world);
  assert.deepEqual(posts.slice(sent).map(body => [body.customer_id, body.amount_vnd]), [[3, '20000000']]);
  assert.deepEqual([world.books[2].receipts.map(body => body.amount_vnd), world.books[3].receipts.map(body => body.amount_vnd)], [['10000000'], ['20000000']]);
  // Lượt 2 (bản lưu trống): A bỏ dở một lần chia mới, B ghi xong; A mở lại không gửi gì.
  await three(page);
  world.books[2].failNext = { error: 'INVALID_RECEIPT', message: 'Phiếu không hợp lệ.' };
  await split(page).locator('.split-save').click();
  await split(page).locator('.split-review .split-st-error').waitFor();
  await split(page).locator('.split-review .split-close').click();
  await split(page).locator('.split-ask .split-stop').click();
  await reopen(other);
  await other.locator('.split-drawer .split-save').click();
  await other.locator('.split-drawer').waitFor({ state: 'hidden' });
  const before = receiptPosts(world).length;
  await reopen(page);
  await split(page).locator('.split-form').waitFor();
  assert.match(await page.locator('.cn-toast-text').innerText(), /đã xong hay đã bỏ ở tab khác/);
  await settled(page);
  assert.equal(receiptPosts(world).length, before, 'tab A không gửi lại');
  await other.close();
}, setup));
