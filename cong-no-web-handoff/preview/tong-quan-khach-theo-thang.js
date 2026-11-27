/* Tổng quan: khối "Khách theo tháng" ở cuối trang (KHACH-THANG-01, 28/11/2026). Chọn một tháng (‹ ›, mặc định tháng hiện tại,
 * ?thang=yyyy-mm trên địa chỉ) thì thấy mọi sổ có phát sinh, đã thu hoặc còn nợ của tháng đó: phát sinh và đã thu như dòng
 * Tổng tháng của Sổ khách, còn nợ của tháng như ô của Công nợ theo tháng. Số do GET /api/v7/month-customers tính; trang chỉ
 * vẽ. Bấm dòng mở Sổ khách đúng tháng. Khối nằm ngoài #dashboard nên lượt vẽ lại của dashboard-v7.js không xóa nó. Chỉ đọc. */
(() => {
  'use strict';
  const F = CongNoFormat;
  const node = document.getElementById('khach-thang');
  if (!node) return;
  const { esc } = F;
  const PAGE_ROWS = 10;
  const MONTH = /^(\d{4})-(0[1-9]|1[0-2])$/;
  const vnNow = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit' }).format(new Date()).slice(0, 7);
  const shift = (key, by) => {
    const [y, m] = key.split('-').map(Number);
    const at = new Date(Date.UTC(y, m - 1 + by, 1));
    return `${at.getUTCFullYear()}-${String(at.getUTCMonth() + 1).padStart(2, '0')}`;
  };
  const title = key => `Tháng ${Number(key.slice(5))}/${key.slice(0, 4)}`;
  const tipAttr = lines => ` data-tip="${esc(lines.filter(Boolean).join('\n'))}"`;
  const svg = body => `<svg viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
  const ICON = { prev: svg('<path d="M15 6l-6 6 6 6"/>'), next: svg('<path d="M9 6l6 6-6 6"/>') };
  const asked = new URLSearchParams(location.search).get('thang') ?? '';
  const state = { month: MONTH.test(asked) && asked <= vnNow() ? asked : vnNow(), body: null, error: null, all: false, names: new Map(), turn: 0 };
  const ledgerHref = (id, key) => `/so-khach-v7-live.html?customer=${encodeURIComponent(id)}&month=${key}`;
  // Số 0 là "–" như bảng khách của Tổng quan; số đầy đủ ở chữ rê chuột.
  const cell = (value, label) => (F.toBig(value) === 0n ? '<td class="num zero">–</td>'
    : `<td class="num"${tipAttr([label, F.full(value)])}>${esc(F.short(value))}</td>`);

  // Giữ ?thang= trên địa chỉ (tháng hiện tại thì bỏ), không đụng tham số lọc của phần trên.
  function writeUrl() {
    const query = new URLSearchParams(location.search);
    if (state.month === vnNow()) query.delete('thang'); else query.set('thang', state.month);
    history.replaceState(history.state, '', location.pathname + (query.toString() ? `?${query}` : ''));
  }

  function paint() {
    const now = vnNow();
    const nav = `<div class="kt-nav" role="group" aria-label="Chọn tháng"><button type="button" class="btn icon-btn" data-kt="-1" aria-label="Tháng trước">${ICON.prev}</button>`
      + `<b id="kt-month" aria-live="polite">${esc(title(state.month))}</b>`
      + `<button type="button" class="btn icon-btn" data-kt="1" aria-label="Tháng sau"${state.month >= now ? ' disabled' : ''}>${ICON.next}</button></div>`;
    const head = `<div class="list-head"><h2 id="h-kt">Khách theo tháng</h2>${nav}</div>`;
    const body = state.body?.month?.slice(0, 7) === state.month ? state.body : null;
    let main;
    if (state.error && !body) main = `<p class="empty">${esc(state.error)} <button type="button" class="btn" data-kt-retry>Thử lại</button></p>`;
    else if (!body) main = '<p class="empty">Đang tải khách của tháng…</p>';
    else if (!body.customers.length) main = `<p class="empty">${esc(title(state.month))} chưa có khách nào có phát sinh, tiền thu hay nợ.</p>`;
    else {
      const rows = state.all ? body.customers : body.customers.slice(0, PAGE_ROWS);
      const name = id => state.names.get(String(id)) ?? `Sổ ${id}`;
      const sum = `<p class="kt-sum">${body.customers.length} khách · phát sinh <b${tipAttr(['Phát sinh', F.full(body.charges_vnd)])} tabindex="0">${esc(F.short(body.charges_vnd))}</b>`
        + ` · đã thu <b${tipAttr(['Đã thu trong tháng', F.full(body.received_vnd)])} tabindex="0">${esc(F.short(body.received_vnd))}</b>`
        + ` · còn nợ <b${tipAttr(['Còn nợ của tháng', 'Phần phát sinh tháng này chưa được trả', F.full(body.outstanding_vnd)])} tabindex="0">${esc(F.short(body.outstanding_vnd))}</b></p>`;
      const table = '<div class="tbl-wrap"><table class="dtable kt-table"><thead><tr><th scope="col">Khách</th>'
        + `<th scope="col" class="r"><span${tipAttr(['Phát sinh', 'Chuyến, phụ phí, điều chỉnh của tháng (như dòng Tổng tháng của Sổ khách)'])} tabindex="0">Phát sinh</span></th>`
        + `<th scope="col" class="r"><span${tipAttr(['Đã thu', 'Tiền khách trả trong tháng, theo ngày tiền về'])} tabindex="0">Đã thu</span></th>`
        + `<th scope="col" class="r"><span${tipAttr(['Còn nợ', 'Phần phát sinh của tháng chưa được trả (như ô Công nợ theo tháng)'])} tabindex="0">Còn nợ</span></th>`
        + '<th scope="col" class="go"><span class="sr-only">Mở</span></th></tr></thead><tbody>'
        + rows.map(row => `<tr data-kt-id="${row.customer_id}"><td class="who"><a href="${ledgerHref(row.customer_id, state.month)}"><span class="nm">${esc(name(row.customer_id))}</span></a></td>`
          + cell(row.charges_vnd, 'Phát sinh') + cell(row.received_vnd, 'Đã thu') + cell(row.outstanding_vnd, 'Còn nợ của tháng')
          + `<td class="go" aria-hidden="true">${ICON.next}</td></tr>`).join('')
        + '</tbody></table></div>';
      const more = body.customers.length > rows.length ? `<div class="more"><button type="button" class="btn" data-kt-more>Hiện cả ${body.customers.length} khách</button></div>` : '';
      main = sum + table + more;
    }
    const focused = document.activeElement?.closest?.('#khach-thang [data-kt]')?.dataset.kt;
    node.innerHTML = `<section class="debtors kt" aria-labelledby="h-kt">${head}${main}</section>`;
    if (focused) node.querySelector(`[data-kt="${focused}"]:not(:disabled)`)?.focus();
  }

  async function load() {
    const mine = ++state.turn, month = state.month;
    try {
      const [body, customers] = await Promise.all([
        CongNoNet.fetchJson(`/api/v7/month-customers?month=${month}-01`, { what: 'khách của tháng' }),
        CongNoNet.customers().then(data => data.customers ?? []).catch(() => []),
      ]);
      if (mine !== state.turn) return;
      if (body?.month?.slice(0, 7) !== month || !Array.isArray(body.customers)) throw Error('Dữ liệu khách của tháng không hợp lệ.');
      state.names = F.customerLabels(customers);
      state.body = body;
      state.error = null;
    } catch (error) {
      if (mine !== state.turn) return;
      state.error = CongNoNet.messageOf(error, 'Không tải được khách của tháng.');
    }
    paint();
  }

  node.addEventListener('click', event => {
    const step = event.target.closest('[data-kt]');
    if (step && !step.disabled) {
      state.month = shift(state.month, Number(step.dataset.kt));
      state.all = false; state.error = null;
      writeUrl(); paint(); load(); return;
    }
    if (event.target.closest('[data-kt-more]')) { state.all = true; paint(); return; }
    if (event.target.closest('[data-kt-retry]')) { state.error = null; paint(); load(); return; }
    // Bấm chỗ khác trên dòng cũng mở sổ như bấm tên.
    const line = event.target.closest('tr[data-kt-id]');
    if (line && !event.target.closest('a')) location.href = ledgerHref(line.dataset.ktId, state.month);
  });

  paint();
  load();
  // Cùng nhịp với phần trên của Tổng quan; máy chủ giữ bản đọc theo dấu dữ liệu nên lượt không đổi gì rất nhẹ.
  setInterval(() => { if (!document.hidden && document.activeElement?.id !== 'customer-search') load(); }, 60_000);
  document.getElementById('refresh-data')?.addEventListener('click', () => load());
})();
