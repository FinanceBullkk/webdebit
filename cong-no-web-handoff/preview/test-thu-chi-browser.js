const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// ZALO-THU-CHI-01 PR-2: trang Thu chi (chỉ xem). Máy chủ giả, dữ liệu bịa; nhịp hỏi 5 giây chạy bằng đồng hồ giả.
const TODAY = '2026-11-20';
const GROUP = '1'.repeat(64);
const PHOTO = 'c'.repeat(64);
const item = (id, day, hour, direction, amount, status, extra = {}) => ({
  source: 'chat', message_id: id, conversation_id: GROUP, conversation_name: 'Nhóm thu chi thử', sent_at: Date.parse(`${day}T${String(hour).padStart(2, '0')}:00:00+07:00`),
  day, sender_name: 'Lan', direction, amount_vnd: amount, text: `${direction} ${amount} thử`, media: [], target: { kind: null, id: null, label: null }, ambiguous: false,
  status, shared: false, unchecked: false, ledger_ref: null, ledger_vnd: null, ...extra });
const so = (id, label) => ({ kind: 'so', id, label });
const ITEMS = [
  item('t1', TODAY, 11, 'thu', 50_000_000, 'RECORDED', { target: so(1, 'SỔ A'), ledger_ref: { kind: 'receipt', customer_id: 1, pid: 'PH-1', date: TODAY }, media: [{ id: PHOTO, mime: 'image/jpeg' }] }),
  item('t2', TODAY, 9, 'chi', 2_500_000, 'WAITING', { target: { kind: 'xe', id: 10, label: '51C-12345' } }),
  item('t3', '2026-11-19', 15, 'thu', 30_000_000, 'AMOUNT_DIFF', { target: so(2, 'SỔ B'), ledger_vnd: 28_000_000, ledger_ref: { kind: 'receipt', customer_id: 2, date: '2026-11-19' } }),
  item('t4', '2026-11-19', 10, 'ung', 3_000_000, 'RECORDED', { target: { kind: 'tai_xe', id: 20, label: 'Bình' }, ledger_ref: { kind: 'ung', id: 5, date: '2026-11-19' } }),
  item('t5', '2026-11-15', 9, 'thu', 40_000_000, 'MISSING', { target: so(3, '陈氏贸易有限公司 RẤT DÀI TÊN SỔ ĐỂ THỬ BỐ CỤC') }),
  item('t6', '2026-11-16', 9, 'thu', 7_000_000, 'SUGGEST', { ledger_ref: { kind: 'receipt', customer_id: 4, name: 'SỔ D', date: '2026-11-16' } }),
  item('t7', '2026-11-17', 9, 'chi', 5_000_000, 'NO_LEDGER'),
  item('t8', '2026-11-17', 10, 'thu', null, 'NO_AMOUNT', { text: 'thu 50 khach' }),
  item('t9', '2026-11-18', 10, 'thu', 9_000_000, 'UNKNOWN_TARGET'),
];
const body = (items, extra = {}) => ({ unavailable: false, sources_failed: [], from: '2026-11-14', to: TODAY, today: TODAY, items, totals: {}, counts: {}, bundle_at: '2026-11-20T11:00:00+07:00',
  last_message_at: Date.parse(`${TODAY}T11:00:00+07:00`), zalo: { state: 'ok', at: '2026-11-20T11:30:00+07:00', silent_minutes: 0, identity: 'attached', quiet_minutes: 0 }, ...extra });

