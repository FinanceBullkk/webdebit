/* Sổ khách V7 bản live — Bảng giá theo ngày hiệu lực (BANG-GIA-01, specs/v7-bang-gia-hieu-luc.md, giai đoạn 2).
 * Khung Bảng giá là ma trận nơi đi × đợt giá (BANG-GIA-05, specs/v7-bang-gia-ma-tran.md), khối phải Shipper áp giá TT,
 * nút "Điền giá theo bảng (N chuyến)" và chữ nhỏ ở ô Đơn giá. Server tra giá và ghi; trang không tự tính giá hay cộng tiền.
 * Nạp trước so-khach-v7-ui.js, dùng chung phạm vi của initLive qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).price = ctx => {
  'use strict';
  const { root, model, api, live, customerId, escape, fmt, dateText, monthKey, monthLabel, showNotice } = ctx;
  const TIER = { khach: 'giá khách', tt: 'giá TT' };
  let status = null;            // GET /api/v7/price-table/status của phiên bản sổ đang vẽ
  let loadedVersion = null;
  let confirm = null;           // { kind: 'ready'|'reapply', ids }
  let sending = false;
  let form = null;              // bảng giá đang sửa trong khung { rows, periods, cells, base, ships, aliases }; null = khung đóng
  let savedShape = '';
  let bar = null;               // { kind: 'info'|'ok'|'bad', text } | { kind: 'ask' }
  let bookShippers = [];
  let loading = false;          // đang đọc bảng giá: chưa hiện lưới để không gõ vào bảng sắp bị thay
  let nextUid = 1;

  // ---- Trạng thái giá: tải lại khi phiên bản sổ đổi; server cũ chưa có đường này thì coi như sổ chưa có bảng giá ----
  ctx.priceOnSnapshot = data => {
    if (!data || data.status !== 'active' || data.version === loadedVersion) return;
    loadedVersion = data.version;
    loadStatus();
  };
  ctx.busyChecks.push(() => form !== null || confirm !== null);
  async function loadStatus() {
    try {
      const response = await fetch(`/api/v7/price-table/status?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      if (!response.ok) return;
      const data = await response.json();
      if (typeof data?.ready_count !== 'number' || !Array.isArray(data.trips)) return;
      // Chỉ vẽ lại khi phần hiện ra đổi: vẽ lại cả sổ sẽ đóng các khung chi tiết đang mở.
      const shape = value => JSON.stringify([value?.has_table, value?.ready_count, value?.ready_total_vnd, value?.reapply_count,
        (value?.trips ?? []).map(trip => [trip.trip_id, trip.ready, trip.differs, trip.from_table, trip.lookup])]);
      if (shape(data) === shape(status)) return;
      status = data;
      if (confirm && !confirmIds(confirm.kind).length) confirm = null;
      // Khung hỏi áp giá đang mở thì vẽ ngay để số chuyến trong khung đúng với lệnh sắp gửi.
      if (confirm) ctx.redraw(); else ctx.redrawWhenFree();
    } catch { /* giữ trạng thái cũ; lần đọc sổ sau thử lại */ }
  }
  const tripsOf = () => new Map((ctx.snapshot?.trips ?? []).map(trip => [trip.id, trip]));
  const lookupOf = id => status?.trips.find(row => row.trip_id === id)?.lookup ?? {};
  // Áp lại giá mới chỉ cho chuyến đang theo bảng, tính vào sổ và ô giá đang sửa được (tháng mở).
  function confirmIds(kind) {
    const trips = tripsOf();
    return (status?.trips ?? []).filter(row => kind === 'ready' ? row.ready
      : row.differs && row.from_table && trips.get(row.trip_id)?.editable === true).map(row => row.trip_id);
  }

  // SO-GON-06: "Điền giá theo bảng" là việc (thanh việc), "Bảng giá" là cài đặt (menu Cài đặt ▾).
  ctx.priceButtons = active => {
    if (!active) return { task: '', setting: '' };
    const ready = status?.ready_count ?? 0;
    return { setting: '<button class="price-table-open" aria-haspopup="dialog">Bảng giá</button>',
      task: ready && !confirm ? `<button class="price-table-apply">Điền giá theo bảng (${ready} chuyến)</button>` : '' };
  };

  // Sau khi vẽ sổ: chữ nhỏ ở ô Đơn giá và khung hỏi lại dưới đầu sổ.
  const REASONS = { UNKNOWN_LOCATION: ['ngoài bảng giá', 'Nơi đi chưa có trong bảng giá'], UNKNOWN_DESTINATION: ['chưa có đích', 'Bảng giá chưa có giá cho nơi đến này, cũng chưa có giá chung (Nơi đến trống) của nơi đi'], NO_PERIOD: ['ngoài ngày có giá', 'Bảng giá chưa có giá cho ngày chuyến này'],
    NO_DATE: ['thiếu ngày', 'Chuyến thiếu ngày nên chưa tra được giá'], NO_ORIGIN: ['thiếu nơi đi', 'Chuyến thiếu nơi đi nên chưa tra được giá'], NO_DESTINATION: ['thiếu nơi đến', 'Chuyến thiếu nơi đến mà nơi đi chỉ có giá theo từng nơi đến'] };
  ctx.priceAfterRender = active => {
    if (!active || !status) return;
    for (const row of status.trips) {
      // Ô Đơn giá: vị trí đổi khi sổ không có cột Shipper (audit UX 31/10/2026).
      const cell = root.querySelector(`[data-row="trip-${row.trip_id}"]`)?.children[ctx.columns.unitPrice()];
      if (!cell) continue;
      const lookup = row.lookup ?? {};
      let note = '', cls = 'price-hint', title = '';
      if (row.ready) { note = `bảng ${fmt(lookup.unit_price_vnd)}`; cls += ' price-ready'; title = `Theo bảng: ${fmt(lookup.unit_price_vnd)} (${TIER[lookup.tier] ?? ''}${lookup.any_destination ? ', giá chung của nơi đi' : ''})`; }
      else if (row.differs) { note = `bảng ${fmt(lookup.unit_price_vnd)}`; cls += ' price-diff'; title = `Khác bảng giá: bảng ${fmt(lookup.unit_price_vnd)} (${TIER[lookup.tier] ?? ''})`; }
      else if (row.from_table) { note = 'theo bảng'; title = `Giá ghi theo bảng (${TIER[lookup.tier] ?? ''})`; }
      else if (row.unit_price_vnd == null && lookup.reason === 'NO_RATE') { note = `thiếu ${TIER[lookup.tier] ?? 'giá'}`; title = `Bảng giá có chuyến từ ${lookup.location ?? 'nơi đi này'} đến ${lookup.destination ?? 'nơi đến này'} nhưng chưa có ${TIER[lookup.tier] ?? 'giá'}`; }
      else if (row.unit_price_vnd == null && REASONS[lookup.reason]) [note, title] = REASONS[lookup.reason];
      if (!note) continue;
      cell.insertAdjacentHTML('beforeend', `<small class="${cls}">${escape(note)}</small>`);
      if (title) cell.title = title;
      if (row.differs) cell.classList.add('price-differs');
    }
    const reapply = confirmIds('reapply').length;
    const strip = reapply && confirm?.kind !== 'reapply'
      ? `<div class="price-strip">Bảng giá đã đổi: <strong>${reapply}</strong> chuyến đang ghi theo giá cũ của bảng. <button type="button" class="price-reapply-open">Áp lại giá mới</button></div>` : '';
    root.querySelector('.book-tasks')?.insertAdjacentHTML('beforeend', strip);
    root.querySelector('.book-bar')?.insertAdjacentHTML('afterend', confirmPanel());
  };
  function confirmPanel() {
    if (!confirm) return '';
    const count = confirm.ids.length;
    const trips = tripsOf();
    const months = [...new Set(confirm.ids.map(id => monthKey(trips.get(id)?.month)).filter(Boolean))].sort()
      .map(key => `tháng ${monthLabel(key)}`).join(', ');
    const head = confirm.kind === 'ready'
      ? `<strong>Điền giá theo bảng cho ${count} chuyến${months ? ` ${escape(months)}` : ''}?</strong> Tổng còn nợ tăng <strong>${fmt(status.ready_total_vnd)} đ</strong>.`
      : `<strong>Áp lại giá mới của bảng cho ${count} chuyến${months ? ` ${escape(months)}` : ''}?</strong> Đơn giá các chuyến này đổi theo bảng.`;
    const rows = confirm.ids.map(id => {
      const trip = trips.get(id) ?? {};
      const lookup = lookupOf(id);
      return `<tr><td>${escape(trip.container ?? '')}</td><td>${trip.event_date ? escape(dateText(trip.event_date)) : ''}</td><td>${escape(trip.origin ?? '')}</td><td>${escape(trip.destination ?? '')}</td><td>${escape(trip.shipper || '–')}</td>
        ${confirm.kind === 'reapply' ? `<td class="num">${fmt(trip.unit_price_vnd)}</td>` : ''}<td class="num">${fmt(lookup.unit_price_vnd)}</td><td>${TIER[lookup.tier] ?? ''}</td></tr>`;
    }).join('');
    return `<div class="price-panel confirm" role="region" aria-label="Xác nhận điền giá theo bảng"><p>${head} Phiếu thu tự phân bổ lại theo nợ cũ trước.</p>
      <div class="price-confirm-list"><table><thead><tr><th>Số container</th><th>Ngày chuyến</th><th>Nơi đi</th><th>Nơi đến</th><th>Shipper</th>${confirm.kind === 'reapply' ? '<th class="num">Đang ghi</th>' : ''}<th class="num">Đơn giá theo bảng</th><th>Loại giá</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="price-actions"><button type="button" class="price-table-write primary">${confirm.kind === 'ready' ? `Điền ${count} giá` : `Áp ${count} giá`}</button><button type="button" class="price-table-cancel">Thôi</button></div></div>`;
  }
  async function post(path, body) {
    const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let result = {};
    try { result = await response.json(); } catch { /* lỗi không có thân */ }
    return { ok: response.ok, result };
  }
  async function writeApply(button) {
    if (sending || !confirm) return;
    if (api.hasPending()) { showNotice('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.'); return; }
    sending = true; button.disabled = true;
    const { ids, kind } = confirm;
    let outcome;
    try {
      outcome = await post('/api/v7/price-table/apply', { customer_id: customerId, expected_version: ctx.snapshot.version,
        idempotency_key: crypto.randomUUID(), trip_ids: ids });
    } catch {
      sending = false; button.disabled = false;
      showNotice('Chưa rõ kết quả điền giá. Tải lại sổ để kiểm tra trước khi thử lại.');
      return;
    }
    sending = false;
    confirm = null;
    try { await api.read(); } catch { showNotice('Đã gửi lệnh điền giá; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
    showNotice(outcome.ok ? `Đã ${kind === 'ready' ? 'điền giá' : 'áp lại giá'} theo bảng cho ${ids.length} chuyến.`
      : `Chưa điền giá nào. ${outcome.result.message || 'Tải lại sổ rồi thử lại.'}`);
  }

  // ---- Khung Bảng giá: ma trận nơi đi × đợt giá (BANG-GIA-05, specs/v7-bang-gia-ma-tran.md) ----
  // Hàng = cặp Nơi đi · Nơi đến; cột = một đợt (Từ ngày, Đến ngày) như server lưu, mỗi đợt một cặp ô Giá khách | Giá TT.
  // Trang chỉ sắp xếp và kiểm dạng dữ liệu; tra giá, đổi giá chuyến và tiền vẫn do server (BANG-GIA-02).
  const TIERS = ['khach', 'tt'];
  const SHOWN = 3;                // số đợt mới nhất hiện mặc định
  let ui = { side: 'ship', period: null, showAll: false, filter: '' };   // khối phải: ship | period | new | paste
  let failed = false;           // đọc bảng giá lỗi: không cho sửa
  let original = null;          // bảng giá như server trả lúc mở, để bước xem lại nói bảng đổi gì
  let review = null;            // bước Xem lại trước khi lưu: { body, result, unknown }
  let errorList = [];
  const layer = () => {
    if (typeof document.createElement !== 'function') return { hidden: true, innerHTML: '', addEventListener() {}, querySelector: () => null, querySelectorAll: () => [], contains: () => false };
    const element = document.createElement('div');
    element.className = 'price-table-dialog';
    element.hidden = true;
    element.setAttribute('role', 'dialog');
    element.setAttribute('aria-modal', 'true');
    element.setAttribute('aria-label', 'Bảng giá của sổ');
    document.body.append(element);
    return element;
  };
  const dialog = layer();
  const $ = selector => dialog.querySelector(selector);
  const dmy = iso => iso ? dateText(iso) : '';
  // Ngày dạng d/m/yyyy hoặc dd/mm/yyyy (như Sheet hiện) → yyyy-mm-dd; sai thì null.
  function isoOf(text) {
    const match = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(String(text ?? '').trim());
    if (!match) return null;
    const [day, month, year] = [Number(match[1]), Number(match[2]), Number(match[3])];
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
    return date.toISOString().slice(0, 10);
  }
  const addDays = (iso, days) => new Date(Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)) + days)).toISOString().slice(0, 10);
  const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  // Giá gõ/dán: "60,000,000", "60.000.000" hoặc "60000000"; trống hoặc "-" là chưa có giá (không phải 0). Sai thì throw.
  function priceOf(text) {
    const value = String(text ?? '').trim();
    if (!value || /^[-–—]$/.test(value)) return null;
    return model.parseVnd(value).toString();
  }
  const priceOk = text => { try { priceOf(text); return true; } catch { return false; } };
  // Khóa so tên như server (_price_key): hoa, gộp khoảng trắng.
  const keyOf = text => String(text ?? '').replace(/\s+/g, ' ').trim().toUpperCase();
  const dateTidy = text => { const iso = isoOf(text); return iso ? dmy(iso) : String(text ?? '').trim(); };
  const priceTidy = text => { try { const price = priceOf(text); return price == null ? '' : fmt(price); } catch { return String(text ?? '').trim(); } };
  const cellKey = (row, period) => `${row.uid}|${period.uid}`;
  const cellOf = (row, period) => form.cells.get(cellKey(row, period)) ?? { khach: '', tt: '' };
  const hasPrice = cell => Boolean(cell && (String(cell.khach).trim() || String(cell.tt).trim()));
  const named = row => Boolean(keyOf(row.kho) || keyOf(row.den));
  const used = row => named(row) || form.periods.some(period => hasPrice(form.cells.get(cellKey(row, period))));
  function setCell(row, period, tier, value, base) {
    const key = cellKey(row, period);
    const cell = form.cells.get(key) ?? { khach: '', tt: '' };
    cell[tier] = value;
    form.cells.set(key, cell);
    if (base !== undefined) { const old = form.base.get(key) ?? { khach: '', tt: '' }; old[tier] = base; form.base.set(key, old); }
  }
  const sortKey = period => [isoOf(period.from) ?? '9999-99-99', String(period.to).trim() ? (isoOf(period.to) ?? '9999-99-99') : '9999-12-31'];
  const sorted = () => [...form.periods].sort((a, b) => {
    const [x, y] = [sortKey(a), sortKey(b)];
    return x[0].localeCompare(y[0]) || x[1].localeCompare(y[1]) || a.uid - b.uid;
  });
  // Nhãn đợt: "15/09 – 09/10/2026", cùng năm thì bỏ năm ở Từ ngày; Đến ngày trống thì "Từ 10/10/2026".
  function periodLabel(period) {
    const from = isoOf(period.from), to = String(period.to).trim() ? isoOf(period.to) : '';
    if (!from) return period.from.trim() ? `Từ ${period.from.trim()}` : 'Chưa có Từ ngày';
    if (to === '') return `Từ ${dmy(from)}`;
    if (!to) return `${dmy(from)} – ${period.to.trim()}`;
    return `${from.slice(0, 4) === to.slice(0, 4) ? dmy(from).slice(0, 5) : dmy(from)} – ${dmy(to)}`;
  }
  const shortDate = period => isoOf(period.from) ? dmy(isoOf(period.from)) : period.from.trim();

  function fromServer(table) {
    const aliases = new Map((table?.locations ?? []).map(item => [keyOf(item.name), item.aliases ?? []]));
    const order = new Map((table?.locations ?? []).map((item, index) => [keyOf(item.name), index]));
    const next = { rows: [], periods: [], cells: new Map(), base: new Map(), ships: [...new Set((table?.tt_shippers ?? []).map(keyOf).filter(Boolean))], aliases };
    const byPair = new Map();
    for (const item of [...(table?.periods ?? [])].sort((a, b) => String(a.valid_from).localeCompare(String(b.valid_from)))) {
      const period = { uid: nextUid++, from: dmy(item.valid_from), to: dmy(item.valid_to), fresh: false, closes: [] };
      next.periods.push(period);
      for (const rate of item.rates ?? []) {
        const key = `${keyOf(rate.location)}|${keyOf(rate.destination)}`;
        if (!byPair.has(key)) byPair.set(key, { uid: nextUid++, kho: keyOf(rate.location), den: keyOf(rate.destination) });
        const cellId = `${byPair.get(key).uid}|${period.uid}`;
        for (const map of [next.cells, next.base]) { const cell = map.get(cellId) ?? { khach: '', tt: '' }; cell[rate.tier] = fmt(rate.unit_price_vnd); map.set(cellId, cell); }
      }
    }
    next.rows = [...byPair.values()].sort((a, b) => (order.get(a.kho) ?? 1e9) - (order.get(b.kho) ?? 1e9) || a.kho.localeCompare(b.kho)
      || (a.den ? 1 : 0) - (b.den ? 1 : 0) || a.den.localeCompare(b.den));
    return next;
  }
  // Bảng gửi server: mỗi cột còn giá là một đợt (cột cùng ngày gộp làm một); tên khác của nơi đi giữ như đã lưu.
  function payload() {
    const locations = new Map(), periods = new Map();
    // Nơi đi theo thứ tự hàng trên lưới, chỉ nơi đi còn ít nhất một giá.
    for (const row of form.rows) {
      const key = keyOf(row.kho);
      if (key && !locations.has(key) && form.periods.some(period => hasPrice(form.cells.get(cellKey(row, period))))) locations.set(key, { name: key, aliases: form.aliases.get(key) ?? [] });
    }
    for (const period of sorted()) {
      const from = isoOf(period.from), to = String(period.to).trim() ? isoOf(period.to) : null;
      for (const row of form.rows) {
        const key = keyOf(row.kho);
        const cell = form.cells.get(cellKey(row, period));
        if (!key || !hasPrice(cell)) continue;
        const periodKey = `${from}|${to}`;
        if (!periods.has(periodKey)) periods.set(periodKey, { valid_from: from, valid_to: to, rates: [] });
        for (const tier of TIERS) {
          const price = priceOf(cell[tier]);
          if (price != null) periods.get(periodKey).rates.push({ location: key, destination: keyOf(row.den), tier, unit_price_vnd: price });
        }
      }
    }
    return { tt_shippers: [...new Set(form.ships.map(keyOf).filter(Boolean))], locations: [...locations.values()],
      periods: [...periods.values()].sort((a, b) => a.valid_from.localeCompare(b.valid_from)) };
  }
  // Hình dạng để biết còn thay đổi chưa lưu: tập (đợt, nơi đi, nơi đến, loại giá, giá) đã chuẩn hóa và danh sách shipper TT.
  function shapeOf(value) {
    const items = [];
    for (const period of value.periods) for (const row of value.rows) {
      const cell = value.cells.get(cellKey(row, period));
      for (const tier of TIERS) if (cell && String(cell[tier]).trim()) items.push([dateTidy(period.from), dateTidy(period.to), keyOf(row.kho), keyOf(row.den), tier, priceTidy(cell[tier])].join('|'));
    }
    return JSON.stringify([items.sort(), [...new Set(value.ships.map(keyOf).filter(Boolean))].sort()]);
  }
  const editedCell = (row, period, tier) => priceTidy(cellOf(row, period)[tier]) !== priceTidy((form.base.get(cellKey(row, period)) ?? {})[tier]);
  const editedCount = () => { let n = 0; for (const period of form.periods) for (const row of form.rows) for (const tier of TIERS) if (editedCell(row, period, tier)) n += 1; return n; };

  // Kiểm cả bảng như server: ngày của đợt, giá từng ô, hàng thiếu/trùng nơi đi, trùng ngày cùng nơi đi + nơi đến + loại giá
  // (BANG-GIA-04 mục 4). Lỗi gắn vào đúng ô / đầu cột, kèm danh sách lỗi bằng chữ trên lưới.
  function check() {
    const cells = new Map(), rows = new Map(), periods = new Map(), list = [];
    const where = row => `${keyOf(row.kho) || 'Hàng không tên'}${keyOf(row.den) ? ` → ${keyOf(row.den)}` : ''}`;
    for (const period of form.periods) {
      const from = isoOf(period.from), to = String(period.to).trim() ? isoOf(period.to) : '';
      let text = '';
      if (!String(period.from).trim()) text = 'Thiếu Từ ngày';
      else if (!from) text = 'Từ ngày sai';
      else if (to === null) text = 'Đến ngày sai';
      else if (to && to < from) text = 'Đến trước Từ ngày';
      if (text) { periods.set(period.uid, text); list.push({ text: `Đợt ${periodLabel(period)}: ${text}`, period: period.uid }); }
    }
    const seen = new Map();
    form.rows.forEach((row, index) => {
      if (!used(row)) return;
      const key = `${keyOf(row.kho)}|${keyOf(row.den)}`;
      if (!keyOf(row.kho)) { rows.set(row.uid, 'Thiếu Nơi đi'); list.push({ text: `Hàng ${index + 1}: thiếu Nơi đi`, row: row.uid }); }
      else if (seen.has(key)) { rows.set(row.uid, 'Hai hàng trùng'); list.push({ text: `${where(row)} có hai hàng`, row: row.uid }); }
      else seen.set(key, row);
      for (const period of form.periods) for (const tier of TIERS) {
        if (priceOk(cellOf(row, period)[tier])) continue;
        cells.set(`${row.uid}|${period.uid}|${tier}`, 'sai');
        list.push({ text: `${where(row)}, đợt ${shortDate(period)}: ${tier === 'khach' ? 'Giá khách' : 'Giá TT'} sai`, cell: [row.uid, period.uid, tier] });
      }
    });
    // Trùng ngày: chỉ xét đợt có ngày đúng, trong cùng một hàng (hàng là cặp nơi đi + nơi đến) và cùng loại giá.
    const ranges = form.periods.filter(period => !periods.has(period.uid))
      .map(period => ({ period, from: isoOf(period.from), to: String(period.to).trim() ? isoOf(period.to) : '9999-12-31' }));
    for (const row of form.rows) {
      if (!keyOf(row.kho) || rows.has(row.uid)) continue;
      for (const tier of TIERS) {
        const have = ranges.filter(item => String(cellOf(row, item.period)[tier]).trim());
        for (let i = 0; i < have.length; i += 1) for (let j = i + 1; j < have.length; j += 1) {
          const [a, b] = [have[i], have[j]];
          if (!(a.from <= b.to && b.from <= a.to)) continue;
          const [first, second] = a.from <= b.from ? [a.period, b.period] : [b.period, a.period];
          cells.set(`${row.uid}|${a.period.uid}|${tier}`, 'trùng'); cells.set(`${row.uid}|${b.period.uid}|${tier}`, 'trùng');
          if (!periods.has(second.uid)) periods.set(second.uid, `Trùng ngày đợt ${shortDate(first)}`);
          if (!periods.has(first.uid)) periods.set(first.uid, `Trùng ngày đợt ${shortDate(second)}`);
          list.push({ text: `${where(row)}: đợt ${shortDate(second)} trùng ngày đợt ${shortDate(first)} (${TIER[tier]})`, cell: [row.uid, second.uid, tier] });
        }
      }
    }
    return { cells, rows, periods, list, size: list.length };
  }
  function periodState(period, errors) {
    if (errors.periods.has(period.uid)) return ['bad', errors.periods.get(period.uid)];
    if (period.fresh) return ['fresh', 'đợt mới'];
    const from = isoOf(period.from), to = String(period.to).trim() ? isoOf(period.to) : '';
    const now = today();
    if (from > now) return ['future', 'sắp áp dụng'];
    if (to && to < now) return ['old', 'hết hạn'];
    return ['now', 'đang dùng'];
  }
  // Cột hiện: 3 đợt mới nhất, cộng đợt đang chọn và đợt có lỗi; "Xem đợt cũ hơn" mở hết.
  function visiblePeriods(errors) {
    const all = sorted();
    if (ui.showAll || all.length <= SHOWN) return { shown: all, hidden: 0 };
    const keep = new Set(all.slice(-SHOWN).map(period => period.uid));
    for (const period of all) if (period.uid === ui.period || errors.periods.has(period.uid) || period.fresh) keep.add(period.uid);
    const shown = all.filter(period => keep.has(period.uid));
    return { shown, hidden: all.length - shown.length };
  }
  const visibleRows = () => {
    const needle = keyOf(ui.filter);
    return form.rows.filter(row => !needle || keyOf(row.kho).includes(needle) || keyOf(row.den).includes(needle) || !named(row));
  };
  // Ô khác đợt liền trước (cột gần nhất bên trái có giá của cùng hàng) thì đậm.
  function changedFromPrevious(row, period, tier, order) {
    const value = priceTidy(cellOf(row, period)[tier]);
    if (!value) return false;
    for (let i = order.indexOf(period) - 1; i >= 0; i -= 1) {
      const previous = form.cells.get(cellKey(row, order[i]));
      if (hasPrice(previous)) return priceTidy(previous[tier]) !== value;
    }
    return false;
  }

  async function openDialog() {
    form = fromServer(null);
    original = null; review = null;
    ui = { side: 'ship', period: null, showAll: false, filter: '' };
    loading = true;
    bar = { kind: 'info', text: 'Đang đọc bảng giá…' };
    savedShape = shapeOf(form);
    dialog.hidden = false;
    render();
    try {
      const response = await fetch(`/api/v7/price-table?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data?.price_table) throw Error(data?.message || 'Không đọc được bảng giá.');
      form = fromServer(data.price_table);
      original = data.price_table;
      bookShippers = Array.isArray(data.book_shippers) ? data.book_shippers : [];
      savedShape = shapeOf(form);
      bar = null;
    } catch (error) { bar = { kind: 'bad', text: error.message || 'Không đọc được bảng giá.' }; loading = false; failed = true; render(); return; }
    loading = false;
    render();
    $('.price-grid-title')?.focus();
  }
  function closeDialog() { form = null; review = null; bar = null; loading = false; failed = false; dialog.hidden = true; dialog.innerHTML = ''; root.querySelector('.price-table-open')?.focus(); ctx.redraw(); }
  const dirty = () => form && !loading && !failed && shapeOf(form) !== savedShape;
  function requestClose() {
    if (dirty()) { bar = { kind: 'ask' }; renderBar(); $('.price-bar .primary')?.focus(); return; }
    closeDialog();
  }
  const shipCount = name => bookShippers.find(item => keyOf(item.name) === keyOf(name))?.trip_count ?? 0;
  // Tên shipper gần giống một shipper TT: bỏ khoảng trắng/dấu chấm/gạch thì trùng, hoặc khác không quá 2 ký tự.
  const loose = text => keyOf(text).replace(/[\s.\-_,]/g, '');
  function distance(a, b) {
    if (Math.abs(a.length - b.length) > 2) return 3;
    let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i += 1) {
      const current = [i];
      for (let j = 1; j <= b.length; j += 1) current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      previous = current;
    }
    return previous[b.length];
  }
  const lookalike = name => form.ships.find(ship => { const [a, b] = [loose(name), loose(ship)]; return a && b && (a === b || (Math.min(a.length, b.length) >= 5 && distance(a, b) <= 2)); });

  // Vẽ lại cả khung, giữ con trỏ ở ô đang đứng (ô giá, ô nơi đi, ô ở khối phải).
  function focusKey() {
    const el = document.activeElement;
    if (!el || !dialog.contains(el)) return null;
    const d = el.dataset ?? {};
    if (d.tier) return `input[data-row="${d.row}"][data-per="${d.per}"][data-tier="${d.tier}"]`;
    if (d.f) return `input[data-row="${d.row}"][data-f="${d.f}"]`;
    return el.id ? `#${el.id}` : null;
  }
  function rerender() {
    const key = focusKey();
    render();
    if (key) $(key)?.focus();
  }

  function render() {
    if (!form) return;
    const title = `<h2 class="price-grid-title" tabindex="-1">Bảng giá <span class="pm-book">${escape(live.customerName?.(customerId) ?? 'sổ khách')}</span></h2>`;
    if (review) { renderReview(); return; }
    if (loading || failed) {
      dialog.innerHTML = `<div class="price-table-panel"><header>${title}<span class="price-grow"></span><button type="button" class="price-table-close">Đóng</button></header><div class="price-bar"></div></div>`;
      renderBar();
      return;
    }
    const errors = check();
    const empty = !form.rows.length && !form.periods.length;
    dialog.innerHTML = `<div class="price-table-panel"><header>${title}<span class="price-dirty" hidden></span><span class="price-grow"></span>
        <button type="button" class="price-paste-open"${ui.side === 'paste' ? ' aria-pressed="true"' : ''}>Dán từ Sheet</button><button type="button" class="price-table-save primary">Xem lại và lưu</button><button type="button" class="price-table-close">Đóng</button></header>
      <div class="pm-body"><main class="pm-main">
        <div class="pm-tools"><input class="pm-find" id="pm-find" value="${escape(ui.filter)}" placeholder="Tìm nơi đi" aria-label="Tìm nơi đi" autocomplete="off" spellcheck="false">
          <span class="pm-hint"></span><button type="button" class="price-row-add">+ Thêm nơi đi</button><button type="button" class="price-new-open">${form.periods.length ? '+ Đổi giá từ ngày…' : '+ Thêm đợt giá'}</button></div>
        <div class="price-bar"></div><div class="pm-errors" role="alert"></div>${outsideStrip()}
        ${empty ? helpBox() : `<div class="pm-scroll">${grid(errors)}</div>`}
      </main><aside class="pm-side" aria-label="${ui.side === 'ship' ? 'Shipper áp giá TT' : 'Đợt giá'}">${side(errors)}</aside></div></div>
      <datalist id="price-ship-list">${bookShippers.map(item => `<option value="${escape(item.name)}">`).join('')}</datalist>`;
    renderBar();
    updateGrid(errors);
  }
  // Dải "nơi đi ngoài bảng" (BANG-GIA-05, người dùng chốt 13/11/2026): chuyến chưa có giá vì server tra ra UNKNOWN_LOCATION,
  // gom theo nơi đi chưa có hàng trên lưới. Nút chỉ thêm hàng trống để gõ giá; không tự điền giá, không ghi gì cho tới khi lưu.
  function outsideOrigins() {
    const trips = tripsOf();
    const have = new Set(form.rows.map(row => keyOf(row.kho)).filter(Boolean));
    const counts = new Map();
    for (const row of status?.trips ?? []) {
      const trip = trips.get(row.trip_id);
      if (row.lookup?.reason !== 'UNKNOWN_LOCATION' || row.unit_price_vnd != null || !trip || trip.deleted) continue;
      const key = keyOf(trip.origin);
      if (key && !have.has(key)) counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }
  function outsideStrip() {
    const origins = outsideOrigins();
    if (!origins.length) return '';
    const total = origins.reduce((sum, [, count]) => sum + count, 0);
    const shown = origins.slice(0, 5).map(([name, count]) => `${escape(name)} (${count} chuyến)`).join(', ');
    return `<div class="pm-outside" role="status"><span>${total} chuyến chưa có giá vì nơi đi ngoài bảng: ${shown}${origins.length > 5 ? `, và ${origins.length - 5} nơi đi khác` : ''}.</span>
      <button type="button" class="price-outside-add">Thêm ${origins.length} nơi đi này</button></div>`;
  }
  const SHEET_PICTURE = `<table class="price-sheet" aria-hidden="true"><tr><td class="s">EFFECTIVE FROM</td><td class="s">EFFECTIVE TO</td><td class="s">LOCATION</td><td class="s">… PRICE</td><td class="s r">TT PRICE</td><td class="g"></td><td class="o">SHIPPER ÁP GIÁ TT</td></tr>
      <tr><td class="s">15/09/2026</td><td class="s">09/10/2026</td><td class="s">LONG AN</td><td class="s n">58,000,000</td><td class="s r n">72,000,000</td><td class="g"></td><td class="o">TÊN SHIPPER</td></tr>
      <tr><td class="s">10/10/2026</td><td class="s"></td><td class="s">LONG AN</td><td class="s n">58,000,000</td><td class="s r n">66,000,000</td><td class="g"></td><td class="o"></td></tr></table>`;
  const pasteArea = id => `<textarea class="pm-paste" id="${id}" rows="3" placeholder="Bấm vào đây rồi Ctrl+V" aria-label="Dán vùng bảng giá từ Sheet" spellcheck="false"></textarea>`;
  function helpBox() {
    return `<div class="price-help"><div><p><strong>Sổ này chưa có bảng giá.</strong> Trên Sheet chọn vùng bảng giá như hình (kèm cột SHIPPER ÁP GIÁ TT nếu có), Ctrl+C, rồi dán vào ô dưới.</p>
      <p>Nơi đến để trống là giá chung của nơi đi; chỉ điền Nơi đến khi nơi đến đó có giá riêng.</p>${pasteArea('pm-paste-main')}</div>${SHEET_PICTURE}</div>`;
  }
  function grid(errors) {
    const { shown, hidden } = visiblePeriods(errors);
    const rows = visibleRows();
    const head1 = shown.map(period => {
      const [state, text] = periodState(period, errors);
      return `<th colspan="2" class="ph st-${state}${ui.period === period.uid ? ' sel' : ''}" data-per="${period.uid}"><button type="button" class="pm-period" data-per="${period.uid}" aria-label="Sửa ngày đợt ${escape(periodLabel(period))}">
        <span class="pd">${escape(periodLabel(period))}</span><span class="ps">${escape(text)}</span></button></th>`;
    }).join('');
    const head2 = shown.map(period => { const [state] = periodState(period, errors); return `<th class="num sep st-${state}">Giá khách</th><th class="num st-${state}">Giá TT</th>`; }).join('');
    const body = rows.map(row => {
      const label = `${keyOf(row.kho) || 'hàng mới'}${keyOf(row.den) ? ` → ${keyOf(row.den)}` : ''}`;
      return `<tr data-row="${row.uid}"><th class="pk" scope="row"><input data-row="${row.uid}" data-f="kho" value="${escape(row.kho)}" title="${escape(row.kho)}" aria-label="Nơi đi" autocomplete="off" spellcheck="false"></th>
        <td class="pn"><input data-row="${row.uid}" data-f="den" value="${escape(row.den)}" title="${escape(row.den)}" aria-label="Nơi đến của ${escape(keyOf(row.kho) || 'hàng mới')}" autocomplete="off" spellcheck="false"></td>
        <td class="px"><button type="button" class="price-row-drop" data-row="${row.uid}" aria-label="Bỏ hàng ${escape(label)}">×</button></td>
        ${shown.map(period => { const [state] = periodState(period, errors); const cell = cellOf(row, period); return TIERS.map(tier =>
          `<td class="pc st-${state}${tier === 'khach' ? ' sep' : ''}"><input class="num" data-row="${row.uid}" data-per="${period.uid}" data-tier="${tier}" value="${escape(cell[tier])}" placeholder="—"
            aria-label="${tier === 'tt' ? 'Giá TT' : 'Giá khách'} ${escape(label)} đợt ${escape(periodLabel(period))}" autocomplete="off" spellcheck="false" inputmode="numeric"></td>`).join(''); }).join('')}</tr>`;
    }).join('');
    const none = rows.length ? '' : `<tr><td class="pm-none" colspan="${3 + shown.length * 2}">${form.rows.length ? 'Không có nơi đi nào có chữ này.' : 'Chưa có nơi đi. Bấm "+ Thêm nơi đi" hoặc dán từ Sheet.'}</td></tr>`;
    return `<table class="pm-grid"><thead><tr><th colspan="3" class="pm-corner">${hidden ? `<button type="button" class="pm-older">‹ Xem ${hidden} đợt cũ hơn</button>`
        : ui.showAll && form.periods.length > SHOWN ? `<button type="button" class="pm-older">Chỉ xem ${SHOWN} đợt mới nhất</button>` : ''}</th>${head1}</tr>
      <tr><th class="pk">Nơi đi</th><th class="pn">Nơi đến</th><th class="px"></th>${head2}</tr></thead><tbody>${body}${none}</tbody></table>`;
  }
  function side(errors) {
    if (ui.side === 'paste') {
      return `<h3>Dán từ Sheet</h3><p>Trên Sheet chọn từ cột EFFECTIVE FROM tới TT PRICE (thêm cột SHIPPER ÁP GIÁ TT nếu có), Ctrl+C, rồi dán vào ô dưới.</p>
        ${pasteArea('pm-paste-side')}<p class="pm-note">Cùng đợt, cùng nơi đi thì giá dán vào thay giá đang có; đợt hoặc nơi đi mới được thêm vào.</p>
        <p class="pm-note">Muốn dán một cột giá: đứng ở ô giá đầu tiên trong lưới rồi Ctrl+V.</p><div class="pm-side-actions"><button type="button" class="pm-side-close">Xong</button></div>`;
    }
    if (ui.side === 'new') {
      return `<h3>Đợt giá mới</h3><label for="price-new-from">Áp dụng từ ngày</label><input id="price-new-from" class="price-new-from" placeholder="dd/mm/yyyy" inputmode="numeric" autocomplete="off">
        <p class="pm-note">${form.periods.some(period => !String(period.to).trim()) ? 'Thêm cột giá mới bên phải, chép giá đang dùng để sửa. Đợt đang dùng tự kết thúc ngày liền trước.' : 'Thêm cột giá trống bên phải để gõ hoặc dán giá.'}</p>
        <div class="pm-side-actions"><button type="button" class="price-new-ok primary">Thêm cột giá mới</button><button type="button" class="price-new-cancel">Thôi</button></div>`;
    }
    const period = ui.side === 'period' && form.periods.find(item => item.uid === ui.period);
    if (period) {
      const count = form.rows.filter(row => hasPrice(form.cells.get(cellKey(row, period)))).length;
      const error = errors.periods.get(period.uid);
      const closed = form.periods.filter(item => period.closes.includes(item.uid));
      return `<h3>${period.fresh ? 'Đợt giá mới' : 'Đợt giá'}</h3>
        <label for="pm-from">${period.fresh ? 'Áp dụng từ ngày' : 'Từ ngày'}</label><input id="pm-from" class="pm-date" data-pf="from" value="${escape(period.from)}" placeholder="dd/mm/yyyy" inputmode="numeric" autocomplete="off">
        <label for="pm-to">Đến ngày</label><input id="pm-to" class="pm-date" data-pf="to" value="${escape(period.to)}" placeholder="trống = còn dùng" inputmode="numeric" autocomplete="off">
        <p class="pm-error"${error ? '' : ' hidden'}>${escape(error ?? '')}</p>
        ${closed.length ? `<p class="pm-note pm-closes">${closed.map(item => `Đợt ${escape(shortDate(item))} tự kết thúc ngày ${escape(dateTidy(item.to))}.`).join(' ')}</p>` : ''}
        ${period.fresh ? '<p class="pm-counts"></p>' : `<p class="pm-note">${count} nơi đi có giá trong đợt này.</p>`}
        <div class="pm-side-actions"><button type="button" class="price-period-drop" data-per="${period.uid}">Bỏ đợt này</button><button type="button" class="pm-side-close">Xong</button></div>`;
    }
    const shipRows = form.ships.map((name, index) => {
      const count = shipCount(name);
      return `<li><b>${escape(name)}</b><span class="${count ? 'pm-count' : 'pm-count none'}">${count ? `${count} chuyến` : 'chưa có chuyến'}</span><button type="button" class="price-ship-drop" data-s="${index}" aria-label="Bỏ shipper ${escape(name)}">×</button></li>`;
    }).join('');
    const ttKeys = new Set(form.ships.map(keyOf));
    const khach = bookShippers.filter(item => !ttKeys.has(keyOf(item.name))).sort((a, b) => (b.trip_count ?? 0) - (a.trip_count ?? 0) || String(a.name).localeCompare(String(b.name)));
    const khachRows = khach.map(item => {
      const like = lookalike(item.name);
      return `<li${like ? ' class="like"' : ''}><span>${escape(keyOf(item.name))}</span><span class="pm-count">${item.trip_count ?? 0} chuyến</span>${like
        ? `<span class="pm-like">Gần giống ${escape(like)}</span><button type="button" class="price-ship-move" data-name="${escape(keyOf(item.name))}">Chuyển sang giá TT</button>` : ''}</li>`;
    }).join('');
    return `<h3>Shipper áp giá TT</h3><p class="pm-note">Shipper khác lấy giá khách.</p><ul class="pm-ships">${shipRows || '<li class="pm-empty">Chưa có shipper nào.</li>'}</ul>
      <div class="pm-ship-add"><input id="pm-ship-new" class="pm-ship-new" list="price-ship-list" placeholder="Tên shipper" aria-label="Tên shipper thêm vào giá TT" autocomplete="off" spellcheck="false"><button type="button" class="price-ship-add">Thêm</button></div>
      <h4>Trong sổ đang lấy giá khách</h4>${bookShippers.length ? (khachRows ? `<ul class="pm-khach">${khachRows}</ul>` : '<p class="pm-note">Mọi shipper trong sổ đều lấy giá TT.</p>')
        : '<p class="pm-note">Chuyến trong sổ chưa có tên shipper: mọi chuyến lấy giá khách.</p>'}`;
  }
  function renderBar() {
    const box = $('.price-bar');
    if (!box) return;
    if (bar?.kind === 'ask') box.innerHTML = `<div class="price-msg ask" role="alert"><span>Bảng giá có thay đổi chưa lưu.</span><button type="button" class="price-table-save primary">Lưu</button><button type="button" class="price-discard">Bỏ thay đổi</button><button type="button" class="price-stay">Ở lại</button></div>`;
    else box.innerHTML = bar ? `<div class="price-msg ${bar.kind}" role="${bar.kind === 'bad' ? 'alert' : 'status'}"><span>${escape(bar.text)}</span>${loading || failed ? '' : '<button type="button" class="price-msg-close">Đóng</button>'}</div>` : '';
  }
  const setBar = (kind, text) => { bar = { kind, text }; renderBar(); };
  // Đang gõ: cập nhật màu ô, chữ ở đầu cột, danh sách lỗi, trạng thái lưu tại chỗ, không vẽ lại ô nhập.
  function updateGrid(errors = check()) {
    const order = sorted();
    const byUid = new Map(form.rows.map(row => [row.uid, row]));
    const periods = new Map(form.periods.map(period => [period.uid, period]));
    for (const input of dialog.querySelectorAll('input[data-tier]')) {
      const row = byUid.get(Number(input.dataset.row)), period = periods.get(Number(input.dataset.per)), tier = input.dataset.tier;
      if (!row || !period) continue;
      const error = errors.cells.get(`${row.uid}|${period.uid}|${tier}`);
      input.classList.toggle('edited', editedCell(row, period, tier));
      input.classList.toggle('changed', changedFromPrevious(row, period, tier, order));
      input.classList.toggle('bad', Boolean(error));
      if (error) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid');
    }
    for (const input of dialog.querySelectorAll('input[data-f="kho"]')) {
      const error = errors.rows.get(Number(input.dataset.row));
      input.classList.toggle('bad', Boolean(error));
      input.title = error ? `${error}: ${input.value}` : input.value;
    }
    for (const th of dialog.querySelectorAll('th.ph')) {
      const period = periods.get(Number(th.dataset.per));
      if (!period) continue;
      const [state, text] = periodState(period, errors);
      th.className = `ph st-${state}${ui.period === period.uid ? ' sel' : ''}`;
      th.querySelector('.ps').textContent = text;
      th.querySelector('.pd').textContent = periodLabel(period);
    }
    const box = $('.pm-errors');
    if (box) box.innerHTML = errors.size ? `<strong>Chưa lưu được: ${errors.size} lỗi cần sửa</strong><ul>${errors.list.slice(0, 4).map((item, index) =>
      `<li>${escape(item.text)} <button type="button" class="pm-goto" data-i="${index}">Sửa</button></li>`).join('')}</ul>${errors.size > 4 ? `<span>và ${errors.size - 4} lỗi khác.</span>` : ''}` : '';
    if (box) box.hidden = !errors.size;
    errorList = errors.list;
    const sideError = $('.pm-error');
    if (sideError && ui.period != null) { const text = errors.periods.get(ui.period) ?? ''; sideError.textContent = text; sideError.hidden = !text; }
    const counts = $('.pm-counts');
    const period = periods.get(ui.period);
    const closes = $('.pm-closes');
    if (closes && period) closes.textContent = form.periods.filter(item => period.closes.includes(item.uid))
      .map(item => `Đợt ${shortDate(item)} tự kết thúc ngày ${dateTidy(item.to)}.`).join(' ');
    if (counts && period) {
      const filled = form.rows.filter(row => hasPrice(form.cells.get(cellKey(row, period))));
      const changed = filled.filter(row => TIERS.some(tier => editedCell(row, period, tier))).length;
      counts.innerHTML = `<b>${changed} nơi đi</b> đổi giá<br><span class="pm-note">${filled.length - changed} nơi đi giữ giá đợt trước</span>`;
    }
    const isDirty = dirty();
    const chip = $('.price-dirty');
    if (chip) { const n = editedCount(); chip.hidden = !isDirty; chip.textContent = `Chưa lưu${n ? ` · ${n} ô giá đổi` : ''}`; }
    const hint = $('.pm-hint');
    if (hint) {
      const total = form.periods.length;
      hint.textContent = isDirty ? 'Lưu xong, chuyến đang theo bảng ở tháng mở tự đổi giá.'
        : total ? `${Math.min(total, SHOWN) < total && !ui.showAll ? `${SHOWN} đợt gần nhất. ` : ''}Ô đậm: giá khác đợt trước.` : '';
      hint.classList.toggle('warn', isDirty);
    }
  }
  function goTo(item) {
    if (!item) return;
    if (item.period != null) { openPeriod(item.period); $('#pm-from')?.focus(); return; }
    const [rowUid, periodUid, tier] = item.cell ?? [item.row];
    if (ui.filter) ui.filter = '';
    if (periodUid != null && !visiblePeriods(check()).shown.some(period => period.uid === periodUid)) ui.showAll = true;
    render();
    const input = tier ? $(`input[data-row="${rowUid}"][data-per="${periodUid}"][data-tier="${tier}"]`) : $(`input[data-row="${rowUid}"][data-f="kho"]`);
    input?.focus();
    input?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }
  function openPeriod(uid) { ui.side = 'period'; ui.period = uid; render(); }
  function addShips(names) {
    let added = 0;
    for (const name of names) {
      const key = keyOf(name);
      if (!key || /shipper/i.test(key) || form.ships.some(ship => keyOf(ship) === key)) continue;
      form.ships.push(key);
      added += 1;
    }
    return added;
  }
  function rowFor(kho, den) {
    let row = form.rows.find(item => keyOf(item.kho) === kho && keyOf(item.den) === den);
    if (row) return row;
    row = { uid: nextUid++, kho, den };
    // Hàng có nơi đến riêng đứng ngay sau các hàng cùng nơi đi.
    let at = -1;
    form.rows.forEach((item, index) => { if (keyOf(item.kho) === kho) at = index; });
    if (at < 0) { at = form.rows.length; while (at > 0 && !used(form.rows[at - 1])) at -= 1; } else at += 1;
    form.rows.splice(at, 0, row);
    return row;
  }
  function periodFor(from, to) {
    const found = form.periods.find(period => dateTidy(period.from) === from && dateTidy(period.to) === to);
    if (found) return found;
    const period = { uid: nextUid++, from, to, fresh: false, closes: [] };
    form.periods.push(period);
    return period;
  }
  const splitLines = text => String(text).replace(/\r\n?/g, '\n').replace(/\n+$/, '').split('\n').map(line => line.split('\t').map(cell => cell.trim()));
  // Vùng Sheet phẳng (Từ · Đến · Nơi đi · [Nơi đến] · Giá khách · Giá TT, cột shipper sau một cột trống) → gộp vào ma trận:
  // cùng (Từ, Đến) là một đợt, cùng (Nơi đi, Nơi đến) là một hàng; ô cùng đợt cùng hàng bị thay.
  const looksFlat = text => splitLines(text).some(cells => cells.length >= 5 || isoOf(cells[0]));
  function importFlat(text) {
    const names = [], periods = new Set();
    let count = 0;
    for (const cells of splitLines(text)) {
      const withDestination = cells.length === 6 || cells.length >= 8;
      const shipperColumn = cells.length >= 8 ? 7 : 6;
      if (cells[shipperColumn]) names.push(cells[shipperColumn]);
      if (cells[0] && !/\d/.test(cells[0])) continue;   // dòng tiêu đề
      const [from, to, kho, den, khach, tt] = withDestination ? cells : [cells[0], cells[1], cells[2], '', cells[3], cells[4]];
      if (![from, to, kho, den, khach, tt].some(Boolean)) continue;
      const period = periodFor(dateTidy(from), dateTidy(to));
      const row = rowFor(keyOf(kho), keyOf(den));
      setCell(row, period, 'khach', priceTidy(khach));
      setCell(row, period, 'tt', priceTidy(tt));
      periods.add(period.uid);
      count += 1;
    }
    const added = addShips(names);
    ui.side = 'ship';
    render();
    if (count || added) setBar('ok', `Đã dán ${[count ? `${count} dòng giá vào ${periods.size} đợt` : '', added ? `${added} shipper áp giá TT` : ''].filter(Boolean).join(' và ')}. Kiểm lại rồi bấm Lưu bảng giá.`);
    else setBar('bad', 'Không thấy dòng giá nào. Trên Sheet chọn từ cột EFFECTIVE FROM tới TT PRICE rồi dán lại.');
  }
  // Dán một khối 1–2 cột vào ô giá: điền xuống từ hàng đang đứng theo thứ tự hàng đang hiện (cột 2 vào ô bên phải).
  function fillDown(el, text) {
    const rows = visibleRows();
    const start = rows.findIndex(row => row.uid === Number(el.dataset.row));
    const period = form.periods.find(item => item.uid === Number(el.dataset.per));
    const tiers = el.dataset.tier === 'khach' ? ['khach', 'tt'] : ['tt'];
    const lines = splitLines(text);
    let count = 0;
    lines.forEach((cells, k) => {
      const row = rows[start + k];
      if (!row) return;
      tiers.forEach((tier, c) => { if (c < cells.length) setCell(row, period, tier, priceTidy(cells[c])); });
      count += 1;
    });
    rerender();
    setBar(count < lines.length ? 'bad' : 'ok', count < lines.length ? `Đã dán ${count} dòng; ${lines.length - count} dòng thừa vì hết hàng nơi đi. Thêm nơi đi rồi dán lại phần thừa.`
      : `Đã dán ${count} ô giá vào đợt ${periodLabel(period)}.`);
  }
  // Đổi giá từ ngày (Q6 của BANG-GIA-01): đợt còn dùng kết thúc ngày liền trước, cột mới chép giá của chúng để sửa.
  function newPeriod(text) {
    const iso = isoOf(text);
    const fail = message => { setBar('bad', message); $('.price-new-from')?.focus(); };
    if (!iso) { fail('Ngày giá mới chưa đúng dạng ngày/tháng/năm, ví dụ 01/11/2026.'); return; }
    const open = form.periods.filter(period => !String(period.to).trim() && isoOf(period.from));
    const latest = open.map(period => isoOf(period.from)).sort().at(-1);
    if (latest && latest >= iso) { fail(`Ngày giá mới phải sau ${dmy(latest)}.`); return; }
    const end = dmy(addDays(iso, -1));
    const period = { uid: nextUid++, from: dmy(iso), to: '', fresh: true, closes: open.map(item => item.uid) };
    const sources = [...open].sort((a, b) => isoOf(b.from).localeCompare(isoOf(a.from)));
    for (const row of form.rows) {
      const source = sources.find(item => hasPrice(form.cells.get(cellKey(row, item))));
      if (!source) continue;
      const cell = cellOf(row, source);
      for (const tier of TIERS) setCell(row, period, tier, cell[tier], cell[tier]);
    }
    for (const item of open) item.to = end;
    form.periods.push(period);
    bar = null;
    ui.side = 'period'; ui.period = period.uid;
    render();
    setBar('info', open.length ? `Đã thêm cột giá từ ${dmy(iso)}, chép giá đang dùng. Sửa ô nào, ô đó tô vàng.` : `Đã thêm cột giá từ ${dmy(iso)}. Gõ hoặc dán giá vào cột mới.`);
    const input = $(`input[data-per="${period.uid}"][data-tier="khach"]`);
    input?.focus();
    input?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }
  // Sửa ngày đợt ở khối phải; đợt mới thì ngày kết thúc của đợt nó đã đóng đi theo. Gõ/rời ô chỉ cập nhật tại chỗ
  // (không vẽ lại khi con trỏ đang sang ô kế bên); Enter, "Xong" hoặc đóng khối mới xếp lại cột theo ngày.
  function setPeriodDate(el, final, resort) {
    const period = form.periods.find(item => item.uid === ui.period);
    if (!period) return;
    if (final) el.value = dateTidy(el.value);
    period[el.dataset.pf] = el.value;
    if (el.dataset.pf === 'from' && period.fresh && isoOf(period.from)) {
      for (const item of form.periods) if (period.closes.includes(item.uid)) item.to = dmy(addDays(isoOf(period.from), -1));
    }
    if (resort) rerender(); else updateGrid();
  }

  const failText = result => result.error === 'NO_CHANGE' ? 'Bảng giá không có gì thay đổi.'
    : result.error === 'STALE_LEDGER' ? 'Sổ vừa thay đổi ở nơi khác nên chưa lưu. Chép lại các giá vừa sửa, đóng khung, tải lại sổ rồi sửa lại.'
      : result.message || 'Chưa lưu được bảng giá.';
  // Bước 1 của Lưu (BANG-GIA-05): kiểm tại trang, rồi hỏi server lưu thử (preview_price_table: chạy đúng lệnh lưu rồi hoàn tác)
  // để thấy trước chuyến nào đổi giá, tổng còn nợ đổi bao nhiêu. Trang không tự tính tiền.
  async function startReview() {
    if (sending) return;
    const errors = check();
    if (errors.size) {
      bar = null; renderBar();
      updateGrid(errors);
      $('.pm-goto')?.focus();
      return;
    }
    const body = { customer_id: customerId, expected_version: ctx.snapshot.version, price_table: payload() };
    review = { body, result: null, unknown: false };
    sending = true;
    render();
    let outcome;
    try { outcome = await post('/api/v7/price-table/preview', { ...body, idempotency_key: crypto.randomUUID() }); } catch { outcome = { ok: false, result: {} }; }
    sending = false;
    if (!review || review.body !== body) return;
    if (outcome.ok) review.result = outcome.result;
    else if (['NO_CHANGE', 'STALE_LEDGER'].includes(outcome.result.error) || /^(INVALID_PRICE_TABLE|PRICE_)/.test(outcome.result.error ?? '')) {
      review = null;
      render();
      setBar('bad', failText(outcome.result));
      return;
    } else review.unknown = true;   // máy chủ chưa tính được: vẫn cho xem bảng đổi gì và lưu, lưu xong báo từng chuyến như cũ
    render();
    $('.price-review-save')?.focus();
  }
  // Bước 2: lưu thật đúng bảng và phiên bản sổ đã xem; sổ đổi giữa chừng thì server trả STALE_LEDGER.
  async function save(button) {
    if (sending || !review) return;
    sending = true; button.disabled = true;
    let outcome;
    try {
      outcome = await post('/api/v7/price-table', { ...review.body, idempotency_key: crypto.randomUUID() });
    } catch {
      sending = false; button.disabled = false;
      review = null; render();
      setBar('bad', 'Chưa rõ đã lưu chưa. Đóng khung, tải lại sổ rồi mở Bảng giá để kiểm tra.');
      return;
    }
    sending = false; button.disabled = false;
    if (!outcome.ok) {
      review = null; render();
      setBar('bad', failText(outcome.result));
      return;
    }
    root.querySelector('.page-more')?.removeAttribute('open');   // menu ⋯ còn mở sẽ che thông báo trước → sau
    closeDialog();
    try { await api.read(); } catch { showNotice('Đã lưu bảng giá; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
    showNotice(savedNotice(outcome.result));
  }
  // Bảng giá đổi gì: so bảng đã lưu với bảng sắp gửi (chỉ là dữ liệu bảng, không phải tiền). Đợt mới thì so với đợt liền trước.
  function tableChanges(before, after) {
    const periods = table => new Map((table?.periods ?? []).map(item => [item.valid_from, item.valid_to ?? null]));
    const flat = table => {
      const map = new Map();
      for (const item of table?.periods ?? []) for (const rate of item.rates ?? []) map.set(`${item.valid_from}|${keyOf(rate.location)}|${keyOf(rate.destination)}|${rate.tier}`, String(rate.unit_price_vnd));
      return map;
    };
    const [old, now, oldRates, newRates] = [periods(before), periods(after), flat(before), flat(after)];
    const lines = [];
    for (const [from, to] of now) {
      if (!old.has(from)) lines.push(`Thêm đợt giá từ ${dmy(from)}${to ? ` đến ${dmy(to)}` : ''}.`);
      else if (old.get(from) !== to) lines.push(to ? `Đợt ${dmy(from)} kết thúc ngày ${dmy(to)}.` : `Đợt ${dmy(from)} dùng tiếp, bỏ ngày kết thúc.`);
    }
    for (const [from, to] of old) if (!now.has(from)) lines.push(`Bỏ đợt ${dmy(from)}${to ? ` – ${dmy(to)}` : ''}.`);
    const starts = [...now.keys()].sort();
    const rows = [];
    let same = 0;
    const byParts = (a, b) => { const [x, y] = [a.split('|'), b.split('|')]; return x.reduce((order, part, i) => order || part.localeCompare(y[i]), 0); };
    for (const key of [...new Set([...oldRates.keys(), ...newRates.keys()])].sort(byParts)) {
      const [from, kho, den, tier] = key.split('|');
      let was = oldRates.get(key) ?? null;
      const is = newRates.get(key) ?? null;
      if (!old.has(from) && now.has(from)) {   // đợt mới: so với đợt liền trước có giá của cùng nơi đi, nơi đến, loại giá
        was = null;
        for (const start of starts.filter(start => start < from).reverse()) if (newRates.has(`${start}|${kho}|${den}|${tier}`)) { was = newRates.get(`${start}|${kho}|${den}|${tier}`); break; }
      }
      if (was === is) { same += 1; continue; }
      rows.push({ kho, den, from, tier, was, is });
    }
    const ships = [new Set((before?.tt_shippers ?? []).map(keyOf)), new Set((after?.tt_shippers ?? []).map(keyOf))];
    const added = [...ships[1]].filter(name => !ships[0].has(name)), removed = [...ships[0]].filter(name => !ships[1].has(name));
    if (added.length) lines.push(`Thêm shipper áp giá TT: ${added.join(', ')}.`);
    if (removed.length) lines.push(`Bỏ shipper áp giá TT: ${removed.join(', ')}.`);
    return { lines, rows, same };
  }
  function renderReview() {
    const name = escape(live.customerName?.(customerId) ?? 'sổ khách');
    const result = review.result;
    const changes = tableChanges(original, review.body.price_table);
    const trips = tripsOf();
    const repriced = result?.repriced_trips ?? [];
    const delta = BigInt(result?.repriced_delta_vnd ?? 0);
    const signed = value => value > 0n ? `+${fmt(String(value))}` : value < 0n ? `−${fmt(String(-value))}` : '0';
    const diff = row => { const change = model.priceTableChange(row.was, row.is); return change == null ? '' : signed(change); };
    const tiles = result ? [
      [`${repriced.length} chuyến`, 'tự đổi sang giá mới'],
      [delta === 0n ? '0 đ' : `${signed(delta)} đ`, delta === 0n ? 'còn nợ của khách không đổi' : `còn nợ của khách ${delta > 0n ? 'tăng' : 'giảm'}`],
    ] : [];
    const kept = result ? [result.typed_trips ? `${result.typed_trips} chuyến giá gõ tay khác bảng` : '', result.locked_trips ? `${result.locked_trips} chuyến ở tháng khóa` : '',
      result.no_price_trips ? `${result.no_price_trips} chuyến bảng mới không còn giá` : ''].filter(Boolean) : [];
    const tripRows = repriced.map(item => {
      const trip = trips.get(item.trip_id) ?? {};
      return `<tr><td>${escape(item.container ?? trip.container ?? '')}</td><td>${trip.event_date ? escape(dateText(trip.event_date)) : ''}</td><td>${escape(trip.origin ?? '')}</td>
        <td>${escape(TIER[item.tier] ?? '')}</td><td class="num muted">${fmt(item.before_vnd)}</td><td class="num"><b>${fmt(item.after_vnd)}</b></td></tr>`;
    }).join('');
    const label = !result ? 'Lưu bảng giá' : repriced.length ? `Lưu và đổi giá ${repriced.length} chuyến` : 'Lưu bảng giá';
    const effects = review.unknown
      ? '<p class="pm-note">Chưa tính được trước chuyến nào đổi giá. Lưu xong, web báo từng chuyến giá cũ → mới như trước.</p>'
      : !result ? '<p class="pm-note" role="status">Đang tính chuyến đổi giá…</p>'
        : `<div class="rv-tiles">${tiles.map(([value, text]) => `<div class="rv-tile"><b>${escape(value)}</b><span>${escape(text)}</span></div>`).join('')}</div>
          ${kept.length ? `<p class="rv-kept"><b>Giữ nguyên giá:</b> ${escape(kept.join('; '))}.</p>` : ''}
          ${repriced.length ? `<div class="rv-list"><table><thead><tr><th>Số container</th><th>Ngày chuyến</th><th>Nơi đi</th><th>Loại giá</th><th class="num">Đang ghi</th><th class="num">Giá mới</th></tr></thead><tbody>${tripRows}</tbody></table></div>`
            : '<p class="pm-note">Không chuyến nào trong sổ đổi giá.</p>'}
          <p class="pm-note">${repriced.length ? 'Phiếu thu tự phân bổ lại theo nợ cũ trước.' : ''}${result.ready_count ? ` ${result.ready_count} chuyến chưa có giá sẽ điền được bằng nút "Điền giá theo bảng" sau khi lưu.` : ''}</p>`;
    dialog.innerHTML = `<div class="price-table-panel price-review"><header><h2 class="price-grid-title" tabindex="-1">Xem lại trước khi lưu bảng giá <span class="pm-book">${name}</span></h2><span class="price-grow"></span>
        <button type="button" class="price-review-back">Quay lại sửa</button><button type="button" class="price-review-save primary"${result || review.unknown ? '' : ' disabled'}>${escape(label)}</button></header>
      <div class="rv-body"><section class="rv-card rv-table" aria-label="Bảng giá thay đổi gì"><h3>Bảng giá thay đổi gì</h3>
        ${changes.lines.map(line => `<p>${escape(line)}</p>`).join('')}
        ${changes.rows.length ? `<div class="rv-list"><table><thead><tr><th>Nơi đi → nơi đến</th><th class="num">Trước</th><th class="num">Sau</th><th class="num">Đổi</th></tr></thead><tbody>${changes.rows.map((row, index) =>
          `${index && changes.rows[index - 1].from === row.from ? '' : `<tr class="rv-group"><td colspan="4">Đợt từ ${escape(dmy(row.from))}</td></tr>`}<tr><td><b>${escape(row.kho)}</b>${row.den ? ` → ${escape(row.den)}` : ''} <small>${escape(TIER[row.tier])}</small></td>
            <td class="num muted">${row.was == null ? '—' : fmt(row.was)}</td><td class="num">${row.is == null ? '—' : `<b>${fmt(row.is)}</b>`}</td><td class="num">${escape(diff(row))}</td></tr>`).join('')}</tbody></table></div>` : '<p class="pm-note">Không giá nào đổi.</p>'}
        ${changes.same ? `<p class="pm-note">${changes.same} giá giữ như cũ hoặc như đợt trước.</p>` : ''}</section>
      <section class="rv-card rv-trips" aria-label="Chuyến trong sổ đổi theo"><h3>Chuyến trong sổ đổi theo</h3>${effects}</section></div></div>`;
  }
  // BANG-GIA-02: server đã đổi giá ngay trong lệnh lưu; thao tác đụng tiền phải cho thấy trước → sau.
  function savedNotice(result) {
    const trips = result.repriced_trips ?? [], locked = result.locked_trips ?? 0, noPrice = result.no_price_trips ?? 0;
    const parts = ['Đã lưu bảng giá.'];
    if (trips.length) {
      const shown = trips.slice(0, 3).map(trip => `${trip.container} ${fmt(trip.before_vnd)} → ${fmt(trip.after_vnd)}`).join('; ');
      const more = trips.length > 3 ? ` và ${trips.length - 3} chuyến khác (xem Lịch sử)` : '';
      const delta = BigInt(result.repriced_delta_vnd ?? 0);
      parts.push(`Đã đổi giá ${trips.length} chuyến: ${shown}${more}.`,
        delta === 0n ? 'Tổng tiền các chuyến không đổi.' : `Tổng tiền các chuyến ${delta > 0n ? 'tăng' : 'giảm'} ${fmt(String(delta < 0n ? -delta : delta))} đ.`);
    }
    if (locked) parts.push(`${locked} chuyến ở tháng khóa chưa đổi: mở khóa tháng rồi bấm "Áp lại giá mới".`);
    if (noPrice) parts.push(`${noPrice} chuyến không còn giá trong bảng mới, giữ giá đang ghi.`);
    return parts.join(' ');
  }

  const rowOf = el => form.rows.find(row => row.uid === Number(el.dataset.row));
  const periodOf = el => form.periods.find(period => period.uid === Number(el.dataset.per));
  dialog.addEventListener('input', event => {
    const el = event.target;
    if (!form) return;
    if (el.dataset.tier) { setCell(rowOf(el), periodOf(el), el.dataset.tier, el.value); updateGrid(); }
    else if (el.dataset.f) { rowOf(el)[el.dataset.f] = el.value; updateGrid(); }
    else if (el.dataset.pf) setPeriodDate(el, false, false);
    else if (el.matches('.pm-find')) {
      ui.filter = el.value;
      const scroll = $('.pm-scroll');
      if (scroll) { scroll.innerHTML = grid(check()); updateGrid(); }
    }
  });
  dialog.addEventListener('change', event => {
    const el = event.target;
    if (!form) return;
    if (el.dataset.tier) { el.value = priceTidy(el.value); setCell(rowOf(el), periodOf(el), el.dataset.tier, el.value); updateGrid(); }
    else if (el.dataset.f) {
      const row = rowOf(el);
      el.value = keyOf(el.value);
      // Đổi tên nơi đi thì tên khác đã lưu đi theo tên mới.
      if (el.dataset.f === 'kho' && row.kho !== el.value && form.aliases.has(keyOf(row.kho)) && !form.rows.some(item => item !== row && keyOf(item.kho) === keyOf(row.kho))) {
        form.aliases.set(el.value, form.aliases.get(keyOf(row.kho)));
      }
      row[el.dataset.f] = el.value;
      updateGrid();
    } else if (el.dataset.pf) setPeriodDate(el, true, false);
  });
  dialog.addEventListener('paste', event => {
    const el = event.target;
    const text = event.clipboardData?.getData('text/plain') ?? '';
    if (!form || loading || failed) return;
    if (el.matches?.('.pm-paste')) { event.preventDefault(); importFlat(text); return; }
    if (!/[\t\n]/.test(text.trim())) return;
    if (el.dataset?.tier || el.dataset?.f) {
      event.preventDefault();
      if (looksFlat(text)) importFlat(text);
      else if (el.dataset.tier) fillDown(el, text);
      else {
        // Dán cột tên vào ô Nơi đi: điền xuống, cột 2 là Nơi đến; hết hàng thì thêm hàng.
        const rows = visibleRows();
        let at = rows.findIndex(row => row.uid === Number(el.dataset.row));
        for (const cells of splitLines(text)) {
          let row = rows[at];
          if (!row) { row = { uid: nextUid++, kho: '', den: '' }; form.rows.push(row); }
          if (el.dataset.f === 'kho') { row.kho = keyOf(cells[0]); if (cells.length > 1) row.den = keyOf(cells[1]); } else row.den = keyOf(cells[0]);
          at += 1;
        }
        rerender();
      }
    } else if (el.id === 'pm-ship-new') {
      event.preventDefault();
      const added = addShips(text.split(/\r?\n/).map(line => line.split('\t')[0]));
      render();
      setBar('ok', `Đã dán ${added} shipper áp giá TT.`);
    }
  });
  function move(el, step) {
    const rows = visibleRows();
    const at = rows.findIndex(row => row.uid === Number(el.dataset.row));
    const next = rows[at + step];
    if (!next) return false;
    const selector = el.dataset.tier ? `input[data-row="${next.uid}"][data-per="${el.dataset.per}"][data-tier="${el.dataset.tier}"]` : `input[data-row="${next.uid}"][data-f="${el.dataset.f}"]`;
    el.dispatchEvent(new Event('change', { bubbles: true }));
    $(selector)?.focus();
    return true;
  }
  dialog.addEventListener('keydown', event => {
    const el = event.target;
    const plain = !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey;
    if ((el.dataset.tier || el.dataset.f) && plain && ['Enter', 'ArrowDown', 'ArrowUp'].includes(event.key)) {
      // SO-GON-04 (L5): Enter và mũi tên xuống sang ô cùng cột hàng dưới, mũi tên lên sang hàng trên; ghi ô đang đứng như Enter.
      event.preventDefault();
      if (!move(el, event.key === 'ArrowUp' ? -1 : 1) && event.key === 'Enter') el.dispatchEvent(new Event('change', { bubbles: true }));
    } else if (event.key === 'Enter' && el.matches('.price-new-from')) { event.preventDefault(); newPeriod(el.value); }
    else if (event.key === 'Enter' && el.dataset.pf) { event.preventDefault(); setPeriodDate(el, true, true); }
    else if (event.key === 'Enter' && el.id === 'pm-ship-new') { event.preventDefault(); $('.price-ship-add')?.click(); }
  });
  dialog.addEventListener('click', event => {
    if (!form) return;
    if (event.target === dialog) { if (!review) requestClose(); return; }
    const button = event.target.closest('button');
    if (!button) return;
    if (button.matches('.price-table-save')) { bar = null; startReview(); }
    else if (button.matches('.price-review-save')) save(button);
    else if (button.matches('.price-review-back')) { review = null; render(); $('.price-table-save')?.focus(); }
    else if (button.matches('.price-table-close')) requestClose();
    else if (button.matches('.price-discard')) closeDialog();
    else if (button.matches('.price-stay,.price-msg-close')) { bar = null; renderBar(); }
    else if (loading || failed) return;
    else if (button.matches('.price-paste-open')) { ui.side = ui.side === 'paste' ? 'ship' : 'paste'; render(); $('#pm-paste-side')?.focus(); }
    else if (button.matches('.price-new-open')) { ui.side = 'new'; ui.period = null; render(); $('.price-new-from')?.focus(); }
    else if (button.matches('.price-new-ok')) newPeriod($('.price-new-from')?.value);
    else if (button.matches('.price-new-cancel,.pm-side-close')) { ui.side = 'ship'; ui.period = null; render(); }
    else if (button.matches('.pm-period')) { openPeriod(Number(button.dataset.per)); $('#pm-from')?.focus(); }
    else if (button.matches('.pm-older')) { ui.showAll = !ui.showAll; render(); }
    else if (button.matches('.pm-goto')) goTo(errorList[Number(button.dataset.i)]);
    else if (button.matches('.price-row-add')) {
      ui.filter = '';
      const row = { uid: nextUid++, kho: '', den: '' };
      form.rows.push(row);
      render();
      $(`input[data-row="${row.uid}"][data-f="kho"]`)?.focus();
    } else if (button.matches('.price-outside-add')) {
      const added = outsideOrigins().map(([name]) => ({ uid: nextUid++, kho: name, den: '' }));
      form.rows.push(...added);
      ui.filter = '';
      render();
      setBar('info', `Đã thêm ${added.length} hàng nơi đi, chưa có giá. Gõ giá vào cột đợt cần dùng rồi bấm Xem lại và lưu.`);
      const latest = sorted().at(-1);
      const input = latest && $(`input[data-row="${added[0]?.uid}"][data-per="${latest.uid}"][data-tier="khach"]`);
      (input ?? $(`input[data-row="${added[0]?.uid}"][data-f="kho"]`))?.focus();
      input?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    } else if (button.matches('.price-row-drop')) {
      const uid = Number(button.dataset.row);
      form.rows = form.rows.filter(row => row.uid !== uid);
      render();
    } else if (button.matches('.price-period-drop')) {
      const uid = Number(button.dataset.per);
      const period = form.periods.find(item => item.uid === uid);
      // Bỏ đợt mới vừa thêm thì đợt nó đã đóng lại còn dùng như trước.
      if (period?.fresh) for (const item of form.periods) if (period.closes.includes(item.uid)) item.to = '';
      form.periods = form.periods.filter(item => item.uid !== uid);
      ui.side = 'ship'; ui.period = null;
      render();
      setBar('info', `Đã bỏ đợt ${period ? periodLabel(period) : ''}. Bảng giá chỉ đổi khi bấm Lưu.`);
    } else if (button.matches('.price-ship-add')) {
      const input = $('#pm-ship-new');
      const added = addShips([input?.value ?? '']);
      render();
      if (!added && input?.value.trim()) setBar('bad', 'Shipper này đã có trong danh sách giá TT.');
      $('#pm-ship-new')?.focus();
    } else if (button.matches('.price-ship-move')) { addShips([button.dataset.name]); render(); }
    else if (button.matches('.price-ship-drop')) { form.ships.splice(Number(button.dataset.s), 1); render(); }
  });
  // Esc: đóng câu hỏi đang hiện, rồi khối đang mở bên phải, rồi mới đóng khung (hỏi lưu nếu còn thay đổi).
  if (typeof document.addEventListener === 'function') document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !form) return;
    if (review) { review = null; render(); } else if (bar?.kind === 'ask') { bar = null; renderBar(); } else if (ui.side !== 'ship' && !loading && !failed) { ui.side = 'ship'; ui.period = null; render(); } else requestClose();
  });


  root.addEventListener('click', event => {
    const button = event.target.closest('.price-table-open,.price-table-apply,.price-reapply-open,.price-table-cancel,.price-table-write');
    if (!button || button.disabled || !ctx.snapshot) return;
    if (button.matches('.price-table-open')) { openDialog(); return; }
    if (button.matches('.price-table-write')) { writeApply(button); return; }
    if (button.matches('.price-table-cancel')) confirm = null;
    else {
      const kind = button.matches('.price-table-apply') ? 'ready' : 'reapply';
      const ids = confirmIds(kind);
      confirm = ids.length ? { kind, ids } : null;
    }
    ctx.redraw();
    root.querySelector(confirm ? '.price-table-write' : '.price-table-open')?.focus();
  });
};
