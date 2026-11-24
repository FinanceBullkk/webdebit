const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// THU-CHI-02 đợt 0: trang bản thử "Thu chi tự sinh". Máy chủ tĩnh chỉ phục vụ file trong thư mục preview; mọi /api/ bị đếm và trả 404.
const BANNER = 'Bản thử · số bịa · không nối ngân hàng';
const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1280, height: 720 };
const clean = text => text.replace(/\s+/g, ' ').trim();

function makeServer(state) {
  return http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (status, type, data) => { res.writeHead(status, { 'Content-Type': type }); res.end(data); };
    if (url.pathname.startsWith('/api/')) { state.api.push(url.pathname); return send(404, 'application/json', '{}'); }
    const file = path.join(__dirname, url.pathname.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(fn, { viewport = DESKTOP } = {}) {
  const state = { api: [] };
  const server = makeServer(state);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) state.api.push(request.url()); });
    await page.goto(`http://127.0.0.1:${server.address().port}/thu-chi-tu-sinh.html`);
    await fn(page, state, `http://127.0.0.1:${server.address().port}/thu-chi-tu-sinh.html`);
    assert.deepEqual(errors, []);
    assert.deepEqual(state.api, [], 'bản thử không được gọi /api/');
  } finally {
    await browser.close();
    server.close();
  }
}

const role = (page, name) => page.locator('.tcs-role', { hasText: name }).click();
const next = page => page.locator('[data-act="next"]').click();
const figs = page => page.$$eval('[data-fig]', items => Object.fromEntries(items.map(item => [item.dataset.fig, item.dataset.value])));
const progress = page => page.locator('[data-progress]').innerText();
const overflow = page => page.evaluate(() => ({
  doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  wide: [...document.querySelectorAll('body *')].filter(element => element.offsetParent !== null && element.getBoundingClientRect().right > window.innerWidth + 1)
    .map(element => `${element.tagName}.${element.className}`).slice(0, 5),
}));

// Bảng kỳ vọng số trên Dòng tiền sau từng bước, tính tay (cùng bảng với test model): đồng, USD (cent), đang ứng, Cần sếp, vào, ra.
const EXPECTED = [
  ['750000000', '2000000', '20000000', '0', '0', '0'],
  ['942189000', '2000000', '20000000', '2', '201689000', '9500000'],
  ['942189000', '2000000', '20000000', '1', '201689000', '9500000'],
  ['942189000', '2000000', '20000000', '2', '201689000', '9500000'],
  ['942189000', '2000000', '20000000', '1', '201689000', '9500000'],
  ['934189000', '2000000', '20000000', '1', '201689000', '17500000'],
  ['934189000', '2000000', '20000000', '1', '201689000', '17500000'],
  ['1239589000', '2798500', '20000000', '1', '201689000', '17500000'],
  ['1119589000', '2798500', '20000000', '1', '201689000', '137500000'],
  ['1114089000', '2798500', '20000000', '2', '201689000', '143000000'],
  ['1084089000', '2798500', '50000000', '2', '201689000', '173000000'],
  ['1084089000', '2798500', '50000000', '2', '201689000', '173000000'],
];
const pick = value => [value.vnd, value.usd, value.owed, value['can-sep'], value.vao, value.ra];

test('Kịch bản 11 bước chạy hết bằng nút Tiếp; sau mỗi bước, số trên Dòng tiền của sếp bằng bảng kỳ vọng', () => withPage(async page => {
  await role(page, 'Sếp');
  assert.deepEqual(pick(await figs(page)), EXPECTED[0]);
  for (let step = 1; step <= 11; step += 1) {
    await next(page);
    await role(page, 'Sếp');
    assert.match(await progress(page), new RegExp(`Đã làm ${step} / 11 bước`));
    assert.deepEqual(pick(await figs(page)), EXPECTED[step], `sau bước ${step}`);
  }
  assert.equal(await page.locator('[data-step="end"]').count(), 1);
  assert.equal(await page.locator('[data-act="next"]').isDisabled(), true);
  // Cuối ngày: chữ trên Dòng tiền đọc được bằng chữ, không chỉ số ẩn.
  assert.equal(await page.locator('[data-fig="vnd"]').innerText(), '1.084.089.000 đ');
  assert.equal(await page.locator('[data-fig="owed"]').innerText(), '50.000.000 đ');
}));

