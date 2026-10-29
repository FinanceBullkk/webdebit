/* PRESENCE-01: ai đang online, đang ở đâu, ô đang chọn (mức 1), mũi tên chuột người khác (mức 2) — specs/v7-ai-dang-online.md.
 * Dùng chung cho mọi trang V7 có .topbar. Báo vị trí qua POST /api/v7/presence, nhận danh sách qua SSE
 * /api/v7/presence/stream; mất SSE thì hỏi định kỳ. Chỉ là chỉ báo: lỗi mạng không ảnh hưởng sổ. */
(() => {
  'use strict';
  const COLORS = ['#c2410c', '#15803d', '#7c3aed', '#0e7490', '#be185d', '#a16207', '#1d4ed8', '#4b5563'];
  const HEARTBEAT = 10000, POLL = 2000, RETRY_STREAM = 30000, LOST_AFTER = 30000, DEBOUNCE = 150, MOVE_GAP = 200;
  const HIDE_KEY = 'presence-hide-pointers';
  const PAGE_NAMES = { dashboard: 'Tổng quan', 'cong-no-theo-thang': 'Công nợ theo tháng', 'sheet-queue': 'Chuyến từ Sheet', 'viec-can-lam': 'Việc cần làm' };
  const BOOK_LINK = /so-khach-v7-live\.html\?customer=([1-9][0-9]*)/;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);

  function tabId() {
    const fresh = () => Array.from(crypto.getRandomValues(new Uint8Array(12)), b => b.toString(16).padStart(2, '0')).join('');
    try {
      const saved = sessionStorage.getItem('presence-tab');
      if (saved && /^[a-f0-9]{24}$/.test(saved)) return saved;
      const id = fresh();
      sessionStorage.setItem('presence-tab', id);
      return id;
    } catch { return fresh(); }
  }

  function monthText(month) { return month ? `tháng ${Number(month.slice(5, 7))}/${month.slice(0, 4)}` : ''; }

  // options: page, customerId?, position() -> {month, cell}, decorate(people)?, onJump(person)?,
  // pointer() -> {row, col, fx, fy} | null và locate(anchor) -> ô (mức 2, chỉ sổ khách).
  function start(options) {
    const topbar = document.querySelector('.topbar');
    if (!topbar || typeof fetch !== 'function') return null;
    const tab = tabId();
    const names = new Map();
    let people = [], lastOk = Date.now(), lost = false, stream = null, polling = null, pending = null, namesAsked = false;
    let avatarsKey = '', lastMove = 0, moveTimer = null, hidePointers = false;
    try { hidePointers = localStorage.getItem(HIDE_KEY) === '1'; } catch { /* trình duyệt chặn lưu: mặc định hiện */ }
    const bar = document.createElement('div');
    bar.className = 'presence';
    bar.setAttribute('aria-label', 'Người đang mở web');
    topbar.append(bar);
    const pointers = options.pointer ? document.createElement('div') : null;
    const toggle = options.pointer ? document.createElement('button') : null;
    if (pointers) {
      pointers.className = 'presence-pointers';
      pointers.setAttribute('aria-hidden', 'true');
      document.body.append(pointers);
      toggle.type = 'button';
      toggle.className = 'presence-toggle';
      topbar.append(toggle);
    }

    const sameBook = person => options.customerId != null && person.page === 'so-khach' && person.customer_id === options.customerId;
    const where = person => {
      if (person.page !== 'so-khach') return `đang ở ${PAGE_NAMES[person.page] ?? 'trang khác'}`;
      const book = sameBook(person) ? 'sổ này' : `sổ ${names.get(person.customer_id) ?? `khách #${person.customer_id}`}`;
      return `đang mở ${book}${person.month ? `, ${monthText(person.month)}` : ''}${person.cell?.editing ? ' · đang sửa' : ''}`;
    };

    async function loadNames() {
      if (namesAsked) return;
      namesAsked = true;
      try {
        const response = await fetch('/api/v7/customers');
        const data = response.ok ? await response.json() : null;
        for (const row of data?.customers ?? []) names.set(row.id, row.name);
        render();
      } catch { /* thiếu tên thì hiện mã sổ */ }
    }

    function render() {
      lost = Date.now() - lastOk > LOST_AFTER;
      bar.classList.toggle('presence-off', lost);
      if (people.some(person => person.page === 'so-khach' && !sameBook(person))) loadNames();
      const sorted = [...people].sort((a, b) => sameBook(b) - sameBook(a));
      // Con trỏ đổi 5 lần/giây; chỉ vẽ lại vòng tròn khi thông tin trên đó đổi, để chú thích đang mở không chớp.
      const key = JSON.stringify([lost, hidePointers, [...names], sorted.map(person => [person.id, person.name, person.color, person.page, person.customer_id, person.month, Boolean(person.cell?.editing)])]);
      if (key === avatarsKey) { decorate(); return; }
      avatarsKey = key;
      if (toggle) {
        toggle.textContent = hidePointers ? 'Hiện con trỏ' : 'Ẩn con trỏ';
        toggle.title = hidePointers ? 'Hiện mũi tên chuột của người khác' : 'Ẩn mũi tên chuột của người khác (vẫn thấy ô họ đang chọn)';
        toggle.setAttribute('aria-pressed', String(hidePointers));
      }
      bar.innerHTML = (lost ? '<span class="presence-lost">Không thấy được người khác</span>' : '') + sorted.map(person => {
        const text = `${person.name} · ${where(person)}`;
        return `<button type="button" class="presence-avatar${sameBook(person) ? '' : ' away'}" data-person="${esc(person.id)}" style="--pc:${COLORS[person.color % COLORS.length]}" aria-label="${esc(text)}">${esc(person.name.slice(0, 1).toUpperCase())}<span class="presence-tip" aria-hidden="true">${esc(text)}</span></button>`;
      }).join('');
      decorate();
    }

    const observer = new MutationObserver(() => requestAnimationFrame(decorate));
    function decorate() {
      observer.disconnect();
      try {
        const shown = lost ? [] : people;
        for (const node of document.querySelectorAll('.presence-dots')) node.remove();
        // Mọi chỗ trỏ tới một sổ khách: liên kết mở sổ, hàng khách trên Tổng quan (data-khach).
        for (const link of document.querySelectorAll('a[href*="so-khach-v7-live.html?customer="],[data-khach]')) {
          if (link.closest('.topbar,.presence')) continue;
          const id = Number(link.dataset.khach ?? link.getAttribute('href').match(BOOK_LINK)?.[1]);
          const here = shown.filter(person => person.page === 'so-khach' && person.customer_id === id);
          if (!here.length) continue;
          const dots = document.createElement('span');
          dots.className = 'presence-dots';
          dots.innerHTML = here.map(person => `<span class="presence-dot" style="--pc:${COLORS[person.color % COLORS.length]}" title="${esc(person.name)} đang mở sổ này" role="img" aria-label="${esc(person.name)} đang mở sổ này"></span>`).join('');
          (link.querySelector('.nm') ?? link).append(dots);
        }
        options.decorate?.(shown.filter(sameBook), COLORS);
        drawPointers();
      } finally {
        observer.observe(document.body, { childList: true, subtree: true });
      }
    }

    // Mũi tên neo theo ô (dòng + cột + phần nghìn trong ô), nên đúng chỗ dù hai máy khác cỡ màn hình, zoom hay cuộn.
    function drawPointers() {
      if (!pointers) return;
      const keep = new Map([...pointers.children].map(node => [node.dataset.id, node]));
      const shown = lost || hidePointers ? [] : people.filter(person => sameBook(person) && person.pointer);
      for (const person of shown) {
        const cell = options.locate(person.pointer);
        const box = cell?.getBoundingClientRect();
        if (!box || !box.width) continue;
        let node = keep.get(person.id);
        keep.delete(person.id);
        if (!node) {
          node = document.createElement('div');
          node.className = 'presence-pointer';
          node.dataset.id = person.id;
          const color = COLORS[person.color % COLORS.length];
          node.style.setProperty('--pc', color);
          node.innerHTML = `<svg width="18" height="22" viewBox="0 0 18 22"><path d="M1 1l15 11-7 1-3 7z" fill="${color}" stroke="#fff" stroke-width="1.5"/></svg><b>${esc(person.name)}</b>`;
          pointers.append(node);
        }
        node.style.left = `${box.left + scrollX + box.width * person.pointer.fx / 1000}px`;
        node.style.top = `${box.top + scrollY + box.height * person.pointer.fy / 1000}px`;
      }
      for (const node of keep.values()) node.remove();
    }

    function update(list) {
      lastOk = Date.now();
      if (Array.isArray(list)) people = list.filter(person => person && typeof person.name === 'string' && Number.isInteger(person.color));
      render();
    }

    function body(page = options.page) {
      const position = page ? (options.position?.() ?? {}) : {};
      return JSON.stringify({ tab, page, customer_id: page ? options.customerId ?? null : null,
        month: position.month ?? null, cell: position.cell ?? null,
        pointer: page && !document.hidden ? options.pointer?.() ?? null : null });
    }

    async function send() {
      try {
        const response = await fetch('/api/v7/presence', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body() });
        if (response.ok) update((await response.json()).people);
      } catch { /* mất mạng: nhịp sau gửi lại */ }
    }

    function report() {
      clearTimeout(pending);
      pending = setTimeout(send, DEBOUNCE);
    }

    // Chuột di: gửi ngay nhưng tối đa 5 lần/giây; lần cuối luôn được gửi.
    function move() {
      clearTimeout(moveTimer);
      const wait = lastMove + MOVE_GAP - Date.now();
      if (wait > 0) { moveTimer = setTimeout(move, wait); return; }
      lastMove = Date.now();
      clearTimeout(pending);
      send();
    }

    function poll(on) {
      if (on && !polling) polling = setInterval(send, POLL);
      if (!on && polling) { clearInterval(polling); polling = null; }
    }

    function openStream() {
      if (typeof EventSource !== 'function') { poll(true); return; }
      stream = new EventSource(`/api/v7/presence/stream?tab=${tab}`);
      stream.onopen = () => { poll(false); lastOk = Date.now(); };
      stream.addEventListener('presence', event => {
        try { update(JSON.parse(event.data).people); } catch { /* gói hỏng: chờ gói sau */ }
      });
      stream.onerror = () => {
        if (stream.readyState !== EventSource.CLOSED) return;   // đang tự nối lại
        stream = null;
        poll(true);
        setTimeout(openStream, RETRY_STREAM);
      };
    }

    bar.addEventListener('click', event => {
      const button = event.target.closest('.presence-avatar');
      const person = button && people.find(item => item.id === button.dataset.person);
      if (person && sameBook(person)) options.onJump?.(person);
    });
    toggle?.addEventListener('click', () => {
      hidePointers = !hidePointers;
      try { localStorage.setItem(HIDE_KEY, hidePointers ? '1' : '0'); } catch { /* không nhớ được cũng không sao */ }
      render();
    });
    if (pointers) {
      let frame = 0;
      const redraw = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(drawPointers); };
      addEventListener('scroll', redraw, { capture: true, passive: true });
      addEventListener('resize', redraw);
    }
    document.addEventListener('focusin', report);
    document.addEventListener('focusout', report);
    addEventListener('pagehide', () => {
      try { fetch('/api/v7/presence', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body(null), keepalive: true }).catch(() => {}); } catch { /* đóng tab */ }
    });
    setInterval(send, HEARTBEAT);
    setInterval(() => { if ((Date.now() - lastOk > LOST_AFTER) !== lost) render(); }, 5000);
    render();
    send();
    openStream();
    return { report, move, people: () => people, sameBook };
  }

  window.Presence = { start, COLORS };
  // Trang không có phần riêng (Tổng quan, ma trận) tự bật qua <body data-presence="…">.
  const page = typeof document !== 'undefined' ? document.body?.dataset.presence : null;
  if (page) start({ page });
})();
