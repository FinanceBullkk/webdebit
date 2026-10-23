(() => {
  'use strict';
  const root = document.querySelector('#dashboard');
  const money = value => value == null ? '—' : `${BigInt(value).toLocaleString('vi-VN')} đ`;
  const creditMoney = value => money(String(value).replace(/^-/, ''));
  const monthText = value => /^\d{4}-\d{2}/.test(value ?? '') ? `${value.slice(5, 7)}/${value.slice(0, 4)}` : '—';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const customerLink = (id, name) => `<a href="/so-khach-v7-live.html?customer=${encodeURIComponent(id)}">${esc(name)}</a>`;
  const agingLabels = { current: 'Tháng này', '1-2': '1–2 tháng trước', '3-6': '3–6 tháng trước', 'over-6': 'Trên 6 tháng' };

  function todoGroup(items, title, row) {
    return items.length ? `<section class="todo-group"><div class="todo-head"><span>${title}</span><span>${items.length} việc</span></div>${items.map(row).join('')}</section>` : '';
  }

  function render(data) {
    const todo = data.todo;
    root.innerHTML = `<div class="grid">
      <section class="card receivable"><h2><span class="icon">▣</span>Còn phải thu</h2><div class="big-money money">${money(data.receivable.total_vnd)}</div><div class="substat">${data.receivable.customers} khách đang nợ</div><div class="credit">Khách đang dư: <strong>${creditMoney(data.credit.total_vnd)}</strong> · <strong>${data.credit.customers} khách</strong></div></section>
      <section class="card aging"><h2><span class="icon">▮</span>Nợ theo tháng phát sinh</h2>${data.aging.map(item => `<div class="aging-row"><span>${agingLabels[item.bucket] ?? esc(item.bucket)}</span><progress aria-label="${agingLabels[item.bucket] ?? esc(item.bucket)}" max="${esc(data.receivable.total_vnd)}" value="${esc(item.receivable_vnd)}"></progress><strong class="money">${money(item.receivable_vnd)}</strong></div>`).join('')}</section>
      <section class="card commodity"><h2><span class="icon">◆</span>Theo mặt hàng</h2><table class="table"><thead><tr><th>Mặt hàng</th><th>Phương thức</th><th>Số khách</th><th class="money">Còn phải thu</th></tr></thead><tbody>${data.by_commodity.map(item => `<tr><td>${esc(item.commodity ?? 'Chưa phân loại')}${item.commodity == null ? '<span class="warning">Cảnh báo: cần phân loại</span>' : ''}</td><td>${esc(item.transport_mode ?? '—')}</td><td>${item.customers} khách</td><td class="money">${money(item.receivable_vnd)}</td></tr>`).join('')}</tbody></table></section>
      <section class="card top-debtors"><h2><span class="icon">♟</span>Khách nợ nhiều nhất</h2><table class="table"><thead><tr><th>#</th><th>Khách</th><th>Mặt hàng</th><th class="money">Còn nợ</th><th>Nợ xa nhất từ</th></tr></thead><tbody>${data.top_debtors.map((item, index) => `<tr><td>${index + 1}</td><td>${customerLink(item.customer_id, item.name)}</td><td>${esc(item.commodity ?? '—')}</td><td class="money">${money(item.outstanding_vnd)}</td><td>${monthText(item.oldest_open_month)}</td></tr>`).join('')}</tbody></table></section>
      <section class="card todo"><h2><span class="icon">☷</span>Việc cần làm</h2>${todoGroup(todo.missing_price, 'Chuyến web thiếu đơn giá', item => `<div class="todo-row"><span>${customerLink(item.customer_id, item.name)}</span><span>${item.count} chuyến thiếu đơn giá &gt;</span></div>`)}${todoGroup(todo.pending_review, 'Chuyến CHỜ KIỂM', item => `<div class="todo-row"><span>${customerLink(item.customer_id, item.name)}</span><span>${item.count} chuyến CHỜ KIỂM &gt;</span></div>`)}${todoGroup(todo.no_baseline, 'Khách chưa có số dư đầu', item => `<div class="todo-row"><span>${customerLink(item.customer_id, item.name)}</span><span>Chưa có số dư đầu &gt;</span></div>`)}${todoGroup(todo.credit, 'Sổ đang dư tiền', item => `<div class="todo-row"><span>${customerLink(item.customer_id, item.name)}</span><span>Đang dư ${creditMoney(item.credit_vnd)} &gt;</span></div>`)}${Object.values(todo).every(items => !items.length) ? '<p class="empty">Không có việc cần làm.</p>' : ''}</section>
      <section class="card today"><h2><span class="icon">▣</span>Hôm nay</h2><div class="today-stats"><div class="today-stat"><strong>${data.today.trips}</strong>chuyến đã nhập</div><div class="today-stat"><strong>${data.today.receipts}</strong>phiếu thu</div><div class="today-stat"><strong>${money(data.today.received_vnd)}</strong>đã thu</div><div class="today-stat"><strong>${data.today.voids}</strong>phiếu đã hủy</div></div><table class="table"><thead><tr><th>Người nhập</th><th>Chuyến</th><th>Phiếu thu</th><th class="money">Đã thu</th></tr></thead><tbody>${data.today.by_actor.map(item => `<tr><td>${esc(item.actor)}</td><td>${item.trips}</td><td>${item.receipts}</td><td class="money">${money(item.received_vnd)}</td></tr>`).join('')}<tr><th>Tổng</th><th>${data.today.trips}</th><th>${data.today.receipts}</th><th class="money">${money(data.today.received_vnd)}</th></tr></tbody></table></section>
    </div>`;
  }

  function setupSearch(customers) {
    const input = document.querySelector('#customer-search');
    const results = document.querySelector('#customer-results');
    const draw = () => {
      const query = input.value.trim().toLocaleLowerCase();
      const found = customers.filter(item => item.name.toLocaleLowerCase().includes(query)).slice(0, 20);
      results.innerHTML = found.map(item => `<a role="option" href="/so-khach-v7-live.html?customer=${encodeURIComponent(item.id)}">${esc(item.name)}</a>`).join('');
      results.hidden = !query || !found.length;
    };
    input.addEventListener('input', draw);
    input.addEventListener('focus', draw);
    document.addEventListener('click', event => { if (!event.target.closest('.search')) results.hidden = true; });
  }

  async function load() {
    try {
      const response = await fetch('/api/v7/dashboard', { cache: 'no-store' });
      if (!response.ok) throw Error('Không tải được tổng quan công nợ.');
      const data = await response.json();
      const [year, month, day] = data.as_of.split('-');
      document.querySelector('#as-of').textContent = `Tính đến ${day}/${month}/${year}`;
      const banner = document.querySelector('#demo-banner');
      if (data.demo || data.real_copy) {
        banner.hidden = false;
        banner.textContent = data.real_copy ? 'Dữ liệu thật · bản sao cô lập, chưa phải prod' : 'Dữ liệu thử · DỮ LIỆU GIẢ · Không phải sổ thật';
      }
      render(data);
      try {
        const customerResponse = await fetch('/api/v7/customers', { cache: 'no-store' });
        if (customerResponse.ok) setupSearch((await customerResponse.json()).customers ?? []);
      } catch {
        // Summary remains usable when optional customer search is unavailable.
      }
    } catch (error) {
      const alert = document.querySelector('#error');
      alert.hidden = false;
      alert.textContent = error.message;
      root.replaceChildren();
    }
  }

  load();
})();