function makeServer(state) {
  return http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    const send = (status, type, data) => { res.writeHead(status, { 'Content-Type': type }); res.end(data); };
    const json = (data, status = 200) => send(status, 'application/json', JSON.stringify(data));
    if (url.pathname === '/api/v7/cash-chat/review' && req.method === 'POST') {   // Luồng 3: ghi lại thân lệnh, trả theo kịch bản của test
      let raw = '';
      req.on('data', chunk => { raw += chunk; });
      req.on('end', () => {
        const sent = JSON.parse(raw);
        state.posts.push(sent);
        const next = (state.review ?? (() => ({})))(sent);
        return next.status ? json({ error: next.error, message: next.message }, next.status) : json({ id: state.posts.length, ...sent });
      });
      return undefined;
    }
    if (url.pathname === '/api/v7/cash-chat/targets') {
      state.targetCalls += 1;
      return json(TARGETS);
    }
    if (url.pathname === '/api/v7/cash-chat') {
      state.calls.push(url.search);
      const next = state.respond();
      return next.status ? json({ error: 'X' }, next.status) : json(next.body);
    }
    if (url.pathname.startsWith('/api/v7/zalo/media/')) return send(200, 'image/png', Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64'));
    if (url.pathname === '/api/v7/customers') return json({ customers: [] });
    if (url.pathname.startsWith('/api/')) return json({}, 404);
    if (url.pathname === '/zalo-chat.html') return send(200, 'text/html', '<!doctype html><title>Chat</title><p id="chat">chat</p>');
    const file = path.join(__dirname, url.pathname.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

const TARGETS = { so: [{ id: 1, label: 'SỔ A' }, { id: 2, label: 'SỔ B' }, { id: 3, label: '陈氏贸易有限公司 RẤT DÀI TÊN SỔ ĐỂ THỬ BỐ CỤC' }],
  xe: [{ id: 10, label: '51C-12345' }, { id: 11, label: '29H-67890' }], tai_xe: [{ id: 20, label: 'Bình' }, { id: 21, label: 'Cường' }], failed: false };

async function withPage(respond, fn, { viewport = { width: 1280, height: 720 }, clock = false, review = null } = {}) {
  const state = { calls: [], respond, posts: [], review, targetCalls: 0 };
  const server = makeServer(state);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    if (clock) await page.clock.install();   // nhịp 5 giây của trang chỉ chạy khi test gọi runFor
    await page.goto(`http://127.0.0.1:${server.address().port}/thu-chi.html`);
    await fn(page, state);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    server.close();
  }
}
const ok = items => () => ({ body: body(items) });
const clean = text => text.replace(/\s+/g, ' ').trim();
const ready = page => page.locator('.tc-row').first().waitFor();

test('Thu chi: hôm nay và 7 ngày, gom theo ngày mới trên cùng, trạng thái đối chiếu bằng câu thường', () => withPage(ok(ITEMS), async page => {
  await ready(page);
  assert.equal(await page.locator('nav a.active, .admin-tabs a.active').first().innerText(), 'Quản trị');
  assert.equal(await page.locator('.admin-tabs a.active').innerText(), 'Thu chi');
  const [today, week] = await page.locator('.tc-card').allInnerTexts();
  assert.match(clean(today), /Hôm nay/);
  assert.match(clean(today), /50\.000\.000 đ Thu · 1 khoản/);
  assert.match(clean(today), /2\.500\.000 đ Chi · 1 khoản/);
  assert.match(clean(today), /0 đ Ứng · 0 khoản/);
  assert.match(clean(week), /136.000.000 đ Thu · 5 khoản/);   // 50 + 30 + 40 + 7 + 9 triệu; khoản không đọc được số không tính
  assert.match(clean(week), /Chưa vào sổ: 1/);
  assert.match(clean(week), /Lệch số: 1/);
  assert.match(clean(week), /Không đọc được số: 1/);
  assert.deepEqual((await page.locator('.tc-day h3').allInnerTexts()).map(clean), ['Hôm nay 20/11', 'Hôm qua 19/11', '18/11', '17/11', '16/11', '15/11']);
  const rows = await page.locator('.tc-row').allInnerTexts();
  assert.match(clean(rows[0]), /^11:00 Lan Nhóm thu chi thử Thu 50\.000\.000 đ Sổ SỔ A .* Đã vào sổ Mở sổ Xử lý Mở tin$/);
  assert.match(clean(rows[1]), /Chi 2\.500\.000 đ Xe 51C-12345 .* Chờ vào sổ/);
  assert.match(clean(rows[2]), /Lệch: báo 30\.000\.000 đ, sổ 28\.000\.000 đ/);
  assert.match(clean(rows[3]), /Ứng 3\.000\.000 đ Tài xế Bình .* Đã vào sổ Mở Đội xe/);
  assert.match(clean(await page.locator('.tc-row[data-status="MISSING"]').innerText()), /Chưa vào sổ Quá 3 ngày/);
  assert.match(clean(await page.locator('.tc-row[data-status="SUGGEST"]').innerText()), /Có thể là phiếu của sổ SỔ D Người xác nhận/);
  assert.match(clean(await page.locator('.tc-row[data-status="UNKNOWN_TARGET"]').innerText()), /Chưa rõ của ai/);
  assert.match(clean(await page.locator('.tc-row[data-status="NO_LEDGER"]').innerText()), /Web chưa có sổ chi này/);
  const none = await page.locator('.tc-row[data-status="NO_AMOUNT"] .tc-amt').innerText();
  assert.equal(none.trim(), '—');   // không đọc được số: dấu gạch, không phải 0
  assert.match(await page.locator('#zalo-at').innerText(), /^Zalo cập nhật lúc 11:30$/);
  assert.equal(await page.locator('#zalo-warn').isHidden(), true);
  assert.equal(await page.locator('.tc-thumbs img').count(), 1);
}));

test('Thu chi: Mở tin sang đúng tin của Chat Zalo, Mở sổ sang đúng sổ và tháng', () => withPage(ok(ITEMS), async page => {
  await ready(page);
  assert.equal(await page.locator('.tc-open').first().getAttribute('href'), `/zalo-chat.html?c=${GROUP}&m=t1`);
  assert.equal(await page.locator('.tc-status a', { hasText: 'Mở sổ' }).first().getAttribute('href'), '/so-khach-v7-live.html?customer=1&month=2026-11');
  await page.locator('.tc-open').first().click();
  await page.waitForURL(/zalo-chat\.html\?c=1{64}&m=t1/);
}));

test('Thu chi: lọc Chưa vào sổ, Lệch số, Chưa rõ đối tượng ghi số đúng với danh sách; bàn phím bấm được', () => withPage(ok(ITEMS), async page => {
  await ready(page);
  assert.deepEqual((await page.locator('.tc-chip').allInnerTexts()).map(clean), ['Tất cả9', 'Chưa vào sổ1', 'Lệch số1', 'Chưa rõ đối tượng2', 'Không đọc được số1']);
  await page.locator('.tc-chip', { hasText: 'Chưa vào sổ' }).click();
  assert.equal(await page.locator('.tc-row').count(), 1);
  assert.equal(await page.locator('.tc-chip[aria-pressed="true"]').innerText().then(clean), 'Chưa vào sổ1');
  await page.locator('.tc-chip', { hasText: 'Chưa rõ đối tượng' }).click();
  assert.equal(await page.locator('.tc-row').count(), 2);
  // Bàn phím: Tab tới chip, Space bấm; chip giữ tiêu điểm sau khi vẽ lại.
  await page.locator('.tc-chip', { hasText: 'Lệch số' }).focus();
  await page.keyboard.press('Space');
  assert.equal(await page.locator('.tc-row').count(), 1);
  assert.equal(await page.evaluate(() => document.activeElement.dataset.f), 'diff');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement.dataset.f), 'noamount');
  assert.equal(await page.locator('.tc-row').count(), 1);
}));

test('Thu chi: khoản mới tự hiện sau một lượt hỏi, không cần tải lại', () => {
  let phase = 0;
  const added = item('n1', TODAY, 12, 'thu', 8_000_000, 'WAITING', { target: so(5, 'SỔ E') });
  return withPage(() => ({ body: body(phase ? [added, ...ITEMS] : ITEMS) }), async (page, state) => {
    await ready(page);
    assert.equal(await page.locator('.tc-row').count(), 9);
    phase = 1;
    await page.clock.runFor(5000);
    await page.locator('.tc-row.is-new').waitFor();
    assert.equal(await page.locator('.tc-row').count(), 10);
    assert.match(clean(await page.locator('.tc-row.is-new').innerText()), /Thu 8\.000\.000 đ Sổ SỔ E/);
    assert.equal(await page.locator('#new-note').innerText(), 'Có 1 khoản mới');
    assert.match(clean(await page.locator('.tc-card').first().innerText()), /58\.000\.000 đ Thu · 2 khoản/);
    assert.ok(state.calls.length >= 2);
  }, { clock: true });
});

const answer = page => page.waitForResponse(response => response.url().includes('/api/v7/cash-chat'));

test('Thu chi: tab ẩn thì ngừng hỏi, hiện lại thì hỏi ngay', () => withPage(ok(ITEMS), async (page, state) => {
  await ready(page);
  const setHidden = hidden => page.evaluate(value => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => value });
    document.dispatchEvent(new Event('visibilitychange'));
  }, hidden);
  await setHidden(true);
  const before = state.calls.length;
  await page.clock.runFor(30_000);
  await page.waitForTimeout(150);   // đồng hồ giả không chạy giờ thật: chờ chắc chắn không có yêu cầu nào đang bay
  assert.equal(state.calls.length, before);
  let answered = answer(page);   // đợi phản hồi mạng về rồi mới tua đồng hồ, để lượt đếm không chạy trước yêu cầu
  await setHidden(false);
  await answered;
  assert.equal(state.calls.length, before + 1);
  answered = answer(page);
  await page.clock.runFor(5000);
  await answered;
  assert.equal(state.calls.length, before + 2);
}, { clock: true }));

