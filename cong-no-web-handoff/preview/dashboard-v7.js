(() => {
  'use strict';
  const F = CongNoFormat;
  const M = DashboardModel;
  const root = document.querySelector('#dashboard');
  const $ = id => document.getElementById(id);
  const monthText = value => /^\d{4}-\d{2}/.test(value ?? '') ? `${value.slice(5, 7)}/${value.slice(0, 4)}` : '—';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const ledgerHref = id => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}`;
  // Số rút gọn, rê chuột thấy số đồng chính xác.
  const amount = (value, unit) => `<span class="money" title="${esc(F.full(value))}">${esc(F.short(value, unit))}</span>`;
  const positive = value => String(value).replace(/^-/, '');
  const fold = value => String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[đĐ]/g, 'd').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const transportText = mode => ({ CANG: 'cảng', 'CẢNG': 'cảng', BO: 'bộ', 'BỘ': 'bộ' })[mode] ?? (mode ? String(mode).toLowerCase() : '');
  const commodityText = (commodity, mode) => commodity ? `${commodity}${transportText(mode) ? ` · ${transportText(mode)}` : ''}` : 'Chưa phân loại';
  const customerLabel = row => row.label ?? `${row.display_name ?? row.name}${row.commodity ? ` · ${commodityText(row.commodity, row.transport_mode)}` : ''}`;
  const customerLabels = customers => {
    const counts = new Map();
    for (const row of customers) counts.set(customerLabel(row), (counts.get(customerLabel(row)) ?? 0) + 1);
    return new Map(customers.map(row => [String(row.id), counts.get(customerLabel(row)) > 1 ? `${customerLabel(row)} · sổ ${row.id}` : customerLabel(row)]));
  };
  // Tên ngắn cho danh sách thanh: tên Sheet; trùng tên thì thêm mặt hàng, vẫn trùng thì thêm số sổ.
  const shortLabels = customers => {
    const base = row => row.display_name ?? row.name;
    const withCommodity = row => `${base(row)} · ${commodityText(row.commodity, row.transport_mode)}`;
    return new Map(customers.map(row => {
      if (customers.filter(item => base(item) === base(row)).length < 2) return [String(row.id), base(row)];
      if (customers.filter(item => withCommodity(item) === withCommodity(row)).length < 2) return [String(row.id), withCommodity(row)];
      return [String(row.id), `${withCommodity(row)} · sổ ${row.id}`];
    }));
  };
  const AGING = ['Tháng này', '1–2 tháng trước', '3–6 tháng trước', 'Trên 6 tháng'];
  let loading = false;
  // Nút "Làm mới" đọc Sheet ngay (specs/v7-sheet-refresh.md); server chưa bật thì giữ chữ "Cập nhật …".
  let sheetRefresh = null;
  let searchReady = false;
  let currentCustomers = [];
  // Trạng thái lọc (ghi lên địa chỉ trang): nhóm tuổi, dòng mặt hàng, khách đang mở ngăn kéo.
  const state = { age: null, com: null, data: null, debtors: null, ageReady: false, groups: [], labels: new Map(), names: new Map() };
  const markUpdated = () => { const node = document.querySelector('#updated-at'); if (node) node.textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`; sheetRefresh?.paint(); };

  function receivableCard(data) {
    const [, figure, unit] = /^(.*) (tỷ|triệu|đ)$/.exec(F.short(data.receivable.total_vnd)) ?? [null, F.short(data.receivable.total_vnd), ''];
    return `<section class="card receivable" aria-labelledby="h-receivable"><h2 id="h-receivable">Còn phải thu</h2>
      <div class="big-money" title="${esc(F.full(data.receivable.total_vnd))}">${esc(figure)}<small>${esc(unit)}</small></div>
      <div class="substat"><span class="money">${esc(F.full(data.receivable.total_vnd))}</span> · ${data.receivable.customers} khách đang nợ</div>
      <div class="minis">
        <div class="mini"><div class="k">Khách đang dư</div><div class="v credit">${amount(positive(data.credit.total_vnd))}</div><div class="s">${data.credit.customers} khách · tính riêng</div></div>
        <div class="mini"><div class="k">Đã thu hôm nay</div><div class="v">${amount(data.today.received_vnd)}</div><div class="s">${data.today.receipts} phiếu thu</div></div>
      </div></section>`;
  }

  function agingCard(data) {
    const total = data.receivable.total_vnd;
    const byBucket = new Map(data.aging.map(item => [item.bucket, item.receivable_vnd]));
    const value = i => byBucket.get(M.BUCKETS[i]) ?? '0';
    const old = F.sum([value(2), value(3)]);
    const bar = F.toBig(total) > 0n
      ? M.BUCKETS.map((_, i) => F.toBig(value(i)) > 0n ? `<span data-i="${i}" data-tip="age:${i}" style="flex:${F.barWidth(value(i), total)};background:var(--age-${i})"></span>` : '').join('')
      : '';
    return `<section class="card aging" id="age-card" aria-labelledby="h-aging"><div class="card-head"><h2 id="h-aging">Nợ theo tháng phát sinh</h2></div>
      ${F.toBig(total) > 0n ? `<p class="age-note"><b>${esc(F.short(old))} (${esc(F.percent(old, total))})</b> là nợ phát sinh từ 3 tháng trước trở về trước.</p>` : ''}
      <div class="age-bar" role="img" aria-label="${esc(M.BUCKETS.map((_, i) => `${AGING[i]} ${F.short(value(i))}`).join(', '))}">${bar}</div>
      <div class="age-legend">${M.BUCKETS.map((_, i) => `<button type="button" data-tuoi="${i}" data-tip="age:${i}" aria-pressed="false"><div class="k"><span class="sw" style="background:var(--age-${i})"></span>${AGING[i]}</div><div class="v">${amount(value(i))}</div><div class="p">${esc(F.percent(value(i), total))}</div></button>`).join('')}</div></section>`;
  }

  function todoCard(data, label) {
    const todo = data.todo;
    const sumCount = items => items.reduce((count, item) => count + item.count, 0);
    // Khách thiếu mặt hàng / sầu riêng chưa ghi cảng-bộ (cần ma trận để biết đủ khách đang nợ).
    const unsorted = (state.debtors ?? []).filter(row => row.key === M.UNSORTED).map(row => ({ customer_id: row.id, name: row.name, commodity: row.commodity }));
    const groups = [
      ['Chuyến thiếu đơn giá', 'critical', todo.missing_price, `${sumCount(todo.missing_price)} chuyến`, item => `${item.count} chuyến`, 'thieu-gia'],
      ['Chuyến chờ kiểm', 'warning', todo.pending_review, `${sumCount(todo.pending_review)} chuyến`, item => `${item.count} chuyến`, 'cho-kiem'],
      ['Chưa có số dư đầu', 'neutral', todo.no_baseline, `${todo.no_baseline.length} khách`, () => 'mở sổ', null],
      ['Cần gán mặt hàng / cảng-bộ', 'neutral', unsorted, `${unsorted.length} khách`, item => item.commodity ? 'chưa rõ cảng/bộ' : 'chưa có mặt hàng', null],
      ['Sổ đang dư tiền', 'credit', todo.credit, `${todo.credit.length} khách`, item => `dư ${esc(F.short(positive(item.credit_vnd)))}`, null],
    ].filter(group => group[2].length);
    const customers = groups.reduce((count, group) => count + group[2].length, 0);
    return `<section class="card todo" aria-labelledby="h-todo"><div class="card-head"><h2 id="h-todo">Việc cần làm</h2>${customers ? `<span class="aside">${customers} khách cần xem</span>` : ''}</div>
      ${groups.map(([title, tone, items, count, what, loc]) => `<div class="todo-group"><div class="todo-title"><span>${title}</span><span class="tag ${tone}">${count}</span></div><ul class="rows">${items.map(item =>
        `<li><a href="${ledgerHref(item.customer_id)}${loc ? `&amp;loc=${loc}` : ''}"${loc ? ' title="Mở sổ, đánh dấu các dòng cần xử lý"' : ''}><span class="who">${esc(label(item))}</span><span class="what">${what(item)}</span><span class="chev" aria-hidden="true">›</span></a></li>`).join('')}</ul></div>`).join('')}
      ${groups.length ? '' : '<p class="empty">Không có việc cần làm.</p>'}</section>`;
  }

  function todayCard(data) {
    const today = data.today;
    const body = today.trips + today.receipts + today.voids === 0
      ? '<p class="empty">Chưa có giao dịch nào hôm nay.</p>'
      : `<div class="today-stats"><div class="today-stat"><b>${today.trips}</b><span>chuyến nhập</span></div><div class="today-stat"><b>${today.receipts}</b><span>phiếu thu</span></div><div class="today-stat"><b>${amount(today.received_vnd)}</b><span>đã thu</span></div><div class="today-stat"><b>${today.voids}</b><span>phiếu hủy</span></div></div>
        <div class="actors">${today.by_actor.map(item => `<div><span>${esc(item.actor)}</span><span>${item.trips} chuyến · ${item.receipts} phiếu · ${amount(item.received_vnd)}${item.voids ? ` · ${item.voids} hủy` : ''}</span></div>`).join('')}</div>`;
    return `<section class="card today" aria-labelledby="h-today"><div class="card-head"><h2 id="h-today">Hôm nay</h2><span class="aside">theo ngày ghi</span></div>${body}</section>`;
  }

  // Một dòng thanh: tên + số (tỷ, 2 số lẻ) + thanh. `major` to và dày hơn; `grey` cho Khác / Chưa phân loại.
  const barRow = ({ cls = '', attrs, name, value, width }) =>
    `<button type="button" class="bar-row${cls}" ${attrs}><span class="line"><span class="nm">${esc(name)}</span><span class="val money">${esc(F.billions(value))}</span></span><span class="track"><i style="width:${width}%"></i></span></button>`;

  function commodityCard() {
    const groups = state.groups;
    const max = groups.reduce((top, item) => (item.total > top ? item.total : top), 0n).toString();
    const ranked = groups.filter(item => !item.grey);
    const major = M.majorCount(ranked.map(item => item.total));
    const firstGrey = groups.find(item => item.grey);
    const rows = groups.map(item => barRow({
      cls: item.grey ? ` grey${item === firstGrey ? ' first' : ''}` : ranked.indexOf(item) < major ? ' major' : '',
      attrs: `data-mh="${esc(item.key)}" data-tip="com:${esc(item.key)}" aria-pressed="${item.key === state.com}"${state.debtors ? '' : ' disabled'}`,
      name: item.key, value: item.total, width: F.barWidth(item.total, max) }));
    return `<section class="card commodity" id="com-card" aria-labelledby="h-commodity"><div class="card-head"><h2 id="h-commodity">Theo mặt hàng</h2><span class="aside">tỷ đồng</span></div>
      ${groups.length ? `<div class="bars" id="com">${rows.join('')}</div>` : '<p class="empty">Chưa có khách đang nợ.</p>'}</section>`;
  }

  function topCard() {
    return `<section class="card top-debtors" aria-labelledby="h-top"><div class="card-head"><h2 id="h-top"></h2><span class="aside" id="top-aside"></span></div>
      <div class="bars" id="top"></div><div class="tbl-foot"><a id="top-all" href="/cong-no-theo-thang.html"></a></div></section>`;
  }

  const filtered = () => state.age != null || state.com != null;
  const groupByKey = key => state.groups.find(item => item.key === key) ?? null;

  // Danh sách khách bên phải: không lọc thì 10 khách nợ nhiều nhất của get_dashboard; có lọc thì từ ma trận.
  function topRows() {
    if (!filtered()) return state.data.top_debtors.map(item => ({ id: item.customer_id, value: F.toBig(item.outstanding_vnd), oldest: item.oldest_open_month }));
    return M.filterDebtors(state.debtors ?? [], { age: state.age, group: groupByKey(state.com) })
      .map(item => ({ id: item.row.id, value: item.value, oldest: item.row.oldest }));
  }

  function paintFilters() {
    const data = state.data;
    $('age-card').classList.toggle('picking', state.age != null);
    document.querySelectorAll('[data-tuoi]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.tuoi) === state.age)));
    document.querySelectorAll('.age-bar [data-i]').forEach(span => span.classList.toggle('on', Number(span.dataset.i) === state.age));
    $('com-card').classList.toggle('picking', state.com != null);
    document.querySelectorAll('[data-mh]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mh === state.com)));
    $('filterbar').hidden = !filtered();
    $('chips').innerHTML = (state.age != null ? `<span class="chip">Phần nợ ${esc(AGING[state.age].toLowerCase())}<button type="button" data-clear="age" aria-label="Bỏ lọc ${esc(AGING[state.age])}">✕</button></span>` : '')
      + (state.com != null ? `<span class="chip">${esc(state.com)}<button type="button" data-clear="com" aria-label="Bỏ lọc ${esc(state.com)}">✕</button></span>` : '');
    const rows = topRows();
    const shown = rows.slice(0, 10);
    const total = F.sum(rows.map(item => item.value));
    $('h-top').textContent = filtered() ? `${rows.length} khách theo lọc` : 'Khách nợ nhiều nhất';
    $('top-aside').textContent = filtered() && rows.length ? `tổng ${F.short(total)} · tỷ đồng` : 'tỷ đồng';
    const major = M.majorCount(rows.map(item => item.value));
    const max = shown.length ? shown[0].value.toString() : '1';
    $('top').innerHTML = shown.length ? shown.map((item, index) => barRow({
      cls: index < major ? ' major' : '', attrs: `data-khach="${item.id}" data-tip="khach:${item.id}" aria-haspopup="dialog"`,
      name: state.names.get(String(item.id)) ?? data.top_debtors.find(row => row.customer_id === item.id)?.name ?? (state.debtors ?? []).find(row => row.id === item.id)?.name ?? `Sổ ${item.id}`,
      value: item.value, width: F.barWidth(item.value, max) })).join('')
      : `<p class="empty">${filtered() ? 'Không có khách nào khớp lọc này.' : 'Không có khách đang nợ.'}</p>`;
    const query = new URLSearchParams({ 'con-no': '1' });
    if (state.age != null) query.set('tuoi', String(state.age));
    $('top-all').href = `/cong-no-theo-thang.html?${query}`;
    $('top-all').textContent = rows.length > 10 ? `Xem cả ${rows.length} khách ở Công nợ theo tháng ›` : 'Xem ở Công nợ theo tháng ›';
  }

  function render(data, customers = []) {
    const labels = customerLabels(customers);
    const commodityLabel = item => item.commodity ? `${item.name} · ${commodityText(item.commodity, item.transport_mode)}` : item.name;
    const label = item => labels.get(String(item.customer_id)) ?? commodityLabel(item);
    state.names = shortLabels(customers);
    state.groups = M.commodityGroups(data.by_commodity, data.receivable.total_vnd);
    if (state.com != null && !groupByKey(state.com)) state.com = null;
    root.innerHTML = `<div class="grid">${receivableCard(data)}${agingCard(data)}
      <div class="filterbar" id="filterbar" hidden><span>Đang lọc danh sách khách:</span><span class="chips" id="chips"></span><button type="button" class="clear-all" data-clear="all">Bỏ lọc</button></div>
      ${todoCard(data, label)}<div class="side">${commodityCard()}${todayCard(data)}</div>${topCard()}</div>`;
    paintFilters();
  }

  // Trạng thái trên địa chỉ trang: ?tuoi= (0–3), ?mh= (dòng mặt hàng), ?khach= (ngăn kéo).
  const params = () => new URLSearchParams(location.search);
  const writeUrl = () => {
    const query = params();
    if (state.age == null) query.delete('tuoi'); else query.set('tuoi', String(state.age));
    if (state.com == null) query.delete('mh'); else query.set('mh', state.com);
    history.replaceState(null, '', location.pathname + (query.toString() ? `?${query}` : ''));
  };
  const readUrl = () => {
    const query = params();
    state.age = /^[0-3]$/.test(query.get('tuoi') ?? '') ? Number(query.get('tuoi')) : null;
    state.com = query.get('mh') || null;
  };

  function pickAge(index) {
    // Phần nợ theo nhóm của từng khách không khớp tổng get_dashboard (hoặc chưa tải được ma trận): soi ở ma trận.
    if (!state.ageReady) { location.href = `/cong-no-theo-thang.html?tuoi=${index}&con-no=1`; return; }
    state.age = state.age === index ? null : index;
    writeUrl(); paintFilters();
  }

  root.addEventListener('click', event => {
    const legend = event.target.closest('[data-tuoi]');
    if (legend) return pickAge(Number(legend.dataset.tuoi));
    const segment = event.target.closest('.age-bar [data-i]');
    if (segment) return pickAge(Number(segment.dataset.i));
    const commodity = event.target.closest('[data-mh]');
    if (commodity && state.debtors) {
      state.com = state.com === commodity.dataset.mh ? null : commodity.dataset.mh;
      writeUrl(); paintFilters(); return;
    }
    const clear = event.target.closest('[data-clear]');
    if (clear) {
      if (clear.dataset.clear !== 'com') state.age = null;
      if (clear.dataset.clear !== 'age') state.com = null;
      writeUrl(); paintFilters(); return;
    }
    const customer = event.target.closest('[data-khach]');
    if (customer) {
      openDrawer(Number(customer.dataset.khach), customer);
      const query = params(); query.set('khach', customer.dataset.khach);
      history.pushState(null, '', `${location.pathname}?${query}`);
      pushed = true;
    }
  });

  // Ô thông tin khi rê chuột hoặc focus bàn phím: số đứng đầu, chi tiết theo sau.
  function tipText(key) {
    const [kind, id] = [key.slice(0, key.indexOf(':')), key.slice(key.indexOf(':') + 1)];
    const data = state.data;
    const total = data.receivable.total_vnd;
    if (kind === 'age') {
      const value = data.aging.find(item => item.bucket === M.BUCKETS[Number(id)])?.receivable_vnd ?? '0';
      const count = state.ageReady ? state.debtors.filter(row => row.buckets[Number(id)] > 0n).length : null;
      return [AGING[Number(id)], F.short(value), `${F.percent(value, total)} còn phải thu${count == null ? '' : ` · ${count} khách`}`, F.full(value)];
    }
    if (kind === 'com') {
      const group = groupByKey(id);
      const extra = group.key === M.OTHER ? ` · ${group.names.join(', ')}` : '';
      return [group.key, F.short(group.total), `${F.percent(group.total, total)} còn phải thu · ${group.customers} khách${extra}`, F.full(group.total)];
    }
    const item = topRows().find(row => row.id === Number(id));
    if (!item) return null;
    const part = state.age == null ? `${F.percent(item.value, total)} còn phải thu` : `phần nợ ${AGING[state.age].toLowerCase()}`;
    return [state.names.get(id) ?? `Sổ ${id}`, F.short(item.value), `${part}${item.oldest ? ` · nợ từ ${monthText(item.oldest)}` : ''}`, F.full(item.value)];
  }
  const tip = $('tip');
  const hideTip = () => { tip.hidden = true; };
  function showTip(el) {
    if (el.disabled) return hideTip();
    const text = tipText(el.dataset.tip);
    if (!text) return hideTip();
    tip.replaceChildren(...text.map((line, index) => {
      const node = document.createElement(index === 1 ? 'b' : 'span');
      node.textContent = line;
      return node;
    }));
    tip.hidden = false;
    const box = el.getBoundingClientRect();
    const left = Math.min(Math.max(8, box.left + box.width / 2 - tip.offsetWidth / 2), innerWidth - tip.offsetWidth - 8);
    const above = box.top - tip.offsetHeight - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${above > 64 ? above : box.bottom + 8}px`;
  }
  document.addEventListener('pointerover', event => { const el = event.target.closest?.('#dashboard [data-tip]'); if (el) showTip(el); else hideTip(); });
  document.addEventListener('focusin', event => { const el = event.target.closest?.('#dashboard [data-tip]'); if (el) showTip(el); else hideTip(); });
  document.addEventListener('focusout', hideTip);
  addEventListener('scroll', hideTip, { passive: true });

  // Ngăn kéo xem nhanh một khách: nợ theo tháng từ ma trận, nút mở sổ.
  let lastFocus = null;
  let pushed = false;
  function openDrawer(id, trigger = null) {
    const row = (state.debtors ?? []).find(item => item.id === id);
    const top = state.data.top_debtors.find(item => item.customer_id === id);
    if (!row && !top) return;
    hideTip();
    const name = state.names.get(String(id)) ?? row?.name ?? top.name;
    const total = row ? row.total : F.toBig(top.outstanding_vnd);
    $('d-name').textContent = name;
    $('d-sub').textContent = row ? (row.key === M.UNSORTED ? 'Chưa phân loại' : row.key) : commodityText(top.commodity, top.transport_mode);
    const lines = row ? [...row.months.map(item => [`Tháng ${item.key.slice(5)}/${item.key.slice(0, 4)}`, item.value, M.ageIndex(Number(item.key.slice(0, 4)), Number(item.key.slice(5)), state.data.as_of)]),
      ...(row.older !== 0n ? [[`Trước năm ${row.olderBefore}`, row.older, 3]] : [])] : [];
    const max = lines.reduce((top, line) => (line[1] > top ? line[1] : top), 0n).toString();
    const missing = state.data.todo.missing_price.find(item => item.customer_id === id);
    $('d-body').innerHTML = `<div class="total"><span>Còn nợ</span><b class="money" title="${esc(F.full(total))}">${esc(F.short(total))}</b></div>`
      + (lines.length ? `<h3>Còn nợ theo tháng phát sinh</h3>${lines.map(([text, value, age]) => `<div class="mrow"><span>${esc(text)}</span><span class="track"><i style="width:${F.barWidth(value, max)}%;background:var(--age-${age})"></i></span><span class="r money" title="${esc(F.full(value))}">${value < 0n ? `dư ${esc(F.short(-value))}` : esc(F.short(value))}</span></div>`).join('')}`
        : '<p class="empty">Chưa tải được nợ theo tháng. Mở sổ để xem chi tiết.</p>')
      + (missing ? `<p class="flags">${missing.count} chuyến thiếu đơn giá — chưa tính vào số trên.</p>` : '');
    $('d-open').href = ledgerHref(id);
    $('d-matrix').href = '/cong-no-theo-thang.html?con-no=1';
    lastFocus = trigger ?? document.activeElement;
    $('scrim').hidden = false;
    $('drawer').hidden = false;
    $('d-close').focus();
  }
  function closeDrawer() {
    $('scrim').hidden = true;
    $('drawer').hidden = true;
    const again = lastFocus?.dataset?.khach && document.querySelector(`#top [data-khach="${lastFocus.dataset.khach}"]`);
    (again || lastFocus)?.focus?.();
  }
  const leave = () => {
    if ($('drawer').hidden) return;
    if (pushed) { pushed = false; history.back(); return; }
    closeDrawer();
    const query = params(); query.delete('khach');
    history.replaceState(null, '', location.pathname + (query.toString() ? `?${query}` : ''));
  };
  $('d-close').addEventListener('click', leave);
  $('scrim').addEventListener('click', leave);
  document.addEventListener('keydown', event => {
    if ($('drawer').hidden) return;
    if (event.key === 'Escape') leave();
    if (event.key === 'Tab') {
      const focusable = [...$('drawer').querySelectorAll('button,a[href]')];
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  window.addEventListener('popstate', () => {
    pushed = false;
    readUrl();
    if (state.data) paintFilters();
    const id = Number(params().get('khach'));
    if (id) openDrawer(id); else if (!$('drawer').hidden) closeDrawer();
  });

  function setupSearch(customers) {
    currentCustomers = customers;
    if (searchReady) return;
    searchReady = true;
    const input = document.querySelector('#customer-search');
    const results = document.querySelector('#customer-results');
    const draw = () => {
      const query = fold(input.value);
      const labels = customerLabels(currentCustomers);
      const found = currentCustomers.filter(item => [item.name, item.display_name, item.label, item.commodity, ...(item.aliases ?? [])]
        .some(value => fold(value).includes(query))).slice(0, 20);
      results.innerHTML = found.map(item => `<a role="option" href="${ledgerHref(item.id)}">${esc(labels.get(String(item.id)))}</a>`).join('');
      results.hidden = !query || !found.length;
    };
    input.addEventListener('input', draw);
    input.addEventListener('focus', draw);
    document.addEventListener('click', event => { if (!event.target.closest('.search')) results.hidden = true; });
  }

  const json = async url => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw Error(url);
    return response.json();
  };

  async function load() {
    if (loading) return;
    loading = true;
    try {
      const response = await fetch('/api/v7/dashboard', { cache: 'no-store' });
      if (!response.ok) throw Error('Không tải được tổng quan công nợ.');
      const data = await response.json();
      const [year, month, day] = data.as_of.split('-');
      document.querySelector('#as-of').textContent = `Số liệu đến ${day}/${month}/${year}`;
      const banner = document.querySelector('#demo-banner');
      if (data.demo || data.real_copy) {
        banner.hidden = false;
        banner.textContent = data.real_copy ? 'Dữ liệu thật · bản sao cô lập, chưa phải prod' : 'Dữ liệu thử · DỮ LIỆU GIẢ · Không phải sổ thật';
      }
      // Danh sách khách và ma trận là phần thêm: lỗi thì trang vẫn đọc được, chỉ tắt lọc.
      const [customers, current, previous] = await Promise.all([
        json('/api/v7/customers').then(body => body.customers ?? []).catch(() => []),
        json(`/api/v7/receivables/matrix?year=${Number(year)}`).catch(() => null),
        Number(year) > 2000 ? json(`/api/v7/receivables/matrix?year=${Number(year) - 1}`).catch(() => null) : null,
      ]);
      state.data = data;
      try {
        state.debtors = current ? M.debtors(current, previous, data.as_of) : null;
      } catch {
        state.debtors = null;
      }
      state.ageReady = Boolean(state.debtors) && M.agingMatches(state.debtors, data.aging);
      if (!state.ageReady) state.age = null;
      if (!state.debtors) state.com = null;
      render(data, customers);
      setupSearch(customers);
      document.querySelector('#error').hidden = true;
      markUpdated();
      const open = Number(params().get('khach'));
      if (open && $('drawer').hidden) openDrawer(open);
    } catch (error) {
      const alert = document.querySelector('#error');
      alert.hidden = false;
      alert.textContent = error.message;
      if (!root.querySelector('.grid')) root.replaceChildren();
    } finally { loading = false; }
  }

  readUrl();
  load();
  const refresh = () => { if (document.activeElement?.id === 'customer-search' || !$('drawer').hidden) return; load(); sheetRefresh?.load(); };
  const button = document.querySelector('#refresh-data');
  if (globalThis.SheetRefresh) {
    sheetRefresh = globalThis.SheetRefresh.create({ node: document.querySelector('#updated-at'), button, onDone: () => load() });
    sheetRefresh.load();
  }
  button?.addEventListener('click', () => { load(); sheetRefresh?.trigger(); });
  setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
