(() => {
'use strict';
// NHAT-KY-01 (specs/nhat-ky-01.md): Nhật ký công việc, bố cục trang hồ sơ GitHub. Chỉ đọc GET /api/v7/nhat-ky.
// Dữ liệu nhúng lúc đăng (bản chụp); khi xem trong claude.ai, trang nghe cơ sở dữ liệu và vẽ lại khi có thay đổi.
// Lọc chéo: bấm mảng, ngày, tuần hoặc ô giờ ở bất kỳ đâu thì mọi hộp khác lọc theo;
// mỗi hộp không tự lọc theo chiều của chính nó (để vẫn thấy và đổi được lựa chọn).
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
// Octicons 16px (GitHub)
const OCT = {
  calendar: "M4.75 0a.75.75 0 0 1 .75.75V2h5V.75a.75.75 0 0 1 1.5 0V2h1.25c.966 0 1.75.784 1.75 1.75v10.5A1.75 1.75 0 0 1 13.25 16H2.75A1.75 1.75 0 0 1 1 14.25V3.75C1 2.784 1.784 2 2.75 2H4V.75A.75.75 0 0 1 4.75 0ZM2.5 7.5v6.75c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25V7.5Zm10.75-4H2.75a.25.25 0 0 0-.25.25V6h11V3.75a.25.25 0 0 0-.25-.25Z",
  merge: "M5.45 5.154A4.25 4.25 0 0 0 9.25 7.5h1.378a2.251 2.251 0 1 1 0 1.5H9.25A5.734 5.734 0 0 1 5 7.123v3.505a2.25 2.25 0 1 1-1.5 0V5.372a2.25 2.25 0 1 1 1.95-.218ZM4.25 13.5a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm8.5-4.5a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5ZM5 3.25a.75.75 0 1 0 0 .005V3.25Z",
  clock: "M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm7-3.25v2.992l2.028.812a.75.75 0 0 1-.557 1.392l-2.5-1A.751.751 0 0 1 7 8.25v-3.5a.75.75 0 0 1 1.5 0Z",
  pulse: "M6 2c.306 0 .582.187.696.471L10 10.731l1.304-3.26A.751.751 0 0 1 12 7h3.25a.75.75 0 0 1 0 1.5h-2.742l-1.812 4.528a.751.751 0 0 1-1.392 0L6 4.77 4.696 8.03A.75.75 0 0 1 4 8.5H.75a.75.75 0 0 1 0-1.5h2.742l1.812-4.529A.751.751 0 0 1 6 2Z",
  commit: "M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z",
  repo: "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.71 1.71.75.75 0 0 1-1.06 1.06A2.49 2.49 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.71A2.49 2.49 0 0 1 4.5 9h8Z",
  book: "M0 1.75A.75.75 0 0 1 .75 1h4.253c1.227 0 2.317.59 3 1.501A3.743 3.743 0 0 1 11.006 1h4.245a.75.75 0 0 1 .75.75v10.5a.75.75 0 0 1-.75.75h-4.507a2.25 2.25 0 0 0-1.591.659l-.622.621a.75.75 0 0 1-1.06 0l-.622-.621A2.25 2.25 0 0 0 5.258 13H.75a.75.75 0 0 1-.75-.75Zm7.251 10.324.004-5.073-.002-2.253A2.25 2.25 0 0 0 5.003 2.5H1.5v9h3.757a3.75 3.75 0 0 1 1.994.574ZM8.755 4.75l-.004 7.322a3.752 3.752 0 0 1 1.992-.572H14.5v-9h-3.495a2.25 2.25 0 0 0-2.25 2.25Z",
  open: "M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"
};
const oct = (name, fill) => `<svg class="oct" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"${fill ? ` style="fill:${fill}"` : ""}><path d="${OCT[name]}"/></svg>`;

const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const svgEl = (tag, attrs) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
const tip = (node, text) => { node.setAttribute("data-tip", text); return node; };
const parse = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const key = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const dm = d => `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
const dmy = d => `${dm(d)}/${d.getFullYear()}`;
const nf = n => n.toLocaleString("vi-VN");
const dec = (v, n = 1) => v.toLocaleString("vi-VN", { maximumFractionDigits: n });
const sum = (xs, i) => xs.reduce((n, c) => n + c[i], 0);
const mins = c => { const [h, m] = c[6].split(":").map(Number); return h * 60 + m; };
const isWeekend = k => [0, 6].includes(parse(k).getDay());
// Ngoài giờ hành chính: trước 8h, từ 17h30, hoặc thứ Bảy, Chủ nhật
const offHours = (k, c) => isWeekend(k) || mins(c) < 480 || mins(c) >= 1050;
const wk = k => { const d = parse(k); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return key(d); };
const slotOf = (k, c) => `${(parse(k).getDay() + 6) % 7}-${Math.floor(mins(c) / 60)}`;

let MONTH = "all";
try { MONTH = localStorage.getItem("nk-month") || "all"; } catch { /* trình duyệt chặn lưu: dùng mặc định */ }
// Bộ lọc chung. lane: mảng; day: yyyy-mm-dd; week: thứ Hai đầu tuần; slot: "thứ-giờ" (0 = T2)
let F = { lane: null, day: null, week: null, slot: null };
let openDay = null, G = {};

function pass(k, c, skip = []) {
  if (F.lane && !skip.includes("lane") && c[2] !== F.lane) return false;
  if (F.day && !skip.includes("day") && k !== F.day) return false;
  if (F.week && !skip.includes("week") && wk(k) !== F.week) return false;
  if (F.slot && !skip.includes("slot") && slotOf(k, c) !== F.slot) return false;
  return true;
}
const chF = (k, skip) => DATA.days[k] ? DATA.days[k].changes.filter(c => pass(k, c, skip)) : [];
const anyFilter = () => Object.values(F).some(Boolean);
function setF(dim, val) { F[dim] = F[dim] === val ? null : val; render(); }
const clearF = () => { F = { lane: null, day: null, week: null, slot: null }; render(); };

function derive() {
  const dates = Object.keys(DATA.days).sort();
  const toK = [dates[dates.length - 1], DATA.period.to].sort().pop();
  const from = parse(DATA.period.from), to = parse(toK);
  const allDays = []; for (let d = new Date(from); d <= to; d.setDate(d.getDate() + 1)) allDays.push(key(d));
  const months = [...new Set(allDays.map(k => k.slice(0, 7)))].reverse();
  if (MONTH !== "all" && !months.includes(MONTH)) MONTH = "all";
  if (F.day && !DATA.days[F.day]) F.day = null;
  // Ngày đang lọc nằm ngoài tháng đang xem thì chuyển về tháng của ngày đó
  if (F.day && MONTH !== "all" && F.day.slice(0, 7) !== MONTH) MONTH = F.day.slice(0, 7);
  const inScope = k => MONTH === "all" || k.slice(0, 7) === MONTH;
  const ch = k => DATA.days[k].changes;
  G = { dates, from, to, allDays, months, ch, cnt: k => ch(k).length,
        rDays: allDays.filter(inScope), rDates: dates.filter(inScope), all: dates.flatMap(ch) };
}
const rangeF = skip => G.rDates.flatMap(k => chF(k, skip).map(c => [k, c]));

// ===== Tab =====
const VIEWS = [{ id: "tong-quan", name: "Tổng quan", icon: "book" }, { id: "cay", name: "Cây công việc", icon: "merge" }];
VIEWS.forEach(v => {
  const b = el("button", "tab"); b.type = "button"; b.dataset.view = v.id;
  b.innerHTML = oct(v.icon); b.append(el("span", null, v.name));
  if (v.id === "cay") { const c = el("span", "counter"); c.id = "cnt-cay"; b.append(c); }
  b.addEventListener("click", () => { location.hash = v.id; });
  $("tabs").append(b);
});
function route() {
  const id = VIEWS.some(v => v.id === location.hash.slice(1)) ? location.hash.slice(1) : "tong-quan";
  VIEWS.forEach(v => { $("view-" + v.id).hidden = v.id !== id; });
  document.querySelectorAll(".tab").forEach(t => { t.classList.toggle("on", t.dataset.view === id); t.setAttribute("aria-current", t.dataset.view === id ? "page" : "false"); });
}
addEventListener("hashchange", route);
function renderMonths() {
  $("seg").replaceChildren(...["all", ...G.months].map(m => {
    const b = el("button", MONTH === m ? "on" : "", m === "all" ? "Tất cả" : `Tháng ${+m.slice(5)}`); b.type = "button";
    b.addEventListener("click", () => { MONTH = m; try { localStorage.setItem("nk-month", m); } catch { /* bỏ qua */ } render(); });
    return b;
  }));
}

// ===== Cột trái: avatar identicon, thông tin, huy hiệu, việc tiếp theo =====
(() => {
  // Identicon 5×5 đối xứng như avatar mặc định của GitHub, sinh cố định từ tên
  let h = 2166136261; for (const ch of "cong-no-doi-xe") { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; }
  const s = svgEl("svg", { viewBox: "0 0 70 70", role: "img", "aria-label": "Ảnh đại diện" });
  s.append(svgEl("rect", { width: 70, height: 70, fill: "var(--bg-subtle)" }));
  for (let r = 0; r < 5; r++) for (let c = 0; c < 3; c++) {
    if ((h >> (r * 3 + c)) & 1) [...new Set([c, 4 - c])].forEach(cc => s.append(svgEl("rect", { x: 10 + cc * 10, y: 10 + r * 10, width: 10, height: 10, fill: "var(--c3)" })));
  }
  $("avatar").append(s);
})();
function bestStreak(has) {
  let best = { len: 0 }, run = 0, start = null;
  G.allDays.forEach(k => { if (has(k)) { if (!run) start = k; run++; if (run > best.len) best = { len: run, a: start, b: k }; } else run = 0; });
  return best;
}
function renderSide() {
  const days = G.dates.length, streak = bestStreak(k => DATA.days[k]);
  const meta = [
    ["merge", `<b>${nf(G.all.length)}</b> thay đổi`],
    ["pulse", `<b>${days}</b>/${G.allDays.length} ngày có việc`],
    ["commit", `<span class="add">+${nf(sum(G.all, 3))}</span> / <span class="del">−${nf(sum(G.all, 4))}</span> dòng`],
    ["calendar", `${dm(G.from)} – ${dmy(G.to)}`]
  ];
  $("pmeta").replaceChildren(...meta.map(([i, h]) => { const li = el("li"); li.innerHTML = oct(i) + `<span>${h}</span>`; return li; }));
  // Huy hiệu kiểu Achievements: đĩa tròn có số, chú thích ngắn bên dưới
  const off = G.dates.reduce((n, k) => n + G.ch(k).filter(c => offHours(k, c)).length, 0);
  const badges = [
    [`${streak.len}`, "ngày liền", "var(--c3)", `Chuỗi dài nhất ${streak.len} ngày liền không nghỉ${streak.len ? ": " + dm(parse(streak.a)) + " → " + dm(parse(streak.b)) : ""}`],
    [`${Math.round(off / G.all.length * 100)}%`, "ngoài giờ", "var(--attention)", `${nf(off)} / ${nf(G.all.length)} thay đổi trước 8h, từ 17h30 hoặc cuối tuần`],
    [`${G.dates.filter(isWeekend).length}`, "cuối tuần", "var(--l2)", "Số ngày thứ Bảy, Chủ nhật có việc"]
  ];
  $("achv").replaceChildren(...badges.map(([v, t, col, hint]) => {
    const b = tip(el("div", "badge"), hint), d = el("div", "disc", v); d.style.background = col; b.append(d, el("span", null, t)); return b;
  }));
  $("next").replaceChildren(...(DATA.next || []).map(t => { const r = el("div"); r.innerHTML = oct("open", "var(--success)"); r.append(el("span", null, t)); return r; }));
}

// ===== Thanh lọc đang áp =====
function renderFilterBar() {
  const bar = $("fbar"); bar.replaceChildren(); bar.hidden = !anyFilter();
  if (!anyFilter()) return;
  bar.append(el("span", "fcount", `Đang xem ${nf(rangeF([]).length)} thay đổi`));
  const chip = (dim, label, color) => {
    const c = el("button", "fchip"); c.type = "button"; c.setAttribute("aria-label", `Bỏ lọc ${label}`);
    if (color) { const d = el("span", "dot"); d.style.background = color; c.append(d); }
    c.append(document.createTextNode(label), el("span", "x", "×"));
    c.addEventListener("click", () => setF(dim, F[dim])); bar.append(c);
  };
  if (F.lane) chip("lane", LANE[F.lane].name, LANE[F.lane].color);
  if (F.day) chip("day", `${WD[parse(F.day).getDay()]} ${dm(parse(F.day))}`);
  if (F.week) chip("week", `Tuần từ ${dm(parse(F.week))}`);
  if (F.slot) { const [r, h] = F.slot.split("-").map(Number); chip("slot", `${WD_SHORT[r]}, ${h}h–${h + 1}h`); }
  if (F.day) { const b = el("button", "link", "Chi tiết ngày →"); b.type = "button"; b.addEventListener("click", () => openDetail(F.day)); bar.append(b); }
  const clr = el("button", "link", "Xóa lọc"); clr.type = "button"; clr.addEventListener("click", clearF); bar.append(clr);
}

// Thanh kiểu "Languages": đoạn màu theo tỷ lệ + chú giải (chấm, tên, số); bấm để lọc mảng
function langBar(bar, legend, rows, withPct) {
  const tot = rows.length;
  LANES.forEach(l => {
    const n = rows.filter(c => c[2] === l.id).length; if (!n) return;
    const seg = tip(el("button", F.lane && F.lane !== l.id ? "fade" : ""), `${l.name}: ${n} (${Math.round(n / tot * 100)}%)`);
    seg.type = "button"; seg.style.flex = n; seg.style.background = l.color; seg.setAttribute("aria-label", `Lọc ${l.name}`);
    seg.addEventListener("click", () => setF("lane", l.id)); bar.append(seg);
  });
  LANES.map(l => [l, rows.filter(c => c[2] === l.id).length]).filter(p => p[1] || withPct).sort((a, b) => b[1] - a[1]).forEach(([l, n]) => {
    const b = el("button", F.lane && F.lane !== l.id ? "fade" : ""); b.type = "button";
    const d = el("span", "dot"); d.style.background = l.color;
    b.append(d, el("b", null, l.name), el("span", "pct", withPct ? `${tot ? Math.round(n / tot * 100) : 0}% · ${n}` : `${n}`));
    b.addEventListener("click", () => setF("lane", l.id)); legend.append(b);
  });
}

// ===== Hộp Hôm nay: hàng số liệu kiểu Pulse, dòng giờ, thanh mảng kiểu Languages =====
function renderToday() {
  const { dates } = G, latest = dates[dates.length - 1], ld = parse(latest), lch = G.ch(latest);
  // "Hôm nay" theo giờ Việt Nam (DATE-01): en-CA cho dạng yyyy-mm-dd
  const vnDay = back => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(Date.now() - back * 86_400_000);
  const tag = latest === vnDay(0) ? "Hôm nay" : latest === vnDay(1) ? "Hôm qua" : "Ngày làm gần nhất";
  $("todayHead").textContent = `${tag} · ${WD[ld.getDay()]} ${dm(ld)} · ${DATA.headlines[latest] || ""}`;
  const more = el("button", "link", "Chi tiết →"); more.type = "button"; more.addEventListener("click", () => openDetail(latest));
  $("todayLink").replaceChildren(more);
  const avg = G.all.length / dates.length, rank = [...dates].sort((a, b) => G.cnt(b) - G.cnt(a)).indexOf(latest) + 1;
  const stat = (v, label, graphic, hint, cls, id) => {
    const d = tip(el("div", "stat"), hint), top = el("div", "stat-v"), b = el("b", cls, v);
    if (id) b.id = id; top.append(b, el("span", null, label)); d.append(top, graphic); $("todayStats").append(d);
  };
  { // Số thay đổi so với trung bình: thanh tiến độ, vạch đen là trung bình
    const mx = Math.max(lch.length, avg) * 1.1, p = el("div", "Progress"), i = el("i"); i.style.width = (lch.length / mx * 100) + "%"; i.style.background = "var(--c3)"; p.append(i);
    const wrap = el("div"); wrap.style.position = "relative"; wrap.append(p);
    const mark = el("i"); Object.assign(mark.style, { position: "absolute", top: "-3px", bottom: "-3px", width: "2px", background: "var(--fg)", left: (avg / mx * 100) + "%" }); wrap.append(mark);
    stat(lch.length, `thay đổi · ×${dec(lch.length / avg)} TB`, wrap, `Hôm nay ${lch.length}, trung bình ${dec(avg)}/ngày làm (vạch đen)`, "num", "todayNum");
  }
  { // Hạng: cột mọi ngày xếp giảm dần, hôm nay tô xanh
    const sorted = [...dates].sort((a, b) => G.cnt(b) - G.cnt(a)), mx = G.cnt(sorted[0]), W = 120, H = 24, bw = W / sorted.length;
    const s = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "mini", preserveAspectRatio: "none" });
    sorted.forEach((k, i) => { const h = Math.max(1.5, G.cnt(k) / mx * H); s.append(svgEl("rect", { x: i * bw + .4, y: H - h, width: Math.max(bw - .8, .6), height: h, fill: k === latest ? "var(--c3)" : "var(--border)" })); });
    stat(`#${rank}`, `/ ${dates.length} ngày`, s, `Xếp thứ ${rank} trong ${dates.length} ngày làm`, "num");
  }
  { // Dòng thêm và bỏ
    const a = sum(lch, 3), r = sum(lch, 4), p = el("div", "Progress");
    const ia = el("i"), ir = el("i"); ia.style.flex = a || 1; ia.style.background = "var(--success)"; ir.style.flex = r; ir.style.background = "var(--danger)"; p.append(ia, ir);
    stat("+" + nf(a), `−${nf(r)} dòng`, p, `${nf(a)} dòng thêm, ${nf(r)} dòng bỏ, ${nf(sum(lch, 5))} file`, "num add");
  }
  // Dòng giờ: mỗi chấm một thay đổi; đoạn xanh trên trục là từ thay đổi đầu tới cuối
  const W = Math.max(300, Math.round($("tline").getBoundingClientRect().width - 32) || 720), BK = W < 600 ? 60 : 20;
  const L = 8, R = 8, AX = 22, r = 5, step = 11, x = m => L + (W - L - R) * m / 1440;
  const buckets = {};
  const pts = lch.map(c => { const b = Math.floor(mins(c) / BK); buckets[b] = (buckets[b] || 0) + 1; return { c, b, i: buckets[b] }; });
  const H = AX + 18 + Math.max(...Object.values(buckets)) * step, base = H - AX;
  const s = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Giờ đưa từng thay đổi lên trong ngày" });
  s.append(svgEl("rect", { x: x(480), y: 0, width: x(1050) - x(480), height: base, fill: "var(--counter)", rx: 4 }));
  const wt = svgEl("text", { x: (x(480) + x(1050)) / 2, y: 12, "text-anchor": "middle" }); wt.textContent = "giờ hành chính"; s.append(wt);
  s.append(svgEl("line", { x1: L, x2: W - R, y1: base, y2: base, stroke: "var(--border)" }));
  const x1 = x(mins(lch[0])), x2 = x(mins(lch[lch.length - 1]));
  s.append(svgEl("line", { x1, x2, y1: base, y2: base, stroke: "var(--accent)", "stroke-width": 3, "stroke-linecap": "round" }));
  const ends = [[x1, lch[0][6], "end"], [x2, lch[lch.length - 1][6], "start"]];
  for (let hh = 0; hh <= 24; hh += 3) {
    const hx = x(hh * 60); if (ends.some(([ex]) => Math.abs(ex - hx) < 46)) continue;
    const t = svgEl("text", { x: hx, y: H - 5, "text-anchor": hh === 0 ? "start" : hh === 24 ? "end" : "middle" }); t.textContent = `${hh}h`; s.append(t);
  }
  ends.forEach(([ex, txt, anchor]) => { const t = svgEl("text", { x: ex + (anchor === "end" ? 4 : -4), y: H - 5, "text-anchor": anchor, style: "fill:var(--accent);font-weight:600" }); t.textContent = txt; s.append(t); });
  pts.forEach(p => {
    const dot = tip(svgEl("circle", { cx: x(p.b * BK + BK / 2), cy: base - 3 - r - (p.i - 1) * step, r, fill: LANE[p.c[2]].color, class: "pick" }),
      `${p.c[6]} · ${LANE[p.c[2]].name}\n${p.c[1]}`);
    if (!pass(latest, p.c, ["day", "week"])) dot.classList.add("off");
    dot.addEventListener("click", () => { F.day = latest; setF("slot", slotOf(latest, p.c)); });
    s.append(dot);
  });
  $("tline").append(s);
  langBar($("todayBar"), $("todayLegend"), lch, false);
}

