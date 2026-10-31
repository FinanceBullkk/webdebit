/* Sổ khách V7 bản live — trang khách (TRANG-KHACH-01, specs/v7-trang-khach.md, PR A1): phần trái của đầu trang (← Quay lại,
 * tên khách, mặt hàng, thanh bốn thẻ Tình hình · Sổ · Trao đổi · Hồ sơ) và việc đổi thẻ. Thẻ Sổ là sổ khách của SO-GON-04,
 * không đổi gì. Đổi thẻ chỉ ghi thẻ lên <body data-the> (so-khach-v7.css ẩn/hiện, DOM giữ nguyên nên chữ đang gõ ở thẻ Sổ còn
 * nguyên) và đổi địa chỉ bằng history.replaceState: không tải lại trang, Back về trang trước chứ không lùi từng thẻ.
 * Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).tabs = ctx => {
  'use strict';
  const { root, live, customerId, escape } = ctx;
  const TABS = [['tinh-hinh', 'Tình hình'], ['so', 'Sổ'], ['trao-doi', 'Trao đổi'], ['ho-so', 'Hồ sơ']];
  // Thẻ chưa có nội dung (PR A2, A3): thẻ sẽ trả lời gì.
  const SOON = { 'tinh-hinh': 'khách đang nợ bao nhiêu, quá hạn bao nhiêu, nợ đang tăng hay giảm, khách còn đi hàng không',
    'trao-doi': 'phiếu thu, lần nhắc nợ và tin Zalo của khách', 'ho-so': 'mặt hàng, giá đang áp, cột phụ phí, ảnh chứng từ, hạn trả' };
  const known = id => TABS.some(([tab]) => tab === id);
  const query = new URLSearchParams(location.search);
  // K2: địa chỉ không ghi thẻ thì mở Sổ; có month= hoặc loc= thì luôn mở Sổ — mọi link cũ giữ nguyên nghĩa.
  let current = query.has('month') || query.has('loc') || !known(query.get('the')) ? 'so' : query.get('the');
  const scrolls = new Map();   // chỗ cuộn của từng thẻ: quay lại thẻ Sổ đúng chỗ đang làm
  const mark = () => { if (document.body) document.body.dataset.the = current; };
  mark();
  // Ô tìm khách lên thanh trên như các trang khác (audit UX 4.1) để đầu trang đủ chỗ; dời ngay lúc cài (sổ đọc lỗi vẫn tìm được
  // khách khác), giữ trình nghe của so-khach-v7-api.js.
  const picker = document.querySelector('#customer-picker'), topbar = document.querySelector('.topbar');
  if (picker?.id === 'customer-picker' && topbar) {
    topbar.append(picker);
    picker.classList.add('in-bar');
    const search = picker.querySelector('#customer-search');
    search.placeholder = 'Tìm khách để mở sổ';
    search.addEventListener('focus', () => search.select());
  }

  // ← Quay lại (audit UX 4.1): về trang vừa đến bằng lịch sử của tab (máy chủ gửi Referrer-Policy: no-referrer nên trang không
  // biết trang trước là trang nào); tab mới mở, chưa có trang trước, thì về Tổng quan.
  const backLink = () => (window.history?.length > 1
    ? '<a class="page-back" href="/dashboard-v7.html" data-back="lich-su">← Quay lại</a>'
    : '<a class="page-back" href="/dashboard-v7.html">← Tổng quan</a>');
  // Tên khách viết đủ, không cắt (audit P1-1): tên dài thì xuống dòng, chữ nhỏ một cỡ; mặt hàng · cảng/bộ chữ nhạt bên cạnh.
  function who() {
    const label = live.customerName(customerId) ?? `#${customerId}`;
    const row = live.customerRow?.(customerId);
    const name = String(row?.display_name ?? row?.name ?? '');
    const meta = name && label.startsWith(`${name} · `) ? label.slice(name.length + 3) : '';
    const shown = meta ? name : label;
    return `<div class="page-who${shown.length > 30 ? ' long' : ''}"><h1 class="page-name">${escape(shown)}</h1>`
      + `${meta ? `<span class="page-meta">${escape(meta)}</span>` : ''}</div>`;
  }
  // Thẻ Sổ kèm số việc chờ, cùng cách đếm với chấm cam trên chip tháng (SO-GON-04 L1.3; `work` do so-khach-v7-month-ui.js đếm).
  function tabBar(work) {
    return `<div class="page-tabs" role="tablist" aria-label="Các thẻ của khách">${TABS.map(([id, name]) => {
      const count = id === 'so' && work > 0 ? work : 0;
      return `<button type="button" role="tab" class="page-tab" id="tab-${id}" data-the="${id}" aria-controls="the-${id}" `
        + `aria-selected="${id === current}" tabindex="${id === current ? 0 : -1}"`
        + `${count ? ` aria-label="${name} · ${count} việc chờ" title="${count} việc chờ ở các tháng"` : ''}>${name}`
        + `${count ? `<span class="tab-work" aria-hidden="true">${count}</span>` : ''}</button>`;
    }).join('')}</div>`;
  }
  const pageHead = work => backLink() + who() + tabBar(work);
  const tabPanes = () => TABS.filter(([id]) => id !== 'so').map(([id, name]) =>
    `<section class="tab-pane tab-soon" id="the-${id}" role="tabpanel" aria-labelledby="tab-${id}"><h2>${name}</h2>`
    + `<p>Thẻ này đang làm, có trong bản sau: ${SOON[id]}.</p><p>Bây giờ số của khách xem ở thẻ Sổ.</p>`
    + '<button type="button" class="tab-go" data-the="so">Mở thẻ Sổ</button></section>').join('');

  // Đổi thẻ: ghi thẻ lên <body>, tô thẻ, đổi địa chỉ (thẻ Sổ không ghi the=; rời Sổ thì bỏ month= và loc= vì hai tham số đó
  // luôn mở Sổ), về chỗ cuộn cũ của thẻ. Ghi phiếu thu (so-khach-v7-entry-ui.js) gọi showTab('so') trước khi mở khung.
  function showTab(id) {
    if (!known(id) || id === current) return;
    scrolls.set(current, window.scrollY);
    current = id;
    mark();
    for (const tab of root.querySelectorAll('.page-tab')) {
      tab.setAttribute('aria-selected', String(tab.dataset.the === id));
      tab.tabIndex = tab.dataset.the === id ? 0 : -1;
    }
    const next = new URLSearchParams(location.search);
    if (id === 'so') next.delete('the');
    else { next.set('the', id); next.delete('month'); next.delete('loc'); }
    window.history.replaceState(window.history.state, '', `${location.pathname}?${next}${location.hash}`);
    window.scrollTo({ top: scrolls.get(id) ?? 0, behavior: 'instant' });
    // Sổ tự cập nhật lúc đang ẩn thì phần đo vị trí (danh sách phiếu dính, chip tháng đang xem) đo sai: đo lại khi hiện.
    if (id === 'so') { window.dispatchEvent(new Event('resize')); window.dispatchEvent(new Event('scroll')); }
  }

  root.addEventListener('click', event => {
    const back = event.target.closest('.page-back[data-back]');
    if (back && event.button === 0 && !(event.ctrlKey || event.metaKey || event.shiftKey)) { event.preventDefault(); window.history.back(); return; }
    const tab = event.target.closest('.page-tab,.tab-go');
    if (!tab) return;
    showTab(tab.dataset.the);
    if (tab.matches('.tab-go')) root.querySelector(`#tab-${tab.dataset.the}`)?.focus();
  });
  // Bàn phím theo mẫu thanh thẻ WAI-ARIA, bấm mới mở: mũi tên trái/phải (vòng), Home/End chuyển tiêu điểm; Enter/Space mở thẻ.
  root.addEventListener('keydown', event => {
    const tab = event.target.closest?.('.page-tab');
    if (!tab || event.altKey || event.ctrlKey || event.metaKey) return;
    const tabs = [...root.querySelectorAll('.page-tab')], at = tabs.indexOf(tab);
    const to = { ArrowRight: at + 1, ArrowLeft: at - 1 + tabs.length, Home: 0, End: tabs.length - 1 }[event.key];
    if (to === undefined) return;
    event.preventDefault();
    tabs[to % tabs.length].focus();
  });

  Object.assign(ctx, { pageHead, tabPanes, showTab });
};