test('Thu chi: Zalo cũ hiện "cập nhật lần cuối" và cảnh báo, Zalo chưa mở ghi số phút', async () => {
  await withPage(() => ({ body: body(ITEMS, { zalo: { state: 'silent', at: '2026-11-20T08:05:00+07:00', silent_minutes: 200, identity: 'attached', quiet_minutes: 0 } }) }), async page => {
    await ready(page);
    assert.equal(await page.locator('#zalo-at').innerText(), 'Zalo cập nhật lần cuối lúc 08:05');
    assert.match(await page.locator('#zalo-warn').innerText(), /Máy Zalo không báo về từ 08:05/);
  });
  await withPage(() => ({ body: body(ITEMS, { zalo: { state: 'ok', at: '2026-11-20T11:30:00+07:00', silent_minutes: 0, identity: 'waiting_for_zalo', quiet_minutes: 42 } }) }), async page => {
    await ready(page);
    assert.match(await page.locator('#zalo-warn').innerText(), /Zalo chưa mở trên máy Zalo \(42 phút\)/);
    assert.equal(await page.locator('#zalo-at').getAttribute('class'), 'tc-zalo stale');
  });
  await withPage(() => ({ body: body(ITEMS, { zalo: { state: 'missing' }, bundle_at: '2026-11-19T22:00:00+07:00' }) }), async page => {
    await ready(page);
    assert.equal(await page.locator('#zalo-at').innerText(), 'Zalo cập nhật lúc 19/11 22:00');   // chưa có máy Zalo báo về: lấy giờ dựng gói, ghi cả ngày
  });
});

test('Thu chi: trống, thiếu gói, lỗi mạng (thử lại được) và mất mạng sau khi đã có số', async () => {
  await withPage(ok([]), async page => {
    await page.locator('.empty').waitFor();
    assert.match(await page.locator('.empty').innerText(), /Chưa có khoản thu chi nào trong 7 ngày/);
    assert.match(clean(await page.locator('.tc-card').first().innerText()), /0 đ Thu · 0 khoản/);
  });
  await withPage(() => ({ body: { unavailable: true, zalo: { state: 'missing' } } }), async page => {
    await page.locator('.empty').waitFor();
    assert.match(await page.locator('.empty').innerText(), /chưa có dữ liệu chat Zalo/);
  });
  let fail = true;
  await withPage(() => (fail ? { status: 503 } : { body: body(ITEMS) }), async page => {
    await page.locator('#error').waitFor();
    assert.match(await page.locator('#error').innerText(), /Không tải được thu chi\. Kiểm tra mạng rồi bấm Thử lại/);
    fail = false;
    await page.locator('#retry').click();
    await ready(page);
    assert.equal(await page.locator('#error').isHidden(), true);
  });
  let down = false;
  await withPage(() => (down ? { status: 503 } : { body: body(ITEMS) }), async page => {
    await ready(page);
    down = true;
    await page.clock.runFor(5000);
    await page.locator('#error').waitFor();
    assert.match(await page.locator('#error').innerText(), /Số đang hiện là lần tải trước/);
    assert.equal(await page.locator('.tc-row').count(), 9);
  }, { clock: true });
});

test('Thu chi: đổi sang 30 ngày hỏi đúng khoảng', () => withPage(ok(ITEMS), async (page, state) => {
  await ready(page);
  await page.locator('#range').selectOption('30');
  await ready(page);
  assert.match(state.calls.at(-1), /from=2026-10-22&to=2026-11-20/);
  assert.match(state.calls[0], /from=\d{4}-\d{2}-\d{2}&to=\d{4}-\d{2}-\d{2}/);
}));

test('Thu chi: 1280×720 không tràn ngang, tên sổ dài (chữ Hán) bị cắt gọn trong dòng', () => withPage(ok(ITEMS), async page => {
  await ready(page);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  const long = await page.locator('.tc-row[data-status="MISSING"]').evaluate(row => ({ row: row.getBoundingClientRect().width, target: row.querySelector('.tc-target').getBoundingClientRect().width }));
  assert.ok(long.target < long.row * 0.4, `cột đối tượng không phình: ${long.target}/${long.row}`);
  // Khối số và dòng đầu của danh sách thấy trong khung 1280×560 của Chrome thật.
  const top = await page.locator('.tc-row').first().evaluate(el => el.getBoundingClientRect().bottom);
  assert.ok(top <= 560, `dòng đầu nằm trong khung 560: ${top}`);
}));

test('Thu chi: điện thoại 390px, mỗi khoản là một thẻ gọn, không tràn ngang, nút đủ lớn để chạm', () => withPage(ok(ITEMS), async page => {
  await ready(page);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'không có thanh cuộn ngang');
  const open = await page.locator('.tc-open').first().boundingBox();
  assert.ok(open.height >= 40, `nút Mở tin cao ${open.height}`);
  const chip = await page.locator('.tc-chip').first().boundingBox();
  assert.ok(chip.height >= 40);
  const row = await page.locator('.tc-row').first().evaluate(el => {
    const box = el.getBoundingClientRect();
    return { width: box.width, parts: [...el.children].map(child => { const rect = child.getBoundingClientRect(); return [rect.left >= box.left - 1, rect.right <= box.right + 1]; }) };
  });
  assert.ok(row.parts.every(([left, right]) => left && right), 'mọi phần của thẻ nằm trong thẻ');
  assert.match(await page.locator('#zalo-at').innerText(), /Zalo cập nhật lúc/);   // tuổi dữ liệu vẫn thấy ở điện thoại
  const amount = await page.locator('.tc-row').first().locator('.tc-amt').boundingBox();
  assert.ok(amount.x > 195, 'số tiền ở bên phải của thẻ, cùng dòng với giờ và người gửi');
}, { viewport: { width: 390, height: 844 } }));

