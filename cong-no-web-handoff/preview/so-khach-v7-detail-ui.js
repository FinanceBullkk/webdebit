/* Sổ khách V7 bản live — bảng chi tiết theo bảng kê gửi khách (SO-CHI-TIET-01, specs/v7-so-chi-tiet.md). Chỉ để xem: mỗi container
 * một dòng. Mặc định là bảng gọn (phí + cước mình thu = Tổng, cước khách tự trả đứng ngoài, bấm dòng để bung phép cộng); "Đủ cột" theo
 * thứ tự file. Sửa dữ liệu vẫn ở bảng sổ, đổi bằng nút trên thanh chuyến.
 * Mọi số và trạng thái lấy nguyên từ `sheet_details` của GET; phần này không cộng trừ tiền (ARCH-03). Trường ctx: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).detail = ctx => {
  'use strict';
  const { root, escape, fmt, redraw } = ctx;
  // Tên gọi bảng kê chỉ đặt ở đây: người dùng có thể đổi thành "Debit" sau.
  const KE = 'Bảng kê';
  const ke = KE.toLowerCase();
  const STORE = 'so-khach-bang';
  const remembered = () => { try { return localStorage.getItem(STORE); } catch { return null; } };
  const remember = value => { try { localStorage.setItem(STORE, value); } catch { /* không lưu được thì chỉ đổi trong phiên */ } };
  let ledgerView = remembered() === 'so';
  let mode = remembered() === 'du' ? 'du' : 'gon';
  // Lọc và dòng đang mở sống qua các lần vẽ lại, nên tự tải lại không làm mất.
  let filter = null;
  let openRow = null;
  const has = data => (data.sheet_details?.rows ?? []).length > 0;
  // ?loc= cần hàng của bảng sổ để cuộn tới và tô.
  const locating = () => new URLSearchParams(location.search).has('loc');
  const detailOn = data => has(data) && !ledgerView && !locating();
  const rowsOf = (data, key) => data.sheet_details.rows.filter(row => row.month === key);
  const detailCount = (data, key) => rowsOf(data, key).filter(row => row.container).length;
  const detailMissing = (data, key) => rowsOf(data, key).filter(row => row.state === 'no_price').length;
  const rowKey = row => `${row.kind}-${row.id}`;

  const GROUPS = [
    { id: 'chua-gia', label: 'Chưa có giá', states: ['no_price'] },
    { id: 'doi-chieu', label: `Đối chiếu ${ke}`, states: ['differs', 'no_add'] },
    { id: 'khong-co', label: `Chưa có trên ${ke}`, states: ['no_detail'] },
  ];
  const inGroup = (row, group) => group.states.includes(row.state);
  // Lọc thuộc một tháng; hết dòng khớp (ví dụ vừa có giá) thì coi như không lọc, không để bảng trống.
  const activeGroup = (rows, key) => {
    const group = filter?.month === key ? GROUPS.find(item => item.id === filter.id) : null;
    return group && rows.some(row => inGroup(row, group)) ? group : null;
  };

  const ICON = {
    edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/></svg>',
    down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
    up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>',
  };

  function chips(data, key) {
    const rows = rowsOf(data, key);
    const active = activeGroup(rows, key);
    const shown = GROUPS.map(group => ({ group, count: rows.filter(row => inGroup(row, group)).length })).filter(item => item.count);
    if (!shown.length) return '';
    return `<div class="dt-chips" role="group" aria-label="Lọc theo tình trạng">${shown.map(({ group, count }) => {
      const on = active === group;
      return `<button type="button" class="dt-chip" data-filter="${group.id}" aria-pressed="${on}">${group.label} ${count}${on ? ' ✕' : ''}</button>`;
    }).join('')}</div>`;
  }
  // Thanh chuyến: chip lọc, Gọn | Đủ cột, nút sang bảng sổ. Đang ở bảng sổ thì chỉ còn nút quay lại.
  function detailTools(data, key) {
    if (!has(data) || locating()) return '';
    if (!detailOn(data)) return '<button type="button" class="detail-toggle">Xem bảng chi tiết</button>';
    const modeButton = (id, label) => `<button type="button" class="dt-mode" data-mode="${id}" aria-pressed="${mode === id}">${label}</button>`;
    return `${chips(data, key)}<div class="dt-views"><div class="dt-modes" role="group" aria-label="Cách xem bảng">${modeButton('gon', 'Gọn')}${modeButton('du', 'Đủ cột')}</div>`
      + `<button type="button" class="detail-toggle dt-edit" aria-label="Sửa ở bảng sổ" title="Sửa ở bảng sổ">${ICON.edit}</button></div>`;
  }

  const zero = value => /^0+$/.test(value);
  const money = value => value == null || zero(value) ? '–' : fmt(value);
  const absMoney = value => fmt(value.replace('-', ''));
  const over = value => value.startsWith('-') ? 'kém' : 'hơn';
  const customerOf = row => row.has_detail && !row.of_counted ? row.of_vnd : null;
  const flagged = row => row.state === 'differs' || row.state === 'no_add';
  const status = row => ({
    differs: () => `${KE} ${over(row.sheet_diff_vnd)} ${absMoney(row.sheet_diff_vnd)}`,
    no_add: () => `${KE} không cộng ra Tổng`,
    no_detail: () => `Chưa có trên ${ke}`,
    no_price: () => 'Chưa có giá',
    loose: () => 'Không gắn container',
  })[row.state]();
  const statusCell = (row, span) => `<td colspan="${span}" class="dt-status dt-status-${row.state}">${escape(status(row))}</td>`;
  // Ô Tổng luôn là số của sổ. Rê chuột thấy số của bảng kê; đủ số thì không cần.
  function totalTitle(row) {
    if (row.sheet_total_vnd == null) return '';
    if (row.state === 'no_price') return `Sổ chưa có giá, ${ke} ghi ${fmt(row.sheet_total_vnd)}`;
    if (row.state === 'differs') return `${KE} ghi ${fmt(row.sheet_total_vnd)}`;
    if (row.state === 'no_add') return `Các khoản trên ${ke} cộng lại ${fmt(row.parts_vnd)}, Tổng ${ke} ghi ${fmt(row.sheet_total_vnd)}`;
    return '';
  }
  const totalCell = row => {
    const title = totalTitle(row);
    return `<td class="num dt-total${flagged(row) ? ' dt-differs' : ''}"${title ? ` title="${escape(title)}"` : ''}>${row.total_vnd == null ? '–' : fmt(row.total_vnd)}</td>`;
  };
  const containerCell = row => row.container ? `<td class="dt-cont">${escape(row.container)}</td>` : '<td>Phí lẻ</td>';

  // ---- Bảng gọn ----
  const line = (kind, sign, label, value) => `<div class="dt-line dt-line-${kind}"><span>${sign}</span><span>${escape(label)}</span><span>${value}</span></div>`;
  const partLines = row => line('plain', '', 'Phí phát sinh', money(row.fee_vnd)) + line('plain', '+', 'Phí DV hải quan', money(row.service_vnd))
    + line('plain', '+', 'Cước nội địa', money(row.truck_vnd)) + line('plain', '+', 'VAT 8%', money(row.vat_vnd));
  const customerLine = (row, label) => money(customerOf(row)) === '–' ? '' : line('outside', '', label, money(customerOf(row)));
  const ledgerOnly = row => line('total', '=', 'Sổ đang tính', money(row.total_vnd));
  // Phép cộng đúng theo số trên dòng: dòng không cộng ra thì ghi "Các khoản cộng lại", không đặt dấu = trước số không phải kết quả.
  function moreLines(row) {
    const ofMine = label => row.of_counted ? line('plain', '+', label, money(row.of_vnd)) : '';
    if (row.state === 'ok') {
      return partLines(row) + ofMine('Cước tàu mình thu') + line('total', '=', 'Tổng', money(row.total_vnd)) + customerLine(row, 'Cước tàu khách tự trả, không tính');
    }
    if (row.state === 'differs') {
      const written = row.adds_up ? line('total', '=', `${KE} ghi`, money(row.sheet_total_vnd))
        : line('total', '=', 'Các khoản cộng lại', money(row.parts_vnd)) + line('strong', '', `${KE} ghi`, money(row.sheet_total_vnd));
      return partLines(row) + ofMine('Cước tàu mình thu') + written + line('strong', '', 'Sổ đang tính, số nợ theo số này', money(row.total_vnd))
        + line('plain', '', `${KE} ${over(row.sheet_diff_vnd)} sổ`, absMoney(row.sheet_diff_vnd)) + customerLine(row, 'Cước tàu khách tự trả, không tính');
    }
    if (row.state === 'no_add') {
      const written = row.sheet_total_vnd == null ? line('strong', '', 'Sổ đang tính, số nợ theo số này', money(row.total_vnd))
        : line('strong', '', `Tổng ghi trên ${ke}, sổ đang tính số này`, money(row.sheet_total_vnd));
      const gap = row.adds_diff_vnd == null ? '' : line('plain', '', `Các khoản ${over(row.adds_diff_vnd)} Tổng`, absMoney(row.adds_diff_vnd));
      return partLines(row) + ofMine('Cước tàu') + line('total', '=', 'Các khoản cộng lại', money(row.parts_vnd)) + written + gap + customerLine(row, `Cước tàu trên ${ke}, ngoài phép cộng này`);
    }
    if (row.state === 'no_price') return row.sheet_total_vnd == null ? '' : line('strong', '', `${KE} ghi`, money(row.sheet_total_vnd));
    return ledgerOnly(row);
  }
  const HINT = {
    differs: `Nếu ${ke} đã cũ, dán lại trên Sheet; khớp thì dòng này hết báo.`,
    no_detail: `Chưa tách được từng khoản. ${KE} mới có chuyến này thì tự hiện.`,
    no_price: 'Chờ giá từ Sheet. Chuyến này chưa tính vào nợ.',
    loose: 'Khoản này lấy nguyên từ sổ.',
  };
  function moreRow(row) {
    const infos = row.container ? [['Bill', row.bill], ['Tên tàu', row.ship], ['ETD · ETA', `${row.etd || '–'} · ${row.eta || '–'}`], ['Nơi đóng hàng', row.from], ['Cảng đến', row.to]] : [['Ngày', row.day]];
    return `<tr class="dt-more"><td colspan="9"><div class="dt-more-grid"><dl class="dt-infos">${infos.map(([label, value]) => `<dt>${label}</dt><dd>${escape(value || '–')}</dd>`).join('')}</dl>`
      + `<div class="dt-lines">${moreLines(row)}${HINT[row.state] ? `<p class="dt-hint">${escape(HINT[row.state])}</p>` : ''}</div></div></td></tr>`;
  }
  function compactRow(row, number) {
    const open = openRow === rowKey(row);
    const route = [row.from, row.to].filter(Boolean).join(' → ') || '–';
    const middle = row.state === 'ok'
      ? `<td class="num dt-mine">${money(row.phi_vnd)}</td><td class="num dt-mine dt-of-mine">${row.of_counted ? money(row.of_vnd) : '–'}</td>`
      : statusCell(row, 2);
    const arrow = `<td class="dt-arrow-cell"><button type="button" class="dt-arrow" data-open="${escape(rowKey(row))}" aria-expanded="${open}" `
      + `aria-label="${open ? 'Thu gọn' : 'Xem chi tiết'} ${escape(row.container || 'phí lẻ')}">${open ? ICON.up : ICON.down}</button></td>`;
    return `<tr class="dt-row${open ? ' dt-open' : ''}" data-detail="${escape(rowKey(row))}"><td class="dt-stt">${row.container ? number : '–'}</td>${containerCell(row)}<td>${escape(row.day)}</td>`
      + `<td class="dt-route">${escape(route)}</td>${middle}${totalCell(row)}<td class="num dt-customer">${money(customerOf(row))}</td>${arrow}</tr>${open ? moreRow(row) : ''}`;
  }
  const footLabel = summary => summary.diff_vnd == null ? 'Cộng cả tháng' : zero(summary.diff_vnd) ? 'Cộng cả tháng, bằng Phát sinh' : 'Phát sinh của sổ';
  function compactTable(rows, summary, numbered) {
    return '<table class="detail-table dt-gon" aria-label="Bảng chi tiết của tháng"><colgroup><col class="c-stt"><col class="c-cont"><col class="c-pack"><col><col class="c-phi"><col class="c-of"><col class="c-total"><col class="c-customer"><col class="c-arrow"></colgroup>'
      + '<thead><tr><th scope="col" class="dt-stt">STT</th><th scope="col">Số container</th><th scope="col">Ngày đóng</th><th scope="col">Nơi đóng hàng → Cảng đến</th><th scope="col" class="num dt-own">Phí mình thu</th>'
      + '<th scope="col" class="num dt-own">+ Cước tàu mình thu</th><th scope="col" class="num dt-own">= Tổng</th><th scope="col" class="num dt-customer">Cước khách tự trả (không tính)</th><th scope="col" aria-label="Mở dòng"></th></tr></thead>'
      + `<tbody>${rows.map(row => compactRow(row, numbered.get(row))).join('')}</tbody>`
      + `<tfoot><tr><td colspan="6" class="dt-foot-label">${footLabel(summary)}</td><td class="num dt-foot-total">${fmt(summary.charges_vnd ?? summary.total_vnd)}</td>`
      + `<td class="num dt-foot-customer">${money(summary.of_customer_vnd)}</td><td></td></tr></tfoot></table>`;
  }

  // ---- Đủ cột: 15 cột theo thứ tự file ----
  const moneyCell = (value, cls) => `<td class="num ${cls}">${money(value)}</td>`;
  // Cước tàu: có số mà nằm trong Tổng thì mình thu (xanh đậm), ngoài Tổng là khách tự trả (cam), không có số thì trống.
  const ofCell = row => row.of_vnd == null ? '<td class="num dt-own">–</td>'
    : row.of_counted ? `<td class="num dt-of-own" title="Mình thu, đã tính vào Tổng">${fmt(row.of_vnd)}</td>`
      : `<td class="num dt-of-customer" title="Khách tự trả, không tính vào Tổng">${fmt(row.of_vnd)}</td>`;
  const moneyCells = row => row.state === 'ok'
    ? moneyCell(row.fee_vnd, 'dt-own') + moneyCell(row.service_vnd, 'dt-own') + moneyCell(row.truck_vnd, 'dt-own') + ofCell(row) + moneyCell(row.vat_vnd, 'dt-own')
    : statusCell(row, 5);
  const text = value => `<td class="dt-text" title="${escape(value)}">${escape(value)}</td>`;
  const fullRow = (row, number) => `<tr data-detail="${escape(rowKey(row))}"><td>${row.container ? number : '–'}</td>${containerCell(row)}${text(row.bill)}${text(row.ship)}`
    + `<td>${escape(row.day)}</td><td>${escape(row.etd)}</td><td>${escape(row.eta)}</td>${text(row.from)}${text(row.to)}${moneyCells(row)}${totalCell(row)}</tr>`;
  function fullTable(rows, summary, numbered) {
    const legend = `<span><i class="dt-swatch own" aria-hidden="true"></i>Mình thu, tính vào Tổng</span><span><i class="dt-swatch customer" aria-hidden="true"></i>Khách tự trả ${money(summary.of_customer_vnd)}, không tính</span>`;
    return '<table class="detail-table dt-du" aria-label="Bảng chi tiết của tháng"><colgroup><col class="c-stt"><col class="c-cont"><col class="c-bill"><col class="c-ship">'
      + '<col class="c-pack"><col class="c-day"><col class="c-day"><col class="c-from"><col class="c-to"><col class="c-fee"><col class="c-service"><col class="c-truck"><col class="c-of"><col class="c-vat"><col class="c-total"></colgroup>'
      + '<thead><tr><th scope="col">STT</th><th scope="col">Số container</th><th scope="col">Bill</th><th scope="col">Tên tàu</th><th scope="col">Ngày đóng</th>'
      + '<th scope="col">ETD</th><th scope="col">ETA</th><th scope="col">Nơi đóng hàng</th><th scope="col">Cảng đến</th><th scope="col" class="num dt-own">Phí phát sinh</th>'
      + '<th scope="col" class="num dt-own">Phí DV hải quan</th><th scope="col" class="num dt-own">Cước nội địa</th><th scope="col" class="num">Cước tàu OF</th>'
      + `<th scope="col" class="num dt-own">VAT 8%</th><th scope="col" class="num">Tổng</th></tr></thead><tbody>${rows.map(row => fullRow(row, numbered.get(row))).join('')}</tbody>`
      + `<tfoot><tr><td colspan="15"><div class="dt-foot-row">${legend}<strong class="dt-foot-total">${footLabel(summary)}: ${fmt(summary.charges_vnd ?? summary.total_vnd)}</strong></div></td></tr></tfoot></table>`;
  }

  // Khi lọc Đối chiếu: một dòng báo phần chênh. Cộng các dòng lệch Phát sinh (điều chỉnh tháng) thì báo cả khi không lọc.
  function compareNote(summary) {
    const parts = [];
    if (summary.compare_differs) {
      const diff = summary.compare_diff_vnd;
      parts.push(`${KE} khác sổ ở ${summary.compare_differs} container, cộng lại ${zero(diff) ? 'bằng sổ' : `${over(diff)} sổ ${absMoney(diff)}`}.`);
    }
    if (summary.compare_no_add) parts.push(`${summary.compare_no_add} container có các khoản ${ke} không cộng ra Tổng.`);
    parts.push('Tổng và số nợ theo sổ.');
    return `<p class="detail-note" role="status">${parts.join(' ')}</p>`;
  }
  const monthNote = summary => summary.diff_vnd == null || zero(summary.diff_vnd) ? ''
    : `<p class="detail-note" role="status">Cộng các dòng ${fmt(summary.total_vnd)}, Phát sinh của sổ ${fmt(summary.charges_vnd)}: lệch ${fmt(summary.diff_vnd)}.</p>`;

  function detailTable(data, key) {
    const all = rowsOf(data, key);
    const summary = data.sheet_details.months?.[key];
    if (!all.length || !summary) return '<p class="detail-note">Tháng này chưa có chuyến.</p>';
    // STT theo cả tháng, lọc không đánh số lại: người đọc còn đối chiếu được với file.
    let number = 0;
    const numbered = new Map(all.map(row => [row, row.container ? ++number : 0]));
    const group = activeGroup(all, key);
    const rows = group ? all.filter(row => inGroup(row, group)) : all;
    const note = group?.id === 'doi-chieu' ? compareNote(summary) : '';
    return monthNote(summary) + note + (mode === 'du' ? fullTable(rows, summary, numbered) : compactTable(rows, summary, numbered));
  }

  function setFilter(month, id) {
    filter = { month, id };
    openRow = null;
    redraw();
  }
  function detailShowMissing(key) {
    setFilter(key, 'chua-gia');
    root.querySelector('.dt-chip[data-filter="chua-gia"]')?.focus();
  }
  root.addEventListener('click', event => {
    const target = event.target;
    if (target.closest('.detail-toggle')) {
      ledgerView = !ledgerView;
      remember(ledgerView ? 'so' : mode);
      redraw();
      root.querySelector('.detail-toggle')?.focus({ preventScroll: true });
      return;
    }
    const pickMode = target.closest('.dt-mode');
    if (pickMode) {
      mode = pickMode.dataset.mode;
      remember(mode);
      redraw();
      return;
    }
    const chip = target.closest('.dt-chip');
    if (chip) {
      const month = chip.closest('section')?.id.replace('thang-', '');
      if (chip.getAttribute('aria-pressed') === 'true') { filter = null; openRow = null; redraw(); } else setFilter(month, chip.dataset.filter);
      return;
    }
    const row = target.closest('tr.dt-row');
    // Kéo chọn số container để chép thì không bung dòng.
    if (!row || String(getSelection())) return;
    openRow = openRow === row.dataset.detail ? null : row.dataset.detail;
    redraw();
    root.querySelector('tr.dt-more')?.scrollIntoView({ block: 'nearest' });
  });

  Object.assign(ctx, { detailOn, detailCount, detailMissing, detailTools, detailTable, detailShowMissing });
};
