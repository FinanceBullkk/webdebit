(() => {
  'use strict';
  // QUYEN-02 (specs/quyen-02.md): trang Người dùng, chỉ quản lý. Đọc GET /api/v7/admin/users, ghi POST cùng đường với
  // `version` vừa đọc (lệch thì máy chủ trả STALE, trang đọc lại). Login cố định trên máy chủ và dòng của chính mình không
  // có ô đổi vai trò hay nút ⋯. Bố cục 20/11/2026: thẻ Thành viên (dòng xin vào ở đầu), thẻ Lịch sử, hộp thoại Thêm người.
  const F = CongNoFormat;
  const { esc } = F;
  const $ = id => document.getElementById(id);
  const URL_USERS = '/api/v7/admin/users';
  const ROLE = { admin: 'Quản lý', user: 'Nhân viên' };
  const HISTORY_SHORT = 5;
  const LOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
  const DOTS = '<svg viewBox="0 0 24 24" aria-hidden="true" style="fill:currentColor;stroke:none"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>';
  const dialog = $('add-dialog');
  let data = null, confirming = null, editing = null, menuFor = null, busy = false, allHistory = false, toastTimer = 0;

  const short = login => String(login ?? '').split('@')[0] || '—';
  const when = iso => {
    const at = new Date(iso);
    if (!iso || Number.isNaN(at.getTime())) return '—';
    const part = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }).formatToParts(at);
    const get = type => part.find(item => item.type === type)?.value ?? '';
    return `${get('day')}/${get('month')} ${get('hour')}:${get('minute')}`;
  };
  const shown = user => user.name || short(user.login);
  // Tên trên Lịch sử: tên gọi của người còn trong danh sách, không thì phần trước @ của login; rê chuột thấy login đủ.
  const who = login => {
    const user = data.users?.find(item => item.login === login);
    return `<span title="${esc(login)}">${esc(user ? shown(user) : short(login))}</span>`;
  };
  const initial = user => {
    const words = shown(user).trim().split(/\s+/);
    return (user.name ? words[words.length - 1] : words[0]).charAt(0).toUpperCase() || '?';
  };

  function flash(text) {
    const box = $('flash');
    clearTimeout(toastTimer);
    box.textContent = text;
    box.hidden = !text;
    if (text) toastTimer = setTimeout(() => { box.hidden = true; }, 4000);
  }
  // Lỗi hiện trong hộp thoại khi hộp đang mở (lớp phủ che phần trang), ngoài ra ở đầu trang.
  function fail(text, retry = false) {
    if (text && dialog.open) { addError(text); return; }
    const box = $('error');
    box.innerHTML = text ? `<span>${esc(text)}</span>${retry ? '<button type="button" class="nd-btn" id="retry">Thử lại</button>' : ''}` : '';
    box.hidden = !text;
    if (retry) $('retry').addEventListener('click', load);
  }
  function addError(text) {
    const box = $('add-error');
    box.textContent = text;
    box.hidden = !text;
    $('add-login').setAttribute('aria-invalid', String(Boolean(text)));
  }

  function drawDenied() {
    const rows = data.configured ? data.denied ?? [] : [];
    $('denied').innerHTML = rows.map(row => `<div class="nd-grid nd-row request" data-login="${esc(row.login)}">`
      + `<div class="nd-who"><span class="nd-av" aria-hidden="true">?</span><div class="text"><div class="name">${esc(row.login)}</div>`
      + `<div class="sub">Xin vào sổ · ${esc(row.count)} lần · lần cuối ${esc(when(row.last_at))}</div></div></div>`
      + '<div class="nd-acts"><button type="button" class="nd-btn" data-act="dismiss">Bỏ qua</button>'
      + `<button type="button" class="nd-btn primary" data-act="allow" aria-label="Cho ${esc(row.login)} vào làm Nhân viên">Cho vào</button></div></div>`).join('');
  }

  function roleCell(user) {
    const label = esc(shown(user));
    if (user.me || user.fixed || !data.configured) {
      const why = user.fixed ? 'Cố định trên máy chủ, không đổi trên web' : user.me ? 'Không tự đổi vai trò của mình' : 'Chỉ xem';
      return `<span class="nd-box locked" title="${why}">${ROLE[user.role] ?? '—'}${user.fixed ? LOCK : ''}</span><span></span>`;
    }
    const open = menuFor === user.login;
    return `<select class="nd-box" data-act="role" aria-label="Vai trò của ${label}">${['user', 'admin'].map(role =>
      `<option value="${role}"${user.role === role ? ' selected' : ''}>${ROLE[role]}</option>`).join('')}</select>`
      + `<div class="nd-slot"><button type="button" class="nd-icon" data-act="menu" aria-haspopup="menu" aria-expanded="${open}" aria-label="Thao tác với ${label}">${DOTS}</button>`
      + (open ? `<div class="nd-menu" role="menu" aria-label="Thao tác với ${label}">`
        + '<button type="button" role="menuitem" data-act="edit-name">Sửa tên gọi</button>'
        + '<button type="button" role="menuitem" class="red" data-act="ask-remove">Bỏ quyền vào</button></div>' : '')
      + '</div>';
  }

  function drawUsers() {
    const users = data.users ?? [];
    const admins = users.filter(user => user.role === 'admin').length;
    $('user-count').textContent = `${users.length} người · ${admins} quản lý`;
    $('users').innerHTML = users.length ? users.map(user => {
      const login = esc(user.login);
      if (confirming === user.login) {
        return `<div class="nd-grid nd-row confirm" data-login="${login}" role="group" aria-label="Xác nhận bỏ quyền vào">`
          + `<span class="ask">Bỏ quyền vào của ${esc(shown(user))} (${login})? Họ sẽ không mở được sổ nữa.</span>`
          + '<div class="nd-acts"><button type="button" class="nd-btn" data-act="cancel">Thôi</button>'
          + '<button type="button" class="nd-btn danger" data-act="remove">Bỏ quyền</button></div></div>';
      }
      const body = editing === user.login
        ? `<div class="nd-rename"><input type="text" maxlength="40" value="${esc(user.name ?? '')}" aria-label="Tên gọi của ${login}" placeholder="Tên gọi">`
          + '<button type="button" class="nd-btn primary" data-act="save-name">Lưu</button><button type="button" class="nd-btn" data-act="cancel">Thôi</button></div>'
        : `<div class="text"><div class="name">${esc(shown(user))}${user.me ? '<span class="nd-me">Bạn</span>' : ''}</div><div class="sub">${login}</div></div>`;
      return `<div class="nd-grid nd-row" data-login="${login}"><div class="nd-who"><span class="nd-av" aria-hidden="true">${esc(initial(user))}</span>${body}</div>${roleCell(user)}</div>`;
    }).join('') : '<p class="nd-empty">Chưa có ai trong danh sách.</p>';
    const note = $('users-note');
    note.textContent = data.broken ? 'File danh sách trên máy chủ bị hỏng: đang chỉ dùng danh sách cố định, chưa sửa được trên web.'
      : data.configured ? '' : 'Máy chủ chưa bật quản lý người dùng trên web: danh sách này chỉ xem.';
    note.classList.toggle('bad', Boolean(data.broken));
    note.hidden = !note.textContent;
    const input = document.querySelector('.nd-rename input');
    if (input) { input.focus(); input.select(); }
  }

  function historyText(item) {
    const before = item.before ?? {}, after = item.after ?? {};
    const name = who(item.login);
    if (item.action === 'add') return `cho ${name} vào làm ${ROLE[after.role] ?? '—'}`;
    if (item.action === 'remove') return `bỏ quyền vào của ${name} (trước là ${ROLE[before.role] ?? '—'})`;
    if (item.action === 'role') return `đổi vai trò ${name}: ${ROLE[before.role] ?? '—'} → ${ROLE[after.role] ?? '—'}`;
    return `đổi tên gọi ${esc(short(item.login))}: ${esc(before.name || '—')} → ${esc(after.name || '—')}`;
  }
  // Người làm: login có @ là người (chính mình ghi "Bạn"); không có @ là máy (chuyển từ cấu hình máy chủ) ghi "Hệ thống".
  function actor(raw) {
    const text = String(raw ?? '');
    if (!text.includes('@')) return `<b title="${esc(text)}">Hệ thống</b>`;
    const me = data.users?.find(user => user.me);
    return `<b title="${esc(text)}">${me?.login === text ? 'Bạn' : who(text)}</b>`;
  }
  function drawHistory() {
    const rows = data.history ?? [];
    const list = allHistory ? rows : rows.slice(0, HISTORY_SHORT);
    $('history').innerHTML = rows.length
      ? list.map(item => `<div class="nd-hist"><span class="what">${actor(item.actor)} ${historyText(item)}</span><span class="at">${esc(when(item.at))}</span></div>`).join('')
        + (rows.length > HISTORY_SHORT ? `<div class="nd-more"><button type="button" class="nd-btn" id="history-more">${allHistory ? 'Thu gọn' : `Xem thêm ${rows.length - HISTORY_SHORT}`}</button></div>` : '')
      : '<p class="nd-empty">Chưa có thay đổi nào trên web.</p>';
  }

  function draw() {
    drawDenied();
    drawUsers();
    $('add-open').hidden = !data.configured;
    drawHistory();
  }

  async function load() {
    try {
      const response = await fetch(URL_USERS, { cache: 'no-store' });
      const body = await response.json().catch(() => null);
      if (!response.ok || !body || !Array.isArray(body.users)) throw Error(body?.message || 'Không đọc được danh sách người dùng.');
      data = body;
      fail('');
      draw();
    } catch (error) {
      fail(error.message === 'Failed to fetch' ? 'Mất kết nối tới máy chủ.' : error.message, true);
      if (!data) $('users').innerHTML = '';
    }
  }

  function setBusy(on) {
    busy = on;
    document.querySelectorAll('.nd button, .nd select').forEach(control => { control.disabled = on; });
  }

  async function send(body, done) {
    if (busy || !data) return false;
    setBusy(true);
    try {
      const response = await fetch(URL_USERS, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, version: data.version }) });
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        // Bản cũ: đọc lại rồi mới báo, như nhánh thành công bên dưới; báo trước thì câu "Trang đã đọc lại" hiện khi bảng còn số cũ
        // (ô chọn còn giá trị vừa bấm), và load() thành công còn xóa câu đó đi.
        if (result?.error === 'STALE') { confirming = editing = menuFor = null; await load(); fail(result.message); }
        else { fail(result?.message || 'Chưa lưu được. Thử lại sau.'); drawUsers(); }
        return false;
      }
      // Báo "Đã …" chỉ sau khi đọc lại và vẽ xong bảng: không để câu báo đi trước số trên bảng.
      confirming = editing = menuFor = null;
      fail('');
      flash('');
      await load();
      flash(done);
      return true;
    } catch {
      fail('Mất kết nối tới máy chủ. Bấm Đọc lại để xem đã lưu chưa.');
      return false;
    } finally {
      setBusy(false);
    }
  }

  function closeMenu(focusButton) {
    if (!menuFor) return;
    const login = menuFor;
    menuFor = null;
    drawUsers();
    if (focusButton) document.querySelector(`.nd-row[data-login="${CSS.escape(login)}"] [data-act="menu"]`)?.focus();
  }

  $('denied').addEventListener('click', event => {
    const button = event.target.closest('button[data-act]');
    const login = button?.closest('.nd-row')?.dataset.login;
    if (!login) return;
    if (button.dataset.act === 'allow') send({ action: 'add', login, role: 'user' }, `Đã cho ${login} vào làm Nhân viên.`);
    else { data.denied = data.denied.filter(row => row.login !== login); drawDenied(); }
  });

  $('users').addEventListener('click', event => {
    const button = event.target.closest('button[data-act]');
    const login = button?.closest('.nd-row')?.dataset.login;
    if (!login) return;
    const user = data.users.find(item => item.login === login);
    const act = button.dataset.act;
    if (act === 'menu') {
      const opening = menuFor !== login;
      menuFor = opening ? login : null;
      confirming = editing = null;
      drawUsers();
      if (opening) document.querySelector('.nd-menu button')?.focus();
    } else if (act === 'ask-remove') { confirming = login; editing = menuFor = null; drawUsers(); document.querySelector('.nd-row.confirm .danger')?.focus(); }
    else if (act === 'cancel') { confirming = editing = null; drawUsers(); }
    else if (act === 'remove') send({ action: 'remove', login }, `Đã bỏ quyền vào của ${shown(user)}.`);
    else if (act === 'edit-name') { editing = login; confirming = menuFor = null; drawUsers(); }
    else if (act === 'save-name') {
      const name = button.closest('.nd-rename').querySelector('input').value.trim();
      send({ action: 'name', login, name: name || null }, `Đã lưu tên gọi của ${login}.`);
    }
  });
  $('users').addEventListener('change', event => {
    const select = event.target.closest('select[data-act="role"]');
    const login = select?.closest('.nd-row')?.dataset.login;
    if (!login) return;
    const user = data.users.find(item => item.login === login);
    send({ action: 'role', login, role: select.value }, `Đã đổi ${shown(user)} thành ${ROLE[select.value]}.`);
  });
  $('users').addEventListener('keydown', event => {
    if (event.target.matches('.nd-rename input') && event.key === 'Enter') event.target.closest('.nd-rename').querySelector('[data-act="save-name"]').click();
    if (event.key !== 'Escape') return;
    if (menuFor) closeMenu(true);
    else if (confirming || editing) { confirming = editing = null; drawUsers(); }
  });
  document.addEventListener('click', event => {
    if (menuFor && !event.target.closest('.nd-slot')) closeMenu(false);
  });
  $('history').addEventListener('click', event => {
    if (event.target.closest('#history-more')) { allHistory = !allHistory; drawHistory(); }
  });

  $('add-open').addEventListener('click', () => {
    confirming = editing = menuFor = null;
    drawUsers();
    addError('');
    flash('');
    dialog.showModal();
    $('add-login').focus();
  });
  dialog.addEventListener('click', event => {
    if (event.target.closest('[data-close]') || event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => {
    $('add-form').reset();
    addError('');
    $('add-open').focus();
  });
  $('add-login').addEventListener('input', () => addError(''));
  $('add-form').addEventListener('submit', async event => {
    event.preventDefault();
    const login = $('add-login').value.trim();
    if (!/^[^\s@,]+@[^\s@,]+$/.test(login)) { addError('Login Tailscale có dạng ten@mien, ví dụ ten@gmail.com.'); $('add-login').focus(); return; }
    const role = document.querySelector('input[name="add-role"]:checked').value;
    const name = $('add-name').value.trim();
    const ok = await send({ action: 'add', login, role, ...(name ? { name } : {}) }, `Đã cho ${login} vào làm ${ROLE[role]}.`);
    if (ok) dialog.close();
  });
  $('refresh-data').addEventListener('click', () => { flash(''); load(); });

  load();
})();
