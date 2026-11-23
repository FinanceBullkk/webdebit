const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

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
  { conversation_id: CONV_A, display_name: 'Nguyễn Kim Mẫu', name_status: 'matched_storage_info_cache', message_count: 7, last_message_at: DAY + 86_403_000, last_own_message_at: DAY + 86_402_000, participant_count: 2 },
  { conversation_id: CONV_B, display_name: null, name_status: 'unmatched', message_count: 1, last_message_at: DAY, last_own_message_at: null, participant_count: 1 },
] });
const report = () => ({ status: 'EXPORTED_WITH_GAPS', conversation_count: 2, message_count: 8, named_conversations: 1, owner_conversations: 1, body_missing: 1, attachment_matched: 1, attachment_unmatched: 1, skipped_lines: 0 });
const { foldText: fold } = require('./cong-no-format.js');   // cùng quy tắc với fold của web/v7_zalo_chat.py

// ZALO-GROUP-01: gói web — một group có tên người gửi và ảnh; 120 tin để thử mở thẳng một tin ở trang giữa.
const GROUP = '5'.repeat(64);
const PIC = 'e'.repeat(64);
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
const people = { [OWNER]: 'Hào', [KHACH]: 'Mẫu', ['c'.repeat(64)]: 'Kế toán A' };
const groupRows = Array.from({ length: 120 }, (_, i) => {
  const sender = i % 3 === 0 ? OWNER : i % 3 === 1 ? KHACH : 'c'.repeat(64);
  const row = msg(`g${i}`, sender === OWNER, DAY + i * 60_000, `Tin số ${i}`, { sender_id: sender, sender_name: people[sender], media: [], deleted: false });
  if (i === 118) return { ...row, message_type: 2, type_label: 'Ảnh', body_kind: 'card', body_text: null, media: [{ id: PIC, mime: 'image/png', width: 1, height: 1 }] };
  if (i === 119) return { ...row, message_type: 2, type_label: 'Ảnh', body_kind: 'card', body_text: null, media: [] };
  return row;
});

// ZALO-AGENT-01 (21/11/2026): một group có avatar, trả lời tin, cảm xúc, sticker, ghi âm. 60 tin để tin được trả lời x0 nằm ngoài trang đầu.
const EXTRA = '6'.repeat(64);
const KETOAN = 'c'.repeat(64);
const GONE = 'f'.repeat(64);   // avatar máy chủ trả 404 (ảnh đã bị Zalo xóa)
const quoted = (id, sender, name, text) => ({ message_id: id, found: true, sender_id: sender, sender_name: name, type_label: 'Văn bản', deleted: false, body_text: text });
const extra = (i, sender, text, more = {}) => msg(`x${i}`, sender === OWNER, DAY + i * 60_000, text, { sender_id: sender, sender_name: people[sender], media: [], deleted: false,
  sender_avatar: sender === KHACH ? PIC : sender === KETOAN ? GONE : null, quote: null, reactions: [], sticker: null, ...more });
const extraRows = [
  extra(0, KHACH, 'Hóa đơn tháng 10'),
  ...Array.from({ length: 52 }, (_, n) => extra(n + 1, n % 2 ? OWNER : KHACH, `Tin phụ ${n + 1}`)),   // x52 là của Mình
  extra(53, KHACH, 'Trả lời tin gần', { quote: quoted('x52', OWNER, 'Hào', 'Tin phụ 52'), reactions: [{ emoji: '/-heart', count: 3 }, { emoji: '/-strong', count: 1 }, { emoji: '--b', count: 2 }, { emoji: ':-zz', count: 1 }, { emoji: '🎄', count: 1 }] }),
  extra(54, KETOAN, 'Trả lời tin cũ', { quote: quoted('x0', KHACH, 'Mẫu', 'Hóa đơn tháng 10') }),
  extra(55, KHACH, 'Trả lời tin đã mất', { quote: { message_id: 'x-mat', found: false } }),
  extra(56, KETOAN, null, { message_type: 36, type_label: 'Sticker', body_kind: 'card', sticker: { id: PIC, mime: 'image/png', width: 240, height: 240 } }),
  extra(57, KHACH, null, { message_type: 3, type_label: 'Ghi âm', body_kind: 'card', media: [{ id: '7'.repeat(64), mime: 'audio/aac', width: null, height: null }] }),
  extra(58, KHACH, null, { message_type: 3, type_label: 'Ghi âm', body_kind: 'card', media: [{ id: '8'.repeat(64), mime: 'audio/amr', width: null, height: null }] }),
  extra(59, OWNER, 'Ok', { media: [{ id: '9'.repeat(64), mime: 'video/mp4', width: 640, height: 360 }] }),
];

