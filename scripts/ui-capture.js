#!/usr/bin/env node
// Chụp các trạng thái giao diện khai báo trong spec (mục "## Ảnh chụp giao diện", khối ```json)
// và đo các luật UX đo được trên giao diện đã render. agent-run.ps1 gọi file này từ checkout chính,
// nên agent trong worktree không sửa được công cụ chụp.
//
//   node scripts/ui-capture.js --spec <spec.md> --root <thư mục chứa trang> --out <thư mục ảnh> --label after|before
//
// Ghi <out>/<state>-<w>x<h>.png, <out>/report.json, <out>/checks.md. Mã thoát 0 kể cả khi có phát hiện;
// chỉ khác 0 khi không đọc được khai báo hoặc không mở được trình duyệt.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

const arg = name => { const i = process.argv.indexOf('--' + name); return i > 0 ? process.argv[i + 1] : undefined; };
const specPath = arg('spec'), root = arg('root'), out = arg('out'), label = arg('label') || 'after';
if (!specPath || !root || !out) { console.error('Thiếu --spec, --root hoặc --out.'); process.exit(64); }

const HEADING = '## Ảnh chụp giao diện';
const STEP_TIMEOUT = 5000;
// Cùng luật với kiểm mockup trong agent-run.ps1 (Test-MockupRules).
const TECH = /\b(D0\d|Q0\d|S1\d|fixture|RAM|revision|API|guardrail|GUARDRAIL|ids\s*=)/;
const ABBR_MONEY = /\d+([.,]\d+)?\s?(tr|triệu|k)\b/;

function readCapture() {
  const text = fs.readFileSync(specPath, 'utf8');
  const at = text.indexOf(HEADING);
  if (at < 0) throw new Error(`Spec không có mục "${HEADING}".`);
  const m = /```json\s*\n([\s\S]*?)\n```/.exec(text.slice(at));
  if (!m) throw new Error(`Mục "${HEADING}" thiếu khối \`\`\`json.`);
  const c = JSON.parse(m[1]);
  if (!c.page || !Array.isArray(c.states) || !c.states.length) throw new Error('Khối chụp cần "page" và "states" (ít nhất một trạng thái).');
  const names = new Set();
  for (const s of c.states) {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(s.name || '')) throw new Error(`Tên trạng thái không hợp lệ: ${JSON.stringify(s.name)} (chỉ a-z, 0-9, -).`);
    if (names.has(s.name)) throw new Error(`Trùng tên trạng thái: ${s.name}`);
    names.add(s.name);
    for (const st of s.steps || []) stepKind(st);
  }
  c.viewports = c.viewports || [[1280, 720]];
  return c;
}

const KINDS = ['click', 'fill', 'select', 'check', 'uncheck', 'press', 'focus', 'hover', 'paste', 'waitFor'];
function stepKind(st) {
  const k = Object.keys(st).filter(x => KINDS.includes(x));
  if (k.length !== 1) throw new Error(`Bước không hợp lệ ${JSON.stringify(st)}; dùng đúng một trong: ${KINDS.join(', ')}.`);
  return k[0];
}

// Selector chạy ở strict mode: khớp 0 hoặc nhiều phần tử là lỗi, để kịch bản luôn chỉ đúng một chỗ.
async function runStep(page, st) {
  const k = stepKind(st), v = st[k], o = {timeout: STEP_TIMEOUT};
  switch (k) {
    case 'click': return page.locator(v).click(o);
    case 'fill': return page.locator(v[0]).fill(String(v[1]), o);
    case 'select': return page.locator(v[0]).selectOption(String(v[1]), o);
    case 'check': return page.locator(v).check(o);
    case 'uncheck': return page.locator(v).uncheck(o);
    case 'focus': return page.locator(v).focus(o);
    case 'hover': return page.locator(v).hover(o);
    case 'waitFor': return page.locator(v).waitFor({state: 'visible', ...o});
    case 'press': for (let i = 0; i < (st.times || 1); i++) await page.keyboard.press(v); return;
    case 'paste': // Như test browser: dán TSV vào ô đang chọn bằng ClipboardEvent.
      await page.locator(v[0]).focus(o);
      return page.locator(v[0]).evaluate((el, t) => {
        const d = new DataTransfer(); d.setData('text/plain', t);
        el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: d, bubbles: true, cancelable: true}));
      }, String(v[1]));
  }
}

