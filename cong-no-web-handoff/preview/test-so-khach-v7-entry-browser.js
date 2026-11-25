/* Trình duyệt (Playwright) cho khung "Ghi phiếu thu" có bước xem lại, băng kết quả, "Hủy phiếu vừa ghi" và câu hỏi trước khi
 * khóa/mở khóa tháng (SO-GON-04, specs/v7-so-khach-ux-dot-2.md, PR 2b). Máy chủ giả, dữ liệu giả, không chạm DB hay Sheet. */
const { test } = require('./shared-browser.js');
const assert = require('node:assert/strict');
const { clock, todayMonth, withPage, posts, viewMonth, settled } = require('./so-khach-v7-browser-world');

const today = `${clock.slice(8, 10)}/${clock.slice(5, 7)}/${clock.slice(0, 4)}`;
const thisMonth = `${Number(clock.slice(5, 7))}/${clock.slice(0, 4)}`;
const drawer = page => page.locator('.entry-drawer');
const receiptPosts = world => posts(world).filter(([path]) => path === '/api/v7/receipts');
// Mở khung, gõ ngày và số tiền, Enter ở ô Số tiền: sang bước xem lại.
async function fill(page, date, amount) {
  if (await drawer(page).isHidden()) await page.locator('.entry-open').click();
  await drawer(page).locator('.receipt-date').fill(date);
  await drawer(page).locator('.receipt-amount').fill(amount);
  await drawer(page).locator('.receipt-amount').press('Enter');
}

test('Ghi phiếu thu: một nút ở đầu sổ, Enter ra bước xem lại (chưa gửi), Enter nữa mới ghi đúng một lệnh', async () => withPage(async ({ page, world, shot }) => {
  const open = page.locator('.pay-head .entry-open');
  assert.equal(await open.innerText(), '+ Ghi phiếu thu');
  await open.click();
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('receipt-date')), true);
  await drawer(page).locator('.entry-today').click();
  assert.equal(await drawer(page).locator('.receipt-date').inputValue(), today);
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('receipt-amount')), true);
  await drawer(page).locator('.receipt-amount').fill('50.000.000');
  await drawer(page).locator('.receipt-reference').fill('CK 123');
  await drawer(page).locator('.receipt-reference').press('Enter');
  const review = drawer(page).locator('.entry-review');
  await review.waitFor();
  const text = await review.innerText();
  assert.match(text, new RegExp(`Ghi phiếu 50\\.000\\.000 đ · THU TIỀN · ngày ${today.replace(/\//g, '\\/')}, nằm ở tháng ${thisMonth.replace('/', '\\/')}\\.`));
  assert.match(text, /Tổng còn nợ: 1\.250\.000\.000 đ → 1\.200\.000\.000 đ\./);
  assert.match(text, /Tham chiếu: CK 123/);
  assert.match(text, /Phần trừ nợ từng tháng hiện ngay sau khi ghi/);
  assert.doesNotMatch(text, /khách dư|đang khóa/);
  await settled(page);
  assert.equal(world.requests.length, 0, 'bước xem lại chưa gửi lệnh nào');
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('entry-sum')), true, 'SK-C2: tiêu điểm ở câu tóm tắt, không ở nút Ghi phiếu');
  await shot('entry-xem-lai');
  // Sửa lại: về ô Số tiền, số đã gõ còn nguyên.
  await drawer(page).locator('.entry-back').click();
  assert.equal(await drawer(page).locator('.receipt-amount').inputValue(), '50.000.000');
  await drawer(page).locator('.receipt-amount').press('Enter');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('receipt-save')), true, 'Tab hai lần tới nút Ghi phiếu');
  await page.keyboard.press('Enter');
  await page.locator('.saved-strip').waitFor();
  await settled(page);
  assert.equal(receiptPosts(world).length, 1);
  await settled(page);
  assert.deepEqual({ ...receiptPosts(world)[0][1], idempotency_key: typeof receiptPosts(world)[0][1].idempotency_key },
    { customer_id: 1, expected_version: 1, idempotency_key: 'string', date: clock, method: 'THU TIỀN', amount_vnd: '50000000', reference: 'CK 123' });
  // Ghi xong: khung đóng và về trống; băng kết quả ghi phần trừ nợ theo sổ vừa tải; dòng phiếu tô và nằm trong tầm nhìn.
  assert.equal(await drawer(page).isHidden(), true);
  assert.match(await page.locator('.saved-strip').innerText(),
    new RegExp(`Đã ghi phiếu PH-001 · 50\\.000\\.000 đ · ngày ${today.replace(/\//g, '\\/')} · trừ nợ T${thisMonth.replace('/', '\\/')} 50\\.000\\.000\\.`));
  assert.equal(await page.locator('tr.pay-row:has(td[data-pid="PH-001"][data-field="date"])').evaluate(row => row.classList.contains('just-saved')), true);
  await page.locator('.entry-open').click();
  assert.equal(await drawer(page).locator('.receipt-amount').inputValue(), '');
  await shot('entry-da-ghi');
}, world => { world.total = '1250000000'; }));

