/* Bảng đối chiếu (VIEC-DOI-CHIEU-01): phần tính, không đụng DOM. Tiền là chuỗi số nguyên VND, cộng bằng BigInt; chưa biết là null, không phải 0. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DoiChieuModel = api;
}(typeof self !== 'undefined' ? self : this, () => {
  const big = value => (value === null || value === undefined ? null : BigInt(value));

  const isAhead = row => row.reason === 'WEB_AHEAD' || (row.reason === 'FIXED' && row.status !== 'KHOP');
  const isDone = row => row.reason === 'FIXED' || row.reason === 'BOOK_CREATED';
  const abs = value => { const n = big(value); return n === null ? null : n < 0n ? -n : n; };

  // Khách phải xem, lệch lớn trước; máy ghi xong mà không khớp đứng đầu; chưa biết số lệch xếp sau cùng.
  function openRows(reconcile) {
    const rows = (reconcile?.customers ?? []).filter(row => !isDone(row) && !isAhead(row));
    const rank = row => (row.reason === 'VERIFY_FAILED' ? 0 : row.difference_vnd === null || row.difference_vnd === undefined ? 2 : 1);
    return [...rows].sort((a, b) => rank(a) - rank(b) || (abs(b.difference_vnd) > abs(a.difference_vnd) ? 1 : abs(b.difference_vnd) < abs(a.difference_vnd) ? -1 : 0));
  }
  const aheadRows = reconcile => (reconcile?.customers ?? []).filter(row => row.reason === 'WEB_AHEAD');
  const fixedRows = reconcile => (reconcile?.customers ?? []).filter(isDone);
  const openIds = reconcile => new Set(openRows(reconcile).map(row => row.customer_id).filter(Boolean));

  // Nợ tập trung ở vài khách lớn: đếm khách một mình dễ tưởng gần xong, nên kèm tỷ lệ theo tiền. Còn khách lệch thì chưa phải 100%.
  function share(reconcile) {
    const all = big(reconcile?.all_web_vnd ?? 0);
    if (all <= 0n) return null;
    const percent = big(reconcile.matched_web_vnd ?? 0) * 100n / all;
    return percent === 100n && (reconcile.counts?.KHOP ?? 0) < (reconcile.total ?? 0) ? 'gần 100' : percent.toString();
  }

  const vnHourMinute = ms => {
    const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(new Date(ms));
    const pick = type => Number(parts.find(part => part.type === type).value);
    return [pick('hour') % 24, pick('minute')];
  };
  // Timer chạy phút :05 mỗi giờ từ 7 tới 22 giờ VN.
  function nextCheck(now) {
    const [hour, minute] = vnHourMinute(now);
    const pad = n => String(n).padStart(2, '0');
    if (hour < 7) return '07:05';
    if (hour > 22 || (hour === 22 && minute >= 5)) return '07:05 sáng mai';
    return `${pad(minute < 5 ? hour : hour + 1)}:05`;
  }
  // Quá 3 giờ trong khung chạy là máy đã dừng; đêm thì lần cuối là 22 giờ, không tính là cũ.
  function isOld(checkedAt, now) {
    const [hour] = vnHourMinute(now);
    return hour >= 10 && hour <= 22 && now - Date.parse(checkedAt) > 3 * 3600_000;
  }

  const groupRows = (group, off) => group.rows.filter(row => !off?.has(row.key));
  function groupDelta(group, off) {
    if (group.kind !== 'prices' || !off?.size) return big(group.delta_vnd);
    return groupRows(group, off).reduce((sum, row) => sum + big(row.delta_vnd), 0n);
  }

  // Số của bảng đối chiếu theo khoản đang chọn. `off`: chuyến bỏ ra trong nhóm giá; nhóm bỏ hết chuyến coi như không chọn.
  function summarize(statement, selected = new Set(), off = new Set()) {
    const web = big(statement.web_vnd);
    const sheet = big(statement.sheet_total_vnd);
    const ahead = big(statement.web_ahead_vnd ?? 0);
    const items = [];
    let total = 0n;
    for (const group of statement.groups ?? []) {
      if (!selected.has(group.id)) continue;
      const rows = group.kind === 'prices' ? groupRows(group, off) : group.rows;
      if (!rows.length) continue;
      const delta = groupDelta(group, off);
      total += delta;
      items.push({ id: group.id, delta_vnd: delta.toString(), rows: group.kind === 'prices' && rows.length < group.rows.length ? rows.map(row => row.key) : null });
    }
    const after = web + total;
    return { web: web.toString(), after: after.toString(), total: total.toString(), sheet: sheet === null ? null : sheet.toString(),
      remaining: sheet === null ? null : (after - sheet - ahead).toString(), now: sheet === null ? null : (web - sheet - ahead).toString(), items,
      lockedMonths: (statement.groups ?? []).filter(group => group.locked && items.some(item => item.id === group.id)).map(group => group.month) };
  }

  // Chỉ khác phụ phí khi mọi dòng cùng đơn giá hai bên; web chưa có đơn giá thì là giá.
  const isFeeOnly = group => group.kind === 'prices' && group.rows.every(row => row.web_unit_price_vnd !== null && row.web_unit_price_vnd === row.sheet_unit_price_vnd);

  return { openRows, aheadRows, fixedRows, openIds, share, nextCheck, isOld, groupDelta, summarize, isFeeOnly, isAhead };
}));
