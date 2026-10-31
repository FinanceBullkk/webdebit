/* Trình duyệt (Playwright) cho ảnh chứng từ phiếu thu (CHUNG-TU-01). Máy chủ giả, ảnh giả vẽ bằng canvas, không chạm DB. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { clock, todayMonth, withPage } = require('./so-khach-v7-browser-world');

// SO-GON-04: ảnh dán vào khung "Ghi phiếu thu" (bên phải, ngoài sổ), không còn hàng nhập trong từng tháng.
const section = '.entry-drawer';
const today = `${clock.slice(8, 10)}/${clock.slice(5, 7)}/${clock.slice(0, 4)}`;

// Dán một ảnh giả (hoặc file không phải ảnh) như Ctrl+V vào phần tử đang chọn.
const paste = (page, { color = '#2a6', kind = 'image' } = {}) => page.evaluate(async ({ color, kind }) => {
  let file;
  if (kind === 'pdf') file = new File(['%PDF-1.7 fake'], 'bang-ke.pdf', { type: 'application/pdf' });
  else {
    const canvas = document.createElement('canvas');
    canvas.width = 300; canvas.height = 600;
    const draw = canvas.getContext('2d');
    draw.fillStyle = color; draw.fillRect(0, 0, 300, 600);
    draw.fillStyle = '#fff'; draw.font = '28px sans-serif'; draw.fillText('ẢNH GIẢ 50.000.000', 10, 300);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    file = new File([blob], 'anh-gia.png', { type: 'image/png' });
  }
  const data = new DataTransfer();
  data.items.add(file);
  (document.activeElement ?? document.body).dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
}, { color, kind });

test('dán ảnh vào khung Ghi phiếu thu, ghi phiếu: phiếu trước, ảnh sau; xem và gỡ ảnh có lý do', async () => withPage(async ({ page, world, shot }) => {
  const entry = page.locator(section);
  await page.locator('.entry-open').click();
  await entry.locator('.receipt-date').focus();
  await paste(page, { kind: 'pdf' });
  await page.waitForSelector(`${section} .image-error`);
  assert.match(await entry.locator('.image-error').innerText(), /không phải ảnh/);

  await paste(page);
  await page.waitForSelector(`${section} .image-thumb`);
  assert.equal(await page.locator('.image-viewer').isVisible(), true);
  assert.match(await page.locator('.image-viewer').innerText(), /Phiếu đang nhập · ảnh 1\/1[\s\S]*VND thực nhận/);
  await page.waitForFunction(() => document.querySelector('.image-viewer img')?.complete);
  assert.equal(world.requests.length, 0, 'dán ảnh chưa gửi lệnh nào');
  await shot('dan-chung-tu-hang-nhap');

  await entry.locator('.receipt-date').fill(today);
  await entry.locator('.receipt-amount').fill('50000000');
  // Nút "Xem lại" đi cùng đường với Enter; bước xem lại ghi số ảnh kèm theo; Ghi phiếu: phiếu trước, ảnh sau.
  await entry.locator('.entry-next').click();
  assert.match(await entry.locator('.entry-review').innerText(), /Kèm 1 ảnh chứng từ/);
  assert.equal(world.requests.length, 0, 'xem lại chưa gửi lệnh nào');
  await entry.locator('.receipt-save').click();
  await page.waitForFunction(() => document.querySelector('.image-clip:not(.none)')?.textContent.includes('📎 1'));
  const [first, second] = world.requests;
  assert.equal(first.path, '/api/v7/receipts');
  assert.equal(second.path, '/api/v7/receipts/images');
  assert.equal(second.body.pid, 'PH-001');
  assert.match(second.body.content_type, /^image\/(webp|jpeg)$/);
  assert.equal(second.body.expected_version, first.body.expected_version + 1);
  assert.equal(await page.locator('.image-thumb').count(), 0, 'khung nhập hết ảnh sau khi ghi');
  await page.locator('.saved-strip').waitFor();
  assert.match(await page.locator('.saved-strip').innerText(), /Đã ghi phiếu PH-001 · 50\.000\.000 đ[\s\S]*Kèm 1 ảnh\./);

  await page.locator('.image-clip:not(.none)').click();
  await page.waitForFunction(() => document.querySelector('.image-viewer img')?.naturalWidth > 0);
  assert.match(await page.locator('.image-viewer').innerText(), /Phiếu PH-001 · ảnh 1\/1/);
  await page.locator('.image-remove-open').click();
  await page.locator('.image-remove-confirm').click();
  assert.match(await page.locator('.image-reason-error').innerText(), /Cần ghi lý do/);
  assert.equal(world.requests.length, 2);
  await page.locator('.image-reason').fill('Đính nhầm');
  await page.locator('.image-reason').press('Enter');
  await page.waitForFunction(() => document.querySelector('.image-clip')?.classList.contains('none'));
  assert.deepEqual(world.requests.at(-1).body.reason, 'Đính nhầm');
  assert.match(await page.locator('.image-viewer').innerText(), /Phiếu chưa có ảnh/);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.image-viewer').isVisible(), false);
}));

test('ảnh đã đính ở sổ khác: cảnh báo, không chặn; mở khung phiếu đã ghi rồi dán thì đính thẳng vào phiếu đó', async () => withPage(async ({ page, world }) => {
  await page.locator('.entry-open').click();
  await page.locator(`${section} .receipt-date`).focus();
  await paste(page, { color: '#a52' });
  await page.waitForSelector(`${section} .image-thumb`);
  const hash = world.finds.at(-1);
  assert.match(hash, /^[0-9a-f]{64}$/);
  world.otherImages = [{ image_id: 7, customer_id: 2, customer_name: 'KHÁCH GIẢ B', pid: 'PH-009', date: '2026-10-21', voided: false, sha256: hash }];
  await page.locator('.image-thumb-drop').click();
  await paste(page, { color: '#a52' });
  await page.waitForSelector(`${section} .image-warn`);
  assert.match(await page.locator(`${section} .image-warn`).innerText(), /phiếu PH-009 của KHÁCH GIẢ B ngày 21\/10\/2026/);
  await page.locator('.image-thumb-drop').click();

  assert.equal(await page.locator('.image-viewer').isVisible(), false, 'bỏ ảnh cuối thì đóng khung');
  // Khung Ghi phiếu thu che cột phiếu thu bên phải (như ngăn phụ phí): đóng khung rồi mới bấm 📎 của phiếu đã ghi.
  await page.locator('.entry-close').click();
  await page.locator('.image-clip').first().click();
  assert.match(await page.locator('.image-viewer').innerText(), /Phiếu PH-001[\s\S]*Phiếu chưa có ảnh/);
  await paste(page, { color: '#25a' });
  await page.waitForFunction(() => document.querySelector('.image-viewer')?.innerText.includes('ảnh 1/1'));
  assert.equal(world.requests.at(-1).path, '/api/v7/receipts/images');
  assert.equal(world.requests.at(-1).body.pid, 'PH-001');
}, world => {
  world.receipts.push({ id: 1, pid: 'PH-001', date: `${clock}`, method: 'THU TIỀN', amount_vnd: '10', reference: null, voided_by_event: null,
    void_reason: null, allocations: [{ id: 1, month: todayMonth, kind: 'debt', amount_vnd: '10', superseded_by_event: null }] });
}));
