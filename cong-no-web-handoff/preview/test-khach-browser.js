const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// KHACH-WEB-01: thẻ Khách của Quản trị. Dữ liệu giả; máy chủ giả giữ sổ, tên booking, phiên bản sổ và khóa chống ghi trùng.
function fresh(extra = {}) {
  return {
    customers: [
      { id: 9, name: 'KHACH CU GIA', status: 'active', commodity: 'Dừa', transport_mode: 'CANG', booking_names: ['CHU HANG CU', 'CHU HANG HAI DUONG'] },
      { id: 10, name: 'KHACH GIA NONG 413', status: 'active', commodity: 'Dừa', transport_mode: 'CANG', booking_names: [] },
      { id: 11, name: 'SO NHAP GIA', status: 'NO_BASELINE', commodity: null, transport_mode: null, booking_names: [] },
      { id: 12, name: 'ĐƯỜNG BỘ KHÁCH GIẢ', status: 'active', commodity: 'Sầu riêng', transport_mode: 'BO', booking_names: [] },
      { id: 13, name: 'KHACH CHUOI GIA', status: 'active', commodity: 'Chuối', transport_mode: 'CANG', booking_names: [] },
      { id: 14, name: 'KHACH LUU TRU GIA', status: 'active', commodity: 'Dừa', transport_mode: null, booking_names: ['CHU HANG LUU'], archived: true },
    ],
    unmapped: { state: 'ok', road_state: 'ok', sheet_state: 'ok', snapshot_created_at: '2026-11-24T01:00:00+00:00', owners: [
      { name: 'CHU HANG GIA 413', family: 'BIEN', trips: 5, first: '2026-11-02', last: '2026-11-15', commodities: ['Dừa'], containers: ['FAKU1000001'],
        sheet_tabs: [{ tab: 'KHACH GIA NONG 413', book_name: 'KHACH GIA NONG 413', trips: 5, customer_id: 10 }], suggest_customer_id: 10, many_books: 0, assigned_to: null },
      { name: 'KHO GIA', family: 'BO', trips: 2, first: '2026-11-10', last: '2026-11-12', commodities: [], containers: ['ROAU1000003'],
        sheet_tabs: [], suggest_customer_id: null, many_books: 2, assigned_to: null },
      { name: 'CHU HANG LA GIA', family: 'BIEN', trips: 1, first: '2026-11-22', last: '2026-11-22', commodities: ['CHUỐI'], containers: ['FAKU1000002'],
        sheet_tabs: [{ tab: 'TAB CHUA: CO SO GIA', book_name: 'TAB CHUA CO SO GIA', trips: 1, customer_id: null }], suggest_customer_id: null, many_books: 0, assigned_to: null },
      { name: 'CHU HANG BO GIA', family: 'BO', trips: 1, first: '2026-11-20', last: '2026-11-20', commodities: [], containers: ['ROAU1000005'],
        sheet_tabs: [], suggest_customer_id: null, many_books: 0, assigned_to: null },
      { name: 'CHU HANG HAI DUONG', family: 'BO', trips: 1, first: '2026-11-11', last: '2026-11-11', commodities: [], containers: ['ROAU1000004'],
        sheet_tabs: [], suggest_customer_id: null, many_books: 0, assigned_to: { id: 9, name: 'KHACH CU GIA' } },
    ] },
    ...extra,
  };
}

