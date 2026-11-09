/* Máy chủ giả và trình duyệt dùng chung cho test-so-khach-v7-*-browser.js (sửa tại ô, đối chiếu Sheet).
 * Tách từ test-so-khach-v7-edit-browser.js (29/10/2026). Dữ liệu giả, không chạm DB hay Sheet. */
const assert = require('node:assert/strict');
const http = require('node:http');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared } = require('./shared-browser.js');

const shots = process.env.SHOTS_DIR;
const clock = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const todayMonth = `${clock.slice(0, 7)}-01`;
const monthOf = iso => `${iso.slice(0, 7)}-01`;

// Danh mục phụ phí giả (PHU-PHI-01): như danh mục khởi tạo, id cố định để test chọn được.
const feeCatalog = () => [
  { id: 1, name: 'Neo', kind: 'service', sign: 'positive', system_key: null, active: true, sort: 1 },
  { id: 2, name: 'Điện', kind: 'service', sign: 'positive', system_key: null, active: true, sort: 2 },
  { id: 3, name: 'Ghép', kind: 'service', sign: 'positive', system_key: null, active: true, sort: 3 },
  { id: 4, name: 'Bảo hiểm', kind: 'service', sign: 'positive', system_key: null, active: true, sort: 4 },
  { id: 7, name: 'Khác', kind: 'service', sign: 'positive', system_key: 'other', active: true, sort: 100 },
  { id: 8, name: 'Giảm trừ', kind: 'service', sign: 'negative', system_key: 'discount', active: true, sort: 101 },
  { id: 9, name: 'Phụ phí ban đầu', kind: 'service', sign: 'any', system_key: 'initial', active: true, sort: 102 },
];

// Sổ giả: chuyến web và dòng sổ gốc tháng 9 đang mở; mỗi test có thể khóa riêng.
function makeWorld() {
  return {
    feeTypes: feeCatalog(), feeColumns: [], nextFeeLine: 600, catalogRequests: [],
    version: 1, reads: 0, refreshCalls: [], sheetRefresh: null, sheetSync: { snapshot_sha256: 'a'.repeat(64), new_count: 0, conflict_count: 0, items: [] }, receipts: [], images: [], otherImages: [], requests: [], failNext: null, locks: [{ month: '2026-09-01', locked: false }], nextEvent: 1, events: [], adjustments: [],
    trips: [{ id: 11, month: '2026-09-01', container: 'DEMU1234567', carrier: 'Tàu thử', event_date: '2026-09-15', origin: 'Nơi A', destination: 'Nơi B',
      unit_price_vnd: '50000000', other_fee_vnd: null, amount_vnd: '50000000', status: 'confirmed', is_missing_price: false, is_fee_only: false,
      editable: true, info_editable: true, deleted: false }],
    legacy: [
      { id: 21, month: '2026-09-01', kind: 'trip', source_total_vnd: null, editable: true,
        display: { row: 5, stt: '1', container: 'OLDU0000001', carrier: 'Xe 1', date: '2026-09-02', from: 'Nơi C', to: 'Nơi D', unit_price: '', fee_vnd: '', flags: ['MISSING_PRICE'] },
        current: { container: 'OLDU0000001', carrier: 'Xe 1', shipper: 'Chủ hàng thử', event_date: '2026-09-02', origin: 'Nơi C', destination: 'Nơi D', unit_price_vnd: null, other_fee_vnd: null, counted_vnd: '0', month: '2026-09-01', deleted: false } },
      { id: 22, month: '2026-09-01', kind: 'trip', source_total_vnd: '93000000', editable: true,
        fee_lines: [{ id: 501, fee_type_id: 9, amount_vnd: '3000000', note: null }],
        display: { row: 6, stt: '2', container: 'OLDU0000002', carrier: 'Xe 2', date: '2026-09-03', from: 'Nơi C', to: 'Nơi D', unit_price: '90000000', fee_vnd: '3000000', flags: [] },
        current: { container: 'OLDU0000002', carrier: 'Xe 2', event_date: '2026-09-03', origin: 'Nơi C', destination: 'Nơi D', unit_price_vnd: '90000000', other_fee_vnd: '3000000', counted_vnd: '93000000', month: '2026-09-01', deleted: false } },
    ],
  };
}

// months[] mặc định khớp các dòng như server: phát sinh = Thành tiền chuyến đã duyệt + dòng sổ gốc + điều chỉnh của tháng, đã thu
// = phiếu chưa hủy theo ngày thu; nợ đầu/cuối tháng cộng dồn từ tháng đầu (sổ giả không có số dư đầu). world.monthValues ghi đè.
function monthsOf(world, keys, trips, legacy) {
  const sum = values => values.reduce((total, value) => total + BigInt(value ?? 0), 0n);
  let prior = 0n;
  return keys.map(month => {
    const charges = sum([...trips.filter(trip => trip.month === month && trip.status === 'confirmed').map(trip => trip.amount_vnd),
      ...legacy.filter(row => (row.current?.month ?? row.month) === month && row.kind !== 'receipt').map(row => row.current?.counted_vnd ?? row.source_total_vnd),
      ...world.adjustments.filter(row => row.month === month).map(row => row.amount_vnd)]);
    const received = sum(world.receipts.filter(row => row.voided_by_event == null && `${row.date.slice(0, 7)}-01` === month).map(row => row.amount_vnd));
    const end = prior + charges - received;
    const row = { month, prior_months_vnd: String(prior), charges_vnd: String(charges), received_vnd: String(received),
      end_of_month_vnd: String(end), outstanding_vnd: '0', ...world.monthValues?.[month] };
    prior = end;
    return row;
  });
}

