const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

// ZALO-CHAT-01: tab Chat Zalo — danh sách hội thoại, tin theo trang (trang 0 mới nhất), tìm, lỗi 503.
// Máy chủ giả trả JSON theo đúng hợp đồng /api/v7/zalo/*; dữ liệu bịa, không có nội dung chat thật.
const OWNER = 'a'.repeat(64);
const KHACH = 'b'.repeat(64);
const CONV_A = '1'.repeat(64);
const CONV_B = '2'.repeat(64);
const DAY = 1_760_000_000_000; // 09/10/2025 giờ VN
const msg = (id, own, stamp, text, extra = {}) => ({
  message_id: id, sender_id: own ? OWNER : KHACH, is_own: own, timestamp_ms: stamp, message_type: 1, type_label: 'Văn bản',
  status: own ? 2 : 4, status_label: own ? 'đã gửi' : 'đã nhận', body_kind: 'text', body_text: text, body_state: 'decoded_basic_encryption',
  attachment: null, ...extra,
});
// 7 tin, m1 cũ nhất → m7 mới nhất.
const ALL = [
  msg('m1', true, DAY + 1000, 'Chào anh, tháng này còn 3 cont chưa thanh toán'),
  msg('m2', false, DAY + 2000, 'Dạ để em xem lại'),
  msg('m3', false, DAY + 3000, 'Em gửi hình cont nha', { message_type: 2, type_label: 'Ảnh', body_kind: 'card', body_text: null,
    attachment: { state: 'matched', title: null, url_count: 2, media_items: [{ source_table: 'image', ext_type: null, title: null, file_size: null, width: 1920, height: 2560 }] } }),
  msg('m4', true, DAY + 86_400_000, 'Anh gửi file công nợ', { message_type: 19, type_label: 'Tệp',
    attachment: { state: 'unmatched', title: 'cong-no.pdf', url_count: 1, media_items: [] } }),
  msg('m5', false, DAY + 86_401_000, null, { body_kind: 'missing', body_text: null }),
  msg('m6', true, DAY + 86_402_000, 'Mai em chuyển nhé'),
  msg('m7', false, DAY + 86_403_000, 'Dạ vâng ạ'),
];
const conversations = () => ({ total: 2, conversations: [
  { conversation_id: CONV_A, display_name: 'Nguyễn Hoàng Vũ', name_status: 'matched_storage_info_cache', message_count: 7, last_message_at: DAY + 86_403_000, last_own_message_at: DAY + 86_402_000, participant_count: 2 },
  { conversation_id: CONV_B, display_name: null, name_status: 'unmatched', message_count: 1, last_message_at: DAY, last_own_message_at: null, participant_count: 1 },
] });
const report = () => ({ status: 'EXPORTED_WITH_GAPS', conversation_count: 2, message_count: 8, named_conversations: 1, owner_conversations: 1, body_missing: 1, attachment_matched: 1, attachment_unmatched: 1, skipped_lines: 0 });
const { foldText: fold } = require('./cong-no-format.js');   // cùng quy tắc với fold của web/v7_zalo_chat.py

// ZALO-GROUP-01: gói web — một group có tên người gửi và ảnh; 120 tin để thử mở thẳng một tin ở trang giữa.
const GROUP = '5'.repeat(64);
const PIC = 'e'.repeat(64);
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
const people = { [OWNER]: 'Hào', [KHACH]: 'Vũ', ['c'.repeat(64)]: 'Lan kế toán' };
const groupRows = Array.from({ length: 120 }, (_, i) => {
  const sender = i % 3 === 0 ? OWNER : i % 3 === 1 ? KHACH : 'c'.repeat(64);
  const row = msg(`g${i}`, sender === OWNER, DAY + i * 60_000, `Tin số ${i}`, { sender_id: sender, sender_name: people[sender], media: [], deleted: false });
  if (i === 118) return { ...row, message_type: 2, type_label: 'Ảnh', body_kind: 'card', body_text: null, media: [{ id: PIC, mime: 'image/png', width: 1, height: 1 }] };
  if (i === 119) return { ...row, message_type: 2, type_label: 'Ảnh', body_kind: 'card', body_text: null, media: [] };
  return row;
});

