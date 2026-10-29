(() => {
  'use strict';
  const F = CongNoFormat;
  const root = document.querySelector('#dashboard');
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
  const AGING = { current: 'Tháng này', '1-2': '1–2 tháng trước', '3-6': '3–6 tháng trước', 'over-6': 'Trên 6 tháng' };
  const AGING_ORDER = ['current', '1-2', '3-6', 'over-6'];
  let loading = false;
  // Nút "Làm mới" đọc Sheet ngay (specs/v7-sheet-refresh.md); server chưa bật thì giữ chữ "Cập nhật …".
  let sheetRefresh = null;
  let searchReady = false;
  let currentCustomers = [];
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
    const buckets = AGING_ORDER.filter(key => byBucket.has(key));
    const old = F.sum(['3-6', 'over-6'].filter(key => byBucket.has(key)).map(key => byBucket.get(key)));
    const bar = F.toBig(total) > 0n
      ? buckets.map((key, i) => F.toBig(byBucket.get(key)) > 0n
        ? `<span style="flex:${F.barWidth(byBucket.get(key), total)};background:var(--age-${i})" title="${AGING[key]}: ${esc(F.full(byBucket.get(key)))}"></span>` : '').join('')
      : '';
    return `<section class="card aging" aria-labelledby="h-aging"><div class="card-head"><h2 id="h-aging">Nợ theo tháng phát sinh</h2><span class="aside">tính theo tháng phát sinh nợ, không phải ngày quá hạn</span></div>
      <div class="age-bar" role="img" aria-label="${esc(buckets.map(key => `${AGING[key]} ${F.short(byBucket.get(key))}`).join(', '))}">${bar}</div>
      <div class="age-legend">${buckets.map((key, i) => `<div><div class="k"><span class="sw" style="background:var(--age-${i})"></span>${AGING[key]}</div><div class="v">${amount(byBucket.get(key))}</div><div class="p">${esc(F.percent(byBucket.get(key), total))}</div></div>`).join('')}</div>
      ${F.toBig(total) > 0n ? `<p class="age-note"><b>${esc(F.short(old))}</b> (${esc(F.percent(old, total))}) là nợ phát sinh từ 3 tháng trước trở về trước.</p>` : ''}</section>`;
  }

  function todoCard(data, label) {
    const todo = data.todo;
    const sumCount = items => items.reduce((count, item) => count + item.count, 0);
    const groups = [
      ['Chuyến thiếu đơn giá', 'critical', todo.missing_price, `${sumCount(todo.missing_price)} chuyến`, item => `${item.count} chuyến`],
      ['Chuyến chờ kiểm', 'warning', todo.pending_review, `${sumCount(todo.pending_review)} chuyến`, item => `${item.count} chuyến`],
      ['Chưa có số dư đầu', 'neutral', todo.no_baseline, `${todo.no_baseline.length} khách`, () => 'mở sổ'],
      ['Sổ đang dư tiền', 'credit', todo.credit, `${todo.credit.length} khách`, item => `dư ${esc(F.short(positive(item.credit_vnd)))}`],
    ].filter(group => group[2].length);
    const customers = groups.reduce((count, group) => count + group[2].length, 0);
    return `<section class="card todo" aria-labelledby="h-todo"><div class="card-head"><h2 id="h-todo">Việc cần làm</h2>${customers ? `<span class="aside">${customers} khách cần xem</span>` : ''}</div>
      ${groups.map(([title, tone, items, count, what]) => `<div class="todo-group"><div class="todo-title"><span>${title}</span><span class="tag ${tone}">${count}</span></div><ul class="rows">${items.map(item =>
        `<li><a href="${ledgerHref(item.customer_id)}"><span class="who">${esc(label(item))}</span><span class="what">${what(item)}</span><span class="chev" aria-hidden="true">›</span></a></li>`).join('')}</ul></div>`).join('')}
      ${groups.length ? '' : '<p class="empty">Không có việc cần làm.</p>'}</section>`;
  }

  function todayCard(data) {
    const today = data.today;
    const body = today.trips + today.receipts + today.voids === 0
      ? '<p class="empty">Chưa có giao dịch nào hôm nay.</p>'
      : `<div class="today-stats"><div class="today-stat"><b>${today.trips}</b><span>chuyến nhập</span></div><div class="today-stat"><b>${today.receipts}</b><span>phiếu thu</span></div><div class="today-stat"><b>${amount(today.received_vnd)}</b><span>đã thu</span></div><div class="today-stat"><b>${today.voids}</b><span>phiếu hủy</span></div></div>
        <div class="actors">${today.by_actor.map(item => `<div><span>${esc(item.actor)}</span><span>${item.trips} chuyến · ${item.receipts} phiếu · ${amount(item.received_vnd)}${item.voids ? ` · ${item.voids} hủy` : ''}</span></div>`).join('')}</div>`;
    return `<section class="card today" aria-labelledby="h-today"><div class="card-head"><h2 id="h-today">Hôm nay</h2><span class="aside">theo ngày ghi trên web</span></div>${body}</section>`;
  }

  function topCard(data, label) {
    const total = data.receivable.total_vnd;
    const share = data.top_debtors.length ? F.percent(F.sum(data.top_debtors.map(item => item.outstanding_vnd)), total) : '';
    return `<section class="card top-debtors" aria-labelledby="h-top"><div class="card-head"><h2 id="h-top">Khách nợ nhiều nhất</h2>${share && share !== '—' ? `<span class="aside">${data.top_debtors.length} khách · ${esc(share)} còn phải thu</span>` : ''}</div>
      ${data.top_debtors.length ? `<ul class="rows">${data.top_debtors.map((item, index) => `<li><a href="${ledgerHref(item.customer_id)}" title="Mở sổ khách"><span class="rank">${index + 1}</span>
        <span class="who"><b>${esc(label(item))}</b><span>nợ từ ${monthText(item.oldest_open_month)}</span></span>
        <span class="amt"><b>${amount(item.outstanding_vnd)}</b><span>${esc(F.percent(item.outstanding_vnd, total))}</span></span><span class="chev" aria-hidden="true">›</span></a></li>`).join('')}</ul>` : '<p class="empty">Không có khách đang nợ.</p>'}</section>`;
  }

  function commodityCard(data) {
    const total = data.receivable.total_vnd;
    const values = data.by_commodity.map(item => F.toBig(item.receivable_vnd));
    const max = values.reduce((a, b) => (b > a ? b : a), 0n);
    return `<section class="card commodity" aria-labelledby="h-commodity"><div class="card-head"><h2 id="h-commodity">Theo mặt hàng</h2></div>
      ${data.by_commodity.length ? `<ul class="rows">${data.by_commodity.map(item => `<li class="${item.commodity == null ? 'none' : ''}"><div class="row">
        <div class="line"><b>${esc(commodityText(item.commodity, item.transport_mode))}</b>${amount(item.receivable_vnd)}</div>
        <div class="meta">${item.customers} khách · ${esc(F.percent(item.receivable_vnd, total))}${item.commodity == null ? ' · <span class="warning">cần gán mặt hàng</span>' : ''}</div>
        <div class="bar"><i style="width:${F.barWidth(item.receivable_vnd, max.toString())}%"></i></div></div></li>`).join('')}</ul>` : '<p class="empty">Chưa có khách đang nợ.</p>'}</section>`;
  }

  function render(data, customers = []) {
    const labels = customerLabels(customers);
    const label = item => labels.get(String(item.customer_id)) ?? commodityLabel(item);
    const commodityLabel = item => item.commodity ? `${item.name} · ${commodityText(item.commodity, item.transport_mode)}` : item.name;
    root.innerHTML = `<div class="grid">${receivableCard(data)}${agingCard(data)}
      <div class="side">${todoCard(data, label)}${todayCard(data)}</div>${topCard(data, label)}${commodityCard(data)}</div>`;
  }

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
      let customers = [];
      try {
        const customerResponse = await fetch('/api/v7/customers', { cache: 'no-store' });
        if (customerResponse.ok) customers = (await customerResponse.json()).customers ?? [];
      } catch {
        // Dashboard vẫn đọc được khi danh sách khách tạm lỗi.
      }
      render(data, customers);
      setupSearch(customers);
      document.querySelector('#error').hidden = true;
      markUpdated();
    } catch (error) {
      const alert = document.querySelector('#error');
      alert.hidden = false;
      alert.textContent = error.message;
      if (!root.querySelector('.grid')) root.replaceChildren();
    } finally { loading = false; }
  }

  load();
  const refresh = () => { if (document.activeElement?.id === 'customer-search') return; load(); sheetRefresh?.load(); };
  const button = document.querySelector('#refresh-data');
  if (globalThis.SheetRefresh) {
    sheetRefresh = globalThis.SheetRefresh.create({ node: document.querySelector('#updated-at'), button, onDone: () => load() });
    sheetRefresh.load();
  }
  button?.addEventListener('click', () => { load(); sheetRefresh?.trigger(); });
  setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
