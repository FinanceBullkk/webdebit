const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// SO-TIEN P0-a lát 2: hai trang Sổ tiền và Đối soát ngày trên máy chủ giả cùng dạng /api/v7/tien/* (dữ liệu bịa: tài khoản giả,
// số tròn). Máy chủ giả làm theo luật của hàm SQL thật ở những chỗ màn phụ thuộc: phân loại lô (dòng nghi trùng mềm có đúng một
// ứng viên, giao dịch cùng tiền còn lại là UNMATCHED_EXISTING), commit_import (mọi giao dịch của U là đích "trùng" hoặc giữ có lý
// do; đích "trùng" cùng ngày/chiều/tiền, không hai lần), set_allocation (lý do khi bỏ hay đổi dòng cũ, mã đích là chuỗi số), chặn
// ngày đã ký (DAY_SIGNED kèm ngày), mở lại ngày kéo theo các ngày sau. Câu báo lỗi chép từ v7_api_tables.ERRORS. Luật tiền thật
// kiểm ở harness PostgreSQL (tools/test_pg_tien.py).
const TODAY = '2026-11-25';
const ACTOR = 'ketoan@gia';
const HASH = 'a'.repeat(64);
const MESSAGES = {
  TIEN_OFF: [404, 'Sổ tiền chưa bật.'],
  NOT_FOUND: [404, 'Không có đường dẫn này.'],
  TIEN_FORBIDDEN: [403, 'Bạn chưa được cấp vai sổ tiền cho việc này.'],
  IMPORT_HAS_ERRORS: [409, 'Lô còn dòng lỗi nên chưa ghi vào sổ được. Sửa file rồi nhập lại.'],
  IMPORT_SUSPECT_UNRESOLVED: [409, 'Còn dòng nghi trùng chưa quyết.'],
  IMPORT_PREVIEW_STALE: [409, 'Sổ đã đổi từ lúc xem trước. Bỏ lô này rồi nhập lại file.'],
  BALANCE_CHAIN_BROKEN: [409, 'Số dư của file không liền với sổ. Xem chỗ gãy trong bảng xem trước.'],
  DUPLICATE_TARGET_INVALID: [409, 'Giao dịch chọn làm bản trùng không hợp lệ: phải cùng ngày, cùng chiều, cùng số tiền và chưa được dòng khác nhận.'],
  VOID_WOULD_LOSE_ALLOCATED: [409, 'Lô có giao dịch đang phân bổ. Gỡ phân bổ trước khi hủy lô.'],
  OVER_ALLOCATION: [409, 'Tổng phân bổ vượt số tiền giao dịch.'],
  STALE_VERSION: [409, 'Dữ liệu vừa đổi ở máy khác. Tải lại rồi làm lại.'],
  DAY_NOT_READY: [409, 'Ngày này chưa ký được.'],
  REASON_REQUIRED: [422, 'Cần ghi lý do.'],
  INVALID_COMMAND: [422, 'Dữ liệu nhập không hợp lệ.'],
  INTERNAL: [500, 'Máy chủ lỗi tạm thời.'],
};
const vn = date => date.split('-').reverse().join('/');
function loi(code, extra = {}) {
  // DAY_SIGNED: câu của v7_api_tien._explain (nói rõ ngày cần mở lại).
  const [status, message] = code === 'DAY_SIGNED' ? [409, `Ngày ${vn(extra.detail)} đã ký số dư, mà thay đổi này làm đổi số dư của ngày đó. Mở lại ngày ${vn(extra.detail)} ở Đối soát ngày (các ngày đã ký sau đó mở lại theo) rồi làm lại.`]
    : MESSAGES[code];
  return Object.assign(new Error(message), { status, error: code, extra });
}

