/* In-memory UI adapter for V5 ledger connected to LedgerV5Model. */
(() => {
  'use strict';
  const model = typeof LedgerV5Model !== 'undefined'
    ? LedgerV5Model
    : (typeof require !== 'undefined' ? require('./so-cong-no-v5-model.js') : null);

  const SAMPLE_DATE = '17/10/2026';
  const TODAY_ISO = '2026-10-17';

  const safe = s => String(s ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));

  function fmtVnd(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'string') value = model.lineAmount({ unitPriceVnd: value, otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null });
    const s = typeof value === 'bigint' ? value.toString() : String(value).trim();
    const isNegative = s.startsWith('-');
    const digits = isNegative ? s.slice(1) : s;
    const formatted = digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return isNegative ? '−' + formatted : formatted;
  }

  const parseDigits = s => {
    const d = String(s ?? '').trim();
    if (!d) return null;
    if (!/^(?:\d+|\d{1,3}(?:\.\d{3})+)$/.test(d)) throw new Error('Số tiền phải là số nguyên không âm; chỉ dùng dấu chấm để phân nhóm ba chữ số.');
    return d.replace(/\./g, '');
  };

  const moneyCell = n => (n === null || n === undefined) ? '—' : fmtVnd(n);

  const dateValid = s => {
    const m = String(s || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (!m) return false;
    const d = new Date(+m[3], +m[2] - 1, +m[1]);
    return d.getFullYear() === +m[3] && d.getMonth() === +m[2] - 1 && d.getDate() === +m[1] && d <= new Date('2026-10-17T23:59:59');
  };

  const baseClients = [
    { id: 'KHACH_MAU', category: 'Thanh long', closed: '95000000', open: '90000000', status: 'open', warn: true },
    { id: 'KHACH_B', category: 'Thanh long', brought: '18000000', origin: '122000000', paid: '40000000', open: '0', cont: 9, status: 'closed' },
    { id: 'KHACH_C', category: 'Thanh long', brought: '0', origin: null, paid: null, open: '0', cont: null, status: 'not-open' },
    { id: 'KHACH_D', category: 'Mít', brought: '30000000', origin: '60000000', paid: '20000000', open: '0', cont: 3, status: 'closed' },
    { id: 'KHACH_E', category: 'Mít', brought: '12000000', origin: null, paid: null, open: '45000000', cont: 2, status: 'open' }
  ];

  const originalRows = [
    { id: 'DEMO-105', carrier: 'WH', date: '08/04/2026', from: 'PHAN THIET', to: 'SHEKOU', otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null, unitPriceVnd: '40000000' },
    { id: 'DEMO-106', carrier: 'WH', date: '12/04/2026', from: 'PHAN THIET', to: 'SHEKOU', otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null, unitPriceVnd: '30000000' },
    { id: 'DEMO-107', carrier: 'WH', date: '18/04/2026', from: 'PHAN THIET', to: 'SHEKOU', otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null, unitPriceVnd: '20000000' },
    { id: 'DEMO-103', carrier: 'WH', date: '22/04/2026', from: 'PHAN THIET', to: 'SHEKOU', otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null, unitPriceVnd: null }
  ];

  const originalReceipts = [
    { id: 'CT-CHO-05', ledger: 'KHACH_MAU · thanh long', period: '04.2026', enteredAt: 'DEMO-103', amountVnd: '5000000', receivedOn: null, confirmed: false }
  ];

  let S;
  const clone = o => JSON.parse(JSON.stringify(o));

  const reset = () => {
    S = {
      tab: 'ledger',
      filter: 'all',
      search: '',
      month: '04.2026',
      selected: 'KHACH_MAU',
      expanded: null,
      openMenu: null,
      expandedMonths: new Set(['04.2026']),
      modal: null,
      drawer: null,
      actor: 'Nguyễn Văn A',
      rows: clone(originalRows),
      unconfirmedReceipts: clone(originalReceipts),
      editingPayment: false,
      paymentError: '',
      paymentDraft: { date: '20/04/2026', method: 'Chuyển khoản', ref: 'UNC-0420', amount: '120.000.000' },
      confirmedReceipt: null,
      pasteInput: '',
      pasteMessage: '',
      pasteOk: false,
      inlineFeedback: '',
      inlinePasteInput: '',
      modalNotice: '',
      showDeleteBlock: false,
      pendingDelete: null,
      customRows: [],
      simulatedClosed: false,
      audit: [],
      importWarnings: [],
      editingRow: null,
    };
  };

  function rowsNow() {
    return [...S.rows, ...S.customRows];
  }

  function balance() {
    const totals = model.monthTotals(rowsNow());
    const openVnd = model.monthTotals(S.simulatedClosed ? [] : rowsNow()).pricedTotalVnd;
    const closedVnd = model.monthTotals([
      { unitPriceVnd: '95000000', otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null },
      ...(S.simulatedClosed ? rowsNow() : []),
    ]).pricedTotalVnd;
    const buckets = [
      { key: 'before-T01', kind: 'closed', balanceVnd: '20000000' },
      { key: 'T01', kind: 'closed', balanceVnd: '20000000' },
      { key: 'T02', kind: 'closed', balanceVnd: '30000000' },
      { key: 'T03', kind: 'closed', balanceVnd: '25000000' },
      { key: 'T04', kind: S.simulatedClosed ? 'closed' : 'open', balanceVnd: totals.pricedTotalVnd },
    ];
    const receipts = [];
    if (S.confirmedReceipt) receipts.push(S.confirmedReceipt);
    for (const r of S.unconfirmedReceipts) receipts.push(r);
    return model.ledgerBalance({
      closedVnd,
      openVnd,
      receipts,
      buckets,
    });
  }

  function currentClients() {
    const b = balance();
    const totals = model.monthTotals(rowsNow());
    return baseClients.map(c => {
      if (c.id === 'KHACH_MAU') {
        return {
          ...c,
          closed: b.closedRemainingVnd,
          open: b.openRemainingVnd,
          status: S.simulatedClosed ? 'closed' : 'open',
          warn: !S.simulatedClosed && totals.missingPriceIds.length > 0,
        };
      }
      const lines = [c.brought, c.origin].map(unitPriceVnd => ({ unitPriceVnd, otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null }));
      const closedVnd = model.monthTotals(lines).pricedTotalVnd;
      const openVnd = model.lineAmount({ unitPriceVnd: c.open, otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null });
      const result = model.ledgerBalance({ closedVnd, openVnd,
        receipts: c.paid === null ? [] : [{ amountVnd: c.paid, receivedOn: '2026-04-20' }],
        buckets: [{ key: 'closed', kind: 'closed', balanceVnd: closedVnd }, { key: 'open', kind: 'open', balanceVnd: openVnd }],
      });
      return { ...c, closed: result.closedRemainingVnd, open: result.openRemainingVnd };
    });
  }

  function filteredClients() {
    return currentClients().filter(c => {
      const hit = !S.search || (c.id + ' ' + c.category).toLowerCase().includes(S.search.toLowerCase());
      const match = S.filter === 'all' || (S.filter === 'unclosed' && c.status === 'open') || (S.filter === 'open' && c.status === 'open') || (S.filter === 'closed' && c.status === 'closed');
      return hit && match;
    });
  }

  const roleName = () => S.actor;
  const roleTitle = () => S.actor === 'Nguyễn Văn A' ? 'Người nhập' : (S.actor === 'Lê Văn C' ? 'Người chốt' : 'Người thu tiền');
  const roleAvatar = () => S.actor === 'Nguyễn Văn A' ? 'NA' : (S.actor === 'Lê Văn C' ? 'LC' : 'TB');
  const statusName = s => s === 'open' ? 'Đang mở' : (s === 'closed' ? 'Đã chốt' : 'Chưa mở');
  const statusColor = s => s === 'open' ? 'blue' : (s === 'closed' ? 'green' : 'gray');
  const tag = (text, type) => `<span class="tag ${type}">${safe(text)}</span>`;

  function renderSidebar() {
    const clients = filteredClients();
    const groups = [...new Set(clients.map(c => c.category))];
    const totals = model.monthTotals(rowsNow());
    return `<aside class="aside"><div class="aside-sticky">
      <div class="brand"><strong><span class="brand-mark">▤</span> CÔNG NỢ</strong><span class="small-muted">${SAMPLE_DATE}</span></div>
      <div class="nav-tabs"><button data-action="tab" data-value="total" class="${S.tab === 'total' ? 'active' : ''}">Tổng</button><button data-action="tab" data-value="ledger" class="${S.tab === 'ledger' ? 'active' : ''}">Sổ khách</button></div>
      <label class="field-label" for="month-select">Tháng xem</label><select id="month-select" data-action="month" class="field"><option value="04.2026">04.2026</option></select>
      <div class="search-wrap"><span class="search-glyph">⌕</span><input id="customer-search" data-action="search" class="field" placeholder="Tìm khách hoặc loại hàng..." value="${safe(S.search)}" aria-label="Tìm sổ" /></div>
      <div class="filter-tabs">${[['all', 'Tất cả'], ['unclosed', 'Chưa chốt'], ['open', 'Đang mở'], ['closed', 'Đã chốt']].map(([id, label]) => `<button data-action="filter" data-value="${id}" class="${S.filter === id ? 'active' : ''}">${label}</button>`).join('')}</div>
      <div class="result-count">${S.filter === 'unclosed' ? `${clients.length} / 5 sổ mẫu chưa chốt` : `${clients.length} / 5 sổ mẫu`} <span class="small-muted">· khoảng 240 sổ thực tế</span></div>
      <div class="customer-groups">${groups.length ? groups.map(g => `<div class="group-header">${safe(g)} (${clients.filter(c => c.category === g).length})</div>${clients.filter(c => c.category === g).map(c => `
        <button data-action="customer" data-value="${safe(c.id)}" class="customer ${S.selected === c.id ? 'active' : ''}">
          <div class="customer-top"><strong>${safe(c.id)}</strong>${tag(statusName(c.status), statusColor(c.status))}</div>
          <div class="customer-money"><div><span>Đã chốt</span><strong>${fmtVnd(c.closed)}</strong></div><div><span>Đang mở</span><strong>${c.id === 'KHACH_MAU' ? `${fmtVnd(c.open)}${!S.simulatedClosed && totals.pricedTotalVnd > 0n && c.open === 0n ? ' · đã thu đủ' : ''}` : (c.open !== 0n ? fmtVnd(c.open) : '—')}</strong></div></div>
          ${c.id === 'KHACH_MAU' ? `<div class="customer-warning">${totals.missingPriceIds.length ? `⚠ ${totals.missingPriceIds.length} dòng thiếu giá · ` : ''}${S.unconfirmedReceipts.length ? `${S.unconfirmedReceipts.length} chứng từ chưa xác nhận (${fmtVnd(S.unconfirmedReceipts[0].amountVnd)})` : 'Không có chứng từ chưa xác nhận'}</div>` : ''}
        </button>`).join('')}`).join('') : '<div class="empty">Không tìm thấy sổ phù hợp.</div>'}</div>
      ${S.unconfirmedReceipts.length ? `<div class="aside-footer"><strong>Chứng từ chưa xác nhận</strong><br/>KHACH_MAU · ${fmtVnd(S.unconfirmedReceipts[0].amountVnd)}<br/>Chưa có ngày nhận tiền · ngoài số dư.</div>` : ''}
    </div></aside>`;
  }

  function renderTop() {
    return `<header class="topbar"><div><h1>${S.tab === 'total' ? 'Tổng công nợ' : `${safe(S.selected)} · ${S.selected === 'KHACH_MAU' ? 'thanh long' : (baseClients.find(c => c.id === S.selected)?.category || '')}`}</h1><p>Ngày xem: ${SAMPLE_DATE} · Tuyến PHAN THIET → SHEKOU</p></div>
    <div class="top-right">
      <select class="field" data-action="actor" aria-label="Chọn vai" style="width:auto;min-height:40px;padding:6px 10px;font-size:16px">
        <option value="Nguyễn Văn A" ${S.actor === 'Nguyễn Văn A' ? 'selected' : ''}>Nguyễn Văn A</option>
        <option value="Trần Thị B" ${S.actor === 'Trần Thị B' ? 'selected' : ''}>Trần Thị B</option>
        <option value="Lê Văn C" ${S.actor === 'Lê Văn C' ? 'selected' : ''}>Lê Văn C</option>
      </select>
      <div class="profile"><span class="avatar">${roleAvatar()}</span><div><strong>${roleName()}</strong><small>${roleTitle()}</small></div></div>
    </div></header>`;
  }

  function renderSummary() {
    const b = balance();
    return `<div class="summary">
      <div class="stat"><span>Đã chốt</span><strong>${fmtVnd(b.closedRemainingVnd)}</strong><small>${b.closedRemainingVnd === 0n ? 'đã thu đủ' : `Còn phải thu đã chốt đến hết tháng ${S.simulatedClosed ? '04' : '03'}.2026`}</small></div>
      <div class="stat open"><span>Đang mở · chưa chốt</span><strong>${fmtVnd(b.openRemainingVnd)}</strong><small>${!S.simulatedClosed && model.monthTotals(rowsNow()).pricedTotalVnd > 0n && b.openRemainingVnd === 0n ? 'đã thu đủ' : 'Các chuyến tháng 04.2026'}</small></div>
      <div class="view-month"><div>THÁNG ĐANG XEM<strong>04.2026</strong></div></div>
    </div>`;
  }

  const historical = [
    { month: '01.2026', date: '02/02/2026', balance: '40000000' },
    { month: '02.2026', date: '02/03/2026', balance: '70000000' },
    { month: '03.2026', date: '02/04/2026', balance: '95000000' }
  ];

  function renderHistorical() {
    return historical.map(h => {
      const opened = S.expandedMonths.has(h.month);
      return `<section class="month"><button class="month-head" data-action="expand-month" data-value="${h.month}"><span class="month-name"><span class="triangle ${opened ? 'down' : ''}"></span><strong>THÁNG ${h.month}</strong>${tag('Đã chốt · ' + h.date, 'green')}</span><span class="month-number">Số dư cuối tháng <strong>${fmtVnd(h.balance)}</strong></span></button>
      ${opened ? `<div class="totals"><p style="font-size:16px;color:#526985">Lịch sử tháng ${h.month} (chỉ xem; số dư không thay đổi khi ghi khoản thu tháng 04)</p><div class="total-line"><span class="total-label">Còn phải thu cuối tháng</span><span class="total-value">${fmtVnd(h.balance)}</span></div></div>` : ''}</section>`;
    }).join('');
  }

  function payCells(r) {
    if (r.id === 'DEMO-105' && S.editingPayment) {
      return `<td><input data-pay="date" class="cell-input" placeholder="dd/mm/yyyy" value="${safe(S.paymentDraft.date)}" aria-label="Ngày nhận tiền" /></td><td><select data-pay="method" class="cell-input" aria-label="Cách thu">${['', 'Chuyển khoản', 'Cấn trừ', 'Ứng trước', 'Khác'].map(v => `<option ${S.paymentDraft.method === v ? 'selected' : ''}>${safe(v)}</option>`).join('')}</select></td><td><input data-pay="ref" class="cell-input" value="${safe(S.paymentDraft.ref)}" placeholder="Tham chiếu" aria-label="Tham chiếu" /></td><td><input data-pay="amount" class="cell-input numeric" value="${safe(S.paymentDraft.amount)}" placeholder="Số tiền" aria-label="Đã thu" /></td>`;
    }
    if (r.id === 'DEMO-105' && S.confirmedReceipt) {
      const x = S.confirmedReceipt;
      return `<td>${safe(x.date)}</td><td>${safe(x.method)}</td><td>${safe(x.ref)}</td><td class="numeric">${fmtVnd(x.amountVnd)}</td>`;
    }
    const rec = S.unconfirmedReceipts.find(x => x.enteredAt === r.id);
    if (rec) {
      return `<td class="muted">—</td><td class="muted">—</td><td><span class="receipt-pending">${safe(rec.id)}</span></td><td class="numeric"><span class="receipt-pending">${fmtVnd(rec.amountVnd)} · Chưa xác nhận</span></td>`;
    }
    return `<td class="muted"><button class="container-link" data-action="row-payment" data-value="${safe(r.id)}" style="display:inline-block;width:100%;text-align:left;color:inherit;text-decoration:none;min-height:40px;padding:0">—</button></td><td class="muted">—</td><td class="muted">—</td><td class="numeric muted">—</td>`;
  }

  function renderRow(r, i) {
    const modelAmount = model.lineAmount(r);
    const bad = modelAmount === null;
    const bg = bad ? 'row-bad' : (S.expanded === r.id ? 'row-selected' : '');
    const covered = !!S.confirmedReceipt && ['DEMO-105', 'DEMO-106', 'DEMO-107'].includes(r.id);

    let mismatchDiff = null;
    if (r.pastedAmountVnd !== null && r.pastedAmountVnd !== undefined && modelAmount !== null) {
      const excess = model.allocateReceipt(r.pastedAmountVnd, [{ key: 'k', kind: 'closed', balanceVnd: modelAmount.toString() }]).overpaymentVnd;
      const shortfall = model.allocateReceipt(modelAmount.toString(), [{ key: 'k', kind: 'closed', balanceVnd: r.pastedAmountVnd }]).overpaymentVnd;
      const diff = excess > 0n ? excess : shortfall;
      if (diff > 0n) mismatchDiff = diff;
    }
    const mismatch = mismatchDiff !== null;
    const status = r.isNew ? tag('Đang nhập', 'orange') :
      (mismatch ? tag('Lệch tiền · kiểm lại', 'red') :
        (bad ? tag('Thiếu giá', 'red') :
          (covered ? tag(r.id === 'DEMO-105' ? 'Ghi khoản thu' : 'Trong nhóm đã thu', 'green') :
            tag(S.simulatedClosed ? 'Đã chốt' : 'Chưa chốt', S.simulatedClosed ? 'green' : 'blue'))));

    const isDraft = !!r.isNew;
    const isEditingPrice = S.editingRow === r.id;
    const priceCell = isDraft ?
      `<input class="cell-input numeric" data-edit-row="${safe(r.id)}" data-col="price" value="${r.unitPriceVnd === null ? '' : safe(r.unitPriceVnd)}" placeholder="Đơn giá" />` :
      (isEditingPrice ?
        `<input class="cell-input numeric" data-edit-row="${safe(r.id)}" data-col="price" value="${r.unitPriceVnd === null ? '' : safe(r.unitPriceVnd)}" placeholder="Đơn giá" autofocus />` :
        `<button class="container-link numeric" data-action="row-edit" data-value="${safe(r.id)}" style="display:inline-block;width:100%;text-align:right;font-weight:750;color:inherit;text-decoration:none;min-height:40px;padding:0">${moneyCell(r.unitPriceVnd)}</button>`);

    const tr = `<tr class="${bg} ${S.editingPayment && r.id === 'DEMO-105' ? 'payment-edit' : ''}">
      <td class="idx">${i + 1}</td>
      <td>${isDraft ? `<input class="cell-input" data-edit-row="${safe(r.id)}" data-col="id" value="${safe(r.id)}" aria-label="Số container" />` : `<button class="container-link" data-action="expand-row" data-value="${safe(r.id)}">${safe(r.id)}</button>`}</td>
      <td>${isDraft ? `<input class="cell-input" data-edit-row="${safe(r.id)}" data-col="date" value="${safe(r.date)}" aria-label="Ngày chuyến" />` : safe(r.date)}</td>
      <td class="numeric">${priceCell}</td>
      <td class="numeric ${bad ? 'warning-text' : ''}">${bad ? '<span class="invalid-cell">Chưa có dữ liệu</span>' : fmtVnd(modelAmount)}${mismatch ? `<div class="small-info">Bảng tính: ${fmtVnd(r.pastedAmountVnd)} · lệch ${fmtVnd(mismatchDiff)}, kiểm lại</div>` : ''}</td>
      ${payCells(r)}
      <td>${status}</td>
      <td><button class="dot-btn" aria-label="Thao tác dòng ${safe(r.id)}" data-action="row-menu" data-value="${safe(r.id)}">⋮</button></td>
    </tr>`;

    const detailItems = [
      ['Hãng tàu', 'carrier', r.carrier],
      ['Nơi đi', 'from', r.from],
      ['Nơi đến', 'to', r.to],
      ['Phí khác', 'otherFeeVnd', moneyCell(r.otherFeeVnd)],
      ['Phí cắm điện cảng', 'plugFeeVnd', moneyCell(r.plugFeeVnd)],
      ['Phí áp tải', 'escortFeeVnd', moneyCell(r.escortFeeVnd)],
      ['Tham chiếu', 'receipt', '—']
    ];
    const details = S.expanded === r.id ? `<tr class="expanded-row"><td colspan="11"><div class="details">${detailItems.map(([name, key, val]) => `<div><label>${safe(name)}</label>${isDraft && key !== 'receipt' ? `<input data-edit-row="${safe(r.id)}" data-col="${key}" value="${safe(val === '—' ? '' : val)}" />` : `<strong>${safe(val || '—')}</strong>`}</div>`).join('')}
      <div class="formula-detail">Thành tiền = Đơn giá + Phí khác + Phí cắm điện cảng + Phí áp tải<br/>${moneyCell(r.unitPriceVnd)} + ${r.otherFeeVnd === null ? '—' : fmtVnd(r.otherFeeVnd)} + ${r.plugFeeVnd === null ? '—' : fmtVnd(r.plugFeeVnd)} + ${r.escortFeeVnd === null ? '—' : fmtVnd(r.escortFeeVnd)} = ${modelAmount === null ? 'Chưa có dữ liệu' : fmtVnd(modelAmount)}. Phí trống là không phát sinh phí.</div>
      </div><div class="details-bottom"><span>${r.id === 'DEMO-103' ? `${fmtVnd('5000000')} được ghi tại dòng DEMO-103, là khoản thu của sổ tháng 04; chưa có ngày nhận tiền nên chưa xác nhận.` : 'Bung chi tiết đầy đủ mà không cần bật cột cho cả bảng.'}</span><button data-action="expand-row" data-value="${safe(r.id)}" class="btn">Thu gọn</button></div></td></tr>` : '';

    const menu = S.openMenu === r.id ? `<tr class="row-menu-tr"><td colspan="11"><div class="row-menu-actions"><strong style="margin-right:auto;color:#486580">${safe(r.id)} · Thao tác trên chuyến</strong><button class="btn" data-action="row-expand" data-value="${safe(r.id)}">Bung chi tiết</button><button class="btn" data-action="row-payment" data-value="${safe(r.id)}">Ghi tiền thu</button><button class="btn danger" data-action="row-remove" data-value="${safe(r.id)}">Bỏ dòng</button></div></td></tr>` : '';

    const paymentInfo = S.editingPayment && r.id === 'DEMO-105' ? `<tr><td colspan="11" style="padding:0">
      <div class="receipt-action"><span><strong>Ghi tại dòng DEMO-105</strong> · khoản thu thuộc sổ KHACH_MAU · thanh long, tháng 04.2026. Nhập đủ bốn trường ngay trên dòng.</span><button data-action="payment-cancel" class="btn">Hủy</button><button data-action="payment-preview" class="btn primary">Xem kết quả mô phỏng</button></div>
      ${S.paymentError ? `<div class="validation" role="alert">${safe(S.paymentError)}</div>` : ''}
    </td></tr>` : '';

    return tr + paymentInfo + details + menu;
  }

  function renderMainLedger() {
    if (S.selected !== 'KHACH_MAU') return `<div class="scene-note"><strong>${safe(S.selected)}</strong> đang được chọn. Để xem dữ liệu chi tiết đã được cung cấp trong brief, chọn lại KHACH_MAU; các sổ khác chỉ có số tổng minh họa.</div>`;
    const b = balance();
    const totals = model.monthTotals(rowsNow());
    return `${renderSummary()}${renderHistorical()}<section class="month current"><button class="month-head" data-action="expand-month" data-value="04.2026">
      <span class="month-name"><span class="triangle ${S.expandedMonths.has('04.2026') ? 'down' : ''}"></span><strong>THÁNG 04.2026</strong>${tag(S.simulatedClosed ? 'Đã chốt' : 'Đang mở · chưa chốt', S.simulatedClosed ? 'green' : 'blue')}</span>
      <span class="month-number">${totals.pricedCount} chuyến có giá <strong>· ${fmtVnd(totals.pricedTotalVnd)}</strong></span></button>
      ${S.expandedMonths.has('04.2026') ? `<div class="actions">
        <button class="btn primary" data-action="open-paste">▤ Dán từ bảng tính</button>
        <button class="btn" data-action="new-row">＋ Thêm dòng</button><span class="action-hint">Dán trực tiếp 11 cột vào dòng trống cuối bảng</span>
        <button class="btn action-last" data-action="open-close">Chốt công nợ tháng 04</button>
      </div><div class="table-scroll"><table class="ledger"><thead><tr>
        <th class="idx">STT</th><th class="con">Số container</th><th class="date">Ngày</th><th class="price numeric">Đơn giá</th>
        <th class="amount numeric">Thành tiền</th><th class="datepay">Ngày nhận tiền</th><th class="method">Cách thu</th>
        <th class="ref">Tham chiếu</th><th class="paid numeric">Đã thu</th><th class="state">Tình trạng</th><th class="extra"></th>
      </tr></thead><tbody>${rowsNow().map(renderRow).join('')}
      <tr class="add-row"><td class="idx">${rowsNow().length + 1}</td><td colspan="10"><textarea class="inline-paste-area" data-action="inline-paste" rows="1" placeholder="Dán trực tiếp từ Sheet: 11 cột, tối đa 50 dòng. Click vào đây rồi Ctrl+V…" aria-label="Dán trực tiếp chuyến vào dòng trống">${safe(S.inlinePasteInput)}</textarea></td></tr>
      </tbody></table></div>${S.inlineFeedback ? `<div class="paste-feedback">${safe(S.inlineFeedback)}</div>` : ''}${S.importWarnings.length ? `<div class="notice">${S.importWarnings.map(safe).join('<br/>')}</div>` : ''}
      <div class="totals">
        <div class="total-line"><span class="total-label">Số dư tháng chuyển sang</span><span class="total-value">${fmtVnd('95000000')}</span></div>
        <div class="total-line"><span class="total-label">Phát sinh tháng 04 · ${totals.pricedCount} chuyến có giá</span><span class="total-value">${fmtVnd(totals.pricedTotalVnd)}</span></div>
        <div class="total-line"><span class="total-label">Đã thu trong tháng (đã ghi nhận)</span><span class="total-value">${b.receivedVnd > 0n ? fmtVnd(b.receivedVnd) : '—'}</span></div>
        <div class="total-line"><span class="total-label"><strong>Còn phải thu cuối tháng</strong>${b.overpaymentVnd > 0n ? ' · khách trả dư · phải trả lại' : ' (phần đã chốt)'}</span><span class="total-value ${b.overpaymentVnd > 0n ? 'overpaid-text' : ''}">${fmtVnd(b.endOfMonthVnd)}</span></div>
        <div class="total-line highlight"><span class="total-label">Đang mở · chưa chốt</span><span class="total-value">${fmtVnd(b.openRemainingVnd)}${!S.simulatedClosed && totals.pricedTotalVnd > 0n && b.openRemainingVnd === 0n ? ' · đã thu đủ' : ''}</span></div>
        ${b.receivedVnd > 0n ? `<div style="padding-top:12px;display:flex;justify-content:flex-end"><button data-action="allocation" class="allocation-link">Xem phân bổ khoản thu ${fmtVnd(b.receivedVnd)} theo từng tháng →</button></div>` : ''}
      </div><div class="notice">${S.unconfirmedReceipts.length ? `Chứng từ ${fmtVnd(S.unconfirmedReceipts[0].amountVnd)} · ${safe(S.unconfirmedReceipts[0].id)} ghi tại dòng DEMO-103 chưa có ngày nhận tiền: <strong>chưa xác nhận, không tính vào số dư</strong>.` : 'Không có chứng từ chưa xác nhận.'} ${totals.missingPriceIds.includes('DEMO-103') ? 'DEMO-103 còn thiếu giá, chưa được tính vào phát sinh.' : ''}</div>` : ''}</section>`;
  }

  function renderTotal() {
    const b = balance();
    const data = [
      { name: 'KHACH_MAU', cat: 'Thanh long', brought: '95000000', origin: S.simulatedClosed ? model.monthTotals(rowsNow()).pricedTotalVnd : null, paid: b.receivedVnd > 0n ? b.receivedVnd : null, closed: b.endOfMonthVnd, open: b.openRemainingVnd, cont: rowsNow().length, status: S.simulatedClosed ? 'closed' : 'open' },
      ...currentClients().filter(c => c.id !== 'KHACH_MAU').map(c => ({ ...c, name: c.id, cat: c.category })),
    ];
    return `<div class="demo-strip"><strong>TỔNG · THÁNG 04.2026</strong><span>Bấm một khách để mở sổ của khách đó.</span></div><div class="table-card"><table class="total-table"><thead><tr><th>Loại hàng</th><th>Khách</th><th>Số dư chuyển sang</th><th>Phát sinh đã chốt</th><th>Đã thu</th><th>Còn phải thu cuối tháng</th><th>Đang mở</th><th>Số cont</th><th>Trạng thái</th></tr></thead><tbody>
    ${data.map(d => `<tr data-action="customer" data-value="${d.name}"><td>${d.cat}</td><td><strong>${d.name}</strong></td><td class="numeric">${fmtVnd(d.brought)}</td><td class="numeric">${moneyCell(d.origin)}</td><td class="numeric">${moneyCell(d.paid)}</td><td class="numeric">${fmtVnd(d.closed)}</td><td class="numeric">${d.open !== 0n ? fmtVnd(d.open) : '—'}</td><td>${d.cont ?? '—'}</td><td>${tag(statusName(d.status), statusColor(d.status))}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function renderModal() {
    if (S.showDeleteBlock) {
      const pending = S.unconfirmedReceipts.filter(r => r.enteredAt === (S.pendingDelete || 'DEMO-103'));
      return `<div class="overlay" role="dialog" aria-modal="true"><div class="dialog small"><div class="dialog-head"><h2>Xác nhận bỏ chuyến ${safe(S.pendingDelete || 'DEMO-103')}</h2><button class="x-close" data-action="close-modal">×</button></div><div class="dialog-body">
      <p>Bạn muốn bỏ dòng chuyến <strong>${safe(S.pendingDelete || 'DEMO-103')}</strong> khỏi tháng 04.2026?</p>
      ${pending.length ? `<div class="validation"><strong>Đồng thời bỏ chứng từ chưa xác nhận ${safe(pending[0].id)} · ${fmtVnd(pending[0].amountVnd)}</strong>, được ghi tại dòng này. Khoản thu này thuộc sổ KHACH_MAU · thanh long và tháng 04.2026, không phải tiền thuộc riêng chuyến.</div>` : ''}
      <p>Việc bỏ chuyến và chứng từ chưa xác nhận sẽ được <strong>lưu vết</strong> trong bản mô phỏng. Khoản thu <strong>đã xác nhận</strong> không được bỏ theo cách này, phải đảo riêng.</p>
      </div><div class="dialog-footer"><button class="btn" data-action="close-modal">Giữ lại</button><button class="btn danger" data-action="confirm-delete" data-value="${safe(S.pendingDelete || 'DEMO-103')}">Bỏ dòng và chứng từ chưa xác nhận</button></div></div></div>`;
    }
    if (S.modal === 'paste') {
      return `<div class="overlay" role="dialog" aria-modal="true"><div class="dialog"><div class="dialog-head"><h2>Dán từ bảng tính</h2><button class="x-close" data-action="close-modal">×</button></div><div class="dialog-body">
      <p><strong>KHACH_MAU · thanh long · THÁNG 04.2026</strong> — dữ liệu dán vào tháng này, không chọn kỳ riêng.</p><div class="paste-layout"><div><strong>11 cột theo thứ tự khi dán</strong><ol class="columns-list">${['STT (tự đánh, bỏ qua khi dán)', 'Số container', 'Hãng tàu', 'Ngày', 'Nơi đi', 'Nơi đến', 'Phí khác', 'Phí cắm điện cảng', 'Phí áp tải', 'Đơn giá', 'Thành tiền (chỉ để đối chiếu)'].map((v, i) => `<li><span>${i + 1}</span>${v}</li>`).join('')}</ol></div>
      <div><label class="field-label" for="paste-data">Dán dữ liệu từ bảng tính vào đây…</label><textarea id="paste-data" class="paste-area" data-action="paste-text" placeholder="1[TAB]DEMO-109[TAB]WH[TAB]20/04/2026[TAB]...">${safe(S.pasteInput)}</textarea>
      <div class="box-note">Tối đa 50 dòng mỗi lần dán · Không dán cột tiền thu. Thành tiền tự cộng; Thành tiền từ Sheet chỉ dùng đối chiếu, nếu lệch sẽ báo “lệch X, kiểm lại”, không tự sửa hoặc bỏ dòng.</div>
      ${S.pasteMessage ? `<div class="validation ${S.pasteOk ? 'good' : ''}">${safe(S.pasteMessage)}</div>` : ''}</div></div></div><div class="dialog-footer"><button data-action="close-modal" class="btn">Hủy</button><button data-action="paste-submit" class="btn primary">Kiểm tra và thêm vào sổ</button></div></div></div>`;
    }
    if (S.modal === 'close') {
      const closeCheck = model.canClose({ lines: rowsNow(), enteredBy: 'Nguyễn Văn A', closedBy: S.actor });
      const errors = [...closeCheck.reasons];
      const pr = model.monthTotals(rowsNow());
      return `<div class="overlay" role="dialog" aria-modal="true"><div class="dialog small"><div class="dialog-head"><h2>${errors.length ? 'Không thể chốt công nợ tháng 04' : 'Xem lại để chốt công nợ tháng 04'}</h2><button class="x-close" data-action="close-modal">×</button></div><div class="dialog-body">
      <p>Đăng nhập: <strong>${safe(roleName())}</strong> · ${safe(roleTitle())}</p><div class="review-stats"><div><small>Chuyến có giá</small><strong>${pr.pricedCount}</strong></div><div><small>Tổng phát sinh</small><strong>${fmtVnd(pr.pricedTotalVnd)}</strong></div><div><small>Dòng thiếu giá</small><strong>${pr.missingPriceIds.length}</strong></div></div>
      ${errors.length ? `<div class="validation"><strong>Không thể chốt vì ${errors.length} lý do:</strong><ol class="blockers">${errors.map(e => `<li>${safe(e)}</li>`).join('')}</ol></div>` : `<p>Người chốt: <strong>${safe(roleName())}</strong>. Chốt cả tháng, không chốt từng chuyến.</p>
      <div class="box-note">DEMO-103 được bổ sung đơn giá giả định ${fmtVnd('15000000')}. <strong>Chốt tháng vẫn được phép khi chứng từ ${S.unconfirmedReceipts[0]?.id || 'CT-CHO-05'} · ${fmtVnd('5000000')} chưa xác nhận.</strong> Sau chốt, chứng từ vẫn treo và vẫn ngoài số dư.</div>`}
      ${S.modalNotice ? `<div class="validation">${safe(S.modalNotice)}</div>` : ''}
      </div><div class="dialog-footer"><button data-action="close-modal" class="btn">Quay lại sổ</button>${!errors.length ? '<button class="btn primary" data-action="close-sim">Chốt công nợ tháng 04</button>' : ''}</div></div></div>`;
    }
    return '';
  }

  function renderDrawer() {
    if (S.drawer !== 'allocation') return '';
    const receipt = S.confirmedReceipt;
    if (!receipt) return '';
    const b = balance();
    const openVnd = model.monthTotals(rowsNow()).pricedTotalVnd.toString();
    const buckets = [
      { key: 'before-T01', kind: 'closed', balanceVnd: '20000000' },
      { key: 'T01', kind: 'closed', balanceVnd: '20000000' },
      { key: 'T02', kind: 'closed', balanceVnd: '30000000' },
      { key: 'T03', kind: 'closed', balanceVnd: '25000000' },
      { key: 'T04', kind: S.simulatedClosed ? 'closed' : 'open', balanceVnd: openVnd },
    ];
    const { allocations, overpaymentVnd } = model.allocateReceipt(receipt.amountVnd, buckets);
    const allocMap = {};
    for (const a of allocations) allocMap[a.key] = a.amountVnd;
    const closedAllocatedVnd = model.monthTotals(allocations.filter(a => a.kind === 'closed').map(a => ({
      unitPriceVnd: a.amountVnd, otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null,
    }))).pricedTotalVnd;
    const closedSubtotal = `<tr class="sub"><td>${b.closedRemainingVnd === 0n ? 'Hết phần đã chốt' : 'Phần đã chốt'}</td><td>${fmtVnd(closedAllocatedVnd)}</td></tr>`;

    return `<div class="drawer-shade" data-action="drawer-close"></div><aside class="drawer"><div class="dialog-head"><h2>Phân bổ khoản thu ${fmtVnd(receipt.amountVnd)}</h2><button class="x-close" data-action="drawer-close">×</button></div><div class="dialog-body">
      <p><strong>Ngày nhận tiền:</strong> ${safe(receipt.date)}<br/><strong>Cách thu:</strong> ${safe(receipt.method)}<br/><strong>Tham chiếu:</strong> ${safe(receipt.ref)}<br/><strong>Ghi tại dòng:</strong> DEMO-105 · sổ KHACH_MAU · thanh long · tháng 04.2026<br/><strong>Phủ nhóm:</strong> DEMO-105, DEMO-106, DEMO-107</p>
      <table class="alloc-table"><thead><tr><th>Phân bổ vào</th><th>Số tiền</th></tr></thead><tbody>
        <tr><td>Số dư trước tháng 01.2026</td><td>${fmtVnd(allocMap['before-T01'] ?? 0n)}</td></tr>
        <tr><td>Tháng 01.2026</td><td>${fmtVnd(allocMap['T01'] ?? 0n)}</td></tr>
        <tr><td>Tháng 02.2026</td><td>${fmtVnd(allocMap['T02'] ?? 0n)}</td></tr>
        <tr><td>Tháng 03.2026</td><td>${fmtVnd(allocMap['T03'] ?? 0n)}</td></tr>
        ${S.simulatedClosed ? '' : closedSubtotal}
        <tr><td>Tháng 04.2026 · ${S.simulatedClosed ? 'đã chốt' : 'đang mở'}</td><td>${fmtVnd(allocMap['T04'] ?? 0n)}</td></tr>
        ${S.simulatedClosed ? closedSubtotal : ''}
        ${overpaymentVnd > 0n ? `<tr class="sub"><td>Không còn nợ để trừ · trả dư</td><td>${fmtVnd(overpaymentVnd)}</td></tr>` : ''}
        <tr class="grand"><td>Tổng khoản thu</td><td>${fmtVnd(receipt.amountVnd)}</td></tr></tbody></table>
      <div class="${overpaymentVnd > 0n ? 'validation' : 'validation good'}">Đã chốt: <strong>${fmtVnd(b.closedRemainingVnd)}</strong>${b.closedRemainingVnd === 0n ? ' · đã thu đủ' : ''}. Đang mở: <strong>${fmtVnd(b.openRemainingVnd)}</strong>${!S.simulatedClosed && openVnd !== '0' && b.openRemainingVnd === 0n ? ' · đã thu đủ' : ''}.
        ${overpaymentVnd > 0n ? `<p class="overpaid-text">Còn phải thu cuối tháng: ${fmtVnd(b.endOfMonthVnd)} · khách trả dư · phải trả lại.</p><p>Khoản dư chỉ nằm trong sổ KHACH_MAU · thanh long; không tự chuyển sang sổ khác.</p>` : ''}</div>
      <p>Số dư lịch sử tháng 01 / 02 / 03 vẫn giữ nguyên ${historical.map(h => fmtVnd(h.balance)).join(' / ')}.</p>
    </div></aside>`;
  }

  function renderScreen() {
    return `<div class="app">${renderSidebar()}<main class="main">${renderTop()}<div class="content"><div class="demo-strip"><strong>Chỉ mô phỏng · không kết nối dữ liệu thật</strong><span>THÁNG 04.2026</span></div>${S.tab === 'total' ? renderTotal() : renderMainLedger()}${S.audit.length ? `<div class="audit-box"><strong>Lịch sử thao tác trong trang:</strong>${S.audit.map(a => `<div>${safe(a)}</div>`).join('')}</div>` : ''}</div></main></div>${renderModal()}${renderDrawer()}`;
  }

  function render() {
    const invalid = document.querySelector('[data-edit-row]:invalid');
    if (invalid) { invalid.reportValidity(); return; }
    document.getElementById('app').innerHTML = `<section id="khung-01" class="scene-frame">${renderScreen()}</section>${renderOutsideNotes()}`;
  }

  function renderOutsideNotes() {
    return `<aside class="external-notes"><strong>Điểm còn mở (ghi chú ngoài màn hình)</strong><ol>
    <li>Thứ tự 11 cột của bảng tính nguồn chưa được đối chiếu thực tế.</li>
    <li>Ai được xác nhận chứng từ và cần căn cứ gì: hiện hoãn, chưa thiết kế nút xác nhận.</li>
    <li>Tiền khách trả dư nằm ở sổ khách × loại hàng này, mặc định không tự dùng cho sổ khác.</li>
    <li>Sổ “chưa mở” có tính là “chưa chốt” không: khung 08 tạm không tính.</li>
    </ol><p>Trang mô phỏng dùng dữ liệu giả trong bộ nhớ, không lưu hoặc thay đổi công nợ thật.</p></aside>`;
  }

  function setPayFromDOM() {
    document.querySelectorAll('[data-pay]').forEach(el => {
      S.paymentDraft[el.dataset.pay] = el.value;
    });
  }

  function checkPaste(text = S.pasteInput) {
    const lines = (text || '').replace(/\r/g, '').split('\n');
    while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
    if (!lines.length) {
      S.pasteMessage = 'Chưa có dữ liệu để dán.';
      S.pasteOk = false;
      return null;
    }
    if (lines.length > 50) {
      S.pasteMessage = 'Tối đa 50 dòng mỗi lần dán. Không nhận dòng nào.';
      S.pasteOk = false;
      return null;
    }
    const incoming = [];
    const warnings = [];
    for (let i = 0; i < lines.length; i++) {
      const f = lines[i].split('\t');
      if (f.length !== 11) {
        S.pasteMessage = `Dòng ${i + 1}: cần đúng 11 cột, đang có ${f.length}. Không nhận dòng nào.`;
        S.pasteOk = false;
        return null;
      }
      const id = f[1].trim();
      const date = f[3].trim();
      if (!id || !dateValid(date)) {
        S.pasteMessage = `Dòng ${i + 1}: thiếu số container hoặc ngày không hợp lệ. Không nhận dòng nào.`;
        S.pasteOk = false;
        return null;
      }
      let amounts;
      try { amounts = f.slice(6).map(parseDigits); }
      catch (error) {
        S.pasteMessage = `Dòng ${i + 1}: ${error.message} Không nhận dòng nào.`;
        S.pasteOk = false;
        return null;
      }
      const row = {
        id,
        carrier: f[2].trim(),
        date,
        from: f[4].trim(),
        to: f[5].trim(),
        otherFeeVnd: amounts[0],
        plugFeeVnd: amounts[1],
        escortFeeVnd: amounts[2],
        unitPriceVnd: amounts[3],
        pastedAmountVnd: amounts[4],
      };
      if (row.unitPriceVnd === null) {
        warnings.push(`Dòng ${i + 1} (${row.id}): chưa có giá.`);
      }
      const modelAmount = model.lineAmount(row);
      if (row.pastedAmountVnd !== null && modelAmount !== null) {
        const excess = model.allocateReceipt(row.pastedAmountVnd, [{ key: 'k', kind: 'closed', balanceVnd: modelAmount.toString() }]).overpaymentVnd;
        const shortfall = model.allocateReceipt(modelAmount.toString(), [{ key: 'k', kind: 'closed', balanceVnd: row.pastedAmountVnd }]).overpaymentVnd;
        const diff = excess > 0n ? excess : shortfall;
        if (diff > 0n) {
          warnings.push(`Dòng ${i + 1} (${row.id}): Thành tiền bảng tính ${fmtVnd(row.pastedAmountVnd)}, thành tiền tự cộng ${fmtVnd(modelAmount)}, lệch ${fmtVnd(diff)}, kiểm lại.`);
        }
      }
      incoming.push(row);
    }
    S.importWarnings = warnings;
    S.pasteOk = true;
    S.pasteMessage = `Đã đọc ${incoming.length} dòng. ${warnings.length ? warnings.join(' ') : 'Thành tiền khớp với số tự cộng.'} ${warnings.length ? 'Giữ nguyên dữ liệu dán để kiểm tra, không tự sửa hoặc bỏ dòng.' : ''}`;
    return incoming;
  }

  function previewPayment() {
    if (S.confirmedReceipt) return;
    setPayFromDOM();
    const p = S.paymentDraft;
    let amount;
    try { amount = parseDigits(p.amount); }
    catch (error) {
      S.paymentError = error.message;
      render();
      document.querySelector('[data-pay="amount"]')?.focus();
      return;
    }
    if (!dateValid(p.date) || !p.method || !p.ref.trim() || amount === null || BigInt(amount) <= 0n) {
      alert('Cần nhập đủ ngày nhận tiền, cách thu, tham chiếu và số tiền nguyên dương.');
      return;
    }
    const parts = p.date.split('/');
    const isoDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
    S.confirmedReceipt = {
      date: p.date,
      method: p.method,
      ref: p.ref,
      amountVnd: amount,
      receivedOn: isoDate,
    };
    S.editingPayment = false;
    S.drawer = null;
    render();
  }

  function openDelete(id) {
    S.pendingDelete = id;
    S.showDeleteBlock = true;
    render();
  }

  function confirmDelete(id) {
    const row = rowsNow().find(r => r.id === id);
    if (!row) return;
    const pending = S.unconfirmedReceipts.filter(r => r.enteredAt === id);
    const approvedReceipt = !!(S.confirmedReceipt && id === 'DEMO-105');
    if (approvedReceipt) {
      alert('Khoản thu đã xác nhận không được bỏ theo thao tác này, phải đảo riêng.');
      return;
    }
    S.rows = S.rows.filter(r => r.id !== id);
    S.customRows = S.customRows.filter(r => r.id !== id);
    S.unconfirmedReceipts = S.unconfirmedReceipts.filter(r => r.enteredAt !== id);
    S.audit.push(`17/10/2026 · ${roleName()} bỏ dòng ${id}${pending.length ? ` và bỏ ${pending.length} chứng từ chưa xác nhận (${pending.map(r => r.id + ' · ' + fmtVnd(r.amountVnd)).join(', ')})` : ''}.`);
    S.showDeleteBlock = false;
    S.pendingDelete = null;
    S.modal = null;
    render();
  }

  document.addEventListener('paste', ev => {
    if (ev.target.dataset.action !== 'inline-paste') return;
    if (S.simulatedClosed) { ev.preventDefault(); return; }
    const content = ev.clipboardData?.getData('text/plain') || '';
    if (!content) return;
    ev.preventDefault();
    const incoming = checkPaste(content);
    S.inlinePasteInput = incoming ? '' : content;
    if (incoming) {
      S.customRows.push(...incoming);
      S.inlineFeedback = `Đã thêm ${incoming.length} chuyến vào tháng 04 (chỉ trong bản mẫu).`;
    } else {
      S.inlineFeedback = S.pasteMessage;
    }
    render();
  });

  document.addEventListener('input', ev => {
    if (ev.target.dataset.editRow) {
      if (S.simulatedClosed) return;
      const field = ev.target.dataset.col;
      const id = ev.target.dataset.editRow;
      const row = rowsNow().find(r => r.id === id);
      if (row) {
        let amount;
        if (['price', 'unitPriceVnd', 'other', 'plug', 'escort', 'otherFeeVnd', 'plugFeeVnd', 'escortFeeVnd'].includes(field)) {
          try {
            amount = parseDigits(ev.target.value);
            ev.target.setCustomValidity('');
          } catch (error) {
            ev.target.setCustomValidity(error.message);
            ev.target.reportValidity();
            return;
          }
        }
        if (field === 'price' || field === 'unitPriceVnd') {
          row.unitPriceVnd = amount;
        } else if (['other', 'plug', 'escort', 'otherFeeVnd', 'plugFeeVnd', 'escortFeeVnd'].includes(field)) {
          const map = { other: 'otherFeeVnd', plug: 'plugFeeVnd', escort: 'escortFeeVnd', otherFeeVnd: 'otherFeeVnd', plugFeeVnd: 'plugFeeVnd', escortFeeVnd: 'escortFeeVnd' };
          row[map[field]] = amount;
        } else if (field === 'id') {
          row.id = ev.target.value;
          ev.target.dataset.editRow = row.id;
        } else {
          row[field] = ev.target.value;
        }
      }
    }
    if (ev.target.dataset.pay) S.paymentDraft[ev.target.dataset.pay] = ev.target.value;
    if (ev.target.dataset.action === 'paste-text') S.pasteInput = ev.target.value;
    if (ev.target.dataset.action === 'actor') {
      S.actor = ev.target.value;
      render();
    }
    if (ev.target.dataset.action === 'search') {
      S.search = ev.target.value;
      const point = ev.target.selectionStart;
      const aside = document.querySelector('.aside-sticky');
      const y = aside?.scrollTop ?? 0;
      render();
      const el = document.querySelector('[data-action="search"]');
      el?.focus();
      if (el) el.setSelectionRange(point, point);
      const afterAside = document.querySelector('.aside-sticky');
      if (afterAside) afterAside.scrollTop = y;
    }
  });

  document.addEventListener('change', ev => {
    if (ev.target.dataset.action === 'actor') {
      S.actor = ev.target.value;
      render();
    }
  });

  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape' && (S.modal || S.showDeleteBlock || S.drawer)) {
      S.modal = null;
      S.showDeleteBlock = false;
      S.drawer = null;
      render();
    }
    if (ev.key === 'Enter' && ev.target.dataset.pay) {
      ev.preventDefault();
      previewPayment();
    }
    if (ev.key === 'Enter' && ev.target.dataset.editRow) {
      ev.preventDefault();
      const invalid = document.querySelector('[data-edit-row]:invalid');
      if (invalid) { invalid.reportValidity(); return; }
      S.editingRow = null;
      S.inlineFeedback = 'Đã cập nhật dòng trong bản mẫu (không có máy chủ lưu dữ liệu).';
      render();
    }
  });

  document.addEventListener('click', ev => {
    const btn = ev.target.closest('[data-action]');
    if (!btn) return;
    const act = btn.dataset.action;
    const v = btn.dataset.value;
    if (S.simulatedClosed && ['open-paste', 'new-row', 'row-edit', 'row-remove', 'confirm-delete', 'paste-submit', 'open-close', 'close-sim'].includes(act)) {
      alert('Tháng đã chốt, không sửa đè.');
      return;
    }
    const invalid = document.querySelector('[data-edit-row]:invalid');
    if (invalid) { invalid.reportValidity(); return; }

    if (act === 'tab') { S.tab = v; render(); return; }
    if (act === 'filter') { S.filter = v; render(); return; }
    if (act === 'customer') { S.selected = v; S.tab = 'ledger'; render(); return; }
    if (act === 'expand-month') {
      if (S.expandedMonths.has(v)) S.expandedMonths.delete(v);
      else S.expandedMonths.add(v);
      render();
      return;
    }
    if (act === 'expand-row') {
      S.expanded = S.expanded === v ? null : v;
      render();
      return;
    }
    if (act === 'open-paste') { S.modal = 'paste'; S.pasteMessage = ''; render(); return; }
    if (act === 'close-modal') { S.modal = null; S.showDeleteBlock = false; render(); return; }
    if (act === 'drawer-close') { S.drawer = null; render(); return; }
    if (act === 'allocation') { S.drawer = 'allocation'; render(); return; }
    if (act === 'payment-cancel') { S.editingPayment = false; render(); return; }
    if (act === 'payment-preview') { previewPayment(); return; }
    if (act === 'open-close') { S.modal = 'close'; render(); return; }
    if (act === 'close-sim') {
      if (!model.canClose({ lines: rowsNow(), enteredBy: 'Nguyễn Văn A', closedBy: S.actor }).ok) return;
      S.simulatedClosed = true; S.editingRow = null; S.modal = null; render(); return;
    }
    if (act === 'new-row') {
      const id = 'DEMO-' + (200 + S.customRows.length);
      S.customRows.push({
        id, carrier: '', date: '22/04/2026', from: '', to: '',
        otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null, unitPriceVnd: null,
        isNew: true
      });
      S.expanded = id;
      render();
      return;
    }
    if (act === 'paste-submit') {
      S.pasteInput = document.getElementById('paste-data')?.value || '';
      const incoming = checkPaste();
      if (incoming) {
        S.customRows.push(...incoming);
        S.modal = null;
        S.expanded = null;
        render();
      } else {
        render();
      }
      return;
    }
    if (act === 'row-menu') {
      S.openMenu = S.openMenu === v ? null : v;
      render();
      return;
    }
    if (act === 'row-expand') {
      S.expanded = v;
      S.openMenu = null;
      render();
      return;
    }
    if (act === 'row-payment') {
      S.openMenu = null;
      if (S.confirmedReceipt) {
        alert('Khoản thu đã ghi nhận không được sửa đè, phải đảo riêng.');
        return;
      }
      if (v !== 'DEMO-105') {
        alert('Ví dụ thu 120 triệu được minh họa trên dòng đầu nhóm DEMO-105.');
        render();
        return;
      }
      S.editingPayment = true;
      S.paymentError = '';
      S.expanded = null;
      render();
      return;
    }
    if (act === 'row-edit') {
      S.editingRow = v;
      render();
      return;
    }
    if (act === 'row-remove') {
      S.openMenu = null;
      openDelete(v);
      return;
    }
    if (act === 'confirm-delete') {
      confirmDelete(v);
      return;
    }
  });

  reset();
  render();
})();
