/* Menu trái dùng chung (3/11/2026): mọi trang đặt <aside class="app-nav" data-active="…"></aside> rồi nạp file này trước
 * script của trang. File vẽ nút ☰, ô Tìm khách, sáu mục điều hướng và số "sổ còn việc" trên mục Việc cần làm — cùng cách đếm
 * với trang Việc cần làm (InboxTable.books: việc từ Sheet + chuyến thiếu giá, chờ kiểm, số dư đầu, sổ chưa gán mặt hàng).
 * Trang đã có số liệu thì báo qua AppNav.setCustomers / AppNav.setTodoCount (data-count="page") để khỏi đọc API hai lần;
 * trang khác thì file tự đọc. Không ghi gì lên server; chỉ lưu số đếm gần nhất trên máy (localStorage) và bản số liệu Việc cần
 * làm gần nhất trong tab (sessionStorage, đóng tab là hết) để bấm sang trang đó thấy bảng ngay. */
globalThis.AppNav = (() => {
  'use strict';
  // cong-no-format.js khai báo CongNoFormat bằng const ở tầm script: dùng tên trực tiếp, không có trên globalThis.
  const F = CongNoFormat;
  const svg = paths => `<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
  const PAGES = [
    ['tong-quan', '/dashboard-v7.html', 'Tổng quan', '<rect x="4" y="4" width="7" height="7" rx="1"></rect><rect x="13" y="4" width="7" height="7" rx="1"></rect><rect x="4" y="13" width="7" height="7" rx="1"></rect><rect x="13" y="13" width="7" height="7" rx="1"></rect>'],
    ['theo-thang', '/cong-no-theo-thang.html', 'Công nợ theo tháng', '<rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M4 10h16M9 3v4M15 3v4"></path>'],
    ['so-khach', '/so-khach-v7-live.html', 'Sổ khách', '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"></path><path d="M5 17a3 3 0 0 1 3-3h11"></path>'],
    ['bang-thu', '/bang-thu.html', 'Bảng thu', '<rect x="3" y="6" width="18" height="12" rx="2"></rect><circle cx="12" cy="12" r="2.5"></circle><path d="M6.5 9.5v.01M17.5 14.5v.01"></path>'],
    ['viec-can-lam', '/viec-can-lam.html', 'Việc cần làm', '<path d="M9 6h11M9 12h11M9 18h11"></path><path d="M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"></path>'],
    ['may-chay', '/may-chay.html', 'Máy chạy', '<rect x="4" y="6" width="16" height="11" rx="2"></rect><path d="M8 21h8M12 17v4M8 11h2M13 11h3"></path>'],
  ];
  const ledgerHref = id => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}`;
  const root = document.querySelector('aside.app-nav');
  let customers = null, loadingCustomers = null;

  function mount() {
    const active = root.dataset.active;
    root.innerHTML = `<button type="button" id="nav-toggle" aria-label="Mở menu" aria-expanded="false">${svg('<path d="M4 6h16M4 12h16M4 18h16"></path>')}</button>`
      + `<label class="search">${svg('<circle cx="11" cy="11" r="6.5"></circle><path d="M16 16l4.5 4.5"></path>')}<span class="search-label">Tìm khách</span>`
      + '<input id="customer-search" type="search" aria-label="Tìm khách" placeholder="Tìm khách" autocomplete="off">'
      + '<div id="customer-results" role="listbox" hidden></div></label>'
      + `<nav aria-label="Điều hướng chính">${PAGES.map(([id, href, label, paths]) => `<a${id === active ? ' class="active" aria-current="page"' : ''} href="${href}">`
        + `${svg(paths)}${label}${id === 'viec-can-lam' ? '<span class="badge" id="todo-badge" hidden></span>' : ''}</a>`).join('')}</nav>`;
    root.querySelector('#nav-toggle').addEventListener('click', event => {
      const expanded = event.currentTarget.getAttribute('aria-expanded') !== 'true';
      event.currentTarget.setAttribute('aria-expanded', String(expanded));
      event.currentTarget.setAttribute('aria-label', expanded ? 'Thu gọn menu' : 'Mở menu');
      root.classList.toggle('menu-open', expanded);
    });
    setupSearch();
  }

  // Ô tìm khách: tên Sheet, tên hiển thị, nhãn, mặt hàng, tên gọi khác; bỏ dấu (MH-01), chữ Hán so nguyên chữ.
  function setupSearch() {
    const input = root.querySelector('#customer-search');
    const results = root.querySelector('#customer-results');
    const draw = () => {
      const raw = input.value.trim();
      if (!raw || !customers) { results.hidden = true; return; }
      const loose = F.fold(raw), exact = F.foldText(raw);
      const labels = F.customerLabels(customers);
      const found = customers.filter(item => [item.name, item.display_name, item.label, item.commodity, ...(item.aliases ?? [])]
        .some(value => (loose && F.fold(value).includes(loose)) || F.foldText(value).includes(exact))).slice(0, 20);
      results.innerHTML = found.map(item => `<a role="option" href="${ledgerHref(item.id)}">${F.esc(labels.get(String(item.id)))}</a>`).join('');
      results.hidden = !found.length;
    };
    const ready = () => {
      if (customers || loadingCustomers) return loadingCustomers;
      loadingCustomers = fetch('/api/v7/customers', { cache: 'no-store' }).then(r => (r.ok ? r.json() : Promise.reject(Error('customers'))))
        .then(body => { customers ??= body.customers ?? []; draw(); }).catch(() => { loadingCustomers = null; });
      return loadingCustomers;
    };
    input.addEventListener('focus', () => { ready(); draw(); });
    input.addEventListener('input', () => { ready(); draw(); });
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { results.hidden = true; input.blur(); return; }
      if (event.key === 'ArrowDown' && !results.hidden) { event.preventDefault(); results.querySelector('a')?.focus(); }
      if (event.key === 'Enter' && !results.hidden) results.querySelector('a')?.click();
    });
    results.addEventListener('keydown', event => {
      if (event.key === 'Escape') { results.hidden = true; input.focus(); }
      if (event.key === 'ArrowDown') { event.preventDefault(); document.activeElement.nextElementSibling?.focus(); }
      if (event.key === 'ArrowUp') { event.preventDefault(); (document.activeElement.previousElementSibling ?? input).focus(); }
    });
    document.addEventListener('click', event => { if (!event.target.closest('.app-nav .search')) results.hidden = true; });
  }

  function setCustomers(list) {
    if (!Array.isArray(list)) return;
    customers = list;
  }

  // Số vừa đếm được lưu trên máy để trang không tự đếm (Sổ khách: thẻ Sổ không gọi thêm API) vẫn hiện cùng số.
  const CACHE = 'webdebit.todoCount';
  function paint(count) {
    const badge = document.querySelector('#todo-badge');
    if (!badge) return;
    badge.textContent = count ? String(count) : '';
    badge.hidden = !count;
    badge.setAttribute('aria-label', `${count} sổ còn việc`);
  }
  function setTodoCount(n) {
    const count = Number.isInteger(n) && n > 0 ? n : 0;
    paint(count);
    try { localStorage.setItem(CACHE, JSON.stringify({ n: count, at: Date.now() })); } catch { /* chế độ riêng tư: chỉ mất số đệm */ }
  }
  function paintCached() {
    try {
      const saved = JSON.parse(localStorage.getItem(CACHE) ?? 'null');
      if (saved && Number.isInteger(saved.n) && Date.now() - saved.at < 30 * 60_000) paint(saved.n);
    } catch { /* không có số đệm thì để trống */ }
  }

  // Bản số liệu Việc cần làm gần nhất trong tab. Trang đó vẽ bản này ngay rồi đọc lại; bản cũ quá 8 tiếng (một ngày làm việc) thì bỏ. Bản cũ chỉ hiện tới khi đọc xong và nút ghi khóa trong lúc đó.
  const SNAPSHOT = 'webdebit.todoSnapshot.v1';
  function saveTodoSnapshot({ inbox, dashboard, unsorted, customers: list }) {
    if (!inbox || !dashboard || !unsorted || !list?.length || ['computing', 'unavailable'].includes(inbox.state) || inbox.failed?.length) return;
    try { sessionStorage.setItem(SNAPSHOT, JSON.stringify({ inbox, dashboard, unsorted, customers: list, at: Date.now() })); } catch { /* đầy hoặc bị chặn: lần sau đợi tải như thường */ }
  }
  function readTodoSnapshot() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(SNAPSHOT) ?? 'null');
      return saved && Date.now() - saved.at < 8 * 3_600_000 ? saved : null;
    } catch { return null; }
  }

  // Trang không tự đếm: đọc ba nguồn như trang Việc cần làm; nguồn nào lỗi thì giữ số cũ, không báo lỗi trên menu.
  async function loadTodoCount() {
    if (!globalThis.InboxTable) return;
    const json = url => fetch(url, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null);
    const [inbox, dashboard, debt] = await Promise.all([json('/api/v7/inbox'), json('/api/v7/dashboard'), json('/api/v7/dashboard/debt')]);
    if (!inbox && !dashboard) return;
    const key = typeof DashboardModel === 'undefined' ? null : DashboardModel.commodityKey;
    const unsorted = (debt?.customers ?? []).filter(row => (key ? key(row.commodity, row.transport_mode) === F.UNSORTED : !row.commodity))
      .map(row => ({ customer_id: row.customer_id, name: row.name, commodity: row.commodity }));
    setTodoCount(globalThis.InboxTable.books(inbox, dashboard, unsorted).length);
    // Sẵn ba nguồn rồi thì giữ lại: lần đầu bấm sang Việc cần làm cũng khỏi đợi.
    if (inbox && dashboard && debt) {
      customers ??= await json('/api/v7/customers').then(body => body?.customers ?? null);
      saveTodoSnapshot({ inbox, dashboard, unsorted, customers });
    }
  }

  // Sổ khách còn menu riêng (cùng số đo): không có <aside class="app-nav"> thì chỉ hiện số đệm, không đọc API.
  if (root) mount();
  paintCached();
  addEventListener('storage', event => { if (event.key === CACHE) paintCached(); });
  if (root && root.dataset.count !== 'page') {
    loadTodoCount();
    setInterval(() => { if (!document.hidden) loadTodoCount(); }, 120_000);
  }
  return { setCustomers, setTodoCount, loadTodoCount, saveTodoSnapshot, readTodoSnapshot };
})();
