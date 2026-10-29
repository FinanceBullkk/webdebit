/* Phép tính cho Tổng quan quản lý công nợ (DASH-03, duyệt 29/10/2026): nhóm hạn trả, mức rủi ro và
   phân loại khách từ GET /api/v7/dashboard/debt. Tiền là BigInt từ chuỗi VND của API; server tính nhóm
   hạn trả và mức rủi ro, ở đây chỉ gom/lọc danh sách. File render (dashboard-v7.js) không tự cộng trừ. */
const DashboardModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const UNSORTED = 'Chưa phân loại';
  const OTHER = 'Khác';
  const TIERS = ['not_due', 'due_this_month', 'late_1_2', 'late_3_6', 'late_over_6'];
  const RISK = { high: 'Rủi ro cao', watch: 'Theo dõi', ok: 'Trong hạn' };
  const fold = value => String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[đĐ]/g, 'd').toLowerCase().trim();
  const transportText = mode => ({ CANG: 'cảng', 'CẢNG': 'cảng', BO: 'bộ', 'BỘ': 'bộ' })[mode] ?? '';
  const dm = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  const dmy = iso => `${dm(iso)}/${iso.slice(0, 4)}`;
  const monthText = iso => `${Number(iso.slice(5, 7))}/${iso.slice(0, 4)}`;
  // Tới 90 ngày đếm ngày, lâu hơn đếm tháng: dễ đọc hơn "678 ngày".
  const ago = days => days > 90 ? `${Math.floor(days / 30)} tháng` : `${days} ngày`;

  /** Chỉ sầu riêng tách cảng/bộ; thiếu mặt hàng, hoặc sầu riêng chưa ghi cảng/bộ, là "Chưa phân loại". */
  function commodityKey(commodity, mode) {
    if (!commodity) return UNSORTED;
    if (fold(commodity) !== 'sau rieng') return commodity;
    return transportText(mode) ? `${commodity} ${transportText(mode)}` : UNSORTED;
  }

  /** Tên tháng lùi `back` tháng so với tháng của `asOf`: "T7", hoặc "T12/2025" khi khác năm. */
  function monthName(asOf, back) {
    const n = Number(asOf.slice(0, 4)) * 12 + Number(asOf.slice(5, 7)) - 1 - back;
    const year = Math.floor(n / 12);
    return year === Number(asOf.slice(0, 4)) ? `T${n % 12 + 1}` : `T${n % 12 + 1}/${year}`;
  }

  /**
   * Nhãn 5 nhóm hạn trả kèm tháng nợ của từng nhóm, cùng quy tắc với server: nợ tháng M đến hạn cuối
   * tháng M + `due_after_months`; số tháng quá hạn dưới 0 · 0 · 1–2 · 3–6 · từ 7.
   */
  function tierLabels(asOf, rule) {
    const due = rule?.due_after_months ?? 1;
    const span = (from, to) => (from === to ? monthName(asOf, from) : `${monthName(asOf, from)}–${monthName(asOf, to)}`);
    const lastDay = new Date(Date.UTC(Number(asOf.slice(0, 4)), Number(asOf.slice(5, 7)), 0)).getUTCDate();
    return [
      { label: 'Chưa đến hạn', short: 'chưa đến hạn', span: `nợ ${span(due - 1, 0)}` },
      { label: `Đến hạn ${lastDay}/${Number(asOf.slice(5, 7))}`, short: `đến hạn ${lastDay}/${Number(asOf.slice(5, 7))}`, span: `nợ ${monthName(asOf, due)}` },
      { label: 'Quá hạn 1–2 tháng', short: 'quá hạn 1–2 tháng', span: `nợ ${span(due + 2, due + 1)}` },
      { label: 'Quá hạn 3–6 tháng', short: 'quá hạn 3–6 tháng', span: `nợ ${span(due + 6, due + 3)}` },
      { label: 'Quá hạn trên 6 tháng', short: 'quá hạn trên 6 tháng', span: `nợ ${monthName(asOf, due + 7)} trở về trước` },
    ];
  }

  /** Nhóm hạn trả (0–4) của một tháng nợ "YYYY-MM-01", để tô thanh trong ngăn kéo. */
  function tierOfMonth(month, asOf, rule) {
    const late = (Number(asOf.slice(0, 4)) - Number(month.slice(0, 4))) * 12
      + Number(asOf.slice(5, 7)) - Number(month.slice(5, 7)) - (rule?.due_after_months ?? 1);
    return late < 0 ? 0 : late === 0 ? 1 : late <= 2 ? 2 : late <= 6 ? 3 : 4;
  }

  /** Một dòng lý do ngắn: dấu hiệu rủi ro trước; khách không rủi ro cao thì nói nợ nào quá hạn và lần trả gần nhất. */
  function reason(row, rule) {
    const paid = row.payDate ? `có trả ${row.payExact ? dm(row.payDate) : `khoảng T${monthText(row.payDate)}`}` : 'chưa trả lần nào';
    let parts;
    if (row.risk === 'high') {
      parts = [];
      if (row.longOverdue > 0n && row.oldest) parts.push(`Nợ từ T${monthText(row.oldest)}`);
      if (row.payDays == null) parts.push('chưa trả lần nào');
      else if (row.payDays > rule.no_pay_days) parts.push(`${ago(row.payDays)} chưa trả`);
      if (row.tripDays == null) parts.push('chưa có chuyến');
      else if (row.tripDays > rule.no_trip_days) parts.push('ngừng đi hàng');
      else if (row.tripDays <= rule.active_trip_days) parts.push('vẫn đi hàng');
    } else {
      const late = row.months.find(item => item.tier >= 2 && item.value > 0n);
      parts = [late ? `Nợ T${monthText(late.key)} quá hạn` : 'Trong hạn', paid];
    }
    const text = parts.join(' · ');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  /** Câu giải thích trong ngăn kéo: vì sao khách ở mức này. */
  function reasons(row, rule) {
    const oldest = row.oldest ? ` (nợ từ tháng ${monthText(row.oldest)})` : '';
    return [
      row.longOverdue > 0n ? `Còn ${F.short(row.longOverdue)} quá hạn từ 3 tháng trở lên${oldest}`
        : row.overdue > 0n ? `Quá hạn ${F.short(row.overdue)}${oldest}` : 'Chưa có nợ quá hạn',
      row.payDate ? `Trả gần nhất ${row.payExact ? dmy(row.payDate) : `trong tháng ${monthText(row.payDate)}`} — ${row.payDays ? `${ago(row.payDays)} trước` : 'hôm nay'}`
        : 'Chưa trả lần nào',
      row.tripDate ? `Đi hàng gần nhất ${row.tripExact ? dmy(row.tripDate) : `trong tháng ${monthText(row.tripDate)}`} — ${row.tripDays > rule.no_trip_days ? 'đã ngừng đi hàng' : row.tripDays > rule.active_trip_days ? 'ít đi hàng' : 'vẫn đi hàng'}`
        : 'Chưa có chuyến',
    ];
  }

  /** Khách đang nợ từ dashboard/debt, tiền đổi sang BigInt, kèm lớp của từng tiêu chí phân loại. */
  function debtors(debt) {
    const rule = debt.rule;
    const rows = debt.customers.map(item => {
      const row = {
        id: item.customer_id, name: item.name, commodity: item.commodity, transportMode: item.transport_mode,
        total: F.toBig(item.outstanding_vnd), tiers: item.tiers_vnd.map(F.toBig), overdue: F.toBig(item.overdue_vnd),
        longOverdue: F.toBig(item.long_overdue_vnd), oldest: item.oldest_open_month ?? null, risk: item.risk,
        payDate: item.last_receipt_date, payExact: item.last_receipt_exact, payDays: item.pay_days,
        tripDate: item.last_trip_date, tripExact: item.last_trip_exact, tripDays: item.trip_days,
        months: (item.months ?? []).map(m => ({ key: m.month, value: F.toBig(m.outstanding_vnd), tier: tierOfMonth(m.month, debt.as_of, rule) })),
        com: commodityKey(item.commodity, item.transport_mode),
      };
      row.pay = row.payDays == null ? 'never' : row.payDays <= 30 ? 'p30' : row.payDays <= rule.no_pay_days ? 'p60' : 'p61';
      row.trip = row.tripDays == null || row.tripDays > rule.no_trip_days ? 't91' : row.tripDays > rule.active_trip_days ? 't90' : 't30';
      row.why = reason(row, rule);
      return row;
    });
    const bySize = [...rows].sort((a, b) => (b.total > a.total ? 1 : b.total < a.total ? -1 : a.id - b.id));
    bySize.forEach((row, index) => { row.size = index < 5 ? 'top5' : index < 10 ? 'next5' : 'rest'; });
    // Mặt hàng dưới 1% còn phải thu gom "Khác"; "Chưa phân loại" giữ riêng.
    const receivable = F.toBig(debt.receivable_vnd);
    const comTotals = new Map();
    for (const row of rows) comTotals.set(row.com, (comTotals.get(row.com) ?? 0n) + row.total);
    for (const row of rows) if (row.com !== UNSORTED && comTotals.get(row.com) * 100n < receivable) row.com = OTHER;
    return rows;
  }

  /** Server và danh sách khách phải cộng về cùng tổng thì mới cho lọc/phân loại tại chỗ. */
  function totalsMatch(rows, debt) {
    return F.sum(rows.map(row => row.total)) === F.toBig(debt.receivable_vnd)
      && TIERS.every((tier, i) => F.sum(rows.map(row => row.tiers[i])) === F.toBig(debt.due_tiers.find(item => item.tier === tier)?.receivable_vnd ?? '0'));
  }

  const compare = (a, b) => (b > a ? 1 : b < a ? -1 : 0);

  /** Năm tiêu chí phân loại; mỗi nhóm có số khách, còn nợ, quá hạn, tên khách. Nhóm rỗng bỏ đi. */
  function dimensions(rows, receivable) {
    const total = F.toBig(receivable);
    const group = (field, classes) => classes.map(item => {
      const members = rows.filter(row => row[field] === item.key);
      return { ...item, count: members.length, total: F.sum(members.map(row => row.total)),
        overdue: F.sum(members.map(row => row.overdue)), names: members.map(row => row.name) };
    }).filter(item => item.count);
    const find = (groups, key) => groups.find(item => item.key === key);
    const coms = [...new Set(rows.map(row => row.com))].map(key => ({ key, label: key, tone: key === OTHER || key === UNSORTED ? 'grey' : '' }));
    const comGroups = group('com', coms).sort((a, b) => ((a.tone === 'grey') - (b.tone === 'grey'))
      || ((a.key === UNSORTED) - (b.key === UNSORTED)) || compare(a.total, b.total) || a.key.localeCompare(b.key, 'vi'));
    return [
      { key: 'risk', tab: 'Rủi ro', title: 'Mức rủi ro', groups: group('risk', [
        { key: 'high', label: 'Rủi ro cao', tone: 'critical' }, { key: 'watch', label: 'Cần theo dõi', tone: 'warning' },
        { key: 'ok', label: 'Trong hạn' }]),
      lead: groups => { const g = find(groups, 'high'); return g ? [['b', `${g.count} khách rủi ro cao`], ' đang nợ ', ['b', F.short(g.total)], `, trong đó quá hạn ${F.short(g.overdue)}.`] : ['Không có khách rủi ro cao.']; } },
      { key: 'pay', tab: 'Lần trả', title: 'Lần trả gần nhất', groups: group('pay', [
        { key: 'p30', label: 'Có trả trong 30 ngày qua' }, { key: 'p60', label: '31–60 ngày chưa trả', tone: 'warning' },
        { key: 'p61', label: 'Trên 60 ngày chưa trả', tone: 'critical' }, { key: 'never', label: 'Chưa trả lần nào', tone: 'grey' }]),
      lead: groups => { const g = find(groups, 'p61'); return g ? [['b', `${g.count} khách`], ' đã hơn 60 ngày chưa trả, đang nợ ', ['b', F.short(g.total)], '.'] : ['Khách nào cũng có trả trong 60 ngày qua.']; } },
      { key: 'trip', tab: 'Đi hàng', title: 'Đi hàng gần nhất', groups: group('trip', [
        { key: 't30', label: 'Đang đi hàng (30 ngày qua)' }, { key: 't90', label: 'Ít đi hàng (31–90 ngày)', tone: 'grey' },
        { key: 't91', label: 'Ngừng đi hàng (trên 90 ngày)', tone: 'critical' }]),
      lead: groups => { const g = find(groups, 't91'); return g ? [['b', `${g.count} khách ngừng đi hàng`], ' còn nợ ', ['b', F.short(g.total)], '.'] : ['Khách đang nợ đều còn đi hàng.']; } },
      { key: 'size', tab: 'Quy mô', title: 'Quy mô nợ', groups: group('size', [
        { key: 'top5', label: '5 khách nợ nhiều nhất' }, { key: 'next5', label: '5 khách tiếp theo' },
        { key: 'rest', label: 'Các khách còn lại', tone: 'grey' }]),
      lead: groups => { const g = find(groups, 'top5'); return g ? [`${g.count === 5 ? '5 khách' : `${g.count} khách`} nợ nhiều nhất chiếm `, ['b', F.percent(g.total, total)], ' tổng còn phải thu.'] : []; } },
      { key: 'com', tab: 'Mặt hàng', title: 'Mặt hàng', groups: comGroups,
        lead: groups => (groups.length ? [['b', groups[0].label], ' chiếm ', ['b', F.percent(groups[0].total, total)], ' tổng còn phải thu.'] : []) },
    ];
  }

  /**
   * Danh sách khách theo lọc: `tier` là nhóm hạn trả (cột số đầu thành phần nợ thuộc nhóm), `cls` là
   * {dim, key} của một nhóm phân loại. Mặc định xếp theo cột số đầu, `sort: 'total'` xếp theo còn nợ.
   */
  function filterRows(rows, { tier = null, cls = null, sort = 'overdue' } = {}) {
    return rows.filter(row => (tier == null || row.tiers[tier] > 0n) && (!cls || row[cls.dim] === cls.key))
      .map(row => ({ row, first: tier == null ? row.overdue : row.tiers[tier] }))
      .sort((a, b) => (sort === 'total' ? compare(a.row.total, b.row.total) || compare(a.first, b.first)
        : compare(a.first, b.first) || compare(a.row.total, b.row.total)) || a.row.name.localeCompare(b.row.name, 'vi'));
  }

  return { UNSORTED, OTHER, TIERS, RISK, commodityKey, monthName, tierLabels, tierOfMonth, reason, reasons,
    debtors, totalsMatch, dimensions, filterRows };
})();
if (typeof module !== 'undefined') module.exports = DashboardModel;