// ZALO-GROUP-01 G4: sổ công nợ giả cho gắn group ↔ sổ và dấu tin, theo hợp đồng /api/v7/zalo/link(s), /api/v7/marks.
// Trạng thái dấu như hàm get_marks lúc chưa có phiếu thu: hứa trả "pending", khách báo đã chuyển "waiting".
const todayVn = (days = 0) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(Date.now() + days * 86_400_000);
function ledgerWorld() {
  return { links: [], marks: [], posts: [], customers: [{ id: 7, name: 'NGUYEN KIM MAU', label: 'Nguyễn Kim Mẫu · Sầu riêng' },
    { id: 8, name: 'TRAN THI GIA', label: 'Trần Thị Giả · Thanh long' }] };
}
function ledgerRoute(world, req, url, body, json) {
  if (req.method === 'GET' && url.pathname === '/api/v7/zalo/links') return json(200, { links: world.links });
  if (req.method === 'GET' && url.pathname === '/api/v7/customers') return json(200, { customers: world.customers });
  if (req.method === 'GET' && url.pathname === '/api/v7/marks') {
    const id = url.searchParams.get('conversation');
    return json(200, { marks: world.marks.filter(row => row.conversation_id === id).slice().reverse() });
  }
  // Báo vị trí (presence.js) cũng là POST và đi theo nhịp giờ: không phải lệnh ghi sổ, để nhánh presence bên dưới trả lời.
  // Ghi nó vào posts thì posts.at(-1) có lúc là nhịp báo vị trí rơi vào sau lệnh cần kiểm (máy chậm thì dễ gặp).
  if (req.method !== 'POST' || url.pathname.startsWith('/api/v7/presence')) return false;
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
    // Như record_mark: cùng khóa mà tiền/ngày/ghi chú khác thì từ chối, không trả dấu cũ như đã lưu nội dung mới.
    if (old && ['amount_vnd', 'on_date', 'note'].some(key => (old[key] ?? null) !== (body[key] ?? null)))
      return json(409, { error: 'IDEMPOTENCY_CONFLICT', message: 'Mã yêu cầu đã dùng cho nội dung khác.' });
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
// `live`: dòng đến sau (ZALO-AGENT-01) theo thứ tự đến: tin mới, tin tới muộn, tin sửa (cùng message_id), tin xóa (deleted: true).
// Test đẩy thêm vào mảng này để giả máy Zalo gửi lên; token `abcd1234:N` là số dòng đã đọc. `control.prefix` đổi = gói đã dựng lại.
const sorted = rows => rows.map((row, index) => [row, index]).sort((a, b) => (a[0].timestamp_ms - b[0].timestamp_ms) || (a[1] - b[1])).map(item => item[0]);
function withLive(base, live) {
  const rows = new Map(base.map(row => [row.message_id, row]));
  for (const row of live) rows.set(row.message_id, row);
  return sorted([...rows.values()]);
}
// `beat.value`: nhịp tim máy Zalo mà /api/v7/zalo/report trả (null là chưa có máy Zalo báo về); test đổi giữa chừng để giả máy im.
function makeServer({ unavailable = false, requests = [], drop = new Set(), bundled = false, extras = false, world = null, live = [], control = { prefix: 'abcd1234' }, beat = { value: null } } = {}) {
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
        const zalo = beat.value ? { zalo: beat.value } : {};
        return json(200, bundled ? { ...report(), status: 'BUNDLED', conversation_count: 1, message_count: 120, media_count: 1, built_at: '2026-11-01T14:12:19+07:00', ...zalo } : report());
      }
      if (url.pathname === '/api/v7/zalo/conversations' && extras) {
        return json(200, { total: 1, conversations: [{ conversation_id: EXTRA, display_name: 'Nhóm có avatar', name_status: 'name_index', message_count: 60,
          last_message_at: DAY + 59 * 60_000, last_own_message_at: DAY + 59 * 60_000, participant_count: 3, is_group: true, avatar: PIC }] });
      }
      if (url.pathname === '/api/v7/zalo/conversations') {
        return json(200, bundled ? { total: 1, conversations: [{ conversation_id: GROUP, display_name: 'Nhóm Mẫu - công nợ', name_status: 'name_index', message_count: 120,
          last_message_at: DAY + 119 * 60_000, last_own_message_at: DAY + 117 * 60_000, participant_count: 3, is_group: true }] } : conversations());
      }
      if (url.pathname === '/api/v7/zalo/messages') {
        const id = url.searchParams.get('conversation');
        if (![CONV_A, CONV_B, GROUP, EXTRA].includes(id)) return json(404, { error: 'CONVERSATION_NOT_FOUND', message: 'Không có hội thoại này.' });
        let page = Number(url.searchParams.get('page') ?? 0);
        const limit = Number(url.searchParams.get('limit') ?? 50);
        const q = fold(url.searchParams.get('q') ?? '');
        const base = id === EXTRA ? extraRows : id === GROUP ? groupRows : id === CONV_B ? [msg('x1', false, DAY, 'Khuyến mãi hôm nay')] : ALL;
        const rows = withLive(base, id === CONV_B ? [] : live);
        if (url.searchParams.has('since')) {   // A3: mọi dòng đến sau token, theo thứ tự đến
          const [prefix, offset] = url.searchParams.get('since').split(':');
          if (prefix !== control.prefix) return json(200, { conversation_id: id, reset: true, token: `${control.prefix}:${live.length}` });
          const fresh = live.slice(Number(offset));
          const chosen = fresh.slice(0, limit);
          return json(200, { conversation_id: id, messages: chosen, since: url.searchParams.get('since'), token: `${control.prefix}:${Number(offset) + chosen.length}`,
            reset: false, total: rows.length, has_more: fresh.length > limit, latest_ms: rows.at(-1)?.timestamp_ms ?? null });
        }
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
          pages: Math.ceil(selected.length / limit), has_older: start > 0, query: url.searchParams.get('q') ?? '', token: `${control.prefix}:${live.length}`, ...(focus ? { focus } : {}) });
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