function world() {
  const tx = (id, date, direction, amount, description, extra = {}) => ({ id, booking_date: date, direction, amount_minor: String(amount),
    bank_ref: null, description, allocations: [], version: 0, voided: false, ...extra });
  return {
    roles: ['tien_nhap', 'tien_phan_bo', 'tien_review'], off: false, version: 3, seq: 100, keys: new Map(), posts: [], calls: [],
    failNext: 0, voidBlocked: false, errorLine: false, failDay: null, windowFrom: null, dataUntil: '2026-11-24',
    tx: [tx(41, '2026-11-20', 'in', 50000, 'CK GIA MOT', { bank_ref: 'FT1', version: 1,
      allocations: [{ id: 1, target_kind: 'customer_unapplied', target_ref: { customer_id: '12' }, amount_minor: '50000', note: null }] }),
    tx(42, '2026-11-21', 'out', 20000, 'CHI GIA HAI'), tx(43, '2026-11-21', 'in', 30000, 'CK GIA BA'),
    tx(44, '2026-11-21', 'in', 30000, 'CK GIA BA LAN HAI'), tx(45, '2026-11-22', 'out', 15000, 'CHI GIA BON')],
    // Giao dịch ở tài khoản khác cùng pháp nhân (chân kia của chuyển nội bộ).
    other: [{ id: 90, account_id: 8, direction: 'in', amount_minor: '20000' }],
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
}

const signed = (amount, direction) => (direction === 'in' ? BigInt(amount) : -BigInt(amount));
const live = w => w.tx.filter(t => !t.voided);
const ledger = (w, date) => (1000000n + live(w).filter(t => t.booking_date <= date).reduce((s, t) => s + signed(t.amount_minor, t.direction), 0n)).toString();
// tien._signed_from: ngày đã ký số dư sớm nhất từ `date` trở đi (null: không có).
const signedFrom = (w, date) => Object.keys(w.days).sort().find(d => d >= date && w.days[d].coverage_status === 'signed') ?? null;
const signedDays = (w, lines) => [...new Set(lines.filter(l => l.class === 'new' || l.class === 'suspect').map(l => signedFrom(w, l.booking_date)).filter(Boolean))].sort();
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
    // F = 1 dòng, E = 2 giao dịch cùng ngày/chiều/tiền (43, 44): _classify bước 4b cho dòng ứng viên mềm thứ nhất (43); 44 không là
    // ứng viên mềm của dòng nào nên thành gãy UNMATCHED_EXISTING (vẫn được chọn làm đích "trùng" vì cùng ngày/chiều/tiền).
    { seq: 3, line_no: 3, booking_date: '2026-11-21', direction: 'in', amount_minor: '30000', currency: 'VND', bank_ref: null, description: 'CK GIA BA FT9',
      class: 'suspect', code: null, candidate: 43, soft_candidates: [43] }];
  // Dòng lỗi: ô số tiền không đọc được, máy chủ trả nguyên văn.
  if (w.errorLine) lines.push({ seq: 4, line_no: 4, booking_date: '2026-11-23', direction: 'in', amount_minor: '70.000', currency: 'VND', bank_ref: null,
    description: 'CK GIA LOI', class: 'error', code: 'LINE_AMOUNT', candidate: null, soft_candidates: null });
  const counts = { rows: lines.length, new: 1, duplicate: 1, suspect: 1, error: w.errorLine ? 1 : 0 };
  const breaks = [{ code: 'UNMATCHED_EXISTING', transaction_id: 44, booking_date: '2026-11-21', direction: 'in', amount_minor: '30000' },
    { code: 'UNMATCHED_EXISTING', transaction_id: 45, booking_date: '2026-11-22', direction: 'out', amount_minor: '15000' }];
  const balance = { opening_minor: '1050000', expected_opening_minor: '1050000', closing_minor: '1105000', computed_closing_minor: '1105000', chain_breaks: 0, unmatched_existing: 2 };
  const file = { id: 4, byte_size: 200, media_type: 'text/csv', name: 'sao-ke-gia-2.csv' };
  w.view = { import: { id: 10, account_id: 7, status: 'validated', template: 'demo-csv@1', period_from: '2026-11-21', period_to: '2026-11-24',
    opening_minor: '1050000', closing_minor: '1105000', last_day_complete: false, counts_at_preview: counts,
    preview_account_version: w.version, reason: null, file, created: { actor: ACTOR, at: '2026-11-25T10:00:00+00:00' }, committed: null, closed: null },
  account_version: w.version, currency: 'VND', raw_visible: raw(w), roles: w.roles, stale: false, lines: raw(w) ? lines : lines.map(({ description: _hidden, ...l }) => l),
  preview_hash: HASH, counts, balance, breaks, signed_days: signedDays(w, lines) };
  w.imports.unshift({ id: 10, status: 'validated', template: 'demo-csv@1', period_from: '2026-11-21', period_to: '2026-11-24', last_day_complete: false,
    counts, reason: null, stale: false, file, created: { actor: ACTOR, at: '2026-11-25T10:00:00+00:00' }, committed: null, closed: null });
  return { import_id: 10, status: 'validated', template: 'demo-csv@1', preview_account_version: w.version, preview_hash: HASH, counts,
    balance, breaks, lines, file_id: 4, signed_days: signedDays(w, lines) };
}

function read(w, route, q) {
  if (route === '/api/v7/tien/me') {
    if (w.off) throw loi('TIEN_OFF');
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
      coverage: { data_until: w.dataUntil, data_until_state: 'partial', complete_until: '2026-11-23', missing_days: [], missing_count: 0,
        unsigned_full_days: unsigned, last_signed_day: '2026-11-20' } };
  }
  if (route === '/api/v7/tien/accounts/7/imports') return { account_id: 7, account_version: w.version, roles: w.roles, imports: w.imports };
  if (route === '/api/v7/tien/accounts/7/transactions') {
    const rows = w.tx.filter(t => t.booking_date >= q.get('from') && t.booking_date <= q.get('to')).map(t => txRow(w, t));
    return { account_id: 7, description_visible: raw(w), transactions: rows };
  }
  if (route === '/api/v7/tien/accounts/7/coverage') {
    // Cửa sổ ngày như get_coverage: [from, to], mặc định tới hôm nay; w.windowFrom thu hẹp cửa sổ mặc định để có nút "Ngày trước".
    const to = q.get('to') ?? TODAY;
    const from = q.get('from') ?? w.windowFrom ?? '2026-08-25';
    return { account_id: 7, from, to, today: TODAY, opening_as_of: '2026-11-20', days: Object.keys(w.days).filter(d => d >= from && d <= to).sort().reverse()
      .map(date => ({ date, coverage: w.days[date].coverage, coverage_status: w.days[date].coverage_status, business_status: w.days[date].business_status,
        transactions: live(w).filter(t => t.booking_date === date).length })) };
  }
  let m = /^\/api\/v7\/tien\/accounts\/7\/days\/(\d{4}-\d{2}-\d{2})$/.exec(route);
  if (m) {
    if (w.failDay === m[1]) { w.failDay = null; throw loi('INTERNAL'); }
    return day(w, m[1]);
  }
  // get_import phân loại lại lô chờ mỗi lần đọc (ngày đã ký tính lại theo lúc đọc).
  if (route === '/api/v7/tien/imports/10') return { ...w.view, signed_days: signedDays(w, w.view.lines) };
  m = /^\/api\/v7\/tien\/transactions\/(\d+)$/.exec(route);
  if (m) {
    const t = w.tx.find(x => x.id === Number(m[1]));
    return { transaction: txRow(w, t), description_visible: raw(w), roles: w.roles, coverage_status: 'unconfirmed',
      sources: [{ import_id: 9, role: 'origin', line_no: 1, import_status: 'committed', period_from: '2026-11-20', period_to: '2026-11-24' }],
      allocations: t.allocations, history: t.allocations.length ? [{ event_id: 5, before: [], after: t.allocations, reason: null, by: { actor: ACTOR, at: '2026-11-21T03:00:00+00:00' } }] : [] };
  }
  throw loi('NOT_FOUND');
}