test('Dải "Bản thử · số bịa · không nối ngân hàng" luôn hiện ở mọi vai và mọi bước', () => withPage(async page => {
  for (let step = 0; step < 3; step += 1) {
    for (const name of ['Sếp', 'Kế toán', 'Tiền hàng', 'Nhân viên']) {
      await role(page, name);
      assert.equal(clean(await page.locator('.tcs-banner').innerText()), BANNER);
      assert.equal(await page.locator('.tcs-banner').isVisible(), true);
    }
    await next(page);
  }
  await page.mouse.wheel(0, 3000);
  assert.equal(await page.locator('.tcs-banner').isVisible(), true);   // dải dính đầu trang
  const box = await page.locator('.tcs-banner').boundingBox();
  assert.ok(box.y <= 1);
}));

test('Sếp trên 390×844 không cuộn ngang ở đầu, giữa và cuối kịch bản; chữ, nút đạt cỡ tối thiểu', () => withPage(async page => {
  for (const step of [0, 4, 9, 11]) {
    while (Number((await progress(page)).match(/(\d+) \//)[1]) < step) await next(page);
    await role(page, 'Sếp');
    const result = await overflow(page);
    assert.deepEqual([result.doc <= 0, result.wide], [true, []], `bước ${step}`);
  }
  await assertSizes(page);
}, { viewport: PHONE }));

test('Nhân viên trên 390×844 không cuộn ngang ở danh sách, biểu mẫu có lỗi và chi tiết đề nghị', () => withPage(async page => {
  await role(page, 'Nhân viên');
  await page.locator('[data-act="tab"][data-id="tao"]').click();
  await page.locator('[data-act="create"]').click();   // để trống: hiện đủ lỗi
  assert.deepEqual(await overflow(page).then(result => [result.doc <= 0, result.wide]), [true, []]);
  await page.locator('[data-act="example"]').click();
  await page.locator('[data-act="create"]').click();
  assert.equal(await page.locator('h2[data-code]').count(), 1);
  assert.deepEqual(await overflow(page).then(result => [result.doc <= 0, result.wide]), [true, []]);
  await page.locator('[data-act="close-request"]').click();
  assert.deepEqual(await overflow(page).then(result => [result.doc <= 0, result.wide]), [true, []]);
  await assertSizes(page);
}, { viewport: PHONE }));

test('Kế toán và Tiền hàng trên 1280×720 không cuộn ngang ở mọi tab và mọi bước chính', () => withPage(async page => {
  for (let step = 0; step <= 11; step += 1) {
    if (step > 0) await next(page);
    if (![0, 1, 5, 8, 10, 11].includes(step)) continue;
    await role(page, 'Kế toán');
    for (const tab of ['so-tien', 'ngoai-le', 'cho-chuyen', 'quy', 'cong-no']) {
      await page.locator(`[data-act="tab"][data-id="${tab}"]`).click();
      const result = await overflow(page);
      assert.deepEqual([result.doc <= 0, result.wide], [true, []], `kế toán ${tab} bước ${step}`);
    }
    await role(page, 'Tiền hàng');
    for (const wallet of ['tq1', 'tq2']) {
      await page.locator(`[data-act="wallet"][data-id="${wallet}"]`).click();
      const result = await overflow(page);
      assert.deepEqual([result.doc <= 0, result.wide], [true, []], `tiền hàng ${wallet} bước ${step}`);
    }
  }
  await assertSizes(page);
  // Khung 1280×720: nút Tiếp và đầu màn của vai thấy ngay, không phải cuộn.
  await page.evaluate(() => window.scrollTo(0, 0));
  const nextBox = await page.locator('[data-act="next"]').boundingBox();
  assert.ok(nextBox.y + nextBox.height <= 720);
}));

async function assertSizes(page) {
  const bad = await page.evaluate(() => {
    const out = [];
    const visible = element => element.offsetParent !== null && element.getBoundingClientRect().width > 0;
    for (const element of document.querySelectorAll('body *')) {
      if (!visible(element)) continue;
      const own = [...element.childNodes].some(node => node.nodeType === 3 && node.textContent.trim());
      const size = parseFloat(getComputedStyle(element).fontSize);
      if (own && size < 13) out.push(`chữ ${size}px: ${element.className || element.tagName}`);
    }
    for (const element of document.querySelectorAll('button, select, input[type=text], textarea, summary, .tcs-check')) {
      if (!visible(element)) continue;
      const box = element.getBoundingClientRect();
      if (box.height < 40) out.push(`vùng bấm ${Math.round(box.height)}px: ${element.className || element.tagName}`);
    }
    if (parseFloat(getComputedStyle(document.body).fontSize) < 16) out.push('chữ thân dưới 16px');
    return out;
  });
  assert.deepEqual(bad, []);
}

test('Nhân viên: lỗi nhập hiện dưới đúng ô, giữ nguyên dữ liệu đã gõ; gửi được thì có dòng thời gian và bot báo', () => withPage(async page => {
  await role(page, 'Nhân viên');
  await page.locator('[data-act="tab"][data-id="tao"]').click();
  await page.locator('[data-f="amountText"]').fill('1,5');
  await page.locator('[data-act="create"]').click();
  assert.match(await page.locator('#err-amount').innerText(), /số nguyên lớn hơn 0/);
  assert.match(await page.locator('#err-payee').innerText(), /Chọn người nhận/);
  assert.match(await page.locator('#err-attachment').innerText(), /Đính kèm ảnh/);
  assert.equal(await page.locator('[data-f="amountText"]').inputValue(), '1,5');   // không mất chữ đã gõ
  assert.equal(await page.locator('[data-f="amountText"]').getAttribute('aria-invalid'), 'true');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.f), 'payeeId');   // tiêu điểm tới ô lỗi đầu tiên của biểu mẫu
  await page.locator('[data-act="kind"][data-id="chi_ho"]').click();
  await page.locator('[data-act="create"]').click();
  assert.match(await page.locator('#err-wallet').innerText(), /Chọn khách Trung Quốc/);
  await page.locator('[data-act="kind"][data-id="chi_thuong"]').click();
  await page.locator('[data-act="example"]').click();
  await page.locator('[data-act="create"]').click();
  assert.match(clean(await page.locator('#note').innerText()), /Đã gửi đề nghị DC0456\. Bot \(mô phỏng\) đã báo sếp\./);
  assert.match(clean(await page.locator('.tcs-time-line').innerText()), /✓ Tạo Xong .*Nhân viên 1/);
  assert.match(clean(await page.locator('.tcs-time-line').innerText()), /○ Duyệt Chưa tới/);
  assert.match(clean(await page.locator('.tcs-botmsg').innerText()), /Bot \(mô phỏng\) đã nhắn: .* → Sếp: Có đề nghị DC0456 chờ duyệt\./);
  // Trao đổi: rỗng bị chặn, có nội dung thì hiện.
  await page.locator('[data-act="comment"]').click();
  assert.match(await page.locator('#err-text').innerText(), /Gõ nội dung trao đổi/);
  await page.locator('[data-f="comment"]').fill('Đã gửi ảnh hóa đơn');
  await page.locator('[data-act="comment"]').click();
  assert.match(clean(await page.locator('.tcs-chat').innerText()), /Nhân viên 1 Đã gửi ảnh hóa đơn/);
}, { viewport: PHONE }));

test('Sếp: từ chối không lý do bị chặn và báo dưới ô; có lý do thì từ chối; duyệt thì Cần sếp giảm', () => withPage(async page => {
  await next(page); await next(page); await next(page);   // đến khi có đề nghị chờ duyệt
  await role(page, 'Sếp');
  assert.equal((await figs(page))['can-sep'], '2');
  await page.locator('[data-act="reject-open"]').click();
  await page.locator('[data-act="reject-send"]').click();
  assert.match(await page.locator('#err-reason').innerText(), /Ghi lý do từ chối/);
  assert.equal(await page.locator('[data-request]').count(), 1);   // chưa từ chối
  await page.locator('[data-f="rejectReason"]').fill('Thiếu hóa đơn');
  await page.locator('[data-act="reject-send"]').click();
  assert.match(clean(await page.locator('#note').innerText()), /Đã từ chối DC0456/);
  assert.equal(await page.locator('[data-request]').count(), 0);
  assert.equal((await figs(page))['can-sep'], '1');
}, { viewport: PHONE }));

test('Chỉ vai Sếp có nút Duyệt bù cho khoản chi không có đề nghị; vai khác không thấy nút', () => withPage(async page => {
  for (let step = 0; step < 9; step += 1) await next(page);   // đến bước 9: chi không đề nghị
  for (const name of ['Kế toán', 'Tiền hàng', 'Nhân viên']) {
    await role(page, name);
    assert.equal(await page.locator('[data-act="approve-late"]').count(), 0, name);
    assert.equal(await page.getByText('Duyệt bù', { exact: true }).count(), 0, name);
  }
  await role(page, 'Kế toán');
  await page.locator('[data-act="tab"][data-id="ngoai-le"]').click();
  assert.match(await page.locator('#view').innerText(), /Kế toán và người chuyển không tự gỡ được/);
  await role(page, 'Sếp');
  assert.equal(await page.locator('[data-act="approve-late"]').count(), 2);   // khoản sáng và khoản chiều
  await page.locator('[data-act="approve-late"]').first().click();
  assert.equal((await figs(page))['can-sep'], '1');
  assert.match(clean(await page.locator('#note').innerText()), /Đã duyệt bù/);
}));

test('Kế toán: gắn khoản chưa rõ cho khách, phiếu điền sẵn hiện ở việc team công nợ; việc riêng bị che; ngoại lệ xếp theo số tiền', () => withPage(async page => {
  await next(page);
  await role(page, 'Kế toán');
  await page.locator('[data-act="tab"][data-id="ngoai-le"]').click();
  const titles = await page.locator('[data-exception] .head b').allInnerTexts();
  assert.deepEqual(titles, ['Tiền về lệch so với phiếu', 'Tiền về chưa rõ của ai', 'Chi chưa có đề nghị']);   // 29,7 triệu, 12 triệu, 3,5 triệu
  await page.locator('[data-act="attach"][data-id="g08"]').click();   // chưa chọn khách
  assert.match(await page.locator('#err-attach-g08').innerText(), /Chọn khách trước khi gắn/);
  await page.locator('[data-f="cust-g08"]').selectOption('kh-a');
  await page.locator('[data-f="rem-g08"]').check();
  await page.locator('[data-act="attach"][data-id="g08"]').click();
  assert.match(clean(await page.locator('#note').innerText()), /Phiếu thu điền sẵn PD\d+ .*lần sau máy tự nhận người chuyển này/);
  await page.locator('[data-act="tab"][data-id="cong-no"]').click();
  assert.match(clean(await page.locator('#view').innerText()), /Khách A · 2026-11-24 12\.000\.000 đ Mã giao dịch g08/);
  await page.locator('[data-act="tab"][data-id="so-tien"]').click();
  const text = await page.locator('#view').innerText();
  assert.match(text, /Việc riêng/);
  assert.doesNotMatch(text, /VIEC RIENG|Người lạ/);
  assert.match(text, /R5 cùng số tiền/);
  assert.match(text, /Phí ngân hàng đã tách/);
}));

test('Kế toán: chép nội dung có mã đề nghị, đã chuyển (mô phỏng), giao tiền mặt cần ảnh biên bản, kiểm quỹ lệch có cờ', () => withPage(async (page) => {
  for (let step = 0; step < 4; step += 1) await next(page);   // đề nghị đã duyệt
  await role(page, 'Kế toán');
  await page.locator('[data-act="tab"][data-id="cho-chuyen"]').click();
  assert.equal(clean(await page.locator('.tcs-copy').innerText()), 'DC0456 Cảng Y');
  await page.locator('[data-act="copy"]').click();
  assert.match(clean(await page.locator('#note').innerText()), /Đã chép nội dung chuyển khoản: DC0456 Cảng Y/);
  await page.locator('[data-act="transferred"]').click();
  assert.equal(await page.locator('[data-act="transferred"]').isDisabled(), true);
  assert.match(await page.locator('[data-request]').innerText(), /Đã chuyển, chờ ngân hàng/);
  for (let step = 4; step < 9; step += 1) await next(page);   // tới hết bước 9
  await next(page);   // bước 10: tạo đề nghị ứng, sếp duyệt, giao tiền mặt (máy làm thay)
  await role(page, 'Kế toán');
  await page.locator('[data-act="tab"][data-id="quy"]').click();
  assert.equal(await page.locator('[data-fig="quy"]').innerText(), '20.000.000 đ');
  await page.locator('[data-f="counted"]').fill('19.500.000');
  await page.locator('[data-act="count"]').click();
  assert.match(clean(await page.locator('#note').innerText()), /Kiểm quỹ: lệch, đã có cờ\./);
  assert.match(clean(await page.locator('#view').innerText()), /đếm 19\.500\.000 đ, sổ 20\.000\.000 đ Lệch −500\.000 đ/);
  await page.locator('[data-f="counted"]').fill('');
  await page.locator('[data-act="count"]').click();
  assert.match(await page.locator('#err-counted').innerText(), /Nhập số tiền đếm được/);
}));

test('Bước 10: thẻ đề nghị ứng ghi rõ vượt số dư ví; giao tiền mặt tay không có ảnh bị chặn, có ảnh thì quỹ trừ và ví âm thêm', () => withPage(async page => {
  for (let step = 0; step < 9; step += 1) await next(page);
  // Người bấm tay: nhân viên tạo đề nghị ứng, sếp duyệt, thủ quỹ giao.
  await role(page, 'Nhân viên');
  await page.locator('[data-act="tab"][data-id="tao"]').click();
  await page.locator('[data-act="kind"][data-id="ung_tien_mat"]').click();
  await page.locator('[data-act="example"]').click();
  await page.locator('[data-act="create"]').click();
  await role(page, 'Sếp');
  assert.match(clean(await page.locator('[data-request]').innerText()), /Vượt số dư ví: ví Khách TQ 2 còn −20\.000\.000 đ, đề nghị 30\.000\.000 đ; sau khi chi còn −50\.000\.000 đ\./);
  await page.locator('[data-act="approve"]').click();
  await role(page, 'Kế toán');
  await page.locator('[data-act="tab"][data-id="quy"]').click();
  await page.locator('[data-act="handover"]').click();
  assert.match(await page.locator('#err-photo-DC0458').innerText(), /Đính kèm ảnh biên bản bàn giao/);
  await page.locator('[data-f="photo-DC0458"]').check();
  await page.locator('[data-act="handover"]').click();
  assert.equal(await page.locator('[data-fig="quy"]').innerText(), '20.000.000 đ');
  await role(page, 'Tiền hàng');
  await page.locator('[data-act="wallet"][data-id="tq2"]').click();
  assert.equal(await page.locator('[data-wallet="tq2"]').innerText(), '−50.000.000 đ');
  assert.match(clean(await page.locator('.tcs-wbtn[aria-pressed="true"] small').first().innerText()), /Đang ứng: công ty ứng trước cho khách/);
  await role(page, 'Sếp');
  assert.equal((await figs(page)).owed, '50000000');
}));

test('Tiền hàng: ví âm có chữ "Đang ứng"; tiền chờ về nhập có kiểm; tiền về thì báo "Về rồi" kèm phí ngân hàng', () => withPage(async page => {
  await role(page, 'Tiền hàng');
  assert.match(clean(await page.locator('[data-wallet="tq2"]').locator('xpath=..').innerText()), /Khách TQ 2 −20\.000\.000 đ Đang ứng: công ty ứng trước cho khách/);
  await page.locator('[data-act="expect"]').click();
  assert.match(await page.locator('#err-wallet').innerText(), /Chọn khách Trung Quốc/);
  assert.match(await page.locator('#err-amount').innerText(), /số đô la nguyên lớn hơn 0/);
  await page.locator('[data-f="expWallet"]').selectOption('tq2');
  await page.locator('[data-f="expAmount"]').fill('8.000');
  await page.locator('[data-act="expect"]').click();
  assert.match(clean(await page.locator('[data-expect]').innerText()), /Khách TQ 2 · 8\.000,00 USD Đang chờ/);
  for (let step = 0; step < 6; step += 1) await next(page);   // máy thấy đã có tiền chờ ở bước 6 (không tạo thêm), rồi USD về ở bước 7
  await next(page);
  await role(page, 'Tiền hàng');
  assert.equal(await page.locator('[data-expect]').count(), 1);
  assert.match(clean(await page.locator('[data-expect]').innerText()), /Về rồi · phí ngân hàng 15,00 USD/);
  assert.match(clean(await page.locator('#view').innerText()), /USD chờ bán 7.985,00 USD/);
}));

test('Sao kê ví Khách TQ 1 sau bước 8 có từng dòng: USD × tỷ giá, ba lần chi hộ, số còn lại', () => withPage(async page => {
  for (let step = 0; step < 8; step += 1) await next(page);
  await role(page, 'Tiền hàng');
  const text = clean(await page.locator('.tcs-stmt').innerText());
  assert.match(text, /12\.000,00 USD × tỷ giá tính khách 25\.300 đ\/USD \+303\.600\.000 đ Còn lại 453.600.000 đ/);
  assert.match(text, /DC0457 · Nhà vườn 1 −50\.000\.000 đ Còn lại 403\.600\.000 đ/);
  assert.match(text, /−30\.000\.000 đ Còn lại 333\.600\.000 đ/);
  assert.match(text, /Tỷ giá ngân hàng 25.450 đ\/USD; tỷ giá tính khách 25\.300 đ\/USD/);
}));

test('Bàn phím: Tab tới được mọi nút, Enter và Space bấm được, tiêu điểm thấy rõ và ở lại chỗ cũ sau khi vẽ lại', () => withPage(async page => {
  // Từ đầu trang, Tab tới nút Tiếp rồi Enter hết 11 bước mà không dùng chuột.
  let found = false;
  for (let index = 0; index < 30 && !found; index += 1) {
    await page.keyboard.press('Tab');
    found = await page.evaluate(() => document.activeElement?.dataset?.act === 'next');
  }
  assert.equal(found, true);
  const outline = await page.evaluate(() => { const style = getComputedStyle(document.activeElement); return [style.outlineStyle, parseFloat(style.outlineWidth)]; });
  assert.equal(outline[0], 'solid');
  assert.ok(outline[1] >= 2);
  for (let step = 1; step <= 11; step += 1) {
    await page.keyboard.press(step % 2 ? 'Enter' : 'Space');
    assert.match(await progress(page), new RegExp(`Đã làm ${step} / 11 bước`));
    assert.equal(await page.evaluate(() => document.activeElement?.dataset?.act), step === 11 ? undefined : 'next');   // tiêu điểm ở lại nút Tiếp
  }
  // Chọn vai bằng bàn phím.
  await page.locator('.tcs-role', { hasText: 'Tiền hàng' }).focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('.tcs-role[aria-pressed="true"]').innerText(), 'Tiền hàng');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.id), 'tienhang');
  // Mọi nút và ô trong màn có thể với tới: không phần tử bấm được nào có tabindex âm.
  assert.equal(await page.locator('#view button[tabindex="-1"], #view a[tabindex="-1"]').count(), 0);
}));

