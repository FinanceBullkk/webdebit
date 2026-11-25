/* Menu trái dùng chung (3/11/2026): mọi trang đặt <aside class="app-nav" data-active="…"></aside> rồi nạp file này trước
 * script của trang. File vẽ nút ☰, ô Tìm khách, các mục điều hướng và số "sổ còn việc" trên mục Quản trị — cùng cách đếm
 * với trang Việc cần làm (InboxTable.books: việc từ Sheet + chuyến thiếu giá, chờ kiểm, số dư đầu, sổ chưa gán mặt hàng).
 * Trang đã có số liệu thì báo qua AppNav.setCustomers / AppNav.setTodoCount (data-count="page") để khỏi đọc API hai lần;
 * trang khác thì file tự đọc. Không ghi gì lên server; chỉ lưu số đếm gần nhất trên máy (localStorage) và bản số liệu Việc cần
 * làm gần nhất trong tab (sessionStorage, đóng tab là hết) để bấm sang trang đó thấy bảng ngay.
 * QUYEN-02: mục Quản trị và dải thẻ (xem ADMIN_TABS).
 * QUYEN-01 (20/11/2026): máy chủ gắn data-role="user" vào <html> cho login không phải quản lý; khi đó menu chỉ còn các
 * trang làm sổ, không có số Việc cần làm, và mọi link tới trang quản lý trên trang (cả menu viết sẵn của Sổ khách) bị bỏ. */