function makeServer(state) {
  const versions = new Map([[9, 4], [10, 7], [12, 2], [13, 1]]);
  const done = new Map();   // khóa chống ghi trùng -> kết quả
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body) => { response.writeHead(status, { 'Content-Type': type }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    state.calls.push(`${request.method} ${route}${url.search}`);
    if (route === '/api/v7/admin/customers' && request.method === 'GET') return out(state.data);
    if (route === '/api/v7/ledger/events') {
      const id = Number(url.searchParams.get('customer'));
      return out({ customer_id: id, version: versions.get(id) ?? 1, events: [] });
    }
    if (request.method === 'POST' && (route === '/api/v7/admin/booking-names' || route === '/api/v7/admin/customers')) {
      let raw = '';
      request.on('data', chunk => { raw += chunk; });
      request.on('end', () => {
        const body = JSON.parse(raw);
        state.posts.push({ route, body });
        if (done.has(body.idempotency_key)) return state.drop ? request.socket.destroy() : out(done.get(body.idempotency_key));
        if (state.reject) { const [status, code, message] = state.reject; state.reject = null; return out({ error: code, message }, status); }
        const data = state.data;
        let result;
        if (route === '/api/v7/admin/customers') {
          const id = 20 + data.customers.length;
          data.customers.push({ id, name: body.book_name, status: 'active', commodity: body.commodity, transport_mode: body.transport_mode,
            booking_names: body.booking_names });
          data.unmapped.owners = data.unmapped.owners.filter(owner => !body.booking_names.includes(owner.name));
          result = { customer_id: id, booking_names: body.booking_names, version: 5, name: body.book_name };
        } else {
          const book = data.customers.find(item => item.id === body.customer_id);
          if (body.expected_version !== versions.get(book.id)) return out({ error: 'STALE_LEDGER', message: 'Sổ đã thay đổi. Tải lại rồi thử tiếp.' }, 409);
          book.booking_names = body.remove ? book.booking_names.filter(name => name !== body.name) : [...book.booking_names, body.name].sort();
          if (!body.remove) data.unmapped.owners = data.unmapped.owners.filter(owner => owner.name !== body.name);
          versions.set(book.id, versions.get(book.id) + 1);
          result = { booking_names: book.booking_names, version: versions.get(book.id) };
        }
        done.set(body.idempotency_key, result);
        // Máy chủ ghi xong nhưng mất phản hồi: cắt mọi lần (Chrome tự gửi lại khi kết nối bị cắt một lần) tới khi test cho phép.
        return state.drop ? request.socket.destroy() : out(result);
      });
      return undefined;
    }
    if (route === '/api/v7/customers') return out({ customers: [] });
    if (route === '/api/v7/todo-badge') return out({ inbox: { state: 'ready', books: [] }, dashboard: { todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] } }, debt: { customers: [] } });
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 404);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(options, fn, viewport = { width: 1265, height: 560 }) {
  const state = { calls: [], posts: [], ...options, data: fresh(options.data) };
  const server = makeServer(state);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await (await browser.newContext({ viewport })).newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/khach.html`);
    await page.locator('#books .kh-row, #books .nd-empty').first().waitFor();
    await fn(page, state);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    server.close();
  }
}
const owner = (page, name, family = 'BIEN') => page.locator(`#owners .kh-owner[data-owner="${family}|${name}"]`);
const book = (page, id) => page.locator(`#books .kh-row[data-id="${id}"]`);
const noSideScroll = page => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
const flashed = page => page.locator('#flash').innerText();

test('Khách: thẻ Khách sáng trong Quản trị; chủ hàng chưa có sổ kèm tab Sheet và gợi ý; sổ đang hoạt động kèm tên booking', () => withPage({}, async page => {
  assert.equal(await page.locator('nav.admin-tabs a.active').innerText(), 'Khách');
  assert.equal(await page.locator('#owner-count').innerText(), '5 tên · 10 chuyến');
  const main = await owner(page, 'CHU HANG GIA 413').innerText();
  assert.ok(main.includes('5 chuyến') && main.includes('02/11/2026 – 15/11/2026') && main.includes('Dừa')
    && main.includes('Sheet ghi ở tab: KHACH GIA NONG 413 (5)'), main);
  const options = await owner(page, 'CHU HANG GIA 413').locator('.kh-pick option').allInnerTexts();
  assert.equal(options[1], 'KHACH GIA NONG 413 · gợi ý', 'sổ gợi ý đứng đầu');
  assert.equal(await owner(page, 'CHU HANG GIA 413').locator('.kh-pick').inputValue(), '10', 'sổ gợi ý chọn sẵn');
  assert.deepEqual(await owner(page, 'CHU HANG GIA 413').locator('.nd-btn.primary').allInnerTexts(), ['Gán vào sổ'], 'có gợi ý: nút chính là Gán');
  assert.deepEqual(await owner(page, 'CHU HANG LA GIA').locator('.nd-btn.primary').allInnerTexts(), ['Tạo sổ mới'], 'không gợi ý: nút chính là Tạo sổ');
  assert.ok(!options.some(text => text.includes('SO NHAP GIA')), 'sổ chưa hoạt động không nhận tên');
  assert.ok(!options.some(text => text.includes('ĐƯỜNG BỘ KHÁCH GIẢ') || text.includes('KHACH LUU TRU GIA')), 'chuyến biển: không sổ đi bộ, không sổ lưu trữ');
  assert.deepEqual(await owner(page, 'CHU HANG BO GIA', 'BO').locator('.kh-pick option').allInnerTexts(), ['Chọn sổ…', 'ĐƯỜNG BỘ KHÁCH GIẢ'], 'chuyến bộ: chỉ sổ không đi biển');
  const kho = owner(page, 'KHO GIA', 'BO');
  assert.ok((await kho.innerText()).includes('đã vào 2 sổ khác nhau theo tab Sheet (thường là kho)'));
  assert.equal(await kho.locator('button, select').count(), 0, 'tên kho: không có nút gán');
  const twice = owner(page, 'CHU HANG HAI DUONG', 'BO');
  assert.ok((await twice.innerText()).includes('Tên này đã gán cho sổ KHACH CU GIA'));
  assert.equal(await twice.locator('button, select').count(), 0);
  assert.equal(await page.locator('#book-count').innerText(), '5 sổ · 2 sổ có tên booking');
  const old = await book(page, 9).innerText();
  assert.ok(old.includes('KHACH CU GIA') && old.includes('Dừa · Biển') && old.includes('CHU HANG CU'), old);
  assert.equal(await book(page, 9).locator('a').getAttribute('href'), '/so-khach-v7-live.html?customer=9');
  assert.ok((await book(page, 14).innerText()).includes('lưu trữ'));
  assert.equal(await book(page, 14).locator('[data-act="add"]').count(), 0, 'sổ lưu trữ không thêm tên');
  assert.ok(await noSideScroll(page));
}));

test('Khách: gán tên vào sổ phải chọn sổ, hỏi lại rồi mới gửi với phiên bản vừa đọc; xong thì tên rời danh sách', () => withPage({}, async (page, state) => {
  await owner(page, 'CHU HANG LA GIA').getByRole('button', { name: 'Gán vào sổ' }).click();
  assert.equal(await page.locator('#error').innerText(), 'Chọn sổ để gán tên trước.');
  assert.equal(state.posts.length, 0);
  await owner(page, 'CHU HANG GIA 413').locator('.kh-pick').selectOption('10');
  await owner(page, 'CHU HANG GIA 413').getByRole('button', { name: 'Gán vào sổ' }).click();
  const ask = await page.locator('#owners .kh-ask').innerText();
  assert.ok(ask.includes('Gán tên CHU HANG GIA 413 vào sổ KHACH GIA NONG 413?') && ask.includes('chưa có giá'), ask);
  assert.equal(state.posts.length, 0, 'chưa gửi khi chưa xác nhận');
  await page.locator('#owners .kh-ask').getByRole('button', { name: 'Gán', exact: true }).click();
  await page.locator('#flash').waitFor();
  assert.ok((await flashed(page)).startsWith('Đã gán CHU HANG GIA 413 vào sổ KHACH GIA NONG 413.'));
  assert.equal(state.posts.length, 1);
  const sent = state.posts[0].body;
  assert.deepEqual({ ...sent, idempotency_key: typeof sent.idempotency_key }, { customer_id: 10, expected_version: 7, name: 'CHU HANG GIA 413', remove: false, idempotency_key: 'string' });
  assert.ok(state.calls.indexOf('GET /api/v7/ledger/events?customer=10') < state.calls.indexOf('POST /api/v7/admin/booking-names'));
  assert.equal(await owner(page, 'CHU HANG GIA 413').count(), 0);
  assert.ok((await book(page, 10).innerText()).includes('CHU HANG GIA 413'));
}));

test('Khách: tạo sổ mới từ chủ hàng điền sẵn tên sổ của tab Sheet, mặt hàng theo danh mục, đường; mất phản hồi thì bấm lại cùng khóa', () => withPage({}, async (page, state) => {
  await owner(page, 'CHU HANG LA GIA').getByRole('button', { name: 'Tạo sổ mới' }).click();
  assert.equal(await page.locator('#create-name').inputValue(), 'TAB CHUA CO SO GIA', 'tên sổ máy sẽ tạo cho tab (bỏ dấu file xuất không nhận)');
  assert.equal(await page.locator('#create-commodity').inputValue(), 'Chuối', 'mặt hàng booking ứng tên trong danh mục');
  assert.deepEqual(await page.locator('#create-commodity option').allInnerTexts(), ['Chưa gán', 'Chuối', 'Dừa', 'Sầu riêng']);
  assert.equal(await page.locator('#create-booking').inputValue(), 'CHU HANG LA GIA');
  assert.equal(await page.locator('input[name="create-mode"]:checked').getAttribute('value'), 'CANG');
  state.drop = true;
  await page.locator('#create-submit').click();
  await page.locator('#create-error').filter({ hasText: 'Mất kết nối' }).waitFor();
  assert.equal(await page.locator('#create-commodity').inputValue(), 'Chuối', 'đọc lại danh sách không làm mất mặt hàng đang chọn');
  state.drop = false;
  await page.locator('#create-submit').click();
  await page.locator('#flash').waitFor();
  assert.equal(await page.locator('#create-dialog').evaluate(el => el.open), false);
  assert.ok(state.posts.length >= 2);
  assert.equal(new Set(state.posts.map(post => post.body.idempotency_key)).size, 1, 'bấm lại cùng khóa');
  assert.deepEqual({ ...state.posts.at(-1).body, idempotency_key: 'k' },
    { book_name: 'TAB CHUA CO SO GIA', commodity: 'Chuối', transport_mode: 'CANG', booking_names: ['CHU HANG LA GIA'], idempotency_key: 'k' });
  assert.equal(state.data.customers.filter(item => item.name === 'TAB CHUA CO SO GIA').length, 1, 'một sổ');
  assert.equal(await owner(page, 'CHU HANG LA GIA').count(), 0);
}));

test('Khách: máy chủ từ chối thì báo trong hộp và bỏ khóa; Thêm khách mới để trống tên thì không gửi', () => withPage({}, async (page, state) => {
  await page.locator('#create-open').click();
  await page.locator('#create-submit').click();
  assert.equal(await page.locator('#create-error').innerText(), 'Gõ tên sổ.');
  await page.locator('#create-name').fill('KHACH CU GIA');
  await page.locator('#create-booking').fill('ten  thu\n\nten thu');
  state.reject = [409, 'BOOK_EXISTS', 'Sổ tên này đã có.'];
  await page.locator('#create-submit').click();
  await page.locator('#create-error').filter({ hasText: 'Sổ tên này đã có.' }).waitFor();
  await page.locator('#create-name').fill('KHACH MOI GIA');
  await page.locator('input[name="create-mode"][value="BO"]').check();
  await page.locator('#create-submit').click();
  await page.locator('#flash').filter({ hasText: 'Đã tạo sổ KHACH MOI GIA.' }).waitFor();
  assert.equal(state.posts.length, 2);
  assert.notEqual(state.posts[0].body.idempotency_key, state.posts[1].body.idempotency_key, 'lệnh bị từ chối không giữ khóa');
  assert.deepEqual(state.posts[1].body.booking_names, ['TEN THU']);
  assert.equal(state.posts[1].body.transport_mode, 'BO');
  assert.equal(state.posts[1].body.commodity, null);
}));

test('Khách: máy chủ lỗi hay khóa đã dùng cho nội dung khác thì chưa rõ đã ghi: giữ khóa, đọc lại danh sách, nói rõ', () => withPage({}, async (page, state) => {
  await page.locator('#create-open').click();
  await page.locator('#create-name').fill('KHACH MOI GIA');
  const reads = () => state.calls.filter(call => call === 'GET /api/v7/admin/customers').length;
  const before = reads();
  state.reject = [502, 'BAD_GATEWAY', 'Lỗi cổng.'];
  await page.locator('#create-submit').click();
  await page.locator('#create-error').filter({ hasText: 'chưa rõ sổ đã tạo chưa' }).waitFor();
  assert.ok(reads() > before, 'đọc lại danh sách để xem sổ đã có chưa');
  state.reject = [409, 'IDEMPOTENCY_CONFLICT', 'Mã yêu cầu đã dùng cho nội dung khác.'];
  await page.locator('#create-name').fill('KHACH MOI GIA 2');
  await page.locator('#create-submit').click();
  await page.locator('#create-error').filter({ hasText: 'đóng hộp này rồi mở lại' }).waitFor();
  assert.equal(await page.locator('#create-dialog').evaluate(el => el.open), true);
  await page.locator('#create-submit').click();
  await page.locator('#flash').waitFor();
  assert.equal(new Set(state.posts.map(post => post.body.idempotency_key)).size, 1, 'chưa rõ kết quả thì không đổi khóa');
}));

test('Khách: bỏ tên hỏi lại kiểu nguy hiểm; thêm tên gõ thường thì gửi chữ hoa; tìm theo tên sổ hay tên booking, bỏ dấu', () => withPage({}, async (page, state) => {
  await book(page, 9).getByRole('button', { name: 'Bỏ tên CHU HANG CU khỏi sổ KHACH CU GIA' }).click();
  assert.ok((await page.locator('#books .kh-ask.danger').innerText()).includes('Bỏ tên CHU HANG CU khỏi sổ KHACH CU GIA?'));
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#books .kh-ask').count(), 0);
  await book(page, 9).getByRole('button', { name: 'Bỏ tên CHU HANG CU khỏi sổ KHACH CU GIA' }).click();
  await page.locator('#books .kh-ask .danger').click();
  await page.locator('#flash').waitFor();
  assert.deepEqual({ ...state.posts[0].body, idempotency_key: 'k' }, { customer_id: 9, expected_version: 4, idempotency_key: 'k', name: 'CHU HANG CU', remove: true });
  await book(page, 12).getByRole('button', { name: 'Thêm tên trên booking cho sổ ĐƯỜNG BỘ KHÁCH GIẢ' }).click();
  await page.locator('.kh-add-box input').fill('kho  moi 401');
  await page.keyboard.press('Enter');
  await page.locator('#flash').filter({ hasText: 'KHO MOI 401' }).waitFor();
  assert.equal(state.posts[1].body.name, 'KHO MOI 401');
  assert.ok((await book(page, 12).innerText()).includes('KHO MOI 401'));
  await page.locator('#book-search').fill('duong bo khach');
  assert.deepEqual(await page.locator('#books .kh-row').evaluateAll(rows => rows.map(row => row.dataset.id)), ['12']);
  await page.locator('#book-search').fill('kho moi');
  assert.deepEqual(await page.locator('#books .kh-row').evaluateAll(rows => rows.map(row => row.dataset.id)), ['12']);
}));

test('Khách: bản chụp booking đọc lỗi hay cũ thì nói rõ; chữ lạ không chèn HTML; khổ điện thoại không tràn ngang', async () => {
  await withPage({ data: { unmapped: { state: 'unavailable', owners: [] } } }, async page => {
    assert.ok((await page.locator('#owners').innerText()).includes('Không đọc được bản chụp booking'));
    assert.equal(await page.locator('#owner-count').innerText(), '');
  });
  const evil = '<img src=x onerror=alert(1)>';
  await withPage({ data: { unmapped: { state: 'ok', road_state: 'unavailable', snapshot_stale_minutes: 120, owners: [
    { name: evil, family: 'BO', trips: 1, first: '2026-11-03', last: '2026-11-03', commodities: [], containers: [], sheet_tabs: [], suggest_customer_id: null },
    { name: 'KHO GIA', family: 'BO', trips: 2, first: '2026-11-10', last: '2026-11-12', commodities: [], containers: [], sheet_tabs: [], suggest_customer_id: null, many_books: 3 }] } } }, async page => {
    assert.equal(await page.locator('#owners img').count(), 0);
    const text = await page.locator('#owners').innerText();
    assert.ok(text.includes(evil) && text.includes('Chưa đọc được bản chụp CONT_BO') && text.includes('Bản chụp booking đã cũ 120 phút'), text);
    assert.ok(await noSideScroll(page));
    const low = await page.evaluate(() => [...document.querySelectorAll('.kh .nd-btn')].filter(el => el.offsetParent && el.getBoundingClientRect().height < 36).length);
    assert.equal(low, 0);
  }, { width: 390, height: 800 });
});
