const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// MAY-CHAY-01: tab Máy chạy. Dữ liệu giả; trang chỉ xem nên không được có lệnh POST nào ngoài presence.
const at = (h, m, s = 0, day = '2026-11-06') => `${day}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}+07:00`;
const segments = (list, day) => list.map(([stage, h, m, s]) => ({ stage, at: at(h, m, s, day) }));
const quiet = () => ({ state: 'done', mode: 'fix', started_at: at(9, 5), finished_at: at(9, 10), books: 10, counts: { KHOP: 10 }, fixed: 0, created: 0, unlinked: {}, customers: {}, too_many: false,
  segments: segments([['tai', 9, 5, 0], ['sach', 9, 5, 10], ['doc', 9, 7, 0], ['so', 9, 9, 40], ['luu', 9, 9, 50]]) });
const wrote = () => ({ state: 'done', mode: 'fix', started_at: at(8, 5), finished_at: at(8, 13), books: 10, counts: { KHOP: 9 }, fixed: 1, created: 0, unlinked: { CHI_CO_SHEET: 1 }, too_many: false,
  segments: segments([['tai', 8, 5, 0], ['sach', 8, 5, 10], ['doc', 8, 7, 0], ['so', 8, 9, 0], ['chot', 8, 9, 10], ['tim', 8, 9, 12], ['ghi', 8, 12, 0], ['luu', 8, 12, 50]]),
  customers: { 7: { customer_id: 7, reason: 'FIXED', decided_at: at(8, 11), done_at: at(8, 12, 20), before_vnd: '248300000', after_vnd: '260800000', target_vnd: '260800000' }, 9: { customer_id: 9, reason: 'NO_EXACT_FIX', decided_at: at(8, 11, 30), difference_vnd: '-8200000' } } });
const running = () => ({ state: 'running', mode: 'fix', started_at: at(10, 5), finished_at: null, stage: 'doc', done: 4, total: 10, unlinked: {}, customers: {}, too_many: false, segments: segments([['tai', 10, 5, 0], ['sach', 10, 5, 10], ['doc', 10, 7, 0]]) });
const row = trace => ({ finished_at: trace.finished_at, mode: 'fix', counts: trace.counts, total: trace.books, fixed: trace.fixed, created: trace.created, detail: trace });
const oldRow = () => ({ finished_at: at(13, 12, 38, '2026-11-05'), mode: 'fix', counts: { KHOP: 9 }, total: 10, fixed: 1, created: 0, detail: null });
const JOBS = [
  { id: 'reconcile', name: 'Đối soát tự sửa', does: 'So tổng từng khách, ghi khi khớp', every: 'Mỗi giờ, 7–22 giờ', last: at(9, 5), next: at(10, 5), state: 'ok' },
  { id: 'sheet', name: 'Bản chụp Sheet', does: 'Đọc CONT_NGUON, CONT_BO', every: '15 phút một lần', last: at(9, 30), next: at(9, 45), state: 'ok' },
  { id: 'prices', name: 'Giá Sheet', does: 'Đọc giá và phiếu thu', every: '15 phút một lần', last: null, next: null, state: 'failed' },
];
const TASKS = { 'kh-9-lech': { title: 'kh-9 còn lệch', body: 'Đã 4 lượt liền với kh-9. Cần chủ sổ xem.', level: 'warn' }, 'sao-luu-tre': { title: 'Sao lưu trễ', body: 'Cần xem.', level: 'urgent' } };
const base = () => ({ now: at(9, 40), run: quiet(), jobs: JOBS, office: { state: 'idle', tasks: TASKS, updated_at: at(9, 15), model_called_at: at(9, 15) }, runs: [oldRow(), row(wrote()), row(quiet())] });
const CUSTOMERS = [{ id: 7, name: 'KHACH BAY', status: 'active' }, { id: 9, name: 'KHACH CHIN', status: 'active' }];