// commit_import của lát 1, theo đúng thứ tự kiểm của hàm SQL.
function commitImport(w, b) {
  const v = w.view;
  const dec = b.suspect_decisions ?? [];
  const keep = b.keep_existing ?? [];
  if (!w.roles.includes(dec.length + keep.length > 0 ? 'tien_review' : 'tien_nhap')) throw loi('TIEN_FORBIDDEN');
  if (b.expected_preview_hash !== HASH || v?.import.status !== 'validated') throw loi('IMPORT_PREVIEW_STALE');
  if (v.counts.error > 0) throw loi('IMPORT_HAS_ERRORS');
  const decision = line => dec.find(d => d.line_no === line.line_no);
  if (v.lines.some(l => l.class === 'suspect' && !decision(l))) throw loi('IMPORT_SUSPECT_UNRESOLVED');
  const hard = new Set(v.lines.filter(l => l.class === 'duplicate').map(l => l.candidate));
  const targets = dec.filter(d => d.decision === 'duplicate_of').map(d => d.transaction_id);
  for (const d of dec.filter(x => x.decision === 'duplicate_of')) {
    const line = v.lines.find(l => l.line_no === d.line_no);
    const t = live(w).find(x => x.id === d.transaction_id);
    if (!t || t.booking_date !== line.booking_date || t.direction !== line.direction || t.amount_minor !== line.amount_minor || hard.has(t.id)
      || targets.filter(id => id === t.id).length > 1) throw loi('DUPLICATE_TARGET_INVALID');
  }
  // U tính từ kỳ của lô (giao dịch hiệu lực trong kỳ chưa là ứng viên trùng chắc), không từ breaks như so-tien-model.js.
  const pool = live(w).filter(t => t.booking_date >= v.import.period_from && t.booking_date <= v.import.period_to && !hard.has(t.id)).map(t => t.id);
  if (keep.some(k => !pool.includes(k.transaction_id) || targets.includes(k.transaction_id))
    || new Set(keep.map(k => k.transaction_id)).size !== keep.length) throw loi('INVALID_COMMAND');
  if (keep.some(k => !k.reason?.trim())) throw loi('REASON_REQUIRED');
  if (pool.some(id => !targets.includes(id) && !keep.some(k => k.transaction_id === id))) throw loi('BALANCE_CHAIN_BROKEN', { detail: 'UNMATCHED_EXISTING' });
  const create = v.lines.filter(l => l.class === 'new' || (l.class === 'suspect' && decision(l).decision === 'new'));
  const blocked = create.map(l => signedFrom(w, l.booking_date)).filter(Boolean).sort()[0];
  if (blocked) throw loi('DAY_SIGNED', { detail: blocked });
  const ids = create.map(l => {
    w.tx.push({ id: ++w.seq, booking_date: l.booking_date, direction: l.direction, amount_minor: l.amount_minor, bank_ref: l.bank_ref,
      description: l.description, allocations: [], version: 0, voided: false });
    return w.seq;
  });
  v.import.status = 'committed';
  w.imports[0] = { ...w.imports[0], status: 'committed', committed: { actor: ACTOR, at: '2026-11-25T10:05:00+00:00' } };
  w.version += 1;
  return { import_id: 10, status: 'committed', account_version: w.version, created: ids.length, confirmed: v.lines.length - ids.length,
    kept: keep.length, transaction_ids: ids };
}

// set_allocation của lát 1: mã đích là chuỗi số; chân kia của chuyển nội bộ ở tài khoản khác, ngược chiều; bộ y hệt thì không đổi;
// bỏ hay đổi dòng đang hiệu lực mới cần lý do.
function setAllocation(w, b) {
  const t = w.tx.find(x => x.id === b.transaction_id);
  if (t.version !== b.expected_version) throw loi('STALE_VERSION');
  const id = value => typeof value === 'string' && /^[1-9]\d{0,17}$/.test(value);
  let total = 0n;
  const lines = b.lines.map(l => {
    if (['ar_book', 'customer_unapplied'].includes(l.target_kind) && !id(l.target_ref.customer_id)) throw loi('INVALID_COMMAND');
    if (l.target_kind === 'internal_transfer') {
      const other = id(l.target_ref.transaction_id) && w.other.find(o => String(o.id) === l.target_ref.transaction_id);
      if (!other || other.direction === t.direction) throw loi('INVALID_COMMAND');
    }
    total += BigInt(l.amount_minor);
    if (total > BigInt(t.amount_minor)) throw loi('OVER_ALLOCATION');
    return { target_kind: l.target_kind, target_ref: l.target_ref, amount_minor: l.amount_minor, note: l.note ?? null };
  });
  const key = l => JSON.stringify([l.target_kind, l.target_ref, l.amount_minor, l.note ?? null]);
  const left = lines.map(key);
  if (JSON.stringify(t.allocations.map(key).sort()) === JSON.stringify([...left].sort())) return { transaction_id: t.id, version: t.version, ...state(t), unchanged: true };
  const removed = t.allocations.some(a => {
    const at = left.indexOf(key(a));
    if (at < 0) return true;
    left.splice(at, 1);
    return false;
  });
  if (removed && !b.reason) throw loi('REASON_REQUIRED');
  t.allocations = lines.map(l => ({ id: ++w.seq, ...l }));
  t.version += 1;
  return { transaction_id: t.id, version: t.version, ...state(t), unchanged: false };
}

