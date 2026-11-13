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
    return { amountVnd: isMissingPrice || trip.status === "pending_review" ? null : (price ?? 0n) + (fee ?? 0n), isFeeOnly, isMissingPrice };
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

  // Same Unicode White_Space set and ALT key as sokhach._normalize_key/_booking_key.
  function normalizeTripKey(value) {
    // eslint-disable-next-line no-control-regex -- matches SQL Unicode White_Space, including tabs/newlines.
    return (value ?? "").replace(/[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]/g, "").toUpperCase();
  }

  function tripKey(trip) {
    const container = normalizeTripKey(trip.container);
    const booking = normalizeTripKey(trip.booking);
    if (!container) return null;
    const day = validDate(trip.date) ? trip.date.slice(6) + trip.date.slice(3, 5) + trip.date.slice(0, 2) : "UNKNOWN";
    return `${/[\p{L}\p{N}]/u.test(booking) ? booking : `ALT:${container}:${day}`}|${container}`;
  }

  function sameTrip(left, right) {
    const key = tripKey(left);
    if (!key || normalizeTripKey(left.container) !== normalizeTripKey(right.container)) return false;
    if (key === tripKey(right)) return true;
    const day = trip => validDate(trip.date) ? Date.UTC(+trip.date.slice(6), +trip.date.slice(3, 5) - 1, +trip.date.slice(0, 2)) : NaN;
    return Math.abs(day(left) - day(right)) <= 3 * 86400000;
  }

  function classifyPastedTrips(trips, existing = [], references = []) {
    const seen = [];
    return trips.map(trip => {
      const reason = references.some(row => sameTrip(trip, row)) ? "BASELINE_DUPLICATE"
        : existing.some(row => sameTrip(trip, row)) ? "WEB_DUPLICATE"
        : seen.some(row => sameTrip(trip, row)) ? "BATCH_DUPLICATE" : null;
      seen.push(trip);
      return { ...trip, trip_key: tripKey(trip), status: reason ? "pending_review" : "confirmed", reviewReason: reason };
    });
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
        if (result.amountVnd !== null) chargesVnd += result.amountVnd;
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

  // NHAP-SHEET-01: one typed cell → the string the server takes. Throws a Vietnamese message.
  // Dates accept d/m/yyyy like the Sheet; money "" means unknown (NULL), never 0.
  // Blank text goes to the server as-is: only it knows whether the row needs the cell (fee-only rows do not).
  const CELL_FIELDS = ["container", "carrier", "shipper", "event_date", "origin", "destination", "unit_price_vnd", "other_fee_vnd"];
  function parseCellEdit(field, text, todayIso) {
    if (!CELL_FIELDS.includes(field)) throw new Error("Ô không được sửa.");
    const value = String(text ?? "").trim();
    if (field === "event_date") {
      const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(value);
      const padded = match ? `${match[1].padStart(2, "0")}/${match[2].padStart(2, "0")}/${match[3]}` : "";
      if (!validDate(padded)) throw new Error("Ngày phải dạng dd/mm/yyyy.");
      const iso = `${match[3]}-${padded.slice(3, 5)}-${padded.slice(0, 2)}`;
      if (todayIso && iso > todayIso) throw new Error("Ngày không được sau hôm nay.");
      return iso;
    }
    if (field === "unit_price_vnd" || field === "other_fee_vnd") {
      if (!value) return "";
      try { return parseVnd(value).toString(); } catch { throw new Error("Số tiền không hợp lệ."); }
    }
    return field === "container" ? value.replace(/\s+/g, "").toUpperCase() : value;
  }

  // Total of server adjustment rows (digit strings, signed) shown as one line per month; null when none.
  function sumAdjustments(rows) {
    if (!rows.length) return null;
    return rows.reduce((sum, row) => sum + vnd(row.amount_vnd, true), 0n);
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
        receipt = { pid: item.pid, date: item.date, method: item.kind === "advance" ? item.receiptMethod ?? item.method : item.method, reference: item.reference ?? null, totalVnd: 0n, oldKeys: new Set() };
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
        lines.push({ monthKey: debt.key, receipt: { pid: receipt.pid, reference: receipt.reference, date: receipt.date, method: receipt.method,
          amountVnd: applied.toString(), kind: "debt", voided: null } });
        newKeys.add(debt.key);
        debt.left -= applied;
        left -= applied;
      }
      if (left > 0n) {
        const key = months.at(-1).key;
        lines.push({ monthKey: key, receipt: { pid: receipt.pid, reference: receipt.reference, date: receipt.date, method: "ỨNG TRƯỚC",
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
    if (!changes || !Object.keys(changes).length || Object.keys(changes).some(key => !["date", "method", "reference"].includes(key))) throw new Error("Invalid receipt edit");
    if (changes.reference != null && (typeof changes.reference !== "string" || changes.reference.length > 500)) throw new Error("Invalid reference");
    const draft = structuredClone(book);
    const lines = [];
    for (const month of monthsOf(draft)) month.receipts.forEach((receipt, index) => {
      if (receipt.pid !== pid) return;
      if (receipt.voided !== null) throw new Error("Receipt already voided");
      const updated = { ...receipt, reference: changes.reference == null ? receipt.reference ?? null : changes.reference.trim() || null, date: changes.date ?? receipt.date,
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

  /* Trang khách, thẻ Tình hình (TRANG-KHACH-01, khối 2 "Nợ đang tăng hay giảm?"): `count` tháng tới tháng `today` từ months[]
     của GET /api/v7/ledger, số lấy nguyên từ GET (dòng Tổng tháng, DA-THU-01). Tháng không có trong months[] không có cột
     (null, không phải 0); điểm Còn nợ cuối tháng giữ số của tháng gần nhất trước đó, kể cả tháng trước cửa sổ (`carried`);
     sổ chưa có tháng nào trước đó thì không có điểm. `*At` là vị trí để vẽ (0 = đáy, 1 = đỉnh) trên một thang từ số nhỏ nhất
     (≤ 0) tới số lớn nhất (≥ 0), `zeroAt` là vị trí số 0; `low`/`last` là chỉ số điểm thấp nhất (lần đầu) và điểm cuối. */
  function monthSeries(months, today, count = 12) {
    const keyOf = value => String(value ?? "").slice(0, 7);
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(keyOf(today))) throw new Error("Invalid month");
    const shift = (key, by) => {
      const n = Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1 + by;
      return `${Math.floor(n / 12)}-${String(n % 12 + 1).padStart(2, "0")}`;
    };
    const money = value => value === null || value === undefined ? null : vnd(String(value), true);
    const rows = new Map((Array.isArray(months) ? months : []).map(row => [keyOf(row.month), row]));
    const first = shift(keyOf(today), 1 - count);
    let carry = null;
    for (const key of [...rows.keys()].sort()) {
      if (key < first && money(rows.get(key).end_of_month_vnd) !== null) carry = money(rows.get(key).end_of_month_vnd);
    }
    const items = Array.from({ length: count }, (_, index) => {
      const key = shift(first, index), row = rows.get(key), own = row ? money(row.end_of_month_vnd) : null;
      if (own !== null) carry = own;
      return { key, present: row !== undefined, chargesVnd: row ? money(row.charges_vnd) : null,
        receivedVnd: row ? money(row.received_vnd) : null, endVnd: carry, carried: own === null && carry !== null };
    });
    const values = items.flatMap(item => [item.chargesVnd, item.receivedVnd, item.endVnd]).filter(value => value !== null);
    const bottom = values.reduce((min, value) => value < min ? value : min, 0n);
    const top = values.reduce((max, value) => value > max ? value : max, 0n);
    const at = value => value === null ? null : top === bottom ? 0 : Number((value - bottom) * 10000n / (top - bottom)) / 10000;
    for (const item of items) Object.assign(item, { chargesAt: at(item.chargesVnd), receivedAt: at(item.receivedVnd), endAt: at(item.endVnd) });
    const points = items.map((item, index) => [item.endVnd, index]).filter(([value]) => value !== null);
    return { items, zeroAt: at(0n), low: points.length ? points.reduce((best, point) => point[0] < best[0] ? point : best)[1] : null,
      last: points.length ? points.at(-1)[1] : null };
  }

  // Khách đang dư (tổng còn nợ âm, CAN-DU-01): số trả trước, dương; không dư thì 0.
  function creditOf(total) {
    const amount = vnd(String(total), true);
    return amount < 0n ? -amount : 0n;
  }

  /* Cấn trừ hai sổ (CT-2SO). Số tiền do server trả (chuỗi nguyên) đọc bằng vnd(); số gõ tay đọc bằng parsePositiveVnd.
     Hàm ở đây chỉ đọc/kiểm hợp đồng JSON và dựng dữ liệu hiển thị; server mới là nơi chặn và ghi. */
  const OFFSET_OUTSIDE = "OUTSIDE";
  const OFFSET_MESSAGES = {
    SOURCE_REQUIRED: "Chọn sổ lấy tiền, hoặc chọn Ngoài sổ",
    INVALID_VND: "Số tiền không hợp lệ",
    OFFSET_SAME_BOOK: "Không cấn trừ trong cùng một sổ",
    FUTURE_DATE: "Ngày trả không được sau hôm nay",
    INVALID_DATE: "Ngày trả không hợp lệ",
    STALE_LEDGER: "Số dư đã đổi, tải lại số rồi xác nhận lại",
    NO_BASELINE: "Sổ chưa có số dư mở đầu",
    OFFSET_SOURCE_ARCHIVED: "Sổ lấy tiền đã lưu trữ",
    OFFSET_NOT_FOUND: "Không tìm thấy cặp cấn trừ",
    OFFSET_ALREADY_VOID: "Cặp cấn trừ này đã hủy",
    VOID_REASON_REQUIRED: "Nhập lý do hủy",
    OFFSET_PAIR_REQUIRED: "Phiếu này thuộc cặp cấn trừ, hủy hoặc đổi ngày ở cả cặp",
    IDEMPOTENCY_CONFLICT: "Lệnh trùng khóa nhưng khác nội dung",
    NO_CHANGE: "Không có gì thay đổi",
  };

  function idText(value) {
    if (typeof value === "number" && Number.isSafeInteger(value) && value > 0) return String(value);
    if (typeof value === "string" && /^[1-9]\d*$/.test(value)) return value;
    throw new Error("Invalid id");
  }

  function parseOffsetSources(list) {
    if (!Array.isArray(list)) throw new Error("Invalid offset sources");
    return list.map(item => {
      const outstandingVnd = vnd(item.outstanding_vnd, true);
      const availableCreditVnd = vnd(item.available_credit_vnd);
      if (outstandingVnd >= 0n || availableCreditVnd !== -outstandingVnd) throw new Error("Invalid offset source");
      if (typeof item.name !== "string" || !item.name.trim()) throw new Error("Invalid offset source");
      const commodity = typeof item.commodity === "string" && item.commodity.trim() ? item.commodity.trim() : null;
      return { customerId: idText(item.customer_id), name: item.name.trim(), commodity, version: idText(item.version),
        outstandingVnd, availableCreditVnd, label: commodity ? `${item.name.trim()} · ${commodity}` : item.name.trim() };
    });
  }

  function filterOffsetSources(sources, query) {
    const norm = text => String(text).normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
    const needle = norm(query ?? "").trim();
    return sources.filter(source => norm(source.label).includes(needle));
  }

  function planOffsetEntry({ source, amountText }) {
    if (source === null || source === undefined) return { ok: false, code: "SOURCE_REQUIRED", message: OFFSET_MESSAGES.SOURCE_REQUIRED };
    let amountVnd;
    try { amountVnd = parsePositiveVnd(amountText); }
    catch { return { ok: false, code: "INVALID_VND", message: OFFSET_MESSAGES.INVALID_VND }; }
    if (source === OFFSET_OUTSIDE) return { ok: true, outside: true, amountVnd };
    if (amountVnd > source.availableCreditVnd) {
      return { ok: false, code: "OFFSET_EXCEEDS_CREDIT", amountVnd,
        message: `Sổ ${source.label} chỉ còn dư ${formatVnd(source.availableCreditVnd)}` };
    }
    return { ok: true, outside: false, amountVnd };
  }

  /* Chỉ để hiện khung xác nhận; server kiểm lại dưới khóa với version đã xem. */
  function planOffsetPreview({ source, targetOutstandingVnd, amountVnd }) {
    if (typeof targetOutstandingVnd !== "bigint" || typeof amountVnd !== "bigint" || amountVnd <= 0n) throw new Error("Invalid offset preview");
    const targetAfterVnd = targetOutstandingVnd - amountVnd;
    return {
      source: { beforeVnd: source.outstandingVnd, afterVnd: source.outstandingVnd + amountVnd },
      target: { beforeVnd: targetOutstandingVnd, afterVnd: targetAfterVnd },
      targetNegativeVnd: targetAfterVnd < 0n ? targetAfterVnd : null,
    };
  }

  // Bước xem lại bảng giá (BANG-GIA-05): giá một ô trước → sau, chỉ để hiển thị. Thiếu một bên (NULL ≠ 0) thì không có mức đổi.
  function priceTableChange(beforeVnd, afterVnd) {
    if (beforeVnd == null || afterVnd == null) return null;
    return vnd(afterVnd) - vnd(beforeVnd);
  }

  // Ghi giá từ Sheet (specs/v7-price-queue.md): tiền là chuỗi số nguyên từ server; phụ phí null = 0 khi có đơn giá (V7-BE).
  function sheetPriceAmount(item) {
    return vnd(item.sheet_unit_price_vnd) + (item.sheet_other_fee_vnd == null ? 0n : vnd(item.sheet_other_fee_vnd));
  }

  // Giá Sheet ở mục "Cần xem" có thể âm (giảm trừ): đọc có dấu, chỉ để hiển thị.
  function sheetVnd(value) {
    return value == null ? null : vnd(value, true);
  }

  function planSheetPrices(ready, totalOutstandingVnd) {
    const increaseVnd = ready.reduce((sum, item) => sum + sheetPriceAmount(item), 0n);
    const beforeVnd = vnd(totalOutstandingVnd, true);   // khách đang dư thì tổng còn nợ âm
    return { count: ready.length, increaseVnd, beforeVnd, afterVnd: beforeVnd + increaseVnd };
  }

  function planSheetPriceConflicts(items, totalOutstandingVnd) {
    const beforeVnd = vnd(totalOutstandingVnd, true);
    const deltaVnd = items.reduce((sum, item) => {
      const oldAmount = item.target_kind === 'legacy' ? vnd(item.web_total_vnd, true)
        : vnd(item.web_unit_price_vnd, true) + (item.web_other_fee_vnd == null ? 0n : vnd(item.web_other_fee_vnd, true));
      const newAmount = vnd(item.sheet_unit_price_vnd, true)
        + (item.sheet_other_fee_vnd == null ? 0n : vnd(item.sheet_other_fee_vnd, true));
      return sum + newAmount - oldAmount;
    }, 0n);
    return { beforeVnd, afterVnd: beforeVnd + deltaVnd, deltaVnd };
  }

  // Ghi phiếu thu từ Sheet (specs/v7-receipt-queue.md): tiền là chuỗi số nguyên dương từ server.
  function planSheetReceipts(ready, totalOutstandingVnd) {
    const totalVnd = ready.reduce((sum, item) => sum + vnd(item.amount_vnd), 0n);
    const beforeVnd = vnd(totalOutstandingVnd, true);
    return { count: ready.length, totalVnd, beforeVnd, afterVnd: beforeVnd - totalVnd };
  }

  // Bước xem lại trước khi ghi một phiếu thu tay (SO-GON-04 H5): tổng còn nợ trước → sau; sau âm là khách dư (creditVnd).
  // Phần trừ nợ từng tháng do server quyết định (record_receipt rồi phân bổ lại mọi phiếu), trang không tính trước.
  function planReceiptPreview(totalOutstandingVnd, amountVnd) {
    const beforeVnd = vnd(totalOutstandingVnd, true);
    const afterVnd = beforeVnd - vnd(amountVnd);
    return { beforeVnd, afterVnd, creditVnd: afterVnd < 0n ? -afterVnd : 0n };
  }

  function offsetErrorMessage(code, detail) {
    if (code === "OFFSET_EXCEEDS_CREDIT") {
      const credit = detail && typeof detail.available_credit_vnd === "string" ? vnd(detail.available_credit_vnd) : null;
      return credit === null ? "Sổ lấy tiền không đủ dư" : `Sổ lấy tiền chỉ còn dư ${formatVnd(credit)}`;
    }
    return OFFSET_MESSAGES[code] ?? "Không ghi được cấn trừ";
  }

  function parseOffsetResult(result) {
    if (!result || typeof result !== "object") throw new Error("Invalid offset result");
    const receipt = result.target_receipt ?? {};
    return { pairId: idText(result.offset_pair_id), sourceCustomerId: idText(result.source_customer_id),
      targetCustomerId: idText(result.target_customer_id), sourceVersion: idText(result.source_version),
      targetVersion: idText(result.target_version), sourcePid: String(result.source_pid), targetPid: String(result.target_pid),
      overpaymentVnd: receipt.overpayment_vnd === undefined ? 0n : vnd(receipt.overpayment_vnd) };
  }

  function parseOffsetLink(receipt) {
    if (receipt.offset_pair_id === null || receipt.offset_pair_id === undefined) return null;
    return { pairId: idText(receipt.offset_pair_id), counterpartyCustomerId: idText(receipt.counterparty_customer_id),
      counterpartyName: String(receipt.counterparty_name) };
  }

  // PHU-PHI-01: cụm cột phụ phí của một chuyến/dòng sổ gốc, từ fee_lines của server (chỉ để hiện).
  // own[i] = tổng các khoản của cột riêng thứ i (null khi không có khoản); other = các khoản còn lại (cột Khác).
  const feeSum = lines => lines.length ? lines.reduce((sum, line) => sum + vnd(String(line.amount_vnd), true), 0n) : null;
  function feeCells(lines, columnIds) {
    const list = Array.isArray(lines) ? lines : [];
    const ids = columnIds.map(Number);
    const other = list.filter(line => !ids.includes(Number(line.fee_type_id)));
    return { own: ids.map(id => feeSum(list.filter(line => Number(line.fee_type_id) === id))),
      otherVnd: feeSum(other), otherCount: other.length, totalVnd: feeSum(list) };
  }
  // Dòng Tổng tháng: tổng từng cột phụ phí của mọi chuyến trong tháng (null khi cột trống cả tháng).
  function feeColumnTotals(lineLists, columnIds) {
    const cells = lineLists.map(lines => feeCells(lines, columnIds));
    const total = pick => { const values = cells.map(pick).filter(value => value !== null);
      return values.length ? values.reduce((sum, value) => sum + value, 0n) : null; };
    return { own: columnIds.map((_, index) => total(cell => cell.own[index])), otherVnd: total(cell => cell.otherVnd) };
  }
  // Tổng cột đơn giá đã biết; không tính chuyến chờ kiểm, đã loại hoặc đã xóa. Trống cả cột vẫn là null.
  function unitPriceTotal(trips, legacyRows) {
    const prices = [...trips.filter(row => row.status === 'confirmed' && !row.deleted).map(row => row.unit_price_vnd),
      ...legacyRows.filter(row => row.kind === 'trip' && !row.current?.deleted).map(row =>
        row.editable && row.current ? row.current.unit_price_vnd
          : /^-?\d+$/.test(row.display?.unit_price ?? '') ? row.display.unit_price : null)]
      .filter(value => value != null && value !== '');
    return prices.length ? prices.reduce((sum, value) => sum + vnd(String(value), true), 0n) : null;
  }
  // Tách phụ phí theo bảng PS (specs/v7-phu-phi-tu-ps.md): chỉ đổi loại. Trang chỉ ghi "Tổng tiền không đổi"
  // khi mọi chuyến có tổng trước = sau; lệch một chuyến thì same = false và không cho tách.
  function planPsFees(ready) {
    const list = Array.isArray(ready) ? ready : [];
    let totalVnd = 0n;
    let fills = 0;
    for (const item of list) {
      const before = feeSum(item.before ?? []);
      const after = feeSum(item.after ?? []);
      // MAY-PS-01: dòng sổ gốc chỉ ghi đủ khoản đã tính sẵn trong TOTAL, server giữ nguyên TOTAL.
      if (item.fill === true && after !== null) { fills += 1; totalVnd += after; continue; }
      if (before === null || before !== after) return { count: list.length, totalVnd: null, same: false, fills: 0 };
      totalVnd += before;
    }
    return { count: list.length, totalVnd, same: list.length > 0, fills };
  }
  // Ô PS số lẻ (PS_BAD_AMOUNT), ví dụ =631579/2 = "315789.5": Sheet định dạng #,##0 hiện tròn 315.790 nên chỉ số thô thì
  // người dùng không tìm được ô. Chỉ để hiện chữ; không bao giờ thành tiền (specs/v7-phu-phi-tu-ps.md: không tự làm tròn).
  function psOddText(raw) {
    const parts = /^(\d+)\.(\d+)$/.exec(String(raw ?? "").trim());
    if (!parts) return null;
    const whole = BigInt(parts[1]);
    return { exact: `${formatVnd(whole)},${parts[2]}`, shown: formatVnd(parts[2][0] >= "5" ? whole + 1n : whole) };
  }
  const feeLinesText = (lines, nameOf) => (lines ?? []).map(line => `${nameOf(line.fee_type_id)} ${formatVnd(vnd(String(line.amount_vnd), true))}`).join(" + ");
  // Số phụ phí gõ tay: trống → null (chỉ ô cột riêng: xóa trắng); khác 0; dấu theo loại (fee_type.sign).
  function parseFeeInput(text, sign, { allowBlank = false } = {}) {
    const value = String(text ?? "").trim().replace(/\s+/g, "");
    if (!value) { if (allowBlank) return null; throw new Error("Nhập số tiền khác 0"); }
    let amount;
    try { amount = value.startsWith("-") ? -parseVnd(value.slice(1)) : parseVnd(value.replace(/^\+/, "")); }
    catch { throw new Error("Số tiền không đọc được"); }
    if (amount === 0n) throw new Error("Nhập số tiền khác 0");
    if (sign === "negative" && amount > 0n) throw new Error("Giảm trừ nhập số âm");
    if (sign === "positive" && amount < 0n) throw new Error("Loại này nhập số dương — số âm chọn loại Giảm trừ");
    return amount;
  }
  // Dòng sổ gốc có Thành tiền khác đơn giá + phụ phí (counted_differs): lần sửa phí đầu tiên tính lại
  // Thành tiền = đơn giá + tổng khoản sau lệnh. change: {set:{typeId, amountVnd|null}} | {add} | {replace:{lineId,…}} | {void:{lineId}}.
  function feeTotalAfter(unitPriceVnd, lines, change) {
    let next = (Array.isArray(lines) ? lines : []).map(line => ({ id: Number(line.id), type: Number(line.fee_type_id), amount: vnd(String(line.amount_vnd), true) }));
    if (change.set) {
      next = next.filter(line => line.type !== Number(change.set.typeId));
      if (change.set.amountVnd !== null) next.push({ type: Number(change.set.typeId), amount: change.set.amountVnd });
    }
    if (change.add) next.push({ type: Number(change.add.typeId), amount: change.add.amountVnd });
    if (change.replace) next = next.map(line => line.id === Number(change.replace.lineId) ? { ...line, amount: change.replace.amountVnd } : line);
    if (change.void) next = next.filter(line => line.id !== Number(change.void.lineId));
    return vnd(String(unitPriceVnd)) + next.reduce((sum, line) => sum + line.amount, 0n);
  }
  // Hộp hỏi lại: Thành tiền trước → sau và phần chênh, khi lần sửa phí đầu tiên tính lại dòng sổ gốc.
  function recountPreview(countedVnd, unitPriceVnd, lines, change) {
    const beforeVnd = vnd(String(countedVnd), true);
    const afterVnd = feeTotalAfter(unitPriceVnd, lines, change);
    return { beforeVnd, afterVnd, deltaVnd: afterVnd - beforeVnd };
  }

  // DEBIT-NOTE-01 + DEBIT-NOTE-02 (mẫu Debit Note v3 sếp duyệt 30/10/2026, specs/v7-debit-note.md): chứng từ của một
  // tháng công nợ — chỉ các chuyến của tháng. Mọi con số trên chứng từ tính ở đây từ dòng chi tiết, không nhập tay.
  // Danh mục loại phí in trên chứng từ, đúng thứ tự cột. Tám loại đầu theo đặc tả v3; bốn loại sau là loại phụ phí sổ web
  // đang có mà danh mục v3 chưa có, chỉ thành cột khi phát sinh (CÒN MỞ: sếp gán vào tám loại hay giữ).
  const DN_FEES = [
    { code: "LUMP_SUM", en: "UNIT PRICE", cn: "单价" }, { code: "STORAGE", en: "STORAGE", cn: "早装产生费用" },
    { code: "TRUCKING", en: "TRUCKING", cn: "拼柜" }, { code: "GENSET", en: "GENERATOR / ELECTRICITY FEE", cn: "发电机/电费" },
    { code: "OVERSTAY", en: "OVERSTAY", cn: "押车" }, { code: "HC_FEE", en: "HC FEE", cn: "卫生证" },
    { code: "CANCELLATION", en: "CANCELLATION FEE", cn: "取消订柜费" }, { code: "AMENDMENT", en: "AMD FEE", cn: "改单费" },
    { code: "INSURANCE", en: "INSURANCE", cn: "保险", extra: true }, { code: "INSPECTION", en: "INSPECTION (O+CD+VS)", cn: "检验费", extra: true },
    { code: "OTHER", en: "OTHER FEES", cn: "其他费用", extra: true }, { code: "DISCOUNT", en: "DISCOUNT", cn: "折扣", extra: true },
  ];
  const dnFold = text => String(text ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[đĐ]/g, "d").toLowerCase().replace(/[^a-z0-9]/g, "");
  // Tên loại phụ phí trên sổ web → mã loại phí trên chứng từ. Neo = 押车 (OVERSTAY), Điện = GENSET, Ghép = 拼柜 (TRUCKING).
  const FEE_RULES = [[/^(neo|overstay|epxe)/, "OVERSTAY"], [/^(dien|phidien|genset|generator|electric)/, "GENSET"],
    [/^(ghep|dongghep|trucking)/, "TRUCKING"], [/^(health|hc|vesinh)/, "HC_FEE"], [/^(storage|luukho|luubai|dongsom)/, "STORAGE"],
    [/^(huy|phihuy|cancel)/, "CANCELLATION"], [/^(amd|amend|suabill|suadon|doibill)/, "AMENDMENT"], [/^(baohiem|insurance)/, "INSURANCE"],
    [/^(kiemdinh|inspection)/, "INSPECTION"], [/^(giamtru|discount)/, "DISCOUNT"]];
  const dnFeeCode = name => FEE_RULES.find(([pattern]) => pattern.test(dnFold(name)))?.[1] ?? "OTHER";

  // Số container theo ISO 6346: 3 chữ chủ, 1 chữ loại (U/J/Z/R), 6 số, 1 chữ số kiểm tra.
  function containerCheck(value) {
    const id = String(value ?? "").toUpperCase().replace(/\s+/g, "");
    if (!/^[A-Z]{3}[UJZR]\d{7}$/.test(id)) return { id, valid: false, reason: "format" };
    let sum = 0;
    for (let index = 0; index < 10; index++) {
      let value = index < 4 ? id.charCodeAt(index) - 55 : Number(id[index]);
      if (index < 4) value += Math.floor((value - 1) / 10);   // bảng chữ ISO bỏ 11, 22, 33
      sum += value * 2 ** index;
    }
    const expected = sum % 11 % 10;
    return { id, valid: expected === Number(id[10]), reason: expected === Number(id[10]) ? null : "check", expected };
  }

  // Số tiền bằng chữ tiếng Anh: SAY VIETNAM DONG … ONLY; nhóm tỷ/triệu/nghìn, 21–99 có gạch nối, không dùng AND.
  const WORD_ONES = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE",
    "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"];
  const WORD_TENS = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"];
  function wordsBelowThousand(number) {
    const parts = [];
    if (number >= 100) parts.push(WORD_ONES[Math.floor(number / 100)], "HUNDRED");
    const rest = number % 100;
    if (rest >= 20) parts.push(WORD_TENS[Math.floor(rest / 10)] + (rest % 10 ? `-${WORD_ONES[rest % 10]}` : ""));
    else if (rest > 0) parts.push(WORD_ONES[rest]);
    return parts.join(" ");
  }
  function vndInWords(amountVnd) {
    if (typeof amountVnd !== "bigint" || amountVnd < 0n || amountVnd >= 10n ** 15n) return null;
    if (amountVnd === 0n) return "SAY VIETNAM DONG ZERO ONLY";
    const parts = [];
    let rest = amountVnd;
    for (const [size, label] of [[10n ** 12n, "TRILLION"], [10n ** 9n, "BILLION"], [10n ** 6n, "MILLION"], [1000n, "THOUSAND"], [1n, ""]]) {
      const group = rest / size;
      rest %= size;
      if (group > 0n) parts.push(wordsBelowThousand(Number(group)), label);
    }
    return `SAY VIETNAM DONG ${parts.filter(Boolean).join(" ")} ONLY`;
  }

  // Tỷ giá VND/USD: số nguyên dương, cho phép dấu phẩy ngăn nghìn.
  function parseRate(text) {
    const value = String(text ?? "").trim();
    if (!/^(\d{1,3}(,\d{3})+|\d+)$/.test(value)) return null;
    const rate = BigInt(value.replace(/,/g, ""));
    return rate > 0n ? rate : null;
  }
  // Quy đổi một lần trên tổng: tổng VND ÷ tỷ giá, làm tròn nửa lên 2 số lẻ. Trả về số cent (BigInt).
  function usdCents(totalVnd, rate) {
    if (typeof totalVnd !== "bigint" || typeof rate !== "bigint" || rate <= 0n || totalVnd < 0n) return null;
    return (totalVnd * 200n + rate) / (2n * rate);
  }
  const usdText = cents => typeof cents !== "bigint" ? "" : `${(cents / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${String(cents % 100n).padStart(2, "0")}`;

  // Ngày trên chứng từ: "01 Dec 2025" — tháng tiếng Anh, không theo ngôn ngữ máy.
  const DN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const isIsoDay = iso => {
    const text = String(iso ?? "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
    const date = new Date(`${text}T00:00:00Z`);
    return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === text;
  };
  const validDay = isIsoDay;
  const dnDate = iso => isIsoDay(iso) ? `${iso.slice(8, 10)} ${DN_MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}` : "";
  const dnPeriod = monthKey => `${DN_MONTHS[Number(monthKey.slice(5, 7)) - 1]} ${monthKey.slice(0, 4)}`;
  function addDays(iso, days) {
    if (!isIsoDay(iso) || !Number.isInteger(days)) return null;
    const date = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
    date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString().slice(0, 10);
  }

  // Danh mục nơi đóng hàng và cảng đến (DIA-DIEM-01): tên chuẩn chữ Latin kèm tên tiếng Trung đã đối chiếu nguồn bên Trung
  // (Bộ Thương mại TQ, Baidu Baike, chính quyền Quảng Tây). Tỉnh theo ranh giới trước 7/2025 cho khớp Sheet. Huyện chưa có
  // nguồn Trung hoặc tên Nôm hiếm (Chợ Gạo, Cái Bè) chỉ in tên tỉnh. Chuẩn chính tả: "Dak Lak", không "DAKLAK".
  const DN_PLACES = [
    { en: "Dak Lak", cn: "多乐省", aliases: ["Daklak"] }, { en: "Dak Nong", cn: "得农省", aliases: ["Daknong"] }, { en: "Gia Lai", cn: "嘉莱省" }, { en: "Kon Tum", cn: "昆嵩省", aliases: ["Kontum"] },
    { en: "Lam Dong", cn: "林同省" }, { en: "Binh Phuoc", cn: "平福省" }, { en: "Binh Duong", cn: "平阳省" }, { en: "Dong Nai", cn: "同奈省" },
    { en: "Tay Ninh", cn: "西宁省" }, { en: "Ho Chi Minh", cn: "胡志明市", aliases: ["TP HCM", "HCM"] }, { en: "Long An", cn: "隆安省" },
    { en: "Tien Giang", cn: "前江省" }, { en: "Ben Tre", cn: "槟椥省" }, { en: "Vinh Long", cn: "永隆省" }, { en: "Tra Vinh", cn: "茶荣省" },
    { en: "Dong Thap", cn: "同塔省" }, { en: "An Giang", cn: "安江省" }, { en: "Can Tho", cn: "芹苴市" }, { en: "Hau Giang", cn: "后江省" },
    { en: "Soc Trang", cn: "朔庄省" }, { en: "Kien Giang", cn: "坚江省" }, { en: "Bac Lieu", cn: "薄辽省" }, { en: "Ca Mau", cn: "金瓯省" },
    { en: "Khanh Hoa", cn: "庆和省" }, { en: "Phu Yen", cn: "富安省" }, { en: "Binh Dinh", cn: "平定省" }, { en: "Quang Nam", cn: "广南省" },
    { en: "Quang Ngai", cn: "广义省" }, { en: "Binh Thuan", cn: "平顺省" }, { en: "Ninh Thuan", cn: "宁顺省" },
    { en: "Ba Ria - Vung Tau", cn: "巴地头顿省", aliases: ["Vung Tau", "V Tau"] },
    { en: "Phan Thiet", cn: "平顺省潘切市" }, { en: "Tanh Linh", cn: "平顺省性灵县" }, { en: "Bac Binh", cn: "平顺省北平县" },
    { en: "Trang Bom", cn: "同奈省壮奔县", aliases: ["Bau Ham"] }, { en: "Dinh Quan", cn: "同奈省定贯县", aliases: ["D Quan"] }, { en: "Tan Phu", cn: "同奈省新富县" },
    { en: "Cam My", cn: "同奈省锦美县" }, { en: "Long Thanh", cn: "同奈省隆城县" }, { en: "Long Khanh", cn: "同奈省隆庆市" },
    { en: "Dong Xoai", cn: "平福省同帅市" }, { en: "Hon Quan", cn: "平福省" }, { en: "Tan Uyen", cn: "平阳省新渊市" },
    { en: "Phu Giao", cn: "平阳省富教县" }, { en: "Dau Tieng", cn: "平阳省油汀县" }, { en: "Cu Chi", cn: "胡志明市古芝县" },
    { en: "Hoc Mon", cn: "胡志明市福门县" }, { en: "Chau Duc", cn: "巴地头顿省周德县" }, { en: "Bao Loc", cn: "林同省保禄市" },
    { en: "Buon Ho", cn: "多乐省" }, { en: "Krong Pac", cn: "多乐省克容帕县", aliases: ["Krong Pak"] }, { en: "Tan An", cn: "隆安省新安市" }, { en: "Tam Vu", cn: "隆安省" },
    { en: "Cao Lanh", cn: "同塔省" }, { en: "Tan Chau", cn: "西宁省" }, { en: "Cho Gao", cn: "前江省" }, { en: "Cai Be", cn: "前江省" },
  ];
  // Viết tắt tỉnh/huyện ở cuối tên kho trên Sheet ("KIM CƯƠNG TB"). BT bỏ ngoài vì vừa là Bến Tre vừa là Bình Thuận.
  const DN_PLACE_ABBR = { tb: "Trang Bom", dq: "Dinh Quan", bp: "Binh Phuoc", vt: "Ba Ria - Vung Tau", tg: "Tien Giang", pt: "Phan Thiet",
    bd: "Binh Duong", dn: "Dong Nai", tn: "Tay Ninh", la: "Long An", dt: "Dong Thap" };
  // Cảng đến của chuyến cảng và cửa khẩu của chuyến bộ. Cửa khẩu in theo cặp tên Trung "bên Trung—bên Việt" như văn bản bên Trung.
  const DN_PORTS = [
    { en: "Shanghai", cn: "上海港" }, { en: "Shekou", cn: "深圳蛇口港" }, { en: "Zhapu", cn: "嘉兴乍浦港" }, { en: "Qingdao", cn: "青岛港" },
    { en: "Dalian", cn: "大连港" }, { en: "Xiamen", cn: "厦门港" }, { en: "Hong Kong", cn: "香港" },
    { en: "Kaohsiung", cn: "高雄港", aliases: ["Kaohsiung - Taiwan"] }, { en: "Tianjin", cn: "天津港" }, { en: "Nansha", cn: "广州南沙港" },
    { en: "Port Klang", cn: "巴生港" }, { en: "Port Klang North Port", cn: "巴生北港", aliases: ["N-Port Klang"] },
    { en: "Port Klang Westport", cn: "巴生西港", aliases: ["W-Port Klang"] }, { en: "Singapore", cn: "新加坡港" }, { en: "Qinzhou", cn: "钦州港" },
    { en: "Ningbo", cn: "宁波港" }, { en: "Qinhuangdao", cn: "秦皇岛港" }, { en: "Lianyungang", cn: "连云港" }, { en: "Taicang", cn: "太仓港" },
    { en: "Humen", cn: "东莞虎门港" }, { en: "Shenzhen", cn: "深圳港" }, { en: "Yantian", cn: "深圳盐田港" }, { en: "Guangzhou", cn: "广州港" },
    { en: "Huangpu", cn: "广州黄埔港" }, { en: "Fangcheng", cn: "防城港" }, { en: "Haikou", cn: "海口港" },
    { en: "Pingxiang", cn: "凭祥" }, { en: "Dongxing", cn: "东兴" }, { en: "Hekou", cn: "河口" },
    { en: "Lao Cai", cn: "河口—老街口岸" }, { en: "Thanh Thuy", cn: "天保—清水口岸" }, { en: "Huu Nghi", cn: "友谊关—友谊口岸" },
    { en: "Chi Ma", cn: "爱店—支码口岸" }, { en: "Ta Lung", cn: "水口—驮隆口岸" }, { en: "Coc Nam", cn: "弄尧—谷南口岸" },
    { en: "Mong Cai", cn: "东兴—芒街口岸", aliases: ["Mong Cai - Dong Hung"] }, { en: "Tan Thanh", cn: "浦寨—新清口岸" },
  ];
  const titleCase = text => String(text ?? "").trim().replace(/\s+/g, " ").toLowerCase().replace(/(^|[\s(\-/])([a-z])/g, (_, lead, char) => lead + char.toUpperCase());
  const dnWords = text => String(text ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[đĐ]/g, "d").toLowerCase().split(/[^a-z0-9&]+/).filter(Boolean);
  const entryOf = item => typeof item === "string" ? { en: item, cn: "" } : item;
  // Tên kho có địa danh ở đầu hoặc cuối ("CỬU LONG - BẾN TRE", "KIM CƯƠNG TB") → mục danh mục của địa danh đó. Địa danh nằm giữa
  // tên ("KHO BÌNH THUẬN PHÁT") không tính: đó là tên công ty.
  function placeInside(words, entries) {
    const phrases = entries.flatMap(entry => [entry.en, ...(entry.aliases ?? [])].map(name => ({ words: dnWords(name), entry })))
      .sort((a, b) => b.words.length - a.words.length);
    const same = (list, at, words) => words.every((word, index) => list[at + index] === word);
    const core = words.slice();
    while (core.length > 1 && /^\d+$/.test(core.at(-1))) core.pop();
    const abbr = core.length > 1 ? DN_PLACE_ABBR[core.at(-1)] : undefined;
    for (const list of abbr ? [core, core.slice(0, -1)] : [core]) {
      const fits = phrase => phrase.words.length <= list.length;
      const found = [phrases.find(phrase => fits(phrase) && same(list, list.length - phrase.words.length, phrase.words)),
        phrases.find(phrase => fits(phrase) && same(list, 0, phrase.words))].filter(Boolean);
      // Có cả hai đầu ("KRÔNG PẮC-DAK LAK") thì lấy địa danh cụ thể hơn: tên Trung dài hơn là có cả huyện.
      if (found.length) return found.map(phrase => phrase.entry).sort((a, b) => b.cn.length - a.cn.length)[0];
    }
    return abbr ? entries.find(entry => entry.en === abbr) ?? null : null;
  }
  // Một tên nơi (có thể "GIA LAI + DAK LAK") → chữ chuẩn, tên tiếng Trung và cờ có trong danh mục. Ngoài danh mục thì giữ chữ
  // gốc; nếu đọc được địa danh trong tên kho thì vẫn kèm tên Trung của địa danh đó.
  function dnPlace(raw, list) {
    const entries = list.map(entryOf);
    const catalog = new Map(entries.flatMap(entry => [entry.en, ...(entry.aliases ?? [])].map(name => [dnFold(name), entry])));
    const parts = String(raw ?? "").split("+").map(part => part.trim()).filter(Boolean);
    const named = parts.map(part => catalog.get(dnFold(part)) ?? null);
    const cn = parts.map((part, index) => named[index]?.cn || (list === DN_PLACES ? placeInside(dnWords(part), entries)?.cn ?? "" : ""));
    return { text: parts.map((part, index) => named[index]?.en ?? titleCase(part)).join(" + "), cn: cn.filter(Boolean).join(" + "),
      known: parts.length > 0 && named.every(Boolean) };
  }
  // Chữ in trên chứng từ: tên chuẩn rồi tên Trung ("Shanghai  上海港").
  const dnPlaceText = place => [place.text, place.cn].filter(Boolean).join("  ");

  // Ô tiền của một dòng ở cột loại phí `code`: dòng container có LUMP-SUM và phí theo loại; dòng phí không gắn container
  // chỉ có số tiền ở đúng cột loại của nó. null = không có khoản.
  const dnCell = (code, item) => item.fees ? (code === "LUMP_SUM" ? item.lumpSumVnd : item.fees[code] ?? null) : item.code === code ? item.amountVnd : null;
  const sumOrNull = list => list.some(value => value === null) ? null : list.reduce((sum, value) => sum + value, 0n);

  function debitNote(ledger, monthKey, feeTypes = []) {
    const month = row => String(row.month ?? "").slice(0, 7);
    const names = new Map(feeTypes.map(type => [Number(type.id), type.name]));
    const money = value => value === null || value === undefined ? null : vnd(String(value), true);
    const containers = [], extras = [];
    const add = (info, lines, lumpSumVnd, sourceVnd, feeOnly) => {
      const list = Array.isArray(lines) ? lines : [];
      if (feeOnly) {   // dòng phí không gắn container (phí lẻ): mỗi khoản một dòng ADDITIONAL CHARGES
        if (list.length) for (const line of list) extras.push({ date: info.date, code: dnFeeCode(names.get(Number(line.fee_type_id))),
          note: String(line.note ?? "").trim(), amountVnd: vnd(String(line.amount_vnd), true) });
        else extras.push({ date: info.date, code: "OTHER", note: "", amountVnd: sourceVnd });
        return;
      }
      const fees = {};
      for (const line of list) {
        const code = dnFeeCode(names.get(Number(line.fee_type_id)));
        fees[code] = (fees[code] ?? 0n) + vnd(String(line.amount_vnd), true);
      }
      const feesVnd = Object.values(fees).reduce((sum, value) => sum + value, 0n);
      const amountVnd = lumpSumVnd === null ? null : lumpSumVnd + feesVnd;   // thành tiền = LUMP-SUM + phí của dòng
      containers.push({ ...info, container: containerCheck(info.container).id, place: dnPlace(info.origin, DN_PLACES),
        port: dnPlace(info.destination, DN_PORTS), lumpSumVnd, fees, feesVnd, amountVnd,
        mismatch: amountVnd !== null && sourceVnd !== null && amountVnd !== sourceVnd });
    };
    for (const row of ledger.legacy_rows ?? []) {
      if (row.kind !== "trip" || month(row) !== monthKey || row.current?.deleted) continue;
      const cur = row.editable && row.current ? row.current : null, d = row.display ?? {};
      const lumpSumVnd = cur ? money(cur.unit_price_vnd) : /^\d+$/.test(d.unit_price ?? "") ? vnd(d.unit_price) : null;
      const sourceVnd = cur ? (cur.unit_price_vnd == null && cur.counted_vnd === "0" ? null : money(cur.counted_vnd))
        : (d.flags ?? []).includes("MISSING_PRICE") ? null : money(row.source_total_vnd);
      const info = cur ? { container: cur.container, carrier: cur.carrier, shipper: cur.shipper, date: cur.event_date, origin: cur.origin, destination: cur.destination }
        : { container: d.container, carrier: d.carrier, shipper: d.shipper, date: d.date, origin: d.from, destination: d.to };
      add(info, row.fee_lines, lumpSumVnd, sourceVnd, !info.container);
    }
    let pendingCount = 0;
    for (const trip of ledger.trips ?? []) {
      if (month(trip) !== monthKey || trip.deleted) continue;
      if (trip.status !== "confirmed") { if (trip.status === "pending_review") pendingCount++; continue; }
      const info = { container: trip.container, carrier: trip.carrier, shipper: trip.shipper, date: trip.event_date, origin: trip.origin, destination: trip.destination };
      add(info, trip.fee_lines, trip.is_missing_price ? null : money(trip.unit_price_vnd), trip.is_missing_price ? null : money(trip.amount_vnd), trip.is_fee_only === true);
    }
    const day = row => validDay(row.date) ? String(row.date).slice(0, 10) : "9999";
    const byDay = list => list.map((row, index) => ({ row, index })).sort((a, b) => day(a.row).localeCompare(day(b.row)) || a.index - b.index).map(item => item.row);
    const rows = byDay(containers).map((row, index) => ({ ...row, no: index + 1 }));
    const charges = byDay(extras);
    const all = [...rows, ...charges];
    // LUMP-SUM luôn là cột; loại khác thành cột khi có ô khác 0 (kể cả dòng phí không gắn container).
    const columnTotal = code => code === "LUMP_SUM" ? sumOrNull(rows.map(row => row.lumpSumVnd))
      : sumOrNull(all.filter(item => item.fees || item.code === code).map(item => item.fees ? item.fees[code] ?? 0n : item.amountVnd));
    const used = DN_FEES.filter(fee => fee.code === "LUMP_SUM" || all.some(item => { const value = dnCell(fee.code, item); return value !== null && value !== 0n; }));
    const lumpSumVnd = columnTotal("LUMP_SUM");
    const containerFeesVnd = rows.reduce((sum, row) => sum + row.feesVnd, 0n);
    const additionalVnd = sumOrNull(charges.map(item => item.amountVnd));
    const totalVnd = sumOrNull([...rows.map(row => row.amountVnd), additionalVnd]);
    const groups = new Map();
    for (const row of rows) {
      const item = groups.get(row.port.text) ?? { port: row.port.text, portCn: row.port.cn, containers: 0, lumps: [], otherVnd: 0n };
      item.containers++; item.lumps.push(row.lumpSumVnd); item.otherVnd += row.feesVnd;
      groups.set(row.port.text, item);
    }
    const summary = [...groups.values()].map(item => ({ port: item.port, portCn: item.portCn, containers: item.containers,
      lumpSumVnd: sumOrNull(item.lumps), otherVnd: item.otherVnd }))
      .sort((a, b) => b.containers - a.containers || a.port.localeCompare(b.port));
    const otherVnd = additionalVnd === null ? null : containerFeesVnd + additionalVnd;
    const subtotalVnd = lumpSumVnd === null || otherVnd === null ? null : lumpSumVnd + otherVnd;
    const adjustmentCount = (ledger.adjustments ?? []).filter(row => month(row) === monthKey && row.legacy_row_id == null).length;
    const missingCount = rows.filter(row => row.lumpSumVnd === null).length + charges.filter(item => item.amountVnd === null).length;
    const column = fee => ({ ...fee, totalVnd: columnTotal(fee.code) });
    return { monthKey, period: dnPeriod(monthKey), rows, charges, feeColumns: used.map(column),
      excelColumns: DN_FEES.filter(fee => !fee.extra || used.includes(fee)).map(column),
      summary, additionalVnd: charges.length ? additionalVnd : null, lumpSumVnd, otherVnd, subtotalVnd, totalVnd, containerCount: rows.length,
      complete: all.length > 0 && missingCount === 0, missingCount, pendingCount, adjustmentCount,
      lastLoadingDate: rows.map(day).filter(value => value !== "9999").sort().at(-1) ?? null };
  }

  // Kiểm tra trước khi phát hành: "block" thì chỉ xuất được bản nháp; "warn" cần người lập xác nhận; "info" chỉ báo.
  const PHONE = /(^|\D)0\d{9}(?!\d)/;
  function debitNoteChecks(note, doc) {
    const out = [];
    const push = level => text => out.push({ level, text });
    const block = push("block"), warn = push("warn"), info = push("info");
    const blank = value => !String(value ?? "").trim();
    if (!note.rows.length && !note.charges.length) block("Tháng này không có chuyến nào để lập chứng từ.");
    if (note.missingCount) block(`${note.missingCount} dòng chưa có giá hoặc số tiền.`);
    const bad = note.rows.filter(row => !containerCheck(row.container).valid);
    if (bad.length) block(`Số container sai theo ISO 6346: ${bad.map(row => row.container || "(trống)").join(", ")}.`);
    const seen = new Map();
    for (const row of note.rows) if (row.container) seen.set(row.container, (seen.get(row.container) ?? 0) + 1);
    const twice = [...seen].filter(([, count]) => count > 1).map(([id]) => id);
    if (twice.length) block(`Container trùng trong chứng từ: ${twice.join(", ")}.`);
    const off = note.rows.filter(row => row.mismatch);
    if (off.length) block(`Thành tiền đơn giá + phí khác số trên sổ ở container: ${off.map(row => row.container).join(", ")}.`);
    if (note.subtotalVnd !== null && note.totalVnd !== null && note.subtotalVnd !== note.totalVnd) block("Subtotal trang 1 khác TOTAL DUE.");
    const missing = [["Số debit note", doc.number], ["Dịch vụ", doc.service], ["Tên bên phát hành", doc.issuer?.name], ["MST bên phát hành", doc.issuer?.taxId],
      ["Tên pháp lý của khách", doc.buyer?.legal], ["Địa chỉ của khách", doc.buyer?.address], ["Người nhận tiền", doc.payment?.beneficiary],
      ["Ngân hàng", doc.payment?.bank], ["Số tài khoản", doc.payment?.account], ["SWIFT", doc.payment?.swift]].filter(([, value]) => blank(value)).map(([label]) => label);
    if (missing.length) block(`Còn thiếu: ${missing.join(", ")}.`);
    if (!validDay(doc.issueDate)) block("Ngày phát hành chưa đúng.");
    if (!Number.isInteger(doc.paymentDays) || doc.paymentDays < 0 || doc.paymentDays > 365) block("Số ngày thanh toán phải là số nguyên từ 0 đến 365.");
    if (doc.usd?.on && (parseRate(doc.usd.rate) === null || blank(doc.usd.source) || !validDay(doc.usd.date))) block("Bật quy đổi USD nhưng thiếu tỷ giá, nguồn hoặc ngày lấy tỷ giá.");
    const texts = note.charges.map(item => item.note).concat(doc.extraTexts ?? []);
    if (texts.some(text => PHONE.test(String(text).replace(/(?<=\d)[ .-](?=\d)/g, "")))) block("Mô tả hoặc ghi chú có chuỗi giống số điện thoại.");
    if (!blank(doc.payment?.beneficiary) && !blank(doc.issuer?.name) && dnFold(doc.payment.beneficiary) !== dnFold(doc.issuer.name))
      warn("Chủ tài khoản nhận tiền khác bên phát hành.");
    if (validDay(doc.issueDate) && note.lastLoadingDate && doc.issueDate < note.lastLoadingDate)
      warn(`Ngày phát hành sớm hơn ngày đóng hàng cuối cùng (${dnDate(note.lastLoadingDate)}).`);
    const places = [...new Set(note.rows.filter(row => !row.place.known).map(row => row.place.text || "(trống)"))];
    const ports = [...new Set(note.rows.filter(row => !row.port.known).map(row => row.port.text || "(trống)"))];
    if (places.length) warn(`Nơi đóng hàng ngoài danh mục: ${places.join(", ")}.`);
    if (ports.length) warn(`Cảng đến ngoài danh mục: ${ports.join(", ")}.`);
    const zero = note.rows.filter(row => row.lumpSumVnd === 0n);
    if (zero.length) warn(`${zero.length} container có đơn giá bằng 0.`);
    const thin = note.rows.filter(row => blank(row.carrier) || blank(row.shipper) || !validDay(row.date));
    if (thin.length) warn(`${thin.length} container thiếu hãng tàu, shipper hoặc ngày đóng hàng.`);
    if (note.pendingCount) info(`${note.pendingCount} chuyến đang CHỜ KIỂM không lên chứng từ.`);
    if (note.adjustmentCount) info(`Tháng có ${note.adjustmentCount} dòng điều chỉnh, không lên chứng từ.`);
    return out;
  }
  // Số debit note gợi ý: <mã bên phát hành>-<yymm của kỳ>-001 (CÒN MỞ: quy tắc đánh số chính thức).
  const suggestNumber = (code, monthKey) => `${code}-${monthKey.slice(2, 4)}${monthKey.slice(5, 7)}-001`;

  function parseOutgoingOffsets(list) {
    if (!Array.isArray(list)) throw new Error("Invalid outgoing offsets");
    return list.map(item => {
      const amountVnd = vnd(item.amount_vnd, true);
      if (amountVnd >= 0n) throw new Error("Outgoing offset must be negative");
      return { pairId: idText(item.offset_pair_id), pid: String(item.pid), date: item.date, amountVnd,
        voided: item.void_reason !== null && item.void_reason !== undefined, voidReason: item.void_reason ?? null,
        counterpartyCustomerId: idText(item.counterparty_customer_id), counterpartyName: String(item.counterparty_name) };
    });
  }

  // GIA-O-01 (B): chữ dán vào ô Đơn giá (chép từ Sheet/Excel: dòng cách bằng xuống dòng, cột bằng Tab) → giá từng dòng.
  // Một cột: mỗi dòng một giá, theo thứ tự. Hai cột có số container: ghép theo container (cột nào trước cũng được).
  // Dòng trống là bỏ qua (null), không phải 0; dòng cuối trống do Sheet thêm thì bỏ. Ô không đọc được thành số tiền > 0 thì lỗi kèm số dòng.
  const PASTE_CONTAINER = /^[A-Z]{4}\d{7}$/;
  function parsePricePaste(text) {
    const lines = String(text ?? "").replace(/\r\n?/g, "\n").split("\n");
    while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
    const rows = lines.map((line, index) => {
      const cells = line.split("\t").map(cell => cell.trim());
      return { line: index + 1, cells, containerAt: cells.findIndex(cell => PASTE_CONTAINER.test(cell.replace(/\s+/g, "").toUpperCase())) };
    });
    const filled = rows.filter(row => row.cells.some(Boolean));
    const withContainer = filled.filter(row => row.containerAt >= 0).length;
    const mode = withContainer ? "container" : "order";
    const errors = [];
    if (withContainer && withContainer !== filled.length) errors.push("Có dòng có số container, có dòng không. Chép cả cột container cho mọi dòng, hoặc chỉ cột giá.");
    const out = [];
    for (const row of rows) {
      const others = row.cells.filter((cell, index) => cell && index !== row.containerAt);
      if (others.length > 1) { errors.push(`Dòng ${row.line}: có nhiều cột. Chép một cột giá, hoặc hai cột container và giá.`); continue; }
      const container = mode === "container" && row.containerAt >= 0 ? row.cells[row.containerAt].replace(/\s+/g, "").toUpperCase() : null;
      const raw = others[0] ?? "";
      if (!raw) { out.push({ line: row.line, container, priceVnd: null }); continue; }
      let value;
      try { value = parseVnd(raw.replace(/\s*(đ|₫|vnđ|vnd)$/i, "")); } catch { value = null; }
      if (value === null || value <= 0n || value > 9223372036854775807n) { errors.push(`Dòng ${row.line}: “${raw}” không đọc được thành số tiền.`); continue; }
      out.push({ line: row.line, container, priceVnd: value.toString() });
    }
    return { mode, rows: out, errors };
  }

  // Kế hoạch ghi từ chữ đã đọc. `order`: khóa dòng của bảng tháng từ dòng đang đứng trở xuống ("trip-11", "legacy-21").
  // Chỉ ghi chuyến web đã duyệt, có container, sửa được (tháng mở), chưa có giá hoặc giá khác. Dòng sổ gốc, chờ kiểm, đã loại,
  // phí lẻ, tháng khóa, container không có hoặc trùng, dòng dán thừa: nêu lý do, không ghi. Nợ trước → sau cộng đúng tiền từng
  // chuyến (đơn giá mới + phụ phí đang có, trừ Thành tiền đang tính).
  function planPricePaste(parsed, snapshot, order = []) {
    const trips = (snapshot?.trips ?? []).filter(trip => !trip.deleted);
    const legacy = (snapshot?.legacy_rows ?? []).filter(row => row.kind !== "receipt");
    const byKey = key => {
      const [kind, id] = [key.slice(0, key.indexOf("-")), key.slice(key.indexOf("-") + 1)];
      return kind === "trip" ? { kind, row: trips.find(trip => String(trip.id) === id) } : { kind, row: legacy.find(row => String(row.id) === id) };
    };
    const box = value => String(value ?? "").replace(/\s+/g, "").toUpperCase();
    const items = parsed.rows.map((pasted, index) => {
      const base = { line: pasted.line, priceVnd: pasted.priceVnd, container: pasted.container };
      if (pasted.priceVnd === null) return { ...base, status: "empty" };   // dòng trống là bỏ qua, kể cả sau chuyến cuối
      let target;
      if (parsed.mode === "container") {
        const hits = [...trips.filter(trip => box(trip.container) === pasted.container).map(row => ({ kind: "trip", row })),
          ...legacy.filter(row => box(row.current?.container ?? row.display?.container) === pasted.container).map(row => ({ kind: "legacy", row }))];
        if (hits.length !== 1) return { ...base, status: "skip", reason: hits.length ? "container có nhiều dòng trong sổ" : "không có trong sổ" };
        target = hits[0];
      } else {
        if (index >= order.length) return { ...base, status: "skip", reason: "thừa, hết chuyến trong bảng tháng" };
        target = byKey(order[index]);
      }
      const { kind, row } = target;
      const container = kind === "trip" ? row?.container : row?.current?.container ?? row?.display?.container;
      const info = { ...base, container: container || base.container, date: kind === "trip" ? row?.event_date : row?.current?.event_date };
      if (!row) return { ...info, status: "skip", reason: "không có trong sổ" };
      if (kind === "legacy") return { ...info, status: "skip", reason: "dòng sổ gốc: sửa từng ô" };
      if (row.status === "pending_review") return { ...info, status: "skip", reason: "chờ kiểm" };
      if (row.status !== "confirmed") return { ...info, status: "skip", reason: "đã loại" };
      if (row.is_fee_only || !row.container) return { ...info, status: "skip", reason: "dòng phí lẻ" };
      if (row.editable !== true) return { ...info, status: "skip", reason: "tháng khóa" };
      const oldPriceVnd = row.unit_price_vnd ?? null;
      if (oldPriceVnd === pasted.priceVnd) return { ...info, status: "same", tripId: row.id, oldPriceVnd };
      const fee = row.other_fee_vnd == null ? 0n : vnd(row.other_fee_vnd, true);
      const oldAmountVnd = oldPriceVnd === null ? 0n : vnd(row.amount_vnd ?? "0", true);
      const newAmountVnd = vnd(pasted.priceVnd) + fee;
      return { ...info, status: "write", tripId: row.id, oldPriceVnd, otherFeeVnd: row.other_fee_vnd ?? null, deltaVnd: newAmountVnd - oldAmountVnd,
        small: vnd(pasted.priceVnd) < 1000000n, overwrite: oldPriceVnd !== null };
    });
    // Hai dòng dán cùng một chuyến (ghép container), kể cả một dòng trùng giá đang có: nguồn có hai giá, không đoán dòng nào đúng, bỏ cả hai.
    const matched = items.filter(item => item.status === "write" || item.status === "same");
    const seen = new Map();
    for (const item of matched) seen.set(item.tripId, (seen.get(item.tripId) ?? 0) + 1);
    for (const item of matched) if (seen.get(item.tripId) > 1) Object.assign(item, { status: "skip", reason: "dán hai lần cho cùng chuyến" });
    const finalWrites = items.filter(item => item.status === "write");
    const beforeVnd = vnd(snapshot?.total_outstanding_vnd ?? "0", true);
    const deltaVnd = finalWrites.reduce((sum, item) => sum + item.deltaVnd, 0n);
    return { items, writes: finalWrites, beforeVnd, afterVnd: beforeVnd + deltaVnd, deltaVnd };
  }

  return { tripAmount, amountWith, parsePastedTrips, tripKey, sameTrip, classifyPastedTrips, parseVnd, parsePricePaste, planPricePaste, parsePositiveVnd, formatVnd, formatOutstanding, monthChain, outstandingByMonth, planReceipt, planReallocation,
    nextReceiptPid, receiptNotice, receiptDetails, voidedLines, planVoid, planReceiptEdit, planAdjustment, planMonthAdjustment,
    parseSignedVnd, adjustmentAmount, monthSeries, creditOf, isMonthOpen, pendingCounts, parseCellEdit, sumAdjustments,
    OFFSET_OUTSIDE, parseOffsetSources, filterOffsetSources, planOffsetEntry, planOffsetPreview, offsetErrorMessage,
    sheetPriceAmount, sheetVnd, priceTableChange, planSheetPrices, planSheetPriceConflicts, planSheetReceipts, planReceiptPreview, feeCells, feeColumnTotals, unitPriceTotal, planPsFees, psOddText, feeLinesText, parseFeeInput, feeTotalAfter, recountPreview,
    parseOffsetResult, parseOffsetLink, parseOutgoingOffsets, DN_FEES, DN_PLACES, DN_PORTS, dnFeeCode, containerCheck, vndInWords,
    parseRate, usdCents, usdText, dnDate, dnPeriod, addDays, dnPlace, dnPlaceText, dnCell, debitNote, debitNoteChecks, suggestNumber };
})();
if (typeof module !== "undefined") module.exports = SoKhachV7Model;