test('Thu chi: đang đọc (cuộn xuống) thì khoản mới không vẽ lại danh sách mà hiện nút; bấm nút hoặc cuộn về đầu thì nhận', () => {
  let phase = 0;
  const added = item('n1', TODAY, 12, 'thu', 8_000_000, 'WAITING', { target: so(5, 'SỔ E') });
  const more = item('n2', TODAY, 13, 'chi', 1_000_000, 'WAITING');
  return withPage(() => ({ body: body(phase === 2 ? [more, added, ...ITEMS] : phase ? [added, ...ITEMS] : ITEMS) }), async page => {
    await ready(page);
    await page.evaluate(() => { window.scrollTo(0, 400); document.querySelector('.tc-row').dataset.keep = '1'; });
    assert.ok(await page.evaluate(() => window.scrollY) > 120);
    phase = 1;
    let answered = answer(page);
    await page.clock.runFor(5000);
    await answered;
    await page.locator('#new-pill').waitFor();
    assert.equal(await page.locator('#new-pill').innerText(), 'Có 1 khoản mới, bấm để xem');
    assert.equal(await page.locator('.tc-row[data-keep]').count(), 1, 'danh sách không bị vẽ lại dưới tay người đọc');
    assert.equal(await page.locator('.tc-row').count(), 9);
    assert.ok(await page.evaluate(() => window.scrollY) > 120, 'không bị kéo đi chỗ khác');
    await page.locator('#new-pill').click();
    assert.equal(await page.locator('.tc-row').count(), 10);
    assert.equal(await page.locator('#new-pill').isHidden(), true);
    assert.equal(await page.evaluate(() => window.scrollY), 0);
    // Lần nữa: cuộn xuống, có khoản mới nữa, rồi tự cuộn về đầu thì nhận luôn, không cần bấm.
    phase = 2;
    await page.evaluate(() => window.scrollTo(0, 400));
    answered = answer(page);
    await page.clock.runFor(5000);
    await answered;
    await page.locator('#new-pill').waitFor();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.locator('#new-pill').waitFor({ state: 'hidden' });
    assert.equal(await page.locator('.tc-row').count(), 11);
  }, { clock: true, viewport: { width: 1280, height: 400 } });
});

test('Thu chi: tiêu điểm đang ở trong danh sách thì không vẽ lại, nút hiện thay', () => {
  let phase = 0;
  const added = item('n1', TODAY, 12, 'thu', 8_000_000, 'WAITING', { target: so(5, 'SỔ E') });
  return withPage(() => ({ body: body(phase ? [added, ...ITEMS] : ITEMS) }), async page => {
    await ready(page);
    await page.locator('.tc-open').first().focus();
    phase = 1;
    const answered = answer(page);
    await page.clock.runFor(5000);
    await answered;
    await page.locator('#new-pill').waitFor();
    assert.equal(await page.locator('.tc-row').count(), 9);
    assert.equal(await page.evaluate(() => document.activeElement.className), 'tc-open', 'tiêu điểm bàn phím không mất');
  }, { clock: true });
});

test('Thu chi: hồi từ "thiếu gói" không tô mọi khoản là mới, tô nền chỉ một lần', () => {
  let phase = 0;
  const added = item('n1', TODAY, 12, 'thu', 8_000_000, 'WAITING', { target: so(5, 'SỔ E') });
  return withPage(() => ({ body: phase === 0 ? { unavailable: true, zalo: { state: 'missing' } } : phase === 1 ? body(ITEMS) : body([added, ...ITEMS]) }), async page => {
    await page.locator('.empty').waitFor();
    phase = 1;
    await page.clock.runFor(5000);
    await ready(page);
    assert.equal(await page.locator('.tc-row.is-new').count(), 0);
    assert.equal(await page.locator('#new-note').innerText(), '');
    phase = 2;
    await page.clock.runFor(5000);
    await page.locator('.tc-row.is-new').waitFor();
    assert.equal(await page.locator('.tc-row.is-new').count(), 1);
    await page.locator('.tc-chip', { hasText: 'Lệch số' }).click();   // vẽ lại vì lọc: không tô lại
    await page.locator('.tc-chip', { hasText: 'Tất cả' }).click();
    assert.equal(await page.locator('.tc-row.is-new').count(), 0);
  }, { clock: true });
});

test('Thu chi: lỗi liên tiếp thì giãn nhịp hỏi (10 rồi 20 giây), hồi lại thì về 5 giây', () => {
  let down = false;
  return withPage(() => (down ? { status: 503 } : { body: body(ITEMS) }), async (page, state) => {
    await ready(page);
    const start = state.calls.length;
    down = true;
    let answered = answer(page);
    await page.clock.runFor(5000);
    await answered;
    assert.equal(state.calls.length, start + 1);
    await page.clock.runFor(5000);   // lần lỗi thứ nhất: lần sau cách 10 giây
    await page.waitForTimeout(150);
    assert.equal(state.calls.length, start + 1);
    answered = answer(page);
    await page.clock.runFor(5000);
    await answered;
    assert.equal(state.calls.length, start + 2);
    down = false;
    answered = answer(page);
    await page.clock.runFor(20_000);   // lỗi thứ hai: lần sau cách 20 giây
    await answered;
    await page.locator('#error').waitFor({ state: 'hidden' });
    answered = answer(page);
    await page.clock.runFor(5000);   // đã hồi: về nhịp 5 giây
    await answered;
    assert.equal(state.calls.length, start + 4);
  }, { clock: true });
});

test('Thu chi: giờ Zalo là ISO có múi giờ, đổi đúng sang giờ Việt Nam; loại đối tượng lạ không hiện "undefined"', async () => {
  await withPage(() => ({ body: body([item('x1', TODAY, 9, 'thu', 5_000_000, 'UNKNOWN_TARGET', { target: { kind: 'la', id: 1, label: null } })],
    { zalo: { state: 'ok', at: '2026-11-20T04:05:00Z', silent_minutes: 0, identity: 'attached', quiet_minutes: 0 } }) }), async page => {
    await ready(page);
    assert.equal(await page.locator('#zalo-at').innerText(), 'Zalo cập nhật lúc 11:05');
    assert.doesNotMatch(await page.locator('.tc-row').innerText(), /undefined|null/);
    assert.equal(clean(await page.locator('.tc-target').innerText()).startsWith('—'), true);
  });
});

test('Thu chi: nguồn sổ đọc lỗi thì báo rõ và khoản liên quan ghi "Chưa đối chiếu được", không phải "Chưa vào sổ"', () => withPage(
  () => ({ body: body([item('u1', '2026-11-10', 9, 'thu', 5_000_000, 'WAITING', { target: so(1, 'SỔ A'), unchecked: true })], { sources_failed: ['receipt', 'marks'] }) }), async page => {
    await ready(page);
    assert.match(await page.locator('#source-warn').innerText(), /Không đọc được phiếu thu, dấu khách báo đã chuyển lúc này/);
    assert.match(clean(await page.locator('.tc-row').innerText()), /Chưa đối chiếu được Không đọc được sổ lúc này/);
    assert.equal(await page.locator('.tc-chip', { hasText: 'Chưa vào sổ' }).innerText().then(clean), 'Chưa vào sổ0');
  }));