async function withPage(options, fn, { query = '', viewport = { width: 1280, height: 720 }, clock = false } = {}) {
  const server = makeServer(options);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const context = await browser.newContext({ viewport });
    const tab = await context.newPage();
    const logs = [];
    tab.on('console', message => logs.push(message.text()));
    if (clock) await tab.clock.install();   // đồng hồ giả từ đầu: nhịp 5 giây của trang chỉ chạy khi test gọi runFor
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
    assert.deepEqual(await page.locator('.conv .nm').allInnerTexts(), ['Nguyễn Kim Mẫu', `Chưa rõ tên · ${CONV_B.slice(0, 8)}`]);
    assert.deepEqual(await page.locator('.conv .last').allInnerTexts(), ['10/10/2025', '09/10/2025']);
    assert.match(await page.locator('.conv .sub').first().innerText(), /7 tin · Mình nhắn gần nhất 10\/10\/2025/);
    assert.equal(await page.locator('nav a.active').innerText(), 'Sổ khách');
    assert.equal(await page.locator('a.back').getAttribute('href'), '/so-khach-v7-live.html');
    await page.locator('#conversation-search').fill('kim mau');
    assert.deepEqual(await page.locator('.conv .nm').allInnerTexts(), ['Nguyễn Kim Mẫu']);
    assert.equal(await page.locator('#conversation-count').innerText(), '1 / 2');
    await page.locator('.conv').first().click();
    await page.locator('.msg').first().waitFor();
    assert.equal(await page.locator('#title').innerText(), 'Nguyễn Kim Mẫu');
    assert.deepEqual(await page.locator('.msg').evaluateAll(nodes => nodes.map(n => n.dataset.id)), ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7']);
    assert.deepEqual(await page.locator('.day').allInnerTexts(), ['09/10/2025', '10/10/2025']);
    assert.deepEqual(await page.locator('.msg.own .who').allInnerTexts(), ['Mình', 'Mình', 'Mình']);
    assert.equal(await page.locator('.msg.other .who').first().innerText(), 'Nguyễn Kim Mẫu');
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

test('Chat Zalo: mở từ Thu chi thì nút quay lại về Thu chi, vẫn giữ khi đổi hội thoại; menu vẫn sáng Sổ khách', async () => {
  await withPage({}, async page => {
    await page.locator('.msg').first().waitFor();
    assert.equal(await page.locator('h1').innerText(), 'Chat Zalo, WeChat');
    assert.equal(await page.locator('nav a.active').innerText(), 'Sổ khách');
    assert.deepEqual([await page.locator('a.back').getAttribute('href'), await page.locator('a.back').innerText()], ['/thu-chi.html', '← Thu chi']);
    await page.locator('.conv').nth(1).click();
    await page.waitForURL(/from=thu-chi/);
    assert.match(page.url(), new RegExp(`c=${CONV_B}`));
  }, { query: `?c=${CONV_A}&from=thu-chi` });
  await withPage({}, async page => {   // giá trị lạ: như mở thường
    await page.locator('.conv').first().waitFor();
    assert.equal(await page.locator('a.back').getAttribute('href'), '/so-khach-v7-live.html');
  }, { query: '?from=https://x.example.test' });
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

test('Chat Zalo: ?q= từ thẻ Trao đổi lọc sẵn và tự mở khi chỉ còn một hội thoại', async () => {
  await withPage({}, async page => {
    await page.locator('.msg').first().waitFor();
    assert.equal(await page.locator('#conversation-search').inputValue(), 'Nguyễn Kim Mẫu');
    assert.equal(await page.locator('#title').innerText(), 'Nguyễn Kim Mẫu');
  }, { query: `?q=${encodeURIComponent('Nguyễn Kim Mẫu')}` });
});

test('Chat Zalo: máy chủ chưa có bản xuất thì báo rõ, không treo "Đang tải"', async () => {
  await withPage({ unavailable: true }, async page => {
    await page.locator('#error').waitFor({ state: 'visible' });
    assert.match(await page.locator('#error').innerText(), /Máy chủ chưa có tin nhắn của group Zalo nào/);
    assert.match(await page.locator('#error').innerText(), /zalo_web_bundle\.py add/);
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
    assert.match(await page.locator('#summary').innerText(), /^1 group · 120 tin · 1 ảnh · Zalo cập nhật lúc 14:12 01\/11\/2026 · chỉ xem$/);   // chưa có máy Zalo báo về: giờ dựng gói
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g119"]').waitFor();
    // Khung tin tự cuộn và đứng ở tin mới nhất; trang không dài theo số tin (lỗi flex: 1 bỏ qua height, sửa 1/11/2026).
    const layout = await page.locator('#messages').evaluate(box => ({ inner: box.scrollHeight > box.clientHeight,
      bottom: Math.round(box.scrollHeight - box.scrollTop - box.clientHeight), page: document.documentElement.scrollHeight }));
    assert.deepEqual(layout, { inner: true, bottom: 0, page: 720 });
    assert.equal(await page.locator('.msg[data-id="g117"] .who').innerText(), 'Mình');
    assert.equal(await page.locator('.msg[data-id="g118"] .who').innerText(), 'Mẫu');
    assert.equal(await page.locator('.msg[data-id="g119"] .who').innerText(), 'Kế toán A');
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
    assert.match(await page.locator('#mark-quote').innerText(), /Mẫu · .*\nTin số 115/);
    assert.ok(await page.locator('#mark-no-book').isVisible());
    await page.locator('#mark-no-book [data-open-link]').click();
    await page.locator('#link-search').fill('kim mau');
    await page.locator('#link-options .option').first().waitFor();   // danh sách sổ tải sau khi mở hộp
    assert.deepEqual(await page.locator('#link-options .option').allInnerTexts(), ['Nguyễn Kim Mẫu · Sầu riêng']);
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
      message_sender: 'Mẫu', message_excerpt: 'Tin số 115', note: 'mai chuyển', amount_vnd: '50000000', on_date: todayVn(3) });
    assert.deepEqual(await page.locator('#links .chip a').allInnerTexts(), ['Nguyễn Kim Mẫu · Sầu riêng']);
    assert.match(await page.locator('.conv .books').innerText(), /Sổ: Nguyễn Kim Mẫu/);
    assert.equal(await page.locator('#links a').getAttribute('href'), '/so-khach-v7-live.html?customer=7&the=trao-doi');
  });
});

test('Đánh dấu (G4): khách báo đã chuyển không cho ngày mai, ghi chú bắt buộc chữ; mất mạng khi lưu thì bấm lại vẫn chỉ một dấu', async () => {
  const world = ledgerWorld();
  world.links.push({ conversation_id: GROUP, customer_id: 7, customer_name: 'Nguyễn Kim Mẫu · Sầu riêng' });
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

test('Đánh dấu (audit A08): lần lưu đầu đã ghi nhưng mất phản hồi, sửa số tiền rồi bấm lại thì không báo đã lưu số mới', async () => {
  const world = ledgerWorld();
  world.links.push({ conversation_id: GROUP, customer_id: 7, customer_name: 'Nguyễn Kim Mẫu · Sầu riêng' });
  await withPage({ bundled: true, world }, async page => {
    // Máy chủ ghi xong nhưng trình duyệt không nhận được phản hồi (mất mạng giữa chừng): đúng một lần.
    let lose = true;
    await page.route('**/api/v7/marks', async route => {
      if (route.request().method() !== 'POST' || !lose) return route.continue();
      lose = false;
      await route.fetch();
      return route.abort('failed');
    });
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g116"]').waitFor();
    await page.locator('.msg[data-id="g116"]').hover();
    await page.locator('.msg[data-id="g116"] .mark-btn').click();
    await page.locator('#mark-amount').fill('2.000.000');
    await page.locator('#mark-date').fill(todayVn(2));
    await page.locator('#mark-save').click();
    await page.locator('#mark-error').waitFor();
    assert.match(await page.locator('#mark-error').innerText(), /Kiểm tra mạng rồi bấm lại/);
    assert.equal(world.marks.length, 1, 'lần đầu đã ghi ở máy chủ');
    await page.locator('#mark-amount').fill('3.000.000');
    await page.locator('#mark-save').click();
    await page.locator('#mark-dialog').waitFor({ state: 'hidden' });
    // Câu báo hiện sau khi tải lại danh sách dấu (cùng thứ tự như lúc lưu được).
    await page.locator('#subtitle', { hasText: 'Lần bấm trước đã lưu dấu với nội dung cũ' }).waitFor();
    assert.doesNotMatch(await page.locator('#subtitle').innerText(), /Đã lưu dấu/);
    assert.equal(world.marks.length, 1, 'không thêm dấu thứ hai');
    assert.equal(world.marks[0].amount_vnd, '2000000', 'dấu đã lưu giữ số tiền cũ');
    await page.locator('.msg[data-id="g116"] .mark').waitFor();
    assert.match(await page.locator('.msg[data-id="g116"] .mark span').innerText(), /^Hứa trả 2\.000\.000 đ/);
    // Đánh dấu lại sau đó dùng khóa mới: là dấu thứ hai do người dùng chủ động, không phải gửi lại.
    const keys = world.posts.filter(post => post.path === '/api/v7/marks').map(post => post.body.idempotency_key);
    assert.equal(new Set(keys).size, 1, 'hai lần bấm của cùng một lần đánh dấu dùng chung một khóa');
  });
});

test('Đánh dấu (G4): bỏ dấu và bỏ gắn sổ bắt buộc lý do; điện thoại chạm vào tin thì hiện nút Đánh dấu', async () => {
  const world = ledgerWorld();
  world.links.push({ conversation_id: GROUP, customer_id: 7, customer_name: 'Nguyễn Kim Mẫu · Sầu riêng' });
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

// ZALO-AGENT-01 (A3): tin mới tự hiện. Đồng hồ giả: trang hỏi `since=` theo nhịp 5 giây, test điều khiển bằng runFor.
const afterRequests = requests => requests.filter(item => item.includes('&since='));
const lastStamp = rows => rows.at(-1).timestamp_ms;
// Đồng hồ của trang là đồng hồ giả (rAF cũng đứng): chờ điều kiện ở phía Node bằng timer thật, không dùng waitForFunction.
async function until(check, what) {
  for (let i = 0; i < 300; i += 1) {
    if (await check()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.fail('không thấy: ' + what);
}
const groupMsg = (i, own, text) => msg(`g${i}`, own, DAY + i * 60_000, text, { sender_name: own ? 'Hào' : 'Mẫu', media: [], deleted: false });

test('Chat Zalo tự cập nhật: đang ở đáy thì tin mới nối vào cuối và cuộn theo, hỏi đúng token since=', async () => {
  const requests = [];
  const live = [];
  await withPage({ requests, live }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="m7"]').waitFor();
    assert.deepEqual(afterRequests(requests), [], 'chưa tới 5 giây thì chưa hỏi');
    live.push(msg('m8', false, lastStamp(ALL) + 5000, 'Em vừa chuyển rồi anh'));
    await page.clock.runFor(5000);
    await page.locator('.msg[data-id="m8"]').waitFor();
    assert.match(await page.locator('.msg[data-id="m8"] .body').innerText(), /Em vừa chuyển rồi anh/);
    assert.equal(afterRequests(requests).length, 1);
    assert.ok(afterRequests(requests)[0].includes('since=abcd1234%3A0'), 'hỏi từ token lúc mở hội thoại');
    assert.equal(await page.locator('#new-pill').isHidden(), true, 'đang ở đáy: không cần nút');
    assert.equal(await page.locator('#messages').evaluate(box => box.scrollHeight - box.scrollTop - box.clientHeight < 5), true, 'cuộn theo tin mới');
    assert.match(await page.locator('#subtitle').innerText(), /8 tin · đang hiện 8/);
    // Lần hỏi kế: tin đã có thì không nối lại.
    await page.clock.runFor(5000);
    await until(() => afterRequests(requests).length === 2, 'lượt hỏi thứ hai');
    assert.equal(await page.locator('.msg').count(), 8);
    assert.equal(await page.locator('.msg[data-id="m8"]').count(), 1);
  }, { clock: true });
});

test('Chat Zalo tự cập nhật: đang đọc tin cũ thì không bị kéo xuống, hiện nút "N tin mới", bấm nút hoặc cuộn xuống đáy thì hết nút', async () => {
  const live = [];
  await withPage({ bundled: true, live }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g119"]').waitFor();
    const box = page.locator('#messages');
    await box.evaluate(node => { node.scrollTop = 0; });
    live.push(groupMsg(120, false, 'Tin mới một'), groupMsg(121, true, 'Tin mới hai'));
    await page.clock.runFor(5000);
    await page.locator('#new-pill').waitFor({ state: 'visible' });
    assert.match(await page.locator('#new-pill').innerText(), /^2 tin mới/);
    assert.equal(await box.evaluate(node => node.scrollTop), 0, 'vị trí đang đọc giữ nguyên');
    assert.equal(await page.locator('.msg[data-id="g121"]').count(), 1, 'tin mới đã nối vào cuối khung');
    live.push(groupMsg(122, false, 'Tin mới ba'));
    await page.clock.runFor(5000);
    await page.locator('#new-pill', { hasText: /^3 tin mới/ }).waitFor();
    await page.locator('#new-pill').click();
    assert.equal(await page.locator('#new-pill').isHidden(), true);
    assert.equal(await box.evaluate(node => node.scrollHeight - node.scrollTop - node.clientHeight < 5), true, 'bấm nút thì xuống đáy');
    // Cuộn lên đọc tiếp rồi cuộn tay xuống đáy cũng xóa nút.
    await box.evaluate(node => { node.scrollTop = 0; });
    live.push(groupMsg(123, false, 'Tin mới bốn'));
    await page.clock.runFor(5000);
    await page.locator('#new-pill').waitFor({ state: 'visible' });
    await box.evaluate(node => { node.scrollTop = node.scrollHeight; });
    await page.locator('#new-pill').waitFor({ state: 'hidden' });
  }, { clock: true });
});

test('Chat Zalo tự cập nhật: tab ẩn thì ngừng hỏi, hiện lại thì hỏi ngay; chưa mở hội thoại hoặc đang tìm thì không hỏi', async () => {
  const requests = [];
  const live = [];
  await withPage({ requests, live }, async page => {
    await page.clock.runFor(10_000);
    assert.deepEqual(afterRequests(requests), [], 'chưa mở hội thoại thì không hỏi tin mới');
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="m7"]').waitFor();
    const setHidden = hidden => page.evaluate(value => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => value });
      document.dispatchEvent(new Event('visibilitychange'));
    }, hidden);
    await setHidden(true);
    live.push(msg('m8', false, lastStamp(ALL) + 5000, 'Tin khi tab ẩn'));
    await page.clock.runFor(30_000);
    assert.deepEqual(afterRequests(requests), [], 'tab ẩn: không hỏi');
    await setHidden(false);
    await page.locator('.msg[data-id="m8"]').waitFor();
    assert.equal(afterRequests(requests).length, 1, 'hiện lại: hỏi ngay một lượt');
    await page.locator('#message-search').fill('cont');
    await page.clock.runFor(300);   // hết nhịp chờ gõ của ô tìm
    await page.locator('#subtitle', { hasText: /^1 tin khớp/ }).waitFor();
    const asked = afterRequests(requests).length;
    live.push(msg('m9', false, lastStamp(ALL) + 9000, 'cont thêm'));
    await page.clock.runFor(10_000);
    assert.equal(afterRequests(requests).length, asked, 'đang tìm trong hội thoại: không hỏi, không nối tin vào kết quả tìm');
  }, { clock: true });
});

test('Chat Zalo tự cập nhật: nút "N tin mới" ở điện thoại 390px đủ lớn để chạm, nằm gọn trong khung tin, không tràn ngang', async () => {
  const live = [];
  await withPage({ bundled: true, live }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g119"]').waitFor();
    await page.locator('#messages').evaluate(node => { node.scrollTop = 0; });
    live.push(groupMsg(120, false, 'Tin mới'));
    await page.clock.runFor(5000);
    await page.locator('#new-pill').waitFor({ state: 'visible' });
    const pill = await page.locator('#new-pill').boundingBox();
    assert.ok(pill.height >= 40, `nút đủ cao để chạm (${pill.height}px)`);
    const pane = await page.locator('.detail-pane').boundingBox();
    assert.ok(pill.x >= pane.x && pill.x + pill.width <= pane.x + pane.width, 'nút nằm gọn trong khung tin');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'không tràn ngang');
  }, { clock: true, viewport: { width: 390, height: 780 } });
});

