(() => {
  'use strict';
  // QUYEN-02 (specs/quyen-02.md): trang Người dùng, chỉ quản lý. Đọc GET /api/v7/admin/users, ghi POST cùng đường với
  // `version` vừa đọc (lệch thì máy chủ trả STALE, trang đọc lại). Login cố định trên máy chủ và dòng của chính mình không có nút.
  const F = CongNoFormat;
  const { esc } = F;
  const $ = id => document.getElementById(id);
  const URL_USERS = '/api/v7/admin/users';
  const ROLE = { admin: 'Quản lý', user: 'Nhân viên' };
  let data = null, confirming = null, editing = null, busy = false;

  const short = login => String(login ?? '').split('@')[0] || '—';
  const when = iso => {
    const at = new Date(iso);
    if (!iso || Number.isNaN(at.getTime())) return '—';
    const part = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }).formatToParts(at);
    const get = type => part.find(item => item.type === type)?.value ?? '';
    return `${get('day')}/${get('month')} ${get('hour')}:${get('minute')}`;
  };
  const shown = user => user.name || short(user.login);
  const roleTag = role => `<span class="nd-role ${role === 'admin' ? 'admin' : ''}">${ROLE[role] ?? '—'}</span>`;

  function flash(text) {
    const box = $('flash');
    box.textContent = text;
    box.hidden = !text;
  }
  function fail(text, retry = false) {
    const box = $('error');
    box.innerHTML = text ? `${esc(text)}${retry ? ' <button type="button" class="btn" id="retry">Thử lại</button>' : ''}` : '';
    box.hidden = !text;
    if (retry) $('retry').addEventListener('click', load);
  }

  function drawDenied() {
    const rows = data.configured ? data.denied ?? [] : [];
    $('denied-box').hidden = !rows.length;
    $('denied').innerHTML = rows.map(row => `<li data-login="${esc(row.login)}"><span class="who">${esc(row.login)}</span>`
      + `<span class="when">lần cuối ${esc(when(row.last_at))} · ${row.count} lần</span>`
      + `<button type="button" class="btn primary" data-act="allow">Cho vào (nhân viên)</button>`
      + `<button type="button" class="btn quiet" data-act="dismiss">Bỏ qua</button></li>`).join('');
  }

  function actions(user) {
    if (user.me) return '<span class="nd-tag">Bạn</span>';
    if (user.fixed) return '<span class="nd-tag">Cố định trên máy chủ</span>';
    if (!data.configured) return '';
    const other = user.role === 'admin' ? 'user' : 'admin';
    return `<button type="button" class="btn" data-act="role" data-role="${other}">Đổi thành ${ROLE[other]}</button>`
      + '<button type="button" class="btn" data-act="ask-remove">Bỏ quyền vào</button>';
  }

  function drawUsers() {
    const users = data.users ?? [];
    $('user-count').textContent = `(${users.length})`;
    if (!users.length) { $('users').innerHTML = '<p class="empty">Chưa có ai trong danh sách.</p>'; return; }
    $('users').innerHTML = `<table class="nd-table"><thead><tr><th>Tên gọi</th><th>Login</th><th>Vai trò</th><th>Thêm bởi</th><th></th></tr></thead><tbody>${
      users.map(user => {
        const login = esc(user.login);
        if (confirming === user.login) {
          return `<tr class="confirm" data-login="${login}"><td colspan="4" class="ask">Bỏ quyền vào của ${esc(shown(user))} (${login})? Họ sẽ không mở được sổ nữa.</td>`
            + '<td class="acts"><button type="button" class="btn danger" data-act="remove">Bỏ quyền</button><button type="button" class="btn" data-act="cancel">Thôi</button></td></tr>';
        }
        const nameCell = editing === user.login
          ? `<td class="nd-name"><input type="text" maxlength="40" value="${esc(user.name ?? '')}" aria-label="Tên gọi của ${login}">`
            + ' <button type="button" class="btn" data-act="save-name">Lưu</button> <button type="button" class="btn quiet" data-act="cancel">Thôi</button></td>'
          : `<td class="nd-name">${esc(shown(user))}${!user.fixed && !user.me && data.configured ? ' <button type="button" class="btn quiet" data-act="edit-name" aria-label="Đặt tên gọi cho ' + login + '">Sửa tên</button>' : ''}</td>`;
        const meta = user.added_at ? `${esc(short(user.added_by))} · ${esc(when(user.added_at))}` : '—';
        return `<tr data-login="${login}">${nameCell}<td class="login">${login}</td><td>${roleTag(user.role)}</td><td class="meta">${meta}</td><td class="acts">${actions(user)}</td></tr>`;
      }).join('')}</tbody></table>`
      + (data.broken ? '<p class="nd-hint bad">File danh sách trên máy chủ bị hỏng: đang chỉ dùng danh sách cố định, chưa sửa được trên web.</p>'
        : data.configured ? '' : '<p class="nd-hint">Máy chủ chưa bật quản lý người dùng trên web: danh sách này chỉ xem.</p>');
    const input = document.querySelector('.nd-name input');
    if (input) { input.focus(); input.select(); }
  }

  function historyText(item) {
    const before = item.before ?? {}, after = item.after ?? {};
    if (item.action === 'add') return `Cho ${item.login} vào làm ${ROLE[after.role] ?? '—'}${after.name ? ` (tên ${after.name})` : ''}`;
    if (item.action === 'remove') return `Bỏ quyền vào của ${item.login} (trước là ${ROLE[before.role] ?? '—'})`;
    if (item.action === 'role') return `Đổi vai trò ${item.login}: ${ROLE[before.role] ?? '—'} → ${ROLE[after.role] ?? '—'}`;
    return `Đổi tên gọi ${item.login}: ${before.name || '—'} → ${after.name || '—'}`;
  }
  function drawHistory() {
    const rows = data.history ?? [];
    $('history').innerHTML = rows.length
      ? `<table class="nd-history"><tbody>${rows.map(item => `<tr><td class="at">${esc(when(item.at))}</td><td class="who">${esc(short(item.actor))}</td>`
        + `<td class="what">${esc(historyText(item))}</td></tr>`).join('')}</tbody></table>`
      : '<p class="empty">Chưa có thay đổi nào trên web.</p>';
  }

  function draw() {
    drawDenied();
    drawUsers();
    $('add-box').hidden = !data.configured;
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

  async function send(body, done) {
    if (busy || !data) return false;
    busy = true;
    document.querySelectorAll('.nd button').forEach(button => { button.disabled = true; });
    try {
      const response = await fetch(URL_USERS, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, version: data.version }) });
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        fail(result?.message || 'Chưa lưu được. Thử lại sau.');
        if (result?.error === 'STALE') { confirming = editing = null; await load(); fail(result.message); }
        return false;
      }
      // Báo "Đã …" chỉ sau khi đọc lại và vẽ xong bảng: không để câu báo đi trước số trên bảng.
      confirming = editing = null;
      fail('');
      flash('');
      await load();
      flash(done);
      return true;
    } catch {
      fail('Mất kết nối tới máy chủ. Bấm Đọc lại để xem đã lưu chưa.');
      return false;
    } finally {
      busy = false;
      document.querySelectorAll('.nd button').forEach(button => { button.disabled = false; });
    }
  }

  $('denied').addEventListener('click', event => {
    const button = event.target.closest('button[data-act]');
    const login = button?.closest('li')?.dataset.login;
    if (!login) return;
    if (button.dataset.act === 'allow') send({ action: 'add', login, role: 'user' }, `Đã cho ${login} vào làm Nhân viên.`);
    else { data.denied = data.denied.filter(row => row.login !== login); drawDenied(); }
  });

  $('users').addEventListener('click', event => {
    const button = event.target.closest('button[data-act]');
    const login = button?.closest('tr')?.dataset.login;
    if (!login) return;
    const user = data.users.find(item => item.login === login);
    const act = button.dataset.act;
    if (act === 'ask-remove') { confirming = login; editing = null; flash(''); drawUsers(); document.querySelector('tr.confirm .btn.danger')?.focus(); }
    else if (act === 'cancel') { confirming = editing = null; drawUsers(); }
    else if (act === 'remove') send({ action: 'remove', login }, `Đã bỏ quyền vào của ${shown(user)}.`);
    else if (act === 'role') send({ action: 'role', login, role: button.dataset.role }, `Đã đổi ${shown(user)} thành ${ROLE[button.dataset.role]}.`);
    else if (act === 'edit-name') { editing = login; confirming = null; drawUsers(); }
    else if (act === 'save-name') {
      const name = button.closest('td').querySelector('input').value.trim();
      send({ action: 'name', login, name: name || null }, `Đã lưu tên gọi của ${login}.`);
    }
  });
  $('users').addEventListener('keydown', event => {
    if (event.target.matches('.nd-name input') && event.key === 'Enter') event.target.closest('td').querySelector('[data-act="save-name"]').click();
    if (event.key === 'Escape' && (confirming || editing)) { confirming = editing = null; drawUsers(); }
  });

  $('add-form').addEventListener('submit', async event => {
    event.preventDefault();
    const input = $('add-login');
    const login = input.value.trim();
    const shape = /^[^\s@,]+@[^\s@,]+$/.test(login);
    input.setAttribute('aria-invalid', String(!shape));
    if (!shape) { fail('Login Tailscale có dạng ten@mien, ví dụ ten@gmail.com.'); input.focus(); return; }
    const role = document.querySelector('input[name="add-role"]:checked').value;
    const name = $('add-name').value.trim();
    const ok = await send({ action: 'add', login, role, ...(name ? { name } : {}) }, `Đã cho ${login} vào làm ${ROLE[role]}.`);
    if (ok) { input.value = ''; $('add-name').value = ''; input.removeAttribute('aria-invalid'); }
  });
  $('refresh-data').addEventListener('click', () => { flash(''); load(); });

  load();
})();
