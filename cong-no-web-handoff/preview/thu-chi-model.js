/* Phép tính cho trang Thu chi (ZALO-THU-CHI-01 PR-2): tổng theo ngày, đếm theo bộ lọc, gom ngày, câu trạng thái đối chiếu.
   Dữ liệu là `items` của GET /api/v7/cash-chat; số tiền cộng bằng BigInt ở đây, render (thu-chi-ui.js) chỉ định dạng (ARCH-03).
   Khoản không đọc được số (amount_vnd null) không bao giờ vào tổng, chỉ được đếm riêng.
   PR-4b: khoản `source: 'anh'` là ảnh chuyển khoản máy đọc (không kèm mẫu); `image_vnd` là số đọc từ ảnh của khoản để so với số gõ. */
const ThuChiModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const KINDS = ['thu', 'chi', 'ung'];
  const FILTERS = [
    { id: 'all', label: 'Tất cả', match: () => true },
    { id: 'missing', label: 'Chưa vào sổ', match: item => item.status === 'MISSING' },
    { id: 'diff', label: 'Lệch số', match: item => item.status === 'AMOUNT_DIFF' || Boolean(item.image_diff) },
    { id: 'unknown', label: 'Chưa rõ đối tượng', match: item => item.status === 'UNKNOWN_TARGET' || item.status === 'SUGGEST' },
    { id: 'noamount', label: 'Không đọc được số', match: item => item.status === 'NO_AMOUNT' },
  ];

  /** Tổng và số khoản của một nhóm khoản: thu, chi, ứng (số khoản chỉ tính khoản đọc được số; `img` là số khoản trong đó đọc từ ảnh),
      cùng các số cần xem. */
  function summarize(items) {
    const out = { missing: 0, diff: 0, noAmount: 0 };
    for (const kind of KINDS) out[kind] = { n: 0, img: 0, vnd: '0' };
    const sums = { thu: 0n, chi: 0n, ung: 0n };
    for (const item of items) {
      if (item.status === 'MISSING') out.missing += 1;
      if (item.status === 'AMOUNT_DIFF' || item.image_diff) out.diff += 1;
      if (item.amount_vnd == null) { out.noAmount += 1; continue; }
      sums[item.direction] += F.toBig(String(item.amount_vnd));
      out[item.direction].n += 1;
      if (item.source === 'anh') out[item.direction].img += 1;
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

  /** Khóa nhận ra khoản mới giữa hai lần hỏi: mã tin (khoản từ ảnh thêm mã ảnh: một tin có thể có hai ảnh), hoặc dấu của sổ khi không có tin. */
  const keyOf = item => `${item.source}:${item.message_id ?? `${item.conversation_id}:${item.sent_at}:${item.amount_vnd}`}`
    + (item.source === 'anh' ? `:${item.media?.[0]?.id ?? ''}` : '');
  const newKeys = (before, after) => {
    const seen = new Set(before.map(keyOf));
    return after.map(keyOf).filter(key => !seen.has(key));
  };

  const money = value => (value == null ? '—' : F.full(String(value)));

  /** Mẫu gõ và ảnh chứng đọc ra hai số khác nhau (Luồng 4: "mẫu X, ảnh Y"). Số lấy từ ảnh thì không có gì để so. */
  /** Mẫu gõ và ảnh chứng đọc ra hai số khác nhau (Luồng 4: "mẫu X, ảnh Y"). Máy chủ đặt cờ; trạng thái đối chiếu vẫn giữ nguyên. */
  const imageDiff = item => Boolean(item.image_diff);
  const joinNotes = (...notes) => notes.filter(Boolean).join(' ');

  /** Câu trạng thái đối chiếu theo bảng của spec (Luồng 2). `tone`: ok (đã vào sổ), wait, warn (cần người xem), info.
      Mẫu và ảnh khác số thì câu chính là "Lệch: mẫu X, ảnh Y", câu đối chiếu (đã vào sổ, gợi ý sổ, chưa vào sổ…) chuyển xuống ghi chú. */
  function statusText(item) {
    const base = matchText(item);
    if (!imageDiff(item)) return base;
    return { tone: 'warn', text: `Lệch: mẫu ${money(item.amount_vnd)}, ảnh ${money(item.image_vnd)}`, note: joinNotes(`${base.text}.`, base.note) };
  }

  function matchText(item) {
    const shared = item.shared ? 'Một dòng sổ có hai khoản báo cùng chờ: người xem chọn.' : '';
    const image = item.source === 'anh';
    // Dấu khách báo giữ số người nhập; ảnh gộp vào dấu mà đọc ra số khác thì chỉ ghi chú để người xem so.
    const markImage = item.source === 'mark' && item.image_vnd != null && String(item.image_vnd) !== String(item.amount_vnd) ? `Ảnh đọc ra ${money(item.image_vnd)}.` : '';
    if (item.unchecked && item.status === 'WAITING') return { tone: 'info', text: 'Chưa đối chiếu được', note: 'Không đọc được sổ lúc này, chưa biết đã vào sổ hay chưa.' };
    switch (item.status) {
      case 'RECORDED': return { tone: 'ok', text: 'Đã vào sổ', note: markImage };
      case 'WAITING': return { tone: 'wait', text: 'Chờ vào sổ', note: markImage };
      case 'MISSING': return { tone: 'warn', text: 'Chưa vào sổ', note: joinNotes('Quá 3 ngày vẫn chưa thấy trong sổ.', markImage) };
      case 'AMOUNT_DIFF': return { tone: 'warn', text: `Lệch: báo ${money(item.amount_vnd)}, sổ ${money(item.ledger_vnd)}`, note: shared };
      case 'SUGGEST': return { tone: 'warn', text: `Có thể là phiếu của sổ ${item.ledger_ref?.name ?? ''}`.trim(), note: joinNotes('Người xác nhận.', shared) };
      case 'UNKNOWN_TARGET':
        if (image) {   // `link`: lý do máy chủ gửi kèm (one, many, none, failed)
          const why = { failed: 'Không đọc được danh sách nhóm gắn sổ lúc này.', many: 'Hội thoại gắn nhiều sổ.' }[item.link] ?? 'Hội thoại chưa gắn sổ.';
          return { tone: 'info', text: 'Chưa rõ của ai', note: joinNotes(why, item.unchecked && item.link !== 'failed' ? 'Chưa kiểm được phiếu đúng số lúc này.' : '') };
        }
        return { tone: 'info', text: 'Chưa rõ của ai', note: item.unchecked ? 'Không đọc được danh sách khách và xe lúc này.' : item.ambiguous ? 'Tin khớp nhiều hơn một tên.' : '' };
      case 'NO_LEDGER': return { tone: 'info', text: 'Web chưa có sổ chi này', note: 'Chỉ liệt kê.' };
      case 'NO_AMOUNT':
        if (image) {
          const seen = (item.image?.candidates ?? []).map(money);
          return { tone: 'info', text: 'Ảnh chưa đọc chắc',
            note: `${seen.length ? `Máy đọc ra ${seen.join(' và ')}.` : 'Máy không đọc ra số.'} Mở ảnh để xem, không cộng vào tổng.` };
        }
        return { tone: 'info', text: 'Không đọc được số', note: 'Số tiền không đúng mẫu, không cộng vào tổng.' };
      default: return { tone: 'info', text: '', note: '' };
    }
  }

  const KIND_LABEL = { thu: 'Thu', chi: 'Chi', ung: 'Ứng' };

  const api = { FILTERS, KIND_LABEL, summarize, counts, filterItems, groupByDay, range, dayShift, keyOf, newKeys, statusText, imageDiff, money };
  return api;
})();
if (typeof module !== 'undefined') module.exports = ThuChiModel;
