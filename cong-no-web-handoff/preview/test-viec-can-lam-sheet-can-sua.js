// Khối "Sheet cần sửa" (KIEM-TAB-01 3d): phần dựng chuỗi HTML, không cần trình duyệt. Dữ liệu giả.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const S = require('./viec-can-lam-sheet-can-sua.js');

const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const cell = (v = '', extra = {}) => ({ v, f: null, bg: null, b: false, al: null, ...extra });
const finding = (extra = {}) => ({ tab: 'Mẫu', kind: 'row_shift', level: 'error', rows: [15, 16], cells: ['B15', 'F16'], message: 'Tiền lệch một dòng.', fix: 'Đưa tiền lên.', ...extra });
const statement = (findings, extra = {}) => ({ blocked: { code: 'TAB_BROKEN', findings, held: false, held_reasons: {}, ...extra } });
const region = (extra = {}) => ({
  sheet_id: 5, first_row: 10, first_col: 1, col_letters: ['A', 'B', 'C', 'D'], widths: [50, 80, 80, 80], heights: [21, 21],
  cells: [[cell('A10'), cell('B10', { bg: '#ffe6e6', b: true }), cell(), cell()], [cell(''), cell('-5.000', { al: 'RIGHT' }), cell(), cell()]],
  merges: [], column_groups: [{ cols: [0], collapsed: false }, { cols: [1], collapsed: false }, { cols: [2, 3], collapsed: true }],
  marks: [{ row: 0, col: 1, cell: 'B10', level: 'error', text: 'Ô sai.' }], ...extra });
const state = (entries = {}) => ({ regionOpen: new Set(Object.keys(entries)), region: new Map(Object.entries(entries)) });
const loaded = (extra = {}) => ({ region: region(), read_at: '2026-11-06T10:14:00+07:00', open_url: 'https://docs.google.com/spreadsheets/d/FAKE/edit#gid=5&range=B10', sample: null, ...extra });

test('mỗi chỗ sai một thẻ: tiêu đề thường, ô, câu, cách sửa; chỉ chỗ có ô mới có nút xem vùng', () => {
  const out = S.html(7, statement([finding(), { tab: 'Mẫu', kind: 'MISSING_MONTH', level: 'error', count: 2 }, finding({ kind: 'duplicate_container', level: 'warning', cells: ['B3'] })]), state(), { esc });
  assert.match(out, /Tab Sheet của khách này cần sửa trước khi web ghi tiền\.<\/strong> 3 chỗ/);
  assert.match(out, /<h3>Tiền lệch một dòng<\/h3>/);
  assert.match(out, /<b>B15<\/b>, <b>F16<\/b>/);
  assert.match(out, /Cách sửa:<\/strong> Đưa tiền lên\./);
  assert.match(out, /Không thấy khối tháng/);
  assert.equal((out.match(/data-sc-view=/g) ?? []).length, 2);   // chỗ chỉ có mã lỗi không có nút
  assert.match(out, /sf-card sf-warning/);   // cảnh báo màu cam, không đỏ
});

test('vùng ô chỉ hiện khi mở; đang tải và lỗi có chữ riêng, lỗi có Thử lại', () => {
  const closed = S.html(7, statement([finding()]), state(), { esc });
  assert.doesNotMatch(closed, /sf-scroll/);
  assert.match(closed, /aria-expanded="false"/);
  assert.match(S.html(7, statement([finding()]), { regionOpen: new Set(['7:0']), region: new Map() }, { esc }), /Đang đọc Sheet…/);
  const failed = S.html(7, statement([finding()]), state({ '7:0': null }), { esc });
  assert.match(failed, /Chưa tải được hình Sheet/);
  assert.match(failed, /data-sc-refresh="7:0"/);
});

