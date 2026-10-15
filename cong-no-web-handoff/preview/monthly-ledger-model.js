/* Handoff v2 fixture only. Amounts are exact integer VND; no live ledger writes. */
const MonthlyLedgerPreview = (() => {
  const customer = { id: "KH-DEMO", name: "KHACH_MAU" };
  const shipments = [
    { id: "CH-001", period: "2026-01", date: "2026-01-02", container: "EMCU5391060", carrier: "EVG", origin: "TIEN GIANG", destination: "HONGKONG", price: 42000000n, fees: 1000000n, total: 43000000n, status: "posted" },
    { id: "CH-002", period: "2026-01", date: "2026-01-02", container: "EMCU5625868", carrier: "EVG", origin: "TIEN GIANG", destination: "HONGKONG", price: 43500000n, fees: 0n, total: 43500000n, status: "posted" },
    { id: "CH-003", period: "2026-01", date: "2026-01-02", container: "EMCU5738000", carrier: "EMC", origin: "TIEN GIANG", destination: "HONGKONG", price: 43500000n, fees: 2500000n, total: 46000000n, status: "posted" },
    { id: "CH-004", period: "2026-01", date: "2026-01-05", container: "SEGU9951606", carrier: "WH", origin: "PHAN THIET", destination: "SHEKOU", price: 45500000n, fees: 0n, total: 45500000n, status: "posted" },
    { id: "CH-005", period: "2026-02", date: "2026-02-05", container: "DFOU6412431", carrier: null, origin: null, destination: null, price: 43000000n, fees: 0n, total: 43000000n, status: "posted" },
    { id: "CH-006", period: "2026-02", date: "2026-02-08", container: "FBIU5374130", carrier: null, origin: null, destination: null, price: 46000000n, fees: 1000000n, total: 47000000n, status: "posted" },
    { id: "CH-007", period: "2026-02", date: "2026-02-10", container: "BMOU9318648", carrier: null, origin: null, destination: null, price: null, fees: 0n, total: null, status: "waiting_price" },
  ];
  const payments = [
    { id: "PT-001/A1", receiptId: "PT-001", period: "2025-12", date: "2026-02-10", kind: "receipt", amount: 441500000n, receiptTotal: 441500000n, status: "posted" },
    { id: "OFF-001", receiptId: null, period: "2026-01", date: "2026-01-31", kind: "offset", amount: 80000000n, receiptTotal: null, status: "posted" },
    { id: "PT-003/A1", receiptId: "PT-003", period: "2026-01", date: "2026-03-20", kind: "receipt", amount: 50000000n, receiptTotal: 50000000n, status: "posted" },
    { id: "PT-004/A1", receiptId: "PT-004", period: "2026-02", date: "2026-03-10", kind: "receipt", amount: 30000000n, receiptTotal: 30000000n, status: "posted" },
    { id: "PT-005", receiptId: "PT-005", period: "2026-02", date: "2026-03-12", kind: "receipt", amount: 10000000n, receiptTotal: 10000000n, status: "waiting_confirmation" },
  ];
  const openings = [{ id: "SD-001", period: "2025-12", date: "2025-12-31", amount: 441500000n, status: "posted" }];
  const periods = ["2025-12", "2026-01", "2026-02"];
  const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
  const byDateId = (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id);

  function snapshot({ asOf = "2026-10-14", period = "all" } = {}) {
    if (!validDate(asOf) || asOf < "2025-12-31" || asOf > "2026-10-14") throw new Error("Date outside fixture");
    if (period !== "all" && !periods.includes(period)) throw new Error("Unknown period");
    const months = periods.map(debtPeriod => {
      const monthOpenings = openings.filter(row => row.period === debtPeriod && row.date <= asOf);
      const monthShipments = shipments.filter(row => row.period === debtPeriod && row.date <= asOf).sort(byDateId);
      const monthPayments = payments.filter(row => row.period === debtPeriod && row.date <= asOf).sort(byDateId);
      if (!monthOpenings.length && !monthShipments.length && !monthPayments.length) return null;
      const opening = monthOpenings.reduce((sum, row) => sum + row.amount, 0n);
      const charge = monthShipments.reduce((sum, row) => sum + (row.status === "posted" ? row.total : 0n), 0n);
      const paid = monthPayments.reduce((sum, row) => sum + (row.status === "posted" ? row.amount : 0n), 0n);
      return {
        period: debtPeriod, openings: monthOpenings, shipments: monthShipments, payments: monthPayments,
        opening, charge, paid, balance: opening + charge - paid,
        waitingPrice: monthShipments.filter(row => row.status === "waiting_price").length,
        waitingConfirmation: monthPayments.filter(row => row.status === "waiting_confirmation").length,
      };
    }).filter(Boolean);
    const visible = period === "all" ? months : months.filter(month => month.period === period);
    const sum = (list, key) => list.reduce((total, month) => total + month[key], 0n);
    return {
      customer, asOf, period, months: visible,
      allBalance: sum(months, "balance"), visibleBalance: sum(visible, "balance"),
      waitingPrice: months.reduce((count, month) => count + month.waitingPrice, 0),
      waitingConfirmation: months.reduce((count, month) => count + month.waitingConfirmation, 0),
      confirmedUnallocated: 0n,
    };
  }
  function planReceipt(amountVnd, asOf = "2026-10-14") {
    if (!/^\d+$/.test(String(amountVnd)) || BigInt(amountVnd) <= 0n) throw new Error("Invalid receipt amount");
    let remaining = BigInt(amountVnd);
    const allocations = [];
    for (const month of snapshot({ asOf, period: "all" }).months) {
      const available = month.balance > 0n ? month.balance : 0n;
      const applied = remaining < available ? remaining : available;
      if (applied > 0n) allocations.push({ period: month.period, amount: applied });
      remaining -= applied;
      if (remaining === 0n) break;
    }
    return { allocations, unallocated: remaining };
  }
  return { snapshot, planReceipt };
})();
if (typeof module !== "undefined") module.exports = MonthlyLedgerPreview;
