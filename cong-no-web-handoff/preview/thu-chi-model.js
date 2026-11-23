/* Phép tính cho trang Thu chi (ZALO-THU-CHI-01 PR-2): tổng theo ngày, đếm theo bộ lọc, gom ngày, câu trạng thái đối chiếu.
   Dữ liệu là `items` của GET /api/v7/cash-chat; số tiền cộng bằng BigInt ở đây, render (thu-chi-ui.js) chỉ định dạng (ARCH-03).
   Khoản không đọc được số (amount_vnd null) không bao giờ vào tổng, chỉ được đếm riêng.
   PR-4b: khoản `source: 'anh'` là ảnh chuyển khoản máy đọc (không kèm mẫu); `image_vnd` là số đọc từ ảnh của khoản để so với số gõ.
   Luồng 3: khoản người dùng đã loại (`NOT_CASH`) chỉ hiện ở bộ lọc "Đã loại", không đếm và không cộng ở đâu khác. */
const ThuChiModel = (() => {
  'use strict';
  const F = typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js');
  const KINDS = ['thu', 'chi', 'ung'];
  // Mọi mã trạng thái của máy chủ: trang hỏi đủ, kể cả khoản đã loại, để bộ lọc "Đã loại" không phải hỏi riêng.
  const STATUSES = ['RECORDED', 'WAITING', 'MISSING', 'AMOUNT_DIFF', 'SUGGEST', 'UNKNOWN_TARGET', 'NO_LEDGER', 'NO_AMOUNT', 'NOT_CASH'];
  const dropped = item => item.status === 'NOT_CASH';
  const FILTERS = [
    { id: 'all', label: 'Tất cả', match: item => !dropped(item) },
    { id: 'missing', label: 'Chưa vào sổ', match: item => item.status === 'MISSING' },
    { id: 'diff', label: 'Lệch số', match: item => item.status === 'AMOUNT_DIFF' || Boolean(item.image_diff) },
    { id: 'unknown', label: 'Chưa rõ đối tượng', match: item => item.status === 'UNKNOWN_TARGET' || item.status === 'SUGGEST' },
    { id: 'noamount', label: 'Không đọc được số', match: item => item.status === 'NO_AMOUNT' },
    { id: 'notcash', label: 'Đã loại', match: dropped },
  ];

  /** Tổng và số khoản của một nhóm khoản: thu, chi, ứng (số khoản chỉ tính khoản đọc được số; `img` là số khoản trong đó đọc từ ảnh),
      cùng các số cần xem. */
  function summarize(items) {
    const out = { missing: 0, diff: 0, noAmount: 0 };
    for (const kind of KINDS) out[kind] = { n: 0, img: 0, vnd: '0' };
    const sums = { thu: 0n, chi: 0n, ung: 0n };
    for (const item of items) {
      if (dropped(item)) continue;
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
    const status = !imageDiff(item) ? base
      : { tone: 'warn', text: `Lệch: mẫu ${money(item.amount_vnd)}, ảnh ${money(item.image_vnd)}`, note: joinNotes(`${base.text}.`, base.note) };
    return { ...status, note: joinNotes(status.note, resentNote(item)) };
  }

  /** Luồng 4: cùng một lần trả được gửi lại (cùng ảnh, hoặc ảnh khác cùng số và cùng phút giao dịch) thì chỉ tính một khoản; ghi rõ để người
      xem không tưởng bị sót hay cộng hai lần. Máy chủ đếm (`resent`), 0 hay thiếu là không trùng. */
  const resentNote = item => (Number.isInteger(item.resent) && item.resent > 0
    ? `Ảnh chuyển khoản gửi lại thêm ${item.resent.toLocaleString('vi-VN')} lần (cùng giao dịch): chỉ tính một lần.` : '');

  function matchText(item) {
    const shared = item.shared ? 'Một dòng sổ có hai khoản báo cùng chờ: người xem chọn.' : '';
    const image = item.source === 'anh';
    // Dấu khách báo giữ số người nhập; ảnh gộp vào dấu mà đọc ra số khác thì chỉ ghi chú để người xem so.
    const markImage = item.source === 'mark' && item.image_vnd != null && String(item.image_vnd) !== String(item.amount_vnd) ? `Ảnh đọc ra ${money(item.image_vnd)}.` : '';
    if (item.unchecked && item.status === 'WAITING') return { tone: 'info', text: 'Chưa đối chiếu được', note: 'Không đọc được sổ lúc này, chưa biết đã vào sổ hay chưa.' };
    if (item.old_txn && item.status === 'WAITING') {   // máy chủ không kết luận "chưa vào sổ" cho ảnh ghi ngày giao dịch quá cũ
      const [year, month, day] = String(item.image?.txn_time ?? '').slice(0, 10).split('-');
      const when = day ? ` ${day}/${month}/${year}` : '';
      return { tone: 'info', text: 'Ảnh ghi ngày cũ', note: `Ảnh ghi giao dịch ngày${when}, trước ngày gửi hơn 3 tháng: ảnh cũ gửi lại hoặc máy đọc nhầm ngày. Mở ảnh để xem.` };
    }
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
      case 'NOT_CASH': return { tone: 'info', text: 'Đã loại: không phải thu chi', note: item.review?.reason ? `Lý do: ${item.review.reason}` : '' };
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

  // ---- Luồng 3: xác nhận, sửa số, gắn đối tượng, loại (POST /api/v7/cash-chat/review). Không ghi tiền. ----

  /** Khoản bấm xử lý được không, và vì sao không. Dấu "khách báo đã chuyển" có luồng riêng ở Chat Zalo; một tin có hai ảnh chuyển khoản
      thì máy chủ không biết xác nhận ảnh nào (MULTIPLE_IMAGES), nên nói trước thay vì để người bấm rồi mới báo lỗi. */
  function reviewable(item, items) {
    if (item.source === 'mark') return { ok: false, why: 'Dấu khách báo: sửa ở Chat Zalo.' };
    if (!item.message_id || !item.conversation_id) return { ok: false, why: '' };
    const twins = items.filter(other => other.message_id === item.message_id).length;
    if (twins > 1) return { ok: false, why: 'Tin có nhiều ảnh chuyển khoản: chưa xử lý riêng từng ảnh được.' };
    return { ok: true, why: '' };
  }

  /** Việc bấm được ở một khoản. Khoản đã loại chỉ còn "Đưa lại vào thu chi" (là một lần xác nhận: xác nhận và loại thay nhau). */
  function actions(item) {
    if (dropped(item)) return ['restore'];
    const out = [];
    if (item.amount_vnd != null && item.review?.decision !== 'confirm') out.push('confirm');
    return [...out, 'amount', 'target', 'not_cash'];
  }
  const ACTION_LABEL = { confirm: 'Đúng, xác nhận', restore: 'Đưa lại vào thu chi', amount: 'Sửa số', target: 'Gắn sổ/xe', not_cash: 'Không phải thu chi' };
  const LAST_LABEL = { confirm: 'Xác nhận', amount: 'Sửa số', target: 'Gắn đối tượng', not_cash: 'Loại' };

  /** Thu thì gắn sổ khách; chi và ứng thì gắn xe hoặc tài xế (như máy tự khớp). */
  const targetKinds = direction => (direction === 'thu' ? ['so'] : ['xe', 'tai_xe']);
  const TARGET_LABEL = { so: 'Sổ', xe: 'Xe', tai_xe: 'Tài xế' };

  /** Số người gõ ở ô "Số đúng": chỉ chữ số và dấu ngăn nghìn đều (chấm, phẩy hay khoảng trắng, đúng bộ đọc chung `readVnd`).
      Không đọc "tr", "k" hay số lẻ ("1,5" không thành 15): không đoán số. Trả chuỗi VND nguyên dương ≤ 10^12, hoặc null. */
  function parseAmount(text) {
    const digits = F.readVnd(text, { space: true });
    if (digits === null || !/^[1-9][0-9]*$/.test(digits) || digits.length > 13) return null;
    return F.toBig(digits) <= 10n ** 12n ? digits : null;
  }

  /** Tìm đối tượng theo tên hay biển số, bỏ dấu; "51c12345" khớp "51C-123.45". Giữ chữ Hán (foldText không xóa). */
  function searchTargets(rows, query, limit = 8) {
    const loose = F.foldText(query).trim();
    const tight = F.fold(query).replace(/ /g, '');
    if (!loose) return rows.slice(0, limit);
    return rows.filter(row => F.foldText(row.label).includes(loose) || (tight && F.fold(row.label).replace(/ /g, '').includes(tight))).slice(0, limit);
  }

  /** Câu ngắn về lần xử lý gần nhất (người làm, việc, số lần); giờ do trang định dạng. */
  function reviewSummary(item) {
    const review = item.review;
    if (!review || !review.last_action) return null;
    const what = review.decision === 'confirm' ? 'Đã xác nhận' : review.decision === 'not_cash' ? 'Đã loại'
      : LAST_LABEL[review.last_action] ? `Đã ${LAST_LABEL[review.last_action].toLowerCase()}` : 'Đã xử lý';
    return { what, by: review.last_by ?? null, at: review.last_at ?? null, times: Number(review.reviews) || 1 };
  }

  const api = { STATUSES, FILTERS, KIND_LABEL, summarize, counts, filterItems, groupByDay, range, dayShift, keyOf, newKeys, statusText, imageDiff, money,
    reviewable, actions, ACTION_LABEL, targetKinds, TARGET_LABEL, parseAmount, searchTargets, reviewSummary };
  return api;
})();
if (typeof module !== 'undefined') module.exports = ThuChiModel;
