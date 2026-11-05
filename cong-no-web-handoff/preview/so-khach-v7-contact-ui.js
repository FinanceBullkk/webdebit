/* Sổ khách V7 bản live — thẻ Trao đổi và thẻ Hồ sơ của trang khách (TRANG-KHACH-01, specs/v7-trang-khach.md, PR A3), phần A:
 *   Trao đổi: dòng thời gian của sổ, mới nhất ở trên — phiếu thu và cấn trừ (tháng trừ nợ theo dòng phân bổ còn hiệu lực, phiếu
 *     hủy gạch kèm lý do), hội thoại Zalo tìm theo tên, dấu tin Zalo (ZALO-GROUP-01: hứa trả, khách báo đã chuyển, ghi chú); lọc
 *     Tất cả · Hứa trả · Zalo · Thu tiền (Debit note là giai đoạn B); Mở chat (group đã gắn trước, tìm theo tên sau). Nhắc nợ đang
 *     ẩn (NHAC-NO-01, sửa đổi 4/11/2026).
 *   Hồ sơ (HO-SO-01, khung HoSoV4): đầu hồ sơ (chữ viết tắt, tên, mặt hàng · vận chuyển) rồi hai cột 62/38 — thỏa thuận làm việc
 *     (hạn trả theo quy tắc chung DASH-03), giá và phụ phí đang áp theo bảng giá của sổ; group Zalo đã gắn. Mục cần backend (hạn
 *     mức, hợp đồng, người liên hệ, ghi chú, tài liệu) hiện trạng thái trống, nút của chúng báo rõ chưa lưu được.
 * Hai thẻ không ghi tiền; số tiền lấy nguyên từ GET, chỉ định dạng (ARCH-03).
 * Chat, Tổng quan và bảng giá chỉ đọc khi thẻ cần chúng đang mở, đọc lại khi sổ đổi phiên bản hoặc lần đọc đã quá 60
 * giây (như thẻ Tình hình); nguồn nào lỗi thì chỉ khối đó báo lỗi kèm Thử lại. Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).contact = ctx => {
  'use strict';
  const { root, api, live, customerId, escape, dateText, monthKey, monthLabel, showTab, todayIso } = ctx;
  const { full, toBig, commodityText, transportText, vnDay, loadError } = CongNoFormat;
  const FILTERS = [['all', 'Tất cả'], ['hua', 'Hứa trả'], ['lienlac', 'Zalo'], ['thu', 'Thu tiền']];
  // ZALO-GROUP-01: dấu tin Zalo — hứa trả và khách báo đã chuyển vào lọc "Hứa trả", ghi chú vào "Zalo".
  const MARK = { promise: 'Hứa trả', paid_claim: 'Khách báo đã chuyển', note: 'Ghi chú' };
  const MARK_STATUS = { pending: 'đang chờ', kept: 'giữ lời', missed: 'lỡ hẹn', waiting: 'chờ đối chiếu',
    received: 'đã có phiếu thu', not_seen: 'chưa thấy phiếu thu' };
  // Nút ở thẻ Sổ mà thẻ Hồ sơ mở tới: bảng giá và cột phụ phí sửa ở thẻ Sổ (SO-GON-04 L7).
  const OPEN = { 'bang-gia': '.price-table-open', 'phu-phi': '.fee-settings-open' };
  // Nguồn phụ đọc qua so-khach-v7-api.js và thẻ cần chúng; `what` là chữ trong câu đang đọc, câu lỗi.
  const side = { chats: { read: 'findChats', what: 'hội thoại Zalo' },
    marks: { read: 'readMarks', what: 'dấu tin Zalo' }, links: { read: 'readZaloLinks', what: 'group Zalo đã gắn' },
    debt: { read: 'readDebt', what: 'hạn trả' }, prices: { read: 'readPrices', what: 'bảng giá' },
    groups: { read: 'readZaloGroups', what: 'group Zalo đã gắn' } };
  const NEEDS = { 'trao-doi': ['chats', 'marks', 'links'], 'ho-so': ['debt', 'prices', 'groups'] };
  // HO-SO-01: nút của mục cần backend (giai đoạn B) bấm thì báo rõ, không mở khung nhập giả, không ghi gì.
  const SOON = { 'sua-ho-so': 'Chỉnh sửa hồ sơ', 'han-muc': 'Đặt hạn mức', 'hop-dong': 'Tải hợp đồng lên', 'lien-he': 'Thêm người liên hệ',
    'ghi-chu': 'Thêm ghi chú', 'tai-lieu': 'Tải tài liệu lên' };
  for (const item of Object.values(side)) item.state = 'idle';
  let filter = 'all', soon = '';
  const shown = () => document.body?.dataset.the;
  const loaded = item => item.state !== 'error' && Object.hasOwn(item, 'data');
  // Nhãn đọc màn hình bắt đầu bằng chữ trên nút (WCAG 2.5.3), `more` nói thêm nút làm gì.
  const button = (go, text, more = '') => `<button type="button" class="ov-go" data-go="${escape(go)}"`
    + `${more ? ` aria-label="${escape(`${text} — ${more}`)}"` : ''}>${escape(text)}</button>`;
  const sentence = text => { const low = String(text ?? '').toLocaleLowerCase('vi'); return low.charAt(0).toLocaleUpperCase('vi') + low.slice(1); };
  // Khối đọc từ một nguồn phụ: đang đọc, lỗi kèm Thử lại, hoặc nội dung.
  const source = (name, render) => {
    const item = side[name];
    return item.state === 'error' ? `<span class="ct-error" role="alert">${escape(loadError(item.what))} ${button(`retry:${name}`, 'Thử lại')}</span>`
      : loaded(item) ? render(item.data) : `Đang đọc ${item.what}…`;
  };

  // Đọc nguồn phụ của thẻ đang mở: lần đầu, khi sổ đổi phiên bản (vừa ghi) hoặc lần đọc đã quá 60 giây; `only` là nút Thử lại.
  function wake(only = null) {
    const version = ctx.snapshot?.version;
    for (const name of only ? [only] : NEEDS[shown()] ?? []) {
      const item = side[name];
      const fresh = item.state !== 'idle' && item.version === version && Date.now() - item.at < 60_000;
      if (item.state === 'loading' || (!only && fresh)) continue;
      Object.assign(item, { state: 'loading', version });
      api[item.read]().then(data => Object.assign(item, { state: 'ok', data }), () => { item.state = 'error'; })
        .finally(() => { item.at = Date.now(); paint(); });
    }
  }
  // Khung chỉ có nội dung khi thẻ đang mở: dòng thời gian có thể dài, không dựng lại mỗi lần sổ vẽ lại lúc người dùng ở thẻ khác.
  const content = id => (shown() === id && ctx.snapshot ? body(id, ctx.snapshot) : '');
  // Nguồn phụ về sau lần vẽ sổ: chỉ vẽ lại hai khung thẻ này; tiêu điểm đang ở một nút của thẻ thì về nút cùng việc.
  function paint() {
    for (const id of Object.keys(NEEDS)) {
      const pane = root.querySelector(`#the-${id}`);
      if (!pane) continue;
      const focus = pane.contains(document.activeElement) ? document.activeElement.dataset?.go : null;
      pane.innerHTML = content(id);
      if (focus) pane.querySelector(`[data-go="${CSS.escape(focus)}"]`)?.focus();
    }
  }

  // Một mục dòng thời gian: ngày (yyyy-mm-dd), loại để lọc, dòng đầu, các dòng nhỏ.
  const entry = (date, kind, head, facts = [], voided = false) => ({ date: String(date ?? ''), kind, voided,
    html: `${head}${facts.filter(Boolean).map(fact => `<span class="ct-sub">${fact}</span>`).join('')}` });
  // Nút 📎 cho phiếu đã có ảnh: bấm thì sang thẻ Sổ, khung xem ảnh của so-khach-v7-images-ui.js mở ở đó.
  const clip = row => {
    const count = ctx.imageCount?.(row.pid) ?? 0;
    return count ? `<button type="button" class="ov-go image-clip" data-pid="${escape(row.pid)}" `
      + `aria-label="📎 ${count} — xem ảnh chứng từ phiếu ${escape(dateText(row.date))} ở thẻ Sổ">📎 ${count}</button>` : '';
  };
  // Trừ nợ từng tháng (một tháng thì chỉ ghi tháng, như danh sách phiếu ở thẻ Sổ); phần trả dư sau khi hết nợ là ứng trước.
  function share(lines) {
    const debt = lines.filter(line => line.kind !== 'advance');
    const months = debt.map(line => `T${monthLabel(monthKey(line.month))}${lines.length > 1 ? ` ${full(line.amount_vnd)}` : ''}`);
    return [debt.length ? `Trừ nợ ${months.join(' · ')}` : '', ...lines.filter(line => line.kind === 'advance').map(line => `ứng trước ${full(line.amount_vnd)}`)]
      .filter(Boolean).join(' · ');
  }
  // Phiếu thu và cấn trừ vào sổ (receipts[]), khoản cấn trừ sang sổ khác (outgoing_offsets[]). Tháng trừ nợ lấy dòng phân bổ còn
  // hiệu lực (superseded_by_event trống); phiếu đã hủy gạch số tiền, ghi ngày hủy và lý do.
  function money(data) {
    const other = row => `<a href="/so-khach-v7-live.html?customer=${encodeURIComponent(row.counterparty_customer_id)}">${escape(row.counterparty_name)}</a>`;
    const amount = (row, voided) => `<span class="ct-money">${voided ? `<s>${full(row.amount_vnd)}</s>` : full(row.amount_vnd)}</span>`;
    const killed = row => `Đã hủy${row.voided_on ? ` ngày ${escape(dateText(row.voided_on))}` : ''}, không tính tiền · Lý do: ${escape(row.void_reason ?? '')}`;
    const paid = (data.receipts ?? []).map(row => {
      const voided = row.voided_by_event != null;
      const what = row.offset_pair_id != null ? `Cấn trừ từ ${other(row)}` : escape(sentence(row.method));
      return entry(row.date, 'thu', `<b>${what} ${amount(row, voided)}</b>${clip(row)}`, [voided ? killed(row)
        : share((row.allocations ?? []).filter(line => line.superseded_by_event == null)), (note => note ? `Tham chiếu: ${escape(note)}` : '')(CongNoFormat.receiptNote(row.reference, row.date).label)], voided);
    });
    const sent = (data.outgoing_offsets ?? []).map(row => entry(row.date, 'thu', `<b>Cấn trừ sang ${other(row)} ${amount(row, row.voided_by_event != null)}</b>`,
      [row.voided_by_event != null ? killed(row) : ''], row.voided_by_event != null));
    return [...paid, ...sent].reverse();
  }
  // Hội thoại Zalo tìm theo tên: mỗi hội thoại một mục ở ngày tin cuối, ba hội thoại có tin mới nhất.
  function talks() {
    const chats = loaded(side.chats) ? side.chats.data.conversations ?? [] : [];
    return chats.filter(row => row.last_message_at).slice(0, 3).map(row => entry(vnDay(row.last_message_at), 'lienlac',
      `<b>Zalo · tin cuối trong “${escape(row.display_name ?? 'hội thoại chưa rõ tên')}”</b>`, [`${escape(row.message_count)} tin · `
        + `${row.last_own_message_at ? `mình nhắn gần nhất ${dateText(vnDay(row.last_own_message_at))}` : 'mình chưa nhắn'} · `
        + `<a href="${escape(chatHref(row))}">Mở hội thoại</a>`]));
  }
  // Dấu tin Zalo của sổ (ZALO-GROUP-01), ở ngày của tin được đánh dấu; trạng thái do máy chủ tính từ phiếu thu chưa hủy. Dấu đã bỏ
  // gạch kèm lý do như phiếu hủy. "Mở tin" sang trang Chat đúng group, cuộn tới đúng tin.
  function marked() {
    const rows = loaded(side.marks) ? side.marks.data : [];
    return rows.map(row => {
      const cancelled = row.status === 'cancelled';
      const what = row.kind === 'note' ? `${MARK.note}: ${escape(row.note ?? '')}`
        : `${MARK[row.kind]} <span class="ct-money">${full(row.amount_vnd)}</span> · ${row.kind === 'promise' ? 'hẹn' : 'ngày'} ${escape(dateText(row.on_date))}`;
      const state = row.status && !cancelled ? `<span class="ct-mark ${escape(row.status)}">${escape(MARK_STATUS[row.status] ?? row.status)}`
        + `${row.status === 'missed' ? ` · đã trả ${full(row.paid_vnd ?? '0')}` : ''}${row.receipt_pid ? ` · phiếu ${escape(row.receipt_pid)}` : ''}</span>` : '';
      const quote = row.message_excerpt ? `“${escape(row.message_excerpt)}”${row.message_sender ? ` — ${escape(row.message_sender)}` : ''}` : '';
      const open = row.conversation_id && row.message_id
        ? `<a href="/zalo-chat.html?c=${encodeURIComponent(row.conversation_id)}&amp;m=${encodeURIComponent(row.message_id)}">Mở tin</a>` : '';
      const day = row.message_at ? vnDay(Date.parse(row.message_at)) : row.created_on;
      return entry(day, row.kind === 'note' ? 'lienlac' : 'hua', `<b>${what}</b>${state}`,
        [cancelled ? `Đã bỏ dấu · Lý do: ${escape(row.cancel_reason ?? '')}` : '', [quote, open].filter(Boolean).join(' · '),
          `Đánh dấu bởi ${escape(row.created_by ?? '')}`], cancelled);
    });
  }
  // Trang Chat Zalo: sổ đã gắn group thì mở group đó; chưa gắn thì lọc theo tên khách (trang tự mở khi chỉ một hội thoại khớp);
  // có `row` thì mở đúng hội thoại đó.
  function chatHref(row = null) {
    const linked = loaded(side.links) ? side.links.data : [];
    if (!row && linked.length) return `/zalo-chat.html?c=${encodeURIComponent(linked[0].conversation_id)}`;
    const name = loaded(side.chats) ? side.chats.data.name : '';
    return `/zalo-chat.html${name ? `?q=${encodeURIComponent(name)}${row ? `&c=${encodeURIComponent(row.conversation_id)}` : ''}` : ''}`;
  }
  const linkStatus = linked => (linked.length ? `Group Zalo đã gắn: ${linked.length}. Mở chat sẽ mở group đó.` : '');
  const chatStatus = ({ name, conversations }) => (conversations === null ? 'Chưa có dữ liệu chat trên máy chủ.'
    : !conversations.length ? `Không có hội thoại Zalo nào có tên “${escape(name)}”.`
      : conversations.length > 3 ? `Còn ${conversations.length - 3} hội thoại khác có tên “${escape(name)}”: bấm Mở chat để xem.` : '');

  function talk(data) {
    const items = [...talks(), ...marked(), ...money(data)].sort((a, b) => b.date.localeCompare(a.date));
    const count = key => (key === 'all' ? items.length : items.filter(item => item.kind === key).length);
    const chips = FILTERS.map(([key, label]) => `<button type="button" class="ct-chip" data-go="loai:${key}" aria-pressed="${filter === key}">`
      + `${label} <b>${count(key)}</b></button>`).join('');
    const rows = items.filter(item => filter === 'all' || item.kind === filter).map(item => `<li class="ct-item${item.voided ? ' voided' : ''}" `
      + `data-kind="${item.kind}"><time datetime="${escape(item.date)}">${escape(dateText(item.date))}</time><div>${item.html}</div></li>`).join('');
    const status = [source('chats', chatStatus), source('marks', () => ''), source('links', linkStatus)]
      .filter(Boolean).map(line => `<p class="ct-status">${line}</p>`).join('');
    return `<div class="ct-bar"><div class="ct-chips" role="group" aria-label="Lọc theo loại">${chips}</div>`
      + `<a class="ov-go" href="${escape(chatHref())}">Mở chat</a></div>${status}`
      + `<ol class="ov-block ct-list">${rows || '<li class="ct-item"><span></span><div>Chưa có mục nào.</div></li>'}</ol>`
      + '<p class="ov-note">Khoản thu trước khi lên web (sổ gốc) xem ở thẻ Sổ.</p>';
  }

  // Hạn trả (DASH-03 (1)): nợ tháng M đến hạn ngày cuối tháng M + due_after_months; kèm ví dụ bằng tháng hiện tại (giờ VN).
  const dueRule = after => (after === 0 ? 'Cuối chính tháng nợ' : after === 1 ? 'Cuối tháng kế tiếp' : `Cuối tháng thứ ${after} sau tháng nợ`);
  function dueExample(after, key) {
    const end = new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) + after, 0)).toISOString().slice(0, 10);
    return `Công nợ tháng ${monthLabel(key)} đến hạn ${dateText(end)} · quy tắc chung mọi khách`;
  }
  // Giá và phụ phí: đợt giá có Từ ngày ≤ hôm nay ≤ Đến ngày (Đến ngày trống là chưa hết hạn) là giá đang áp — đúng các dòng "Đang dùng"
  // của khung Bảng giá ở thẻ Sổ (so-khach-v7-price-ui.js), cùng thứ tự nơi đi; nơi đi không có giá hôm nay (đợt cũ đã hết hạn hoặc
  // chưa từng có giá) ghi cam ngay ở dòng đó; đợt sắp áp gần nhất ghi "giá mới từ". Số tiền nguyên từ GET, chỉ định dạng (ARCH-03).
  function prices(table, today) {
    const keyOf = text => String(text ?? '').replace(/\s+/g, ' ').trim().toUpperCase();
    const order = new Map((table.locations ?? []).map((item, index) => [keyOf(item.name), index]));
    const places = (period, extra) => {
      const found = new Map();
      for (const rate of period.rates ?? []) {
        if (!found.has(keyOf(rate.location))) found.set(keyOf(rate.location), { key: keyOf(rate.location), place: rate.location, ...extra });
        found.get(keyOf(rate.location))[rate.tier] = rate.unit_price_vnd;
      }
      return [...found.values()].sort((a, b) => (order.get(a.key) ?? 0) - (order.get(b.key) ?? 0));
    };
    const periods = [...table.periods].sort((a, b) => a.valid_from.localeCompare(b.valid_from));
    const rows = [];
    for (const period of periods.filter(item => item.valid_from <= today && (!item.valid_to || item.valid_to >= today))) {
      const when = period.valid_to ? `${dateText(period.valid_from)} – ${dateText(period.valid_to)}` : `từ ${dateText(period.valid_from)}, chưa có ngày hết`;
      rows.push(...places(period, { when, kind: 'now' }));
    }
    // Nơi đi chưa có giá hôm nay: lấy giá của đợt hết hạn gần nhất có nơi đó (ghi ngày hết hạn), không có thì "chưa có giá".
    const expired = periods.filter(item => item.valid_to && item.valid_to < today).reverse();
    const missing = new Map();
    for (const row of [...expired.flatMap(item => places(item, { when: `hết hạn ${dateText(item.valid_to)} · chưa có giá mới`, kind: 'warn' })),
      ...(table.locations ?? []).map(item => ({ key: keyOf(item.name), place: item.name, when: 'chưa có giá', kind: 'warn' }))]) {
      if (!rows.some(now => now.key === row.key) && !missing.has(row.key)) missing.set(row.key, row);
    }
    rows.push(...[...missing.values()].sort((a, b) => (order.get(a.key) ?? 0) - (order.get(b.key) ?? 0)));
    const next = periods.find(item => item.valid_from > today);
    if (next) rows.push(...places(next, { when: `giá mới từ ${dateText(next.valid_from)}`, kind: 'next' }));
    const vnd = value => (value == null ? '–' : toBig(value).toLocaleString('vi-VN'));
    const ships = table.tt_shippers ?? [];
    return (rows.length ? '<table class="hs-prices"><thead><tr><th scope="col">Nơi đi</th><th scope="col" class="num">Giá khách</th>'
      + `<th scope="col" class="num">Giá TT</th><th scope="col">Hiệu lực</th></tr></thead><tbody>${rows.map(row => `<tr class="${row.kind}">`
        + `<td>${escape(row.place)}</td><td class="num">${vnd(row.khach)}</td><td class="num">${vnd(row.tt)}</td><td>${escape(row.when)}</td></tr>`).join('')}`
      + '</tbody></table>' : '<p class="hs-empty">Sổ chưa có bảng giá.</p>')
      + `<p class="hs-hint">Đơn vị: đồng/chuyến. ${escape(ships.length ? `Giá TT áp cho shipper ${ships.join(', ')}; shipper khác lấy giá khách.` : 'Mọi shipper lấy giá khách.')}</p>`;
  }
  // Nút dạng chữ xanh (vùng bấm 40px); `go` như các nút khác của thẻ.
  const action = (go, text, more = '', kind = '') => `<button type="button" class="hs-action${kind ? ` ${kind}` : ''}" data-go="${escape(go)}"`
    + `${more ? ` aria-label="${escape(`${text} — ${more}`)}"` : ''}>${escape(text)}</button>`;
  const later = (key, text = SOON[key]) => action(`chua:${key}`, text, 'chưa lưu được trên web');
  const section = (title, html, tool = '') => `<section class="hs-section"><div class="hs-head"><h3>${title}</h3>${tool}</div>${html}</section>`;
  const term = (label, html) => `<div class="hs-term"><span class="hs-label">${label}</span><div>${html}</div></div>`;
  // Group Zalo đã gắn (ZALO-GROUP-01): chỉ hiện mục khi sổ có group; tên và tin cuối từ gói chat trên máy chủ.
  function groups() {
    const item = side.groups;
    if (item.state === 'error') return section('Nhóm trao đổi', `<p class="hs-empty">${source('groups', () => '')}</p>`);
    if (!loaded(item) || !item.data.length) return '';
    return section('Nhóm trao đổi', item.data.map(row => `<div class="hs-person"><span class="hs-avatar" aria-hidden="true">Z</span>`
      + `<span class="hs-who"><b>${escape(row.display_name ?? 'Group Zalo đã gắn')}</b><span>Zalo · ${row.last_message_at
        ? `tin cuối ${escape(dateText(vnDay(row.last_message_at)))}` : `gắn ngày ${escape(dateText(vnDay(Date.parse(row.linked_at))))}`}</span></span>`
      + `<a class="hs-link" href="/zalo-chat.html?c=${encodeURIComponent(row.conversation_id)}">Mở nhóm</a></div>`).join(''));
  }
  // Chữ viết tắt ở đầu hồ sơ: chữ đầu của hai từ cuối tên sổ ("Công ty Mẫu Bình Minh" → BM).
  const initials = name => String(name).trim().split(/\s+/).slice(-2).map(word => [...word][0] ?? '').join('').toLocaleUpperCase('vi');
  function profile() {
    const today = todayIso(), row = live.customerRow?.(customerId);
    const name = String(row?.name ?? live.customerName(customerId) ?? `#${customerId}`);
    const transport = transportText(row?.transport_mode);
    const facts = row?.commodity ? [row.commodity, transport ? `Đường ${transport}` : ''].filter(Boolean).join(' · ') : commodityText(null);
    const fees = ctx.feeColumnIds.map(id => ctx.feeTypeName(id));
    const after = loaded(side.debt) ? side.debt.data.rule?.due_after_months ?? 1 : null;
    const pay = source('debt', () => `<b>${escape(dueRule(after))}</b><span class="hs-sub">${escape(dueExample(after, today.slice(0, 7)))}</span>`);
    const head = `<header class="hs-id"><span class="hs-initials" aria-hidden="true">${escape(initials(name))}</span><div class="hs-id-text">`
      + `<h2 class="hs-name">${escape(name)}</h2><p class="hs-facts">${escape(facts)}</p></div>${later('sua-ho-so').replace('hs-action', 'hs-action outline')}</header>`;
    const left = section('Thông tin doanh nghiệp', '<p class="hs-empty">Tên pháp lý, mã số thuế, khu vực chưa lưu trên web.</p>')
      + section('Thỏa thuận làm việc', term('Thanh toán', pay)
        + term('Hạn mức công nợ', `<div class="hs-line"><div><b>Chưa đặt hạn mức</b><span class="hs-sub">Chưa đặt nghĩa là chưa giới hạn, không phải 0 đ.</span></div>${later('han-muc')}</div>`)
        + term('Hợp đồng', `<div class="hs-line"><b>Chưa lưu hợp đồng trên web</b>${later('hop-dong')}</div>`))
      + section('Giá và phụ phí áp dụng', source('prices', table => prices(table, today))
        + `<div class="hs-line"><p class="hs-fees">Phụ phí riêng trên sổ: <b>${escape(fees.length ? fees.join(', ') : 'chưa chọn')}</b>`
        + `${fees.length ? '' : ', mọi phụ phí vào cột Khác'}</p>${action('mo:phu-phi', 'Cài đặt phụ phí', 'sang thẻ Sổ, mở khung cài đặt phụ phí')}</div>`,
      action('mo:bang-gia', 'Xem bảng giá ›', 'sang thẻ Sổ, mở khung Bảng giá'));
    const right = section('Người liên hệ', '<p class="hs-empty">Chưa có người liên hệ. Thêm người quyết định để biết gọi ai khi cần.</p>', later('lien-he', '+ Thêm'))
      + groups()
      + section('Ghi chú khi làm việc', '<p class="hs-empty">Chưa có ghi chú.</p>', later('ghi-chu', '+ Thêm ghi chú'))
      + section('Tài liệu', '<p class="hs-empty">Chưa có tài liệu. Nên lưu hợp đồng, phụ lục giá và biên bản đối chiếu nợ đã ký.</p>', later('tai-lieu'));
    const toast = soon ? `<div class="hs-toast" role="status"><span>${escape(soon)}</span>${action('dong', 'Đóng')}</div>` : '';
    return `${head}<div class="hs-cols"><div class="hs-main">${left}</div><aside class="hs-side" aria-label="Liên hệ và tài liệu">${right}</aside></div>${toast}`;
  }

  // Dữ liệu lạ làm thẻ vẽ lỗi thì chỉ thẻ này báo, thẻ Sổ vẫn dùng được. Khách chưa có số dư đầu: một câu như thẻ Tình hình.
  function body(id, data) {
    if (data.status !== 'active') {
      return '<div class="ov-block" role="status"><p>Khách chưa có số dư đầu hiệu lực. Chưa có số để xem.</p>'
        + '<button type="button" class="tab-go" data-the="so">Mở thẻ Sổ</button></div>';
    }
    try { return id === 'trao-doi' ? talk(data) : profile(); }
    catch { return `<div class="ov-block" role="alert"><p>Chưa vẽ được thẻ ${id === 'trao-doi' ? 'Trao đổi' : 'Hồ sơ'}. Số của khách xem ở thẻ Sổ.</p></div>`; }
  }
  // Khung thẻ Trao đổi hoặc Hồ sơ, vẽ cùng lần với cả sổ (so-khach-v7-tabs-ui.js đặt sau thẻ Sổ).
  function contactPane(id) {
    if (shown() === id && ctx.snapshot?.status === 'active') wake();
    return `<section class="tab-pane ct" id="the-${id}" role="tabpanel" aria-labelledby="tab-${id}">${content(id)}</section>`;
  }
  // Vừa mở thẻ Trao đổi hoặc Hồ sơ: đọc nguồn phụ nếu cần, dựng khung (hiện "Đang đọc…" tới khi nguồn về).
  function contactShown(id) {
    if (!NEEDS[id]) return;
    if (ctx.snapshot?.status === 'active') wake();
    paint();
  }

  root.addEventListener('click', event => {
    // Nút 📎: sang thẻ Sổ trước, rồi so-khach-v7-images-ui.js (nghe ở document, sau #app) mở khung xem ảnh ở thẻ Sổ.
    if (event.target.closest?.('.ct .image-clip')) { showTab('so'); return; }
    const target = event.target.closest?.('.ct [data-go]');
    if (!target) return;
    const [what, value] = target.dataset.go.split(':');
    if (what === 'retry') { wake(value); paint(); }
    else if (what === 'loai') { filter = value; paint(); }
    else if (what === 'mo') { soon = ''; showTab('so'); root.querySelector(OPEN[value])?.click(); }
    else if (what === 'chua') { soon = `${SOON[value]}: chưa lưu được trên web — cần thêm chức năng (giai đoạn B).`; paint(); }
    else if (what === 'dong') { soon = ''; paint(); }
  });

  Object.assign(ctx, { contactPane, contactShown });
};
