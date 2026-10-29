// Một bộ dữ liệu giả dùng chung cho mọi trang mockup — tên khách và số tiền đều hư cấu.
// Đơn vị đồng. months = còn nợ theo tháng phát sinh năm 2026; older = nợ từ năm trước.
// Mọi khối trên trang tính từ đây nên luôn cộng về cùng tổng (thay bảng "đối chiếu tự động" của v2).
window.MOCK = (() => {
  'use strict';
  const AS_OF = { year: 2026, month: 10, label: '29/10/2026' };
  const ROWS = [
    { id: 1, name: 'MAI HOA (GL)', commodity: 'Sầu riêng', transport: 'cảng', months: { 7: 3850000000, 8: 6420000000, 9: 6890000000, 10: 3430000000 }, older: { 2025: 1200000000 } },
    { id: 2, name: 'LONG THÀNH', commodity: 'Sầu riêng', transport: 'bộ', months: { 8: 4100000000, 9: 4400000000, 10: 3300000000 }, older: {} },
    { id: 3, name: 'THANH PHÁT', commodity: 'Sầu riêng', transport: 'cảng', months: { 8: 2200000000, 9: 3330000000, 10: 3500000000 }, older: {} },
    { id: 4, name: 'HẢI NAM', commodity: 'Sầu riêng', transport: 'bộ', months: { 3: 1200000000, 5: 950000000 }, older: {} },
    { id: 5, name: 'AN NHIÊN', commodity: 'Sầu riêng', transport: 'cảng', months: { 9: 1400000000, 10: 650000000 }, older: {} },
    { id: 6, name: 'SÔNG HỒNG', commodity: 'Thanh long', transport: 'bộ', months: { 5: 1100000000, 6: 1250000000, 9: 1450000000 }, older: {} },
    { id: 7, name: 'GIA PHÁT', commodity: 'Thanh long', transport: null, months: { 7: 350000000, 8: 620000000 }, older: {} },
    { id: 8, name: 'THẢO VY', commodity: 'Thanh long', transport: null, months: { 10: 420000000 }, older: {} },
    { id: 9, name: 'HẢI TRIỀU', commodity: 'Chuối', transport: null, months: { 1: 2300000000, 2: 1700000000, 3: 1600000000 }, older: {} },
    { id: 10, name: 'BẢO NGỐC', commodity: 'Chuối', transport: null, months: { 9: 280000000, 10: 120000000 }, older: {} },
    { id: 11, name: 'ÁNH DƯƠNG', commodity: 'Dừa', transport: null, months: { 2: 1100000000, 3: 1500000000, 4: 1500000000 }, older: {} },
    { id: 12, name: 'TÂN PHÚ', commodity: 'Dừa', transport: null, months: { 10: 350000000 }, older: {} },
    // v5: khách sầu riêng chưa ghi cảng/bộ và hai mặt hàng rất nhỏ — để thấy dòng "chưa rõ" và nhóm "Khác".
    { id: 18, name: 'PHƯƠNG NAM', commodity: 'Sầu riêng', transport: null, months: { 8: 900000000, 9: 1100000000 }, older: {} },
    { id: 19, name: 'HOÀNG MAI', commodity: 'Mít', transport: null, months: { 10: 45000000 }, older: {} },
    { id: 20, name: 'SAO VIỆT', commodity: 'Bán cước', transport: null, months: { 9: 28000000 }, older: {} },
    { id: 13, name: 'MAI THẢO', commodity: 'Xoài', transport: null, months: { 8: 310000000, 10: 590000000 }, older: {} },
    { id: 14, name: 'ĐÌNH TRUNG', commodity: null, transport: null, months: {}, older: { 2024: 551000000 } },
    { id: 15, name: 'QUANG MINH', commodity: null, transport: null, months: {}, older: {} },
    { id: 16, name: 'KIM LAN', commodity: null, transport: null, months: { 10: -350000000 }, older: {} },
    // Khách chưa có số dư đầu: không vào tổng nào, chỉ hiện ở Việc cần làm (DASH-01).
    { id: 17, name: 'PHÚ LONG', commodity: null, transport: null, noBaseline: true, months: {}, older: {} },
  ];
  const TODO = {
    missingPrice: [{ id: 1, count: 3 }, { id: 9, count: 7 }, { id: 3, count: 2 }],
    pendingReview: [{ id: 6, count: 1 }, { id: 7, count: 1 }],
  };
  const TODAY = { byActor: [
    { actor: 'Lan', trips: 3, receipts: 2, received: 265000000, voids: 0 },
    { actor: 'Hùng', trips: 2, receipts: 1, received: 147500000, voids: 0 },
  ] };

  const sumValues = obj => Object.values(obj).reduce((a, v) => a + v, 0);
  const yearOf = row => sumValues(row.months);
  const olderOf = row => sumValues(row.older);
  const allOf = row => yearOf(row) + olderOf(row);
  const ledger = ROWS.filter(row => !row.noBaseline);
  const debtors = ledger.filter(row => allOf(row) > 0);
  const creditors = ledger.filter(row => allOf(row) < 0);
  const groupKey = row => row.commodity == null ? '' : row.commodity + (row.transport ? ' · ' + row.transport : '');
  const groupLabel = key => key || 'Chưa phân loại';

  // Nhóm tuổi theo tháng phát sinh: 0 = tháng này, 1 = 1–2, 2 = 3–6, 3 = trên 6 tháng.
  const ageOf = month => { const d = AS_OF.month - month; return d <= 0 ? 0 : d <= 2 ? 1 : d <= 6 ? 2 : 3; };
  const aging = [0, 0, 0, 0];
  for (const row of debtors) {
    for (const [m, v] of Object.entries(row.months)) aging[ageOf(Number(m))] += v;
    aging[3] += olderOf(row);
  }
  const oldestMonth = row => {
    const years = Object.keys(row.older).filter(y => row.older[y] > 0).map(Number);
    if (years.length) return `${Math.min(...years)}`;
    const months = Object.keys(row.months).filter(m => row.months[m] > 0).map(Number);
    return months.length ? `${String(Math.min(...months)).padStart(2, '0')}/${AS_OF.year}` : '';
  };

  const fmtFull = v => v.toLocaleString('vi-VN') + ' đ';
  const fmtShort = v => {
    const abs = Math.abs(v);
    if (abs >= 1e9) return (v / 1e9).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + ' tỷ';
    if (abs >= 1e6) return (v / 1e6).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + ' tr';
    return v.toLocaleString('vi-VN');
  };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
  const byId = id => ROWS.find(row => row.id === id);

  return { AS_OF, ROWS, TODO, TODAY, ledger, debtors, creditors, aging, yearOf, olderOf, allOf,
    groupKey, groupLabel, oldestMonth, fmtFull, fmtShort, esc, byId,
    receivable: debtors.reduce((a, row) => a + allOf(row), 0),
    credit: creditors.reduce((a, row) => a + allOf(row), 0) };
})();