// ZALO-GROUP-01 G4: sổ công nợ giả cho gắn group ↔ sổ và dấu tin, theo hợp đồng /api/v7/zalo/link(s), /api/v7/marks.
// Trạng thái dấu như hàm get_marks lúc chưa có phiếu thu: hứa trả "pending", khách báo đã chuyển "waiting".
const todayVn = (days = 0) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(Date.now() + days * 86_400_000);
function ledgerWorld() {
  return { links: [], marks: [], posts: [], customers: [{ id: 7, name: 'NGUYEN HOANG VU', label: 'Nguyễn Hoàng Vũ · Sầu riêng' },
    { id: 8, name: 'TRAN LAN', label: 'Trần Lan · Thanh long' }] };
}
function ledgerRoute(world, req, url, body, json) {
  if (req.method === 'GET' && url.pathname === '/api/v7/zalo/links') return json(200, { links: world.links });
  if (req.method === 'GET' && url.pathname === '/api/v7/customers') return json(200, { customers: world.customers });
  if (req.method === 'GET' && url.pathname === '/api/v7/marks') {
    const id = url.searchParams.get('conversation');
    return json(200, { marks: world.marks.filter(row => row.conversation_id === id).slice().reverse() });
  }
  if (req.method !== 'POST') return false;
  world.posts.push({ path: url.pathname, body });
  if (url.pathname === '/api/v7/zalo/link') {
    const book = world.customers.find(row => row.id === body.customer_id);
    world.links.push({ conversation_id: body.conversation_id, customer_id: book.id, customer_name: book.label });
    return json(200, world.links.at(-1));
  }
  if (url.pathname === '/api/v7/zalo/unlink') {
    world.links = world.links.filter(row => !(row.conversation_id === body.conversation_id && row.customer_id === body.customer_id));
    return json(200, { unlinked: true });
  }
  if (url.pathname === '/api/v7/marks') {
    const old = world.marks.find(row => row.idempotency_key === body.idempotency_key);
    if (old) return json(200, { ...old, replayed: true });
    const book = world.links.find(row => row.customer_id === body.customer_id);
    // Tiền trả về dạng chuỗi như get_marks (ARCH-03).
    world.marks.push({ ...body, id: world.marks.length + 1, customer_name: book?.customer_name, amount_vnd: body.amount_vnd ?? null,
      status: { promise: 'pending', paid_claim: 'waiting', note: null }[body.kind], paid_vnd: body.kind === 'promise' ? '0' : null });
    return json(200, world.marks.at(-1));
  }
  if (url.pathname === '/api/v7/marks/cancel') {
    const row = world.marks.find(item => item.id === body.id);
    Object.assign(row, { status: 'cancelled', cancel_reason: body.reason });
    return json(200, row);
  }
  return false;
}

