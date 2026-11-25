/* Tab Máy chạy (MAY-CHAY-01): đổi dữ liệu của /api/v7/machine thành một lượt để vẽ, và tính trạng thái ở từng giây của lượt. Không đụng DOM.
 * Mọi thứ trên màn hình suy từ `run` và `t` (giây kể từ lúc lượt bắt đầu), nên tua tới, tua lùi, xem trực tiếp đều cùng một đường. */
const MayChayModel = (() => {
  'use strict';
  const ORDER = ['tai', 'sach', 'doc', 'so', 'chot', 'tim', 'ghi', 'luu'];
  const NAMES = { tai: 'Tải Sheet', sach: 'Làm sạch', doc: 'Đọc sổ web', so: 'So tổng', chot: 'Chốt 1', tim: 'Tìm cách sửa', ghi: 'Ghi và đọc lại', luu: 'Lưu kết quả' };
  // Nhịp đi lại của nhân vật khi xem trực tiếp, tính bằng giây. Chỉ để vẽ: trạm chưa xong thì không biết còn bao lâu, nên không suy ra tiến độ từ đây.
  const BEAT = { tai: 12, sach: 40, doc: 40, so: 8, chot: 4, tim: 40, ghi: 8, luu: 6 };
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
    DETAIL_DIFFERS: { tag: 'Không ghi', tone: 'warn', why: 'Tổng khớp Sheet nhưng Sheet còn khoản web chưa theo, cộng lại không bù đủ. Cần người xem.' },
    WEB_KEPT: { tag: 'Giữ web', tone: 'warn', why: 'Sheet sửa hoặc bỏ khoản web đã có. Web là sổ chính nên máy không sửa theo, chờ người quyết.' },
    HELD: { tag: 'Bị giữ', tone: 'warn', why: 'Tab đọc không được, khách này không đưa vào so. Cần người xem.' },
    WEB_AHEAD: { tag: 'Web đi trước', tone: 'info', why: 'Web có việc Sheet chưa có. Chênh đúng bằng phần đó, không cần ghi.' },
    CHI_CO_WEB: { tag: 'Chỉ báo', tone: 'warn', why: 'Có sổ trên web mà không thấy trên Sheet. Máy không tự xóa.' },
    WEB_BOOK: { tag: 'Sổ web', tone: 'info', why: 'Sổ tạo trên web (KHACH-WEB-01), không cần tab Sheet.' },
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
      const writing = Boolean(item.writing && !item.reason && !item.done_at);   // đang ghi dở, chỉ có khi xem trực tiếp
      const done = item.done_at ? secOfDay(item.done_at) - start : writing ? Infinity : decided;
      return { id: item.customer_id, reason: item.reason ?? null, info: item.reason ? info : writing ? { tag: 'Đang ghi', tone: 'ok' } : { tag: 'Đang xét', tone: 'info' }, wrote: Boolean(info.wrote && item.reason) || writing, before: item.before_vnd ?? null, after: item.after_vnd ?? null, target: item.target_vnd ?? null, difference: item.difference_vnd ?? null, decided, done, judged: Boolean(item.decided_at || item.reason) };
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
    const weights = [['tai', 11], ['sach', 250], ['doc', 29], ['so', 1], ...(touched ? [['chot', 1], ['tim', 154], ['ghi', 25]] : []), ['luu', 3]];
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
    if (!s.d) { if (!run.live && (passed || t >= run.sec)) state = 'skip'; }   // đang chạy thì chưa biết trạm sau có cần không
    else if (cur === key) state = 'run';
    else if (t >= s.to) state = 'done';
    if (state === 'skip') text = key === 'chot' ? 'không cần' : run.tooMany ? 'không chạy' : 'bỏ qua';
    if (key === 'tai' && f > 0) text = 'chỉ đọc';
    const elapsed = run.live && cur === key ? Math.floor(Math.max(t - s.from, 0)) : null;
    if (['sach', 'doc', 'so'].includes(key) && f > 0) {
      // Trạm đang chạy trực tiếp đếm theo job báo; xem lại thì suy theo thời gian của trạm.
      const reported = run.live && cur === key && run.count;
      const whole = reported ? run.count : run.total;
      if (whole) text = `${reported ? (run.done ?? 0) : Math.floor(f * whole)}/${whole}`;
      else if (elapsed !== null) text = duration(elapsed);   // job chưa báo được số đếm ở trạm này: chỉ nói số giây đã qua, không vẽ tỉ lệ giả
    }
    if (key === 'chot' && s.d && f >= 1) { text = run.tooMany ? 'dừng' : 'qua'; if (run.tooMany) state = 'stop'; }
    if (key === 'tim' && s.d && f > 0 && !run.countsOnly) text = run.live ? `${run.customers.filter(c => c.judged).length}/${Math.max(run.different ?? 0, run.customers.length)} khách` : `${run.customers.filter(c => t >= c.decided).length}/${run.customers.length} khách`;   // đang quét file: khách chưa vào danh sách nhưng job đã báo số lệch
    if (key === 'ghi' && s.d && f > 0 && !run.countsOnly) {
      const list = run.customers.filter(c => c.wrote);
      text = `${list.filter(c => t >= c.done).length}/${list.length} khách`;
      if (f >= 1 && list.some(c => c.reason === 'VERIFY_FAILED')) state = 'stop';
    }
    if (key === 'luu' && f >= 1) text = 'xong';
    return { state, text, f };
  }

  const HELD = new Set(['NO_EXACT_FIX', 'AMBIGUOUS_FIX', 'NOTHING_TO_WRITE', 'TOO_MANY_GROUPS', 'SHEET_SHUFFLED', 'DETAIL_DIFFERS', 'WEB_KEPT']);
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
      if (run.failed && run.failReason === 'MAT_TIN_HIEU') return `Lượt ${clockOf(run.start).slice(0, 5)} dừng giữa chừng: job không còn chạy mà chưa báo xong. Máy canh sẽ báo email.`;
      if (run.failed) return `Lượt ${clockOf(run.start).slice(0, 5)} dừng vì lỗi (${run.failReason ?? 'không rõ'}). Máy canh sẽ báo email.`;
      if (run.customers.some(c => c.reason === 'VERIFY_FAILED')) return 'Lượt xong, có lỗi: ghi xong đọc lại không khớp. Máy canh gửi email.';
      if (run.tooMany) return `Lượt xong, không ghi: ${run.different ?? 'nhiều'} khách lệch vượt ngưỡng.`;
      const wrote = run.fixed + run.created, left = run.total !== null && run.khop !== null ? run.total - run.khop : 0;
      return `Lượt xong lúc ${clockOf(run.end).slice(0, 5)}: ${run.khop ?? '—'}/${run.total ?? '—'} khớp${wrote ? `, máy đã ghi ${wrote} khách` : ', không ghi gì'}${left ? `, ${left} chờ người xem` : ''}.`;
    }
    const info = key => stationInfo(run, t, key, cur).text;
    switch (cur) {
      case 'tai': return 'Đang tải bản Sheet. Chỉ đọc.';
      case 'sach': return run.live ? 'Đang làm sạch các tab khách.' : `Đang làm sạch tab khách${info('sach') ? `: ${info('sach')}` : ''}`;
      case 'doc': return `Đang đọc tổng từng sổ web: ${info('doc')}`;
      case 'so': return run.live ? 'Đang so tổng Sheet với web.' : `Đang so tổng Sheet với web: ${info('so')}`;
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
      const open = run.tooMany ? run.different : Math.max(run.different ?? 0, run.customers.length);   // khách chỉ vào danh sách sau khi xét xong; số lệch job báo trước đó
      add(run.stages.so.to, run.countsOnly ? `So xong: ${run.khop ?? '—'}/${run.total ?? '—'} khớp sau lượt.` : open ? `So xong: ${open} khách cần xét.` : 'So xong: khớp hết, không có việc gì để ghi.');
    }
    if (run.tooMany && t >= run.stages.chot.to) add(run.stages.chot.to, 'Chốt 1 chặn: quá nhiều khách lệch, có thể Sheet đang sửa hàng loạt. Lượt này không ghi.');
    return lines.sort((a, b) => b.at - a.at);
  }

  // ----- Trực tiếp -----
  // Dòng trạng thái lúc đối soát nghỉ. Không có số giây đếm ngược ở đây vì dòng này được đọc cho trình đọc màn hình (aria-live).
  // `sheetOff` (WEB-CHINH-01): đã thôi dùng Sheet sổ nợ thì lượt mỗi giờ chỉ so booking, và số khớp Sheet của lượt cũ không nhắc nữa.
  function idleLine({ run, next, now, jobs, sheetOff = false }) {
    const day = String(now).slice(0, 10);
    const parts = [`${sheetOff ? 'So sổ với booking' : 'Đối soát'} đang nghỉ, ${next ? `lượt kế ${hhmm(next)}${String(next).slice(0, 10) === day ? '' : ' ngày mai'}` : 'chưa thấy lịch lượt kế'}.`];
    if (run && !sheetOff) {
      const label = `Lượt trước ${clockOf(run.start).slice(0, 5)}${run.day === day ? '' : ` ngày ${Number(run.day.slice(8))}/${Number(run.day.slice(5, 7))}`}`;
      const wrote = run.fixed + run.created, left = run.total !== null && run.khop !== null ? run.total - run.khop : 0;
      if (run.failed) parts.push(run.failReason === 'MAT_TIN_HIEU' ? `${label} dừng giữa chừng.` : `${label} dừng vì lỗi.`);
      else parts.push(`${label}: ${run.khop ?? '—'}/${run.total ?? '—'} khớp${wrote ? `, ghi ${wrote} khách` : ', không ghi gì'}${left ? `, ${left} chờ người xem` : ''}.`);
    }
    const busy = jobs.filter(job => job.state === 'running' && job.id !== 'reconcile').map(job => job.name);
    if (busy.length) parts.push(`${busy.join(', ')} đang chạy.`);
    const bad = jobs.filter(job => ['failed', 'late', 'off'].includes(job.state)).map(job => job.name);
    if (bad.length) parts.push(`Cần xem: ${bad.join(', ')}.`);
    return parts.join(' ');
  }

  const WROTE_AUTO = { price: ['Ghi giá', 'chuyến'], ps: ['Tách phụ phí', 'chuyến'], trip: ['Thêm chuyến', 'chuyến'], event_date: ['Điền ngày', 'chuyến'] };
  function autoCards(entries) {
    const groups = new Map();
    for (const entry of entries) {
      const kind = entry.kind ?? (entry.field === 'event_date' ? 'event_date' : 'text');
      const key = `${entry.customer_id}|${kind}`;
      if (!groups.has(key)) groups.set(key, { kind, id: entry.customer_id, list: [] });
      groups.get(key).list.push(entry);
    }
    return [...groups.values()].map(({ kind, id, list }) => {
      const [tag, unit] = WROTE_AUTO[kind] ?? ['Điền chữ', 'chỗ'];
      const pending = list.filter(entry => entry.pending).length, one = list.length === 1 ? list[0] : null;
      const amt = kind === 'price' && one ? `${money(one.before_unit_price_vnd)} → ${money(one.unit_price_vnd)}` : null;
      return { at: list.reduce((acc, entry) => (entry.at > acc ? entry.at : acc), ''), id, tag, tone: 'ok', amt, why: `${list.length} ${unit} theo Sheet${one?.container ? `, cont ${one.container}` : ''}${pending ? `; ${pending} chưa có giá nên chưa cộng nợ` : ''}.` };
    });
  }
  // Hôm nay máy đã đụng vào tiền của ai, cả qua lượt đối soát lẫn qua hộp chờ trong API; mới trước.
  function todayMoney(rows, auto, day) {
    const items = [...autoCards(auto ?? [])];
    let countsOnly = 0;
    for (const row of rows ?? []) {
      if (String(row.finished_at).slice(0, 10) !== day) continue;
      if (!row.detail) { countsOnly += (row.fixed ?? 0) + (row.created ?? 0); continue; }
      for (const item of Object.values(row.detail.customers ?? {})) {
        const info = resultOf(item.reason);
        if (!item.reason || !info.wrote) continue;
        items.push({ at: item.done_at ?? row.finished_at, id: item.customer_id, tag: info.tag, tone: info.tone, amt: item.before_vnd || item.after_vnd ? `${money(item.before_vnd)} → ${money(item.after_vnd)}` : null, why: item.reason === 'FIXED' ? 'Đúng một tổ hợp bằng số lệch. Đọc lại sổ: bằng đích.' : info.why });
      }
    }
    return { items: items.sort((a, b) => (a.at < b.at ? 1 : -1)), countsOnly };
  }

  const duration = seconds => { const s = Math.max(0, Math.round(seconds)); return s < 60 ? `${s} giây` : `${Math.floor(s / 60)} phút${s % 60 ? ` ${s % 60} giây` : ''}`; };
  // Một dòng nhật ký cho lần chạy gần nhất của job, theo giờ thật systemd báo.
  function jobEvent(job) {
    if (!job.started) return null;
    if (job.state === 'running' && !job.ended) return { key: `${job.id}@${job.started}`, at: job.started, text: `${job.name} đang chạy.` };
    if (!job.ended) return null;
    const took = duration((Date.parse(job.ended) - Date.parse(job.started)) / 1000);
    return { key: `${job.id}@${job.started}`, at: job.ended, text: job.state === 'failed' ? `${job.name} lỗi sau ${took}.` : `${job.name} xong, ${took}.`, bad: job.state === 'failed' };
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

  // ZALO-AGENT-01: nhóm "Máy Zalo", mỗi bộ xử lý một dòng câu thường. `zalo` là phần `zalo` của /api/v7/machine (chỉ mã, số, giờ).
  // Thứ tự ưu tiên của một dòng: không nghe máy > WeChat tắt/chờ đăng nhập (dòng WeChat) > Zalo chưa mở > Zalo mở mà chưa đọc được
  // > lỗi > WeChat im (đã đăng nhập mà quá ngưỡng chưa đọc được lượt nào) > không giải được ảnh (dòng WeChat) > chậm > đang đuổi kịp > bình thường.
  const ZALO_NAMES = { bundle: 'Gói chat', insurance: 'Bảo hiểm', money_images: 'Ảnh chuyển khoản', wechat: 'WeChat' };
  const TONE_RANK = { ok: 0, warn: 1, bad: 2 };
  // WECHAT-01: WeChat đọc kho riêng, không theo revision của Zalo: Zalo chưa mở không làm WeChat dừng, và "kịp tin mới" không đo được;
  // máy chủ gửi số tin đã nhập kho (`messages`, null là không rõ, không phải 0).
  // Khi máy Zalo báo: "đọc lần cuối" (lượt đọc THÀNH CÔNG gần nhất, không phải nhịp tim) và "tin mới nhất" (chỉ để xem: nhóm có thể im cả đêm).
  const ago = minutes => (minutes < 1 ? 'vừa xong' : minutes < 60 ? `${minutes} phút trước` : minutes < 48 * 60 ? `${Math.floor(minutes / 60)} giờ trước` : `${Math.floor(minutes / 1440)} ngày trước`);
  const lasted = minutes => (minutes < 60 ? `${minutes} phút` : `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`);
  function wechatText(item) {
    const parts = ['Đang chạy'];
    if (Number.isInteger(item.read_minutes)) parts.push(`đọc lần cuối ${ago(item.read_minutes)}`);
    if (Number.isInteger(item.newest_minutes)) parts.push(`tin mới nhất ${ago(item.newest_minutes)}`);
    if (Number.isInteger(item.messages)) parts.push(`${item.messages.toLocaleString('vi-VN')} tin đã nhập`);
    return parts.join(', ');
  }
  // WeChat quá ngưỡng (3 nhịp đọc, tối thiểu 15 phút, do máy chủ tính; từ lượt đọc cuối hoặc lúc agent chạy lại) chưa có lượt đọc thành công
  // nào: im, dù không có mã lỗi. Như máy canh: chỉ nhường cho câu về app khi câu đó đã quá 15 phút (app vừa đóng 3 phút thì vẫn nói im).
  const wechatSilent = item => item.id === 'wechat' && Number.isInteger(item.read_minutes)
    && item.read_minutes > (Number.isInteger(item.read_limit_minutes) ? item.read_limit_minutes : 15)
    && !(WECHAT_APP[item.app] && Number.isInteger(item.app_minutes) && item.app_minutes > 15);
  // App WeChat trên máy Zalo (đọc DB vẫn được khi WeChat tắt, nên phải nói riêng); `app_minutes` là số phút đã như vậy.
  const WECHAT_APP = { closed: 'Chưa mở trên máy Zalo', update: 'Đang chờ cập nhật, chưa mở lại trên máy Zalo', login: 'Chờ đăng nhập trên máy Zalo, xác nhận trên điện thoại' };
  const wechatApp = item => `${WECHAT_APP[item.app]}${Number.isInteger(item.app_minutes) && item.app_minutes > 0 ? ` (${item.app_minutes} phút)` : ''}`;
  // Zalo đã mở mà live-sync chưa lấy được khóa đọc tin (`reprobing`): lúc Zalo vừa mở thì chỉ thoáng qua, nên như dòng đầu trang Chat
  // và Thu chi, quá 5 phút mới nói (22/11/2026 kẹt hơn 18 giờ mà tab vẫn ghi "kịp tin mới").
  const ZALO_UNREAD_MINUTES = 5;
  function zaloLines(zalo) {
    if (!zalo || zalo.state === 'missing') return { tone: 'off', head: 'Chưa có máy Zalo báo về', rows: [] };
    const silent = zalo.state === 'silent';
    const unread = zalo.identity === 'reprobing' && Number.isInteger(zalo.quiet_minutes) && zalo.quiet_minutes >= ZALO_UNREAD_MINUTES
      ? `Zalo đã mở nhưng chưa đọc được tin, có thể đang chờ đăng nhập (${zalo.quiet_minutes.toLocaleString('vi-VN')} phút)` : '';
    const lost = zalo.at ? `Không nghe máy Zalo từ ${hhmm(zalo.at)}` : 'Không nghe máy Zalo';
    const rows = (zalo.processors ?? []).map(item => {
      const wechat = item.id === 'wechat';
      let text = wechat ? wechatText(item) : 'Đang chạy, kịp tin mới', tone = 'ok';
      if (silent) { text = lost; tone = 'bad'; }
      else if (wechatSilent(item) && item.state !== 'error') { text = `Im ${lasted(item.read_minutes)}: chưa đọc được lượt nào`; tone = 'warn'; }
      else if (wechat && WECHAT_APP[item.app]) { text = wechatApp(item); tone = 'warn'; }
      else if (zalo.identity === 'waiting_for_zalo' && !wechat) { text = 'Zalo chưa mở trên máy Zalo'; tone = 'warn'; }
      else if (unread && !wechat) { text = unread; tone = 'warn'; }
      else if (item.state === 'error') { text = `Gặp lỗi, mã: ${item.error}`; tone = 'bad'; }
      else if (wechat && item.images === 'no_key') { text = 'Đang chạy, không giải được ảnh'; tone = 'warn'; }
      else if (item.state === 'slow') { text = item.minutes === null ? 'Chậm, chưa xong lần nào' : `Chậm ${item.minutes} phút`; tone = 'warn'; }
      else if (item.state === 'catching_up') text = 'Đang đuổi kịp tin mới';
      return { id: item.id, name: ZALO_NAMES[item.id] ?? item.id, text, tone };
    });
    if (silent && !rows.length) rows.push({ id: 'agent', name: 'Máy Zalo', text: lost, tone: 'bad' });
    if (!silent && zalo.push_error) rows.push({ id: 'push', name: 'Đẩy lên máy chủ', text: `Gặp lỗi, mã: ${zalo.push_error}`, tone: 'bad' });
    const tone = rows.reduce((worst, row) => (TONE_RANK[row.tone] > TONE_RANK[worst] ? row.tone : worst), 'ok');
    const groups = zalo.selected_groups === null || zalo.selected_groups === undefined ? ''
      : zalo.selected_groups === 0 ? ' · chưa chọn nhóm nào' : ` · ${zalo.selected_groups} nhóm đã chọn`;
    return { tone, head: zalo.at ? `Máy Zalo báo lúc ${hhmm(zalo.at)}${groups}` : 'Máy Zalo không báo được', rows };
  }

  // ZALO-BOT-01: nhóm "Bot Zalo hỏi đáp". `bot` là phần `zalo_bot` của /api/v7/machine/now (mã, số, giờ; bộ đếm trong ngày giờ VN).
  // Chưa cài bot (`missing`) thì trả null và nhóm ẩn hẳn. Dòng nick phụ nói việc cần làm khi không nhận tin.
  const BOT_KENH = {
    online: ['Đang nhận tin', 'ok'], connecting: ['Đang nối', 'warn'], login_required: ['Cần quét QR đăng nhập lại', 'bad'],
    login_pending: ['Đang chờ quét QR', 'warn'], kicked: ['Bị phiên khác đá ra: có ai mở nick phụ trên Zalo Web hay Zalo PC?', 'bad'],
    offline: ['Kênh không nối với bộ não', 'bad'], error: ['Gặp lỗi', 'bad'], sandbox_missing: ['Không chạy: unit thiếu chặn mạng tới API', 'bad'],
    unknown: ['Không rõ trạng thái', 'warn'],
  };
  function botLines(bot) {
    if (!bot || bot.state === 'missing') return null;
    if (bot.state === 'silent') {
      return { tone: 'bad', head: bot.at ? `Không nghe bot Zalo từ ${hhmm(bot.at)}` : 'Không nghe bot Zalo',
        rows: [{ id: 'brain', name: 'Bộ não', text: 'Không ghi nhịp tim', tone: 'bad' }] };
    }
    const [state, tone] = BOT_KENH[bot.kenh] ?? BOT_KENH.unknown;
    const code = bot.kenh === 'error' && bot.kenh_code ? `, mã: ${bot.kenh_code}` : '';
    const minutes = bot.kenh !== 'online' && Number.isInteger(bot.kenh_minutes) && bot.kenh_minutes > 0 ? ` (${bot.kenh_minutes} phút)` : '';
    const rows = [{ id: 'kenh', name: 'Nick phụ', text: `${state}${code}${minutes}`, tone }];
    const count = key => (Number.isInteger(bot.counts?.[key]) ? bot.counts[key] : 0);
    if (!bot.enabled) rows.push({ id: 'tra-loi', name: 'Trả lời', text: 'Đang tắt', tone: 'warn' });
    else {
      const failed = count('error') + count('too_slow') + count('refused');
      const parts = [[count('answered'), 'câu đã trả lời'], [count('fixed'), 'câu trả câu cố định'], [count('not_sure'), 'câu chưa chắc'],
        [failed, 'câu lỗi'], [count('over_budget'), 'câu hết hạn mức']].filter(([n]) => n > 0).map(([n, label]) => `${n} ${label}`);
      const worry = count('not_sure') + failed + count('over_budget');
      rows.push({ id: 'tra-loi', name: 'Hôm nay', text: parts.length ? parts.join(', ') : 'Chưa có câu hỏi', tone: worry ? 'warn' : 'ok' });
    }
    if (count('stranger')) rows.push({ id: 'nguoi-la', name: 'Người lạ', text: `${count('stranger')} tin, bot không trả lời`, tone: 'ok' });
    if (bot.error) rows.push({ id: 'brain', name: 'Bộ não', text: `Gặp lỗi, mã: ${bot.error}`, tone: 'bad' });
    const worst = rows.reduce((acc, row) => (TONE_RANK[row.tone] > TONE_RANK[acc] ? row.tone : acc), 'ok');
    return { tone: worst, head: `Bot Zalo báo lúc ${hhmm(bot.at)}`, rows };
  }

  return { ORDER, NAMES, BEAT, zaloLines, botLines, idleLine, todayMoney, jobEvent, duration, RESULT, resultOf, secOfDay, clockOf, hhmm, money, millions, fromTrace, fromCounts, fromRow, slotKind, byDay, stageNow, stationInfo, gateMarks, sentence, logLines, withNames, taskCustomer, drill };
})();
if (typeof module !== 'undefined') module.exports = MayChayModel;
