(() => {
  'use strict';
  // BANG-THU-01: tiền về theo ngày, gom mọi sổ, chỉ xem. Mọi số tiền và phép cộng ở get_receipt_book, trang chỉ định dạng;
  // riêng tổng phiếu Sheet chưa ghi cộng bằng CongNoFormat.sum từ /api/v7/inbox, như tab Đòi nợ.
  const F = CongNoFormat;
  const root = document.getElementById('bang-thu');
  const $ = id => document.getElementById(id);
  const { esc, dateText, full, monthTag, monthTitle } = F;
  const number = value => F.toBig(value).toLocaleString('vi-VN');
  const PLAIN_METHOD = 'THU TIỀN';

  const query = new URLSearchParams(location.search);
  const state = {
    month: /^\d{4}-(0[1-9]|1[0-2])$/.test(query.get('month') ?? '') ? query.get('month') : null,
    view: query.get('xem') === 'khach' ? 'khach' : 'ngay',
    book: null, labels: null, pending: null, showVoided: false, painted: null,
  };
  let turn = 0;

  const json = async url => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw Error(url);
    return response.json();
  };
  const monthKey = iso => String(iso ?? '').slice(0, 7);
  const dayMonth = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  const nameOf = row => state.labels?.get(String(row.customer_id)) ?? row.name;
  const ledgerHref = (id, month) => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}&amp;month=${esc(monthKey(month))}`;

  // Ngày trước ngày `iso`, tính theo lịch, không phụ thuộc múi giờ máy.
  function dayBefore(iso) {
    const [year, month, day] = iso.split('-').map(Number);
    return new Date(Date.UTC(year, month - 1, day - 1)).toISOString().slice(0, 10);
  }
  function dayLabel(iso, asOf) {
    if (iso === asOf) return `Hôm nay ${dayMonth(iso)}`;
    if (iso === dayBefore(asOf)) return `Hôm qua ${dayMonth(iso)}`;
    return dayMonth(iso);
  }

  // Cột Trừ nợ. Phiếu web: các tháng đang được trừ. Dòng Sheet không có phân bổ riêng: tháng của khối ghi nó.
  function debtCell(row, year) {
    if (row.source === 'sheet') {
      const tag = monthTag(row.book_month, year);
      return `<td class="debt" title="Ghi ở khối ${esc(F.monthLabel(row.book_month))} trên Sheet">${esc(tag)}</td>`;
    }
    const lines = row.allocations ?? [];
    if (!lines.length) return '<td class="debt">—</td>';
    const seen = new Set();
    const parts = [];
    for (const line of lines) {
      const text = line.kind === 'advance' ? 'ứng trước' : monthTag(line.month, year);
      if (!seen.has(text)) { seen.add(text); parts.push(text); }
    }
    const title = lines.map(line => `${line.kind === 'advance' ? 'Ứng trước' : `T${F.monthLabel(line.month)}`} ${number(line.amount_vnd)}`).join(' · ');
    return `<td class="debt" title="${esc(title)}">${esc(parts.join(', '))}</td>`;
  }
  // Ô ngày của Sheet có thể là số serial (46327): trùng ngày của dòng thì không lặp lại, khác thì đổi ra ngày để đọc được.
  function plainNote(row) {
    const note = row.note ?? '';
    if (!/^\d{5}(\.0+)?$/.test(note)) return note;
    const iso = new Date(Date.UTC(1899, 11, 30) + parseInt(note, 10) * 86400000).toISOString().slice(0, 10);
    return iso === row.date ? '' : dateText(iso);
  }
  function noteText(row) {
    const method = row.method && row.method !== PLAIN_METHOD ? row.method : '';
    return [method, plainNote(row)].filter(Boolean).join(' · ');
  }
  function receiptRow(row, year) {
    const label = nameOf(row);
    const note = noteText(row);
    return `<tr class="pay"><td class="who"><a class="row-link" href="${ledgerHref(row.customer_id, row.book_month)}" title="Mở sổ ${esc(label)}, tháng ${esc(F.monthLabel(row.book_month))}">${esc(label)}</a></td>`
      + `<td class="num">${esc(number(row.amount_vnd))}</td><td class="note"${note ? ` title="${esc(note)}"` : ''}>${esc(note)}</td>${debtCell(row, year)}</tr>`;
  }
  const count = (n, what = 'phiếu') => `${n.toLocaleString('vi-VN')} ${what}`;

  function byDayTable(book, year) {
    const head = '<thead><tr><th scope="col">Khách</th><th scope="col" class="num">Số tiền</th><th scope="col">Ghi chú</th><th scope="col">Trừ nợ</th></tr></thead>';
    const days = book.days.map(day => `<tbody class="day"><tr class="day-head"><th scope="rowgroup">${esc(dayLabel(day.date, book.as_of))} <small>${esc(count(day.count))}</small></th>`
      + `<td class="num">${esc(number(day.total_vnd))}</td><td colspan="2"></td></tr>${day.rows.map(row => receiptRow(row, year)).join('')}</tbody>`).join('');
    const undated = book.undated.length ? `<tbody class="day undated" id="khong-ro-ngay"><tr class="day-head"><th scope="rowgroup">Không rõ ngày thu <small>${esc(count(book.undated.length))}, chưa cộng vào tổng tháng</small></th>`
      + `<td class="num">${esc(number(book.summary.undated_vnd))}</td><td colspan="2"></td></tr>${book.undated.map(row => receiptRow(row, year)).join('')}</tbody>` : '';
    return `<table class="thu by-day">${head}${days}${undated}</table>`;
  }

  function byCustomerTable(book) {
    const hasUndated = book.customers.some(row => row.undated_count > 0);
    const rows = book.customers.map(row => {
      const label = nameOf(row);
      return `<tr class="pay"><td class="who"><a class="row-link" href="${ledgerHref(row.customer_id, row.book_month)}" title="Mở sổ ${esc(label)}, tháng ${esc(F.monthLabel(row.book_month))}">${esc(label)}</a></td>`
        + `<td class="num">${row.count ? esc(number(row.total_vnd)) : '—'}</td><td class="num">${row.count || '—'}</td>`
        + (hasUndated ? `<td class="num">${row.undated_count ? esc(number(row.undated_vnd)) : '—'}</td>` : '')
        + `<td class="when">${row.last_date ? esc(dateText(row.last_date)) : '—'}</td></tr>`;
    }).join('');
    return `<table class="thu by-customer"><thead><tr><th scope="col">Khách</th><th scope="col" class="num">Đã trả</th><th scope="col" class="num">Số lần</th>`
      + `${hasUndated ? '<th scope="col" class="num">Không rõ ngày</th>' : ''}<th scope="col">Trả gần nhất</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function figures(book) {
    const s = book.summary;
    const isThisMonth = book.month === book.today_month;
    const today = isThisMonth ? `<div class="fig" id="fig-today"><span>Hôm nay ${esc(dayMonth(book.as_of))}</span>`
      + (s.today_count ? `<b>${esc(full(s.today_vnd))}</b><small>${esc(count(s.today_count))}</small>` : '<b class="none">chưa có phiếu</b>') + '</div>' : '';
    const month = `<div class="fig" id="fig-month"><span>${esc(monthTitle(book.month))}</span><b>${esc(full(s.total_vnd))}</b><small>${esc(count(s.count))} · ${esc(count(s.customers, 'khách'))}</small></div>`;
    const inner = `<span>Không rõ ngày</span><b>${esc(full(s.undated_vnd))}</b><small>${esc(count(s.undated_count))}, chưa cộng</small>`;
    const undated = !s.undated_count ? '' : state.view === 'ngay'
      ? `<a class="fig undated" id="fig-undated" href="#khong-ro-ngay">${inner}</a>` : `<div class="fig undated" id="fig-undated">${inner}</div>`;
    return today + month + undated;
  }

  function monthOptions(book) {
    const months = book.months.map(item => item.month);
    if (!months.includes(book.month)) months.push(book.month);
    months.sort().reverse();
    const at = months.indexOf(book.month);
    return { newer: months[at - 1], older: months[at + 1],
      options: months.map(month => `<option value="${esc(monthKey(month))}"${month === book.month ? ' selected' : ''}>${esc(monthTitle(month))}</option>`).join('') };
  }

  function pendingLine() {
    const pending = state.pending;
    if (pending === 'computing') return '<p class="pending unknown" id="pending">Đang kiểm phiếu thu trên Sheet chờ ghi: số ở đây có thể còn thiếu.</p>';
    if (pending === 'unknown') return '<p class="pending unknown" id="pending">Chưa kiểm được phiếu thu trên Sheet chờ ghi: số ở đây có thể còn thiếu.</p>';
    if (!pending) return '';
    return `<a class="pending" id="pending" href="/viec-can-lam.html">Còn ${esc(count(pending.count))} trên Sheet chưa ghi vào web · ${esc(full(pending.amount))} <span aria-hidden="true">›</span></a>`;
  }

  function extras(book) {
    const offsets = book.offsets.length ? `<section class="extra" id="offsets"><h2>Cấn trừ giữa hai sổ <small>không phải tiền mới vào, không cộng vào bảng</small></h2><ul>`
      + book.offsets.map(row => `<li>${esc(dateText(row.date))} · <a href="${ledgerHref(row.source_customer_id, row.date)}">${esc(nameOf({ customer_id: row.source_customer_id, name: row.source_name }))}</a> sang `
        + `<a href="${ledgerHref(row.target_customer_id, row.date)}">${esc(nameOf({ customer_id: row.target_customer_id, name: row.target_name }))}</a> · <span class="money">${esc(number(row.amount_vnd))}</span></li>`).join('')
      + '</ul></section>' : '';
    const voided = book.voided.length ? `<section class="extra" id="voided"><p>${esc(count(book.voided.length))} đã hủy, không tính tiền <button type="button" class="link" id="void-toggle" aria-expanded="${state.showVoided}">${state.showVoided ? 'Ẩn' : 'Xem'}</button></p>`
      + (state.showVoided ? `<ul>${book.voided.map(row => `<li><s class="money">${esc(number(row.amount_vnd))}</s> · <a href="${ledgerHref(row.customer_id, row.date)}">${esc(nameOf(row))}</a> · ${esc(dateText(row.date))} · hủy ${esc(dateText(row.voided_on))}${row.void_reason ? ` · ${esc(row.void_reason)}` : ''}</li>`).join('')}</ul>` : '')
      + '</section>' : '';
    const note = book.summary.has_sheet ? '<p class="tiny" id="sheet-note">Sheet ghi khoản thu ở tháng nợ, bảng này xếp theo ngày tiền về, nên tổng tháng có thể khác "Đã thu" của tháng đó trong sổ.</p>' : '';
    return offsets + voided + note;
  }

  function paint() {
    const book = state.book;
    if (!book) return;
    const signature = JSON.stringify([book, state.pending, state.view, state.showVoided, state.labels ? [...state.labels] : null]);
    if (signature === state.painted) return;
    state.painted = signature;
    const focused = document.activeElement?.id;
    const year = Number(book.month.slice(0, 4));
    const { newer, older, options } = monthOptions(book);
    const empty = !book.days.length && !book.undated.length;
    const body = empty ? `<p class="empty" id="empty">${esc(monthTitle(book.month))} chưa có phiếu thu.</p>`
      : state.view === 'khach' ? byCustomerTable(book) : byDayTable(book, year);
    root.innerHTML = `<section class="head"><div class="month-nav">
        <button type="button" class="btn step" id="month-older" aria-label="Tháng trước"${older ? ` data-month="${esc(monthKey(older))}"` : ' disabled'}>‹</button>
        <select id="month-pick" aria-label="Chọn tháng">${options}</select>
        <button type="button" class="btn step" id="month-newer" aria-label="Tháng sau"${newer ? ` data-month="${esc(monthKey(newer))}"` : ' disabled'}>›</button>
      </div><div class="figs" aria-live="polite">${figures(book)}</div>
      <div class="views" role="group" aria-label="Cách xem"><button type="button" class="btn view" id="view-ngay" data-view="ngay" aria-pressed="${state.view === 'ngay'}">Theo ngày</button><button type="button" class="btn view" id="view-khach" data-view="khach" aria-pressed="${state.view === 'khach'}">Theo khách</button></div></section>
      ${pendingLine()}<section class="list">${body}</section>${extras(book)}`;
    // Vẽ lại không làm mất tiêu điểm; nút đổi tháng vừa bị khóa (hết tháng) thì chuyển sang nút còn lại.
    const again = focused ? $(focused) : null;
    if (again?.disabled) $(focused === 'month-older' ? 'month-newer' : 'month-older')?.focus();
    else again?.focus();
  }

  // Giữ tháng và cách xem trên địa chỉ để bấm Back từ sổ về đúng chỗ.
  function syncAddress() {
    const params = new URLSearchParams();
    if (state.month) params.set('month', state.month);
    if (state.view === 'khach') params.set('xem', 'khach');
    const text = params.toString();
    history.replaceState(null, '', `${location.pathname}${text ? `?${text}` : ''}`);
  }

  function readPending(inbox) {
    if (inbox?.state === 'computing') return 'computing';   // vài phút đầu sau khi API khởi động lại
    if (inbox?.state !== 'ready') return 'unknown';
    const books = (inbox.books ?? []).filter(book => !book.sheet_matched && book.receipts.ready + book.receipts.review > 0);
    if (!books.length) return null;
    return { count: books.reduce((total, book) => total + book.receipts.ready + book.receipts.review, 0), amount: String(F.sum(books.map(book => book.receipts.amount_vnd))) };
  }

  async function load() {
    const mine = ++turn;
    try {
      const [book, customers, inbox] = await Promise.all([
        json(`/api/v7/receipt-book${state.month ? `?month=${state.month}-01` : ''}`),
        state.labels ? null : json('/api/v7/customers').then(body => body.customers ?? []).catch(() => null),
        json('/api/v7/inbox').catch(() => null),
      ]);
      if (mine !== turn) return;   // người dùng vừa đổi tháng: lượt mới hơn sẽ vẽ
      if (customers) { state.labels = F.customerLabels(customers); globalThis.AppNav?.setCustomers(customers); }
      state.book = book;
      state.pending = readPending(inbox);
      const banner = $('demo-banner');
      banner.hidden = !book.demo && !book.real_copy;
      banner.textContent = book.real_copy ? 'Dữ liệu thật · bản sao cô lập, chưa phải prod' : book.demo ? 'Dữ liệu thử · DỮ LIỆU GIẢ' : '';
      $('as-of').textContent = `Số liệu đến ${dateText(book.as_of)}`;
      $('updated-at').textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`;
      paint();
      $('error').hidden = true;
    } catch {
      if (mine !== turn) return;
      const alert = $('error');
      alert.hidden = false;
      alert.innerHTML = `${esc(F.loadError('bảng thu'))}<button type="button" class="btn" id="retry">Thử lại</button>`;
      if (!state.book) root.replaceChildren();
    }
  }

  function showMonth(month) {
    state.month = month;
    state.showVoided = false;
    syncAddress();
    if (state.book) root.querySelector('.list')?.setAttribute('aria-busy', 'true');
    load();
  }

  root.addEventListener('click', event => {
    const step = event.target.closest('.step');
    if (step?.dataset.month) { showMonth(step.dataset.month); return; }
    const view = event.target.closest('[data-view]');
    if (view) { state.view = view.dataset.view; syncAddress(); paint(); return; }
    if (event.target.closest('#void-toggle')) { state.showVoided = !state.showVoided; paint(); }
  });
  root.addEventListener('change', event => {
    if (event.target.id === 'month-pick') showMonth(event.target.value);
  });
  $('error').addEventListener('click', event => { if (event.target.id === 'retry') load(); });
  $('refresh-data').addEventListener('click', load);

  load();
  setInterval(() => { if (!document.hidden && document.activeElement?.id !== 'month-pick') load(); }, 60_000);
})();
