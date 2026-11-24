const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// SO-TIEN P0-a lát 2: hai trang Sổ tiền và Đối soát ngày trên máy chủ giả cùng dạng /api/v7/tien/* (dữ liệu bịa: tài khoản giả,
// số tròn). Máy chủ giả giữ luật chính đủ để kiểm luồng màn (mã yêu cầu, quyết nghi trùng, giữ giao dịch cũ có lý do, kiểm ngày
// trước khi ký, version); luật tiền thật kiểm ở harness PostgreSQL (tools/test_pg_tien.py).
const TODAY = '2026-11-25';
const ACTOR = 'ketoan@gia';
const HASH = 'a'.repeat(64);

function world() {
  const tx = (id, date, direction, amount, description, extra = {}) => ({ id, booking_date: date, direction, amount_minor: String(amount),
    bank_ref: null, description, allocations: [], version: 0, voided: false, ...extra });
  const w = {
    roles: ['tien_nhap', 'tien_phan_bo', 'tien_review'], off: false, version: 3, seq: 100, keys: new Map(), posts: [], calls: [],
    failNext: 0, voidBlocked: false,
    tx: [tx(41, '2026-11-20', 'in', 50000, 'CK GIA MOT', { bank_ref: 'FT1', version: 1,
      allocations: [{ id: 1, target_kind: 'customer_unapplied', target_ref: { customer_id: '12' }, amount_minor: '50000', note: null }] }),
    tx(42, '2026-11-21', 'out', 20000, 'CHI GIA HAI'), tx(43, '2026-11-21', 'in', 30000, 'CK GIA BA'),
    tx(44, '2026-11-21', 'in', 30000, 'CK GIA BA LAN HAI'), tx(45, '2026-11-22', 'out', 15000, 'CHI GIA BON')],
    imports: [{ id: 9, status: 'committed', template: 'demo-csv@1', period_from: '2026-11-20', period_to: '2026-11-24', last_day_complete: false,
      counts: { rows: 5, new: 5, duplicate: 0, suspect: 0, error: 0 }, reason: null, stale: false,
      file: { id: 3, byte_size: 300, media_type: 'text/csv', name: 'sao-ke-gia-1.csv' },
      created: { actor: ACTOR, at: '2026-11-24T10:00:00+00:00' }, committed: { actor: ACTOR, at: '2026-11-24T10:01:00+00:00' }, closed: null }],
    view: null,
    days: {
      '2026-11-20': { coverage: 'full', coverage_status: 'signed', business_status: 'signed', evidence: [], reasons: [],
        history: [{ id: 2, track: 'business', action: 'sign', role_overlap: false, note: null, snapshot: { not_fully_allocated: 0 }, by: { actor: 'doichieu@gia', at: '2026-11-21T09:00:00+00:00' } },
          { id: 1, track: 'coverage', action: 'sign', role_overlap: false, note: null, snapshot: {}, by: { actor: 'doichieu@gia', at: '2026-11-21T08:00:00+00:00' } }] },
      '2026-11-21': { coverage: 'full', coverage_status: 'unconfirmed', business_status: 'open', reasons: [], history: [],
        evidence: [{ source: 'file', import_id: 9, amount_minor: '1090000', current: true }] },
      '2026-11-22': { coverage: 'full', coverage_status: 'unconfirmed', business_status: 'open', reasons: [], history: [],
        evidence: [{ source: 'file', import_id: 9, amount_minor: '1075000', current: true }] },
      '2026-11-23': { coverage: 'full', coverage_status: 'unconfirmed', business_status: 'open', reasons: ['NO_EVIDENCE'], history: [], evidence: [] },
      '2026-11-24': { coverage: 'partial', coverage_status: 'unconfirmed', business_status: 'open', reasons: ['DAY_INCOMPLETE', 'NO_EVIDENCE'], history: [], evidence: [] },
      '2026-11-25': { coverage: 'missing', coverage_status: 'unconfirmed', business_status: 'open', reasons: ['DAY_MISSING', 'MISSING_DAYS_BEFORE', 'NO_EVIDENCE'], history: [], evidence: [] },
    },
  };
  return w;
}