test('Chat Zalo tự cập nhật: tin tới muộn vào đúng chỗ thời gian, tin bị sửa và bị xóa được thay tại chỗ', async () => {
  const live = [];
  await withPage({ live }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="m7"]').waitFor();
    // Máy Zalo mở lại sau khi tắt đêm: đọc bù một tin giờ cũ hơn mọi tin đang hiện, sửa m2, xóa m4, rồi tin mới nhất.
    live.push(msg('m0', false, DAY + 500, 'Tin tới muộn, giờ rất cũ'),
      msg('m2', false, DAY + 2000, 'Dạ em xem rồi, sửa lại'),
      msg('m4', true, DAY + 86_400_000, null, { body_kind: 'missing', body_text: null, deleted: true }),
      msg('m8', false, lastStamp(ALL) + 5000, 'Tin mới nhất'));
    await page.clock.runFor(5000);
    await page.locator('.msg[data-id="m8"]').waitFor();
    assert.deepEqual(await page.locator('.msg').evaluateAll(nodes => nodes.map(n => n.dataset.id)), ['m0', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8']);
    assert.match(await page.locator('.msg[data-id="m2"] .body').innerText(), /sửa lại/);
    assert.equal(await page.locator('.msg[data-id="m2"] .body', { hasText: 'Dạ để em xem lại' }).count(), 0);
    assert.match(await page.locator('.msg[data-id="m4"] .body').innerText(), /Tin đã bị thu hồi/);
    assert.equal(await page.locator('.msg[data-id="m4"] .att').count(), 0, 'tin đã xóa không còn đính kèm');
  }, { clock: true });
});

