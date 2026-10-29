// Tab Việc cần làm (DASH-03, 29/10/2026): nhận nguyên khối Việc cần làm và Hôm nay từ Tổng quan cũ, thêm sổ đang dư.
// Người nhập xem cuối ngày; bấm dòng mở đúng sổ khách (`?loc=` tô các chuyến cần xử lý). Trang chỉ đọc.
(() => {
  'use strict';
  const F = CongNoFormat;
  const M = DashboardModel;
  const root = document.querySelector('#todo-root');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const ledgerHref = id => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}`;
  const amount = value => `<span class="money" title="${esc(F.full(value))}">${esc(F.short(value))}</span>`;
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
  let loading = false;
  let sheetRefresh = null;
  let searchReady = false;
  let currentCustomers = [];
  const markUpdated = () => { const node = document.querySelector('#updated-at'); if (node) node.textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`; sheetRefresh?.paint(); };

  function todoCard(data, unsorted, label) {
    const todo = data.todo;
    const sumCount = items => items.reduce((count, item) => count + item.count, 0);
    const groups = [
      ['Chuyến thiếu đơn giá', 'critical', todo.missing_price, `${sumCount(todo.missing_price)} chuyến`, item => `${item.count} chuyến`, 'thieu-gia'],
      ['Chuyến chờ kiểm', 'warning', todo.pending_review, `${sumCount(todo.pending_review)} chuyến`, item => `${item.count} chuyến`, 'cho-kiem'],
      ['Chưa có số dư đầu', 'neutral', todo.no_baseline, `${todo.no_baseline.length} khách`, () => 'mở sổ', null],
      ['Cần gán mặt hàng / cảng-bộ', 'neutral', unsorted, `${unsorted.length} khách`, item => item.commodity ? 'chưa rõ cảng/bộ' : 'chưa có mặt hàng', null],
    ].filter(group => group[2].length);
    const customers = new Set(groups.flatMap(group => group[2].map(item => item.customer_id))).size;
    return `<section class="card todo" aria-labelledby="h-todo"><div class="card-head"><h2 id="h-todo">Cần xử lý trong sổ</h2>${customers ? `<span class="aside">${customers} khách cần xem</span>` : ''}</div>
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
    return `<section class="card today" aria-labelledby="h-today"><div class="card-head"><h2 id="h-today">Hôm nay</h2><span class="aside">theo ngày ghi trên web</span></div>${body}</section>`;
  }

  function creditCard(data, label) {
    const items = data.todo.credit;
    return `<section class="card credit" aria-labelledby="h-credit"><div class="card-head"><h2 id="h-credit">Sổ đang dư tiền</h2><span class="aside">tự trừ vào chuyến sau</span></div>
      ${items.length ? `<div class="todo-group"><ul class="rows">${items.map(item => `<li><a href="${ledgerHref(item.customer_id)}"><span class="who">${esc(label(item))}</span><span class="what">dư ${esc(F.short(positive(item.credit_vnd)))}</span><span class="chev" aria-hidden="true">›</span></a></li>`).join('')}</ul></div>`
        : '<p class="empty">Không có sổ nào đang dư.</p>'}</section>`;
  }

  function paintBadge(data, unsorted) {
    const badge = document.querySelector('#todo-badge');
    const ids = new Set([...data.todo.missing_price, ...data.todo.pending_review, ...data.todo.no_baseline, ...unsorted].map(item => item.customer_id));
    badge.textContent = ids.size ? String(ids.size) : '';
    badge.hidden = !ids.size;
    badge.setAttribute('aria-label', `${ids.size} khách cần xem`);
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
      if (!response.ok) throw Error('Không tải được việc cần làm.');
      const data = await response.json();
      const [year, month, day] = data.as_of.split('-');
      document.querySelector('#as-of').textContent = `Số liệu đến ${day}/${month}/${year}`;
      const banner = document.querySelector('#demo-banner');
      if (data.demo || data.real_copy) {
        banner.hidden = false;
        banner.textContent = data.real_copy ? 'Dữ liệu thật · bản sao cô lập, chưa phải prod' : 'Dữ liệu thử · DỮ LIỆU GIẢ · Không phải sổ thật';
      }
      // Sổ cần gán mặt hàng lấy từ danh sách khách đang nợ của Tổng quan; lỗi thì chỉ bỏ nhóm đó.
      const [customers, debt] = await Promise.all([
        json('/api/v7/customers').then(body => body.customers ?? []).catch(() => []),
        json('/api/v7/dashboard/debt').catch(() => null),
      ]);
      const unsorted = (debt?.customers ?? []).filter(row => M.commodityKey(row.commodity, row.transport_mode) === M.UNSORTED)
        .map(row => ({ customer_id: row.customer_id, name: row.name, commodity: row.commodity }));
      const labels = customerLabels(customers);
      const label = item => labels.get(String(item.customer_id)) ?? item.name;
      root.innerHTML = `<div class="grid">${todoCard(data, unsorted, label)}<div class="side">${todayCard(data)}${creditCard(data, label)}</div></div>`;
      paintBadge(data, unsorted);
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
