(() => {
  'use strict';
  // ZALO-THU-CHI-01 PR-2: trang Thu chi (chỉ xem). Dữ liệu từ GET /api/v7/cash-chat, hỏi lại 5 giây một lần khi tab hiện; tổng, gom ngày,
  // lọc và câu trạng thái tính ở thu-chi-model.js, file này chỉ định dạng (ARCH-03). Tin chat không bao giờ ghi tiền.
  const F = CongNoFormat;
  const M = ThuChiModel;
  const { esc } = F;
  const $ = id => document.getElementById(id);
  const root = $('thu-chi');
  const POLL_MS = 5000;
  const state = { days: 7, filter: 'all', data: null, raw: '', fresh: new Set() };
  let pollTimer = null;
  let turn = 0;

  const hhmm = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false });
  const clock = ms => (ms == null ? '—' : hhmm.format(ms));
  const dayMonth = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  const dayLabel = (iso, today) => (iso === today ? `Hôm nay ${dayMonth(iso)}` : iso === M.dayShift(today, -1) ? `Hôm qua ${dayMonth(iso)}` : dayMonth(iso));
  const stamp = (iso, today) => (iso ? `${iso.slice(0, 10) === today ? '' : `${dayMonth(iso)} `}${iso.slice(11, 16)}` : '');
  const money = value => F.full(String(value));
  const count = n => n.toLocaleString('vi-VN');

  async function fetchData() {
    const today = state.data?.today ?? F.vnDay(Date.now());
    const { from, to } = M.range(today, state.days);
    const response = await fetch(`/api/v7/cash-chat?from=${from}&to=${to}`, { cache: 'no-store' });
    if (!response.ok) throw Error('cash-chat');
    return response.text();
  }

  // Tuổi dữ liệu Zalo: lấy từ nhịp tim của máy Zalo, không giả là mới. Máy im hoặc Zalo chưa mở thì có dòng cảnh báo riêng.
  function paintZalo(data) {
    const zalo = data.zalo ?? {};
    const at = zalo.state === 'ok' || zalo.state === 'silent' ? zalo.at : data.bundle_at;
    const stale = zalo.state === 'silent' || (zalo.identity === 'waiting_for_zalo' && (zalo.quiet_minutes ?? 0) >= 5);
    const label = $('zalo-at');
    label.textContent = at ? `Zalo cập nhật ${stale ? 'lần cuối ' : ''}lúc ${stamp(at, data.today)}` : 'Zalo: chưa có tin';
    label.classList.toggle('stale', stale);
    label.dataset.tip = data.last_message_at ? `Tin gần nhất lúc ${clock(data.last_message_at)}` : '';
    label.title = label.dataset.tip;
    const warn = $('zalo-warn');
    warn.textContent = zalo.state === 'silent' ? `Máy Zalo không báo về từ ${stamp(zalo.at, data.today)}. Tin mới có thể chưa lên.`
      : stale ? `Zalo chưa mở trên máy Zalo (${count(zalo.quiet_minutes)} phút). Tin mới chưa lên.` : '';
    warn.hidden = !warn.textContent;
  }

  const fig = (kind, sum) => `<div class="tc-fig ${kind}"><b>${esc(money(sum[kind].vnd))}</b><small>${esc(M.KIND_LABEL[kind])} · ${count(sum[kind].n)} khoản</small></div>`;
  function card(title, sum) {
    const pill = (n, text, warn) => `<span class="tc-pill${n ? (warn ? ' warn' : '') : ' zero'}">${esc(text)}: ${count(n)}</span>`;
    return `<section class="tc-card" aria-label="${esc(title)}"><h2>${esc(title)}</h2><div class="tc-figs">${['thu', 'chi', 'ung'].map(kind => fig(kind, sum)).join('')}</div>`
      + `<div class="tc-flags">${pill(sum.missing, 'Chưa vào sổ', true)}${pill(sum.diff, 'Lệch số', true)}${sum.noAmount ? pill(sum.noAmount, 'Không đọc được số', false) : ''}</div></section>`;
  }

  function sumLine(sum) {
    const parts = ['thu', 'chi', 'ung'].filter(kind => sum[kind].n).map(kind => `${M.KIND_LABEL[kind]} ${money(sum[kind].vnd)}`);
    if (sum.missing) parts.push(`${count(sum.missing)} chưa vào sổ`);
    return parts.join(' · ');
  }

  function ledgerLink(item) {
    const ref = item.ledger_ref;
    if (!ref || !['RECORDED', 'AMOUNT_DIFF', 'SUGGEST'].includes(item.status)) return '';
    if (ref.kind === 'receipt') {
      const customer = ref.customer_id ?? item.target.id;
      if (customer == null) return '';
      const month = ref.date ? `&amp;month=${esc(ref.date.slice(0, 7))}` : '';
      return ` <a href="/so-khach-v7-live.html?customer=${encodeURIComponent(customer)}${month}">Mở sổ</a>`;
    }
    return ' <a href="/doi-xe.html">Mở Đội xe</a>';
  }

  function thumbs(item) {
    if (!item.media.length) return '';
    const shown = item.media.slice(0, 3).map(media => `<a href="/api/v7/zalo/media/${esc(media.id)}" target="_blank" rel="noopener" aria-label="Xem ảnh chứng">`
      + `<img src="/api/v7/zalo/media/${esc(media.id)}" alt="Ảnh chứng" loading="lazy"></a>`).join('');
    const more = item.media.length > 3 ? `<span>+${item.media.length - 3}</span>` : '';
    return `<div class="tc-thumbs">${shown}${more}</div>`;
  }

  const TARGET = { so: 'Sổ', xe: 'Xe', tai_xe: 'Tài xế' };
  function row(item) {
    const status = M.statusText(item);
    const target = item.target.kind ? `${TARGET[item.target.kind]} ${item.target.label ?? ''}`.trim() : '—';
    const open = item.conversation_id
      ? `<a class="tc-open" href="/zalo-chat.html?c=${encodeURIComponent(item.conversation_id)}${item.message_id ? `&amp;m=${encodeURIComponent(item.message_id)}` : ''}">Mở tin</a>` : '';
    return `<div class="tc-row${state.fresh.has(M.keyOf(item)) ? ' is-new' : ''}" data-status="${esc(item.status)}">`
      + `<span class="tc-time">${esc(clock(item.sent_at))}</span>`
      + `<div class="tc-who"><b>${esc(item.sender_name ?? 'Không rõ tên')}</b><small title="${esc(item.conversation_name ?? '')}">${esc(item.conversation_name ?? '')}${item.source === 'mark' ? ' · dấu khách báo' : ''}</small></div>`
      + `<span class="tc-kind-cell"><span class="tc-kind ${esc(item.direction)}">${esc(M.KIND_LABEL[item.direction])}</span></span>`
      + `<span class="tc-amt">${item.amount_vnd == null ? '<span class="dash">—</span>' : esc(money(item.amount_vnd))}</span>`
      + `<div class="tc-target">${esc(target)}<span class="tc-text" title="${esc(item.text)}">${esc(item.text)}</span></div>`
      + `<div class="tc-status ${status.tone}"><b>${esc(status.text)}</b>${status.note ? `<small>${esc(status.note)}</small>` : ''}${ledgerLink(item)}</div>`
      + `<div class="tc-side">${thumbs(item)}${open}</div></div>`;
  }

  function render() {
    const data = state.data;
    if (data.unavailable) {
      root.innerHTML = '<p class="empty">Máy chủ chưa có dữ liệu chat Zalo. Khi nhóm Zalo đã chọn được đưa lên máy chủ thì thu chi hiện ở đây.</p>';
      return;
    }
    const all = data.items;
    const keepFocus = document.activeElement?.dataset?.f ?? null;
    const counts = M.counts(all);
    const shown = M.groupByDay(M.filterItems(all, state.filter));
    const range = state.days === 7 ? '7 ngày' : `${state.days} ngày`;
    const filters = M.FILTERS.filter(filter => filter.id !== 'noamount' || counts.noamount || state.filter === 'noamount')
      .map(filter => `<button type="button" class="tc-chip" data-f="${filter.id}" aria-pressed="${filter.id === state.filter}">${esc(filter.label)}<b>${count(counts[filter.id])}</b></button>`).join('');
    const empty = !all.length
      ? `<p class="empty">Chưa có khoản thu chi nào trong ${range}. Chỉ tin bắt đầu bằng thu, chi hoặc ứng kèm số tiền mới hiện ở đây, ví dụ: thu 50tr Khách A.</p>`
      : !shown.length ? '<p class="empty">Không có khoản nào trong bộ lọc này.</p>' : '';
    root.innerHTML = `<div class="tc-band">${card('Hôm nay', M.summarize(all.filter(item => item.day === data.today)))}${card(`${range} gần nhất`, M.summarize(all))}</div>`
      + `<div class="tc-filters" role="group" aria-label="Lọc khoản">${filters}</div>${empty}`
      + shown.map(group => `<section class="tc-day" aria-label="${esc(dayLabel(group.day, data.today))}"><header><h3>${esc(dayLabel(group.day, data.today))}</h3>`
        + `<span class="sums">${esc(sumLine(group.sum))}</span></header>${group.rows.map(row).join('')}</section>`).join('');
    if (keepFocus) root.querySelector(`[data-f="${keepFocus}"]`)?.focus();
  }

  async function load({ initial = false } = {}) {
    const mine = ++turn;
    try {
      const text = await fetchData();
      if (mine !== turn) return;
      $('error').hidden = true;
      const data = JSON.parse(text);
      paintZalo(data);
      if (text === state.raw) return;
      const before = state.data?.items ?? [];
      const added = state.data && !data.unavailable ? M.newKeys(before, data.items ?? []) : [];
      state.raw = text;
      state.data = data;
      state.fresh = new Set(added);
      $('new-note').textContent = added.length ? `Có ${added.length} khoản mới` : '';
      render();
    } catch {
      if (mine !== turn) return;
      const error = $('error');
      error.innerHTML = state.data
        ? 'Không cập nhật được. Số đang hiện là lần tải trước.'
        : `${esc(F.loadError('thu chi'))} <button type="button" class="btn" id="retry">Thử lại</button>`;
      error.hidden = false;
      $('retry')?.addEventListener('click', () => { load({ initial: true }); });
      if (initial && !state.data) root.innerHTML = '';
    }
  }

  function schedule() {
    clearTimeout(pollTimer);
    pollTimer = document.hidden ? null : setTimeout(async () => { await load(); schedule(); }, POLL_MS);
  }
  document.addEventListener('visibilitychange', () => {
    clearTimeout(pollTimer);
    if (!document.hidden) load().then(schedule);   // tab hiện lại: hỏi ngay một lượt rồi theo nhịp 5 giây; tab ẩn thì ngừng
  });
  root.addEventListener('click', event => {
    const chip = event.target.closest('[data-f]');
    if (!chip) return;
    state.filter = chip.dataset.f;
    render();
  });
  $('range').addEventListener('change', event => {
    state.days = Number(event.target.value);
    state.data = null;   // khoảng khác thì không so với bản cũ để tìm khoản mới
    state.raw = '';
    root.innerHTML = '<p class="loading">Đang tải thu chi…</p>';
    load();
  });
  $('refresh-data').addEventListener('click', () => { state.raw = ''; load(); });

  load({ initial: true }).then(schedule);
})();
