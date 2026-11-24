const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// QUYEN-02: trang Người dùng và dải thẻ Quản trị. Dữ liệu giả, máy chủ giả giữ trạng thái như v7_access (version, lịch sử).
const BOSS = 'boss@example.test';
const at = '2026-11-20T10:35:00+07:00';
function fresh(extra = {}) {
  return {
    configured: true, broken: false, version: 2,
    users: [
      { login: BOSS, name: null, role: 'admin', fixed: true, added_by: null, added_at: null },
      { login: 'lan.ketoan@example.test', name: 'Lan', role: 'user', fixed: false, added_by: BOSS, added_at: at },
      { login: 'mot-login-rat-dai-cua-nhan-vien-moi-vao-lam@example-company-domain.test', name: null, role: 'user', fixed: false, added_by: BOSS, added_at: at },
    ],
    denied: [{ login: 'la@example.test', count: 3, last_at: at }],
    history: [{ at, actor: BOSS, action: 'add', login: 'lan.ketoan@example.test', before: null, after: { role: 'user', name: 'Lan' } }],
    ...extra,
  };
}

function makeServer(state) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body) => { response.writeHead(status, { 'Content-Type': type }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    if (route === '/api/v7/admin/users' && request.method === 'GET') {
      if (state.readFails) return out({ error: 'X', message: 'Máy chủ bận.' }, 503);
      const { users, ...rest } = state.data;
      const body = { ...rest, users: users.map(user => ({ ...user, me: user.login === BOSS })) };
      // Lượt đọc lại sau khi ghi chậm như máy CI bận: câu báo "Đã …" chỉ được hiện khi bảng đã vẽ lại.
      if (state.slowReload && state.posts.length) { setTimeout(() => out(body), 300); return undefined; }
      return out(body);
    }
    if (route === '/api/v7/admin/users' && request.method === 'POST') {
      let raw = '';
      request.on('data', chunk => { raw += chunk; });
      request.on('end', () => {
        const body = JSON.parse(raw);
        state.posts.push(body);
        const data = state.data;
        if (state.stale) { state.stale = false; data.version += 1; return out({ error: 'STALE', message: 'Danh sách vừa được người khác đổi. Trang đã đọc lại, xem rồi làm lại.' }, 409); }
        if (body.version !== data.version) return out({ error: 'STALE', message: 'lệch' }, 409);
        const user = data.users.find(item => item.login === body.login);
        const before = user ? { role: user.role, name: user.name } : null;
        if (body.action === 'add') {
          if (user) return out({ error: 'EXISTS', message: 'Login này đã có trong danh sách.' }, 409);
          data.users.push({ login: body.login, name: body.name ?? null, role: body.role, fixed: false, added_by: BOSS, added_at: at });
          data.denied = data.denied.filter(row => row.login !== body.login);
        } else if (body.action === 'remove') data.users = data.users.filter(item => item !== user);
        else if (body.action === 'role') user.role = body.role;
        else user.name = body.name;
        const now = data.users.find(item => item.login === body.login);
        data.history.unshift({ at, actor: BOSS, action: body.action, login: body.login, before, after: now ? { role: now.role, name: now.name } : null });
        data.version += 1;
        return out({ ok: true, version: data.version, changed: true });
      });
      return undefined;
    }
    if (route === '/api/v7/customers') return out({ customers: [] });
    if (route === '/api/v7/inbox') return out({ state: 'ready', books: [{ customer_id: 7, receipts: { ready: 2, review: 0, amount_vnd: '10' } }] });
    if (route === '/api/v7/dashboard') return out({ todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] } });
    if (route === '/api/v7/dashboard/debt') return out({ customers: [] });
    if (route === '/api/v7/todo-badge') return out({ inbox: { state: 'ready', books: [{ customer_id: 7, receipts: { ready: 2, review: 0, amount_vnd: '10' } }] },
      dashboard: { todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] } }, debt: { customers: [] } });
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 404);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(options, fn, viewport = { width: 1265, height: 560 }) {
  const state = { posts: [], ...options, data: fresh(options.data) };
  const server = makeServer(state);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await (await browser.newContext({ viewport })).newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = `http://127.0.0.1:${server.address().port}`;
    await page.goto(`${base}${options.page ?? '/nguoi-dung.html'}`);
    await fn(page, state, base);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    server.close();
  }
}
const rowOf = (page, login) => page.locator(`#users .nd-row[data-login="${login}"]`);
const noSideScroll = page => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
const openMenu = (page, name) => page.getByRole('button', { name: `Thao tác với ${name}` }).click();

