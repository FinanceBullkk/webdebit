/* Phép tính cho Tổng quan tương tác (mockup v5.3 đã duyệt 29/10/2026): phần nợ theo nhóm tuổi
   của từng khách, gom mặt hàng, lọc danh sách khách. Tiền là BigInt từ chuỗi VND của API;
   file render (dashboard-v7.js) chỉ gọi các hàm ở đây, không tự cộng trừ. */
const DashboardModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const UNSORTED = 'Chưa phân loại';
  const OTHER = 'Khác';
  const BUCKETS = ['current', '1-2', '3-6', 'over-6'];
  const fold = value => String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[đĐ]/g, 'd').toLowerCase().trim();
  const transportText = mode => ({ CANG: 'cảng', 'CẢNG': 'cảng', BO: 'bộ', 'BỘ': 'bộ' })[mode] ?? '';

  /** Nhóm tuổi như get_dashboard: số tháng từ tháng nợ tới tháng hiện tại; 0 (kể cả tháng sau) · 1–2 · 3–6 · trên 6. */
  function ageIndex(year, month, asOf) {
    const diff = (Number(asOf.slice(0, 4)) - year) * 12 + Number(asOf.slice(5, 7)) - month;
    return diff <= 0 ? 0 : diff <= 2 ? 1 : diff <= 6 ? 2 : 3;
  }

  /** Chỉ sầu riêng tách cảng/bộ; thiếu mặt hàng, hoặc sầu riêng chưa ghi cảng/bộ, là "Chưa phân loại". */
  function commodityKey(commodity, mode) {
    if (!commodity) return UNSORTED;
    if (fold(commodity) !== 'sau rieng') return commodity;
    return transportText(mode) ? `${commodity} ${transportText(mode)}` : UNSORTED;
  }

  /**
   * Khách đang nợ kèm phần nợ theo nhóm tuổi, từ ma trận năm hiện tại và năm trước.
   * Phần còn lại ngoài hai năm (nợ từ hai năm trước trở về trước) luôn quá 6 tháng.
   */
  function debtors(current, previous, asOf) {
    const year = Number(asOf.slice(0, 4));
    const before = new Map((previous?.customers ?? []).map(row => [row.customer_id, row]));
    return current.customers.filter(row => F.toBig(row.total_all_vnd) > 0n).map(row => {
      const buckets = [0n, 0n, 0n, 0n];
      const months = [];
      let counted = 0n;
      for (const [y, source] of [[year, row], [year - 1, before.get(row.customer_id)]]) {
        if (!source) continue;
        for (let m = 12; m >= 1; m--) {
          const value = F.toBig(source.months?.[String(m)] ?? '0');
          if (value === 0n) continue;
          buckets[ageIndex(y, m, asOf)] += value;
          counted += value;
          months.push({ key: `${y}-${String(m).padStart(2, '0')}`, value });
        }
      }
      const older = F.toBig(row.total_all_vnd) - counted;
      buckets[3] += older;
      return { id: row.customer_id, name: row.name, commodity: row.commodity, transportMode: row.transport_mode,
        key: commodityKey(row.commodity, row.transport_mode), total: F.toBig(row.total_all_vnd), buckets, months,
        older, olderBefore: year - 1, oldest: row.oldest_open_month ?? null };
    });
  }

  /** Cộng phần nợ từng nhóm của mọi khách; trang so với `aging` của get_dashboard trước khi cho lọc theo tuổi. */
  function bucketTotals(list) {
    return BUCKETS.map((_, i) => F.sum(list.map(row => row.buckets[i])));
  }

  function agingMatches(list, aging) {
    const totals = bucketTotals(list);
    return BUCKETS.every((bucket, i) => F.toBig(aging.find(item => item.bucket === bucket)?.receivable_vnd ?? '0') === totals[i]);
  }

  /**
   * Gom `by_commodity` của get_dashboard thành dòng của khối mặt hàng: xếp tiền giảm dần,
   * mặt hàng dưới 1% còn phải thu gom "Khác", "Chưa phân loại" luôn cuối.
   */
  function commodityGroups(byCommodity, receivable) {
    const total = F.toBig(receivable);
    const merged = new Map();
    for (const row of byCommodity) {
      const key = commodityKey(row.commodity, row.transport_mode);
      const item = merged.get(key) ?? { key, total: 0n, customers: 0, names: [] };
      item.total += F.toBig(row.receivable_vnd);
      item.customers += row.customers;
      merged.set(key, item);
    }
    const groups = [];
    const other = { key: OTHER, total: 0n, customers: 0, names: [], grey: true, members: [] };
    for (const item of merged.values()) {
      if (item.key !== UNSORTED && item.total * 100n < total) {
        other.total += item.total; other.customers += item.customers; other.names.push(item.key); other.members.push(item.key);
      } else groups.push({ ...item, grey: item.key === UNSORTED, members: [item.key] });
    }
    if (other.members.length) groups.push(other);
    const rank = item => (item.key === OTHER ? 1 : 0) + (item.key === UNSORTED ? 2 : 0);
    return groups.sort((a, b) => rank(a) - rank(b) || (b.total > a.total ? 1 : b.total < a.total ? -1 : a.key.localeCompare(b.key, 'vi')));
  }

  /** Số dòng "nhóm đầu": các dòng đầu cộng dồn tới 60% danh sách (ít nhất 1). */
  function majorCount(values) {
    const total = F.sum(values);
    let acc = 0n;
    let n = 0;
    for (const value of values) {
      if (acc * 10n >= total * 6n) break;
      acc += F.toBig(value);
      n += 1;
    }
    return values.length ? Math.max(1, n) : 0;
  }

  /**
   * Danh sách khách theo lọc: `age` là chỉ số nhóm tuổi (số cạnh tên là phần nợ thuộc nhóm),
   * `group` là một dòng của khối mặt hàng. Xếp tiền giảm dần rồi theo tên.
   */
  function filterDebtors(list, { age = null, group = null } = {}) {
    return list.map(row => ({ row, value: age == null ? row.total : row.buckets[age] }))
      .filter(item => item.value > 0n && (!group || group.members.includes(item.row.key)))
      .sort((a, b) => (b.value > a.value ? 1 : b.value < a.value ? -1 : a.row.name.localeCompare(b.row.name, 'vi')));
  }

  return { UNSORTED, OTHER, BUCKETS, ageIndex, commodityKey, debtors, bucketTotals, agingMatches, commodityGroups, majorCount, filterDebtors };
})();
if (typeof module !== 'undefined') module.exports = DashboardModel;
