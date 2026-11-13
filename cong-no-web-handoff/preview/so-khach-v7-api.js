/* Client V7: server giữ số dư và phân bổ; key giữ nguyên khi chưa rõ kết quả. */
(() => {
  'use strict';
  const routes = {
    paste: ['/api/v7/trips/paste', ['debt_month', 'trips']],
    price: ['/api/v7/trips/price', ['trip_id', 'unit_price_vnd', 'other_fee_vnd']],
    tripAdjust: ['/api/v7/trips/adjust', ['trip_id', 'new_amount_vnd', 'field', 'new_value_vnd', 'note']],
    monthAdjust: ['/api/v7/months/adjust', ['debt_month', 'amount_vnd', 'note']],
    monthAdjustDelete: ['/api/v7/months/adjust/delete', ['adjustment_id']],
    receipt: ['/api/v7/receipts', ['date', 'method', 'amount_vnd', 'reference']],
    receiptMeta: ['/api/v7/receipts/meta', ['pid', 'date', 'method', 'reference']],
    receiptVoid: ['/api/v7/receipts/void', ['pid', 'reason']],
    // CHUNG-TU-01: ảnh chứng từ gắn phiếu đã ghi; ảnh gửi base64, không đổi số tiền.
    imageAttach: ['/api/v7/receipts/images', ['pid', 'content_type', 'data_base64']],
    imageRemove: ['/api/v7/receipts/images/remove', ['image_id', 'reason']],
    lock: ['/api/v7/months/lock', ['month', 'locked']],
    tripReview: ['/api/v7/trips/review', ['trip_id', 'decision', 'reason']],
    // NHAP-SHEET-01: sửa một ô / xóa hẳn, mọi tháng kể cả tháng khóa; value luôn là chuỗi.
    tripInfo: ['/api/v7/trips/info', ['trip_id', 'field', 'value']],
    tripDelete: ['/api/v7/trips/delete', ['trip_id']],
    legacyEdit: ['/api/v7/legacy/edit', ['legacy_row_id', 'field', 'value']],
    legacyDelete: ['/api/v7/legacy/delete', ['legacy_row_id']],
    // PHU-PHI-01: khoản phụ phí theo chuyến ({trip_id}) hoặc dòng sổ gốc ({legacy_row_id}); cột riêng của sổ.
    feeAdd: ['/api/v7/trips/fees/add', ['targets', 'fee_type_id', 'amount_vnd', 'note']],
    feeSet: ['/api/v7/trips/fees/set', ['target', 'fee_type_id', 'amount_vnd']],
    feeReplace: ['/api/v7/trips/fees/replace', ['fee_line_id', 'fee_type_id', 'amount_vnd', 'note']],
    feeVoid: ['/api/v7/trips/fees/void', ['fee_line_id']],
    feeColumns: ['/api/v7/books/fee-columns', ['fee_type_ids']],
  };
  // Danh mục loại phụ phí dùng chung mọi sổ: không gắn khách, không version sổ.
  const catalogRoutes = {
    feeTypeAdd: ['/api/v7/fee-types', ['name', 'kind']],
    feeTypeUpdate: ['/api/v7/fee-types/update', ['command', 'fee_type_id', 'name', 'kind', 'active']],
  };
  // Cấn trừ hai sổ (CT-2SO): một lệnh ghi cả hai sổ, cần version của cả hai. 'target' = sổ đang mở là sổ nhận.
  const offsetRoutes = {
    offset: ['/api/v7/offsets', ['source_customer_id', 'source_version', 'date', 'amount_vnd', 'reference'], 'target'],
    offsetVoid: ['/api/v7/offsets/void', ['other_version', 'offset_pair_id', 'reason'], 'self'],
    offsetDate: ['/api/v7/offsets/date', ['other_version', 'offset_pair_id', 'date'], 'self'],
  };
  const idFields = ['source_customer_id', 'source_version', 'other_version', 'offset_pair_id'];
  const stale = 'Sổ vừa thay đổi. Kiểm tra dữ liệu mới rồi thực hiện lại.';
  const busyText = 'Đang ghi các giá vừa dán. Chờ xong rồi làm tiếp.';
  const unknown = 'Chưa rõ lệnh đã lưu. Thử lại bằng cùng yêu cầu.';
  const tripFields = ['date', 'booking', 'container', 'carrier', 'shipper', 'from', 'to', 'note', 'src', 'unitPriceVnd', 'otherFeeVnd'];
  const customerNames = new Map();
  const customerRows = new Map();   // DEBIT-NOTE-02: tên, mặt hàng, phương thức để điền sẵn debit note
  // Tên Sheet của sổ (display_name, rồi name), như tên Đòi nợ dùng trong tin nhắc và nút Chat; danh sách chưa về thì "".
  const sheetName = id => String(customerRows.get(id)?.display_name ?? customerRows.get(id)?.name ?? '').trim();
  // Trang khách: tìm hội thoại Zalo cần tên khách nên đợi danh sách khách về (đọc được hay lỗi).
  let customersDone = () => {};
  const customersLoaded = new Promise(resolve => { customersDone = resolve; });

  // Danh sách khách tải sau sổ: vẽ lại qua renderer để tên khách vào đúng tiêu đề, không chép đè DOM.
  let redraw = null;
  // Nút "Đổi khách" ở đầu sổ: mở danh sách khách và đặt con trỏ vào ô tìm.
  let showCustomers = () => document.querySelector('#customer-search')?.focus();
  const realCopyText = 'Dữ liệu thật · bản sao cô lập, chưa phải prod';

  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  // MH-01: fold hạ chữ thường, bỏ dấu, gộp ký tự lạ thành khoảng trắng — gõ "sau rieng bo" khớp "Sầu riêng · bộ".
  const { fold, commodityText, customerLabel, customerLabels } = F;
  const unclassified = F.UNSORTED;
  const groupLabel = row => commodityText(row.commodity, row.transport_mode);

  // Nhóm theo mặt hàng + phương thức, nhóm xếp theo tên, "Chưa phân loại" cuối; trong nhóm giữ thứ tự server.
  // found theo đúng thứ tự hiển thị để Enter mở dòng đầu tiên người dùng thấy.
  function groupCustomers(customers, query = '') {
    const wanted = fold(query);
    const groups = new Map();
    for (const row of customers) {
      const label = groupLabel(row);
      const names = [row.name, row.display_name, row.label, ...(row.aliases ?? [])];
      if (wanted && !names.some(name => fold(name).includes(wanted)) && !fold(label).includes(wanted)) continue;
      if (!groups.has(label)) groups.set(label, { label, rows: [] });
      groups.get(label).rows.push(row);
    }
    const ordered = [...groups.values()].sort((a, b) =>
      (a.label === unclassified) - (b.label === unclassified) || a.label.localeCompare(b.label, 'vi'));
    // Chưa khách nào có mặt hàng (DB chưa gán): danh sách phẳng như cũ, không hiện một nhóm "Chưa phân loại" thừa.
    return { groups: ordered, found: ordered.flatMap(group => group.rows),
      labelled: customers.some(row => row.commodity) };
  }

  async function loadCustomers(fetcher = fetch) {
    const search = document.querySelector('#customer-search');
    const list = document.querySelector('#customer-list');
    if (!search || !list) { customersDone(); return; }
    try {
      const response = await fetcher('/api/v7/customers', { cache: 'no-store' });
      if (!response.ok) throw Error();
      const data = await response.json();
      const customers = data.customers ?? [];
      // Show the real-copy/demo banner already on the picker page, before any ledger opens.
      const banner = document.querySelector('#demo-banner');
      if (banner && (data.real_copy === true || data.demo === true)) {
        if (data.real_copy === true) banner.textContent = realCopyText;
        banner.hidden = false;
      }
      customerNames.clear();
      customerRows.clear();
      for (const [id, label] of customerLabels(customers)) customerNames.set(id, label);
      for (const row of customers) customerRows.set(row.id, row);
      // Plain links, not a <select>: the embedded app browser does not open native select popups.
      const current = new URLSearchParams(location.search).get('customer');
      const href = row => `/so-khach-v7-live.html?customer=${encodeURIComponent(row.id)}`;
      let found = [];
      let listAll = !current;
      const render = () => {
        const query = search.value.trim();
        const grouped = groupCustomers(customers, query);
        found = grouped.found;
        // Before typing, list everyone only when no customer is open yet or the search box is in use.
        // Trang chọn khách (chưa mở sổ) đủ chỗ nên hiện mọi sổ; hộp đổi khách nhỏ chỉ hiện 50 dòng đầu.
        const shown = new Set(query || listAll ? (current ? found.slice(0, 50) : found) : []);
        const items = [];
        for (const group of grouped.groups) {
          const rows = group.rows.filter(row => shown.has(row));
          if (!rows.length) continue;
          if (grouped.labelled) {
            const head = document.createElement('div');
            head.className = 'customer-group';
            head.textContent = `${group.label} (${group.rows.length})`;
            items.push(head);
          }
          for (const row of rows) {
            const link = document.createElement('a');
            link.href = href(row);
            // Dòng đã nằm dưới nhóm mặt hàng: bỏ phần mặt hàng lặp lại, giữ " · sổ <id>" để phân biệt sổ trùng tên.
            const label = customerNames.get(String(row.id));
            const display = grouped.labelled ? label.replace(` · ${group.label}`, '') : label;
            link.textContent = row.status === 'active' ? display : `${display} (chưa có số dư đầu)`;
            if (String(row.id) === current) link.setAttribute('aria-current', 'page');
            items.push(link);
          }
        }
        list.replaceChildren(...items);
        document.querySelector('#customer-count').textContent = query && !found.length
          ? `Không có khách nào khớp “${query}”`
          : query || listAll
            ? `${found.length} khách${found.length > shown.size ? ` · hiện ${shown.size}, gõ thêm để lọc` : ''}`
            : `${customers.length} khách · gõ tên để đổi khách`;
      };
      search.addEventListener('input', render);
      search.addEventListener('focus', () => { listAll = true; render(); });
      showCustomers = () => { listAll = true; render(); search.focus(); };
      search.addEventListener('keydown', event => {
        if (event.key === 'Enter' && found.length) location.href = href(found[0]);
      });
      render();
      redraw?.();
    } catch {
      document.querySelector('#customer-count').textContent = 'Không tải được danh sách khách';
    } finally { customersDone(); }
  }
  if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', () => { loadCustomers(); });

  // onRedraw: trang vẽ lại từ bản đang có mà giữ ô đang gõ; thiếu thì vẽ lại bằng onSnapshot.
  // NHAP-NHANH-01: onPatched nhận bản sổ đã vá (ô vừa gõ) hay bản đọc lại trong lúc hàng đợi ghi nền chạy — trang vẽ khi rảnh,
  // không thay #app lúc đang gõ; thiếu thì vẽ bằng onSnapshot. onSaving: hàng đợi bắt đầu/xong (dòng "Đang lưu…" đầu sổ).
  function create({ customerId, fetcher = fetch, key = () => crypto.randomUUID(), onSnapshot = () => {}, onRedraw = null, onNotice = () => {},
    onPatched = null, onSaving = () => {} }) {
    let snapshot = null;
    let pending = null;
    let outcome = null;
    // NHAP-NHANH-01: hàng đợi ghi nền { items, index, version }; items[index..] là lệnh chưa ghi xong, bản sổ hiện ra luôn vá
    // thêm các lệnh đó để lần đọc lại xen vào không làm ô vừa gõ nháy về số cũ.
    let queue = null, queueRun = null;
    const queueActive = () => !!queueRun && outcome?.status !== 'unknown';
    const overlay = data => (queue ? queue.items.slice(queue.index).reduce((acc, item) => item.patch?.(acc) ?? acc, data) : data);
    // MO-SO-NHANH-01: so-khach-v7-prefetch.js (đầu <head>) đã bắt đầu GET sổ của ?customer= lúc trang mở; lần đọc đầu
    // lấy phản hồi đó (một lần, đúng mã khách) thay vì gọi lại. Lỗi hay đổi khách thì fetch như thường.
    const prefetched = () => {
      const early = typeof window !== 'undefined' ? window.SoKhachV7Prefetch : null;
      if (!early?.response || String(early.customerId) !== String(customerId)) return null;
      const { response } = early;
      early.response = null;
      return response;
    };
    // gentle (hàng đợi ghi nền): vẽ qua onPatched để không thay #app giữa lúc người dùng đang gõ ô kế tiếp.
    async function read({ gentle = false } = {}) {
      const response = await (prefetched() ?? fetcher(`/api/v7/ledger?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' }));
      if (!response.ok) throw Error('Không đọc được sổ khách.');
      const next = await response.json();
      if (!next || next.customer_id !== customerId || !Number.isSafeInteger(next.version)) throw Error('Dữ liệu sổ không hợp lệ.');
      const banner = typeof document !== 'undefined' && document.querySelector('#demo-banner');
      if (banner) {
        if (next.real_copy === true) banner.textContent = realCopyText;
        banner.hidden = next.demo !== true && next.real_copy !== true;
      }
      snapshot = overlay(next);
      if (gentle && onPatched) onPatched(snapshot); else onSnapshot(snapshot);
      return next;
    }
    // MO-SO-NHANH-02: Lịch sử của sổ đọc riêng khi mở khung; không đụng bản sổ đang giữ, không cần lệnh đang chờ.
    async function readEvents() {
      const response = await fetcher(`/api/v7/ledger/events?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được lịch sử.');
      const body = await response.json();
      if (!body || body.customer_id !== customerId || !Array.isArray(body.events)) throw Error('Dữ liệu lịch sử không hợp lệ.');
      return body;
    }
    // Kết quả cuối theo khóa lệnh (lưu, sổ đổi, lỗi): phần giao diện hỏi đúng lệnh của mình (khung Ghi phiếu thu với phiếu
    // "chưa rõ" đã Thử lại ở đầu sổ), không dựa vào kết quả dùng chung của lệnh gần nhất.
    const settled = new Map();
    const remember = (key, value) => { settled.set(key, value); if (settled.size > 500) settled.delete(settled.keys().next().value); return value; };
    // Sửa 13/11/2026: lệnh đang gửi (tới khi sổ đọc lại xong). Ai dựng số từ sổ (hộp Debit note) chờ settle() trước, để
    // bấm thẳng nút từ ô vừa gõ (ô lưu lúc mất tiêu điểm) vẫn thấy số vừa ghi.
    let inflight = null;
    function send() {
      // Còn `pending` sau khi gửi xong = chưa rõ kết quả: vẽ lại băng đầu sổ để hiện nút Thử lại (sending() đã tắt).
      const run = sendOnce().finally(() => { if (inflight === run) inflight = null; if (pending) onSaving(); });
      inflight = run;
      return run;
    }
    async function sendOnce() {
      const sentKey = pending.body.idempotency_key;
      try {
        const response = await fetcher(pending.path, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pending.body),
        });
        const result = await response.json();
        if (!response.ok) {
          if (result.error === 'STALE_LEDGER') {
            outcome = remember(sentKey, { status: 'stale' });
            pending = null;
            snapshot = null;
            try { await read(); } catch { onNotice('Không tải được sổ mới. Tải lại trang rồi kiểm tra.'); return; }
            onNotice(stale);
            return;
          }
          if (result.error === 'RESULT_UNKNOWN') { outcome = { status: 'unknown' }; onNotice(unknown); return; }
          outcome = remember(sentKey, { status: 'error', result });
          pending = null;
          onNotice(result.message || 'Không lưu được thao tác.');
          return result;
        }
        outcome = remember(sentKey, { status: 'saved', result });
        await read();
        // Lệnh khác bị từ chối trong lúc đọc lại sổ đã xóa kết quả dùng chung: gán lại cho đúng lệnh này trước khi nó trả về.
        outcome = settled.get(sentKey);
        pending = null;
        onNotice(result.duplicate_reference ? 'Đã lưu. Tham chiếu trùng với phiếu khác trong sổ.' : 'Đã lưu.');
      } catch {
        outcome = { status: 'unknown' };
        onNotice(unknown);
      }
    }
    async function submit(action, fields) {
      outcome = null;   // trước mọi lần từ chối: kết quả của lệnh trước (hay chuỗi giá) không được đọc nhầm là của lệnh này
      if (queueRun) { await queueRun; outcome = null; }   // NHAP-NHANH-01: lệnh khác chờ hàng đợi ghi nền xong
      if (running) throw Error(busyText);
      if (pending) throw Error('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.');
      if (snapshot?.status !== 'active') throw Error('Khách chưa có số dư đầu hiệu lực.');
      const [path, intent] = intentOf(action, fields);
      pending = { path, body: { customer_id: customerId, expected_version: snapshot.version,
        idempotency_key: key(), ...intent } };
      return await send();
    }
    // Lệnh sổ đã lọc trường và kiểm kiểu (chung cho submit và hàng đợi ghi nền).
    function intentOf(action, fields) {
      const route = routes[action];
      if (!route) throw Error('Thao tác không hợp lệ.');
      const intent = Object.fromEntries(route[1].filter(name => Object.hasOwn(fields, name)).map(name => [name, fields[name]]));
      if (Array.isArray(intent.trips)) intent.trips = intent.trips.map(trip =>
        Object.fromEntries(tripFields.filter(name => Object.hasOwn(trip, name)).map(name => [name, trip[name]])));
      for (const name of ['amount_vnd', 'new_amount_vnd', 'new_value_vnd', 'unit_price_vnd', 'other_fee_vnd']) {
        if (Object.hasOwn(intent, name) && intent[name] !== null && typeof intent[name] !== 'string') throw Error('Số tiền phải là chuỗi VND.');
      }
      if (Object.hasOwn(intent, 'value') && typeof intent.value !== 'string') throw Error('Giá trị ô phải là chuỗi.');
      for (const trip of intent.trips ?? []) {
        if (['unitPriceVnd', 'otherFeeVnd'].some(name => trip[name] !== null && trip[name] !== undefined && typeof trip[name] !== 'string')) throw Error('Số tiền phải là chuỗi VND.');
      }
      return [route[0], intent];
    }
    // ---- NHAP-NHANH-01 (specs/nhap-nhanh-01.md): gõ xong hiện ngay, ghi nền như Sheet ----
    // quick() vá bản sổ ngay (patch: bản sổ → bản đã vá, hoặc null) rồi xếp lệnh vào hàng đợi; các lệnh đi lần lượt, lệnh sau
    // dùng `version` lệnh trước trả về; hết lệnh thì đọc lại sổ một lần. Lệnh bị từ chối: dừng, bỏ các lệnh sau (báo số ô),
    // đọc lại sổ cho ô về số thật. Mất mạng: giữ lệnh đó với cùng khóa (`pending`), Thử lại ghi nốt. Trả Promise xong khi sổ
    // đã đọc lại: {status: saved|error|stale|dropped, result}.
    function quick(action, fields, { patch = null, label = '' } = {}) {
      outcome = null;
      if (running) throw Error(busyText);
      if (pending && !queue) throw Error('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.');
      if (snapshot?.status !== 'active') throw Error('Khách chưa có số dư đầu hiệu lực.');
      const [path, intent] = intentOf(action, fields);
      let resolve;
      const done = new Promise(ready => { resolve = ready; });
      queue ??= { items: [], index: 0, version: snapshot.version };
      queue.items.push({ path, intent, key: key(), patch, label, resolve, result: null });
      const patched = patch?.(snapshot);
      if (patched) { snapshot = patched; (onPatched ?? onSnapshot)(patched); }
      if (!queueRun && !pending) runQueue();   // còn lệnh chưa rõ kết quả: chờ người dùng bấm Thử lại
      return done;
    }
    const runQueue = () => {
      queueRun ??= loopQuick().finally(() => { queueRun = null; onSaving(); });
      onSaving();
      return queueRun;
    };
    async function loopQuick() {
      const run = queue;
      for (;;) {
        while (run.index < run.items.length) {
          const item = run.items[run.index];
          pending ??= { path: item.path, body: { customer_id: customerId, expected_version: run.version, idempotency_key: item.key, ...item.intent } };
          let response, result;
          try {
            response = await fetcher(pending.path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pending.body) });
            result = await response.json();
          } catch {
            outcome = { status: 'unknown' };
            onNotice(unknown);
            return;
          }
          if (!response.ok && result?.error === 'RESULT_UNKNOWN') { outcome = { status: 'unknown' }; onNotice(unknown); return; }
          if (!response.ok && result?.error !== 'NO_CHANGE') {
            pending = null;
            const later = run.items.slice(run.index + 1);
            queue = null;
            outcome = remember(item.key, { status: result?.error === 'STALE_LEDGER' ? 'stale' : 'error', result });
            try { await read({ gentle: true }); } catch { /* câu báo dưới đây vẫn nói ô nào chưa lưu */ }
            const why = result?.error === 'STALE_LEDGER' ? stale : result?.message || 'Không lưu được thao tác.';
            onNotice(`Chưa lưu ${item.label || 'ô vừa sửa'}: ${why}${later.length ? ` ${later.length} ô sửa sau đó cũng chưa lưu, nhập lại các ô đó.` : ''}`);
            item.resolve(outcome);
            for (const other of later) other.resolve({ status: 'dropped' });
            return;
          }
          pending = null;
          item.result = response.ok ? result : null;
          remember(item.key, { status: 'saved', result: item.result });
          run.index += 1;
          if (response.ok && Number.isSafeInteger(result?.version)) run.version = result.version;
          else if (response.ok) {
            // Lệnh không trả version: đọc lại sổ lấy version trước khi gửi lệnh sau.
            try { run.version = (await read({ gentle: true })).version; }
            catch { queue = null; outcome = { status: 'unknown' }; onNotice('Đã lưu nhưng không tải lại được sổ. Tải lại trang rồi kiểm tra.'); return; }
          }
        }
        let readBack = true;
        try { await read({ gentle: true }); } catch { readBack = false; }
        if (run.index < run.items.length) continue;   // gõ thêm trong lúc đọc lại: ghi nốt rồi đọc lại lần nữa
        queue = null;
        outcome = { status: 'saved' };
        for (const item of run.items) item.resolve({ status: 'saved', result: item.result });
        onNotice(readBack ? 'Đã lưu.' : 'Đã lưu nhưng không tải lại được sổ. Tải lại trang rồi kiểm tra.');
        return;
      }
    }
    // GIA-O-01 (B): chuỗi lệnh cùng loại trên sổ đang mở (dán cột giá). Lệnh sau dùng phiên bản lệnh trước trả về; đọc lại sổ
    // một lần ở cuối. Mất mạng: `pending` giữ đúng lệnh chưa rõ (cùng khóa), `series` giữ phần còn lại; retry() gửi lại lệnh đó
    // rồi đi tiếp. Lệnh lỗi (sổ vừa đổi, tháng vừa khóa…): dừng, đọc lại sổ. Trả {status: saved|stopped|unknown, done, total}.
    let series = null, running = null;
    // Một vòng ghi một lúc: Thử lại (hay bấm đúp) trong lúc vòng đang chạy chỉ chờ vòng đó, không chạy vòng thứ hai trên cùng
    // `series` (hai vòng cùng tăng chỉ số sẽ bỏ sót một chuyến mà vẫn báo đã ghi đủ).
    // Câu báo vẽ sau khi vòng đã xong (running = null): chưa rõ kết quả thì đầu sổ hiện nút Thử lại, không còn "đang ghi".
    const runSeries = () => (running ??= loopSeries().then(({ notice }) => { running = null; onNotice(notice); return outcome; },
      error => { running = null; throw error; }));
    async function loopSeries() {
      const run = series, total = run.items.length;
      while (run.index < total) {
        pending ??= { path: run.path, body: { customer_id: customerId, expected_version: run.version, idempotency_key: key(), ...run.items[run.index] } };
        let response, result;
        try {
          response = await fetcher(pending.path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pending.body) });
          result = await response.json();
        } catch {
          outcome = { status: 'unknown', done: run.index, total };
          return { notice: unknown };
        }
        if (!response.ok && result?.error === 'RESULT_UNKNOWN') { outcome = { status: 'unknown', done: run.index, total }; return { notice: unknown }; }
        if (!response.ok || !Number.isSafeInteger(result?.version)) {
          pending = null;
          try { await read(); } catch { /* sổ không đọc lại được: câu báo dưới đây vẫn nói rõ đã ghi bao nhiêu */ }
          series = null;
          outcome = { status: 'stopped', done: run.index, total, result };
          return { notice: `Ghi được ${run.index}/${total} giá rồi dừng: ${result?.message || 'không lưu được thao tác.'} Kiểm tra các chuyến còn lại.` };
        }
        run.version = result.version; run.index += 1; pending = null;
      }
      // Chuỗi còn giữ (đang chạy) tới khi đọc lại sổ xong: lệnh khác gửi vào lúc đó vẫn bị chặn, không đọc nhầm kết quả.
      let readBack = true;
      try { await read(); } catch { readBack = false; }
      series = null;
      outcome = { status: 'saved', done: total, total };
      return { notice: readBack ? `Đã ghi ${total} giá.` : `Đã ghi ${total} giá nhưng không tải lại được sổ. Tải lại trang rồi kiểm tra.` };
    }
    async function submitSeries(action, list) {
      if (queueRun) await queueRun;
      if (running) throw Error(busyText);
      if (pending || series) throw Error('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.');
      outcome = null;
      if (snapshot?.status !== 'active') throw Error('Khách chưa có số dư đầu hiệu lực.');
      const route = routes[action];
      if (!route || !Array.isArray(list) || !list.length) throw Error('Thao tác không hợp lệ.');
      const items = list.map(fields => Object.fromEntries(route[1].filter(name => Object.hasOwn(fields, name)).map(name => [name, fields[name]])));
      for (const intent of items) for (const name of ['unit_price_vnd', 'other_fee_vnd']) {
        if (Object.hasOwn(intent, name) && intent[name] !== null && typeof intent[name] !== 'string') throw Error('Số tiền phải là chuỗi VND.');
      }
      series = { path: route[0], items, index: 0, version: snapshot.version };
      return await runSeries();
    }
    // Lệnh cấn trừ: trả {status: saved|error|stale|unknown, result} để giao diện biết đóng khung hay giữ lại.
    async function submitOffset(action, fields) {
      if (queueRun) await queueRun;
      outcome = null;
      if (running) throw Error(busyText);
      if (pending) throw Error('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.');
      if (snapshot?.status !== 'active') throw Error('Khách chưa có số dư đầu hiệu lực.');
      const route = offsetRoutes[action];
      if (!route) throw Error('Thao tác không hợp lệ.');
      const intent = Object.fromEntries(route[1].filter(name => Object.hasOwn(fields, name)).map(name => [name, fields[name]]));
      if (route[1].some(name => name !== 'reference' && !Object.hasOwn(intent, name))) throw Error('Thiếu thông tin cấn trừ.');
      for (const name of idFields) {
        if (!Object.hasOwn(intent, name)) continue;
        const number = Number(intent[name]);
        if (!Number.isSafeInteger(number) || number < 0) throw Error('Mã sổ hoặc phiên bản không hợp lệ.');
        intent[name] = number;
      }
      if (Object.hasOwn(intent, 'amount_vnd') && typeof intent.amount_vnd !== 'string') throw Error('Số tiền phải là chuỗi VND.');
      const head = route[2] === 'target'
        ? { target_customer_id: customerId, target_version: snapshot.version }
        : { customer_id: customerId, expected_version: snapshot.version };
      pending = { path: route[0], body: { ...head, idempotency_key: key(), ...intent } };
      outcome = null;
      await send();
      return outcome ?? { status: 'unknown' };
    }
    // Đọc sổ khách khác chỉ để lấy version và mã phiếu phía bên kia của cặp; không đổi snapshot của sổ đang mở.
    async function readOther(otherId) {
      const response = await fetcher(`/api/v7/ledger?customer=${encodeURIComponent(otherId)}`, { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được sổ bên kia của cấn trừ.');
      const data = await response.json();
      if (!data || Number(data.customer_id) !== Number(otherId) || !Number.isSafeInteger(data.version)) throw Error('Dữ liệu sổ bên kia không hợp lệ.');
      return data;
    }
    async function loadOffsetSources() {
      const response = await fetcher(`/api/v7/offset-sources?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được danh sách sổ đang dư tiền.');
      const data = await response.json();
      if (!data || !Array.isArray(data.sources)) throw Error('Danh sách sổ đang dư tiền không hợp lệ.');
      return data.sources;
    }
    // Lệnh danh mục: trả {status, result} như cấn trừ; xong thì đọc lại sổ (send) để vẽ lại.
    async function submitCatalog(action, fields) {
      if (queueRun) await queueRun;
      outcome = null;
      if (running) throw Error(busyText);
      if (pending) throw Error('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.');
      const route = catalogRoutes[action];
      if (!route) throw Error('Thao tác không hợp lệ.');
      const intent = Object.fromEntries(route[1].filter(name => Object.hasOwn(fields, name)).map(name => [name, fields[name]]));
      pending = { path: route[0], body: { idempotency_key: key(), ...intent } };
      outcome = null;
      await send();
      return outcome ?? { status: 'unknown' };
    }
    async function loadFeeTypes() {
      const response = await fetcher('/api/v7/fee-types', { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được danh mục phụ phí.');
      const data = await response.json();
      if (!data || !Array.isArray(data.fee_types)) throw Error('Danh mục phụ phí không hợp lệ.');
      return data.fee_types;
    }
    // Trang khách, thẻ Tình hình (TRANG-KHACH-01): chỉ đọc, không đổi sổ. Tổng quan trả mọi sổ đang nợ; trang lấy dòng của sổ
    // đang mở (không có dòng: sổ không nợ, row = null), kèm ngày số liệu (giờ VN) và quy tắc hạn trả (DASH-03).
    async function readDebt() {
      const response = await fetcher('/api/v7/dashboard/debt', { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được số quá hạn.');
      const data = await response.json();
      if (!data || !Array.isArray(data.customers) || !/^\d{4}-\d\d-\d\d$/.test(data.as_of ?? '')) throw Error('Số quá hạn không hợp lệ.');
      return { asOf: data.as_of, rule: data.rule ?? {}, row: data.customers.find(row => Number(row.customer_id) === customerId) ?? null };
    }
    // Thẻ Trao đổi và Tình hình: hội thoại Zalo có tên khớp tên Sheet của sổ (ZALO-CHAT-01). Máy chủ
    // chưa có bản xuất chat (503 ZALO_EXPORT_UNAVAILABLE, như hao hiện nay) thì conversations = null, không phải lỗi.
    async function findChats() {
      await customersLoaded;
      const name = sheetName(customerId);
      if (!name) throw Error('Chưa biết tên khách để tìm hội thoại.');
      const response = await fetcher(`/api/v7/zalo/conversations?q=${encodeURIComponent(name)}`, { cache: 'no-store' });
      const data = await response.json().catch(() => null);
      if (response.status === 503 && data?.error === 'ZALO_EXPORT_UNAVAILABLE') return { name, conversations: null };
      if (!response.ok || !Array.isArray(data?.conversations)) throw Error('Không đọc được hội thoại Zalo.');
      return { name, conversations: data.conversations };
    }
    // Thẻ Trao đổi (ZALO-GROUP-01): dấu tin của sổ (hứa trả, khách báo đã chuyển, ghi chú; trạng thái máy chủ tính từ phiếu thu)
    // và các group Zalo đã gắn với sổ. Chỉ đọc; dấu là ghi chú ngoài đường tiền.
    async function readMarks() {
      const response = await fetcher(`/api/v7/marks?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được dấu tin Zalo.');
      const data = await response.json();
      if (!Array.isArray(data?.marks)) throw Error('Dấu tin Zalo không hợp lệ.');
      return data.marks;
    }
    async function readZaloLinks() {
      const response = await fetcher('/api/v7/zalo/links', { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được group Zalo đã gắn.');
      const data = await response.json();
      if (!Array.isArray(data?.links)) throw Error('Group Zalo đã gắn không hợp lệ.');
      return data.links.filter(row => Number(row.customer_id) === customerId);
    }
    // Thẻ Hồ sơ (HO-SO-01): group Zalo đã gắn với sổ, kèm tên group và giờ tin cuối lấy từ gói chat trên máy chủ (chỉ group đã
    // chọn lên web). Gói chưa có hoặc đọc lỗi thì vẫn trả group đã gắn, tên để trống.
    async function readZaloGroups() {
      const links = await readZaloLinks();
      if (!links.length) return [];
      const response = await fetcher('/api/v7/zalo/conversations?q=', { cache: 'no-store' }).catch(() => null);
      const data = response?.ok ? await response.json().catch(() => null) : null;
      const known = new Map((Array.isArray(data?.conversations) ? data.conversations : []).map(row => [row.conversation_id, row]));
      return links.map(link => ({ ...link, display_name: known.get(link.conversation_id)?.display_name ?? null,
        last_message_at: known.get(link.conversation_id)?.last_message_at ?? null }));
    }
    // Thẻ Hồ sơ: bảng giá của sổ (BANG-GIA-01), chỉ đọc.
    async function readPrices() {
      const response = await fetcher(`/api/v7/price-table?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được bảng giá.');
      const data = await response.json();
      if (!Array.isArray(data?.price_table?.periods)) throw Error('Bảng giá không hợp lệ.');
      return data.price_table;
    }
    // Debit note (DEBIT-NOTE-03): mẫu đang dùng (v3/v4), thông tin công ty, ngân hàng, tên phí Anh/Trung; file cấu hình máy chủ.
    async function readDebitConfig() {
      const response = await fetcher('/api/v7/debit-note/config', { cache: 'no-store' });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.config || !['v3', 'v4'].includes(data.config.template)) throw Error(data?.message || 'Không đọc được cấu hình debit note.');
      return data.config;
    }
    // THONG-TIN-CTY-01: danh bạ cho hộp debit note v4; chưa bật job thì available: false.
    async function readCompanyInfo() {
      const response = await fetcher('/api/v7/company-info', { cache: 'no-store' });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data || typeof data.available !== 'boolean') throw Error(data?.message || 'Không đọc được Thông tin cty.');
      return data;
    }
    redraw = () => { if (snapshot) (onRedraw ? onRedraw() : onSnapshot(snapshot)); };
    return { read, readEvents, submit, submitSeries, submitOffset, submitCatalog, loadFeeTypes, readOther, loadOffsetSources, readDebt, findChats, readPrices,
      readMarks, readZaloLinks, readZaloGroups, readDebitConfig, readCompanyInfo,
      lastOutcome: () => outcome, retry: async () => { if (series) await runSeries(); else if (queue) await runQueue(); else if (pending) await send(); },
      // NHAP-NHANH-01: hàng đợi đang ghi bình thường là saving(), không phải "còn lệnh chưa rõ" — các nút khác vẫn bấm được
      // (submit chờ hàng đợi xong); kẹt vì mất mạng thì hasPending() như lệnh thường.
      hasPending: () => !!series || !!running || (!queueActive() && (!!pending || !!queue)), snapshot: () => snapshot, quick, saving: () => queueActive(),
      settle: () => Promise.allSettled([inflight, running, queueRun]).then(() => {}),
      sending: () => !!inflight,   // lệnh thường đang gửi (chưa trả lời): chưa phải "chưa rõ kết quả"
      pendingKey: () => pending?.body?.idempotency_key ?? null, outcomeOf: key => settled.get(key) ?? null,   // khóa của lệnh đang chờ: khung phiếu thu biết lệnh chờ có phải phiếu của mình
      // Chuỗi đang ghi (không phải chưa rõ kết quả): đầu sổ báo tiến độ thay cho nút Thử lại.
      progress: () => (series ? { done: series.index, total: series.items.length, running: !!running } : null) };
  }
  const api = { create, stale, unknown, groupCustomers, customerLabel, customerLabels, customerName: id => customerNames.get(String(id)), customerRow: id => customerRows.get(id),
    sheetName, showCustomers: () => showCustomers() };
  if (typeof module !== 'undefined') module.exports = api;
  if (typeof window !== 'undefined') window.SoKhachV7Api = api;
})();
