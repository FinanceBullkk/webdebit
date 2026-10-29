(() => {
  'use strict';
  const F = CongNoFormat;
  const currentYear = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric' }).format(new Date()));
  const currentMonth = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', month: 'numeric' }).format(new Date()));
  // Mở từ Tổng quan: ?tuoi=0–3 (nhóm tuổi nợ) và ?con-no=1 (chỉ khách còn nợ).
  const opened = new URLSearchParams(location.search);
  const state = { year: currentYear, data: null, query: '', commodity: '', onlyOpen: opened.get('con-no') === '1', request: 0, detail: 0, detailFocus: null,
    age: /^[0-3]$/.test(opened.get('tuoi') ?? '') ? Number(opened.get('tuoi')) : null };
  const AGES = ['Tháng này', '1–2 tháng trước', '3–6 tháng trước', 'Trên 6 tháng'];
  // Nhóm tuổi của một tháng như get_dashboard; tháng sau tháng hiện tại không thuộc nhóm nào trên ma trận.
  const ageOf = month => {
    const diff = (currentYear - state.year) * 12 + currentMonth - month;
    return diff < 0 ? -1 : diff === 0 ? 0 : diff <= 2 ? 1 : diff <= 6 ? 2 : 3;
  };
  const pickClass = month => state.age == null ? '' : ageOf(month) === state.age ? ' pick' : ' dim';
  const markUpdated = () => { const node = document.querySelector('#updated-at'); if (node) node.textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`; };
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[ch]);
  const vnd = F.toBig;
  const fmt = value => F.full(typeof value === 'bigint' ? value : vnd(String(value)));
  const signed = value => value == null ? '—' : F.full(typeof value === 'bigint' ? value : vnd(value));
  const short = value => F.short(value, 'tr');
  const yearMin = 2000;
  const yearMax = currentYear + 1;
  const MONTHS = Array.from({ length: 12 }, (_, index) => index + 1);
  const yearTotal = customer => vnd(customer.total_year_vnd);
  const allTotal = customer => vnd(customer.total_all_vnd);
  const monthValue = (customer, month) => vnd(customer.months?.[String(month)]);
  const transportText = mode => ({ CANG: 'cảng', 'CẢNG': 'cảng', BO: 'bộ', 'BỘ': 'bộ' })[mode] ?? (mode ? String(mode).toLowerCase() : '');
  // Nhóm theo mặt hàng · phương thức, như Tổng quan; '' là chưa phân loại.
  const groupKey = customer => customer.commodity ? customer.commodity + (transportText(customer.transport_mode) ? ' · ' + transportText(customer.transport_mode) : '') : '';
  const groupLabel = key => key || 'Chưa phân loại';
  const compareDesc = (a, b) => (b > a ? 1 : b < a ? -1 : 0);

  function validatePayload(payload, year) {
    if (payload.year !== year || !Array.isArray(payload.customers)) throw Error('Dữ liệu ma trận từ API không hợp lệ.');
    vnd(payload.grand_total_year_vnd); vnd(payload.grand_total_all_vnd);
    for (const customer of payload.customers) {
      if (!Number.isSafeInteger(customer.customer_id) || customer.customer_id <= 0 || typeof customer.name !== 'string'
          || (customer.commodity !== null && typeof customer.commodity !== 'string')) throw Error('Dữ liệu khách từ API không hợp lệ.');
      vnd(customer.total_year_vnd); vnd(customer.total_all_vnd);
      for (const month of MONTHS) monthValue(customer, month);
    }
  }

  function showError(message) {
    const el = $('#error');
    el.hidden = !message;
    el.textContent = message || '';
  }

  const monthClass = month => 'm' + (month % 2 ? '' : ' even') + pickClass(month);

  function heatCell(customer, month) {
    const value = monthValue(customer, month);
    const attrs = 'data-id="' + esc(customer.customer_id) + '" data-month="' + month + '" type="button" title="' + esc(fmt(value < 0n ? -value : value)) + (value < 0n ? ' (dư)' : '') + '"';
    if (value === 0n) return '<td class="' + monthClass(month) + '"></td>';
    if (value < 0n) return '<td class="' + monthClass(month) + '"><button class="cell-btn neg money" ' + attrs + '>dư ' + esc(short(-value)) + '</button></td>';
    const step = F.heatStep(value);
    return '<td class="' + monthClass(month) + '"><button class="cell-btn money" ' + attrs + ' style="background:var(--heat-' + step + ');color:' + (step >= 5 ? '#fff' : 'var(--ink)') + '">' + esc(short(value)) + '</button></td>';
  }

  function totalCell(value, cls) {
    if (value === 0n) return '<td class="tot ' + cls + ' muted">—</td>';
    return '<td class="tot ' + cls + (value < 0n ? ' neg' : '') + '" title="' + esc(fmt(value < 0n ? -value : value)) + '">' + (value < 0n ? 'dư ' + esc(short(-value)) : esc(short(value))) + '</td>';
  }

  function renderSummary(data) {
    const debtors = data.customers.filter(customer => allTotal(customer) > 0n);
    const creditors = data.customers.filter(customer => allTotal(customer) < 0n);
    const receivable = F.sum(debtors.map(customer => customer.total_all_vnd));
    const credit = -F.sum(creditors.map(customer => customer.total_all_vnd));
    const other = receivable - F.sum(debtors.map(customer => customer.total_year_vnd));
    const put = (id, value) => { $(id).textContent = F.short(value); $(id).title = fmt(value); };
    put('#scope-receivable', receivable);
    put('#scope-credit', credit);
    put('#scope-other', other);
    $('#scope-other-label').textContent = state.year === currentYear ? 'Trong đó nợ từ trước ' + state.year : 'Trong đó nợ ngoài năm ' + state.year;
    const closed = data.customers.length - debtors.length - creditors.length;
    $('#scope-status').innerHTML = '<span><b>' + debtors.length + '</b> khách còn nợ</span><span class="muted">' + creditors.length + ' đang dư · ' + closed + ' đã tất toán</span>';
  }

  function paintAgePick() {
    const box = $('#age-pick');
    box.hidden = state.age == null;
    if (state.age == null) return;
    const months = MONTHS.filter(month => ageOf(month) === state.age);
    const span = months.length ? 'tháng ' + months[0] + (months.length > 1 ? '–' + months.at(-1) : '') + '/' + state.year : 'không có tháng nào trong năm ' + state.year;
    box.innerHTML = '<span>Đang xem nhóm <b>' + AGES[state.age] + '</b> (' + span + (state.age === 3 ? ', kể cả nợ ngoài năm ở cột Mọi năm' : '') + ') — chỉ hiện khách có nợ trong nhóm này.</span><button type="button" class="btn" id="age-clear">Bỏ chọn nhóm</button>';
    $('#age-clear').addEventListener('click', () => {
      state.age = null;
      const query = new URLSearchParams(location.search); query.delete('tuoi');
      history.replaceState(null, '', location.pathname + (query.toString() ? '?' + query : ''));
      render();
    });
  }

  function render() {
    const data = state.data;
    if (!data) return;
    const rows = data.customers.filter(customer => {
      const matchesText = !state.query || (customer.name + ' ' + groupKey(customer)).toLocaleLowerCase('vi').includes(state.query);
      const matchesCommodity = state.commodity === '' ? true : groupKey(customer) === (state.commodity === '__none' ? '' : state.commodity);
      // Nhóm trên 6 tháng gồm cả nợ ngoài năm đang xem (cột Mọi năm lớn hơn cột Năm).
      const inAge = state.age == null || MONTHS.some(month => ageOf(month) === state.age && monthValue(customer, month) > 0n)
        || (state.age === 3 && allTotal(customer) > yearTotal(customer));
      return matchesText && matchesCommodity && inAge && (!state.onlyOpen || allTotal(customer) > 0n);
    });
    paintAgePick();
    const groups = new Map();
    rows.forEach(customer => {
      const key = groupKey(customer);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(customer);
    });
    const groupAll = members => F.sum(members.map(customer => customer.total_all_vnd));
    const ordered = [...groups.entries()].sort((a, b) => {
      if (a[0] === '') return 1;
      if (b[0] === '') return -1;
      return compareDesc(groupAll(a[1]), groupAll(b[1])) || a[0].localeCompare(b[0], 'vi');
    });
    const isCurrent = month => state.year === currentYear && month === currentMonth;
    $('#heat-head').innerHTML = '<th class="khach" scope="col">Khách</th>' +
      MONTHS.map(month => '<th class="mh' + (month % 2 ? '' : ' even') + (isCurrent(month) ? ' cur' : '') + pickClass(month).replace(' dim', '') + '" scope="col">Tháng ' + month + '</th>').join('') +
      '<th class="tot" scope="col">Năm ' + state.year + '</th><th class="tot" scope="col">Mọi năm</th>';
    const parts = [];
    for (const [key, members] of ordered) {
      members.sort((a, b) => compareDesc(allTotal(a), allTotal(b)) || a.name.localeCompare(b.name, 'vi'));
      parts.push('<tr class="group"><td class="khach" title="' + esc(groupLabel(key)) + '">' + esc(groupLabel(key)) + '<span class="n">(' + members.length + ')</span></td><td colspan="12"></td>' +
        totalCell(F.sum(members.map(customer => customer.total_year_vnd)), 'yr') + totalCell(groupAll(members), 'all') + '</tr>');
      members.forEach((customer, index) => {
        parts.push('<tr class="' + (index % 2 ? 'alt' : '') + '"><td class="khach"><a href="/so-khach-v7-live.html?customer=' + esc(customer.customer_id) + '" title="Mở sổ ' + esc(customer.name) + '">' + esc(customer.name) + '</a></td>' +
          MONTHS.map(month => heatCell(customer, month)).join('') + totalCell(yearTotal(customer), 'yr') + totalCell(allTotal(customer), 'all') + '</tr>');
      });
    }
    $('#heat-body').innerHTML = parts.length ? parts.join('') : '<tr><td colspan="15" class="empty-message">Không có khách phù hợp.</td></tr>';
    const monthSums = MONTHS.map(month => F.sum(rows.map(customer => monthValue(customer, month))));
    const footCell = value => '<td title="' + esc(fmt(value)) + '">' + (value === 0n ? '—' : esc(short(value))) + '</td>';
    $('#heat-foot').innerHTML = '<tr><td class="khach">Tổng ' + rows.length + ' khách<span>đã trừ tiền khách dư</span></td>' + monthSums.map(footCell).join('') +
      footCell(F.sum(rows.map(customer => customer.total_year_vnd))) + footCell(F.sum(rows.map(customer => customer.total_all_vnd))) + '</tr>';

    renderSummary(data);
    $('#year-cur').textContent = state.year;
    $('#as-of').textContent = data.as_of ? 'Số liệu đến ' + data.as_of.split('-').reverse().join('/') : '';
    const monthSum = F.sum(data.customers.flatMap(customer => MONTHS.map(month => monthValue(customer, month))));
    const customerYearSum = F.sum(data.customers.map(customer => customer.total_year_vnd));
    const customerAllSum = F.sum(data.customers.map(customer => customer.total_all_vnd));
    const matches = monthSum === customerYearSum && customerYearSum === vnd(data.grand_total_year_vnd) && customerAllSum === vnd(data.grand_total_all_vnd);
    $('#recon').innerHTML = matches ? '<b>✓ Khớp</b> — cộng 12 tháng bằng cột năm, cộng các khách bằng dòng tổng.' : 'LỆCH giữa ô tháng, cột khách và tổng toàn bảng. Cần kiểm tra nguồn.';
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
      const values = [...new Set(payload.customers.map(groupKey).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'));
      const select = $('#commodity');
      select.replaceChildren(new Option('Tất cả mặt hàng', ''));
      values.forEach(value => select.add(new Option(value, value)));
      if (payload.customers.some(customer => !groupKey(customer))) select.add(new Option('Chưa phân loại', '__none'));
      select.value = state.commodity;
      state.commodity = select.value;
      render();
      markUpdated();
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
    $('#drawer-meta').textContent = 'Tháng ' + month + '/' + state.year + ' · ' + groupLabel(groupKey(customer));
    $('#drawer-body').innerHTML = '<div class="kv big"><span>Còn lại tháng này</span><b class="money">' + signed(monthValue(customer, month)) + '</b></div><p class="note">Đang tải chi tiết sổ…</p>';
    $('#drawer').hidden = false; $('#drawer-scrim').hidden = false; document.body.classList.add('drawer-open'); $('#drawer-close').focus();
    try {
      const response = await fetch('/api/v7/receivables/detail?customer=' + customerId + '&month=' + date + '-01', { cache: 'no-store' });
      const ledger = await response.json();
      if (!response.ok || ledger.status !== 'active') throw Error('Không tải được chi tiết tháng.');
      if (detail !== state.detail || $('#drawer').hidden) return;
      const trips = ledger.trips || [];
      const opening = ledger.opening;
      let html = '<div class="kv big"><span>Còn lại tháng này</span><b class="money">' + signed(monthValue(customer, month)) + '</b></div>';
      if (vnd(ledger.outstanding_vnd) !== monthValue(customer, month)) html += '<div class="warnbox">Ô ma trận và chi tiết sổ không khớp. Cần kiểm tra nguồn.</div>';
      if (opening) html += '<div class="warnbox">Tháng số dư đầu: khoản mục lịch sử, không có chi tiết theo container.</div>';
      html += '<div class="kv"><span>' + (opening ? 'Nợ ghi vào kỳ (gồm số dư đầu)' : 'Phát sinh trong tháng') + '</span><b class="money">' + signed(ledger.charges_vnd) + '</b></div><div class="kv"><span>Thu đã phân bổ vào tháng</span><b class="money">' + signed(ledger.received_vnd) + '</b></div>';
      if (trips.length) html += '<h3>Chuyến / container trong tháng</h3><table class="mini-table"><thead><tr><th>Container</th><th>Ngày</th><th class="money">Đơn giá</th><th class="money">Phụ phí</th><th class="money">Thành tiền</th></tr></thead><tbody>' + trips.map(trip => '<tr><td>' + esc(trip.container || '—') + '</td><td>' + esc(trip.event_date || '—') + '</td><td class="money">' + signed(trip.unit_price_vnd) + '</td><td class="money">' + signed(trip.other_fee_vnd) + '</td><td class="money">' + signed(trip.amount_vnd) + '</td></tr>').join('') + '</tbody></table>';
      html += '<p class="note">Thu phân bổ theo tháng, theo nợ cũ trước; không phân bổ theo container.</p><p class="note"><a href="/so-khach-v7-live.html?customer=' + customerId + '">Mở sổ khách ›</a></p>';
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
  const refresh = () => { if ($('#drawer').hidden && !document.querySelector('input:focus,select:focus')) load(state.year); };
  $('#refresh-data').addEventListener('click', () => load(state.year));
  setInterval(() => { if (!document.hidden) refresh(); }, 60_000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  $('#find').addEventListener('input', event => { state.query = event.target.value.trim().toLocaleLowerCase('vi'); render(); });
  $('#commodity').addEventListener('change', event => { state.commodity = event.target.value; render(); });
  $('#only-open').checked = state.onlyOpen;
  $('#only-open').addEventListener('change', event => { state.onlyOpen = event.target.checked; render(); });
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
