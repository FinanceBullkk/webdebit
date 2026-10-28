/* Nút "↻ Làm mới" đọc Sheet ngay (specs/v7-sheet-refresh.md). Dùng chung cho sổ khách và Tổng quan.
   Chỉ hỏi/gửi yêu cầu; server không trả số tiền ở đây. Server chưa bật tính năng thì trang giữ chữ cũ. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SheetRefresh = api;
}(typeof self !== 'undefined' ? self : this, function () {
  const POLL_MS = 5000;
  const clock = iso => new Date(iso).toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit' });

  // Chữ cạnh nút cho từng trạng thái; null nghĩa là để trang tự ghi như cũ.
  function label(status, asked) {
    if (!status || status.state === 'unavailable') return null;
    const at = status.sheet_at ? clock(status.sheet_at) : null;
    if (status.state === 'running') return { text: 'Đang lấy từ Sheet… (khoảng 1 phút)', busy: true };
    if (status.state === 'failed') return { text: at ? `Chưa lấy được từ Sheet, đang dùng bản lúc ${at}` : 'Chưa lấy được từ Sheet', error: true };
    if (!at) return null;
    if (asked && status.recent) return { text: `Sheet vừa lấy lúc ${at}` };
    return { text: `Sheet lúc ${at} · tự tải mỗi 60 giây` };
  }

  function create({ node, button, onDone = () => {}, fetcher = fetch, timers = { setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: id => clearTimeout(id) } }) {
    let status = null;
    let asked = false;
    let timer = null;

    function paint() {
      const view = label(status, asked);
      if (!view || !node) return;
      node.replaceChildren();
      if (view.busy) {
        const spin = document.createElement('span');
        spin.className = 'sheet-spin';
        spin.setAttribute('aria-hidden', 'true');
        node.append(spin);
      }
      node.append(view.text);
      node.classList.toggle('sheet-busy', !!view.busy);
      node.classList.toggle('sheet-error', !!view.error);
      button?.setAttribute('aria-busy', view.busy ? 'true' : 'false');
    }

    async function call(method) {
      try {
        const response = await fetcher('/api/v7/sheet/refresh', method === 'POST'
          ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', cache: 'no-store' }
          : { cache: 'no-store' });
        return response.ok ? await response.json() : null;
      } catch { return null; }
    }

    async function apply(next) {
      const wasRunning = status?.state === 'running';
      if (next) status = next;
      else if (asked && wasRunning) status = { ...status, state: 'failed' };
      timers.clearTimeout(timer);
      timer = null;
      if (status?.state === 'running') timer = timers.setTimeout(() => { load(); }, POLL_MS);
      else if (wasRunning && status?.state === 'idle') await onDone();
      paint();
    }

    async function load() { await apply(await call('GET')); }

    // Bấm tay: gửi yêu cầu, rồi hỏi lại 5 giây một lần tới khi xong.
    async function trigger() {
      if (status?.state === 'running') { paint(); return; }
      asked = true;
      const next = await call('POST');
      if (!next && status && status.state !== 'unavailable') status = { ...status, state: 'failed' };
      await apply(next);
    }

    return { load, trigger, paint, status: () => status };
  }

  return { create, label };
}));
