(() => {
  'use strict';
  // NHAC-NO-01: tab Đòi nợ — khách quá hạn + mốc "đã nhắc" (reminder_log), nút Copy tin nhắc.
  // Chỉ dùng metadata công nợ + mốc nhắc; không đụng nội dung tin nhắn.
  const F = CongNoFormat;
  const root = document.getElementById('doi-no');
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const FILTERS = [['all', 'Tất cả'], ['chua-nhac', 'Chưa nhắc'], ['nhac-cho', 'Đã nhắc, chưa trả']];
  const state = { asOf: null, rows: [], byId: new Map(), names: new Map(), filter: 'all' };
  let loading = false;

  const json = async url => {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw Error(url);
    return response.json();
  };
  const post = (url, body) => fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });

  // Chênh lệch ngày giữa hai chuỗi YYYY-MM-DD (a - b), tính theo lịch, không phụ thuộc múi giờ máy.
  const dayDiff = (a, b) => {
    if (!a || !b) return null;
    const toUTC = s => { const [y, m, d] = s.split('-').map(Number); return Date.UTC(y, m - 1, d); };
    return Math.round((toUTC(a) - toUTC(b)) / 86400000);
  };
  const monthLabel = key => `Tháng ${key.slice(5, 7)}/${key.slice(0, 4)}`;

  const transportText = mode => ({ CANG: 'cảng', BO: 'bộ' })[mode] ?? (mode ? String(mode).toLowerCase() : '');
  const commodityText = (commodity, mode) => commodity ? `${commodity}${transportText(mode) ? ` · ${transportText(mode)}` : ''}` : 'Chưa phân loại';
  // Tên hiển thị: tên Sheet; trùng tên thì thêm số sổ.
  function buildNames(customers) {
    const base = row => row.display_name ?? row.name;
    const dupe = name => customers.filter(item => base(item) === name).length > 1;
    return new Map(customers.map(row => [String(row.id), dupe(base(row)) ? `${base(row)} · sổ ${row.id}` : base(row)]));
  }
  const nameOf = id => state.names.get(String(id)) ?? state.byId.get(id)?.name ?? `Sổ ${id}`;

  function statusOf(row) {
    const rem = row.reminder;
    if (!rem || !rem.last_reminded) return { key: 'chua-nhac', label: 'Chưa nhắc', tone: 'bad' };
    const paidAfter = row.last_receipt_date && row.last_receipt_date > rem.last_reminded;
    if (paidAfter) return { key: 'da-tra', label: 'Đã trả sau khi nhắc', tone: 'ok' };
    const days = dayDiff(state.asOf, rem.last_reminded);
    return { key: 'nhac-cho', label: days ? `Đã nhắc ${days} ngày, chưa trả` : 'Đã nhắc hôm nay', tone: 'watch' };
  }

  function matchFilter(row) {
    if (state.filter === 'all') return true;
    const key = statusOf(row).key;
    if (state.filter === 'chua-nhac') return key === 'chua-nhac';
    if (state.filter === 'nhac-cho') return key === 'nhac-cho';
    return true;
  }

  // Tin nhắc: tổng nợ, phần quá hạn, nợ từng tháng còn lại. Số đồng chính xác để dán vào group.
  function buildMessage(row) {
    const lines = [`Kính gửi ${nameOf(row.customer_id)},`,
      `Tổng công nợ còn lại: ${F.full(row.outstanding_vnd)}`,
      `Trong đó quá hạn: ${F.full(row.overdue_vnd)}`];
    const months = (row.months ?? []).filter(m => F.toBig(m.outstanding_vnd) > 0n);
    if (months.length) {
      lines.push('Chi tiết nợ theo tháng:');
      for (const m of months) lines.push(`- ${monthLabel(m.month)}: ${F.full(m.outstanding_vnd)}`);
    }
    lines.push('Kính nhờ anh/chị sắp xếp thanh toán giúp. Xin cảm ơn!');
    return lines.join('\n');
  }

  function toast(text, bad = false) {
    const node = $('toast');
    node.textContent = text;
    node.classList.toggle('bad', bad);
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
  }

  async function copyRemind(id) {
    const row = state.byId.get(id);
    if (!row) return;
    let copied = false;
    try {
      await navigator.clipboard.writeText(buildMessage(row));
      copied = true;
    } catch { /* clipboard bị chặn: vẫn ghi mốc nhắc, báo người dùng copy tay */ }
    try {
      const response = await post('/api/v7/reminders', { customer_id: id, source: 'copy-button' });
      if (!response.ok) throw Error('post');
      const result = await response.json();
      row.reminder = {
        last_reminded: result.reminded_at ?? state.asOf,
        reminder_count: (row.reminder?.reminder_count ?? 0) + (row.reminder ? 0 : 1),
        last_source: 'copy-button',
      };
      paint();
      toast(copied ? `Đã copy tin & ghi "đã nhắc" ${nameOf(id)}` : `Đã ghi "đã nhắc" ${nameOf(id)} (chưa copy được, copy tay)`, !copied);
    } catch {
      toast(copied ? 'Đã copy tin, nhưng chưa ghi được mốc nhắc. Thử lại.' : 'Chưa copy và chưa ghi được. Thử lại.', true);
    }
  }

  function paint() {
    const rows = state.rows.filter(matchFilter);
    const unreminded = state.rows.filter(r => statusOf(r).key === 'chua-nhac').length;
    const filterBtns = FILTERS.map(([key, label]) => {
      const count = key === 'all' ? state.rows.length : state.rows.filter(r => statusOf(r).key === key).length;
      return `<button type="button" class="chip" data-filter="${key}" aria-pressed="${state.filter === key}">${esc(label)} <b>${count}</b></button>`;
    }).join('');
    const list = rows.length ? rows.map(row => {
      const st = statusOf(row);
      const rem = row.reminder;
      const remText = rem && rem.last_reminded
        ? `${esc(rem.last_reminded)}${dayDiff(state.asOf, rem.last_reminded) ? ` · ${dayDiff(state.asOf, rem.last_reminded)} ngày trước` : ' · hôm nay'}`
        : '<i class="muted">chưa nhắc</i>';
      const paid = row.last_receipt_date ? esc(row.last_receipt_date) : '<i class="muted">chưa có</i>';
      return `<div class="rrow s-${st.key}">
        <span class="who"><i class="dot r-${esc(row.risk)}" aria-hidden="true"></i><span class="nm">${esc(nameOf(row.customer_id))}</span><small>${esc(commodityText(row.commodity, row.transport_mode))}</small></span>
        <span class="num od" title="${esc(F.full(row.overdue_vnd))}">${esc(F.short(row.overdue_vnd))}</span>
        <span class="num" title="${esc(F.full(row.outstanding_vnd))}">${esc(F.short(row.outstanding_vnd))}</span>
        <span class="when">${paid}</span>
        <span class="when">${remText}</span>
        <span class="st ${st.tone}">${esc(st.label)}</span>
        <span class="acts"><button type="button" class="btn copy" data-copy="${row.customer_id}">Copy tin nhắc</button><a class="btn chat" href="/zalo-chat.html?q=${encodeURIComponent(nameOf(row.customer_id).replace(/ · sổ \d+$/, ''))}" title="Mở hội thoại Zalo với khách này">Chat</a></span>
      </div>`;
    }).join('') : `<p class="empty">${state.filter === 'all' ? 'Không có khách quá hạn.' : 'Không có khách khớp lọc này.'}</p>`;
    root.innerHTML = `<section class="card">
      <div class="card-head"><h2>Khách quá hạn cần đòi <small>${state.rows.length} khách · ${unreminded} chưa nhắc</small></h2></div>
      <div class="filters">${filterBtns}</div>
      <div class="rhead"><span>Khách</span><span class="num">Quá hạn</span><span class="num">Còn nợ</span><span class="when">Trả gần nhất</span><span class="when">Nhắc gần nhất</span><span class="st">Trạng thái</span><span></span></div>
      <div class="rlist">${list}</div>
      <p class="tiny">"Đã nhắc" ghi khi bạn bấm Copy tin nhắc (dán vào Zalo). Nút Chat mở lại hội thoại Zalo với khách từ bản xuất (<a href="/zalo-chat.html">xem mọi hội thoại</a>).</p>
    </section>`;
  }

  root.addEventListener('click', event => {
    const copy = event.target.closest('[data-copy]');
    if (copy) { copyRemind(Number(copy.dataset.copy)); return; }
    const filter = event.target.closest('[data-filter]');
    if (filter) { state.filter = filter.dataset.filter; paint(); }
  });

  async function load() {
    if (loading) return;
    loading = true;
    try {
      const [debt, reminders, customers] = await Promise.all([
        json('/api/v7/dashboard/debt'),
        json('/api/v7/reminders').then(body => body.reminders ?? []).catch(() => []),
        json('/api/v7/customers').then(body => body.customers ?? []).catch(() => []),
      ]);
      state.asOf = debt.as_of;
      if (debt.as_of) {
        const [year, month, day] = debt.as_of.split('-');
        $('as-of').textContent = `Số liệu đến ${day}/${month}/${year}`;
      }
      state.byId = new Map();
      state.rows = (debt.customers ?? []).filter(row => F.toBig(row.overdue_vnd) > 0n);
      state.names = buildNames(customers);
      const rem = new Map(reminders.map(r => [r.customer_id, r]));
      for (const row of state.rows) { row.reminder = rem.get(row.customer_id) ?? null; state.byId.set(row.customer_id, row); }
      paint();
      $('error').hidden = true;
      $('updated-at').textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })} · tự tải mỗi 60 giây`;
    } catch {
      const alert = $('error');
      alert.hidden = false;
      alert.textContent = 'Không tải được số liệu đòi nợ. Bấm Làm mới để thử lại.';
      if (!root.querySelector('.card')) root.replaceChildren();
    } finally { loading = false; }
  }

  load();
  $('refresh-data')?.addEventListener('click', load);
  setInterval(() => { if (!document.hidden && document.activeElement?.tagName !== 'BUTTON') load(); }, 60_000);
})();