test('Người dùng: menu sáu mục có Quản trị sáng, dải thẻ tám thẻ, dòng cố định và dòng của mình không đổi được', () => withPage({}, async page => {
  await page.locator('#users .nd-row').first().waitFor();
  const menu = (await page.locator('.app-nav nav a').allInnerTexts()).map(text => text.split('\n')[0]);
  assert.deepEqual(menu, ['Tổng quan', 'Công nợ theo tháng', 'Sổ khách', 'Bảng thu', 'Báo cáo tháng', 'Quản trị']);
  assert.equal((await page.locator('.app-nav nav a.active').innerText()).split('\n')[0], 'Quản trị');
  assert.equal(await page.locator('.app-nav nav a.active').getAttribute('href'), '/viec-can-lam.html');
  const tabs = page.locator('nav.admin-tabs a');
  assert.deepEqual((await tabs.allInnerTexts()).map(text => text.replace(/\d+$/, '').trim()), ['Việc cần làm', 'Máy chạy', 'Đội xe', 'Thông tin cty', 'Thu chi', 'Nhật ký', 'Người dùng', 'Khách']);
  assert.equal(await page.locator('nav.admin-tabs a.active').innerText(), 'Người dùng');
  // Dải thẻ nằm ngay trên thanh đầu trang, không đè.
  const strip = await page.locator('nav.admin-tabs').boundingBox(), head = await page.locator('.page-head.topbar').boundingBox();
  assert.ok(strip.height <= 41 && head.y >= strip.y + strip.height - 1, `dải ${JSON.stringify(strip)} đầu trang ${JSON.stringify(head)}`);
  const boss = rowOf(page, BOSS);
  assert.match(await boss.innerText(), /boss\s*Bạn[\s\S]*Quản lý/);
  assert.equal(await boss.locator('button, select').count(), 0);
  const lan = rowOf(page, 'lan.ketoan@example.test');
  assert.match(await lan.locator('.nd-who').innerText(), /^L\s+Lan\s+lan\.ketoan@example\.test$/);
  assert.equal(await lan.locator('select').inputValue(), 'user');
  assert.equal(await page.locator('#user-count').innerText(), '3 người · 1 quản lý');
  // Lịch sử là câu ngắn: chính mình ghi "Bạn", login còn trong danh sách hiện tên gọi.
  assert.match(await page.locator('#history').innerText(), /Bạn cho Lan vào làm Nhân viên/);
  // Một trục: cột Vai trò thẳng hàng giữa dòng khóa và dòng có ô chọn, nội dung căn trái theo dải thẻ.
  const lockedBox = await boss.locator('.nd-box').boundingBox(), selectBox = await lan.locator('select').boundingBox();
  assert.equal(Math.round(lockedBox.x), Math.round(selectBox.x));
  assert.equal(Math.round(lockedBox.width), Math.round(selectBox.width));
  const card = await page.locator('.nd-card').first().boundingBox();
  assert.ok(card.x < strip.x + 40, `thẻ ${card.x} lệch xa dải thẻ ${strip.x}`);
  assert.ok(await noSideScroll(page));
  // Số "sổ còn việc" lên cả mục Quản trị và thẻ Việc cần làm.
  await page.locator('#todo-badge:not([hidden])').waitFor();
  assert.equal(await page.locator('#todo-badge').innerText(), await page.locator('nav.admin-tabs .tab-badge').innerText());
  if (process.env.SHOTS_DIR) await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'nguoi-dung-1280.png') });
}));

