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

  // NHAP-SHEET-01: bảng nhập kiểu Sheet. Vùng dán theo bố cục tab khách (specs/v7-nhap-kieu-sheet.md):
  // container ở cột c, rồi hãng tàu, ngày, nơi đi, nơi đến, ba cột phí, đơn giá, thành tiền; từ c+10 là tiền khách trả.
  const DRAFT_FIELDS = ["container", "carrier", "shipper", "date", "from", "to", "price", "fee"];
  const containerKey = text => String(text ?? "").toUpperCase().replace(/\s+/g, "");
  const looksLikeContainer = text => /^[A-Z]{4}\d{7}$/.test(containerKey(text));
  const draftMoney = text => {
    const value = String(text ?? "").trim();
    if (!value || /[a-zà-ỹ]/i.test(value)) return { value: null };   // trống hoặc chữ ("chưa có giá") = chưa có
    try { return { value: parseVnd(value) }; } catch { return { error: "Số tiền không đọc được" }; }
  };
  function draftDate(text, todayIso) {
    const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(text ?? "").trim());
    if (!match) return { error: "Ngày cần dạng ngày/tháng/năm, ví dụ 20/10/2026" };
    const padded = `${match[1].padStart(2, "0")}/${match[2].padStart(2, "0")}/${match[3]}`;
    if (!validDate(padded)) return { error: "Ngày không có thật" };
    if (todayIso && `${match[3]}-${padded.slice(3, 5)}-${padded.slice(0, 2)}` > todayIso) return { error: "Ngày ở tương lai" };
    return { text: padded };
  }
  const blankDraft = () => ({ container: "", carrier: "", date: "", from: "", to: "", price: "", fee: "", sheetTotal: "" });

  // Chuẩn hóa hàng nháp để hiện lại: container viết hoa, ngày dd/mm/yyyy, số có dấu chấm.
  function tidyDraft(row) {
    const out = { ...row, container: containerKey(row.container) };
    const date = draftDate(row.date);
    if (date.text) out.date = date.text;
    for (const name of ["price", "fee"]) {
      const read = draftMoney(row[name]);
      if (read.value !== null && read.value !== undefined) out[name] = formatVnd(read.value);
    }
    return out;
  }

  // Đọc vùng dán thành hàng nháp. Không thấy container: trải theo thứ tự cột web từ ô đang bấm (startField), như Excel.
  function spreadPaste(text, startField = "container") {
    const lines = String(text ?? "").replace(/\r/g, "").split("\n").map(line => line.split("\t"));
    while (lines.length && lines[lines.length - 1].every(cell => !cell.trim())) lines.pop();
    const anchor = lines.map(cells => cells.slice(0, 3).findIndex(looksLikeContainer)).find(index => index >= 0);
    const rows = [];
    let skipped = 0, payments = false;
    for (const cells of lines) {
      const joined = cells.join(" ").trim();
      if (!joined || (/c[ộo]ng|t[ổo]ng/i.test(joined) && !cells.some(looksLikeContainer))) { skipped++; continue; }
      const row = blankDraft();
      if (anchor !== undefined) {
        const at = offset => (cells[anchor + offset] ?? "").trim();
        Object.assign(row, { container: at(0), carrier: at(1), date: at(2), from: at(3), to: at(4), price: at(8), sheetTotal: at(9) });
        const fees = [at(5), at(6), at(7)].filter(Boolean);
        const parsed = fees.map(draftMoney);
        row.fee = !fees.length ? "" : parsed.some(item => item.error || item.value === null) ? fees.join(" + ")
          : formatVnd(parsed.reduce((sum, item) => sum + item.value, 0n));
        if (cells.slice(anchor + 10).some(cell => cell.trim())) payments = true;
      } else {
        const from = Math.max(0, DRAFT_FIELDS.indexOf(startField));
        cells.forEach((cell, offset) => { if (DRAFT_FIELDS[from + offset]) row[DRAFT_FIELDS[from + offset]] = cell.trim(); });
      }
      rows.push(tidyDraft(row));
    }
    return { rows, skipped, payments, byColumn: anchor === undefined };
  }

  // Kiểm một hàng nháp: lỗi theo ô, thành tiền, cờ chưa có giá, cảnh báo Sheet lệch; trip là payload paste_trips khi không lỗi.
  function checkDraft(row, todayIso) {
    const errors = {};
    const labels = { container: "số container", carrier: "hãng tàu", from: "nơi đi", to: "nơi đến" };
    for (const name of ["container", "carrier", "from", "to"]) if (!String(row[name] ?? "").trim()) errors[name] = `Thiếu ${labels[name]}`;
    const date = String(row.date ?? "").trim() ? draftDate(row.date, todayIso) : { error: "Thiếu ngày chuyến" };
    if (date.error) errors.date = date.error;
    const price = draftMoney(row.price), fee = draftMoney(row.fee);
    if (price.error) errors.price = price.error;
    if (fee.error) errors.fee = fee.error;
    const missing = !price.error && price.value === null;
    const amountVnd = price.value === null || price.value === undefined || fee.error ? null : price.value + (fee.value ?? 0n);
    const sheet = draftMoney(row.sheetTotal);
    const warn = amountVnd !== null && sheet.value !== undefined && sheet.value !== null && sheet.value !== amountVnd
      ? `Sheet ghi ${formatVnd(sheet.value)}` : "";
    const trip = Object.keys(errors).length ? null : {
      container: containerKey(row.container), carrier: row.carrier.trim(), date: date.text, from: row.from.trim(), to: row.to.trim(),
      unitPriceVnd: missing ? null : price.value.toString(), otherFeeVnd: fee.value === null ? null : fee.value.toString(), note: "", src: "" };
    if (trip && String(row.shipper ?? '').trim()) trip.shipper = String(row.shipper).trim();
    return { errors, amountVnd, missing, warn, trip };
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
  const CELL_FIELDS = ["container", "carrier", "event_date", "origin", "destination", "unit_price_vnd", "other_fee_vnd"];
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

  return { tripAmount, amountWith, parsePastedTrips, spreadPaste, checkDraft, tidyDraft, blankDraft, DRAFT_FIELDS, tripKey, sameTrip, classifyPastedTrips, parseVnd, parsePositiveVnd, formatVnd, formatOutstanding, monthChain, outstandingByMonth, planReceipt, planReallocation,
    nextReceiptPid, receiptNotice, receiptDetails, voidedLines, planVoid, planReceiptEdit, planAdjustment, planMonthAdjustment,
    parseSignedVnd, adjustmentAmount, isMonthOpen, pendingCounts, parseCellEdit, sumAdjustments,
    OFFSET_OUTSIDE, parseOffsetSources, filterOffsetSources, planOffsetEntry, planOffsetPreview, offsetErrorMessage,
    sheetPriceAmount, sheetVnd, planSheetPrices, feeCells, feeColumnTotals, parseFeeInput, feeTotalAfter, recountPreview,
    parseOffsetResult, parseOffsetLink, parseOutgoingOffsets };
})();
if (typeof module !== "undefined") module.exports = SoKhachV7Model;
