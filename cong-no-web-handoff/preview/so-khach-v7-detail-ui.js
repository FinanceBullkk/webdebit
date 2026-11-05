/* Sổ khách V7 bản live — bảng chi tiết theo bảng kê gửi khách (SO-CHI-TIET-01, specs/v7-so-chi-tiet.md). Chỉ để xem: mỗi container
 * một dòng, tô màu thay cho hai dòng trên Sheet. Sửa dữ liệu vẫn ở bảng sổ, đổi bằng nút trên thanh "Chuyến trong tháng".
 * Mọi số lấy nguyên từ `sheet_details` của GET; phần này không cộng trừ tiền (ARCH-03). Trường ctx đọc/ghi: so-khach-v7-ctx.js. */
(window.SoKhachV7LiveParts ??= {}).detail = ctx => {
  'use strict';
  const { root, escape, fmt, redraw } = ctx;
  const STORE = 'so-khach-bang';
  const remembered = () => { try { return localStorage.getItem(STORE); } catch { return null; } };
  let ledgerView = remembered() === 'so';
  const has = data => (data.sheet_details?.rows ?? []).length > 0;
  // ?loc= cần hàng của bảng sổ để cuộn tới và tô.
  const locating = () => new URLSearchParams(location.search).has('loc');
  const detailOn = data => has(data) && !ledgerView && !locating();
  const rowsOf = (data, key) => data.sheet_details.rows.filter(row => row.month === key);
  const detailCount = (data, key) => rowsOf(data, key).filter(row => row.container).length;
  const detailMissing = (data, key) => rowsOf(data, key).filter(row => row.total_vnd == null).length;
  const LEGEND = '<div class="detail-legend"><span><i class="dt-swatch own" aria-hidden="true"></i>Mình thu, tính vào Tổng</span>'
    + '<span><i class="dt-swatch customer" aria-hidden="true"></i>Khách tự trả, không tính</span></div>';
  const detailToggle = data => !has(data) || locating() ? ''
    : `<button type="button" class="detail-toggle">${detailOn(data) ? 'Xem bảng sổ để sửa' : 'Xem bảng chi tiết'}</button>${detailOn(data) ? LEGEND : ''}`;

  const money = value => value == null || /^0+$/.test(value) ? '–' : fmt(value);
  const moneyCell = (value, cls) => `<td class="num ${cls}">${money(value)}</td>`;
  // Cước tàu: có số mà nằm trong Tổng thì mình thu (xanh đậm), ngoài Tổng là khách tự trả (cam), không có số thì trống.
  const ofCell = row => row.of_vnd == null ? '<td class="num dt-own">–</td>'
    : row.of_counted ? `<td class="num dt-of-own" title="Mình thu, đã tính vào Tổng">${fmt(row.of_vnd)}</td>`
      : `<td class="num dt-of-customer" title="Khách tự trả, không tính vào Tổng">${fmt(row.of_vnd)}</td>`;
  const moneyCells = row => row.has_detail
    ? moneyCell(row.fee_vnd, 'dt-own') + moneyCell(row.service_vnd, 'dt-own') + moneyCell(row.truck_vnd, 'dt-own') + ofCell(row) + moneyCell(row.vat_vnd, 'dt-own')
    : `<td colspan="5" class="${row.total_vnd == null ? 'dt-missing">chưa có giá' : 'dt-no-detail">chưa có trên bảng kê'}</td>`;
  const label = row => row.container ? `<td class="dt-cont">${escape(row.container)}</td>` : '<td>Phí lẻ</td>';
  const text = value => `<td class="dt-text" title="${escape(value)}">${escape(value)}</td>`;

  function rowHtml(row, number) {
    const differs = row.differs ? ` title="Sổ đang ghi ${fmt(row.ledger_vnd)}"` : '';
    return `<tr data-detail="${escape(`${row.kind}-${row.id}`)}"><td>${row.container ? number : '–'}</td>${label(row)}${text(row.bill)}${text(row.ship)}`
      + `<td>${escape(row.day)}</td><td>${escape(row.etd)}</td><td>${escape(row.eta)}</td>${text(row.from)}${text(row.to)}${moneyCells(row)}`
      + `<td class="num dt-total${row.differs ? ' dt-differs' : ''}"${differs}>${row.total_vnd == null ? '–' : fmt(row.total_vnd)}</td></tr>`;
  }

  // Bảng kê khác sổ thì chỉ báo; số nợ vẫn theo tab sổ.
  function noteHtml(summary) {
    const parts = [];
    if (summary.diff_vnd != null && !/^0+$/.test(summary.diff_vnd)) {
      parts.push(`Cộng bảng kê ${fmt(summary.total_vnd)}, sổ ${fmt(summary.charges_vnd)}: lệch ${fmt(summary.diff_vnd)}. Số nợ theo sổ.`);
    }
    if (summary.differs.length) parts.push(`Khác sổ: ${summary.differs.map(escape).join(', ')}.`);
    if (summary.no_detail) parts.push(`${summary.no_detail} chuyến chưa có trên bảng kê.`);
    return parts.length ? `<p class="detail-note" role="status">${parts.join(' ')}</p>` : '';
  }

  function detailTable(data, key) {
    const rows = rowsOf(data, key);
    const summary = data.sheet_details.months?.[key];
    if (!rows.length || !summary) return '<p class="detail-note">Tháng này chưa có chuyến.</p>';
    let number = 0;
    const body = rows.map(row => rowHtml(row, row.container ? ++number : 0)).join('');
    const customer = /^0+$/.test(summary.of_customer_vnd) ? ''
      : `<span class="dt-customer-sum">Khách tự trả cước tàu: <b>${fmt(summary.of_customer_vnd)}</b>, không tính vào Tổng</span>`;
    return noteHtml(summary)
      + '<table class="detail-table" aria-label="Bảng chi tiết của tháng"><colgroup><col class="c-stt"><col class="c-cont"><col class="c-bill"><col class="c-ship">'
      + '<col class="c-pack"><col class="c-day"><col class="c-day"><col class="c-from"><col class="c-to"><col class="c-fee"><col class="c-service"><col class="c-truck"><col class="c-of"><col class="c-vat"><col class="c-total"></colgroup>'
      + '<thead><tr><th scope="col">STT</th><th scope="col">Số container</th><th scope="col">Bill</th><th scope="col">Tên tàu</th><th scope="col">Ngày đóng</th>'
      + '<th scope="col">ETD</th><th scope="col">ETA</th><th scope="col">Nơi đóng hàng</th><th scope="col">Cảng đến</th><th scope="col" class="num dt-own">Phí phát sinh</th>'
      + '<th scope="col" class="num dt-own">Phí DV hải quan</th><th scope="col" class="num dt-own">Cước nội địa</th><th scope="col" class="num">Cước tàu OF</th>'
      + `<th scope="col" class="num dt-own">VAT 8%</th><th scope="col" class="num">Tổng</th></tr></thead><tbody>${body}</tbody>`
      + `<tfoot><tr><td colspan="9">${customer}</td>${moneyCell(summary.fee_vnd, '')}${moneyCell(summary.service_vnd, '')}${moneyCell(summary.truck_vnd, '')}`
      + `${moneyCell(summary.of_counted_vnd, '')}${moneyCell(summary.vat_vnd, '')}${moneyCell(summary.total_vnd, '')}</tr></tfoot></table>`;
  }

  root.addEventListener('click', event => {
    if (!event.target.closest('.detail-toggle')) return;
    ledgerView = !ledgerView;
    try { localStorage.setItem(STORE, ledgerView ? 'so' : 'chi-tiet'); } catch { /* không lưu được thì chỉ đổi trong phiên */ }
    redraw();
    root.querySelector('.detail-toggle')?.focus({ preventScroll: true });
  });

  Object.assign(ctx, { detailOn, detailCount, detailMissing, detailToggle, detailTable });
};
