const assert = require('node:assert/strict');
const path = require('node:path');
const { test, launchShared } = require('./shared-browser');

test('gợi ý chỉ hiện khi phiên bản sổ và cả hai nguồn còn đúng; sổ đã khớp không khuyên hủy phiếu cũ', async () => {
  const browser = await launchShared();
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.setContent('<main></main>');
    for (const file of ['viec-can-lam-doi-chieu-model.js', 'viec-can-lam-table.js', 'viec-can-lam-doi-chieu.js']) {
      await page.addScriptTag({ path: path.join(__dirname, file) });
    }
    const render = changes => page.evaluate(changes => {
      const basis = { version: 1, prices_sha256: 'a'.repeat(64), receipts_sha256: 'b'.repeat(64),
        web_total_vnd: '900', sheet_total_vnd: '1000' };
      const item = { customer_id: 7, customer: 'TEST', status: 'LECH_TONG', reason: 'NOTHING_TO_WRITE',
        web_total_vnd: '900', sheet_total_vnd: '1000', difference_vnd: '-100', hints_explain: true,
        hints_basis: changes.missingBasis ? undefined : basis,
        hints: [{ kind: 'receipt_twice', pids: ['PH-1', 'PH-2'], date: '2026-10-31', amount_vnd: '100', delta_vnd: '100' }] };
      const statement = { ...basis, web_vnd: '900', sheet_total_vnd: '1000', web_ahead_vnd: '0', groups: [], ...changes };
      const state = { open: 7, data: new Map(changes.loading ? [] : [[7, statement]]), sel: new Map(), off: new Map(),
        kept: new Map(), xem: new Set(), undo: new Map() };
      document.querySelector('main').innerHTML = globalThis.DoiChieuView.lechHtml(
        { checked_at: '2026-11-10T10:00:00+07:00', customers: [item] }, state,
        { F: { full: String }, esc: String, href: () => '#test', now: Date.parse('2026-11-10T10:10:00+07:00'), action: null, busy: false,
          bookVersions: new Map([[7, changes.bookVersion ?? 1]]) });
    }, changes);
    await render({});
    assert.match(await page.locator('.dc-why').innerText(), /Có tổ hợp gợi ý khớp số tiền lệch, cần kiểm chứng/);
    assert.equal(await page.locator('.dc-hints li').count(), 1);
    for (const change of [{ version: 2, web_vnd: '1000' }, { version: 2 }, { bookVersion: 2 },
      { prices_sha256: 'c'.repeat(64) }, { receipts_sha256: 'd'.repeat(64) },
      { sheet_total_vnd: '900' }, { web_vnd: '1000' }, { missingBasis: true }, { loading: true }]) {
      await render(change);
      assert.doesNotMatch(await page.locator('main').innerText(), /PH-1|PH-2|Có tổ hợp gợi ý/);
      assert.equal(await page.locator('.dc-hints').count(), 0);
      if (change.web_vnd === '1000') assert.equal(await page.locator('.dc-left.ok').count(), 1);
    }
  } finally { await browser.close(); }
});
