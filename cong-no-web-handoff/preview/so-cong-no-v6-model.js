/* In-memory V6 money model. No posting or live data. */
const LedgerV6Model = (() => {
  function vnd(value, signed = false) {
    if (typeof value === "bigint") {
      if (!signed && value < 0n) throw new Error("Invalid VND amount");
      return value;
    }
    if (typeof value !== "string" || !(signed ? /^-?\d+$/ : /^\d+$/).test(value)) {
      throw new Error("Invalid VND amount");
    }
    return BigInt(value);
  }

  function monthKey(key) {
    if (typeof key !== "string" || !/^\d{4}-(0[1-9]|1[0-2])$/.test(key)) {
      throw new Error("Invalid month key");
    }
    return key;
  }

  function isoDay(value) {
    if (typeof value !== "string" || !/^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(value)) {
      throw new Error("Invalid ISO day");
    }
    const year = BigInt(value.slice(0, 4));
    const month = value.slice(5, 7);
    const day = BigInt(value.slice(8));
    const leap = year % 4n === 0n && (year % 100n !== 0n || year % 400n === 0n);
    const maximum = month === "02" ? (leap ? 29n : 28n)
      : ["04", "06", "09", "11"].includes(month) ? 30n : 31n;
    if (day > maximum) throw new Error("Invalid ISO day");
    return value;
  }

  function lineAmount({ unitPriceVnd, otherFeeVnd, plugFeeVnd, escortFeeVnd }) {
    const price = unitPriceVnd === null ? null : vnd(unitPriceVnd);
    const fees = [otherFeeVnd, plugFeeVnd, escortFeeVnd]
      .reduce((total, fee) => total + (fee === null ? 0n : vnd(fee)), 0n);
    return price === null ? null : price + fees;
  }

  function monthTotals(lines) {
    const result = { pricedCount: 0, pricedTotalVnd: 0n, missingPriceIds: [], mismatches: [] };
    for (const line of lines) {
      const amount = lineAmount(line);
      const pastedVnd = line.pastedAmountVnd === null ? null : vnd(line.pastedAmountVnd);
      if (amount === null) result.missingPriceIds.push(line.id);
      else {
        result.pricedCount += 1;
        result.pricedTotalVnd += amount;
        if (pastedVnd !== null && pastedVnd !== amount) result.mismatches.push({
          id: line.id, pastedVnd, computedVnd: amount,
          diffVnd: pastedVnd > amount ? pastedVnd - amount : amount - pastedVnd,
        });
      }
    }
    return result;
  }

  function isDirectEditable(key, todayIso) {
    monthKey(key);
    isoDay(todayIso);
    const next = key.slice(5) === "12"
      ? `${(BigInt(key.slice(0, 4)) + 1n).toString().padStart(4, "0")}-01`
      : `${key.slice(0, 5)}${(BigInt(key.slice(5)) + 1n).toString().padStart(2, "0")}`;
    return todayIso <= `${next}-05`;
  }

  function openingLineIds(lines) {
    if (!Array.isArray(lines)) throw new Error("Opening month needs a lines list");
    const ids = new Set();
    for (const line of lines) {
      if (!line || typeof line.id !== "string" || !line.id.trim()) throw new Error("Invalid opening line id");
      if (ids.has(line.id)) throw new Error("Duplicate opening line id");
      ids.add(line.id);
    }
    return ids;
  }

  function checkedBook(book) {
    const { opening, months, adjustments, receipts } = book;
    const beforeBalanceVnd = vnd(opening.beforeBalanceVnd);
    if (typeof opening.beforeKey !== "string" || !opening.beforeKey.trim() ||
        !Array.isArray(opening.months) || !Array.isArray(months) ||
        !Array.isArray(adjustments) || !Array.isArray(receipts)) throw new Error("Invalid book");
    const keys = new Set();
    let previous = "";
    let openingDebtVnd = beforeBalanceVnd;
    for (const month of opening.months) {
      monthKey(month.key);
      if (month.key <= previous) throw new Error("Months must increase without duplicates");
      previous = month.key;
      keys.add(month.key);
      openingLineIds(month.lines);
      openingDebtVnd += vnd(month.remainingVnd);
      vnd(month.endOfMonthVnd, true);
    }
    if (opening.months.length && openingDebtVnd !== vnd(opening.months.at(-1).endOfMonthVnd, true)) {
      throw new Error("Opening balance does not match remaining debt");
    }
    for (const month of months) {
      monthKey(month.key);
      if (month.key <= previous || !Array.isArray(month.lines)) {
        throw new Error("Web months must follow opening months in order");
      }
      previous = month.key;
      keys.add(month.key);
    }
    const adjusted = new Map();
    for (const item of adjustments) {
      if (!keys.has(monthKey(item.monthKey)) || typeof item.reason !== "string" || !item.reason.trim()) {
        throw new Error("Invalid adjustment");
      }
      const amount = vnd(item.amountVnd, true);
      if (amount === 0n) throw new Error("Zero adjustment");
      adjusted.set(item.monthKey, (adjusted.get(item.monthKey) ?? 0n) + amount);
    }
    for (const receipt of receipts) {
      if (!keys.has(monthKey(receipt.monthKey))) throw new Error("Receipt month not in book");
      if (receipt.receivedOn !== null) {
        isoDay(receipt.receivedOn);
        vnd(receipt.amountVnd);
      }
    }
    return { beforeBalanceVnd, adjusted };
  }

  function monthChain(book) {
    const { beforeBalanceVnd, adjusted } = checkedBook(book);
    const chain = [];
    let carryVnd = beforeBalanceVnd;
    let openingAdjustmentsVnd = 0n;
    for (const month of book.opening.months) {
      const adjustmentsVnd = adjusted.get(month.key) ?? 0n;
      openingAdjustmentsVnd += adjustmentsVnd;
      const endOfMonthVnd = vnd(month.endOfMonthVnd, true) + openingAdjustmentsVnd;
      chain.push({ key: month.key, source: "opening", carryVnd, chargesVnd: null,
        adjustmentsVnd, receivedVnd: null, endOfMonthVnd, missingPriceIds: [], mismatches: [] });
      carryVnd = endOfMonthVnd;
    }
    for (const month of book.months) {
      const { pricedTotalVnd, missingPriceIds, mismatches } = monthTotals(month.lines);
      const adjustmentsVnd = adjusted.get(month.key) ?? 0n;
      const receivedVnd = book.receipts.reduce((sum, receipt) =>
        sum + (receipt.monthKey === month.key && receipt.receivedOn !== null ? vnd(receipt.amountVnd) : 0n), 0n);
      const endOfMonthVnd = carryVnd + pricedTotalVnd + adjustmentsVnd - receivedVnd;
      chain.push({ key: month.key, source: "web", carryVnd, chargesVnd: pricedTotalVnd,
        adjustmentsVnd, receivedVnd, endOfMonthVnd, missingPriceIds, mismatches });
      carryVnd = endOfMonthVnd;
    }
    return chain;
  }

  function allocate(book) {
    const chain = monthChain(book);
    const remaining = [{ key: book.opening.beforeKey, balanceVnd: vnd(book.opening.beforeBalanceVnd) },
      ...book.opening.months.map(month => ({ key: month.key,
        balanceVnd: vnd(month.remainingVnd) + chain.find(row => row.key === month.key).adjustmentsVnd })),
      ...chain.filter(row => row.source === "web").map(row => ({ key: row.key,
        balanceVnd: row.chargesVnd + row.adjustmentsVnd }))];
    if (remaining.some(row => row.balanceVnd < 0n)) throw new Error("Negative debt bucket");
    let overpaymentVnd = 0n;
    const receipts = book.receipts.filter(receipt => receipt.receivedOn !== null)
      .sort((a, b) => a.receivedOn < b.receivedOn ? -1 : a.receivedOn > b.receivedOn ? 1
        : a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
      .map(receipt => {
        let left = vnd(receipt.amountVnd);
        const allocations = [];
        for (const debt of remaining) {
          if (left === 0n) break;
          const amountVnd = left < debt.balanceVnd ? left : debt.balanceVnd;
          if (amountVnd === 0n) continue;
          allocations.push({ key: debt.key, amountVnd });
          debt.balanceVnd -= amountVnd;
          left -= amountVnd;
        }
        overpaymentVnd += left;
        return { id: receipt.id, allocations, overpaymentVnd: left };
      });
    return { receipts, remaining, overpaymentVnd };
  }

  function validateAdjustment(adjustment, book) {
    const reasons = [];
    if (typeof adjustment.reason !== "string" || !adjustment.reason.trim()) reasons.push("Thiếu lý do.");
    try {
      if (vnd(adjustment.amountVnd, true) === 0n) reasons.push("Số tiền điều chỉnh phải khác 0.");
    } catch { reasons.push("Số tiền điều chỉnh sai định dạng."); }
    const month = [...book.opening.months, ...book.months].find(item => item.key === adjustment.monthKey);
    if (!month) reasons.push("Tháng không có trong sổ.");
    else if (adjustment.lineId !== null && !month.lines.some(line => line.id === adjustment.lineId)) {
      reasons.push("Dòng không có trong tháng.");
    }
    return { ok: reasons.length === 0, reasons };
  }

  return { lineAmount, monthTotals, isDirectEditable, monthChain, allocate, validateAdjustment };
})();
if (typeof module !== "undefined") module.exports = LedgerV6Model;