function write(w, route, b) {
  const need = role => { if (!w.roles.includes(role)) throw loi('TIEN_FORBIDDEN'); };
  if (route === '/api/v7/tien/imports/preview') { need('tien_nhap'); return preview(w); }
  if (route === '/api/v7/tien/imports/commit') return commitImport(w, b);
  if (route === '/api/v7/tien/imports/reject') {
    need('tien_nhap');
    if (!b.reason) throw loi('REASON_REQUIRED');
    w.view.import.status = 'rejected';
    w.imports[0] = { ...w.imports[0], status: 'rejected', reason: b.reason, closed: { actor: ACTOR, at: '2026-11-25T10:06:00+00:00' } };
    return { import_id: b.import_id, status: 'rejected' };
  }
  if (route === '/api/v7/tien/imports/void') {
    need('tien_review');
    if (w.voidBlocked) throw loi('VOID_WOULD_LOSE_ALLOCATED');
    const imp = w.imports.find(i => i.id === b.import_id);
    imp.status = 'voided';
    imp.reason = b.reason;
    w.version += 1;
    return { import_id: b.import_id, status: 'voided', account_version: w.version, voided_transactions: [42], kept_transactions: [] };
  }
  if (route === '/api/v7/tien/allocations') { need('tien_phan_bo'); return setAllocation(w, b); }
  if (route === '/api/v7/tien/balance-evidence') {
    need('tien_review');
    if (!b.note) throw loi('REASON_REQUIRED');
    const d = w.days[b.as_of_date];
    d.evidence.push({ source: b.source, evidence_id: ++w.seq, amount_minor: b.amount_minor, note: b.note, role_overlap: false, actor: ACTOR, at: '2026-11-25T10:10:00+00:00', current: true });
    d.reasons = d.reasons.filter(r => r !== 'NO_EVIDENCE');
    return { evidence_id: w.seq, account_id: 7, as_of_date: b.as_of_date, role_overlap: false };
  }
  const history = (date, track, action, note = null) => w.days[date].history.unshift({ id: ++w.seq, track, action, role_overlap: false, note,
    snapshot: { not_fully_allocated: day(w, date).business.not_fully_allocated }, by: { actor: ACTOR, at: '2026-11-25T10:20:00+00:00' } });
  const d = w.days[b.business_date];
  if (route === '/api/v7/tien/days/sign-coverage') {
    need('tien_review');
    if (b.expected_version !== w.version) throw loi('STALE_VERSION');
    const now = day(w, b.business_date);
    if (!now.ready) throw loi('DAY_NOT_READY', { detail: now.reasons.join(',') });
    d.coverage_status = 'signed';
    history(b.business_date, 'coverage', 'sign');
    return { account_id: 7, business_date: b.business_date, coverage_status: 'signed', changed: true, role_overlap: false };
  }
  if (route === '/api/v7/tien/days/sign-business') {
    need('tien_review');
    if (d.coverage_status !== 'signed') throw loi('DAY_NOT_READY', { detail: 'COVERAGE_NOT_SIGNED' });
    d.business_status = 'signed';
    history(b.business_date, 'business', 'sign');
    return { account_id: 7, business_date: b.business_date, business_status: 'signed', changed: true, role_overlap: false,
      not_fully_allocated: day(w, b.business_date).business.not_fully_allocated };
  }
  if (route === '/api/v7/tien/days/reopen') {
    need('tien_review');
    if (!b.reason) throw loi('REASON_REQUIRED');
    // reopen_day: mở lại số dư kéo theo mọi ngày sau đang ký số dư (kèm chữ ký đối soát của chúng); mở lại đối soát chỉ ngày đó.
    const days = b.track === 'coverage' ? Object.keys(w.days).sort().filter(x => x >= b.business_date && w.days[x].coverage_status === 'signed') : [b.business_date];
    for (const x of days) {
      if (b.track === 'coverage') { w.days[x].coverage_status = 'reopened'; history(x, 'coverage', 'reopen', b.reason); }
      if (w.days[x].business_status === 'signed') { w.days[x].business_status = 'reopened'; history(x, 'business', 'reopen', b.reason); }
    }
    return { account_id: 7, business_date: b.business_date, coverage_status: d.coverage_status, business_status: d.business_status, reopened_days: days };
  }
  throw loi('NOT_FOUND');
}