const signed = (amount, direction) => (direction === 'in' ? BigInt(amount) : -BigInt(amount));
const live = w => w.tx.filter(t => !t.voided);
const ledger = (w, date) => (1000000n + live(w).filter(t => t.booking_date <= date).reduce((s, t) => s + signed(t.amount_minor, t.direction), 0n)).toString();
function state(t) {
  const allocated = t.allocations.reduce((s, a) => s + BigInt(a.amount_minor), 0n);
  const status = t.voided ? 'voided' : t.direction === 'in'
    ? (!t.allocations.length ? 'unidentified' : t.allocations.every(a => a.target_kind === 'customer_unapplied') ? 'unapplied'
      : allocated < BigInt(t.amount_minor) ? 'partial' : 'applied')
    : (!t.allocations.length ? 'unmatched' : allocated < BigInt(t.amount_minor) ? 'partial' : 'matched');
  return { allocated_minor: allocated.toString(), unallocated_minor: (BigInt(t.amount_minor) - allocated).toString(), status };
}
const raw = w => w.roles.includes('tien_nhap') || w.roles.includes('tien_review');
function txRow(w, t) {
  return { id: t.id, direction: t.direction, amount_minor: t.amount_minor, currency: 'VND', booking_date: t.booking_date, value_date: null,
    bank_ref: t.bank_ref, voided: t.voided, version: t.version, sources: [], ...state(t), ...(raw(w) ? { description: t.description } : {}) };
}
function loi(status, error, message, extra = {}) { return Object.assign(new Error(message), { status, error, extra }); }
function day(w, date) {
  const d = w.days[date];
  const evidence = d.evidence.map(e => ({ ...e, difference_minor: (BigInt(ledger(w, date)) - BigInt(e.amount_minor)).toString() }));
  const reasons = d.reasons.filter(r => r !== 'BALANCE_DIFFERENCE');
  if (evidence.some(e => e.current && e.difference_minor !== '0')) reasons.push('BALANCE_DIFFERENCE');
  const txs = live(w).filter(t => t.booking_date === date);
  return { date, coverage: d.coverage, missing_before: [], missing_before_count: 0, pending_imports: [], ledger_closing_minor: ledger(w, date),
    evidence, reasons, ready: reasons.length === 0, account_id: 7, account_version: w.version, currency: 'VND', roles: w.roles,
    coverage_status: d.coverage_status, business_status: d.business_status, importers: [ACTOR],
    business: { transactions: txs.length, not_fully_allocated: txs.filter(t => !['applied', 'matched'].includes(state(t).status)).length },
    history: d.history };
}
function preview(w) {
  const lines = [
    { seq: 1, line_no: 1, booking_date: '2026-11-21', direction: 'out', amount_minor: '20000', currency: 'VND', bank_ref: null, description: 'CHI GIA HAI',
      class: 'duplicate', code: null, candidate: 42, soft_candidates: null },
    { seq: 2, line_no: 2, booking_date: '2026-11-24', direction: 'in', amount_minor: '70000', currency: 'VND', bank_ref: 'FT2', description: 'CK GIA MOI',
      class: 'new', code: null, candidate: null, soft_candidates: null },
    { seq: 3, line_no: 3, booking_date: '2026-11-21', direction: 'in', amount_minor: '30000', currency: 'VND', bank_ref: null, description: 'CK GIA BA FT9',
      class: 'suspect', code: null, candidate: null, soft_candidates: [43, 44] }];
  w.view = { import: { id: 10, account_id: 7, status: 'validated', template: 'demo-csv@1', period_from: '2026-11-21', period_to: '2026-11-24',
    opening_minor: '1050000', closing_minor: '1105000', last_day_complete: false, counts_at_preview: { rows: 3, new: 1, duplicate: 1, suspect: 1, error: 0 },
    preview_account_version: w.version, reason: null, file: { id: 4, byte_size: 200, media_type: 'text/csv', name: 'sao-ke-gia-2.csv' },
    created: { actor: ACTOR, at: '2026-11-25T10:00:00+00:00' }, committed: null, closed: null },
  account_version: w.version, currency: 'VND', raw_visible: raw(w), roles: w.roles, stale: false, lines: raw(w) ? lines : lines.map(({ description, ...l }) => l),
  preview_hash: HASH, counts: { rows: 3, new: 1, duplicate: 1, suspect: 1, error: 0 },
  balance: { opening_minor: '1050000', expected_opening_minor: '1050000', closing_minor: '1105000', computed_closing_minor: '1105000', chain_breaks: 0, unmatched_existing: 1 },
  breaks: [{ code: 'UNMATCHED_EXISTING', transaction_id: 45, booking_date: '2026-11-22', direction: 'out', amount_minor: '15000' }], signed_days: [] };
  w.imports.unshift({ id: 10, status: 'validated', template: 'demo-csv@1', period_from: '2026-11-21', period_to: '2026-11-24', last_day_complete: false,
    counts: w.view.counts, reason: null, stale: false, file: { id: 4, byte_size: 200, media_type: 'text/csv', name: 'sao-ke-gia-2.csv' },
    created: { actor: ACTOR, at: '2026-11-25T10:00:00+00:00' }, committed: null, closed: null });
  return { import_id: 10, status: 'validated', template: 'demo-csv@1', preview_account_version: w.version, preview_hash: HASH, counts: w.view.counts,
    balance: w.view.balance, breaks: w.view.breaks, lines, file_id: 4, signed_days: [] };
}

