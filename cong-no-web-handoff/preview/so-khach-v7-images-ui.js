/* Sổ khách V7 bản live — ảnh chứng từ phiếu thu (CHUNG-TU-01, specs/v7-dan-chung-tu.md).
 * Dán (Ctrl+V), kéo thả hoặc chọn ảnh chuyển khoản; ảnh chỉ để đối chiếu, không đổi số tiền.
 * Nạp trước so-khach-v7-ui.js, dùng chung phạm vi của initLive qua ctx (hợp đồng: so-khach-v7-ctx.js). */
(window.SoKhachV7LiveParts ??= {}).images = ctx => {
  'use strict';
  const { root, api, customerId, escape, dateText, showNotice, submit } = ctx;
  const MAX_IMAGES = 5, MAX_EDGE = 2400, MAX_BYTES = 2 * 1024 * 1024;
  const TYPES = ['image/png', 'image/jpeg', 'image/webp'];
  const drafts = new Map();     // tháng "YYYY-MM" của hàng nhập → [{ url, b64, type, sha256, warning }]
  const problems = new Map();   // tháng → câu lỗi gần nhất của hàng nhập đó
  let saved = new Map();        // mã phiếu → [{ id, sha256, content_type }]
  let loadedVersion = null;
  const blobs = new Map();      // mã ảnh → object URL đã tải
  let view = null;              // { pid } phiếu đã ghi | { month } phiếu đang nhập; kèm index, zoom, removing
  let panel = null;

  const receiptOf = pid => (ctx.snapshot?.receipts ?? []).find(row => row.pid === pid);
  const isVoided = receipt => receipt?.voided_by_event != null;

  // Danh sách ảnh tải lại khi phiên bản sổ đổi; server cũ chưa có đường này thì coi như chưa có ảnh.
  ctx.imagesOnSnapshot = data => {
    if (!data || data.version === loadedVersion) return;
    loadedVersion = data.version;
    loadList();
  };
  async function loadList() {
    try {
      const response = await fetch(`/api/v7/receipt-images?customer=${encodeURIComponent(customerId)}`, { cache: 'no-store' });
      if (!response.ok) return;
      const data = await response.json();
      if (!Array.isArray(data?.images)) return;
      const next = new Map();
      for (const image of data.images) {
        if (!next.has(image.pid)) next.set(image.pid, []);
        next.get(image.pid).push(image);
      }
      // Chỉ vẽ lại khi ảnh thật sự đổi: vẽ lại cả sổ sẽ đóng các khung chi tiết đang mở (đối chiếu Sheet, CHỜ KIỂM).
      const ids = map => JSON.stringify([...map].map(([pid, list]) => [pid, list.map(image => image.id)]));
      if (ids(next) === ids(saved)) return;
      saved = next;
      ctx.redraw();
      renderView();
    } catch { /* giữ danh sách cũ; lần đọc sổ sau thử lại */ }
  }

  // Nút 📎 cạnh số tiền phiếu đã ghi (không áp cho khoản cấn trừ đi và khoản thu sổ gốc).
  ctx.imageClip = receipt => {
    if (!receipt?.pid || receipt.outgoing) return '';
    const count = saved.get(receipt.pid)?.length ?? 0;
    if (!count && isVoided(receipt)) return '';
    return count
      ? `<button type="button" class="image-clip" data-pid="${escape(receipt.pid)}" aria-label="Xem ${count} ảnh chứng từ phiếu ${escape(receipt.pid)}">📎 ${count}</button>`
      : `<button type="button" class="image-clip none" data-pid="${escape(receipt.pid)}" aria-label="Đính ảnh chứng từ cho phiếu ${escape(receipt.pid)}" title="Đính ảnh">＋📎</button>`;
  };

  // Chỗ dán ảnh trong khung nhập phiếu (trên nút Ghi phiếu): ảnh vừa dán, gợi ý cách dán, cảnh báo/lỗi.
  ctx.imageEntryBox = month => {
    const list = drafts.get(month) ?? [];
    const thumbs = list.map((item, index) => `<span class="image-thumb${view?.month === month && view.index === index ? ' on' : ''}"><button type="button" class="image-thumb-open" data-month="${escape(month)}" data-index="${index}" aria-label="Xem ảnh ${index + 1}"><img src="${escape(item.url)}" alt=""></button><button type="button" class="image-thumb-drop" data-month="${escape(month)}" data-index="${index}" aria-label="Bỏ ảnh ${index + 1} khỏi phiếu đang nhập">×</button></span>`).join('');
    const hint = list.length ? `${list.length}/${MAX_IMAGES} ảnh. Dán tiếp để thêm.` : '<b>📎 Ảnh chuyển khoản:</b> Ctrl+V hoặc kéo thả vào đây';
    const warnings = list.filter(item => item.warning).map(item => `<p class="image-warn" role="status">⚠ ${escape(item.warning)}</p>`).join('');
    const problem = problems.get(month);
    return `<div class="image-entry" data-month="${escape(month)}"><div class="image-drop">${thumbs}<span class="image-hint">${hint}</span><button type="button" class="image-pick">Chọn ảnh…</button><input type="file" class="image-file" accept="${TYPES.join(',')}" multiple hidden></div>${warnings}${problem ? `<p class="image-error" role="alert">${escape(problem)}</p>` : ''}</div>`;
  };

  // Tự cập nhật sổ tạm dừng khi còn ảnh chưa ghi hoặc khung xem đang mở.
  ctx.busyChecks.push(() => drafts.size > 0 || view !== null);

  function bytesToBase64(bytes) {
    let text = '';
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(text);
  }
  async function sha256(bytes) {
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  }
  // Nén nhẹ trước khi gửi: cạnh dài ≤ 2400 px (ảnh chụp màn hình điện thoại giữ nguyên cỡ), WebP 0,9; trình duyệt không có WebP thì JPEG.
  async function compress(file) {
    const url = URL.createObjectURL(file);
    try {
      const image = new Image();
      await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
      const scale = Math.min(1, MAX_EDGE / Math.max(image.naturalWidth, image.naturalHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
      const encode = type => new Promise(resolve => canvas.toBlob(resolve, type, 0.9));
      let blob = await encode('image/webp');
      if (blob?.type !== 'image/webp') blob = await encode('image/jpeg');
      if (!blob) throw Error('encode');
      return blob;
    } finally { URL.revokeObjectURL(url); }
  }
  async function prepare(file) {
    if (!TYPES.includes(file.type)) throw Error(`File "${file.name || 'vừa dán'}" không phải ảnh. Chỉ nhận ảnh PNG, JPG hoặc WebP.`);
    let blob;
    try { blob = await compress(file); } catch { throw Error('Không mở được ảnh này. Thử chụp màn hình lại rồi dán.'); }
    if (blob.size > MAX_BYTES) throw Error('Ảnh quá lớn kể cả sau khi nén (trên 2 MB). Cắt bớt phần thừa rồi dán lại.');
    const bytes = new Uint8Array(await blob.arrayBuffer());
    return { url: URL.createObjectURL(blob), b64: bytesToBase64(bytes), type: blob.type, sha256: await sha256(bytes) };
  }
  // Cảnh báo, không chặn: khách trả gộp hai sổ thì cùng một ảnh nằm ở hai phiếu.
  async function duplicateWarning(hash) {
    try {
      const response = await fetch(`/api/v7/receipt-images/find?sha256=${hash}`, { cache: 'no-store' });
      const matches = response.ok ? (await response.json())?.matches : null;
      if (!Array.isArray(matches) || !matches.length) return '';
      return matchText(matches);
    } catch { return ''; }
  }
  const matchText = matches => `Ảnh này đã đính vào ${matches.slice(0, 3).map(row =>
    `phiếu ${row.pid}${Number(row.customer_id) === customerId ? '' : ` của ${row.customer_name}`} ngày ${dateText(row.date)}${row.voided ? ' (đã hủy)' : ''}`).join(', ')}. Vẫn ghi được nếu khách trả gộp; kiểm lại để khỏi ghi trùng.`;

  async function addDrafts(month, files) {
    problems.delete(month);
    const list = drafts.get(month) ?? [];
    for (const file of files) {
      if (list.length >= MAX_IMAGES) { problems.set(month, `Mỗi phiếu tối đa ${MAX_IMAGES} ảnh. Bỏ bớt ảnh rồi dán lại.`); break; }
      try {
        const item = await prepare(file);
        if (list.some(other => other.sha256 === item.sha256)) { URL.revokeObjectURL(item.url); problems.set(month, 'Ảnh này đã có trong phiếu đang nhập.'); continue; }
        item.warning = await duplicateWarning(item.sha256);
        list.push(item);
      } catch (error) { problems.set(month, error.message); }
    }
    if (list.length) drafts.set(month, list);
    if (list.length) view = { month, index: list.length - 1, zoom: false };
    ctx.redraw();
    renderView();
  }
  async function attachSaved(pid, files) {
    if (isVoided(receiptOf(pid))) { showNotice('Phiếu đã hủy, không đính thêm ảnh được.'); return; }
    for (const file of files) {
      if ((saved.get(pid)?.length ?? 0) >= MAX_IMAGES) { showNotice(`Phiếu ${pid} đã đủ ${MAX_IMAGES} ảnh.`); return; }
      let item;
      try { item = await prepare(file); } catch (error) { showNotice(error.message); return; }
      URL.revokeObjectURL(item.url);
      const done = await send(pid, item);
      if (!done) return;
      showNotice(done.duplicates?.length ? `Đã đính ảnh vào phiếu ${pid}. ${matchText(done.duplicates)}` : `Đã đính ảnh vào phiếu ${pid}.`);
    }
  }
  // Một lệnh đính ảnh; trả kết quả server khi đã lưu, null khi lỗi (submit đã hiện câu lỗi).
  async function send(pid, item) {
    await submit('imageAttach', { pid, content_type: item.type, data_base64: item.b64 });
    const outcome = api.lastOutcome();
    return outcome?.status === 'saved' ? outcome.result : null;
  }

  // Ghi phiếu xong (so-khach-v7-edit-ui.js gọi): đính lần lượt các ảnh đã dán ở hàng nhập của tháng đó.
  ctx.afterReceiptSaved = async (month, pid) => {
    const list = drafts.get(month);
    if (!list?.length || !pid) return;
    drafts.delete(month);
    problems.delete(month);
    if (view?.month === month) view = null;
    let stored = 0;
    const warnings = [];
    for (const item of list) {
      const done = await send(pid, item);
      URL.revokeObjectURL(item.url);
      if (!done) break;
      stored += 1;
      if (done.duplicates?.length) warnings.push(matchText(done.duplicates));
    }
    renderView();
    const missing = list.length - stored;
    showNotice(missing
      ? `Phiếu ${pid} đã ghi đúng số tiền, nhưng còn ${missing} ảnh chưa lưu. Bấm 📎 của phiếu ${pid} rồi dán lại ảnh.`
      : `Đã ghi phiếu ${pid} kèm ${stored} ảnh.${warnings.length ? ` ${warnings[0]}` : ''}`);
  };

  // ---- Khung xem ảnh: đè lên vùng chuyến, cạnh danh sách phiếu thu ----
  function images() {
    if (!view) return [];
    return view.pid ? saved.get(view.pid) ?? [] : drafts.get(view.month) ?? [];
  }
  async function imageUrl(image) {
    if (image.url) return image.url;
    if (blobs.has(image.id)) return blobs.get(image.id);
    const response = await fetch(`/api/v7/receipt-image?customer=${encodeURIComponent(customerId)}&id=${encodeURIComponent(image.id)}`, { cache: 'no-store' });
    const data = response.ok ? await response.json() : null;
    if (!data?.data_base64 || !TYPES.includes(data.content_type)) throw Error('image');
    const bytes = Uint8Array.from(atob(data.data_base64), char => char.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: data.content_type }));
    blobs.set(image.id, url);
    return url;
  }
  function renderView() {
    if (!view) { if (panel) panel.hidden = true; return; }
    if (!panel) {
      panel = document.createElement('aside');
      panel.className = 'image-viewer';
      panel.setAttribute('role', 'dialog');
      panel.setAttribute('aria-label', 'Xem ảnh chứng từ');
      document.body.append(panel);
      panel.addEventListener('click', onPanelClick);
      panel.addEventListener('keydown', event => { if (event.key === 'Enter' && event.target.matches('.image-reason')) { event.preventDefault(); confirmRemove(); } });
    }
    const list = images();
    if (view.index >= list.length) view.index = Math.max(0, list.length - 1);
    const receipt = view.pid ? receiptOf(view.pid) : null;
    const voided = isVoided(receipt);
    const title = view.pid ? `Phiếu ${view.pid}${voided ? ' (đã hủy)' : ''}` : 'Phiếu đang nhập';
    const foot = voided ? 'Phiếu đã hủy: chỉ xem ảnh, không đính thêm.'
      : `Ảnh chỉ để đối chiếu, web không đọc số. Ảnh RMB: Số tiền ghi <b>VND thực nhận</b>, RMB và tỷ giá ghi ở Tham chiếu.${view.pid ? ' Khung này đang mở: bấm Ctrl+V để <b>đính thêm ảnh vào phiếu này</b>.' : ''}`;
    panel.hidden = false;
    panel.innerHTML = `<div class="image-viewer-bar"><strong>${escape(title)}${list.length ? ` · ảnh ${view.index + 1}/${list.length}` : ''}</strong>
      <button type="button" class="image-prev" aria-label="Ảnh trước" ${view.index > 0 ? '' : 'disabled'}>‹</button>
      <button type="button" class="image-next" aria-label="Ảnh sau" ${view.index < list.length - 1 ? '' : 'disabled'}>›</button>
      <button type="button" class="image-zoom">${view.zoom ? 'Vừa khung' : 'Phóng to'}</button>
      ${view.pid && !voided && list.length ? '<button type="button" class="image-remove-open danger">Gỡ ảnh</button>' : ''}
      <button type="button" class="image-close">Đóng</button></div>
      <div class="image-viewer-body${view.zoom ? ' zoom' : ''}">${list.length ? '<p class="image-loading">Đang tải ảnh…</p><img alt="Ảnh chứng từ" hidden>' : `<p class="image-empty">Phiếu chưa có ảnh.${voided ? '' : ' Bấm Ctrl+V hoặc kéo thả ảnh vào khung này.'}</p>`}</div>
      ${view.removing ? '<div class="image-remove"><label>Lý do gỡ ảnh (bắt buộc) <input class="image-reason" maxlength="200" placeholder="Ví dụ: đính nhầm ảnh của khách khác"></label><span class="image-reason-error" role="alert"></span><div class="image-remove-actions"><button type="button" class="image-remove-cancel">Thôi</button><button type="button" class="image-remove-confirm danger">Gỡ ảnh</button></div></div>' : ''}
      <p class="image-viewer-foot">${foot}</p>`;
    if (view.removing) panel.querySelector('.image-reason').focus();
    const image = list[view.index];
    if (!image) return;
    const shown = view;
    imageUrl(image).then(url => {
      if (view !== shown || !panel) return;
      const img = panel.querySelector('.image-viewer-body img');
      if (!img) return;
      img.src = url; img.hidden = false;
      panel.querySelector('.image-loading')?.remove();
    }).catch(() => {
      const loading = panel?.querySelector('.image-loading');
      if (loading && view === shown) loading.textContent = 'Không tải được ảnh. Đóng rồi mở lại.';
    });
  }
  function closeView() { view = null; renderView(); ctx.redraw(); }
  async function confirmRemove() {
    const reason = panel.querySelector('.image-reason')?.value.trim();
    if (!reason) { panel.querySelector('.image-reason-error').textContent = 'Cần ghi lý do trước khi gỡ.'; panel.querySelector('.image-reason').focus(); return; }
    const image = images()[view.index];
    await submit('imageRemove', { image_id: image.id, reason });
    if (api.lastOutcome()?.status !== 'saved') return;
    view = { ...view, removing: false };
    showNotice(`Đã gỡ 1 ảnh khỏi phiếu ${view.pid}. Ảnh không bị xóa hẳn, xem lại trong Lịch sử.`);
  }
  function onPanelClick(event) {
    const button = event.target.closest('button');
    if (!button || !view) return;
    if (button.matches('.image-close')) closeView();
    else if (button.matches('.image-prev')) { view = { ...view, index: view.index - 1, removing: false }; renderView(); }
    else if (button.matches('.image-next')) { view = { ...view, index: view.index + 1, removing: false }; renderView(); }
    else if (button.matches('.image-zoom')) { view = { ...view, zoom: !view.zoom }; renderView(); }
    else if (button.matches('.image-remove-open')) { view = { ...view, removing: true }; renderView(); }
    else if (button.matches('.image-remove-cancel')) { view = { ...view, removing: false }; renderView(); }
    else if (button.matches('.image-remove-confirm')) confirmRemove();
  }

  // Ảnh dán vào đâu: khung xem của phiếu đã ghi đang mở thì vào phiếu đó; còn lại vào hàng nhập của tháng
  // đang đứng (ô đang chọn), không có thì tháng hiện tại.
  function entryMonth(node) {
    const row = node?.closest?.('.image-entry');
    if (row) return row.dataset.month;
    const section = node?.closest?.('section[id^="thang-"]');
    if (section && root.querySelector(`#${section.id} .image-entry`)) return section.id.slice(6);
    if (view?.month) return view.month;
    const today = String(ctx.snapshot?.today_month ?? '').slice(0, 7);
    const rows = [...root.querySelectorAll('.image-entry')];
    return (rows.find(item => item.dataset.month === today) ?? rows.at(-1))?.dataset.month ?? null;
  }
  function take(files, node) {
    if (!files.length) return false;
    if (view?.pid && (!node || panel?.contains(node) || !node.closest?.('.image-entry'))) { attachSaved(view.pid, files); return true; }
    const month = entryMonth(node);
    if (!month) { showNotice('Khách chưa có số dư đầu hiệu lực. Chưa thể ghi.'); return true; }
    addDrafts(month, files);
    return true;
  }
  if (typeof document.addEventListener === 'function') {
    document.addEventListener('paste', event => {
      const files = [...(event.clipboardData?.files ?? [])];
      if (!files.length) return;   // dán chữ vào ô nhập vẫn như thường
      event.preventDefault();
      take(files, document.activeElement);
    });
    document.addEventListener('dragover', event => {
      if (!event.dataTransfer?.types?.includes('Files')) return;
      event.preventDefault();
      event.target.closest?.('.image-drop')?.classList.add('over');
    });
    document.addEventListener('dragleave', event => event.target.closest?.('.image-drop')?.classList.remove('over'));
    document.addEventListener('drop', event => {
      const files = [...(event.dataTransfer?.files ?? [])];
      if (!files.length) return;
      event.preventDefault();
      take(files, event.target);
    });
    document.addEventListener('keydown', event => {
      // Esc trong ô nhập ngoài khung xem giữ việc riêng của ô đó (bỏ sửa), không đóng khung.
      if (event.key === 'Escape' && view && !(event.target.matches?.('input,select,textarea') && !panel?.contains(event.target))) closeView();
    });
  }
  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.matches('.image-clip')) { view = { pid: button.dataset.pid, index: 0, zoom: false }; renderView(); ctx.redraw(); }
    else if (button.matches('.image-thumb-open')) { view = { month: button.dataset.month, index: Number(button.dataset.index), zoom: false }; renderView(); ctx.redraw(); }
    else if (button.matches('.image-thumb-drop')) {
      const list = drafts.get(button.dataset.month) ?? [];
      const [item] = list.splice(Number(button.dataset.index), 1);
      if (item) URL.revokeObjectURL(item.url);
      if (!list.length) drafts.delete(button.dataset.month);
      problems.delete(button.dataset.month);
      if (view?.month === button.dataset.month) view = list.length ? { ...view, index: Math.min(view.index, list.length - 1) } : null;
      renderView(); ctx.redraw();
    } else if (button.matches('.image-pick')) button.closest('.image-entry').querySelector('.image-file').click();
  });
  root.addEventListener('change', event => {
    if (!event.target.matches('.image-file') || !event.target.files.length) return;
    addDrafts(event.target.closest('.image-entry').dataset.month, [...event.target.files]);
  });
};
