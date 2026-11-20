(() => {
'use strict';
// NHAT-KY-01 (specs/nhat-ky-01.md): Nhật ký công việc dạng bản tin theo ngày (chọn A, 20/11/2026). Chỉ đọc GET /api/v7/nhat-ky.
// Thứ tự đọc: tuần này mấy thay đổi và mảng nào đang chạy (lưới ô ngày từng mảng) → dòng thời gian từng ngày → giờ làm.
// Ít chữ (20/11 chiều): ô không in số, câu lời thường chỉ hiện khi bấm dòng mảng. Bộ lọc chung: mảng, tuần, ngày, giờ. Mỗi khối không tự lọc theo chiều của chính nó để vẫn thấy và đổi được lựa chọn.
// Không đếm là việc: PR chỉ ghi nhật ký/trạng thái triển khai và PR bot nâng thư viện (máy chủ đã lọc, lọc lại cho chắc)
const NOISE = /^(Nhật ký|docs\(deploys?\)|docs: .*(triển khai|hao)|Record .*deployment)|[Bb]ump |chore\(deps/;
function clean(d) {
  const days = {};
  for (const k in d.days) { const ch = d.days[k].changes.filter(c => !NOISE.test(c[1])); if (ch.length) days[k] = { ...d.days[k], changes: ch }; }
  return { ...d, days };
}
let DATA = null;
const LANES = [
  { id: "so-khach", name: "Sổ khách", areas: ["so-khach"] },
  { id: "quan-ly", name: "Màn quản lý", areas: ["tong-quan", "dien-thoai", "zalo"] },
  { id: "may", name: "Máy tự làm", areas: ["may"] },
  { id: "gia", name: "Giá & debit note", areas: ["gia", "debit"] },
  { id: "an-toan", name: "An toàn & nền tảng", areas: ["an-toan", "nen"] },
  { id: "doi-xe", name: "Đội xe", areas: ["doi-xe"] }
];
LANES.forEach((l, i) => l.color = `var(--l${i + 1})`);
const LANE = Object.fromEntries(LANES.map(l => [l.id, l]));
const laneOfArea = a => LANE[a] || LANES.find(l => l.areas.includes(a)) || LANE["an-toan"];
const WD = ["Chủ nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];
const WD_SHORT = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const MAX_WEEKS = 6, PAGE = 7;

const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const btn = (cls, text) => { const b = el("button", cls, text); b.type = "button"; return b; };
const svgEl = (tag, attrs) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
const tip = (node, text) => { node.setAttribute("data-tip", text); return node; };
const dot = color => { const d = el("span", "dot"); d.style.background = color; return d; };
const parse = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const key = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const dm = d => `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
const nf = n => n.toLocaleString("vi-VN");
const mins = c => { const [h, m] = c[6].split(":").map(Number); return h * 60 + m; };
const hourOf = c => Math.floor(mins(c) / 60);
const isWeekend = k => [0, 6].includes(parse(k).getDay());
const wk = k => { const d = parse(k); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return key(d); };
const addDays = (k, n) => { const d = parse(k); d.setDate(d.getDate() + n); return key(d); };
// Giờ hành chính 8h–17h30 thứ Hai–thứ Sáu; còn lại chia ba nhóm ngoài giờ
const KIND = [
  { id: "in", name: "Trong giờ", color: "var(--h-in)" },
  { id: "early", name: "Sáng sớm (trước 8h)", color: "var(--h-early)" },
  { id: "late", name: "Buổi tối (từ 17h30)", color: "var(--h-late)" },
  { id: "weekend", name: "Thứ Bảy, Chủ nhật", color: "var(--h-weekend)" }
];
const kindOf = (k, c) => isWeekend(k) ? "weekend" : mins(c) < 480 ? "early" : mins(c) >= 1050 ? "late" : "in";
// "Hôm nay" theo giờ Việt Nam (DATE-01): en-CA cho dạng yyyy-mm-dd
const vnDay = back => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(Date.now() - back * 86_400_000);
const dayTag = k => k === vnDay(0) ? "Hôm nay" : k === vnDay(1) ? "Hôm qua" : "";

// Bộ lọc chung. lane: mảng; week: thứ Hai đầu tuần (yyyy-mm-dd); day: yyyy-mm-dd; hour: 0–23
let F = { lane: null, week: null, day: null, hour: null };
let G = {}, shown = PAGE;
const open = new Set();   // dòng mảng đang bung trong từng ngày: "ngày|mảng"
function pass(k, c, skip = []) {
  if (F.lane && !skip.includes("lane") && c[2] !== F.lane) return false;
  if (F.week && !skip.includes("week") && wk(k) !== F.week) return false;
  if (F.day && !skip.includes("day") && k !== F.day) return false;
  if (F.hour != null && !skip.includes("hour") && hourOf(c) !== F.hour) return false;
  return true;
}
const anyFilter = () => F.lane || F.week || F.day || F.hour != null;
const rows = skip => G.dates.flatMap(k => DATA.days[k].changes.filter(c => pass(k, c, skip)).map(c => [k, c]));
function setF(patch) {
  for (const d in patch) F[d] = F[d] === patch[d] ? null : patch[d];
  if (patch.day && F.day) F.week = null;
  if (patch.week && F.week) F.day = null;
  shown = PAGE; render();
}
const clearF = () => { F = { lane: null, week: null, day: null, hour: null }; shown = PAGE; render(); };

function derive() {
  const dates = Object.keys(DATA.days).sort(), last = dates[dates.length - 1];
  const weeks = []; for (let w = wk(dates[0]); w <= wk(last); w = addDays(w, 7)) weeks.push(w);
  if (F.week && !weeks.includes(F.week)) F.week = null;
  if (F.day && !DATA.days[F.day]) F.day = null;
  G = { dates, last, weeks, gridWeeks: weeks.slice(-MAX_WEEKS) };
}

// ===== Khối 1: tuần đang xem + lưới ô vuông theo ngày cho từng mảng (kiểu lịch đóng góp GitHub) =====
function renderWeek() {
  const cur = F.week || wk(F.day || G.last), prev = addDays(cur, -7), end = addDays(cur, 6);
  const inWeek = w => rows(["week", "day"]).filter(([k]) => wk(k) === w);
  const now = inWeek(cur), before = inWeek(prev), days = w => new Set(inWeek(w).map(([k]) => k)).size;
  $("weekTitle").textContent = `Tuần ${dm(parse(cur))} – ${dm(parse(end))}`;
  $("weekAside").textContent = cur === wk(vnDay(0)) ? "tuần này" : F.week ? "tuần đã chọn" : "tuần gần nhất";
  const sum = $("weekSum"); sum.replaceChildren();
  const big = el("div", "nk-big"); const n = el("b", "num", nf(now.length)); n.id = "weekNum";
  big.append(n, el("span", null, `thay đổi${F.lane ? " " + LANE[F.lane].name : ""}${F.hour != null ? ` lúc ${F.hour}h` : ""} · ${days(cur)} ngày làm`));
  sum.append(big);
  if (G.weeks.includes(prev)) {
    const p = before.length, delta = el("span", "nk-delta" + (p && now.length >= p ? " up" : ""));
    delta.textContent = p ? `${now.length >= p ? "▲" : "▼"} ${nf(Math.abs(now.length - p))} so tuần trước` : "tuần trước chưa có";
    tip(delta, `Tuần trước: ${nf(p)} thay đổi trong ${days(prev)} ngày`); sum.append(delta);
  }

  // Mỗi mảng một hàng ô ngày; đậm nhạt một sắc theo số thay đổi, không in số (di chuột để xem). Hàng đầu là cả hệ thống.
  const ws = G.gridWeeks, cal = $("cal"); cal.replaceChildren();
  const today = vnDay(0), cnt = {};
  rows(["lane", "week", "day"]).forEach(([k, c]) => { cnt[`${c[2]}|${k}`] = (cnt[`${c[2]}|${k}`] || 0) + 1; cnt[`*|${k}`] = (cnt[`*|${k}`] || 0) + 1; });
  const laneMax = Math.max(1, ...Object.entries(cnt).filter(([key]) => !key.startsWith("*")).map(([, v]) => v));
  const allMax = Math.max(1, ...Object.entries(cnt).filter(([key]) => key.startsWith("*")).map(([, v]) => v));
  const level = (v, mx) => v ? Math.min(4, Math.ceil(v / mx * 4)) : 0;
  const old = j => j < ws.length - 3 ? " old" : "";   // màn hẹp chỉ hiện 3 tuần gần nhất
  // Hàng tiêu đề: nhãn tuần bấm được
  const head = el("div", "cal-row cal-head"); head.append(el("span", "cal-lab"));
  const wrapH = el("div", "cal-weeks");
  ws.forEach((w, j) => {
    const b = btn("cal-wk" + old(j) + (F.week === w ? " on" : ""), dm(parse(w)));
    b.setAttribute("aria-pressed", F.week === w); tip(b, `Xem tuần từ ${dm(parse(w))}`);
    b.addEventListener("click", () => setF({ week: w })); wrapH.append(b);
  });
  head.append(wrapH, el("span", "cal-n", "Tuần"));
  cal.append(head);
  const row = (id, name, color) => {
    const r = el("div", "cal-row" + (id === "*" ? " all" : "") + (F.lane && id !== "*" && F.lane !== id ? " dim" : ""));
    const lab = id === "*" ? el("span", "cal-lab", name) : btn("cal-lab lane" + (F.lane === id ? " on" : ""));
    if (id !== "*") { lab.append(dot(color), el("span", null, name)); lab.setAttribute("aria-pressed", F.lane === id); lab.addEventListener("click", () => setF({ lane: id })); }
    const wrap = el("div", "cal-weeks");
    ws.forEach((w, j) => {
      const g = el("div", "cal-wk7" + old(j) + (F.week && F.week !== w ? " dim" : ""));
      for (let i = 0; i < 7; i++) {
        const k = addDays(w, i), v = cnt[`${id}|${k}`] || 0, label = `${id === "*" ? "Cả hệ thống" : name} · ${WD_SHORT[i]} ${dm(parse(k))}: ${v ? nf(v) + " thay đổi" : "không có"}`;
        if (k > today || k > G.last && !v) { g.append(el("i", "sq fut")); continue; }
        const s = btn(`sq q${level(v, id === "*" ? allMax : laneMax)}` + (F.day === k ? " sel" : ""));
        tip(s, label); s.setAttribute("aria-label", label);
        if (v) s.addEventListener("click", () => { if (id !== "*") F.lane = F.day === k && F.lane === id ? null : id; setF({ day: k }); });
        else s.disabled = true;
        g.append(s);
      }
      wrap.append(g);
    });
    const tot = ws.includes(cur) ? Object.entries(cnt).filter(([key]) => key.startsWith(id + "|") && wk(key.slice(id.length + 1)) === cur).reduce((a, [, v]) => a + v, 0) : 0;
    r.append(lab, wrap, el("b", "cal-n num" + (tot ? "" : " zero"), tot ? nf(tot) : "·"));
    return r;
  };
  cal.append(row("*", "Tất cả"));
  LANES.forEach(l => cal.append(row(l.id, l.name, l.color)));
  const leg = el("div", "cal-leg"); leg.append(el("span", null, "Ít"));
  for (let i = 0; i <= 4; i++) leg.append(el("i", `sq q${i}`));
  leg.append(el("span", null, "Nhiều"));
  cal.append(leg);
}

// ===== Đang làm tiếp =====
function renderNext() {
  const items = DATA.next || [];
  $("next").replaceChildren(...(items.length ? items.map(t => el("li", null, t)) : [el("li", "muted", "Chưa ghi việc tiếp theo.")]));
}

// ===== Thanh lọc =====
function renderFilterBar() {
  const bar = $("fbar"); bar.replaceChildren();
  if (!anyFilter()) return;
  const chip = (patch, label, color) => {
    const c = btn("fchip"); c.setAttribute("aria-label", `Bỏ lọc ${label}`);
    if (color) c.append(dot(color));
    c.append(document.createTextNode(label), el("span", "x", "×"));
    c.addEventListener("click", () => setF(patch)); bar.append(c);
  };
  if (F.lane) chip({ lane: F.lane }, LANE[F.lane].name, LANE[F.lane].color);
  if (F.week) chip({ week: F.week }, `Tuần ${dm(parse(F.week))}`);
  if (F.day) chip({ day: F.day }, `${WD_SHORT[(parse(F.day).getDay() + 6) % 7]} ${dm(parse(F.day))}`);
  if (F.hour != null) chip({ hour: F.hour }, `${F.hour}h–${F.hour + 1}h`);
  const clr = btn("link", "Xóa lọc"); clr.addEventListener("click", clearF); bar.append(clr);
}

// ===== Khối 2: dòng thời gian kiểu GitHub. Mỗi ngày: tiêu đề + mỗi mảng một thanh dài theo số thay đổi;
// câu lời thường và tên thay đổi chỉ hiện khi bấm dòng mảng =====
function renderFeed() {
  const days = [...G.dates].reverse().filter(k => DATA.days[k].changes.some(c => pass(k, c)));
  const list = F.week || F.day ? days : days.slice(0, shown), feed = $("feed");
  feed.replaceChildren();
  $("feedTitle").textContent = anyFilter() ? `Từng ngày · ${nf(rows([]).length)} thay đổi khớp lọc` : "Từng ngày";
  if (!list.length) { feed.append(el("p", "nk-empty", "Không có thay đổi nào khớp lọc.")); }
  const per = k => LANES.map(l => [l, DATA.days[k].changes.filter(c => c[2] === l.id && pass(k, c))]).filter(([, cs]) => cs.length);
  const max = Math.max(1, ...list.flatMap(k => per(k).map(([, cs]) => cs.length)));
  const tl = el("div", "tl");
  list.forEach(k => {
    const d = parse(k), day = DATA.days[k], hit = day.changes.filter(c => pass(k, c)), tag = dayTag(k);
    const art = el("article", "tl-day"); art.dataset.day = k;
    const head = el("div", "tl-head"), when = el("b", "tl-when num", `${WD_SHORT[(d.getDay() + 6) % 7]} ${dm(d)}`);
    head.append(el("span", "tl-node"), when);
    if (tag) head.append(el("span", "tag", tag));
    head.append(el("h3", DATA.headlines[k] ? null : "muted", DATA.headlines[k] || "Các thay đổi trong ngày"),
      tip(el("span", "count num", `${nf(hit.length)}`), `${hit.length} thay đổi, ${hit[0][6]}–${hit[hit.length - 1][6]}`));
    const ul = el("ul", "tl-lanes");
    per(k).sort((a, b) => b[1].length - a[1].length).forEach(([l, cs]) => {
      const id = `${k}|${l.id}`, isOpen = open.has(id) || !!F.lane || F.hour != null;
      const li = el("li"), b = btn("tl-lane"); b.setAttribute("aria-expanded", isOpen);
      const name = el("span", "tl-name"); name.append(dot(l.color), el("span", null, l.name));
      const track = el("span", "tl-track"), bar = el("i"); bar.style.width = `${Math.max(3, cs.length / max * 100)}%`; bar.style.background = l.color; track.append(bar);
      b.append(name, track, el("b", "num", nf(cs.length)), el("span", "chev", "›"));
      b.addEventListener("click", () => { open.has(id) ? open.delete(id) : open.add(id); renderFeed(); });
      li.append(b);
      if (isOpen) {
        const more = el("div", "tl-more");
        const items = (day.items || []).filter(([a]) => laneOfArea(a) === l).map(([, t]) => t);
        if (items.length) { const u = el("ul", "says"); items.forEach(t => u.append(el("li", null, t))); more.append(u); }
        const o = el("ol", "prs");
        [...cs].reverse().forEach(c => { const x = el("li"); x.append(el("span", "t num", c[6]), el("span", null, c[1])); o.append(x); });
        // Có câu lời thường thì tên thay đổi kỹ thuật thu lại một dòng; chưa có câu thì hiện luôn
        if (items.length) { const det = el("details", "tech"); det.append(el("summary", null, `Xem ${nf(cs.length)} thay đổi kỹ thuật`), o); more.append(det); }
        else more.append(o);
        li.append(more);
      }
      ul.append(li);
    });
    art.append(head, ul); tl.append(art);
  });
  feed.append(tl);
  const more = $("more"), rest = days.length - list.length;
  more.hidden = rest <= 0;
  more.textContent = `Xem thêm ${Math.min(PAGE, rest)} ngày (còn ${rest})`;
}
$("more").addEventListener("click", () => { shown += PAGE; renderFeed(); });

// ===== Khối 3: giờ làm. Hai biểu đồ một chiều (theo giờ, theo thứ) thay lưới thứ × giờ =====
function renderHours() {
  const rs = rows(["hour"]), box = $("hours"), tot = rs.length;
  box.replaceChildren();
  $("hoursScope").textContent = F.day ? dm(parse(F.day)) : F.week ? `tuần ${dm(parse(F.week))}` : "cả kỳ";
  if (!tot) { box.append(el("p", "muted", "Chưa có thay đổi.")); return; }
  const by = Object.fromEntries(KIND.map(x => [x.id, 0])); rs.forEach(([k, c]) => by[kindOf(k, c)]++);
  const off = tot - by.in;
  const head = el("div", "nk-big"); const pct = el("b", "num", `${Math.round(off / tot * 100)}%`); pct.id = "offPct";
  head.append(pct, el("span", null, `ngoài giờ hành chính · ${nf(off)}/${nf(tot)} thay đổi`));
  // Thanh chia mảnh mỏng, chú giải là danh sách có số ngay bên dưới
  const bar = el("div", "split");
  KIND.forEach(x => { if (!by[x.id]) return; const i = tip(el("i"), `${x.name}: ${by[x.id]}`); i.style.flex = by[x.id]; i.style.background = x.color; bar.append(i); });
  const leg = el("ul", "kinds");
  KIND.forEach(x => { const li = el("li"); li.append(dot(x.color), el("span", null, x.name), el("b", "num", nf(by[x.id]))); leg.append(li); });

  // Theo giờ trong ngày: cột chồng theo nhóm, nền nhạt là 8h–17h30
  const hours = Array.from({ length: 24 }, () => Object.fromEntries(KIND.map(x => [x.id, 0])));
  rs.forEach(([k, c]) => hours[hourOf(c)][kindOf(k, c)]++);
  const tH = hours.map(h => KIND.reduce((n, x) => n + h[x.id], 0)), mx = Math.max(...tH, 1), peak = tH.indexOf(Math.max(...tH));
  const W = 288, H = 110, B = 92, bw = W / 24, s = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "hist", role: "img", "aria-label": "Số thay đổi theo giờ trong ngày" });
  s.append(svgEl("rect", { x: 8 * bw, y: 0, width: 9.5 * bw, height: B, fill: "var(--head)" }));
  s.append(svgEl("line", { x1: 0, x2: W, y1: B, y2: B, stroke: "var(--line)" }));
  hours.forEach((h, i) => {
    let y = B;
    KIND.forEach(x => {
      if (!h[x.id]) return;
      const hh = h[x.id] / mx * (B - 6);
      s.append(svgEl("rect", { x: i * bw + 1.5, y: y - hh, width: bw - 3, height: Math.max(hh - 1, 1), rx: 1.5, fill: x.color, opacity: F.hour != null && F.hour !== i ? .3 : 1 }));
      y -= hh;
    });
    if (!tH[i]) return;
    const hit = tip(svgEl("rect", { x: i * bw, y: 0, width: bw, height: H, fill: "transparent", class: "pick" + (F.hour === i ? " on" : "") }),
      `${i}h–${i + 1}h: ${tH[i]} thay đổi\n` + KIND.filter(x => h[x.id]).map(x => `${x.name}: ${h[x.id]}`).join("\n"));
    hit.addEventListener("click", () => setF({ hour: i }));
    s.append(hit);
  });
  [0, 6, 12, 18, 24].forEach(hh => { const t = svgEl("text", { x: Math.min(Math.max(hh * bw, 6), W - 8), y: H - 2, "text-anchor": hh === 0 ? "start" : hh === 24 ? "end" : "middle" }); t.textContent = `${hh}h`; s.append(t); });
  const cap = el("p", "cap"); cap.innerHTML = `Nhiều nhất lúc <b>${peak}h</b>. Nền nhạt là 8h–17h30; bấm một cột để xem giờ đó.`;

  // Theo thứ trong tuần
  const wdN = Array(7).fill(0); rs.forEach(([k]) => wdN[(parse(k).getDay() + 6) % 7]++);
  const wmax = Math.max(...wdN, 1), wrow = el("div", "wdays");
  wdN.forEach((n, i) => {
    const c = tip(el("div", "wd" + (i >= 5 ? " we" : "")), `${WD[(i + 1) % 7]}: ${n} thay đổi`), b = el("i");
    b.style.height = `${Math.max(n ? 3 : 0, n / wmax * 36)}px`;
    c.append(el("span", "num", nf(n)), b, el("small", null, WD_SHORT[i])); wrow.append(c);
  });
  box.append(head, bar, leg, el("h3", null, "Theo giờ trong ngày"), s, cap, el("h3", null, "Theo thứ trong tuần"), wrow);
}

// ===== Vẽ lại toàn bộ =====
function render() {
  derive();
  renderWeek(); renderNext(); renderFilterBar(); renderFeed(); renderHours();
}
document.addEventListener("keydown", e => { if (e.key === "Escape" && anyFilter()) clearF(); });

// ===== Chú thích nổi =====
const tipEl = $("tooltip");
document.addEventListener("pointerover", e => {
  const t = e.target.closest && e.target.closest("[data-tip]");
  if (!t) { tipEl.hidden = true; return; }
  tipEl.replaceChildren(...t.getAttribute("data-tip").split("\n").filter(Boolean).map((line, i) => el(i ? "div" : "b", null, line)));
  tipEl.hidden = false;
});
document.addEventListener("pointermove", e => {
  if (tipEl.hidden) return;
  const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
  tipEl.style.left = Math.max(8, Math.min(e.clientX + 12, innerWidth - w - 8)) + "px";
  tipEl.style.top = (e.clientY - h - 12 < 8 ? e.clientY + 16 : e.clientY - h - 12) + "px";
});
document.addEventListener("pointerout", e => { if (!e.relatedTarget || !e.relatedTarget.closest || !e.relatedTarget.closest("[data-tip]")) tipEl.hidden = true; });
document.addEventListener("click", () => { tipEl.hidden = true; });

// ===== Sáng / Tối / Theo máy (nhat-ky-theme.js đã áp lựa chọn trước khi vẽ trang) =====
(() => {
  const theme = window.nkTheme; if (!theme) return;
  const MODES = [["light", "Sáng"], ["dark", "Tối"], ["auto", "Theo máy"]];
  const paint = () => $("mode").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.mode === theme.get()));
  MODES.forEach(([id, name]) => {
    const b = btn("", name); b.dataset.mode = id;
    if (id === "auto") tip(b, "Theo cài đặt sáng/tối của máy");
    b.addEventListener("click", () => { theme.set(id); paint(); });   // màu đều là biến CSS nên không cần vẽ lại
    $("mode").append(b);
  });
  paint();
})();

// ===== Tự cập nhật: đọc GET /api/v7/nhat-ky mỗi 60 giây khi tab đang mở =====
const POLL_MS = 60_000;
let seen = null, toastTimer = null, failed = false;
function paintLive(body) {
  const box = $("live");
  box.className = "live" + (failed ? " warn" : body && !body.error ? " on" : " warn");
  $("liveTxt").textContent = failed ? "Chưa đọc được máy chủ, đang thử lại"
    : body?.error ? `${body.error} · số liệu lúc ${body.checked_at || "—"}` : `Trực tiếp · GitHub lúc ${body?.checked_at || "—"}`;
  tip(box, "Máy chủ hỏi GitHub mỗi 5 phút; trang đọc lại máy chủ mỗi phút");
}
function toast(n, latestTitle) {
  const t = $("toast"); t.replaceChildren(el("b", null, `+${n} thay đổi mới`), el("span", null, latestTitle || ""));
  t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 6000);
  const num = $("weekNum"); if (num) { num.classList.remove("flash"); void num.offsetWidth; num.classList.add("flash"); }
}
const okChange = c => Array.isArray(c) && c.length >= 7 && typeof c[0] === "string" && typeof c[1] === "string" && typeof c[6] === "string"
  && /^\d\d:\d\d$/.test(c[6]) && [3, 4, 5].every(i => Number.isFinite(c[i]));
function fromApi(body) {
  const days = {}, headlines = {};
  for (const [k, v] of Object.entries(body.days || {})) {
    if (!/^\d{4}-\d\d-\d\d$/.test(k) || !v || !Array.isArray(v.changes)) continue;
    const changes = v.changes.filter(okChange).map(c => [c[0], c[1], LANE[c[2]] ? c[2] : "so-khach", c[3], c[4], c[5], c[6]])
      .sort((a, b) => a[6].localeCompare(b[6]));
    if (!changes.length) continue;
    days[k] = { items: Array.isArray(v.items) ? v.items.filter(i => Array.isArray(i) && typeof i[1] === "string") : [], changes };
    headlines[k] = typeof v.headline === "string" ? v.headline : "";
  }
  if (!Object.keys(days).length) return null;
  return clean({ updated: body.checked_at || "", headlines, days,
    highlights: Array.isArray(body.highlights) ? body.highlights : [], next: Array.isArray(body.next) ? body.next : [] });
}
async function load() {
  let body;
  try {
    const response = await fetch("/api/v7/nhat-ky", { cache: "no-store" });
    body = await response.json();
    if (!response.ok) throw Error(body?.message || "nhat-ky");
    failed = false;
  } catch {
    failed = true; paintLive(null);
    if (!DATA) { $("error").textContent = "Chưa đọc được Nhật ký công việc từ máy chủ. Trang tự thử lại sau một phút."; $("error").hidden = false; }
    return;
  }
  $("error").hidden = true;
  const next = fromApi(body);
  if (!next || !Object.keys(next.days).length) { $("error").textContent = "Máy chủ chưa có dữ liệu Nhật ký công việc."; $("error").hidden = false; paintLive(body); return; }
  const ids = Object.values(next.days).flatMap(d => d.changes.map(c => c[0]));
  const fresh = seen ? ids.filter(id => !seen.has(id)) : [];
  DATA = next; seen = new Set(ids);
  render(); paintLive(body);
  document.body.dataset.loaded = "1";
  if (fresh.length) {
    const all = Object.keys(DATA.days).sort().flatMap(k => DATA.days[k].changes);
    toast(fresh.length, all.filter(c => fresh.includes(c[0])).pop()?.[1]);
  }
}
load();
setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
})();
