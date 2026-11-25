/* SO-TIEN P0-a lát 2: phần không vẽ của hai trang Sổ tiền và Đối soát ngày (specs/so-tien-p0a-lat2.md, mục Màn hình).
 * Gồm chữ nghiệp vụ cho mã của máy chủ (lớp dòng, trạng thái phân bổ, độ phủ, lý do chưa ký, chỗ gãy), đọc số tiền gõ tay, tính
 * phần còn lại khi phân bổ (BigInt; tính tiền chỉ ở model, ARCH-03), gom quyết định dòng nghi trùng/giao dịch cũ thành thân lệnh
 * commit đúng luật của commit_import (mọi giao dịch đã có trong kỳ mà file chưa nhận phải là đích "trùng" hoặc được giữ có lý do),
 * và chọn ngày làm việc tiếp theo. Tiền từ máy chủ là chuỗi số nguyên đơn vị nhỏ nhất; null là chưa biết, hiện "—"; chuỗi không
 * phải số nguyên (dòng lỗi của file) hiện nguyên văn. Không gọi mạng, không đụng DOM: test ở test-so-tien-model.js. */
(function (root, factory) {
  // cong-no-format.js khai báo CongNoFormat bằng const ở tầm script (không có trên globalThis); Node lấy qua require.
  const api = factory(typeof CongNoFormat !== 'undefined' ? CongNoFormat : require('./cong-no-format.js'));
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.SoTienModel = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, F => {
  'use strict';

  const CLASS = { new: 'Mới', duplicate: 'Đã có trong sổ', suspect: 'Cần quyết', error: 'Lỗi' };
  const STATUS = {
    unidentified: 'Chưa rõ khách', unapplied: 'Biết khách, chưa rõ khoản', partial: 'Phân bổ một phần', applied: 'Đã phân bổ đủ',
    unmatched: 'Chưa ghép', matched: 'Đã ghép đủ', voided: 'Đã hủy',
  };
  const IMPORT_STATUS = { validated: 'Chờ ghi', committed: 'Đã ghi', rejected: 'Đã bỏ', voided: 'Đã hủy' };
  const COVERAGE = { full: 'Đủ sao kê', partial: 'Ngày chưa trọn', missing: 'Thiếu sao kê', before_opening: 'Trước số dư mở', future: 'Chưa tới' };
  const SIGN = { signed: 'Đã ký', reopened: 'Mở lại', unconfirmed: 'Chưa ký', open: 'Chưa ký' };
  const SOURCE = { file: 'File sao kê', bank_pdf: 'Sao kê PDF', bank_app: 'App ngân hàng', bank_paper: 'Giấy ngân hàng', other: 'Nguồn khác' };
  const LINE_ERROR = {
    LINE_DUPLICATE_NO: 'Số dòng lặp trong file', LINE_FUTURE_DATE: 'Ngày sau hôm nay', LINE_OUT_OF_PERIOD: 'Ngày ngoài kỳ của file',
    LINE_BEFORE_OPENING: 'Ngày trước số dư mở', LINE_DIRECTION: 'Không rõ thu hay chi', LINE_AMOUNT: 'Số tiền không đọc được',
    LINE_CURRENCY: 'Khác tiền tệ tài khoản',
  };
  const REASON = {
    NO_OPENING: 'Tài khoản chưa có số dư mở.',
    DAY_FUTURE: 'Ngày này chưa tới.',
    BEFORE_OPENING: 'Ngày này trước ngày số dư mở.',
    DAY_INCOMPLETE: 'Sao kê của ngày này chưa trọn ngày: nhập file của ngày làm việc sau (phủ cả ngày này).',
    DAY_MISSING: 'Chưa có sao kê phủ ngày này.',
    MISSING_DAYS_BEFORE: 'Còn ngày trước đó thiếu sao kê hoặc chưa trọn, nên chưa chứng minh được số dư.',
    PENDING_IMPORT: 'Còn lô sao kê chờ ghi phủ tới ngày này: ghi hoặc bỏ lô đó trước (người có vai nhập bỏ được lô).',
    NO_EVIDENCE: 'Chưa có số dư cuối ngày của ngân hàng: file mới nhất không có số dư cuối, cần nhập số dư từ sao kê PDF hoặc app.',
    BALANCE_DIFFERENCE: 'Số dư sổ khác số dư ngân hàng.',
    COVERAGE_NOT_SIGNED: 'Ký số dư của ngày này trước.',
  };
  // Đích phân bổ của lát 2, xếp theo chiều tiền hay gặp; `ref` là ô cần nhập thêm (null: không có).
  const TARGETS = [
    { kind: 'customer_unapplied', label: 'Tiền khách, chưa rõ khoản', ref: 'customer_id', dir: 'in' },
    { kind: 'ar_book', label: 'Trả nợ sổ khách', ref: 'customer_id', dir: 'in' },
    { kind: 'customer_funds_pending', label: 'Tiền hàng khách, chờ', ref: null, dir: 'in' },
    { kind: 'interest', label: 'Lãi ngân hàng', ref: null, dir: 'in' },
    { kind: 'expense_category', label: 'Mục chi', ref: 'category', dir: 'out' },
    { kind: 'fleet', label: 'Đội xe', ref: null, dir: 'out' },
    { kind: 'bank_fee', label: 'Phí ngân hàng', ref: null, dir: 'out' },
    { kind: 'cash_withdrawal', label: 'Rút tiền mặt', ref: null, dir: 'out' },
    { kind: 'internal_transfer', label: 'Chuyển nội bộ (đã có chân kia)', ref: 'transaction_id', dir: null },
    { kind: 'internal_transfer_pending', label: 'Chuyển nội bộ, chờ chân kia', ref: null, dir: null },
    { kind: 'other', label: 'Khác', ref: null, dir: null },
  ];
  const TARGET = Object.fromEntries(TARGETS.map(t => [t.kind, t]));
  const ROLE = { tien_xem: 'xem', tien_nhap: 'nhập', tien_phan_bo: 'phân bổ', tien_review: 'đối chiếu', tien_quan_tri: 'quản trị' };
  const WEEKDAY = ['Chủ nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];

  // Tiền: chuỗi số nguyên → "1.234 đ"; null → "—"; chuỗi khác (ô số tiền sai dạng của dòng lỗi) → nguyên văn, không ném lỗi.
  const money = value => (value === null || value === undefined ? '—' : /^-?\d+$/.test(String(value)) ? F.full(value) : String(value));
  // 'YYYY-MM-DD' → 'dd/mm/yyyy'; tính bằng chữ, không qua Date nên không lệch múi giờ.
  const vnDate = value => (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value.split('-').reverse().join('/') : '—');
  const shortDate = value => vnDate(value).slice(0, 5);
  const utc = value => { const [y, m, d] = value.split('-').map(Number); return Date.UTC(y, m - 1, d); };
  const weekday = value => WEEKDAY[new Date(utc(value)).getUTCDay()];   // thứ của ngày lịch, giờ UTC cố định
  const daysBetween = (from, to) => Math.round((utc(to) - utc(from)) / 86400000);
  const addDays = (value, n) => new Date(utc(value) + n * 86400000).toISOString().slice(0, 10);
  // Giờ VN của một mốc ISO từ vết: 'dd/mm hh:mm'.
  function stamp(value) {
    if (!value) return '—';
    const parts = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
      .formatToParts(new Date(value)).reduce((out, p) => ({ ...out, [p.type]: p.value }), {});
    return `${parts.day}/${parts.month} ${parts.hour}:${parts.minute}`;
  }
  // Chữ người gõ gửi lên máy chủ: gộp xuống dòng và khoảng trắng thành một dấu cách (API từ chối ký tự điều khiển).
  const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();

  // Số tiền gõ tay: "1.234.567", "1234567", "-25.000" → chuỗi số nguyên; sai dạng → null. Không nhận số lẻ.
  function readAmount(text, { signed = false } = {}) {
    const raw = String(text ?? '').trim();
    const negative = signed && raw.startsWith('-');
    const digits = F.readVnd(negative ? raw.slice(1).trim() : raw, { unit: true });
    if (digits === null) return null;
    const plain = digits.replace(/^0+(?=\d)/, '');
    if (plain.length > 18) return null;
    return negative && plain !== '0' ? `-${plain}` : plain;
  }

  // Phân bổ: còn lại = số tiền − Σ dòng (dòng chưa đọc được tính như chưa nhập). Trả chuỗi (có thể âm khi vượt).
  function remaining(amount, lines) {
    let left = BigInt(amount);
    for (const line of lines) {
      const value = readAmount(line.amount);
      if (value !== null) left -= BigInt(value);
    }
    return left.toString();
  }

  // Dòng phân bổ người dùng đang sửa → thân lệnh; lỗi đầu tiên (chữ) hoặc null. Mã trong target_ref là chuỗi số (luật set_allocation).
  function allocationLines(lines) {
    const out = [];
    for (const [i, line] of lines.entries()) {
      const target = TARGET[line.kind];
      const amount = readAmount(line.amount);
      if (!target) return { error: `Dòng ${i + 1}: chọn loại.` };
      if (amount === null || amount === '0') return { error: `Dòng ${i + 1}: số tiền phải là số nguyên lớn hơn 0.` };
      const ref = {};
      if (target.ref) {
        const value = clean(line.ref);
        if (!value) return { error: `Dòng ${i + 1}: ${target.ref === 'category' ? 'ghi mục chi' : target.ref === 'customer_id' ? 'chọn sổ khách' : 'ghi mã giao dịch đối ứng'}.` };
        if (target.ref !== 'category' && !/^[1-9]\d{0,17}$/.test(value)) return { error: `Dòng ${i + 1}: mã phải là số.` };
        ref[target.ref] = value;
      }
      const note = clean(line.note);
      out.push({ target_kind: target.kind, target_ref: ref, amount_minor: amount, ...(note ? { note } : {}) });
    }
    return { lines: out };
  }

  // Bộ mới có bỏ hay đổi dòng đang hiệu lực không (máy chủ đòi lý do khi có, BR-AL3).
  function changesExisting(current, next) {
    const key = l => JSON.stringify([l.target_kind, l.target_ref, l.amount_minor, l.note ?? null]);
    const pool = next.map(key);
    return current.some(line => {
      const at = pool.indexOf(key(line));
      if (at < 0) return true;
      pool.splice(at, 1);
      return false;
    });
  }

  // Đích hiện cho người dùng: "sổ khách #12", "giao dịch #41", tên mục chi.
  function refText(ref) {
    return Object.entries(ref ?? {}).map(([k, v]) => (k === 'customer_id' ? `sổ khách #${v}` : k === 'transaction_id' ? `giao dịch #${v}` : String(v))).join(', ');
  }

  // Lô chờ (theo commit_import của lát 1): dòng nghi trùng chọn "mới" hoặc "trùng" một giao dịch đã có cùng ngày, chiều, số tiền (ứng
  // viên mềm của dòng, hoặc giao dịch đã có mà file chưa nhận); `pool` là mọi giao dịch đã có trong kỳ mà file chưa nhận chắc chắn
  // (giao dịch file không có + ứng viên mềm) — mỗi cái phải là đích "trùng" của một dòng, hoặc được giữ có lý do.
  function questions(view) {
    const unmatched = (view.breaks ?? []).filter(b => b.code === 'UNMATCHED_EXISTING');
    const suspectLines = view.lines.filter(l => l.class === 'suspect');
    const suspects = suspectLines.map(l => {
      const own = l.soft_candidates ?? (l.candidate ? [l.candidate] : []);
      const same = unmatched.filter(u => u.booking_date === l.booking_date && u.direction === l.direction && u.amount_minor === l.amount_minor)
        .map(u => u.transaction_id);
      return { line: l, candidates: [...new Set([...own, ...same])] };
    });
    const pool = [...new Set([...unmatched.map(u => u.transaction_id), ...suspectLines.flatMap(l => l.soft_candidates ?? [])])];
    return { suspects, unmatched, pool };
  }

  const targetsOf = choice => new Map(Object.entries(choice.lines).filter(([, v]) => v !== 'new').map(([line, tx]) => [tx, Number(line)]));

  // Giao dịch cần hỏi lý do giữ lúc này: trong pool, chưa là đích "trùng", và không còn là lựa chọn của dòng chưa quyết.
  function keepAsks(view, choice) {
    const { suspects, pool } = questions(view);
    const targets = targetsOf(choice);
    const open = new Set(suspects.filter(s => choice.lines[s.line.line_no] === undefined).flatMap(s => s.candidates));
    return pool.filter(id => !targets.has(id) && !open.has(id));
  }

  function commitBody(view, choice, known = {}) {
    const { suspects, unmatched, pool } = questions(view);
    const decisions = [];
    const targets = new Set();
    for (const { line } of suspects) {
      const picked = choice.lines[line.line_no];
      if (picked === undefined) return { error: `Dòng ${line.line_no}: chọn giao dịch mới hay trùng.` };
      if (picked === 'new') {
        decisions.push({ line_no: line.line_no, decision: 'new' });
      } else {
        if (targets.has(picked)) return { error: `Dòng ${line.line_no}: hai dòng không thể cùng trùng một giao dịch đã có.` };
        targets.add(picked);
        decisions.push({ line_no: line.line_no, decision: 'duplicate_of', transaction_id: picked });
      }
    }
    const keep = [];
    for (const id of pool) {
      if (targets.has(id)) continue;
      const reason = clean(choice.keep[id]);
      if (!reason) {
        const tx = known[id] ?? unmatched.find(u => u.transaction_id === id);
        const what = tx ? `ngày ${vnDate(tx.booking_date)}, ${money(tx.amount_minor)}` : `#${id}`;
        return { error: `Giao dịch đã có ${what} chưa được file nhận: ghi lý do giữ.` };
      }
      keep.push({ transaction_id: id, reason });
    }
    const body = { import_id: view.import.id, expected_preview_hash: view.preview_hash };
    if (decisions.length) body.suspect_decisions = decisions;
    if (keep.length) body.keep_existing = keep;
    return { body, needsReview: decisions.length + keep.length > 0 };
  }

  // Lô chờ: chỗ chặn ghi (máy chủ chắc chắn từ chối) theo thứ tự hiện cho người dùng; gãy số dư tối đa 5 câu.
  function blockers(view) {
    const out = [];
    if (view.stale) out.push('Sổ đã đổi từ lúc xem trước lô này (vừa ghi lô khác). Bỏ lô này rồi nhập lại file.');
    if ((view.counts?.error ?? 0) > 0) out.push(`Lô có ${view.counts.error} dòng lỗi. Sửa file (tải lại từ ngân hàng) rồi nhập lại.`);
    const chain = (view.breaks ?? []).filter(b => b.code !== 'UNMATCHED_EXISTING');
    for (const b of chain.slice(0, 5)) {
      if (b.code === 'OPENING_MISMATCH') out.push(`Số dư đầu của file ${money(b.actual_minor)} khác số dư sổ đầu kỳ ${money(b.expected_minor)}.`);
      else if (b.code === 'RUNNING_BALANCE') out.push(`Dòng ${b.line_no}: số dư sau trong file ${money(b.actual_minor)}, tính theo các dòng trước là ${money(b.expected_minor)}.`);
      else if (b.code === 'CLOSING_MISMATCH') out.push(`Số dư cuối của file ${money(b.actual_minor)} khác số dư đầu cộng các dòng ${money(b.expected_minor)}.`);
    }
    if (chain.length > 5) out.push(`Và ${chain.length - 5} chỗ gãy số dư khác.`);
    return out;
  }

  // Lô chờ: cảnh báo không chặn — ngày đã ký số dư sẽ chặn nếu lô tạo giao dịch ở ngày đó hoặc trước (dòng chọn "trùng" thì không tạo).
  function warnings(view) {
    return (view.signed_days ?? []).map(day => `Ngày ${vnDate(day)} đã ký số dư. Nếu lô tạo giao dịch ở ngày đó hoặc trước đó thì ghi sẽ bị chặn: mở lại ngày ${vnDate(day)} ở Đối soát ngày (các ngày đã ký sau đó mở lại theo).`);
  }

  // Ngày nên mở đầu tiên ở Đối soát ngày: ngày cũ nhất đủ sao kê mà chưa ký số dư hoặc chưa ký đối soát; không có thì ngày mới nhất.
  function nextDay(days) {
    const open = days.filter(d => d.coverage === 'full' && (d.coverage_status !== 'signed' || d.business_status !== 'signed'));
    if (open.length) return open[open.length - 1].date;   // danh sách mới nhất trước
    return days[0]?.date ?? null;
  }

  // Câu ngắn trạng thái số dư của một ngày trong cột ngày.
  function dayCoverageText(day) {
    if (day.coverage_status === 'signed') return 'Đã ký';
    if (day.coverage === 'missing') return 'Thiếu sao kê';
    if (day.coverage === 'partial') return 'Chưa trọn';
    return day.coverage_status === 'reopened' ? 'Mở lại' : 'Chưa ký';
  }

  const has = (roles, role) => Array.isArray(roles) && roles.includes(role);

  // Tháng 'YYYY-MM' → [ngày 1, ngày cuối tháng nhưng không quá hôm nay] (hôm nay là chuỗi ngày VN do máy chủ gửi).
  function monthRange(month, today) {
    const [y, m] = month.split('-').map(Number);
    const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
    const end = `${month}-${String(last).padStart(2, '0')}`;
    return [`${month}-01`, end < today ? end : today];
  }

  // Chênh = số dư sổ − số dư ngân hàng (chuỗi số nguyên có dấu) → câu thường.
  function diffText(diff) {
    if (diff === null || diff === undefined) return '—';
    if (diff === '0') return 'Khớp';
    return diff.startsWith('-') ? `Sổ thấp hơn ngân hàng ${money(diff.slice(1))}` : `Sổ cao hơn ngân hàng ${money(diff)}`;
  }

  // Ai ghi được lô chờ (lát 1): lô có câu cần quyết (nghi trùng, giao dịch cũ) cần vai đối chiếu; lô không có thì cần vai nhập.
  function commitRole(view) {
    const { suspects, pool } = questions(view);
    return suspects.length + pool.length > 0 ? 'tien_review' : 'tien_nhap';
  }

  return {
    CLASS, STATUS, IMPORT_STATUS, COVERAGE, SIGN, SOURCE, LINE_ERROR, REASON, TARGETS, TARGET, ROLE,
    money, vnDate, shortDate, weekday, daysBetween, addDays, stamp, clean, readAmount, remaining, allocationLines, changesExisting,
    refText, questions, keepAsks, commitBody, blockers, warnings, nextDay, dayCoverageText, has, monthRange, diffText, commitRole,
  };
}));