function read(w, route, q) {
  if (route === '/api/v7/tien/me') {
    if (w.off) throw loi(404, 'TIEN_OFF', 'Sổ tiền chưa bật.');
    return { mode: 'on', visible: w.roles.length > 0, actor: ACTOR, grants: w.roles.map(role => ({ role, legal_entity_id: 1, legal_entity_code: 'PN-GIA', account_id: null })),
      templates: [{ id: 'demo-csv@1', label: 'Mẫu thử CSV (chỉ dữ liệu giả)', media_type: 'text/csv', extension: '.csv' }] };
  }
  const account = { id: 7, legal_entity: { id: 1, code: 'PN-GIA', name: 'Phap nhan gia' }, kind: 'bank', bank_code: 'NHGIA', account_last4: '1234',
    currency: 'VND', holder: 'company', statement_template: 'demo-csv@1', status: 'active', roles: w.roles };
  if (route === '/api/v7/tien/accounts') return { accounts: [account] };
  if (route === '/api/v7/tien/accounts/7') {
    const unsigned = Object.values(w.days).filter(d => d.coverage === 'full' && d.coverage_status !== 'signed').length;
    return { account: { ...account, version: w.version }, opening: { as_of: '2026-11-20', amount_minor: '1000000' }, balance_minor: ledger(w, TODAY),
      today: TODAY, roles: w.roles, pending_imports: w.imports.filter(i => i.status === 'validated').length,
      coverage: { data_until: '2026-11-24', data_until_state: 'partial', complete_until: '2026-11-23', missing_days: [], missing_count: 0,
        unsigned_full_days: unsigned, last_signed_day: '2026-11-20' } };
  }
  if (route === '/api/v7/tien/accounts/7/imports') return { account_id: 7, account_version: w.version, roles: w.roles, imports: w.imports };
  if (route === '/api/v7/tien/accounts/7/transactions') {
    const rows = w.tx.filter(t => t.booking_date >= q.get('from') && t.booking_date <= q.get('to')).map(t => txRow(w, t));
    return { account_id: 7, description_visible: raw(w), transactions: rows };
  }
  if (route === '/api/v7/tien/accounts/7/coverage') {
    return { account_id: 7, today: TODAY, opening_as_of: '2026-11-20', days: Object.keys(w.days).sort().reverse().map(date => ({ date,
      coverage: w.days[date].coverage, coverage_status: w.days[date].coverage_status, business_status: w.days[date].business_status,
      transactions: live(w).filter(t => t.booking_date === date).length })) };
  }
  let m = /^\/api\/v7\/tien\/accounts\/7\/days\/(\d{4}-\d{2}-\d{2})$/.exec(route);
  if (m) return day(w, m[1]);
  if (route === '/api/v7/tien/imports/10') return w.view;
  m = /^\/api\/v7\/tien\/transactions\/(\d+)$/.exec(route);
  if (m) {
    const t = w.tx.find(x => x.id === Number(m[1]));
    return { transaction: txRow(w, t), description_visible: raw(w), roles: w.roles, coverage_status: 'unconfirmed',
      sources: [{ import_id: 9, role: 'origin', line_no: 1, import_status: 'committed', period_from: '2026-11-20', period_to: '2026-11-24' }],
      allocations: t.allocations, history: t.allocations.length ? [{ event_id: 5, before: [], after: t.allocations, reason: null, by: { actor: ACTOR, at: '2026-11-21T03:00:00+00:00' } }] : [] };
  }
  throw loi(404, 'NOT_FOUND', 'Không có đường dẫn này.');
}