// ===== Thẻ ghim kiểu repo =====
function renderPins() {
  (DATA.highlights || []).forEach(h => {
    const lane = laneOfArea(h.area), scope = rangeF(["lane"]).map(([, c]) => c), n = scope.filter(c => c[2] === lane.id).length;
    const days = G.rDates.filter(k => chF(k, ["lane"]).some(c => c[2] === lane.id)).length, pct = scope.length ? Math.round(n / scope.length * 100) : 0;
    const b = el("button", "pin" + (F.lane === lane.id ? " on" : "")); b.type = "button";
    const t = el("div", "t"); t.innerHTML = oct("repo"); t.append(el("span", null, h.title || ""), el("span", "label", "Đang chạy"));
    const f = el("div", "foot"), s1 = el("span"), s2 = el("span"), s3 = el("span");
    const d = el("span", "dot"); d.style.background = lane.color; s1.append(d, document.createTextNode(lane.name));
    s2.innerHTML = oct("merge"); s2.append(document.createTextNode(nf(n)));
    s3.innerHTML = oct("calendar"); s3.append(document.createTextNode(`${days} ngày`));
    f.append(s1, s2, s3, el("span", "pct", `${pct}%`));
    b.append(t, el("p", null, h.text || ""), f);
    tip(b, `${h.title}: ${n} thay đổi (${pct}%) trong ${days} ngày`);
    b.addEventListener("click", () => setF("lane", lane.id));
    $("pins").append(b);
  });
}