// PR-4b: ảnh chuyển khoản máy đọc (source 'anh'). Số, ngân hàng và tên sổ bịa.
const PAY = 'd'.repeat(64);
const shot = { id: PAY, mime: 'image/jpeg' };
const photo = (id, day, hour, amount, status, image, extra = {}) => item(id, day, hour, 'thu', amount, status, {
  source: 'anh', text: '', amount_from: amount == null ? null : 'anh', image_vnd: amount, media: [shot], image, ...extra });
const IMAGES = [
  photo('a1', TODAY, 10, 7_000_000, 'RECORDED', { by: 'ocr', bank: 'VIETCOMBANK', txn_time: '2026-11-20T09:58:00+07:00', candidates: [7_000_000] },
    { target: so(1, 'SỔ A'), ledger_ref: { kind: 'receipt', customer_id: 1, pid: 'PH-2', date: TODAY } }),
  photo('a2', TODAY, 9, null, 'NO_AMOUNT', { by: 'human', bank: null, txn_time: null, candidates: [1_050_000, 1_500_000] }),
  photo('a3', '2026-11-19', 15, 4_000_000, 'UNKNOWN_TARGET', { by: 'ocr', bank: 'MB', txn_time: '2026-11-19', candidates: [4_000_000] }, { link: 'none' }),
  item('t1', '2026-11-19', 9, 'thu', 5_000_000, 'RECORDED', { text: 'thu 5tr SỔ B', image_vnd: 5_500_000, image_diff: true, amount_from: null, ledger_vnd: 5_000_000,
    target: so(2, 'SỔ B'), ledger_ref: { kind: 'receipt', customer_id: 2, date: '2026-11-19' }, media: [shot] }),
];

test('Thu chi: ảnh chuyển khoản máy đọc hiện như khoản thu, ghi "đọc từ ảnh", giờ giao dịch rồi ngân hàng', () => withPage(ok(IMAGES), async page => {
  await ready(page);
  const [today, week] = (await page.locator('.tc-card').allInnerTexts()).map(clean);
  assert.match(today, /7\.000\.000 đ Thu · 1 khoản, 1 từ ảnh/);   // ảnh chưa đọc chắc không vào tổng
  assert.match(week, /16\.000\.000 đ Thu · 3 khoản, 2 từ ảnh/);
  assert.match(week, /Không đọc được số: 1/);
  const row = id => page.locator('.tc-row').filter({ has: page.locator(`a[href$="m=${id}"]`) });
  assert.match(clean(await row('a1').innerText()), /^10:00 Lan Nhóm thu chi thử Thu 7\.000\.000 đ đọc từ ảnh Sổ SỔ A Giao dịch 09:58 · VIETCOMBANK Đã vào sổ Mở sổ Xử lý Mở tin$/);
  assert.equal((await row('a2').locator('.tc-amt').innerText()).trim(), '—');
  assert.match(clean(await row('a2').innerText()), /Ảnh chưa đọc chắc Máy đọc ra 1\.050\.000 đ và 1\.500\.000 đ\. Mở ảnh để xem, không cộng vào tổng\./);
  assert.match(clean(await row('a3').innerText()), /— Ảnh chuyển khoản · MB Chưa rõ của ai Hội thoại chưa gắn sổ\./);
  assert.match(clean(await row('t1').innerText()), /Lệch: mẫu 5\.000\.000 đ, ảnh 5\.500\.000 đ Đã vào sổ\. Mở sổ/);   // đối chiếu vẫn giữ, có nút mở sổ
  assert.equal(await row('t1').locator('.tc-src').count(), 0);   // số gõ theo mẫu: không ghi "đọc từ ảnh"
  assert.equal(await page.locator('.tc-row[data-source="anh"] img').first().getAttribute('alt'), 'Ảnh chuyển khoản');
  assert.deepEqual((await page.locator('.tc-chip').allInnerTexts()).map(clean), ['Tất cả4', 'Chưa vào sổ0', 'Lệch số1', 'Chưa rõ đối tượng1', 'Không đọc được số1']);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
}));

test('Thu chi: dòng ảnh ở điện thoại 390px gọn trong thẻ, "đọc từ ảnh" nằm dưới số tiền', () => withPage(ok(IMAGES), async page => {
  await ready(page);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'không có thanh cuộn ngang');
  const box = await page.locator('.tc-row[data-source="anh"]').first().evaluate(el => {
    const card = el.getBoundingClientRect();
    const amount = el.querySelector('.tc-amt b, .tc-amt').getBoundingClientRect();
    const source = el.querySelector('.tc-src').getBoundingClientRect();
    return { inside: [...el.children].every(child => { const rect = child.getBoundingClientRect(); return rect.left >= card.left - 1 && rect.right <= card.right + 1; }),
      below: source.top >= amount.top, right: source.right <= card.right + 1 };
  });
  assert.deepEqual(box, { inside: true, below: true, right: true });
}, { viewport: { width: 390, height: 844 } }));

test('Thu chi: file đọc ảnh hỏng thì nói rõ khoản từ ảnh chưa hiện, không gộp vào câu "Chưa đối chiếu được"', () => withPage(
  () => ({ body: body([item('t1', TODAY, 9, 'thu', 5_000_000, 'WAITING', { target: so(1, 'SỔ A') })], { sources_failed: ['reads'] }) }), async page => {
    await ready(page);
    assert.equal(clean(await page.locator('#source-warn').innerText()), 'Không đọc được kết quả đọc ảnh chuyển khoản lúc này: khoản từ ảnh chưa hiện.');
  }));

test('Thu chi: danh sách nhóm gắn sổ đọc lỗi thì khoản từ ảnh ghi lý do, cảnh báo nêu đúng nguồn', () => withPage(
  () => ({ body: body([photo('a9', TODAY, 9, 7_000_000, 'UNKNOWN_TARGET', { by: 'ocr', bank: null, txn_time: null, candidates: [7_000_000] }, { unchecked: true, link: 'failed' })],
    { sources_failed: ['links'] }) }), async page => {
    await ready(page);
    assert.match(await page.locator('#source-warn').innerText(), /^Không đọc được danh sách nhóm gắn sổ lúc này\./);
    assert.match(clean(await page.locator('.tc-row').innerText()), /Ảnh chuyển khoản Chưa rõ của ai Không đọc được danh sách nhóm gắn sổ lúc này\./);
  }));