function write(w, route, b) {
  const need = role => { if (!w.roles.includes(role)) throw loi(403, 'TIEN_FORBIDDEN', 'Bạn chưa được cấp vai sổ tiền cho việc này.'); };
  if (route === '/api/v7/tien/imports/preview') { need('tien_nhap'); return preview(w); }
  if (route === '/api/v7/tien/imports/commit') {
    if (b.expected_preview_hash !== HASH || w.view?.import.status !== 'validated') throw loi(409, 'IMPORT_PREVIEW_STALE', 'Sổ đã đổi từ lúc xem trước. Bỏ lô này rồi nhập lại file.');
    need(b.suspect_decisions || b.keep_existing ? 'tien_review' : 'tien_nhap');
    const decided = new Map((b.suspect_decisions ?? []).map(d => [d.line_no, d]));
    if (!decided.has(3)) throw loi(409, 'IMPORT_SUSPECT_UNRESOLVED', 'Còn dòng nghi trùng chưa quyết.');
    const kept = (b.keep_existing ?? []).filter(k => k.reason);
    if (!kept.some(k => k.transaction_id === 45) && decided.get(3).transaction_id !== 45) throw loi(409, 'BALANCE_CHAIN_BROKEN', 'Số dư của file không liền với sổ.', { detail: 'UNMATCHED_EXISTING' });
    w.tx.push({ id: ++w.seq, booking_date: '2026-11-24', direction: 'in', amount_minor: '70000', bank_ref: 'FT2', description: 'CK GIA MOI', allocations: [], version: 0, voided: false });
    if (decided.get(3).decision === 'new') w.tx.push({ id: ++w.seq, booking_date: '2026-11-21', direction: 'in', amount_minor: '30000', bank_ref: null, description: 'CK GIA BA FT9', allocations: [], version: 0, voided: false });
    w.view.import.status = 'committed';
    w.imports[0] = { ...w.imports[0], status: 'committed', committed: { actor: ACTOR, at: '2026-11-25T10:05:00+00:00' } };
    w.version += 1;
    return { import_id: 10, status: 'committed', account_version: w.version, created: decided.get(3).decision === 'new' ? 2 : 1,
      confirmed: decided.get(3).decision === 'new' ? 1 : 2, kept: kept.length, transaction_ids: [w.seq] };
  }
  if (route === '/api/v7/tien/imports/reject') {
    need('tien_nhap');
    if (!b.reason) throw loi(422, 'REASON_REQUIRED', 'Cần ghi lý do.');
    w.view.import.status = 'rejected';
    w.imports[0] = { ...w.imports[0], status: 'rejected', reason: b.reason, closed: { actor: ACTOR, at: '2026-11-25T10:06:00+00:00' } };
    return { import_id: b.import_id, status: 'rejected' };
  }
  if (route === '/api/v7/tien/imports/void') {
    need('tien_review');
    if (w.voidBlocked) throw loi(409, 'VOID_WOULD_LOSE_ALLOCATED', 'Lô có giao dịch đang phân bổ. Gỡ phân bổ trước khi hủy lô.');
    const imp = w.imports.find(i => i.id === b.import_id);
    imp.status = 'voided';
    imp.reason = b.reason;
    w.version += 1;
    return { import_id: b.import_id, status: 'voided', account_version: w.version, voided_transactions: [42], kept_transactions: [] };
  }
  if (route === '/api/v7/tien/allocations') {
    need('tien_phan_bo');
    const t = w.tx.find(x => x.id === b.transaction_id);
    if (t.version !== b.expected_version) throw loi(409, 'STALE_VERSION', 'Dữ liệu vừa đổi ở máy khác. Tải lại rồi làm lại.');
    if (t.allocations.length && !b.reason) throw loi(422, 'REASON_REQUIRED', 'Cần ghi lý do.');
    t.allocations = b.lines.map((l, i) => ({ id: 50 + i, note: null, ...l }));
    t.version += 1;
    return { transaction_id: t.id, version: t.version, ...state(t), allocations: t.allocations };
  }
  if (route === '/api/v7/tien/balance-evidence') {
    need('tien_review');
    const d = w.days[b.as_of_date];
    d.evidence.push({ source: b.source, evidence_id: ++w.seq, amount_minor: b.amount_minor, note: b.note, role_overlap: false, actor: ACTOR, at: '2026-11-25T10:10:00+00:00', current: true });
    d.reasons = d.reasons.filter(r => r !== 'NO_EVIDENCE');
    return { evidence_id: w.seq, account_id: 7, as_of_date: b.as_of_date, role_overlap: false };
  }
  const d = w.days[b.business_date];
  const history = (track, action, note = null) => d.history.unshift({ id: ++w.seq, track, action, role_overlap: false, note,
    snapshot: { not_fully_allocated: day(w, b.business_date).business.not_fully_allocated }, by: { actor: ACTOR, at: '2026-11-25T10:20:00+00:00' } });
  if (route === '/api/v7/tien/days/sign-coverage') {
    need('tien_review');
    if (b.expected_version !== w.version) throw loi(409, 'STALE_VERSION', 'Dữ liệu vừa đổi ở máy khác. Tải lại rồi làm lại.');
    const now = day(w, b.business_date);
    if (!now.ready) throw loi(409, 'DAY_NOT_READY', 'Ngày này chưa ký được.', { detail: now.reasons.join(',') });
    d.coverage_status = 'signed';
    history('coverage', 'sign');
    return { account_id: 7, business_date: b.business_date, coverage_status: 'signed', changed: true, role_overlap: false };
  }
  if (route === '/api/v7/tien/days/sign-business') {
    need('tien_review');
    if (d.coverage_status !== 'signed') throw loi(409, 'DAY_NOT_READY', 'Ngày này chưa ký được.', { detail: 'COVERAGE_NOT_SIGNED' });
    d.business_status = 'signed';
    history('business', 'sign');
    return { account_id: 7, business_date: b.business_date, business_status: 'signed', changed: true, role_overlap: false,
      not_fully_allocated: day(w, b.business_date).business.not_fully_allocated };
  }
  if (route === '/api/v7/tien/days/reopen') {
    need('tien_review');
    if (b.track === 'coverage') { d.coverage_status = 'reopened'; history('coverage', 'reopen', b.reason); }
    if (d.business_status === 'signed') { d.business_status = 'reopened'; history('business', 'reopen', b.reason); }
    return { account_id: 7, business_date: b.business_date, coverage_status: d.coverage_status, business_status: d.business_status };
  }
  throw loi(404, 'NOT_FOUND', 'x');
}

