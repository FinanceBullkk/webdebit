/* Sổ khách V7 bản live — Bảng giá theo ngày hiệu lực (BANG-GIA-01, specs/v7-bang-gia-hieu-luc.md, giai đoạn 2).
 * Màn Bảng giá (dán từ Sheet, đợt giá, kho và tên khác, shipper của TT), nút "Áp giá theo bảng cho N chuyến",
 * chữ "theo bảng"/"khác bảng giá" ở ô Đơn giá. Server tra giá và ghi; trang không tự tính giá hay cộng tiền.
 * Nạp trước so-khach-v7-ui.js, dùng chung phạm vi của initLive qua ctx (xem so-khach-v7-ui.js). */
(window.SoKhachV7LiveParts ??= {}).price = ctx => {
  'use strict';
  const { root, model, api, customerId, escape, fmt, dateText, monthKey, monthLabel, showNotice } = ctx;
  const REASONS = { NO_DATE: 'thiếu ngày để tra giá', NO_ORIGIN: 'thiếu kho đi để tra giá',
    UNKNOWN_LOCATION: 'kho chưa có trong bảng giá', NO_PERIOD: 'ngày này chưa có giá trong bảng',
    NO_RATE: 'kho có trong bảng nhưng chưa có giá loại này' };
  const TIER = { khach: 'giá khách', tt: 'giá TT' };
  const SHORT = { khach: 'khách', tt: 'TT' };
  let status = null;            // GET /api/v7/price-table/status của phiên bản sổ đang vẽ
  let loadedVersion = null;
  let confirm = null;           // { kind: 'ready'|'reapply', ids }
  let sending = false;
  let form = null;              // bảng giá đang sửa trong khung; null = khung đóng
  let formError = '';
  let formInfo = '';
  let bookShippers = [];
  let nextUid = 1;

  // ---- Trạng thái giá: tải lại khi phiên bản sổ đổi; server cũ chưa có đường này thì coi như sổ chưa có bảng giá ----
  ctx.priceOnSnapshot = data => {
    if (!data || data.status !== 'active' || data.version === loadedVersion) return;
    loadedVersion = data.version;
    loadStatus();
  };
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
      + (ready ? `<button class="price-table-apply">Áp giá theo bảng cho ${ready} chuyến</button>` : '');
  };
  ctx.busyChecks.push(() => form !== null || confirm !== null);

  // Sau khi vẽ sổ: chữ nhỏ ở ô Đơn giá và khung hỏi lại dưới đầu sổ.
  ctx.priceAfterRender = active => {
    if (!active || !status) return;
    for (const row of status.trips) {
      const cell = root.querySelector(`[data-row="trip-${row.trip_id}"]`)?.children[7];
      if (!cell) continue;
      const lookup = row.lookup ?? {};
      let note = '', cls = 'price-hint';
      // Cột Đơn giá hẹp: chữ ngắn, xuống dòng trong ô.
      if (row.ready) note = `bảng: ${fmt(lookup.unit_price_vnd)} (${SHORT[lookup.tier] ?? ''})`;
      else if (row.differs) { note = `khác bảng: ${fmt(lookup.unit_price_vnd)}`; cls = 'price-hint price-diff'; }
      else if (row.from_table) note = `theo bảng (${SHORT[lookup.tier] ?? ''})`;
      else if (row.unit_price_vnd == null && REASONS[lookup.reason]) note = REASONS[lookup.reason];
      if (!note) continue;
      cell.insertAdjacentHTML('beforeend', `<small class="${cls}">${escape(note)}</small>`);
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
    const months = [...new Set(confirm.ids.map(id => monthKey(tripsOf().get(id)?.month)).filter(Boolean))].sort()
      .map(key => `tháng ${monthLabel(key)}`).join(', ');
    const body = confirm.kind === 'ready'
      ? `<strong>Áp giá theo bảng cho ${count} chuyến chưa có giá${months ? ` (${escape(months)})` : ''}?</strong> Tổng còn nợ tăng <strong>${fmt(status.ready_total_vnd)} đ</strong> (đơn giá + phụ phí đang có).`
      : `<strong>Áp lại giá mới của bảng cho ${count} chuyến${months ? ` (${escape(months)})` : ''}?</strong> Đơn giá các chuyến này đổi theo bảng; số tiền xem lại trên sổ sau khi ghi.`;
    return `<div class="price-panel confirm" role="region" aria-label="Xác nhận áp giá theo bảng"><p>${body} Phiếu thu tự phân bổ lại theo nợ cũ trước.</p><div class="price-actions"><button type="button" class="price-table-write primary">Áp ${count} giá</button><button type="button" class="price-table-cancel">Thôi</button></div></div>`;
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
    const ids = confirm.ids;
    let outcome;
    try {
      outcome = await post('/api/v7/price-table/apply', { customer_id: customerId, expected_version: ctx.snapshot.version,
        idempotency_key: crypto.randomUUID(), trip_ids: ids });
    } catch {
      sending = false; button.disabled = false;
      showNotice('Chưa rõ kết quả áp giá. Tải lại sổ để kiểm tra trước khi thử lại.');
      return;
    }
    sending = false;
    confirm = null;
    try { await api.read(); } catch { showNotice('Đã gửi lệnh áp giá; không tải được sổ mới. Tải lại trang để kiểm tra.'); return; }
    showNotice(outcome.ok ? `Đã áp giá theo bảng cho ${ids.length} chuyến.`
      : `Chưa áp giá nào. ${outcome.result.message || 'Tải lại sổ rồi thử lại.'}`);
  }

  // ---- Khung Bảng giá ----
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
  const dmy = iso => iso ? dateText(iso) : '';
  // Ngày dạng d/m/yyyy hoặc dd/mm/yyyy (như Sheet hiện) → yyyy-mm-dd; sai thì null.
  function isoOf(text) {
    const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(text ?? '').trim());
    if (!match) return null;
    const [day, month, year] = [Number(match[1]), Number(match[2]), Number(match[3])];
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
    return date.toISOString().slice(0, 10);
  }
  const dayBefore = iso => new Date(Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)) - 1)).toISOString().slice(0, 10);
  // Giá gõ/dán: "60,000,000", "60.000.000" hoặc "60000000"; trống là không có giá (không phải 0).
  function priceOf(text) {
    const value = String(text ?? '').trim();
    if (!value) return null;
    return model.parseVnd(value).toString();
  }
  const priceText = value => value == null || value === '' ? '' : fmt(value);

  function fromServer(table) {
    const locations = (table?.locations ?? []).map(item => ({ uid: nextUid++, name: item.name, aliases: (item.aliases ?? []).join(', ') }));
    const byName = new Map(locations.map(item => [item.name.toUpperCase(), item.uid]));
    const periods = (table?.periods ?? []).map(period => {
      const rates = {};
      for (const rate of period.rates ?? []) {
        const uid = byName.get(String(rate.location).toUpperCase());
        if (uid == null) continue;
        (rates[uid] ??= { khach: '', tt: '' })[rate.tier] = priceText(rate.unit_price_vnd);
      }
      return { from: dmy(period.valid_from), to: dmy(period.valid_to), rates };
    });
    return { shippers: (table?.tt_shippers ?? []).join('\n'), locations, periods, adding: null, pasteOpen: false };
  }
  async function openDialog() {
    formError = ''; formInfo = 'Đang đọc bảng giá…';
    form = fromServer(null);
    dialog.hidden = false;
    render();
    try {
      const response = await fetch(`/api/v7/price-table?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data?.price_table) throw Error(data?.message || 'Không đọc được bảng giá.');
      form = fromServer(data.price_table);
      bookShippers = Array.isArray(data.book_shippers) ? data.book_shippers : [];
      formInfo = '';
    } catch (error) { formInfo = ''; formError = error.message || 'Không đọc được bảng giá.'; }
    render();
    dialog.querySelector('.price-table-close')?.focus();
  }
  function closeDialog() { form = null; dialog.hidden = true; dialog.innerHTML = ''; root.querySelector('.price-table-open')?.focus(); ctx.redraw(); }

  function render() {
    if (!form) return;
    const listed = new Set(form.shippers.split('\n').map(name => name.trim().toUpperCase().replace(/\s+/g, ' ')).filter(Boolean));
    const others = bookShippers.filter(item => item.tier === 'khach' && !listed.has(String(item.name).toUpperCase().replace(/\s+/g, ' ')));
    const shipperList = others.length
      ? `<p class="fee-muted">Shipper trong sổ đang lấy <b>giá khách</b> — soát tên viết lệch so với danh sách TT:</p><ul class="price-book-shippers">${others.map(item =>
        `<li>${escape(item.name)} <small>(${item.trip_count} chuyến)</small> <button type="button" class="price-shipper-add" data-name="${escape(item.name)}">Thêm vào TT</button></li>`).join('')}</ul>` : '';
    const locationRows = form.locations.map((item, index) => `<tr><td><input class="price-loc-name" data-index="${index}" value="${escape(item.name)}" aria-label="Tên kho ${index + 1}" maxlength="200"></td>
      <td><input class="price-loc-aliases" data-index="${index}" value="${escape(item.aliases)}" aria-label="Tên khác của kho ${index + 1}" placeholder="Ví dụ: DAKLAK, DAKLAK-得乐"></td>
      <td><button type="button" class="price-loc-drop" data-index="${index}" aria-label="Bỏ kho ${escape(item.name || index + 1)}">Bỏ</button></td></tr>`).join('');
    const periodCards = form.periods.map((period, p) => `<section class="price-period" aria-label="Đợt giá ${p + 1}"><div class="price-period-head"><b>Đợt ${p + 1}</b>
      <label>Từ ngày <input class="price-from" data-p="${p}" value="${escape(period.from)}" placeholder="dd/mm/yyyy" inputmode="numeric"></label>
      <label>Đến ngày <input class="price-to" data-p="${p}" value="${escape(period.to)}" placeholder="trống = đang áp dụng" inputmode="numeric"></label>
      <button type="button" class="price-period-drop" data-p="${p}">Bỏ đợt này</button></div>
      <table class="price-rates"><thead><tr><th>Kho</th><th class="num">Giá khách</th><th class="num">Giá TT</th></tr></thead><tbody>${form.locations.map(item => {
        const rate = period.rates[item.uid] ?? { khach: '', tt: '' };
        return `<tr><td>${escape(item.name || '(chưa đặt tên)')}</td>${['khach', 'tt'].map(tier => `<td class="num"><input class="price-rate" data-p="${p}" data-uid="${item.uid}" data-tier="${tier}" value="${escape(rate[tier])}" inputmode="numeric" aria-label="${TIER[tier]} ${escape(item.name)} đợt ${p + 1}"></td>`).join('')}</tr>`;
      }).join('')}</tbody></table></section>`).join('');
    const open = form.periods.find(period => !period.to.trim());
    const adding = form.adding ? `<div class="price-adding"><label>Đợt mới từ ngày <input class="price-new-from" value="${escape(form.adding.from)}" placeholder="dd/mm/yyyy" inputmode="numeric"></label>
      ${open ? `<label><input type="checkbox" class="price-close-old" ${form.adding.closeOld ? 'checked' : ''}> Đóng đợt đang áp dụng (từ ${escape(open.from)}) vào ngày liền trước</label>` : ''}
      <button type="button" class="price-new-ok primary">Thêm đợt</button><button type="button" class="price-new-cancel">Thôi</button></div>` : '';
    const paste = form.pasteOpen ? `<div class="price-paste"><p class="fee-muted">Trên Sheet chọn đủ 5 cột theo thứ tự <b>Từ ngày · Đến ngày · Kho · Giá khách · Giá TT</b> (bỏ dòng tiêu đề cũng được), Ctrl+C rồi dán vào ô dưới. Đợt giá trong khung sẽ được thay bằng phần dán; kho mới tự thêm. Chưa lưu cho tới khi bấm Lưu bảng giá.</p>
      <textarea class="price-paste-text" rows="6" aria-label="Dán bảng giá từ Sheet"></textarea><div class="price-actions"><button type="button" class="price-paste-read primary">Đọc phần dán</button><button type="button" class="price-paste-cancel">Thôi</button></div></div>` : '';
    dialog.innerHTML = `<div class="fee-panel price-table-panel"><header><h2>Bảng giá của sổ</h2><button type="button" class="price-table-close">Đóng</button></header><div class="fee-panel-body">
      <p class="fee-muted">Giá tra theo <b>ngày xe nhập kho</b> và <b>kho đi</b>. Shipper có trong danh sách TT lấy <b>giá TT</b>; mọi shipper khác, kể cả để trống, lấy <b>giá khách</b>. Lưu bảng giá không đổi chuyến đã ghi.</p>
      ${formInfo ? `<p class="fee-info" role="status">${escape(formInfo)}</p>` : ''}<p class="fee-error" role="alert">${escape(formError)}</p>
      <div class="price-table-tools"><button type="button" class="price-paste-open">Dán bảng giá từ Sheet</button></div>${paste}
      <h3>Shipper của TT</h3><textarea class="price-shippers" rows="3" aria-label="Shipper của TT, mỗi dòng một tên">${escape(form.shippers)}</textarea>${shipperList}
      <h3>Kho và tên khác</h3><table class="price-locations"><thead><tr><th>Kho</th><th>Tên khác (cách nhau dấu phẩy)</th><th></th></tr></thead><tbody>${locationRows}</tbody></table>
      <button type="button" class="price-loc-add">+ Thêm kho</button>
      <h3>Đợt giá</h3>${periodCards || '<p class="fee-muted">Chưa có đợt giá nào.</p>'}${adding}
      ${form.adding ? '' : '<button type="button" class="price-period-add">+ Thêm đợt giá</button>'}
      <div class="price-actions price-save-row"><button type="button" class="price-table-save primary">Lưu bảng giá</button><button type="button" class="price-table-close">Đóng không lưu</button></div>
    </div></div>`;
  }
  // Đọc ô đang gõ vào form trước khi vẽ lại (vẽ lại thay toàn bộ ô nhập).
  function collect() {
    if (!form) return;
    const value = selector => dialog.querySelector(selector)?.value;
    form.shippers = value('.price-shippers') ?? form.shippers;
    for (const input of dialog.querySelectorAll('.price-loc-name')) form.locations[Number(input.dataset.index)].name = input.value.trim();
    for (const input of dialog.querySelectorAll('.price-loc-aliases')) form.locations[Number(input.dataset.index)].aliases = input.value;
    for (const input of dialog.querySelectorAll('.price-from')) form.periods[Number(input.dataset.p)].from = input.value.trim();
    for (const input of dialog.querySelectorAll('.price-to')) form.periods[Number(input.dataset.p)].to = input.value.trim();
    for (const input of dialog.querySelectorAll('.price-rate')) {
      (form.periods[Number(input.dataset.p)].rates[input.dataset.uid] ??= { khach: '', tt: '' })[input.dataset.tier] = input.value.trim();
    }
    if (form.adding) {
      form.adding.from = value('.price-new-from')?.trim() ?? form.adding.from;
      form.adding.closeOld = dialog.querySelector('.price-close-old')?.checked ?? form.adding.closeOld;
    }
  }
  // Dán từ Sheet: mỗi dòng Từ ngày, Đến ngày, Kho, Giá khách, Giá TT (tab). Dòng không bắt đầu bằng ngày là tiêu đề, bỏ qua.
  function readPaste(text) {
    const groups = new Map();
    const problems = [];
    let count = 0;
    text.split(/\r?\n/).forEach((line, index) => {
      const cells = line.split('\t').map(cell => cell.trim());
      if (!cells.some(Boolean) || !isoOf(cells[0])) return;
      const [from, to, location, khach, tt] = cells;
      if (!location) return;
      if (to && !isoOf(to)) { problems.push(`dòng ${index + 1}: ngày đến "${to}" không đọc được`); return; }
      const prices = {};
      for (const [tier, raw] of [['khach', khach], ['tt', tt]]) {
        try { prices[tier] = priceOf(raw); } catch { problems.push(`dòng ${index + 1}: giá "${raw}" không đọc được`); }
      }
      const key = `${isoOf(from)}|${to ? isoOf(to) : ''}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({ location, prices });
      count += 1;
    });
    if (problems.length) throw Error(`Chưa đọc được phần dán: ${problems.slice(0, 3).join('; ')}${problems.length > 3 ? '…' : ''}`);
    if (!count) throw Error('Không thấy dòng giá nào. Chọn đủ 5 cột: Từ ngày, Đến ngày, Kho, Giá khách, Giá TT.');
    const uidOf = name => {
      const found = form.locations.find(item => item.name.toUpperCase() === name.toUpperCase());
      if (found) return found.uid;
      const item = { uid: nextUid++, name, aliases: '' };
      form.locations.push(item);
      return item.uid;
    };
    form.periods = [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([key, rows]) => {
      const [from, to] = key.split('|');
      const rates = {};
      for (const row of rows) rates[uidOf(row.location)] = { khach: priceText(row.prices.khach), tt: priceText(row.prices.tt) };
      return { from: dmy(from), to: dmy(to), rates };
    });
    return `Đã đọc ${count} dòng thành ${form.periods.length} đợt giá. Xem lại rồi bấm Lưu bảng giá.`;
  }
  // Bảng giá gửi server: kiểm ngày và giá ngay tại khung; chồng ngày, tên trùng do server kiểm.
  function payload() {
    const names = form.locations.map(item => item.name.trim());
    if (names.some(name => !name)) throw Error('Có kho chưa đặt tên. Đặt tên hoặc bỏ kho đó.');
    const periods = form.periods.map((period, p) => {
      const from = isoOf(period.from);
      if (!from) throw Error(`Đợt ${p + 1}: ngày bắt đầu "${period.from}" không đúng dạng dd/mm/yyyy.`);
      const to = period.to.trim() ? isoOf(period.to) : null;
      if (period.to.trim() && !to) throw Error(`Đợt ${p + 1}: ngày đến "${period.to}" không đúng dạng dd/mm/yyyy.`);
      const rates = [];
      for (const item of form.locations) {
        for (const tier of ['khach', 'tt']) {
          let amount;
          try { amount = priceOf(period.rates[item.uid]?.[tier]); } catch { throw Error(`Đợt ${p + 1}, ${item.name}, ${TIER[tier]}: giá "${period.rates[item.uid][tier]}" không đọc được.`); }
          if (amount !== null) rates.push({ location: item.name.trim(), tier, unit_price_vnd: amount });
        }
      }
      return { valid_from: from, valid_to: to, rates };
    });
    return { tt_shippers: form.shippers.split('\n').map(name => name.trim()).filter(Boolean),
      locations: form.locations.map(item => ({ name: item.name.trim(), aliases: item.aliases.split(',').map(name => name.trim()).filter(Boolean) })),
      periods };
  }
  async function save(button) {
    collect();
    let table;
    try { table = payload(); } catch (error) { formError = error.message; formInfo = ''; render(); return; }
    if (sending) return;
    sending = true; button.disabled = true;
    let outcome;
    try {
      outcome = await post('/api/v7/price-table', { customer_id: customerId, expected_version: ctx.snapshot.version,
        idempotency_key: crypto.randomUUID(), price_table: table });
    } catch {
      sending = false;
      formError = 'Chưa rõ đã lưu chưa. Đóng khung, tải lại sổ rồi mở Bảng giá để kiểm tra.'; render();
      return;
    }
    sending = false;
    if (!outcome.ok) {
      formError = outcome.result.error === 'NO_CHANGE' ? 'Bảng giá không có gì thay đổi.'
        : outcome.result.error === 'STALE_LEDGER' ? 'Sổ vừa thay đổi. Đóng khung, tải lại rồi lưu lại.'
          : outcome.result.message || 'Chưa lưu được bảng giá.';
      formInfo = ''; render();
      return;
    }
    const affected = outcome.result.affected_trips ?? 0;
    form = fromServer(outcome.result.price_table ?? table);
    formError = '';
    formInfo = `Đã lưu bảng giá.${affected ? ` ${affected} chuyến đang ghi theo giá cũ của bảng: đóng khung rồi bấm "Áp lại giá mới" nếu muốn đổi.` : ''}`;
    render();
    try { await api.read(); } catch { formError = 'Đã lưu; không tải được sổ mới. Tải lại trang để kiểm tra.'; render(); }
  }

  dialog.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!form || (!button && event.target !== dialog)) return;
    if (event.target === dialog || button.matches('.price-table-close')) { closeDialog(); return; }
    if (button.matches('.price-table-save')) { save(button); return; }
    collect();
    formError = '';
    if (button.matches('.price-shipper-add')) form.shippers = `${form.shippers.trim()}\n${button.dataset.name}`.trim();
    else if (button.matches('.price-loc-add')) form.locations.push({ uid: nextUid++, name: '', aliases: '' });
    else if (button.matches('.price-loc-drop')) {
      const [item] = form.locations.splice(Number(button.dataset.index), 1);
      for (const period of form.periods) delete period.rates[item.uid];
    } else if (button.matches('.price-period-drop')) form.periods.splice(Number(button.dataset.p), 1);
    else if (button.matches('.price-period-add')) form.adding = { from: '', closeOld: true };
    else if (button.matches('.price-new-cancel')) form.adding = null;
    else if (button.matches('.price-new-ok')) {
      const from = isoOf(form.adding.from);
      if (!from) { formError = 'Ngày bắt đầu đợt mới phải có dạng dd/mm/yyyy.'; render(); return; }
      const open = form.periods.find(period => !period.to.trim());
      // Q6 (BANG-GIA-01): mặc định đóng đợt đang áp dụng vào ngày liền trước; đợt mới chép giá đợt đó để sửa.
      if (open && form.adding.closeOld) {
        if (!isoOf(open.from) || isoOf(open.from) >= from) { formError = 'Đợt mới phải bắt đầu sau ngày bắt đầu của đợt đang áp dụng.'; render(); return; }
        open.to = dmy(dayBefore(from));
      }
      const source = open ?? form.periods.at(-1);
      form.periods.push({ from: dmy(from), to: '', rates: JSON.parse(JSON.stringify(source?.rates ?? {})) });
      form.adding = null;
      formInfo = 'Đã thêm đợt mới với giá chép từ đợt trước. Sửa giá rồi bấm Lưu bảng giá.';
    } else if (button.matches('.price-paste-open')) form.pasteOpen = true;
    else if (button.matches('.price-paste-cancel')) form.pasteOpen = false;
    else if (button.matches('.price-paste-read')) {
      try { formInfo = readPaste(dialog.querySelector('.price-paste-text').value); form.pasteOpen = false; } catch (error) { formError = error.message; }
    }
    render();
  });
  // Esc đóng khung (kể cả khi vẽ lại làm mất con trỏ khỏi khung).
  if (typeof document.addEventListener === 'function') document.addEventListener('keydown', event => { if (event.key === 'Escape' && form) closeDialog(); });

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