test('Thu chi: giờ giao dịch khác ngày tin thì ghi cả ngày; giờ không ghi múi là giờ Việt Nam', () => withPage(
  () => ({ body: body([
    photo('g1', '2026-11-19', 9, 1_000_000, 'WAITING', { by: 'ocr', bank: 'ACB', txn_time: '2026-11-18T16:50:00+00:00', candidates: [] }),   // 23:50 giờ Việt Nam
    photo('g2', '2026-11-19', 8, 2_000_000, 'WAITING', { by: 'ocr', bank: 'ACB', txn_time: '2026-11-18', candidates: [] }),
    photo('g3', '2026-11-19', 7, 3_000_000, 'WAITING', { by: 'ocr', bank: null, txn_time: '2026-11-19T06:15', candidates: [] })]) }), async page => {
    await ready(page);
    assert.deepEqual((await page.locator('.tc-row .tc-text').allInnerTexts()).map(clean),
      ['Giao dịch 23:50 18/11 · ACB', 'Giao dịch ngày 18/11 · ACB', 'Giao dịch 06:15']);
  }));

test('Thu chi: ảnh cũ gửi lại nằm ở ngày giao dịch, cột giờ ghi cả ngày tin; giao dịch trước khoảng xem chỉ được đếm, không cộng', () => withPage(
  () => ({ body: body([photo('o1', '2026-11-16', 10, 5_000_000, 'RECORDED', { by: 'ocr', bank: 'ACB', txn_time: '2026-11-16T10:15:00+07:00', candidates: [] },
    { sent_at: Date.parse('2026-11-19T15:12:00+07:00'), target: so(1, 'SỔ A'), link: 'one' })], { images_before: 2 }) }), async page => {
    await ready(page);
    assert.deepEqual((await page.locator('.tc-day h3').allInnerTexts()).map(clean), ['16/11']);
    assert.match(clean(await page.locator('.tc-row').innerText()), /^19\/11 15:12 Lan .* Giao dịch 10:15 · ACB Đã vào sổ/);
    assert.equal(clean(await page.locator('.tc-note').innerText()), '2 ảnh chuyển khoản gửi trong 7 ngày là giao dịch trước đó, không cộng vào tổng.');
  }));

// ---- Luồng 3 (PR-3): xác nhận, sửa số, gắn đối tượng, loại. Không ghi tiền; số, tên, biển số bịa. ----
const rowOf = (page, id) => page.locator(`.tc-row[data-k="chat:${id}"]`);
const openRow = async (page, id) => {
  await rowOf(page, id).locator('.tc-act').click();
  await page.locator('.tc-panel').waitFor();
};
const sentGets = state => state.calls.length;

test('Xử lý: hỏi đủ mọi trạng thái kể cả đã loại; Đúng, xác nhận ghi một lệnh, đóng khung, báo một dòng và tải lại ngay', () => withPage(ok(ITEMS), async (page, state) => {
  await ready(page);
  assert.match(state.calls[0], /&status=RECORDED,WAITING,MISSING,AMOUNT_DIFF,SUGGEST,UNKNOWN_TARGET,NO_LEDGER,NO_AMOUNT,NOT_CASH$/);
  await openRow(page, 't2');
  assert.equal(await rowOf(page, 't2').locator('.tc-act').getAttribute('aria-expanded'), 'true');
  assert.deepEqual((await page.locator('.tc-acts .btn').allInnerTexts()).map(clean), ['Đúng, xác nhận', 'Sửa số', 'Gắn sổ/xe', 'Không phải thu chi', 'Đóng']);
  assert.match(clean(await page.locator('.tc-panel .tc-hint').innerText()), /không ghi phiếu thu hay dòng chi/);
  assert.equal(await page.evaluate(() => document.activeElement.textContent), 'Đúng, xác nhận');   // tiêu điểm vào khung
  const before = sentGets(state);
  await page.locator('[data-act="confirm"]').click();
  await page.locator('#done:not([hidden])').waitFor();
  assert.equal(state.posts.length, 1);
  assert.deepEqual(Object.keys(state.posts[0]).sort(), ['action', 'message_id', 'request_id']);
  assert.deepEqual([state.posts[0].message_id, state.posts[0].action], ['t2', 'confirm']);
  assert.match(state.posts[0].request_id, /^[0-9a-f-]{36}$/);
  assert.equal(clean(await page.locator('#done').innerText()), 'Đã xác nhận khoản chi 2.500.000 đ của Lan.');
  assert.equal(await page.locator('.tc-panel').count(), 0);
  assert.ok(sentGets(state) > before, 'hỏi lại ngay, không đợi nhịp 5 giây');
}));

test('Xử lý: khoản đã xác nhận hiện người làm và lúc làm, không còn nút xác nhận; khoản không có số chưa xác nhận được', () => withPage(ok([
  item('r1', TODAY, 10, 'thu', 5_000_000, 'WAITING', { review: { decision: 'confirm', reviews: 2, last_action: 'confirm', last_by: 'lan', last_at: '2026-11-20T10:05:00+07:00' } }),
  item('r2', TODAY, 9, 'thu', 4_500_000, 'WAITING', { amount_from: 'sua', target: so(1, 'SỔ A'), target_from: 'sua' }),
  ...ITEMS]), async page => {
  await ready(page);
  assert.match(clean(await rowOf(page, 'r1').locator('.tc-status').innerText()), /Chờ vào sổ Đã xác nhận · lan · 10:05 · 2 lần/);
  assert.match(clean(await rowOf(page, 'r2').innerText()), /4\.500\.000 đ đã sửa tay Sổ SỔ A gắn tay/);
  await openRow(page, 'r1');
  assert.equal(await page.locator('.tc-acts [data-act="confirm"]').count(), 0);
  await openRow(page, 't8');   // mở dòng khác thì khung cũ đóng, chỉ một khung một lúc
  assert.equal(await page.locator('.tc-panel').count(), 1);
  assert.equal(await page.locator('.tc-acts [data-act="confirm"]').count(), 0);   // không đọc được số: chưa có gì để xác nhận
}));