test('Trước lùi một bước và bỏ việc bấm tay; Đặt lại về đầu ngày; vai và bước được nhớ khi tải lại', () => withPage(async (page, state, url) => {
  await next(page); await next(page); await next(page);
  await page.locator('[data-act="back"]').click();
  assert.match(await progress(page), /Đã làm 2 \/ 11 bước/);
  await role(page, 'Sếp');
  assert.equal((await figs(page))['can-sep'], '1');   // đề nghị bước 3 đã bị bỏ
  await next(page); await next(page);
  await role(page, 'Tiền hàng');
  await page.reload();
  assert.match(await progress(page), /Đã làm 4 \/ 11 bước/);
  assert.equal(await page.locator('.tcs-role[aria-pressed="true"]').innerText(), 'Tiền hàng');
  assert.equal(await page.evaluate(() => new URL(location.href).pathname), new URL(url).pathname);
  await page.locator('[data-act="reset"]').click();
  assert.match(await progress(page), /Đã làm 0 \/ 11 bước/);
  await role(page, 'Sếp');
  assert.deepEqual(pick(await figs(page)), EXPECTED[0]);
}));

test('Mỗi danh sách rỗng có chữ nói rõ; localStorage hỏng thì trang vẫn chạy', () => withPage(async page => {
  await role(page, 'Kế toán');
  for (const [tab, text] of [['so-tien', /Chưa có giao dịch nào/], ['ngoai-le', /Hộp ngoại lệ trống/], ['cho-chuyen', /Chưa có đề nghị nào đã duyệt/], ['cong-no', /Chưa có phiếu điền sẵn/]]) {
    await page.locator(`[data-act="tab"][data-id="${tab}"]`).click();
    assert.match(await page.locator('.tcs-empty').first().innerText(), text, tab);
  }
  await role(page, 'Nhân viên');
  assert.match(await page.locator('.tcs-empty').innerText(), /Chưa có đề nghị nào/);
  await role(page, 'Sếp');
  assert.match(await page.locator('[aria-label="Cần sếp"] .tcs-empty').innerText(), /Không có gì chờ sếp/);
  const fresh = await page.context().newPage();
  await fresh.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('bị chặn'); } }); });
  await fresh.goto(page.url());
  assert.match(await fresh.locator('[data-progress]').innerText(), /Đã làm 0 \/ 11 bước/);
  await fresh.locator('[data-act="next"]').click();
  assert.match(await fresh.locator('[data-progress]').innerText(), /Đã làm 1 \/ 11 bước/);
}));