globalThis.AppNav = (() => {
  'use strict';
  // cong-no-format.js khai báo CongNoFormat bằng const ở tầm script: dùng tên trực tiếp, không có trên globalThis.
  const F = CongNoFormat;
  const svg = paths => `<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
  // Chỉ máy chủ quyết vai trò; thiếu thuộc tính là quản lý (dev, test, bản cài chưa đặt danh sách quản lý).
  const isAdmin = () => document.documentElement.dataset.role !== 'user';
  const ADMIN_PAGES = ['/viec-can-lam.html', '/may-chay.html', '/doi-xe.html', '/doi-xe-bang-ke.html', '/thong-tin-cty.html',
    '/nhat-ky-cong-viec.html', '/nguoi-dung.html', '/doi-no.html', '/sheet-trip-queue.html', '/khach.html'];
  // Bánh răng (25/11/2026, nét theo bộ Lucide, giấy phép ISC): hình mặt trời cũ khó nhận ra là Quản trị.
  const ICON_QUAN_TRI = '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle>';
  const THU_CHI_ICON = '<path d="M4 8h13l-3-3M20 16H7l3 3"></path>';   // hai mũi tên tiền vào, tiền ra
  // QUYEN-02 (20/11/2026): năm trang làm sổ cho mọi người; quản lý có thêm một mục Quản trị (vào thẳng Việc cần làm, mang số
  // "sổ còn việc"), các màn quản lý chuyển nhau bằng dải thẻ ở đầu trang.
  const PAGES = [
    ['tong-quan', '/dashboard-v7.html', 'Tổng quan', '<rect x="4" y="4" width="7" height="7" rx="1"></rect><rect x="13" y="4" width="7" height="7" rx="1"></rect><rect x="4" y="13" width="7" height="7" rx="1"></rect><rect x="13" y="13" width="7" height="7" rx="1"></rect>'],
    ['theo-thang', '/cong-no-theo-thang.html', 'Công nợ theo tháng', '<rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M4 10h16M9 3v4M15 3v4"></path>'],
    ['so-khach', '/so-khach-v7-live.html', 'Sổ khách', '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"></path><path d="M5 17a3 3 0 0 1 3-3h11"></path>'],
    ['bang-thu', '/bang-thu.html', 'Bảng thu', '<rect x="3" y="6" width="18" height="12" rx="2"></rect><circle cx="12" cy="12" r="2.5"></circle><path d="M6.5 9.5v.01M17.5 14.5v.01"></path>'],
    ['bao-cao-thang', '/bao-cao-thang.html', 'Báo cáo tháng', '<path d="M5 3h10l4 4v14H5z"></path><path d="M15 3v4h4M8 17v-3M12 17v-6M16 17v-4"></path>'],
    // Thu chi (QUYEN-01 sửa đổi 25/11/2026): quản lý vào từ dải thẻ Quản trị; người dùng có mục riêng ở menu.
    ...(isAdmin() ? [['quan-tri', '/viec-can-lam.html', 'Quản trị', ICON_QUAN_TRI]]
      : [['thu-chi', '/thu-chi.html', 'Thu chi', THU_CHI_ICON]]),
  ];
  const ADMIN_TABS = [
    ['viec-can-lam', '/viec-can-lam.html', 'Việc cần làm'], ['may-chay', '/may-chay.html', 'Máy chạy'], ['doi-xe', '/doi-xe.html', 'Đội xe'],
    ['thong-tin-cty', '/thong-tin-cty.html', 'Thông tin cty'], ['thu-chi', '/thu-chi.html', 'Thu chi'], ['nhat-ky', '/nhat-ky-cong-viec.html', 'Nhật ký'], ['nguoi-dung', '/nguoi-dung.html', 'Người dùng'],
    ['khach', '/khach.html', 'Khách'],   // KHACH-WEB-01: tạo sổ, gán tên chủ hàng booking
  ];
  const UNDER_ADMIN = new Set(ADMIN_TABS.map(([id]) => id));   // trang ẩn (Đòi nợ, Chuyến từ Sheet) không sáng mục nào
  const ledgerHref = id => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}`;
  const root = document.querySelector('aside.app-nav');
  let customers = null, loadingCustomers = null;

  // Quản trị mang lớp nav-admin để xuống đáy dải menu (app-nav.css), tách khỏi năm trang làm sổ.
  const navClass = (id, active) => {
    const names = [id === active && 'active', id === 'quan-tri' && 'nav-admin'].filter(Boolean);
    return (names.length ? ` class="${names.join(' ')}"` : '') + (id === active ? ' aria-current="page"' : '');
  };

  function mount() {
    const active = isAdmin() && UNDER_ADMIN.has(root.dataset.active) ? 'quan-tri' : root.dataset.active;
    root.innerHTML = `<button type="button" id="nav-toggle" aria-label="Mở menu" aria-expanded="false">${svg('<path d="M4 6h16M4 12h16M4 18h16"></path>')}</button>`
      + `<label class="search">${svg('<circle cx="11" cy="11" r="6.5"></circle><path d="M16 16l4.5 4.5"></path>')}<span class="search-label">Tìm khách</span>`
      + '<input id="customer-search" type="search" aria-label="Tìm khách" placeholder="Tìm khách" autocomplete="off">'
      + '<div id="customer-results" role="listbox" hidden></div></label>'
      + `<nav aria-label="Điều hướng chính">${PAGES.map(([id, href, label, paths]) => `<a${navClass(id, active)} href="${href}">`
        + `${svg(paths)}${label}${id === 'quan-tri' ? '<span class="badge" id="todo-badge" data-todo-badge hidden></span>' : ''}</a>`).join('')}</nav>`;
    mountTabs(root.dataset.active);
    root.querySelector('#nav-toggle').addEventListener('click', event => {
      const expanded = event.currentTarget.getAttribute('aria-expanded') !== 'true';
      event.currentTarget.setAttribute('aria-expanded', String(expanded));
      event.currentTarget.setAttribute('aria-label', expanded ? 'Thu gọn menu' : 'Mở menu');
      root.classList.toggle('menu-open', expanded);
    });
    setupSearch();
  }

  // QUYEN-02: dải thẻ Quản trị ngay trước <main>, ngoài thanh đầu trang của từng màn (trang tự vẽ lại thanh đó).
  function mountTabs(current) {
    const main = document.querySelector('main');
    if (!isAdmin() || !UNDER_ADMIN.has(current) || !main || document.querySelector('.admin-tabs')) return;
    const tabs = document.createElement('nav');
    tabs.className = 'admin-tabs';
    tabs.setAttribute('aria-label', 'Quản trị');
    tabs.innerHTML = ADMIN_TABS.map(([id, href, label]) => `<a href="${href}"${id === current ? ' class="active" aria-current="page"' : ''}>${label}`
      + `${id === 'viec-can-lam' ? '<span class="tab-badge" data-todo-badge hidden></span>' : ''}</a>`).join('');
    main.before(tabs);
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
      loadingCustomers = CongNoNet.customers()
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
    for (const badge of document.querySelectorAll('#todo-badge, [data-todo-badge]')) {
      badge.textContent = count ? String(count) : '';
      badge.hidden = !count;
      badge.setAttribute('aria-label', `${count} sổ còn việc`);
    }
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

  // Trang không tự đếm: một lần đọc /api/v7/todo-badge (audit giao diện 23/11, F7) gộp ba nguồn của Việc cần làm (danh sách
  // nợ đã cắt chỉ còn mặt hàng), rồi đếm bằng chính InboxTable.books để số trên menu bằng số trên trang. Trước đây ba lượt gọi
  // (~87 KB mỗi lượt, mỗi 2 phút). Lỗi thì giữ số cũ, không báo lỗi trên menu.
  async function loadTodoCount() {
    if (!globalThis.InboxTable) return;
    const body = await fetch('/api/v7/todo-badge', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null);
    if (!body) return;
    const { inbox, dashboard, debt } = body;
    const key = typeof DashboardModel === 'undefined' ? null : DashboardModel.commodityKey;
    const unsorted = (debt?.customers ?? []).filter(row => (key ? key(row.commodity, row.transport_mode) === F.UNSORTED : !row.commodity))
      .map(row => ({ customer_id: row.customer_id, name: row.name, commodity: row.commodity }));
    setTodoCount(globalThis.InboxTable.books(inbox, dashboard, unsorted).length);
    // Sẵn ba nguồn rồi thì giữ lại: lần đầu bấm sang Việc cần làm cũng khỏi đợi (#342).
    if (inbox && dashboard && debt) {
      customers ??= await CongNoNet.customers().then(data => data?.customers ?? null, () => null);
      saveTodoSnapshot({ inbox, dashboard, unsorted, customers });
    }
  }

  // Người dùng: bỏ link tới trang quản lý đã có sẵn trong HTML (menu riêng của Sổ khách). Link vẽ sau lúc chạy thì
  // trang tự hỏi AppNav.isAdmin().
  function dropAdminLinks() {
    for (const link of document.querySelectorAll('a[href]')) {
      if (ADMIN_PAGES.includes(new URL(link.href, location.href).pathname)) link.remove();
    }
    // Menu viết sẵn của Sổ khách: người dùng có thêm mục Thu chi ở cuối, như menu dùng chung (QUYEN-01 sửa đổi 25/11/2026).
    const own = document.querySelector('.topbar > nav');
    if (own && !own.querySelector('a[href="/thu-chi.html"]')) {
      own.insertAdjacentHTML('beforeend', `<a href="/thu-chi.html">${svg(THU_CHI_ICON).replace('aria-hidden', 'fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden')}<span>Thu chi</span></a>`);
    }
  }

  // Sổ khách còn menu riêng (cùng số đo): không có <aside class="app-nav"> thì chỉ hiện số đệm, không đọc API.
  if (root) mount();
  if (!isAdmin()) dropAdminLinks();
  else paintCached();
  addEventListener('storage', event => { if (event.key === CACHE && isAdmin()) paintCached(); });
  if (root && root.dataset.count !== 'page' && isAdmin()) {
    loadTodoCount();
    setInterval(() => { if (!document.hidden) loadTodoCount(); }, 120_000);
  }
  return { isAdmin, setCustomers, setTodoCount, loadTodoCount, saveTodoSnapshot, readTodoSnapshot };
})();