test('Xử lý: sửa số chỉ nhận chữ số, hiện trước → sau, Enter lưu, gửi chuỗi VND nguyên', () => withPage(ok(ITEMS), async (page, state) => {
  await ready(page);
  await openRow(page, 't2');
  await page.locator('[data-act="amount"]').click();
  const input = page.locator('#tc-amount');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'tc-amount');
  const save = page.locator('.tc-panel [data-act="save"]');
  assert.equal(await save.isDisabled(), true);
  assert.equal(await page.locator('.tc-acts [data-act="confirm"]').getAttribute('class'), 'btn');   // một nút chính mỗi lúc: nút Lưu
  for (const bad of ['2,4tr', '500k', '0']) {
    await input.fill(bad);
    assert.match(await page.locator('#tc-preview').innerText(), /Chỉ gõ chữ số/);
    assert.equal(await save.isDisabled(), true);
  }
  await input.fill('2.500.000');
  assert.equal(await page.locator('#tc-preview').innerText(), 'Bằng số đang có, không cần sửa.');
  assert.equal(await save.isDisabled(), true);
  await input.fill('2.400.000');
  assert.equal(clean(await page.locator('#tc-preview').innerText()), 'Số: 2.500.000 đ → 2.400.000 đ');
  assert.equal(await save.isDisabled(), false);
  await input.press('Enter');
  await page.locator('#done:not([hidden])').waitFor();
  assert.deepEqual([state.posts[0].action, state.posts[0].value], ['amount', '2400000']);
  assert.equal(clean(await page.locator('#done').innerText()), 'Đã sửa số: 2.500.000 đ → 2.400.000 đ.');
}));

test('Xử lý: gắn đối tượng — thu chỉ chọn sổ, chi chọn xe hoặc tài xế; tìm bỏ dấu, biển số không cần gạch; danh sách hỏi một lần', () => withPage(ok(ITEMS), async (page, state) => {
  await ready(page);
  await openRow(page, 't9');   // thu chưa rõ của ai
  await page.locator('[data-act="target"]').click();
  await page.locator('.tc-opt').first().waitFor();
  assert.equal(await page.locator('.tc-kinds').count(), 0);
  assert.equal(await page.locator('.tc-field').innerText().then(clean), 'Tìm sổ');
  await page.locator('#tc-q').fill('so b');
  assert.deepEqual(await page.locator('.tc-opt').allInnerTexts(), ['SỔ B']);
  await page.locator('#tc-q').fill('陈氏');
  await page.locator('.tc-opt').click();
  assert.equal(await page.locator('.tc-opt').getAttribute('aria-selected'), 'true');
  assert.match(clean(await page.locator('#tc-preview').innerText()), /^Đối tượng: — → Sổ 陈氏贸易有限公司/);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'tên dài không làm tràn ngang');
  await page.locator('[data-act="close"]').click();
  assert.equal(await page.evaluate(() => document.activeElement.dataset.k), 'chat:t9');   // đóng thì tiêu điểm về nút Xử lý của dòng
  await openRow(page, 't2');   // chi xe
  await page.locator('[data-act="target"]').click();
  assert.deepEqual((await page.locator('.tc-kinds [role="radio"]').allInnerTexts()).map(clean), ['Xe', 'Tài xế']);
  assert.equal(await page.locator('[data-kind="xe"]').getAttribute('aria-checked'), 'true');   // đang gắn xe: mở đúng loại đang có
  await page.locator('#tc-q').fill('51c12345');
  await page.locator('.tc-opt').click();
  assert.equal(clean(await page.locator('#tc-preview').innerText()), 'Đúng đối tượng đang có, không cần gắn lại.');
  assert.equal(await page.locator('.tc-panel [data-act="save"]').isDisabled(), true);
  await page.locator('[data-kind="tai_xe"]').click();
  await page.locator('#tc-q').fill('cuong');
  await page.locator('.tc-opt').click();
  assert.equal(clean(await page.locator('#tc-preview').innerText()), 'Đối tượng: Xe 51C-12345 → Tài xế Cường');
  await page.locator('.tc-panel [data-act="save"]').click();
  await page.locator('#done:not([hidden])').waitFor();
  assert.deepEqual(state.posts.map(post => [post.message_id, post.action, post.value]), [['t2', 'target', { kind: 'tai_xe', id: 21 }]]);
  assert.equal(state.targetCalls, 1);
}));

test('Xử lý: loại bắt buộc lý do, ẩn khỏi danh sách, Hoàn tác đưa lại bằng một lần xác nhận với mã yêu cầu mới', () => {
  let dropped = false;
  const shown = () => ({ body: body(ITEMS.map(one => (dropped && one.message_id === 't7'
    ? { ...one, status: 'NOT_CASH', review: { decision: 'not_cash', reason: 'chuyển nội bộ', reviews: 1, last_action: 'not_cash', last_by: 'lan' } } : one))) });
  return withPage(shown, async (page, state) => {
    await ready(page);
    await openRow(page, 't7');
    await page.locator('[data-act="not_cash"]').click();
    const save = page.locator('.tc-panel [data-act="save"]');
    assert.equal(await save.innerText(), 'Loại khoản');
    assert.equal(await save.isDisabled(), true);
    await page.locator('#tc-reason').fill('   ');
    assert.equal(await save.isDisabled(), true);
    await page.locator('#tc-reason').fill(' chuyển nội bộ ');
    dropped = true;
    await save.click();
    await page.locator('#done:not([hidden])').waitFor();
    assert.deepEqual([state.posts[0].action, state.posts[0].reason], ['not_cash', 'chuyển nội bộ']);
    assert.match(clean(await page.locator('#done').innerText()), /^Đã loại khoản chi 5\.000\.000 đ của Lan\. Xem lại ở bộ lọc "Đã loại"\. Hoàn tác$/);
    await rowOf(page, 't7').waitFor({ state: 'detached' });
    assert.equal(await page.locator('.tc-chip', { hasText: 'Đã loại' }).innerText().then(clean), 'Đã loại1');
    assert.match(clean(await page.locator('.tc-card').nth(1).innerText()), /2\.500\.000 đ Chi · 1 khoản/);   // còn khoản chi xe, khoản đã loại không cộng
    await page.locator('.tc-chip', { hasText: 'Đã loại' }).click();
    assert.match(clean(await rowOf(page, 't7').innerText()), /Đã loại: không phải thu chi Lý do: chuyển nội bộ/);
    dropped = false;
    await page.locator('#done [data-undo]').click();
    await page.locator('#done', { hasText: 'Đã đưa khoản lại vào thu chi.' }).waitFor();
    assert.deepEqual([state.posts[1].message_id, state.posts[1].action], ['t7', 'confirm']);
    assert.notEqual(state.posts[1].request_id, state.posts[0].request_id);
  });
});

test('Xử lý: khoản đã loại mở ra chỉ có "Đưa lại vào thu chi"', () => withPage(ok([item('x1', TODAY, 9, 'chi', 1_000_000, 'NOT_CASH',
  { review: { decision: 'not_cash', reason: 'trùng', reviews: 1, last_action: 'not_cash' } }), ...ITEMS]), async (page, state) => {
  await ready(page);
  await page.locator('.tc-chip', { hasText: 'Đã loại' }).click();
  await openRow(page, 'x1');
  assert.deepEqual((await page.locator('.tc-acts .btn').allInnerTexts()).map(clean), ['Đưa lại vào thu chi', 'Đóng']);
  await page.locator('[data-act="restore"]').click();
  await page.locator('#done:not([hidden])').waitFor();
  assert.deepEqual([state.posts[0].action, clean(await page.locator('#done').innerText())], ['confirm', 'Đã đưa lại khoản chi 1.000.000 đ của Lan vào thu chi.']);
}));

