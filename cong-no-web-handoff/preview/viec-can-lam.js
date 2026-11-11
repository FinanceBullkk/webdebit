// Việc cần làm (VIEC-DOI-CHIEU-01): số nợ lệch, dọn chi tiết, máy đã làm; nguồn việc Sheet + sổ web, ghi qua API hiện hành.
(() => {
  'use strict';
  const F = CongNoFormat;
  const M = DashboardModel;
  const root = document.querySelector('#todo-root');
  const { esc, customerLabels } = F;
  const ledgerHref = id => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}`;
  let loading = false;
  let sheetRefresh = null;
  let currentCustomers = [];
  let dashboard = null;
  let unsorted = null;
  // Hộp ngoại lệ P1: khối riêng, tải và lỗi riêng; đang tính thì hỏi lại sau 5 giây.
  const inboxRoot = document.querySelector('#inbox-root');
  let inboxTimer = null;
  let inboxLoading = false;
  const markUpdated = () => { const node = document.querySelector('#updated-at'); if (node) node.textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`; sheetRefresh?.paint(); };

  const json = async url => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw Error(url);
    return response.json();
  };

  // Danh sách khách dùng chung cho hai lượt đọc đang chạy cùng lúc (số Tổng quan và việc từ Sheet): chỉ một request.
  let customersRead = null;
  const readCustomers = () => (customersRead ??= json('/api/v7/customers').then(body => body.customers ?? []).finally(() => { customersRead = null; }));

  async function load() {
    if (loading || inbox.busy || inbox.review || inbox.action) return;
    loading = true;
    try {
      // Đọc cùng lúc ba nguồn: đọc nối tiếp làm mở trang chậm thêm thời gian của /dashboard (0,25 giây trên hao).
      // Sổ cần gán mặt hàng lấy từ danh sách khách đang nợ của Tổng quan; danh sách nào lỗi thì chỉ bỏ nhóm đó.
      const [data, customers, debt] = await Promise.all([
        json('/api/v7/dashboard'),
        readCustomers().catch(() => null),
        json('/api/v7/dashboard/debt').catch(() => null),
      ]);
      const [year, month, day] = data.as_of.split('-');
      document.querySelector('#as-of').textContent = `Số liệu đến ${day}/${month}/${year}`;
      const banner = document.querySelector('#demo-banner');
      if (data.demo || data.real_copy) {
        banner.hidden = false;
        banner.textContent = data.real_copy ? 'Dữ liệu thật · bản sao cô lập, chưa phải prod' : 'Dữ liệu thử · DỮ LIỆU GIẢ · Không phải sổ thật';
      }
      unsorted = debt ? (debt.customers ?? []).filter(row => M.commodityKey(row.commodity, row.transport_mode) === M.UNSORTED)
        .map(row => ({ customer_id: row.customer_id, name: row.name, commodity: row.commodity })) : null;
      dashboard = data;
      firstLoadDone = true;
      if (customers) { currentCustomers = customers; globalThis.AppNav?.setCustomers(customers); }
      markFresh('dashboard');
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
      // Không đọc được bản mới thì không để bản cũ giả làm số hiện tại.
      if (inbox.stale) { dashboard = null; unsorted = null; inbox.stale = false; }
      firstLoadDone = true;
      paintInbox();
    } finally { loading = false; }
  }

  // Hộp P2 (specs/v7-hop-ngoai-le-p2.md): sổ đã chọn, khung xem lại, kết quả lần ghi; giữ qua các lần tự tải lại.
  const TAB_KEY = 'webdebit.todoTab';
  const savedTab = () => { try { const tab = sessionStorage.getItem(TAB_KEY); return ['lech', 'don', 'may'].includes(tab) ? tab : 'lech'; } catch { return 'lech'; } };
  const inbox = { data: undefined, selected: new Set(), selectedPrices: new Set(), review: null, result: null, busy: false, keys: new Map(), filter: '', open: null, details: new Map(), action: null, tab: savedTab(),
    tongOpen: false,   // danh sách chỗ tab TONG chưa cộng đủ (KIEM-TONG-01) đang mở; giữ qua các lần tự tải lại
    // Bảng đối chiếu: khách đang mở, số từng khách, khoản đang chọn, chuyến bỏ ra, nhóm đang xem từng dòng, kết quả lần ghi.
    dc: { open: null, closed: false, data: new Map(), sel: new Map(), off: new Map(), kept: new Map(), xem: new Set(), undo: new Map(), ai: new Map() },
    // Tab Đã làm (HOAT-DONG-01): ngày đang xem (null = hôm nay), lọc máy/người, bản đọc theo ngày (undefined đang tải, null lỗi).
    act: { day: null, filter: 'all', data: new Map(), loading: null } };
  const inboxLabel = book => {
    const row = currentCustomers.find(c => c.id === book.customer_id);
    if (!row) return `Sổ #${book.customer_id}`;
    const name = row.display_name ?? row.name;
    return currentCustomers.filter(c => (c.display_name ?? c.name) === name).length === 1 ? name : customerLabels(currentCustomers).get(String(row.id));
  };
  const drafts = new Map();
  const draftKey = input => input.hasAttribute('data-trip-book') ? `trip-book:${input.dataset.tripBook}` : input.hasAttribute('data-commodity') ? `commodity:${input.dataset.commodity}` : input.hasAttribute('data-transport') ? `transport:${input.dataset.transport}` : input.hasAttribute('data-receipt-date') ? `receipt-date:${input.dataset.receiptDate}` : input.hasAttribute('data-manual-price') ? `price:${input.dataset.manualPrice}` : `reason:${input.dataset.reason}`;
  // Tự tải lại chạy nền mỗi 60 giây và mỗi lần quay lại tab: dữ liệu không đổi thì không đụng DOM, để người đang làm không mất
  // ô đang gõ, danh sách đang mở hay cú bấm rơi đúng lúc thay DOM.
  let paintedHtml = null;
  // Lần mở đầu chờ đủ cả hai bên (số Tổng quan và việc từ Sheet) rồi mới vẽ, để không chớp "Chưa đủ dữ liệu" trong lúc đang tải.
  let firstLoadDone = false;
  const fresh = { dashboard: false, inbox: false };
  function markFresh(part) {
    fresh[part] = true;
    if (fresh.dashboard && fresh.inbox) inbox.stale = false;
    if (!inbox.stale) globalThis.AppNav?.saveTodoSnapshot({ inbox: inbox.data, dashboard, unsorted, customers: currentCustomers });
  }
  // Đang hiện bản cũ của tab: xem được, mở dòng được; mọi nút ghi khóa tới khi có bản mới (thường dưới 1 giây).
  const VIEW_ONLY = ['data-filter', 'data-open-book', 'data-tab', 'data-dc-open', 'data-dc-xem', 'data-dc-retry', 'data-act-day', 'data-act-date', 'data-act-filter', 'data-act-retry', 'data-tong-toggle'];
  function paintInbox() {
    if (!firstLoadDone || inbox.data === undefined) return;
    const html = globalThis.InboxTable.render(inbox.data, {
      F, esc, href: ledgerHref, failedText: F.loadError('việc từ Sheet'), label: inboxLabel,
      selected: inbox.selected, selectedPrices: inbox.selectedPrices, review: inbox.review, result: inbox.result, busy: inbox.busy,
      stale: inbox.stale, dashboard, unsorted, filter: inbox.filter, open: inbox.open, details: inbox.details, tab: inbox.tab, dc: inbox.dc, act: actView(), action: inbox.action, actionHtml: actionHtml(), notice: inbox.notice, tongOpen: inbox.tongOpen,
      undoHtml: inbox.undo?.length && !inbox.action && !inbox.review && !inbox.result?.unknown ? '<div class="inbox-result" role="status">Đã ghi các mục vừa chọn. <button type="button" class="btn" data-undo-batch>Hoàn tác</button></div>' : '',
    });
    root.replaceChildren();
    globalThis.AppNav?.setTodoCount(globalThis.InboxTable.books(inbox.data, dashboard, unsorted ?? []).length);
    const sheetAt = inbox.data?.sheet_at;
    document.querySelector('#sheet-clock').textContent = sheetAt ? new Date(sheetAt).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' }) : '—';
    if (html === paintedHtml) return;
    paintedHtml = html;
    const active = document.activeElement;
    const scrollLeft = inboxRoot.querySelector('.work-scroll:has(.work-table)')?.scrollLeft ?? 0;
    const focusAttr = inboxRoot.contains(active) && ['data-pick', 'data-pick-price', 'data-filter', 'data-open-book', 'data-tab', 'data-dc-open', 'data-dc-pick', 'data-dc-row', 'data-dc-xem', 'data-act-filter', 'data-act-date', 'data-review', 'data-manual-price', 'data-receipt-date', 'data-commodity', 'data-transport', 'data-trip-book', 'data-tong-toggle'].find(attr => active.hasAttribute(attr));
    const focusValue = focusAttr ? active.getAttribute(focusAttr) : null;
    const caret = focusAttr && active.tagName === 'INPUT' && active.type !== 'checkbox' ? active.selectionStart : null;
    inboxRoot.innerHTML = html;
    for (const input of inboxRoot.querySelectorAll('[data-manual-price],[data-reason],[data-receipt-date],[data-commodity],[data-transport],[data-trip-book]')) input.value = drafts.get(draftKey(input)) ?? input.dataset.suggestedPrice ?? '';
    for (const input of inboxRoot.querySelectorAll('[data-manual-price]')) setPriceValidity(input);
    for (const input of inboxRoot.querySelectorAll('[data-pick],[data-pick-price]')) input.disabled = inbox.busy || !!inbox.review || !!inbox.action;
    if (inbox.stale) for (const control of inboxRoot.querySelectorAll('button,input,select')) if (!VIEW_ONLY.some(attr => control.hasAttribute(attr))) control.disabled = true;
    if (focusAttr) {
      const again = inboxRoot.querySelector(`[${focusAttr}="${CSS.escape(focusValue)}"]:not(:disabled)`);
      again?.focus({ preventScroll: true });
      if (caret !== null) again?.setSelectionRange(caret, caret);
    }
    const scroller = inboxRoot.querySelector('.work-scroll:has(.work-table)');
    if (scroller) scroller.scrollLeft = scrollLeft;
  }

  // Tab Đã làm: đọc theo ngày khi tab mở; hôm nay đọc lại mỗi lần tự tải, ngày cũ đọc một lần (Lịch sử chỉ thêm, không sửa).
  const vnToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });
  const actDay = () => inbox.act.day ?? vnToday();
  const actView = () => ({ day: actDay(), today: vnToday(), filter: inbox.act.filter, body: inbox.act.data.get(actDay()) });
  async function loadActivity(force = false) {
    const day = actDay(), act = inbox.act;
    if (inbox.tab !== 'may' || act.loading === day || (!force && act.data.get(day) && day !== vnToday())) return;
    act.loading = day;
    try {
      const body = await json(day === vnToday() ? '/api/v7/activity' : `/api/v7/activity?day=${encodeURIComponent(day)}`);
      act.data.set(day, body);
    } catch { if (!act.data.get(day)) act.data.set(day, null); }
    if (act.loading === day) act.loading = null;
    if (actDay() === day) paintInbox();
  }
  function showActivityDay(day) {
    const today = vnToday();
    inbox.act.day = !day || day === 'today' || day >= today ? null : day;
    if (inbox.act.data.get(actDay()) === null) inbox.act.data.delete(actDay());
    paintInbox();
    loadActivity();
  }

  async function loadInbox() {
    if (inboxLoading || !globalThis.InboxCard || inbox.busy || inbox.review || inbox.action) return;   // không vẽ lại khi đang xem lại/ghi
    inboxLoading = true;
    clearTimeout(inboxTimer);
    try {
      const [data, customers] = await Promise.all([json('/api/v7/inbox'),
        currentCustomers.length ? currentCustomers : readCustomers().catch(() => [])]);
      inbox.data = data;
      if (!currentCustomers.length) currentCustomers = customers;
      // Bỏ chọn sổ không còn ghi được (đã ghi xong, phiếu đổi sang cần xem…).
      const writable = new Set((data.books ?? []).filter(globalThis.InboxCard.canWrite).map(book => book.customer_id));
      for (const id of inbox.selected) if (!writable.has(id)) inbox.selected.delete(id);
      for (const id of inbox.selectedPrices) if (!data.books?.some(b => b.customer_id === id && b.prices.ready)) inbox.selectedPrices.delete(id);
      // Sổ đang đóng mở lại thì đọc mới; sổ đang mở giữ bản đang hiện tới khi refreshDetail có bản mới.
      for (const id of inbox.details.keys()) if (id !== inbox.open) inbox.details.delete(id);
      markFresh('inbox');
    } catch { inbox.data = null; inbox.stale = false; }
    paintInbox();
    if (inbox.data && (inbox.data.state === 'computing' || inbox.data.refreshing)) inboxTimer = setTimeout(loadInbox, 5_000);
    inboxLoading = false;
    if (inbox.open !== null) refreshDetail(inbox.open);
    syncStatement();
  }

  // Bảng đối chiếu: khách lệch lớn nhất mở sẵn; đóng tay thì để đóng. Khách hết lệch thì đóng.
  const Doi = globalThis.DoiChieuModel;
  function syncStatement() {
    const dc = inbox.dc;
    const ids = Doi.openRows(inbox.data?.reconcile).map(row => row.customer_id).filter(Boolean);
    if (dc.open !== null && !ids.includes(dc.open)) dc.open = null;
    if (dc.open === null && !dc.closed && ids.length) dc.open = ids[0];
    if (dc.open !== null) refreshStatement(dc.open);
    paintInbox();
  }
  let statementRead = 0;
  // Tải nền không đè lựa chọn; khoản hay chuyến không còn thì bỏ khỏi lựa chọn. Đọc lỗi thì giữ số đang hiện, chưa có số thì báo.
  async function refreshStatement(id) {
    const read = ++statementRead;
    const dc = inbox.dc;
    const statement = await json(`/api/v7/sheet/doi-chieu?customer=${id}`).catch(() => null);
    if (read !== statementRead || inbox.action || inbox.busy) return;
    if (statement === null && dc.data.get(id)) return;
    dc.data.set(id, statement);
    if (statement) {
      const groups = new Set(statement.groups.map(group => group.id));
      const rows = new Set(statement.groups.flatMap(group => group.kind === 'prices' ? group.rows.map(row => row.key) : []));
      for (const key of dc.sel.get(id) ?? []) if (!groups.has(key)) dc.sel.get(id).delete(key);
      for (const key of dc.off.get(id) ?? []) if (!rows.has(key)) dc.off.get(id).delete(key);
    }
    paintInbox();
  }
  async function previewAi(id) {
    inbox.dc.ai.set(id, { loading: true }); paintInbox();
    try {
      const preview = await json(`/api/v7/ai/preview?customer=${id}`);
      inbox.dc.ai.set(id, { preview });
    } catch { inbox.dc.ai.set(id, { error: 'Không tải được bản xem trước AI. Thử lại sau.' }); }
    paintInbox();
  }
  async function explainAi(id) {
    const state = inbox.dc.ai.get(id), preview = state?.preview;
    if (!preview?.enabled || state.sending) return;
    inbox.dc.ai.set(id, { preview, sending: true }); paintInbox();
    try {
      const response = await fetch('/api/v7/ai/explain', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: id, fingerprint: preview.fingerprint, consent: true }) });
      const body = await response.json();
      if (!response.ok) throw Error(body.message ?? 'Claude chưa trả lời được.');
      inbox.dc.ai.set(id, { preview, result: body });
    } catch (error) { inbox.dc.ai.set(id, { preview, error: error.message ?? 'Claude chưa trả lời được.' }); }
    paintInbox();
  }
  const dcSet = (map, id) => { if (!map.has(id)) map.set(id, new Set()); return map.get(id); };
  function reviewStatement(id) {
    const dc = inbox.dc, statement = dc.data.get(id);
    if (!statement || inbox.action) return;
    const sum = Doi.summarize(statement, dc.sel.get(id), dc.off.get(id));
    if (!sum.items.length) return;
    const gap = sum.remaining === null ? 'Chưa so được với Sheet. ' : sum.remaining === '0' ? 'Sau khi ghi khớp Sheet tới từng đồng. ' : `Sau khi ghi vẫn lệch Sheet ${globalThis.DoiChieuView.money(sum.remaining, F)} tr. `;
    const locked = sum.lockedMonths.length ? `Tháng đang khóa (${sum.lockedMonths.map(month => `T${Number(month.slice(5, 7))}`).join(', ')}): web mở, ghi, rồi khóa lại. ` : '';
    inbox.action = { id, rowKey: `dc:${id}`, doiChieu: 'ghi', count: sum.items.length, title: 'Ghi đối chiếu', path: '/api/v7/sheet/doi-chieu/ghi',
      text: `Ghi ${sum.items.length} khoản. Còn nợ ${F.full(sum.web)} → ${F.full(sum.after)}. ${gap}${locked}Có ghi Lịch sử.`,
      body: { customer_id: id, expected_version: statement.version, prices_sha256: statement.prices_sha256, receipts_sha256: statement.receipts_sha256, items: sum.items } };
    paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus();
  }
  function reviewKeep(id, rows) {
    const statement = inbox.dc.data.get(id);
    if (!statement || inbox.action || !rows.length) return;
    inbox.action = { id, rowKey: `dc:${id}`, doiChieu: 'giu', count: rows.length, title: 'Giữ số web', path: '/api/v7/sheet/doi-chieu/giu',
      text: `Giữ số web cho ${rows.length} chuyến. Nợ không đổi, vẫn lệch Sheet. Việc này ẩn đi tới khi dòng trên Sheet đổi. Có ghi Lịch sử.`,
      body: { customer_id: id, expected_version: statement.version, idempotency_key: crypto.randomUUID(),
        rows: rows.map(row => { const [kind, target] = row.key.split(':'); return { target_kind: kind, target_id: Number(target), source_fingerprint: row.source_fingerprint }; }) } };
    paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus();
  }
  function reviewUndo(id) {
    const undo = inbox.dc.undo.get(id);
    if (!undo?.keys || inbox.action) return;
    inbox.action = { id, rowKey: `dc:${id}`, doiChieu: 'hoan-tac', title: 'Hoàn tác', path: '/api/v7/sheet/doi-chieu/hoan-tac',
      text: `Hoàn tác lần vừa ghi. Còn nợ ${F.full(undo.after)} → ${F.full(undo.before)}. Có ghi Lịch sử.`,
      body: { customer_id: id, expected_version: undo.version, idempotency_key: crypto.randomUUID(), command_keys: undo.keys, months: undo.months } };
    paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus();
  }
  function statementWritten(a, body) {
    const dc = inbox.dc, id = a.id;
    if (a.doiChieu === 'ghi') {
      dc.sel.delete(id); dc.off.delete(id);
      dc.undo.set(id, { text: `Đã ghi ${a.count} khoản. Còn nợ ${F.full(body.before_vnd)} → ${F.full(body.after_vnd)}.`, keys: body.undo?.command_keys ?? null, months: body.undo?.months ?? [],
        version: body.version, before: body.before_vnd, after: body.after_vnd, note: body.undo ? '' : 'Muốn sửa thì mở sổ.' });
    } else if (a.doiChieu === 'giu') {
      dcSet(dc.kept, id).clear();
      for (const row of a.body.rows) dc.kept.get(id).add(`${row.target_kind}:${row.target_id}`);
      dc.undo.delete(id);
    } else dc.undo.set(id, { text: 'Đã hoàn tác lần vừa ghi.', keys: null, note: '' });
  }

  const readDetail = async id => {
    const ledger = await json(`/api/v7/ledger?customer=${id}`);
    ledger.price_status = await json(`/api/v7/price-table/status?customer=${id}`).catch(() => null);
    return ledger;
  };
  // Lần đọc mới nhất mới được vẽ: bản đọc nền về muộn không đè bản đọc ngay sau khi ghi.
  let detailRead = 0;

  async function loadDetail(id, force = false) {
    if (!force && inbox.details.has(id)) return;
    const read = ++detailRead;
    inbox.details.delete(id);
    paintInbox();
    const ledger = await readDetail(id).catch(() => null);
    if (read !== detailRead) return;
    inbox.details.set(id, ledger);
    paintInbox();
  }

  // Đọc nền cho sổ đang mở: không hiện "đang tải". Đọc lỗi thì giữ bản đang hiện, nhịp sau đọc lại; lệnh ghi đã kèm phiên bản sổ nên
  // bản cũ không ghi sai được. Đang xem lại hoặc đang ghi thì bỏ bản vừa đọc để số đang xem lại không đổi dưới tay người dùng.
  async function refreshDetail(id) {
    if (!inbox.details.get(id)) { await loadDetail(id, true); return; }
    const read = ++detailRead;
    const ledger = await readDetail(id).catch(() => null);
    if (!ledger || read !== detailRead || inbox.open !== id || inbox.busy || inbox.review || inbox.action) return;
    inbox.details.set(id, ledger);
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
        rows.push({ id, name: inboxLabel({ customer_id: id }), what: parts.join(' · '), before: ledger.total_outstanding_vnd, after, note: credit });
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
    if (a.rows) return `<section class="receipt-review" role="dialog" aria-labelledby="h-action"><h3 id="h-action">${esc(a.title)} · ${a.count} mục ở ${a.rows.length} sổ</h3><div class="work-scroll"><table><thead><tr><th>Khách</th><th>Ghi</th><th class="num">Còn nợ trước → sau <span class="muted">tr</span></th><th>Lưu ý</th></tr></thead><tbody>${a.rows.map(r => `<tr><td>${esc(r.name)}</td><td>${esc(r.what)}</td><td class="num action-description" title="${esc(`${F.full(r.before)} → ${F.full(r.after)}`)}">${globalThis.InboxTable.million(r.before)} → <strong>${globalThis.InboxTable.million(r.after)}</strong></td><td>${esc(r.note)}</td></tr>`).join('')}</tbody></table></div><p>${a.undo ? 'Hủy đúng phiếu vừa ghi với lý do hoàn tác; trả giá về trước lần ghi. Sổ đã đổi thì dừng để đối chiếu.' : 'Phiếu ghi đúng ngày trên Sheet, trừ vào nợ cũ trước. Chuyến có giá thì bắt đầu cộng vào nợ.'}</p>${a.error ? `<p role="alert">${esc(a.error)}</p>` : ''}<div class="actions">${a.path ? `<button class="btn primary" type="button" data-action-write${inbox.busy ? ' disabled' : ''}>${inbox.busy ? 'Đang ghi…' : a.unknown ? 'Thử lại' : `${a.undo ? 'Hoàn tác' : 'Ghi'} ${a.count} mục`}</button>` : ''}${a.unknown ? '' : '<button class="btn" type="button" data-action-cancel>Thôi</button>'}</div></section>`;
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
    inbox.undo = null;
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
        if (a.doiChieu) statementWritten(a, body);
        else {
          inbox.details.delete(a.id);
          inbox.notice = body.complete === false ? `Đã ghi ${body.written ?? body.approved}; còn ${body.remaining} mục chưa ghi. Mở lại sổ để kiểm tra.` : `Đã xử lý: ${a.title}. Mở sổ xem Lịch sử nếu cần kiểm tra.`;
          await loadDetail(a.id, true);
        }
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
        task.done = true; task.undoKeys = body.undo_keys; task.version = body.version;
        if (task.kind === 'prices') inbox.selectedPrices.delete(task.body.customer_id); else inbox.selected.delete(task.body.customer_id);
        const next = a.tasks.find(t => !t.done && t.body.customer_id === task.body.customer_id);
        if (next) {
          if (!Number.isInteger(body.version)) { a.path = null; a.error = 'Đã ghi một lô; chưa nhận được phiên bản mới. Mở sổ kiểm tra trước khi làm tiếp.'; break; }
          next.body.expected_version = body.version;
        }
      }
      if (a.tasks.every(t => t.done)) {
        a.path = null;
        a.title = a.undo ? 'Đã hoàn tác các mục vừa ghi' : 'Đã ghi các mục đã chọn';
        if (a.undo) inbox.undo = null;
        else if (a.tasks.every(t => t.undoKeys?.length && Number.isInteger(t.version))) {
          inbox.undo = a.rows.map(row => {
            const tasks = a.tasks.filter(t => t.body.customer_id === row.id);
            return { id: row.id, before: row.before, after: row.after, version: tasks.at(-1).version, keys: tasks.flatMap(t => t.undoKeys) };
          });
        }
        loadInbox(); load();
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
    if (!inbox.result?.unknown) inbox.undo = null;
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
        if (response.ok && body.complete) {
          outcome.push({ ...row, ok: true, written: body.written });
          if (body.undo_keys?.length && Number.isInteger(body.version)) {
            inbox.undo ??= [];
            inbox.undo.push({ id: book.customer_id, version: body.version, keys: body.undo_keys, before: book.outstanding_vnd,
              after: globalThis.InboxCard.changePreview(book.outstanding_vnd, book.receipts.ready_amount_vnd, '0') });
          }
        }
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
    const input = event.target.closest('[data-manual-price],[data-reason],[data-receipt-date],[data-commodity],[data-transport],[data-trip-book]');
    if (input) { input.setCustomValidity(''); drafts.set(draftKey(input), input.value); if (input.hasAttribute('data-manual-price')) setPriceValidity(input); }
  });
  function setPriceValidity(input) {
    const button = input.closest('.detail-actions')?.querySelector('[data-command="price"]');
    if (!button) return;
    try { globalThis.InboxTable.parseMillions(input.value); button.disabled = inbox.busy; }
    catch { button.disabled = true; }
  }
  inboxRoot.addEventListener('change', event => {
    const actDate = event.target.closest('[data-act-date]');
    if (actDate) { if (/^\d{4}-\d\d-\d\d$/.test(actDate.value)) showActivityDay(actDate.value); return; }
    if (inbox.busy || inbox.review || inbox.action) return;
    const dcPick = event.target.closest('[data-dc-pick]');
    if (dcPick && inbox.dc.open !== null) {
      const set = dcSet(inbox.dc.sel, inbox.dc.open);
      if (dcPick.checked) set.add(dcPick.dataset.dcPick); else set.delete(dcPick.dataset.dcPick);
      paintInbox(); return;
    }
    const dcRow = event.target.closest('[data-dc-row]');
    if (dcRow && inbox.dc.open !== null) {
      const set = dcSet(inbox.dc.off, inbox.dc.open);
      if (dcRow.checked) set.delete(dcRow.dataset.dcRow); else set.add(dcRow.dataset.dcRow);
      paintInbox(); return;
    }
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
    if (button.hasAttribute('data-tab')) {
      inbox.tab = button.dataset.tab;
      try { sessionStorage.setItem(TAB_KEY, inbox.tab); } catch { /* chỉ để nhớ tab, không có cũng được */ }
      paintInbox(); loadActivity(); return;
    }
    if (button.hasAttribute('data-tong-toggle')) { inbox.tongOpen = !inbox.tongOpen; paintInbox(); return; }
    if (button.hasAttribute('data-act-day')) { showActivityDay(button.dataset.actDay); return; }
    if (button.hasAttribute('data-act-filter')) { inbox.act.filter = button.dataset.actFilter; paintInbox(); return; }
    if (button.hasAttribute('data-act-retry')) { inbox.act.data.delete(actDay()); paintInbox(); loadActivity(true); return; }
    if (button.hasAttribute('data-dc-open')) {
      const id = Number(button.dataset.dcOpen), dc = inbox.dc;
      dc.closed = dc.open === id;
      dc.open = dc.open === id ? null : id;
      paintInbox();
      if (dc.open !== null) await refreshStatement(dc.open);
      return;
    }
    if (button.hasAttribute('data-dc-retry')) { inbox.dc.data.delete(Number(button.dataset.dcRetry)); paintInbox(); await refreshStatement(Number(button.dataset.dcRetry)); return; }
    if (button.hasAttribute('data-ai-preview')) { await previewAi(Number(button.dataset.aiPreview)); return; }
    if (button.hasAttribute('data-ai-send')) { await explainAi(Number(button.dataset.aiSend)); return; }
    if (button.hasAttribute('data-ai-close')) { inbox.dc.ai.delete(Number(button.dataset.aiClose)); paintInbox(); return; }
    if (button.hasAttribute('data-dc-xem')) {
      const set = inbox.dc.xem, key = button.dataset.dcXem;
      if (set.has(key)) set.delete(key); else set.add(key);
      paintInbox(); return;
    }
    if (button.hasAttribute('data-dc-ghi')) { reviewStatement(Number(button.dataset.dcGhi)); return; }
    if (button.hasAttribute('data-dc-undo')) { reviewUndo(Number(button.dataset.dcUndo)); return; }
    if (button.hasAttribute('data-dc-giu') || button.hasAttribute('data-dc-giu-row')) {
      const id = inbox.dc.open, rows = (inbox.dc.data.get(id)?.groups ?? []).flatMap(group => group.rows.filter(row => row.status === 'CONFLICT' && row.source_fingerprint
        && (button.dataset.dcGiuRow ? row.key === button.dataset.dcGiuRow : group.id === button.dataset.dcGiu)));
      reviewKeep(id, rows);
      return;
    }
    if (button.hasAttribute('data-pick-ready')) {
      const hidden = Doi.openIds(inbox.data?.reconcile);   // khoản của khách lệch ghi ở bảng đối chiếu, không chọn ngầm ở đây
      const shown = (inbox.data?.books ?? []).filter(b => !hidden.has(b.customer_id));
      inbox.selected = new Set(shown.filter(globalThis.InboxCard.canWrite).map(b => b.customer_id));
      inbox.selectedPrices = new Set(shown.filter(b => b.prices?.ready).map(b => b.customer_id));
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
    if (button.hasAttribute('data-undo-batch')) {
      if (inbox.action || inbox.review || !inbox.undo?.length) return;
      inbox.action = { undo: true, title: 'Hoàn tác lần vừa ghi', path: 'batch', count: inbox.undo.reduce((n, r) => n + r.keys.length, 0),
        rows: inbox.undo.map(row => ({ id: row.id, name: inboxLabel({ customer_id: row.id }), what: 'Hoàn tác phần vừa ghi', before: row.after, after: row.before, note: 'Hủy phiếu / phục hồi giá, có Lịch sử' })),
        tasks: inbox.undo.map(row => ({ kind: 'undo', path: '/api/v7/sheet/batch/undo', count: row.keys.length, done: false,
          body: { customer_id: row.id, expected_version: row.version, idempotency_key: crypto.randomUUID(), command_keys: row.keys } })) };
      paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus(); return;
    }
    if (button.hasAttribute('data-detail-retry')) { await loadDetail(Number(button.dataset.detailRetry), true); return; }
    if (button.hasAttribute('data-remove-trip')) { reviewRemove(Number(button.dataset.removeTrip)); return; }
    if (button.hasAttribute('data-command')) { reviewCommand(button); return; }
    if (button.hasAttribute('data-assign-trip')) {
      if (inbox.action || inbox.review) return;
      const ledger = inbox.details.get(inbox.open), source = button.dataset.assignTrip;
      const row = ledger?.sheet_sync?.items?.find(r => r.source_fingerprint === source && r.sync_state === 'NEW');
      const targetId = Number(inboxRoot.querySelector(`[data-trip-book="${source}"]`)?.value);
      const choice = row?.candidate_books?.find(c => c.id === targetId);
      if (!choice) return;
      button.disabled = true;
      try {
        const target = targetId === inbox.open ? ledger : await json(`/api/v7/ledger?customer=${targetId}`);
        if (!Number.isInteger(target.version)) throw Error();
        inbox.action = { id: inbox.open, title: `Đưa chuyến ${row.container} vào ${choice.commodity ?? choice.name}`, rowKey: `assignment:${source}`,
          text: 'Chỉ đưa chuyến này vào sổ được chọn, chưa có giá, nợ không đổi. Chuyến nghi trùng sẽ chờ kiểm.',
          inlineText: `Vào sổ ${choice.commodity ?? choice.name} · chưa giá, nợ không đổi`, path: '/api/v7/sheet/trips/assign',
          body: { customer_id: inbox.open, expected_version: ledger.version, idempotency_key: crypto.randomUUID(),
            target_customer_id: targetId, target_version: target.version, source_fingerprint: source } };
        paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus();
      } catch { inbox.notice = 'Chưa đọc được sổ đích. Thử lại trước khi đưa chuyến vào sổ.'; paintInbox(); }
      button.disabled = false; return;
    }
    if (button.hasAttribute('data-save-commodity')) {
      if (inbox.action || inbox.review) return;
      const ledger = inbox.details.get(inbox.open);
      const commodity = inboxRoot.querySelector('[data-commodity]')?.value;
      if (!commodity || !Number.isInteger(ledger?.version)) return;
      inbox.action = { id: inbox.open, title: `Gán mặt hàng ${commodity}`, rowKey: 'commodity',
        text: `Gán mặt hàng ${commodity} cho sổ này. Nợ không đổi; không chuyển chuyến hoặc gộp sổ.`,
        inlineText: `Gán mặt hàng ${commodity} · nợ không đổi`, path: '/api/v7/customers/commodity',
        body: { customer_id: inbox.open, expected_version: ledger.version, idempotency_key: crypto.randomUUID(), commodity_name: commodity } };
      paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus(); return;
    }
    if (button.hasAttribute('data-save-transport')) {
      if (inbox.action || inbox.review) return;
      const ledger = inbox.details.get(inbox.open);
      const mode = inboxRoot.querySelector('[data-transport]')?.value;
      if (!mode || !Number.isInteger(ledger?.version)) return;
      const word = { CANG: 'Cảng', BO: 'Bộ' }[mode];
      inbox.action = { id: inbox.open, title: `Gán ${word}`, rowKey: 'transport',
        text: `Ghi sổ này đi ${word}. Nợ không đổi; không chuyển chuyến hoặc gộp sổ.`,
        inlineText: `Gán ${word} · nợ không đổi`, path: '/api/v7/customers/transport',
        body: { customer_id: inbox.open, expected_version: ledger.version, idempotency_key: crypto.randomUUID(), transport_mode: mode } };
      paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus(); return;
    }
    if (button.hasAttribute('data-record-sheet-receipt')) {
      if (inbox.action || inbox.review) return;
      const ledger = inbox.details.get(inbox.open);
      const source = button.dataset.recordSheetReceipt;
      const row = ledger?.sheet_receipts?.review?.find(r => r.source_fingerprint === source && r.status === 'NO_DATE');
      if (!row) return;
      const input = inboxRoot.querySelector(`[data-receipt-date="${source}"]`);
      try {
        const text = input.value.trim();
        const supplied = /^\d{1,2}\/\d{1,2}$/.test(text) ? `${text}/${row.debt_month.slice(0, 4)}` : text;
        const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Ho_Chi_Minh' });
        const date = SoKhachV7Model.parseCellEdit('event_date', supplied, today);
        const after = globalThis.InboxCard.changePreview(ledger.total_outstanding_vnd, row.amount_vnd, '0');
        inbox.action = { id: inbox.open, title: 'Ghi phiếu thu', rowKey: `receipt:${source}`,
          text: `Ghi phiếu ${F.full(row.amount_vnd)}, ngày ${F.dateText(date)}. Còn nợ ${F.full(ledger.total_outstanding_vnd)} → ${F.full(after)}.`,
          inlineText: `Ghi phiếu ngày ${F.dateText(date)} · nợ ${globalThis.InboxTable.million(ledger.total_outstanding_vnd)} → ${globalThis.InboxTable.million(after)} tr`,
          path: '/api/v7/sheet/receipts/review', body: { customer_id: inbox.open, expected_version: ledger.version,
            idempotency_key: crypto.randomUUID(), source_fingerprint: source, date } };
        paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus();
      } catch (error) { input.setCustomValidity(error.message); input.reportValidity(); }
      return;
    }
    if (button.hasAttribute('data-keep-trip') || button.hasAttribute('data-keep-price') || button.hasAttribute('data-use-sheet-price')) {
      if (inbox.action || inbox.review) return;
      const ledger = inbox.details.get(inbox.open);
      const useSheet = button.hasAttribute('data-use-sheet-price');
      const price = useSheet || button.hasAttribute('data-keep-price');
      const row = price ? ledger?.sheet_prices?.review?.find(r => `${r.target_kind}:${r.target_id}` === (button.dataset.keepPrice ?? button.dataset.useSheetPrice))
        : ledger?.sheet_sync?.removed_items?.find(r => r.trip_id === Number(button.dataset.keepTrip));
      if (!row?.source_fingerprint) return;
      inbox.action = { id: inbox.open, title: price ? 'Giữ giá web' : 'Giữ chuyến',
        text: 'Giữ số liệu web, nợ không đổi. Lưu người làm trong Lịch sử. Dòng Sheet liên quan đổi thì hỏi lại.',
        inlineText: 'Giữ số liệu web · nợ không đổi', rowKey: price ? `sheet-price:${row.target_kind}:${row.target_id}` : `removed:${row.trip_id}`,
        path: '/api/v7/sheet/tasks/keep', body: { customer_id: inbox.open, expected_version: ledger.version,
          idempotency_key: crypto.randomUUID(), task_kind: price ? 'price' : 'removed',
          target_kind: price ? row.target_kind : 'trip', target_id: price ? row.target_id : row.trip_id, source_fingerprint: row.source_fingerprint } };
      if (useSheet) {
        const current = row.target_kind === 'trip' ? ledger.trips?.find(t => t.id === row.target_id)
          : ledger.legacy_rows?.find(t => t.id === row.target_id)?.current;
        if (!current || row.month_locked) { inbox.action = null; return; }
        const next = SoKhachV7Model.tripAmount({ container: row.container, status: 'confirmed', unitPriceVnd: row.sheet_unit_price_vnd, otherFeeVnd: row.sheet_other_fee_vnd }).amountVnd;
        if (next == null || (current.amount_vnd ?? current.counted_vnd) == null) { inbox.action = null; return; }
        const after = globalThis.InboxCard.changePreview(ledger.total_outstanding_vnd, current.amount_vnd ?? current.counted_vnd, next.toString());
        Object.assign(inbox.action, { title: 'Lấy giá Sheet', path: '/api/v7/sheet/tasks/price',
          text: `Đơn giá ${F.full(row.web_unit_price_vnd)} → ${F.full(row.sheet_unit_price_vnd)}, phụ phí ${row.web_other_fee_vnd == null ? '—' : F.full(row.web_other_fee_vnd)} → ${row.sheet_other_fee_vnd == null ? '—' : F.full(row.sheet_other_fee_vnd)}. Còn nợ ${F.full(ledger.total_outstanding_vnd)} → ${F.full(after)}.`,
          inlineText: `Lấy giá Sheet ${globalThis.InboxTable.million(row.sheet_unit_price_vnd)} tr · nợ ${globalThis.InboxTable.million(ledger.total_outstanding_vnd)} → ${globalThis.InboxTable.million(after)} tr` });
      }
      paintInbox(); inboxRoot.querySelector('[data-action-cancel]')?.focus(); return;
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

  // Có bản gần nhất của tab thì vẽ ngay, rồi đọc lại như thường: lần vào trang không còn phải ngồi đợi.
  function showSnapshot(saved) {
    if (!saved?.inbox || !saved.dashboard || !Array.isArray(saved.unsorted) || !Array.isArray(saved.customers)) return;
    try {
      Object.assign(inbox, { data: saved.inbox, stale: true });
      dashboard = saved.dashboard;
      unsorted = saved.unsorted;
      currentCustomers = saved.customers;
      firstLoadDone = true;
      globalThis.AppNav?.setCustomers(saved.customers);
      paintInbox();
    } catch {
      // Bản lưu từ phiên bản web cũ không vẽ được: quay về đợi tải như thường.
      Object.assign(inbox, { data: undefined, stale: false });
      dashboard = null; unsorted = null; currentCustomers = []; firstLoadDone = false; paintedHtml = null;
      inboxRoot.replaceChildren();
    }
  }
  showSnapshot(globalThis.AppNav?.readTodoSnapshot());
  load();
  loadInbox();
  loadActivity();
  const refresh = () => { if (document.activeElement?.id === 'customer-search') return; load(); loadInbox(); loadActivity(); sheetRefresh?.load(); };
  document.querySelector('#error').addEventListener('click', event => { if (event.target.closest('[data-retry]')) load(); });
  const button = document.querySelector('#refresh-data');
  if (globalThis.SheetRefresh) {
    sheetRefresh = globalThis.SheetRefresh.create({ node: document.querySelector('#updated-at'), button, onDone: () => { load(); loadInbox(); } });
    sheetRefresh.load();
  }
  button?.addEventListener('click', () => { load(); loadInbox(); loadActivity(true); sheetRefresh?.trigger(); });
  setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