// world.todayMonth (tháng hiện tại của server), world.months (cả months[]), world.status và world.total (null khi chưa có số dư
// đầu) để test thẻ Tình hình dựng sổ nhiều tháng; mặc định như trước.
function ledger(world) {
  const trips = world.trips.filter(trip => !trip.deleted);
  const legacy = world.legacy.filter(row => !row.current?.deleted);
  const today = world.todayMonth ?? todayMonth;
  const keys = [...new Set([...trips, ...legacy].map(row => row.month).concat(today))].sort();
  const feeSum = lines => lines.reduce((sum, line) => sum + BigInt(line.amount_vnd), 0n);
  return { status: world.status ?? 'active', customer_id: 1, version: world.version, demo: true, today_month: today,
    fee_columns: world.feeColumns.map((id, index) => ({ fee_type_id: id, position: index + 1 })),
    month_locks: world.locks,
    months: world.months ?? monthsOf(world, keys, trips, legacy),
    total_outstanding_vnd: world.total === undefined ? '0' : world.total, trips: trips.map(trip => ({ ...trip, fee_lines: trip.fee_lines ?? [] })), adjustments: world.adjustments, opening: [], source_exceptions: [], receipts: world.receipts, outgoing_offsets: world.outgoing ?? [],
    legacy_rows: legacy.map(row => ({ ...row, month: row.current?.month ?? row.month, fee_lines: row.fee_lines ?? [],
      counted_differs: row.current?.unit_price_vnd != null && BigInt(row.current.counted_vnd) !== BigInt(row.current.unit_price_vnd) + feeSum(row.fee_lines ?? []) })), sheet_sync: world.sheetSync,
    sheet_prices: world.sheetPrices ?? { ready: [], review: [], ready_count: 0, review_count: 0 },
    sheet_receipts: world.sheetReceipts ?? { ready: [], review: [], ready_count: 0, review_count: 0 },
    ...(world.psFees ? { ps_fees: world.psFees } : {}), ...(world.details ? { sheet_details: world.details } : {}) };
}