// `drop`: tập đường API mà máy chủ cắt kết nối (giả mất mạng); test xóa khỏi tập để lần sau tải được.
function makeServer({ unavailable = false, requests = [], drop = new Set(), bundled = false, world = null } = {}) {
  return http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://x');
    if (drop.has(url.pathname)) { req.socket.destroy(); return; }
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    const json = (status, body) => send(status, 'application/json', JSON.stringify(body));
    if (world) {
      let raw = '';
      for await (const chunk of req) raw += chunk;
      if (ledgerRoute(world, req, url, raw ? JSON.parse(raw) : null, json) !== false) return;
    }
    if (url.pathname.startsWith('/api/v7/zalo/')) {
      requests.push(url.pathname + url.search);
      if (unavailable) return json(503, { error: 'ZALO_EXPORT_UNAVAILABLE', message: 'Máy chủ chưa có bản xuất chat Zalo: chưa đặt WEBDEBIT_ZALO_EXPORT_DIR' });
      if (url.pathname === `/api/v7/zalo/media/${PIC}`) return send(200, 'image/png', PNG);
      if (url.pathname === '/api/v7/zalo/report') {
        return json(200, bundled ? { ...report(), status: 'BUNDLED', conversation_count: 1, message_count: 120, media_count: 1, built_at: '2026-11-01T14:12:19+07:00' } : report());
      }
      if (url.pathname === '/api/v7/zalo/conversations') {
        return json(200, bundled ? { total: 1, conversations: [{ conversation_id: GROUP, display_name: 'Nhóm Vũ - công nợ', name_status: 'name_index', message_count: 120,
          last_message_at: DAY + 119 * 60_000, last_own_message_at: DAY + 117 * 60_000, participant_count: 3, is_group: true }] } : conversations());
      }
      if (url.pathname === '/api/v7/zalo/messages') {
        const id = url.searchParams.get('conversation');
        if (![CONV_A, CONV_B, GROUP].includes(id)) return json(404, { error: 'CONVERSATION_NOT_FOUND', message: 'Không có hội thoại này.' });
        let page = Number(url.searchParams.get('page') ?? 0);
        const limit = Number(url.searchParams.get('limit') ?? 50);
        const q = fold(url.searchParams.get('q') ?? '');
        const rows = id === GROUP ? groupRows : id === CONV_B ? [msg('x1', false, DAY, 'Khuyến mãi hôm nay')] : ALL;
        const selected = q ? rows.filter(m => m.body_text && fold(m.body_text).includes(q)) : rows;
        const focus = url.searchParams.get('message');
        if (focus) {
          const at = selected.findIndex(m => m.message_id === focus);
          if (at < 0) return json(404, { error: 'MESSAGE_NOT_FOUND', message: 'Tin này không còn trong dữ liệu chat.' });
          page = Math.floor((selected.length - 1 - at) / limit);
        }
        const end = Math.max(selected.length - page * limit, 0);
        const start = Math.max(end - limit, 0);
        return json(200, { conversation_id: id, messages: selected.slice(start, end), total: selected.length, page, limit,
          pages: Math.ceil(selected.length / limit), has_older: start > 0, query: url.searchParams.get('q') ?? '', ...(focus ? { focus } : {}) });
      }
      return json(404, { error: 'NOT_FOUND' });
    }
    if (url.pathname.startsWith('/api/v7/presence')) return json(200, { people: [] });
    const file = path.join(__dirname, url.pathname.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(options, fn, { query = '', viewport = { width: 1280, height: 720 } } = {}) {
  const server = makeServer(options);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport });
    const tab = await context.newPage();
    const logs = [];
    tab.on('console', message => logs.push(message.text()));
    await tab.goto(`http://127.0.0.1:${server.address().port}/zalo-chat.html${query}`);
    await fn(tab, logs);
  } finally {
    await browser.close();
    server.close();
  }
}