test('Chat Zalo tự cập nhật: tin tới muộn cũ hơn cả khung đang hiện (thuộc trang cũ) không chen vào khung, tổng tin vẫn tăng', async () => {
  const live = [];
  await withPage({ bundled: true, live }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="g119"]').waitFor();
    assert.equal(await page.locator('.msg').count(), 50);
    live.push(msg('g-old', false, DAY + 5 * 60_000, 'Tin rất cũ tới muộn', { sender_name: 'Mẫu', media: [], deleted: false }));
    await page.clock.runFor(5000);
    await page.locator('#subtitle', { hasText: /^121 tin/ }).waitFor();
    assert.equal(await page.locator('.msg').count(), 50, 'không chen vào khung đang hiện');
    assert.equal(await page.locator('#new-pill').isHidden(), true);
    assert.equal(await page.locator('.msg[data-id="g-old"]').count(), 0);
  }, { clock: true });
});

test('Chat Zalo tự cập nhật: gói được dựng lại (token khác) thì trang tải lại hội thoại', async () => {
  const requests = [];
  const control = { prefix: 'abcd1234' };
  const live = [];
  await withPage({ requests, live, control }, async page => {
    await page.locator('.conv').first().click();
    await page.locator('.msg[data-id="m7"]').waitFor();
    const loads = () => requests.filter(item => item.includes('&page=0&limit=50')).length;
    assert.equal(loads(), 1);
    control.prefix = 'ffff0000';   // máy chủ đã nạp gói dựng lại
    live.push(msg('m8', false, lastStamp(ALL) + 5000, 'Có sau khi dựng lại'));
    await page.clock.runFor(5000);
    await page.locator('.msg[data-id="m8"]').waitFor();
    assert.equal(loads(), 2, 'tải lại trang mới nhất thay vì ghép');
    await page.clock.runFor(5000);   // token mới đã nhận: lần hỏi sau không reset nữa
    await until(() => afterRequests(requests).length === 2, 'lượt hỏi sau khi tải lại');
    assert.equal(loads(), 2);
  }, { clock: true });
});