// Lệnh phụ phí giả: một đích (chuyến web / dòng sổ gốc); tháng khóa và dòng sổ gốc chưa có đơn giá bị chặn như server.
function feeTarget(world, target) {
  if (target.trip_id != null) {
    const trip = world.trips.find(row => row.id === target.trip_id && !row.deleted);
    return { row: trip, month: trip.month, lines: (trip.fee_lines ??= []), legacy: false };
  }
  const row = world.legacy.find(item => item.id === target.legacy_row_id);
  return { row, month: row.current.month, lines: (row.fee_lines ??= []), legacy: true };
}
function syncFee(info) {
  const total = info.lines.length ? info.lines.reduce((sum, line) => sum + BigInt(line.amount_vnd), 0n) : null;
  if (info.legacy) {
    const cur = info.row.current;
    Object.assign(cur, { other_fee_vnd: total?.toString() ?? null, counted_vnd: String(BigInt(cur.unit_price_vnd) + (total ?? 0n)) });
  } else {
    const trip = info.row;
    trip.other_fee_vnd = total?.toString() ?? null;
    if (trip.unit_price_vnd != null) trip.amount_vnd = String(BigInt(trip.unit_price_vnd) + (total ?? 0n));
  }
}
function applyFee(world, url, body) {
  const locked = month => (world.locks.find(row => row.month === month)?.locked) ?? month !== todayMonth;
  const lineTarget = id => [...world.trips.map(row => ({ trip_id: row.id, lines: row.fee_lines ?? [] })),
    ...world.legacy.map(row => ({ legacy_row_id: row.id, lines: row.fee_lines ?? [] }))].find(item => item.lines.some(line => line.id === id));
  const targets = url.endsWith('/add') ? body.targets : url.endsWith('/set') ? [body.target]
    : (() => { const found = lineTarget(body.fee_line_id); return found ? [found.trip_id != null ? { trip_id: found.trip_id } : { legacy_row_id: found.legacy_row_id }] : []; })();
  if (!targets.length) return [409, { error: 'FEE_LINE_NOT_FOUND', message: 'Không tìm thấy khoản phụ phí. Tải lại sổ.' }];
  const infos = targets.map(target => feeTarget(world, target));
  if (infos.some(info => locked(info.month))) return [422, { error: 'MONTH_LOCKED', message: 'Tháng đã khóa — mở khóa tháng để sửa phụ phí.' }];
  if (infos.some(info => info.legacy && info.row.current.unit_price_vnd == null)) return [422, { error: 'LEGACY_NO_UNIT_PRICE', message: 'Dòng sổ gốc chưa có đơn giá.' }];
  const type = world.feeTypes.find(item => item.id === body.fee_type_id);
  if (!url.endsWith('/void') && body.amount_vnd != null && type && ((type.sign === 'positive' && body.amount_vnd.startsWith('-')) || (type.sign === 'negative' && !body.amount_vnd.startsWith('-')))) {
    return [422, { error: 'FEE_SIGN_INVALID', message: 'Dấu phụ phí không phù hợp với loại phí.' }];
  }
  const before = infos.map(info => ({ ...(info.legacy ? { legacy_row_id: info.row.id, counted_vnd: info.row.current.counted_vnd } : { trip_id: info.row.id }), fee_lines: info.lines.map(line => ({ ...line })) }));
  for (const info of infos) {
    if (url.endsWith('/set')) info.lines.splice(0, info.lines.length, ...info.lines.filter(line => line.fee_type_id !== body.fee_type_id));
    if (url.endsWith('/replace') || url.endsWith('/void')) info.lines.splice(info.lines.findIndex(line => line.id === body.fee_line_id), 1);
    if (!url.endsWith('/void') && body.amount_vnd != null) info.lines.push({ id: world.nextFeeLine++, fee_type_id: body.fee_type_id, amount_vnd: body.amount_vnd, note: body.note ?? null });
    syncFee(info);
  }
  const kind = { add: 'add_trip_fees', set: 'set_trip_fee_type', replace: 'replace_trip_fee', void: 'void_trip_fee' }[url.split('/').pop()];
  world.events.unshift({ kind, actor: 'nguoi-thu', at: '2026-10-01T03:00:00Z', before: { targets: before, batch_count: infos.length },
    after: { targets: infos.map(info => ({ ...(info.legacy ? { legacy_row_id: info.row.id, counted_vnd: info.row.current.counted_vnd } : { trip_id: info.row.id }), fee_lines: info.lines })), batch_count: infos.length } });
  world.version += 1;
  return [200, { ok: true }];
}

