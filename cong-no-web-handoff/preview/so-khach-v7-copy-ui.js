/* Sổ khách V7 bản live — chọn vùng ô và chép như Sheet (CHEP-O-01, specs/v7-chep-vung-o.md).
 * Bảng chuyến (table.trip-list): kéo chuột qua các ô, hoặc Shift+bấm, Shift+mũi tên để chọn một vùng chữ nhật; Ctrl+C chép vùng
 * (không có vùng thì chép ô đang đứng) thành chữ cách bằng Tab, mỗi hàng một dòng: dán vào Google Sheet hay Excel ra đúng ô.
 * Chỉ đọc chữ đang hiện, không gửi lệnh. Số tiền chép liền không dấu chấm (Sheet nào cũng đọc ra số); "–", "chưa có giá" chép
 * thành ô trống; Tuyến tách hai cột nơi đi, nơi đến như Sheet; chữ nhỏ (theo bảng, KHÁC…), nút và ô tick không chép. */
(window.SoKhachV7LiveParts ??= {}).copy = ctx => {
  'use strict';
  const { root, showNotice } = ctx;
  let range = null;      // { table, a: [hàng, cột], b: [hàng, cột] }; hàng tính trong rowsOf(table), cột là cellIndex
  let drag = null;       // đang giữ chuột trái: { table, at } ô bắt đầu
  let swallowClick = false;
  const EDGES = ['range-top', 'range-bottom', 'range-left', 'range-right'];

  // Hàng có ô trải nhiều cột (dòng hỏi, dòng "vừa chuyển") không phải hàng chuyến: không chọn, không chép.
  const rowsOf = table => [...table.tBodies].flatMap(body => [...body.rows]).filter(row => !row.querySelector(':scope > td[colspan]'));
  const cellOf = target => {
    const td = target?.closest?.('td');
    const table = td?.closest('table');
    return td && table?.matches('table.trip-list') && root.contains(table) && !td.hasAttribute('colspan') ? td : null;
  };
  const posOf = td => {
    const table = td.closest('table');
    const row = rowsOf(table).indexOf(td.parentElement);
    return row < 0 ? null : { table, at: [row, td.cellIndex] };
  };
  const live = () => range && range.table.isConnected ? range : null;
  const bounds = ({ a, b }) => [Math.min(a[0], b[0]), Math.max(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[1], b[1])];

  function paint() {
    root.querySelectorAll('td.cell-range').forEach(td => td.classList.remove('cell-range', ...EDGES));
    const now = live();
    if (!now) return;
    const [top, bottom, left, right] = bounds(now);
    rowsOf(now.table).slice(top, bottom + 1).forEach((row, index) => {
      for (let col = left; col <= Math.min(right, row.cells.length - 1); col++) {
        const td = row.cells[col];
        td.classList.add('cell-range');
        if (index === 0) td.classList.add('range-top');
        if (index === bottom - top) td.classList.add('range-bottom');
        if (col === left) td.classList.add('range-left');
        if (col === right) td.classList.add('range-right');
      }
    });
  }
  const clear = () => { if (range) { range = null; paint(); } };
  const setRange = (table, a, b) => { range = { table, a, b }; paint(); };

  // Chữ chép của một ô: bỏ nút, ô nhập, chữ nhỏ, chữ ẩn; số tiền "85.000.000" → "85000000".
  function clean(el) {
    const copy = el.cloneNode(true);
    copy.querySelectorAll('input,select,textarea,small,.fee-plus,.fee-dash,.cell-error,[aria-hidden="true"],button:not(.row-tag)').forEach(item => item.remove());
    const text = copy.textContent.replace(/\s+/g, ' ').trim();
    if (['–', '-', 'chưa có giá'].includes(text)) return '';
    return /^-?\d{1,3}(\.\d{3})+$/.test(text) ? text.replace(/\./g, '') : text;
  }
  function cellTexts(td) {
    if (td.matches('.route-cell')) {
      const parts = [...td.children].filter(item => !item.matches('.route-arrow'));
      if (parts.length === 2) return parts.map(clean);
    }
    return [clean(td)];
  }
  function textOf(table, [top, bottom, left, right]) {
    return rowsOf(table).slice(top, bottom + 1)
      .map(row => [...row.cells].slice(left, right + 1).flatMap(cellTexts).join('\t')).join('\n');
  }

  // ---- Chuột ----
  document.addEventListener('mousedown', event => {
    const td = event.button === 0 ? cellOf(event.target) : null;
    if (!td || event.target.closest('input,select,textarea,button,a')) { if (!event.shiftKey || !td) clear(); return; }
    const pos = posOf(td);
    if (!pos) { clear(); return; }
    if (event.shiftKey) {
      // Shift+bấm: mở rộng từ ô đầu vùng (hoặc ô đang đứng) tới ô bấm; không mở ô sửa, không bôi chữ.
      const now = live(), here = cellOf(document.activeElement), stand = here && posOf(here);
      const from = now?.table === pos.table ? now.a : stand?.table === pos.table ? stand.at : null;
      if (from) {
        event.preventDefault();
        swallowClick = true;
        setRange(pos.table, from, pos.at);
        return;
      }
    }
    clear();
    drag = pos;
  });
  root.addEventListener('mouseover', event => {
    if (!drag) return;
    if (!(event.buttons & 1)) { drag = null; return; }
    const td = cellOf(event.target);
    const pos = td && posOf(td);
    if (!pos || pos.table !== drag.table) return;
    const same = pos.at[0] === drag.at[0] && pos.at[1] === drag.at[1];
    if (same && !live()) return;
    drag.table.classList.add('range-dragging');
    window.getSelection?.()?.removeAllRanges();
    setRange(drag.table, drag.at, pos.at);
  });
  document.addEventListener('mouseup', () => {
    if (!drag) return;
    drag.table.classList.remove('range-dragging');
    const now = live();
    // Kéo rồi quay về đúng ô đầu: như bấm một ô, không giữ vùng.
    if (now && now.a[0] === now.b[0] && now.a[1] === now.b[1]) clear();
    drag = null;
  });
  // Shift+bấm đã chọn vùng: chặn lần bấm đó ở pha capture để ô không mở ô sửa (các phần khác nghe ở pha bubble).
  root.addEventListener('click', event => {
    if (!swallowClick) return;
    swallowClick = false;
    event.stopPropagation();
    event.preventDefault();
  }, true);

  // ---- Bàn phím: Shift+mũi tên mở rộng vùng, Esc bỏ vùng ----
  const STEP = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
  root.addEventListener('keydown', event => {
    if (event.target.matches?.('input:not([type="checkbox"]),select,textarea')) return;
    if (event.key === 'Escape' && live()) { event.preventDefault(); clear(); return; }
    if (!STEP[event.key] || !event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return;
    const here = cellOf(event.target);
    const pos = here && posOf(here);
    if (!pos) return;
    const now = live()?.table === pos.table ? live() : { table: pos.table, a: pos.at, b: pos.at };
    const rows = rowsOf(pos.table);
    const row = Math.max(0, Math.min(rows.length - 1, now.b[0] + STEP[event.key][0]));
    const col = Math.max(0, Math.min(rows[row].cells.length - 1, now.b[1] + STEP[event.key][1]));
    event.preventDefault();
    setRange(pos.table, now.a, [row, col]);
    rows[row].cells[col]?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  });

  // ---- Ctrl+C ----
  document.addEventListener('copy', event => {
    if (event.target.matches?.('input,select,textarea')) return;   // đang gõ trong ô: chép chữ đã bôi như thường
    const now = live();
    let text;
    if (now) text = textOf(now.table, bounds(now));
    else {
      const td = cellOf(document.activeElement);
      const pos = td && posOf(td);
      if (!pos || !window.getSelection?.()?.isCollapsed) return;   // có chữ đang bôi ngoài vùng: để trình duyệt chép
      text = textOf(pos.table, [pos.at[0], pos.at[0], pos.at[1], pos.at[1]]);
    }
    event.clipboardData.setData('text/plain', text);
    event.preventDefault();
    const lines = text.split('\n'), cols = lines[0].split('\t').length;   // Tuyến chép thành hai cột
    showNotice(lines.length * cols > 1 ? `Đã chép ${lines.length} hàng × ${cols} cột. Dán vào Sheet bằng Ctrl+V.` : 'Đã chép 1 ô.');
  });
};