// ---- ZALO-AGENT-01 (21/11/2026): avatar, trả lời tin, cảm xúc, sticker, ghi âm. Dữ liệu bịa. ----
const openExtra = async (page, requests) => {
  await page.locator('.conv').first().click();
  await page.locator('.msg[data-id="x59"]').waitFor();
  return requests;
};

test('Chat Zalo: avatar ở danh sách và ở tin đầu cụm của người khác; ảnh hỏng thì hiện chữ cái đầu; tin của mình không có avatar', () => withPage({ extras: true }, async page => {
  await page.locator('.conv').first().waitFor();
  assert.equal(await page.locator('.conv .conv-ava').getAttribute('src'), `/api/v7/zalo/media/${PIC}`);
  await openExtra(page);
  assert.equal(await page.locator('.msg[data-id="x53"] .msg-ava').getAttribute('src'), `/api/v7/zalo/media/${PIC}`);
  await page.locator('.msg[data-id="x54"] span.msg-ava.none').waitFor();   // 404 → chữ cái đầu của "Kế toán A"
  assert.equal(await page.locator('.msg[data-id="x54"] .msg-ava').innerText(), 'K');
  assert.equal(await page.locator('.msg[data-id="x59"] .msg-ava').count(), 0);
  assert.equal(await page.locator('.msg[data-id="x58"] .msg-ava').count(), 0);   // tin thứ hai của cụm: không lặp avatar
  assert.equal(await page.locator('.msg[data-id="x58"] .who').count(), 0);
}));

