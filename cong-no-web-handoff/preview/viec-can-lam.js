// Việc cần làm: bảng bốn cột đã chọn 2/11; nguồn việc Sheet + sổ web, ghi qua API hiện hành.
(() => {
  'use strict';
  const F = CongNoFormat;
  const M = DashboardModel;
  const root = document.querySelector('#todo-root');
  const { esc, foldText, customerLabels } = F;
  const ledgerHref = id => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}`;
  let loading = false;
  let sheetRefresh = null;
  let searchReady = false;
  let currentCustomers = [];
  let dashboard = null;
  let unsorted = null;
  // Hộp ngoại lệ P1: khối riêng, tải và lỗi riêng; đang tính thì hỏi lại sau 5 giây.
  const inboxRoot = document.querySelector('#inbox-root');
  let inboxTimer = null;
  let inboxLoading = false;
  const markUpdated = () => { const node = document.querySelector('#updated-at'); if (node) node.textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`; sheetRefresh?.paint(); };

  function setupSearch(customers) {
    currentCustomers = customers;
    if (searchReady) return;
    searchReady = true;
    const input = document.querySelector('#customer-search');
    const results = document.querySelector('#customer-results');
    const draw = () => {
      const query = foldText(input.value).trim();
      const labels = customerLabels(currentCustomers);
      const found = currentCustomers.filter(item => [item.name, item.display_name, item.label, item.commodity, ...(item.aliases ?? [])]
        .some(value => foldText(value).includes(query))).slice(0, 20);
      results.innerHTML = found.map(item => `<a role="option" href="${ledgerHref(item.id)}">${esc(labels.get(String(item.id)))}</a>`).join('');
      results.hidden = !query || !found.length;
    };
    input.addEventListener('input', draw);
    input.addEventListener('focus', draw);
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { results.hidden = true; return; }
      if (event.key === 'ArrowDown' && !results.hidden) { event.preventDefault(); results.querySelector('a')?.focus(); }
      if (event.key === 'Enter' && !results.hidden) results.querySelector('a')?.click();
    });
    document.addEventListener('click', event => { if (!event.target.closest('.search')) results.hidden = true; });
  }

  const json = async url => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw Error(url);
    return response.json();
  };

  async function load() {
    if (loading || inbox.busy || inbox.review || inbox.action) return;
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
        json('/api/v7/customers').then(body => body.customers ?? []).catch(() => null),
        json('/api/v7/dashboard/debt').catch(() => null),
      ]);
      unsorted = debt ? (debt.customers ?? []).filter(row => M.commodityKey(row.commodity, row.transport_mode) === M.UNSORTED)
        .map(row => ({ customer_id: row.customer_id, name: row.name, commodity: row.commodity })) : null;
      dashboard = data;
      root.replaceChildren();
      if (customers) setupSearch(customers);
      paintInbox();
      document.querySelector('#error').hidden = true;
      markUpdated();
      if (!customers || !debt) {
        const alert = document.querySelector('#error');
        alert.hidden = false;
        alert.textContent = 'Chưa tải đủ danh sách khách hoặc mặt hàng. Việc đang hiện có thể thiếu. Bấm Làm mới để thử lại.';
      }
    } catch {
      const alert = document.querySelector('#error');
      alert.hidden = false;
      // Audit UX 31/10/2026 (P1-6): một câu tiếng Việt "chuyện gì · cần làm gì" và nút Thử lại; không bao giờ hiện chữ của trình duyệt.
      alert.innerHTML = `${esc(F.loadError('việc cần làm'))} <button type="button" class="btn" data-retry>Thử lại</button>`;
      root.replaceChildren();
    } finally { loading = false; }
  }

  // Hộp P2 (specs/v7-hop-ngoai-le-p2.md): sổ đã chọn, khung xem lại, kết quả lần ghi; giữ qua các lần tự tải lại.
  const inbox = { data: undefined, selected: new Set(), selectedPrices: new Set(), review: null, result: null, busy: false, keys: new Map(), filter: '', open: null, details: new Map(), showAuto: false, action: null };
  const inboxLabel = book => {
    const row = currentCustomers.find(c => c.id === book.customer_id);
    if (!row) return `Sổ #${book.customer_id}`;
    const name = row.display_name ?? row.name;
    return currentCustomers.filter(c => (c.display_name ?? c.name) === name).length === 1 ? name : customerLabels(currentCustomers).get(String(row.id));
  };
  const drafts = new Map();
  const keptMemory = new Map();
  const draftKey = input => input.hasAttribute('data-manual-price') ? `price:${input.dataset.manualPrice}` : `reason:${input.dataset.reason}`;
  function paintInbox() {
    const active = document.activeElement;
    const scrollLeft = inboxRoot.querySelector('.work-scroll:has(.work-table)')?.scrollLeft ?? 0;
    const focusAttr = inboxRoot.contains(active) && ['data-pick', 'data-pick-price', 'data-filter', 'data-open-book', 'data-auto', 'data-review'].find(attr => active.hasAttribute(attr));
    const focusValue = focusAttr ? active.getAttribute(focusAttr) : null;
    inboxRoot.innerHTML = globalThis.InboxTable.render(inbox.data, {
      F, esc, href: ledgerHref, failedText: F.loadError('việc từ Sheet'), label: inboxLabel,
      selected: inbox.selected, selectedPrices: inbox.selectedPrices, review: inbox.review, result: inbox.result, busy: inbox.busy,
      dashboard, unsorted, filter: inbox.filter, open: inbox.open, details: inbox.details, showAuto: inbox.showAuto, action: inbox.action, actionHtml: actionHtml(), notice: inbox.notice,
    });
    const badge = document.querySelector('#todo-badge');
    const n = globalThis.InboxTable.books(inbox.data, dashboard, unsorted ?? []).length;
    badge.textContent = String(n);
    badge.hidden = !n;
    badge.setAttribute('aria-label', String(n) + ' sổ còn việc');
    const sheetAt = inbox.data?.sheet_at;
    document.querySelector('#sheet-clock').textContent = sheetAt ? new Date(sheetAt).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' }) : '—';
    for (const input of inboxRoot.querySelectorAll('[data-manual-price],[data-reason]')) input.value = drafts.get(draftKey(input)) ?? input.dataset.suggestedPrice ?? '';
    for (const input of inboxRoot.querySelectorAll('[data-manual-price]')) setPriceValidity(input);
    for (const input of inboxRoot.querySelectorAll('[data-pick],[data-pick-price]')) input.disabled = inbox.busy || !!inbox.review || !!inbox.action;
    if (focusAttr) inboxRoot.querySelector(`[${focusAttr}="${CSS.escape(focusValue)}"]:not(:disabled)`)?.focus({ preventScroll: true });
    const scroller = inboxRoot.querySelector('.work-scroll:has(.work-table)');
    if (scroller) scroller.scrollLeft = scrollLeft;
  }

  async function loadInbox() {
    if (inboxLoading || !globalThis.InboxCard || inbox.busy || inbox.review || inbox.action) return;   // không vẽ lại khi đang xem lại/ghi
    inboxLoading = true;
    clearTimeout(inboxTimer);
    try {
      const [data, customers] = await Promise.all([json('/api/v7/inbox'),
        currentCustomers.length ? currentCustomers : json('/api/v7/customers').then(body => body.customers ?? []).catch(() => [])]);
      inbox.data = data;
      if (!currentCustomers.length) currentCustomers = customers;
      // Bỏ chọn sổ không còn ghi được (đã ghi xong, phiếu đổi sang cần xem…).
      const writable = new Set((data.books ?? []).filter(globalThis.InboxCard.canWrite).map(book => book.customer_id));
      for (const id of inbox.selected) if (!writable.has(id)) inbox.selected.delete(id);
      for (const id of inbox.selectedPrices) if (!data.books?.some(b => b.customer_id === id && b.prices.ready)) inbox.selectedPrices.delete(id);
      inbox.details.clear();
    } catch { inbox.data = null; }
    paintInbox();
    if (inbox.data && (inbox.data.state === 'computing' || inbox.data.refreshing)) inboxTimer = setTimeout(loadInbox, 5_000);
    inboxLoading = false;
    if (inbox.open !== null) loadDetail(inbox.open);
  }

  async function loadDetail(id, force = false) {
    if (!force && inbox.details.has(id)) return;
    inbox.details.delete(id);
    paintInbox();
    try {
      const ledger = await json(`/api/v7/ledger?customer=${id}`);
      ledger.price_status = await json(`/api/v7/price-table/status?customer=${id}`).catch(() => null);
      const key = `sokhach-v7-sheet-giu:${id}:${ledger.sheet_sync?.snapshot_sha256 ?? ''}`;
      const kept = new Set(keptMemory.get(key) ?? []);
      try { for (const trip of JSON.parse(localStorage.getItem(key) ?? '[]')) kept.add(String(trip)); } catch { /* giữ bản trong phiên */ }
      if (ledger.sheet_sync?.removed_items) ledger.sheet_sync.removed_items = ledger.sheet_sync.removed_items.filter(r => !kept.has(String(r.trip_id)));
      inbox.details.set(id, ledger);
    }
    catch { inbox.details.set(id, null); }
    paintInbox();
  }

  async function reviewCombined() {
    if (inbox.busy || inbox.action || inbox.review) return;
    inbox.busy = true; paintInbox();
    try {
      const tasks = [], lines = [], rows = [];
      for (const id of new Set([...inbox.selected, ...inbox.selectedPrices])) {
        const ledger = await json(`/api/v7/ledger?customer=${id}`);
        const parts = [], kinds = [];
        let after = ledger.total_outstanding_vnd;
        const before = F.full(after); // validate known total before offering write
        if (inbox.selectedPrices.has(id)) {
          const price = ledger.sheet_prices;
          if (!price?.ready?.length || price.unavailable) throw Error('Giá từ Sheet đã đổi. Tải lại việc rồi chọn lại.');
          const plan = SoKhachV7Model.planSheetPrices(price.ready, after);
          after = plan.afterVnd.toString();
          parts.push(`${plan.count} giá Sheet`); kinds.push(['prices', price]);
        }
        if (inbox.selected.has(id)) {
          const receipt = ledger.sheet_receipts;
          if (!receipt?.ready?.length || receipt.unavailable) throw Error('Phiếu thu đã đổi. Tải lại việc rồi chọn lại.');
          const plan = SoKhachV7Model.planSheetReceipts(receipt.ready, after);
          after = plan.afterVnd.toString();
          parts.push(`${plan.count} phiếu thu`); kinds.push(['receipts', receipt]);
        }
        for (const [kind, part] of kinds) {
          if (!Number.isInteger(ledger.version) || !/^[0-9a-f]{64}$/.test(part.snapshot_sha256 ?? '')) throw Error('Sổ chưa đủ dữ liệu để ghi. Tải lại rồi chọn lại.');
          tasks.push({ count: part.ready.length, path: `/api/v7/sheet/${kind}`, body: { customer_id: id, expected_version: ledger.version,
            snapshot_sha256: part.snapshot_sha256, idempotency_key: crypto.randomUUID() }, kind, done: false });
        }
        const credit = F.toBig(after) < 0n ? ` · khách sẽ dư ${F.full(-F.toBig(after))}` : '';
        lines.push(`${inboxLabel({ customer_id: id })}: ${parts.join(' · ')}; còn nợ ${before} → ${F.full(after)}${credit}`);
        rows.push({ name: inboxLabel({ customer_id: id }), what: parts.join(' · '), before: ledger.total_outstanding_vnd, after, note: credit });
      }
      inbox.open = null;
      inbox.action = { title: 'Xem lại trước khi ghi', text: lines.join('\n'), rows, tasks, count: tasks.reduce((n, t) => n + t.count, 0), path: 'batch' };
    } catch {
      inbox.action = { title: 'Chưa xem lại được', text: 'Không tải đủ phiếu thu, giá hoặc số nợ của sổ. Tải lại rồi chọn lại; chưa ghi mục nào.' };
    }
    inbox.busy = false; paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus();
  }

  function reviewRemove(id) {
    if (inbox.action || inbox.review) return;
    const ledger = inbox.details.get(inbox.open);
    const row = ledger?.sheet_sync?.removed_items?.find(r => r.trip_id === id);
    if (!row || row.month_locked || !Number.isInteger(ledger.version)) return;
    const counted = row.status === 'confirmed' ? row.amount_vnd : '0';
    if (counted == null) return;
    const preview = `Còn nợ ${F.full(ledger.total_outstanding_vnd)} → ${F.full(globalThis.InboxCard.changePreview(ledger.total_outstanding_vnd, counted, '0'))}.`;
    inbox.action = { title: `Xóa chuyến ${row.container}`, id: inbox.open, rowKey: `removed:${id}`,
      inlineText: `Xóa chuyến · nợ ${globalThis.InboxTable.million(ledger.total_outstanding_vnd)} → ${globalThis.InboxTable.million(globalThis.InboxCard.changePreview(ledger.total_outstanding_vnd, counted, '0'))} tr`,
      text: `Sheet không còn dòng này. ${preview} Xóa trên web có ghi Lịch sử.`,
      path: '/api/v7/trips/delete', body: { customer_id: inbox.open, expected_version: ledger.version,
        trip_id: id, idempotency_key: crypto.randomUUID() } };
    paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus();
  }

  function reviewCommand(button) {
    if (inbox.action || inbox.review) return;
    const ledger = inbox.details.get(inbox.open);
    if (!Number.isInteger(ledger?.version)) return;
    const kind = button.dataset.command;
    const row = ledger.trips?.find(r => r.id === Number(button.dataset.trip));
    const body = { customer_id: inbox.open, expected_version: ledger.version, idempotency_key: crypto.randomUUID() };
    let title, text, path, inlineText;
    try {
      if (kind === 'ps' || kind === 'approve') {
        const part = kind === 'ps' ? ledger.ps_fees : ledger.sheet_sync;
        if (!/^[0-9a-f]{64}$/.test(part?.snapshot_sha256 ?? '')) throw Error();
        body.snapshot_sha256 = part.snapshot_sha256;
        if (kind === 'ps') {
          const plan = SoKhachV7Model.planPsFees(part.ready);
          if (!plan.same) throw Error();
          title = `Tách phụ phí cho ${plan.count} chuyến`;
          text = `Tổng phụ phí ${F.full(plan.totalVnd)}, tổng còn nợ ${F.full(ledger.total_outstanding_vnd)} giữ nguyên.`;
          path = '/api/v7/ps/fees';
        } else {
          const n = part.items.filter(r => r.sync_state === 'NEW').length;
          title = `Duyệt ${n} chuyến mới`;
          text = 'Chuyến vào sổ chưa có giá, chưa cộng nợ. Chuyến nghi trùng vào chờ kiểm.';
          path = '/api/v7/sheet/approve';
        }
      } else {
        if (!row || row.editable !== true) throw Error();
        body.trip_id = row.id;
        let next = '0';
        if (kind === 'price') {
          body.unit_price_vnd = globalThis.InboxTable.parseMillions(inboxRoot.querySelector(`[data-manual-price="${row.id}"]`).value);
          body.other_fee_vnd = row.other_fee_vnd;
          next = SoKhachV7Model.tripAmount({ unitPriceVnd: body.unit_price_vnd, otherFeeVnd: row.other_fee_vnd, container: row.container, status: row.status }).amountVnd.toString();
          title = `Ghi đơn giá ${F.full(body.unit_price_vnd)} cho ${row.container}`;
          path = '/api/v7/trips/price';
        } else {
          body.reason = '';
          body.decision = kind;
          next = kind === 'confirm' ? SoKhachV7Model.tripAmount({ unitPriceVnd: row.unit_price_vnd, otherFeeVnd: row.other_fee_vnd, container: row.container, status: 'confirmed' }).amountVnd?.toString() ?? '0' : '0';
          title = `${kind === 'confirm' ? 'Tính vào sổ' : 'Loại chuyến'} ${row.container}`;
          path = '/api/v7/trips/review';
        }
        text = `Còn nợ ${F.full(ledger.total_outstanding_vnd)} → ${F.full(globalThis.InboxCard.changePreview(ledger.total_outstanding_vnd, '0', next))}. ${body.reason ?? 'Chuyến bắt đầu tính nợ theo đơn giá đã nhập.'}`;
        inlineText = `${kind === 'price' ? `Ghi giá ${globalThis.InboxTable.million(body.unit_price_vnd)} tr` : kind === 'confirm' ? 'Chuyến riêng' : 'Bỏ chuyến'} · ${next === '0' ? 'nợ không đổi' : `nợ ${globalThis.InboxTable.million(ledger.total_outstanding_vnd)} → ${globalThis.InboxTable.million(globalThis.InboxCard.changePreview(ledger.total_outstanding_vnd, '0', next))} tr`}`;
      }
      inbox.action = { title, text, inlineText, path, body, id: inbox.open, rowKey: row ? `${kind === 'price' ? 'price' : 'review'}:${row.id}` : null, reasonRequired: kind === 'confirm' || kind === 'reject' };
      paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus();
    } catch {
      const alert = document.querySelector('#error');
      alert.hidden = false;
      alert.textContent = 'Chưa đủ thông tin để ghi. Nhập đơn giá bằng triệu đồng, dùng dấu phẩy cho phần lẻ; hoặc mở sổ để đối chiếu.';
    }
  }

  function actionHtml() {
    const a = inbox.action;
    if (!a) return '';
    if (a.rowKey) return '';
    if (a.rows) return `<section class="receipt-review" role="dialog" aria-labelledby="h-action"><h3 id="h-action">${esc(a.title)} · ${a.count} mục ở ${a.rows.length} sổ</h3><div class="work-scroll"><table><thead><tr><th>Khách</th><th>Ghi</th><th class="num">Còn nợ trước → sau <span class="muted">tr</span></th><th>Lưu ý</th></tr></thead><tbody>${a.rows.map(r => `<tr><td>${esc(r.name)}</td><td>${esc(r.what)}</td><td class="num action-description" title="${esc(`${F.full(r.before)} → ${F.full(r.after)}`)}">${globalThis.InboxTable.million(r.before)} → <strong>${globalThis.InboxTable.million(r.after)}</strong></td><td>${esc(r.note)}</td></tr>`).join('')}</tbody></table></div><p>Phiếu ghi đúng ngày trên Sheet, trừ vào nợ cũ trước. Chuyến có giá thì bắt đầu cộng vào nợ.</p>${a.error ? `<p role="alert">${esc(a.error)}</p>` : ''}<div class="actions">${a.path ? `<button class="btn primary" type="button" data-action-write${inbox.busy ? ' disabled' : ''}>${inbox.busy ? 'Đang ghi…' : a.unknown ? 'Thử lại' : `Ghi ${a.count} mục`}</button>` : ''}${a.unknown ? '' : '<button class="btn" type="button" data-action-cancel>Thôi</button>'}</div></section>`;
    return `<section class="receipt-review" role="dialog" aria-labelledby="h-action"><h3 id="h-action">${esc(a.title)}</h3><p class="action-description">${esc(a.text)}</p>${a.tasks ? '<p>Giá có nguồn mới bắt đầu tính nợ. Phiếu thu trừ nợ cũ trước; ngày trong tháng khóa vẫn ghi được.</p>' : ''}${a.error ? `<p role="alert">${esc(a.error)}</p>` : ''}<div class="actions">${a.path ? `<button type="button" class="btn primary" data-action-write${inbox.busy ? ' disabled' : ''}>${inbox.busy ? 'Đang ghi…' : a.unknown ? 'Thử lại' : 'Xác nhận'}</button>` : ''}${a.unknown ? '' : `<button type="button" class="btn" data-action-cancel${inbox.busy ? ' disabled' : ''}>Thôi</button>`}</div></section>`;
  }

  async function writeAction() {
    const a = inbox.action;
    if (!a?.path || inbox.busy) return;
    if (a.reasonRequired && !a.unknown) {
      const reason = inboxRoot.querySelector('[data-action-reason]');
      if (!reason?.value.trim() || reason.value.trim().length > 500) {
        reason?.setCustomValidity('Nhập lý do kết luận để lưu Lịch sử.'); reason?.reportValidity(); return;
      }
      a.body.reason = reason.value.trim();
    }
    inbox.busy = true; paintInbox();
    if (a.tasks) { await writeCombined(a); return; }
    try {
      const response = await fetch(a.path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(a.body) });
      const body = await response.json();
      a.unknown = false;
      if (!response.ok) {
        a.error = body.message ?? 'Chưa ghi được. Tải lại sổ rồi thử lại.';
        a.path = null;
      } else {
        inbox.action = null;
        if (a.body.trip_id) { drafts.delete(`price:${a.body.trip_id}`); drafts.delete(`reason:${a.body.trip_id}`); }
        inbox.details.delete(a.id);
        inbox.notice = body.complete === false ? `Đã ghi ${body.written ?? body.approved}; còn ${body.remaining} mục chưa ghi. Mở lại sổ để kiểm tra.` : `Đã xử lý: ${a.title}. Mở sổ xem Lịch sử nếu cần kiểm tra.`;
        await loadDetail(a.id, true);
      }
    } catch {
      a.unknown = true;
      a.error = 'Mất kết nối khi ghi: chưa rõ kết quả. Bấm Thử lại; yêu cầu giữ nguyên để không ghi trùng.';
    }
    inbox.busy = false; paintInbox();
    if (!inbox.action) { loadInbox(); load(); }
  }

  async function writeCombined(a) {
    try {
      for (const task of a.tasks.filter(t => !t.done)) {
        const response = await fetch(task.path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(task.body) });
        const body = await response.json();
        a.unknown = false;
        if (!response.ok || body.complete !== true) {
          a.path = null;
          a.error = body.message ?? `Ghi được ${body.written ?? 0} mục trong lô rồi dừng. Mở sổ kiểm tra; tải lại trước khi chọn lại.`;
          break;
        }
        task.done = true;
        if (task.kind === 'prices') inbox.selectedPrices.delete(task.body.customer_id); else inbox.selected.delete(task.body.customer_id);
        const next = a.tasks.find(t => !t.done && t.body.customer_id === task.body.customer_id);
        if (next) {
          if (!Number.isInteger(body.version)) { a.path = null; a.error = 'Đã ghi một lô; chưa nhận được phiên bản mới. Mở sổ kiểm tra trước khi làm tiếp.'; break; }
          next.body.expected_version = body.version;
        }
      }
      if (a.tasks.every(t => t.done)) {
        a.path = null;
        a.title = 'Đã ghi các mục đã chọn';
      } else a.title = `Đã ghi ${a.tasks.filter(t => t.done).length}/${a.tasks.length} lô theo sổ`;
    } catch {
      a.unknown = true;
      a.error = 'Mất kết nối khi ghi: chưa rõ kết quả lô đang ghi. Thử lại giữ nguyên yêu cầu, bỏ qua các lô đã xong.';
    }
    inbox.busy = false; paintInbox();
  }

  // Ghi phiếu của từng sổ đã xem lại bằng lệnh duyệt đang có. Khóa chống ghi trùng gắn với (sổ, phiên bản, bản chụp):
  // bấm lại hay "Thử lại" sau mất mạng dùng đúng khóa đó; sổ đã ghi một phần thì server báo sổ đã đổi, không ghi lại.
  async function writeReceipts() {
    const books = inbox.review ?? [];
    if (!books.length || inbox.busy) return;
    inbox.busy = true;
    paintInbox();
    const outcome = [];
    let unknown = false;
    for (const book of books) {
      const tag = `${book.customer_id}:${book.version}:${book.receipts.snapshot_sha256}`;
      if (!inbox.keys.has(tag)) inbox.keys.set(tag, globalThis.crypto?.randomUUID?.() ?? `hop-${Date.now()}-${Math.random().toString(16).slice(2)}`);
      const row = { customer_id: book.customer_id, written: 0, amount_vnd: book.receipts.ready_amount_vnd };
      try {
        const response = await fetch('/api/v7/sheet/receipts', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ customer_id: book.customer_id, expected_version: book.version,
            snapshot_sha256: book.receipts.snapshot_sha256, idempotency_key: inbox.keys.get(tag) }) });
        const body = await response.json();
        if (response.ok && body.complete) outcome.push({ ...row, ok: true, written: body.written });
        else if (response.ok) outcome.push({ ...row, ok: false, message: `Ghi được ${body.written}/${book.receipts.ready} phiếu rồi dừng. Mở sổ xem phiếu còn lại.` });
        else outcome.push({ ...row, ok: false, message: body.message ?? 'Chưa ghi được sổ này. Tải lại rồi thử lại.' });
      } catch {
        unknown = true;
        outcome.push({ ...row, ok: false, message: 'Mất kết nối khi ghi: chưa rõ sổ này đã ghi chưa. Bấm Thử lại (không ghi trùng).' });
      }
    }
    for (const row of outcome) if (row.ok) inbox.selected.delete(row.customer_id);
    inbox.result = { books: outcome, unknown };
    inbox.review = unknown ? books.filter(book => outcome.some(row => row.customer_id === book.customer_id && !row.ok)) : null;
    inbox.busy = false;
    paintInbox();
    if (!unknown) loadInbox();   // sổ vừa ghi được API tính lại ngay ở lần đọc này
  }

  inboxRoot.addEventListener('input', event => {
    if (event.target.matches('[data-action-reason]')) { event.target.setCustomValidity(''); return; }
    const input = event.target.closest('[data-manual-price],[data-reason]');
    if (input) { drafts.set(draftKey(input), input.value); if (input.hasAttribute('data-manual-price')) setPriceValidity(input); }
  });
  function setPriceValidity(input) {
    const button = input.closest('.detail-actions')?.querySelector('[data-command="price"]');
    if (!button) return;
    try { globalThis.InboxTable.parseMillions(input.value); button.disabled = inbox.busy; }
    catch { button.disabled = true; }
  }
  inboxRoot.addEventListener('change', event => {
    if (inbox.busy || inbox.review || inbox.action) return;
    const price = event.target.closest('[data-pick-price]');
    if (price) {
      const id = Number(price.dataset.pickPrice);
      if (price.checked) inbox.selectedPrices.add(id); else inbox.selectedPrices.delete(id);
      paintInbox(); return;
    }
    const pick = event.target.closest('[data-pick]');
    const all = event.target.closest('[data-pick-all]');
    if (!pick && !all) return;
    if (pick) {
      const id = Number(pick.dataset.pick);
      if (pick.checked) inbox.selected.add(id); else inbox.selected.delete(id);
    } else {
      const writable = (inbox.data?.books ?? []).filter(globalThis.InboxCard.canWrite).map(book => book.customer_id);
      inbox.selected = new Set(all.checked ? writable : []);
    }
    paintInbox();
  });
  inboxRoot.addEventListener('click', async event => {
    if (inbox.busy) return;
    const button = event.target.closest('button');
    if (!button) return;
    if ((inbox.action?.unknown || inbox.result?.unknown) && !button.matches('[data-action-write],[data-write-retry]')) return;
    if ((inbox.action || inbox.review) && !button.matches('[data-action-write],[data-action-cancel],[data-write],[data-write-retry],[data-review-cancel]')) return;
    if (button.hasAttribute('data-filter')) {
      inbox.filter = inbox.filter === button.dataset.filter ? '' : button.dataset.filter; paintInbox(); return;
    }
    if (button.hasAttribute('data-auto')) { inbox.showAuto = !inbox.showAuto; paintInbox(); return; }
    if (button.hasAttribute('data-pick-ready')) {
      inbox.selected = new Set((inbox.data?.books ?? []).filter(globalThis.InboxCard.canWrite).map(b => b.customer_id));
      inbox.selectedPrices = new Set((inbox.data?.books ?? []).filter(b => b.prices?.ready).map(b => b.customer_id));
      if (inbox.selectedPrices.size) { await reviewCombined(); return; }
      inbox.review = (inbox.data?.books ?? []).filter(b => inbox.selected.has(b.customer_id));
      inbox.result = null; paintInbox(); inboxRoot.querySelector('[data-write]')?.focus(); return;
    }
    if (button.hasAttribute('data-open-book')) {
      const id = Number(button.dataset.openBook);
      inbox.open = inbox.open === id ? null : id;
      paintInbox();
      inboxRoot.querySelector('[data-open-book="' + id + '"]')?.focus();
      if (inbox.open !== null) await loadDetail(id);
      return;
    }
    if (button.hasAttribute('data-detail-retry')) { await loadDetail(Number(button.dataset.detailRetry), true); return; }
    if (button.hasAttribute('data-remove-trip')) { reviewRemove(Number(button.dataset.removeTrip)); return; }
    if (button.hasAttribute('data-command')) { reviewCommand(button); return; }
    if (button.hasAttribute('data-keep-trip')) {
      const ledger = inbox.details.get(inbox.open);
      if (!ledger) return;
      const id = Number(button.dataset.keepTrip);
      const key = `sokhach-v7-sheet-giu:${inbox.open}:${ledger.sheet_sync.snapshot_sha256 ?? ''}`;
      try {
        const kept = new Set(JSON.parse(localStorage.getItem(key) ?? '[]'));
        kept.add(String(id)); localStorage.setItem(key, JSON.stringify([...kept]));
      } catch { /* sổ hiện hành cũng hỗ trợ trình duyệt chặn lưu cục bộ */ }
      const kept = new Set(keptMemory.get(key) ?? []);
      kept.add(String(id)); keptMemory.set(key, kept);
      ledger.sheet_sync.removed_items = ledger.sheet_sync.removed_items.filter(r => r.trip_id !== id);
      paintInbox(); return;
    }
    if (button.hasAttribute('data-action-cancel')) { inbox.action = null; paintInbox(); loadInbox(); return; }
    if (button.hasAttribute('data-action-write')) { await writeAction(); return; }
    if (event.target.closest('[data-inbox-retry]')) { loadInbox(); return; }
    if (event.target.closest('[data-review]')) {
      if (inbox.selectedPrices.size) { await reviewCombined(); return; }
      inbox.action = null;
      inbox.result = null;
      inbox.review = (inbox.data?.books ?? []).filter(book => inbox.selected.has(book.customer_id) && globalThis.InboxCard.canWrite(book));
      paintInbox();
      inboxRoot.querySelector('[data-write]')?.focus();
      return;
    }
    if (event.target.closest('[data-review-cancel]')) { inbox.review = null; paintInbox(); return; }
    if (event.target.closest('[data-write]') || event.target.closest('[data-write-retry]')) writeReceipts();
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || inbox.busy) return;
    if (inbox.action?.unknown || inbox.result?.unknown) return;
    inbox.review = null; inbox.action = null; paintInbox();
    inboxRoot.querySelector('[data-review]')?.focus();
  });
  document.querySelector('#nav-toggle').addEventListener('click', event => {
    const button = event.currentTarget;
    const expanded = button.getAttribute('aria-expanded') !== 'true';
    button.setAttribute('aria-expanded', String(expanded));
    button.closest('.todo-nav').classList.toggle('menu-open', expanded);
  });

  load();
  loadInbox();
  const refresh = () => { if (document.activeElement?.id === 'customer-search') return; load(); loadInbox(); sheetRefresh?.load(); };
  document.querySelector('#error').addEventListener('click', event => { if (event.target.closest('[data-retry]')) load(); });
  const button = document.querySelector('#refresh-data');
  if (globalThis.SheetRefresh) {
    sheetRefresh = globalThis.SheetRefresh.create({ node: document.querySelector('#updated-at'), button, onDone: () => { load(); loadInbox(); } });
    sheetRefresh.load();
  }
  button?.addEventListener('click', () => { load(); loadInbox(); sheetRefresh?.trigger(); });
  setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