test('SK-C2: gõ ngày, số tiền, Enter, Enter (kể cả giữ phím) không gửi lệnh ghi; Tab tới Ghi phiếu rồi Enter ghi đúng một lệnh', async () => withPage(async ({ page, world }) => {
  await fill(page, today, '2000000');
  const review = drawer(page).locator('.entry-review');
  await review.waitFor();
  await page.keyboard.press('Enter');
  await page.keyboard.down('Enter');
  await page.keyboard.down('Enter');   // phím giữ lặp (event.repeat)
  await page.keyboard.up('Enter');
  await settled(page);
  assert.equal(world.requests.length, 0, 'Enter, Enter và giữ Enter không gửi lệnh nào');
  assert.equal(await review.isVisible(), true, 'bước Xem lại vẫn mở');
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('entry-sum')), true);
  // Ghi có chủ ý: Tab tới Ghi phiếu rồi Enter.
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('receipt-save')), true);
  await page.keyboard.press('Enter');
  await page.locator('.saved-strip').waitFor();
  await settled(page);
  assert.equal(receiptPosts(world).length, 1);
  assert.equal(receiptPosts(world)[0][1].amount_vnd, '2000000');
}));

test('SK-N10: ô Số tiền hiện số đã hiểu có nhóm nghìn khi gõ và khi rời ô; lỗi nói dạng đúng và tắt khi sửa ô', async () => withPage(async ({ page, world, shot }) => {
  await page.locator('.entry-open').click();
  const amount = drawer(page).locator('.receipt-amount');
  const hint = drawer(page).locator('.entry-amount-hint');
  const error = drawer(page).locator('.receipt-amount-error');
  await amount.pressSequentially('1234567');
  assert.equal(await hint.innerText(), 'Hiểu là 1.234.567 đ');
  assert.equal(await amount.inputValue(), '1234567', 'đang gõ thì không đổi chữ trong ô');
  await shot('entry-so-tien-hieu-la');
  await drawer(page).locator('.receipt-reference').focus();   // rời ô
  assert.equal(await amount.inputValue(), '1.234.567');
  // Chữ chưa đọc được: giữ nguyên chữ gõ, không hiện số; lỗi chỉ khi bấm Xem lại.
  await amount.fill('45tr');
  assert.equal(await hint.innerText(), '');
  await drawer(page).locator('.receipt-reference').focus();
  assert.equal(await amount.inputValue(), '45tr');
  await drawer(page).locator('.receipt-date').fill(today);
  await amount.press('Enter');
  assert.match(await error.innerText(), /^Số tiền không hợp lệ\. Chỉ gõ chữ số/);
  await shot('entry-so-tien-loi');
  // Sửa ô: lỗi cũ tắt ngay, không đợi lần Xem lại sau.
  await amount.pressSequentially('0');
  assert.equal(await error.innerText(), '');
  await amount.fill('45.000.000');
  assert.equal(await hint.innerText(), 'Hiểu là 45.000.000 đ');
  await settled(page);
  assert.equal(world.requests.length, 0);
}));