// ===== Lưới đóng góp (không tự lọc theo ngày, tuần) =====
function renderCalendar() {
  const level = n => n === 0 ? 0 : n <= 5 ? 1 : n <= 15 ? 2 : n <= 30 ? 3 : 4;
  const from = parse(G.rDays[0]), to = parse(G.rDays[G.rDays.length - 1]);
  const tot = G.rDates.reduce((n, k) => n + chF(k, ["day", "week"]).length, 0);
  const t = el("span"); t.innerHTML = `<b>${nf(tot)} thay đổi</b> ${MONTH === "all" ? `từ ${dm(from)} đến ${dm(to)}` : `trong tháng ${+MONTH.slice(5)}`}`;
  $("contribTitle").replaceChildren(t);
  const start = new Date(from.getFullYear(), from.getMonth(), 1); start.setDate(start.getDate() - (start.getDay() + 6) % 7);
  const end = new Date(to.getFullYear(), to.getMonth() + 1, 0); end.setDate(end.getDate() + (7 - end.getDay()) % 7);
  const weeks = []; for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 7)) weeks.push(new Date(d));
  const cg = $("cg"), head = el("tr"); head.append(el("td"));
  weeks.forEach((w, i) => head.append(el("td", null, (i === 0 || w.getDate() <= 7) ? `Th${w.getMonth() + 1}` : "")));
  cg.append(head);
  ["T2", "", "T4", "", "T6", "", "CN"].forEach((lbl, r) => {
    const tr = el("tr"); tr.append(el("td", "wd", lbl));
    weeks.forEach(w => {
      const d = new Date(w); d.setDate(w.getDate() + r);
      const k = key(d), n = chF(k, ["day", "week"]).length, td = el("td");
      let sq;
      if (d > to) sq = el("i", "sq none");
      else if (n && d >= from) {
        sq = el("button", `sq l${level(n)}` + (F.day === k ? " sel" : "") + (F.week && wk(k) !== F.week ? " fade" : "")); sq.type = "button";
        sq.setAttribute("aria-label", `${n} thay đổi ngày ${dmy(d)}`);
        tip(sq, `${n} thay đổi ngày ${dm(d)}\n${DATA.headlines[k] || ""}`);
        sq.addEventListener("click", () => setF("day", k));
      } else { sq = el("i", "sq" + (d < from ? " out" : "")); tip(sq, `Không có thay đổi ngày ${dm(d)}`); }
      td.append(sq); tr.append(td);
    });
    cg.append(tr);
  });
}

