// Dữ liệu giả cho bản xem "Tổng quan quản lý công nợ" — tên khách và số tiền đều hư cấu.
// Đơn vị đồng. months = còn nợ theo tháng phát sinh năm 2026; older = còn nợ của năm trước (coi như tháng 12).
// lastPay = ngày thu gần nhất (null = chưa thu lần nào); lastTrip = ngày xe nhập kho gần nhất;
// paid / charged = đã thu (theo ngày thu, như sổ khách) và phát sinh trong tháng hiện tại.
// Mọi khối trên trang tính từ đây nên luôn cộng về cùng tổng.
window.MOCK = (() => {
  'use strict';
  const AS_OF = { year: 2026, month: 10, day: 29, label: '29/10/2026' };
  // Quy tắc ĐỀ XUẤT, chờ người dùng chốt: nợ tháng M đến hạn cuối tháng M+1; ngưỡng rủi ro bên dưới.
  const RULE = { dueAfterMonths: 1, longOverdueMonths: 3, noPayDays: 60, noTripDays: 90, activeTripDays: 30 };
  const ROWS = [
    { id: 1, name: 'MAI HOA (GL)', commodity: 'Sầu riêng', transport: 'cảng', months: { 7: 3850000000, 8: 6420000000, 9: 6890000000, 10: 3430000000 }, older: { 2025: 1200000000 }, lastPay: '2026-10-15', lastTrip: '2026-10-27', paid: 2100000000, charged: 3430000000 },
    { id: 2, name: 'LONG THÀNH', commodity: 'Sầu riêng', transport: 'bộ', months: { 8: 4100000000, 9: 4400000000, 10: 3300000000 }, older: {}, lastPay: '2026-10-20', lastTrip: '2026-10-28', paid: 3000000000, charged: 3300000000 },
    { id: 3, name: 'THANH PHÁT', commodity: 'Sầu riêng', transport: 'cảng', months: { 8: 2200000000, 9: 3330000000, 10: 3500000000 }, older: {}, lastPay: '2026-08-25', lastTrip: '2026-10-26', paid: 0, charged: 3500000000 },
    { id: 4, name: 'HẢI NAM', commodity: 'Sầu riêng', transport: 'bộ', months: { 3: 1200000000, 5: 950000000 }, older: {}, lastPay: '2026-06-10', lastTrip: '2026-05-20', paid: 0, charged: 0 },
    { id: 5, name: 'AN NHIÊN', commodity: 'Sầu riêng', transport: 'cảng', months: { 9: 1400000000, 10: 650000000 }, older: {}, lastPay: '2026-10-22', lastTrip: '2026-10-29', paid: 900000000, charged: 650000000 },
    { id: 6, name: 'SÔNG HỒNG', commodity: 'Thanh long', transport: 'bộ', months: { 5: 1100000000, 6: 1250000000, 9: 1450000000 }, older: {}, lastPay: '2026-09-30', lastTrip: '2026-09-24', paid: 0, charged: 0 },
    { id: 7, name: 'GIA PHÁT', commodity: 'Thanh long', transport: null, months: { 7: 350000000, 8: 620000000 }, older: {}, lastPay: '2026-09-12', lastTrip: '2026-08-30', paid: 0, charged: 0 },
    { id: 8, name: 'THẢO VY', commodity: 'Thanh long', transport: null, months: { 10: 420000000 }, older: {}, lastPay: '2026-10-10', lastTrip: '2026-10-24', paid: 300000000, charged: 720000000 },
    { id: 9, name: 'HẢI TRIỀU', commodity: 'Chuối', transport: null, months: { 1: 2300000000, 2: 1700000000, 3: 1600000000 }, older: {}, lastPay: '2026-04-02', lastTrip: '2026-03-28', paid: 0, charged: 0 },
    { id: 10, name: 'BẢO NGỌC', commodity: 'Chuối', transport: null, months: { 9: 280000000, 10: 120000000 }, older: {}, lastPay: '2026-10-18', lastTrip: '2026-10-25', paid: 250000000, charged: 120000000 },
    { id: 11, name: 'ÁNH DƯƠNG', commodity: 'Dừa', transport: null, months: { 2: 1100000000, 3: 1500000000, 4: 1500000000 }, older: {}, lastPay: '2026-09-05', lastTrip: '2026-04-18', paid: 0, charged: 0 },
    { id: 12, name: 'TÂN PHÚ', commodity: 'Dừa', transport: null, months: { 10: 350000000 }, older: {}, lastPay: null, lastTrip: '2026-10-21', paid: 0, charged: 350000000 },
    { id: 18, name: 'PHƯƠNG NAM', commodity: 'Sầu riêng', transport: null, months: { 8: 900000000, 9: 1100000000 }, older: {}, lastPay: '2026-10-02', lastTrip: '2026-09-29', paid: 600000000, charged: 0 },
    { id: 19, name: 'HOÀNG MAI', commodity: 'Mít', transport: null, months: { 10: 45000000 }, older: {}, lastPay: null, lastTrip: '2026-10-17', paid: 0, charged: 45000000 },
    { id: 20, name: 'SAO VIỆT', commodity: 'Bán cước', transport: null, months: { 9: 28000000 }, older: {}, lastPay: '2026-09-15', lastTrip: '2026-09-14', paid: 0, charged: 0 },
    { id: 13, name: 'MAI THẢO', commodity: 'Xoài', transport: null, months: { 8: 310000000, 10: 590000000 }, older: {}, lastPay: '2026-10-12', lastTrip: '2026-10-21', paid: 200000000, charged: 590000000 },
    { id: 14, name: 'ĐÌNH TRUNG', commodity: null, transport: null, months: {}, older: { 2024: 551000000 }, lastPay: '2024-12-20', lastTrip: '2024-11-08', paid: 0, charged: 0 },
    { id: 15, name: 'QUANG MINH', commodity: null, transport: null, months: {}, older: {}, lastPay: '2026-07-03', lastTrip: '2026-06-21', paid: 0, charged: 0 },
    { id: 16, name: 'KIM LAN', commodity: null, transport: null, months: { 10: -350000000 }, older: {}, lastPay: '2026-10-08', lastTrip: '2026-10-03', paid: 1200000000, charged: 850000000 },
    // Khách chưa có số dư đầu: không vào tổng nào, chỉ hiện ở Việc cần làm (DASH-01).
    { id: 17, name: 'PHÚ LONG', commodity: null, transport: null, noBaseline: true, months: {}, older: {} },
  ];
  // Chuyến web thiếu đơn giá / chờ kiểm (DASH-01: dòng sổ gốc thiếu giá không tính).
  const TODO = {
    missingPrice: [{ id: 2, count: 5 }, { id: 1, count: 3 }, { id: 3, count: 2 }, { id: 8, count: 2 }],
    pendingReview: [{ id: 5, count: 1 }, { id: 13, count: 1 }],
  };
  const TODAY = { byActor: [
    { actor: 'Lan', trips: 6, receipts: 2, received: 265000000, voids: 0 },
    { actor: 'Hùng', trips: 4, receipts: 1, received: 147500000, voids: 1 },
  ] };

  const sum = list => list.reduce((total, value) => total + value, 0);
  const nf2 = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const nf1 = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const nfm = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 });
  const full = value => `${Math.round(value).toLocaleString('vi-VN')} đ`;
  const short = value => Math.abs(value) >= 1e9 ? `${nf2.format(value / 1e9)} tỷ`
    : Math.abs(value) >= 1e6 ? `${nfm.format(value / 1e6)} triệu` : full(value);
  const billions = value => nf2.format(value / 1e9);
  const hero = value => [nf1.format(value / 1e9), 'tỷ'];
  const pct = (value, total) => total ? `${nfm.format(value / total * 100)}%` : '—';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);

  const dayNo = (y, m, d) => Date.UTC(y, m - 1, d) / 864e5;
  const daysAgo = iso => iso == null ? null
    : dayNo(AS_OF.year, AS_OF.month, AS_OF.day) - dayNo(+iso.slice(0, 4), +iso.slice(5, 7), +iso.slice(8, 10));
  const dm = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  const dmy = iso => `${dm(iso)}/${iso.slice(0, 4)}`;
  // Khoảng thời gian dễ đọc: tới 90 ngày đếm ngày, lâu hơn đếm tháng.
  const ago = days => days > 90 ? `${Math.floor(days / 30)} tháng` : `${days} ngày`;
  // Tên tháng lùi `back` tháng so với tháng hiện tại: T7 (cùng năm) hoặc T12/2025.
  const monthName = back => {
    const n = AS_OF.year * 12 + AS_OF.month - 1 - back;
    const y = Math.floor(n / 12), m = n % 12 + 1;
    return y === AS_OF.year ? `T${m}` : `T${m}/${y}`;
  };
  const span = (from, to) => from === to ? monthName(from) : `${monthName(to)}–${monthName(from)}`;

  // Nhóm hạn trả của một tháng nợ: số tháng đã quá hạn = khoảng cách tới tháng hiện tại − số tháng được nợ.
  const lateOf = (y, m) => (AS_OF.year - y) * 12 + AS_OF.month - m - RULE.dueAfterMonths;
  const tierOf = late => late < 0 ? 0 : late === 0 ? 1 : late <= 2 ? 2 : late <= 6 ? 3 : 4;
  const due = RULE.dueAfterMonths;
  const lastDay = new Date(Date.UTC(AS_OF.year, AS_OF.month, 0)).getUTCDate();
  const TIERS = [
    { label: 'Chưa đến hạn', span: `nợ ${span(due - 1, 0)}` },
    { label: `Đến hạn ${lastDay}/${AS_OF.month}`, span: `nợ ${monthName(due)}` },
    { label: 'Quá hạn 1–2 tháng', span: `nợ ${span(due + 2, due + 1)}` },
    { label: 'Quá hạn 3–6 tháng', span: `nợ ${span(due + 6, due + 3)}` },
    { label: 'Quá hạn trên 6 tháng', span: `nợ ${monthName(due + 7)} trở về trước` },
  ];

  const transportText = row => row.commodity && row.transport ? ` · ${row.transport}` : '';
  const comText = row => row.commodity ? `${row.commodity}${transportText(row)}` : 'Chưa có mặt hàng';
  // Như Tổng quan hiện có: chỉ sầu riêng tách cảng/bộ; thiếu mặt hàng hoặc sầu riêng chưa ghi cảng/bộ là "Chưa phân loại".
  const comKey = row => row.commodity == null || (row.commodity === 'Sầu riêng' && !row.transport) ? 'Chưa phân loại'
    : row.commodity === 'Sầu riêng' ? `Sầu riêng ${row.transport}` : row.commodity;

  function derive(row) {
    const months = [
      ...Object.entries(row.older).map(([y, value]) => ({ label: `Năm ${y}`, name: y, value, tier: tierOf(lateOf(+y, 12)), order: +y * 100 + 12 })),
      ...Object.entries(row.months).map(([m, value]) => ({ label: `Tháng ${m}/${AS_OF.year}`, name: `T${m}/${AS_OF.year}`, value, tier: tierOf(lateOf(AS_OF.year, +m)), order: AS_OF.year * 100 + +m })),
    ].sort((a, b) => a.order - b.order);
    const tiers = [0, 0, 0, 0, 0];
    for (const item of months) tiers[item.tier] += item.value;
    const total = sum(tiers);
    const overdue = tiers[2] + tiers[3] + tiers[4];
    const longOverdue = tiers[3] + tiers[4];
    const open = months.filter(item => item.value > 0);
    const oldest = open[0]?.name ?? '';
    const oldestLate = open.find(item => item.tier >= 2)?.name ?? '';
    const payDays = daysAgo(row.lastPay);
    const tripDays = daysAgo(row.lastTrip);
    const risk = overdue <= 0 ? 'ok'
      : longOverdue > 0 || payDays == null || payDays > RULE.noPayDays || tripDays == null || tripDays > RULE.noTripDays ? 'high' : 'watch';
    // Một dòng lý do ngắn: dấu hiệu rủi ro trước, thông tin bình thường (có trả gần đây) chỉ khi không có dấu hiệu.
    const signals = [];
    if (longOverdue > 0) signals.push(`Nợ từ ${oldest}`);
    if (payDays == null) signals.push('chưa trả lần nào');
    else if (payDays > RULE.noPayDays) signals.push(`${ago(payDays)} chưa trả`);
    if (tripDays != null && tripDays > RULE.noTripDays) signals.push('ngừng đi hàng');
    else if (risk === 'high' && tripDays != null && tripDays <= RULE.activeTripDays) signals.push('vẫn đi hàng');
    const paidText = row.lastPay ? `có trả ${dm(row.lastPay)}` : 'chưa trả lần nào';
    const why = risk === 'high' ? signals : [overdue > 0 ? `Nợ ${oldestLate} quá hạn` : 'Trong hạn', paidText];
    const pay = payDays == null ? 'never' : payDays <= 30 ? 'p30' : payDays <= RULE.noPayDays ? 'p60' : 'p61';
    const trip = tripDays == null || tripDays > RULE.noTripDays ? 't91' : tripDays > RULE.activeTripDays ? 't90' : 't30';
    const text = why.join(' · ');
    return { ...row, months, tiers, total, overdue, longOverdue, oldest, oldestLate, payDays, tripDays, risk, why: text.charAt(0).toUpperCase() + text.slice(1), pay, trip };
  }

  // Câu giải thích trong ngăn kéo khách: vì sao khách ở mức rủi ro này.
  function reasons(row) {
    const out = [row.longOverdue > 0 ? `Còn ${short(row.longOverdue)} quá hạn từ 3 tháng trở lên (nợ từ ${row.oldest})`
      : row.overdue > 0 ? `Quá hạn ${short(row.overdue)} (nợ ${row.oldestLate})` : 'Chưa có nợ quá hạn'];
    out.push(row.lastPay ? `Trả gần nhất ${dmy(row.lastPay)} — ${row.payDays ? `${ago(row.payDays)} trước` : 'hôm nay'}` : 'Chưa trả lần nào');
    out.push(row.lastTrip ? `Đi hàng gần nhất ${dmy(row.lastTrip)} — ${row.tripDays > RULE.noTripDays ? 'đã ngừng đi hàng' : row.tripDays > RULE.activeTripDays ? 'ít đi hàng' : 'vẫn đi hàng'}` : 'Chưa có chuyến');
    return out;
  }

  const ledger = ROWS.filter(row => !row.noBaseline).map(derive);
  const debtors = ledger.filter(row => row.total > 0).sort((a, b) => b.total - a.total);
  const creditors = ledger.filter(row => row.total < 0);
  const receivable = sum(debtors.map(row => row.total));
  debtors.forEach((row, index) => { row.size = index < 5 ? 'top5' : index < 10 ? 'next5' : 'rest'; });

  // Mặt hàng dưới 1% còn phải thu gom vào "Khác"; "Khác" và "Chưa phân loại" luôn ở cuối.
  const comTotals = new Map();
  for (const row of debtors) comTotals.set(comKey(row), (comTotals.get(comKey(row)) ?? 0) + row.total);
  for (const row of debtors) {
    const key = comKey(row);
    row.com = key !== 'Chưa phân loại' && comTotals.get(key) / receivable < 0.01 ? 'Khác' : key;
  }
  const comClasses = [...new Set(debtors.map(row => row.com))]
    .map(key => ({ key, label: key, tone: key === 'Khác' || key === 'Chưa phân loại' ? 'grey' : '', total: sum(debtors.filter(row => row.com === key).map(row => row.total)) }))
    .sort((a, b) => (a.tone === 'grey') - (b.tone === 'grey') || (a.key === 'Chưa phân loại') - (b.key === 'Chưa phân loại') || b.total - a.total);

  const group = (field, classes) => classes.map(item => {
    const rows = debtors.filter(row => row[field] === item.key);
    return { ...item, count: rows.length, total: sum(rows.map(row => row.total)), overdue: sum(rows.map(row => row.overdue)), names: rows.map(row => row.name) };
  }).filter(item => item.count);
  const find = (groups, key) => groups.find(item => item.key === key);

  const DIMS = [
    { key: 'risk', tab: 'Rủi ro', title: 'Mức rủi ro', groups: group('risk', [
      { key: 'high', label: 'Rủi ro cao', tone: 'critical' },
      { key: 'watch', label: 'Cần theo dõi', tone: 'warning' },
      { key: 'ok', label: 'Trong hạn' }]),
    lead: groups => { const g = find(groups, 'high'); return g ? `<b>${g.count} khách rủi ro cao</b> đang nợ <b>${short(g.total)}</b>, trong đó quá hạn ${short(g.overdue)}.` : 'Không có khách rủi ro cao.'; } },
    { key: 'pay', tab: 'Lần trả', title: 'Lần trả gần nhất', groups: group('pay', [
      { key: 'p30', label: 'Có trả trong 30 ngày qua' },
      { key: 'p60', label: '31–60 ngày chưa trả', tone: 'warning' },
      { key: 'p61', label: 'Trên 60 ngày chưa trả', tone: 'critical' },
      { key: 'never', label: 'Chưa trả lần nào', tone: 'grey' }]),
    lead: groups => { const g = find(groups, 'p61'); return g ? `<b>${g.count} khách</b> đã hơn 60 ngày chưa trả, đang nợ <b>${short(g.total)}</b>.` : 'Khách nào cũng có trả trong 60 ngày qua.'; } },
    { key: 'trip', tab: 'Đi hàng', title: 'Đi hàng gần nhất', groups: group('trip', [
      { key: 't30', label: 'Đang đi hàng (30 ngày qua)' },
      { key: 't90', label: 'Ít đi hàng (31–90 ngày)', tone: 'grey' },
      { key: 't91', label: 'Ngừng đi hàng (trên 90 ngày)', tone: 'critical' }]),
    lead: groups => { const g = find(groups, 't91'); return g ? `<b>${g.count} khách ngừng đi hàng</b> còn nợ <b>${short(g.total)}</b>.` : 'Khách đang nợ đều còn đi hàng.'; } },
    { key: 'size', tab: 'Quy mô', title: 'Quy mô nợ', groups: group('size', [
      { key: 'top5', label: '5 khách nợ nhiều nhất' },
      { key: 'next5', label: '5 khách tiếp theo' },
      { key: 'rest', label: 'Các khách còn lại', tone: 'grey' }]),
    lead: groups => `5 khách nợ nhiều nhất chiếm <b>${pct(find(groups, 'top5').total, receivable)}</b> tổng còn phải thu.` },
    { key: 'com', tab: 'Mặt hàng', title: 'Mặt hàng', groups: group('com', comClasses),
      lead: groups => `<b>${groups[0].label}</b> chiếm <b>${pct(groups[0].total, receivable)}</b> tổng còn phải thu.` },
  ];

  const tiers = TIERS.map((_, i) => sum(debtors.map(row => row.tiers[i])));
  const overdue = tiers[2] + tiers[3] + tiers[4];
  const high = debtors.filter(row => row.risk === 'high');
  const unsorted = debtors.filter(row => row.com === 'Chưa phân loại');
  const todoIds = new Set([...TODO.missingPrice.map(x => x.id), ...TODO.pendingReview.map(x => x.id),
    ...ROWS.filter(row => row.noBaseline).map(row => row.id), ...unsorted.map(row => row.id)]);

  return {
    AS_OF, RULE, ROWS, TODO, TODAY, TIERS, DIMS, debtors, creditors, receivable, tiers, overdue, high, unsorted,
    longOverdue: tiers[3] + tiers[4],
    highOverdue: sum(high.map(row => row.overdue)),
    overdueCustomers: debtors.filter(row => row.overdue > 0).length,
    paidThisMonth: sum(ledger.map(row => row.paid ?? 0)),
    chargedThisMonth: sum(ledger.map(row => row.charged ?? 0)),
    credit: sum(creditors.map(row => row.total)),
    missingTrips: sum(TODO.missingPrice.map(x => x.count)),
    todoCustomers: todoIds.size,
    byId: id => ROWS.find(row => row.id === id),
    sum, full, short, billions, hero, pct, esc, comText, reasons,
  };
})();
