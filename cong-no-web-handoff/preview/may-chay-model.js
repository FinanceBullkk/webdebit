/* Tab Máy chạy (MAY-CHAY-01): đổi dữ liệu của /api/v7/machine thành một lượt để vẽ, và tính trạng thái ở từng giây của lượt. Không đụng DOM.
 * Mọi thứ trên màn hình suy từ `run` và `t` (giây kể từ lúc lượt bắt đầu), nên tua tới, tua lùi, xem trực tiếp đều cùng một đường. */
const MayChayModel = (() => {
  'use strict';
  const ORDER = ['tai', 'sach', 'doc', 'so', 'chot', 'tim', 'ghi', 'luu'];
  const NAMES = { tai: 'Tải Sheet', sach: 'Làm sạch', doc: 'Đọc sổ web', so: 'So tổng', chot: 'Chốt 1', tim: 'Tìm cách sửa', ghi: 'Ghi và đọc lại', luu: 'Lưu kết quả' };
  // wrote: lý do này nghĩa là đã có lệnh ghi vào sổ.
  const RESULT = {
    FIXED: { tag: 'Đã ghi', tone: 'ok', wrote: true },
    BOOK_CREATED: { tag: 'Tạo sổ mới', tone: 'new', wrote: true, why: 'Tab mới có trên TONG, số khớp. Máy tạo sổ theo đường nạp mốc.' },
    VERIFY_FAILED: { tag: 'Báo lỗi', tone: 'bad', wrote: true, why: 'Ghi xong đọc lại không khớp. Chốt 3 báo lỗi, máy canh gửi email.' },
    WRITE_ERROR: { tag: 'Lỗi ghi', tone: 'bad', wrote: true, why: 'Lệnh ghi bị từ chối. Máy đọc lại sổ, lượt sau tính lại.' },
    CHECK_ERROR: { tag: 'Lỗi kiểm', tone: 'bad', why: 'Lỗi khi kiểm khách này. Khách khác vẫn chạy, lượt sau tính lại.' },
    NO_EXACT_FIX: { tag: 'Không ghi', tone: 'warn', why: 'Không có tổ hợp nào bằng đúng số lệch, nên không ghi. Cần người xem.' },
    AMBIGUOUS_FIX: { tag: 'Không ghi', tone: 'warn', why: 'Có hơn một tổ hợp cùng ra đúng số lệch. Máy không đoán, cần người chọn.' },
    NOTHING_TO_WRITE: { tag: 'Không ghi', tone: 'warn', why: 'Lệch mà không có việc nào đang chờ để ghi. Cần người xem.' },
    TOO_MANY_GROUPS: { tag: 'Không ghi', tone: 'warn', why: 'Quá nhiều nhóm việc để máy xét. Cần người xem.' },
    TOO_MANY_DIFFERENT: { tag: 'Không ghi', tone: 'warn', why: 'Quá nhiều khách lệch cùng lúc, cả lượt không ghi.' },
    SHEET_SHUFFLED: { tag: 'Không ghi', tone: 'warn', why: 'Giá trên Sheet đổi chỗ trong tháng, khớp tổng không phân biệt được. Cần người xem.' },
    HELD: { tag: 'Bị giữ', tone: 'warn', why: 'Tab đọc không được, khách này không đưa vào so. Cần người xem.' },
    WEB_AHEAD: { tag: 'Web đi trước', tone: 'info', why: 'Web có việc Sheet chưa có. Chênh đúng bằng phần đó, không cần ghi.' },
    CHI_CO_WEB: { tag: 'Chỉ báo', tone: 'warn', why: 'Có sổ trên web mà không thấy trên Sheet. Máy không tự xóa.' },
    THIEU_SO: { tag: 'Chỉ báo', tone: 'warn', why: 'Thiếu số để so.' },
    BOOK_OVERLAP: { tag: 'Không tạo sổ', tone: 'warn', why: 'Tab mới trùng chuyến với sổ khác. Cần người xem.' },
    TOO_MANY_NEW_BOOKS: { tag: 'Không tạo sổ', tone: 'warn', why: 'Quá nhiều tab mới cùng lúc. Cần người xem.' },
    WOULD_FIX: { tag: 'Sẽ ghi', tone: 'info', why: 'Lượt chỉ kiểm, không ghi.' },
    WOULD_CREATE_BOOK: { tag: 'Sẽ tạo sổ', tone: 'info', why: 'Lượt chỉ kiểm, không tạo sổ.' },
  };
  const resultOf = reason => RESULT[reason] ?? { tag: 'Cần xem', tone: 'warn', why: 'Máy không ghi khách này.' };
  const secOfDay = iso => { const [h, m, s] = String(iso).slice(11, 19).split(':').map(Number); return h * 3600 + m * 60 + (s || 0); };
  const pad = n => String(n).padStart(2, '0');
  const clockOf = s => { const v = Math.max(0, Math.floor(s)); return `${pad(Math.floor(v / 3600) % 24)}:${pad(Math.floor(v / 60) % 60)}:${pad(v % 60)}`; };
  const hhmm = iso => String(iso ?? '').slice(11, 16);

  // Tiền là chuỗi số nguyên từ API: chỉ tách nhóm, không đổi sang số thực.
  const groups = text => { const raw = String(text ?? ''); const sign = raw.startsWith('-') ? '-' : ''; return sign + raw.replace(/^-/, '').replace(/\B(?=(\d{3})+(?!\d))/g, '.'); };
  const money = text => (text === null || text === undefined || text === '' ? '—' : `${groups(text)}đ`);
  function millions(text) {
    if (text === null || text === undefined || text === '') return '—';
    const value = BigInt(text), negative = value < 0n, abs = negative ? -value : value;
    const tenths = (abs + 50000n) / 100000n, whole = tenths / 10n, part = tenths % 10n;
    return `${negative ? '-' : ''}${groups(String(whole))}${part ? `,${part}` : ''} tr`;
  }

  function buildStages(segments, sec) {
    const stages = {};
    let cursor = 0;
    for (const key of ORDER) {
      const own = segments.map((item, index) => ({ ...item, end: segments[index + 1]?.t ?? sec })).filter(item => item.stage === key);
      if (own.length) {
        const from = own[0].t, to = own[own.length - 1].end;
        stages[key] = { from, to, d: Math.max(to - from, 0.001) };
        cursor = Math.max(cursor, to);
      } else stages[key] = { from: cursor, to: cursor, d: 0 };
    }
    return stages;
  }

  function fromTrace(trace, row) {
    const start = secOfDay(trace.started_at), live = trace.state === 'running';
    const end = trace.finished_at ? secOfDay(trace.finished_at) : start;
    const sec = Math.max(end - start, 1);
    const segments = (trace.segments ?? []).map(item => ({ stage: item.stage, t: Math.max(secOfDay(item.at) - start, 0) }));
    const stages = buildStages(segments, sec);
    const counts = trace.counts ?? row?.counts ?? {};
    const customers = Object.values(trace.customers ?? {}).map(item => {
      const info = resultOf(item.reason);
      const decided = item.decided_at ? secOfDay(item.decided_at) - start : stages.tim.d ? stages.tim.from : stages.luu.from;
      const done = item.done_at ? secOfDay(item.done_at) - start : decided;
      return { id: item.customer_id, reason: item.reason ?? null, info: item.reason ? info : { tag: 'Đang xét', tone: 'info' }, wrote: Boolean(info.wrote && item.reason), before: item.before_vnd ?? null, after: item.after_vnd ?? null, target: item.target_vnd ?? null, difference: item.difference_vnd ?? null, decided, done };
    }).sort((a, b) => a.decided - b.decided);
    return {
      id: trace.started_at, day: String(trace.started_at).slice(0, 10), start, sec, end, segments, stages, customers, live, failed: trace.state === 'failed', failReason: trace.reason ?? null,
      tooMany: Boolean(trace.too_many), different: trace.different ?? null, total: trace.books ?? row?.total ?? null, khop: counts.KHOP ?? null, fixed: trace.fixed ?? row?.fixed ?? 0, created: trace.created ?? row?.created ?? 0,
      unlinked: trace.unlinked ?? {}, stage: trace.stage ?? null, done: trace.done ?? null, count: trace.total ?? null, mode: trace.mode ?? null, countsOnly: false, estimated: false, drill: null,
    };
  }

  // Dòng log cũ chỉ có số đếm: chia trạm theo ước tính, thẻ khách không có. Tổng số giây tính từ phút :05 của lịch.
  function fromCounts(row) {
    const at = row.finished_at, end = secOfDay(at), minute = Math.floor(end / 60) % 60, total = row.total ?? 0, khop = row.counts?.KHOP ?? 0;
    const touched = total - khop + (row.fixed ?? 0) + (row.created ?? 0) > 0;
    const onSchedule = minute >= 5 && minute <= 14;
    const sec = Math.max(onSchedule ? end - (end - (end % 3600)) - 300 : touched ? 450 : 292, 30);
    const weights = [['tai', 12], ['sach', 135], ['doc', 125], ['so', 8], ...(touched ? [['chot', 2], ['tim', 140], ['ghi', 25]] : []), ['luu', 5]];
    const sum = weights.reduce((acc, item) => acc + item[1], 0);
    let t = 0;
    const segments = weights.map(([stage, weight]) => { const item = { stage, t }; t += (weight / sum) * sec; return item; });
    return {
      id: at, day: String(at).slice(0, 10), start: end - sec, sec, end, segments, stages: buildStages(segments, sec), customers: [], live: false, failed: false, failReason: null, tooMany: false, different: total - khop,
      total, khop, fixed: row.fixed ?? 0, created: row.created ?? 0, unlinked: {}, stage: null, done: null, count: null, mode: row.mode ?? null, countsOnly: true, estimated: true, onSchedule, drill: null,
    };
  }
  const fromRow = row => (row.detail ? fromTrace(row.detail, row) : fromCounts(row));

  const slotKind = run => (run.failed ? 'bad' : run.fixed + run.created > 0 ? 'wrote' : run.total !== null && run.khop !== null && run.khop < run.total ? 'left' : 'quiet');

  function byDay(rows) {
    const days = new Map();
    for (const row of rows) {
      const run = fromRow(row);
      if (!days.has(run.day)) days.set(run.day, []);
      days.get(run.day).push(run);
    }
    return [...days.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1)).map(([day, runs]) => ({
      day, runs, fixed: runs.reduce((acc, run) => acc + run.fixed, 0), created: runs.reduce((acc, run) => acc + run.created, 0), label: `${Number(day.slice(8))}/${Number(day.slice(5, 7))}`,
    }));
  }

  function stageNow(run, t) {
    if (t >= run.sec && !run.live) return null;
    let current = null;
    for (const item of run.segments) if (item.t <= t) current = item.stage;
    return current;
  }

  function stationInfo(run, t, key, cur) {
    const s = run.stages[key];
    const f = s.d ? Math.min(1, Math.max(0, (t - s.from) / s.d)) : 0;
    let state = '', text = '';
    const passed = run.stages.so.d ? t >= run.stages.so.to : false;
    if (!s.d) { if (passed || (t >= run.sec && !run.live)) state = 'skip'; }
    else if (cur === key) state = 'run';
    else if (t >= s.to) state = 'done';
    if (state === 'skip') text = key === 'chot' ? 'không cần' : run.tooMany ? 'không chạy' : 'bỏ qua';
    if (key === 'tai' && f > 0) text = 'chỉ đọc';
    if (['sach', 'doc', 'so'].includes(key) && f > 0) {
      // Trạm đang chạy trực tiếp đếm theo job báo; xem lại thì suy theo thời gian của trạm.
      const reported = run.live && cur === key && run.count;
      const whole = reported ? run.count : run.total;
      if (whole) text = `${reported ? (run.done ?? 0) : Math.floor(f * whole)}/${whole}`;
    }
    if (key === 'chot' && s.d && f >= 1) { text = run.tooMany ? 'dừng' : 'qua'; if (run.tooMany) state = 'stop'; }
    if (key === 'tim' && s.d && f > 0 && !run.countsOnly) text = `${run.customers.filter(c => t >= c.decided).length}/${run.customers.length} khách`;
    if (key === 'ghi' && s.d && f > 0 && !run.countsOnly) {
      const list = run.customers.filter(c => c.wrote);
      text = `${list.filter(c => t >= c.done).length}/${list.length} khách`;
      if (f >= 1 && list.some(c => c.reason === 'VERIFY_FAILED')) state = 'stop';
    }
    if (key === 'luu' && f >= 1) text = 'xong';
    return { state, text, f };
  }

  const HELD = new Set(['NO_EXACT_FIX', 'AMBIGUOUS_FIX', 'NOTHING_TO_WRITE', 'TOO_MANY_GROUPS', 'SHEET_SHUFFLED']);
  function gateMarks(run, t) {
    const decided = run.customers.filter(c => t >= c.decided);
    const held = decided.some(c => HELD.has(c.reason)), wrote = decided.some(c => c.wrote);
    const first = run.tooMany && t >= run.stages.chot.to ? 'held' : run.stages.chot.d && t >= run.stages.chot.to ? 'pass' : '';
    const second = held ? 'held' : wrote ? 'pass' : '';
    const failed = run.customers.some(c => c.reason === 'VERIFY_FAILED' && t >= c.done), checked = run.customers.some(c => c.reason === 'FIXED' && t >= c.done);
    const third = failed ? 'hit' : checked ? 'pass' : '';
    const mark = (state, mixed) => (!state ? '' : state === 'pass' ? '✓ ' : state === 'hit' ? '✕ ' : mixed ? '! ' : '■ ');
    return [first, second, third].map((state, index) => ({ state, mark: mark(state, index === 1 && held && wrote) }));
  }

  function sentence(run, t, cur) {
    const over = t >= run.sec && !run.live;
    if (over) {
      if (run.failed) return `Lượt ${clockOf(run.start).slice(0, 5)} dừng vì lỗi (${run.failReason ?? 'không rõ'}). Máy canh sẽ báo email.`;
      if (run.customers.some(c => c.reason === 'VERIFY_FAILED')) return 'Lượt xong, có lỗi: ghi xong đọc lại không khớp. Máy canh gửi email.';
      if (run.tooMany) return `Lượt xong, không ghi: ${run.different ?? 'nhiều'} khách lệch vượt ngưỡng.`;
      const wrote = run.fixed + run.created, left = run.total !== null && run.khop !== null ? run.total - run.khop : 0;
      return `Lượt xong lúc ${clockOf(run.end).slice(0, 5)}: ${run.khop ?? '—'}/${run.total ?? '—'} khớp${wrote ? `, máy đã ghi ${wrote} khách` : ', không ghi gì'}${left ? `, ${left} chờ người xem` : ''}.`;
    }
    const info = key => stationInfo(run, t, key, cur).text;
    switch (cur) {
      case 'tai': return 'Đang tải bản Sheet. Chỉ đọc.';
      case 'sach': return `Đang làm sạch tab khách${info('sach') ? `: ${info('sach')}` : ''}`;
      case 'doc': return `Đang đọc tổng từng sổ web: ${info('doc')}`;
      case 'so': return `Đang so tổng Sheet với web: ${info('so')}`;
      case 'chot': return 'Đang kiểm chốt 1: số khách lệch có vượt ngưỡng không.';
      case 'tim': return 'Đang tìm đúng một tổ hợp bằng số lệch.';
      case 'ghi': return 'Đang ghi vào sổ rồi đọc lại để kiểm.';
      case 'luu': return 'Đang lưu kết quả.';
      default: return run.live ? 'Lượt đang bắt đầu.' : '';
    }
  }

  function logLines(run, t) {
    const lines = [];
    const add = (at, text) => lines.push({ at, text });
    const ends = { tai: 'Tải xong bản Sheet. Chỉ đọc, không sửa gì trên Sheet.', sach: 'Làm sạch xong các tab khách.', doc: 'Đọc xong tổng từng sổ trên web.', luu: 'Lưu kết quả cho tab Việc cần làm.' };
    for (const key of ['tai', 'sach', 'doc', 'luu']) if (run.stages[key].d && t >= run.stages[key].to && (!run.live || key !== 'luu')) add(run.stages[key].to, ends[key]);
    if (run.stages.so.d && t >= run.stages.so.to) {
      const open = run.tooMany ? run.different : run.customers.length;
      add(run.stages.so.to, run.countsOnly ? `So xong: ${run.khop ?? '—'}/${run.total ?? '—'} khớp sau lượt.` : open ? `So xong: ${open} khách cần xét.` : 'So xong: khớp hết, không có việc gì để ghi.');
    }
    if (run.tooMany && t >= run.stages.chot.to) add(run.stages.chot.to, 'Chốt 1 chặn: quá nhiều khách lệch, có thể Sheet đang sửa hàng loạt. Lượt này không ghi.');
    return lines.sort((a, b) => b.at - a.at);
  }

  const withNames = (text, labelOf) => String(text ?? '').replace(/\bkh-(\d+)\b/gi, (whole, id) => labelOf(id) ?? whole);
  const taskCustomer = key => { const hit = /^kh-(\d+)/.exec(key); return hit ? hit[1] : null; };

  // Ba ca diễn tập chạy qua đúng đường vẽ, dữ liệu là giả và ghi rõ trên màn.
  function drill(kind) {
    const iso = s => `2000-01-15T${clockOf(s)}+07:00`;
    const base = 9 * 3600 + 300, segs = list => list.map(([stage, at]) => ({ stage, at: iso(base + at) }));
    const common = { state: 'done', mode: 'fix', started_at: iso(base), unlinked: {} };
    if (kind === 'many') return { ...fromTrace({ ...common, finished_at: iso(base + 292), too_many: true, different: 57, books: 239, counts: { KHOP: 182 }, segments: segs([['tai', 0], ['sach', 12], ['doc', 145], ['so', 270], ['chot', 278], ['luu', 287]]) }), drill: 'Hơn 40 khách lệch' };
    const customer = kind === 'two'
      ? { customer_id: 0, reason: 'AMBIGUOUS_FIX', decided_at: iso(base + 370) }
      : { customer_id: 0, reason: 'VERIFY_FAILED', decided_at: iso(base + 370), done_at: iso(base + 425), before_vnd: '120000000', after_vnd: '124000000', target_vnd: '129000000' };
    const list = kind === 'two' ? [['tai', 0], ['sach', 12], ['doc', 145], ['so', 270], ['chot', 278], ['tim', 280], ['luu', 445]] : [['tai', 0], ['sach', 12], ['doc', 145], ['so', 270], ['chot', 278], ['tim', 280], ['ghi', 410], ['luu', 445]];
    return { ...fromTrace({ ...common, finished_at: iso(base + 450), different: 1, books: 239, counts: { KHOP: 238 }, customers: { 0: customer }, segments: segs(list) }), drill: kind === 'two' ? 'Hai tổ hợp cùng khớp' : 'Đọc lại không khớp' };
  }

  return { ORDER, NAMES, RESULT, resultOf, secOfDay, clockOf, hhmm, money, millions, fromTrace, fromCounts, fromRow, slotKind, byDay, stageNow, stationInfo, gateMarks, sentence, logLines, withNames, taskCustomer, drill };
})();
if (typeof module !== 'undefined') module.exports = MayChayModel;
