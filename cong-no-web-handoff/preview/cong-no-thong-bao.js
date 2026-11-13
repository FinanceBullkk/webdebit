/* Thông báo nổi dùng chung (THONG-BAO-01, specs/v7-thong-bao.md): thay băng vàng ở đầu sổ.
 * Một thông báo một lúc, góc dưới bên trái vùng trang, nằm ngoài #app nên vẽ lại sổ không làm nó nháy hay mất.
 * Loại theo câu: "Đã …" không kèm lưu ý → xong, tự tắt sau 5–12 giây theo độ dài (rê chuột hoặc tab vào thì dừng đếm);
 * "Đã …" kèm lưu ý (chưa, không tải được, trùng, chờ kiểm…) → cần xem; câu "Không … được", "Chưa rõ …" → lỗi; câu khác
 * (bị chặn, sổ vừa đổi) → cần xem. Cần xem và lỗi giữ tới khi bấm × hoặc Esc. Không lấy tiêu điểm khi hiện để không cắt ngang ô đang gõ.
 * Chữ nằm ở .live-notice (giữ tên cũ cho test và trình đọc màn hình); tắt chỉ ẩn, chữ còn tới lần báo sau. */
(() => {
  'use strict';
  const ERROR = /^(Không|Chưa rõ|Lỗi)|không (lưu|tải|ghi|duyệt|đọc|giữ|đính|tách)[^.]* được|không hợp lệ/i;
  const CAVEAT = /chưa|không (lưu|tải|ghi|duyệt|đọc|giữ|đính|tách)|trùng|chờ kiểm|tải lại|lệch|thiếu/i;
  const kindOf = text => /^Đã\s/.test(text) ? (CAVEAT.test(text) ? 'warn' : 'ok') : ERROR.test(text) ? 'error' : 'warn';
  const ICONS = {
    ok: '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="m8 12.5 2.7 2.7L16.2 9.6"/>',
    warn: '<path d="M10.3 4.2 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
    error: '<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"/><path d="M12 7.5v5.5M12 16.5h.01"/>',
  };
  const svg = paths => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  let host = null, box = null, timer = 0, left = 0, started = 0, paused = false;

  function build() {
    if (host || typeof document.createElement !== 'function' || !document.body) return host;
    host = document.createElement('div');
    host.className = 'cn-toast-host';
    host.setAttribute('aria-live', 'polite');
    host.hidden = true;
    host.innerHTML = '<div class="cn-toast" role="status"><span class="cn-toast-icon"></span><p class="cn-toast-text live-notice"></p>'
      + `<button type="button" class="cn-toast-close" aria-label="Đóng thông báo" title="Đóng">${svg('<path d="M6 6l12 12M18 6 6 18"/>')}</button>`
      + '<span class="cn-toast-timer" aria-hidden="true"></span></div>';
    document.body.append(host);
    box = host.firstElementChild;
    box.querySelector('.cn-toast-close').addEventListener('click', hide);
    box.addEventListener('keydown', event => { if (event.key === 'Escape') { event.stopPropagation(); hide(); } });
    box.addEventListener('mouseenter', pause);
    box.addEventListener('mouseleave', resume);
    box.addEventListener('focusin', pause);
    box.addEventListener('focusout', event => { if (!box.contains(event.relatedTarget)) resume(); });
    return host;
  }
  function count(ms) {
    clearTimeout(timer);
    left = ms; started = Date.now();
    timer = setTimeout(hide, ms);
  }
  function pause() {
    if (paused || !left) return;
    paused = true;
    clearTimeout(timer);
    left = Math.max(1500, left - (Date.now() - started));
    box.classList.add('paused');
  }
  function resume() {
    if (!paused) return;
    paused = false;
    box.classList.remove('paused');
    count(left);
  }
  // Hiện một câu (thay câu đang hiện). Câu trống thì tắt.
  function show(text, options = {}) {
    const value = String(text ?? '').trim();
    if (!value) { hide(); return; }
    if (!build()) return;
    const kind = options.kind || kindOf(value);
    clearTimeout(timer);
    left = 0; paused = false;
    box.className = `cn-toast is-${kind}`;
    box.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    box.querySelector('.cn-toast-icon').innerHTML = svg(ICONS[kind]);
    box.querySelector('.live-notice').textContent = value;
    // Hiện lại từ đầu để hiệu ứng vào và thanh đếm chạy lại cả khi câu mới giống câu cũ.
    host.hidden = false;
    box.classList.remove('entering');
    void box.offsetWidth;
    box.classList.add('entering');
    if (kind === 'ok') {
      const ms = Math.min(12000, Math.max(5000, 3000 + value.length * 60));
      box.style.setProperty('--cn-toast-ms', `${ms}ms`);
      count(ms);
    }
  }
  function hide() {
    clearTimeout(timer);
    left = 0; paused = false;
    if (host) host.hidden = true;
  }
  window.CongNoThongBao = { show, hide, kindOf };
})();