test('Bấm Ghi phiếu hai lần nhanh vẫn một phiếu; vượt tổng nợ thì xem lại báo khách dư', async () => withPage(async ({ page, world }) => {
  await fill(page, today, '30000000');
  assert.match(await drawer(page).locator('.entry-review').innerText(), /Tổng còn nợ: 10\.000\.000 đ → -20\.000\.000 đ\.[\s\S]*Sau phiếu này khách dư 20\.000\.000 đ\./);
  await drawer(page).locator('.receipt-save').dblclick();
  await page.locator('.saved-strip').waitFor();
  await settled(page);
  assert.equal(receiptPosts(world).length, 1);
  assert.equal(world.receipts.length, 1);
}, world => { world.total = '10000000'; }));

test('Chặn tại ô trước khi gửi: ngày sai, ngày sau hôm nay, thiếu số tiền, số 0; Esc đóng khung', async () => withPage(async ({ page, world }) => {
  await fill(page, '32/13/2026', '1000');
  assert.equal(await drawer(page).locator('.receipt-date-error').innerText(), 'Ngày trả phải dạng dd/mm/yyyy.');
  await fill(page, '01/01/2099', '1000');
  assert.equal(await drawer(page).locator('.receipt-date-error').innerText(), 'Ngày trả không được sau hôm nay.');
  await fill(page, today, '');
  assert.equal(await drawer(page).locator('.receipt-amount-error').innerText(), 'Nhập số tiền khách trả.');
  await fill(page, today, '0');
  assert.equal(await drawer(page).locator('.receipt-amount-error').innerText(), 'Số tiền phải lớn hơn 0.');
  await fill(page, today, 'abc');
  assert.match(await drawer(page).locator('.receipt-amount-error').innerText(), /^Số tiền không hợp lệ\. Chỉ gõ chữ số.*45\.000\.000.*không gõ chữ như tr, k/);
  assert.equal(await drawer(page).locator('.entry-review').isHidden(), true);
  await settled(page);
  assert.equal(world.requests.length, 0);
  await page.keyboard.press('Escape');
  assert.equal(await drawer(page).isHidden(), true);
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('entry-open')), true);
}));