function apply(world, url, body) {
  const fail = world.failNext;
  if (fail) { world.failNext = null; return [422, fail]; }
  // Danh mục loại phụ phí: dùng chung mọi sổ, không version sổ.
  if (url === '/api/v7/fee-types' || url === '/api/v7/fee-types/update') {
    world.catalogRequests.push(body);
    if (url.endsWith('/update')) {
      const type = world.feeTypes.find(item => item.id === body.fee_type_id);
      if (body.command === 'rename_fee_type') type.name = body.name;
      if (body.command === 'set_fee_type_kind') type.kind = body.kind;
      if (body.command === 'set_fee_type_active') type.active = body.active;
    } else {
      if (world.feeTypes.some(item => item.name.toLowerCase() === body.name.toLowerCase())) return [409, { error: 'FEE_TYPE_DUPLICATE', message: 'Tên loại phụ phí đã tồn tại.' }];
      world.feeTypes.push({ id: 20 + world.feeTypes.length, name: body.name, kind: body.kind, sign: 'positive', system_key: null, active: true, sort: 50 });
    }
    return [200, { ok: true }];
  }
  if (body.expected_version !== world.version) return [409, { error: 'STALE_LEDGER' }];
  if (url.startsWith('/api/v7/trips/fees/')) return applyFee(world, url, body);
  if (url === '/api/v7/books/fee-columns') {
    if (body.fee_type_ids.length > 3) return [422, { error: 'FEE_COLUMNS_MAX', message: 'Sổ chỉ được chọn tối đa 3 cột phụ phí.' }];
    world.events.unshift({ kind: 'set_book_fee_columns', actor: 'nguoi-thu', at: '2026-10-01T03:00:00Z',
      before: { fee_columns: world.feeColumns.map((id, index) => ({ fee_type_id: id, position: index + 1 })) }, after: { fee_columns: body.fee_type_ids } });
    world.feeColumns = [...body.fee_type_ids];
    world.version += 1;
    return [200, { ok: true }];
  }
  if (url === '/api/v7/sheet/approve') {
    if (body.snapshot_sha256 !== world.sheetSync.snapshot_sha256) return [409, { error: 'STALE_SHEET' }];
    const row = world.sheetSync.items.find(item => item.sync_state === 'NEW');
    world.trips.push({ id: 200, month: monthOf(row.event_date), container: row.container, carrier: row.carrier,
      event_date: row.event_date, origin: row.origin, destination: row.destination, unit_price_vnd: null,
      other_fee_vnd: null, amount_vnd: null, note: 'Chuyến đồng bộ', status: 'confirmed', is_missing_price: true,
      is_fee_only: false, editable: true, info_editable: true, deleted: false });
    world.sheetSync = { ...world.sheetSync, items: [], new_count: 0, conflict_count: 0 };
    world.version += 1;
    return [200, { approved: 1, remaining: 0, complete: true }];
  }
  if (url === '/api/v7/sheet/prices') {
    if (world.priceStale || body.snapshot_sha256 !== world.sheetPrices.snapshot_sha256) return [409, { error: 'STALE_SHEET', message: 'Sheet đã đổi. Tải lại rồi ghi.' }];
    const written = world.sheetPrices.ready.length;
    for (const item of world.sheetPrices.ready) {
      const row = item.target_kind === 'trip' ? world.trips.find(trip => trip.id === item.target_id)
        : world.legacy.find(line => line.id === item.target_id).current;
      Object.assign(row, { unit_price_vnd: item.sheet_unit_price_vnd, other_fee_vnd: item.sheet_other_fee_vnd, is_missing_price: false });
    }
    world.sheetPrices = { ...world.sheetPrices, ready: [], ready_count: 0 };
    world.version += 1;
    return [200, { written, remaining: 0, complete: true, version: world.version }];
  }
  if (url === '/api/v7/sheet/prices/conflicts') {
    if (world.priceConflictStale || body.snapshot_sha256 !== world.sheetPrices.snapshot_sha256)
      return [409, { error: 'STALE_SHEET', message: 'Sheet đã đổi.' }];
    const selected = body.conflicts.map(key => world.sheetPrices.review.find(item => item.status === 'CONFLICT' && item.batchable &&
      item.target_kind === key.target_kind && item.target_id === key.target_id && item.source_row === key.source_row));
    if (selected.some(item => !item)) return [409, { error: 'STALE_SHEET', message: 'Dòng giá đã đổi.' }];
    for (const item of selected) {
      const row = item.target_kind === 'trip' ? world.trips.find(trip => trip.id === item.target_id)
        : world.legacy.find(line => line.id === item.target_id).current;
      const fee = BigInt(item.sheet_other_fee_vnd ?? '0');
      Object.assign(row, { unit_price_vnd: item.sheet_unit_price_vnd, other_fee_vnd: item.sheet_other_fee_vnd,
        counted_vnd: item.target_kind === 'legacy' ? String(BigInt(item.sheet_unit_price_vnd) + fee) : row.counted_vnd,
        amount_vnd: item.target_kind === 'trip' ? String(BigInt(item.sheet_unit_price_vnd) + fee) : row.amount_vnd });
      world.sheetPrices.review.splice(world.sheetPrices.review.indexOf(item), 1);
      world.version += 1;
    }
    world.sheetPrices.review_count = world.sheetPrices.review.length;
    return [200, { written: selected.length, remaining: 0, complete: true, version: world.version }];
  }
  // THU-SHEET-01: mỗi phiếu READY thành một phiếu thu web, như record_receipt.
  if (url === '/api/v7/sheet/receipts') {
    if (world.receiptStale || body.snapshot_sha256 !== world.sheetReceipts.snapshot_sha256) return [409, { error: 'STALE_SHEET', message: 'Sheet đã đổi. Tải lại rồi ghi.' }];
    for (const item of world.sheetReceipts.ready) {
      const pid = `PH-${String(world.receipts.length + 1).padStart(3, '0')}`;
      world.receipts.push({ id: world.receipts.length + 1, pid, date: item.date, method: 'THU TIỀN', amount_vnd: item.amount_vnd,
        reference: `Sheet: ${item.note}`, voided_by_event: null, void_reason: null,
        allocations: [{ id: 1, month: monthOf(item.date), kind: 'debt', amount_vnd: item.amount_vnd, superseded_by_event: null }] });
    }
    const written = world.sheetReceipts.ready.length;
    world.sheetReceipts = { ...world.sheetReceipts, ready: [], ready_count: 0 };
    world.version += 1;
    return [200, { written, remaining: 0, complete: true, version: world.version }];
  }
  // Tách phụ phí theo bảng PS: thay khoản của từng chuyến READY bằng kế hoạch "sau", tổng giữ nguyên.
  if (url === '/api/v7/ps/fees') {
    if (world.psStale || body.snapshot_sha256 !== world.psFees.snapshot_sha256) return [409, { error: 'STALE_SHEET', message: 'Bảng PS đã đổi. Tải lại rồi tách.' }];
    for (const item of world.psFees.ready) {
      const info = feeTarget(world, item.target_kind === 'trip' ? { trip_id: item.target_id } : { legacy_row_id: item.target_id });
      const before = info.lines.map(line => ({ ...line }));
      info.lines.splice(0, info.lines.length, ...item.after.map(line => ({ id: world.nextFeeLine++, ...line })));
      syncFee(info);
      world.events.unshift({ kind: 'rewrite_trip_fees', actor: 'nguoi-thu', at: '2026-10-01T03:00:00Z',
        before: { targets: [{ [item.target_kind === 'trip' ? 'trip_id' : 'legacy_row_id']: item.target_id, fee_lines: before }], batch_count: 1 },
        after: { targets: [{ [item.target_kind === 'trip' ? 'trip_id' : 'legacy_row_id']: item.target_id, fee_lines: info.lines }], batch_count: 1 } });
    }
    const written = world.psFees.ready.length;
    world.psFees = { ...world.psFees, ready: [], ready_count: 0 };
    world.version += 1;
    return [200, { written, remaining: 0, complete: true, version: world.version }];
  }
  if (url === '/api/v7/sheet/tasks/keep' && body.task_kind === 'ps') {
    const item = world.psFees?.review.find(row => row.keepable && row.target_kind === body.target_kind && row.target_id === body.target_id
      && row.source_fingerprint === body.source_fingerprint);
    if (!item || body.expected_version !== world.version) return [409, { error: 'STALE_SHEET', message: 'Dòng PS đã đổi.' }];
    world.psFees.review = world.psFees.review.filter(row => row !== item);
    world.psFees.review_count = world.psFees.review.length;
    return [200, { kept: true, version: ++world.version }];
  }
  if (url === '/api/v7/sheet/tasks/keep') {
    const item = world.sheetSync.removed_items?.find(row => row.trip_id === body.target_id);
    if (!item || item.source_fingerprint !== body.source_fingerprint) return [409, { error: 'STALE_SHEET' }];
    world.sheetSync.removed_items = world.sheetSync.removed_items.filter(row => row !== item);
    world.sheetSync.removed_count = world.sheetSync.removed_items.length;
    return [200, { kept: true, version: ++world.version }];
  }
  if (url === '/api/v7/sheet/resolve') {
    const item = world.sheetSync.items.find(row => row.source_row === body.source_row || row.existing_id === body.target_id);
    if (!item || !item.changed_fields.includes(body.field)) return [404, { message: 'Không còn trường lệch.' }];
    item.changed_fields = item.changed_fields.filter(field => field !== body.field);
    if (!item.changed_fields.length) world.sheetSync = { ...world.sheetSync, items: world.sheetSync.items.filter(row => row !== item), conflict_count: Math.max(0, world.sheetSync.conflict_count - 1) };
    world.version += 1;
    return [200, { resolved: true, version: world.version }];
  }
  const event = (kind, before, after) => world.events.unshift({ kind, actor: 'nguoi-thu', at: '2026-10-01T03:00:00Z', before, after });
  // CHUNG-TU-01: phiếu thu và ảnh chứng từ giả; ảnh không đổi số tiền.
  if (url === '/api/v7/receipts') {
    const pid = `PH-${String(world.receipts.length + 1).padStart(3, '0')}`;
    world.receipts.push({ id: world.receipts.length + 1, pid, date: body.date, method: body.method, amount_vnd: body.amount_vnd,
      reference: body.reference ?? null, voided_by_event: null, void_reason: null,
      allocations: [{ id: 1, month: monthOf(body.date), kind: 'debt', amount_vnd: body.amount_vnd, superseded_by_event: null }] });
    event('receipt', {}, { pid, date: body.date, amount_vnd: body.amount_vnd });
    world.version += 1;
    return [200, { pid, receipt_id: world.receipts.length, version: world.version }];
  }
  // Hủy phiếu: phiếu và phần trừ nợ của nó bị thay bằng sự kiện hủy, như void_receipt.
  if (url === '/api/v7/receipts/void') {
    const receipt = world.receipts.find(item => item.pid === body.pid && item.voided_by_event == null);
    if (!receipt) return [422, { error: 'RECEIPT_NOT_FOUND', message: 'Không tìm thấy phiếu.' }];
    const id = 100 + world.nextEvent++;
    Object.assign(receipt, { voided_by_event: id, void_reason: body.reason, voided_on: clock,
      allocations: receipt.allocations.map(line => ({ ...line, superseded_by_event: id })) });
    event('void', { pid: body.pid }, { pid: body.pid, reason: body.reason });
    world.version += 1;
    return [200, { pid: body.pid, version: world.version }];
  }
  if (url === '/api/v7/receipts/images') {
    const data = Buffer.from(body.data_base64, 'base64');
    const sha256 = crypto.createHash('sha256').update(data).digest('hex');
    const active = world.images.filter(image => image.pid === body.pid && !image.removed);
    if (active.some(image => image.sha256 === sha256)) return [409, { error: 'IMAGE_DUPLICATE', message: 'Ảnh này đã có trong phiếu.' }];
    const image = { id: 900 + world.images.length, pid: body.pid, sha256, content_type: body.content_type, data: body.data_base64, removed: false };
    world.images.push(image);
    event('receipt_image', {}, { image: { id: image.id, pid: body.pid } });
    world.version += 1;
    return [200, { image: { id: image.id, pid: body.pid, sha256 }, duplicates: world.otherImages.filter(other => other.sha256 === sha256), version: world.version }];
  }
  if (url === '/api/v7/receipts/images/remove') {
    const image = world.images.find(item => item.id === body.image_id);
    image.removed = true;
    event('receipt_image_remove', { image: { id: image.id, pid: image.pid } }, { image: { id: image.id, pid: image.pid, removed: true, reason: body.reason } });
    world.version += 1;
    return [200, { image_id: image.id, removed: true, version: world.version }];
  }
  if (url === '/api/v7/trips/price') {
    const trip = world.trips.find(row => row.id === body.trip_id);
    Object.assign(trip, { unit_price_vnd: body.unit_price_vnd, other_fee_vnd: body.other_fee_vnd, is_missing_price: false });
    event('price_edit', { price: {} }, { price: {} });
  } else if (url === '/api/v7/months/lock') {
    world.locks = world.locks.map(row => row.month === body.month ? { ...row, locked: body.locked } : row);
  } else if (url === '/api/v7/trips/info') {
    const trip = world.trips.find(row => row.id === body.trip_id && !row.deleted);
    const before = { id: trip.id, field: body.field, value: trip[body.field], debt_month: trip.month, status: trip.status };
    trip[body.field] = body.value;
    if (body.field === 'event_date') trip.month = monthOf(body.value);
    const after = { trip: { ...before, value: body.value, debt_month: trip.month } };
    if (trip.month !== before.debt_month) Object.assign(after, { moved_from_month: before.debt_month, moved_to_month: trip.month });
    event('trip_edit', { trip: before }, after);
  } else if (url === '/api/v7/trips/delete') {
    const trip = world.trips.find(row => row.id === body.trip_id);
    event('trip_delete', { trip: { ...trip } }, { trip: { id: trip.id, deleted: true } });
    trip.deleted = true;
  } else if (url === '/api/v7/legacy/edit' || url === '/api/v7/legacy/delete') {
    const row = world.legacy.find(item => item.id === body.legacy_row_id);
    const old = { ...row.current };
    const next = { ...old };
    if (url.endsWith('delete')) Object.assign(next, { deleted: true, counted_vnd: '0' });
    else {
      next[body.field] = body.value === '' ? null : body.value;
      if (body.field === 'event_date') next.month = monthOf(body.value);
      if (body.field.endsWith('_vnd')) next.counted_vnd = next.unit_price_vnd == null ? '0' : String(BigInt(next.unit_price_vnd) + BigInt(next.other_fee_vnd ?? 0));
    }
    const delta = BigInt(next.counted_vnd) - BigInt(old.counted_vnd);
    if (delta !== 0n) world.adjustments.push({ id: world.adjustments.length + 1, month: old.month, trip_id: null, legacy_row_id: row.id, amount_vnd: delta.toString(), note: null });
    row.current = next;
    event(url.endsWith('delete') ? 'legacy_delete' : 'legacy_edit', { legacy: { ...old, field: body.field, value: old[body.field] } }, { legacy: { ...next, field: body.field, value: next[body.field] } });
  } else if (url === '/api/v7/price-table') {
    if (body.expected_version !== world.version) return [409, { error: 'STALE_LEDGER', message: 'Sổ đã thay đổi. Tải lại rồi thử tiếp.' }];
    const before = world.priceTable ?? { tt_shippers: [], locations: [], periods: [] };
    world.priceTable = body.price_table;
    event('price_table_edit', { price_table: before }, { price_table: body.price_table });
    world.version += 1;
    const locked = world.lockedTrips ?? 0, noPrice = world.noPriceTrips ?? 0;
    return [200, { price_table: body.price_table, affected_trips: locked + noPrice, repriced_trips: world.repricedTrips ?? [],
      repriced_delta_vnd: world.repricedDelta ?? '0', locked_trips: locked, no_price_trips: noPrice, reallocated: [], version: world.version }];
  } else if (url === '/api/v7/price-table/apply') {
    const status = world.priceStatus;
    const rows = body.trip_ids.map(id => status.trips.find(row => row.trip_id === id));
    const before = rows.map(row => ({ trip_id: row.trip_id, unit_price_vnd: world.trips.find(trip => trip.id === row.trip_id).unit_price_vnd }));
    for (const row of rows) {
      const trip = world.trips.find(item => item.id === row.trip_id);
      Object.assign(trip, { unit_price_vnd: row.lookup.unit_price_vnd, amount_vnd: row.lookup.unit_price_vnd, is_missing_price: false });
      Object.assign(row, { unit_price_vnd: row.lookup.unit_price_vnd, ready: false, differs: false, from_table: true });
    }
    world.priceStatus = { ...status, ready_count: status.trips.filter(row => row.ready).length, ready_total_vnd: '0', reapply_count: 0 };
    event('price_table_apply', { trips: before }, { trips: rows.map(row => ({ trip_id: row.trip_id, unit_price_vnd: row.lookup.unit_price_vnd })) });
  } else if (url === '/api/v7/months/adjust/delete') {
    const row = world.adjustments.find(item => item.id === body.adjustment_id && item.trip_id == null && item.legacy_row_id == null);
    if (!row) return [422, { error: 'ADJUSTMENT_NOT_FOUND', message: 'Không tìm thấy dòng điều chỉnh cả tháng, có thể đã xóa. Tải lại sổ.' }];
    world.adjustments = world.adjustments.filter(item => item !== row);
    event('adjust_month_delete', { adjustment: { ...row } }, { adjustment: { id: row.id, month: row.month, amount_vnd: '0', deleted: true } });
  } else if (url === '/api/v7/trips/paste') {
    for (const trip of body.trips) {
      const [d, m, y] = trip.date.split('/');
      world.trips.push({ id: 100 + world.trips.length, month: `${y}-${m}-01`, container: trip.container, carrier: trip.carrier, event_date: `${y}-${m}-${d}`,
        origin: trip.from, destination: trip.to, unit_price_vnd: trip.unitPriceVnd, other_fee_vnd: trip.otherFeeVnd, amount_vnd: trip.unitPriceVnd,
        status: 'confirmed', is_missing_price: trip.unitPriceVnd === null, is_fee_only: false, editable: true, info_editable: true, deleted: false });
    }
    event('paste', {}, { trips: body.trips });
  } else return [404, { error: 'NOT_FOUND' }];
  world.version += 1;
  return [200, { ok: true }];
}