test('Chat Zalo: danh sách hội thoại có tên, số tin, ngày tin cuối; lọc không dấu; mở hội thoại hiện trang mới nhất theo thời gian', async () => {
  const requests = [];
  await withPage({ requests }, async (page, logs) => {
    await page.locator('.conv').first().waitFor();
    assert.match(await page.locator('#summary').innerText(), /2 hội thoại · 8 tin · 1 có tên khách · 1 đính kèm chưa khớp/);
    assert.deepEqual(await page.locator('.conv .nm').allInnerTexts(), ['Nguyễn Hoàng Vũ', `Chưa rõ tên · ${CONV_B.slice(0, 8)}`]);
    assert.deepEqual(await page.locator('.conv .last').allInnerTexts(), ['10/10/2025', '09/10/2025']);
    assert.match(await page.locator('.conv .sub').first().innerText(), /7 tin · Mình nhắn gần nhất 10\/10\/2025/);
    assert.equal(await page.locator('nav a.active').innerText(), 'Đòi nợ');
    await page.locator('#conversation-search').fill('hoang vu');
    assert.deepEqual(await page.locator('.conv .nm').allInnerTexts(), ['Nguyễn Hoàng Vũ']);
    assert.equal(await page.locator('#conversation-count').innerText(), '1 / 2');
    await page.locator('.conv').first().click();
    await page.locator('.msg').first().waitFor();
    assert.equal(await page.locator('#title').innerText(), 'Nguyễn Hoàng Vũ');
    assert.deepEqual(await page.locator('.msg').evaluateAll(nodes => nodes.map(n => n.dataset.id)), ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7']);
    assert.deepEqual(await page.locator('.day').allInnerTexts(), ['09/10/2025', '10/10/2025']);
    assert.deepEqual(await page.locator('.msg.own .who').allInnerTexts(), ['Mình', 'Mình', 'Mình']);
    assert.equal(await page.locator('.msg.other .who').first().innerText(), 'Nguyễn Hoàng Vũ');
    // ZALO-GROUP-01: dòng trên bong bóng chỉ còn người gửi và giờ (bỏ "Văn bản · đã gửi" cho đỡ rối).
    assert.doesNotMatch(await page.locator('.msg[data-id="m1"] .meta').innerText(), /Văn bản|đã gửi/);
    // Đính kèm đã khớp, chưa khớp, và tin thiếu nội dung đều hiện rõ.
    assert.match(await page.locator('.msg[data-id="m3"] .att.matched').innerText(), /Ảnh · 1920×2560/);
    assert.match(await page.locator('.msg[data-id="m4"] .att.unmatched').innerText(), /chưa khớp metadata: cong-no.pdf/);
    assert.match(await page.locator('.msg[data-id="m5"] .body.missing').innerText(), /Không đọc được nội dung/);
    assert.ok(await page.locator('.end').isVisible());
    assert.equal(await page.locator('#older').count(), 0);
    assert.ok(requests.some(r => r.startsWith(`/api/v7/zalo/messages?conversation=${CONV_A}&page=0&limit=50`)));
    assert.ok(!logs.some(line => /cont chưa thanh toán|Dạ để em/.test(line)), 'không log nội dung tin ra console');
    assert.ok(page.url().includes(`c=${CONV_A}`));
  });
});

test('Chat Zalo: phân trang tải tin cũ hơn và tìm trong hội thoại qua API', async () => {
  const requests = [];
  await withPage({ requests }, async page => {
    await page.locator('.conv').first().waitFor();
    // Trang 3 tin: lần đầu m5–m7, "Tải tin cũ hơn" thêm m2–m4 lên trên.
    await page.evaluate(() => { window.history.replaceState(null, '', '?'); });
    await page.locator('.conv').first().click();
    await page.locator('.msg').first().waitFor();
    assert.equal(await page.locator('.msg').count(), 7);
    await page.locator('#message-search').fill('cont');
    await page.locator('.msg mark').first().waitFor();
    // m3 là thẻ ảnh không có chữ nên không khớp; chỉ m1 có "cont" trong nội dung.
    assert.deepEqual(await page.locator('.msg').evaluateAll(nodes => nodes.map(n => n.dataset.id)), ['m1']);
    assert.match(await page.locator('#subtitle').innerText(), /1 tin khớp "cont"/);
    assert.ok(requests.some(r => r.includes(`conversation=${CONV_A}`) && r.includes('q=cont')));
    await page.locator('#message-search').fill('khong co');
    await page.locator('.messages .empty').waitFor();
    assert.match(await page.locator('.messages .empty').innerText(), /Không có tin nào khớp/);
  });
});

test('Chat Zalo: nút Tải tin cũ hơn ghép trang cũ lên trên, giữ thứ tự thời gian', async () => {
  await withPage({}, async page => {
    await page.locator('.conv').first().waitFor();
    // Ép trang nhỏ bằng cách chặn limit: máy chủ giả tôn trọng limit, trang dùng 50 nên giả lập qua route.
    await page.route('**/api/v7/zalo/messages*', route => {
      const url = new URL(route.request().url());
      url.searchParams.set('limit', '3');
      route.continue({ url: url.toString() });
    });
    await page.locator('.conv').first().click();
    await page.locator('#older').waitFor();
    assert.deepEqual(await page.locator('.msg').evaluateAll(nodes => nodes.map(n => n.dataset.id)), ['m5', 'm6', 'm7']);
    assert.match(await page.locator('#older').innerText(), /4 tin/);
    await page.locator('#older').click();
    await page.locator('.msg[data-id="m2"]').waitFor();
    assert.deepEqual(await page.locator('.msg').evaluateAll(nodes => nodes.map(n => n.dataset.id)), ['m2', 'm3', 'm4', 'm5', 'm6', 'm7']);
    await page.locator('#older').click();
    await page.locator('.end').waitFor();
    assert.equal(await page.locator('.msg').count(), 7);
    assert.equal(await page.locator('#older').count(), 0);
  });
});

test('Chat Zalo: ?q= từ tab Đòi nợ lọc sẵn và tự mở khi chỉ còn một hội thoại', async () => {
  await withPage({}, async page => {
    await page.locator('.msg').first().waitFor();
    assert.equal(await page.locator('#conversation-search').inputValue(), 'Nguyễn Hoàng Vũ');
    assert.equal(await page.locator('#title').innerText(), 'Nguyễn Hoàng Vũ');
  }, { query: `?q=${encodeURIComponent('Nguyễn Hoàng Vũ')}` });
});

test('Chat Zalo: máy chủ chưa có bản xuất thì báo rõ, không treo "Đang tải"', async () => {
  await withPage({ unavailable: true }, async page => {
    await page.locator('#error').waitFor({ state: 'visible' });
    assert.match(await page.locator('#error').innerText(), /chưa có bản xuất chat Zalo/);
    assert.match(await page.locator('#error').innerText(), /WEBDEBIT_ZALO_EXPORT_DIR/);
    assert.equal(await page.locator('#summary').innerText(), 'Chưa có dữ liệu chat.');
    assert.ok(await page.locator('#chat').isHidden());
  });
});

// Audit UX 31/10/2026 (P1-6): mất mạng khi tải chỉ hiện câu tiếng Việt và nút Thử lại; không hiện chữ của trình duyệt.
test('Chat Zalo: mất mạng khi tải danh sách hay tin nhắn thì báo bằng câu tiếng Việt, nút Thử lại tải lại', async () => {
  const drop = new Set(['/api/v7/zalo/report']);
  await withPage({ drop }, async page => {
    await page.locator('#error').waitFor({ state: 'visible' });
    const text = await page.locator('#error').innerText();
    assert.match(text, /^Không tải được dữ liệu chat\. Kiểm tra mạng rồi bấm Thử lại\.\s*Thử lại$/);
    assert.doesNotMatch(text, /fetch|TypeError|HTTP/i);
    drop.clear();
    await page.locator('#error').getByRole('button', { name: 'Thử lại' }).click();
    await page.locator('.conv').first().waitFor();
    assert.ok(await page.locator('#error').isHidden());
    drop.add('/api/v7/zalo/messages');
    await page.locator('.conv').first().click();
    await page.locator('#messages [data-retry-page]').waitFor();
    assert.match(await page.locator('#messages').innerText(), /^Không tải được tin nhắn\. Kiểm tra mạng rồi bấm Thử lại\.\s*Thử lại$/);
    drop.clear();
    await page.locator('#messages').getByRole('button', { name: 'Thử lại' }).click();
    await page.locator('.msg').first().waitFor();
  });
});

test('Chat Zalo: màn hình điện thoại hiện danh sách, mở hội thoại thì sang tin nhắn, nút ← về danh sách', async () => {
  await withPage({}, async page => {
    await page.locator('.conv').first().waitFor();
    assert.ok(await page.locator('.detail-pane').isHidden());
    await page.locator('.conv').first().click();
    await page.locator('.msg').first().waitFor();
    assert.ok(await page.locator('.list-pane').isHidden());
    assert.ok(await page.locator('#back-list').isVisible());
    await page.locator('#back-list').click();
    assert.ok(await page.locator('.list-pane').isVisible());
    assert.ok(await page.locator('.detail-pane').isHidden());
  }, { viewport: { width: 390, height: 844 } });
});

test('Chat Zalo (gói web): group có tên người gửi theo cụm, ảnh trong tin, bấm xem lớn, ảnh mất thì báo', async () => {
  await withPage({ bundled: true }, async (page, logs) => {
    await page.locator('.conv').first().waitFor();
    assert.match(await page.locator('#summary').innerText(), /^1 group · 120 tin · 1 ảnh · cập nhật 14:12 01\/11\/2026 · chỉ xem$/);
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g119"]').waitFor();
    // Khung tin tự cuộn và đứng ở tin mới nhất; trang không dài theo số tin (lỗi flex: 1 bỏ qua height, sửa 1/11/2026).
    const layout = await page.locator('#messages').evaluate(box => ({ inner: box.scrollHeight > box.clientHeight,
      bottom: Math.round(box.scrollHeight - box.scrollTop - box.clientHeight), page: document.documentElement.scrollHeight }));
    assert.deepEqual(layout, { inner: true, bottom: 0, page: 720 });
    assert.equal(await page.locator('.msg[data-id="g117"] .who').innerText(), 'Mình');
    assert.equal(await page.locator('.msg[data-id="g118"] .who').innerText(), 'Vũ');
    assert.equal(await page.locator('.msg[data-id="g119"] .who').innerText(), 'Lan kế toán');
    const picture = page.locator('.msg[data-id="g118"] .pic img');
    await picture.waitFor();
    assert.equal(await picture.evaluate(img => img.complete && img.naturalWidth), 1);
    assert.match(await picture.getAttribute('src'), new RegExp(`/api/v7/zalo/media/${PIC}$`));
    assert.match(await page.locator('.msg[data-id="g119"] .pic-gone').innerText(), /Ảnh không còn trên Zalo/);
    await page.locator('.msg[data-id="g118"] .pic').click();
    assert.ok(await page.locator('#pic-viewer').evaluate(dialog => dialog.open));
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#pic-viewer').evaluate(dialog => dialog.open), false);
    assert.ok(!logs.some(line => /Tin số/.test(line)), 'không log nội dung tin ra console');
  }, {});
});

test('Chat Zalo (gói web): ?c=&m= mở đúng tin ở giữa hội thoại, tô sáng, tải được tin mới hơn và cũ hơn', async () => {
  const requests = [];
  await withPage({ bundled: true, requests }, async page => {
    await page.locator('.msg.focus').waitFor();
    assert.equal(await page.locator('.msg.focus').getAttribute('data-id'), 'g30');
    assert.ok(requests.some(r => r.includes('message=g30')));
    // 120 tin, trang 50: g30 ở trang 1 (g20–g69); còn tin cũ hơn và tin mới hơn.
    assert.deepEqual(await page.locator('.msg').evaluateAll(nodes => [nodes[0].dataset.id, nodes.at(-1).dataset.id]), ['g20', 'g69']);
    assert.ok(await page.locator('.msg.focus').isVisible());
    await page.locator('#newer').click();
    await page.locator('.msg[data-id="g119"]').waitFor();
    assert.equal(await page.locator('#newer').count(), 0);
    assert.match(await page.locator('#older').innerText(), /20 tin/);
    await page.locator('#older').click();
    await page.locator('.end').waitFor();
    assert.equal(await page.locator('.msg').count(), 120);
    assert.equal(await page.locator('.msg.focus').count(), 0, 'tô sáng tắt sau 3 giây hoặc khi vẽ lại');
  }, { query: `?c=${GROUP}&m=g30` });
});

test('Chat Zalo (gói web): tin đã đánh dấu không còn thì báo và hiện tin mới nhất', async () => {
  await withPage({ bundled: true }, async page => {
    await page.locator('.msg[data-id="g119"]').waitFor();
    assert.match(await page.locator('#subtitle').innerText(), /Tin đã đánh dấu không còn trên web/);
  }, { query: `?c=${GROUP}&m=khong-co` });
});

test('Đánh dấu (G4): group chưa gắn sổ thì gắn ngay trong hộp, ghi hứa trả từ một tin, nhãn hiện dưới tin và tên sổ ở danh sách', async () => {
  const world = ledgerWorld();
  await withPage({ bundled: true, world }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g115"]').waitFor();
    assert.match(await page.locator('#links').innerText(), /Chưa gắn sổ/);
    await page.locator('.msg[data-id="g115"]').hover();
    await page.locator('.msg[data-id="g115"] .mark-btn').click();
    assert.ok(await page.locator('#mark-dialog').evaluate(dialog => dialog.open));
    assert.match(await page.locator('#mark-quote').innerText(), /Vũ · .*\nTin số 115/);
    assert.ok(await page.locator('#mark-no-book').isVisible());
    await page.locator('#mark-no-book [data-open-link]').click();
    await page.locator('#link-search').fill('hoang vu');
    assert.deepEqual(await page.locator('#link-options .option').allInnerTexts(), ['Nguyễn Hoàng Vũ · Sầu riêng']);
    await page.locator('#link-options .option').click();
    await page.locator('#mark-book-field').waitFor();
    assert.equal(await page.locator('#mark-book').inputValue(), '7');
    // Thiếu số tiền thì báo, không gửi.
    await page.locator('#mark-save').click();
    assert.match(await page.locator('#mark-error').innerText(), /Số tiền phải là số nguyên dương/);
    await page.locator('#mark-amount').fill('50.000.000');
    await page.locator('#mark-date').fill(todayVn(3));
    await page.locator('#mark-note').fill('mai chuyển');
    await page.locator('#mark-save').click();
    await page.locator('.msg[data-id="g115"] .mark').waitFor();
    const due = todayVn(3).split('-').reverse().join('/');
    assert.equal(await page.locator('.msg[data-id="g115"] .mark span').innerText(), `Hứa trả 50.000.000 đ · hẹn ${due} · đang chờ`);
    const sent = world.posts.find(post => post.path === '/api/v7/marks').body;
    assert.deepEqual({ ...sent, idempotency_key: typeof sent.idempotency_key, message_at: typeof sent.message_at }, {
      customer_id: 7, kind: 'promise', idempotency_key: 'string', conversation_id: GROUP, message_id: 'g115', message_at: 'string',
      message_sender: 'Vũ', message_excerpt: 'Tin số 115', note: 'mai chuyển', amount_vnd: '50000000', on_date: todayVn(3) });
    assert.deepEqual(await page.locator('#links .chip a').allInnerTexts(), ['Nguyễn Hoàng Vũ · Sầu riêng']);
    assert.match(await page.locator('.conv .books').innerText(), /Sổ: Nguyễn Hoàng Vũ/);
    assert.equal(await page.locator('#links a').getAttribute('href'), '/so-khach-v7-live.html?customer=7&the=trao-doi');
  });
});