function makeServer(state) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body) => { response.writeHead(status, { 'Content-Type': type }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    state.calls.push(`${request.method} ${route}`);
    if (route === '/api/v7/machine' || route === '/api/v7/machine/now') return state.down ? out({ error: 'X' }, 503) : out(state.data());
    if (route === '/api/v7/customers') return out({ customers: CUSTOMERS });
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 503);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(state, fn, viewport = { width: 1265, height: 560 }) {
  const shared = { calls: [], down: false, data: base, ...state };
  const server = makeServer(shared);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await (await browser.newContext({ viewport })).newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/may-chay.html`);
    await page.locator('.slot').first().waitFor({ state: 'attached' });
    await fn(page, shared);
    assert.deepEqual(errors, []);
    assert.deepEqual(shared.calls.filter(call => call.startsWith('POST') && !call.includes('presence')), [], 'trang chỉ xem không gửi lệnh ghi');
  } finally {
    await browser.close();
    server.close();
  }
}
const now = page => page.locator('#now').innerText();

test('Máy chạy: mở trang là trực tiếp, không có nút phát lại, thấy lượt kế và việc hôm nay; không tràn ngang, dải lượt lọt khung', () => withPage({}, async page => {
  await page.waitForFunction(() => document.getElementById('now').textContent.startsWith('Đối soát đang nghỉ'));
  assert.equal(await now(page), 'Đối soát đang nghỉ, lượt kế 10:05. Lượt trước 09:05: 10/10 khớp, không ghi gì. Cần xem: Giá Sheet.');
  assert.equal(await page.locator('#live-pill').innerText(), 'Trực tiếp');
  for (const id of ['#play', '#speed', '#scrub', '#go-live']) assert.equal(await page.locator(id).isVisible(), false, id);
  assert.match(await page.locator('#clock').innerText(), /^lượt kế còn \d+:\d\d$/);
  const cards = await page.locator('#cards').innerText();
  assert.ok(cards.includes('Hôm nay máy đã ghi 1 việc'), cards);
  assert.ok(cards.includes('248.300.000đ → 260.800.000đ'), cards);
  assert.ok((await page.locator('#cards a').first().getAttribute('href')).includes('customer=7'));
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  const lastDay = await page.locator('.day').last().boundingBox();
  assert.ok(lastDay.y + lastDay.height <= 560, `dải lượt lọt khung 560: ${lastDay.y + lastDay.height}`);
  const canvas = await page.locator('#office').boundingBox();
  assert.ok(canvas.width >= 700, `văn phòng đủ rộng để đọc chữ: ${canvas.width}`);
  assert.equal(await page.locator('.app-nav a.active').innerText(), 'Máy chạy');
  const menu = await page.locator('.app-nav nav a').last().boundingBox();
  assert.ok(menu.y + menu.height <= 560, `mục cuối menu lọt khung: ${menu.y + menu.height}`);
  const heights = await page.evaluate(() => [...new Set([...document.querySelectorAll('.stage-head > *:not([hidden])')].map(node => Math.round(node.getBoundingClientRect().top + node.getBoundingClientRect().height / 2)))]);
  assert.ok(Math.max(...heights) - Math.min(...heights) <= 2, `hàng nút không xuống dòng: ${heights}`);
}));

test('Máy chạy: lượt có ghi hiện trước → sau đúng từng đồng, link tới sổ, khách lệch nêu lý do, khách chưa có sổ chỉ đếm', () => withPage({}, async page => {
  await page.locator('.slot.wrote').first().click();
  await page.locator('#scrub').evaluate(node => { node.value = 1000; node.dispatchEvent(new Event('input')); });
  const text = await page.locator('#cards').innerText();
  assert.ok(text.includes('248.300.000đ → 260.800.000đ'), text);
  assert.ok(text.includes('KHACH BAY'), text);
  assert.ok(text.includes('-8.200.000đ'), text);
  assert.ok(text.includes('không có tổ hợp') || text.includes('Không có tổ hợp'), text);
  assert.ok(text.includes('1 khách chưa có sổ'), text);
  assert.ok((await page.locator('#cards a').first().getAttribute('href')).includes('customer=7'));
  assert.ok((await now(page)).includes('máy đã ghi 1 khách'));
}));

test('Máy chạy: lượt cũ chỉ có số đếm thì nói rõ, không dựng thẻ khách giả', () => withPage({}, async page => {
  await page.locator('.day').last().locator('.slot').first().click();
  await page.locator('#scrub').evaluate(node => { node.value = 1000; node.dispatchEvent(new Event('input')); });
  const text = await page.locator('#cards').innerText();
  assert.ok(text.includes('chỉ còn số đếm'), text);
  assert.ok(!text.includes('Khách A'));
  assert.ok((await page.locator('#clock').innerText()).includes('ước tính'));
}));

test('Máy chạy: có lượt đang chạy thì tự theo, đếm đúng số job báo; mất kết nối thì báo và thôi vẽ tiếp', () => withPage({ data: () => ({ ...base(), now: at(10, 7, 30), run: running() }) }, async (page, state) => {
  await page.waitForFunction(() => document.getElementById('now').textContent.startsWith('Đang đọc'));
  assert.equal(await now(page), 'Đang đọc tổng từng sổ web: 4/10');
  assert.ok((await page.locator('#run-title').innerText()).startsWith('Đang chạy'));
  assert.equal(await page.locator('#play').isVisible(), false);
  assert.equal(await page.locator('#scrub').isVisible(), false);
  assert.match(await page.locator('#clock').innerText(), /^đã chạy /);
  assert.equal(await page.locator('.slot.now').innerText(), '10:05 đang chạy');
  state.down = true;
  await page.waitForFunction(() => document.getElementById('now').textContent.startsWith('Mất kết nối'), null, { timeout: 8000 });
  assert.ok((await now(page)).includes('đứng yên'));
  assert.equal(await page.locator('#live-pill').innerText(), 'Mất tín hiệu');
}));

test('Máy chạy: đang mở trang mà lượt bắt đầu thì tự vào trực tiếp không cần bấm; lượt xong tự đọc lại danh sách, có thêm ô lượt mới', () => {
  let phase = 'idle';
  const done = () => ({ ...quiet(), started_at: at(10, 5), finished_at: at(10, 10), segments: segments([['tai', 10, 5, 0], ['luu', 10, 9, 50]]) });
  const data = () => (phase === 'idle' ? base() : phase === 'run' ? { ...base(), now: at(10, 7, 30), run: running() } : { ...base(), now: at(10, 11), run: done(), runs: [...base().runs, row(done())] });
  return withPage({ data }, async page => {
    await page.waitForFunction(() => document.getElementById('now').textContent.startsWith('Đối soát đang nghỉ'));
    const before = await page.locator('.slot').count();
    phase = 'run';
    await page.waitForFunction(() => document.getElementById('now').textContent.startsWith('Đang đọc'), null, { timeout: 6000 });
    phase = 'done';
    await page.waitForFunction(() => document.getElementById('now').textContent.includes('Lượt trước 10:05'), null, { timeout: 6000 });
    assert.equal(await page.locator('.slot').count(), before + 1);
    assert.equal(await page.locator('.slot.now').count(), 0);
    assert.ok((await page.locator('#run-title').innerText()).includes('10:05'));
  });
});

test('Máy chạy: đồng hồ chạy theo giờ máy chủ khi máy nghỉ; job phụ đang chạy thì nói ngay, xong thì vào nhật ký kèm số giây thật', () => {
  let jobs = JOBS;
  return withPage({ data: () => ({ ...base(), jobs }) }, async page => {
    await page.waitForFunction(() => document.getElementById('clock').textContent.startsWith('lượt kế còn'));
    const first = await page.locator('#clock').innerText();
    await page.waitForFunction(text => document.getElementById('clock').textContent !== text, first, { timeout: 4000 });
    jobs = JOBS.map(job => (job.id === 'sheet' ? { ...job, state: 'running', started: at(9, 45, 0), ended: null } : job));
    await page.waitForFunction(() => document.getElementById('now').textContent.includes('Bản chụp Sheet đang chạy'), null, { timeout: 6000 });
    assert.ok(await page.locator('#live-pill').evaluate(node => node.classList.contains('busy')));
    await page.waitForFunction(() => document.getElementById('log').textContent.includes('Bản chụp Sheet đang chạy'), null, { timeout: 3000 });
    jobs = JOBS.map(job => (job.id === 'sheet' ? { ...job, state: 'ok', started: at(9, 45, 0), ended: at(9, 45, 4) } : job));
    await page.waitForFunction(() => document.getElementById('log').textContent.includes('Bản chụp Sheet xong, 4 giây'), null, { timeout: 6000 });
    assert.ok(!(await now(page)).includes('đang chạy'));
    assert.ok(!(await page.locator('#log').innerText()).includes('đang chạy'), 'cùng một lần chạy chỉ còn một dòng');
  });
});

test('Máy chạy: việc máy ghi qua hộp chờ cũng hiện trong "hôm nay", gom theo sổ, nói rõ chuyến chưa có giá', () => withPage({ data: () => ({ ...base(), auto: [
  { at: at(9, 31), kind: 'price', customer_id: 9, container: 'CONT1', unit_price_vnd: '12000000', before_unit_price_vnd: null },
  { at: at(9, 32), kind: 'trip', customer_id: 7, container: 'CONT2', pending: true },
  { at: at(9, 33), kind: 'trip', customer_id: 7, container: 'CONT3', pending: false },
] }) }, async page => {
  await page.waitForFunction(() => document.getElementById('cards').textContent.includes('Thêm chuyến'));
  const text = await page.locator('#cards').innerText();
  assert.ok(text.includes('Hôm nay máy đã ghi 3 việc'), text);
  assert.ok(text.includes('— → 12.000.000đ'), text);
  assert.ok(text.includes('2 chuyến theo Sheet; 1 chưa có giá nên chưa cộng nợ'), text);
  assert.ok(text.indexOf('Thêm chuyến') < text.indexOf('Ghi giá'), 'mới nhất lên trên');
  const cut = await page.evaluate(() => [...document.querySelectorAll('#cards .card, #cards .why, #log span')].filter(node => node.scrollWidth > node.clientWidth + 1 && node.clientWidth > 0).map(node => node.textContent.slice(0, 40)));
  assert.deepEqual(cut, [], 'chữ trong khung bên phải xuống dòng, không bị cắt');
}));

test('Máy chạy: xem lại lượt cũ khi đang có lượt chạy thì có nút về trực tiếp, không tự kéo đi', () => withPage({ data: () => ({ ...base(), now: at(10, 7, 30), run: running() }) }, async page => {
  await page.waitForFunction(() => document.getElementById('now').textContent.startsWith('Đang đọc'));
  await page.locator('.slot.wrote').first().click();
  assert.equal(await page.locator('#go-live').isVisible(), true);
  assert.equal(await page.locator('#go-live').innerText(), 'Đang chạy: xem trực tiếp');
  assert.equal(await page.locator('#live-pill').innerText(), 'Đang xem lại');
  await page.waitForTimeout(3500);
  assert.ok((await page.locator('#run-title').innerText()).startsWith('Lượt 08:05'));
  await page.locator('#go-live').click();
  assert.ok((await page.locator('#run-title').innerText()).startsWith('Đang chạy'));
  assert.equal(await page.locator('#live-pill').innerText(), 'Trực tiếp');
}));

test('Máy chạy: bảng việc đổi mã khách thành tên, có link sổ, báo do AI viết; đếm và màu trên nhãn', () => withPage({}, async page => {
  assert.equal(await page.locator('#task-n').innerText(), '2');
  assert.equal(await page.locator('#task-n').getAttribute('class'), 'urgent');
  await page.locator('#tab-tasks').click();
  const text = await page.locator('#tasks').innerText();
  assert.ok(text.includes('KHACH CHIN còn lệch'), text);
  assert.ok(text.includes('Đã 4 lượt liền với KHACH CHIN'), text);
  assert.ok(!text.includes('kh-9'), text);
  assert.ok(text.includes('do AI viết'), text);
  assert.ok((await page.locator('#tasks a').first().getAttribute('href')).includes('customer=9'));
  await page.locator('#tab-money').click();
  assert.equal(await page.locator('#money-box').isVisible(), true);
}));

test('Máy chạy: chưa có Hermes thì nói chưa chạy; nội dung thẻ không chèn được HTML', () => withPage({ data: () => ({ ...base(), office: { state: 'off', tasks: { a: { title: '<img src=x onerror=alert(1)>', body: '<b>x</b>', level: 'info' } }, updated_at: null } }) }, async page => {
  await page.locator('#tab-tasks').click();
  assert.ok((await page.locator('#tasks').innerText()).includes('Hermes chưa chạy lần nào'));
  assert.equal(await page.locator('#tasks img').count(), 0);
  assert.ok((await page.locator('#tasks').innerText()).includes('<img src=x'));
}));

test('Máy chạy: ba ca diễn tập ghi rõ giả lập, không lẫn với lượt thật', () => withPage({}, async page => {
  await page.locator('[data-drill="many"]').click();
  await page.locator('#scrub').evaluate(node => { node.value = 1000; node.dispatchEvent(new Event('input')); });
  assert.ok((await page.locator('#run-title').innerText()).includes('giả lập'));
  assert.ok((await now(page)).includes('không ghi'));
  assert.ok(await page.locator('#status').evaluate(node => node.classList.contains('drill')));
  await page.locator('[data-drill="verify"]').click();
  await page.locator('#scrub').evaluate(node => { node.value = 1000; node.dispatchEvent(new Event('input')); });
  assert.ok((await page.locator('#cards').innerText()).includes('129.000.000đ'));
}));

test('Máy chạy: chọn nhân viên hiện việc của họ; bấm vào hình cũng được; tua cả ngày báo máy nghỉ và giờ chạy tới', () => withPage({}, async page => {
  await page.locator('#who-pick').selectOption('ghi');
  assert.ok((await page.locator('#who').innerText()).includes('Bàn duy nhất được ghi vào sổ'));
  await page.locator('#who-close').click();
  assert.equal(await page.locator('#who').isVisible(), false);
  const box = await page.locator('#office').boundingBox();
  await page.mouse.click(box.x + (306 / 860) * box.width, box.y + (190 / 860) * box.width);
  assert.ok((await page.locator('#who').innerText()).includes('Hermes'));
  await page.locator('#who-close').click();
  await page.locator('.whole').first().click();
  await page.locator('#speed').selectOption('30');
  assert.ok((await page.locator('#run-title').innerText()).startsWith('Cả ngày 6/11'));
  const first = await page.locator('#clock').innerText();
  await page.waitForTimeout(800);
  assert.notEqual(await page.locator('#clock').innerText(), first);
  await page.locator('#scrub').evaluate(node => { node.value = 0; node.dispatchEvent(new Event('input')); });
  assert.ok((await now(page)).startsWith('Máy đang nghỉ. Lượt kế lúc 08:05'));
}));

test('Máy chạy: bảng job hiện tình trạng, thiếu lịch là gạch; khổ hẹp không tràn trang', () => withPage({}, async page => {
  const rows = await page.locator('#jobs-body tr').allInnerTexts();
  assert.ok(rows[0].includes('Đối soát tự sửa'));
  assert.ok(rows[2].includes('Lần trước lỗi'));
  assert.ok(rows[2].includes('—'));
  const wide = await page.evaluate(() => { const limit = document.documentElement.clientWidth; return document.documentElement.scrollWidth <= limit ? [] : [...document.querySelectorAll('body *')].filter(node => node.getBoundingClientRect().right > limit + 1 && !node.closest('.officebox, .jobwrap')).map(node => `${node.tagName}#${node.id}.${node.className}:${(node.textContent ?? '').slice(0, 30)}:${node.parentElement.className}`).slice(0, 8); });
  assert.deepEqual(wide, [], 'khổ điện thoại không tràn ngang');
}, { width: 420, height: 800 }));
