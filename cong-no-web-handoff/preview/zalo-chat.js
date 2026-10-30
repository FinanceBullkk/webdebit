(() => {
  'use strict';
  // ZALO-CHAT-01: tab Chat Zalo — xem lại hội thoại với khách từ bản xuất (chỉ đọc).
  // Trang chỉ nhận từng trang tin từ /api/v7/zalo/messages (tối đa 100 tin một lượt), không bao giờ
  // tải cả bản xuất; không ghi nội dung tin ra console hay nơi nào khác.
  const $ = id => document.getElementById(id);
  // Thoát HTML và so khớp không phân biệt hoa thường/dấu tiếng Việt (foldText: cùng quy tắc với máy chủ) từ CongNoFormat.
  const { esc, foldText } = CongNoFormat;
  const TZ = 'Asia/Ho_Chi_Minh';
  const PAGE_LIMIT = 50;
  const state = {
    conversations: [], filter: '', selected: null, messages: [], total: 0, page: 0, hasOlder: false,
    query: '', request: 0, loading: false,
  };
  const chat = $('chat');

  const dayKey = ms => new Date(ms).toLocaleDateString('vi-VN', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric' });
  const timeText = ms => (ms ? new Date(ms).toLocaleTimeString('vi-VN', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }) : '');
  const shortId = id => (id ? String(id).slice(0, 8) : '');
  const nameOf = row => row.display_name || `Chưa rõ tên · ${shortId(row.conversation_id)}`;
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
      box.textContent = `Không tải được dữ liệu chat. ${error?.message ?? ''} Tải lại trang để thử lại.`.trim();
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
    const row = state.conversations.find(item => item.conversation_id === state.selected);
    if (row && row.display_name && row.participant_count <= 2) return row.display_name;
    return `Thành viên ${shortId(message.sender_id)}`;
  }

  function renderMessage(message) {
    const body = message.body_kind === 'missing'
      ? `<div class="body missing">Không đọc được nội dung tin này${message.body_state ? ` (${esc(message.body_state)})` : ''}.</div>`
      : message.body_text
        ? `<div class="body${message.body_kind === 'card' ? ' card' : ''}">${highlight(message.body_text)}</div>`
        : `<div class="body card">[${esc(message.type_label)}]</div>`;
    return `<article class="msg ${message.is_own ? 'own' : 'other'}" data-id="${esc(message.message_id)}">
      <div class="meta"><span class="who">${esc(senderText(message))}</span><time>${esc(timeText(message.timestamp_ms))}</time><span>${esc(message.type_label)}</span><span>${esc(message.status_label)}</span></div>
      ${body}${attachmentText(message.attachment)}
    </article>`;
  }

  function paintMessages() {
    const box = $('messages');
    if (!state.messages.length) {
      box.innerHTML = `<p class="empty">${state.query.trim() ? 'Không có tin nào khớp từ khóa.' : 'Hội thoại chưa có tin nào trong bản xuất.'}</p>`;
      return;
    }
    const parts = [];
    if (state.hasOlder) parts.push(`<button type="button" class="btn older" id="older">Tải tin cũ hơn (${number(state.total - state.messages.length)} tin)</button>`);
    else parts.push(`<p class="end">Đầu hội thoại${state.query.trim() ? ' (kết quả tìm)' : ''}</p>`);
    let day = null;
    for (const message of state.messages) {
      const key = message.timestamp_ms ? dayKey(message.timestamp_ms) : null;
      if (key && key !== day) { parts.push(`<div class="day">${esc(key)}</div>`); day = key; }
      parts.push(renderMessage(message));
    }
    box.innerHTML = parts.join('');
  }

  async function loadPage(page) {
    const request = ++state.request;
    const params = new URLSearchParams({ conversation: state.selected, page: String(page), limit: String(PAGE_LIMIT) });
    if (state.query.trim()) params.set('q', state.query.trim());
    const box = $('messages');
    const older = $('older');
    if (older) { older.disabled = true; older.textContent = 'Đang tải…'; } else box.innerHTML = '<p class="loading">Đang tải tin nhắn…</p>';
    try {
      const data = await json(`/api/v7/zalo/messages?${params}`);
      if (request !== state.request) return;
      state.total = data.total;
      state.hasOlder = data.has_older;
      state.page = page;
      const before = box.scrollHeight - box.scrollTop;
      state.messages = page === 0 ? data.messages : data.messages.concat(state.messages);
      paintMessages();
      // Trang 0: cuộn xuống tin mới nhất; tải tin cũ: giữ nguyên chỗ đang đọc.
      box.scrollTop = page === 0 ? box.scrollHeight : box.scrollHeight - before;
      $('subtitle').textContent = state.query.trim()
        ? `${number(data.total)} tin khớp "${state.query.trim()}"`
        : `${number(data.total)} tin · đang hiện ${number(state.messages.length)}`;
    } catch (error) {
      if (request !== state.request) return;
      if (error.status === 404) box.innerHTML = '<p class="empty">Hội thoại này không còn trong bản xuất.</p>';
      else box.innerHTML = `<p class="empty">Không tải được tin nhắn. ${esc(error.message)}</p>`;
    }
  }

  async function open(id) {
    const row = state.conversations.find(item => item.conversation_id === id);
    if (!row) return;
    state.selected = id;
    state.query = '';
    state.messages = [];
    $('message-search').value = '';
    $('message-search').disabled = false;
    $('title').textContent = nameOf(row);
    $('title').title = id;
    $('subtitle').textContent = `${number(row.message_count)} tin`;
    chat.classList.add('show-detail');
    paintList();
    setUrl();
    await loadPage(0);
  }

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
    if (event.target.closest('#older') && state.hasOlder) loadPage(state.page + 1);
  });
  $('back-list').addEventListener('click', () => {
    chat.classList.remove('show-detail');
  });

  async function init() {
    const params = new URLSearchParams(location.search);
    state.filter = params.get('q') ?? '';
    $('conversation-search').value = state.filter;
    try {
      const [summary, list] = await Promise.all([json('/api/v7/zalo/report'), json('/api/v7/zalo/conversations')]);
      state.conversations = list.conversations ?? [];
      $('summary').textContent = `${number(summary.conversation_count)} hội thoại · ${number(summary.message_count)} tin · ${number(summary.named_conversations)} có tên khách · ${number(summary.attachment_unmatched)} đính kèm chưa khớp · chỉ xem`;
      chat.hidden = false;
      $('error').hidden = true;
      paintList();
      const wanted = params.get('c');
      const matches = filtered();
      if (wanted && state.conversations.some(row => row.conversation_id === wanted)) await open(wanted);
      else if (state.filter.trim() && matches.length === 1) await open(matches[0].conversation_id);
    } catch (error) {
      $('summary').textContent = 'Chưa có dữ liệu chat.';
      showError(error);
    }
  }

  init();
})();