test('Đánh dấu (G4): khách báo đã chuyển không cho ngày mai, ghi chú bắt buộc chữ; mất mạng khi lưu thì bấm lại vẫn chỉ một dấu', async () => {
  const world = ledgerWorld();
  world.links.push({ conversation_id: GROUP, customer_id: 7, customer_name: 'Nguyễn Hoàng Vũ · Sầu riêng' });
  const drop = new Set();
  await withPage({ bundled: true, world, drop }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g118"]').waitFor();
    await page.locator('.msg[data-id="g118"]').hover();
    await page.locator('.msg[data-id="g118"] .mark-btn').click();
    assert.match(await page.locator('#mark-quote').innerText(), /\[Ảnh\]/);
    await page.locator('#mark-form input[value="paid_claim"]').check();
    assert.equal(await page.locator('#mark-date-label').innerText(), 'Ngày khách nói đã chuyển');
    await page.locator('#mark-amount').fill('300000');
    await page.locator('#mark-date').fill(todayVn(1));
    await page.locator('#mark-save').click();
    assert.match(await page.locator('#mark-error').innerText(), /không được sau hôm nay/);
    await page.locator('#mark-date').fill(todayVn(0));
    drop.add('/api/v7/marks');
    await page.locator('#mark-save').click();
    await page.locator('#mark-error').waitFor();
    assert.match(await page.locator('#mark-error').innerText(), /^Không lưu dấu được\. Kiểm tra mạng rồi bấm lại\.$/);
    assert.equal(await page.locator('#mark-save').isEnabled(), true);
    drop.clear();
    await page.locator('#mark-save').click();
    await page.locator('.msg[data-id="g118"] .mark').waitFor();
    assert.equal(world.marks.length, 1, 'bấm lại sau mất mạng không tạo dấu thứ hai');
    assert.match(await page.locator('.msg[data-id="g118"] .mark').innerText(), /Khách báo đã chuyển 300\.000 đ · ngày .* · chờ đối chiếu/);
    // Ghi chú: không có ô tiền, chữ bắt buộc.
    await page.locator('.msg[data-id="g117"]').hover();
    await page.locator('.msg[data-id="g117"] .mark-btn').click();
    await page.locator('#mark-form input[value="note"]').check();
    assert.ok(await page.locator('#mark-amount-field').isHidden());
    await page.locator('#mark-save').click();
    assert.match(await page.locator('#mark-error').innerText(), /Ghi chú không được trống/);
    await page.locator('#mark-note').fill('Xin giãn tới cuối tháng');
    await page.locator('#mark-save').click();
    await page.locator('.msg[data-id="g117"] .mark').waitFor();
    assert.equal(await page.locator('.msg[data-id="g117"] .mark span').innerText(), 'Ghi chú: Xin giãn tới cuối tháng');
    assert.equal(world.posts.filter(post => post.path === '/api/v7/marks').at(-1).body.amount_vnd, undefined);
  });
});

