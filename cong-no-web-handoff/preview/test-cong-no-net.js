const { test } = require('node:test');
const assert = require('node:assert/strict');
const { fetchJson, postJson, fetchResponse, readJson, messageOf } = require('./cong-no-net.js');

// Response giả đủ cho module: ok, status, json(); thân HTML thì json() ném SyntaxError như trình duyệt.
const respond = (status, body) => ({
  ok: status >= 200 && status < 300, status,
  json: async () => (typeof body === 'string' ? JSON.parse(body) : body),
});
const offline = async () => { throw new TypeError('Failed to fetch'); };

test('mất mạng: câu tiếng Việt có tên thứ đang tải, mã NETWORK, không lộ chữ trình duyệt', async () => {
  await assert.rejects(fetchJson('/api/x', { what: 'bảng giá', fetcher: offline }), error => {
    assert.equal(error.code, 'NETWORK');
    assert.equal(error.message, 'Không tải được bảng giá: mất kết nối tới máy chủ. Kiểm tra mạng rồi bấm lại.');
    return true;
  });
  await assert.rejects(fetchResponse('/api/x', { what: 'sổ', fetcher: offline }), { code: 'NETWORK' });
});

test('lỗi API giữ câu của máy chủ và mã; lỗi không có thân JSON thì câu theo mã HTTP', async () => {
  const api = async () => respond(409, { error: 'STALE_LEDGER', message: 'Sổ vừa thay đổi.' });
  await assert.rejects(fetchJson('/api/x', { fetcher: api }), { code: 'STALE_LEDGER', status: 409, message: 'Sổ vừa thay đổi.' });
  const proxy = async () => respond(502, '<html>Bad Gateway</html>');
  await assert.rejects(fetchJson('/api/x', { what: 'hàng chờ', fetcher: proxy }),
    { code: 'HTTP', status: 502, message: 'Không tải được hàng chờ: máy chủ đang bận hoặc đang khởi động lại. Chờ ít phút rồi bấm lại.' });
  const denied = async () => respond(403, '');
  await assert.rejects(fetchJson('/api/x', { fetcher: denied }), { status: 403, message: 'Không tải được dữ liệu: tài khoản này chưa được cấp quyền.' });
});

test('200 mà thân không đọc được là BAD_BODY; readJson tách thân hỏng với đứt mạng', async () => {
  await assert.rejects(fetchJson('/api/x', { what: 'sổ', fetcher: async () => respond(200, '<html>') }), { code: 'BAD_BODY' });
  await assert.rejects(readJson({ status: 200, json: async () => { throw new TypeError('network error'); } }, 'sổ'), { code: 'NETWORK' });
  assert.deepEqual(await readJson(respond(200, { a: 1 })), { a: 1 });
});

test('postJson gửi POST thân JSON, không cache', async () => {
  const seen = [];
  const data = await postJson('/api/y', { a: 1 }, { fetcher: async (url, init) => { seen.push([url, init]); return respond(200, { ok: true }); } });
  assert.deepEqual(data, { ok: true });
  assert.equal(seen[0][1].method, 'POST');
  assert.equal(seen[0][1].cache, 'no-store');
  assert.equal(seen[0][1].headers['Content-Type'], 'application/json');
  assert.equal(seen[0][1].body, '{"a":1}');
});

test('messageOf: chữ trình duyệt đổi thành câu tiếng Việt, câu đã Việt hóa giữ nguyên', () => {
  const offlineText = 'Không làm được: mất kết nối tới máy chủ. Kiểm tra mạng rồi bấm lại.';
  assert.equal(messageOf(new TypeError('Failed to fetch')), offlineText);
  assert.equal(messageOf(new TypeError('Load failed')), offlineText);   // Safari trên iPhone
  assert.equal(messageOf(new TypeError('NetworkError when attempting to fetch resource.')), offlineText);   // Firefox
  assert.equal(messageOf(Object.assign(new Error('signal is aborted without reason'), { name: 'AbortError', code: 20 })), offlineText);
  assert.equal(messageOf(new SyntaxError("Unexpected token '<', \"<html>\" is not valid JSON")), 'Máy chủ trả về dữ liệu không đọc được. Bấm lại sau ít phút.');
  assert.equal(messageOf(Object.assign(new Error('Sổ vừa thay đổi.'), { code: 'STALE_LEDGER' })), 'Sổ vừa thay đổi.');
  assert.equal(messageOf(new Error('Cần nhập lý do')), 'Cần nhập lý do');
  assert.equal(messageOf(null, 'Không lưu được.'), 'Không lưu được.');
  assert.equal(messageOf(new Error(''), 'Không lưu được.'), 'Không lưu được.');
});

test('customers: các phần cùng trang dùng chung một lần đọc; lỗi không giữ lại; fresh đọc lại', async () => {
  const { customers } = require('./cong-no-net.js');
  let calls = 0, fail = true;
  const fetcher = async () => { calls += 1; if (fail) throw new TypeError('Failed to fetch'); return respond(200, { customers: [{ id: 1 }] }); };
  await assert.rejects(customers({ fetcher, fresh: true }), { code: 'NETWORK' });
  fail = false;
  const [a, b] = await Promise.all([customers({ fetcher }), customers({ fetcher })]);
  assert.equal(calls, 2, 'lần lỗi không giữ lại; hai phần gọi cùng lúc chỉ một lần đọc');
  assert.equal(a, b);
  await customers({ fetcher });
  assert.equal(calls, 2, 'chưa quá 60 giây: dùng lại');
  await customers({ fetcher, fresh: true });
  assert.equal(calls, 3);
});