test('Bàn phím: bấm Từ chối thì tiêu điểm vào ô lý do; duyệt xong thì tiêu điểm tới dòng báo kết quả, không rơi về đầu trang', () => withPage(async page => {
  for (let step = 0; step < 3; step += 1) await next(page);
  await role(page, 'Sếp');
  await page.locator('[data-act="reject-open"]').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.f), 'rejectReason');
  await page.keyboard.type('Thiếu hóa đơn');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');   // Gửi từ chối
  assert.match(clean(await page.locator('#note').innerText()), /Đã từ chối DC0456/);
  assert.equal(await page.evaluate(() => document.activeElement.id), 'note');
}));

test('Sếp từ chối rồi bấm Tiếp: bước chuyển tiền được bỏ qua bằng một câu rõ, không có tiền ra', () => withPage(async page => {
  for (let step = 0; step < 3; step += 1) await next(page);
  await role(page, 'Sếp');
  await page.locator('[data-act="reject-open"]').click();
  await page.locator('[data-f="rejectReason"]').fill('Thiếu hóa đơn');
  await page.locator('[data-act="reject-send"]').click();
  await next(page);   // bước 4 đã xử lý
  await next(page);   // bước 5: bỏ qua
  assert.match(clean(await page.locator('#note').innerText()), /Bước 5: Đề nghị DC0456 đã bị từ chối nên không chuyển tiền\./);
  await role(page, 'Sếp');
  const value = await figs(page);
  assert.deepEqual([value.vnd, value['can-sep']], ['942189000', '1']);
}));