function makeServer(w) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x');
    const route = url.pathname;
    const send = (status, headers, body) => { response.writeHead(status, headers); response.end(body); };
    const out = (body, status = 200) => send(status, { 'Content-Type': 'application/json' }, JSON.stringify(body));
    w.calls.push(`${request.method} ${route}${url.search}`);
    if (route.startsWith('/api/v7/tien')) {
      if (request.method === 'GET') {
        if (route === '/api/v7/tien/files/3') {
          return send(200, { 'Content-Type': 'text/csv', 'Content-Disposition': "attachment; filename=\"sao-ke-gia-1.csv\"; filename*=UTF-8''sao-ke-gia-1.csv" }, 'date,ref\n');
        }
        if (route === '/api/v7/tien/accounts/7/export.xlsx') {
          return send(200, { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': "attachment; filename=\"so-tien.xlsx\"; filename*=UTF-8''so-tien-NHGIA-1234.xlsx" }, 'PK-gia');
        }
        try { return out(read(w, route, url.searchParams)); } catch (e) { return out({ error: e.error, message: e.message, ...e.extra }, e.status ?? 500); }
      }
      let body = '';
      request.on('data', chunk => { body += chunk; });
      request.on('end', () => {
        const b = JSON.parse(body);
        w.posts.push({ route, body: b });
        if (w.failNext > 0) { w.failNext -= 1; request.socket.destroy(); return; }
        try {
          if (w.keys.has(b.idempotency_key)) return out(w.keys.get(b.idempotency_key));
          const result = write(w, route, b);
          w.keys.set(b.idempotency_key, result);
          return out(result);
        } catch (e) { return out({ error: e.error, message: e.message, ...e.extra }, e.status ?? 500); }
      });
      return undefined;
    }
    if (route === '/api/v7/customers') return out({ customers: [{ id: 12, name: 'Khách Giả Một' }, { id: 13, name: 'Khách Giả Hai' }] });
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 503);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, { 'Content-Type': 'text/plain' }, 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, { 'Content-Type': type }, fs.readFileSync(file));
  });
}

async function withPage(page, fn, { setup, query = '' } = {}) {
  const w = world();
  setup?.(w);
  const server = makeServer(w);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, acceptDownloads: true });
    const tab = await context.newPage();
    const errors = [];
    tab.on('pageerror', error => errors.push(error.message));
    const consoleErrors = [];
    tab.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
    await tab.goto(`http://127.0.0.1:${server.address().port}/${page}${query}`);
    await tab.locator('body[data-loaded]').waitFor({ state: 'attached', timeout: 10000 }).catch(error => {
      throw new Error(`trang không tải xong: ${[...errors, ...consoleErrors].join(' | ') || error.message}`);
    });
    await fn(tab, w);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
// Ảnh để soát giao diện bằng mắt (dữ liệu giả): chạy với SHOTS_DIR=<thư mục ngoài repo>.
async function shot(page, name) {
  if (!process.env.SHOTS_DIR) return;
  fs.mkdirSync(process.env.SHOTS_DIR, { recursive: true });
  await page.screenshot({ path: path.join(process.env.SHOTS_DIR, `so-tien-${name}.png`) });
}
const posts = (w, route) => w.posts.filter(p => p.route === `/api/v7/tien${route}`);
const toast = (page, text) => page.locator('#st-toast').filter({ hasText: text }).waitFor();
const CSV = Buffer.from('#period,2026-11-21,2026-11-24,partial\ndate,ref,description,debit,credit,balance\n2026-11-24,FT2,CK GIA MOI,,70000,\n');

test('Sổ tiền: thẻ số dư tới ngày nào, lô đã nhập, giao dịch tháng, mở chi tiết giao dịch', () => withPage('so-tien.html', async (page, w) => {
  await shot(page, '1-so-tien');
  assert.equal(await page.locator('#st-balance').innerText(), '1.075.000 đ');
  const card = page.locator('.st-hero');
  assert.match(await card.innerText(), /Dữ liệu tới ngày 24\/11\/2026; ngày này chưa trọn[\s\S]*Không thiếu ngày nào[\s\S]*3 ngày đủ sao kê chưa ký số dư/);
  assert.ok((await card.boundingBox()).y + (await card.boundingBox()).height < 560, 'thẻ số dư nằm trong phần màn thấy được 1280×560');
  assert.match(await page.locator('#st-account').innerText(), /NHGIA ••••1234 · VND/);
  assert.match(await page.locator('table').nth(0).innerText(), /20\/11\/2026 – 24\/11\/2026\s+Đã ghi\s+5 dòng · 5 mới/);
  const rows = page.locator('tr.st-row');
  assert.equal(await rows.count(), 5);
  assert.match(await rows.nth(1).innerText(), /21\/11\/2026\s+20\.000 đ\s+CHI GIA HAI\s+Chưa ghép\s+20\.000 đ/);
  await rows.nth(1).click();
  const detail = page.locator('tr.st-detail');
  await detail.waitFor();
  assert.match(await detail.innerText(), /Nguồn[\s\S]*dòng 1[\s\S]*Chưa phân bổ\.[\s\S]*Phân bổ ở Đối soát ngày 21\/11\/2026/);
  assert.equal(await detail.locator('a').getAttribute('href'), '/doi-soat-ngay.html?account=7&date=2026-11-21');
  await page.locator('select[data-act="status"]').selectOption('unidentified');
  assert.equal(await rows.count(), 2, 'lọc theo trạng thái');
  const download = page.waitForEvent('download');
  await page.locator('[data-act="export"]').click();
  assert.equal((await download).suggestedFilename(), 'so-tien-NHGIA-1234.xlsx');
  assert.ok(w.calls.includes('GET /api/v7/tien/accounts/7/export.xlsx?from=2026-11-01&to=2026-11-25'));
}));

