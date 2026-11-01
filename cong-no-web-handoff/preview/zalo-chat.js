(() => {
  'use strict';
  // ZALO-CHAT-01: tab Chat Zalo — xem lại hội thoại với khách từ bản xuất (chỉ đọc).
  // Trang chỉ nhận từng trang tin từ /api/v7/zalo/messages (tối đa 100 tin một lượt), không bao giờ
  // tải cả bản xuất; không ghi nội dung tin ra console hay nơi nào khác.
  const $ = id => document.getElementById(id);
  // Thoát HTML và so khớp không phân biệt hoa thường/dấu tiếng Việt (foldText: cùng quy tắc với máy chủ) từ CongNoFormat.
  const { esc, foldText, loadError, full, dateText, vnDay } = CongNoFormat;
  const TZ = 'Asia/Ho_Chi_Minh';
  const PAGE_LIMIT = 50;
  // page: trang cũ nhất đã tải; newest: trang mới nhất đã tải (khác 0 khi mở thẳng một tin bằng ?m=).
  const state = {
    conversations: [], filter: '', selected: null, messages: [], total: 0, page: 0, newest: 0, hasOlder: false,
    query: '', request: 0, loading: false, focus: null,
  };
  const MEDIA = '/api/v7/zalo/media/';
  const chat = $('chat');

  const dayKey = ms => new Date(ms).toLocaleDateString('vi-VN', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric' });
  const timeText = ms => (ms ? new Date(ms).toLocaleTimeString('vi-VN', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }) : '');
  const shortId = id => (id ? String(id).slice(0, 8) : '');
  const nameOf = row => row.display_name || `Chưa rõ tên · ${shortId(row.conversation_id)}`;
  const updatedText = iso => {
    const ms = Date.parse(iso ?? '');
    return Number.isNaN(ms) ? 'không rõ' : `${timeText(ms)} ${dayKey(ms)}`;
  };
  const number = value => Number(value ?? 0).toLocaleString('vi-VN');
  // Kích thước tệp (không phải tiền): số nguyên phần mười MB để khỏi dùng số thực.
  const sizeText = bytes => {
    if (bytes >= 1048576) { const tenths = Math.round((bytes * 10) / 1048576); return `${Math.floor(tenths / 10)},${tenths % 10} MB`; }
    return bytes >= 1024 ? `${Math.round(bytes / 1024)} KB` : `${bytes} byte`;
  };

  async function json(url) {
    const response = await fetch(url, { cache: 'no-store' });
    let body;
    try { body = await response.json(); } catch { body = null; }
    if (!response.ok) {
      const error = Error(body?.message || `HTTP ${response.status}`);
      error.status = response.status;
      error.code = body?.error;
      throw error;
    }
    return body;
  }

  function showError(error) {
    const box = $('error');
    box.hidden = false;
    if (error?.status === 503 && error.code === 'ZALO_EXPORT_UNAVAILABLE') {
      box.innerHTML = `Máy chủ này chưa có bản xuất chat Zalo nên chưa xem được. ${esc(error.message)}<br>` +
        'Cách bật: chép thư mục bản xuất (conversations.json, messages.jsonl) lên máy chạy web, đặt biến <code>WEBDEBIT_ZALO_EXPORT_DIR</code> rồi khởi động lại dịch vụ.';
    } else if (error?.status === 403) {
      box.textContent = 'Bạn không có quyền xem chat trên máy chủ này.';
    } else {
      // Audit UX 31/10/2026 (P1-6): một câu tiếng Việt và nút Thử lại; không hiện chữ của trình duyệt hay mã HTTP.
      box.innerHTML = `${esc(loadError('dữ liệu chat'))} <button type="button" class="btn" data-retry>Thử lại</button>`;
    }
  }

  function setUrl() {
    const params = new URLSearchParams();
    if (state.filter) params.set('q', state.filter);
    if (state.selected) params.set('c', state.selected);
    const next = params.toString() ? `?${params}` : location.pathname;
    try { history.replaceState(null, '', next); } catch { /* trang mở từ file:// thì bỏ qua */ }
  }

  function filtered() {
    const needle = foldText(state.filter.trim());
    if (!needle) return state.conversations;
    return state.conversations.filter(row => foldText(row.display_name).includes(needle) || row.conversation_id.startsWith(needle));
  }

  function paintList() {
    const rows = filtered();
    $('conversation-count').textContent = state.filter.trim() ? `${rows.length} / ${state.conversations.length}` : `${state.conversations.length} hội thoại`;
    $('conversations').innerHTML = rows.length ? rows.map(row => {
      const own = row.last_own_message_at ? `Mình nhắn gần nhất <b>${esc(dayKey(row.last_own_message_at))}</b>` : 'Mình chưa nhắn';
      return `<button type="button" class="conv" role="listitem" data-id="${esc(row.conversation_id)}" aria-current="${row.conversation_id === state.selected}" title="${esc(row.conversation_id)}">
        <span class="nm${row.display_name ? '' : ' unnamed'}">${esc(nameOf(row))}</span>
        <span class="last">${esc(row.last_message_at ? dayKey(row.last_message_at) : '—')}</span>
        <span class="sub">${number(row.message_count)} tin · ${own}</span>
        ${(links.byConversation.get(row.conversation_id) ?? []).length ? `<span class="sub books">Sổ: ${esc(links.byConversation.get(row.conversation_id).map(book => book.customer_name).join(', '))}</span>` : ''}
      </button>`;
    }).join('') : '<p class="empty">Không có hội thoại khớp.</p>';
  }

  function highlight(text) {
    const safe = esc(text);
    const needle = state.query.trim();
    if (!needle) return safe;
    const folded = foldText(text);
    const target = foldText(needle);
    // Chỉ tô khi độ dài không đổi sau khi bỏ dấu (gần như luôn đúng với tiếng Việt), tránh lệch vị trí.
    if (folded.length !== text.length) return safe;
    let out = '';
    let from = 0;
    for (let at = folded.indexOf(target, from); at >= 0; at = folded.indexOf(target, from)) {
      out += esc(text.slice(from, at)) + `<mark>${esc(text.slice(at, at + needle.length))}</mark>`;
      from = at + needle.length;
    }
    return out + esc(text.slice(from));
  }

  function attachmentText(att) {
    if (!att) return '';
    if (att.state !== 'matched') {
      const urls = att.url_count ? ` (${att.url_count} liên kết đã băm)` : '';
      return `<div class="att unmatched">Đính kèm chưa khớp metadata${att.title ? `: ${esc(att.title)}` : ''}${urls}</div>`;
    }
    const items = att.media_items.map(item => [
      item.source_table === 'image' ? 'Ảnh' : item.source_table === 'file' ? 'Tệp' : item.source_table === 'link' ? 'Liên kết' : 'Media',
      item.title, item.ext_type ? `.${item.ext_type}` : null,
      item.file_size != null ? sizeText(item.file_size) : null,
      item.width && item.height ? `${item.width}×${item.height}` : null,
    ].filter(Boolean).join(' · '));
    return `<div class="att matched">${items.map(esc).join('<br>')}</div>`;
  }

  function senderText(message) {
    if (message.is_own) return 'Mình';
    if (message.sender_name) return message.sender_name;
    const row = state.conversations.find(item => item.conversation_id === state.selected);
    if (row && row.display_name && row.participant_count <= 2 && !row.is_group) return row.display_name;
    return `Thành viên ${shortId(message.sender_id)}`;
  }

  // Ảnh/video của gói web (ZALO-GROUP-01): tải theo từng tin từ máy chủ, không bao giờ từ CDN của Zalo.
  function mediaHtml(message) {
    const items = message.media ?? [];
    if (!items.length) {
      return [2, 7].includes(message.message_type) && !message.deleted && !message.attachment
        ? '<div class="pic-gone">Ảnh không còn trên Zalo</div>' : '';
    }
    return `<div class="pics">${items.map(item => {
      const src = MEDIA + encodeURIComponent(item.id);
      if (item.mime === 'video/mp4') return `<video class="vid" controls preload="none" src="${esc(src)}"></video>`;
      // Đặt sẵn khung đúng tỉ lệ (tối đa 280×320) trước khi ảnh tải, để khung tin không nhảy khi ảnh hiện dần.
      const scale = item.width > 0 && item.height > 0 ? Math.min(280 / item.width, 320 / item.height, 1) : 0;
      const size = scale ? ` style="width:${Math.round(item.width * scale)}px;height:${Math.round(item.height * scale)}px"` : '';
      return `<button type="button" class="pic" data-pic="${esc(src)}" aria-label="Xem ảnh lớn"><img src="${esc(src)}"${size} loading="lazy" alt="Ảnh trong tin"></button>`;
    }).join('')}</div>`;
  }

  function bodyHtml(message) {
    if (message.deleted) return '<div class="body card">Tin đã bị thu hồi.</div>';
    if (message.body_kind === 'missing') {
      return `<div class="body missing">Không đọc được nội dung tin này${message.body_state ? ` (${esc(message.body_state)})` : ''}.</div>`;
    }
    if (message.body_text) return `<div class="body${message.body_kind === 'card' ? ' card' : ''}">${highlight(message.body_text)}</div>`;
    // Ảnh không chữ thì chỉ hiện ảnh; loại khác không có chữ thì ghi tên loại (Sticker, Ghi âm…).
    return (message.media ?? []).length || [2, 7].includes(message.message_type) ? '' : `<div class="body card">[${esc(message.type_label)}]</div>`;
  }

  // Tin liền nhau cùng người gửi gộp thành một cụm như Zalo: tên ở tin đầu cụm, giờ ở mỗi tin.
  function renderMessage(message, first) {
    const who = first ? `<span class="who">${esc(senderText(message))}</span>` : '';
    const action = links.ok && !message.deleted
      ? `<button type="button" class="mark-btn" data-mark="${esc(message.message_id)}" aria-label="Đánh dấu tin lúc ${esc(timeText(message.timestamp_ms))}">Đánh dấu</button>` : '';
    return `<article class="msg ${message.is_own ? 'own' : 'other'}${first ? ' first' : ''}${message.message_id === state.focus ? ' focus' : ''}" data-id="${esc(message.message_id)}">
      <div class="meta">${who}<time>${esc(timeText(message.timestamp_ms))}</time>${action}</div>
      ${bodyHtml(message)}${mediaHtml(message)}${attachmentText(message.attachment)}${marksHtml(message.message_id)}
    </article>`;
  }

  // ZALO-GROUP-01: gắn group ↔ sổ và dấu tin (hứa trả, khách báo đã chuyển, ghi chú). Dấu là ghi chú ngoài đường tiền: không
  // cộng vào số dư; số tiền gửi dạng chuỗi số nguyên như mọi lệnh tiền; trạng thái do máy chủ tính từ phiếu thu.
  const links = { ok: false, byConversation: new Map() };   // ok = false: máy chủ không nối sổ (bản chạy thử) thì ẩn nút
  const marks = new Map();                                    // mã tin → các dấu của group đang mở
  let customers = null;
  const KIND = { promise: 'Hứa trả', paid_claim: 'Khách báo đã chuyển', note: 'Ghi chú' };
  const STATUS = { pending: 'đang chờ', kept: 'giữ lời', missed: 'lỡ hẹn', waiting: 'chờ đối chiếu',
    received: 'đã có phiếu thu', not_seen: 'chưa thấy phiếu thu', cancelled: 'đã bỏ' };
  const today = () => vnDay(Date.now());
  const linkedBooks = () => links.byConversation.get(state.selected) ?? [];

  async function post(url, body) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let data;
    try { data = await response.json(); } catch { data = null; }
    if (!response.ok) {
      const error = Error(data?.message || '');
      error.status = response.status;
      throw error;
    }
    return data;
  }
  // Câu lỗi khi ghi: máy chủ trả câu tiếng Việt thì hiện câu đó; mất mạng thì câu chung, bấm lại dùng cùng mã yêu cầu.
  const saveError = (error, what) => (error.status && error.message ? error.message : `Không ${what} được. Kiểm tra mạng rồi bấm lại.`);

  async function loadLinks() {
    try {
      const data = await json('/api/v7/zalo/links');
      links.byConversation = new Map();
      for (const row of data.links ?? []) {
        if (!links.byConversation.has(row.conversation_id)) links.byConversation.set(row.conversation_id, []);
        links.byConversation.get(row.conversation_id).push(row);
      }
      links.ok = true;
    } catch { links.ok = false; }
  }
  async function loadMarks(id) {
    marks.clear();
    if (!links.ok) return;
    try {
      const data = await json(`/api/v7/marks?conversation=${encodeURIComponent(id)}`);
      if (id !== state.selected) return;
      for (const row of data.marks ?? []) {
        if (!row.message_id) continue;
        if (!marks.has(row.message_id)) marks.set(row.message_id, []);
        marks.get(row.message_id).push(row);
      }
    } catch { /* nhãn dấu là phần phụ: đọc lỗi thì tin vẫn hiện, lần mở sau đọc lại */ }
  }
  function markText(row) {
    const book = linkedBooks().length > 1 || !linkedBooks().some(item => item.customer_id === row.customer_id)
      ? ` · sổ ${esc(row.customer_name ?? row.customer_id)}` : '';
    const status = row.status ? ` · ${STATUS[row.status] ?? esc(row.status)}${row.status === 'missed' ? ` (đã trả ${full(row.paid_vnd ?? '0')})` : ''}` : '';
    const money = row.kind === 'note' ? `: ${esc(row.note ?? '')}`
      : ` ${full(row.amount_vnd)} · ${row.kind === 'promise' ? 'hẹn' : 'ngày'} ${esc(dateText(row.on_date))}`;
    return `${KIND[row.kind] ?? esc(row.kind)}${money}${status}${book}`;
  }
  function marksHtml(id) {
    const rows = marks.get(id) ?? [];
    return rows.length ? `<ul class="marks">${rows.map(row => `<li class="mark ${esc(row.kind)} ${esc(row.status ?? '')}">`
      + `<span>${row.status === 'cancelled' ? `<s>${markText(row)}</s> · lý do: ${esc(row.cancel_reason ?? '')}` : markText(row)}</span>`
      + (row.status === 'cancelled' ? '' : `<button type="button" class="link-btn" data-unmark="${esc(row.id)}">Bỏ dấu</button>`)
      + '</li>').join('')}</ul>` : '';
  }
  function paintLinks() {
    const box = $('links');
    box.hidden = !links.ok || !state.selected;
    if (box.hidden) return;
    const chips = linkedBooks().map(row => `<span class="chip"><a href="/so-khach-v7-live.html?customer=${encodeURIComponent(row.customer_id)}&the=trao-doi">`
      + `${esc(row.customer_name)}</a><button type="button" class="chip-x" data-unlink="${esc(row.customer_id)}" aria-label="Bỏ gắn sổ ${esc(row.customer_name)}">×</button></span>`);
    box.innerHTML = `${chips.length ? `Sổ: ${chips.join('')}` : '<span class="hint">Chưa gắn sổ.</span>'}`
      + `<button type="button" class="link-btn" data-open-link>${chips.length ? 'Gắn thêm sổ' : 'Gắn sổ'}</button>`;
  }
  // Vẽ lại khung tin mà giữ nguyên chỗ đang đọc (sau khi ghi dấu, gắn sổ).
  function repaintKeep() {
    const box = $('messages');
    const top = box.scrollTop;
    paintMessages();
    box.scrollTop = top;
  }

  // Hộp Đánh dấu: một mã yêu cầu cho mỗi lần mở, bấm Lưu lặp (mất mạng rồi bấm lại) không tạo hai dấu.
  const markDialog = $('mark-dialog');
  let marking = null;
  const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
  function messageExcerpt(message) {
    const text = message.body_text || (message.media?.length ? '[Ảnh]' : `[${message.type_label}]`);
    return text.length > 300 ? `${text.slice(0, 299)}…` : text;
  }
  function fillBooks() {
    const books = linkedBooks();
    const select = $('mark-book');
    const keep = select.value;
    select.innerHTML = books.length > 1 ? `<option value="">Chọn sổ…</option>${books.map(row => `<option value="${esc(row.customer_id)}">${esc(row.customer_name)}</option>`).join('')}`
      : books.map(row => `<option value="${esc(row.customer_id)}">${esc(row.customer_name)}</option>`).join('');
    if (books.some(row => String(row.customer_id) === keep)) select.value = keep;
    $('mark-book-field').hidden = !books.length;
    $('mark-no-book').hidden = books.length > 0;
  }
  function syncKind() {
    const kind = new FormData($('mark-form')).get('kind');
    $('mark-amount-field').hidden = $('mark-date-field').hidden = kind === 'note';
    $('mark-date-label').textContent = kind === 'promise' ? 'Hẹn ngày trả' : 'Ngày khách nói đã chuyển';
    const date = $('mark-date');
    if (kind === 'promise') { date.min = today(); date.removeAttribute('max'); if (date.value && date.value < today()) date.value = ''; }
    if (kind === 'paid_claim') {
      date.max = today(); date.removeAttribute('min');
      if (!date.value || date.value > today()) date.value = marking?.message.timestamp_ms ? vnDay(marking.message.timestamp_ms) : today();
    }
  }
  function openMark(id) {
    const message = state.messages.find(item => item.message_id === id);
    if (!message) return;
    marking = { message, key: newKey() };
    $('mark-form').reset();
    $('mark-quote').innerHTML = `<b>${esc(senderText(message))}</b> · ${esc(timeText(message.timestamp_ms))} ${esc(dayKey(message.timestamp_ms))}<br>${esc(messageExcerpt(message))}`;
    $('mark-error').hidden = true;
    $('mark-save').disabled = false;
    $('mark-save').textContent = 'Lưu dấu';
    fillBooks();
    syncKind();
    markDialog.showModal();
  }
  function markBody() {
    const form = new FormData($('mark-form'));
    const kind = form.get('kind');
    const book = Number(form.get('book'));
    const note = String(form.get('note') ?? '').trim();
    if (!linkedBooks().length) return 'Gắn group với sổ trước rồi mới đánh dấu.';
    if (!book) return 'Chọn sổ của dấu này.';
    const body = { customer_id: book, kind, idempotency_key: marking.key, conversation_id: state.selected,
      message_id: marking.message.message_id, message_at: new Date(marking.message.timestamp_ms).toISOString(),
      message_sender: senderText(marking.message).slice(0, 200), message_excerpt: messageExcerpt(marking.message) };
    if (note) body.note = note;
    if (kind === 'note') return note ? body : 'Ghi chú không được trống.';
    // Số tiền gõ có dấu chấm ngăn nghìn (50.000.000) hay chữ "đ" đều nhận; còn lại phải là số nguyên dương.
    const amount = String(form.get('amount') ?? '').replace(/[.\s,]|đ$/giu, '');
    if (!/^[1-9][0-9]{0,17}$/.test(amount)) return 'Số tiền phải là số nguyên dương, ví dụ 50.000.000.';
    const day = String(form.get('on_date') ?? '');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return kind === 'promise' ? 'Chọn ngày khách hẹn trả.' : 'Chọn ngày khách nói đã chuyển.';
    if (kind === 'promise' && day < today()) return 'Ngày hẹn trả phải từ hôm nay trở đi.';
    if (kind === 'paid_claim' && day > today()) return 'Ngày khách nói đã chuyển không được sau hôm nay.';
    return { ...body, amount_vnd: amount, on_date: day };
  }
  async function saveMark(event) {
    event.preventDefault();
    const body = markBody();
    const errorBox = $('mark-error');
    if (typeof body === 'string') { errorBox.textContent = body; errorBox.hidden = false; return; }
    const button = $('mark-save');
    if (button.disabled) return;
    button.disabled = true;
    button.textContent = 'Đang lưu…';
    errorBox.hidden = true;
    try {
      await post('/api/v7/marks', body);
      markDialog.close();
      await loadMarks(state.selected);
      repaintKeep();
      $('subtitle').textContent = `Đã lưu dấu ${KIND[body.kind].toLowerCase()}.`;
    } catch (error) {
      errorBox.textContent = saveError(error, 'lưu dấu');
      errorBox.hidden = false;
      button.disabled = false;
      button.textContent = 'Lưu dấu';
    }
  }

  // Gắn group với sổ: tìm sổ theo tên (không dấu), bấm một dòng là gắn.
  const linkDialog = $('link-dialog');
  async function openLink() {
    $('link-error').hidden = true;
    $('link-search').value = '';
    $('link-options').innerHTML = '<p class="hint">Đang tải danh sách sổ…</p>';
    linkDialog.showModal();
    if (!customers) {
      try { customers = (await json('/api/v7/customers')).customers ?? []; } catch {
        $('link-options').innerHTML = `<p class="form-error">${esc(loadError('danh sách sổ'))}</p>`;
        return;
      }
    }
    paintOptions();
  }
  const bookName = row => row.label || row.display_name || row.name;
  function paintOptions() {
    if (!customers) return;   // còn đang tải: giữ câu "Đang tải…", tải xong sẽ lọc theo chữ đã gõ
    const needle = foldText($('link-search').value.trim());
    const taken = new Set(linkedBooks().map(row => String(row.customer_id)));
    const rows = (customers ?? []).filter(row => !taken.has(String(row.id)) && (!needle || foldText(bookName(row)).includes(needle))).slice(0, 30);
    $('link-options').innerHTML = rows.length ? rows.map(row => `<button type="button" class="option" role="option" data-book="${esc(row.id)}">${esc(bookName(row))}</button>`).join('')
      : '<p class="hint">Không có sổ khớp.</p>';
  }
  async function link(customer) {
    try {
      await post('/api/v7/zalo/link', { conversation_id: state.selected, customer_id: customer });
      linkDialog.close();
      await loadLinks();
      paintLinks();
      paintList();
      if (markDialog.open) fillBooks();
      repaintKeep();
    } catch (error) {
      $('link-error').textContent = saveError(error, 'gắn sổ');
      $('link-error').hidden = false;
    }
  }

  // Bỏ dấu, bỏ gắn: lý do bắt buộc, giữ vết như hủy phiếu.
  const reasonDialog = $('reason-dialog');
  let reasonAction = null;
  function askReason(title, what, action) {
    reasonAction = action;
    $('reason-title').textContent = title;
    $('reason-what').textContent = what;
    $('reason-text').value = '';
    $('reason-error').hidden = true;
    $('reason-save').disabled = false;
    reasonDialog.showModal();
  }
  async function saveReason(event) {
    event.preventDefault();
    const reason = $('reason-text').value.trim();
    if (!reason) { $('reason-error').textContent = 'Cần ghi lý do.'; $('reason-error').hidden = false; return; }
    if ($('reason-save').disabled) return;
    $('reason-save').disabled = true;
    try {
      await reasonAction(reason);
      reasonDialog.close();
    } catch (error) {
      $('reason-error').textContent = saveError(error, 'lưu');
      $('reason-error').hidden = false;
      $('reason-save').disabled = false;
    }
  }
  function unmark(id) {
    const row = [...marks.values()].flat().find(item => String(item.id) === String(id));
    if (!row) return;
    askReason('Bỏ dấu', markText(row).replace(/<[^>]*>/g, ''), async reason => {
      await post('/api/v7/marks/cancel', { id: row.id, reason });
      await loadMarks(state.selected);
      repaintKeep();
    });
  }
  function unlink(customer) {
    const row = linkedBooks().find(item => String(item.customer_id) === String(customer));
    if (!row) return;
    askReason('Bỏ gắn sổ', `Bỏ gắn group này với sổ ${row.customer_name}. Dấu đã ghi vẫn giữ.`, async reason => {
      await post('/api/v7/zalo/unlink', { conversation_id: state.selected, customer_id: row.customer_id, reason });
      await loadLinks();
      paintLinks();
      paintList();
      repaintKeep();
    });
  }

  for (const dialog of [markDialog, linkDialog, reasonDialog]) {
    dialog.addEventListener('click', event => { if (event.target.closest('[data-close]')) dialog.close(); });
  }
  $('mark-form').addEventListener('change', event => { if (event.target.name === 'kind') syncKind(); });
  $('mark-form').addEventListener('submit', saveMark);
  $('mark-no-book').addEventListener('click', event => { if (event.target.closest('[data-open-link]')) openLink(); });
  $('link-search').addEventListener('input', paintOptions);
  $('link-options').addEventListener('click', event => { const option = event.target.closest('[data-book]'); if (option) link(Number(option.dataset.book)); });
  $('reason-form').addEventListener('submit', saveReason);
  $('links').addEventListener('click', event => {
    if (event.target.closest('[data-open-link]')) openLink();
    const chip = event.target.closest('[data-unlink]');
    if (chip) unlink(chip.dataset.unlink);
  });

  function paintMessages() {
    const box = $('messages');
    if (!state.messages.length) {
      box.innerHTML = `<p class="empty">${state.query.trim() ? 'Không có tin nào khớp từ khóa.' : 'Hội thoại chưa có tin nào trong bản xuất.'}</p>`;
      return;
    }
    const parts = [];
    if (state.hasOlder) parts.push(`<button type="button" class="btn older" id="older">Tải tin cũ hơn (${number(state.total - state.messages.length - state.newest * PAGE_LIMIT)} tin)</button>`);
    else parts.push(`<p class="end">Đầu hội thoại${state.query.trim() ? ' (kết quả tìm)' : ''}</p>`);
    let day = null;
    let previous = null;
    for (const message of state.messages) {
      const key = message.timestamp_ms ? dayKey(message.timestamp_ms) : null;
      if (key && key !== day) { parts.push(`<div class="day">${esc(key)}</div>`); day = key; previous = null; }
      const first = !previous || previous.sender_id !== message.sender_id;
      parts.push(renderMessage(message, first));
      previous = message;
    }
    if (state.newest > 0) parts.push(`<button type="button" class="btn newer" id="newer">Tải tin mới hơn</button>`);
    box.innerHTML = parts.join('');
  }

  // mode: 'fresh' thay cả khung (mở hội thoại, tìm, thử lại), 'older' ghép lên trên, 'newer' ghép xuống dưới.
  // `focus`: mở đúng trang chứa tin đó (máy chủ tính trang), tô sáng và cuộn tới tin.
  async function loadPage(page, { mode = 'fresh', focus = null } = {}) {
    const request = ++state.request;
    const params = new URLSearchParams({ conversation: state.selected, page: String(page), limit: String(PAGE_LIMIT) });
    if (state.query.trim()) params.set('q', state.query.trim());
    if (focus) params.set('message', focus);
    const box = $('messages');
    const fresh = mode === 'fresh';
    const button = mode === 'older' ? $('older') : mode === 'newer' ? $('newer') : null;
    if (button) { button.disabled = true; button.textContent = 'Đang tải…'; } else box.innerHTML = '<p class="loading">Đang tải tin nhắn…</p>';
    try {
      const data = await json(`/api/v7/zalo/messages?${params}`);
      if (request !== state.request) return;
      state.total = data.total;
      const before = box.scrollHeight - box.scrollTop;
      const top = box.scrollTop;
      if (fresh) {
        state.page = state.newest = data.page;
        state.hasOlder = data.has_older;
        state.messages = data.messages;
        state.focus = data.focus ?? null;
      } else if (mode === 'older') {
        state.page = data.page;
        state.hasOlder = data.has_older;
        state.messages = data.messages.concat(state.messages);
      } else {
        state.newest = data.page;
        state.messages = state.messages.concat(data.messages);
      }
      paintMessages();
      const target = state.focus && fresh ? box.querySelector('.msg.focus') : null;
      if (target) {
        state.focus = null;   // chỉ tô lần mở này; tải thêm trang vẽ lại thì không tô nữa
        target.scrollIntoView({ block: 'center' });
        setTimeout(() => target.classList.remove('focus'), 3000);
      } else if (fresh) box.scrollTop = box.scrollHeight;          // trang mới nhất: cuộn xuống tin cuối
      else if (mode === 'older') box.scrollTop = box.scrollHeight - before;   // tải tin cũ: giữ chỗ đang đọc
      else box.scrollTop = top;
      $('subtitle').textContent = state.query.trim()
        ? `${number(data.total)} tin khớp "${state.query.trim()}"`
        : `${number(data.total)} tin · đang hiện ${number(state.messages.length)}`;
    } catch (error) {
      if (request !== state.request) return;
      if (error.status === 404 && error.code === 'MESSAGE_NOT_FOUND') {
        state.focus = null;
        await loadPage(0);
        $('subtitle').textContent = 'Tin đã đánh dấu không còn trên web; đang hiện tin mới nhất.';
      } else if (error.status === 404) box.innerHTML = '<p class="empty">Hội thoại này không còn trong bản xuất.</p>';
      else box.innerHTML = `<p class="empty">${esc(loadError('tin nhắn'))} <button type="button" class="btn" data-retry-page="${page}">Thử lại</button></p>`;
    }
  }

  async function open(id, focus = null) {
    const row = state.conversations.find(item => item.conversation_id === id);
    if (!row) return;
    state.selected = id;
    state.query = '';
    state.messages = [];
    state.page = state.newest = 0;
    $('message-search').value = '';
    $('message-search').disabled = false;
    $('title').textContent = nameOf(row);
    $('title').title = id;
    $('subtitle').textContent = `${number(row.message_count)} tin`;
    chat.classList.add('show-detail');
    paintList();
    setUrl();
    paintLinks();
    await Promise.all([loadMarks(id), loadPage(0, { focus })]);
    if (marks.size && state.selected === id) repaintKeep();
  }

  // Xem ảnh lớn: hộp thoại gốc của trình duyệt, Esc hoặc bấm ra ngoài thì đóng.
  const viewer = $('pic-viewer');
  function showPicture(src) {
    viewer.querySelector('img').src = src;
    viewer.showModal();
  }
  viewer.addEventListener('click', event => { if (event.target === viewer || event.target.closest('[data-close]')) viewer.close(); });

  let searchTimer = null;
  $('conversation-search').addEventListener('input', event => {
    state.filter = event.target.value;
    paintList();
    setUrl();
  });
  $('message-search').addEventListener('input', event => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = event.target.value;
      if (state.selected) loadPage(0);
    }, 300);
  });
  $('conversations').addEventListener('click', event => {
    const button = event.target.closest('[data-id]');
    if (button) open(button.dataset.id);
  });
  $('messages').addEventListener('click', event => {
    const retry = event.target.closest('[data-retry-page]');
    if (retry) { loadPage(Number(retry.dataset.retryPage)); return; }
    const picture = event.target.closest('[data-pic]');
    if (picture) { showPicture(picture.dataset.pic); return; }
    const mark = event.target.closest('[data-mark]');
    if (mark) { openMark(mark.dataset.mark); return; }
    const unmarkButton = event.target.closest('[data-unmark]');
    if (unmarkButton) { unmark(unmarkButton.dataset.unmark); return; }
    // Điện thoại không rê chuột: chạm vào tin thì hiện nút Đánh dấu của tin đó.
    const article = event.target.closest('.msg');
    if (article) {
      for (const other of $('messages').querySelectorAll('.msg.show-actions')) if (other !== article) other.classList.remove('show-actions');
      article.classList.add('show-actions');
    }
    if (event.target.closest('#older') && state.hasOlder) loadPage(state.page + 1, { mode: 'older' });
    if (event.target.closest('#newer') && state.newest > 0) loadPage(state.newest - 1, { mode: 'newer' });
  });
  $('back-list').addEventListener('click', () => {
    chat.classList.remove('show-detail');
  });

  async function init() {
    const params = new URLSearchParams(location.search);
    state.filter = params.get('q') ?? '';
    $('conversation-search').value = state.filter;
    $('summary').textContent = 'Đang tải…';
    try {
      const [summary, list] = await Promise.all([json('/api/v7/zalo/report'), json('/api/v7/zalo/conversations'), loadLinks()]);
      state.conversations = list.conversations ?? [];
      // Gói web (ZALO-GROUP-01) ghi giờ dựng; bản xuất cũ 30/10 thì giữ dòng đếm như trước.
      $('summary').textContent = summary.status === 'BUNDLED'
        ? `${number(summary.conversation_count)} group · ${number(summary.message_count)} tin · ${number(summary.media_count)} ảnh · cập nhật ${updatedText(summary.built_at)} · chỉ xem`
        : `${number(summary.conversation_count)} hội thoại · ${number(summary.message_count)} tin · ${number(summary.named_conversations)} có tên khách · ${number(summary.attachment_unmatched)} đính kèm chưa khớp · chỉ xem`;
      chat.hidden = false;
      $('error').hidden = true;
      paintList();
      const wanted = params.get('c');
      const matches = filtered();
      if (wanted && state.conversations.some(row => row.conversation_id === wanted)) await open(wanted, params.get('m'));
      else if (state.filter.trim() && matches.length === 1) await open(matches[0].conversation_id);
    } catch (error) {
      $('summary').textContent = 'Chưa có dữ liệu chat.';
      showError(error);
    }
  }

  $('error').addEventListener('click', event => { if (event.target.closest('[data-retry]')) init(); });
  init();
})();
