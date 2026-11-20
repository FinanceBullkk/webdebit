/* Phép tính cho trang Thu chi (ZALO-THU-CHI-01 PR-2): tổng theo ngày, đếm theo bộ lọc, gom ngày, câu trạng thái đối chiếu.
   Dữ liệu là `items` của GET /api/v7/cash-chat; số tiền cộng bằng BigInt ở đây, render (thu-chi-ui.js) chỉ định dạng (ARCH-03).
   Khoản không đọc được số (amount_vnd null) không bao giờ vào tổng, chỉ được đếm riêng. */
const ThuChiModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const KINDS = ['thu', 'chi', 'ung'];
  const FILTERS = [
    { id: 'all', label: 'Tất cả', match: () => true },
    { id: 'missing', label: 'Chưa vào sổ', match: item => item.status === 'MISSING' },
    { id: 'diff', label: 'Lệch số', match: item => item.status === 'AMOUNT_DIFF' },
    { id: 'unknown', label: 'Chưa rõ đối tượng', match: item => item.status === 'UNKNOWN_TARGET' || item.status === 'SUGGEST' },
    { id: 'noamount', label: 'Không đọc được số', match: item => item.status === 'NO_AMOUNT' },
  ];

  /** Tổng và số khoản của một nhóm khoản: thu, chi, ứng (số khoản chỉ tính khoản đọc được số), cùng các số cần xem. */
  function summarize(items) {
    const out = { missing: 0, diff: 0, noAmount: 0 };
    for (const kind of KINDS) out[kind] = { n: 0, vnd: '0' };
    const sums = { thu: 0n, chi: 0n, ung: 0n };
    for (const item of items) {
      if (item.status === 'MISSING') out.missing += 1;
      if (item.status === 'AMOUNT_DIFF') out.diff += 1;
      if (item.amount_vnd == null) { out.noAmount += 1; continue; }
      sums[item.direction] += F.toBig(String(item.amount_vnd));
      out[item.direction].n += 1;
    }
    for (const kind of KINDS) out[kind].vnd = String(sums[kind]);
    return out;
  }

  /** Số khoản của từng bộ lọc, để chip ghi số đúng với danh sách sau khi bấm. */
  const counts = items => Object.fromEntries(FILTERS.map(filter => [filter.id, items.filter(filter.match).length]));

  const filterItems = (items, id) => items.filter((FILTERS.find(filter => filter.id === id) ?? FILTERS[0]).match);

  /** Gom theo ngày, ngày mới trên cùng; trong ngày giữ thứ tự server (mới nhất trên). Mỗi ngày có tổng thu, chi, ứng. */
  function groupByDay(items) {
    const days = new Map();
    for (const item of items) {
      if (!days.has(item.day)) days.set(item.day, []);
      days.get(item.day).push(item);
    }
    return [...days.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1)).map(([day, rows]) => ({ day, rows, sum: summarize(rows) }));
  }

  const dayShift = (iso, delta) => {
    const [year, month, day] = iso.split('-').map(Number);
    return new Date(Date.UTC(year, month - 1, day + delta)).toISOString().slice(0, 10);
  };
  /** Khoảng xem `days` ngày tính tới hôm nay (giờ VN của server). */
  const range = (today, days) => ({ from: dayShift(today, 1 - days), to: today });

  /** Khóa nhận ra khoản mới giữa hai lần hỏi: mã tin, hoặc dấu của sổ khi không có tin. */
  const keyOf = item => `${item.source}:${item.message_id ?? `${item.conversation_id}:${item.sent_at}:${item.amount_vnd}`}`;
  const newKeys = (before, after) => {
    const seen = new Set(before.map(keyOf));
    return after.map(keyOf).filter(key => !seen.has(key));
  };

  const money = value => (value == null ? '—' : F.full(String(value)));

  /** Câu trạng thái đối chiếu theo bảng của spec (Luồng 2). `tone`: ok (đã vào sổ), wait, warn (cần người xem), info. */
  function statusText(item) {
    const shared = item.shared ? 'Một dòng sổ có hai khoản báo cùng chờ: người xem chọn.' : '';
    switch (item.status) {
      case 'RECORDED': return { tone: 'ok', text: 'Đã vào sổ', note: '' };
      case 'WAITING': return { tone: 'wait', text: 'Chờ vào sổ', note: '' };
      case 'MISSING': return { tone: 'warn', text: 'Chưa vào sổ', note: 'Quá 3 ngày vẫn chưa thấy trong sổ.' };
      case 'AMOUNT_DIFF': return { tone: 'warn', text: `Lệch: báo ${money(item.amount_vnd)}, sổ ${money(item.ledger_vnd)}`, note: shared };
      case 'SUGGEST': return { tone: 'warn', text: `Có thể là phiếu của sổ ${item.ledger_ref?.name ?? ''}`.trim(), note: ['Người xác nhận.', shared].filter(Boolean).join(' ') };
      case 'UNKNOWN_TARGET': return { tone: 'info', text: 'Chưa rõ của ai', note: item.ambiguous ? 'Tin khớp nhiều hơn một tên.' : '' };
      case 'NO_LEDGER': return { tone: 'info', text: 'Web chưa có sổ chi này', note: 'Chỉ liệt kê.' };
      case 'NO_AMOUNT': return { tone: 'info', text: 'Không đọc được số', note: 'Số tiền không đúng mẫu, không cộng vào tổng.' };
      default: return { tone: 'info', text: '', note: '' };
    }
  }

  const KIND_LABEL = { thu: 'Thu', chi: 'Chi', ung: 'Ứng' };

  const api = { FILTERS, KIND_LABEL, summarize, counts, filterItems, groupByDay, range, dayShift, keyOf, newKeys, statusText, money };
  return api;
})();
if (typeof module !== 'undefined') module.exports = ThuChiModel;
