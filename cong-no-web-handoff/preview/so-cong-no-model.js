/* Read-only fixture model for the proposed Sổ công nợ screen. No live data. */
const LedgerPreview = (() => {
  const customer = { id: "KH-001", name: "Công ty Minh An" };
  const base = [
    { id: "SD-001", period: "2025-12", date: "2025-12-31", sequence: 1, signed: "2800000000", type: "opening", label: "Số dư đầu đã ghi sổ", source: "Fixture A" },
    { id: "CH-001", period: "2026-10", date: "2026-10-05", sequence: 2, signed: "500000000", type: "shipment", label: "Chuyến hàng CH-001", source: "Fixture A" },
    { id: "PT-001/A1", period: "2026-10", date: "2026-10-12", sequence: 3, signed: "-200000000", type: "receipt", label: "Phân bổ thu PT-001 · kỳ 10", source: "PT-001 · thực nhận 200,000,000 VND ngày 12/10/2026" },
  ];
  const extra = [
    { id: "CH-003", period: "2026-09", date: "2026-09-20", sequence: 4, signed: "100000000", type: "shipment", label: "Chuyến hàng CH-003", source: "Fixture B" },
    { id: "PT-003/A1", period: "2026-09", date: "2026-10-14", sequence: 5, signed: "-100000000", type: "receipt", label: "Phân bổ PT-003 · kỳ 09", source: "PT-003 · thực nhận 150,000,000 VND ngày 14/10/2026" },
    { id: "PT-003/A2", period: "2026-10", date: "2026-10-14", sequence: 6, signed: "-50000000", type: "receipt", label: "Phân bổ PT-003 · kỳ 10", source: "PT-003 · thực nhận 150,000,000 VND ngày 14/10/2026" },
  ];
  const pending = [
    { id: "CH-002", date: "2026-10-13", type: "shipment", status: "Chờ giá", detail: "Chưa xác định đơn giá; phụ phí cũng chưa vào số dư." },
    { id: "PT-002", date: "2026-10-14", type: "receipt", status: "Chờ xác nhận", detail: "Thu dự kiến 50,000,000 VND; đề nghị trả kỳ 2026-09. Chưa tính là thực thu." },
  ];
  const amount = value => BigInt(value);
  const sum = rows => rows.reduce((total, item) => total + amount(item.signed), 0n);
  const order = (a, b) => a.date.localeCompare(b.date) || a.sequence - b.sequence || a.id.localeCompare(b.id);

  // Proposed allocation for a confirmed new receipt. No database write.
  function allocateOldestFirst(receiptVnd, periodBalances) {
    if (!/^\d+$/.test(String(receiptVnd)) || amount(receiptVnd) <= 0n) throw new Error("Invalid receipt amount");
    if (!Array.isArray(periodBalances)) throw new Error("Invalid period balances");
    const seen = new Set();
    const sorted = periodBalances.map(item => {
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(item.period) || !/^-?\d+$/.test(String(item.balanceVnd)) || seen.has(item.period)) throw new Error("Invalid period balance");
      seen.add(item.period);
      return { period: item.period, balance: amount(item.balanceVnd) };
    }).sort((a, b) => a.period.localeCompare(b.period));
    let remaining = amount(receiptVnd);
    const allocations = [];
    for (const item of sorted) {
      const applied = item.balance > 0n ? (remaining < item.balance ? remaining : item.balance) : 0n;
      if (applied > 0n) allocations.push({ period: item.period, amountVnd: applied });
      remaining -= applied;
      if (remaining === 0n) break;
    }
    return { allocations, unallocatedVnd: remaining };
  }

  function snapshot({ fixture = "A", period = "2026-10", asOf = "2026-10-14", page = 1, pageSize = 2 } = {}) {
    if (!["A", "B"].includes(fixture)) throw new Error("Unknown fixture");
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period)) throw new Error("Invalid period");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(asOf) || asOf < "2025-12-31" || asOf > "2026-10-14") throw new Error("Date outside fixture");
    if (!Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1) throw new Error("Invalid pagination");
    const entries = (fixture === "B" ? base.concat(extra) : base).filter(item => item.date <= asOf);
    const previous = sum(entries.filter(item => item.period < period));
    const selected = sum(entries.filter(item => item.period === period));
    const later = sum(entries.filter(item => item.period > period));
    const start = asOf.slice(0, 7) + "-01";
    const opening = sum(entries.filter(item => item.period === period && item.date < start));
    let running = opening;
    const fullRows = entries.filter(item => item.period === period && item.date >= start).sort(order).map(item => {
      running += amount(item.signed);
      return { ...item, running };
    });
    const pageCount = Math.max(1, Math.ceil(fullRows.length / pageSize));
    const safePage = Math.min(page, pageCount);
    return {
      customer, fixture, period, asOf, start, opening,
      previous, selected, later, all: previous + selected + later,
      unallocated: 0n, // Both fixtures allocate every confirmed receipt in full.
      rows: fullRows.slice((safePage - 1) * pageSize, safePage * pageSize),
      rowCount: fullRows.length, page: safePage, pageCount,
      pending: pending.filter(item => item.date <= asOf),
    };
  }
  return { snapshot, allocateOldestFirst };
})();
if (typeof module !== "undefined") module.exports = LedgerPreview;
