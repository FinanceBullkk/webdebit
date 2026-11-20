(() => {
'use strict';
// NHAT-KY-01 (specs/nhat-ky-01.md): Nhật ký công việc dạng bản tin theo ngày (chọn A, 20/11/2026). Chỉ đọc GET /api/v7/nhat-ky.
// Thứ tự đọc: tuần này mấy thay đổi và mảng nào đang chạy (bảng mảng × tuần) → từng ngày bằng lời thường → giờ làm.
// Bộ lọc chung: mảng, tuần, giờ. Mỗi khối không tự lọc theo chiều của chính nó để vẫn thấy và đổi được lựa chọn.
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
const MAX_WEEKS = 8, PAGE = 7;

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

// Bộ lọc chung. lane: mảng; week: thứ Hai đầu tuần (yyyy-mm-dd); hour: 0–23
let F = { lane: null, week: null, hour: null };
let G = {}, shown = PAGE;
function pass(k, c, skip = []) {
  if (F.lane && !skip.includes("lane") && c[2] !== F.lane) return false;
  if (F.week && !skip.includes("week") && wk(k) !== F.week) return false;
  if (F.hour != null && !skip.includes("hour") && hourOf(c) !== F.hour) return false;
  return true;
}
const anyFilter = () => F.lane || F.week || F.hour != null;
const rows = skip => G.dates.flatMap(k => DATA.days[k].changes.filter(c => pass(k, c, skip)).map(c => [k, c]));
function setF(patch) {
  for (const d in patch) F[d] = F[d] === patch[d] ? null : patch[d];
  shown = PAGE; render();
}
const clearF = () => { F = { lane: null, week: null, hour: null }; shown = PAGE; render(); };

function derive() {
  const dates = Object.keys(DATA.days).sort(), last = dates[dates.length - 1];
  const weeks = []; for (let w = wk(dates[0]); w <= wk(last); w = addDays(w, 7)) weeks.push(w);
  if (F.week && !weeks.includes(F.week)) F.week = null;
  G = { dates, last, weeks, shownWeeks: weeks.slice(-MAX_WEEKS), highlight: {} };
  (DATA.highlights || []).forEach(h => { const l = laneOfArea(h.area); if (!G.highlight[l.id]) G.highlight[l.id] = h; });
}

// ===== Khối 1: tuần đang xem + bảng mảng × tuần =====
function renderWeek() {
  const cur = F.week || wk(G.last), prev = addDays(cur, -7), end = addDays(cur, 6);
  const inWeek = w => rows(["week"]).filter(([k]) => wk(k) === w);
  const now = inWeek(cur), before = inWeek(prev), days = w => new Set(inWeek(w).map(([k]) => k)).size;
  $("weekTitle").textContent = `Tuần ${dm(parse(cur))} – ${dm(parse(end))}`;
  $("weekAside").textContent = cur === wk(vnDay(0)) ? "tuần này" : F.week ? "tuần đã chọn" : "tuần gần nhất";
  const sum = $("weekSum"); sum.replaceChildren();
  const big = el("div", "nk-big"); const n = el("b", "num", nf(now.length)); n.id = "weekNum";
  big.append(n, el("span", null, `thay đổi${F.lane ? " " + LANE[F.lane].name : ""}${F.hour != null ? ` lúc ${F.hour}h` : ""} trong ${days(cur)} ngày làm`));
  sum.append(big);
  const facts = el("ul", "nk-facts");
  if (G.weeks.includes(prev)) facts.append(el("li", null, before.length ? `Tuần trước: ${nf(before.length)} thay đổi trong ${days(prev)} ngày` : "Tuần trước: chưa có"));
  const top = LANES.map(l => [l, now.filter(([, c]) => c[2] === l.id).length]).sort((a, b) => b[1] - a[1])[0];
  if (top && top[1] && !F.lane) { const li = el("li"); li.append("Làm nhiều nhất: ", dot(top[0].color), el("b", null, top[0].name), ` (${nf(top[1])})`); facts.append(li); }
  sum.append(facts);

  // Bảng nhiệt một màu: hàng là mảng (chấm màu = danh tính), cột là tuần, số trong ô là số thay đổi
  const ws = G.shownWeeks, cell = (lane, w) => rows(["lane", "week"]).filter(([k, c]) => c[2] === lane && wk(k) === w).length;
  const counts = LANES.map(l => ws.map(w => cell(l.id, w))), max = Math.max(1, ...counts.flat());
  const level = v => v ? Math.min(5, 1 + Math.floor(v / max * 4.999)) : 0;
  const t = $("matrix"); t.replaceChildren();
  const hr = el("tr"); hr.append(el("th", "lane-h", "Mảng"));
  const old = j => j < ws.length - 5 ? "old" : "";   // màn hẹp chỉ hiện 5 tuần gần nhất
  ws.forEach((w, j) => {
    const th = el("th", old(j)), b = btn("wk" + (F.week === w ? " on" : F.week ? " dim" : ""), dm(parse(w)));
    b.setAttribute("aria-pressed", F.week === w); tip(b, `Xem tuần từ ${dm(parse(w))}`);
    b.addEventListener("click", () => setF({ week: w })); th.append(b); hr.append(th);
  });
  hr.append(el("th", "last-h", "Gần nhất"));
  const thead = el("thead"); thead.append(hr);
  const tbody = el("tbody");
  LANES.forEach((l, i) => {
    const tr = el("tr", F.lane && F.lane !== l.id ? "dim" : ""), th = el("th"), b = btn("lane" + (F.lane === l.id ? " on" : ""));
    const h = G.highlight[l.id], txt = el("span", "lt");
    txt.append(el("b", null, l.name)); if (h && h.text) txt.append(el("small", null, h.text));
    b.append(dot(l.color), txt); b.setAttribute("aria-pressed", F.lane === l.id);
    tip(b, h ? `${h.title}\n${h.text || ""}` : l.name);
    b.addEventListener("click", () => setF({ lane: l.id })); th.append(b); tr.append(th);
    counts[i].forEach((v, j) => {
      const td = el("td", old(j)), w = ws[j];
      if (v) {
        const c = btn(`hc h${level(v)}` + (F.lane === l.id && F.week === w ? " on" : "") + (F.week && F.week !== w ? " dim" : ""), nf(v));
        tip(c, `${l.name}, tuần ${dm(parse(w))}: ${v} thay đổi`); c.setAttribute("aria-label", `${l.name}, tuần ${dm(parse(w))}: ${v} thay đổi`);
        c.addEventListener("click", () => { F.lane = F.lane === l.id && F.week === w ? null : l.id; F.week = F.lane ? w : null; shown = PAGE; render(); });
        td.append(c);
      } else td.append(el("span", "hc h0", "·"));
      tr.append(td);
    });
    const lastK = [...G.dates].reverse().find(k => DATA.days[k].changes.some(c => c[2] === l.id));
    const ago = lastK ? Math.round((parse(G.last) - parse(lastK)) / 86_400_000) : null;
    tr.append(el("td", "last" + (ago > 7 ? " stale" : ""), lastK ? (dayTag(lastK) || dm(parse(lastK))) : "—"));
    tbody.append(tr);
  });
  const tf = el("tr", "total"); tf.append(el("th", null, "Tổng"));
  ws.forEach((w, j) => tf.append(el("td", `num ${old(j)}` + (F.week && F.week !== w ? " dim" : ""), nf(counts.reduce((n, r) => n + r[j], 0)))));
  tf.append(el("td"));
  const tfoot = el("tfoot"); tfoot.append(tf);
  t.append(thead, tbody, tfoot);
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
  if (F.hour != null) chip({ hour: F.hour }, `${F.hour}h–${F.hour + 1}h`);
  const clr = btn("link", "Xóa lọc"); clr.addEventListener("click", clearF); bar.append(clr);
}

// ===== Khối 2: từng ngày, mới nhất trước, bằng lời thường =====
function renderFeed() {
  const days = [...G.dates].reverse().filter(k => DATA.days[k].changes.some(c => pass(k, c)));
  const list = F.week ? days : days.slice(0, shown), feed = $("feed");
  feed.replaceChildren();
  $("feedTitle").textContent = anyFilter() ? `Từng ngày · ${nf(rows([]).length)} thay đổi khớp lọc` : "Từng ngày";
  if (!list.length) feed.append(el("p", "nk-empty", "Không có thay đổi nào khớp lọc."));
  list.forEach(k => {
    const d = parse(k), day = DATA.days[k], ch = day.changes, hit = ch.filter(c => pass(k, c));
    const art = el("article", "nk-day"); art.dataset.day = k;
    const when = el("div", "when"), tag = dayTag(k);
    when.append(el("b", null, WD_SHORT[(d.getDay() + 6) % 7]), el("span", "num", dm(d)));
    if (tag) when.append(el("span", "tag", tag));
    const body = el("div", "body"), head = el("div", "dhead");
    head.append(el("h3", DATA.headlines[k] ? null : "muted", DATA.headlines[k] || "Các thay đổi trong ngày"),
      el("span", "count num", anyFilter() ? `${hit.length}/${ch.length} thay đổi` : `${ch.length} thay đổi · ${ch[0][6]}–${ch[ch.length - 1][6]}`));
    body.append(head);
    // Câu cùng mảng đứng liền nhau theo thứ tự mảng, nhãn mảng chỉ in ở câu đầu nhóm
    const items = (day.items || []).map(([a, txt], i) => [laneOfArea(a), txt, i]).filter(([l]) => !F.lane || l.id === F.lane)
      .sort((a, b) => LANES.indexOf(a[0]) - LANES.indexOf(b[0]) || a[2] - b[2]);
    if (items.length) {
      const ul = el("ul", "items");
      items.forEach(([l, txt], i) => {
        const li = el("li", i && items[i - 1][0] === l ? "cont" : ""), lab = el("span", "lname");
        if (!li.className) lab.append(dot(l.color), document.createTextNode(l.name));
        li.append(lab, el("span", "txt", txt)); ul.append(li);
      });
      body.append(ul);
    } else if (F.lane || !(day.items || []).length) {
      body.append(el("p", "muted note", F.lane ? `Tóm tắt ngày không nhắc riêng ${LANE[F.lane].name}; xem danh sách thay đổi bên dưới.` : "Chưa có tóm tắt lời thường cho ngày này."));
    }
    const det = el("details", "tech"); det.open = F.hour != null || !items.length;
    det.append(el("summary", null, anyFilter() && hit.length < ch.length ? `Danh sách thay đổi (${hit.length} khớp lọc)` : `Danh sách thay đổi (${ch.length})`));
    const ol = el("ol");
    [...(anyFilter() ? hit : ch)].reverse().forEach(c => {
      const li = el("li"); li.append(el("span", "t num", c[6]), dot(LANE[c[2]].color), el("span", null, c[1])); ol.append(li);
    });
    det.append(ol); body.append(det);
    art.append(when, body); feed.append(art);
  });
  const more = $("more"), rest = days.length - list.length;
  more.hidden = rest <= 0;
  more.textContent = `Xem thêm ${Math.min(PAGE, rest)} ngày (còn ${rest})`;
}
$("more").addEventListener("click", () => { shown += PAGE; renderFeed(); });

// ===== Khối 3: giờ làm. Hai biểu đồ một chiều (theo giờ, theo thứ) thay lưới thứ × giờ =====
function renderHours() {
  const rs = rows(["hour"]), box = $("hours"), tot = rs.length;
  box.replaceChildren();
  $("hoursScope").textContent = F.week ? `tuần ${dm(parse(F.week))}` : "cả kỳ";
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