async function withPage(fn, setup = () => {}) {
  const world = makeWorld();
  setup(world);
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const send = (status, body) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (url.pathname === '/api/v7/customers') { send(200, { customers: world.customers ?? [{ id: 1, name: 'Khách Thử Sửa', status: 'active' }], demo: true }); return; }
    if (url.pathname.startsWith('/api/v7/presence')) {   // PRESENCE-01: không vào world.requests; SSE không có nên trang hỏi định kỳ
      const chunks = [];
      req.on('data', chunk => chunks.push(chunk));
      req.on('end', () => {
        if (req.method === 'POST') (world.presenceReports ??= []).push(JSON.parse(Buffer.concat(chunks).toString('utf8')));
        send(200, { people: world.people ?? [] });
      });
      return;
    }
    if (url.pathname === '/api/v7/ledger') { world.reads++; send(200, ledger(world)); return; }
    // MO-SO-NHANH-02: Lịch sử đọc riêng như server thật. world.eventsFail: lỗi một lần để thử nút Thử lại.
    if (url.pathname === '/api/v7/ledger/events') {
      world.eventReads = (world.eventReads ?? 0) + 1;
      if (world.eventsFail) { world.eventsFail = false; send(503, { error: 'DB_UNAVAILABLE', message: 'Sổ tạm thời không truy cập được.' }); return; }
      send(200, { customer_id: 1, version: world.version, events: world.events });
      return;
    }
    // Thẻ Tình hình (TRANG-KHACH-01): dòng Tổng quan của sổ giả do test đặt, mặc định sổ không nợ. Vẫn ghi sideReads cho
    // /reminders để test bắt được nếu trang khách đọc lại lần nhắc khi nhắc nợ đang ẩn (NHAC-NO-01, sửa đổi 4/11/2026).
    if (url.pathname === '/api/v7/dashboard/debt' || (url.pathname === '/api/v7/reminders' && req.method === 'GET')) {
      (world.sideReads ??= []).push(url.pathname);
      send(200, url.pathname.endsWith('/reminders') ? { reminders: [] } : world.debt ?? { as_of: clock,
        rule: { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 }, receivable_vnd: '0', customers: [] });
      return;
    }
    // Chat Zalo (ZALO-CHAT-01): hội thoại có tên chứa q do test đặt (world.chats); không đặt thì như hao, máy chủ chưa có bản xuất.
    if (url.pathname === '/api/v7/zalo/conversations') {
      const q = url.searchParams.get('q') ?? '';
      (world.chatReads ??= []).push(q);
      if (!world.chats) send(503, { error: 'ZALO_EXPORT_UNAVAILABLE', message: 'Máy chủ chưa có bản xuất chat Zalo: chưa đặt WEBDEBIT_ZALO_EXPORT_DIR' });
      else send(200, { conversations: world.chats.filter(row => (row.display_name ?? '').toLowerCase().includes(q.toLowerCase())), total: world.chats.length });
      return;
    }
    // ZALO-GROUP-01: dấu tin và group đã gắn của sổ giả do test đặt (world.marks, world.zaloLinks); mặc định chưa có.
    if (url.pathname === '/api/v7/marks' && req.method === 'GET') { send(200, { marks: world.marks ?? [] }); return; }
    if (url.pathname === '/api/v7/zalo/links' && req.method === 'GET') { send(200, { links: world.zaloLinks ?? [] }); return; }
    if (url.pathname === '/api/v7/fee-types' && req.method === 'GET') { send(200, { fee_types: world.feeTypes }); return; }
    if (url.pathname === '/api/v7/receipt-images') {
      send(200, { images: world.images.filter(image => !image.removed).map(({ id, pid, sha256, content_type }) => ({ id, pid, sha256, content_type })) });
      return;
    }
    if (url.pathname === '/api/v7/receipt-image') {
      const image = world.images.find(item => item.id === Number(url.searchParams.get('id')));
      if (image) send(200, { id: image.id, content_type: image.content_type, data_base64: image.data }); else send(422, { error: 'IMAGE_NOT_FOUND' });
      return;
    }
    if (url.pathname === '/api/v7/receipt-images/find') {
      (world.finds ??= []).push(url.searchParams.get('sha256'));
      send(200, { matches: world.otherImages.filter(other => other.sha256 === url.searchParams.get('sha256')) });
      return;
    }
    // BANG-GIA-01: bảng giá và trạng thái giá do test đặt sẵn (world.priceTable, world.priceStatus).
    if (url.pathname === '/api/v7/price-table' && req.method === 'GET') {
      send(200, { customer_id: 1, version: world.version, price_table: world.priceTable ?? { tt_shippers: [], locations: [], periods: [] },
        book_shippers: world.bookShippers ?? [] });
      return;
    }
    if (url.pathname === '/api/v7/price-table/status') {
      send(200, world.priceStatus ?? { customer_id: 1, version: world.version, has_table: false, trips: [], ready_count: 0,
        ready_total_vnd: '0', ready_months: [], reapply_count: 0 });
      return;
    }
    if (url.pathname === '/api/v7/sheet/refresh') {   // nút Làm mới: mặc định server chưa bật
      world.refreshCalls.push(req.method);
      if (world.sheetRefresh) send(200, world.sheetRefresh(req.method)); else send(404, { error: 'NOT_FOUND' });
      return;
    }
    if (url.pathname.startsWith('/api/')) {
      const chunks = [];
      req.on('data', chunk => chunks.push(chunk));
      req.on('end', () => {
        const body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
        world.requests.push({ path: url.pathname, body });
        send(...apply(world, url.pathname, body));
      });
      return;
    }
    const file = path.join(__dirname, url.pathname.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.css') ? 'text/css' : 'text/javascript; charset=utf-8' });
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // SO-GON-04: sổ chỉ mở sẵn tháng hiện tại và tháng liền trước. Dữ liệu giả nằm ở tháng 9/2026 nên mặc định mở tháng đó
    // (?month=) để test không đổi theo ngày chạy; world.month = null để thử đúng mặc định.
    const month = world.month === undefined ? '&month=2026-09' : world.month ? `&month=${world.month}` : '';
    if (world.clock) await page.clock.setFixedTime(world.clock);   // ghim đồng hồ trang (giờ VN) cho test theo ngày
    await world.beforeOpen?.(page);   // cho test chặn phản hồi trước khi trang mở (dữ liệu về muộn)
    await page.goto(`http://127.0.0.1:${server.address().port}/so-khach-v7-live.html?customer=1${month}${world.query ?? ''}`);
    await page.waitForSelector('.book-head');
    await customersLoaded(page);
    const shot = async name => { if (shots) { fs.mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: true }); } };
    await fn({ page, world, shot });
    assert.deepEqual(errors, []);
  } finally { await browser.close(); server.close(); }
}

