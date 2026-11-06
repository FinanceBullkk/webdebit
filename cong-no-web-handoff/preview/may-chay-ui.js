/* Trang Máy chạy (MAY-CHAY-01): chỉ xem. Đọc /api/v7/machine, vẽ văn phòng, danh sách việc đụng vào tiền, bảng việc của Hermes, các lượt, lịch job.
 * Mở ra là trực tiếp: đồng hồ theo giờ máy chủ, nhân viên chỉ cử động khi job đó thật sự chạy. Xem lại là việc người xem tự bấm, có nút về trực tiếp.
 * Mất kết nối thì báo và đứng yên, không vẽ tiếp. */
(() => {
  'use strict';
  const M = MayChayModel, F = CongNoFormat, $ = id => document.getElementById(id);
  const esc = F.esc;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const POLL_LIVE = 2000, POLL_HIDDEN = 30000, FETCH_TIMEOUT = 8000, STALE_SECONDS = 15, STAGE_PAD = 20, PAINT_GAP = 500, FEED_KEPT = 60, FEED_SHOWN = 40;
  const WHO = {
    hermes: ['Hermes, quản lý', 'Chỉ đọc', 'Nhân viên duy nhất là AI; các nhân viên khác là script chạy theo luật. Chỉ đọc bản tóm tắt có mã khách và số đếm, gom việc thành thẻ cho chủ sổ. Không có chìa khóa phòng ghi và không có đường nào để ghi sổ. Lượt không có gì mới thì không gọi AI.'],
    tai: ['Tải Sheet', 'Chỉ đọc', 'Tải bản xlsx của sổ gốc từ Google với quyền chỉ đọc. Bản tải bị xóa ngay sau lượt.'],
    sach: ['Làm sạch', 'Chỉ đọc', 'Làm sạch từng tab đúng như đối soát chính thức. Tab đọc không được thì khách đó bị giữ lại, không đưa vào so.'],
    doc: ['Đọc sổ web', 'Chỉ đọc', 'Đọc tổng còn nợ của từng sổ trên web, đi từng sổ một.'],
    so: ['So tổng', 'Chỉ đọc', 'So tổng Sheet với tổng web của từng khách, tới từng đồng. Khớp thì xong, lệch thì đưa sang chốt.'],
    chot: ['Chốt 1', 'Không ghi', 'Quá nhiều khách lệch cùng lúc thì có thể Sheet đang sửa hàng loạt hoặc bản tải có vấn đề. Cả lượt chỉ báo, không ghi gì.'],
    tim: ['Tìm cách sửa', 'Không ghi', 'Gom việc đang chờ thành từng nhóm (phiếu thu, giá) rồi tìm đúng một tổ hợp bằng đúng số lệch. Không có, hoặc có hơn một tổ hợp, thì không ghi.'],
    ghi: ['Ghi và đọc lại', 'Ghi vào sổ', 'Bàn duy nhất được ghi vào sổ, tên người ghi là Máy (theo Sheet). Ghi xong đọc lại sổ, tổng phải bằng đích; không bằng thì báo lỗi.'],
    luu: ['Lưu kết quả', 'Không đụng sổ', 'Lưu kết quả cho tab Việc cần làm, thêm một dòng vào sổ theo dõi.'],
  };
  const JOB_WHO = { sheet: ['Bản chụp Sheet', 'Chỉ đọc'], prices: ['Giá Sheet', 'Chỉ đọc'], ps: ['Phí PS', 'Chỉ đọc'], watchdog: ['Máy canh', 'Chỉ đọc'], 'backup-hourly': ['Sao lưu giờ', 'Không đụng sổ'] };
  const JOB_STATE = { ok: 'Bình thường', running: 'Đang chạy', late: 'Trễ lịch', failed: 'Lần trước lỗi', off: 'Đang tắt', unknown: '—' };

  const state = {
    data: null, labels: new Map(), mode: 'live', run: null, t: 0, playing: false, speed: 10, camOn: true, selected: null, tab: 'money', day: null,
    offline: false, seenAt: 0, wall: 0, lastFrame: 0, lastTick: 0, cardsKey: null, tasksKey: null, jobsKey: null, feed: new Map(), feedHtml: null, liveHtml: null, paintedAt: 0, fullFinished: null, wasRunning: false,
  };
  const office = MayChayOffice.create($('office'), { reduce, onPick: key => openWho(key) });
  office.onRedraw(() => draw());
  const labelOf = id => state.labels.get(String(id));

  // ----- Thời gian -----
  // Giờ máy chủ cộng thời gian từ lần đọc cuối. Không đọc được quá lâu thì đồng hồ dừng ở đó, không chạy tiếp bằng đồng hồ của trình duyệt.
  const sinceSeen = () => Math.min((performance.now() - state.seenAt) / 1000, STALE_SECONDS);
  const nowSec = () => M.secOfDay(state.data.now) + sinceSeen();
  const liveTime = () => Math.max(nowSec() - state.run.start, 0);
  const isRunning = () => state.data?.run?.state === 'running';

  // Lượt để hiện khi xem trực tiếp: đang chạy thì theo tín hiệu; không thì kết quả lượt gần nhất.
  function setLiveRun() {
    const trace = state.data?.run, rows = state.data?.runs ?? [], last = rows[rows.length - 1];
    if (trace?.state === 'running') {
      const run = M.fromTrace(trace);
      run.sec = Math.max(M.secOfDay(state.data.now) - run.start, 1);
      if (run.stage && run.stages[run.stage]) {   // trạm đang chạy kéo dài theo thời gian thật, đoạn cuối chưa có mốc kết thúc
        run.stages[run.stage].to = run.sec + STAGE_PAD;
        run.stages[run.stage].d = Math.max(run.stages[run.stage].to - run.stages[run.stage].from, 0.001);
      }
      state.run = run;
      return;
    }
    // Lượt chết giữa chừng không có dòng trong sổ theo dõi, và lượt vừa xong có thể chưa kịp đọc lại danh sách.
    const newer = trace?.finished_at && (!last || trace.finished_at > last.finished_at);
    state.run = newer ? M.fromTrace(trace) : last ? M.fromRow(last) : null;
    state.t = state.run?.sec ?? 0;
  }

  // ----- Chọn lượt -----
  function pick(run, { play = false } = {}) {
    state.mode = run.drill ? 'drill' : 'replay'; state.day = null; state.run = run;
    state.t = play && !reduce ? 0 : run.sec; state.playing = play && !reduce; state.cardsKey = null;
    paintSlots(); draw();
  }
  function goLive() {
    state.mode = 'live'; state.day = null; state.playing = false; state.liveHtml = null; state.feedHtml = null;
    setLiveRun(); paintSlots(); draw();
  }
  function startDay(entry) {
    const runs = [...entry.runs].sort((a, b) => a.start - b.start), first = runs[0], lastRun = runs[runs.length - 1];
    state.day = { label: entry.label, runs, from: Math.min(first.start - 420, 7 * 3600 - 420), to: lastRun.start + lastRun.sec + 420, clock: 0, idle: true, next: null };
    state.day.clock = state.day.from;
    state.mode = 'day'; state.playing = !reduce; state.cardsKey = null;
    syncDay(); draw();
  }
  function syncDay() {
    const day = state.day;
    const active = day.runs.find(run => day.clock >= run.start && day.clock < run.start + run.sec);
    const done = day.runs.filter(run => run.start + run.sec <= day.clock).pop();
    const target = active ?? done ?? day.runs[0];
    if (target !== state.run) { state.run = target; state.cardsKey = null; paintSlots(); }
    day.idle = !active;
    day.next = day.runs.find(run => run.start > day.clock)?.start ?? null;
    state.t = active ? day.clock - active.start : done ? target.sec : 0;
  }
  // Cả ngày: nhanh lúc máy nghỉ, chậm trong lượt, chậm nhất lúc đụng vào tiền.
  function dayRate(cur) {
    const f = state.speed / 10;
    if (state.day.idle) return 600 * f;
    return (cur === 'ghi' || (cur === 'luu' && state.run.customers.some(item => item.wrote)) ? 10 : cur === 'tim' ? 30 : 60) * f;
  }

  // ----- Vẽ -----
  function jobsById() { return new Map((state.data?.jobs ?? []).map(job => [job.id, job])); }
  // Xem lại: job khác chạy theo lịch, chưa có log từng lần; trực tiếp thì theo systemd.
  function scheduleActive(id, clock) {
    const s = Math.floor(clock), h = Math.floor(s / 3600) % 24, m = Math.floor(s / 60) % 60, span = state.mode === 'day' ? 200 : 0;
    const secOfMinute = s % 60;
    const match = (mm, hh) => ({ sheet: mm % 15 === 0, prices: mm % 15 === 0, ps: mm % 15 === 0, watchdog: mm % 15 === 2, 'backup-hourly': mm === 0 && hh >= 6 && hh <= 22 })[id];
    if (match(m, h)) return secOfMinute < Math.max({ sheet: 4, prices: 13, ps: 8, watchdog: 6, 'backup-hourly': 11 }[id], span);
    if (span > 60) { const pm = (m + 59) % 60, ph = pm === 59 ? (h + 23) % 24 : h; return match(pm, ph) && secOfMinute < span - 60; }
    return false;
  }

  function draw() {
    const run = state.run;
    if (!run) { paintEmpty(); return; }
    const live = state.mode === 'live', running = live && run.live;
    const t = running ? liveTime() : state.t, cur = M.stageNow(run, t), over = t >= run.sec && !run.live;
    const clock = state.mode === 'day' ? state.day.clock : live ? nowSec() : run.start + Math.min(t, run.sec);
    const jobs = jobsById(), next = jobs.get('reconcile')?.next;
    const hermes = run.drill ? { state: 'idle', tasks: {} } : state.data?.office ?? { state: 'off', tasks: {} };
    const idleNext = state.mode === 'day' && state.day.idle ? (state.day.next ? `Máy nghỉ, lượt kế ${M.clockOf(state.day.next).slice(0, 5)}` : 'Hết lượt trong ngày')
      : live && !running ? (next ? `Máy nghỉ, lượt kế ${M.hhmm(next)}` : 'Máy nghỉ') : '';
    office.draw({
      run, t, cur, clock, wall: state.wall, labelOf, hermes, idleNext, camOn: state.camOn && (running || !live), sideBubbles: live,
      rate: state.mode === 'day' ? dayRate(cur) : live ? 1 : state.speed,
      jobActive: id => (live ? jobs.get(id)?.state === 'running' : scheduleActive(id, clock)),
      jobState: id => (live ? jobs.get(id)?.state : null),
    });
    paintStatus(run, t, cur, over);
    if (live) paintLive(run, t); else paintCards(run, t, over);
    paintTasks();
    if (state.selected) paintWhoState(run, t, cur);
  }

  function setText(id, value) { const node = $(id); if (node.textContent !== value) node.textContent = value; }

  function paintEmpty() {
    setText('now', state.offline ? 'Mất kết nối máy chủ.' : state.data ? M.idleLine({ run: null, next: jobsById().get('reconcile')?.next, now: state.data.now, jobs: state.data.jobs ?? [] }) : 'Đang tải…');
    setText('run-title', 'Máy chạy');
    paintPill();
  }

  function paintPill() {
    const live = state.mode === 'live', pill = $('live-pill');
    const busy = live && (isRunning() || (state.data?.jobs ?? []).some(job => job.state === 'running'));
    const [kind, label] = live ? (state.offline ? ['lost', 'Mất tín hiệu'] : [busy ? 'busy' : '', 'Trực tiếp']) : ['replay', state.run?.drill ? 'Diễn tập' : 'Đang xem lại'];
    pill.className = `live-pill ${kind}`;
    setText('live-pill', label);
  }

  function countdown(next) {
    if (!next) return '';
    const left = Math.floor((Date.parse(next) - Date.parse(state.data.now)) / 1000 - sinceSeen());
    if (left <= 0) return 'lượt kế sắp chạy';
    const h = Math.floor(left / 3600), m = Math.floor(left / 60) % 60, s = left % 60;
    return h ? `lượt kế còn ${h} giờ ${m} phút` : `lượt kế còn ${m}:${String(s).padStart(2, '0')}`;
  }

  function paintStatus(run, t, cur, over) {
    const live = state.mode === 'live', running = live && run.live, idle = state.mode === 'day' && state.day.idle;
    const jobs = state.data?.jobs ?? [], next = jobsById().get('reconcile')?.next;
    let line;
    if (state.offline) line = 'Mất kết nối máy chủ. Số dưới đây có thể cũ, hình đứng yên.';
    else if (live && !running) line = M.idleLine({ run, next, now: state.data.now, jobs });
    else if (idle) {
      const done = state.day.runs.filter(item => item.start + item.sec <= state.day.clock).pop();
      line = `${state.day.next ? `Máy đang nghỉ. Lượt kế lúc ${M.clockOf(state.day.next).slice(0, 5)}.` : 'Hết lượt trong ngày.'}${done ? ` Lượt trước: ${done.khop ?? '—'}/${done.total ?? '—'} khớp.` : ''}`;
    } else line = M.sentence(run, t, cur);
    setText('now', line);
    const bad = state.offline || run.failed || run.tooMany || run.customers.some(item => item.info.tone === 'bad') || (live && jobs.some(job => ['failed', 'late', 'off'].includes(job.state)));
    const busy = live ? running || jobs.some(job => job.state === 'running') : !over;
    $('lamp').className = `lamp ${idle ? '' : busy && !state.offline ? 'run' : bad ? 'bad' : run.khop !== null && run.total !== null && run.khop < run.total ? 'warn' : 'ok'}`;
    $('status').classList.toggle('drill', Boolean(run.drill));
    const dayText = run.day === (state.data?.now ?? '').slice(0, 10) ? 'hôm nay' : `${Number(run.day.slice(8))}/${Number(run.day.slice(5, 7))}`;
    const startText = `${M.clockOf(run.start).slice(0, 5)} ${dayText}`;
    setText('run-title', run.drill ? `Diễn tập: ${run.drill} (giả lập)` : state.mode === 'day' ? `Cả ngày ${state.day.label}` : running ? `Đang chạy lượt ${startText}` : live ? `Đang nghỉ, số của lượt ${startText}` : `Lượt ${startText}`);
    setText('clock', state.offline && live ? '' : state.mode === 'day' ? M.clockOf(state.day.clock) : running ? `đã chạy ${M.duration(t)}` : live ? countdown(next) : `${Math.floor(Math.min(t, run.sec))}/${run.sec}s${run.estimated ? ' ước tính' : ''}`);
    const scrub = $('scrub');
    scrub.hidden = live; $('speed').hidden = live; $('play').hidden = live;
    if (!live) {
      scrub.value = state.mode === 'day' ? Math.round(((state.day.clock - state.day.from) / (state.day.to - state.day.from)) * 1000) : Math.round((Math.min(t, run.sec) / run.sec) * 1000);
      setText('play', state.playing ? 'Dừng' : (state.mode === 'day' ? state.day.clock >= state.day.to : over) ? 'Phát lại' : 'Phát');
    }
    $('go-live').hidden = live;
    setText('go-live', isRunning() ? 'Đang chạy: xem trực tiếp' : 'Về trực tiếp');
    paintPill();
  }

  // Thẻ của một lượt ở giây t: dùng chung cho xem lại và phần đang chạy của xem trực tiếp.
  function runCards(run, t) {
    const seen = run.customers.filter(item => t >= item.decided);
    const name = item => (run.drill ? 'Khách A' : labelOf(item.id) ?? `Sổ ${item.id}`);
    const cards = [];
    if (run.tooMany && t >= run.stages.chot.to) cards.push(`<div class="card"><span class="tag t-bad">Dừng</span><b>${esc(run.different ?? 'Nhiều')} khách lệch</b><div class="why">Vượt ngưỡng. Máy không ghi khách nào, chỉ báo ở Việc cần làm.</div></div>`);
    for (const item of seen) {
      const pending = item.wrote && t < item.done, info = item.info;
      let body;
      if (pending) body = '<div class="why">Đã chọn được tổ hợp, đang ghi...</div>';
      else if (item.reason === 'FIXED') body = `<div class="amt">${M.money(item.before)} → ${M.money(item.after)}</div><div class="why">Đúng một tổ hợp bằng số lệch. Đọc lại sổ: bằng đích.</div>`;
      else if (item.reason === 'VERIFY_FAILED') body = `<div class="amt">${M.money(item.before)} → ${M.money(item.after)}</div><div class="why">Đích phải là ${M.money(item.target)}. ${esc(info.why)}</div>`;
      else body = `${item.difference ? `<div class="amt">Lệch ${M.money(item.difference)}</div>` : ''}<div class="why">${esc(info.why ?? '')}</div>`;
      const title = run.drill ? esc(name(item)) : `<a href="/so-khach-v7-live.html?customer=${encodeURIComponent(item.id)}">${esc(name(item))}</a>`;
      cards.push(`<div class="card"><span class="tag t-${pending ? 'ok' : info.tone}">${pending ? 'Đang ghi' : esc(info.tag)}</span><b>${title}</b>${body}</div>`);
    }
    for (const [reason, count] of Object.entries(run.unlinked ?? {})) {
      if (t >= run.stages.so.to) cards.push(`<div class="card"><span class="tag t-${M.resultOf(reason).tone}">${esc(M.resultOf(reason).tag)}</span><b>${esc(count)} khách chưa có sổ</b><div class="why">${esc(M.resultOf(reason).why ?? 'Có trên Sheet, chưa có sổ web.')}</div></div>`);
    }
    return cards;
  }

  // Trực tiếp: phần đang chạy ở trên, dưới là mọi việc hôm nay máy đã đụng vào tiền, rồi nhật ký theo giờ thật.
  function paintLive(run, t) {
    const at = performance.now();
    if (state.liveHtml !== null && at - state.paintedAt < PAINT_GAP) return;
    state.paintedAt = at;
    const day = (state.data?.now ?? '').slice(0, 10);
    const money = M.todayMoney(state.data?.runs, state.data?.auto, day);
    const today = money.items.map(item => `<div class="card"><span class="tag t-${esc(item.tone)}">${esc(item.tag)}</span><b><a href="/so-khach-v7-live.html?customer=${encodeURIComponent(item.id)}">${esc(labelOf(item.id) ?? `Sổ ${item.id}`)}</a></b>${item.amt ? `<div class="amt">${esc(item.amt)}</div>` : ''}<div class="why">${esc(M.hhmm(item.at))} · ${esc(item.why ?? '')}</div></div>`);
    const parts = [...(run.live ? runCards(run, t) : []), `<div class="today-head">${today.length ? `Hôm nay máy đã ghi ${today.length} việc` : 'Hôm nay máy chưa ghi gì vào sổ'}</div>`, ...today];
    if (money.countsOnly) parts.push(`<div class="none">Lượt cũ hôm nay còn ${money.countsOnly} khách đã ghi, chỉ lưu số đếm.</div>`);
    const html = parts.join('');
    if (html !== state.liveHtml) { $('cards').innerHTML = html; state.liveHtml = html; }
    const isoOf = sec => `${run.day}T${M.clockOf(run.start + sec)}+07:00`;
    const own = !run.live ? [] : [...M.logLines(run, t).map(item => ({ at: isoOf(item.at), text: item.text })),
      ...run.customers.filter(item => t >= item.done && item.reason).map(item => ({ at: isoOf(item.done), text: `${labelOf(item.id) ?? `Sổ ${item.id}`}: ${(item.info.tag ?? '').toLowerCase()}.` }))];
    const lines = [...own, ...state.feed.values()].sort((a, b) => (a.at < b.at ? 1 : -1)).slice(0, FEED_SHOWN);
    const feed = lines.map(item => `<li${item.bad ? ' class="bad"' : ''}><time>${esc(String(item.at).slice(11, 19))}</time><span>${esc(item.text)}</span></li>`).join('');
    if (feed !== state.feedHtml) { $('log').innerHTML = feed; state.feedHtml = feed; }
  }

  function paintCards(run, t, over) {
    const lines = M.logLines(run, t);
    const seen = run.customers.filter(item => t >= item.decided);
    const key = [run.id, seen.map(item => `${item.id}${t >= item.done ? 1 : 0}`).join(), lines.length, run.tooMany && t >= run.stages.chot.to, over].join('|');
    if (key === state.cardsKey) return;
    state.cardsKey = key; state.liveHtml = null; state.feedHtml = null;
    const name = item => (run.drill ? 'Khách A' : labelOf(item.id) ?? `Sổ ${item.id}`);
    const cards = runCards(run, t);
    if (run.countsOnly) cards.push(`<div class="none">Lượt này trước khi có tín hiệu từng bước nên chỉ còn số đếm: sửa ${run.fixed}, tạo sổ ${run.created}. Thời lượng từng trạm là ước tính.</div>`);
    else if (!cards.length) cards.push(`<div class="none">${over ? 'Lượt này máy không ghi gì vào sổ.' : 'Chưa có gì. Trạm Ghi chỉ chạy khi có khách lệch.'}</div>`);
    $('cards').innerHTML = cards.join('');
    const merged = [...lines, ...run.customers.filter(item => t >= item.done && item.reason).map(item => ({ at: item.done, text: `${name(item)}: ${(item.info.tag ?? '').toLowerCase()}.` }))].sort((a, b) => b.at - a.at);
    $('log').innerHTML = merged.map(item => `<li><time>${M.clockOf(run.start + item.at)}</time><span>${esc(item.text)}</span></li>`).join('');
  }

  function paintTasks() {
    const office2 = state.data?.office ?? { state: 'off', tasks: {} };
    const items = Object.entries(office2.tasks ?? {});
    const badge = $('task-n');
    badge.textContent = items.length || '';
    badge.className = items.some(([, task]) => task.level === 'urgent') ? 'urgent' : items.length ? 'has' : '';
    const key = JSON.stringify([office2.state, office2.updated_at, items, state.labels.size]);
    if (key === state.tasksKey) return;
    state.tasksKey = key;
    const named = text => esc(M.withNames(text, labelOf));
    const cls = { urgent: 't-bad', warn: 't-warn', info: 't-new' }, tag = { urgent: 'Gấp', warn: 'Cần xem', info: 'Ghi chú' };
    const rows = items.map(([id, task]) => {
      const customer = M.taskCustomer(id);
      const title = customer ? `<a href="/so-khach-v7-live.html?customer=${encodeURIComponent(customer)}">${named(task.title)}</a>` : named(task.title);
      return `<div class="card"><span class="tag ${cls[task.level] ?? 't-new'}">${tag[task.level] ?? 'Ghi chú'}</span><b>${title}</b><div class="why">${named(task.body)}</div></div>`;
    });
    const updated = office2.updated_at ? `Hermes cập nhật lúc ${M.hhmm(office2.updated_at)} ngày ${Number(office2.updated_at.slice(8, 10))}/${Number(office2.updated_at.slice(5, 7))}. Thẻ do AI viết, cần chủ sổ xem lại.` : 'Hermes chưa chạy lần nào.';
    $('tasks').innerHTML = `<div class="mock">${esc(updated)}</div>${rows.join('') || '<div class="none">Chưa có việc cần giao. Lượt không có gì mới thì quản lý không gọi AI.</div>'}`;
  }

  function paintSlots() {
    const rows = state.data?.runs ?? [], today = (state.data?.now ?? '').slice(0, 10), running = isRunning();
    const days = M.byDay(rows);
    if (running && !days.some(entry => entry.day === today)) days.unshift({ day: today, runs: [], fixed: 0, created: 0, label: `${Number(today.slice(8))}/${Number(today.slice(5, 7))}` });
    const shown = days.slice(0, 3);
    const nowSlot = entry => (running && entry.day === today ? `<button type="button" class="slot now" data-live="1" aria-current="${state.mode === 'live' ? 'true' : 'false'}">${M.hhmm(state.data.run.started_at)} đang chạy</button>` : '');
    $('days').innerHTML = shown.map((entry, dayIndex) => `<div class="day"><div class="day-name">${entry.runs.length ? `<button class="ctrl whole" type="button" data-day="${dayIndex}">Tua cả ngày</button>` : ''}<span><b>${esc(entry.label)}</b> · ${entry.runs.length} lượt · sửa ${entry.fixed}${entry.created ? `, tạo ${entry.created}` : ''}</span></div>`
      + entry.runs.map((run, index) => {
        const title = `Xong ${M.clockOf(run.end)}: ${run.khop ?? '—'}/${run.total ?? '—'} khớp, sửa ${run.fixed}, tạo sổ ${run.created}${run.countsOnly ? '. Chỉ có số đếm' : ''}`;
        const offSchedule = run.countsOnly && run.onSchedule === false;
        return `<button type="button" class="slot ${M.slotKind(run)}${offSchedule ? ' offs' : ''}" data-day="${dayIndex}" data-run="${index}" title="${esc(title)}" aria-label="${esc(title)}" aria-current="${state.run?.id === run.id ? 'true' : 'false'}">${M.clockOf(run.start).slice(0, 5)}</button>`;
      }).join('') + nowSlot(entry) + '</div>').join('') || '<p class="none">Chưa có lượt nào trong sổ theo dõi.</p>';
    state.shownDays = shown;
  }

  function paintJobs() {
    const jobs = state.data?.jobs ?? [], key = JSON.stringify(jobs);
    if (key === state.jobsKey) return;
    state.jobsKey = key;
    $('jobs-body').innerHTML = jobs.map(job => `<tr class="job-${esc(job.state)}"><td>${esc(job.name)}</td><td>${esc(job.does)}</td><td>${esc(job.every)}</td><td>${job.last ? esc(`${M.hhmm(job.last)} ${Number(job.last.slice(8, 10))}/${Number(job.last.slice(5, 7))}`) : '—'}</td><td>${job.next ? esc(`${M.hhmm(job.next)} ${Number(job.next.slice(8, 10))}/${Number(job.next.slice(5, 7))}`) : '—'}</td><td>${esc(JOB_STATE[job.state] ?? job.state)}</td></tr>`).join('');
  }

  // ----- Thẻ nhân viên -----
  function openWho(key) {
    state.selected = key;
    office.select(key);
    $('who').hidden = !key;
    $('who-pick').value = key ?? '';
    if (!key) return;
    const jobId = key.startsWith('job-') ? key.slice(4) : null;
    const job = jobId ? jobsById().get(jobId) : null;
    const [name, badge, body] = jobId ? [...(JOB_WHO[jobId] ?? [jobId, '']), job ? `${job.does}. ${job.every}.` : ''] : WHO[key];
    $('who-name').textContent = name; $('who-badge').textContent = badge; $('who-badge').className = `tag ${badge === 'Ghi vào sổ' ? 't-bad' : 't-new'}`; $('who-body').textContent = body;
    draw();
  }
  function paintWhoState(run, t, cur) {
    const key = state.selected;
    if (key === 'hermes') { const office2 = state.data?.office; $('who-state').textContent = office2?.state === 'working' ? 'Đang đọc tóm tắt' : office2?.state === 'off' ? 'Chưa chạy' : `${Object.keys(office2?.tasks ?? {}).length} thẻ đang mở`; return; }
    if (key.startsWith('job-')) { $('who-state').textContent = JOB_STATE[jobsById().get(key.slice(4))?.state] ?? '—'; return; }
    const info = M.stationInfo(run, t, key, cur);
    $('who-state').textContent = `${({ run: 'Đang chạy', done: 'Đã xong trong lượt này', skip: 'Lượt này không cần', stop: 'Đã dừng' })[info.state] ?? 'Chưa tới lượt'}${info.text && info.state !== 'skip' ? ` · ${info.text}` : ''}`;
  }

  // ----- Đọc API -----
  async function loadCustomers() {
    try {
      const response = await fetch('/api/v7/customers', { cache: 'no-store' });
      if (!response.ok) return;
      const body = await response.json();
      globalThis.AppNav?.setCustomers(body.customers ?? []);
      state.labels = F.customerLabels(body.customers ?? []);
      state.cardsKey = null; state.tasksKey = null; state.liveHtml = null; state.feedHtml = null;
    } catch { /* không có tên thì hiện "Sổ <id>" */ }
  }
  function rememberJobRuns() {
    for (const job of state.data.jobs ?? []) {
      const event = M.jobEvent(job);
      if (event) state.feed.set(event.key, event);
    }
    while (state.feed.size > FEED_KEPT) state.feed.delete([...state.feed.values()].sort((a, b) => (a.at < b.at ? -1 : 1))[0].key);
  }
  // Trả true khi có lượt vừa xong mà danh sách các lượt chưa có: cần đọc lại bản đầy đủ.
  function applyData(body, full) {
    state.data = full ? body : { ...state.data, ...body };
    state.seenAt = performance.now();
    state.offline = false;
    rememberJobRuns();
    paintJobs();
    const running = isRunning(), finished = state.data.run?.finished_at ?? null;
    if (full) state.fullFinished = finished;
    if (state.mode === 'live') setLiveRun();
    if (full || running !== state.wasRunning) paintSlots();
    state.wasRunning = running;
    return !full && finished !== null && finished !== state.fullFinished;
  }
  let timer = null;
  async function poll(full = false) {
    clearTimeout(timer);
    if (document.hidden && !full) { timer = setTimeout(poll, POLL_HIDDEN); return; }
    try {
      const response = await fetch(full ? '/api/v7/machine' : '/api/v7/machine/now', { cache: 'no-store', signal: AbortSignal.timeout(FETCH_TIMEOUT) });
      if (!response.ok) throw new Error(String(response.status));
      if (applyData(await response.json(), full)) { await poll(true); return; }
    } catch {
      state.offline = true;
    }
    draw();
    timer = setTimeout(poll, POLL_LIVE);
  }

  // ----- Vòng khung hình -----
  function frame(now) {
    const dt = state.lastFrame ? Math.min(now - state.lastFrame, 200) : 0;
    state.lastFrame = now; state.wall = now;
    const live = state.mode === 'live';
    const moving = live && !state.offline && !document.hidden && (state.run?.live || (state.data?.jobs ?? []).some(job => job.state === 'running'));
    const working = state.data?.office?.state === 'working';
    if (state.playing && state.run) {
      if (state.mode === 'day') {
        state.day.clock += (dt / 1000) * dayRate(M.stageNow(state.run, state.t));
        if (state.day.clock >= state.day.to) { state.day.clock = state.day.to; state.playing = false; }
        syncDay();
      } else {
        state.t += (dt / 1000) * state.speed;
        if (state.t >= state.run.sec) { state.t = state.run.sec; state.playing = false; }
      }
      draw();
    } else if (moving || working) draw();
    else if (live && state.data && now - state.lastTick >= 1000) { state.lastTick = now; draw(); }   // máy nghỉ: chỉ đồng hồ và đếm ngược đổi, mỗi giây một lần là đủ
    requestAnimationFrame(frame);
  }

  // ----- Điều khiển -----
  $('play').addEventListener('click', () => {
    if (!state.run) return;
    if (state.mode === 'day') { if (state.day.clock >= state.day.to) state.day.clock = state.day.from; syncDay(); } else if (state.t >= state.run.sec) { state.t = 0; state.cardsKey = null; }
    state.playing = !state.playing; draw();
  });
  $('speed').addEventListener('change', event => { state.speed = Number(event.target.value); });
  $('scrub').addEventListener('input', event => {
    if (!state.run) return;
    state.playing = false; state.cardsKey = null;
    if (state.mode === 'day') { state.day.clock = state.day.from + (event.target.value / 1000) * (state.day.to - state.day.from); syncDay(); }
    else state.t = (event.target.value / 1000) * state.run.sec;
    draw();
  });
  $('cam').addEventListener('click', () => { state.camOn = !state.camOn; $('cam').setAttribute('aria-pressed', String(state.camOn)); $('cam').textContent = `Máy quay: ${state.camOn ? 'bật' : 'tắt'}`; draw(); });
  $('who-pick').addEventListener('change', event => openWho(event.target.value || null));
  $('who-close').addEventListener('click', () => openWho(null));
  $('go-live').addEventListener('click', goLive);
  const showTab = which => { $('tab-money').setAttribute('aria-pressed', String(which === 'money')); $('tab-tasks').setAttribute('aria-pressed', String(which === 'tasks')); $('money-box').hidden = which !== 'money'; $('tasks-box').hidden = which !== 'tasks'; };
  $('tab-money').addEventListener('click', () => showTab('money'));
  $('tab-tasks').addEventListener('click', () => showTab('tasks'));
  $('days').addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.live) { goLive(); return; }
    const entry = state.shownDays?.[Number(button.dataset.day)];
    if (!entry) return;
    if (button.classList.contains('whole')) startDay(entry);
    else pick(entry.runs[Number(button.dataset.run)], { play: true });
  });
  document.querySelectorAll('[data-drill]').forEach(button => button.addEventListener('click', () => pick(M.drill(button.dataset.drill), { play: true })));
  addEventListener('resize', () => { if (state.run) draw(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  $('refresh-data').addEventListener('click', () => poll(true));

  loadCustomers().then(() => { if (state.run) draw(); });
  poll(true);
  requestAnimationFrame(frame);
})();