test('"Cần sếp" bằng số thẻ đang hiện, kể cả cờ kiểm quỹ lệch', () => withPage(async page => {
  for (let step = 0; step < 10; step += 1) await next(page);
  await role(page, 'Kế toán');
  await page.locator('[data-act="tab"][data-id="quy"]').click();
  await page.locator('[data-f="counted"]').fill('1.000.000');
  await page.locator('[data-act="count"]').click();
  await role(page, 'Sếp');
  const cards = await page.locator('[aria-label="Cần sếp"] .tcs-ask').count();
  assert.equal(String(cards), (await figs(page))['can-sep']);
  assert.match(clean(await page.locator('[data-fig="can-sep"]').locator('xpath=..').innerText()), /1 cờ khác/);
}));

test('Điện thoại 390px: mô tả bước nằm trong "Cả 11 bước", nội dung của vai bắt đầu trong màn đầu tiên; có lối về Tổng quan', () => withPage(async page => {
  assert.equal(await page.locator('.tcs-back').getAttribute('href'), '/dashboard-v7.html');
  assert.equal(await page.locator('.tcs-step-text.wide-only').isVisible(), false);
  await role(page, 'Sếp');
  const top = await page.locator('#view').boundingBox();
  assert.ok(top.y < 720, `nội dung vai bắt đầu ở ${Math.round(top.y)}px`);   // CI Ubuntu không có Segoe UI, chữ rộng hơn: chừa dư, vẫn trong màn 844px
  await page.locator('summary').click();
  assert.equal(await page.locator('.tcs-step-text.narrow-only').isVisible(), true);
}, { viewport: PHONE }));