test('Đánh dấu (G4): bỏ dấu và bỏ gắn sổ bắt buộc lý do; điện thoại chạm vào tin thì hiện nút Đánh dấu', async () => {
  const world = ledgerWorld();
  world.links.push({ conversation_id: GROUP, customer_id: 7, customer_name: 'Nguyễn Hoàng Vũ · Sầu riêng' });
  world.marks.push({ id: 1, customer_id: 7, kind: 'promise', amount_vnd: '2000000', on_date: todayVn(2), conversation_id: GROUP, message_id: 'g119',
    status: 'pending', paid_vnd: '0', idempotency_key: 'k1' });
  await withPage({ bundled: true, world }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g119"] .mark').waitFor();
    await page.locator('.msg[data-id="g119"] [data-unmark]').click();
    await page.locator('#reason-save').click();
    assert.match(await page.locator('#reason-error').innerText(), /Cần ghi lý do/);
    await page.locator('#reason-text').fill('ghi nhầm');
    await page.locator('#reason-save').click();
    await page.locator('.msg[data-id="g119"] .mark s').waitFor();
    assert.match(await page.locator('.msg[data-id="g119"] .mark').innerText(), /đã bỏ · lý do: ghi nhầm/);
    assert.equal(await page.locator('.msg[data-id="g119"] [data-unmark]').count(), 0);
    await page.locator('#links [data-unlink="7"]').click();
    await page.locator('#reason-text').fill('nhầm group');
    await page.locator('#reason-save').click();
    await page.locator('#links .hint').waitFor();
    assert.deepEqual(world.posts.at(-1), { path: '/api/v7/zalo/unlink', body: { conversation_id: GROUP, customer_id: 7, reason: 'nhầm group' } });
  });
  await withPage({ bundled: true, world: ledgerWorld() }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g116"]').waitFor();
    assert.ok(await page.locator('.msg[data-id="g116"] .mark-btn').isHidden());
    await page.locator('.msg[data-id="g116"] .body').click();
    assert.ok(await page.locator('.msg[data-id="g116"] .mark-btn').isVisible());
    const height = await page.locator('.msg[data-id="g116"] .mark-btn').evaluate(node => node.getBoundingClientRect().height);
    assert.ok(height >= 26, `nút Đánh dấu đủ lớn để chạm (${height}px)`);
  }, { viewport: { width: 375, height: 812 } });
});
