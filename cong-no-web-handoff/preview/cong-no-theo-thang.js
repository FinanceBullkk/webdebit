(() => {
  'use strict';
  const currentYear = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric' }).format(new Date()));
  const state = { year: currentYear, data: null, query: '', commodity: '', request: 0, detail: 0, detailFocus: null };
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[ch]);
  const vnd = value => {
    if (typeof value !== 'string' || !/^-?[0-9]+$/.test(value)) throw Error('Dữ liệu tiền từ API không hợp lệ.');
    return BigInt(value);
  };
  const fmt = value => (typeof value === 'bigint' ? value : vnd(String(value))).toLocaleString('vi-VN') + ' đ';
  const signed = value => {
    if (value == null) return '—';
    const amount = typeof value === 'bigint' ? value : vnd(value);
    return amount < 0n ? '−' + fmt(-amount) : fmt(amount);
  };
  const yearMin = 2000;
  const yearMax = currentYear + 1;
  const monthKey = month => String(month);
  const yearTotal = customer => vnd(customer.total_year_vnd);
  const allTotal = customer => vnd(customer.total_all_vnd);
  const monthValue = (customer, month) => vnd(customer.months?.[monthKey(month)]);

  function validatePayload(payload, year) {
    if (payload.year !== year || !Array.isArray(payload.customers)) throw Error('Dữ liệu ma trận từ API không hợp lệ.');
    vnd(payload.grand_total_year_vnd); vnd(payload.grand_total_all_vnd);
    for (const customer of payload.customers) {
      if (!Number.isSafeInteger(customer.customer_id) || customer.customer_id <= 0 || typeof customer.name !== 'string'
          || (customer.commodity !== null && typeof customer.commodity !== 'string')) throw Error('Dữ liệu khách từ API không hợp lệ.');
      vnd(customer.total_year_vnd); vnd(customer.total_all_vnd);
      for (let month = 1; month <= 12; month++) monthValue(customer, month);
    }
  }

  function showError(message) {
    const el = $('#error');
    el.hidden = !message;
    el.textContent = message || '';
  }

  function heatCell(customer, month, max) {
    const value = monthValue(customer, month);
    const attrs = 'data-id="' + esc(customer.customer_id) + '" data-month="' + month + '"';
    if (value === 0n) return '<td class="empty-cell"><span class="cell-btn" aria-hidden="true"></span></td>';
    if (value < 0n) return '<td><button class="cell-btn neg money" ' + attrs + '>' + signed(value) + '</button></td>';
    const alpha = Math.min(0.84, 0.12 + Number(value * 72n / (max || 1n)) / 100);
    const color = Math.round(alpha * 255).toString(16).padStart(2, '0');
    return '<td><button class="cell-btn money" ' + attrs + ' style="background:#1e4e8c' + color + ';color:' + (alpha > 0.55 ? '#fff' : '#1e293b') + '">' + fmt(value) + '</button></td>';
  }

  function render() {
    const data = state.data;
    if (!data) return;
    const rows = data.customers.filter(customer => {
      const matchesText = !state.query || (customer.name + ' ' + (customer.commodity ?? '')).toLocaleLowerCase().includes(state.query);
      const matchesCommodity = !state.commodity || (state.commodity === '__none' ? customer.commodity == null : customer.commodity === state.commodity);
      return matchesText && matchesCommodity;
    });
    const groups = new Map();
    rows.forEach(customer => {
      const key = customer.commodity ?? '__none';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(customer);
    });
    const ordered = [...groups.entries()].sort((a, b) => {
      if (a[0] === '__none') return 1;
      if (b[0] === '__none') return -1;
      const total = members => members.reduce((sum, customer) => sum + allTotal(customer), 0n);
      return total(b[1]) > total(a[1]) ? 1 : total(b[1]) < total(a[1]) ? -1 : a[0].localeCompare(b[0], 'vi');
    });
    const max = rows.reduce((maxValue, customer) => {
      for (let month = 1; month <= 12; month++) maxValue = monthValue(customer, month) > maxValue ? monthValue(customer, month) : maxValue;
      return maxValue;
    }, 1n);
    const parts = [];
    let sumYear = 0n, sumAll = 0n;
    for (const [key, members] of ordered) {
      members.sort((a, b) => allTotal(b) > allTotal(a) ? 1 : allTotal(b) < allTotal(a) ? -1 : a.name.localeCompare(b.name, 'vi'));
      const groupYear = members.reduce((sum, customer) => sum + yearTotal(customer), 0n);
      const groupAll = members.reduce((sum, customer) => sum + allTotal(customer), 0n);
      sumYear += groupYear; sumAll += groupAll;
      const label = key === '__none' ? 'Chưa phân loại' : key;
      parts.push('<tr class="group"><th class="glabel">' + esc(label) + '<span class="n">' + members.length + ' khách</span></th><th class="gspacer" colspan="12"></th><th class="gcol-year money">' + (groupYear ? fmt(groupYear) : '—') + '</th><th class="gcol-all money">' + fmt(groupAll) + '</th></tr>');
      for (const customer of members) {
        parts.push('<tr><td class="khach">' + esc(customer.name) + '</td>' + Array.from({ length: 12 }, (_, index) => heatCell(customer, index + 1, max)).join('') + '<td class="total-col money">' + (yearTotal(customer) ? fmt(yearTotal(customer)) : '—') + '</td><td class="all-col money">' + fmt(allTotal(customer)) + '</td></tr>');
      }
    }
    $('#heat-body').innerHTML = parts.length ? parts.join('') : '<tr><td colspan="15" class="empty-message">Không có khách phù hợp.</td></tr>';
    $('#sum-year').textContent = fmt(sumYear);
    $('#sum-all').textContent = fmt(sumAll);
    $('#scope-year').textContent = fmt(vnd(data.grand_total_year_vnd));
    $('#scope-all').textContent = fmt(vnd(data.grand_total_all_vnd));
    $('#scope-year-sub').textContent = 'tổng 12 tháng của ' + state.year + ' · toàn bộ khách';
    $('#scope-old').textContent = (vnd(data.grand_total_all_vnd) - vnd(data.grand_total_year_vnd)).toLocaleString('vi-VN');
    $('#scope-year-label').textContent = state.year;
    $('#th-year').textContent = state.year;
    $('#year-cur').textContent = state.year;
    $('#as-of').textContent = data.as_of ? 'Tính đến ' + data.as_of.split('-').reverse().join('/') : '';
    const monthSum = data.customers.reduce((sum, customer) => sum + Array.from({ length: 12 }, (_, index) => monthValue(customer, index + 1)).reduce((a, b) => a + b, 0n), 0n);
    const customerYearSum = data.customers.reduce((sum, customer) => sum + yearTotal(customer), 0n);
    const customerAllSum = data.customers.reduce((sum, customer) => sum + allTotal(customer), 0n);
    const matches = monthSum === customerYearSum && customerYearSum === vnd(data.grand_total_year_vnd) && customerAllSum === vnd(data.grand_total_all_vnd);
    $('#recon').textContent = matches ? 'Đối chiếu API: 12 ô tháng = cột Năm; tổng khách = tổng toàn bảng. KHỚP.' : 'Đối chiếu API: LỆCH giữa ô tháng, cột khách và tổng toàn bảng. Cần kiểm tra nguồn.';
    $('#recon').classList.toggle('mismatch', !matches);
    $('#year-prev').disabled = state.year <= yearMin;
    $('#year-next').disabled = state.year >= yearMax;
    document.querySelectorAll('.cell-btn[data-id]').forEach(button => button.addEventListener('click', () => openDetail(Number(button.dataset.id), Number(button.dataset.month), button)));
  }

  async function load(year) {
    const request = ++state.request;
    showError('');
    try {
      const response = await fetch('/api/v7/receivables/matrix?year=' + encodeURIComponent(year), { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || 'Không tải được ma trận công nợ.');
      validatePayload(payload, year);
      if (request !== state.request) return;
      state.year = payload.year;
      state.data = payload;
      const banner = $('#demo-banner');
      banner.hidden = !payload.demo && !payload.real_copy;
      banner.textContent = payload.real_copy ? 'Dữ liệu thật · bản sao cô lập, chưa phải prod' : payload.demo ? 'Dữ liệu thử · không phải sổ thật' : '';
      const values = [...new Set(payload.customers.map(customer => customer.commodity).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'));
      const select = $('#commodity');
      select.replaceChildren(new Option('Mặt hàng: tất cả', ''));
      values.forEach(value => select.add(new Option('Mặt hàng: ' + value, value)));
      if (payload.customers.some(customer => customer.commodity == null)) select.add(new Option('Mặt hàng: chưa phân loại', '__none'));
      select.value = state.commodity;
      state.commodity = select.value;
      render();
    } catch (error) {
      if (request !== state.request) return;
      showError(error.message);
      if (!state.data) $('#recon').textContent = '';
    }
  }

  async function openDetail(customerId, month, trigger) {
    const detail = ++state.detail;
    state.detailFocus = trigger;
    const customer = state.data.customers.find(item => item.customer_id === customerId);
    if (!customer) return;
    const date = state.year + '-' + String(month).padStart(2, '0');
    $('#drawer-title').textContent = customer.name;
    $('#drawer-meta').textContent = 'Tháng ' + month + '/' + state.year + ' · ' + (customer.commodity ?? 'Chưa phân loại');
    $('#drawer-body').innerHTML = '<div class="kv big"><span>Còn lại tháng này</span><b class="money">' + signed(monthValue(customer, month)) + '</b></div><p class="note">Đang tải chi tiết sổ…</p>';
    $('#drawer').hidden = false; $('#drawer-scrim').hidden = false; document.body.classList.add('drawer-open'); $('#drawer-close').focus();
    try {
      const response = await fetch('/api/v7/ledger?customer=' + customerId, { cache: 'no-store' });
      const ledger = await response.json();
      if (!response.ok || ledger.status !== 'active') throw Error('Không tải được sổ khách.');
      if (detail !== state.detail || $('#drawer').hidden) return;
      const monthRow = (ledger.months || []).find(row => String(row.month).slice(0, 7) === date);
      const trips = (ledger.trips || []).filter(trip => String(trip.month).slice(0, 7) === date);
      const opening = (ledger.opening || []).some(row => String(row.month).slice(0, 7) === date);
      let html = '<div class="kv big"><span>Còn lại tháng này</span><b class="money">' + signed(monthValue(customer, month)) + '</b></div>';
      if (!monthRow || vnd(monthRow.outstanding_vnd) !== monthValue(customer, month)) html += '<div class="warnbox">Ô ma trận và chi tiết sổ không khớp. Cần kiểm tra nguồn.</div>';
      if (opening) html += '<div class="warnbox">Tháng số dư đầu: khoản mục lịch sử, không có chi tiết theo container.</div>';
      if (monthRow) html += '<div class="kv"><span>' + (opening ? 'Nợ ghi vào kỳ (gồm số dư đầu)' : 'Phát sinh trong tháng') + '</span><b class="money">' + signed(monthRow.charges_vnd) + '</b></div><div class="kv"><span>Thu đã phân bổ vào tháng</span><b class="money">' + signed(monthRow.received_vnd) + '</b></div>';
      if (trips.length) html += '<h3>Chuyến / container trong tháng</h3><table class="mini-table"><thead><tr><th>Container</th><th>Ngày</th><th class="money">Đơn giá</th><th class="money">Phụ phí</th><th class="money">Thành tiền</th></tr></thead><tbody>' + trips.map(trip => '<tr><td>' + esc(trip.container || '—') + '</td><td>' + esc(trip.event_date || '—') + '</td><td class="money">' + signed(trip.unit_price_vnd) + '</td><td class="money">' + signed(trip.other_fee_vnd) + '</td><td class="money">' + signed(trip.amount_vnd) + '</td></tr>').join('') + '</tbody></table>';
      html += '<p class="note">Thu phân bổ theo tháng, theo nợ cũ trước; không phân bổ theo container.</p><p class="note"><a href="/so-khach-v7-live.html?customer=' + customerId + '">Mở sổ khách</a></p>';
      $('#drawer-body').innerHTML = html;
    } catch {
      if (detail !== state.detail || $('#drawer').hidden) return;
      $('#drawer-body').innerHTML += '<p class="note">Không tải được chi tiết sổ. Giá trị ô vẫn lấy từ ma trận API.</p>';
    }
  }

  function closeDrawer() {
    state.detail++;
    $('#drawer').hidden = true; $('#drawer-scrim').hidden = true; document.body.classList.remove('drawer-open');
    if (state.detailFocus?.isConnected) state.detailFocus.focus();
  }
  $('#year-prev').addEventListener('click', () => load(state.year - 1));
  $('#year-next').addEventListener('click', () => load(state.year + 1));
  $('#find').addEventListener('input', event => { state.query = event.target.value.trim().toLocaleLowerCase(); render(); });
  $('#commodity').addEventListener('change', event => { state.commodity = event.target.value; render(); });
  $('#drawer-close').addEventListener('click', closeDrawer);
  $('#drawer-scrim').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', event => {
    if ($('#drawer').hidden) return;
    if (event.key === 'Escape') closeDrawer();
    if (event.key === 'Tab') {
      const focusable = [...$('#drawer').querySelectorAll('button,a[href]')];
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  load(state.year);
})();