function makeServer(w) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x');
    const route = url.pathname;
    const send = (status, headers, body) => { response.writeHead(status, headers); response.end(body); };
    const out = (body, status = 200) => send(status, { 'Content-Type': 'application/json' }, JSON.stringify(body));
    const fail = e => (e.error ? out({ error: e.error, message: e.message, ...e.extra }, e.status) : out({ error: 'TEST_BUG', message: e.message }, 500));
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
        try { return out(read(w, route, url.searchParams)); } catch (e) { return fail(e); }
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
        } catch (e) { return fail(e); }
      });
      return undefined;
    }
    if (route === '/api/v7/customers') {
      return out({ customers: [{ id: 13, name: 'Khách Giả Hai', status: 'active' }, { id: 12, name: 'Khách Giả Một', status: 'active' }, { id: 14, name: 'Khách Giả Cũ', status: 'closed' }] });
    }
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
    assert.deepEqual(w.posts.filter(p => p.route === 'TEST_BUG'), []);
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
const upload = async page => {
  await page.locator('input[data-act="upload"]').setInputFiles({ name: 'sao-ke-gia-2.csv', mimeType: 'text/csv', buffer: CSV });
  await page.locator('#st-review').waitFor();
};

test('Sổ tiền: thẻ số dư tới ngày nào, lô đã nhập, giao dịch tháng, mở chi tiết giao dịch', () => withPage('so-tien.html', async (page, w) => {
  await shot(page, '1-so-tien');
  assert.equal(await page.locator('#st-balance').innerText(), '1.075.000 đ');
  const card = page.locator('.st-hero');
  assert.match(await card.innerText(), /Dữ liệu tới ngày 24\/11\/2026; ngày này chưa trọn[\s\S]*Không có ngày trống giữa các lần nhập[\s\S]*3 ngày đủ sao kê chưa ký số dư/);
  assert.doesNotMatch(await card.innerText(), /Chưa có sao kê từ/, 'dữ liệu tới hôm qua là bình thường, không nhắc');
  assert.ok((await card.boundingBox()).y + (await card.boundingBox()).height < 560, 'thẻ số dư nằm trong phần màn thấy được 1280×560');
  assert.match(await page.locator('#st-account').innerText(), /NHGIA ••••1234 · VND/);
  assert.notEqual(await page.locator('.st-account').evaluate(el => getComputedStyle(el).color), 'rgb(255, 255, 255)',
    'nhãn tài khoản phải đọc được trên thanh đầu trang nền trắng');
  assert.match(await page.locator('table').nth(0).innerText(), /20\/11\/2026 – 24\/11\/2026\s+Đã ghi\s+5 dòng · 5 mới/);
  const rows = page.locator('tr.st-row');
  assert.equal(await rows.count(), 5);
  assert.match(await rows.nth(1).innerText(), /21\/11\/2026\s+20\.000 đ\s+CHI GIA HAI\s+Chưa ghép\s+20\.000 đ/);
  await rows.nth(1).click();
  const detail = page.locator('tr.st-detail');
  await detail.waitFor();
  assert.match(await detail.innerText(), /Mã giao dịch trong sổ tiền: #42[\s\S]*Nguồn[\s\S]*dòng 1[\s\S]*Chưa phân bổ\.[\s\S]*Phân bổ ở Đối soát ngày 21\/11\/2026/);
  assert.equal(await detail.locator('a').getAttribute('href'), '/doi-soat-ngay.html?account=7&date=2026-11-21');
  await rows.nth(0).click();
  await page.locator('tr.st-row[data-tx="41"][aria-expanded="true"]').waitFor();
  assert.match(await detail.innerText(), /Tiền khách, chưa rõ khoản \(sổ khách #12\): 50\.000 đ/, 'đích hiện bằng chữ, không phải mã trơn');
  await page.locator('select[data-act="status"]').selectOption('unidentified');
  assert.equal(await rows.count(), 2, 'lọc theo trạng thái');
  const download = page.waitForEvent('download');
  await page.locator('[data-act="export"]').click();
  assert.equal((await download).suggestedFilename(), 'so-tien-NHGIA-1234.xlsx');
  assert.ok(w.calls.includes('GET /api/v7/tien/accounts/7/export.xlsx?from=2026-11-01&to=2026-11-25'));
}));

test('Nhập sao kê: xem trước, quyết dòng nghi trùng, giữ mọi giao dịch cũ file chưa nhận (lý do), ghi vào sổ một lần', () => withPage('so-tien.html', async (page, w) => {
  await upload(page);
  const review = page.locator('#st-review');
  await shot(page, '2-xem-truoc');
  assert.deepEqual(posts(w, '/imports/preview').map(p => ({ ...p.body, idempotency_key: '?' })), [{ idempotency_key: '?', account_id: 7,
    template: 'demo-csv@1', file_name: 'sao-ke-gia-2.csv', content_base64: CSV.toString('base64') }]);
  assert.match(await review.innerText(), /3 dòng: 1 mới · 1 đã có trong sổ · 1 cần quyết · 0 lỗi[\s\S]*Số dư đầu, cuối của file liền với sổ\./);
  const asks = page.locator('.st-q');
  // Ứng viên của dòng 3: ứng viên mềm (43) và giao dịch file chưa nhận cùng ngày/chiều/tiền (44). 44 chưa hỏi lý do giữ khi dòng 3
  // chưa quyết (có thể là đích "trùng").
  assert.equal(await asks.count(), 2);
  assert.match(await asks.nth(0).innerText(), /Dòng 3 · 21\/11\/2026 · Thu 30\.000 đ · CK GIA BA FT9[\s\S]*Đây là giao dịch mới[\s\S]*Trùng giao dịch đã có: 21\/11\/2026 · Thu 30\.000 đ · CK GIA BA[\s\S]*CK GIA BA LAN HAI/);
  assert.match(await asks.nth(1).innerText(), /Giao dịch đã có trong sổ: 22\/11\/2026 · Chi 15\.000 đ · CHI GIA BON[\s\S]*File mới không có/);
  // Bảng đủ dòng chỉ dựng khi mở, và còn mở sau khi vẽ lại.
  assert.equal(await page.locator('#st-all table').count(), 0);
  await page.locator('#st-all summary').click();
  await page.locator('#st-all table').waitFor();
  assert.equal(await page.locator('#st-all tbody tr').count(), 3);
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Dòng 3: chọn giao dịch mới hay trùng.');
  assert.equal(posts(w, '/imports/commit').length, 0, 'thiếu quyết định thì không gửi');
  await asks.nth(0).locator('input[value="43"]').check();
  await page.locator('textarea[data-keep="44"]').waitFor();
  assert.ok(await page.locator('#st-all').evaluate(el => el.open), 'bảng đủ dòng vẫn mở sau khi vẽ lại');
  assert.match(await review.innerText(), /CK GIA BA\s*Đã ghép với dòng 3 của file\./);
  await page.locator('textarea[data-keep="45"]').fill('Ngân hàng chưa trả giao dịch này, giữ để đối chiếu');
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Giao dịch đã có ngày 21/11/2026, 30.000 đ chưa được file nhận: ghi lý do giữ.');
  assert.equal(posts(w, '/imports/commit').length, 0);
  await page.locator('textarea[data-keep="44"]').fill('Hai lần chuyển cùng số tiền\ntrong ngày, file mới chỉ có một');
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Đã ghi vào sổ: 1 giao dịch mới, 2 dòng đã có, giữ 2 giao dịch cũ.');
  const [sent] = posts(w, '/imports/commit');
  assert.deepEqual({ ...sent.body, idempotency_key: '?' }, { idempotency_key: '?', import_id: 10, expected_preview_hash: HASH,
    suspect_decisions: [{ line_no: 3, decision: 'duplicate_of', transaction_id: 43 }],
    keep_existing: [{ transaction_id: 44, reason: 'Hai lần chuyển cùng số tiền trong ngày, file mới chỉ có một' },
      { transaction_id: 45, reason: 'Ngân hàng chưa trả giao dịch này, giữ để đối chiếu' }] });
  assert.equal(await review.count(), 0, 'ghi xong thì đóng hộp xem trước');
  assert.equal(await page.locator('#st-balance').innerText(), '1.145.000 đ', 'thẻ đọc lại số dư mới');
}));

test('Lô có ngày đã ký số dư: chỉ cảnh báo; chọn "mới" thì máy chủ chặn và nói ngày cần mở lại; chọn "trùng" thì ghi được', () => withPage('so-tien.html', async (page, w) => {
  await upload(page);
  await page.locator('.st-warn').scrollIntoViewIfNeeded();
  await shot(page, '6-ngay-da-ky');
  assert.match(await page.locator('.st-warn').innerText(), /Ngày 21\/11\/2026 đã ký số dư[\s\S]*mở lại ngày 21\/11\/2026 ở Đối soát ngày/);
  assert.equal(await page.locator('.st-block').count(), 0, 'ngày đã ký không phải chỗ chặn');
  await page.locator('.st-q').nth(0).locator('input[value="new"]').check();
  for (const id of [43, 44, 45]) await page.locator(`textarea[data-keep="${id}"]`).fill(`Giữ giao dịch giả ${id}`);
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Ngày 21/11/2026 đã ký số dư, mà thay đổi này làm đổi số dư của ngày đó. Mở lại ngày 21/11/2026 ở Đối soát ngày');
  assert.ok(await page.locator('.st-q').nth(0).locator('input[value="new"]').isChecked(), 'quyết định còn nguyên sau khi bị chặn');
  await page.locator('.st-q').nth(0).locator('input[value="43"]').check();
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Đã ghi vào sổ: 1 giao dịch mới, 2 dòng đã có, giữ 2 giao dịch cũ.');
  assert.deepEqual(posts(w, '/imports/commit').map(p => p.body.keep_existing.map(k => k.transaction_id)), [[44, 45, 43], [44, 45]]);
}, { setup: w => { w.days['2026-11-21'].coverage_status = 'signed'; } }));

test('Dòng lỗi: số tiền sai dạng hiện nguyên văn, lô bị chặn ghi', () => withPage('so-tien.html', async page => {
  await upload(page);
  const block = page.locator('.st-block');
  assert.match(await block.innerText(), /Lô có 1 dòng lỗi[\s\S]*Dòng 4 · 23\/11\/2026 · Thu 70\.000 · CK GIA LOI: Số tiền không đọc được/);
  assert.ok(await page.locator('[data-act="commit"]').isDisabled());
}, { setup: w => { w.errorLine = true; } }));

test('Vai: chỉ có vai nhập thì không quyết được nghi trùng; chỉ có vai xem thì không thấy khối nhập, file gốc, xuất Excel', async () => {
  await withPage('so-tien.html', async page => {
    await page.locator('[data-act="open-import"]').first().click();
    await page.locator('#st-review').waitFor();
    assert.ok(await page.locator('.st-q input[type="radio"]').first().isDisabled());
    assert.ok(await page.locator('[data-act="commit"]').isDisabled());
    assert.match(await page.locator('.st-ro').innerText(), /Lô có 1 dòng nghi trùng và 3 giao dịch đã có cần xác nhận: người có vai đối chiếu mở lô này/);
  }, { setup: w => { w.roles = ['tien_nhap']; preview(w); } });
  await withPage('so-tien.html', async page => {
    assert.equal(await page.locator('#st-import-title').count(), 0);
    assert.equal(await page.locator('[data-act="download-file"]').count(), 0);
    assert.equal(await page.locator('[data-act="open-import"]').count(), 0, 'người xem không mở được lô chờ');
    assert.equal(await page.locator('[data-act="export"]').count(), 0);
    assert.equal(await page.locator('th', { hasText: 'Nội dung' }).count(), 0, 'người xem không thấy nội dung chuyển khoản');
    assert.match(await page.locator('.st-hero').innerText(), /Chưa có sao kê từ ngày 21\/11\/2026 \(5 ngày\)/, 'dữ liệu cũ thì nhắc, không gọi là đủ');
  }, { setup: w => { w.roles = ['tien_xem']; w.dataUntil = '2026-11-20'; preview(w); } });
});

test('Bỏ lô và hủy lô cần lý do; mất mạng khi ghi thì giữ quyết định, bấm lại dùng đúng mã yêu cầu', () => withPage('so-tien.html', async (page, w) => {
  await page.locator('[data-act="void"]').click();
  const dialog = page.locator('#st-reason');
  await dialog.waitFor();
  await page.locator('#st-reason-ok').click();
  assert.ok(await dialog.isVisible(), 'chưa ghi lý do thì hộp không đóng');
  await page.locator('#st-reason-input').fill('Nhập nhầm file\ncủa   tài khoản khác ');
  await page.locator('#st-reason-ok').click();
  await toast(page, 'Lô có giao dịch đang phân bổ');
  assert.deepEqual(posts(w, '/imports/void').map(p => p.body.reason), ['Nhập nhầm file của tài khoản khác'], 'xuống dòng, khoảng trắng thừa gộp lại');
  w.voidBlocked = false;
  await upload(page);
  await page.locator('.st-q').nth(0).locator('input[value="new"]').check();
  // Chọn "mới" thì ứng viên mềm 43 cũng là giao dịch cũ file chưa nhận: phải giữ có lý do như 44, 45.
  for (const id of [44, 45, 43]) await page.locator(`textarea[data-keep="${id}"]`).fill(`Giữ giao dịch giả ${id}`);
  // Máy chủ đã ghi nhưng trả lời mất trên đường (route.fetch rồi abort): trang báo mất kết nối, bấm lại phải dùng đúng mã yêu cầu để
  // máy chủ trả kết quả cũ thay vì ghi lần hai. (Hủy socket ở máy chủ giả thì Chrome tự gửi lại lệnh, không thấy lỗi.)
  await page.route('**/api/v7/tien/imports/commit', async route => { await route.fetch(); await route.abort('failed'); }, { times: 1 });
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Mất kết nối');
  assert.ok(await page.locator('.st-q').nth(0).locator('input[value="new"]').isChecked(), 'quyết định còn nguyên sau khi mất mạng');
  assert.equal(await page.locator('textarea[data-keep="43"]').inputValue(), 'Giữ giao dịch giả 43');
  const before = w.tx.length;
  await page.locator('[data-act="commit"]').click();
  await toast(page, 'Đã ghi vào sổ: 2 giao dịch mới, 1 dòng đã có, giữ 3 giao dịch cũ.');
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
  assert.match(await page.locator('section[aria-labelledby="st-tx-title"]').innerText(), /Chi #42[\s\S]*Thu #43/, 'mã giao dịch hiện trong bảng (ghép chuyển nội bộ)');
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
  // "Thôi" đóng ô nhập và bỏ số đang gõ.
  await page.locator('[data-act="ev-open"]').click();
  await page.locator('input[data-ev="amount"]').fill('9.999');
  await page.locator('[data-act="ev-cancel"]').click();
  assert.equal(await page.locator('input[data-ev="amount"]').count(), 0);
  await page.locator('[data-act="ev-open"]').click();
  assert.equal(await page.locator('input[data-ev="amount"]').inputValue(), '');
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

test('Mở lại số dư một ngày kéo theo các ngày sau đang ký; câu báo nêu đủ các ngày', () => withPage('doi-soat-ngay.html', async (page, w) => {
  for (const date of ['2026-11-21', '2026-11-22']) {
    await page.locator(`.st-days button[data-date="${date}"]`).click();
    await page.locator(`.st-days button[data-date="${date}"][aria-current="true"]`).waitFor();
    await page.locator('[data-act="sign-coverage"]').click();
    await toast(page, `Đã ký số dư ngày ${vn(date)}`);
  }
  await page.locator('.st-days button[data-date="2026-11-21"]').click();
  await page.locator('.st-days button[data-date="2026-11-21"][aria-current="true"]').waitFor();
  await page.locator('[data-act="reopen"][data-track="coverage"]').click();
  assert.match(await page.locator('#st-reason-text').innerText(), /mọi ngày sau đang ký/);
  await page.locator('#st-reason-input').fill('Nhập bù giao dịch muộn');
  await page.locator('#st-reason-ok').click();
  await toast(page, 'Đã mở lại 2 ngày: 21/11, 22/11.');
  assert.deepEqual(posts(w, '/days/reopen').map(p => [p.body.business_date, p.body.track, p.body.reason]),
    [['2026-11-21', 'coverage', 'Nhập bù giao dịch muộn']], 'một lệnh cho ngày được chọn; máy chủ kéo theo ngày sau');
  assert.match(await page.locator('.st-days button[data-date="2026-11-22"]').innerText(), /Số dư: Mở lại/);
  assert.match(await page.locator('.st-days button[data-date="2026-11-20"]').innerText(), /Số dư: Đã ký/, 'ngày trước đó giữ chữ ký');
}));

test('Đối soát ngày: đọc ngày lỗi thì báo, không để số của ngày cũ dưới nhãn ngày mới; cột ngày xem được ngày cũ hơn', () => withPage('doi-soat-ngay.html', async (page, w) => {
  assert.deepEqual(await page.locator('.st-days button[data-act="day"]').evaluateAll(els => els.map(el => el.dataset.date)), ['2026-11-25', '2026-11-24', '2026-11-23']);
  assert.match(await page.locator('.st-days button[aria-current="true"]').innerText(), /23\/11/, 'ngày cũ nhất còn việc trong cửa sổ');
  assert.match(await page.locator('.st-days button[data-date="2026-11-25"]').innerText(), /Số dư: Chưa tải sao kê/, 'hôm nay chưa có sao kê không tô đỏ');
  w.failDay = '2026-11-24';
  await page.locator('.st-days button[data-date="2026-11-24"]').click();
  await page.locator('#error:not([hidden])').waitFor();
  assert.equal(await page.locator('#error').innerText(), 'Máy chủ lỗi tạm thời.');
  assert.equal(await page.locator('section[aria-labelledby="st-bal-title"]').count(), 0, 'không hiện số dư ngày 23 dưới nhãn ngày 24');
  await page.locator('.st-days button[data-date="2026-11-24"]').click();
  await page.locator('section[aria-labelledby="st-bal-title"]').waitFor();
  assert.match(await page.locator('#st-bal-title').innerText(), /Thứ Ba 24\/11\/2026/);
  assert.ok(await page.locator('#error').isHidden());
  await page.locator('[data-act="days-older"]').click();
  await page.locator('[data-act="days-newest"]').waitFor();
  assert.ok(w.calls.includes('GET /api/v7/tien/accounts/7/coverage?from=2026-08-22&to=2026-11-22'));
  assert.deepEqual(await page.locator('.st-days button[data-act="day"]').evaluateAll(els => els.map(el => el.dataset.date)), ['2026-11-22', '2026-11-21', '2026-11-20']);
  assert.equal(await page.locator('[data-act="days-older"]').count(), 0, 'đã tới ngày số dư mở');
  await page.locator('[data-act="days-newest"]').click();
  await page.locator('.st-days button[data-date="2026-11-25"]').waitFor();
}, { setup: w => { w.windowFrom = '2026-11-23'; } }));

test('Phân bổ: chọn sổ khách, chia dòng, còn lại tính sẵn, vượt số tiền thì báo, đổi dòng cũ cần lý do', () => withPage('doi-soat-ngay.html', async (page, w) => {
  await page.locator('[data-act="alloc"][data-id="43"]').click();
  const dialog = page.locator('#st-alloc');
  await dialog.waitFor();
  assert.match(await dialog.innerText(), /21\/11\/2026 · Thu 30\.000 đ · CK GIA BA[\s\S]*Còn lại chưa phân bổ: 0 đ/);
  assert.deepEqual(await dialog.locator('select[data-field="ref"] option').allInnerTexts(), ['Chọn sổ khách', 'Khách Giả Hai', 'Khách Giả Một'],
    'chỉ sổ khách đang dùng, xếp theo tên');
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
  await dialog.locator('input[data-alloc-reason]').fill(' Lãi\tghi  nhầm ');
  await dialog.locator('[data-act="alloc-save"]').click();
  await toast(page, 'Đã lưu phân bổ.');
  assert.deepEqual(posts(w, '/allocations')[1].body.reason, 'Lãi ghi nhầm');
  assert.equal(posts(w, '/allocations')[1].body.expected_version, 1);
}));

test('Phân bổ chuyển nội bộ: mã chân kia gửi dạng chuỗi số; máy chủ từ chối thì lỗi hiện ngay trong hộp', () => withPage('doi-soat-ngay.html', async (page, w) => {
  await page.locator('[data-act="alloc"][data-id="42"]').click();
  const dialog = page.locator('#st-alloc');
  await dialog.waitFor();
  await dialog.locator('select[data-field="kind"]').selectOption('internal_transfer');
  await dialog.locator('input[data-field="ref"]').fill('41');
  await dialog.locator('[data-act="alloc-save"]').click();
  await dialog.locator('[role="alert"]').filter({ hasText: 'Dữ liệu nhập không hợp lệ.' }).waitFor();
  assert.ok(await dialog.isVisible(), 'lỗi máy chủ không đóng hộp, dòng đang sửa còn nguyên');
  assert.equal(await dialog.locator('input[data-field="ref"]').inputValue(), '41');
  await dialog.locator('input[data-field="ref"]').fill('90');
  await dialog.locator('[data-act="alloc-save"]').click();
  await toast(page, 'Đã lưu phân bổ. Còn lại chưa phân bổ: 0 đ.');
  assert.deepEqual(posts(w, '/allocations').map(p => p.body.lines), [
    [{ target_kind: 'internal_transfer', target_ref: { transaction_id: '41' }, amount_minor: '20000' }],
    [{ target_kind: 'internal_transfer', target_ref: { transaction_id: '90' }, amount_minor: '20000' }]]);
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
