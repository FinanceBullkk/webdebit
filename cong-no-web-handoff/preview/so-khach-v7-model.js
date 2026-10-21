/* Pure V7 customer ledger money model. Plans describe changes; caller applies them. */
const SoKhachV7Model = (() => {
  function vnd(value, signed = false) {
    if (typeof value !== "string" || !(signed ? /^-?\d+$/ : /^\d+$/).test(value)) {
      throw new Error("Invalid VND amount");
    }
    return BigInt(value);
  }

  function parseVnd(text) {
    if (typeof text !== "string") throw new Error("Invalid VND amount");
    const value = text.trim();
    if (/^\d+$/.test(value)) return vnd(value);
    if (!/^[1-9]\d{0,2}([,.]\d{3})+$/.test(value) || (value.includes(",") && value.includes("."))) {
      throw new Error("Invalid VND amount");
    }
    return vnd(value.replace(/[,.]/g, ""));
  }

  function formatVnd(amount) {
    if (typeof amount !== "bigint") throw new Error("Invalid VND amount");
    const digits = (amount < 0n ? -amount : amount).toString();
    return (amount < 0n ? "-" : "") + digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function formatOutstanding(amount) {
    return amount === 0n ? "–" : formatVnd(amount);
  }

  function parsePositiveVnd(text) {
    const amount = parseVnd(text);
    if (amount === 0n) throw new Error("Receipt must be positive");
    return amount;
  }

  function tripAmount(trip) {
    const price = trip.unitPriceVnd === null ? null : vnd(trip.unitPriceVnd);
    const fee = trip.otherFeeVnd === null ? null : vnd(trip.otherFeeVnd);
    const isFeeOnly = price === null && fee !== null && !trip.container;
    const isMissingPrice = price === null && !isFeeOnly;
    return { amountVnd: isMissingPrice ? null : (price ?? 0n) + (fee ?? 0n), isFeeOnly, isMissingPrice };
  }

  function amountWith(trip, values) {
    const amount = tripAmount({ ...trip, ...values }).amountVnd;
    if (amount === null) throw new Error("Trip has no price");
    return amount;
  }

  function parsePastedTrips(text) {
    if (typeof text !== "string") return { errors: ["Dữ liệu dán không hợp lệ"] };
    const trips = [];
    const errors = [];
    text.split(/\r?\n/).forEach((line, index) => {
      if (!line.trim()) return;
      const fields = line.split("\t").map(field => field.trim());
      if (fields.length !== 7) {
        errors.push(`Dòng ${index + 1}: cần đúng 7 cột`);
        return;
      }
      const [container, carrier, date, from, to, price, fee] = fields;
      if (!container || !carrier || !from || !to) errors.push(`Dòng ${index + 1}: thiếu thông tin chuyến`);
      const match = /^(0[1-9]|[12]\d|3[01])\/(0[1-9]|1[0-2])\/(\d{4})$/.exec(date);
      const parsed = match && new Date(Date.UTC(+match[3], +match[2] - 1, +match[1]));
      if (!parsed || parsed.getUTCFullYear() !== +match[3] || parsed.getUTCMonth() + 1 !== +match[2]
        || parsed.getUTCDate() !== +match[1]) errors.push(`Dòng ${index + 1}: ngày chuyến không hợp lệ`);
      let unitPriceVnd = null;
      let otherFeeVnd = null;
      try { if (price) unitPriceVnd = parseVnd(price).toString(); }
      catch { errors.push(`Dòng ${index + 1}: đơn giá không hợp lệ`); }
      try { if (fee) otherFeeVnd = parseVnd(fee).toString(); }
      catch { errors.push(`Dòng ${index + 1}: phụ phí không hợp lệ`); }
      trips.push({ container, carrier, date, from, to, unitPriceVnd, otherFeeVnd, note: "", src: "" });
    });
    return errors.length ? { errors } : { trips };
  }

  function monthsOf(book) {
    if (!book || !Array.isArray(book.months)) throw new Error("Invalid book");
    const keys = new Set();
    for (const month of book.months) {
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month.key) || keys.has(month.key)
        || !Array.isArray(month.trips) || !Array.isArray(month.receipts)) throw new Error("Invalid month");
      keys.add(month.key);
    }
    return [...book.months].sort((a, b) => a.key.localeCompare(b.key));
  }

  function lineId(month, index) {
    return month.trips[index].id ?? `${month.key}#${index}`;
  }

  function monthChain(book) {
    let carryVnd = 0n;
    const months = monthsOf(book).map(month => {
      let chargesVnd = 0n;
      let adjustmentsVnd = 0n;
      let receivedVnd = 0n;
      let tripCount = 0;
      const missingPriceIds = [];
      month.trips.forEach((trip, index) => {
        const result = tripAmount(trip);
        if (result.isMissingPrice) missingPriceIds.push(lineId(month, index));
        else chargesVnd += result.amountVnd;
        if (!result.isFeeOnly) tripCount++;
      });
      for (const adjustment of month.adjustments ?? []) {
        adjustmentsVnd += vnd(adjustment.amountVnd, true);
      }
      for (const receipt of month.receipts) {
        if (receipt.voided === null) receivedVnd += vnd(receipt.amountVnd);
      }
      const endOfMonthVnd = carryVnd + chargesVnd + adjustmentsVnd - receivedVnd;
      const row = { key: month.key, carryVnd, chargesVnd, adjustmentsVnd, totalChargesVnd: chargesVnd + adjustmentsVnd, receivedVnd,
        endOfMonthVnd, tripCount, lineCount: month.trips.length, missingPriceIds };
      carryVnd = endOfMonthVnd;
      return row;
    });
    return { months, totalOutstandingVnd: carryVnd };
  }

  function outstandingByMonth(book) {
    return monthsOf(book).map(month => {
      const chargesVnd = month.trips.reduce((sum, trip) => sum + (tripAmount(trip).amountVnd ?? 0n), 0n);
      const adjustmentsVnd = (month.adjustments ?? []).reduce((sum, item) =>
        sum + vnd(item.amountVnd, true), 0n);
      const receivedVnd = month.receipts.reduce((sum, receipt) =>
        sum + (receipt.voided === null ? vnd(receipt.amountVnd) : 0n), 0n);
      return { monthKey: month.key, outstandingVnd: chargesVnd + adjustmentsVnd - receivedVnd };
    });
  }

  function validDate(date) {
    if (typeof date !== "string" || !/^(0[1-9]|[12]\d|3[01])\/(0[1-9]|1[0-2])\/\d{4}$/.test(date)) return false;
    const [day, month, year] = date.split("/");
    const parsed = new Date(Date.UTC(+year, +month - 1, +day));
    return parsed.getUTCFullYear() === +year && parsed.getUTCMonth() + 1 === +month && parsed.getUTCDate() === +day;
  }

  function receiptInput({ pid, date, method, amountVnd }) {
    if (typeof pid !== "string" || !pid.trim() || !["THU TIỀN", "CẤN TRỪ", "ỨNG TRƯỚC", "KHÁC"].includes(method) || !validDate(date)) throw new Error("Invalid receipt");
    const amount = vnd(amountVnd);
    if (amount === 0n) throw new Error("Receipt must be positive");
    return amount;
  }

  function planReceipt(book, receipt) {
    const amount = receiptInput(receipt);
    const months = monthsOf(book);
    if (!months.length) throw new Error("No month for receipt");
    if (months.some(month => month.receipts.some(item => item.pid === receipt.pid))) throw new Error("Duplicate receipt pid");
    let left = amount;
    const lines = [];
    for (const row of outstandingByMonth(book)) {
      if (left === 0n) break;
      const applied = row.outstandingVnd > 0n
        ? (left < row.outstandingVnd ? left : row.outstandingVnd) : 0n;
      if (applied > 0n) {
        lines.push({ monthKey: row.monthKey, amountVnd: applied.toString(), kind: "debt" });
        left -= applied;
      }
    }
    if (left > 0n) {
      const lastKey = months.at(-1).key;
      lines.push({ monthKey: lastKey, amountVnd: left.toString(), kind: "advance" });
    }
    return { lines, overpaymentVnd: left, totalVnd: amount };
  }

  function planReallocation(book) {
    const months = monthsOf(book);
    if (!months.length) throw new Error("No month for receipt");
    const debts = outstandingByMonth({ months: months.map(month => ({ ...month, receipts: [] })) })
      .map(row => ({ key: row.monthKey, left: row.outstandingVnd }));
    const receipts = new Map();
    for (const month of months) for (const item of month.receipts) {
      if (item.voided !== null) continue;
      const amount = receiptInput(item);
      let receipt = receipts.get(item.pid);
      if (!receipt) {
        receipt = { pid: item.pid, date: item.date, method: item.kind === "advance" ? item.receiptMethod ?? item.method : item.method, totalVnd: 0n, oldKeys: new Set() };
        receipts.set(item.pid, receipt);
      } else if (receipt.date !== item.date || (item.kind !== "advance" && receipt.method !== item.method)) {
        throw new Error("Conflicting receipt lines");
      }
      if (item.kind !== "advance") receipt.method = item.method;
      receipt.totalVnd += amount;
      receipt.oldKeys.add(month.key);
    }
    const ordered = [...receipts.values()].sort((a, b) => {
      const dateA = a.date.slice(6) + a.date.slice(3, 5) + a.date.slice(0, 2);
      const dateB = b.date.slice(6) + b.date.slice(3, 5) + b.date.slice(0, 2);
      return dateA < dateB ? -1 : dateA > dateB ? 1 : a.pid < b.pid ? -1 : a.pid > b.pid ? 1 : 0;
    });
    const lines = [];
    const changedPids = [];
    for (const receipt of ordered) {
      let left = receipt.totalVnd;
      const newKeys = new Set();
      for (const debt of debts) {
        if (left === 0n) break;
        const applied = debt.left > 0n ? (left < debt.left ? left : debt.left) : 0n;
        if (applied === 0n) continue;
        lines.push({ monthKey: debt.key, receipt: { pid: receipt.pid, date: receipt.date, method: receipt.method,
          amountVnd: applied.toString(), kind: "debt", voided: null } });
        newKeys.add(debt.key);
        debt.left -= applied;
        left -= applied;
      }
      if (left > 0n) {
        const key = months.at(-1).key;
        lines.push({ monthKey: key, receipt: { pid: receipt.pid, date: receipt.date, method: "ỨNG TRƯỚC",
          amountVnd: left.toString(), kind: "advance", receiptMethod: receipt.method, voided: null } });
        newKeys.add(key);
      }
      if (newKeys.size !== receipt.oldKeys.size || [...newKeys].some(key => !receipt.oldKeys.has(key))) changedPids.push(receipt.pid);
    }
    return { lines, changedPids };
  }

  function nextReceiptPid(book) {
    const largest = monthsOf(book).flatMap(month => month.receipts).reduce((max, receipt) => {
      const match = /^PH-(\d+)$/.exec(receipt.pid);
      return match ? Math.max(max, Number(match[1])) : max;
    }, 0);
    return `PH-${String(largest + 1).padStart(3, "0")}`;
  }

  function receiptNotice(pid, plan) {
    const debt = plan.lines.filter(line => line.kind === "debt")
      .map(line => `tháng ${Number(line.monthKey.slice(5))}/${line.monthKey.slice(0, 4)} ${formatVnd(vnd(line.amountVnd))}`);
    const advance = plan.overpaymentVnd > 0n ? [`ỨNG TRƯỚC ${formatVnd(plan.overpaymentVnd)}`] : [];
    return `${pid} đã trừ: ${[...debt, ...advance].join(" · ")}`;
  }

  function receiptDetails(book, pid) {
    const lines = monthsOf(book).flatMap(month => month.receipts.filter(receipt => receipt.pid === pid && receipt.voided === null)
      .map(receipt => ({ monthKey: month.key, receipt })));
    if (!lines.length) throw new Error("Receipt not found");
    return { totalVnd: lines.reduce((sum, line) => sum + vnd(line.receipt.amountVnd), 0n),
      monthKeys: [...new Set(lines.map(line => line.monthKey))] };
  }

  function voidedLines(book, monthKey) {
    const month = monthsOf(book).find(item => item.key === monthKey);
    if (!month) throw new Error("Month not found");
    return month.receipts.filter(receipt => receipt.voided !== null).map(receipt => ({
      amountVnd: vnd(receipt.amountVnd), date: receipt.date, voidedOn: receipt.voidedOn, reason: receipt.voided,
    }));
  }

  function planVoid(book, pid, reason, voidedOn) {
    if (typeof reason !== "string" || !reason.trim()) throw new Error("Void reason required");
    if (!validDate(voidedOn)) throw new Error("Invalid void date");
    const lines = [];
    let totalVnd = 0n;
    for (const month of monthsOf(book)) {
      month.receipts.forEach((receipt, index) => {
        if (receipt.pid !== pid) return;
        if (receipt.voided !== null) throw new Error("Receipt already voided");
        totalVnd += vnd(receipt.amountVnd);
        lines.push({ monthKey: month.key, index, receipt: { ...receipt, voided: reason.trim(), voidedOn } });
      });
    }
    if (!lines.length) throw new Error("Receipt not found");
    return { lines, totalVnd, monthKeys: [...new Set(lines.map(line => line.monthKey))] };
  }

  function planReceiptEdit(book, pid, changes) {
    if (!changes || !Object.keys(changes).length || Object.keys(changes).some(key => !["date", "method"].includes(key))) throw new Error("Invalid receipt edit");
    const draft = structuredClone(book);
    const lines = [];
    for (const month of monthsOf(draft)) month.receipts.forEach((receipt, index) => {
      if (receipt.pid !== pid) return;
      if (receipt.voided !== null) throw new Error("Receipt already voided");
      const updated = { ...receipt, date: changes.date ?? receipt.date,
        method: receipt.kind === "advance" ? "ỨNG TRƯỚC" : changes.method ?? receipt.method };
      if (receipt.kind === "advance") updated.receiptMethod = changes.method ?? receipt.receiptMethod ?? receipt.method;
      receiptInput(updated);
      if (receipt.kind === "advance") receiptInput({ ...updated, method: updated.receiptMethod });
      month.receipts[index] = updated;
      lines.push({ monthKey: month.key, index, receipt: updated });
    });
    if (!lines.length) throw new Error("Receipt not found");
    if (changes.date === undefined) return { lines, reallocation: null };
    return { lines, reallocation: planReallocation(draft) };
  }

  function isMonthOpen(locks, monthKey) {
    if (typeof monthKey !== "string" || !/^\d{4}-(0[1-9]|1[0-2])$/.test(monthKey)) throw new Error("Invalid month key");
    if (!locks || typeof locks !== "object" || typeof locks[monthKey] !== "boolean") throw new Error("Missing month lock");
    return !locks[monthKey];
  }

  function parseSignedVnd(text) {
    if (typeof text !== "string") throw new Error("Invalid VND amount");
    const match = /^([+-]?)(.+)$/.exec(text.trim());
    if (!match) throw new Error("Invalid VND amount");
    const amount = parseVnd(match[2]);
    if (amount === 0n) throw new Error("Adjustment must be nonzero");
    return match[1] === "-" ? -amount : amount;
  }

  function planMonthAdjustment(book, { monthKey, amount, reason }) {
    const month = monthsOf(book).find(item => item.key === monthKey);
    if (!month) throw new Error("Month not found");
    const amountVnd = parseSignedVnd(amount);
    const ids = new Set((month.adjustments ?? []).map(item => item.adjId));
    let sequence = 1;
    while (ids.has(`${monthKey}:month:${sequence}`)) sequence++;
    return { monthKey, adjId: `${monthKey}:month:${sequence}`, amountVnd: amountVnd.toString(),
      reason: typeof reason === "string" ? reason.trim() : "", counted: true };
  }

  function planAdjustment(book, locks, { monthKey, lineId: id, newAmountVnd, reason }) {
    const editable = isMonthOpen(locks, monthKey);
    const month = monthsOf(book).find(item => item.key === monthKey);
    if (!month) throw new Error("Month not found");
    if (editable) {
      throw new Error("Open month: edit trip directly");
    }
    const index = month.trips.findIndex((trip, i) => lineId(month, i) === id);
    if (index < 0) throw new Error("Trip not found");
    const originalAmountVnd = tripAmount(month.trips[index]).amountVnd;
    if (originalAmountVnd === null) throw new Error("Trip has no price");
    const existing = (month.adjustments ?? []).filter(item => item.lineId === id);
    const oldAmountVnd = existing.reduce((sum, item) =>
      sum + vnd(item.amountVnd, true), originalAmountVnd);
    const proposedAmountVnd = vnd(newAmountVnd);
    const amountVnd = proposedAmountVnd - oldAmountVnd;
    if (amountVnd === 0n) return null;
    const usedIds = new Set(existing.map(item => item.adjId));
    let sequence = 1;
    while (usedIds.has(`${id}:adj:${sequence}`)) sequence++;
    return { monthKey, lineId: id, adjId: `${id}:adj:${sequence}`,
      oldAmountVnd, newAmountVnd: proposedAmountVnd,
      amountVnd: amountVnd.toString(), reason: typeof reason === "string" ? reason.trim() : "",
      counted: true };
  }

  function pendingCounts(book) {
    let missingPrice = 0;
    for (const month of monthsOf(book)) {
      missingPrice += month.trips.filter(trip => tripAmount(trip).isMissingPrice).length;
    }
    return { missingPrice, uncertainReceipts: 0 };
  }

  function adjustmentAmount(item) {
    return vnd(item.amountVnd, true);
  }

  return { tripAmount, amountWith, parsePastedTrips, parseVnd, parsePositiveVnd, formatVnd, formatOutstanding, monthChain, outstandingByMonth, planReceipt, planReallocation,
    nextReceiptPid, receiptNotice, receiptDetails, voidedLines, planVoid, planReceiptEdit, planAdjustment, planMonthAdjustment,
    parseSignedVnd, adjustmentAmount, isMonthOpen, pendingCounts };
})();
if (typeof module !== "undefined") module.exports = SoKhachV7Model;
