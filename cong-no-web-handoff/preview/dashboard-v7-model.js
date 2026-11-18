/* Phép tính cho Tổng quan (quy tắc DASH-03 29/10/2026, trình bày DASH-05 2/11/2026): nhóm hạn trả, chip mức rủi ro,
   tiến độ thu tháng từ GET /api/v7/dashboard/debt. Tiền là BigInt từ chuỗi VND của API; server tính nhóm hạn trả và
   mức rủi ro, ở đây chỉ gom/lọc/đối chiếu. Render (dashboard-v7.js) không tự cộng trừ. */
const DashboardModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const UNSORTED = F.UNSORTED;
  const OTHER = 'Khác';
  const TIERS = ['not_due', 'due_this_month', 'late_1_2', 'late_3_6', 'late_over_6'];
  // DASH-05 (4): khách không có nợ quá hạn là "Không quá hạn"; "Trong hạn" chỉ dành cho tiền chưa quá hạn.
  const RISK = { high: 'Rủi ro cao', watch: 'Theo dõi', ok: 'Không quá hạn' };
  const RISKS = ['high', 'watch', 'ok'];
  const { fold, transportText, monthLabel } = F;
  const dm = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  // Tới 90 ngày đếm ngày, lâu hơn đếm tháng: dễ đọc hơn "678 ngày" trong câu chữ (bảng ghi số ngày, đơn vị ở đầu cột).
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
   * Nhãn 5 nhóm hạn trả, cùng quy tắc với server: nợ tháng M đến hạn cuối tháng M + `due_after_months`; số tháng
   * quá hạn dưới 0 · 0 · 1–2 · 3–6 · từ 7. `tile` là tên ngắn trên ô, `label` tên đủ và `span` tháng nợ cho chú thích.
   */
  function tierLabels(asOf, rule) {
    const due = rule?.due_after_months ?? 1;
    const span = (from, to) => (from === to ? monthName(asOf, from) : `${monthName(asOf, from)}–${monthName(asOf, to)}`);
    const lastDay = new Date(Date.UTC(Number(asOf.slice(0, 4)), Number(asOf.slice(5, 7)), 0)).getUTCDate();
    const end = `${lastDay}/${Number(asOf.slice(5, 7))}`;
    return [
      { label: 'Chưa đến hạn', tile: 'Chưa đến hạn', span: `nợ ${span(due - 1, 0)}` },
      { label: `Đến hạn ${end}`, tile: `Hạn ${end}`, span: `nợ ${monthName(asOf, due)}` },
      { label: 'Quá hạn 1–2 tháng', tile: '1–2 tháng', span: `nợ ${span(due + 2, due + 1)}` },
      { label: 'Quá hạn 3–6 tháng', tile: '3–6 tháng', span: `nợ ${span(due + 6, due + 3)}` },
      { label: 'Quá hạn trên 6 tháng', tile: '> 6 tháng', span: `nợ ${monthName(asOf, due + 7)} trở về trước` },
    ];
  }

  /** Nhóm hạn trả (0–4) của một tháng nợ "YYYY-MM-01", cùng quy tắc với server. */
  function tierOfMonth(month, asOf, rule) {
    const late = (Number(asOf.slice(0, 4)) - Number(month.slice(0, 4))) * 12
      + Number(asOf.slice(5, 7)) - Number(month.slice(5, 7)) - (rule?.due_after_months ?? 1);
    return late < 0 ? 0 : late === 0 ? 1 : late <= 2 ? 2 : late <= 6 ? 3 : 4;
  }

  /** Một dòng lý do cho chú thích của dòng khách: dấu hiệu rủi ro trước; khách khác thì nói nợ nào quá hạn và lần trả gần nhất. */
  function reason(row, rule) {
    const paid = row.payDate ? `có trả ${row.payExact ? dm(row.payDate) : `khoảng T${monthLabel(row.payDate)}`}` : 'chưa trả lần nào';
    let parts;
    if (row.risk === 'high') {
      parts = [];
      if (row.longOverdue > 0n && row.oldest) parts.push(`Nợ từ T${monthLabel(row.oldest)}`);
      if (row.payDays == null) parts.push('chưa trả lần nào');
      else if (row.payDays > rule.no_pay_days) parts.push(`${ago(row.payDays)} chưa trả`);
      if (row.tripDays == null) parts.push('chưa có chuyến');
      else if (row.tripDays > rule.no_trip_days) parts.push('ngừng đi hàng');
      else if (row.tripDays <= rule.active_trip_days) parts.push('vẫn đi hàng');
    } else {
      const late = row.lateMonth;
      parts = [late ? `Nợ T${monthLabel(late)} quá hạn` : 'Không quá hạn', paid];
    }
    const text = parts.join(' · ');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  /** Khách đang nợ từ dashboard/debt, tiền đổi sang BigInt; mặt hàng dưới 1% còn phải thu gom "Khác". */
  function debtors(debt) {
    const rule = debt.rule;
    const rows = debt.customers.map(item => {
      const row = {
        id: item.customer_id, name: item.name, commodity: item.commodity, transportMode: item.transport_mode,
        total: F.toBig(item.outstanding_vnd), tiers: item.tiers_vnd.map(F.toBig), overdue: F.toBig(item.overdue_vnd),
        longOverdue: F.toBig(item.long_overdue_vnd), oldest: item.oldest_open_month ?? null, risk: item.risk,
        payDate: item.last_receipt_date, payExact: item.last_receipt_exact, payDays: item.pay_days,
        tripDate: item.last_trip_date, tripExact: item.last_trip_exact, tripDays: item.trip_days,
        com: commodityKey(item.commodity, item.transport_mode),
      };
      // Tháng nợ quá hạn đầu tiên còn nợ, để chú thích nói "Nợ T8 quá hạn".
      row.lateMonth = (item.months ?? []).find(m => tierOfMonth(m.month, debt.as_of, rule) >= 2 && F.toBig(m.outstanding_vnd) > 0n)?.month ?? null;
      row.why = reason(row, rule);
      return row;
    });
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
  const summarize = (item, members) => ({ ...item, count: members.length, total: F.sum(members.map(row => row.total)),
    overdue: F.sum(members.map(row => row.overdue)) });

  /**
   * Ba chip mức rủi ro (DASH-05): số khách và tiền quá hạn mỗi mức. Khách quá hạn âm (dư ở nợ cũ, còn nợ mới) là
   * "Không quá hạn" theo server; phần âm đó nằm trong `overdue` của chip này và được đếm ở `credit` để chú thích.
   */
  function risks(rows) {
    const credit = rows.filter(row => row.overdue < 0n);
    return { groups: RISKS.map(key => summarize({ key, label: RISK[key] }, rows.filter(row => row.risk === key))),
      credit: { count: credit.length, overdue: F.sum(credit.map(row => row.overdue)) } };
  }

  /**
   * Chip đối chiếu được với `summary` của server: số khách và tiền quá hạn của Rủi ro cao, số khách có quá hạn
   * (Rủi ro cao + Theo dõi), và tổng quá hạn của cả ba chip (kể cả phần âm) bằng ngoặc Quá hạn.
   */
  function riskMatches(rk, summary) {
    if (!rk || !summary) return false;
    const [high, watch] = rk.groups;
    return high.count === summary.high_customers && high.overdue === F.toBig(summary.high_overdue_vnd)
      && high.count + watch.count === summary.overdue_customers
      && F.sum(rk.groups.map(group => group.overdue)) === F.toBig(summary.overdue_vnd);
  }

  /**
   * Khối Công nợ theo mặt hàng (DASH-07): mỗi nhóm số khách, còn phải thu, quá hạn; nhiều tiền trước, "Khác" rồi
   * "Chưa phân loại" cuối. `late` là phần quá hạn dương (khách dư ở nợ cũ không làm thanh dài quá còn phải thu);
   * `members` là tên các mặt hàng đã gộp vào "Khác".
   */
  function commodities(rows) {
    return [...new Set(rows.map(row => row.com))]
      .map(key => {
        const members = rows.filter(row => row.com === key);
        const group = summarize({ key, label: key, tone: key === OTHER || key === UNSORTED ? 'grey' : '' }, members);
        group.late = group.overdue > 0n ? group.overdue : 0n;
        group.members = key === OTHER ? [...new Set(members.map(row => F.commodityText(row.commodity, row.transportMode)))].sort((a, b) => a.localeCompare(b, 'vi')) : [];
        return group;
      })
      .sort((a, b) => ((a.tone === 'grey') - (b.tone === 'grey')) || ((a.key === UNSORTED) - (b.key === UNSORTED))
        || compare(a.total, b.total) || a.key.localeCompare(b.key, 'vi'));
  }

  /**
   * Lọc chéo (DASH-08): khách theo các lọc đang chọn, bỏ chiều `skip` của chính khối đang vẽ ('tier' | 'risk' | 'com'),
   * để khối vẫn hiện đủ lựa chọn của mình (ô đang chọn chỉ được tô) mà số tính lại theo các lọc còn lại.
   */
  function scope(rows, { tier = null, risk = null, com = null } = {}, skip = null) {
    const t = skip === 'tier' ? null : tier;
    const r = skip === 'risk' ? null : risk;
    const c = skip === 'com' ? null : com;
    return rows.filter(row => (t == null || row.tiers[t] > 0n) && (r == null || row.risk === r) && (c == null || row.com === c));
  }

  /** Dải đầu của một phạm vi khách: còn phải thu, 5 nhóm hạn trả, quá hạn (kể phần âm như server), khách dư ở nợ cũ. */
  function totals(rows) {
    const credit = rows.filter(row => row.overdue < 0n);
    return { count: rows.length, total: F.sum(rows.map(row => row.total)), tiers: TIERS.map((_, i) => F.sum(rows.map(row => row.tiers[i]))),
      overdue: F.sum(rows.map(row => row.overdue)), credit: { count: credit.length, overdue: F.sum(credit.map(row => row.overdue)) } };
  }

  /** Tiền của một khách cho khối đang lọc nhóm hạn trả: có nhóm thì tiền nhóm đó, không thì `field`. */
  const amountOf = (row, tier, field) => (tier == null ? row[field] : row.tiers[tier]);

  /**
   * Ba chip mức rủi ro của một phạm vi: số khách và tiền. Không lọc nhóm hạn trả: tiền quá hạn (như `risks`); có lọc:
   * tiền thuộc nhóm đó, cho cả chip Không quá hạn.
   */
  function riskView(rows, tier = null) {
    return RISKS.map(key => {
      const members = rows.filter(row => row.risk === key);
      return { key, label: RISK[key], count: members.length, amount: F.sum(members.map(row => amountOf(row, tier, 'overdue'))) };
    });
  }

  /**
   * Dòng mặt hàng của một phạm vi, giữ nhóm và thứ tự của `coms` (bố cục không nhảy khi lọc). Không lọc nhóm hạn trả:
   * còn phải thu và phần quá hạn dương; có lọc: tiền nhóm đó, cả là quá hạn khi nhóm đã quá hạn (từ 1–2 tháng).
   */
  function comView(rows, coms, tier = null) {
    return coms.map(item => {
      const members = rows.filter(row => row.com === item.key);
      const total = F.sum(members.map(row => amountOf(row, tier, 'total')));
      const overdue = F.sum(members.map(row => row.overdue));
      const late = tier == null ? (overdue > 0n ? overdue : 0n) : tier >= 2 ? total : 0n;
      return { ...item, count: members.length, total, late };
    });
  }

  /**
   * Thu tháng theo lọc (DASH-08): cộng `this_month.customers` (thu/phát sinh tháng này từng sổ, cả sổ đã hết nợ) của các sổ
   * trong phạm vi. Lọc hạn trả / mức rủi ro chỉ khớp sổ đang nợ (sổ hết nợ không có nhóm); lọc mặt hàng khớp cả sổ hết nợ,
   * mặt hàng không có trong `coms` gộp "Khác". API chưa có `customers` hoặc không lọc gì thì trả null (dùng tổng của server).
   */
  function monthFlow(thisMonth, rows, coms, { tier = null, risk = null, com = null } = {}) {
    if (!Array.isArray(thisMonth?.customers) || (tier == null && risk == null && com == null)) return null;
    const byId = new Map(rows.map(row => [row.id, row]));
    const keys = new Set(coms.map(item => item.key));
    const comOf = book => {
      const row = byId.get(book.customer_id);
      if (row) return row.com;
      const key = commodityKey(book.commodity, book.transport_mode);
      return key === UNSORTED || (keys.has(key) && key !== OTHER) ? key : OTHER;
    };
    const books = thisMonth.customers.filter(book => {
      const row = byId.get(book.customer_id);
      if ((tier != null || risk != null) && !row) return false;
      return (tier == null || row.tiers[tier] > 0n) && (risk == null || row.risk === risk) && (com == null || comOf(book) === com);
    });
    return { charges_vnd: F.sum(books.map(book => book.charges_vnd)), received_vnd: F.sum(books.map(book => book.received_vnd)), books: books.length };
  }

  /**
   * Thước đo tháng: đã thu so với phát sinh tháng này, hôm nay là ngày mấy và còn mấy ngày tới cuối tháng (theo `as_of`,
   * giờ VN). Phát sinh 0 thì không có tỉ lệ (`percent` null, `fill` 0); thu vượt phát sinh thì thước đầy, % vẫn đúng.
   */
  function monthProgress(asOf, thisMonth) {
    const day = Number(asOf.slice(8, 10));
    const days = new Date(Date.UTC(Number(asOf.slice(0, 4)), Number(asOf.slice(5, 7)), 0)).getUTCDate();
    const charges = F.toBig(thisMonth?.charges_vnd ?? '0');
    const received = F.toBig(thisMonth?.received_vnd ?? '0');
    return { month: Number(asOf.slice(5, 7)), day, days, left: days - day, dayPct: Math.round(day / days * 100), charges, received,
      fill: charges > 0n ? F.barWidth(received, charges) : 0, percent: charges > 0n ? F.percent(received, charges) : null };
  }

  /** Ô số ngày trên bảng: chỉ con số (đơn vị ở đầu cột) và sắc thái theo ngưỡng; null là "chưa", không phải 0. */
  function dayCell(days, limit, active) {
    if (days == null) return { text: 'chưa', tone: 'bad' };
    return { text: String(days), tone: days > limit ? 'bad' : days > active ? 'warn' : '' };
  }

  /**
   * Danh sách khách theo lọc: `tier` là nhóm hạn trả (cột tiền đầu thành phần nợ thuộc nhóm), `risk` là mức rủi ro,
   * `com` là mặt hàng. Xếp theo cột tiền đầu (mặc định), `total` còn nợ, `pay`/`trip` số ngày giảm dần với null
   * (chưa trả / chưa có chuyến) coi là lâu nhất.
   */
  function filterRows(rows, { tier = null, risk = null, com = null, sort = 'overdue' } = {}) {
    const days = value => (value == null ? Infinity : value);
    const byDays = (field, a, b) => compare(days(a.row[field]), days(b.row[field]));
    return rows.filter(row => (tier == null || row.tiers[tier] > 0n) && (risk == null || row.risk === risk) && (com == null || row.com === com))
      .map(row => ({ row, first: tier == null ? row.overdue : row.tiers[tier] }))
      .sort((a, b) => (sort === 'total' ? compare(a.row.total, b.row.total) || compare(a.first, b.first)
        : sort === 'pay' ? byDays('payDays', a, b) || compare(a.first, b.first)
          : sort === 'trip' ? byDays('tripDays', a, b) || compare(a.first, b.first)
            : compare(a.first, b.first) || compare(a.row.total, b.row.total)) || a.row.name.localeCompare(b.row.name, 'vi'));
  }

  return { UNSORTED, OTHER, TIERS, RISK, RISKS, commodityKey, monthName, tierLabels, tierOfMonth, reason, ago,
    debtors, totalsMatch, risks, riskMatches, commodities, scope, totals, riskView, comView, monthFlow, monthProgress, dayCell, filterRows };
})();
if (typeof module !== 'undefined') module.exports = DashboardModel;