// Đo trong trang: cỡ chữ, tương phản (ước tính trên nền đặc gần nhất), vùng bấm, chữ cấm, cuộn ngang, focus.
function audit(rootSel) {
  const root = rootSel ? document.querySelector(rootSel) : document.body;
  if (!root) return {missingRoot: true};
  const visible = el => { const s = getComputedStyle(el); const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0; };
  const rgb = c => { const m = c.match(/[\d.]+/g) || [0, 0, 0, 0]; return {r: +m[0], g: +m[1], b: +m[2], a: m[3] === undefined ? 1 : +m[3]}; };
  const lum = ({r, g, b}) => { const f = x => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor); if (c.a > 0.5) return c; } return {r: 255, g: 255, b: 255, a: 1}; };
  const desc = el => { let d = el.tagName.toLowerCase(); if (el.id) d += '#' + el.id; for (const a of ['data-action', 'data-edit', 'data-select', 'aria-label', 'name']) if (el.getAttribute(a)) { d += `[${a}="${el.getAttribute(a).slice(0, 40)}"]`; break; } return d; };
  /* global TECH_RE, MONEY_RE -- hai hằng này được tiêm vào thân hàm khi
     serialize sang page context (xem chỗ dựng `fn` bên dưới), nên không
     khai báo tĩnh được. */
  const fonts = {}, contrast = [], words = [], seen = new Set();
  const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    const t = n.textContent.replace(/\s+/g, ' ').trim(), el = n.parentElement;
    if (!t || !el || seen.has(el) || !visible(el) || ['SCRIPT', 'STYLE', 'OPTION'].includes(el.tagName)) continue;
    seen.add(el);
    const s = getComputedStyle(el), size = parseFloat(s.fontSize), bold = +s.fontWeight >= 700;
    (fonts[size] = fonts[size] || []).push(t.slice(0, 60));
    const fg = rgb(s.color), bg = bgOf(el), L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const need = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;
    if (fg.a > 0.5 && ratio < need) contrast.push({text: t.slice(0, 60), ratio: +ratio.toFixed(2), need, el: desc(el)});
    if (TECH_RE.test(t) || MONEY_RE.test(t)) words.push(t.slice(0, 80));
  }
  const targets = [];
  for (const el of root.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [tabindex]:not([tabindex="-1"])')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (Math.min(r.width, r.height) < 40) targets.push({el: desc(el), w: Math.round(r.width), h: Math.round(r.height)});
  }
  const a = document.activeElement, fs = a && a !== document.body ? getComputedStyle(a) : null;
  return {
    fonts: Object.entries(fonts).map(([s, l]) => ({size: +s, count: l.length, sample: l.slice(0, 3)})).sort((x, y) => x.size - y.size),
    contrast, words, targets,
    hScroll: document.documentElement.scrollWidth > window.innerWidth ? document.documentElement.scrollWidth : 0,
    focus: fs ? {el: desc(a), outline: `${fs.outlineStyle} ${fs.outlineWidth} ${fs.outlineColor}`, visibleOutline: fs.outlineStyle !== 'none' && parseFloat(fs.outlineWidth) > 0 || fs.boxShadow !== 'none'} : null,
  };
}

// Mỗi phát hiện có khóa ổn định để so với bản chụp trước thay đổi: chỉ phát hiện MỚI là do lần sửa này.
function findings(r, isBefore) {
  const f = [], add = (key, msg) => f.push({key, msg});
  if (r.stepError) add('step', isBefore ? `KHÔNG ÁP DỤNG trước thay đổi: ${r.stepError}` : `LỖI kịch bản: ${r.stepError}`);
  for (const e of r.errors) add('js:' + e, `LỖI JS trên trang: ${e}`);
  const a = r.audit;
  if (!a) return f;
  if (a.missingRoot) { add('root', `LỖI: không thấy vùng chụp ${r.shot}`); return f; }
  for (const x of a.fonts) {
    const ex = x.sample.map(s => `"${s}"`).join(', ');
    if (x.size < 11) add('font:' + x.size, `LỖI cỡ chữ ${x.size}px < 11px (${x.count} chỗ), ví dụ: ${ex}`);
    else if (x.size < 12) add('font:' + x.size, `CẢNH BÁO cỡ chữ ${x.size}px (${x.count} chỗ, chỉ hợp với nhãn trạng thái nhỏ), ví dụ: ${ex}`);
  }
  for (const c of a.contrast) add(`contrast:${c.text}|${c.el}`, `LỖI tương phản ${c.ratio}:1 < ${c.need}:1 (ước tính): "${c.text}" ở ${c.el}`);
  for (const w of a.words) add('word:' + w, `LỖI từ kỹ thuật/tiền viết tắt trên màn hình: "${w}"`);
  for (const t of a.targets) add(`target:${t.el}:${t.w}x${t.h}`, `CẢNH BÁO vùng bấm < 40px: ${t.el} ${t.w}×${t.h}`);
  if (a.hScroll) add('hscroll', `CẢNH BÁO trang cuộn ngang: rộng ${a.hScroll}px > khung ${r.viewport[0]}px`);
  if (a.focus && !a.focus.visibleOutline) add('focus:' + a.focus.el, `LỖI phần tử đang focus không có viền nhìn thấy: ${a.focus.el} (outline ${a.focus.outline})`);
  return f;
}

