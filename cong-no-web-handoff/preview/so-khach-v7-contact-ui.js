/* Sổ khách V7 bản live — thẻ Trao đổi và thẻ Hồ sơ của trang khách (TRANG-KHACH-01, specs/v7-trang-khach.md, PR A3), phần A:
 *   Trao đổi: dòng thời gian của sổ, mới nhất ở trên — phiếu thu và cấn trừ (tháng trừ nợ theo dòng phân bổ còn hiệu lực, phiếu
 *     hủy gạch kèm lý do), lần nhắc gần nhất, hội thoại Zalo tìm theo tên như nút Chat ở Đòi nợ, dấu tin Zalo (ZALO-GROUP-01: hứa
 *     trả, khách báo đã chuyển, ghi chú); lọc Tất cả · Hứa trả · Nhắc và Zalo · Thu tiền (Debit note là giai đoạn B); Copy tin nhắc
 *     (cùng tin, cùng lệnh ghi reminder_log với Đòi nợ) và Mở chat (group đã gắn trước, tìm theo tên sau).
 *   Hồ sơ: mặt hàng · cảng/bộ, hạn trả (quy tắc chung DASH-03), giá đang áp hôm nay (giờ VN) theo bảng giá của sổ, cột phụ phí
 *     riêng, phiếu có ảnh chứng từ.
 * Hai thẻ không ghi tiền (Copy tin nhắc chỉ ghi "đã nhắc", ngoài đường tiền); số tiền lấy nguyên từ GET, chỉ định dạng (ARCH-03).
 * Lần nhắc, chat, Tổng quan và bảng giá chỉ đọc khi thẻ cần chúng đang mở, đọc lại khi sổ đổi phiên bản hoặc lần đọc đã quá 60
 * giây (như thẻ Tình hình); nguồn nào lỗi thì chỉ khối đó báo lỗi kèm Thử lại. Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).contact = ctx => {
  'use strict';
  const { root, api, live, customerId, escape, dateText, monthKey, monthLabel, showTab, todayIso } = ctx;
  const { full, commodityText, vnDay, loadError, reminderText } = CongNoFormat;
  const SOURCE = { 'copy-button': 'bấm Copy tin nhắc', zalo: 'Zalo', manual: 'ghi tay' };
  const FILTERS = [['all', 'Tất cả'], ['hua', 'Hứa trả'], ['lienlac', 'Nhắc và Zalo'], ['thu', 'Thu tiền']];
  // ZALO-GROUP-01: dấu tin Zalo — hứa trả và khách báo đã chuyển vào lọc "Hứa trả", ghi chú vào "Nhắc và Zalo".
  const MARK = { promise: 'Hứa trả', paid_claim: 'Khách báo đã chuyển', note: 'Ghi chú' };
  const MARK_STATUS = { pending: 'đang chờ', kept: 'giữ lời', missed: 'lỡ hẹn', waiting: 'chờ đối chiếu',
    received: 'đã có phiếu thu', not_seen: 'chưa thấy phiếu thu' };
  // Nút ở thẻ Sổ mà thẻ Hồ sơ mở tới: bảng giá và cột phụ phí sửa ở thẻ Sổ (SO-GON-04 L7).
  const OPEN = { 'bang-gia': '.price-table-open', 'phu-phi': '.fee-settings-open' };
  // Nguồn phụ đọc qua so-khach-v7-api.js và thẻ cần chúng; `what` là chữ trong câu đang đọc, câu lỗi.
  const side = { reminders: { read: 'readReminders', what: 'lần nhắc nợ' }, chats: { read: 'findChats', what: 'hội thoại Zalo' },
    marks: { read: 'readMarks', what: 'dấu tin Zalo' }, links: { read: 'readZaloLinks', what: 'group Zalo đã gắn' },
    debt: { read: 'readDebt', what: 'hạn trả' }, prices: { read: 'readPrices', what: 'bảng giá' } };
  const NEEDS = { 'trao-doi': ['reminders', 'chats', 'marks', 'links'], 'ho-so': ['debt', 'prices'] };
  for (const item of Object.values(side)) item.state = 'idle';
  let filter = 'all', note = '', copying = false;
  const shown = () => document.body?.dataset.the;
  const loaded = item => item.state !== 'error' && Object.hasOwn(item, 'data');
  // Nhãn đọc màn hình bắt đầu bằng chữ trên nút (WCAG 2.5.3), `more` nói thêm nút làm gì.
  const button = (go, text, more = '') => `<button type="button" class="ov-go" data-go="${escape(go)}"`
    + `${more ? ` aria-label="${escape(`${text} — ${more}`)}"` : ''}>${escape(text)}</button>`;
  const block = (title, html) => `<section class="ov-block"><h2>${title}</h2>${html}</section>`;
  const say = (text, bad = false) => `<p class="ct-note${bad ? ' bad' : ''}" role="${bad ? 'alert' : 'status'}">${escape(text)}</p>`;
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
        : share((row.allocations ?? []).filter(line => line.superseded_by_event == null)), row.reference ? `Tham chiếu: ${escape(row.reference)}` : ''], voided);
    });
    const sent = (data.outgoing_offsets ?? []).map(row => entry(row.date, 'thu', `<b>Cấn trừ sang ${other(row)} ${amount(row, row.voided_by_event != null)}</b>`,
      [row.voided_by_event != null ? killed(row) : ''], row.voided_by_event != null));
    return [...paid, ...sent].reverse();
  }
  // Lần nhắc gần nhất (reminder_log; từng lần nhắc có ghi chú là giai đoạn B4) và hội thoại Zalo tìm theo tên: mỗi hội thoại một mục
  // ở ngày tin cuối, ba hội thoại có tin mới nhất.
  function talks() {
    const last = loaded(side.reminders) ? side.reminders.data : null;
    const chats = loaded(side.chats) ? side.chats.data.conversations ?? [] : [];
    return [...(last ? [entry(last.last_reminded, 'lienlac', `<b>Nhắc nợ · ${escape(SOURCE[last.last_source] ?? last.last_source)}</b>`,
      [`Lần nhắc gần nhất · đã nhắc ${escape(last.reminder_count)} lần`])] : []),
    ...chats.filter(row => row.last_message_at).slice(0, 3).map(row => entry(vnDay(row.last_message_at), 'lienlac',
      `<b>Zalo · tin cuối trong “${escape(row.display_name ?? 'hội thoại chưa rõ tên')}”</b>`, [`${escape(row.message_count)} tin · `
        + `${row.last_own_message_at ? `mình nhắn gần nhất ${dateText(vnDay(row.last_own_message_at))}` : 'mình chưa nhắn'} · `
        + `<a href="${escape(chatHref(row))}">Mở hội thoại</a>`]))];
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
    const status = [source('reminders', () => ''), source('chats', chatStatus), source('marks', () => ''), source('links', linkStatus)]
      .filter(Boolean).map(line => `<p class="ct-status">${line}</p>`).join('');
    return `<div class="ct-bar"><div class="ct-chips" role="group" aria-label="Lọc theo loại">${chips}</div>`
      + `${button('copy', copying ? 'Đang soạn tin…' : 'Copy tin nhắc', 'chép tin nhắc nợ để dán vào Zalo và ghi “đã nhắc” hôm nay')}`
      + `<a class="ov-go" href="${escape(chatHref())}">Mở chat</a></div>${note}${status}`
      + `<ol class="ov-block ct-list">${rows || '<li class="ct-item"><span></span><div>Chưa có mục nào.</div></li>'}</ol>`
      + '<p class="ov-note">Khoản thu trước khi lên web (sổ gốc) xem ở thẻ Sổ.</p>';
  }

  // Copy tin nhắc như Đòi nợ: tin soạn từ dòng của khách ở Tổng quan, đọc ngay lúc bấm để số gửi khách là số mới nhất; chép vào bộ
  // nhớ tạm rồi ghi "đã nhắc" (POST /api/v7/reminders, source copy-button) và đọc lại lần nhắc để dòng thời gian theo số server.
  async function remindNote() {
    const { row } = await api.readDebt();
    if (!row) return say('Khách không còn nợ nên không có tin nhắc.');
    const text = reminderText(live.sheetName(customerId) || 'quý khách', row);
    const copied = await Promise.resolve().then(() => navigator.clipboard.writeText(text)).then(() => true, () => false);
    try { await api.remind(); } catch {
      return say(`${copied ? 'Đã copy tin nhưng chưa' : 'Chưa copy và chưa'} ghi được “đã nhắc”. Bấm Copy tin nhắc lần nữa.`, true);
    }
    wake('reminders');
    return copied ? say('Đã copy tin nhắc và ghi “đã nhắc” hôm nay. Dán vào Zalo của khách.')
      : `${say('Đã ghi “đã nhắc” hôm nay nhưng chưa copy được: chọn tin dưới đây rồi copy tay.')}`
        + `<textarea class="ct-text" readonly rows="7" aria-label="Tin nhắc nợ">${escape(text)}</textarea>`;
  }
  async function copy() {
    if (copying) return;
    copying = true;
    note = '';
    paint();
    note = await remindNote().catch(() => say(loadError('số nợ để soạn tin nhắc'), true));
    copying = false;
    paint();
  }

  // Hạn trả (DASH-03 (1)): nợ tháng M đến hạn ngày cuối tháng M + due_after_months; kèm ví dụ bằng tháng hiện tại (giờ VN).
  const dueRule = after => (after === 0 ? 'Cuối chính tháng nợ' : after === 1 ? 'Cuối tháng sau tháng nợ' : `Cuối tháng thứ ${after} sau tháng nợ`);
  function dueExample(after, key) {
    const end = new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) + after, 0)).toISOString().slice(0, 10);
    return `Quy tắc chung của mọi sổ, như Tổng quan · ví dụ nợ tháng ${monthLabel(key)} hạn ${dateText(end)}`;
  }
  // Giá đang áp hôm nay: đợt giá có Từ ngày ≤ hôm nay ≤ Đến ngày (Đến ngày trống là chưa hết hạn), mỗi nơi đi của đợt một dòng — đúng
  // các dòng "Đang dùng" của khung Bảng giá ở thẻ Sổ (so-khach-v7-price-ui.js), cùng thứ tự.
  function prices(table, today) {
    if (!table.periods.length) return '<p>Sổ chưa có bảng giá.</p>';
    const keyOf = text => String(text ?? '').replace(/\s+/g, ' ').trim().toUpperCase();
    const order = new Map((table.locations ?? []).map((item, index) => [keyOf(item.name), index]));
    const rows = [];
    for (const period of table.periods.filter(item => item.valid_from <= today && (!item.valid_to || item.valid_to >= today))
      .sort((a, b) => a.valid_from.localeCompare(b.valid_from))) {
      const places = new Map();
      for (const rate of period.rates ?? []) {
        if (!places.has(keyOf(rate.location))) places.set(keyOf(rate.location), { place: rate.location, from: period.valid_from, to: period.valid_to });
        places.get(keyOf(rate.location))[rate.tier] = rate.unit_price_vnd;
      }
      rows.push(...[...places].sort(([a], [b]) => (order.get(a) ?? 0) - (order.get(b) ?? 0)).map(([, row]) => row));
    }
    const price = value => (value == null ? '–' : full(value));
    const next = table.periods.map(item => item.valid_from).filter(from => from > today).sort()[0];
    const ships = table.tt_shippers ?? [];
    const notes = [ships.length ? `Shipper áp giá TT: ${ships.join(', ')}; shipper khác lấy giá khách.` : 'Mọi shipper lấy giá khách.',
      next ? `Có giá mới từ ${dateText(next)}.` : ''].filter(Boolean).join(' ');
    return (rows.length ? '<table class="ct-prices"><thead><tr><th scope="col">Nơi đi</th><th scope="col" class="num">Giá khách</th>'
      + `<th scope="col" class="num">Giá TT</th><th scope="col">Hiệu lực</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escape(row.place)}</td>`
        + `<td class="num">${price(row.khach)}</td><td class="num">${price(row.tt)}</td>`
        + `<td>từ ${escape(dateText(row.from))}${row.to ? ` đến ${escape(dateText(row.to))}` : ''}</td></tr>`).join('')}</tbody></table>`
      : '<p>Không có giá nào áp cho hôm nay.</p>') + `<p class="ov-note">${escape(notes)}</p>`;
  }
  function profile(data) {
    const today = todayIso(), row = live.customerRow?.(customerId);
    const line = (label, value) => `<div class="ct-row"><span>${label}</span><span>${value}</span></div>`;
    const fees = ctx.feeColumnIds.map(id => escape(ctx.feeTypeName(id)));
    const images = (data.receipts ?? []).filter(receipt => (ctx.imageCount?.(receipt.pid) ?? 0) > 0).reverse();
    const after = loaded(side.debt) ? side.debt.data.rule?.due_after_months ?? 1 : null;
    return `<div class="ct-grid">${block('Mặt hàng và hạn trả', line('Mặt hàng · vận chuyển', row ? escape(commodityText(row.commodity, row.transport_mode)) : '–')
      + line('Hạn trả', source('debt', () => escape(dueRule(after))))
      + (after === null ? '' : `<p class="ov-note">${escape(dueExample(after, today.slice(0, 7)))}</p>`))}`
      + block(`Giá đang áp hôm nay ${dateText(today)}`, source('prices', table => prices(table, today))
        + button('mo:bang-gia', 'Mở Bảng giá', 'sang thẻ Sổ, mở khung Bảng giá'))
      + block('Cột phụ phí riêng của sổ', `<p>${fees.length ? `${fees.join(' · ')}. Phụ phí loại khác vào cột Khác.`
        : 'Chưa chọn cột riêng: mọi phụ phí vào cột Khác.'}</p>${button('mo:phu-phi', 'Cài đặt phụ phí', 'sang thẻ Sổ, mở khung cài đặt phụ phí')}`)
      + block('Ảnh chứng từ', images.length ? images.map(receipt => line(`Phiếu ${escape(dateText(receipt.date))} · ${full(receipt.amount_vnd)}`
        + `${receipt.voided_by_event != null ? ' (đã hủy)' : ''}`, clip(receipt))).join('') : '<p>Chưa phiếu nào có ảnh chứng từ.</p>') + '</div>';
  }

  // Dữ liệu lạ làm thẻ vẽ lỗi thì chỉ thẻ này báo, thẻ Sổ vẫn dùng được. Khách chưa có số dư đầu: một câu như thẻ Tình hình.
  function body(id, data) {
    if (data.status !== 'active') {
      return '<div class="ov-block" role="status"><p>Khách chưa có số dư đầu hiệu lực. Chưa có số để xem.</p>'
        + '<button type="button" class="tab-go" data-the="so">Mở thẻ Sổ</button></div>';
    }
    try { return id === 'trao-doi' ? talk(data) : profile(data); }
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
    else if (what === 'copy') copy();
    else if (what === 'mo') { showTab('so'); root.querySelector(OPEN[value])?.click(); }
  });

  Object.assign(ctx, { contactPane, contactShown });
};