test('Người dùng: cho vào login xin vào, đổi vai trò ở ô chọn, bỏ quyền qua nút ⋯ phải hỏi lại, Thôi thì không gửi gì', () => withPage({ slowReload: true }, async (page, state) => {
  const request = page.locator('#denied .nd-row', { hasText: 'la@example.test' });
  await request.waitFor();
  assert.match(await request.innerText(), /Xin vào sổ · 3 lần/);
  await request.getByRole('button', { name: 'Cho la@example.test vào làm Nhân viên' }).click();
  await page.locator('#flash', { hasText: 'Đã cho la@example.test vào làm Nhân viên.' }).waitFor();
  assert.equal(await page.locator('#denied .nd-row').count(), 0);
  assert.deepEqual(state.posts.at(-1), { action: 'add', login: 'la@example.test', role: 'user', version: 2 });
  await rowOf(page, 'la@example.test').waitFor();

  await rowOf(page, 'lan.ketoan@example.test').locator('select').selectOption('admin');
  await page.locator('#flash', { hasText: 'Đã đổi Lan thành Quản lý.' }).waitFor();
  assert.equal(await rowOf(page, 'lan.ketoan@example.test').locator('select').inputValue(), 'admin');
  assert.deepEqual(state.posts.at(-1), { action: 'role', login: 'lan.ketoan@example.test', role: 'admin', version: 3 });

  // Nút ⋯: Escape và bấm ra ngoài đều đóng menu, không gửi gì.
  const posts = state.posts.length;
  await openMenu(page, 'Lan');
  await page.getByRole('menuitem', { name: 'Sửa tên gọi' }).waitFor();
  if (process.env.SHOTS_DIR) await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'nguoi-dung-menu.png') });
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.nd-menu').count(), 0);
  await openMenu(page, 'Lan');
  await page.locator('#history-title').click();
  assert.equal(await page.locator('.nd-menu').count(), 0);

  await openMenu(page, 'Lan');
  await page.getByRole('menuitem', { name: 'Bỏ quyền vào' }).click();
  const confirm = page.locator('.nd-row.confirm');
  assert.match(await confirm.innerText(), /Bỏ quyền vào của Lan \(lan\.ketoan@example\.test\)\? Họ sẽ không mở được sổ nữa\./);
  await confirm.getByRole('button', { name: 'Thôi' }).click();
  assert.equal(state.posts.length, posts);
  await openMenu(page, 'Lan');
  await page.getByRole('menuitem', { name: 'Bỏ quyền vào' }).click();
  await page.locator('.nd-row.confirm').getByRole('button', { name: 'Bỏ quyền' }).click();
  await page.locator('#flash', { hasText: 'Đã bỏ quyền vào của Lan.' }).waitFor();
  assert.equal(await rowOf(page, 'lan.ketoan@example.test').count(), 0);
  assert.match(await page.locator('#history').innerText(), /Bạn bỏ quyền vào của lan\.ketoan \(trước là Quản lý\)/);
}));

test('Người dùng: hộp thoại Thêm người kiểm dạng login trước khi gửi, đặt tên; trùng thì báo câu của máy chủ trong hộp', () => withPage({ slowReload: true }, async (page, state) => {
  await page.locator('#users .nd-row').first().waitFor();
  await page.locator('#add-open').click();
  assert.equal(await page.locator('#add-dialog').evaluate(node => node.open), true);
  await page.locator('#add-login').fill('khong co a cong');
  await page.locator('#add-submit').click();
  assert.match(await page.locator('#add-error').innerText(), /ten@mien/);
  if (process.env.SHOTS_DIR) await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'nguoi-dung-them.png') });
  assert.equal(await page.locator('#add-login').getAttribute('aria-invalid'), 'true');
  assert.equal(state.posts.length, 0);
  await page.locator('#add-login').fill('moi@example.test');
  assert.equal(await page.locator('#add-error').isHidden(), true);
  await page.locator('#add-name').fill('Hoa');
  await page.locator('input[name="add-role"][value="admin"]').check();
  await page.locator('#add-submit').click();
  await page.locator('#flash', { hasText: 'Đã cho moi@example.test vào làm Quản lý.' }).waitFor();
  assert.deepEqual(state.posts.at(-1), { action: 'add', login: 'moi@example.test', role: 'admin', name: 'Hoa', version: 2 });
  assert.equal(await page.locator('#add-dialog').evaluate(node => node.open), false);
  // Mở lại thì ô trống; login trùng thì câu của máy chủ hiện trong hộp, hộp vẫn mở.
  await page.locator('#add-open').click();
  assert.equal(await page.locator('#add-login').inputValue(), '');
  await page.locator('#add-login').fill('moi@example.test');
  await page.locator('#add-submit').click();
  await page.locator('#add-error', { hasText: 'Login này đã có trong danh sách.' }).waitFor();
  assert.equal(await page.locator('#add-dialog').evaluate(node => node.open), true);
  await page.locator('#add-dialog').getByRole('button', { name: 'Thôi' }).click();
  assert.equal(await page.locator('#add-dialog').evaluate(node => node.open), false);
  // Sửa tên qua nút ⋯, Enter để lưu.
  await openMenu(page, 'Hoa');
  await page.getByRole('menuitem', { name: 'Sửa tên gọi' }).click();
  await page.locator('.nd-rename input').fill('Hoa kế toán');
  await page.locator('.nd-rename input').press('Enter');
  await page.locator('#flash', { hasText: 'Đã lưu tên gọi của moi@example.test.' }).waitFor();
  assert.match(await rowOf(page, 'moi@example.test').innerText(), /Hoa kế toán/);
}));