// ===== Theo tuần (không tự lọc theo tuần, ngày) =====
function renderWeeks() {
  const ws = {}, wd = {};
  G.rDates.forEach(k => { const n = chF(k, ["week", "day"]).length, w = wk(k); ws[w] = (ws[w] || 0) + n; if (n) wd[w] = (wd[w] || 0) + 1; });
  const ks = Object.keys(ws).sort(), cur = F.week || ks[ks.length - 1], prev = ks[ks.indexOf(cur) - 1], max = Math.max(...Object.values(ws), 1);
  const head = el("div", "bigline"); head.append(el("b", "num", ws[cur]), el("span", "muted", F.week ? "tuần đã chọn" : "tuần này"));
  if (prev && wd[prev] && wd[cur]) {
    const diff = Math.round(((ws[cur] / wd[cur]) / (ws[prev] / wd[prev]) - 1) * 100);
    head.append(tip(el("span", "Label-g" + (diff < 0 ? " Label-r" : ""), `${diff >= 0 ? "↑" : "↓"} ${Math.abs(diff)}%`), "Số thay đổi mỗi ngày làm so với tuần trước"));
  }
  const box = el("div", "weeks");
  ks.forEach(w => {
    const d = el("button", (w === cur ? "cur" : "") + (F.week && F.week !== w ? " fade" : "")), i = el("i"); d.type = "button";
    i.style.height = (ws[w] / max * 100) + "px";
    tip(d, `Tuần từ ${dm(parse(w))}: ${ws[w]} thay đổi trong ${wd[w] || 0} ngày`);
    d.append(el("b", null, ws[w]), i, el("span", null, dm(parse(w))));
    d.addEventListener("click", () => setF("week", w)); box.append(d);
  });
  $("weeks").append(head, box);
  $("weeksScope").textContent = MONTH === "all" ? "" : `tháng ${+MONTH.slice(5)}`;
}