test('Xử lý: lỗi của máy chủ hiện câu của máy chủ; mất mạng thì bấm lại cùng mã yêu cầu; mã đã dùng cho nội dung khác thì đổi mã', () => {
  const script = [{ status: 422, error: 'TARGET_NOT_FOUND', message: 'Không tìm thấy sổ, xe hay người này.' }, {},
    { status: 409, error: 'IDEMPOTENCY_CONFLICT', message: 'Mã yêu cầu đã dùng cho nội dung khác.' }, {}];
  return withPage(ok(ITEMS), async (page, state) => {
    await ready(page);
    await openRow(page, 't2');
    await page.locator('[data-act="confirm"]').click();
    await page.locator('.tc-perr:not([hidden])').waitFor();
    assert.equal(await page.locator('.tc-perr').innerText(), 'Không tìm thấy sổ, xe hay người này.');
    // Mất mạng: chặn ở trình duyệt (cắt socket thì Chrome tự gửi lại lệnh trên kết nối mới, không ra lỗi).
    let lost = null;
    await page.route('**/api/v7/cash-chat/review', route => { lost = route.request().postDataJSON(); return route.abort('failed'); });
    await page.locator('[data-act="confirm"]').click();
    await page.locator('.tc-perr', { hasText: 'Không chắc đã lưu' }).waitFor();
    await page.unroute('**/api/v7/cash-chat/review');
    await page.locator('[data-act="confirm"]').click();   // bấm lại sau mất mạng: cùng mã, máy chủ không ghi hai lần
    await page.locator('#done:not([hidden])').waitFor();
    assert.equal(state.posts[1].request_id, lost.request_id);
    await openRow(page, 't3');
    await page.locator('[data-act="confirm"]').click();
    await page.locator('.tc-perr', { hasText: 'Lần bấm trước đã được ghi với nội dung cũ' }).waitFor();
    await page.locator('[data-act="confirm"]').click();
    await page.locator('#done:not([hidden])').waitFor();
    assert.notEqual(state.posts[3].request_id, state.posts[2].request_id);
  }, { review: () => script.shift() ?? {} });
});

test('Xử lý: khung đang mở thì nhịp 5 giây không vẽ lại (chữ đang gõ còn nguyên), Esc đóng rồi nhận bản mới', () => {
  let phase = 0;
  const added = item('n1', TODAY, 12, 'thu', 8_000_000, 'WAITING', { target: so(5, 'SỔ E') });
  return withPage(() => ({ body: body(phase ? [added, ...ITEMS] : ITEMS) }), async page => {
    await ready(page);
    await openRow(page, 't2');
    await page.locator('[data-act="amount"]').click();
    await page.locator('#tc-amount').fill('2.400');
    await page.locator('.tc-day h3').first().click();   // tiêu điểm rời ô nhưng khung vẫn mở
    phase = 1;
    await page.clock.runFor(5000);
    await page.locator('#new-pill:not([hidden])').waitFor();
    assert.equal(await page.locator('#tc-amount').inputValue(), '2.400');
    assert.equal(await page.locator('.tc-row').count(), 9);
    await page.locator('#tc-amount').press('Escape');
    assert.equal(await page.locator('.tc-panel').count(), 0);
    assert.equal(await page.locator('.tc-row').count(), 10);
  }, { clock: true });
});

test('Xử lý: dấu khách báo và tin có hai ảnh chuyển khoản không có nút, tin hai ảnh nói lý do', () => withPage(ok([
  photo('p2', TODAY, 10, 1_000_000, 'WAITING', { by: 'ocr', candidates: [] }, { media: [{ id: '1'.repeat(64) }] }),
  photo('p2', TODAY, 10, 2_000_000, 'WAITING', { by: 'ocr', candidates: [] }, { media: [{ id: '2'.repeat(64) }] }),
  item('k1', TODAY, 9, 'thu', 3_000_000, 'WAITING', { source: 'mark' }), ...ITEMS]), async page => {
  await ready(page);
  const twins = page.locator('.tc-row[data-k^="anh:p2"]');
  assert.equal(await twins.locator('.tc-act').count(), 0);
  assert.match(clean(await twins.first().innerText()), /Tin có nhiều ảnh chuyển khoản: chưa xử lý riêng từng ảnh được/);
  assert.equal(await page.locator('.tc-row[data-k^="mark:k1"] .tc-act').count(), 0);
  assert.equal(await page.locator('.tc-row[data-k="chat:t1"] .tc-act').count(), 1);
}));

test('Xử lý: điện thoại 390px, khung gọn trong màn, nút đủ lớn để chạm', () => withPage(ok(ITEMS), async page => {
  await ready(page);
  await openRow(page, 't2');
  await page.locator('[data-act="not_cash"]').click();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'không có thanh cuộn ngang');
  for (const box of await page.locator('.tc-panel .btn, .tc-act').evaluateAll(els => els.map(el => el.getBoundingClientRect().toJSON()))) {
    assert.ok(box.height >= 40 && box.right <= 390, `nút ${JSON.stringify(box)}`);
  }
  const amount = await rowOf(page, 't2').locator('.tc-amt').boundingBox();
  assert.ok(amount.x > 195, 'số tiền vẫn ở bên phải, cụm nút xuống hàng riêng');
}, { viewport: { width: 390, height: 844 } }));

test('Xử lý: 1280×720, mở khung gắn thì nút Lưu nằm trong khung thấy (không bị đẩy dưới mép)', () => withPage(ok(ITEMS), async page => {
  await ready(page);
  await openRow(page, 't5');
  await page.locator('[data-act="target"]').click();
  await page.locator('.tc-opt').first().waitFor();
  const save = await page.locator('.tc-panel [data-act="save"]').boundingBox();
  assert.ok(save.y + save.height <= 720, `nút Lưu ở ${save.y}`);
  // Cột cuối cố định: số tiền các dòng thẳng một cột dù dòng có ảnh hay không.
  const rights = await page.locator('.tc-day').first().locator('.tc-amt').evaluateAll(els => els.map(el => Math.round(el.getBoundingClientRect().right)));
  assert.equal(new Set(rights).size, 1, `mép phải số tiền: ${rights}`);
}));
