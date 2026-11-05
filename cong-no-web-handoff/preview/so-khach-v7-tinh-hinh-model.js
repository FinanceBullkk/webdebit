/* Phép tính cho thẻ Tình hình (TUONG-TAC-01): từng tháng nợ theo hạn, dòng Hoạt động, số chuyến mỗi tháng, thước của hình.
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

  /** Chuyến của một tháng: dòng web (trừ đã xóa, đã loại, phí lẻ) và dòng chuyến sổ gốc chưa xóa, cùng cách đếm thẻ Đi hàng. */
  function tripCount(data, key) {
    return (data.trips ?? []).filter(trip => monthKey(trip.month) === key && !trip.deleted && trip.status !== 'rejected' && !trip.is_fee_only).length
      + (data.legacy_rows ?? []).filter(row => monthKey(row.month) === key && row.kind !== 'receipt' && !row.current?.deleted).length;
  }

  // Ngày cuối tháng của khoản không có ngày, không vượt hôm nay: chỉ để xếp thứ tự, cùng cách pay_last của get_dashboard_debt.
  function endOfMonth(key, today) {
    const last = new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)), 0)).toISOString().slice(0, 10);
    return last < today ? last : today;
  }

  function tripLine(container, amount, priced) {
    return [container || 'Không có container', priced ? full(amount) : 'chưa giá'];
  }

  /**
   * Dòng Hoạt động, mới nhất trước. Gồm phiếu web, khoản thu và chuyến sổ gốc, dấu Zalo, hội thoại Zalo. Khoản sổ gốc không có ngày ghi tháng của khối
   * (`date` null), xếp ở cuối tháng đó, không đoán ngày. Mỗi dòng: kind (paid, trip, mark, remind), key (tháng), title, sub, lines [nhãn, giá trị], go.
   */
  function activity(data, { marks = [], chats = [], today }) {
    const out = [];
    const push = (kind, id, key, date, title, sub, lines, go) => out.push({ id: `${kind}:${id}`, kind, key, date, sort: date ?? endOfMonth(key, today), title, sub, lines, go });

    for (const row of data.receipts ?? []) {
      if (row.voided_by_event != null || !isDate(row.date)) continue;
      const key = monthKey(row.date);
      const lines = (row.allocations ?? []).map(line => [line.kind === 'advance' ? 'Ứng trước' : `Trừ nợ T${monthLabel(line.month)}`, full(line.amount_vnd)]);
      push('paid', `web-${row.id ?? row.pid}`, key, row.date, `Khách trả ${full(row.amount_vnd)}`, row.method ?? '', lines, `thang:${key}`);
    }
    const trips = new Map();
    const addTrip = (key, date, destination, line) => {
      const id = `${date ?? key}|${destination}`;
      if (!trips.has(id)) trips.set(id, { key, date, destination, lines: [] });
      trips.get(id).lines.push(line);
    };
    for (const row of data.trips ?? []) {
      if (row.deleted || row.status !== 'confirmed' || row.is_fee_only) continue;
      const key = monthKey(row.month ?? row.event_date);
      addTrip(key, isDate(row.event_date) ? row.event_date : null, row.destination ?? '', tripLine(row.container, row.amount_vnd, row.amount_vnd != null));
    }
    for (const row of data.legacy_rows ?? []) {
      // Dòng chưa sửa có thể không có `current` (khoản thu sổ gốc luôn vậy): số ở source_total_vnd, chữ ở display.
      const current = row.current ?? {};
      if (current.deleted) continue;
      const key = monthKey(row.month ?? current.month);
      const display = typeof row.display === 'object' && row.display !== null ? row.display : {};
      const date = [current.event_date, display.date].find(isDate) ?? null;
      const amount = toBig(current.counted_vnd ?? row.source_total_vnd ?? '0');
      if (row.kind === 'receipt') {
        if (amount !== 0n) push('paid', `sheet-${row.id}`, key, date, `Khách trả ${full(amount)}`, 'theo sổ gốc', [['Ghi ở khối', `T${monthLabel(key)}`]], `thang:${key}`);
      } else {
        const priced = (current.unit_price_vnd ?? display.unit_price) != null || amount !== 0n;
        addTrip(key, date, current.destination ?? display.to ?? '', tripLine(current.container ?? display.container, amount, priced));
      }
    }
    for (const [id, group] of trips) {
      push('trip', id, group.key, group.date, `${group.lines.length} chuyến đi hàng`, group.destination, group.lines, `thang:${group.key}`);
    }
    for (const row of marks) {
      if (row.status === 'cancelled') continue;
      const date = row.message_at ? vnDay(row.message_at) : String(row.created_on ?? '').slice(0, 10);
      if (!isDate(date)) continue;
      const waiting = row.status === 'pending' ? 'đang chờ' : row.status;
      const title = row.kind === 'promise' ? `Hứa trả ${full(row.amount_vnd)}` : row.kind === 'paid_claim' ? `Báo đã chuyển ${full(row.amount_vnd)}` : 'Ghi chú';
      const lines = [row.amount_vnd != null ? ['Số tiền', full(row.amount_vnd)] : null, row.on_date ? ['Hẹn trả', dateText(row.on_date)] : null,
        row.kind === 'promise' ? ['Trạng thái', waiting] : null].filter(Boolean);
      push('mark', `mark-${row.id}`, monthKey(date), date, title, row.kind === 'promise' ? `hẹn ${dateText(row.on_date)} · ${waiting}` : '', lines, 'trao-doi');
    }
    for (const row of chats) {
      if (!row.last_message_at) continue;
      const date = vnDay(row.last_message_at);
      if (isDate(date)) push('remind', `zalo-${row.id ?? row.display_name}`, monthKey(date), date, 'Zalo gần nhất', row.display_name ?? '', [['Hội thoại', row.display_name ?? '']], 'trao-doi');
    }
    return out.sort((a, b) => b.sort.localeCompare(a.sort) || (a.date === null) - (b.date === null));
  }

  const KINDS = { all: () => true, paid: row => row.kind === 'paid', trip: row => row.kind === 'trip', talk: row => row.kind === 'mark' || row.kind === 'remind' };

  /** Thước của hình: vị trí 0–1 của một giá trị, gồm cả số 0 để cột âm không tràn. */
  function scale(values) {
    const known = values.filter(value => value !== null).map(value => BigInt(value));
    const bottom = known.reduce((min, value) => (value < min ? value : min), 0n);
    const top = known.reduce((max, value) => (value > max ? value : max), 0n);
    const at = value => (value === null ? null : top === bottom ? 0 : Number((BigInt(value) - bottom) * 10000n / (top - bottom)) / 10000);
    return { at, zeroAt: at(0n) };
  }

  return { ago, debtTiers, factDate, tripCount, activity, KINDS, scale };
})();
if (typeof module !== 'undefined') module.exports = TinhHinhModel;
