/* Phép tính cho Bảng thu (BANG-THU-02): bộ lọc mặt hàng và các cách gom, dựng từ đúng dữ liệu tháng của GET /api/v7/receipt-book.
   Không lọc thì tổng lấy nguyên số server; có lọc hoặc gom nhóm thì cộng BigInt ở đây, render (bang-thu-ui.js) chỉ định dạng (ARCH-03).
   Mọi cách gom giữ đẳng thức: tổng các nhóm bằng tổng tháng đang hiện, phần không rõ ngày tính riêng, không cộng vào. */
const BangThuModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const D = typeof DashboardModel !== 'undefined' ? DashboardModel : require('./dashboard-v7-model.js');
  const { toBig, sum, barWidth, UNSORTED } = F;
  const compare = (a, b) => (b > a ? 1 : b < a ? -1 : 0);
  const YEAR_MONTHS = 12;

  /** Map String(id) → nhóm mặt hàng của sổ, cùng cách phân nhóm với bộ lọc Tổng quan. */
  const commodityMap = customers => new Map(customers.map(row => [String(row.id), D.commodityKey(row.commodity, row.transport_mode)]));

  /** Danh sách cho bộ lọc: theo chữ cái, "Chưa phân loại" cuối; không đổi theo tháng để mắt quen chỗ. */
  const commodityOptions = coms => [...new Set(coms.values())].sort((a, b) => ((a === UNSORTED) - (b === UNSORTED)) || a.localeCompare(b, 'vi'));

  const commodityOf = (coms, id) => coms?.get(String(id)) ?? UNSORTED;

  /**
   * Dữ liệu của tháng theo bộ lọc, cùng dạng với `book`. Không lọc (`key` null) thì trả nguyên `book`, số là số server.
   * Có lọc thì cộng lại từ các dòng của sổ thuộc mặt hàng đó; cấn trừ giữ khoản có một đầu thuộc mặt hàng đó.
   */
  function scope(book, key, coms) {
    if (key == null) return book;
    const keep = id => commodityOf(coms, id) === key;
    const days = book.days.map(day => ({ ...day, rows: day.rows.filter(row => keep(row.customer_id)) })).filter(day => day.rows.length)
      .map(day => ({ ...day, total_vnd: String(sum(day.rows.map(row => row.amount_vnd))), count: day.rows.length }));
    const undated = book.undated.filter(row => keep(row.customer_id));
    const customers = book.customers.filter(row => keep(row.customer_id));
    const today = days.find(day => day.date === book.as_of);
    return { ...book, days, undated, customers,
      offsets: book.offsets.filter(row => keep(row.source_customer_id) || keep(row.target_customer_id)),
      voided: book.voided.filter(row => keep(row.customer_id)),
      summary: {
        total_vnd: String(sum(days.map(day => day.total_vnd))),
        count: days.reduce((total, day) => total + day.count, 0),
        customers: customers.filter(row => row.count > 0).length,
        undated_vnd: String(sum(undated.map(row => row.amount_vnd))),
        undated_count: undated.length,
        today_vnd: today?.total_vnd ?? '0',
        today_count: today?.count ?? 0,
        has_sheet: [...days.flatMap(day => day.rows), ...undated].some(row => row.source === 'sheet'),
      } };
  }

  /**
   * Thu của một ngày, cùng dạng `scoped` (TUONG-TAC-01). Không lọc thì trả nguyên. Không rõ ngày, cấn trừ, phiếu hủy thuộc cả tháng nên để trống.
   * Khách cộng lại từ dòng trong ngày, nhiều tiền trước, cùng trường với customers[] của server.
   */
  function scopeDay(scoped, date) {
    if (date == null) return scoped;
    const days = scoped.days.filter(day => day.date === date);
    const rows = days.flatMap(day => day.rows);
    const who = new Map();
    for (const row of rows) {
      const line = who.get(row.customer_id) ?? { customer_id: row.customer_id, name: row.name, total: 0n, count: 0, undated_vnd: '0', undated_count: 0, last_date: date, book_month: row.book_month };
      line.total += toBig(row.amount_vnd);
      line.count += 1;
      if (row.book_month > line.book_month) line.book_month = row.book_month;
      who.set(row.customer_id, line);
    }
    const customers = [...who.values()].sort((a, b) => compare(a.total, b.total)).map(({ total, ...row }) => ({ ...row, total_vnd: String(total) }));
    return { ...scoped, days, undated: [], customers, offsets: [], voided: [],
      summary: { ...scoped.summary, total_vnd: String(sum(days.map(day => day.total_vnd))), count: rows.length, customers: customers.length,
        undated_vnd: '0', undated_count: 0, has_sheet: rows.some(row => row.source === 'sheet') } };
  }

  const widest = rows => rows.reduce((top, row) => (row.total > top ? row.total : top), 0n);
  const fromServer = row => ({ id: row.customer_id, name: row.name, month: row.book_month, total: toBig(row.total_vnd), count: row.count,
    undated: toBig(row.undated_vnd), undatedCount: row.undated_count, lastDate: row.last_date });
  // Nhóm nhiều tiền trước; nhóm chỉ có khoản không rõ ngày xếp theo phần đó.
  const byMoney = (a, b) => compare(a.total, b.total) || compare(a.undated, b.undated);

  /** Theo khách: giữ thứ tự server (cột Đã trả), thêm độ dài thanh so với sổ nhiều tiền nhất. */
  function byCustomer(scoped) {
    const rows = scoped.customers.map(fromServer);
    const top = widest(rows);
    return rows.map(row => ({ ...row, pct: barWidth(row.total, top) }));
  }

  // Gộp các sổ vào nhóm: tổng nhóm, và độ dài thanh của nhóm và sổ theo chung một thước (nhóm lớn nhất).
  function finishGroups(groups) {
    const done = groups.map(group => ({ ...group, total: sum(group.rows.map(row => row.total)), undated: sum(group.rows.map(row => row.undated)),
      count: group.rows.reduce((total, row) => total + row.count, 0), undatedCount: group.rows.reduce((total, row) => total + row.undatedCount, 0) }));
    const top = widest(done);
    return done.map(group => ({ ...group, pct: barWidth(group.total, top), rows: group.rows.map(row => ({ ...row, pct: barWidth(row.total, top) })) }));
  }

  /** Theo mặt hàng: nhóm nhiều tiền trước, trong nhóm giữ thứ tự sổ của server. */
  function byCommodity(scoped, coms) {
    const groups = new Map();
    for (const row of scoped.customers.map(fromServer)) {
      const key = commodityOf(coms, row.id);
      if (!groups.has(key)) groups.set(key, { key, rows: [] });
      groups.get(key).rows.push(row);
    }
    return finishGroups([...groups.values()]).sort((a, b) => byMoney(a, b) || a.key.localeCompare(b.key, 'vi'));
  }

  /** Các phần tiền của một dòng thu theo tháng nợ. Phiếu web đọc phân bổ; dòng Sheet nằm ở tháng của khối; phân bổ thiếu thì phần còn lại đứng riêng. */
  function receiptParts(row) {
    const amount = toBig(row.amount_vnd);
    if (row.source === 'sheet') return [{ kind: 'debt', month: row.book_month, amount }];
    const lines = (row.allocations ?? []).map(line => ({ kind: line.kind === 'advance' ? 'advance' : 'debt', month: line.month, amount: toBig(line.amount_vnd) }));
    const rest = amount - sum(lines.map(line => line.amount));
    return rest === 0n ? lines : [...lines, { kind: 'none', month: row.book_month, amount: rest }];
  }

  const KIND_ORDER = { debt: 0, advance: 1, none: 2 };
  const partKey = part => (part.kind === 'debt' ? part.month : part.kind);

  /**
   * Phiếu của một khách để mở tại dòng: có ngày trước (mới nhất lên trên), không rõ ngày sau. `debtKey` là nhóm của tab Theo tháng nợ:
   * chỉ lấy phần tiền của nhóm đó, để số mở ra cộng bằng số trên dòng khách.
   */
  function receiptsOf(scoped, id, debtKey = null) {
    const amount = row => (debtKey == null ? toBig(row.amount_vnd) : sum(receiptParts(row).filter(part => partKey(part) === debtKey).map(part => part.amount)));
    const mine = (rows, dated) => rows.filter(row => row.customer_id === id).map(row => ({ row, dated, amount: amount(row) })).filter(item => item.amount !== 0n);
    return [...mine(scoped.days.flatMap(day => day.rows), true), ...mine(scoped.undated, false)];
  }

  /**
   * Theo tháng nợ: nợ cũ lên trước, rồi Ứng trước, rồi Chưa phân bổ. Phiếu chia nhiều tháng đếm ở mỗi nhóm nên tổng "Số lần" các nhóm
   * có thể lớn hơn số phiếu; tiền thì tách đúng phần, tổng các nhóm bằng tổng tháng.
   */
  function byDebtMonth(scoped) {
    const groups = new Map();
    const add = (row, dated) => {
      for (const part of receiptParts(row)) {
        const key = partKey(part);
        if (!groups.has(key)) groups.set(key, { key, kind: part.kind, month: part.kind === 'debt' ? part.month : null, who: new Map() });
        const who = groups.get(key).who;
        if (!who.has(row.customer_id)) who.set(row.customer_id, { id: row.customer_id, name: row.name, month: part.month, total: 0n, count: 0, undated: 0n, undatedCount: 0, lastDate: null });
        const line = who.get(row.customer_id);
        if (part.month > line.month) line.month = part.month;
        if (dated) {
          line.total += part.amount;
          line.count += 1;
          if (!line.lastDate || row.date > line.lastDate) line.lastDate = row.date;
        } else {
          line.undated += part.amount;
          line.undatedCount += 1;
        }
      }
    };
    for (const day of scoped.days) for (const row of day.rows) add(row, true);
    for (const row of scoped.undated) add(row, false);
    const list = [...groups.values()].map(({ who, ...group }) => ({ ...group,
      rows: [...who.values()].sort((a, b) => byMoney(a, b) || a.name.localeCompare(b.name, 'vi')) }));
    return finishGroups(list).sort((a, b) => (KIND_ORDER[a.kind] - KIND_ORDER[b.kind]) || String(a.month).localeCompare(String(b.month)));
  }

  // Tháng lùi `back` tháng so với "YYYY-MM-01", tính bằng số nguyên, không qua múi giờ.
  function monthBack(month, back) {
    const n = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 - back;
    return `${Math.floor(n / 12)}-${String(n % 12 + 1).padStart(2, '0')}-01`;
  }

  /** 12 tháng liền tính tới tháng mới nhất; tháng không có phiếu vẫn có dòng (`has` false) để không giấu khoảng trống. Thanh theo chung một thước. */
  function lastYear(book) {
    const byMonth = new Map(book.months.map(item => [item.month, item]));
    const latest = [book.today_month, ...book.months.map(item => item.month)].sort().at(-1);
    const rows = Array.from({ length: YEAR_MONTHS }, (_, back) => {
      const month = monthBack(latest, back);
      const item = byMonth.get(month);
      return { month, has: Boolean(item && (item.count || item.undated_count)), total: toBig(item?.total_vnd ?? '0'), count: item?.count ?? 0,
        undated: toBig(item?.undated_vnd ?? '0'), undatedCount: item?.undated_count ?? 0 };
    });
    const top = rows.reduce((max, row) => (row.total + row.undated > max ? row.total + row.undated : max), 0n);
    return rows.map(row => ({ ...row, pct: barWidth(row.total, top), undatedPct: barWidth(row.undated, top) }));
  }

  /** Dải ngày: mỗi ngày của tháng một cột, cột cao theo ngày nhiều tiền nhất; `total` null là ngày không có phiếu; `shares` là phần trăm của từng khách trong cột. */
  function dayStrip(scoped, book) {
    const year = Number(book.month.slice(0, 4));
    const month = Number(book.month.slice(5, 7));
    const count = new Date(Date.UTC(year, month, 0)).getUTCDate();
    const byDate = new Map(scoped.days.map(day => [day.date, day]));
    const top = scoped.days.reduce((max, day) => (toBig(day.total_vnd) > max ? toBig(day.total_vnd) : max), 0n);
    return Array.from({ length: count }, (_, index) => {
      const date = `${book.month.slice(0, 8)}${String(index + 1).padStart(2, '0')}`;
      const day = byDate.get(date);
      const who = {};
      for (const row of day?.rows ?? []) who[row.customer_id] = (who[row.customer_id] ?? 0n) + toBig(row.amount_vnd);
      return { day: index + 1, date, total: day?.total_vnd ?? null, count: day?.count ?? 0, pct: day ? barWidth(day.total_vnd, top) : 0,
        customers: Object.keys(who).length, shares: Object.fromEntries(Object.entries(who).map(([id, value]) => [id, barWidth(value, toBig(day.total_vnd))])),
        today: date === book.as_of, future: date > book.as_of };
    });
  }

  /**
   * Phiếu Sheet chưa ghi vào web, cùng cách đếm với tab Đòi nợ; có lọc thì chỉ sổ thuộc mặt hàng đó.
   * Trả 'computing' (API vừa khởi động), 'unknown' (không đọc được), null (không còn phiếu) hoặc { count, amount }.
   */
  function pending(inbox, key = null, coms = null) {
    if (inbox?.state === 'computing') return 'computing';
    if (inbox?.state !== 'ready') return 'unknown';
    const books = (inbox.books ?? []).filter(book => !book.sheet_matched && book.receipts.ready + book.receipts.review > 0
      && (key == null || commodityOf(coms, book.customer_id) === key));
    if (!books.length) return null;
    return { count: books.reduce((total, book) => total + book.receipts.ready + book.receipts.review, 0), amount: String(sum(books.map(book => book.receipts.amount_vnd))) };
  }

  return { commodityMap, commodityOptions, scope, scopeDay, receiptsOf, byCustomer, byCommodity, receiptParts, byDebtMonth, lastYear, dayStrip, pending };
})();
if (typeof module !== 'undefined') module.exports = BangThuModel;
