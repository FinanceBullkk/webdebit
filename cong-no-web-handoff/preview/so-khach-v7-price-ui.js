/* Sổ khách V7 bản live — Bảng giá theo ngày hiệu lực (BANG-GIA-01, specs/v7-bang-gia-hieu-luc.md, giai đoạn 2, giao diện lưới).
 * Khung Bảng giá là lưới giống vùng bảng giá trên Sheet (Từ ngày · Đến ngày · Nơi đi · Giá khách · Giá TT, cột Shipper áp giá TT),
 * nút "Điền giá theo bảng (N chuyến)" và chữ nhỏ ở ô Đơn giá. Server tra giá và ghi; trang không tự tính giá hay cộng tiền.
 * Nạp trước so-khach-v7-ui.js, dùng chung phạm vi của initLive qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).price = ctx => {
  'use strict';
  const { root, model, api, live, customerId, escape, fmt, dateText, monthKey, monthLabel, showNotice } = ctx;
  const TIER = { khach: 'giá khách', tt: 'giá TT' };
  const FIELDS = ['from', 'to', 'kho', 'khach', 'tt'];
  const LABELS = ['Từ ngày', 'Đến ngày', 'Nơi đi', 'Giá khách', 'Giá TT'];
  let status = null;            // GET /api/v7/price-table/status của phiên bản sổ đang vẽ
  let loadedVersion = null;
  let confirm = null;           // { kind: 'ready'|'reapply', ids }
  let sending = false;
  let form = null;              // bảng giá đang sửa trong khung; null = khung đóng
  let savedShape = '';
  let bar = null;               // { kind: 'info'|'ok'|'bad', text } | { kind: 'ask' } | { kind: 'new' }
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
      ctx.redraw();
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

  ctx.priceButtons = active => {
    if (!active) return '';
    const ready = status?.ready_count ?? 0;
    return `<button class="price-table-open" aria-haspopup="dialog">Bảng giá</button>`
      + (ready && !confirm ? `<button class="price-table-apply">Điền giá theo bảng (${ready} chuyến)</button>` : '');
  };

  // Sau khi vẽ sổ: chữ nhỏ ở ô Đơn giá và khung hỏi lại dưới đầu sổ.
  const REASONS = { UNKNOWN_LOCATION: ['ngoài bảng giá', 'Nơi đi chưa có trong bảng giá'], NO_PERIOD: ['ngoài ngày có giá', 'Bảng giá chưa có giá cho ngày chuyến này'],
    NO_DATE: ['thiếu ngày', 'Chuyến thiếu ngày nên chưa tra được giá'], NO_ORIGIN: ['thiếu nơi đi', 'Chuyến thiếu nơi đi nên chưa tra được giá'] };
  ctx.priceAfterRender = active => {
    if (!active || !status) return;
    for (const row of status.trips) {
      // Ô Đơn giá: vị trí đổi khi sổ không có cột Shipper (audit UX 31/10/2026).
      const cell = root.querySelector(`[data-row="trip-${row.trip_id}"]`)?.children[ctx.columns.unitPrice()];
      if (!cell) continue;
      const lookup = row.lookup ?? {};
      let note = '', cls = 'price-hint', title = '';
      if (row.ready) { note = `bảng ${fmt(lookup.unit_price_vnd)}`; cls += ' price-ready'; title = `Theo bảng: ${fmt(lookup.unit_price_vnd)} (${TIER[lookup.tier] ?? ''})`; }
      else if (row.differs) { note = `bảng ${fmt(lookup.unit_price_vnd)}`; cls += ' price-diff'; title = `Khác bảng giá: bảng ${fmt(lookup.unit_price_vnd)} (${TIER[lookup.tier] ?? ''})`; }
      else if (row.from_table) { note = 'theo bảng'; title = `Giá ghi theo bảng (${TIER[lookup.tier] ?? ''})`; }
      else if (row.unit_price_vnd == null && lookup.reason === 'NO_RATE') { note = `thiếu ${TIER[lookup.tier] ?? 'giá'}`; title = `Bảng giá có ${lookup.location ?? 'nơi đi này'} nhưng chưa có ${TIER[lookup.tier] ?? 'giá'}`; }
      else if (row.unit_price_vnd == null && REASONS[lookup.reason]) [note, title] = REASONS[lookup.reason];
      if (!note) continue;
      cell.insertAdjacentHTML('beforeend', `<small class="${cls}">${escape(note)}</small>`);
      if (title) cell.title = title;
      if (row.differs) cell.classList.add('price-differs');
    }
    const reapply = confirmIds('reapply').length;
    const strip = reapply && confirm?.kind !== 'reapply'
      ? `<div class="price-strip">Bảng giá đã đổi: <strong>${reapply}</strong> chuyến đang ghi theo giá cũ của bảng. <button type="button" class="price-reapply-open">Áp lại giá mới</button></div>` : '';
    root.querySelector('.book-head')?.insertAdjacentHTML('afterend', strip + confirmPanel());
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
      return `<tr><td>${escape(trip.container ?? '')}</td><td>${trip.event_date ? escape(dateText(trip.event_date)) : ''}</td><td>${escape(trip.origin ?? '')}</td><td>${escape(trip.shipper || '–')}</td>
        ${confirm.kind === 'reapply' ? `<td class="num">${fmt(trip.unit_price_vnd)}</td>` : ''}<td class="num">${fmt(lookup.unit_price_vnd)}</td><td>${TIER[lookup.tier] ?? ''}</td></tr>`;
    }).join('');
    return `<div class="price-panel confirm" role="region" aria-label="Xác nhận điền giá theo bảng"><p>${head} Phiếu thu tự phân bổ lại theo nợ cũ trước.</p>
      <div class="price-confirm-list"><table><thead><tr><th>Số container</th><th>Ngày chuyến</th><th>Nơi đi</th><th>Shipper</th>${confirm.kind === 'reapply' ? '<th class="num">Đang ghi</th>' : ''}<th class="num">Đơn giá theo bảng</th><th>Loại giá</th></tr></thead><tbody>${rows}</tbody></table></div>
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

  // ---- Khung Bảng giá: lưới như Sheet ----
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
  function tidy(field, value) {
    const text = String(value ?? '').trim();
    if (field === 'from' || field === 'to') { const iso = isoOf(text); return iso ? dmy(iso) : text; }
    if (field === 'khach' || field === 'tt') { try { const price = priceOf(text); return price == null ? text : fmt(price); } catch { return text; } }
    return field === 'kho' ? keyOf(text) : text;
  }
  const blankRow = () => ({ uid: nextUid++, from: '', to: '', kho: '', khach: '', tt: '', fresh: false });
  const filled = row => FIELDS.some(field => String(row[field]).trim());
  // Luôn còn 3 hàng trống cuối lưới giá và 2 ô trống cuối cột shipper (như lưới nhập chuyến).
  function pad() {
    let empty = 0;
    for (let i = form.rows.length - 1; i >= 0 && !filled(form.rows[i]); i -= 1) empty += 1;
    for (; empty < 3; empty += 1) form.rows.push(blankRow());
    empty = 0;
    for (let i = form.ships.length - 1; i >= 0 && !form.ships[i].name.trim(); i -= 1) empty += 1;
    for (; empty < 2; empty += 1) form.ships.push({ uid: nextUid++, name: '' });
  }

  function fromServer(table) {
    const aliases = new Map((table?.locations ?? []).map(item => [keyOf(item.name), item.aliases ?? []]));
    const order = new Map((table?.locations ?? []).map((item, index) => [keyOf(item.name), index]));
    const rows = [];
    for (const period of [...(table?.periods ?? [])].sort((a, b) => String(a.valid_from).localeCompare(String(b.valid_from)))) {
      const byLocation = new Map();
      for (const rate of period.rates ?? []) {
        const key = keyOf(rate.location);
        if (!byLocation.has(key)) byLocation.set(key, { uid: nextUid++, from: dmy(period.valid_from), to: dmy(period.valid_to), kho: rate.location, khach: '', tt: '', fresh: false });
        byLocation.get(key)[rate.tier] = fmt(rate.unit_price_vnd);
      }
      rows.push(...[...byLocation.entries()].sort(([a], [b]) => (order.get(a) ?? 0) - (order.get(b) ?? 0)).map(([, row]) => row));
    }
    const result = { rows, ships: (table?.tt_shippers ?? []).map(name => ({ uid: nextUid++, name })), aliases };
    return result;
  }
  const shapeOf = value => JSON.stringify([value.rows.filter(filled).map(row => FIELDS.map(field => tidy(field, row[field]))),
    [...new Set(value.ships.map(ship => keyOf(ship.name)).filter(Boolean))].sort()]);

  // Kiểm cả bảng như server (ngày, giá, trùng ngày cùng nơi đi và cùng loại giá); lỗi theo dòng, câu ngắn hiện ở cột Tình trạng.
  function check() {
    const errors = new Map();
    const flag = (row, field, text) => { const item = errors.get(row.uid) ?? { fields: new Set(), text }; item.fields.add(field); errors.set(row.uid, item); };
    const good = [];
    form.rows.forEach((row, index) => {
      if (!filled(row)) return;
      const from = isoOf(row.from);
      const to = String(row.to).trim() ? isoOf(row.to) : '';
      if (!String(row.from).trim()) flag(row, 'from', 'Thiếu Từ ngày');
      else if (!from) flag(row, 'from', 'Từ ngày sai');
      if (to === null) flag(row, 'to', 'Đến ngày sai');
      else if (from && to && to < from) flag(row, 'to', 'Đến trước Từ ngày');
      if (!keyOf(row.kho)) flag(row, 'kho', 'Thiếu nơi đi');
      if (!priceOk(row.khach)) flag(row, 'khach', 'Giá khách sai');
      if (!priceOk(row.tt)) flag(row, 'tt', 'Giá TT sai');
      if (!errors.has(row.uid)) good.push({ row, n: index + 1, from, to, key: keyOf(row.kho), khach: priceOf(row.khach), tt: priceOf(row.tt) });
    });
    for (let i = 0; i < good.length; i += 1) {
      for (let j = i + 1; j < good.length; j += 1) {
        const [a, b] = [good[i], good[j]];
        const sameTier = (a.khach != null && b.khach != null) || (a.tt != null && b.tt != null) || (a.khach == null && a.tt == null && b.khach == null && b.tt == null);
        if (a.key !== b.key || !sameTier || !(a.from <= (b.to || '9999-12-31') && b.from <= (a.to || '9999-12-31'))) continue;
        flag(b.row, 'from', `Trùng ngày dòng ${a.n}`); flag(b.row, 'to', '');
        flag(a.row, 'from', `Trùng ngày dòng ${b.n}`); flag(a.row, 'to', '');
      }
    }
    return { errors, good };
  }
  function rowState(row, errors) {
    if (!filled(row)) return ['none', ''];
    const error = errors.get(row.uid);
    if (error) return ['bad', error.text];
    const from = isoOf(row.from);
    const to = String(row.to).trim() ? isoOf(row.to) : '';
    const now = today();
    if (from > now) return ['future', 'Sắp áp dụng'];
    if (to && to < now) return ['old', 'Hết hạn'];
    return ['now', 'Đang dùng'];
  }

  async function openDialog() {
    form = fromServer(null);
    loading = true;
    bar = { kind: 'info', text: 'Đang đọc bảng giá…' };
    savedShape = shapeOf({ rows: [], ships: [] });
    dialog.hidden = false;
    render();
    try {
      const response = await fetch(`/api/v7/price-table?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data?.price_table) throw Error(data?.message || 'Không đọc được bảng giá.');
      form = fromServer(data.price_table);
      bookShippers = Array.isArray(data.book_shippers) ? data.book_shippers : [];
      savedShape = shapeOf(form);
      bar = null;
    } catch (error) { bar = { kind: 'bad', text: error.message || 'Không đọc được bảng giá.' }; loading = false; render(); dialog.querySelector('.price-body')?.remove(); dialog.querySelector('.price-table-save')?.remove(); dialog.querySelector('.price-new-open')?.remove(); return; }
    loading = false;
    render();
    $('.price-grid-title')?.focus();
  }
  function closeDialog() { form = null; bar = null; loading = false; dialog.hidden = true; dialog.innerHTML = ''; root.querySelector('.price-table-open')?.focus(); ctx.redraw(); }
  const dirty = () => form && shapeOf(form) !== savedShape;
  function requestClose() {
    if (dirty()) { bar = { kind: 'ask' }; renderBar(); $('.price-bar .primary')?.focus(); return; }
    closeDialog();
  }
  const shipCount = name => bookShippers.find(item => keyOf(item.name) === keyOf(name))?.trip_count ?? 0;
  const shipNote = name => { if (!String(name).trim()) return ''; const count = shipCount(name); return `<span class="price-ship-count${count ? '' : ' none'}">${count ? `${count} chuyến` : 'chưa có chuyến'}</span>`; };

  function render() {
    if (!form) return;
    if (loading) {
      dialog.innerHTML = `<div class="price-table-panel"><header><h2 class="price-grid-title" tabindex="-1">Bảng giá · ${escape(live.customerName?.(customerId) ?? 'sổ khách')}</h2><span class="price-grow"></span><button type="button" class="price-table-close">Đóng</button></header><div class="price-bar"></div></div>`;
      renderBar();
      return;
    }
    pad();
    const { errors } = check();
    const hasRows = form.rows.some(filled);
    const empty = !hasRows && !form.ships.some(ship => ship.name.trim());
    const rows = form.rows.map((row, r) => {
      const error = errors.get(row.uid);
      const [state, text] = rowState(row, errors);
      return `<tr data-uid="${row.uid}" class="${row.fresh ? 'fresh' : ''}${state === 'old' ? ' old' : ''}"><td class="rn">${r + 1}</td>${FIELDS.map((field, c) =>
        `<td data-f="${field}" class="${error?.fields.has(field) ? 'bad' : ''}"><input data-r="${r}" data-c="${c}" class="${c >= 3 ? 'num' : ''}" value="${escape(row[field])}" ${c >= 3 && filled(row) ? 'placeholder="–"' : ''} aria-label="${LABELS[c]} dòng ${r + 1}" autocomplete="off" spellcheck="false"></td>`).join('')}
        <td class="st st-${state}">${escape(text)}</td><td class="xc">${filled(row) ? `<button type="button" class="price-row-drop" data-r="${r}" aria-label="Bỏ dòng ${r + 1}">×</button>` : ''}</td></tr>`;
    }).join('');
    const ships = form.ships.map((ship, s) => `<tr><td class="ship-cell"><input data-s="${s}" value="${escape(ship.name)}" list="price-ship-list" aria-label="Shipper áp giá TT dòng ${s + 1}" autocomplete="off" spellcheck="false">${shipNote(ship.name)}</td>
      <td class="xc">${ship.name.trim() ? `<button type="button" class="price-ship-drop" data-s="${s}" aria-label="Bỏ shipper ${escape(ship.name)}">×</button>` : ''}</td></tr>`).join('');
    const help = empty ? `<div class="price-help"><p>Trên Sheet, bôi đen vùng bảng giá như hình rồi Ctrl+C. Bấm vào ô dòng 1 bên dưới, Ctrl+V.</p>
      <table class="price-sheet" aria-hidden="true"><tr><td class="s">EFFECTIVE FROM</td><td class="s">EFFECTIVE TO</td><td class="s">LOCATION</td><td class="s">… PRICE</td><td class="s r">TT PRICE</td><td class="g"></td><td class="o">SHIPPER ÁP GIÁ TT</td></tr>
      <tr><td class="s">15/09/2026</td><td class="s">09/10/2026</td><td class="s">LONG AN</td><td class="s n">58,000,000</td><td class="s r n">72,000,000</td><td class="g"></td><td class="o">TÊN SHIPPER</td></tr>
      <tr><td class="s">10/10/2026</td><td class="s"></td><td class="s">LONG AN</td><td class="s n">58,000,000</td><td class="s r n">66,000,000</td><td class="g"></td><td class="o"></td></tr></table></div>` : '';
    dialog.innerHTML = `<div class="price-table-panel"><header><h2 class="price-grid-title" tabindex="-1">Bảng giá · ${escape(live.customerName?.(customerId) ?? 'sổ khách')}</h2><span class="price-dirty" hidden>Chưa lưu</span><span class="price-grow"></span>
        ${hasRows ? '<button type="button" class="price-new-open">Đổi giá từ ngày…</button>' : ''}<button type="button" class="price-table-save primary">Lưu bảng giá</button><button type="button" class="price-table-close">Đóng</button></header>
      <div class="price-bar"></div>
      <div class="price-body">${help}<div class="price-grids">
        <div><p class="price-hint-line">Dán từ Sheet vào ô bất kỳ của hàng trống, hoặc gõ tay. Ô giá để trống là chưa có giá.</p>
          <table class="price-grid price-grid-main"><thead><tr><th class="rn"></th><th class="w-date">Từ ngày</th><th class="w-date">Đến ngày</th><th class="w-kho">Nơi đi</th><th class="num w-price">Giá khách</th><th class="num w-price">Giá TT</th><th class="w-st">Tình trạng</th><th class="xc"></th></tr></thead><tbody>${rows}</tbody></table></div>
        <div><p class="price-hint-line">&nbsp;</p><table class="price-grid price-grid-ship"><thead><tr><th class="w-ship">Shipper áp giá TT</th><th class="xc"></th></tr></thead><tbody>${ships}</tbody></table>
          <p class="price-ship-note">Shipper không có trong cột này lấy giá khách.</p></div>
      </div></div></div>
      <datalist id="price-ship-list">${bookShippers.map(item => `<option value="${escape(item.name)}">`).join('')}</datalist>`;
    renderBar();
    updateDirty();
  }
  function renderBar() {
    const box = $('.price-bar');
    if (!box) return;
    if (bar?.kind === 'ask') box.innerHTML = `<div class="price-msg ask" role="alert"><span>Bảng giá có thay đổi chưa lưu.</span><button type="button" class="price-table-save primary">Lưu</button><button type="button" class="price-discard">Bỏ thay đổi</button><button type="button" class="price-stay">Ở lại</button></div>`;
    else if (bar?.kind === 'new') box.innerHTML = `<div class="price-msg form"><label for="price-new-from">Giá mới áp dụng từ ngày</label><input id="price-new-from" class="price-new-from" placeholder="dd/mm/yyyy" inputmode="numeric" autocomplete="off">
      <button type="button" class="price-new-ok primary">Thêm dòng giá mới</button><button type="button" class="price-new-cancel">Thôi</button></div>`;
    else box.innerHTML = bar ? `<div class="price-msg ${bar.kind}" role="${bar.kind === 'bad' ? 'alert' : 'status'}"><span>${escape(bar.text)}</span><button type="button" class="price-msg-close">Đóng</button></div>` : '';
  }
  const setBar = (kind, text) => { bar = { kind, text }; renderBar(); };
  function updateDirty() { const chip = $('.price-dirty'); if (chip) chip.hidden = !dirty(); }
  // Đang gõ: tô ô sai và cập nhật cột Tình trạng tại chỗ, không vẽ lại ô nhập.
  function updateGrid() {
    const { errors } = check();
    for (const row of form.rows) {
      const tr = dialog.querySelector(`tr[data-uid="${row.uid}"]`);
      if (!tr) continue;
      const error = errors.get(row.uid);
      for (const td of tr.querySelectorAll('td[data-f]')) td.classList.toggle('bad', Boolean(error?.fields.has(td.dataset.f)));
      const [state, text] = rowState(row, errors);
      const cell = tr.querySelector('td.st');
      cell.className = `st st-${state}`;
      cell.textContent = text;
      tr.classList.toggle('old', state === 'old');
    }
    updateDirty();
  }
  function addShips(names) {
    let added = 0;
    for (const name of names) {
      const key = keyOf(name);
      if (!key || /shipper/i.test(key) || form.ships.some(ship => keyOf(ship.name) === key)) continue;
      const slot = form.ships.find(ship => !ship.name.trim());
      if (slot) slot.name = key; else form.ships.push({ uid: nextUid++, name: key });
      added += 1;
    }
    return added;
  }
  // Dán khối từ Sheet bắt đầu tại ô (r, c): 5 cột giá; cột thứ 7 tính từ Từ ngày (sau một cột trống) là shipper áp giá TT. Dòng tiêu đề tự bỏ.
  function pasteBlock(r0, c0, text) {
    const lines = String(text).replace(/\r\n?/g, '\n').replace(/\n+$/, '').split('\n').map(line => line.split('\t').map(cell => cell.trim()));
    const names = [];
    let r = r0, count = 0;
    for (const cells of lines) {
      if (cells[6 - c0]) names.push(cells[6 - c0]);
      if (c0 === 0 && cells[0] && !/\d/.test(cells[0])) continue;
      const values = cells.slice(0, 5 - c0);
      if (!values.some(Boolean)) continue;
      while (form.rows.length <= r) form.rows.push(blankRow());
      values.forEach((value, k) => { form.rows[r][FIELDS[c0 + k]] = tidy(FIELDS[c0 + k], value); });
      r += 1; count += 1;
    }
    const added = addShips(names);
    render();
    const parts = [count ? `${count} dòng giá` : '', added ? `${added} shipper áp giá TT` : ''].filter(Boolean);
    if (parts.length) setBar('ok', `Đã dán ${parts.join(' và ')}. Kiểm lại rồi bấm Lưu bảng giá.`);
    else setBar('bad', 'Không thấy dòng giá nào. Trên Sheet chọn từ cột EFFECTIVE FROM tới TT PRICE rồi dán lại.');
    $(`input[data-r="${r0}"][data-c="${c0}"]`)?.focus();
  }
  function newPeriod(text) {
    const iso = isoOf(text);
    if (!iso) { setBar('bad', 'Ngày giá mới chưa đúng dạng ngày/tháng/năm, ví dụ 01/11/2026. Bấm "Đổi giá từ ngày…" để nhập lại.'); return; }
    const current = form.rows.filter(row => filled(row) && !String(row.to).trim() && isoOf(row.from));
    if (!current.length) { setBar('bad', 'Không có dòng giá nào đang dùng (Đến ngày để trống) để chép.'); return; }
    const latest = current.map(row => isoOf(row.from)).sort().at(-1);
    if (latest >= iso) { setBar('bad', `Ngày giá mới phải sau ${dmy(latest)}.`); return; }
    // Q6 (BANG-GIA-01): giá đang dùng kết thúc ngày liền trước; dòng mới chép giá cũ để sửa.
    const end = dmy(addDays(iso, -1));
    const copies = current.map(row => ({ ...row, uid: nextUid++, from: dmy(iso), to: '', fresh: true }));
    for (const row of current) row.to = end;
    let at = form.rows.length;
    while (at > 0 && !filled(form.rows[at - 1])) at -= 1;
    form.rows.splice(at, 0, ...copies);
    bar = null;
    render();
    setBar('info', `Đã thêm ${copies.length} dòng giá từ ${dmy(iso)} (tô vàng), giá chép từ giá cũ. Giá cũ dùng tới ${end}. Sửa giá rồi bấm Lưu bảng giá.`);
    const input = $(`input[data-r="${at}"][data-c="3"]`);
    input?.focus();
    input?.scrollIntoView?.({ block: 'center' });
  }
  // Lưới → bảng gửi server: dòng cùng Từ ngày/Đến ngày gộp thành một đợt; tên khác của nơi đi giữ như đã lưu.
  function payload(good) {
    const locations = new Map(), periods = new Map();
    for (const item of good) {
      if (!locations.has(item.key)) locations.set(item.key, { name: item.key, aliases: form.aliases.get(item.key) ?? [] });
      const periodKey = `${item.from}|${item.to}`;
      if (!periods.has(periodKey)) periods.set(periodKey, { valid_from: item.from, valid_to: item.to || null, rates: [] });
      for (const tier of ['khach', 'tt']) if (item[tier] != null) periods.get(periodKey).rates.push({ location: item.key, tier, unit_price_vnd: item[tier] });
    }
    return { tt_shippers: [...new Set(form.ships.map(ship => keyOf(ship.name)).filter(Boolean))], locations: [...locations.values()],
      periods: [...periods.values()].sort((a, b) => a.valid_from.localeCompare(b.valid_from)) };
  }
  async function save(button) {
    if (sending) return;
    const { errors, good } = check();
    if (errors.size) {
      render();
      setBar('bad', `Chưa lưu: ${errors.size} dòng sai (tô đỏ). Sửa rồi bấm Lưu lại.`);
      const r = form.rows.findIndex(row => errors.has(row.uid));
      $(`input[data-r="${r}"][data-c="${FIELDS.indexOf([...errors.get(form.rows[r].uid).fields][0])}"]`)?.focus();
      return;
    }
    sending = true; button.disabled = true;
    let outcome;
    try {
      outcome = await post('/api/v7/price-table', { customer_id: customerId, expected_version: ctx.snapshot.version,
        idempotency_key: crypto.randomUUID(), price_table: payload(good) });
    } catch {
      sending = false; button.disabled = false;
      setBar('bad', 'Chưa rõ đã lưu chưa. Đóng khung, tải lại sổ rồi mở Bảng giá để kiểm tra.');
      return;
    }
    sending = false; button.disabled = false;
    if (!outcome.ok) {
      setBar('bad', outcome.result.error === 'NO_CHANGE' ? 'Bảng giá không có gì thay đổi.'
        : outcome.result.error === 'STALE_LEDGER' ? 'Sổ vừa thay đổi. Đóng khung, tải lại rồi lưu lại.'
          : outcome.result.message || 'Chưa lưu được bảng giá.');
      return;
    }
    const affected = outcome.result.affected_trips ?? 0;
    closeDialog();
    try { await api.read(); } catch { showNotice('Đã lưu bảng giá; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
    showNotice(`Đã lưu bảng giá. Giá các chuyến đã ghi không tự đổi.${affected ? ` ${affected} chuyến đang ghi theo giá cũ của bảng: bấm "Áp lại giá mới" nếu muốn đổi.` : ''}`);
  }

  dialog.addEventListener('input', event => {
    const el = event.target;
    if (!form) return;
    if (el.dataset.c != null) { form.rows[Number(el.dataset.r)][FIELDS[Number(el.dataset.c)]] = el.value; updateGrid(); }
    else if (el.dataset.s != null) {
      form.ships[Number(el.dataset.s)].name = el.value;
      el.parentElement.querySelector('.price-ship-count')?.remove();
      el.insertAdjacentHTML('afterend', shipNote(el.value));
      updateDirty();
    }
  });
  dialog.addEventListener('change', event => {
    const el = event.target;
    if (!form) return;
    if (el.dataset.c != null) {
      const field = FIELDS[Number(el.dataset.c)];
      el.value = tidy(field, el.value);
      form.rows[Number(el.dataset.r)][field] = el.value;
      updateGrid();
    } else if (el.dataset.s != null) {
      el.value = keyOf(el.value);
      form.ships[Number(el.dataset.s)].name = el.value;
      updateDirty();
    }
  });
  // Ô trống cuối lưới vừa được dùng thì thêm hàng trống mới, giữ con trỏ ở ô đang chọn.
  dialog.addEventListener('focusout', event => {
    const el = event.target;
    if (!form || (el.dataset.c == null && el.dataset.s == null)) return;
    if (!form.rows.slice(-3).some(filled) && !form.ships.slice(-2).some(ship => ship.name.trim())) return;
    setTimeout(() => {
      if (!form || !dialog.contains(document.activeElement)) return;
      const { r, c, s } = document.activeElement.dataset ?? {};
      if (r == null && s == null) return;
      render();
      (r != null ? $(`input[data-r="${r}"][data-c="${c}"]`) : $(`input[data-s="${s}"]`))?.focus();
    }, 0);
  });
  dialog.addEventListener('paste', event => {
    const el = event.target;
    const text = event.clipboardData?.getData('text/plain') ?? '';
    if (!form || !/[\t\n]/.test(text.trim())) return;
    if (el.dataset?.c != null) { event.preventDefault(); pasteBlock(Number(el.dataset.r), Number(el.dataset.c), text); }
    else if (el.dataset?.s != null) {
      event.preventDefault();
      const added = addShips(text.split(/\r?\n/).map(line => line.split('\t')[0]));
      render();
      setBar('ok', `Đã dán ${added} shipper áp giá TT.`);
    }
  });
  dialog.addEventListener('keydown', event => {
    const el = event.target;
    if (event.key === 'Enter' && el.dataset.c != null) {
      event.preventDefault();
      el.dispatchEvent(new Event('change', { bubbles: true }));
      $(`input[data-r="${Number(el.dataset.r) + 1}"][data-c="${el.dataset.c}"]`)?.focus();
    } else if (event.key === 'Enter' && el.matches('.price-new-from')) { event.preventDefault(); newPeriod(el.value); }
  });
  dialog.addEventListener('click', event => {
    if (!form) return;
    if (event.target === dialog) { requestClose(); return; }
    const button = event.target.closest('button');
    if (!button) return;
    if (button.matches('.price-table-save')) save(button);
    else if (button.matches('.price-table-close')) requestClose();
    else if (button.matches('.price-discard')) closeDialog();
    else if (button.matches('.price-stay,.price-msg-close,.price-new-cancel')) { bar = null; renderBar(); }
    else if (button.matches('.price-new-open')) { bar = { kind: 'new' }; renderBar(); $('.price-new-from')?.focus(); }
    else if (button.matches('.price-new-ok')) newPeriod($('.price-new-from')?.value);
    else if (button.matches('.price-row-drop')) { form.rows.splice(Number(button.dataset.r), 1); render(); }
    else if (button.matches('.price-ship-drop')) { form.ships.splice(Number(button.dataset.s), 1); render(); }
  });
  // Esc: đóng câu hỏi đang hiện, hoặc đóng khung (hỏi lưu nếu còn thay đổi).
  if (typeof document.addEventListener === 'function') document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !form) return;
    if (bar?.kind === 'ask' || bar?.kind === 'new') { bar = null; renderBar(); } else requestClose();
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
