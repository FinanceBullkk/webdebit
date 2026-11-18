const assert = require('node:assert/strict');
const path = require('node:path');
const { test, launchShared } = require('./shared-browser');

// Vẽ bảng khách lệch một khách có gợi ý; `changes` đổi bản đối chiếu, phiên bản sổ hoặc trạng thái dòng.
async function withRender(fn) {
  const browser = await launchShared();
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.setContent('<main></main>');
    for (const file of ['viec-can-lam-doi-chieu-model.js', 'viec-can-lam-table.js', 'viec-can-lam-doi-chieu.js']) {
      await page.addScriptTag({ path: path.join(__dirname, file) });
    }
    await fn(changes => page.evaluate(changes => {
      const basis = { version: 1, prices_sha256: 'a'.repeat(64), receipts_sha256: 'b'.repeat(64),
        web_total_vnd: '900', sheet_total_vnd: '1000' };
      const ahead = { kind: 'ahead_old', container: 'MAUU0000091', date: '2026-10-01', amount_vnd: '50', days: 40 };
      const item = { customer_id: 7, customer: 'TEST', status: 'LECH_TONG', reason: 'NOTHING_TO_WRITE',
        web_total_vnd: '900', sheet_total_vnd: '1000', difference_vnd: '-100', hints_explain: true,
        hints_basis: changes.missingBasis ? undefined : basis,
        hints: [{ kind: 'receipt_twice', pids: ['PH-1', 'PH-2'], date: '2026-10-31', amount_vnd: '100', delta_vnd: '100' },
          ...(changes.ahead ? [ahead] : [])] };
      const statement = { ...basis, web_vnd: '900', sheet_total_vnd: '1000', web_ahead_vnd: '0', groups: [], ...changes };
      const state = { open: changes.closed ? null : 7, data: new Map(changes.loading ? [] : [[7, statement]]), sel: new Map(), off: new Map(),
        kept: new Map(), xem: new Set(), undo: new Map() };
      document.querySelector('main').innerHTML = globalThis.DoiChieuView.lechHtml(
        { checked_at: '2026-11-10T10:00:00+07:00', customers: [item] }, state,
        { F: { full: String }, esc: String, href: () => '#test', now: Date.parse('2026-11-10T10:10:00+07:00'), action: null, busy: false,
          bookVersions: new Map([[7, changes.bookVersion ?? 1]]) });
    }, changes), page);
  } finally { await browser.close(); }
}

test('gợi ý chỉ hiện khi phiên bản sổ và cả hai nguồn còn đúng; sổ đã khớp không khuyên hủy phiếu cũ', async () => withRender(async (render, page) => {
  await render({});
  assert.match(await page.locator('.dc-why').innerText(), /Có tổ hợp gợi ý khớp số tiền lệch, cần kiểm chứng/);
  assert.equal(await page.locator('.dc-hints li').count(), 1);
  for (const change of [{ version: 2, web_vnd: '1000' }, { version: 2 }, { bookVersion: 2 },
    { prices_sha256: 'c'.repeat(64) }, { receipts_sha256: 'd'.repeat(64) },
    { sheet_total_vnd: '900' }, { web_vnd: '1000' }, { missingBasis: true }, { loading: true }, { missingBasis: true, loading: true }]) {
    await render(change);
    assert.doesNotMatch(await page.locator('main').innerText(), /PH-1|PH-2|Có tổ hợp gợi ý/);
    assert.equal(await page.locator('.dc-hints').count(), 0);
    if (change.web_vnd === '1000') assert.equal(await page.locator('.dc-left.ok').count(), 1);
  }
}));

test('dòng đóng: sổ chưa đổi thì cột Vì sao vẫn tóm tắt gợi ý, sổ đổi thì báo chờ xác nhận', async () => withRender(async (render, page) => {
  await render({ closed: true });
  assert.match(await page.locator('.dc-why').innerText(), /cần kiểm chứng: Phiếu PH-1 và PH-2/);
  for (const change of [{ closed: true, bookVersion: 2 }, { closed: true, missingBasis: true }]) {
    await render(change);
    assert.doesNotMatch(await page.locator('main').innerText(), /PH-1|PH-2/);
    assert.match(await page.locator('.dc-why').innerText(), /chưa được xác nhận với sổ và nguồn hiện tại/);
  }
}));

test('gợi ý cũ bị ẩn nhưng chuyến đi trước cần xem vẫn hiện (không phải lời khuyên sửa tiền)', async () => withRender(async (render, page) => {
  for (const change of [{ ahead: true, closed: true, bookVersion: 2 }, { ahead: true, version: 2 }]) {
    await render(change);
    const text = await page.locator('main').innerText();
    assert.doesNotMatch(text, /PH-1|PH-2|Có tổ hợp gợi ý/);
    assert.match(text, /MAUU0000091/);
  }
}));