test('Người dùng: bản cũ thì đọc lại và nói rõ; đọc lỗi có Thử lại; máy chủ chưa bật thì chỉ xem', async () => {
  // Lượt đọc lại chậm như máy CI bận (lượt `main` ngày 22/11/2026 đỏ hai lần ở đây): câu "vừa được người khác đổi" chỉ được hiện khi
  // bảng đã đọc lại và vẽ xong, nên lúc thấy câu thì ô chọn đã về giá trị của máy chủ.
  await withPage({ stale: true, slowReload: true }, async page => {
    await page.locator('#users .nd-row').first().waitFor();
    await rowOf(page, 'lan.ketoan@example.test').locator('select').selectOption('admin');
    await page.locator('#error', { hasText: 'Danh sách vừa được người khác đổi' }).waitFor();
    assert.equal(await rowOf(page, 'lan.ketoan@example.test').locator('select').inputValue(), 'user');
  });
  await withPage({ readFails: true }, async (page, state) => {
    await page.locator('#error', { hasText: 'Máy chủ bận.' }).waitFor();
    state.readFails = false;
    await page.locator('#retry').click();
    await page.locator('#users .nd-row').first().waitFor();
    assert.equal(await page.locator('#error').isHidden(), true);
  });
  await withPage({ data: { configured: false, denied: [] } }, async page => {
    await page.locator('#users .nd-row').first().waitFor();
    assert.equal(await page.locator('#add-open').isHidden(), true);
    assert.equal(await page.locator('#users button, #users select').count(), 0);
    assert.match(await page.locator('#users-note').innerText(), /chỉ xem/);
  });
});

test('Người dùng: điện thoại 390px không cuộn ngang, login dài xuống dòng, hộp thoại vừa màn', () => withPage({}, async page => {
  await page.locator('#users .nd-row').first().waitFor();
  assert.ok(await noSideScroll(page));
  const long = rowOf(page, 'mot-login-rat-dai-cua-nhan-vien-moi-vao-lam@example-company-domain.test').locator('.sub');
  assert.ok((await long.boundingBox()).width <= 390);
  if (process.env.SHOTS_DIR) await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'nguoi-dung-390.png'), fullPage: true });
  await page.locator('#add-open').click();
  const box = await page.locator('#add-dialog').boundingBox();
  assert.ok(box.x >= 0 && box.x + box.width <= 390, JSON.stringify(box));
}, { width: 390, height: 800 }));

test('Dải thẻ Quản trị có trên các màn quản lý, không có trên trang làm sổ', () => withPage({ page: '/thong-tin-cty.html' }, async (page, _state, base) => {
  await page.locator('nav.admin-tabs').waitFor();
  assert.equal(await page.locator('nav.admin-tabs a.active').innerText(), 'Thông tin cty');
  await page.goto(`${base}/bang-thu.html`);
  await page.locator('.app-nav nav a').first().waitFor();
  assert.equal(await page.locator('nav.admin-tabs').count(), 0);
  assert.equal(await page.locator('.app-nav nav a.active').innerText(), 'Bảng thu');
}));