test('PHIEU-WEB-01: không rõ ngày trả → chọn tháng, ghi ngày cuối tháng (không sau hôm nay) và tham chiếu "(ngày tượng trưng)"', async () => withPage(async ({ page, world, shot }) => {
  const n = Number(clock.slice(0, 4)) * 12 + Number(clock.slice(5, 7)) - 2;
  const prev = `${Math.floor(n / 12)}-${String(n % 12 + 1).padStart(2, '0')}`;
  const prevEnd = `${prev}-${String(new Date(Date.UTC(Number(prev.slice(0, 4)), Number(prev.slice(5, 7)), 0)).getUTCDate()).padStart(2, '0')}`;
  const shown = iso => `${iso.slice(8)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
  await page.locator('.entry-open').click();
  await drawer(page).locator('.receipt-unknown').check();
  assert.equal(await drawer(page).locator('.receipt-date').isDisabled(), true, 'ô ngày tắt khi không rõ ngày');
  assert.equal(await drawer(page).locator('.receipt-month').inputValue(), '', 'tháng chưa chọn sẵn');
  assert.equal(await drawer(page).locator('.receipt-month option').count(), 13);
  // Chưa chọn tháng: chặn tại ô, không gửi.
  await drawer(page).locator('.receipt-amount').fill('2.000.000');
  await drawer(page).locator('.receipt-amount').press('Enter');
  assert.equal(await drawer(page).locator('.receipt-month-error').innerText(), 'Chọn tháng khách trả.');
  // Tháng trước: ngày cuối tháng đó.
  await drawer(page).locator('.receipt-month').selectOption(prev);
  assert.equal(await drawer(page).locator('.entry-symbolic-hint').innerText(), `Ghi ngày ${shown(prevEnd)} (ngày tượng trưng).`);
  await drawer(page).locator('.receipt-reference').fill('CK qua Zalo');
  await drawer(page).locator('.receipt-reference').press('Enter');
  const review = drawer(page).locator('.entry-review');
  await review.waitFor();
  assert.match(await review.innerText(), new RegExp(`ngày ${shown(prevEnd).replace(/\//g, '\\/')} \\(ngày tượng trưng\\), nằm ở tháng`));
  assert.match(await review.innerText(), /Không rõ ngày trả: ghi ngày cuối tháng/);
  await shot('entry-khong-ro-ngay');
  // Tháng hiện tại: ngày cuối tháng sau hôm nay nên lấy hôm nay (cùng luật máy Sheet).
  await drawer(page).locator('.entry-back').click();
  await drawer(page).locator('.receipt-month').selectOption(clock.slice(0, 7));
  assert.equal(await drawer(page).locator('.entry-symbolic-hint').innerText(), `Ghi ngày ${today} (ngày tượng trưng).`);
  await drawer(page).locator('.receipt-month').selectOption(prev);
  await drawer(page).locator('.receipt-amount').press('Enter');
  await drawer(page).locator('.receipt-save').click();
  await page.locator('.saved-strip').waitFor();
  await settled(page);
  assert.equal(receiptPosts(world).length, 1);
  const sent = receiptPosts(world)[0][1];
  assert.equal(sent.date, prevEnd);
  assert.equal(sent.reference, 'CK qua Zalo (ngày tượng trưng)');
  assert.equal(sent.amount_vnd, '2000000');
  // Khung về trống: bỏ đánh dấu, ô ngày bật lại.
  await page.locator('.entry-open').click();
  assert.equal(await drawer(page).locator('.receipt-unknown').isChecked(), false);
  assert.equal(await drawer(page).locator('.receipt-date').isDisabled(), false);
  assert.equal(await drawer(page).locator('.entry-month').isHidden(), true);
  // Cấn trừ cần ngày cụ thể.
  await drawer(page).locator('.receipt-unknown').check();
  await drawer(page).locator('.receipt-method').selectOption('CẤN TRỪ');
  await drawer(page).locator('.receipt-amount').fill('1000');
  await drawer(page).locator('.receipt-amount').press('Enter');
  assert.match(await drawer(page).locator('.receipt-month-error').innerText(), /Cấn trừ cần ngày cụ thể/);
  assert.equal(receiptPosts(world).length, 1);
}, world => { world.total = '10000000'; }));

test('Server báo ngày sau hôm nay: về ô Ngày, không kẹt lệnh; sổ đổi dưới tay: xem lại số mới rồi ghi lại', async () => withPage(async ({ page, world }) => {
  world.failNext = { error: 'FUTURE_RECEIPT_DATE', message: 'Ngày trả không được sau hôm nay.' };
  await fill(page, today, '1000');
  await drawer(page).locator('.receipt-save').click();
  await drawer(page).locator('.receipt-date-error').filter({ hasText: 'Ngày trả không được sau hôm nay.' }).waitFor();
  assert.equal(await drawer(page).locator('.entry-form').isVisible(), true);
  // Sổ đổi giữa lúc xem lại: lệnh bị từ chối vì phiên bản, sổ tải lại, khung vẫn ở bước xem lại với số mới.
  await drawer(page).locator('.receipt-amount').press('Enter');
  world.version += 1;
  world.total = '7000';
  await drawer(page).locator('.receipt-save').click();
  await drawer(page).locator('.entry-error').filter({ hasText: 'Sổ vừa thay đổi' }).waitFor();
  assert.match(await drawer(page).locator('.entry-review').innerText(), /Tổng còn nợ: 7\.000 đ → 6\.000 đ\./);
  await drawer(page).locator('.receipt-save').click();
  await page.locator('.saved-strip').waitFor();
  assert.equal(world.receipts.length, 1);
}));

test('Mất mạng khi ghi: khung báo chưa rõ, Thử lại gửi lại cùng lệnh, chỉ một phiếu', async () => withPage(async ({ page, world }) => {
  await fill(page, today, '2000');
  await page.route('**/api/v7/receipts', route => route.abort(), { times: 1 });
  await drawer(page).locator('.receipt-save').click();
  await drawer(page).locator('.entry-retry').waitFor();
  assert.match(await drawer(page).locator('.entry-error').innerText(), /Chưa rõ phiếu đã lưu chưa/);
  assert.equal(world.receipts.length, 0);
  await drawer(page).locator('.entry-retry').click();
  await page.locator('.saved-strip').waitFor();
  assert.equal(world.receipts.length, 1);
  await settled(page);
  assert.equal(receiptPosts(world).length, 1);
}));

test('Hủy phiếu vừa ghi: mở dòng hủy có lý do điền sẵn; lý do trống không gửi; hủy xong băng kết quả tắt', async () => withPage(async ({ page, world }) => {
  await fill(page, today, '3000');
  await drawer(page).locator('.receipt-save').click();
  await page.locator('.saved-strip .saved-void').click();
  const reason = page.locator('.void-prompt[data-pid="PH-001"] .void-reason');
  assert.equal(await reason.inputValue(), 'Ghi nhầm, hủy ngay sau khi ghi');
  await reason.fill('');
  await reason.press('Enter');
  assert.equal(await page.locator('.void-prompt .cell-error').innerText(), 'Cần nhập lý do');
  await settled(page);
  assert.equal(posts(world).some(([path]) => path === '/api/v7/receipts/void'), false);
  await reason.fill('Ghi nhầm, hủy ngay sau khi ghi');
  await reason.press('Enter');
  await page.waitForFunction(() => !document.querySelector('.saved-strip'));
  await settled(page);
  assert.deepEqual(posts(world).at(-1)[0], '/api/v7/receipts/void');
  await settled(page);
  assert.equal(posts(world).at(-1)[1].reason, 'Ghi nhầm, hủy ngay sau khi ghi');
  assert.match(await page.locator('.void-summary').innerText(), /1 phiếu đã hủy/);
}));

test('Khóa / mở khóa tháng: hỏi một câu dưới nút; Thôi hay Esc không gửi lệnh; Khóa tháng mới gửi', async () => withPage(async ({ page, world }) => {
  const key = todayMonth.slice(0, 7), short = Number(key.slice(5));
  await viewMonth(page, key);
  const lock = page.locator(`.month-lock[data-month="${todayMonth}"]`);
  await lock.click();
  const ask = page.locator('.lock-ask');
  assert.match(await ask.innerText(), new RegExp(`Khóa tháng ${short}\\/${key.slice(0, 4)}\\? Sau khi khóa, sửa tiền trong tháng sẽ thành dòng điều chỉnh\\.`));
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('lock-yes')), true);
  await ask.locator('.lock-no').click();
  assert.equal(await page.locator('.lock-ask').count(), 0);
  assert.equal(await lock.evaluate(button => document.activeElement === button), true, 'tiêu điểm về ổ khóa');
  await lock.click();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.lock-ask').count(), 0);
  await settled(page);
  assert.equal(world.requests.length, 0);
  await lock.click();
  await page.locator('.lock-yes').click();
  await settled(page);
  assert.deepEqual(posts(world).map(([path, body]) => [path, body.month, body.locked]), [['/api/v7/months/lock', todayMonth, true]]);
}, world => { world.locks = [{ month: '2026-09-01', locked: false }, { month: todayMonth, locked: false }]; }));

test('Dán ảnh khi chưa mở khung: khung Ghi phiếu thu tự mở và giữ ảnh', async () => withPage(async ({ page }) => {
  await page.evaluate(async () => {
    const canvas = document.createElement('canvas');
    canvas.width = 120; canvas.height = 240;
    canvas.getContext('2d').fillRect(0, 0, 120, 240);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    const data = new DataTransfer();
    data.items.add(new File([blob], 'anh-gia.png', { type: 'image/png' }));
    document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  });
  await drawer(page).locator('.image-thumb').waitFor();
  assert.equal(await drawer(page).isVisible(), true);
}));
