(() => {
  'use strict';
  // KHACH-WEB-01 (specs/v7-khach-web.md): thẻ Khách của Quản trị, chỉ quản lý. Đọc GET /api/v7/admin/customers. Hai việc:
  // chủ hàng booking chưa có sổ (gán vào sổ có sẵn hoặc tạo sổ mới) và tên trên booking của từng sổ (thêm, bỏ). Mỗi lệnh ghi
  // đọc phiên bản sổ ngay trước khi gửi (get_ledger_events, nhẹ), giữ khóa chống ghi trùng tới khi biết chắc kết quả: mất mạng hay
  // máy chủ lỗi thì đọc lại danh sách và bấm lại cùng khóa, máy chủ trả kết quả cũ chứ không ghi hai lần. Không đụng tiền: chuyến vào
  // sổ ở lượt máy sau, chưa giá.
  const F = CongNoFormat;
  const { esc } = F;
  const $ = id => document.getElementById(id);
  const URL_DATA = '/api/v7/admin/customers';
  const FAMILY = { BIEN: 'Biển', BO: 'Bộ' };
  const MODE = { CANG: 'Biển', BO: 'Bộ' };
  const UNKNOWN = 'Mất kết nối hoặc máy chủ lỗi, chưa rõ đã lưu chưa. Đã đọc lại danh sách: xem lại rồi mới bấm; bấm lại thì không ghi hai lần.';
  const dialog = $('create-dialog');
  // pending: thao tác đang hỏi xác nhận hay đang gõ, một chỗ một lúc. keys: khóa chống ghi trùng theo ý định, xóa khi biết chắc kết quả.
  let data = null, pending = null, busy = false, toastTimer = 0, createKey = null;
  const keys = new Map();

  const day = iso => F.dateText(String(iso ?? '').slice(0, 10));
  const books = () => (data?.customers ?? []).filter(book => book.status === 'active');
  const bookById = id => books().find(book => book.id === id);
  // Tên ở sổ đi biển chỉ dẫn chuyến biển, ở sổ đi bộ chỉ dẫn chuyến bộ; sổ chưa ghi đường nhận cả hai; sổ lưu trữ không nhận tên mới.
  const fits = (book, family) => !book.archived && book.transport_mode !== (family === 'BO' ? 'CANG' : 'BO');
  const fold = text => String(text ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/gi, 'd').toLowerCase();
  const upperName = text => String(text ?? '').normalize('NFC').trim().replace(/\s+/g, ' ').toUpperCase();
  const newKey = () => (globalThis.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const ownerId = owner => `${owner.family}|${owner.name}`;
  // Danh mục mặt hàng đang dùng (sổ nào có mặt hàng đó). Mặt hàng gõ trên booking ("SẦU RIÊNG") ứng tên trong danh mục khi cùng chữ.
  const catalog = () => [...new Set((data?.customers ?? []).map(book => book.commodity).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'));
  const catalogName = text => catalog().find(name => upperName(name) === upperName(text)) ?? '';

  function flash(text) {
    const box = $('flash');
    clearTimeout(toastTimer);
    box.textContent = text;
    box.hidden = !text;
    if (text) toastTimer = setTimeout(() => { box.hidden = true; }, 5000);
  }
  function fail(text, retry = false) {
    if (text && dialog.open) { createError(text); return; }
    const box = $('error');
    box.innerHTML = text ? `<span>${esc(text)}</span>${retry ? '<button type="button" class="nd-btn" id="retry">Thử lại</button>' : ''}` : '';
    box.hidden = !text;
    if (retry) $('retry').addEventListener('click', load);
  }
  function createError(text) {
    const box = $('create-error');
    box.textContent = text;
    box.hidden = !text;
  }

  function bookOptions(owner) {
    const suggest = owner.suggest_customer_id;
    const list = books().filter(book => fits(book, owner.family))
      .sort((a, b) => (a.id === suggest ? -1 : b.id === suggest ? 1 : a.name.localeCompare(b.name, 'vi')));
    // Sổ gợi ý (tab Sheet đang ghi các chuyến này ứng sổ đó) được chọn sẵn; vẫn phải bấm Gán rồi xác nhận.
    return '<option value="">Chọn sổ…</option>' + list.map(book =>
      `<option value="${book.id}"${book.id === suggest ? ' selected' : ''}>${esc(book.name)}${book.id === suggest ? ' · gợi ý' : ''}</option>`).join('');
  }

  // Không gán được ở đây: tên kho đã vào nhiều sổ theo tab, hay tên đã gán cho một sổ chưa nhận chuyến này (một tên chỉ gán một sổ).
  function blockedText(owner) {
    if (owner.many_books) return `Chuyến bộ của tên này đã vào ${owner.many_books} sổ khác nhau theo tab Sheet (thường là kho), nên không gán vào một sổ. Chuyến chờ tab Sheet.`;
    if (owner.assigned_to) {
      return `Tên này đã gán cho sổ ${owner.assigned_to.name}, nhưng sổ đó không nhận chuyến ${owner.family === 'BO' ? 'bộ' : 'biển'} này (khác đường, lưu trữ hay chưa có mốc). `
        + 'Một tên chỉ gán một sổ: bỏ tên ở sổ đó trước nếu muốn gán lại.';
    }
    return '';
  }

  function ownerHtml(owner) {
    const id = esc(ownerId(owner));
    if (pending?.kind === 'assign' && pending.owner === ownerId(owner)) {
      const book = bookById(pending.book);
      return `<div class="kh-owner kh-ask" data-owner="${id}" role="group" aria-label="Xác nhận gán tên booking">`
        + `<span class="ask">Gán tên <b>${esc(owner.name)}</b> vào sổ <b>${esc(book?.name ?? '—')}</b>? Chuyến ${owner.family === 'BO' ? 'bộ' : 'biển'} mang tên này sẽ tự vào sổ đó ở lượt máy sau, chưa có giá.</span>`
        + '<div class="nd-acts"><button type="button" class="nd-btn" data-act="cancel">Thôi</button>'
        + '<button type="button" class="nd-btn primary" data-act="assign-confirm">Gán</button></div></div>';
    }
    const tabs = owner.sheet_tabs?.length
      ? `<div class="sub">Sheet ghi ở tab: ${owner.sheet_tabs.map(tab => `${esc(tab.tab)} (${esc(tab.trips)})`).join(', ')}</div>` : '';
    const goods = owner.commodities?.length ? ` · ${esc(owner.commodities.join(', '))}` : '';
    const head = `<div class="kh-owner-main"><div class="name">${esc(owner.name)}<span class="kh-tag">${FAMILY[owner.family] ?? '—'}</span></div>`
      + `<div class="sub">${esc(owner.trips)} chuyến · ${esc(day(owner.first))}${owner.last !== owner.first ? ` – ${esc(day(owner.last))}` : ''}${goods}</div>${tabs}</div>`;
    const blocked = blockedText(owner);
    if (blocked) return `<div class="kh-owner kh-blocked" data-owner="${id}">${head}<p class="kh-why">${esc(blocked)}</p></div>`;
    const suggested = Boolean(owner.suggest_customer_id && bookById(owner.suggest_customer_id));
    return `<div class="kh-owner" data-owner="${id}">${head}`
      + `<div class="nd-acts"><select class="nd-box kh-pick" aria-label="Sổ để gán ${esc(owner.name)}">${bookOptions(owner)}</select>`
      + `<button type="button" class="nd-btn${suggested ? ' primary' : ''}" data-act="assign">Gán vào sổ</button>`
      + `<button type="button" class="nd-btn${suggested ? '' : ' primary'}" data-act="create">Tạo sổ mới</button></div></div>`;
  }

  function drawOwners() {
    const state = data?.unmapped ?? {};
    const owners = state.owners ?? [];
    const trips = owners.reduce((sum, owner) => sum + owner.trips, 0);
    $('owner-count').textContent = state.state === 'ok' ? `${owners.length} tên · ${trips} chuyến` : '';
    if (state.state !== 'ok') {
      $('owners').innerHTML = '<p class="nd-note bad">Không đọc được bản chụp booking nên chưa liệt kê được. Bấm Đọc lại sau ít phút.</p>';
      return;
    }
    const notes = [
      state.snapshot_stale_minutes ? `Bản chụp booking đã cũ ${state.snapshot_stale_minutes} phút: danh sách có thể chưa mới.` : '',
      state.sheet_state === 'unavailable' ? 'Chưa đọc được bản chụp giá Sheet: chưa gợi ý tab, chưa liệt kê chuyến bộ.'
        : state.road_state === 'ok' ? '' : 'Chưa đọc được bản chụp CONT_BO: danh sách chỉ có chuyến biển.',
    ].filter(Boolean).map(text => `<p class="nd-note bad">${esc(text)}</p>`).join('');
    $('owners').innerHTML = notes + (owners.length ? owners.map(ownerHtml).join('') : '<p class="nd-empty">Không có chủ hàng nào chưa có sổ.</p>');
  }

  function namesHtml(book) {
    const chips = (book.booking_names ?? []).map(name => `<span class="kh-chip">${esc(name)}`
      + `<button type="button" class="kh-x" data-act="ask-remove" data-name="${esc(name)}" aria-label="Bỏ tên ${esc(name)} khỏi sổ ${esc(book.name)}">`
      + '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6 6l8 8M14 6l-8 8"/></svg></button></span>').join('');
    if (pending?.kind === 'add' && pending.book === book.id) {
      return `${chips}<span class="kh-add-box"><input type="text" maxlength="200" spellcheck="false" aria-label="Tên trên booking thêm vào sổ ${esc(book.name)}" placeholder="Tên chủ hàng trên booking">`
        + '<button type="button" class="nd-btn primary" data-act="add-confirm">Gán</button><button type="button" class="nd-btn" data-act="cancel">Thôi</button></span>';
    }
    return book.archived ? chips : `${chips}<button type="button" class="nd-btn kh-add" data-act="add" aria-label="Thêm tên trên booking cho sổ ${esc(book.name)}">+ Thêm tên</button>`;
  }

  function bookHtml(book) {
    if (pending?.kind === 'remove' && pending.book === book.id) {
      return `<div class="kh-grid kh-row kh-ask danger" data-id="${book.id}" role="group" aria-label="Xác nhận bỏ tên booking">`
        + `<span class="ask">Bỏ tên <b>${esc(pending.name)}</b> khỏi sổ <b>${esc(book.name)}</b>? Chuyến mới mang tên này sẽ không tự vào sổ nữa; chuyến đã vào sổ giữ nguyên.</span>`
        + '<div class="nd-acts"><button type="button" class="nd-btn" data-act="cancel">Thôi</button>'
        + '<button type="button" class="nd-btn danger" data-act="remove-confirm">Bỏ tên</button></div></div>';
    }
    const kind = [book.commodity, MODE[book.transport_mode], book.archived ? 'lưu trữ' : ''].filter(Boolean).join(' · ') || '—';
    return `<div class="kh-grid kh-row" data-id="${book.id}"><div class="kh-name"><a href="/so-khach-v7-live.html?customer=${encodeURIComponent(book.id)}">${esc(book.name)}</a></div>`
      + `<div class="kh-kind">${esc(kind)}</div><div class="kh-names">${namesHtml(book)}</div></div>`;
  }

  function drawBooks() {
    const query = fold($('book-search').value.trim());
    const all = books();
    const shown = query ? all.filter(book => fold(book.name).includes(query) || (book.booking_names ?? []).some(name => fold(name).includes(query))) : all;
    const named = all.filter(book => book.booking_names?.length).length;
    $('book-count').textContent = `${all.length} sổ · ${named} sổ có tên booking`;
    $('books').innerHTML = shown.length ? shown.map(bookHtml).join('') : `<p class="nd-empty">${query ? 'Không có sổ hay tên booking nào khớp.' : 'Chưa có sổ nào.'}</p>`;
    // Đọc lại giữa lúc hộp tạo sổ đang mở (mất mạng rồi bấm lại): giữ mặt hàng đang chọn, không thì lần bấm lại gửi nội dung khác.
    const select = $('create-commodity'), keep = select.value;
    select.innerHTML = '<option value="">Chưa gán</option>' + catalog().map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join('');
    select.value = catalog().includes(keep) ? keep : '';
    const input = document.querySelector('.kh-add-box input');
    if (input) input.focus();
  }

  function lock() {
    document.querySelectorAll('.kh button, .kh select, .kh input, .kh textarea').forEach(control => { control.disabled = busy; });
  }

  function draw() {
    drawOwners();
    drawBooks();
    if (busy) lock();   // vẽ lại lúc đang gửi (đọc lại sau khi ghi): nút mới vẽ cũng phải khóa, không thì bấm mà không có gì xảy ra
  }

  async function load() {
    try {
      const body = await CongNoNet.fetchJson(URL_DATA, { what: 'danh sách khách' });
      if (!body || !Array.isArray(body.customers)) throw Error('Không đọc được danh sách khách.');
      data = body;
      fail('');
      draw();
    } catch (error) {
      fail(CongNoNet.messageOf(error, 'Không đọc được danh sách khách.'), true);
      if (!data) $('owners').innerHTML = '';
    }
  }

  function setBusy(on) {
    busy = on;
    lock();
  }

  // Gửi một lệnh; đọc lại và vẽ xong rồi mới báo "Đã …". Máy chủ từ chối rõ (4xx) thì bỏ khóa: không có gì được ghi. Mất mạng, máy
  // chủ lỗi (5xx) hay khóa đã dùng cho nội dung khác thì chưa rõ đã ghi chưa: giữ khóa, người gọi đọc lại danh sách trước khi báo.
  async function post(url, body, key, done) {
    let response;
    try {
      response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    } catch {
      throw Object.assign(Error('Mất kết nối tới máy chủ.'), { unknown: true });
    }
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      const unknown = response.status >= 500 || result?.error === 'IDEMPOTENCY_CONFLICT';
      if (!unknown) keys.delete(key);
      throw Object.assign(Error(result?.message || 'Chưa lưu được. Thử lại sau.'), { server: !unknown, unknown, code: result?.error });
    }
    keys.delete(key);
    pending = null;
    fail('');
    flash('');
    await load();
    flash(typeof done === 'function' ? done(result) : done);
    return result;
  }

  async function setName(bookId, name, remove, done) {
    if (busy) return false;
    const intent = `${bookId}|${name}|${remove}`;
    const key = keys.get(intent) ?? newKey();
    keys.set(intent, key);
    setBusy(true);
    try {
      const events = await CongNoNet.fetchJson(`/api/v7/ledger/events?customer=${encodeURIComponent(bookId)}`, { what: 'phiên bản sổ' });
      await post('/api/v7/admin/booking-names', { customer_id: bookId, expected_version: events.version, idempotency_key: key, name, remove }, key, done);
      return true;
    } catch (error) {
      if (error.unknown) await load();
      fail(error.server ? error.message : error.unknown ? UNKNOWN : 'Mất kết nối tới máy chủ. Bấm lại để thử; lệnh không ghi hai lần.');
      return false;
    } finally {
      setBusy(false);
      if (pending) draw();
    }
  }

  function openCreate(owner = null) {
    pending = null;
    draw();
    $('create-form').reset();
    createError('');
    createKey = null;
    if (owner) {
      // Tab Sheet chưa có sổ: điền đúng tên sổ máy sẽ tạo cho tab đó (bỏ các dấu file xuất không nhận), để máy đối soát ghép đúng sổ.
      const tab = owner.sheet_tabs?.find(item => item.customer_id === null);
      $('create-name').value = tab?.book_name ?? tab?.tab ?? owner.name;
      document.querySelector(`input[name="create-mode"][value="${owner.family === 'BO' ? 'BO' : 'CANG'}"]`).checked = true;
      $('create-commodity').value = catalogName(owner.commodities?.[0]);
      $('create-booking').value = owner.name;
    }
    flash('');
    dialog.showModal();
    $('create-name').focus();
  }

  $('owners').addEventListener('click', event => {
    const button = event.target.closest('button[data-act]');
    const row = button?.closest('.kh-owner');
    if (!row || busy) return;
    const owner = (data.unmapped?.owners ?? []).find(item => ownerId(item) === row.dataset.owner);
    const act = button.dataset.act;
    if (act === 'assign') {
      const book = Number(row.querySelector('.kh-pick').value);
      if (!book) { fail('Chọn sổ để gán tên trước.'); row.querySelector('.kh-pick').focus(); return; }
      fail('');
      pending = { kind: 'assign', owner: row.dataset.owner, book, name: owner.name };
      drawOwners();
      document.querySelector('.kh-owner.kh-ask .primary')?.focus();
    } else if (act === 'assign-confirm' && pending?.kind === 'assign') {
      const { book, name } = pending;
      setName(book, name, false, `Đã gán ${name} vào sổ ${bookById(book)?.name ?? ''}. Chuyến sẽ vào sổ ở lượt máy sau.`);
    } else if (act === 'create') openCreate(owner);
    else if (act === 'cancel') { pending = null; drawOwners(); }
  });

  $('books').addEventListener('click', event => {
    const button = event.target.closest('button[data-act]');
    const row = button?.closest('.kh-row');
    if (!row || busy) return;
    const book = bookById(Number(row.dataset.id));
    const act = button.dataset.act;
    if (act === 'add') { pending = { kind: 'add', book: book.id }; fail(''); drawBooks(); }
    else if (act === 'add-confirm') {
      const name = upperName(row.querySelector('.kh-add-box input').value);
      if (!name) { fail('Gõ tên chủ hàng như trên booking.'); return; }
      setName(book.id, name, false, `Đã gán ${name} vào sổ ${book.name}.`);
    } else if (act === 'ask-remove') { pending = { kind: 'remove', book: book.id, name: button.dataset.name }; fail(''); drawBooks(); document.querySelector('.kh-row.kh-ask .danger')?.focus(); }
    else if (act === 'remove-confirm' && pending?.kind === 'remove') setName(book.id, pending.name, true, `Đã bỏ tên ${pending.name} khỏi sổ ${book.name}.`);
    else if (act === 'cancel') { pending = null; drawBooks(); }
  });
  for (const id of ['owners', 'books']) {
    $(id).addEventListener('keydown', event => {
      if (busy) return;
      if (event.target.matches('.kh-add-box input') && event.key === 'Enter') event.target.closest('.kh-add-box').querySelector('[data-act="add-confirm"]').click();
      if (event.key === 'Escape' && pending) { pending = null; draw(); }
    });
  }
  $('book-search').addEventListener('input', () => { if (pending?.kind !== 'assign') pending = null; drawBooks(); });

  $('create-open').addEventListener('click', () => openCreate());
  // Đang gửi thì không đóng hộp (Esc, nút đóng, bấm ra ngoài): kết quả hay lỗi phải hiện trong chính hộp này.
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('click', event => {
    if (busy) return;
    if (event.target.closest('[data-close]') || event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => { createError(''); $('create-open').focus(); });
  $('create-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const book = $('create-name').value.normalize('NFC').trim().replace(/\s+/g, ' ');
    if (!book) { createError('Gõ tên sổ.'); $('create-name').focus(); return; }
    const names = [...new Set($('create-booking').value.split(/\n/).map(upperName).filter(Boolean))];
    if (names.length > 20) { createError('Tối đa 20 tên trên booking.'); return; }
    const mode = document.querySelector('input[name="create-mode"]:checked').value;
    const commodity = $('create-commodity').value;
    createKey = createKey ?? newKey();
    setBusy(true);
    try {
      await post(URL_DATA, { book_name: book, commodity: commodity || null, transport_mode: mode, booking_names: names, idempotency_key: createKey },
        createKey, result => `Đã tạo sổ ${result?.name ?? book}.${names.length ? ' Chuyến booking của tên đã gán sẽ vào sổ ở lượt máy sau.' : ''}`);
      createKey = null;
      dialog.close();
    } catch (error) {
      if (error.server) createKey = null;
      if (error.unknown) await load();
      createError(error.server ? error.message
        : error.code === 'IDEMPOTENCY_CONFLICT' ? 'Lần bấm trước có thể đã tạo sổ (nội dung lúc đó khác bây giờ). Đã đọc lại danh sách sổ: xem lại; muốn tạo sổ khác thì đóng hộp này rồi mở lại.'
          : 'Mất kết nối hoặc máy chủ lỗi, chưa rõ sổ đã tạo chưa. Đã đọc lại danh sách sổ: xem lại; bấm Tạo sổ lần nữa thì không tạo hai sổ.');
    } finally {
      setBusy(false);
    }
  });
  $('refresh-data').addEventListener('click', () => { flash(''); load(); });

  load();
})();