// Gom các dòng cùng loại để báo cáo ngắn: tối đa 8 dòng mỗi loại.
function summarize(items) {
  const groups = {};
  for (const x of items) (groups[x.key.split(':')[0]] = groups[x.key.split(':')[0]] || []).push(x.msg);
  return Object.values(groups).flatMap(g => g.length > 8 ? [...g.slice(0, 8), `… thêm ${g.length - 8} dòng cùng loại (xem report.json)`] : g);
}

(async () => {
  let cap;
  try { cap = readCapture(); } catch (e) { console.error(e.message); process.exit(65); }
  const pageFile = path.join(root, cap.page);
  fs.mkdirSync(out, {recursive: true});
  for (const f of fs.readdirSync(out)) if (/\.(png|json|md)$/.test(f)) fs.rmSync(path.join(out, f));
  if (!fs.existsSync(pageFile)) {
    fs.writeFileSync(path.join(out, 'checks.md'), `LỖI: không có trang ${cap.page} trong ${label}.\n`);
    console.log(`Không có trang ${cap.page}`); return;
  }
  const url = pathToFileURL(pageFile).href;
  const browser = await chromium.launch({headless: true});
  const results = [];
  try {
    for (const [w, h] of cap.viewports) {
      for (const s of cap.states) {
        const page = await browser.newPage({viewport: {width: w, height: h}});
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
        const r = {name: s.name, board: s.board || '', note: s.note || '', viewport: [w, h], shot: s.shot || '', errors, file: `${s.name}-${w}x${h}.png`};
        try {
          await page.goto(url);
          for (const [i, st] of (s.steps || []).entries()) {
            try { await runStep(page, st); }
            catch (e) { r.stepError = `bước ${i + 1} ${JSON.stringify(st)}: ${e.message.split('\n')[0]}`; break; }
          }
          await page.waitForTimeout(100);
          const fn = `const TECH_RE=${TECH};const MONEY_RE=${ABBR_MONEY};return (${audit})(${JSON.stringify(s.shot || '')});`;
          r.audit = await page.evaluate(new Function(fn));
          const target = s.shot ? page.locator(s.shot) : null;
          if (target && await target.count() === 1) await target.screenshot({path: path.join(out, r.file), timeout: STEP_TIMEOUT});
          else await page.screenshot({path: path.join(out, r.file), fullPage: !!s.fullPage});
        } catch (e) { r.stepError = r.stepError || e.message.split('\n')[0]; }
        finally { await page.close(); }
        r.findings = findings(r, label === 'before');
        results.push(r);
        console.log(`${label} ${r.file}: ${r.findings.length ? r.findings.length + ' phát hiện' : 'không phát hiện'}`);
      }
    }
  } finally { await browser.close(); }
  // So với bản chụp trước thay đổi (cùng trạng thái, cùng khung) nếu có.
  const prevFile = arg('compare');
  const prev = prevFile && fs.existsSync(prevFile) ? JSON.parse(fs.readFileSync(prevFile, 'utf8')) : null;
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(results, null, 2));
  const md = results.map(r => {
    const fontLine = r.audit && r.audit.fonts ? r.audit.fonts.map(x => `${x.size}px×${x.count}`).join(', ') : '—';
    const before = prev && prev.find(p => p.name === r.name && p.viewport.join() === r.viewport.join());
    const usable = before && !before.stepError;
    const oldKeys = new Set(usable ? before.findings.map(x => x.key) : []);
    const fresh = r.findings.filter(x => !oldKeys.has(x.key)), old = r.findings.filter(x => oldKeys.has(x.key));
    const head = !prev ? [] : !before ? ['- So sánh: không có bản chụp trước thay đổi cho trạng thái này.']
      : !usable ? ['- So sánh: trạng thái này chưa đạt được trước thay đổi (thao tác mới), mọi phát hiện coi là MỚI.'] : [];
    return [`### ${r.name} · ${r.viewport.join('x')} · ${label === 'before' ? 'TRƯỚC thay đổi' : 'SAU thay đổi'}`,
      `- Ảnh: ${r.file}${r.board ? ` · đối chiếu board mockup "${r.board}"` : ''}${r.note ? ` · ${r.note}` : ''}`,
      `- Cỡ chữ (px×số chỗ): ${fontLine}`,
      r.audit && r.audit.focus ? `- Đang focus: ${r.audit.focus.el} (outline ${r.audit.focus.outline})` : '- Đang focus: (không có)',
      ...head,
      ...(fresh.length ? summarize(fresh).map(x => `- ${prev ? 'MỚI: ' : ''}${x}`) : [`- Không có phát hiện${prev ? ' mới' : ''} đo được.`]),
      ...(old.length ? [`- Có sẵn trước thay đổi, không do lần sửa này: ${old.length} phát hiện (${[...new Set(old.map(x => x.key.split(':')[0]))].join(', ')}); chi tiết trong report.json.`] : [])].join('\n');
  }).join('\n\n');
  fs.writeFileSync(path.join(out, 'checks.md'), md + '\n');
})().catch(e => { console.error(e.stack || e.message); process.exit(70); });