test('Nhập sao kê: xem trước, quyết dòng nghi trùng và giao dịch cũ (lý do), ghi vào sổ một lần', () => withPage('so-tien.html', async (page, w) => {
  await page.locator('input[data-act="upload"]').setInputFiles({ name: 'sao-ke-gia-2.csv', mimeType: 'text/csv', buffer: CSV });
  const review = page.locator('#st-review');
  await review.waitFor();
  await shot(page, '2-xem-truoc');
  assert.deepEqual(posts(w, '/imports/preview').map(p => ({ ...p.body, idempotency_key: '?' })), [{ idempotency_key: '?', account_id: 7,
    template: 'demo-csv@1', file_name: 'sao-ke-gia-2.csv', content_base64: CSV.toString('base64') }]);
  assert.match(await review.innerText(), /3 dòng: 1 mới · 1 đã có trong sổ · 1 cần quyết · 0 lỗi[\s\S]*Số dư đầu, cuối của file liền với sổ\./);
  const ask = page.locator('.st-q').nth(0);
  assert.match(await ask.innerText(), /Dòng 3 · 21\/11\/2026 · Thu 30\.000 đ · CK GIA BA FT9[\s\S]*Đây là giao dịch mới[\s\S]*Trùng giao dịch đã có: 21\/11\/2026 · Thu 30\.000 đ · CK GIA BA[\s\S]*CK GIA BA LAN HAI/);
  assert.match(await page.locator('.st-q').nth(1).innerText(), /Giao dịch đã có trong sổ: 22\/11\/2026 · Chi 15\.000 đ · CHI GIA BON[\s\S]*File mới không có/);
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Dòng 3: chọn giao dịch mới hay trùng.');
  assert.equal(posts(w, '/imports/commit').length, 0, 'thiếu quyết định thì không gửi');
  await ask.locator('input[value="43"]').check();
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'ghi lý do giữ');
  await page.locator('textarea[data-keep="45"]').fill('Ngân hàng chưa trả giao dịch này, giữ để đối chiếu');
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Đã ghi vào sổ: 1 giao dịch mới, 2 dòng đã có, giữ 1 giao dịch cũ.');
  const [sent] = posts(w, '/imports/commit');
  assert.deepEqual({ ...sent.body, idempotency_key: '?' }, { idempotency_key: '?', import_id: 10, expected_preview_hash: HASH,
    suspect_decisions: [{ line_no: 3, decision: 'duplicate_of', transaction_id: 43 }],
    keep_existing: [{ transaction_id: 45, reason: 'Ngân hàng chưa trả giao dịch này, giữ để đối chiếu' }] });
  assert.equal(await review.count(), 0, 'ghi xong thì đóng hộp xem trước');
  assert.equal(await page.locator('#st-balance').innerText(), '1.145.000 đ', 'thẻ đọc lại số dư mới');
}));

test('Vai: chỉ có vai nhập thì không quyết được nghi trùng; chỉ có vai xem thì không thấy khối nhập, file gốc, xuất Excel', async () => {
  await withPage('so-tien.html', async page => {
    await page.locator('[data-act="open-import"]').first().click();
    await page.locator('#st-review').waitFor();
    assert.ok(await page.locator('.st-q input[type="radio"]').first().isDisabled());
    assert.ok(await page.locator('[data-act="commit"]').isDisabled());
    assert.match(await page.locator('.st-ro').innerText(), /2 chỗ cần người đối chiếu quyết/);
  }, { setup: w => { w.roles = ['tien_nhap']; preview(w); } });
  await withPage('so-tien.html', async page => {
    assert.equal(await page.locator('#st-import-title').count(), 0);
    assert.equal(await page.locator('[data-act="download-file"]').count(), 0);
    assert.equal(await page.locator('[data-act="export"]').count(), 0);
    assert.equal(await page.locator('th', { hasText: 'Nội dung' }).count(), 0, 'người xem không thấy nội dung chuyển khoản');
  }, { setup: w => { w.roles = ['tien_xem']; } });
});