test('lưới: chữ cột và số dòng, ô lỗi có viền và chú thích, cột trống liên tiếp là một cột "…", số căn phải, nền và đậm giữ như Sheet', () => {
  const out = S.html(7, statement([finding()]), state({ '7:0': loaded() }), { esc });
  assert.match(out, /<th scope="col" style="min-width:50px">A<\/th>/);
  assert.match(out, /<th scope="row" class="sf-rowno">10<\/th>/);
  assert.match(out, /class="sf-cell sf-error sf-bold"[^>]*style="background:#ffe6e6"[^>]*title="Ô sai\."[^>]*data-sc-mark="B10"/);
  assert.equal((out.match(/<td class="sf-gap"/g) ?? []).length, 2);   // một ô "…" mỗi dòng
  assert.equal((out.match(/<th class="sf-gap"/g) ?? []).length, 1);   // hai cột trống liền nhau chỉ một tiêu đề "…"
  assert.match(out, /class="sf-cell sf-right">-5\.000/);
  assert.match(out, /Đọc lúc 10:14/);
  assert.match(out, /<a class="btn" href="https:\/\/docs\.google\.com\/spreadsheets\/d\/FAKE\/edit#gid=5&amp;range=B10" target="_blank" rel="noopener">Mở ô này trên Sheet<\/a>/);
});

test('ô gộp: chỉ giữ khi nằm gọn trong các cột đang hiện, ô bị phủ không vẽ lại', () => {
  const merged = S.gridHtml(region({ merges: [{ r1: 0, c1: 0, r2: 1, c2: 2 }] }), esc);
  assert.match(merged, /colspan="2"/);
  assert.equal((merged.match(/<td class="sf-cell/g) ?? []).length, 3);   // 4 ô thường − 1 bị phủ
  const across = S.gridHtml(region({ merges: [{ r1: 0, c1: 1, r2: 1, c2: 4 }] }), esc);   // trùm cột "…": bỏ gộp
  assert.doesNotMatch(across, /colspan=/);
});

test('chain_break: nêu công thức mẫu và ô đang là gì', () => {
  const typed = S.html(7, statement([finding({ kind: 'chain_break', cells: ['N45'] })]), state({ '7:0': loaded({ sample: { sample: '=N40+K45-M45', current: '0', has_formula: false } }) }), { esc });
  assert.match(typed, /<code>=N40\+K45-M45<\/code>; ô này đang là số gõ tay <code>0<\/code>, không phải công thức/);
  const blank = S.html(7, statement([finding({ kind: 'chain_break', cells: ['N45'] })]), state({ '7:0': loaded({ sample: { sample: '=SUM(M1:M9)', current: null, has_formula: false } }) }), { esc });
  assert.match(blank, /ô này đang để trống/);
  const other = S.html(7, statement([finding({ kind: 'chain_break', cells: ['N45'] })]), state({ '7:0': loaded({ sample: { sample: '=A1', current: '=B1', has_formula: true } }) }), { esc });
  assert.match(other, /ô này đang là <code>=B1<\/code>/);
});

test('máy giữ khách mà chưa chỉ ra được ô: nói thật và kèm mã lỗi', () => {
  const out = S.html(7, statement([], { held: true, held_reasons: { ANCHOR_CHAIN_MISMATCH: 2, MISSING_MONTH: 1 } }), state(), { esc });
  assert.match(out, /Máy đang giữ khách này vì Sheet có chỗ chưa đọc được/);
  assert.match(out, /ANCHOR_CHAIN_MISMATCH ×2, MISSING_MONTH\./);
  assert.doesNotMatch(out, /sf-card/);
});

test('chữ từ server và từ Sheet được thoát; link mở ô không nhận chữ nguy hiểm trong thuộc tính', () => {
  const bad = '<img src=x onerror=alert(1)>';
  const out = S.html(7, statement([finding({ message: bad, fix: bad })]), state({ '7:0': loaded({ open_url: 'https://x.test/?a="><script>', region: region({ cells: [[cell(bad), cell(), cell(), cell()], [cell(), cell(), cell(), cell()]] }) }) }), { esc });
  assert.doesNotMatch(out, /<img|<script/);
  assert.match(out, /&lt;img src=x onerror=alert\(1\)&gt;/);
});
