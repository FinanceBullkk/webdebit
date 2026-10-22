/* Client V7: server giữ số dư và phân bổ; key giữ nguyên khi chưa rõ kết quả. */
(() => {
  'use strict';
  const routes = {
    paste: ['/api/v7/trips/paste', ['debt_month', 'trips']],
    price: ['/api/v7/trips/price', ['trip_id', 'unit_price_vnd', 'other_fee_vnd']],
    tripAdjust: ['/api/v7/trips/adjust', ['trip_id', 'new_amount_vnd', 'field', 'new_value_vnd', 'note']],
    monthAdjust: ['/api/v7/months/adjust', ['debt_month', 'amount_vnd', 'note']],
    receipt: ['/api/v7/receipts', ['date', 'method', 'amount_vnd', 'reference']],
    receiptMeta: ['/api/v7/receipts/meta', ['pid', 'date', 'method', 'reference']],
    receiptVoid: ['/api/v7/receipts/void', ['pid', 'reason']],
    lock: ['/api/v7/months/lock', ['month', 'locked']],
  };
  // Cấn trừ hai sổ (CT-2SO): một lệnh ghi cả hai sổ, cần version của cả hai. 'target' = sổ đang mở là sổ nhận.
  const offsetRoutes = {
    offset: ['/api/v7/offsets', ['source_customer_id', 'source_version', 'date', 'amount_vnd', 'reference'], 'target'],
    offsetVoid: ['/api/v7/offsets/void', ['other_version', 'offset_pair_id', 'reason'], 'self'],
    offsetDate: ['/api/v7/offsets/date', ['other_version', 'offset_pair_id', 'date'], 'self'],
  };
  const idFields = ['source_customer_id', 'source_version', 'other_version', 'offset_pair_id'];
  const stale = 'Sổ vừa thay đổi. Kiểm tra dữ liệu mới rồi thực hiện lại.';
  const unknown = 'Chưa rõ lệnh đã lưu. Thử lại bằng cùng yêu cầu.';
  const tripFields = ['date', 'booking', 'container', 'carrier', 'from', 'to', 'note', 'src', 'unitPriceVnd', 'otherFeeVnd'];
  const customerNames = new Map();

  // Danh sách khách tải sau sổ: vẽ lại qua renderer để tên khách vào đúng tiêu đề, không chép đè DOM.
  let redraw = null;
  // Nút "Đổi khách" ở đầu sổ: mở danh sách khách và đặt con trỏ vào ô tìm.
  let showCustomers = () => document.querySelector('#customer-search')?.focus();
  const realCopyText = 'Dữ liệu thật · bản sao cô lập, chưa phải prod';

  async function loadCustomers(fetcher = fetch) {
    const search = document.querySelector('#customer-search');
    const list = document.querySelector('#customer-list');
    if (!search || !list) return;
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
      for (const row of customers) customerNames.set(row.id, row.name);
      // Plain links, not a <select>: the embedded app browser does not open native select popups.
      const current = new URLSearchParams(location.search).get('customer');
      const href = row => `/so-khach-v7-live.html?customer=${encodeURIComponent(row.id)}`;
      let found = [];
      let listAll = !current;
      const render = () => {
        const query = search.value.trim().toLocaleLowerCase();
        found = customers.filter(row => row.name.toLocaleLowerCase().includes(query));
        // Before typing, list everyone only when no customer is open yet or the search box is in use.
        const shown = query || listAll ? found.slice(0, 50) : [];
        list.replaceChildren(...shown.map(row => {
          const link = document.createElement('a');
          link.href = href(row);
          link.textContent = row.status === 'active' ? row.name : `${row.name} (chưa có số dư đầu)`;
          if (String(row.id) === current) link.setAttribute('aria-current', 'page');
          return link;
        }));
        document.querySelector('#customer-count').textContent = query || listAll
          ? `${found.length} khách${found.length > shown.length ? ` · hiện ${shown.length}, gõ thêm để lọc` : ''}`
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
    }
  }
  if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', () => { loadCustomers(); });

  function create({ customerId, fetcher = fetch, key = () => crypto.randomUUID(), onSnapshot = () => {}, onNotice = () => {} }) {
    let snapshot = null;
    let pending = null;
    let outcome = null;
    async function read() {
      const response = await fetcher(`/api/v7/ledger?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      if (!response.ok) throw Error('Không đọc được sổ khách.');
      const next = await response.json();
      if (!next || next.customer_id !== customerId || !Number.isSafeInteger(next.version)) throw Error('Dữ liệu sổ không hợp lệ.');
      const banner = typeof document !== 'undefined' && document.querySelector('#demo-banner');
      if (banner) {
        if (next.real_copy === true) banner.textContent = realCopyText;
        banner.hidden = next.demo !== true && next.real_copy !== true;
      }
      snapshot = next;

      onSnapshot(next);
      return next;
    }
    async function send() {
      try {
        const response = await fetcher(pending.path, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pending.body),
        });
        const result = await response.json();
        if (!response.ok) {
          if (result.error === 'STALE_LEDGER') {
            outcome = { status: 'stale' };
            pending = null;
            snapshot = null;
            try { await read(); } catch { onNotice('Không tải được sổ mới. Tải lại trang rồi kiểm tra.'); return; }
            onNotice(stale);
            return;
          }
          if (result.error === 'RESULT_UNKNOWN') { outcome = { status: 'unknown' }; onNotice(unknown); return; }
          outcome = { status: 'error', result };
          pending = null;
          onNotice(result.message || 'Không lưu được thao tác.');
          return result;
        }
        outcome = { status: 'saved', result };
        await read();
        pending = null;
        onNotice(result.duplicate_reference ? 'Đã lưu. Tham chiếu trùng với phiếu khác trong sổ.' : 'Đã lưu.');
      } catch {
        outcome = { status: 'unknown' };
        onNotice(unknown);
      }
    }
    async function submit(action, fields) {
      if (pending) throw Error('Còn thao tác chưa rõ kết quả. Thử lại thao tác đó trước.');
      if (snapshot?.status !== 'active') throw Error('Khách chưa có số dư đầu hiệu lực.');
      const route = routes[action];
      if (!route) throw Error('Thao tác không hợp lệ.');
      const intent = Object.fromEntries(route[1].filter(name => Object.hasOwn(fields, name)).map(name => [name, fields[name]]));
      if (Array.isArray(intent.trips)) intent.trips = intent.trips.map(trip =>
        Object.fromEntries(tripFields.filter(name => Object.hasOwn(trip, name)).map(name => [name, trip[name]])));
      for (const name of ['amount_vnd', 'new_amount_vnd', 'new_value_vnd', 'unit_price_vnd', 'other_fee_vnd']) {
        if (Object.hasOwn(intent, name) && intent[name] !== null && typeof intent[name] !== 'string') throw Error('Số tiền phải là chuỗi VND.');
      }
      for (const trip of intent.trips ?? []) {
        if (['unitPriceVnd', 'otherFeeVnd'].some(name => trip[name] !== null && trip[name] !== undefined && typeof trip[name] !== 'string')) throw Error('Số tiền phải là chuỗi VND.');
      }
      pending = { path: route[0], body: { customer_id: customerId, expected_version: snapshot.version,
        idempotency_key: key(), ...intent } };
      return await send();
    }
    // Lệnh cấn trừ: trả {status: saved|error|stale|unknown, result} để giao diện biết đóng khung hay giữ lại.
    async function submitOffset(action, fields) {
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
    redraw = () => { if (snapshot) onSnapshot(snapshot); };
    return { read, submit, submitOffset, readOther, loadOffsetSources, retry: async () => { if (pending) await send(); }, hasPending: () => !!pending,
      snapshot: () => snapshot };
  }
  const api = { create, stale, unknown, customerName: id => customerNames.get(id), showCustomers: () => showCustomers() };
  if (typeof module !== 'undefined') module.exports = api;
  if (typeof window !== 'undefined') window.SoKhachV7Api = api;
})();