test('Bỏ lô và hủy lô cần lý do; mất mạng khi ghi thì giữ quyết định, bấm lại dùng đúng mã yêu cầu', () => withPage('so-tien.html', async (page, w) => {
  await page.locator('[data-act="void"]').click();
  const dialog = page.locator('#st-reason');
  await dialog.waitFor();
  await page.locator('#st-reason-ok').click();
  assert.ok(await dialog.isVisible(), 'chưa ghi lý do thì hộp không đóng');
  await page.locator('#st-reason-input').fill('Nhập nhầm file của tài khoản khác');
  await page.locator('#st-reason-ok').click();
  await toast(page, 'Lô có giao dịch đang phân bổ');
  assert.deepEqual(posts(w, '/imports/void').map(p => p.body.reason), ['Nhập nhầm file của tài khoản khác']);
  w.voidBlocked = false;
  await page.locator('input[data-act="upload"]').setInputFiles({ name: 'sao-ke-gia-2.csv', mimeType: 'text/csv', buffer: CSV });
  await page.locator('#st-review').waitFor();
  await page.locator('.st-q').nth(0).locator('input[value="new"]').check();
  await page.locator('textarea[data-keep="45"]').fill('Giữ giao dịch giả');
  // Máy chủ đã ghi nhưng trả lời mất trên đường (route.fetch rồi abort): trang báo mất kết nối, bấm lại phải dùng đúng mã yêu cầu để
  // máy chủ trả kết quả cũ thay vì ghi lần hai. (Hủy socket ở máy chủ giả thì Chrome tự gửi lại lệnh, không thấy lỗi.)
  await page.route('**/api/v7/tien/imports/commit', async route => { await route.fetch(); await route.abort('failed'); }, { times: 1 });
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Mất kết nối');
  assert.ok(await page.locator('.st-q').nth(0).locator('input[value="new"]').isChecked(), 'quyết định còn nguyên sau khi mất mạng');
  const before = w.tx.length;
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Đã ghi vào sổ: 2 giao dịch mới');
  const keys = posts(w, '/imports/commit').map(p => p.body.idempotency_key);
  assert.equal(keys.length, 2);
  assert.equal(keys[0], keys[1], 'gửi lại sau mất mạng dùng cùng mã');
  assert.equal(w.tx.length, before, 'lần gửi lại nhận kết quả cũ, không ghi giao dịch lần hai');
}, { setup: w => { w.voidBlocked = true; } }));

