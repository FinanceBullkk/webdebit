/* Bộ chọn tháng trên thanh đầu Tổng quan (KHACH-THANG-01, audit 28/11/2026: hai nút ‹ › không chữ trong thẻ Thu tháng khó thấy
 * và nói sai phạm vi; người dùng chọn đặt ở thanh đầu trang). Một nút có chữ "Tất cả tháng" / "Tháng 10/2026" mở bảng 12 tháng
 * của một năm để chọn thẳng; ‹ › hai bên lùi/tiến một tháng; × bỏ lọc. Chỉ vẽ và báo tháng được chọn; lọc, tải số và địa chỉ
 * trang do dashboard-v7.js lo.
 *
 *   const picker = TongQuanChonThang.create({ node, read, pick });
 *   read() → { month: 'yyyy-mm' | null, current: 'yyyy-mm', ready: boolean }; pick('yyyy-mm' | null); picker.paint()
 */
globalThis.TongQuanChonThang = (() => {
  'use strict';
  const MIN_YEAR = 2020;
  const svg = body => `<svg viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
  const ICON = {
    calendar: svg('<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>'),
    prev: svg('<path d="M15 6l-6 6 6 6"/>'), next: svg('<path d="M9 6l6 6-6 6"/>'),
    down: svg('<path d="M7 10l5 5 5-5"/>'), close: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
  };
  const shift = (key, by) => {
    const at = new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) - 1 + by, 1));
    return `${at.getUTCFullYear()}-${String(at.getUTCMonth() + 1).padStart(2, '0')}`;
  };
  // Nhãn dựng từ số: tháng có thể đến từ ?thang= của địa chỉ.
  const long = key => `Tháng ${Number(key.slice(5, 7))}/${Number(key.slice(0, 4))}`;
  const short = key => `T${Number(key.slice(5, 7))}/${Number(key.slice(0, 4))}`;

  function create({ node, read, pick }) {
    let open = false, year = null;
    const close = refocus => {
      if (!open) return;
      open = false; paint();
      if (refocus) node.querySelector('.mp-main')?.focus();
    };

    function paint() {
      const { month, current, ready } = read();
      if (!current) { node.innerHTML = ''; return; }
      const off = ready ? '' : ' disabled';
      const shown = year ?? Number((month ?? current).slice(0, 4));
      const label = month ? long(month) : 'Tất cả tháng';
      const grid = Array.from({ length: 12 }, (_, i) => {
        const key = `${shown}-${String(i + 1).padStart(2, '0')}`;
        return `<button type="button" class="mp-cell" data-pick="${key}" aria-pressed="${key === month}"${key > current ? ' disabled' : ''}>T${i + 1}</button>`;
      }).join('');
      const pop = !open ? '' : `<div class="mp-pop" role="dialog" aria-label="Chọn tháng">`
        + `<div class="mp-year"><button type="button" data-year="-1" aria-label="Năm trước"${shown <= MIN_YEAR ? ' disabled' : ''}>${ICON.prev}</button>`
        + `<b>${shown}</b><button type="button" data-year="1" aria-label="Năm sau"${shown >= Number(current.slice(0, 4)) ? ' disabled' : ''}>${ICON.next}</button></div>`
        + `<div class="mp-grid">${grid}</div>`
        + `<button type="button" class="mp-all" data-pick=""${month ? '' : ' aria-pressed="true"'}>Tất cả tháng</button></div>`;
      node.innerHTML = `<div class="mp${month ? ' on' : ''}" role="group" aria-label="Lọc cả trang theo tháng">`
        + `<button type="button" class="mp-step" data-step="-1" aria-label="Tháng trước"${off}>${ICON.prev}</button>`
        + `<button type="button" class="mp-main" aria-haspopup="dialog" aria-expanded="${open}"${off} title="Lọc cả trang theo tháng">${ICON.calendar}`
        + `<span class="mp-long">${label}</span><span class="mp-short">${month ? short(month) : 'Tháng'}</span>${ICON.down}</button>`
        + (month ? `<button type="button" class="mp-clear" aria-label="Bỏ lọc ${long(month)}"${off}>${ICON.close}</button>` : '')
        + `<button type="button" class="mp-step" data-step="1" aria-label="Tháng sau"${!ready || !month || month >= current ? ' disabled' : ''}>${ICON.next}</button>`
        + `${pop}</div>`;
      // Mở bảng: tiêu điểm vào tháng đang lọc, không có thì tháng hiện tại (năm khác thì ô đầu còn bấm được).
      if (open) (node.querySelector('.mp-cell[aria-pressed="true"]') ?? node.querySelector(`.mp-cell[data-pick="${current}"]`)
        ?? node.querySelector('.mp-cell:not(:disabled)'))?.focus();
    }

    node.addEventListener('click', event => {
      const target = event.target.closest('button');
      if (!target || target.disabled) return;
      const { month, current } = read();
      if (target.matches('.mp-main')) { open = !open; year = null; paint(); return; }
      if (target.matches('.mp-clear')) { open = false; pick(null); return; }
      if (target.dataset.step) {
        // Đang xem tất cả tháng: ‹ là tháng hiện tại; › không vượt tháng hiện tại.
        const next = month ? shift(month, Number(target.dataset.step)) : current;
        if (next <= current) { open = false; pick(next); }
        return;
      }
      if (target.dataset.year) { year = (year ?? Number((month ?? current).slice(0, 4))) + Number(target.dataset.year); paint(); return; }
      if (target.dataset.pick != null) { open = false; year = null; pick(target.dataset.pick || null); node.querySelector('.mp-main')?.focus(); }
    });
    node.addEventListener('keydown', event => { if (event.key === 'Escape' && open) { event.preventDefault(); close(true); } });
    // Bấm ra ngoài thì đóng. Xét đường đi của sự kiện: nút vừa bấm có thể đã bị vẽ lại (không còn trong node) khi sự kiện tới đây.
    document.addEventListener('click', event => { if (open && !event.composedPath().includes(node)) close(false); });
    return { paint };
  }

  return { create };
})();