// Danh sách khách tải song song với sổ; về sau thì vẽ lại cả sổ (redraw trong loadCustomers), tách phần tử
// vừa lấy khỏi DOM (rect = 0). Chờ nó xong (#customer-count có chữ) mới thao tác hay đo. Từ MO-SO-NHANH-01 GET sổ bắt đầu ở đầu
// <head> nên sổ gần như luôn vẽ trước danh sách khách; CI windows 4/11/2026 đỏ đúng cửa sổ này sau page.reload() (tái hiện
// tại máy khi /api/v7/customers chậm 30 ms). Vì vậy mọi test tải lại trang bằng reload() dưới đây, không gọi page.reload() thẳng.
const customersLoaded = page => page.waitForFunction(() => document.querySelector('#customer-count')?.textContent);
async function reload(page) {
  await page.reload();
  await customersLoaded(page);
}

const tripCell = (page, field, id = 11) => page.locator(`.info-edit[data-kind="trip"][data-id="${id}"][data-field="${field}"]`);
const legacyCell = (page, id, field) => page.locator(`.info-edit[data-kind="legacy"][data-id="${id}"][data-field="${field}"]`);
const posts = world => world.requests.map(item => [item.path, item.body]);

// SO-GON-05: sổ hiện một tháng; sang tháng khác bằng chip như người dùng, chờ bảng tháng đó vẽ xong. `key` là yyyy-mm hoặc ngày.
async function viewMonth(page, key) {
  const month = key.slice(0, 7);
  await page.locator(`.month-chip[data-month="${month}"]`).click();
  // Tháng không có dòng nào thì thân tháng cao 0px: chờ có mặt, không chờ "nhìn thấy".
  await page.locator(`#thang-${month} .month-body`).waitFor({ state: 'attached' });
}

module.exports = { clock, todayMonth, withPage, reload, tripCell, legacyCell, posts, viewMonth };