test('Đối soát ngày: mở ngày còn việc, ký số dư, ký đối soát, mở lại; ngày thiếu số dư ngân hàng nhập tay rồi ký', () => withPage('doi-soat-ngay.html', async (page, w) => {
  await shot(page, '3-doi-soat');
  const current = page.locator('.st-days button[aria-current="true"]');
  assert.match(await current.innerText(), /Thứ Bảy 21\/11[\s\S]*Số dư: Chưa ký/);
  const balance = page.locator('section[aria-labelledby="st-bal-title"]');
  assert.match(await balance.innerText(), /Số dư cuối ngày Thứ Bảy 21\/11\/2026[\s\S]*Khớp, chờ ký[\s\S]*1\.090\.000 đ[\s\S]*File sao kê \(lô #9\) · bản mới nhất, dùng để ký[\s\S]*Khớp/);
  assert.ok(await page.locator('[data-act="sign-business"]').isDisabled(), 'ký đối soát sau khi ký số dư');
  await page.locator('[data-act="sign-coverage"]').click();
  await toast(page, 'Đã ký số dư ngày 21/11/2026');
  assert.deepEqual(posts(w, '/days/sign-coverage').map(p => ({ ...p.body, idempotency_key: '?' })),
    [{ idempotency_key: '?', account_id: 7, business_date: '2026-11-21', expected_version: 3 }]);
  assert.match(await balance.innerText(), /Đã ký số dư[\s\S]*Ký bởi ketoan@gia/);
  await page.locator('[data-act="sign-business"]').click();
  await toast(page, 'Đã ký đối soát ngày 21/11/2026; còn 3 khoản chưa phân bổ đủ.');
  await page.locator('[data-act="reopen"][data-track="business"]').click();
  await page.locator('#st-reason-input').fill('Phân bổ lại khoản giả');
  await page.locator('#st-reason-ok').click();
  await toast(page, 'Đã mở lại.');
  assert.deepEqual(posts(w, '/days/reopen').map(p => [p.body.track, p.body.reason]), [['business', 'Phân bổ lại khoản giả']]);
  assert.match(await page.locator('section[aria-labelledby="st-hist-title"]').innerText(), /Đối soát: mở lại[\s\S]*Phân bổ lại khoản giả[\s\S]*Đối soát: ký[\s\S]*Số dư: ký/);
  await page.locator('.st-days button[data-date="2026-11-23"]').click();
  await page.locator('.st-days button[data-date="2026-11-23"][aria-current="true"]').waitFor();
  assert.match(await balance.innerText(), /Chưa có số dư cuối ngày của ngân hàng/);
  assert.ok(await page.locator('[data-act="sign-coverage"]').isDisabled());
  await page.locator('[data-act="ev-open"]').click();
  await page.locator('input[data-ev="amount"]').fill('1.075.000');
  await page.locator('[data-act="ev-save"]').click();
  await toast(page, 'Ghi chú lấy số dư từ đâu');
  await page.locator('input[data-ev="note"]').fill('Sao kê PDF giả tải lúc 17:05');
  await page.locator('[data-act="ev-save"]').click();
  await toast(page, 'Đã lưu số dư ngân hàng.');
  assert.deepEqual(posts(w, '/balance-evidence').map(p => ({ ...p.body, idempotency_key: '?' })), [{ idempotency_key: '?', account_id: 7,
    as_of_date: '2026-11-23', amount_minor: '1075000', source: 'bank_pdf', note: 'Sao kê PDF giả tải lúc 17:05' }]);
  assert.ok(await page.locator('[data-act="sign-coverage"]').isEnabled());
  await shot(page, '4-doi-soat-bang-chung');
}));

test('Phân bổ: chọn sổ khách, chia dòng, còn lại tính sẵn, vượt số tiền thì báo, đổi dòng cũ cần lý do', () => withPage('doi-soat-ngay.html', async (page, w) => {
  await page.locator('[data-act="alloc"][data-id="43"]').click();
  const dialog = page.locator('#st-alloc');
  await dialog.waitFor();
  assert.match(await dialog.innerText(), /21\/11\/2026 · Thu 30\.000 đ · CK GIA BA[\s\S]*Còn lại chưa phân bổ: 0 đ/);
  await dialog.locator('select[data-field="ref"]').selectOption('12');
  await dialog.locator('input[data-field="amount"]').fill('20.000');
  assert.equal(await page.locator('#st-alloc-left').innerText(), 'Còn lại chưa phân bổ: 10.000 đ');
  await dialog.locator('[data-act="alloc-add"]').click();
  await dialog.locator('select[data-field="kind"]').nth(1).selectOption('interest');
  await dialog.locator('input[data-field="amount"]').nth(1).fill('15.000');
  assert.equal(await page.locator('#st-alloc-left').innerText(), 'Vượt số tiền giao dịch 5.000 đ');
  await shot(page, '5-phan-bo');
  await dialog.locator('[data-act="alloc-save"]').click();
  assert.match(await dialog.innerText(), /Tổng các dòng vượt số tiền giao dịch\./);
  await dialog.locator('input[data-field="amount"]').nth(1).fill('10.000');
  await dialog.locator('[data-act="alloc-save"]').click();
  await toast(page, 'Đã lưu phân bổ. Còn lại chưa phân bổ: 0 đ.');
  assert.deepEqual(posts(w, '/allocations').map(p => ({ ...p.body, idempotency_key: '?' })), [{ idempotency_key: '?', transaction_id: 43, expected_version: 0,
    lines: [{ target_kind: 'customer_unapplied', target_ref: { customer_id: '12' }, amount_minor: '20000' }, { target_kind: 'interest', target_ref: {}, amount_minor: '10000' }] }]);
  assert.equal(await dialog.isVisible(), false);
  await page.locator('[data-act="alloc"][data-id="43"]').click();
  await dialog.waitFor();
  await dialog.locator('[data-act="alloc-remove"]').nth(1).click();
  await dialog.locator('[data-act="alloc-save"]').click();
  assert.match(await dialog.innerText(), /Bỏ hay đổi dòng đã có: ghi lý do\./);
  await dialog.locator('input[data-alloc-reason]').fill('Lãi ghi nhầm');
  await dialog.locator('[data-act="alloc-save"]').click();
  await toast(page, 'Đã lưu phân bổ.');
  assert.deepEqual(posts(w, '/allocations')[1].body.reason, 'Lãi ghi nhầm');
  assert.equal(posts(w, '/allocations')[1].body.expected_version, 1);
}));

test('Cờ tắt hoặc chưa có vai: câu báo thay cho màn, không lỗi trang', async () => {
  for (const page of ['so-tien.html', 'doi-soat-ngay.html']) {
    await withPage(page, async tab => {
      assert.match(await tab.locator('#st-root').innerText(), /Sổ tiền chưa bật trên máy này\./);
    }, { setup: w => { w.off = true; } });
    await withPage(page, async tab => {
      assert.match(await tab.locator('#st-root').innerText(), /Bạn chưa được cấp vai sổ tiền/);
    }, { setup: w => { w.roles = []; } });
  }
});
