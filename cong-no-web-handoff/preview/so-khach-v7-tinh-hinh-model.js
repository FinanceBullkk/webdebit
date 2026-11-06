/* Phép tính cho thẻ Tình hình (TUONG-TAC-01, TINH-HINH-01): từng tháng nợ theo hạn, dòng tiền về và hứa trả, số tiền của lần trả gần nhất, số chuyến mỗi tháng.
   Không vẽ gì; số tiền cộng bằng BigInt, render (so-khach-v7-overview-ui.js) chỉ định dạng (ARCH-03). */
const TinhHinhModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const { toBig, sum, full, dateText, monthLabel, vnDay } = F;
  const monthKey = value => String(value ?? '').slice(0, 7);
  const dayNumber = iso => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))) / 86400000;
  const isDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value ?? '');
  // Như DashboardModel.ago: tới 90 ngày đếm ngày, lâu hơn đếm tháng.
  const ago = days => (days > 90 ? `${Math.floor(days / 30)} tháng` : `${days} ngày`);

  /**
   * Tháng nợ của khách, xếp theo hạn như tier của get_dashboard_debt: chậm = số tháng tính tới tháng này − due_after_months;
   * < 0 chưa đến hạn, 0 đến hạn tháng này, > 0 quá hạn. `matches` false nghĩa là cộng lại không bằng tiers_vnd: không được hiện từng tháng.
   */
  function debtTiers(row, asOf, dueAfter = 1) {
    const groups = { late: [], due: [], future: [] };
    const now = Number(asOf.slice(0, 4)) * 12 + Number(asOf.slice(5, 7));
    for (const item of row?.months ?? []) {
      const year = Number(item.month.slice(0, 4));
      const month = Number(item.month.slice(5, 7));
      const late = now - (year * 12 + month) - dueAfter;
      // Ngày 0 của tháng sau tháng đến hạn là ngày cuối tháng đến hạn.
      const dueNumber = Date.UTC(year, month + dueAfter, 0) / 86400000;
      groups[late > 0 ? 'late' : late === 0 ? 'due' : 'future'].push({ key: monthKey(item.month), amount: toBig(item.outstanding_vnd),
        dueDate: new Date(dueNumber * 86400000).toISOString().slice(0, 10), days: dayNumber(asOf) - dueNumber });
    }
    const total = list => sum(list.map(item => item.amount));
    const tiers = (row?.tiers_vnd ?? []).map(toBig);
    const matches = tiers.length === 5 && total(groups.future) === tiers[0] && total(groups.due) === tiers[1]
      && total(groups.late) === tiers[2] + tiers[3] + tiers[4];
    return { groups, matches };
  }

  /** Ngày của một dữ kiện: có ngày đúng thì ghi ngày, chỉ biết tháng thì nói rõ, chưa có thì nói chưa có. */
  function factDate(date, exact) {
    if (!date) return 'Chưa có';
    return exact ? dateText(date) : `trong tháng ${monthLabel(date)}`;
  }

  /** Chuyến của một tháng: dòng web (trừ đã xóa, đã loại, phí lẻ) và dòng chuyến sổ gốc chưa xóa. */
  function tripCount(data, key) {
    return (data.trips ?? []).filter(trip => monthKey(trip.month) === key && !trip.deleted && trip.status !== 'rejected' && !trip.is_fee_only).length
      + (data.legacy_rows ?? []).filter(row => monthKey(row.month) === key && row.kind !== 'receipt' && !row.current?.deleted).length;
  }

  // Ngày cuối tháng của khoản không có ngày, không vượt hôm nay: chỉ để xếp thứ tự, cùng cách pay_last của get_dashboard_debt.
  function endOfMonth(key, today) {
    const last = new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)), 0)).toISOString().slice(0, 10);
    return last < today ? last : today;
  }

  /**
   * Dòng "Tiền về và hứa trả": phiếu web, khoản thu sổ gốc, hứa trả, báo đã chuyển. Hứa trả đang chờ đứng đầu, còn lại mới nhất trước. Khoản sổ gốc không có ngày
   * ghi tháng của khối (`date` null), xếp ở cuối tháng đó, không đoán ngày. Mỗi dòng: kind (paid, mark), key (tháng), title, sub, lines [nhãn, giá trị], go;
   * dòng tiền có `amount` (BigInt) để cộng số của một ngày.
   */
  function moneyEvents(data, { marks = [], today }) {
    const out = [];
    const push = (kind, id, key, date, title, sub, lines, go, extra = {}) => out.push({ id: `${kind}:${id}`, kind, key, date, sort: date ?? endOfMonth(key, today), title, sub, lines, go, ...extra });

    for (const row of data.receipts ?? []) {
      if (row.voided_by_event != null || !isDate(row.date)) continue;
      const key = monthKey(row.date);
      const lines = (row.allocations ?? []).map(line => [line.kind === 'advance' ? 'Ứng trước' : `Trừ nợ T${monthLabel(line.month)}`, full(line.amount_vnd)]);
      push('paid', `web-${row.id ?? row.pid}`, key, row.date, full(row.amount_vnd), '', lines, `thang:${key}`, { amount: toBig(row.amount_vnd) });
    }
    for (const row of data.legacy_rows ?? []) {
      if (row.kind !== 'receipt') continue;
      // Dòng chưa sửa có thể không có `current` (khoản thu sổ gốc luôn vậy): số ở source_total_vnd, chữ ở display.
      const current = row.current ?? {};
      if (current.deleted) continue;
      const key = monthKey(row.month ?? current.month);
      const display = typeof row.display === 'object' && row.display !== null ? row.display : {};
      const date = [current.event_date, display.date].find(isDate) ?? null;
      const amount = toBig(current.counted_vnd ?? row.source_total_vnd ?? '0');
      if (amount !== 0n) push('paid', `sheet-${row.id}`, key, date, full(amount), '', [['Theo sổ gốc, ghi ở khối', `T${monthLabel(key)}`]], `thang:${key}`, { amount });
    }
    for (const row of marks) {
      if (row.status === 'cancelled' || (row.kind !== 'promise' && row.kind !== 'paid_claim')) continue;
      const date = row.message_at ? vnDay(row.message_at) : String(row.created_on ?? '').slice(0, 10);
      if (!isDate(date)) continue;
      const waiting = row.status === 'pending' ? 'đang chờ' : row.status;
      const promise = row.kind === 'promise';
      const lines = [row.amount_vnd != null ? ['Số tiền', full(row.amount_vnd)] : null, row.on_date ? ['Hẹn trả', dateText(row.on_date)] : null,
        promise ? ['Trạng thái', waiting] : null].filter(Boolean);
      const amountText = row.amount_vnd != null ? ` ${full(row.amount_vnd)}` : '';
      push('mark', `mark-${row.id}`, monthKey(date), date, `${promise ? 'Hứa trả' : 'Báo đã chuyển'}${amountText}`, promise ? `hẹn ${dateText(row.on_date)} · ${waiting}` : '', lines, 'trao-doi',
        { waiting: promise && row.status === 'pending' });
    }
    return out.sort((a, b) => Boolean(b.waiting) - Boolean(a.waiting) || b.sort.localeCompare(a.sort) || (a.date === null) - (b.date === null));
  }

  /**
   * Số tiền của lần trả gần nhất Tổng quan báo: tổng các khoản đúng ngày đó; chỉ biết tháng thì tổng các khoản không ngày của tháng đó.
   * Không có khoản nào khớp thì null (không đoán số): Tổng quan còn tính cả nguồn sổ không có ở đây.
   */
  function paidOn(events, date, exact) {
    if (!date) return null;
    const rows = events.filter(row => row.kind === 'paid' && (exact ? row.date === date : row.date === null && row.key === monthKey(date)));
    return rows.length ? sum(rows.map(row => row.amount)) : null;
  }

  return { ago, debtTiers, factDate, tripCount, moneyEvents, paidOn };
})();
if (typeof module !== 'undefined') module.exports = TinhHinhModel;
