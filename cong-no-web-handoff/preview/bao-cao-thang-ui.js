(() => {
  'use strict';
  // BAO-CAO-THANG-01 (specs/v7-bao-cao-thang.md): tháng này có những khách nào, đi bao nhiêu cont, đối chiếu booking (CONT_NGUON,
  // CONT_BO), Sheet sổ nợ và sổ web. Chỉ xem. Số đếm do GET /api/v7/report/month tính; chữ và lọc ở bao-cao-thang-model.js.
  const F = CongNoFormat;
  const M = BaoCaoThangModel;
  const { esc, dateText, monthTitle } = F;
  const $ = id => document.getElementById(id);
  const root = $('bao-cao');
  const svg = body => `<svg viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
  const ICON = { prev: svg('<path d="M15 6l-6 6 6 6"/>'), next: svg('<path d="M9 6l6 6-6 6"/>'), open: svg('<path d="M9 6l6 6-6 6"/>') };
  const query = new URLSearchParams(location.search);
  const state = {
    month: M.MONTH.test(query.get('month') ?? '') ? query.get('month') : null,
    onlyIssues: query.get('lech') === '1',
    family: ['BIEN', 'BO'].includes(query.get('loai')) ? query.get('loai') : null,
    open: new Set(), body: null, painted: null,
  };
  let turn = 0;

  const number = value => (value === null || value === undefined ? '—' : Number(value).toLocaleString('vi-VN'));
  const ledgerHref = (id, month) => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}&amp;month=${esc(month)}`;
  const dayMonth = iso => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : '');
  const tipAttr = lines => ` data-tip="${esc(lines.filter(Boolean).join('\n'))}"`;
  const timeText = iso => {
    const at = new Date(iso);
    if (!iso || Number.isNaN(at.getTime())) return '';
    const part = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', hour12: false }).formatToParts(at);
    const get = type => part.find(item => item.type === type)?.value ?? '';
    return `${get('hour')}:${get('minute')} ${get('day')}/${get('month')}`;
  };

  function syncAddress() {
    const next = new URLSearchParams();
    if (state.month) next.set('month', state.month);
    if (state.onlyIssues) next.set('lech', '1');
    if (state.family) next.set('loai', state.family);
    const text = next.toString();
    history.replaceState(null, '', `${location.pathname}${text ? `?${text}` : ''}`);
  }

  function paintMonthNav(body) {
    const list = M.months(body.start, body.current ? body.month : (body.end ?? body.month));
    if (!list.includes(body.month)) list.push(body.month);
    list.sort().reverse();
    const at = list.indexOf(body.month);
    const newer = list[at - 1], older = list[at + 1];
    const step = (id, label, icon, target, edge) => `<button type="button" class="btn icon-btn step" id="${id}" aria-label="${label}"${target ? ` data-month="${esc(target)}"${tipAttr([monthTitle(target)])}` : ` disabled${tipAttr([edge])}`}>${icon}</button>`;
    $('month-nav').innerHTML = `${step('month-older', 'Tháng trước', ICON.prev, older, 'Chưa có báo cáo tháng cũ hơn')}<select id="month-pick" aria-label="Chọn tháng">${
      list.map(month => `<option value="${esc(month)}"${month === body.month ? ' selected' : ''}>${esc(monthTitle(month))}</option>`).join('')}</select>${
      step('month-newer', 'Tháng sau', ICON.next, newer, 'Đang ở tháng mới nhất')}`;
  }

  function notice(body) {
    const at = timeText(body.checked_at);
    if (body.state === 'none') return '<p class="note bad">Chưa có kết quả đối chiếu Sheet với booking. Máy chạy mỗi giờ từ 7 tới 22 giờ; bảng dưới chỉ có số web.</p>';
    if (body.state === 'outside') return `<p class="note warn">Tháng này trước khi có đủ hai bảng booking (biển từ 12/2025) nên chỉ có số web.</p>`;
    if (body.state === 'stale') return `<p class="note warn">Số Sheet và booking là của lượt ${esc(at)}, cũ hơn một giờ: lượt máy gần nhất chưa chạy xong hoặc bị lỗi.</p>`;
    return '';
  }

  function summary(body) {
    const rows = M.summaryRows(body.totals, body.current);
    const cell = (value, flag) => `<td class="num${flag && value ? ' flag' : ''}">${number(value)}</td>`;
    const at = timeText(body.checked_at);
    const notes = [
      at ? `Booking và Sheet theo lượt máy lúc ${esc(at)}; web theo lúc mở trang.` : 'Web theo lúc mở trang.',
      'Booking là hai tab CONT_NGUON (biển) và CONT_BO (bộ). Tháng theo ngày chuyến.',
      body.current ? 'Tháng đang chạy: chuyến mới thường lên Sheet chậm một hai ngày.' : '',
      body.before_book ? `${number(body.before_book)} chuyến booking trước khi có sổ khách nằm trong số dư đầu kỳ, không tính.` : '',
    ].filter(Boolean);
    return `<section class="sum" aria-label="Tổng tháng"><table class="sum-table"><thead><tr><th scope="col">${esc(monthTitle(body.month))}</th><th scope="col">Biển</th><th scope="col">Bộ</th><th scope="col">Tổng</th></tr></thead>
      <tbody>${rows.map(row => `<tr class="${row.flag ? 'gap' : ''}"><th scope="row">${esc(row.label)}</th>${row.values.map(value => cell(value, row.flag)).join('')}</tr>`).join('')}</tbody></table>
      <ul class="sum-notes">${notes.map(text => `<li>${text}</li>`).join('')}</ul></section>`;
  }

  function chipHtml(chip) {
    return `<span class="chip ${chip.tone}">${esc(chip.text)}</span>`;
  }

  function tripRows(item, body) {
    const head = '<tr><th scope="col">Container</th><th scope="col">Ngày chuyến</th><th scope="col">Booking</th><th scope="col">Sheet</th><th scope="col">Web</th><th scope="col">Tình trạng</th></tr>';
    const lines = item.rows.map(row => {
      const status = M.statusOf(row, body.current);
      const booking = row.booking ? `${dayMonth(row.booking.date)}${row.booking.ref ? ` · ${esc(row.booking.ref)}` : ''}` : '—';
      const sheet = row.row ? `dòng ${esc(row.row)}${row.block && row.block !== body.month ? ` · khối ${esc(row.block.slice(5, 7))}/${esc(row.block.slice(0, 4))}` : ''}${row.amount_vnd ? ` · ${esc(F.short(row.amount_vnd, 'tr'))}` : row.status === 'chep' ? ' · 0đ' : ''}` : '—';
      const web = row.web ? `${dayMonth(row.web.date)}${row.web.source === 'legacy' ? ' · sổ gốc' : ''}` : '—';
      const day = row.booking?.date ?? row.date ?? row.web?.date;
      return `<tr class="t-${status.tone}"><td class="cont">${esc(row.cont)}</td><td class="day">${day ? esc(dateText(day)) : '<span class="muted">không ngày</span>'}</td>
        <td>${booking}</td><td>${sheet}</td><td>${web}</td><td>${chipHtml(status)}</td></tr>`;
    }).join('');
    const link = item.book_id ? `<a class="open-book" href="${ledgerHref(item.book_id, body.month)}">Mở sổ ${esc(monthTitle(body.month).toLowerCase())} ${ICON.open}</a>`
      : `<span class="muted">${item.name ? 'Chưa có sổ web cùng tên tab Sheet' : `Chủ hàng trên booking: ${esc(item.owner || '—')}; máy chưa đoán được sổ`}</span>`;
    return `<tr class="trips"><td colspan="7"><div class="trips-box"><table class="trip-table"><thead>${head}</thead><tbody>${lines}</tbody></table>${link}</div></td></tr>`;
  }

  function customers(body) {
    const list = M.filter(body.customers, state);
    const all = body.customers.length;
    const issues = body.customers.filter(item => item.issues > 0).length;
    const seg = (value, label) => `<button type="button" class="seg${state.family === value ? ' on' : ''}" data-family="${value ?? ''}" aria-pressed="${state.family === value}">${label}</button>`;
    const rows = list.map(item => {
      const key = M.customerKey(item);
      const open = state.open.has(key);
      const name = item.name ? esc(item.name) : `<span class="muted">Chưa rõ sổ · ${esc(item.owner || '—')}</span>`;
      const chips = M.chips(item, body.current);
      return `<tr class="cust${item.issues ? ' has-issue' : ''}${open ? ' open' : ''}" data-key="${esc(key)}">
        <th scope="row"><button type="button" class="cust-btn" aria-expanded="${open}"><span class="caret" aria-hidden="true"></span><span class="who">${name}</span>${item.commodity ? `<span class="com">${esc(item.commodity)}</span>` : ''}</button></th>
        <td>${esc(M.familyText(item.families))}</td><td class="num">${number(item.booking)}</td><td class="num">${number(item.sheet)}</td><td class="num">${number(item.web)}</td>
        <td><div class="chips">${chips.length ? chips.map(chipHtml).join('') : '<span class="chip ok">Khớp</span>'}</div></td>
        <td class="num money">${item.amount_vnd && item.amount_vnd !== '0' ? esc(F.short(item.amount_vnd, 'tr')) : '—'}</td></tr>${open ? tripRows(item, body) : ''}`;
    }).join('');
    return `<section class="cust-box" aria-label="Theo khách"><div class="cust-tools"><h2>Khách <span class="muted">(${number(list.length)}${list.length !== all ? `/${number(all)}` : ''})</span></h2>
      <label class="only"><input type="checkbox" id="only-issues"${state.onlyIssues ? ' checked' : ''}> Chỉ khách cần xem <span class="muted">(${number(issues)})</span></label>
      <div class="segs" role="group" aria-label="Lọc biển hay bộ">${seg(null, 'Tất cả')}${seg('BIEN', 'Biển')}${seg('BO', 'Bộ')}</div></div>
      <table class="cust-table"><thead><tr><th scope="col">Khách</th><th scope="col">Loại</th><th scope="col" class="num">Booking</th><th scope="col" class="num">Sheet</th><th scope="col" class="num">Web</th><th scope="col">Cần xem</th><th scope="col" class="num">Tiền trên Sheet</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="7" class="empty">Không có khách nào khớp bộ lọc.</td></tr>'}</tbody></table></section>`;
  }

  function paint() {
    const body = state.body;
    if (!body) return;
    const signature = JSON.stringify([body, state.onlyIssues, state.family, [...state.open]]);
    if (signature === state.painted) return;
    state.painted = signature;
    paintMonthNav(body);
    root.innerHTML = `${notice(body)}${summary(body)}${customers(body)}`;
    document.body.dataset.loaded = '1';
  }

  async function load() {
    const mine = ++turn;
    try {
      const response = await fetch(`/api/v7/report/month${state.month ? `?month=${state.month}` : ''}`, { cache: 'no-store' });
      if (!response.ok) throw Error(String(response.status));
      const body = await response.json();
      if (mine !== turn) return;   // người dùng vừa đổi tháng: lượt mới hơn sẽ vẽ
      state.body = body;
      state.month = state.month ?? body.month;
      $('as-of').textContent = `Cập nhật ${timeText(body.now)}`;
      $('error').hidden = true;
      paint();
    } catch {
      if (mine !== turn) return;
      const alert = $('error');
      alert.hidden = false;
      alert.innerHTML = `${esc(F.loadError('báo cáo tháng'))}<button type="button" class="btn" id="retry">Thử lại</button>`;
      if (!state.body) root.replaceChildren();
      document.body.dataset.loaded = '1';
    }
  }

  function showMonth(month) {
    if (!M.MONTH.test(month ?? '') || month === state.month) return;
    state.month = month;
    state.open.clear();
    syncAddress();
    load();
  }

  document.addEventListener('click', event => {
    const target = event.target.closest('button, a');
    if (!target) return;
    if (target.id === 'retry' || target.id === 'refresh-data') return load();
    if (target.dataset.month) return showMonth(target.dataset.month);
    if (target.classList.contains('seg')) {
      state.family = target.dataset.family || null;
      syncAddress();
      return paint();
    }
    if (target.classList.contains('cust-btn')) {
      const key = target.closest('tr').dataset.key;
      if (state.open.has(key)) state.open.delete(key); else state.open.add(key);
      paint();
      document.querySelector(`tr.cust[data-key="${CSS.escape(key)}"] .cust-btn`)?.focus();
    }
  });
  document.addEventListener('change', event => {
    if (event.target.id === 'month-pick') showMonth(event.target.value);
    if (event.target.id === 'only-issues') {
      state.onlyIssues = event.target.checked;
      syncAddress();
      paint();
      $('only-issues')?.focus();
    }
  });
  load();
})();
