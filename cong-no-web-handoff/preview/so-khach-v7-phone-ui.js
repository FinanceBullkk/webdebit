/* Sổ khách V7 bản live — bảng chuyến trên điện thoại (DIEN-THOAI-CHUYEN-01, specs/v7-so-khach-dien-thoai.md).
 * Dưới 760px bảng chuyến chỉ hiện Ngày chuyến · Số container · Thành tiền (so-khach-v7-phone.css); bấm một hàng mở khung chi
 * tiết từ dưới lên. Khung đọc nguyên chữ đang hiện trong các ô của hàng đó, nhãn lấy từ hàng tiêu đề cột: không tính lại
 * tiền (ARCH-03). Trên điện thoại bảng chuyến chỉ để xem: bấm hàng không mở sửa ô, không xóa, không duyệt (trình nghe bắt
 * ở pha capture của #app, chặn trước mọi phần khác). Màn rộng không đổi: lớp đánh dấu chỉ có tác dụng trong @media. */
(window.SoKhachV7LiveParts ??= {}).phone = ctx => {
  'use strict';
  const { root, escape } = ctx;
  const QUERY = '(max-width: 760px)';
  const media = typeof matchMedia === 'function' ? matchMedia(QUERY) : null;
  const narrow = () => Boolean(media?.matches);
  // Hàng chuyến của bảng (sổ gốc, web, lệch Sheet đã nối) và hàng Sheet chưa vào sổ (chờ duyệt, lệch chưa nối).
  const ROWS = '.trip-card .trip-list tr[data-row], .trip-card tr.sheet-new, .trip-card tr.sheet-conflict:not([data-row])';
  const TAGS = { chua: 'Chưa có giá', duyet: 'Chờ duyệt', khac: 'Sheet khác' };

  let sheet = null;
  let openKey = null;
  let returnFocus = null;

  const card = () => root.querySelector?.('#the-so .trip-card') ?? null;
  const labelsOf = box => [...box.querySelectorAll('.ledger-head th')].map(th => th.textContent.trim());
  const keyOf = row => row.dataset.row ? `row:${row.dataset.row}` : row.dataset.sheetNew ? `sheet:${row.dataset.sheetNew}` : null;
  const findRow = key => [...(card()?.querySelectorAll('tr.ph-row') ?? [])].find(row => keyOf(row) === key) ?? null;
  const statusOf = row => row.classList.contains('sheet-new') ? 'duyet'
    : row.classList.contains('sheet-conflict') && !row.dataset.row ? 'khac'
      : row.querySelector('td.missing') ? 'chua' : null;
  // Chữ của một ô như đang hiện, bỏ nhãn phụ (gợi ý giá, nhãn Sheet), nút và ô chọn.
  const textOf = td => {
    if (!td) return '–';
    const sum = td.querySelector('.fee-sum');
    if (sum) return sum.textContent.trim();
    const copy = td.cloneNode(true);
    for (const node of copy.querySelectorAll('small, button, input, .fee-plus, .fee-dash, .ph-tag')) node.remove();
    return copy.textContent.replace(/\s+/g, ' ').trim() || '–';
  };

  // Sau mỗi lần vẽ: đánh dấu ba ô của mỗi hàng chuyến, nhãn trạng thái ở cột Thành tiền, nhãn dòng cộng; khung đang mở thì đọc lại.
  function phoneAfterRender() {
    const box = card();
    if (!box) { close(false); return; }
    const labels = labelsOf(box);
    const marks = [['ph-date', labels.indexOf('Ngày chuyến')], ['ph-cont', labels.indexOf('Số container')], ['ph-amt', labels.length - 1]];
    if (marks.some(([, index]) => index < 0)) return;
    const heads = box.querySelectorAll('.ledger-head th');
    for (const [name, index] of marks) heads[index]?.classList.add(name);
    for (const row of box.querySelectorAll(ROWS)) {
      if (row.cells.length !== labels.length) continue;
      row.classList.add('ph-row');
      for (const [name, index] of marks) row.cells[index].classList.add(name);
      const status = statusOf(row);
      if (status) {
        // Nội dung cũ của ô (dấu –, nút Duyệt) bọc lại để chỉ ẩn trên điện thoại; trình đọc màn hình chỉ đọc nhãn.
        const amount = row.cells[labels.length - 1];
        const original = document.createElement('span');
        original.className = 'ph-orig';
        original.append(...amount.childNodes);
        amount.append(original);
        row.classList.add('ph-tagged');
        amount.insertAdjacentHTML('beforeend', `<span class="ph-tag ${status}">${TAGS[status]}</span>`);
      }
    }
    box.querySelector('tr.subtotal > td')?.insertAdjacentHTML('afterbegin', '<span class="ph-only">Cộng tháng, bằng Phát sinh</span>');
    if (openKey) {
      const row = findRow(openKey);
      if (row) fill(row); else close(false);
    }
  }

  function detail(row) {
    const labels = labelsOf(card());
    const at = name => labels.indexOf(name);
    const cells = [...row.cells];
    const unit = at('Đơn giá');
    const infos = labels.map((label, index) => [label, index]).filter(([label, index]) => index > 1 && index < unit && label !== 'Ngày chuyến')
      .map(([label, index]) => `<dt>${escape(label)}</dt><dd>${escape(textOf(cells[index]))}</dd>`).join('');
    const status = statusOf(row);
    const last = labels.length - 1;
    const money = labels.map((label, index) => [label, index]).filter(([, index]) => index >= unit).map(([label, index]) => {
      const value = index === last && status ? TAGS[status] : textOf(cells[index]);
      if (index === last) return `<div class="ph-line total"><span>=</span><span>${escape(label)}</span><span>${escape(value)}</span></div>`;
      const minus = /^-\d/.test(value);
      const sign = index === unit ? '' : minus ? '−' : '+';
      return `<div class="ph-line"><span>${sign}</span><span>${escape(label)}</span><span>${escape(minus ? value.slice(1) : value)}</span></div>`;
    }).join('');
    const why = row.querySelector('.sheet-why')?.textContent.trim();
    const sheetTag = row.querySelector('.sheet-tag')?.textContent.replace(/^KHÁC:\s*/, '').trim();
    const rowTag = row.querySelector('.row-tag');
    const note = status === 'duyet' ? `Chuyến mới từ Sheet, chưa tính vào nợ cho tới khi duyệt${why ? ` (${why})` : ''}.`
      : status === 'khac' ? `Sheet có chuyến này nhưng chưa nối được vào sổ (${sheetTag || 'chưa rõ'}).`
        : status === 'chua' ? 'Chưa có giá nên chưa tính vào nợ.'
          : sheetTag ? `Sheet ghi khác ở: ${sheetTag}. Sổ vẫn tính theo số đang hiện.`
            : rowTag?.classList.contains('review') ? 'Đang chờ kiểm, chưa tính vào nợ.'
              : rowTag?.classList.contains('rejected') ? 'Đã loại, không tính vào nợ.' : '';
    const stt = textOf(cells[0]);
    return { title: textOf(cells[at('Số container')]), sub: `${stt === '–' ? 'Phí lẻ' : `Chuyến ${stt}`} · ${textOf(cells[at('Ngày chuyến')])}`,
      infos, money, note };
  }

  function ensureSheet() {
    if (sheet) return sheet;
    sheet = document.createElement('div');
    sheet.className = 'ph-sheet';
    sheet.hidden = true;
    sheet.innerHTML = '<div class="ph-veil" data-ph="close"></div><div class="ph-panel" role="dialog" aria-modal="true" aria-labelledby="ph-title">'
      + '<div class="ph-grip" aria-hidden="true"></div><div class="ph-head"><div class="ph-name"><h2 id="ph-title" class="ph-title"></h2>'
      + '<div class="ph-sub"></div></div><button type="button" class="ph-close" data-ph="close" aria-label="Đóng">'
      + '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>'
      + '</button></div><dl class="ph-info"></dl><div class="ph-money"></div><p class="ph-note"></p><p class="ph-desk">Sửa chuyến trên máy tính.</p>'
      + '<div class="ph-nav"><button type="button" data-ph="prev">‹ Chuyến trước</button><button type="button" data-ph="next">Chuyến sau ›</button></div></div>';
    sheet.addEventListener('click', event => {
      const act = event.target.closest('[data-ph]')?.dataset.ph;
      if (act === 'close') close(true);
      else if (act === 'prev' || act === 'next') step(act === 'next' ? 1 : -1);
    });
    // Esc đóng khung ở bất kỳ đâu khi khung đang mở (tiêu điểm có thể đã rơi về trang khi nút vừa bấm bị tắt).
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !sheet.hidden) { event.preventDefault(); event.stopPropagation(); close(true); }
    }, true);
    document.body.append(sheet);
    return sheet;
  }

  function fill(row) {
    const view = detail(row);
    const box = ensureSheet();
    box.querySelector('.ph-title').textContent = view.title;
    box.querySelector('.ph-sub').textContent = view.sub;
    box.querySelector('.ph-info').innerHTML = view.infos;
    box.querySelector('.ph-money').innerHTML = view.money;
    const note = box.querySelector('.ph-note');
    note.textContent = view.note;
    note.hidden = !view.note;
    const rows = [...card().querySelectorAll('tr.ph-row')];
    const index = rows.indexOf(row);
    box.querySelector('[data-ph="prev"]').disabled = index <= 0;
    box.querySelector('[data-ph="next"]').disabled = index < 0 || index >= rows.length - 1;
    if (!box.hidden && document.activeElement?.disabled) box.querySelector('.ph-close').focus();
    openKey = keyOf(row) ?? `index:${index}`;
  }

  function open(row) {
    returnFocus = row;
    fill(row);
    sheet.hidden = false;
    document.documentElement.classList.add('ph-lock');
    sheet.querySelector('.ph-close').focus();
  }

  function close(back) {
    if (!sheet || sheet.hidden) { openKey = null; return; }
    sheet.hidden = true;
    openKey = null;
    document.documentElement.classList.remove('ph-lock');
    if (back && returnFocus?.isConnected) returnFocus.querySelector('.ph-cont')?.focus?.();
    returnFocus = null;
  }

  function step(delta) {
    const rows = [...(card()?.querySelectorAll('tr.ph-row') ?? [])];
    const current = openKey?.startsWith('index:') ? Number(openKey.slice(6)) : rows.findIndex(row => keyOf(row) === openKey);
    const next = rows[current + delta];
    if (next) { returnFocus = next; fill(next); }
  }

  // Pha capture trên #app: chạy trước trình nghe sửa ô, xóa, duyệt của các phần khác và chặn hẳn chúng trên điện thoại.
  const intercept = event => {
    if (!narrow()) return;
    if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
    const row = event.target.closest?.('tr.ph-row');
    if (!row || !root.contains(row)) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    open(row);
  };
  root.addEventListener('click', intercept, true);
  root.addEventListener('keydown', intercept, true);
  media?.addEventListener?.('change', () => { if (!narrow()) close(false); });

  Object.assign(ctx, { phoneAfterRender });
};