// ===== Giờ làm: thứ × giờ (không tự lọc theo ô giờ) =====
function renderPunch() {
  const grid = Array.from({ length: 7 }, () => Array(24).fill(0));
  rangeF(["slot"]).forEach(([k, c]) => { const [r, h] = slotOf(k, c).split("-").map(Number); grid[r][h]++; });
  const max = Math.max(...grid.flat(), 1), W = 760, L = 34, T = 6, cw = (W - L - 6) / 24, rh = 26, H = T + 7 * rh + 20;
  const s = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Số thay đổi theo thứ và giờ" });
  s.append(svgEl("rect", { x: L + 8 * cw, y: T, width: 9.5 * cw, height: 5 * rh, fill: "var(--counter)", rx: 4 }));
  WD_SHORT.forEach((lb, r) => {
    const t = svgEl("text", { x: 0, y: T + r * rh + rh / 2 + 4 }); t.textContent = lb; s.append(t);
    grid[r].forEach((n, h) => {
      const cx = L + h * cw + cw / 2, cy = T + r * rh + rh / 2, id = `${r}-${h}`;
      if (!n) { s.append(svgEl("circle", { cx, cy, r: 1.3, fill: "var(--border)" })); return; }
      const c = tip(svgEl("circle", { cx, cy, r: 2.5 + Math.sqrt(n / max) * 9, fill: "var(--c3)", class: "pick", opacity: F.slot && F.slot !== id ? .25 : 1,
        stroke: F.slot === id ? "var(--fg)" : "none", "stroke-width": 2 }), `${lb}, ${h}h–${h + 1}h: ${n} thay đổi`);
      c.addEventListener("click", () => setF("slot", id)); s.append(c);
    });
  });
  for (let h = 0; h < 24; h += 3) { const t = svgEl("text", { x: L + h * cw + cw / 2, y: H - 4, "text-anchor": "middle" }); t.textContent = `${h}h`; s.append(t); }
  const byHour = Array(24).fill(0); grid.forEach(r => r.forEach((n, h) => byHour[h] += n));
  const ph = byHour.indexOf(Math.max(...byHour));
  const night = byHour.slice(0, 6).reduce((a, b) => a + b, 0) + byHour.slice(22).reduce((a, b) => a + b, 0);
  const cap = el("div", "cap"); cap.innerHTML = `Đỉnh <b>${ph}h</b> · <b>${night}</b> thay đổi lúc 22h–6h`;
  $("punch").append(s, cap);
  // % ngoài giờ trên cùng tập đang vẽ: sáng sớm (trước 8h), buổi tối (từ 17h30) ngày thường, cuối tuần
  const rows = rangeF(["slot"]), off = rows.filter(([k, c]) => offHours(k, c));
  const parts = [["Sáng sớm", off.filter(([k, c]) => !isWeekend(k) && mins(c) < 480).length, "var(--l4)"],
                 ["Buổi tối", off.filter(([k, c]) => !isWeekend(k) && mins(c) >= 1050).length, "var(--l2)"],
                 ["Cuối tuần", off.filter(([k]) => isWeekend(k)).length, "var(--l6)"]];
  const line = $("offline"), big = el("b", "big num", `${rows.length ? Math.round(off.length / rows.length * 100) : 0}%`);
  const p = el("div", "Progress");
  parts.forEach(([lb, n, col]) => { if (!n) return; const i = tip(el("i"), `${lb}: ${n}`); i.style.width = (n / Math.max(rows.length, 1) * 100) + "%"; i.style.background = col; p.append(i); });
  line.append(big, el("span", null, `ngoài giờ · ${nf(off.length)}/${nf(rows.length)}`), p);
  parts.forEach(([lb, n, col]) => { const sp = el("span"), d = el("span", "dot"); d.style.cssText = `background:${col};width:8px;height:8px`; sp.append(d, document.createTextNode(`${lb} ${n}`)); line.append(sp); });
}

