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
const fold = s => String(s ?? '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();

function makeServer({ unavailable = false, requests = [] } = {}) {
  return http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    const json = (status, body) => send(status, 'application/json', JSON.stringify(body));
    if (url.pathname.startsWith('/api/v7/zalo/')) {
      requests.push(url.pathname + url.search);
      if (unavailable) return json(503, { error: 'ZALO_EXPORT_UNAVAILABLE', message: 'Máy chủ chưa có bản xuất chat Zalo: chưa đặt WEBDEBIT_ZALO_EXPORT_DIR' });
      if (url.pathname === '/api/v7/zalo/report') return json(200, report());
      if (url.pathname === '/api/v7/zalo/conversations') return json(200, conversations());
      if (url.pathname === '/api/v7/zalo/messages') {
        const id = url.searchParams.get('conversation');
        if (id !== CONV_A && id !== CONV_B) return json(404, { error: 'CONVERSATION_NOT_FOUND', message: 'Không có hội thoại này.' });
        const page = Number(url.searchParams.get('page') ?? 0);
        const limit = Number(url.searchParams.get('limit') ?? 50);
        const q = fold(url.searchParams.get('q') ?? '');
        const rows = id === CONV_B ? [msg('x1', false, DAY, 'Khuyến mãi hôm nay')] : ALL;
        const selected = q ? rows.filter(m => m.body_text && fold(m.body_text).includes(q)) : rows;
        const end = Math.max(selected.length - page * limit, 0);
        const start = Math.max(end - limit, 0);
        return json(200, { conversation_id: id, messages: selected.slice(start, end), total: selected.length, page, limit,
          pages: Math.ceil(selected.length / limit), has_older: start > 0, query: url.searchParams.get('q') ?? '' });
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
    assert.match(await page.locator('.msg[data-id="m1"] .meta').innerText(), /Văn bản\s*đã gửi/);
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
