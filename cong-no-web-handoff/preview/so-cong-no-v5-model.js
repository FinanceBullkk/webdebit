/* In-memory V5 money model. No posting or live data. */
const LedgerV5Model = (() => {
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

  function lineAmount({ unitPriceVnd, otherFeeVnd, plugFeeVnd, escortFeeVnd }) {
    const price = unitPriceVnd === null ? null : vnd(unitPriceVnd);
    const fees = [otherFeeVnd, plugFeeVnd, escortFeeVnd]
      .reduce((total, fee) => total + (fee === null ? 0n : vnd(fee)), 0n);
    return price === null ? null : price + fees;
  }

  function monthTotals(lines) {
    const result = { pricedCount: 0, pricedTotalVnd: 0n, missingPriceIds: [] };
    for (const line of lines) {
      const amount = lineAmount(line);
      if (amount === null) result.missingPriceIds.push(line.id);
      else {
        result.pricedCount += 1;
        result.pricedTotalVnd += amount;
      }
    }
    return result;
  }

  function allocateReceipt(receiptVnd, buckets) {
    let remaining = vnd(receiptVnd);
    const balances = buckets.map(bucket => {
      if (bucket.kind !== "closed" && bucket.kind !== "open") throw new Error("Invalid bucket kind");
      return { ...bucket, balanceVnd: vnd(bucket.balanceVnd, true) };
    });
    const allocations = [];
    for (const bucket of balances) {
      if (bucket.balanceVnd <= 0n || remaining === 0n) continue;
      const amountVnd = remaining < bucket.balanceVnd ? remaining : bucket.balanceVnd;
      allocations.push({ key: bucket.key, kind: bucket.kind, amountVnd });
      remaining -= amountVnd;
    }
    return { allocations, overpaymentVnd: remaining };
  }

  function ledgerBalance({ closedVnd, openVnd, receipts, buckets }) {
    const closed = vnd(closedVnd);
    const open = vnd(openVnd);
    let receivedVnd = 0n;
    for (const receipt of receipts) {
      if (receipt.receivedOn === null) continue;
      if (typeof receipt.receivedOn !== "string" || !receipt.receivedOn.trim()) {
        throw new Error("Missing receivedOn; use null for an unconfirmed receipt");
      }
      receivedVnd += vnd(receipt.amountVnd);
    }
    // Same ordered buckets for all receipts; aggregation does not rewrite history.
    const { allocations, overpaymentVnd } = allocateReceipt(receivedVnd, buckets);
    const balances = { closed: 0n, open: 0n };
    for (const bucket of buckets) {
      const balance = vnd(bucket.balanceVnd, true);
      if (balance > 0n) balances[bucket.kind] += balance;
    }
    if (balances.closed !== closed || balances.open !== open) {
      throw new Error("Bucket balances do not match closedVnd/openVnd");
    }
    for (const allocation of allocations) balances[allocation.kind] -= allocation.amountVnd;
    return {
      closedRemainingVnd: balances.closed,
      openRemainingVnd: balances.open,
      overpaymentVnd,
      receivedVnd,
      endOfMonthVnd: balances.closed - overpaymentVnd,
    };
  }

  function canClose({ lines, enteredBy, closedBy }) {
    if (typeof enteredBy !== "string" || !enteredBy.trim() ||
        typeof closedBy !== "string" || !closedBy.trim()) throw new Error("Missing actor");
    const reasons = [];
    if (closedBy === enteredBy) reasons.push("Người nhập không được tự chốt.");
    const { missingPriceIds } = monthTotals(lines);
    if (missingPriceIds.length) reasons.push(`Chưa có giá: ${missingPriceIds.join(", ")}.`);
    return { ok: reasons.length === 0, reasons };
  }

  return { lineAmount, monthTotals, allocateReceipt, ledgerBalance, canClose };
})();
if (typeof module !== "undefined") module.exports = LedgerV5Model;
