/* Văn phòng của tab Máy chạy (MAY-CHAY-01): chỉ vẽ. Mỗi nhân viên là một trạm thật của job; chỉ cử động khi trạm đó đang chạy, hết lượt thì đứng yên.
 * Nhân vật và cảnh vẽ bằng khối pixel, không dùng ảnh ngoài. Hermes là nhân viên duy nhất là AI; không có chìa khóa phòng ghi. */
const MayChayOffice = (() => {
  'use strict';
  const M = MayChayModel;
  const WW = 860, WH = 284, BAR = 22, SS = 2;   // thế giới 860×284, vẽ gấp đôi rồi thu về để nét và không hở mép
  const FONT = '"Segoe UI",system-ui,sans-serif';
  const SEATS = {
    tai: { x: 110, y: 92, shirt: '#3f7cc4', hair: '#2b2320', skin: '#f0c8a0' }, sach: { x: 205, y: 92, shirt: '#2f9a8b', hair: '#7a4a26', skin: '#e4b68c', long: true },
    doc: { x: 300, y: 92, shirt: '#c4793f', hair: '#1e1e24', skin: '#c99468' }, so: { x: 395, y: 92, shirt: '#7a5fc0', hair: '#3b2a1c', skin: '#f0c8a0', long: true },
    tim: { x: 478, y: 196, shirt: '#c2557a', hair: '#23201d', skin: '#d9a97e' }, ghi: { x: 690, y: 196, shirt: '#1c5cab', hair: '#6b4a2a', skin: '#f0c8a0' },
    luu: { x: 775, y: 92, shirt: '#5f8a3a', hair: '#2c2c2c', skin: '#b98258', long: true },
  };
  const HERMES = { x: 312, y: 196, shirt: '#26324a', hair: '#3a3a44', skin: '#e4b68c' };
  const GUARD = { shirt: '#39465a', hair: '#1c2430', skin: '#e4b68c' }, GATE = { x: 392, y: 196 }, TRAY = { x: 492, y: 96 }, KHO = { x: 528, y: 165, w: 84, h: 70 };
  const SIDE_JOBS = [
    { id: 'sheet', name: 'Bản chụp', x: 30, shirt: '#4d8fb0', hair: '#2b2320', skin: '#f0c8a0' },
    { id: 'prices', name: 'Giá', x: 82, shirt: '#a0694d', hair: '#54331d', skin: '#d9a97e', long: true },
    { id: 'ps', name: 'PS', x: 134, shirt: '#6c7fb5', hair: '#1e1e24', skin: '#c99468' },
    { id: 'watchdog', name: 'Máy canh', x: 186, shirt: '#b04d4d', hair: '#3b2a1c', skin: '#f0c8a0' },
    { id: 'backup-hourly', name: 'Sao lưu', x: 238, shirt: '#4f8a6c', hair: '#2c2c2c', skin: '#e4b68c', long: true },
  ];
  const COL = { floor: '#e6d9c6', floor2: '#d6c6ae', room: '#d8e1ec', room2: '#cfd9e6', wall: '#eef0f3', wall2: '#e2e8f0', rug: '#d9d2e3', trim: '#b9c2cd', desk: '#a97c50', top: '#d2a679', chair: '#6f7c8b', shelf: '#7d6146', screen: '#22303f',
    surface: '#ffffff', ink: '#1a1a19', ink2: '#52514e', ink3: '#6f6d67', accent: '#2a78d6', credit: '#0f766e', critical: '#c8322f', warning: '#9a5b00', line: '#d7dce3', halo: '#ffffff', creditSoft: '#e3f4f1', warningSoft: '#fdf3e1', criticalSoft: '#fdecea' };

  // Nhân vật pixel: lưới 12×17, mỗi ô 2 đơn vị, cache sẵn từng dáng.
  const shade = (hex, f) => `#${[1, 3, 5].map(i => Math.round(parseInt(hex.slice(i, i + 2), 16) * f).toString(16).padStart(2, '0')).join('')}`;
  const LEGS = {
    front: { stand: ['...pppppp...', '...pp..pp...', '...pp..pp...', '...bb..bb...'], a: ['...pppppp...', '...pp..pp...', '...pp...bb..', '...bb.......'], b: ['...pppppp...', '...pp..pp...', '..bb...pp...', '.......bb...'] },
    side: { stand: ['....pppp....', '....pppp....', '....pppp....', '....bbbb....'], a: ['....pppp....', '...pp..pp...', '..pp....pp..', '..bb....bb..'], b: ['....pppp....', '....pppp....', '....pp.pp...', '....bb.bb...'] },
  };
  const BODY = {
    front: ['...hhhhhh...', '..hhhhhhhh..', '..hhhhhhhh..', '..hssssssh..', '..sewsswes..', '..ssssssss..', '...sSSSSs...', '..cccccccc..', '.cccccccccc.', '.cCccccccCc.', '.cCccccccCc.', '.s.cccccc.s.', '...cccccc...'],
    back: ['...hhhhhh...', '..hhhhhhhh..', '..hhhhhhhh..', '..hhhhhhhh..', '..hhhhhhhh..', '..hhhhhhhh..', '...sSSSSs...', '..cccccccc..', '.cccccccccc.', '.cCCCCCCCCc.', '.cCccccccCc.', '.s.cccccc.s.', '...cccccc...'],
    side: ['....hhhhh...', '...hhhhhhh..', '...hhhhhhh..', '...hhsssss..', '...hsssews..', '...sssssss..', '....sSSs....', '....ccccc...', '...ccccccc..', '...cCcccc...', '...cCcccc...', '...sccccc...', '....cccc....'],
  };
  const spriteCache = new Map();
  function sprite(look, dir, frame) {
    const key = [look.shirt, look.hair, look.skin, look.long ? 1 : 0, dir, frame].join();
    if (spriteCache.has(key)) return spriteCache.get(key);
    const view = dir === 'left' || dir === 'right' ? 'side' : dir;
    const rows = BODY[view].concat(LEGS[view === 'side' ? 'side' : 'front'][frame]);
    const can = document.createElement('canvas'); can.width = 12; can.height = 17;
    const x = can.getContext('2d');
    const pal = { h: look.hair, s: look.skin, S: shade(look.skin, 0.82), c: look.shirt, C: shade(look.shirt, 0.72), p: '#39414d', b: '#24262b', e: '#22262c', w: '#ffffff' };
    rows.forEach((row, r) => [...row].forEach((ch, i) => { if (pal[ch]) { x.fillStyle = pal[ch]; x.fillRect(i, r, 1, 1); } }));
    if (look.long && view !== 'side') { x.fillStyle = look.hair; x.fillRect(2, 5, 1, 4); x.fillRect(9, 5, 1, 4); if (view === 'back') x.fillRect(3, 6, 6, 3); }
    let out = can;
    if (dir === 'left') { const flip = document.createElement('canvas'); flip.width = 12; flip.height = 17; const fx = flip.getContext('2d'); fx.translate(12, 0); fx.scale(-1, 1); fx.drawImage(can, 0, 0); out = flip; }
    spriteCache.set(key, out);
    return out;
  }

  const along = (points, f) => {
    let total = 0; const seg = [];
    for (let i = 1; i < points.length; i++) { const d = Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]); seg.push(d); total += d; }
    let left = f * total;
    for (let i = 0; i < seg.length; i++) {
      if (left <= seg[i] || i === seg.length - 1) { const q = seg[i] ? Math.min(left / seg[i], 1) : 0; return [points[i][0] + (points[i + 1][0] - points[i][0]) * q, points[i][1] + (points[i + 1][1] - points[i][1]) * q]; }
      left -= seg[i];
    }
    return points[0];
  };
  function walkPose(path, q, returning) {
    const pos = along(path, q), next = along(path, Math.min(1, q + 0.02)), prev = along(path, Math.max(0, q - 0.02));
    let dx = next[0] - prev[0], dy = next[1] - prev[1];
    if (returning) { dx = -dx; dy = -dy; }
    return { pos, dir: Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : dy > 0 ? 'front' : 'back' };
  }
  function skyOf(hour) {
    if (hour < 6 || hour >= 19) return { key: 'night', sky: '#1b2747', low: '#2a3a63', dark: 0.27, sun: 0 };
    if (hour < 8) return { key: 'dawn', sky: '#f5c58f', low: '#fbe3bd', dark: 0.05, sun: 0.1 };
    if (hour >= 17) return { key: 'dusk', sky: '#ee9a66', low: '#f9cf9a', dark: 0.1, sun: 0.1 };
    return { key: 'day', sky: '#8fc7f2', low: '#cfe8fb', dark: 0, sun: 0.1 };
  }

  function create(canvas, { onPick, reduce = false } = {}) {
    const sc = canvas.getContext('2d');
    const world = document.createElement('canvas'); world.width = WW * SS; world.height = WH * SS;
    const c = world.getContext('2d'); c.scale(SS, SS); c.imageSmoothingEnabled = false;
    const bgCanvas = document.createElement('canvas'); bgCanvas.width = WW * SS; bgCanvas.height = WH * SS;
    const bc = bgCanvas.getContext('2d'); bc.scale(SS, SS);
    let bgKey = '', lastCam = { x: 0, y: 0, z: 1 }, hover = null, selected = null, walkers = {}, last = null, redraw = () => {};
    const R = (x, y, w, h, col, ctx = c) => { ctx.fillStyle = col; ctx.fillRect(Math.round(x), Math.round(y), w, h); };
    function txt(text, x, y, opt = {}) {
      c.font = `${opt.weight || 400} ${opt.size || 13}px ${FONT}`; c.textAlign = opt.align || 'center'; c.textBaseline = 'alphabetic';
      if (opt.halo !== false) { c.lineWidth = 3.5; c.lineJoin = 'round'; c.strokeStyle = COL.halo; c.strokeText(text, x, y); }
      c.fillStyle = opt.color || COL.ink; c.fillText(text, x, y);
    }
    function plaque(text, x, y, border, fill, ink, weight = 600) {
      c.font = `${weight} 12.5px ${FONT}`;
      const w = c.measureText(text).width + 14, left = Math.max(4, Math.min(WW - 4 - w, x - w / 2));
      c.fillStyle = fill; c.strokeStyle = border; c.lineWidth = 1.5;
      c.beginPath(); c.roundRect(left, y - 11, w, 22, 6); c.fill(); c.stroke();
      c.textAlign = 'left'; c.textBaseline = 'alphabetic'; c.fillStyle = ink; c.fillText(text, left + 7, y + 4);
      return { left, w };
    }
    function bubble(text, x, y, tone) {
      const border = tone === 'bad' ? COL.critical : tone === 'warn' ? COL.warning : COL.accent;
      const box = plaque(text, x, y, border, COL.surface, COL.ink);
      const tail = Math.max(box.left + 6, Math.min(box.left + box.w - 12, x - 3));
      R(tail, y + 11, 6, 3, border); R(tail + 1, y + 14, 3, 3, border);
    }
    function person(x, y, look, dir = 'front', frame = 'stand') {
      x = Math.round(x); y = Math.round(y);
      c.fillStyle = 'rgba(20,30,45,.22)'; c.fillRect(x - 10, y - 2, 20, 4);
      c.drawImage(sprite(look, dir, frame), x - 12, y - 34, 24, 34);
    }
    function paper(x, y) { R(x - 5, y - 6, 10, 12, '#ffffff'); R(x - 5, y - 6, 10, 1, '#b7bec8'); R(x - 3, y - 3, 6, 1, '#9aa3ae'); R(x - 3, y, 6, 1, '#9aa3ae'); }
    const fly = (from, to, f, lift = 18) => paper(from[0] + (to[0] - from[0]) * f, from[1] + (to[1] - from[1]) * f - Math.sin(f * Math.PI) * lift);
    function glow(x, y, r, col, alpha) {
      const g = c.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, col); g.addColorStop(1, 'rgba(0,0,0,0)');
      c.save(); c.globalCompositeOperation = 'lighter'; c.globalAlpha = alpha; c.fillStyle = g; c.fillRect(x - r, y - r, r * 2, r * 2); c.restore();
    }

    function buildBg(sky) {
      const b = bc, F = (x, y, w, h, col) => R(x, y, w, h, col, b);
      // Sàn gỗ khu đọc, sàn thảm phòng ghi: nhìn là biết hai khu khác nhau.
      F(0, 56, 570, WH, COL.floor);
      for (let y = 56, r = 0; y < WH; y += 14, r++) { F(0, y + 13, 570, 1, COL.floor2); for (let x = (r % 2) * 46; x < 570; x += 92) F(x, y, 1, 13, COL.floor2); }
      F(570, 56, WW - 570, WH, COL.room);
      for (let y = 56; y < WH; y += 20) for (let x = 570 + (y % 40 === 16 ? 0 : 20); x < WW; x += 40) F(x, y, 20, 20, COL.room2);
      F(0, 0, 570, 50, COL.wall); F(570, 0, WW - 570, 50, COL.wall2); F(0, 50, WW, 6, COL.trim);
      for (const wx of [160, 242, 778]) {
        F(wx - 3, 7, 68, 36, COL.trim); F(wx, 10, 62, 30, sky.sky); F(wx, 28, 62, 12, sky.low);
        if (sky.key === 'night') for (const [sx, sy] of [[6, 5], [20, 12], [33, 6], [47, 14], [55, 4], [12, 20]]) F(wx + sx, 10 + sy, 2, 2, '#e8eefc');
        else { F(wx + 8, 32, 14, 8, shade(sky.low, 0.8)); F(wx + 40, 30, 18, 10, shade(sky.low, 0.72)); }
        F(wx + 30, 10, 2, 30, COL.trim); F(wx - 3, 43, 68, 3, COL.top);
      }
      if (sky.sun) {
        b.save(); b.globalAlpha = sky.sun; b.fillStyle = sky.key === 'day' ? '#fff6d8' : '#ffd9a8';
        for (const wx of [160, 242, 778]) { b.beginPath(); b.moveTo(wx, 56); b.lineTo(wx + 62, 56); b.lineTo(wx + 34, 170); b.lineTo(wx - 28, 170); b.closePath(); b.fill(); }
        b.restore();
      }
      b.textAlign = 'left'; b.textBaseline = 'alphabetic';
      b.font = `600 13px ${FONT}`; b.fillStyle = COL.ink2; b.fillText('KHU ĐỌC', 424, 24); b.font = `400 12px ${FONT}`; b.fillText('không ghi được vào sổ', 424, 40);
      b.font = `600 13px ${FONT}`; b.fillStyle = COL.ink; b.fillText('PHÒNG GHI SỔ', 586, 24); b.font = `400 12px ${FONT}`; b.fillStyle = COL.ink2; b.fillText('chỉ 1 bàn', 586, 40);
      b.save(); b.globalAlpha = 0.28; F(566, 56, 8, 109, COL.accent); b.restore();
      F(566, 56, 8, 3, COL.trim); F(566, 110, 8, 2, COL.trim); F(566, 235, 8, 5, COL.trim);
      F(14, 16, 44, 66, COL.shelf); for (let i = 0; i < 3; i++) { F(18, 21 + i * 20, 36, 17, COL.top); F(32, 27 + i * 20, 8, 3, COL.shelf); }
      b.fillStyle = COL.ink; b.font = `600 12px ${FONT}`; b.fillText('Google Sheet', 66, 14);
      F(KHO.x, KHO.y, KHO.w, KHO.h, COL.shelf); F(KHO.x, KHO.y + KHO.h, KHO.w, 5, '#5a4632');
      const spines = ['#c2557a', '#3f7cc4', '#2f9a8b', '#c4793f', '#7a5fc0', '#5f8a3a'];
      for (let row = 0; row < 3; row++) { F(KHO.x + 3, KHO.y + 4 + row * 22, KHO.w - 6, 19, COL.top); for (let i = 0; i < 13; i++) F(KHO.x + 5 + i * 6, KHO.y + 6 + row * 22, 5, 17, spines[(i + row * 2) % 6]); }
      F(8, 170, 262, 92, COL.rug); b.save(); b.globalAlpha = 0.18; F(8, 170, 262, 3, COL.ink); F(8, 259, 262, 3, COL.ink); b.restore();
      F(278, 170, 68, 92, COL.rug); b.save(); b.globalAlpha = 0.25; F(278, 170, 68, 3, COL.accent); F(278, 259, 68, 3, COL.accent); b.restore();
      b.fillStyle = COL.ink2; b.font = `400 12px ${FONT}`; b.fillText('Các job khác', 14, 164);
      for (const [px, py] of [[838, 118], [838, 268], [544, 80]]) {
        F(px - 7, py - 8, 14, 10, '#a8654a'); F(px - 8, py - 10, 16, 3, '#8d5340');
        F(px - 10, py - 26, 20, 16, '#3f8f5f'); F(px - 6, py - 34, 12, 10, '#54a874'); F(px - 13, py - 20, 6, 8, '#54a874'); F(px + 7, py - 22, 6, 8, '#2f7a4f');
      }
      F(690, 8, 66, 36, COL.shelf); F(693, 11, 60, 30, COL.top);
      F(TRAY.x - 34, TRAY.y, 68, 11, COL.top); F(TRAY.x - 34, TRAY.y + 11, 68, 15, COL.desk); F(TRAY.x - 30, TRAY.y + 26, 5, 6, COL.desk); F(TRAY.x + 25, TRAY.y + 26, 5, 6, COL.desk);
    }

    function deskAt(seat, state, typing, away, small, wall) {
      const { x, y } = seat, w = small ? 22 : 32;
      R(x - (small ? 9 : 15), y - 13, small ? 18 : 22, 24, COL.chair);
      if (!away) person(x - (small ? 0 : 6), y + 12, seat);
      R(x - w, y, w * 2, 2, '#e3b98c'); R(x - w, y + 2, w * 2, 9, COL.top); R(x - w, y + 11, w * 2, 15, COL.desk);
      R(x - w + 4, y + 26, 4, 6, COL.desk); R(x + w - 8, y + 26, 4, 6, COL.desk);
      if (!small) { R(x - 4, y + 14, 16, 2, '#8a6541'); R(x - 26, y + 14, 16, 2, '#8a6541'); }
      const on = state === 'run', mx = small ? x + 7 : x + 8, mw = small ? 12 : 20, mh = small ? 10 : 15;
      R(mx, y - mh - 3, mw, mh, COL.screen);
      R(mx + 2, y - mh - 1, mw - 4, mh - 4, on ? '#6da7ec' : '#3c4a5a');
      if (on) for (let i = 0; i < (small ? 2 : 3); i++) R(mx + 3, y - mh + i * 3, 2 + ((Math.floor(wall / 180) + i * 3) % (mw - 7)), 1, '#eaf2fc');
      R(mx + mw / 2 - 2, y - 3, 4, 3, COL.screen);
      if (!small) { R(x - 20, y + 3, 22, 5, '#46505c'); R(x - 19, y + 4, 20, 1, '#7d8896'); }
      if (typing && !away && !reduce) { const bob = Math.floor(wall / 110) % 2, hx = small ? 0 : -6; R(x + hx - 9, y + 1 + bob, 5, 3, seat.skin); R(x + hx + 4, y + 2 - bob, 5, 3, seat.skin); }
      const lamp = state === 'run' ? COL.accent : state === 'done' ? COL.credit : state === 'stop' || state === 'failed' ? COL.critical : state === 'late' || state === 'off' ? '#e0a64f' : COL.line;
      R(x - w + 3, y - 6, 6, 6, lamp); R(x - w + 3, y - 6, 6, 1, 'rgba(255,255,255,.5)');
    }

    function camera(run, t, cur, rate, camOn) {
      const still = { x: 0, y: 0, z: 1 };
      if (!camOn || reduce || rate > 15) return still;
      const ease = e => { const v = Math.max(0, Math.min(1, e)); return 1 + 0.5 * v * v * (3 - 2 * v); };
      const wrote = run.customers.some(item => item.wrote), failed = run.customers.some(item => item.reason === 'VERIFY_FAILED' && t >= item.done);
      const cy = 170;
      let z = 1, cx = 650;
      if (cur === 'ghi') z = ease((t - run.stages.ghi.from) / Math.max(run.stages.ghi.d * 0.14, 0.5));
      else if (failed) z = 1.4;
      else if (cur === 'luu' && wrote) z = ease(1 - (t - run.stages.luu.from) / Math.max(run.stages.luu.d, 0.5));
      else if (run.tooMany && t >= run.stages.chot.to && t < run.stages.chot.to + 40) { z = ease(Math.min(t - run.stages.chot.to, run.stages.chot.to + 40 - t) / 5); cx = GATE.x; }
      if (z <= 1) return still;
      const w = WW / z, h = WH / z;
      return { z, x: Math.max(0, Math.min(WW - w, cx - w / 2)), y: Math.max(0, Math.min(WH - h, cy - h / 2)) };
    }

    const spotOf = key => {
      if (key === 'hermes') return [HERMES.x - 6, HERMES.y + 8];
      if (key === 'chot') return [GATE.x, GATE.y + 12];
      const job = SIDE_JOBS.find(item => `job-${item.id}` === key);
      if (job) return [job.x, 216];
      if (walkers[key]) return walkers[key].pos;
      const seat = SEATS[key];
      return seat ? [seat.x - 6, seat.y + 8] : null;
    };

    // Vẽ một khung. `view`: { run, t, cur, clock, rate, camOn, labelOf, jobActive(id), jobState(id), hermes:{state,tasks}, idleNext, wall }.
    function draw(view) {
      last = view;
      const w = canvas.clientWidth; if (!w) return;
      const dpr = globalThis.devicePixelRatio || 1, cw = Math.round(w * dpr), ch = Math.round(((w * (WH + BAR)) / WW) * dpr);
      if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch; }
      const { run, t, cur, clock, labelOf, wall, hermes } = view;
      const hour = Math.floor(clock / 3600) % 24, sky = skyOf(hour);
      if (sky.key !== bgKey) { bgKey = sky.key; bc.clearRect(0, 0, WW, WH); buildBg(sky); }
      c.drawImage(bgCanvas, 0, 0, WW, WH);
      const over = t >= run.sec && !run.live, info = {};
      for (const key of M.ORDER) info[key] = M.stationInfo(run, t, key, cur);
      const nameOf = item => (run.drill ? 'Khách A' : labelOf?.(item.id) ?? `Sổ ${item.id}`);

      R(320, 10, 84, 28, COL.screen); txt(M.clockOf(clock), 362, 29, { color: '#eaf2fc', weight: 600, size: 15, halo: false });
      if (info.luu.f >= 1 && !view.idleNext) { R(698, 15, 11, 10, '#fff'); R(713, 15, 11, 10, '#fff'); R(728, 15, 11, 10, '#fff'); R(698, 28, 11, 8, '#fff6c9'); }

      const pending = run.customers.length + (run.tooMany ? (run.different ?? 0) : 0) + (run.countsOnly ? Math.max((run.total ?? 0) - (run.khop ?? 0) + run.fixed + run.created, 0) : 0);
      const startMatched = Math.max((run.total ?? 0) - pending, 0);
      const soF = info.so.f, extra = run.customers.filter(item => ['FIXED', 'BOOK_CREATED'].includes(item.reason) && t >= item.done).length + (run.countsOnly && over ? run.fixed + run.created : 0);
      const pile = Math.round(soF * 26);
      for (let i = 0; i < pile; i += 3) { R(TRAY.x - 14, TRAY.y - 2 - i, 28, 2, '#fff'); R(TRAY.x - 14, TRAY.y - 3 - i, 28, 1, '#b7bec8'); }

      const chotState = info.chot.state, stopped = run.tooMany && t >= run.stages.chot.to, gx = GATE.x, gy = GATE.y;
      R(gx - 28, gy - 30, 6, 46, COL.shelf); R(gx + 22, gy - 30, 6, 46, COL.shelf);
      if (stopped) { for (let i = 0; i < 44; i += 11) R(gx - 22 + i, gy - 14, 11, 7, i % 22 ? '#fff' : COL.critical); }
      else R(gx - 22, gy - 30, 44, 4, chotState === 'done' ? COL.credit : chotState === 'run' ? COL.accent : COL.line);
      person(gx, gy + 18, GUARD);

      const doorOpen = cur === 'ghi';
      if (doorOpen) R(566, 240, 8, 8, '#7d6146');
      else { R(566, 240, 8, 44, '#7d6146'); R(568, 258, 4, 6, '#e0b64a'); }

      walkers = {};
      const fCur = cur ? info[cur].f : 0;
      const frameOf = moving => (moving && !reduce ? (Math.floor(wall / 170) % 2 ? 'a' : 'b') : 'stand');
      if (cur === 'tai') {
        const g = fCur < 0.45 ? fCur / 0.45 : fCur < 0.55 ? 1 : (1 - fCur) / 0.45, back = fCur >= 0.55;
        walkers.tai = { ...walkPose([[104, 104], [72, 118], [36, 102]], g, back), moving: fCur < 0.45 || back, carry: back };
      }
      if (cur === 'doc') {
        const g = (fCur * 4) % 1, back = g >= 0.5;
        walkers.doc = { ...walkPose([[294, 104], [344, 110], [344, 278], [518, 278], [518, 236]], back ? 2 - g * 2 : g * 2, back), moving: true, carry: back };
      }
      let writing = null;
      if (cur === 'ghi') {
        const list = run.customers.filter(item => item.wrote);
        const n = Math.max(list.length, 1), s = run.stages.ghi, slot = Math.max(s.d / n, 0.001);
        const idx = Math.min(n - 1, Math.floor(Math.max(t - s.from, 0) / slot)), g = ((t - s.from) / slot) % 1;
        writing = list[idx] ?? null;
        const q = g < 0.42 ? g / 0.42 : g < 0.58 ? 1 : (1 - g) / 0.42, back = g >= 0.58;
        walkers.ghi = { ...walkPose([[684, 208], [684, 186], [640, 186], [628, 206]], q, back), moving: g < 0.42 || back, carry: g < 0.42 };
        if (g >= 0.42 && g < 0.58) walkers.ghi.dir = 'left';
      }
      if (cur === 'luu') {
        const back = fCur >= 0.5;
        walkers.luu = { ...walkPose([[769, 104], [745, 110], [728, 72]], back ? (1 - fCur) * 2 : fCur * 2, back), moving: true, carry: !back };
      }
      for (const job of SIDE_JOBS) {
        const on = view.jobActive?.(job.id), state = view.jobState?.(job.id);
        deskAt({ ...job, y: 208 }, on ? 'run' : ['failed', 'late', 'off'].includes(state) ? state : '', on, false, true, wall);
        if (on) glow(job.x + 12, 200, 28, '#6da7ec', 0.7);
      }
      const hermesWorking = hermes?.state === 'working';
      deskAt(HERMES, hermesWorking ? 'run' : '', hermesWorking, false, false, wall);
      for (const key of ['tai', 'sach', 'doc', 'so', 'luu', 'tim', 'ghi']) deskAt(SEATS[key], info[key].state, cur === key && !walkers[key], Boolean(walkers[key]), false, wall);

      const pass = { sach: ['tai', 'sach'], doc: ['sach', 'doc'], so: ['doc', 'so'] };
      if (cur && pass[cur] && fCur < 0.18) { const [a, b] = pass[cur]; fly([SEATS[a].x + 20, SEATS[a].y - 2], [SEATS[b].x - 20, SEATS[b].y - 2], fCur / 0.18); }
      if (cur === 'so' && !reduce) for (let i = 0; i < 4; i++) fly([SEATS.so.x + 24, 88], [TRAY.x - 8, TRAY.y - pile - 4], (wall / 1100 + i / 4) % 1, 22);
      if (cur === 'chot' && !run.tooMany) fly([SEATS.so.x, 122], [gx, gy - 26], fCur, 4);
      if (cur === 'tim' && fCur < 0.1) fly([gx + 10, gy - 20], [SEATS.tim.x - 10, SEATS.tim.y - 4], fCur / 0.1, 10);
      if (cur === 'ghi' && fCur < 0.14) paper(...along([[488, 196], [540, 262], [572, 262], [650, 262], [684, 214]], fCur / 0.14));
      for (const key in walkers) {
        const v = walkers[key];
        person(v.pos[0], v.pos[1], SEATS[key], v.dir, frameOf(v.moving));
        if (v.carry) paper(v.pos[0] + (v.dir === 'left' ? -13 : 13), v.pos[1] - 15);
      }
      const mark = selected || hover;
      if (mark) { const at = spotOf(mark); if (at) { c.strokeStyle = COL.accent; c.lineWidth = 2; c.beginPath(); c.ellipse(at[0], at[1] + 8, 26, 9, 0, 0, Math.PI * 2); c.stroke(); } }

      if (sky.dark) { c.fillStyle = `rgba(14,22,52,${sky.dark})`; c.fillRect(0, 0, WW, WH); }
      if (sky.key === 'night') for (const [lx, ly] of [[200, 110], [395, 120], [490, 220], [690, 150], [130, 225]]) glow(lx, ly, 110, '#ffdf9e', 0.2);
      if (cur && SEATS[cur] && !walkers[cur]) glow(SEATS[cur].x + 18, SEATS[cur].y - 8, 58, '#6da7ec', sky.dark ? 0.75 : 0.42);
      if (hermesWorking) glow(HERMES.x + 18, HERMES.y - 8, 58, '#b9a7f0', sky.dark ? 0.75 : 0.45);
      if (cur === 'ghi') glow(KHO.x + KHO.w / 2, KHO.y + 34, 72, '#ffe08a', 0.45);
      if (cur === 'doc') glow(KHO.x + 6, KHO.y + 26, 40, '#9fc7f5', 0.4);
      const failed = run.customers.some(item => item.reason === 'VERIFY_FAILED' && t >= item.done);
      if (failed) {
        const on = reduce || Math.floor(wall / 340) % 2;
        c.fillStyle = `rgba(200,50,47,${on ? 0.2 : 0.08})`; c.fillRect(574, 56, WW - 574, WH - 56);
        R(624, 4, 14, 8, on ? '#ff5c56' : '#7a2c2a');
      }
      if (stopped) { const on = reduce || Math.floor(wall / 340) % 2; glow(gx, gy - 14, 62, '#ff5c56', on ? 0.6 : 0.25); }

      for (const key of Object.keys(SEATS)) {
        const seat = SEATS[key], skip = info[key].state === 'skip';
        txt(M.NAMES[key], seat.x, seat.y + 44, { weight: 600, size: 13.5, color: skip ? COL.ink3 : COL.ink });
        if (info[key].text) txt(info[key].text, seat.x, seat.y + 60, { size: 12.5, color: COL.ink2 });
        if (skip && !over && !walkers[key]) txt('z z', seat.x - 6, seat.y - 28, { size: 12.5, color: COL.ink3 });
      }
      txt(soF > 0 && run.total !== null ? `Khớp ${Math.floor(soF * startMatched) + extra}` : 'Khớp —', TRAY.x, TRAY.y + 43, { weight: 600, size: 13.5 });
      txt('Chốt 1', gx, gy + 34, { weight: 600, size: 13.5, color: chotState === 'skip' ? COL.ink3 : COL.ink });
      if (info.chot.text) txt(info.chot.text, gx, gy + 50, { size: 12.5, color: COL.ink2 });
      txt('Sổ web', KHO.x + KHO.w / 2, KHO.y + KHO.h + 19, { weight: 600, size: 13.5 });
      txt(doorOpen ? 'cửa mở: đang ghi' : 'cửa khóa', 590, WH - 8, { size: 12, weight: doorOpen ? 600 : 400, align: 'left', color: doorOpen ? COL.accent : COL.ink2 });
      txt('Hermes', HERMES.x, HERMES.y + 44, { weight: 600, size: 13.5 });
      const taskCount = Object.keys(hermes?.tasks ?? {}).length;
      txt(hermes?.state === 'off' ? 'chưa chạy' : hermesWorking ? 'đang đọc tóm tắt' : 'quản lý · AI', HERMES.x, HERMES.y + 60, { size: 12.5, color: COL.ink2 });
      for (const job of SIDE_JOBS) txt(job.name, job.x, 256, { size: 12, color: COL.ink2 });

      const ranks = {}, nextRank = key => { ranks[key] = (ranks[key] || 0) + 1; return ranks[key] - 1; };
      const overflow = (key, limit, x, y) => { if (ranks[key] === limit + 1) plaque(`+${run.customers.length - limit} khách`, x, y, COL.line, COL.surface, COL.ink2); };
      for (const item of run.customers) {
        if (run.tooMany || t < run.stages.so.to) continue;
        let px, py, tone = 'move';
        if (t < run.stages.chot.to) { px = gx; py = gy - 46 - nextRank('gate') * 24; }
        else if (t < item.decided || !item.wrote) { const rank = nextRank('tim'); if (rank > 1) { overflow('tim', 2, SEATS.tim.x + 36, SEATS.tim.y - 65); continue; } px = SEATS.tim.x - 30 + rank * 112; py = SEATS.tim.y - 41; tone = t >= item.decided ? (item.info.tone === 'bad' ? 'bad' : 'warn') : 'move'; }
        else if (t < item.done) { if (writing === item && walkers.ghi) continue; px = SEATS.ghi.x + nextRank('ghi') * 24; py = SEATS.ghi.y - 41; }
        else if (item.info.tone === 'bad') { px = SEATS.ghi.x; py = SEATS.ghi.y - 41; tone = 'bad'; }
        else { const rank = nextRank('luu'); if (rank > 3) { overflow('luu', 4, SEATS.luu.x, 176 + 4 * 24); continue; } px = SEATS.luu.x; py = 176 + rank * 24; tone = 'ok'; }
        const look = { move: [COL.accent, COL.surface], warn: [COL.warning, COL.warningSoft], bad: [COL.critical, COL.criticalSoft], ok: [COL.credit, COL.creditSoft] }[tone];
        const name = nameOf(item);
        plaque(name.length > 12 ? `${name.slice(0, 11)}…` : name, px, py, look[0], look[1], COL.ink);
      }
      for (const item of run.customers) {
        const age = t - item.done, span = 24;
        if (!item.wrote || age < 0) continue;
        const bad = item.info.tone === 'bad', label = bad ? 'LỆCH' : item.reason === 'BOOK_CREATED' ? 'SỔ MỚI' : 'KHỚP', grow = Math.min(1, age / 3.5), col = bad ? COL.critical : COL.credit;
        c.save(); c.translate(SEATS.ghi.x + 2, SEATS.ghi.y + 6); c.rotate(-0.14); c.scale(1.7 - 0.7 * grow, 1.7 - 0.7 * grow);
        c.globalAlpha = Math.max(0.85, Math.min(1, (span - age) / 6 + 0.85));
        c.lineWidth = 2.5; c.strokeStyle = col; c.fillStyle = COL.surface; c.beginPath(); c.roundRect(-33, -14, 66, 26, 4); c.fill(); c.stroke();
        c.fillStyle = col; c.font = `700 15px ${FONT}`; c.textAlign = 'center'; c.fillText(label, 0, 4);
        c.restore();
        if (item.before !== null && !bad && age < span) plaque(`${M.millions(item.before)} → ${M.millions(item.after)}`, SEATS.ghi.x + 6, SEATS.ghi.y - 48 - Math.min(26, age * 2), col, COL.surface, COL.ink);
      }
      const say = {
        tai: ['Lấy bản Sheet, chỉ đọc', walkers.tai], sach: [`Làm sạch ${info.sach.text}`], doc: [`Đọc sổ ${info.doc.text}`, walkers.doc], so: [`So tổng ${info.so.text}`],
        tim: ['Tìm đúng 1 tổ hợp'], ghi: [writing ? `Ghi ${nameOf(writing).slice(0, 14)}, rồi đọc lại` : 'Ghi vào sổ', walkers.ghi], luu: ['Lưu kết quả', walkers.luu],
      };
      if (cur && say[cur] && !(cur === 'ghi' && writing && t >= writing.done)) {
        const [text, v] = say[cur];
        bubble(text, v ? v.pos[0] : SEATS[cur].x - 6, Math.max(14, (v ? v.pos[1] - 34 : SEATS[cur].y - 22) - 20));
      }
      if (cur === 'chot') bubble('Có quá nhiều khách lệch không?', gx, gy - 46);
      if (stopped) bubble('Dừng, lượt này không ghi', gx, gy - 46, 'bad');
      if (failed) bubble('Đọc lại không khớp!', SEATS.ghi.x, SEATS.ghi.y - 70, 'bad');
      if (hermesWorking) bubble('Đang đọc tóm tắt', HERMES.x, HERMES.y - 42);
      else if (taskCount && !run.drill) bubble(`${taskCount} thẻ việc`, HERMES.x, HERMES.y - 42, Object.values(hermes.tasks).some(item => item.level === 'urgent') ? 'bad' : 'warn');
      if (view.idleNext) bubble(view.idleNext, 362, 60);

      const cam = camera(run, t, cur, view.rate, view.camOn); lastCam = cam;
      sc.setTransform(1, 0, 0, 1, 0, 0);
      sc.imageSmoothingEnabled = true; sc.imageSmoothingQuality = 'high';
      const k = cw / WW;
      sc.drawImage(world, cam.x * SS, cam.y * SS, (WW / cam.z) * SS, (WH / cam.z) * SS, 0, 0, cw, WH * k);
      sc.setTransform(k, 0, 0, k, 0, 0);
      sc.fillStyle = '#16324f'; sc.fillRect(0, WH, WW, BAR);
      const HUD = ['Chốt 1: không quá nhiều khách lệch', 'Chốt 2: đúng 1 tổ hợp bằng số lệch', 'Chốt 3: ghi xong đọc lại phải khớp'];
      sc.textAlign = 'left'; sc.textBaseline = 'alphabetic';
      M.gateMarks(run, t).forEach((gate, i) => {
        sc.font = `${gate.state ? 600 : 400} 12.5px ${FONT}`;
        sc.fillStyle = gate.state === 'hit' ? '#ff9a96' : gate.state === 'held' ? '#f0c069' : gate.state === 'pass' ? '#7fdcc9' : '#c3d1e0';
        sc.fillText(gate.mark + HUD[i], 10 + i * 284, WH + 16);
      });
    }

    function pickAt(event) {
      const box = canvas.getBoundingClientRect(), scale = WW / box.width;
      const mx = (event.clientX - box.left) * scale, my = (event.clientY - box.top) * scale;
      if (my > WH) return null;
      const wx = lastCam.x + mx / lastCam.z, wy = lastCam.y + my / lastCam.z;
      let best = null, bestD = 44;
      for (const key of [...Object.keys(SEATS), 'chot', 'hermes', ...SIDE_JOBS.map(job => `job-${job.id}`)]) {
        const at = spotOf(key);
        if (!at) continue;
        const d = Math.hypot(wx - at[0], (wy - (at[1] - 14)) * 1.2);
        if (d < bestD) { bestD = d; best = key; }
      }
      return best;
    }
    canvas.addEventListener('click', event => onPick?.(pickAt(event)));
    canvas.addEventListener('mousemove', event => { const key = pickAt(event); canvas.style.cursor = key ? 'pointer' : 'default'; if (key !== hover) { hover = key; redraw(); } });
    canvas.addEventListener('mouseleave', () => { hover = null; redraw(); });
    return {
      draw,
      select(key) { selected = key; redraw(); },
      onRedraw(fn) { redraw = () => { if (last) fn(); }; },
    };
  }
  return { create, SIDE_JOBS };
})();
if (typeof module !== 'undefined') module.exports = MayChayOffice;