test('Chat Zalo: trả lời tin hiện tên và đoạn trích; bấm thì nhảy tới tin gốc (đang hiện hoặc ở trang cũ hơn) và tô sáng', () => {
  const requests = [];
  return withPage({ extras: true, requests }, async page => {
    await openExtra(page, requests);
    const near = page.locator('.msg[data-id="x53"] .reply');
    assert.deepEqual([await near.locator('.q-who').innerText(), await near.locator('.q-text').innerText()], ['↩ Mình', 'Tin phụ 52']);   // x52 do mình gửi
    assert.match(await page.locator('.msg[data-id="x53"]').innerText(), /Trả lời tin gần/);
    await near.click();
    await page.locator('.msg.focus[data-id="x52"]').waitFor();
    assert.equal(await page.locator('.msg[data-id="x52"]').evaluate(node => {
      const box = node.getBoundingClientRect(), pane = document.getElementById('messages').getBoundingClientRect();
      return box.top >= pane.top && box.bottom <= pane.bottom;
    }), true, 'tin gốc nằm trong khung đang thấy');
    assert.match(await page.locator('.msg[data-id="x54"] .reply').innerText(), /↩ Mẫu\s+Hóa đơn tháng 10/);
    await page.locator('.msg[data-id="x54"] .reply').click();   // x0 không có ở trang đầu: mở đúng trang chứa nó
    await page.locator('.msg.focus[data-id="x0"]').waitFor();
    assert.ok(requests.some(item => item.includes('message=x0')));
  });
});

test('Chat Zalo: tin gốc không còn thì ghi rõ, không bấm được; cảm xúc là chip có số người; sticker là ảnh, không ghi [Sticker]', () => withPage({ extras: true }, async page => {
  await openExtra(page);
  assert.equal(await page.locator('.msg[data-id="x55"] .reply.gone').innerText(), '↩ Trả lời một tin không còn trên web');
  assert.equal(await page.locator('.msg[data-id="x55"] [data-quote]').count(), 0);
  // Gói giữ mã chữ của Zalo ("/-heart", "--b"): màn đổi ra hình, mã lạ thành hình chung, không bao giờ hiện mã thô.
  const reacts = page.locator('.msg[data-id="x53"] .react');
  assert.deepEqual(await reacts.evaluateAll(nodes => nodes.map(node => node.textContent)), ['❤️3', '👍', '😞2', '🙂', '🎄']);
  assert.equal(await reacts.first().getAttribute('title'), '3 người thả ❤️');
  assert.equal(await reacts.nth(3).getAttribute('title'), '1 người thả một cảm xúc khác');
  assert.doesNotMatch(await page.locator('.msg[data-id="x53"] .reacts').innerText(), /[-/:]/);
  const sticker = page.locator('.msg[data-id="x56"] img.sticker');
  assert.deepEqual([await sticker.getAttribute('width'), await sticker.getAttribute('height')], ['120', '120']);
  assert.doesNotMatch(await page.locator('.msg[data-id="x56"]').innerText(), /\[Sticker\]/);
}));

test('Chat Zalo: ghi âm AAC nghe ngay trên trang, AMR thì tải về; không tải trước khi bấm', () => {
  const requests = [];
  return withPage({ extras: true, requests }, async page => {
    await openExtra(page, requests);
    const voice = page.locator('.msg[data-id="x57"] audio.voice');
    assert.deepEqual([await voice.getAttribute('src'), await voice.getAttribute('preload')], [`/api/v7/zalo/media/${'7'.repeat(64)}`, 'none']);
    const file = page.locator('.msg[data-id="x58"] a.voice-file');
    assert.equal(await file.innerText(), 'Ghi âm · tải về để nghe');
    assert.equal(await file.getAttribute('download'), '');
    assert.equal(requests.filter(item => item.includes('7'.repeat(64)) || item.includes('8'.repeat(64))).length, 0);
    assert.doesNotMatch(await page.locator('.msg[data-id="x57"]').innerText(), /\[Ghi âm\]/);
  });
});

test('Chat Zalo: video có playsinline và preload=metadata để iPhone phát trong khung tin', () => withPage({ extras: true }, async page => {
  await openExtra(page);
  const video = page.locator('.msg[data-id="x59"] video.vid');
  assert.equal(await video.getAttribute('src'), `/api/v7/zalo/media/${'9'.repeat(64)}`);
  assert.deepEqual(await video.evaluate(node => [node.hasAttribute('playsinline'), node.hasAttribute('controls'), node.getAttribute('preload')]), [true, true, 'metadata']);
  // Ghi âm AAC giữ preload=none: nhiều ghi âm trong một trang không đổ yêu cầu lên máy chủ trước khi bấm.
  assert.equal(await page.locator('.msg[data-id="x57"] audio.voice').getAttribute('preload'), 'none');
}));

test('Chat Zalo: điện thoại 390px, trích dẫn dài bị cắt trong bong bóng, không tràn ngang', () => withPage({ extras: true }, async page => {
  await openExtra(page);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  const fit = await page.locator('.msg[data-id="x53"]').evaluate(node => {
    const box = node.getBoundingClientRect(), quote = node.querySelector('.reply').getBoundingClientRect();
    return quote.left >= box.left && quote.right <= box.right + 1;
  });
  assert.equal(fit, true);
}, { viewport: { width: 390, height: 844 } }));