// ===== Tab cây công việc =====
function laneChip(l, n) {
  const c = el("button", "branch" + (F.lane === l.id ? " on" : F.lane ? " dim" : "")); c.type = "button";
  const dt = el("span", "dot"); dt.style.background = l.color;
  c.append(dt, document.createTextNode(l.name + " "), el("span", "counter", n));
  c.addEventListener("click", () => setF("lane", l.id));
  return c;
}
function renderTree() {
  LANES.forEach(l => $("lanes").append(laneChip(l, G.all.filter(c => c[2] === l.id).length)));
  const X0 = 14, GAP = 17, W = X0 + GAP * LANES.length + 10, STEP = 6, PAD = 10, dates = G.dates;
  const firstDay = {}; dates.forEach(k => G.ch(k).forEach(c => { if (!(c[2] in firstDay)) firstDay[c[2]] = k; }));
  const tree = $("tree"); let lastMonth = null;
  [...dates].reverse().forEach((k, idx) => {
    const d = parse(k), ch = [...G.ch(k)].reverse(), n = ch.length, hit = chF(k).length;
    if (d.getMonth() !== lastMonth) { lastMonth = d.getMonth(); tree.append(el("div", "daysep", `Tháng ${d.getMonth() + 1}/${d.getFullYear()}`)); }
    const H = Math.max(52, PAD * 2 + n * STEP), yOf = j => PAD + (j + .5) * (H - PAD * 2) / n, isLast = idx === dates.length - 1;
    const row = el("button", "row" + (F.day === k ? " sel" : "") + (anyFilter() && !hit ? " fade" : "")); row.type = "button";
    const s = svgEl("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    s.append(svgEl("line", { x1: X0, y1: idx === 0 ? PAD : 0, x2: X0, y2: isLast ? H - PAD : H, stroke: "var(--main-line)", "stroke-width": 2 }));
    LANES.forEach((l, i) => {
      const x = X0 + GAP * (i + 1);
      if (!firstDay[l.id] || k < firstDay[l.id]) return;
      const g = svgEl("g", { opacity: F.lane && F.lane !== l.id ? .15 : 1 });
      const mine = ch.map((c, j) => c[2] === l.id ? j : -1).filter(j => j >= 0);
      const top = idx === 0 ? (mine.length ? yOf(mine[0]) : PAD) : 0;
      if (k === firstDay[l.id]) {
        const yb = yOf(mine[mine.length - 1]);
        g.append(svgEl("path", { d: `M${X0} ${H} C ${X0} ${yb + 8}, ${x} ${yb + 12}, ${x} ${yb}`, fill: "none", stroke: l.color, "stroke-width": 2 }));
        g.append(svgEl("line", { x1: x, y1: top, x2: x, y2: yb, stroke: l.color, "stroke-width": 2 }));
      } else g.append(svgEl("line", { x1: x, y1: top, x2: x, y2: H, stroke: l.color, "stroke-width": 2 }));
      mine.forEach(j => g.append(tip(svgEl("circle", { cx: x, cy: yOf(j), r: n > 24 ? 2.6 : 3.4, fill: l.color, opacity: pass(k, ch[j], ["lane"]) ? 1 : .2 }), `${ch[j][6]} · ${ch[j][0]}\n${ch[j][1]}`)));
      s.append(g);
    });
    s.append(svgEl("circle", { cx: X0, cy: PAD, r: 4.5, fill: "var(--bg)", stroke: "var(--main-line)", "stroke-width": 2 }));
    const msg = el("span", "msg"), l1 = el("span", "line1");
    l1.append(el("span", "hd", DATA.headlines[k] || ""), el("span", "counter", anyFilter() ? `${hit}/${n}` : n));
    msg.append(l1, el("span", "line2", `${WD[d.getDay()]} ${dm(d)}`)); row.append(s, msg);
    row.addEventListener("click", () => openDetail(k));
    tree.append(row);
  });
}

// ===== Vẽ lại toàn bộ =====
const CONTAINERS = ["todayStats", "tline", "todayBar", "todayLegend", "pins", "cg", "weeks", "offline", "punch", "lanes", "tree"];
function render() {
  derive();
  CONTAINERS.forEach(id => $(id).replaceChildren());
  $("cnt-cay").textContent = G.all.length;
  renderMonths(); renderSide(); renderFilterBar(); renderToday(); renderPins(); renderCalendar(); renderWeeks(); renderPunch(); renderTree();
  if (openDay) { if (DATA.days[openDay]) renderDetail(); else closeDetail(); }
}

// ===== Ngăn kéo chi tiết ngày =====
const detail = $("detail"), scrim = $("scrim");
function renderDetail() {
  if (!openDay) return;
  const k = openDay, d = parse(k), day = DATA.days[k], ch = day.changes;
  detail.replaceChildren();
  const h = el("div", "dh");
  const x = el("button", "close", "×"); x.type = "button"; x.setAttribute("aria-label", "Đóng"); x.addEventListener("click", closeDetail);
  const st = el("div", "dstats");
  st.append(el("span", "num", `${ch.length} thay đổi`), el("span", "num add", "+" + nf(sum(ch, 3))), el("span", "num del", "−" + nf(sum(ch, 4))), el("span", "num", `${ch[0][6]} → ${ch[ch.length - 1][6]}`));
  const bar = el("div", "Progress"); langBar(bar, el("div"), ch, false);
  const filt = el("button", "link", F.day === k ? "Bỏ lọc ngày này" : "Lọc cả trang theo ngày này"); filt.type = "button";
  filt.addEventListener("click", () => setF("day", k));
  h.append(el("span", "date", `${WD[d.getDay()]}, ${dmy(d)}`), el("h3", null, DATA.headlines[k] || ""), st, bar, filt, x);
  const ul = el("ul", "items");
  (day.items || []).forEach(([a, t]) => {
    const l = laneOfArea(a), li = el("li"); if (F.lane && l.id !== F.lane) li.classList.add("dim");
    const dot = el("span", "dot"); dot.style.background = l.color;
    const body = el("div"); body.append(el("small", null, l.name), el("span", null, t));
    li.append(dot, body); ul.append(li);
  });
  const shown = ch.filter(c => pass(k, c, ["day", "week"])).length;
  const det = el("details"); det.open = anyFilter() && shown < ch.length;
  det.append(el("summary", null, anyFilter() ? `Danh sách kỹ thuật (${shown} khớp lọc / ${ch.length})` : `Danh sách kỹ thuật (${ch.length})`));
  const ol = el("ul", "prs");
  [...ch].reverse().forEach(c => {
    const [num, t, lane, a, r, , hm] = c;
    const li = el("li"); if (!pass(k, c, ["day", "week"])) li.classList.add("dim");
    const dot = el("span", "dot"); dot.style.background = (LANE[lane] || LANE["so-khach"]).color;
    const s = el("span"); s.append(document.createTextNode(t + " "), el("span", "meta num", `${hm} · ${num} · `), el("span", "meta num add", "+" + nf(a)), el("span", "meta", " "), el("span", "meta num del", "−" + nf(r)));
    li.append(dot, s); ol.append(li);
  });
  det.append(ol);
  detail.append(h, ul, det);
}
function openDetail(k) { openDay = k; renderDetail(); detail.scrollTop = 0; detail.classList.add("open"); scrim.hidden = false; }
function closeDetail() { detail.classList.remove("open"); scrim.hidden = true; openDay = null; }
scrim.addEventListener("click", closeDetail);
document.addEventListener("keydown", e => { if (e.key !== "Escape") return; if (openDay) closeDetail(); else if (anyFilter()) clearF(); });

// ===== Chú thích nổi kiểu GitHub =====
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
  const num = $("todayNum"); if (num) { num.classList.remove("flash"); void num.offsetWidth; num.classList.add("flash"); }
}
const okChange = c => Array.isArray(c) && c.length >= 7 && typeof c[0] === "string" && typeof c[1] === "string" && typeof c[6] === "string"
  && /^\d\d:\d\d$/.test(c[6]) && [3, 4, 5].every(i => Number.isFinite(c[i]));
function fromApi(body) {
  const days = {}, headlines = {};
  for (const [k, v] of Object.entries(body.days || {})) {
    if (!/^\d{4}-\d\d-\d\d$/.test(k) || !v || !Array.isArray(v.changes)) continue;
    const changes = v.changes.filter(okChange).map(c => [c[0], c[1], LANE[c[2]] ? c[2] : "so-khach", c[3], c[4], c[5], c[6]]);
    if (!changes.length) continue;
    days[k] = { items: Array.isArray(v.items) ? v.items.filter(i => Array.isArray(i) && typeof i[1] === "string") : [], changes };
    headlines[k] = typeof v.headline === "string" ? v.headline : "";
  }
  const dates = Object.keys(days).sort();
  if (!dates.length) return null;
  return clean({ period: { from: body.from || dates[0], to: body.to || dates[dates.length - 1] }, updated: body.checked_at || "",
    highlights: Array.isArray(body.highlights) ? body.highlights : [], next: Array.isArray(body.next) ? body.next : [], headlines, days });
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
  if (!next) { $("error").textContent = "Máy chủ chưa có dữ liệu Nhật ký công việc."; $("error").hidden = false; paintLive(body); return; }
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
route(); load();
setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
})();