// ---- ZALO-THU-CHI-01 "Bị chặn": máy Zalo im hay Zalo chưa mở thì Chat Zalo ghi "lần cuối" và cảnh báo, như trang Thu chi. ----
const OLD_BEAT = '2026-11-01T08:05:00+07:00';   // ngày cố định đã qua: giờ luôn kèm ngày, test không đổi theo ngày chạy

test('Chat Zalo: máy Zalo im thì dòng đầu ghi "cập nhật lần cuối" và có cảnh báo; Zalo chưa mở hay mở mà chưa đọc được ghi số phút; máy báo đều thì không cảnh báo', async () => {
  await withPage({ bundled: true, beat: { value: { state: 'silent', at: OLD_BEAT, silent_minutes: 200, identity: 'attached', quiet_minutes: 0 } } }, async page => {
    await page.locator('.conv').first().waitFor();
    assert.match(await page.locator('#summary').innerText(), /· Zalo cập nhật lần cuối lúc 08:05 01\/11\/2026 · chỉ xem$/);
    assert.equal(await page.locator('#summary').getAttribute('class'), 'summary stale');
    assert.equal(await page.locator('#zalo-warn').innerText(), 'Máy Zalo không báo về từ 08:05 01/11/2026. Tin mới có thể chưa lên.');
  });
  await withPage({ bundled: true, beat: { value: { state: 'ok', at: OLD_BEAT, silent_minutes: 0, identity: 'waiting_for_zalo', quiet_minutes: 42 } } }, async page => {
    await page.locator('.conv').first().waitFor();
    assert.equal(await page.locator('#zalo-warn').innerText(), 'Zalo chưa mở trên máy Zalo (42 phút). Tin Zalo mới chưa lên.');
  });
  await withPage({ bundled: true, beat: { value: { state: 'ok', at: OLD_BEAT, silent_minutes: 0, identity: 'reprobing', quiet_minutes: 1107 } } }, async page => {
    await page.locator('.conv').first().waitFor();
    assert.equal(await page.locator('#summary').getAttribute('class'), 'summary stale');
    assert.equal(await page.locator('#zalo-warn').innerText(),
      'Zalo đã mở trên máy Zalo nhưng chưa đọc được tin (1.107 phút), có thể đang chờ đăng nhập lại. Tin Zalo mới chưa lên.');
  });
  await withPage({ bundled: true, beat: { value: { state: 'ok', at: OLD_BEAT, silent_minutes: 0, identity: 'attached', quiet_minutes: 0 } } }, async page => {
    await page.locator('.conv').first().waitFor();
    assert.match(await page.locator('#summary').innerText(), /· Zalo cập nhật lúc 08:05 01\/11\/2026 · chỉ xem$/);   // nhịp tim thắng giờ dựng gói
    assert.equal(await page.locator('#zalo-warn').isHidden(), true);
  });
});

test('Chat Zalo: máy Zalo im giữa chừng thì sau một phút dòng đầu tự đổi sang "lần cuối" và hiện cảnh báo, không cần tải lại; tab ẩn thì không hỏi', async () => {
  const requests = [];
  const beat = { value: { state: 'ok', at: OLD_BEAT, silent_minutes: 0, identity: 'attached', quiet_minutes: 0 } };
  await withPage({ bundled: true, requests, beat }, async page => {
    await page.locator('.conv').first().waitFor();
    assert.equal(await page.locator('#zalo-warn').isHidden(), true);
    beat.value = { state: 'silent', at: OLD_BEAT, silent_minutes: 20, identity: 'attached', quiet_minutes: 0 };
    const reports = () => requests.filter(item => item === '/api/v7/zalo/report').length;
    await page.clock.runFor(30_000);
    assert.equal(reports(), 1);   // chưa đủ một phút: không hỏi lại
    await page.clock.runFor(35_000);
    await page.locator('#zalo-warn:not([hidden])').waitFor();
    assert.match(await page.locator('#summary').innerText(), /Zalo cập nhật lần cuối lúc 08:05 01\/11\/2026/);
    assert.equal(reports(), 2);
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.clock.runFor(180_000);
    await page.waitForTimeout(150);   // đồng hồ giả không chạy giờ thật: chờ chắc chắn không có yêu cầu nào đang bay
    assert.equal(reports(), 2);
  }, { clock: true });
});

test('Chat Zalo: có dòng cảnh báo thì khung chat vẫn vừa màn (1280×720 và 390×844): tin mới nhất ở đáy khung không bị đẩy dưới mép', async () => {
  for (const viewport of [{ width: 1280, height: 720 }, { width: 390, height: 844 }]) {
    await withPage({ bundled: true, beat: { value: { state: 'silent', at: OLD_BEAT, silent_minutes: 200, identity: 'attached', quiet_minutes: 0 } } }, async page => {
      await page.locator('.conv').first().click();
      await page.locator('.msg[data-id="g119"]').waitFor();
      assert.equal(await page.locator('#zalo-warn').isVisible(), true);
      const fit = await page.evaluate(() => ({ bottom: document.getElementById('chat').getBoundingClientRect().bottom, height: window.innerHeight,
        scroll: document.documentElement.scrollHeight - window.innerHeight }));
      assert.ok(fit.bottom <= fit.height + 1, `khung chat đáy ${fit.bottom} / màn ${fit.height} (${viewport.width})`);
      assert.ok(fit.scroll <= 1, `trang không cuộn thêm: ${fit.scroll} (${viewport.width})`);
    }, { viewport });
  }
});
